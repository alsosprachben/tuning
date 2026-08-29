#!/usr/bin/env python3
"""Play the synth live from a MIDI keyboard.

The kernel was built for this: `synth_voice` renders any absolute sample range
statelessly (analytic phase), and it re-reads `non`/`noff` on every call. So a
live front end is not a new synthesiser -- it is a partial table that grows at
note-on and gets one int64 written into it at note-off, rendered a block at a
time by exactly the same C the offline renderer uses.

Two things make it fast enough to play by hand:

  - Note templates. Building one note's partials in Python costs 1.4-7 ms, which
    is most of a 10 ms budget on its own. So each (program, note) is built ONCE,
    through blockrender.prepare() on an in-memory MIDI file -- the same code path
    as an offline render, not a copy of it -- and cached. Note-on then stamps the
    cached columns into a preallocated slab and fixes the phase anchor, which is
    a handful of vectorised numpy writes.

  - Idle partials are nearly free. The kernel skips a partial whose window does
    not overlap the block in ~6 ns, so the slab can be large and mostly dead;
    there is no need to compact it or track an active count.

BLOCK ALIGNMENT MATTERS. The kernel is window-independent only when the window is
a multiple of BLK. Its amplitude envelope is interpolated across the FULL block
and so does not care, but the tension-bend / mode-lock pitch transient computes
its phase from the CLIPPED window start, so a window that splits a block gets a
different transient. Measured against a single-window render of one trumpet note:
512-frame windows at BLK=512 agree to 3.9e-08, but 256-frame windows are off by
1.1e-03, all of it inside the attack where the mode lock lives. So the callback
size and BLK are set equal here. BLK=128 also buys a 2.7 ms control quantum
instead of 10.7 ms, which is what keeps a struck attack from smearing.

Usage:  live.py [--program N] [--port SUBSTRING] [--rate HZ] [--frames N] [--list]
"""
import sys, os, time, threading, argparse, collections, signal

# The kernel enters an OpenMP region per call. At a 256-frame window that is one
# chunk -- no parallelism to gain -- and the default active wait policy spins,
# which measured as multiple milliseconds of jitter on small windows. Must be set
# before the library loads.
os.environ.setdefault("OMP_WAIT_POLICY", "passive")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import mido
import blockrender as B
import tonelib as T

# Columns of the partial table, in the order blockrender builds them.
COLS_F8 = ("om", "p0")
COLS_F4 = ("aL", "aR", "nf", "fa", "re", "ch", "logr", "logrA", "aft", "sus",
           "cv", "cc", "crl", "sj", "csc", "tbav", "tau", "tcut",
           "vd", "vr", "vp", "delL", "delR")
COLS_I8 = ("non", "noff")
COLS_I4 = ("gr", "cr")

IDLE = 1 << 62          # a note-on so far in the future the partial never sounds


class Slab:
    """The live partial table: fixed capacity, slots handed out per note."""

    def __init__(self, capacity=8192):
        self.cap = capacity
        self.a = {}
        for k in COLS_F8: self.a[k] = np.zeros(capacity, np.float64)
        for k in COLS_F4: self.a[k] = np.zeros(capacity, np.float32)
        for k in COLS_I8: self.a[k] = np.full(capacity, IDLE, np.int64)
        for k in COLS_I4: self.a[k] = np.zeros(capacity, np.int32)
        self.a["gr"][:] = -1            # -1 = always on, no organ gate or swell
        self.free = collections.deque(range(capacity))
        self.retiring = []              # slots released, still ringing out
        self.live = {}                  # (channel, note) -> [slot indices]
        # Non-organ voices never read G/S, but the kernel still wants pointers.
        self.G = np.ones((1, 1), np.float32)
        self.S = np.ones((1, 1), np.float32)
        self.sh = (0.06, 1.6, 3.5, 1500.0)
        self._prep_cache = None
        self.rate = 48000.0   # set by Live; needed by retune()
        # Aftertouch recomputes amplitude from an unpressed base rather than
        # scaling what is already there, so repeated messages cannot compound.
        self.aL0 = np.zeros(capacity, np.float32)
        self.aR0 = np.zeros(capacity, np.float32)
        self.hrel = np.ones(capacity, np.float32)   # partial freq / lowest partial

    def prep(self):
        """The kernel takes pointers into these arrays, and the arrays never move
        -- only their contents change -- so the dict is built once. Rebuilding it
        per callback was an allocation on the audio thread."""
        if self._prep_cache is None:
            d = dict(self.a)
            d.update(lib=self.lib, P=self.cap, nblk=1, G=self.G, S=self.S, sh=self.sh)
            self._prep_cache = d
        return self._prep_cache

    def stamp(self, tmpl, key, n0, vel_scale):
        """Place one note's partials at absolute sample n0. Returns False if the
        slab is full -- the caller decides what to do about that."""
        n = tmpl["P"]
        if len(self.free) < n:
            return False
        slots = [self.free.popleft() for _ in range(n)]
        idx = np.fromiter(slots, np.int64, n)
        a = self.a
        for k in COLS_F4:
            a[k][idx] = tmpl[k]
        for k in COLS_I4:
            a[k][idx] = tmpl[k]
        a["om"][idx] = tmpl["om"]
        # Phase is anchored to the note's own onset: p0 = -om*non + ph0. Shift the
        # template's anchor from its build-time onset to this one.
        a["p0"][idx] = tmpl["p0"] + tmpl["om"] * (tmpl["non"] - n0)
        a["non"][idx] = n0
        a["noff"][idx] = IDLE           # held until the key is released
        if vel_scale != 1.0:
            a["aL"][idx] = tmpl["aL"] * vel_scale
            a["aR"][idx] = tmpl["aR"] * vel_scale
        self.aL0[idx] = a["aL"][idx]
        self.aR0[idx] = a["aR"][idx]
        self.hrel[idx] = tmpl["hrel"]
        self.live.setdefault(key, []).extend(slots)
        return True

    def press(self, slots, pressure, gain_db, tilt):
        """Aftertouch: lean on the note and it swells AND opens.

        A wind player pressing harder is not turning up a volume knob -- more air
        is louder and brighter together, which is the same thing the brass voices
        model as register effort: the source's roll-off shallows as the player
        pushes. So pressure lifts the whole note by gain_db and additionally
        tilts the series, scaling each partial by (f/f0)^(tilt*pressure). At zero
        pressure both terms are 1 and the note is exactly as it was played.

        Recomputed from aL0/aR0, never from the current value, so a stream of
        aftertouch messages cannot compound into a runaway.
        """
        if not slots:
            return
        idx = np.fromiter(slots, np.int64, len(slots))
        base = self.aL0[idx].astype(np.float64)
        shape = self.hrel[idx].astype(np.float64) ** (tilt * pressure)
        # The tilt is COLOUR, gain_db is LEVEL -- the same separation the bore
        # filter keeps. Left un-normalised the two compounded and 8 dB of asked-for
        # crescendo arrived as 11.
        p2 = (base * base).sum()
        if p2 > 0.0:
            shape *= (p2 / (((base * shape) ** 2).sum() + 1e-30)) ** 0.5
        shape *= 10.0 ** (gain_db * pressure / 20.0)
        self.a["aL"][idx] = self.aL0[idx] * shape
        self.a["aR"][idx] = self.aR0[idx] * shape

    def retune(self, slots, n, om_scale=None, vd=None):
        """Change a sounding partial's pitch or vibrato WITHOUT a click.

        A partial's phase is ph = p0 + om*n, plus the vibrato's accumulated
        extra, which the kernel recomputes from the CURRENT vd every block:

            E(n) = (fp*vd/vr) * (cos(2*pi*vr*ton + vp) - cos(2*pi*vr*n/sr + vp))

        Change om or vd and both terms jump, which is a click. So work out what
        the total phase is now, apply the change, and put the difference back
        into p0 -- the one field that exists to anchor phase. Both terms move
        together because fp is a function of om, so a bend applied to a note that
        is already vibrating has to account for its effect on E as well.
        """
        if not slots:
            return
        idx = np.fromiter(slots, np.int64, len(slots))
        a = self.a
        om0 = a["om"][idx].copy()
        vd0 = a["vd"][idx].astype(np.float64)
        vr = np.maximum(a["vr"][idx].astype(np.float64), 1e-6)
        vp = a["vp"][idx].astype(np.float64)
        ton = a["non"][idx].astype(np.float64) / self.rate
        tn = n / self.rate
        w2 = 2.0 * np.pi * vr
        swing = np.cos(w2 * ton + vp) - np.cos(w2 * tn + vp)

        def extra(om, vd):
            return (om * self.rate / (2.0 * np.pi)) * vd / vr * swing

        before = extra(om0, vd0)
        om1 = om0 * om_scale if om_scale is not None else om0
        vd1 = np.full(len(idx), float(vd)) if vd is not None else vd0
        after = extra(om1, vd1)
        a["p0"][idx] += (om0 - om1) * n - (after - before)
        if om_scale is not None:
            a["om"][idx] = om1
        if vd is not None:
            a["vd"][idx] = vd1

    def release(self, key, n):
        """Note-off: one write per partial. The kernel picks it up next block."""
        slots = self.live.pop(key, None)
        if not slots:
            return
        idx = np.fromiter(slots, np.int64, len(slots))
        self.a["noff"][idx] = n
        self.retiring.append((idx, n))

    def reap(self, n):
        """Return slots whose release has finished ringing."""
        keep = []
        for idx, off in self.retiring:
            tail = off + float(self.a["re"][idx].max()) + B.BLK
            if n > tail:
                self.a["non"][idx] = IDLE
                self.free.extend(int(i) for i in idx)
            else:
                keep.append((idx, off))
        self.retiring = keep


class Live:
    def __init__(self, program=56, rate=48000, frames=128, capacity=8192,
                 tuner="hybrid", verbose=True):
        B.set_sample_rate(rate)
        B.BLK = frames          # see BLOCK ALIGNMENT in the module docstring
        self.rate, self.frames, self.program, self.tuner = rate, frames, program, tuner
        self.verbose = verbose
        self.slab = Slab(capacity)
        self.slab.lib = B.ensure_lib()
        self.templates = {}
        self.n = 0                       # absolute sample clock
        self.events = collections.deque()
        self.lock = threading.Lock()
        self.slab.rate = float(rate)
        self.bend = {}          # channel -> current pitch-bend ratio
        self.mod = {}           # channel -> current vibrato depth (fraction)
        self.pressure = {}      # channel -> aftertouch 0..1
        self.bend_range = 2.0   # semitones at full wheel, the GM convention
        self.mod_cents = 35.0   # cents of vibrato at full mod wheel
        self.press_db = 8.0     # crescendo at full aftertouch
        self.press_tilt = 0.30  # and it brightens as it swells: see Slab.press
        self.underruns = 0
        self.dropped = 0
        self.peak = 0.0

    # ---- templates ----------------------------------------------------------
    def template(self, note):
        """One note's partial table, built once through the offline code path."""
        t = self.templates.get(note)
        if t is None:
            m = mido.MidiFile(type=1, ticks_per_beat=480)
            tr = mido.MidiTrack(); m.tracks.append(tr)
            tr.append(mido.MetaMessage("set_tempo", tempo=1000000, time=0))
            tr.append(mido.Message("program_change", channel=0, program=self.program, time=0))
            tr.append(mido.Message("note_on", channel=0, note=note, velocity=127, time=0))
            tr.append(mido.Message("note_off", channel=0, note=note, velocity=0, time=480))
            tr.append(mido.MetaMessage("end_of_track", time=480))
            p = B.prepare(m, self.tuner)
            t = {k: np.array(p[k]) for k in COLS_F8 + COLS_F4 + COLS_I8 + COLS_I4}
            t["P"] = p["P"]
            nf = t["nf"].astype(np.float64)
            t["hrel"] = (nf / max(nf.min(), 1e-9)).astype(np.float32)
            self.templates[note] = t
        return t

    def warm(self, lo=36, hi=84):
        """Build templates up front so the first press of a key is not the one
        that costs 2 ms. Cheap enough to just do for the playable range."""
        t0 = time.time()
        for n in range(lo, hi + 1):
            self.template(n)
        if self.verbose:
            tot = sum(t["P"] for t in self.templates.values())
            sys.stderr.write("  %d templates, %d partials, %.2f s (%.2f ms/note)\n"
                             % (len(self.templates), tot, time.time() - t0,
                                (time.time() - t0) / max(len(self.templates), 1) * 1000))

    # ---- midi ---------------------------------------------------------------
    def on_midi(self, msg):
        if msg.type in ("note_on", "note_off", "pitchwheel", "control_change",
                        "aftertouch", "polytouch"):
            with self.lock:
                self.events.append((time.monotonic(), msg))

    def apply(self, n0):
        with self.lock:
            evs, self.events = self.events, collections.deque()
        for stamped, msg in evs:
            ch = msg.channel
            if msg.type == "pitchwheel":
                # MIDI pitch bend is +/- 8192 over the wheel's range, which is
                # +/- bend_range semitones by convention.
                ratio = 2.0 ** (msg.pitch / 8192.0 * self.bend_range / 12.0)
                prev = self.bend.get(ch, 1.0)
                self.bend[ch] = ratio
                if prev != ratio:
                    self.slab.retune(self._sounding(ch), n0, om_scale=ratio / prev)
            elif msg.type == "aftertouch":
                self.pressure[ch] = msg.value / 127.0
                self.slab.press(self._sounding(ch), self.pressure[ch],
                                self.press_db, self.press_tilt)
            elif msg.type == "polytouch":
                self.slab.press(self.slab.live.get((ch, msg.note), []),
                                msg.value / 127.0, self.press_db, self.press_tilt)
            elif msg.type == "control_change":
                if msg.control == 1:
                    # THE MOD WHEEL IS VIBRATO. That is what it is for on a wind
                    # or string patch, and it is the one control every library
                    # agrees on after dynamics. The machinery already exists --
                    # it is the per-player vibrato built for the string sections
                    # -- so here it is simply driven by hand instead of by seed.
                    depth = (2.0 ** (self.mod_cents * msg.value / 127.0 / 1200.0)) - 1.0
                    self.mod[ch] = depth
                    self.slab.retune(self._sounding(ch), n0, vd=depth)
                elif msg.control == 123:                # all notes off
                    for k in [k for k in self.slab.live if k[0] == ch]:
                        self.slab.release(k, n0)
            elif msg.type == "note_on" and msg.velocity > 0:
                key = (ch, msg.note)
                tmpl = self.template(msg.note)
                scale = (msg.velocity / 127.0) ** 2
                if not self.slab.stamp(tmpl, key, n0, scale):
                    self.dropped += 1
                    continue
                # a note started while the wheel is up must join in progress
                slots = self.slab.live.get(key)
                pr = self.pressure.get(ch, 0.0)
                if pr:
                    self.slab.press(slots, pr, self.press_db, self.press_tilt)
                b, v = self.bend.get(ch, 1.0), self.mod.get(ch, 0.0)
                if b != 1.0 or v != 0.0:
                    self.slab.retune(slots, n0, om_scale=(b if b != 1.0 else None),
                                     vd=(v if v != 0.0 else None))
            else:
                self.slab.release((ch, msg.note), n0)

    def _sounding(self, ch):
        out = []
        for (c, _), slots in self.slab.live.items():
            if c == ch:
                out.extend(slots)
        return out

    # ---- audio --------------------------------------------------------------
    def callback(self, in_data, frame_count, time_info, status):
        import pyaudio
        if status:
            self.underruns += 1
        n0 = self.n
        self.apply(n0)
        self.slab.reap(n0)
        L, R = B.synth_window(self.slab.prep(), n0, frame_count)
        self.n = n0 + frame_count
        p = float(max(np.abs(L).max(), np.abs(R).max()))
        if p > self.peak:
            self.peak = p
        st = np.empty(frame_count * 2, np.float32)
        st[0::2] = L; st[1::2] = R
        return (st.tobytes(), pyaudio.paContinue)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", type=int, default=56, help="GM program (default 56, trumpet)")
    ap.add_argument("--port", default=None, help="substring of the MIDI input port name")
    ap.add_argument("--rate", type=int, default=48000)
    ap.add_argument("--frames", type=int, default=128,
                help="audio block; also becomes the kernel control block (see docstring)")
    ap.add_argument("--tuner", default="hybrid")
    ap.add_argument("--list", action="store_true", help="list MIDI inputs and exit")
    a = ap.parse_args()

    names = mido.get_input_names()
    if a.list:
        for n in names:
            print(" ", n)
        return
    if not names:
        sys.exit("no MIDI inputs found (is the keyboard plugged in?)")
    name = next((n for n in names if a.port and a.port.lower() in n.lower()), names[0])

    import pyaudio
    live = Live(program=a.program, rate=a.rate, frames=a.frames, tuner=a.tuner)
    cls = __import__("patch_map").property_class_for_program(a.program).__name__
    sys.stderr.write("  program %d -> %s at %d Hz, %d-frame blocks\n"
                     % (a.program, cls, a.rate, a.frames))
    live.warm()

    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paFloat32, channels=2, rate=a.rate, output=True,
                     frames_per_buffer=a.frames, stream_callback=live.callback)
    port = mido.open_input(name, callback=live.on_midi)
    sys.stderr.write("  listening on %s -- ctrl-c to stop\n" % name)
    # SIGTERM as well as ctrl-c, so `timeout 90 live.py` still reports its stats
    # instead of being killed silently.
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    stream.start_stream()
    last = time.monotonic()
    try:
        while stream.is_active() and not stop.is_set():
            time.sleep(0.2)
            if time.monotonic() - last >= 5.0:
                last = time.monotonic()
                sounding = sum(len(v) for v in live.slab.live.values())
                sys.stderr.write("    %5.1f s  peak %.3f  sounding %4d partials  "
                                 "free %5d  underruns %d  dropped %d\n"
                                 % (live.n / live.rate, live.peak, sounding,
                                    len(live.slab.free), live.underruns, live.dropped))
                sys.stderr.flush()
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream(); stream.close(); pa.terminate(); port.close()
        sys.stderr.write("\n  peak %.3f  underruns %d  dropped %d\n"
                         % (live.peak, live.underruns, live.dropped))


if __name__ == "__main__":
    main()
