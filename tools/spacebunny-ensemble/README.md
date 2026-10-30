# spacebunny-ensemble

Papers **#2** and **#4** from the arXiv shortlist, integrated against
`stealth/space-bunny-alpha` on the Nous Portal API.

| # | Paper | Mechanism implemented here |
|---|-------|----------------------------|
| 4 | **2604.17433** — *Self-Consistency from Only Two Samples* (CoT-PoT) | Two independent solvers (CoT + PoT). Agree → done at 2 calls. Disagree → one third CoT at higher temperature as tie-break. |
| 2 | **2607.02436** — *Reasoning effort, not tool access, buys first-try reliability* | `reasoning_effort` swept as a measured ladder; reports first-try rate and tokens-per-correct per rung. |

Both are inference-time only. No weights, no gradients, no logprobs — the
endpoint does not offer `logprobs`, which is exactly why nothing here depends
on them.

## MEASURED RESULTS — real completions, 2026-10-03

Model: `stealth/space-bunny-alpha` via `inference-api.nousresearch.com`,
CoT prompt, `temperature=0`. Numbers below are from actual API responses.

### GSM8K test, n=10 — saturated, so it proves nothing

| effort | acc | first-try | tok/correct |
|---|---|---|---|
| low | 100.0% | 100.0% | 372.0 |
| medium | 90.0% | 90.0% | 436.3 |
| high | 100.0% | 100.0% | 397.3 |

The model is already perfect at `low`. **Do not read "no effort lift" here as
evidence about the effort dial** — a benchmark with no headroom cannot show a
lift. (The medium dip is one item, n=10, not a signal.)

### Harder in-house set, n=8 — real headroom, still no lift

| effort | acc | first-try | tok/correct |
|---|---|---|---|
| low | 62.5% | 62.5% | 528.6 |
| medium | 62.5% | 62.5% | 562.0 |
| high | 62.5% | 62.5% | 535.0 |

**Paper #2 does not replicate on this model.** 2607.02436 measured High→xHigh
lifting first-try runs 28%→89%. Here `reasoning_effort` is flat across all
three rungs — same 62.5%, and **the same three items fail at every effort**.
The failures are not "not thinking hard enough"; they are stable
misreadings of the problem.

### Ensemble, same hard set, effort=medium — the decisive result

| metric | value |
|---|---|
| accuracy | 62.5% (identical to CoT alone) |
| CoT/PoT agreement | **8/8 = 100%** |
| escalated | 0/8 |
| calls/problem | 2.00 |
| PoT programs executed | 8/8 |

**Paper #4's premise fails here.** CoT and PoT agreed on *every* item,
including all three wrong ones. Executing the program is not an independent
check — the model makes the same interpretive error before it writes any code.
The ensemble cost 2× the tokens and bought **zero** accuracy.

This is precisely the coverage wall 2605.14163 names: selection can't fix a
shared blind spot, and both solvers share one.

## PTTS-ZS (paper #3, arXiv 2609.27374) — the planner works, the executor ignores it

`--planned` runs PTTS-ZS against repeated sampling at **matched executor
budget** (k branches each; the PTTS arm spends one extra call on the planner).
PTTS-RL is not implemented — it trains the planner, and a black-box API gives
no weights.

The interesting result is not the accuracy delta. It is a *separation*:

Run twice, against two baselines. `exec-temp` is the baseline's temperature:

| run | arm | top-1 | pass@k | plan-div | ans-div | calls | tokens |
|---|---|---|---|---|---|---|---|
| temp 0.7 | repeated x4 | 62.5% | 62.5% | – | 0.25 | 32 | 8,838 |
| temp 0.7 | PTTS-ZS x4 | 62.5% | 62.5% | **0.83** | 0.25 | 40 | 25,872 |
| **temp 0.0** | repeated x4 (greedy) | 62.5% | 62.5% | – | 0.25 | 32 | 8,767 |
| **temp 0.0** | PTTS-ZS x4 | 62.5% | 62.5% | **0.99** | 0.26 | 40 | 24,771 |

The greedy run is the important one. A sampling baseline is the *weakest*
control, because temperature already generates diverse branches and gives PTTS
little to prove. Against a baseline that cannot diversify, plan diversity rose
to **0.99** — the planner is doing its job perfectly — and accuracy still did
not move by one problem.

**plan-div 0.99, ans-div 0.26.** The planner wrote four genuinely distinct
methods for the tiling problem — *unit-rescaling*, *area ratio*,
*row-and-column count*, *one-meter block partition* — and all four branches
still returned 12. Planning changed the reasoning path **without changing the
outcome**. Cost: 2.8× the tokens, zero accuracy.

This holds on all 8 problems, and it holds on the wrong ones too: the discount
problem drew *sequential percentage*, *work backward*, *algebraic setup*,
*net-percentage decomposition* and all four landed on 245 instead of 43.

This is why the harness measures plan diversity separately from answer
diversity. An answer-only metric reads 0.25 and reports "the planner emitted
near-duplicates", which blames the planner for the executor's convergence.
Both numbers are printed on every run.

**Self-reported adherence is 1.00 on every branch** — the model claims perfect
compliance with a plan whose differing steps it then collapses into one result.
Self-report is not a usable control for whether a plan was actually followed.

Practical read: on this model, executor-side convergence is the binding
constraint. More branches, planned or not, cannot fix a shared blind spot. The
lever has to be something outside the model — a real calculator, a test
harness, or a verifier that isn't the same weights.

### Two metrics the headline hides

- `fallbacks` — a planner that returns nothing usable falls back to unplanned
  branches and says `FELL BACK` in `error`. Those rows are not a PTTS
  measurement and are excluded from the verdict, never silently averaged.
- `lost` — dead calls. A lost branch shrinks effective k, so pass@k is
  measured over fewer branches than requested and coverage is understated for
  whichever arm lost more. The greedy run lost one branch to `EndpointError`;
  branches now retry twice (exponential backoff) and permanent losses are
  counted and printed.
- `coverage_measurable` — pass@k is only reported as coverage when every
  problem has a gold. Partial grading is called out in the render.

## MATH-500 (levels 4-5), n=40 — real benchmark, paired test

The 8-item set could not distinguish "no effect" from "underpowered". MATH-500
supplies 158 numeric items at levels 4-5;40 were sampled (seed 0, deterministic).

**reasoning_effort ladder, CoT only, temperature 0:**

| effort | solved | accuracy |
|---|---|---|
| low | 36/40 | 90.0% |
| medium | 38/40 | 95.0% |
| high | 37/40 | 92.5% |

Paired (same problems, index-aligned) comparisons:

| comparison | delta | 95% CI | p | verdict |
|---|---|---|---|---|
| low → medium | −5.0pp | [−15.0, +5.0] | 0.312 | not significant |
| low → high | −2.5pp | [−10.0, +5.0] | 0.607 | not significant |
| medium → high | +2.5pp | [−5.0, +10.0] | 0.611 | not significant |

**2607.02436 does not replicate**, now on a real benchmark at 5× the sample
size. The apparent +15pp from the first run was one problem: on a rerun the
ordering changed (medium was no longer best), which is exactly what noise at
this n looks like.

The per-item breakdown is the informative part:

- **34/40 solved by all three rungs**
- **1/40 missed by all three** — irreducible for this model
- **5/40 solved by some rung** — the *only* headroom effort can move

Five problems are individually solvable, and which rung gets them is
**non-monotonic**: medium wins idx 24,25 but *loses* idx 0 and 21 that low got.
There is no ordering of the dial that captures all five, because the rungs are
not nested — higher effort sometimes loses a problem lower effort solved.

At n=40 the minimum detectable effect is **18.8pp**; one problem is 2.5pp. So
this experiment can only detect a lift of ~7 problems. The 5-problem pool of
movable items is *smaller than the noise floor* — no rung comparison at this n
can resolve it. That is the honest limit, and it is why the null is reported
with its power rather than as a bare "no effect".

## Verdict across all three papers

| method | paper | result on this model |
|---|---|---|
| reasoning-effort ladder | 2607.02436 | flat at every rung (n=8: 62.5%; MATH-500 n=40: 90/95/92.5%, all n.s., MDE 18.8pp) |
| CoT+PoT ensemble | 2604.17433 | 8/8 agreement incl. all wrong; zero gain, 2× tokens |
| PTTS-ZS planned branches | 2609.27374 | plan-div 0.99, ans-div 0.26; zero gain, 2.8× tokens |

Three independent test-time-compute methods, three failures, one shared cause:
**the model's answer distribution is too narrow for extra compute to act on.**
Every approach spends more tokens re-rolling the same conclusion.

Concretely, what would be different: the gains all require branches that reach
*different* answers, and nothing available through a chat-only API produces
them. The remaining lever is external to the model — real arithmetic, real
execution, real test cases. Not more sampling.

## Status: mechanism VALIDATED and MEASURED

**Verified by execution:**
- 219/219 offline self-tests (`python3 selftest.py`, exit 0)
- Report paths end-to-end against a fake model (`python3 dryrun.py`, exit 0)
- `npx -y pyright *.py` clean: 0 errors, 0 warnings
- **Real completions obtained** — `run.py --probe` → 200, exit 0
- Credential pool in `~/.hermes/auth.json` has two working Nous credentials
  (`device_code` oauth, `api-key-1`); both return correct answers
- GSM8K + hard set measured across three methods; results in `results.jsonl`

### Auth: where the credentials actually live

`~/.hermes/auth.json` → `credential_pool.nous`, **not** `~/.hermes/.env`.
The `.env` file's `LM_API_KEY` is a *different, dead* credential; preferring it
produced a 401 that looked exactly like a dead account. `resolve_key()` now
reads the Hermes credential pool, prefers the oauth credential (it carries an
`expires_at`), and `chat()` fails over across the pool.

### The 400 that lies

Unauthenticated, `/chat/completions` returns **400 `Unknown model`** for
*every* listed model. That is the no-auth path wearing a misleading message,
not a statement about the model id. A genuinely absent model returns
**404 `not found in our configuration`**. Verified:

| Request | Result |
|---|---|
| `/models`, no auth | 200, 425 models |
| `/chat`, no auth, listed model | 400 "Unknown model" |
| `/chat`, no auth, fake model | 404 "not found" |
| `/chat`, no auth, **no `Content-Type`** | 400 "Model parameter is required" |

Last row matters: omit `Content-Type` and the endpoint silently discards the
body, then reports a missing model. Both 400s are unauthenticated-path noise.

## Static verification

`npx -y pyright *.py` → **0 errors, 0 warnings**. This is part of the gate, not
an afterthought: pyright found two real bugs that 206 passing tests missed,
because every test drove the happy path.

- **`_raw` returned `dict | str` and the 200 branch called `.get()` on it.**
  An HTTPError body is decoded *text*, and a well-formed 200 can still be a
  JSON array. Both would have raised `AttributeError` inside the auth
  diagnostics — i.e. a network blip would crash the one function whose job is
  to explain network blips. Body is now narrowed with `isinstance`, and a
  non-JSON 200 degrades to text instead of raising.
- **`_raw` returned status `None` on transport failure.** Every caller compares
  against int literals, so `None` fell through every branch and surfaced as an
  unclassified mystery status — which reads like an auth or model problem and
  sends you debugging credentials while the DNS is down. Replaced with
  `TRANSPORT_FAILED = -1`, named explicitly in `probe_endpoint`.

## Usage

```bash
python3 run.py --selftest              # offline, no network
python3 run.py --probe                 # liveness + auth; exit 2 if unusable
python3 run.py --ladder --hard -n 8 -v # measure the effort dial (harder set)
python3 run.py --ensemble --hard -n 8 # measure CoT-PoT (harder set)
python3 run.py --planned --hard -n 8 --branches 4 -v   # PTTS-ZS vs repeated
python3 run.py --planned --hard -n 8 --branches 4 --exec-temp 0.0   # vs GREEDY
python3 run.py --both --hard -n 8 -v  # both
python3 run.py -q "What is 17*23?::391" # single inline problem
```

Credentials resolve automatically from the Hermes credential pool, so no
setup is needed. GSM8K loads from the local HF cache (no network). Use
`--hard` for the harder in-house set -- GSM8K is saturated for this model.

Runs append to `results.jsonl`. Every row carries the model id and a `graded`
flag, so an ungraded run can never be mistaken for a measured one.

## What each number means

**Ladder** — CoT only, `temperature=0`, effort the only variable. PoT is
excluded on purpose: 2608.01347's finding is that prompt, effort and harness
interact, so mixing the ensemble into the effort measurement confounds it.
Reports `acc`, `first-try`, `tokens/correct`. The paper's contrast was
High→xHigh (28%→89% first-try); this ladder runs **low→high** and spends
effort only on the residual, because the prompt is free and the endpoint is
$0/$0. If the model turns out to be effort-insensitive the whole ladder costs
one rung.

**Ensemble** — reports the k-reduction claim directly as `calls/problem`
(2.0 when solvers agree, 3.0 on disagreement) plus the mode head-to-head.
That head-to-head is a *premise check*: 2604.17433 only pays off if CoT and PoT
have complementary errors. If one mode dominates, ensembling cannot help much,
and the report says so rather than quietly reporting an ensemble number.

## Design decisions worth knowing

**PoT programs are executed, so they are untrusted code.** `sandbox.py` runs
them under `RLIMIT_AS`/`CPU`/`NOFILE`/`FSIZE`, a wall-clock timeout, its own
process group, a scrubbed environment, an import denylist injected as a source
prelude, and a static preflight screen. This is **not a security boundary** —
it stops runaway loops and casual escape, not a determined adversary. Run it
where that is acceptable.

**The sandbox denylist was derived empirically, not by guessing.** Denying
`os`/`sys`/`importlib` looked strictly safer but broke `fractions` and
`statistics` (the latter imports `random`, which imports `os`). A sweep showed
the shipped 49-module list lets all 32 common stdlib math modules import
cleanly; `selftest.py` guards that with 32 individual assertions so the
over-broad version cannot come back.

**Tie-break is a fresh CoT, not a second PoT.** If the program disagreed with
CoT, re-rolling the same execution strategy mostly reproduces the same bug.
2609.27374 measured the general principle: independent sampling from one policy
produces correlated branches.

**Verdicts I did not overstate.** The effort-lift evidence is contradictory in
the literature — 2607.02436 reports 28%→89%, while preregistered 2608.16956
found *no* accuracy difference for high effort on AIME (CI permitting up to
+4.67pp). Neither number transfers to this model. That is why this repo
measures the dial instead of citing either result.

## Files

| File | Role |
|------|------|
| `run.py` | CLI: probe / ladder / ensemble, arg wiring, result serialisation |
| `nous_client.py` | Portal client; verified endpoint facts in the module docstring |
| `ladder.py` | Effort ladder + ensemble sweep + report rendering |
| `ensembler.py` | CoT and PoT solvers, tie-break policy |
| `sandbox.py` | PoT execution containment |
| `extract.py` | Answer extraction and numeric equivalence |
| `datasets.py` | GSM8K / JSONL / inline problem loading |
| `selftest.py` | 123 offline assertions, no API |
| `dryrun.py` | End-to-end report paths against a fake model |