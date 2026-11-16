#!/usr/bin/env python3
"""
Spike: how good can a LATTICE code get, really?

Jack's challenge: "we have an annulus, error correcting code, lattices — it must
be possible." This spike tests that instead of asserting it.

Three questions, each answered by measurement or by a cited theorem:

  Q1  Within our Euclidean lattice family, what is the BEST qubits-per-logical
      we can achieve?  (measured: sweep torus shapes)
  Q2  Is there any room left in 2D?  (theorem: Bravyi-Poulin-Terhal 2010 —
      any 2D local code needs n = Omega(d^2), so the surface code is optimal)
  Q3  What do the codes that DO beat it look like?  (hyperbolic: constant rate
      but d ~ log n; qLDPC: constant rate, ~13 physical per logical)

Nothing here attacks anything. It is a rate comparison.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/sudosudo/qverify/lab")
from qec_5402_probe import Toric, gf2_rank      # noqa: E402

HERE = Path(__file__).resolve().parent
rows = []


def rate(Lx, Ly):
    """n/k for a torus, computed from its own stabilizer matrix."""
    tc = Toric(Lx, Ly)
    stars, plaqs = tc.generators()
    rs = len(gf2_rank([x for x, _ in stars]))
    rp = len(gf2_rank([z for _, z in plaqs]))
    k = tc.n - rs - rp
    return {"Lx": Lx, "Ly": Ly, "n": tc.n, "k": k, "d": min(Lx, Ly),
            "phys_per_logical": tc.n / k}


print("=" * 78)
print("SPIKE — HOW GOOD CAN A LATTICE CODE GET?")
print("=" * 78)

print("\nQ1. best qubits-per-logical inside our Euclidean torus family")
print(f"  {'lattice':>10} {'n':>6} {'k':>3} {'d':>4} {'phys/logical':>13}")
shapes = [(3, 3), (5, 5), (8, 8), (12, 12), (20, 20), (37, 37), (37, 73)]
for (Lx, Ly) in shapes:
    r = rate(Lx, Ly)
    rows.append(r)
    print(f"  {Lx}x{Ly:<8} {r['n']:>6} {r['k']:>3} {r['d']:>4} "
          f"{r['phys_per_logical']:>13.0f}")
# best rate AT A GIVEN DISTANCE (apples to apples): for each d, the minimum
# phys/logical over all shapes with that d
by_d = {}
for r in rows:
    by_d.setdefault(r["d"], []).append(r)
best_at_d = {d: min(v, key=lambda r: r["phys_per_logical"])
             for d, v in by_d.items()}

print("\n  best rate AT EACH DISTANCE (square wins: d^2 per logical):")
for d in sorted(best_at_d):
    b = best_at_d[d]
    print(f"    d={d:>3}: {b['Lx']}x{b['Ly']} -> "
          f"{b['phys_per_logical']:.0f} physical/logical "
          f"(d^2 = {d * d})")
best = best_at_d[max(best_at_d)]          # the largest distance we measured
print(f"\n  at d={best['d']} the best 2D shape is {best['Lx']}x{best['Ly']} at "
      f"{best['phys_per_logical']:.0f} physical per logical "
      f"(d^2 = {best['d'] ** 2}).")

ours = next(r for r in rows if r["Lx"] == 37 and r["Ly"] == 73)
square = best_at_d[37]
print(f"\n  OUR lattice 37x73: {ours['phys_per_logical']:.0f} physical/logical")
print(f"  a SQUARE 37x37 torus gives the SAME k={square['k']} and d="
      f"{square['d']} with {square['n']} qubits")
print(f"  -> our rectangular choice is {ours['n'] / square['n']:.1f}x worse "
      f"than the best 2D shape at the same protection.")

print("\nQ2. is there any room left in 2D?")
print("  Bravyi-Poulin-Terhal, PRL 104, 050503 (2010), arXiv:0909.5200:")
print("  any 2D local code with distance d needs n = Omega(d^2) physical")
print("  qubits. The surface code ACHIEVES that bound, so within 2D Euclidean")
print("  geometry our family is already optimal — there is nothing to gain.")
print(f"  Measured: our best d={best['d']} code uses "
      f"{best['phys_per_logical']:.0f} = d^2 physical per logical.")

print("\nQ3. what beats it, and at what cost?")
print("  hyperbolic surface codes (Zemor 2009; Breuckmann-Terhal):")
print("    constant rate k/n, BUT d ~ log n  ->  n ~ exp(c*d): exponentially")
print("    worse for a FIXED distance. Not a route to d~256.")
print("  quantum LDPC codes (non-local stabilizers, e.g. Q102):")
print("    constant rate AND constant relative distance.")
ldpc_phys, ldpc_logical = 19397, 1457
print(f"    published ECDLP machine: {ldpc_phys:,} physical / "
      f"{ldpc_logical:,} logical = {ldpc_phys / ldpc_logical:.1f} per logical")
print(f"    vs our best 2D lattice: {best['phys_per_logical']:.0f} per logical "
      f"-> {best['phys_per_logical'] / (ldpc_phys / ldpc_logical):.0f}x worse")

verdict = {
    "best_2d_lattice_rate": best["phys_per_logical"],
    "best_2d_lattice": f"{best['Lx']}x{best['Ly']}",
    "our_lattice_rate": ours["phys_per_logical"],
    "square_same_protection_rate": square["phys_per_logical"],
    "our_choice_penalty": ours["n"] / square["n"],
    "qldpc_rate": ldpc_phys / ldpc_logical,
    "gap_to_qldpc": best["phys_per_logical"] / (ldpc_phys / ldpc_logical),
    "two_d_bound": "n = Omega(d^2) for any 2D local code (BPT 2010)",
    "hyperbolic": "constant rate but d ~ log n (exponential n for fixed d)",
}
print("\n" + "=" * 78)
for k, v in verdict.items():
    print(f"  {k}: {v}")
print("=" * 78)
(HERE / "verdict.json").write_text(json.dumps(verdict, indent=2) + "\n")
print(f"\nwrote {HERE / 'verdict.json'}")
