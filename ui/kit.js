// THE CONTROLS (the plan's "parts kit"): knob, wave knob, fader, switch,
// toggle, display field and dial -- one gesture model for all of them, made
// for fingers.
//
//   drag        up or right turns it up; a full turn is TRAVEL px of finger
//   fine        a second finger resting anywhere off the controls: ten times finer
//   detent      a named position (a centre, triangle/saw/square, 0 dB) holds
//               the value for DETENT px of finger before it lets go
//   double-tap  back to the patch's (onReset)
//   long-press  the control's sheet: its value to type, the patch's (onInfo)
//
// Each control is a plain object over an element; set() moves it without
// calling back, so values pushed by the engine never fight a finger.
'use strict';

const Kit = (() => {
  const TRAVEL = 220, FINE = 10, DETENT = 14, LONG_MS = 550, TAP_MS = 300, SLOP = 6;
  const NS = 'http://www.w3.org/2000/svg';

  // ---- the fingers resting off the controls (fine mode)
  const resting = new Set();
  document.addEventListener('pointerdown', e => {
    if (!e.target.closest('[data-kit]')) resting.add(e.pointerId);
  }, true);
  const lift = e => resting.delete(e.pointerId);
  document.addEventListener('pointerup', lift, true);
  document.addEventListener('pointercancel', lift, true);
  const fine = () => resting.size > 0;

  // ---- the value bubble over the finger
  const bubble = document.createElement('div');
  bubble.className = 'kit-bubble'; bubble.hidden = true;
  document.addEventListener('DOMContentLoaded', () => document.body.appendChild(bubble));
  function showBubble(x, y, text, isFine) {
    bubble.textContent = text + (isFine ? '  · fine' : '');
    bubble.hidden = false;
    const w = bubble.offsetWidth;
    bubble.style.left = Math.max(4, Math.min(innerWidth - w - 4, x - w / 2)) + 'px';
    bubble.style.top = Math.max(4, y - 90) + 'px';
  }
  const hideBubble = () => { bubble.hidden = true; };

  // ---- the gesture: a relative drag with detents, double-tap, long-press
  // g: { get(), set(v, fromFinger), lo, hi, detents[], step (0 continuous),
  //      onReset, onInfo, text(), axis ('both' | 'v' | 'h'), travel }
  function gesture(el, g) {
    el.dataset.kit = '1';
    el.style.touchAction = 'none';
    let id = null, x0 = 0, y0 = 0, raw = 0, moved = false, lastTap = 0, timer = 0, wasFine = false;
    const span = () => g.hi - g.lo;

    // raw finger travel -> value, flat for DETENT px at each detent
    function valueOf(r) {
      const per = span() / (g.travel || TRAVEL);   // value per px
      let v = g.base + r * per;
      for (const d of g.detents || []) {
        const at = (d - g.base) / per;               // px where the detent is reached
        const hold = DETENT;
        if (r > at && at >= 0) { v = r - at < hold ? d : v - hold * per; }
        else if (r < at && at <= 0) { v = at - r < hold ? d : v + hold * per; }
      }
      v = Math.max(g.lo, Math.min(g.hi, v));
      if (g.step) v = g.lo + Math.round((v - g.lo) / g.step) * g.step;
      return v;
    }

    el.addEventListener('pointerdown', e => {
      if (id !== null) return;
      id = e.pointerId; el.setPointerCapture(id);
      x0 = e.clientX; y0 = e.clientY; raw = 0; moved = false; wasFine = fine();
      g.base = g.get();
      el.classList.add('kit-active');
      clearTimeout(timer);
      timer = setTimeout(() => { if (!moved && id !== null && g.onInfo) { end(); g.onInfo(); } }, LONG_MS);
      e.preventDefault();
    });
    el.addEventListener('pointermove', e => {
      if (e.pointerId !== id) return;
      const dx = e.clientX - x0, dy = y0 - e.clientY;
      if (!moved && Math.hypot(dx, dy) < SLOP) return;
      if (!moved) { moved = true; clearTimeout(timer); }
      const f = fine();
      if (f !== wasFine) {                          // (fine on or off mid-drag: from here, no jump)
        g.base = g.get(); x0 = e.clientX; y0 = e.clientY; raw = 0; wasFine = f;
        return;
      }
      const d = g.axis === 'v' ? dy : g.axis === 'h' ? dx : dy + dx;
      raw = d / (f ? FINE : 1);
      const v = valueOf(raw);
      if (v !== g.get()) g.set(v, true);
      showBubble(e.clientX, e.clientY, g.text(), f);
    });
    function end() {
      if (id === null) return;
      try { el.releasePointerCapture(id); } catch (_) {}
      id = null; clearTimeout(timer); hideBubble(); el.classList.remove('kit-active');
      if (g.onEnd) g.onEnd();
    }
    el.addEventListener('pointerup', e => {
      if (e.pointerId !== id) return;
      const tapped = !moved;
      end();
      if (tapped) {
        const now = performance.now();
        if (now - lastTap < TAP_MS) { lastTap = 0; if (g.onReset) g.onReset(); else if (g.onTap) g.onTap(); }
        else { lastTap = now; if (g.onTap) g.onTap(); }
      }
    });
    el.addEventListener('pointercancel', e => { if (e.pointerId === id) end(); });
    return { busy: () => id !== null };
  }

  function svg(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }

  // ---- THE KNOB: 270 degrees, a ring that fills (from the top when centred)
  const A0 = -135, A1 = 135;
  function arcPath(r, c, d0, d1) {
    const p = d => { const t = (d - 90) * Math.PI / 180; return [c + r * Math.cos(t), c + r * Math.sin(t)]; };
    const [x0, y0] = p(d0), [x1, y1] = p(d1);
    return `M${x0.toFixed(2)} ${y0.toFixed(2)} A${r} ${r} 0 ${Math.abs(d1 - d0) > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  }

  // opts: { label, value, centred, detents, fmt(v), onChange(v), onReset, onInfo, size, scope ('osc'|'sub'), own }
  function knob(parent, o) {
    const el = document.createElement('div');
    el.className = 'kit-knob' + (o.size === 'big' ? ' big' : '') + (o.scope ? ' wave' : '');
    let scopePath = null;
    if (o.scope) {
      const sc = svg('svg', { class: 'kit-scope', viewBox: '0 0 96 36', 'aria-hidden': 'true' }, el);
      svg('rect', { x: 0, y: 0, width: 96, height: 36, rx: 4, class: 'kit-scope-bg' }, sc);
      svg('line', { x1: 2, x2: 94, y1: 18, y2: 18, class: 'kit-scope-axis' }, sc);
      scopePath = svg('path', { class: 'kit-scope-trace', d: '' }, sc);
    }
    const s = svg('svg', { viewBox: '0 0 64 64', class: 'kit-dial', 'aria-hidden': 'true' }, el);
    svg('path', { d: arcPath(27, 32, A0, A1), class: 'kit-track' }, s);
    const fill = svg('path', { class: 'kit-fill', d: '' }, s);
    for (const d of o.detents || []) {          // (the named positions, ticked)
      const a = (A0 + (A1 - A0) * d - 90) * Math.PI / 180;
      svg('line', { x1: 32 + 30 * Math.cos(a), y1: 32 + 30 * Math.sin(a), x2: 32 + 32.5 * Math.cos(a), y2: 32 + 32.5 * Math.sin(a), class: 'kit-tick' }, s);
    }
    svg('circle', { cx: 32, cy: 32, r: 20, class: 'kit-cap-rim' }, s);
    svg('circle', { cx: 32, cy: 32, r: 16, class: 'kit-cap' }, s);
    const ptr = svg('line', { x1: 32, y1: 32, x2: 32, y2: 16, class: 'kit-ptr' }, s);
    const lab = document.createElement('div'); lab.className = 'kit-label'; lab.textContent = o.label || '';
    const val = document.createElement('div'); val.className = 'kit-value';
    el.append(lab, val);
    parent.appendChild(el);

    let v = o.value ?? 0, text = '', own = !!o.own;
    function draw() {
      const a = A0 + (A1 - A0) * v, from = o.centred ? 0 : A0;
      fill.setAttribute('d', Math.abs(a - from) > 0.5 ? arcPath(27, 32, Math.min(a, from), Math.max(a, from)) : '');
      const t = (a - 90) * Math.PI / 180;
      ptr.setAttribute('x2', (32 + 15 * Math.cos(t)).toFixed(2)); ptr.setAttribute('y2', (32 + 15 * Math.sin(t)).toFixed(2));
      val.textContent = text;
      el.classList.toggle('own', own);
      if (scopePath) scopePath.setAttribute('d', Wave.path(o.scope, v, 96, 36));
    }
    const fmt = x => (o.fmt ? o.fmt(x) : x.toFixed(2));
    text = fmt(v);
    const ctl = {
      el,
      get: () => v,
      set(nv, nt, nown) { if (g.busy()) return; v = nv; text = nt ?? fmt(nv); if (nown !== undefined) own = nown; draw(); },
    };
    const g = gesture(el, {
      lo: 0, hi: 1, detents: o.detents, get: () => v,
      set(nv) { v = nv; text = fmt(nv); own = true; draw(); if (o.onChange) o.onChange(nv); },
      text: () => text, onReset: o.onReset, onInfo: o.onInfo, onEnd: o.onEnd,
    });
    draw();
    return ctl;
  }

  // ---- THE FADER: vertical, its detents (0 dB, the patch's) ticked
  // opts: { label, value, lo, hi, detents, fmt, onChange, onReset, onInfo }
  function fader(parent, o) {
    const el = document.createElement('div'); el.className = 'kit-fader';
    const slot = document.createElement('div'); slot.className = 'kit-slot';
    const cap = document.createElement('div'); cap.className = 'kit-fcap';
    for (const d of o.detents || []) {
      const t = document.createElement('i'); t.className = 'kit-ftick';
      t.style.bottom = (100 * (d - o.lo) / (o.hi - o.lo)) + '%'; slot.appendChild(t);
    }
    slot.appendChild(cap);
    const lab = document.createElement('div'); lab.className = 'kit-label'; lab.textContent = o.label || '';
    const val = document.createElement('div'); val.className = 'kit-value';
    el.append(slot, val, lab); parent.appendChild(el);
    let v = o.value ?? o.lo, own = false;
    const fmt = x => (o.fmt ? o.fmt(x) : x.toFixed(1));
    function draw() { cap.style.bottom = `calc(${100 * (v - o.lo) / (o.hi - o.lo)}% - 14px)`; val.textContent = fmt(v); el.classList.toggle('own', own); }
    const g = gesture(el, {
      lo: o.lo, hi: o.hi, detents: o.detents, axis: 'v', travel: o.travel || 260, step: o.step || 0, get: () => v,
      set(nv) { v = nv; own = true; draw(); if (o.onChange) o.onChange(nv); },
      text: () => fmt(v), onReset: o.onReset, onInfo: o.onInfo, onEnd: o.onEnd,
    });
    draw();
    return { el, get: () => v, set(nv, nown) { if (g.busy()) return; v = nv; if (nown !== undefined) own = nown; draw(); } };
  }

  // ---- THE SWITCH: segments for a few short words, one tap each
  function segments(parent, o) {
    const el = document.createElement('div'); el.className = 'kit-switch';
    const row = document.createElement('div'); row.className = 'kit-seg';
    const btns = o.options.map((t, i) => {
      const b = document.createElement('button'); b.textContent = t; b.dataset.kit = '1';
      b.style.touchAction = 'manipulation';
      b.onclick = () => { set(i); if (o.onChange) o.onChange(i); };
      row.appendChild(b); return b;
    });
    const lab = document.createElement('div'); lab.className = 'kit-label'; lab.textContent = o.label || '';
    el.append(row, lab); parent.appendChild(el);
    function set(i) { btns.forEach((b, k) => b.classList.toggle('on', k === i)); }
    set(o.value ?? 0);
    return { el, set };
  }

  // ---- THE TOGGLE
  function toggle(parent, o) {
    const el = document.createElement('div'); el.className = 'kit-switch';
    const b = document.createElement('button'); b.className = 'kit-toggle'; b.dataset.kit = '1';
    b.style.touchAction = 'manipulation';
    const lab = document.createElement('div'); lab.className = 'kit-label'; lab.textContent = o.label || '';
    el.append(b, lab); parent.appendChild(el);
    let on = !!o.value;
    const draw = () => b.classList.toggle('on', on);
    b.onclick = () => { on = !on; draw(); if (o.onChange) o.onChange(on); };
    draw();
    return { el, set(x) { on = !!x; draw(); } };
  }

  // ---- A DISPLAY FIELD: tap to select it; drag it, or turn the dial, to change it
  function field(parent, o) {
    const el = document.createElement('div'); el.className = 'kit-field';
    el.innerHTML = `<b>${o.label}</b><span></span>`;
    parent.appendChild(el);
    let v = o.value ?? 0;
    const sp = el.querySelector('span');
    const fmt = x => (o.fmt ? o.fmt(x) : String(x));
    const draw = () => { sp.textContent = fmt(v); };
    const g = gesture(el, {
      lo: o.lo, hi: o.hi, step: 1, axis: 'both', travel: o.travel || 4 * (o.hi - o.lo + 1), get: () => v,
      set(nv) { v = nv; draw(); if (o.onChange) o.onChange(nv); },
      text: () => `${o.label} ${fmt(v)}`, onTap: () => o.onSelect && o.onSelect(ctl), onReset: o.onReset,
    });
    const ctl = {
      el, get: () => v,
      set(nv) { if (g.busy()) return; v = Math.max(o.lo, Math.min(o.hi, nv)); draw(); },
      nudge(d) { const nv = Math.max(o.lo, Math.min(o.hi, v + d)); if (nv !== v) { v = nv; draw(); if (o.onChange) o.onChange(nv); } },
      select(on) { el.classList.toggle('on', on); },
    };
    draw();
    return ctl;
  }

  // ---- THE DIAL: turned round its centre, a step each 15 degrees (onStep(+1 | -1))
  function dial(parent, o) {
    const el = document.createElement('div'); el.className = 'kit-jog'; el.dataset.kit = '1';
    el.style.touchAction = 'none';
    const dot = document.createElement('i'); el.appendChild(dot); parent.appendChild(el);
    let id = null, last = 0, acc = 0, rot = 0;
    const ang = e => { const r = el.getBoundingClientRect(); return Math.atan2(e.clientY - (r.top + r.height / 2), e.clientX - (r.left + r.width / 2)) * 180 / Math.PI; };
    el.addEventListener('pointerdown', e => { if (id !== null) return; id = e.pointerId; el.setPointerCapture(id); last = ang(e); acc = 0; e.preventDefault(); });
    el.addEventListener('pointermove', e => {
      if (e.pointerId !== id) return;
      let a = ang(e), d = a - last; last = a;
      if (d > 180) d -= 360; if (d < -180) d += 360;
      rot += d; el.style.setProperty('--rot', rot + 'deg');
      acc += d;
      const per = fine() ? 45 : 15;
      while (acc >= per) { acc -= per; o.onStep(1); }
      while (acc <= -per) { acc += per; o.onStep(-1); }
    });
    const up = e => { if (e.pointerId === id) { id = null; } };
    el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up);
    return { el };
  }

  // ---- THE SHEET (long-press): a control's value to type, and the patch's
  // opts: { title, text, value (0..1 or lo..hi), lo, hi, onSet(v), onReset }
  function sheet(o) {
    const back = document.createElement('div'); back.className = 'kit-sheet-back';
    const sh = document.createElement('div'); sh.className = 'kit-sheet';
    const lo = o.lo ?? 0, hi = o.hi ?? 1;
    sh.innerHTML = `<h3>${o.title}</h3><p class="now">${o.text}</p>` +
      `<label>Position <input type="number" inputmode="decimal" step="any" min="${lo}" max="${hi}" value="${(+o.value).toFixed(3)}"></label>` +
      `<p class="hint">${o.hint || ''}</p>` +
      `<div class="row">${o.onReset ? '<button class="reset">Back to the patch</button>' : ''}<button class="set">Set</button><button class="close">Close</button></div>`;
    back.appendChild(sh); document.body.appendChild(back);
    const inp = sh.querySelector('input');
    const close = () => back.remove();
    sh.querySelector('.close').onclick = close;
    back.addEventListener('pointerdown', e => { if (e.target === back) close(); });
    sh.querySelector('.set').onclick = () => { const v = parseFloat(inp.value); if (isFinite(v)) o.onSet(Math.max(lo, Math.min(hi, v))); close(); };
    if (o.onReset) sh.querySelector('.reset').onclick = () => { o.onReset(); close(); };
  }

  return { knob, fader, segments, toggle, field, dial, sheet, fine };
})();

// THE WAVES, as the engine makes them (moog.py _osc_parts, _sub_cached): each
// a crossfade of straight-line waves, one period of +-1
const Wave = (() => {
  const TRI = 0.335, SAW = 0.5, SQUARE = 0.68, FOLD_MAX = 5, PULSE_MIN = 0.025, SUB_SQUARE = 0.3, SUB_PULSE_MIN = 0.0033;
  const reflect = x => { x = ((x + 1) % 4 + 4) % 4; return x <= 2 ? x - 1 : 3 - x; };
  const tri = x => (x < 0.5 ? -1 + 4 * x : 3 - 4 * x);
  const saw = x => -1 + 2 * x;
  const pulse = (d, c) => x => (x >= c - d / 2 && x < c + d / 2 ? 1 : -1);
  function osc(s) {
    if (s < TRI) { const g = 1 + (FOLD_MAX - 1) * (TRI - s) / TRI; return x => reflect(g * tri(x)); }
    if (s < SAW) { const a = (s - TRI) / (SAW - TRI); return x => (1 - a) * tri(x) + a * saw(x); }
    if (s < SQUARE) { const a = (s - SAW) / (SQUARE - SAW), sq = pulse(0.5, 0.75); return x => (1 - a) * saw(x) + a * sq(x); }
    const d = 0.5 - (0.5 - PULSE_MIN) * (s - SQUARE) / (1 - SQUARE);
    return pulse(d, 0.75);
  }
  function sub(s) {
    if (s < SUB_SQUARE) { const a = s / SUB_SQUARE, sq = pulse(0.5, 0.5); return x => (1 - a) * tri(x) + a * sq(x); }
    return pulse(0.5 - (0.5 - SUB_PULSE_MIN) * (s - SUB_SQUARE) / (1 - SUB_SQUARE), 0.5);
  }
  // two periods across the scope, sampled finely enough for a 2% pulse
  function path(kind, s, W, H) {
    const f = kind === 'sub' ? sub(s) : osc(s), N = 600;
    let d = '';
    for (let i = 0; i <= N; i++) {
      const x = (2 * i / N) % 1, y = f(i === N ? 0.9999 : x);
      d += (i ? 'L' : 'M') + (3 + i / N * (W - 6)).toFixed(1) + ' ' + (H / 2 - y * (H / 2 - 4)).toFixed(1);
    }
    return d;
  }
  return { osc, sub, path, TRI, SAW, SQUARE, SUB_SQUARE };
})();
