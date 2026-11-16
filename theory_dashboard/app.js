/* ============================================================================
 * Theory of Things — interactive prediction workbench
 * UI layer. All mathematics lives in model.js (window.TOT).
 * ========================================================================== */
(function () {
  'use strict';

  var TOT = window.TOT;

  /* ------------------------------------------------------------------ utils */
  function mean(a) {
    if (!a.length) return NaN;
    var s = 0;
    for (var i = 0; i < a.length; i++) s += a[i];
    return s / a.length;
  }
  function rmse(a) {
    if (!a.length) return NaN;
    var s = 0;
    for (var i = 0; i < a.length; i++) s += a[i] * a[i];
    return Math.sqrt(s / a.length);
  }
  function sum(a) {
    var s = 0;
    for (var i = 0; i < a.length; i++) s += a[i];
    return s;
  }
  function fmt(v) {
    if (v == null || !isFinite(v)) return '—';
    if (Object.is(v, -0)) v = 0;
    var a = Math.abs(v);
    if (a >= 1000) return v.toFixed(1);
    if (a >= 1) return v.toFixed(3);
    if (a >= 0.001) return v.toFixed(5);
    return v.toExponential(2);
  }
  function fmtInt(v) { return String(Math.round(v)); }
  function decimalsFor(step) {
    if (step >= 1) return 0;
    var s = String(step), i = s.indexOf('.');
    return i < 0 ? 0 : Math.min(6, s.length - i - 1);
  }
  function pctDecimal(v) {
    if (!isFinite(v)) return '—';
    if (Math.abs(v) < 0.001) return v.toExponential(2);
    return v.toFixed(5);
  }

  /* ------------------------------------------------------------- canvas core */
  function setupCanvas(canvas) {
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.clientWidth || 600;
    var h = canvas.clientHeight || 260;
    canvas.width = Math.max(1, Math.round(w * dpr));
    canvas.height = Math.max(1, Math.round(h * dpr));
    var ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx: ctx, w: w, h: h };
  }

  function drawLineChart(canvas, opts) {
    var s = setupCanvas(canvas), ctx = s.ctx, w = s.w, h = s.h;
    var pad = { l: 58, r: 16, t: 24, b: 32 };
    var iw = Math.max(10, w - pad.l - pad.r);
    var ih = Math.max(10, h - pad.t - pad.b);
    var series = (opts.series || []).filter(function (q) { return q.data && q.data.length; });
    var ymin = Infinity, ymax = -Infinity, n = 1;
    series.forEach(function (q) {
      n = Math.max(n, q.data.length);
      q.data.forEach(function (v) {
        if (isFinite(v)) { if (v < ymin) ymin = v; if (v > ymax) ymax = v; }
      });
    });
    if (!isFinite(ymin)) { ymin = 0; ymax = 1; }
    if (ymin === ymax) { ymin -= 1; ymax += 1; }
    var span = ymax - ymin;
    ymin -= span * 0.08; ymax += span * 0.08;

    function X(i) { return pad.l + (n <= 1 ? 0 : (i / (n - 1)) * iw); }
    function Y(v) { return pad.t + ((ymax - v) / (ymax - ymin)) * ih; }

    canvas._geom = { pad: pad, iw: iw, n: n };

    /* grid + axes */
    ctx.strokeStyle = '#232c40';
    ctx.fillStyle = '#8b93a7';
    ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace';
    ctx.lineWidth = 1;
    for (var g = 0; g <= 4; g++) {
      var gv = ymin + (ymax - ymin) * g / 4;
      var gy = Y(gv);
      ctx.beginPath(); ctx.moveTo(pad.l, gy); ctx.lineTo(w - pad.r, gy); ctx.stroke();
      ctx.textAlign = 'right';
      ctx.fillText(fmt(gv), pad.l - 6, gy + 3);
    }
    ctx.textAlign = 'center';
    var xstep = Math.max(1, Math.ceil(n / 8));
    for (var i = 0; i < n; i += xstep) ctx.fillText(String(i), X(i), h - pad.b + 16);
    if (opts.xLabel) { ctx.fillText(opts.xLabel, pad.l + iw / 2, h - 6); }
    if (opts.yLabel) {
      ctx.save(); ctx.translate(11, pad.t + ih / 2); ctx.rotate(-Math.PI / 2);
      ctx.textAlign = 'center'; ctx.fillText(opts.yLabel, 0, 0); ctx.restore();
    }

    /* series */
    series.forEach(function (q) {
      ctx.strokeStyle = q.color || '#5eead4';
      ctx.lineWidth = q.width || 1.6;
      ctx.setLineDash(q.dash || []);
      ctx.beginPath();
      var started = false;
      q.data.forEach(function (v, idx) {
        if (!isFinite(v)) { started = false; return; }
        var xx = X(idx), yy = Y(v);
        if (!started) { ctx.moveTo(xx, yy); started = true; } else ctx.lineTo(xx, yy);
      });
      ctx.stroke();
      ctx.setLineDash([]);
    });

    /* markers (reversal points etc.) */
    (opts.markers || []).forEach(function (m) {
      var idx = m.index;
      if (idx < 0 || idx >= n) return;
      var src = m.series != null ? series[m.series] : null;
      var v = src ? src.data[idx] : (m.value != null ? m.value : ymin);
      if (!isFinite(v)) return;
      ctx.fillStyle = m.color || '#f87171';
      ctx.beginPath(); ctx.arc(X(idx), Y(v), 3.2, 0, 2 * Math.PI); ctx.fill();
    });

    /* legend */
    var lx = pad.l + 4, ly = 12;
    ctx.textAlign = 'left';
    series.forEach(function (q) {
      ctx.fillStyle = q.color || '#5eead4';
      ctx.fillRect(lx, ly - 7, 12, 3);
      ctx.fillStyle = '#c7cede';
      ctx.fillText(q.name || '', lx + 16, ly - 2);
      lx += 16 + ctx.measureText(q.name || '').width + 14;
    });

    /* hover crosshair + readout */
    if (canvas._hover && canvas._geom) {
      var hi = canvas._hover.i;
      if (hi >= 0 && hi < n) {
        ctx.strokeStyle = '#4b5878';
        ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(X(hi), pad.t); ctx.lineTo(X(hi), h - pad.b); ctx.stroke();
        ctx.setLineDash([]);
        var lines = [String(hi)];
        series.forEach(function (q) {
          if (q.data[hi] != null && isFinite(q.data[hi])) lines.push((q.name || '') + '=' + fmt(q.data[hi]));
        });
        ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace';
        var bw = 0;
        lines.forEach(function (t) { bw = Math.max(bw, ctx.measureText(t).width); });
        bw += 10;
        var bx = Math.min(w - bw - 4, Math.max(4, canvas._hover.mx + 8));
        var by = Math.max(4, canvas._hover.my - 22);
        ctx.fillStyle = 'rgba(10,14,24,0.92)';
        ctx.fillRect(bx, by, bw, 12 + lines.length * 12);
        ctx.fillStyle = '#e6ebf7';
        ctx.textAlign = 'left';
        lines.forEach(function (t, k) { ctx.fillText(t, bx + 5, by + 11 + k * 12); });
      }
    }
  }

  function drawUnitCircle(canvas, opts) {
    var s = setupCanvas(canvas), ctx = s.ctx, w = s.w, h = s.h;
    var cx = w / 2, cy = h / 2, r = Math.min(w, h) / 2 - 28;
    ctx.strokeStyle = '#2a3348';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, 2 * Math.PI); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx - r, cy); ctx.lineTo(cx + r, cy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx, cy - r); ctx.lineTo(cx, cy + r); ctx.stroke();
    ctx.fillStyle = '#8b93a7';
    ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace';
    ctx.textAlign = 'center';
    ctx.fillText('+1', cx + r + 10, cy + 3);
    ctx.fillText('−1', cx - r - 10, cy + 3);
    ctx.fillText('+1', cx + 4, cy - r - 4);
    ctx.fillText('−1', cx + 4, cy + r + 12);
    ctx.fillText('cos θ (alignment)', cx, h - 6);
    ctx.save(); ctx.translate(10, cy); ctx.rotate(-Math.PI / 2);
    ctx.fillText('sin θ (differential)', 0, 0); ctx.restore();

    if (opts.path && opts.path.length) {
      ctx.strokeStyle = opts.pathColor || '#5eead4';
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      opts.path.forEach(function (p, i) {
        var X = cx + p.C * r, Y = cy - p.S * r;
        if (i) ctx.lineTo(X, Y); else ctx.moveTo(X, Y);
      });
      ctx.stroke();
    }
    (opts.vectors || []).forEach(function (v) {
      var X = cx + v.C * r, Y = cy - v.S * r;
      var ang = Math.atan2(Y - cy, X - cx);
      ctx.strokeStyle = v.color || '#fbbf24';
      ctx.fillStyle = ctx.strokeStyle;
      ctx.lineWidth = v.width || 2;
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(X, Y); ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(X, Y);
      ctx.lineTo(X - 8 * Math.cos(ang - 0.42), Y - 8 * Math.sin(ang - 0.42));
      ctx.lineTo(X - 8 * Math.cos(ang + 0.42), Y - 8 * Math.sin(ang + 0.42));
      ctx.closePath(); ctx.fill();
      if (v.label) {
        ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace';
        ctx.textAlign = 'left';
        ctx.fillText(v.label, X + 6, Y - 4);
      }
    });
    (opts.points || []).forEach(function (p) {
      ctx.fillStyle = p.color || '#93c5fd';
      ctx.beginPath(); ctx.arc(cx + p.C * r, cy - p.S * r, p.r || 2.5, 0, 2 * Math.PI); ctx.fill();
    });
  }

  /* ------------------------------------------------------------- control UI */
  var PARAMS = {};
  var CONTROL_INPUTS = {};
  var LAST = {};
  var ACTIVE = 'physical';
  var runTimer = null;

  function scheduleRun(name) {
    if (runTimer) clearTimeout(runTimer);
    runTimer = setTimeout(function () { runModule(name); }, 30);
  }

  function buildControls(moduleKey, schema) {
    var host = document.getElementById('ctl-' + moduleKey);
    if (!host) return;
    host.innerHTML = '';
    PARAMS[moduleKey] = {};
    CONTROL_INPUTS[moduleKey] = {};
    Object.keys(schema).forEach(function (key) {
      var sc = schema[key];
      var val0 = sc.value;
      PARAMS[moduleKey][key] = val0;

      var row = document.createElement('div');
      row.className = 'ctrl';

      var lab = document.createElement('span');
      lab.className = 'ctrl-label';
      lab.textContent = sc.label;

      var range = document.createElement('input');
      range.type = 'range';
      range.min = sc.min; range.max = sc.max; range.step = sc.step; range.value = val0;

      var num = document.createElement('input');
      num.type = 'number';
      num.min = sc.min; num.max = sc.max; num.step = sc.step; num.value = val0;

      var val = document.createElement('span');
      val.className = 'ctrl-val';

      function show(v) {
        if (sc.int) val.textContent = fmtInt(v);
        else val.textContent = v.toFixed(decimalsFor(sc.step));
      }
      show(val0);

      function set(v, src) {
        if (!isFinite(v)) v = val0;
        v = Math.min(sc.max, Math.max(sc.min, v));
        PARAMS[moduleKey][key] = v;
        range.value = v; num.value = v; show(v);
        scheduleRun(moduleKey);
      }
      range.addEventListener('input', function () { set(parseFloat(range.value)); });
      num.addEventListener('change', function () { set(parseFloat(num.value)); });

      CONTROL_INPUTS[moduleKey][key] = { range: range, num: num, show: show };

      row.appendChild(lab); row.appendChild(range); row.appendChild(num); row.appendChild(val);
      host.appendChild(row);
    });
  }

  function applyPreset(moduleKey, values) {
    var schema = SCHEMAS[moduleKey];
    Object.keys(values).forEach(function (k) {
      if (!schema[k]) return;
      var v = values[k];
      PARAMS[moduleKey][k] = v;
      var c = CONTROL_INPUTS[moduleKey][k];
      if (c) { c.range.value = v; c.num.value = v; c.show(v); }
    });
    runModule(moduleKey);
  }

  function setStats(id, rows) {
    var host = document.getElementById(id);
    if (!host) return;
    var html = '<table>';
    rows.forEach(function (r) {
      html += '<tr><td>' + r[0] + '</td><td>' + r[1] + '</td></tr>';
    });
    host.innerHTML = html + '</table>';
  }

  /* --------------------------------------------------------------- modules */
  var SCHEMAS = {
    physical: {
      x0: { label: 'Initial state x₀', min: -10, max: 10, step: 0.1, value: 0 },
      u0: { label: 'Intended transformation u₀', min: -5, max: 5, step: 0.05, value: 1 },
      uAmp: { label: 'Drive amplitude', min: 0, max: 5, step: 0.05, value: 0 },
      uFreq: { label: 'Drive frequency (cycles/step)', min: 0, max: 0.2, step: 0.001, value: 0 },
      uPhase: { label: 'Drive phase (rad)', min: -3.1416, max: 3.1416, step: 0.01, value: 0 },
      k1: { label: 'Linear induced response k₁', min: 0, max: 1, step: 0.005, value: 0.08 },
      k2: { label: 'Quadratic induced response k₂', min: 0, max: 0.1, step: 0.0005, value: 0.001 },
      k3: { label: 'Cross response k₃ (u·x)', min: 0, max: 1, step: 0.005, value: 0 },
      U0: { label: 'Internal energy U₀', min: -50, max: 50, step: 0.5, value: 10 },
      alphaU: { label: 'Energy coupling αU', min: 0, max: 5, step: 0.05, value: 0.5 },
      P0: { label: 'Pressure P₀', min: 0, max: 10, step: 0.1, value: 1 },
      V0: { label: 'Volume V₀', min: 0, max: 10, step: 0.1, value: 1 },
      horizon: { label: 'Horizon N', min: 2, max: 400, step: 1, value: 120, int: true }
    },
    polarity: {
      c0: { label: 'Concentration c₀', min: 0, max: 100, step: 1, value: 60 },
      g0: { label: 'Generation g₀', min: 0, max: 100, step: 1, value: 40 },
      u0: { label: 'Pole transfer u₀', min: -5, max: 5, step: 0.05, value: 1 },
      gamma: { label: 'Singularity coupling γ', min: 0, max: 2, step: 0.01, value: 0.3 },
      kappa: { label: 'Regeneration κ', min: 0, max: 1, step: 0.005, value: 0.05 },
      noise: { label: 'Nondeterminative noise', min: 0, max: 2, step: 0.01, value: 0 },
      seed: { label: 'Seed', min: 1, max: 100000, step: 1, value: 7, int: true },
      horizon: { label: 'Horizon N', min: 2, max: 400, step: 1, value: 120, int: true }
    },
    economy: {
      stock0: { label: 'Initial stock R₀', min: 0, max: 1000, step: 10, value: 500 },
      K: { label: 'Carrying capacity K', min: 100, max: 5000, step: 50, value: 1000 },
      rho: { label: 'Regeneration rate ρ', min: 0, max: 1, step: 0.005, value: 0.2 },
      consumption: { label: 'Consumption C', min: 0, max: 500, step: 5, value: 50 },
      extraction: { label: 'Extraction E', min: 0, max: 500, step: 5, value: 100 },
      price: { label: 'Price per unit', min: 0, max: 20, step: 0.1, value: 2 },
      cost: { label: 'Cost per unit', min: 0, max: 20, step: 0.1, value: 1 },
      synergy: { label: 'Synergy coefficient s', min: -1, max: 2, step: 0.01, value: 0.15 },
      horizon: { label: 'Horizon N', min: 2, max: 400, step: 1, value: 60, int: true }
    },
    knowledge: {
      theta: { label: 'Perspective angle θ (°)', min: 0, max: 360, step: 1, value: 35 },
      k: { label: 'Knowledge magnitude k', min: 0, max: 10, step: 0.1, value: 1 },
      B: { label: 'Observational baseline B', min: 0, max: 100, step: 0.1, value: 1 },
      D: { label: 'Distance to system D', min: 0.1, max: 1000, step: 0.1, value: 100 },
      epsilon: { label: 'Resolution threshold ε', min: 0.0001, max: 0.1, step: 0.0001, value: 0.01 },
      perspectives: { label: 'Perspectives in monad', min: 1, max: 50, step: 1, value: 1, int: true },
      dB: { label: 'Baseline added per perspective δB', min: 0, max: 100, step: 0.5, value: 0.5 }
    },
    iteration: {
      theta0: { label: 'Initial angle θ₀ (°)', min: 0, max: 360, step: 1, value: 35 },
      k0: { label: 'Initial magnitude k₀', min: 0.1, max: 10, step: 0.1, value: 1 },
      proj: { label: 'Projection scale p', min: 0.5, max: 1.5, step: 0.01, value: 1 },
      projAngle: { label: 'Projection rotation (°)', min: -180, max: 180, step: 1, value: 0 },
      refl: { label: 'Reflection scale r', min: 0.5, max: 1.5, step: 0.01, value: 1 },
      reflAngle: { label: 'Reflection rotation (°)', min: -180, max: 180, step: 1, value: 0 },
      iterations: { label: 'Iterations', min: 2, max: 200, step: 1, value: 60, int: true }
    },
    prediction: {
      x0: { label: 'Initial state x₀', min: -10, max: 10, step: 0.1, value: 0 },
      u0: { label: 'Intended transformation u₀', min: -5, max: 5, step: 0.05, value: 1 },
      k1t: { label: 'True linear response k₁ᵗ', min: 0, max: 1, step: 0.005, value: 0.08 },
      k2t: { label: 'True quadratic response k₂ᵗ', min: 0, max: 0.1, step: 0.0005, value: 0.001 },
      k1m: { label: 'Model linear response k₁ᵐ', min: 0, max: 1, step: 0.005, value: 0.08 },
      k2m: { label: 'Model quadratic response k₂ᵐ', min: 0, max: 0.1, step: 0.0005, value: 0.001 },
      bias: { label: 'Model bias', min: -5, max: 5, step: 0.05, value: 0 },
      noise: { label: 'Nondeterminative amplitude η', min: 0, max: 5, step: 0.01, value: 0.5 },
      horizon: { label: 'Horizon N', min: 2, max: 400, step: 1, value: 120, int: true },
      runs: { label: 'Monte Carlo runs', min: 1, max: 500, step: 1, value: 50, int: true },
      seed: { label: 'Seed', min: 1, max: 100000, step: 1, value: 42, int: true }
    }
  };

  var PRESETS = {
    physical: {
      'Stable advance': { k1: 0.02, k2: 0.0005, k3: 0, u0: 1, uAmp: 0 },
      'N+1 reversal': { k1: 0.35, k2: 0.02, k3: 0, u0: 1, uAmp: 0 },
      'Driven oscillation': { k1: 0.15, k2: 0.005, k3: 0.1, u0: 0, uAmp: 2, uFreq: 0.02, uPhase: 1.5708 }
    },
    polarity: {
      'Concentration → generation': { c0: 80, g0: 20, u0: 2, gamma: 0.4, kappa: 0.02, noise: 0 },
      'Balanced oscillation': { c0: 50, g0: 50, u0: 0.5, gamma: 0.8, kappa: 0.05, noise: 0.2 },
      'Noisy reversal': { c0: 60, g0: 40, u0: 1, gamma: 0.6, kappa: 0.03, noise: 1.5 }
    },
    economy: {
      'Extraction collapse': { stock0: 500, K: 1000, rho: 0.1, consumption: 50, extraction: 200, synergy: 0 },
      'Sustainability': { stock0: 500, K: 1000, rho: 0.4, consumption: 80, extraction: 40, synergy: 0 },
      'Synergy beyond singularity': { stock0: 500, K: 1000, rho: 0.25, consumption: 60, extraction: 80, synergy: 0.5 }
    },
    prediction: {
      'Calm / accurate model': { noise: 0.05, k1m: 0.08, k2m: 0.001, bias: 0, k1t: 0.08, k2t: 0.001 },
      'Model mismatch': { noise: 0.2, k1m: 0.2, k2m: 0.005, bias: 0.3, k1t: 0.08, k2t: 0.001 },
      'Noisy realization': { noise: 2.5, k1m: 0.08, k2m: 0.001, bias: 0, k1t: 0.08, k2t: 0.001 }
    }
  };

  function bindPresetButtons() {
    document.querySelectorAll('[data-preset-module]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var mod = btn.getAttribute('data-preset-module');
        var name = btn.getAttribute('data-preset-name');
        if (PRESETS[mod] && PRESETS[mod][name]) applyPreset(mod, PRESETS[mod][name]);
      });
    });
  }

  /* ------------------------------------------------------------ run modules */
  function runPhysical() {
    var p = PARAMS.physical;
    var r = TOT.nPlusOne(p);
    var revIdx = [];
    r.rev.forEach(function (b, i) { if (b) revIdx.push(i + 1); });

    drawLineChart(document.getElementById('chart-phys-x'), {
      series: [
        { name: 'x[N] state', data: r.x, color: '#5eead4' },
        { name: 'u[N] intended', data: r.u, color: '#93c5fd', dash: [5, 3] },
        { name: 'f[N] induced', data: r.f, color: '#f9a8d4', dash: [2, 3] }
      ],
      xLabel: 'N', yLabel: 'value',
      markers: revIdx.map(function (i) { return { index: i, color: '#f87171' }; })
    });
    drawLineChart(document.getElementById('chart-phys-h'), {
      series: [
        { name: 'H = U + PV', data: r.H, color: '#fbbf24' },
        { name: 'U (internal energy)', data: r.U, color: '#a78bfa', dash: [5, 3] }
      ],
      xLabel: 'N', yLabel: 'enthalpy'
    });
    var peak = 0;
    r.x.forEach(function (v) { peak = Math.max(peak, Math.abs(v)); });
    setStats('stats-physical', [
      ['Final state x[N]', fmt(r.x[r.N])],
      ['Peak |x|', fmt(peak)],
      ['Reversals (sign Δx ≠ sign u)', fmtInt(revIdx.length)],
      ['Mean H', fmt(mean(r.H))],
      ['Final H', fmt(r.H[r.N])]
    ]);
    LAST.physical = {
      params: Object.assign({}, p),
      csv: [['N', 'x', 'u', 'f', 'H', 'reversal']].concat(
        r.x.map(function (_, i) {
          return [i, r.x[i], r.u[i], r.f[i], r.H[i], i < r.rev.length ? (r.rev[i] ? 1 : 0) : ''];
        })
      )
    };
  }

  function runPolarity() {
    var p = PARAMS.polarity;
    var r = TOT.polarity(p);
    var revIdx = [];
    r.rev.forEach(function (b, i) { if (b) revIdx.push(i + 1); });

    drawLineChart(document.getElementById('chart-pol-poles'), {
      series: [
        { name: 'c[N] concentration', data: r.c, color: '#5eead4' },
        { name: 'g[N] generation', data: r.g, color: '#93c5fd' }
      ],
      xLabel: 'N', yLabel: 'pole magnitude',
      markers: revIdx.map(function (i) { return { index: i, color: '#f87171' }; })
    });
    drawLineChart(document.getElementById('chart-pol-pol'), {
      series: [
        { name: 'polarity (c−g)/(c+g)', data: r.pol, color: '#fbbf24' },
        { name: 'E_C = +E', data: r.EC, color: '#f9a8d4', dash: [4, 3] },
        { name: 'E_G = −E', data: r.EG, color: '#a78bfa', dash: [4, 3] }
      ],
      xLabel: 'N', yLabel: 'polarity / entropic magnitude'
    });
    setStats('stats-polarity', [
      ['Final polarity', fmt(r.pol[r.N])],
      ['Total c + g (conserved)', fmt(r.c[r.N] + r.g[r.N])],
      ['Reversals through Ω', fmtInt(revIdx.length)],
      ['Final E_C / E_G', fmt(r.EC[r.N]) + ' / ' + fmt(r.EG[r.N])]
    ]);
    LAST.polarity = {
      params: Object.assign({}, p),
      csv: [['N', 'c', 'g', 'polarity', 'E_C', 'E_G', 'reversal']].concat(
        r.c.map(function (_, i) {
          return [i, r.c[i], r.g[i], r.pol[i], r.EC[i], r.EG[i], i < r.rev.length ? (r.rev[i] ? 1 : 0) : ''];
        })
      )
    };
  }

  function runEconomy() {
    var p = PARAMS.economy;
    var r = TOT.economy(p);
    var revIdx = [];
    r.rev.forEach(function (b, i) { if (b) revIdx.push(i + 1); });

    drawLineChart(document.getElementById('chart-eco-stock'), {
      series: [
        { name: 'R[N] stock', data: r.R, color: '#5eead4' },
        { name: 'regeneration', data: r.regen, color: '#93c5fd', dash: [5, 3] },
        { name: 'extraction', data: r.ex, color: '#fbbf24', dash: [2, 3] },
        { name: 'consumption', data: r.cons, color: '#f9a8d4', dash: [2, 3] }
      ],
      xLabel: 'N', yLabel: 'units',
      markers: revIdx.map(function (i) { return { index: i, color: '#f87171' }; })
    });
    drawLineChart(document.getElementById('chart-eco-value'), {
      series: [
        { name: 'E = extraction value', data: r.E, color: '#fbbf24' },
        { name: 'S = regeneration − consumption', data: r.S, color: '#5eead4' },
        { name: 'Y = synergy', data: r.Y, color: '#a78bfa' }
      ],
      xLabel: 'N', yLabel: 'value'
    });
    setStats('stats-economy', [
      ['Final stock R[N]', fmt(r.R[r.N])],
      ['Total extraction value', fmt(sum(r.E))],
      ['Total sustainability S', fmt(sum(r.S))],
      ['Total synergy Y', fmt(sum(r.Y))],
      ['Reversals (extract while stock falls)', fmtInt(revIdx.length)]
    ]);
    LAST.economy = {
      params: Object.assign({}, p),
      csv: [['N', 'R', 'regeneration', 'extraction', 'consumption', 'E_value', 'S_sustainability', 'Y_synergy', 'reversal']].concat(
        r.R.map(function (_, i) {
          return [i, r.R[i], r.regen[i], r.ex[i], r.cons[i], r.E[i], r.S[i], r.Y[i], i < r.rev.length ? (r.rev[i] ? 1 : 0) : ''];
        })
      )
    };
  }

  function runKnowledge() {
    var p = PARAMS.knowledge;
    var kn = TOT.knowledge(p.theta, p.k);
    var base = TOT.resolution(p.B, p.D, p.epsilon);

    var deltas = [], ratios = [], resolvedFlags = [];
    for (var m = 1; m <= p.perspectives; m++) {
      var Beff = p.B + (m - 1) * p.dB;
      var rr = TOT.resolution(Beff, p.D, p.epsilon);
      deltas.push(rr.delta);
      ratios.push(rr.ratio);
      resolvedFlags.push(rr.resolved ? 1 : 0);
    }

    drawUnitCircle(document.getElementById('chart-kn-circle'), {
      vectors: [{ C: kn.CK, S: kn.SK, color: '#fbbf24', label: 'P (perspective)' }],
      points: [{ C: 1, S: 0, color: '#5eead4', r: 3 }, { C: 0, S: 1, color: '#93c5fd', r: 3 }]
    });
    drawLineChart(document.getElementById('chart-kn-res'), {
      series: [
        { name: 'δ = B/D', data: deltas, color: '#5eead4' },
        { name: 'ε threshold', data: deltas.map(function () { return p.epsilon; }), color: '#f87171', dash: [5, 3] }
      ],
      xLabel: 'perspectives in monad', yLabel: 'angular differential'
    });
    var resolvedCount = resolvedFlags.reduce(function (a, b) { return a + b; }, 0);
    setStats('stats-knowledge', [
      ['C_K = cos θ', fmt(kn.CK)],
      ['S_K = sin θ', fmt(kn.SK)],
      ['C_K² + S_K²', fmt(kn.CK * kn.CK + kn.SK * kn.SK)],
      ['K_parallel = k·cos θ', fmt(kn.Kpar)],
      ['K_perpendicular = k·sin θ', fmt(kn.Kperp)],
      ['k² − (K_par² + K_perp²)', fmt(kn.magnitude * kn.magnitude - (kn.Kpar * kn.Kpar + kn.Kperp * kn.Kperp))],
      ['δ = B/D (base)', pctDecimal(base.delta)],
      ['δ / ε', pctDecimal(base.ratio)],
      ['Resolved at base baseline', base.resolved ? 'yes' : 'no'],
      ['Perspectives resolving', fmtInt(resolvedCount) + ' / ' + fmtInt(p.perspectives)]
    ]);
    LAST.knowledge = {
      params: Object.assign({}, p),
      csv: [['metric', 'value', 'delta', 'ratio', 'resolved']]
        .concat([
          ['theta_deg', p.theta], ['k', p.k], ['C_K', kn.CK], ['S_K', kn.SK],
          ['K_parallel', kn.Kpar], ['K_perpendicular', kn.Kperp],
          ['B', p.B], ['D', p.D], ['epsilon', p.epsilon],
          ['delta_base', base.delta, base.delta, base.ratio, base.resolved ? 1 : 0],
          ['resolved_base', base.resolved ? 1 : 0]
        ].map(function (r) { return r.concat(['', '', '', '', '']).slice(0, 5); }))
        .concat(deltas.map(function (d, i) {
          return ['perspective_' + (i + 1), d, d, ratios[i], resolvedFlags[i]];
        }))
    };
  }

  function runIteration() {
    var p = PARAMS.iteration;
    var r = TOT.knowledgeIteration(p);
    var path = r.xs.map(function (c, i) { return { C: c, S: r.ys[i] }; });
    drawUnitCircle(document.getElementById('chart-it-circle'), {
      path: path,
      pathColor: '#5eead4',
      vectors: [{ C: r.xs[r.N], S: r.ys[r.N], color: '#fbbf24', label: 'K[N]' }],
      points: [{ C: 1, S: 0, color: '#93c5fd', r: 3 }]
    });
    drawLineChart(document.getElementById('chart-it-mag'), {
      series: [
        { name: 'magnitude k[N]', data: r.mags, color: '#fbbf24' },
        { name: 'coherence cos Δθ', data: r.coh, color: '#5eead4' }
      ],
      xLabel: 'iteration', yLabel: 'value'
    });
    var meanCoh = mean(r.coh);
    setStats('stats-iteration', [
      ['Final angle θ[N]', fmt(r.thetaFinal) + '°'],
      ['Final magnitude k[N]', fmt(r.mags[r.N])],
      ['Mean coherence', fmt(meanCoh)],
      ['Min coherence', fmt(r.coh.length ? Math.min.apply(null, r.coh) : NaN)]
    ]);
    LAST.iteration = {
      params: Object.assign({}, p),
      csv: [['N', 'C', 'S', 'magnitude', 'coherence']].concat(
        r.xs.map(function (_, i) {
          return [i, r.xs[i], r.ys[i], r.mags[i], i < r.coh.length ? r.coh[i] : ''];
        })
      )
    };
  }

  function runPrediction() {
    var p = PARAMS.prediction;
    var r = TOT.prediction(p);
    var mc = TOT.monteCarlo(p);
    var dOpen = r.x.map(function (v, i) { return v - r.xhOpen[i]; });

    drawLineChart(document.getElementById('chart-pred-state'), {
      series: [
        { name: 'realized x[N]', data: r.x, color: '#5eead4' },
        { name: 'one-step projection x̂[N]', data: r.xh, color: '#fbbf24', dash: [5, 3] },
        { name: 'open-loop projection', data: r.xhOpen, color: '#f9a8d4', dash: [2, 3] },
        { name: 'MC mean', data: mc.mean, color: '#a78bfa', width: 1.2 },
        { name: 'MC 5%', data: mc.p5, color: '#a78bfa', dash: [3, 3], width: 1 },
        { name: 'MC 95%', data: mc.p95, color: '#a78bfa', dash: [3, 3], width: 1 }
      ],
      xLabel: 'N', yLabel: 'state'
    });
    drawLineChart(document.getElementById('chart-pred-delta'), {
      series: [
        { name: 'δ[N] = x[N] − x̂[N] (one-step)', data: r.d, color: '#f87171' },
        { name: 'δ[N] open-loop', data: dOpen, color: '#fbbf24', dash: [5, 3] }
      ],
      xLabel: 'N', yLabel: 'resolution difference'
    });
    var covered = 0, counted = 0;
    for (var i = 0; i <= r.N; i++) {
      counted++;
      if (r.x[i] >= mc.p5[i] && r.x[i] <= mc.p95[i]) covered++;
    }
    setStats('stats-prediction', [
      ['Final realized x[N]', fmt(r.x[r.N])],
      ['Final one-step projection', fmt(r.xh[r.N])],
      ['Final δ (one-step)', fmt(r.d[r.N])],
      ['RMSE δ (one-step)', fmt(rmse(r.d))],
      ['MC mean final', fmt(mc.mean[r.N])],
      ['MC 5% / 95% final', fmt(mc.p5[r.N]) + ' / ' + fmt(mc.p95[r.N])],
      ['Realized inside 90% band', fmtInt(covered) + ' / ' + fmtInt(counted) + ' steps'],
      ['Runs / seed', fmtInt(mc.M) + ' / ' + fmtInt(p.seed)]
    ]);
    LAST.prediction = {
      params: Object.assign({}, p),
      csv: [['N', 'x_realized', 'x_hat_one_step', 'x_hat_open_loop', 'delta_one_step', 'delta_open_loop', 'eta', 'mc_mean', 'mc_p5', 'mc_p95']].concat(
        r.x.map(function (_, i) {
          return [i, r.x[i], r.xh[i], r.xhOpen[i], r.d[i], dOpen[i], r.eta[i], mc.mean[i], mc.p5[i], mc.p95[i]];
        })
      )
    };
  }

  var RUNNERS = {
    physical: runPhysical,
    polarity: runPolarity,
    economy: runEconomy,
    knowledge: runKnowledge,
    iteration: runIteration,
    prediction: runPrediction
  };

  function runModule(name) {
    var fn = RUNNERS[name];
    if (fn) fn();
  }

  function runAll() {
    Object.keys(RUNNERS).forEach(function (k) { runModule(k); });
  }

  /* ------------------------------------------------------------ CSV export */
  function downloadCSV(filename, rows) {
    var csv = rows.map(function (r) {
      return r.map(function (c) {
        var s = c == null ? '' : String(c);
        return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
      }).join(',');
    }).join('\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }

  function exportModule(name) {
    if (!LAST[name]) runModule(name);
    var entry = LAST[name];
    if (!entry) return;
    downloadCSV('theory_of_things_' + name + '.csv', entry.csv);
  }

  /* --------------------------------------------------------------- self test */
  function runSelfTest() {
    var checks = [];
    function chk(name, cond, detail) {
      checks.push({ name: name, pass: !!cond, detail: detail == null ? '' : String(detail) });
    }
    function near(a, b, tol) { return Math.abs(a - b) <= (tol == null ? 1e-9 : tol); }

    var kn = TOT.knowledge(35, 2.5);
    chk('C_K² + S_K² = 1', near(kn.CK * kn.CK + kn.SK * kn.SK, 1, 1e-12), (kn.CK * kn.CK + kn.SK * kn.SK));
    chk('k² = K_par² + K_perp²', near(kn.magnitude * kn.magnitude, kn.Kpar * kn.Kpar + kn.Kperp * kn.Kperp, 1e-12),
      kn.magnitude * kn.magnitude - (kn.Kpar * kn.Kpar + kn.Kperp * kn.Kperp));

    var res = TOT.resolution(2, 50, 0.01);
    chk('δ = B/D', near(res.delta, 0.04, 1e-12), res.delta);
    chk('resolved ⇔ δ > ε', res.resolved === (res.delta > res.epsilon), res.resolved);
    chk('H = U + PV', TOT.enthalpy(3, 4, 5) === 23, TOT.enthalpy(3, 4, 5));

    var np = TOT.nPlusOne({ x0: 1, u0: 1, uAmp: 0.5, uFreq: 0.03, uPhase: 0.2, k1: 0.2, k2: 0.01, k3: 0.05, U0: 5, alphaU: 0.3, P0: 2, V0: 3, horizon: 60 });
    var okTrans = true, okRev = true;
    for (var i = 0; i < np.N; i++) {
      var u = np.u[i];
      var f = -(0.2 * np.x[i] + 0.01 * np.x[i] * Math.abs(np.x[i]) + 0.05 * u * np.x[i]);
      if (!near(np.x[i + 1], np.x[i] + u + f, 1e-9)) okTrans = false;
      var expectRev = Math.abs(u) > 1e-12 && Math.abs(np.x[i + 1] - np.x[i]) > 1e-12 &&
        TOT.sign(np.x[i + 1] - np.x[i]) !== TOT.sign(u);
      if (np.rev[i] !== expectRev) okRev = false;
    }
    chk('x[N+1] = x[N] + u[N] + f(x,u)', okTrans, okTrans ? '60/60 transitions' : 'transition mismatch');
    chk('reversal flag = sign(Δx) ≠ sign(u)', okRev, okRev ? '60/60 flags' : 'flag mismatch');
    chk('H[N] = U[N] + P₀V₀', np.H.every(function (h, j) { return near(h, np.U[j] + 2 * 3, 1e-9); }), 'checked all N');

    var pol = TOT.polarity({ c0: 60, g0: 40, u0: 1, gamma: 0.3, kappa: 0.05, noise: 0, seed: 7, horizon: 60 });
    var totalOk = near(pol.c[0] + pol.g[0], pol.total, 1e-9);
    var magOk = pol.EC.every(function (e, j) { return near(Math.abs(e), Math.abs(pol.EG[j]), 1e-12); });
    chk('c + g conserved', totalOk, pol.c[0] + pol.g[0]);
    chk('|E_C| = |E_G|', magOk, 'all N');

    var eco = TOT.economy({ stock0: 500, K: 1000, rho: 0.2, consumption: 50, extraction: 100, price: 2, cost: 1, synergy: 0.15, horizon: 40 });
    var yOk = true;
    for (var j = 0; j < eco.N; j++) {
      if (!near(eco.Y[j], 0.15 * (eco.E[j] + eco.S[j]), 1e-9)) yOk = false;
      if (eco.R[j] < -1e-12) yOk = false;
    }
    chk('Y = s·(V(A)+V(B)) and R ≥ 0', yOk, yOk ? '40/40 steps' : 'economy mismatch');

    var it = TOT.knowledgeIteration({ theta0: 35, k0: 1, proj: 1, projAngle: 0, refl: 1, reflAngle: 0, iterations: 30 });
    chk('identity iteration keeps direction', near(it.xs[0], it.xs[it.N], 1e-9) && near(it.ys[0], it.ys[it.N], 1e-9), it.thetaFinal);

    var pr1 = TOT.prediction({ x0: 0, u0: 1, k1t: 0.08, k2t: 0.001, k1m: 0.08, k2m: 0.001, bias: 0, noise: 0.5, horizon: 50, seed: 42 });
    var pr2 = TOT.prediction({ x0: 0, u0: 1, k1t: 0.08, k2t: 0.001, k1m: 0.08, k2m: 0.001, bias: 0, noise: 0.5, horizon: 50, seed: 42 });
    chk('same seed → identical forecast', JSON.stringify(pr1.x) === JSON.stringify(pr2.x), pr1.N + ' steps');
    var dOk = true;
    for (var k = 1; k <= pr1.N; k++) {
      var fT = -(0.08 * pr1.x[k - 1] + 0.001 * pr1.x[k - 1] * Math.abs(pr1.x[k - 1]));
      var fM = -(0.08 * pr1.x[k - 1] + 0.001 * pr1.x[k - 1] * Math.abs(pr1.x[k - 1]));
      if (!near(pr1.d[k], fT + pr1.eta[k - 1] - fM, 1e-9)) dOk = false;
    }
    chk('δ[N] = f_true(x) + η − f_model(x)', dOk, dOk ? '50/50 steps' : 'delta mismatch');

    var mc = TOT.monteCarlo({ x0: 0, u0: 1, k1t: 0.08, k2t: 0.001, k1m: 0.08, k2m: 0.001, bias: 0, noise: 0.5, horizon: 40, runs: 25, seed: 42 });
    var bandOk = true;
    for (var m = 0; m <= mc.N; m++) if (!(mc.p5[m] <= mc.p95[m])) bandOk = false;
    chk('MC 5% ≤ 95% band', bandOk, mc.M + ' runs');
    var detOk = JSON.stringify(TOT.monteCarlo({ x0: 0, u0: 1, k1t: 0.08, k2t: 0.001, k1m: 0.08, k2m: 0.001, bias: 0, noise: 0.5, horizon: 40, runs: 25, seed: 42 }).mean) === JSON.stringify(mc.mean);
    chk('MC deterministic under seed', detOk, '');

    var passed = checks.filter(function (c) { return c.pass; }).length;
    var result = { pass: passed, fail: checks.length - passed, total: checks.length, checks: checks };
    window.__SELFTEST__ = result;
    var pre = document.getElementById('selftest');
    if (pre) {
      pre.textContent = checks.map(function (c) {
        return (c.pass ? 'PASS' : 'FAIL') + '  ' + c.name + (c.detail ? '  [' + c.detail + ']' : '');
      }).join('\n') + '\n\nTOTAL: ' + passed + '/' + checks.length + ' passed';
    }
    return result;
  }

  /* ------------------------------------------------------------------- tabs */
  function initTabs() {
    var buttons = document.querySelectorAll('.tab-btn');
    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        buttons.forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        var name = btn.getAttribute('data-tab');
        document.querySelectorAll('.panel').forEach(function (p) { p.classList.remove('active'); });
        var panel = document.getElementById('panel-' + name);
        if (panel) panel.classList.add('active');
        ACTIVE = name;
        runModule(name);
      });
    });
  }

  function initExport() {
    document.querySelectorAll('[data-export]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        exportModule(btn.getAttribute('data-export'));
      });
    });
    var st = document.getElementById('selftest-btn');
    if (st) st.addEventListener('click', runSelfTest);
  }

  /* ------------------------------------------------------------------ boot */
  function boot() {
    Object.keys(SCHEMAS).forEach(function (k) { buildControls(k, SCHEMAS[k]); });
    bindPresetButtons();
    initTabs();
    initExport();
    runModule(ACTIVE);
    window.addEventListener('resize', function () { runModule(ACTIVE); });
    window.__DASHBOARD__ = {
      ready: true,
      runModule: runModule,
      runAll: runAll,
      selfTest: runSelfTest,
      params: PARAMS,
      last: LAST
    };
    if (/[?&]selftest=1/.test(window.location.search)) {
      runAll();
      runSelfTest();
    }
  }

  window.addEventListener('error', function (e) {
    var host = document.getElementById('js-errors');
    if (host) host.textContent += '\n' + (e.message || e.error) + ' @ ' + (e.filename || '') + ':' + (e.lineno || '');
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
