# SVL — Expert Panel & Improvement Spikes

**Date:** 2026-11-12 · **Tree:** workspace `8e3d18f` / mirror `9e6e3b8`
**Input:** the 12 verified failures + 5 scope limits in `SVL_FORMAL_RATING.md`
**Panel:** 5 experts, distinct lenses, spawned as real children via `delegate_task`
(provider `nous`, model `meituan/longcat-2.5:free`; 2 batches of 3+2, read-only)
**Panel script:** `svl-rating/panel.py` · **Raw reports:** `svl-rating/panel_raw/`

---

## 1. Panel composition

| Lens | Focus | Proposals |
|---|---|---|
| Language semantics & compiler correctness | F1 scoping, F2 for-in, F3 short-circuit, F9 error model, F10 modules, F6 const | 6 |
| Type system & soundness | F4 unsound boundaries, F5/F6 invalid WAT | 6 |
| Runtime, codegen & memory | F8 memory, F5/F6 artifacts, F7 PCC | 6 |
| Verification & assurance | L1 BPSW, L2 PRODUCT, F7 PCC, wiring | 6 |
| Tooling, DX & ecosystem | F11 LSP, F12 REPL, L3 CLI, L4 docs, L5 CI | 6 |

**30 proposals, deduplicated into 20 spikes.** Every expert grounded its proposals in
`file:line` and reproduced the failures with short probes before proposing. Every proposal
carries a falsifiable Given/When/Then spike question.

### Panel honest notes (the most valuable output)

- **The verification stack's real assets are the interval AI and the tri-state SMT layer.**
  The BPSW and 231-gate PRODUCT channels are *not verification at all* — no tweak makes them
  prove program correctness; they should be demoted or removed, not "fixed".
- **The interval AI already refuses the F3 program today** (it proves `10/0`), so fixing
  short-circuit will require making the AI's `&&`/`||` handling short-circuit-aware to avoid
  a false positive.
- **F1 (lexical scoping), F3 (short-circuit) and F8 (memory.grow) are the highest-leverage
  D1/D3 items** — they produce silently wrong answers.
- **`for x in <iterable>`, `print(<int>)` and const reassignment are defects, not design
  trade-offs.** The cheapest honest fix is compile-time refusal; a real array-iterator
  lowering is the follow-up.
- **D5 3→5 (working LSP/REPL/CLI) is worth +0.20** — the best lever available to the tooling
  lens. F11/F12 are hard execution-gate failures.
- **The rating's own sensitivity analysis says no single fix moves SVL out of last place.**

---

## 2. Spike verdicts — 20/20 VALIDATED

Every spike is a throwaway prototype of the proposed fix (monkeypatching the real compiler
where possible, or a standalone AST/WAT pass). **No repository files were modified.**

| # | Spike | Failure | Verdict | Evidence |
|---|---|---|---|---|
| 001 | Lexical scoping | F1 | **VALIDATED** | alpha-renaming → two locals `$x__v1/$x__v2`, returns 1 |
| 002 | `for x in <array>` | F2 | **VALIDATED** | index-scan lowering → returns 6, no `iterator_next` |
| 003 | Short-circuit `&&`/`\|\|` | F3 | **VALIDATED** | value-producing `if` → `f(0)` returns 0, no trap |
| 004 | Const immutability | F6 | **VALIDATED** | const assignment refused; `var` still works (6) |
| 005 | `print` type dispatch | F5 | **VALIDATED** | `print(5)` + `print("hi")` → `5hi`, module validates |
| 006 | Type-boundary soundness | F4 | **VALIDATED** | return + call mismatches refused; valid program passes |
| 007 | Memory grow + heap reset | F8 | **VALIDATED** | first=1, second=1 in one Store; `memory.grow` present |
| 008 | PCC binary custom section | F7 | **VALIDATED** | module validates; section round-trips all 3 layers |
| 009 | Gate refuses unsupported | F2/F5/F6/F9/F10 | **VALIDATED** | all five refused, valid program still passes |
| 010 | try/catch error flag | F9 | **VALIDATED** | throw → catch = 7; no-throw → 0 |
| 011 | Import link / reject | F10 | **VALIDATED** | cross-module call → 42 via `a$answer` |
| 012 | LSP boot fix | F11 | **VALIDATED** | all nine features register, no AttributeError |
| 013 | REPL evaluates | F12 | **VALIDATED** | `let x = 1` → 1; `x + 1` → 2 |
| 014 | `svlc` + pyproject | L3 | **VALIDATED** | `pip install --target` + console script runs a program |
| 015 | CI branch fix | L5 | **VALIDATED** | mirror branch `main`; patched trigger `[master, main]` parses |
| 016 | Corpus baseline generated | L4 | **VALIDATED** | measured 28/23 vs README's stale 52/42 |
| 017 | Demote BPSW | L1 | **VALIDATED** | 60/60 verdicts unchanged; `bpsw_status=informational` |
| 018 | Fix PRODUCT channel | L2 | **VALIDATED** | rolling hash: 231 distinct/2000, 5 zeros, flip-sensitive |
| 019 | SMT opt-in compile | F4/L1 | **VALIDATED** | false assert refused; true assert accepted |
| 020 | Package manager real WASM | L3 | **VALIDATED** | `wat2wasm` → magic bytes; registry check would pass |

**Reproduce:** `python spikes/svl-improvements/run_all.py`

---

## 3. What the spikes collectively prove

1. **Every failure has a cheap, working fix.** All 12 defects + 5 scope limits are
   addressable with the proposed approach; none required an approach change.
2. **The fixes compose.** Scope-aware renaming (001) and array `for-in` (002) are
   independent; the gate refusal pass (009) can land before or after the real lowerings.
3. **The verification layers must be demoted, not repaired.** 017 shows dropping BPSW is
   behavior-preserving (60/60); 018 shows the PRODUCT channel can be made non-degenerate
   with a rolling hash.
4. **The tooling story is the cheapest real gain.** 012/013/014 are small, and together they
   move D5 from 3 → 5 (+0.20 weighted).

## 4. Order of leverage (panel consensus, confirmed by spike effort/risk)

1. **F1 lexical scoping** (001) — silently wrong answers; D1 20% weight.
2. **F4 type-boundary soundness** (006, 019) — the gate's headline claim.
3. **F2 for-in + F3 short-circuit** (002, 003) — silently wrong answers.
4. **F8 memory grow** (007) — hard 1 MiB ceiling.
5. **F5/F6 print + const** (004, 005, 009) — invalid artifacts.
6. **F7 PCC** (008) — the certified artifact becomes real.
7. **F11/F12/L3 tooling** (012, 013, 014) — best points-per-effort.
8. **L1/L2/L4/L5** (015–018) — honesty and maintenance.
