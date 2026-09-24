#!/usr/bin/env python3
"""A MIDI 2.0 client of the ALSA sequencer, through ctypes: UMP in and out.

    python3 alsaump.py --list              the sequencer's ports
    python3 alsaump.py --selftest          two clients talk UMP; a MIDI 1.0
                                           sender reaches a MIDI 2.0 reader

No Python MIDI library speaks UMP yet (mido 1.2, python-rtmidi 1.5), but
alsa-lib has since 1.2.10: a client that declares itself MIDI 2.0 with
snd_seq_set_client_midi_version reads and writes snd_seq_ump_event_t, and the
kernel's sequencer converts between it and every legacy MIDI 1.0 client. So
this is also a second bridge -- the kernel's -- beside ump.Midi1to2.

THE STRUCT is snd_seq_ump_event_t from alsa-lib 1.2.11's include/seq_event.h,
which is not installed here (no libasound2-dev), so it is spelled out below
from the source rather than guessed:

    u8 type, u8 flags, u8 tag, u8 queue          0..3
    snd_seq_timestamp_t time (8 bytes)           4..11
    snd_seq_addr_t source {u8 client, u8 port}   12..13
    snd_seq_addr_t dest                          14..15
    union { legacy data; u32 ump[4] }            16..31

SND_SEQ_EVENT_UMP (flags bit 5) marks a UMP event; `type` is then unused.
"""
import ctypes
import ctypes.util
import os
import select
import threading

SND_SEQ_OPEN_DUPLEX = 3
SND_SEQ_NONBLOCK = 1
SND_SEQ_CLIENT_UMP_MIDI_2_0 = 2
SND_SEQ_EVENT_UMP = 1 << 5
SND_SEQ_QUEUE_DIRECT = 253
SND_SEQ_ADDRESS_SUBSCRIBERS = 254
CAP_READ, CAP_WRITE, CAP_SUBS_READ, CAP_SUBS_WRITE = 1 << 0, 1 << 1, 1 << 5, 1 << 6
TYPE_MIDI_GENERIC, TYPE_APPLICATION = 1 << 1, 1 << 20
EAGAIN = 11


class Addr(ctypes.Structure):
    _fields_ = [("client", ctypes.c_ubyte), ("port", ctypes.c_ubyte)]


class UmpEvent(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ubyte), ("flags", ctypes.c_ubyte),
                ("tag", ctypes.c_ubyte), ("queue", ctypes.c_ubyte),
                ("time", ctypes.c_uint32 * 2),
                ("source", Addr), ("dest", Addr),
                ("ump", ctypes.c_uint32 * 4)]


class PollFd(ctypes.Structure):
    _fields_ = [("fd", ctypes.c_int), ("events", ctypes.c_short), ("revents", ctypes.c_short)]


assert ctypes.sizeof(UmpEvent) == 32


def _lib():
    name = ctypes.util.find_library("asound") or "libasound.so.2"
    lib = ctypes.CDLL(name, use_errno=True)
    if not hasattr(lib, "snd_seq_set_client_midi_version"):
        raise OSError("alsa-lib is older than 1.2.10: no UMP sequencer API")
    P = ctypes.c_void_p
    lib.snd_seq_open.argtypes = [ctypes.POINTER(P), ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    lib.snd_seq_close.argtypes = [P]
    lib.snd_seq_client_id.argtypes = [P]
    lib.snd_seq_set_client_name.argtypes = [P, ctypes.c_char_p]
    lib.snd_seq_set_client_midi_version.argtypes = [P, ctypes.c_int]
    lib.snd_seq_create_simple_port.argtypes = [P, ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint]
    lib.snd_seq_connect_from.argtypes = [P, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.snd_seq_connect_to.argtypes = [P, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.snd_seq_parse_address.argtypes = [P, ctypes.POINTER(Addr), ctypes.c_char_p]
    lib.snd_seq_ump_event_input.argtypes = [P, ctypes.POINTER(ctypes.POINTER(UmpEvent))]
    lib.snd_seq_ump_event_output_direct.argtypes = [P, ctypes.POINTER(UmpEvent)]
    lib.snd_seq_poll_descriptors_count.argtypes = [P, ctypes.c_short]
    lib.snd_seq_poll_descriptors.argtypes = [P, ctypes.POINTER(PollFd), ctypes.c_uint, ctypes.c_short]
    return lib


class UmpClient(object):
    """One MIDI 2.0 client with one port that both receives and sends.

    `on_packet(words)` is called on the client's own thread for each UMP
    received -- which is where live.on_ump goes."""

    def __init__(self, name="tuning", port_name="MIDI 2.0 in", on_packet=None):
        self.lib = _lib()
        self.seq = ctypes.c_void_p()
        r = self.lib.snd_seq_open(ctypes.byref(self.seq), b"default",
                                  SND_SEQ_OPEN_DUPLEX, SND_SEQ_NONBLOCK)
        if r < 0:
            raise OSError("snd_seq_open: %d" % r)
        self.lib.snd_seq_set_client_name(self.seq, name.encode())
        r = self.lib.snd_seq_set_client_midi_version(self.seq, SND_SEQ_CLIENT_UMP_MIDI_2_0)
        if r < 0:
            raise OSError("this kernel's sequencer has no MIDI 2.0 clients (%d)" % r)
        self.client = self.lib.snd_seq_client_id(self.seq)
        self.port = self.lib.snd_seq_create_simple_port(
            self.seq, port_name.encode(),
            CAP_READ | CAP_WRITE | CAP_SUBS_READ | CAP_SUBS_WRITE,
            TYPE_MIDI_GENERIC | TYPE_APPLICATION)
        if self.port < 0:
            raise OSError("snd_seq_create_simple_port: %d" % self.port)
        self.on_packet = on_packet
        self._stop = threading.Event()
        self._thread = None

    @property
    def address(self):
        return "%d:%d" % (self.client, self.port)

    def resolve(self, spec):
        """'20:0', or a client name such as 'USB Midi' -> (client, port)."""
        a = Addr()
        r = self.lib.snd_seq_parse_address(self.seq, ctypes.byref(a), spec.encode())
        if r < 0:
            raise OSError("no sequencer port %r" % spec)
        return a.client, a.port

    def connect_from(self, spec):
        """Subscribe this port to a sender: the kernel converts a MIDI 1.0
        sender's events to UMP on the way."""
        c, p = self.resolve(spec)
        r = self.lib.snd_seq_connect_from(self.seq, self.port, c, p)
        if r < 0:
            raise OSError("connect from %s: %d" % (spec, r))
        return c, p

    def connect_to(self, spec):
        c, p = self.resolve(spec)
        r = self.lib.snd_seq_connect_to(self.seq, self.port, c, p)
        if r < 0:
            raise OSError("connect to %s: %d" % (spec, r))
        return c, p

    def send(self, words, dest=None):
        """One UMP, now: to `dest` (client, port), or to every subscriber."""
        ev = UmpEvent()
        ev.flags = SND_SEQ_EVENT_UMP
        ev.queue = SND_SEQ_QUEUE_DIRECT
        ev.source.client, ev.source.port = self.client, self.port
        if dest is None:
            ev.dest.client, ev.dest.port = SND_SEQ_ADDRESS_SUBSCRIBERS, 0
        else:
            ev.dest.client, ev.dest.port = dest
        for i, w in enumerate(words[:4]):
            ev.ump[i] = w & 0xFFFFFFFF
        r = self.lib.snd_seq_ump_event_output_direct(self.seq, ctypes.byref(ev))
        if r < 0:
            raise OSError("snd_seq_ump_event_output_direct: %d" % r)

    def read_pending(self):
        """Every UMP waiting now, as word tuples, without blocking."""
        import ump as _U
        out = []
        p = ctypes.POINTER(UmpEvent)()
        while True:
            r = self.lib.snd_seq_ump_event_input(self.seq, ctypes.byref(p))
            if r < 0:
                break
            ev = p.contents
            if ev.flags & SND_SEQ_EVENT_UMP:
                w0 = ev.ump[0]
                n = _U.WORDS[(w0 >> 28) & 0xF]
                out.append(tuple(ev.ump[i] for i in range(n)))
        return out

    def _fds(self):
        n = self.lib.snd_seq_poll_descriptors_count(self.seq, select.POLLIN)
        arr = (PollFd * n)()
        self.lib.snd_seq_poll_descriptors(self.seq, arr, n, select.POLLIN)
        return [arr[i].fd for i in range(n)]

    def start(self):
        """Read on a thread of our own until close(), handing each UMP on."""
        po = select.poll()
        for fd in self._fds():
            po.register(fd, select.POLLIN)

        def run():
            while not self._stop.is_set():
                if not po.poll(100):
                    continue
                for w in self.read_pending():
                    if self.on_packet:
                        self.on_packet(w)
        self._thread = threading.Thread(target=run, daemon=True, name="alsa-ump")
        self._thread.start()
        return self

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(1.0)
        if self.seq:
            self.lib.snd_seq_close(self.seq)
            self.seq = ctypes.c_void_p()


def list_ports():
    """The sequencer's clients and ports, from /proc (what aconnect reads)."""
    try:
        return open("/proc/asound/seq/clients").read()
    except OSError:
        return ""


def selftest():
    import time
    import ump as U
    fails = []

    def check(name, ok, detail=""):
        print("  %-66s %s%s" % (name, "ok" if ok else "FAIL", ("  " + detail) if detail else ""))
        if not ok:
            fails.append(name)
    got = []
    rx = UmpClient("tuning-rx", on_packet=got.append).start()
    tx = UmpClient("tuning-tx")
    tx.connect_to(rx.address)
    sent = [U.m2_note_on(0, 0, 64, 0xC000, 3, U.semitones_to_q(63.8631, 9)),
            U.m2_per_note_bend(0, 0, 64, 0x9000_0000),
            U.m2_cc(0, 0, 11, 0x8040_2010), U.m2_note_off(0, 0, 64, 0)]
    for p in sent:
        tx.send(p)
    t0 = time.monotonic()
    while len(got) < len(sent) and time.monotonic() - t0 < 2.0:
        time.sleep(0.01)
    check("two MIDI 2.0 clients pass UMP through the kernel untouched",
          got == [tuple(p) for p in sent],
          "  (%d of %d; a Pitch 7.9 attribute and a 32-bit CC survive bit for bit)"
          % (len(got), len(sent)))
    # THE KERNEL'S OWN BRIDGE: a MIDI 1.0 client's bytes arrive as UMP. It is a
    # cross-check on ump.Midi1to2 rather than a replacement for it.
    got.clear()
    try:
        import mido
        # rtmidi is a MIDI 1.0 client: it opens our port as it would any other.
        name = next(n for n in mido.get_output_names() if n.startswith("tuning-rx:"))
        out = mido.open_output(name)
        time.sleep(0.05)
        msgs = [mido.Message("note_on", channel=2, note=60, velocity=100),
                mido.Message("control_change", channel=2, control=74, value=87),
                mido.Message("pitchwheel", channel=2, pitch=1234),
                mido.Message("note_on", channel=2, note=60, velocity=0)]
        for m in msgs:
            out.send(m)
        t0 = time.monotonic()
        while len(got) < len(msgs) and time.monotonic() - t0 < 2.0:
            time.sleep(0.01)
        tr = U.Midi1to2()
        mine = [tuple(p) for m in msgs for p in tr.feed(m)]
        # ONE KNOWN DIFFERENCE. D.3.1: a velocity-0 Note On "shall be
        # translated to a MIDI 2.0 Protocol Note Off message with Velocity
        # 0x8000". Linux 6.8's sequencer sends velocity 0x0000. ump.py follows
        # the spec; the engine does not read note-off velocity, so the two
        # bridges sound the same.
        kern = [p[:1] + (0,) + p[2:] if ((p[0] >> 20) & 0xF) == 0x8 and p[1] == 0x80000000
                else p for p in mine]
        check("a MIDI 1.0 sender reaches a MIDI 2.0 client as the spec's translation",
              got == kern,
              "  (%d packets identical to ump.Midi1to2, but for the kernel's note-off "
              "velocity 0x0000 where D.3.1 says 0x8000)" % len(got))
        out.close()
    except Exception as e:
        check("a MIDI 1.0 sender reaches a MIDI 2.0 client as the spec's translation",
              False, "  (%s: %s)" % (type(e).__name__, e))
    rx.close(); tx.close()
    print("  all passed" if not fails else "  FAILED: " + ", ".join(fails))
    return not fails


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    if "--list" in sys.argv:
        print(list_ports())
        sys.exit(0)
    print(__doc__)
