// THE WIRE: one WebSocket to nvlive (uiserve.h); a call answered by its id
// (uiapi.cpp), what changed pushed on its own. Reconnects when the engine
// comes back.
'use strict';

const Wire = (() => {
  let ws = null, nextId = 1;
  const waiting = new Map();
  let onOpen = () => {}, onPush = () => {}, onDown = () => {};

  function call(name, args = {}) {
    return new Promise(res => {
      if (!ws || ws.readyState !== 1) { res({ ok: false, error: 'not connected' }); return; }
      const id = nextId++;
      waiting.set(id, res);
      ws.send(JSON.stringify({ call: name, id, ...args }));
    });
  }

  function open() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => onOpen();
    ws.onmessage = ev => {
      const m = JSON.parse(ev.data);
      if (m.id !== undefined && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); return; }
      onPush(m);
    };
    ws.onclose = () => {
      waiting.forEach(res => res({ ok: false, error: 'closed' })); waiting.clear();
      onDown(); setTimeout(open, 1000);
    };
  }

  // a value sent while a finger moves: at most once a frame, the latest
  function throttled(send) {
    let pend = null, raf = 0;
    return v => {
      pend = v;
      if (raf) return;
      raf = requestAnimationFrame(() => { raf = 0; const p = pend; pend = null; send(p); });
    };
  }

  return {
    call, throttled,
    connect(opts) { onOpen = opts.open || onOpen; onPush = opts.push || onPush; onDown = opts.down || onDown; open(); },
  };
})();
