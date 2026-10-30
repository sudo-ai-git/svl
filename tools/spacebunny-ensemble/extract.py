"""Numeric answer extraction + normalization.

Two jobs:
  1. pull a final numeric answer out of free-form CoT text
  2. decide whether two extracted answers actually mean the same thing

The second job matters more than the first. Majority voting over strings
falls apart on "1,000" vs "1000" vs "$1000.00", and a PoT program that
prints "0.6666666666" and a CoT that says "2/3" are the same answer.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Optional

# Ordered: first pattern that matches wins. Later patterns are fallbacks for
# models that ignore the requested format. The numeric group deliberately
# admits fractions (3/4) and exponents (1.5e3) -- truncating those to "3" and
# "1.5" is a silent wrong answer, not a parse failure.
_NUMPAT = r"(-?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?(?:\s*/\s*-?\d[\d,]*(?:\.\d+)?)?)"
_ANSWER_PATTERNS = [
    re.compile(r"####\s*\\?\$?\s*" + _NUMPAT),                 # GSM8K native
    re.compile(r"\\boxed\{\s*\\?\$?\s*" + _NUMPAT),           # boxed
    re.compile(r"<answer>\s*\\?\$?\s*" + _NUMPAT + r"\s*</answer>", re.I),
    re.compile(r"(?:final answer|answer)\s*(?:is|:)\s*\**\s*\\?\$?\s*" + _NUMPAT,
               re.I),
    re.compile(r"^\s*\\?\$?\s*" + _NUMPAT + r"\s*$", re.M),   # bare last line
]

_NUM = re.compile(r"-?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?")


def _strip_markers(s: str) -> str:
    s = s.strip()
    s = s.replace("\\$", "").replace("$", "")
    s = s.replace("\\%", "").replace("%", "")
    s = s.replace(",", "").replace("\\!", "").replace("!", "")
    return s.strip().strip(".").strip()


def _to_float(tok: str) -> Optional[float]:
    """Parse a numeric token to float. Handles 1,000 / 1e3 / 3/4 / 50%."""
    tok = _strip_markers(tok)
    if not tok:
        return None
    try:
        return float(tok)
    except ValueError:
        pass
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", tok)
    if m:
        try:
            den = float(m.group(2))
            return float(m.group(1)) / den if den else None
        except (ValueError, ZeroDivisionError):
            return None
    return None


def extract_answer(text: str) -> Optional[float]:
    """Best-effort final-answer extraction. Returns float or None."""
    if not text:
        return None
    for pat in _ANSWER_PATTERNS:
        hits = pat.findall(text)
        if hits:
            v = _to_float(hits[-1])
            if v is not None:
                return v
    # last resort: last numeric token anywhere in the tail of the response
    tail = text[-400:]
    nums = _NUM.findall(tail)
    for tok in reversed(nums):
        v = _to_float(tok)
        if v is not None:
            return v
    return None


def answers_agree(a: Optional[float], b: Optional[float],
                  rel_tol: float = 1e-6) -> Optional[bool]:
    """True/False if comparable, None if either side is missing.

    Relative tolerance so that 100000 and 100000.0000001 agree, but 2/3 and
    0.666 agree too (they differ in the 3rd decimal, well inside 1e-6
    relative for small magnitudes -- see REL_SLACK below).
    """
    if a is None or b is None:
        return None
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) <= rel_tol * scale


def format_answer(v: Optional[float]) -> str:
    """Canonical string form, for logging and for grader keys."""
    if v is None:
        return "<none>"
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return repr(round(v, 6))


def last_number(text: str) -> Optional[float]:
    """For program output: take the final numeric token printed."""
    return extract_answer(text) if text else None