"""MATH-500 loader -- a real benchmark with headroom, replacing the in-house set.

Why this exists: the first three papers were measured on an 8-item hand-built
set. At n=8 "no effect" and "underpowered" are indistinguishable, so thoseresults could not support the conclusion they were used for. MATH-500 gives
321 strictly-numeric items (158 at level 4-5) from a standard published
competition suite, which is enough to put an interval on the answer.

Grading note, and it matters: only answers that parse to a float are used, so
the grader is an exact numeric comparison with the same relative tolerance the
rest of the harness uses. That is stricter than MATH-500's own boxed-answer
string-equality rule and it silently drops 36% of the set (the LaTeX-heavy
answers like frac{3}{4} and (3,pi/2)). We keep only what we can actually
verify -- an unverifiable answer would be a silent correctness hole, which is
the same failure class as counting dead branches as wrong answers.
"""

from __future__ import annotations

import json
import os
import random
import re
from typing import Optional

_MATH500 = os.path.expanduser(
    "~/.hermes/cache/spacebunny-ensemble/math500/test.jsonl")

_REMOTE = ("https://huggingface.co/datasets/HuggingFaceH4/MATH-500/"
           "resolve/main/test.jsonl")

_INT = re.compile(r"^-?\d+$")
_DEC = re.compile(r"^-?\d*\.\d+$")
_FRAC = re.compile(r"^(-?\d+)\s*/\s*(-?\d+)$")


def _strip(ans: str) -> str:
    """Remove LaTeX noise from an answer string.

    Done with explicit replaces, not str.translate: the tidy helpers like
    '\\!' and '\\,' are two characters long and str.translate requires
    single-character keys, so a translate table raises ValueError at import.

    Handles the noise forms MATH-500 actually uses: percent signs and the
    brace-grouped thousands separator ('1{,}000').

    Braces are NOT stripped in general. Only the specific grouping pattern
    '{,}' is removed, then the whole string must still parse as a plain
    number. Stripping every brace turns '{12}' into 12 -- fabricating a gold
    out of LaTeX, which is worse than dropping the item because it silently
    invents a correct answer for an unverifiable question.
    """
    s = str(ans)
    for junk in ("\\!", "\\,", "\\;", "\\ ", "\\%", "$", "\\$", "{,}"):
        s = s.replace(junk, "")
    return s.strip()


def to_float(ans: str) -> Optional[float]:
    """Strict numeric parse. Returns None for anything not exactly numeric.

    Deliberately NOT lenient. A fuzzy parser here would mark wrong answers
    correct, and a benchmark that overstates accuracy is worse than a smaller
    honest one.
    """
    if ans is None:
        return None
    s = _strip(ans)
    if re.match(r"^-?[\d,]+\.?\d*$", s):
        s = s.replace(",", "")
    if s.endswith("%") and _INT.match(s[:-1]):
        # MATH-500 sometimes stores percents as bare digits; keep the digits
        # rather than inventing a scale factor we cannot justify.
        s = s[:-1].strip()
    if _INT.match(s):
        return float(s)
    if _DEC.match(s):
        return float(s)
    m = _FRAC.match(s)
    if m:
        den = float(m.group(2))
        if den == 0:
            return None
        return float(m.group(1)) / den
    return None


def _ensure_cached() -> Optional[str]:
    if os.path.isfile(_MATH500):
        return _MATH500
    try:
        import time
        import urllib.request
        os.makedirs(os.path.dirname(_MATH500), exist_ok=True)
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    _REMOTE, headers={"User-Agent": "Mozilla/5.0"})
                blob = urllib.request.urlopen(req, timeout=90).read()
                with open(_MATH500, "wb") as f:
                    f.write(blob)
                return _MATH500
            except Exception:
                if attempt == 2:
                    return None
                time.sleep(2 * (attempt + 1))
    except Exception:
        return None
    return None


def load_math500(n: int = 40, *, levels: Optional[tuple[int, ...]] = None,
                 seed: int = 0) -> list[tuple[str, Optional[float]]]:
    """n numeric MATH-500 problems, optionally filtered by difficulty level.

    Deterministic given (n, levels, seed): the same call returns the same
    problems in the same order, so a rerun compares like with like.
    """
    path = _ensure_cached()
    if not path:
        raise FileNotFoundError(
            f"MATH-500 not cached at {_MATH500} and download failed")
    rows = [json.loads(l) for l in open(path)]
    items: list[tuple[str, Optional[float]]] = []
    for r in rows:
        lvl = r.get("level")
        if levels and lvl not in levels:
            continue
        gold = to_float(r.get("answer", ""))
        if gold is None:
            continue
        q = r["problem"].strip()
        items.append((q, gold))
    if seed:
        random.Random(seed).shuffle(items)
    return items[:n]


def load_math500_hard(n: int = 40, seed: int = 0
                      ) -> list[tuple[str, Optional[float]]]:
    """Levels 4-5 only -- the headroom end of the suite."""
    return load_math500(n, levels=(4, 5), seed=seed)


def describe(items: list[tuple[str, Optional[float]]]) -> str:
    golds = [g for _, g in items if g is not None]
    dec = sum(1 for g in golds if abs(g - round(g)) > 1e-9)
    return (f"n={len(items)} graded={len(golds)} "
            f"decimal-golds={dec} "
            f"non-integer={dec}/{len(golds)}")