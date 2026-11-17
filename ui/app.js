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
  $('health').textContent = t || '\u00a0';     // (its line kept, empty: nothing above it moves)
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
  if (card === 'effects') drawEffects();
  if (card === 'control') drawControl();
  if (card === 'matrix') { const r = await Wire.call('matrix'); if (r.matrix) setMatrix(r.matrix); }
  if (card === 'drums') { DR.sel = null; const r = await Wire.call('drums'); if (r.drums) setDrums(r.drums); }
}
Kit.press($('prev'), () => select(S.row - 1));
Kit.press($('next'), () => select(S.row + 1));
Kit.press($('mute'), () => { const p = cur(); if (p) { partSet(S.row, { muted: p.muted ? 0 : 1 }); drawDisplay(); drawStrips(); drawKeyboard(); } });
Kit.press($('solo'), () => soloPart(S.row));
Kit.press($('panic'), () => Wire.call('panic'));
// QUIT (the Setup card's): a second tap within 3 s stops the engine, which
// closes this window
let quitArmed = 0;
Kit.press($('quit'), () => {
  if (Date.now() - quitArmed < 3000) { Wire.call('quit'); return; }
  quitArmed = Date.now(); $('quit').textContent = 'TAP AGAIN TO QUIT';
  setTimeout(() => { if (Date.now() - quitArmed >= 3000) $('quit').textContent = 'QUIT CLAVITONE'; }, 3100);
});
async function soloPart(row) {
  await Wire.call('part_solo', { row });
  const r = await Wire.call('parts'); if (r.parts) setParts(r.parts);
}

// ---------------------------------------------------------------- THE CARD KEYS
const CARDS = [
  ['parts', 'Parts', true], ['library', 'Library', true], ['synth', 'Synth', true],
  ['stops', 'Stops', true], ['piano', 'Piano', true], ['drums', 'Drums', true], ['effects', 'Effects', true],
  ['matrix', 'Matrix', true], ['tuning', 'Tuning', true], ['control', 'Control', true], ['scenes', 'Scenes', true], ['setup', 'Setup', true],
];
const LATER = {
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
  Wire.call('setup', { open: id === 'setup' ? 1 : 0 }).then(r => { if (r.setup) setSetup(r.setup); });
  Wire.call('scenes', { open: id === 'scenes' ? 1 : 0 }).then(r => { if (r.scenes) setScenes(r.scenes); });
  Wire.call('control', { open: id === 'control' ? 1 : 0, kinds: CT.kinds ? 0 : 1 }).then(r => { if (r.control) setControl(r.control); });
  Wire.call('tuning', { open: id === 'tuning' ? 1 : 0, lists: TN.lists ? 0 : 1 }).then(r => { if (r.tuning) setTuning(r.tuning); });
  Wire.call('matrix', { open: id === 'matrix' ? 1 : 0, tables: MX.t ? 0 : 1 }).then(r => { if (r.tables) MX.t = r.tables; if (r.matrix) setMatrix(r.matrix); });
  Wire.call('effects', { open: id === 'effects' ? 1 : 0, tables: FX.t ? 0 : 1 }).then(r => { if (r.tables) FX.t = r.tables; if (r.effects) setEffects(r.effects); });
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
// The selected part's Moog panel, laid out as the Messenger's own front
// panel (LFO 1 and the left-hand controller, the oscillators, the mixer, the
// filter, the envelopes), then our MF-104 delay. Built from the engine's knob
// table (nv_host_synth_knobs: each knob's section, its place there, the
// panel's name and a switch's words -- panel.h SYNTH_CARD).
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
// (the sections as the Messenger's panel has them: the left-hand controller
// under LFO 1; each control at its place, "row.col[.rows]"; a row's name
// where the panel prints one)
const SY_STACK = { 'Left hand': 'LFO 1' };
const SY_ROWS = { Envelopes: { 1: 'Filter envelope', 2: 'Amplifier envelope' }, Oscillators: { 1: '1', 2: '2' } };
function buildSynth() {
  const el = $('synth');
  el.innerHTML = ''; SY.ctl = {};
  const cols = new Map();
  const order = S.knobs.map((k, i) => i).filter(i => S.knobs[i].column).sort((a, b) => S.knobs[a].at - S.knobs[b].at);
  order.forEach(i => {
    const k = S.knobs[i];
    if (!cols.has(k.column)) {
      const c = document.createElement('section'); c.className = 'sy-col'; c.dataset.col = k.column;
      c.innerHTML = `<h3>${esc(k.column)}</h3><div class="sy-grid"></div>`;
      const host = SY_STACK[k.column] && cols.get(SY_STACK[k.column]);
      if (host) { host.el.classList.add('stacked'); host.el.appendChild(c); c.classList.add('sub'); } else el.appendChild(c);
      const grid = c.querySelector('.sy-grid');
      for (const [r, t] of Object.entries(SY_ROWS[k.column] || {})) {
        const l = document.createElement('div'); l.className = 'sy-row' + (t.length < 3 ? ' n' : ''); l.textContent = t;
        l.style.gridRow = r; l.style.gridColumn = k.column === 'Oscillators' ? '1' : '1';
        grid.appendChild(l);
      }
      cols.set(k.column, { el: c, grid });
    }
    const col = cols.get(k.column);
    const cell = document.createElement('div'); cell.className = 'sy-cell';
    const [r, c, rs] = String(k.group).split('.').map(Number);
    cell.style.gridRow = rs ? `${r} / span ${rs}` : String(r || 1);
    // (the oscillators' row numbers take a column of their own before the octave switches)
    cell.style.gridColumn = String((c || 1) + (k.column === 'Oscillators' ? 1 : 0));
    col.grid.appendChild(cell);
    synthCtl(cell, k, i);
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
      return `<button class="tab" data-kit="1" data-rank="${r}"><span class="tnm">${esc(a)}</span><span class="tf">${f}</span></button>`;
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
        `<span class="pdk">${noteName(k[0])} <small>${k[0]}</small></span><span class="pnm">${esc(k[1] || '—')}</span></button>`).join('') +
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

// ---------------------------------------------------------------- THE EFFECTS CARD
// The insertion effect (the Sound Canvas's EFX: one for the parts put on it):
// its type by family, its parameters as knobs in Roland's own printed values,
// its sends; and the system effects every part sends to (CC91, 93, 94) and
// the EQ. What a file sets comes back by the poll.
const FX = { t: null, e: null, sig: '', ctl: {}, fam: null, about: null, mine: {} };
const REVERBS = ['Room 1', 'Room 2', 'Room 3', 'Hall 1', 'Hall 2', 'Plate', 'Delay', 'Pan Delay'];
const CHORUSES = ['Chorus 1', 'Chorus 2', 'Chorus 3', 'Chorus 4', 'FB Chorus', 'Flanger', 'Short Delay', 'Short Delay FB'];
const DELAYS = ['Delay 1', 'Delay 2', 'Delay 3', 'Delay 4', 'Pan Delay 1', 'Pan Delay 2', 'Pan Delay 3', 'Pan Delay 4', 'Delay to Rev', 'Pan Repeat'];
const range = (lo, hi) => Array.from({ length: hi - lo + 1 }, (_, i) => lo + i);
// a knob over a list of values (each its own words): stepped by the list
function listKnob(parent, o) {
  const n = o.vals.length, idx = v => Math.max(0, o.vals.indexOf(v));
  const say = i => (o.shown ? o.shown[i] : String(o.vals[i]));
  let last = -1;
  const k = Kit.knob(parent, {
    label: o.label, value: n > 1 ? idx(o.value) / (n - 1) : 0, centred: o.centred, onReset: o.onReset,
    fmt: x => say(Math.round(x * (n - 1))),
    onChange: x => { const i = Math.round(x * (n - 1)); if (i !== last) { last = i; o.onSet(o.vals[i]); } },
    onInfo: () => Kit.sheet({ title: o.label, text: say(idx(o.value)), label: 'Value', value: o.vals[idx(o.value)], digits: 0,
      lo: o.vals[0], hi: o.vals[n - 1], hint: o.hint || '', onSet: v => { const j = o.vals.reduce((b, x, q) => Math.abs(x - v) < Math.abs(o.vals[b] - v) ? q : b, 0); o.onSet(o.vals[j]); } }),
  });
  k.el.addEventListener('pointerdown', () => { if (o.onTouch) o.onTouch(); });
  return { el: k.el, set: (v, own) => { const i = idx(v); k.set(n > 1 ? i / (n - 1) : 0, say(i), own); } };
}
// what this screen just set stands until the engine has it (a poll in between reads the old)
function fxMine(key, v) { FX.mine[key] = { v, until: performance.now() + HOLD_MS }; }
function fxVal(key, v) { const m = FX.mine[key]; if (m && m.until > performance.now()) return m.v; delete FX.mine[key]; return v; }
function efxSend(kind, a, b, key) { if (key) fxMine(key, b); Wire.call('efx_send', { kind, a, b }); }
function sysSend(hi, lo, v, key) { fxMine(key, v); Wire.call('sysfx_send', { hi, lo, v }); }
function setEffects(e) { FX.e = e; if (card === 'effects') drawEffects(); }
function partChannels() { const p = cur(); return !p ? [0] : p.channel < 0 ? range(0, 15) : [p.channel]; }
function drawEffects() {
  const e = FX.e, t = FX.t;
  if (!e || !t) return;
  const x = e.efx, p = cur();
  $('fxWho').textContent = p ? `part ${pad(S.row + 1, 2)} · ${p.name}` : '';
  const key = x.msb + '.' + x.lsb;
  const type = t.types.find(y => y[1] === x.msb && y[2] === x.lsb);
  const on = partChannels().every(c => x.parts.includes(c));
  $('fxOn').classList.toggle('on', on);
  $('fxName').textContent = type ? `${pad(type[0], 2)} ${type[3]}` : '00 Thru';
  const chans = x.parts.filter(c => c < 16).map(c => c + 1);
  $('fxParts').textContent = (chans.length ? `On it: channel${chans.length > 1 ? 's' : ''} ${chans.join(', ')}.` : 'No part is on it yet.') +
    (x.why ? ` Not played live: ${x.why}.` : '');
  // the families, then the family's types
  if (FX.fam === null) FX.fam = type ? t.families.findIndex(f => type[0] >= f[0] && type[0] <= f[1]) : 0;
  const fsig = FX.fam + '|' + key;
  if (fsig !== FX.fsig) {
    FX.fsig = fsig;
    $('fxFams').innerHTML = t.families.map((f, i) => `<button class="fam${i === FX.fam ? ' on' : ''}" data-kit="1" data-i="${i}">${esc(f[2])}</button>`).join('');
    const f = t.families[Math.max(0, FX.fam)];
    $('fxTypes').innerHTML = `<button class="fxt${!type ? ' cur' : ''}" data-kit="1" data-msb="0" data-lsb="0"><b>00</b> Thru</button>` +
      t.types.filter(y => f && y[0] >= f[0] && y[0] <= f[1]).map(y =>
        `<button class="fxt${type === y ? ' cur' : ''}" data-kit="1" data-msb="${y[1]}" data-lsb="${y[2]}"><b>${pad(y[0], 2)}</b> ${esc(y[3])}</button>`).join('');
  }
  // its parameters (built again for another type)
  const ps = t.params[key] || [];
  if (key !== FX.sig) {
    FX.sig = key; FX.ctl = {};
    const el = $('fxParams'); el.innerHTML = ps.length ? '' : '<p class="pn-note">Thru: the parts on it play dry. Choose a type.</p>';
    for (const [n, name, mark, fresh, vals, shown] of ps)
      FX.ctl['p' + n] = listKnob(el, { label: name + (mark && mark !== '-' ? ' ' + mark : ''), vals, shown, value: fresh,
        onSet: v => efxSend('p', n, v, 'p' + n), onTouch: () => drawFxAbout('efx') });
    const sd = $('fxSends'); sd.innerHTML = '';
    ['Reverb', 'Chorus', 'Delay'].forEach((nm, i) => {
      FX.ctl['s' + i] = listKnob(sd, { label: 'to ' + nm, vals: range(0, 127), value: 0, onSet: v => efxSend('s', 0x17 + i, v, 's' + i) });
    });
  }
  for (const [n, , , fresh] of ps) if (FX.ctl['p' + n]) FX.ctl['p' + n].set(fxVal('p' + n, x.p[n] >= 0 ? x.p[n] : fresh));
  for (let i = 0; i < 3; i++) if (FX.ctl['s' + i]) FX.ctl['s' + i].set(fxVal('s' + i, x.send[i]));
  drawSys();
  drawFxAbout();
}
Kit.press($('fxOn'), () => {
  const on = !$('fxOn').classList.contains('on');
  for (const c of partChannels()) Wire.call('efx_send', { kind: 'c', a: c, b: on ? 1 : 0 });
  $('fxOn').classList.toggle('on', on);
});
Kit.press($('fxFams'), b => { FX.fam = +b.dataset.i; FX.fsig = ''; drawEffects(); }, '.fam');
Kit.press($('fxTypes'), b => {
  Wire.call('efx_send', { kind: 't', a: +b.dataset.msb, b: +b.dataset.lsb });
  $('fxTypes').querySelectorAll('.fxt').forEach(q => q.classList.toggle('cur', q === b));
  FX.aboutOf = 'efx';
}, '.fxt');
// the system effects: each a box, its type and its knobs (GS 40 01 3x/5x, 40 02 0x)
function drawSys() {
  const y = FX.e.sys, el = $('fxSys');
  if (!y) { el.innerHTML = '<p class="pn-note">Reading the system effects…</p>'; FX.ssig = ''; return; }
  const boxes = [
    { id: 'rev', name: 'Reverb', cc: 'CC91', types: REVERBS, type: y.rev[0], lo: 0x30,
      knobs: [['Level', 0x33, y.rev[1], 0, 127], ['Time', 0x34, y.rev[2], 0, 127]].concat(y.rev[3] >= 0 ? [['Feedback', 0x35, y.rev[3], 0, 127]] : []) },
    { id: 'cho', name: 'Chorus', cc: 'CC93', types: CHORUSES, type: y.cho[0], lo: 0x38,
      knobs: [['Pre-LPF', 0x39, y.cho[1], 0, 7], ['Level', 0x3A, y.cho[2], 0, 127], ['Feedback', 0x3B, y.cho[3], 0, 127],
        ['Delay', 0x3C, y.cho[4], 0, 127], ['Rate', 0x3D, y.cho[5], 0, 127], ['Depth', 0x3E, y.cho[6], 0, 127]] },
    { id: 'dly', name: 'Delay', cc: 'CC94', types: DELAYS, type: y.dly[0], lo: 0x50,
      knobs: [['Pre-LPF', 0x51, y.dly[1], 0, 7], ['Time', 0x52, y.dly[2], 1, 0x73], ['Ratio L', 0x53, y.dly[3], 1, 0x78],
        ['Ratio R', 0x54, y.dly[4], 1, 0x78], ['Level C', 0x55, y.dly[5], 0, 127], ['Level L', 0x56, y.dly[6], 0, 127],
        ['Level R', 0x57, y.dly[7], 0, 127], ['Level', 0x58, y.dly[8], 0, 127], ['Feedback', 0x59, y.dly[9], 0, 127]] },
  ];
  const sig = boxes.map(b => b.id + b.knobs.length).join('|');
  if (sig !== FX.ssig) {
    FX.ssig = sig;
    el.innerHTML = boxes.map(b => `<div class="fx-box" data-box="${b.id}"><h3>${b.name} <small>${b.cc}</small></h3>` +
      `<div class="fx-st">${b.types.map((n, i) => `<button class="fxs" data-kit="1" data-lo="${b.lo}" data-v="${i}" data-box="${b.id}">${n}</button>`).join('')}</div>` +
      `<p class="pn-note fx-room"></p><div class="fx-knobs sm"></div></div>`).join('') +
      `<div class="fx-box" data-box="eq"><h3>EQ <small>the whole mix</small></h3><div class="fx-knobs sm"></div></div>`;
    for (const b of boxes) {
      const kb = el.querySelector(`[data-box="${b.id}"] .fx-knobs`);
      for (const [nm, lo, , a, z] of b.knobs)
        FX.ctl[b.id + lo] = listKnob(kb, { label: nm, vals: range(a, z), value: a, onSet: v => sysSend(1, lo, v, b.id + lo), onTouch: () => drawFxAbout(b.id) });
    }
    const eq = el.querySelector('[data-box="eq"] .fx-knobs');
    const gains = range(0x34, 0x4C), gsh = gains.map(g => (g - 0x40 > 0 ? '+' : '') + (g - 0x40) + ' dB');
    FX.ctl.eq0 = listKnob(eq, { label: 'Low', vals: [0, 1], shown: ['200 Hz', '400 Hz'], value: 0, onSet: v => sysSend(2, 0, v, 'eq0'), onTouch: () => drawFxAbout('eq') });
    FX.ctl.eq1 = listKnob(eq, { label: 'Low gain', vals: gains, shown: gsh, value: 0x40, centred: true, onSet: v => sysSend(2, 1, v, 'eq1'), onTouch: () => drawFxAbout('eq') });
    FX.ctl.eq2 = listKnob(eq, { label: 'High', vals: [0, 1], shown: ['3 kHz', '6 kHz'], value: 0, onSet: v => sysSend(2, 2, v, 'eq2'), onTouch: () => drawFxAbout('eq') });
    FX.ctl.eq3 = listKnob(eq, { label: 'High gain', vals: gains, shown: gsh, value: 0x40, centred: true, onSet: v => sysSend(2, 3, v, 'eq3'), onTouch: () => drawFxAbout('eq') });
  }
  for (const b of boxes) {
    const t = fxVal(b.id + 'type', b.type);
    el.querySelectorAll(`.fxs[data-box="${b.id}"]`).forEach(q => q.classList.toggle('on', +q.dataset.v === t));
    for (const [, lo, v] of b.knobs) FX.ctl[b.id + lo].set(fxVal(b.id + lo, v));
  }
  el.querySelector('[data-box="rev"] .fx-room').textContent = y.rev[0] < 0 ? `No GS reverb set: the room is the panel's, ${y.room}.` : '';
  for (let k = 0; k < 4; k++) FX.ctl['eq' + k].set(fxVal('eq' + k, y.eq[k]));
}
Kit.press($('fxSys'), b => {
  sysSend(1, +b.dataset.lo, +b.dataset.v, b.dataset.box + 'type');
  $('fxSys').querySelectorAll(`.fxs[data-box="${b.dataset.box}"]`).forEach(q => q.classList.toggle('on', q === b));
  drawFxAbout(b.dataset.box);
}, '.fxs');
const FX_NOTE = { rev: 'Reverb (system)', cho: 'Chorus (system)', dly: 'Delay (system)', eq: 'EQ (system)' };
function drawFxAbout(of) {
  if (of) FX.aboutOf = of;
  const a = S.about, el = $('fxAbout');
  if (!a || !a.efx || !FX.e || !FX.t) { el.innerHTML = ''; return; }
  const w = FX.aboutOf || 'efx';
  if (w === 'efx') {
    const x = FX.e.efx, type = FX.t.types.find(y => y[1] === x.msb && y[2] === x.lsb);
    el.innerHTML = type ? (a.efx[type[3]] ? aboutHtml(type[3], a.efx[type[3]]) : `<p class="ab-hint">${esc(type[3])}: no notes yet.</p>`)
      : '<p class="ab-hint">Touch a knob or a type for what it is.</p>';
  } else el.innerHTML = aboutHtml(FX_NOTE[w].replace(' (system)', ''), a.effects[FX_NOTE[w]]);
}

// ---------------------------------------------------------------- THE MATRIX CARD
// What each controller moves on the selected part's channel (GS's controller
// matrix, 40 2x): the six sources down the side, the eleven destinations
// across, a knob in each cell in the destination's own unit. Changed from
// power-on: lit. Double-tap a cell: back to power-on.
const MX = { t: null, m: null, sig: '', ctl: {} };
const MX_SRC = ['Mod wheel', 'Pitch bend', 'Channel aftertouch', 'Poly aftertouch', 'CC1', 'CC2'];
const MX_DEST = [['', 'Pitch'], ['', 'Cutoff'], ['', 'Amplitude'], ['LFO 1', 'Rate'], ['LFO 1', 'Pitch'], ['LFO 1', 'Filter'], ['LFO 1', 'Amp'],
  ['LFO 2', 'Rate'], ['LFO 2', 'Pitch'], ['LFO 2', 'Filter'], ['LFO 2', 'Amp']];
function setMatrix(m) { if (m.row !== S.row) return; MX.m = m; if (card === 'matrix') drawMatrix(); }
function drawMatrix() {
  const m = MX.m, t = MX.t, el = $('mx');
  if (!m || !t) return;
  $('mxWho').textContent = `part ${pad(m.row + 1, 2)} · ${m.part}`;
  $('mxInfo').textContent = m.channel < 0 ? 'every channel' : `channel ${m.channel + 1}`;
  if (!m.raw) { el.innerHTML = '<p class="empty">Reading the matrix…</p>'; MX.sig = ''; return; }
  if (MX.sig !== 'grid') {
    MX.sig = 'grid'; MX.ctl = {};
    el.innerHTML = `<div class="mx-h"></div>` + MX_DEST.map(([g, d], j) => `<div class="mx-h${j === 3 || j === 7 ? ' grp' : ''}"><small>${g}</small>${d}</div>`).join('') +
      MX_SRC.map((s, i) => `<div class="mx-src" data-src="${i}"><b>${s}</b>${i >= 4 ? `<span class="mx-cc"></span><button class="hb mx-learn" data-kit="1" data-which="${i}">LEARN</button>` : ''}</div>` +
        MX_DEST.map((_, j) => `<div class="mx-cell${j === 3 || j === 7 ? ' grp' : ''}" data-c="${i}.${j}"></div>`).join('')).join('');
    for (let i = 0; i < 6; i++) for (let j = 0; j < 11; j++) {
      const d = t[j];
      MX.ctl[i + '.' + j] = listKnob(el.querySelector(`[data-c="${i}.${j}"]`), {
        label: '', vals: range(d.lo, d.hi), shown: d.shown, value: d.zero, centred: Math.abs((d.zero - d.lo) / (d.hi - d.lo) - 0.5) < 0.05,
        onSet: v => { fxMine('mx' + i + '.' + j, v); Wire.call('cmx_set', { src: i, dest: j, raw: v }); },
        onReset: () => { const v = MX.m.def[i][j]; fxMine('mx' + i + '.' + j, v); MX.ctl[i + '.' + j].set(v, false); Wire.call('cmx_set', { src: i, dest: j, raw: v }); },
      });
    }
  }
  for (let i = 0; i < 6; i++) {
    let used = false;
    for (let j = 0; j < 11; j++) {
      const v = fxVal('mx' + i + '.' + j, m.raw[i][j]), own = v !== m.def[i][j];
      MX.ctl[i + '.' + j].set(v, own);
      used = used || v !== t[j].zero;
    }
    el.querySelector(`.mx-src[data-src="${i}"]`).classList.toggle('used', used);
  }
  el.querySelectorAll('.mx-cc').forEach((c, k) => { c.textContent = 'is CC' + (k ? m.cc2 : m.cc1); });
  el.querySelectorAll('.mx-learn').forEach(b => {
    const on = m.learning === +b.dataset.which;
    b.textContent = on ? 'MOVE A CONTROL…' : 'LEARN'; b.classList.toggle('blink', on);
  });
  $('mxGm2').textContent = m.gm2.length ? 'Set by a file\'s GM2 messages (shown, not changed here): ' +
    m.gm2.map(([cc, d, txt]) => `CC${cc} → ${MX_DEST[d].join(' ').trim()} ${txt}`).join(' · ') : '';
  const a = S.about, k = a && a.effects && Object.keys(a.effects).find(x => x.startsWith('Controller matrix'));
  $('mxAbout').innerHTML = k ? aboutHtml('Controller matrix', a.effects[k]) : '';
}
Kit.press($('mx'), async b => {
  const which = +b.dataset.which, on = MX.m && MX.m.learning === which;
  await Wire.call('cmx_learn', { which: on ? 0 : which });
  const r = await Wire.call('matrix'); if (r.matrix) setMatrix(r.matrix);
}, '.mx-learn');
Kit.press($('mx'), c => {           // (CC1/CC2's number, typed)
  const which = c.closest('.mx-src').dataset.src === '4' ? 4 : 5, m = MX.m;
  Kit.sheet({ title: (which === 4 ? 'CC1' : 'CC2') + ': which controller', text: 'CC' + (which === 4 ? m.cc1 : m.cc2), label: 'Controller number',
    value: which === 4 ? m.cc1 : m.cc2, digits: 0, lo: 0, hi: 95, hint: 'Or LEARN: move the knob or pedal you want.',
    onSet: async v => { await Wire.call('cmx_assign', { which, cc: Math.round(v) }); const r = await Wire.call('matrix'); if (r.matrix) setMatrix(r.matrix); } });
}, '.mx-cc');

// ---------------------------------------------------------------- THE TUNING CARD
// The rig's tuner (every part: the patches built again in it), grouped by
// what it is for; its shape drawn -- an octave's notes in cents from equal
// temperament, and how far each key strays across the keyboard (stretch);
// the Eastern tuning the Indian voices play (a raga system, a raga, Sa).
const TN = { t: null, lists: null, east: null };
const TN_GROUPS = [
  ['Concert pitch, A=440', ['gm2', 'hybrid440', 'hybridmeanpiano', 'stretchedhelmholtz', 'even']],
  ['Baroque pitch, A=415', ['hybrid', 'stretch', 'werckmeister', 'sankey', 'meantone']],
  ['Pure octaves: pipes', ['hybridharm', 'hybridharm440', 'hybridmean']],
];
const SA_KEYS = ['c', 'c#', 'd', 'd#', 'e', 'f', 'f#', 'g', 'g#', 'a', 'a#', 'b'];
function eastParts(e) {        // "raga:<system>[/<raga>]@<sa>" taken apart
  if (!e || !e.startsWith('raga:')) return { system: '', raga: '', sa: 'c#' };
  let b = e.slice(5), sa = 'c#';
  const at = b.indexOf('@'); if (at >= 0) { sa = b.slice(at + 1).split(':')[0] || 'c#'; b = b.slice(0, at); }
  const [system, raga] = b.split('/');
  return { system: system || '', raga: raga || '', sa };
}
const eastSpec = p => (p.system ? `raga:${p.system}${p.raga ? '/' + p.raga : ''}@${p.sa}` : '');
function setTuning(t) {
  if (t.tuners) TN.lists = { tuners: t.tuners, systems: t.systems, ragas: t.ragas };
  TN.t = t;
  if (TN.east && TN.east.until < performance.now()) TN.east = null;
  if (card === 'tuning') drawTuning();
}
function drawTuning() {
  const t = TN.t, L = TN.lists;
  if (!t || !L) return;
  const building = t.tuner !== t.now;
  $('tnInfo').textContent = building ? `building the patches in ${t.tuner}…` : `playing ${t.now}`;
  const sig = t.tuner + '|' + t.now;
  if (sig !== TN.sig) {
    TN.sig = sig;
    const named = new Set(TN_GROUPS.flatMap(g => g[1]));
    const groups = TN_GROUPS.map(([g, ns]) => [g, ns.map(n => L.tuners.find(x => x[0] === n)).filter(Boolean)]);
    groups.push(['Indian, every part', L.tuners.filter(x => x[0].startsWith('raga:'))]);
    groups.push(['Other systems', L.tuners.filter(x => !named.has(x[0]) && !x[0].startsWith('raga:'))]);
    $('tnList').innerHTML = groups.filter(g => g[1].length).map(([g, ts]) => `<section><h3>${g}</h3><div class="tn-grid">` +
      ts.map(([n, d]) => `<button class="tnt${n === t.tuner ? (building ? ' pending' : ' cur') : ''}" data-kit="1" data-name="${esc(n)}">` +
        `<b>${esc(n)}</b><span>${esc(d)}</span></button>`).join('') + '</div></section>').join('');
  }
  $('tnName').textContent = t.tuner + (t.shape.a4 ? ` · A4 = ${t.shape.a4} Hz` : '');
  drawShape(t.shape);
  drawEast();
}
Kit.press($('tnList'), async b => {
  $('tnList').querySelectorAll('.tnt').forEach(q => q.classList.toggle('pending', q === b));
  const r = await Wire.call('tuner_set', { name: b.dataset.name });
  if (r.tuning) setTuning(r.tuning);
}, '.tnt');
function drawShape(sh) {
  const el = $('tnShape');
  if (!sh || !sh.cents) { el.innerHTML = '<text x="300" y="150" class="tn-l" text-anchor="middle">this tuner has no fixed table (it follows the file or the music)</text>'; return; }
  const c = sh.cents;
  // an octave (C4-B4): bars from equal temperament, ±30 cents
  const W = 600, top = 26, h1 = 110, mid1 = top + h1 / 2, sc1 = (h1 / 2) / 30, bw = W / 12;
  let g = `<text x="0" y="14" class="tn-h">C4 to B4, cents from equal temperament</text>` +
    `<line x1="0" x2="${W}" y1="${mid1}" y2="${mid1}" class="tn-ax"/>`;
  for (let i = 0; i < 12; i++) {
    const v = c[60 + i], x = i * bw;
    const nm = NOTE_NAMES[i];
    if (v !== null) {
      const hh = Math.max(-h1 / 2, Math.min(h1 / 2, v * sc1));
      g += `<rect x="${(x + bw * 0.2).toFixed(1)}" width="${(bw * 0.6).toFixed(1)}" y="${(hh > 0 ? mid1 - hh : mid1).toFixed(1)}" height="${Math.max(1, Math.abs(hh)).toFixed(1)}" class="tn-bar"/>` +
        `<text x="${(x + bw / 2).toFixed(1)}" y="${(hh > 0 ? mid1 - hh - 4 : mid1 - hh + 12).toFixed(1)}" class="tn-v">${v > 0 ? '+' : ''}${v.toFixed(Math.abs(v) < 10 ? 1 : 0)}</text>`;
    }
    g += `<text x="${(x + bw / 2).toFixed(1)}" y="${top + h1 + 14}" class="tn-l">${nm}</text>`;
  }
  // the keyboard A0-C8: each key's cents (the stretch), ±40 cents
  const top2 = 182, h2 = 100, mid2 = top2 + h2 / 2, sc2 = (h2 / 2) / 40;
  g += `<text x="0" y="${top2 - 8}" class="tn-h">A0 to C8: each octave's stretch from 2:1, in cents</text><line x1="0" x2="${W}" y1="${mid2}" y2="${mid2}" class="tn-ax"/>`;
  let d = '';
  for (let n = 21; n <= 108; n++) {
    const b = c[60 + n % 12];                     // (the octave's own temperament taken out: the stretch alone)
    const v = c[n] === null || b === null ? null : c[n] - b; if (v === null) continue;
    const x = (n - 21) / 87 * W, y = mid2 - Math.max(-h2 / 2, Math.min(h2 / 2, v * sc2));
    d += (d ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
    if (n % 12 === 0) g += `<text x="${x.toFixed(1)}" y="${top2 + h2 + 14}" class="tn-l">C${n / 12 - 1}</text>`;
  }
  g += `<path d="${d}" class="tn-line"/>` +
    `<text x="${W}" y="${top2 + 10}" class="tn-l" text-anchor="end">+40</text><text x="${W}" y="${top2 + h2}" class="tn-l" text-anchor="end">−40</text>`;
  el.innerHTML = g;
}
function drawEast() {
  const L = TN.lists, p = TN.east ? TN.east.p : eastParts(TN.t.eastern);
  const esig = eastSpec(p) + '|' + !!TN.measured;
  if (esig === TN.esig) return;
  TN.esig = esig;
  const measured = p.system.startsWith('saraga_') || TN.measured;
  $('tnSys').innerHTML = `<button class="tns${!p.system && !TN.measured ? ' on' : ''}" data-kit="1" data-sys="">Off</button>` +
    L.systems.filter(x => !x.startsWith('saraga_')).map(x => `<button class="tns${x === p.system ? ' on' : ''}" data-kit="1" data-sys="${esc(x)}">${esc(x)}</button>`).join('') +
    `<button class="tns${measured ? ' on' : ''}" data-kit="1" data-measured="1">measured ragas…</button>`;
  $('tnRagas').innerHTML = measured
    ? L.systems.filter(x => x.startsWith('saraga_')).map(x => `<button class="tns${x === p.system ? ' on' : ''}" data-kit="1" data-sys="${esc(x)}">${esc(x.slice(7).replace(/_/g, ' '))}</button>`).join('')
    : p.system ? `<button class="tns${!p.raga ? ' on' : ''}" data-kit="1" data-raga="">No raga</button>` +
      L.ragas.map(x => `<button class="tns${x === p.raga ? ' on' : ''}" data-kit="1" data-raga="${esc(x)}">${esc(x)}</button>`).join('') : '';
  $('tnSa').innerHTML = p.system ? '<b>Sa</b>' + SA_KEYS.map(k => `<button class="tns${k === p.sa ? ' on' : ''}" data-kit="1" data-sa="${k}">${k.toUpperCase()}</button>`).join('') : '';
  $('tnEast').textContent = p.system ? `The Indian instruments' parts play ${p.system.startsWith('saraga_') ? 'raga ' + p.system.slice(7).replace(/_/g, ' ') + ' as measured (Saraga)' : p.system}${p.raga ? ', raga ' + p.raga : ''}, Sa on ${p.sa.toUpperCase()} (unless the tuner above is itself Indian).`
    : 'Off: the Indian instruments play the tuner above.';
  const on = $('tnRagas').querySelector('.on'); if (on) on.scrollIntoView({ block: 'nearest' });
}
Kit.press($('tnList').parentNode.querySelector('.tn-east'), async b => {
  const p = Object.assign({}, TN.east ? TN.east.p : eastParts(TN.t.eastern));
  if (b.dataset.measured) { TN.measured = true; TN.esig = ''; drawEast(); return; }
  if (b.dataset.sys !== undefined) {
    p.system = b.dataset.sys; TN.measured = false;
    if (!p.system || p.system.startsWith('saraga_')) p.raga = '';
  }
  if (b.dataset.raga !== undefined) p.raga = b.dataset.raga;
  if (b.dataset.sa !== undefined) p.sa = b.dataset.sa;
  TN.east = { p, until: performance.now() + 1500 };
  drawEast();
  const r = await Wire.call('eastern_set', { spec: eastSpec(p) });
  if (r.tuning) setTuning(r.tuning);
}, '.tns');

// ---------------------------------------------------------------- THE CONTROL CARD
// The on-screen controls (a pedal or wheel the keyboard lacks): each sent
// straight to the engine on its channel, a switch latching (press down, press
// up), the pitch wheel and aftertouch springing back when let go. And the
// routes: the keyboard's own controls rewritten -- a key as the sustain, a
// CC onto another, the wheel's half onto a switch -- with learn for the source.
const CT = { c: null, kinds: null, ctl: {}, sig: null, adding: false, nw: { src: -1, arg: -1, dst: null, keep: 0, ch: -1, latch: 0, press: 1 } };
const SCAN = [['off', 0], ['V1', 18], ['V2', 37], ['V3', 55], ['C1', 73], ['C2', 91], ['C3', 110]];
const ctKind = key => (CT.kinds || []).find(k => k[0] === key) || [key, 'CC' + key, 'continuous', 0];
function setControl(c) {
  if (c.kinds) CT.kinds = c.kinds;
  CT.c = c;
  if (card === 'control') drawControl();
}
let ctT = {};
function ctSend(i, v) {                  // (a drag's values at most 30 a second; the last always goes)
  const t = ctT[i] || (ctT[i] = { tm: 0, want: null });
  t.want = v;
  if (t.tm) return;
  const go = () => { t.tm = 0; if (t.want === null) return; const x = t.want; t.want = null; Wire.call('control_set', { i, v: x }); t.tm = setTimeout(go, 33); };
  go();
}
function drawControl() {
  const c = CT.c;
  if (!c || !CT.kinds) return;
  const p = cur();
  $('ctWho').textContent = p ? `part ${pad(S.row + 1, 2)} · ${p.name}` : '';
  $('ctInfo').textContent = `${c.controls.length} control${c.controls.length === 1 ? '' : 's'} · ${c.routes.length} route${c.routes.length === 1 ? '' : 's'}`;
  const sig = c.controls.map(x => x.key + ':' + x.channel).join(',');
  if (sig !== CT.sig) {
    CT.sig = sig; CT.ctl = {};
    const el = $('ctStrip'); el.innerHTML = '';
    for (const x of c.controls) {
      const [, label, kind] = ctKind(x.key);
      const box = document.createElement('div'); box.className = 'ct-c';
      box.innerHTML = `<div class="ct-body"></div><span class="ct-ch">${x.channel < 0 ? 'every channel' : 'channel ' + (x.channel + 1)}</span>` +
        `<button class="hb ct-rm" data-kit="1" data-i="${x.i}">REMOVE</button>`;
      el.appendChild(box);
      const body = box.querySelector('.ct-body');
      if (kind === 'switch') {
        const b = document.createElement('button'); b.className = 'pd-btn ct-sw'; b.dataset.kit = '1';
        body.append(b); const l = document.createElement('b'); l.textContent = label.toUpperCase(); body.append(l);
        Kit.press(b, () => { const on = !b.classList.contains('on'); b.classList.toggle('on', on); CT.mine = { i: x.i, on, until: performance.now() + HOLD_MS }; Wire.call('control_set', { i: x.i, v: on ? 127 : 0 }); });
        CT.ctl[x.i] = { set: (v, on) => b.classList.toggle('on', on) };
      } else if (kind === 'selector') {
        const sg = Kit.segments(body, { label: label.toUpperCase(), options: SCAN.map(q => q[0]), value: 0, onChange: j => Wire.call('control_set', { i: x.i, v: SCAN[j][1] }) });
        sg.el.classList.add('v');
        CT.ctl[x.i] = { set: v => { let j = 0; SCAN.forEach((q, k) => { if (v >= q[1]) j = k; }); sg.set(j); } };
      } else {
        const bend = kind === 'bend', spring = bend || kind === 'pressure';
        const lo = bend ? -8192 : 0, hi = bend ? 8191 : 127;
        const f = Kit.fader(body, { label: label.toUpperCase(), value: x.value, lo, hi, step: 1, travel: 300, detents: bend ? [0] : [],
          fmt: v => (bend ? (v > 0 ? '+' : '') + Math.round(v) : String(Math.round(v))),
          onChange: v => ctSend(x.i, Math.round(v)),
          onEnd: spring ? () => { f.set(0, false); ctSend(x.i, 0); } : undefined });
        CT.ctl[x.i] = { set: v => f.set(v, false) };
      }
    }
    const add = document.createElement('button'); add.className = 'ct-plus'; add.dataset.kit = '1'; add.textContent = '+ ADD A CONTROL';
    el.appendChild(add);
    Kit.press(add, () => { CT.adding = !CT.adding; drawAdd(); });
  }
  for (const x of c.controls) {
    const k = CT.ctl[x.i]; if (!k) continue;
    const m = CT.mine; let on = x.on;
    if (m && m.i === x.i && m.until > performance.now()) on = m.on;
    k.set(x.value, on);
  }
  drawAdd(); drawRoutes();
}
Kit.press($('ctStrip'), async b => { await Wire.call('control_remove', { i: +b.dataset.i }); CT.sig = null; const r = await Wire.call('control'); if (r.control) setControl(r.control); }, '.ct-rm');
function drawAdd() {
  const el = $('ctAdd');
  el.hidden = !CT.adding;
  if (!CT.adding) return;
  const p = cur(), ch = p && p.channel >= 0 ? p.channel : -1;
  const have = new Set(CT.c.controls.map(x => x.key + ':' + x.channel));
  el.innerHTML = `<p class="pn-note">Add a control on ${ch < 0 ? 'every channel' : 'channel ' + (ch + 1) + ' (part ' + pad(S.row + 1, 2) + "'s)"}:</p><div class="ct-kinds">` +
    CT.kinds.map(([key, label, kind]) => `<button class="tns${have.has(key + ':' + ch) ? ' on' : ''}" data-kit="1" data-key="${key}" data-ch="${ch}">${esc(label)}<small>${kind}</small></button>`).join('') + '</div>';
}
Kit.press($('ctAdd'), async b => {
  await Wire.call('control_add', { key: +b.dataset.key, channel: +b.dataset.ch });
  CT.adding = false; CT.sig = null;
  const r = await Wire.call('control'); if (r.control) setControl(r.control);
}, '.tns');
// THE ROUTES, and a new one: its source (learnt or chosen), destination, how
const KEYN = n => NOTE_NAMES[n % 12] + (Math.floor(n / 12) - 1);
function drawRoutes() {
  const c = CT.c, nw = CT.nw;
  $('ctRoutes').innerHTML = c.routes.length ? c.routes.map(r => `<div class="rt"><span>${esc(r.text)}</span>` +
    `<button class="hb rt-rm" data-kit="1" data-i="${r.i}">REMOVE</button></div>`).join('') : '<p class="pn-note">No routes: the keyboard\'s controls reach the engine as they are.</p>';
  if (c.learnt && c.learnt[0] && CT.waiting) {
    CT.waiting = 0;
    nw.src = c.learnt[0] === 1 ? 3 : 0; nw.arg = c.learnt[1];
  }
  const learning = c.learning || 0;
  const srcName = nw.src === 3 ? (nw.arg >= 0 ? 'key ' + KEYN(nw.arg) : 'a key') : nw.src === 0 ? (nw.arg >= 0 ? 'CC' + nw.arg : 'a controller')
    : nw.src === 1 ? ['the pitch wheel up', 'the pitch wheel down', 'the pitch wheel, either way'][Math.max(0, nw.arg)] : nw.src === 2 ? 'aftertouch' : '—';
  const dst = nw.dst === null ? null : ctKind(nw.dst);
  const sw = dst && dst[2] === 'switch';
  const p = cur(), pch = p && p.channel >= 0 ? p.channel : -1;
  const ready = nw.src >= 0 && (nw.src === 1 || nw.src === 2 || nw.arg >= 0) && nw.dst !== null;
  $('ctNew').innerHTML = `<h4>A new route</h4>` +
    `<div class="tn-row"><b>FROM</b>` +
    `<button class="tns${learning === 1 ? ' on blink' : nw.src === 3 ? ' on' : ''}" data-kit="1" data-learn="1">${learning === 1 ? 'PRESS A KEY…' : 'A KEY (LEARN)'}</button>` +
    `<button class="tns${learning === 2 ? ' on blink' : nw.src === 0 ? ' on' : ''}" data-kit="1" data-learn="2">${learning === 2 ? 'MOVE A CONTROL…' : 'A CONTROLLER (LEARN)'}</button>` +
    ['UP', 'DOWN', 'EITHER'].map((t, j) => `<button class="tns${nw.src === 1 && nw.arg === j ? ' on' : ''}" data-kit="1" data-wheel="${j}">WHEEL ${t}</button>`).join('') +
    `<button class="tns${nw.src === 2 ? ' on' : ''}" data-kit="1" data-press="1">AFTERTOUCH</button></div>` +
    `<div class="tn-row"><b>TO</b></div><div class="ct-kinds sm">` + CT.kinds.filter(k => k[0] >= 0 || k[0] === -3).map(([key, label]) =>
      `<button class="tns${nw.dst === key ? ' on' : ''}" data-kit="1" data-dst="${key}">${esc(label)}</button>`).join('') + '</div>' +
    `<div class="tn-row"><b>HOW</b>` +
    `<button class="tns${nw.keep ? ' on' : ''}" data-kit="1" data-opt="keep">KEEP THE ORIGINAL TOO</button>` +
    (sw ? `<button class="tns${nw.latch ? ' on' : ''}" data-kit="1" data-opt="latch">LATCH (PRESS ON, PRESS OFF)</button>` : '') +
    (nw.src === 3 && nw.dst === 64 ? `<button class="tns${nw.press ? ' on' : ''}" data-kit="1" data-opt="press">PUSH INTO IT TO DAMP</button>` : '') +
    `<button class="tns${nw.ch < 0 ? ' on' : ''}" data-kit="1" data-chan="-1">EVERY CHANNEL</button>` +
    (pch >= 0 ? `<button class="tns${nw.ch === pch ? ' on' : ''}" data-kit="1" data-chan="${pch}">CHANNEL ${pch + 1}</button>` : '') + '</div>' +
    `<div class="tn-row"><span class="rt-say">${esc(srcName)} → ${dst ? esc(dst[1]) : '…'}</span>` +
    `<button class="hb rt-add" data-kit="1"${ready ? '' : ' disabled'}>ADD THE ROUTE</button></div>`;
}
Kit.press($('ctRoutes'), async b => { await Wire.call('route_remove', { i: +b.dataset.i }); const r = await Wire.call('control'); if (r.control) setControl(r.control); }, '.rt-rm');
Kit.press($('ctNew'), async b => {
  const nw = CT.nw, d = b.dataset;
  if (d.learn) { const k = +d.learn; const on = (CT.c.learning || 0) !== k; CT.waiting = on ? k : 0; await Wire.call('route_learn', { kind: on ? k : 0 }); CT.c.learning = on ? k : 0; CT.c.learnt = [0, -1]; }
  else if (d.wheel !== undefined) { nw.src = 1; nw.arg = +d.wheel; }
  else if (d.press) { nw.src = 2; nw.arg = 0; }
  else if (d.dst !== undefined) nw.dst = +d.dst;
  else if (d.opt) nw[d.opt] = nw[d.opt] ? 0 : 1;
  else if (d.chan !== undefined) nw.ch = +d.chan;
  else if (b.classList.contains('rt-add')) {
    const sw = ctKind(nw.dst)[2] === 'switch';
    const r7 = [nw.src, nw.src === 2 ? 0 : nw.arg, nw.dst, nw.keep, nw.ch, sw ? nw.latch : 0, nw.src === 3 && nw.dst === 64 ? nw.press : 0];
    await Wire.call('route_add', { r: r7 });
    CT.nw = { src: -1, arg: -1, dst: null, keep: 0, ch: -1, latch: 0, press: 1 };
    const r = await Wire.call('control'); if (r.control) setControl(r.control);
    return;
  }
  drawRoutes();
}, '.tns, .rt-add');

// ---------------------------------------------------------------- A NAME, typed on the screen's own keys
function nameSheet(title, value, onSet) {
  const back = document.createElement('div'); back.className = 'kit-sheet-back';
  const sh = document.createElement('div'); sh.className = 'kit-sheet name-sheet';
  const rows = ['1234567890', 'qwertyuiop', 'asdfghjkl-', 'zxcvbnm_'];
  sh.innerHTML = `<h3>${esc(title)}</h3><div class="name-val"></div><div class="osk">` +
    rows.map(r => `<div>${[...r].map(c => `<button data-k="${c}">${c}</button>`).join('')}</div>`).join('') +
    '<div><button data-k="clear" class="w">CLEAR</button><button data-k=" " class="space">SPACE</button><button data-k="back" class="w">⌫</button></div></div>' +
    '<div class="row"><button class="close">Cancel</button><button class="set">Save</button></div>';
  back.appendChild(sh); document.body.appendChild(back);
  let v = value || '';
  const show = () => { sh.querySelector('.name-val').textContent = v || ' '; sh.querySelector('.set').disabled = !v.trim(); };
  show();
  sh.querySelector('.osk').addEventListener('pointerdown', e => {
    const b = e.target.closest('button'); if (!b) return; e.preventDefault();
    const k = b.dataset.k;
    v = k === 'clear' ? '' : k === 'back' ? v.slice(0, -1) : (v + k).slice(0, 40);
    show();
  });
  const close = () => back.remove();
  Kit.press(sh.querySelector('.close'), close);
  Kit.press(sh.querySelector('.set'), () => { if (v.trim()) { close(); onSet(v.trim()); } });
}

// ---------------------------------------------------------------- THE SCENES CARD
// The presets (the whole setup) and the scenes (each channel's controls),
// kept beside the session and shared with live.py and the apps: a tap
// chooses one, LOAD or RECALL brings it, DELETE takes it out. The
// metronome, and the GS reset.
const SC = { s: null, sel: { preset: null, scene: null }, msg: '', resetArm: 0 };
function setScenes(x) { SC.s = x; if (card === 'scenes') drawScenes(); }
function partsSay(ps) {
  return ps.map(([pg, v, dr]) => {
    const p = S.patches.find(q => !!q.drums === dr && q.program === pg && (dr || q.variation === v));
    return p ? p.name : (dr ? 'kit ' + pg : 'program ' + pg);
  }).join(' + ');
}
function drawScenes() {
  const x = SC.s; if (!x) return;
  $('scInfo').textContent = SC.msg || (x.kept ? '' : 'No session file: presets and scenes cannot be kept.');
  const sp = SC.sel.preset, ss = SC.sel.scene;
  $('scPresets').innerHTML = x.presets.length ? x.presets.map(p => `<div class="sc-item${p.name === sp ? ' on' : ''}" data-kind="preset" data-name="${esc(p.name)}" data-kit="1">` +
    `<b>${esc(p.name)}</b><span>${esc(partsSay(p.parts))}${p.tuner ? ' · ' + esc(p.tuner) : ''}</span>` +
    (p.name === sp ? `<div class="sc-do"><button class="hb" data-do="preset_load" data-kit="1">LOAD</button><button class="hb" data-do="preset_save" data-kit="1">SAVE OVER</button><button class="hb" data-do="preset_delete" data-kit="1">DELETE</button></div>` : '') +
    '</div>').join('') : '<p class="pn-note">No presets yet.</p>';
  $('scScenes').innerHTML = x.scenes.length ? x.scenes.map(c => `<div class="sc-item${c.name === ss ? ' on' : ''}" data-kind="scene" data-name="${esc(c.name)}" data-kit="1">` +
    `<b>${esc(c.name)}</b><span>${c.n} setting${c.n === 1 ? '' : 's'}</span>` +
    (c.name === ss ? `<div class="sc-do"><button class="hb" data-do="scene_recall" data-kit="1">RECALL</button><button class="hb" data-do="scene_save" data-kit="1">SAVE OVER</button><button class="hb" data-do="scene_delete" data-kit="1">DELETE</button></div>` : '') +
    '</div>').join('') : '<p class="pn-note">No scenes yet.</p>';
  drawMetro();
}
async function scDo(call, name) {
  const r = await Wire.call(call, { name });
  SC.msg = r.msg || ''; if (call.endsWith('_delete')) SC.sel = { preset: null, scene: null };
  if (r.scenes) setScenes(r.scenes); else drawScenes();
  clearTimeout(SC.msgT); SC.msgT = setTimeout(() => { SC.msg = ''; drawScenes(); }, 4000);
}
for (const id of ['scPresets', 'scScenes']) {
  Kit.press($(id), (t, e) => {
    const b = e.target.closest('[data-do]');
    if (b) { scDo(b.dataset.do, t.dataset.name); return; }
    SC.sel[t.dataset.kind] = SC.sel[t.dataset.kind] === t.dataset.name ? null : t.dataset.name;
    drawScenes();
  }, '.sc-item');
}
Kit.press($('presetSave'), () => nameSheet('Save this setup as', '', n => scDo('preset_save', n)));
Kit.press($('sceneSave'), () => nameSheet('Save the controls as', '', n => scDo('scene_save', n)));
Kit.press($('gsReset'), () => {
  const b = $('gsReset');
  if (SC.resetArm > performance.now()) { SC.resetArm = 0; b.textContent = 'GS RESET'; b.classList.remove('blink'); Wire.call('gs_reset'); SC.msg = 'GS reset sent'; drawScenes(); return; }
  SC.resetArm = performance.now() + 3000; b.textContent = 'TAP AGAIN TO RESET'; b.classList.add('blink');
  setTimeout(() => { if (SC.resetArm && SC.resetArm <= performance.now()) { SC.resetArm = 0; b.textContent = 'GS RESET'; b.classList.remove('blink'); } }, 3100);
});
// THE METRONOME: the globals 10 (bpm, 0 off), 11 (its bell every n beats), 12 (its level)
const MT = { built: false };
function drawMetro() {
  const m = SC.s.metro, el = $('scMetro');
  if (!MT.built) {
    MT.built = true; el.innerHTML = '';
    MT.on = Kit.toggle(el, { label: 'ON', value: m[0] > 0, onChange: on => {
      let last = 100; try { last = +localStorage.getItem('clavitone.bpm') || 100; } catch (_) {}
      Wire.call('global_set', { i: 10, v: on ? last : 0 });
    } });
    MT.bpm = listKnob(el, { label: 'Tempo', vals: range(30, 300), value: m[0] > 0 ? m[0] : 100, onSet: v => {
      try { localStorage.setItem('clavitone.bpm', v); } catch (_) {}
      if (SC.s.metro[0] > 0) Wire.call('global_set', { i: 10, v });
    } });
    MT.ring = listKnob(el, { label: 'Bell every', vals: range(0, 16), shown: range(0, 16).map(n => (n ? n + ' beats' : 'none')), value: m[1], onSet: v => Wire.call('global_set', { i: 11, v }) });
    MT.db = listKnob(el, { label: 'Level', vals: range(-40, 12), shown: range(-40, 12).map(n => (n > 0 ? '+' : '') + n + ' dB'), value: Math.round(m[2]), onSet: v => Wire.call('global_set', { i: 12, v }) });
  }
  MT.on.set(m[0] > 0);
  if (m[0] > 0) MT.bpm.set(Math.round(m[0]));
  MT.ring.set(Math.round(m[1])); MT.db.set(Math.round(m[2]));
}

// ---------------------------------------------------------------- THE SETUP CARD
// The MIDI inputs (each plugged-in device on or off), the Messenger, the
// globals every part plays through (nv_host_set_global: livetui's GLOBALS),
// the room, how program changes are read, and rubato's borrowed time.
const SU = { s: null, built: false, ctl: {} };
const GLOB = [   // [index, label, lo, hi, step, format]
  [0, 'Master', -60, 0, 0.5, v => v.toFixed(1) + ' dB'], [1, 'Headroom', 0, 24, 0.5, v => v.toFixed(1) + ' dB'],
  [2, 'Limiter knee', 0.1, 1, 0.02, v => v.toFixed(2)], [3, 'Bend range', 0, 24, 0.5, v => v.toFixed(1) + ' st'],
  [4, 'Mod depth', 0, 200, 5, v => v.toFixed(0) + ' c'], [9, 'Mod rate', 0, 1.5, 0.05, v => '+' + (v * 100).toFixed(0) + '%'],
  [5, 'Aftertouch', 0, 24, 0.5, v => v.toFixed(1) + ' dB'],
];
const STDS = ['ours', 'SC-55', 'SC-88', 'SC-88Pro', 'SC-8850'];
function setSetup(x) { SU.s = x; if (card === 'setup') drawSetup(); }
function drawSetup() {
  const x = SU.s; if (!x) return;
  const g = x.globals;
  $('suInfo').textContent = `${x.rate} Hz · ${x.block} frames a block (${(1000 * x.block / x.rate).toFixed(2)} ms)`;
  $('suIns').innerHTML = (x.inputs.length ? x.inputs.map(d => `<button class="su-in${d.on ? ' on' : ''}" data-kit="1" data-path="${esc(d.path)}">` +
    `<b>${esc(d.name)}</b><span>${esc(d.path.replace('/dev/snd/', ''))} · ${d.on ? (d.open ? 'reading' : 'wanted, not open') : 'off'}</span></button>`).join('')
    : '<p class="pn-note">No MIDI devices plugged in.</p>') + (x.input_err ? `<p class="pn-note">${esc(x.input_err)}</p>` : '');
  $('suMsgr').textContent = x.messenger.line ? (x.messenger.line === '-' ? 'Looked for when the program is a Messenger patch.' : 'On ' + x.messenger.line + '.') : 'None set.';
  $('suMsgrOpts').innerHTML = `<button class="tns${x.messenger.reads ? ' on' : ''}" data-kit="1" data-m="reads">READ ITS KNOBS</button>` +
    `<button class="tns${x.messenger.pre107 ? ' on' : ''}" data-kit="1" data-m="pre107">FIRMWARE BEFORE 1.0.7</button>`;
  if (!SU.built) {
    SU.built = true;
    const el = $('suKnobs'); el.innerHTML = '';
    for (const [i, label, lo, hi, step, f] of GLOB) {
      const n = Math.round((hi - lo) / step), vals = range(0, n);
      SU.ctl[i] = listKnob(el, { label, vals, shown: vals.map(k => f(lo + k * step)), value: 0,
        onSet: k => { fxMine('g' + i, k); Wire.call('global_set', { i, v: +(lo + k * step).toFixed(4) }); } });
      SU.ctl[i].map = v => Math.round((v - lo) / step);
    }
  }
  for (const [i] of GLOB) SU.ctl[i].set(fxVal('g' + i, SU.ctl[i].map(g[i])));
  $('suSw').innerHTML = `<button class="tns${g[6] > 0.5 ? ' on' : ''}" data-kit="1" data-g="6">THE GPU</button>` +
    `<button class="tns${g[7] > 0.5 ? ' on' : ''}" data-kit="1" data-g="7">THE ROOM'S TAIL</button>`;
  $('suRooms').innerHTML = (S.rooms || []).map((r, i) => `<button class="tns${r === x.room ? ' on' : ''}" data-kit="1" data-room="${i}">${esc(r)}</button>`).join('');
  $('suStd').innerHTML = STDS.map((n, i) => `<button class="tns${Math.round(g[13]) === i ? ' on' : ''}" data-kit="1" data-std="${i}">${n}</button>`).join('');
  const r = x.rubato, ms = f => (1000 * f / x.rate).toFixed(1) + ' ms';
  $('suRub').innerHTML = x.rubato_on ? [
    ['Callbacks that waited', r[0]], ['Time held, ever', ms(r[1])], ['Owed now', ms(r[2])],
    ['Time returned', ms(r[6]) + ` (${r[5]} cuts)`], ['Held by the partials ringing on', ms(r[7])]]
    .map(([k, v]) => `<div class="su-r"><span>${k}</span><b>${v}</b></div>`).join('') +
    '<p class="pn-note">When a block is late, the sound already playing is held on and the time is borrowed; it is given back where no note falls.</p>'
    : '<p class="pn-note">Rubato is off: start nvlive with --rubato to let a late block borrow time instead of dropping out.</p>';
}
Kit.press($('suIns'), b => { Wire.call('input_set', { path: b.dataset.path, on: b.classList.contains('on') ? 0 : 1 }); b.classList.toggle('on'); }, '.su-in');
Kit.press($('suMsgrOpts'), b => { const k = b.dataset.m; Wire.call('messenger_set', { [k]: b.classList.contains('on') ? 0 : 1 }); b.classList.toggle('on'); }, '.tns');
Kit.press($('suSw'), b => { Wire.call('global_set', { i: +b.dataset.g, v: b.classList.contains('on') ? 0 : 1 }); b.classList.toggle('on'); }, '.tns');
Kit.press($('suRooms'), b => { Wire.call('global_set', { i: 8, v: +b.dataset.room }); $('suRooms').querySelectorAll('.tns').forEach(q => q.classList.toggle('on', q === b)); }, '.tns');
Kit.press($('suStd'), b => { Wire.call('global_set', { i: 13, v: +b.dataset.std }); $('suStd').querySelectorAll('.tns').forEach(q => q.classList.toggle('on', q === b)); }, '.tns');

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
    S.rooms = h.rooms || [];
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
    if (m.effects) setEffects(m.effects);
    if (m.matrix) setMatrix(m.matrix);
    if (m.tuning) setTuning(m.tuning);
    if (m.control) setControl(m.control);
    if (m.scenes) setScenes(m.scenes);
    if (m.setup) setSetup(m.setup);
    if (m.synth && m.synth.row === S.row && (m.synth.layer === S.layer || m.synth.layers <= S.layer)) { S.layer = m.synth.layer; S.synth = m.synth; if (card === 'synth') drawSynth(); }
  },
  down() { $('gone').hidden = false; },
});
