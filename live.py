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

THE ENGINE IS MULTI-TIMBRAL. A `Part` is one patch listening on one channel over
one range of keys, so patches layer (two parts over the same keys) and split
(two parts over different keys). The expensive half of a part -- its templates --
lives in a `Bank` keyed by (program, drums, tuner) and shared between parts that
want the same patch, so a layer of two trumpets builds one bank.

NOTHING BUILDS ON THE AUDIO THREAD. `Bank.get()` is a pure dict lookup and
returns None on a miss; every build goes through `Bank.warm()` on another
thread. See the GIL note in `main()` for why that is not free either.

BLOCK ALIGNMENT MATTERS. The kernel is window-independent only when the window is
a multiple of BLK. Its amplitude envelope is interpolated across the FULL block
and so does not care, but the tension-bend / mode-lock pitch transient computes
its phase from the CLIPPED window start, so a window that splits a block gets a
different transient. Measured against a single-window render of one trumpet note:
512-frame windows at BLK=512 agree to 3.9e-08, but 256-frame windows are off by
1.1e-03, all of it inside the attack where the mode lock lives. So the callback
size and BLK are set equal here. BLK=128 also buys a 2.7 ms control quantum
instead of 10.7 ms, which is what keeps a struck attack from smearing.

Usage:  live.py [--tui] [--program N] [--port SUBSTRING] [--rate HZ] [--frames N]
"""
import sys, os, time, threading, argparse, collections, signal, itertools
import random as _random

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
# p0 is the LEFT ear's carrier phase and p0R the RIGHT one: the interaural
# delay is folded into the phase anchor, p0 = -om*(non + d) + ph0, so an ear
# really does receive the partial late rather than merely receiving its envelope
# late. See blockrender.emit_partial.
COLS_F8 = ("om", "p0", "p0R")
COLS_F4 = ("aL", "aR", "nf", "fa", "re", "ch", "logr", "logrA", "aft", "sus",
           "cv", "cc", "crl", "sj", "csc", "tbav", "tau", "tcut",
           "vd", "vr", "vp", "delL", "delR")
COLS_I8 = ("non", "noff")
COLS_I4 = ("gr", "cr", "pl")
ALL_COLS = COLS_F8 + COLS_F4 + COLS_I8 + COLS_I4

IDLE = 1 << 62          # a note-on so far in the future the partial never sounds

MELODIC_RANGE = (21, 96)        # a keyboard
DRUM_RANGE = (35, 81)           # the GM kit


class Slab:
    """The live partial table: fixed capacity, slots handed out per note.

    Keys are opaque to the slab. Live uses a UNIFORM 4-tuple,
    (part_id, channel, note, rank_or_None) -- see Live._sounding for why the
    shape is not allowed to vary.
    """

    def __init__(self, capacity=16384):
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
        # `busy` is the occupancy map, and it stays true through the release
        # tail -- a slot is only cleared by reap(), once it has finished
        # ringing. So it is exactly "might still make sound", which is what the
        # renderer needs to know to split the table or to stop walking it.
        self.dirty = True               # occupancy changed: recompute the split
        self.live = {}                  # key -> [slot indices]
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
        # The mod wheel DEEPENS a section's vibrato, it does not replace it.
        # vbase is the vibrato this partial was built with -- the player's own,
        # from voice_vibrato -- and vsc is that player's depth relative to their
        # section's mean, so the wheel adds in proportion and the spread between
        # players survives. Same shape as aL0/aR0 for aftertouch: recompute from
        # a baseline, never scale what is already there.
        self.vbase = np.zeros(capacity, np.float32)
        self.vsc = np.ones(capacity, np.float32)
        # ...and the rate, which the wheel scales rather than sets: a player
        # leaning into a vibrato widens AND quickens it, and the spread of rates
        # across the section has to survive that or seven players end up beating
        # at one speed again.
        self.vrbase = np.ones(capacity, np.float32) * 5.5
        # Entry scatter is REDRAWN ON EVERY PRESS, which is the half of it the
        # offline path cannot do: there the offsets are hashed off the pitch, so
        # one pitch always scatters the same way (the reference renderer has no
        # nominal note onset to key on -- its hammer_down is handed the moment
        # each PARTIAL was struck). Live has a press, so repeated punches on one
        # note land differently every time, which is what a section does.
        self._rng = _random.Random(0x5CA7)
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
        self.dirty = True
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
        # Each player enters at their own instant, drawn fresh for this press.
        # The template carries the offline scatter in its own `non`; that is
        # discarded rather than added to.
        scat = tmpl.get("scatter_ms", 0.0)
        if scat and n:
            pl = tmpl["pl"]
            offs = np.array([self._rng.random() * scat * 0.001 * self.rate
                             for _ in range(int(pl.max()) + 1)])
            newnon = (n0 + offs[pl]).astype(np.int64)
        else:
            newnon = n0
        # p0 = -om*(non + ear delay) + ph0, so moving the onset moves the phase
        # anchor with it. Written against the template's OWN onsets, which makes
        # it correct whether or not they differ from each other.
        a["p0"][idx] = tmpl["p0"] + tmpl["om"] * (tmpl["non"] - newnon)
        a["p0R"][idx] = tmpl["p0R"] + tmpl["om"] * (tmpl["non"] - newnon)
        a["non"][idx] = newnon
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
        self.vbase[idx] = tmpl["vd"]
        self.vrbase[idx] = tmpl["vr"]
        # Relative to this note's own mean, so a wheel of N cents means N cents
        # of ADDED depth on an average player. A one-body voice has no spread
        # (and often no vibrato at all), so it falls back to 1.0 and the wheel
        # behaves exactly as it always did.
        mv = float(np.mean(tmpl["vd"])) if n else 0.0
        self.vsc[idx] = (tmpl["vd"] / mv) if mv > 1e-12 else 1.0
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

    def retune(self, slots, n, om_scale=None, vd=None, vrs=None):
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
        vr0 = np.maximum(a["vr"][idx].astype(np.float64), 1e-6)
        vp = a["vp"][idx].astype(np.float64)
        ton = a["non"][idx].astype(np.float64) / self.rate
        tn = n / self.rate

        # The RATE is inside the accumulated extra phase too, not only the depth
        # -- the kernel's term is (f*d/r)*(cos(2*pi*r*ton + p) - cos(2*pi*r*t + p))
        # -- so a rate change has to be evaluated on both sides of the swap or it
        # steps the phase and clicks. Hence r as an argument rather than a
        # closure over one value.
        def extra(om, vd, r, ph):
            w2 = 2.0 * np.pi * r
            swing = np.cos(w2 * ton + ph) - np.cos(w2 * tn + ph)
            return (om * self.rate / (2.0 * np.pi)) * vd / r * swing

        vr1 = (np.maximum(self.vrbase[idx].astype(np.float64) * float(vrs), 1e-6)
               if vrs is not None else vr0)
        # THE VIBRATO'S OWN PHASE HAS TO SURVIVE A RATE CHANGE TOO. Its argument
        # is 2*pi*r*t + vp in ABSOLUTE time, so moving r moves that argument by
        # 2*pi*(r1-r0)*t -- and t is time since the note began, so the jump GROWS
        # the longer the note is held: 0.35 rad for one MIDI step on a 5 s note,
        # 44 rad (7 cycles) for a full sweep. Correcting only the carrier left
        # every partial of every player lurching at the same instant, which is a
        # shared, correlated event in an ensemble built entirely on not having
        # any. Ben heard it before I had a test for it.
        #
        # Rotate vp so the LFO simply changes speed and carries on from where it
        # was: 2*pi*r1*tn + vp1 == 2*pi*r0*tn + vp.
        vp1 = vp + 2.0 * np.pi * (vr0 - vr1) * tn if vrs is not None else vp
        before = extra(om0, vd0, vr0, vp)
        om1 = om0 * om_scale if om_scale is not None else om0
        vd1 = ((self.vbase[idx].astype(np.float64)
                + float(vd) * self.vsc[idx].astype(np.float64))
               if vd is not None else vd0)
        after = extra(om1, vd1, vr1, vp1)
        # Both ears take the SAME increment. The interaural delay lives inside
        # each anchor already (p0 = -om*(non+d) + ph0), and continuity only asks
        # that p0 + om*n be unbroken, so the difference between the ears carries
        # through untouched -- the note bends without moving in the room.
        step = (om0 - om1) * n - (after - before)
        a["p0"][idx] += step
        a["p0R"][idx] += step
        if om_scale is not None:
            a["om"][idx] = om1
        if vd is not None:
            a["vd"][idx] = vd1
        if vrs is not None:
            a["vr"][idx] = vr1
            a["vp"][idx] = vp1

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
                if len(live):
                    self.busy[live] = False
                    self.dirty = True
                self.free.extend(int(i) for i in live)
            else:
                keep.append((idx, off))
        self.retiring = keep


# Below this many occupied slots, waking threads costs more than it saves.
# Measured, not guessed -- see Renderer.crossover() and the README table.
PARALLEL_MIN = 700


class Renderer:
    """Render one block, optionally splitting the partial table across threads.

    Partials are independent and the kernel ACCUMULATES into its output buffers,
    so N threads can each take a slice of the table and the results add. ctypes
    releases the GIL for the duration of the call, so this really is parallel
    even though it is driven from Python.

    Why it is worth doing: the chiff is a per-sample random phase on every
    partial -- a hash plus a sincosf, inside the sample loop -- and it runs for
    the whole attack. A six-note string chord costs 2.5 ms a block while the
    chiff is speaking against a 2.67 ms budget, and 0.85 ms after it stops. The
    voices where that bites are the ones where the noise IS the sound: snare
    3.0, brass 2.6, breath and seashore 2.4, flue organ 1.3.

    Why the kernel's own OpenMP does not do it: that parallelises over TIME
    chunks, and synth_window passes CHUNK = SR, so a 128-frame block is a single
    chunk and every core but one sits idle.

    THE SPLIT MUST FOLLOW THE OCCUPANCY, not the capacity. Slots are handed out
    from the front of the free list, so an even split of [0, capacity) gave
    thread 0 every active partial and measured SLOWER than one thread. Splitting
    by equal counts of occupied slots gives 2.30 -> 1.28 ms on 3 threads.

    Splitting changes the ORDER of a float sum, so the output differs from the
    single-threaded path in its last bits (measured 2e-6 relative, -114 dB).
    Offline rendering never comes through here.
    """

    def __init__(self, slab, frames, nthreads=1):
        self.slab = slab
        self.frames = frames
        self.K = max(1, int(nthreads))
        self.n0 = 0
        self.act = 0
        self._b = None
        self.stop = False
        self.error = None
        self.L = np.zeros(frames, np.float32)
        self.R = np.zeros(frames, np.float32)
        self.bufs = [(np.zeros(frames, np.float32), np.zeros(frames, np.float32))
                     for _ in range(self.K)]
        self.go = [threading.Event() for _ in range(self.K)]
        self.done = [threading.Event() for _ in range(self.K)]
        self.threads = []
        for k in range(1, self.K):          # worker 0 is the calling thread
            t = threading.Thread(target=self._work, args=(k,), daemon=True)
            t.start()
            self.threads.append(t)

    def close(self):
        self.stop = True
        for e in self.go:
            e.set()

    def bounds(self):
        """Split points with an equal number of OCCUPIED slots in each range,
        recomputed only when occupancy has changed."""
        sl = self.slab
        if sl.dirty:
            act = np.flatnonzero(sl.busy)
            self.act = len(act)
            if self.act == 0:
                self._b = None
            else:
                hi = int(act[-1]) + 1
                K = self.K
                self._b = ([0] + [int(act[self.act * k // K]) for k in range(1, K)]
                           + [hi])
            sl.dirty = False
        return self._b

    def _work(self, k):
        while True:
            self.go[k].wait(); self.go[k].clear()
            if self.stop:
                return
            try:
                L, R = self.bufs[k]
                L[:] = 0.0; R[:] = 0.0
                b = self._b
                B.synth_partials(self.slab.prep(), self.n0, self.frames,
                                 b[k], b[k + 1], L, R)
            except Exception as e:
                self.error = "%s: %s" % (type(e).__name__, e)
            finally:
                self.done[k].set()

    def render(self, n0, frames):
        b = self.bounds()
        L, R = self.L, self.R
        L[:] = 0.0; R[:] = 0.0
        if b is None:                       # nothing occupied: silence, cheaply
            return L, R
        if self.K == 1 or self.act < PARALLEL_MIN or frames != self.frames:
            # One call over [0, hi). Slots past the high-water mark are idle and
            # contribute exactly zero, so stopping there is bit-identical.
            B.synth_partials(self.slab.prep(), n0, frames, 0, b[-1], L, R)
        else:
            self.n0 = n0
            for k in range(1, self.K):
                self.go[k].set()
            B.synth_partials(self.slab.prep(), n0, frames, b[0], b[1], L, R)
            for k in range(1, self.K):
                self.done[k].wait(); self.done[k].clear()
                L += self.bufs[k][0]; R += self.bufs[k][1]
        L *= T.master_gain; R *= T.master_gain
        np.clip(L, -1, 1, L); np.clip(R, -1, 1, R)
        return L, R


# ---- banks: the expensive, shareable half of a patch ------------------------

_BANKS = collections.OrderedDict()   # (program, drums, tuner) -> Bank
_BANK_PARTIAL_CAP = 400000           # ~50 MB of templates; piano alone is 125k
_BANK_LOCK = threading.RLock()


class Bank:
    """Every template for one patch: (program, drums, tuner).

    Shared by every Part that wants that patch, so layering two trumpets builds
    one bank. Effectively immutable once warmed, which is what makes it safe to
    hand to the audio thread by a single attribute assignment.
    """

    def __init__(self, program, drums, tuner):
        self.program, self.drums, self.tuner = program, drums, tuner
        pc = None if drums else __import__("patch_map").property_class_for_program(program)
        self.cls_name = "GM percussion" if drums else pc.__name__
        self.organ = (not drums) and getattr(pc, "registerable", False)
        self.rank_names = [r[0] for r in getattr(pc, "stop_ranks", [])] if pc else []
        # The order a crescendo pedal adds them in, which is the organ's own idea
        # of how a registration should grow.
        self.cres_order = list(getattr(pc, "crescendo_order", self.rank_names)) if pc else []
        self.templates = {}
        self.partials = 0
        self.warmed = False
        # Measured, not assumed: 8 bands if this voice's timbre moves with
        # velocity, 1 if velocity is pure gain. See _vel_dependent().
        self.nbuckets = 1 if drums else (8 if self._vel_dependent() else 1)
        self.range = DRUM_RANGE if drums else MELODIC_RANGE

    # ---- template construction (NEVER on the audio thread) ------------------
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

    def _voice_class(self, note):
        """The property class this note will actually be rendered with.

        Per NOTE, not per program: an ensemble patch routes each note to the
        instrument whose register it is in, so one_shot and section_onset_ms have
        to be read off the class that note actually got. Asking by program gave a
        routed brass section the un-sectioned trombone and silently lost its
        entry scatter.
        """
        if self.drums:
            got = percussion_for_note(note)
            return got[1] if got else None
        return __import__("patch_map").property_class_for_note(self.program, note)

    def _raw_template(self, note, vel):
        """Build one note at one velocity. Costs 1.4-10 ms: off-thread only."""
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
        t = {k: np.array(p[k]) for k in ALL_COLS}
        t["P"] = p["P"]
        nf = t["nf"].astype(np.float64)
        # An unmapped drum note builds NOTHING: percussion_for_note has no
        # voice for it and prepare() emits no partials. A zero-partial
        # template is legal, not an error, and must not reach nf.min().
        t["hrel"] = ((nf / max(nf.min(), 1e-9)).astype(np.float32)
                     if len(nf) else np.zeros(0, np.float32))
        # A one-shot voice's length is its own decay, decided at build time.
        # Live, that means note-off must NOT truncate it -- see stamp/release.
        # ONE-SHOT IS A PROPERTY OF THE VOICE, not of drum mode. A celesta,
        # glockenspiel, marimba, vibraphone, tubular bell, timpano or wood
        # block is struck: it rings out its own decay and note-off means
        # nothing to it, exactly as a snare does. Deciding this from
        # `self.drums` cut every melodic struck voice at key-up -- and their
        # release time is 0.1 ms, because offline the note is extended to 8 s
        # and the release is never used, so the value was only ever the
        # floor. Cutting a ringing bar in 0.1 ms is a click.
        t["oneshot"] = bool(t["P"]) and getattr(self._voice_class(note),
                                                "one_shot", False)
        t["dur"] = int(t["noff"][0] - t["non"][0]) if t["P"] else 0
        t["scatter_ms"] = getattr(self._voice_class(note), "section_onset_ms", 0.0) or 0.0
        t["ranks"] = {}
        if self.organ:
            # gr is the rank index the offline gate would have used, so it is
            # exactly the label needed to slice this template per stop.
            gr = t["gr"]
            for i, nm in enumerate(self.rank_names):
                msk = gr == i
                if not msk.any():
                    continue
                cols = {k: t[k][msk] for k in ALL_COLS}
                t["ranks"][nm] = (cols, int(msk.sum()), t["hrel"][msk])
        t["vel"] = vel
        return t

    def warm(self, progress=None):
        """Build every template for the playable range. Off-thread only."""
        if self.warmed:
            return self
        lo, hi = self.range
        done = 0
        total = (hi - lo + 1) * self.nbuckets
        for note in range(lo, hi + 1):
            for b in range(self.nbuckets):
                if (note, b) not in self.templates:
                    try:
                        t = self._raw_template(note, self.bucket_vel(b))
                    except Exception:
                        t = None         # unmapped drum note: nothing to build
                    if t is not None:
                        self.templates[(note, b)] = t
                        self.partials += t["P"]
                done += 1
                if progress and (done & 15) == 0:
                    progress(self, done / float(total))
        self.warmed = True
        if progress:
            progress(self, 1.0)
        return self

    # ---- lookup (the audio thread's only entry point) -----------------------
    def get(self, note, vel):
        """Pure lookup. A miss returns None and is NEVER a build: building here
        costs 1.4-10 ms, which is more than a whole 2.7 ms block."""
        return self.templates.get((note, self.bucket(vel)))


def bank_for(program, drums, tuner, progress=None):
    """The warmed Bank for one patch, built if it is not already cached.

    BLOCKS while it builds -- callers must not be the audio thread. Serialised,
    because blockrender.prepare() reseeds the global RNG and two concurrent
    builds would race on it.
    """
    key = (int(program), bool(drums), str(tuner))
    with _BANK_LOCK:
        got = _BANKS.get(key)
        if got is None:
            got = Bank(key[0], key[1], key[2])
            _BANKS[key] = got
        got.warm(progress)
        _BANKS.move_to_end(key)
        # LRU by partial count: piano is 125k partials (~16 MB) on its own.
        while (len(_BANKS) > 1
               and sum(b.partials for b in _BANKS.values()) > _BANK_PARTIAL_CAP):
            _BANKS.popitem(last=False)
        return got


# ---- parts: the cheap, per-assignment half ---------------------------------

_PART_IDS = itertools.count(1)


class Part:
    """One patch assignment: a Bank, listening on a channel over a key range.

    Two parts over the same keys is a LAYER; two over different keys is a SPLIT.
    Everything here is cheap to change; everything expensive is in the Bank.
    """

    def __init__(self, bank, channel=None, lo=0, hi=127, transpose=0, level_db=0.0):
        self.pid = next(_PART_IDS)
        self.bank = bank
        self.channel = channel          # None = listen on every channel
        self.lo, self.hi = lo, hi
        self.transpose = transpose
        self.level_db = level_db
        self.muted = False
        # Which stops are out, per part: two organ layers can differ.
        self.drawn = set(bank.cres_order[:1])   # start on the 8' foundation
        self.cres = 0.0

    # a Part delegates its patch identity to its bank
    program = property(lambda self: self.bank.program)
    drums = property(lambda self: self.bank.drums)
    organ = property(lambda self: self.bank.organ)
    tuner = property(lambda self: self.bank.tuner)

    def matches(self, ch, note):
        return ((self.channel is None or self.channel == ch)
                and self.lo <= note <= self.hi and not self.muted)

    def gain(self):
        return 10.0 ** (self.level_db / 20.0)

    def label(self):
        if self.drums:
            return "-- drum kit"
        return "%d %s" % (self.program, self.bank.cls_name)

    def to_dict(self):
        return dict(program=self.program, drums=self.drums, tuner=self.tuner,
                    channel=self.channel, lo=self.lo, hi=self.hi,
                    transpose=self.transpose, level_db=self.level_db,
                    muted=self.muted, drawn=sorted(self.drawn))

    @staticmethod
    def from_dict(d, progress=None):
        bank = bank_for(d.get("program", 56), d.get("drums", False),
                        d.get("tuner", "hybrid"), progress)
        p = Part(bank, d.get("channel"), d.get("lo", 0), d.get("hi", 127),
                 d.get("transpose", 0), d.get("level_db", 0.0))
        p.muted = bool(d.get("muted", False))
        if d.get("drawn"):
            p.drawn = {r for r in d["drawn"] if r in bank.rank_names}
        return p


class Live:
    def __init__(self, program=56, rate=48000, frames=128, capacity=16384,
                 tuner="hybrid", verbose=True, drums=False, headroom_db=4.0,
                 parts=None, threads=1):
        B.set_sample_rate(rate)
        B.BLK = frames          # see BLOCK ALIGNMENT in the module docstring
        self.rate, self.frames, self.tuner = rate, frames, tuner
        self.verbose = verbose
        self.slab = Slab(capacity)
        self.slab.lib = B.ensure_lib()
        self.slab.rate = float(rate)
        self.headroom_db = headroom_db
        self.slab.headroom = 10.0 ** (-headroom_db / 20.0)
        self.renderer = Renderer(self.slab, frames, threads)
        # The part set is swapped WHOLESALE by a single attribute assignment,
        # which is atomic under the GIL: the callback sees the old tuple or the
        # new one, never a half-built one. See set_parts().
        if parts is None:
            parts = (Part(Bank(program, bool(drums), tuner)),)
        self.parts = tuple(parts)
        # WHICH KEYS ARE DOWN, tracked explicitly. It used to be inferred from
        # what the slab was sounding, which is not the same thing: the crescendo
        # retires ranks OUT of the slab, so a held note could lose every rank it
        # had and vanish from the only record that it was still down.
        self.down = set()
        self.stuck = 0
        self.misses = 0         # templates asked for that were never built
        self.measure = False    # --latency: record MIDI-to-DAC for each note
        self.lat = []
        self._dac = self._cur = self._wall = 0.0
        self.pedal = {}         # channel -> sustain pedal down
        self.pedalled = set()   # keys whose damper the pedal is holding off
        self.n = 0                       # absolute sample clock
        self.events = collections.deque()
        self.lock = threading.Lock()
        self.bend = {}          # channel -> current pitch-bend ratio
        self.mod = {}           # channel -> current vibrato depth (fraction)
        self.pressure = {}      # channel -> aftertouch 0..1
        self.bend_range = 2.0   # semitones at full wheel, the GM convention
        self.mod_cents = 35.0   # cents of vibrato at full mod wheel
        # ...and how much FASTER it gets there. Depth and rate move together on
        # a real instrument: leaning into a vibrato widens and quickens it at
        # once, and a wheel that only widens reads as a effect rather than a
        # player. Proportional, so the section's spread of rates survives --
        # 4.8-6.3 Hz at rest becomes 6.0-7.9 at full, which is where an intense
        # string vibrato actually sits.
        self.mod_rate = 0.25    # +25% rate at full wheel
        self.modw = {}          # channel -> wheel position 0..1
        self.cc1_count = 0      # how many mod-wheel messages have arrived
        self.cc1_last = -1      # and the last value, so a monitor can see them
        self.thresh = 0.70      # soft-limiter knee; see Live.limit
        self.press_db = 8.0     # crescendo at full aftertouch
        self.press_tilt = 0.30  # and it brightens as it swells: see Slab.press
        self.underruns = 0
        self.dropped = 0
        self.errors = 0
        self.last_error = None
        self.peak = 0.0
        self.last_peak = 0.0
        self.render_ms = 0.0    # last block's kernel time, against the budget
        self.render_max = 0.0
        self.blocks = 0

    # ---- parts --------------------------------------------------------------
    def set_parts(self, parts):
        """Swap the part set. Call from the TUI/builder thread, never the audio
        one -- but the swap itself is a single atomic assignment, so the callback
        never sees a partial list. Notes belonging to parts that are going away
        are released; notes on parts that survive keep sounding."""
        keep = {p.pid for p in parts}
        n0 = self.n
        for k in [k for k in list(self.slab.live) if k[0] not in keep]:
            self.slab.oneshot.pop(k, None)
            self.slab.release(k, n0)
        self.parts = tuple(parts)

    def warm(self, progress=None):
        """Build every part's bank. Off-thread; blocks."""
        t0 = time.time()
        for p in self.parts:
            p.bank.warm(progress)
        if self.verbose:
            tot = sum(p.bank.partials for p in self.parts)
            nt = sum(len(p.bank.templates) for p in self.parts)
            sys.stderr.write("  %d templates, %d partials, %.2f s\n"
                             % (nt, tot, time.time() - t0))

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
        parts = self.parts
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
            self.slab.press(self._sounding(ch, note=msg.note),
                            msg.value / 127.0, self.press_db, self.press_tilt)
        elif msg.type == "control_change":
            if msg.control == 1:
                self.cc1_count += 1; self.cc1_last = msg.value
                # THE MOD WHEEL IS A CRESCENDO PEDAL on an organ part and
                # VIBRATO on everything else, and with layers it can be both at
                # once -- so each part is asked separately rather than the whole
                # channel taking one branch.
                organs = [p for p in parts if p.organ and self._listens(p, ch)]
                others = [p for p in parts if not p.organ and self._listens(p, ch)]
                for part in organs:
                    self._crescendo(part, ch, msg.value, n0)
                if others:
                    # THE MOD WHEEL IS VIBRATO. That is what it is for on a wind
                    # or string patch, and it is the one control every library
                    # agrees on after dynamics. The machinery already exists --
                    # it is the per-player vibrato built for the string sections
                    # -- so here it is simply driven by hand instead of by seed.
                    w = msg.value / 127.0
                    depth = (2.0 ** (self.mod_cents * w / 1200.0)) - 1.0
                    self.mod[ch] = depth
                    self.modw[ch] = w
                    self.slab.retune(self._sounding(ch, pids={p.pid for p in others}),
                                     n0, vd=depth, vrs=1.0 + self.mod_rate * w)
            elif msg.control == 64:                 # sustain pedal
                downp = msg.value >= 64
                was = self.pedal.get(ch, False)
                self.pedal[ch] = downp
                if was and not downp:
                    # Pedal up: every damper falls at once.
                    gone = {k for k in self.pedalled if k[0] == ch}
                    for k in [k for k in list(self.slab.live) if (k[1], k[2]) in gone]:
                        self.slab.release(k, n0)
                    self.pedalled -= gone
            elif msg.control == 123:                # all notes off
                self.down = {k for k in self.down if k[0] != ch}
                self.pedalled = {k for k in self.pedalled if k[0] != ch}
                self.pedal[ch] = False
                for k in [k for k in list(self.slab.live) if k[1] == ch]:
                    self.slab.oneshot.pop(k, None)
                    self.slab.release(k, n0)
        elif msg.type == "note_on" and msg.velocity > 0:
            # Every voice records the key as down, not just the organ. The
            # stuck-note sweep releases whatever is sounding without a key behind
            # it, so a voice that never registered its key had every note swept
            # a block after it started -- notes dying in a fraction of a second.
            self.down.add((ch, msg.note))
            for part in parts:
                if part.matches(ch, msg.note):
                    self._note_on(part, ch, msg.note, msg.velocity, n0)
        else:
            self.down.discard((ch, msg.note))
            pedalled = False
            for part in parts:
                if not part.matches(ch, msg.note):
                    continue
                if self.pedal.get(ch, False) and not part.organ:
                    # The key is up but the damper is not: the string keeps
                    # ringing until the pedal is lifted. Recorded so the
                    # stuck-note sweep does not mistake it for a lost note-off.
                    # An organ has no dampers, so a pedalled organ layer still
                    # stops when the key does.
                    pedalled = True
                    continue
                self._note_off(part, ch, msg.note, n0)
            if pedalled:
                self.pedalled.add((ch, msg.note))

    def _note_on(self, part, ch, note, vel, n0):
        snote = note + part.transpose
        if not 0 <= snote <= 127:
            return
        tmpl = part.bank.get(snote, vel)
        if tmpl is None:
            # Never build here: that is 1.4-10 ms on the audio thread. Silence,
            # counted, and the builder thread is what fixes it.
            self.misses += 1
            return
        # Timbre is quantised to the bucket, level is not: trim by the ratio
        # of the actual velocity to the one the bucket was built at.
        scale = ((vel / 127.0) ** 2 /
                 max((tmpl.get("vel", 127) / 127.0) ** 2, 1e-9)) * part.gain()
        if part.organ:
            # A pipe organ has no touch: a key is open or shut, and the wind
            # does the rest. Velocity is deliberately ignored.
            for rank in part.drawn:
                self._draw(part, tmpl, ch, note, rank, n0)
            return
        key = (part.pid, ch, note, None)
        if not self.slab.stamp(tmpl, key, n0, scale):
            self.dropped += 1
            return                  # slab full: this note does not sound
        # a note started while the wheel is up must join in progress
        slots = self.slab.live.get(key)
        if part.drums:
            # CHOKE, live. Offline this is done by scanning FORWARD for
            # the next strike in the exclusive class and truncating the
            # earlier note to it. Live there is no forward to scan -- but
            # the strike that does the choking is happening right now, so
            # it is simply a note-off written into whatever is ringing.
            grp = choke_group(snote)
            if grp:
                for k in [k for k in list(self.slab.live)
                          if k[0] == part.pid and k[2] != note
                          and (k[2] + part.transpose) in grp]:
                    self.slab.oneshot.pop(k, None)
                    self.slab.release(k, n0)
        pr = self.pressure.get(ch, 0.0)
        if pr:
            self.slab.press(slots, pr, self.press_db, self.press_tilt)
        b, v = self.bend.get(ch, 1.0), self.mod.get(ch, 0.0)
        w = self.modw.get(ch, 0.0)
        if b != 1.0 or v != 0.0 or w != 0.0:
            self.slab.retune(slots, n0, om_scale=(b if b != 1.0 else None),
                             vd=(v if v != 0.0 else None),
                             vrs=(1.0 + self.mod_rate * w) if w != 0.0 else None)

    def _note_off(self, part, ch, note, n0):
        if part.organ:
            for k in [k for k in list(self.slab.live)
                      if k[0] == part.pid and k[1] == ch and k[2] == note]:
                self.slab.release(k, n0)
        else:
            self.slab.release((part.pid, ch, note, None), n0)

    def _crescendo(self, part, ch, value, n0):
        """Rolling the wheel up adds stops in the organ's own crescendo order;
        rolling it down retires them. A stop drawn while keys are held speaks AS
        A FRESH PIPE -- new partials stamped at this instant, with their own
        speech -- which is what actually happens when you pull a stop mid-chord.
        The offline renderer gets this from rank_speak_sec by scanning forward
        through future CC events; live it is simply now."""
        part.cres = value / 127.0
        n = int(part.cres * len(part.bank.cres_order) + 1e-9)
        self.set_stops(part, set(part.bank.cres_order[:max(1, n)]), n0)

    def set_stops(self, part, want, n0=None):
        """Draw and retire ranks to match `want`, on every key already down."""
        if n0 is None:
            n0 = self.n
        want = {r for r in want if r in part.bank.rank_names} or set(part.bank.cres_order[:1])
        for rank in want - part.drawn:
            for (c, note) in self._held_any():
                if part.matches(c, note):
                    t = part.bank.get(note + part.transpose, 127)
                    if t is not None:
                        self._draw(part, t, c, note, rank, n0)
        for rank in part.drawn - want:
            for k in [k for k in list(self.slab.live)
                      if k[0] == part.pid and k[3] == rank]:
                self.slab.release(k, n0)
        part.drawn = set(want)

    def _draw(self, part, tmpl, ch, note, rank, n0):
        got = tmpl.get("ranks", {}).get(rank)
        if not got:
            return
        cols, n, hrel = got
        if not self.slab.stamp_cols(cols, n, (part.pid, ch, note, rank), n0,
                                    part.gain(), hrel, 0, False):
            self.dropped += 1

    def _listens(self, part, ch):
        return (part.channel is None or part.channel == ch) and not part.muted

    def _held_any(self):
        """Every key actually down -- from the key state, not from whatever
        happens to be sounding."""
        return sorted(self.down)

    def sweep(self, n):
        """Release anything sounding whose key is not down.

        A dropped note-off would otherwise drone forever, which is what a long
        session produced: 221 partials held and never freed, with the audio
        thread perfectly healthy underneath. Cheap, and it turns a lost message
        into a note that ends slightly late rather than one that never ends.
        """
        for k in [k for k in list(self.slab.live)
                  if (k[1], k[2]) not in self.down
                  and (k[1], k[2]) not in self.pedalled
                  and not self.slab.oneshot.get(k)]:
            self.slab.release(k, n)
            self.stuck += 1

    def _sounding(self, ch, pids=None, note=None):
        """Every slot sounding on this channel, optionally narrowed to a set of
        parts or to one note.

        Keys are a UNIFORM (part, channel, note, rank) 4-tuple. They did not use
        to be -- a normal voice was a pair and the organ a triple -- and
        _sounding unpacked them as pairs, so pitch bend and aftertouch raised on
        every organ note. The per-message guard caught it, so the audio was fine
        and the controls simply did nothing, which is exactly the kind of failure
        a guard can hide. It only surfaced because the telemetry started
        reporting errors. Indexing a fixed shape cannot fail that way.
        """
        out = []
        for k, slots in self.slab.live.items():
            if k[1] != ch:
                continue
            if pids is not None and k[0] not in pids:
                continue
            if note is not None and k[2] != note:
                continue
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
        t0 = time.perf_counter()
        try:
            self.apply(n0)
            self.sweep(n0)
            self.slab.reap(n0)
            L, R = self.renderer.render(n0, frame_count)
        except Exception as e:
            # Last line of defence: emit silence for this block rather than let
            # the exception propagate, which PortAudio answers by stopping.
            self.errors += 1
            self.last_error = "%s: %s" % (type(e).__name__, e)
            L = R = np.zeros(frame_count, np.float32)
        if self.renderer.error:
            self.errors += 1
            self.last_error, self.renderer.error = self.renderer.error, None
        L, R = self.limit(L), self.limit(R)
        # Layering makes overload reachable, and the drop counter only reports it
        # AFTER notes are already lost. This reports it before.
        self.render_ms = (time.perf_counter() - t0) * 1000.0
        # The first blocks after the stream opens cost several times the steady
        # state -- library warm-up and page faults -- so a max that included them
        # would sit permanently over budget and tell you nothing.
        self.blocks += 1
        if self.blocks > 16 and self.render_ms > self.render_max:
            self.render_max = self.render_ms
        self.n = n0 + frame_count
        p = float(max(np.abs(L).max(), np.abs(R).max()))
        self.last_peak = p          # this block only, so a meter can fall back
        if p > self.peak:
            self.peak = p
        st = np.empty(frame_count * 2, np.float32)
        st[0::2] = L; st[1::2] = R
        return (st.tobytes(), pyaudio.paContinue)

    # ---- telemetry ----------------------------------------------------------
    def wheel_state(self):
        """What the mod wheel is actually doing right now: the last value seen
        per channel, and the vibrato depth/rate the sounding partials carry. Put
        on screen because a wheel that "keeps getting pulled back to 0" is not
        something the offline path can reproduce -- the value has to be watched
        while the hardware is sending."""
        sl = self.slab
        idx = np.flatnonzero(sl.busy)
        if not len(idx):
            return None
        vd = sl.a["vd"][idx].astype(np.float64)
        vr = sl.a["vr"][idx].astype(np.float64)
        cents = np.log2(np.maximum(1.0 + vd, 1e-9)) * 1200.0
        w = max(self.modw.values()) if self.modw else 0.0
        return dict(wheel=w, cents_lo=float(cents.min()), cents_hi=float(cents.max()),
                    rate_lo=float(vr.min()), rate_hi=float(vr.max()),
                    cc1=self.cc1_count, cc1_last=self.cc1_last)

    def stats(self):
        return dict(t=self.n / self.rate, peak=self.peak,
                    last_peak=self.last_peak,
                    sounding=sum(len(v) for v in self.slab.live.values()),
                    used=self.slab.cap - len(self.slab.free), cap=self.slab.cap,
                    free=len(self.slab.free),
                    under=self.underruns, drop=self.dropped, err=self.errors,
                    stuck=self.stuck, miss=self.misses,
                    render_ms=self.render_ms, render_max=self.render_max,
                    threads=self.renderer.K, active=self.renderer.act,
                    budget_ms=self.frames * 1000.0 / self.rate,
                    last_error=self.last_error)


# ---- presets ---------------------------------------------------------------

PRESET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets.json")


def load_presets(path=PRESET_PATH):
    import json
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def preset_from(live):
    return dict(
        parts=[p.to_dict() for p in live.parts],
        master_db=round(20.0 * float(np.log10(max(T.master_gain, 1e-9))), 2),
        headroom_db=live.headroom_db,
        bend_range=live.bend_range, mod_cents=live.mod_cents,
        press_db=live.press_db, press_tilt=live.press_tilt,
        thresh=live.thresh,
    )


def save_preset(name, live, path=PRESET_PATH):
    """Store the whole performance state under `name`. Presets are DATA, not
    code: a voice is still only ever defined in tonelib.py."""
    import json
    d = load_presets(path)
    d[name] = preset_from(live)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)
    return d


def apply_preset(live, preset, progress=None):
    """Rebuild the part set from a preset. BLOCKS while banks build."""
    parts = [Part.from_dict(pd, progress) for pd in preset.get("parts", [])]
    if not parts:
        return
    live.set_parts(parts)
    if "master_db" in preset:
        T.master_gain = 10.0 ** (float(preset["master_db"]) / 20.0)
    for k in ("headroom_db", "bend_range", "mod_cents", "press_db",
              "press_tilt", "thresh"):
        if k in preset:
            setattr(live, k, float(preset[k]))
    live.slab.headroom = 10.0 ** (-live.headroom_db / 20.0)


def selftest():
    import tonelib as _T
    """Assert the live engine's behaviour without any audio or MIDI hardware.

    Written after breaking the same area twice: generalising the stuck-note sweep
    to every voice while leaving the key-down bookkeeping in the organ branch, so
    every piano note was swept a block after it started. Both failures -- notes
    that never stop and notes that stop instantly -- come from the same pair of
    invariants, so both are asserted here rather than left to be noticed.
    """
    import random, tempfile
    fails = []

    def check(name, ok, detail=""):
        print("   %-54s %s%s" % (name, "ok" if ok else "FAIL", detail))
        if not ok:
            fails.append(name)

    def sounding(lv):
        return sum(len(v) for v in lv.slab.live.values())

    def leak(lv, label):
        for k in range(20000):
            lv.slab.reap(lv.n + k * 128)
        n = lv.slab.cap - len(lv.slab.free)
        check(label, n == 0, "" if n == 0 else "  (%d leaked)" % n)

    for prog, drums, label in ((0, False, "piano"), (56, False, "trumpet"),
                               (19, False, "organ"), (0, True, "drums")):
        lv = Live(program=prog, rate=48000, frames=128, drums=drums, verbose=False)
        lv.warm()
        note = 38 if drums else 60

        # 1. a held note keeps sounding
        lv.on_midi(mido.Message("note_on", channel=0, note=note, velocity=100))
        for _ in range(int(1.5 * 48000) // 128):
            lv.callback(None, 128, None, 0)
        n = lv.n
        check("%s: held note still sounds after 1.5 s" % label,
              sounding(lv) > 0 or drums)

        # 2. note-off releases it (a struck drum ignores note-off by design)
        lv.on_midi(mido.Message("note_off", channel=0, note=note, velocity=0))
        lv.apply(n); lv.sweep(n)
        held = sounding(lv)
        if drums:
            # A struck drum rings on regardless of the key. The precise question
            # is not "is it still audible" -- after 1.5 s a snare has decayed on
            # its own -- but "did note-off CHANGE anything". So render the same
            # strike twice, once with a note-off and once without, and require
            # them to be identical.
            def strike(send_off):
                l2 = Live(program=prog, rate=48000, frames=128, drums=True, verbose=False)
                l2.warm()
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
        leak(lv, "%s: all slots returned" % label)

    # 4. the sustain pedal holds, and the sweep does not steal pedalled notes
    lv = Live(program=0, rate=48000, frames=128, verbose=False); lv.warm()
    lv.on_midi(mido.Message("control_change", channel=0, control=64, value=127))
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100)); lv.apply(0)
    lv.on_midi(mido.Message("note_off", channel=0, note=60, velocity=0))
    lv.apply(4800); lv.sweep(4800)
    check("pedal: holds the note after key-up", sounding(lv) > 0)
    lv.on_midi(mido.Message("control_change", channel=0, control=64, value=0))
    lv.apply(9600); lv.sweep(9600)
    check("pedal: releases on pedal-up", sounding(lv) == 0)

    # 5. a lost note-off is healed rather than droning
    lv = Live(program=0, rate=48000, frames=128, verbose=False); lv.warm()
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100)); lv.apply(0)
    lv.down.clear()                       # the note-off never arrived
    lv.sweep(4800)
    check("lost note-off is swept", lv.stuck == 1 and sounding(lv) == 0)

    # ---- multi-timbral ------------------------------------------------------
    # 6. a SPLIT sends each key to exactly one part
    kit = Part(bank_for(0, True, "hybrid"), lo=21, hi=47, transpose=14)
    tpt = Part(bank_for(56, False, "hybrid"), lo=48, hi=96)
    lv = Live(rate=48000, frames=128, verbose=False, parts=(kit, tpt))
    lv.on_midi(mido.Message("note_on", channel=0, note=24, velocity=100))
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
    lv.apply(0)
    check("split: each key reaches exactly its own part",
          {k[0] for k in lv.slab.live} == {kit.pid, tpt.pid}
          and all(k[0] == kit.pid for k in lv.slab.live if k[2] == 24)
          and all(k[0] == tpt.pid for k in lv.slab.live if k[2] == 60))

    # 7. a LAYER sends one key to both parts, and both release
    a1 = Part(bank_for(56, False, "hybrid"))
    a2 = Part(bank_for(48, False, "hybrid"))
    lv = Live(rate=48000, frames=128, verbose=False, parts=(a1, a2))
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100)); lv.apply(0)
    check("layer: one key sounds both parts",
          {k[0] for k in lv.slab.live} == {a1.pid, a2.pid})
    lv.on_midi(mido.Message("note_off", channel=0, note=60, velocity=0))
    lv.apply(4800); lv.sweep(4800)
    check("layer: one note-off releases both", sounding(lv) == 0)

    # 8. every slab key is the same shape -- the bug that hid in _sounding
    lv = Live(program=19, rate=48000, frames=128, verbose=False); lv.warm()
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
    lv.on_midi(mido.Message("control_change", channel=0, control=1, value=127))
    lv.apply(0)
    check("keys are uniform 4-tuples (organ ranks included)",
          bool(lv.slab.live) and all(len(k) == 4 for k in lv.slab.live))
    check("organ: bend and aftertouch reach every rank",
          len(lv._sounding(0)) == sounding(lv) and lv.errors == 0)

    # 9. a part swap under load leaks nothing
    lv = Live(program=56, rate=48000, frames=128, verbose=False); lv.warm()
    for note in (55, 60, 64):
        lv.on_midi(mido.Message("note_on", channel=0, note=note, velocity=100))
    lv.apply(0); lv.callback(None, 128, None, 0)
    lv.set_parts((Part(bank_for(48, False, "hybrid")),))
    lv.down.clear(); lv.sweep(lv.n)
    leak(lv, "part swap under load leaks no slots")

    # 10. an unbuilt template is silence, not a build on the audio thread
    lv = Live(program=56, rate=48000, frames=128, verbose=False)   # NOT warmed
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
    t0 = time.perf_counter(); lv.apply(0); dt = (time.perf_counter() - t0) * 1000.0
    check("unbuilt template is silent, and fast",
          lv.misses == 1 and sounding(lv) == 0 and dt < 1.0, "  (%.3f ms)" % dt)

    # 11. presets round-trip
    lv = Live(rate=48000, frames=128, verbose=False,
              parts=(Part(bank_for(56, False, "hybrid"), lo=48, hi=96, level_db=-3.0),
                     Part(bank_for(0, True, "hybrid"), lo=21, hi=47, transpose=14)))
    lv.bend_range = 7.0
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        pth = f.name
    try:
        save_preset("t", lv, pth)
        lv2 = Live(rate=48000, frames=128, verbose=False)
        apply_preset(lv2, load_presets(pth)["t"])
        shape = lambda l: [(p.program, p.drums, p.lo, p.hi, p.transpose, p.level_db)
                           for p in l.parts]
        check("preset saves and reloads the part set",
              shape(lv) == shape(lv2) and lv2.bend_range == 7.0)
    finally:
        os.unlink(pth)

    # ---- the mod wheel on an ensemble --------------------------------------
    # It should DEEPEN the section's vibrato, not flatten it. It used to write
    # one depth over every player, so a wheel-up turned seven violinists into
    # seven metronomes at exactly 35 cents.
    lv = Live(program=48, rate=48000, frames=128, verbose=False); lv.warm()
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100)); lv.apply(0)
    idx = np.flatnonzero(lv.slab.busy)
    def spread(a):
        # exact, not rounded: the depths are ~0.002 apart in raw units and
        # rounding to 5 places merged two of the seven players
        return len(np.unique(a[idx]))
    base = lv.slab.a["vd"][idx].copy(); baser = lv.slab.a["vr"][idx].copy()

    check("section vibrato: 7 depths, 7 rates, 7 phases",
          spread(lv.slab.a["vd"]) == 7 and spread(lv.slab.a["vr"]) == 7
          and spread(lv.slab.a["vp"]) == 7)
    lv.on_midi(mido.Message("control_change", channel=0, control=1, value=127))
    lv.apply(128)
    up = lv.slab.a["vd"][idx]
    check("mod wheel deepens without flattening", spread(lv.slab.a["vd"]) == 7
          and float(up.min()) > float(base.max()),
          "  (%.1f-%.1f cents)" % tuple(np.log2(1 + np.array([up.min(), up.max()],
                                                             dtype=np.float64)) * 1200))
    # vp itself MOVES on a rate change -- it is rotated so the LFO keeps its
    # place -- so the invariant is the LFO's phase, 2*pi*r*t + vp, not the
    # stored offset. The players stay distinct either way.
    def lfo(sl, ix, n):
        return (2 * np.pi * sl.a["vr"][ix].astype(np.float64) * (n / sl.rate)
                + sl.a["vp"][ix].astype(np.float64))
    check("...and the players stay distinct", spread(lv.slab.a["vp"]) == 7)
    # EVERY player quickens, not merely the range as a whole -- the resting and
    # raised ranges overlap (4.82-6.31 -> 6.02-7.89), so comparing the extremes
    # proves nothing. Compare each player against their own resting rate.
    check("mod wheel quickens as well as deepens, per player",
          spread(lv.slab.a["vr"]) == 7
          and bool((lv.slab.a["vr"][idx] > baser).all()),
          "  (%.2f-%.2f -> %.2f-%.2f Hz)"
          % (baser.min(), baser.max(),
             lv.slab.a["vr"][idx].min(), lv.slab.a["vr"][idx].max()))
    for v in (40, 100, 20, 127, 0):
        lv.on_midi(mido.Message("control_change", channel=0, control=1, value=v))
        lv.apply(256)
    check("wheel back to 0 restores the baseline exactly (no compounding)",
          float(np.abs(lv.slab.a["vd"][idx] - base).max()) == 0.0
          and float(np.abs(lv.slab.a["vr"][idx] - baser).max()) == 0.0)
    lv.renderer.close()

    # THE RATE IS INSIDE THE ACCUMULATED PHASE, not only the depth: the kernel's
    # vibrato term is (f*d/r)*(cos(2*pi*r*ton+vp) - cos(2*pi*r*t+vp)), so moving
    # r without re-deriving the anchor steps the phase. Measured, that step is
    # 53 radians -- eight cycles -- on every partial. Asserted here rather than
    # left to the ear, because an audio-domain click test could not see it: an
    # 8-sample slew window on an already-oscillating signal read 2.3x against
    # 2.1x, indistinguishable, while the phase itself was out by 8 cycles.
    def total_phase(slab, ix, n):
        a = slab.a
        om = a["om"][ix]; d = a["vd"][ix].astype(np.float64)
        r = np.maximum(a["vr"][ix].astype(np.float64), 1e-6)
        vp = a["vp"][ix].astype(np.float64)
        ton = a["non"][ix].astype(np.float64) / slab.rate
        f = om * slab.rate / (2 * np.pi); w2 = 2 * np.pi * r
        return (a["p0"][ix] + om * n
                + (f * d / r) * (np.cos(w2 * ton + vp) - np.cos(w2 * n / slab.rate + vp)))
    for prog, label in ((48, "section"), (56, "one player")):
        lv = Live(program=prog, rate=48000, frames=128, verbose=False); lv.warm()
        lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100)); lv.apply(0)
        for _ in range(40):
            lv.callback(None, 128, None, 0)
        ix = np.flatnonzero(lv.slab.busy); n = lv.n
        was = total_phase(lv.slab, ix, n); wasl = lfo(lv.slab, ix, n)
        lv.slab.retune(list(ix), n, vd=0.0203, vrs=1.25)
        jump = float(np.abs(total_phase(lv.slab, ix, n) - was).max())
        ljump = float(np.abs(lfo(lv.slab, ix, n) - wasl).max())
        check("%s: depth AND rate change without stepping the carrier" % label,
              jump < 1e-3, "  (%.1e rad)" % jump)
        # The one Ben's ear found and the carrier test could not: the LFO's own
        # phase is 2*pi*r*t + vp in absolute time, so a rate change moved it by
        # 2*pi*(r1-r0)*t -- growing with the note's age, 44 rad on a 5 s note --
        # simultaneously on every partial of every player.
        check("%s: ...or the vibrato's own phase" % label,
              ljump < 1e-3, "  (%.1e rad)" % ljump)
        # and it must still be true for a note that has been held a long time,
        # since the error was proportional to elapsed time
        for _ in range(3000):
            lv.callback(None, 128, None, 0)
        ix = np.flatnonzero(lv.slab.busy); n = lv.n
        wasl = lfo(lv.slab, ix, n)
        lv.slab.retune(list(ix), n, vd=0.0, vrs=1.0)
        lj2 = float(np.abs(lfo(lv.slab, ix, n) - wasl).max())
        check("%s: ...still, after 8 s of holding" % label, lj2 < 1e-3,
              "  (%.1e rad)" % lj2)
        lv.renderer.close()

    # a one-body voice has no spread to preserve and must behave as it always did
    lv = Live(program=56, rate=48000, frames=128, verbose=False); lv.warm()
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100)); lv.apply(0)
    lv.on_midi(mido.Message("control_change", channel=0, control=1, value=127)); lv.apply(128)
    i2 = np.flatnonzero(lv.slab.busy)
    cents = np.log2(1.0 + lv.slab.a["vd"][i2].astype(np.float64)) * 1200.0
    check("one player: the wheel is still a flat 35 cents",
          len(np.unique(lv.slab.a["vd"][i2])) == 1
          and abs(cents[0] - lv.mod_cents) < 0.01)
    lv.renderer.close()

    # ---- the reference renderer must survive a NON-section voice ------------
    # hammer_down asks every partial that carries a player index for its entry
    # offset, and the build gives one-body voices `player = 0` too. While
    # section_onsets_at lived on SectionMixin that call raised AttributeError for
    # every non-section voice, and the parity checks never saw it because they
    # were all run on strings and brass.
    for cls, lab in ((_T.ClarinetProperties, "clarinet"),
                     (_T.TrumpetProperties, "trumpet"),
                     (_T.GrandPianoProperties, "piano"),
                     (_T.ViolinProperties, "violin (a section)")):
        p = cls(261.63, 0.0, 1.0, 1.0)
        got = p.section_onsets_at(261.63)
        want_none = not getattr(cls, "section_onset_ms", 0.0) or getattr(cls, "section_players", 1) <= 1
        check("%s: section_onsets_at answers without raising" % lab,
              (got is None) == want_none, "  (%s)" % ("None" if got is None else "%d players" % len(got)))

    # ---- a chord on a solo voice is several players -------------------------
    lv = Live(program=56, rate=48000, frames=128, verbose=False); lv.warm()
    for nn in (60, 64, 67, 72):
        lv.on_midi(mido.Message("note_on", channel=0, note=nn, velocity=100))
    lv.apply(0)
    ix = np.flatnonzero(lv.slab.busy)
    rest = float(np.abs(lv.slab.a["vd"][ix]).max())
    check("a trumpet is dead straight until the wheel moves", rest == 0.0)
    lv.on_midi(mido.Message("control_change", channel=0, control=1, value=127)); lv.apply(128)
    nph = len(np.unique(lv.slab.a["vp"][ix])); nrt = len(np.unique(lv.slab.a["vr"][ix]))
    check("a four-note chord vibrates as four players, not one",
          nph == 4 and nrt == 4, "  (%d phases, %d rates)" % (nph, nrt))
    # depth stays common: they are copies of one instrument, not a string desk
    c = np.log2(1.0 + lv.slab.a["vd"][ix].astype(np.float64)) * 1200.0
    check("...at one depth, since they are the same instrument",
          float(c.max() - c.min()) < 0.01, "  (%.1f-%.1f cents)" % (c.min(), c.max()))
    lv.renderer.close()

    # and the locked behaviour is still reachable, which is the right answer for
    # a synth lead and makes the wheel a tempo control
    was = _T.TrumpetProperties.solo_vibrato_spread
    _T.TrumpetProperties.solo_vibrato_spread = 0.0
    _T._SOLO_VIBRATO.clear(); _BANKS.clear()
    lv = Live(program=56, rate=48000, frames=128, verbose=False); lv.warm()
    for nn in (60, 64, 67, 72):
        lv.on_midi(mido.Message("note_on", channel=0, note=nn, velocity=100))
    lv.on_midi(mido.Message("control_change", channel=0, control=1, value=127)); lv.apply(0)
    ix = np.flatnonzero(lv.slab.busy)
    check("spread = 0 locks the chord back together",
          len(np.unique(lv.slab.a["vp"][ix])) == 1 and len(np.unique(lv.slab.a["vr"][ix])) == 1)
    lv.renderer.close()
    _T.TrumpetProperties.solo_vibrato_spread = was
    _T._SOLO_VIBRATO.clear(); _BANKS.clear()

    # ---- vibrato must reach a voice that also SPEAKS ------------------------
    # The kernel's mode-lock transient and its vibrato shared one slot and the
    # second one to run threw the first away. 31 of a trumpet's 32 partials carry
    # a mode-lock term, so the mod wheel reached the FUNDAMENTAL ONLY: measured,
    # h1 swung 33.4 cents while h2, h4 and h8 swung 0.3, 0.1 and 0.1.
    lv = Live(program=56, rate=48000, frames=128, verbose=False); lv.warm()
    tb = lv.parts[0].bank.get(60, 100)["tbav"]
    check("a trumpet's partials do carry a mode-lock term",
          int((tb != 0).sum()) >= len(tb) - 1, "  (%d of %d)" % (int((tb != 0).sum()), len(tb)))
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100)); lv.apply(0)
    buf = []
    for i in range(int(2.2 * 48000) // 128):
        if i == 30:
            lv.on_midi(mido.Message("control_change", channel=0, control=1, value=127))
        b, _f = lv.callback(None, 128, None, 0)
        buf.append(np.frombuffer(b, np.float32)[0::2])
    x = np.concatenate(buf).astype(np.float64); sr = 48000.0
    def swing(h):
        f = 261.63 * h; N = len(x)
        S = np.fft.fft(x); fr = np.fft.fftfreq(N, 1 / sr)
        H = np.zeros(N, complex); bd = (fr > f * 0.93) & (fr < f * 1.07); H[bd] = 2 * S[bd]
        ph = np.unwrap(np.angle(np.fft.ifft(H)))
        inst = np.diff(ph) / (2 * np.pi) * sr
        seg = inst[int(1.2 * sr):int(2.0 * sr)]
        c = 1200 * np.log2(np.maximum(seg, 1e-6) / np.median(seg)); c -= c.mean()
        return float(np.percentile(np.abs(c), 95))
    h1, h2, h4 = swing(1), swing(2), swing(4)
    check("the mod wheel reaches the HARMONICS, not just the fundamental",
          h2 > 20.0 and h4 > 20.0,
          "  (h1 %.0f, h2 %.0f, h4 %.0f cents)" % (h1, h2, h4))
    lv.renderer.close()

    # ---- entry scatter -----------------------------------------------------
    lv = Live(program=61, rate=48000, frames=128, verbose=False); lv.warm()   # brass section
    def press(l, note=55):
        l.on_midi(mido.Message("note_on", channel=0, note=note, velocity=110)); l.apply(l.n)
        ix = np.flatnonzero(l.slab.busy)
        non = l.slab.a["non"][ix]; pl = l.slab.a["pl"][ix]
        ent = tuple(sorted(int(non[pl == p].min()) - int(non.min())
                           for p in np.unique(pl)))
        l.on_midi(mido.Message("note_off", channel=0, note=note, velocity=0)); l.apply(l.n)
        for _ in range(80):
            l.callback(None, 128, None, 0)
        return ent
    e1 = press(lv); e2 = press(lv); e3 = press(lv)
    check("a section's players enter at different instants",
          len(set(e1)) == 5, "  (%s samples)" % (e1,))
    check("and differently on every press", e1 != e2 and e2 != e3)
    span = max(e1) / 48000.0 * 1000.0
    check("scatter stays inside section_onset_ms", span <= 6.0 + 1e-6,
          "  (%.2f ms of 6.0)" % span)
    lv.down.clear(); lv.sweep(lv.n)
    leak(lv, "entry scatter leaks no slots")
    lv.renderer.close()

    # a one-body voice must be untouched: every partial starts together
    lv = Live(program=57, rate=48000, frames=128, verbose=False); lv.warm()   # one trombone
    e = press(lv)
    check("a single player still enters as one", e == (0,), "  (%s)" % (e,))
    lv.renderer.close()

    # ---- the threaded renderer ---------------------------------------------
    # 12. splitting the table across threads must not change what you hear
    def chord(K):
        lv = Live(rate=48000, frames=128, verbose=False, threads=K,
                  parts=(Part(bank_for(48, False, "hybrid")),))
        for nn in (48, 52, 55, 60, 64, 67):
            lv.on_midi(mido.Message("note_on", channel=0, note=nn, velocity=110))
        lv.apply(0)
        buf = []
        for _ in range(40):                       # right through the chiff
            b, _f = lv.callback(None, 128, None, 0)
            buf.append(np.frombuffer(b, np.float32))
        out = np.concatenate(buf)
        return lv, out
    lv1, one = chord(1)
    lv3, three = chord(3)
    check("threaded render engages above PARALLEL_MIN",
          lv3.renderer.act >= PARALLEL_MIN and lv3.renderer.K == 3,
          "  (%d active)" % lv3.renderer.act)
    rel = float(np.abs(three - one).max()) / max(float(np.abs(one).max()), 1e-30)
    check("3 threads match 1 thread to the last bits", rel < 1e-4,
          "  (%.1e relative, %.0f dB down)" % (rel, 20 * np.log10(max(rel, 1e-30))))
    # the split follows OCCUPANCY, not capacity -- an even split of the whole
    # slab gave thread 0 every active partial and measured slower than one
    b = lv3.renderer.bounds()
    per = [int(lv3.slab.busy[b[k]:b[k + 1]].sum()) for k in range(3)]
    check("the split balances occupied slots, not slot indices",
          max(per) <= 2 * max(min(per), 1), "  (%s)" % per)
    lv1.down.clear(); lv3.down.clear(); lv1.sweep(lv1.n); lv3.sweep(lv3.n)
    leak(lv3, "threaded: all slots returned")
    lv1.renderer.close(); lv3.renderer.close()

    # 13. a light block must NOT wake the pool -- below the threshold the
    # wakeups cost more than the split saves (measured 0.96x at 560 partials)
    lv = Live(program=56, rate=48000, frames=128, verbose=False, threads=4)
    lv.warm()
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
    lv.apply(0); lv.callback(None, 128, None, 0)
    check("a light block takes the direct path", lv.renderer.act < PARALLEL_MIN,
          "  (%d active)" % lv.renderer.act)
    lv.renderer.close()

    # 14. swapping the pool live, which is what the TUI's threads control does
    lv = Live(rate=48000, frames=128, verbose=False, threads=1,
              parts=(Part(bank_for(48, False, "hybrid")),))
    for nn in (48, 52, 55, 60, 64, 67):
        lv.on_midi(mido.Message("note_on", channel=0, note=nn, velocity=110))
    lv.apply(0); lv.callback(None, 128, None, 0)
    old = lv.renderer
    lv.renderer = Renderer(lv.slab, lv.frames, 3)
    lv.slab.dirty = True
    old.close()
    ok = True
    for _ in range(20):
        try:
            lv.callback(None, 128, None, 0)
        except Exception:
            ok = False
    check("the worker pool can be swapped while notes sound",
          ok and lv.errors == 0, "" if lv.errors == 0 else "  (%s)" % lv.last_error)
    lv.down.clear(); lv.sweep(lv.n)
    leak(lv, "pool swap leaks no slots")
    lv.renderer.close()

    # 15. fuzz every mode: no errors, no leaks
    for prog, drums, label in ((0, False, "piano"), (19, False, "organ"), (0, True, "drums")):
        lv = Live(program=prog, rate=48000, frames=128, drums=drums, verbose=False)
        lv.warm()
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
        lv.apply(n); lv.down.clear(); lv.sweep(n); lv.n = n
        check("%s: 2500 mixed events, no errors" % label, lv.errors == 0,
              "" if lv.errors == 0 else "  (%s)" % lv.last_error)
        leak(lv, "%s: 2500 mixed events, no leak" % label)

    # 16. a fuzzed LAYER + SPLIT, the configuration the TUI actually makes
    lv = Live(rate=48000, frames=128, verbose=False, parts=(
        Part(bank_for(0, True, "hybrid"), lo=21, hi=47, transpose=14),
        Part(bank_for(48, False, "hybrid"), lo=48, hi=96),
        Part(bank_for(56, False, "hybrid"), lo=48, hi=96, level_db=-6.0)))
    random.seed(9); down = set(); n = 0
    for _ in range(1500):
        n += 128; r = random.random()
        if r < 0.35:
            v = random.choice([24, 30, 38, 55, 60, 67])
            lv.on_midi(mido.Message("note_on", channel=0, note=v, velocity=random.randint(1, 127)))
            down.add(v)
        elif r < 0.65 and down:
            v = random.choice(sorted(down))
            lv.on_midi(mido.Message("note_off", channel=0, note=v, velocity=0)); down.discard(v)
        elif r < 0.75:
            lv.on_midi(mido.Message("control_change", channel=0, control=64,
                                    value=random.choice([0, 127])))
        elif r < 0.9:
            lv.on_midi(mido.Message("control_change", channel=0, control=1, value=random.randint(0, 127)))
        else:
            lv.on_midi(mido.Message("pitchwheel", channel=0, pitch=random.randint(-8192, 8191)))
        lv.apply(n); lv.sweep(n); lv.slab.reap(n)
    lv.on_midi(mido.Message("control_change", channel=0, control=64, value=0))
    lv.on_midi(mido.Message("control_change", channel=0, control=123, value=0))
    lv.apply(n); lv.down.clear(); lv.pedalled.clear(); lv.sweep(n); lv.n = n
    check("layer+split: 1500 mixed events, no errors", lv.errors == 0,
          "" if lv.errors == 0 else "  (%s)" % lv.last_error)
    leak(lv, "layer+split: 1500 mixed events, no leak")

    print("\n  %s" % ("all passed" if not fails else "FAILED: %s" % ", ".join(fails)))
    return 1 if fails else 0


def open_stream(live, rate, frames):
    import pyaudio
    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paFloat32, channels=2, rate=rate, output=True,
                     frames_per_buffer=frames, stream_callback=live.callback)
    return pa, stream


def pick_port(sub):
    names = mido.get_input_names()
    if not names:
        return None, []
    return next((n for n in names if sub and sub.lower() in n.lower()), names[0]), names


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
    ap.add_argument("--capacity", type=int, default=16384, help="partial slots (layering needs more)")
    ap.add_argument("--threads", type=int, default=1,
                help="split the partial table across N threads (3 is usually best; "
                     "only engages above %d occupied slots)" % PARALLEL_MIN)
    ap.add_argument("--preset", default=None, help="load this preset from presets.json at startup")
    ap.add_argument("--tui", action="store_true", help="full-screen synthesiser interface")
    ap.add_argument("--list", action="store_true", help="list MIDI inputs and exit")
    ap.add_argument("--selftest", action="store_true", help="run the behaviour checks and exit")
    ap.add_argument("--latency", action="store_true", help="measure MIDI-to-DAC latency while you play")
    a = ap.parse_args()

    if a.selftest:
        sys.exit(selftest())

    if a.list:
        for n in mido.get_input_names():
            print(" ", n)
        return
    name, names = pick_port(a.port)
    if not name:
        sys.exit("no MIDI inputs found (is the keyboard plugged in?)")

    # THE GIL IS THE REAL CONSTRAINT ON BACKGROUND BUILDS. PyAudio's callback is
    # a Python callback, so it needs the GIL, and blockrender.prepare() is pure
    # Python and holds it. The default switch interval is 5 ms -- longer than the
    # 2.7 ms budget at 128 frames -- so a patch built while playing would underrun
    # on nothing but thread scheduling. 0.5 ms costs a little throughput and buys
    # a build that does not glitch.
    sys.setswitchinterval(0.0005)

    live = Live(program=a.program, rate=a.rate, frames=a.frames, tuner=a.tuner,
                drums=a.drums, headroom_db=a.headroom, capacity=a.capacity,
                threads=a.threads, verbose=not a.tui)
    if a.preset:
        pres = load_presets().get(a.preset)
        if not pres:
            sys.exit("no preset %r in %s" % (a.preset, PRESET_PATH))
        apply_preset(live, pres)
    live.warm()

    if a.tui:
        import livetui
        return livetui.run(live, name)

    if a.drums:
        sys.stderr.write("  GM percussion at %d Hz, %d-frame blocks\n" % (a.rate, a.frames))
    else:
        sys.stderr.write("  program %d -> %s at %d Hz, %d-frame blocks\n"
                         % (a.program, live.parts[0].bank.cls_name, a.rate, a.frames))

    pa, stream = open_stream(live, a.rate, a.frames)
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
                s = live.stats()
                sys.stderr.write("    %5.1f s  peak %.3f  sounding %4d  free %5d  "
                                 "under %d  drop %d  err %d  stuck %d  miss %d%s\n"
                                 % (s["t"], s["peak"], s["sounding"], s["free"],
                                    s["under"], s["drop"], s["err"], s["stuck"],
                                    s["miss"],
                                    ("  last: " + s["last_error"]) if s["last_error"] else ""))
                sys.stderr.flush()
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream(); stream.close(); pa.terminate(); port.close()
        live.renderer.close()
        s = live.stats()
        sys.stderr.write("\n  peak %.3f  underruns %d  dropped %d  errors %d  stuck %d  miss %d\n"
                         % (s["peak"], s["under"], s["drop"], s["err"], s["stuck"], s["miss"]))
        if live.lat:
            def stat(vals):
                v = sorted(x * 1000.0 for x in vals)
                return (v[len(v) // 2], v[0], v[-1])
            tot = stat([x + y for x, y in live.lat])
            inq = stat([x for x, _ in live.lat])
            buf = stat([y for _, y in live.lat])
            sys.stderr.write("  MIDI-to-DAC over %d notes:\n" % len(live.lat))
            sys.stderr.write("    midi in + queue  median %5.1f ms  (%.1f - %.1f)\n" % inq)
            sys.stderr.write("    audio buffer     median %5.1f ms  (%.1f - %.1f)\n" % buf)
            sys.stderr.write("    TOTAL            median %5.1f ms  (%.1f - %.1f)\n" % tot)
        if live.last_error:
            sys.stderr.write("  last error: %s\n" % live.last_error)


if __name__ == "__main__":
    main()
