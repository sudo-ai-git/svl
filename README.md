# SVL — Self-Verifying Language

SVL (Self-Verifying Language) is a programming language with **built-in three-layer verification** that runs automatically on every compilation:

| Layer | Name | Technology | Purpose |
|-------|------|------------|---------|
| **L1** | Syntax | 231-Gate Checksums | Structural integrity via SUM/LINEAR/PRODUCT mod 231 |
| **L2** | Types | Mod-5 Dual-Stream | Mod-5 buckets + Z/2 negation + structural checksums |
| **L3** | Theorem | BPSW Monodromy | Cryptographic verification via SHA256 + BPSW on primes {37,73,17} |

## Quick Start

```bash
# Full spike suite (48/50 — the 2 failures are H36/H37, genuinely unimplemented)
python -m svl.spike_runner

# REPL
python -m svl.repl

# Interactive LSP server
python -m svl.lsp_server
```

## Features

- **22 tokens** mapped to the Hebrew alphabet (+ ASCII aliases)
- **Deterministic compilation** — bit-identical WASM output across runs, with no `PYTHONHASHSEED`
  pinning required (every value that feeds a checksum, a serialised AST or a program hash is a fixed
  function of its input)
- **A WASM backend that actually executes** — `while` (incl. nested), `for i in a..b`, `if`/`else`,
  `if…then…else` *expressions*, top-level `const`/`var`, `assert`, `print`/`print_int` compile, assemble
  under wasmtime and run (`svl/compiler_wasm.py`)
- **Self-hosting compiler** — bootstraps in 3 stages
- **Extended type system** — effects, linear/unique types, dependent `vec<T,N>`, gradual typing, macros, module functors, algebraic effects, type classes, higher-kinded types, refinement types, intersection/union, quantified constraints, type families, modal types
- **Verification extensions** — SMT/Z3, incremental 231-gate checksums, proof-carrying code, abstract interpretation, differential verification, property-based testing
- **Compiler optimizations** — SIMD, tail-call optimization, escape analysis, WASM GC, PGO, LTO, hot reload
- **Tooling** — tree-sitter grammar, tactic prover, time-travel debugger, component-model FFI/WIT, package registry with attestations, incremental compilation, distributed build cache, LSIF, docs generation, Jupyter kernel, RL-guided optimization

## Repository Layout

```
svl/                    # Language implementation (lexer, parser, verification, compiler)
SVL_PROGRAMMER_KB.md    # Programmer's knowledge base (complete reference)
svl_grammar.json        # Generated tree-sitter grammar
queries/                # Tree-sitter highlight/injection/local queries
examples/               # Example SVL programs
```

## Verification Gates

1. `python -m svl.spike_s9_bpsw` — BPSW all primes pass
2. `python -m svl.spike_s10_self_verify` — 3-stage bootstrap bit-identical + mutations detected
3. `python -m svl.spike_runner` — no spike regressions (48/50, H36/H37 unimplemented). Note the runner
   **exits non-zero (2)** when any spike fails — that is deliberate: a gate that cannot fail is not a gate.
   On a clean checkout expect `Total: 50 | Passed: 48 | Failed: 2` and exit code **2**; the two failures are
   the self-declared unimplemented stubs, not a broken environment.
4. Golden refs: `python -c "from svl.golden_refs import verify_all_golden_refs; print(verify_all_golden_refs())"`
5. `python -m svl.spike_s17_wasm_determinism` — **assembles** the compiler's output with the wasmtime
   module. A skipped/absent runtime reports FAIL, not success, and a text-level "determinism" check cannot
   see invalid WAT — which is how a backend that produced unassemblable WASM once looked green.
6. Assembling is not enough: the emitted module must **run**. Expected values for a quick probe —
   `while i<=5 { s+=i; i+=1 }` → 15; `for i in 0..5 { s+=i }` → 10; `let r = if c then 10 else 20` with
   `c=0` → 20; `assert x==5` with `x=5` → no trap (and it must trap when the condition is false).

## License

MIT