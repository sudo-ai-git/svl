"""Statistics that make a null result interpretable.

The first three papers were measured at n=8, where "no effect" and "underpowered"
are the same observation. That is why this module exists: a null result is only
reportable if the interval is tight enough to exclude an effect worth caring
about, and a non-null result is only reportable if the interval excludes zero.

Everything here is stdlib-only. The point is that the arithmetic is inspectable
and testable, not that it is sophisticated -- scipy would be one more thing
whose version-specific behaviour I would have to verify before quoting a number
from it.

Deliberate choices:
  * Wilson score intervals, NOT normal approximation. At p near 0 or 1 and
    small n the normal interval runs outside [0,1] and is far too narrow.
  * Newcombe's method for a difference of two proportions, which is built from
    Wilson bounds and so inherits their coverage at small n.
  * A minimum detectable effect is reported alongside every null result, so the
    reader can see what the experiment was actually powered to detect.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# 95% two-sided normal quantile
Z95 = 1.959963984540054


@dataclass
class Interval:
    lo: float
    hi: float
    successes: int
    n: int
    method: str = "wilson"

    @property
    def point(self) -> float:
        return self.successes / self.n if self.n else 0.0

    @property
    def width(self) -> float:
        return self.hi - self.lo

    @property
    def excludes_zero(self) -> bool:
        """For a one-sided-vs-null reading: is the effect clearly non-zero?"""
        return self.lo > 0.0

    @property
    def significant(self) -> bool:
        return self.lo > 0.0 or self.hi < 1.0

    def fmt(self, pct: bool = True) -> str:
        s = 100.0 if pct else 1.0
        d = 1 if pct else 3
        return (f"{self.point*s:.{d}f}% [{self.lo*s:.{d}f}, {self.hi*s:.{d}f}]")

    def __str__(self) -> str:
        return (f"{self.fmt()}  ({self.successes}/{self.n}, "
                f"width={100*self.width:.1f}pp)")


def wilson(successes: int, n: int, z: float = Z95) -> Interval:
    """Wilson score interval for a binomial proportion.

    Always inside [0,1] and correct at small n, unlike the Wald interval.
    """
    if n <= 0:
        return Interval(0.0, 1.0, 0, 0, "wilson")
    p = successes / n
    d = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z / d) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return Interval(max(0.0, centre - half), min(1.0, centre + half),
                    successes, n, "wilson")


def newcombe_diff(s1: int, n1: int, s2: int, n2: int,
                  z: float = Z95) -> tuple[float, float, float]:
    """Difference s1/n1 - s2/n2 with a Newcombe hybrid-score interval.

    Built from the two Wilson bounds, so it inherits their coverage at the small
    sample sizes where the Wald difference interval is hopeless.
    Returns (diff, lo, hi).
    """
    if n1 <= 0 or n2 <= 0:
        return 0.0, -1.0, 1.0
    a = wilson(s1, n1, z)
    b = wilson(s2, n2, z)
    diff = a.point - b.point
    # Newcombe: lower = diff - sqrt((p1-l1)^2 + (u2-p2)^2)
    lo = diff - math.sqrt((a.point - a.lo) ** 2 + (b.hi - b.point) ** 2)
    hi = diff + math.sqrt((a.hi - a.point) ** 2 + (b.point - b.lo) ** 2)
    return diff, max(-1.0, lo), min(1.0, hi)


def paired_bootstrap_delta(per_item_a: list[int], per_item_b: list[int],
                           iters: int = 10_000,
                           seed: int = 0) -> tuple[float, float, float,
                                                    Optional[float]]:
    """Paired bootstrap over the DIFFERENCE of two per-item outcome lists.

    Both arms saw the SAME problems, so the pairing is real and resampling
    items (not runs) is the right unit. Returns
    (delta, ci_lo, ci_hi, p_two_sided).

    The CI is a percentile bootstrap of the delta. The p-value is NOT read off
    that same distribution: a percentile bootstrap is centred on the OBSERVED
    delta, so "how often does a resample exceed obs" is ~0.5 by construction and
    everything looks significant. That version reported p=0.0000 for 36/40 vs
    38/40 -- one swapped problem -- while the CI correctly straddled zero.

    To test H0 the resamples must be centred on zero, so each per-item
    difference is shifted by the observed mean before resampling (Efron &
    Tibshirani's bootstrap hypothesis test). The percentile CI and the
    null-centred p then agree.

    p is None when it is undefined: with zero-variance arms there is no
    reference distribution, so any tail fraction is 0 or 1 by construction.
    A fabricated p is worse than none -- the CI still decides.
    """
    import random
    if len(per_item_a) != len(per_item_b):
        raise ValueError("paired arms must have equal length")
    n = len(per_item_a)
    if n == 0:
        return 0.0, -1.0, 1.0, 1.0

    diffs = [a - b for a, b in zip(per_item_a, per_item_b)]
    obs = sum(diffs) / n
    centred = [d - obs for d in diffs]

    rng = random.Random(seed)
    idx = range(n)
    deltas: list[float] = []
    nulls: list[float] = []
    for _ in range(iters):
        s = s0 = 0
        for _ in range(n):
            j = rng.choice(idx)
            s += diffs[j]
            s0 += centred[j]
        deltas.append(s / n)
        nulls.append(s0 / n)
    deltas.sort()
    lo = deltas[int(0.025 * iters)]
    hi = deltas[min(iters - 1, int(0.975 * iters))]

    if deltas[-1] - deltas[0] <= 1e-12:
        return obs, lo, hi, None       # type: ignore[return-value]

    # Far tails only: the inclusive versions overlap when |obs| is small
    # relative to the spread, and 2*min() of an overlapping pair gave p=1.13.
    # Strictly-beyond tails are disjoint, so the doubled minimum is <= 1.
    far_high = sum(1 for x in nulls if x > abs(obs)) / iters
    far_low = sum(1 for x in nulls if x < -abs(obs)) / iters
    p = max(0.0, min(1.0, 2.0 * min(far_high, far_low)))
    return obs, lo, hi, p


def min_detectable_effect(n: int, baseline_p: float = 0.5,
                          z: float = Z95, power_z: float = 0.8416) -> float:
    """Smallest accuracy gain this n could detect with 80% power.

    Reported with every null result. Without it, "no significant difference" is
    indistinguishable from "this experiment could never have found a
    difference" -- which is exactly the n=8 problem.
    """
    if n <= 0:
        return 1.0
    p1, p2 = baseline_p, baseline_p
    pb = (p1 + p2) / 2
    return (z + power_z) * math.sqrt(2 * pb * (1 - pb) / n)


def mde_two_sided(n: int, baseline_p: float = 0.5) -> float:
    """Alias kept for readability at the call site."""
    return min_detectable_effect(n, baseline_p)


def describe_null(iv: Interval, baseline_p: float | None = None) -> str:
    """Honest phrasing for a non-significant result."""
    bits = [f"{iv.point*100:.1f}% [{iv.lo*100:.1f}, {iv.hi*100:.1f}]"]
    if not iv.significant:
        if iv.n > 0:
            mde = min_detectable_effect(iv.n, baseline_p or iv.point)
            bits.append(f"NOT significant; n={iv.n} could only detect "
                        f"gains of >={mde*100:.1f}pp")
        else:
            bits.append("NOT significant")
    else:
        bits.append("significant")
    return "; ".join(bits)


def paired_verdict(name_a: str, per_item_a: list[int],
                   name_b: str, per_item_b: list[int],
                   seed: int = 0) -> str:
    """Compare two arms run on the SAME problems, with the power stated.

    The pairing is real (both arms saw identical items), so a paired bootstrap
    is the right tool and is tighter than comparing two independent intervals.

    Reports, in order: both headline rates with intervals, the paired delta with
    its interval, and -- for a null -- the smallest gain this n could have
    detected. A null without that last number is not a finding.
    """
    n = len(per_item_a)
    ia = wilson(sum(per_item_a), n)
    ib = wilson(sum(per_item_b), n)
    obs, lo, hi, p = paired_bootstrap_delta(per_item_a, per_item_b,
                                            iters=10_000, seed=seed)
    lines = [
        f"  {name_a:<22} {ia.fmt()}  ({ia.successes}/{ia.n})",
        f"  {name_b:<22} {ib.fmt()}  ({ib.successes}/{ib.n})",
        f"  paired delta: {obs*100:+.1f}pp  95% CI [{lo*100:+.1f}, "
        f"{hi*100:+.1f}]",
    ]
    if lo > 0:
        verdict = f"SIGNIFICANT gain for {name_a} (CI excludes 0)"
    elif hi < 0:
        verdict = f"SIGNIFICANT loss for {name_a} (CI excludes 0)"
    else:
        mde = min_detectable_effect(n, ia.point)
        verdict = (f"NO SIGNIFICANT DIFFERENCE -- n={n} could only detect "
                   f"gains of >={mde*100:.1f}pp, so a real effect smaller "
                   f"than that is still consistent with these data")
    if p is not None:
        verdict += f"; bootstrap p={p:.4f}"
    else:
        verdict += "; bootstrap p undefined (zero-variance arms)"
    lines.append(f"  VERDICT: {verdict}")
    return "\n".join(lines)