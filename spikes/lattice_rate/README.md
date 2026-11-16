# Spike: how good can a lattice code get, really?

**Question (Jack's challenge).** "You won't know till you try — we have an
annulus, an error-correcting code, lattices. It must be possible."

So this spike **tries** instead of asserting. Three sub-questions:

- **Q1** — within our Euclidean lattice family, what is the best
  physical-qubits-per-logical we can achieve? *(measured)*
- **Q2** — is there any room left in 2D? *(a theorem, quoted)*
- **Q3** — what beats it, and at what cost? *(quoted + arithmetic)*

**Run:** `python spike_lattice_rate.py`

---

## Q1 — measured: the square wins, and our rectangle is 2× off

| lattice | n | k | d | physical per logical |
|---|---|---|---|---|
| 3×3 | 18 | 2 | 3 | 9 |
| 5×5 | 50 | 2 | 5 | 25 |
| 8×8 | 128 | 2 | 8 | 64 |
| 12×12 | 288 | 2 | 12 | 144 |
| 20×20 | 800 | 2 | 20 | 400 |
| **37×37** | **2,738** | **2** | **37** | **1,369** |
| 37×73 (ours) | 5,402 | 2 | 37 | 2,701 |

`n/k = Lx·Ly` and `d = min(Lx,Ly)`, so at a **fixed distance the square lattice
is optimal**, at exactly `d²` physical qubits per logical.

**Concrete finding: our 37×73 rectangle is 2.0× worse than a square 37×37 torus
at the same k and the same d.** Same two logical qubits, same distance 37 —
2,738 qubits instead of 5,402. That is a free factor of two we left on the
table by choosing a rectangle.

## Q2 — there is no room left in 2D

**Bravyi, Poulin, Terhal, PRL 104, 050503 (2010), arXiv:0909.5200:** any 2D
local code with distance `d` needs `n = Ω(d²)` physical qubits. The surface
code *achieves* that bound.

Our measurement lands exactly on it: at d=37 the best shape uses
1,369 = 37² physical per logical. So within 2D Euclidean geometry this family
is **provably optimal** — no lattice trick, no annulus trick, no reshaping can
beat `d²` while the stabilizers stay local and 2D.

## Q3 — what beats it, and why it is not a lattice trick

| family | rate | distance behaviour |
|---|---|---|
| 2D surface/toric (ours) | 1 logical per d² physical | optimal in 2D (BPT) |
| hyperbolic surface codes (Zémor 2009; Breuckmann–Terhal) | **constant rate** k/n | **d ~ log n** → `n ~ exp(c·d)`: exponentially worse at a *fixed* distance |
| quantum LDPC (non-local stabilizers, e.g. Q102) | **constant rate and constant relative distance** | ~13.3 physical per logical in the published ECDLP machine |

The hyperbolic route is the tempting one — constant rate sounds like the win —
but its distance only grows logarithmically, so hitting `d ≈ 256` costs
exponentially many qubits. It trades one wall for a worse one.

The route that actually works abandons locality: quantum LDPC codes have
constant rate **and** constant relative distance, at ~**13.3 physical qubits
per logical** versus our best 2D **1,369** — a **103×** gap.

---

## Spike 2 — `spike_kd2.py`: `n = k·d²` is an invariant, and our rectangle is dominated

Spike 1 found the square torus uses exactly `d²` per logical. Spike 2 tests
whether that is an **invariant**, and then maps the frontier.

**`c = n/(k·d²)` measured:**

| lattice | n | k | d | c |
|---|---|---|---|---|
| 3×3 … 37×37 (all squares) | 18 … 2,738 | 2 | 3 … 37 | **1.000** |
| 3×5 | 30 | 2 | 3 | 1.667 |
| 5×12 | 120 | 2 | 5 | 2.400 |
| 8×20 | 320 | 2 | 8 | 2.500 |
| **37×73 (ours)** | 5,402 | 2 | 37 | **1.973** |

- **Every square torus has `c = 1` exactly** — the Bravyi–Poulin–Terhal 2D bound
  `n = Ω(d²)` saturated. It is an invariant, not a coincidence.
- A rectangle has `c = Lx·Ly / min(Lx,Ly)²` — pure aspect-ratio waste. Our
  37×73 measures **1.973**, i.e. it is *no better per logical qubit than a planar
  code*, because the rectangle throws away the torus's second logical qubit.
- **Any number of square tori keeps `c = 1`** (m=1,2,3,5,8 measured): k scales,
  c does not.

**The frontier at a fixed budget of 5,402 qubits** (the real engineering
question — what does this hardware buy me?):

| m tori | L | n used | k | d |
|---|---|---|---|---|
| 1 | 51 | 5,202 | 2 | **51** |
| 2 | 36 | 5,184 | 4 | 36 |
| 3 | 30 | 5,400 | 6 | 30 |
| 4 | 25 | 5,000 | 8 | 25 |
| 8 | 18 | 5,184 | **16** | 18 |

**With the same 5,402 qubits, a single square 51×51 torus gives d=51 instead of
our 37 — 40% more distance — and eight 18×18 tori give k=16 instead of our 2.**
Our 37×73 choice is dominated on both axes.

**Note on the qLDPC comparison:** the BPT bound applies only to *local* codes,
so the quantum-LDPC machine is not "beating" it — it is outside its scope. Its
measured ratio is 13.3 physical per logical.

## Verdict

- **PARTIAL.** Jack was right that testing beats asserting: the test found a
  free **2×** — our rectangle should have been a square.
- **INVALIDATED as a path to ECDLP-256.** The 2D lattice family is at its
  provable optimum (`n = Ω(d²)`), and the only families that beat it are
  non-local (qLDPC) or exponentially worse in distance (hyperbolic).
- The gap that matters is **103×** (1,369 vs 13.3), and no rearrangement of the
  lattice closes it.

**What to do with the finding:** if the lattice is ever used for storage, use
the square `d×d` shape, not the rectangle. The 37×73 choice was justified by
the 231-gate dimensions, not by coding efficiency — and it costs 2× for nothing.

## Sources

- Bravyi, Poulin, Terhal, PRL 104, 050503 (2010), arXiv:0909.5200 — 2D lower
  bound `n = Ω(d²)`.
- Zémor (2009); Breuckmann–Terhal — hyperbolic surface codes: constant rate,
  `d ~ log n` (as summarised in the BPT paper's discussion of non-Euclidean
  geometry).
- Häner et al. (IonQ), Sep 2026 — quantum LDPC (Q102) ECDLP machine: 1,457
  logical qubits, 19,397 physical, 25.7 days.
