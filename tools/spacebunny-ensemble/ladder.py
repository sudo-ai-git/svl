"""Paper 2607.02436 -- Reasoning effort as the lever.

Their measured contrast: High -> xHigh took first-try perfect runs from 28% to
89% on agentic coding. Also the finding that kills the obvious move -- adding a
testing tool raised cost 42-68% and improved nothing.

This module treats effort as a measured variable, not a setting. `ladder` runs
the same problems across an effort ladder and reports first-try perfect rate,
tokens, and cost-per-correct -- the three numbers that decide whether a rung is
worth climbing.

Deliberate design choice, and it contradicts the paper's headline direction:
the ladder runs LOW -> HIGH and escalates upward, while 2607.02436 escalated
High -> xHigh. Reason: the prompt is free and the endpoint is $0/$0, so the
cheap rung is probed first and expensive effort is spent only on the residual.
If the model turns out to be effort-insensitive, the whole ladder costs one
rung. That is the opposite of assuming more tokens is better, and it is
testable in one run -- which is the point.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from ensembler import Attempt, ProblemResult, solve_cot, solve_pot
import extract
from nous_client import Reply


@dataclass
class RungStats:
    effort: str
    n: int = 0
    correct: int = 0
    first_try: int = 0        # correct on the very first CoT, no escalation
    tokens: int = 0
    calls: int = 0
    sec: float = 0.0
    answered: int = 0
    truncated: int = 0

    # Per-problem correctness, in the order problems were run. Every rung sees
    # the SAME problems in the SAME order, so index-aligned comparison across
    # rungs is a valid paired test -- and far tighter than comparing two
    # independent accuracies, where a +15pp swing is indistinguishable from
    # the same problems being re-graded differently.
    outcomes: list[int] = field(default_factory=list)

    @property
    def acc(self) -> float:
        return self.correct / self.n if self.n else 0.0

    @property
    def first_try_rate(self) -> float:
        return self.first_try / self.n if self.n else 0.0

    @property
    def cost_per_correct(self) -> float:
        """Tokens per correct answer. With $0/$0 pricing, tokens and wall clock
        are the real budget -- this is the number to optimize."""
        return self.tokens / self.correct if self.correct else float("inf")

    def header(self) -> str:
        return (f"{self.effort:>8}  n={self.n:<4} acc={self.acc:6.1%}  "
                f"first-try={self.first_try_rate:6.1%}  "
                f"tok/correct={self.cost_per_correct:9.1f}  "
                f"tok={self.tokens:<8} calls={self.calls:<5} "
                f"sec={self.sec:7.1f}")


@dataclass
class LadderReport:
    rungs: list[RungStats] = field(default_factory=list)
    per_problem: dict[str, str] = field(default_factory=dict)  # qhash -> effort
    errors: list[str] = field(default_factory=list)

    def render(self) -> str:
        if not self.rungs:
            return "(no rungs completed)"
        out = ["", "=" * 96,
               "REASONING-EFFORT LADDER  (paper 2607.02436)",
               "=" * 96,
               f"{'effort':>8}  {'n':<6} {'accuracy':<12} {'first-try':<16} "
               f"{'tok/correct':<13} {'tokens':<10} {'calls':<7} {'sec':<9}"]
        out.append("-" * 96)
        for r in self.rungs:
            out.append(r.header())
        out.append("-" * 96)
        first = self.rungs[0]
        best = max(self.rungs, key=lambda r: r.acc)
        cheapest = min((r for r in self.rungs if r.correct),
                       key=lambda r: r.cost_per_correct, default=None)
        out.append(f"baseline rung : {first.effort}  acc={first.acc:.1%}")
        # Deliberately no "(+X% vs baseline)" on this line. It is an UNPAIRED
        # best-of-N difference chosen after the fact, so it is a selection
        # effect, not an effect: an early n=8 run headlined +15pp here and the
        # rerun reversed the ranking. Compare rungs with a PAIRED test
        # (stats.paired_bootstrap_delta on rung.outcomes); that CI is the
        # verdict and it is deliberately not rendered here as a number.
        out.append(f"best rung by accuracy : {best.effort}  acc={best.acc:.1%}"
                   f"  (selected post hoc -- not a tested effect)")
        if cheapest:
            out.append(f"best tok/correct: {cheapest.effort}  "
                       f"{cheapest.cost_per_correct:.1f} tok/correct")
        gains = [r for r in self.rungs[1:] if r.first_try_rate > first.first_try_rate]
        if gains:
            top = max(gains, key=lambda r: r.first_try_rate)
            # Same rule as the accuracy line above: report the two endpoints,
            # never a post-hoc "+X% lift" as if it were an established effect.
            # At one problem per rung the raw delta is 2.5pp, far below this
            # design's ~18.8pp detectable floor.
            out.append(f"first-try lift (candidate, untested): {top.effort}  "
                       f"{first.first_try_rate:.1%} -> {top.first_try_rate:.1%}"
                       f"  -- needs a paired test to call")
        else:
            out.append("first-try lift: none -- effort did NOT move first-try rate")
        if self.errors:
            out.append(f"errors: {len(self.errors)} (first: {self.errors[0][:90]})")
        out.append("=" * 96)
        return "\n".join(out)


def _probe_efforts(call: Callable[..., Reply], candidates: list[str],
                   key: Optional[str]) -> tuple[list[str], list[str]]:
    """Find which reasoning_effort values the endpoint actually accepts.

    The public model record does not enumerate them, and a rejected value can
    come back as a 400 that looks like a contract error. Probe cheaply, keep
    what works, and warn about what does not rather than crashing the ladder.
    """
    ok: list[str] = []
    bad: list[str] = []
    for e in candidates:
        try:
            r = call(messages=[{"role": "user", "content": "1+1=? one number"}],
                     effort=e, temperature=0.0, max_tokens=64)
            if r.text:
                ok.append(e)
            else:
                bad.append(e)
        except Exception as ex:
            bad.append(f"{e}: {type(ex).__name__} {str(ex)[:70]}")
    return ok, bad


def ladder(problems: list[tuple[str, Optional[float]]], *,
           call: Callable[..., Reply],
           efforts: list[str],
           key: Optional[str] = None,
           probe: bool = True,
           max_tokens: int = 2048,
           verbose: bool = False) -> LadderReport:
    """Run every problem at every effort rung. Ascending order by convention."""
    rep = LadderReport()

    if probe:
        accepted, rejected = _probe_efforts(call, efforts, key)
        if rejected:
            rep.errors.append("effort probe rejected: " + "; ".join(rejected))
        if not accepted:
            # Degrade to a single unspecified-effort rung, but say so loudly.
            # A ladder that silently collapses to one rung reads like a
            # measurement and is not one. (Caught by dryrun.py.)
            rep.errors.append(
                "DEGRADED: no reasoning_effort value was accepted; this run "
                "measures the model at effort UNSPECIFIED, not a ladder. "
                "Treat any single-rung 'result' as a baseline, not as evidence "
                "about the effort dial.")
            accepted = []
        efforts = accepted or [None]  # type: ignore[list-item]
    if efforts and efforts[0] is None:
        efforts = [None]  # type: ignore[list-item]

    for eff in efforts:  # ascending: cheap rung first
        st = RungStats(effort=str(eff))
        for q, gold in problems:
            t0 = time.time()
            try:
                # CoT only for the ladder. Adding PoT here would confound the
                # effort measurement with the ensemble -- the ladder's job is
                # to isolate effort, and 2608.01347's whole point is that
                # prompt/effort/harness are interacting factors.
                a = solve_cot(q, call, effort=eff, temperature=0.0,
                              max_tokens=max_tokens)
            except Exception as ex:
                rep.errors.append(f"[{eff}] {q[:50]}: {type(ex).__name__} {str(ex)[:70]}")
                st.sec += time.time() - t0
                # Placeholder so index alignment across rungs is preserved. A
                # missing slot would shift every later problem by one and
                # silently corrupt the paired comparison.
                st.outcomes.append(0)
                continue

            st.n += 1
            st.tokens += a.tokens
            st.calls += 1
            st.sec += time.time() - t0
            if a.ok:
                st.answered += 1
            if "truncated" in a.detail:
                st.truncated += 1

            agree = extract.answers_agree(a.answer, gold)
            st.outcomes.append(1 if agree is True else 0)
            if agree is True:
                st.correct += 1
                st.first_try += 1          # no escalation happened, by definition
                rep.per_problem[q] = str(eff)
                if verbose:
                    print(f"  [{eff}] ✓ {a.answer}  ({a.tokens}t)")
            elif verbose:
                print(f"  [{eff}] ✗ got={a.answer} want={gold}  ({a.tokens}t)")

        rep.rungs.append(st)
    return rep


def ensemble_sweep(problems: list[tuple[str, Optional[float]]], *,
                   call: Callable[..., Reply],
                   effort: Optional[str],
                   max_tokens: int = 2048,
                   allow_escalation: bool = True,
                   verbose: bool = True) -> tuple[list[ProblemResult], dict]:
    """Run the CoT-PoT ensemble once per problem. Paper 2604.17433 mechanism."""
    from ensembler import solve_problem
    results: list[ProblemResult] = []
    t0 = time.time()
    for q, gold in problems:
        r = solve_problem(q, gold, call=call, effort=effort,
                          escalate_effort=effort,
                          max_tokens=max_tokens,
                          allow_escalation=allow_escalation)
        results.append(r)
        if verbose:
            mark = {True: "✓", False: "✗", None: "?"}[r.correct]
            flag = " [escalated]" if r.escalated else ""
            print(f"  {mark} final={extract.format_answer(r.final):>12} "
                  f"want={extract.format_answer(r.gold):>12} "
                  f"calls={r.calls} tok={r.tokens}{flag}")
            print(r.reasoning_trace())
    n = len(results)
    graded = [r for r in results if r.correct is not None]
    corr = sum(1 for r in graded if r.correct)
    agreed = sum(1 for r in results if r.agreed)
    esc = sum(1 for r in results if r.escalated)
    total_calls = sum(r.calls for r in results)
    total_tok = sum(r.tokens for r in results)
    summary = {
        "n": n,
        "correct": corr,
        "accuracy": corr / n if n else 0.0,
        "agreed_no_escalation": agreed,
        "agreement_rate": agreed / n if n else 0.0,
        "escalated": esc,
        "escalation_rate": esc / n if n else 0.0,
        "calls": total_calls,
        "calls_per_problem": total_calls / n if n else 0.0,
        "tokens": total_tok,
        "tokens_per_problem": total_tok / n if n else 0.0,
        "tokens_per_correct": (total_tok / corr) if corr else float("inf"),
        "wall_sec": time.time() - t0,
    }
    return results, summary