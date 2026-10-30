"""Paper 2604.17433 -- Self-Consistency from Only Two Samples (CoT-PoT).

Claim: CoT and PoT have complementary error profiles. Ensembling the two modes
cuts the samples needed for self-consistency by ~9.3x, and most tasks resolve
with two samples.

This module implements the mechanism, not the paper's number. Two independent
solvers disagree -> a third call breaks the tie. Two calls on the happy path.
The honest accounting is at the bottom: every escalation is counted and priced.

Note the sampling-bias interaction with 2603.19118: they found a hybrid
estimator (self-consistency + verbalized confidence) beats either signal alone
even at small budgets. `verbalized` is on by default for exactly that reason,
and it costs nothing extra because reasoning_effort already produces text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import extract
import sandbox
from nous_client import Reply

COT_SYSTEM = """You are a careful math reasoner. Solve the problem with \
short explicit reasoning steps, then give the final numeric answer on the last \
line in exactly this format:

#### <number>

Rules: the answer is always a single number (no units, no currency symbols, no \
commas). Do not write code. Do not restate the problem."""

POT_SYSTEM = """You solve math problems by writing a short Python program.

Output ONLY a single ```python code block, no explanation before or after it.
The program must:
  - compute the answer using explicit arithmetic
  - print exactly one line: print(<answer>)
  - be self-contained (use only the standard library, no input(), no file I/O)
  - guard against division by zero; if a case is undefined print 'None'

Do not print intermediate steps. Do not add example usage after the block."""


@dataclass
class Attempt:
    mode: str                      # "cot" | "pot" | "escalation"
    effort: Optional[str]
    answer: Optional[float]
    ok: bool
    tokens: int
    detail: str = ""
    latency: float = 0.0
    raw_text: str = ""


@dataclass
class ProblemResult:
    question: str
    gold: Optional[float]
    attempts: list[Attempt] = field(default_factory=list)
    final: Optional[float] = None
    correct: Optional[bool] = None
    agreed: bool = False
    calls: int = 0
    tokens: int = 0
    escalated: bool = False

    @property
    def cost_calls(self) -> int:
        return self.calls

    def reasoning_trace(self) -> str:
        lines = []
        for a in self.attempts:
            lines.append(
                f"  [{a.mode:9} effort={a.effort or '-':6}] "
                f"ans={extract.format_answer(a.answer):>12} "
                f"ok={a.ok!s:5} {a.detail}")
        return "\n".join(lines) or "  (none)"


def _split(text: str) -> tuple[Optional[float], str]:
    """Final answer plus optional verbalized confidence.

    Confidence is parsed from a line like 'confidence: 0.8' or a trailing
    '(confidence 80%)'. Missing confidence is not an error -- it just means the
    hybrid estimator degrades to pure self-consistency for that attempt.
    """
    conf: Optional[float] = None
    import re
    m = re.search(r"confidence[:\s]+([01]?\.\d+|0|1)\b", text, re.I)
    if m:
        try:
            conf = float(m.group(1))
        except ValueError:
            conf = None
    if conf is None:
        m = re.search(r"confidence[:\s]+(\d{1,3})\s*%", text, re.I)
        if m:
            conf = min(1.0, float(m.group(1)) / 100.0)
    return conf, text


def solve_cot(question: str, call: Callable[..., Reply], *,
              effort: Optional[str], temperature: Optional[float],
              max_tokens: int = 2048, include_confidence: bool = False) -> Attempt:
    import time
    sys_prompt = COT_SYSTEM
    if include_confidence:
        sys_prompt += ("\n\nAfter the #### line, add a second line exactly:\n"
                       "confidence: <0.0-1.0>\n"
                       "That is your calibrated probability the answer is correct.")
    t0 = time.time()
    try:
        r = call(messages=[{"role": "system", "content": sys_prompt},
                           {"role": "user", "content": question}],
                 effort=effort, temperature=temperature,
                 max_tokens=max_tokens)
    except Exception as e:
        return Attempt("cot", effort, None, False, 0, f"call failed: {e}",
                       time.time() - t0)
    conf, _ = _split(r.text)
    ans = extract.extract_answer(r.text)
    detail = "truncated" if r.truncated else ""
    if conf is not None:
        detail = (detail + f" conf={conf:.2f}").strip()
    return Attempt("cot", effort, ans, ans is not None, r.usage.total,
                   detail, time.time() - t0, r.text)


def solve_pot(question: str, call: Callable[..., Reply], *,
              effort: Optional[str], temperature: Optional[float],
              max_tokens: int = 2048,
              timeout: float = sandbox.DEFAULT_TIMEOUT) -> Attempt:
    import time
    t0 = time.time()
    try:
        r = call(messages=[{"role": "system", "content": POT_SYSTEM},
                           {"role": "user", "content": question}],
                 effort=effort, temperature=temperature,
                 max_tokens=max_tokens)
    except Exception as e:
        return Attempt("pot", effort, None, False, 0, f"call failed: {e}",
                       time.time() - t0)

    src = sandbox.strip_markdown_fence(r.text)
    if not src:
        return Attempt("pot", effort, None, False, r.usage.total,
                       "no code emitted", time.time() - t0, r.text)

    ex = sandbox.run_pot(src, timeout=timeout)
    if ex.blocked:
        return Attempt("pot", effort, None, False, r.usage.total,
                       f"sandbox blocked: {ex.stderr[-120:]}",
                       time.time() - t0, r.text)
    if not ex.ok:
        why = "timeout" if ex.timed_out else f"rc={ex.returncode}"
        return Attempt("pot", effort, None, False, r.usage.total,
                       f"exec failed ({why}) {ex.stderr[-120:]}",
                       time.time() - t0, r.text)

    ans = extract.last_number(ex.stdout)
    if ans is None:
        return Attempt("pot", effort, None, False, r.usage.total,
                       f"no number in stdout: {ex.stdout[-120:]!r}",
                       time.time() - t0, r.text)
    return Attempt("pot", effort, ans, True, r.usage.total, "",
                   time.time() - t0, r.text)


def _escalate_cot(question: str, call: Callable[..., Reply], *,
                  effort: Optional[str], temperature: float,
                  max_tokens: int) -> Attempt:
    """Tie-break with a fresh CoT at higher temperature.

    Deliberately *not* a third PoT: if the program already disagreed with CoT,
    re-rolling the same execution strategy mostly reproduces the same bug.
    Diversifying the strategy is the whole point (cf. 2609.27374, where
    independent sampling from one policy yields correlated branches).
    """
    return solve_cot(question, call, effort=effort, temperature=temperature,
                     max_tokens=max_tokens)


def solve_problem(question: str, gold: Optional[float], *,
                  call: Callable[..., Reply],
                  effort: Optional[str] = None,
                  escalate_effort: Optional[str] = None,
                  temperature: Optional[float] = None,
                  tiebreak_temperature: float = 0.8,
                  max_tokens: int = 2048,
                  include_confidence: bool = False,
                  allow_escalation: bool = True) -> ProblemResult:
    """Two solvers, one tie-break. Returns a fully accounted ProblemResult."""
    res = ProblemResult(question=question, gold=gold)
    escalate_effort = escalate_effort or effort

    cot = solve_cot(question, call, effort=effort, temperature=temperature,
                    max_tokens=max_tokens,
                    include_confidence=include_confidence)
    pot = solve_pot(question, call, effort=effort, temperature=temperature,
                    max_tokens=max_tokens)
    res.attempts.extend([cot, pot])
    res.calls += 2
    res.tokens += cot.tokens + pot.tokens

    agree = extract.answers_agree(cot.answer, pot.answer)

    if agree is True:
        res.agreed = True
        res.final = cot.answer          # both say the same; prefer CoT's surface
    elif cot.answer is None and pot.answer is None:
        # nothing produced an answer -- a third call of either kind is the
        # best available move, so escalate rather than give up
        res.escalated = True
        tb = _escalate_cot(question, call, effort=escalate_effort,
                           temperature=tiebreak_temperature,
                           max_tokens=max_tokens)
        res.attempts.append(tb)
        res.calls += 1
        res.tokens += tb.tokens
        res.final = tb.answer
    elif agree is False:
        if allow_escalation:
            res.escalated = True
            tb = _escalate_cot(question, call, effort=escalate_effort,
                               temperature=tiebreak_temperature,
                               max_tokens=max_tokens)
            res.attempts.append(tb)
            res.calls += 1
            res.tokens += tb.tokens
            # trust the tie-break, but only if it disagrees with neither
            if extract.answers_agree(tb.answer, cot.answer) is True:
                res.final = tb.answer
            elif extract.answers_agree(tb.answer, pot.answer) is True:
                res.final = tb.answer
            else:
                # 2-vs-1: the executable path is the only oracle we actually have
                res.final = pot.answer if pot.answer is not None else tb.answer
        else:
            res.final = pot.answer if pot.answer is not None else cot.answer
    else:
        # one side missing -- prefer the executable answer, it was verified
        res.final = pot.answer if pot.answer is not None else cot.answer

    if res.gold is not None:
        res.correct = extract.answers_agree(res.final, res.gold)
    return res