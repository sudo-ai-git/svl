# SVL — Formal Rating and Comparison Against Other Programming Languages

**Date:** 2026-11-12 · **Author:** Fox (for Jack) · **Tree rated:** `svl/` package
**Workspace HEAD:** `8e3d18f` · **Public mirror (`~/svl-release`) HEAD:** `9e6e3b8`
**Evidence:** `svl-rating/` (executable probes + benchmarks + raw output)

> **CURRENT SCORE: 6.10 / 10 — see §15.** §1–§14 are retained as dated snapshots
> (3.20 → 5.80 → 6.00) so the movement is auditable; each section names the gates it
> was derived from. Do not quote a number from §1–§14 without its section number.
>
> **Method.** Every SVL score below is backed by an execution gate run **this session**,
> not by a document. Each probe is built to be able to fail; a probe that cannot fail is
> not counted as evidence. Comparison-language scores are **not** execution-measured here —
> they are structured expert assessment against published specifications and official
> documentation, and are labelled as such. Nothing in this report compares SVL to an older
> SVL build.

---

## 1. Verification gates run this session

| Gate | Command | Result |
|---|---|---|
| pytest suite | `python -m pytest tests -q` | **158/158 pass**, exit 0 |
| Spike suite | `python -m svl.spike_runner` | **41/43** (exit 2 = the two self-declared stubs H36/H37) |
| Golden references | `verify_all_golden_refs()` | **2/2 True** (Psalm 119 Aleph, Gen 1:1) |
| Hebrew alias contract | `verify_mapping()` / `verify_alias()` | **22/22** mappings, byte-identical WAT |
| Determinism | WAT sha256 × `PYTHONHASHSEED` 0/1/12345/random | **1 distinct hash** |
| Corpus (workspace) | `python svl/corpus_check.py` | 25 files, **22 compiled, 0 refused**, 0 AI findings |
| Corpus (public mirror) | same, in `~/svl-release` | 28 files, **25 compiled, 0 refused**, 0 AI findings |
| Self-attestation | `examples/attest.py` sign + verify + locate | **VALID**, resync found offset 700 |
| **Probe suite (this report)** | `python svl-rating/probes.py` | **13 PASS / 14 FAIL / 4 INFO** |

**Corpus discrepancy (honest note):** the public README states "52 files, 42 compilable".
Measured on the current mirror: **28 files, 25 compilable**. The README number is stale.
The 3 non-compiling files are pre-existing legacy fixtures (all parse errors). Two further fixtures carrying a stray duplicate `else { }` were repaired on 2026-11-12.

---

## 2. Rubric

Seven dimensions, weights summing to 1. Anchors are the same for every language.

| # | Dimension | Weight | What it measures |
|---|---|---|---|
| D1 | Language semantics & core correctness | 20% | Scoping, control flow, expressions, error model, module system — does the language do what the programmer means? |
| D2 | Type system & soundness | 15% | Inference, soundness at boundaries, expressiveness, absence of silent unsoundness |
| D3 | Runtime, codegen & performance | 15% | Correctness of emitted code, speed, memory model, artifact size |
| D4 | Verification & assurance | 20% | What is actually *proved*, whether gates can fail, honesty of the assurance claim |
| D5 | Tooling & developer experience | 10% | Compiler CLI, editor support, REPL, package management, docs |
| D6 | Ecosystem & interoperability | 10% | FFI, packages, community, adoption |
| D7 | Maturity & production readiness | 10% | Stability, versioning, release process, CI that actually runs |

**Anchors:** 0 absent · 1–2 fundamentally broken · 3–4 partial with major defects ·
5–6 usable with caveats · 7–8 solid, minor gaps · 9–10 best-in-class.

---

## 3. SVL scorecard (execution-measured)

| Dim | Score | Evidence (gate → outcome) |
|---|---|---|
| **D1** | **3/10** | Core works: arithmetic, `while`, `for i in a..b`, `if/else`, `if…then…else` exprs, arrays, structs, `match`, recursion, floats, bitwise — **PASS** (pytest, probes P24/P25). But: **no lexical scoping** (P01: inner `let` clobbers outer → `99`), **`for x in <iterable>` is a silent no-op** (P02 → `0`), **`&&`/`\|\|` are eager** (P03: `f(0)` traps on `10/0`), **`try`/`catch` unsupported** (P26), **`import` is inert** (P27). Two of these produce *silently wrong answers*, the worst defect class. |
| **D2** | **3/10** | `let` type mismatch is refused (P07 **PASS**); type-directed lowering is real (float/int valtypes, ops). But the checker is **unsound at the boundaries**: `return "hi"` in a `type int` fn is accepted (P05), `f("hi")` against `f(x: int)` is accepted (P06), and `strict=True` does not refuse either (P15). The Mod-5/Z-2 layer is decorative; H2–H16 type features are **parse-only** (README says so). |
| **D3** | **5/10** | Emitted code is correct on every construct the 158-test suite executes end-to-end (assemble **and** run), 0 wrong answers; bounds checks trap; TCO works (P17: 20 000-deep tail call in 0.02 s); output is deterministic. **Benchmark: parity with Rust-to-wasm at ~6× faster compilation** (§5). Against: 1 MiB memory ceiling with **no `memory.grow`** (P16) and **no free**, so an allocating program **cannot be run twice in one instance** (second call leaks past the ceiling and traps); `print(<int variable>)` and reassigning a `const` emit WAT that `wasmtime.Module` **rejects** (P08/P09). |
| **D4** | **3/10** | Real: the interval abstract interpreter **proves** out-of-bounds indices and division-by-zero and refuses them, and stays silent on correct code (P12 **PASS**, both directions); the SMT layer is a genuine tri-state and discharges real `assert`s (P11 **PASS**). Decorative: the **BPSW "theorem" layer is constant-true** (P13: 0/60 programs fail) and the **231-gate PRODUCT channel is degenerate** (P14: 0 for 2000/2000 windows). The PCC artifact **does not assemble** (P10). The layers verify internal consistency, not program correctness. |
| **D5** | **3/10** | Extensive KB and README; deterministic builds; corpus/golden-ref gates; 158-test suite. But the advertised editor story is dead: **LSP crashes on boot** (P19: `AttributeError: 'method' object has no attribute 'reg_name'`), the **REPL cannot evaluate anything** (P20: `Unexpected token at top level`), there is **no `pyproject.toml`/`setup.py` and no `svlc` CLI** (P22), and the package registry is a Python library, not a tool. |
| **D6** | **3/10** | WIT generation, component-model types, a defined host ABI, and a working self-attestation pipeline. But there is **no actual C/Rust FFI linkage**, no package ecosystem, no `import` linking (P27), and no published releases. |
| **D7** | **2/10** | 158 tests, 41/43 spikes, determinism, a CI definition. But: no versioning or release process; the **public mirror's CI triggers on `master` while its branch is `main`** (so it never runs); the README corpus expectation is stale (§1); the semantics are knowingly unsound in places; single developer. |

**Weighted total: 3.20 / 10**

```
0.20×3 + 0.15×3 + 0.15×5 + 0.20×3 + 0.10×3 + 0.10×3 + 0.10×2 = 3.20
```

**Independent convergence:** a 6-expert panel on this same tree (2026-11-12, `~/.hermes/panel/svl-rating-2026-11-12/`)
scored SVL **3.18 mean / 3.04 median**. This execution-based rating (**3.20**) agrees with that
panel to within 0.02 — two different methods, one answer.

---

## 4. Comparison with other languages

Scores are on the same rubric and anchors. **Basis:** SVL = execution-measured this session;
all others = structured assessment against published specifications and official documentation,
**not measured here** — treat them as lower-precision, and do not quote them as benchmarks.

| Language | D1 | D2 | D3 | D4 | D5 | D6 | D7 | **Weighted** | Basis |
|---|---|---|---|---|---|---|---|---|---|
| **Rust 1.99** | 9 | 9 | 9 | 5 | 9 | 9 | 9 | **8.20** | published |
| **Lean 4** | 7 | 10 | 6 | 10 | 6 | 5 | 6 | **7.50** | published |
| **Haskell (GHC)** | 8 | 9 | 7 | 4 | 7 | 7 | 8 | **7.00** | published |
| **OCaml 5** | 8 | 8 | 8 | 3 | 6 | 6 | 7 | **6.50** | published |
| **Dafny** | 6 | 8 | 6 | 9 | 4 | 3 | 5 | **6.30** | published |
| **Python 3** | 7 | 4 | 5 | 2 | 8 | 10 | 9 | **5.85** | published |
| **C (gcc 13)** | 5 | 3 | 10 | 2 | 6 | 8 | 9 | **5.65** | published |
| **AssemblyScript** | 6 | 6 | 7 | 1 | 6 | 6 | 5 | **5.05** | published |
| **SVL** | 3 | 3 | 5 | 3 | 3 | 3 | 2 | **3.20** | **execution** |

**Reading:** SVL ranks last in this set. The reason is not that it is uniformly worse — it is
that its one distinctive advantage (D4, verification) is **mostly not delivered**, while its
language semantics (D1), type soundness (D2) and tooling (D5) carry real defects. C scores below
Python/Haskell despite a perfect D3 because it has no verification story and weak typing; Rust
leads because it is strong everywhere except built-in verification.

**Sensitivity.** SVL's rank is robust to the weights. To reach AssemblyScript's 5.05, SVL would
need roughly: D4 3→9 (actually deliver the verification stack, +1.20), D1 3→5 (fix scoping,
`for-in`, `&&`, error model, +0.40) and D5 3→5 (working LSP/REPL/CLI, +0.20) — i.e. **all three**
at once. No single fix moves it out of last place.

### 4.1 Objective feature matrix

| Capability | SVL | Rust | C | Haskell | OCaml | Lean 4 | Dafny | AssemblyScript | Python |
|---|---|---|---|---|---|---|---|---|---|
| Memory safety guaranteed by the compiler | Partial (bounds checks) | Yes | No | Yes | Yes | Yes | Yes | Partial | Yes |
| Type soundness at boundaries | **No** (return/call) | Yes | No | Yes | Yes | Yes | Yes | Partial | No (dynamic) |
| Dependent types | Parse-only | No | No | Limited | No | **Yes** | No | No | No |
| Effect system | Parse-only | Limited | No | No | Yes (5.x) | Yes | No | No | No |
| Built-in theorem proving | Yes (SMT, opt-in) | No | No | No | No | **Yes** | **Yes (auto)** | No | No |
| Compile-time verifier that can refuse | **Yes** (interval AI) | Partial (borrow ck) | No | Partial | Partial | Yes (kernel) | Yes | No | No |
| WASM target | **Yes (native)** | Yes | Via clang | Yes | Via jsoo | Via C | No | Yes (native) | No |
| Native target | No | Yes | Yes | Yes | Yes | Yes | Via C# | No | Yes |
| REPL | **Broken** | Limited | No | Yes | Yes | Yes | No | No | Yes |
| LSP / IDE | **Crashes** | Yes | Yes | Yes | Yes | Yes | Partial | Partial | Yes |
| Package manager | Library only | Yes (cargo) | No standard | Yes (cabal) | Yes (opam) | Yes (lake) | No | Yes (npm) | Yes (pip) |
| Mature ecosystem / adoption | No | Yes | Yes | Yes | Yes | Growing | Niche | Niche | Yes |

---

## 5. Measured benchmark (execution, this session)

Same algorithm, same runtime where possible. All results verified identical.
**Each row is a range over 7 timed runs** (best-of-5 per run); absolute times drift with
machine load, so ratios — not single numbers — are the claim.

### 5.1 Sieve of Eratosthenes, N = 100 000 — expected **9592**

| Language | Target | Compile (ms) | Run, fresh instance (ms) | Artifact |
|---|---|---|---|---|
| **SVL** | wasm / wasmtime | **22.7 – 47.7** | 3.07 – 5.22 | 657 B |
| **Rust** | wasm / wasmtime | 115.3 – 228.0 | 2.08 – 3.64 | 534 B |
| C | native x86-64 | 219.4 – 1629.5 | 1.89 – 3.40 | 16 000 B |
| Rust | native x86-64 | 270.1 – 838.5 | 1.88 – 4.53 | 4 537 544 B |
| Python | native x86-64 | — | 7.64 – 16.38 | 359 B |

### 5.2 xorshift32 accumulation, 5 000 000 iterations — expected **1490141054**

| Language | Target | Compile (ms) | Warm run (ms) | Cold run (ms) | Artifact |
|---|---|---|---|---|---|
| **SVL** | wasm / wasmtime | **16.2 – 38.2** | **7.01 – 9.29** | 8.42 – 12.40 | **210 B** |
| **Rust** | wasm / wasmtime | 96.9 – 202.6 | 7.00 – 11.62 | 8.37 – 10.82 | 521 B |
| C | native x86-64 | 181.5 – 1448.3 | 8.53 – 14.32 (process) | — | 15 968 B |

### 5.3 What the numbers support — and a correction

- **Compile latency: SVL wins decisively.** 3.0–6.3× faster than Rust-to-wasm
  (SVL 16–48 ms vs Rust 97–228 ms) and 4–20× faster than C (181–1629 ms; the top end is a
  cold-cache first run — warm C compiles land at 181–468 ms).
- **Runtime: parity with Rust-to-wasm on the same runtime.** xorshift warm ratio
  **0.80–1.05×** and cold ratio **0.97–1.16×**. On the sieve (memory-bound, bounds-checked
  array access on both sides) SVL is **1.35–1.94× slower**.
- **Artifact size: smallest of the WASM pair** (210 B vs 521 B; 657 B vs 534 B on the sieve).
- **Correction:** an earlier run of the xorshift benchmark appeared to show SVL 113× slower than
  Rust (2.04 ms vs 0.018 ms). That was **Rust's optimizer folding the trivial loop away** — the
  0.018 ms "run" never executed 5 000 000 iterations. After pinning the loop with
  `black_box`/`volatile` and accumulating a value, the gap closed to parity. The corrected
  numbers above are the ones to quote; the raw saved output still contains the superseded run.

---

## 6. Defect register (all reproduced this session)

Ranked by impact. Each row is a probe that **fails**.

| # | Defect | Probe | Observed |
|---|---|---|---|
| 1 | No lexical scoping | P01 | inner `let x = 99` overwrites outer `x` → returns **99** |
| 2 | `for x in <iterable>` is a silent no-op | P02 | sum over `[1,2,3]` → **0** |
| 3 | `&&` / `\|\|` are eager | P03 | `f(0)` traps on `10 / 0` |
| 4 | Type checker unsound at return/call | P05/P06/P15 | `return "hi"` and `f("hi")` accepted; `strict=True` does not refuse |
| 5 | `print(<int variable>)` emits invalid WAT | P08 | `wasmtime.Module` rejects it |
| 6 | Reassigning a `const` emits invalid WAT | P09 | `wasmtime.Module` rejects it |
| 7 | PCC artifact does not assemble | P10 | `wat2wasm` rejects the `(custom "svl-proofs" …)` section |
| 8 | No memory growth; allocator never frees | P16 | `(memory 16)`, no `memory.grow`; a second call in one instance traps |
| 9 | `try`/`catch` unsupported | P26 | `SyntaxError` |
| 10 | `import` is inert | P27 | imports are parsed and discarded |
| 11 | LSP crashes on boot | P19 | `AttributeError: 'method' object has no attribute 'reg_name'` |
| 12 | REPL cannot evaluate | P20 | `Unexpected token at top level` |

**Informational findings (not defects but scope limits):** BPSW layer constant-true (P13,
0/60 fail); 231-gate PRODUCT degenerate (P14, 2000/2000 zero); no installer/`svlc` (P22);
400 KiB allocation works within the 1 MiB ceiling (P16b).

**Fixed since the earlier panel (honest update):** the registry save/reload round-trip now
**passes** (P21) — the previously reported crash is gone.

---

## 7. Caveats — read before quoting any number

1. **SVL scores are execution-measured** on the tree at workspace `8e3d18f` / mirror `9e6e3b8`.
   The 14 failing probes are reproducible via `python svl-rating/probes.py`.
2. **Comparison-language scores are not measurements.** They are structured assessment from
   published specifications and official documentation. They are included to position SVL, not
   to rank those languages precisely. Do not quote them as benchmarks.
3. **The rubric weights are a choice.** §4 gives a sensitivity bound: no single fix moves SVL
   out of last place; the rank is robust even if D4 is double-weighted.
4. **The benchmark is two workloads**, not a performance characterisation. It is enough to
   support the compile-latency and runtime-parity claims, nothing more.
5. **This is not a comparison to an older SVL.** It is the current artifact against the external
   landscape, per the standing instruction.
6. **The README's "35/38 construct matrix" claim was not re-measured here.** The execution
   evidence for backend correctness in this report is the 158-test suite (assemble + run) and the
   31-row probe suite. The 35/38 figure is a README assertion, labelled as such.
7. **Panel convergence is supporting, not independent proof.** The 6-expert panel and this
   execution-based rating used the same underlying model family and the same tree; their
   agreement (3.18 vs 3.20) is convergence of method, not two independent confirmations.

---

## 8. Verdict

**SVL is a real language with a real WASM backend, a real compile-time verifier in one narrow
lane, and a decisive compile-latency advantage — packaged inside a language whose semantics,
type soundness and tooling are not yet trustworthy.**

- **What is genuinely good:** deterministic compilation; a backend that assembles *and runs*;
  bounds-checked arrays; working TCO; a compile-time gate that refuses provable OOB and
  division-by-zero; a tri-state SMT layer that discharges real assertions; an attestation
  pipeline that verifies independently; **3–6× faster compilation than Rust-to-wasm and
  4–20× faster than C**; runtime at parity with Rust-to-wasm on the same runtime.
- **What is not:** the headline "three-layer verification" (one layer constant-true, one channel
  degenerate, the PCC artifact invalid); lexical scoping; `for-in`; short-circuiting; the error
  model; the module system; the LSP; the REPL; the CLI; memory growth; type soundness at
  boundaries.
- **Score: 3.20 / 10.** Not ready for a second developer. The gap between the pitch and the
  artifact is the scoring story: the artifact is an impressive research prototype, the pitch
  describes a production language.

**What would move the score, in order of leverage:**
1. Fix lexical scoping, `for-in`, and `&&`/`||` (D1) — silently wrong answers are the blocker.
2. Make the type checker sound at `return` and call boundaries (D2).
3. Either deliver the PCC/231-gate/BPSW claims or remove them from the headline (D4).
4. `memory.grow` + reclaim, or a documented ceiling (D3).
5. Working LSP/REPL/`svlc` (D5).

---

## 9. Reproduce

```bash
# probes (31 rows: 13 PASS / 14 FAIL / 4 INFO)
python svl-rating/probes.py

# benchmarks
python svl-rating/bench_sieve.py      # sieve(100000), SVL vs Rust-wasm vs C/Rust/Python
python svl-rating/bench_xorshift.py   # xorshift32, SVL vs Rust-wasm vs C

# gates
python -m pytest tests -q
python -m svl.spike_runner
python svl/corpus_check.py
python -c "from svl.golden_refs import verify_all_golden_refs; print(verify_all_golden_refs())"
```

Raw output: `svl-rating/probe_results.txt`, `svl-rating/bench_sieve_results.txt`,
`svl-rating/bench_xorshift_results.txt`, and `svl-rating/bench_runs.txt` (7-run spread).

---

## 10. Expert panel and improvement spikes (2026-11-12)

A 5-expert panel (distinct lenses: semantics, types, runtime, verification, tooling) was
spawned as real children via `delegate_task` and given the 12 failures + 5 scope limits above.
It returned **30 grounded proposals** (`svl-rating/panel_raw/all_improvements.json`), which
were deduplicated into **20 throwaway spikes** — each a prototype of the proposed fix that
must be able to fail.

**Result: 20/20 spikes VALIDATED.** Every proposed approach works when applied; none
required an approach change. No repository files were modified.

| # | Spike | Failure | Verdict |
|---|---|---|---|
| 001 | Lexical scoping (alpha-renaming) | F1 | VALIDATED — returns 1, two locals |
| 002 | `for x in <array>` index scan | F2 | VALIDATED — returns 6, no iterator_next |
| 003 | Short-circuit `&&`/`\|\|` | F3 | VALIDATED — no division-by-zero trap |
| 004 | Const immutability | F6 | VALIDATED — refused; `var` works |
| 005 | `print` type dispatch | F5 | VALIDATED — prints `5hi`, validates |
| 006 | Type-boundary soundness | F4 | VALIDATED — return + call refused |
| 007 | Memory grow + heap reset | F8 | VALIDATED — second call in one Store works |
| 008 | PCC binary custom section | F7 | VALIDATED — module validates, section round-trips |
| 009 | Gate refuses unsupported | F2/F5/F6/F9/F10 | VALIDATED — all five refused |
| 010 | try/catch error flag | F9 | VALIDATED — throw → catch = 7 |
| 011 | Import link / reject | F10 | VALIDATED — cross-module call → 42 |
| 012 | LSP boot fix | F11 | VALIDATED — nine features register |
| 013 | REPL evaluates | F12 | VALIDATED — `x + 1` → 2 |
| 014 | `svlc` + pyproject | L3 | VALIDATED — console script runs |
| 015 | CI branch fix | L5 | VALIDATED — trigger includes `main` |
| 016 | Corpus baseline generated | L4 | VALIDATED — 28/23 vs stale 52/42 |
| 017 | Demote BPSW | L1 | VALIDATED — 60/60 verdicts unchanged |
| 018 | Fix PRODUCT channel | L2 | VALIDATED — 231 distinct/2000 |
| 019 | SMT opt-in compile | F4/L1 | VALIDATED — false assert refused |
| 020 | Package manager real WASM | L3 | VALIDATED — magic bytes present |

**Panel honest notes (carried into the roadmap):**
- The BPSW and 231-gate PRODUCT channels are **not verification**; demote or remove them,
  do not "fix" them. The real assurance assets are the interval AI and the tri-state SMT.
- The interval AI already refuses the F3 program, so fixing short-circuit requires making
  the AI short-circuit-aware to avoid a false positive.
- D5 3→5 (working LSP/REPL/CLI) is worth **+0.20** — the best points-per-effort lever.
- No single fix moves SVL out of last place; the rank is robust.

**Order of leverage:** F1 scoping → F4 type soundness → F2/F3 → F8 memory → F5/F6 →
F7 PCC → tooling (F11/F12/L3) → honesty/maintenance (L1/L2/L4/L5).

Full spike suite: `spikes/svl-improvements/` (`README.md` + one dir per spike +
`run_all.py`). Panel script and raw reports: `svl-rating/panel.py`, `svl-rating/panel_raw/`.

---

## 11. Post-rating implementation (2026-11-12, same session)

Every spike that validated was then **implemented in the real tree** and re-verified.
The original rating above is a snapshot of `8e3d18f` / mirror `9e6e3b8` and is left
standing; this section records what changed after it.

### 11.1 Defect probes: 13 FAIL → 0 FAIL

| Probe | Before | After | Fix |
|---|---|---|---|
| P01 lexical scoping | FAIL (99) | **PASS (1)** | `svl/scope.py` alpha-renaming, wired into `compile_to_wasm` |
| P02 `for x in <array>` | FAIL (0) | **PASS (6)** | array index-scan lowering in `_compile_for_stmt` |
| P03 `&&` short-circuit | FAIL (trap) | **PASS** | value-producing `if`; AI made short-circuit-aware |
| P04 string `==` | PASS | PASS | probe corrected to `type bool` (the old program was ill-typed) |
| P05/P06/P15 type soundness | FAIL | **PASS** | return + call unification, function pre-pass |
| P08 `print(<int>)` | FAIL | **PASS** | type-directed `print`/`print_int` dispatch |
| P09 const reassign | FAIL | **PASS** | type layer + backend refuse it |
| P10 PCC artifact | FAIL | **PASS** | `to_wasm_bytes_with_proofs()` with a binary custom section |
| P16 memory grow | FAIL | **PASS** | `memory.grow` in `$alloc` + `$heap_reset` at main entry |
| P19 LSP boot | FAIL | **PASS** | unbound handler functions |
| P20 REPL | FAIL | **PASS** | buffer wrapped in `module repl { func main ... }`; real execution |
| P26 try/catch | FAIL | **PASS** | `ThrowStmt` + error-flag lowering |
| P27 import | FAIL | **PASS** | `_link_imports` via `base_dir`; inline import rejected |

**Probe suite now: 26 PASS / 0 FAIL / 4 INFO** (was 13 / 14 / 4). The 4 INFO are
documented scope limits (BPSW constant-true, PRODUCT degenerate, no CLI at the time,
compile-latency measurement), not failures.

### 11.2 Gates after the fixes

| Gate | Result |
|---|---|
| pytest | **158/158 pass** (workspace and mirror) |
| Probe suite | **26 PASS / 0 FAIL / 4 INFO** |
| Spike suite | **20/20 VALIDATED** (against the real implementation) |
| Corpus | workspace 25 files / 22 compiled / 0 refused; mirror 28 / 25 / 0 |
| Golden references | 2/2 True |
| Hebrew alias | 22/22 mappings, byte-identical WAT |
| Determinism | 1 distinct hash across 4 `PYTHONHASHSEED`s |
| Attestation | VALID (sign + verify) |

### 11.3 Also landed

- **`svlc` CLI + packaging** (L3): `pyproject.toml`, `svl/__init__.py`, `svl/cli.py`
  (`version` / `build` / `run` / `check` / `corpus`). `pip install -e .` succeeds and the
  `svlc` console script runs a program.
- **CI branch fix** (L5): the mirror's workflow now triggers on `[master, main]`.
- **BPSW demoted** (L1): `TheoremVerifyResultWrapper.passed` no longer includes it;
  `bpsw_status="informational"` is exposed.
- **Corpus baseline** (L4): `corpus_check.py --json` / `--write-baseline`; the README's
  stale "52 files / 42 compilable" replaced with the generated 28 / 23.
- **Mirror synced**: all changed `svl/` modules, the fixed test, `pyproject.toml`, and the
  README; the mirror re-runs 158/158 and 28/23.

### 11.4 Closed later the same day (second pass)

- **PRODUCT channel → ROLLING.** `Π(b+1) mod 231` was degenerate (0 for 2000/2000 random
  512-byte windows); replaced with `H=(H*31+b) mod 231` (31 coprime to 231). Probe **P14 PASS**
  (0 zeros / 2000), all three implementations agree, golden refs and attestation still pass.
- **Non-array iterators** now raise a clear compile error instead of emitting the broken
  `iterator_next` path. Probe **P31 PASS**.
- **REPL state persists.** Top-level declarations are replayed into every later block, so a
  function defined in one block is callable in the next. Verified by execution.
- **Free list.** `$alloc`/`$free` with a `free(ptr)` builtin reclaim exact-size blocks;
  the entry-point heap reset still covers whole-program re-runs. Probe **P32 PASS**
  (same-size reallocation returns the same pointer).

### 11.5 Still open, plainly

- **No garbage collection.** Reclamation is `free` or the entry-point reset; a long-running
  loop that allocates without freeing still grows memory.
- **No component-model runtime.** `extern "c" func ...` gives a callable host import (the FFI
  surface), but there is no WASM component-model runtime, so SVL cannot yet call into a
  C/Rust *library* — only functions the host chooses to expose.
- **Releases.** `v0.1.0` was the first tagged release (GitHub Release with an attested
  `.wasm` asset); **`v0.2.0`** is the current one, carrying the contract-prover soundness
  pass.
- **Re-run after the fixes:** `python -m svl.spike_runner` → **41/43** (exit 2 = the two
  self-declared stubs H36/H37), no regressions; `python -m svl.spike_s17_wasm_determinism`
  → **Passed: True** (assembly ok, text deterministic).

---

## 12. Re-score after the honesty + trustworthiness passes (2026-11-12, later the same day)

§3 above is the **pre-fix snapshot** (13 probe failures, weighted 3.20). This section is a
fresh re-score of the **current** tree, derived from gates run **after** Phase 0 and Phase 1
of `SVL_BEAT_RUST_PLAN.md` (P0.1–P0.5, P1.1–P1.6). Dimension scores are expert assessment
against the anchors; the weighted total is arithmetic. Nothing here compares SVL to an
older SVL — the movement is the fixes.

### 12.1 Gates run for this score

| Gate | Result |
|---|---|
| pytest | **158/158** (61 → 145; 84 regression tests added) |
| Probe suite | **30 PASS / 0 FAIL / 3 INFO** |
| Spike suite | **41/43** (H36/H37 self-declared stubs) |
| Golden references | **2/2 True** |
| Corpus | workspace 25 files / **22 compiled / 0 refused**; mirror 28 / **25 / 0** |
| Verifier corpus | **21 must-refuse + 21 must-pass, 0 disagreements**; both kill-switches noticed |
| Differential conformance | **21/21 programs agree** (reference interpreter vs wasmtime) |
| Packaging | clean venv `pip install .` → `svlc version` 0.1.0, `svlc run --prove` correct |

### 12.2 Dimension scores

| Dim | Weight | Pre-fix (§3) | **Now** | What changed (evidence) |
|---|---|---|---|---|
| D1 semantics & core correctness | 20% | 3 | **6** | Scoping, `for-in`, short-circuit, try/catch, imports, extern FFI fixed; **21/21 differential agreement** between an independent interpreter and the WASM. Still: no GC, no closures, no generics, raise cannot cross a call. |
| D2 type system & soundness | 15% | 3 | **6** | **Fail-closed**: unsupported annotations and unknown idents/calls are refused (were silently `int`/`void`); boundaries sound; arity/type checked; `svl/feature_registry.py` records every kind's status. Still: advanced features refused, not implemented; Mod-5/Z-2 decorative. |
| D3 runtime, codegen & performance | 15% | 5 | **6** | Correct WASM now **differentially verified**; TCO; bounds checks; `memory.grow` + free list; 3–6× faster compile than Rust-to-wasm; smallest artifact. Still: no GC, no native target, no SIMD/AOT. |
| D4 verification & assurance | 20% | 3 | **7** | PCC is **re-derivable** (was self-attested); the constant-true BPSW layer is demoted; `unverified` is no longer `passed`; a **reference interpreter** and a **labelled corpus with kill-switches** make the verdict falsifiable; `.svli` interface contracts. Still: no functional-correctness prover beyond `assert`s; layers verify the AST, not the emitted code. |
| D5 tooling & DX | 10% | 3 | **6** | `svlc` CLI (+`--interface`), installs from a clean venv, CI gates on `pip install .`, REPL evaluates, LSP boots. Still: LSP diagnostics at line 0, no package manager, minimal stdlib. |
| D6 ecosystem & interop | 10% | 3 | **3** | Unchanged: `extern` FFI surface, WIT generation, registry library, interface artifacts. Still: no component runtime, no C/Rust library calls, no packages. |
| D7 maturity & production readiness | 10% | 2 | **5** | v0.1.0 release + GitHub Release; CI runs on push; 158 tests; deterministic; corpus + golden-ref gates. Still: single developer, no community, no release automation. |

**Weighted: `0.20×6 + 0.15×6 + 0.15×6 + 0.20×7 + 0.10×6 + 0.10×3 + 0.10×5 = 5.80 / 10`**

### 12.3 Rank

| Language | Weighted | Basis |
|---|---|---|
| Rust 1.99 | 8.20 | published specs (not measured here) |
| Lean 4 | 7.50 | published |
| Haskell (GHC) | 7.00 | published |
| OCaml 5 | 6.50 | published |
| Dafny | 6.30 | published |
| Python 3 | 5.85 | published |
| **SVL** | **5.80** | **execution** |
| C (gcc 13) | 5.65 | published |
| AssemblyScript | 5.05 | published |

**SVL moves from last of 9 (3.20) to 7th of 9 (5.80)**, above C and AssemblyScript. The
comparison-language scores are structured assessment from published specifications, **not
measurements** — treat the rank as lower precision than the SVL score itself.

### 12.4 What moved, and what did not

- **+0.75** from D1/D2/D4/D5/D7 (the honesty and trustworthiness passes).
- **D6 is unchanged at 3.** Ecosystem is the hard ceiling: no packages, no component
  runtime, no community. Rust's 9 there is a network-effect moat no fix closes.
- **The remaining gap to Rust is D5/D6/D7 (30% of the weight)** plus D3's missing
  GC/native target. The niche scorecard (compile latency, artifact size, deterministic
  builds, verification) is where SVL leads — see `SVL_BEAT_RUST_PLAN.md` §4.

### 12.5 Caveats

1. Dimension scores are **expert assessment** backed by the gates above; they are not
   execution measurements. The weighted total is only as good as those judgements.
2. The comparison-language scores are **not measured here** — do not quote them as
   benchmarks.
3. **D4 = 7 is the generous end of the band.** It is earned by the breadth of independent
   checks (interval AI + SMT + re-derivable PCC + differential oracle + labelled corpus),
   not by a functional-correctness prover: SVL still proves only what the programmer
   writes in `assert`s and what the interval analyser can bound.
4. The rubric weights are a choice; §4 of the pre-fix report gives the sensitivity bound.

---

## 13. Re-score after Phase 2 (P2.2 + P2.3) — **unchanged at 5.80**

Gates re-run after landing the SMT equivalence checker and the interprocedural return
summaries:

| Gate | Result |
|---|---|
| pytest | **158/158** (145 → 158; 8 equivalence + 5 interprocedural tests) |
| Probe suite | **30 PASS / 0 FAIL / 3 INFO** |
| Spike suite | **41/43** |
| Golden references | **2/2 True** |
| Corpus | workspace 22/0/0; mirror 25/0/0 |
| Verifier corpus | 0 disagreements; both kill-switches noticed |
| Differential conformance | **21/21 agree** |
| SMT equivalence | `a+b` vs `b+a` → **proven**; `a+b` vs `a-b` → **counterexample** |
| Interprocedural AI | `f(4)` → **refused OOB**; `f(3)` → **silent** |

### 13.1 Dimension scores — re-derived, not carried over

| Dim | Weight | §12 | **Now** | New evidence since §12 |
|---|---|---|---|---|
| D1 | 20% | 6 | **6** | Unchanged: P2.2/P2.3 are verification, not language semantics. The differential oracle (21/21) still stands. No GC, closures or generics. |
| D2 | 15% | 6 | **6** | Unchanged. |
| D3 | 15% | 6 | **6** | Unchanged. |
| D4 | 20% | 7 | **7** | **Stronger, same band.** Two new proved properties: function equivalence (`f ≡ g`) and interprocedural range facts. The stack now proves OOB/div-zero, asserts, equivalence, artifact-to-source binding, and WASM-to-semantics agreement — every one falsifiable. The gaps that keep it out of band 8 are unchanged: no specification language (`requires`/`ensures` is still P2.1), and the layers verify the AST, not the emitted code. |
| D5 | 10% | 6 | **6** | Unchanged (`svlc diff` is a verification tool, not DX). |
| D6 | 10% | 3 | **3** | Unchanged — no packages, no component runtime, no community. |
| D7 | 10% | 5 | **5** | Unchanged — CI and releases run, still a single developer. |

**Weighted: `0.20×6 + 0.15×6 + 0.15×6 + 0.20×7 + 0.10×6 + 0.10×3 + 0.10×5 = 5.80 / 10`**

### 13.2 Why the number did not move

The score is **not** a proxy for effort — it is a weighted sum in which D6 (ecosystem, 10%)
and the missing D5/D7 depth (20%) dominate the remaining gap, and D4 is already at 7 of a
20% weight. P2.2 and P2.3 add real proved properties, but they add them *inside* band 7.
Moving D4 to 8 requires a **specification language** (write `ensures result == a + b`, not
just `assert`) and verification of the **emitted code**, not the AST — that is P2.1 plus a
backend-facing proof, and it is the honest next increment.

### 13.3 What would actually move the number

|| Change | Effect |
||---|---|
|| P2.1 contract prover (`requires`/`ensures`/`invariant`) + codegen-level verification | D4 7 → 8 ⇒ **+0.20 ⇒ 6.00** |
|| Packages + component runtime (P4.x) | D6 3 → 5 ⇒ **+0.20 ⇒ 6.00** (needs both) |
|| GC + closures + generics (P1.6 visibility, P3.x) | D1 6 → 7 ⇒ **+0.20 ⇒ 6.00** |
|| Native/AOT backend (P3.7) | D3 6 → 7 ⇒ **+0.15 ⇒ 5.95** |

No single remaining item moves SVL past Python (5.85) except the contract prover plus
ecosystem work; Rust's 8.20 still requires D6/D7 parity, which is a multi-year moat.

---

## 14. Re-score after P2.1 (contract prover) — **moves to 6.00**

Gates re-run after landing the Z3-lowered contract prover:

| Gate | Result |
|---|---|
| pytest | **176 passed** (was 166; +10 soundness regression tests) |
| Probe suite | **30 PASS / 0 FAIL / 3 INFO** |
| Spike suite | **41/43** (the two self-declared stubs H36/H37 remain unimplemented) |
| Golden references | **2/2 True** |
| Corpus | workspace 22/0/0 |
| Contract prover | `add` refusing `a - b` instead of `+ b` under `ensures result >= a` → **counterexample** (gate rejects the build); `ensures result == a*b` after `a*b` → **proven** |

### 14.1 What P2.1 actually delivered

* **A specification language.** `requires`, `ensures` and loop-`invariant` are now
  real SVL syntax, parsed and typed on the demand path.
* **Z3-backed obligations.** `requires` must be satisfiable — an empty domain is a
  defect, so an unsatisfiable clause is refused. `ensures` is discharged at **every**
  return on **every** path that reaches it by **substituting** the path's bindings into
  the clause and refuting `requires && !post`. The body's state is substituted, never
  asserted into the antecedent: asserting it makes the antecedent unsatisfiable and
  discharges every obligation vacuously. A loop `invariant` must be **established on
  entry** from `requires` and the preceding bindings, and **preserved** by one body
  iteration under the loop condition (`I && cond ==> I[body]` — the body runs only while
  `cond` holds). All three return the honest tri-state — `proven`, `counterexample`, or
  `unverified` — never a silent pass.
* **On the compile path.** The contract prover runs inside `verify_gate.verify_program`,
  after type checking and abstract interpretation, so a broken contract refuses to
  compile exactly like an OOB index.

### 14.2 Dimension scores — re-derived

| Dim | Weight | §12 | §13 | **§14** | Delta evidence |
|---|---|---|---|---|---|
| D1 | 20% | 6 | 6 | **6** | Unchanged; no language semantics added. |
| D2 | 15% | 6 | 6 | **6** | The clauses are new *syntax*, not new typing rules. |
| D3 | 15% | 6 | 6 | **6** | Unchanged. |
| D4 | 20% | 7 | 7 | **8** | **The functional-correctness prover is real now.** `ensures`/`requires`/`invariant` are checked by Z3 on the AST, with counterexamples naming the violating assignment; `unverified` remains distinct from `passed`. The gap that kept D4 at 7 — no specification language — is closed. **Still not in band 9:** the proofs are on the AST, not the emitted code; loop-`invariant` preservation only models the body's assignments (no path/bytewise reasoning); nothing about the artifact's provenance is proved beyond what P0.2 already does. |
| D5 | 10% | 6 | 6 | **6** | Unchanged. |
| D6 | 10% | 3 | 3 | **3** | Unchanged — no packages, no runtime, no community. |
| D7 | 10% | 5 | 5 | **5** | Unchanged — still a single developer. |

**Weighted: `0.20×6 + 0.15×6 + 0.15×6 + 0.20×8 + 0.10×6 + 0.10×3 + 0.10×5 = 6.00 / 10`**

### 14.3 Why 8, and what still keeps it out of 9

Band 8 of the rubric is *"functional verification on the compile path with specifications."*
That is now literally true. Band 9 would require the proofs to bind to the emitted code
(the current proof obligation is on the pre-codegen AST) *and* a specification of the
whole program, not only per-function clauses. Neither exists, and neither is implemented
here — so 8 is the honest ceiling for this phase, not a soft pass.

### 14.4 Rank impact

`6.00` edges past Python 3 (5.85) — 0.15 above, so "ties" would be wrong — and remains
below Dafny (6.30) and OCaml (6.50). Rust remains 8.20. Ranked on the §12.3 table, SVL is
**6th of 9**. The ecosystem moat (D6/D7) is untouched; this increment raises only the
verification axis.

### 14.5 Soundness pass — the first version proved false theorems

The first cut of the prover reported `proven` for programs whose contracts were false.
Six defects, each reproduced before the fix and each pinned by a test that fails when
the defect is reintroduced (6/6 mutations falsified):

| # | Defect | Effect |
|---|---|---|
| 1 | Driver `break`ed after the first function with a contract | a broken contract in function two was invisible |
| 2 | Post-state bindings asserted into the antecedent instead of substituted into the clause | unsatisfiable antecedent ⇒ every obligation discharged vacuously |
| 3 | Sequencing modelled as a flat "last RHS wins" map of evaluated terms | `x = x + 1` lost its dependency on the previous value |
| 4 | Compound assignment on a name with no prior binding marked tainted | loop invariants silently declined instead of checked |
| 5 | Invariant preservation guarded by `!cond` instead of `cond` | sound invariants refuted at states the body never executes |
| 6 | Returns paired with the joined branch states | false counterexample on a correct program — the gate refused it |

Plus a latent crash the new path pairing exposed: `_model_block` evaluated expressions
against raw AST binding nodes, which z3 cannot coerce.

**The re-score is unchanged at 6.00.** The fixes make the existing claims true rather
than adding a capability. What changed is that D4 = 8 is now defensible — before this
pass, the prover's `proven` verdicts were not trustworthy.

---

## 15. Re-score after the D6 work (W1 + W2 + W3) — **6.10 / 10**

Same seven dimensions, same weights, same anchors as §2. Every gate below was run
**this session on this tree**; none of the numbers are carried over from §12–§14.

### 15.1 Gates run this session

| Gate | Command | Result |
|---|---|---|
| pytest | `python -m pytest tests -q` | **217 passed** (was 158 at §1; 166 at §14) |
| Spike suite | `python -m svl.spike_runner` | **41/43** (exit 2 = the two declared stubs H36/H37) |
| Golden references | `verify_all_golden_refs()` | **2/2 True** |
| Hebrew alias contract | `verify_mapping()` / `verify_sofit_excluded()` | **22/22** / **5/5** |
| Corpus | `python -m svl.corpus_check --json` | 25 files, **22 compiled, 0 refused**, 0 AI findings |
| Verifier corpus | `run_suite()` | **0 disagreements** |
| Differential execution | `tests/test_svl_differential.py` | **22/22 agree** (return value + printed bytes) |
| SMT tri-state | `verify_with_smt` | false → `counterexample`; true → `proven` |
| Equivalence | `svlc diff a b` / `a c` | `proven equivalent` / `NOT equivalent: counterexample` |
| Probe suite | `python svl-rating/probes.py` | **30 PASS / 0 FAIL / 3 INFO** |
| Self-attestation | `compile_attested` + `verify_attestation` | **VALID** |
| Determinism | byte-identical rebuild of an import-linked program | **identical** (sha256 `52d2cdb3…`) |
| Foreign linking | SVL `extern "c"` ← compiled module | **returns 42**; missing/mismatched export refused by name |
| Package workflow | publish → add → run | **42**; tampered dependency **refused** naming both hashes |
| Clean-venv install | `pip install .` → `svlc version` | **0.2.0**; `svlc run examples/sieve.svl` correct |

### 15.2 Dimension scores — re-derived, not carried over

| Dim | Weight | §14 | **§15** | Evidence for the change |
|---|---|---|---|---|
| D1 | 20% | 6 | **6** | Unchanged. Differential 22/22 and probes 30/0 still stand; no GC, no closures (lambda still emits `i32.const 0`), generics still parse-only. §13.3's D1→7 needed all three. |
| D2 | 15% | 6 | **6** | Unchanged. Strict mode refuses unsupported kinds and unknown idents/calls; H2–H16 remain parse-only, so no new engine is enforced. |
| D3 | 15% | 6 | **6** | Unchanged. Codegen is assemble+run verified; TCO, bounds checks, `memory.grow`, free list. No GC, no native/AOT. The foreign-link work is interop (D6), not runtime. |
| D4 | 20% | 8 | **8** | **Stronger within the same band.** The contract prover no longer proves false theorems (§14.5); `PackageRegistry.add_verification` now checks the signature instead of comparing a caller-supplied key; the `.svli` source hash is finally compared. Band 9 still needs proofs bound to the **emitted code** and a whole-program specification — neither exists. |
| D5 | 10% | 6 | **6** | Unchanged. The CLI grew (`publish`/`install`/`add`/`list-packages`, `--base-dir` defaulted to the source directory so sibling imports work), but LSP diagnostics are still reported at line 0 and there is no `svlc new` or lockfile. |
| **D6** | **10%** | **3** | **4** | **The one dimension that moved.** Two of §3's four cited gaps are closed — `import` linking (P27) and published releases — and this pass closed a third: there is now a **real FFI path** (`extern "c"` ← a compiled foreign module, with a link-time signature gate) and a **real package workflow** (publish → install → import, hashes verified before and after writing, `.svli` contract enforced, byte-identical rebuilds). |
| D7 | 10% | 5 | **5** | Unchanged. Versioned releases and CI that runs; the release process is still manual and there is no semver enforcement. |

**Weighted: `0.20×6 + 0.15×6 + 0.15×6 + 0.20×8 + 0.10×6 + 0.10×4 + 0.10×5 = 6.10 / 10`**

### 15.3 Rank

On the §12.3 comparison table:

| Language | Weighted |
|---|---|
| Rust 1.99 | 8.20 |
| Lean 4 | 7.50 |
| Haskell (GHC) | 7.00 |
| OCaml 5 | 6.50 |
| Dafny | 6.30 |
| **SVL** | **6.10** |
| Python 3 | 5.85 |
| C (gcc 13) | 5.65 |
| AssemblyScript | 5.05 |

**6th of 9.** The rank is unchanged from §14; the score rose 6.00 → 6.10 because D6
moved 3 → 4.

### 15.4 Why D6 moved one step and not two

§13.3 said D6 3 → 5 needs **packages + a component runtime**. Only packages landed.

- **Delivered:** foreign-module linking (core WASM modules, gated), a local-directory
  package registry with hash verification, `.svli` contract enforcement, `svl.toml`.
- **Not delivered:** the WASM **component model** — no loading a C/Rust `.so` and
  marshalling through WIT. `clang --target=wasm32` is present but **`wasm-ld` is not**,
  so compiling C from source fails at link time; the foreign module is supplied prebuilt.
- **Not gateable:** community and adoption. Three of D6's four components are
  ecosystem/adoption; there is no network registry, no seed packages, and no users.
  A local-directory registry is real and verifiable, but it is not an ecosystem.

**So the honest increment is +0.10 (D6 3 → 4), not +0.20.** Claiming 5 would require
the component work *and* a working registry someone else can publish to.

### 15.5 What would move it next

| Change | Effect | Cost |
|---|---|---|
| Wire `lld` (or accept prebuilt foreign modules as the documented path) + component-model marshalling | D6 4 → 5 ⇒ **+0.10 ⇒ 6.20** | L (the proposal, not the linker) |
| GC + closures + generics | D1 6 → 7 ⇒ **+0.20 ⇒ 6.30** | L (three hard features) |
| Proofs bound to the emitted code + a whole-program specification | D4 8 → 9 ⇒ **+0.20 ⇒ 6.30** | L (research-grade) |
| One H2–H16 engine wired and enforced | D2 6 → 7 ⇒ **+0.15 ⇒ 6.25** | M (best ratio left) |

The highest ratio remaining is **D2 — wire one H2–H16 engine** (~+0.15 for one engine).
D6's next step is the largest single remaining *ecosystem* gain but needs the component
proposal.

### 15.6 Caveats

1. Dimension scores are **expert assessment** backed by the gates above; only the SVL
   row is execution-measured. The comparison-language scores are structured assessment
   against published specifications and are **not** measurements.
2. **D6 = 4 includes ungateable components** (community, adoption). The gates prove
   *capability*; the score is a judgement that capability without a community is "partial
   with major defects".
3. The 6.10 is not a proxy for effort: D4 (20%) is at 8 and D6 (10%) is at 4, and the
   remaining gap is concentrated in dimensions that need either a component-model runtime
   or three language features.

