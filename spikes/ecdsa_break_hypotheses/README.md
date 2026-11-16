# Spike: ten hypotheses for breaking ECDSA-256 with what we have

**Question.** Can we reach a cryptographically-relevant quantum break of
secp256k1 (the curve behind ECDSA-256 / Bitcoin) with the assets in this
workspace — a verified `[[5402,2,37]]` toric code, a photonic linear-optical
simulator, a QEC harness, and verified secp256k1 arithmetic?

**Method.** Ten hypotheses, risk-ordered (the ones most likely to kill the idea
first). Each is decomposed into one measurable question and tested. Two are
built for real; the rest die on arithmetic. Verdicts are
VALIDATED / PARTIAL / INVALIDATED.

**Run:**

```
python spike_ecdsa_hypotheses.py
```

**Scope and ethics.** Nothing here attacks a third party. H7 uses a keypair
generated inside the process; it exists to demonstrate why nonce reuse is fatal.
The published resource numbers are quoted, with sources listed at the bottom.

---

## Results

| # | Hypothesis | Verdict | Decisive evidence |
|---|---|---|---|
| H1 | Tile our tori for logical capacity | **INVALIDATED** | 2,701 physical per logical → 1,457 logical needs **3,935,357** physical for data alone |
| H2 | Use quantum LDPC codes | **VALIDATED** (not ours) | 13.3 physical per logical vs our 2,701 — **203×** better; needs hardware we lack |
| H3 | Better decoder | **INVALIDATED** | decoder changes error rate/runtime, not the qubit count |
| H4 | More distance | **INVALIDATED** | d=145 costs ~2d² = 42,050 physical per logical — wrong direction |
| H5 | Better magic-state factories | **PARTIAL** | drives runtime and qubits, but needs hardware; the big win came from the code |
| H6 | Classical Pollard rho | **INVALIDATED** | 2¹²⁸ ops ≈ 1.1e19 years at an absurd 1e12 ops/s |
| H7 | Nonce reuse (classical) | **VALIDATED** | recovered the private key exactly from two signatures sharing a nonce; distinct nonces give a wrong key |
| H8 | Shor at small scale | **VALIDATED** small / **INVALIDATED** at scale | simulated circuit returned r=4 (true order); 1,457 logical qubits and 26 days vs our 2 |
| H9 | Fewer Toffolis (58M→39M) | **PARTIAL** | 33% fewer gates cuts runtime, not qubits |
| H10 | Repeat attempts to 95% | **PARTIAL** | 6 attempts (p=40.7%) ≈ 154 days; 3 (p=63.3%) ≈ 77 days |

**Summary: 3 validated (one of them "not ours"), 3 partial, 4 invalidated.**

---

## What the two real builds showed

**H7 — nonce reuse.** Two ECDSA signatures made with the same nonce `k` give
`k = (h1 − h2)/(s1 − s2)` and then `d = (s1·k − h1)/r`. Built on verified
secp256k1 arithmetic; the private key was recovered exactly, and a control with
distinct nonces produced a wrong key. **This is the route that breaks ECDSA in
practice today, and it needs no quantum computer.**

**H8 — Shor period finding.** A statevector simulation of the order-finding
circuit for `N=15, a=7` (8-bit control register) recovered the true order
`r=4`. Two bugs were found and fixed while building it, both instructive:
taking the *first* continued-fraction candidate returned 12 (a multiple of the
order) instead of 4 — the post-processing must take the **minimum** admitted
period; and reading the y=0 column instead of the first register's marginal
gave a meaningless distribution.

---

## The honest conclusion

The quantum route is **not closed by physics** — it is closed for us by
**qubit efficiency and engineering**. The published state of the art is 1,457
logical qubits in 19,397 physical qubits (13.3 per logical) using quantum LDPC
codes; our lattice delivers 2 logical qubits in 5,402 physical (2,701 per
logical). Closing that 203× gap is a code-family and hardware problem, and the
remaining runtime is 26 days per attempt.

If the goal is "break ECDSA-256", the only route demonstrated end-to-end here
is **classical and non-quantum**: nonce reuse. That is a demonstration on a
self-generated key, not an attack on any real target.

---

## Sources (quoted, not independently recomputed)

- Roetteler, Naehrig, Svore, Lauter (Microsoft Research, 2017),
  *Quantum Resource Estimates for Computing Elliptic Curve Discrete Logarithms*,
  arXiv:1706.06752 — `9n + 2⌈log2 n⌉ + 10` qubits, giving 2330 at n=256.
- Häner, Tripier, Young, Naehrig, …, Roetteler (IonQ, Sep 2026),
  *Computing 256-bit elliptic curve discrete logarithms in 26 days on a
  fault-tolerant trapped-ion quantum computer with 20,000 qubits* — 1457 logical
  qubits, 39M Toffoli gates, 19,397 physical qubits, 25.7 days, success
  40.7%–63.3%.
- A 2019 surface-code figure ("296 million physical qubits") was deliberately
  **omitted**: it could not be confirmed from the sources reachable here.

The arithmetic in H1–H6, H9, H10 uses only those quoted numbers and is shown in
the script so it can be re-checked.
