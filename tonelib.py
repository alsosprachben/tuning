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


def section_onset(salt, midi, index, width_ms):
    """How late player `index` is, in seconds, 0..width_ms.

    Stateless and keyed on the SECTION and the PITCH -- not on an RNG draw and
    not on the clock. Both of those were tried and both are wrong here:

      - An RNG draw in __init__, the way attack_jitter is done, desynchronises
        the two renderers: the reference builds ONE TONE PER EAR, so it
        constructs two properties per note where blockrender constructs one, and
        the same player would get a different entry time in each ear.
        (attack_jitter has that flaw today; only the piano sets it, and 0-2 ms
        of it, so it surfaces as a small unintended ITD rather than anything
        audible.)
      - Keying on the note's start time gives a different scatter per entry,
        which is what you actually want -- but the reference has no nominal
        onset to key on. Its hammer_down receives the moment THAT PARTIAL was
        struck, and those drift a millisecond or two apart within one note, so
        every partial drew its own entry and the two renderers disagreed by
        2 dB across the band.

    So OFFLINE a given pitch scatters the same way every time it is played;
    different pitches scatter differently. Live is not bound by this and redraws
    on every key press -- see Slab.stamp_cols -- which is where repeated punches
    on one pitch actually happen.
    """
    if not width_ms:
        return 0.0
    x = (int(salt) & 0xFFFFFFFF) * 0x9E3779B1
    x = (x + (int(midi) << 20) + int(index)) & 0xFFFFFFFFFFFFFFFF
    x = (x + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    x ^= x >> 30; x = (x * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    x ^= x >> 27; x = (x * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    x ^= x >> 31
    return (x / 18446744073709551616.0) * (width_ms / 1000.0)


def rand(second):
    """A stateless hash, not a table -- see hash01() in synthkernel.c.

    This was a 100000-entry table read at index floor(x * granularity) MOD
    granularity, and its one caller passes x = t * f -- so how random the chiff
    was depended on how round the partial's frequency happened to be. At A=440,
    A2 repeats every 200 ms and A3/A4 every 50 ms, while E4, C4, G3 and D4 do
    not repeat inside a second. Under hybrid (A=441) the A octaves repeat at
    exactly the partial's period, where the chiff stops being noise at all.
    Same index, no wrap, run through splitmix64 -- so it never repeats, treats
    every note alike, and the C kernel computes the identical value from the
    identical index.
    """
    x = int(second * rand_granularity) & 0xFFFFFFFFFFFFFFFF
    x = (x + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    x ^= x >> 31
    return (x >> 11) * (1.0 / 9007199254740992.0)


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


def db_amplitude(db):
    # db_ratio above is a POWER ratio, which is what the decay envelopes want.
    # Anything multiplied into a partial's AMPLITUDE needs the /20 form, or the
    # knob lands at twice its stated value -- which is what had happened to
    # register_effort_db: 3.5 dB on the horn was delivering 7, and that inflated
    # U was most of why the brass measured 4 to 9 dB louder at the bottom of the
    # compass than at the top.
    return 10 ** (float(db) / 20)


from zlib import crc32 as _crc32

# Per-note draws that the build was repeating per HARMONIC. All three are pure
# functions of (class, note) or (class, note, player) and were being recomputed
# tens of thousands of times per piece; see the docstrings at their use sites.
_SECTION_SALT = {}
_VIBRATO_CACHE = {}
_SECTION_CACHE = {}

_PLUCK_COMB = {}


def _pluck_comb(plucked_harmonic, pluck_dampening, harmonic):
    """The legacy pluck comb, memoised. Was 87% of the time to build a render.

    series_volume() used to evaluate this inline as

        sum(tv for th, tv in self.plucked_volumes if harmonic % th)

    over a list that is 999 entries long for every pipe, wind, brass, string,
    organ and vocal voice (BlownPipeProperties.plucked_harmonic = 1000). That is
    an O(1000) Python generator per harmonic per rank per note: profiled on a
    254-note organ fugue it was 50.8 million iterations and 87% of the whole
    build.

    It depends on nothing per-note -- not pitch, not velocity, not the note's
    gain -- only on the two class constants and the harmonic index. So it is
    computed once per (plucked_harmonic, pluck_dampening, harmonic) and kept.
    The table is tiny: harmonics run to at most 80.
    """
    key = (plucked_harmonic, pluck_dampening, harmonic)
    got = _PLUCK_COMB.get(key)
    if got is None:
        if plucked_harmonic:
            got = sum(((plucked_harmonic - h) / plucked_harmonic) ** pluck_dampening
                      for h in range(1, int(plucked_harmonic)) if harmonic % h)
        else:
            got = 1.0 if harmonic % 1000000 else 0.0
        _PLUCK_COMB[key] = got
    return got


_RANK_SPECTRA = {}


def rank_spectrum(cls):
    """A borrowed spectrum class with the player's register behaviour removed.

    A cross-family stop borrows an orchestral voice's harmonic_volume for its
    COLOUR -- the organ Trumpet is a reed rank shaped like a trumpet, not a
    trumpet. But harmonic_volume carries the note's gain, and that gain carries
    register_effort/register_tilt, which model what a PLAYER does across the
    compass. A pipe has no player: it is cut to a length and it speaks. Left in,
    the trumpet's projection tilt would have leaned the rank's own balance up the
    keyboard by several dB.
    """
    got = _RANK_SPECTRA.get(cls)
    if got is None:
        got = type(cls.__name__ + "Rank", (cls,),
                   {"register_effort_db": 0.0, "register_tilt_db": 0.0, "projection_db": 0.0})
        _RANK_SPECTRA[cls] = got
    return got


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

    # (depth_fraction, rate_hz, phase_rad) if this partial belongs to a player
    # with their own vibrato; None for one-body voices. See voice_vibrato().
    vibrato = None

    # Which player of a section this partial belongs to, or None for a voice
    # that is one body. Only used to look up that player's entry time.
    player = None

    # Where this partial's phase accumulator starts, in CYCLES, at the onset.
    # 0 for everything struck or blown as one body; an ensemble's extra players
    # each get their own (see BowedStringProperties.unison_voices).
    start_phase = 0.0

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

    # Fractional pitch offset of THIS partial at onset, decaying to 0 as the pipe's
    # drive mode-locks it to an exact harmonic (see SimplePartial.frequency and
    # SynthProperties.mode_lock_offset_for). 0 = no speech transient.
    mode_lock_offset = 0.0

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
        fade_time = self.properties.speech_time(
            fade_time, getattr(self, "base_frequency", frequency))

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

        # ENTRY SCATTER: this player's own start, on THIS entry. Shifting
        # `second` is all it takes -- last_second is set from it below, so the
        # phase accumulator starts late too, which is why the line above says
        # attack_jitter delays "phase + envelope". blockrender does the same
        # thing by moving the partial's `non`.
        if self.player is not None:
            # base_frequency, NOT `frequency`: hammer_down is handed THIS
            # PARTIAL's frequency, so hashing the pitch off it gave every
            # harmonic of a player its own entry time -- 32 entries per player
            # instead of one, and 2 dB of disagreement with blockrender, which
            # keys off the note's f0.
            _o = self.properties.section_onsets_at(
                getattr(self, 'base_frequency', frequency))
            if _o and self.player < len(_o):
                second = second + _o[self.player]

        # Reset the phase accumulator at the strike so the partial starts at
        # phase 0 here, regardless of when it was created. Without this a note
        # attacking at t>0 has last_second=0, so its first cycle() jumps to
        # second*frequency -- a different offset per partial -- leaving the
        # struck strings (and same-frequency string-group voices) incoherent and
        # cancelling. A real strike excites all modes in phase; so must we.
        self.last_cycle = self.start_phase
        self.last_second = second

        if self.properties.attack_time is not None:
            fade_time = self.properties.attack_time
        else:
            fade_time = self.properties.chiff_min_valve_time + (
                        self.properties.chiff_max_valve_time - self.properties.chiff_min_valve_time) * 1.0
        fade_time = self.properties.speech_time(
            fade_time, getattr(self, "base_frequency", frequency))

        if self.max_fade is not None:
            fade_time = min(fade_time, self.max_fade)

        self.attack_fade = Fade(Second(second + self.delay), Second(second + self.delay + fade_time))
        # The chiff burst has its OWN (short, capped) width, decoupled from the
        # slow speech fade, and rolls off for the upper harmonics -- so a big
        # pipe's chiff is a brief low chuff, not a long high hiss (see the chiff
        # model on SynthProperties). Defaults reproduce the old behaviour exactly.
        base_freq = getattr(self, "base_frequency", frequency)
        chiff_fade_time = self.properties.chiff_time(base_freq, fade_time)
        if self.max_fade is not None:
            chiff_fade_time = min(chiff_fade_time, self.max_fade)
        self.chiff_fade = Fade(Second(second + self.delay),
                               Second(second + self.delay + chiff_fade_time))
        self.chiff_hgain = self.properties.chiff_harmonic_gain(
            frequency / base_freq if base_freq else 1.0)
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
                # chiff_fade (its own short, capped width) -- NOT attack_fade (the
                # slow speech), so a big pipe's chiff is a brief burst, not a long hiss.
                jitter_fade = self.chiff_fade.fade_in(second)  # * self.chiff_fade.fade_out(second)
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

                # base_frequency/440 scales chiff volume DOWN for big pipes; the
                # per-partial chiff_hgain rolls off the upper harmonics (low chuff).
                jitter = sin(pi * 2 * (self.cycle(second,
                                                  frequency) + cycle_jitter)) * jitter_fade * self.properties.chiff_volume * self.base_frequency / 440 * getattr(self, "chiff_hgain", 1.0)
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
        # Sum this voice's partials in full precision -- do NOT clamp per tone.
        # A loud voice (e.g. a full-pleno organ note whose partials line up at the
        # in-phase attack) legitimately exceeds +/-1 before it is mixed with the
        # others; clamping here would distort and quiet that single voice. The one
        # clip that belongs is at the output, after all voices are summed and
        # scaled by master_gain (SynthSampler.sum_values). The block backend mixes
        # the same way.
        return sum(p.value(second, nyquist) for p in self.partials)


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
        # Per-player vibrato: the frequency itself wanders, and cycle() integrates
        # it sample by sample (the C kernel does the same integral analytically).
        if self.vibrato is not None:
            from math import sin as _sin
            d, r, ph = self.vibrato
            f *= 1.0 + d * _sin(6.283185307179586 * r * second + ph)

        tb = self.properties.tension_bend
        if tb and self.sustain is not None:
            t = second - self.sustain.start_second.get()
            if 0.0 <= t < self.properties.tension_settle_cutoff:
                env = _exp(-t / self.properties.tension_settle_time)
                f *= 1.0 + tb * self.properties.attack_volume * env
        # Pipe speech transient: a pipe's PASSIVE resonances are mildly inharmonic
        # (the open-end correction shrinks with frequency, so upper modes sit sharp),
        # but a sounding pipe is a nonlinearly DRIVEN oscillator -- the jet (or reed
        # tongue) mode-locks the modes into one exactly periodic waveform. So the
        # partials start at their passive, inharmonic frequencies and are pulled to
        # exact harmonics as the oscillation locks. That transient is a real part of
        # how a pipe speaks; the steady tone is harmonic, which is why organs are
        # NOT stretch-tuned. self.mode_lock_offset is the partial's fractional
        # deviation at onset (0 for the fundamental, growing with mode number).
        mo = self.mode_lock_offset
        if mo and self.sustain is not None:
            t = second - self.sustain.start_second.get()
            tau = self.properties.mode_lock_time
            if 0.0 <= t < tau * 6.0:
                f *= 1.0 + mo * _exp(-t / tau)
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
    # dB of attenuation for EVEN harmonics, or None to use odd_only absolutely.
    # See series_volume(): a real stopped pipe suppresses its even harmonics,
    # it does not delete them -- measured 24 to 38 dB down on the Iowa clarinet.
    even_harmonic_db = None

    from inharmonicity import inharmonicity_coefficient_2nd_harmonic, inharmonicity_coefficient_3rd_harmonic

    # Organ registration: True on the pipe-organ families (flue/reed), whose
    # tones build a full stop-list of ranks (extra octave/fifth partial series)
    # and read a LIVE per-channel gate (drawn stops / crescendo) and swell tilt
    # at render time. False everywhere else -- those voices keep the frozen
    # attack-time channel_volume and a single harmonic series (see init_partials
    # and SynthTone.sum_values). Default off so nothing but organs changes.
    registerable = False

    # No-swell defaults. These make the block kernel's shutter arithmetic exactly
    # identity (level = 1, no HF tilt) so it agrees with shutter() below for any
    # registerable voice without a swell box. OrganProperties overrides all four.
    swell_floor      = 1.0
    swell_gain_power = 1.0
    swell_hf_max     = 0.0
    swell_hf_ref_hz  = 1500.0

    def shutter(self, freq, s):
        """Swell shutter for a registerable voice: how much a partial at `freq` is
        attenuated when the box is `s` open. Identity here -- an instrument with no
        swell (a harpsichord, a Baroque organ without a box) passes everything.
        OrganProperties overrides this with the real per-partial shutter tilt."""
        return 1.0

    # Strike/pluck point as a fraction of the speaking length. When set, mode n is
    # excited with amplitude |sin(n*pi*strike_point)| -- a comb that nulls the
    # harmonics at multiples of 1/strike_point. None = no comb (uses the legacy
    # plucked_volumes path; pipes etc.). The piano sets ~1/7 to soften the 7th.
    strike_point = None
    # True = a felt hammer, whose contact patch widens with force and fills the
    # comb notch (velocity-dependent timbre). False = a hard narrow exciter at
    # fixed force -- a plectrum -- whose notch never fills.
    strike_fills_with_force = True
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

    # Wavelength-scaled speech. A flue or reed PIPE speaks by building its
    # standing wave over a roughly fixed number of periods, so the onset (and
    # note-off) ramp grows with WAVELENGTH -- speech_cycles periods of the note
    # fundamental (1/f), bass pipes speaking slowly and trebles promptly. Added
    # on top of the fixed valve/attack floor. 0 (default) = frequency-independent
    # (struck strings and brass, whose speech is set by the excitation, not the
    # air column). See speech_time() and hammer_down/hammer_up.
    speech_cycles = 0.0

    def speech_time(self, fixed, frequency):
        """Full onset/release ramp: the fixed valve/attack floor plus, for pipes,
        speech_cycles wavelengths of the fundamental (bass speaks slowly)."""
        if self.speech_cycles > 0.0 and frequency > 0.0:
            return fixed + self.speech_cycles / frequency
        return fixed

    # --- Chiff shape vs pipe size ---------------------------------------------
    # The chiff is the edge-tone "spit" at the ONSET -- distinct from the smooth,
    # wavelength-scaled SPEECH (the amplitude build as the pipe fills). Tying the
    # chiff to the speech time makes a big pipe's chiff a long HIGH hiss (all its
    # partials jitter for the whole slow speech) -- obnoxious and unphysical. In a
    # real pipe the big mouth/cutup makes the chiff a brief, LOW "chuff": short,
    # and with its high harmonics attenuated. Two size-dependent knobs, both
    # no-ops by default (struck/brass voices unchanged), let a pipe model that:
    #   chiff_width        : chiff burst duration (s). None = use the speech fade,
    #                        as before. A pipe sets a short, capped value so the
    #                        chiff does NOT last the whole speech.
    #   chiff_width_cycles : if > 0, the burst is this many periods of the
    #                        fundamental, capped at chiff_width (bass a touch
    #                        longer than treble, but bounded -- not the full speech).
    #   chiff_harmonic_span/_power : the jet excites the LOW modes; harmonic h gets
    #                        1/(1+((h-1)/span)**power) of the chiff. None = uniform
    #                        (as before). A pipe rolls its highs off -> low chuff,
    #                        so a big pipe's high-Hz partials no longer hiss.
    # (Chiff volume already scales down with pipe size via the base_frequency/440
    # factor in wave()/the kernel -- kept.)
    chiff_width = None
    chiff_width_cycles = 0.0
    chiff_harmonic_span = None
    chiff_harmonic_power = 2.0

    def chiff_time(self, frequency, speech_fade):
        """Chiff burst duration: the speech fade by default, or a short capped,
        mildly wavelength-scaled burst when the voice sets chiff_width(_cycles)."""
        if self.chiff_width is None and self.chiff_width_cycles <= 0.0:
            return speech_fade
        w = self.chiff_width if self.chiff_width is not None else speech_fade
        if self.chiff_width_cycles > 0.0 and frequency > 0.0:
            w = min(w, self.chiff_width_cycles / frequency)
        return w

    # --- Pipe speech: inharmonic onset, harmonic sustain -----------------------
    # An open pipe's mode n sits at n*c/(2(L + 2*delta_n)). The end correction
    # delta shrinks as the wavelength approaches the pipe's radius, so the
    # effective length shortens with mode number and the upper PASSIVE resonances
    # sit sharp. Unlike a string's stiffness (which grows as h^2 without bound),
    # this SATURATES: once delta is negligible the deviation stops growing. Hence
    #     offset(h) = mode_lock_spread * (1 - 1/(1 + (h/mode_lock_knee)^2))
    # rising from ~0 at the fundamental to mode_lock_spread for high modes.
    # The oscillation is then driven and mode-locks to exact harmonics within
    # mode_lock_time, so this is purely an ONSET transient -- the steady tone is
    # harmonic. 0 = off (strings, brass, anything already modelled another way).
    mode_lock_spread = 0.0     # fractional sharpness of the high passive modes
    mode_lock_knee = 3.0       # mode number at which half the deviation is reached
    mode_lock_time = 0.035     # s: how fast the drive pulls the modes into lock

    def mode_lock_offset_for(self, harmonic):
        if self.mode_lock_spread <= 0.0 or harmonic <= 1:
            return 0.0
        x = (float(harmonic) / self.mode_lock_knee) ** 2
        return self.mode_lock_spread * (x / (1.0 + x))

    def chiff_harmonic_gain(self, harmonic):
        """Per-partial chiff weight: 1 at the fundamental, rolling off for the
        upper harmonics so a large pipe's high partials don't hiss. 1.0 (uniform)
        unless chiff_harmonic_span is set."""
        if self.chiff_harmonic_span is None:
            return 1.0
        x = (harmonic - 1.0) / self.chiff_harmonic_span
        if x <= 0.0:
            return 1.0
        return 1.0 / (1.0 + x ** self.chiff_harmonic_power)

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        """Extra detuned voices for this harmonic, as (gain_multiplier,
        detune_Hz, detune_ratio, decay_rate_dbps, start_phase_cycles).

        start_phase is 0 for a struck or plucked body, where every voice really
        does start together -- see hammer_down(), which zeroes the accumulator
        for exactly that reason. It is NOT 0 for an ensemble of separate players:
        see BowedStringProperties.unison_voices().
        """
        return [(self.unison_gain, offset, 0.0, harmonic_decay, 0.0)
                for offset in self.unison_detune]

    def voice_vibrato(self, frequency, index):
        """(depth_fraction, rate_hz, phase_rad) for one player, or None.

        index 0 is the main voice; 1..n-1 are the extras from unison_voices().
        None for anything that is one body rather than several people.
        """
        return None

    # Metres each side of the section's centre that its players occupy. 0 is one
    # point source, which is RIGHT for a piano's three strings (one hammer, one
    # bridge point) and a drum head's modes, and wrong for people in chairs --
    # so it stays 0 here and only an actual ensemble turns it on.
    section_width_m = 0.0

    def section_position_x(self, index):
        """Where player `index` sits, in metres (+ = right).

        WHY THIS MATTERS MOST IN THE BASS. Below about 500 Hz the head casts no
        shadow -- at C2 the level difference between the ears from a single
        source is 0.01 dB -- so the only binaural cue left down there is arrival
        TIME. Seven players sharing one position share one ITD exactly, and the
        section collapses to a point source in precisely the register where the
        level cue has already given up. Spread across the desks they get seven
        different ITDs (about 460 us end to end at 1.5 m), which is the cue the
        ear actually uses at those frequencies.

        Players sit at FIXED DESKS: the seating depends on the section and the
        player, never on the note, so the ensemble holds still while the music
        moves through it. Seeded off _section_salt, so two string patches are two
        different orchestras rather than the same one twice.
        """
        n = getattr(self, 'section_players', 1)
        w = self.section_width_m
        if n <= 1 or not w:
            return self.position_x
        # Spread across the desks, with a little jitter so they are not on a
        # perfect grid -- a grid of equal spacings is its own kind of comb.
        rng = _random.Random(0x5EA7 + index * 7919 + self._section_salt() * 65537)
        span = (2.0 * index / float(n - 1)) - 1.0        # -1 .. +1
        return self.position_x + w * (span + rng.uniform(-0.5, 0.5) / n)

    def section_seats(self, channel=None):
        """Per-player (left_inc, right_inc, left_delay, right_delay), or None if
        this voice is one body rather than an ensemble. Once per note, never per
        partial -- the kernel already carries per-partial ear gain and delay."""
        if not self.section_width_m or getattr(self, 'section_players', 1) <= 1:
            return None
        return [self.hrtf_at(self.section_position_x(i))
                for i in range(self.section_players)]
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

    # Head/room geometry for the Woodworth ITD + Brown-Duda head-shadow model.
    # Class attributes so hrtf_at() can place an arbitrary source (e.g. one organ
    # rank) without rebuilding the note.
    head_radius = 0.0875        # metres
    listener_distance = 2.0     # metres (a stage image, not the 0.2 m soundboard)

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
        self.gain = (self.initial_gain * db_amplitude(self.octave_gain * self.octave_position)
                     * db_amplitude(self.register_effort() + self.projection_db)
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
            # Brown-Duda structural model, driven by the source position via
            # hrtf_at() (factored out so a registerable voice can place each rank
            # independently -- see rank_position_x / _build_registered_partials).
            self.hrtf_beta = 2.0 * self.sound_speed / self.head_radius
            (self.left_incidence, self.right_incidence,
             self.left_hrtf_delay, self.right_hrtf_delay) = self.hrtf_at(self.position_x)

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

    def hrtf_at(self, position_x):
        """Per-ear (left_inc, right_inc, left_delay, right_delay) for a source at
        position_x metres (+ = right), via the Woodworth ITD on a spherical head.
        Factored out of __init__ so a registerable voice can place each rank at
        its own case position without rebuilding the note."""
        from math import atan2, sqrt, acos, cos, pi
        azimuth = atan2(position_x, self.listener_distance)
        distance = max(sqrt(position_x ** 2 + self.listener_distance ** 2), self.head_radius)
        base_delay = distance / self.sound_speed
        def woodworth(ear_azimuth):
            # incidence angle between the source ray and the ear axis
            theta = acos(cos(azimuth - ear_azimuth))
            offset = -cos(theta) if theta <= pi / 2 else (theta - pi / 2)
            return theta, base_delay + offset * self.head_radius / self.sound_speed
        li, ld = woodworth(-pi / 2)
        ri, rd = woodworth(pi / 2)
        return li, ri, ld, rd

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

    def series_volume(self, harmonic):
        """The harmonic series the vibrating body produces, before the bell."""
        if self.max_harmonic and harmonic > self.max_harmonic:
            return 0.0

        if harmonic % 2 == 0:
            # A cylindrical pipe stopped at one end resonates at odd multiples
            # only -- but "only" is the ideal, not the instrument. Measured on
            # the Iowa clarinet at C4 the evens are 24 to 38 dB down, not absent:
            # the bore is not a perfect cylinder, the bell radiates, and the reed
            # drives asymmetrically. even_harmonic_db carries that; odd_only
            # stays as the absolute case an organ's stopped rank wants.
            if self.even_harmonic_db is None and self.odd_only:
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
            # A felt hammer's contact patch WIDENS with force, filling the notch --
            # so the comb is velocity-dependent. A plectrum does not: a quill is
            # narrow and hard and plucks with a fixed force (that is why a
            # harpsichord has no dynamics), so its notch stays at full depth.
            depth = self.strike_depth
            if self.strike_fills_with_force:
                depth *= (1.0 - self.attack_volume)
            comb = (1.0 - depth) + depth * abs(_sin(harmonic * _pi * self.strike_point))
        else:
            comb = _pluck_comb(self.plucked_harmonic, self.pluck_dampening, harmonic)

        v = self.gain / (harmonic ** self.attack_dampening) * comb
        if harmonic % 2 == 0 and self.even_harmonic_db is not None:
            v *= 10.0 ** (self.even_harmonic_db / 20.0)
        return v

    def harmonic_volume(self, harmonic):
        """What leaves the instrument: the body's series, shaped by the bore."""
        v = self.series_volume(harmonic)
        if v == 0.0 or not self.bore_corner_hz:
            return v
        f0 = self.frequency_x * (2.0 ** self.octave_position)
        return v * self.bore_gain(f0 * harmonic) * self._bore_norm()

    def _bore_norm(self):
        # THE BORE IS A COLOUR, NOT A VOLUME CONTROL. A fixed roll-off applied to a
        # moving harmonic series takes energy out in proportion to how many partials
        # sit above the corner -- and that count grows with pitch, so the filter was
        # quietly imposing about 3 dB per octave of level slope on top of the
        # darkening it is there to do. Measured, every brass voice was loudest at
        # the bottom of its compass and fell 4 to 9 dB into the top; the horn was
        # 8.8 dB down at F4, which is exactly where horn parts live. That is
        # backwards -- a trumpet's high G is the loudest thing in the orchestra and
        # its low G is a weak, fuzzy note -- and it was never a modelled effect,
        # only a side effect.
        #
        # So the filter is renormalised to preserve the series' total power. It
        # still darkens the tone up high, exactly as before, but it no longer
        # decides how loud the note is. Loudness across the compass belongs to
        # register_effort_at(), where a player's behaviour is modelled.
        # ...and the same argument applies to the SERIES, not only the filter.
        # octave_dampening steepens the source's roll-off as the note rises --
        # a brass player's buzz simplifies up high, which is real and measured --
        # but a steeper roll-off is also less total power, so the voice quietly
        # got softer up the compass for a reason that was meant to be timbral.
        # Measured on the refitted bassoon: 9 dB between C3 and C4, none of it
        # intended. So the reference here is the series at the voice's OWN
        # tonal_dampening, with no octave term and no filter: colour may change
        # with register, loudness may not, and what should change with register
        # does so in register_effort_at() where it can be seen.
        if self._bore_norm_cache is None:
            f0 = self.frequency_x * (2.0 ** self.octave_position)
            ref = shaped = 0.0
            for h in range(1, (self.max_harmonic or 64) + 1):
                a = self.series_volume(h)
                if a == 0.0:
                    continue
                # the same partial as it would be at the reference register
                r = a * (h ** (self.attack_dampening - self.tonal_dampening))
                ref += r * r
                g = a * self.bore_gain(f0 * h)
                shaped += g * g
            self._bore_norm_cache = (ref / shaped) ** 0.5 if shaped > 0.0 else 1.0
        return self._bore_norm_cache

    # --- effort across the register ------------------------------------------
    # A wind player does not produce every note with the same ease. The comfortable
    # middle of the instrument speaks on very little air; the extremes cost work --
    # more pressure at the top, more volume of air at the bottom -- and a player
    # who is reaching for a note pushes to get it. So the loudness curve across the
    # compass is a U, not a flat line, and a model that makes every register equally
    # easy sounds mid-heavy for exactly that reason.
    #
    # register_effort_db is the boost at the extremes of the useful range;
    # register_center_hz is where the instrument is easiest. Off (0.0) by default:
    # this is a wind-player behaviour, not a property of every sounding body.
    projection_db = 0.0          # see HornProperties: off for everything else
    register_effort_db = 0.0
    register_center_hz = 440.0
    register_half_octaves = 1.6      # how far from centre the full boost is reached

    # ...but the U is not symmetric, and modelling it as one leaves an instrument
    # loudest at the bottom of its compass. Effort is what a note COSTS; it is not
    # what the note gives back. At the top a brass player is pushing against a
    # short, stiff air column and the bell radiates the result efficiently -- the
    # note is loud because it is high. At the bottom the same work moves a lot of
    # air slowly through a bell that radiates low frequencies poorly, and what
    # comes out is big and soft. So a trumpet's high G is the loudest thing in the
    # orchestra while its low G is weak and fuzzy, and the two are the SAME effort.
    # register_tilt_db is that dB-per-octave rise, saturating at the same distance
    # from centre the effort curve uses.
    register_tilt_db = 0.0

    # A fixed radiation corner (bore/bell). Off by default: only voices whose
    # body has a fixed geometry set it.
    bore_corner_hz = 0.0
    bore_order = 1.0
    _bore_norm_cache = None      # per-note, set on first use (see _bore_norm)

    # THE OTHER HALF OF THE BELL. bore_corner_hz is the roll-off of the highs --
    # wall losses inside the tube. But a bell is an acoustic horn, an impedance
    # transformer, and below a cutoff set by its flare it cannot radiate at all:
    # the wave reflects back down the tube instead of leaving it. So a bell is a
    # BANDPASS, and the low side is why a horn's written fundamental is nearly
    # absent while its 6th harmonic is the loudest thing in the note.
    #
    # Measured (Iowa horn, C2): the series rises 16.8 dB from h1 to h6 and then
    # plateaus. A resonance cannot do that -- a peak wide enough to cover h6-h8
    # still passes h1 -- but a second-order high-pass at the bell's cutoff does,
    # and it is what is physically there. Off (0) for everything without a bell.
    bell_cutoff_hz = 0.0
    bell_order = 2.0

    def bore_gain(self, partial_hz):
        g = 1.0
        if self.bore_corner_hz:
            g /= 1.0 + (partial_hz / self.bore_corner_hz) ** self.bore_order
        if self.bell_cutoff_hz:
            x = (partial_hz / self.bell_cutoff_hz) ** self.bell_order
            g *= x / (1.0 + x)
        return g

    def register_effort_at(self, frequency):
        if not self.register_effort_db and not self.register_tilt_db:
            return 0.0
        octaves = _log(float(frequency) / self.register_center_hz) / _log(2)
        span = self.register_half_octaves
        x = min(1.0, abs(octaves) / span)
        tilt = self.register_tilt_db * max(-span, min(span, octaves))
        return self.register_effort_db * (x * x) + tilt

    def register_effort(self):
        return self.register_effort_at(self.frequency_x * (2.0 ** self.octave_position))

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
    # dB of attenuation for EVEN harmonics, or None to use odd_only absolutely.
    # See series_volume(): a real stopped pipe suppresses them, it does not
    # delete them (measured 24-38 dB down on the Iowa clarinet).
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


# --- Harpsichord -------------------------------------------------------------
# A harpsichord is a REGISTERED instrument, exactly like the organ: the plectrum
# plucks with a fixed force, so there are no dynamics -- you change the sound by
# engaging whole CHOIRS of strings (registers), not by touch. So it reuses the
# same registerable/stop_ranks machinery, and the CC11 stop bitfield becomes the
# stop levers. COUPLING (the classic "both manuals" tutti) is simply drawing both
# 8' choirs at once, which is what a coupler mechanically does.
#
# The two 8' choirs differ by PLUCKING POINT: the lower-manual jack plucks further
# from the nut (rounder, fewer high harmonics), the upper-manual jack close to the
# nut (nasal and bright). In this model the pluck spectrum is set by
# plucked_harmonic (the harmonic where the pluck comb nulls), so each choir is a
# spectrum class borrowed via the cross-family stop mechanism.
class HarpsiBase(PluckedStringProperties):
    """Shared harpsichord physics. A plucked string released from a triangular
    displacement at fraction p of its length feeds mode n with amplitude
    ~ |sin(n*pi*p)| / n^2: a 1/n^2 rolloff times a COMB that nulls every harmonic
    at multiples of 1/p. The plucking point p is therefore the whole character of
    a harpsichord -- and, because a quill is hard and narrow and plucks at fixed
    force, the notch never fills the way a piano's felt hammer fills it
    (strike_fills_with_force = False). That fixed force is also why the instrument
    has no dynamics, which is what makes it a REGISTERED instrument.
    """
    strike_fills_with_force = False   # a quill, not a felt hammer: the comb stays deep
    strike_depth = 1.0
    tonal_dampening = 1.55            # toward the pluck's 1/n^2, kept a little bright
    octave_dampening = 0.02
    # Thin, low-tension brass/iron: much less inharmonicity than a piano's wound steel.
    inharmonicity_dynamic = False
    inharmonicity_coefficient = 0.00012
    # Plucked strings sing then die; the treble dies faster than the bass.
    decay_db = 3.2
    harmonic_decay_db = 1.5
    decay_register_slope = 0.42
    # The jack: a short bright tick as the plectrum lets go, and -- unlike an organ,
    # which cannot chiff on release -- a real THUD as the damper lands on note-off.
    chiff_volume = 0.55
    chiff_cycle = 0.30
    chiff_release = 0.8
    chiff_width = 0.012
    chiff_harmonic_span = None        # the tick follows the string's own spectrum
    attack_time = 0.002               # the pluck releases almost instantly


class HarpsiUpperProperties(HarpsiBase):
    """Upper-manual 8': the jack plucks very close to the nut, so the comb nulls
    start high and the low harmonics are weak -- the classic nasal, reedy colour."""
    strike_point = 0.045              # ~1/22 of the string
    tonal_dampening = 1.30            # brighter still


class HarpsiLuteProperties(HarpsiBase):
    """Lute (buff) stop: leather pads press the strings at the nut, killing the
    upper partials and shortening the decay -- a dry, dull pizzicato."""
    strike_point = 0.11
    tonal_dampening = 2.4
    decay_db = 11.0
    harmonic_decay_db = 3.0
    chiff_volume = 0.30


class HarpsichordProperties(HarpsiBase):
    # Balance-normalised to the rest of the instrument set (K-weighted, equal
    # velocity). Safe for the existing repertoire because every render ends in
    # a peak normalise and these voices play alone -- and the organ family is
    # shifted by ONE common factor, so the reed-versus-flue balance tuned by ear
    # survives untouched.
    initial_gain = 0.3142260371
    strike_point = 0.115              # lower-manual 8': ~1/9, round and full

    # Registers as stops (CC11 bitfield, bit i = stop_ranks[i]):
    #   bit 0 = 8' lower manual      bit 1 = 8' upper manual (nasal)
    #   bit 2 = 4' choir             bit 3 = lute/buff stop
    # COUPLED tutti = 0b0011 (both 8's) or 0b0111 (both 8's + 4') -- the full
    # "grand jeu". A single 8' (0b0001) is the plain one-choir sound.
    registerable = True
    stop_ranks = [
        ("8",       1.0, 1.00),
        ("8-upper", 1.0, 0.82, HarpsiUpperProperties),
        ("4",       2.0, 0.58),
        ("lute",    1.0, 0.50, HarpsiLuteProperties),
    ]
    crescendo_order = ["8", "8-upper", "4", "lute"]


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
    # Balance-normalised to the rest of the instrument set (K-weighted, equal
    # velocity). Safe for the existing repertoire because every render ends in
    # a peak normalise and these voices play alone -- and the organ family is
    # shifted by ONE common factor, so the reed-versus-flue balance tuned by ear
    # survives untouched.
    initial_gain = 0.07178438693
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
            # phase 0: a hammer excites all three strings in the same instant.
            voices.append((g, 0.0, ratio, harmonic_decay, 0.0))
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
    # BALANCE. Measured K-weighted at the same MIDI velocity, each voice in its
    # own comfortable register, the orchestra spanned 24.8 dB -- a flute 13.7 dB
    # over a trumpet. No score can correct that: the composer's velocities are
    # supposed to set the balance, and they cannot if the voices are not level
    # with each other to begin with. Normalised to the brass, which was the most
    # recently calibrated (against a real trumpet recording).
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
    initial_gain = 1.0 / 6784   # balance-normalised against the brass (see above)

    enharmonic_width = 0.0

    max_harmonic = 32
    # Flue pipes are not perfectly harmonic: the mouth/end correction shifts the
    # effective length with frequency (and scales with bore width), stretching the
    # partials slightly. The fixed 2nd-harmonic coefficient is the static base --
    # it places the octave partial on the "equal pythagorean" stretched octave
    # (stretch_interval = 7th root of the Pythagorean comma, so 12 pure fifths =
    # 7 stretched octaves; see inharmonicity.py).
    #
    # With inharmonicity_dynamic = True, init_partials instead recomputes the
    # coefficient per note from a frequency-dependent model
    # (inharmonicity_coefficient_for_frequency). We borrow the canonical
    # Steinway-B model below -- the SAME coefficients the hybrid tuner bends its
    # octaves along -- so under the hybrid tuning the pipe's octave partial sits
    # exactly on the tuner's stretched octave and the two lock instead of
    # beating. (Reed organ overrides the coefficient to 0 and stays phase-locked;
    # the OrganProperties family below pins this flag back to False, so neither
    # the frequency-model nor the crash-prone lookup is reached for organs/brass
    # -- only the bare blown pipe stretches dynamically.)
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic
    inharmonicity_dynamic = True
    a, b, c, d, e = Steinway.a, Steinway.b, Steinway.c, Steinway.d, Steinway.e
    inharmonicity_coefficient_func = InharmonicStringProperties.inharmonicity_coefficient_func
    inharmonicity_coefficient_for_frequency = InharmonicStringProperties.inharmonicity_coefficient_for_frequency

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
    inharmonicity_dynamic = False   # organs/reeds/brass stay phase-locked; only the bare blown pipe stretches dynamically
    tonal_dampening = 1.4
    octave_dampening = 1.0 / 8
    octave_modulo = True

    # --- Swell shutter (CC7, applied LIVE per partial in SynthTone.sum_values) ---
    # A swell box is a shutter over the whole division: as it closes it drops the
    # overall level AND muffles the highs (treble is more directional/absorbed).
    # In an additive engine that is one per-partial spectral tilt, no filter. s in
    # [0,1] from the smoothed CC7; s=1 (open) is exactly unity, so an organ with
    # no swell automation renders identically to before. Only defined here; it is
    # only ever called for registerable voices (flue/reed) that carry reg state.
    swell_floor    = 0.06     # fully-closed box still radiates ~ -24 dB (never silent)
    swell_gain_power = 1.6    # perceptual taper of overall level vs the pedal
    swell_hf_ref_hz  = 1500.0 # frequency scale of the treble damping
    swell_hf_max     = 3.5    # extra HF attenuation exponent at full close

    # An organ pipe cannot chiff on RELEASE. The chiff is the jet striking the lip
    # when wind arrives; on note-off the pallet closes, the wind stops and the
    # standing wave simply decays (release_fade already models that). Firing the
    # chiff again at note-off (the inherited blown-pipe behaviour, where a player's
    # breath does make a release noise) put a bright hiss on every release -- up to
    # +41 dB of HF on a bass note-off, since the release fade is wavelength-long.
    chiff_release = 0.0

    # Pipe ceiling (Hz): above this a drawn rank has no pipes. None = full compass
    # (today's behaviour). ~2.1 kHz caps the upperwork near c'' (MIDI 72). What
    # happens there is pipe_break_mode: 'fold' = break back an octave (energy kept,
    # the top re-colors -- authentic mixture behaviour but subtle); 'truncate' = the
    # rank simply stops (energy removed, the top audibly THINS -- "misses the top rank").
    pipe_ceiling_hz = None
    pipe_break_mode = 'fold'

    def shutter(self, freq, s):
        if s >= 1.0:
            return 1.0
        if s < 0.0:
            s = 0.0
        level = self.swell_floor + (1.0 - self.swell_floor) * (s ** self.swell_gain_power)
        hf = _exp(-(1.0 - s) * self.swell_hf_max * (freq / self.swell_hf_ref_hz))
        return level * hf

    # --- Spatial layout: the pipe case, not a keyboard --------------------------
    # A piano is one soundboard the listener faces, so its notes ride a straight
    # low-left -> high-right line (octave_width). An organ's ranks are physical
    # pipe rows SCATTERED around a room, and its chest is laid out C/C# (adjacent
    # semitones on opposite sides), so a linear keyboard is wrong. Instead, for
    # each RANK we place a source at position_x (metres, +right):
    #
    #   x = spiral_m * sin(2pi * octave_position + spiral_phase)   # helix: rotates
    #     + drift_m  * octave_position                             #   once per octave,
    #     + offset[rank]                                           #   drifts low->high
    #     + split[rank] * (+1 even key / -1 odd key)               # C/C# antiphonal
    #     + channel_pan * 4                                        # CC10 division pan
    #
    # sin(2pi*octave_position) IS the chroma circle (octave_position is log2 pitch,
    # so 2pi*octave_position advances one turn per octave); octave-related notes
    # land together (harmonically close = spatially close, the Shepard helix) while
    # the drift keeps a gentle register climb. Each footage rank adds its own case
    # offset (independent placement) and its own C/C# split depth -- 16' wide in the
    # facade towers, 8' central, upperwork spread. Fed through hrtf_at() per rank.
    spiral_spatial = True
    spiral_m     = 0.9      # metres: half-width of the per-octave rotation
    spiral_phase = 0.0
    drift_m      = 0.12     # metres/octave: residual low->high climb (helix pitch)
    # rank key -> (fixed case offset m, C/C# antiphonal depth m). The offset is the
    # DOMINANT cue -- each footage is a physically separate pipe row, spread wide
    # across the case (16' one flank, 8' centre, upperwork/mutations fanned out).
    # The C/C# split is SUBTLE: the two chest halves are adjacent, a few degrees
    # apart, so adjacent semitones only shimmer side to side, they don't alternate
    # hard L<->R (that read as a gimmick).
    rank_spatial = {
        "16":     (-1.55, 0.22),   # pedal 16': far flank, a touch of tower width
        "8":      (0.0,   0.12),   # foundation, central
        "4":      (0.95,  0.12),
        "2":      (-1.15, 0.10),
        "2-2/3":  (1.60,  0.10),
        "5-1/3":  (-1.70, 0.10),
        "flute":  (1.25,  0.12),
        "trumpet": (-1.35, 0.15),
    }
    rank_spatial_default = (0.0, 0.12)

    def rank_position_x(self, rank_key):
        """position_x (metres, +right) for one drawn rank of THIS note: the helix
        by key + the rank's fixed case offset + its C/C# antiphonal side."""
        from math import sin, pi
        op = self.octave_position
        offset, split = self.rank_spatial.get(rank_key, self.rank_spatial_default)
        parity = 1.0 if (round(12.0 * op) % 2 == 0) else -1.0
        return (self.spiral_m * sin(2.0 * pi * op + self.spiral_phase)
                + self.drift_m * op
                + offset + split * parity
                + self.channel_pan * 4.0)


class FlueOrganProperties(OrganProperties):
    # Balance-normalised to the rest of the instrument set (K-weighted, equal
    # velocity). Safe for the existing repertoire because every render ends in
    # a peak normalise and these voices play alone -- and the organ family is
    # shifted by ONE common factor, so the reed-versus-flue balance tuned by ear
    # survives untouched.
    initial_gain = 0.0001294572617
    # Flue pipes have pitched partials, so like the bare blown pipe they must
    # track whatever tuning renders them or their octaves beat. Under the hybrid
    # (Steinway-B) tuning -- the temperament for dense Baroque counterpoint --
    # re-enable the dynamic model (inherited a,b,c,d,e + coefficient function
    # from BlownPipeProperties) so the flue organ's octave partials lock to the
    # tuner's stretched octaves. OrganProperties pins this False for the family;
    # only the flue organ (pitched, like the pipe) opts back in. The reed organ
    # keeps coefficient 0 and stays harmonic / phase-locked; brass stays locked.
    # A SOUNDING pipe is a driven, mode-locked oscillator: its steady tone is
    # exactly harmonic, which is why organs are tuned with PURE octaves and never
    # stretch-tuned (a piano must stretch because its free-decaying stiff strings
    # really do ring inharmonically). The pipe's mild passive inharmonicity lives
    # in the ONSET instead -- see mode_lock_spread below.
    inharmonicity_dynamic = False
    inharmonicity_coefficient = 0.0
    # Passive modes ~0.35% sharp at the top, locking within ~40 ms. This is the
    # pipe "settling" into speech; the sustain is harmonic.
    mode_lock_spread = 0.0035
    mode_lock_knee = 3.0
    mode_lock_time = 0.040
    odd_only = False
    # A flue pipe speaks by building its standing wave, so its onset is GRADUAL
    # and scales with WAVELENGTH -- not the old fixed 0.10 s (which made trebles
    # sluggish and the bass not gradual enough). A small fixed floor (jet transit)
    # plus speech_cycles periods of the fundamental: low C (~65 Hz) speaks in
    # ~70 ms, middle C in ~25 ms, the top in ~12 ms.
    chiff_min_valve_time = 0.004
    chiff_max_valve_time = 0.008
    speech_cycles = 4.0

    # Chiff = the pipe SPEAKING. A pipe can only radiate at the frequencies it
    # resonates, so the onset transient is shaped by the same modes as the steady
    # tone: we let the chiff follow the pipe's own harmonic_volume (it is already
    # multiplied by each partial's amplitude) and impose NO extra rolloff. That is
    # the physical model AND it self-voices per stop -- the dark Flute gets a dark
    # chuff, a principal a brighter spit, the Mixtur brighter still, with no
    # per-voice knobs. Because the chiff now matches the tone instead of being an
    # independent hiss, it can also last the whole SPEECH (width = None/0 cycles):
    # one transient blooming into steady tone, bass slow and treble prompt.
    chiff_width = None
    chiff_width_cycles = 0.0
    chiff_harmonic_span = None
    chiff_volume = 1.3

    # Upperwork breaks back near c'' -- the top of the manual loses the 2'/mixtures,
    # so an ascending run re-colors at the peak instead of climbing (see OrganProperties).
    pipe_ceiling_hz = 2100.0

    # --- Stop list (drawn via CC11 bitfield / CC4 crescendo) ---
    # A principal chorus. Each rank is a full harmonic series placed a footage
    # interval away on the note's OWN inharmonic-stretched grid (see
    # init_partials): ratio is the frequency multiple (8'=1, 4'=octave up=2,
    # 2'=+2 8ves=4, 2 2/3'=twelfth=3, 16'=octave down=0.5, 5 1/3'=fifth=1.5).
    # Because a 4' fundamental (h=2) lands exactly on the 8's stretched 2nd
    # partial, the ranks LOCK by construction under the hybrid tuning. gain is
    # the pyramid weight (8' loudest, upperwork softer, quints softest). Bit i
    # of the CC11 mask = stop_ranks[i]; default drawn set is 8'-only.
    registerable = True
    stop_ranks = [
        ("8",     1.0, 1.00),
        ("4",     2.0, 0.72),
        ("2",     4.0, 0.55),
        ("2-2/3", 3.0, 0.40),
        ("16",    0.5, 0.80),
        ("5-1/3", 1.5, 0.34),
    ]
    # Rollschweller draw order for the CC4 crescendo pedal: brighten, then weight.
    crescendo_order = ["8", "4", "2", "2-2/3", "16", "5-1/3"]


class ReedOrganProperties(OrganProperties):
    # A chorus reed is present but should NOT dominate. Equal-PEAK calibration
    # (1/2200) left the spiky odd-only reed reading ~1-2 dB *under* the flue on
    # sustains, so it wanted lifting; but its high crest factor means a big lift
    # makes the ATTACKS poke over the flue ("over-bold, trumpet-like"). 1/2000 is
    # the balance point -- sustains close to the flue, peaks not jumping out --
    # paired with a gentler front (below) so the per-note attack doesn't stab.
    # Balance-normalised to the rest of the instrument set (K-weighted, equal
    # velocity). Safe for the existing repertoire because every render ends in
    # a peak normalise and these voices play alone -- and the organ family is
    # shifted by ONE common factor, so the reed-versus-flue balance tuned by ear
    # survives untouched.
    initial_gain = 0.0001967750377
    chiff_cycle = 0.0
    chiff_volume = 0.0
    chiff_min_valve_time = 0.0
    chiff_max_valve_time = 0.0

    # Reed tongues top out lower than flue pipes (short high resonators go weak/
    # unstable), so a reed's upperwork (a 4' clairon, a reed mixture) breaks back
    # sooner. The 8'/16' foundation and a solo reed line keep full compass (only
    # ratio >= 2 breaks -- see _build_registered_partials).
    pipe_ceiling_hz = 1600.0

    # A reed speaks promptly (the tongue, not a slow air column), but with a
    # PRESSURE-BUILD swell: as the pallet opens, wind pressure in the boot rises,
    # the tongue over-speaks for an instant, then settles as the pipe reaches
    # steady state -- the reed's "front", like a gentle trumpet attack. Modelled
    # as a short wavelength-scaled onset ramp (pressure building) plus a decay
    # front that blooms to the peak and settles ~2 dB into the sustain and holds
    # (pressure released), the upper harmonics settling a touch faster (the edge
    # blooms on the attack). Without this the reed onset is an instant step -- the
    # "fake" attack. Much gentler than the brass front (decay_db 18, sustain 0.6).
    attack_time = 0.004         # jet/tongue floor; speech_cycles adds the wavelength term
    speech_cycles = 2.0         # reeds speak ~half the flue's ramp
    # The tongue is a stiffer, more decisive driver than a flue jet: the modes lock
    # sooner and from a smaller initial spread.
    mode_lock_spread = 0.0020
    mode_lock_knee = 3.0
    mode_lock_time = 0.022
    decay_db = 5.0              # gentle front (was 9): a soft bloom, not a stab
    harmonic_decay_db = 2.5     # upper harmonics bloom then settle a little faster
    harmonic_decay_dampening = 0.0
    sustain_level = 0.86        # blooms to the peak, releases ~1.3 dB, then holds

    # A reed chorus: 8' with a 16' for gravity and a 4' clairon on top. Same
    # live-gate mechanism as the flue; bit i of the CC11 mask = stop_ranks[i].
    registerable = True
    stop_ranks = [
        ("8",  1.0, 1.00),
        ("16", 0.5, 0.72),
        ("4",  2.0, 0.55),
    ]
    crescendo_order = ["8", "16", "4"]
    odd_only = True
    inharmonicity_coefficient = 0.0


class FormantBody:
    """A body with fixed resonances: the harmonics slide through, the peaks stay.

    A resonator does not care what note is being played. Its peaks sit at fixed
    frequencies, so a partial is loud when it happens to land on one -- which is
    why a bassoon's fourth harmonic can be 19 dB ABOVE its fundamental at C3 and
    the same instrument sounds like a bassoon two octaves up. Any voice whose
    spectrum peaks somewhere other than the fundamental needs this; a monotonic
    1/n^d rolloff cannot express it at all, because it makes h1 the strongest
    partial by construction.

    Rides on bore_gain, so it inherits that filter's power normalisation: moving
    a formant changes the colour, never the loudness. formants are
    (centre Hz, bandwidth Hz, amplitude); formant_floor is what the body passes
    between its resonances, and bore_corner_hz still rolls the top off above them.
    """
    formants = ()
    formant_floor = 0.06

    # ANTIRESONANCES. A tube with a side branch -- a tonehole, a register vent,
    # the bassoon's long wing joint -- has frequencies it will NOT pass: the
    # branch presents a short to ground and the partial that lands there is
    # cancelled. Poles alone cannot make a dip; a formant list can only add.
    # Measured on the Iowa bassoon at C3, the 5th harmonic sits 33 dB BELOW its
    # neighbours (-13.7 between +19.3 and -2.1), which is a zero, not the gap
    # between two peaks. (centre Hz, bandwidth Hz, depth 0..1).
    antiformants = ()

    def bore_gain(self, partial_hz):
        g = self.formant_floor
        for centre, bandwidth, amp in self.formants:
            d = (partial_hz - centre) / (bandwidth * 0.5)
            g += amp / (1.0 + d * d)
        for centre, bandwidth, depth in self.antiformants:
            d = (partial_hz - centre) / (bandwidth * 0.5)
            g *= 1.0 - depth / (1.0 + d * d)
        return g / (1.0 + (partial_hz / self.bore_corner_hz) ** self.bore_order)


class SectionMixin:
    """Several PLAYERS on one part, rather than one player made wide.

    Factored out of BowedStringProperties so it is not bolted to a bowed
    spectrum. A section is a way of being played, not a timbre: massed brass and
    massed strings share the arithmetic -- N stacks a few cents apart, each with
    its own start phase, its own vibrato and its own chair -- and share none of
    the bore, bell or excitation. Mix it into whatever voice is doing the
    playing.

    Neutral by default (one player, no spread), so mixing it in changes nothing
    until a class sets its numbers.

    section_vibrato_cents MUST STAY NON-ZERO on any class that turns this on.
    voice_vibrato() returns None when it is falsy, so at 0 a player has no depth,
    rate OR phase of their own -- and the live mod wheel takes its per-player
    proportions from exactly that, so a resting depth of 0 makes a wheel-up write
    one flat value over the whole section. Shallow is fine, absent is not.
    """
    section_players = 1                # 1 = not a section; nothing below applies
    section_spread_cents = 0.0         # +/- pitch spread across the players
    section_vibrato_cents = 0.0        # +/- depth, per player (see the note above)
    section_vibrato_hz = (4.6, 6.4)    # each player at their own rate
    # Milliseconds of ENTRY SCATTER: players do not start together, and how far
    # apart they are is set against the onset ramp they are scattering inside
    # (40 ms for the brass section, 100 ms for the strings), not in the
    # abstract. Drawn 0..this, never negative, as timing_jitter_seconds is --
    # an early player would have to start before the note.
    section_onset_ms = 0.0

    def section_onsets_at(self, frequency):
        """Per-player entry offsets in seconds. None when this voice is not a
        section. See section_onset() for why it is keyed on the pitch."""
        n = getattr(self, 'section_players', 1)
        w = getattr(self, 'section_onset_ms', 0.0)
        if n <= 1 or not w:
            return None
        midi = int(round(69 + 12 * _log(float(frequency) / 440.0) / _log(2)))
        salt = self._section_salt()
        return [section_onset(salt, midi, i, w) for i in range(n)]

    def _section_salt(self):
        """A stable per-voice-class number, so two SECTIONS are two sections.

        The seeds below key on pitch, which is what makes a note's players the
        same players every time it is played. But two different string patches
        doubling the same note then drew the SAME spread, the same phases and the
        same vibrato -- so the fourteen voices were seven exactly coincident
        pairs. Coincident voices add coherently (+6 dB, not +3) and the second
        section reinforces the first's comb instead of smearing it: louder than
        the score asks, and still a phaser. Ben's two patches, "String marcado"
        (prog 48) and "String dolce" (prog 49), double each other note for note.

        crc32 of the class name, not hash(): hash() of a str is salted per
        process, and this must be identical in both renderers and every run.

        Memoised per class, and crc32 imported at module scope: this used to do
        the import and the checksum on every call, and it is called once per
        player per harmonic -- 442856 times to build one four-minute piece.
        """
        cls = type(self)
        got = _SECTION_SALT.get(cls)
        if got is None:
            got = _crc32(cls.__name__.encode()) & 0xFFFF
            _SECTION_SALT[cls] = got
        return got

    def voice_vibrato(self, frequency, index):
        """Memoised per (class, note, player): it takes no harmonic argument and
        never did, yet the build calls it once per harmonic per player -- 387499
        times for one piece, each one seeding a fresh Mersenne Twister."""
        if not self.section_vibrato_cents:
            return None
        midi = int(round(69 + 12 * _log(float(frequency) / 440.0) / _log(2)))
        key = (type(self), midi, index)
        got = _VIBRATO_CACHE.get(key)
        if got is None:
            rng = _random.Random(0x71B0 + midi * 64 + index + self._section_salt() * 8191)
            depth = (2.0 ** (self.section_vibrato_cents / 1200.0) - 1.0) * rng.uniform(0.7, 1.0)
            got = (depth, rng.uniform(*self.section_vibrato_hz),
                   rng.uniform(0.0, 6.283185307179586))
            _VIBRATO_CACHE[key] = got
        return got

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        """The other players: section_players - 1 extra stacks, each a few cents
        off. Seeded per note (as the piano seeds its unisons) so a given pitch is
        always the same section but no two pitches share a spread -- otherwise
        every note detunes identically and the section reads as one chorused
        voice. The seed is per NOTE, so all of a note's partials agree on where
        each player is, which is what makes the spread scale with the partial.
        """
        n = self.section_players
        if n <= 1:
            return super().unison_voices(frequency, harmonic, harmonic_decay)
        midi = int(round(69 + 12 * _log(float(frequency) / 440.0) / _log(2)))
        # The spread and the phases are per NOTE, not per harmonic -- that is the
        # whole point of seeding on the pitch -- so they are drawn once and kept.
        # Only harmonic_decay varies down the series, and it is passed in.
        key = (type(self), midi)
        cached = _SECTION_CACHE.get(key)
        if cached is not None:
            return [(1.0, 0.0, ratio, harmonic_decay, phase) for ratio, phase in cached]
        rng = _random.Random(0x5EC0 + midi + self._section_salt() * 65537)
        cents = [rng.uniform(-self.section_spread_cents, self.section_spread_cents)
                 for _ in range(n - 1)]
        # Straddle the written pitch. A free draw leaves the section's centre a
        # cent or two off, which is the whole section playing flat against the
        # winds; the main voice sits at 0, so the extras must average to it.
        mean = sum(cents) / len(cents)
        cents = [c - mean * (n - 1) / float(n) for c in cents]
        # AND THEY DO NOT START IN PHASE. Seven equal voices launched from phase 0
        # sum coherently at the onset -- 7x, not sqrt(7)x -- and only drift apart
        # as the detuning accrues phase. Measured, that put a +9.3 dB spike on the
        # front of every note (a single voice's peak-over-sustain is +0.3 dB, which
        # is what a bowed string should be) and left the voices sweeping through a
        # synchronised comb as they separated: an attack like a hammer and an
        # audible phaser, neither of which is a string section. The piano's own
        # note about its unisons says the same thing -- equal voices beating
        # together go "to deep nulls (a phaser)" instead of shimmering.
        #
        # A hammer strikes three strings at one instant; seven players do not
        # share an instant. Give each its own start and the sum is incoherent
        # from the first sample -- the right attack and the right steady state.
        #
        made = [(2.0 ** (c / 1200.0) - 1.0, rng.random()) for c in cents]
        _SECTION_CACHE[key] = made
        return [(1.0, 0.0, ratio, harmonic_decay, phase) for ratio, phase in made]


class BrassProperties(OrganProperties):
    # A DRIVEN AIR COLUMN IS EXACTLY HARMONIC. The reed, or the lips, lock every
    # mode to the fundamental -- the same reason FlueOrganProperties and
    # ReedOrganProperties carry B = 0. Inheriting the piano's stretch put partial
    # 8 sixty-nine cents sharp here (a hundred and two for the blown pipe), so the
    # upper partials beat against each other and against the other players. That
    # beating is heard as shimmer, and trimming the breath noise cannot remove it,
    # because it is not noise.
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    # ...but the ONSET is not locked yet. Before the lips and the air column
    # agree, the modes sit off their harmonic positions and pull in over the
    # first few tens of milliseconds -- the same model the organ pipes use, and
    # the reason a brass attack has its characteristic bite. The machinery was
    # already here (knee and time set) with the spread left at zero, so the
    # inharmonicity was being carried by a STATIC stretch on the sustain instead,
    # which is where it does not belong.
    mode_lock_spread = 0.0030
    # EFFORT ACROSS THE COMPASS. A player does not produce every note with the
    # same ease: the middle of the horn speaks on very little air, while the top
    # costs pressure and the bottom costs volume, and a player reaching for
    # either pushes to get there. Modelling every register as equally easy makes
    # the middle the loudest thing in the section, which is not what a section
    # sounds like. Centre is the comfortable part of the trumpet's staff.
    # THE BORE AND BELL ARE A FIXED FILTER. A brass instrument radiates through a
    # bell whose behaviour is set by its geometry, not by the note being played,
    # so the spectral envelope stays put while the harmonics move through it. Play
    # higher and fewer partials fall under the corner -- the tone darkens by
    # itself, which is exactly what a tuba does up high and why a big bore darkens
    # sooner than a small one. Modelled as a fixed roll-off rather than an
    # octave-dependent dampening, because the cause is the instrument's geometry
    # and not the register.
    bore_corner_hz = 2400.0
    bore_order = 1.2

    register_effort_db = 3.0
    register_tilt_db = 1.8        # see register_tilt_db: brass projects as it rises
    register_center_hz = 370.0
    register_half_octaves = 1.5
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
    chiff_volume = 0.06
    # A brass attack is a transient, not a burst of noise. At 2.9 the first 50 ms
    # measured as spectral flatness 0.41 -- essentially noise -- against 0.000 for
    # the sustain, so the note began fuzzy and then turned into a pure tone. That
    # gap IS the "difference between attack and sustain": not level (only 3 dB)
    # and not brightness (the sustain is actually brighter), but character.
    #
    # A held note is not sterile, but sustain_jitter is the wrong instrument for
    # that: it modulates each partial's PHASE, which reads as shimmer or chorus,
    # where a real player's sustain noise is broadband breath. Measured against
    # ~/Documents/trumpet.wav the real sustain is flatness 0.030 -- but reaching
    # that number with phase jitter buys the number and the wrong sound. Kept to
    # a trace.
    sustain_jitter = 0.0050             # hard tongued attack
    chiff_min_valve_time = 0.015
    chiff_max_valve_time = 0.04    # fast, tight onset


class DarkBrassProperties(BrassProperties):
    """Conical-bore brass (French horn, tuba): the continuous flare damps the
    upper harmonics into a round, mellow tone, and conical instruments speak
    less abruptly -- a rounder, slower attack with a gentler bloom."""
    # BALANCE. Measured K-weighted at the same MIDI velocity, each voice in its
    # own comfortable register, the orchestra spanned 24.8 dB -- a flute 13.7 dB
    # over a trumpet. No score can correct that: the composer's velocities are
    # supposed to set the balance, and they cannot if the voices are not level
    # with each other to begin with. Normalised to the brass, which was the most
    # recently calibrated (against a real trumpet recording).
    initial_gain = 1.0 / 5850
    tonal_dampening = 1.35         # fast rolloff = few highs, dark/round
    harmonic_decay_db = 2.0        # gentle brightness bloom
    decay_db = 13.0
    sustain_level = 0.7            # subtle front
    chiff_volume = 0.05
    sustain_jitter = 0.0045
    bore_corner_hz = 700.0        # a huge bore and bell: darkens far sooner
    # Measured (Iowa tuba, C2): the series rises 15.6 dB to h5 (330 Hz). A tuba's
    # bell is enormous but 65 Hz is still below what it radiates well.
    bell_cutoff_hz = 390.0
    register_effort_db = 3.5      # extremes still cost more air, but less steeply
    # A tuba is the exception in the family: its power really does live at the
    # bottom, and the top of the instrument thins rather than blooms. Tilted, but
    # only half as far as the trumpet and the horn.
    register_tilt_db = 1.0
    register_center_hz = 130.0
    register_half_octaves = 1.5   # see BrightBrass: air keeps moving on a held note             # soft tongue, rounder speech
    chiff_min_valve_time = 0.03
    chiff_max_valve_time = 0.075   # slower, rounder onset


# --- Cross-family stops: a Flute on the flue (19) and a Trumpet on the reed (20).
# A stop_ranks entry may carry a 4th field, a "spectrum" property class, whose
# harmonic_volume shapes THAT rank's amplitudes -- borrowing only the timbre. The
# inharmonicity (the grid the rank locks to), the envelope, and the decay stay the
# BASE organ's: flue-dynamic (hybrid-lock) under the flute, reed-harmonic under the
# trumpet. So a drawn flute/trumpet is a genuinely different colour that still locks
# like every other stop. Appended here (not inline) because BrightBrass is defined
# after ReedOrgan. Flute = flue bit 6; Trumpet = reed bit 3.
FlueOrganProperties.stop_ranks = FlueOrganProperties.stop_ranks + [("flute", 1.0, 0.60, BlownPipeProperties)]
# Mixtur III -- one drawstop, several very high ranks (1 1/3' + 1' + 2/3'). They sit
# far above the pipe ceiling, so the break-back folds them back constantly to stay
# under it: THAT is a Mixtur's "composition", and why its shimmer re-colors up the
# keyboard instead of turning shrill. A COMPOUND rank: ratio is a list of the ranks'
# footages; the build loops expand it, each sub-rank breaking back on the note's grid
# (so all stay hybrid-locked). Drawn by bit 7 (14-bit stop word: CC11 | CC43<<7).
FlueOrganProperties.stop_ranks = FlueOrganProperties.stop_ranks + [("mixture", [6.0, 8.0, 12.0], 0.28)]
# Trumpet rank gain 0.42: the climax Trompette read too bold; trimmed so the
# peroration crowns without blaring (also relieves the dense close's headroom).
ReedOrganProperties.stop_ranks = ReedOrganProperties.stop_ranks + [("trumpet", 1.0, 0.42, BrightBrassProperties, True)]


# --- Broad melodic buckets (generic; specialize per-instrument later) ---

class TrumpetProperties(BrightBrassProperties):
    """The Bb trumpet, fitted to the Iowa recordings across three registers.

    BrightBrassProperties is left as it was, because it is also the spectrum the
    organ's Trumpet stop borrows -- changing it would move the whole Bach corpus.
    This class is GM 56/59 only.

    The correction is large and it is a SIGN error, not a tuning error. The old
    model had the series falling from the fundamental (-4.4 dB at h2, -12.4 by
    h6); a real trumpet RISES (+4.5 at h2, +17.3 by h6 at E3). Mean error across
    E3, C4 and C5 was 20.0 dB. The earlier calibration against Ben's own trumpet
    recording was real, but it measured attack character, noise and brightness --
    never the harmonic tilt, which was inverted the whole time.
    #
    Same two mechanisms as the horn: a bell that will not radiate below its
    cutoff, and a source that simplifies as the player goes up. Fitted on E3 and
    C5, the extremes, and checked against C4 in the middle: 4.3 dB mean across
    all three, against 20.0 for the old model.
    """
    initial_gain = 1.0 / 4060    # re-levelled after the refit
    bell_cutoff_hz = 1600.0
    bell_order = 3.0
    bore_corner_hz = 1800.0
    tonal_dampening = 2.00
    octave_dampening = 0.25


class TromboneProperties(BrightBrassProperties):
    # BALANCE. Measured K-weighted at the same MIDI velocity, each voice in its
    # own comfortable register, the orchestra spanned 24.8 dB -- a flute 13.7 dB
    # over a trumpet. No score can correct that: the composer's velocities are
    # supposed to set the balance, and they cannot if the voices are not level
    # with each other to begin with. Normalised to the brass, which was the most
    # recently calibrated (against a real trumpet recording).
    initial_gain = 1.0 / 5468
    """Tenor trombone: the trumpet's bright brass, but an octave lower and with a
    larger bore.

    It had been sharing BrightBrassProperties outright, which put the TRUMPET's
    comfortable centre (370 Hz) on an instrument that lives an octave below it --
    so the trombone's ordinary register looked to the effort curve like a trumpet
    straining at the bottom and was boosted 3 dB throughout. Its own centre and a
    lower bore corner fix both the level and the colour.
    """
    register_center_hz = 175.0     # around F3, the middle of the tenor's staff
    bore_corner_hz = 1600.0        # larger bore than a trumpet: darker
    # Measured (Iowa, C3): the 3rd harmonic at 393 Hz is 7.5 dB above the
    # fundamental -- the same bell high-pass as the horn, at a higher cutoff
    # because the bore is narrower.
    bell_cutoff_hz = 230.0


class HornProperties(DarkBrassProperties):
    # BALANCE. Measured K-weighted at the same MIDI velocity, each voice in its
    # own comfortable register, the orchestra spanned 24.8 dB -- a flute 13.7 dB
    # over a trumpet. No score can correct that: the composer's velocities are
    # supposed to set the balance, and they cannot if the voices are not level
    # with each other to begin with. Normalised to the brass, which was the most
    # recently calibrated (against a real trumpet recording).
    initial_gain = 1.0 / 4648
    """French horn: dark like the tuba's family, but it plays where a trumpet does.

    Sharing DarkBrassProperties gave it the TUBA's centre of 130 Hz, so the horn's
    normal treble-staff register read as a tuba reaching high and was boosted by
    2 dB. The horn is dark because of its narrow conical bore and backward bell,
    not because it is low.
    """
    # No projection term. A horn's backward bell and its use in sections are real,
    # but compensating for them on the voice put it ahead of the score: monocas4,
    # which is balanced more evenly, and softorch both came out horn-heavy. The
    # rest of the set is normalised to equal loudness at equal velocity and the
    # horn now is too -- balance belongs in the CC7 of the piece, not here.
    # The horn is dark, not a tuba: it blooms upward like the rest of the brass,
    # so it takes the family's tilt back off DarkBrass's tuba-shaped 1.0.
    register_tilt_db = 1.8
    register_center_hz = 262.0     # around C4, the horn's comfortable middle
    bore_corner_hz = 1100.0        # dark, but nothing like a tuba
    # MEASURED, and the measurement overturned two guesses in a row.
    #
    # Iowa horn at C2: the series RISES 16.8 dB from h1 to h6 and then plateaus,
    # where this model had it falling monotonically. A formant cannot do that --
    # any peak wide enough to cover h6-h8 still passes h1 -- so the first fix was
    # a bell high-pass, which is the real physics: below the flare's cutoff the
    # wave reflects back down the tube instead of radiating.
    #
    # But fitted at C2 alone, that bell FAILED on held-out data: it predicted a
    # rising series at C4 where the real horn at C4 falls away steeply (+1.5 at
    # h2 down to -37.0 at h7), 23.6 dB rms wrong. A fixed filter cannot give two
    # different tilts at the same frequencies, so the tilt is not all filter --
    # the SOURCE changes with register. A player's buzz is harmonically rich down
    # low and nearly sinusoidal up high, which is what octave_dampening is for.
    #
    # Fitted jointly to C2 and C4: 3.3 dB rms across BOTH, against 23.6 for the
    # bell alone. Bell 650 Hz at 3rd order, and a source rolloff that steepens by
    # 0.60 per octave.
    bell_cutoff_hz = 650.0
    bell_order = 3.0
    bore_corner_hz = 900.0
    tonal_dampening = 3.25
    octave_dampening = 0.60


class BrassSectionProperties(SectionMixin, TromboneProperties):
    """GM 61, Brass Section: several players, not one player made loud.

    It was mapped to a single TromboneProperties -- the right weight, but one
    instrument. A section is a way of being played, so the same machinery the
    string sections use applies here over a brass spectrum: N stacks a few cents
    apart, each with its own start phase, its own vibrato and its own chair.

    Not the same numbers as the strings, though, because it is not the same
    ensemble:

      - FIVE players, not seven. A GM brass section is a punchy unison of a few
        trumpets and trombones, not a desk-doubled orchestral body.
      - TIGHTER pitch spread. Brass players hear beats against each other very
        strongly on a sustained tone and lock to them; a string section, spread
        across more desks and bowing rather than buzzing, stays looser.
      - MUCH less vibrato. Orchestral brass plays a section passage nearly
        straight, where a string section never does. 2.5 cents is a shimmer that
        keeps the beat rates wandering, which is what it is there for -- and it
        must not be zero (see SectionMixin).
      - NARROWER on the stage. Brass sit in a block; strings spread across the
        front.

    Known gap: the players share an attack instant. A real section's entries
    scatter by a few milliseconds, and brass scatter more than strings, but
    attack_jitter is per NOTE rather than per player and there is no per-player
    time offset in the partial table to hang it on.
    """
    section_players = 5
    section_spread_cents = 5.0
    section_vibrato_cents = 2.5
    section_vibrato_hz = (5.0, 6.6)
    section_width_m = 0.9
    # 6 ms inside a 40 ms onset -- about 15% of the ramp, which is a real entry
    # rather than sloppiness. Brass scatter less than strings in absolute terms
    # and it shows far more, because the ramp they scatter inside is 2.5x shorter.
    section_onset_ms = 6.0
    # /sqrt(players), exactly as the string sections do it: the players are at
    # different pitches, so they are incoherent and add in POWER. This keeps a
    # brass SECTION at the same calibrated loudness as the single trombone it
    # replaces, so the equal-velocity balance across the orchestra survives.
    initial_gain = TromboneProperties.initial_gain / (section_players ** 0.5)


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


class BowedStringProperties(SectionMixin, BlownPipeProperties):
    """Sustained bowed string: full harmonic series with a sawtooth-ish
    1/n tilt, no chiff, gentle onset. Covers solo strings (violin, viola,
    cello, contrabass), string/synth ensembles, choir/voice pads, and
    sustained synth leads/pads as a broad bucket. This is the brighter
    'first' section; BowedStringSecond is the darker companion."""
    odd_only = False
    # BALANCE. Measured K-weighted at the same MIDI velocity, each voice in its
    # own comfortable register, the orchestra spanned 24.8 dB -- a flute 13.7 dB
    # over a trumpet. No score can correct that: the composer's velocities are
    # supposed to set the balance, and they cannot if the voices are not level
    # with each other to begin with. Normalised to the brass, which was the most
    # recently calibrated (against a real trumpet recording).
    section_players = 7            # a section's character, not its headcount
    section_spread_cents = 6.0     # +/- : an orchestral section's pitch spread
    # /sqrt(players): the voices are at different pitches, so they are incoherent
    # and add in POWER, not amplitude. Dividing here keeps the section at exactly
    # the loudness the equal-velocity balance was calibrated to with one voice --
    # and reads section_players, so raising the headcount cannot change the level.
    initial_gain = 1.0 / 9381 / (section_players ** 0.5)
    # A SECTION IS PLAYERS, NOT JITTER. This used to claim section shimmer from a
    # small sustained phase jitter -- "broader per-partial band, no amplitude
    # wobble" -- and measurement says it never did that. The jitter applies the
    # SAME phase-deviation magnitude to every partial, but a section's spread is
    # a spread in PITCH, so a player δ cents away puts partial n at n·δ: the band
    # must grow with the partial, and this one did not. And the deviation is
    # small (0.19 rad mean), so the jittered copy stayed nearly in phase with the
    # partial it copied. Turning sustain_jitter from 0.3 to 0 moved the skirt
    # around every partial by nothing at all and the loudness by 0.87 dB -- so
    # the whole mechanism was a coherent level bump wearing a shimmer's name,
    # and part of why the strings sat louder than the score asked for.
    #
    # The fast kernel makes the honest version affordable: render the players.
    # Each is a full harmonic stack a few cents off its neighbours, so the
    # detuning IS in pitch and every partial's spread scales with n for free,
    # and the beating between them is real beating rather than a modulation
    # applied to one voice. unison_voices() below is the piano's own machinery,
    # which both renderers already understand.
    chiff_cycle = 0.06          # phase-deviation magnitude (small = subtle)
    # NO CHIFF. This class's own docstring has said "no chiff" since it was
    # written; c9b648c kept chiff_volume at 0.5 on the strength of a comment --
    # "still wanted on the ATTACK: bow scrape is real" -- that was an assertion,
    # not a measurement. Measured: it adds a FLAT +0.3 to +0.5 dB in every band
    # from 125 Hz to 8 kHz, which is not what a bow scrape looks like, and the
    # difference signal sits 53 dB below the chord. It also cost the whole
    # polyphonic attack: a six-note chord ran 2.5 ms a block against a 2.67 ms
    # budget while it spoke, and 0.85 ms after -- the per-sample hash and
    # sincosf in the kernel's jitter branch, on every partial. What it was
    # standing in for -- the incoherence of several players not starting
    # together -- is now modelled, by seven players with their own phases,
    # vibratos and chairs. Voices where the noise IS the sound keep theirs:
    # snare 3.0, brass 2.6, breath and seashore 2.4, flue organ 1.3.
    chiff_volume = 0.0
    chiff_release = 0.0
    sustain_jitter = 0.0        # the held note is the players now, not a jitter
    chiff_min_valve_time = 0.04
    chiff_max_valve_time = 0.10

    max_harmonic = 40
    # A BOWED STRING IS HARMONIC. The bow's Helmholtz motion forces the string
    # into exact periodicity -- stiffness inharmonicity is a FREE-vibration
    # effect, which is why it belongs to the piano and not here. The 0.0 below
    # has been dead since it was written: BlownPipeProperties sets
    # inharmonicity_dynamic = True, and blockrender (and the reference) answer
    # that by OVERWRITING the coefficient with
    # inharmonicity_coefficient_for_frequency(f0). Measured on a rendered D4,
    # the partials came out at ratios 5.02, 8.10, 11.27, 13.45, 19.20 -- a
    # quadratic stretch of B ~ 4e-4, which is a piano bass string. The Iowa
    # violin's partials sit inside a +/-3% window at every harmonic up to 16.
    inharmonicity_dynamic = False
    inharmonicity_coefficient = 0.0

    # THE BODY. A bowed string is a sawtooth -- amplitude ~ 1/n, forty partials of
    # it -- but you never hear the string. You hear a wooden box radiating it, and
    # a box with a bridge stops radiating efficiently above the bridge hill, a
    # couple of kHz up. This voice had no body at all (bore_corner_hz = 0), so it
    # radiated 13 kHz as perfectly as it radiated 330.
    #
    # That is fine for ONE string and ruinous for a section. A player d cents away
    # puts harmonic n off by n*d, so at +/-6 cents the 16th partial is spread
    # +/-96 cents and the 40th +/-240: measured, from the 16th up NONE of the
    # energy is still within +/-7 cents of its partial. The top of the series
    # stops being partials and becomes a continuous noise bed -- 5 to 13 kHz, only
    # ~25 dB below the fundamental, sitting exactly where it masks everything else
    # in the orchestra. Ben heard it as the strings obscuring the mix.
    #
    # Rolling the body off cuts that bed by 14 dB and costs no loudness at all
    # (bore_gain is power-preserving: it is a colour, not a volume control), which
    # is the point -- the strings were not too loud so much as too WIDE.
    bore_corner_hz = 3000.0
    bore_order = 2.0

    # ...AND THEY DO NOT HOLD THEIR PITCH. Static detunes beat at FIXED rates
    # forever: seven voices held exactly apart form a comb whose notches march at
    # constant speed, which is a phaser, and no starting phase can fix it because
    # the rates themselves never change. Every real player has a vibrato, so the
    # beat rates wander and never settle into a pattern. Narrow on purpose --
    # this is a section's collective warmth, not a soloist's expressive vibrato.
    # Spread the desks. Wide on purpose: this is the cue that still works in the
    # bass, where the head-shadow one does not.
    section_width_m = 1.5
    # 12 ms of entry scatter inside a 100 ms bow: a string section is looser
    # than a brass one, but its slow onset hides most of it either way.
    section_onset_ms = 12.0
    # KEEP THIS NON-ZERO. voice_vibrato() returns None when it is falsy, so at 0
    # a player has no depth, no rate and no phase of their own -- and the live
    # mod wheel takes its per-player proportions from exactly that, so a resting
    # depth of 0 makes a wheel-up write one flat value over the whole section
    # again (measured: 7 distinct depths at any rest > 0, 1 at rest = 0). Shallow
    # is fine, absent is not. 5 cents rests as a shimmer and the wheel deepens it
    # to 35-45, which is where real expressive string vibrato sits.
    section_vibrato_cents = 5.0        # +/- depth
    section_vibrato_hz = (4.6, 6.4)    # each player at their own rate

    # 1/n-ish spectrum: brighter than an organ, no octave-modulo steps
    tonal_dampening = 1.0
    octave_dampening = 0.05
    octave_modulo = False


class BowedStringSecondProperties(BowedStringProperties):
    """The SLOW string section (GM String Ensemble 2).

    General MIDI only gives the two ensembles names, so the reading everyone
    actually implements is the Roland SC-55's, where 48 is `Strings` and 49 is
    `SlowStr` -- the difference is the BOW, not the tone colour. 49 is the pad:
    a slow draw you lay underneath something, where 48 speaks promptly enough to
    play a line. This class used to differ only by being darker, with both
    sections sharing an identical 40 ms onset, so the one distinction the name
    carries was the one it did not make.

    Darker AND slower is not two decisions: a slow bow puts less energy into the
    upper partials, so the colour follows from the speed rather than standing on
    its own.
    """
    # BALANCE. Measured K-weighted at the same MIDI velocity, each voice in its
    # own comfortable register, the orchestra spanned 24.8 dB -- a flute 13.7 dB
    # over a trumpet. No score can correct that: the composer's velocities are
    # supposed to set the balance, and they cannot if the voices are not level
    # with each other to begin with. Normalised to the brass, which was the most
    # recently calibrated (against a real trumpet recording).
    initial_gain = 1.0 / 8536 / (BowedStringProperties.section_players ** 0.5)   # as the first section
    tonal_dampening = 1.25      # darker: the slow bow's own consequence
    max_harmonic = 32
    # THE SLOW BOW. chiff_max_valve_time is the onset ramp when attack_time is
    # None (blockrender: `at = props.attack_time if ... else chiff_max_valve_time`;
    # the reference agrees), and with release_valve_time unset it is the release
    # too -- which is right, a slow draw stops slowly as well. 40 ms -> 300 ms.
    # Both are capped at 0.45*duration, so a short note still speaks in time.
    chiff_min_valve_time = 0.12
    chiff_max_valve_time = 0.30
    # sustain_jitter = 0.38 lived here until now: the leftover from before the
    # section was seven real players. c9b648c took it to 0.0 on the parent --
    # "the held note is the players now, not a jitter" -- and missed the
    # subclass, so Ensemble 2 kept the noise the players were meant to replace.
    # chiff_cycle went with it: it shaped a chiff whose volume is now zero.



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

    # PITCH DRIFT FROM TENSION, the same effect the piano models and for the same
    # reason: a head struck hard is stretched further, a stretched head is a
    # tighter head, and a tighter head is sharper. So the note starts above its
    # pitch and settles onto it as the amplitude falls -- and because the bend is
    # scaled by attack_volume, a hard stroke drifts and a soft one barely does.
    # On a tom this is the familiar downward "pyow"; it is why a drum hit hard
    # does not merely sound louder.
    #
    # This belongs to the membranes and NOT to the bars: a bar's pitch is set by
    # its stiffness and geometry, which a mallet does not change, so the struck
    # bar voices correctly leave tension_bend at zero.
    tension_bend = 0.030          # ~50 cents at full velocity
    tension_settle_time = 0.20
    tension_settle_cutoff = 1.2

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
    tension_bend = 0.045       # a kick drops hardest of all: a slack, wide head
    tension_settle_time = 0.13
    max_harmonic = 10
    tonal_dampening = 1.9      # darker/rounder: fundamental-dominant thump
    decay_db = 24.0            # more body (louder-perceived); rings ~1.1 s


# --- Struck bars and plates (GM 8-15) --------------------------------------
# All eight of these shared one generic MalletProperties, whose inharmonicity put
# the second partial at 2.02x the first -- essentially a harmonic series, which is
# the one thing a struck bar is not. A bar free at both ends rings at
# 1 : 2.756 : 5.404 : 8.933, and THAT ratio is why a glockenspiel sounds like
# metal rather than like a flute.
#
# What separates the instruments in this family is whether the bar is undercut.
# Carving an arch out of the underside lowers the second mode until it is a
# musical interval above the first: two octaves (4:1) on a marimba and vibraphone,
# a twelfth (3:1) on a xylophone. A glockenspiel is not undercut at all, so it
# keeps the raw 2.756 and reads as a clangorous plate.
#
# The engine's stretch is r(n) = n * (1 + (n^2 - 1) * B / 2), with the fundamental
# pinned, so B can place the SECOND mode exactly -- the one that matters -- and
# the third then lands close for the undercut bars (marimba 11.0 against a real
# 10.0, xylophone 7.0 against 6.0). For the un-undercut bar the third overshoots
# (6.0 against 5.4), so those voices keep few modes.

class StruckBarProperties(MalletProperties):
    """A bar free at both ends, not undercut: 1 : 2.756 : ... See above.

    ONE-SHOT, like the drums: nothing about lifting a key stops a struck bar.
    Measured before this was set, every voice in the family rang for exactly the
    length of the test note -- 0.49 s for a 0.49 s note -- so decay_db was
    controlling nothing at all and a glockenspiel and a xylophone were
    indistinguishable in duration. What ends the note is the bar's own decay.
    """
    one_shot = True
    release_floor_db = -45.0
    inharmonicity_coefficient = 0.252     # places mode 2 at 2.756
    inharmonicity_dynamic = False
    max_harmonic = 4


class GlockenspielProperties(StruckBarProperties):
    """Steel bars, no resonators: bright, clangorous and long-ringing.

    MEASURED against the University of Iowa MIS recording (bells.plastic.mf,
    C6-B6). Two corrections to what theory alone had given:

      - the second partial sits at ~3.07x the fundamental, not the ideal free
        bar's 2.756. Clear on the strokes where it is strong (3.095 at -8.5 dB,
        3.065 at -23.7 dB). Real bars are not the uniform beam of the textbook.
      - it rings far longer than assumed: T60 ~14.6 s against the ~3.7 s the
        model produced. Orchestra bells are undamped steel and they sing.
    """
    bar_second_mode = 3.07
    inharmonicity_coefficient = (3.07 / 2.0 - 1.0) / 1.5   # place mode 2 at 3.07
    initial_gain = 1.0 / 2.8      # levelled to the orchestra at equal velocity
    tonal_dampening = 0.9        # bright: the upper modes carry
    decay_db = 1.27              # T60 ~14.6 s, measured
    harmonic_decay_db = 0.6      # see TubularBell: this is what caps the ring


class CelestaProperties(StruckBarProperties):
    """Steel plates struck through felt, each over a wooden resonator. The felt
    is what separates it from a glockenspiel -- a soft hammer cannot excite the
    high modes, so it is the same bar sounding much gentler."""
    initial_gain = 1.0 / 2.7
    tonal_dampening = 1.7        # felt: the top is simply not excited
    decay_db = 9.0
    harmonic_decay_db = 5.0


class MusicBoxProperties(StruckBarProperties):
    """A plucked steel comb tooth: a bar fixed at ONE end rather than free at
    both, plucked by a pin. Bright and short, and small -- the teeth are tiny,
    so there is very little of it."""
    initial_gain = 1.0 / 2.7
    tonal_dampening = 1.1
    decay_db = 17.5              # ~0.8 s
    harmonic_decay_db = 6.0


class TunedBarProperties(MalletProperties):
    """A bar undercut so its overtones land on WHOLE-NUMBER ratios.

    This is the real division in the family, and it is not metal-versus-wood.
    Carving an arch from the underside of a bar lowers its first overtone until
    it is a musical interval above the fundamental, and the makers tune it to an
    exact harmonic: 4:1 (two octaves) on a marimba and a vibraphone, 3:1 (a
    twelfth) on a xylophone. A glockenspiel bar is not undercut at all, so it
    keeps the free bar's 1 : 2.756 : 5.404 and clangs. Which is why a xylophone
    is hard and bright next to a marimba's roundness: both are tuned, but the
    xylophone's tuned overtone sits an octave closer to the fundamental.

    So these voices must NOT be stretched. Their modes are harmonic -- a sparse
    subset of the series, with everything between simply absent, which is what a
    bar is: a few discrete modes rather than a full series. Modelled directly as
    the modes that sound, instead of bending a harmonic series into place.

    (The first overtone is the one makers tune reliably; the second is less
    consistent from instrument to instrument, so the upper mode here is a fair
    representative rather than a specification.)
    """
    one_shot = True                       # see StruckBarProperties
    release_floor_db = -45.0
    inharmonicity_coefficient = 0.0       # harmonic by construction
    inharmonicity_dynamic = False
    # MEASURED (Iowa MIS): a vibraphone's partials come out 1 : 4.02 : 10.06 --
    # the 4:1 undercut and the 10:1 second overtone, both exactly as tuned. A
    # marimba shows 1 : 3.02 : 4.03, so it carries a further mode near 3 that
    # this list omits; the 4:1 is confirmed on both.
    bar_modes = ((1, 1.0), (4, 0.48), (10, 0.10))
    max_harmonic = 10

    def series_volume(self, harmonic):
        """Only the bar's own modes sound; the rest of the series is silent."""
        for n, g in self.bar_modes:
            if harmonic == n:
                return self.gain * g
        return 0.0


class UndercutBarProperties(TunedBarProperties):
    """Undercut to two octaves (4:1): marimba and vibraphone."""


class VibraphoneProperties(UndercutBarProperties):
    """Aluminium bars over tuned resonators, with a damper pedal: mellow and
    very long-ringing. (The motor-driven fans that give a vibraphone its name
    modulate the resonators; that tremolo is not modelled here.)"""
    initial_gain = 1.0 / 5.8
    tonal_dampening = 1.5
    decay_db = 3.2      # ~3.5 s: a vibraphone rings a long time
    harmonic_decay_db = 4.0


class MarimbaProperties(UndercutBarProperties):
    """Rosewood, same 4:1 undercut as the vibraphone but wood instead of metal:
    the same tuning, a far shorter ring and a much darker tone."""
    initial_gain = 1.0 / 5.3
    tonal_dampening = 2.0        # wood: dark, fundamental-dominant
    # MEASURED (Iowa MIS, Marimba.yarn.mf, C4-B4): T60 1.56 s over 7 strokes,
    # r2 0.992 -- about twice the ring the model had been given by guess. Wood
    # does not ring like metal, but it rings more than I assumed.
    decay_db = 5.1               # T60 ~1.56 s, measured
    # The strike is already right (overtone -13.0 dB against a measured -12.5),
    # but it lingered: -29.6 dB in the sustain where the real bar is at -57.5.
    # A marimba's overtones die almost immediately and leave a near-pure tone,
    # which is what makes it mellow.
    harmonic_decay_db = 22.0


class XylophoneProperties(TunedBarProperties):
    """Rosewood undercut to a TWELFTH (3:1) rather than two octaves, which is
    what makes a xylophone bright and hard where a marimba is round -- the tuned
    overtone sits an octave closer to the fundamental. Short, dry, struck hard."""
    # MEASURED (Iowa MIS, xylophone.hardrubber.mf, C5-B5): partials at
    # 1 : 3.02 : 6.43, confirming both the twelfth undercut and a mode near 6.
    #
    # And the twelfth is LOUDER THAN THE FUNDAMENTAL at the strike -- measured
    # +9.4 dB above it in the first 40 ms, against the -9.3 dB this model gave.
    # That is the whole reason a xylophone reads as a hard bright clack rather
    # than as a pitch: what you hear first is mostly the twelfth. It then falls
    # away fast, to -29.5 dB by the sustain, so the note settles onto its
    # fundamental almost at once.
    bar_modes = ((1, 1.0), (3, 5.2), (6.43, 0.05))
    max_harmonic = 7
    initial_gain = 1.0 / 21.9   # the strong twelfth carries real energy
    tonal_dampening = 1.2
    decay_db = 15.0              # T60 ~0.69 s, measured (Iowa): dry, but not as
                                 # dry as the 0.2 s I had asserted
    harmonic_decay_db = 26.0     # the twelfth must fall ~39 dB in 0.35 s


class TubularBellProperties(TunedBarProperties):
    """Long brass tubes -- and the clearest missing-fundamental instrument in
    the orchestra.

    A tubular bell's tuned modes run 2 : 3 : 4 (: 5 : 6), and there is NO partial
    at the pitch you hear: the ear reconstructs the fundamental an octave below
    the lowest one. That is why a tubular bell's note is faintly ambiguous, and
    why it does not sound like the bar instruments despite being hit with the
    same mallet.

    An earlier note here said the engine could not omit the first partial. That
    was true before bar_modes existed; it simply starts at 2, so the written note
    sounds as the fundamental the partials imply rather than as a partial itself.
    """
    bar_modes = ((2, 1.0), (3, 0.75), (4, 0.50), (5, 0.30), (6, 0.16))
    max_harmonic = 6
    release_floor_db = -60.0     # it must be allowed to ring out
    initial_gain = 1.0 / 7.9
    tonal_dampening = 1.0
    decay_db = 0.55
    # It is the PER-HARMONIC decay that sets a bell's ring, not decay_db: these
    # modes are harmonics 2-6, so at 2.0 dB each the upper ones were gone in
    # 3.5 s however slow the overall decay was -- lowering decay_db from 1.2 to
    # 0.55 moved it by a third of a second. At 0.5 it rings ~7.5 s, a struck
    # chime the player has not yet damped.
    harmonic_decay_db = 0.5


class TimpaniProperties(MembraneDrumProperties):
    """A kettledrum: a large tuned membrane over a closed bowl.

    GM 47 had been routed to MalletProperties -- a struck BAR, a quite different
    body. But inheriting the tom was not enough either: a tom and a timpano have
    the same *kind* of body and do not sound alike, and the reason is the bowl.

    A free circular membrane's modes are 1 : 1.59 : 2.14 : 2.30 : 2.65 -- no
    musical relationship at all, which is why a tom has no definite pitch.
    Enclose the air behind it and the cavity loads the membrane, pulling the
    useful modes into near-whole-number ratios: 1 : 1.5 : 2 : 2.5 : 3, i.e.
    harmonics 2:3:4:5:6 of a fundamental an octave below the lowest of them. The
    ear supplies that missing fundamental and hears a definite note. THAT is what
    makes a timpano pitched, and it is the whole difference from a tom.

    The engine's stretch cannot make a half-integer ratio, so the modes are
    placed explicitly -- the integer one by the series, the rest as extra voices
    at their own ratios, each decaying faster than the one below it, as the
    higher modes of a head do.
    """
    # (ratio to the sounding pitch, relative amplitude)
    membrane_modes = ((1.00, 0.55), (1.50, 1.00), (2.00, 0.70),
                      (2.50, 0.42), (3.00, 0.22))
    inharmonicity_coefficient = 0.0    # the ratios are set explicitly below
    inharmonicity_dynamic = False
    max_harmonic = 1                   # mode 1 only; the rest are unison voices

    # Less drift than a tom: a timpano's head is already at high tension to be
    # tuned at all, so the same stroke stretches it proportionally less -- and a
    # big head settles more slowly.
    tension_bend = 0.016       # ~27 cents at full velocity
    tension_settle_time = 0.30

    initial_gain = 1.0 / 7.3
    tonal_dampening = 1.75
    decay_db = 5.5                     # ~2 s: a kettle sings, it does not thump
    harmonic_decay_db = 5.0
    harmonic_decay_dampening = 0.25

    def series_volume(self, harmonic):
        return self.gain * self.membrane_modes[0][1] if harmonic == 1 else 0.0

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        if harmonic != 1:
            return []
        base = self.membrane_modes[0][1]
        return [(g / base, 0.0, ratio - 1.0,
                 harmonic_decay * (1.0 + 0.45 * (ratio - 1.0)), 0.0)
                for ratio, g in self.membrane_modes[1:]]


class NoisyPercussionMixin:
    """A radiation roll-off for the percussion voices that carry a noise wash.

    Adding broadband chiff to the hats, cymbals and wood blocks made them 40% of
    their energy above 12 kHz and 16% above 18 kHz, because the wash runs flat
    all the way to Nyquist. Nothing physical does that: a cymbal radiates poorly
    at the extreme top, air absorbs what is left, and a microphone would not
    capture it either. It reads as grit and fizz rather than as brightness, and
    lossy encoding of that much ultrasonic energy adds artefacts of its own.

    So the partials fall away above hf_corner_hz at hf_order * 6 dB/octave.
    """
    hf_corner_hz = 9000.0
    hf_order = 1.5

    def _hf_rolloff(self, harmonic):
        fn = self.frequency_x * (2.0 ** self.octave_position) * harmonic
        return 1.0 / (1.0 + (fn / self.hf_corner_hz) ** self.hf_order)

    def harmonic_volume(self, harmonic):
        v = super().harmonic_volume(harmonic)
        return 0.0 if v == 0.0 else v * self._hf_rolloff(harmonic)

    def chiff_harmonic_gain(self, harmonic):
        # The WASH needs the roll-off too, and it is the larger half of the
        # problem: chiff_harmonic_gain returns 1.0 at every harmonic by default,
        # so the noise ran flat to Nyquist while the tonal partials were already
        # falling away. Rolling off only the partials moved the drums' energy
        # above 12 kHz from 39.9% to 39.4% -- essentially nothing, because the
        # noise was carrying nearly all of it.
        return super().chiff_harmonic_gain(harmonic) * self._hf_rolloff(harmonic)


class NoiseDrumProperties(NoisyPercussionMixin, PercussionProperties):
    """Noise-dominated hit (hi-hat, shaker, guiro): a dense stack of strongly
    stretched partials approximating a band of colored noise, with a fast
    decay. decay_db sets how long the wash rings."""
    # A struck instrument ignores note-off: nothing about lifting the stick
    # stops a hi-hats, shakers, guiro, whistles. GM sequencers write arbitrary drum note lengths, so
    # honouring them cut these off at whatever the file happened to say
    # rather than letting them ring for their own time.
    one_shot = True
    release_floor_db = -50.0

    initial_gain = 1.0 / 11.0   # hats sat above the kick; the added wash reads louder
    max_harmonic = 64
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic * 40.0
    # A hi-hat is BROADBAND: two cymbals clamped together have no pitch. Measured
    # on the RING rather than the strike, the open hat was putting 41% of its
    # energy into a single 380 Hz partial by 400 ms and rising -- the noise died
    # and left pure modes behind, so the later it got the more it sang. Flattened
    # to the cymbal's value, with the wash sustained through the ring as a cymbal
    # does, since that is physically the same instrument.
    tonal_dampening = 0.15
    chiff_volume = 2.0
    chiff_cycle = 0.95
    chiff_release = 0.0
    sustain_jitter = 1.0           # the wash lasts as long as the hat does
    decay_db = 20.0
    harmonic_decay_db = 2.0
    harmonic_decay_dampening = 0.0


class SnareDrumProperties(NoisyPercussionMixin, PercussionProperties):
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


class SawtoothSynthProperties(BowedStringProperties):
    """An analogue-style SAWTOOTH lead: every harmonic present at exactly 1/n.

    General MIDI's synth leads were routed to the flue organ, which is a real
    pipe with an organ's own spectrum -- so a game cue's saw lead came out as
    an 8' principal. A saw is trivial for an additive engine, being nothing but
    the harmonic series at 1/n, so it is worth having as itself rather than as
    the nearest acoustic neighbour.

    Kept deliberately ideal: no inharmonicity (an oscillator has none) and no
    chiff. The shimmer BowedString uses for section detune is switched off for
    the same reason -- a single oscillator does not have a section.
    """
    odd_only = False
    max_harmonic = 64
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    chiff_volume = 0.0
    sustain_jitter = 0.0
    # CALIBRATED against the pipe organ at the same note and velocity. A saw
    # sums 64 partials at 1/n, so for the same initial_gain it lands ~20 dB
    # hotter than a voice whose spectrum rolls off quickly -- enough to clip the
    # mix of a General MIDI cue outright (Flat factor 18 on the first attempt).
    # Sharing a gain constant with another family is not the same as sharing a
    # level; the divisor has to be measured, not assumed.
    initial_gain = 1.0 / 6.6

    def harmonic_volume(self, harmonic):
        if self.max_harmonic and harmonic > self.max_harmonic:
            return 0.0
        # self.gain (which carries initial_gain and the octave tilt) is applied
        # INSIDE harmonic_volume by the base class -- returning a bare 1/n
        # discarded it, so these voices ignored their own initial_gain entirely
        # and came out ~20 dB above every other family, clipping the mix.
        return self.gain / harmonic


class SquareSynthProperties(SawtoothSynthProperties):
    """An analogue-style SQUARE/pulse lead: ODD harmonics only, at 1/n.

    The odd-only series is what makes a square hollow where a saw is bright --
    the same distinction the reed pipes already model, but here with no
    inharmonicity and no breath.
    """
    odd_only = True
    initial_gain = 1.0 / 6.5       # measured the same way; a square sits ~1 dB under a saw

    def harmonic_volume(self, harmonic):
        if harmonic % 2 != 1:
            return 0.0
        if self.max_harmonic and harmonic > self.max_harmonic:
            return 0.0
        return self.gain / harmonic


class MetalPercussionProperties(PercussionProperties):
    """Struck pitched metal/wood that rings with a clear-ish pitch (cowbell,
    agogo, triangle, woodblock, claves, ride bell): bright inharmonic modes,
    no noise wash -- these are meant to be tonal, unlike a cymbal."""
    # A struck instrument ignores note-off: nothing about lifting the stick
    # stops a cowbell, agogo, triangle. GM sequencers write arbitrary drum note lengths, so
    # honouring them cut these off at whatever the file happened to say
    # rather than letting them ring for their own time.
    one_shot = True
    release_floor_db = -50.0

    initial_gain = 1.0 / 2.25
    max_harmonic = 40
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic * 20.0
    tonal_dampening = 0.9
    decay_db = 4.0
    harmonic_decay_db = 1.5
    harmonic_decay_dampening = 0.1


class WoodPercussionProperties(NoisyPercussionMixin, PercussionProperties):
    """Struck WOOD -- claves, woodblocks, guiro body: a hard, dry tock.

    These were sharing MetalPercussionProperties with the cowbell, the agogo and
    the triangle, whose ring is measured in seconds. A clave rings for about two
    tenths of one. At the shared decay every stroke overlapped the next, so a
    samba pattern accumulated into a sustained pitched drone instead of reading
    as rhythm -- the more damaging because wood percussion is nearly always
    keeping time, and time-keeping that holds a pitch competes with the tune.

    So: a definite pitch, as wood has, but gone almost immediately.
    """
    # Level, measured against the rest of the kit: at 1/2.25 (inherited from the
    # tonal-metal family) a clave peaked ABOVE the bass drum, which is not where
    # a time-keeping click belongs. Broadband noise also reads louder than a
    # tonal ping of the same peak, so the added wash needs paying for.
    initial_gain = 1.0 / 5.0
    max_harmonic = 44
    # A block or a clave is mostly a CLICK. Its modes are wildly inharmonic --
    # a short bar's bending modes sit near 1 : 2.76 : 5.4, nothing like a
    # harmonic series -- so no pitch should stand out enough to sing. At x12
    # stretch with tonal_dampening 0.8 the low partials were still close enough
    # to harmonic, and prominent enough, to read as a note.
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic * 16.0
    # A clave is a TUNED block -- it has a definite pitch, and burying it in
    # wash turned the part into brushes. This sits between the two failures:
    # tonal enough that the pitch is there, inharmonic and transient enough that
    # it reads as a click keeping time rather than as a note.
    tonal_dampening = 0.75
    # The strike is broadband; the RING is modal. Sustaining the wash through the
    # ring turned the part into brushes -- but a few decaying sinusoids is exactly
    # what a clave is, once they last 0.2 s instead of the eleven seconds this
    # voice originally inherited. The noise belongs at the onset only.
    chiff_volume = 0.65
    chiff_cycle = 0.5
    chiff_release = 0.0
    # The noise must persist through the (very short) ring, not just the onset --
    # a cymbal does this too. With noise only at the attack, what was left after
    # the first few milliseconds was a handful of decaying sinusoids, and that is
    # a pitch no matter how quickly it dies.
    sustain_jitter = 1.0
    chiff_min_valve_time = 0.001
    chiff_max_valve_time = 0.004
    one_shot = True                 # a struck block ignores note-off; it is already gone
    release_floor_db = -50.0
    decay_db = 260.0                # ~0.23 s to -60 dB (metal percussion: 10.9 s)
    harmonic_decay_db = 40.0        # the upper modes go first: a tock, not a ring
    harmonic_decay_dampening = 0.0


class CymbalProperties(NoisyPercussionMixin, PercussionProperties):
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


class RideBellProperties(CymbalProperties):
    """The BELL of a ride cymbal: struck on the raised centre, so a definite
    pitch speaks THROUGH a cymbal's wash rather than instead of it.

    It was mapped to MetalPercussion -- the tonal bucket with the cowbell, the
    claves and the woodblock -- which gave it a clear pitch and NO wash at all,
    so it read as a melodic ping. That matters more than it sounds: a ride bell
    often carries the entire rhythm of a samba or a battle cue, and a rhythm
    part with a definite pitch starts competing with the tune.

    So: the cymbal family's broadband bed, but with the modes lifted well clear
    of it, and a much shorter ring than a crash, because a ride articulates
    where a crash washes.
    """
    tonal_dampening = 0.55      # modes stand out of the wash (a crash sits at 0.15)
    chiff_volume = 0.9          # less hiss than a crash
    decay_db = 11.0             # articulates instead of washing (a crash is 6.0)
    max_harmonic = 60


# --- The human voice -------------------------------------------------------

class SynthLeadProperties(FlueOrganProperties):
    """GM 82-87: synth leads that borrow the flue pipe's tone but have no stops.

    Same fault as the woodwinds -- registerable makes CC11 a stop word, and a
    Calliope lead has no drawbars. The flue timbre is a fair stand-in for these
    simple waveform leads; the drawbars are not.
    """
    registerable = False


class ReedPipeProperties(ReedOrganProperties):
    """GM 109/111 (bagpipe, shanai): a reed driving a pipe, but one player's
    instrument rather than a console. Reed tone, no drawbars."""
    registerable = False


class OrchestralFluteProperties(BlownPipeProperties):
    """An OPEN pipe: flute, piccolo, recorder, whistle, shakuhachi.

    BlownPipeProperties carries odd_only = True, which is right for the stopped
    ranks our organ pipeline drives through it (a Gedackt is closed at one end
    and resonates at odd multiples only). It is wrong for an orchestral flute,
    which is open at both ends and has the full series. Measured against the
    Iowa MIS flute (nonvib, mf, C5): h2 is 7.1 dB below the fundamental and h3
    is 7.0 -- the second harmonic is as strong as the third, where this model
    was rendering it at -134 dB, which is to say not at all.

    The series also falls away faster above h3 than any single 1/n^d can follow
    (real: -20.5 at h4, -35.7 at h6), so a radiation corner carries that.
    """
    odd_only = False
    tonal_dampening = 1.0
    bore_corner_hz = 2200.0
    bore_order = 1.6


class OrchestralReedProperties(ReedOrganProperties):
    """A woodwind, borrowing the reed organ's timbre but NOT its drawbars.

    GM 64-71 -- the saxophones, oboe, English horn, bassoon and clarinet -- route
    here for their sound, and inherited registerable = True with it. That has one
    real consequence: for a registerable voice CC11 is read as a 14-bit STOP WORD,
    not as expression. An oboe part that shapes a phrase with expression was
    therefore drawing and retiring stops instead. alright.mid does exactly this,
    with eight distinct CC11 values across its sax section.

    A drawbar is a physical control surface on an organ. A clarinet does not have
    one, so this class does not pretend it does, and CC11 goes back to meaning
    what GM says it means.
    """
    registerable = False


class DoubleReedProperties(FormantBody, OrchestralReedProperties):
    """Oboe, english horn, bassoon, and the saxophones: CONICAL bores.

    A cone behaves like an open pipe -- full harmonic series -- not like the
    stopped cylinder that odd_only describes. Measured on the Iowa oboe at C4,
    h2 is +1.7 dB ABOVE the fundamental and h4 is +2.5; on the bassoon at C3,
    h4 is +19.3. This model had every one of those at -130 dB.

    What it still does not capture is that these instruments' strength lies in a
    FORMANT well above the fundamental -- the oboe's near 1.4 kHz, the bassoon's
    near 500 -- which no monotonic 1/n^d can produce. Getting the even harmonics
    back is the larger half of the error; the formant is the remaining half.
    """
    odd_only = False
    tonal_dampening = 0.75    # these are bright: the upper series carries
    initial_gain = 1.0 / 8050   # levelled to the set after the formant refit
    # FORMANT, measured. The Iowa oboe at C4 peaks at its 5th harmonic, 1295 Hz,
    # 12.6 dB ABOVE the fundamental -- the oboe's characteristic resonance, and
    # the reason it cuts through an orchestra. The bassoon peaks at its 4th,
    # 524 Hz, 19.3 dB above. A conical reed is a resonator with a strong peak
    # well up the series, which is exactly what a 1/n^d rolloff cannot be.
    formants = ((1300.0, 700.0, 2.6), (3000.0, 1400.0, 0.6))
    formant_floor = 0.30
    bore_corner_hz = 5000.0
    bore_order = 1.6


class BassoonProperties(DoubleReedProperties):
    """The bassoon's resonance sits far lower than the oboe's -- measured at its
    4th harmonic, 524 Hz, 19.3 dB above the fundamental at C3. Same conical
    family, an octave and a half lower formant, which is the whole difference
    between the two voices."""
    # Fitted to the Iowa bassoon at C3 AND C4: 7.9 dB rms across both, where a
    # single resonance managed only 10.5 dB on one register alone.
    #
    # The reason it needed a ZERO: at C3 the 5th harmonic sits 33 dB below its
    # neighbours (-13.7 between +19.3 and -2.1). Poles cannot make a dip that
    # deep -- a formant list only adds -- and the notch is real, a side branch in
    # the bore cancelling whatever partial lands on it. With the antiresonance
    # the model reproduces it: +22.3 at h4 then -11.2 at h5.
    # Levelled after the refit: a shallower source rolloff puts far more power in
    # the series, and the bore normalisation only compensates for the FILTER.
    initial_gain = 1.0 / 10000
    formants = ((500.0, 180.0, 4.0),)
    antiformants = ((660.0, 180.0, 0.95),)
    formant_floor = 0.03
    tonal_dampening = 0.5
    octave_dampening = 0.4
    bore_corner_hz = 3000.0


class SaxophoneProperties(DoubleReedProperties):
    """A big conical reed: the same open series, with a resonance between the
    bassoon's and the oboe's. Not measured -- the Iowa saxophone samples were
    not fetched -- so this is placed by bore size between two that were."""
    formants = ((900.0, 450.0, 2.2), (2000.0, 1000.0, 0.6))
    bore_corner_hz = 4000.0


class ClarinetProperties(OrchestralReedProperties):
    """A cylindrical bore stopped by the reed: the one orchestral wind whose
    odd harmonics really do dominate.

    Measured (Iowa, C4, mf): h3 is only 2.7 dB below the fundamental while h2 is
    38.5 dB down, and h5 is -14.2 against h4's -23.9. So the evens are strongly
    suppressed but PRESENT -- absolute odd_only put them at -130 dB, which loses
    the reediness that the weak-but-audible evens carry.
    """
    even_harmonic_db = -26.5     # lands h2 near the measured -38.5 dB
    tonal_dampening = 0.9        # strong odd series well up the spectrum
    initial_gain = 1.0 / 6400    # levelled to the set


class VocalProperties(FormantBody, BowedStringProperties):
    """A sung vowel: a glottal source shaped by the fixed resonances of a
    vocal tract.

    GM 52-54 (Choir Aahs, Voice Oohs, Synth Voice) had been falling through to
    the bowed-string bucket, which is 1950 notes across the collection -- and not
    incidental notes, but the actual choral writing: a full SATB CANON.MID,
    satb196, dimin, bwv196, djchp210. Strings were a reasonable stand-in for
    "sustained and non-percussive" and wrong about the one thing that makes a
    voice recognisable, which is not the source but the FILTER.

    The vocal folds make a buzz -- roughly a pulse train, about -12 dB/octave,
    which is what tonal_dampening says here. What identifies a vowel is where the
    tract resonates: two or three formants at FIXED frequencies that do not move
    when the pitch does, so a soprano and a bass singing "ah" share them. That is
    exactly the shape bore_gain already models for a brass bell -- a fixed filter
    the harmonics slide through -- so the formants go there and inherit its power
    normalisation for free, which keeps a vowel change a change of colour and not
    of loudness.

    Inherits the string SECTION, deliberately: a choir is a number of people who
    do not agree on the pitch and each carry their own vibrato, which is the same
    machinery for the same reason. Singers agree rather less than string players,
    hence the wider spread.
    """
    section_spread_cents = 8.0
    section_vibrato_cents = 7.0
    section_vibrato_hz = (4.8, 6.2)

    # (centre Hz, bandwidth Hz, amplitude). Default is "ah".
    formants = ((700.0, 130.0, 1.00), (1220.0, 90.0, 0.50), (2600.0, 130.0, 0.22))
    formant_floor = 0.06        # the tract is not silent between resonances
    tonal_dampening = 1.8       # glottal source, ~-12 dB/octave
    max_harmonic = 48
    bore_corner_hz = 4000.0     # the mouth stops radiating: also arms bore_gain
    bore_order = 2.0




class ChoirAahsProperties(VocalProperties):
    """GM 52. An open "ah": the first formant high and the tract wide open."""
    # BALANCE, per vowel: the formant filter is power-normalised, but the vowels
    # still land differently because they weight the source's harmonics
    # differently -- "oo" throws away everything above its low F2. Measured
    # K-weighted at velocity 100 like the rest of the set and brought to the
    # orchestra's level. /sqrt(players) as for any section.
    initial_gain = 1.0 / 6875 / (VocalProperties.section_players ** 0.5)


class VoiceOohsProperties(VocalProperties):
    """GM 53. A rounded "oo": lips narrowed, so F1 and F2 drop a long way and
    the vowel goes dark. The single biggest audible difference between vowels
    is F2, and it moves by more than an octave between these two."""
    formants = ((300.0, 90.0, 1.00), (870.0, 100.0, 0.42), (2240.0, 140.0, 0.12))
    bore_corner_hz = 3000.0
    initial_gain = 1.0 / 6127 / (VocalProperties.section_players ** 0.5)


class SynthVoiceProperties(VocalProperties):
    """GM 54. A synthesized voice: an "eh" between the other two, and steadier
    than people are -- less spread, less vibrato, because the thing being
    imitated is a synthesizer imitating a choir."""
    formants = ((530.0, 110.0, 1.00), (1840.0, 110.0, 0.55), (2480.0, 140.0, 0.25))
    section_spread_cents = 4.0
    section_vibrato_cents = 3.0
    initial_gain = 1.0 / 4542 / (VocalProperties.section_players ** 0.5)


# --- Sound effects (GM 120-127) --------------------------------------------
# The whole effects bank fell through to MalletProperties, a struck bar, so a
# gunshot rang as a tuned bell. These are not pitched instruments at all: they
# are bands of noise, built the way the percussion voices build theirs -- hard
# inharmonicity to scatter the partials off the harmonic grid, a near-flat
# tonal_dampening so no mode stands out of the wash, and a wide running phase
# jitter (the chiff mechanism) to smear what is left into continuous noise.

class BreathNoiseProperties(NoisyPercussionMixin, BlownPipeProperties):
    """GM 121. Breath with no note in it: broadband, and it lasts as long as
    the player holds it -- so this sustains rather than ringing out like the
    struck percussion. 339 notes of it in bwx27c, which had been bells."""
    odd_only = False
    # BALANCE. Unmeasured, the wash came out 16 dB over a trumpet -- a broadband
    # voice fills far more of the spectrum than a tone of the same peak does.
    # Levelled to the orchestra like everything else.
    initial_gain = 1.0 / 28395
    max_harmonic = 64
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic * 45.0
    inharmonicity_dynamic = False
    tonal_dampening = 0.25         # near-flat: a hiss, not a chord
    chiff_volume = 2.4
    chiff_cycle = 0.95             # a full cycle of jitter = noise, not shimmer
    chiff_release = 0.6
    sustain_jitter = 1.0           # the breath keeps moving while it is held
    hf_corner_hz = 7000.0
    mode_lock_spread = 0.0


class SeashoreProperties(BreathNoiseProperties):
    """GM 122. Surf: the same noise, slower and darker -- it swells in and
    ebbs out rather than starting, and the sea has far more low in it than a
    breath does."""
    initial_gain = 1.0 / 13071      # levelled: see BreathNoiseProperties
    tonal_dampening = 0.5          # darker than breath: weighted low
    hf_corner_hz = 3500.0
    chiff_min_valve_time = 0.35    # swells in
    chiff_max_valve_time = 0.9
    chiff_release = 1.0


class GunshotProperties(NoisyPercussionMixin, PercussionProperties):
    """GM 127. A crack: everything at once and then gone. One-shot, because
    nothing about releasing a key stops a gunshot -- and the six of them in
    A-Team are written as short notes, so honouring note-off would clip the
    report to nothing."""
    one_shot = True
    release_floor_db = -50.0
    # Levelled to sit ~6 dB OVER the orchestra rather than with it: a gunshot is
    # supposed to be the loudest thing in the piece, but not to swamp it.
    initial_gain = 1.0 / 13
    max_harmonic = 72
    inharmonicity_coefficient = SynthProperties.inharmonicity_coefficient_2nd_harmonic * 60.0
    tonal_dampening = 0.12         # flattest of all: no pitch survives
    # A GUNSHOT IS AN IMPULSE, AND THE TAIL IS THE ROOM. Almost nothing you hear
    # after the first few milliseconds comes from the gun: it comes from whatever
    # the blast is standing in. So this voice is a click, and the hall the mix is
    # rendered through supplies the decay -- which is what an impulse response IS.
    #
    # Measured: at decay_db 30 the voice made its own 0.54 s tail and the hall
    # added essentially nothing on top of it (T40 0.539 s dry, 0.595 s wet) -- a
    # synthetic decay with reverb painted over it. As a click the dry T40 is
    # 48 ms and the wet T40 is 0.50 s, i.e. the decay now belongs entirely to the
    # room. It also comes out the SAME 0.49-0.50 s whichever click length is
    # used, which is the tell that the room is doing the work.
    decay_db = 400.0               # dry T40 ~48 ms: a crack, not a ring
    harmonic_decay_db = 3.0
    harmonic_decay_dampening = 0.0
    chiff_volume = 2.6
    chiff_cycle = 0.95
    chiff_release = 0.0
    sustain_jitter = 1.0
    chiff_min_valve_time = 0.001   # instantaneous
    chiff_max_valve_time = 0.004
    hf_corner_hz = 8000.0


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

    def sum_values(self, second, nyquist):
        # Registerable (organ) tones scale each partial LIVE by its rank's gate
        # (drawn stops / crescendo) times the swell shutter, both read from the
        # per-channel RegState the MIDI layer steps each sample. A rank at gate ~0
        # is skipped (no partial eval). swell == 1 makes shutter() return 1.0, so
        # a fully-open 8'-only organ sums exactly like the base path. Non-organ
        # tones fall through to the frozen single-series sum.
        st = self.reg_state
        if st is None:
            return BaseTone.sum_values(self, second, nyquist)
        gate = st.gate
        swell = st.swell
        shutter = self.properties.shutter
        v = 0.0
        for p in self.partials:
            g = gate.get(p.rank, 0.0)
            if g <= 1e-4:
                continue
            v += g * shutter(p.nom_freq, swell) * p.value(second, nyquist)
        # Full precision, no per-tone clamp: the pleno legitimately exceeds +/-1
        # here and is clipped once at the output (see BaseTone.sum_values).
        return v

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
        self.reg_state = None   # set in init_partials for registerable voices
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
            # A section's players sit at their own desks, so each gets its own
            # incidence and its own arrival time -- for THIS ear. None for a
            # voice that is one body. See SynthProperties.section_position_x.
            _seats = self.properties.section_seats()
            self.seats = (None if not _seats else
                          [(li, ld) for li, ri, ld, rd in _seats] if self.audio_channel == 0
                          else [(ri, rd) for li, ri, ld, rd in _seats])
        else:
            self.seats = None
            self.delay = {
                0: self.properties.left_delay,
                1: self.properties.right_delay,
            }[self.audio_channel]
            self.pan = {
                0: self.properties.left_pan,
                1: self.properties.right_pan,
            }[self.audio_channel]

        self.partials = []

        # Organ voices build a full stop-list of ranks and read a LIVE per-rank
        # gate + swell tilt at render time (see _build_registered_partials and
        # SynthTone.sum_values). Every other voice keeps the single harmonic
        # series below, untouched.
        if getattr(self.property_class, 'registerable', False):
            self.reg_state = self.sampler.reg_state_for(self.midi_channel)
            self._build_registered_partials()
            if self.max_fade is not None:
                for partial in self.partials:
                    partial.max_fade = self.max_fade
            return
        self.reg_state = None

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
            main_inc, main_delay = (self.seats[0] if self.seats
                                    else (getattr(self, 'incidence', 0.0), self.delay))
            harmonic_volume = harmonic_volume_raw * self.pan
            if hrtf:
                harmonic_volume *= self.properties.hrtf_gain(harmonic_frequency, main_inc)
            if harmonic_volume == 0.0:
                continue

            volume += harmonic_volume

            harmonic_decay = self.properties.harmonic_decay(harmonic)
            transverse.append((harmonic_frequency, harmonic_volume_raw, harmonic_decay))
            errlog("SimplePartial(%s, %s, %s, %s, %s)" % (
                self.frequency, harmonic, harmonic_volume, harmonic_decay, self.delay))
            main = SimplePartial(self.properties, self.frequency, harmonic, harmonic_volume,
                                 harmonic_decay, main_delay, self.ref_count)
            # The ear delay moves the CARRIER too, not only the envelope -- see
            # the note in blockrender.emit_partial. start_phase is in cycles, so
            # a delay of d seconds is -f*d of them.
            if hrtf:
                main.start_phase = -harmonic_frequency * main_delay
            main.vibrato = self.properties.voice_vibrato(self.frequency, 0)   # player 0
            main.player = 0
            self.partials.append(main)
            # Extra unison voices beat against the main partial: a couple of
            # ratio-detuned strings for a piano (the dance), a fixed-Hz spread
            # for a section of many bowed strings. Each voice carries its own
            # gain, detune (Hz and/or ratio), and decay.
            for ui, (gain_mult, offset_hz, detune_ratio, unison_decay, start_phase) in \
                    enumerate(self.properties.unison_voices(self.frequency, harmonic, harmonic_decay)):
                # This player's chair. The shadow is read at the NOMINAL
                # harmonic, as the main voice's is: a few cents of detune moves
                # it by nothing, and the two renderers have to agree.
                uinc, udelay = (self.seats[ui + 1]
                                if self.seats and ui + 1 < len(self.seats)
                                else (main_inc, main_delay))
                uvol = harmonic_volume_raw * self.pan
                if hrtf:
                    uvol *= self.properties.hrtf_gain(harmonic_frequency, uinc)
                partial = SimplePartial(self.properties, self.frequency, harmonic,
                                        uvol * gain_mult, unison_decay,
                                        udelay, self.ref_count)
                partial.frequency_offset = offset_hz
                partial.detune_ratio = detune_ratio
                partial.start_phase = start_phase
                if hrtf:
                    # this player's own arrival, at this player's own frequency
                    # (blockrender uses the detuned om for the same reason)
                    uf = harmonic_frequency * (1.0 + detune_ratio) + offset_hz
                    partial.start_phase = start_phase - uf * udelay
                partial.vibrato = self.properties.voice_vibrato(self.frequency, ui + 1)
                partial.player = ui + 1
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

    def _build_registered_partials(self):
        """Build every rank in the voice's stop list. Each rank is a full
        harmonic series placed a footage interval away on the note's OWN
        inharmonic-stretched grid: rank harmonic m sits at partial index
        h = ratio*m, so its stretched frequency f*h*(1+0.5(h^2-1)B) coincides
        with the 8' series wherever the grids meet (a 4' fundamental, h=2, lands
        exactly on the 8's stretched 2nd partial) -- the ranks LOCK, no beating.
        Every partial is tagged with its rank key and nominal frequency; the
        live per-rank gate and swell tilt are applied in SynthTone.sum_values,
        so a muted rank costs only a dict lookup. The 8' rank alone reproduces
        the pre-registration single-series render exactly."""
        props = self.properties
        f = self.frequency
        if props.inharmonicity_dynamic:
            props.inharmonicity_coefficient = props.inharmonicity_coefficient_for_frequency(f)
        B = props.inharmonicity_coefficient
        maxm = getattr(props, 'max_harmonic', 64) or 64
        spec_cache = {}
        for rank in props.stop_ranks:
            key, ratio, gain = rank[0], rank[1], rank[2]
            spec_cls = rank[3] if len(rank) > 3 else None   # borrow this voice's SPECTRUM only
            dyn = rank[4] if len(rank) > 4 else False        # force flue-dynamic inharmonicity (hybrid-lock)
            sp = None
            if spec_cls is not None:
                sp = spec_cache.get(spec_cls)
                if sp is None:
                    sp = rank_spectrum(spec_cls)(f, props.channel_pan, props.attack_volume,
                                                props.channel_volume)
                    spec_cache[spec_cls] = sp
                hv_fn = sp.harmonic_volume
            else:
                hv_fn = props.harmonic_volume
            # A reed (harmonic base) drawn against the stretched flue beats -- a phaser.
            # dyn=True gives this rank the flue dynamic (Steinway) stretch so it LOCKS
            # to hybrid like the principals. Otherwise use the base voice's grid.
            rank_B = (sp or props).inharmonicity_coefficient_for_frequency(f) if dyn else B
            # Place this drawstop at its case position (shared across a compound rank's
            # sub-footages -- one stop, one location).
            if hrtf and getattr(props, 'spiral_spatial', False):
                _li, _ri, _ld, _rd = props.hrtf_at(props.rank_position_x(key))
                rank_incidence = _li if self.audio_channel == 0 else _ri
                rank_delay = _ld if self.audio_channel == 0 else _rd
            else:
                rank_incidence = getattr(self, 'incidence', None)
                rank_delay = self.delay
            ceiling = getattr(props, 'pipe_ceiling_hz', None)
            mode = getattr(props, 'pipe_break_mode', 'fold')
            # A Mixtur is a COMPOUND rank -- ratio is a LIST of footages, each built and
            # broken back on its own. A plain stop has a single scalar ratio.
            sub_ratios = ratio if isinstance(ratio, (list, tuple)) else [ratio]
            for sub in sub_ratios:
                # Rank break-back: past the pipe ceiling a high rank has no pipes, so it
                # FOLDS an octave (repeats) -- a Mixtur's composition break, why the top
                # re-colors instead of turning shrill. Fold the FOOTAGE and re-derive on
                # the stretched grid, so it stays hybrid-LOCKED (not a naive freq halve).
                # Only upperwork (>=2) breaks; the 8'/16'/quint foundation keeps its pipes.
                eff_ratio = sub
                if ceiling and sub >= 2.0 and f * sub > ceiling:
                    if mode == 'truncate':
                        continue                  # no pipes past the ceiling -> silent (top THINS)
                    while f * eff_ratio > ceiling and eff_ratio >= 2.0:
                        eff_ratio *= 0.5          # break back an octave (top RE-COLORS)
                for m in range(1, maxm + 1):
                    h = eff_ratio * m
                    stretch = (1.0 + 0.5 * (h * h - 1.0) * rank_B) if rank_B > 0.0 else 1.0
                    hf = f * h * stretch
                    if hf > self.nyquist:
                        break
                    hv = hv_fn(m)
                    if hv == 0.0:
                        continue
                    vol = hv * self.pan
                    if hrtf:
                        vol *= props.hrtf_gain(hf, rank_incidence)
                    vol *= gain
                    decay = props.harmonic_decay(m)
                    p = SimplePartial(props, f, h, vol, decay, rank_delay, self.ref_count)
                    if dyn:
                        p.inharmonic_stretch = stretch   # override the base-B stretch SimplePartial computed
                    p.mode_lock_offset = props.mode_lock_offset_for(m)   # speech transient
                    p.rank = key
                    p.nom_freq = hf
                    p.vibrato = props.voice_vibrato(f, 0)     # player 0
                    self.partials.append(p)
                    for ui, (gain_mult, offset_hz, detune_ratio, unison_decay, start_phase) in \
                            enumerate(props.unison_voices(f, m, decay)):
                        up = SimplePartial(props, f, h, vol * gain_mult, unison_decay,
                                           rank_delay, self.ref_count)
                        if dyn:
                            up.inharmonic_stretch = stretch
                        up.frequency_offset = offset_hz
                        up.detune_ratio = detune_ratio
                        up.start_phase = start_phase
                        up.vibrato = props.voice_vibrato(f, ui + 1)
                        up.rank = key
                        up.nom_freq = hf
                        self.partials.append(up)


class RegState:
    """Live organ-registration state for one MIDI channel, shared between the
    MIDI layer (which steps it toward the CC targets each sample) and the tones
    (which read it at render time). `gate[rank]` in [0,1] is how far each drawn
    stop is out; `swell` in [0,1] is how open the shutter is. Defaults reproduce
    a single 8' rank, fully open -- i.e. today's organ sound."""
    __slots__ = ('swell', 'gate')

    def __init__(self):
        self.swell = 1.0
        self.gate = {"8": 1.0}


class SynthSampler(BaseSampler):
    def __init__(self, audio_channel=0, sample_rate=48000, sample_depth=16, sample_packing="h"):
        BaseSampler.__init__(self, sample_rate, sample_depth, sample_packing)
        self.audio_channel = audio_channel
        self.tones = {}
        # midi_channel -> RegState, created on demand. The MIDI layer's
        # per-sample stepper writes here; registerable tones read it.
        self.channel_state = {}

    def reg_state_for(self, midi_channel):
        st = self.channel_state.get(midi_channel)
        if st is None:
            st = RegState()
            self.channel_state[midi_channel] = st
        return st

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
