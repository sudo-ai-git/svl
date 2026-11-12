# Expert report — verification & assurance

## gate-refuse-unsupported  (addresses ['F2', 'F5', 'F6', 'F9', 'F10'], effort M, risk Medium — false positives on existing corpus programs are possible (sweep examples/ and tests/ first); local const reassignment already fails at parse time, so the const check mainly matters for module-level consts.)

**Problem.** verify_program (svl/verify_gate.py:38-80) runs the AST guard, type layer and interval AI, but the AI only reports OOB/div-zero (svl/abstract_interpretation.py:1183-1230); the backend then silently no-ops iterator `for` (svl/compiler_wasm.py:582-625, `call $iterator_next` at 608-613), emits a one-operand `call $print` for print(<int>) (compiler_wasm.py:1039-1044), and emits `global.set` on an immutable const global (compiler_wasm.py:265-284, mutability CONST at 281-282), so a program can pass the gate and still be wrong.

**Proposal.** Add a backend-contract pass to the gate: extend ASTGuard (svl/ast_guard.py:39-85) or add check_backend_support(ast) in a new svl/backend_contract.py, emitting a Finding(severity='error') for (a) ForStmt whose iter_expr is not BinaryExpr('..'); (b) CallExpr to print whose argument is not a string Literal; (c) AssignExpr / ExprStmt(AssignExpr) targeting a name collected from ConstDecl (extend _collect, abstract_interpretation.py:762-793, to return const_names); (d) Import and TryStmt nodes, which the backend drops or rejects late. Wire it into verify_program as step 3.5 and into the default strict compile (compiler_wasm.py:1521-1523).

**Expected.** The program `let a=[1,2,3] let s=0 for x in a { s+=x } return s` raises SVLVerificationError('... iterator for-loop is not supported by the backend ...') instead of returning 0; `let x=5 print(x)` and `const c: int = 5 ... c = 6` are refused with the construct named; the 61-test suite and corpus_check still pass.

**Spike.** Given the five failing constructs (for-in, print(int), const reassignment, try/catch, import), when compiled with compile_file_to_wasm(src) under the strict default, then each raises SVLVerificationError naming the construct; and `python -m pytest tests -q` stays 61/61 with corpus_check reporting 0 newly-refused files.

## demote-bpsw  (addresses ['L1'], effort M, risk Low — removes a false guarantee; requires updating README/rating claims and the PCC proof schema.)

**Problem.** compute_monodromy_for_prime (svl/bpsw_monodromy.py:232-256) runs BPSW on program_hash % p for p in {17,37,73}, so the tested value is always below 73 and MR-base-2 plus Lucas-Selfridge agree on every input; verify_theorem (bpsw_monodromy.py:301-334) is therefore constant-true (measured 0/60 random ASTs fail), yet it is counted as a verification layer in TheoremLayer.verify_theorem (svl/theorem_layer.py:133,186) and embedded as the theorem proof by PCCWasmGenerator.generate (svl/pcc_wasm.py:120-139).

**Proposal.** Remove theorem_result.passed and all_parities_even from TheoremVerifyResultWrapper.passed (theorem_layer.py:186) and keep the computation only as bpsw_status='informational' with a docstring stating it is a hash-primality certificate, not a program proof. Replace the PCC theorem artifact with the independently checkable svl.attest payload (attest.ast_fingerprint, svl/attest.py:148-169) so the artifact binds source_sha256 to ast_sha256 to content_sha256 and can be rejected by attest.verify_attestation (attest.py:241-258). If a real primality test is wanted, apply BPSW to the full 256-bit program_hash rather than hash % p and report it as a curiosity, never as evidence.

**Expected.** verify_theorem_layer(src).passed is computed from syntax, types and attestation only; the wrapper exposes bpsw_status='informational'; PCCWasmGenerator embeds attest.ast_fingerprint(source) and verify_pcc_wasm recomputes content_hash, so flipping one byte of the module body makes verification fail. Probe P13 is retired as evidence rather than reported as a green check.

**Spike.** Given 60 programs, when running the new theorem layer, then passed equals the syntax/type/attestation verdict for all 60; and given a generated PCC artifact, when one byte of its code section is flipped, then verify_pcc_wasm returns False with a hash mismatch (before the change it returned True because the proof was self-declared).

## fix-product-channel  (addresses ['L2'], effort S, risk Low — but it changes the pinned gate231 triple, so golden references and attestation payloads (attest.py:156 documents a pinned gate [167, 10, 0]) must be regenerated.)

**Problem.** product_checksum (svl/gate231.py:24-29) computes the product of (b+1) mod 231; because 231 = 3*7*11, any byte with b+1 congruent to 0 mod 3, 7 or 11 forces the product to 0 and it can never recover — measured 2000/2000 random 512-byte windows give 0 (1 distinct value), degenerating the 231-gate and attest.locate_sync (svl/attest.py:47-55, which documents the effective keyspace as 231^2).

**Proposal.** Replace the PRODUCT channel with a polynomial rolling hash H = (H*31 + b) mod 231 (31 is coprime to 231) or an FNV-1a 32-bit hash reduced mod 231, keeping the (SUM, LINEAR, PRODUCT) tuple shape and meta_checksum (gate231.py:47-50) so type_layer._verify_structural (svl/type_layer.py:215-236), attest.ast_fingerprint and verify_checksums need no signature changes. Rename the field to ROLLING if desired but keep its tuple position.

**Expected.** 2000 random 512-byte windows yield more than 100 distinct PRODUCT values and fewer than 1% zeros; verify_checksums becomes falsifiable (a one-byte change alters the checksum with probability about 1 - 1/231); locate_sync's false-sync rate drops from about 1/53361 to about 1/231^3 per position.

**Spike.** Given 2000 random 512-byte windows, when computing the new PRODUCT channel, then len(set(values)) > 100 and zeros/2000 < 0.01; and when one byte of a window is flipped, then the checksum changes.

## pcc-real-custom-section  (addresses ['F7'], effort S, risk Low — the `(@custom ...)` form is already proven to assemble in this repo (attest._section_text).)

**Problem.** PCCWasmModule.to_wasm_with_proofs (svl/pcc_wasm.py:32-66) inserts `(custom "svl-proofs" "<hex>")` into the WAT; `(custom ...)` is not a valid WAT module field — measured: wasmtime.wat2wasm rejects it with 'expected valid module field', while `(@custom "svl-proofs" "\de\ad\be\ef")` assembles. extract_proofs_from_wasm (pcc_wasm.py:215-231) parses only the invalid form, the binary encoder WasmCustomSection.create_proof_section (pcc_wasm.py:297-301) is never used, and verify_proofs (pcc_wasm.py:68-71) just ANDs self-declared booleans.

**Proposal.** Emit `(@custom "svl-proofs" "<wat-escaped bytes>")` using the same escaping as attest._wat_escape and attest._section_text (svl/attest.py:144-146, 188-196), and update extract_proofs_from_wasm's regex to match it; or add to_wasm_bytes() that assembles the WAT and appends WasmCustomSection.create_proof_section. Replace the self-declared passed booleans with attest's content_sha256 and ast_sha256 so verify_pcc_wasm (pcc_wasm.py:234-252) recomputes the canonical hash and fails on mutation.

**Expected.** PCCWasmGenerator().generate(src).to_wasm_with_proofs() is accepted by wasmtime.wat2wasm and wasmtime.Module; extract_proofs_from_wasm recovers the payload; verify_pcc_wasm returns True on the untouched artifact and False with a hash mismatch after a one-byte code change.

**Spike.** Given a generated PCC artifact, when assembled with wasmtime.wat2wasm, then it succeeds (before: 'expected valid module field'); and when one byte of the code section is flipped, then verify_pcc_wasm returns False.

## smt-opt-in-compile  (addresses ['F4', 'L1'], effort M, risk Low-Medium — SMT cost is opt-in; the Z3-absent fix is a pure bug fix; merging AI and SMT findings needs a shared result type.)

**Problem.** The SMT layer is real (svl/smt_theorem.py:758-819) but opt-in and off the compile path: verify_program (svl/verify_gate.py:38-80) never calls it and compile_file_to_wasm (svl/compiler_wasm.py:1503-1532) has no prove flag, while verify_program_theorem still runs the constant-true BPSW layer first (smt_theorem.py:766-771). Conversely TheoremLayer.verify_theorem folds smt_verified into all_passed unconditionally (svl/theorem_layer.py:186), so on an interpreter without z3 (SMT_INTEGRATION=False, theorem_layer.py:18-38) every program is reported as failed — a false refusal.

**Proposal.** (a) Add prove=False to compile_file_to_wasm; when set, run smt_theorem.verify_with_smt(source) after assert_verified and raise SVLVerificationError with the model on status='counterexample'. (b) Fix theorem_layer.py:186 to include smt_verified only when the SMT layer actually ran (smt_ran = SMT_INTEGRATION and Z3_AVAILABLE and config.use_smt), adding smt_skipped to the wrapper. (c) Remove the BPSW pre-gate in verify_program_theorem so the prover is not chained to the decorative layer. (d) Return AI findings and the SMT status from one combined result so the gate can report proven / refused / unverified honestly.

**Expected.** compile_file_to_wasm('func f(a: int) type int { assert a > 0 return 0 }', prove=True) raises SVLVerificationError with counterexample a=0, while `assert a + 1 > a` compiles with status='proven'; without z3 installed, verify_theorem_layer(src).passed is True and smt_skipped=True instead of False.

**Spike.** Given a program with `assert a > 0`, when compiled with prove=True, then compilation is refused and the counterexample model is printed; and given the same program on an interpreter with z3 hidden, when calling verify_theorem_layer, then passed is True (before the fix: False for every program).

## type-boundary-soundness  (addresses ['F4'], effort M, risk Medium — string-returning void functions and the array-handle/int allowance need care; a corpus sweep is required.)

**Problem.** TypeChecker._check_return_stmt (svl/type_inference.py:852-854) synthesizes the return value's type but never unifies it with the enclosing FuncDecl.return_type, and _synth_call (type_inference.py:518-527) returns the callee's return type without unifying argument types with parameter types — so `return "hi"` in a `type int` function and `f("hi")` against `f(x: int)` pass verify_type and therefore the gate (svl/verify_gate.py:56-62).

**Proposal.** In _check_func_decl (type_inference.py:883-917), compute return_type before walking the body and record it on the checker; in _check_return_stmt, unify the synthesized value type with it and append 'Type mismatch in return: ...' on failure. In _synth_call, after instantiating the callee's Type.func, unify each argument's synthesized type with the corresponding parameter type (skipping builtins with type vars and the array-handle/int allowance already used for `let`). verify_type already forwards these errors to verify_gate, so no gate change is needed.

**Expected.** `func f() type int { return "hi" }` and `func f(x: int) type int { return x }` called as `f("hi")` both raise SVLVerificationError at the default strict compile; `let x: int = "hi"` still fails; void functions with no return value are unaffected; P15 flips to PASS.

**Spike.** Given the two boundary programs, when compiled with compile_file_to_wasm(src) under the strict default, then each raises SVLVerificationError naming the boundary; and `python -m pytest tests -q` plus corpus_check still pass (void and never/Error returns must not be caught).

