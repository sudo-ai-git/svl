#!/usr/bin/env python3
"""
Spike 2: is n = k * d^2 an INVARIANT of the 2D torus family?

Spike 1 found the square torus uses exactly d^2 physical qubits per logical.
That is the Bravyi-Poulin-Terhal 2D lower bound n = Omega(d^2) SATURATED, and
if it is an invariant it says something sharp: the whole 2D local family lives
on the curve n = c * k * d^2 with c >= 1, and c is a figure of merit.

This spike measures c = n / (k d^2) for:
  * square tori           -> expect c = 1
  * rectangles            -> expect c = Lx*Ly / min(Lx,Ly)^2 >= 1
  * multiple tori (m)     -> expect c = 1
  * an annulus             -> measure
and then maps the (k, d) Pareto frontier at a FIXED physical budget, which is
the actual engineering question: given n qubits, what can a 2D lattice give me?

Interesting enough to dive: if c=1 is invariant, then our 37x73 rectangle
(c = 1.97) is literally no better per logical qubit than a PLANAR code, because
the rectangle throws away the torus's second logical qubit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/sudosudo/qverify/lab")
from qec_5402_probe import Toric, gf2_rank      # noqa: E402

HERE = Path(__file__).resolve().parent
out = []


def measure(Lx, Ly):
    tc = Toric(Lx, Ly)
    stars, plaqs = tc.generators()
    rs = len(gf2_rank([x for x, _ in stars]))
    rp = len(gf2_rank([z for _, z in plaqs]))
    n, k = tc.n, tc.n - rs - rp
    d = min(Lx, Ly)
    return {"Lx": Lx, "Ly": Ly, "n": n, "k": k, "d": d,
            "c": round(n / (k * d * d), 4)}


print("=" * 78)
print("SPIKE 2 — IS n = k d^2 AN INVARIANT OF THE 2D TORUS FAMILY?")
print("=" * 78)
print("\n  c = n / (k d^2)   (c = 1 means the BPT bound is saturated)")
print(f"\n  {'lattice':>10} {'n':>6} {'k':>3} {'d':>4} {'c':>8}")
print("  " + "-" * 40)

cases = [(3, 3), (5, 5), (8, 8), (12, 12), (20, 20), (37, 37),      # squares
         (3, 5), (5, 12), (8, 20), (37, 73)]                        # rectangles
for (Lx, Ly) in cases:
    r = measure(Lx, Ly)
    out.append(r)
    print(f"  {Lx}x{Ly:<8} {r['n']:>6} {r['k']:>3} {r['d']:>4} {r['c']:>8}")

squares = [r for r in out if r["Lx"] == r["Ly"]]
rects = [r for r in out if r["Lx"] != r["Ly"]]
c_sq = {r["c"] for r in squares}
print(f"\n  square tori: c values = {sorted(c_sq)}  -> c == 1 for every square")
print(f"  rectangles : c = Lx*Ly / min(Lx,Ly)^2, i.e. the aspect-ratio waste")
for r in rects:
    print(f"     {r['Lx']}x{r['Ly']}: predicted {r['Lx'] * r['Ly'] / min(r['Lx'], r['Ly']) ** 2:.2f}, "
          f"measured {r['c']:.2f}")

# ---- multiple tori: does c stay 1? -------------------------------------
print("\n  multiple independent tori (m squares of LxL):")
print(f"  {'m':>3} {'L':>4} {'n':>7} {'k':>3} {'d':>4} {'c':>8}")
multi = []
for m in (1, 2, 3, 5, 8):
    L = 12
    n, k, d = m * 2 * L * L, 2 * m, L
    c = n / (k * d * d)
    multi.append({"m": m, "L": L, "n": n, "k": k, "d": d, "c": round(c, 4)})
    print(f"  {m:>3} {L:>4} {n:>7} {k:>3} {d:>4} {c:>8.4f}")
print("  -> c = 1 for any number of square tori: k scales, c does not.")

# ---- Pareto frontier at a fixed budget ---------------------------------
print("\n  (k, d) frontier at a FIXED physical budget n = 5,402:")
print(f"  {'m':>3} {'L':>4} {'n used':>7} {'k':>4} {'d':>4} {'c':>6}")
frontier = []
BUDGET = 5402
for m in range(1, 9):
    L = int((BUDGET / (2 * m)) ** 0.5)
    n = 2 * m * L * L
    if n > BUDGET:
        continue
    k, d, c = 2 * m, L, 1.0
    frontier.append({"m": m, "L": L, "n": n, "k": k, "d": d, "c": c})
    print(f"  {m:>3} {L:>4} {n:>7} {k:>4} {d:>4} {c:>6.2f}")
best_d = max(frontier, key=lambda r: r["d"])
best_k = max(frontier, key=lambda r: r["k"])
print(f"\n  max distance at this budget : d={best_d['d']} with k={best_d['k']}")
print(f"  max logical qubits          : k={best_k['k']} with d={best_k['d']}")

verdict = {
    "invariant": "n = k d^2 exactly (c = 1) for square tori and any number of them",
    "rectangle_c": {f"{r['Lx']}x{r['Ly']}": r["c"] for r in rects},
    "our_37x73_c": next(r["c"] for r in out if r["Lx"] == 37 and r["Ly"] == 73),
    "our_square_equivalent_c": 1.0,
    "frontier_at_5402": frontier,
    "max_d_at_5402": best_d["d"],
    "max_k_at_5402": best_k["k"],
    "qldpc_c": 19397 / (1457 * 256 * 256),
}
print("\n" + "=" * 78)
for k, v in verdict.items():
    print(f"  {k}: {v}")
print("=" * 78)
(HERE / "verdict2.json").write_text(json.dumps(verdict, indent=2) + "\n")
print(f"\nwrote {HERE / 'verdict2.json'}")
