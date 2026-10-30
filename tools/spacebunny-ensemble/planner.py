"""Paper 2609.27374 -- Planned Test-Time Scaling with Coordinated Reasoning Paths.

The problem it attacks is precisely the one measured in this repo. My ensemble
run on the hard set: CoT and PoT agreed on 8/8 items including all three wrong
ones. Independent sampling from one policy produces correlated branches, so
extra inference compute re-rolls the same mistake. PTTS makes the branches
*coordinated* instead: a planner emits a distinct outline per branch, and an
executor conditions on its outline.

  PTTS-ZS (zero-shot)  -- what we can run. Planner writes all k outlines in one
                          autoregressive pass, executors are the untouched model.
  PTTS-RL              -- trains the planner against pass@k. Needs weights, which
                          a black-box API does not give us. Not implemented; not
                          faked.

Two things this module measures that the headline pass@k number hides, because
both are the reasons the method can fail:

  1. DISTINCTNESS -- are the branches actually different, or does the planner
     emit k paraphrases? Measured as pairwise answer disagreement plus a
     self-reported diversity check.
  2. ATTRIBUTION -- does a branch succeed *because* of its outline? A planner
     that improves accuracy while producing identical branches is not the
     mechanism the paper describes.

If distinctness is ~0, PTTS has collapsed into repeated sampling and any gain
is noise. That check runs on every experiment.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import extract
from nous_client import Reply

PLANNER_SYSTEM = """You design DIVERGENT solution strategies for a math problem.

You will be given one problem and must write {k} mutually DIFFERENT solution \
outlines. Different means a genuinely different approach, not different wording:
different first step, different decomposition, different representation \
(e.g. work backwards, enumerate cases, set up an equation, simulate directly, \
check by substitution).

Rules:
- Each outline must be independently solvable and self-contained.
- State the concrete first move of that approach in one line.
- Do NOT compute the final answer. You are planning routes, not solving.
- Output exactly {k} outlines in this format and nothing else:

<outline id="1">
approach: <short name of the method>
first move: <the concrete first step>
steps:
- <step>
- <step>
</outline>
<outline id="2">
...
</outline>

The outlines must differ from each other in approach, not just in numbering."""

EXECUTOR_SYSTEM = """You solve a math problem by following a specific plan.

You will be given a problem and ONE solution outline. Follow that outline \
faithfully -- it was chosen to be a route you would not have picked yourself.

Output your reasoning, then the final line exactly:
#### <number>

The answer is always a single number (no units, no currency, no commas)."""


@dataclass
class Outline:
    id: str
    approach: str = ""
    first_move: str = ""
    steps: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"approach: {self.approach or 'unspecified'}"]
        if self.first_move:
            lines.append(f"first move: {self.first_move}")
        if self.steps:
            lines.append("steps:")
            lines.extend(f"- {s}" for s in self.steps)
        return "\n".join(lines)


@dataclass
class Branch:
    index: int
    outline_id: str
    answer: Optional[float]
    tokens: int
    ok: bool
    detail: str = ""
    raw_text: str = ""
    follow_score: Optional[float] = None    # self-reported plan adherence

    def short(self) -> str:
        return (f"b{self.index}[o{self.outline_id}] "
                f"{extract.format_answer(self.answer)}")


@dataclass
class PlannedResult:
    question: str
    gold: Optional[float]
    outlines: list[Outline] = field(default_factory=list)
    branches: list[Branch] = field(default_factory=list)
    final: Optional[float] = None
    correct: Optional[bool] = None
    passed_at_k: bool = False          # any branch correct (pass@k)
    calls: int = 0
    tokens: int = 0
    planner_tokens: int = 0
    sec: float = 0.0
    error: str = ""

    # ---- diversity diagnostics: the part the headline metric hides --------
    #
    # Two DIFFERENT kinds of diversity, and conflating them is exactly how a
    # PTTS harness produces a confident wrong conclusion. Measured on this
    # model: the planner emitted four genuinely different methods (grid-count,
    # area-preservation, unit-rescaling, row-by-row) and all four branches
    # still returned the same answer. The convergence happens at the executor,
    # not the planner. Reporting "low diversity" from answer counts alone would
    # blame the planner for the executor's behaviour.

    @property
    def distinct_answers(self) -> int:
        vals = [b.answer for b in self.branches if b. answer is not None]
        uniq: list[float] = []
        for v in vals:
            if not any(extract.answers_agree(v, u) for u in uniq):
                uniq.append(v)
        return len(uniq)

    @property
    def plan_diversity(self) -> float:
        """Pairwise dissimilarity of the planner's outlines, in [0, 1].

        1.0 = every outline describes a different approach.
        This is the quantity PTTS actually claims to control.
        """
        return _text_diversity([o.approach for o in self.outlines])

    @property
    def answered(self) -> int:
        return sum(1 for b in self.branches if b.answer is not None)

    @property
    def lost_branches(self) -> int:
        """Branches that produced nothing -- dead calls, not wrong answers.

        These shrink effective coverage, so they must be visible: a run that
        lost 3 of 16 branches did not measure pass@4.
        """
        return sum(1 for b in self.branches if b.answer is None)

    @property
    def diversity(self) -> float:
        """Fraction of branches that produced a distinct answer.

        0.0 -> every branch identical, PTTS has degenerated into repeated
        sampling. 1.0 -> every branch disagreed.
        """
        if not self.branches:
            return 0.0
        return self.distinct_answers / max(1, self.answered)

    @property
    def spread(self) -> float:
        """1 - max share of any single answer among answered branches."""
        if not self.answered:
            return 0.0
        vals = [b.answer for b in self.branches if b.answer is not None]
        uniq: list[float] = []
        for v in vals:
            if not any(extract.answers_agree(v, u) for u in uniq):
                uniq.append(v)
        best = 0
        for u in uniq:
            n = sum(1 for v in vals if extract.answers_agree(v, u) is True)
            best = max(best, n)
        return 1.0 - best / len(vals)

    def trace(self) -> str:
        out = [f"  outlines parsed: {len(self.outlines)}"
               f"  plan-div={self.plan_diversity:.2f}"]
        for o in self.outlines:
            out.append(f"    [o{o.id}] {o.approach or '?':38} | "
                       f"{(o.first_move or '')[:60]}")
        for b in self.branches:
            fs = "" if b.follow_score is None else f" follow={b.follow_score:.2f}"
            out.append(f"    {b.short():28} ok={b.ok!s:5} "
                       f"tok={b.tokens:<5}{fs} {b.detail}")
        return "\n".join(out)


_STOP = frozenset("""a an the of to for and or in on at by with from as is are be using
use method approach way solve compute calculate determine find get via that this
then than into over under each all one two three first next step steps direct
direct""".split())

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower())
            if w not in _STOP and len(w) > 2}


def _text_diversity(texts: list[str]) -> float:
    """Mean pairwise Jaccard DISsimilarity of short strings, in [0, 1].

    0.0 = all identical (or fewer than 2 items); 1.0 = no shared content words.
    Deliberately not embedding or an LLM judge: this has to be cheap, offline,
    and deterministic enough that a regression test can assert on it.
    """
    toks = [_tokens(t) for t in texts]
    toks = [t for t in toks if t]
    if len(toks) < 2:
        return 0.0
    pairs, sims = 0, 0.0
    for i in range(len(toks)):
        for j in range(i + 1, len(toks)):
            union = toks[i] | toks[j]
            if not union:
                continue
            inter = len(toks[i] & toks[j])
            sims += inter / len(union)
            pairs += 1
    if not pairs:
        return 0.0
    return max(0.0, min(1.0, 1.0 - sims / pairs))


# ---------------------------------------------------------------- parsing

_OUTLINE_RE = re.compile(
    r"<outline[^>]*\bid\s*=\s*[\"']?(\d+)[\"']?[^>]*>(.*?)</outline>",
    re.S | re.I)


def parse_outlines(text: str, k: int) -> list[Outline]:
    """Pull outlines out of a planner response.

    Tolerant by design: models add prose, renumber, or emit unclosed tags.
    Falling back to splitting on the ids means a malformed response still
    produces usable plans instead of collapsing to a single branch.
    """
    if not text:
        return []
    out: list[Outline] = []
    for m in _OUTLINE_RE.finditer(text):
        body = m.group(2)
        o = Outline(id=m.group(1))
        a = re.search(r"approach\s*:\s*(.+)", body, re.I)
        if a:
            o.approach = a.group(1).strip().strip('"').strip()
        f = re.search(r"first move\s*:\s*(.+)", body, re.I)
        if f:
            o.first_move = f.group(1).strip().strip('"').strip()
        s = re.search(r"steps\s*:\s*(.*)", body, re.I | re.S)
        if s:
            o.steps = [ln.strip().lstrip("-*").strip()
                       for ln in s.group(1).splitlines()
                       if ln.strip().startswith(("-", "*"))]
        if o.approach or o.steps or o.first_move:
            out.append(o)

    if out:
        return out[:k]

    # fallback: numbered blocks without the tag wrapper
    blocks = re.split(r"\n(?=\s*(?:outline\s*)?\d+[.)]\s)", text)
    cand: list[Outline] = []
    for i, b in enumerate(blocks):
        a = re.search(r"approach\s*:\s*(.+)", b, re.I)
        f = re.search(r"first move\s*:\s*(.+)", b, re.I)
        if a or f:
            cand.append(Outline(id=str(i + 1),
                                approach=(a.group(1).strip() if a else ""),
                                first_move=(f.group(1).strip() if f else "")))
    return cand[:k]


_FOLLOW_RE = re.compile(
    r"plan[- ]adherence\s*:\s*([01]?\.\d+|0|1|10|[1-9])\s*(%?)", re.I)


def parse_follow_score(text: str) -> Optional[float]:
    m = _FOLLOW_RE.search(text or "")
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    if m.group(2) == "%":
        v /= 100.0
    elif v > 1.0:
        v /= 10.0
    return max(0.0, min(1.0, v))


# ---------------------------------------------------------------- solving

def make_planner(k: int) -> str:
    return PLANNER_SYSTEM.replace("{k}", str(k))


def plan(question: str, k: int, call: Callable[..., Reply], *,
         effort: Optional[str], temperature: float = 0.7,
         max_tokens: int = 1600) -> tuple[list[Outline], int, str]:
    """One autoregressive pass producing up to k outlines.

    temperature>0 on purpose: the whole point is that the planner must not
    return the same plan k times. A greedy planner is the degenerate case and
    the diversity check will catch it, but there is no reason to make it more
    likely.
    """
    try:
        r = call(messages=[{"role": "system", "content": make_planner(k)},
                           {"role": "user", "content": question}],
                 effort=effort, temperature=temperature, max_tokens=max_tokens)
    except Exception as e:
        return [], 0, f"planner failed: {type(e).__name__} {e}"
    outs = parse_outlines(r.text, k)
    return outs, r.usage.total, ("" if outs else "planner produced no outlines")


_BACKOFF = (1.0, 3.0)      # seconds; two retries is enough for a blip


def execute(question: str, outline: Outline, index: int,
            call: Callable[..., Reply], *, effort: Optional[str],
            temperature: float = 0.0, max_tokens: int = 2048,
            ask_adherence: bool = True,
            branch_retries: int = 2) -> Branch:
    """One executor call, with retry on transient endpoint failure.

    A branch that dies costs coverage, and coverage is the metric PTTS is
    judged on: an EndpointError that silently removes a branch makes the run
    look LESS diverse than it is. Retry the same outline before giving up, and
    count how many branches were lost so the caller can report it.
    """
    plan_text = (f"<outline id=\"{outline.id}\">\n{outline.render()}\n</outline>")
    user = f"Problem:\n{question}\n\nFollow ONLY this outline:\n{plan_text}"
    if ask_adherence:
        user += ("\n\nAfter your #### line, add one line exactly:\n"
                 "plan-adherence: <0-10>")

    detail = ""
    for attempt in range(branch_retries + 1):
        try:
            r = call(messages=[{"role": "system", "content": EXECUTOR_SYSTEM},
                               {"role": "user", "content": user}],
                     effort=effort, temperature=temperature,
                     max_tokens=max_tokens)
        except Exception as e:
            detail = f"call failed: {type(e).__name__}"
            if attempt < branch_retries:
                time.sleep(_BACKOFF[min(attempt, len(_BACKOFF) - 1)])
                continue
            return Branch(index, outline.id, None, 0, False, detail,
                          follow_score=None)
        ans = extract.extract_answer(r.text)
        if ans is None and attempt < branch_retries:
            # a truncated or unparsable completion is usually a token-budget
            # problem, not a reasoning problem -- one more attempt often lands
            detail = "unparsable"
            time.sleep(_BACKOFF[min(attempt, len(_BACKOFF) - 1)])
            continue
        detail = "truncated" if r.truncated else ""
        return Branch(index, outline.id, ans, r.usage.total, ans is not None,
                      detail, r.text, parse_follow_score(r.text))
    return Branch(index, outline.id, None, 0, False, detail or "failed",
                  follow_score=None)


def vote(branches: list[Branch]) -> Optional[float]:
    """Majority vote over branch answers.

    Ties break toward the branch with the highest self-reported plan adherence,
    then toward the earliest branch (planning order carries the model's own
    preference). No logprobs are available to break ties properly, and this
    says so rather than pretending the tiebreak is principled.
    """
    answered = [b for b in branches if b.answer is not None]
    if not answered:
        return None
    buckets: list[tuple[float, list[Branch]]] = []
    for b in answered:
        for i, (val, members) in enumerate(buckets):
            if extract.answers_agree(b.answer, val) is True:
                members.append(b)
                break
        else:
            buckets.append((b.answer, [b]))  # type: ignore[arg-type]
    if not buckets:
        return None
    top = max(len(m) for _, m in buckets)
    tied = [(v, m) for v, m in buckets if len(m) == top]
    if len(tied) == 1:
        return tied[0][0]
    tied.sort(key=lambda vm: (
        -(max((x.follow_score or 0.0) for x in vm[1])),
        min(x.index for x in vm[1]),
    ))
    return tied[0][0]


def solve_planned(question: str, gold: Optional[float], k: int, *,
                  call: Callable[..., Reply],
                  effort: Optional[str] = None,
                  planner_temperature: float = 0.7,
                  executor_temperature: float = 0.0,
                  max_tokens: int = 2048,
                  ask_adherence: bool = True) -> PlannedResult:
    """PTTS-ZS: plan k routes, execute each, vote.

    Falls back to un-planned branches if the planner returns nothing usable, and
    says so in `error` -- a fallback that silently looks like success is how
    PTTS gets credited for gains that came from plain resampling.
    """
    t0 = time.time()
    res = PlannedResult(question=question, gold=gold)
    outs, ptok, perr = plan(question, k, call, effort=effort,
                            temperature=planner_temperature,
                            max_tokens=max_tokens)
    res.outlines = outs
    res.planner_tokens = ptok
    res.tokens += ptok
    res.calls += 1
    res.sec = time.time() - t0
    if perr:
        res.error = perr

    if not outs:
        # degraded: run k plain CoT branches so the comparison stays honest
        for i in range(k):
            b = _plain_branch(question, i, call, effort=effort,
                              temperature=executor_temperature,
                              max_tokens=max_tokens)
            res.branches.append(b)
            res.calls += 1
            res.tokens += b.tokens
        res.error = (res.error + " | " if res.error else "") + \
            "FELL BACK TO UNPLANNED BRANCHES"
    else:
        for i, o in enumerate(outs):
            b = execute(question, o, i, call, effort=effort,
                        temperature=executor_temperature,
                        max_tokens=max_tokens, ask_adherence=ask_adherence)
            res.branches.append(b)
            res.calls += 1
            res.tokens += b.tokens

    res.final = vote(res.branches)
    if gold is not None:
        res.correct = extract.answers_agree(res.final, gold)
        res.passed_at_k = any(
            extract.answers_agree(b.answer, gold) is True
            for b in res.branches)
    res.sec = time.time() - t0
    return res


def _plain_branch(question: str, index: int,
                  call: Callable[..., Reply], *, effort: Optional[str],
                  temperature: float, max_tokens: int,
                  branch_retries: int = 2) -> Branch:
    for attempt in range(branch_retries + 1):
        try:
            r = call(messages=[{"role": "system",
                                "content": "Solve. End with a line "
                                           "'#### <number>'."},
                               {"role": "user", "content": question}],
                     effort=effort, temperature=temperature,
                     max_tokens=max_tokens)
        except Exception as e:
            if attempt < branch_retries:
                time.sleep(_BACKOFF[min(attempt, len(_BACKOFF) - 1)])
                continue
            return Branch(index, "-", None, 0, False,
                          f"call failed: {type(e).__name__}")
        ans = extract.extract_answer(r.text)
        if ans is None and attempt < branch_retries:
            time.sleep(_BACKOFF[min(attempt, len(_BACKOFF) - 1)])
            continue
        return Branch(index, "-", ans, r.usage.total, ans is not None,
                      "truncated" if r.truncated else "", r.text, None)
    return Branch(index, "-", None, 0, False, "failed")