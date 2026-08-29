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
from percussion_map import percussion_for_note, choke_group, GM_PERCUSSION_CHANNEL

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
        # A slot can be scheduled for retirement twice -- stamp() schedules a
        # one-shot's natural end, and choking it pops `oneshot` and calls
        # release(), which schedules it again -- so freeing has to be idempotent
        # or the slot is handed out twice and the free list grows past capacity.
        self.busy = np.zeros(capacity, bool)
        self.live = {}                  # (channel, note) -> [slot indices]
        self.oneshot = {}               # keys whose note-off must be ignored
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
        # LIVE HAS NO NORMALISE. Every offline render ends in a peak normalise to
        # -1 dBFS, and the voice gains were calibrated on that assumption -- a
        # single kick peaks at 0.568 on its own, so two of them clip. A stream
        # cannot know its own peak in advance, so it needs headroom up front and
        # a limiter behind. Set by Live from --headroom.
        self.headroom = 1.0

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
        return self.stamp_cols(tmpl, tmpl["P"], key, n0, vel_scale,
                               tmpl["hrel"], tmpl.get("dur", 0), tmpl.get("oneshot"))

    def stamp_cols(self, tmpl, n, key, n0, vel_scale, hrel, dur, oneshot):
        """As stamp(), but over an arbitrary column dict -- so one organ RANK can
        be placed on its own, which is what drawing a stop mid-note means."""
        if n == 0:
            return True     # unmapped note: silent, but not a dropped note
        if len(self.free) < n:
            return False
        slots = [self.free.popleft() for _ in range(n)]
        idx = np.fromiter(slots, np.int64, n)
        self.busy[idx] = True
        a = self.a
        for k in COLS_F4:
            a[k][idx] = tmpl[k]
        for k in COLS_I4:
            a[k][idx] = tmpl[k]
        a["gr"][idx] = -1     # ungated: a drawn rank is one we stamped
        a["cr"][idx] = 0
        a["om"][idx] = tmpl["om"]
        # Phase is anchored to the note's own onset: p0 = -om*non + ph0. Shift the
        # template's anchor from its build-time onset to this one.
        a["p0"][idx] = tmpl["p0"] + tmpl["om"] * (tmpl["non"] - n0)
        a["non"][idx] = n0
        # A sustaining voice is held until the key is released; a struck one
        # already knows how long it rings and must not be cut short by note-off.
        a["noff"][idx] = (n0 + dur) if oneshot else IDLE
        if oneshot:
            self.retiring.append((idx, n0 + dur))
        if vel_scale != 1.0:
            a["aL"][idx] = tmpl["aL"] * vel_scale
            a["aR"][idx] = tmpl["aR"] * vel_scale
        if self.headroom != 1.0:
            a["aL"][idx] *= self.headroom
            a["aR"][idx] *= self.headroom
        self.aL0[idx] = a["aL"][idx]
        self.aR0[idx] = a["aR"][idx]
        self.hrel[idx] = hrel
        self.live.setdefault(key, []).extend(slots)
        if oneshot:
            self.oneshot[key] = True
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
        if self.oneshot.get(key):
            self.oneshot.pop(key, None)
            return                      # struck: it rings out, note-off is not a stop
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
                live = idx[self.busy[idx]]
                self.busy[live] = False
                self.free.extend(int(i) for i in live)
            else:
                keep.append((idx, off))
        self.retiring = keep


class Live:
    def __init__(self, program=56, rate=48000, frames=128, capacity=8192,
                 tuner="hybrid", verbose=True, drums=False, headroom_db=4.0):
        B.set_sample_rate(rate)
        B.BLK = frames          # see BLOCK ALIGNMENT in the module docstring
        self.rate, self.frames, self.program, self.tuner = rate, frames, program, tuner
        self.drums = drums
        pc = __import__("patch_map").property_class_for_program(program)
        self.organ = (not drums) and getattr(pc, "registerable", False)
        self.rank_names = [r[0] for r in getattr(pc, "stop_ranks", [])]
        # The order a crescendo pedal adds them in, which is the organ's own idea
        # of how a registration should grow.
        self.cres_order = list(getattr(pc, "crescendo_order", self.rank_names))
        self.drawn = set(self.cres_order[:1])    # start on the 8' foundation
        self.cres = 0.0
        # WHICH KEYS ARE DOWN, tracked explicitly. It used to be inferred from
        # what the slab was sounding, which is not the same thing: the crescendo
        # retires ranks OUT of the slab, so a held note could lose every rank it
        # had and vanish from the only record that it was still down.
        self.down = set()
        self.stuck = 0
        self.measure = False    # --latency: record MIDI-to-DAC for each note
        self.lat = []
        self._dac = self._cur = self._wall = 0.0
        self.pedal = {}         # channel -> sustain pedal down
        self.pedalled = set()   # keys whose damper the pedal is holding off
        self.nbuckets = 1
        self.verbose = verbose
        self.slab = Slab(capacity)
        self.slab.lib = B.ensure_lib()
        self.templates = {}
        # Measured, not assumed: 8 bands if this voice's timbre moves with
        # velocity, 1 if velocity is pure gain. See _vel_dependent().
        if not drums:
            self.nbuckets = 8 if self._vel_dependent() else 1
        self.n = 0                       # absolute sample clock
        self.events = collections.deque()
        self.lock = threading.Lock()
        self.slab.rate = float(rate)
        self.slab.headroom = 10.0 ** (-headroom_db / 20.0)
        self.bend = {}          # channel -> current pitch-bend ratio
        self.mod = {}           # channel -> current vibrato depth (fraction)
        self.pressure = {}      # channel -> aftertouch 0..1
        self.bend_range = 2.0   # semitones at full wheel, the GM convention
        self.mod_cents = 35.0   # cents of vibrato at full mod wheel
        self.thresh = 0.70      # soft-limiter knee; see Live.limit
        self.press_db = 8.0     # crescendo at full aftertouch
        self.press_tilt = 0.30  # and it brightens as it swells: see Slab.press
        self.underruns = 0
        self.dropped = 0
        self.errors = 0
        self.last_error = None
        self.peak = 0.0

    # ---- templates ----------------------------------------------------------
    def _vel_dependent(self):
        """Does this voice's SPECTRUM change with velocity, or only its level?

        Measured rather than assumed: build the same note soft and loud and see
        whether the partial amplitudes differ by a constant factor. If they do,
        velocity is pure gain and one template serves every dynamic. If they do
        not -- a piano, whose hammer fills the strike comb as it is struck harder
        -- the timbre has to be built per velocity band.
        """
        try:
            loud = self._raw_template(60, 127)
            soft = self._raw_template(60, 32)
        except Exception:
            return False
        if loud["P"] != soft["P"] or loud["P"] == 0:
            return True
        r = soft["aL"] / np.maximum(loud["aL"], 1e-30)
        r = r[np.isfinite(r) & (r > 0)]
        return bool(len(r) and r.max() / max(r.min(), 1e-30) > 1.01)

    def bucket(self, vel):
        return min(self.nbuckets - 1, int(vel * self.nbuckets / 128.0))

    def bucket_vel(self, b):
        """The velocity a bucket is built at: the centre of its band."""
        return int(min(127, (b + 0.5) * 128.0 / self.nbuckets))

    def template(self, note, vel=127):
        """One note's partial table, built once through the offline code path.

        Keyed by (note, velocity bucket). Most voices scale linearly with
        velocity, so one bucket serves them all. A piano does not: the hammer's
        contact patch widens with force and fills the strike comb, and its
        low-pass corner opens, so a template built fortissimo and merely turned
        down is a fortissimo note played quietly. See _vel_dependent().
        """
        b = self.bucket(vel)
        t = self.templates.get((note, b))
        if t is None:
            t = self._raw_template(note, self.bucket_vel(b))
            self.templates[(note, b)] = t
        return t

    def _raw_template(self, note, vel):
        """Build one note at one velocity, with no bucket lookup in the way."""
        if True:
            ch = GM_PERCUSSION_CHANNEL if self.drums else 0
            m = mido.MidiFile(type=1, ticks_per_beat=480)
            tr = mido.MidiTrack(); m.tracks.append(tr)
            tr.append(mido.MetaMessage("set_tempo", tempo=1000000, time=0))
            if not self.drums:
                tr.append(mido.Message("program_change", channel=ch, program=self.program, time=0))
            if self.organ:
                # Draw everything so every rank emits partials AND speaks at the
                # note's own onset. The live registration is then decided by which
                # ranks we choose to stamp, not by a gate over ones already there.
                tr.append(mido.Message("control_change", channel=ch, control=11, value=127, time=0))
                tr.append(mido.Message("control_change", channel=ch, control=43, value=127, time=0))
            tr.append(mido.Message("note_on", channel=ch, note=note, velocity=vel, time=0))
            tr.append(mido.Message("note_off", channel=ch, note=note, velocity=0, time=480))
            # A struck drum ignores note-off and rings out on its own decay, so
            # prepare() extends it to 8 s. The template has to be long enough to
            # hold that, or the tail is cut at build time.
            tr.append(mido.MetaMessage("end_of_track", time=480 * (18 if self.drums else 1)))
            p = B.prepare(m, self.tuner)
            t = {k: np.array(p[k]) for k in COLS_F8 + COLS_F4 + COLS_I8 + COLS_I4}
            t["P"] = p["P"]
            nf = t["nf"].astype(np.float64)
            # An unmapped drum note builds NOTHING: percussion_for_note has no
            # voice for it and prepare() emits no partials. A zero-partial
            # template is legal, not an error, and must not reach nf.min().
            t["hrel"] = ((nf / max(nf.min(), 1e-9)).astype(np.float32)
                         if len(nf) else np.zeros(0, np.float32))
            # A one-shot voice's length is its own decay, decided at build time.
            # Live, that means note-off must NOT truncate it -- see stamp/release.
            t["oneshot"] = bool(self.drums and t["P"] and
                                (t["noff"][0] - t["non"][0]) > 4.0 * B.SR)
            t["dur"] = int(t["noff"][0] - t["non"][0]) if t["P"] else 0
            if self.organ:
                # gr is the rank index the offline gate would have used, so it is
                # exactly the label needed to slice this template per stop.
                gr = t["gr"]
                t["ranks"] = {}
                for i, nm in enumerate(self.rank_names):
                    m = gr == i
                    if not m.any():
                        continue
                    cols = {k: t[k][m] for k in COLS_F8 + COLS_F4 + COLS_I8 + COLS_I4}
                    t["ranks"][nm] = (cols, int(m.sum()), t["hrel"][m])
            t["vel"] = vel
            return t

    def warm(self, lo=None, hi=None):
        """Build templates up front so the first press of a key is not the one
        that costs 2 ms. Cheap enough to just do for the playable range."""
        if lo is None:
            lo, hi = (35, 81) if self.drums else (21, 96)   # the GM kit, or a keyboard
        t0 = time.time()
        for n in range(lo, hi + 1):
            for b in range(self.nbuckets):
                try:
                    self.template(n, self.bucket_vel(b))
                except Exception:
                    pass                # unmapped drum note: nothing to build
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
            if self.measure and msg.type == "note_on" and msg.velocity > 0 and self._dac:
                # When will this note's first sample leave the DAC, in the same
                # clock the MIDI message was stamped in?
                # Two separable parts: how long the message waited to be picked
                # up (USB + ALSA + rtmidi + our queue), and how far ahead of the
                # DAC we are rendering (the audio buffer).
                self.lat.append(((self._wall - stamped), (self._dac - self._cur)))
            try:
                self._one(n0, msg)
            except Exception as e:
                # One malformed or unhandleable message must never stop the
                # audio. An unmapped drum note used to raise here and kill the
                # stream mid-performance.
                self.errors += 1
                self.last_error = "%s: %s" % (type(e).__name__, e)

    def _one(self, n0, msg):
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
            if msg.control == 1 and self.organ:
                # THE MOD WHEEL IS A CRESCENDO PEDAL. Rolling it up adds stops in
                # the organ's own crescendo order; rolling it down retires them.
                # A stop drawn while keys are held speaks AS A FRESH PIPE -- new
                # partials stamped at this instant, with their own speech -- which
                # is what actually happens when you pull a stop mid-chord. The
                # offline renderer gets this from rank_speak_sec by scanning
                # forward through future CC events; live it is simply now.
                self.cres = msg.value / 127.0
                n = int(self.cres * len(self.cres_order) + 1e-9)
                want = set(self.cres_order[:max(1, n)])   # the 8' never retires
                for rank in want - self.drawn:
                    for (c, note) in self._held(ch):
                        self._draw(self.template(note), c, note, rank, n0)
                for rank in self.drawn - want:
                    for k in [k for k in self.slab.live if len(k) == 3 and k[2] == rank]:
                        self.slab.release(k, n0)
                self.drawn = want
            elif msg.control == 1:
                # THE MOD WHEEL IS VIBRATO. That is what it is for on a wind
                # or string patch, and it is the one control every library
                # agrees on after dynamics. The machinery already exists --
                # it is the per-player vibrato built for the string sections
                # -- so here it is simply driven by hand instead of by seed.
                depth = (2.0 ** (self.mod_cents * msg.value / 127.0 / 1200.0)) - 1.0
                self.mod[ch] = depth
                self.slab.retune(self._sounding(ch), n0, vd=depth)
            elif msg.control == 64:                 # sustain pedal
                downp = msg.value >= 64
                was = self.pedal.get(ch, False)
                self.pedal[ch] = downp
                if was and not downp:
                    # Pedal up: every damper falls at once.
                    for k in [k for k in self.pedalled if k[0] == ch]:
                        self.slab.release(k, n0)
                    self.pedalled = {k for k in self.pedalled if k[0] != ch}
            elif msg.control == 123:                # all notes off
                self.down = {k for k in self.down if k[0] != ch}
                self.pedalled = {k for k in self.pedalled if k[0] != ch}
                self.pedal[ch] = False
                for k in [k for k in self.slab.live if k[0] == ch]:
                    self.slab.oneshot.pop(k, None)
                    self.slab.release(k, n0)
        elif msg.type == "note_on" and msg.velocity > 0:
            key = (ch, msg.note)
            # Every voice records the key as down, not just the organ. The
            # stuck-note sweep releases whatever is sounding without a key behind
            # it, so a voice that never registered its key had every note swept
            # a block after it started -- notes dying in a fraction of a second.
            self.down.add((ch, msg.note))
            tmpl = self.template(msg.note, msg.velocity)
            # Timbre is quantised to the bucket, level is not: trim by the ratio
            # of the actual velocity to the one the bucket was built at.
            scale = ((msg.velocity / 127.0) ** 2 /
                     max((tmpl.get("vel", 127) / 127.0) ** 2, 1e-9))
            if self.organ:
                # A pipe organ has no touch: a key is open or shut, and the wind
                # does the rest. Velocity is deliberately ignored.
                for rank in self.drawn:
                    self._draw(tmpl, ch, msg.note, rank, n0)
                return
            if not self.slab.stamp(tmpl, key, n0, scale):
                self.dropped += 1
                self.down.discard((ch, msg.note))
                return                  # slab full: this note does not sound
            # a note started while the wheel is up must join in progress
            slots = self.slab.live.get(key)
            if self.drums:
                # CHOKE, live. Offline this is done by scanning FORWARD for
                # the next strike in the exclusive class and truncating the
                # earlier note to it. Live there is no forward to scan -- but
                # the strike that does the choking is happening right now, so
                # it is simply a note-off written into whatever is ringing.
                grp = choke_group(msg.note)
                if grp:
                    for k in [k for k in self.slab.live if k[1] in grp and k[1] != msg.note]:
                        self.slab.oneshot.pop(k, None)
                        self.slab.release(k, n0)
            pr = self.pressure.get(ch, 0.0)
            if pr:
                self.slab.press(slots, pr, self.press_db, self.press_tilt)
            b, v = self.bend.get(ch, 1.0), self.mod.get(ch, 0.0)
            if b != 1.0 or v != 0.0:
                self.slab.retune(slots, n0, om_scale=(b if b != 1.0 else None),
                                 vd=(v if v != 0.0 else None))
        else:
            self.down.discard((ch, msg.note))
            if self.pedal.get(ch, False) and not self.organ:
                # The key is up but the damper is not: the string keeps ringing
                # until the pedal is lifted. Recorded so the stuck-note sweep
                # does not mistake it for a lost note-off and cut it.
                self.pedalled.add((ch, msg.note))
                return
            if self.organ:
                for k in [k for k in self.slab.live
                          if len(k) == 3 and k[0] == ch and k[1] == msg.note]:
                    self.slab.release(k, n0)
            else:
                self.slab.release((ch, msg.note), n0)

    def _draw(self, tmpl, ch, note, rank, n0):
        got = tmpl.get("ranks", {}).get(rank)
        if not got:
            return
        cols, n, hrel = got
        if not self.slab.stamp_cols(cols, n, (ch, note, rank), n0, 1.0, hrel, 0, False):
            self.dropped += 1

    def _held(self, ch):
        """Notes actually down on this channel -- from the key state, not from
        whatever happens to be sounding."""
        return sorted(k for k in self.down if k[0] == ch)

    def sweep(self, n):
        """Release anything sounding whose key is not down.

        A dropped note-off would otherwise drone forever, which is what a long
        session produced: 221 partials held and never freed, with the audio
        thread perfectly healthy underneath. Cheap, and it turns a lost message
        into a note that ends slightly late rather than one that never ends.
        """
        for k in [k for k in self.slab.live
                  if (k[0], k[1]) not in self.down
                  and (k[0], k[1]) not in self.pedalled
                  and not self.slab.oneshot.get(k)]:
            self.slab.release(k, n)
            self.stuck += 1

    def _sounding(self, ch):
        """Every slot sounding on this channel.

        Keys are (channel, note) for a normal voice but (channel, note, RANK) for
        the organ, so this indexes rather than unpacks. Unpacking as a pair meant
        pitch bend and aftertouch raised on every organ note -- caught by the
        per-message guard, so the audio was fine and the controls simply did
        nothing, which is exactly the kind of failure a guard can hide. It only
        surfaced because the telemetry started reporting errors.
        """
        out = []
        for k, slots in self.slab.live.items():
            if k[0] == ch:
                out.extend(slots)
        return out

    def limit(self, x):
        """Soft knee above `thresh`, straight through below it.

        Stateless and per-sample, so it needs no lookahead and cannot pump; what
        it costs is a little rounding of the loudest transients, which on drum
        peaks is far preferable to the hard clip that synth_window would
        otherwise apply. Below the threshold the signal is untouched.
        """
        t = self.thresh
        a = np.abs(x)
        over = a > t
        if not over.any():
            return x
        y = x.copy()
        y[over] = np.sign(x[over]) * (t + (1.0 - t) * np.tanh((a[over] - t) / (1.0 - t)))
        return y

    # ---- audio --------------------------------------------------------------
    def callback(self, in_data, frame_count, time_info, status):
        import pyaudio
        if status:
            self.underruns += 1
        # PortAudio hands us its own clock plus the time this block will actually
        # reach the DAC. Pin that to time.monotonic once per block so a MIDI
        # arrival timestamp can be compared with when its sound leaves.
        if time_info:
            self._dac = time_info.get("output_buffer_dac_time", 0.0)
            self._cur = time_info.get("current_time", 0.0)
            self._wall = time.monotonic()
        n0 = self.n
        try:
            self.apply(n0)
            self.sweep(n0)
            self.slab.reap(n0)
            L, R = B.synth_window(self.slab.prep(), n0, frame_count)
        except Exception as e:
            # Last line of defence: emit silence for this block rather than let
            # the exception propagate, which PortAudio answers by stopping.
            self.errors += 1
            self.last_error = "%s: %s" % (type(e).__name__, e)
            L = R = np.zeros(frame_count, np.float32)
        self.n = n0 + frame_count
        L, R = self.limit(L), self.limit(R)
        p = float(max(np.abs(L).max(), np.abs(R).max()))
        if p > self.peak:
            self.peak = p
        st = np.empty(frame_count * 2, np.float32)
        st[0::2] = L; st[1::2] = R
        return (st.tobytes(), pyaudio.paContinue)


def selftest():
    """Assert the live engine's behaviour without any audio or MIDI hardware.

    Written after breaking the same area twice: generalising the stuck-note sweep
    to every voice while leaving the key-down bookkeeping in the organ branch, so
    every piano note was swept a block after it started. Both failures -- notes
    that never stop and notes that stop instantly -- come from the same pair of
    invariants, so both are asserted here rather than left to be noticed.
    """
    import random
    fails = []

    def check(name, ok, detail=""):
        print("   %-46s %s%s" % (name, "ok" if ok else "FAIL", detail))
        if not ok:
            fails.append(name)

    for prog, drums, label in ((0, False, "piano"), (56, False, "trumpet"),
                               (19, False, "organ"), (0, True, "drums")):
        lv = Live(program=prog, rate=48000, frames=128, drums=drums, verbose=False)
        note = 38 if drums else 60

        # 1. a held note keeps sounding
        lv.on_midi(mido.Message("note_on", channel=0, note=note, velocity=100))
        n = 0
        for _ in range(int(1.5 * 48000) // 128):
            lv.callback(None, 128, None, 0); n += 128
        check("%s: held note still sounds after 1.5 s" % label,
              sum(len(v) for v in lv.slab.live.values()) > 0 or drums)

        # 2. note-off releases it (a struck drum ignores note-off by design)
        lv.on_midi(mido.Message("note_off", channel=0, note=note, velocity=0))
        lv.apply(n); lv.sweep(n)
        held = sum(len(v) for v in lv.slab.live.values())
        if drums:
            # A struck drum rings on regardless of the key. The precise question
            # is not "is it still audible" -- after 1.5 s a snare has decayed on
            # its own -- but "did note-off CHANGE anything". So render the same
            # strike twice, once with a note-off and once without, and require
            # them to be identical.
            def strike(send_off):
                l2 = Live(program=prog, rate=48000, frames=128, drums=True, verbose=False)
                l2.on_midi(mido.Message("note_on", channel=0, note=note, velocity=100))
                buf = []
                for i in range(int(1.2 * 48000) // 128):
                    if send_off and i == 40:
                        l2.on_midi(mido.Message("note_off", channel=0, note=note, velocity=0))
                    b, _f = l2.callback(None, 128, None, 0)
                    buf.append(np.frombuffer(b, np.float32))
                return np.concatenate(buf)
            a, b2 = strike(True), strike(False)
            check("%s: note-off changes nothing (one-shot)" % label,
                  float(np.abs(a - b2).max()) == 0.0)
        else:
            check("%s: note-off releases" % label, held == 0)

        # 3. everything is returned once it has rung out
        for k in range(20000):
            lv.slab.reap(n + k * 128)
        check("%s: all slots returned" % label,
              len(lv.slab.free) == lv.slab.cap,
              "" if len(lv.slab.free) == lv.slab.cap
              else "  (%d leaked)" % (lv.slab.cap - len(lv.slab.free)))

    # 4. the sustain pedal holds, and the sweep does not steal pedalled notes
    lv = Live(program=0, rate=48000, frames=128, verbose=False)
    lv.on_midi(mido.Message("control_change", channel=0, control=64, value=127))
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100)); lv.apply(0)
    lv.on_midi(mido.Message("note_off", channel=0, note=60, velocity=0))
    lv.apply(4800); lv.sweep(4800)
    check("pedal: holds the note after key-up",
          sum(len(v) for v in lv.slab.live.values()) > 0)
    lv.on_midi(mido.Message("control_change", channel=0, control=64, value=0))
    lv.apply(9600); lv.sweep(9600)
    check("pedal: releases on pedal-up",
          sum(len(v) for v in lv.slab.live.values()) == 0)

    # 5. a lost note-off is healed rather than droning
    lv = Live(program=0, rate=48000, frames=128, verbose=False)
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100)); lv.apply(0)
    lv.down.clear()                       # the note-off never arrived
    lv.sweep(4800)
    check("lost note-off is swept", lv.stuck == 1 and
          sum(len(v) for v in lv.slab.live.values()) == 0)

    # 6. fuzz every mode: no errors, no leaks
    for prog, drums, label in ((0, False, "piano"), (19, False, "organ"), (0, True, "drums")):
        lv = Live(program=prog, rate=48000, frames=128, drums=drums, verbose=False)
        random.seed(5); down = set(); n = 0
        notes = [38, 42, 46, 49] if drums else [48, 55, 60, 64]
        for _ in range(2500):
            n += 128; r = random.random()
            if r < 0.30:
                v = random.choice(notes)
                lv.on_midi(mido.Message("note_on", channel=0, note=v, velocity=random.randint(1, 127)))
                down.add(v)
            elif r < 0.55 and down:
                v = random.choice(sorted(down))
                lv.on_midi(mido.Message("note_off", channel=0, note=v, velocity=0)); down.discard(v)
            elif r < 0.62 and down:
                down.discard(random.choice(sorted(down)))          # a lost note-off
            elif r < 0.75:
                lv.on_midi(mido.Message("control_change", channel=0, control=1, value=random.randint(0, 127)))
            elif r < 0.85:
                lv.on_midi(mido.Message("pitchwheel", channel=0, pitch=random.randint(-8192, 8191)))
            else:
                lv.on_midi(mido.Message("aftertouch", channel=0, value=random.randint(0, 127)))
            lv.apply(n)
            lv.down &= {(0, x) for x in down}
            lv.sweep(n); lv.slab.reap(n)
        for v in sorted(down):
            lv.on_midi(mido.Message("note_off", channel=0, note=v, velocity=0))
        lv.apply(n); lv.down.clear(); lv.sweep(n)
        for k in range(20000):
            lv.slab.reap(n + k * 128)
        check("%s: 2500 mixed events, no errors" % label, lv.errors == 0,
              "" if lv.errors == 0 else "  (%s)" % lv.last_error)
        check("%s: 2500 mixed events, no leak" % label,
              len(lv.slab.free) == lv.slab.cap,
              "" if len(lv.slab.free) == lv.slab.cap
              else "  (%d leaked)" % (lv.slab.cap - len(lv.slab.free)))

    print("\n  %s" % ("all passed" if not fails else "FAILED: %s" % ", ".join(fails)))
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", type=int, default=56, help="GM program (default 56, trumpet)")
    ap.add_argument("--port", default=None, help="substring of the MIDI input port name")
    ap.add_argument("--rate", type=int, default=48000)
    ap.add_argument("--frames", type=int, default=128,
                help="audio block; also becomes the kernel control block (see docstring)")
    ap.add_argument("--tuner", default="hybrid")
    ap.add_argument("--drums", action="store_true", help="GM percussion: notes are drums, not pitches")
    ap.add_argument("--headroom", type=float, default=4.0, help="dB of headroom (live cannot normalise)")
    ap.add_argument("--list", action="store_true", help="list MIDI inputs and exit")
    ap.add_argument("--selftest", action="store_true", help="run the behaviour checks and exit")
    ap.add_argument("--latency", action="store_true", help="measure MIDI-to-DAC latency while you play")
    a = ap.parse_args()

    if a.selftest:
        sys.exit(selftest())

    names = mido.get_input_names()
    if a.list:
        for n in names:
            print(" ", n)
        return
    if not names:
        sys.exit("no MIDI inputs found (is the keyboard plugged in?)")
    name = next((n for n in names if a.port and a.port.lower() in n.lower()), names[0])

    import pyaudio
    live = Live(program=a.program, rate=a.rate, frames=a.frames, tuner=a.tuner, drums=a.drums,
                headroom_db=a.headroom)
    if a.drums:
        sys.stderr.write("  GM percussion at %d Hz, %d-frame blocks\n" % (a.rate, a.frames))
    else:
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
    live.measure = a.latency
    if a.latency:
        li = stream.get_output_latency()
        sys.stderr.write("  PortAudio reports %.2f ms output latency; play some notes\n"
                         % (li * 1000.0))
    stream.start_stream()
    last = time.monotonic()
    try:
        while stream.is_active() and not stop.is_set():
            time.sleep(0.2)
            if time.monotonic() - last >= 5.0:
                last = time.monotonic()
                sounding = sum(len(v) for v in live.slab.live.values())
                sys.stderr.write("    %5.1f s  peak %.3f  sounding %4d  free %5d  "
                                 "under %d  drop %d  err %d  stuck %d%s\n"
                                 % (live.n / live.rate, live.peak, sounding,
                                    len(live.slab.free), live.underruns, live.dropped,
                                    live.errors, live.stuck,
                                    ("  last: " + live.last_error) if live.last_error else ""))
                sys.stderr.flush()
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream(); stream.close(); pa.terminate(); port.close()
        sys.stderr.write("\n  peak %.3f  underruns %d  dropped %d  errors %d  stuck %d\n"
                         % (live.peak, live.underruns, live.dropped, live.errors, live.stuck))
        if live.lat:
            def stat(vals):
                v = sorted(x * 1000.0 for x in vals)
                return (v[len(v) // 2], v[0], v[-1])
            tot = stat([a + b for a, b in live.lat])
            inq = stat([a for a, _ in live.lat])
            buf = stat([b for _, b in live.lat])
            sys.stderr.write("  MIDI-to-DAC over %d notes:\n" % len(live.lat))
            sys.stderr.write("    midi in + queue  median %5.1f ms  (%.1f - %.1f)\n" % inq)
            sys.stderr.write("    audio buffer     median %5.1f ms  (%.1f - %.1f)\n" % buf)
            sys.stderr.write("    TOTAL            median %5.1f ms  (%.1f - %.1f)\n" % tot)
        if live.last_error:
            sys.stderr.write("  last error: %s\n" % live.last_error)


if __name__ == "__main__":
    main()
