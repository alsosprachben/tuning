#!/usr/bin/env python3
"""Play the synth live from a MIDI keyboard.

The kernel was built for this: `synth_voice` renders any absolute sample range
statelessly (analytic phase), and it re-reads `non`/`noff` on every call. So a
live front end is not a new synthesiser -- it is a partial table that grows at
note-on and gets one int64 written into it at note-off, rendered a block at a
time by exactly the same C the offline renderer uses.

Usage: python3 live.py [--port NAME] [--program N] [--frames N] [--headroom dB]
       python3 live.py --list | --selftest | --latency

It answers twenty controllers -- 1, 5, 6, 7, 10, 11, 38, 64, 65, 66, 67, 84,
93, 98, 99, 100, 101, 120, 121, 123 -- plus program change, both aftertouches,
the wheel, and SysEx (GM System On, GM2 Scale/Octave Tuning), with RPN 0/0,
0/1 and 0/2. That is GM Level 1 complete, plus three of GM 2's; the fourth,
CC91, is offline-only. See midi.md, which is generated from this dispatch.

BANKS ARE BUILT OFF THE AUDIO THREAD and pinned while a Part is playing from
one. Pinning is not an optimisation: without it the LRU evicted the bank that
had just been requested, because a freshly built bank is the most recent thing
in the cache and nothing was holding it, so sixteen timbres left eleven
resident and each new arrival evicted itself.

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
import tempfile
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
import chorus as _CHR
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
# A GLIDE BELONGS TO THE PRESS, NOT TO THE VOICE, so these three are the one
# group that is NOT copied from the template -- they are zeroed at stamp time
# and written afterwards if this particular note-on is gliding. Templates are
# keyed on (note, velocity bucket), and a portamento's source pitch is neither;
# baking it in would mean a template per interval, which is the cache blowing
# up for a fact that costs three floats to carry instead.
COLS_F4_NOTE = ("gb", "gt", "gc")
COLS_I8 = ("non", "noff")
COLS_I4 = ("gr", "cr", "br", "pl")

# ---- CC10, and what pan actually IS in this renderer ------------------------
# NOT A PAN LAW. The file path puts CC10 into channel_pan, which becomes a
# POSITION IN METRES (tonelib: position_x = octave_position*octave_width +
# channel_pan*4) and then an HRTF. Measured on that geometry, hard left against
# centre:
#
#     interaural delay   +0.516 ms
#     level difference   +0.10 dB at 100 Hz, +1.92 at 500,
#                        +9.86 at 2 kHz, +15.20 at 4 kHz
#
# So an amplitude pan law would not merely lose the time cue -- it would be a
# DIFFERENT EFFECT, loud where this one is nearly silent and silent where it is
# loud. Live therefore does what the file does: a head shadow that depends on
# frequency, and an interaural delay.
#
# Precomputed once from tonelib's own hrtf_at, so the two paths place a pan
# identically and the audio thread does no trigonometry.
PAN_METRES = 4.0                # channel_pan * 4, from tonelib's position_x
_PAN_TABLE = None               # cc -> (alphaL, alphaR, half_itd_s)
_PAN_BETA = 0.0                 # the head-shadow corner, rad/s


def pan_table():
    """cc -> (alpha_left, alpha_right, half_itd_seconds), 128 entries.

    alpha is the only thing hrtf_gain takes from DIRECTION, so inverting it
    here leaves the audio thread one sqrt per partial.
    """
    global _PAN_TABLE, _PAN_BETA
    if _PAN_TABLE is not None:
        return _PAN_TABLE
    # StoppedPipe rather than the bare base: SynthProperties is abstract enough
    # that it cannot be constructed. Only the head geometry is read, and that
    # is the same on every voice.
    q = T.StoppedPipeProperties(261.63, 0.0, 1.0, 1.0)
    _PAN_BETA = q.hrtf_beta
    amin, tmin = 0.1, 150.0 * math.pi / 180.0
    out = []
    for cc in range(128):
        li, ri, ld, rd = q.hrtf_at((cc - 64) / 63.0 * PAN_METRES)
        al = 1.0 + amin / 2.0 + (1.0 - amin / 2.0) * math.cos(li * math.pi / tmin)
        ar = 1.0 + amin / 2.0 + (1.0 - amin / 2.0) * math.cos(ri * math.pi / tmin)
        # THE DIFFERENTIAL ONLY. Panning hard moves the source 4 m sideways,
        # which puts it 7.5 ms further from BOTH ears -- and the kernel shifts
        # the envelope by delL/delR, so applying that would start a hard-panned
        # attack 7.5 ms late in an engine whose control quantum is 2.7 ms. It
        # would also break _amp_snapshot, which picks the direct sound out as
        # the partials within two samples of the minimum delay. A delay applied
        # equally to both ears of one source is not a cue anyway.
        out.append((al, ar, (ld - rd) / 2.0))
    _PAN_TABLE = out
    return out
ALL_COLS = COLS_F8 + COLS_F4 + COLS_F4_NOTE + COLS_I8 + COLS_I4

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
        for k in COLS_F4_NOTE: self.a[k] = np.zeros(capacity, np.float32)
        for k in COLS_I8: self.a[k] = np.full(capacity, IDLE, np.int64)
        for k in COLS_I4: self.a[k] = np.zeros(capacity, np.int32)
        self.a["gr"][:] = -1            # -1 = always on, no organ gate or swell
        self.a["br"][:] = -1            # -1 = no bend row; live bends via retune
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
        self.BR = np.ones((1, 1), np.float32)     # inert: see prep()
        self.BC = np.zeros((1, 1), np.float64)
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
            # BR/BC ARE INERT HERE, ON PURPOSE. The kernel is shared with the
            # file renderer, which uses these rows for pitch bend; live bends
            # through Slab.retune instead, which rewrites om and re-anchors the
            # phase. So live hands the kernel one row of ones and one of zeros
            # and every slot's br stays -1, which takes the same code path the
            # kernel took before the rows existed. (Unifying the two is a
            # tempting follow-up and deliberately not this change.)
            d.update(lib=self.lib, P=self.cap, nblk=1, G=self.G, S=self.S,
                     BR=self.BR, BC=self.BC, sh=self.sh)
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
        for k in COLS_F4_NOTE:
            a[k][idx] = 0.0   # no glide unless this press asks for one
        a["gr"][idx] = -1     # ungated: a drawn rank is one we stamped
        a["br"][idx] = -1     # live bends through retune, never through a row
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
        # A DISTORTION PRODUCT GLIDES WITH ITS PARENTS. Every input to the
        # valve is moving by one ratio, so every sum and difference of them
        # moves by that same ratio -- copied, not zeroed, unlike at stamp time.
        for k in COLS_F4_NOTE:
            a[k][idx] = a[k][src]
        for k in COLS_I4:
            a[k][idx] = a[k][src]
        a["gr"][idx] = -1       # ungated: the amplifier is not a drawn rank
        a["br"][idx] = -1
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

    def channel_gain(self, slots, ratio):
        """Move the channel fader under a note already sounding.

        THE BASELINE, not the current value. aL0/aR0 are what aftertouch, the
        rotor and the tone rockers all recompute from, so scaling those makes
        the fader compose with every one of them instead of being wiped by the
        next aftertouch message. And it takes a RATIO rather than an absolute
        gain, so a stream of CC7s cannot compound -- the caller remembers what
        it last applied, exactly as _one does for the drive step.

        AND THERE ARE FOUR BASELINES, NOT ONE -- which is what this comment got
        wrong when it was written a few hours ago. A Leslie, a tremolo and a
        clavinet's rockers each capture their OWN copy of the amplitude
        (ls_aL/ls_aR at 296, tr_aL/tr_aR at 387, cv_aL/cv_aR at 365) and then
        ASSIGN a["aL"] from it on every block. So scaling only aL0 and a["aL"]
        is erased within one block on exactly the voices that have a panel
        effect: measured on program 16, CC11 127 -> 32 moved the note -23.9 dB
        as it should, and one callback later it was back to +0.1. The existing
        selftest passed only because it used the bagpipe, which has none of
        them.

        Unconditional, because an unarmed row's baseline is zero and scaling it
        is a no-op -- and when that row is later armed, the capture reads an
        a["aL"] that already carries the fader.
        """
        if not slots or ratio == 1.0:
            return
        idx = np.fromiter(slots, np.int64, len(slots))
        r = np.float32(ratio)
        self.aL0[idx] *= r
        self.aR0[idx] *= r
        self.a["aL"][idx] *= r
        self.a["aR"][idx] *= r
        self.tr_aL[idx] *= r
        self.tr_aR[idx] *= r
        self.ls_aL[idx] *= r
        self.ls_aR[idx] *= r
        self.cv_aL[idx] *= r
        self.cv_aR[idx] *= r

    def repan(self, slots, cc, was, rate, itd=True):
        """Move a note's source position, CC10 `was` -> CC10 `cc`.

        RATIOS AND DELTAS, never absolutes, so a stream of CC10s cannot
        compound -- the caller remembers what it last applied, exactly as it
        does for the channel fader.

        THE LEVEL IMAGE AND THE TIME IMAGE ARE SEPARATE, and only the first of
        them may move under a sounding note. delL/delR are not bookkeeping:
        the kernel shifts each ear's ENVELOPE by them (see AMP in
        synthkernel.c), so moving them mid-note moves the time origin of a
        decaying note -- a level step, not merely a phase click. A pan pot on a
        desk does not move a source's arrival time either. So a note takes its
        interaural delay when it is struck, and after that only the head shadow
        follows the hand.

        The shadow is frequency-dependent and that is the whole point: hard
        left is 0.10 dB at 100 Hz and 15.2 dB at 4 kHz. A single gain would be
        a different effect.
        """
        if not slots or cc == was:
            return
        tab = pan_table()
        al1, ar1, d1 = tab[max(0, min(127, int(cc)))]
        al0, ar0, d0 = tab[max(0, min(127, int(was)))]
        idx = np.fromiter(slots, np.int64, len(slots))
        a = self.a
        om = 2.0 * math.pi * a["nf"][idx].astype(np.float64)
        b2 = _PAN_BETA * _PAN_BETA
        shelf = lambda al: np.sqrt((al * om) ** 2 + b2)
        rl = (shelf(al1) / shelf(al0)).astype(np.float32)
        rr = (shelf(ar1) / shelf(ar0)).astype(np.float32)
        for L, R in ((self.aL0, self.aR0), (a["aL"], a["aR"]),
                     (self.tr_aL, self.tr_aR), (self.ls_aL, self.ls_aR),
                     (self.cv_aL, self.cv_aR)):
            L[idx] *= rl
            R[idx] *= rr
        if itd:
            # p0 = -om*(non + delay) + ph0 in blockrender, so a delay delta of
            # d samples moves the anchor by -om*d. Both ears, opposite signs.
            dl = np.float32((d1 - d0) * rate)
            a["delL"][idx] += dl
            a["delR"][idx] -= dl
            a["p0"][idx] -= a["om"][idx] * float(dl)
            a["p0R"][idx] += a["om"][idx] * float(dl)

    def soft_strings(self, slots, drop, top):
        """Silence the `drop` highest unison voices of a note -- una corda.

        AT NOTE-ON ONLY, and that is not a shortcut. The shift moves the whole
        action sideways so the hammer no longer REACHES the last string; once a
        note has been struck, moving the pedal cannot un-strike a string that
        is already vibrating. A real una corda pedal pressed mid-note does
        nothing to the notes already sounding, and neither does this.

        The strings are already separable: blockrender stamps every unison
        voice with its own index in `pl` (_PL[0] = ui + 1), so this is a mask
        on a column that exists rather than a filter over one that does not.

        `top` is the INSTRUMENT's highest string index, not this note's. A note
        with one or two strings loses nothing: the action still slides, and the
        hammer still covers every string there is. Taking "the highest present"
        instead removed the second string in the bass, where the file renderer
        correctly removed none -- measured as a 0.48 dB divergence at C2.
        """
        if not slots or drop <= 0 or top <= 0:
            return
        idx = np.fromiter(slots, np.int64, len(slots))
        gone = idx[self.a["pl"][idx] > top - drop]
        if not len(gone):
            return
        for arr in (self.aL0, self.aR0, self.a["aL"], self.a["aR"],
                    self.tr_aL, self.tr_aR, self.ls_aL, self.ls_aR,
                    self.cv_aL, self.cv_aR):
            arr[gone] = 0.0

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
_BANK_PINNED = set()        # (program, drums, tuner) a Part is holding now


class Bank:
    """Every template for one patch: (program, drums, tuner).

    Shared by every Part that wants that patch, so layering two trumpets builds
    one bank. Effectively immutable once warmed, which is what makes it safe to
    hand to the audio thread by a single attribute assignment.
    """

    def __init__(self, program, drums, tuner):
        self.program, self.drums, self.tuner = program, drums, tuner
        self._freqs = None
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
        # AND THE IMBALANCE, which live never carried. Offline passes each voice
        # its own (blockrender's _AMP_IMB); live passed none, so tubeamp's
        # default of 0.06 applied -- a balanced push-pull pair with its even
        # orders cancelled. GM 30 asks for 0.80. The same voice was running
        # through two different amplifiers depending on how it was played.
        self.amp_imbalance = None if drums else getattr(pc, "amp_imbalance", None)
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
        # THE DRONES ARE NOT THE NOTE, so unlike every other CC1 voice this one
        # does NOT get a template axis. A bagpipe drone sounds once while the
        # bag is up; baking it into the chanter's template would restart three
        # of them on every note and stack them on a held line. So the chanter
        # template is built with the drones CORKED (see _raw_template), and the
        # drones are stamped separately as their own held voices.
        # A KEY THAT ONLY OPENS A VALVE DOES NOT SET THE LEVEL, and live has to
        # know it too. The class flag was honoured in the PARTIALS -- every
        # bucket of a fixed-volume voice comes out identical -- and then thrown
        # away again by the velocity trim in _note_on, which scales what it
        # stamps by (vel/bucket_vel)^2 whatever the voice is. The harpsichord
        # escaped only because it is `registerable` and takes the organ branch
        # before that line; the accordions and the bagpipe did not, and
        # measured +24.1 dB from velocity 30 to 120 on a patch whose own class
        # says velocity does nothing.
        self.touch_sensitive = drums or bool(getattr(pc, "touch_sensitive", True))
        # CC64: does this voice have anything for a pedal to lift? A struck or
        # plucked string rings and the felt is what stops it; a bowed or blown
        # one stops when the player does. Drums are one-shots and ignore
        # note-off entirely, so the pedal cannot reach them either way.
        self.damper_pedal = (not drums) and bool(getattr(pc, "damper_pedal", True))
        # How many strings the una corda shift takes away; 0 on everything
        # that is not a grand. See SynthProperties.soft_pedal_strings.
        self.soft_pedal_strings = (0 if drums
                                   else int(getattr(pc, "soft_pedal_strings", 0)))
        # ...and WHICH strings those are. The shift takes the third string of a
        # TRICHORD; on a note that has only one or two it still moves, and the
        # hammer still covers every string there is. So the index is fixed by
        # the instrument, not by what a given note happens to have -- dropping
        # "the highest one present" would take the second string in the bass,
        # where the file renderer correctly takes nothing.
        # note_detune_cents is drawn PER NOTE in __init__, so the class does
        # not carry it -- ask an instance at a reference pitch. Its length is
        # the instrument's string complement and does not vary with the note.
        self.soft_pedal_top = 0
        if not drums and self.soft_pedal_strings:
            try:
                self.soft_pedal_top = len(
                    pc(261.63, 0.0, 1.0, 1.0).note_detune_cents or ())
            except Exception:
                self.soft_pedal_top = 0
        self.drone_wheel = (not drums) and bool(getattr(pc, "drone_wheel", False))
        # RATIOS OF THE TONIC, not frequencies. A drone is tuned to the
        # chanter before playing, so it has to follow the part's tuner: at
        # `hybrid` Low A is 415 Hz and a drone nailed to 220 would be a
        # hundred cents out against the one note it exists to reinforce.
        self.drone_ratios = tuple(getattr(pc, "drone_ratios", ())) if pc else ()
        self.drone_gain = tuple(getattr(pc, "drone_gain", ())) if pc else ()
        self.scale_tonic_note = getattr(pc, "scale_tonic_note", None) if pc else None
        self.part_break_s = float(getattr(pc, "part_break_s", 2.0)) if pc else 2.0
        self.detune_wheel = (not drums) and bool(getattr(pc, "detune_wheel", False))
        if self.detune_wheel:
            self.speeds = DETUNE_STEPS
            self.leslie_default = DETUNE_STEPS[len(DETUNE_STEPS) // 2]
        self.rank_names = [r[0] for r in getattr(pc, "stop_ranks", [])] if pc else []
        # THE VOICE'S OWN REGISTRATION, which has never once applied. Part
        # read it as `getattr(bank.pc, ...) if hasattr(bank, 'pc')` -- and Bank
        # binds pc as a LOCAL and never assigns self.pc, so hasattr was always
        # False and every organ Part started on rank 0 regardless of what its
        # class declared. Four classes declare multi-bit registrations.
        self.default_stops = 1 if drums else int(getattr(pc, "default_stops", 1))
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

    def freqs(self):
        """This bank's tuning table, built once.

        THE RATIO IS ALL PORTAMENTO NEEDS, and taking it from the table rather
        than from a template means it is the same number the file renderer
        uses. A glide is between two notes of one channel, so whatever the
        channel did to both -- bend, coarse and fine tuning, the GM2 scale
        table -- is the same multiplier on each and cancels.
        """
        if self._freqs is None:
            self._freqs = __import__("blockrender").tuning_table(self.tuner)
        return self._freqs

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
        if self.drone_wheel and fast is None:
            # CORK THEM FOR THE BUILD, and say so in the MIDI rather than by
            # setting the module global -- blockrender reads the CHANNEL'S OWN
            # CC1 and writes `bagpipe_drones` from it on the first note, so a
            # value set from out here is overwritten before any partial is
            # emitted. (Set it and measure: the template still came out with
            # 110 and 220 Hz partials under a written D5. The selftest caught
            # exactly that.)
            #
            # Why cork it at all: blockrender emits the spanning unison across
            # the note's phrase, and a ONE-NOTE template is its own whole
            # phrase, so every template would carry three drones and a held
            # line would stack them a set at a time. Live sounds the drones as
            # their own held voices instead; this template is the chanter.
            fast = 0
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

    def warm(self, progress=None, stop=None):
        """Build every template for the playable range. Off-thread only.

        `stop` lets a newer program change preempt an older one's warm: it
        returns without setting `warmed`, so the next pass resumes where the
        cache left off rather than starting again.
        """
        if self.warmed:
            return self
        lo, hi = self.range
        done = 0
        total = (hi - lo + 1) * self.nbuckets * len(self.speeds)
        for note in range(lo, hi + 1):
            for b in range(self.nbuckets):
                for sp in self.speeds:
                    if stop is not None and stop():
                        return self          # preempted; resume later
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
        # LRU by partial count: piano is 242k partials on its own.
        #
        # BUT NEVER A BANK SOMEBODY IS PLAYING. The cap counts partials and
        # nothing else, so the least-recently-used bank it drops can be one a
        # Part is holding and sounding through -- which was only a rebuild cost
        # until a program change could re-select a voice, and is now a voice
        # rebuilt from cold in the middle of a piece. Measured: sixteen typical
        # GM timbres warm to 503,387 partials against a 400,000 cap, and one
        # gets evicted. The piano alone is 242,718 of that.
        #
        # So the LRU drops what nothing is using, and stops when everything
        # left is in use -- a rig playing sixteen voices keeps all sixteen,
        # because it is playing all sixteen.
        while len(_BANKS) > 1:
            if sum(b.partials for b in _BANKS.values()) <= _BANK_PARTIAL_CAP:
                break
            # ...and never the one just asked for. It is not pinned yet --
            # the caller pins it once it is holding it -- and it is the most
            # recently used, so without this the bank being built evicts
            # ITSELF the moment the cache is full. Measured: sixteen voices
            # added one at a time left eleven resident, each new arrival
            # throwing away the one before it had a chance to be claimed.
            drop = next((k for k in _BANKS
                         if k != key and k not in _BANK_PINNED), None)
            if drop is None:
                break           # every bank left is on stage
            del _BANKS[drop]
        return got


def pin_banks(keys):
    """The banks a live rig is holding, which the LRU must not evict."""
    with _BANK_LOCK:
        _BANK_PINNED.clear()
        _BANK_PINNED.update(keys)


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
        self.cres = 0.0
        self.set_bank(bank)

    def set_bank(self, bank):
        """Point this part at a voice -- at construction, or on a program change.

        IN PLACE, keeping the pid. A program change must not cut a note that is
        already sounding (it does not on any synthesiser), and the pid is the
        key for every per-part dict there is: the drive step, the tremolo
        depth, the rockers, the detune, the drone count. Building a new Part
        would orphan all of them and release every held note through set_parts.
        """
        self.bank = bank
        # Which stops are out, per part: two organ layers can differ.
        ds = getattr(bank, "default_stops", 1)
        self.drawn = {r for j, r in enumerate(bank.rank_names) if (ds >> j) & 1} \
                      or set(bank.cres_order[:1])   # the voice's own registration

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
        # CC7 AND CC11, WHICH LIVE DID NOT HAVE AT ALL. It implemented CC1,
        # CC64 and CC123 and nothing else, so `level_db` in the mixer was the
        # only volume there was. That is survivable on a piano, where velocity
        # is the dynamic -- and it is the WHOLE dynamic range of a patch whose
        # class says velocity does nothing. A bagpipe with neither touch nor
        # channel volume cannot be played at two levels at all.
        self.vol = {}           # channel -> CC7, 127 until one arrives
        self.expr = {}          # channel -> CC11, the swell and the bellows
        self.cgain = {}         # channel -> the gain last applied to its notes
        self.cpan = {}          # channel -> the CC10 last applied to its notes
        self.wheel = {}         # channel -> raw pitchwheel, -8192..8191
        self.brange = {}        # channel -> RPN 0, semitones; absent = bend_range
        self.coarse = {}        # channel -> RPN 2, semitones
        self.fine = {}          # channel -> RPN 1, cents
        self.rpn = {}           # channel -> selected (msb, lsb); (127,127) = null
        # GM2 scale/octave tuning: twelve cent offsets per channel, and the
        # ratio last APPLIED to each pitch class so a repeat cannot compound.
        # It cannot fold into self.bend, which is one scalar for the channel.
        self.chorus = {}        # channel -> CC93 send, 0..1
        self.soft = {}          # channel -> the una corda shift is in
        self.sost = {}          # channel -> keys the sostenuto pedal is holding
        self.sota = {}          # channel -> [12 cents]
        self.sota_at = {}       # (channel, pitch class) -> ratio last applied
        # PORTAMENTO. CC65 is a switch, CC5 a speed, CC84 neither -- its byte is
        # a source NOTE NUMBER, it fires once, and Roland's Example 2 shows it
        # working with the switch off and nothing sounding. See midi.md.
        self.porta_on = {}      # channel -> CC65 is up
        self.porta_time = {}    # channel -> CC5, 0 (fastest) by Roland's default
        self.porta_src = {}     # channel -> a pending CC84 source note, consumed
        # WHICH NOTE A GLIDE STARTS FROM, and self.down cannot answer it: it is
        # a SET of what is held, with no order in it, so it knows what is down
        # and not what went down last. Poly mode has no defined answer here --
        # Roland does not give one, which is why CC84 exists -- and the last
        # note to start is the convention everyone uses.
        self.last_on = {}       # channel -> the most recent note-on
        self._glide_from = None # source pitch for the note-on being dispatched
        self._rpn_fine_msb = {}
        self.drone_count = {}   # pid -> how many drones are uncorked (0-3)
        self.drone_quiet = {}   # pid -> the sample the chanter went silent at
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
        # ...and the same division for program changes: the audio thread may
        # queue a voice change, never build one. See _bank_worker.
        self.bank_reqs = collections.deque()      # (pid, (program, drums, tuner))
        self.warm_reqs = collections.deque(maxlen=256)   # (bank, note, bucket, axis)
        self.bank_go = threading.Event()
        self.bank_stop = False
        self.bank_label = None                    # what is building, for the TUI
        self.bank_busy = False                    # a pass is in flight: see wait_bank
        self.bank_err = None
        self.bank_thread = threading.Thread(target=self._bank_worker, daemon=True)
        self.bank_thread.start()
        self.thresh = 0.70      # soft-limiter knee; see Live.limit
        self.press_db = T.PRESS_DB      # one constant, shared with the file path
        self.press_tilt = T.PRESS_TILT
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
        self._pin_banks()

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
                        "aftertouch", "polytouch", "program_change", "sysex"):
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

    def _pin_banks(self):
        """Tell the cache which voices are on stage, so it evicts none of them."""
        pin_banks({(p.bank.program, p.bank.drums, p.bank.tuner)
                   for p in self.parts})

    def shutdown(self):
        """Stop the worker threads and the renderer.

        The builder holds no lock the interpreter needs, but a daemon thread
        still mid-build at shutdown discards whatever stdout had buffered --
        which cost an hour of chasing a program change that was working
        perfectly and simply could not say so.
        """
        self.bank_stop = True
        self.bank_go.set()
        self.amp_stop = True
        self.amp_go.set()
        self.renderer.close()

    def panic(self):
        """All notes off, the one thing you want when something drones."""
        self.post(self._all_off)

    def _all_off(self, n0):
        """The body of panic, callable with n0 in hand -- which is what a GM
        System On needs, because it arrives ON the audio thread and must take
        effect on this block rather than the next."""
        for k in list(self.slab.live):
            self.slab.oneshot.pop(k, None)
            self.slab.release(k, n0)
        self.down.clear()
        self.pedalled.clear()
        for p in self.parts:
            self._amp_touch(p)

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
        if msg.type == "sysex":
            # No channel on a sysex, and every line below this reads one.
            self._sysex(n0, msg)
            return
        ch = msg.channel
        parts = self.parts
        if msg.type == "pitchwheel":
            # MIDI pitch bend is +/- 8192 over the wheel's range, which is
            # +/- bend_range semitones by convention.
            # THE RAW WHEEL IS KEPT, which nothing did before: `bend` holds a
            # ratio, and RPN 0 changing the range while the wheel is off centre
            # has to recompute from the wheel itself. See _repitch.
            self.wheel[ch] = msg.pitch
            if any(p.bank.leslie for p in parts if self._listens(p, ch)):
                # ON A ROTOR PART THE WHEEL IS THE HALF-MOON, not a bend: see
                # PW_FIRE. A Hammond has no pitch bend to take away.
                self._half_moon(ch, msg.pitch)
            self._repitch(ch, n0)
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
                # AND ON A BAGPIPE THE WHEEL IS HOW MANY DRONES ARE UNCORKED.
                # This is the bug Ben heard: with no branch of its own the
                # bagpipe fell into `others` and CC1 gave it 35 cents of
                # vibrato -- on the one instrument in the bank that has no
                # vibrato at all, since a bag under constant pressure is what
                # a piper is FOR.
                dronists = [p for p in here if p.bank.drone_wheel]
                others = [p for p in here
                          if not p.organ and not p.bank.leslie
                          and p.bank.amp_drive <= 0.0
                          and p.bank.tremolo_depth <= 0.0
                          and not p.bank.clav_panel
                          and not p.bank.detune_wheel
                          and not p.bank.drone_wheel]
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
                for part in dronists:
                    # Even quarters over the wheel, as blockrender does, so a
                    # file and the keyboard cork the same drones at the same
                    # place. UNLIKE the offline path this is live rather than
                    # read-once: a piper corks before playing, but a player at
                    # a keyboard has a wheel in their hand and expects it to
                    # do something, so the drones come and go under it.
                    _nd = len(part.bank.drone_ratios)
                    n = max(0, min(_nd, int(round(msg.value / 127.0 * _nd))))
                    if self.drone_count.get(part.pid) != n:
                        self.drone_count[part.pid] = n
                        if self._chanting(part, ch):
                            self._drones(part, ch, n0)
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
            elif msg.control in (7, 11):            # volume and expression
                # (v7*v11)^2, which is blockrender's law at line 840 -- the
                # same squared MIDI curve velocity uses, applied to the
                # CHANNEL. Snapshotted into every note stamped from here on,
                # which is exactly what the file path does.
                if msg.control == 7:
                    self.vol[ch] = msg.value
                else:
                    self.expr[ch] = msg.value
                g = self._chan_gain(ch)
                was = self.cgain.get(ch, 1.0)
                if g != was:
                    self.cgain[ch] = g
                    # ...AND IT REACHES A NOTE ALREADY SOUNDING, which the file
                    # path cannot do: offline a note's amplitude is fixed when
                    # its partials are emitted, so CC7 is read once at note-on
                    # and a swell written mid-note does nothing. Live has a
                    # fader in someone's hand, and on an organ or a bagpipe
                    # CC11 IS the swell box and the only expression there is.
                    # The DIFFERENCE is that and only that: a note stamped at
                    # this setting comes out identical either way.
                    self.slab.channel_gain(self._sounding(ch), g / max(was, 1e-9))
            elif msg.control == 10:                 # pan
                # THE LEVEL IMAGE FOLLOWS THE POT, THE TIME IMAGE DOES NOT --
                # see Slab.repan. A note keeps the interaural delay it was
                # struck with; the head shadow moves under the hand.
                was = self.cpan.get(ch, T.GM_DEFAULT_PAN)
                if msg.value != was:
                    self.cpan[ch] = msg.value
                    self.slab.repan(self._sounding(ch), msg.value, was,
                                    self.rate, itd=False)
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
            elif msg.control == 93:                 # chorus send
                # A setup for the notes to come, like the soft pedal: a copy of
                # a note already sounding would have to start in the middle of
                # its own envelope. See _chorus.
                self.chorus[ch] = msg.value / 127.0
            elif msg.control == 67:                 # soft pedal (una corda)
                # A SETUP FOR THE NOTES TO COME, not an effect on the ones
                # sounding -- see Slab.soft_strings. Nothing to do here but
                # remember it; _note_on reads it when the hammer swings.
                self.soft[ch] = msg.value >= 64
            elif msg.control == 5:                  # portamento time
                self.porta_time[ch] = msg.value
            elif msg.control == 65:                 # portamento on/off
                # Roland: 0-63 OFF, 64-127 ON -- the same switch point the three
                # pedals collapse half-pedalling at.
                self.porta_on[ch] = msg.value >= 64
            elif msg.control == 84:                 # portamento control
                # THE BYTE IS A NOTE NUMBER, not a depth. It arms the NEXT
                # note-on on this channel to start from that pitch, once, and
                # it does not need CC65: Roland's Example 2 sends it with
                # nothing sounding at all and still glides.
                self.porta_src[ch] = msg.value
            elif msg.control == 66:                 # sostenuto pedal
                # NOT THE DAMPER PEDAL WITH A DIFFERENT NUMBER. Sustain holds
                # everything played while it is down; sostenuto holds only the
                # keys that were ALREADY DOWN at the instant it went down, and
                # lets everything after that damp normally. That asymmetry is
                # the whole instrument -- it is how a pianist holds a bass note
                # under a passage that has to stay dry.
                _dn = msg.value >= 64
                _wasq = bool(self.sost.get(ch))
                if _dn and not _wasq:
                    # A SNAPSHOT of what is down right now, and nothing later.
                    self.sost[ch] = {k for k in self.down if k[0] == ch}
                elif not _dn and _wasq:
                    _gone = self.sost.pop(ch, set())
                    for k in [k for k in list(self.slab.live)
                              if (k[1], k[2]) in _gone
                              and (k[1], k[2]) not in self.down
                              and not (self.pedal.get(ch, False))]:
                        self.slab.release(k, n0)
                    self.pedalled -= _gone
            elif msg.control in (98, 99):           # NRPN select
                # Nothing here implements an NRPN, but selecting one must STOP
                # a following CC6 from landing on whatever RPN was last chosen.
                self.rpn[ch] = None
            elif msg.control == 101:                # RPN MSB
                _sel = self.rpn.get(ch) or (127, 127)
                self.rpn[ch] = (msg.value, _sel[1])
            elif msg.control == 100:                # RPN LSB
                _sel = self.rpn.get(ch) or (127, 127)
                self.rpn[ch] = (_sel[0], msg.value)
            elif msg.control in (6, 38):            # data entry
                self._rpn_data(ch, msg.control, msg.value, n0)
            elif msg.control == 121:                # reset all controllers
                self._reset_controllers(n0, ch)
            elif msg.control == 120:                # all SOUND off
                # THE DIFFERENCE FROM CC123 IS THE TAIL. All Notes Off lifts
                # the keys and lets every voice ring out on its own release;
                # All Sound Off stops the channel NOW, pedal or no pedal, and
                # is what a panic button sends.
                #
                # "Now" is four milliseconds, not zero. The kernel divides by
                # the release length (invr = 1.f/relS[p]), so a zero release is
                # a divide by zero -- and a hard cut is a step, and a step is a
                # click. RETRIGGER_FADE is the constant the file renderer
                # already floors every release at, for exactly this argument.
                for p in parts:
                    self._amp_touch(p)
                self.down = {k for k in self.down if k[0] != ch}
                self.pedalled = {k for k in self.pedalled if k[0] != ch}
                self.sost.pop(ch, None)
                self.pedal[ch] = False
                _fade = np.float32(B.RETRIGGER_FADE * self.rate)
                for k in [k for k in list(self.slab.live) if k[1] == ch]:
                    _sl = self.slab.live.get(k)
                    if _sl:
                        _ix = np.fromiter(_sl, np.int64, len(_sl))
                        self.slab.a["re"][_ix] = np.minimum(
                            self.slab.a["re"][_ix], _fade)
                    self.slab.oneshot.pop(k, None)
                    self.slab.release(k, n0)
            elif msg.control == 123:                # all notes off
                # The amplifier's partials hang off a key with no channel, so
                # this sweep cannot see them -- but their parents are about to
                # go, so mark them stale and let the pump clear them.
                for p in parts:
                    self._amp_touch(p)
                # ...AND IT HONOURS THE PEDAL, which it did not. This branch
                # cleared `pedalled`, cleared `pedal` and popped every oneshot
                # -- which is All SOUND Off's behaviour, not its own. All Notes
                # Off means the keys came up: a note under a held damper goes
                # on ringing, and a struck cymbal goes on ringing, because
                # neither is a key being held down.
                self.down = {k for k in self.down if k[0] != ch}
                _keep = (self.pedal.get(ch, False), self.sost.get(ch) or set())
                for k in [k for k in list(self.slab.live) if k[1] == ch]:
                    if self.slab.oneshot.get(k):
                        continue                # rings out on its own decay
                    if _keep[0] or (k[1], k[2]) in _keep[1]:
                        self.pedalled.add((k[1], k[2]))
                        continue                # a damper is still off it
                    self.slab.release(k, n0)
        elif msg.type == "program_change":
            # INCOMING MIDI WINS. A part listening on this channel changes
            # voice; notes already sounding keep the templates they were struck
            # with, which is what a program change means and what keeps a held
            # chord intact across one.
            #
            # A DRUM PART STAYS A DRUM PART: `drums` is carried through, so a
            # program change on channel 10 re-selects the kit rather than
            # turning the kit into a piano. GM has no melodic program there.
            for part in parts:
                if not self._listens(part, ch):
                    continue
                want = (int(msg.program), part.drums, part.tuner)
                if (part.bank.program, part.bank.drums, part.bank.tuner) == want:
                    continue
                self.bank_reqs.append((part.pid, want))
            if self.bank_reqs:
                self.bank_go.set()
        elif msg.type == "note_on" and msg.velocity > 0:
            # Every voice records the key as down, not just the organ. The
            # stuck-note sweep releases whatever is sounding without a key behind
            # it, so a voice that never registered its key had every note swept
            # a block after it started -- notes dying in a fraction of a second.
            self.down.add((ch, msg.note))
            # WHERE THIS NOTE GLIDES FROM, decided once for the channel before
            # any part sees it -- a layered channel is several parts and one
            # keyboard, so they must all glide from the same place. A pending
            # CC84 wins and is spent here; otherwise CC65 takes the last note
            # to have started. Read BEFORE last_on is updated, or every note
            # would glide from itself.
            _psrc = self.porta_src.pop(ch, None)
            if _psrc is None and self.porta_on.get(ch):
                _psrc = self.last_on.get(ch)
            self._glide_from = _psrc if _psrc != msg.note else None
            self.last_on[ch] = msg.note
            for part in parts:
                if part.matches(ch, msg.note):
                    self._note_on(part, ch, msg.note, msg.velocity, n0)
            self._glide_from = None
        else:
            self.down.discard((ch, msg.note))
            pedalled = False
            for part in parts:
                if not part.matches(ch, msg.note):
                    continue
                # ONE SOURCE OF TRUTH with the file path, which grew the same
                # rule today. `not part.organ` was right and narrow: it caught
                # the organs and the harpsichord (registerable, both) and left
                # every bowed string and every blown pipe holding a pedalled
                # note at full bow with nobody bowing it. See
                # SynthProperties.damper_pedal.
                if ((self.pedal.get(ch, False)
                     or (ch, msg.note) in self.sost.get(ch, ()))
                        and part.bank.damper_pedal):
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
            # ...AND ASK FOR IT. A program change swaps in a cold bank so the
            # part is playable at once; this is what fills it, one template per
            # note actually played, instead of eight seconds up front.
            self.misses += 1
            self.warm_reqs.append((part.bank, snote, part.bank.bucket(vel), _axis))
            self.bank_go.set()
            return
        # Timbre is quantised to the bucket, level is not: trim by the ratio
        # of the actual velocity to the one the bucket was built at.
        #
        # ...UNLESS THE VOICE HAS NO TOUCH. Then the bucket's template already
        # carries the whole level -- attack_volume was neutralised when it was
        # built -- and trimming it by velocity is the touch sensitivity the
        # class spent a paragraph refusing. See Bank.touch_sensitive.
        scale = part.gain() * self._chan_gain(ch)
        if part.bank.touch_sensitive:
            scale *= ((vel / 127.0) ** 2 /
                      max((tmpl.get("vel", 127) / 127.0) ** 2, 1e-9))
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
        # PAN BEFORE THE EFFECTS CAPTURE. clav_tone, tremolo_arm and press all
        # take their own baseline from a["aL"], so the pan has to be in it
        # already or the first block would wipe it -- the same trap the channel
        # fader fell into. Full transform here, delay included: this note has
        # not sounded yet, so there is no envelope to step.
        _cp = self.cpan.get(ch, T.GM_DEFAULT_PAN)
        if _cp != T.GM_DEFAULT_PAN and slots:
            self.slab.repan(slots, _cp, T.GM_DEFAULT_PAN, self.rate, itd=True)
        # UNA CORDA, before those same captures and for the same reason.
        if self.soft.get(ch) and slots:
            self.slab.soft_strings(slots, part.bank.soft_pedal_strings,
                                   part.bank.soft_pedal_top)
        # PORTAMENTO, stamped rather than swept. The kernel carries the glide
        # per partial (gb/gt/gc), so live does not advance anything per block
        # the way the Leslie's Doppler has to -- the note is placed once with
        # its whole trajectory attached and the kernel renders it. That is also
        # what makes the two renderers agree by construction rather than by
        # calibration: they write the same three floats.
        if self._glide_from is not None and slots:
            self._glide(part, ch, note, slots)
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
        if part.bank.drone_wheel:
            self.drone_quiet.pop(part.pid, None)
            self._drones(part, ch, n0)
        if self.chorus.get(ch, 0.0) > _CHR.FLOOR:
            self._chorus(part, ch, note, vel, key, slots, n0)
        # THE CHANNEL'S TUNING IS PER PITCH CLASS, so it multiplies the
        # channel's single bend ratio rather than joining it. `note` is the
        # written key, which is what the MIDI spec indexes the table by.
        b = self.bend.get(ch, 1.0) * self._sota_ratio(ch, note)
        v = self.mod.get(ch, 0.0)
        w = self.modw.get(ch, 0.0)
        if b != 1.0 or v != 0.0 or w != 0.0:
            self.slab.retune(slots, n0, om_scale=(b if b != 1.0 else None),
                             vd=(v if v != 0.0 else None),
                             vrs=(1.0 + self.mod_rate * w) if w != 0.0 else None)

    def _chan_gain(self, ch):
        """CC7 x CC11, squared -- blockrender's (v7*v11)**2, one law.

        ...and one set of defaults with it. GM powers a channel up at volume
        100, not 127, which is four decibels of room for a part to be turned
        UP. Both renderers read tonelib's constant so they cannot drift.
        """
        return ((self.vol.get(ch, T.GM_DEFAULT_VOLUME) / 127.0)
                * (self.expr.get(ch, T.GM_DEFAULT_EXPRESSION) / 127.0)) ** 2

    CHORUS_SLOT = "chorus"
    CHORUS_MAX = 2              # copies, live: see _chorus

    def _chorus(self, part, ch, note, vel, key, slots, n0):
        """Stamp this note's chorus copies, a few cents away.

        OFFLINE THIS IS A PASS OVER THE FINISHED TABLE and costs one clone per
        partial. Live there is no finished table -- a template is stamped into
        a slab with 16384 slots, and a layered string voice is ~260 partials
        per key. So the copies are stamped like any other note, and the count
        is CAPPED: three copies of a ten-note string chord is 10,400 slots,
        two thirds of the slab, for an effect that is audible with one.

        A SEND IS A MIX, as offline: the wet share comes out of the dry one and
        the total is held, so CC93 does not double as a volume control.

        Applied at note-on only. A copy of a note that is already sounding
        would have to start in the middle of its own envelope, and stamping it
        fresh would sound like a second strike -- which is not what turning up
        a chorus does.
        """
        send = self.chorus.get(ch, 0.0)
        if send <= _CHR.FLOOR or not slots:
            return
        cents = _CHR.offsets_for(
            part.bank._voice_class(note + part.transpose))[:self.CHORUS_MAX]
        if not cents:
            return
        tmpl = part.bank.get(note + part.transpose, vel, part.bank.leslie_default)
        if tmpl is None:
            return
        wet = (send / float(len(cents))) ** 0.5
        dry = (1.0 - send) ** 0.5
        scale = ((vel / 127.0) ** 2
                 / max((tmpl.get("vel", 127) / 127.0) ** 2, 1e-9)) * part.gain()
        made = False
        for ci, c in enumerate(cents):
            ckey = (part.pid, ch, note, "%s%d" % (self.CHORUS_SLOT, ci))
            if ckey in self.slab.live:
                continue
            if not self.slab.stamp(tmpl, ckey, n0,
                                   scale * self._chan_gain(ch) * wet):
                self.dropped += 1
                continue
            csl = self.slab.live.get(ckey)
            if csl:
                self.slab.retune(csl, n0, om_scale=2.0 ** (c / 1200.0),
                                 vd=_CHR.SWEEP_DEPTH,
                                 vrs=_CHR.SWEEP_HZ[ci % len(_CHR.SWEEP_HZ)])
                made = True
        if made and dry != 1.0:
            self.slab.channel_gain(slots, dry)

    DRONE_SLOT = "drone"

    def _chanting(self, part, ch):
        """Is a CHANTER note sounding? The drones do not count themselves."""
        return any(k[0] == part.pid and k[1] == ch and k[3] != self.DRONE_SLOT
                   for k in list(self.slab.live))

    def _tonic_hz(self, part, ch=None):
        """Where this part's tuner actually put the instrument's tonic.

        Read off the tonic's OWN template rather than computed, so it survives
        any temperament, any transposition the bank applies, and the chanter's
        own scale -- the tonic's scale offset is zero by definition, so this is
        the same number the file path publishes as bagpipe_tonic_hz.
        """
        n = part.bank.scale_tonic_note
        if n is None:
            return 0.0
        t = part.bank.get(n, 100, part.bank.leslie_default)
        if t is None:
            return 0.0
        # ...AND THE CHANNEL'S OWN TUNING, if one was sent. A drone is tuned to
        # the chanter, so retuning the channel has to move both or the pipe
        # goes out with itself -- the same argument that made the drones
        # ratios of the tonic rather than absolute Hz.
        hz = float(np.asarray(t["nf"])[:t["P"]].min())
        return hz if ch is None else hz * self._sota_ratio(ch, n)

    def _glide(self, part, ch, note, slots):
        """Write this press's portamento into the slots just stamped.

        THE BANK DECIDES WHETHER IT GLIDES AT ALL, and it decides by mechanism
        rather than by a flag: a trombone's slide, a stopped string, a valved
        horn and a lag circuit are four different gestures and only the last
        two are interchangeable. A voice with no mechanism ignores CC5/65/84
        entirely, exactly as one with no damper ignores CC64.
        """
        src = self._glide_from + part.transpose
        tgt = note + part.transpose
        # THE ROUTER, NOT THE PROGRAM. GM 61 Brass Section hands each register
        # to a different body, and two of those bodies are a slide and two are
        # valves -- so the mechanism is a fact about the note, not the patch.
        pc = part.bank._voice_class(tgt)
        mech = getattr(pc, "glide_mechanism", None)
        if not mech:
            return
        F = part.bank.freqs()
        if not (0 <= src < len(F)) or F[src] <= 0.0 or F[tgt] <= 0.0:
            return
        # CAN THE MECHANISM REACH? An arm and a slide have a compass; a circuit
        # does not. Out of reach is played clean -- a trombonist whose slide
        # cannot get there does not glide most of the way and jump.
        reach = getattr(pc, "glide_reach_semitones", None)
        if reach is not None and abs(tgt - src) > reach + 1e-9:
            return
        g = T.glide_g(F[tgt], F[src])
        tau = T.glide_tau(self.porta_time.get(ch, 0), F[tgt], F[src], mech)
        idx = np.fromiter(slots, np.int64, len(slots))
        a = self.slab.a
        a["gb"][idx] = g
        a["gt"][idx] = tau
        a["gc"][idx] = tau * T.PORTA_SETTLE_TAUS
        self.slab.dirty = True
        self.glides = getattr(self, "glides", 0) + 1

    def _drones(self, part, ch, n0):
        """Bring the uncorked drones up and cork the rest.

        A DRONE IS THE PART, NOT THE NOTE, which is the whole reason this is
        not a template axis. It sounds from the moment the bag is under
        pressure until the piper lets it down, so it is stamped once, held
        across everything the chanter plays, and released only after the
        chanter has been silent for `part_break_s`.

        The drone is voiced as this same instrument at the drone's own pitch,
        which is the same approximation the offline path makes -- there, a
        drone rides the chanter's harmonic series transposed to 220 or 110 Hz.
        Both are a conical-reed stand-in for what is really a cylindrical pipe
        with a single beating reed; the two renderers at least make it
        together, and the difference between them is which register the series
        is read in.
        """
        want = self.drone_count.get(part.pid, len(part.bank.drone_ratios))
        tonic = self._tonic_hz(part, ch)
        if tonic <= 0.0:
            return
        for i, hz in enumerate(tonic * r for r in part.bank.drone_ratios):
            key = (part.pid, ch, -1 - i, self.DRONE_SLOT)
            on = key in self.slab.live
            if i < want and not on:
                # The nearest key, and then retuned onto the drone's ABSOLUTE
                # frequency -- which is not the same as the nearest key's.
                # A bagpipe is not on an equal-tempered tuner: measured, this
                # voice puts MIDI 57 at 207.4 Hz, a full semitone under A3, so
                # picking the key and stopping would have left the live drones
                # 102 cents below the file's. The correction is read off the
                # template's OWN fundamental rather than assumed, so it holds
                # whatever tuner the part is on.
                note = int(round(69.0 + 12.0 * math.log2(hz / 440.0)))
                if not MELODIC_RANGE[0] <= note <= MELODIC_RANGE[1]:
                    continue
                tmpl = part.bank.get(note, 100, part.bank.leslie_default)
                if tmpl is None:
                    self.misses += 1
                    continue
                g = (part.bank.drone_gain[i]
                     if i < len(part.bank.drone_gain) else 1.0)
                if not self.slab.stamp(tmpl, key, n0,
                                       g * part.gain() * self._chan_gain(ch)):
                    self.dropped += 1
                    continue
                slots = self.slab.live.get(key)
                f0 = float(np.asarray(tmpl["nf"])[:tmpl["P"]].min())
                if slots is not None and f0 > 0.0 and abs(hz / f0 - 1.0) > 1e-9:
                    # ...and this is also what puts the two tenors three cents
                    # apart, since drone_hz already carries that and both land
                    # on the same key. It is the beat a piper calls drone lock.
                    self.slab.retune(slots, n0, om_scale=hz / f0)
            elif i >= want and on:
                self.slab.release(key, n0)

    def _drone_reap(self, n0):
        """Let the bag down once the chanter has been quiet long enough.

        Offline this is `part_break_s`, a gap in a score the renderer can see
        the far side of. Live there is no far side, so the same number is spent
        as a HOLD: the drones stay up through a rest and stop only when the
        piper has plainly stopped playing. Without it every gap between two
        notes would cork and re-sound three drones.
        """
        if not self.drone_quiet:
            return
        for pid, (ch, when, hold) in list(self.drone_quiet.items()):
            if n0 - when < hold:
                continue
            del self.drone_quiet[pid]
            for k in [k for k in list(self.slab.live)
                      if k[0] == pid and k[3] == self.DRONE_SLOT]:
                self.slab.release(k, n0)

    def _note_off(self, part, ch, note, n0):
        self._amp_touch(part)
        if part.bank.drone_wheel:
            # Arm the hold rather than release: this key may be the middle of a
            # phrase. _drone_reap decides, part_break_s later.
            self.slab.release((part.pid, ch, note, None), n0)
            if not self._chanting(part, ch):
                self.drone_quiet[part.pid] = (
                    ch, n0, int(part.bank.part_break_s * self.rate))
            return
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

    def _bend_range(self, ch):
        return self.brange.get(ch, self.bend_range)

    def _repitch(self, ch, n0):
        """Recompute this channel's total pitch ratio and move its notes to it.

        ONE PRODUCT, ONE LAST-APPLIED VALUE. The wheel, the bend range (RPN 0),
        the coarse tune (RPN 2) and the fine tune (RPN 1) are four inputs to a
        single ratio, and applying any of them RELATIVELY against the last one
        means they cannot fight each other.

        It is also why the RAW wheel value has to be kept, which nothing did
        before: `bend` holds a ratio, so changing the range while the wheel is
        off centre has to recompute from the wheel -- and moving the sounding
        pitch when the range changes is the entire point of RPN 0.
        """
        r = (self._bend_range(ch) * self.wheel.get(ch, 0) / 8192.0 / 12.0
             + (self.coarse.get(ch, 0.0) + self.fine.get(ch, 0.0) / 100.0) / 12.0)
        ratio = 2.0 ** r
        prev = self.bend.get(ch, 1.0)
        if ratio == prev:
            return
        self.bend[ch] = ratio
        here = [p for p in self.parts if self._listens(p, ch)]
        rotors = [p for p in here if p.bank.leslie]
        if rotors:
            # A layered rig can have a Hammond and a lead on one channel, and
            # only one of them has a reason to ignore the wheel.
            keep = {p.pid for p in here if not p.bank.leslie}
            if keep:
                self.slab.retune(self._sounding(ch, pids=keep), n0,
                                 om_scale=ratio / prev)
        else:
            self.slab.retune(self._sounding(ch), n0, om_scale=ratio / prev)

    def _sota_ratio(self, ch, note):
        """This channel's scale/octave factor for one written key."""
        t = self.sota.get(ch)
        return 1.0 if not t else 2.0 ** (t[note % 12] / 1200.0)

    def _resota(self, ch, n0):
        """Move this channel's sounding notes onto a new scale/octave table.

        TWELVE RATIOS, NOT ONE, which is the whole reason this cannot go
        through _repitch. Each pitch class is retuned against the ratio last
        applied to THAT class, so a stream of tables cannot compound -- the
        same discipline the bend and the fader use, twelve times over.

        No rebuild: a template is a set of partial frequencies and retune
        scales them. Baking a channel's tuning into templates would mean the
        bank cache key grew a channel, which is sixteen times the build cost
        and sixteen times the memory.
        """
        for pc in range(12):
            want = self._sota_ratio(ch, pc)
            was = self.sota_at.get((ch, pc), 1.0)
            if want == was:
                continue
            self.sota_at[(ch, pc)] = want
            slots = self._sounding(ch, pcs={pc})
            if slots:
                self.slab.retune(slots, n0, om_scale=want / was)

    def _rpn_data(self, ch, cc, value, n0):
        """CC6/CC38 into whichever RPN is selected. Unknown ones are ignored."""
        sel = self.rpn.get(ch, (127, 127))
        if sel is None or sel == (127, 127):
            return                      # RPN null, or an NRPN: not ours
        if sel == (0, 0):               # pitch bend sensitivity
            if cc == 6:
                # CC6 is semitones and zeroes the cents, which is the universal
                # convention and makes a bare 101/100/6 exact -- which is what
                # almost every GM file sends.
                self.brange[ch] = float(value)
            else:
                self.brange[ch] = float(int(self._bend_range(ch))) + value / 100.0
        elif sel == (0, 1):             # fine tuning, 14-bit, +/-100 cents
            if cc == 6:
                self._rpn_fine_msb[ch] = value
            lsb = value if cc == 38 else 0
            msb = self._rpn_fine_msb.get(ch, 64)
            self.fine[ch] = ((msb << 7 | lsb) - 8192) / 8192.0 * 100.0
        elif sel == (0, 2):             # coarse tuning, MSB only, +/-64 st
            if cc == 6:
                self.coarse[ch] = float(value - 64)
        else:
            return
        self._repitch(ch, n0)

    # Sent as real messages rather than re-implemented, because CC1 on this
    # engine is seven different controls chosen per voice (drive, drone count,
    # rockers, detune, tremolo depth, crescendo, vibrato) and a second copy of
    # that logic would be wrong within a week. Contains no CC121 and no sysex,
    # so _reset_controllers cannot recurse.
    _RESET_CC = ((1, 0), (11, 127), (64, 0), (65, 0), (66, 0), (67, 0))

    def _reset_controllers(self, n0, ch):
        """CC121. Modulation, expression, pedals, bend, pressure, RPN select.

        NOT CC7 volume, NOT CC10 pan, NOT the program, and NOT the tuning RPNs:
        those are what a GM System On resets, and this is not one.

        CLEARING THE DICTS IS NOT ENOUGH. A sounding note carries the old bend
        in its `om` and the old expression in its amplitude, so each is put
        back by the branch that put it there -- through the same inverse-ratio
        arithmetic that makes a stream of controllers non-compounding.
        """
        self.wheel[ch] = 0
        self._repitch(ch, n0)
        # A PENDING CC84 IS NOT A CONTROLLER AND STILL GOES. It is a one-shot
        # that has not fired yet, and leaving it armed across a reset would let
        # a glide arrive from a source note the file asked for before somebody
        # said "put everything back". CC5 stays: it is a setting, like the bend
        # range, and GM's reset list does not name it either.
        self.porta_src.pop(ch, None)
        for cc, v in self._RESET_CC:
            try:
                self._one(n0, mido.Message("control_change", channel=ch,
                                           control=cc, value=v))
            except Exception as e:
                self.errors += 1
                self.last_error = "%s: %s" % (type(e).__name__, e)
        try:
            self._one(n0, mido.Message("aftertouch", channel=ch, value=0))
        except Exception:
            pass
        self.rpn[ch] = (127, 127)
        self.pw_armed[ch] = True

    def _sysex(self, n0, msg):
        """GM System On: F0 7E <dev> 09 01 F7.

        Anything else is ignored SILENTLY and does not count an error -- a
        Roland GS or Yamaha XG header in a file is not a malformed message,
        it is a message for a different machine.

        IT RE-PROGRAMS THE PARTS THAT EXIST AND CREATES NONE. A real GM module
        is sixteen-part multitimbral; a Part here is an explicit assignment
        with a channel, a key range, a level and a registration, and
        manufacturing sixteen of them would demolish a hand-built split and cut
        every held note. That is the one place this is not GM Level 1 complete,
        and it is deliberate.
        """
        d = tuple(msg.data)
        # SCALE/OCTAVE TUNING first: same universal id, a different sub-id, and
        # the codec lives in blockrender so the two renderers cannot read the
        # same bytes differently.
        import blockrender as _BRs
        _t = _BRs.parse_sota(d)
        if _t is not None:
            _chs, _cents = _t
            for _c in _chs:
                self.sota[_c] = list(_cents)
                self._resota(_c, n0)
            return
        if len(d) < 4 or d[0] != 0x7E or d[2] != 0x09 or d[3] not in (0x01, 0x03):
            return
        self._all_off(n0)
        for ch in range(16):
            self._reset_controllers(n0, ch)
            self.vol[ch] = T.GM_DEFAULT_VOLUME
            self.expr[ch] = T.GM_DEFAULT_EXPRESSION
            try:
                self._one(n0, mido.Message("control_change", channel=ch,
                                           control=10, value=T.GM_DEFAULT_PAN))
            except Exception:
                pass
            # The per-channel tuning RPNs go; self.bend_range does NOT. GM says
            # +/-2, and that is what an absent override gives -- but the TUI
            # knob and the preset are the human, and a file does not overrule
            # the person at the console.
            self.brange.pop(ch, None)
            self.coarse.pop(ch, None)
            self.fine.pop(ch, None)
            self._repitch(ch, n0)
            # ...and the channel's scale/octave table, which is a tuning and so
            # survives CC121 but not a system reset. Cleared THEN re-applied,
            # so any note still sounding is moved back to equal rather than
            # left where the old table put it.
            self.sota.pop(ch, None)
            self._resota(ch, n0)
        self.cgain.clear()
        for part in self.parts:
            want = (0, part.drums, part.tuner)
            if (part.bank.program, part.bank.drums, part.bank.tuner) != want:
                self.bank_reqs.append((part.pid, want))
        if self.bank_reqs:
            self.bank_go.set()

    def _bank_worker(self):
        """Build voices off the audio thread, for program changes.

        `_one` runs INSIDE the PortAudio callback, where the budget is 2.7 ms
        and a full Bank.warm is 0.4 to 8.5 SECONDS. So a program change only
        queues here, and this thread does the work -- the same division
        _amp_worker already makes for distortion, for the same reason.

        AND IT SWAPS THE VOICE BEFORE IT IS WARM. Constructing a Bank costs 5
        to 33 ms (measured); warming it costs up to 8.5 s. Waiting for warm
        would mean seconds of silence after every program change, and a GM file
        that cycles sixteen programs would never catch up. So the part is
        pointed at the cold bank immediately and plays whatever templates exist
        -- none, at first, which Bank.get already handles by returning None and
        counting a miss. The misses are then filled ON DEMAND, one template at
        a time (13.9 ms for the worst voice), so a chord struck on a fresh
        program is silent once and sounds ~60 ms later. That is the difference
        between a usable program change and an unusable one.
        """
        while not self.bank_stop:
          try:
            if not self.bank_go.wait(0.2):
                continue
            self.bank_go.clear()
            # BUSY SPANS THE WHOLE PASS, not just the build. The queue empties
            # the instant a request is POPPED, so anything watching bank_reqs
            # alone sees an idle builder in the window between the pop and the
            # first assignment to bank_label -- and calls the swap done before
            # it has been posted. That is a race a test wins by luck.
            self.bank_busy = True
            while self.bank_reqs and not self.bank_stop:
                pid, want = self.bank_reqs.popleft()
                # COALESCE. A file that sweeps a bank select sends a dozen
                # program changes in a row and only the last one is worth
                # building.
                if any(p == pid for p, _ in self.bank_reqs):
                    continue
                part = next((q for q in self.parts if q.pid == pid), None)
                if part is None:
                    continue        # the rig was rebuilt under us; drop it
                try:
                    with _BANK_LOCK:
                        bank = _BANKS.get(want)
                        if bank is None:
                            bank = Bank(want[0], want[1], want[2])
                            _BANKS[want] = bank
                        _BANKS.move_to_end(want)
                    self.post(lambda n0, _p=part, _b=bank: self._swap_bank(_p, _b, n0))
                    # Published BEFORE the warm, which is the call that can
                    # evict: the new bank is on stage the moment it is swapped
                    # in, and the old one still is until then.
                    pin_banks({(q.bank.program, q.bank.drums, q.bank.tuner)
                               for q in self.parts} | {want})
                    self.bank_label = "%d" % want[0]
                    bank.warm(stop=lambda: bool(self.bank_reqs) or self.bank_stop)
                    self.bank_label = None
                except Exception as e:
                    self.bank_err = "%s: %s" % (type(e).__name__, e)
                    self.bank_label = None
            self._fill_misses()
            self.bank_busy = False
          except BaseException as e:
            # A builder thread that dies silently takes the feature with it and
            # leaves no trace; this is the only place that can say so.
            import traceback
            self.bank_err = traceback.format_exc()
            self.bank_label = None
            self.bank_busy = False

    def _fill_misses(self):
        """Build the templates a note actually asked for and did not find."""
        while self.warm_reqs and not self.bank_stop:
            bank, note, bucket, axis = self.warm_reqs.popleft()
            if (note, bucket, axis) in bank.templates:
                continue
            try:
                t = bank._raw_template(note, bank.bucket_vel(bucket), axis)
            except Exception:
                t = None
            if t is not None:
                # One writer, and Bank.get is a pure dict lookup, so this is
                # safe against the audio thread under the GIL.
                bank.templates[(note, bucket, axis)] = t
                bank.partials += t["P"]

    def _swap_bank(self, part, bank, n0):
        """Point a part at a new voice, on the audio thread.

        Notes already sounding keep the templates they were struck with, which
        is what a program change means. What must go is everything keyed to the
        OLD voice: its panel state, and its amplifier's products.
        """
        part.set_bank(bank)
        for d in (self.drive_step, self.trem_depth, self.clav_step,
                  self.detune_step, self.drone_count, self.drone_quiet):
            d.pop(part.pid, None)
        self.amp_dirty.discard(part.pid)
        self._amp_touch(part)

    def wait_bank(self, timeout=30.0):
        """Block until the builder is idle -- for tests and for the TUI."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if (not self.bank_reqs and not self.warm_reqs
                    and not self.bank_busy and self.bank_label is None):
                self.apply(self.n)
                return True
            time.sleep(0.01)
        return False

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
            pid, key, src, f, am, ph, drive, when, ref, imb = job
            try:
                fc, ac, pc = _TA.combine(f, am, ph)
                _kw = {} if imb is None else {"imbalance": float(imb)}
                out = _TA.emit(fc.tolist(), ac.tolist(), pc.tolist(),
                               float(self.rate), drive,
                               window_s=_TA.LIVE_WINDOW_S,
                               oversample=_TA.LIVE_OVERSAMPLE,
                               keep=_TA.LIVE_KEEP, reference=ref, **_kw)
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
                getattr(part.bank, 'amp_reference', None),
                getattr(part.bank, 'amp_imbalance', None))

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
        # THE SWELL BOX IS CC11, which is the one control a pipe organ's
        # console really has -- so the organ path takes the channel gain too,
        # even though it takes no velocity at all. It cannot come from the
        # scale computed in _note_on, because this branch returns before that
        # is used.
        if not self.slab.stamp_cols(cols, n, key, n0,
                                    part.gain() * self._chan_gain(ch),
                                    hrel, 0, False):
            self.dropped += 1
            return
        # A REGISTERABLE VOICE STILL TAKES A TUNING, even though it takes no
        # bend. `_note_on` returns here before every per-channel pitch
        # adjustment, which is right for the wheel -- an organ has no pitch
        # bend and a Hammond's tonewheels run off a synchronous motor -- and
        # wrong for a temperament. The harpsichord is registerable, and a
        # harpsichord is the instrument a temperament is FOR: measured before
        # this line existed, a channel tuned to Sankey's offsets moved a
        # trumpet by -9.766 cents and a harpsichord by 0.000.
        _sr = self._sota_ratio(ch, note)
        if _sr != 1.0:
            self.slab.retune(self.slab.last_slots, n0, om_scale=_sr)
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

        AND NOT A NOTE THE SOSTENUTO PEDAL IS HOLDING, which is the same trap
        a third time: its key is not down, so without the guard the sweep takes
        it one block after the pedal caught it. The damper pedal is safe here
        only because `pedalled` is checked below; sostenuto needed its own.

        AND NOT THE BAGPIPE'S DRONES, for exactly the same reason and caught
        exactly the same way. A drone belongs to the PART, so no key is ever
        down for it -- and it was stamped, swept one block later, and rendered
        43 dB under the chanter instead of 14. It sounded like a faint buzz and
        measured like one. Its lifetime is the phrase's, and _drone_reap is
        what keeps it honest.
        """
        for k in [k for k in list(self.slab.live)
                  if k[3] not in ("amp", self.DRONE_SLOT)
                  and (k[1], k[2]) not in self.sost.get(k[1], ())
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

    def _sounding(self, ch, pids=None, note=None, pcs=None):
        """Every slot sounding on this channel, optionally narrowed to a set of
        parts, to one note, or to a set of PITCH CLASSES.

        The pitch-class filter exists for scale/octave tuning, which is twelve
        different ratios where everything else here is one. Keyed on the
        WRITTEN note, `k[2]`, not the sounding one: the MIDI spec indexes the
        table by the key number received, so a transposed Part is tuned by the
        key the player pressed and not by the pitch that comes out. That is
        also, conveniently, the number the slab key already carries.

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
            if pcs is not None and (k[2] % 12) not in pcs:
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
            self._drone_reap(n0)
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
        # FLUSHED, because an abnormal exit discards whatever stdout had
        # buffered -- and a suite that dies without saying which check it died
        # in costs more time than every check in it saves. (Twice today: a
        # program change that worked perfectly and could not say so, and this.)
        print("   %-54s %s%s" % (name, "ok" if ok else "FAIL", detail),
              flush=True)
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

    # ---- THE WINDING, which is what sets a pickup's level -------------------
    # The model had geometry and no turns, so a bridge humbucker -- the hottest
    # pickup anyone fits -- came out the QUIETEST voice on the instrument, and
    # GM 30 measured 3.2 dB under GM 29. A builder winds a bridge pickup hotter
    # precisely because the string moves least there.
    def _pk(q, h):
        return q.pickup_gain(h)
    # The coil's own aperture sinc is in there too, so build the expectation
    # rather than assuming h1 escapes it.
    _x = math.pi * inst[30].pickup_width
    _expect = (abs(math.sin(math.pi * 0.049) + math.sin(math.pi * 0.077))
               * abs(math.sin(_x) / _x) * inst[30].pickup_turns)
    check("a humbucker's coils are in series, not averaged",
          abs(_pk(inst[30], 1) - _expect) < 1e-12,
          "  (h1 reads %.4f = both coils summed, x %.2f turns)"
          % (_pk(inst[30], 1), inst[30].pickup_turns))
    check("...and a bridge pickup is wound hotter than a middle one",
          inst[30].pickup_turns > inst[27].pickup_turns
          and inst[29].pickup_turns > inst[27].pickup_turns,
          "  (16.6k humbucker %.2f, 6.2k bridge coil %.2f, 5.8k middle 1.00)"
          % (inst[30].pickup_turns, inst[29].pickup_turns))
    # A HUMBUCKER'S COILS ARE EACH SMALLER, which is the half of it that stops
    # the series sum turning into a flat +6 dB on every humbucker.
    check("...while a vintage humbucker's coils are each SMALLER than a single",
          inst[26].pickup_turns < 1.0 < 2.0 * inst[26].pickup_turns,
          "  (4.0k per coil = %.2f, but two in series = %.2f)"
          % (inst[26].pickup_turns, 2.0 * inst[26].pickup_turns))
    # THE WINDING IS A LEVEL, NOT A COLOUR -- the one thing that must not move.
    _shape = lambda q: [q.harmonic_volume(h) / q.harmonic_volume(1)
                        for h in range(1, 25)]
    class _NoTurns(_T.DistortionGuitarProperties):
        pickup_turns = 1.0
    _w = max(abs(a - b) for a, b in zip(_shape(inst[30]),
                                        _shape(_NoTurns(220.0, 0.0, 1.0, 1.0))))
    check("...and the turns set the level without touching the tone",
          _w < 1e-9, "  (worst shape deviation %.1e over 24 harmonics)" % _w)
    # THE INVERSIONS THEMSELVES. Rendered levels are in examples/levels.py;
    # what is checkable here is that the mechanism points the right way.
    check("the distortion guitar is hotter at the pickup than the overdriven one",
          _pk(inst[30], 1) > _pk(inst[29], 1),
          "  (h1 %.3f vs %.3f)" % (_pk(inst[30], 1), _pk(inst[29], 1)))
    # ...and a slap, whose brightness costs it the bottom of a 1/n series, gets
    # its level back from the arm rather than from a filter.
    check("a slap arrives harder than a pluck, and says so as momentum",
          binst[36].initial_gain > 1.5 * binst[33].initial_gain
          and binst[37].initial_gain > binst[36].initial_gain,
          "  (finger %.3f, slap %.3f, pop %.3f)"
          % (binst[33].initial_gain, binst[36].initial_gain,
             binst[37].initial_gain))
    # THE REPO RULE: initial_gain and amp_reference move together, or the
    # louder voice is also a more distorted one.
    # Each family has its own base ratio (a bass rig is not a guitar rig), and
    # within a family the reference must have tracked the winding EXACTLY --
    # turns times coils, since that is the whole of what changed at the valve's
    # input. Any other number means one of these voices is now more distorted
    # than it was voiced to be.
    _base = {"g": (0.1772 / 0.0869, 1.0), "b": (0.2289 / 0.2790, 1.0)}
    _amped = [(26, inst[26], "g"), (29, inst[29], "g"), (30, inst[30], "g"),
              (36, binst[36], "b"), (37, binst[37], "b")]
    _err = []
    for _n, _q, _fam in _amped:
        _want = (_q.pickup_turns * len(_q.pickup_points)) * _base[_fam][0]
        _got = _q.amp_reference / _q.initial_gain
        _err.append((_n, abs(_got / _want - 1.0)))
    check("...and every re-levelled voice kept its drive where it was",
          max(e for _n, e in _err) < 1e-9,
          "  (reference/gain tracks turns x coils: worst %.1e)"
          % max(e for _n, e in _err))

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

    # ------------------------------------------------ the kit's hand drums
    import percussion_map as _PMk
    # Notes 60-66 and 86-87 were ONE MembraneDrumProperties: nine notes, four
    # instruments. They share a circular head and its twelve Bessel modes and
    # very little else -- what separates a bongo from a surdo is the SHELL, and
    # what separates a timbale from a conga is what the shell is made of.
    _kit = {_n: _PMk.PERCUSSION[_n][1] for _n in (60, 61, 62, 63, 64, 65, 66, 86, 87)}
    check("the kit's hand drums are four instruments, not one",
          len({_c.__name__ for _c in _kit.values()}) == 4
          and _kit[60] is _T.BongoProperties and _kit[65] is _T.TimbaleProperties,
          "  (bongo, conga, timbale, surdo across nine notes)")
    # A SHELL RADIATES ON ITS OWN; it does not filter the head. The first
    # version made it a formant, and measured against the head's modes three of
    # the four shells had nothing to filter: a conga's cavity sits near 128 Hz
    # and a surdo's near 52, BELOW the lowest mode, while a timbale's steel
    # rings above 1280 and the highest mode reaches 1116.
    _cg = _kit[63](210.0, 0.0, 1.0, 1.0)
    _shell = [210.0 * (1.0 + _v[2]) for _v in _cg.unison_voices(210.0, 1, 30.0)]
    check("...and a shell RADIATES, where a formant could only have filtered",
          _shell and min(_shell) < 210.0 * _kit[63].mode_ratios[0],
          "  (the conga's %.0f Hz sits under its own %.0f Hz head)"
          % (min(_shell), 210.0))
    _tb = _kit[65](270.0, 0.0, 1.0, 1.0)
    _tshell = [270.0 * (1.0 + _v[2]) for _v in _tb.unison_voices(270.0, 1, 30.0)]
    check("...and the timbale's steel rings above the head, where wood cannot",
          max(_tshell) > 270.0 * _kit[65].mode_ratios[-1] * 1.5
          and _kit[65].shell_decay_db < _kit[63].shell_decay_db,
          "  (%.0f Hz against a head reaching %.0f, and it holds it longer)"
          % (max(_tshell), 270.0 * _kit[65].mode_ratios[-1]))
    # ...AND ONCE PER NOTE, NOT PER MODE. A shell is one resonance; emitting it
    # under every harmonic would put twelve copies of it in the sound.
    check("...and the shell is emitted once, not under every mode",
          len(_cg.unison_voices(210.0, 1, 30.0)) > 0
          and not _cg.unison_voices(210.0, 2, 30.0),
          "  (under harmonic 1 only)")
    # AN ELECTRIC SNARE IS A MACHINE, not the acoustic snare at another pitch.
    _es = _PMk.PERCUSSION[40][1]
    check("...and the electric snare is a drum machine, not a retuned snare",
          _es is _T.ElectricSnareProperties and _es.tension_bend > 0.0
          and not _es.strike_noise_slope,
          "  (its body DROPS, and it does not get rattlier when hit harder)")

    # --------------------------------------- the three "recordings of the world"
    import patch_map as _PMr
    # 123, 124 and 125 were the last programs in the bank marked CATEGORY ERROR
    # and the last at rating 1. Ben: "We can do all of them physically, yes?" --
    # and all three turned out to be instruments once named properly.
    _bt = _PMr.property_class_for_note(123, 60)
    _tp = _PMr.property_class_for_note(124, 60)
    _hc = _PMr.property_class_for_note(125, 60)
    check("the bird, the telephone and the helicopter are modelled, not sampled",
          all(not issubclass(_c, _T.MalletProperties) for _c in (_bt, _tp, _hc))
          and len({_c.__name__ for _c in (_bt, _tp, _hc)}) == 3,
          "  (a chirp, a struck bell, and a blade passing frequency)")
    # A TELEPHONE IS A BELL STRUCK TWENTY TIMES A SECOND -- the thing in the
    # room, not the 440+480 Hz ringback the exchange sends the caller. The
    # repetition is GM 102's mechanism, whose limitation there (repeated ONSETS
    # rather than a repeated signal) is exactly right for a clapper.
    _on = _tp(261.63, 0.0, 1.0, 1.0).section_onsets_at(261.63)
    _gap = _on[2] - _on[1]
    check("...and the telephone's clapper strikes about twenty times a second",
          18.0 < 1.0 / _gap < 24.0 and _on[-1] > 0.5,
          "  (%d strikes %.0f ms apart, spanning %.2f s of the note)"
          % (len(_on) - 1, 1000 * _gap, _on[-1]))
    # ...which needed the entry cap raised, or the bell rings for the first
    # quarter of each burst and then sits silent.
    check("...which it could not do at the default entry cap",
          _tp.unison_onset_fraction_max > 0.9
          and _T.SynthProperties.unison_onset_fraction_max == 0.25,
          "  (%.0f%% of the note against a section's 25%%)"
          % (100 * _tp.unison_onset_fraction_max))
    # A HELICOPTER'S FUNDAMENTAL IS BELOW HEARING. The written note picks the
    # ROTOR, four octaves down, and what reaches the ear is the series above it.
    check("...and the helicopter's note chooses a rotor, not a pitch",
          _hc.sounding_octaves <= -3.0
          and _T.SynthProperties.sounding_octaves == 0.0
          and [_n for _n, _c in vars(_T).items()
               if isinstance(_c, type) and getattr(_c, "sounding_octaves", 0.0)]
          == ["HelicopterProperties"],
          "  (a written C4 sounds at 16.3 Hz, with partials every 16.3 to 1 kHz)")
    # A BIRD IS A CHIRP: tension_bend for the third time and in the third
    # direction -- the piano's sag, the synth drum's 808 fall, and a bird's
    # RISE. Negative, which only works because the steelpan fixed a register
    # scaling that silently skipped any voice whose bend was not positive.
    # Fetched here rather than borrowed from the block below: that one runs
    # AFTER this and its _sd was not yet bound, which the selftest caught by
    # crashing -- the third time in this session a check has been the thing
    # that found the mistake.
    _sd118 = _PMr.property_class_for_note(118, 60)
    check("...and the bird's pitch RISES, where the synth drum's falls",
          _bt.tension_bend < 0.0 and _sd118.tension_bend > 0.0,
          "  (rendered on C6: 999 Hz, then 1040, then 1050 -- the written 1047)")

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
    # CC1 SAYS HOW MANY, NOT HOW LOUD. A piper does not turn a drone down, they
    # CORK it -- so the wheel selects a count out of the set the instrument has,
    # and each step is a pipe that existed: the Great Highland Bagpipe carried
    # two tenors for most of its history and the bass drone was added later.
    _was = _T.bagpipe_drones
    _counts = []
    try:
        for _n in (0, 1, 2, 3):
            _T.bagpipe_drones = _n
            _counts.append(len(_eth[109](392.0, 0.0, 1.0, 1.0)
                               .unison_voices(392.0, 1, 0.0)))
    finally:
        _T.bagpipe_drones = _was
    check("...and CC1 corks them one at a time, rather than turning them down",
          _counts == [0, 1, 2, 3],
          "  (0 is the chanter alone; 2 is the pipe before the bass drone)")
    # ...AND THE ORDER IS THE INSTRUMENT'S OWN. drone_hz is (tenor, tenor, bass),
    # so the count is a slice and every intermediate state is playable.
    _T.bagpipe_drones = 2
    try:
        _two = sorted(392.0 * (1.0 + _v[2]) for _v in
                      _eth[109](392.0, 0.0, 1.0, 1.0).unison_voices(392.0, 1, 0.0))
    finally:
        _T.bagpipe_drones = _was
    check("...and two drones means two TENORS, not a tenor and the bass",
          len(_two) == 2 and min(_two) > 150.0,
          "  (%s Hz -- the two-drone pipe, not half of the modern one)"
          % ", ".join("%.0f" % _x for _x in _two))
    # AND THEY BELONG TO THE PART. Ben: "The drones seem to me to be a channel
    # event?" -- they are, and attaching them to the note made them restart on
    # every one. The flag is general; the bagpipe is the only voice that sets
    # it, because a chorus, a section and a set of sympathetic strings all
    # belong to the note that excited them and a drone does not.
    _spanners = [_n for _n, _c in vars(_T).items()
                 if isinstance(_c, type) and getattr(_c, "unison_spans_part", False)]
    check("...and they span the PHRASE, not the note and not the channel",
          _eth[109].unison_spans_part
          and not _T.SynthProperties.unison_spans_part
          and _spanners == ["BagpipeProperties"]
          and _eth[109].part_break_s > 0.0,
          "  (rendered: the drone holds through a detached line, and stops "
          "dead through a %.0f s rest)" % _eth[109].part_break_s)

    # ---- AND THE SAME THING LIVE, which it was not doing ---------------------
    # Ben, playing it: "Live bagpipe doesn't do the mod control over drones. It
    # does a vibrato." It did. live.py knew nothing about `drone_wheel`, so the
    # bagpipe fell through to the catch-all CC1 branch and got 35 cents of
    # vibrato -- on the one instrument in the bank that cannot have any, since a
    # bag under constant pressure is the entire point of the machine. And the
    # drones themselves were baked into every note's template, so a held line
    # stacked three of them per note.
    lvbp = Live(program=109, rate=48000, frames=128, verbose=False); lvbp.warm()
    _bpb = lvbp.parts[0].bank
    check("the live bagpipe knows it has drones, and keeps them out of the note",
          _bpb.drone_wheel and len(_bpb.drone_ratios) == 3
          and not _bpb.detune_wheel,
          "  (%d drones, %d template axis positions)"
          % (len(_bpb.drone_ratios), len(_bpb.speeds)))
    # THE CHANTER TEMPLATE IS THE CHANTER. If a drone were baked in, the
    # template for a high note would carry partials down at 110 and 220 Hz.
    _nf = np.asarray(_bpb.get(74, 100, _bpb.leslie_default)["nf"])
    check("...so a chanter note carries no 220 Hz drone of its own",
          float(_nf.min()) > 300.0,
          "  (lowest partial %.0f Hz on a written D5, well above the drones)"
          % float(_nf.min()))

    def _bp_drones():
        return sorted(k[2] for k in lvbp.slab.live if k[3] == lvbp.DRONE_SLOT)

    def _bp_cc1(v, n):
        lvbp.on_midi(mido.Message("control_change", channel=0, control=1, value=v))
        lvbp.apply(n)

    # THE WHEEL IS THE CORK, live and offline at the same places.
    lvbp.on_midi(mido.Message("note_on", channel=0, note=74, velocity=100))
    lvbp.apply(0)
    _live_counts = [len(_bp_drones())]
    for _v in (0, 42, 85, 127):
        _bp_cc1(_v, 0)
        _live_counts.append(len(_bp_drones()))
    check("...and live, CC1 corks them exactly where the file does",
          _live_counts == [3, 0, 1, 2, 3],
          "  (3 with no wheel, then %s at CC1 0/42/85/127)"
          % "/".join(str(_c) for _c in _live_counts[1:]))
    # ...AND IT IS NOT A VIBRATO. The bug, asserted directly: after all that
    # wheel movement, nothing on this channel may have picked up a depth.
    check("...and moving the wheel put no vibrato on the chanter at all",
          lvbp.mod.get(0, 0.0) == 0.0 and lvbp.modw.get(0, 0.0) == 0.0
          and float(np.abs(lvbp.slab.a["vd"][lvbp.slab.busy]).max()
                    if lvbp.slab.busy.any() else 0.0) < 1e-9,
          "  (a bag under constant pressure cannot waver, and now does not)")
    # AT THE FILE'S OWN PITCHES, to the Hz. A bagpipe is not on an equal
    # tuner -- measured, this voice puts MIDI 57 at 207.4 Hz, a semitone under
    # A3 -- so picking the nearest key and stopping would have left every live
    # drone 102 cents below the one the renderer writes. The correction is read
    # off the template's own fundamental, which is also what puts the two
    # tenors three cents apart when they land on the same key.
    _dr_f = sorted(float(lvbp.slab.a["om"][lvbp.slab.live[_k]].min())
                   * lvbp.rate / (2.0 * _math.pi)
                   for _k in lvbp.slab.live if _k[3] == lvbp.DRONE_SLOT)
    _want_f = sorted(lvbp._tonic_hz(lvbp.parts[0]) * _r
                     for _r in _bpb.drone_ratios)
    check("...at the file's own drone pitches, not the nearest key's",
          len(_dr_f) == 3
          and max(abs(a / b - 1.0) for a, b in zip(_dr_f, _want_f)) < 1e-6,
          "  (%s Hz against the file's %s)"
          % (", ".join("%.3f" % _x for _x in _dr_f),
             ", ".join("%.3f" % _x for _x in _want_f)))
    check("...and the two tenors are still three cents apart, which is the beat",
          1.0 < 1200 * _math.log2(_dr_f[2] / _dr_f[1]) < 6.0,
          "  (%.1f cents: one beat every %.1f s)"
          % (1200 * _math.log2(_dr_f[2] / _dr_f[1]),
             1.0 / max(abs(_dr_f[2] - _dr_f[1]), 1e-9)))
    # SWEEP MUST NOT TAKE THEM. A drone belongs to the part, so no key is ever
    # down for it -- and sweep releases exactly that. It was stamped, swept one
    # block later, and rendered 43 dB under the chanter where it belongs at 14.
    # Same failure as the amplifier's, whose exemption is two lines above it.
    lvbp.sweep(0)
    check("...and the block sweep leaves them alone, as it does the amplifier",
          len([_k for _k in lvbp.slab.live if _k[3] == lvbp.DRONE_SLOT]) == 3,
          "  (a part-level voice has no key down, and sweep looks for one)")

    # ---- A BAG IS A PRESSURE REGULATOR --------------------------------------
    # Ben, still playing it: "it should be more like an organ: not touch
    # sensitive. Channel volumes only." A piper's arm holds the bag at a
    # constant pressure -- that is what a bag is FOR, and why a piper can
    # breathe without the sound stopping. There is no dynamic marking in pipe
    # music because there is no way to play one.
    #
    # It had touch by DEFAULT rather than by a claim: the reed-pipe chain sits
    # under ReedOrganProperties, but the False lives on FlueOrganProperties, so
    # it fell through to SynthProperties. That default is right for the shanai,
    # which is mouth-blown, and wrong for the one pipe with a bag in the way.
    check("a bag holds one pressure, so the bagpipe has no touch",
          not _eth[109].touch_sensitive and _eth[111].touch_sensitive,
          "  (and the shanai keeps its, being blown by a mouth)")

    # A RANK BORROWS A SPECTRUM, NOT A TOUCH. The line that builds a
    # cross-family stop says "borrow this voice's spectrum only" and then
    # handed the borrowed class a velocity too. A church organ's Gedackt is a
    # StoppedPipeProperties, which sits ABOVE OrganProperties and so takes the
    # touch-sensitive default: one rank of eight scaled by (vel/127)^2 on a
    # patch whose own class says velocity does nothing. Measured, 33 partials
    # of 491 -- exactly the odd harmonics, which is what a stopped pipe has --
    # and the church organ built 8 velocity buckets to carry it.
    _borrowers = [(_n, _c) for _n, _c in sorted(vars(_T).items())
                  if isinstance(_c, type) and getattr(_c, "stop_ranks", None)
                  and not _c.touch_sensitive
                  and any(len(_r) > 3 and isinstance(_r[3], type)
                          and _r[3].touch_sensitive for _r in _c.stop_ranks)]
    check("a voice with no touch has no touch in its ranks either",
          len(_borrowers) >= 3,
          "  (%s borrow a touch-sensitive spectrum, and must not borrow the touch)"
          % ", ".join(_n.replace("Properties", "") for _n, _c in _borrowers))
    _spread = []
    for _g, _lab in ((19, "church organ"), (16, "drawbar organ"),
                     (80, "square lead"), (109, "bagpipe")):
        _l = Live(program=_g, rate=48000, frames=128, verbose=False)
        _b = _l.parts[0].bank
        _t1 = _b._raw_template(60, 127); _t2 = _b._raw_template(60, 32)
        _r = (np.asarray(_t2["aL"])[:_t2["P"]]
              / np.maximum(np.asarray(_t1["aL"])[:_t1["P"]], 1e-30))
        _r = _r[np.isfinite(_r) & (_r > 0)]
        _spread.append((_lab, _b.nbuckets,
                        20 * _math.log10(_r.max() / max(_r.min(), 1e-30))))
        _l.renderer.close()
    # 1e-4 dB, not 0: templates are stored as float32, so the square lead's
    # 64 partials come back 1e-6 dB apart at two velocities from rounding
    # alone. The threshold is a storage limit, not a tolerance for touch.
    check("...so its partials do not move with velocity, and it needs one bucket",
          all(_n == 1 and abs(_d) < 1e-4 for _l, _n, _d in _spread),
          "  (" + ", ".join("%s %d bucket/%.2f dB" % _t for _t in _spread) + ")")

    # ---- GM Level 1's control surface, live -------------------------------
    # The two renderers had COMPLEMENTARY gaps: live had bend, aftertouch and
    # the pedal and no pan or program change; the file path had pan and
    # program change and none of the others. Neither was the union.
    _gm = Live(program=56, rate=48000, frames=128, verbose=False)
    _gm.warm()

    # PAN IS NOT A GAIN LAW HERE. CC10 offline becomes a position in METRES and
    # then an HRTF, so hard left is 0.10 dB at 100 Hz and 15.2 at 4 kHz plus
    # half a millisecond of interaural delay. An amplitude pan would be a
    # different effect: loud where this one is silent.
    def _panshot(_cc, _note=72):
        _gm.on_midi(mido.Message("control_change", channel=0, control=10, value=_cc))
        _gm.on_midi(mido.Message("note_on", channel=0, note=_note, velocity=100))
        _gm.apply(0)
        _k = [_x for _x in _gm.slab.live if _x[2] == _note][0]
        _sl = _gm.slab.live[_k]
        _a = _gm.slab.a
        _hi = _a["nf"][_sl] > 3000.0
        _r = (float(np.abs(_a["aL"][_sl][_hi]).sum()),
              float(np.abs(_a["aR"][_sl][_hi]).sum()),
              float(_a["delR"][_sl].mean() - _a["delL"][_sl].mean()))
        _gm.on_midi(mido.Message("note_off", channel=0, note=_note, velocity=0))
        _gm.apply(0)
        _gm.slab.release(_k, 0); _gm.slab.reap(10 ** 9)
        return _r
    _pl = _panshot(0); _pc0 = _panshot(64); _pr = _panshot(127)
    _db = lambda a, b: 20 * _math.log10(max(a, 1e-30) / max(b, 1e-30))
    check("CC10 places a source, it does not fade one",
          _db(_pl[0], _pl[1]) > 12.0 and _db(_pr[0], _pr[1]) < -12.0
          and abs(_db(_pc0[0], _pc0[1])) < 1.0,
          "  (above 3 kHz: %+.1f dB hard left, %+.1f centred, %+.1f hard right)"
          % (_db(_pl[0], _pl[1]), _db(_pc0[0], _pc0[1]), _db(_pr[0], _pr[1])))
    check("...with an interaural delay, which is the whole cue in the bass",
          abs(_pl[2] / 48.0 - 0.5) < 0.1 and abs(_pr[2] / 48.0 + 0.5) < 0.1,
          "  (%+.3f ms hard left, %+.3f hard right)"
          % (_pl[2] / 48.0, _pr[2] / 48.0))
    # ...AND THE TIME IMAGE DOES NOT MOVE UNDER A SOUNDING NOTE. delL/delR
    # shift each ear's ENVELOPE in the kernel, so moving them mid-note is a
    # level step, not a click. A pan pot does not move a source's arrival time.
    _gm.on_midi(mido.Message("note_on", channel=0, note=72, velocity=100))
    _gm.apply(0)
    _k = [_x for _x in _gm.slab.live if _x[2] == 72][0]
    _sl = _gm.slab.live[_k]
    _d0 = _gm.slab.a["delL"][_sl].copy()
    _a0 = float(np.abs(_gm.slab.a["aL"][_sl]).sum())
    _gm.on_midi(mido.Message("control_change", channel=0, control=10, value=0))
    _gm.apply(0)
    _a1 = float(np.abs(_gm.slab.a["aL"][_sl]).sum())
    _gm.on_midi(mido.Message("control_change", channel=0, control=10, value=0))
    _gm.apply(0)
    _a2 = float(np.abs(_gm.slab.a["aL"][_sl]).sum())
    check("...and the level image follows the pot while the time image does not",
          _db(_a1, _a0) > 2.0
          and np.array_equal(_d0, _gm.slab.a["delL"][_sl])
          and abs(_a2 - _a1) < 1e-6,
          "  (%+.1f dB, delays bit-identical, and a repeat adds %+.4f dB)"
          % (_db(_a1, _a0), _db(_a2, _a1)))
    _gm.slab.release(_k, 0); _gm.slab.reap(10 ** 9)

    # RPN 0, AND WHY THE RAW WHEEL HAS TO BE KEPT. `bend` holds a ratio and is
    # applied relatively, so changing the range while the wheel is off centre
    # can only work if the wheel value itself was stored -- which nothing did.
    # Moving the SOUNDING pitch when the range changes is the point of RPN 0.
    for _cc, _v in ((101, 0), (100, 0), (6, 2)):
        _gm.on_midi(mido.Message("control_change", channel=0, control=_cc, value=_v))
    _gm.on_midi(mido.Message("pitchwheel", channel=0, pitch=4096))
    _gm.apply(0)
    _c2 = 1200 * _math.log2(_gm.bend[0])
    _gm.on_midi(mido.Message("control_change", channel=0, control=6, value=12))
    _gm.apply(0)
    _c12 = 1200 * _math.log2(_gm.bend[0])
    check("RPN 0 changes the bend range under a wheel already off centre",
          abs(_c2 - 100.0) < 0.1 and abs(_c12 - 600.0) < 0.1,
          "  (half wheel: %.0f cents at +/-2, %.0f at +/-12)" % (_c2, _c12))
    # RPN 1 and 2 are TUNINGS and fold into the same product -- and a null
    # selection must stop a stray CC6 from landing on the last RPN used.
    _gm.on_midi(mido.Message("control_change", channel=0, control=100, value=2))
    _gm.on_midi(mido.Message("control_change", channel=0, control=6, value=64 + 7))
    _gm.apply(0)
    _tot = 1200 * _math.log2(_gm.bend[0])
    for _cc, _v in ((101, 127), (100, 127), (6, 99)):
        _gm.on_midi(mido.Message("control_change", channel=0, control=_cc, value=_v))
    _gm.apply(0)
    check("...and RPN 2 tunes the channel, while a null selection ignores data",
          abs(_tot - 1300.0) < 0.1 and _gm.coarse.get(0) == 7.0,
          "  (600 cents of wheel + 700 of coarse = %.0f, and CC6 after a null "
          "left it at %.0f semitones)" % (_tot, _gm.coarse.get(0, 0)))

    # CC121. Clearing the dicts is not enough: a sounding note carries the old
    # bend in its om and the old expression in its amplitude.
    for _cc, _v in ((7, 40), (11, 40), (10, 0), (64, 127), (1, 100)):
        _gm.on_midi(mido.Message("control_change", channel=0, control=_cc, value=_v))
    _gm.apply(0)
    _gm.on_midi(mido.Message("control_change", channel=0, control=121, value=0))
    _gm.apply(0)
    check("CC121 resets the controllers and keeps what is not one",
          _gm.wheel.get(0) == 0 and _gm.mod.get(0, 0.0) == 0.0
          and _gm.pedal.get(0) is False and _gm.expr.get(0) == 127
          and _gm.vol.get(0) == 40 and _gm.cpan.get(0) == 0
          and _gm.rpn.get(0) == (127, 127) and _gm.coarse.get(0) == 7.0,
          "  (volume, pan and the tuning RPNs survive it -- they are not "
          "controllers; the wheel, mod, pedals and expression do not)")

    # GM System On. It RE-PROGRAMS the parts that exist and creates none: a
    # Part here is an explicit assignment with a channel, a range and a level,
    # and manufacturing sixteen would demolish a hand-built split.
    _gm.on_midi(mido.Message("note_on", channel=0, note=67, velocity=100))
    _gm.apply(0)
    _n_before = len(_gm.slab.live)
    _gm.on_midi(mido.Message("sysex", data=[0x7E, 0x7F, 0x09, 0x01]))
    _gm.apply(128)
    check("a GM System On resets the machine and leaves the rig standing",
          _n_before > 0 and len(_gm.slab.live) == 0
          and _gm.vol.get(0) == _T.GM_DEFAULT_VOLUME
          and _gm.cpan.get(0) == _T.GM_DEFAULT_PAN
          and _gm.bend_range == 2.0 and not _gm.brange and not _gm.coarse,
          "  (%d notes off, volume %d, pan centred, the per-channel tuning "
          "cleared -- and bend_range, which is the TUI's knob, untouched)"
          % (_n_before, _T.GM_DEFAULT_VOLUME))
    _errs = _gm.errors
    _gm.on_midi(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12]))
    _gm.apply(256)
    check("...and a sysex for another machine is ignored, not an error",
          _gm.errors == _errs,
          "  (a Roland GS or Yamaha XG header in a file is not malformed)")
    _gm.shutdown()

    # PROGRAM CHANGE. The audio thread may queue a voice change, never build
    # one: _one runs inside the callback where the budget is 2.7 ms and a warm
    # is up to 8.5 SECONDS. The part is pointed at a COLD bank at once and the
    # templates are filled on demand, one per note actually played.
    _pc = Live(program=56, rate=48000, frames=128, verbose=False)
    _pc.warm()
    _pc.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
    _pc.apply(0)
    _pid0, _held = _pc.parts[0].pid, len(_pc.slab.live)
    _pc.on_midi(mido.Message("program_change", channel=0, program=41))
    _pc.apply(0)
    _ok = _pc.wait_bank(90)
    check("a program change switches the voice without cutting a held note",
          _ok and _pc.parts[0].program == 41 and _pc.parts[0].pid == _pid0
          and len(_pc.slab.live) == _held,
          "  (56 -> 41, the pid kept so every per-part control survives, and "
          "the chord still sounding on its own templates)")
    check("...and the default registration finally applies",
          Bank(16, False, "hybrid").default_stops == 7
          and len(Part(Bank(16, False, "hybrid")).drawn) == 3,
          "  (Bank never assigned self.pc, so hasattr() was always False and "
          "every organ part started on one rank whatever its class declared)")
    _pc.shutdown()

    # ---- PITCH BEND: A TUNING IS NOT A GESTURE ------------------------------
    # The file path ignored the wheel completely -- a render at full deflection
    # and one without came back bit-identical. What that threw away was not
    # only expression: John Sankey's bwv847.mid and bwv974.mid put one pitch
    # class on each channel and one STATIC bend on each, which is a temperament
    # written as twelve numbers, and it was going in the bin.
    #
    # The classifier has no threshold in it. If the wheel never moves while a
    # channel is sounding, a fixed offset on f0 reproduces it EXACTLY -- so it
    # is not an approximation, and a harpsichord can have it.
    import blockrender as _BRb
    import patch_map as _PMb
    check("a static pitch bend is a TUNING, and every voice takes one",
          abs(_T.bend_ratio(-400) - 2.0 ** (-400 / 8192.0 * 2.0 / 12.0)) < 1e-15
          and _T.BEND_RANGE_SEMITONES == 2.0,
          "  (-400 of 8192 is %.2f cents at GM's +/-2 semitones)"
          % (1200 * _math.log2(_T.bend_ratio(-400))))
    # ...AND A MOVING ONE IS A GESTURE, which a struck bar cannot make.
    _nobend = [_g for _g in range(128)
               if not _PMb.property_class_for_note(_g, 60).pitch_bendable]
    check("...but a MOVING one is a gesture, and not every voice has one",
          set(range(16, 24)) <= set(_nobend) and 0 in _nobend and 6 in _nobend
          and 109 in _nobend
          and _PMb.property_class_for_note(40, 60).pitch_bendable
          and _PMb.property_class_for_note(56, 60).pitch_bendable,
          "  (%d voices refuse it: pianos, organs, tuned percussion, the pipes;"
          " a lip and a fingerboard keep it)" % len(_nobend))
    # THE ROWS. A bend is a RATIO, so the phase a partial accrues over a block
    # is w*(r-1)*BLK and the w factors out -- the cumulative term is
    # partial-independent, which is why one pair of rows serves a channel.
    # r is computed FROM the cumulative array so the identity holds by
    # construction: that is what makes the phase continuous across a step in
    # the wheel, and a bend a chirp rather than a click.
    _was_sr = _BRb.SR
    _BRb.SR = 48000
    _r, _c = _BRb.bend_blocks([(0.1, 2.0)], 40)
    _BRb.SR = _was_sr
    _ident = float(np.abs(_c[1:] - (_c[:-1] + (_r[:-1] - 1.0) * _BRb.BLK)).max())
    check("...and the bend rows' phase and frequency agree by construction",
          _ident < 1e-6 and abs(_r[0] - 1.0) < 1e-9 and abs(_r[-1] - 2.0) < 1e-6,
          "  (C[b+1] - C[b] - (r[b]-1)*BLK worst %.1e over 40 blocks)" % _ident)
    # AND THE KERNEL IS CHECKED NOW. Without argtypes a ctypes call does no
    # checking at all: a prototype and a call site out of step give you a
    # pointer read as a float, not a TypeError. Parsed from the C rather than
    # transcribed, because a transcribed copy is one more thing that can drift.
    _at = getattr(_BRb.ensure_lib().synth_voice, "argtypes", None)
    check("...and the kernel's arguments are typed, read off the C itself",
          _at is not None and len(_at) > 40,
          "  (%s argument types derived from synthkernel.c)"
          % (len(_at) if _at else "no"))

    # ---- AFTERTOUCH, and why the two paths agree by algebra -----------------
    # The file path had none at all. It has one number per note now -- the
    # time-weighted MEAN pressure over the note's span, not a note-on snapshot,
    # because pressure is by definition applied after the key is down and a
    # value read at note-on is the previous note's.
    #
    # The agreement with live is algebra, not calibration. Live scales each
    # partial by (f/f0)^(press_tilt*p) with press_tilt = effort_tilt*PRESS_DB/
    # 6.0206; tonelib does attack_dampening -= effort_tilt*effort/6.0206, which
    # is the same expression with effort = PRESS_DB*p. One constant, so they
    # cannot drift.
    _lvp = Live(program=56, rate=48000, frames=128, verbose=False)
    check("aftertouch is one constant, shared by both renderers",
          _lvp.press_db == _T.PRESS_DB and _lvp.press_tilt == _T.PRESS_TILT
          and _T.PRESS_DB == 8.0,
          "  (%.1f dB and a tilt of %.2f, in tonelib where both can see them)"
          % (_T.PRESS_DB, _T.PRESS_TILT))
    _tp = _PMb.property_class_for_note(56, 60)
    _e0 = _tp(261.63, 0.0, 1.0, 1.0, 0.0)
    _e1 = _tp(261.63, 0.0, 1.0, 1.0, _T.PRESS_DB)
    _b = lambda q: (sum(q.harmonic_volume(h) ** 2 for h in range(5, 33))
                    / sum(q.harmonic_volume(h) ** 2 for h in range(1, 33)))
    check("...and pressure opens the series, which is what leaning in does",
          _b(_e1) > _b(_e0) * 1.05 and _tp.effort_tilt > 0.0,
          "  (energy above h4: %.1f%% -> %.1f%% at full pressure)"
          % (100 * _b(_e0), 100 * _b(_e1)))
    _lvp.renderer.close()

    # ---- CC91 reverb is a DISTANCE, which this renderer already had ---------
    # roomtail.py has said so from the start: "the room constant sets the
    # reverberant field against the direct sound at the source distance. No
    # wet/dry knob." T60 does not contain r at all; only the ratio does, and it
    # goes as r squared. So CC91 is how many times the nominal distance a
    # channel stands at, and GM's default of 40 IS that nominal distance -- a
    # file that never sends it renders exactly as it did.
    import roomtail as _RT
    _rp = _T.StoppedPipeProperties(261.63, 0.0, 1.0, 1.0)
    _bands = _RT.decay_and_level(_rp)
    _r0 = _rp.radiation_distance
    _t60 = [t for _f, t, _r in _bands]
    check("the room's decay does not depend on where the source stands",
          max(_t60) / min(_t60) > 1.5,
          "  (T60 %.2f-%.2f s across the bands, and r appears in none of it -- "
          "only in the ratio, as r squared)" % (min(_t60), max(_t60)))
    # ...so a whole channel's contribution to the tail is ONE SCALAR, which is
    # a textbook send bus arrived at from the room equation rather than bolted
    # onto it. The critical distance is where the room overtakes the direct
    # sound, and the bass gets there first -- which is why halls sound warm.
    _rc = [(f, _r0 / _math.sqrt(ratio)) for f, _t, ratio in _bands]
    _lo = [d for f, d in _rc if f <= 125][0]
    _hi = [d for f, d in _rc if f >= 1000][0]
    check("...and the bass reaches the room before the treble does",
          _lo < _hi,
          "  (critical distance %.1f m at 125 Hz against %.1f m at 1 kHz, from "
          "the same formula -- nothing dialled that in)" % (_lo, _hi))
    check("...and GM's default send is the distance the room was placed for",
          _BRb.GM_DEFAULT_REVERB == 40,
          "  (so CC91 40 is 1.00x nominal, 0 is on the microphone and 127 is "
          "%.2fx -- %.1f m, past the %.1f m where the room takes over)"
          % (127.0 / 40, _r0 * 127.0 / 40, _lo))

    # ---- CC93 chorus: systematic, not drawn ---------------------------------
    # A bucket-brigade chorus makes a small number of copies at FIXED offsets,
    # each swept by its own slow oscillator. A string SECTION has many players
    # whose spread is random, per player and per note. GM2's chorus is the
    # first, which is the accordion-musette argument this file already makes
    # three times -- and it is why a chorus can be a pass over the finished
    # partial table at all, where a detune normally cannot: the offsets are
    # constants chosen in advance and only the wet gain follows the controller.
    import chorus as _CHRk
    check("a chorus is a fixed comb, not a section's scatter",
          len(_CHRk.DEFAULT_CENTS) >= 2
          and all(abs(_c) < 30.0 for _c in _CHRk.DEFAULT_CENTS)
          and len(set(_CHRk.SWEEP_HZ)) == len(_CHRk.SWEEP_HZ),
          "  (%s cents, each swept at its own rate so the comb does not march "
          "in step and read as a phaser)"
          % "/".join("%+.0f" % _c for _c in _CHRk.DEFAULT_CENTS))
    # ...AND IT TAKES THE VOICE'S OWN COMB where the voice has one, because on
    # a string machine or a synth pad the chorus is part of what it IS.
    _mach = _CHRk.offsets_for(_PMb.property_class_for_note(51, 60)(261.63, 0, 1, 1))
    _plain = _CHRk.offsets_for(_PMb.property_class_for_note(48, 60)(261.63, 0, 1, 1))
    check("...and it is the instrument's own where the instrument has one",
          tuple(_mach) != tuple(_plain) and len(_mach) >= 2,
          "  (synth strings %s against a plain pair %s)"
          % ("/".join("%+.0f" % _c for _c in _mach),
             "/".join("%+.0f" % _c for _c in _plain)))

    # A SEND IS A MIX, NOT AN ADDITION, which is the same decision CC91 takes.
    # Copies are incoherent with their parent so their POWERS add: two at full
    # send made the channel 3.5 dB louder before the wet share was taken out of
    # the dry one. A controller that raises the level while it is asked for an
    # effect is a controller nobody can use.
    _lc = Live(program=48, rate=48000, frames=128, verbose=False)
    _lc.warm()

    def _chor(_send):
        _lc.on_midi(mido.Message("control_change", channel=0,
                                 control=93, value=_send))
        _lc.on_midi(mido.Message("note_on", channel=0, note=69, velocity=100))
        _lc.apply(0)
        _ks = [_k for _k in _lc.slab.live if _k[2] == 69]
        _pw = sum(float((_lc.slab.a["aL"][_lc.slab.live[_k]] ** 2).sum())
                  for _k in _ks)
        _main = [_k for _k in _ks if _k[3] is None][0]
        _f0 = float(_lc.slab.a["om"][_lc.slab.live[_main]].min())
        _off = sorted(1200 * _math.log2(
            float(_lc.slab.a["om"][_lc.slab.live[_k]].min()) / _f0)
            for _k in _ks if _k[3] is not None)
        _n = sum(len(_lc.slab.live[_k]) for _k in _ks)
        _lc.on_midi(mido.Message("note_off", channel=0, note=69, velocity=0))
        _lc.apply(0)
        for _k in _ks:
            _lc.slab.release(_k, 0)
        _lc.slab.reap(10 ** 9)
        return _n, _pw, _off
    _n0, _p0c, _o0 = _chor(0)
    _n1, _p1c, _o1 = _chor(127)
    check("live, the chorus holds the level it was asked for an effect",
          abs(10 * _math.log10(_p1c / _p0c)) < 0.2 and not _o0,
          "  (%+.2f dB at full send -- the wet share comes out of the dry one, "
          "and powers add because the copies are incoherent)"
          % (10 * _math.log10(_p1c / _p0c)))
    check("...with the copies exactly where the comb says",
          len(_o1) == 2 and abs(_o1[0] + 7.0) < 0.05 and abs(_o1[1] - 7.0) < 0.05,
          "  (%s, and %d slots against %d dry -- capped at %d copies, because "
          "a ten-note string chord at three would be two thirds of the slab)"
          % ("/".join("%+.1fc" % _c for _c in _o1), _n1, _n0, Live.CHORUS_MAX))
    _lc.shutdown()

    # ---- the three pedals GM2 asks for --------------------------------------
    # CC120 ALL SOUND OFF stops a channel dead where CC123 lifts the keys and
    # lets it ring. Those had been the same branch, which is CC120's meaning,
    # not CC123's: a note under a held damper keeps sounding when the keys come
    # up, and so does a struck cymbal, because neither is a key being held.
    _lp = Live(program=0, rate=48000, frames=128, verbose=False)
    _lp.warm()
    for _cc, _want in ((123, True), (120, False)):
        _lp.on_midi(mido.Message("control_change", channel=0, control=64, value=127))
        _lp.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
        _lp.apply(0)
        _lp.on_midi(mido.Message("note_off", channel=0, note=60, velocity=0))
        _lp.apply(0)
        _lp.on_midi(mido.Message("control_change", channel=0, control=_cc, value=0))
        _lp.apply(128)
        _rings = any(_k[2] == 60 for _k in _lp.slab.live)
        if _cc == 123:
            check("CC123 lifts the keys; a pedalled note goes on ringing",
                  _rings is _want, "  (the damper is still off the string)")
        else:
            check("...and CC120 stops the channel, pedal or no pedal",
                  _rings is _want, "  (four milliseconds, not zero -- the "
                  "kernel divides by the release and a cut is a click)")
        for _k in list(_lp.slab.live):
            _lp.slab.release(_k, 0)
        _lp.slab.reap(10 ** 9)

    # CC66 SOSTENUTO holds only what was already down. That asymmetry is the
    # whole instrument and nothing else distinguishes it from sustain.
    _lp.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
    _lp.apply(0)
    _lp.on_midi(mido.Message("control_change", channel=0, control=66, value=127))
    _lp.apply(0)
    _lp.on_midi(mido.Message("note_off", channel=0, note=60, velocity=0))
    _lp.on_midi(mido.Message("note_on", channel=0, note=64, velocity=100))
    _lp.apply(0)
    _lp.on_midi(mido.Message("note_off", channel=0, note=64, velocity=0))
    _lp.apply(0)
    _lp.sweep(128); _lp.sweep(256)
    _alive = sorted({_k[2] for _k in _lp.slab.live})
    check("sostenuto holds the keys that were down, and only those",
          _alive == [60],
          "  (C4 was down when the pedal fell and is held; E4 came after and "
          "is not -- and it survives a sweep, which is where this bug lives)")
    _lp.on_midi(mido.Message("control_change", channel=0, control=66, value=0))
    _lp.apply(384)
    check("...and lets go when the pedal does",
          not [_k for _k in _lp.slab.live if _k[2] == 60], "")
    _lp.shutdown()

    # ---- PORTAMENTO, CC5/CC65/CC84 ------------------------------------------
    #
    # A GLIDE IS A LENGTH MOVING. The kernel carries it per partial as
    # 1/(1 + g*e^(-t/tau)) -- the reciprocal, because f is 1/L and what settles
    # is the hand's position, not the pitch. See midi.md and examples/portamento.py.
    _pg = Live(program=57, rate=44100, frames=128, verbose=False,
               tuner="hybrid440")          # 57 trombone: a real slide
    _pg.warm()

    def _pump(lv, n=2):
        for _ in range(n):
            _n0 = lv.n
            lv.apply(_n0); lv.renderer.render(_n0, 128); lv.n = _n0 + 128

    def _gcols(lv, _note):
        """The glide on THIS note's slots, not on anything the slab still holds.

        Scanning the whole slab for a nonzero gb finds the note BEFORE this one
        -- which is still sounding, still gliding, and still correct -- and so
        reports that every note glides forever. Three checks below failed that
        way before they were asking the right question.
        """
        _sl = [i for k, v in lv.slab.live.items() if k[2] == _note for i in v]
        if not _sl:
            return None
        _i = np.fromiter(_sl, np.int64, len(_sl))
        _g = np.asarray(lv.slab.a["gb"])[_i]
        if not (_g != 0.0).any():
            return None
        _j = _sl[int(np.nonzero(_g != 0.0)[0][0])]
        return tuple(float(np.asarray(lv.slab.a[k])[_j])
                     for k in ("gb", "gt", "gc"))

    # float32 columns: gb lands exactly (0.25 is a power of two), gt does not,
    # so the comparison is relative and sized to the storage rather than to
    # double precision. A tolerance of 1e-9 on a float32 is a test that fails
    # for arithmetic reasons and tells you nothing about the feature.
    def _f32eq(a, b):
        return abs(a - b) <= 1e-6 * max(1.0, abs(b))

    _pg.on_midi(mido.Message("control_change", channel=0, control=5, value=64))
    _pg.on_midi(mido.Message("control_change", channel=0, control=65, value=127))
    _pg.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
    _pump(_pg)
    check("a note with nothing before it does not glide", _gcols(_pg, 60) is None,
          "  (there is nowhere to glide from)")
    _pg.on_midi(mido.Message("note_off", channel=0, note=60, velocity=0))
    _pg.on_midi(mido.Message("note_on", channel=0, note=64, velocity=100))
    _pump(_pg)
    _gc = _gcols(_pg, 64)
    _F = _BRb.tuning_table("hybrid440")
    _wg = T.glide_g(_F[64], _F[60])
    _wt = T.glide_tau(64, _F[64], _F[60], "slide")
    check("...and the next one glides from it, by the tuning table's own ratio",
          _gc is not None and _f32eq(_gc[0], _wg),
          "  (g = %.6f, and 1/(1+g) is the source pitch exactly)" % _wg)
    check("...at the speed CC5 asked for",
          _gc is not None and _f32eq(_gc[1], _wt),
          "  (tau %.4f s, from the LENGTH travelled, not the interval)" % _wt)

    # SAME INTERVAL, SAME TRAVEL, SAME TIME -- the direction symmetry that the
    # first draft of the speed law did NOT have. It normalised the travel by
    # the target length, which made a glide up 25% slower than the identical
    # glide down: an artefact that would have had to be defended as physics.
    _tu = T.glide_tau(64, _F[64], _F[60], "slide")
    _td = T.glide_tau(64, _F[60], _F[64], "slide")
    check("a glide takes the same time in either direction",
          abs(_tu - _td) < 1e-12, "  (%.4f s both ways: it is the same slide)" % _tu)
    # ...BUT NOT THE SAME CURVE. f is 1/L, so the same remaining travel is worth
    # more cents as the tube shortens: an upward glide lingers near its target.
    _hu = -math.log((math.sqrt(1.0 + _wg) - 1.0) / _wg)
    _gd = T.glide_g(_F[60], _F[64])
    _hd = -math.log((math.sqrt(1.0 + _gd) - 1.0) / _gd)
    check("...and not the same curve, which is what makes it a length",
          _hu > math.log(2.0) > _hd,
          "  (half the interval at %.3f tau going up, %.3f down, ln2 = %.3f "
          "for a lag circuit)" % (_hu, _hd, math.log(2.0)))

    # THE REACH IS THE MECHANISM'S. A trombone's slide is a tritone; asked for
    # more, a player does not glide most of the way and jump, they play it.
    _pg.on_midi(mido.Message("note_off", channel=0, note=64, velocity=0))
    _pg.on_midi(mido.Message("note_on", channel=0, note=76, velocity=100))
    _pump(_pg)
    check("past the slide's reach it plays clean instead of gliding",
          _gcols(_pg, 76) is None,
          "  (an octave, and seven positions only span a tritone)")

    # CC84: THE BYTE IS A NOTE NUMBER, it fires once, and Roland's Example 2
    # shows it working with CC65 off and nothing sounding at all.
    _pg.on_midi(mido.Message("control_change", channel=0, control=65, value=0))
    _pg.on_midi(mido.Message("note_off", channel=0, note=76, velocity=0))
    _pump(_pg)
    _pg.on_midi(mido.Message("control_change", channel=0, control=84, value=60))
    _pg.on_midi(mido.Message("note_on", channel=0, note=64, velocity=100))
    _pump(_pg)
    check("CC84 glides with the switch OFF, which is Roland's Example 2",
          _gcols(_pg, 64) is not None and _f32eq(_gcols(_pg, 64)[0], _wg),
          "  (a source note number, not a depth)")
    _pg.on_midi(mido.Message("note_off", channel=0, note=64, velocity=0))
    _pg.on_midi(mido.Message("note_on", channel=0, note=62, velocity=100))
    _pump(_pg)
    check("...and it is spent: the note after it does not glide",
          _gcols(_pg, 62) is None, "  (a one-shot, not a mode)")
    _pg.shutdown()

    # A VALVED GLISS WALKS THE HARMONICS, in the file renderer. A trumpet does
    # not slide: it runs through real fingerings and blows through the
    # harmonics, so the renderer emits a run of real notes. Offline only --
    # live would have to schedule those note-groups ahead on the audio thread,
    # which nothing here does yet, so live glides a valved voice only as far as
    # the lip reaches and plays anything wider clean. The two paths therefore
    # agree up to two semitones and diverge deliberately past it.
    def _gliss_mid(_prog, _cc5, _a, _b):
        _m = mido.MidiFile(ticks_per_beat=480)
        _t = mido.MidiTrack(); _m.tracks.append(_t)
        _t.append(mido.Message("program_change", channel=0, program=_prog, time=0))
        _t.append(mido.Message("control_change", channel=0, control=5, value=_cc5, time=0))
        _t.append(mido.Message("control_change", channel=0, control=65, value=127, time=0))
        _t.append(mido.Message("note_on", channel=0, note=_a, velocity=100, time=0))
        _t.append(mido.Message("note_off", channel=0, note=_a, velocity=0, time=480))
        _t.append(mido.Message("note_on", channel=0, note=_b, velocity=100, time=0))
        _t.append(mido.Message("note_off", channel=0, note=_b, velocity=0, time=1920))
        _fn = os.path.join(tempfile.gettempdir(), "gliss_%d_%d.mid" % (_prog, _cc5))
        _m.save(_fn)
        return _fn

    def _groups(_prep, _tol_ms=20.0):
        """Partials by STEP, not by exact onset.

        attack_jitter and the section's entry scatter put one note's partials a
        few milliseconds apart, so grouping on the exact sample splits a step
        into pieces with different partial counts -- and comparing their powers
        then compares unequal sets. That mistake reported an 18 dB half-valve
        dip on a TROMBONE while this was being written, which has no valves.
        """
        _nf = np.asarray(_prep["nf"]); _non = np.asarray(_prep["non"])
        _tol = _tol_ms * 44100.0 / 1000.0
        _out = {}
        for _i in range(len(_nf)):
            _t = float(_non[_i])
            _k = next((_k0 for _k0 in _out if abs(_k0 - _t) <= _tol), int(_t))
            _out.setdefault(_k, []).append(_i)
        return _out, _nf, _non

    _gm = _gliss_mid(56, 20, 60, 67)             # trumpet, C4 -> G4, a quick rip
    _gp = _BRb.prepare(_gm, "hybrid440")
    _gg, _gnf, _gnon = _groups(_gp)
    _gts = sorted(_gg)
    _gf = [min(float(_gnf[_i]) for _i in _gg[_t]) for _t in _gts]
    _grun = sorted({round(_f, 2) for _f in _gf})
    check("a valved gliss is a RUN of real pitches, not a sweep",
          len(_grun) >= 8,
          "  (%d distinct pitches from C4 to G4 -- seven fingerings and the "
          "note it arrives at)" % len(_grun))
    # THE STEPS ARE FINGERED, NOT TEMPERED. brass_fingering puts every semitone
    # a few cents off equal, differently, and that wobble is a good part of what
    # makes the gesture sound like a brass player rather than a pitch ramp.
    _gsemi = [1200.0 * math.log(_grun[_i + 1] / _grun[_i], 2.0)
              for _i in range(len(_grun) - 1)]
    _gspread = max(_gsemi) - min(_gsemi)
    check("...and its rungs are FINGERED, not equal-tempered",
          _gspread > 5.0,
          "  (%.1f cents of spread across the run, against 0.0 for a "
          "chromatic scale)" % _gspread)

    # CC5 OPENS THE SMEAR AND DROPS THE LEVEL. A quick gliss is a rip and the
    # steps are the sound of it; a slow one is held, and a player holding a
    # staircase half-valves instead -- which breaks the harmonic alignment and
    # loses support. The dip is the tell.
    _gp2 = _BRb.prepare(_gliss_mid(56, 110, 60, 67), "hybrid440")
    _gg2, _gnf2, _gnon2 = _groups(_gp2)
    _gt1 = float(np.asarray(_gp["gt"])[_gg[_gts[3]][0]])
    _gts2 = sorted(_gg2)
    _gt2 = float(np.asarray(_gp2["gt"])[_gg2[_gts2[3]][0]])
    check("CC5 opens the smear between the rungs", _gt2 > 8.0 * _gt1,
          "  (tau %.4f s at CC5=20 against %.4f at 110 -- clean steps against "
          "a staircase with no flat left on it)" % (_gt1, _gt2))
    _gam = np.asarray(_gp2["aM"])
    _gpow = [float(np.sum(_gam[_gg2[_t]] ** 2)) for _t in _gts2[1:]]
    _gdip = 10.0 * math.log10(min(_gpow) / max(_gpow[0], 1e-12))
    check("...and half-valving loses support through the middle",
          _gdip < -2.0,
          "  (%.1f dB down where the alignment is worst, back up at the "
          "fingering it arrives on)" % _gdip)

    # THE TROMBONE IS THE CONTROL. A real slide, so no lattice and no run: one
    # note with one continuous glide on it.
    _gb = _BRb.prepare(_gliss_mid(57, 20, 60, 67), "hybrid440")
    _ggb, _gnfb, _gnonb = _groups(_gb)
    check("a trombone does not do this, having an actual slide",
          len(_ggb) <= 2,
          "  (%d note-groups against the trumpet's %d: seven positions are a "
          "continuum, seven fingerings are not)" % (len(_ggb), len(_gg)))

    # A VOICE WITH NO MECHANISM REFUSES, exactly as one with no damper refuses
    # CC64. A hammer leaves the string; there is nothing to slide along.
    _pp = Live(program=0, rate=44100, frames=128, verbose=False, tuner="hybrid440")
    _pp.warm()
    _pp.on_midi(mido.Message("control_change", channel=0, control=65, value=127))
    _pp.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
    _pump(_pp)
    _pp.on_midi(mido.Message("note_off", channel=0, note=60, velocity=0))
    _pp.on_midi(mido.Message("note_on", channel=0, note=64, velocity=100))
    _pump(_pp)
    check("a grand piano refuses portamento outright",
          _gcols(_pp, 64) is None, "  (glide_mechanism is None on a struck string)")
    _pp.shutdown()

    # CC67 UNA CORDA is a STRING COUNT, not a filter. The action slides so the
    # hammer strikes two strings of three: quieter and different in colour both
    # fall out of that rather than being fitted. The strings were already
    # separable -- blockrender stamps each unison voice with its own `pl`.
    _ls = Live(program=0, rate=48000, frames=128, verbose=False)
    _ls.warm()

    def _una(_soft, _note):
        _ls.on_midi(mido.Message("control_change", channel=0, control=67,
                                 value=127 if _soft else 0))
        _ls.on_midi(mido.Message("note_on", channel=0, note=_note, velocity=100))
        _ls.apply(0)
        _k = [_x for _x in _ls.slab.live if _x[2] == _note][0]
        _sl = _ls.slab.live[_k]
        _pl = _ls.slab.a["pl"][_sl]
        _am = np.abs(_ls.slab.a["aL"][_sl])
        _r = (sorted({int(v) for v, x in zip(_pl, _am) if x > 0}), float(_am.sum()))
        _ls.on_midi(mido.Message("note_off", channel=0, note=_note, velocity=0))
        _ls.apply(0)
        _ls.slab.release(_k, 0); _ls.slab.reap(10 ** 9)
        return _r
    _d4, _s4 = _una(False, 60), _una(True, 60)
    _d2, _s2 = _una(False, 36), _una(True, 36)
    check("the soft pedal takes a string, and the level follows from that",
          _s4[0] == [0, 1] and _d4[0] == [0, 1, 2]
          and -2.0 < 20 * _math.log10(_s4[1] / _d4[1]) < -0.5,
          "  (C4 loses its third string: %+.2f dB, which is what one string "
          "of three is worth)" % (20 * _math.log10(_s4[1] / _d4[1])))
    # ...AND NOTHING WHERE THERE IS NO THIRD STRING. The index is the
    # instrument's, not the note's: dropping "the highest present" took the
    # SECOND string in the bass, a 0.48 dB divergence from the file renderer.
    check("...and nothing at all in the bass, which has no third string",
          _s2[0] == _d2[0] and abs(_s2[1] - _d2[1]) < 1e-6,
          "  (C2 is a bichord; the action still slides and the hammer still "
          "covers every string there is)")
    check("...and a harpsichord has no una corda to give",
          _T.HarpsiBase.soft_pedal_strings == 0
          and _T.GrandPianoProperties.soft_pedal_strings == 1,
          "  (a quill plucks one string per register, drawn by hand)")
    _ls.shutdown()

    # ---- the bank cache must not evict a voice that is on stage -------------
    # The LRU counted partials and nothing else, so the bank it dropped could
    # be one a Part was holding and sounding through. That was only a rebuild
    # cost until a program change could re-select a voice; now it is a voice
    # rebuilt from cold in the middle of a piece.
    #
    # Sixteen typical GM timbres come to 503,387 partials against a 400,000
    # cap. A rig playing all sixteen keeps all sixteen, because it is playing
    # all sixteen -- the cap governs what nothing is using.
    _PROGS = [0, 11, 19, 24, 30, 33, 40, 48, 56, 61, 66, 73, 80, 89, 105, 118]
    _held = []
    for _i, _p in enumerate(_PROGS):
        _held.append(Part(bank_for(_p, _p == 118, "hybrid"), channel=_i))
        pin_banks({(_q.bank.program, _q.bank.drums, _q.bank.tuner)
                   for _q in _held})
    _res = len(_BANKS)
    _tot = sum(_b.partials for _b in _BANKS.values())
    check("the cache keeps every voice a rig is actually playing",
          _res == 16 and _tot > _BANK_PARTIAL_CAP,
          "  (%d of 16 resident, %d partials -- %.2fx the cap, on purpose)"
          % (_res, _tot, float(_tot) / _BANK_PARTIAL_CAP))
    # ...AND THE BANK JUST ASKED FOR IS NEVER THE ONE DROPPED. It is not
    # pinned yet -- the caller pins it once it holds it -- and it is the most
    # recently used, so without that guard a full cache makes each new arrival
    # evict itself. Measured before the fix: sixteen added one at a time left
    # ELEVEN resident, each throwing away the one before.
    pin_banks(set())
    bank_for(2, False, "hybrid")
    _after = sum(_b.partials for _b in _BANKS.values())
    check("...and still evicts freely once nothing is holding them",
          _after <= _BANK_PARTIAL_CAP
          and (2, False, "hybrid") in _BANKS,
          "  (%d partials, %.2fx the cap, and the newest survived)"
          % (_after, float(_after) / _BANK_PARTIAL_CAP))
    del _held

    # ---- GM2 Scale/Octave Tuning Adjust -------------------------------------
    # Twelve cent offsets per pitch class: the standard, portable way to put a
    # TEMPERAMENT in a MIDI file. Nothing here spoke it, which is why John
    # Sankey's bwv847.mid smuggles his tuning through one-pitch-class-per-
    # channel static pitch bend -- twelve numbers sent through a control meant
    # for a gesture, costing twelve channels, and legible to nothing else.
    _SANKEY = [0.0, -9.77, -7.71, -5.86, -9.77, -1.95,
               -11.72, -3.78, -7.81, -11.72, -3.91, -7.81]
    _m2 = _BRb.sota_message(_SANKEY, two_byte=True)
    _m1 = _BRb.sota_message(_SANKEY, two_byte=False)
    _g2 = _BRb.parse_sota(_m2)
    _g1 = _BRb.parse_sota(_m1)
    _e2 = max(abs(a - b) for a, b in zip(_g2[1], _SANKEY))
    _e1 = max(abs(a - b) for a, b in zip(_g1[1], _SANKEY))
    check("a temperament round-trips through the GM2 tuning sysex",
          _e2 < 0.01 and _e1 < 0.5 and len(_g2[0]) == 16,
          "  (2-byte %.3f cents, 1-byte %.2f -- which is its own 1-cent step)"
          % (_e2, _e1))
    # A message for another machine must be ignored SILENTLY: a Roland GS or
    # Yamaha XG header in a file is not malformed, it is not ours.
    check("...and a sysex for another machine is not mistaken for one",
          _BRb.parse_sota([0x41, 0x10, 0x42, 0x12]) is None
          and _BRb.parse_sota([0x7E, 0x7F, 0x09, 0x01]) is None
          and _BRb.parse_sota([0x7E]) is None,
          "  (GM System On is 7E..09, not 7E..08, and must not match either)")
    # THE CHANNEL BITMAP is three bytes in an order nobody remembers: ff is
    # channels 14-15, gg is 7-13, hh is 0-6.
    _one = _BRb.parse_sota(_BRb.sota_message(_SANKEY, channels=[0, 9, 15]))
    check("...and the three-byte channel map addresses the right channels",
          _one[0] == {0, 9, 15},
          "  (ff = 14-15, gg = 7-13, hh = 0-6)")
    # WHAT IT CANNOT CARRY, stated rather than discovered. Twelve cents per
    # pitch class is a temperament and nothing more: a stretched octave forces
    # every C to one offset, and a dynamic tuner retunes per chord.
    import examples.tuning_sysex as _TS
    _pure = _TS.stretch_of("meantone")
    _str = _TS.stretch_of("stretch")
    check("...and it cannot carry a stretched octave, which the export says",
          _pure < 0.05 < _str,
          "  (meantone varies %.2f cents across the compass and exports "
          "exactly; stretch varies %.2f and cannot)" % (_pure, _str))

    # ---- ...AND LIVE HONOURS IT, by retuning rather than rebuilding ---------
    # Baking a channel's tuning into templates would put a channel in the bank
    # cache key: sixteen times the build cost and sixteen times the memory,
    # against a cap a piano already fills a quarter of. Retune scales `om` on
    # partials that are already sounding, which is what it is for.
    #
    # TWELVE RATIOS, NOT ONE. Everything else per-channel here -- bend, the
    # RPN tunings, the fader -- is a single scalar. This is one per pitch
    # class, so it cannot fold into self.bend and needs its own
    # last-applied bookkeeping, twelve times over.
    _lvs = Live(program=6, rate=48000, frames=128, verbose=False)
    _lvs.warm()
    _SANK = [0.0, -9.77, -7.71, -5.86, -9.77, -1.95,
             -11.72, -3.78, -7.81, -11.72, -3.91, -7.81]
    _lvs.on_midi(mido.Message("sysex", data=_BRb.sota_message(_SANK)))
    _lvs.apply(0)
    _worst = 0.0
    for _n in range(60, 72):
        _lvs.on_midi(mido.Message("note_on", channel=0, note=_n, velocity=100))
        _lvs.apply(0)
        _ks = [_k for _k in _lvs.slab.live if _k[2] == _n]
        _om = np.concatenate([_lvs.slab.a["om"][_lvs.slab.live[_k]] for _k in _ks])
        _nf = np.concatenate([_lvs.slab.a["nf"][_lvs.slab.live[_k]] for _k in _ks])
        _c = 1200 * _math.log2((_om.min() * _lvs.rate / (2 * _math.pi))
                               / float(_nf[_nf > 0].min()))
        _worst = max(_worst, abs(_c - _SANK[_n % 12]))
    check("live takes the same tuning, on a voice that cannot bend",
          _worst < 0.02,
          "  (a harpsichord over twelve pitch classes, worst %.4f cents)"
          % _worst)
    # A REGISTERABLE VOICE STILL TAKES A TUNING. _note_on returns down the
    # organ branch before every per-channel pitch adjustment -- right for the
    # wheel, wrong for a temperament, and the harpsichord is registerable.
    # Measured before the fix: the trumpet moved -9.766 cents and the
    # harpsichord 0.000.
    check("...including down the rank path, which returns before the wheel",
          _lvs.parts[0].organ and _worst < 0.02,
          "  (part.organ is True here; an organ takes no bend and a "
          "harpsichord still takes a temperament)")
    # ...AND A SOUNDING NOTE MOVES, without compounding.
    _lv2 = Live(program=56, rate=48000, frames=128, verbose=False)
    _lv2.warm()
    _lv2.on_midi(mido.Message("note_on", channel=0, note=61, velocity=100))
    _lv2.apply(0)
    _k = [_x for _x in _lv2.slab.live if _x[2] == 61][0]
    _b0 = float(_lv2.slab.a["om"][_lv2.slab.live[_k]].min())
    _lv2.on_midi(mido.Message("sysex", data=_BRb.sota_message(_SANK)))
    _lv2.apply(0)
    _b1 = float(_lv2.slab.a["om"][_lv2.slab.live[_k]].min())
    _lv2.on_midi(mido.Message("sysex", data=_BRb.sota_message(_SANK)))
    _lv2.apply(0)
    _b2 = float(_lv2.slab.a["om"][_lv2.slab.live[_k]].min())
    check("...and a note already sounding is moved onto it, once",
          abs(1200 * _math.log2(_b1 / _b0) - _SANK[1]) < 0.02 and _b2 == _b1,
          "  (%+.3f cents, and the same table twice adds %+.4f)"
          % (1200 * _math.log2(_b1 / _b0), 1200 * _math.log2(_b2 / _b1)))
    # A TUNING SURVIVES CC121 AND NOT A SYSTEM RESET -- it is not a controller.
    _lv2.on_midi(mido.Message("control_change", channel=0, control=121, value=0))
    _lv2.apply(0)
    _kept = _lv2.sota.get(0) is not None
    _lv2.on_midi(mido.Message("sysex", data=[0x7E, 0x7F, 0x09, 0x01]))
    _lv2.apply(128)
    check("...and it survives CC121 but not a GM System On",
          _kept and _lv2.sota.get(0) is None,
          "  (a temperament is a tuning, not a controller)")
    _lvs.shutdown(); _lv2.shutdown()

    # ---- THE PIPER'S SCALE, which is not a temperament ----------------------
    # Nine holes cut once, and every one of them tuned to beat cleanly against
    # a fixed A drone -- which makes the scale just intonation on Low A rather
    # than a compromise between keys. A pipe cannot change key, so it has
    # nothing to compromise for.
    _bp = _eth[109]
    _ratio = {0: 1.0, 2: 9.0 / 8, 4: 5.0 / 4, 5: 4.0 / 3, 7: 3.0 / 2,
              9: 5.0 / 3, 10: 16.0 / 9, 12: 2.0, -2: 8.0 / 9}
    _worst = max(abs(_bp.scale_cents[_k]
                     - 1200.0 * _math.log2(_v)) for _k, _v in _ratio.items())
    check("a chanter's nine holes are just intonation on Low A, not a temperament",
          _bp.scale_tonic_note == 69 and len(_bp.scale_cents) == 9
          and _worst < 0.01,
          "  (worst departure from the pure ratio %.3f cents)" % _worst)
    # THE FLAT SEVENTH IS THE ONE EVERYBODY HEARS: 16/9 is 996 cents, four
    # under equal, and there is no leading tone anywhere on the instrument --
    # which is why a song has to be adapted rather than transposed to play it.
    check("...with a flat seventh and a flat third, where equal has neither",
          abs(_bp.scale_cents[10] - 996.09) < 0.01
          and abs(_bp.scale_cents[4] - 386.31) < 0.01,
          "  (High G %.0f cents against equal's 1000, C# %.0f against 400)"
          % (_bp.scale_cents[10], _bp.scale_cents[4]))
    # AND THE DRONES ARE TUNED TO THE CHANTER, which is what a piper does by
    # ear before playing. They were absolute Hz -- right at A=440 and a hundred
    # cents out at `hybrid`'s A=415, against the one note they reinforce.
    _by_tuner = {}
    for _tn in ("hybrid440", "hybrid"):
        _l = Live(program=109, rate=48000, frames=128, tuner=_tn, verbose=False)
        _l.warm()
        _by_tuner[_tn] = (_l._tonic_hz(_l.parts[0]),
                          sorted(_l._tonic_hz(_l.parts[0]) * _r
                                 for _r in _l.parts[0].bank.drone_ratios))
        _l.renderer.close()
    _a4, _d4 = _by_tuner["hybrid440"]
    _a1, _d1 = _by_tuner["hybrid"]
    check("...and the drones are tuned to the chanter, not to a fork",
          abs(_a4 - 440.0) < 0.01 and abs(_a1 - 415.0) < 0.01
          and all(abs(1200 * _math.log2(_x / _y) + 101.27) < 0.5
                  for _x, _y in zip(_d1, _d4)),
          "  (Low A %.0f and %.0f Hz; the drones follow it, %.0f cents down)"
          % (_a4, _a1, 1200 * _math.log2(_d1[0] / _d4[0])))
    check("...and they are RATIOS now, so nothing is nailed to 440",
          not hasattr(_T.SynthProperties, "drone_ratios")
          and abs(_bp.drone_ratios[0] - 0.5) < 1e-12
          and abs(_bp.drone_ratios[2] - 0.25) < 1e-12,
          "  (two tenors an octave under Low A, a bass two octaves under)")

    def _live_level(_lv, _ch=0, note=60, vel=100, cc7=None, cc11=None):
        for _c, _v in ((7, cc7), (11, cc11)):
            if _v is not None:
                _lv.on_midi(mido.Message("control_change", channel=_ch,
                                         control=_c, value=_v))
        _lv.on_midi(mido.Message("note_on", channel=_ch, note=note, velocity=vel))
        _lv.apply(0)
        _ks = [_k for _k in _lv.slab.live if _k[2] == note]
        _v = sum(float(np.abs(_lv.slab.a["aL"][_lv.slab.live[_k]]).sum())
                 for _k in _ks)
        _lv.on_midi(mido.Message("note_off", channel=_ch, note=note, velocity=0))
        _lv.apply(0)
        for _k in _ks:
            _lv.slab.release(_k, 0)
        _lv.slab.reap(10 ** 9)
        return _v

    # THE CLASS FLAG WAS HONOURED IN THE PARTIALS AND THROWN AWAY AGAIN. Every
    # bucket of a fixed-volume voice comes out identical -- and then _note_on
    # trimmed what it stamped by (vel/bucket_vel)^2 whatever the voice was. The
    # harpsichord escaped only because it is `registerable` and returns down the
    # organ branch before that line; the accordions and the bagpipe did not, and
    # measured +24.1 dB from velocity 30 to 120 on a patch whose own class says
    # velocity does nothing. Checked through the BANK, which is the path that
    # broke, exactly as the earlier bucket version of this bug was.
    _touchless = []
    for _g, _lab in ((109, "bagpipe"), (21, "accordion"), (23, "tango accordion"),
                     (20, "reed organ"), (6, "harpsichord")):
        _l = Live(program=_g, rate=48000, frames=128, verbose=False); _l.warm()
        _db = 20.0 * _math.log10(max(_live_level(_l, vel=120), 1e-12)
                                 / max(_live_level(_l, vel=30), 1e-12))
        if abs(_db) > 0.01:
            _touchless.append("%s %+.1f dB" % (_lab, _db))
        _l.renderer.close()
    check("...and live honours that, which it did not for anything but the organs",
          not _touchless,
          "  (five fixed-volume voices, velocity 30 to 120, all flat)"
          if not _touchless else "  (still touch-sensitive: %s)"
          % ", ".join(_touchless))
    # ...AND CHANNEL VOLUME HAD TO EXIST FOR THAT TO BE PLAYABLE. Live
    # implemented CC1, CC64 and CC123 and nothing else, so with velocity
    # correctly doing nothing a bagpipe had no dynamic range at all. CC7 and
    # CC11 now carry blockrender's own law, (v7*v11)^2 at line 840.
    _lv7 = Live(program=109, rate=48000, frames=128, verbose=False); _lv7.warm()
    _f = _live_level(_lv7, cc7=127, cc11=127)
    _g7 = 20.0 * _math.log10(_live_level(_lv7, cc7=40, cc11=127) / _f)
    _g11 = 20.0 * _math.log10(_live_level(_lv7, cc7=127, cc11=40) / _f)
    _want = 20.0 * _math.log10((40 / 127.0) ** 2)
    check("...so CC7 and CC11 exist now, on the file path's own law",
          abs(_g7 - _want) < 0.05 and abs(_g11 - _want) < 0.05,
          "  (CC 40 gives %+.1f and %+.1f dB against (40/127)^2 = %+.1f)"
          % (_g7, _g11, _want))
    # AND A SWELL REACHES A NOTE ALREADY SOUNDING, which is the one place live
    # goes further than the file path: offline an amplitude is fixed when the
    # partials are emitted, so CC11 is read once at note-on. On an organ or a
    # bagpipe that pedal IS the expression, and here there is a foot on it.
    _lv7.on_midi(mido.Message("control_change", channel=0, control=7, value=127))
    _lv7.on_midi(mido.Message("control_change", channel=0, control=11, value=127))
    _lv7.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
    _lv7.apply(0)
    _k60 = [_k for _k in _lv7.slab.live if _k[2] == 60][0]
    _sum = lambda: float(np.abs(_lv7.slab.a["aL"][_lv7.slab.live[_k60]]).sum())
    _a0 = _sum()
    _lv7.on_midi(mido.Message("control_change", channel=0, control=11, value=64))
    _lv7.apply(0)
    _a1 = _sum()
    _lv7.on_midi(mido.Message("control_change", channel=0, control=11, value=64))
    _lv7.apply(0)
    _a2 = _sum()
    # ...AND ON EVERY VOICE, WHICH IT DID NOT. A Leslie, a tremolo and a
    # clavinet's rockers each capture their own copy of the amplitude and then
    # ASSIGN a["aL"] from it every block, so a fader that scaled only aL0 was
    # erased within one block on exactly the voices with a panel effect.
    # Measured on program 16 before the fix: CC11 127 -> 32 landed at -23.9 dB
    # and one callback later read +0.1.
    #
    # LIKE FOR LIKE, which is the whole trick of this check: a tremolo is a
    # time-varying gain, so the Rhodes really does move 4.08 dB over one block
    # whatever the fader is doing. Comparing a swung note against an unswung
    # one reads that as a 4 dB error. Both sides are therefore measured after
    # the SAME number of blocks.
    _fade = []
    for _g, _lab, _arm in ((4, "Rhodes", True), (16, "Hammond", False),
                           (7, "clavinet", True), (109, "bagpipe", False)):
        _lv2 = []
        for _cc in (127, 32):
            _l = Live(program=_g, rate=48000, frames=128, verbose=False); _l.warm()
            if _arm:
                _l.on_midi(mido.Message("control_change", channel=0,
                                        control=1, value=127))
            _l.on_midi(mido.Message("control_change", channel=0,
                                    control=11, value=_cc))
            _l.on_midi(mido.Message("note_on", channel=0, note=60, velocity=100))
            _l.apply(0)
            _l.callback(None, 128, None, 0)
            _ks = [_k for _k in _l.slab.live if _k[2] == 60]
            _lv2.append(sum(float(np.abs(_l.slab.a["aL"][_l.slab.live[_k]]).sum())
                            for _k in _ks))
            _l.renderer.close()
        _fade.append((_lab, 20 * _math.log10(max(_lv2[1], 1e-30)
                                             / max(_lv2[0], 1e-30))))
    _want = 20 * _math.log10((32 / 127.0) ** 2)
    check("...and it survives a block on voices with a panel effect",
          all(abs(_d - _want) < 0.2 for _l, _d in _fade),
          "  (" + ", ".join("%s %+.1f" % _t for _t in _fade)
          + " dB against %+.1f)" % _want)

    check("...and the swell reaches a note already sounding, without compounding",
          abs(20 * _math.log10(_a1 / _a0)
              - 20 * _math.log10((64 / 127.0) ** 2)) < 0.05
          and abs(_a2 - _a1) < 1e-6,
          "  (%+.1f dB under a held note, and the same message twice adds %+.2f)"
          % (20 * _math.log10(_a1 / _a0), 20 * _math.log10(_a2 / _a1)))
    _lv7.renderer.close()
    # A DRONE SPANS THE PHRASE, LIVE TOO, and live has no far side of the rest
    # to look at -- so part_break_s is spent as a HOLD instead. The drones stay
    # up through a gap between notes and are let down only once the piper has
    # plainly stopped.
    lvbp.on_midi(mido.Message("note_off", channel=0, note=74, velocity=0))
    lvbp.apply(0)
    _held = len(_bp_drones())
    lvbp._drone_reap(int(0.5 * lvbp.rate))
    _short = len(_bp_drones())
    lvbp._drone_reap(int(3.0 * lvbp.rate))
    lvbp.slab.reap(int(3.0 * lvbp.rate) + 4 * lvbp.rate)
    _long = len(_bp_drones())
    check("...and the bag stays up through a rest, and is let down after one",
          _held == 3 and _short == 3 and _long == 0,
          "  (3 drones at note-off, 3 still at 0.5 s, none at %.0f s)"
          % _bpb.part_break_s)
    lvbp.renderer.close()
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
