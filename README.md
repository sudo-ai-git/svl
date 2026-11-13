# SVL — Self-Verifying Language

SVL (Self-Verifying Language) is a programming language with **built-in three-layer verification** that runs automatically on every compilation:

| Layer | Name | Technology | Purpose |
|-------|------|------------|---------|
| **L1** | Syntax | 231-Gate Checksums | Structural integrity via SUM/LINEAR/ROLLING mod 231 |
| **L2** | Types | Mod-5 Dual-Stream | Mod-5 buckets + Z/2 negation + structural checksums |
| **L3** | Theorem | BPSW Monodromy | Cryptographic verification via SHA256 + BPSW on primes {37,73,17} — **constant-true, see the scope note** |

> **Scope of the layers (measured, don't skip this).**
>
> **What is now enforced:** `compile_file_to_wasm` runs a verification gate (AST guard + the type
> checker + an interval abstract interpreter) and **refuses to compile** on failure, so
> "verification runs on every compilation" is true for those checks. Pass `strict=False` to bypass it.
>
> **What they do not do:** they verify **internal consistency and hash properties** — the AST is
> well-formed, types are structurally consistent, the program hash has the expected parity — not that
> your program computes what you meant. Given semantically different programs (`a + 2`, `a - 2`,
> `a * 2`), all layers pass on all of them; only the recorded 231-gate value differs. Treat the gate as
> a *tamper/drift detector against a pinned reference*: it catches a program that **changed**, not one
> that is **wrong**.
>
> **One advertised layer carries no information and is documented as such** rather than quietly run:
> the BPSW "theorem" layer is constant-true (0/200 random programs fail; every residue of {17,37,73}
> parities even) and is now **excluded from `passed`** — `TheoremVerifyResultWrapper.bpsw_status`
> is `"informational"`. The 231-gate's third channel was also degenerate for real programs (the
> old `Π(b+1) mod 231` was 0 for 2000/2000 random 512-byte windows); it was **replaced on
> 2026-11-12 with a rolling hash** `H=(H*31+b) mod 231` (31 is coprime to 231), which is
> non-degenerate and flip-sensitive. The SMT layer is **no longer hollow**: it discharges real
> `assert`s in Z3 and reports a tri-state (`proven` / `counterexample` / `unverified`). See KB §5.3.2.

## Quick Start

```bash
# Full spike suite (41/43 — the 2 failures are H36/H37, genuinely unimplemented)
python -m svl.spike_runner

# Write and RUN a program (compiles to WASM, executes in wasmtime, prints its output)
python3 examples/run_example.py examples/bubble_sort.svl   # sorted=1 sum=28 cmps=15 swaps=8 odds=6
python3 examples/run_example.py examples/sieve.svl         # pi(10)=4 pi(40)=12 pi(70)=19 pi(100)=25

# A playable Snake, written in SVL (w a s d to steer, q to quit; --timeout for real-time)
python3 examples/run_snake.py examples/snake.svl
printf 'dddddsddddd' | python3 examples/run_snake.py examples/snake.svl   # scripted replay

# Build a SELF-ATTESTED artifact and verify it independently
python3 examples/attest.py examples/sieve.svl --out /tmp/sieve.wasm
python3 examples/attest.py --verify /tmp/sieve.wasm     # recomputes the hash; tampering -> INVALID

# The compile-time gate refuses a program it can PROVE is broken (strict=True is the default)
python3 -c "from svl.compiler_wasm import compile_file_to_wasm; compile_file_to_wasm('''module t {
  func main() type int { let a: int = [1, 2, 3]  let i: int = 5  return a[i] } }''')"
# -> SVLVerificationError: provable out-of-bounds index on 'a': index [5, 5] is always >= length(a) = [3, 3]

# REPL
python -m svl.repl

# Prove (or refute) every `assert` in a program with Z3 -- opt-in (`prove=True` / `svlc build --prove`)
python3 -c "from svl.smt_theorem import verify_with_smt; r = verify_with_smt(open('examples/sieve.svl').read()); print(r.status, f'{r.assertions_proven}/{r.assertions_checked} assertions proven')"
python3 -c "from svl.smt_theorem import verify_with_smt; print(verify_with_smt('module t { func f(a: int) type int { assert a + 1 > a return 0 } }').status)"  # proven

# The AST round-trips exactly through the binary format
python3 -c "from svl.serialization import test_roundtrip; test_roundtrip()"

# The Mod-5 lattice laws hold (12/12, exhaustively over all 125 triples)
python3 -c "from svl.mod5_types import verify_mod5_lattice; print(all(verify_mod5_lattice().values()))"

# Self-framing resync: find an artifact's leading block inside a larger stream
python3 -c "open('/tmp/stream.bin','wb').write(b'padding'*100 + open('/tmp/sieve.wasm','rb').read())"
python3 examples/attest.py examples/sieve.svl --locate /tmp/stream.bin   # -> starts: [700]

# Interactive LSP server
python -m svl.lsp_server
```

A complete program (see `examples/`):

```svl
module prog {
  struct Stats { comparisons: int  swaps: int }

  func sort(a: int, n: int) type Stats {
    let st: Stats = Stats{comparisons: 0, swaps: 0}
    let i: int = 0
    while i < n - 1 {
      let j: int = 0
      while j < n - 1 - i {
        st.comparisons += 1
        if a[j] > a[j + 1] then {
          let t: int = a[j]
          a[j] = a[j + 1]
          a[j + 1] = t
          st.swaps += 1
        } else { }
        j += 1
      }
      i += 1
    }
    return st
  }

  func main() type int {
    let a: int = [5, 3, 9, 1, 7, 3]
    sort(a, len(a))
    return a[0] * 100 + len(a)
  }
}
```

## Features

- **22 tokens** mapped to the Hebrew alphabet (+ ASCII aliases), and the alias contract is **tested**
  (`svl/hebrew_alias.py`): 22/22 letter→token mappings, and a program plus its Hebrew spelling must
  compile to **byte-identical** WAT. Final forms (sofit) are excluded by design — a sofit letter only
  occurs at the end of a Hebrew word, so using one as a keyword would be ambiguous.
- **Deterministic compilation** — bit-identical WASM output across runs, with no `PYTHONHASHSEED`
  pinning required (every value that feeds a checksum, a serialised AST or a program hash is a fixed
  function of its input)
- **A WASM backend you can write programs in** — mutable variables (`x = v`, `x += v`), **arrays**
  (literals, `a[i]` read/write with bounds checks, `len`, `zeros(n)`, `for x in <array>`), **structs**
  (declaration, literals, field read/write, pass to functions), **`match`** (`case <lit> => e`,
  `case _ => e`), `while` (incl. nested), `for i in a..b`, `if`/`else`, `if…then…else` *expressions*,
  `const`/`var`, `assert`, `print`/`print_int`, **`free(ptr)`** (returns an allocation to the
  free list), `void` returns, **recursion**, arithmetic, bitwise (`& | ^ << >>`, unary `~`) and
  unary `-`/`!`, **short-circuit `&&`/`||`**, **`try`/`catch`/`throw`**, **top-level
  `import`** (resolved with `base_dir`), and **`extern "c" func name(...)`** — a host import
  you can call like any function. Measured 2026-11-12: the 176-test pytest suite assembles
  **and runs** every construct; the 33-row probe suite is **30 PASS / 0 FAIL / 3 INFO**
  (`svl-rating/probes.py`).
- **Command line** — `pip install -e .` then `svlc build|run|check|corpus|repl|lsp`
  (`svl/cli.py`, console script in `pyproject.toml`). `build|run --prove` discharges every
  `assert` with Z3; `check --json` emits machine-readable problems. Latest tagged release:
  **`v0.7.0`**, with a GitHub Release carrying an attested `.wasm` asset.
- **Packages** — `svlc publish <lib.svl> --version V` verifies a library (syntax, types,
  theorem, determinism ×3), writes the package with its `.svli` contract, copies it into a
  registry directory, and reads it back and re-hashes. `svlc install <name>[@<ver>] --into
  DIR` checks the registry's recorded hashes **before** writing, unpacks into
  `svl_modules/<name>/<ver>/`, and records the dependency in `svl.toml`. `svlc run` a
  program importing it and the linker refuses a source that no longer matches its
  contract — a body-only change (`a + b` → `a - b`, same signature) is caught by the
  recorded source hash, not just signature changes. Verified end to end: publish → add →
  run returns 42; rebuild is byte-identical; a tampered dependency is refused by name.
- **Foreign linking** — `svlc run --link MODULE.wasm` (repeatable) satisfies `extern "c"`
  imports from a compiled foreign module instead of a host callback, with a link-time
  signature check that names both sides of a mismatch. Verified: an SVL program called a
  foreign `add` and got 42. Compiling C from source is **not** wired — `clang --target=
  wasm32` is present but `wasm-ld` is not, so the foreign module is supplied prebuilt.
- ~~**Self-hosting compiler** — bootstraps in 3 stages~~ **RETRACTED**: `svl/compiler_svl.svl` is a
  540-byte stub whose `main()` assigns integer constants and `assert true` — it compiles nothing. There
  is no self-hosted compiler.
- **Extended type system** — a wide type syntax parses, and the status of *every* kind is
  recorded in `svl/feature_registry.py` (`verify_registry()` fails if the parser grows a
  kind with no status decision). **Strict mode refuses what nothing enforces**: `linear int`,
  `int & string`, `vec<int, n>`, `?`, `box int`, `forall a. C => T` and the rest are refused
  at compile time, naming the feature and its status; `strict=False` still compiles them.
  **Refinement types are enforced**, not refused: `{ v: int | v > 0 }` discharges through Z3
  at `let`, call and `return` sites, and a violated obligation is a compile error —
  `let x: {v: int | v > 0} = -5` is refused, `= 5` compiles, and a refined parameter may be
  used as an assumption inside its body. Predicates are QF_LIA over `int`/`bool`; anything
  the encoder declines (`/`, `%`, calls, arrays) is silence, never a discharge.
  **`linear`/`unique` are enforced too**: a static move discipline (Rust-shaped, over
  variable usage rather than memory, since SVL has value semantics) — a bare variable in a
  move position (a `let` RHS, an argument, a `return`) consumes it, and a moved value may
  not be used or moved again. An unconsumed `linear` warns; `unique` is affine.
  **`vec<T, n>` is enforced**: the declared length must match an array literal or `zeros(k)`
  initializer, and nested bounds recurse. Type constructors are **kind-checked** — `type
  Box<a> = ...` gives Box kind `* -> *`, so `Box<int, int>` and a bare `Box` are refused.
  Support matrix (2026-11-12):

  | enforced (checked) | engine-only (not on the compile path) | parse-only |
  |---|---|---|
  | `int`/`float`/`bool`/`string`, struct, named, `fn(...) -> ...`, generic, tuple, array, **refinement**, **linear**, **unique**, **vec** | `*`, `* -> *` | `?`, `forall`, intersection, union |

  Declaration-level features (macros, module types/functors, algebraic effects, type
  classes/instances) parse and are refused by the structural checksum. See KB §11.
- **Formal rating** — `SVL_FORMAL_RATING.md` scores SVL against Rust, Lean, Haskell, OCaml,
  Dafny, Python, C and AssemblyScript on a 7-dimension rubric, execution-measured against the
  gates in `svl-rating/`. Current score: **6.60/10**, **4th of 9** (§19; above OCaml at
  6.50, Dafny at 6.30, Python 3 at 5.85, C and AssemblyScript; Rust leads at 8.20). The
  comparison-language scores are structured assessment from published specifications, not
  measurements.
- **Verification extensions** — incremental 231-gate checksums, proof-carrying code, differential verification, property-based testing. **Real additions here:** `examples/attest.py` binds a compiled artifact to a checkable `content_sha256`, the SMT layer (`svl/smt_theorem.py`) discharges real `assert`s in Z3, `svl/serialization.py` round-trips the binary AST format, and `svl/hebrew_alias.py` pins the Hebrew alias contract. **PCC is real as of 2026-11-12**: `PCCWasmModule.to_wasm_bytes_with_proofs()` emits a binary module with a standard `svl-proofs` custom section that `wasmtime.Module` validates, and `extract_proofs_from_wasm_bytes()` recovers the payload (the old WAT-text form is deprecated — wat2wasm has no custom-section syntax).
- **Whole-program specification** — a module may declare clauses at MODULE scope,
  applying to its entry point (the function exported as `<module>_main`):
  `module m requires <expr> ensures <expr> { func main() ... }`.  This says what the
  PROGRAM guarantees, not just what one function does.  The clauses merge with the entry
  point's own and are discharged by the same Z3 contract prover, so a module spec is
  **proved, not tested**; a module with a spec but no `main` is refused.
- **Compilation certificate (PCC)** — `PCCWasmModule` binds the artifact to its source
  through the compiler: the artifact's own canonical bytes, the recompilation under the
  pinned compiler, and the check that the artifact's bytes **are** that recompilation.
  `verify_pcc_wasm` re-derives the gate and SMT verdict from the source and refuses a
  swapped body, a flipped byte, a forged hash, a forged compiler version or a wrong
  source.  Measured: an artifact carrying a *different* compilation under a
  forged-but-consistent pair of claims used to pass; it is now refused.
- **SMT theorem layer that actually proves things** — `svl/smt_theorem.py` builds a z3 model
  of a program's arithmetic and discharges every `assert` by refuting its negation: `unsat` →
  proven, `sat` → a concrete counterexample. Measured: `assert a + 1 > a` is **proven for all
  `a`**; `assert a > 0` is refuted with the counterexample `a = 0`. It reports a tri-state —
  `proven`, `counterexample`, `unverified`, and `vacuous` (no assertions).
  **Loops and arrays are modelled** (2026-11-12): loop invariants are proposed from the
  condition and the variable initialisers and then *proved* (entry + preservation) before
  use, and arrays use the z3 `Array` theory (`a[i]`, `zeros(n)`, `len`). `/` and `%` remain
  declined — WASM `i32` division truncates while Z3's is Euclidean, and modelling one as the
  other would be a false proof. It is **opt-in** — `compile_file_to_wasm(..., prove=True)` /
  `svlc build|run --prove` — not on by default.

**Codegen IS now affected by the type layer** (2026-11-12): `compiler_wasm.py` runs the type
checker (`svl/type_lowering.py`) and lowers locals, parameters, globals, arithmetic width and
struct resolution from its inferred types. Previously `let x = 1.5` emitted an i32 local
holding an f64 literal (invalid WAT that still parsed) and `x + y` on two floats emitted
`i32.add`.
- **The binary deserializer is real** — `svl/serialization.py` round-trips `to_binary` → `from_binary`
  → `to_binary` exactly. The wire format is **not self-describing** (an int in 1..5, a bool and a
  string of length 1..5 all begin with the same byte), so the reader is driven by the declared field
  types and **raises rather than guessing**. Verified 2026-11-12: all 25 compilable mirror corpus
  programs round-trip exactly, all 43 `NODE_TAGS` node types individually, and every
  `Literal`/`Pattern`/`TypeExpr` discriminator path. `test_roundtrip()` now asserts structural
  equality **and** byte-stability. Known gap: `CastExpr` is not in `NODE_TAGS`, so the
  *serializer* rejects it — it has never been serialisable.
- **Compiler lowerings on the path** — **tail-call optimization** (a tail `return f(args)` with a
  matching in-module signature becomes a WASM `return_call`; a 20000-deep tail-recursive call
  completes where the non-tail form traps), **type-directed lowering** (locals, params, globals,
  arithmetic width, struct resolution), **scope-aware alpha-renaming** (`svl/scope.py`), **array
  `for-in` index scan**, **short-circuit `&&`/`||`**, **`memory.grow` + heap reset**,
  **`try`/`catch` error-flag lowering**, **`print` type dispatch**, and **import linking**. The
  six dead optimizations (SIMD, escape analysis, WASM GC, PGO, LTO, hot reloading) and the RL
  pass-selection compiler (H49) were **removed** on 2026-11-12 rather than left as dead code
  sustaining the claim.
- **Tooling** — `svlc` CLI (`build`/`run`/`check`/`corpus`/`repl`/`lsp`, with `--prove` and
  `--json`), **LSP server** (boots and registers all handlers), **REPL** (evaluates a block and
  remembers definitions), **`extern` FFI** (host imports are callable), tree-sitter grammar,
  tactic prover, time-travel debugger, component-model WIT, package registry with attestations,
  incremental compilation, distributed build cache, LSIF, docs generation, Jupyter kernel.
  Not yet working: non-array iterators are rejected with a clear compile error (only ranges
  and arrays are iterable); allocations are reclaimed only through `free` or the entry-point
  heap reset (there is no garbage collector).

## Repository Layout

```
svl/                    # Language implementation (lexer, parser, verification, compiler)
svl/cli.py              # `svlc` command line (build / run / check / corpus)
pyproject.toml          # packaging + the `svlc` / `svl-lsp` / `svl-repl` console scripts
SVL_PROGRAMMER_KB.md    # Programmer's knowledge base (complete reference)
svl_grammar.json        # Generated tree-sitter grammar
queries/                # Tree-sitter highlight/injection/local queries
examples/               # Example SVL programs
tests/                  # pytest suite (assemble + run every compiled module)
.github/workflows/      # CI: pytest, corpus, golden refs, alias contract, spike suite
pytest.ini              # testpaths = tests
requirements-dev.txt    # every dependency the suite and spikes import
```

## Verification Gates

1. `python -m svl.spike_s9_bpsw` — BPSW all primes pass
2. `python -m svl.spike_s10_self_verify` — 3-stage bootstrap bit-identical + mutations detected
3. `python -m svl.spike_runner` — no spike regressions (41/43, H36/H37 unimplemented). Note the runner
   **exits non-zero (2)** when any spike fails — that is deliberate: a gate that cannot fail is not a gate.
   On a clean checkout expect `Total: 43 | Passed: 41 | Failed: 2` and exit code **2**; the two failures are
   the self-declared unimplemented stubs, not a broken environment. The set is 43 after the dead-optimization
   removals (see the Compiler optimizations bullet above).

4. Golden refs: `python -c "from svl.golden_refs import verify_all_golden_refs; print(verify_all_golden_refs())"`
5. `python -m pytest tests -q` — the CI suite: 166 tests covering type-directed lowering, backend
   execution (assemble **and run**), SMT loop invariants/arrays, TCO, the verification gates and the
   corpus. Every compiled module is validated with `wasmtime.Module`, not by inspecting text.
   `.github/workflows/ci.yml` runs it on Python 3.10/3.11/3.12 plus the corpus check, the golden
   references, the Hebrew alias contract and this spike suite.

6. `python -m svl.spike_s17_wasm_determinism` — **assembles** the compiler's output with the wasmtime
   module. A skipped/absent runtime reports FAIL, not success, and a text-level "determinism" check cannot
   see invalid WAT — which is how a backend that produced unassemblable WASM once looked green.
7. Assembling is not enough: the emitted module must **run**. Expected values for a quick probe —
   `while i<=5 { s+=i; i+=1 }` → 15; `for i in 0..5 { s+=i }` → 10; `let r = if c then 10 else 20` with
   `c=0` → 20; `assert x==5` with `x=5` → no trap (and it must trap when the condition is false).
8. **AST round-trip** — `python3 -c "from svl.serialization import test_roundtrip; test_roundtrip()"`.
   Asserts structural equality **and** byte-stable re-serialisation. A stub deserializer once made
   the old size-only check pass while `from_binary(to_binary(ast))` returned a dict.
9. **The Mod-5 lattice** — `python3 -c "from svl.mod5_types import verify_mod5_lattice; print(all(verify_mod5_lattice().values()))"`
   must print `True` (12 laws, exhaustively over all 125 triples).
10. **The Hebrew alias contract** — `svl.hebrew_alias.verify_mapping()` is 22/22 and
   `verify_alias(source)` requires byte-identical WAT for a program and its Hebrew spelling.
11. **Corpus expectation** (generated by `python svl/corpus_check.py --json`, 2026-11-12) —
    **28 files, 25 compilable, 0 refused, 0 abstract-interpreter findings, 25/25 round-trip
    exact**. The 3 non-compiling files are pre-existing legacy fixtures (all never parsed,
    2 fail with `Unknown identifier 'ELSE'`).
12. **Determinism** — WAT sha256 identical across `PYTHONHASHSEED` 0/1/12345/random, and the
    canonical AST fingerprint is identical for ASCII, Hebrew, re-indented and commented variants.
13. **Defect probe suite** — `python svl-rating/probes.py` (workspace) runs 33 execution probes
    that each must be able to fail: **30 PASS / 0 FAIL / 3 INFO**. The three INFO rows are
    documented scope limits (BPSW constant-true, installable-package/`svlc` CLI, compile-latency
    measurement), not failures.
14. **CLI** — `pip install -e .` then `svlc version` prints `0.1.0` and `svlc run <file.svl>`
    compiles and executes a program.

## License

MIT