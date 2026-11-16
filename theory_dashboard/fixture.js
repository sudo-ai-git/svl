/* Prints a fixed simulation fixture as JSON so verify.py can cross-check the
 * JavaScript model against an independent Python reimplementation. */
'use strict';
const T = require('./model.js');
const phys = T.nPlusOne({
  x0: 1, u0: 1, uAmp: 0.5, uFreq: 0.03, uPhase: 0.2,
  k1: 0.2, k2: 0.01, k3: 0.05, U0: 5, alphaU: 0.3, P0: 2, V0: 3, horizon: 60
});
const pred = T.prediction({
  x0: 0, u0: 1, k1t: 0.08, k2t: 0.001, k1m: 0.08, k2m: 0.001,
  bias: 0, noise: 0.5, horizon: 50, seed: 42
});
console.log(JSON.stringify({
  x: phys.x, u: phys.u, f: phys.f, H: phys.H, rev: phys.rev,
  px: pred.x, delta: pred.d, eta: pred.eta
}));
