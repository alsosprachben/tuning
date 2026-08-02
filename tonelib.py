#!/usr/bin/env python

"""
Copyright Ben Woolley 2010.
All rights reserved.
"""

import os
import random as _random
from math import exp as _exp, log as _log, sin as _sin, pi as _pi
verbose = os.environ.get("TUNING_VERBOSE", "") not in ("", "0")

# Spatialization uses the Brown-Duda spherical-head model by default:
# per-ear Woodworth delays and a per-partial, frequency-dependent
# head-shadow gain, both derived from the modeled source position.
# Set TUNING_HRTF=0 to restore the legacy amplitude pan law.
hrtf = os.environ.get("TUNING_HRTF", "1") not in ("", "0")


def errlog(s):
    import sys
    if verbose:
        sys.stderr.write(str(s) + "\n")
        sys.stderr.flush()


has_clipped = False
clipping = False
max_v = 1.0

rand_granularity = 100000


def init_rand():
    import random
    global entropy
    entropy = [random.random() for i in range(rand_granularity)]


init_rand()


def rand(second):
    return entropy[int(second * rand_granularity) % rand_granularity]


def clipped(v):
    v = abs(v)
    global max_v, clipping, has_clipped
    if v > max_v:
        max_v = v
        clipping = True
    elif clipping:
        clipping = False
        errlog("New peak: " + str(max_v) + ", " + str(1.0 / max_v))

    if not has_clipped:
        has_clipped = True
        errlog("Clipped!!!\n")


class Second:
    def __init__(self, second=0.0):
        self.second = float(second)

    def set(self, second):
        self.second = float(second)

    def get(self):
        return self.second


def db_ratio(db):
    return 10 ** (float(db) / 10)


# The per-sample decay/bloom envelope is rate**(-t) == exp(-t * ln(rate)). With
# ln(rate) precomputed (see Decay), a direct exp() is both exact/continuous and
# faster than pow (pow recomputes the log every call) -- and ~5x faster than a
# Python lookup table, whose interpreter overhead dwarfs the C exp.


# Master output gain (amplitude), applied to the summed per-channel signal
# just before clipping. Per-voice gains are tuned on 1-3 voice material, so
# an 8-voice tutti sums well past full scale and clips; this gives global
# headroom without disturbing the relative balance. Override in amplitude dB
# with TUNING_MASTER_DB (0 = unity, -12 = quarter amplitude).
master_gain = 10.0 ** (float(os.environ.get("TUNING_MASTER_DB", "-9.3")) / 20.0)


class Decay:

    def __init__(self, dbps, start_second, sustain_level=0.0,
                 aftersound_level=0.0, aftersound_dbps=None):
        self.start_second = start_second
        self.dbps = dbps
        self.rate = db_ratio(dbps)
        # Floor the decay approaches instead of zero: 0 = die away (plucked,
        # struck), >0 = bloom to the attack peak then settle to this fraction
        # and hold (the brass "front"; a sustaining voice with decay_db > 0).
        self.sustain_level = sustain_level
        # Two-stage (piano) decay: a fraction `aftersound_level` of the energy
        # decays at the slower `aftersound_dbps` rate. This is the coupled-string
        # tail that rings on after the bright prompt sheds -- modelled as an
        # ENVELOPE, not detuned voices (equal detuned voices beat to a null and
        # swell back, which sounds like a slow crescendo). 0 = plain single decay.
        self.aftersound_level = aftersound_level
        self.aftersound_rate = db_ratio(aftersound_dbps) if aftersound_dbps is not None else self.rate
        # Precompute ln(rate) so the per-sample envelope is neg_exp(t*ln rate)
        # (== rate**-t) -- a table index rather than a pow every sample.
        self.log_rate = _log(self.rate)
        self.log_aftersound_rate = _log(self.aftersound_rate)
        self.sample_decay = None
        self.sample_volume = 0.0

    def decay(self, second, last_second=None):
        if last_second:
            if self.sample_decay:
                self.sample_volume *= self.sample_decay
                return self.sample_volume
            else:
                self.sample_volume = self.decay(second)
                self.sample_decay = self.decay(second) / self.decay(last_second)
                return self.sample_volume
        else:
            t = second - self.start_second.get()
            if self.aftersound_level > 0.0:
                base = ((1.0 - self.aftersound_level) * _exp(-t * self.log_rate)
                        + self.aftersound_level * _exp(-t * self.log_aftersound_rate))
            else:
                base = _exp(-t * self.log_rate)
            return self.sustain_level + (1.0 - self.sustain_level) * base


class Fade:
    def __init__(self, start_second=None, end_second=None):
        self.start_second = start_second
        self.end_second = end_second or Second()

    def set_duration(self, second):
        self.end_second.set(self.start_second.get() + second)

    def fade_in(self, second):
        if self.start_second is None:
            return 1.0
        else:
            start = self.start_second.get()
            end = self.end_second.get()
            if second >= end:
                return 1.0
            elif second <= start:
                return 0.0
            else:
                t = (second - start) / (end - start)
                # Smoothstep: zero slope at both ends, so the onset has no corner
                # (a linear ramp's derivative jump is itself an audible click).
                return t * t * (3.0 - 2.0 * t)

    def fade_out(self, second):
        if self.start_second is None:
            return 1.0
        else:
            start = self.start_second.get()
            end = self.end_second.get()
            if second >= end:
                return 0.0
            elif second <= start:
                return 1.0
            else:
                t = (second - start) / (end - start)
                return 1.0 - t * t * (3.0 - 2.0 * t)


class BasePartial:
    # public

    # Upper bound on the attack/release fade in seconds, set per note from
    # its duration so a fade can't outlast a short note. None = no cap.
    max_fade = None


    # Detune of this partial from the exact harmonic, in Hz. Nonzero for the
    # extra unison voices of a chorus/ensemble so they beat against the main.
    frequency_offset = 0.0

    # Fractional (ratio) detune of the whole voice -- a real mistuned string is
    # off by a constant ratio, so partial n is offset by ~n x the fundamental's
    # Hz. This is what makes the upper partials of a piano's 2-3 strings beat
    # progressively faster and "dance", where a fixed-Hz offset would beat every
    # harmonic at the same rate. 0.0 = on pitch.
    detune_ratio = 0.0

    def frequency(self, second):
        "stub input"

        return 0

    def value(self, second, nyquist):
        "result output"

        frequency = self.frequency(second)
        return self.wave(second, frequency, self.volume(second, frequency, nyquist))

    class Releasing:
        pass

    class Attacking:
        pass

    class Reattacking:
        pass

    class Lifted:
        pass

    class Pressed:
        pass

    def __init__(self, properties, intensity=1.0, decay_rate=0.0, delay=0.0, release_floor_db=None):
        from collections import deque
        # public state
        self.properties = properties
        self.ref_count = 0
        self.pending_attack = False
        self.pending_release = False
        self.delay = delay
        self.state = self.Lifted

        self.decay_rate = decay_rate
        self.sustain = None
        self.attack_fade = None
        self.release_fade = None
        self.hit_floor = False

        # static properties
        self.intensity = intensity
        if not release_floor_db:
            # A one-shot voice (percussion) needs an audible floor so it
            # actually finishes and gets cleaned up as its decay rings out;
            # sustained voices use a very deep floor.
            release_floor_db = getattr(properties, "release_floor_db", None)
        if not release_floor_db:
            from math import log
            depth = 16
            release_floor_db = -(log(2 ** (2 * depth)) / log(10)) * 10
        self.floor = db_ratio(release_floor_db)

        # private state
        self.last_cycle = 0.0
        self.last_second = 0.0

    # private

    def finished(self):
        # A one-shot voice is never released; it retires when its decay rings
        # down past the floor (hit_floor is set in wave()).
        return (self.state is self.Lifted and not self.pending_attack) or self.hit_floor

    def lift(self):
        errlog("lift %s %s %i - 1" % (id(self), self.state, self.ref_count))
        self.pending_release = True
        self.ref_count -= 1

    def unlift(self):
        errlog("unlift %s %s %i + 1" % (id(self), self.state, self.ref_count))
        self.pending_attack = True
        self.ref_count += 1

    def actuate(self, frequency, second):
        has_attack = self.pending_attack
        self.pending_attack = False
        has_release = self.pending_release
        self.pending_release = False

        if self.ref_count > 0:
            if has_attack:
                if self.state is self.Lifted:
                    self.hammer_down(frequency, second)
                elif self.state is self.Pressed:
                    self.hammer_up(frequency, second)
                    self.state = self.Reattacking
                elif self.state is self.Releasing:
                    self.state = self.Reattacking
                # else is already attacking
            else:
                if self.state is self.Lifted:
                    # should at least be attacked
                    self.hammer_down(frequency, second)
                # else let hammer actions continue

        elif self.ref_count <= 0:
            if has_release:
                if self.state is self.Pressed:
                    self.hammer_up(frequency, second)
                elif self.state is self.Reattacking:
                    self.state = self.Releasing
                # self.Lifted and self.Releasing are already releasing or released
            else:
                if self.state is self.Pressed:
                    # should at least be released
                    self.hammer_up(frequency, second)
                # else let hammer actions continue

    def hammer_up(self, frequency, second):
        self.state = self.Releasing
        errlog("hammer_up %s %s %s %s" % (frequency, second, id(self), self.state))

        # A cymbal splashes fast but rings out slowly; release_valve_time lets
        # the note-off fade differ from the attack fade. Defaults to the same
        # valve fade as the attack when unset.
        release_time = self.properties.release_valve_time
        if release_time is None:
            fade_time = self.properties.chiff_min_valve_time + (
                        self.properties.chiff_max_valve_time - self.properties.chiff_min_valve_time) * 1.0
        else:
            fade_time = release_time

        if self.max_fade is not None:
            # Short note: cap the onset transient so it fits, or a slow
            # valve/breath fade would smear fast notes (trills, tonguing).
            fade_time = min(fade_time, self.max_fade)

        self.release_fade = Fade(Second(second + self.delay), Second(second + self.delay + fade_time))

    def hammer_down(self, frequency, second):
        self.state = self.Attacking
        errlog("hammer_down %s %s %s %s" % (frequency, second, id(self), self.state))

        # Per-note timing jitter: delay the whole strike (phase + envelope) by a
        # small amount so doubled voices don't attack in lockstep. Shared across
        # the note's partials (same properties), so the note stays coherent.
        second = second + self.properties.attack_jitter

        # Reset the phase accumulator at the strike so the partial starts at
        # phase 0 here, regardless of when it was created. Without this a note
        # attacking at t>0 has last_second=0, so its first cycle() jumps to
        # second*frequency -- a different offset per partial -- leaving the
        # struck strings (and same-frequency string-group voices) incoherent and
        # cancelling. A real strike excites all modes in phase; so must we.
        self.last_cycle = 0.0
        self.last_second = second

        if self.properties.attack_time is not None:
            fade_time = self.properties.attack_time
        else:
            fade_time = self.properties.chiff_min_valve_time + (
                        self.properties.chiff_max_valve_time - self.properties.chiff_min_valve_time) * 1.0

        if self.max_fade is not None:
            fade_time = min(fade_time, self.max_fade)

        self.attack_fade = Fade(Second(second + self.delay), Second(second + self.delay + fade_time))
        # base_frequency is the note fundamental (harmonic 1); use it, not this
        # partial's harmonic frequency, to pick the string count / aftersound.
        aftersound_level, aftersound_dbps = self.properties.aftersound(
            getattr(self, "base_frequency", frequency), self.decay_rate)
        self.sustain = Decay(self.decay_rate, Second(second + self.delay),
                             self.properties.sustain_level, aftersound_level, aftersound_dbps)

    def force(self, frequency, second):
        self.actuate(frequency, second)

        if self.state is self.Lifted:
            self.last_cycle = 0
            self.last_second = second
            return 0.0
        elif self.state is self.Pressed:
            return 1.0
        elif self.state is self.Attacking:
            return self.attack(frequency, second)
        elif self.state is self.Releasing:
            return self.release(frequency, second)
        elif self.state is self.Reattacking:
            return self.release(frequency, second)

    def attack(self, frequency, second):
        v = self.attack_fade.fade_in(second)
        if v == 1.0:
            # errlog(self.state)
            self.state = self.Pressed
            errlog("pressed %s %s %s %s" % (frequency, second, id(self), self.state))
            if self.ref_count <= 0:
                errlog("!!!! PANIC ref_count, trying to recover by lifting the hammer.")
                # attack overlapped deref... bring up the hammer
                self.hammer_up(frequency, second)
        return v

    def release(self, frequency, second):
        v = self.release_fade.fade_out(second)
        if v == 0.0:
            # errlog(self.state)
            if self.state is self.Reattacking:
                self.hammer_down(frequency, second)
                errlog("reattacking %s %s %s %s" % (frequency, second, id(self), self.state))
            else:
                self.state = self.Lifted
                errlog("lifted %s %s %s %s" % (frequency, second, id(self), self.state))
                self.last_cycle = 0
                self.last_second = second
        return v

    def cycle(self, second, frequency):
        cycle = self.last_cycle + (second - self.last_second) * frequency
        self.last_cycle = cycle
        self.last_second = second
        return cycle

    def wave(self, second, frequency, volume):
        from math import sin, pi

        if volume <= self.floor:
            # Latch hit_floor (used by one-shot voices to know they have rung
            # out) only once past the onset: during Attacking/Reattacking the
            # volume ramps up through zero, which must not read as "decayed".
            if (not self.hit_floor
                    and self.state is not self.Attacking
                    and self.state is not self.Reattacking):
                errlog("Dropping partial that hit the floor.")
                self.hit_floor = True
            return 0.0

        if self.properties.chiff_volume > 0.0:
            if self.state is self.Attacking:
                jitter_fade = self.attack_fade.fade_in(second)  # * self.attack_fade.fade_out(second)
                jitter_fade = jitter_fade ** 0.5
                jitter_fade *= (1.0 - jitter_fade)
            elif self.state is self.Releasing:
                jitter_fade = self.release_fade.fade_in(second)  # * self.release_fade.fade_out(second)
                jitter_fade = jitter_fade ** 0.5
                jitter_fade *= (1.0 - jitter_fade)
                # scale release noise separately; brass valves do not hiss on note-off
                jitter_fade *= self.properties.chiff_release
            else:
                # Held note: a small steady phase jitter broadens each partial
                # into a band, the width of a section of slightly out-of-phase
                # strings -- a sustained chiff, no beating or amplitude wobble.
                jitter_fade = self.properties.sustain_jitter

            if jitter_fade > 0:
                cycle_jitter = rand(second * frequency) * self.properties.chiff_cycle

                jitter = sin(pi * 2 * (self.cycle(second,
                                                  frequency) + cycle_jitter)) * jitter_fade * self.properties.chiff_volume * self.base_frequency / 440
            else:
                jitter = 0.0
        else:
            jitter = 0.0

        return (jitter + sin(pi * 2 * self.cycle(second, frequency))) * volume

    def volume(self, second, frequency, nyquist):
        if frequency <= nyquist:
            return self.intensity * self.force(frequency, second) * (
                self.sustain.decay(second) if self.sustain is not None else 1.0)
        else:
            return 0.0


class BaseTone:
    def sum_values(self, second, nyquist):
        v = sum(p.value(second, nyquist) for p in self.partials)
        if v > 1.0:
            clipped(v)
            v = 1.0

        if v < -1.0:
            clipped(v)
            v = -1.0

        return v


class BaseSampler:
    def __init__(self, sample_rate=48000, sample_depth=16, sample_packing="h"):
        from struct import Struct
        self.rate = sample_rate
        self.depth = sample_depth
        self.packing = Struct(sample_packing)

        self.nyquist = self.rate / 2
        self.cardinality = 1 << self.depth
        self.bytes = self.depth / 8

    def signed_sample(self, i):
        return int(((self.sum_values(float(i) / self.rate, self.nyquist) + 1) / 2 * (self.cardinality - 1) - (
                    self.cardinality / 2)) + .5)

    def sample(self, i):
        return self.packing.pack(self.signed_sample(i))


class SimplePartial(BasePartial):
    def __init__(self, properties, f, h, v=1.0, db=0.0, delay=0.0, ref_count=0):
        if db > 30: db = 30
        # errlog(db)
        BasePartial.__init__(self, properties, v, db, delay)
        self.base_frequency = f
        self.harmonic = h
        # Inharmonic stretch: a real string's nth partial sits sharp of n*f0 by
        # sqrt-of-stiffness, here f0*n*(1 + 0.5*(n^2-1)*B). B is fixed for the
        # note (properties.inharmonicity_coefficient is set per note-frequency in
        # init_partials before the partials are built), so precompute the factor
        # once rather than per sample. B == 0 (air columns) -> 1.0, pure harmonic.
        B = properties.inharmonicity_coefficient
        self.inharmonic_stretch = (1.0 + 0.5 * (h * h - 1) * B) if B > 0.0 else 1.0
        if ref_count > 0:
            for i in range(ref_count):
                self.unlift()

        if ref_count < 0:
            for i in range(-ref_count):
                self.lift()

    def updateBaseFrequency(self, f):
        self.base_frequency = f

    def updatePan(self, p):
        self.pan = p

    def frequency(self, second):
        # Detune is stored on the partial (per unison voice), not on the
        # shared properties; reading properties here silently disabled every
        # chorus, so unison voices piled up at the same pitch with no beating.
        # inharmonic_stretch pushes upper partials sharp (piano/plucked/mallet);
        # it is 1.0 for the air-column instruments, leaving them pure-harmonic.
        # detune_ratio mistunes the whole string by a constant ratio (the dance);
        # pitch_jitter is a per-note micro-detune (shared by all partials) so two
        # voices on the same pitch beat naturally instead of locking.
        f = (self.base_frequency * (1.0 + self.properties.pitch_jitter) * (1.0 + self.detune_ratio)
             * self.harmonic * self.inharmonic_stretch + self.frequency_offset)
        # Tension modulation: a struck string starts sharp (large displacement =
        # more tension) and settles down to the tuned pitch. Modelled as an ATTACK
        # TRANSIENT (fast exponential from the strike), not the slow amplitude
        # decay -- so the sustained portion, which the tuning is matched against,
        # rings at the tuned base_frequency rather than perpetually sharp.
        tb = self.properties.tension_bend
        if tb and self.sustain is not None:
            t = second - self.sustain.start_second.get()
            if 0.0 <= t < self.properties.tension_settle_cutoff:
                env = _exp(-t / self.properties.tension_settle_time)
                f *= 1.0 + tb * self.properties.attack_volume * env
        return f


class SquareWave(SimplePartial):
    def wave(self, second, frequency, volume):
        from math import floor
        if volume > 0.0:
            t = self.cycle(second, frequency)
            on = int(t * 2) % 2 == 0
            return volume if on else -volume
        else:
            self.cycle(second, frequency)
            return 0.0


class TriangleWave(SimplePartial):
    def wave(self, second, frequency, volume):
        from math import floor
        if volume > 0.0:
            # not yet implemented -- still a square wave
            t = self.cycle(second, frequency)
            on = int(t * 2) % 2 == 0
            return volume if on else -volume
        else:
            self.cycle(second, frequency)
            return 0.0


class SawtoothWave(SimplePartial):
    def wave(self, second, frequency, volume):
        from math import floor
        if volume > 0.0:
            t = self.cycle(second, frequency)
            return 2.0 * (t - floor(t + 0.5)) * volume
        else:
            self.cycle(second, frequency)
            return 0.0


class SynthProperties:
    from inharmonicity import inharmonicity_coefficient_2nd_harmonic, inharmonicity_coefficient_3rd_harmonic

    # Strike/pluck point as a fraction of the speaking length. When set, mode n is
    # excited with amplitude |sin(n*pi*strike_point)| -- a comb that nulls the
    # harmonics at multiples of 1/strike_point. None = no comb (uses the legacy
    # plucked_volumes path; pipes etc.). The piano sets ~1/7 to soften the 7th.
    strike_point = None
    strike_depth = 1.0    # how deep the strike comb notches (1=point-strike null, 0=off); the
                          # finite hammer width fills it in, so real pianos want it shallow.

    # Chorus/ensemble: extra unison voices detuned by these Hz offsets, each
    # scaled by unison_gain. Empty = a single voice (no beating).
    unison_detune = ()
    unison_gain = 1.0

    # Amplitude-dependent pitch drift (string tension modulation). 0 = off; the
    # piano sets it so a note blooms sharp on the strike and settles as it decays.
    # Register-scaled in __init__: tension_bend is the value at tension_bend_ref_hz
    # and grows toward the bass as (ref/f0) ** tension_bend_slope. The bloom is an
    # ATTACK TRANSIENT (settle_time), decaying to the tuned pitch well within the
    # sustained portion -- a tuner matches the sustain, so that must land on pitch.
    tension_bend = 0.0
    tension_bend_ref_hz = 262.0
    tension_bend_slope = 1.0
    tension_settle_time = 0.28   # s: transient decays to the tuned pitch this fast
    tension_settle_cutoff = 1.8  # s: past this the bloom is spent; skip the math

    # Per-note natural jitter (0 = off). Now that every strike is phase-coherent,
    # two voices on the same pitch would align TOO perfectly (a machine-gun,
    # electronic doubling). Real doublings sit at slightly different pitches (so
    # they BEAT -- a living shimmer, never a persistent cancellation) and strike
    # a hair apart. A random-but-fixed value is drawn PER NOTE in __init__ and
    # shared by all its partials, so the note stays internally coherent (the
    # phase fix is preserved) while different notes decorrelate.
    pitch_jitter_cents = 0.0     # +/- this many cents, random per note (the beat)
    timing_jitter_seconds = 0.0  # 0..this delay to the strike, random per note (stagger)

    # Onset ramp in seconds. None = derive it from the chiff/valve time (winds).
    # A struck string otherwise gets a 0-length ramp -> the amplitude steps 0->full
    # in one sample, and with every partial phase-aligned at the strike that step
    # is a bandlimited impulse: a digital click. A few ms of smoothstep ramp
    # attenuates the first (loudest) impulse cycle and bandlimits the onset.
    attack_time = None

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        """Extra detuned voices for this harmonic, as (gain_multiplier,
        detune_Hz, detune_ratio, decay_rate_dbps). Default: one voice per
        unison_detune offset, a fixed-Hz chorus at unison_gain and the same
        decay -- fine for a bowed section. The piano overrides this with
        ratio-detuned string groups (the dance)."""
        return [(self.unison_gain, offset, 0.0, harmonic_decay)
                for offset in self.unison_detune]

    def aftersound(self, frequency, decay_rate):
        """Two-stage decay parameters (slow-tail energy fraction, slow rate in
        dbps) for a note at this fundamental. Default: none -- a single
        exponential decay. The piano overrides this with its string count."""
        return (0.0, decay_rate)

    # Sustained phase jitter on a held note (fraction of the chiff amount that
    # keeps running during the Pressed state). Broadens each partial into a
    # band -- a section-of-strings shimmer from one voice. 0 = clean/static.
    sustain_jitter = 0.0

    # Amplitude-envelope sustain floor, with decay_db > 0: the note blooms to
    # the attack peak then settles to this fraction and holds -- the brass
    # "front". 0 (default) = the decay dies away, as for plucked/struck.
    sustain_level = 0.0

    # Note-off fade time in seconds, decoupled from the attack fade so a
    # cymbal can splash fast yet ring out slowly. None = match the attack.
    release_valve_time = None

    # One-shot voice: note-off is ignored; the strike rings out on its own
    # exponential decay (struck percussion). Needs release_floor_db so it
    # retires in finite time instead of decaying toward a 192 dB floor.
    one_shot = False
    release_floor_db = None

    # Metres of stereo spread per octave of pitch (times position_x). Positive =
    # higher notes toward one side; the piano flips the sign so its keyboard reads
    # low-left to high-right (a player's view). Class attribute so it can be set
    # per instrument.
    octave_width = 0.165

    # Decay rate scaling per octave (times harmonic_decay). 0 = register-flat; the
    # piano sets it > 0 so the bass rings long and the treble decays fast.
    decay_register_slope = 0.0

    def __init__(self, frequency=256.0, channel_pan=0.0, attack_volume=1.0, channel_volume=1.0):
        self.channel_pan = channel_pan
        self.attack_volume = attack_volume
        self.channel_volume = channel_volume

        self.frequency_x = 415.0

        from math import log
        self.octave_position = (log(float(frequency) / self.frequency_x) / log(2))

        # Register-dependent decay rate: < 1 slows the bass, > 1 speeds the treble
        # (heavy vs light, lightly- vs heavily-damped strings). 0 slope = flat.
        self.decay_register_factor = 2.0 ** (self.decay_register_slope * self.octave_position)

        # Per-note jitter, drawn once here (shared by all the note's partials).
        self.pitch_jitter = (2.0 ** (_random.uniform(-self.pitch_jitter_cents, self.pitch_jitter_cents) / 1200.0) - 1.0
                             ) if self.pitch_jitter_cents else 0.0
        self.attack_jitter = _random.uniform(0.0, self.timing_jitter_seconds) if self.timing_jitter_seconds else 0.0

        # Register-scale the tension pitch-drift: bass strings displace far more
        # for a given strike, so they bloom much sharper than the treble. Grows
        # toward low f0 (tension_bend is the value at tension_bend_ref_hz); capped
        # so an extreme-bass fff can't bend absurdly.
        if self.tension_bend > 0.0:
            self.tension_bend = min(0.04, self.tension_bend
                * (self.tension_bend_ref_hz / float(frequency)) ** self.tension_bend_slope)

        if self.inharmonicity_dynamic:
            self.inharmonicity_coefficient *= (1.0 + abs(self.octave_position))

        if self.octave_modulo:
            from math import floor
            self.attack_dampening = self.tonal_dampening + floor(self.octave_position) * self.octave_dampening
        else:
            self.attack_dampening = self.tonal_dampening + self.octave_position * self.octave_dampening

        # attack_volume = per-note velocity gain, channel_volume = CC7*CC11
        # channel gain, both already squared to the MIDI (V/127)^2 law.
        self.gain = (self.initial_gain * db_ratio(self.octave_gain * self.octave_position)
                     * self.attack_volume * self.channel_volume)

        self.position_x = self.octave_position * self.octave_width + self.channel_pan * 4  # meters
        self.position_y = 0.2  # meters

        self.ear_distance = 0.02  # meters

        self.sound_speed = 343.174  # meters per second

        self.left_distance = ((self.position_x - self.ear_distance / 2) ** 2 + self.position_y ** 2)
        self.right_distance = ((self.position_x + self.ear_distance / 2) ** 2 + self.position_y ** 2)

        self.left_delay = self.left_distance / self.sound_speed
        self.right_delay = self.right_distance / self.sound_speed

        self.left_intensity = 1.0 / self.left_distance ** 2
        self.right_intensity = 1.0 / self.right_distance ** 2

        from math import atan, pi
        # Amplitude placement: pitch-based soundboard position plus the
        # channel pan (CC10), which also contributes interaural delay above.
        self.pan_position = atan(self.octave_position / 20) / pi * 2 + self.channel_pan
        self.left_pan, self.right_pan = self.pan(self.pan_position)

        if hrtf:
            # Brown-Duda structural model, driven by the same source
            # position: azimuth from the head (0 = front, + = right), a
            # listener distance suited to a stage image rather than the
            # legacy 0.2 m soundboard distance.
            from math import atan2, sqrt, acos, cos
            self.head_radius = 0.0875  # meters
            self.hrtf_beta = 2.0 * self.sound_speed / self.head_radius
            listener_distance = 2.0  # meters
            azimuth = atan2(self.position_x, listener_distance)
            distance = max(sqrt(self.position_x ** 2 + listener_distance ** 2),
                           self.head_radius)
            base_delay = distance / self.sound_speed

            def woodworth(ear_azimuth):
                # incidence angle between the source ray and the ear axis
                theta = acos(cos(azimuth - ear_azimuth))
                if theta <= pi / 2:
                    offset = -cos(theta)
                else:
                    offset = theta - pi / 2
                return theta, base_delay + offset * self.head_radius / self.sound_speed

            self.left_incidence, self.left_hrtf_delay = woodworth(-pi / 2)
            self.right_incidence, self.right_hrtf_delay = woodworth(pi / 2)

        # self.left_pan  = self.left_pan * self.left_intensity  / 20
        # self.right_pan = self.right_pan * self.right_intensity / 20

        if self.plucked_harmonic:
            # pluck dampening
            self.plucked_volumes = [
                (harmonic, ((self.plucked_harmonic - harmonic) / self.plucked_harmonic) ** self.pluck_dampening)
                for harmonic
                in range(1, int(self.plucked_harmonic))
            ]
        else:
            self.plucked_volumes = [(1000000, 1.0)]

    def hrtf_gain(self, frequency, incidence):
        # Brown-Duda head-shadow magnitude: single pole-zero sphere
        # approximation. alpha runs from 2.0 at the near ear (+6 dB high
        # shelf) to 0.1 around 150 degrees (-20 dB), recovering slightly
        # at 180 (the bright spot). Low frequencies pass unshadowed.
        from math import cos, pi, sqrt
        alpha_min = 0.1
        theta_min = 150.0 * pi / 180.0
        alpha = 1.0 + alpha_min / 2.0 + (1.0 - alpha_min / 2.0) * cos(incidence * pi / theta_min)
        omega = 2.0 * pi * frequency
        return sqrt((alpha * omega) ** 2 + self.hrtf_beta ** 2) / sqrt(omega ** 2 + self.hrtf_beta ** 2)

    def pan(self, p):
        from math import log, cos, sin, pi
        if p > 1.0: p = 1.0
        if p < -1.0: p = -1.0

        if p == -1.0:
            # limit of the formulas below: full left (also avoids log(0))
            left = 1.0
            right = 0.0
        else:
            left = 10.0 ** (2.0 * log(cos(pi * (float(p) / 2 + .5) / 2)))
            right = 10.0 ** (2.0 * log(sin(pi * (float(p) / 2 + .5) / 2)))

        return (left, right)

    def harmonic_volume(self, harmonic):
        if self.max_harmonic and harmonic > self.max_harmonic:
            return 0.0

        if self.odd_only and harmonic % 2 != 1:
            return 0.0

        if self.strike_point:
            # Strike comb: a string struck at fraction p of its length feeds mode n with
            # amplitude ~ |sin(n*pi*p)|, weakening n at multiples of 1/p (p~1/7 -> the sour
            # 7th). A real hammer has WIDTH that fills the notch, and that width GROWS with
            # force (harder blow -> felt compresses flatter -> wider contact patch -> notch
            # fills). So the notch is deep when played softly and fills toward ff -- a
            # velocity-dependent timbre, not just loudness. strike_depth is the depth at the
            # softest blow; attack_volume = (vel/127)^2 fills it in as you play louder.
            # (Matches the Iowa reference, an ff sample, whose 7th is already un-notched.)
            depth = self.strike_depth * (1.0 - self.attack_volume)
            comb = (1.0 - depth) + depth * abs(_sin(harmonic * _pi * self.strike_point))
        else:
            comb = sum(tv for th, tv in self.plucked_volumes if harmonic % th)   # legacy path (pipes)

        return self.gain / (harmonic ** self.attack_dampening) * comb

    def harmonic_decay(self, harmonic):
        base = self.decay_db + self.harmonic_decay_db * harmonic * (harmonic ** self.harmonic_decay_dampening)
        # Register-dependent decay: heavy bass strings ring far longer than the
        # light, heavily-damped treble. decay_register_factor (set in __init__ from
        # decay_register_slope) is < 1 in the bass (slower) and > 1 in the treble.
        return base * self.decay_register_factor


class PluckedStringProperties(SynthProperties):
    octave_gain = -0.0

    chiff_cycle = 0.0
    chiff_volume = 0.0
    chiff_min_valve_time = 0.0
    chiff_max_valve_time = 0.0

    odd_only = False
    initial_gain = 1.0 / 50

    max_harmonic = 64
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic
    inharmonicity_dynamic = False

    plucked_harmonic = 7.0
    pluck_dampening = 1.0

    tonal_dampening = 1.1
    octave_dampening = 0.025
    octave_modulo = False

    decay_db = 0.0
    harmonic_decay_db = 1.0
    harmonic_decay_dampening = 0.0


class TriplePluckedStringProperties(PluckedStringProperties):
    string_count = 3
    unison_detune = (0.25, 0.3)   # triple-string beating


class InharmonicStringProperties(PluckedStringProperties):
    # http://daffy.uah.edu/piano/page4/page3/index.html
    inharmonicity_dynamic = True

    # Hammer strike point ~1/7 of the speaking length: the |sin(n*pi*p)| comb nulls
    # the 7th harmonic (and 14th, 21st) -- the flat, dissonant minor-7th partials a
    # real piano's strike point is placed to suppress. Slightly off 1/7 (e.g. 0.135)
    # would give a deep notch instead of a mathematically exact zero.
    strike_point = 1.0 / 7
    strike_depth = 0.65   # notch depth at the SOFTEST blow; fills toward 0 at ff (velocity
                          # widens the felt contact). ~0 at ff matches the Iowa ff reference.

    inharmonicity_coefficient_func = lambda self, x, a, b, c, d, e: a + b * x + c * x * x + (d / x) + (e / (x * x))

    def inharmonicity_coefficient_for_frequency(self, frequency):
        return self.inharmonicity_coefficient_func(float(frequency), self.a, self.b, self.c, self.d, self.e)


class Steinway(InharmonicStringProperties):
    # empirical inharmonicity model for Steinway B
    a = 5.22964e-6
    b = 1.21012e-6
    c = 8.3666e-10
    d = -0.007927
    e = 0.429601

    # Keyboard pan: negative flips the pitch->position sign so the bass sits LEFT
    # and the treble RIGHT (a player's-eye view). This is the default spread, so
    # no per-part (SATB) channel pan is needed.
    octave_width = -0.12

    # Bass rings long, treble decays fast (heavy/undamped vs light/damped strings).
    # Register tilt: measured per-harmonic against the Iowa MIS samples, the bass
    # tonal partials must ring FAR longer than the mid (C2 fundamental ~1.9 dB/s
    # vs C4 ~3.9), while the treble decays a touch faster (C6 ~8.6). Mid (C4) sits
    # at octave_position 0 so the slope leaves it untouched; steepening it slows
    # the bass ring and speeds the treble to match the reference.
    decay_register_slope = 0.85

    # --- Prompt vs aftersound (Weinreich double decay) ---
    # A real piano note FADES FAST at first (the in-phase string mode dumps energy
    # hard into the bridge -- the "prompt"), then a small fraction rings on slowly
    # (the coupled-string "aftersound"). Measured against the Iowa MIS samples the
    # prompt is ~8 dB/s in the bass and ~20+ dB/s in the mid; the old decay_db=0
    # gave the fundamental only ~1 dB/s -- an organ-like sustain with no fade.
    # decay_db is that prompt floor (added to every partial before the register
    # tilt); harmonic_decay_db keeps the top decaying faster still (tone darkens
    # as it fades); the aftersound_* below carry the quiet, long tail.
    decay_db = 13.0
    harmonic_decay_db = 1.5

    # --- Real string-count-per-note, with the coupled-string two-stage decay ---
    # A piano strings each note with 1, 2, or 3 unison strings by register. The
    # strings are mistuned a hair and coupled through the bridge, so per Weinreich
    # the in-phase (symmetric) mode drives the bridge hard and decays fast -- the
    # "prompt" -- while the antisymmetric modes barely load the bridge and ring on
    # -- the "aftersound", the long singing tail. More strings -> stronger tail;
    # a single bass string has none.
    #
    # Two intertwined effects:
    #  1. The SING -- the coupled-string aftersound -- is an amplitude ENVELOPE
    #     (Decay.aftersound_*), driven by string count. Modelling it as detuned
    #     voices would beat the fundamental to a null and swell (a crescendo).
    #  2. The DANCE -- the upper-harmonic shimmer -- is real ratio-detuned string
    #     GROUPS. Each extra string is mistuned by a constant cents ratio, so its
    #     partial n sits ~n x further in Hz from the main string's; with the
    #     inharmonic stretch now live, those per-partial beat rates are
    #     incommensurate, so the upper partials sweep against each other and never
    #     realign -- shimmer, not throb. The cents are ASYMMETRIC so 3 strings
    #     never share a beat rate. The fundamental barely beats (slow, subtle);
    #     the interest climbs with the harmonic number, as on a real piano.
    aftersound_decay_ratio = 0.13      # slow tail decays this fraction as fast as the prompt
                                       # (~0.12 measured: prompt ~20 dB/s, singing tail ~2.5 dB/s)
    aftersound_level_1 = 0.28          # single wound bass string -- rings long/full (soundboard-coupled)
    aftersound_level_2 = 0.18          # slow-tail energy fraction, 2-string tenor
    aftersound_level_3 = 0.16          # ...3-string treble (more strings -> more sing)
    # Per-note UNIQUE unison detune: each note's 2nd/3rd strings are mistuned by a
    # random amount within this |cents| range, seeded deterministically per pitch
    # in __init__ (so a given note is always the same, but no two notes share a
    # detune -- avoiding the identical-every-note "wavetable" sound). One flat, one
    # sharp, so the pair straddles the tuned pitch and the note stays in tune.
    string_detune_range = (0.5, 1.7)    # min..max |cents| of the extra strings
    string_gain = (0.28, 0.20)          # extras well below the main so the unison beats
                                        # shallowly (a shimmer) instead of to deep nulls (a phaser)

    # Regulate the string-count breaks: a real piano is voiced so the monochord ->
    # bichord (G1) and bichord -> trichord (B2) crossings are seamless. We can't
    # have a fractional string, but we CAN fade each added string's gain in over a
    # couple of semitones around its break (and blend the aftersound level the same
    # way) so the shimmer and ring cross over smoothly instead of switching on hard.
    string_break_hz = (48.0, 120.0)     # F#1|G1 and A#2|B2 boundaries (see string_count_for_frequency)
    string_crossfade_semitones = 3.0    # width of the smoothstep crossfade at each break

    # --- Phantom (longitudinal) partials: the wound-bass "clang" (Conklin,
    # JASA 100, 1996) ---
    # A struck string modulates its own tension at 2x the vibration frequency;
    # that nonlinearity pumps the (much faster) longitudinal string modes and
    # radiates SUM-TONES at f_i + f_j of the transverse partials -- inharmonic
    # partials, NOT on the n*f0 series, that cluster where the longitudinal modes
    # resonate (~1 kHz for the bottom octave) and give a real piano bass its
    # metallic ring. Audible only in the wound register; they build on the strike
    # (amplitude^2 -> gain ~ v_i*v_j) and decay ~2x as fast as their parents
    # (rate d_i + d_j). Synthesized here as extra non-harmonic partials at the
    # pair-sum frequencies. Measured against the Iowa MIS F1 sample: the loudest
    # phantoms sit ~ -8 dB below the note peak, clustered 800-1400 Hz.
    phantom_coupling = 30.0       # 0 = off; overall nonlinear gain (tuned by metric, unit at C2)
    phantom_max_order = 30        # pair transverse partials up to this harmonic (reach ~1.3 kHz)
    phantom_ref_hz = 65.0         # reference pitch (C2) at which coupling == phantom_coupling
    phantom_register_power = 2.5  # phantoms taper CONTINUOUSLY as (ref/f)^power: strong on the bottom
                                  # wound strings, fading smoothly to negligible by the mid so the
                                  # top of the register stays clean (a gentler tilt, ~1.0, leaves
                                  # audible clang up at C4). No floor -> a smooth taper, no cliff.
    phantom_note_max_hz = 260.0   # hard safety cap only (coupling is already ~3% here); above it, none
    phantom_gain_floor = 3e-3     # prune pair-sums quieter than this fraction of the peak partial

    # Damper: releasing the key drops the felt and stops the string over ~0.1 s
    # (a fast decay with a soft thump), not the instant cut that a 0-length
    # release gives. (The very top of a real piano has no damper; not modelled.)
    release_valve_time = 0.12

    # --- Hammer excitation (vs a bright pluck) ---
    # A felt hammer rests on the string for a few ms, so it cannot excite partials
    # whose period is shorter than the contact time: it LOW-PASSES the strike
    # spectrum. That soft top is what separates a struck piano from a plucked
    # harpsichord. A harder/faster strike shortens the contact and raises the
    # corner, so louder notes are brighter -- the piano's dynamic timbre. Model it
    # as a soft low-pass on the harmonic amplitudes above hammer_corner_hz, the
    # corner opening with velocity (attack_volume).
    hammer_corner_hz = 4000.0    # low-pass corner at mid velocity; raise = brighter
    hammer_order = 2.0           # rolloff steepness above the corner (~6*order dB/oct)

    # Hammer contact time: a few ms of onset ramp so the strike isn't a
    # one-sample step (a click). Real contact runs ~1 ms treble to ~4 ms bass;
    # a single mid value is a good first approximation.
    attack_time = 0.003

    # --- Soundboard body response ---
    # A fixed body filter applied per partial by absolute frequency (independent
    # of velocity, unlike the hammer). It gives the tone its wooden body: a broad
    # low-mid warmth resonance, a roll-off of the extreme top (the board does not
    # radiate the highest partials efficiently), and a sub-bass radiation loss.
    # It also darkens the upper-mid partials whose string-group beating reads as a
    # phaser, so the shimmer sits under a fixed formant instead of sweeping bare.
    board_body_hz = 240.0        # centre of the low-mid warmth boost
    board_body_width = 1.05      # half-width in octaves (log-gaussian)
    board_body_gain = 0.6        # peak boost (0.6 -> ~+4 dB) at board_body_hz
    board_high_hz = 2600.0       # radiation roll-off corner up top
    board_high_order = 1.6       # gentle (~10 dB/oct) high roll-off
    board_low_hz = 35.0          # sub-bass radiation roll-off (6 dB/oct below)

    # --- Tension modulation (pitch drifts down as the note decays) ---
    # A struck string's large initial displacement stretches it, raising tension
    # and pitch; as the amplitude decays the tension relaxes and the pitch drifts
    # back down. The shift goes as amplitude^2 and scales with strike velocity, so
    # a hard/low note blooms noticeably sharp then settles. tension_bend is the
    # fractional sharpening at full amplitude and velocity (0.008 ~ 14 cents).
    tension_bend = 0.008

    # Natural per-note jitter so same-pitch doublings beat and stagger instead of
    # locking into a machine-gun unison (now that every strike is phase-coherent).
    pitch_jitter_cents = 1.0
    timing_jitter_seconds = 0.002

    def __init__(self, frequency=256.0, channel_pan=0.0, attack_volume=1.0, channel_volume=1.0):
        super().__init__(frequency, channel_pan, attack_volume, channel_volume)
        # Deterministic-per-pitch, unique-across-pitches unison detune: seed by the
        # (rounded) MIDI note so a given key is always identical, but no two notes
        # share a detune. Straddle the pitch (one flat string, one sharp) so the
        # note stays in tune. Keyboard pan is automatic -- octave_position already
        # spreads notes low-left to high-right via position_x (no channel pan
        # needed), so the strings' physical uniqueness and register placement come
        # for free per note.
        from math import log
        midi = int(round(69.0 + 12.0 * log(float(frequency) / 440.0) / log(2)))
        rng = _random.Random(midi)
        lo, hi = self.string_detune_range
        self.note_detune_cents = (-rng.uniform(lo, hi), rng.uniform(lo, hi))

    def string_count_for_frequency(self, frequency):
        # Full-upright stringing (the owner's instrument): single wound monochord
        # bass, two strings from G1, three from B2. Thresholds sit BETWEEN the
        # boundary notes (F#1|G1 ~ 48 Hz, A#2|B2 ~ 120 Hz) so the hybrid tuning's
        # slightly-sharp pitches still land on the right side of each break.
        if frequency < 48.0:    # A0-F#1: single wound string
            return 1
        if frequency < 120.0:   # G1-A#2: two strings (still wound)
            return 2
        return 3                # B2 and up: three strings

    def _string_blend(self, frequency, break_hz):
        # Smoothstep 0..1 as frequency rises through break_hz +/- half the crossfade
        # width (log-symmetric), so an added string fades in over a few semitones
        # instead of switching on at a single note -- the "regulation" of the break.
        half = self.string_crossfade_semitones / 2.0
        lo = break_hz * 2.0 ** (-half / 12.0)
        hi = break_hz * 2.0 ** (half / 12.0)
        if frequency <= lo:
            return 0.0
        if frequency >= hi:
            return 1.0
        t = (_log(frequency) - _log(lo)) / (_log(hi) - _log(lo))
        return t * t * (3.0 - 2.0 * t)

    def aftersound(self, frequency, decay_rate):
        # Blend the ring level across both breaks instead of stepping per string count.
        b1 = self._string_blend(frequency, self.string_break_hz[0])
        b2 = self._string_blend(frequency, self.string_break_hz[1])
        level = self.aftersound_level_1 + (self.aftersound_level_2 - self.aftersound_level_1) * b1
        level += (self.aftersound_level_3 - level) * b2
        return (level, decay_rate * self.aftersound_decay_ratio)

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        # Second string fades in across G1, third across B2 -- a crossfade, not a
        # hard switch, so the unison shimmer regulates smoothly through the breaks.
        gains = (self.string_gain[0] * self._string_blend(frequency, self.string_break_hz[0]),
                 self.string_gain[1] * self._string_blend(frequency, self.string_break_hz[1]))
        voices = []
        for i, g in enumerate(gains[:len(self.note_detune_cents)]):
            if g < 1e-3:
                continue
            ratio = 2.0 ** (self.note_detune_cents[i] / 1200.0) - 1.0
            voices.append((g, 0.0, ratio, harmonic_decay))
        return voices

    def harmonic_volume(self, harmonic):
        v = super().harmonic_volume(harmonic)
        if v == 0.0:
            return 0.0
        # Hammer low-pass: attenuate partials above a velocity-dependent corner.
        # attack_volume = (velocity/127)^2, so louder strikes open the corner and
        # brighten the tone. (Note frequency is not stored raw; recover it from
        # octave_position = log2(f0 / frequency_x).)
        fn = self.frequency_x * (2.0 ** self.octave_position) * harmonic
        fc = self.hammer_corner_hz * (0.7 + 0.7 * self.attack_volume)
        return v / (1.0 + (fn / fc) ** self.hammer_order) * self.soundboard_gain(fn)

    def soundboard_gain(self, fn):
        # Body warmth (log-gaussian boost in the low-mid) x top radiation
        # roll-off x sub-bass radiation loss. Fixed, velocity-independent.
        body = 1.0 + self.board_body_gain * _exp(
            -(_log(fn / self.board_body_hz) ** 2) / (2.0 * self.board_body_width ** 2))
        high = 1.0 / (1.0 + (fn / self.board_high_hz) ** self.board_high_order)
        low = 1.0 / (1.0 + (self.board_low_hz / fn) ** 2)
        return body * high * low


class BlownPipeProperties(SynthProperties):
    octave_gain = -0.0

    chiff_cycle = 1.0 / 5.0
    chiff_volume = 1.0
    chiff_release = 1.0
    # Pipes are tongued, not softly blown: a hard, fast onset. Kept short so
    # fast notes (flute trills) finish their attack and reach full amplitude
    # instead of living in a perpetual ramp -- an under-developed trill note
    # reads as quiet no matter its gain. (Organ/reed/brass override these.)
    chiff_min_valve_time = 0.006
    chiff_max_valve_time = 0.018

    odd_only = True
    # Peak-normalized to the loudest orchestral voice (bowed string): a stored
    # wavetable is normalized so its waveform peaks at unity, and a sparse
    # spectrum (odd-only pipe -- nearly a sine, crest ~2 dB) then carries far
    # more RMS at that peak than a rich, spiky voice (brass crest ~9 dB). The
    # flat 1/5000 undercounted that: the pipe measured ~6 dB below the string's
    # rendered peak, so it sat too quiet. See the per-class gains below; the
    # ratios come from the real rendered peak of each voice at middle C.
    # Equal-peak put the flute at 1/2400, but that leaves a lead voice merely
    # tied with the accompaniment (horn/tuba) that shares its register; the
    # normalization boosted those mid voices up to meet it, costing the flute
    # the relative prominence it had before. A lead sits ABOVE the group, so
    # push ~+4.5 dB past equal-peak -- clear of dark brass rather than tied.
    initial_gain = 1.0 / 1400   # pipe/flute lead: equal-peak (1/2400) + ~4.5 dB

    enharmonic_width = 0.0

    max_harmonic = 32
    # Flue pipes are not perfectly harmonic: the mouth/end correction shifts the
    # effective length with frequency (and scales with bore width), stretching the
    # partials slightly. Use the fixed 2nd-harmonic coefficient -- NOT the piano's
    # dynamic Steinway model -- which places the octave partial exactly on the
    # "equal pythagorean" stretched octave (stretch_interval = 7th root of the
    # Pythagorean comma, so 12 pure fifths = 7 stretched octaves; see
    # inharmonicity.py). The pipe's spectrum then reinforces that temperament.
    # Inherited by flue organ / pipe / flute / brass; reed organ and bowed
    # strings override back to 0.
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic
    inharmonicity_dynamic = False

    plucked_harmonic = 1000.0
    pluck_dampening = 1.0

    tonal_dampening = 2.0
    octave_dampening = 0.0
    octave_modulo = False

    decay_db = 0.0
    harmonic_decay_db = 0.0
    harmonic_decay_dampening = 0.0


class OrganProperties(BlownPipeProperties):
    initial_gain = 1.0 / 5000   # keep organ/reed/brass at the pre-pipe level
    tonal_dampening = 1.4
    octave_dampening = 1.0 / 8
    octave_modulo = True


class FlueOrganProperties(OrganProperties):
    initial_gain = 1.0 / 3040   # +4.3 dB to equal-peak (moderate spectrum)
    odd_only = False
    # Principal pipes speak fast; keep the inherited chiff character but
    # compress it into a tighter onset than the generic blown pipe's 0.3 s.
    chiff_min_valve_time = 0.03
    chiff_max_valve_time = 0.10


class ReedOrganProperties(OrganProperties):
    initial_gain = 1.0 / 2200   # +7.1 dB to equal-peak (odd-only reed: sparse)
    chiff_cycle = 0.0
    chiff_volume = 0.0
    chiff_min_valve_time = 0.0
    chiff_max_valve_time = 0.0
    odd_only = True
    inharmonicity_coefficient = 0.0


class BrassProperties(OrganProperties):
    # tongued attack: narrowband growl, attack only, quick valve
    initial_gain = 1.0 / 3310   # +3.6 dB to equal-peak (rich but spiky, crest ~7 dB)
    chiff_cycle = 0.35
    chiff_volume = 2.6
    chiff_release = 0.0
    # Faster, more tongued attack than the organ's slow swell.
    chiff_min_valve_time = 0.02
    chiff_max_valve_time = 0.045

    # Full harmonic series, not odd-only: odd-only is the hollow clarinet/reed
    # signature; brass is bright and full.
    odd_only = False
    tonal_dampening = 1.0       # brighter than the organ's 1.4: brass buzz

    # Brass "front": the note blooms to the attack peak, then settles ~4 dB
    # into the sustain within ~0.15 s and holds, with the upper harmonics
    # settling faster (the brightness blooms on the attack). This amplitude
    # envelope is much of what separates a brass note from a held reed.
    decay_db = 18.0
    harmonic_decay_db = 4.0
    harmonic_decay_dampening = 0.0
    sustain_level = 0.6


class BrightBrassProperties(BrassProperties):
    """Cylindrical-bore brass (trumpet, trombone): the cylindrical tubing
    sustains strong upper harmonics, so these are bright and edgy with a
    pronounced attack 'rip' -- the brightness blooms hard then settles."""
    initial_gain = 1.0 / 4880      # +0.2 dB to equal-peak (already near the loudest)
    tonal_dampening = 0.82         # slow rolloff = strong harmonics, bright
    harmonic_decay_db = 5.5        # strong brightness bloom on the attack
    decay_db = 20.0
    sustain_level = 0.58           # pronounced front
    chiff_volume = 2.9             # hard tongued attack
    chiff_min_valve_time = 0.015
    chiff_max_valve_time = 0.04    # fast, tight onset


class DarkBrassProperties(BrassProperties):
    """Conical-bore brass (French horn, tuba): the continuous flare damps the
    upper harmonics into a round, mellow tone, and conical instruments speak
    less abruptly -- a rounder, slower attack with a gentler bloom."""
    initial_gain = 1.0 / 2320      # +6.7 dB to equal-peak (dark = sparse highs)
    tonal_dampening = 1.35         # fast rolloff = few highs, dark/round
    harmonic_decay_db = 2.0        # gentle brightness bloom
    decay_db = 13.0
    sustain_level = 0.7            # subtle front
    chiff_volume = 1.6             # soft tongue, rounder speech
    chiff_min_valve_time = 0.03
    chiff_max_valve_time = 0.075   # slower, rounder onset


# --- Broad melodic buckets (generic; specialize per-instrument later) ---

class MalletProperties(PluckedStringProperties):
    """Struck bar/bell: bright inharmonic onset, fast shimmer decay. Covers
    the chromatic-percussion family (celesta, glockenspiel, vibraphone,
    marimba, xylophone, tubular bells) and struck ethnic/percussive metal
    (kalimba, steel drums, tinkle bell, agogo, woodblock). A first generic
    voice; a true modal-bar model is the realism step."""
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic * 6.0
    inharmonicity_dynamic = False

    # struck bars ring in a few clangorous modes, not a full harmonic stack
    max_harmonic = 24
    plucked_harmonic = 4.0
    pluck_dampening = 1.5

    tonal_dampening = 1.4
    # bright onset that decays fast: upper partials shed quickly
    decay_db = 0.0
    harmonic_decay_db = 4.0
    harmonic_decay_dampening = 0.3


class BowedStringProperties(BlownPipeProperties):
    """Sustained bowed string: full harmonic series with a sawtooth-ish
    1/n tilt, no chiff, gentle onset. Covers solo strings (violin, viola,
    cello, contrabass), string/synth ensembles, choir/voice pads, and
    sustained synth leads/pads as a broad bucket. This is the brighter
    'first' section; BowedStringSecond is the darker companion."""
    odd_only = False
    initial_gain = 1.0 / 5000   # neutral; CC7 (79 in monocas2) holds strings back
    # Section shimmer via a small sustained phase jitter (a running chiff),
    # not many detuned voices: broader per-partial band, no amplitude wobble.
    chiff_cycle = 0.06          # phase-deviation magnitude (small = subtle)
    chiff_volume = 0.5
    chiff_release = 0.0
    sustain_jitter = 0.3        # how much jitter persists on the held note
    chiff_min_valve_time = 0.04
    chiff_max_valve_time = 0.10

    max_harmonic = 40
    inharmonicity_coefficient = 0.0

    # 1/n-ish spectrum: brighter than an organ, no octave-modulo steps
    tonal_dampening = 1.0
    octave_dampening = 0.05
    octave_modulo = False


class BowedStringSecondProperties(BowedStringProperties):
    """The 'second' string section (GM String Ensemble 2): darker and a
    little rounder than the first, with a slightly wider shimmer, so the two
    ensembles read as distinct sections rather than one doubled patch."""
    initial_gain = 1.0 / 3560   # +2.9 dB to equal-peak (darker than first section)
    tonal_dampening = 1.25      # darker: upper partials rolled off more
    max_harmonic = 32
    chiff_cycle = 0.045         # a subtly different shimmer texture
    sustain_jitter = 0.38



# --- Percussion (channel 10): broad noise/membrane/metal buckets ---
# The additive engine has no white-noise source, so "noise" is approximated
# by a dense stack of strongly inharmonic partials whose stretched
# frequencies decorrelate into colored noise. Each drum is struck at a
# fixed base frequency from the percussion map, not a tuned pitch.

class PercussionProperties(PluckedStringProperties):
    """Base drum voice: struck onset, no chiff jitter, fast decay."""
    chiff_cycle = 0.0
    chiff_volume = 0.0
    chiff_min_valve_time = 0.002
    chiff_max_valve_time = 0.010
    odd_only = False
    inharmonicity_dynamic = False
    plucked_harmonic = 0.0     # no string comb/notching on a drum
    octave_gain = 0.0
    octave_dampening = 0.0
    octave_modulo = False


class MembraneDrumProperties(PercussionProperties):
    """Struck membrane that rings with a pitch (toms, congas, timbales,
    cuica): a strong low fundamental with a few mildly inharmonic modes.
    One-shot, like the other struck percussion -- it rings out its own decay
    (~0.8 s here) regardless of how short the note is. decay_db sets the
    ring: higher = tighter."""
    one_shot = True
    release_floor_db = -40.0
    initial_gain = 1.0 / 2.5
    max_harmonic = 12
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic * 8.0
    tonal_dampening = 1.6
    decay_db = 34.0            # tom ring ~0.85 s to -30 dB
    harmonic_decay_db = 6.0
    harmonic_decay_dampening = 0.2


class KickDrumProperties(MembraneDrumProperties):
    """Bass drum: a tight, dark low thump -- louder and shorter than a tom,
    a punchy body that dies in about half a second."""
    initial_gain = 1.0 / 1.05  # near the per-tone ceiling (cannot go higher clean)
    max_harmonic = 10
    tonal_dampening = 1.9      # darker/rounder: fundamental-dominant thump
    decay_db = 24.0            # more body (louder-perceived); rings ~1.1 s


class NoiseDrumProperties(PercussionProperties):
    """Noise-dominated hit (hi-hat, shaker, guiro): a dense stack of strongly
    stretched partials approximating a band of colored noise, with a fast
    decay. decay_db sets how long the wash rings."""
    initial_gain = 1.0 / 5.6
    max_harmonic = 64
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic * 40.0
    tonal_dampening = 0.4          # nearly flat spectrum = broadband
    decay_db = 20.0
    harmonic_decay_db = 2.0
    harmonic_decay_dampening = 0.0


class SnareDrumProperties(PercussionProperties):
    """Snare: a short burst of mostly noise. Discrete inharmonic partials
    alone still read as pitched, so the noise comes primarily from a wide
    running phase jitter (the chiff mechanism cranked up) that smears every
    partial into broadband hiss -- the snare wires -- over a punchy decay."""
    initial_gain = 1.0 / 9
    max_harmonic = 48
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic * 20.0
    tonal_dampening = 0.3
    # One-shot, like the crash: the hit rings out its own decay (~1 s tail)
    # regardless of how short the note is, instead of being cut at note-off.
    one_shot = True
    release_floor_db = -45.0
    decay_db = 28.0                 # fast, punchy
    harmonic_decay_db = 1.5
    harmonic_decay_dampening = 0.0

    # Wide chiff = the wire noise. Large phase deviation with the jitter run
    # at full through the whole hit makes each partial mostly noise, so the
    # snare is a "shhh" crack, not a pitched tom.
    chiff_volume = 3.0
    chiff_cycle = 0.9               # near-full phase decorrelation -> noise
    chiff_release = 0.0
    sustain_jitter = 1.0            # jitter runs the entire (short) hit
    chiff_min_valve_time = 0.002
    chiff_max_valve_time = 0.012


class MetalPercussionProperties(PercussionProperties):
    """Struck pitched metal/wood that rings with a clear-ish pitch (cowbell,
    agogo, triangle, woodblock, claves, ride bell): bright inharmonic modes,
    no noise wash -- these are meant to be tonal, unlike a cymbal."""
    initial_gain = 1.0 / 2.25
    max_harmonic = 40
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic * 20.0
    tonal_dampening = 0.9
    decay_db = 4.0
    harmonic_decay_db = 1.5
    harmonic_decay_dampening = 0.1


class CymbalProperties(PercussionProperties):
    """Cymbal (crash, ride, splash, china): a bright broadband noise wash --
    the snare's wide-chiff noise, but a fast splash that rings out over a
    second or two instead of a punchy die. A few inharmonic modes give the
    metallic edge under the hiss."""
    initial_gain = 1.0 / 10
    max_harmonic = 80               # very bright, energy well up top
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic * 25.0
    tonal_dampening = 0.15          # near-flat: the modes don't stick out of the wash

    # One-shot: the splash rings out on its own exponential decay and ignores
    # note-off, so a short crash note still rings and there is no linear-fade
    # "cut". A slow decay_db is what makes it a crash and not a hi-hat -- long
    # sustaining wash, not a quick tick.
    one_shot = True
    release_floor_db = -50.0
    decay_db = 6.0
    harmonic_decay_db = 0.4
    harmonic_decay_dampening = 0.0

    # Broadband wash via wide chiff, like the snare, sustained the whole ring.
    # Kept below the level that slams the per-tone ceiling so initial_gain
    # actually controls how loud the crash is.
    chiff_volume = 1.8
    chiff_cycle = 0.95
    chiff_release = 0.0
    sustain_jitter = 1.0
    chiff_min_valve_time = 0.002
    chiff_max_valve_time = 0.02     # fast splash onset


class SynthTone(BaseTone):
    synth_id = 0

    def updateFrequency(self, frequency):
        if self.frequency is None:
            self.frequency = frequency
            self.init_partials(frequency)

        if frequency != self.frequency:
            for partial in self.partials:
                # if not partial.state is partial.Pressed:
                partial.updateBaseFrequency(frequency)

    def updatePan(self, p):
        if p != self.pan:
            for partial in self.partials:
                # if not partial.state is partial.Pressed:
                partial.updatePan(p)

    def release(self):
        self.ref_count -= 1
        for partial in self.partials:
            partial.lift()

    def unrelease(self):
        self.ref_count += 1
        for partial in self.partials:
            partial.unlift()

    def finished(self):
        if self.partials:
            return self.partials[0].finished()
        else:
            return False

    def remove(self):
        self.sampler.remove(self)

    def __init__(self, sampler, nyquist, audio_channel, midi_channel, panning=0.0, start=None, stop=None,
                 property_class=SynthProperties, attack_volume=1.0, channel_volume=1.0):
        self.sampler = sampler
        self.id = self.synth_id
        SynthTone.synth_id += 1

        self.frequency = None
        self.panning = panning
        # Velocity gain and channel (CC7*CC11) gain, applied to the partials'
        # amplitude when the tuner builds them in init_partials.
        self.attack_volume = attack_volume
        self.channel_volume = channel_volume
        self.nyquist = nyquist
        self.audio_channel = audio_channel
        self.midi_channel = midi_channel
        self.start = start
        self.stop = stop
        self.property_class = property_class

        # May be incremented by an attack that arrives before the first
        # tuning creates the partials; they inherit this count on creation.
        self.ref_count = 0
        self.partials = []

        # Per-note onset-fade cap (seconds); set from note duration so fast
        # notes still articulate. None until the note-on supplies a length.
        self.max_fade = None

    def set_max_fade(self, max_fade):
        self.max_fade = max_fade
        for partial in self.partials:
            partial.max_fade = max_fade

    def init_partials(self, frequency):
        self.properties = self.property_class(frequency, self.panning,
                                              self.attack_volume, self.channel_volume)
        if hrtf:
            # Delay from the spherical-head model; amplitude comes per
            # partial from the head-shadow gain instead of a flat pan.
            self.delay = {
                0: self.properties.left_hrtf_delay,
                1: self.properties.right_hrtf_delay,
            }[self.audio_channel]
            self.incidence = {
                0: self.properties.left_incidence,
                1: self.properties.right_incidence,
            }[self.audio_channel]
            self.pan = 1.0
        else:
            self.delay = {
                0: self.properties.left_delay,
                1: self.properties.right_delay,
            }[self.audio_channel]
            self.pan = {
                0: self.properties.left_pan,
                1: self.properties.right_pan,
            }[self.audio_channel]

        self.partials = []

        volume = 0.0
        transverse = []                       # (freq, raw gain, decay) for phantom-partial pairing
        max_partials = int(float(self.nyquist) / self.frequency)
        for harmonic in range(1, max_partials):
            if self.properties.inharmonicity_dynamic:
                self.properties.inharmonicity_coefficient = self.properties.inharmonicity_coefficient_for_frequency(
                    frequency)

            if self.properties.inharmonicity_coefficient > 0.0:
                harmonic_frequency = self.frequency * harmonic * (
                            1.0 + 0.5 * (harmonic ** 2 - 1) * self.properties.inharmonicity_coefficient)
            else:
                harmonic_frequency = self.frequency * harmonic

            if harmonic_frequency > self.nyquist:
                break

            harmonic_volume_raw = self.properties.harmonic_volume(harmonic)
            harmonic_volume = harmonic_volume_raw * self.pan
            if hrtf:
                harmonic_volume *= self.properties.hrtf_gain(harmonic_frequency, self.incidence)
            if harmonic_volume == 0.0:
                continue

            volume += harmonic_volume

            harmonic_decay = self.properties.harmonic_decay(harmonic)
            transverse.append((harmonic_frequency, harmonic_volume_raw, harmonic_decay))
            errlog("SimplePartial(%s, %s, %s, %s, %s)" % (
                self.frequency, harmonic, harmonic_volume, harmonic_decay, self.delay))
            self.partials.append(
                SimplePartial(self.properties, self.frequency, harmonic, harmonic_volume, harmonic_decay, self.delay,
                              self.ref_count))
            # Extra unison voices beat against the main partial: a couple of
            # ratio-detuned strings for a piano (the dance), a fixed-Hz spread
            # for a section of many bowed strings. Each voice carries its own
            # gain, detune (Hz and/or ratio), and decay.
            for gain_mult, offset_hz, detune_ratio, unison_decay in self.properties.unison_voices(
                    self.frequency, harmonic, harmonic_decay):
                partial = SimplePartial(self.properties, self.frequency, harmonic,
                                        harmonic_volume * gain_mult, unison_decay,
                                        self.delay, self.ref_count)
                partial.frequency_offset = offset_hz
                partial.detune_ratio = detune_ratio
                self.partials.append(partial)

        # --- Phantom (longitudinal) partials for the wound bass (Conklin) ---
        # Sum-tones f_i + f_j of the transverse partials, gain ~ coupling*v_i*v_j
        # (the tension nonlinearity), decay d_i + d_j (a product of two decays).
        # Gated to the wound register; off (coupling 0) for every other tuning.
        coupling = getattr(self.properties, 'phantom_coupling', 0.0)
        power = getattr(self.properties, 'phantom_register_power', 0.0)
        if power > 0.0:                       # continuous taper: strong at the bottom, fading up
            coupling *= (getattr(self.properties, 'phantom_ref_hz', 65.0) / self.frequency) ** power
        if coupling > 0.0 and self.frequency <= getattr(self.properties, 'phantom_note_max_hz', 0.0) and transverse:
            parents = transverse[:getattr(self.properties, 'phantom_max_order', 16)]
            floor = getattr(self.properties, 'phantom_gain_floor', 3e-3) * max(v for _, v, _ in parents)
            for a in range(len(parents)):
                fa, va, da = parents[a]
                for b in range(a, len(parents)):
                    fb, vb, db_ = parents[b]
                    f_ph = fa + fb
                    if f_ph >= self.nyquist:
                        break
                    gain = coupling * va * vb * (1.0 if a == b else 2.0)
                    if gain < floor:
                        continue
                    ph = SimplePartial(self.properties, self.frequency, f_ph / self.frequency,
                                       gain * self.pan, da + db_, self.delay, self.ref_count)
                    ph.inharmonic_stretch = 1.0    # already placed at the (stretched) sum frequency
                    self.partials.append(ph)

        # Partials created after a note-on set a fade cap inherit it.
        if self.max_fade is not None:
            for partial in self.partials:
                partial.max_fade = self.max_fade


class SynthSampler(BaseSampler):
    def __init__(self, audio_channel=0, sample_rate=48000, sample_depth=16, sample_packing="h"):
        BaseSampler.__init__(self, sample_rate, sample_depth, sample_packing)
        self.audio_channel = audio_channel
        self.tones = {}

    def newTone(self, midi_channel, frequency, pan, start, stop=None, property_class=SynthProperties,
                attack_volume=1.0, channel_volume=1.0):
        tone = SynthTone(self, self.nyquist, self.audio_channel, midi_channel, pan, start, stop,
                         property_class, attack_volume, channel_volume)
        self.tones[tone.id] = tone
        return tone

    def remove(self, tone):
        if tone.id in self.tones:
            del self.tones[tone.id]

    def remaining(self):
        return not self.tones

    def has_active_tones(self):
        """True while any tone is still sounding (not decayed/released). Used
        to keep the render running until a one-shot percussion tail rings out,
        rather than stopping on the first zero-valued output sample (which a
        clean tonal voice produces at every zero crossing)."""
        return any(not tone.finished() for tone in self.tones.values())

    def sum_values(self, seconds, nyquist):
        if self.tones:
            # errlog(sorted(tone.frequency for tone in self.tones.values()))
            v = sum(tone.sum_values(seconds, nyquist) for tone in list(self.tones.values())) * master_gain
            # for tone in self.tones.values():
            #    errlog(tone)
            #    errlog(tone.sum_values(seconds, nyquist))
            if v > 1.0:
                clipped(v)
                v = 1.0

            if v < -1.0:
                clipped(v)
                v = -1.0

            return v
        else:
            return 0.0
