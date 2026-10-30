"""Problem loading. GSM8K from the local HF cache, or a JSONL file.

GSM8K is used because the whole mechanism is built around a *verifiable*
answer: no logprobs, no weight access, but you can always check the answer.
That is the same condition2605.14163 identifies as the binding constraint --
coverage is easy to amplify, selection needs a local soundness signal.
"""

from __future__ import annotations

import glob
import json
import os
import random
import re
from typing import Optional

_CACHED_GSM8K = os.path.expanduser(
    "~/.cache/huggingface/hub/datasets--openai--gsm8k/snapshots/*/main/*.parquet")

_ANS_RE = re.compile(r"####\s*(-?[\d,]*\.?\d+)")


def _gold_from_gsm8k(ans_field: str) -> Optional[float]:
    tail = ans_field.split("####")[-1] if "####" in ans_field else ans_field
    m = _ANS_RE.search(ans_field)
    tok = m.group(1) if m else tail.strip().split("\n")[-1]
    try:
        return float(tok.replace(",", "").replace("$", ""))
    except ValueError:
        return None


def load_gsm8k(n: int = 20, split: str = "test", seed: int = 0,
               shuffle: bool = False) -> list[tuple[str, Optional[float]]]:
    """Load n GSM8K items. Prefers datasets/parquet; falls back to the raw
    jsonl that ships alongside, so this works with no network."""
    files = sorted(glob.glob(_CACHED_GSM8K))
    if not files:
        raise FileNotFoundError(
            "no cached GSM8K parquet found under ~/.cache/huggingface")

    rows: list[dict] = []
    try:
        import pyarrow.parquet as pq  # type: ignore
        for fp in files:
            if split not in os.path.basename(fp):
                continue
            rows.extend(pq.read_table(fp).to_pylist())
    except ImportError:
        for fp in files:
            if split not in os.path.basename(fp):
                continue
            with open(fp) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
    if not rows:
        raise FileNotFoundError(f"no '{split}' split among {files}")

    out = [(r["question"], _gold_from_gsm8k(r["answer"])) for r in rows
           if r.get("question")]
    out = [p for p in out if p[1] is not None]
    if shuffle:
        random.Random(seed).shuffle(out)
    return out[:n]


def load_jsonl(path: str, limit: Optional[int] = None
               ) -> list[tuple[str, Optional[float]]]:
    """Each line: {"question": str, "answer": number|null}."""
    out: list[tuple[str, Optional[float]]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            q = d.get("question") or d.get("q") or d.get("problem")
            a = d.get("answer", d.get("gold"))
            if q is None:
                continue
            if a is not None:
                try:
                    a = float(str(a).replace(",", "").replace("$", ""))
                except ValueError:
                    a = None
            out.append((q, a))
            if limit and len(out) >= limit:
                break
    return out


def load_inline(specs: list[str]
                ) -> list[tuple[str, Optional[float]]]:
    """CLI form: "question text" or "question text ::42" """
    out = []
    for s in specs:
        if "::" in s:
            q, a = s.rsplit("::", 1)
            try:
                out.append((q, float(a)))
            except ValueError:
                out.append((q, None))
        else:
            out.append((s, None))
    return out


# ---------------------------------------------------------------------------
# Harder in-house set.
#
# Why this exists: measured 2026-10-03, Space Bunny Alpha scores 100% on the
# first 10 GSM8K test items at EVERY effort level including `low`. A saturated
# benchmark cannot show a lift -- both papers measure gains, so a benchmark
# where the model is already perfect reports "no effect" for the wrong reason.
#
# These items are multi-step and chosen to be error-prone: they need
# proportional reasoning, unit bookkeeping, and resisting the classic
# "intermediate-result-as-final-answer" trap. Gold answers are verified by
# hand-arithmetic in the comments and re-checked by the ladder's own grader.
HARD_SET: list[tuple[str, float]] = [
    # 15% of 240 = 36; then 36 * 1.2 = 43.2 -> 43. Trap: answering 36.
    ("A jacket costs $240. A store applies a 15% discount, then adds 20% "
     "sales tax on the discounted price. What is the final price in dollars, "
     "rounded to the nearest whole number?", 43.0),
    # rate: 60 km in 1.5h = 40 km/h; 40*3.5 = 140. Trap: 210 (ignoring 1.5h).
    ("A car travels 60 kilometers in 1.5 hours. At the same constant speed, "
     "how many kilometers does it travel in 3.5 hours?", 140.0),
    # 5 crates * 12 = 60; spoil 1/4 = 15; sell 60-15 = 45.
    ("A grocer receives 5 crates of apples with 12 apples in each crate. "
     "One quarter of the apples spoil. How many apples remain to be sold?", 45.0),
    # 3*4=12 tiles, each 0.25 m^2 -> 3.0 m^2
    ("A floor is 3 meters by 4 meters and is tiled with square tiles that are "
     "0.5 meters on each side. What is the total area in square meters of all "
     "the tiles? Give the number of square meters.", 3.0),
    # compound: 100*1.1=110, *1.1=121
    ("A population of 100 grows by 10 percent in the first year and by another "
     "10 percent in the second year. What is the population after two years?",
     121.0),
    # 8 workers * 3 days = 24 worker-days; job needs 24 -> 1 day
    ("Eight workers finish a job in 3 days. How many days would four workers "
     "take to finish the same job?", 6.0),
    # sum then total: 12+7+9=28; spend 15 -> 13
    ("A shop sells pens for $3, notebooks for $7 and bags for $9. Maya buys 4 "
     "pens, 1 notebook and 1 bag, and pays with a $60 note. How much change "
     "does she receive in dollars?", 26.0),
    # fraction of fraction: half of 3/4 = 3/8 = 0.375
    ("Three quarters of a collection are red. Of the red items, half are also "
     "square. What fraction of the whole collection is both red and square? "
     "Give the decimal.", 0.375),
]


def load_hard(n: int = 8) -> list[tuple[str, Optional[float]]]:
    return [(q, g) for q, g in HARD_SET[:n]]