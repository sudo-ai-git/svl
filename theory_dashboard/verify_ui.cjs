/* UI-layer verification: execute app.js under a minimal DOM stub in Node.
 * This exercises boot(), control generation, all six module runners,
 * tab switching, parameter updates, self-test and CSV row construction.
 * Run: node verify_ui.js
 */
'use strict';

let pass = 0, fail = 0;
const failures = [];
function chk(name, cond, detail) {
  if (cond) { pass++; console.log('PASS  ' + name + (detail ? '  [' + detail + ']' : '')); }
  else { fail++; failures.push(name + (detail ? '  [' + detail + ']' : '')); console.log('FAIL  ' + name + (detail ? '  [' + detail + ']' : '')); }
}

class FakeElement {
  constructor(tag) {
    this.tagName = tag || 'div';
    this.children = [];
    this._handlers = {};
    this.attributes = {};
    this.style = {};
    this.textContent = '';
    this.innerHTML = '';
    this.value = '';
    this.type = '';
    this.min = ''; this.max = ''; this.step = '';
    this.clientWidth = 600;
    this.clientHeight = 260;
    const set = new Set();
    this.classList = {
      add: (c) => set.add(c),
      remove: (c) => set.delete(c),
      contains: (c) => set.has(c),
      _set: set
    };
  }
  appendChild(c) { this.children.push(c); return c; }
  remove() {}
  addEventListener(t, fn) { (this._handlers[t] = this._handlers[t] || []).push(fn); }
  dispatch(t, ev) { (this._handlers[t] || []).forEach((fn) => fn(ev || {})); }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k]; }
  getBoundingClientRect() { return { left: 0, top: 0, width: 600, height: 260 }; }
  getContext() {
    return new Proxy({}, {
      get: (obj, key) => {
        if (key === 'measureText') return () => ({ width: 10 });
        if (key in obj) return obj[key];
        return () => {};
      },
      set: () => true
    });
  }
  click() { this.dispatch('click'); }
}

const byId = {};
function getEl(id, tag) {
  if (!byId[id]) { byId[id] = new FakeElement(tag); byId[id].id = id; }
  return byId[id];
}

const panels = ['physical', 'polarity', 'economy', 'knowledge', 'iteration', 'prediction'].map((name) => {
  const e = getEl('panel-' + name, 'section');
  e.classList.add('panel');
  return e;
});
const tabs = ['physical', 'polarity', 'economy', 'knowledge', 'iteration', 'prediction'].map((name) => {
  const b = getEl('tab-' + name, 'button');
  b.setAttribute('data-tab', name);
  b.classList.add('tab-btn');
  return b;
});
const exportBtns = ['physical', 'polarity', 'economy', 'knowledge', 'iteration', 'prediction'].map((name) => {
  const b = getEl('export-' + name, 'button');
  b.setAttribute('data-export', name);
  return b;
});
const presets = [];
[['physical', 'Stable advance'], ['physical', 'N+1 reversal'], ['physical', 'Driven oscillation'],
  ['polarity', 'Concentration → generation'], ['polarity', 'Balanced oscillation'], ['polarity', 'Noisy reversal'],
  ['economy', 'Extraction collapse'], ['economy', 'Sustainability'], ['economy', 'Synergy beyond singularity'],
  ['prediction', 'Calm / accurate model'], ['prediction', 'Model mismatch'], ['prediction', 'Noisy realization']
].forEach(([mod, nm]) => {
  const b = getEl('preset-' + mod + '-' + nm, 'button');
  b.setAttribute('data-preset-module', mod);
  b.setAttribute('data-preset-name', nm);
  presets.push(b);
});

const documentStub = {
  readyState: 'complete',
  getElementById: (id) => getEl(id),
  querySelectorAll: (sel) => {
    if (sel === '.panel') return panels;
    if (sel === '.tab-btn') return tabs;
    if (sel === '[data-export]') return exportBtns;
    if (sel === '[data-preset-module]') return presets;
    return [];
  },
  createElement: (tag) => new FakeElement(tag),
  body: new FakeElement('body'),
  addEventListener: () => {}
};

const winHandlers = {};
const windowStub = {
  TOT: require('./model.js'),
  devicePixelRatio: 1,
  location: { search: '' },
  addEventListener: (t, fn) => { (winHandlers[t] = winHandlers[t] || []).push(fn); }
};

global.window = windowStub;
global.document = documentStub;
global.URL = { createObjectURL: () => 'blob:stub', revokeObjectURL: () => {} };
global.Blob = class Blob { constructor(parts) { this.parts = parts; } };

require('./app.js');

const D = windowStub.__DASHBOARD__;
chk('dashboard booted and exposed __DASHBOARD__.ready', D && D.ready === true, D ? 'ready' : 'undefined');

/* controls generated for every schema key */
const schemaKeys = {
  physical: 13, polarity: 8, economy: 9, knowledge: 7, iteration: 7, prediction: 11
};
Object.keys(schemaKeys).forEach((mod) => {
  const host = getEl('ctl-' + mod);
  const rows = host.children.filter((c) => c.children && c.children.length === 4);
  chk('controls built: ' + mod, rows.length === schemaKeys[mod], rows.length + '/' + schemaKeys[mod]);
  const range = rows[0].children[1];
  chk('range input wired: ' + mod, range.type === 'range' && typeof range._handlers.input === 'object' && range._handlers.input.length === 1, '');
});

/* all modules run and produce CSV rows of the right length */
D.runAll();
const expectedRows = { physical: 122, polarity: 122, economy: 62, knowledge: 13, iteration: 62, prediction: 122 };
Object.keys(expectedRows).forEach((mod) => {
  const entry = D.last[mod];
  chk('module produced CSV: ' + mod, !!entry && entry.csv.length === expectedRows[mod],
    entry ? String(entry.csv.length) + ' rows' : 'missing');
  if (entry) {
    const badCol = entry.csv.some((r) => r.length !== entry.csv[0].length);
    chk('CSV columns consistent: ' + mod, !badCol, entry.csv[0].length + ' columns');
  }
});

/* stats tables rendered */
['physical', 'polarity', 'economy', 'knowledge', 'iteration', 'prediction'].forEach((mod) => {
  const st = getEl('stats-' + mod);
  chk('stats rendered: ' + mod, st.innerHTML.indexOf('<table>') === 0 && st.innerHTML.indexOf('</table>') > 0, '');
});

/* self-test */
const st = D.selfTest();
chk('self-test all pass', st.fail === 0 && st.pass === st.total, st.pass + '/' + st.total);
chk('self-test written to #selftest', getEl('selftest').textContent.indexOf('TOTAL:') > 0, '');
chk('no JavaScript errors captured', getEl('js-errors').textContent.trim() === '', getEl('js-errors').textContent.trim());

/* parameter update path: slider input updates params and reruns */
const physX0 = getEl('ctl-physical').children[0].children[1];
physX0.value = '5';
physX0.dispatch('input');
chk('slider input updates params.physical.x0', D.params.physical.x0 === 5, String(D.params.physical.x0));
D.runModule('physical');
chk('rerun after input produces new CSV', D.last.physical.csv.length === 122, String(D.last.physical.csv.length));

/* preset path */
const before = D.params.prediction.noise;
presets.find((b) => b.getAttribute('data-preset-name') === 'Noisy realization').click();
chk('preset applied to params', D.params.prediction.noise !== before && D.params.prediction.noise === 2.5, String(D.params.prediction.noise));

/* tab switching */
tabs.find((b) => b.getAttribute('data-tab') === 'polarity').click();
chk('tab switch activates panel', getEl('panel-polarity').classList.contains('active') && !getEl('panel-physical').classList.contains('active'), '');
chk('tab switch reran module', !!D.last.polarity, '');

/* export builds a CSV string without throwing */
let exported = null;
const origCreate = global.URL.createObjectURL;
global.URL.createObjectURL = (blob) => { exported = blob.parts.join(''); return 'blob:x'; };
exportBtns.find((b) => b.getAttribute('data-export') === 'physical').click();
global.URL.createObjectURL = origCreate;
chk('CSV export produced content', typeof exported === 'string' && exported.split('\n').length === 122, exported ? exported.split('\n').length + ' lines' : 'none');
chk('CSV header correct', exported && exported.startsWith('N,x,u,f,H,reversal'), exported ? exported.split('\n')[0] : 'none');

console.log('\nTOTAL: ' + pass + '/' + (pass + fail) + ' passed');
if (fail) { console.log('FAILURES:\n' + failures.join('\n')); process.exit(1); }
