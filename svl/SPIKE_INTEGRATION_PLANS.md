# SVL Spike Integration Plans

## Passed Spikes (Ready for Integration)

### H17: SMT-Based Theorem Layer (Z3 Integration) ✓
**Status**: Z3 available and working
**Integration Plan**:
1. Add Z3 as optional dependency in pyproject.toml
2. Create `svl/smt_theorem.py` with Z3-based verification
3. Add `SMTTheoremLayer` class that uses Z3 for:
   - Arithmetic constraint solving
   - Bitvector reasoning
   - Quantifier instantiation
4. Integrate with existing theorem layer as alternative backend
5. Add configuration flag `use_smt: bool`
6. Run regression tests on golden references

**Implementation Priority**: HIGH - Enhances theorem proving power

---

### H19: Symbolic Execution for Theorem Layer ✓
**Status**: Z3 symbolic execution works
**Integration Plan**:
1. Create `svl/symbolic_execution.py` with symbolic interpreter
2. Implement symbolic execution engine for SVL AST
3. Add path exploration with Z3 constraint solving
4. Generate counterexamples for failed verifications
5. Integrate with mutation testing for automated bug finding
6. Add `--symbolic` flag to verification CLI

**Implementation Priority**: HIGH - Enables automated counterexample generation

---

### H22: Differential Verification ✓
**Status**: Works via monodromy comparison
**Integration Plan**:
1. Create `svl/differential.py` with diff verification API
2. Implement `verify_diff(old_source, new_source) -> DiffResult`
3. Compare all 3 verification layers (syntax, types, theorem)
4. Report semantic changes vs textual changes
5. Integrate with git hooks for PR verification
6. Add `svl diff` CLI command

**Implementation Priority**: MEDIUM - Useful for CI/CD

---

### H23: Probabilistic Verification ✓
**Status**: Verification is deterministic (good!)
**Integration Plan**:
1. Document deterministic verification as feature
2. Add benchmark suite for verification performance
3. Consider Monte Carlo for expensive checks (future)
4. No code changes needed - verification is already deterministic

**Implementation Priority**: LOW - Already satisfied

---

### H24: Self-Certifying Compiler ✓
**Status**: Compiler source passes all 3 layers
**Integration Plan**:
1. Add compiler self-verification to bootstrap test
2. Create `svl/self_certify.py` with certification pipeline
3. Generate proof artifacts for each compilation stage
4. Verify WASM output matches source verification
5. Add `--self-certify` flag to compiler

**Implementation Priority**: HIGH - Closes the trust loop

---

### H31: AOT Compilation with Cranelift ✓
**Status**: wasmtime available
**Integration Plan**:
1. Add `svl/aot.py` with AOT compilation pipeline
2. Use wasmtime's Cranelift backend for native code gen
3. Implement `--aot` flag for compiler
4. Cache compiled artifacts for fast startup
5. Benchmark AOT vs JIT for CLI tools
6. Support cross-compilation targets

**Implementation Priority**: MEDIUM - Improves CLI startup time

---

### H39: Semantic Diff ✓
**Status**: Feasible via layer comparison
**Integration Plan**:
1. Create `svl/semantic_diff.py` with diff engine
2. Implement layer-by-layer comparison:
   - Syntax: AST structure diff
   - Types: Type signature diff
   - Theorem: Monodromy signature diff
3. Output structured diff (JSON) for tooling
4. Add `svl diff` CLI command
5. Integrate with GitHub Actions for PR comments

**Implementation Priority**: MEDIUM - Improves code review

---

## Failing Spikes (Need Implementation)

### Language Extensions (Parser + Type Checker)

#### H1: Semantic Versioning in Module System
**Requirements**:
- Parser: `module name@version { }`
- Parser: `import name@version_constraint`
- Version parsing (semver)
- Version resolution algorithm
- Lock file generation

#### H2: Effect System with Row Polymorphism
**Requirements**:
- Parser: `!Effect` annotations on functions
- Effect row types: `!{IO, State, Exception}`
- Effect inference with row polymorphism
- Effect handling in type checker
- Compilation to WASM (effect handlers)

#### H3: Linear/Uniqueness Types
**Requirements**:
- Parser: `linear T`, `unique T` type qualifiers
- Linear type checker (usage tracking)
- Borrow checker (regions)
- Compilation to linear WASM (when available)

#### H4: Dependent Types for Array Bounds
**Requirements**:
- Parser: `Vec<T, n>` where `n: Nat`
- Dependent type checker (simplified)
- Erasure to runtime checks or static proof
- Integration with theorem layer for proofs

#### H5: Gradual Typing with Blame
**Requirements**:
- Parser: `?` type (dynamic)
- Cast syntax: `(e : T)` with blame labels
- Blame tracking in type checker
- Runtime cast checking

#### H6: Macro System with Hygiene
**Requirements**:
- Parser: `macro_rules!` syntax
- Hygienic macro expander
- Pattern matching in macros
- Integration with parser

#### H7: Module Functors
**Requirements**:
- Parser: `module type SIG = { }` and `module M(X: SIG) = { }`
- Functor application and sharing constraints
- Type checking of functor bodies

#### H8: Algebraic Effects with Handlers
**Requirements**:
- Parser: `effect E { }` and `handler H for E { }`
- Effect typing rules
- Handler compilation to WASM

#### H9: Type Classes with Coherence
**Requirements**:
- Parser: `class C a where { }` and `instance C T where { }`
- Dictionary passing elaboration
- Coherence checking

#### H10: Higher-Kinded Types
**Requirements**:
- Kind system: `Type -> Type`
- Parser: `f<_>` syntax
- Kind inference

#### H11: Refinement Types
**Requirements**:
- Parser: `{ v: T | P(v) }`
- SMT-based refinement checking
- Liquid types integration

#### H12: Intersection and Union Types
**Requirements**:
- Parser: `A & B`, `A | B`
- Subtyping with intersections/unions
- Type inference with unions

#### H13: Quantified Constraints
**Requirements**:
- Parser: `forall a. C a => D a`
- Constraint solver extension

#### H14: Type-Level Computation
**Requirements**:
- Parser: `type family F a where { }`
- Type family reduction
- Confluence checking

#### H15: Linear Type Inference with Regions
**Requirements**:
- Region inference algorithm
- Integration with linear types

#### H16: Modal Types for Staging
**Requirements**:
- Parser: `□T`, `◇T`
- Staging type rules
- Code generation for staged code

### Compiler/Runtime Improvements

#### H18: Incremental 231-Gate Checksums
**Requirements**:
- Incremental checksum API
- AST change detection
- O(1) update on local edits

#### H20: Proof-Carrying Code for WASM
**Requirements**:
- WASM custom sections for proofs
- Proof format specification
- Proof checker in WASM

#### H21: Abstract Interpretation for Type Layer
**Requirements**:
- Abstract domains (intervals, congruences)
- Fixpoint computation
- Integration with dual-stream

#### H25: WASM GC Proposal Support
**Requirements**:
- Emit `struct` and `array` WASM GC types
- GC root management
- Integration with linear types

#### H26: SIMD Vectorization
**Requirements**:
- Loop detection
- SIMD instruction selection
- WASM SIMD emission

#### H27: Tail Call Optimization
**Requirements**:
- TCO detection in compiler
- `return_call` emission
- Stack usage verification

#### H28: Escape Analysis
**Requirements**:
- Escape analysis pass
- Stack allocation for non-escaping objects

#### H29: Profile-Guided Optimization
**Requirements**:
- Profile collection in WASM
- Profile-guided optimization passes

#### H30: Link-Time Optimization
**Requirements**:
- wasm-ld integration
- Cross-module inlining

#### H32: Hot Reloading with State Migration
**Requirements**:
- State serialization format
- Schema migration logic
- REPL integration

### Tooling/Ecosystem

#### H33: LSP with Tree-sitter
**Requirements**:
- Tree-sitter grammar for SVL
- LSP semantic tokens provider

#### H34: Interactive Theorem Proving
**Requirements**:
- Tactic language
- Proof state management
- REPL integration

#### H35: Time-Travel Debugging
**Requirements**:
- Deterministic execution trace
- Replay engine

#### H36: Visual AST/Type Explorer
**Requirements**:
- Web-based visualization
- AST/type graph rendering

#### H37: AI-Assisted Proof Search
**Requirements**:
- Local LLM integration
- Tactic suggestion engine

#### H38: Property-Based Testing
**Requirements**:
- Hypothesis integration
- Generator derivation from types

#### H40: Error Messages with Repair Suggestions
**Requirements**:
- Error categorization
- Repair suggestion engine
- ML-based improvement (optional)

#### H41: FFI with C/Rust via Component Model
**Requirements**:
- WASM Component Model support
- WIT generation from SVL
- Host bindings

#### H42: WIT Generation
**Requirements**:
- WIT emitter from SVL modules
- Round-trip testing

#### H43: Package Registry with Verification
**Requirements**:
- Attestation format
- Registry API
- Verification on install

#### H44: Incremental Compilation
**Requirements**:
- Salsa integration
- Query-based compiler architecture

#### H45: Distributed Build Cache
**Requirements**:
- Remote execution protocol
- Content-addressed cache

#### H46: LSIF for Code Navigation
**Requirements**:
- LSIF emitter
- Index upload integration

#### H47: Docs Generation from Verification
**Requirements**:
- Doc generator from types/theorems
- Example extraction

#### H48: REPL Notebooks (Jupyter Kernel)
**Requirements**:
- IPython kernel protocol
- Verification display in notebooks

#### H49: Self-Optimizing Compiler (RL)
**Requirements**:
- RL environment for compiler passes
- Training infrastructure

#### H50: Verified Distributed Consensus (Raft)
**Requirements**:
- Raft implementation in SVL
- Full 3-layer verification
- Network model formalization