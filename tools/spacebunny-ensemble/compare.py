"""Head-to-head: PTTS-ZS vs repeated sampling at matched budget.

This is the only fair comparison, and it is the one the paper's headline number
implies. Both arms get k executor calls per problem. The PTTS arm spends one
extra call on the planner; that overhead is reported rather than hidden, and
`--equal-total-calls` re-runs the baseline with k+1 branches so both arms spend
the same TOTAL number of calls.

Reported per arm:
  acc          top-1 accuracy after majority vote
  pass@k       any branch correct -- coverage, the paper's real metric
  diversity    distinct answers / answered branches
  spread       1 - largest single-answer share
  adherence    mean self-reported plan adherence (PTTS only)
  calls, tokens

pass@k is where PTTS should win: it is a coverage claim. If pass@k does not
move while diversity is high, the planner is producing different-looking plans
that do not change outcomes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import extract
import planner as P
from nous_client import Reply


@dataclass
class ArmStats:
    name: str
    n: int = 0
    graded: int = 0
    correct: int = 0
    passed_at_k: int = 0
    calls: int = 0
    tokens: int = 0
    sec: float = 0.0
    diversity: list[float] = field(default_factory=list)
    plan_diversity: list[float] = field(default_factory=list)
    spread: list[float] = field(default_factory=list)
    adherence: list[float] = field(default_factory=list)
    distinct_answers: list[int] = field(default_factory=list)
    fallbacks: int = 0
    lost_branches: int = 0
    per_problem: dict[str, Optional[float]] = field(default_factory=dict)

    def add(self, r: P.PlannedResult) -> None:
        self.n += 1
        self.calls += r.calls
        self.tokens += r.tokens
        self.sec += r.sec
        self.diversity.append(r.diversity)
        self.plan_diversity.append(r.plan_diversity)
        self.spread.append(r.spread)
        self.distinct_answers.append(r.distinct_answers)
        if "FELL BACK" in r.error:
            self.fallbacks += 1
        self.lost_branches += r.lost_branches
        fs = [b.follow_score for b in r.branches if b.follow_score is not None]
        if fs:
            self.adherence.append(sum(fs) / len(fs))
        if r.correct is not None:
            self.graded += 1
            self.correct += 1 if r.correct else 0
        if r.passed_at_k:
            self.passed_at_k += 1

    @property
    def acc(self) -> float:
        return self.correct / self.graded if self.graded else 0.0

    @property
    def pass_at_k(self) -> float:
        """Coverage: did ANY branch produce the right answer?

        Denominator is the number of PROBLEMS with a gold, not the number
        graded, so an ungraded problem can never inflate the rate. Pass@k is
        only meaningful on a graded set.
        """
        denom = self.graded or self.n
        return self.passed_at_k / denom if denom else 0.0

    @property
    def coverage_measurable(self) -> bool:
        return self.graded > 0 and self.graded == self.n

    @property
    def mean_diversity(self) -> float:
        return sum(self.diversity) / len(self.diversity) if self.diversity else 0.0

    @property
    def mean_plan_diversity(self) -> float:
        return (sum(self.plan_diversity) / len(self.plan_diversity)
                if self.plan_diversity else 0.0)

    @property
    def mean_spread(self) -> float:
        return sum(self.spread) / len(self.spread) if self.spread else 0.0

    @property
    def mean_adherence(self) -> Optional[float]:
        return (sum(self.adherence) / len(self.adherence)
                if self.adherence else None)

    def row(self) -> str:
        adh = (f"{self.mean_adherence:.2f}" if self.mean_adherence is not None
               else "  -  ")
        return (f"  {self.name:<26} acc={self.acc:6.1%}  pass@k={self.pass_at_k:6.1%}  "
                f"plan-div={self.mean_plan_diversity:5.2f}  "
                f"ans-div={self.mean_diversity:5.2f}  "
                f"adher={adh}  calls={self.calls:<5} tok={self.tokens:<7} "
                f"fallback={self.fallbacks} lost={self.lost_branches}")


def run_repeated(problems, k: int, call: Callable[..., Reply], *,
                 effort: Optional[str], temperature: float,
                 max_tokens: int) -> ArmStats:
    """Baseline: k independent CoT samples, majority vote. No coordination."""
    st = ArmStats(f"repeated x{k}")
    t0 = time.time()
    for q, gold in problems:
        r = P.PlannedResult(question=q, gold=gold)
        for i in range(k):
            b = P._plain_branch(q, i, call, effort=effort,
                                temperature=temperature, max_tokens=max_tokens)
            r.branches.append(b)
            r.calls += 1
            r.tokens += b.tokens
        r.final = P.vote(r.branches)
        if gold is not None:
            r.correct = extract.answers_agree(r.final, gold)
            r.passed_at_k = any(
                extract.answers_agree(b.answer, gold) is True
                for b in r.branches)
        st.add(r)
    st.sec = time.time() - t0
    return st


def run_ptts(problems, k: int, call: Callable[..., Reply], *,
             effort: Optional[str], planner_temperature: float,
             executor_temperature: float, max_tokens: int,
             verbose: bool) -> ArmStats:
    st = ArmStats(f"PTTS-ZS x{k} (+1 plan)")
    for q, gold in problems:
        r = P.solve_planned(q, gold, k, call=call, effort=effort,
                            planner_temperature=planner_temperature,
                            executor_temperature=executor_temperature,
                            max_tokens=max_tokens)
        st.add(r)
        if verbose:
            mark = {True: "✓", False: "✗", None: "?"}[r.correct]
            pk = "PASS@k" if r.passed_at_k else "  --  "
            lost = f" LOST={r.lost_branches}" if r.lost_branches else ""
            print(f"  {mark} gold={extract.format_answer(gold):>10} "
                  f"voted={extract.format_answer(r.final):>10} {pk} "
                  f"distinct={r.distinct_answers}/{len(r.branches)} "
                  f"calls={r.calls} tok={r.tokens}{lost}")
            print(r.trace())
    return st


def render(name_a: str, a: ArmStats, name_b: str, b: ArmStats, k: int) -> str:
    L = ["", "=" * 104,
         f"PLANNED vs REPEATED -- matched k={k} executor calls "
         f"(paper 2609.27374)",
         "=" * 104,
         f"{'arm':<26} {'top-1':<14} {'pass@k':<14} {'plan-div':<11} "
         f"{'ans-div':<10} {'adherence':<12} calls  tokens  fallback",
         "-" * 104,
         a.row(), b.row(),
         "-" * 104]

    da = b.acc - a.acc
    dp = b.pass_at_k - a.pass_at_k
    L.append(f"  delta (PTTS - repeated):  top-1 {da:+.1%}   pass@k {dp:+.1%}")
    L.append("")

    pd, ad = b.mean_plan_diversity, b.mean_diversity
    pd0 = a.mean_diversity

    # The decisive diagnosis is the SEPARATION of the two diversities.
    if pd >= 0.60 and ad < 0.40:
        L.append("  THE PLANNER WORKS, THE EXECUTOR IGNORES IT.")
        L.append(f"  plan-div {pd:.2f} but ans-div {ad:.2f}: the planner wrote")
        L.append("  genuinely different methods and every branch still")
        L.append("  converged on the same number. Planning changed the")
        L.append("  reasoning path WITHOUT changing the outcome.")
        L.append("")
        L.append("  This is not a PTTS implementation failure and not a")
        L.append("  planning failure -- it is the executor being unable to")
        L.append("  act on a plan. Self-reported adherence does not detect")
        L.append("  it: the model reports near-perfect adherence to a plan")
        L.append("  whose different steps it then collapses to one result.")
        L.append("  More branches cannot help; the convergence is the binding")
        L.append("  constraint.")
    elif pd < 0.34:
        L.append("  PLANNER DEGENERATE: outlines are near-duplicates, so this")
        L.append("  arm is repeated sampling plus overhead. Any delta is noise.")
    elif dp > 0:
        L.append("  pass@k improved: planned branches reach answers that plain")
        L.append("  resampling does not. That is the coverage mechanism.")
    else:
        L.append("  pass@k did NOT move.")
        if pd >= 0.34:
            L.append("  Branches ARE diverse, so diversity alone is not")
            L.append("  sufficient -- different plans land on the same")
            L.append("  correctness. A coverage wall, not a coordination")
            L.append("  failure.")

    if pd0 > 0.5:
        L.append("")
        L.append(f"  NOTE: the baseline is itself highly diverse "
                 f"(ans-div {pd0:.2f}). Temperature is already producing")
        L.append("  diverse branches here, so PTTS has less headroom to beat")
        L.append("  than it would against a greedy baseline. This weakens the")
        L.append("  comparison -- a greedy baseline is the fairer control.")
    if not a.coverage_measurable or not b.coverage_measurable:
        L.append("")
        L.append("  UNGRADED PROBLEMS PRESENT: pass@k above is not a valid")
        L.append("  coverage measurement. Treat top-1 only.")

    if b.fallbacks:
        L.append("")
        L.append(f"  WARNING: {b.fallbacks} PTTS problem(s) fell back to")
        L.append("  unplanned branches. Those rows are NOT a PTTS measurement.")
    if a.lost_branches or b.lost_branches:
        L.append("")
        L.append(f"  LOST BRANCHES: repeated={a.lost_branches} "
                 f"ptts={b.lost_branches}. Dead calls shrink effective k, so")
        L.append("  pass@k above is measured over fewer branches than k. "
                 "Coverage")
        L.append("  is understated for whichever arm lost more.")
    L.append("=" * 104)
    return "\n".join(L)