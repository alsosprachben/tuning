// THE TOUCH INTERFACE: the front panel (the display, its seven fields, the
// dial, the part keys), the card keys, and the cards -- Parts and Library
// Synth and Stops now.
//
// Values the engine pushes (parts, meters, a knob turned on a Messenger)
// never fight a finger: a control under one ignores them (kit.js), and a
// value just changed here is laid over what the engine pushes for HOLD_MS,
// till the engine has caught up -- so every view of it shows the same.
'use strict';

const $ = id => document.getElementById(id);
const S = {
  parts: [], row: 0, layer: 0, knobs: [], synth: null,
  patches: [], favs: new Set(), favsKept: false, fam: 'all', build: null, picking: null,
  stops: null, organs: [], drawnMine: null,
  about: null, stopTouched: null,
};
const HOLD_MS = 700;
const FAMILIES = ['Piano', 'Chromatic Perc.', 'Organ', 'Guitar', 'Bass', 'Strings', 'Ensemble', 'Brass',
  'Reed', 'Pipe', 'Synth Lead', 'Synth Pad', 'Synth Effects', 'Ethnic', 'Percussive', 'Sound Effects'];
const NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const note = n => NOTES[n % 12] + (Math.floor(n / 12) - 1);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const pad = (n, k) => String(n).padStart(k, '0');
const signed = v => (v > 0 ? '+' : '') + v;
const dbText = v => (v > 0 ? '+' : '') + v.toFixed(1);
const panText = v => (v < 64 ? 'L' + (64 - v) : v > 64 ? 'R' + (v - 64) : 'C');
const cur = () => S.parts[S.row];
// a patch's family: GM's sixteen by program, the drum kits, and the MT-32's
// and CM-32P's own tones (banks 127, 126: under GM's numbers, not its families)
const BANKS = { 127: ['mt32', 'MT-32'], 126: ['cm32p', 'CM-64 PCM'] };
const famOf = p => (p.drums ? 'drums' : BANKS[p.variation] ? BANKS[p.variation][0] : String(p.program >> 3));
const famLabel = p => (p.drums ? 'Drum kits' : BANKS[p.variation] ? BANKS[p.variation][1] : FAMILIES[p.program >> 3]);
const famName = p => (p.drums ? 'DRUM SET' : famLabel(p).toUpperCase());

// changed here a moment ago ("row:field" -> value, until): laid over the
// engine's pushes till then
const mine = new Map();
function keep(row, args) {
  const p = S.parts[row], until = performance.now() + HOLD_MS;
  for (const k in args) { mine.set(row + ':' + k, { v: args[k], until }); if (p) p[k] = args[k]; }
}
function overlay(ps) {
  const now = performance.now();
  for (const [k, m] of mine) {
    if (m.until < now) { mine.delete(k); continue; }
    const [row, f] = k.split(':'), p = ps[+row];
    if (p) p[f] = m.v;
  }
}

// a part's edit, merged with what it has (uiapi's part_set)
function partSet(row, args) {
  keep(row, args);
  return Wire.call('part_set', { row, ...args });
}

// ---------------------------------------------------------------- THE DISPLAY
const bars = [];
(function makeBars() {
  for (let ch = 0; ch < 16; ch++) {
    const b = document.createElement('div'); b.className = 'bar';
    const segs = [];
    for (let i = 0; i < 10; i++) { const s = document.createElement('i'); b.appendChild(s); segs.push(s); }
    $('bars').appendChild(b); bars.push(segs);
    const n = document.createElement('span'); n.textContent = ch + 1; $('barn').appendChild(n);
  }
})();

// the seven fields: [label, lo, hi, text, from the part, to the engine, reset]
// (LEVEL in half dB: the field steps by one)
const FIELDS = [
  ['LEVEL', -60, 20, v => dbText(v / 2), p => Math.round(p.level_db * 2), (r, v) => partSet(r, { level_db: v / 2 }), 0],
  ['PAN', 0, 127, panText, p => p.pan, (r, v) => cc(r, 10, v), 64],
  ['REVERB', 0, 127, String, p => p.reverb, (r, v) => cc(r, 91, v), 40],
  ['CHORUS', 0, 127, String, p => p.chorus, (r, v) => cc(r, 93, v), 0],
  ['DELAY', 0, 127, String, p => p.delay, (r, v) => cc(r, 94, v), 0],
  ['KEY', -24, 24, signed, p => p.transpose, (r, v) => partSet(r, { transpose: v }), 0],
  ['CH', 0, 16, v => (v ? String(v) : 'ALL'), p => p.channel + 1, (r, v) => partSet(r, { channel: v - 1 }), null],
];
const CC_KEY = { 10: 'pan', 91: 'reverb', 93: 'chorus', 94: 'delay' };
function cc(row, n, v) {
  keep(row, { [CC_KEY[n]]: v });
  return Wire.call('part_cc', { row, cc: n, v });
}

const fields = [];
let selField = null;
FIELDS.forEach(([label, lo, hi, fmt, from, to, reset]) => {
  const send = Wire.throttled(v => { to(S.row, v); changed(); });
  const f = Kit.field($('fields'), {
    label, lo, hi, value: 0, fmt,
    travel: Math.max(160, 3 * (hi - lo + 1)),
    onSelect: c => pickField(c),
    onChange: v => send(v),
    onReset: reset === null ? undefined : () => { f.set(reset); to(S.row, reset); changed(); },
    onInfo: () => Kit.sheet({
      title: label, text: fmt(f.get()), label: 'Value', value: f.get(), digits: 0, lo, hi,
      hint: label === 'LEVEL' ? 'In half decibels: 0 is 0 dB, -12 is -6 dB.' : label === 'CH' ? '0 is every channel.' : '',
      onSet: v => { f.set(Math.round(v)); to(S.row, Math.round(v)); changed(); },
    }),
  });
  f.label = label; f.from = from;
  fields.push(f);
});
function pickField(f) { selField = f; fields.forEach(x => x.select(x === f)); $('jogwho').textContent = f.label; }
pickField(fields[0]);
Kit.dial($('jog'), { onStep: d => { if (selField) selField.nudge(d); } });

// a field moved here: the rest of the screen shows it at once
function changed() { drawDisplay(); drawStrips(); }

function drawDisplay() {
  const p = cur();
  $('partno').textContent = p ? pad(S.row + 1, 2) : '--';
  $('patch').textContent = p ? p.name : '';
  $('family').textContent = p
    ? (p.drums ? 'DRUM SET ' + p.program : 'PROGRAM ' + pad(p.program, 3) + (p.variation ? '.' + p.variation : '') + ' · ' + famName(p)) +
      (p.channel < 0 ? ' · ALL CH' : ' · CH ' + (p.channel + 1))
    : '';
  if (p) fields.forEach(f => f.set(f.from(p)));
  $('mute').classList.toggle('on', !!(p && p.muted));
  $('solo').classList.toggle('on', !!(p && p.solo === 1));
  drawHealth();
}

let lastMeters = null;
function drawMeters(m) {
  lastMeters = m;
  m.bars.forEach((db, ch) => {
    const k = Math.round((db + 40) / 40 * 10);
    bars[ch].forEach((s, i) => s.classList.toggle('lit', i < k));
  });
  ['pkL', 'pkR'].forEach((id, c) => {
    const db = m.peak[c], w = Math.max(0, Math.min(100, (db + 48) / 48 * 100));
    $(id).style.width = w + '%'; $(id).classList.toggle('hot', db > -1);
  });
  const cpu = m.budget_ms > 0 ? Math.round(100 * m.ms_mean / m.budget_ms) : 0;
  // (fixed widths, the words still while the numbers move: the display is monospaced)
  $('cpu').textContent = (m.gpu ? 'GPU+CPU' : 'CPU').padEnd(8) + (Math.min(cpu, 999) + '%').padStart(5);
  $('voices').textContent = 'VOICES'.padEnd(8) + String(Math.min(Math.round(m.voices), 99999)).padStart(5);
  drawHealth();
}
function drawHealth() {
  const b = S.build, m = lastMeters;
  let t = '';
  if (b && b.n > 0) t = 'BUILDING' + (b.total > 0 ? ' ' + Math.round(100 * b.done / b.total) + '%' : '');
  else if (m && m.underruns) t = `UNDERRUNS ${m.underruns}`;
  else if (m && m.rt_dropped) t = 'RT DROPPED';
  $('health').textContent = t;
  $('health').classList.toggle('busy', !!(b && b.n > 0));
}

// ---------------------------------------------------------------- THE PART KEYS
async function select(row) {
  if (row < 0 || row >= S.parts.length) return;
  S.row = row; S.layer = 0;
  drawDisplay(); drawStrips(); drawKeyboard(); drawTiles(false); drawAbout();
  const s = await Wire.call('select', { row, layer: 0 });
  S.synth = s.synth; drawSynth();
  if (s.stops && s.stops.row === S.row) setStops(s.stops);
  if (card === 'piano') { const r = await Wire.call('piano'); if (r.piano) setPiano(r.piano); }
  if (card === 'drums') { DR.sel = null; const r = await Wire.call('drums'); if (r.drums) setDrums(r.drums); }
}
Kit.press($('prev'), () => select(S.row - 1));
Kit.press($('next'), () => select(S.row + 1));
Kit.press($('mute'), () => { const p = cur(); if (p) { partSet(S.row, { muted: p.muted ? 0 : 1 }); drawDisplay(); drawStrips(); drawKeyboard(); } });
Kit.press($('solo'), () => soloPart(S.row));
Kit.press($('panic'), () => Wire.call('panic'));
async function soloPart(row) {
  await Wire.call('part_solo', { row });
  const r = await Wire.call('parts'); if (r.parts) setParts(r.parts);
}

// ---------------------------------------------------------------- THE CARD KEYS
const CARDS = [
  ['parts', 'Parts', true], ['library', 'Library', true], ['synth', 'Synth', true],
  ['stops', 'Stops', true], ['piano', 'Piano', true], ['drums', 'Drums', true], ['effects', 'Effects'],
  ['matrix', 'Matrix'], ['tuning', 'Tuning'], ['control', 'Control'], ['scenes', 'Scenes'], ['setup', 'Setup'],
];
const LATER = {
  effects: 'the insertion effect and the reverb, chorus, delay and EQ',
  matrix: 'what each controller moves', tuning: 'the tuner, pitch standard and the Eastern systems',
  control: 'on-screen controls, routes and learn', scenes: 'presets, scenes, the GS reset and the metronome',
  setup: 'MIDI, audio, borrowed time and the globals',
};
let card = 'parts';
try { card = localStorage.getItem('clavitone.card') || 'parts'; } catch (_) {}
if (card === 'organ') card = 'stops';
CARDS.forEach(([id, label, ready]) => {
  const b = document.createElement('button');
  b.className = 'ck' + (ready ? '' : ' later'); b.dataset.kit = '1'; b.dataset.id = id; b.textContent = label;
  Kit.press(b, () => showCard(id));
  $('keys').appendChild(b);
});
function showCard(id) {
  card = id;
  try { localStorage.setItem('clavitone.card', id); } catch (_) {}
  const ready = CARDS.find(c => c[0] === id)?.[2];
  document.querySelectorAll('#keys .ck').forEach(b => b.classList.toggle('on', b.dataset.id === id));
  document.querySelectorAll('#deck > .card').forEach(c => { c.hidden = c.dataset.card !== (ready ? id : 'later'); });
  if (!ready) $('later').textContent = `${CARDS.find(c => c[0] === id)[1]}: ${LATER[id]}. This card comes in a later step.`;
  if (id === 'parts') { drawKeyboard(); drawStrips(); }
  if (id === 'library') drawTiles(true);
  if (id === 'synth') drawSynth();
  if (id === 'stops') drawStops();
  Wire.call('piano', { open: id === 'piano' ? 1 : 0 }).then(r => { if (r.piano) setPiano(r.piano); });
  Wire.call('drums', { open: id === 'drums' ? 1 : 0, sets: DR.sets ? 0 : 1 }).then(r => { if (r.drums) setDrums(r.drums); });
}

// ---------------------------------------------------------------- PARTS: the keyboard and the parts' ranges
const KB = { lo: 0, hi: 127, W: 1000, keyH: 56, laneH: 20, drag: null };
const isBlack = n => [1, 3, 6, 8, 10].includes(n % 12);
const whiteIdx = n => { let k = 0; for (let i = 0; i < n; i++) if (!isBlack(i)) k++; return k; };
const NWHITE = whiteIdx(128);
function keyLeft(n) { const ww = KB.W / NWHITE; return isBlack(n) ? whiteIdx(n) * ww - ww * 0.3 : whiteIdx(n) * ww; }
function keyRight(n) { const ww = KB.W / NWHITE; return isBlack(n) ? whiteIdx(n) * ww + ww * 0.3 : (whiteIdx(n) + 1) * ww; }
function keyAt(x) {            // the key under x (viewBox units): nearest centre
  let best = 0, bd = 1e9;
  for (let n = 0; n < 128; n++) { const d = Math.abs((keyLeft(n) + keyRight(n)) / 2 - x); if (d < bd) { bd = d; best = n; } }
  return best;
}
function drawKeyboard() {
  if (card !== 'parts') return;
  const el = $('kb'), n = S.parts.length;
  KB.W = Math.max(600, el.clientWidth || 1000);
  KB.laneH = Math.max(10, Math.min(24, Math.floor(150 / Math.max(1, n))));
  const H = KB.keyH + 16 + n * KB.laneH + 4;
  let s = `<svg viewBox="0 0 ${KB.W} ${H}" width="${KB.W}" height="${H}">`;
  for (let k = 0; k < 128; k++) if (!isBlack(k)) s += `<rect class="wk" x="${keyLeft(k)}" y="0" width="${keyRight(k) - keyLeft(k) - 1}" height="${KB.keyH}"/>`;
  for (let k = 0; k < 128; k++) if (isBlack(k)) s += `<rect class="bk" x="${keyLeft(k)}" y="0" width="${keyRight(k) - keyLeft(k)}" height="${KB.keyH * 0.62}"/>`;
  for (let k = 0; k < 128; k += 12) s += `<text class="oct" x="${keyLeft(k) + 3}" y="${KB.keyH + 13}">${note(k)}</text>`;
  S.parts.forEach((p, i) => {
    const y = KB.keyH + 16 + i * KB.laneH, x0 = keyLeft(p.lo), x1 = keyRight(p.hi);
    const cls = 'lane' + (p.row === S.row ? ' sel' : '') + (p.muted || p.solo === 2 ? ' dim' : '');
    s += `<g class="${cls}" data-row="${p.row}"><rect class="lane-bar" x="${x0}" y="${y + 1}" width="${Math.max(4, x1 - x0)}" height="${KB.laneH - 3}" rx="3"/>`;
    if (KB.laneH >= 14) s += `<text class="lane-t" x="${x0 + 6}" y="${y + KB.laneH * 0.68}">${pad(p.row + 1, 2)} ${esc(p.name)}  ${note(p.lo)}–${note(p.hi)}</text>`;
    s += `<rect class="lane-end" x="${x0}" y="${y + 1}" width="5" height="${KB.laneH - 3}"/><rect class="lane-end" x="${x1 - 5}" y="${y + 1}" width="5" height="${KB.laneH - 3}"/></g>`;
  });
  el.innerHTML = s + '</svg>';
}
// a lane: tap selects its part; a drag near an end moves that end (by key)
(function laneDrag() {
  const el = $('kb');
  el.style.touchAction = 'none';
  const vx = e => { const r = el.querySelector('svg').getBoundingClientRect(); return (e.clientX - r.left) * KB.W / r.width; };
  const send = Wire.throttled(({ row, lo, hi }) => partSet(row, { lo, hi }));
  el.addEventListener('pointerdown', e => {
    const g = e.target.closest('.lane');
    if (!g || KB.drag) return;
    const row = +g.dataset.row, p = S.parts[row], x = vx(e);
    const pxPerUnit = el.querySelector('svg').getBoundingClientRect().width / KB.W;
    const near = 28 / pxPerUnit;           // (a fingertip from an end)
    const dl = Math.abs(x - keyLeft(p.lo)), dr = Math.abs(x - keyRight(p.hi));
    const end = dl < near && dl <= dr ? 'lo' : dr < near ? 'hi' : null;
    KB.drag = { id: e.pointerId, row, end, moved: false, x0: e.clientX };
    el.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  el.addEventListener('pointermove', e => {
    const d = KB.drag;
    if (!d || e.pointerId !== d.id || !d.end) return;
    if (!d.moved && Math.abs(e.clientX - d.x0) < 6) return;
    d.moved = true;
    const p = S.parts[d.row], k = keyAt(vx(e));
    if (d.end === 'lo') p.lo = Math.min(k, p.hi); else p.hi = Math.max(k, p.lo);
    keep(d.row, { lo: p.lo, hi: p.hi });
    send({ row: d.row, lo: p.lo, hi: p.hi });
    drawKeyboard(); bubbleRange(e, p);
  });
  const up = e => {
    const d = KB.drag;
    if (!d || e.pointerId !== d.id) return;
    KB.drag = null; $('kbBubble')?.remove();
    if (!d.moved) select(d.row); else drawStrips();
  };
  el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up);
  function bubbleRange(e, p) {
    let b = $('kbBubble');
    if (!b) { b = document.createElement('div'); b.id = 'kbBubble'; b.className = 'kit-bubble'; document.body.appendChild(b); }
    b.textContent = `${note(p.lo)} – ${note(p.hi)}`;
    b.style.left = Math.max(4, e.clientX - b.offsetWidth / 2) + 'px'; b.style.top = Math.max(4, e.clientY - 90) + 'px';
  }
})();
addEventListener('resize', () => drawKeyboard());

// ---------------------------------------------------------------- PARTS: the channel strips
let stripSig = '';
const strips = [];
function drawStrips() {
  if (card !== 'parts') return;
  const sig = S.parts.map(p => p.row).join(',');
  if (sig !== stripSig) buildStrips(sig);
  S.parts.forEach((p, i) => {
    const st = strips[i]; if (!st) return;
    st.el.classList.toggle('sel', p.row === S.row);
    st.el.classList.toggle('dim', !!(p.muted || p.solo === 2));
    st.name.textContent = p.name;
    st.detail.textContent = `${p.drums ? 'drums' : 'prog ' + pad(p.program, 3) + (p.variation ? '.' + p.variation : '')} · ${note(p.lo)}–${note(p.hi)}`;
    st.pan.set(p.pan / 127, panText(p.pan), p.pan !== 64);
    st.level.set(p.level_db, p.level_db !== 0);
    st.key.set(p.transpose);
    st.ch.set(p.channel + 1);
    st.mute.classList.toggle('on', !!p.muted);
    st.solo.classList.toggle('on', p.solo === 1);
    st.touch.textContent = p.touch_fixed ? 'FIXED' : 'VEL';
    st.touch.classList.toggle('on', !!p.touch_fixed);
  });
}
function buildStrips(sig) {
  stripSig = sig;
  const box = $('strips'); box.innerHTML = ''; strips.length = 0;
  S.parts.forEach(p => {
    const row = p.row;
    const el = document.createElement('div'); el.className = 'strip';
    const head = document.createElement('div'); head.className = 'st-head'; head.dataset.kit = '1';
    head.innerHTML = `<span class="st-n">${pad(row + 1, 2)}</span><span class="st-name"></span><span class="st-d"></span>`;
    Kit.press(head, () => select(row));
    el.appendChild(head);
    // the fader on the left; the pan knob, KEY and CH beside it
    const body = document.createElement('div'); body.className = 'st-body'; el.appendChild(body);
    const faders = document.createElement('div'); faders.className = 'st-fader'; body.appendChild(faders);
    const side = document.createElement('div'); side.className = 'st-side'; body.appendChild(side);
    const knobs = document.createElement('div'); knobs.className = 'st-knob'; side.appendChild(knobs);
    const sendPan = Wire.throttled(v => cc(row, 10, v));
    const pan = Kit.knob(knobs, {
      label: 'pan', value: 0.5, centred: true, detents: [64 / 127],
      fmt: v => panText(Math.round(v * 127)),
      onChange: v => { keep(row, { pan: Math.round(v * 127) }); sendPan(Math.round(v * 127)); if (row === S.row) drawDisplay(); },
      onReset: () => { cc(row, 10, 64); pan.set(64 / 127, 'C', false); if (row === S.row) drawDisplay(); },
    });
    const sendLvl = Wire.throttled(v => partSet(row, { level_db: Math.round(v * 2) / 2 }));
    const level = Kit.fader(faders, {
      label: 'level', lo: -30, hi: 10, value: 0, detents: [0], step: 0.5, travel: 220,
      fmt: v => dbText(v) + ' dB',
      onChange: v => { keep(row, { level_db: Math.round(v * 2) / 2 }); sendLvl(v); if (row === S.row) drawDisplay(); },
      onReset: () => { level.set(0, false); partSet(row, { level_db: 0 }); if (row === S.row) drawDisplay(); },
    });
    const fl = document.createElement('div'); fl.className = 'st-fields lcd'; side.appendChild(fl);
    const ms = document.createElement('div'); ms.className = 'st-ms'; el.appendChild(ms);
    const mute = document.createElement('button'); mute.className = 'hb led'; mute.textContent = 'MUTE'; mute.dataset.kit = '1';
    Kit.press(mute, () => { const q = S.parts[row]; partSet(row, { muted: q.muted ? 0 : 1 }); drawStrips(); drawDisplay(); drawKeyboard(); });
    const solo = document.createElement('button'); solo.className = 'hb led'; solo.textContent = 'SOLO'; solo.dataset.kit = '1';
    Kit.press(solo, () => soloPart(row));
    ms.append(mute, solo);
    const sendKey = Wire.throttled(v => partSet(row, { transpose: v }));
    const key = Kit.field(fl, {
      label: 'KEY', lo: -24, hi: 24, value: 0, fmt: signed, travel: 200,
      onChange: v => { keep(row, { transpose: v }); sendKey(v); if (row === S.row) drawDisplay(); },
      onReset: () => { key.set(0); partSet(row, { transpose: 0 }); if (row === S.row) drawDisplay(); },
    });
    const sendCh = Wire.throttled(v => partSet(row, { channel: v - 1 }));
    const ch = Kit.field(fl, {
      label: 'CH', lo: 0, hi: 16, value: 0, fmt: v => (v ? String(v) : 'ALL'), travel: 160,
      onChange: v => { keep(row, { channel: v - 1 }); sendCh(v); if (row === S.row) drawDisplay(); },
    });
    const touch = document.createElement('button'); touch.className = 'hb led st-touch'; touch.dataset.kit = '1';
    Kit.press(touch, () => { const q = S.parts[row]; q.touch_fixed = !q.touch_fixed; Wire.call('part_touch', { row, fixed: q.touch_fixed ? 1 : 0 }); drawStrips(); });
    ms.appendChild(touch);
    box.appendChild(el);
    strips.push({ el, name: head.querySelector('.st-name'), detail: head.querySelector('.st-d'), pan, level, key, ch, mute, solo, touch });
  });
}
async function partAct(name) {
  const r = await Wire.call(name, { row: S.row });
  $('partsMsg').textContent = r.ok ? '' : r.error || '';
  if (r.parts) setParts(r.parts);
}
Kit.press($('layer'), () => partAct('part_layer'));
Kit.press($('split'), () => partAct('part_split'));
Kit.press($('remove'), () => partAct('part_delete'));

// ---------------------------------------------------------------- THE LIBRARY
const famList = [['fav', '★ Favourites'], ['all', 'All'], ...FAMILIES.map((f, i) => [String(i), f]), ['drums', 'Drum kits'],
  ...Object.values(BANKS)];
famList.forEach(([id, label]) => {
  const b = document.createElement('button'); b.className = 'fam'; b.dataset.id = id; b.dataset.kit = '1'; b.textContent = label;
  Kit.press(b, () => { S.fam = id; $('q').value = ''; drawTiles(true); });
  $('fams').appendChild(b);
});
const favKey = p => `${p.drums ? 1 : 0}:${p.program}.${p.variation}`;
const isCur = (p, q) => q && !!q.drums === !!p.drums && q.program === p.program && (q.drums || q.variation === p.variation);
function shown() {
  const words = $('q').value.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length) {
    return S.patches.filter(p => {
      const t = `${pad(p.program, 3)} ${p.name} ${famLabel(p)}`.toLowerCase();
      return words.every(w => t.includes(w));
    });
  }
  if (S.fam === 'all') return S.patches;
  if (S.fam === 'fav') return S.patches.filter(p => S.favs.has(favKey(p)));
  return S.patches.filter(p => famOf(p) === S.fam);
}
let tilesSig = '';
function drawTiles(force) {
  if (card !== 'library') return;
  const searching = $('q').value.trim() !== '';
  document.querySelectorAll('#fams .fam').forEach(b => b.classList.toggle('on', !searching && b.dataset.id === S.fam));
  const list = shown(), p0 = cur();
  const sig = list.length + '|' + $('q').value + '|' + S.fam + '|' + [...S.favs].join();
  if (force || sig !== tilesSig) {
    tilesSig = sig;
    $('tiles').innerHTML = list.length ? list.map(p =>
      `<button class="tile" data-kit="1" data-pick="${p.pick}"><span class="pn">${p.drums ? '<i>KIT </i>' + p.program : pad(p.program, 3) + (p.variation ? '<i>.' + p.variation + '</i>' : '')}</span>` +
      `<span class="nm">${esc(p.name)}</span><span class="star${S.favs.has(favKey(p)) ? ' on' : ''}" data-fav="${favKey(p)}">★</span></button>`).join('')
      : `<p class="empty">${S.fam === 'fav' && !searching ? 'No favourites yet: tap a patch\'s star to keep it here.' : 'Nothing matches.'}</p>`;
  }
  const byPick = new Map(S.patches.map(p => [String(p.pick), p]));
  $('tiles').querySelectorAll('.tile').forEach(t => {
    const p = byPick.get(t.dataset.pick);
    t.classList.toggle('cur', isCur(p, p0));
    t.classList.toggle('pending', S.picking === p.pick);
  });
  $('libInfo').textContent = `${list.length} patch${list.length === 1 ? '' : 'es'} · tap to play on part ${pad(S.row + 1, 2)}` +
    (S.favsKept ? '' : ' · (no session: stars are not kept)');
}
Kit.press($('tiles'), async (t, e) => {
  const star = e.target.closest('.star');
  if (star) {
    const k = star.dataset.fav;
    if (S.favs.has(k)) S.favs.delete(k); else S.favs.add(k);
    star.classList.toggle('on', S.favs.has(k));
    Wire.call('favourites_set', { favourites: [...S.favs] });
    if (S.fam === 'fav') drawTiles(true);
    return;
  }
  S.picking = +t.dataset.pick;
  drawTiles(false);
  await Wire.call('part_pick', { row: S.row, pick: S.picking });
}, '.tile');
$('q').addEventListener('input', () => drawTiles(true));

// the on-screen keys for the search (a touch screen with no keyboard; on a
// tablet the system's own comes up instead)
const ownKeys = /Linux/.test(navigator.userAgent) && !/Android/.test(navigator.userAgent);
if (ownKeys) {
  $('q').setAttribute('inputmode', 'none');
  const rows = ['1234567890', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm'];
  $('osk').innerHTML = rows.map(r => `<div>${[...r].map(c => `<button data-k="${c}">${c}</button>`).join('')}</div>`).join('') +
    '<div><button data-k="clear" class="w">CLEAR</button><button data-k=" " class="space">SPACE</button><button data-k="back" class="w">⌫</button><button data-k="done" class="w">DONE</button></div>';
  $('osk').querySelectorAll('button').forEach(b => { b.dataset.kit = '1'; });
  $('osk').addEventListener('pointerdown', e => {
    const b = e.target.closest('button'); if (!b) return;
    e.preventDefault();
    const k = b.dataset.k, q = $('q');
    if (k === 'done') { $('osk').hidden = true; q.blur(); return; }
    q.value = k === 'clear' ? '' : k === 'back' ? q.value.slice(0, -1) : q.value + k;
    drawTiles(true);
  });
  $('q').addEventListener('focus', () => { $('osk').hidden = false; });
  // (a touch anywhere else puts the keys away: a tile, a family, another card)
  document.addEventListener('pointerdown', e => {
    if ($('osk').hidden || e.target.closest('#osk, #q')) return;
    $('osk').hidden = true; $('q').blur();
  }, true);
}

// ---------------------------------------------------------------- THE SYNTH CARD
// The selected part's Moog panel, laid out as any analog synth reads, the
// sound flowing left to right: the oscillators, the mixer, the filter, the
// two envelopes, the modulation, the delay. Built from the engine's knob
// table (nv_host_synth_knobs: each knob's column, group, generic label and a
// switch's words), so nothing here names a knob but the layout hints below.
// Orange is changed from the patch: double-tap a control to put it back.
const SY = { sig: '', ctl: {} };
// (a switch's look: a vertical stack where its words are long or many)
const vertical = k => k.steps.length > 2 || k.words.some(w => w.length > 6);
const isToggle = k => k.steps.length === 2 && k.words.join() === 'off,on';
function synthCtl(parent, k, i) {
  const send = Wire.throttled(async v => {
    const r = await Wire.call('synth_set', { row: S.row, layer: S.layer, knob: k.knob, v });
    if (r.text !== undefined && SY.ctl[i] && SY.ctl[i].text) SY.ctl[i].text(r.text);
  });
  const forget = async () => { await Wire.call('synth_forget', { row: S.row, layer: S.layer, knob: k.knob }); refreshSynth(); };
  if (k.steps.length) {
    const box = document.createElement('div'); box.className = 'sy-sw';
    parent.appendChild(box);
    if (isToggle(k)) {
      const c = Kit.toggle(box, { label: k.generic, value: false, onChange: on => { send(on ? k.steps[1] : k.steps[0]); markOwn(i); } });
      SY.ctl[i] = { set: (v, t, own) => { c.set(v !== 0); c.el.classList.toggle('own', own); }, el: c.el };
    } else {
      const c = Kit.segments(box, { label: k.generic, options: k.words, value: 0,
        onChange: x => { send(k.steps[x]); markOwn(i); } });
      if (vertical(k)) c.el.classList.add('v');
      SY.ctl[i] = { set: (v, t, own) => { const j = k.steps.findIndex(st => Math.abs(st - v) < 1e-6); if (j >= 0) c.set(j); c.el.classList.toggle('own', own); }, el: c.el };
    }
    // (double-tap the label: back to the patch's)
    let last = 0;
    SY.ctl[i].el.querySelector('.kit-label').addEventListener('pointerup', () => { const t = performance.now(); if (t - last < 350) forget(); last = t; });
    return;
  }
  const wave = k.kind === 'wave' ? 'osc' : k.kind === 'subwave' ? 'sub' : null;
  let text = '';
  const c = Kit.knob(parent, {
    label: k.generic, value: 0, centred: k.centred,
    detents: wave === 'osc' ? [Wave.TRI, Wave.SAW, Wave.SQUARE] : wave === 'sub' ? [Wave.SUB_SQUARE] : k.centred ? [0.5] : [],
    scope: wave, size: k.kind === 'hz' ? 'big' : undefined,
    fmt: () => text,                              // (the engine's words: each set answers with them)
    onChange: v => send(v),
    onReset: forget,
    onInfo: () => Kit.sheet({
      title: `${k.group} ${k.generic}`, text, value: c.get(),
      hint: `The knob's position, 0 to 1${k.centred ? ' (0.5 the centre)' : ''}. The Messenger calls it ${k.section} ${k.label}.`,
      onSet: async v => { const r = await Wire.call('synth_set', { row: S.row, layer: S.layer, knob: k.knob, v }); c.set(v, r.text, true); },
      onReset: forget,
    }),
  });
  SY.ctl[i] = {
    set: (v, t, own) => { text = t; c.set(v, t, own); },
    text: t => { text = t; c.el.querySelector('.kit-value').textContent = t; },
    el: c.el,
  };
}
function markOwn(i) { const c = SY.ctl[i]; if (c) c.el.classList.add('own'); }
function buildSynth() {
  const el = $('synth');
  el.innerHTML = ''; SY.ctl = {};
  const cols = new Map();
  // (in the card's order: its columns as the sound flows, each group's knobs as a player reads them)
  const order = S.knobs.map((k, i) => i).filter(i => S.knobs[i].column).sort((a, b) => S.knobs[a].at - S.knobs[b].at);
  order.forEach(i => {
    const k = S.knobs[i];
    if (!cols.has(k.column)) {
      const c = document.createElement('section'); c.className = 'sy-col'; c.dataset.col = k.column;
      c.innerHTML = `<h3>${esc(k.column)}</h3>`;
      el.appendChild(c); cols.set(k.column, { el: c, groups: new Map() });
    }
    const col = cols.get(k.column);
    if (!col.groups.has(k.group)) {
      const g = document.createElement('div'); g.className = 'sy-grp'; g.dataset.grp = k.group;
      g.innerHTML = k.group !== k.column ? `<h4>${esc(k.group)}</h4><div class="sy-body"></div>` : '<div class="sy-body"></div>';
      col.el.appendChild(g); col.groups.set(k.group, g.querySelector('.sy-body'));
    }
    synthCtl(col.groups.get(k.group), k, i);
  });
}
function drawSynth() {
  const sy = S.synth, has = sy && sy.layers > 0;
  $('synthWho').textContent = has ? `part ${pad(sy.row + 1, 2)} · ${cur() ? cur().name : ''}` : '';
  $('synthEmpty').hidden = has;
  $('synth').hidden = !has;
  $('synthActs').hidden = !has;
  if (!has) {
    $('synthEmpty').textContent = sy && sy.layers < 0 ? 'Reading the part…' :
      `${cur() ? cur().name : 'This part'} is not a synth. The synth programs (Synth Lead, Synth Pad, the synth basses, brass and strings) bring their knobs here.`;
    return;
  }
  const sig = S.knobs.length + '|' + (S.knobs[0] && S.knobs[0].column);
  if (sig !== SY.sig) { SY.sig = sig; buildSynth(); }
  S.knobs.forEach((k, i) => { const c = SY.ctl[i]; if (c) c.set(sy.pn[k.knob], sy.text[i], !!sy.own[k.knob]); });
  const n = S.knobs.filter(k => sy.own[k.knob]).length;
  $('synthBack').textContent = n ? `${n} CHANGED · BACK TO THE PATCH` : 'AS THE PATCH';
  $('synthBack').disabled = !n;
  const lay = $('synthLayer');
  lay.hidden = sy.layers < 2;
  lay.querySelectorAll('button').forEach((b, j) => b.classList.toggle('on', j === S.layer));
}
async function refreshSynth() { const s = await Wire.call('synth', { row: S.row, layer: S.layer }); if (s.synth && s.synth.row === S.row) { S.synth = s.synth; if (card === 'synth') drawSynth(); } }
Kit.press($('synthBack'), async () => {
  const sy = S.synth;
  if (!sy) return;
  for (const k of S.knobs) if (sy.own[k.knob]) await Wire.call('synth_forget', { row: S.row, layer: S.layer, knob: k.knob });
  refreshSynth();
});
$('synthLayer').querySelectorAll('button').forEach((b, j) => Kit.press(b, async () => {
  S.layer = j;
  const s = await Wire.call('select', { row: S.row, layer: j });
  S.synth = s.synth; drawSynth();
}));

// ---------------------------------------------------------------- STOPS: the selected part's organ
// A stop jamb: the voice's rows as the panel has them (tonelib stop_rows),
// each row's groups apart, a tab lit when drawn. A tap draws or retires it;
// the whole registration goes to the engine, so taps faster than a block all
// land. What a file or a preset draws comes back by the poll.
const FEET = new Set(['32', '16', '10-2/3', '8', '5-1/3', '4', '2-2/3', '2', '1-3/5', '1-1/3', '1']);
function stopParts(nm, feet) {          // "principal 16" -> ["Principal", "16′"]; "mixture III" -> ["Mixture", "III"]
  const m = /^(.*?)\s+(\d+(?:-\d+\/\d+)?|[IVX]+)$/.exec(nm);
  const cap = t => t.replace(/(^|\s)\S/g, c => c.toUpperCase());
  if (!m) return [cap(nm), ''];
  return [cap(m[1]), m[2] + (feet && FEET.has(m[2]) ? '′' : '')];
}
function stopsDrawn() {
  const st = S.stops;
  const m = S.drawnMine;
  if (m && m.until > performance.now() && m.program === st.program && m.row === st.row) return m.drawn;
  S.drawnMine = null;
  return st.drawn;
}
let stopsSig = '';
function drawStops(force) {
  if (card !== 'stops') return;
  const st = S.stops, el = $('jamb');
  if (!st) { el.innerHTML = '<p class="empty">Reading the organ…</p>'; return; }
  $('stopsWho').textContent = `part ${pad(st.row + 1, 2)} · ${st.part}`;
  if (st.program < 0) {
    stopsSig = '';
    const orgs = S.organs.map(pg => S.patches.find(p => !p.drums && p.program === pg && p.variation === 0)).filter(Boolean);
    $('stopsInfo').textContent = '';
    el.innerHTML = `<p class="empty">${esc(st.part || 'This part')} has no stops. Put an organ on part ${pad(st.row + 1, 2)}:</p>` +
      `<div class="organs">${orgs.map(p => `<button class="tile" data-kit="1" data-pick="${p.pick}"><span class="pn">${pad(p.program, 3)}</span>` +
        `<span class="nm">${esc(p.name)}</span><span></span></button>`).join('')}</div>`;
    return;
  }
  const drawn = stopsDrawn();
  const sig = st.row + '|' + st.program + '|' + st.names.join(',');
  if (force || sig !== stopsSig) {
    stopsSig = sig;
    const nums = st.names.map(n => (/\s(\S+)$/.exec(n) || [])[1]).filter(t => t && /^\d/.test(t));
    const feet = nums.length > 0 && nums.every(t => FEET.has(t));
    el.innerHTML = st.rows.map(row => `<div class="jrow">${row.map(g => `<div class="jgrp">${g.map(r => {
      const [a, b] = stopParts(st.names[r] || String(r), feet);
      const f = b.endsWith('′') ? `${esc(b.slice(0, -1))}<i>′</i>` : esc(b);
      return `<button class="tab" data-kit="1" data-rank="${r}"><span class="tn">${esc(a)}</span><span class="tf">${f}</span></button>`;
    }).join('')}</div>`).join('')}</div>`).join('');
  }
  el.querySelectorAll('.tab').forEach(b => b.classList.toggle('on', !!drawn[+b.dataset.rank]));
  const k = drawn.filter(Boolean).length;
  $('stopsInfo').textContent = `${k} of ${st.names.length} drawn`;
}
Kit.press($('jamb'), (t) => {
  const st = S.stops;
  if (!st) return;
  if (t.classList.contains('tile')) {             // (an organ onto the part)
    S.picking = +t.dataset.pick;
    Wire.call('part_pick', { row: st.row, pick: S.picking });
    return;
  }
  const d = stopsDrawn().slice(), r = +t.dataset.rank;
  d[r] = d[r] ? 0 : 1;
  S.stopTouched = { program: st.program, rank: r };
  S.drawnMine = { row: st.row, program: st.program, drawn: d, until: performance.now() + HOLD_MS };
  drawStops();
  Wire.call('stops_set', { row: st.row, drawn: d });
}, '.tab, .tile');
function setStops(st) {
  if (st.row !== S.row) return;                    // (the part before: a select crossed it)
  if (S.stops && (S.stops.row !== st.row || S.stops.program !== st.program)) S.stopTouched = null;
  S.stops = st;
  drawAbout();
  drawStops();
}

// ---------------------------------------------------------------- THE PIANO CARD
// The selected part's pedals as the engine has them (a file's, the
// keyboard's, these), each damper's rest on its strings at the sustain's
// value (a half pedal: the bass's heavier dampers still touching), and the
// key held as the pedal (pushed into: the dampers lowered)
const NOTE_NAMES = ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B'];
const noteName = n => NOTE_NAMES[n % 12] + (Math.floor(n / 12) - 1);
const PN = { sus: null, mine: null };
function pedalSay(v) { return v <= 0 ? 'UP' : v >= 127 ? 'DOWN' : 'HALF ' + v; }
PN.sus = Kit.fader($('pdSus'), {
  label: 'SUSTAIN', value: 0, lo: 0, hi: 127, step: 1, travel: 300, fmt: x => pedalSay(Math.round(x)),
  onChange: v => sendPedal(64, Math.round(v)),
});
let pedalT = 0, pedalWant = null;
function sendPedal(cc, v) {               // (a drag's values at most 30 a second; the last always goes)
  PN.mine = { cc, v, until: performance.now() + HOLD_MS };
  if (S.piano && cc === 64) { S.piano.sustain = v; drawDampers(); }
  pedalWant = { cc, v };
  if (pedalT) return;
  const go = () => { pedalT = 0; if (!pedalWant) return; const w = pedalWant; pedalWant = null; Wire.call('pedal_set', { row: S.row, cc: w.cc, v: w.v }); pedalT = setTimeout(go, 33); };
  go();
}
Kit.press($('pdSoft'), () => { const on = !(S.piano && S.piano.soft); if (S.piano) S.piano.soft = on; sendPedal(67, on ? 127 : 0); drawPiano(); });
Kit.press($('pdSost'), () => { const on = !(S.piano && S.piano.sostenuto); if (S.piano) S.piano.sostenuto = on; sendPedal(66, on ? 127 : 0); drawPiano(); });
document.querySelectorAll('.pd-quick button').forEach(b => Kit.press(b, () => { const v = +b.dataset.v; PN.sus.set(v); sendPedal(64, v); drawPiano(); }));
Kit.press($('pedalLearn'), async () => {
  const on = !(S.piano && S.piano.learning);
  await Wire.call('pedal_key_learn', { on: on ? 1 : 0 });
  if (S.piano) { S.piano.learning = on; drawPiano(); }
});
Kit.press($('pedalKeys'), async t => {
  const r = await Wire.call('pedal_key_remove', { i: +t.dataset.i });
  if (!r.ok) return;
  const p = await Wire.call('piano'); if (p.piano) setPiano(p.piano);
}, '.pk-rm');
function setPiano(pn) {
  if (pn.row !== S.row) return;
  const m = PN.mine;                       // (what this screen just sent stands until the engine has it)
  if (m && m.until > performance.now()) {
    if (m.cc === 64) pn.sustain = m.v; else if (m.cc === 66) pn.sostenuto = m.v > 0; else pn.soft = m.v > 0;
  } else PN.mine = null;
  S.piano = pn;
  if (card === 'piano') drawPiano();
}
function drawPiano() {
  const pn = S.piano;
  if (!pn) return;
  $('pianoWho').textContent = `part ${pad(pn.row + 1, 2)} · ${pn.part}`;
  $('pianoInfo').textContent = pn.channel < 0 ? 'pedals on every channel' : `pedals on channel ${pn.channel + 1}`;
  $('pdSoft').classList.toggle('on', pn.soft);
  $('pdSost').classList.toggle('on', pn.sostenuto);
  PN.sus.set(pn.sustain);
  document.querySelectorAll('.pd-quick button').forEach(b => {
    const v = +b.dataset.v;
    b.classList.toggle('on', v === 64 ? pn.sustain > 0 && pn.sustain < 127 : pn.sustain === v);
  });
  drawDampers();
  const keys = pn.keys.map(k => `<div class="pk"><span class="pk-n">${noteName(k.key)}</span><span class="pk-t">${k.press ? 'held: dampers up · pushed into: down' : 'held: dampers up'}` +
    `${k.channel >= 0 ? ' · channel ' + (k.channel + 1) : ''}</span><button class="hb pk-rm" data-i="${k.i}" data-kit="1">REMOVE</button></div>`);
  if (pn.fixed_key >= 0)
    keys.push(`<div class="pk"><span class="pk-n">${noteName(pn.fixed_key)}</span><span class="pk-t">held: dampers up · pushed into: down (set when nvlive started)</span></div>`);
  $('pedalKeys').innerHTML = keys.length ? keys.join('') : '<p class="pn-note">No key is the pedal yet.</p>';
  $('pedalLearn').textContent = pn.learning ? 'PRESS THE KEY NOW… (TAP TO STOP)' : 'LEARN A KEY';
  $('pedalLearn').classList.toggle('blink', pn.learning);
  $('pianoStrings').textContent = pn.strings
    ? 'Sympathetic strings: on. The first part\'s undamped strings ring with what is played.'
    : 'Sympathetic strings: off (nvlive was started without them).';
  drawAbout();
}
function drawDampers() {
  const pn = S.piano;
  if (!pn) return;
  const W = 880, n = pn.contact.length, kw = W / 52;     // (52 white keys, A0 to C8)
  let wi = 0, felts = '', keysW = '', keysB = '';
  const lift = 110, strY = 190, kbY = 230;
  for (let i = 0; i < n; i++) {
    const note = 21 + i, black = isBlack(note);
    const x = black ? wi * kw - kw * 0.32 : wi * kw;
    const w = black ? kw * 0.64 : kw;
    const c = pn.contact[i], y = strY - 40 - (1 - c) * lift;
    felts += `<rect class="felt${c > 0.98 ? ' on' : c > 0.02 ? ' part' : ''}" x="${(x + w * 0.18).toFixed(1)}" y="${y.toFixed(1)}" width="${(w * 0.64).toFixed(1)}" height="40" rx="2"/>`;
    if (black) keysB += `<rect class="kb-b" x="${x.toFixed(1)}" y="${kbY}" width="${w.toFixed(1)}" height="58"/>`;
    else {
      keysW += `<rect class="kb-w" x="${x.toFixed(1)}" y="${kbY}" width="${(w - 1).toFixed(1)}" height="96"/>`;
      if (note % 12 === 0) keysW += `<text class="kb-l" x="${(x + w / 2).toFixed(1)}" y="${kbY + 88}">C${note / 12 - 1}</text>`;
      wi++;
    }
  }
  $('damp').innerHTML = `<line class="string" x1="0" y1="${strY}" x2="${W}" y2="${strY}"/>${felts}${keysW}${keysB}`;
  const on = pn.contact.filter(c => c > 0.98).length, off = pn.contact.filter(c => c < 0.02).length;
  $('dampSay').textContent = off === n ? 'all lifted: every string rings' : on === n ? 'all on the strings'
    : `${n - on - off} resting lightly, ${on} on the strings, ${off} lifted`;
  const band = pn.band.map(([k, lo, hi]) => `${noteName(k)} ${lo}–${hi}`).join(' · ');
  $('dampBand').textContent = `Where the dampers leave the strings, by the pedal's value: ${band}. The bass dampers are heavier and leave later.`;
}

// ---------------------------------------------------------------- THE DRUMS CARD
// The selected part's kit as pads, by kind; a pad struck harder the higher
// it is touched, lit as the keyboard or a file plays it. The kits down the
// side. A user set (GS's two): each key takes its sound from a key of any set.
const DR = { d: null, sets: null, sel: null, sig: '', touched: null };
const DRUM_KINDS = [
  ['Kicks', /kick|bass drum|\bbd\b/i], ['Snares', /snare|rim|stick|clap|snap|brush/i], ['Toms', /\btom/i],
  ['Hi-hats', /hat\b|hi-?hat|\bhh\b/i], ['Cymbals', /cymbal|crash|ride|splash|china|chinese/i],
];
const kindOf = nm => (DRUM_KINDS.find(([, re]) => re.test(nm)) || ['Percussion'])[0];
function setDrums(d) {
  if (d.row !== S.row) return;
  if (d.sets) DR.sets = d.sets;
  if (DR.d && (DR.d.kit !== d.kit)) { DR.sel = null; DR.touched = null; DR.browse = undefined; }
  DR.d = d;
  if (card === 'drums') drawDrums();
}
function drumNote(kit, key) {
  const a = S.about;
  if (!a || !a.perc) return null;
  const own = a.kits[String(kit)];
  if (own && own[key]) return own[key];
  if (own && (a.kit_only || []).includes(kit)) return null;
  return a.perc[key] || null;
}
function drawDrums() {
  const d = DR.d;
  if (!d) return;
  const kits = S.patches.filter(p => p.drums);
  $('drumsWho').textContent = `part ${pad(d.row + 1, 2)} · ${d.part}`;
  const nk = d.keys.filter(k => d.user === undefined || k[1]).length;
  $('drumsInfo').textContent = d.drums ? `${nk} key${nk === 1 ? '' : 's'} · channel ${d.channel < 0 ? 10 : d.channel + 1}` : '';
  const ksig = kits.length + '|' + d.kit;
  if (ksig !== DR.ksig) {
    DR.ksig = ksig;
    $('kits').innerHTML = kits.map(p => `<button class="kit${p.program === d.kit ? ' cur' : ''}" data-kit="1" data-pick="${p.pick}">` +
      `<span class="pn">${p.program}</span><span class="nm">${esc(p.name)}</span></button>`).join('');
    const c = $('kits').querySelector('.cur'); if (c) c.scrollIntoView({ block: 'nearest' });
  }
  const el = $('pads');
  if (!d.drums) {
    DR.sig = '';
    el.innerHTML = `<p class="empty">${esc(d.part || 'This part')} is not a drum set. Pick a kit for part ${pad(d.row + 1, 2)} from the list.</p>`;
    drawUkey(); drawDrumAbout();
    return;
  }
  const user = d.user !== undefined;
  const keys = user ? d.keys.filter(k => k[0] >= 27 && k[0] <= 87 || k[1]) : d.keys;
  const sig = d.kit + '|' + keys.map(k => k[0] + ':' + k[1]).join(',');
  if (sig !== DR.sig) {
    DR.sig = sig;
    const sfx = /sfx|sound|effect/i.test(d.part);
    const groups = new Map();
    for (const k of keys) {
      const g = user && !k[1] ? 'Not set' : sfx ? 'Sounds' : kindOf(k[1]);
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(k);
    }
    const order = ['Kicks', 'Snares', 'Toms', 'Hi-hats', 'Cymbals', 'Percussion', 'Sounds', 'Not set'];
    el.innerHTML = order.filter(g => groups.has(g)).map(g => `<section class="pgrp"><h3>${g}</h3><div class="pgrid">` +
      groups.get(g).map(k => `<button class="pad${user && !k[1] ? ' unset' : ''}" data-key="${k[0]}"><i></i>` +
        `<span class="pk">${noteName(k[0])} <small>${k[0]}</small></span><span class="pnm">${esc(k[1] || '—')}</span></button>`).join('') +
      '</div></section>').join('');
  }
  el.querySelectorAll('.pad').forEach(b => b.classList.toggle('sel', +b.dataset.key === DR.sel));
  drawUkey(); drawDrumAbout();
}
// a pad: down strikes (harder nearer its top), up releases; several fingers at once
const padDown = new Map();
$('pads').addEventListener('pointerdown', e => {
  const b = e.target.closest('.pad'); if (!b || !DR.d) return;
  e.preventDefault();
  const r = b.getBoundingClientRect(), key = +b.dataset.key;
  const v = Math.max(20, Math.min(127, Math.round(127 - 100 * (e.clientY - r.top) / r.height)));
  padDown.set(e.pointerId, key);
  Wire.call('drum_hit', { row: DR.d.row, key, v });
  if (DR.sel !== key) DR.browse = undefined;
  DR.sel = key; DR.touched = key;
  $('pads').querySelectorAll('.pad').forEach(p => p.classList.toggle('sel', p === b));
  drawUkey(); drawDrumAbout();
});
const padUp = e => { const k = padDown.get(e.pointerId); if (k === undefined) return; padDown.delete(e.pointerId); if (DR.d) Wire.call('drum_hit', { row: DR.d.row, key: k, v: 0 }); };
document.addEventListener('pointerup', padUp, true);
document.addEventListener('pointercancel', padUp, true);
function lightPads(hits) {
  if (card !== 'drums') return;
  for (const [k, v] of hits) {
    const b = $('pads').querySelector(`.pad[data-key="${k}"] i`); if (!b) continue;
    b.style.opacity = (0.35 + 0.65 * v / 127).toFixed(2);
    b.classList.remove('go'); void b.offsetWidth; b.classList.add('go');
  }
}
Kit.press($('kits'), t => { S.picking = +t.dataset.pick; Wire.call('part_pick', { row: S.row, pick: S.picking }); t.classList.add('pending'); }, '.kit');
function drawDrumAbout() {
  const d = DR.d, el = $('drumAbout');
  if (!d || !d.drums || !S.about) { el.innerHTML = ''; return; }
  const k = DR.touched;
  if (k === null) { el.innerHTML = `<p class="ab-hint">Touch a pad for what it is and what it was fitted to.</p>`; return; }
  const e = d.keys.find(x => x[0] === k);
  let kit = d.kit, key = k;
  if (d.user !== undefined) { if (!e || e[3] < 0) { el.innerHTML = ''; return; } kit = e[2]; key = e[3]; }
  const rn = drumNote(kit, key);
  el.innerHTML = rn ? aboutHtml(`${noteName(k)} ${e ? e[1] : ''}`, rn) : `<p class="ab-hint">${esc(e ? e[1] : '')}: no notes for this one.</p>`;
}
// A USER SET's key: the set its sound comes from, then that set's key
function drawUkey() {
  const d = DR.d, el = $('ukey');
  if (!d || d.user === undefined || DR.sel === null || !DR.sets) { el.innerHTML = d && d.user !== undefined ? '<p class="pn-note">A user set: touch a pad to choose its sound.</p>' : ''; return; }
  const e = d.keys.find(x => x[0] === DR.sel) || [DR.sel, '', -1, -1];
  const ss = e[3] >= 0 ? e[2] : -1;
  const set = DR.sets.find(x => x[0] === (DR.browse ?? ss)) || null;
  el.innerHTML = `<h3>Key ${noteName(DR.sel)} <small>${DR.sel}</small></h3>` +
    `<p class="pn-note">${e[3] >= 0 ? `Plays ${esc(e[1])} from ${esc((DR.sets.find(x => x[0] === ss) || [0, 'set ' + ss])[1])}.` : 'No sound yet.'}</p>` +
    `<div class="uk-cols"><div class="uk-list" id="ukSets">${DR.sets.map(x => `<button class="uk${x[0] === (set ? set[0] : ss) ? ' on' : ''}" data-kit="1" data-set="${x[0]}">${esc(x[1])}</button>`).join('')}</div>` +
    `<div class="uk-list" id="ukKeys">${set ? set[2].map(([k, nm]) => `<button class="uk${set[0] === ss && k === e[3] ? ' on' : ''}" data-kit="1" data-k="${k}">` +
      `<b>${noteName(k)}</b> ${esc(nm)}</button>`).join('') : '<p class="pn-note">Choose a set.</p>'}</div></div>`;
  for (const q of ['#ukSets .on', '#ukKeys .on']) { const on = el.querySelector(q); if (on) on.scrollIntoView({ block: 'nearest' }); }
}
Kit.press($('ukey'), async t => {
  const d = DR.d; if (!d || DR.sel === null) return;
  if (t.dataset.set !== undefined) { DR.browse = +t.dataset.set; drawUkey(); return; }
  const set = DR.browse ?? (d.keys.find(x => x[0] === DR.sel) || [])[2];
  await Wire.call('udrum_set', { set: d.user, key: DR.sel, code: 0x0B, v: set });
  await Wire.call('udrum_set', { set: d.user, key: DR.sel, code: 0x0C, v: +t.dataset.k });
  Wire.call('drum_hit', { row: d.row, key: DR.sel, v: 100 }); setTimeout(() => Wire.call('drum_hit', { row: d.row, key: DR.sel, v: 0 }), 300);
  const r = await Wire.call('drums'); if (r.drums) setDrums(r.drums);
}, '.uk');

// ---------------------------------------------------------------- THE NOTES
// What each program and stop is, and what it was fitted to (about.json:
// examples/gm_coverage.py --about, the coverage page's own words)
fetch('about.json').then(r => (r.ok ? r.json() : null)).then(a => { S.about = a; drawAbout(); }).catch(() => {});
function aboutHtml(title, rn) {
  if (!rn) return '';
  const [r, note] = rn, lv = S.about.levels[r] || '';
  return `<div class="ab-head"><b>${esc(title)}</b><span class="ab-r r${r}">${r} · ${esc(lv)}</span></div><p>${esc(note)}</p>`;
}
function patchAbout(p) {
  if (!S.about || !p || p.drums) return null;
  return S.about.programs[p.program + '.' + p.variation] || null;
}
function drawAbout() {
  const p = cur();
  $('libAbout').innerHTML = p && patchAbout(p) ? aboutHtml(p.name, patchAbout(p)) : '';
  $('pianoAbout').innerHTML = p && patchAbout(p) ? aboutHtml(p.name, patchAbout(p)) : '';
  const st = S.stops, el = $('stopAbout');
  if (!st || st.program < 0 || !S.about) { el.innerHTML = ''; return; }
  const org = S.about.stops[String(st.program)];
  const t = S.stopTouched;
  if (t !== null && t.program === st.program && org && org.stops[st.names[t.rank]])
    el.innerHTML = aboutHtml(st.names[t.rank], org.stops[st.names[t.rank]]);
  else
    el.innerHTML = aboutHtml(st.part, patchAbout(cur() && cur().row === st.row ? cur() : null)) +
      (org ? `<p class="ab-hint">${esc(org.panel)}: touch a stop for what it is.</p>` : '');
}

// ---------------------------------------------------------------- THE WIRE
function setParts(ps) {
  const before = S.parts.length;
  overlay(ps);
  S.parts = ps;
  if (S.row >= ps.length) S.row = Math.max(0, ps.length - 1);
  if (S.picking !== null) {           // (the patch asked for is the part's now)
    const want = S.patches.find(p => p.pick === S.picking);
    if (!want || isCur(want, cur())) S.picking = null;
  }
  drawDisplay(); drawStrips(); drawTiles(false); drawAbout();
  if (!KB.drag) drawKeyboard();
  if (ps.length !== before) select(S.row);
}

Wire.connect({
  async open() {
    $('gone').hidden = true;
    const h = await Wire.call('hello');
    S.knobs = h.knobs || [];
    const [p, pt, fv, so] = await Promise.all([Wire.call('parts'), Wire.call('patches'), Wire.call('favourites'), Wire.call('stops', { row: S.row })]);
    S.stops = so.stops || null; S.organs = so.organs || [];
    S.patches = pt.patches || [];
    S.favs = new Set(fv.favourites || []); S.favsKept = !!fv.kept;
    S.parts = p.parts || [];
    if (S.row >= S.parts.length) S.row = 0;
    stripSig = '';
    showCard(card);
    select(S.row);
  },
  push(m) {
    if (m.meters) drawMeters(m.meters);
    if (m.build) { S.build = m.build; drawHealth(); }
    if (m.parts) setParts(m.parts);
    if (m.stops) setStops(m.stops);
    if (m.piano) setPiano(m.piano);
    if (m.drums) setDrums(m.drums);
    if (m.hits) lightPads(m.hits);
    if (m.synth && m.synth.row === S.row && (m.synth.layer === S.layer || m.synth.layers <= S.layer)) { S.layer = m.synth.layer; S.synth = m.synth; if (card === 'synth') drawSynth(); }
  },
  down() { $('gone').hidden = false; },
});
