# SVL — Self-Verifying Language

SVL (Self-Verifying Language) is a programming language with **built-in three-layer verification** that runs automatically on every compilation:

| Layer | Name | Technology | Purpose |
|-------|------|------------|---------|
| **L1** | Syntax | 231-Gate Checksums | Structural integrity via SUM/LINEAR/PRODUCT mod 231 |
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
> parities even). The 231-gate's PRODUCT channel is also degenerate for real programs (0 for
> 2000/2000 random 512-byte windows). The SMT layer is **no longer hollow**: it discharges real
> `assert`s in Z3 and reports a tri-state (`proven` / `counterexample` / `unverified`). See KB §5.3.2.

## Quick Start

```bash
# Full spike suite (48/50 — the 2 failures are H36/H37, genuinely unimplemented)
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

# Prove (or refute) every `assert` in a program with Z3 -- opt-in, NOT on the compile path
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
  (literals, `a[i]` read/write with bounds checks, `len`, `zeros(n)`), **structs** (declaration, literals,
  field read/write, pass to functions), **`match`** (`case <lit> => e`, `case _ => e`), `while` (incl.
  nested), `for i in a..b`, `if`/`else`, `if…then…else` *expressions*, `const`/`var`, `assert`,
  `print`/`print_int`, `void` returns, **recursion**, arithmetic, bitwise (`& | ^ << >>`, unary `~`) and
  unary `-`/`!`. Measured against a 38-construct matrix: **35 run correctly, 0 wrong answers**
  (`svl/compiler_wasm.py`).
- ~~**Self-hosting compiler** — bootstraps in 3 stages~~ **RETRACTED**: `svl/compiler_svl.svl` is a
  540-byte stub whose `main()` assigns integer constants and `assert true` — it compiles nothing. There
  is no self-hosted compiler.
- **Extended type system** — effects, linear/unique types, dependent `vec<T,N>`, gradual typing, macros, module functors, algebraic effects, type classes, higher-kinded types, refinement types, intersection/union, quantified constraints, type families, modal types — **parse-level only.** The
  qualifiers are parsed and then consumed by nothing: `grep "kind == 'linear'"` outside the parser
  returns no engine, and `type_families._match_lhs` is `len(args) > 0` (it matches anything). See KB §11.
- **Verification extensions** — incremental 231-gate checksums, proof-carrying code, differential verification, property-based testing — **the labels are aspirational**: PCC embeds a self-declared boolean (and its WAT does not assemble). **Real additions here:** `examples/attest.py` binds a compiled artifact to a checkable `content_sha256`, the SMT layer (`svl/smt_theorem.py`) discharges real `assert`s in Z3, `svl/serialization.py` round-trips the binary AST format, and `svl/hebrew_alias.py` pins the Hebrew alias contract — see below.
- **SMT theorem layer that actually proves things** — `svl/smt_theorem.py` builds a z3 model of a program's straight-line arithmetic and discharges every `assert` by refuting its negation: `unsat` → proven, `sat` → a concrete counterexample. Measured: `assert a + 1 > a` is **proven for all `a`**; `assert a > 0` is refuted with the counterexample `a = 0`. It reports a tri-state — `proven`, `counterexample`, `unverified` (loops, `/`/`%`, arrays: modelled with the wrong semantics would be a false proof, so they are declined), and `vacuous` (no assertions). It is **opt-in**, not on the compile path: far more expensive than the interval interpreter, and answering a different question (all inputs vs. provable index bounds).
- **A canonical program fingerprint that is harnessed** — `svl.serialization.to_canonical_binary` omits the AST's
  source-position fields, so the fingerprint is a function of the *program*: ASCII and Hebrew spellings of the
  same keywords, reformatting, blank lines and comments all give the **same** `ast_sha256` and 231-gate triple
  (the old `to_binary` gave five different values for those five sources). It is the build-cache key
  (`svl.distributed_build`), the package identity recorded by the registry, and the payload of the
  `svl.attest` custom section that `svl.attest.compile_attested` embeds in a shipped artifact. The raw
  `compile_file_to_wasm` stays byte-identical (`attest=False` by default) so artifacts already pinned
  elsewhere remain valid. The same artifact carries a self-framing **sync word** (the 231-gate triple of
  its leading 512-byte block); `svl.attest.locate_sync` finds it inside a larger or shifted stream in
  O(n) — a 128 KB scan is ~20 ms — though the candidate list is not unique because the PRODUCT channel is
  degenerate (see the KB).
- **Abstract interpretation that runs** — `svl/abstract_interpretation.py` performs a sound interval
  analysis over the AST (i32-aware: intervals that leave `[-2**31, 2**31-1]` widen to `top` because WASM
  wraps; array lengths tracked per lvalue path; loop fixpoints with widening; a bounded interprocedural
  pass that binds parameters to the join of their call-site arguments). The compile-time gate refuses a
  program it can **prove** contains an out-of-bounds `a[i]` or a division by a provably zero divisor —
  turning two runtime traps into compile errors. It says nothing when it cannot decide: measured
  **0 findings across all 42 compilable programs** in `examples/` + the workspace corpus, and both
  defect classes caught on demand. Not done: call return values are `top` (no interprocedural value
  summary), so `let n = f(x)` loses precision.
- **The Mod-5 buckets form a real lattice** — `B0 < B1 < B2 < B3 < B4` with join = max and meet = min,
  and `z2_negate` is an order-reversing involution (a duality, **not** a complement:
  `bucket_join(B1,B3) == B3 != B4`). `verify_mod5_lattice()` checks 12 laws exhaustively over all 125
  triples. Dual-stream agreement is now compared **per statement**; it used to be
  `all_semantic == all_structural`, which is True whenever both streams fail everything. Codegen is
  still unaffected: `compiler_wasm.py` never imports the type layer — the type layer reaches
  compilation only through the compile-time gate.
- **The binary deserializer is real** — `svl/serialization.py` round-trips `to_binary` → `from_binary`
  → `to_binary` exactly. The wire format is **not self-describing** (an int in 1..5, a bool and a
  string of length 1..5 all begin with the same byte), so the reader is driven by the declared field
  types and **raises rather than guessing**. Verified: all 42 compilable corpus programs round-trip
  exactly, all 42 `NODE_TAGS` node types individually, and every `Literal`/`Pattern`/`TypeExpr`
  discriminator path. `test_roundtrip()` now asserts structural equality **and** byte-stability.
  Known gap: `CastExpr` is not in `NODE_TAGS`, so the *serializer* rejects it — it has never been
  serialisable.
- **Compiler optimizations** — ~~SIMD, tail-call optimization, escape analysis, WASM GC, PGO, LTO, hot reload~~ **six of the seven are standalone libraries the compiler never calls** (`grep` for `pgo`/`lto`/`tco`/`escape_analysis`/`hot_reload` in `svl/compiler_wasm.py` returns nothing). The one that *is* wired — SIMD — currently breaks the program shape it targets (`for i in 0..4 { s = s + a[i] * b[i] }` fails to assemble).
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
7. **AST round-trip** — `python3 -c "from svl.serialization import test_roundtrip; test_roundtrip()"`.
   Asserts structural equality **and** byte-stable re-serialisation. A stub deserializer once made
   the old size-only check pass while `from_binary(to_binary(ast))` returned a dict.
8. **The Mod-5 lattice** — `python3 -c "from svl.mod5_types import verify_mod5_lattice; print(all(verify_mod5_lattice().values()))"`
   must print `True` (12 laws, exhaustively over all 125 triples).
9. **The Hebrew alias contract** — `svl.hebrew_alias.verify_mapping()` is 22/22 and
   `verify_alias(source)` requires byte-identical WAT for a program and its Hebrew spelling.
10. **Corpus expectation** — 52 files, **42 compilable**, **0** abstract-interpreter findings,
    **42/42** round-trip exact. The 10 non-compiling files are pre-existing legacy fixtures
    (3 never parsed; 7 fail identically with `strict=False`).
11. **Determinism** — WAT sha256 identical across `PYTHONHASHSEED` 0/1/12345/random, and the
    canonical AST fingerprint is identical for ASCII, Hebrew, re-indented and commented variants.

## License

MIT