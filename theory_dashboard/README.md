# Theory of Things — Interactive Prediction Workbench

A self-contained, offline dashboard that turns the equations from the two REDΣ
Research documents into adjustable forecasts:

- [The Theory of Things That Are](https://github.com/chadcoulter/REDE-3iAtlas-Signal-Processing/blob/main/The_Theory_of_Things_That_Are.md)
- [The Theory of Things That Are Not](https://github.com/chadcoulter/REDE-3iAtlas-Signal-Processing/blob/main/The_Theory_of_Things_That_Are_Not.md)

No build step, no dependencies, no network. Open `index.html` in a browser
(double-click it, or `python3 -m http.server` in this directory and visit
`http://localhost:8000`).

## Modules

| # | Module | What it forecasts | Core equations |
|---|--------|-------------------|----------------|
| 1 | Enthalpic N+1 | State trajectory, induced counterforce, reversal points, enthalpy | `x[N+1]=x[N]+u[N]+f(x,u)`, `f=-(k₁x+k₂x\|x\|+k₃ux)`, `H=U+PV` |
| 2 | Entropic Polarity | Concentration/generation poles, polarity oscillation, reversal through Ω | `E_C=+E`, `E_G=-E`, `\|E_C\|=\|E_G\|`, `polarity=(c-g)/(c+g)` |
| 3 | Extraction / Synergy | Resource stock, extraction value, sustainability, synergy, collapse | `R[N+1]=R+ρR(1-R/K)-C-E`, `E=(price-cost)·E`, `S=regen-C`, `Y=s(V(A)+V(B))` |
| 4 | Knowledge & Observation | Alignment/differential coefficients, unit circle, parallax resolution | `C_K=cosθ`, `S_K=sinθ`, `C_K²+S_K²=1`, `δ≈B/D`, `resolved ⇔ δ>ε` |
| 5 | Projection / Reflection | Iterated knowledge direction and magnitude, coherence | `K[N+1]=F(P(K[N]),K[N])`, `coherence=cosΔθ` |
| 6 | Realization vs Projection | Realized state vs model projection, resolution difference, Monte Carlo band | `x[N+1]=x+u+f_true+η`, `x̂[N+1]=x+u+f_model+bias`, `δ=x-x̂` |

Every slider recomputes immediately. Red dots mark reversal points. Hover any
chart for a per-step readout. Each panel has presets and an **Export CSV**
button. All randomness is seeded, so a given parameter set reproduces exactly.

## Files

- `index.html` — page and panel layout
- `styles.css` — theme
- `model.js` — pure mathematics (shared by browser and Node)
- `app.js` — controls, charts, tabs, export, self-test
- `verify.js` — Node model tests
- `verify_ui.cjs` — Node UI-layer tests (DOM stub)
- `fixture.js` — fixed simulation fixture for cross-language checking
- `verify.py` — independent Python reimplementation + harness runner

## Verification (executed)

```
node verify.js          -> 27/27 passed
node verify_ui.cjs      -> 41/41 passed
python3 verify.py       -> 14/14 passed   (incl. element-by-element JS-vs-Python recurrence match)
in-browser self-test    -> 16/16 passed
Playwright load         -> all 6 tabs render, slider/preset recompute, 0 console errors, 0 page errors
canvas pixel check      -> every visible chart has drawn content
```

Run them yourself:

```bash
cd theory_dashboard
node verify.js
node verify_ui.cjs
python3 verify.py
```

## Scope note

The dashboard is a deterministic simulation of the relationships stated in the
two documents. The parameters are user-selected; the outputs are forecasts of
those equations, not empirical measurements. Module 6 is the practical
statement of the second paper: the resolution difference `δ` measures the
model's failure to determine the realized state — it does not assert that the
realized state is itself incomplete.
