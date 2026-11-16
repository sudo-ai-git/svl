/* Node verification harness for model.js — run: node verify.js */
'use strict';
const TOT = require('./model.js');

let pass = 0, fail = 0;
const failures = [];
function chk(name, cond, detail) {
  if (cond) { pass++; console.log('PASS  ' + name + (detail ? '  [' + detail + ']' : '')); }
  else { fail++; failures.push(name + (detail ? '  [' + detail + ']' : '')); console.log('FAIL  ' + name + (detail ? '  [' + detail + ']' : '')); }
}
function near(a, b, tol) { return Math.abs(a - b) <= (tol == null ? 1e-9 : tol); }

/* knowledge coefficients */
{
  const kn = TOT.knowledge(35, 2.5);
  chk('C_K^2 + S_K^2 = 1', near(kn.CK ** 2 + kn.SK ** 2, 1, 1e-12), String(kn.CK ** 2 + kn.SK ** 2));
  chk('k^2 = Kpar^2 + Kperp^2', near(kn.magnitude ** 2, kn.Kpar ** 2 + kn.Kperp ** 2, 1e-12),
    String(kn.magnitude ** 2 - (kn.Kpar ** 2 + kn.Kperp ** 2)));
  const k0 = TOT.knowledge(0, 4);
  chk('theta=0 -> C_K=1, S_K=0', near(k0.CK, 1) && near(k0.SK, 0), k0.CK + ',' + k0.SK);
  const k90 = TOT.knowledge(90, 4);
  chk('theta=90 -> C_K=0, S_K=1', near(k90.CK, 0, 1e-12) && near(k90.SK, 1), k90.CK + ',' + k90.SK);
}

/* observational geometry */
{
  const r = TOT.resolution(2, 50, 0.01);
  chk('delta = B/D', near(r.delta, 0.04, 1e-12), String(r.delta));
  chk('resolved iff delta > epsilon', r.resolved === (r.delta > r.epsilon), String(r.resolved));
  chk('unresolved case', TOT.resolution(0.25, 50, 0.01).resolved === false, 'delta=0.005 < eps=0.01');
  chk('H = U + PV', TOT.enthalpy(3, 4, 5) === 23, String(TOT.enthalpy(3, 4, 5)));
}

/* N+1 engine */
{
  const p = { x0: 1, u0: 1, uAmp: 0.5, uFreq: 0.03, uPhase: 0.2, k1: 0.2, k2: 0.01, k3: 0.05, U0: 5, alphaU: 0.3, P0: 2, V0: 3, horizon: 60 };
  const r = TOT.nPlusOne(p);
  let trans = true, rev = true, ent = true;
  for (let n = 0; n < r.N; n++) {
    const u = r.u[n];
    const f = -(p.k1 * r.x[n] + p.k2 * r.x[n] * Math.abs(r.x[n]) + p.k3 * u * r.x[n]);
    if (!near(r.x[n + 1], r.x[n] + u + f, 1e-9)) trans = false;
    const expect = Math.abs(u) > 1e-12 && Math.abs(r.x[n + 1] - r.x[n]) > 1e-12 &&
      TOT.sign(r.x[n + 1] - r.x[n]) !== TOT.sign(u);
    if (r.rev[n] !== expect) rev = false;
  }
  for (let n = 0; n <= r.N; n++) if (!near(r.H[n], r.U[n] + p.P0 * p.V0, 1e-9)) ent = false;
  chk('x[N+1] = x[N] + u[N] + f(x,u)', trans, r.N + ' transitions');
  chk('reversal flag = sign(dx) != sign(u)', rev, r.N + ' flags');
  chk('H[N] = U[N] + P0*V0', ent, r.N + ' values');
  const revCount = r.rev.filter(Boolean).length;
  chk('reversal count is a non-negative integer', Number.isInteger(revCount) && revCount >= 0, String(revCount));
}

/* polarity */
{
  const r = TOT.polarity({ c0: 60, g0: 40, u0: 1, gamma: 0.3, kappa: 0.05, noise: 0, seed: 7, horizon: 60 });
  chk('c + g conserved', near(r.c[0] + r.g[0], r.total, 1e-9), String(r.c[0] + r.g[0]) + ' -> ' + r.total);
  chk('|E_C| = |E_G|', r.EC.every((e, i) => near(Math.abs(e), Math.abs(r.EG[i]), 1e-12)), 'all N');
  chk('E_C = -E_G', r.EC.every((e, i) => near(e, -r.EG[i], 1e-12)), 'all N');
  const noisy = TOT.polarity({ c0: 60, g0: 40, u0: 1, gamma: 0.3, kappa: 0.05, noise: 1.5, seed: 7, horizon: 60 });
  chk('noise changes the trajectory', JSON.stringify(noisy.c) !== JSON.stringify(r.c), 'seeded and reproducible');
  const noisy2 = TOT.polarity({ c0: 60, g0: 40, u0: 1, gamma: 0.3, kappa: 0.05, noise: 1.5, seed: 7, horizon: 60 });
  chk('same seed -> same noisy trajectory', JSON.stringify(noisy.c) === JSON.stringify(noisy2.c), '');
}

/* economy */
{
  const p = { stock0: 500, K: 1000, rho: 0.2, consumption: 50, extraction: 100, price: 2, cost: 1, synergy: 0.15, horizon: 40 };
  const r = TOT.economy(p);
  let ok = true;
  for (let n = 0; n < r.N; n++) {
    if (!near(r.Y[n], p.synergy * (r.E[n] + r.S[n]), 1e-9)) ok = false;
    if (r.R[n] < -1e-12) ok = false;
    const rg = p.rho * r.R[n] * (1 - r.R[n] / p.K);
    if (!near(r.R[n + 1], Math.max(0, r.R[n] + rg - r.cons[n] - r.ex[n]), 1e-9)) ok = false;
  }
  chk('Y = s*(V(A)+V(B)); stock update; R >= 0', ok, r.N + ' steps');
  const collapse = TOT.economy({ stock0: 500, K: 1000, rho: 0.1, consumption: 50, extraction: 200, price: 2, cost: 1, synergy: 0, horizon: 60 });
  chk('extraction collapse drives stock to floor', collapse.R[60] <= 1e-9, String(collapse.R[60]));
}

/* projection / reflection */
{
  const r = TOT.knowledgeIteration({ theta0: 35, k0: 1, proj: 1, projAngle: 0, refl: 1, reflAngle: 0, iterations: 30 });
  chk('identity iteration preserves direction', near(r.xs[0], r.xs[r.N], 1e-9) && near(r.ys[0], r.ys[r.N], 1e-9), String(r.thetaFinal));
  chk('unit-circle path stays on circle', r.xs.every((c, i) => near(c * c + r.ys[i] * r.ys[i], 1, 1e-9)), 'all points');
  const g = TOT.knowledgeIteration({ theta0: 0, k0: 1, proj: 1.1, projAngle: 0, refl: 1, reflAngle: 0, iterations: 10 });
  chk('projection scales magnitude', near(g.mags[10], 1.1 ** 10, 1e-9), String(g.mags[10]));
}

/* prediction */
{
  const p = { x0: 0, u0: 1, k1t: 0.08, k2t: 0.001, k1m: 0.08, k2m: 0.001, bias: 0, noise: 0.5, horizon: 50, seed: 42 };
  const a = TOT.prediction(p);
  const b = TOT.prediction(p);
  chk('same seed -> identical forecast', JSON.stringify(a.x) === JSON.stringify(b.x), a.N + ' steps');
  let dOk = true;
  for (let n = 1; n <= a.N; n++) {
    const fT = -(p.k1t * a.x[n - 1] + p.k2t * a.x[n - 1] * Math.abs(a.x[n - 1]));
    const fM = -(p.k1m * a.x[n - 1] + p.k2m * a.x[n - 1] * Math.abs(a.x[n - 1]));
    if (!near(a.d[n], fT + a.eta[n - 1] - fM, 1e-9)) dOk = false;
  }
  chk('delta[N] = f_true(x) + eta - f_model(x)', dOk, a.N + ' steps');
  const m = TOT.prediction({ ...p, k1m: 0.2, k2m: 0.005, bias: 0.3 });
  chk('model mismatch changes projection', JSON.stringify(m.xh) !== JSON.stringify(a.xh), '');
  const mc = TOT.monteCarlo({ ...p, runs: 25 });
  chk('MC band ordered', mc.p5.every((v, i) => v <= mc.p95[i]), mc.M + ' runs');
  chk('MC deterministic', JSON.stringify(TOT.monteCarlo({ ...p, runs: 25 }).mean) === JSON.stringify(mc.mean), '');
}

console.log('\nTOTAL: ' + pass + '/' + (pass + fail) + ' passed');
if (fail) { console.log('FAILURES:\n' + failures.join('\n')); process.exit(1); }
