// THE TOUCH INTERFACE: the front panel (the display, its seven fields, the
// dial, the part keys), the card keys, and the cards -- Parts and Library
// and Stops now; the synth's knobs plain until their card comes.
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
  ['stops', 'Stops', true], ['piano', 'Piano'], ['drums', 'Drums'], ['effects', 'Effects'],
  ['matrix', 'Matrix'], ['tuning', 'Tuning'], ['control', 'Control'], ['scenes', 'Scenes'], ['setup', 'Setup'],
];
const LATER = {
  piano: 'the damper, push to damp and the register',
  drums: 'a pad for each key of the kit', effects: 'the insertion effect and the reverb, chorus, delay and EQ',
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
      `<button class="tile" data-kit="1" data-pick="${p.pick}"><span class="pn">${p.drums ? 'KIT ' + p.program : pad(p.program, 3) + (p.variation ? '<i>.' + p.variation + '</i>' : '')}</span>` +
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
}

// ---------------------------------------------------------------- THE SYNTH (plain until its card)
let dragging = null;
function drawSynth() {
  const el = $('synth'), sy = S.synth;
  if (dragging) return;
  el.innerHTML = '';
  $('synthWho').textContent = sy && sy.layers > 0 ? `part ${sy.row + 1}${sy.layers > 1 ? ' · layer ' + 'AB'[sy.layer] : ''}` : '';
  if (!sy || sy.layers <= 0) {
    el.innerHTML = `<p class="empty">${sy && sy.layers < 0 ? 'Reading the part…' : 'This part is not a synth: its knobs appear here when it is.'}</p>`;
    return;
  }
  let sec = null, box;
  S.knobs.forEach((k, i) => {
    if (k.section !== sec) {
      sec = k.section; box = document.createElement('div'); box.className = 'sec';
      box.innerHTML = `<h3>${esc(sec)}</h3>`; el.appendChild(box);
    }
    const v = sy.pn[k.knob], own = sy.own[k.knob];
    const r = document.createElement('div'); r.className = 'row' + (own ? ' own' : '');
    r.innerHTML = `<span>${esc(k.label)}</span>`;
    if (k.steps.length) {
      const seg = document.createElement('div'); seg.className = 'seg';
      k.steps.forEach(st => {
        const b = document.createElement('button');
        b.textContent = st; b.className = Math.abs(st - v) < 1e-6 ? 'on' : '';
        Kit.press(b, () => setKnob(k, st));
        seg.appendChild(b);
      });
      r.appendChild(seg);
    } else {
      const inp = document.createElement('input');
      inp.type = 'range'; inp.min = 0; inp.max = 1; inp.step = 0.001; inp.value = v;
      inp.oninput = () => setKnob(k, +inp.value);
      inp.onpointerdown = () => { dragging = inp; };
      inp.onpointerup = inp.onpointercancel = () => { dragging = null; refreshSynth(); };
      r.appendChild(inp);
    }
    const t = document.createElement('span'); t.className = 'v'; t.textContent = sy.text[i]; r.appendChild(t);
    r.ondblclick = () => forget(k);
    box.appendChild(r);
  });
}
const sendKnob = Wire.throttled(async ({ k, v }) => {
  await Wire.call('synth_set', { row: S.row, layer: S.layer, knob: k.knob, v });
  if (!dragging) refreshSynth();
});
const setKnob = (k, v) => sendKnob({ k, v });
async function forget(k) { await Wire.call('synth_forget', { row: S.row, layer: S.layer, knob: k.knob }); refreshSynth(); }
async function refreshSynth() { const s = await Wire.call('synth', { row: S.row, layer: S.layer }); S.synth = s.synth; if (card === 'synth') drawSynth(); }

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
    if (m.synth && m.synth.row === S.row) { S.synth = m.synth; if (card === 'synth') drawSynth(); }
  },
  down() { $('gone').hidden = false; },
});
