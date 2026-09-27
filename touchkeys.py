#!/usr/bin/env python3
"""Touch keys: a touch-screen piano for live, speaking MPE.

    python3 touchkeys.py [--open] [--port 8765]
    python3 live.py --port touch --tui          # in another terminal
    python3 touchkeys.py --selftest

WHY A WEB PAGE. A terminal cannot be a keyboard: it sends key presses and
auto-repeats but no key RELEASES (gnome-terminal's VTE, inside tmux, has no
kitty keyboard protocol), so a note could only end by guessing from the repeat
timing. A browser page gets a down and an up for every finger (Pointer
Events), the pen's pressure, and the computer keyboard's keydown and keyup --
so the page is the instrument, and this server is the wire: it serves the
page, takes its events over a WebSocket, and plays them into a virtual ALSA
MIDI port, "tuning touch", which live opens like any keyboard.

WHY MPE. Every finger has its own down and up, so every note can have its own
expression -- which is what MPE is (M1-100-UM v1.1), and live plays it. Each
note gets a MEMBER channel of its own; a sideways slide is that note's pitch
bend, a slide along the key its CC74, the pen's pressure its channel
pressure. The sender's rules followed here:

  * the Lower Zone, 15 members, declared by the MPE Configuration Message
    when the page connects and before the first note (live resets only on a
    CHANGE of zone, so repeating it is harmless);
  * a note goes to the member with the fewest active notes, the one released
    longest ago breaking ties, and preferably the channel that last played
    that note number (A.3);
  * its bend, CC74 and pressure are sent BEFORE its Note On (2.4), and
    nothing per-note is sent on its channel after its Note Off (2.2.6);
  * the sustain pedal is on the manager channel (2.3.1).

No libraries beyond what live already uses: the WebSocket is a minimal
RFC 6455 server on asyncio (handshake, masked text frames from the client,
ping and close).
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, 'touchkeys.html')
PORT_NAME = 'tuning touch'
WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

MANAGER = 0
MEMBERS = list(range(1, 16))          # the Lower Zone, all fifteen members
BEND_RANGE = 48.0                     # semitones: the member default an MCM sets (2.2.5)


# ------------------------------------------------------------------ MPE sender

class MpeSender(object):
    """Page events in, MIDI messages out (mido), following MPE's sender rules."""

    def __init__(self, send):
        self.send = send              # callable(mido.Message)
        self.notes = {}               # touch id -> (channel, note)
        self.active = {c: 0 for c in MEMBERS}
        self.released = {c: 0.0 for c in MEMBERS}
        self.last_ch = {}             # note number -> channel it last played on
        self.clock = 0

    def _cc(self, ch, c, v):
        import mido
        self.send(mido.Message('control_change', channel=ch, control=c,
                               value=max(0, min(127, int(v)))))

    def mcm(self):
        """The MPE Configuration Message: Lower Zone, 15 members (2.2.1)."""
        self._cc(MANAGER, 101, 0)
        self._cc(MANAGER, 100, 6)
        self._cc(MANAGER, 6, len(MEMBERS))

    def _tick(self):
        self.clock += 1
        return self.clock

    def allocate(self, note):
        """The member for a new note (A.3): fewest active notes, then the one
        released longest ago -- but the channel that last played this note
        number, if it is free, so repeated notes do not chorus."""
        prev = self.last_ch.get(note)
        if prev is not None and self.active[prev] == 0:
            return prev
        return min(MEMBERS, key=lambda c: (self.active[c], self.released[c], c))

    @staticmethod
    def bend_value(semitones):
        return max(-8192, min(8191, int(round(semitones * 8192.0 / BEND_RANGE))))

    def on(self, tid, note, vel, bend=0.0, timbre=64, pressure=0):
        import mido
        if tid in self.notes:
            self.off(tid)
        note = max(0, min(127, int(note)))
        ch = self.allocate(note)
        # 2.4: the three dimensions' initial values BEFORE the Note On
        self.send(mido.Message('pitchwheel', channel=ch, pitch=self.bend_value(bend)))
        self._cc(ch, 74, timbre)
        self.send(mido.Message('aftertouch', channel=ch, value=max(0, min(127, int(pressure)))))
        self.send(mido.Message('note_on', channel=ch, note=note,
                               velocity=max(1, min(127, int(vel)))))
        self.notes[tid] = (ch, note)
        self.active[ch] += 1
        self.last_ch[note] = ch
        return ch

    def move(self, tid, bend=None, timbre=None, pressure=None):
        import mido
        got = self.notes.get(tid)
        if got is None:
            return            # released: nothing per-note after Note Off (2.2.6)
        ch = got[0]
        if bend is not None:
            self.send(mido.Message('pitchwheel', channel=ch, pitch=self.bend_value(bend)))
        if timbre is not None:
            self._cc(ch, 74, timbre)
        if pressure is not None:
            self.send(mido.Message('aftertouch', channel=ch,
                                   value=max(0, min(127, int(pressure)))))

    def off(self, tid):
        import mido
        got = self.notes.pop(tid, None)
        if got is None:
            return
        ch, note = got
        self.send(mido.Message('note_off', channel=ch, note=note, velocity=64))
        self.active[ch] = max(0, self.active[ch] - 1)
        self.released[ch] = self._tick()

    def sustain(self, down):
        self._cc(MANAGER, 64, 127 if down else 0)

    def mod(self, value):
        # the mod wheel is zone-wide: on the manager, which live fans out to
        # every member (2.3.1)
        self._cc(MANAGER, 1, value)

    def panic(self):
        for tid in list(self.notes):
            self.off(tid)
        self.sustain(False)

    def handle(self, ev):
        """One event from the page (a dict)."""
        t = ev.get('t')
        if t == 'hello':
            self.mcm()
        elif t == 'on':
            self.on(ev['id'], ev['note'], ev.get('vel', 100), ev.get('bend', 0.0),
                    ev.get('tim', 64), ev.get('pres', 0))
        elif t == 'move':
            self.move(ev['id'], ev.get('bend'), ev.get('tim'), ev.get('pres'))
        elif t == 'off':
            self.off(ev['id'])
        elif t == 'sus':
            self.sustain(bool(ev.get('v')))
        elif t == 'mod':
            self.mod(ev.get('v', 0))
        elif t == 'panic':
            self.panic()


# ------------------------------------------------------------------ WebSocket

def ws_accept(key):
    return base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()


def ws_frame(payload, opcode=1, mask=None):
    """One frame. The server's are unmasked; a client's carry `mask`."""
    data = payload.encode() if isinstance(payload, str) else payload
    head = bytes([0x80 | opcode])
    n = len(data)
    mbit = 0x80 if mask is not None else 0
    if n < 126:
        head += bytes([mbit | n])
    elif n < 65536:
        head += bytes([mbit | 126]) + struct.pack('>H', n)
    else:
        head += bytes([mbit | 127]) + struct.pack('>Q', n)
    if mask is not None:
        head += mask
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return head + data


async def ws_read(reader):
    """(opcode, payload bytes) of the next frame; unmasks a client's."""
    b0, b1 = await reader.readexactly(2)
    op, n = b0 & 0x0F, b1 & 0x7F
    if n == 126:
        n = struct.unpack('>H', await reader.readexactly(2))[0]
    elif n == 127:
        n = struct.unpack('>Q', await reader.readexactly(8))[0]
    mask = await reader.readexactly(4) if b1 & 0x80 else None
    data = await reader.readexactly(n)
    if mask:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return op, data


class Server(object):
    def __init__(self, sender, page=PAGE, log=True):
        self.sender = sender
        self.page = page
        self.log = log
        self.clients = 0

    async def serve(self, reader, writer):
        try:
            req = await reader.readuntil(b'\r\n\r\n')
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            writer.close(); return
        lines = req.decode('latin-1').split('\r\n')
        path = lines[0].split(' ')[1] if len(lines[0].split(' ')) > 1 else '/'
        hdr = {l.split(':', 1)[0].strip().lower(): l.split(':', 1)[1].strip()
               for l in lines[1:] if ':' in l}
        if path.startswith('/ws') and hdr.get('upgrade', '').lower() == 'websocket':
            writer.write(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n'
                          'Connection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n'
                          % ws_accept(hdr.get('sec-websocket-key', ''))).encode())
            await writer.drain()
            await self.session(reader, writer)
            return
        body = open(self.page, 'rb').read() if path in ('/', '/index.html') else b'not found'
        code = '200 OK' if path in ('/', '/index.html') else '404 Not Found'
        writer.write(('HTTP/1.1 %s\r\nContent-Type: text/html; charset=utf-8\r\n'
                      'Content-Length: %d\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n'
                      % (code, len(body))).encode() + body)
        await writer.drain()
        writer.close()

    async def session(self, reader, writer):
        self.clients += 1
        if self.log:
            sys.stderr.write("  page connected (%d)\n" % self.clients)
        writer.write(ws_frame(json.dumps({'t': 'ready', 'port': PORT_NAME})))
        await writer.drain()
        try:
            while True:
                op, data = await ws_read(reader)
                if op == 8:                                  # close
                    writer.write(ws_frame(b'', 8)); await writer.drain()
                    break
                if op == 9:                                  # ping
                    writer.write(ws_frame(data, 10)); await writer.drain()
                    continue
                if op != 1:
                    continue
                try:
                    self.sender.handle(json.loads(data.decode()))
                except (ValueError, KeyError) as e:
                    if self.log:
                        sys.stderr.write("  bad event %r: %s\n" % (data[:80], e))
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            # A page that vanishes mid-chord must not leave notes hanging.
            self.sender.panic()
            self.clients -= 1
            writer.close()
            if self.log:
                sys.stderr.write("  page disconnected\n")


def open_port():
    import mido
    return mido.open_output(PORT_NAME, client_name=PORT_NAME)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765, help='HTTP/WebSocket port')
    ap.add_argument('--open', action='store_true', help='open the page in Chromium, app mode')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    out = open_port()
    server = Server(MpeSender(out.send))
    url = 'http://127.0.0.1:%d/' % a.port

    async def run():
        srv = await asyncio.start_server(server.serve, '127.0.0.1', a.port)
        sys.stderr.write("  MIDI port '%s' -- in live: --port touch\n  page: %s\n" % (PORT_NAME, url))
        if a.open:
            import subprocess
            exe = next((e for e in ('chromium', 'chromium-browser', 'google-chrome')
                        if __import__('shutil').which(e)), None)
            if exe:
                # NATIVE WAYLAND INPUT: through XWayland a touch can arrive as
                # a mouse, and multitouch is lost.
                subprocess.Popen([exe, '--app=' + url, '--ozone-platform-hint=auto',
                                  '--touch-events=enabled'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        async with srv:
            await srv.serve_forever()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    finally:
        out.close()


# ------------------------------------------------------------------ selftest

def selftest():
    import threading
    import socket
    import mido
    fails = []

    def check(name, ok, detail=""):
        print("  %-66s %s%s" % (name, "ok" if ok else "FAIL", ("  " + detail) if detail else ""))
        if not ok:
            fails.append(name)

    # framing
    async def roundtrip():
        r = asyncio.StreamReader()
        msg = json.dumps({'t': 'on', 'x': 'é' * 200})
        r.feed_data(ws_frame(msg, mask=b'\x12\x34\x56\x78')); r.feed_eof()
        return await ws_read(r), msg
    (op, data), msg = asyncio.run(roundtrip())
    check("WebSocket frames: a masked 400-byte client frame round-trips",
          op == 1 and data.decode() == msg
          and ws_accept('dGhlIHNhbXBsZSBub25jZQ==') == 's3pPLMBiTxaQ9kYGzzhZRbK+xOo=',
          "  (and the accept key is RFC 6455's own example)")

    # the sender, on its own
    got = []
    s = MpeSender(got.append)
    s.handle({'t': 'hello'})
    chs = [s.on(i, n, 100) for i, n in enumerate((60, 64, 67))]
    first = got[3:7]
    check("MPE: the MCM first, then each note on a member of its own, its "
          "bend, CC74 and pressure before its Note On",
          [(m.control, m.value) for m in got[:3]] == [(101, 0), (100, 6), (6, 15)]
          and len(set(chs)) == 3 and 0 not in chs
          and [m.type for m in first] == ['pitchwheel', 'control_change', 'aftertouch', 'note_on'],
          "  (channels %s)" % [c + 1 for c in chs])
    s.off(1)
    n0 = len(got)
    s.move(1, bend=2.0)
    again = s.on(9, 64, 90)
    check("MPE: nothing per-note after Note Off; a repeated note reuses its channel",
          len(got) == n0 + 4 and again == chs[1],
          "  (E4 back on channel %d)" % (again + 1))

    n0 = len(got)
    s.handle({'t': 'mod', 'v': 90})
    check("the mod wheel is CC1 on the manager",
          len(got) == n0 + 1 and got[-1].type == 'control_change'
          and (got[-1].channel, got[-1].control, got[-1].value) == (MANAGER, 1, 90))

    # end to end: page -> WebSocket -> server -> ALSA -> a MIDI input -> live
    heard = []
    try:
        out = mido.open_output(PORT_NAME + ' test', client_name=PORT_NAME + ' test')
    except Exception as e:
        check("end to end through ALSA", False, "  (%s)" % e)
        print("  FAILED: " + ", ".join(fails)); return False
    time.sleep(0.1)
    name = next(n for n in mido.get_input_names() if (PORT_NAME + ' test') in n)
    inp = mido.open_input(name, callback=heard.append)
    srv_sender = MpeSender(out.send)
    server = Server(srv_sender, log=False)
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    port = []

    def run():
        asyncio.set_event_loop(loop)
        srv = loop.run_until_complete(asyncio.start_server(server.serve, '127.0.0.1', 0))
        port.append(srv.sockets[0].getsockname()[1]); ready.set()
        loop.run_forever()
    th = threading.Thread(target=run, daemon=True); th.start(); ready.wait(2)
    sock = socket.create_connection(('127.0.0.1', port[0]))
    sock.sendall(b'GET /ws HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                 b'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n')
    resp = sock.recv(4096)
    for ev in ({'t': 'hello'},
               {'t': 'on', 'id': 'a', 'note': 60, 'vel': 100},
               {'t': 'on', 'id': 'b', 'note': 64, 'vel': 100},
               {'t': 'on', 'id': 'c', 'note': 67, 'vel': 100},
               {'t': 'move', 'id': 'b', 'bend': 2.0},
               {'t': 'off', 'id': 'a'}, {'t': 'off', 'id': 'b'}, {'t': 'off', 'id': 'c'}):
        sock.sendall(ws_frame(json.dumps(ev), mask=os.urandom(4)))
        time.sleep(0.01)
    time.sleep(0.3)
    sock.sendall(ws_frame(b'', 8, mask=os.urandom(4))); sock.close()
    time.sleep(0.1)
    loop.call_soon_threadsafe(loop.stop)
    inp.close(); out.close()
    ons = [m for m in heard if m.type == 'note_on']
    check("end to end: the page's chord arrives through ALSA on three members",
          b'101 Switching Protocols' in resp and len(ons) == 3
          and len({m.channel for m in ons}) == 3,
          "  (%d messages heard)" % len(heard))
    # ...and live plays it as MPE: the slid note +200 cents, its neighbours not
    sys.path.insert(0, HERE)
    import live as L
    import math
    import numpy as np
    lv = L.Live(program=81, rate=48000, frames=128, verbose=False); lv.warm()
    freqs = {}
    for m in heard:
        lv.on_midi(m); lv.apply(lv.n)
        if m.type == 'pitchwheel' and m.pitch != 0:
            for k, sl in lv.slab.live.items():
                if k[2] in (60, 64, 67):
                    freqs[k[2]] = float(lv.slab.a['om'][list(sl)].min())
        if m.type == 'note_on' and m.note == 67:
            base = {k[2]: float(lv.slab.a['om'][list(sl)].min()) for k, sl in lv.slab.live.items()}
    moved = {n: 1200 * math.log2(freqs[n] / base[n]) for n in freqs}
    lv.renderer.close()
    check("end to end: live hears MPE -- the slid E moves a whole tone, C and G do not",
          lv.mpe.n == {(0, 'lower'): 15} and abs(moved.get(64, 0) - 200.0) < 0.7
          and abs(moved.get(60, 0)) < 1e-6 and abs(moved.get(67, 0)) < 1e-6,
          "  (%s)" % ", ".join("%s %+.2f c" % ({60: 'C', 64: 'E', 67: 'G'}[n], c) for n, c in sorted(moved.items())))
    print("  all passed" if not fails else "  FAILED: " + ", ".join(fails))
    return not fails


if __name__ == '__main__':
    main()
