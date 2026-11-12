# Expert report — tooling, DX & ecosystem

## repl-evaluates  (addresses F12, effort M, risk Medium — a new execution path can trap or leak past the 1 MiB ceiling (F8), so errors must be caught and surfaced as REPL messages, not tracebacks.)

**Problem.** svl/repl.py:228 feeds a raw line to verify_syntax, but svl/parser_rd.py:969 parse_top_level only accepts declarations, so `let x = 1` raises 'Unexpected token at top level'; svl/repl.py:307 _execute_block only re-verifies and never compiles or runs anything, and :322 _reset_buffer discards definitions so no state survives between inputs.

**Proposal.** (a) Wrap the pending buffer in `module repl { ... }` in _verify_current_line/_verify_buffer_incremental before calling the verification layers, and in _execute_block before compiling. (b) Add a real execution path in _execute_block: compile_file_to_wasm -> wasmtime.wat2wasm -> Module -> Linker with the host ABI (extract the import definitions from tests/conftest.py:48-66 into svl/host_abi.py and reuse them in both places) -> call the exported main -> print the i32 result. (c) Keep a persistent self.state.definitions list that survives _reset_buffer, and for each evaluation append a synthetic `func __repl_expr() type int { return <expr> }` so `x + 1` works after `let x = 1`.

**Expected.** `printf 'let x = 1\n\nx + 1\n\nexit\n' | python -m svl.repl` prints 1 then 2 with no 'Unexpected token at top level'; the Jupyter kernel (jupyter_kernel.py:124-128) inherits the same fix and stops reporting 'Executed successfully' for code it never ran.

**Spike.** Given a REPL session, when the user types `let x = 1` then a blank line, then `x + 1` then a blank line, then the output must contain 1 and 2 and no Syntax Error. Throwaway: wrap the buffer in `module repl { ... }` in a scratch script, compile with compile_file_to_wasm, run under wasmtime with the conftest host imports, and assert the returned i32 is 2.

## lsp-boot-fix  (addresses F11, effort S, risk Low)

**Problem.** svl/lsp_server.py:357-365 calls server.feature(NAME)(server.<method>), passing a bound method; pygls 2.1.1's assign_help_attrs (pygls/feature_manager.py:44) does setattr(f, ATTR_REGISTERED_NAME, reg_name), which bound methods reject -> AttributeError: 'method' object has no attribute 'reg_name'. pygls/lsprotocol are also absent from requirements-dev.txt, so CI cannot even import the module.

**Proposal.** Change the eight registrations to pass the unbound functions (SVLLanguageServer.initialize, .did_open, .did_change, .did_close, .did_save, .completion, .hover, .definition, .semantic_tokens_full) — verified all nine register cleanly in a probe — or define module-level `def handler(ls, params)` functions and decorate them. Add pygls>=2.1 and lsprotocol>=2025.0 to requirements-dev.txt (or a requirements-lsp.txt), and add tests/test_lsp_boot.py that constructs SVLLanguageServer, registers the features, and asserts no exception plus a framed initialize response.

**Expected.** python -m svl.lsp_server reaches start_io() and answers an LSP initialize request; pytest tests/test_lsp_boot.py passes; the P19 probe in svl-rating/probes.py flips from FAIL to PASS.

**Spike.** Given pygls 2.1.1 installed, when main() registers SVLLanguageServer.initialize instead of server.initialize, then no AttributeError is raised and the server responds to initialize. Already proven: a probe registering all nine unbound handlers completed without error.

## svlc-cli-pyproject  (addresses L3, effort M, risk Low)

**Problem.** There is no pyproject.toml/setup.py in the repo (only unrelated ones under flipper-gui/ and tanakh-vre-guard/), no svl/__init__.py (the package is an implicit namespace package), and the only CLI is svl/package_manager.py:266 with prog="svl", reachable only as `python -m svl.package_manager`; repl.py and lsp_server.py are only reachable as modules.

**Proposal.** Add pyproject.toml (setuptools; name="svl"; version read from svl/__init__.py; dependencies = the hard module-level imports already enumerated in requirements-dev.txt:12-18; [project.optional-dependencies] lsp = ["pygls>=2.1","lsprotocol>=2025.0"]), with [project.scripts] svlc = "svl.cli:main", svl-lsp = "svl.lsp_server:main", svl-repl = "svl.repl:run_repl". Add svl/__init__.py with __version__ and lazy re-exports. Add svl/cli.py with build|run|check|repl|lsp|corpus|pkg subcommands; run uses compile_file_to_wasm + wasmtime + the shared svl/host_abi.py.

**Expected.** In a clean venv, `pip install -e .` then `svlc --version` prints 0.1.0, `svlc run <file.svl>` prints the program's result, `svlc check <file.svl>` exits non-zero on a gate refusal, and `svlc repl`/`svlc lsp` dispatch to the fixed REPL/LSP.

**Spike.** Given a clean venv, when `pip install -e . --no-deps` is run, then `svlc --help` lists the subcommands and `svlc run` on a known-good program prints the expected value. Throwaway: `python -m venv /tmp/v && /tmp/v/bin/pip install -e . --no-deps && /tmp/v/bin/svlc --version`.

## ci-branch-tooling-smoke  (addresses L5, effort S, risk Low)

**Problem.** .github/workflows/ci.yml:5 triggers on branches: [master], but the public mirror's branch is main, so CI never runs; the workflow also only runs pytest/corpus/golden-refs/spikes and never touches the LSP, REPL, or CLI, so F11/F12/L3 can never be caught.

**Proposal.** Change line 5 to branches: [master, main] (or drop the branch filter). Add a tooling job that (a) boots `python -m svl.lsp_server`, sends a framed initialize, and asserts no traceback; (b) pipes `let x = 1\n\nx + 1\n\n` into `python -m svl.repl` and asserts the output contains 2; (c) runs `svlc --version` once the CLI exists. Add pygls/lsprotocol to the CI install so (a) is exercisable.

**Expected.** A push to the mirror's main branch produces a green (or honestly red) run; a regression in the LSP/REPL/CLI fails CI instead of passing silently.

**Spike.** Given the workflow with branches: [main], when a commit is pushed to main, then a run appears in the Actions tab. Throwaway: push a dummy commit to a main branch in a scratch clone and check the run is triggered.

## package-manager-wat-mislabel  (addresses L3, effort S, risk Low)

**Problem.** svl/package_manager.py:124 sets wasm = compile_file_to_wasm(source), which returns WAT text, and :152 writes it with write_text to module.wasm; svl/package_registry.py:231 then tests content[:4] == b"\x00asm", which is never true, so every published package is recorded UNVERIFIED. Separately :190 install() raises NotImplementedError and :212 publish() only prints 'Published successfully' without uploading, yet both are advertised in the argparse CLI at :280-287.

**Proposal.** Convert WAT to binary with wasmtime.wat2wasm before writing (or write module.wat and name the field accordingly), and hash the binary. For the dead commands, either implement local install by copying from ~/.svl/packages using the existing index, or make the CLI print 'not implemented' and exit 2 while removing them from --help and the README.

**Expected.** `svlc pkg create demo 1.0.0 src.svl` writes a file whose first four bytes are 00 61 73 6d; publish then records VERIFIED when the artifact's svl.attest section checks out; `svlc pkg install` no longer raises NotImplementedError.

**Spike.** Given PackageManager.create_package, when the written module.wasm is read as bytes, then content[:4] == b"\x00asm". Throwaway: run create_package on a small source and `xxd -l 4` the output.

## corpus-baseline-generated  (addresses L4, effort S, risk Low)

**Problem.** The public README states '52 files, 42 compilable', but SVL_FORMAL_RATING.md:30-31 measures 28 files / 23 compilable on the mirror; svl/corpus_check.py:42 hard-codes MIN_COMPILABLE = 20, below the measured 23, and :32-37 globs examples/ and svl-release/examples/, which do not exist in this workspace, so a missing directory is silently skipped.

**Proposal.** Add --json and --write-baseline to corpus_check.py, persist the measured counts in a versioned corpus_baseline.json, raise MIN_COMPILABLE to the measured value (23 on the mirror) or default it to the baseline file, and replace the README's hand-written '52 files, 42 compilable' with the generated number plus a date. Add a CI step that runs the checker and fails if the README number drifts. Make the dead globs explicit (or drop them) so a missing directory is reported, not skipped.

**Expected.** The README reads '28 files, 23 compilable (2026-11-12)'; a change that drops the compilable count to 22 fails CI; the L4 probe flips to PASS.

**Spike.** Given `corpus_check.py --json`, when its files/compiled fields are compared to the numbers printed in the README, then they match. Throwaway: run the checker and diff its output against the README claim.

