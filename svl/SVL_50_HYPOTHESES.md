# SVL Language: 50 Hypotheses for Improvement

## Core Language Architecture (H1-H8)

**H1: Semantic Versioning in Module System**
- Hypothesis: Adding explicit semantic versioning (`module foo@1.2.3`) with version constraints in imports will prevent diamond dependency issues and enable reproducible builds.
- Test: Spike to verify version resolution algorithm with semantic versioning.

**H2: Effect System with Row Polymorphism**
- Hypothesis: Adding an effect system (IO, State, Exception, Async) with row polymorphism will enable precise effect tracking while maintaining inference ergonomics.
- Test: Spike to implement effect inference on a subset of programs.

**H3: Linear/Uniqueness Types for Resource Safety**
- Hypothesis: Adding linear types (`linear T`, `unique T`) will enable compile-time resource management (file handles, memory) without GC.
- Test: Spike to verify linear type checker on resource-heavy programs.

**H4: Dependent Types for Array Bounds**
- Hypothesis: Lightweight dependent types (`Vec<T, n>` where `n: Nat`) will eliminate array bounds checks at runtime.
- Test: Spike to verify dependent type erasure to WASM.

**H5: Gradual Typing with Blame Calculus**
- Hypothesis: Adding gradual typing (`?` type) with blame tracking will enable safe migration from dynamic to static code.
- Test: Spike to verify blame assignment on boundary crossings.

**H6: Macro System with Hygiene (Racket-style)**
- Hypothesis: A hygienic macro system (`syntax-rules` / `syntax-case`) will enable syntactic abstraction without capture bugs.
- Test: Spike to verify macro expansion preserves hygiene.

**H7: Module Functors (ML-style)**
- Hypothesis: Parameterized modules (functors) will enable generic data structures and abstraction over implementations.
- Test: Spike to verify functor application and sharing constraints.

**H8: Algebraic Effects with Handlers**
- Hypothesis: First-class algebraic effects with handlers will replace monad transformers and enable direct-style async/error handling.
- Test: Spike to verify effect handler compilation to WASM.

---

## Type System Enhancements (H9-H16)

**H9: Type Classes with Coherence**
- Hypothesis: Adding type classes (like Haskell) with coherence checking will enable ad-hoc polymorphism without dictionary passing overhead.
- Test: Spike to verify coherence and dictionary elaboration.

**H10: Higher-Kinded Types (HKT)**
- Hypothesis: Adding HKT (`F<T>` where `F: Type -> Type`) will enable generic programming over functors/monads.
- Test: Spike to verify HKT kind inference and compilation.

**H11: Refinement Types (Liquid-style)**
- Hypothesis: Adding refinement types (`{v: int | v > 0}`) will enable verification of invariants at compile time.
- Test: Spike to verify SMT-based refinement checking.

**H12: Intersection and Union Types**
- Hypothesis: Adding intersection (`A & B`) and union (`A | B`) types will enable precise typing of heterogeneous collections.
- Test: Spike to verify subtyping algorithm with intersections/unions.

**H13: Quantified Constraints**
- Hypothesis: Adding quantified constraints (`forall a. C a => D a`) will enable more expressive type class constraints.
- Test: Spike to verify constraint solving with quantifiers.

**H14: Type-Level Computation (Type Families)**
- Hypothesis: Type families (`type family F a where F Int = Bool; F String = Int`) will enable type-level computation.
- Test: Spike to verify type family reduction and confluence.

**H15: Linear Type Inference with Regions**
- Hypothesis: Region-based linear type inference (like Rust's borrow checker) will make linear types ergonomic.
- Test: Spike to verify region inference on realistic programs.

**H16: Modal Types for Staging/Code Gen**
- Hypothesis: Modal types (`□A` for code, `◇A` for runtime) will enable multi-stage programming and compile-time metaprogramming.
- Test: Spike to verify staging annotations and code generation.

---

## Verification Layer Improvements (H17-H24)

**H17: SMT-Based Theorem Layer (Z3 Integration)**
- Hypothesis: Replacing BPSW monodromy with Z3-backed verification will enable arbitrary theorem proving while maintaining deterministic proofs.
- Test: Spike to verify Z3 integration and proof reconstruction.

**H18: Incremental 231-Gate Checksums**
- Hypothesis: Incremental checksum updates (on AST edit) will enable O(1) verification for IDE feedback.
- Test: Spike to benchmark incremental vs full recomputation.

**H19: Symbolic Execution for Theorem Layer**
- Hypothesis: Adding symbolic execution (like KLEE) will find counterexamples for failed theorem checks automatically.
- Test: Spike to verify symbolic execution on mutation detection.

**H20: Proof-Carrying Code (PCC) for WASM**
- Hypothesis: Attaching proofs to WASM output will enable zero-trust deployment verification.
- Test: Spike to verify proof attachment and checking in WASM.

**H21: Abstract Interpretation for Type Layer**
- Hypothesis: Abstract interpretation will find type errors that dual-stream misses (e.g., overflow, division by zero).
- Test: Spike to verify abstract domain precision on benchmarks.

**H22: Differential Verification (Regression Detection)**
- Hypothesis: Differential verification (comparing two program versions) will catch semantic regressions automatically.
- Test: Spike to verify diff verification on mutated programs.

**H23: Probabilistic Verification (Monte Carlo)**
- Hypothesis: Monte Carlo verification for expensive checks (with soundness bounds) will speed up CI.
- Test: Spike to verify error bounds on probabilistic checks.

**H24: Self-Certifying Compiler (Bootstrap Proof)**
- Hypothesis: Proving the compiler correct in SVL itself (using theorem layer) will close the trust loop.
- Test: Spike to verify compiler self-certification on subset.

---

## Status update (2026-11-12)

The compiler-optimization hypotheses in this document were re-audited against the live
backend. Result:

| Hypothesis | Outcome |
|---|---|
| **H27** Tail Call Optimization | ✅ **WIRED** — a tail `return f(args)` with a matching in-module signature becomes a WASM `return_call`; verified by executing a 20000-deep call that would otherwise trap. |
| **H25** WASM GC, **H26** SIMD, **H28** escape analysis, **H29** PGO, **H30** LTO, **H32** hot reloading | ❌ **REMOVED** — standalone libraries the compiler never called. Several were stubs that emitted invalid WAT (SIMD hard-coded its loop bounds and a `sum` local; PGO's `optimize` returned its input; LTO's inliner deleted functions that were still called). |
| **H49** Self-optimizing compiler (RL) | ❌ **REMOVED** — every pass was a no-op. |

The descriptions below are kept for the record; they describe what was attempted, not
what the artifact does. See `SVL_PROGRAMMER_KB.md` §13 for the current state.

## Compiler & Runtime Improvements (H25-H32)

**H25: WASM GC Proposal Support**
- Hypothesis: Targeting WASM GC (struct/array types) will reduce binary size and improve GC integration.
- Test: Spike to compile SVL structs to WASM GC types and benchmark.

**H26: SIMD Vectorization for Numeric Code**
- Hypothesis: Auto-vectorization (WASM SIMD) for numeric loops will match native performance.
- Test: Spike to verify SIMD emission on matrix multiplication.

**H27: Tail Call Optimization (TCO) Guarantee**
- Hypothesis: Mandatory TCO (with verification) will enable recursion as primary iteration.
- Test: Spike to verify TCO on recursive functions and stack usage.

**H28: Escape Analysis for Stack Allocation**
- Hypothesis: Escape analysis will allocate short-lived structs on stack, reducing GC pressure.
- Test: Spike to measure allocation reduction on benchmarks.

**H29: Profile-Guided Optimization (PGO)**
- Hypothesis: PGO with WASM profiling (via `wasm-instr`) will optimize hot paths.
- Test: Spike to verify PGO feedback loop and speedup.

**H30: Link-Time Optimization (LTO) for WASM**
- Hypothesis: WASM LTO (via `wasm-ld`) will enable cross-module inlining and dead code elimination.
- Test: Spike to measure binary size and speedup with LTO.

**H31: AOT Compilation with Cranelift/Winch**
- Hypothesis: AOT compilation to native code (via Cranelift) will beat JIT startup for CLI tools.
- Test: Spike to benchmark AOT vs JIT startup and throughput.

**H32: Hot Reloading with State Migration**
- Hypothesis: Hot code reloading with automatic state migration (via versioned structs) will enable live development.
- Test: Spike to verify state migration on struct schema changes.

---

## Developer Experience (H33-H40)

**H33: LSP with Semantic Highlighting (Tree-sitter)**
- Hypothesis: Tree-sitter grammar + LSP semantic tokens will enable precise IDE highlighting.
- Test: Spike to implement Tree-sitter grammar and verify LSP integration.

**H34: Interactive Theorem Proving (Tactics)**
- Hypothesis: Tactic-based interactive proving (like Coq/Lean) will make theorem layer accessible.
- Test: Spike to implement basic tactic language and verify on golden refs.

**H35: Time-Travel Debugging (Replay)**
- Hypothesis: Deterministic execution + event log will enable time-travel debugging.
- Test: Spike to verify replay determinism on WASM.

**H36: Visual AST/Type Explorer**
- Hypothesis: Interactive visualization of AST, types, and verification state will aid debugging.
- Test: Spike to build web-based explorer and verify on compiler source.

**H37: AI-Assisted Proof Search**
- Hypothesis: LLM-guided tactic search (using local model) will automate trivial theorem steps.
- Test: Spike to verify LLM tactic suggestions on proof corpus.

**H38: Property-Based Testing Integration**
- Hypothesis: Integrated property-based testing (like QuickCheck) with theorem layer will find bugs.
- Test: Spike to verify property generation from type signatures.

**H39: Semantic Diff (Not Textual)**
- Hypothesis: Semantic diff (AST + type + verification aware) will show meaningful changes in PRs.
- Test: Spike to verify semantic diff on mutated golden refs.

**H40: Error Messages with Repair Suggestions**
- Hypothesis: ML-based error message improvement (with repair suggestions) will reduce fix time.
- Test: Spike to verify suggestion quality on common error corpus.

---

## Ecosystem & Interop (H41-H48)

**H41: FFI with C/Rust via WASM Component Model**
- Hypothesis: WASM Component Model will enable safe, typed FFI without C headers.
- Test: Spike to verify component model bindings for a C library.

**H42: WebAssembly Interface Types (WIT) Generation**
- Hypothesis: Auto-generating WIT from SVL modules will enable polyglot composition.
- Test: Spike to verify WIT generation and round-trip.

**H43: Package Registry with Verification Attestation**
- Hypothesis: Package registry storing verification proofs will enable trust-on-first-use.
- Test: Spike to verify attestation format and registry API.

**H44: Incremental Compilation (Salsa/IncR)**
- Hypothesis: Salsa-based incremental compilation will make REPL/IDE fast on large codebases.
- Test: Spike to benchmark incremental rebuilds on compiler source.

**H45: Distributed Build Cache (BuildBarn/Remote Execution)**
- Hypothesis: Remote execution + content-addressed cache will enable fast CI/builds.
- Test: Spike to verify cache hit rates on monorepo.

**H46: Language Server Index Format (LSIF) for Code Navigation**
- Hypothesis: LSIF emission will enable precise cross-repo code navigation in GitHub/GitLab.
- Test: Spike to verify LSIF generation and upload.

**H47: Docs Generation from Verification Artifacts**
- Hypothesis: Auto-generating docs from types, theorems, and examples will keep docs in sync.
- Test: Spike to verify doc generation on standard library.

**H48: REPL Notebooks (Jupyter Kernel)**
- Hypothesis: Jupyter kernel with live verification cells will enable literate programming.
- Test: Spike to verify kernel protocol and verification display.

---

## Radical/Research Ideas (H49-H50)

**H49: Self-Optimizing Compiler (ML-Guided)**
- Hypothesis: RL agent controlling optimization passes (inlining, unrolling) will beat fixed heuristics.
- Test: Spike to train RL agent on compilation corpus and verify speedup.

**H50: Verified Distributed Consensus (Raft in SVL)**
- Hypothesis: Implementing Raft consensus in SVL with full theorem verification will produce bug-free distributed systems code.
- Test: Spike to verify Raft implementation passes all 3 verification layers.