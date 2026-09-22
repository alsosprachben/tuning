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

import math
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
           "cv", "cc", "crl", "sj", "csc", "cbw", "tbav", "tau", "tcut",
           "vd", "vr", "vp", "delL", "delR", "az")
COLS_I8 = ("non", "noff")
COLS_I4 = ("gr", "cr", "pl")
ALL_COLS = COLS_F8 + COLS_F4 + COLS_I8 + COLS_I4

IDLE = 1 << 62          # a note-on so far in the future the partial never sounds

# ---- the half-moon, on the pitch wheel --------------------------------------
# A HAMMOND HAS NO PITCH BEND. The tonewheels are driven by a synchronous motor
# off the mains, so the pitch is the mains frequency and there is nothing to
# bend -- which leaves the wheel free for the control the instrument actually
# has and a keyboard does not: the half-moon switch.
#
# A half-moon is a three-position SWITCH (stop / chorale / tremolo), not a knob,
# and a pitch wheel springs back to centre, so it cannot hold a position. Read
# it as EDGE EVENTS instead: a flick past PW_FIRE steps the ladder one place,
# and letting it spring back past PW_REARM re-arms it. Two flicks up walks
# stop -> chorale -> tremolo. The hysteresis matters -- a wheel left resting on
# the threshold would otherwise machine-gun the rotor with requests.
PW_FIRE = 0.50          # fraction of full travel that fires a step
PW_REARM = 0.20         # and where the wheel has to return to before the next
MIN_AMP_HZ = 20.0       # a parent below this is a rumble, not a tone

# ---- the mod wheel as the swell pedal ---------------------------------------
# On a real rig the Leslie's amplifier has FIXED gain and the swell pedal sits
# in FRONT of it, which is how a player makes it break up: you open the pedal.
# The offline path cannot express that -- it normalises every segment to its
# `drive` and so distorts identically however hard the passage is played -- but
# live the wheel can simply be the drive.
#
# Quantised, because moving it means recomputing the distortion partials and a
# continuous controller would ask for that on every message. Eight steps over
# the range, which is the same trick (and the same reason) as quantising the
# rotor to three zones upstream.
LIVE_DRIVE_STEPS = 8
LIVE_DRIVE_RANGE = 4.0  # wheel fully up = this many times the voice's amp_drive

MELODIC_RANGE = (21, 96)        # a keyboard
DRUM_RANGE = (35, 87)           # every note percussion_map has a voice for
# NOT the GM kit's 35-81. percussion_map reaches 87, and the four notes above
# 81 -- bell tree, castanets, and the mute and open surdo -- were unreachable
# live: warm() never built them, so a pad sending note 84 got a template of
# None and silence. They are fitted voices like the rest of the kit and there
# is no reason the live engine should be the one place they cannot be played.
# 82 and 83 are real holes in the map; warm() already skips what it cannot
# build, so they cost nothing.


class LiveRotor:
    """One rotor, advanced a block at a time.

    The offline Rotor precomputes its whole trajectory because it knows how
    long the piece is. Live there is no end, so this integrates forward: one
    exponential step toward the requested speed per callback, and the angle
    accumulated from the rate as it actually was, not as it was asked to be.
    """

    def __init__(self, horn):
        import leslie as _L
        self.up = _L.HORN_SPIN_UP if horn else _L.DRUM_SPIN_UP
        self.down = _L.HORN_SPIN_DOWN if horn else _L.DRUM_SPIN_DOWN
        self.ratio = 1.0 if horn else _L.DRUM_RATIO
        self.rate = _L.CHORALE
        self.target = _L.CHORALE
        self.angle = 0.0

    def advance(self, dt):
        tau = self.up if self.target > self.rate else self.down
        self.rate += (self.target - self.rate) * (1.0 - math.exp(-dt / tau))
        self.angle += 2.0 * math.pi * self.rate * self.ratio * dt
        if self.angle > 1e6:
            self.angle = math.fmod(self.angle, 2.0 * math.pi)
        return self.angle


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
        # The wash's bandwidth, as a fraction of the partial's frequency. This
        # list has to match blockrender's `cols` exactly -- synth_partials asks
        # the slab for every column by name -- and it must default to RAND_GRAN
        # rather than to zero: at zero the chiff's hash index never advances, so
        # the "noise" becomes a fixed phase offset and the wash turns tonal.
        self.a["cbw"][:] = B.RAND_GRAN
        # THE ROTOR'S SIDE OF THE SLAB. None of this is a kernel column --
        # synth_partials never asks for it -- it is what the callback needs to
        # recompute each partial's level every block: how deeply this partial
        # swings (deeper the higher it sits, because a horn beams), the azimuth
        # it left by, which rotor carries it, and the amplitude it would have
        # had standing still.
        self.ls_on = np.zeros(capacity, bool)
        # The tremolo, and the Rhodes' stereo pan, which is the same thing with
        # one sign flipped (see tremolo.py). Live it is a per-block GAIN rather
        # than sidebands -- cheaper, and exact, which is the same trade
        # leslie_swing makes against leslie.expand. tr_st is +1 for a level
        # tremolo and -1 for a pan, and that is the whole difference.
        # The clavinet's tone rockers. Unlike the tremolo this does NOT need
        # the callback: it is a fixed filter that only moves when the wheel
        # does, so it is recomputed on a CC1 and on each new note and not once
        # a block. cv_aL/cv_aR are the unfiltered template, kept so that
        # sweeping the wheel cannot compound.
        self.cv_on = np.zeros(capacity, bool)
        self.cv_aL = np.zeros(capacity, np.float32)
        self.cv_aR = np.zeros(capacity, np.float32)

        self.tr_on = np.zeros(capacity, bool)
        self.tr_dep = np.zeros(capacity, np.float32)
        self.tr_st = np.ones(capacity, np.float32)
        self.tr_aL = np.zeros(capacity, np.float32)
        self.tr_aR = np.zeros(capacity, np.float32)
        self.ls_am = np.zeros(capacity, np.float32)     # the lobe's floor
        self.ls_sharp = np.ones(capacity, np.float32)
        self.ls_norm = np.ones(capacity, np.float32)     # so the mean is 1
        self.ls_ph = np.zeros(capacity, np.float32)
        self.ls_horn = np.zeros(capacity, bool)
        self.ls_aL = np.zeros(capacity, np.float32)
        self.ls_aR = np.zeros(capacity, np.float32)
        self.last_slots = []
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

    def leslie_arm(self, slots, az, nf, n=None, horn_rate=None, drum_rate=None):
        """Record what the callback needs to swing these partials.

        PASS THE RATES. The Doppler base written here is the deviation at
        FAST_HZ -- a unit, not a speed -- and the callback only rescales it
        when the rotor's rate MOVES. So a partial armed while the rotor sits
        settled on chorale kept a 6.6 Hz wobble at full depth until the switch
        was next touched, which is audible as new notes spinning at tremolo
        while the held ones turn slowly, and as everything snapping back into
        line the moment the speed is changed. Ben, playing: "sometimes in the
        middle speed it goes to 6 Hz in half the sound... when I move it to
        full speed, it resets. It seems related to note off events" -- it was
        note ON, or rather anything that stamps: every new note, every rank
        drawn, and every refresh of the amplifier's products.
        """
        import leslie as _L
        if not slots:
            return
        idx = np.fromiter(slots, np.int64, len(slots))
        nf = np.asarray(nf, np.float64)
        horn = nf >= _L.CROSSOVER_HZ
        # THE LOBE ITSELF, not its first Fourier term. Live this is a gain, so
        # the exact pattern costs no more than a cosine did -- and a cosine is
        # what makes a rotating speaker sound like a tremolo pedal. The drum
        # fires into a rotating scoop rather than sweeping a horn, so its lobe
        # is blunter: half the sharpness and half the depth.
        fl = np.empty(len(nf), np.float32)
        sh = np.empty(len(nf), np.float32)
        for j, f in enumerate(nf):
            a, b = _L.beam(float(f))
            fl[j], sh[j] = a, b
        sh = np.where(horn, sh, np.maximum(sh * 0.5, 0.5))
        fl = np.where(horn, fl, 1.0 - (1.0 - fl) * 0.5)
        self.ls_on[idx] = True
        self.ls_ph[idx] = np.asarray(az, np.float32)
        self.ls_horn[idx] = horn
        self.ls_am[idx] = fl
        self.ls_sharp[idx] = sh
        # mean of the lobe, so the swing is a colour and not a level change
        th = np.linspace(0.0, 2.0 * np.pi, 256, endpoint=False)
        cc = 0.5 * (1.0 + np.cos(th))
        self.ls_norm[idx] = (fl[:, None] + (1.0 - fl[:, None])
                             * cc[None, :] ** (0.5 * sh[:, None])).mean(axis=1)
        self.ls_aL[idx] = self.a["aL"][idx]
        self.ls_aR[idx] = self.a["aR"][idx]
        # THE DOPPLER IS NORMALISED TO A REFERENCE ROTOR, whatever speed the
        # template happened to be built at, so every rotor partial shares one
        # base and a single scalar can move the whole group. vsc is set equal
        # to vbase so retune's `vbase + vd*vsc` becomes vbase*(1+vd) -- depth
        # then tracks rate linearly, which is what Doppler does: the deviation
        # is the arm's tip speed, and tip speed is proportional to rate.
        ref = np.where(horn, _L.FAST_HZ, _L.FAST_HZ * abs(_L.DRUM_RATIO))
        rad = np.where(horn, _L.HORN_RADIUS, _L.DRUM_RADIUS)
        self.vrbase[idx] = ref
        self.vbase[idx] = 2.0 * np.pi * rad * ref / _L.C_SOUND
        self.vsc[idx] = self.vbase[idx]
        if horn_rate is not None:
            self._doppler_to(idx, horn, n, horn_rate, drum_rate)

    def _doppler_to(self, idx, horn, n, horn_rate, drum_rate):
        """Scale these partials' REFERENCE Doppler to the rate the rotors are
        actually turning at.

        leslie_arm writes the deviation a rotor would make at FAST_HZ, because
        that gives every rotor partial one base and lets a single scalar move
        the whole group. The base is not a speed, it is a unit -- so nothing is
        at the right speed until this has run over it.
        """
        import leslie as _L
        for sel, rate, ref in ((horn, horn_rate, _L.FAST_HZ),
                               (~horn, drum_rate,
                                _L.FAST_HZ * abs(_L.DRUM_RATIO))):
            sub = idx[sel]
            if not len(sub):
                continue
            vrs = max(rate, 1e-4) / ref
            self.retune(sub.tolist(), n, vd=vrs - 1.0, vrs=vrs)

    def leslie_doppler(self, n, horn_rate, drum_rate):
        """Move the rotor partials' frequency modulation to the current speed.

        retune() does the hard part -- it puts the phase back so neither the
        carrier nor the accumulated vibrato phase steps, which is what would
        click. Called only when the rate has actually moved, so a settled rotor
        costs nothing -- which is why leslie_arm has to place a NEW partial at
        the current rate itself rather than wait for this.
        """
        m = self.ls_on & self.busy
        if not m.any():
            return
        idx = np.flatnonzero(m)
        self._doppler_to(idx, self.ls_horn[idx], n, horn_rate, drum_rate)

    def clav_tone(self, setting, slots=None):
        """Set the tone rockers on the partials that are sounding.

        Recomputed from the UNFILTERED template every time, never from what is
        already there, so sweeping the wheel back and forth cannot compound --
        the same reason aftertouch works from aL0/aR0.
        """
        import tonelib as _TL
        if slots is None:
            m = self.cv_on & self.busy
            if not m.any():
                return
            idx = np.flatnonzero(m)
        else:
            if slots is None or not len(slots):
                return
            idx = np.asarray(slots, dtype=np.intp)
            fresh = idx[~self.cv_on[idx]]
            if len(fresh):
                self.cv_aL[fresh] = self.a["aL"][fresh]
                self.cv_aR[fresh] = self.a["aR"][fresh]
            self.cv_on[idx] = True
        g = _TL.clav_tone_gain(self.a["nf"][idx], setting)
        self.a["aL"][idx] = self.cv_aL[idx] * g
        self.a["aR"][idx] = self.cv_aR[idx] * g
        self.dirty = True

    def tremolo_arm(self, slots, depth, stereo):
        """Record what the callback needs to swing these partials.

        The base amplitudes are captured ONCE, on rows not already armed.
        Capturing again on a wheel move would save an amplitude that has
        already been modulated and the swing would compound on itself every
        time the wheel was touched -- the mistake aL0/aR0 exists to prevent for
        aftertouch, arrived at from the other direction.
        """
        if slots is None or not len(slots):
            return
        idx = np.asarray(slots, dtype=np.intp)
        fresh = idx[~self.tr_on[idx]]
        if len(fresh):
            self.tr_aL[fresh] = self.a["aL"][fresh]
            self.tr_aR[fresh] = self.a["aR"][fresh]
        self.tr_on[idx] = True
        self.tr_dep[idx] = depth
        self.tr_st[idx] = -1.0 if stereo else 1.0

    def tremolo_swing(self, phase):
        """Set every modulated partial's level from where the modulator has got
        to. Evaluated NOW, so a held chord follows the wheel instead of keeping
        whatever depth it was born with."""
        m = self.tr_on & self.busy
        if not m.any():
            return
        idx = np.flatnonzero(m)
        c = math.cos(phase) * self.tr_dep[idx]
        self.a["aL"][idx] = self.tr_aL[idx] * (1.0 + c)
        self.a["aR"][idx] = self.tr_aR[idx] * (1.0 + c * self.tr_st[idx])

    def leslie_swing(self, horn_angle, drum_angle):
        """Set every rotor partial's level from where the rotor has got to.

        This is the whole point of doing it here rather than as sidebands: the
        angle is evaluated NOW, so a held chord follows a speed change instead
        of keeping whatever it was born with.
        """
        m = self.ls_on & self.busy
        if not m.any():
            return
        idx = np.flatnonzero(m)
        ang = np.where(self.ls_horn[idx], horn_angle, drum_angle)
        fl = self.ls_am[idx]
        c = 0.5 * (1.0 + np.cos(ang - self.ls_ph[idx]))
        g = fl + (1.0 - fl) * c ** (0.5 * self.ls_sharp[idx])
        g /= self.ls_norm[idx]
        self.a["aL"][idx] = self.ls_aL[idx] * g
        self.a["aR"][idx] = self.ls_aR[idx] * g

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
        self.ls_on[idx] = False
        self.tr_on[idx] = False
        self.cv_on[idx] = False
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
        # THE SLOTS JUST ALLOCATED, which is not the same as live[key]: that
        # accumulates, by design -- a key is stamped once per rank, and a
        # re-struck note adds to it rather than replacing it. Arming the rotor
        # from live[key] therefore handed 96 slots an array of 48 azimuths the
        # second time a note was hit, which threw inside the callback, and the
        # callback answers an exception with silence and a skipped reap.
        self.last_slots = slots
        if oneshot:
            self.oneshot[key] = True
        return True

    def stamp_amp(self, key, src, freqs, amps, phases, n0, rate):
        """Place the amplifier's distortion partials, copying `src` for the rest.

        A distortion product is a partial like any other and belongs wherever
        its parents went -- same part, same room, same reflections -- so
        everything except frequency, level and phase is taken from a partial
        that is already sounding. That is exactly what the offline path does
        with `A[k][src]`; here the source is a slot rather than a row.
        """
        n = len(freqs)
        if n == 0 or len(self.free) < n:
            return []
        slots = [self.free.popleft() for _ in range(n)]
        idx = np.fromiter(slots, np.int64, n)
        self.busy[idx] = True
        self.ls_on[idx] = False
        self.tr_on[idx] = False
        self.cv_on[idx] = False
        self.dirty = True
        a = self.a
        for k in COLS_F4:
            a[k][idx] = a[k][src]
        for k in COLS_I4:
            a[k][idx] = a[k][src]
        a["gr"][idx] = -1       # ungated: the amplifier is not a drawn rank
        a["cr"][idx] = 0
        f = np.asarray(freqs, np.float64)
        om = 2.0 * np.pi * f / float(rate)
        a["om"][idx] = om
        a["nf"][idx] = f.astype(np.float32)
        # `phases` is the phase wanted AT n0, and p0 anchors at sample 0.
        a["p0"][idx] = np.asarray(phases, np.float64) - om * n0
        a["p0R"][idx] = a["p0"][idx]
        a["non"][idx] = n0
        a["noff"][idx] = IDLE
        # Levels ride the source's own panning, so a product sits where its
        # parents sit. aL0/aR0 rather than aL/aR: the live rotor rewrites aL/aR
        # every block, and reading it mid-swing would bake the swing in.
        ref = 0.5 * (float(self.aL0[src]) + float(self.aR0[src]))
        g = np.asarray(amps, np.float64) / max(ref, 1e-30)
        a["aL"][idx] = (float(self.aL0[src]) * g).astype(np.float32)
        a["aR"][idx] = (float(self.aR0[src]) * g).astype(np.float32)
        self.aL0[idx] = a["aL"][idx]
        self.aR0[idx] = a["aR"][idx]
        self.hrel[idx] = 1.0
        self.vbase[idx] = 0.0
        self.vrbase[idx] = 0.0
        self.vsc[idx] = 1.0
        self.live.setdefault(key, []).extend(slots)
        self.last_slots = slots
        return slots

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
        # PORTAUDIO IS ASKED FOR A BLOCK SIZE, NOT PROMISED ONE. The buffers are
        # allocated once at `frames` and the kernel writes however many samples
        # it is told to, straight into them through a pointer -- so a callback
        # arriving with a larger frame_count than the stream was opened with is
        # a C write past the end of a numpy array. That is heap corruption, and
        # it presents exactly as Ben saw it: fine for a minute of playing and
        # then "malloc(): invalid next size (unsorted)", nowhere near the code
        # that did it. Grow instead. An allocation on the audio thread is a
        # glitch; writing past a buffer is a crash an hour later.
        if frames > len(self.L):
            self.L = np.zeros(frames, np.float32)
            self.R = np.zeros(frames, np.float32)
            self.bufs = [(np.zeros(frames, np.float32),
                          np.zeros(frames, np.float32))
                         for _ in range(self.K)]
            self.grew = getattr(self, "grew", 0) + 1
        b = self.bounds()
        L, R = self.L, self.R
        L[:] = 0.0; R[:] = 0.0
        # A VIEW OF WHAT WAS ASKED FOR, not the whole buffer: once it has grown
        # it stays grown, and the caller wants exactly frame_count samples.
        if b is None:                       # nothing occupied: silence, cheaply
            return L[:frames], R[:frames]
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
        return L[:frames], R[:frames]


# ---- banks: the expensive, shareable half of a patch ------------------------

# The honky-tonk's wheel positions, pre-warmed so sweeping it cannot miss.
# 64 is the voice's own range, and the value a bank defaults to.
DETUNE_STEPS = (0, 64, 127)

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
        # A ROTOR IS PART OF THE TEMPLATE, not a control over it. The level
        # swing is carried by sidebands at the rotor rate (see leslie.py), so
        # a change of speed is a change of PARTIALS and cannot be retuned --
        # it needs a different template. Hence a speed axis on the cache.
        self.leslie = (not drums) and getattr(pc, "leslie", False)
        # The drive the VOICE was voiced at. Live the mod wheel scales it,
        # so this is the reference and not the setting -- a voice with no
        # amplifier (amp_drive 0) stays clean however far the wheel goes.
        self.amp_drive = 0.0 if drums else float(getattr(pc, "amp_drive", 0.0))
        # The level `amp_drive` is measured against, so playing harder breaks
        # up. None = scale by each chord's own peak, which is right for a
        # keyboard and wrong for anything with a picking hand.
        self.amp_reference = None if drums else getattr(pc, "amp_reference", None)
        # The speaker. The TEMPLATE already went through it -- prepare() runs
        # the cabinet pass -- and that is exact for a linear filter, since
        # filtering each note and summing is the same as filtering the sum.
        # The amplifier's products are the exception: they are created here,
        # after the template was built, so _amp_place has to put them through
        # the speaker itself or they arrive unfiltered. That is the whole
        # difference between overdrive and a wasp.
        self.cabinet = None if drums else getattr(pc, "cabinet", None)
        # The modulation the panel offers, which is NOT baked into the template:
        # live it is a per-block gain, so one template plays at every depth and
        # a held chord follows the wheel. tremolo_depth is what a full wheel
        # asks for, not a setting -- at rest the panel is off.
        # The clavinet's tone rockers, which are a filter and so need no new
        # template -- unlike its AB/CD pickup switches, which would.
        self.clav_panel = (not drums) and bool(getattr(pc, "clav_panel", False))
        self.tremolo_hz = 0.0 if drums else float(getattr(pc, "tremolo_hz", 0.0))
        self.tremolo_depth = 0.0 if drums else float(getattr(pc, "tremolo_depth", 0.0))
        self.tremolo_stereo = (not drums) and bool(getattr(pc, "tremolo_stereo", False))
        # NO SPEED AXIS. It existed because the rotor was baked into the
        # partials; now both the level swing and the Doppler are driven from
        # the callback, so one template serves every speed and the cache is a
        # third the size it was a moment ago.
        self.speeds = (None,)
        self.leslie_default = None
        # A HONKY-TONK'S DETUNE IS IN THE PARTIALS' FREQUENCIES, so unlike the
        # clavinet's rockers it cannot be a gain applied to a note already
        # sounding -- it is a different template. But the axis for that already
        # exists and is literally "the CC1 value to build with", so three wheel
        # positions are pre-warmed and the wheel picks between them. A note
        # keeps the tuning it was struck with, which is what a piano does.
        self.detune_wheel = (not drums) and bool(getattr(pc, "detune_wheel", False))
        if self.detune_wheel:
            self.speeds = DETUNE_STEPS
            self.leslie_default = DETUNE_STEPS[len(DETUNE_STEPS) // 2]
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

    def _raw_template(self, note, vel, fast=None):
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
        if fast is not None:
            # CC1 is the half-moon switch on a tonewheel voice; blockrender
            # reads it through leslie.zone() and gives every partial the
            # rotor's rate and angle. `fast` is the CC value itself, so the
            # zone boundaries live in one place.
            tr.append(mido.Message("control_change", channel=ch, control=1,
                                   value=int(fast), time=0))
        tr.append(mido.Message("note_on", channel=ch, note=note, velocity=vel, time=0))
        tr.append(mido.Message("note_off", channel=ch, note=note, velocity=0, time=480))
        # A struck drum ignores note-off and rings out on its own decay, so
        # prepare() extends it to 8 s. The template has to be long enough to
        # hold that, or the tail is cut at build time.
        tr.append(mido.MetaMessage("end_of_track", time=480 * (18 if self.drums else 1)))
        # NO AMPLIFIER AT BUILD TIME, FOR ANY VOICE. The amplifier is a CHORD
        # effect and a one-note template cannot know about it, so baking each
        # note's own distortion in here has it counted twice once the live
        # stage adds the chord's -- and worse, those baked products are then
        # read back as PARENTS, which is how a single Hammond key came to
        # measure 103 distortion partials where it honestly makes 15.
        #
        # This used to be done only for Leslie voices, because the Hammond was
        # the only thing with an amplifier. An electric guitar has one too and
        # is not a Leslie voice, so it took the `else` branch and built every
        # template through the full offline pass: double distortion, a slow
        # build, and a page of log noise per template into the TUI.
        #
        # THE CABINET STAYS ON, and that is not an inconsistency: a speaker is
        # a LINEAR filter, so filtering each note and summing is the same as
        # filtering the sum. Only the nonlinearity has to wait for the chord.
        import leslie as _L
        import tubeamp as _TA
        _wasa, _TA.ENABLED = _TA.ENABLED, False
        # NO SIDEBANDS LIVE either, for a rotor. Offline the level swing has to
        # be partials because the render is one stateless call; here there is a
        # callback, so the swing is a gain and the rotor stays a thing that can
        # still be turned while a chord is held.
        _was = _L.SIDEBANDS
        if self.leslie:
            _L.SIDEBANDS = False
        try:
            # AND QUIETLY. prepare() reports what its passes did, which is
            # right for a render and is corruption for a curses screen -- the
            # TUI owns the terminal. Redirected rather than flag-guarded so
            # that anything added to those passes later is caught too.
            import contextlib as _ctx, io as _io
            with _ctx.redirect_stdout(_io.StringIO()):
                p = B.prepare(m, self.tuner)
        finally:
            _L.SIDEBANDS = _was
            _TA.ENABLED = _wasa
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
        total = (hi - lo + 1) * self.nbuckets * len(self.speeds)
        for note in range(lo, hi + 1):
            for b in range(self.nbuckets):
                for sp in self.speeds:
                    if (note, b, sp) not in self.templates:
                        try:
                            t = self._raw_template(note, self.bucket_vel(b), sp)
                        except Exception:
                            t = None     # unmapped drum note: nothing to build
                        if t is not None:
                            self.templates[(note, b, sp)] = t
                            self.partials += t["P"]
                    done += 1
                if progress and (done & 15) == 0:
                    progress(self, done / float(total))
        self.warmed = True
        if progress:
            progress(self, 1.0)
        return self

    # ---- lookup (the audio thread's only entry point) -----------------------
    def get(self, note, vel, fast=None):
        """Pure lookup. A miss returns None and is NEVER a build: building here
        costs 1.4-10 ms, which is more than a whole 2.7 ms block."""
        return self.templates.get((note, self.bucket(vel), fast))


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
        ds = getattr(bank.pc, 'default_stops', 1) if hasattr(bank,'pc') else 1
        self.drawn = {r for j, r in enumerate(bank.rank_names) if (ds >> j) & 1} \
                      or set(bank.cres_order[:1])   # start on the voice's own registration
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
        # WORK THE TUI WANTS DONE ON THE AUDIO THREAD. The slab has exactly one
        # writer by design -- the callback -- and everything that keeps it
        # consistent assumes that: `free` is popped from, `live` is added to and
        # popped from, and `last_slots` is written by one stamp and read by the
        # very next line. A second thread doing any of that can hand `_draw` a
        # set of slots that belong to something else entirely. So the TUI asks,
        # and the callback does it, the same way MIDI already works.
        self.cmds = collections.deque()
        self.lock = threading.Lock()
        self.bend = {}          # channel -> current pitch-bend ratio
        self.mod = {}           # channel -> current vibrato depth (fraction)
        self.trem_depth = {}    # pid -> current tremolo/pan depth (fraction)
        self.detune_step = {}   # pid -> which pre-warmed detune the wheel is on
        self.clav_step = {}     # pid -> current tone-rocker position
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
        # Which way the half-moon switch is thrown, per channel. A tonewheel
        # voice has no crescendo pedal -- that is a pipe-organ control -- so on
        # those parts the mod wheel is the rotor instead. The VOICE decides
        # what CC1 means, never a mode: a held controller value cannot be
        # reinterpreted under it, which is the failure a mode would invite.
        self.rotor_fast = {}    # channel -> the CC1 zone a NEW note is built at
        # ONE CABINET, not one per channel: there is a Leslie in the room and
        # everything routed to it turns with the same rotors.
        self.rotor_horn = LiveRotor(True)
        self.rotor_drum = LiveRotor(False)
        self._ls_rate = -1.0    # horn rate the Doppler was last moved to
        self.cc1_count = 0      # how many mod-wheel messages have arrived
        self.cc1_last = -1      # and the last value, so a monitor can see them
        # The half-moon ladder. ONE cabinet, so one position -- but the ARMING
        # is per channel, because each controller has its own wheel and each
        # springs back on its own.
        self.half_moon = 1      # index into (STOP, CHORALE, TREMOLO)
        self.pw_armed = {}      # channel -> is the wheel back near centre
        self.drive_step = {}    # part id -> quantised mod-wheel drive step
        self.amp_dirty = set()  # pids whose distortion partials are stale
        self.amp_job = None     # snapshot handed to the worker
        self.amp_out = None     # what it handed back
        self.amp_busy = False   # owned by the audio thread; see _amp_pump
        self.amp_go = threading.Event()
        self.amp_stop = False
        self.amp_err = None
        self.amp_calls = 0      # how many times the worker has run
        self.amp_thread = threading.Thread(target=self._amp_worker, daemon=True)
        self.amp_thread.start()
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
        # The swap is one assignment and safe here; letting go of the notes the
        # departing parts hold is NOT -- it pops from `live` while the callback
        # may be walking it -- so that part is asked for rather than done. The
        # order is deliberate: swap first, so nothing new is stamped for a part
        # that is going, then release a block later.
        self.parts = tuple(parts)

        def go(n0):
            for k in [k for k in list(self.slab.live) if k[0] not in keep]:
                self.slab.oneshot.pop(k, None)
                self.slab.release(k, n0)
        self.post(go)

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

    def post(self, fn):
        """Ask the audio thread to run `fn(n0)` at the next block boundary.

        For anything that touches the slab from the TUI. It is not about
        tearing a single value -- it is that `free`, `live`, `retiring` and
        `last_slots` are consistent only between one stamp and the next, and a
        second thread cannot see those boundaries.
        """
        with self.lock:
            self.cmds.append(fn)

    def release_part(self, pid):
        """Let go of everything a part is holding. Muting, from the TUI."""
        def go(n0):
            for k in [k for k in list(self.slab.live) if k[0] == pid]:
                self.slab.oneshot.pop(k, None)
                self.slab.release(k, n0)
            for p in self.parts:
                if p.pid == pid:
                    self._amp_touch(p)
        self.post(go)

    def panic(self):
        """All notes off, the one thing you want when something drones."""
        def go(n0):
            for k in list(self.slab.live):
                self.slab.oneshot.pop(k, None)
                self.slab.release(k, n0)
            self.down.clear()
            self.pedalled.clear()
            for p in self.parts:
                self._amp_touch(p)
        self.post(go)

    def request_stops(self, part, want):
        """set_stops from the TUI. Drawing a stop STAMPS, which is the single
        most dangerous thing another thread can do to the slab."""
        want = set(want)
        self.post(lambda n0: self.set_stops(part, want, n0))

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
        if self.cmds:
            with self.lock:
                cmds, self.cmds = self.cmds, collections.deque()
            for fn in cmds:
                try:
                    fn(n0)
                except Exception as e:
                    self.errors += 1
                    self.last_error = "cmd: %s: %s" % (type(e).__name__, e)
        if self.amp_dirty or self.amp_out is not None:
            try:
                self._amp_pump(n0)
            except Exception as e:
                self.errors += 1
                self.last_error = "amp: %s: %s" % (type(e).__name__, e)

    def _one(self, n0, msg):
        ch = msg.channel
        parts = self.parts
        if msg.type == "pitchwheel":
            # MIDI pitch bend is +/- 8192 over the wheel's range, which is
            # +/- bend_range semitones by convention.
            ratio = 2.0 ** (msg.pitch / 8192.0 * self.bend_range / 12.0)
            prev = self.bend.get(ch, 1.0)
            self.bend[ch] = ratio
            here = [p for p in parts if self._listens(p, ch)]
            rotors = [p for p in here if p.bank.leslie]
            if rotors:
                # ON A ROTOR PART THE WHEEL IS THE HALF-MOON, not a bend: see
                # PW_FIRE. A Hammond has no pitch bend to take away.
                self._half_moon(ch, msg.pitch)
            if prev != ratio:
                if rotors:
                    # A layered rig can have a Hammond and a lead on one
                    # channel, and only one of them has a reason to ignore the
                    # wheel -- so the rest still bend.
                    keep = {p.pid for p in here if not p.bank.leslie}
                    if keep:
                        self.slab.retune(self._sounding(ch, pids=keep), n0,
                                         om_scale=ratio / prev)
                else:
                    self.slab.retune(self._sounding(ch), n0, om_scale=ratio / prev)
        elif msg.type == "aftertouch":
            self.pressure[ch] = msg.value / 127.0
            for slots, tilt in self._press_groups(ch):
                self.slab.press(slots, self.pressure[ch], self.press_db, tilt)
        elif msg.type == "polytouch":
            for slots, tilt in self._press_groups(ch, note=msg.note):
                self.slab.press(slots, msg.value / 127.0, self.press_db, tilt)
        elif msg.type == "control_change":
            if msg.control == 1:
                self.cc1_count += 1; self.cc1_last = msg.value
                # THE MOD WHEEL IS A CRESCENDO PEDAL on an organ part and
                # VIBRATO on everything else, and with layers it can be both at
                # once -- so each part is asked separately rather than the whole
                # channel taking one branch.
                here = [p for p in parts if self._listens(p, ch)]
                amped = [p for p in here if p.bank.amp_drive > 0.0]
                organs = [p for p in here if p.organ and not p.bank.leslie]
                # AND ON A VOICE WITH A TREMOLO THE WHEEL IS THE DEPTH KNOB.
                # On a Rhodes suitcase and a Wurlitzer that is the one control
                # a player moves while playing, so it takes the wheel ahead of
                # the vibrato -- a tine cannot be given a pitch vibrato anyway,
                # since nothing about the instrument can bend it.
                tremmed = [p for p in here if p.bank.tremolo_depth > 0.0]
                # AND ON A CLAVINET THE WHEEL IS THE TONE ROCKERS. Four of the
                # six switches left of a D6's keyboard are the tone section, so
                # the wheel sweeps them darkest to brightest. It reaches notes
                # already sounding, which is what flipping a rocker does: the
                # filter is in the preamp, downstream of every ringing string.
                clavs = [p for p in here if p.bank.clav_panel]
                # AND ON A HONKY-TONK THE WHEEL IS HOW FAR OUT OF TUNE. Only the
                # pre-warmed positions exist, so it snaps between them rather
                # than sweeping -- a miss here would be a dropped note.
                detuners = [p for p in here if p.bank.detune_wheel]
                others = [p for p in here
                          if not p.organ and not p.bank.leslie
                          and p.bank.amp_drive <= 0.0
                          and p.bank.tremolo_depth <= 0.0
                          and not p.bank.clav_panel
                          and not p.bank.detune_wheel]
                if amped:
                    # THE WHEEL IS THE GAIN KNOB. On a Leslie it is the swell
                    # pedal, which sits in FRONT of a fixed-gain amplifier; on
                    # a guitar it is the amp's own gain. Either way it decides
                    # where the playing sits on the valve's curve -- and on a
                    # voice with an `amp_reference` how hard you play decides
                    # the rest. Gated on HAVING an amplifier, not on having a
                    # rotor: they were the same thing only because the Hammond
                    # was the first voice with one.
                    step = int(round(msg.value / 127.0 * LIVE_DRIVE_STEPS))
                    for p in amped:
                        if self.drive_step.get(p.pid) != step:
                            self.drive_step[p.pid] = step
                            self.amp_dirty.add(p.pid)
                for part in detuners:
                    self.detune_step[part.pid] = min(
                        DETUNE_STEPS, key=lambda v: abs(v - msg.value))
                for part in clavs:
                    import tonelib as _TLm
                    step = int(round(msg.value / 127.0 * (len(_TLm.CLAV_TONE) - 1)))
                    if self.clav_step.get(part.pid) != step:
                        self.clav_step[part.pid] = step
                        self.slab.clav_tone(step, self._sounding(ch, pids={part.pid}))
                for part in tremmed:
                    self.trem_depth[part.pid] = (msg.value / 127.0) * part.bank.tremolo_depth
                    self.slab.tremolo_arm(self._sounding(ch, pids={part.pid}),
                                          self.trem_depth[part.pid],
                                          part.bank.tremolo_stereo)
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
                # The amplifier's partials hang off a key with no channel, so
                # this sweep cannot see them -- but their parents are about to
                # go, so mark them stale and let the pump clear them.
                for p in parts:
                    self._amp_touch(p)
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
        # No speed in the key any more: the rotor is driven from the callback,
        # so one template plays at every speed and a note started during a ramp
        # simply joins the rotor where it is.
        _axis = (self.detune_step.get(part.pid, part.bank.leslie_default)
                 if part.bank.detune_wheel else part.bank.leslie_default)
        tmpl = part.bank.get(snote, vel, _axis)
        if tmpl is None:
            # Never build here: that is 1.4-10 ms on the audio thread. Silence,
            # counted, and the builder thread is what fixes it.
            self.misses += 1
            return
        # Timbre is quantised to the bucket, level is not: trim by the ratio
        # of the actual velocity to the one the bucket was built at.
        scale = ((vel / 127.0) ** 2 /
                 max((tmpl.get("vel", 127) / 127.0) ** 2, 1e-9)) * part.gain()
        self._amp_touch(part)
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
        cs = self.clav_step.get(part.pid)
        if cs is not None:
            # a note struck while the rockers are down joins them already set
            self.slab.clav_tone(cs, slots)
        d = self.trem_depth.get(part.pid, 0.0)
        if d > 0.0:
            self.slab.tremolo_arm(slots, d, part.bank.tremolo_stereo)
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
        self._amp_touch(part)
        if part.organ:
            for k in [k for k in list(self.slab.live)
                      if k[0] == part.pid and k[1] == ch and k[2] == note]:
                self.slab.release(k, n0)
        else:
            self.slab.release((part.pid, ch, note, None), n0)

    def _half_moon(self, ch, pitch):
        """Step the rotor ladder on a wheel flick. See PW_FIRE.

        Edge-triggered rather than positional, because the wheel springs back
        and a half-moon does not. Firing on the EDGE and re-arming on the
        return is what lets a sprung control hold a position it cannot hold.
        """
        import leslie as _LES
        ladder = (_LES.STOP, _LES.CHORALE, _LES.TREMOLO)
        f = pitch / 8192.0
        armed = self.pw_armed.get(ch, True)
        if armed and abs(f) >= PW_FIRE:
            self.pw_armed[ch] = False
            i = max(0, min(len(ladder) - 1,
                           self.half_moon + (1 if f > 0.0 else -1)))
            if i != self.half_moon:
                self.half_moon = i
                # AIMED, not set: the rotors spend real seconds getting there
                # and every note already sounding follows them, both in level
                # swing and in Doppler.
                self.rotor_horn.target = ladder[i]
                self.rotor_drum.target = ladder[i]
        elif not armed and abs(f) <= PW_REARM:
            self.pw_armed[ch] = True

    def _amp_touch(self, part):
        """Whatever just happened, this part's distortion no longer matches it.

        A product's parents are the chord, so any note on or off changes the
        whole set -- which is the same rule the offline path states as the
        lifetime of a product being the intersection of its parents'.
        """
        if part.bank.amp_drive > 0.0:
            self.amp_dirty.add(part.pid)

    def _amp_key(self, pid):
        # A uniform 4-tuple like every other key, with no channel and no note:
        # nothing that sweeps a channel should catch the amplifier by accident.
        return (pid, -1, -1, "amp")

    def _amp_worker(self):
        """Compute distortion off the audio thread; the callback stamps it.

        `apply` runs inside the PortAudio callback, where a 128-frame block at
        44.1 kHz is 2.9 ms, and one `tubeamp.emit` is about 7 even at the live
        setting. So the callback snapshots the chord, this does the arithmetic,
        and the callback places the answer a block or two later. A few
        milliseconds of lateness after a chord change is inaudible; an underrun
        on every chord change is not.
        """
        import tubeamp as _TA
        while not self.amp_stop:
            if not self.amp_go.wait(0.2):
                continue
            self.amp_go.clear()
            job = self.amp_job
            if self.amp_stop or job is None:
                continue
            pid, key, src, f, am, ph, drive, when, ref = job
            try:
                fc, ac, pc = _TA.combine(f, am, ph)
                out = _TA.emit(fc.tolist(), ac.tolist(), pc.tolist(),
                               float(self.rate), drive,
                               window_s=_TA.LIVE_WINDOW_S,
                               oversample=_TA.LIVE_OVERSAMPLE,
                               keep=_TA.LIVE_KEEP, reference=ref)
                self.amp_calls += 1
            except Exception as e:
                self.amp_err = "%s: %s" % (type(e).__name__, e)
                out = []
            self.amp_out = (pid, key, src, out)

    def _amp_snapshot(self, pid, n0):
        """What the worker needs, read on the audio thread so it cannot race."""
        part = next((p for p in self.parts if p.pid == pid), None)
        key = self._amp_key(pid)
        if part is None:
            self.slab.release(key, n0)
            return None
        # AN UNTOUCHED WHEEL MEANS THE VOICE AS VOICED, not silence. A guitar
        # patch has a drive because its amplifier is part of what it is, and
        # waiting for someone to find the mod wheel before it sounds right is
        # not a default. Once the wheel has been moved it owns the setting.
        step = self.drive_step.get(pid)
        drive = (part.bank.amp_drive if step is None else
                 part.bank.amp_drive * LIVE_DRIVE_RANGE
                 * step / float(LIVE_DRIVE_STEPS))
        slots = [sl for k, ss in self.slab.live.items()
                 if k[0] == pid and k[3] != "amp" for sl in ss]
        if drive <= 0.0 or len(slots) < 2:
            # Wheel down, or nothing left to intermodulate: the stage is clean.
            self.slab.release(key, n0)
            return None
        idx = np.fromiter(slots, np.int64, len(slots))
        # THE DIRECT SOUND ONLY. The room's copies are downstream of the
        # amplifier -- a reflection is what the room did to what the valve
        # already made, not another thing going into it -- and feeding them in
        # counts every partial twice. Measured on one key: 48 partials, 24
        # frequencies, each appearing at 257 samples of delay and again at 570.
        # combine() then summed each pair as one coherent parent, which
        # inflated the drive and put the distortion 5.4 dB ABOVE the signal
        # where the offline stage at the same drive puts it 3 dB under.
        #
        # Offline says this as `dr > 0.5`; live has no such column, so it is
        # the shortest path -- which is what "direct" means. Nothing reflected
        # can arrive sooner than the straight line.
        dl = (self.slab.a["delL"][idx].astype(np.float64)
              + self.slab.a["delR"][idx].astype(np.float64))
        idx = idx[dl <= dl.min() + 2.0]
        if len(idx) < 2:
            self.slab.release(key, n0)
            return None
        om = self.slab.a["om"][idx].astype(np.float64)
        f = om * float(self.rate) / (2.0 * np.pi)
        aM = 0.5 * (self.slab.aL0[idx].astype(np.float64)
                    + self.slab.aR0[idx].astype(np.float64))
        ph = self.slab.a["p0"][idx].astype(np.float64) + om * n0
        ok = np.flatnonzero((f > MIN_AMP_HZ) & (aM > 0.0))
        if len(ok) < 2:
            self.slab.release(key, n0)
            return None
        src = int(idx[ok[int(np.argmax(aM[ok]))]])
        return (pid, key, src, f[ok], aM[ok], ph[ok], drive, n0,
                getattr(part.bank, 'amp_reference', None))

    def _amp_place(self, n0, pid, key, src, out):
        """Stamp what the worker returned. Cheap: no transform, just writes."""
        self.slab.release(key, n0)
        if not out or not self.slab.busy[src]:
            return
        f = [p[0] for p in out]
        a = [p[1] for p in out]
        p = [p[2] for p in out]
        part = next((q for q in self.parts if q.pid == pid), None)
        cab = getattr(part.bank, "cabinet", None) if part else None
        if cab:
            # THROUGH THE SPEAKER, like everything else this voice makes. The
            # note templates were cabineted at build time; these products were
            # not, because they did not exist yet.
            import cabinet as _CB
            g = _CB.get(cab).gain(np.asarray(f, float))
            a = (np.asarray(a, float) * g).tolist()
        slots = self.slab.stamp_amp(key, src, f, a, p, n0, self.rate)
        if slots and self.slab.ls_on[src]:
            # The amplifier is UPSTREAM of the rotor, so its products swing and
            # Doppler like anything else that came out of the cabinet.
            self.slab.leslie_arm(slots, float(self.slab.ls_ph[src]), f, n0,
                                 self.rotor_horn.rate, self.rotor_drum.rate)

    def _amp_pump(self, n0):
        out = self.amp_out
        if out is not None:
            self.amp_out = None
            self.amp_busy = False
            self._amp_place(n0, *out)
        if self.amp_dirty and not self.amp_busy:
            job = self._amp_snapshot(self.amp_dirty.pop(), n0)
            if job is not None:
                self.amp_job = job
                self.amp_busy = True
                self.amp_go.set()

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
        # A drawbar IS a parent, so the amplifier's products are now wrong --
        # drawing all nine bars changes what is intermodulating with what.
        self._amp_touch(part)

    def _draw(self, part, tmpl, ch, note, rank, n0):
        got = tmpl.get("ranks", {}).get(rank)
        if not got:
            return
        cols, n, hrel = got
        key = (part.pid, ch, note, rank)
        if not self.slab.stamp_cols(cols, n, key, n0,
                                    part.gain(), hrel, 0, False):
            self.dropped += 1
            return
        if part.bank.leslie:
            self.slab.leslie_arm(self.slab.last_slots, cols["az"], cols["nf"],
                                 n0, self.rotor_horn.rate, self.rotor_drum.rate)

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

        NOT THE AMPLIFIER, WHICH IS NOT A NOTE. Its key carries no channel and
        no note by design -- nothing that sweeps a channel should catch it --
        and the price of that is that this test cannot be applied to it: there
        is no key down to look for, so it was released on EVERY BLOCK, the
        instant after it was stamped. That is audible as a click each time the
        mod wheel moves and no change in the sound, because the products never
        lived long enough to sound. The amplifier's lifetime is its parents',
        and _amp_touch is what keeps it honest.
        """
        for k in [k for k in list(self.slab.live)
                  if k[3] != "amp"
                  and (k[1], k[2]) not in self.down
                  and (k[1], k[2]) not in self.pedalled
                  and not self.slab.oneshot.get(k)]:
            self.slab.release(k, n)
            self.stuck += 1

    def _press_groups(self, ch, note=None):
        """Sounding slots on this channel, grouped by how much their voice
        BRIGHTENS under aftertouch. Usually one or two groups.

        Per NOTE, not per part, because SOLO_SPLIT means one part can be two
        instruments: a clarinet patch is a bass clarinet below D3, and the two
        do not open up by the same amount.
        """
        groups = {}
        for k, slots in self.slab.live.items():
            if k[1] != ch:
                continue
            if note is not None and k[2] != note:
                continue
            groups.setdefault(self._press_tilt(k[0], k[2]), []).extend(slots)
        return [(v, t) for t, v in groups.items()]

    def _press_tilt(self, pid, note):
        """How much this voice brightens per unit of aftertouch. MEASURED.

        Slab.press scales each partial by (f/f0)^(tilt*p), which is 6.02*tilt dB
        per doubling of harmonic at full pressure, against press_db of level --
        so 6.02*tilt/press_db is exactly the quantity measured on the Iowa
        recordings across pp/mf/ff:

            tenor trombone  +0.68 dB of tilt per dB of level
            French horn     +0.44
            Bb clarinet     +0.13

        One global press_tilt of 0.30 made that ratio 0.226 for every voice --
        less than half a trombone's and nearly double a clarinet's. Leaning on a
        brass note should open it far more than leaning on a clarinet, and the
        difference is most of what makes brass sound like brass.

        Voices with no measurement keep the old constant rather than losing the
        effect: effort_tilt is 0.0 until someone measures that family, and 0.0
        here would mean aftertouch stopped colouring them at all.
        """
        for p in self.parts:
            if p.pid != pid:
                continue
            try:
                et = getattr(p.bank._voice_class(note), "effort_tilt", 0.0)
            except Exception:
                return self.press_tilt
            return (et * self.press_db / 6.0206) if et else self.press_tilt
        return self.press_tilt

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
            if self.slab.tr_on.any():
                # ONE RATE, from an absolute clock, so a held chord and a note
                # struck mid-swing are at the same place in the cycle. Both
                # electric pianos modulate at 5.5 Hz; if a voice ever wants its
                # own rate this has to become per-row, as ls_ph is.
                hz = next((p.bank.tremolo_hz for p in self.parts
                           if p.bank.tremolo_depth > 0.0), 0.0)
                if hz > 0.0:
                    self.slab.tremolo_swing(2.0 * math.pi * hz * n0 / float(self.rate))
            if self.slab.ls_on.any():
                dt = frame_count / float(self.rate)
                ah = self.rotor_horn.advance(dt)
                ad = self.rotor_drum.advance(dt)
                # The level swing is free to recompute, so it happens every
                # block. The Doppler is not -- retune() rewrites phase anchors
                # -- so it moves only when the rate has actually gone
                # somewhere, which is never once the rotor has settled.
                self.slab.leslie_swing(ah, ad)
                if abs(self.rotor_horn.rate - self._ls_rate) > 0.05:
                    self.slab.leslie_doppler(n0, self.rotor_horn.rate,
                                             self.rotor_drum.rate)
                    self._ls_rate = self.rotor_horn.rate
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
        # A COPY BEFORE THE SCAN, because this runs on the TUI thread while the
        # audio thread is stamping and reaping. np.flatnonzero COUNTS the set
        # bits, allocates a result of exactly that size, and then fills it -- so
        # if the audio thread clears a bit in between, fewer indices are written
        # than were allocated and THE TAIL OF THE RESULT IS UNINITIALISED HEAP.
        # That is where "index 136912427831408 is out of bounds for axis 0 with
        # size 16384" came from: a pointer, read as a slot number. The number
        # looks like nonsense and is in fact an address.
        #
        # One memcpy makes the count and the fill see the same array. The answer
        # can be a block out of date, which for a meter is nothing. This got far
        # more likely when the mod wheel became the amplifier's drive, because
        # moving it now churns 150 slots.
        idx = np.flatnonzero(sl.busy.copy())
        if not len(idx):
            return None
        vd = sl.a["vd"][idx].astype(np.float64)
        vr = sl.a["vr"][idx].astype(np.float64)
        cents = np.log2(np.maximum(1.0 + vd, 1e-9)) * 1200.0
        w = max(self.modw.values()) if self.modw else 0.0
        return dict(wheel=w, cents_lo=float(cents.min()), cents_hi=float(cents.max()),
                    rate_lo=float(vr.min()), rate_hi=float(vr.max()),
                    cc1=self.cc1_count, cc1_last=self.cc1_last)

    def _sounding_count(self):
        """How many slots are held, counted without tripping over the writer.

        Same thread problem as wheel_state: `live` is a dict the audio thread
        adds to and pops from, and iterating it from the TUI can raise
        "dictionary changed size during iteration". Retry once, then fall back
        to the free list, which is a single deque length and cannot tear.
        """
        for _ in range(3):
            try:
                return sum(len(v) for v in list(self.slab.live.values()))
            except RuntimeError:
                pass
        return self.slab.cap - len(self.slab.free)

    def stats(self):
        return dict(t=self.n / self.rate, peak=self.peak,
                    last_peak=self.last_peak,
                    sounding=self._sounding_count(),
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
    tpl = lv.parts[0].bank.get(60, 100)
    tb, nf = tpl["tbav"], tpl["nf"]
    # Count by FREQUENCY, not by row. A mode occupies more than one row because
    # the room's reflections ride along with it -- a trumpet's 32 modes are 64
    # rows -- and the fundamental's rows carry zero by construction, since
    # mode_lock_offset_for() is an offset FROM the fundamental. Counting rows
    # asserted "at most one zero", which was true only before the reflections
    # were in the template.
    up = nf > nf.min() * 1.5
    check("a trumpet's partials do carry a mode-lock term",
          int((tb[up] != 0).sum()) == int(up.sum()),
          "  (%d of %d above the fundamental)" % (int((tb[up] != 0).sum()), int(up.sum())))
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

    # ---- the Hammond's two wheels ------------------------------------------
    # A Hammond has no pitch bend and no mod wheel, so both are free for the
    # controls it does have: the half-moon switch and the swell pedal.
    import leslie as _LES
    lv = Live(program=18, rate=44100, frames=128, verbose=False); lv.warm()
    pid = lv.parts[0].pid

    def flick(v):
        lv.on_midi(mido.Message("pitchwheel", channel=0, pitch=int(v * 8191)))
        lv.apply(lv.n)

    def settle(limit=150):
        # A REAL BLOCK, not just apply(): sweep() is what the callback does
        # next, and a version of this that left it out passed while the
        # amplifier was being swept away the instant it was stamped.
        for _ in range(limit):
            time.sleep(0.005)
            lv.apply(lv.n); lv.sweep(lv.n); lv.slab.reap(lv.n)
            lv.n += 128
            if not lv.amp_busy and lv.amp_out is None:
                return True
        return False

    check("the rotor starts on chorale", lv.rotor_horn.target == _LES.CHORALE)
    flick(1.0)
    check("a flick up steps to tremolo", lv.rotor_horn.target == _LES.TREMOLO)
    # HELD, not sprung back with the wheel: that is the whole point of reading
    # edges rather than the position of a control that cannot stay put.
    flick(0.0)
    check("...and holds when the wheel springs back",
          lv.rotor_horn.target == _LES.TREMOLO)
    flick(1.0); flick(0.0)
    check("...and cannot be pushed past the top",
          lv.rotor_horn.target == _LES.TREMOLO and lv.half_moon == 2)
    flick(-1.0); flick(0.0)
    check("a flick down steps back to chorale",
          lv.rotor_horn.target == _LES.CHORALE)
    flick(-1.0); flick(0.0)
    check("...and again to stop", lv.rotor_horn.target == _LES.STOP)
    flick(-1.0); flick(0.0)
    check("...and cannot be pushed below it",
          lv.rotor_horn.target == _LES.STOP and lv.half_moon == 0)
    # A wheel left leaning on the threshold must not machine-gun the ladder.
    flick(1.0)
    for _ in range(20):
        flick(PW_FIRE + 0.02)
    check("a wheel resting on the threshold steps once, not twenty",
          lv.half_moon == 1, "  (half_moon %d)" % lv.half_moon)

    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
    lv.apply(lv.n)
    ix = np.flatnonzero(lv.slab.busy)
    om0 = lv.slab.a["om"][ix].copy()
    flick(1.0); flick(0.0)
    check("the wheel does not BEND a Hammond",
          np.allclose(om0, lv.slab.a["om"][ix]))

    # ---- the mod wheel is the swell pedal ----------------------------------
    key = lv._amp_key(pid)
    lv.on_midi(mido.Message("control_change", channel=0, control=1, value=0))
    lv.apply(lv.n); settle()
    check("wheel down: the stage is clean", not lv.slab.live.get(key))
    lv.on_midi(mido.Message("control_change", channel=0, control=1, value=127))
    lv.apply(lv.n)
    drove = settle()
    one = len(lv.slab.live.get(key, []))
    check("wheel up: the stage distorts", drove and one > 0, "  (%d partials)" % one)
    # THE BUG THIS EXISTS FOR. sweep() releases anything whose key is not
    # down, and the amplifier's key carries no note -- so it was released on
    # every block, the instant after it was stamped. Audible as a click each
    # time the wheel moved and no change in the sound. A test that called
    # apply() without sweep() could not see it.
    was_stuck = lv.stuck
    for _ in range(60):
        lv.apply(lv.n); lv.sweep(lv.n); lv.slab.reap(lv.n); lv.n += 128
    held = len(lv.slab.live.get(key, []))
    check("...and survives the sweep, block after block",
          held == one and lv.stuck == was_stuck,
          "  (%d of %d partials, %d swept)" % (held, one, lv.stuck - was_stuck))
    # A PRODUCT NEEDS TWO PARENTS, so a chord must make more of them than a
    # single key -- even though a Hammond key is already several tonewheels.
    for nn in (64, 67, 72):
        lv.on_midi(mido.Message("note_on", channel=0, note=nn, velocity=100))
    lv.apply(lv.n); settle()
    many = len(lv.slab.live.get(key, []))
    check("a chord makes more distortion than one key", many > one,
          "  (%d vs %d partials)" % (many, one))
    # The products die with the chord that made them: their lifetime is the
    # intersection of their parents', which with nothing sounding is nothing.
    lv.on_midi(mido.Message("control_change", channel=0, control=123, value=0))
    lv.apply(lv.n); lv.down.clear(); lv.pedalled.clear()
    settle()
    check("silence leaves no distortion behind", not lv.slab.live.get(key),
          "  (%d partials)" % len(lv.slab.live.get(key, [])))
    check("the amplifier raised no errors",
          lv.errors == 0 and lv.amp_err is None,
          "" if lv.errors == 0 else "  (%s)" % lv.last_error)
    # The worker exists because `apply` runs in the audio callback: a block at
    # 44.1 kHz is 2.9 ms and one emit is about 7.
    check("the distortion was computed off the audio thread", lv.amp_calls > 0,
          "  (%d runs)" % lv.amp_calls)

    # ---- a note started on a SETTLED rotor joins it at its speed ------------
    # leslie_arm writes the Doppler at FAST_HZ as a unit, and the callback only
    # rescales when the rate MOVES -- so on a settled chorale a new note kept a
    # 6.6 Hz wobble while the held ones turned at 0.8, and changing speed
    # snapped them together. Ben heard it as half the sound spinning fast.
    lv.panic(); lv.apply(lv.n); settle()
    lv.rotor_horn.rate = lv.rotor_horn.target = _LES.CHORALE
    lv.rotor_drum.rate = lv.rotor_drum.target = _LES.CHORALE
    lv._ls_rate = _LES.CHORALE
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
    lv.apply(lv.n); lv.down.add((0, 60))
    fresh = np.array([sl for k in lv.slab.live if k[2] == 60
                      for sl in lv.slab.live[k]], dtype=int)
    vr = np.unique(np.round(lv.slab.a["vr"][fresh], 3)) if len(fresh) else np.array([])
    # the drum turns at DRUM_RATIO of the horn, so two rates are correct here;
    # what is not correct is FAST_HZ, which is nobody's speed at chorale.
    check("a note started on a settled rotor joins it, not the reference",
          len(vr) > 0 and float(np.abs(vr).max()) < _LES.FAST_HZ * 0.5,
          "  (vr %s, FAST_HZ %.2f)" % (vr, _LES.FAST_HZ))
    lv.panic(); lv.apply(lv.n); settle()
    lv.down.clear()

    # ---- the TUI asks; the callback does -----------------------------------
    # The slab has one writer by design. Every path that lets the TUI thread
    # stamp or release goes through post(), and the test is that the work has
    # NOT happened when the call returns and HAS after a block.
    for nn in (60, 64, 67):
        lv.on_midi(mido.Message("note_on", channel=0, note=nn, velocity=100))
    lv.apply(lv.n)
    lv.down.update((0, nn) for nn in (60, 64, 67))
    before = len(lv.slab.live)
    lv.panic()
    check("panic does not touch the slab from the caller's thread",
          len(lv.slab.live) == before and len(lv.cmds) == 1,
          "  (%d keys, %d queued)" % (len(lv.slab.live), len(lv.cmds)))
    lv.apply(lv.n)
    check("...and the callback carries it out",
          len(lv.slab.live) == 0 and not lv.down and not lv.cmds,
          "  (%d keys)" % len(lv.slab.live))

    # Drawing a stop STAMPS, which is the one that could hand the callback's
    # own _draw a set of slots belonging to something else.
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
    lv.apply(lv.n); lv.down.add((0, 60))
    was = set(lv.parts[0].drawn)
    want = set(lv.parts[0].bank.rank_names)
    lv.request_stops(lv.parts[0], want)
    check("drawing a stop is deferred too",
          lv.parts[0].drawn == was and len(lv.cmds) == 1)
    lv.apply(lv.n)
    check("...and all nine bars come out on the callback",
          lv.parts[0].drawn == want and not lv.cmds,
          "  (%d ranks)" % len(lv.parts[0].drawn))
    # and the amplifier notices, because a drawbar is a parent
    check("...and the amplifier knows its parents changed",
          lv.parts[0].pid in lv.amp_dirty or lv.amp_busy or lv.amp_out is not None)
    lv.panic(); lv.apply(lv.n); settle()

    # ---- the meter is read from ANOTHER THREAD ------------------------------
    # np.flatnonzero counts the set bits, allocates a result of that size and
    # then fills it. A concurrent reap clearing a bit in between leaves the
    # tail of the result uninitialised -- heap, read as slot numbers. It
    # reached Ben as "index 136912427831408 is out of bounds for axis 0 with
    # size 16384", which is an address, and it got likely when the mod wheel
    # became the drive and started churning 150 slots per move.
    was = lv.slab.busy.copy()
    stop = []
    def churn():
        rng = np.random.default_rng(3)
        while not stop:
            k = rng.integers(0, lv.slab.cap, 3000)
            lv.slab.busy[k] = False
            lv.slab.busy[k] = True
    th = threading.Thread(target=churn, daemon=True)
    th.start()
    bad = None
    try:
        for _ in range(3000):
            lv.wheel_state()
            lv.stats()
    except Exception as e:
        bad = "%s: %s" % (type(e).__name__, e)
    stop.append(1); th.join(timeout=2.0)
    lv.slab.busy[:] = was
    check("the meter survives being read while the slab churns", bad is None,
          "" if bad is None else "  (%s)" % bad)
    lv.amp_stop = True; lv.amp_go.set()
    lv.renderer.close()

    # ---- the electric guitar ------------------------------------------------
    # Same amplifier, different instrument, and the differences are the point:
    # a guitar BENDS, its wheel is the gain knob rather than a swell pedal, and
    # its products have to go through a speaker that the note templates already
    # went through at build time.
    gv = Live(program=27, rate=44100, frames=128, verbose=False); gv.warm()
    gp = gv.parts[0]

    def gblock():
        n = gv.n
        gv.apply(n); gv.sweep(n); gv.slab.reap(n)
        gv.n = n + 128

    def gsettle(limit=200):
        for _ in range(limit):
            time.sleep(0.004); gblock()
            if not gv.amp_busy and gv.amp_out is None:
                return True
        return False

    check("the guitar has an amplifier and a speaker",
          gp.bank.amp_drive > 0.0 and gp.bank.cabinet
          and gp.bank.amp_reference, "  (%s, drive %.2f, ref %s)"
          % (gp.bank.cabinet, gp.bank.amp_drive, gp.bank.amp_reference))
    gkey = gv._amp_key(gp.pid)
    for nn in (40, 47, 52, 55):
        gv.on_midi(mido.Message("note_on", channel=0, note=nn, velocity=110))
        gv.down.add((0, nn))
    gblock(); gsettle()
    n_default = len(gv.slab.live.get(gkey, []))
    check("an untouched wheel already gives the voice its own drive",
          n_default > 0, "  (%d partials)" % n_default)

    # A GUITAR BENDS. The half-moon ladder is gated on `leslie`, so this is the
    # behaviour a guitar gets for free -- and it would be very wrong to lose.
    ix = np.flatnonzero(gv.slab.busy)
    om0 = gv.slab.a["om"][ix].copy()
    gv.on_midi(mido.Message("pitchwheel", channel=0, pitch=8191)); gblock()
    bent = float(np.max(np.abs(gv.slab.a["om"][ix] / np.maximum(om0, 1e-12) - 1.0)))
    check("the wheel DOES bend a guitar", bent > 0.01,
          "  (%.1f cents)" % (1200.0 * math.log2(1.0 + bent)))
    gv.on_midi(mido.Message("pitchwheel", channel=0, pitch=0)); gblock()
    check("...and the rotor ladder did not move, since a guitar has no rotor",
          gv.half_moon == 1)

    # THE PRODUCTS GO THROUGH THE SPEAKER. The templates were cabineted when
    # they were built; these partials did not exist then, so _amp_place has to
    # do it. Without that, everything the amplifier makes above 5 kHz arrives
    # at full level, which is the difference between overdrive and a wasp.
    # THE SAME PAYLOAD PLACED TWICE, once with the speaker and once without.
    # Measuring it by recomputing instead does not work and the reason is worth
    # keeping: the chord is DECAYING, so a recompute a moment later is a
    # different chord, and two identical passes measured 1.375% and 0.831%.
    # Holding the payload fixed is the only way the speaker is the variable.
    probe = [(400.0, 1.0, 0.0), (8000.0, 1.0, 0.0)]
    gsrc = int(np.flatnonzero(gv.slab.busy)[0])

    def _place_probe():
        gv._amp_place(gv.n, gp.pid, gkey, gsrc, probe)
        sl = gv.slab.live.get(gkey, [])
        i = np.fromiter(sl, np.int64, len(sl))
        f = gv.slab.a["nf"][i]
        a = gv.slab.aL0[i].astype(np.float64)
        lo = a[np.argmin(np.abs(f - 400.0))]
        hi = a[np.argmin(np.abs(f - 8000.0))]
        return 20.0 * math.log10(max(hi, 1e-30) / max(lo, 1e-30))

    got = _place_probe()
    gp.bank.cabinet = None
    flat = _place_probe()
    gp.bank.cabinet = "guitar12"
    import cabinet as _CBT
    want = float(_CBT.get("guitar12").response_db([8000.0])[0]
                 - _CBT.get("guitar12").response_db([400.0])[0])
    check("the amplifier's products go through the speaker",
          abs(flat) < 0.1 and abs(got - want) < 0.5,
          "  (8 kHz vs 400 Hz: %+.1f dB placed, %+.1f dB the cabinet says,"
          " %+.1f dB with no cabinet)" % (got, want, flat))
    gv.slab.release(gkey, gv.n)

    gv.on_midi(mido.Message("control_change", channel=0, control=1, value=0))
    gblock(); gsettle()
    check("wheel down is clean on a guitar too",
          not gv.slab.live.get(gkey), "  (%d partials)" % len(gv.slab.live.get(gkey, [])))
    # BUILDING A BANK MUST BE SILENT AND MUST NOT BAKE THE AMPLIFIER IN.
    # prepare() reports what its passes did, which is right for a render and is
    # corruption for a curses screen; and an amplifier baked into a one-note
    # template is counted twice and then read back as a parent. This was done
    # for Leslie voices only, so a guitar -- which has an amplifier and is not
    # a Leslie voice -- took the other branch: 527 partials a template instead
    # of 128, and a line of log per note into the TUI.
    import io as _io, contextlib as _ctx
    import tubeamp as _TAG
    _buf = _io.StringIO()
    with _ctx.redirect_stdout(_buf):
        _gq = Live(program=29, rate=44100, frames=128, verbose=False)
        _gq.warm()
    check("building an amplified bank says nothing to the terminal",
          _buf.getvalue().strip() == "",
          "" if not _buf.getvalue().strip() else
          "  (%d chars leaked)" % len(_buf.getvalue()))
    check("...and leaves the offline amplifier pass switched back on",
          _TAG.ENABLED is True)
    _tq = _gq.parts[0].bank.get(52, 110)
    check("...and bakes no distortion into the template",
          _tq is not None and _tq["P"] < 200,
          "  (%s partials for one note)" % (None if _tq is None else _tq["P"]))
    _gq.amp_stop = True; _gq.amp_go.set(); _gq.renderer.close()

    check("the guitar raised no errors", gv.errors == 0 and gv.amp_err is None,
          "" if gv.errors == 0 else "  (%s)" % gv.last_error)
    gv.amp_stop = True; gv.amp_go.set(); gv.renderer.close()

    # ---- the rest of the family ---------------------------------------------
    # Cheap, because these are one instrument with the pickup moved, the palm
    # put down or the gain turned up -- so what is worth guarding is that the
    # relationships between them survive, not that each renders.
    fam = [(26, _T.JazzGuitarProperties), (27, _T.ElectricGuitarProperties),
           (28, _T.MutedGuitarProperties), (29, _T.OverdrivenGuitarProperties),
           (30, _T.DistortionGuitarProperties), (31, _T.GuitarHarmonicsProperties)]
    import math as _math
    import patch_map as _PM
    check("all six electrics are wired to their GM programs",
          all(_PM.property_class_for_program(n) is c for n, c in fam))
    inst = {n: c(329.63, 0.0, 1.0, 1.0) for n, c in fam}
    check("drive rises clean -> overdriven -> distortion",
          inst[27].amp_drive < inst[29].amp_drive < inst[30].amp_drive,
          "  (%.2f < %.2f < %.2f)" % (inst[27].amp_drive, inst[29].amp_drive,
                                      inst[30].amp_drive))
    # A PALM MUTE IS A DAMPER, so it has to be a decay and not a filter.
    check("the muted voice damps, and by an order of magnitude",
          inst[28].harmonic_decay(1) > 10.0 * inst[27].harmonic_decay(1),
          "  (%.1f vs %.1f dB/s)" % (inst[28].harmonic_decay(1),
                                     inst[27].harmonic_decay(1)))

    def _h1_share(g):
        v = np.array([g.harmonic_volume(h) for h in range(1, 33)])
        return float(v[0] ** 2 / max((v ** 2).sum(), 1e-30))
    # A touched node DELETES modes where a comb only weights them.
    check("a touched harmonic is far purer than an open string",
          _h1_share(inst[31]) > 2.0 * _h1_share(inst[27]),
          "  (h1 carries %.0f%% vs %.0f%%)"
          % (100 * _h1_share(inst[31]), 100 * _h1_share(inst[27])))
    # A neck humbucker nulls h4/h8/h12 at once; a bridge one waits until h16.
    def _bright(g):
        v = np.array([g.harmonic_volume(h) for h in range(1, 25)])
        return float((np.arange(1, 25) * v ** 2).sum() / max((v ** 2).sum(), 1e-30))
    # ---- category errors in the GM map --------------------------------------
    # Programs that had fallen through _fill to a struck BAR when this file
    # already contained the voice that models them, fitted for the drum kit and
    # reachable from a melodic channel like any other. 115 Woodblock had been
    # pointed at one long ago; its neighbours were left behind.
    for _p, _c in ((15, _T.HammeredDulcimerProperties),
                   (112, _T.CrotaleProperties), (113, _T.AgogoProperties),
                   (116, _T.MembraneDrumProperties), (117, _T.TomTomProperties),
                   (126, _T.ApplauseProperties)):
        if _PM.property_class_for_program(_p) is not _c:
            break
    else:
        _p = None
    check("the six category errors point at the right voice now", _p is None,
          "" if _p is None else "  (GM %d is %s)"
          % (_p, _PM.property_class_for_program(_p).__name__))

    def _mh(c, f0=220.0, top=17):
        g = c(f0, 0.0, 1.0, 1.0)
        e = np.array([g.harmonic_volume(h) for h in range(1, top)]) ** 2
        return float((np.arange(1, top) * e).sum() / max(e.sum(), 1e-30))
    # A DRUM THUMPS; A BAR RINGS. That is the audible content of the error.
    _bar = _T.MalletProperties(220.0, 0.0, 1.0, 1.0)
    _drum = _T.TomTomProperties(220.0, 0.0, 1.0, 1.0)
    check("a melodic tom now thumps instead of ringing",
          _drum.harmonic_decay(1) > 10.0 * _bar.harmonic_decay(1),
          "  (%.0f vs %.0f dB/s)" % (_drum.harmonic_decay(1), _bar.harmonic_decay(1)))
    check("applause is noise, not a tuned bar",
          _mh(_T.ApplauseProperties) > 3.0 * _mh(_T.MalletProperties),
          "  (mean harmonic %.1f vs %.1f)"
          % (_mh(_T.ApplauseProperties), _mh(_T.MalletProperties)))
    # STRUCK, NOT PLUCKED: the hierarchy's whole distinction. A struck voice
    # names its strike point; the generic plucked base has none.
    check("a hammered dulcimer is struck, not plucked",
          _T.HammeredDulcimerProperties.strike_point is not None
          and _T.PluckedStringProperties.strike_point is None
          and _T.HammeredDulcimerProperties.strike_fills_with_force is False,
          "  (struck at 1/%.0f, and a wooden hammer does not fill its notch)"
          % (1.0 / _T.HammeredDulcimerProperties.strike_point))

    # ---- the steelpan, which is ASSERTED and must say so ---------------------
    # 1 : 2 : 3 is the panmaker's tuning and the reason the instrument is
    # pitched at all. If that stops being exact, the voice has stopped being a
    # steelpan and become a bell.
    _sp = _T.SteelPanProperties(261.63, 0.0, 1.0, 1.0)
    check("a steelpan's first three modes are tuned to 1:2:3",
          abs(_sp.mode_ratio(1) - 1.0) < 1e-9
          and abs(_sp.mode_ratio(2) - 2.0) < 1e-9
          and abs(_sp.mode_ratio(3) - 3.0) < 1e-9,
          "  (%.3f, %.3f, %.3f)" % tuple(_sp.mode_ratio(m) for m in (1, 2, 3)))
    # ...and the ones above are NOT tuned, deliberately: nobody hammers them,
    # so they shimmer rather than reinforce. Integers up there would be an
    # invention, and a tidier-looking one than the truth.
    _up = [_sp.mode_ratio(m) for m in range(4, 10)]
    check("...and the modes above them are deliberately not",
          all(abs(r - round(r)) > 0.05 for r in _up),
          "  (%s)" % ", ".join("%.2f" % r for r in _up))
    # MEASURED, and the reverse of what this class first asserted: the tuned
    # modes are exactly where the maker put them and they are QUIET. Octave
    # 29 dB down, twelfth 37, on 26 single-note strikes with the fundamental
    # strongest in 20 of 20.
    _d2 = -20 * math.log10(_sp.harmonic_volume(2) / _sp.harmonic_volume(1))
    _d3 = -20 * math.log10(_sp.harmonic_volume(3) / _sp.harmonic_volume(1))
    check("the fundamental dominates, as the recording says it does",
          20.0 < _d2 < 38.0 and _d2 < _d3,
          "  (octave %.0f dB down, twelfth %.0f)" % (_d2, _d3))
    # A MEASURED MODE SET MUST NOT ALSO BE STRETCHED. The steelpan was built on
    # MetalPercussionProperties, which carries a stiffness term because ITS
    # voices have no mode set -- so the pan's carefully tuned 1:2:3 rendered at
    # 1.000, 2.078, 3.310, the octave 66 cents sharp, while a selftest that
    # checked mode_ratio() reported it perfect. mode_ratio is the INTENT; the
    # stretch happens downstream of it. Every mode_ratios voice in the file
    # must zero the coefficient, and now something checks.
    _stretched = []
    for _n in dir(_T):
        _c = getattr(_T, _n)
        if not (isinstance(_c, type) and _n.endswith('Properties')):
            continue
        if getattr(_c, 'mode_ratios', None) is None:
            continue
        if getattr(_c, 'inharmonicity_coefficient', 0.0):
            _stretched.append(_n)
    check("a voice with a measured mode set is not also stretched",
          not _stretched, "  (%s)" % ", ".join(_stretched))

    check("GM 114 is a pan and no longer a bar",
          _PM.property_class_for_program(114) is _T.SteelPanProperties)
    # SYMPATHETIC RESONANCE. A pan is one sheet of steel, so its coupling is a
    # mechanical kick and not resonance -- and the distance that matters is
    # distance round the CYCLE OF FIFTHS, which is how the areas are laid out.
    check("the pan couples by contact, not coincidence",
          _T.SteelPanProperties.sympathetic_mode == 'contact'
          and _T.SteelPanProperties.sympathetic_gain > 0)
    _bd = _T.body_distance
    check("...and a fifth is nearer than a semitone, across the steel",
          _bd(7, _T.SteelPanProperties) < _bd(1, _T.SteelPanProperties),
          "  (P5 %.1f steps, m2 %.1f)" % (_bd(7, _T.SteelPanProperties),
                                          _bd(1, _T.SteelPanProperties)))
    import sympathetic as _SY
    _r = _SY.responders(_sp)
    check("...and a struck note brings its neighbours with it",
          len(_r) > 0 and all(abs(s) % 12 in (0, 2, 5, 7, 10) for s, _ in _r[:6]),
          "  (%s)" % ", ".join("%+d" % s for s, _ in _r[:6]))

    # ---- the sitar, and what its strings need in order to ring ---------------
    check("GM 104 is a sitar, with strings under the frets",
          _PM.property_class_for_program(104) is _T.SitarProperties
          and len(_T.SitarProperties.sympathetic_strings) == 13
          and _T.SitarProperties.sympathetic_mode == 'coincidence')
    _si = _T.SitarProperties(277.18, 0.0, 1.0, 1.0)
    # Q COMES FROM THE DECAY, so an unphysical ring makes an unphysical
    # resonance: at the first draft's 0.8 dB/s the modes were Q 12000 and
    # nothing could couple to anything.
    check("...and it rings for seconds, not half a minute",
          3.0 < 40.0 / _si.harmonic_decay(1) < 15.0,
          "  (%.1f s to fall 40 dB)" % (40.0 / _si.harmonic_decay(1)))

    # THE PREDICTION, AND IT IS A LARGE ONE. Coincidence needs the driver's
    # partial to land INSIDE the responder's resonance, which at Q 2800 is a
    # fraction of a cent wide. An equal-tempered fifth is two cents narrow of a
    # just one, so it misses. Sympathetic strings therefore ring in just
    # intonation and are near silent in equal temperament -- which is not a
    # defect, it is why the instruments that have them belong to musics that
    # do not temper.
    import blockrender as _BR, sympathetic as _SY
    _c = {}
    for _tn in ('even', 'just'):
        _F = _BR.tuning_table(_tn)
        _vals = []
        for _n in (61, 63, 65, 68, 70):
            _d = _T.SitarProperties(_F[_n], 0.0, 1.0, 1.0)
            _vals.append(_SY._coupling(_d, _T.SitarProperties(_F[_n - 7], 0.0, 1.0, 1.0), 1.0))
        _c[_tn] = sorted(_vals)[len(_vals) // 2]
    check("the taraf ring in just intonation and not in equal",
          _c['just'] > 20.0 * _c['even'],
          "  (coupling %.4f just, %.4f even -- %.0f dB apart)"
          % (_c['just'], _c['even'], 20 * math.log10(_c['just'] / max(_c['even'], 1e-9))))
    # ...and end to end, which is the test that caught the responders being
    # placed at EQUAL-tempered offsets from the driver instead of at their own
    # tuned pitches. With that bug only the octave ever coincided, so the just
    # tuner bought nothing but a louder octave.
    _cnt = {}
    for _tn in ('even', 'just'):
        _F = _BR.tuning_table(_tn)
        _cnt[_tn] = sum(len(_SY.responders(_T.SitarProperties(_F[_n], 0.0, 1.0, 1.0), _F))
                        for _n in (60, 62, 64, 65, 67, 69))
    check("...and it is the fifths and fourths, not just the octaves",
          _cnt['just'] > 3 * _cnt['even'],
          "  (%d responders just, %d even)" % (_cnt['just'], _cnt['even']))

    # ---- the wheel means the same thing live and offline ---------------------
    # CC1 is the gain knob in both, and they are two separate implementations
    # of one mapping: live quantises to LIVE_DRIVE_STEPS because every move
    # costs a recompute, offline does not because there is nothing to
    # economise on. They must still agree, or a part sounds different played
    # than rendered.
    _worst = 0.0
    for _cc in (0, 16, 32, 64, 96, 127):
        _live = LIVE_DRIVE_RANGE * int(round(_cc / 127.0 * LIVE_DRIVE_STEPS)) \
            / float(LIVE_DRIVE_STEPS)
        _off = 4.0 * _cc / 127.0
        _worst = max(_worst, abs(_live - _off))
    check("the gain knob means the same thing live and offline",
          _worst <= LIVE_DRIVE_RANGE / LIVE_DRIVE_STEPS + 1e-9,
          "  (worst disagreement %.3f, one step is %.3f)"
          % (_worst, LIVE_DRIVE_RANGE / LIVE_DRIVE_STEPS))
    # AND THE REFERENCE IS NORMAL PLAYING, NOT MAXIMUM. drive 1.0 has to mean
    # the edge of breakup at a usual touch so digging in goes past it; at the
    # old 127 calibration every real file fell short, since attack_volume is
    # (vel/127)^2 and Riffsym writes everything at 100.
    # AS A RATIO TO THE VOICE'S OWN GAIN, which is the scale-free form and the
    # only one that survives re-levelling a family. The absolute thresholds this
    # check used to carry were tied to the generic initial_gain those voices
    # happened to inherit, so they failed the moment the family was balanced --
    # even though both numbers had moved together and the valve saw exactly the
    # same drive. What "calibrated at normal playing" means is reference over
    # gain, and that is unchanged: guitar 2.03 -> 2.04, bass 0.82 -> 0.82.
    _gr = _T.ElectricGuitarProperties.amp_reference / _T.ElectricGuitarProperties.initial_gain
    _br = _T.ElectricBassProperties.amp_reference / _T.ElectricBassProperties.initial_gain
    check("the amplifier is calibrated at normal playing, not maximum",
          _gr < 2.6 and _br < _gr,
          "  (guitar %.2f, bass %.2f, as a ratio to each voice's own gain)"
          % (_gr, _br))

    # ---- the basses ---------------------------------------------------------
    # The guitar's physics on a longer string, so what is worth guarding is
    # that each GM slot differs from its neighbour in the way its class claims.
    bass = [(33, _T.FingeredBassProperties), (34, _T.PickedBassProperties),
            (35, _T.FretlessBassProperties), (36, _T.SlapBassProperties),
            (37, _T.PoppedBassProperties)]
    check("the five electric basses are wired to their GM programs",
          all(_PM.property_class_for_program(n) is c for n, c in bass))
    # 32 is an UPRIGHT -- a wooden box, which is the one thing a solid body has
    # not got -- and 38-39 have no string at all. Giving either a pickup and a
    # speaker would be the saxophone trap, and THAT is what this guards.
    #
    # It used to guard it partly by asserting 38-39 were untouched, and it fired
    # when they were given voices. Correctly: the clause was true when written
    # and had become a statement about the calendar rather than about the model.
    # What it means is that neither an upright nor a synthesiser is an electric
    # bass guitar, and that survives 38-39 becoming oscillators -- an oscillator
    # has no string for a magnet to read and no amplifier to go through.
    _nopickup = [(32, _T.AcousticBassProperties)] + \
                [(n, _PM.property_class_for_program(n)) for n in (38, 39)]
    check("...and neither the upright nor the synth basses got a pickup",
          _PM.property_class_for_program(32) is _T.AcousticBassProperties
          and all(not getattr(c, "pickup_points", ())
                  and not getattr(c, "cabinet", None)
                  and not getattr(c, "amp_drive", 0.0)
                  for _n, c in _nopickup),
          "  (32 is the measured upright plucked; 38-39 are oscillators, and "
          "none of the three has a magnet or a speaker)")
    binst = {n: c(41.2, 0.0, 1.0, 1.0) for n, c in bass}

    def _mean_h(g, top=17):
        v = np.array([g.harmonic_volume(h) for h in range(1, top)]) ** 2
        return float((np.arange(1, top) * v).sum() / max(v.sum(), 1e-30))
    # A PICK IS HARDER AND NARROWER THAN A FINGER, so its comb notch stays deep
    # and it is played nearer the bridge: brighter, and that is the whole
    # difference between GM 33 and GM 34.
    check("a pick is brighter than a finger",
          _mean_h(binst[34]) > _mean_h(binst[33]),
          "  (mean harmonic %.1f vs %.1f)" % (_mean_h(binst[34]), _mean_h(binst[33])))
    # FRETLESS IS A TERMINATION, NOT A FILTER: the string stops on wood, which
    # is lossy up high, so the harmonics GO rather than never arriving.
    check("fretless loses its top rather than starting without it",
          binst[35].harmonic_decay(8) > 3.0 * binst[33].harmonic_decay(8)
          and abs(_mean_h(binst[35]) - _mean_h(binst[33])) < 0.5,
          "  (h8 decays %.0f vs %.0f dB/s, same spectrum)"
          % (binst[35].harmonic_decay(8), binst[33].harmonic_decay(8)))
    check("a slap is the brightest of them",
          _mean_h(binst[36]) > 1.5 * _mean_h(binst[33]),
          "  (mean harmonic %.1f vs %.1f)" % (_mean_h(binst[36]), _mean_h(binst[33])))
    # A BASS CABINET REACHES WHERE A GUITAR CABINET GIVES UP: the low E's
    # FUNDAMENTAL is the note, at 41 Hz.
    import cabinet as _CBB
    b45 = float(_CBB.get("bass410").response_db([45.0])[0])
    g45 = float(_CBB.get("guitar12").response_db([45.0])[0])
    check("the bass cabinet reaches where the guitar's gives up",
          b45 > g45 + 4.0, "  (%.1f dB vs %.1f dB at 45 Hz)" % (b45, g45))
    # ...and does not bite, which is what that peak is for on a guitar.
    b25 = float(_CBB.get("bass410").response_db([2500.0])[0])
    g25 = float(_CBB.get("guitar12").response_db([2500.0])[0])
    check("...and has far less presence, which a bass does not want",
          b25 < g25 - 4.0, "  (%.1f dB vs %.1f dB at 2.5 kHz)" % (b25, g25))

    # ---- fret noise, which is a different patch from harmonics ---------------
    check("fret noise has its own voice, not a mallet's",
          _PM.property_class_for_program(120) is _T.GuitarFretNoiseProperties,
          "  (%s)" % _PM.property_class_for_program(120).__name__)
    fn = _T.GuitarFretNoiseProperties(880.0, 0.0, 1.0, 1.0)
    # THE GLIDE IS THE SOUND, so it needs range the piano's bloom never did --
    # tension_bend was capped at 0.04 for that, which is 68 cents.
    check("a slide sweeps further than the piano's bloom was allowed to",
          fn.tension_bend > 0.04,
          "  (%.0f cents at onset)" % (1200 * math.log2(1.0 + fn.tension_bend)))
    check("...and it settles in the time a position shift takes",
          fn.tension_settle_time < 0.15, "  (%.2f s)" % fn.tension_settle_time)
    # THE BAND DOES NOT MOVE WITH THE NOTE, which is the claim that matters:
    # a squeak's frequency is slide speed over winding pitch, so it has to land
    # in the same place whatever the left hand is doing. The first version let
    # the note set it, which put the squeak on a musical pitch in the middle of
    # the guitar's own register -- and it was heard, correctly, as another
    # guitar note rather than as frets.
    def _centroid(cls, f0):
        g = cls(f0, 0.0, 1.0, 1.0)
        h = np.arange(1, g.max_harmonic + 1)
        e = np.array([g.harmonic_volume(int(k)) for k in h]) ** 2
        f = f0 * h
        keep = f < 20000.0
        return float((f[keep] * e[keep]).sum() / max(e[keep].sum(), 1e-30))
    lo_f = _centroid(_T.GuitarFretNoiseProperties, 110.0)
    hi_f = _centroid(_T.GuitarFretNoiseProperties, 880.0)
    check("the squeak's band is the hand's, not the fretted note's",
          700.0 < lo_f < 3500.0 and 700.0 < hi_f < 3500.0
          and max(lo_f, hi_f) < 1.6 * min(lo_f, hi_f),
          "  (centroid %.0f Hz at 110 Hz, %.0f Hz three octaves up)"
          % (lo_f, hi_f))
    # ...where a voice that follows its note moves with it, by definition.
    br_lo = _centroid(_T.BreathNoiseProperties, 110.0)
    br_hi = _centroid(_T.BreathNoiseProperties, 880.0)
    check("...unlike breath, which has no band to keep",
          br_hi > 1.8 * br_lo, "  (breath moves %.0f -> %.0f Hz)" % (br_lo, br_hi))
    # Only WOUND strings squeak, so it must fall away up the register.
    hi = _T.GuitarFretNoiseProperties(3520.0, 0.0, 1.0, 1.0)
    check("it fades where the strings would be plain",
          hi.gain < fn.gain * 0.6,
          "  (%.1f dB across two octaves)"
          % (20 * math.log10(max(hi.gain, 1e-30) / max(fn.gain, 1e-30))))

    check("the neck humbucker is darker than the bridge one",
          _bright(inst[26]) < _bright(inst[30]),
          "  (mean harmonic %.1f vs %.1f)" % (_bright(inst[26]), _bright(inst[30])))

    # ---- the electric pianos ------------------------------------------------
    # GM 4 rendered as a Steinway B. A Rhodes is a struck steel TINE read by a
    # magnetic pickup: measured, the tine vibrates as a pure sine and every
    # harmonic is made by the pickup, so nothing about a piano applies to it.
    import math as _math
    import patch_map as _PM
    check("the Rhodes is not a piano", _PM.property_class_for_program(4) is _T.RhodesProperties)
    check("...and the acoustic grand is still itself",
          _PM.property_class_for_program(0) is _T.GrandPianoProperties
          and _PM.property_class_for_program(6) is _T.HarpsichordProperties,
          "  (every one of GM 0-7 is now its own instrument)")

    # ---- the bright piano: the same instrument, voiced hard ------------------
    check("the bright piano is the grand with harder hammers",
          _PM.property_class_for_program(1) is _T.BrightPianoProperties
          and issubclass(_T.BrightPianoProperties, _T.GrandPianoProperties))
    bp, gp2 = _T.BrightPianoProperties, _T.GrandPianoProperties
    check("...a shorter contact time, which IS the hammer's low-pass",
          bp.hammer_corner_hz > gp2.hammer_corner_hz * 1.4,
          "  (%.2f ms of contact against %.2f)"
          % (1000.0 / bp.hammer_corner_hz, 1000.0 / gp2.hammer_corner_hz))
    # A hard hammer barely spreads, so it keeps the strike comb's notch at every
    # dynamic where a soft one fills it in completely by ff.
    _d = lambda c, av: c.strike_depth * (1.0 - c.strike_fill_fraction * av)
    check("...and felt that spreads less, so its notch survives being hit",
          _d(bp, 1.0) > 0.2 and _d(gp2, 1.0) < 0.01,
          "  (notch depth at ff: %.2f here, %.2f on the grand)"
          % (_d(bp, 1.0), _d(gp2, 1.0)))
    # THE CHARACTERISTIC RESULT: the difference is biggest played SOFTLY. A hard
    # hammer is already bright and has less to open into, so the voice brightens
    # LESS from pp to ff than the grand does. That is what voicing argues about.
    def _bright(cls, vel):
        q = cls(261.63, 0.0, (vel / 127.0) ** 2, 1.0)
        v = [q.harmonic_volume(h) for h in range(1, 33)]
        return 10 * _math.log10(sum(x * x for x in v[7:]) / sum(x * x for x in v))
    soft = _bright(bp, 30) - _bright(gp2, 30)
    hard = _bright(bp, 127) - _bright(gp2, 127)
    check("...and it tells MOST when played softly, as hard voicing does",
          soft > hard > 0.0,
          "  (+%.1f dB at v30 against +%.1f at v127)" % (soft, hard))
    check("...so it opens less from pp to ff, having started bright",
          (_bright(bp, 127) - _bright(bp, 30)) < 0.6 * (_bright(gp2, 127) - _bright(gp2, 30)),
          "  (+%.1f dB of opening against the grand's +%.1f)"
          % (_bright(bp, 127) - _bright(bp, 30), _bright(gp2, 127) - _bright(gp2, 30)))
    # The fill fraction generalises a boolean; every other voice must be untouched.
    _moved = [k for k, v in sorted(vars(_T).items())
              if isinstance(v, type) and getattr(v, "strike_fill_fraction", 1.0) != 1.0]
    check("...and generalising that boolean moved nothing else",
          _moved == ["BrightPianoProperties"],
          "  (%d of the whole set departs from the soft default)" % len(_moved))

    # ---- the acoustic bass: the measured upright, plucked --------------------
    # AND NO VOICE IS LEFT AT THE GENERIC GAIN. This check exists because the
    # electric bass shipped 23 dB too quiet for months and Ben's ear caught it,
    # not the suite: fourteen voices inherited PluckedStringProperties'
    # initial_gain = 0.02 and were never balance-normalised, so the family
    # spanned 41 dB. Nothing here measured absolute level -- dozens of checks on
    # spectrum and on relationships BETWEEN voices, none on how loud one is, so
    # a voice could be inaudible and every check would pass.
    #
    # It cannot measure level honestly: that needs a render (examples/levels.py
    # does it properly, and the arithmetic shortcut was wrong by up to 80 dB --
    # a bowed voice has no onset, and the amp and cabinet are not in the
    # series). So it asserts the thing that IS cheap and exact, and which is
    # what actually went wrong: every voice in the family resolves its gain from
    # a deliberately balanced class, not by falling through to the generic base.
    _PLUCKED_FAMILY = (
        "NylonGuitarProperties", "SteelGuitarProperties", "JazzGuitarProperties",
        "ElectricGuitarProperties", "MutedGuitarProperties",
        "OverdrivenGuitarProperties", "DistortionGuitarProperties",
        "GuitarHarmonicsProperties", "AcousticBassProperties",
        "FingeredBassProperties", "PickedBassProperties",
        "FretlessBassProperties", "SlapBassProperties",
    )
    _unbalanced = []
    for _n in _PLUCKED_FAMILY:
        _c = getattr(_T, _n, None)
        if _c is None:
            continue
        _src = next((_k.__name__ for _k in _c.__mro__ if "initial_gain" in vars(_k)),
                    None)
        if _src in (None, "PluckedStringProperties"):
            _unbalanced.append(_n)
    check("every plucked voice has a balanced gain, not the generic one",
          not _unbalanced,
          "  (%d voices, all resolving from a normalised class)"
          % len(_PLUCKED_FAMILY) if not _unbalanced
          else "  (still generic: %s)" % ", ".join(_unbalanced))

    # ------------------------------------------- the last two category errors
    import patch_map as _PMc
    # 118 and 119 were the last two programs in the bank marked CATEGORY ERROR:
    # a drum machine and a reversed cymbal, both on the generic mallet base.
    _sd = _PMc.property_class_for_note(118, 60)
    _rc = _PMc.property_class_for_note(119, 60)
    check("the synth drum and the reverse cymbal are no longer mallets",
          not issubclass(_sd, _T.MalletProperties)
          and not issubclass(_rc, _T.MalletProperties)
          and issubclass(_rc, _T.CrashCymbal1Properties),
          "  (an 808 tom and the MEASURED crash, reversed)")
    # A REVERSE CYMBAL IS THE ONE VOICE WHOSE ENVELOPE RISES. Everything else
    # in this bank decays; a partial can be made to fall faster than its
    # neighbour but not to rise. The rise is the ATTACK, and the only thing
    # in the way was blockrender's flat cap of 0.45 of the note's duration --
    # right for every acoustic voice and wrong for this one.
    check("...and the reverse cymbal's attack may outlast half its note",
          _rc.attack_fraction_max > 0.85
          and _T.SynthProperties.attack_fraction_max == 0.45
          and [_n for _n, _c in vars(_T).items()
               if isinstance(_c, type)
               and getattr(_c, "attack_fraction_max", 0.45) != 0.45]
          == ["ReverseCymbalProperties"],
          "  (%.0f%% of the note against everything else's 45%%)"
          % (100 * _rc.attack_fraction_max))
    # ...AND IT IS NOT A ONE-SHOT, which every other cymbal is. A struck cymbal
    # ignores note-off and rings out because nothing stops it; blockrender
    # extends it to 8 s, and with the attack capped at a FRACTION of the
    # duration that made this voice swell for 7.4 s whatever was written --
    # measured, a 3-second note peaked at 4.84, past its own end. A reverse
    # cymbal exists to ARRIVE somewhere.
    check("...and it ends where it is written, unlike every other cymbal",
          not _rc.one_shot and _T.CrashCymbal1Properties.one_shot,
          "  (rendered, a 3 s note now peaks at 2.82 s; a forward crash at 0.03)")
    # THE DRUM MACHINE'S SWEEP NEEDED NOTHING NEW. tension_bend is a pitch
    # transient that blooms and settles, written for the piano, where a hard
    # blow stretches the string. An 808 tom is the same shape and much more of
    # it: start sharp, fall to pitch, in a fifth of a second.
    check("...and the synth drum sweeps its pitch down, which is its whole sound",
          _sd.tension_bend > 0.3 and _sd.tension_settle_time < 0.1,
          "  (rendered on A2: 167 Hz at the onset, settling to 110)")

    # ------------------------------------------------------------ the ethnic
    import patch_map as _PMe
    # 105-108 were the generic plucked string and the generic mallet; 109 and
    # 111 shared one reed pipe. Each is a different MECHANISM.
    _eth = {_g: _PMe.property_class_for_note(_g, 60) for _g in range(104, 112)}
    check("the ethnic family is eight voices, not three",
          len({_c.__name__ for _c in _eth.values()}) == 8,
          "  (104-111 all distinct)")
    # THE ROUTER, NOT THE ASSIGNMENT. Three of these were written and then
    # immediately overwritten four lines further down -- the same shape as
    # GM 32, where the class existed, was correct, and was never reached.
    check("...and the router agrees with the map that was written",
          _eth[108] is _T.KalimbaProperties and _eth[109] is _T.BagpipeProperties
          and _eth[111] is _T.ShanaiProperties,
          "  (kalimba, bagpipe and shanai reached, not clobbered)")
    # A KALIMBA IS A CANTILEVER, not a bar and not a string. A free-free bar
    # runs 1 : 3 : 5 and a clamped-free cantilever 1 : 6.267 : 17.55, which is
    # why a kalimba's overtones sit above the note as separate pings instead of
    # fusing into it. Same ratios as a Rhodes tine, for the same reason.
    _ka = _eth[108](261.63, 0.0, 1.0, 1.0)
    check("...and the kalimba rings as a CANTILEVER, not as a bar",
          abs(_ka.mode_ratio(2) - 6.267) < 0.01
          and abs(_ka.mode_ratio(3) - 17.55) < 0.01,
          "  (1 : %.3f : %.2f, where a marimba bar is 1 : 4 : 10)"
          % (_ka.mode_ratio(2), _ka.mode_ratio(3)))
    # A DRONE DOES NOT FOLLOW THE MELODY, which is the one thing no other voice
    # in this bank does: every other user of unison_voices returns a RATIO and
    # so tracks the note by construction.
    _dr = []
    for _m in (55, 67, 79):
        _f = 440.0 * 2.0 ** ((_m - 69) / 12.0)
        _q = _eth[109](_f, 0.0, 1.0, 1.0)
        _dr.append(tuple(round(_f * (1.0 + _v[2]), 2)
                         for _v in _q.unison_voices(_f, 1, 0.0)))
    check("...and the bagpipe's drones hold while the melody moves",
          len(set(_dr)) == 1 and len(_dr[0]) == 3,
          "  (%s Hz at every pitch)" % ", ".join("%.1f" % _x for _x in _dr[0]))
    # THREE DRONES, AND TWO OF THEM ARE THE SAME NOTE. A Highland pipe carries
    # two TENORS at A3 and one bass at A2, and the tenors are a chorus rather
    # than a doubling: they beat, always, and a piper's "drone lock" is the
    # sound of two reeds almost agreeing. Rendering one tenor loses it, which
    # is what this class did first -- Ben asked whether the drone should not be
    # "a small chorus of all of the drones of the bag", and it should.
    _ten = sorted(_x for _x in _dr[0] if _x > 150.0)
    check("...and its two tenors beat, which is what drone lock is",
          len(_ten) == 2 and 0.05 < abs(_ten[1] - _ten[0]) < 2.0,
          "  (%.2f Hz apart: one beat every %.1f s, a well-tuned pipe)"
          % (abs(_ten[1] - _ten[0]), 1.0 / max(abs(_ten[1] - _ten[0]), 1e-9)))
    # AND THE DRONES CAN BE SWITCHED OFF. Including them is right -- the
    # reference implementation does, and the program is called Bag pipe rather
    # than Chanter -- but a score that writes its own drone as held notes would
    # have it twice, and a voice cannot tell.
    _was = _T.bagpipe_drone
    try:
        _T.bagpipe_drone = 0.0
        _silent = _eth[109](392.0, 0.0, 1.0, 1.0).unison_voices(392.0, 1, 0.0)
    finally:
        _T.bagpipe_drone = _was
    check("...and they can be corked, for a score that writes its own",
          not _silent and _T.bagpipe_drone,
          "  (CC1 0, or TUNING_BAGPIPE_DRONE=0, leaves the chanter alone)")
    # AND THEY BELONG TO THE PART. Ben: "The drones seem to me to be a channel
    # event?" -- they are, and attaching them to the note made them restart on
    # every one. The flag is general; the bagpipe is the only voice that sets
    # it, because a chorus, a section and a set of sympathetic strings all
    # belong to the note that excited them and a drone does not.
    _spanners = [_n for _n, _c in vars(_T).items()
                 if isinstance(_c, type) and getattr(_c, "unison_spans_part", False)]
    check("...and they span the PART, not the note",
          _eth[109].unison_spans_part
          and not _T.SynthProperties.unison_spans_part
          and _spanners == ["BagpipeProperties"],
          "  (rendered on a detached line the drone holds through the rests)")
    # A CONE PASSES THE WHOLE SERIES. The shanai had been on the bagpipe's
    # class, which is ReedOrganProperties underneath and suppresses the evens.
    _sh = _eth[111](261.63, 0.0, 1.0, 1.0)
    check("...and the shanai's cone brings the even harmonics back",
          not _eth[111].odd_only and _sh.harmonic_volume(2) > 0.0,
          "  (a shawm is an oboe's geometry, not a chanter's)")
    # A MEMBRANE CANNOT RADIATE LOW. The banjo and the shamisen are the only
    # plucked voices here whose body is a stretched skin.
    check("...and the two drumhead instruments cannot radiate their bottom",
          _eth[105].bell_cutoff_hz > 300.0 and _eth[106].bell_cutoff_hz > 300.0
          and _eth[107].bell_cutoff_hz < 200.0,
          "  (banjo %.0f Hz and shamisen %.0f, against the koto's wooden %.0f)"
          % (_eth[105].bell_cutoff_hz, _eth[106].bell_cutoff_hz,
             _eth[107].bell_cutoff_hz))

    # ------------------------------------------------------------ the effects
    import patch_map as _PMfx
    # 96-103 were the LAST block of eight on one voice.
    _fx = {_g: _PMfx.property_class_for_note(_g, 64) for _g in range(96, 104)}
    check("the eight effects are eight voices, not one bowed string",
          len({_c.__name__ for _c in _fx.values()}) == 8,
          "  (and with the pads, sixteen programs off a single class)")
    # Each has a mechanism the others do not, as the pads do.
    _fxm = {
        "echo taps (96, 102)": {_g for _g in _fx if getattr(_fx[_g], "echo_taps", ())},
        "breath (99)": {_g for _g in _fx if _fx[_g].sustain_jitter > 0.3},
        "a deep wobble (101)": {_g for _g in _fx
                                if _fx[_g].section_vibrato_cents > 20.0},
        "odd-only (103)": {_g for _g in _fx if _fx[_g].odd_only},
    }
    check("...and each has a mechanism the others do not",
          _fxm["breath (99)"] == {99} and _fxm["a deep wobble (101)"] == {101}
          and _fxm["odd-only (103)"] == {103}
          and _fxm["echo taps (96, 102)"] == {96, 102},
          "  (%s)" % "; ".join(_fxm))
    # THE TAPS ARE REPEATED ONSETS, NOT A DELAY LINE, and the docstring says so
    # at length. What is checkable is that they are evenly spaced, fall in gain,
    # and sit at the note's own pitch bar a few cents of tape drift.
    _ec = _fx[102](329.63, 0.0, 1.0, 1.0)
    _on = _ec.section_onsets_at(329.63)
    _gn = [_v[0] for _v in _ec.unison_voices(329.63, 1, 0.0)]
    _sp = [round(_on[_i + 1] - _on[_i], 4) for _i in range(len(_on) - 1)]
    check("...and the echo taps are even, falling, and at pitch",
          len(set(_sp)) == 1 and all(_gn[_i] > _gn[_i + 1] for _i in range(len(_gn) - 1))
          and max(abs(1200.0 * math.log2(1.0 + _v[2]))
                  for _v in _ec.unison_voices(329.63, 1, 0.0)) < 15.0,
          "  (%d taps %.0f ms apart, gains %s)"
          % (len(_on) - 1, 1000 * _sp[0], "/".join("%.2f" % _x for _x in _gn)))
    # AND A TAP NEEDS A DECAYING NOTE. With a pad's sustain the repeats merged
    # into what they were repeating; GM 102 is percussive for that reason.
    check("...and the echoing voice decays, or the taps would merge",
          _fx[102].sustain_level < 0.25 and _fx[102].decay_db > 4.0,
          "  (sustain %.2f against the pads' 0.93)" % _fx[102].sustain_level)
    # The stretched effects obey the same cap the pads do.
    _oob = [_g for _g, _c in _fx.items() if _c.inharmonicity_coefficient > 0.0
            and 329.63 * _c.max_harmonic
            * (1.0 + 0.5 * (_c.max_harmonic ** 2 - 1) * _c.inharmonicity_coefficient)
            > 20000.0]
    check("...and the stretched ones keep their top partial in the band",
          not _oob,
          "  (96 and 98 capped at %d and %d partials)"
          % (_fx[96].max_harmonic, _fx[98].max_harmonic) if not _oob
          else "  (out of band: %s)" % _oob)

    # ---------------------------------------------------------------- the pads
    import patch_map as _PMp2
    # 88-95 were ONE BowedStringProperties, and with the effects at 96-103 that
    # was sixteen programs on a single voice -- the largest gap in the bank.
    _pads = {_g: _PMp2.property_class_for_note(_g, 64) for _g in range(88, 96)}
    check("the eight pads are eight voices, not one bowed string",
          len({_c.__name__ for _c in _pads.values()}) == 8
          and not any(issubclass(_c, _T.BowedStringProperties)
                      and not issubclass(_c, _T.SawtoothSynthProperties)
                      for _c in _pads.values()),
          "  (eight distinct classes where there had been one)")
    # EACH GETS A MECHANISM THE OTHERS DO NOT HAVE, which is the difference
    # between eight voices and one voice with eight sets of numbers. GM's own
    # names point at mechanisms: a choir has formants, metal is inharmonic, a
    # halo is hollow, a sweep sweeps.
    _mech = {
        "inharmonic (88, 93)": {_g for _g in _pads
                                if _pads[_g].inharmonicity_coefficient > 0.0},
        "odd-only (94)": {_g for _g in _pads if _pads[_g].odd_only},
        "vocal formants (91)": {_g for _g in _pads if len(_pads[_g].formants) >= 3},
        "fast enough to play (90)": {_g for _g in _pads
                                     if _pads[_g].attack_time < 0.1},
        "a deep sweep (95)": {_g for _g in _pads
                              if _pads[_g].harmonic_decay_db > 5.0},
    }
    check("...and each has a mechanism the others do not",
          _mech["odd-only (94)"] == {94} and _mech["vocal formants (91)"] == {91}
          and _mech["fast enough to play (90)"] == {90}
          and _mech["a deep sweep (95)"] == {95}
          and _mech["inharmonic (88, 93)"] == {88, 93},
          "  (%s)" % "; ".join("%s" % _k for _k in _mech))
    # METAL MEANS INHARMONIC, and that is the one distinction here which is
    # physics rather than filtering: a struck plate's modes are not whole
    # multiples, so the overtones beat instead of fusing into a pitch.
    _mt = _pads[93](329.63, 0.0, 1.0, 1.0)
    _na = _pads[88](329.63, 0.0, 1.0, 1.0)
    check("...and the metallic pad is stretched far past the glassy one",
          _mt.inharmonicity_coefficient > 10.0 * _na.inharmonicity_coefficient,
          "  (B %.5g against %.5g -- a clang against a shimmer)"
          % (_mt.inharmonicity_coefficient, _na.inharmonicity_coefficient))
    # A STRETCHED SERIES MUST BE SHORTER THAN A HARMONIC ONE. The law is
    # 1 + 0.5*(h^2-1)*B, growing with the SQUARE of the index, so a voice with
    # both a stretch and forty partials puts its top one past Nyquist: measured
    # at B = 0.0062, h40 landed at 78 kHz on an E4.
    _bad = []
    for _g, _c in _pads.items():
        _B = _c.inharmonicity_coefficient
        if _B <= 0.0:
            continue
        _h = _c.max_harmonic
        _top = 329.63 * _h * (1.0 + 0.5 * (_h * _h - 1) * _B)
        if _top > 20000.0:
            _bad.append((_g, _top))
    check("...and every stretched voice keeps its top partial in the band",
          not _bad,
          "  (88 and 93 capped at %d and %d partials)"
          % (_pads[88].max_harmonic, _pads[93].max_harmonic) if not _bad
          else "  (out of band: %s)" % _bad)

    # ---------------------------------------------------------- synth strings
    import patch_map as _PMss
    # 50 and 51 were in BOWED_ENSEMBLE, so they routed per register to the four
    # MEASURED string bodies and rendered IDENTICALLY to GM 48: three programs,
    # one voice. Worse than the synth brass's redundancy, which was at least a
    # resemblance rather than the same class.
    _s50 = _PMss.property_class_for_note(50, 64)
    _s51 = _PMss.property_class_for_note(51, 64)
    _s48 = _PMss.property_class_for_note(48, 64)
    check("the synth strings are not the acoustic string ensemble",
          _s50 is not _s48 and _s51 is not _s48 and _s50 is not _s51
          and 50 not in _PMss.BOWED_ENSEMBLE and 51 not in _PMss.BOWED_ENSEMBLE,
          "  (three distinct voices where there had been one)")
    # A CHORUS IS NOT A SECTION, and that is the whole instrument. A string
    # machine has one oscillator per key and a bucket-brigade chorus: a few
    # copies at FIXED offsets, the same on every note. A section has many
    # players whose spread is drawn per note and who never agree.
    def _offs(_g, _midi):
        _f = 440.0 * 2.0 ** ((_midi - 69) / 12.0)
        _q = _PMss.property_class_for_note(_g, _midi)(_f, 0.0, 1.0, 1.0)
        return tuple(round(1200.0 * math.log2(1.0 + _v[2]), 3)
                     for _v in _q.unison_voices(_f, 1, 0.0))
    _mach = {_offs(50, _m) for _m in (52, 64, 76)}
    _sect = {_offs(48, _m) for _m in (52, 64, 76)}
    check("...and the machine's chorus is FIXED where a section's spread is drawn",
          len(_mach) == 1 and len(_sect) == 3,
          "  (the machine gives the same %d offsets on every note; the section "
          "redraws its %d)" % (len(_offs(50, 64)), len(_offs(48, 64))))
    # ...each tap swept by its own slow LFO, which is voice_vibrato running at a
    # chorus rate rather than a violinist's. The two must not be confusable.
    _vb = _s50(329.63, 0.0, 1.0, 1.0).voice_vibrato(329.63, 1)
    check("...and the chorus sweeps far slower than a player vibrates",
          _vb is not None and _s50.section_vibrato_hz[1] < 0.5 * _s48.section_vibrato_hz[0],
          "  (%.2f-%.2f Hz against a violinist's %.1f-%.1f)"
          % (_s50.section_vibrato_hz + _s48.section_vibrato_hz))
    # AND A PAD SWELLS. The attack is fixed in seconds and owes nothing to the
    # note's wavelength, which is why speech_cycles stays zero here.
    check("...and both swell, the second more slowly than the first",
          _s51.attack_time > 2.0 * _s50.attack_time and not _s50.speech_cycles,
          "  (%.0f ms and %.0f ms, neither scaled by wavelength)"
          % (1000 * _s50.attack_time, 1000 * _s51.attack_time))

    # ------------------------------------------------------------- synth bass
    import patch_map as _PMsb
    # 38 and 39 fell through to PluckedStringProperties -- the GENERIC plucked
    # string, which has no `formants` attribute at all, so a synth bass was a
    # bare string series with no body and no filter. The third family caught by
    # that same hole, after the pizzicato and the harp.
    _b1 = _PMsb.property_class_for_note(38, 28)
    _b2 = _PMsb.property_class_for_note(39, 28)
    check("the synth basses are oscillators, not plucked strings",
          _b1 is not _b2
          and not issubclass(_b1, _T.PluckedStringProperties)
          and issubclass(_b1, _T.SawtoothSynthProperties)
          and bool(getattr(_b1, "formants", ())),
          "  (an oscillator under a resonant low-pass, and two distinct presets)")
    # GM 39 IS A SQUARE, which is an exact distinction rather than a tuned one:
    # a square IS the odd harmonics at 1/n, so its evens are absent by
    # definition and it is audibly a different instrument from its neighbour
    # rather than the same one brighter.
    _q39 = _b2(41.2, 0.0, 1.0, 1.0)
    check("...and GM 39 is a SQUARE, hollow where GM 38 is full",
          _b2.odd_only and max(_q39.harmonic_volume(_k) for _k in (2, 4, 6)) < 1e-9,
          "  (no even harmonics at all, by definition)")
    # THE FILTER ENVELOPE IS THE PLUCK: the amplitude holds while the filter
    # shuts, which is why a synth bass note has a bright attack and a round body
    # without getting quieter.
    _q38 = _b1(41.2, 0.0, 1.0, 1.0)
    check("...and the filter shuts while the amplitude holds",
          _q38.harmonic_decay(8) > 5.0 * _q38.harmonic_decay(1),
          "  (h1 %.1f dB/s against h8 %.1f)"
          % (_q38.harmonic_decay(1), _q38.harmonic_decay(8)))
    # NO DETUNE, which is the opposite of the synth brass and is deliberate:
    # two oscillators a few cents apart beat at a rate proportional to
    # frequency, and at E1 that is 0.2 Hz -- a slow wobble across a whole bar,
    # which in the bass reads as the part being out of tune, not as thickness.
    check("...and a synth bass is voiced TIGHT, unlike the synth brass",
          not _q38.unison_voices(41.2, 1, 0.0)
          and not _q39.unison_voices(41.2, 1, 0.0),
          "  (one oscillator; a 6-cent detune would beat at 0.2 Hz down here)")
    # AND NEITHER IS A COPY OF THE ELECTRIC BASSES, which are modelled
    # instruments in this renderer -- the lesson the synth brass taught.
    _eb = _PMsb.property_class_for_note(33, 28)(41.2, 0.0, 1.0, 1.0)
    def _odd_gap(_q):
        return max(abs(20.0 * math.log10(max(_q.harmonic_volume(_k), 1e-12)
                                         / max(_q.harmonic_volume(1), 1e-12))
                       - 20.0 * math.log10(max(_eb.harmonic_volume(_k), 1e-12)
                                           / max(_eb.harmonic_volume(1), 1e-12)))
                   for _k in (3, 5, 7, 9, 11))
    check("...and neither is a copy of the electric bass",
          _odd_gap(_q38) > 8.0 and _odd_gap(_q39) > 8.0,
          "  (%.0f and %.0f dB from GM 33 on the harmonics they share)"
          % (_odd_gap(_q38), _odd_gap(_q39)))

    # ------------------------------------------------------------ synth brass
    import patch_map as _PMb2
    # 62 and 63 sat on BrassProperties, the abstract ACOUSTIC brass base, which
    # carries a bore, a register centre and the intonation tendencies of a
    # played horn. General MIDI specifies nothing about how these are built --
    # Level 1 is a name list -- so the reading is the SC-55's, but a synthesiser
    # is certainly not an air column.
    _sb1 = _PMb2.property_class_for_note(62, 60)
    _sb2 = _PMb2.property_class_for_note(63, 60)
    check("the synth brasses are oscillators, not horns",
          not issubclass(_sb1, _T.BrassProperties)
          and issubclass(_sb1, _T.SawtoothSynthProperties)
          and _sb1 is not _sb2,
          "  (a sawtooth through a resonant filter, and two distinct presets)")
    # THE FILTER, NOT ONLY ITS ENVELOPE. The first version gave these the sweep
    # and left the spectrum a bare 1/n saw -- which made 62 and 63 spectrally
    # IDENTICAL, differing only in an envelope. The bite of a synth brass patch
    # is the RESONANT PEAK at the cutoff, and the two presets' cutoffs are an
    # octave apart, which is what "softer" means on the panel.
    _q1 = _sb1(261.63, 0.0, 1.0, 1.0)
    _q2 = _sb2(261.63, 0.0, 1.0, 1.0)
    _s1 = [_q1.harmonic_volume(_k) / _q1.harmonic_volume(1) for _k in (4, 8, 16)]
    _s2 = [_q2.harmonic_volume(_k) / _q2.harmonic_volume(1) for _k in (4, 8, 16)]
    check("...and they differ in SPECTRUM, not only in envelope",
          max(abs(20.0 * math.log10(_a / _b)) for _a, _b in zip(_s1, _s2)) > 8.0,
          "  (resonances at %.0f and %.0f Hz -- the MEASURED spectral peaks of "
          "the Iowa trumpet and horn, which these two imitate)"
          % (_sb1.formants[0][0], _sb2.formants[0][0]))
    # AND THE RESONANCE HAD TO BE WIRED BY HAND. SawtoothSynthProperties
    # overrides harmonic_volume to return gain/n directly and so never reaches
    # bore_gain, which is the hook FormantBody works through -- the same trap
    # the voice lead fell into. Inheriting a body is not sounding through one.
    # Against the IDEAL 1/n saw these are built from, anywhere in the series --
    # the first version of this check looked only at h8, which on the trumpet
    # reading sits above the resonance and so barely moves; a filter shows
    # itself wherever its corner happens to fall, not at a fixed harmonic.
    def _off_saw(_q):
        _r = _q.harmonic_volume(1)
        return max(abs(20.0 * math.log10(max(_q.harmonic_volume(_k), 1e-12) / _r)
                       + 20.0 * math.log10(_k))
                   for _k in range(2, 17))
    check("...and the filter actually reaches the output",
          min(_off_saw(_q1), _off_saw(_q2)) > 6.0,
          "  (%.1f and %.1f dB off a bare 1/n saw, so the resonance is there)"
          % (_off_saw(_q1), _off_saw(_q2)))
    # AND IT MUST NOT BE A COPY OF THE ACOUSTIC VOICE. This check used to assert
    # the opposite -- that GM 63 tracked the measured horn to within 4 dB -- and
    # that was the wrong test written confidently. GM 56 and GM 60 in this
    # renderer are themselves synthesised, so "sound like a horn" collapses into
    # "be the horn", and a patch that passes a resemblance test has become
    # redundant with the program four numbers earlier. The first version of
    # these two made 62 and 63 identical to each other; tuning them onto the
    # acoustic voices only moved the collision.
    #
    # A synth brass is a caricature: a sawtooth cannot rise to a formant the way
    # a bore does, and its filter sits where the knob is. Checked across the
    # compass, because the two are closest at exactly one pitch and diverge away
    # from it.
    def _gap(_g_syn, _g_ac):
        _worst = 0.0
        for _m in (48, 60, 72, 84):
            _f = 440.0 * 2.0 ** ((_m - 69) / 12.0)
            _a = _PMb2.property_class_for_note(_g_syn, _m)(_f, 0.0, 1.0, 1.0)
            _b = _PMb2.property_class_for_note(_g_ac, _m)(_f, 0.0, 1.0, 1.0)
            for _k in (2, 3, 4, 6, 8):
                _worst = max(_worst, abs(
                    20.0 * math.log10(max(_a.harmonic_volume(_k), 1e-12)
                                      / max(_a.harmonic_volume(1), 1e-12))
                    - 20.0 * math.log10(max(_b.harmonic_volume(_k), 1e-12)
                                        / max(_b.harmonic_volume(1), 1e-12))))
        return _worst
    check("...and neither is a copy of the acoustic voice it leans toward",
          _gap(62, 56) > 10.0 and _gap(63, 60) > 10.0,
          "  (%.0f dB from the trumpet, %.0f from the horn, across four octaves)"
          % (_gap(62, 56), _gap(63, 60)))

    # The two oscillators are a KNOB: the same offset on every note, unlike a
    # piano's unisons (random per note) or a section (random per player).
    _v1 = _q1.unison_voices(261.63, 1, 0.0)
    _v2 = _q2.unison_voices(261.63, 1, 0.0)
    check("...and the second oscillator is a fixed detune, not a spread",
          len(_v1) == 1 and len(_v2) == 1
          and abs(1200.0 * math.log2(1.0 + _v1[0][2]) - _sb1.detune_cents) < 0.01,
          "  (%.0f and %.0f cents, the same on every note)"
          % (_sb1.detune_cents, _sb2.detune_cents))

    # ------------------------------------------------- touch, and the lack of it
    # Ben, playing live: "The harpsichord patch is touch sensitive."
    #
    # A harpsichord key trips a jack and the quill plucks with a force the jack
    # decides, which is the textbook fact about the instrument and the reason it
    # has two manuals and a registration instead of a crescendo. Measured across
    # the corpus, 97% of harpsichord channels write a SINGLE velocity: the people
    # who sequenced them knew too.
    #
    # THE COMMENT IN THE NOTE-ON PATH WAS TRUE AND INSUFFICIENT. It says a
    # registerable voice ignores velocity, and the stamp does. But velocity also
    # picks the BUCKET, and each bucket's template is built at its own velocity
    # with attack_volume baked into the partial amplitudes -- so the harpsichord
    # arrived 23 dB louder at velocity 120 than at 32 without the stamp ever
    # looking at velocity. Checked here through the BANK, which is the path that
    # actually broke, and not only through the class.
    import patch_map as _PMt
    _fixed = [(6, "harpsichord"), (16, "drawbar organ"), (19, "church organ"),
              (20, "reed organ"), (21, "accordion"), (23, "tango accordion")]
    _bad = []
    for _g, _lab in _fixed:
        _c = _PMt.property_class_for_note(_g, 60)
        if _c.touch_sensitive:
            _bad.append(_lab)
    check("a key that trips a jack or opens a valve does not set the level",
          not _bad,
          "  (%d voices fixed-volume)" % len(_fixed) if not _bad
          else "  (still touch-sensitive: %s)" % ", ".join(_bad))
    # ...AND ONLY attack_volume IS NEUTRALISED. CC7 and CC11 are the channel,
    # not the key, and they must still work -- an organ's swell box and an
    # accordion's bellows are exactly that, so a fixed-volume patch that ignored
    # them would be a worse model, not a purer one.
    _hc = _PMt.property_class_for_note(6, 60)
    _full = _hc(261.63, 0.0, 1.0, 1.0).gain
    _soft_key = _hc(261.63, 0.0, (20 / 127.0) ** 2, 1.0).gain
    _soft_cc = _hc(261.63, 0.0, 1.0, (20 / 127.0) ** 2).gain
    check("...but channel volume still does, which is the swell and the bellows",
          abs(_soft_key - _full) < 1e-12 and _soft_cc < 0.1 * _full,
          "  (velocity 20 moves it %.2f dB, CC7 20 moves it %.1f)"
          % (20.0 * math.log10(_soft_key / _full),
             20.0 * math.log10(_soft_cc / _full)))
    # AND THE VOICES THAT DO HAVE TOUCH MUST KEEP IT. A clavinet is a tangent
    # striking a string and is famously expressive; a harmonica has no key at
    # all, so the player's breath is both the valve and the dynamic.
    _touchy = [(0, "piano"), (7, "clavinet"), (22, "harmonica"), (56, "trumpet"),
               (71, "clarinet")]
    _lost = [_l for _g, _l in _touchy
             if not _PMt.property_class_for_note(_g, 60).touch_sensitive]
    check("...and everything that IS touch-sensitive still is",
          not _lost,
          "  (piano, clavinet, harmonica, trumpet, clarinet)" if not _lost
          else "  (lost their touch: %s)" % ", ".join(_lost))

    # ------------------------------------------------------------ the pipes
    import patch_map as _PMp
    # 72-79 differ in three things: whether the tube is OPEN or CLOSED, how the
    # jet is aimed, and how much of the breath misses the edge. Four of the eight
    # had none of that and sat on a generic base.
    _pipes = {_g: _PMp.property_class_for_note(_g, 72) for _g in range(72, 80)}
    check("each pipe is its own voice, not one generic tube",
          len({_c.__name__ for _c in _pipes.values()}) >= 6,
          "  (%d distinct classes over the eight programs)"
          % len({_c.__name__ for _c in _pipes.values()}))
    # A PAN PIPE IS CLOSED AT THE BOTTOM, and nothing else in the family is.
    # That is not a colour: a stopped tube resonates at ODD multiples and
    # overblows at the twelfth rather than the octave.
    _pf = _pipes[75](523.25, 0.0, 1.0, 1.0)
    _evens = max(_pf.harmonic_volume(_k) / _pf.harmonic_volume(1) for _k in (2, 4, 6))
    check("the pan pipe is a CLOSED tube and the rest are open",
          _pipes[75].odd_only and _evens < 1e-6
          and not any(_pipes[_g].odd_only for _g in (72, 73, 74, 77, 78, 79)),
          "  (its evens are absent by construction; no other pipe's are)")
    # ...AND IT IS THE BREATH THAT WAS MISSING. StoppedPipeProperties ships
    # sustain_jitter = 0, so GM 75 rendered as a clean odd-harmonic tone -- an
    # organ's Gedackt rank, which is what that class is for and is not a pan
    # pipe. The player blows across an open tube top with no windway and no
    # labium; most of that jet never couples in, and the noise is most of the
    # sound.
    check("...and the breathy pipes are breathier than the ducted one",
          _pipes[75].sustain_jitter > 3.0 * _pipes[74].sustain_jitter
          and _pipes[77].sustain_jitter > _pipes[75].sustain_jitter,
          "  (recorder %.2f, pan pipe %.2f, shakuhachi %.2f)"
          % (_pipes[74].sustain_jitter, _pipes[75].sustain_jitter,
             _pipes[77].sustain_jitter))
    # A HUMAN WHISTLE IS A HELMHOLTZ RESONATOR, NOT A PIPE. One resonance tuned
    # by the tongue -- no registers, no overblowing, no fingering -- which is
    # why it is the closest thing to a sine a person makes. It belongs with the
    # ocarina and the bottle, where GM already put it.
    check("the whistle is a vessel, not a tube",
          issubclass(_pipes[78], _T.VesselFluteProperties)
          and not issubclass(_pipes[78], _T.BassFluteProperties),
          "  (with the ocarina and the bottle, which GM sits it between)")
    _wh = _pipes[78](523.25, 0.0, 1.0, 1.0)
    _h2 = 20.0 * math.log10(_wh.harmonic_volume(2) / _wh.harmonic_volume(1))
    check("...and is nearly a pure tone, as a whistled note is",
          _h2 < -25.0,
          "  (second harmonic %.1f dB; the flute's is -8.0)" % _h2)
    # THE DUCT IS THE RECORDER'S WHOLE DIFFERENCE from the flute beside it: a
    # windway cut in wood aims the same jet every time, where a flautist steers
    # theirs. So it is purer, and it keeps less breath past the edge.
    _rc = _pipes[74](523.25, 0.0, 1.0, 1.0)
    _fl = _pipes[73](523.25, 0.0, 1.0, 1.0)
    _dr = (20.0 * math.log10(_rc.harmonic_volume(2) / _rc.harmonic_volume(1))
           - 20.0 * math.log10(_fl.harmonic_volume(2) / _fl.harmonic_volume(1)))
    check("the ducted recorder is purer than the lip-blown flute",
          _dr < -1.5 and _pipes[74].sustain_jitter < _pipes[73].sustain_jitter,
          "  (%.1f dB less second harmonic, and less breath past the edge)" % _dr)

    # ---------------------------------------------------------- the synth leads
    import patch_map as _PMl
    # GM 82-87 all shared SynthLeadProperties, which is a FlueOrganProperties:
    # an organ pipe standing in for a synthesiser.
    _leads = {_g: _PMl.property_class_for_program(_g) for _g in range(80, 88)}
    check("each synth lead is its own voice, not one organ pipe",
          len({_c.__name__ for _c in _leads.values()}) == 8
          and not any(issubclass(_c, _T.FlueOrganProperties) for _c in _leads.values()),
          "  (eight distinct classes, none of them a pipe)")
    # THESE ARE THE ONE FAMILY WHOSE TARGET IS A SPECIFICATION. A sawtooth IS
    # the series at 1/n and a square IS the odd harmonics at 1/n -- there is no
    # object to measure, so the check is against the closed form and the
    # tolerance is floating point, not decibels.
    for _gm, _law, _nm in ((81, lambda n: 1.0 / n, "sawtooth"),
                           (80, lambda n: 1.0 / n if n % 2 else 0.0, "square"),
                           (82, lambda n: 1.0 / (n * n) if n % 2 else 0.0, "triangle")):
        _q = _leads[_gm](261.63, 0.0, 1.0, 1.0)
        _v1 = _q.harmonic_volume(1)
        _worst = max(abs(_q.harmonic_volume(_n) / _v1 - _law(_n) / _law(1))
                     for _n in range(1, 33))
        check("the %s is EXACTLY the %s series" % (_nm, _nm),
              _worst < 1e-12,
              "  (worst deviation over 32 partials %.1e)" % _worst)
    # AND ONE OSCILLATOR IS ONE OSCILLATOR. SawtoothSynthProperties' docstring
    # said the section shimmer was switched off and it was not: it inherits
    # BowedStringProperties, so section_players stayed at 7 and GM 80 and 81
    # shipped as seven oscillators 6 cents apart, each with its own vibrato --
    # a supersaw, which is a fine sound, is not a sawtooth, and cannot be
    # "exact". A docstring is not a test; this is the test.
    _plain = [_g for _g in (80, 81, 82, 83, 84, 85) if _leads[_g](261.63, 0.0, 1.0, 1.0)
              .unison_voices(261.63, 1, 0.0)]
    check("...and a single oscillator is not secretly a section",
          not _plain,
          "  (no extra voices on 80-85)" if not _plain
          else "  (still a section: %s)" % _plain)
    # THE TWO FIXED-INTERVAL LEADS are exactly specifiable and are the whole
    # difference between GM 86 and 87.
    def _iv(_g):
        _q = _leads[_g](440.0, 0.0, 1.0, 1.0)
        _vs = _q.unison_voices(440.0, 1, 0.0)
        return 1200.0 * math.log2(1.0 + _vs[0][2]) if _vs else None
    check("the fifths lead really is a TEMPERED fifth up",
          abs(_iv(86) - 700.0) < 0.01,
          "  (%+.1f cents; a just fifth would be +702.0, and a GM oscillator "
          "is offset in semitones)" % _iv(86))
    check("...and the bass lead an octave down",
          abs(_iv(87) + 1200.0) < 1e-6,
          "  (%+.1f cents, which is a ratio of 2 in any temperament)" % _iv(87))
    # AND THE SIX ARE DISTINGUISHED BY SOMETHING, not just by name.
    # THE INTERVAL, not merely whether there is one. The first version of this
    # check recorded "has an extra voice" as a boolean and so could not tell
    # GM 86 from GM 87 -- which are alike in having a second oscillator and
    # differ in nothing else, so a boolean collapsed exactly the pair the check
    # exists to separate. It failed, correctly, and this is the fix.
    def _second(_g):
        _vs = _leads[_g](261.63, 0.0, 1.0, 1.0).unison_voices(261.63, 1, 0.0)
        return round(1.0 + _vs[0][2], 4) if _vs else None
    _feat = {_g: (getattr(_leads[_g], "chiff_volume", 0.0) > 0.0,
                  getattr(_leads[_g], "amp_drive", 0.0) > 0.0,
                  bool(getattr(_leads[_g], "formants", ())),
                  _second(_g))
             for _g in range(83, 88)}
    check("...and chiff, charang, voice, fifths and bass each differ in kind",
          len(set(_feat.values())) == 5,
          "  (breath / valve / formants / +700c / -1200c, one each)")

    # ------------------------------------------------------- the brass section
    import patch_map as _PMb
    # GM 61 handed over from one instrument to the next at a SINGLE NOTE, so one
    # semitone across the C4 break moved the spectrum 13.2 dB on average and
    # 23.2 at the sixth harmonic, where a semitone inside one instrument moves
    # it 1.5 to 5.6. A real trumpet plays F#3-D6 and a trombone E2-F5: they
    # overlap by two octaves and a section has both on a unison line, so the
    # hard split was not modelling a section at all.
    _b = [_PMb.property_class_for_note(61, _n) for _n in range(54, 68)]
    check("the brass section hands over gradually, not at one note",
          len({_c.__name__ for _c in _b}) >= 6,
          "  (%d distinct bodies across the C4 handover, not 2)"
          % len({_c.__name__ for _c in _b}))
    # AND IT REALLY IS A BLEND, moving monotonically from one body to the other.
    # A crossfade that is not monotonic is a wobble, not a handover.
    _bells = [_PMb.property_class_for_note(61, _n).bell_cutoff_hz
              for _n in range(56, 64)]
    check("...and the body moves monotonically from trombone to trumpet",
          all(_bells[_i] <= _bells[_i + 1] + 1e-9 for _i in range(len(_bells) - 1))
          and _bells[-1] > _bells[0],
          "  (bell cutoff %.0f -> %.0f Hz over the handover)"
          % (_bells[0], _bells[-1]))
    # BOTH BREAKS, not just the one that was looked at.
    _lo = [_PMb.property_class_for_note(61, _n).__name__ for _n in range(34, 47)]
    check("...at the lower break too, not only the one that was measured",
          len(set(_lo)) >= 6,
          "  (%d distinct bodies across the E2 handover)" % len(set(_lo)))
    # AND THE ENDS ARE STILL THE INSTRUMENTS THEMSELVES. A blend everywhere
    # would leave no note sounding like a trumpet or a trombone, which is the
    # opposite failure and the reason the crossfade is six semitones and not
    # the full two-octave overlap.
    check("...while the ends are still a trumpet and a tuba",
          issubclass(_PMb.property_class_for_note(61, 84), _T.TrumpetProperties)
          and issubclass(_PMb.property_class_for_note(61, 24),
                         _T.ConicalBrassProperties),
          "  (%.0f semitones of blend, not the whole overlap)"
          % _PMb.BRASS_CROSSFADE_SEMITONES)
    # A FREQUENCY BLENDS IN THE LOG DOMAIN. Halfway between a conical 390 Hz
    # bell and a trumpet's 1600 is 790, not 995.
    _mid = _T.brass_blend(_T.ConicalBrassProperties, _T.TrumpetProperties, 0.5)
    _geo = (390.0 * 1600.0) ** 0.5
    check("...and a filter corner blends geometrically, not linearly",
          abs(_mid.bell_cutoff_hz - _geo) < 1.0,
          "  (%.0f Hz, where a linear blend would give %.0f)"
          % (_mid.bell_cutoff_hz, 0.5 * (390.0 + 1600.0)))

    # ------------------------------------------------- tremolo, pizz, harp
    import patch_map as _PMs
    # GM 45 and 46 were BOTH PluckedStringProperties, which has no `formants`
    # attribute at all -- so a pizzicato section and a harp rendered with no
    # body whatsoever. This is the same hole the acoustic bass was in, and the
    # check is written the way that one is: by asking for the attribute rather
    # than assuming a None default, which is the mistake that wrote it wrong
    # three times.
    for _gm, _what in ((45, "the pizzicato section"), (46, "the harp")):
        _c = _PMs.property_class_for_program(_gm)
        check("%s has a body at all" % _what,
              bool(getattr(_c, "formants", ())),
              "  (%s: %d formant%s)" % (_c.__name__.replace("Properties", ""),
                                        len(getattr(_c, "formants", ())),
                                        "" if len(getattr(_c, "formants", ())) == 1 else "s"))
    # THE PIZZ WEARS THE MEASURED BODY OF WHICHEVER INSTRUMENT THE REGISTER
    # PICKS. A pizzicato section is scored the way a bowed one is, so it splits
    # at the same notes -- but it is NOT bowed, so it takes those boundaries
    # through its own transform, which lends the PLUCKED class the bowed
    # instrument's box rather than the reverse. Checked through the ROUTER, not
    # the assignment: PROGRAM_CLASS[45] is only the no-note fallback, and
    # checking it is exactly the mistake GM 32 and GM 44 both punished.
    _pz_by_reg = [(_n, _PMs.property_class_for_note(45, _n)) for _n in (28, 40, 52, 64)]
    check("the pizzicato takes its body from the register, as the tremolo does",
          len({_c for _, _c in _pz_by_reg}) == 4,
          "  (%s)" % ", ".join(_c.__name__.replace("PizzProperties", "")
                               for _, _c in _pz_by_reg))
    # ...and each of those bodies is the MEASURED one, not an approximation of
    # it. The box is all that transfers: a body does not know how the string it
    # carries was set going.
    _want = ((28, _T.ContrabassProperties), (40, _T.CelloProperties),
             (52, _T.ViolaProperties), (64, _T.ViolinProperties))
    check("...and every one of them is the measured instrument's box",
          all(_PMs.property_class_for_note(45, _n).formants == _b.formants
              and _PMs.property_class_for_note(45, _n).bell_cutoff_hz == _b.bell_cutoff_hz
              for _n, _b in _want),
          "  (formants and bell cutoff carried across unchanged)")
    # ...but they are PLUCKED, not bowed. The transform must not have dragged
    # the bow along with the box.
    check("...while still being plucked and not bowed",
          all(issubclass(_PMs.property_class_for_note(45, _n),
                         _T.PluckedStringProperties)
              and not issubclass(_PMs.property_class_for_note(45, _n),
                                 _T.BowedStringProperties)
              for _n, _ in _want),
          "  (plucked lineage, with a bowed instrument's body)")
    # A BASS PIZZ RINGS AND A VIOLIN PIZZ SNAPS, from one law rather than four
    # numbers: the rate scales with the note's own register.
    _pzb = _PMs.property_class_for_note(45, 28)(41.2, 0.0, 1.0, 1.0)
    _pzt = _PMs.property_class_for_note(45, 76)(659.3, 0.0, 1.0, 1.0)
    check("...and a bass pizz rings far longer than a violin one",
          _pzb.decay_register_factor < 0.5 * _pzt.decay_register_factor,
          "  (rendered: 2.35 s at E1 against 0.42 at E5, to -30 dB)")
    # A PIZZ NOTE IS SHORT. This is most of what separates it from every other
    # plucked voice, and it was 2.2 s to -30 dB before it was measured.
    _pz = _PMs.property_class_for_program(45)
    _hp = _PMs.property_class_for_program(46)
    check("a pizzicato note dies and a harp note rings",
          _pz.decay_db > 10.0 * _hp.decay_db and _hp.decay_db < 1.0,
          "  (pizz %.1f dB/s, harp %.2f)" % (_pz.decay_db, _hp.decay_db))
    # A HARP IS PLUCKED IN TOWARD THE MIDDLE, which is the darkest place there
    # is: the comb's first null lands on a low partial and that, not a filter,
    # is why a harp is mellow.
    check("the harp is plucked near the middle, the pizz near the end",
          0.30 < _hp.strike_point < 0.45 and _pz.strike_point < 0.25,
          "  (harp nulls at h%.1f, pizz at h%.1f)"
          % (1.0 / _hp.strike_point, 1.0 / _pz.strike_point))
    # GM 44 IS AN ARTICULATION AND RIDES ON THE REGISTER'S BODY. A low tremolo
    # is a CELLO section bowing tremolo. A TremoloStringsProperties(Violin) was
    # written first and the per-note router silently overrode it -- 44 is in
    # BOWED_ENSEMBLE -- which is how that was caught. Check the router, never
    # the assignment: the same lesson GM 32 taught.
    _t_lo = _PMs.property_class_for_note(44, 40)
    _t_hi = _PMs.property_class_for_note(44, 72)
    check("tremolo strings ride on whichever body the register picks",
          _t_lo is not _t_hi
          and issubclass(_t_lo, _T.CelloProperties)
          and issubclass(_t_hi, _T.ViolinProperties),
          "  (E2 -> %s, C5 -> %s)" % (_t_lo.__name__.replace("Properties", ""),
                                      _t_hi.__name__.replace("Properties", "")))
    check("...and every one of them actually bows tremolo",
          all(getattr(_PMs.property_class_for_note(44, _n), "tremolo_depth", 0.0) > 0.0
              for _n in (36, 48, 60, 72, 84)),
          "  (%.1f Hz at every pitch, +/-%.0f%% per player)"
          % (_t_hi.tremolo_hz, 100 * _t_hi.tremolo_scatter))
    # AND IT MUST NOT BE CONFUSABLE WITH THE SECTION'S VIBRATO. A tremolo that
    # landed in the 4.6-6.4 Hz vibrato band would just read as a nervous player.
    check("...at a rate no one could mistake for vibrato",
          _t_hi.tremolo_hz > _t_hi.section_vibrato_hz[1] * 1.4,
          "  (tremolo %.1f Hz against vibrato %.1f-%.1f)"
          % ((_t_hi.tremolo_hz,) + tuple(_t_hi.section_vibrato_hz)))

    # ---------------------------------------------------------- free reeds
    # GM 20-23 were all rendering as ReedOrganProperties, which is a pipe
    # organ's reed RANK: a beating reed with a resonator behind it. All four are
    # FREE reeds -- a tongue swinging through a slot with no resonator at all.
    import patch_map as _PM
    _free = [_PM.property_class_for_program(g) for g in (20, 21, 22, 23)]
    check("the free reeds are not a pipe organ's reed rank",
          all(not issubclass(c, _T.ReedOrganProperties) for c in _free)
          and all(issubclass(c, _T.FreeReedProperties) for c in _free),
          "  (%s)" % ", ".join(c.__name__.replace("Properties", "") for c in _free))
    # ...and ReedOrganProperties itself must NOT have moved: it is the base of
    # ReedPipeProperties and of the clarinets, so repurposing it would have
    # taken the clarinet with it. This is the saxophone trap.
    check("...and the organ's reed rank is left exactly as it was",
          issubclass(_T.CylindricalReedProperties, _T.ReedOrganProperties)
          and _T.ReedOrganProperties.odd_only,
          "  (the clarinets still inherit it, and it is still odd-only)")
    # THE EVENS ARE THE WHOLE POINT. A stopped cylinder passes odd multiples, so
    # the rank has no evens by construction; nothing selects harmonics for a free
    # reed, so it has them. Measured at C4.
    _fr = _PM.property_class_for_program(20)(261.63, 0.0, 1.0, 1.0)
    _ev = [_fr.harmonic_volume(k) / _fr.harmonic_volume(1) for k in (2, 4, 6)]
    check("a free reed has even harmonics, which a stopped pipe cannot",
          all(e > 0.02 for e in _ev),
          "  (h2 %.1f, h4 %.1f, h6 %.1f dB; the organ rank's are absent)"
          % tuple(20.0 * math.log10(e) for e in _ev))
    # AND NO DEEP ZEROS. An idealised pulse train has true nulls -- at one point
    # in fitting this the 16th partial sat 57 dB down, a hole no free reed has.
    # Averaging over a spread of gate positions smears them; this is what
    # catches that spread being removed or zeroed.
    _worst = min((_fr.harmonic_volume(k) / _fr.harmonic_volume(1), k)
                 for k in range(2, 25))
    check("...and no zero anywhere in its series",
          _worst[0] > 10.0 ** (-55.0 / 20.0),
          "  (deepest partial h%d at %.1f dB)" % (_worst[1], 20.0 * math.log10(_worst[0])))
    # WET AGAINST DRY is the whole of GM 21 versus GM 23. An accordion's banks
    # are deliberately offset (musette); a bandoneon's are not.
    def _beat(g):
        q = _PM.property_class_for_program(g)(261.63, 0.0, 1.0, 1.0)
        return abs(261.63 * (1.0 + q.unison_voices(261.63, 1, 0.0)[0][2]) - 261.63)
    _wet, _dry = _beat(21), _beat(23)
    check("the accordion is tuned wet and the bandoneon dry",
          _wet > 3.0 * _dry and _wet > 1.0,
          "  (musette beats at %.2f Hz, tango at %.2f)" % (_wet, _dry))

    check("the acoustic bass is not the generic plucked string",
          _PM.property_class_for_program(32) is _T.AcousticBassProperties)
    ab, cb2 = _T.AcousticBassProperties, _T.ContrabassProperties
    # GM 32 and GM 43 are THE SAME INSTRUMENT: arco against pizzicato is an
    # excitation, not a body. So the measured contrabass body is copied over.
    check("...and wears the measured contrabass's body, being the same instrument",
          ab.formants == cb2.formants and ab.bore_corner_hz == cb2.bore_corner_hz
          and ab.bell_cutoff_hz == cb2.bell_cutoff_hz,
          "  (the Iowa double bass, fitted across three registers)")
    # COPIED, NOT INHERITED. The contrabass is bowed -- driven, so decay_db is
    # zero and it sustains as long as the bow moves. Subclassing it would claim
    # a plucked instrument is a driven one.
    check("...but is PLUCKED, so it does not inherit a bowed class",
          issubclass(ab, _T.PluckedStringProperties)
          and not issubclass(ab, _T.BowedStringProperties)
          and cb2.decay_db == 0.0 and ab.decay_db > 0.0,
          "  (the bow sustains at %.1f dB/s; the pluck decays at %.1f)"
          % (cb2.decay_db, ab.decay_db))
    # The pluck point: a quarter of the way from the bridge, where the hand goes
    # at the end of the fingerboard, so the comb nulls at the 4th where a
    # guitar's nulls at the 7th. That low notch is why pizzicato is dark.
    _lv = [ab(82.4, 0.0, 1.0, 1.0).harmonic_volume(h) for h in range(1, 10)]
    _db = [20 * _math.log10(max(v, 1e-15) / _lv[0]) for v in _lv]
    check("...plucked a quarter along, so the comb nulls at the 4th partial",
          ab.strike_point == 0.25 and _db[3] < _db[2] - 5.0 and _db[3] < _db[4] - 5.0
          and _db[7] < _db[6] - 5.0,
          "  (h3 %+.0f, h4 %+.0f, h5 %+.0f dB -- and h8 %+.0f)"
          % (_db[2], _db[3], _db[4], _db[7]))
    # AND IT USES strike_point, NOT plucked_harmonic. The latter is the legacy
    # path and is not a pluck POSITION: it builds divisor entries for 1..P-1, so
    # setting it to 4 zeroed every 6th partial. Measured, and then fixed.
    check("...using the physical comb and not the legacy divisor list",
          ab.strike_point is not None and _db[5] > _db[3],
          "  (h6 %+.0f dB, which the legacy path silenced entirely)" % _db[5])

    # ---- the steel-string, which had no body at all --------------------------
    check("the steel-string guitar is not the generic plucked string",
          _PM.property_class_for_program(25) is _T.SteelGuitarProperties
          and issubclass(_T.SteelGuitarProperties, _T.NylonGuitarProperties))
    st, ny, gen = (_T.SteelGuitarProperties, _T.NylonGuitarProperties,
                   _T.PluckedStringProperties)
    # THE DEFECT WAS NOT SUBTLE: the generic string has formants None and a zero
    # bore corner, so GM 25 rendered as a bare string in free air, next door to
    # the one guitar in the set with a measured body.
    # The generic string is not a FormantBody AT ALL -- it has no `formants`
    # attribute to be None -- and harmonic_volume returns early on its zero
    # bore corner, so no body is ever applied.
    check("...and it now has a body, which the generic one has none of",
          issubclass(st, _T.FormantBody) and st.formants == ny.formants
          and not issubclass(gen, _T.FormantBody) and gen.bore_corner_hz == 0.0,
          "  (the measured classical's body, inherited unshifted)")
    # Steel's low internal loss against nylon's viscoelasticity. The largest of
    # the differences and the reason the instrument rings.
    check("...whose high partials survive, where nylon eats its own",
          st.harmonic_decay_db < ny.harmonic_decay_db * 0.7,
          "  (%.2f against %.2f dB/s per mode)" % (st.harmonic_decay_db, ny.harmonic_decay_db))
    # The nylon MEASURED nothing above 8 kHz, -46 to -61 dB. A steel-string's
    # bronze basses put real energy up there; that is the target.
    def _above(cls, k=8000.0):
        tot = hi = 0.0
        for f0 in (82.4, 110.0, 146.8, 196.0, 246.9, 329.6):
            q = cls(f0, 0.0, (100 / 127.0) ** 2, 1.0)
            for h in range(1, q.max_harmonic + 1):
                v = q.harmonic_volume(h)
                if v <= 0:
                    continue
                tot += v * v
                if f0 * h >= k:
                    hi += v * v
        return 10 * _math.log10(max(hi, 1e-30) / tot)
    check("...and real energy above 8 kHz, where the classical measured none",
          _above(st) > _above(ny) + 8.0,
          "  (%+.1f dB against the nylon's %+.1f)" % (_above(st), _above(ny)))
    # AND THE OBVIOUS DERIVATION IS A DEAD END, recorded so nobody repeats it:
    # steel's modulus is ~50x nylon's, but a steel string for the same note is
    # less than half the diameter and d enters SQUARED. 35%, not 50x.
    check("...with inharmonicity only 35% up, which is the whole of that story",
          abs(st.inharmonicity_coefficient / ny.inharmonicity_coefficient - 1.35) < 0.01,
          "  (x%.2f -- the modulus and the gauge nearly cancel)"
          % (st.inharmonicity_coefficient / ny.inharmonicity_coefficient))

    # ---- the honky-tonk: the same piano, badly tuned -------------------------
    check("the honky-tonk is the grand with the tuner's hand off",
          _PM.property_class_for_program(3) is _T.HonkyTonkProperties
          and issubclass(_T.HonkyTonkProperties, _T.GrandPianoProperties))
    ht, gp = _T.HonkyTonkProperties, _T.GrandPianoProperties
    # The VOICE is one number. Everything else on the class is the wheel.
    _tonal = [k for k in ht.__dict__
              if not k.startswith("_") and k not in ("detune_wheel",)]
    check("...and it needed no new mechanism, only a wider range",
          ht.string_detune_range[0] > gp.string_detune_range[1] * 4.0
          and _tonal == ["string_detune_range"],
          "  (grand %.1f-%.1f cents, honky-tonk %.1f-%.1f, and that is the whole voice)"
          % (gp.string_detune_range + ht.string_detune_range))
    # THE BEAT RATE IS NOT SET ANYWHERE. Two strings a fixed number of CENTS
    # apart beat proportionally to pitch, so one range gives a slow fat wobble
    # in the bass and a fast nervous one at the top, for free.
    def _beat(f):
        q = ht(f, 0.0, 1.0, 1.0)
        return max(f * (2.0 ** (abs(c) / 1200.0) - 1.0) for c in q.note_detune_cents)
    lo_b, hi_b = _beat(65.4), _beat(1046.5)
    check("...and the beat rate follows the pitch rather than being chosen",
          hi_b > 8.0 * lo_b,
          "  (%.2f Hz at C2, %.1f Hz at C6 -- from the same cents)" % (lo_b, hi_b))
    # The main string stays AT PITCH and carries the gain; the extras straddle
    # it. So a honky-tonk jangles without going out of tune, which matters --
    # it still has to play with the rest of the orchestra.
    q = ht(440.0, 0.0, 1.0, 1.0)
    w = [1.0] + list(q.string_gain[:len(q.note_detune_cents)])
    c = [0.0] + list(q.note_detune_cents)
    centre = sum(wi * ci for wi, ci in zip(w, c)) / sum(w)
    check("...and the note itself stays in tune, because the extras straddle it",
          abs(centre) < 4.0,
          "  (gain-weighted centre %+.1f cents off, from %+.0f/%+.0f)"
          % (centre, c[1], c[2]))
    # And the bass cannot wobble at all: the stringing is a single wound
    # monochord down there, so there is no second string to mistune.
    check("...while the bass stays clean, having only one string to begin with",
          q.string_count_for_frequency(41.2) == 1 < q.string_count_for_frequency(440.0),
          "  (%d string at E1, %d at A4)"
          % (q.string_count_for_frequency(41.2), q.string_count_for_frequency(440.0)))

    # CC1 IS HOW FAR OUT OF TUNE, with 64 -- and no wheel at all -- the voice's
    # own range. Unlike the clavinet's rockers this cannot be a gain on a note
    # already sounding: a detune is in the partials' FREQUENCIES, so it is a
    # different template. The axis for that already existed and is literally
    # "the CC1 value to build with", so the positions are pre-warmed.
    lvh = Live(program=3, rate=48000, frames=128, verbose=False); lvh.warm()
    bh = lvh.parts[0].bank
    check("the honky-tonk's wheel is pre-warmed, so sweeping cannot miss",
          bh.detune_wheel and tuple(bh.speeds) == DETUNE_STEPS
          and bh.leslie_default == DETUNE_STEPS[len(DETUNE_STEPS) // 2]
          and all(bh.get(69, 100, v) is not None for v in DETUNE_STEPS),
          "  (positions %s, default %s)" % (DETUNE_STEPS, bh.leslie_default))

    def _unison(cc):
        t = bh.get(69, 100, cc)
        nf = np.asarray(t["nf"])
        u = np.unique(np.round(nf[nf < nf.min() * 1.05], 3))
        mid = u[len(u) // 2]
        return [1200 * _math.log2(v / mid) for v in u]

    spread = [max(_unison(v)) - min(_unison(v)) for v in DETUNE_STEPS]
    check("...and it really moves the strings, not just the template key",
          spread[0] < 0.01 and spread[1] > 25.0 and spread[2] > 1.8 * spread[1],
          "  (unison spread %.1f / %.1f / %.1f cents across the three)" % tuple(spread))
    # The zero position is a piano somebody has just tuned, which is a useful
    # thing to be able to ask for and a sharp test that the wheel reaches.
    check("...with the wheel down giving one string and no beating at all",
          len(_unison(DETUNE_STEPS[0])) == 1,
          "  (the unison collapses to a single in-tune string)")
    lvh.renderer.close()

    # ---- the electric grand: a CP-70 is a short piano with no board ---------
    check("the electric grand is not the acoustic one",
          _PM.property_class_for_program(2) is _T.ElectricGrandProperties
          and issubclass(_T.ElectricGrandProperties, _T.GrandPianoProperties),
          "  (still a piano: same hammers, same action, same strike comb)")
    eg = _T.ElectricGrandProperties(261.63, 0.0, 1.0, 1.0)
    ag = _T.GrandPianoProperties(261.63, 0.0, 1.0, 1.0)
    # B goes as 1/L^4 at fixed pitch, and at constant stress L = C/f until the
    # case runs out -- so two pianos of different size can differ ONLY where the
    # shorter one binds. That predicts a knee, not a tilt.
    _b = lambda q, f: q.inharmonicity_coefficient_for_frequency(f)
    knee = eg.scale_constant_hz_m / eg.case_string_max_m
    check("...and its bass is far stiffer, because its strings are short",
          _b(eg, 41.2) > 8.0 * _b(ag, 41.2),
          "  (%.1fx at E1, ceiling %.1fx)"
          % (_b(eg, 41.2) / _b(ag, 41.2),
             (eg.reference_string_max_m / eg.case_string_max_m) ** 4))
    check("...while ABOVE the knee the two are identical, as the scaling says",
          abs(_b(eg, knee * 1.4) / _b(ag, knee * 1.4) - 1.0) < 1e-9
          and abs(_b(eg, 1046.5) / _b(ag, 1046.5) - 1.0) < 1e-9,
          "  (the CP-70's case binds below %.0f Hz; above that, same string)" % knee)
    # A piezo under the bridge is not a soundboard: no body resonance, and above
    # all no sub-bass RADIATION loss, which is the term a board has and a pickup
    # cannot. That is why an electric grand has more bottom, not less.
    check("...and no soundboard, so it keeps the bass a board cannot radiate",
          eg.soundboard_gain(35.0) / eg.soundboard_gain(400.0)
          > 1.6 * (ag.soundboard_gain(35.0) / ag.soundboard_gain(400.0)),
          "  (35 Hz against 400: %+.1f dB, where the board gives %+.1f)"
          % (20 * _math.log10(eg.soundboard_gain(35.0) / eg.soundboard_gain(400.0)),
             20 * _math.log10(ag.soundboard_gain(35.0) / ag.soundboard_gain(400.0))))
    # The +6 dB/octave of bridge force is DERIVED and deliberately not applied;
    # if somebody switches it on, they should have to mean it.
    check("...and the derived bridge tilt is recorded, not spent",
          eg.bridge_force_power == 0.0 and hasattr(eg, "bridge_force_power"),
          "  (bridge force goes as n*A_n, but the A_n here is a generic tilt)")

    def _rh(f0=261.63, vel=100, cls=_T.RhodesProperties):
        return cls(f0, 0.0, (vel / 127.0) ** 2, 1.0)

    rp = _rh()
    # A waveshaped SINE gives back an exactly harmonic series -- no stiffness,
    # no stretch. A tine is not a string and has neither.
    worst = max(abs(rp.mode_ratio(h) - h) for h in range(1, rp.pickup_harmonics + 1))
    check("a tine's partials are exactly harmonic, unlike a string's",
          worst < 1e-12 and rp.inharmonicity_coefficient == 0.0,
          "  (worst departure %.1e)" % worst)

    # THE SHARPEST CLAIM THE MEASUREMENTS MAKE: "when aligned perfectly centered,
    # the produced sound behind the pickup is twice the fundamental of the tine".
    class _Centred(_T.RhodesProperties):
        pickup_offset = 0.0
    cen = _rh(cls=_Centred)
    ratio = cen.harmonic_volume(1) / cen.harmonic_volume(2)
    check("centre the tine and the fundamental disappears",
          ratio < 1e-6 and cen.harmonic_volume(2) > 0.0,
          "  (h1 %.0f dB under h2; offset 0.30 gives %+.1f)"
          % (20 * _math.log10(max(ratio, 1e-300)),
             20 * _math.log10(rp.harmonic_volume(1) / rp.harmonic_volume(2))))

    # Harmonic k of a waveshaped sine goes as A^k, so it must decay k times as
    # fast as the deflection does. This is the engine's own law with decay_db
    # and harmonic_decay_dampening at zero -- if either drifts off zero, the
    # growl stops decaying into the bell and this catches it.
    d1 = rp.harmonic_decay(1)
    err = max(abs(rp.harmonic_decay(k) / d1 - k) for k in range(1, rp.pickup_harmonics + 1))
    check("harmonic k decays k times as fast as the tine",
          err < 1e-9, "  (worst ratio error %.1e)" % err)

    def _band(cls, f0=261.63, vel=100, hmax=8):
        """Level and growl over a FIXED band. The series is trimmed where the
        curve dies, so max_harmonic moves with velocity -- summing "all of
        them" at two velocities would compare two different bands."""
        q = cls(f0, 0.0, (vel / 127.0) ** 2, 1.0)
        top = getattr(q, "pickup_harmonics", q.max_harmonic)
        v = [q.harmonic_volume(h) if h <= top else 0.0 for h in range(1, hmax + 1)]
        tot = _math.sqrt(sum(x * x for x in v))
        up = _math.sqrt(sum(x * x for x in v[1:]))
        return 20 * _math.log10(tot), 20 * _math.log10(up / v[0])

    def _growl(f0=261.63, vel=100):
        return _band(_T.RhodesProperties, f0, vel)[1]

    # "Velocity sensitivity is to be distinguished by a change in volume to
    # lesser extent than in sound." A hammer sets the tine's DEFLECTION and the
    # coil reads deflection linearly, so the level follows velocity and NOT its
    # square. Measured against a piano over the same velocity range, which is
    # the comparison that makes the claim mean something.
    plo, phi = _band(_T.GrandPianoProperties, vel=35), _band(_T.GrandPianoProperties, vel=127)
    rlo, rhi = _band(_T.RhodesProperties, vel=35), _band(_T.RhodesProperties, vel=127)
    check("velocity changes a Rhodes' volume half as much as a piano's",
          (rhi[0] - rlo[0]) < 0.5 * (phi[0] - plo[0]),
          "  (%+.1f dB against the piano's %+.1f)"
          % (rhi[0] - rlo[0], phi[0] - plo[0]))
    check("...and its timbre far more, which is what the tine is for",
          (rhi[1] - rlo[1]) > 8.0 > (phi[1] - plo[1]),
          "  (growl %.1f -> %.1f dB; the piano's goes %.1f -> %.1f)"
          % (rlo[1], rhi[1], plo[1], phi[1]))

    # "Best audible in the lower register, where the tines have a larger
    # deflection."
    check("the growl is a bass-register effect",
          _growl(65.4) > _growl(261.6) + 4.0 > _growl(1046.5) + 8.0,
          "  (C2 %+.1f, C4 %+.1f, C6 %+.1f dB)"
          % (_growl(65.4), _growl(261.6), _growl(1046.5)))

    # The tonebar is NOT tuned to the tine and is NOT in the sustain: its own
    # eigenfrequencies "only appear in the transient".
    tb = [h for h in range(1, rp.max_harmonic + 1) if h > rp.pickup_harmonics]
    check("the tonebar lives in the transient and nowhere else",
          len(tb) == len(rp.tonebar_gains)
          and all(rp.harmonic_decay(h) > 100.0 * d1 for h in tb)
          and all(abs(rp.mode_ratio(h) - round(rp.mode_ratio(h))) > 1e-6
                  or rp.mode_ratio(h) < 1.0 for h in tb),
          "  (%d modes at %.0f dB/s against the tine's %.1f)"
          % (len(tb), rp.harmonic_decay(tb[0]), d1))

    # A Rhodes has a speaker, and it is not a guitar's: it has to reach a 55 Hz
    # fundamental where a guitar 12" has already given up.
    import cabinet as _CAB
    check("the Rhodes has its own cabinet, not the guitar's",
          rp.cabinet == "rhodes" and rp.amp_drive == 0.0
          and _CAB.get("rhodes").gain(55.0) > _CAB.get("guitar12").gain(55.0),
          "  (%.1f dB at 55 Hz against the guitar's %.1f)"
          % (20 * _math.log10(_CAB.get("rhodes").gain(55.0)),
             20 * _math.log10(_CAB.get("guitar12").gain(55.0))))

    # It is cheap, and it gets cheaper when played softly -- the curve's tail
    # falls below audibility and those partials are never emitted.
    check("a Rhodes note costs a fraction of a piano note",
          _rh(vel=127).max_harmonic < 30 and _rh(vel=35).max_harmonic < _rh(vel=127).max_harmonic,
          "  (%d partials at v127, %d at v35)"
          % (_rh(vel=127).max_harmonic, _rh(vel=35).max_harmonic))

    # ---- and the suitcase's pan vibrato -------------------------------------
    lv = Live(program=4, rate=48000, frames=128, verbose=False); lv.warm()

    def _pump(sec, cc=None):
        Ls, Rs = [], []
        for i in range(int(sec * 48000) // 128):
            if cc is not None and i == 2:
                lv.on_midi(mido.Message("control_change", channel=0, control=1, value=cc))
            b, _f = lv.callback(None, 128, None, 0)
            x = np.frombuffer(b, np.float32)
            Ls.append(x[0::2]); Rs.append(x[1::2])
        return np.concatenate(Ls).astype(float), np.concatenate(Rs).astype(float)

    def _swing(v, rate=5.5, sr=48000.0):
        """Depth and phase of the modulation, with the note's DECAY taken out.
        The decay is 30-odd dB of the envelope and it is not the effect; left
        in, both ears track it together and a pan reads as correlated."""
        e = np.convolve(np.abs(v), np.ones(256) / 256, 'same')[int(0.3 * sr):]
        t = np.arange(len(e)) / sr
        e = np.log(np.maximum(e, 1e-12))
        e = e - np.polyval(np.polyfit(t, e, 3), t)
        W = np.hanning(len(e))
        F = np.fft.rfft(e * W); fr = np.fft.rfftfreq(len(e), 1 / sr)
        k = int(np.argmin(np.abs(fr - rate)))
        return 20 * _math.log10(_math.e) * 2 * abs(F[k]) / (W.sum() / 2), np.angle(F[k])

    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100)); lv.apply(0)
    L, R = _pump(2.0, cc=127)
    dl, pl = _swing(L); dr, pr = _swing(R); dm, _pm = _swing((L + R) / 2.0)
    deg = _math.degrees((pl - pr + _math.pi) % (2 * _math.pi) - _math.pi)
    check("the wheel swings the suitcase's two amplifiers",
          dl > 6.0 and dr > 6.0, "  (%.1f dB each ear at 5.5 Hz)" % dl)
    check("...in opposition, because it is a PAN and not a tremolo",
          abs(abs(deg) - 180.0) < 5.0 and dm < 1.0,
          "  (%.0f deg apart, %.2f dB left in mono)" % (deg, dm))
    check("...and the wheel is not ALSO bending the pitch",
          lv.mod.get(0, 0.0) == 0.0 and lv.parts[0].bank.amp_drive == 0.0)
    lv.renderer.close()

    lv = Live(program=4, rate=48000, frames=128, verbose=False); lv.warm()
    lv.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100)); lv.apply(0)
    L, R = _pump(2.0)
    check("a wheel left at rest leaves the panel switched off",
          _swing(L)[0] < 0.5, "  (%.2f dB at 5.5 Hz)" % _swing(L)[0])
    # Arming twice must not save an already-modulated amplitude: that would
    # compound the swing every time the wheel moved.
    lv.on_midi(mido.Message("control_change", channel=0, control=1, value=100))
    _pump(0.3)
    base = lv.slab.tr_aL[np.flatnonzero(lv.slab.tr_on & lv.slab.busy)].copy()
    for v in (60, 127, 90):
        lv.on_midi(mido.Message("control_change", channel=0, control=1, value=v))
        _pump(0.2)
    now = lv.slab.tr_aL[np.flatnonzero(lv.slab.tr_on & lv.slab.busy)]
    drift = float(np.max(np.abs(now - base))) if len(base) == len(now) else 1.0
    check("moving the wheel does not compound the swing",
          drift < 1e-9, "  (base amplitude drifted %.1e over four moves)" % drift)
    lv.renderer.close()

    # ---- the Wurlitzer: one mechanism, a different curve --------------------
    check("the Wurlitzer is not a piano either",
          _PM.property_class_for_program(5) is _T.WurlitzerProperties)
    wp = _rh(261.63, 127, _T.WurlitzerProperties)
    rp2 = _rh(261.63, 127)
    # A Gaussian is entire and its harmonics collapse faster and faster; 1/d has
    # a pole and its harmonics fall off GEOMETRICALLY. That straight line in dB
    # is the bark, and it is the whole difference between the two instruments.
    def _lad(q, n=6):
        return [20 * _math.log10(max(q.harmonic_volume(h), 1e-300) / q.harmonic_volume(1))
                for h in range(1, n + 1) if h <= q.pickup_harmonics]
    lw, lr = _lad(wp), _lad(rp2)
    # the Rhodes' steps GROW; the Wurlitzer's stay about the same size
    dw = [lw[i] - lw[i + 1] for i in range(len(lw) - 1)]
    dr = [lr[i] - lr[i + 1] for i in range(len(lr) - 1)]
    check("a pole falls off geometrically where a bell curve falls off a cliff",
          max(dw) - min(dw) < 5.0 and max(dr) - min(dr) > 8.0,
          "  (Wurlitzer steps %.0f-%.0f dB, Rhodes %.0f-%.0f)"
          % (min(dw), max(dw), min(dr), max(dr)))
    check("...so it keeps its upper harmonics and barks",
          wp.harmonic_volume(5) / wp.harmonic_volume(1)
          > 20.0 * rp2.harmonic_volume(5) / rp2.harmonic_volume(1),
          "  (h5 at %.0f dB against the Rhodes' %.0f)"
          % (_lad(wp, 5)[-1], _lad(rp2, 5)[-1] if len(_lad(rp2, 5)) >= 5 else float('nan')))
    # A magnet is symmetric about the tine, so centring it kills the fundamental.
    # A capacitor plate is on ONE side, so there is no centred case to find.
    class _WC(_T.WurlitzerProperties):
        pickup_offset = 0.0
    wc = _rh(261.63, 100, _WC)
    check("a one-sided plate is asymmetric wherever the reed sits",
          wc.harmonic_volume(1) > wc.harmonic_volume(2) > 0.0,
          "  (h1 %+.1f dB over h2 at rest position 0, where the tine loses it entirely)"
          % (20 * _math.log10(wc.harmonic_volume(1) / wc.harmonic_volume(2))))
    check("a free reed has no tonebar to ring",
          wp.tonebar_gains == () and wp.max_harmonic == wp.pickup_harmonics
          and len(rp2.tonebar_gains) > 0)
    check("and its own speaker, which does not reach",
          wp.cabinet == "wurlitzer"
          and _CAB.get("wurlitzer").gain(80.0) < 0.3 * _CAB.get("rhodes").gain(80.0),
          "  (%.0f dB at 80 Hz against the suitcase's %+.0f)"
          % (20 * _math.log10(_CAB.get("wurlitzer").gain(80.0)),
             20 * _math.log10(_CAB.get("rhodes").gain(80.0))))
    check("its tremolo survives a mono fold, where the suitcase's pan does not",
          wp.tremolo_stereo is False and rp2.tremolo_stereo is True)

    # ---- the clavinet, which is not a harpsichord ---------------------------
    check("the clavinet is not a harpsichord",
          _PM.property_class_for_program(7) is _T.ClavinetProperties
          and _PM.property_class_for_program(6) is _T.HarpsichordProperties)
    cv = _T.ClavinetProperties(261.63, 0.0, (100 / 127.0) ** 2, 1.0)
    hc = _T.HarpsichordProperties(261.63, 0.0, (100 / 127.0) ** 2, 1.0)
    # It is STRUCK, and struck essentially at the termination -- the tangent
    # traps the string against the anvil -- so its comb RISES through the
    # audible range instead of notching inside it.
    check("...it is struck at the string's own end, so the comb rises",
          cv.strike_point > 0.0 and 1.0 / cv.strike_point > 24.0
          and cv.strike_fills_with_force is False,
          "  (first null at partial %.0f; a piano notches at %.0f)"
          % (1.0 / cv.strike_point, 1.0 / _T.GrandPianoProperties.strike_point))
    up = lambda q: 10 * _math.log10(sum((q.harmonic_volume(h) / q.harmonic_volume(1)) ** 2
                                        for h in range(2, 17)))
    check("...which makes it buzz where a harpsichord rings",
          up(cv) > up(hc) + 3.0,
          "  (%+.1f dB above the fundamental against %+.1f)" % (up(cv), up(hc)))
    # THE MAGNET, which the harpsichord voice it borrowed did not have at all.
    check("...and it has pickups, which the harpsichord has none of",
          cv.pickup_points and cv.pickup_velocity is True
          and not _T.HarpsichordProperties.pickup_points)
    # And the pickup's FRACTION moves with pitch, because the magnet is fixed in
    # space while the speaking length is set per note by where the tangent lands.
    # No other voice here does this: a guitar's nut is fixed, so its fraction is.
    lo = _T.ClavinetProperties(65.4, 0.0, 1.0, 1.0).pickup_points[0]
    hi = _T.ClavinetProperties(1046.5, 0.0, 1.0, 1.0).pickup_points[0]
    check("...whose fraction climbs toward the treble, unlike any other voice",
          hi > lo * 1.8 and _T.ElectricGuitarProperties.pickup_points
          == _T.ElectricGuitarProperties(82.4, 0.0, 1.0, 1.0).pickup_points,
          "  (%.3f at C2, %.3f at C6; a guitar's does not move)" % (lo, hi))
    # The paper: the key, its rebound and the tangent on the anvil mask the
    # string's own onset. So the click is the machine, and it grows with force.
    check("...and its click is the machine, not the string",
          cv.chiff_volume > 0.0 and cv.strike_noise_slope > 0.0
          and cv.chiff_max_valve_time < 0.01,
          "  (%.0f ms of broadband, rising with velocity)" % (1000 * cv.chiff_max_valve_time))

    # ---- and the tone rockers on the wheel ----------------------------------
    # Six switches sit left of a D6's keyboard; four of them are the tone
    # section, so the wheel sweeps those four. The other two select the pickups
    # and are NOT on it -- that changes the comb, which is a template.
    check("the clavinet's tone rockers are a ladder, dark to bright",
          len(_T.CLAV_TONE) >= 4 and _T.CLAV_TONE[_T.CLAV_FLAT][1] == 0.0,
          "  (%s)" % " < ".join(n for n, _c, _o, _h in _T.CLAV_TONE))
    _cf = [_T.clav_tone_gain(4000.0, i) / max(_T.clav_tone_gain(250.0, i), 1e-9)
           for i in range(len(_T.CLAV_TONE))]
    check("...and each rung is brighter than the one below it",
          all(_cf[i] < _cf[i + 1] for i in range(len(_cf) - 1)),
          "  (4 kHz against 250 Hz: %s)" % ", ".join("%.2f" % v for v in _cf))

    def _clav(cc, flip=None, t0=0.02, t1=0.14):
        """One fresh instrument per reading. Stamping every note at absolute
        sample 0 while the stream clock advances plays each one from the middle
        of its own envelope, which is how this probe first read the ladder
        backwards."""
        lvc = Live(program=7, rate=48000, frames=128, verbose=False); lvc.warm()
        if cc is not None:
            lvc.on_midi(mido.Message("control_change", channel=0, control=1, value=cc))
        lvc.on_midi(mido.Message("note_on", channel=0, note=48, velocity=112))
        lvc.apply(lvc.n)
        out = []
        for i in range(int(0.75 * 48000) // 128):
            if flip is not None and i == int(0.25 * 48000) // 128:
                lvc.on_midi(mido.Message("control_change", channel=0, control=1, value=flip))
            b, _f = lvc.callback(None, 128, None, 0)
            out.append(np.frombuffer(b, np.float32)[0::2])
        x = np.concatenate(out).astype(float)
        lvc.renderer.close()
        def cen(a0, a1):
            a, b = int(a0 * 48000), int(a1 * 48000)
            X = np.abs(np.fft.rfft(x[a:b] * np.hanning(b - a)))
            fr = np.fft.rfftfreq(b - a, 1 / 48000.0)
            k = (fr > 80) & (fr < 14000)
            return float((fr[k] * X[k]).sum() / X[k].sum())
        return cen(t0, t1), cen

    cens = [_clav(cc)[0] for cc in (0, 32, 64, 96, 127)]
    check("the wheel sweeps them, and the render follows",
          all(cens[i] < cens[i + 1] for i in range(len(cens) - 1)),
          "  (%s Hz)" % " ".join("%.0f" % v for v in cens))
    _c, cen = _clav(64, flip=0)
    before, after = cen(0.05, 0.22), cen(0.30, 0.60)
    check("...and it reaches a note already ringing, as a rocker does",
          after < before * 0.7,
          "  (%.0f Hz -> %.0f when the wheel is flipped mid-note)" % (before, after))
    # Sweeping back and forth must recompute from the unfiltered template and
    # never from what is already there.
    lvq = Live(program=7, rate=48000, frames=128, verbose=False); lvq.warm()
    lvq.on_midi(mido.Message("control_change", channel=0, control=1, value=127))
    lvq.on_midi(mido.Message("note_on", channel=0, note=48, velocity=112)); lvq.apply(lvq.n)
    for _i in range(6):
        lvq.callback(None, 128, None, 0)
    base = lvq.slab.cv_aL[np.flatnonzero(lvq.slab.cv_on & lvq.slab.busy)].copy()
    for v in (0, 127, 40, 100, 0):
        lvq.on_midi(mido.Message("control_change", channel=0, control=1, value=v))
        lvq.callback(None, 128, None, 0)
    now = lvq.slab.cv_aL[np.flatnonzero(lvq.slab.cv_on & lvq.slab.busy)]
    drift = float(np.max(np.abs(now - base))) if len(base) == len(now) and len(base) else 1.0
    check("...and sweeping it cannot compound",
          drift < 1e-9, "  (unfiltered base drifted %.1e over five moves)" % drift)
    check("...and the wheel is not ALSO bending the pitch on this voice",
          lvq.mod.get(0, 0.0) == 0.0)
    lvq.renderer.close()

    # ---- the cuica, which is not struck at all ------------------------------
    import percussion_map as _PM2
    check("a cuica is not the generic struck membrane",
          _PM2.PERCUSSION[79][1] is _T.CuicaProperties
          and _PM2.PERCUSSION[78][1] is _T.MuteCuicaProperties
          and not issubclass(_T.CuicaProperties, _T.PercussionProperties),
          "  (and not under PercussionProperties, whose docstring says struck)")
    cu = _T.CuicaProperties(260.0, 0.0, 1.0, 1.0)
    # Driven, so it rings while it is driven. A struck membrane's fast decay was
    # modelling the wrong thing entirely.
    check("...it is driven, so it sustains rather than decays",
          cu.decay_db == 0.0 and cu.harmonic_decay_db == 0.0 and cu.one_shot is False)
    # A sawtooth drive, as on a bowed string: harmonics go as 1/n.
    h2 = 20 * _math.log10(cu.harmonic_volume(2) / cu.harmonic_volume(1))
    h4 = 20 * _math.log10(cu.harmonic_volume(4) / cu.harmonic_volume(1))
    check("...with a sawtooth's 1/n series, like the bowed string it resembles",
          abs(h2 + 6.0) < 0.6 and abs(h4 + 12.0) < 0.8,
          "  (h2 %.1f dB, h4 %.1f)" % (h2, h4))
    # DRIVEN AT THE CENTRE, so only the axisymmetric modes can speak: every mode
    # with an angular node has a node exactly where the stick is tied. These are
    # j(0,n)/j(0,1), and they are what the onset must depart to.
    AXI = (1.0, 2.29542, 3.59848, 4.90334, 6.20875)
    got = [h * (1.0 + cu.mode_lock_offset_for(h)) for h in range(1, 6)]
    worst = max(abs(g - w) for g, w in zip(got, AXI))
    check("...and its onset is the AXISYMMETRIC membrane, not the whole Bessel set",
          worst < 0.01 and cu.mode_ratios is None,
          "  (worst %.4f against j(0,n)/j(0,1); %s)"
          % (worst, "steady tone harmonic" if cu.mode_ratios is None else "STEADY IS NOT HARMONIC"))
    # ...but because it is driven it mode-locks, so the STEADY tone is harmonic,
    # exactly the argument the organ pipes make.
    check("...which the drive then pulls into a harmonic tone",
          cu.mode_lock_spread > 0.0 and cu.mode_lock_time > 0.0
          and all(cu.mode_ratio(h) == float(h) for h in range(1, 8)),
          "  (locks in %.0f ms)" % (1000 * cu.mode_lock_time))
    # The other hand: a finger on the head changes the tension, and a membrane's
    # pitch goes as sqrt(T). GM gives two notes, so they glide opposite ways.
    mu = _T.MuteCuicaProperties(420.0, 0.0, 1.0, 1.0)
    check("...and the two notes glide in opposite directions",
          mu.tension_bend < 0.0 < cu.tension_bend
          and abs(cu.tension_bend) > 8.0 * _T.GrandPianoProperties.tension_bend,
          "  (mute %+.0f cents, open %+.0f, against a piano's %+.0f)"
          % (1200 * _math.log2(1 + mu.tension_bend), 1200 * _math.log2(1 + cu.tension_bend),
             1200 * _math.log2(1 + _T.GrandPianoProperties(261.6, 0.0, 1.0, 1.0).tension_bend)))

    # ---- which way a struck thing bends -------------------------------------
    # A string and a drumhead are tuned BY tension, so striking them raises it
    # and they bloom SHARP. A shallow curved shell is not: its nonlinearity is
    # dominated by a quadratic curvature term that enters the amplitude-frequency
    # relation squared and negative, so it softens. The pan is curvature-
    # dominated by construction -- that quadratic term is what makes its 1:2:3
    # tuning work -- so it must bend the other way from the piano.
    def _bend(cls, f0=261.63, vel=127):
        return cls(f0, 0.0, (vel / 127.0) ** 2, 1.0).tension_bend
    check("a shallow curved shell bends FLAT where a string bends sharp",
          _bend(_T.SteelPanProperties) < 0.0 < _bend(_T.GrandPianoProperties),
          "  (pan %+.5f, piano %+.5f, timpani %+.5f)"
          % (_bend(_T.SteelPanProperties), _bend(_T.GrandPianoProperties),
             _bend(_T.TimpaniProperties)))
    # The register scaling used to be gated on `> 0.0`, which silently skipped
    # every softening voice and left it unscaled.
    lo, hi = _bend(_T.SteelPanProperties, 130.8), _bend(_T.SteelPanProperties, 1046.5)
    check("...and the register scaling carries the sign through",
          lo < hi < 0.0 and abs(lo) > abs(hi),
          "  (%+.5f at C3, %+.5f at C6)" % (lo, hi))
    check("...capped in magnitude, not clipped to zero",
          abs(_bend(_T.SteelPanProperties, 20.0)) <= _T.SteelPanProperties.tension_bend_max
          and _bend(_T.SteelPanProperties, 20.0) < 0.0,
          "  (%+.5f two octaves below the compass)" % _bend(_T.SteelPanProperties, 20.0))
    # A CYMBAL'S MODES DO NOT MEASURABLY BEND EITHER. Tracked by phase
    # derivative across 203 well-isolated partials of the Iowa cymbal family,
    # the median drift is under a cent -- against the 16 this class used to
    # assert. What drifts on a cymbal is its CENTROID, by 1400-2100 cents, and
    # that is differential decay rather than any nonlinearity.
    check("a cymbal's modes do not measurably bend",
          all(getattr(c, "tension_bend", 0.0) == 0.0 for c in
              (_T.CymbalProperties, _T.CrashCymbal1Properties, _T.RideCymbalProperties,
               _T.HiHatProperties, _T.ChineseCymbalProperties, _T.SplashCymbalProperties)))
    # Struck BARS have no tension and no curvature, so they get neither.
    check("a straight bar gets no bend at all, having nothing to bend",
          all(getattr(c, "tension_bend", 0.0) == 0.0 for c in
              (_T.GlockenspielProperties, _T.VibraphoneProperties, _T.MarimbaProperties,
               _T.XylophoneProperties, _T.CelestaProperties, _T.TubularBellProperties,
               _T.RhodesProperties)))
    # And it must reach the partial table, negative, scaled by velocity.
    lv = Live(program=114, rate=48000, frames=128, verbose=False); lv.warm()
    hard = float(np.asarray(lv.parts[0].bank.get(60, 127)["tbav"])[0])
    lv.renderer.close()
    check("the pan's bend reaches the partials, still negative",
          hard < 0.0, "  (tbav %+.5f)" % hard)

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
