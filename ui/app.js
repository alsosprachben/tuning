// THE TOUCH INTERFACE, step 1: the wire. One WebSocket to nvlive (uiserve.h);
// each call {call, id, ...} answered by uiapi.cpp; what changed arrives on
// its own (meters, parts, the selected part's knobs).
'use strict';

const $ = id => document.getElementById(id);
let ws, nextId = 1;
const waiting = new Map();
const S = { parts: [], row: 0, layer: 0, knobs: [], synth: null };

function call(name, args = {}) {
  return new Promise(res => {
    const id = nextId++;
    waiting.set(id, res);
    ws.send(JSON.stringify({ call: name, id, ...args }));
  });
}

function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = async () => {
    $('gone').hidden = true;
    const h = await call('hello');
    S.knobs = h.knobs || [];
    const p = await call('parts');
    S.parts = p.parts || [];
    const s = await call('select', { row: S.row, layer: S.layer });
    S.synth = s.synth;
    drawParts(); drawSynth(); drawDisplay();
  };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id !== undefined && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); return; }
    if (m.meters) drawMeters(m.meters);
    if (m.parts) { S.parts = m.parts; drawParts(); drawDisplay(); }
    if (m.synth && m.synth.row === S.row) { S.synth = m.synth; drawSynth(); }
  };
  ws.onclose = () => { $('gone').hidden = false; setTimeout(connect, 1000); };
}

// ---- the display
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

function drawDisplay() {
  const p = S.parts[S.row];
  $('partno').textContent = p ? String(S.row + 1).padStart(2, '0') : '--';
  $('patch').textContent = p ? p.name : '';
  $('family').textContent = p ? (p.drums ? 'DRUM SET ' + p.program : 'PROGRAM ' + String(p.program).padStart(3, '0')) +
    (p.variation ? '.' + p.variation : '') + (p.channel < 0 ? ' · ALL CH' : ' · CH ' + (p.channel + 1)) : '';
}

function drawMeters(m) {
  m.bars.forEach((db, ch) => {
    const k = Math.round((db + 40) / 40 * 10);
    bars[ch].forEach((s, i) => s.classList.toggle('lit', i < k));
  });
  ['pkL', 'pkR'].forEach((id, c) => {
    const db = m.peak[c], w = Math.max(0, Math.min(100, (db + 48) / 48 * 100));
    $(id).style.width = w + '%'; $(id).classList.toggle('hot', db > -1);
  });
  const cpu = m.budget_ms > 0 ? Math.round(100 * m.ms_mean / m.budget_ms) : 0;
  $('cpu').textContent = `CPU ${cpu}%${m.gpu ? ' GPU' : ''}`;
  $('voices').textContent = `VOICES ${Math.round(m.voices)}`;
  $('health').textContent = m.underruns ? `UNDERRUNS ${m.underruns}` : m.rt_dropped ? 'RT DROPPED' : '';
}

// ---- the parts
function drawParts() {
  const el = $('parts'); el.innerHTML = '';
  S.parts.forEach(p => {
    const d = document.createElement('div');
    d.className = 'part' + (p.row === S.row ? ' sel' : '') + (p.muted || p.solo === 2 ? ' dim' : '');
    const ch = p.channel < 0 ? 'all ch' : 'ch ' + (p.channel + 1);
    d.innerHTML = `<span class="n">${String(p.row + 1).padStart(2, '0')}</span><div><div>${esc(p.name)}</div>` +
      `<div class="d">${ch} · ${note(p.lo)}–${note(p.hi)}${p.transpose ? ` · ${p.transpose > 0 ? '+' : ''}${p.transpose}` : ''}` +
      `${p.level_db ? ` · ${p.level_db > 0 ? '+' : ''}${p.level_db} dB` : ''}</div></div>` +
      `<span>${p.muted ? 'M' : ''}${p.solo === 1 ? 'S' : ''}</span>`;
    d.onclick = () => select(p.row);
    el.appendChild(d);
  });
}

async function select(row) {
  if (row < 0 || row >= S.parts.length) return;
  S.row = row; S.layer = 0;
  drawParts(); drawDisplay();
  const s = await call('select', { row, layer: 0 });
  S.synth = s.synth; drawSynth();
}

// ---- the synth knobs, plain for now (the card comes in step 4)
let dragging = null;
function drawSynth() {
  const el = $('synth'), sy = S.synth;
  if (dragging) return;                       // (not under a finger)
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
        b.onclick = () => setKnob(k, st);
        seg.appendChild(b);
      });
      r.appendChild(seg);
    } else {
      const inp = document.createElement('input');
      inp.type = 'range'; inp.min = 0; inp.max = 1; inp.step = 0.001; inp.value = v;
      inp.oninput = () => setKnob(k, +inp.value, true);
      inp.onpointerdown = () => { dragging = inp; };
      inp.onpointerup = inp.onpointercancel = () => { dragging = null; refreshSynth(); };
      r.appendChild(inp);
    }
    const t = document.createElement('span'); t.className = 'v'; t.textContent = sy.text[i]; r.appendChild(t);
    r.ondblclick = () => forget(k);
    box.appendChild(r);
  });
}

let pend = null;
function setKnob(k, v, live) {
  // (a drag sends at most once a frame)
  pend = { k, v };
  if (live && setKnob.raf) return;
  setKnob.raf = requestAnimationFrame(async () => {
    setKnob.raf = null;
    const p = pend; pend = null;
    await call('synth_set', { row: S.row, layer: S.layer, knob: p.k.knob, v: p.v });
    if (!dragging) refreshSynth();
  });
}
async function forget(k) { await call('synth_forget', { row: S.row, layer: S.layer, knob: k.knob }); refreshSynth(); }
async function refreshSynth() { const s = await call('synth', { row: S.row, layer: S.layer }); S.synth = s.synth; drawSynth(); }

$('prev').onclick = () => select(S.row - 1);
$('next').onclick = () => select(S.row + 1);
$('panic').onclick = () => call('panic');

const NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
function note(n) { return NOTES[n % 12] + (Math.floor(n / 12) - 1); }
function esc(s) { return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]); }

connect();
