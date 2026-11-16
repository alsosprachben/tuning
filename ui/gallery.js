// THE CONTROLS TEST PAGE: the kit's controls bound to the first synth part's
// real knobs (and its level), so the feel is tried with the sound.
'use strict';

const $ = id => document.getElementById(id);
const G = { knobs: [], row: 0, synth: null, parts: [], ctl: {} };

function log(s) {
  const el = $('log'), line = document.createElement('div');
  line.textContent = new Date().toLocaleTimeString() + '  ' + s;
  el.prepend(line);
  while (el.childNodes.length > 8) el.lastChild.remove();
}

const find = (section, label) => G.knobs.findIndex(k => k.section === section && k.label === label);

// a knob of the engine's table on a kit control
function engineKnob(parent, section, label, extra = {}) {
  const i = find(section, label);
  if (i < 0) return;
  const k = G.knobs[i];
  const send = Wire.throttled(async v => {
    const r = await Wire.call('synth_set', { row: G.row, knob: k.knob, v });
    if (r.text !== undefined) ctl.setText(r.text);
  });
  let text = '';
  const name = extra.label || label;
  const c = Kit.knob(parent, {
    label: name, value: 0, centred: k.centred, detents: extra.detents || (k.centred ? [0.5] : []),
    size: extra.size, scope: extra.scope,
    fmt: () => text,                            // (the engine's words: each set answers with them)
    onChange: v => send(v),
    onEnd: () => log(`${name}: ${text}`),
    onReset: async () => { await Wire.call('synth_forget', { row: G.row, knob: k.knob }); log(`${name}: back to the patch`); refresh(); },
    onInfo: () => Kit.sheet({
      title: name, text, value: c.get(),
      hint: 'The knob\'s position, 0 to 1. Its value in its own words shows once it is set.',
      onSet: async v => { const r = await Wire.call('synth_set', { row: G.row, knob: k.knob, v }); ctl.set(v, r.text, true); log(`${name}: typed ${v}`); },
      onReset: async () => { await Wire.call('synth_forget', { row: G.row, knob: k.knob }); refresh(); },
    }),
  });
  const ctl = {
    get: c.get,
    setText(t) { text = t; c.el.querySelector('.kit-value').textContent = t; },
    set(v, t, own) { if (t !== undefined) text = t; c.set(v, text, own); },
  };
  G.ctl[i] = ctl;
}

function engineSwitch(parent, section, label, words, extra = {}) {
  const i = find(section, label);
  if (i < 0) return;
  const k = G.knobs[i];
  const steps = k.steps;
  const make = steps.length === 2 && !words ? Kit.toggle : Kit.segments;
  const c = make(parent, {
    label: extra.label || label, options: words || steps.map(String), value: 0,
    onChange: async x => {
      const v = typeof x === 'boolean' ? (x ? steps[1] : steps[0]) : steps[x];
      const r = await Wire.call('synth_set', { row: G.row, knob: k.knob, v });
      log(`${extra.label || label}: ${r.text ?? v}`);
    },
  });
  G.ctl[i] = { switch: c, steps };
}

function apply(sy) {
  if (!sy || sy.layers <= 0) return;
  G.synth = sy;
  for (const i in G.ctl) {
    const k = G.knobs[i], c = G.ctl[i], v = sy.pn[k.knob], own = !!sy.own[k.knob];
    if (c.switch) {
      const j = c.steps.findIndex(s => Math.abs(s - v) < 1e-6);
      if (j >= 0) c.switch.set(j);
    } else {
      c.set(v, sy.text[i], own);
    }
  }
}

async function refresh() {
  const r = await Wire.call('synth', { row: G.row });
  apply(r.synth);
}

let level;
function build() {
  engineKnob($('filter'), 'FILTER', 'cutoff', { size: 'big' });
  engineKnob($('filter'), 'FILTER', 'resonance');
  engineKnob($('filter'), 'FILTER', 'eg amount', { label: 'env amount' });
  engineKnob($('oscs'), 'OSC 1', 'wave', { label: 'osc 1 wave', scope: 'osc', detents: [Wave.TRI, Wave.SAW, Wave.SQUARE] });
  engineKnob($('oscs'), 'OSC 2', 'wave', { label: 'osc 2 wave', scope: 'osc', detents: [Wave.TRI, Wave.SAW, Wave.SQUARE] });
  engineKnob($('oscs'), 'SUB', 'wave', { label: 'sub wave', scope: 'sub', detents: [Wave.SUB_SQUARE] });
  engineKnob($('oscs'), 'OSC 2', 'freq', { label: 'osc 2 freq' });
  engineSwitch($('switches'), 'FILTER', 'mode', ['4P LP', '2P LP', 'BP', 'HP'], { label: 'filter mode' });
  engineSwitch($('switches'), 'OSC 2', 'sync 1>2', ['off', 'on'], { label: 'sync 1›2' });
  engineSwitch($('switches'), 'OSC 1', 'octave', ["32'", "16'", "8'", "4'"], { label: 'osc 1 octave' });

  // the part's level: a fader, 0 dB a detent
  const sendLevel = Wire.throttled(v => Wire.call('part_set', { row: G.row, level_db: Math.round(v * 2) / 2 }));
  level = Kit.fader($('faders'), {
    label: 'level', lo: -30, hi: 10, value: 0, detents: [0], step: 0.5,
    fmt: v => (v > 0 ? '+' : '') + v.toFixed(1) + ' dB',
    onChange: v => sendLevel(v), onEnd: () => log(`level: ${level.get().toFixed(1)} dB`),
    onReset: () => { level.set(0, false); Wire.call('part_set', { row: G.row, level_db: 0 }); log('level: 0 dB'); },
  });

  // a display field and the dial (not sent)
  const fields = [];
  let sel = null;
  const pick = f => { sel = f; fields.forEach(x => x.select(x === f)); };
  [['LEVEL', 0, 127, 100], ['PAN', -64, 63, 0, v => (v < 0 ? 'L' + -v : v > 0 ? 'R' + v : '0')], ['REVERB', 0, 127, 40], ['KEY', -24, 24, 0, v => (v > 0 ? '+' : '') + v]]
    .forEach(([label, lo, hi, value, fmt]) => {
      const f = Kit.field($('fields'), { label, lo, hi, value, fmt, onSelect: c => pick(c), onChange: v => {} });
      fields.push(f);
    });
  pick(fields[0]);
  Kit.dial($('jog'), { onStep: d => { if (sel) sel.nudge(d); } });
}

Wire.connect({
  async open() {
    const h = await Wire.call('hello');
    G.knobs = h.knobs || [];
    const p = await Wire.call('parts');
    G.parts = p.parts || [];
    // the first part that is a synth
    let found = null;
    for (const part of G.parts) {
      const s = await Wire.call('select', { row: part.row });
      if (s.synth && s.synth.layers > 0) { found = part; G.row = part.row; apply(s.synth); break; }
    }
    if (!$('filter').childNodes.length) build();
    if (found) { await Wire.call('select', { row: G.row }); refresh(); }
    $('who').textContent = found ? `part ${found.row + 1} · ${found.name}` : 'no synth part: the knobs move, nothing hears them';
    const lv = G.parts[G.row]; if (lv && level) level.set(lv.level_db, false);
  },
  push(m) {
    if (m.synth && m.synth.row === G.row) apply(m.synth);
    if (m.parts) { G.parts = m.parts; const lv = G.parts[G.row]; if (lv && level) level.set(lv.level_db); }
  },
  down() { $('who').textContent = 'the engine stopped'; },
});
