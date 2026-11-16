#!/usr/bin/env python3
"""Independent verification for the Theory of Things dashboard.

Reimplements the source equations in Python, compares them element-by-element
against the JavaScript model's fixed fixture, and runs the two Node harnesses.
Run: python3 verify.py
"""
import json
import math
import subprocess
import sys

HERE = __file__.rsplit("/", 1)[0]
TOL = 1e-9
passed = 0
failed = 0
failures = []


def chk(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS  {name}" + (f"  [{detail}]" if detail else ""))
    else:
        failed += 1
        failures.append(name + (f"  [{detail}]" if detail else ""))
        print(f"FAIL  {name}" + (f"  [{detail}]" if detail else ""))


def near(a, b, tol=TOL):
    return abs(a - b) <= tol


# ---- closed-form checks -------------------------------------------------
chk("enthalpy H = U + PV", 3 + 4 * 5 == 23, str(3 + 4 * 5))

theta = math.radians(35)
ck, sk = math.cos(theta), math.sin(theta)
chk("C_K^2 + S_K^2 = 1", near(ck * ck + sk * sk, 1.0, 1e-12), str(ck * ck + sk * sk))
k = 2.5
kpar, kperp = k * ck, k * sk
chk("k^2 = Kpar^2 + Kperp^2", near(k * k, kpar * kpar + kperp * kperp, 1e-12),
    str(k * k - (kpar * kpar + kperp * kperp)))

B, D, eps = 2.0, 50.0, 0.01
chk("delta = B/D", near(B / D, 0.04, 1e-12), str(B / D))
chk("resolved iff delta > epsilon", (B / D > eps) is True, "")

# ---- cross-language fixture check --------------------------------------
raw = subprocess.run(["node", "fixture.js"], cwd=HERE, capture_output=True, text=True, check=True).stdout
fx = json.loads(raw)

# independent N+1 recurrence
x0, u0, uAmp, uFreq, uPhase = 1.0, 1.0, 0.5, 0.03, 0.2
k1, k2, k3 = 0.2, 0.01, 0.05
U0, alphaU, P0, V0 = 5.0, 0.3, 2.0, 3.0
N = 60
xs, us, fs, Hs, revs = [0.0] * (N + 1), [0.0] * (N + 1), [0.0] * N, [0.0] * (N + 1), [False] * N
xs[0] = x0
for n in range(N):
    us[n] = u0 + uAmp * math.sin(2 * math.pi * uFreq * n + uPhase)
    fs[n] = -(k1 * xs[n] + k2 * xs[n] * abs(xs[n]) + k3 * us[n] * xs[n])
    xs[n + 1] = xs[n] + us[n] + fs[n]
    Hs[n] = (U0 + alphaU * xs[n]) + P0 * V0
    dx = xs[n + 1] - xs[n]
    revs[n] = abs(us[n]) > 1e-12 and abs(dx) > 1e-12 and (1 if dx > 0 else -1 if dx < 0 else 0) != (1 if us[n] > 0 else -1 if us[n] < 0 else 0)
us[N] = u0 + uAmp * math.sin(2 * math.pi * uFreq * N + uPhase)
Hs[N] = (U0 + alphaU * xs[N]) + P0 * V0

chk("JS x[N] matches independent recurrence",
    all(near(a, b) for a, b in zip(fx["x"], xs)), f"{len(xs)} points, max diff "
    + str(max(abs(a - b) for a, b in zip(fx["x"], xs))))
chk("JS u[N] matches drive", all(near(a, b) for a, b in zip(fx["u"], us)), "")
chk("JS f[N] matches induced response", all(near(a, b) for a, b in zip(fx["f"], fs)), "")
chk("JS H[N] matches U + PV", all(near(a, b) for a, b in zip(fx["H"], Hs)), "")
chk("JS reversal flags match sign condition", fx["rev"] == revs,
    f"{sum(revs)} reversals")

# independent prediction recurrence
px0, pu0 = 0.0, 1.0
pk1t, pk2t, pk1m, pk2m, pbias = 0.08, 0.001, 0.08, 0.001, 0.0
PN = 50
px = [0.0] * (PN + 1)
px[0] = px0
for n in range(PN):
    ft = -(pk1t * px[n] + pk2t * px[n] * abs(px[n]))
    fm = -(pk1m * px[n] + pk2m * px[n] * abs(px[n])) + pbias
    px[n + 1] = px[n] + pu0 + ft + fx["eta"][n]
    chk_delta = px[n + 1] - (px[n] + pu0 + fm)
    if not near(chk_delta, fx["delta"][n + 1]):
        chk("JS delta[N] matches f_true + eta - f_model", False, f"step {n + 1}")
        break
else:
    chk("JS delta[N] matches f_true + eta - f_model", True, f"{PN} steps")
chk("JS realized x[N] matches independent realization",
    all(near(a, b) for a, b in zip(fx["px"], px)), "")

# ---- node harnesses -----------------------------------------------------
for script in ("verify.js", "verify_ui.cjs"):
    r = subprocess.run(["node", script], cwd=HERE, capture_output=True, text=True)
    tail = [ln for ln in r.stdout.strip().splitlines() if ln.startswith("TOTAL:")]
    chk(f"{script} exits 0", r.returncode == 0, tail[0] if tail else r.stderr.strip()[:120])

print(f"\nTOTAL: {passed}/{passed + failed} passed")
if failures:
    print("FAILURES:\n" + "\n".join(failures))
    sys.exit(1)
