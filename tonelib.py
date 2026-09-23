#!/usr/bin/env python

"""
Copyright Ben Woolley 2010.
All rights reserved.
"""

import os
import random as _random
import re as _re
from math import exp as _exp, log as _log, sin as _sin, cos as _cos, pi as _pi, sqrt as _sqrt
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


def rand(second, granularity=None):
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
    x = int(second * (rand_granularity if granularity is None else granularity)) & 0xFFFFFFFFFFFFFFFF
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
    # SATURATE RATHER THAN OVERFLOW. A decay rate is dB per second, and above
    # about 3080 dB/s the exponent leaves the range of a double -- which raised
    # OverflowError rather than producing a very fast decay. It bit twice: a
    # PERCUSSION_RING under about 12 ms, and a measured mode set whose upper
    # modes are indexed far enough out to be solved to a huge rate. 3000 dB/s
    # is a partial gone in 20 ms; nothing above it is audibly different, and
    # nothing should crash for asking.
    return 10 ** (min(float(db), 3000.0) / 10)


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
_SOLO_VIBRATO = {}

_PLUCK_COMB = {}


def _pluck_comb(plucked_harmonic, pluck_dampening, harmonic):
    """The legacy pluck comb, memoised. Was 87% of the time to build a render.

    series_volume() used to evaluate this inline as

        sum(tv for th, tv in self.plucked_volumes if harmonic % th)

    over a list that is 999 entries long for every pipe, wind, brass, string,
    organ and vocal voice (StoppedPipeProperties.plucked_harmonic = 1000). That is
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
        # The partial itself is NOT delayed -- see bloom_gain. blockrender emits
        # the late arrival as a separate quieter copy; the reference renderer
        # builds its partials elsewhere and simply does not model it, which is a
        # known gap between the two and is noted in the class.
        bd = self.delay

        if self.max_fade is not None:
            fade_time = min(fade_time, self.max_fade)

        self.attack_fade = Fade(Second(second + bd), Second(second + bd + fade_time))
        # The chiff burst has its OWN (short, capped) width, decoupled from the
        # slow speech fade, and rolls off for the upper harmonics -- so a big
        # pipe's chiff is a brief low chuff, not a long high hiss (see the chiff
        # model on SynthProperties). Defaults reproduce the old behaviour exactly.
        base_freq = getattr(self, "base_frequency", frequency)
        chiff_fade_time = self.properties.chiff_time(base_freq, fade_time)
        if self.max_fade is not None:
            chiff_fade_time = min(chiff_fade_time, self.max_fade)
        self.chiff_fade = Fade(Second(second + bd),
                               Second(second + bd + chiff_fade_time))
        self.chiff_hgain = self.properties.chiff_harmonic_gain(
            frequency / base_freq if base_freq else 1.0)
        # base_frequency is the note fundamental (harmonic 1); use it, not this
        # partial's harmonic frequency, to pick the string count / aftersound.
        aftersound_level, aftersound_dbps = self.properties.aftersound(
            getattr(self, "base_frequency", frequency), self.decay_rate)
        self.sustain = Decay(self.decay_rate, Second(second + bd),
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
            # GATED ON THE BURST, NOT ON THE STATE. This asked `state is Attacking`,
            # which ends when the ATTACK FADE completes -- and the chiff burst is a
            # different, usually longer clock. A snare's attack fade is 12 ms and
            # its burst 90 ms, so from 12 ms on the hump was abandoned and the wash
            # fell through to sustain_jitter: 0.244 against 0.030, an 18.2 dB hole
            # in the noise from 12 to 90 ms. Measured on the rendered snare, the
            # reference was 13-19 dB short of the block engine above 1 kHz -- above
            # its twelve modes, where the sound IS the wash -- and in agreement
            # below it and after 60 ms.
            #
            # synthkernel.c has always keyed this on time (mid < a + chiffS), which
            # is the right clock: the burst is chiff_time, decoupled from the speech
            # fade on purpose. Voices whose two clocks nearly coincide -- the plates,
            # whose bursts are a few ms -- never showed the difference.
            if self.chiff_fade is not None and self.chiff_fade.fade_in(second) < 1.0:
                # chiff_fade (its own short, capped width) -- NOT attack_fade (the
                # slow speech), so a big pipe's chiff is a brief burst, not a long hiss.
                # THE SUSTAINED WASH IS A FLOOR UNDER THE ATTACK HUMP, not a level
                # the hump drops to zero before reaching. The hump r*(1-r) peaks at
                # 0.25 and returns to 0 at chiff_fade's end, and the sustain then
                # began at sustain_jitter -- so any voice whose sustain_jitter is
                # large against 0.25 STEPPED at the join. A closed hi-hat's is 0.400,
                # which is why it was the worst of them. The floor rises with the
                # hump's own progress, so the attack is untouched at t=0 and the two
                # meet exactly where the hump ends.
                #
                # synthkernel.c has done this since the wash was rebuilt; this side
                # never got the same change, and the two renderers disagreed by 13.7
                # dB on a closed hi-hat and 4.4 dB on a snare because of it. Keep the
                # two expressions identical -- see the block marked THE SUSTAINED
                # WASH IS A FLOOR in the kernel.
                s = self.chiff_fade.fade_in(second)  # * self.chiff_fade.fade_out(second)
                r = s ** 0.5
                jitter_fade = max(r * (1.0 - r), self.properties.sustain_jitter * s)
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
                cycle_jitter = rand(second * frequency,
                                    self.properties.chiff_bandwidth) * self.properties.chiff_cycle

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
    # 44100 IS THE PROJECT'S OFFLINE RATE, not a preference. midi.py renders at
    # 44100 and blockrender.SR is 44100; only live.py moves the block engine to
    # 48000, to match the audio device. This default used to be 48000, which no
    # caller ever hit -- midi.py passes the rate explicitly -- but it sat here as
    # a trap for the next one: a sampler built without an argument would have run
    # 8.8% off, which is a semitone and a half of pitch and an eighth of every
    # duration. That is exactly the error that reached Ben's ears as a fast,
    # sharp monocas2, from the same mistake made in an analysis script.
    def __init__(self, sample_rate=44100, sample_depth=16, sample_packing="h"):
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
        # NO DECAY CLAMP. This read `if db > 30: db = 30`, with no rationale and
        # no counterpart in blockrender, which uses harmonic_decay(m) as given.
        # It bit 156 of a closed hi-hat's 224 modes: the bright top of a cymbal
        # decays at 50-200 dB/s and was held to 30, so those modes rang on and
        # came out up to 31 dB hot. That is the whole of the hi-hat overshoot --
        # the modes are the same, their volumes are the same, only their decay
        # was being held back on this side.
        #
        # A fast decay is not a numerical hazard here: db_ratio is evaluated per
        # partial per block, and a partial that has rung out is dropped at the
        # floor (see wave()).
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
        # A MEASURED MODE SET rides the same factor. frequency() computes
        # base * harmonic * inharmonic_stretch, and the partial stores the
        # integer INDEX -- so placing mode m at its measured ratio is exactly
        # a stretch of ratio/m. Doing it here rather than by handing the ratio
        # in as `harmonic` keeps every other use of the index intact.
        mr = properties.mode_ratio(h)
        if mr != h and h:
            self.inharmonic_stretch *= mr / float(h)
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


def _strike_bit(frequency, harmonic):
    """0 or 1 for this mode's strike sign, deterministic in (pitch, mode).

    blockrender draws these from a module RNG seeded once per render, whose
    consumption order this path cannot reproduce -- it builds the same partials
    but not through the same call sequence. A hash of (pitch, mode) gives every
    mode its own sign, the same sign every time, without the two engines having
    to share a stream. The standard is the one blockrender's docstring sets:
    verify by spectrum, not byte-diff, and an incoherent sum is incoherent
    whichever bits it drew.
    """
    h = (int(round(frequency * 16.0)) * 2654435761 + harmonic * 40503) & 0xFFFFFFFF
    return (h >> 13) & 1


class SynthProperties:
    # dB of attenuation for EVEN harmonics, or None to use odd_only absolutely.
    # See series_volume(): a real stopped pipe suppresses its even harmonics,
    # it does not delete them -- measured 24 to 38 dB down on the Iowa clarinet.
    even_harmonic_db = None

    # AN IRREGULAR MODE SET: partials at MEASURED frequencies, not at multiples
    # of anything.
    #
    # Everything else in this file builds a harmonic series and then bends it --
    # inharmonicity_coefficient stretches it, bar_modes picks whole-numbered
    # members out of it. Both assume the body's modes are RELATED to each other.
    # A struck plate, a slotted gourd, a cymbal, a tam-tam: their modes are set
    # by a two-dimensional boundary and fall where they fall. No stretch of a
    # series reaches them, and pushing the inharmonicity up to try only drives
    # the upper partials past Nyquist, thinning the spectrum instead of filling
    # it -- measured on the guiro, where the top 20 spectral bins held 66% of
    # the energy against the recording's 25%.
    #
    # So: mode_ratios is a tuple of multiples of the fundamental, one per
    # partial, taken from a recording. Partial m sits at f0 * mode_ratios[m-1]
    # rather than at f0 * m. Everything indexed by m -- series_volume,
    # harmonic_decay, chiff_harmonic_gain, unison_voices -- keeps working
    # unchanged, because m stays the mode INDEX and only the frequency it maps
    # to changes.
    #
    # None means the old behaviour, which is every voice that has one.
    mode_ratios = None

    # The measured LEVEL of each of those modes, one per entry in mode_ratios.
    # None means the ordinary series_volume applies.
    mode_gains = None

    # ...AND HOW MUCH IT SUPPRESSES THEM DEPENDS ON THE PITCH. A stopped
    # cylinder is only stopped while the tonehole lattice below the first open
    # hole is long enough to act like one; play higher and the lattice is wide
    # open, the bore stops behaving like a closed pipe, and the evens come back.
    # Measured across the whole Iowa clarinet FAMILY -- Bb, Eb and bass, 124
    # notes from C#2 to B6 -- the even-minus-odd balance runs -25.3 dB below C3
    # to +8.1 dB above C6 and crosses zero near 480 Hz. A 33 dB swing: no single
    # constant can describe it, which is why the clarinet's residual used to sit
    # near 6-7 dB in every register at once.
    #
    # It tracks ABSOLUTE frequency, not the instrument's own register break --
    # the bass clarinet crosses zero at the same concert pitch as the Bb rather
    # than an octave lower, which is the one thing a single instrument could not
    # have shown. dB per octave of octave_position; 0.0 is the old behaviour.
    even_harmonic_db_per_octave = 0.0

    from inharmonicity import inharmonicity_coefficient_2nd_harmonic, inharmonicity_coefficient_3rd_harmonic

    # Organ registration: True on the pipe-organ families (flue/reed), whose
    # tones build a full stop-list of ranks (extra octave/fifth partial series)
    # and read a LIVE per-channel gate (drawn stops / crescendo) and swell tilt
    # at render time. False everywhere else -- those voices keep the frozen
    # attack-time channel_volume and a single harmonic series (see init_partials
    # and SynthTone.sum_values). Default off so nothing but organs changes.
    registerable = False
    # The stop word a voice starts on when the score draws none. An organ starts
    # on its 8' foundation (bit 0) and the player draws the rest; a voice that is
    # only ever played in ONE registration -- an orchestra hit is the whole band or
    # it is not a hit -- declares that registration here instead.
    default_stops = 1

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
    # ...and by how much, for voices that fill only partly. See series_volume.
    strike_fill_fraction = 1.0
    strike_depth = 1.0    # how deep the strike comb notches (1=point-strike null, 0=off); the
                          # finite hammer width fills it in, so real pianos want it shallow.

    # The loudspeaker this voice is heard through, by name (see cabinet.py), or
    # None for an instrument that radiates directly. NOT a body: a body belongs
    # in harmonic_volume, which runs before the amplifier pass, and a cabinet
    # has to be after it or the distortion bypasses the speaker.
    cabinet = None

    # Periodic amplitude modulation, downstream of the tone generator. A
    # Wurlitzer's tremolo and a Rhodes suitcase's stereo "vibrato" (which is a
    # PAN, not a vibrato) are the same mechanism: see tremolo.py. depth is what
    # a full modulation wheel asks for, since it is a panel control a player
    # moves while playing; 0 is off, and off is the default for everything.
    tremolo_hz = 0.0
    tremolo_depth = 0.0
    tremolo_stereo = False

    # How hard the valve stage is driven, in units of its own grid bias. 0 is a
    # clean signal path. The tonewheel overrides this with its own discussion.
    amp_drive = 0.0

    # The signal peak, in this renderer's amplitude units, that `amp_drive`
    # is measured against -- so a quiet note reaches less of the valve's curve
    # than a loud one. None means "scale each segment by its own peak", which
    # removes the playing level from the answer entirely: right for a keyboard
    # whose keys are on or off and whose swell pedal is in front of the amp,
    # wrong for anything where how hard you hit it is the point. See
    # tubeamp.emit.
    amp_reference = None

    # How far the push-pull pair is mismatched, or None for tubeamp's own
    # default. This is the difference between a POWER amp and a PREAMP: a
    # balanced pair cancels its even orders exactly (measured, h2 129 dB down),
    # which is a clean, odd-only, square-ish distortion; a single-ended stage
    # cancels nothing and is even-dominant (h2 15.8 dB down, ABOVE h3). A
    # guitar amplifier's gain stages are single-ended, and that asymmetry is
    # most of why an overdriven guitar sounds warm rather than like a fuzz box.
    amp_imbalance = None

    # SYMPATHETIC RESONANCE: the notes nobody hit. 0 = off, which is every
    # voice but one. See sympathetic_partials() below for the mechanism and
    # what the steelpan recording says about it.
    sympathetic_gain = 0.0
    sympathetic_span = 24        # semitones either side to consider
    sympathetic_max = 6          # most responders emitted per struck note
    sympathetic_floor = 0.02     # drop a responder quieter than this
    # 'coincidence' = a responder rings where its modes MATCH the driver's
    # partials, which is resonance and is how a sitar's sympathetic strings
    # and a piano's undamped ones work. 'contact' = the responder is kicked
    # broadband because it shares a body with the driver, and rings at its own
    # modes whatever the interval. Which one an instrument wants is a question
    # about how the two are joined, not a preference.
    sympathetic_mode = 'coincidence'
    # CONTACT ONLY: how fast the kick falls off with distance across the body,
    # in dB per step. Bending waves lose energy crossing the plate, so a near
    # neighbour is driven harder than a far one.
    #
    # DISTANCE IS MEASURED IN FIFTHS, NOT SEMITONES, because that is how a
    # steelpan is laid out: the note areas run round the pan in the cycle of
    # fifths, so the area physically next to C is G and not C#. Semitone
    # distance would make the nearest neighbours a chromatic cluster, which is
    # both wrong about the instrument and wrong about the recording.
    #
    # It is what makes the measured histogram make sense. One step round the
    # cycle is a fifth or a fourth -- 20% and 5% of the measured coupling. TWO
    # steps is a MAJOR SECOND, which is 27%, the largest single cluster and the
    # one a coincidence model cannot explain at all. Four steps is a third or a
    # sixth, 2% and 7%. The energy falls with distance round the cycle, which
    # is distance across the steel.
    sympathetic_falloff = 0.0

    # COINCIDENCE WITH A FIXED SET. A steelpan's responders are "whatever else
    # is on the instrument", so they are named as intervals from the note
    # struck. A sitar's are thirteen TUNED STRINGS at fixed pitches, retuned
    # for the raga and not moving with the melody -- so they are named
    # absolutely, as semitone offsets from `sympathetic_tonic`. Empty = the
    # interval rule above.
    sympathetic_strings = ()
    sympathetic_tonic = 61       # MIDI note of Sa; a sitar is commonly at C#
    # Extra distance for crossing an octave, in the same steps. A tenor pan's
    # inner ring is the octave above its outer one, so an octave is close.
    sympathetic_octave_step = 0.5

    # A TOUCHED NODE. Rest a finger on the string at 1/k of its length and
    # every mode that does NOT have a node there is killed; what is left is the
    # modes that are multiples of k, so the string speaks k times its open
    # pitch with a spectrum of startling purity. That is a guitar harmonic, and
    # it is a different thing from a comb: a comb weights modes, this one
    # DELETES them. 0 = not touched, which is every other voice.
    #
    # The sounding partial m is therefore string mode m*k, and the comb, the
    # roll-off and the pickup all have to be evaluated THERE rather than at m.
    # (The true modes are also stretched by stiffness at m*k rather than m;
    # that part is not modelled, and on a guitar's thin steel it is small.)
    harmonic_touch = 0

    # THE PICKUP IS A SECOND COMB, and it is the other half of what "tone"
    # means on an electric guitar. A magnetic pickup senses the string at a
    # POINT, so it reads mode n with weight sin(n*pi*q) for a pickup q of the
    # way along the speaking length -- the same function strike_point already
    # computes for the pluck. A plucked electric is therefore two combs
    # multiplied, one fixed by the luthier and one chosen by the player's right
    # hand, and moving either is audible.
    #
    # Positions are fractions of the speaking length measured FROM THE BRIDGE,
    # which is where a pickup's position is actually specified. Empty = no
    # pickup, which is every acoustic instrument and the default.
    pickup_points = ()
    # Two entries is a HUMBUCKER: the coils are summed, and where they fall
    # antiphase they cancel, which puts a null at n = 1/(q2-q1) that no single
    # coil has. That, plus the wider aperture below, is why a humbucker is
    # darker -- not the "thickness" it usually gets credited with.
    #
    # Coil aperture, also as a fraction of the length. A coil is not a point:
    # averaging the string over its width multiplies mode n by a sinc, a
    # low-pass in HARMONIC NUMBER. A Stratocaster single coil is ~9 mm on a
    # 648 mm scale, so its first sinc null lands near the 71st harmonic and it
    # barely matters -- which is the physical reason a single coil is bright.
    pickup_width = 0.0
    # A pickup's output is -dPhi/dt, so it reads string VELOCITY and not
    # displacement: a factor of n, +6 dB per octave against an acoustic pluck.
    # Kept explicit rather than folded into tonal_dampening, because the two
    # say different things -- this one is a consequence of magnetism and would
    # otherwise be silently fitted away by the next person to touch the series.
    pickup_velocity = False
    # TURNS PER COIL, relative to the Stratocaster single coil the base electric
    # models (~7,600 turns, ~5.8 kOhm). This is the one thing the model had no
    # way to say, and it is the reason the levels came out wrong.
    #
    # A pickup's output is proportional to its turns, and A BUILDER CHOOSES THE
    # TURNS. That choice is not free: it is made to compensate for exactly the
    # geometry modelled above. A bridge pickup sits where the string moves
    # least, so it is wound hotter -- 6.2 kOhm against a middle coil's 5.8 is a
    # standard Stratocaster set, and a bridge humbucker meant to push a front
    # end goes to 16 kOhm and beyond. Without this the model has the position
    # and the cancellation and none of the compensation, so a bridge humbucker
    # -- the hottest pickup anyone actually fits -- came out 7.7 dB QUIETER
    # than a middle single coil, which inverted GM 30 against GM 29.
    #
    # Per COIL, not per pickup, because the coils are in series (see
    # pickup_gain) and the series sum already supplies the second one. It has
    # to be per coil, too: a humbucker's coils are each SMALLER than a single
    # coil, since two of them have to fit in one pickup's footprint -- ~4,300
    # turns each in a PAF against a Strat's 7,600. A humbucker is hotter
    # because two coils add, not because each one is bigger, and the two
    # effects are different sizes.
    #
    # Resistance stands in for turns at a fixed wire gauge, which is how these
    # are specified and published.
    pickup_turns = 1.0

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
    # The cap, which used to be the literal 0.04 the piano needs -- "so an
    # extreme-bass fff can't bend absurdly". A voice whose pitch transient IS
    # the sound rather than a bloom on it wants far more: a slide up the neck
    # sweeps a fifth, not 68 cents. See GuitarFretNoiseProperties.
    tension_bend_max = 0.04

    # Per-note natural jitter (0 = off). Now that every strike is phase-coherent,
    # two voices on the same pitch would align TOO perfectly (a machine-gun,
    # electronic doubling). Real doublings sit at slightly different pitches (so
    # they BEAT -- a living shimmer, never a persistent cancellation) and strike
    # a hair apart. A random-but-fixed value is drawn PER NOTE in __init__ and
    # shared by all its partials, so the note stays internally coherent (the
    # phase fix is preserved) while different notes decorrelate.
    pitch_jitter_cents = 0.0     # +/- this many cents, random per note (the beat)
    timing_jitter_seconds = 0.0  # 0..this delay to the strike, random per note (stagger)

    # A PLATE STRUCK HARDER IS NOISIER. Measured on the Iowa cymbals: spectral
    # flatness rises by +0.081 on average from mf to ff -- roughly doubling --
    # on every one of the seven plates. Nothing in this file expressed that: a
    # cymbal's timbre, its wash and its wobble were identical at velocity 30 and
    # at 127, so every crash was the same event at a different level. That is
    # what a listener hears as a strike rather than a hit.
    #
    # chiff_volume scales as attack_volume ** strike_noise_slope. 0 (the default)
    # is the old behaviour exactly, so only the voices that set it are affected.
    strike_noise_slope = 0.0

    # THE WOBBLE. Ben, on why a hard crash reads as a hit and not a strike: "the
    # cymbal is literally wobbling around from the drum stick pushing through it
    # vertically." A plate driven that far is nonlinear -- its modes split and
    # shift -- and closely spaced pairs beat. MEASURED in the ring: 7-32% of the
    # envelope at 0.7-3 Hz, and on the same 17" crash the ff take's depth is
    # about DOUBLE the mf's (10.8/16.2/24.2% against 4.9/9.0/13.8% by band).
    #
    # Ours had modulation of about the right depth, from fixed modes beating,
    # but identical at every velocity -- byte-identical at 70 and 127 -- so it
    # could never be the thing that says "hit hard". This adds one detuned voice
    # per partial, beating at strike_wobble_hz, whose GAIN (and so the depth of
    # the beat) scales with how hard the note was struck. 0.0 = off, which is
    # every other voice in this file.
    strike_wobble_hz = 0.0
    strike_wobble_gain = 0.0
    strike_wobble_slope = 1.0

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

    # THE BLOOM. A struck plate does not put all its energy in at the strike: it
    # is driven hard enough to go nonlinear, and energy cascades UPWARD out of
    # the low modes over the following few hundred milliseconds. MEASURED on the
    # Iowa clash pair, when each band reaches its own maximum after the strike:
    #
    #     150-400 Hz    0 ms      1.6-3.2 kHz   347 ms
    #     400-800       0          3.2-6.4      416
    #     800-1600     21          6.4-16         0
    #
    # -- the middle of the spectrum arrives a THIRD OF A SECOND late. Ours put
    # every band in at 0-16 ms, which is a strike; that late arrival is what Ben
    # first described as "a hit with follow-through" and heard the absence of.
    #
    # Modelled as a per-partial onset: partials near bloom_center_hz take
    # bloom_seconds longer to reach full amplitude, falling off over
    # bloom_octaves either side. That is not the cascade's physics -- no energy
    # actually leaves the low modes here -- but it is its audible consequence,
    # and both renderers already carry a per-partial attack (synthkernel's
    # fadeS[] array, and hammer_down below, which is handed each partial's
    # frequency). 0.0 = off, which is every other voice in this file.
    #
    # It is the ATTACK only: hammer_up (the release) deliberately does not use it.
    bloom_seconds = 0.0
    bloom_center_hz = 3000.0
    bloom_octaves = 1.2
    bloom_slope = 0.5      # how much a softer stroke stretches it; 0 = fixed
    bloom_stretch_max = 4.0    # a ghost note blooms at most this much slower
    # HOW STEEP THE SKIRTS ARE. 2.0 is a plain gaussian and was the first shape;
    # its tails reach everywhere, so at 84 ms of bloom it delayed 200 Hz by 15 ms
    # and 16 kHz by 17 -- the whole spectrum late, which softens the attack
    # instead of blooming the middle. A real plate delays its MIDDLE while the
    # low and the high still arrive at once. Higher exponents flatten the top and
    # steepen the sides, so the delay is confined to a band.
    bloom_shape = 2.0
    # HOW LOUD THE LATE ARRIVAL IS, relative to the partial it arrives beside.
    # The cascade ADDS energy to the middle of the spectrum over time; it does
    # not withhold what was there at the strike. Delaying the partial itself
    # withholds -- and since a crash's strike energy IS its middle, that softens
    # the attack by construction: measured, steepening the skirt so the delay
    # landed more squarely on 800-3200 Hz made the attack WORSE, 64 ms -> 100,
    # because the band being delayed is the band that defines the onset. The
    # real plate has its middle at full strength immediately and then gains
    # more. So the bloom is an extra, later copy of the mid partials, and the
    # partials themselves are never delayed. 0 = no late copy.
    bloom_gain = 0.0
    # How long the late copy takes to swell in, as a multiple of its own delay.
    # The kernel already times each partial's decay from its own onset (a =
    # non[p]), so the copy decays from when it arrives; what it lacked was a rise
    # slow enough not to read as a second strike.
    bloom_swell = 1.0
    # HOW SCATTERED THE ARRIVALS ARE, 0 = all together, 1 = anywhere from nothing
    # to twice the delay. A single band of energy rising coherently is a filter
    # sweep, and that is what it sounds like -- Ben: "The left crash is still wah
    # sounding at the beginning." A real cascade is chaotic: energy finds its way
    # up through hundreds of coupled modes, each arriving on its own schedule,
    # and nothing about it is synchronised. Scattering the arrivals turns the
    # sweep back into a swell.
    bloom_scatter = 0.0

    # WHERE THE STICK LANDS DECIDES EACH MODE'S SIGN. A strike excites mode n in
    # proportion to that mode's shape AT THE STRIKE POINT, and a mode shape has
    # nodes and antinodes -- so some modes start pushing and some start pulling.
    # Everything here has always started every partial at phase 0, which is right
    # for an ideal impulse and is why hammer_down resets the accumulator. With a
    # handful of partials it barely matters. With three hundred it matters a lot:
    # they all add at t=0 and the note gets a spike that is an artefact of the
    # synthesis, not of the plate.
    #
    # MEASURED as crest factor -- peak above K-weighted loudness -- against the
    # recordings: the 17" clash is 13.1 dB and our crash 2 was 21.5; the Iowa
    # splash is 14.0 and ours was 20.9. Both are dense sets. Crash 1, which
    # carries a bloom whose late copies raise loudness without raising the peak,
    # was already close at 16.0 against 14.7.
    #
    # 0.0 keeps every partial in phase, which is every other voice in this file.
    # 1.0 gives each mode its own sign, drawn once and deterministically.
    strike_phase_spread = 0.0

    def bloom_delay_for(self, frequency):
        """Seconds this partial ARRIVES LATE. 0 unless the voice blooms.

        A DELAY, not a longer fade, and the difference is the whole mechanism.
        Lengthening the fade leaves the partial's decay clock running from
        note-on, so it is already dying while it fades in and the two cancel:
        measured, a 205 ms fade left LESS energy at 0.35 s than no bloom at all
        (-6.3 dB against -4.7). Delaying the partial moves its fade and its decay
        together, which is what arriving late actually means. Both renderers
        already carry a per-partial start -- blockrender's non_m, which the string
        sections use so the players do not enter together.
        """
        if self.bloom_seconds <= 0.0 or frequency <= 0.0:
            return 0.0
        from math import log, exp
        d = abs(log(frequency / self.bloom_center_hz) / log(2.0) / self.bloom_octaves)
        return self.bloom_seconds * exp(-0.5 * d ** self.bloom_shape)

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
    # HOW WIDE THE WASH IS, as a fraction of the partial's own frequency.
    # rand() is indexed by t*f*granularity, so the phase is redrawn that many
    # times per cycle and the noise it makes is that wide. At the default
    # (rand_granularity, 100000) it is redrawn every sample and the wash is
    # WHITE: every partial's noise is spread flat across the whole spectrum,
    # with nothing left of where it came from. That is fine for a chuff on a
    # pipe, and wrong for a plate -- turning a cymbal's wash up far enough to
    # fill between its modes then fills the notches between its bands too, so
    # the spectrum flattens exactly as fast as the line spectrum fills in.
    # Measured on the closed hat: at chiff_volume 60 the line excess comes right
    # (0.99 dB rms against the recording) and the band profile goes from 1.65 to
    # 5.00 dB wrong, and no setting of the two escapes that trade.
    #
    # A small value keeps each partial's noise AROUND that partial, so the sum
    # over the mode set is a continuum with the plate's own shape. It is also
    # what the physics says: a cymbal's modes are broadened into bands by
    # nonlinear coupling, they are not replaced by hiss.
    #
    # None = the module default, i.e. white, i.e. exactly as every voice
    # rendered before this existed.
    chiff_bandwidth = None
    # The same width expressed in Hz rather than as a fraction of the
    # partial's frequency. Which of the two is right is a physics question
    # -- see the measurement in HiHatProperties.
    chiff_bandwidth_hz = None
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

    # A PLAYER CAN ONLY SOUND ONE NOTE AT A TIME, so notes that OVERLAP belong to
    # different players -- and different players do not share a vibrato phase.
    # That is the same argument unison_voices makes for a section: voices launched
    # from phase 0 sum coherently and sweep a synchronised comb, "which is what a
    # phaser is". A trumpet patch playing a four-note chord is four trumpeters
    # whether or not it was modelled, and until this it gave them ONE phase and
    # ONE rate. Measured on a chord with the wheel up: trumpet 1 distinct phase,
    # violin 28.
    #
    # DEPTH STAYS 0. A trumpet at rest plays dead straight -- orchestral brass
    # barely vibrates at all -- and the kernel skips the whole vibrato branch on
    # vdep == 0, so this costs nothing until the wheel asks for depth. What it
    # hands out is only WHERE in its cycle each note is and HOW FAST, so when the
    # wheel does add depth the notes of a chord are already apart.
    #
    # Keyed on PITCH, as the sections are: a chord decorrelates because its
    # pitches differ, while a repeated or held note keeps its phase and a
    # sustained line stays continuous. The cost is a phase discontinuity when a
    # melodic line changes pitch, where a real player would carry theirs through;
    # it sits under the attack transient, and it is the same approximation the
    # sections already make.
    #
    # Set the spread to 0 for one locked vibrato across everything, which is the
    # right answer for a synth lead and makes the mod wheel a tempo control.
    solo_vibrato_hz = 5.5           # rate the mod wheel vibrates at
    solo_vibrato_spread = 0.035     # +/- fraction of it; 0 = every note locked

    def voice_vibrato(self, frequency, index):
        """(depth_fraction, rate_hz, phase_rad) for one player, or None.

        index 0 is the main voice; 1..n-1 are the extras from unison_voices().
        A section overrides this with real depth (see SectionMixin); one body
        gets rate and phase only, at zero depth.
        """
        if not self.solo_vibrato_spread:
            return None
        midi = int(round(69 + 12 * _log(float(frequency) / 440.0) / _log(2)))
        key = (type(self), midi, index)
        got = _SOLO_VIBRATO.get(key)
        if got is None:
            rng = _random.Random(0x5010 + midi * 64 + index + self._section_salt() * 8191)
            spread = self.solo_vibrato_spread
            got = (0.0,
                   self.solo_vibrato_hz * (1.0 + rng.uniform(-spread, spread)),
                   rng.uniform(0.0, 6.283185307179586))
            _SOLO_VIBRATO[key] = got
        return got

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

    def section_onsets_at(self, frequency):
        """Per-player entry offsets in seconds. None when this voice is not a
        section. See section_onset() for why it is keyed on the pitch.


        On SynthProperties, NOT SectionMixin. It was on the mixin, and the
        reference renderer's hammer_down calls it whenever a partial carries a
        player index -- which every partial does, since the build sets
        `main.player = 0` for one-body voices too. So every NON-section voice
        crashed the reference renderer outright, and the parity checks missed
        it because they were all run on strings and brass, which are sections.
        blockrender guards with hasattr and was unaffected.

        """
        n = getattr(self, 'section_players', 1)
        w = getattr(self, 'section_onset_ms', 0.0)
        if n <= 1 or not w:
            return None
        midi = int(round(69 + 12 * _log(float(frequency) / 440.0) / _log(2)))
        salt = self._section_salt()
        return [section_onset(salt, midi, i, w) for i in range(n)]


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
    # Height of the source above the listener's ear plane, metres (+ = up). Zero
    # for anything standing on the stage floor; a gallery organ, an offstage
    # chorus in a room above, or a raised percussion riser sit above it. Only the
    # ANGLE to the interaural axis matters, so a source directly overhead has no
    # interaural delay at all -- which is exactly why height needs its own axis
    # and cannot be faked with pan.
    position_z = 0.0            # metres

    # ------------------------------------------------------------------ radiation
    #
    # Two things happen between the instrument and the listener that have
    # nothing to do with the listener's head, and both are per-partial:
    #
    #   directivity     an instrument does not radiate equally in all
    #                   directions, and how unequally depends on frequency. A
    #                   bell of radius a is omnidirectional while the wavelength
    #                   is long against it and beams once ka > 1, so a trumpet
    #                   (a = 62 mm, ka = 1 at about 880 Hz) throws its top
    #                   forward and its bottom everywhere.
    #
    #   air absorption  air is a low-pass filter with distance, going roughly as
    #                   f^2. Over a hall it costs a decibel or so at 10 kHz and
    #                   nothing at 1 kHz.
    #
    # Both are properties of the SOURCE and the PATH, so they belong to what the
    # instrument radiates, not to what an ear receives -- which is why they
    # multiply into the object signal and the head model stays separate.
    #
    # Distance: listener_distance is a 2 m stage IMAGE, chosen so the head model
    # gives sensible interaural cues, not a claim about where the players are.
    # Radiation happens over the real room, so it gets its own distance.
    #
    # RECORDING PERSPECTIVE BY DEFAULT. Every room here was first built with the
    # listener where an audience sits, and every one came back too wet -- four
    # times, corrected by ear each time. Ben's scale-space measurement gives the
    # threshold: two sounds interfere harmonically to first order only within
    # about 3 dB of each other, so a reverberant field 3 dB BELOW the direct
    # sound is audible as space without entering the harmony. That is the line
    # between a room and a chord, and it is a criterion rather than a taste.
    # The distance below solves for it (r_c 5.26 m in this hall). A seat in the
    # audience is 12 m and +7.1 dB, which is a real perspective and sometimes
    # the wanted one -- TUNING_DISTANCE=12, or TUNING_WET=+7.
    radiation_distance = 3.73   # metres; -3.0 dB against the direct sound

    directivity_radius = 0.0    # metres; effective radiating aperture, 0 = omni
    directivity_axis_deg = 0.0  # where the instrument points, relative to the
                                # listener (0 = at them, 180 = directly away)
    directivity_floor = 0.25    # -12 dB, and this floor is doing real work.
                                # An ideal piston has true nulls off axis, but
                                # this model has only the direct path: no back
                                # wall, no risers, no reverberant field. In a
                                # hall none of those let a source vanish, and a
                                # listener off the axis of a large bell hears it
                                # through the room rather than not at all. -26 dB
                                # was audibly wrong -- it took a horn one seat
                                # off centre down 25 dB at 4 kHz. Until there is
                                # a reflection model, this is what stands in for
                                # the energy the room returns.

    air_temperature_c = 20.0
    air_humidity_pct = 50.0
    air_pressure_kpa = 101.325

    @staticmethod
    def _bessel_j1(x):
        """J1(x) for x >= 0, Abramowitz & Stegun 9.4.4 / 9.4.6 (~1e-7)."""
        from math import sqrt, cos
        if x < 3.0:
            t = x / 3.0; t2 = t * t
            return x * (0.5 + t2 * (-0.56249985 + t2 * (0.21093573 + t2 * (
                -0.03954289 + t2 * (0.00443319 + t2 * (-0.00031761 + t2 * 0.00001109))))))
        t = 3.0 / x
        f1 = (0.79788456 + t * (0.00000156 + t * (0.01659667 + t * (0.00017105 + t * (
            -0.00249511 + t * (0.00113653 + t * -0.00020033))))))
        th = (x - 2.35619449 + t * (0.12499612 + t * (0.00005650 + t * (-0.00637879 + t * (
            0.00074348 + t * (0.00079824 + t * -0.00029166))))))
        return f1 * cos(th) / sqrt(x)

    def off_axis_angle(self, position_x=None, position_z=None):
        """Angle between where the instrument points and where the listener is.

        The listener is the origin; the player sits at (x, radiation_distance, z)
        and, with directivity_axis_deg = 0, aims into the hall along -y. Yawing
        the axis by psi about the vertical takes it to (sin psi, -cos psi, 0),
        so 180 degrees points directly upstage, away.

        This has to come from the geometry rather than be a per-instrument
        constant: an instrument aimed straight down the hall is still off axis
        to anyone not sitting in front of it, and that -- not the axis angle --
        is what makes a trumpet at the edge of the stage sound different from
        one in the middle.
        """
        from math import pi, sin, cos, sqrt, acos
        x = self.position_x if position_x is None else position_x
        z = self.position_z if position_z is None else position_z
        d = self.radiation_distance
        psi = self.directivity_axis_deg * pi / 180.0
        norm = sqrt(x * x + d * d + z * z) or 1.0
        cos_theta = (-x * sin(psi) + d * cos(psi)) / norm
        return acos(max(-1.0, min(1.0, cos_theta)))

    def directivity_gain(self, frequency, position_x=None, position_z=None,
                         radius=None):
        """Off-axis gain of a piston of radius `directivity_radius`: 2*J1(x)/x
        with x = k*a*sin(theta). Unity below ka ~ 1 at any angle, which is why
        low notes fill a hall from anywhere and high ones have to be aimed.

        `radius` overrides the class value, for a voice whose radiating aperture
        is not fixed -- an organ, where every rank is a different set of pipes."""
        from math import pi, sin
        a = self.directivity_radius if radius is None else radius
        if a <= 0.0:
            return 1.0
        theta = self.off_axis_angle(position_x, position_z)
        x = abs(2.0 * pi * frequency / self.sound_speed * a * sin(theta))
        if x < 1e-6:
            return 1.0
        return max(abs(2.0 * self._bessel_j1(x) / x), self.directivity_floor)

    def air_absorption_db_per_m(self, frequency):
        """ISO 9613-1 atmospheric attenuation, dB/m. No free parameters: it
        follows from temperature, humidity and pressure, and the oxygen and
        nitrogen relaxation frequencies those imply."""
        from math import exp
        T = self.air_temperature_c + 273.15
        T0, T01 = 293.15, 273.16
        pa = self.air_pressure_kpa / 101.325
        psat = 10.0 ** (-6.8346 * (T01 / T) ** 1.261 + 4.6151)
        h = self.air_humidity_pct * psat / pa
        frO = pa * (24.0 + 4.04e4 * h * (0.02 + h) / (0.391 + h))
        frN = pa * (T / T0) ** -0.5 * (9.0 + 280.0 * h
                                       * exp(-4.170 * ((T / T0) ** (-1.0 / 3.0) - 1.0)))
        f2 = frequency * frequency
        return 8.686 * f2 * (
            1.84e-11 / pa * (T / T0) ** 0.5
            + (T / T0) ** -2.5 * (0.01275 * exp(-2239.1 / T) / (frO + f2 / frO)
                                  + 0.1068 * exp(-3352.0 / T) / (frN + f2 / frN)))

    # ------------------------------------------------------------------ the room
    #
    # Distances from the listener to each surface, metres. A shoebox is a coarse
    # hall, but it is enough for the thing that matters here: a reflection is a
    # second look at the SOURCE, taken from a different angle.
    #
    # That is what no sampled instrument can supply. A sample holds one
    # radiation pattern, the one the microphone caught, so a reflected copy of
    # it is the same timbre arriving late. A real trumpet sends a different
    # spectrum at the ceiling than it sends at the listener -- its top beams
    # forward and its bottom does not -- and computing per partial means each
    # image source can be given the spectrum that actually departed toward its
    # wall, absorbed by that wall's material, and aged by the longer trip
    # through the air.
    room_left = 12.0
    room_right = 12.0
    room_front = 18.0        # the wall behind the players
    room_back = 15.0
    room_ceiling = 12.0
    room_floor = 1.2         # ear height above the floor

    # THE MECHANISM LETTING GO -- off unless a voice has one. A plucked
    # keyboard's jack falls back at note-off and its tongue brushes the string;
    # a pipe's valve closing does not do this, which is why the organ has no
    # release chiff and why this cannot simply be chiff run backwards. Chiff is
    # jittered phase ON the note's partials, so it wears the note's spectrum;
    # this is a mechanical event at fixed frequencies whatever note was played.
    release_click_db = None          # level under the note; None = no mechanism
    release_click_modes = ()         # ((Hz, relative amplitude), ...)
    release_click_decay_db = 0.0     # dB/s, tonelib's power convention
    release_click_s = 0.0            # how long the event is allowed to run
    # SLURRED ONSET. When the previous note on this channel ran up to this one,
    # the exciter never stopped: a bow stays on the string, lips and breath stay
    # in the air column, and only the stopped length or the fingering changes.
    # There is no attack to make, so the onset collapses to the time the new
    # pitch takes to settle. A separated note has to establish Helmholtz motion
    # or an air column from nothing, which is what attack_time describes.
    #
    # None = this voice has no exciter to carry over, which is the honest answer
    # for anything struck or plucked -- and for the ORGAN, where the distinction
    # is easy to get wrong: playing an organ legato does not carry anything
    # across, because each pitch is a different pipe with its own valve, and the
    # new pipe must speak in full. Clarinets inherit from ReedOrganProperties
    # here, so setting this on the organ base would have given every rank a
    # legato it cannot have.
    legato_attack_s = None
    reflection_order = 1     # 0 = off; 1 = one bounce off each surface
    reflection_floor_db = -40.0   # drop an image quieter than this, per partial
    # WHERE THE IMAGE MODEL HANDS OVER TO THE STATISTICAL ONE.
    #
    # Under about 50 ms the ear fuses a reflection with the direct sound: it is
    # heard as tone colour and spaciousness, not as a second event, and it has
    # to be rendered as a real delayed copy with a real direction for those cues
    # to exist. Past that limit the same copy is heard as a separate arrival --
    # an echo. Real halls get away with a 60 ms lateral reflection only because
    # hundreds more surround it; ours has SIX first-order images and nothing
    # else, so a late one stands alone and is heard for what it is. Measured on
    # the solo violin: a -19 dB arrival 59 ms after every note, landing in the
    # gap before the next one in a passage of 68 ms notes at 103 ms spacing, and
    # plainly audible as a click.
    #
    # Dropping it costs no energy, because the diffuse tail is not built from
    # what the images left over -- roomtail derives the whole reverberant field
    # from the room constant, and deliberately begins at 2 ms rather than at the
    # mixing time so that it fills the specular comb. The late image is a
    # DUPLICATE of energy the tail already carries, and the only thing it adds
    # is coherence: the tail delivers it decorrelated and dense, which is what a
    # room does, while the image delivers it as an exact replica of the note.
    # So this hands the late energy to the model that renders it correctly and
    # keeps the images for the window where their directionality is the point.
    #
    # In a small room nothing is past the limit and nothing is dropped -- the
    # chamber's latest image is 21 ms -- so this only bites where it should.
    reflection_fusion_s = 0.050   # 0 = keep every image however late

    # Absorption by octave, 125 Hz to 4 kHz, for a wood-panelled hall over an
    # occupied floor. Panelling on an airspace takes the bass through panel
    # resonance; an occupied audience takes very nearly everything, which is why
    # a floor reflection is weak and why halls hang their reflectors overhead.
    SURFACE_ALPHA = {
        'left':    (0.15, 0.11, 0.10, 0.07, 0.06, 0.07),   # wood panelling
        'right':   (0.15, 0.11, 0.10, 0.07, 0.06, 0.07),
        'front':   (0.02, 0.02, 0.03, 0.04, 0.05, 0.05),   # plaster behind the players
        'back':    (0.25, 0.35, 0.45, 0.50, 0.55, 0.55),   # treated, or it slaps back
        'ceiling': (0.02, 0.02, 0.03, 0.03, 0.04, 0.05),   # plaster
        'floor':   (0.60, 0.74, 0.88, 0.96, 0.93, 0.85),   # occupied seating
    }
    # Scattering: the fraction of the reflected energy that leaves in some other
    # direction than the mirror one. This is the term whose absence made the
    # first version sound like a reverberation chamber. A hall's surfaces are
    # articulated -- coffers, niches, balconies, ornament, and an audience is a
    # very rough surface indeed -- and they break a reflection up rather than
    # returning it whole. Scattering rises with frequency, because what scatters
    # a wavelength is a feature about its size.
    #
    # The scattered energy is not destroyed, it just stops being a discrete
    # early reflection and joins the diffuse field. We do not model that field,
    # so it leaves here and does not come back; when a late tail exists, this is
    # what should feed it.
    SURFACE_SCATTER = {
        'left':    (0.15, 0.25, 0.40, 0.55, 0.65, 0.70),
        'right':   (0.15, 0.25, 0.40, 0.55, 0.65, 0.70),
        'front':   (0.05, 0.10, 0.15, 0.20, 0.25, 0.30),
        'back':    (0.30, 0.40, 0.60, 0.70, 0.80, 0.80),
        'ceiling': (0.10, 0.20, 0.35, 0.50, 0.60, 0.65),
        'floor':   (0.50, 0.60, 0.70, 0.80, 0.80, 0.80),
    }
    _ALPHA_HZ = (125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0)

    def _octave_interp(self, table, frequency):
        from math import log
        f = min(max(frequency, self._ALPHA_HZ[0]), self._ALPHA_HZ[-1])
        for i in range(len(self._ALPHA_HZ) - 1):
            lo, hi = self._ALPHA_HZ[i], self._ALPHA_HZ[i + 1]
            if f <= hi:
                t = (log(f) - log(lo)) / (log(hi) - log(lo))
                return table[i] + t * (table[i + 1] - table[i])
        return table[-1]

    def surface_reflection(self, surface, frequency):
        """Pressure coefficient of the SPECULAR reflection: what the surface
        did not absorb, less what it scattered elsewhere."""
        from math import sqrt
        alpha = self._octave_interp(self.SURFACE_ALPHA[surface], frequency)
        scat = self._octave_interp(self.SURFACE_SCATTER[surface], frequency)
        return sqrt(max(0.0, 1.0 - alpha)) * sqrt(max(0.0, 1.0 - scat))

    WALLS = (('left', 0, 'room_left', -1), ('right', 0, 'room_right', 1),
             ('back', 1, 'room_back', -1), ('front', 1, 'room_front', 1),
             ('floor', 2, 'room_floor', -1), ('ceiling', 2, 'room_ceiling', 1))

    def image_sources(self, sx, sy, sz, order=None):
        """Every image up to `order` bounces: (surfaces, image, mirrored listener).

        Two mirrors are needed, not one. Mirroring the SOURCE gives the image
        whose straight line to the listener has the right length and the right
        arrival direction. Mirroring the LISTENER gives the direction the sound
        actually departed in, which is what the instrument's directivity must be
        read at -- the ray leaves toward the mirrored listener, not toward the
        real one. Using the arrival direction for both would ask a trumpet how
        loud it is toward the audience and then use that for the ceiling.

        AT SECOND ORDER AND ABOVE THE LISTENER IS MIRRORED IN REVERSE. For a
        path source -> A -> B -> listener the image of the source is A then B,
        but the ray leaves toward B mirrored first and then A: the departure
        direction is set by the FIRST surface the ray meets, and that is the
        last one applied to the listener. Getting this backwards reads the
        instrument's directivity toward the wrong wall, which is silent -- the
        delay and the level stay right and only the colour is wrong.

        AN IMAGE IS A PLACE, NOT A SEQUENCE. Mirroring in two PERPENDICULAR
        planes commutes, so floor+left+floor lands exactly where left alone
        does -- the two floor mirrors cancel -- and at third order 186
        sequences reach only 62 distinct positions. Counting them all is not
        merely wasteful: each duplicate is emitted as another partial at the
        same delay, so a single floor bounce arrives five times and is five
        times too loud, and the absorption charged to it is whatever sequence
        happened to be enumerated. Deduplicate by POSITION, keeping the first
        sequence to reach it -- which is the shortest, since this walks breadth
        first, and the shortest is the path the sound actually takes.
        """
        order = self.reflection_order if order is None else order
        if order <= 0:
            return []
        walls = [(nm, ax, sgn * getattr(self, attr))
                 for nm, ax, attr, sgn in self.WALLS]
        by_name = {nm: (ax, pl) for nm, ax, pl in walls}

        def mirror(p, axis, plane):
            q = list(p)
            q[axis] = 2.0 * plane - q[axis]
            return tuple(q)

        out = []
        seen = {tuple(round(v, 4) for v in (sx, sy, sz))}
        frontier = [((), (sx, sy, sz))]
        for _ in range(int(order)):
            nxt = []
            for names, img in frontier:
                for nm, ax, pl in walls:
                    if names and names[-1] == nm:
                        continue
                    seq = names + (nm,)
                    im = mirror(img, ax, pl)
                    key = tuple(round(v, 4) for v in im)
                    if key in seen:
                        continue
                    seen.add(key)
                    lis = (0.0, 0.0, 0.0)
                    for back in reversed(seq):
                        a2, p2 = by_name[back]
                        lis = mirror(lis, a2, p2)
                    out.append((seq, im, lis))
                    nxt.append((seq, im))
            frontier = nxt
        return out

    def reflection_terms(self, frequency, sx, sy, sz, radius=None):
        """[(gain relative to the direct sound, extra delay s, image xyz)].

        Every factor is frequency-dependent and so belongs to the partial, not
        the note: how much the instrument sent that way, what the surface kept,
        and what the longer path cost in air.
        """
        from math import sqrt
        if not self.reflection_order:
            return []
        direct = sqrt(sx * sx + sy * sy + sz * sz) or 1e-9
        direct_dir = self.directivity_gain(frequency, sx, sz, radius) or 1e-9
        air = self.air_absorption_db_per_m(frequency)
        floor = 10.0 ** (self.reflection_floor_db / 20.0)
        out = []
        for names, image, mirrored in self.image_sources(sx, sy, sz):
            path = sqrt(sum(c * c for c in image)) or 1e-9
            # Directivity toward where the ray actually left: the mirrored
            # listener, at the same range as the real one so only angle differs.
            scale = direct / (sqrt(sum((m - s) ** 2 for m, s in
                                       zip(mirrored, (sx, sy, sz)))) or 1e-9)
            ax = (mirrored[0] - sx) * scale
            az = (mirrored[2] - sz) * scale
            depart = self.directivity_gain(frequency, ax, az, radius)
            kept = 1.0
            for nm in names:
                kept *= self.surface_reflection(nm, frequency)
            gain = ((direct / path)
                    * kept
                    * (depart / direct_dir)
                    * 10.0 ** (-(air * (path - direct)) / 20.0))
            if gain < floor:
                continue
            delay = (path - direct) / self.sound_speed
            # Past the fusion limit the diffuse tail already carries this, and
            # carries it decorrelated instead of as a replica of the note.
            if self.reflection_fusion_s and delay > self.reflection_fusion_s:
                continue
            out.append((gain, delay, image))
        return out

    _Q_CACHE = {}

    def sphere_mean_directivity(self, frequency, radius=None):
        """<D^2> averaged over the whole sphere, for the piston pattern.

        The tail needs the power an instrument sends into the ROOM, which is its
        average over every direction -- not the one value pointing at the
        listener. A trumpet aimed down the hall is loud here and quiet
        everywhere else, so using what arrives at the listener as the reverb
        send credits it with power it never radiated.

        The pattern is axisymmetric about the bell, so the average is a single
        integral in the polar angle with the sin(theta) area weight.
        """
        a = self.directivity_radius if radius is None else radius
        if a <= 0.0:
            return 1.0
        key = (round(a, 5), round(frequency, 1), round(self.directivity_floor, 3))
        got = self._Q_CACHE.get(key)
        if got is not None:
            return got
        from math import pi, sin
        k = 2.0 * pi * frequency / self.sound_speed
        n = 180
        total = 0.0
        weight = 0.0
        for i in range(n):
            theta = (i + 0.5) * pi / n
            s = sin(theta)
            x = abs(k * a * s)
            d = 1.0 if x < 1e-6 else max(abs(2.0 * self._bessel_j1(x) / x),
                                         self.directivity_floor)
            total += d * d * s
            weight += s
        got = total / weight if weight else 1.0
        self._Q_CACHE[key] = got
        return got

    def directivity_factor(self, frequency, position_x=None, position_z=None,
                           radius=None):
        """Q: how much louder this instrument is toward the listener than its
        own spherical average. 1.0 for an omnidirectional source, and the
        quantity the room constant wants when it sets the reverberant field
        against the direct sound."""
        mean = self.sphere_mean_directivity(frequency, radius)
        if mean <= 0.0:
            return 1.0
        d = self.directivity_gain(frequency, position_x, position_z, radius)
        return (d * d) / mean

    def radiation_gain(self, frequency, position_x=None, position_z=None,
                       radius=None):
        """What survives the trip: directivity times air absorption over
        radiation_distance. A linear amplitude factor, per partial."""
        db = self.air_absorption_db_per_m(frequency) * self.radiation_distance
        return (self.directivity_gain(frequency, position_x, position_z, radius)
                * (10.0 ** (-db / 20.0)))

    # Decay rate scaling per octave (times harmonic_decay). 0 = register-flat; the
    # piano sets it > 0 so the bass rings long and the treble decays fast.
    decay_register_slope = 0.0

    # DO THIS VOICE'S EXTRA VOICES BELONG TO THE PART RATHER THAN THE NOTE?
    # Almost nothing does: a chorus, a section and a set of sympathetic strings
    # all belong to the note that excited them and stop when it does. A DRONE
    # does not -- it sounds from the moment the bag is under pressure until the
    # player stops, and the melody happens over the top of it. When this is set
    # the renderer emits unison_voices ONCE for the channel, spanning its whole
    # range, instead of once per note.
    unison_spans_part = False

    # ...and how long a gap ENDS one of those parts. A bagpipe's drones follow
    # the played phrases, not the channel's whole lifetime: a piper does not
    # stop for a two-bar rest and does not keep the bag up through a section
    # off. In SECONDS, because that is what the decision is about.
    part_break_s = 2.0

    # HOW MUCH OF A NOTE MAY BE ATTACK. Almost always well under half: an onset
    # that outlasts the note it is opening is not an onset, and blockrender has
    # capped it at 0.45 of the duration since it was written -- which keeps a
    # short note speaking in time and is right for every acoustic voice here.
    #
    # A REVERSE CYMBAL IS THE EXCEPTION, and it is why this is a property rather
    # than a constant. Its envelope IS the attack: a tape played backwards rises
    # for the whole of its length and then stops, so capping the rise at 45%
    # leaves it rising, then sitting, then ending -- which is a swell, not a
    # reversal. See ReverseCymbalProperties.
    attack_fraction_max = 0.45

    # AND HOW LATE AN EXTRA VOICE MAY ENTER, as a fraction of the note. The
    # renderer caps a section player's entry at 0.25 of the duration so that a
    # scattered entrance cannot begin after a short note has ended, which is
    # right for a section and for an echo. A REPEATEDLY STRUCK BELL is the
    # exception: a telephone's clapper hits twenty times a second for as long as
    # the ring lasts, so its strikes must span the whole note and not its first
    # quarter. See TelephoneRingProperties.
    unison_onset_fraction_max = 0.25

    # WHAT THE WRITTEN NOTE MEANS, in octaves. Zero for every instrument: a
    # written C sounds a C. A HELICOPTER is not an instrument -- its "pitch" is
    # a blade passing rate of ten or twenty a second -- so the written note
    # chooses the ROTOR and a C4 must sound four octaves down. See
    # HelicopterProperties.
    #
    # It has to be honoured by the RENDERER and not by the class, which is the
    # mistake this replaced: scaling the frequency in __init__ changed the
    # props' own octave_position and every register law reading it, and left the
    # partial frequencies exactly where they were, because blockrender builds
    # those from its own f0. The measured result was a helicopter whose lowest
    # partial was 261 Hz. Inheriting a thing is not the same as it reaching the
    # output, for the fifth time in this file.
    sounding_octaves = 0.0

    # DOES THE KEY SET THE LOUDNESS? On most instruments, yes: how hard you
    # strike, pluck or blow IS the dynamic. On some it does not and cannot --
    # a harpsichord's key trips a jack and the quill plucks with a force the
    # jack decides, which is exactly why the instrument has two manuals and a
    # registration instead of a crescendo. An organ key opens a pallet valve
    # and the wind pressure does the rest; a harmonium's and an accordion's
    # loudness is in the bellows, not the keyboard.
    #
    # ONLY attack_volume IS NEUTRALISED, never channel_volume. Velocity is the
    # KEY and CC7/CC11 are the CHANNEL, and they are separate factors in gain
    # below -- so a fixed-volume patch still balances in a mix, still follows an
    # expression pedal, and still swells. That is not a compromise to keep mix
    # control: it is what the instrument does. CC11 on an organ IS the swell
    # box, and on an accordion it is the bellows.
    touch_sensitive = True

    # AN INSTRUMENT'S OWN SCALE, where it has holes rather than a keyboard.
    # Empty means "use the temperament", which is every voice that can play a
    # chromatic scale at all -- almost all of them.
    #
    # A TEMPERAMENT IS A COMPROMISE BETWEEN KEYS, and an instrument that cannot
    # change key has no reason to make it. A chanter's holes are cut once, in
    # one place, for one tonic; a recorder's, a tin whistle's and a shawm's
    # likewise. What they are cut FOR is a set of intervals that beat cleanly
    # against the instrument's own drone or its own fundamental, which is not
    # what twelve equal semitones give. So the scale is expressed as CENTS FROM
    # THE INSTRUMENT'S TONIC, and the tonic itself still follows the render's
    # temperament -- the pipe plays with the band, and plays itself in tune.
    #
    # Same argument and same mechanism as the brass intonation in blockrender,
    # which takes a trumpet's pitch from the valve combination rather than from
    # the scale. A degree absent from the table keeps the temperament's pitch:
    # the sequencer has asked for a note the instrument does not have, and
    # silently moving it somewhere else would be worse than sounding it.
    scale_tonic_note = None     # MIDI note of the instrument's tonic
    scale_cents = None          # {semitones from tonic: cents from tonic}

    # CC64. Does this voice have anything for a damper pedal to lift?
    #
    # THE QUESTION IS THE EXCITATION, NOT THE KEYBOARD. A pedal is only
    # meaningful on a voice that would still be ringing when the key comes up:
    # a struck or plucked string rings, and the felt is the only thing that
    # stops it, so lifting the felt is the whole effect. A DRIVEN voice -- a
    # bowed string, a blown pipe, an organ rank -- stops when the excitation
    # stops, and there is no damper anywhere on the instrument to lift. CC64 on
    # such a channel is a sequencer's habit, and honouring it holds a violin
    # note at full bow with nobody bowing it. (Measured: A-Team.mid pedals its
    # bowed-string channel six times.)
    #
    # A SYNTHESISER IS THE OTHER CASE and keeps it. There is no damper there
    # either, but a pedal on a synth holds the GATE, which is a real control a
    # player really has and a sequencer really means. So the default is True
    # and the refusals are the acoustic driven families, named one by one.
    damper_pedal = True

    # CAN THIS VOICE BE BENT? Only a MOVING bend asks -- a static one is a
    # tuning and every voice takes it, which is what lets a harpsichord carry
    # a temperament written as pitch bend (bwv847.mid is written that way).
    # This flag is about the gesture.
    #
    # A struck bar has no pitch control after the strike; a pallet valve is
    # open or shut; a tonewheel runs off a synchronous motor on the mains; a
    # free reed's pitch is its own mass; a bag holds one pressure. A string
    # under a finger, a lip on a mouthpiece and a breath across a reed all
    # bend, which is most of the bank.
    pitch_bendable = True

    # CC67, the soft pedal. How many strings the una corda shift TAKES AWAY.
    #
    # NOT A FILTER AND NOT AN ATTENUATOR. On a grand the whole action slides
    # sideways so the hammer strikes two strings of three -- and quieter, and
    # different in colour, both fall out of that. The remaining pair beats
    # against itself differently from the trio, and that changed beating is
    # what a pianist is actually reaching for; the drop in level is a side
    # effect they usually have to play against.
    #
    # 0 is "this instrument has no soft pedal", which is nearly everything. It
    # also does nothing in the bass by construction, where a piano has one or
    # two strings to begin with -- which is correct: the shift only affects
    # trichord notes.
    soft_pedal_strings = 0

    # CC5/CC65/CC84, portamento: WHICH MECHANISM CARRIES THE GLIDE.
    #
    # Not a boolean, because pitch_bendable is the wrong question. A trumpet is
    # bendable and still cannot lip a glide of a fifth -- it blows through the
    # harmonics instead, which is a different gesture that sounds different, and
    # a flag cannot say so. None means the instrument has no way to move
    # continuously between two pitches at all, and CC5/65/84 do nothing on it,
    # exactly as CC64 does nothing without a damper.
    #
    #   'slide'    a continuous length: a trombone, a slide whistle
    #   'stop'     a stopped string: the violin family, a fretless bass
    #   'valve'    the harmonic lattice: trumpet, horn, tuba (brass_fingering)
    #   'circuit'  an analogue lag: the synthesisers, which model no mechanism
    #
    # AND THE GLIDE IS EXPONENTIAL IN LENGTH, NOT IN PITCH. A slide, a finger
    # and a plunger all move a LENGTH, and f is 1/L. A hand settling toward its
    # target position therefore gives a frequency curve that ACCELERATES in
    # cents going up and DECELERATES going down -- the same hand, the same
    # speed, an asymmetry a synthesiser does not have. GuitarFretNoiseProperties
    # made half of this argument already ("a hand is fastest when it leaves and
    # stops when it arrives"); this is the other half, and the settle is in the
    # coordinate the hand actually moves along. The kernel does the reciprocal.
    glide_mechanism = None

    # CC71-78, GM 2's SOUND CONTROLLERS: which of them this instrument has the
    # mechanism for. They are knobs on a subtractive synth -- brightness is a
    # filter cutoff, resonance its Q, attack and release envelope times -- and a
    # physical model has no filter to turn. So each lands only where the
    # instrument has the thing it names, and the rest are refused the way a bend
    # or a damper is (see sound_controls_of, which also removes everything from
    # a registerable instrument and all but decay from a one-shot):
    #
    #   brightness   effort, on the voices with an effort-to-colour law; the
    #                filter corner on a synthesiser
    #   resonance    a synthesiser's filter Q; a mute's resonance
    #   attack       an onset that takes time: breath, bow, a synth envelope
    #   decay        a ring: a struck or plucked string, a synth's filter decay
    #   release      what a sustaining note does when the key comes up
    #   vib_rate, vib_depth, vib_delay   a player's vibrato
    #
    # Empty by default: an instrument answers nothing it has not been given.
    sound_controls = frozenset()

    # How far the mechanism physically reaches, in semitones. None is unbounded:
    # a synth has no arm, and a valved gliss walks the harmonic series rather
    # than reaching for anything.
    glide_reach_semitones = None

    def __init__(self, frequency=256.0, channel_pan=0.0, attack_volume=1.0, channel_volume=1.0,
                 effort=0.0):
        # effort must be known BEFORE attack_dampening is computed below, which
        # is why it is a constructor argument and not an attribute set after.
        if effort:
            self.effort = effort
        self.channel_pan = channel_pan
        self.attack_volume = attack_volume
        self.channel_volume = channel_volume

        # Strike force -> noise. See strike_noise_slope above. attack_volume is
        # already the GM2/DLS square-law velocity, so this is per NOTE, not a
        # class-wide setting, and it is why it has to happen in the constructor.
        if self.strike_noise_slope and self.chiff_volume:
            av = max(float(attack_volume), 1e-3) ** self.strike_noise_slope
            self.chiff_volume = self.chiff_volume * av
            # AND THE JITTER WITH IT. Ben: "Not just a wobble, but jitter would
            # increase, yes?" -- yes: a plate driven hard has its modes decohere,
            # not merely swing, so the RING gets noisier too and not just the
            # strike. MEASURED: the hard-struck takes carry 1.49x the ring
            # flatness of the soft ones. sustain_jitter is that floor, and it was
            # a fixed number, so the ring was equally coherent however it was hit.
            self.sustain_jitter = self.sustain_jitter * av

        # Strike force -> wobble. One extra voice per partial, offset by a couple
        # of Hz so it beats in the measured band; its gain, which is what sets the
        # depth of the beat, follows the strike. See strike_wobble_hz above.
        # Strike force -> bloom. The cascade is a NONLINEAR effect: it only
        # happens when the plate is driven hard enough to leave the linear
        # regime, so a soft stroke should not bloom at all. Measured across the
        # nine crash takes the mid-band delay is 139, 267, 139, 53 and 416 ms --
        # real, but only two of nine over 150 -- so this is sized to the median
        # of the crashes and left to the top of the velocity range.
        if self.bloom_seconds > 0.0 and self.bloom_slope:
            # A HARDER STRIKE BLOOMS FASTER, not slower. Ben: "the bloom length
            # should be shorter in proportion to attack velocity." The cascade is
            # nonlinear, so the harder the plate is driven the quicker energy
            # finds its way up -- a stick hit cascades almost at once, a soft
            # mallet stroke swells. This was the wrong way round: bloom_seconds
            # was MULTIPLIED by attack_volume**1.5, so a full-velocity crash got
            # the longest swell of all, which is why crash 1 sounded mallet-struck
            # at velocity 127. bloom_seconds is now the delay at FULL velocity --
            # the shortest it ever is -- and softer strokes stretch it, capped so
            # a ghost note does not arrive a second late.
            av = max(float(attack_volume), 1e-3) ** -abs(self.bloom_slope)
            self.bloom_seconds = self.bloom_seconds * min(av, self.bloom_stretch_max)

        if self.strike_wobble_hz > 0.0 and self.strike_wobble_gain > 0.0:
            self.unison_detune = (self.strike_wobble_hz,)
            self.unison_gain = self.strike_wobble_gain * (
                max(float(attack_volume), 1e-3) ** self.strike_wobble_slope)

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
        if self.tension_bend:
            # SIGNED. A string or a drumhead goes SHARP when it is struck, because
            # striking it raises the tension it is tuned by. A shallow curved
            # shell goes FLAT -- see SteelPanProperties -- so the cap and the
            # register scaling work on the magnitude and the sign rides through.
            _tbs = 1.0 if self.tension_bend > 0.0 else -1.0
            self.tension_bend = _tbs * min(self.tension_bend_max, abs(self.tension_bend)
                * (self.tension_bend_ref_hz / float(frequency)) ** self.tension_bend_slope)

        if self.inharmonicity_dynamic:
            self.inharmonicity_coefficient *= (1.0 + abs(self.octave_position))

        if self.octave_modulo:
            from math import floor
            self.attack_dampening = self.tonal_dampening + floor(self.octave_position) * self.octave_dampening
        else:
            self.attack_dampening = self.tonal_dampening + self.octave_position * self.octave_dampening

        # Effort flattens the ladder (see effort_tilt). Subtracted, because a
        # SMALLER attack_dampening is a brighter voice. attack_dampening is in
        # units of dB-per-doubling / 6.02, and both effort and effort_tilt are
        # in dB, so the conversion happens here.
        if self.effort_tilt and self.effort:
            self.attack_dampening -= (self.effort_tilt * self.effort) / 6.0206

        # Per-note even-harmonic balance (see even_harmonic_db_per_octave).
        # Instance attribute, so series_volume picks it up without the class
        # attribute moving underneath every other note.
        if self.even_harmonic_db is not None and self.even_harmonic_db_per_octave:
            self.even_harmonic_db = (self.even_harmonic_db
                                     + self.even_harmonic_db_per_octave * self.octave_position)

        # attack_volume = per-note velocity gain, channel_volume = CC7*CC11
        # channel gain, both already squared to the MIDI (V/127)^2 law.
        # touch_sensitive: a key that only trips a jack or opens a valve does not
        # set the level. channel_volume is untouched -- see the note on the flag.
        _touch = self.attack_volume if self.touch_sensitive else 1.0
        self.gain = (self.initial_gain * db_amplitude(self.octave_gain * self.octave_position)
                     * db_amplitude(self.register_effort() + self.projection_db)
                     * _touch * self.channel_volume)

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

    def hrtf_at(self, position_x, position_z=None, position_y=None):
        """Per-ear (left_inc, right_inc, left_delay, right_delay) for a source at
        position_x metres (+ = right) and position_z metres (+ = up), via the
        Woodworth ITD on a spherical head. Factored out of __init__ so a
        registerable voice can place each rank at its own case position without
        rebuilding the note.

        Both ears lie on the x axis, so the only thing either one asks of a
        source is its angle to that axis -- which is the direction cosine along
        x, whatever the source's height. Writing it that way rather than as an
        azimuth generalises to three dimensions for free and is exactly the old
        two-dimensional result when position_z is 0: there
        sin(atan2(x, y)) == x / sqrt(x**2 + y**2).
        """
        from math import sqrt, acos, cos, pi
        z = self.position_z if position_z is None else position_z
        y = self.listener_distance if position_y is None else position_y
        distance = max(sqrt(position_x ** 2 + y * y + z * z), self.head_radius)
        base_delay = distance / self.sound_speed
        cos_to_right = position_x / distance
        def woodworth(cos_theta):
            # incidence angle between the source ray and the ear axis
            theta = acos(max(-1.0, min(1.0, cos_theta)))
            offset = -cos(theta) if theta <= pi / 2 else (theta - pi / 2)
            return theta, base_delay + offset * self.head_radius / self.sound_speed
        li, ld = woodworth(-cos_to_right)
        ri, rd = woodworth(cos_to_right)
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

        # A measured mode set answers directly: no series, no comb, no tilt.
        if self.mode_gains is not None:
            if 1 <= harmonic <= len(self.mode_gains):
                return self.gain * self.mode_gains[harmonic - 1]
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

        # A touched harmonic sounds string mode m*k as its mth partial.
        sm = harmonic * self.harmonic_touch if self.harmonic_touch else harmonic
        if self.harmonic_touch and self.max_harmonic and sm > self.max_harmonic:
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
                # HOW MUCH the felt flattens, not merely whether it does. A
                # softly-voiced hammer spreads almost completely at ff and its
                # notch disappears; a hard, lacquered one barely spreads at all
                # and keeps the notch at every dynamic. 1.0 is the soft case and
                # the default, so nothing that had the boolean alone moves.
                depth *= (1.0 - self.strike_fill_fraction * self.attack_volume)
            comb = (1.0 - depth) + depth * abs(_sin(sm * _pi * self.strike_point))
        else:
            comb = _pluck_comb(self.plucked_harmonic, self.pluck_dampening, harmonic)

        v = self.gain / (sm ** self.attack_dampening) * comb
        if self.pickup_points:
            v *= self.pickup_gain(sm)
        if harmonic % 2 == 0 and self.even_harmonic_db is not None:
            v *= 10.0 ** (self.even_harmonic_db / 20.0)
        return v

    def pickup_gain(self, harmonic):
        """What a magnetic pickup reads of mode n. 1.0 for anything without one."""
        if not self.pickup_points:
            return 1.0
        # Summed, not averaged in amplitude: two coils in series ARE one
        # signal, and their cancellation is the humbucker's null.
        #
        # THE COMMENT SAID THIS AND THE CODE DIVIDED BY len(pickup_points)
        # ANYWAY, which is the averaging it disclaims -- a flat -6.02 dB on
        # every humbucker, taking away the second coil's contribution while
        # keeping its cancellation. The turns scale below is what sets the
        # level now, and it is per coil, so the series sum belongs here.
        g = abs(sum(_sin(harmonic * _pi * q) for q in self.pickup_points))
        if self.pickup_turns != 1.0:
            g *= self.pickup_turns
        if self.pickup_width:
            x = harmonic * _pi * self.pickup_width
            if x > 1e-9:
                g *= abs(_sin(x) / x)
        if self.pickup_velocity:
            g *= harmonic
        return g

    def harmonic_volume(self, harmonic):
        """What leaves the instrument: the body's series, shaped by the bore."""
        v = self.series_volume(harmonic)
        if v == 0.0 or not self.bore_corner_hz:
            return v
        f0 = self.frequency_x * (2.0 ** self.octave_position)
        # mode_ratio, not `harmonic`: with a measured mode set the partial does
        # NOT sit at f0*m, and the bore filter has to be evaluated where the
        # partial actually is. Identity for every harmonic voice.
        return v * self.bore_gain(f0 * self.mode_ratio(harmonic)) * self._bore_norm()

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

    # EFFORT: HOW HARD THE PLAYER IS WORKING, AS A TIMBRE AND NOT A LEVEL.
    #
    # Blow harder and a brass instrument does not merely get louder, it gets
    # BRIGHTER -- the nonlinear steepening in the bore feeds the upper harmonics
    # far faster than the fundamental. Until now velocity was a pure gain for
    # every wind, brass and bowed voice in this file (only the piano's hammer
    # changed colour with force), so a trumpet at velocity 127 was the identical
    # timbre to one at velocity 20.
    #
    # MEASURED on the Iowa tenor trombone across pp/mf/ff, 33 notes with all
    # three dynamics. The harmonic ladder FLATTENS with effort:
    #
    #     pp -> mf   +12.32 dB louder, tilt +7.71 dB   0.63 dB per dB
    #     mf -> ff    +7.98 dB louder, tilt +4.55 dB   0.57 dB per dB
    #     pooled      tilt = 0.80 x level - 2.01,  r = 0.65
    #
    # so roughly 0.6 dB of ladder flattening per dB of loudness. effort_tilt IS
    # that slope, in dB of flattening per dB of level, and `effort` is the level
    # deviation in dB from the dynamic this class was fitted at. Both are in dB;
    # attack_dampening is dB-per-doubling / 6.02, so __init__ converts.
    #
    # IT IS A FAMILY PROPERTY, NOT A UNIVERSAL ONE. Measured the same way:
    #
    #     tenor trombone   +0.68 dB/dB   r 0.66
    #     French horn      +0.44         r 0.35
    #     Bb clarinet      +0.13         r 0.29
    #
    # which is the difference every player knows -- brass blooms with effort and
    # a clarinet very nearly does not. So this belongs on the family base.
    #
    # WHAT DRIVES IT IS A RELATIVE SIGNAL, NEVER ABSOLUTE VELOCITY. In real MIDI
    # a track's velocities are largely set to balance that instrument against
    # the others, so mapping brightness to raw velocity makes every
    # conservatively mixed brass track permanently dull. Effort comes from
    # DEVIATION -- velocity against a running per-channel baseline, aftertouch
    # (which is a deviation by construction), CC1/CC11, and register position
    # past the comfortable centre. Absolute level stays in channel_volume and
    # attack_volume, where it already is.
    #
    # 0.0 is the old behaviour, and every voice fitted at mf keeps its fit:
    # effort 0 means "the dynamic this class was measured at".
    effort_tilt = 0.0
    effort = 0.0

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

    def mode_ratio(self, m):
        """Where partial m actually sits, as a multiple of the fundamental.

        m for a harmonic series; the measured ratio for a body whose modes are
        not related to each other (see mode_ratios).
        """
        r = self.mode_ratios
        if r is None:
            return float(m)
        return r[m - 1] if 1 <= m <= len(r) else 0.0

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
        # DAMPING SCALES WITH FREQUENCY, NOT WITH AN INDEX. For a harmonic
        # series those are the same number, which is why this took `harmonic`
        # directly. With a measured mode set they are not: a closed hi-hat's
        # modes run from ratio 1 to ratio 64, and indexing gave its 222 Hz mode
        # a T60 of 0.83 s against 0.40 for its 14 kHz one -- a 2:1 spread where
        # a real cymbal is ten times that, so the weak low mode outlived the
        # strong 4.7 kHz one that actually carries the sound. Measured against
        # the recording it put 10 dB too much energy below 500 Hz and 7 dB too
        # little above 3 kHz: a bright tick rendered as a dull one.
        #
        # The fourth place in this file that assumed f = f0 * m, after the
        # partial-frequency computation, harmonic_volume and _hf_rolloff.
        # Identity for every harmonic voice.
        h = self.mode_ratio(harmonic) if self.mode_ratios is not None else harmonic
        base = self.decay_db + self.harmonic_decay_db * h * (h ** self.harmonic_decay_dampening)
        # Register-dependent decay: heavy bass strings ring far longer than the
        # light, heavily-damped treble. decay_register_factor (set in __init__ from
        # decay_register_slope) is < 1 in the bass (slower) and > 1 in the treble.
        return base * self.decay_register_factor


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
        g /= 1.0 + (partial_hz / self.bore_corner_hz) ** self.bore_order
        # A BODY THAT SMALL CANNOT RADIATE THAT LOW. Below its lowest air mode a
        # violin family box stops coupling to the room, and the fundamental goes
        # with it: the Iowa cello's low C has its fundamental 11.2 dB BELOW its
        # strongest partial, where a monotonic model makes h1 the strongest by
        # construction. Same highpass SynthProperties.bore_gain uses for a brass
        # bell, which FormantBody had been dropping. No-op at 0, which is what
        # every voice that had formants before this line was written has.
        if self.bell_cutoff_hz:
            x = (partial_hz / self.bell_cutoff_hz) ** self.bell_order
            g *= x / (1.0 + x)
        return g


class PluckedStringProperties(SynthProperties):
    # CC71-78: a plucked string: how long it rings, and how it is damped.
    sound_controls = frozenset(('decay', 'release'))
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
class HarpsiBase(FormantBody, PluckedStringProperties):
    """Shared harpsichord physics. A plucked string released from a triangular
    displacement at fraction p of its length feeds mode n with amplitude
    ~ |sin(n*pi*p)| / n^2: a 1/n^2 rolloff times a COMB that nulls every harmonic
    at multiples of 1/p. The plucking point p is therefore the whole character of
    a harpsichord -- and, because a quill is hard and narrow and plucks at fixed
    force, the notch never fills the way a piano's felt hammer fills it
    (strike_fills_with_force = False). That fixed force is also why the instrument
    has no dynamics, which is what makes it a REGISTERED instrument.
    """
    # A quill plucks; there is no way to lean on a note afterwards.
    # (A STATIC bend still applies -- that is a temperament, and
    #  bwv847.mid is written that way.)
    pitch_bendable = False
    # The dampers are on the jacks and there is no pedal to lift them.
    damper_pedal = False
    # ...and no una corda either: a quill plucks one string per register, and
    # the registers are drawn by hand, not shifted by a foot.
    soft_pedal_strings = 0
    # NO TOUCH. The key trips a jack; the quill plucks with a force the jack
    # decides, not the player. This is the textbook fact about the instrument
    # and the reason it has two manuals and a registration instead of a
    # crescendo -- and the corpus agrees: 97% of harpsichord channels across
    # 76 measured channels write a SINGLE velocity, because the people who
    # sequenced them knew. channel_volume still applies, so a part still
    # balances and still follows an expression pedal.
    touch_sensitive = False


    # BALANCE-NORMALISED, and on the BASE so every rank gets it. This lived on
    # HarpsichordProperties alone, whose comment said it was safe because "these
    # voices play alone" -- true of a GM patch, false the moment stops are drawn.
    # HarpsiUpperProperties and HarpsiLuteProperties still carried the inherited
    # 1/50, so the upper manual and the buff were 23.9 dB under the lower 8':
    # inaudible in a coupled registration, and a 24 dB drop when selected alone.
    # Found by building a registration demo, which is what demos are for.
    #
    # The relative balance between ranks is stop_ranks' own gains (1.00, 0.82,
    # 0.58, 0.50) and belongs there, not in an accident of which class happened
    # to be normalised.
    initial_gain = 0.3142260371

    # THE DAMPER. A harpsichord jack carries a scrap of felt that lands on the
    # string when the key comes up, and it takes time. This voice had
    # release_valve_time = 0.0, so `rel` floored at 1e-4 s and every note was
    # gated to digital silence in about 7 ms -- the sound of a sampler cutting a
    # voice, not of a damper landing, and something no instrument does.
    #
    # Measured on the VCSL harpsichords (CC0; see sources.md), as the time for
    # the damper to take the first 20 dB, from the envelope peak of the isolated
    # release recordings:
    #
    #     French 19 ms   Unk 42 ms   Flemish 57 ms   English 68 ms
    #     mean 47, sd 30
    #
    # 0.055 s puts the model at 47 ms, the middle of that. The spread is wide
    # because these are four different instruments with four different
    # regulations, so this is a central value and not a constant of nature.
    #
    # Only the FAST stage is fitted. Those recordings also show a slow tail
    # running on for several hundred ms, and it is tempting to read that as the
    # soundboard -- but in a fixed band the French sustains decay at -11.4,
    # -10.5 and -10.6 dB/s for C3, C4 and C5, and three different strings do not
    # agree to a dB. That tail is their ROOM. Fitting it would import a sample
    # library's room into the instrument and then double it against ours.
    release_valve_time = 0.055
    strike_fills_with_force = False   # a quill, not a felt hammer: the comb stays deep
    strike_depth = 1.0
    # BRIGHTNESS, fitted rather than aimed at. This was 1.55 -- "toward the
    # pluck's 1/n^2, kept a little bright" -- and it was far too dull. Against
    # the English set the model's ladder sat 20 dB under the recordings at the
    # 8th harmonic and 24 dB under at the 16th, and its 2-8 kHz content was some
    # 13 dB short of the instrument's.
    #
    # A harpsichord is not 1/n^2. The recordings put the SECOND harmonic ABOVE
    # the fundamental -- +3.3 dB pooled, +9.4 dB in the bass -- which is the weak
    # fundamental everyone recognises the instrument by, and no amount of a
    # steep series tilt produces it.
    #
    # Grid-searched through the renderer, so the body and the power
    # renormalisation are inside the loop rather than corrected for afterwards:
    #
    #     tonal_dampening   ladder rms   2-8 kHz error
    #          1.00           8.65 dB       -3.8 dB
    #          0.85           6.65          -2.2
    #          0.75           5.15          -1.2      <- both minima
    #          0.65           8.17          -0.3
    #          0.55           6.48          +0.6
    #
    # Judged on the ladder AND on broadband brightness together, because a
    # ladder-only fit is one of the four standing ways these go wrong: the ladder
    # alone bottoms in the same place but is noisy, while brightness is monotonic
    # and settles it. 1.55 -> 0.75 takes the ladder rms from 17.52 dB to 5.15.
    #
    # The recordings' own ladder scatters 12-20 dB from note to note, so 5 dB rms
    # is close to what this data can resolve; it is not a claim of 5 dB accuracy.
    tonal_dampening = 0.75
    octave_dampening = 0.02
    # THE SOUNDBOARD. Measured with `voicefit.py formants`, which is the comb
    # method run on the other axis: a pluck comb and a series tilt are fixed in
    # HARMONIC NUMBER, a body resonance is fixed in FREQUENCY, so averaging every
    # partial of every note by frequency -- after removing anything smooth in m --
    # finds the body and washes the source out.
    #
    # All three usable sets show one broad region low down and a dip above it:
    #
    #     English   449 Hz +5.2 dB   566 Hz +3.4
    #     Italian   283 Hz +9.1      224 +7.2, 356 +5.3, 449 +3.8, 566 +4.0
    #     Unk       224 Hz +3.9
    #
    # which is where a harpsichord's soundboard and case cavity live. They differ
    # from each other because they are different bodies, and that is the point:
    # this is the English (Zuckermann) instrument, the only set whose decay also
    # behaved. Fitted as one broad pole rather than the Italian's several,
    # because +5 dB over a third of an octave is what THIS body showed.
    #
    # What this cannot separate is the room: a hall colours by frequency too, and
    # with one microphone there is no way to divide them. Read it as body-plus-
    # room, and keep it modest for that reason.
    # THE JACK FALLING BACK. Measured off the VCSL release recordings, which
    # capture the key coming up in isolation from the note it ends.
    #
    # The release is TWO events at once, and they separate on the same test that
    # separated everything else here: a string event follows the note, a
    # mechanical one does not. Below about 1.2 kHz the release spectrum moves
    # 5.6-7.6 dB from note to note -- that is the damper arriving on the string,
    # and the release fade already models it. Above 2.4 kHz it moves 2.2-4.6 dB
    # and its centroid stays put: that is the jack, and nothing modelled it.
    #
    #     level under the sustain   -12.9 to -19.9 dB, mean -15.6
    #     spectral centroid          2909 to 5068 Hz, mean ~3900
    #
    # The modes below are placed to land the centroid there rather than fitted
    # individually -- five inharmonic frequencies are a stand-in for a small
    # wooden object being dropped, not a claim about its modes. The decay comes
    # from the shortest measured fall (C2, -20 dB in 33 ms); the longer readings
    # run to 211 ms and are the note's own upper partials still ringing in the
    # same band, not the click.
    # -39.6, not the -15.6 the recordings show, because this rides `gain` --
    # the factor before the harmonic ladder -- and not the note's audible peak,
    # which the summed partials produce. Calibrated back THROUGH the renderer
    # (isolating the click by differencing a render against one with it off,
    # since the 55 ms damper is louder than the click for the whole window and
    # hides it): -39.6 puts the click 15 dB under the note, mid-range of the
    # -12.5 to -17.5 measured.
    release_click_db = -39.6
    release_click_modes = ((2200.0, 0.60), (3100.0, 1.00), (4300.0, 0.85),
                           (5900.0, 0.50), (8000.0, 0.25))
    release_click_decay_db = 285.0
    release_click_s = 0.12

    formants = ((490.0, 350.0, 0.40),)
    formant_floor = 0.50            # so the pole stands +5.1 dB over the floor
    # bore_corner_hz GATES the whole formant path -- harmonic_volume returns
    # early on `not self.bore_corner_hz` -- so a body with no corner is silently
    # no body at all. It is placed above the audible band ON PURPOSE: the
    # measurement was detrended in harmonic number, so it cannot see a smooth
    # high-frequency rolloff, and asserting one here would be inventing a number
    # rather than measuring it. -0.5 dB at 10 kHz.
    bore_corner_hz = 40000.0
    bore_order = 2.0

    # RADIATION. A harpsichord is a large flat radiator, not a point: the
    # soundboard is roughly 1.8 x 0.8 m tapering, some 0.9 m2, and a rigid piston
    # of that area has a = 0.54 m and would beam into a 22-degree lobe by 1 kHz.
    # No harpsichord does that, because a soundboard is not rigid -- above its
    # first few modes it breaks up and only a fraction radiates coherently.
    #
    # 0.15 m is that coherent fraction, and it is a GUESS: one microphone at one
    # angle cannot measure a polar pattern, so nothing in the VCSL set constrains
    # it. It puts ka = 1 at 364 Hz, so the instrument is near-omnidirectional
    # through the bass and gently directional above -- which also makes its room
    # send fall with frequency, giving the bass-wet, treble-dry balance a real
    # room has. Until now this voice was omnidirectional at every frequency and
    # fed the room equally from every partial.
    #
    # The radius chooses the TRANSITION, not the strength: this piston model
    # saturates near 12 dB of directivity index whatever the radius (0.08 m
    # gives 9.9 dB at 4 kHz, 0.54 m gives 12.0). So the conservative move is to
    # put the transition high rather than to shrink the piston, and 0.15 keeps
    # everything below 364 Hz effectively omnidirectional.
    directivity_radius = 0.15

    # Thin, low-tension brass/iron: much less inharmonicity than a piano's wound
    # steel -- and less than this class used to claim. MEASURED over 195 notes
    # from six VCSL sets by regressing (f_m/m)^2 on m^2 (see voicefit.py inharm):
    #
    #     English 3.63e-5   Italian 4.38e-5   Unk 2.67e-5
    #     French  2.41e-5   Flemish 2.39e-5
    #     pooled median 3.51e-5, IQR 2.19e-5 .. 8.16e-5
    #
    # 89% of every note measured fell below the 1.2e-4 that stood here.
    #
    # This is the one fit these recordings support unconditionally, because
    # partial FREQUENCIES are immune to reverberation -- a room changes when
    # energy arrives, never at what pitch. So the five instruments agreeing
    # across five different rooms is real agreement and not a shared artefact,
    # which is exactly what could NOT be said of the decay measurements.
    inharmonicity_dynamic = False
    inharmonicity_coefficient = 3.51e-05
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
    # Shifted with the base (-0.80): this was 1.30 against a base of 1.55, a
    # brighter upper manual, and holding it fixed while the base moved would
    # have made the upper manual the DULLER of the two.
    tonal_dampening = 0.50            # brighter still


class HarpsiLuteProperties(HarpsiBase):
    """Lute (buff) stop: leather pads press the strings at the nut, killing the
    upper partials and shortening the decay -- a dry, dull pizzicato."""
    strike_point = 0.11
    tonal_dampening = 1.60            # shifted with the base (-0.80); still the dullest
    decay_db = 11.0
    harmonic_decay_db = 3.0
    chiff_volume = 0.30


class HarpsichordProperties(HarpsiBase):
    # Balance-normalised to the rest of the instrument set (K-weighted, equal
    # velocity). Safe for the existing repertoire because every render ends in
    # a peak normalise and these voices play alone -- and the organ family is
    # shifted by ONE common factor, so the reed-versus-flue balance tuned by ear
    # survives untouched.
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


class HarpsiRossProperties(HarpsichordProperties):
    """John Sankey's own instrument, from the soundfont he recorded through.

    A sibling, deliberately NOT a stop. A stop is a register of one instrument --
    the same strings in the same case, plucked by a different row of jacks -- and
    this is a different harpsichord. HarpsichordProperties is fitted to VCSL's
    English set, a 1970s Zuckermann kit: the bright, nasal end of the family.
    This one is the round, sustaining end, and the difference is measured rather
    than asserted:

        m =                    1     2      3      4      6      8     16
        Sankey's own        0.0   -5.0   -7.0   -6.7  -10.5  -21.6  -27.7
        VCSL English        0.0   +3.3   -4.6   -4.1   -8.5  -14.9  -24.4

    His has a STRONG fundamental where the Zuckermann has a weak one, and it
    rings 36% longer.

    WHAT IS FITTED, from ross.sf2 (<http://www.johnsankey.ca/data/ross.sf2>),
    three unlooped samples at E3, A4 and B5:

      decay -- D(m=1) 2.16 / 3.21 / 5.68 at 160 / 427 / 955 Hz, giving a
        register slope of 0.536 and D(415 Hz) = 3.46 against the base's 4.70.
        The 3.2:1.5 split between the constant and per-harmonic terms is kept
        from the base: three notes fix the LEVEL and the slope, not the split.

      inharmonicity -- 3.23e-5. Not really a fit so much as a confirmation: the
        base carries 3.51e-5 from six VCSL sets, and a different instrument
        sampled in a different decade through a different chain agrees to 8%.

    WHAT IS NOT FITTED, and why the class is thin. His ladder is not a 1/n^k
    tilt: m=2 alone wants tonal_dampening 1.4, m=8 wants 0.75, and it turns back
    up at m=12. That is body and comb structure, and three samples cannot
    separate them -- `voicefit comb` refuses at two usable notes, correctly. The
    best single tilt is the base's own 0.75 at 8.1 dB rms, so it is left alone
    rather than fitted to a number that would only look like a measurement.

    The samples sit near A = 426, but that is NOT his playing pitch: the bank's
    zones declare them E3/A4/B5 and fine-tune them up some 70 cents, landing
    near A = 444, and his MIDI then applies Werckmeister's own -11.72 cents on
    A. He played at about A = 441. Either way it is a property of his tuning,
    not of the voice, so it belongs to a tuner and not here.

    LICENCE. His terms permit modifying his files for personal use but require
    that distributed AUDIO be "derived from the MIDI files using my matching
    soundfont on a SoundBlaster 32 or 100% compatible system". A model fitted to
    that soundfont is not that soundfont, so this class does not make renders
    distributable. See sources.md.
    """
    # Derived from HarpsichordProperties and not from HarpsiBase, because the
    # registration machinery -- `registerable`, `stop_ranks` -- lives there, and
    # a harpsichord that is not registerable does not merely lose its stops: its
    # CC11 is then read as EXPRESSION, so a stop mask of 7 becomes a volume of
    # 7/127 and the instrument nearly vanishes. It inherits strike_point 0.115
    # with it, which is right as a stand-in -- three samples cannot give a comb.
    inharmonicity_coefficient = 3.23e-05
    decay_db = 2.36
    harmonic_decay_db = 1.10
    decay_register_slope = 0.536


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


class HammeredDulcimerProperties(InharmonicStringProperties):
    """GM 15. Steel strings STRUCK with light wooden hammers.

    It was on the plucked base, which is the wrong claim about the instrument:
    a hammered dulcimer is hit, not plucked, and struck versus plucked is the
    distinction the class hierarchy is built on. Its cousin the psaltery is
    plucked; this one is not.

    A HARD HAMMER DOES NOT FILL ITS NOTCH. A piano's felt compresses flatter
    the harder it is hit, widening the contact patch and filling in the comb
    (strike_fills_with_force). A dulcimer hammer is a bare wooden or
    leather-faced spoon, narrow and hard at every dynamic, so the notch stays
    where it is -- the same argument the harpsichord's quill gets, arrived at
    from the other direction.

    COURSES, NOT STRINGS. Each note is two to four strings tuned together and
    never quite together, which is where the instrument's shimmer comes from;
    it is the piano's unison dance on an instrument with no dampers at all to
    stop it. Nothing mutes a dulcimer, so it rings until it stops.

    The stiffness is ESTIMATED -- thin steel on a short scale, so more than a
    harpsichord's iron and far less than a piano's wound bass.
    """
    strike_point = 1.0 / 5       # struck well in from the bridge
    strike_depth = 0.90
    strike_fills_with_force = False
    inharmonicity_coefficient = 1.5e-04
    inharmonicity_dynamic = False
    string_count = 3
    unison_detune = (0.35, 0.5)  # courses, beating: the shimmer
    decay_db = 1.5               # no dampers
    harmonic_decay_db = 2.5


# The Clavinet D6's tone rockers. Six switches sit left of the keyboard: the
# four here are the TONE section -- "Brilliant and Treble activate a high-pass
# filter, while Medium and Soft activate a low-pass filter" -- and the other two
# (AB/CD) select the pickups, which is a different kind of control and is not
# here; see ClavinetProperties.
#
# Ordered DARKEST TO BRIGHTEST so a wheel can sweep them, with the panel's own
# names. Each rung is one rocker, except the middle, which is all four off.
# (corner Hz, order, high-pass?)  CORNERS ARE ESTIMATED -- the names are the
# instrument's, the frequencies are not.
CLAV_TONE = (
    ("soft",      1200.0, 2.0, False),
    ("medium",    3000.0, 2.0, False),
    ("flat",         0.0, 0.0, False),
    ("treble",     400.0, 2.0, True),
    ("brilliant",  900.0, 2.0, True),
)
CLAV_FLAT = 2          # the index of "all four rockers up"


def clav_tone_gain(hz, setting):
    """What one rocker does to a partial at hz. Vectorised over numpy arrays,
    so the same function serves the offline pass and the live per-block gain --
    which is the point of it being a filter of FREQUENCY and not of harmonic
    number. The pickup selection is not like this and cannot be done here."""
    i = int(setting) % len(CLAV_TONE)
    _name, corner, order, high = CLAV_TONE[i]
    if corner <= 0.0:
        return 1.0
    x = (hz / corner) ** order
    return (x / (1.0 + x)) if high else (1.0 / (1.0 + x))


class ClavinetProperties(InharmonicStringProperties):
    """GM 7. A struck steel string read by magnets -- and it was a harpsichord.

    Nothing about a plucked, wooden-bodied instrument is true of it, and the
    voice it inherited had `pickup_points = ()` and `pickup_velocity = False`,
    so the model carried no magnet at all.

    THE TANGENT IS THE TERMINATION, and that is the whole sound. "The rubber tip
    strikes the string and traps it against a metal stud, or anvil, for the
    duration of the note, splitting the string into speaking and nonspeaking
    parts, with the motion of the former transduced by the pickups." A piano is
    struck at about 1/7 of its speaking length and a harpsichord plucked at
    0.115; both get a comb with a NOTCH in the audible range. A clavinet is
    excited essentially AT THE END of the length it goes on to sound, so
    |sin(n*pi*p)| with p small RISES with harmonic number instead of notching
    and its first null sits far above hearing. A weak fundamental and strong
    upper partials: that is the buzz, and it is one attribute.

    AND A HARD TANGENT DOES NOT FILL ITS NOTCH. Piano felt compresses flatter
    the harder it is hit, widening the contact patch and filling the comb in.
    Rubber against a steel anvil does not, so strike_fills_with_force is False,
    the same argument the dulcimer's wooden hammer and the harpsichord's quill
    get from the other direction.

    THE PICKUP FRACTION MOVES WITH PITCH, which no other voice here does. The
    pickups sit at the bridge end at a FIXED PHYSICAL POSITION while the
    speaking length is set per note by where its tangent lands. On a guitar the
    nut is fixed, so a pickup stays at one fraction of the string for every
    note; on a clavinet the same magnet is a fifth of the way up a treble string
    and a fifteenth of the way up a bass one. So pickup_points is computed per
    instance from the note, the way the Rhodes computes its tonebar ratio.

    This is also the voice the electric guitar's pickup machinery was actually
    built for. The Rhodes could not use it -- a tine has one mode and no
    standing wave to sample -- but a clavinet is a plain string with a magnet
    under it, which is exactly what |sin(n*pi*q)| describes, and
    pickup_velocity's +6 dB/octave is the same magnet.

    THE ATTACK IS THE MACHINE, NOT THE STRING: "the mechanical noise generated
    by the key, its rebound, and the tangent hitting the anvil masked the
    striking portion of the tone nearly entirely." So the click is carried as
    broadband noise that grows with force, not as a string transient.

    NO REFERENCE. There is no clavinet in the Iowa set and no usable isolated
    recording of one -- the CC0 material is loops, riffs and synth imitations.
    The mechanism above is from the literature (Gabrielli et al., "A digital
    waveguide-based approach for Clavinet modeling and synthesis", EURASIP
    JASP 2013); the NUMBERS below are estimates, and the ones that matter most
    are the string scale and the pickup's distance from the bridge.
    """

    # Struck at the very end of what sounds. 0.035 puts the comb's first null
    # near the 28th partial, so everything audible is on its rising edge.
    # The four TONE rockers are on the wheel: see CLAV_TONE above and
    # blockrender's clavinet pass. The other two, AB/CD, select which of the two
    # pickups is heard, and they are NOT here -- a pickup selection changes the
    # COMB, which is a different amplitude for every harmonic of every note, so
    # it is a property of the template and cannot be a gain applied to a note
    # already sounding. That is a second pass, and it wants a bank axis.
    clav_panel = True

    strike_point = 0.035
    strike_depth = 0.90
    strike_fills_with_force = False     # rubber on an anvil, not felt

    # Short, stiff steel. Estimated: more than a harpsichord's long thin wire
    # (3.5e-05), far less than a piano's wound bass.
    inharmonicity_coefficient = 1.1e-04
    inharmonicity_dynamic = False

    # The magnet. pickup_points is filled in per note by __init__ below.
    pickup_width = 0.012
    pickup_velocity = True              # -dPhi/dt: the +6 dB/octave is the magnet

    # WHERE THE STRING ENDS, as a function of the note. A real instrument does
    # not scale its lengths as 1/f -- that would want a metre of wire at the
    # bottom -- so the exponent is well under one, giving about 0.38 m at the
    # bottom of the compass and 0.13 m at the top. ESTIMATED.
    speaking_length_ref_m = 0.22
    speaking_length_ref_hz = 261.6
    speaking_length_power = 0.30
    pickup_distance_m = 0.028           # from the bridge. ESTIMATED.
    pickup_fraction_max = 0.30          # do not let the treble null fall too low

    # Against the magnet's rising n. At 1.70 the pickup comb's SECOND LOBE came
    # back to +6.5 dB at the 12th partial, rivalling the peak at the 4th; 2.0
    # leaves the peak at the 3rd with the second lobe down at the fundamental.
    # The voice still carries +11.4 dB above its fundamental where the
    # harpsichord it replaces has +7.3, which is the difference in question.
    tonal_dampening = 2.00
    octave_dampening = 0.0
    decay_db = 5.5                      # it dies fast, and the anvil is lossy
    harmonic_decay_db = 3.0
    release_valve_time = 0.035          # woven yarn, and it means it
    attack_time = 0.0015

    # The key, its rebound and the tangent on the anvil. Loud enough to mask the
    # string's own onset, which is what the paper says it does.
    chiff_volume = 0.55
    chiff_cycle = 0.0
    chiff_min_valve_time = 0.001
    chiff_max_valve_time = 0.006
    strike_noise_slope = 1.3            # and it grows with how hard the key is hit

    # Balance-normalised the way the rest of the set is: C3/C4/C5 at velocity
    # 100, same room and master, matched on rms against the grand piano. It
    # started 18.7 dB UNDER one, because almost all of this voice's energy sits
    # in partials the comb had been pushing around rather than in a fundamental.
    initial_gain = 0.7786

    def __init__(self, frequency=256.0, *args, **kwargs):
        super().__init__(frequency, *args, **kwargs)
        f0 = float(frequency)
        length = self.speaking_length_ref_m * (
            (self.speaking_length_ref_hz / f0) ** self.speaking_length_power)
        q = self.pickup_distance_m / max(length, 1e-6)
        self.speaking_length_m = length
        self.pickup_points = (min(q, self.pickup_fraction_max),)


class GrandPianoProperties(InharmonicStringProperties):
    # CC71-78: a struck string: how long it rings, and how the damper lands;
    # nothing to brighten, no onset to slow.
    sound_controls = frozenset(('decay', 'release'))
    # Struck, then nothing the player does reaches the string.
    pitch_bendable = False
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

    def __init__(self, frequency=256.0, channel_pan=0.0, attack_volume=1.0, channel_volume=1.0,
                 effort=0.0):
        super().__init__(frequency, channel_pan, attack_volume, channel_volume, effort)
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

    # THE UNA CORDA TAKES ONE STRING. See SynthProperties.soft_pedal_strings.
    soft_pedal_strings = 1

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        # Second string fades in across G1, third across B2 -- a crossfade, not a
        # hard switch, so the unison shimmer regulates smoothly through the breaks.
        gains = (self.string_gain[0] * self._string_blend(frequency, self.string_break_hz[0]),
                 self.string_gain[1] * self._string_blend(frequency, self.string_break_hz[1]))
        if soft_pedal_down and self.soft_pedal_strings:
            # The action has slid: the hammer no longer reaches the last
            # string. Dropped rather than damped, so its partials are never
            # emitted -- which is also cheaper.
            gains = gains[:max(0, len(gains) - self.soft_pedal_strings)]
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


# HOW FAR OUT OF TUNE, on the wheel. 1.0 is the class's own range; 0 is a piano
# somebody has just tuned; 2.0 is one nobody has touched in a decade. Set per
# note by blockrender from the channel's CC1, and live by the bank axis, which
# is literally "the CC1 value to build this template with".
honky_detune = 1.0


class BrightPianoProperties(GrandPianoProperties):
    """GM 1. The same piano, voiced hard -- which is what a technician does.

    GM specifies nothing beyond the name: the Level 1 list is a naming
    convention, and the spec names no instrument for any program. What it does
    say is in Level 2's bank variations -- "Wide" and "Dark" are variations OF
    the acoustic grand -- so brightness in GM's own vocabulary is a timbral axis
    on one instrument rather than a different instrument. Hence a voicing.

    AND A VOICING IS A HAMMER. Needling the felt softens it, lacquer hardens it,
    and both change exactly two things this engine already models:

      * CONTACT TIME, which IS the hammer's low-pass. hammer_corner_hz is that
        corner and it already shortens with force, which is why the piano
        brightens when you dig in. A harder hammer starts shorter: 0.14 ms here
        against the grand's 0.25.
      * HOW MUCH THE FELT FLATTENS. A soft hammer spreads under force, widening
        its contact patch and filling in the strike comb's notch -- which is why
        a piano's sour 7th disappears at ff. A hard one barely spreads and keeps
        its notch at every dynamic. That was a BOOLEAN here, the felt-vs-quill
        distinction; strike_fill_fraction now says how much, with 1.0 the soft
        default so nothing else in the set moves.

    THE HAMMER ALONE CANNOT BE HEARD, and that is measured rather than feared:
    removing its low-pass ENTIRELY buys +4.0 dB above the 8th partial, because
    the board is -12.1 dB at 4 kHz where the hammer is only -6.9. So the voicing
    was inaudible until the board moved with it -- see board_high_hz below.

    WITH BOTH, the velocity behaviour is still the characteristic part. Energy
    above the 8th partial at C4:

        vel      grand     bright    difference
         30    -27.1 dB   -19.4 dB     +7.7
        127    -25.1 dB   -18.5 dB     +6.7

    The gap is LARGEST when played softly, and the grand brightens 2.0 dB from
    pp to ff where this voice brightens 1.0 -- it is already bright and has less
    to open into. That is what hard voicing does and why players argue about it:
    the tone stops being something the hand controls.

    NO REFERENCE. There is no piano in the reference set at all; the grand's own
    stretch is a published Steinway B model standing in for an unmeasured
    instrument. Both numbers below are judgements about how far a technician
    would take a hammer, not measurements of one.
    """

    # Balance-normalised against the grand, which it needed: cutting the body
    # warmth takes 2.5 dB of low-mid out of the note. Solved on the render at
    # 21.8 dB per decade of this knob rather than 20, the phantom partials
    # again being sum-tones that scale as its square.
    initial_gain = 0.093189
    hammer_corner_hz = 7000.0       # ~0.14 ms of contact, against 0.25
    strike_fill_fraction = 0.45     # hard felt spreads about half as much

    # AND A BRIGHTER BOARD, because the hammer alone cannot be heard. Measured:
    # removing the hammer's low-pass ENTIRELY buys +4.0 dB above the 8th partial,
    # so no amount of voicing is audible here -- the board owns the top, being
    # -12.1 dB at 4 kHz where the hammer is -6.9. Ben, on the first version:
    # "I can't hear a difference between grand and bright."
    #
    # These were left alone at first on the grounds that they were fitted with
    # the rest of the piano. THEY WERE NOT: sources.md's own list of what is
    # still assertion includes "soundboard formants (not attempted)", and these
    # carry no measurement. The cymbal lesson -- do not change half of a joint
    # fit -- was applied to something that is not a joint fit.
    #
    # A stiffer, thinner, differently braced board radiates higher and has less
    # wooden warmth, and that is what actually separates the makers whose names
    # get attached to the word "bright". It is an assertion on both sides, so
    # there is no fit to break; it is also no longer only a voicing, and the
    # class name should be read as "a brighter piano" rather than "the same
    # piano voiced".
    board_high_hz = 5500.0          # the board radiates higher, against 2600
    board_body_gain = 0.30          # and carries less low-mid warmth, against 0.6


class HonkyTonkProperties(GrandPianoProperties):
    """GM 3. The same piano, badly tuned -- which is all a honky-tonk is.

    It was the acoustic grand unchanged, and the fix needs no new mechanism at
    all: the grand ALREADY models a real unison as one string at pitch and two
    more mistuned around it, drawn per note and straddling so the note itself
    stays in tune. A honky-tonk is that with the tuner's hand off. So this class
    widens one number and touches nothing else.

        grand        0.5 to 1.7 cents     0.43 Hz of beating at A4 -- a shimmer
        honky-tonk   8 to 20 cents        2.0 to 5.1 Hz -- a wobble

    THE BEAT RATE IS NOT A CHOICE, it follows. Two strings a fixed number of
    CENTS apart beat at a rate proportional to pitch, so one range gives 0.3 Hz
    at the bottom of the compass and 12 Hz at the top -- slow and fat in the
    bass, fast and nervous in the treble, which is how a neglected piano
    actually sounds. Nothing here sets a rate; the cents set it.

    AND THE BASS DOES NOT WOBBLE, also for free. The grand's stringing is a
    single wound monochord at the bottom, two strings from G1 and three from B2,
    so the lowest notes have NO second string to mistune. A real honky-tonk is
    the same: its bottom octave is comparatively clean and the jangle lives in
    the middle and top.

    WHAT IS NOT DONE. A tack piano -- drawing pins in the hammers -- is a
    different instrument and a different sound, and GM 3 does not mean it. The
    extras' gains are left at the grand's (0.28, 0.20), which swings the unison
    about 9 dB rather than nulling it; raising string_gain would make the
    wobble deeper as well as wider, and that is a separate knob with a separate
    argument. NO REFERENCE: the range is judged from the beat rates above, not
    measured off an instrument.
    """

    string_detune_range = (8.0, 20.0)   # |cents| of the two extra strings
    detune_wheel = True                 # ...and CC1 scales it, 64 being this

    def __init__(self, frequency=256.0, *args, **kwargs):
        # Scaled BEFORE super(), which is what draws this note's two strings
        # out of the range. An instance attribute, so the class value stays the
        # instrument's own and the wheel is a performance control over it.
        lo, hi = type(self).string_detune_range
        self.string_detune_range = (lo * honky_detune, hi * honky_detune)
        super().__init__(frequency, *args, **kwargs)


class ElectricGrandProperties(GrandPianoProperties):
    """GM 2. A Yamaha CP-70: a real grand action and real strings, with no
    soundboard and a piezo under the bridge. It was the acoustic grand, exactly
    -- the same class object, not even a subclass -- and three things about that
    are wrong. All three are derived here rather than fitted, because there is
    no recording of one to fit against.

    "The same frame, action and frame construction as an acoustic piano, but
    with SHORTER STRINGS", and "pick-ups on each note INSTEAD OF A SOUNDBOARD".

    THE STRETCH IS FROM THE WRONG PIANO, BY THE LARGEST POSSIBLE MARGIN. For a
    stiff string B = pi^2 Q d^2 / (64 rho L^4 f0^2), so at a fixed pitch and
    gauge B goes as 1/L^4 and a string shortened by k has k^4 the
    inharmonicity. The voice this inherits carries a STEINWAY B fit -- a
    seven-foot concert grand, the longest strings in the catalogue and the least
    inharmonic thing it could have been given.

    But the departure is not one number, and the shape is derivable. At constant
    stress f0*L is fixed, so a piano's speaking length follows L = C/f UNTIL THE
    CASE RUNS OUT, and two pianos of different size can only differ where the
    shorter one BINDS. With C = 162 m*Hz (a grand's C4 string is about 0.62 m),
    a 211 cm Steinway binds below 83 Hz and a CP-70's 120 cm case below 154, so:

        above 154 Hz   the two are IDENTICAL -- same length, same B
        83 to 154 Hz   the factor climbs as f^-4
        below 83 Hz    both are capped, and it tops out at (1.95/1.05)^4 = 11.9

    That predicts something specific: an electric grand's stretch departs from a
    concert grand's ONLY in the bottom octave and a half, and there it is huge.
    The 8th partial of its lowest A sits 195 cents sharp against a Steinway's
    17. B reaches 3.8e-03, which is where the literature puts a spinet -- so the
    derivation lands in the right place without having been aimed there.

    A PIEZO READS FORCE, NOT RADIATED SOUND, and that is also derivable. The
    transverse force a string exerts on its bridge is T times the slope there,
    so for mode n it goes as n*A_n: **+6 dB per octave**, the same tilt a
    magnetic pickup gets and for a different reason -- there it is velocity,
    here it is the slope. It is NOT the guitar's pickup comb: a bridge pickup
    sits at the termination and reads force, not displacement at an interior
    point, so there is no |sin(n*pi*q)| and pickup_points stays empty.

    AND THERE IS NO SOUNDBOARD TO RADIATE. The inherited soundboard_gain is
    three things, and a CP-70 has none of them: a body resonance at 240 Hz, a
    top roll-off at 2.6 kHz, and -- the one that matters most -- a sub-bass term
    1/(1+(35/f)^2) that models a BOARD'S POOR RADIATION at low frequency. That
    is a real acoustic loss and a piezo does not have it, so the inherited voice
    was throwing away bass the instrument keeps. Backwards, for an instrument
    whose signature is a thick clean bottom that engineers cut rather than lift.

    WHAT IS KEPT, because it is all still true: the hammers, the action, the
    strike comb at 1/7, the velocity-dependent hammer low-pass, the unison
    dance and the phantom partials. This is a piano.

    NO REFERENCE, so this sits at 2. The +6 dB/octave and the 1/L^4 law are
    derived; the two CASE LENGTHS are facts about the instruments; and
    bridge_corner_hz is an estimate standing in for the mechanical coupling
    between string, bridge and pickup, which is the one number here with
    nothing behind it. How many strings per note a CP-70 uses is also
    unverified -- the unison behaviour is inherited unchanged.
    """

    # L = C/f until the case runs out. C from a grand's C4 string, 0.62 m.
    scale_constant_hz_m = 162.0
    reference_string_max_m = 1.95   # the Steinway B the inherited fit describes
    case_string_max_m = 1.05        # a CP-70, whose case is about half as deep

    # THE +6 dB/OCTAVE IS DERIVED AND DELIBERATELY NOT APPLIED, which is the
    # most interesting thing in this class. Bridge force for mode n is T times
    # the slope, so it goes as n*A_n -- that much is certain. But the A_n it
    # would multiply is this engine's generic 1/n^1.1 string tilt, not a
    # measured displacement spectrum, and stacking a full octave-doubling on
    # top of it puts 1-4 kHz +11 dB and the top +15 over the acoustic grand,
    # measured. A real CP-70 is thick and clean, not brilliant.
    #
    # The physics that rescues it is that a piezo sits under a MASSIVE WOODEN
    # BRIDGE whose mechanical mobility falls with frequency, and that fall
    # takes the slope back by an amount nothing here can predict. So the honest
    # value is 0 and the derivation is recorded rather than spent: setting it to
    # 1.0 and then choosing a corner that cancels it again would be fitting a
    # free parameter to a target that does not exist.
    bridge_force_power = 0.0
    # The board radiates poorly above 2.6 kHz; a pickup does not stop there. The
    # DIRECTION is defensible, the number is an estimate.
    bridge_corner_hz = 4000.0
    bridge_order = 1.6
    initial_gain = 0.088489
    bridge_gain = 1.0               # neutral: the board's three terms became one

    # BALANCE, and it is not linear in this knob. Measured on four notes at
    # velocity 100 with the master well clear of any ceiling, level against
    # initial_gain runs at 38.8 dB per decade where a plain gain would give 20:
    # the piano's PHANTOM PARTIALS are sum-tones whose amplitude goes as the
    # product of two partials' amplitudes, so they scale as the SQUARE of this.
    # Inheriting the acoustic grand's 0.0718 leaves the voice 3.5 dB under one;
    # solved against the measurement it wants 0.0885.

    def inharmonicity_coefficient_for_frequency(self, frequency):
        b = super().inharmonicity_coefficient_for_frequency(frequency)
        f = max(float(frequency), 1e-6)
        c = self.scale_constant_hz_m
        long_ = min(c / f, self.reference_string_max_m)
        short = min(c / f, self.case_string_max_m)
        return b * (long_ / short) ** 4

    def soundboard_gain(self, fn):
        """There is no soundboard. This is the bridge and the piezo on it.

        Overriding the board's method rather than harmonic_volume keeps the
        hammer low-pass above it exactly as the piano has it -- the hammers are
        the same hammers.
        """
        slope = 1.0
        if self.bridge_force_power:
            f0 = self.frequency_x * (2.0 ** self.octave_position)
            slope = max(fn / max(f0, 1e-9), 1.0) ** self.bridge_force_power
        return self.bridge_gain * slope / (
            1.0 + (fn / self.bridge_corner_hz) ** self.bridge_order)


# One waveshaper answer per (curve, offset, deflection). A note asks for it up to
# max_harmonic times, and a bank asks for it once per velocity bucket.
_EP_PICKUP_CACHE = {}

# The voicing screw, in units of the field's width. This is the one adjustment a
# Rhodes technician actually makes on the instrument, and it is the sharpest
# falsifiable claim the measurements offer: at 0.0 the fundamental vanishes and
# the pickup answers at twice the pitch. Exposed so it can be swept and heard --
# see examples/rhodes.py --voicing.
ep_voicing = os.environ.get("TUNING_EP_VOICING", "")

# THE CONTROL. A pickup that does not bend is not a pickup -- a linear flux
# hands back the sine it was given -- and nothing this voice claims about its
# harmonics means anything until the control has been heard to be dull. The
# same discipline that caught the A415 assumption and the steelpan's stretch.
ep_control = os.environ.get("TUNING_EP_CONTROL", "") not in ("", "0")


class ElectricPianoProperties(PluckedStringProperties):
    """GM 4-5. A struck steel bar read by a pickup -- and the pickup IS the voice.

    These rendered as a Steinway B, which is wrong in every particular: an
    electric piano has no strings, no soundboard and no unison trios, so it has
    neither the piano's stretched partials nor its beating. Sibling of
    InharmonicStringProperties rather than a child of it, for that reason.

    THE TINE IS A PURE SINE. Hamburg tracked four points along a struck tine
    with a high-speed camera at 38 kfps: "after an extremely short transient the
    tine vibrates in a perfect sinusoidal motion without appearance of higher
    harmonics" (Muenster & Pfeifle, ISMA 2014). There are no cantilever
    overtones to model here -- not 6.267, not 17.55. One mode.

    SO EVERY HARMONIC YOU HEAR IS MADE BY THE PICKUP: "their specific timbres
    are influenced primarily by the specific pickup system" (Pfeifle & Muenster,
    DAGA 2017). The tine swings through a field that is not flat, so what the
    coil sees is a distorted copy of a sine, and the distortion is the
    instrument:

        Phi(u) = pickup_flux(u),   u(t) = pickup_offset + A sin(wt)

    Two consequences fall out, and both are measurable:

      * CENTRE THE TINE AND THE FUNDAMENTAL DISAPPEARS. A symmetric field
        crossed twice per cycle answers at twice the pitch -- "when aligned
        perfectly centered, the produced sound behind the pickup is twice the
        fundamental of the tine" (DAGA 2017). pickup_offset is the voicing screw
        a Rhodes technician actually turns; at 0.0 the fundamental measures
        221 dB down, and by 0.5 it is 14.6 dB OVER the octave.

      * HARMONIC k GROWS AS A^k, so if the tine's deflection decays at D dB/s
        then harmonic k decays at k*D. That is already this engine's decay law
        (harmonic_decay_db * h, with decay_db and harmonic_decay_dampening both
        zero), so the growl fading into a bell as the note rings -- the Rhodes'
        whole signature -- costs nothing and needs no time-varying spectrum.
        Fitted slopes of log a_k against log A: 0.992, 1.995, 2.993, 3.995,
        4.994, 5.995, against a wanted 1..6.

    And because one sine through a waveshaper gives an EXACTLY HARMONIC series,
    none of this goes near tubeamp -- which exists precisely because distortion
    of a chord is not distortion of its notes. This is one note's own curve, so
    it is only an amplitude law.

    VELOCITY IS A TIMBRE CONTROL MORE THAN A VOLUME CONTROL: "velocity
    sensitivity is to be distinguished by a change in volume to lesser extent
    than in sound. Playing softly the fundamental comes up, playing harder the
    more and more growl appears" (ISMA 2014). See series_volume for how that is
    arranged; and the growl is loudest at the bottom of the compass, "where the
    tines have a larger deflection", which deflection_register_slope carries.

    THE TONEBAR IS NOT TUNED TO THE TINE. "Opposed to common belief, the tine
    and tonebar are not alike in pitch or resonance frequency... several hundred
    to more than 1400 cents apart", and the tine enslaves it, so the tonebar's
    own eigenfrequencies "are not present in the sound, they only appear in the
    transient". It is the glockenspiel-like attack and nothing else.

    NOT the guitar's pickup_points. That comb is |sin(n*pi*q)|, a STRING's
    standing wave sampled at a point in space. A tine has one mode and one
    pickup, and what shapes this sound is the field's shape against
    DISPLACEMENT -- a different physical quantity, and the reason none of the
    electric guitar's pickup machinery carries over.
    """

    # A measured/derived mode set must not ALSO be stretched by a stiffness
    # term. That is the bug that put the steelpan's octave 66 cents sharp, and
    # both renderers do it (SimplePartial.__init__ and blockrender's emit loop).
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False

    # The whole amplitude law is series_volume below, so no comb of any kind.
    strike_point = 0.0
    pickup_points = ()

    # ---- the pickup -----------------------------------------------------
    # pickup_offset and pickup_deflection are both in units of the field's
    # width, which is what makes pickup_flux() dimensionless.
    # Fitted to what a Rhodes does per register: the bass growls but KEEPS its
    # fundamental, the treble is nearly a bell, and velocity moves the growl far
    # more than the level. 0.9 dB rms against those five targets; the first try
    # had the bass so wide that h2 beat h1 and the low notes read an octave up.
    pickup_offset = 0.30          # voicing: how far off the axis the tine sits
    pickup_deflection = 0.25      # swing at velocity 127, middle register
    pickup_deflection_max = 1.10  # past this the tine has left the field
    deflection_register_slope = -0.50   # per octave: low tines swing wider
    pickup_harmonics = 16         # the curve is spent long before this
    pickup_floor_db = -90.0       # and the tail below this is not worth a partial

    # ---- the tonebar ----------------------------------------------------
    # Fitted to the nine tine/tonebar pairs in ISMA 2014 Table 1 (16% rms).
    # The fit carries the measured fact that the two DIVERGE with pitch: the
    # tonebar sits at 0.75 of the tine at the bottom of the compass and 0.11 at
    # the top, which is why this cannot be a fixed ratio.
    tonebar_hz_coeff = 10.06
    tonebar_hz_power = 0.4066
    # Transverse bar modes, then the longitudinal ones. The paper attributes the
    # bright part of the attack to longitudinal waves converting to transverse
    # at the T-joint -- they are "10-15 times faster", and "because of the
    # energy in the high frequency range these waves contribute a lot to the
    # higher overtones of the extremely short initial transient". The transverse
    # ratios are a free bar's; the longitudinal pair is ASSERTED from that
    # 10-15x, not measured.
    tonebar_mode_ratios = (1.0, 2.756, 5.404, 12.0, 24.0)
    tonebar_gains = (0.30, 0.18, 0.10, 0.22, 0.10)
    tonebar_decay_db = 3300.0     # -40 dB in 12 ms: the measured 10-14

    # ---- the ring -------------------------------------------------------
    # decay_db and harmonic_decay_dampening MUST stay at zero: that is what
    # makes the inherited law exactly k*D, which is what A^k demands.
    decay_db = 0.0
    harmonic_decay_dampening = 0.0
    harmonic_decay_db = 10.0
    decay_register_slope = 0.55

    attack_time = 0.004           # hammer contact measured at 6.42 ms
    one_shot = False              # every tine has its own felt damper
    release_valve_time = 0.09
    octave_gain = 0.0             # the deflection slope already tilts the register
    octave_width = -0.12          # keyboard pan, bass left, as the piano has

    # Balance-normalised the way the rest of the set is: three notes, C3/C4/C5,
    # velocity 100, same room and master, matched on rms against the grand
    # piano. It started 18.0 dB under one.
    initial_gain = 0.56950913

    def __init__(self, frequency=256.0, *args, **kwargs):
        super().__init__(frequency, *args, **kwargs)
        # The tonebar is a separate resonator that happens to be bolted on, so
        # where its modes sit depends on the note -- hence mode_ratios per
        # instance rather than per class.
        if ep_voicing != "":
            self.pickup_offset = float(ep_voicing)
        f0 = float(frequency)
        tb = self.tonebar_hz_coeff * (f0 ** self.tonebar_hz_power)
        # A Gaussian's harmonics fall off a CLIFF -- at a middle-register
        # velocity the 10th is already 133 dB down -- so carrying the whole
        # series would spend partials on nothing. Trim to where the curve dies.
        series = self._pickup_series()
        top = self.pickup_harmonics
        if series[0] > 0.0:
            floor = series[0] * (10.0 ** (self.pickup_floor_db / 20.0))
            while top > 1 and series[top - 1] < floor:
                top -= 1
        self._series = series[:top]
        self.pickup_harmonics = top
        self.mode_ratios = (tuple(float(m) for m in range(1, top + 1))
                            + tuple(tb * r / f0 for r in self.tonebar_mode_ratios))
        self.max_harmonic = len(self.mode_ratios)

    def pickup_flux(self, u):
        """Flux through the coil with the tine u from the axis. The curve IS the
        instrument, so this is the one thing a subclass must answer."""
        raise NotImplementedError

    def _deflection(self):
        """How far the tine swings, in units of the field's width.

        Proportional to hammer velocity, and wider at the bottom of the compass.
        attack_volume is the GM square law, so velocity is its square root."""
        a = (self.pickup_deflection
             * (2.0 ** (self.deflection_register_slope * self.octave_position))
             * _sqrt(max(self.attack_volume, 1e-4)))
        return min(a, self.pickup_deflection_max)

    def _pickup_series(self):
        """What the coil makes of one sine: the harmonics of the waveshaped flux."""
        a = self._deflection()
        key = (type(self).__name__, round(self.pickup_offset, 4), round(a, 4),
               self.pickup_harmonics, ep_control)
        out = _EP_PICKUP_CACHE.get(key)
        if out is not None:
            return out
        n = 256
        x0 = self.pickup_offset
        flux = (lambda u: u) if ep_control else self.pickup_flux
        phi = [flux(x0 + a * _sin(2.0 * _pi * i / n)) for i in range(n)]
        s = []
        for k in range(1, self.pickup_harmonics + 1):
            re = sum(phi[i] * _cos(2.0 * _pi * k * i / n) for i in range(n)) * 2.0 / n
            im = sum(phi[i] * _sin(2.0 * _pi * k * i / n) for i in range(n)) * 2.0 / n
            # The coil reads the EMF, -dPhi/dt, and differentiation multiplies
            # partial k by k. This is the magnet's +6 dB/octave, arrived at the
            # same way pickup_velocity does it for a guitar.
            s.append(k * _sqrt(re * re + im * im))
        out = tuple(s)
        _EP_PICKUP_CACHE[key] = out
        return out

    def series_volume(self, harmonic):
        # THE LEVEL FOLLOWS VELOCITY, NOT ITS SQUARE. attack_volume is (v/127)^2,
        # but a hammer sets the tine's DEFLECTION and the coil reads deflection
        # linearly, so dividing it back out here leaves the note's level linear
        # in velocity. The growl is what keeps the square and steeper, since
        # harmonic k goes as A^k -- which is the measured behaviour: velocity
        # changes the sound more than it changes the volume.
        av = max(self.attack_volume, 1e-4)
        np_, nb = self.pickup_harmonics, len(self.tonebar_gains)
        if harmonic < 1 or harmonic > np_ + nb:
            return 0.0
        if harmonic > np_:
            v = self.tonebar_gains[harmonic - np_ - 1] * self._deflection()
        else:
            v = self._series[harmonic - 1]
        return self.gain * v / av

    def harmonic_decay(self, harmonic):
        if harmonic > self.pickup_harmonics:
            # The tonebar lives in the transient only: measured, the waveform is
            # sinusoidal again 10-14 ms after the strike. No register factor --
            # a tick is a tick everywhere on the keyboard.
            return self.tonebar_decay_db
        # k*D, because harmonic k of a waveshaped sine goes as A^k.
        return super().harmonic_decay(harmonic)


class RhodesProperties(ElectricPianoProperties):
    """GM 4, Electric Piano 1: a Fender Rhodes. Electromagnetic, so a bell curve.

    "The flattened sides of the frustum focuses the magnet field in the center
    showing an approximate bell curve characteristic" (DAGA 2017). A Gaussian is
    an extremely smooth nonlinearity, so its harmonics fall off a cliff -- at
    equal drive h8 sits 120 dB down, against 86 for the Wurlitzer's pole. That
    cliff is why a Rhodes bells where a Wurlitzer barks.
    """
    # A struck tine keeps the pitch its length gives it.
    pitch_bendable = False

    cabinet = "rhodes"
    # The panel calls it vibrato; it is a stereo PAN between the suitcase's two
    # amplifiers, which is why it vanishes in mono. CC1 sets how much of it.
    tremolo_hz = 5.5
    tremolo_depth = 0.60
    tremolo_stereo = True

    def pickup_flux(self, u):
        return _exp(-u * u)


class WurlitzerProperties(ElectricPianoProperties):
    """GM 5, Electric Piano 2: a Wurlitzer. Electrostatic, so a pole.

    Not a Rhodes with a filter on it -- a different instrument sharing one
    mechanism. Both are a struck steel bar whose sound is made by its pickup;
    what differs is the CURVE, and two structural facts follow from it.

    A ONE-SIDED PLATE IS ASYMMETRIC WHEREVER THE REED SITS. "A steel plate
    impacted by a hammer vibrates as an electrode of a capacitor... analogous to
    a capacitor microphone, the capacity varies inversely proportional to the
    distance between the electrodes" (DAGA 2017). A Rhodes' magnet is symmetric
    about the tine, which is why centring it kills the fundamental and why
    voicing it is a real adjustment. A Wurlitzer's plate is on ONE side of the
    reed, so 1/d is lopsided at every rest position and there is no centred
    case to find. pickup_offset survives as the gap, not as a voicing screw.

    AND A POLE DOES NOT FALL OFF A CLIFF. A Gaussian is entire, so the Rhodes'
    harmonics collapse faster and faster -- h2 at -4 dB, h8 at -104, h12 at
    -195. 1/d has a pole, so its harmonics fall GEOMETRICALLY, about 10 dB each:
    -6, -25, -47, -69, -92, -116 at the same drive. That straight line in dB is
    the bark, and it is the whole difference between the two instruments.

    NO TONEBAR. "The reeds vibrate freely, providing a surface area large enough
    to produce a measurable change in capacitance" -- there is no second prong
    and no resonator, so there is nothing to make the Rhodes' glockenspiel-like
    attack and tonebar_gains is empty. A Wurlitzer's attack is the hammer, not a
    ringing bar.

    WHAT IS NOT MODELLED. "The specific pickup geometry leads to a highly
    complex decay characteristic showing interesting effects like non-exponential
    decay characteristics and beating of higher partials" (DAGA 2017). Both are
    real and neither is here: this voice decays exponentially, per partial, at
    k*D like its sibling. The beating in particular would need the reed's own
    higher modes, and the same paper's camera says the motion is "approximately
    sinusoidal", so where it comes from is not settled by the measurement.

    A NOTE ON THE SENSING CONVENTION, since it decides everything. Taken as
    charge on a fixed-voltage plate, the signal follows C and therefore 1/d, and
    that is what the paper's sentence describes and what is modelled here. Taken
    at constant charge the voltage would follow d instead and be LINEAR -- a
    condenser microphone's whole virtue. The paper is explicit that the pickup is
    what shapes this instrument's timbre and that "higher velocity results in a
    richer harmonic sound", which only the first reading produces, so that is the
    one followed. It is an interpretation of a circuit, not a measurement of one.
    """
    # A struck reed, the same as the tine: nothing bends it.
    pitch_bendable = False
    # Fitted the same way the Rhodes was, to a Wurlitzer's own register and
    # velocity behaviour: barkier everywhere and much barkier dug into.
    # 1.4 dB rms against five targets.
    pickup_offset = 0.05          # the gap, not a voicing screw: see above
    pickup_deflection = 0.50
    pickup_deflection_max = 0.70  # u must stay well clear of the pole at -1
    deflection_register_slope = -0.30

    # A free reed with nothing bolted to it.
    tonebar_mode_ratios = ()
    tonebar_gains = ()

    # It does not sing as long as a Rhodes: a small reed, a felt damper and no
    # tonebar feeding energy back into it.
    harmonic_decay_db = 16.0
    decay_register_slope = 0.45

    cabinet = "wurlitzer"
    # A true amplitude tremolo, in ONE channel -- a Wurlitzer has one amplifier
    # and one pair of speakers, so unlike the suitcase's pan it survives a mono
    # fold. Same mechanism, one sign.
    tremolo_hz = 5.5
    tremolo_depth = 0.55
    tremolo_stereo = False

    # Same normalisation as its sibling -- C3/C4/C5 at velocity 100, matched on
    # rms against the grand piano. It started 5.1 dB OVER one, which is the
    # small cabinet's midrange doing what a small cabinet does.
    initial_gain = 0.31831274

    def pickup_flux(self, u):
        return 1.0 / (1.0 + u)



class StoppedPipeProperties(SynthProperties):
    # CC71-78: a stopped pipe blown by a player, the pan flute.
    sound_controls = frozenset(('attack', 'release', 'vib_rate', 'vib_depth', 'vib_delay'))
    # A DRIVEN AIR COLUMN HAS NO DAMPER: the tone stops when the wind does, and
    # there is nothing anywhere on the instrument for a pedal to lift. Every
    # pipe, reed, brass and bowed voice in the bank inherits this. The
    # synthesisers that borrow this class's spectrum take it back below,
    # because a pedal on a synth holds the GATE rather than lifting a felt.
    damper_pedal = False

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
    a, b, c, d, e = (GrandPianoProperties.a, GrandPianoProperties.b,
                 GrandPianoProperties.c, GrandPianoProperties.d,
                 GrandPianoProperties.e)
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


class TonewheelProperties(SynthProperties):
    """A Hammond: geared steel wheels turning past magnetic pickups.

    NOT A PIPE, which is why this sits under SynthProperties and not under
    OrganProperties. There is no wind, no jet, no standing wave to build and
    so no speech; a tonewheel is at full amplitude within a millisecond of the
    contacts making, and the transient you hear is the CONTACTS, not the tone.
    Nothing decays. Everything else in this family had to be told how a column
    of air starts; this one has to be told that it does not.

    THE HARMONICS ARE EQUAL-TEMPERED, and that is the single most characteristic
    thing about the instrument. A drawbar does not synthesise a harmonic -- it
    patches in ANOTHER WHEEL, the one already cut for that note of the scale. So
    the "third harmonic" is the tempered twelfth at 2.9966 rather than 3.0, and
    the "fifth" is the tempered seventeenth at 5.0397, which is 13.7 cents SHARP
    of a just third. A Hammond therefore beats against itself on every held
    chord, in a fixed pattern no pipe organ has, and a synthesiser that builds
    the drawbars from exact integer ratios sounds clean and wrong.

    Only nine ratios exist, and the seventh harmonic is not among them.
    """
    # A synchronous motor decides the pitch, not the player.
    pitch_bendable = False
    # A tonewheel runs off a synchronous motor; the key is a switch and the
    # pedal on the console is a swell, not a damper.
    damper_pedal = False
    # NO TOUCH. A tonewheel organ's key is a set of switches closing onto nine
    # busbars: it connects the drawbars' wheels to the output and does nothing
    # else. How fast the key falls changes when the contacts close -- the key
    # click, which this voice models separately -- and never how loud the note
    # is. The expression PEDAL is the volume control, which is CC11.
    touch_sensitive = False

    # NOT MEASURED. Sits between the flue and reed organ so the family balances
    # by ear until somebody puts a B-3 in front of a microphone.
    initial_gain = 0.00015

    # A wheel against a pickup is nearly a sine. Not exactly -- the wheel's
    # profile and the pickup's aperture put a little second and third in -- but
    # the drawbars, not the wheel, are supposed to make the timbre.
    # NOT 3, which was the first guess and wrong: max_harmonic caps the
    # REGISTERED series, so a ceiling of 3 silently deleted every drawbar whose
    # ratio exceeds it -- the 2', the 1-3/5', the 1-1/3' and the 1' simply did
    # not sound, and nothing in the piece reached the horn's side of the
    # crossover. The top drawbar is the 8th, and it wants its own few
    # harmonics, so the cap belongs up here. Wheel purity is tonal_dampening's
    # job and it does it: h2 at -21 dB, h3 at -33, near enough a sine.
    max_harmonic = 24
    tonal_dampening = 3.5
    odd_only = False

    # NO REGISTER SLOPE. Every note is the same nine wheels through the same
    # pickups, so the timbre does not brighten or darken up the compass the way
    # a pipe rank or a string does. Setting this to zero is a claim about the
    # instrument, not a convenience.
    octave_dampening = 0.0
    octave_modulo = False
    octave_gain = 0.0                # nor does it get louder up the keyboard
    enharmonic_width = 0.0
    # Nothing is struck or plucked; these exist because every family has to
    # answer them, not because a wheel has an opinion.
    pluck_dampening = 1.0
    plucked_harmonic = 1000.0

    # Nothing here is a pipe: no chiff, no jet, no air.
    chiff_cycle = 0.0
    chiff_volume = 0.0
    # BUT NOT ZERO VALVE TIMES, which is not the same statement. These are the
    # onset and release FADES, not the chiff, and with the chiff times at zero
    # the release falls back to zero too (see SynthTone.hammer_up: an unset
    # release_valve_time inherits chiff_max_valve_time) and floors at 1e-4 s.
    # Every note then ends in a sample-level step -- Ben heard it immediately,
    # "a bit of a click around the edges... at the ends of all of the notes".
    # It is the harpsichord's damper bug exactly, and this is the second time
    # the same fallback has bitten: see HarpsiBase, where it read as a sampler
    # cutting a voice rather than a damper landing.
    #
    # A Hammond's contacts DO make and break fast, and the click is real and
    # wanted -- but it is a click, not a discontinuity. 1.5 to 3 ms of onset
    # gives the contact bounce; the release runs a little longer because the
    # tone still has an amplifier and a speaker cone to get out through.
    chiff_min_valve_time = 0.0015
    chiff_max_valve_time = 0.0030
    release_valve_time = 0.012
    speech_cycles = 0.0
    mode_lock_spread = 0.0
    inharmonicity_dynamic = False
    inharmonicity_coefficient = 0.0

    # THE KEY CLICK IS THE ATTACK, not an effect laid over it. Nine contacts
    # close within a millisecond or so of each other and each one steps its
    # wheel in from silence; the step IS the click, and it is broadband because
    # it is a step. Give the envelope a millisecond and it arrives on its own.
    attack_time = 0.0015
    decay_db = 0.0                   # a wheel does not decay
    harmonic_decay_db = 0.0
    harmonic_decay_dampening = 0.0
    sustain_level = 1.0

    # DRAWBARS ARE A REGISTRATION, the same machinery the pipe organ and the
    # harpsichord use: CC11 carries the low seven and CC43 the high. Without
    # this flag the renderer treats CC11 as a VOLUME instead (chan_vol becomes
    # (v7*v11)^2 for anything not registerable), so pulling a drawbar would
    # have turned the organ down rather than changed its colour, and the
    # registration would have been stuck on default_stops forever.
    registerable = True

    # The drawbars. Ratios are TEMPERED, not integer -- see above. Amplitudes
    # are the drawbar at 8, the stop mask choosing which are pulled.
    stop_ranks = [
        ("16",    0.5,    1.00),     # sub-fundamental
        ("5-1/3", 1.4983, 0.85),     # sub-third: tempered fifth, not 1.5
        ("8",     1.0,    1.00),     # fundamental
        ("4",     2.0,    0.90),
        ("2-2/3", 2.9966, 0.72),     # tempered twelfth, not 3.0
        ("2",     4.0,    0.66),
        ("1-3/5", 5.0397, 0.52),     # tempered seventeenth: 13.7 cents sharp
        ("1-1/3", 5.9932, 0.45),
        ("1",     8.0,    0.40),
    ]
    crescendo_order = ["8", "4", "16", "2-2/3", "2", "5-1/3", "1-1/3", "1-3/5", "1"]
    # 888 000 000 -- the first three drawbars out, which is where everyone starts.
    default_stops = 0b000000111

    # FOLDBACK. There are only 91 wheels, so the top drawbars have nothing left
    # to patch in and repeat the octave below instead. Without it the upper
    # drawbars run off the end of the generator, which no Hammond does.
    pipe_ceiling_hz = 6000.0

    # The rotating speaker, when there is one. See leslie.py.
    leslie = False
    leslie_fast = True

    # How hard the valve stage is driven, in units of its own grid bias -- so 0
    # is a clean signal path and 1 has the signal reaching the bias point,
    # which is where a 3/2-law triode starts to bend. See tubeamp.py. The
    # distortion it makes is mostly INTERMODULATION between drawbars rather
    # than harmonics of any one of them, which is why a Hammond thickens where
    # a single sine through the same amplifier barely would.
    #
    # THERE IS NO LONGER A CEILING AT 1.0. There used to be, and it was the
    # POWER SERIES' limit rather than the amplifier's: the old stage expanded
    # the transfer function about the operating point, which diverges past the
    # bias, so the only honest thing was to clamp. tubeamp now evaluates the
    # curve instead of expanding it, and the curve has a plate-current ceiling
    # as well as cutoff, so drive past the bias is simply the clip -- which is
    # what real Leslie overdrive is. Drive 1.0 still means the edge of breakup
    # (the stage's slope is 0.62 there); 2 is into it and 4 is well past.
    amp_drive = 0.0


class DrawbarOrganProperties(TonewheelProperties):
    """GM 16. The console itself, no percussion, rotor on chorale."""
    leslie = True
    leslie_fast = False


class PercussiveOrganProperties(TonewheelProperties):
    """GM 17. The same console with the percussion tab down.

    Percussion is a separate decaying tap at the second or third harmonic,
    keyed once per phrase rather than once per note -- a hardware detail this
    does not model. What it does model is the SHAPE: an attack with a bright,
    fast-decaying top over a flat sustain, which is the part that reads.
    """
    default_stops = 0b000001111      # 888 8
    decay_db = 3.0
    harmonic_decay_db = 9.0          # the tap, and it is all in the upper wheels
    harmonic_decay_dampening = 0.0
    sustain_level = 0.80
    leslie = True
    leslie_fast = False


class RockOrganProperties(TonewheelProperties):
    """GM 18. Drawbars out at both ends, rotor running fast, amp pushed."""
    default_stops = 0b100000111      # 888 000 008
    leslie = True
    leslie_fast = True
    # RE-VOICED after tubeamp's units fix. The distortion had been arriving with
    # the valve stage's own gain still on it -- 8 to 9.5 dB hot against a dry path
    # at unity -- so every drive in this file was set to sound right through an
    # amplifier that was shouting. Dividing that out drops the distortion by the
    # same amount, and these numbers put each voice back to the EXACT distortion
    # it made before, measured on a rendered chord against the same chord with
    # the amplifier out.
    #
    # The ratios are not constant -- 1.7x here, 4.8x on the distortion guitar --
    # because the curve compresses: recovering the same distortion from a stage
    # that is already working harder costs disproportionately more drive.
    amp_drive = 1.53


class OrganProperties(StoppedPipeProperties):
    # ---------------------------------------------------------- pipe scaling
    #
    # A rank's directivity is not a fixed aperture, because a rank is not one
    # pipe. But organ SCALING makes it simple anyway: a pipe's diameter is cut
    # in proportion to its speaking length, so for a flue of length L the mouth
    # radius is about L/30, and with f = c/2L that is a = c/(60 f).
    #
    # Then ka at the fundamental is 2*pi*f*a/c = 2*pi/60 = 0.105 -- the SAME for
    # every pipe in the rank, top to bottom. Which means an organ radiates its
    # fundamentals equally in all directions and only begins to beam around the
    # tenth harmonic, whatever note is played. That is why an organ fills a
    # church from anywhere while its brightness depends sharply on where you
    # stand, and why the reverberant field of an organ is duller than the direct
    # sound: the room is fed the fundamentals and denied the upperwork.
    pipe_scale_divisor = 60.0

    def pipe_radius(self, rank_hz):
        """Radiating aperture of the pipe sounding at rank_hz, metres."""
        if rank_hz <= 0.0:
            return 0.0
        return self.sound_speed / (self.pipe_scale_divisor * rank_hz)


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
    # A pallet valve is open or shut and a pipe is cut to length.
    pitch_bendable = False
    # NO TOUCH. A pipe organ key opens a pallet valve. The pipe then speaks at
    # whatever the wind pressure dictates, and pressing harder opens the same
    # valve no further. Dynamics come from the stops and the swell box -- and
    # CC11 IS the swell box, which still applies.
    touch_sensitive = False

    # A PRINCIPAL IS DARKER THAN A REED, and that is most of what tells them
    # apart. OrganProperties sets 1.4 for the family, which measures -6.2 dB
    # per octave of harmonic number on a single D2 with the room switched off
    # -- right for the reed, where a bright series is the point, and far too
    # shallow for an open flue, which the literature puts at -10 to -14. By
    # the eighth partial that was 12 to 24 dB of surplus, audible as an organ
    # that is bright everywhere and has nowhere left to go when the Mixtur
    # arrives. 2.2 measures -11.0 dB/oct. Set HERE and not on the family: the
    # reed's 1.4 is not an error to be corrected, it is the other half of the
    # distinction.
    tonal_dampening = 2.2

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
    # from StoppedPipeProperties) so the flue organ's octave partials lock to the
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
    # CC71-78: the reed winds: breath has an onset, a release and a vibrato.
    sound_controls = frozenset(('attack', 'release', 'vib_rate', 'vib_depth', 'vib_delay'))
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



# ---------------------------------------------------------------- free reeds
# GM 20-23 are a family, and not the one they were mapped to. All four -- reed
# organ, accordion, harmonica, tango accordion -- are FREE reeds, and every one
# of them was rendering as ReedOrganProperties, which is a pipe organ's reed
# RANK: a beating reed with a resonator. That class is right for what it is and
# is the base of the clarinets and ReedPipeProperties, so it stays exactly as it
# is; the error was only in patch_map's _fill(20, 23).
#
# THE DIFFERENCE IS THE RESONATOR, and it decides three things at once.
#
# A beating reed slams shut against a shallot once a cycle, and a PIPE picks out
# which harmonics survive. That pipe is where odd_only comes from (a stopped
# cylinder passes odd multiples) and where pipe_ceiling_hz comes from (a short
# high resonator goes weak and unstable, so a reed rank breaks back early).
#
# A free reed swings THROUGH a close-fitting slot and never seals, and there is
# no resonator at all -- not a short one, not a weak one, none. Pitch is the
# tongue's own bending mode. So:
#
#   - odd_only goes. Nothing is selecting odd multiples.
#   - the break-back goes. There is no resonator to go unstable, which is
#     exactly why an accordion can carry a 4' piccolo rank to the top of its
#     compass where a reed rank in an organ cannot.
#   - the harmonics are made by FLOW MODULATION, not by a resonator.
#
# That last point is the same argument the Rhodes tine makes: one mode, shaped,
# so the series is EXACTLY HARMONIC and needs no mode table. The tongue moves as
# a sinusoid; what is not sinusoidal is the airflow it lets past.

_FREE_REED_CACHE = {}


class FreeReedProperties(SynthProperties):
    """A tongue swinging through a slot. No pipe, no bell, no resonator.

    The flow model, and what is asserted about it. The tongue's displacement is
    a sinusoid. Air passes only while the tongue is clear of the slot, and it is
    INTERRUPTED -- not tapered -- when the tongue swings back across. That jump
    is what makes a free reed buzz: a discontinuity gives 1/k harmonics (about
    -6 dB/octave), where a smooth taper would give 1/k^2 and a much darker
    instrument. Measured on this model the flow alone comes out at -7.9 dB per
    octave, and a voice with its case on at -9.3, with both odd and even
    harmonics present -- the evens being exactly what the stopped pipe's
    odd_only had been forbidding.

    Three parameters, all geometry:

      reed_gate    how far the tongue must swing before the slot is clear
      reed_edge    the crossing is not instant; the tongue has finite speed
      reed_spread  the swing is not identical cycle to cycle and the slot is
                   not a knife edge

    The spread earns its place. An idealised single-shaped pulse has true zeros
    in its spectrum -- at reed_gate = 0.55 the 16th harmonic sat 57 dB down, a
    hole no free reed has, and no amount of reed_edge removed it because it is a
    zero of the pulse and not of the edge. Averaging POWER over a small spread of
    gate positions smears the zeros and leaves the envelope alone. It is the same
    argument SectionMixin makes about a section smearing a comb.

    NOT FITTED TO A RECORDING. The rolloff target is the free-reed literature's
    rough -6 dB/octave; the three numbers are chosen to land near it with
    plausible ripple, not derived from any one instrument's slot geometry.
    """
    # CC71-78: accordion bellows shake and a harmonica player vibrates from the
    # throat.
    sound_controls = frozenset(('attack', 'release', 'vib_rate', 'vib_depth', 'vib_delay'))
    # A free reed's pitch is its own mass and stiffness.
    pitch_bendable = False
    # A free reed speaks while the bellows push and stops when they stop.
    damper_pedal = False
    # NO TOUCH AT THE KEY. A harmonium or accordion key opens a pallet and the
    # BELLOWS set the loudness -- which is why an accordionist's expression is
    # in their left arm. channel_volume still applies and is the right home for
    # it: CC11 on an accordion is the bellows.
    #
    # THE HARMONICA IS THE EXCEPTION and overrides this back to True. It has no
    # keyboard at all: the player's breath is both the valve and the dynamic, so
    # there is no mechanism standing between effort and loudness for the key to
    # bypass. See HarmonicaProperties.
    touch_sensitive = False


    # No pipe. Every one of these is the resonator's doing, and there isn't one.
    odd_only = False
    even_harmonic_db = None
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    pipe_ceiling_hz = 0.0

    # No pipe speech either: a chiff is an air jet finding its edge, and a free
    # reed has no edge to find. What it has is a tongue that takes a moment to
    # come up to amplitude, which is attack_time and speech_cycles below.
    chiff_cycle = 0.0
    chiff_volume = 0.0
    chiff_release = 0.0
    chiff_min_valve_time = 0.0
    chiff_max_valve_time = 0.0

    # SynthProperties is abstract: it carries the machinery, and every concrete
    # family states its own tone attributes. These are the free reed's, and most
    # of them are stated in order to be zero -- which is the point. a..e are the
    # Steinway B stiff-string inharmonicity model and a tongue has no string in
    # it at all; the pluck and octave terms belong to bodies this one does not
    # have. series_volume below replaces the series law outright, so the
    # dampening terms never run, but they must exist to be inherited.
    a = b = c = d = e = 0.0
    octave_modulo = False
    octave_dampening = 0.0
    octave_gain = -0.0
    tonal_dampening = 2.0
    pluck_dampening = 1.0
    plucked_harmonic = 1000.0
    enharmonic_width = 0.0

    reed_gate = 0.55
    reed_edge = 0.15
    reed_spread = 0.15
    reed_points = 21            # gate positions averaged over
    max_harmonic = 32

    # A free reed does not decay -- the wind holds it -- but it does BLOOM: the
    # tongue climbs to amplitude over a few cycles, longer for a big low reed.
    # Gentler than an organ reed's pressure-build, because there is no boot to
    # pressurise: the tongue is simply being got moving.
    attack_time = 0.012
    speech_cycles = 3.0
    decay_db = 2.0
    harmonic_decay_db = 1.0
    harmonic_decay_dampening = 0.0
    sustain_level = 0.92

    # The case, the cavity, the grille cloth. Not a resonator that sets pitch --
    # a lid over the reeds that takes the very top off.
    bore_corner_hz = 5200.0
    bore_order = 2

    initial_gain = 1.0 / 5000   # balance-normalised below, per voice

    def _reed_series(self):
        """The flow spectrum, once per (geometry, length). Cached per class."""
        key = (self.reed_gate, self.reed_edge, self.reed_spread,
               self.reed_points, self.max_harmonic)
        got = _FREE_REED_CACHE.get(key)
        if got is not None:
            return got
        import numpy as _np
        n = 1 << 13
        t = _np.arange(n) / float(n)
        u = _np.sin(2.0 * _np.pi * t)
        power = _np.zeros(n // 2 + 1)
        if self.reed_spread > 0.0 and self.reed_points > 1:
            gates = _np.linspace(self.reed_gate - self.reed_spread,
                                 self.reed_gate + self.reed_spread,
                                 self.reed_points)
        else:
            gates = (self.reed_gate,)
        for g0 in gates:
            x = _np.clip((u - g0) / max(self.reed_edge, 1e-6) + 0.5, 0.0, 1.0)
            a = u * (x * x * (3.0 - 2.0 * x))
            power += (_np.abs(_np.fft.rfft(a)) / float(n)) ** 2
        mag = _np.sqrt(power / len(gates))
        top = min(self.max_harmonic, len(mag) - 1)
        ref = mag[1] if mag[1] > 0 else 1.0
        got = tuple(float(mag[k] / ref) for k in range(0, top + 1))
        _FREE_REED_CACHE[key] = got
        return got

    def series_volume(self, harmonic):
        if self.max_harmonic and harmonic > self.max_harmonic:
            return 0.0
        series = self._reed_series()
        if harmonic >= len(series):
            return 0.0
        return self.gain * series[harmonic]


class ReedOrganFreeProperties(FreeReedProperties):
    """GM 20, the harmonium / American organ: banks of free reeds and a bellows.

    The plainest member, and the reference the other three are voiced against.
    A harmonium has stops, and `registerable` would carry them, but a GM part
    does not ask for a registration and a half-wired one is worse than none;
    this is a single 8' rank.
    """
    # CC71-78: a pumped reed ORGAN: an onset and a release, and nobody's hand
    # on a vibrato.
    sound_controls = frozenset(('attack', 'release'))
    # A big instrument with a wooden case over the reed pans: rounder than an
    # accordion held against the chest, and the case takes more off the top.
    bore_corner_hz = 4200.0
    reed_gate = 0.52
    # Balance-normalised against the CHURCH ORGAN (GM 19) on the same passage
    # in the same room -- the acoustic member of this family and the nearest
    # neighbour in the bank. These voices normalise their own series to h1 = 1,
    # where the pipe classes carry the comb's absolute scale, so the numbers
    # here are ~500x what a pipe voice's look like and mean the same thing.
    initial_gain = 0.05964


class AccordionProperties(FreeReedProperties):
    """GM 21: two or three reed banks per note, DELIBERATELY mistuned.

    Musette. This is the signature of the instrument and it is a different thing
    from a piano's unisons, which is why it does not reuse the piano's machinery.
    A piano's three strings are meant to be identical and are imperfectly tuned,
    so the spread is a random error, drawn per note. An accordion's second reed
    is deliberately offset by a set amount, the same way across the instrument,
    so a tuner can name it: dry is 0-3 cents, American around 8-12, French
    musette 15-20, Scottish up past 25.

    So the offsets here are SYSTEMATIC, not drawn -- and they are what separates
    this voice from GM 23, which is the same instrument tuned dry.
    """
    # 8' + a wet 8'. A third bank (16') for gravity, tuned true.
    reed_detune_cents = (16.0, 0.0)
    reed_bank_gain = (0.85, 0.55)
    reed_bank_ratio = (1.0, 0.5)        # unison, and an octave below

    # Held against the chest with the grille facing out: brighter than the
    # harmonium's cabinet.
    bore_corner_hz = 5600.0
    reed_gate = 0.58
    initial_gain = 0.03588

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        # Each extra bank is a whole reed set, so it carries the full series at
        # its own ratio -- an octave bank is not a detune, it is another reed.
        out = []
        for g, cents, ratio in zip(self.reed_bank_gain, self.reed_detune_cents,
                                   self.reed_bank_ratio):
            if g <= 0.0:
                continue
            det = 2.0 ** (cents / 1200.0) - 1.0
            # A bank sounds at `ratio` times the note, so the partial this voice
            # adds sits at ratio*(1+det) of where the main voice's does.
            out.append((g, 0.0, ratio * (1.0 + det) - 1.0, harmonic_decay, 0.0))
        return out


class TangoAccordionProperties(AccordionProperties):
    """GM 23, the bandoneon: the same instrument tuned DRY.

    A bandoneon is not a musette box. The tremolo that defines GM 21 is most of
    what a tango player does not want, so the wet bank comes down to a couple of
    cents -- enough to thicken, not enough to warble -- and the 16' comes up,
    because the instrument's voice is its gravity.
    """
    reed_detune_cents = (3.0, 0.0)
    reed_bank_gain = (0.80, 0.75)
    bore_corner_hz = 4600.0             # darker: a squarer, heavier box
    reed_gate = 0.50
    initial_gain = 0.03282


class HarmonicaProperties(FormantBody, FreeReedProperties):
    """GM 22: one reed, and a pair of cupped hands.

    The reed is the same mechanism as the other three. What makes a harmonica
    sound like one is everything around it -- a tiny comb, the player's mouth,
    and hands cupped into a cavity that is opened and closed. That is a FIXED
    resonance the harmonics slide through, which is FormantBody's whole reason
    to exist, so the body does the work here rather than the reed.

    One reed per note, so no banks and no musette: a harmonica's warble comes
    from the player, not from the tuning.
    """
    # The one free reed a player blows directly: breath is the dynamic, and
    # there is no key in between. See FreeReedProperties.
    touch_sensitive = True

    # A cupped hand around a small instrument: a broad vocal-tract-like peak
    # low down and a bright one where the comb and the cup ring. Asserted from
    # the size of the cavity, not measured -- see sources.md.
    formants = ((750.0, 500.0, 0.55), (2400.0, 1600.0, 0.75))
    formant_floor = 0.22
    bore_corner_hz = 6500.0             # small and bright
    bore_order = 2
    bell_cutoff_hz = 0.0
    bell_order = 1

    reed_gate = 0.62                    # a small stiff tongue: buzzier
    initial_gain = 0.05713


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
    # CC71-78: a player's effort brightens it, and breath has an onset, a
    # release and a vibrato.
    sound_controls = frozenset(('brightness', 'attack', 'release', 'vib_rate', 'vib_depth', 'vib_delay'))
    # Slurred rather than tongued: the lips keep buzzing and the harmonic
    # shifts, so there is no attack to make -- only the new partial to settle.
    legato_attack_s = 0.015
    # A VALVED GLISS IS NOT A SLIDE. Ben, who plays these: "When we brass
    # players glissando, we do it in many ways. 1. move cleanly from one
    # fingering to another, and blow through the harmonics. 2. move arbitrarily
    # the valves while blowing through the harmonics. 3. pressing down half way
    # on one of the valves to interfere with harmonic alignment, while muffling
    # the gliss, in between. 4. backing off the mouthpiece for a similar effect,
    # to allow for more lip sway."
    #
    # So the reachable pitches are a LATTICE -- harmonic n over the length the
    # valves are adding -- and a gliss walks it rather than sweeping through it.
    # brass_fingering already knows the lattice; it was written for intonation
    # and answers this too.
    glide_mechanism = 'valve'

    # UNTIL THE LATTICE IS BUILT, ONLY THE LIP GLIDES -- which is technique 4,
    # and is real: a player backing off the mouthpiece can sway a note a tone
    # or so without touching a valve. Past that a brass gliss is not a longer
    # version of the same gesture, it is a different one, and rendering it as a
    # smooth sweep would be a worse answer than rendering nothing. So the reach
    # is the lip's reach and a trumpet asked for a fifth plays it clean, until
    # the harmonic walk exists to answer it properly.
    glide_reach_semitones = 2.0
    # A DRIVEN AIR COLUMN IS EXACTLY HARMONIC. The reed, or the lips, lock every
    # mode to the fundamental -- the same reason FlueOrganProperties and
    # ReedOrganProperties carry B = 0. Inheriting the piano's stretch put partial
    # 8 sixty-nine cents sharp here (a hundred and two for the blown pipe), so the
    # upper partials beat against each other and against the other players. That
    # beating is heard as shimmer, and trimming the breath noise cannot remove it,
    # because it is not noise.
    # EFFORT. Measured on the Iowa tenor trombone and French horn across
    # pp/mf/ff: +0.68 and +0.44 dB of harmonic-ladder flattening per dB of
    # level. Brass blooms with effort -- this is the family that does it most,
    # and until now velocity was a pure gain here. 0.55 is the pair's centre,
    # carried by the trumpet and tuba which were not themselves measured; the
    # trombone and horn override it with their own numbers below.
    effort_tilt = 0.55
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


class CylindricalBrassProperties(BrassProperties):
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


class ConicalBrassProperties(BrassProperties):
    """Conical-bore brass (French horn, tuba): the continuous flare damps the
    upper harmonics into a round, mellow tone, and conical instruments speak
    less abruptly -- a rounder, slower attack with a gentler bloom."""
    # BALANCE. Measured K-weighted at the same MIDI velocity, each voice in its
    # own comfortable register, the orchestra spanned 24.8 dB -- a flute 13.7 dB
    # over a trumpet. No score can correct that: the composer's velocities are
    # supposed to set the balance, and they cannot if the voices are not level
    # with each other to begin with. Normalised to the brass, which was the most
    # recently calibrated (against a real trumpet recording).
    # Trimmed +0.83 dB so the spectral fit changes COLOUR and not LEVEL: the
    # equal-velocity balance across the orchestra was calibrated before it,
    # and the fit moved this voice's total energy by that much.
    initial_gain = (1.0 / 5850) * 1.1003
    # FITTED to Iowa Tuba.mf.C2B2 over h1-h12: RMS 11.56 -> 1.25 dB. It was the
    # brightest voice in the brass by a distance -- -8.9 dB at h12 where the
    # recording says -29.8, 21 dB of upper harmonic that is not there. That is
    # why Ben heard the TROMBONE as mellow: the trombone was the closest to right
    # of the four, next to a tuba and a horn that were not.
    # JOINTLY FITTED across Iowa Tuba.mf C1B1 + C2B2 + C3C4.
    # One register is not enough, and this project already knew it: fitting
    # each brass voice to a SINGLE file left the horn 13.5 dB wrong at C4 and
    # put a hole in the middle of the brass section. octave_dampening is what
    # carries a voice from one register to another, and only a multi-register
    # fit can see it -- it comes out NEGATIVE for the trombone and trumpet,
    # which is a brass instrument getting brighter with pitch and effort.
    tonal_dampening = 3.5
    octave_dampening = 0.1
    harmonic_decay_db = 2.0        # gentle brightness bloom
    decay_db = 13.0
    sustain_level = 0.7            # subtle front
    chiff_volume = 0.05
    sustain_jitter = 0.0045
    bore_corner_hz = 800.0
    # Measured (Iowa tuba, C2): the series rises 15.6 dB to h5 (330 Hz). A tuba's
    # bell is enormous but 65 Hz is still below what it radiates well.
    bell_cutoff_hz = 390.0
    bell_order = 5.0
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
FlueOrganProperties.stop_ranks = FlueOrganProperties.stop_ranks + [("flute", 1.0, 0.60, StoppedPipeProperties)]
# Mixtur III -- one drawstop, several very high ranks (1 1/3' + 1' + 2/3'). They sit
# far above the pipe ceiling, so the break-back folds them back constantly to stay
# under it: THAT is a Mixtur's "composition", and why its shimmer re-colors up the
# keyboard instead of turning shrill. A COMPOUND rank: ratio is a list of the ranks'
# footages; the build loops expand it, each sub-rank breaking back on the note's grid
# (so all stay hybrid-locked). Drawn by bit 7 (14-bit stop word: CC11 | CC43<<7).
FlueOrganProperties.stop_ranks = FlueOrganProperties.stop_ranks + [("mixture", [6.0, 8.0, 12.0], 0.28)]
# Trumpet rank gain 0.42: the climax Trompette read too bold; trimmed so the
# peroration crowns without blaring (also relieves the dense close's headroom).
ReedOrganProperties.stop_ranks = ReedOrganProperties.stop_ranks + [("trumpet", 1.0, 0.42, CylindricalBrassProperties, True)]


# --- Broad melodic buckets (generic; specialize per-instrument later) ---

class TrumpetProperties(CylindricalBrassProperties):
    # Radiating aperture: bell 125 mm; ka = 1 at about 880 Hz.
    directivity_radius = 0.062
    """The Bb trumpet, fitted to the Iowa recordings across three registers.

    CylindricalBrassProperties is left as it was, because it is also the spectrum the
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
    # Trimmed +0.37 dB so the spectral fit changes COLOUR and not LEVEL: the
    # equal-velocity balance across the orchestra was calibrated before it,
    # and the fit moved this voice's total energy by that much.
    initial_gain = (1.0 / 4060) * 1.0435
    # FITTED to Iowa Trumpet.novib.mf.C4B4 over h1-h12: RMS 5.29 -> 1.06 dB.
    # The bell was already right; the SOURCE behind it was too fundamental-heavy,
    # so h1 landed 13.3 dB over the recording even with 40 dB of bell on it.
    bell_cutoff_hz = 1600.0
    bell_order = 5.0
    bore_corner_hz = 1700.0
    # JOINTLY FITTED across Iowa Trumpet.novib.mf E3B3 + C4B4 + C5B5.
    # One register is not enough, and this project already knew it: fitting
    # each brass voice to a SINGLE file left the horn 13.5 dB wrong at C4 and
    # put a hole in the middle of the brass section. octave_dampening is what
    # carries a voice from one register to another, and only a multi-register
    # fit can see it -- it comes out NEGATIVE for the trombone and trumpet,
    # which is a brass instrument getting brighter with pitch and effort.
    tonal_dampening = 3.0
    octave_dampening = -0.1


class MutedTrumpetProperties(TrumpetProperties):
    """GM 59, with the mute actually there.

    Program 59 was TrumpetProperties with a comment saying "mute not modelled",
    so a muted part played open. A straight mute is a cone pushed into the bell
    with a narrow annular gap left for the air, and it does three separate
    things, all of which this model already has somewhere to put:

    The bell gets acoustically SMALLER. A brass bell is a high-pass -- below its
    cutoff the wave reflects back down the tube instead of radiating -- and
    shrinking the opening raises that cutoff. So the fundamental and the low
    harmonics, which an open trumpet radiates poorly already, are cut further.
    That, not added brightness, is why a muted trumpet reads as thin and nasal.

    The mute CAVITY resonates. The volume inside the cone with its gap gives a
    broad peak in the upper middle -- around 1.9 kHz for a straight mute -- and
    that peak is the sound people actually identify as "muted".

    The aperture is smaller, so it is LESS directional, not more. Directivity
    goes as k*a, and a mute takes the radiating radius from the bell's 62 mm to
    something nearer 25 mm, which moves ka = 1 from about 880 Hz up past 2 kHz.
    An open trumpet beams its top at the audience; a muted one spreads it. This
    falls straight out of the piston model already in SynthProperties.

    And it is quieter, which is the point of a mute. No equal-loudness trim
    here: the level drop is the instrument, not the fit, and a composer writing
    con sordino expects it.
    """
    # CC71-78: and a mute is a resonator with a Q -- the one acoustic resonance
    # a player puts in.
    sound_controls = BrassProperties.sound_controls | frozenset(('resonance',))
    # The mute's opening rather than the bell's: ka = 1 near 2.2 kHz, so it
    # stays omnidirectional through most of its range.
    directivity_radius = 0.025
    # Raised from the open bell's 1600 Hz: a smaller mouth radiates less low.
    bell_cutoff_hz = 2400.0
    bell_order = 5.0
    # The cavity peak. Broad (low Q) because the gap damps it heavily.
    mute_resonance_hz = 1900.0
    mute_resonance_q = 1.4
    mute_resonance_db = 6.0
    # A straight mute costs about 5 dB on top of what the raised cutoff removes.
    initial_gain = TrumpetProperties.initial_gain * (10.0 ** (-5.0 / 20.0))

    def bore_gain(self, partial_hz):
        g = super(MutedTrumpetProperties, self).bore_gain(partial_hz)
        if self.mute_resonance_hz and self.mute_resonance_db:
            r = partial_hz / self.mute_resonance_hz
            if r > 0.0:
                boost = 10.0 ** (self.mute_resonance_db / 20.0) - 1.0
                g *= 1.0 + boost / (1.0 + (self.mute_resonance_q * (r - 1.0 / r)) ** 2)
        return g

class TromboneProperties(CylindricalBrassProperties):
    # Radiating aperture: bell 216 mm.
    directivity_radius = 0.108
    # THE ONE BRASS WITH NO VALVES AND NO LATTICE. Seven positions, each a
    # semitone lower than the last, on one continuous slide -- so first to
    # seventh is a tritone and everything between them exists. This is the
    # control case for the whole feature: the same controller that smears a
    # trumpet through harmonics is a plain hand speed here.
    glide_mechanism = 'slide'
    glide_reach_semitones = 6.0
    # BALANCE. Measured K-weighted at the same MIDI velocity, each voice in its
    # own comfortable register, the orchestra spanned 24.8 dB -- a flute 13.7 dB
    # over a trumpet. No score can correct that: the composer's velocities are
    # supposed to set the balance, and they cannot if the voices are not level
    # with each other to begin with. Normalised to the brass, which was the most
    # recently calibrated (against a real trumpet recording).
    # Trimmed +2.93 dB so the spectral fit changes COLOUR and not LEVEL: the
    # equal-velocity balance across the orchestra was calibrated before it,
    # and the fit moved this voice's total energy by that much.
    # EFFORT, measured directly on Iowa TenorTrombone pp/mf/ff, 66 pairs, r 0.66.
    effort_tilt = 0.68
    initial_gain = (1.0 / 5468) * 1.4012
    """Tenor trombone: the trumpet's bright brass, but an octave lower and with a
    larger bore.

    It had been sharing CylindricalBrassProperties outright, which put the TRUMPET's
    comfortable centre (370 Hz) on an instrument that lives an octave below it --
    so the trombone's ordinary register looked to the effort curve like a trumpet
    straining at the bottom and was boosted 3 dB throughout. Its own centre and a
    lower bore corner fix both the level and the colour.
    """
    register_center_hz = 149.0
    bore_corner_hz = 1932.1
    bore_order = 1.074
    # Measured (Iowa, C3): the 3rd harmonic at 393 Hz is 7.5 dB above the
    # fundamental -- the same bell high-pass as the horn, at a higher cutoff
    # because the bore is narrower.
    # FITTED to Iowa TenorTrombone.mf.C3B3 over h1-h12: RMS 3.55 -> 1.02 dB.
    # 230 Hz came from ONE observation -- h3 at 393 Hz sitting 7.5 dB over the
    # fundamental -- and three free knobs can satisfy one number in many wrong
    # ways. It also put the trombone's bell cutoff BELOW the tuba's 390, when a
    # trombone bell is half a tuba's diameter and its cutoff must be HIGHER. The
    # family now runs in the order its bells do: trumpet 1600 > trombone 900 >
    # horn and tuba 390.
    bell_cutoff_hz = 1072.8
    bell_order = 3.972
    # A trombone is not an organ pipe. This class inherited 32 from
    # StoppedPipeProperties, which at E2 is a hard ceiling at 2.6 kHz --
    # the register Ben heard as too mellow. Partials above Nyquist are
    # dropped in blockrender, so this only costs where it is real.
    # A trombone is not an organ pipe. This class inherited 32 from
    # StoppedPipeProperties, and at E2 that is a hard ceiling at 2.6 kHz -- the
    # register that sounded too mellow. Partials above Nyquist are dropped in
    # blockrender, so this only costs where the harmonics are real.
    #
    # 96 rather than the 128 the fit wanted, because live.py has to play this:
    #     maxh   HF err   partials   x realtime
    #       32    11.72      19712       105.9
    #       64     6.71      39409        54.8
    #       96     4.63      57666        36.8
    #      128     4.15      69431        29.2
    # 128 buys 0.48 dB for another 20% of the CPU. The knee is at 96.
    max_harmonic = 96
    # JOINTLY FITTED across Iowa TenorTrombone.mf E2B2 + C3B3 + C4B4.
    # One register is not enough, and this project already knew it: fitting
    # each brass voice to a SINGLE file left the horn 13.5 dB wrong at C4 and
    # put a hole in the middle of the brass section. octave_dampening is what
    # carries a voice from one register to another, and only a multi-register
    # fit can see it -- it comes out NEGATIVE for the trombone and trumpet,
    # which is a brass instrument getting brighter with pitch and effort.
    tonal_dampening = 2.901
    octave_dampening = -0.0715



class BassTromboneProperties(TromboneProperties):
    # Radiating aperture: bell 242 mm.
    directivity_radius = 0.121
    """The instrument that actually plays a trombone part below C2.

    MEASURED: Iowa BassTrombone.mf, four registers, C#1-G4, 43 notes.

    Routed from SOLO_SPLIT[57] below C2, which is where a tenor with an F
    attachment finally runs out. It is a real instrument doing a real job rather
    than a transposed tenor: judged on the Iowa bass trombone with BOTH classes
    given enough harmonics, the tenor scores HF 5.90 dB and this scores 4.11.

    max_harmonic is 256 against the tenor's 96, because THE CEILING HAS TO SCALE
    WITH HOW LOW THE INSTRUMENT PLAYS. At C#1 (34.6 Hz) even 96 harmonics stop at
    3.3 kHz while the recording carries past 8 kHz; the sweep runs HF 10.62 ->
    7.62 -> 5.50 -> 4.11 dB at 96/128/192/256 and then flattens. The tenor does
    NOT get 256 -- there it buys 0.49 dB for 43 per cent more partials, the same
    trade already rejected when its own ceiling was set. Here the notes are both
    rare and genuinely that low.
    """
    tonal_dampening = 2.854
    octave_dampening = 0.1446
    bore_corner_hz = 826.6
    bore_order = 1.022
    bell_cutoff_hz = 950.3
    bell_order = 3.442
    register_center_hz = 175.9
    max_harmonic = 256

class HornProperties(ConicalBrassProperties):
    # Radiating aperture: bell 310 mm. The bell really does point back and
    # right with the player's hand in it, and the audience hears it off axis
    # and by reflection -- but this voice's SPECTRUM was fitted to a horn
    # recording, which already contains that. Turning the axis away here
    # would charge for the same mellowness twice, and the direct-path model
    # has no back wall to return the energy the way a hall does. So only the
    # seat geometry applies, as it does to every other instrument, and the
    # bell's own direction stays in the calibrated spectrum where it was
    # measured. Set directivity_axis_deg to experiment, but expect it to be
    # too dark until there is a reflection model to put the energy back.
    directivity_radius = 0.155
    # BALANCE. Measured K-weighted at the same MIDI velocity, each voice in its
    # own comfortable register, the orchestra spanned 24.8 dB -- a flute 13.7 dB
    # over a trumpet. No score can correct that: the composer's velocities are
    # supposed to set the balance, and they cannot if the voices are not level
    # with each other to begin with. Normalised to the brass, which was the most
    # recently calibrated (against a real trumpet recording).
    # Trimmed so the spectral fit changes COLOUR and not LEVEL: the
    # equal-velocity balance across the orchestra was calibrated before it, and
    # each fit moved this voice's total energy by that much. -0.29 dB from the
    # first fit, then +0.32 dB back when the four-register one raised the
    # harmonic ceiling.
    initial_gain = (1.0 / 4648) * 1.0032
    # EFFORT, measured directly on Iowa Horn pp/mf/ff, 46 pairs, r 0.35.
    effort_tilt = 0.44
    """French horn: dark like the tuba's family, but it plays where a trumpet does.

    Sharing ConicalBrassProperties gave it the TUBA's centre of 130 Hz, so the horn's
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
    register_center_hz = 299.7# around C4, the horn's comfortable middle
    # RE-MEASURED across four registers of Iowa Horn.mf -- Bb1B1, C2B2, C4B4,
    # C5F5, 32 notes from Bb1 to F5. The previous fit used TWO registers and was
    # the weakest brass fit on record at 4.79 dB.
    #
    # HF error 17.24 -> 4.75 dB; shape 6.32 -> 6.75, which is the usual price of
    # a top end that is actually there. Most of the win is the harmonic ceiling
    # (17.24 -> 7.78 from that alone) and the rest is the bore: keeping the old
    # 800 Hz roll-off while taking every other fitted value leaves HF at 13.58.
    #
    # NOTE C3-B3 HAS NO mf TAKE at Iowa -- only pp and ff -- so the fit
    # interpolates across the middle of the range rather than measuring it.
    # Mixing an ff take in would have brought a different dynamic's spectrum
    # into an mf fit, which is a worse error than the gap.
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
    # FITTED to Iowa Horn.mf.C2B2 over h1-h12: RMS 8.01 -> 1.65 dB.
    bell_cutoff_hz = 338.8
    bell_order = 5.037
    # JOINTLY FITTED across Iowa Horn.mf C2B2 + C4B4.
    # One register is not enough, and this project already knew it: fitting
    # each brass voice to a SINGLE file left the horn 13.5 dB wrong at C4 and
    # put a hole in the middle of the brass section. octave_dampening is what
    # carries a voice from one register to another, and only a multi-register
    # fit can see it -- it comes out NEGATIVE for the trombone and trumpet,
    # which is a brass instrument getting brighter with pitch and effort.
    tonal_dampening = 2.990
    bore_corner_hz = 6000.0
    # SQRT(F), NOT A CORNER. Viscothermal wall losses in a tube scale as the
    # square root of frequency (Kirchhoff), and a horn is 5.5 m of tubing, so
    # wall loss is what shapes its top -- not a resonant roll-off. The fit drove
    # bore_order to its lower bound looking for exactly that law; 0.5 IS the law,
    # and the error surface is flat between 0.4 and 0.5 (HF 4.42 vs 4.48), so
    # the physical value costs nothing. The other brass keep their steeper
    # exponents because nobody has measured them this way yet.
    bore_order = 0.50
    # 32 came from StoppedPipeProperties, an ORGAN PIPE base, and at Bb1 that is
    # a hard ceiling at 1.9 kHz. The ceiling is chosen so each instrument reaches
    # about the same ABSOLUTE frequency: the tenor trombone's 96 at E2 reaches
    # 7.9 kHz, and a horn at Bb1 needs 128 for the same. HF by ceiling:
    #     32 -> 14.91   64 -> 9.35   96 -> 6.66   128 -> 4.75   192 -> 3.85 dB
    max_harmonic = 128
    octave_dampening = 0.1409


_BRASS_SECTION = {}


_BRASS_BLEND = {}

# Which of a brass class's numbers are FREQUENCIES. A filter corner interpolates
# in the log domain -- halfway between a trombone's 1073 Hz bell and a trumpet's
# 1600 is 1310, not 1337, and for wider gaps the difference is large (a conical
# 390 against a trumpet 1600 is 790 geometrically and 995 linearly). Everything
# else -- orders, dB, times, fractions -- is linear.
_BRASS_LOG = ("bell_cutoff_hz", "bore_corner_hz", "register_center_hz",
              "initial_gain")


def brass_blend(lo, hi, t):
    """A body t of the way from `lo` to `hi`. Cached per (lo, hi, rounded t).

    THE SECTION IS MIXED, and that is the point rather than a smoothing trick.
    GM 61 handed over from trombones to trumpets at a single note, so one
    semitone changed the spectrum by 13.2 dB on average and 23.2 at the sixth
    harmonic -- against 1.5 to 5.6 dB for a semitone step inside one instrument.
    Measured, the seam was two to three times the natural variation.

    A real brass section does not hand over at a point. A trumpet plays F#3 to
    D6 and a trombone E2 to F5, so they overlap by two octaves, and a section on
    a unison line at C4 has both of them on it. What the hard split modelled was
    not a section at all.

    WHAT THIS IS NOT. Blending the two bodies' PARAMETERS is not the same as
    summing two sections' outputs -- the honest version is partials from both
    classes on one note, which the renderer can only do today through the organ's
    registration path, and that would drag a swell box and a CC11 mask onto a
    trumpet. This is the piano's answer instead: `string_crescendo_semitones`
    fades an added string in across its break because "a real piano is voiced so
    the crossings are seamless". Same argument, same shape of fix, and it is a
    crossfade of the colour rather than of the ensemble.
    """
    key = (lo, hi, round(float(t), 3))
    got = _BRASS_BLEND.get(key)
    if got is not None:
        return got
    t = max(0.0, min(1.0, float(t)))
    body = {}
    for k in dir(lo):
        if k.startswith("_"):
            continue
        a = getattr(lo, k, None)
        b = getattr(hi, k, None)
        if not isinstance(a, (int, float)) or isinstance(a, bool):
            continue
        if not isinstance(b, (int, float)) or isinstance(b, bool):
            continue
        if a == b:
            continue
        if k in _BRASS_LOG and a > 0.0 and b > 0.0:
            v = _exp(_log(a) + (_log(b) - _log(a)) * t)
        else:
            v = a + (b - a) * t
        body[k] = type(a)(round(v)) if isinstance(a, int) else v
    body["__doc__"] = ("%s blended %.0f%% toward %s, across the section's range "
                       "handover." % (lo.__name__, 100 * t, hi.__name__))
    got = type("%sTo%s%02dProperties"
               % (lo.__name__.replace("Properties", ""),
                  hi.__name__.replace("Properties", ""), round(t * 100)),
               (lo,), body)
    _BRASS_BLEND[key] = got
    return got


def brass_section(cls):
    """One brass instrument, played by five of them.

    GM 61 used to be a single class over the whole range -- five trombones at
    every pitch -- and patch_map has said since it was written that the brass
    instruments "cannot share one class: doing so boosted the trombone 3 dB
    through its whole range (trumpet's centre) and the horn 2 dB through its
    (tuba's centre)". A section made of one of them breaks that rule at every
    note outside its register. The bodies really are different: trumpet's bell
    cuts at 1600 Hz and its bore at 1800, a trombone's at 230 and 1600.

    So the ensemble routes by range like the strings do, and this wraps whichever
    instrument the note landed on in a section. Cached per class, the way
    slow_bow and percussion_map._with_ring are.

    Not the strings' numbers: FIVE players not seven (a GM brass section is a
    punchy unison of a few trumpets and trombones, not a desk-doubled body), a
    tighter pitch spread (brass hear beats against each other strongly on a
    sustained tone and lock to them), much less vibrato (orchestral brass plays a
    section passage nearly straight), and a narrower stage (brass sit in a block).
    """
    got = _BRASS_SECTION.get(cls)
    if got is None:
        n = 5
        got = type(cls.__name__.replace("Properties", "") + "SectionProperties",
                   (SectionMixin, cls), {
            "section_players": n,
            "section_spread_cents": 5.0,
            "section_vibrato_cents": 2.5,
            "section_vibrato_hz": (5.0, 6.6),
            "section_width_m": 0.9,
            "section_onset_ms": 6.0,
            # /sqrt(players), as the string sections do it: the players are at
            # different pitches, so they are incoherent and add in POWER. Keeps
            # a section at the loudness the one instrument was calibrated to.
            "initial_gain": cls.initial_gain / (n ** 0.5),
            "__doc__": "Five %s, routed here by register." % cls.__name__,
        })
        _BRASS_SECTION[cls] = got
    return got


class MalletProperties(PluckedStringProperties):
    """Struck bar/bell: bright inharmonic onset, fast shimmer decay. Covers
    the chromatic-percussion family (celesta, glockenspiel, vibraphone,
    marimba, xylophone, tubular bells) and struck ethnic/percussive metal
    (kalimba, steel drums, tinkle bell, agogo, woodblock). A first generic
    voice; a true modal-bar model is the realism step."""
    # A struck bar keeps the pitch it was cut to.
    pitch_bendable = False
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



class PizzicatoStringsProperties(FormantBody, SectionMixin, PluckedStringProperties):
    """GM 45: a string section PLUCKING. Not the generic plucked string.

    It had been PluckedStringProperties, which has no `formants` attribute at
    all -- so a pizzicato section was being rendered with NO BODY: a bare string
    series with a bore roll-off, and nothing of the violin about it. That is the
    same hole the acoustic bass was in.

    Three claims, and each one comes from a different place:

    THE BODY IS A VIOLIN'S, and it is measured -- the bridge hill at 2300 Hz
    that ViolinProperties carries, from the Iowa recordings. A pizzicato note
    radiates through exactly the same box as a bowed one; what changed is how
    the string was set going, and a body does not know or care.

    IT IS A SECTION, so SectionMixin, which exists precisely to be mixed into
    whatever is doing the playing. Fewer players than the bowed sections use,
    and a WIDER spread: a section plucking is less together than a section
    bowing, because a bow stroke can be matched to a neighbour's over its whole
    length and a pluck is over before anyone can adjust.

    AND NO VIBRATO. A pizz note in a section is too short to vibrate, and
    section_vibrato_cents = 0 is exactly what SectionMixin's docstring warns
    about -- a player with no depth has no rate or phase either. That warning is
    about a voice whose wheel raises a resting vibrato; this voice has none to
    raise, which is the point. The entry scatter does the decorrelating instead.

    NOT MEASURED. The body is; the pluck is argued. Rated 2.
    """
    # The measured violin body, unchanged -- see ViolinProperties.
    formants = ((2300.0, 1400.0, 0.55),)
    formant_floor = 0.05
    bore_corner_hz = 4000.0
    bore_order = 2.0
    bell_cutoff_hz = 150.0
    bell_order = 2.0

    # Plucked over the end of the fingerboard, which on a violin is about a
    # fifth of the way along from the bridge -- much further out than a guitar's
    # pick, hence rounder. A finger, so the notch fills at no dynamic: a
    # fingertip is soft but it does not flatten with force the way felt does.
    strike_point = 0.20
    strike_depth = 0.70
    strike_fills_with_force = False

    # A PIZZ NOTE IS SHORT. This is what most separates it from every other
    # plucked voice in the bank: a guitar rings for seconds and a pizzicato
    # violin is gone in well under one, because a short thin string on a stiff
    # box is heavily damped and the player's next stop kills it anyway.
    # A BASS PIZZ RINGS AND A VIOLIN PIZZ SNAPS, and that is one law rather than
    # four numbers: decay_register_slope scales the rate with the note's own
    # register, and a slope of 1.0 would be rate proportional to frequency --
    # the standard string result, a fixed number of CYCLES rather than a fixed
    # number of seconds. 0.85 is a touch under that, as the piano's is, because
    # a real bass string is not purely frequency-damped. Re-fitted below once
    # this was switched on, since it changes what decay_db means.
    decay_register_slope = 0.85

    # Measured on a rendered note, 7.0 dB/s left it ringing 2.2 s to -30 dB,
    # which is a guitar. A pizzicato violin is gone in well under a second: a
    # short thin string on a stiff box is heavily damped, and the player's next
    # stop kills what is left. 30 + 12 measured 0.27 s, snappier than the real
    # thing; 16 + 8 lands at 0.5, inside the 0.4-0.8 a pizz note actually has.
    # The nominal rate and the measured one differ because the upper partials
    # dominate the envelope early -- which is why this was measured and not
    # calculated.
    decay_db = 16.0
    harmonic_decay_db = 8.0
    harmonic_decay_dampening = 0.0
    tonal_dampening = 1.45
    max_harmonic = 40

    section_players = 6
    section_spread_cents = 8.0          # wider than the bowed section's 6
    section_vibrato_cents = 0.0         # a pizz note has no time to vibrate
    section_onset_ms = 26.0             # and they do not pluck in the same instant

    # Balance-normalised against the MEASURED violin (GM 40) on the same passage
    # in the same room: the same section, the same body, playing differently, so
    # it is the one comparison that means anything here.
    initial_gain = 0.2383


class HarpProperties(FormantBody, PluckedStringProperties):
    """GM 46: the orchestral harp. One instrument, not a section.

    Also on the generic plucked string until now, and also therefore bodiless.

    WHAT MAKES A HARP SOUND LIKE ONE is where it is plucked and with what. A
    harpist plucks with the flesh of the finger, not a nail or a plectrum, well
    in toward the middle of the string -- and a centre pluck is the darkest
    place there is, because the comb |sin(n*pi*p)| puts its first null at
    n = 1/p. At p = 0.38 that is the third partial, so the fundamental carries
    the note and the low harmonics are already thinned. That, and not a filter,
    is why a harp is mellow.

    AND IT RINGS. The strings are anchored directly into the soundboard with no
    bridge in between, which is why a harp is loud for its size and why an
    undamped note sings on for seconds. Nothing here damps it: the decay is slow
    and the upper partials only a little faster.

    NOT MEASURED. Rated 2.
    """
    # A tapered spruce soundboard over a long tapering box: a broad low
    # resonance where the body is deep, a second where it is shallow. Asserted
    # from the shape of the instrument, not from a recording.
    formants = ((260.0, 180.0, 0.50), (1100.0, 800.0, 0.35))
    formant_floor = 0.12
    bore_corner_hz = 3600.0             # finger flesh: no top end to speak of
    bore_order = 2.0
    bell_cutoff_hz = 90.0               # a big box, but not an infinite one
    bell_order = 2.0

    # Plucked in toward the middle. The null at h3 is the instrument's voice.
    strike_point = 0.38
    strike_depth = 0.80
    strike_fills_with_force = False

    # Anchored into the board and undamped: this is the longest sustain of any
    # plucked voice in the bank, which is the other half of sounding like a harp.
    decay_db = 0.35
    harmonic_decay_db = 0.9
    harmonic_decay_dampening = 0.0
    tonal_dampening = 1.25
    max_harmonic = 48

    # Balance-normalised against the measured violin, as the pizzicato is.
    initial_gain = 0.1183


class BowedStringProperties(SectionMixin, StoppedPipeProperties):
    """Sustained bowed string: full harmonic series with a sawtooth-ish
    1/n tilt, no chiff, gentle onset. Covers solo strings (violin, viola,
    cello, contrabass), string/synth ensembles, choir/voice pads, and
    sustained synth leads/pads as a broad bucket. This is the brighter
    'first' section; BowedStringSecond is the darker companion."""
    # CC71-78: a bow has an onset, a release and a vibrato; nothing brightens a
    # violin but the player's bow, which is velocity.
    sound_controls = frozenset(('attack', 'release', 'vib_rate', 'vib_depth', 'vib_delay'))
    legato_attack_s = 0.012   # the bow never leaves the string; only the stopped length changes
    # AND IF THE STOPPED LENGTH SLIDES INSTEAD OF STEPPING, that is portamento
    # -- the same sentence as the line above, carried further. A hand position
    # spans about a fifth before a shift, which is the reach a player has
    # without lifting; beyond it they still slide, but it is a shift and sounds
    # like one.
    glide_mechanism = 'stop'
    glide_reach_semitones = 7.0
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
    # +4.3 dB. The string family measured that far UNDER the rest of the orchestra
    # at equal velocity (K-weighted, each voice in its own comfortable register),
    # which is the balance convention this set is supposed to hold to but was not.
    # Raised on the BASE so the family's own ratios (viola, contrabass) are kept.
    initial_gain = (1.0 / 9381 / (section_players ** 0.5)) * 1.6406
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
    # has been dead since it was written: StoppedPipeProperties sets
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


# --- The violin family, one class per instrument -----------------------------
#
# Until now violin, viola, cello and contrabass shared ONE class with no body at
# all -- a 3 kHz lowpass and octave_dampening -- and the Iowa recordings say a
# single body cannot serve them. Pooling every harmonic of every note by ABSOLUTE
# frequency (a body resonance is a boost at a fixed frequency whatever harmonic
# lands on it, so it survives the pooling and the 1/n tilt does not):
#
#   violin   1.9-2.7 kHz  +7.7 dB   <- the bridge hill
#   cello      168-240 Hz +5.5 dB, 800-950 Hz +7.4 dB, 1.9-2.3 kHz +4.5 dB
#
# Different boxes, in different places. The old shared class matched the CELLO
# within 1.5 dB over h2-h12 and was 6.0 dB too dark on the VIOLIN, which is what
# you would expect of a model with no bridge hill in it.
#
# Viola and contrabass were NOT recorded here. Their resonances are scaled from
# the measured neighbours by body length -- a viola box is about 1.15x a violin's
# so its modes sit about 0.85x as high, a contrabass about 0.55x a cello's --
# which is a defensible guess and not a measurement. Marked as such.

class ViolinProperties(FormantBody, BowedStringProperties):
    """MEASURED: Iowa Violin.arco.mf, sulD and sulG, 15 notes."""
    formants = ((2300.0, 1400.0, 0.55),)     # the bridge hill
    # FITTED, not carried over. A body doing part of the rolloff means the
    # SOURCE must do less of it or the two compound -- carrying the old
    # tonal_dampening = 1.0 across left the violin 2.5 dB too bright. Grid search
    # over (tonal_dampening, formant_floor) against the Iowa violin, h1-h12:
    # RMS 2.03 dB, h2-h12 mean -0.4.
    formant_floor = 0.05
    tonal_dampening = 1.6
    bore_corner_hz = 4000.0                  # above the hill, not through it
    bore_order = 2.0
    # Its lowest string is G3 = 196 Hz and the Iowa D4 fundamental is the
    # strongest partial in the note, so the box radiates its whole range: the
    # cutoff sits below the instrument rather than inside it.
    bell_cutoff_hz = 150.0
    bell_order = 1.5


class SoloViolinProperties(ViolinProperties):
    """One violin, not a desk of seven.

    GM says program 40 is a Violin and 48 a String Ensemble, so by the spec the
    singular programs are single instruments. This model makes 40-43 sections
    instead, because that is how orchestral MIDI actually uses them -- Holst's
    string parts arrive on 40/41/42/43 and want seven players each -- and
    changing that now would turn every string section in the corpus into a
    soloist.

    So the distinction lives here rather than there. A concerto is solo against
    tutti and nothing else, and a soloist rendered as a section is not a small
    error: seven players a few cents apart with their own entry scatter is
    precisely the sound a concerto exists to contrast against.

    Mapped to GM 110, Fiddle, which is a single player by any reading and was
    previously a section by inheritance.
    """
    section_players = 1
    section_spread_cents = 0.0
    section_onset_ms = 0.0
    # AND THE GAIN MUST COME WITH IT. initial_gain is evaluated in
    # BowedStringProperties' class body as 1/9381 / sqrt(section_players) with
    # section_players = 7, so that a desk of seven and a single instrument come
    # out at the same TOTAL level. Overriding the count here without touching
    # the gain therefore leaves the soloist playing at one seventh of a section
    # -- sqrt(7), 8.4 dB down -- which is exactly what Ben heard.
    initial_gain = ViolinProperties.initial_gain * (ViolinProperties.section_players ** 0.5)


class ViolaProperties(FormantBody, BowedStringProperties):
    """MEASURED: Iowa Viola.arco.mf, sulC C3B3 and C4B4, sulA C5B5.

    It used to be the violin's resonances scaled down by body length, and the
    recording says that guess was half right. The bridge hill was close -- 1950
    Hz guessed against a real peak at 1920-2283, +10.7 dB. The low body was not:
    600 Hz guessed where 480-679 is in fact a DIP, with the real peaks at 430 and
    1030.

    Everything below jointly fitted across all three registers, formant
    AMPLITUDES included -- fitting only the shape left it at 7.6 dB, because the
    amplitudes I read off the pooled spectrum are in the wrong scale for a model
    that has its own tilt underneath them. RMS 7.56 -> 4.65 dB over h1-h12.
    """
    formants = ((430.0, 220.0, 0.16), (1030.0, 450.0, 0.10), (2100.0, 1000.0, 0.60))
    # Trimmed -0.52 dB so the fit changes COLOUR and not LEVEL -- the
    # equal-velocity balance predates it, and the fit moved this voice's
    # total energy by that much.
    initial_gain = BowedStringProperties.initial_gain * 0.9419
    formant_floor = 0.10
    tonal_dampening = 1.50
    octave_dampening = -0.30
    bore_corner_hz = 3600.0
    bore_order = 2.0
    bell_cutoff_hz = 350.0
    bell_order = 3.0


class CelloProperties(FormantBody, BowedStringProperties):
    """MEASURED: Iowa Cello.arco.mf, sulC and sulD, 14 notes."""
    formants = ((190.0, 90.0, 0.45), (870.0, 500.0, 0.60), (2050.0, 900.0, 0.35))
    formant_floor = 0.05        # fitted: RMS 4.95 dB over the D3 and C2 files
    tonal_dampening = 1.8
    bore_corner_hz = 3000.0
    bore_order = 2.0
    # Measured: the low C's fundamental sits 11.2 dB under the strongest partial.
    # 240 Hz / order 2 puts ours at -12.9 with h3 strongest, against Iowa's -11.2
    # with h2 strongest -- the same shape, which a monotonic model cannot make at
    # all because it puts h1 on top by construction.
    bell_cutoff_hz = 240.0
    bell_order = 2.0


class ContrabassProperties(FormantBody, BowedStringProperties):
    """MEASURED: Iowa Bass.arco.mf, sulE E1B1, sulA C2B2, sulG C3B3.

    It used to be the cello's resonances scaled down, and only the lowest one
    survived contact with the recording: 105 Hz guessed against a real peak at
    85-101, +8.4 dB. The other two were wrong -- 480-571 is a DIP rather than the
    peak I put there, and 1142-1358 is flat. The real ones sit at 190 (+8.4) and
    1750 (+6.6).

    The fit then reduced the 190 and 880 poles to almost nothing (0.06 and 0.03),
    so what carries this instrument is the 93 Hz body and the 1750 Hz upper
    resonance. They are kept because they were measured, not because they earn
    much. Jointly fitted across all three registers: RMS 7.77 -> 4.24 dB.
    """
    formants = ((93.0, 45.0, 0.90), (190.0, 100.0, 0.06),
                (880.0, 400.0, 0.03), (1750.0, 800.0, 0.60))
    # Trimmed +1.01 dB so the fit changes COLOUR and not LEVEL -- the
    # equal-velocity balance predates it, and the fit moved this voice's
    # total energy by that much.
    initial_gain = BowedStringProperties.initial_gain * 1.1233
    formant_floor = 0.05
    tonal_dampening = 2.00
    octave_dampening = 0.00
    bore_corner_hz = 5500.0
    bore_order = 2.0
    bell_cutoff_hz = 135.0
    bell_order = 3.0


_SLOW_BOW = {}


_PIZZICATO = {}


def pizzicato(cls):
    """The same BODY, plucked -- GM 45. Cached per class, as slow_bow is.

    GM 45 wore one body across its whole compass, which made every low pizz a
    violin playing low. It is the section that GM 44 is, scored the same way,
    so it routes the same way: the register picks the instrument and the
    articulation rides on it.

    BUT IT INVERTS tremolo_bow's DIRECTION, and that is the whole reason this is
    a separate function rather than another entry in the same table. tremolo_bow
    takes a bowed class and keeps it bowed, changing only the stroke. A
    pizzicato is not a bowed instrument at all: the excitation, the decay and the
    whole class lineage are a PLUCKED string's. So this goes the other way --
    it takes the PLUCKED class and lends it the bowed instrument's body, exactly
    as AcousticBassProperties borrows the measured contrabass's.

    What transfers is the box and only the box. A body does not know how the
    string it is carrying was set going.
    """
    got = _PIZZICATO.get(cls)
    if got is None:
        got = type(cls.__name__.replace("Properties", "") + "PizzProperties",
                   (PizzicatoStringsProperties,), {
            "formants": cls.formants,
            "antiformants": getattr(cls, "antiformants", ()),
            "formant_floor": cls.formant_floor,
            "bore_corner_hz": cls.bore_corner_hz,
            "bore_order": cls.bore_order,
            "bell_cutoff_hz": cls.bell_cutoff_hz,
            "bell_order": cls.bell_order,
            "__doc__": "%s's body, plucked -- GM 45." % cls.__name__,
        })
        _PIZZICATO[cls] = got
    return got


_TREMOLO_BOW = {}


def tremolo_bow(cls):
    """The same instrument, bowed TREMOLO -- GM 44. Cached per class, as
    slow_bow is.

    A TRANSFORM AND NOT A CLASS, and that distinction is the whole design. GM 44
    is in BOWED_ENSEMBLE, so the renderer already routes each note to the
    instrument whose register it falls in -- and it is right to: a low tremolo is
    a CELLO section bowing tremolo, not a violin section playing low. A
    `TremoloStringsProperties(ViolinProperties)` was written first and was wrong
    for exactly that reason, and the per-note router quietly overrode it, which
    is how the error was found. The articulation has to ride on whichever body
    the register picks, the same way slow_bow does for GM 49.

    THE STROKE. Rapid unmeasured bowing, eight to twelve strokes a second. What
    it does to the sound is amplitude modulation, and this renderer makes that
    out of partials rather than out of an LFO:

        (1 + m cos(w t)) sin(W t) = sin + (m/2)[ sin(W+w) + sin(W-w) ]

    so it costs one sideband pair per partial and no new machinery -- the
    identity is tremolo.py's, written for the Wurlitzer.

    THE SECTION IS THE DIFFICULTY. A Wurlitzer has ONE modulator. Fourteen
    players bowing tremolo have fourteen, because nobody counts strokes, so the
    section smears into a shimmer where a single modulator gives a 9 Hz throb
    that sounds like an effect pedal bolted to an orchestra. tremolo_scatter
    gives each player their own rate and phase; see tremolo.py.

    AND IT IS BRIGHTER. A reversal every 105 ms means the note lives in its
    attack, so the upper partials never settle the way a long stroke lets them.
    """
    got = _TREMOLO_BOW.get(cls)
    if got is None:
        got = type(cls.__name__.replace("Properties", "") + "TremoloProperties",
                   (cls,), {
            # Mid-range of the orchestral eight-to-twelve, and well clear of the
            # 4.6-6.4 Hz this same section's VIBRATO runs at: the two must not
            # be confusable, and a tremolo that landed in the vibrato band would
            # simply read as a nervous player.
            "tremolo_hz": 9.5,
            "tremolo_depth": 0.70,        # the string never actually stops
            "tremolo_stereo": False,
            "tremolo_intrinsic": True,    # GM 44 IS tremolo, not a wheel effect
            "tremolo_scatter": 0.20,      # +/-20% of rate per player, free phase
            # The bite of a reversal every 105 ms.
            "tonal_dampening": max(0.2, cls.tonal_dampening - 0.25),
            "__doc__": "%s bowed tremolo, GM 44." % cls.__name__,
        })
        _TREMOLO_BOW[cls] = got
    return got


def slow_bow(cls):
    """The same instrument, drawn slowly -- GM 49, `SlowStr`. Cached per class,
    the way percussion_map._with_ring makes its per-note ring subclasses, so the
    second ensemble gets the same four bodies rather than losing them."""
    got = _SLOW_BOW.get(cls)
    if got is None:
        got = type(cls.__name__.replace("Properties", "") + "SlowProperties", (cls,), {
            "chiff_min_valve_time": 0.12,
            "chiff_max_valve_time": 0.30,
            "tonal_dampening": cls.tonal_dampening + 0.25,
            "max_harmonic": 32,
            "__doc__": "%s with the slow bow of GM 49." % cls.__name__,
        })
        _SLOW_BOW[cls] = got
    return got


class SlowBowedStringProperties(BowedStringProperties):
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
    # +4.3 dB. The string family measured that far UNDER the rest of the orchestra
    # at equal velocity (K-weighted, each voice in its own comfortable register),
    # which is the balance convention this set is supposed to hold to but was not.
    # Raised on the BASE so the family's own ratios (viola, contrabass) are kept.
    initial_gain = (1.0 / 8536 / (BowedStringProperties.section_players ** 0.5)) * 1.6406
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


# --- The guitar box (GM 24) --------------------------------------------------

class SitarProperties(PluckedStringProperties):
    """GM 104. A long steel string over a curved bridge, and thirteen more
    strings underneath that nobody touches.

    ASSERTED, NOT MEASURED, and the steelpan is the cautionary tale: its
    ratios were right and every one of its gains was wrong by 25 to 30 dB when
    a recording finally turned up. Neither collection has a sitar -- Iowa's
    plucked instruments are guitar and piano, and VCSL's Composite
    Chordophones are a concert harp, a folk harp and a strumstick. So the
    SHAPE here follows from how the instrument is built and the LEVELS are
    guesses, which is the distinction that matters.

    THE JAWARI IS THE SOUND. A sitar's bridge is not a knife edge, it is a wide
    gently curved plate, and the string rests along it rather than on a point.
    As the string swings, its contact point MIGRATES along that curve -- the
    speaking length is shortening and lengthening every cycle -- and a boundary
    that moves at the frequency of the string generates energy high in the
    series continuously rather than only at the pluck. That is why a sitar
    buzzes and keeps buzzing, where a guitar's attack is bright and then dulls.

    APPROXIMATED, LIKE THE SLAP BASS AND FOR THE SAME REASON: a moving boundary
    condition is not something this engine can state. What it can state is the
    consequence, and here there are two -- a very shallow spectral roll-off, so
    the series is rich to begin with, and an unusually FLAT decay across the
    harmonics, so the top does not die away before the fundamental does. The
    second is the one that matters and the one a bright plucked string would
    not give: on a normal string the upper partials go first.

    NO BODY HERE. A sitar has a gourd, and a second gourd on some, and they
    colour it considerably. FormantBody is the mechanism and there is no
    measurement to put in it, so it is left out rather than invented -- the
    same call as the electric guitars, where the amplifier is the colour.
    """
    # A mizrab is a hard wire plectrum, plucked close to the bridge: a narrow
    # exciter at fixed force, so the comb notch stays deep.
    strike_point = 0.10
    strike_depth = 0.90
    strike_fills_with_force = False

    # THE BUZZ, as spectrum and as envelope. tonal_dampening 0.55 is far
    # shallower than a guitar's 2.0; harmonic_decay_db 0.45 against the plucked
    # base's 1.0 is the part that makes it a jawari rather than a bright pluck.
    tonal_dampening = 0.55
    max_harmonic = 64
    # A SITAR RINGS FOR SECONDS, NOT FOR HALF A MINUTE. The first version had
    # 0.8, which is 32 s to fall 40 dB -- and since Q comes from the decay,
    # that put the modes at Q 12000 and made every sympathetic coupling
    # vanish. 5.0 is 7.3 s and Q 2800, which is still a very sharp resonance
    # and is what a long steel string on a light bridge actually is.
    decay_db = 5.0
    harmonic_decay_db = 0.45
    harmonic_decay_dampening = 0.0
    inharmonicity_coefficient = 3.0e-05     # long steel, estimated

    # THIRTEEN TARAF STRINGS under the frets, tuned to the raga and not
    # touched. Offsets from Sa: an octave below through a ninth above, on the
    # natural scale -- one common tuning, and a player retunes them per raga,
    # so this is a default and not a fact about sitars.
    sympathetic_mode = 'coincidence'
    sympathetic_strings = (-12, -10, -8, -7, -5, -3, -1, 0, 2, 4, 5, 7, 9)
    # SA MUST BE THE TUNING'S TONIC, and this is the tuner's constraint rather
    # than the instrument's. Indian classical tunes the twelve swaras in just
    # intonation against a fixed Sa, and tunelib's JustTuner is exactly that
    # ratio set -- 16/15, 9/8, 6/5, 5/4, 4/3, 45/32, 3/2, 8/5, 5/3, 9/5, 15/8
    # -- but with its tonic nailed to C. Put Sa anywhere else and the taraf are
    # tuned to intervals that are not pure: measured from C# the fourth is
    # 21.5 cents off where from C it is the just 2.0, and the coupling
    # collapses accordingly.
    #
    # A real sitarist puts Sa wherever they like, commonly C# or D, and retunes
    # the taraf to match. Following that would need a tuner whose tonic moves,
    # which this one has not got.
    sympathetic_tonic = 60                  # Sa at C, where JustTuner's is
    # THE NUMBER MOST LIKELY TO BE WRONG HERE, and there is no measurement
    # behind it -- the steelpan is the precedent, where the ratios were right
    # and every asserted GAIN was out by 25 to 30 dB once a recording existed.
    #
    # It is a judgement about balance: the taraf are a halo round the note,
    # clearly there and never a second voice. Measured on the rendered
    # passage, 0.35 put them 5.6 dB under the played string -- which is two
    # instruments -- and this puts them 14.9 under. 0.20 is -10.5 and 0.07 is
    # -19.7, so the knob is roughly linear in dB and easy to move by ear.
    #
    # THEY DO NOT PILE UP, which was the worry worth checking: nothing damps a
    # taraf, and every note adds nine more of them ringing for seven seconds.
    # Measured second by second across the passage the wash sits at a steady
    # -5.7 dB relative to the melody at the old gain rather than climbing, so
    # it reaches a balance instead of accumulating.
    sympathetic_gain = 0.12
    sympathetic_max = 13
    sympathetic_floor = 0.005


class NylonGuitarProperties(FormantBody, PluckedStringProperties):
    """MEASURED: Iowa Guitar.mf, all six strings, 35 notes G2-A#5.

    THE INSTRUMENT IS NYLON, and that was measured, not read off the page --
    Iowa documents nothing about it. Two independent lines agree. The files are
    named in classical `sul` notation, six strings at 19 frets each; and the
    brightness gradient runs the wrong way for steel. Over the six OPEN strings
    (full length, so no fret confound) the h2-h8 energy relative to h1 runs
    E2 +25.2, A2 -3.5, D3 +3.7, G3 +0.4, B3 -6.0, E4 -9.8 dB, with nothing above
    8 kHz anywhere (-46 to -61 dB). The top two strings are the DARKEST on the
    instrument. Plain steel trebles are the brightest strings on a steel-string
    acoustic and its bronze basses put real energy past 8 kHz; dark
    fundamental-dominant trebles over rich wound basses is the classical guitar.

    (The obvious test -- where the wound/plain boundary sits, D->G on a classical
    and G->B on a steel-string -- does NOT work. At a fixed pitch the lower
    string is fretted further up the neck, which dulls it whatever it is wound
    with, and that confound is the same size as the effect.)

    WHAT THIS CLASS ADDS IS A BODY. PluckedStringProperties has none: its
    spectrum is a function of harmonic NUMBER alone, so it produced the same
    ladder at every pitch, varying 1 dB from E2 to E4 --

        E2  +0 -10 -13 -19 -16 -26 -18 -25
        E4  +0 -10 -14 -21 -18 -28 -20 -28

    -- where the real instrument moves enormously across its range, because its
    resonances stay put while the harmonics slide through them. Iowa's open E2
    has h2 and h3 twenty dB ABOVE its fundamental (a box that size cannot
    radiate 82 Hz), and its E4 has h2 thirteen dB below. Pooling every harmonic
    of every note by ABSOLUTE frequency, the model was up to 19.7 dB too quiet
    at 216 Hz and 10 dB too loud above 7 kHz: a missing body and too much top.

    FITTED ON TWO MEASUREMENTS AT ONCE, and it needs both. A harmonic ladder
    alone does not constrain this instrument, because the harmonics run out long
    before the instrument does: on the low E, h32 is still only 2.6 kHz, so
    everything above that was pure extrapolation. The first fit here scored well
    on the ladder and was WRONG -- it rolled the top off so hard that the energy
    above 4 kHz fell 19 dB below the recording. That is audible at once, and it
    was caught BY EAR, not by the metric. So the objective also carries the
    BROADBAND energy above 2, 4 and 8 kHz, measured over 100 ms from the pluck
    on the six open strings, where the integral has the signal-to-noise that the
    individual high harmonics do not.

        vs the Iowa guitar        h1-h32 shape     >2/4/8 kHz energy
          no body (as it was)        15.78 dB          14.17 dB
          ladder-only fit            10.13             17.68     <- worse
          this                       11.38              4.79

    1.25 dB of ladder given up for 12.9 dB of top end, and the >8 kHz error
    comes out at 0.30 dB. Per-note gain is removed throughout, so the shape
    column measures COLOUR and never level.

    The reference had to be rebuilt to see any of this. The noise floor was
    being estimated from the analysis window itself, which on a decaying pluck
    is the signal -- it masked out real harmonics and left ~18 per note. Iowa's
    true floor is -92 to -133 dBFS and its SNR above 8 kHz is +52 to +85 dB, so
    that content is real; measured against it, a median of 32 harmonics per note
    survive.

    THE PLUCK COMB IS PINNED, NOT FITTED, for a related reason. Letting
    plucked_harmonic and pluck_dampening float scored better by driving
    plucked_harmonic past the last fitted harmonic, which DELETES the comb
    rather than fitting it -- and a player working up a chromatic scale moves
    the plucking point from note to note, so pooling AVERAGES the comb away.
    That is a fact about the measurement, not about guitars.

    What is left is per-note plucking variation, which no pitch-independent
    model can follow: an unconstrained 32-bin body fitted straight to the
    recording still leaves 6.27 dB.
    """
    # The two low poles are narrow (Q ~ 15 and 12) and carry the body; the two
    # broad upper ones carry its top. b1 sits on the search's lower bound, so
    # the recording would take a narrower resonance still than this allows.
    formants = ((291.5, 20.0, 0.486), (399.0, 33.3, 0.667),
                (1029.5, 665.5, 0.191), (1982.9, 533.5, 0.114))
    formant_floor = 0.0576
    # FITTED, not carried over: a body doing part of the rolloff means the
    # source must do less of it, exactly as on the violin.
    tonal_dampening = 0.971
    octave_dampening = -0.263
    bore_corner_hz = 3334.7
    bore_order = 1.412
    # The box stops coupling below its air resonance, which is what strips the
    # low E of its fundamental.
    bell_cutoff_hz = 308.9
    bell_order = 0.533
    # Trimmed -0.05 dB so the fit changes COLOUR and not LEVEL -- the
    # equal-velocity balance predates it, and the fit moved this voice's total
    # energy by that much.
    initial_gain = PluckedStringProperties.initial_gain * 0.9947


class ElectricGuitarProperties(PluckedStringProperties):
    """A solid-body electric: two combs, a magnet, and an amplifier.

    patch_map has said for a long time that "26-31 are electrics, whose colour
    is an amplifier's, not a box's", and left them on the bodyless base because
    there was no amplifier to give them. There is one now, so this class is
    the string and the magnet and nothing else -- the colour arrives downstream,
    from tubeamp and from cabinet.py, which is where it comes from on the real
    instrument too.

    WHAT MAKES IT AN ELECTRIC IS THAT THERE ARE TWO COMBS. A string plucked at
    fraction p feeds mode n with |sin(n*pi*p)|; a pickup at fraction q READS
    mode n with |sin(n*pi*q)|. An acoustic guitar has the first and a body; this
    has the first, the second, and an amplifier. The interaction of the two is
    most of what a guitarist means by tone, and it is why moving the picking
    hand two inches changes the sound of a solid-body far more than it changes
    the sound of a classical.

    GEOMETRY, NOT TASTE. The numbers are a Stratocaster's, which is a measurable
    object: 648 mm scale, middle pickup ~100 mm from the bridge (0.154), coil
    ~9 mm wide (0.014). Picking at 0.19 is a rock player's right hand, nearer
    the bridge than a classical player's. The middle pickup is chosen for GM 27
    because it is neither extreme; the neck position (~0.244) is the jazz sound
    and the bridge (~0.063) is the cutting one, and both are this class with one
    number changed.

    THE SERIES IS 1/n, NOT 1/n^2, and both halves of that are physics. A plucked
    string's DISPLACEMENT modes go as 1/n^2. A magnetic pickup's output is
    -dPhi/dt, so it reads VELOCITY: another factor of n. Net 1/n, which is why a
    solid-body is brighter than its unplugged self -- audibly so, and it is the
    magnet doing it, not the wood. Written as tonal_dampening 2.0 plus
    pickup_velocity rather than as a single fitted 1.0, so that the day someone
    changes the pickup the exponent follows.

    NO BODY AND NO SOUNDBOARD, which is the point of a solid body: nothing is
    pulling energy out of the string, so it rings far longer than an acoustic.
    That is also why it can be amplified to the point of feedback, which this
    does not model.
    """

    # A pick is hard, narrow and plucks at whatever force the player uses, so
    # the notch does NOT fill the way a felt hammer's does -- same argument as
    # the harpsichord's quill. Not quite a point, though: a pick flexes.
    strike_point = 0.19
    strike_fills_with_force = False
    strike_depth = 0.85

    # Stratocaster middle pickup: 100 mm from the bridge on a 648 mm scale.
    pickup_points = (0.154,)
    pickup_width = 0.014          # ~9 mm coil, so its sinc null is past h64
    pickup_velocity = True        # -dPhi/dt: the +6 dB/octave is the magnet

    # 1/n^2 from the pluck; pickup_velocity supplies the n that makes it 1/n.
    tonal_dampening = 2.0
    octave_dampening = 0.0        # the magnet does not care what note it is

    # ESTIMATED, NOT MEASURED, and flagged as such. Plain steel trebles and a
    # flexible-core wound bass on a 648 mm scale sit between a harpsichord's
    # thin iron (3.51e-5, measured over 195 notes) and a piano's short thick
    # wire. Partial frequencies are the one thing a recording gives up
    # unconditionally, so this is worth measuring properly if a steel-string
    # reference ever turns up.
    inharmonicity_coefficient = 5.0e-05

    # A clean valve amplifier is not a distortion-free one -- it is one worked
    # gently. This is the "clean" setting, and TUNING_AMP_DRIVE sweeps it.
    amp_drive = 0.6
    # ...and the level it is measured against, so that picking harder breaks up
    # and picking softly does not. See tubeamp.emit; without this the drive is
    # normalised per segment and the dynamics are divided out.
    # MEASURED, by `python3 examples/guitar.py --calibrate`: the peak a
    # six-string strum makes AT VELOCITY 100, in this renderer's units.
    #
    # NOT at 127, and the difference matters. drive 1.0 has to mean "the edge
    # of breakup at NORMAL playing", so that digging in goes PAST it -- which
    # is how an amplifier is actually set: you put your usual touch where you
    # want it and the hard notes exceed it. Calibrated at 127 the nominal
    # drive was only reachable by playing as hard as MIDI can say, and real
    # files never do: Riffsym writes all 727 of its notes at velocity 100, so
    # its distortion guitars sat at 0.620 of nominal for ever. attack_volume
    # is (vel/127)^2, so that is the square and not the ratio -- 4.1 dB.
    amp_reference = 0.1772

    # A CLEAN VALVE AMPLIFIER IS STILL SINGLE-ENDED. Its preamp is one valve
    # with nothing to cancel against, so even at this drive the distortion it
    # makes is second-order first -- which is what "warm" means and what a
    # balanced pair (tubeamp's own default, h2 129 dB down) would not give.
    amp_imbalance = 0.25

    cabinet = "guitar12"

    # LEVEL. This family inherited PluckedStringProperties' generic 0.02 and was
    # never balance-normalised: measured against the grand piano in its own
    # register it came out -20.8 dB, which Ben heard before anything measured it --
    # "I have heard the electric bass as way too quiet". An amplified instrument
    # is not 20 dB under a piano.
    #
    # BOTH NUMBERS MOVE TOGETHER, and they have to. amp_reference is the level
    # amp_drive is measured against, so raising initial_gain alone drives the
    # valve further into breakup and changes the voice: measured, x4 gave +11.2
    # dB and the next x4 only +8.1. Scaled together the level is exactly linear
    # (+12.0, +24.1 dB for x4 and x16) and the brightness does not move at all
    # (-32.9 dB in every case), so the voiced distortion survives untouched.
    #
    # The anchor is the MEASURED nylon guitar at -9.7 dB, which is this family's
    # own level rather than the piano's. Every member shifts by the one factor,
    # so the relationships between them -- a palm mute quieter, a slap brighter
    # -- are exactly as they were.
    # AND THEN +2 dB AGAIN, because the anchor was wrong for this family. The
    # measured nylon guitar is an ACOUSTIC classical guitar, and pinning an
    # amplified instrument to an unamplified one has no physical content: a
    # guitarist sets this level with the amp's volume knob, not with the string.
    # Ben heard the result as "the bass electric guitar is a bit loud relative
    # to the others", and asked the right question back -- whether the guitars
    # should rise instead. They should. Measured, the electric guitar sat 1.8 dB
    # under the electric bass; this closes that and leaves it just above the
    # acoustic nylon, which is where an amplified guitar belongs.
    #
    # The two ACOUSTIC guitars (GM 24, 25) do not move. Their level IS measured,
    # and they are the reference the rest of the plucked family is placed
    # against -- what changed is the recognition that an amplifier sits between
    # that reference and these voices.
    initial_gain = 0.0869

class ElectricBassProperties(ElectricGuitarProperties):
    """A solid-body electric bass: the guitar's physics on a longer string.

    Everything that makes the guitar an electric makes this one too -- two
    combs, a magnet reading VELOCITY, no body -- so this is that class with the
    geometry of a different instrument and a cabinet built for a different job.
    What actually differs:

      SCALE. 864 mm (34") against the guitar's 648. The pickup and pluck
      positions below are fractions of THAT, so the same millimetre distances
      land at different fractions: a Jazz bridge pickup 70 mm from the bridge
      is 0.081 of the length where 70 mm on a guitar would be 0.108.

      THE CABINET. bass410, not guitar12, and the difference is not taste. A
      low E is 41 Hz and its FUNDAMENTAL is the note, so the box has to reach:
      -4.9 dB at 45 Hz where a guitar 12" is -10.4. And its presence peak is
      +1.2 dB where the guitar's is +6.4, because a bass wants definition and
      that peak is what makes a guitar bite.

      THE AMPLIFIER RUNS CLEAN. A bass rig is usually a clean one -- the
      instrument's job is the bottom of the arrangement, and a clipped bass
      loses the fundamental it is there to supply, since distortion moves
      energy UP. So the drive is a quarter of the guitar's.

    STIFFNESS IS LOWER THAN IT LOOKS. A bass string is far thicker than a
    guitar's, which raises inharmonicity, but it is also a third longer and
    built on a flexible core to keep it playable -- and B falls as 1/L^2. The
    two nearly cancel. ESTIMATED, like the guitar's, and worth measuring if a
    reference ever turns up.
    """
    pickup_points = (0.191,)      # Precision-style split coil, 165 mm of 864
    pickup_width = 0.0116         # ~10 mm coil
    strike_point = 0.12           # plucked over the pickup, as a hand does
    strike_depth = 0.55           # a fingertip is broad: a shallow notch
    inharmonicity_coefficient = 2.0e-05
    amp_drive = 0.28
    amp_imbalance = 0.20
    cabinet = "bass410"
    # MEASURED at velocity 100, like the guitar's: a low E with its octave,
    # which is what a bass line normally is. Well under the guitar's 0.0406
    # because that one is six strings at once; a bass calibrated on a six-note
    # voicing would have a reference it never reaches in use, and would then
    # never break up at all.
    amp_reference = 0.2289

    # LEVEL. This family inherited PluckedStringProperties' generic 0.02 and was
    # never balance-normalised: measured against the grand piano in its own
    # register it came out -32.9 dB, which Ben heard before anything measured it --
    # "I have heard the electric bass as way too quiet". An amplified instrument
    # is not 32 dB under a piano.
    #
    # BOTH NUMBERS MOVE TOGETHER, and they have to. amp_reference is the level
    # amp_drive is measured against, so raising initial_gain alone drives the
    # valve further into breakup and changes the voice: measured, x4 gave +11.2
    # dB and the next x4 only +8.1. Scaled together the level is exactly linear
    # (+12.0, +24.1 dB for x4 and x16) and the brightness does not move at all
    # (-32.9 dB in every case), so the voiced distortion survives untouched.
    #
    # The anchor is the MEASURED nylon guitar at -9.7 dB, which is this family's
    # own level rather than the piano's. Every member shifts by the one factor,
    # so the relationships between them -- a palm mute quieter, a slap brighter
    # -- are exactly as they were.
    initial_gain = 0.2790

class FingeredBassProperties(ElectricBassProperties):
    """GM 33. Two fingers alternating over the neck pickup.

    The base voice IS the fingered bass -- this exists so the GM slot names
    itself rather than pointing at a class called "electric bass" and leaving
    the reader to guess which technique it means.
    """


class PickedBassProperties(ElectricBassProperties):
    """GM 34. The same instrument played with a plectrum.

    Two numbers, and both are the right hand rather than the instrument: a pick
    is HARD and NARROW where a fingertip is soft and broad, so its comb notch
    stays deep instead of being filled in by the contact patch; and it is
    played nearer the bridge, which moves the notch up. That is the whole
    difference between the two GM slots, and it is a difference in the player.
    """
    strike_point = 0.09
    strike_depth = 0.90


class FretlessBassProperties(ElectricBassProperties):
    """GM 35. No frets, so the string stops on WOOD.

    The one physical difference, and it is a termination: a fretted note ends
    on a hard metal wire, which reflects the high partials almost perfectly,
    and a fretless note ends on fingerboard timber under a fingertip, which
    does not. A lossy termination is a DECAY, not a filter -- the note starts
    with its harmonics and loses them, which is the "mwah" a fretless has and
    a fretted bass does not, and it is why simply darkening the voice would be
    wrong: that would take the top off the attack, where it really is present.

    So the fundamental rings as long as ever and the upper partials go four
    times faster.

    AND THE SAME ABSENCE MAKES IT THE GLIDING BASS. With no frets there is
    nothing to step on, which is why the slides are the sound of the
    instrument and why the reach is a long one: a bass neck is long, and
    players use it.
    """
    glide_mechanism = 'stop'
    glide_reach_semitones = 12.0
    harmonic_decay_db = 4.0       # vs 1.0: the top goes, the fundamental stays
    strike_depth = 0.45           # played with more flesh, as fretless is


class SlapBassProperties(ElectricBassProperties):
    """GM 36. The thumb struck against the string, over the fingerboard.

    WHAT MAKES A SLAP BRIGHT IS A COLLISION. The thumb drives the string down
    onto the frets and it rattles back off them; the pop -- the finger pulling
    a string up and releasing it -- does the same thing harder. Each of those
    contacts is very nearly an impulse, and an impulse is broadband, which is
    where a slapped bass gets a top end that no amount of plucking produces.

    HONESTLY, THIS APPROXIMATES THAT RATHER THAN MODELLING IT. A string
    colliding with a fret is a moving boundary condition and this engine has no
    way to say that. What it can say is the consequence: a hard, narrow, near
    point-source excitation, which is `strike_depth` 1.0 at a small
    `strike_point` -- a comb whose first null is past the 16th harmonic instead
    of at the 8th. That gets the brightness and the attack. It does not get the
    rattle, which is a separate sound and would want noisegen.

    The drive is up as well, because a slapped bass is the one case where a
    bass player does push the front end.
    """
    strike_point = 0.06
    strike_depth = 1.00
    pickup_points = (0.081,)      # Jazz bridge pickup, 70 mm of 864
    # 7.5 kOhm against the Precision split coil's ~5.25 per half. A Jazz bridge
    # pickup is wound hot for the same reason every bridge pickup is: it sits
    # where the string barely moves. Same correction as the guitars'.
    pickup_turns = 1.43
    # A SLAP IS HARDER THAN A PLUCK, and the model had no way to say so. Every
    # other difference here is spectral -- the comb, the pickup, the drive --
    # and all of them together still left this voice 4 dB UNDER the fingered
    # bass, which inverts the one thing everybody knows about slap bass. The
    # missing quantity is momentum: a fingertip pluck is a finger flexing and
    # a thumb slap is the forearm rotating, and the moving mass is not close.
    # A factor of two in amplitude is a conservative reading of that, and it
    # is why a bass rig has a compressor on it.
    _thumb = 2.0
    initial_gain = 0.2790 * _thumb
    amp_reference = 0.2289 * 1.43 * _thumb
    amp_drive = 1.45
    amp_imbalance = 0.35


class PoppedBassProperties(SlapBassProperties):
    """GM 37. Slap Bass 2 -- the same technique, leaning on the pop.

    GM does not define what separates its two slap basses and no instrument
    does either, so this is a CONVENTION and is marked as one: 2 is taken as
    the more aggressive of the pair. A pop pulls the string further before it
    releases, so it hits the frets harder and drives the amplifier harder.
    Nothing here is a measurement.
    """
    # ...and it costs level to take it, because the extra drive compresses.
    # Measured, the harder setting alone put GM 37 1.5 dB UNDER GM 36, which
    # is backwards for the more aggressive of the pair. A pop pulls the string
    # further before it lets go, so it arrives with more of everything.
    _pop = 1.25
    initial_gain = 0.2790 * 2.0 * _pop
    amp_reference = 0.2289 * 1.43 * 2.0 * _pop
    amp_drive = 3.41
    amp_imbalance = 0.45


class AcousticBassProperties(FormantBody, PluckedStringProperties):
    """GM 32. The upright, plucked -- the jazz walking bass. It fell through to
    the generic plucked string, which is not a FormantBody and whose zero bore
    corner makes `harmonic_volume` return before any body is applied: no
    instrument at all, only a string.

    AND THE INSTRUMENT IS ALREADY MEASURED, one bank away. GM 43 Contrabass is
    fitted against the Iowa double bass across three registers, and GM 32 is THE
    SAME INSTRUMENT -- the difference is arco against pizzicato, an excitation
    and not a body. So the measured body is copied here verbatim: the 93 Hz
    air resonance at 0.9, the 1750 Hz bridge region, the 5.5 kHz corner and the
    135 Hz bell cutoff are the contrabass's numbers, unchanged.

    COPIED, NOT INHERITED, and that is the whole reason this class is shaped the
    way it is. ContrabassProperties is a BowedStringProperties: bowed means
    driven, which is why it carries decay_db = 0 and harmonic_decay_db = 0 and
    sustains as long as the bow moves. Subclassing it to get the body would mean
    claiming a plucked instrument is a driven one, so this takes
    PluckedStringProperties as its base -- the physical claim -- and FormantBody
    beside it for the resonances, exactly as NylonGuitarProperties does.

    THE PLUCK POINT IS THE OTHER HALF, and it is derivable. A guitar is plucked
    around a seventh of the way along, so its comb first nulls at the 7th
    partial. An upright is plucked at the END OF THE FINGERBOARD, some 25-30 cm
    from the bridge on a ~105 cm string -- a quarter of the way, so the comb
    nulls at the FOURTH. That is most of why pizzicato is dark and
    fundamental-heavy where a guitar is bright: the notch sits low enough to
    take out a partial the ear is still counting.

    AND THE TOP DIES FAST. A thick gut or steel string on a big soft top loses
    its high partials in a moment, which is the thump; the fundamental stays for
    a second or two under it. That is harmonic_decay_db doing the work, not the
    body.

    NO REFERENCE FOR THE PLUCK. The Iowa bass is bowed, so the body below is
    measured and everything about the excitation is derived or asserted: the
    pluck point from where a player's hand goes, the decay rates by ear against
    what a walking bass does. The instrument is right; the gesture is argued.
    """

    # THE CONTRABASS'S MEASURED BODY, copied verbatim. If that fit is ever
    # revised these should move with it -- they are the same instrument.
    formants = ContrabassProperties.formants
    formant_floor = ContrabassProperties.formant_floor
    bore_corner_hz = ContrabassProperties.bore_corner_hz
    bore_order = ContrabassProperties.bore_order
    bell_cutoff_hz = ContrabassProperties.bell_cutoff_hz
    bell_order = ContrabassProperties.bell_order

    # PLUCKED AT THE END OF THE FINGERBOARD, a quarter of the way from the
    # bridge on a ~105 cm string, so the comb nulls at the 4th partial where a
    # guitar's nulls at the 7th. That low notch is most of why pizzicato is dark
    # and fundamental-heavy.
    #
    # strike_point, NOT plucked_harmonic. The latter is the legacy path and is
    # not a pluck POSITION at all: it builds divisor entries for 1..P-1 and sums
    # the ones that do not divide the harmonic, so plucked_harmonic = 4 zeroes
    # every 6th partial and notches the evens -- which is what it did here
    # before this was measured. strike_point is the physical comb the class
    # documents, |sin(n*pi*p)|.
    strike_point = 0.25
    strike_depth = 0.75             # a finger is wide, so the notch is not total
    strike_fills_with_force = False # and it releases rather than compressing

    # The thump: high partials go in a moment, the fundamental stays under them.
    decay_db = 1.2
    harmonic_decay_db = 2.6

    max_harmonic = 40               # as the contrabass has; the body is spent
    tonal_dampening = 1.35          # a soft, wide finger, not a plectrum

    # Balance-normalised against the grand piano on E1/A1/E2 at velocity 100.
    # Exactly 20.0 dB per decade of this knob -- pure linear, unlike the piano's
    # 38.8, whose phantom partials are sum-tones scaling as its square. This
    # voice has none.
    # Re-anchored from the grand piano to this family's own measured level --
    # the nylon guitar's -9.7 dB. Against the piano it read -0.0, which put it
    # 10 dB over every other plucked voice and 16 over its own bowed twin.
    # -3 dB from that, measured. The re-anchor above was done with an
    # arithmetic estimate that put this voice at -10.0; rendered it is -6.4,
    # which made an UNAMPLIFIED upright the loudest thing in the family --
    # louder than the amplified electric bass beside it and 4.5 dB over its own
    # measured bowed twin. A pizzicato attack is brighter and punchier than a
    # bowed one, not louder than an amplifier. This puts it at -9.4, with the
    # electric bass and the electric guitar.
    initial_gain = 0.1900


class SteelGuitarProperties(NylonGuitarProperties):
    """GM 25. The steel-string flat-top, which fell through to the generic
    plucked string -- a voice that is not a FormantBody at all and whose
    `bore_corner_hz` is 0, so `harmonic_volume` returns before any body is
    applied. NO GUITAR BODY WHATSOEVER: it rendered as a bare string in free
    air, next door to the one voice in the family that has a measured one.

    So it inherits that body. The Iowa classical is a close relative -- flat top,
    soundhole, the same construction principle -- and a measured body of the
    wrong size beats no body by a wide margin. What changes is the STRING, the
    pluck and how much top the box passes, and the brief for that is written in
    NylonGuitarProperties from its own measurement:

        "Plain steel trebles are the brightest strings on a steel-string
        acoustic and its bronze basses put real energy past 8 kHz; dark
        fundamental-dominant trebles over rich wound basses is the classical
        guitar."

    -- the nylon having measured NOTHING above 8 kHz anywhere, -46 to -61 dB.
    That is the target and it is somebody else's measurement of the instrument
    this voice is not, which is the best available here.

    THE OBVIOUS DERIVATION IS A DEAD END, and it is worth recording so nobody
    repeats it. Steel's Young's modulus is some fifty times nylon's, so a steel
    string ought to be far more inharmonic. But B goes as Q*d^2/rho at a given
    pitch and scale, and a steel string for the same note is LESS THAN HALF THE
    DIAMETER -- d enters squared, and the two effects very nearly cancel:

        steel .012 high E   Q 200 GPa  d 0.305 mm   ->  2.37
        nylon .028 high E   Q   4 GPa  d 0.711 mm   ->  1.76

    **35%, not 50x.** So inharmonicity is the SMALLEST of the differences here,
    not the defining one, and it is set to exactly that ratio rather than to
    something dramatic.

    WHAT ACTUALLY SEPARATES THEM IS DAMPING. Nylon is viscoelastic and eats its
    own high partials; steel's internal losses are negligible. That is why a
    classical is warm and short where a steel-string jangles and rings, and it
    is a DECAY difference rather than a spectral one -- harmonic_decay_db, not
    inharmonicity.

    NO REFERENCE. There is no steel-string in the set; the numbers below are
    aimed at the nylon's measured description of one, which is not the same
    thing as measuring one. The body is the classical's, unshifted: a
    dreadnought is bigger and its air resonance sits lower, but by how much is
    not derivable here and those formants were fitted jointly with the rest of
    the nylon. Moving them would be guessing at somebody else's fit.
    """

    # Steel's low internal loss: the high partials survive where nylon's die.
    # The largest of the differences, and the reason the instrument rings.
    harmonic_decay_db = 0.55

    # A pick is hard and narrow where flesh and nail are soft and wide, so the
    # source ladder tilts less steeply. The pluck POINT is unchanged -- both
    # instruments are played over much the same part of the string -- so
    # plucked_harmonic stays where the measurement put it.
    tonal_dampening = 0.75

    # A thin, stiff, X-braced spruce top driven through a pin bridge radiates
    # higher than a fan-braced classical's. DIRECTION defensible, number not:
    # it is set where the >8 kHz band stops being empty.
    bore_corner_hz = 7000.0

    # x1.35 exactly, from Q*d^2/rho above. Real, and the least of it.
    inharmonicity_coefficient = NylonGuitarProperties.inharmonicity_coefficient * 1.35


class JazzGuitarProperties(ElectricGuitarProperties):
    """GM 26. A neck humbucker, picked with the thumb side of the hand.

    The dark sound of a jazz box is NOT the box. A pickup senses the string,
    not the air, so even on a hollow instrument almost nothing of the body
    reaches the amplifier -- which is why an archtop played unplugged and
    plugged in are two different instruments. What makes this dark is
    geometry, and all of it is in the pickup:

      - the NECK position, 0.244 of the length, nulls harmonics 4, 8, 12 --
        the whole upper-mid ladder, at once;
      - two COILS 18 mm apart cancel wherever they fall antiphase, which adds
        a second null at n = 1/0.0278 = 36;
      - and picking at 0.25 rather than 0.19 puts the pluck comb's own null
        down at the 4th as well, instead of the 5th.

    Three nulls converging on the 4th harmonic is the sound.
    """
    pickup_points = (0.230, 0.258)      # neck humbucker, 18 mm coil spacing
    # A '57 Classic: 8.0 kOhm for the pair, so 4.0 per coil against a Strat
    # coil's 5.8. Each coil is SMALLER, and the pickup is still hotter overall
    # because the two are in series -- net +2.8 dB, not the +6 the sum alone
    # would give. That is the whole difference between a vintage humbucker and
    # a hot one, and GM 30 is the other end of it.
    pickup_turns = 0.69
    # ...AND THEN TURNED DOWN, which is the other half of how this sound is
    # made. A hot neck humbucker really does read several dB above a middle
    # single coil, and with that modelled this patch came out the LOUDEST in
    # the plucked family, 6 dB over a nylon guitar -- which no jazz guitarist
    # has ever been. The instrument has a volume control and the amplifier has
    # another, and setting them is the first thing a player does. So the
    # pickup keeps its honest output and the patch is set to sit just above
    # the clean guitar, warm rather than loud. Both numbers scale together,
    # so the valve sees exactly what it saw and only the level moves.
    _knob = 0.66
    initial_gain = 0.0869 * _knob
    amp_reference = 0.1772 * 1.38 * _knob   # the pair reads 1.38x a single coil
    strike_point = 0.25                 # picked toward the neck, softly
    strike_depth = 0.7                  # a thumb or a soft pick is not a point
    amp_drive = 0.34
    amp_imbalance = 0.35


class MutedGuitarProperties(ElectricGuitarProperties):
    """GM 28. The picking hand's palm resting on the strings at the bridge.

    A palm mute is a DAMPER, and damping is a decay rate, not a filter. The
    heel of the hand loads the string where it crosses the bridge and takes the
    energy out fast -- fastest from the modes that move most under it, which is
    the high ones. So this is the base voice with its decay opened up by an
    order of magnitude: h1 falls at 38 dB/s where an open string falls at 1,
    and h8 at 94.

    What it is NOT is a low-pass. The attack is undamped -- the palm cannot act
    before the pick does -- so a palm mute starts as bright as an open note and
    then loses its top in a fraction of a second. That ORDER is the sound, and
    a voice that simply rolled the treble off would get the chug and lose the
    click.
    """
    pickup_points = (0.10,)             # near the bridge, where the hand is
    pickup_turns = 1.07                 # a bridge coil is wound hotter: 6.2k
    amp_reference = 0.1772 * 1.07
    strike_point = 0.10
    decay_db = 30.0                     # dB/s on the fundamental
    harmonic_decay_db = 8.0             # ...and far faster up the series
    amp_drive = 1.98
    amp_imbalance = 0.50


class OverdrivenGuitarProperties(ElectricGuitarProperties):
    """GM 29. The same instrument with the amplifier worked.

    Only two numbers differ from the clean voice, and neither is a filter: the
    drive, and the balance of the stage. A guitar amplifier's gain stages are
    SINGLE-ENDED -- one valve, no partner to cancel against -- so they are
    even-order dominant, and that is most of why an overdriven guitar sounds
    warm where a balanced push-pull pair sounds like a square wave. Measured at
    drive 2.0, a balanced stage puts h2 129 dB down and a single-ended one puts
    it 15.8 down, ABOVE its own third.

    Bridge pickup, because that is what the position is for.
    """
    pickup_points = (0.10,)
    pickup_turns = 1.07                 # a bridge coil is wound hotter: 6.2k
    amp_reference = 0.1772 * 1.07
    amp_drive = 4.45
    amp_imbalance = 0.60


class DistortionGuitarProperties(ElectricGuitarProperties):
    """GM 30. Past the bend and into the clip.

    Drive 3.0 is well past the grid bias -- the slope of the stage is 0.43 at
    2 and 0.07 at 4 -- so this is the setting the old power-series amplifier
    could not reach at all, because 1.0 was its radius of convergence rather
    than the amplifier's limit.

    A bridge HUMBUCKER, which is the pairing this patch means: hot enough to
    push the front end, and its own 36th-harmonic null keeps the very top from
    turning to hash before the speaker gets to it.
    """
    pickup_points = (0.049, 0.077)      # bridge humbucker
    # "Hot enough to push the front end" is a NUMBER, and the docstring above
    # has been claiming it without the model being able to say it. A Duncan
    # Distortion is 16.6 kOhm, 8.3 per coil against a Strat coil's 5.8, and
    # two of those in series read 2.86x a middle single coil. That is why
    # people fit one. Against the geometry alone this pickup came out the
    # QUIETEST on the instrument, 7.7 dB under the clean voice, which is how
    # GM 30 ended up below GM 29.
    pickup_turns = 1.43
    amp_reference = 0.1772 * 2.86
    strike_point = 0.13
    amp_drive = 14.43
    amp_imbalance = 0.80


class GuitarHarmonicsProperties(ElectricGuitarProperties):
    """GM 31. A finger resting on a node, so most of the string cannot speak.

    Touch a string at half its length and every odd mode -- which has an
    ANTINODE there -- is killed, while the even ones, which have a node, are
    untouched. The string goes on sounding at twice its open pitch with only
    the modes that fit, and the result is the glassy, almost sine-like tone a
    guitarist gets at the twelfth fret.

    So this is not a filter and not a comb: harmonic_touch DELETES modes. The
    mth partial you hear is string mode 2m, which is also where the pluck comb
    and the pickup comb have to be read -- the combs stretch with it. Measured
    against the open voice, h3 falls from +1 dB to -26.

    It rings, too, because the finger is at a node and a node is not moving:
    the touch selects rather than damps. Decay is left at the base voice's.
    """
    harmonic_touch = 2                  # touched at 1/2: the twelfth fret
    strike_point = 0.13                 # struck near the bridge, as one does
    amp_drive = 0.45


# --- Percussion (channel 10): broad noise/membrane/metal buckets ---
# The additive engine has no white-noise source, so "noise" is approximated
# by a dense stack of strongly inharmonic partials whose stretched
# frequencies decorrelate into colored noise. Each drum is struck at a
# fixed base frequency from the percussion map, not a tuned pitch.

class PercussionProperties(PluckedStringProperties):
    """Base drum voice: struck onset, no chiff jitter, fast decay."""
    # A GATED one-shot stops here, in seconds from the strike, instead of
    # ringing out: see GatedSnareProperties. None is every other struck voice.
    gate_time = None

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




class OrchestraHitProperties(PercussionProperties):
    """GM 55. Not an instrument: the whole orchestra hitting one chord at once.

    It had been falling through to BowedStringProperties -- a SUSTAINED bowed
    note, which is the one thing a hit is not. Its four notes in the Ride of the
    Valkyries rendered as a dull 245 Hz chord carrying six harmonics, where the
    score wants a stab.

    NOTHING IN IT IS PLUCKED, and no single spectrum describes it. A pluck is a
    string released from a triangular displacement, leaving a comb set by where
    the plectrum sat; a hit is an impulsive excitation of every body in the room.
    So the base is the struck one the drums and cymbals share -- which is why
    plucked_harmonic arrives here as 0, and it should.

    And it is a REGISTRATION, not a voice. A hit is scored as everybody playing
    one pitch in octaves, ff, short: basses and tuba at the bottom, trombones and
    cellos above them, the strings and horns at the written pitch, trumpets and
    winds an octave up. That is a stop list -- a rank is a voice class at a
    transposition -- so it is built as one, out of the instrument classes this
    file has already calibrated, rather than by fitting one spectrum to stand in
    for fifteen. Each rank borrows only its own class's SPECTRUM; the envelope,
    the decay and the inharmonicity stay this class's, which is correct because
    the players are struck at one instant and stop together.

    Two things the registration cannot supply, and they are what keep the result
    from sounding like a chord rather than a blow:

      PITCH SPREAD. Sixty players do not agree on the note. That is the unison
      machinery taken in the RATIO slot (cents, as a piano's strings are) rather
      than the fixed-Hz slot one instrument's own strings use -- a section's
      disagreement scales with pitch, one string's beating does not.

      ONSET SCATTER. They do not agree on the INSTANT either, which is what stops
      a hit sounding like one synthetic click. strike_phase_spread is already the
      mechanism for exactly that, from the hi-hat.

    FITTED against a reference built from this file's own voices: thirteen
    already-calibrated orchestral parts playing one ff chord in octaves. There is
    no Iowa recording of an orchestra hit, and the orchestra we already model is
    the only self-consistent standard for the orchestra-in-one-note.
    """
    registerable = True
    default_stops = 0b1111111    # all seven: a hit is the whole band at once
    # The scoring, as a stop list: (name, footage, gain, whose spectrum).
    # Bits 0-6 of the CC11 stop word, so a default expression of 127 draws the
    # whole band -- which is the only registration a hit is ever played in.
    stop_ranks = [
        ("bass",    0.25, 1.593, ConicalBrassProperties),   # basses, tuba: 2 octaves down
        ("tenor",   0.5,  1.180, TromboneProperties),       # trombones, cellos
        ("horn",    1.0,  0.538, HornProperties),           # horns at the written pitch
        ("string",  1.0,  0.673, BowedStringProperties),    # the strings, marcato
        ("tpt",     2.0,  0.430, TrumpetProperties),        # trumpets an octave up
        ("wind",    2.0,  0.338, StoppedPipeProperties),    # flutes and oboes with them
        ("picc",    4.0,  0.348, StoppedPipeProperties),    # piccolo on the top octave
    ]
    crescendo_order = ["string", "bass", "tenor", "horn", "tpt", "wind", "picc"]

    # The chairs, in cents either side of the nominal. Wider than a string
    # section's 6-8 because this is a section of sections: the winds and the
    # brass are tuning to each other as well as to the strings.
    section_cents = (-11.0, -4.5, 4.5, 11.0)
    unison_gain = 0.62

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        return [(self.unison_gain, 0.0, 2.0 ** (c / 1200.0) - 1.0, harmonic_decay, 0.0)
                for c in self.section_cents]

    strike_phase_spread = 0.8   # the players' onsets, smeared
    attack_time = 0.010

    # one_shot, as the struck voices are: a hit is a fixed-length EVENT. Holding
    # the key longer does not hold the orchestra's chord any longer.
    one_shot = True
    release_floor_db = -40.0

    max_harmonic = 32           # per rank, and there are seven of them
    decay_db = 12.0             # fitted to the reference envelope; see the note below
    harmonic_decay_db = 2.0
    # ONE decay law cannot hold both ends of this envelope, because the thing
    # being matched is a SUM: the strings and brass stop when the players stop,
    # while the bass drum and the cymbal ring on underneath them. Fitting the
    # initial drop (-10 dB at 0.17 s) leaves a 1.5 s tail no hit has; fitting the
    # tail costs the attack. This is the compromise, and the honest fix is the
    # two-component aftersound the cymbals already carry, which bends an envelope
    # without tilting the spectrum -- it lives on CymbalProperties, not here.
    harmonic_decay_dampening = 0.0
    tonal_dampening = 0.0

    chiff_volume = 0.35   # the cymbal and the bass drum in the attack
    chiff_cycle = 0.20
    chiff_release = 0.5
    chiff_width = 0.02
    chiff_bandwidth = 6.0   # broad: this noise is not one instrument's

    initial_gain = 1.0 / 50

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
    # THE MODES OF A CIRCULAR MEMBRANE ARE THE BESSEL ZEROS. This is the one
    # body in the file whose mode set needs no recording: it is analytic, and it
    # is the ratio of j(m,n) to j(0,1) for a clamped circular head --
    #
    #   (0,1) 1.000  (1,1) 1.593  (2,1) 2.136  (0,2) 2.295  (3,1) 2.653
    #   (1,2) 2.917  (4,1) 3.155  (2,2) 3.500  (0,3) 3.599  (5,1) 3.647
    #
    # -- and this class had been building a mildly stretched HARMONIC series
    # instead: 1.000 2.031 3.124 4.310 5.620 7.085. Its own docstring already
    # said "a free circular membrane's modes are 1 : 1.59 : 2.14 : 2.30 : 2.65
    # -- no musical relationship at all, which is why a tom has no definite
    # pitch" (see TimpaniProperties, which places its kettle-loaded modes
    # explicitly for exactly this reason). The engine simply had no way to
    # express it until mode_ratios existed.
    #
    # It matters more here than almost anywhere: a harmonic series HAS a pitch.
    # Modelling a tom as one is modelling the single thing that distinguishes a
    # drum from a note.
    #
    # THE RATIOS ARE PHYSICS; THE GAINS ARE JUDGEMENT. There is no drum kit in
    # the Iowa collection -- no snare, no bass drum, no toms -- so unlike the
    # guiro nothing here is fitted to a recording. The amplitudes fall as
    # 1/ratio**1.6, which reproduces the roll-off this class already had through
    # tonal_dampening (mode_gains bypasses that path). Same footing as the
    # ocarina and the blown bottle, and labelled the same way.
    mode_ratios = (1.000, 1.593, 2.136, 2.295, 2.653, 2.917,
                   3.155, 3.500, 3.599, 3.647, 4.059, 4.132)
    mode_gains  = (1.000, 0.475, 0.297, 0.265, 0.210, 0.180,
                   0.159, 0.135, 0.129, 0.126, 0.106, 0.103)
    max_harmonic = 12
    # the mode set is absolute; there is no series left to stretch
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    tonal_dampening = 1.6
    decay_db = 34.0            # tom ring ~0.85 s to -30 dB
    # 36, not the 6 this was set to, because harmonic_decay now scales by mode
    # RATIO and not by mode index (see SynthProperties.harmonic_decay). A drum's
    # twelve Bessel modes span ratios 1.00-4.13, not indices 1-12, so the same
    # number spread the decay three times less far and left the toms up to 11 dB
    # bright in 0.5-1.5 kHz. Solved to hold the previous sound: band drift 5.98
    # -> 1.02 dB, with the -10/-20/-40 dB times unmoved. It cannot go to zero --
    # the correction compresses the range rather than scaling it -- and the
    # membranes were never fitted to a recording, so holding what has been heard
    # is the most this can honestly claim.
    harmonic_decay_db = 36.0
    harmonic_decay_dampening = 0.2


# ------------------------------------------- the hand drums of the GM kit
# Notes 60-66 and 86-87 were ONE MembraneDrumProperties -- nine notes, four
# instruments. They share a circular head and its Bessel modes, and they share
# very little else: what separates a bongo from a surdo is not the tuning, it is
# the SHELL, and what separates a timbale from a conga is what the shell is made
# of.
#
# The map already varies the ring time per note (PERCUSSION_RING), so the
# mute/open pairs -- 62 against 63, 86 against 87 -- were already distinguished
# in the one way a damping hand shows up most. What was missing is the body.


class ShelledDrumProperties(MembraneDrumProperties):
    """A drumhead over a shell that RADIATES ON ITS OWN, not a filtered head.

    The first version of this class made the shell a formant, and that was
    wrong in a way worth recording. A formant can only shape partials that
    already exist, and measured against the head's twelve Bessel modes the
    shells did not overlap them at all: a conga's cavity resonates near 150 Hz
    and a surdo's near 58, both BELOW the lowest mode, while a timbale's metal
    shell rings above 1250 and the highest mode reaches 1116. Three of the four
    shells had nothing to filter, and the four drums came out within 4 dB of
    each other.

    A shell is a SEPARATE SOURCE. The strike drives the head, and the head and
    the stick together drive the air in the shell and the shell itself; those
    radiate at their own frequencies whether or not a head mode happens to sit
    near one. That is why a conga sounds as though the note comes from below
    the head rather than from it.

    So the shell is emitted as extra partials at ABSOLUTE frequencies -- the
    mechanism the bagpipe's drones use, where unison_voices is handed the note's
    own frequency and returns shell_hz/frequency so the result does not track
    it. A drum's shell does not retune when the head is tightened.

    ASSERTED, NOT MEASURED. Iowa's percussion pages have no bongos, congas,
    timbales or surdos.
    """
    shell_hz = ()               # absolute, in Hz
    shell_gain = ()
    shell_decay_db = 30.0       # how fast the shell lets go of it

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        # Only under the head's FUNDAMENTAL: a shell is one resonance, not a
        # copy of the whole mode set, so it must not be re-emitted per mode.
        if harmonic != 1 or not self.shell_hz:
            return []
        f = float(frequency)
        if f <= 0.0:
            return []
        return [(g, 0.0, hz / f - 1.0, self.shell_decay_db, 0.0)
                for hz, g in zip(self.shell_hz, self.shell_gain)]


class BongoProperties(ShelledDrumProperties):
    """Notes 60, 61. Small, very tight, struck with the fingers.

    A bongo is the tightest head in the kit and the shortest shell -- a few
    inches of wood, open at the bottom, far too small and far too open to
    resonate at any pitch that matters. It is the one drum here whose shell does
    almost nothing, and what you hear is the head alone: high, dry, gone at once.

    FINGERS, NOT A STICK, which is the other half. A fingertip is wide and soft
    where a stick is narrow and hard, so the highest modes are never excited --
    a bongo is bright because it is SMALL, not because it is struck sharply.
    """
    shell_hz = (900.0,)         # a token cavity, and deliberately weak
    shell_gain = (0.10,)
    shell_decay_db = 55.0
    tonal_dampening = 1.85      # a fingertip, not a tip
    max_harmonic = 10


class CongaProperties(ShelledDrumProperties):
    """Notes 62, 63, 64. A tall wooden shell with a real column of air in it.

    The drum whose shell matters most: two or three feet of staved wood, narrow
    at the bottom, with a strong low resonance well under the head's own
    fundamental. It is why a conga has BODY under the slap, and why it seems to
    speak from below the head.

    62 is the MUTED hi conga and 63 the open one; percussion_map gives them
    their own ring times, which is what a hand laid on the head actually does.
    """
    shell_hz = (128.0, 395.0)   # the air column, and the first shell mode
    shell_gain = (0.55, 0.16)
    shell_decay_db = 26.0       # wood lets go fairly quickly
    tonal_dampening = 1.55
    max_harmonic = 12


class TimbaleProperties(ShelledDrumProperties):
    """Notes 65, 66. A METAL shell, one head, and sticks.

    Everything else in this group is wood struck with a hand, and the three
    differences all point the same way:

      the SHELL RINGS. Wood damps and metal does not, so a timbale carries a
      bright shell tone well above the head's own modes and holds it far longer
      than the head holds anything. It is what makes the instrument cut.

      NO BOTTOM HEAD and no enclosed air, so there is no low cavity resonance
      to put weight underneath -- the opposite of the conga.

      STICKS, so the high modes are driven hard where a hand would not reach.
    """
    shell_hz = (1280.0, 2350.0, 3900.0)     # steel, and it sings
    shell_gain = (0.42, 0.26, 0.14)
    shell_decay_db = 9.0                    # metal: the longest ring here
    tonal_dampening = 0.95                  # sticks: the brightest of the four
    max_harmonic = 14


class SurdoProperties(ShelledDrumProperties):
    """Notes 86, 87. The biggest drum in a bateria, and a padded beater.

    Two feet across, slack, carried on a strap. The shell is large enough that
    its air resonance sits under even this head's low fundamental, which is why
    a surdo is felt as much as heard.

    86 is MUTED and 87 OPEN: a hand laid flat on the head straight after the
    beater leaves it. percussion_map already rings 86 for 0.25 s against 87's
    0.90, which is the whole of that gesture.
    """
    shell_hz = (52.0, 168.0)
    shell_gain = (0.70, 0.22)
    shell_decay_db = 18.0
    tonal_dampening = 2.10      # a padded beater takes the top off
    max_harmonic = 10


class TomTomProperties(MembraneDrumProperties):
    """A tom: TWO heads over a closed shell, which the bare Bessel set is not.

    MembraneDrumProperties carries the modes of a circular membrane IN VACUO --
    1 : 1.593 : 2.136 : ... -- and that is the textbook idealisation of a head
    with no air on either side. A conga or a timbale is close to it, because the
    shell is open at the bottom and there is no cavity to speak of. A tom is not:
    it has a second head, and the air trapped between them couples the two.

    ONLY THE MODES THAT CHANGE THE ENCLOSED VOLUME FEEL THAT SPRING, and for a
    circular membrane that is exactly the axisymmetric (0,n) family. Any mode
    with a nodal diameter has equal and opposite lobes whose volume displacement
    cancels, so (1,1), (2,1), (3,1) and the rest do not compress the air and do
    not move at all. Each (0,n) mode instead becomes a DOUBLET: the heads moving
    in the same spatial direction leave the volume alone and stay put, while the
    heads moving oppositely compress the air and rise to f*sqrt(1+k).

    Treating the mode as a piston of effective area 2*pi*a^2*J1(j0n)/j0n against
    an adiabatic volume pi*a^2*L, with modal mass sigma*pi*a^2*J1(j0n)^2:

        k_n = 8*rho*c^2 / (L * sigma * omega_n^2 * j0n^2)

    and since omega_n scales as j0n, k falls as 1/j0n^4 -- so the fundamental
    splits hugely and (0,2) and (0,3) barely at all. For a 12x8 rack tom at
    130 Hz with a 7.5 mil head (sigma 0.26 kg/m^2): the (0,1) partner lands at
    2.556, (0,2) at 2.513 and (0,3) at 3.658.

    CROSS-CHECK, because there is no drum recording anywhere in this collection
    to fit against. The same formula applied to a kettledrum says its (0,1) mode
    is pushed far up and radiates strongly -- which is precisely why a timpano's
    pitch comes from (1,1) to (5,1) and never from its fundamental, as
    TimpaniProperties already describes. That account falls out of this rather
    than being put into it.

    STILL PHYSICS, NOT MEASUREMENT, and on the same footing as the Bessel zeros
    it extends: the ratios are derived, the geometry is stated, and nothing here
    has been checked against a tom. Two effects are knowingly left out. Air MASS
    loading lowers every mode, the low ones most, which would compress the whole
    set slightly. And the air modes are the only ones that move net air, so they
    radiate efficiently and should decay faster than their neighbours -- the
    engine's decay is a function of frequency alone, so it cannot single them
    out. A real shell is also vented, which relieves the spring below the vent's
    own resonance; this is the sealed-cavity limit.
    """
    mode_ratios = (1.000, 1.593, 2.136, 2.295, 2.513, 2.556, 2.653, 2.917,
                   3.155, 3.500, 3.599, 3.647, 3.658, 4.059, 4.132)
    mode_gains  = (1.000, 0.475, 0.297, 0.265, 0.229, 0.223, 0.210, 0.180,
                   0.159, 0.135, 0.129, 0.126, 0.126, 0.106, 0.103)
    max_harmonic = 15
    # the three air partners add a little energy; trimmed back so the family
    # sits exactly where it did before this class existed
    initial_gain = (1.0 / 2.5) * 0.9772


class FloorTomProperties(TomTomProperties):
    """GM 41 and 43: a 16x16 floor tom at 87 Hz. Deeper shell and a lower head,
    which pull k in opposite directions -- more depth is a softer air spring,
    a lower fundamental a weaker membrane one -- and the fundamental wins, so a
    floor tom's air partner sits HIGHER than a rack tom's, at 2.679."""
    mode_ratios = (1.000, 1.593, 2.136, 2.295, 2.538, 2.653, 2.679, 2.917,
                   3.155, 3.500, 3.599, 3.647, 3.665, 4.059, 4.132)
    mode_gains  = (1.000, 0.475, 0.297, 0.265, 0.225, 0.210, 0.207, 0.180,
                   0.159, 0.135, 0.129, 0.126, 0.125, 0.106, 0.103)


class HighTomProperties(TomTomProperties):
    """GM 48 and 50: a 10x7 rack tom at 165 Hz. The tightest head in the family
    and the shallowest shell, and here the head wins: the air partner is the
    lowest of the three at 2.219, close enough to (0,2) at 2.295 to beat with
    it, which is the small tom's characteristic tightness."""
    mode_ratios = (1.000, 1.593, 2.136, 2.219, 2.295, 2.452, 2.653, 2.917,
                   3.155, 3.500, 3.599, 3.641, 3.647, 4.059, 4.132)
    mode_gains  = (1.000, 0.475, 0.297, 0.279, 0.265, 0.238, 0.210, 0.180,
                   0.159, 0.135, 0.129, 0.126, 0.126, 0.106, 0.103)


class KickDrumProperties(MembraneDrumProperties):
    """A bass drum: a PORTED cavity, which is a bass-reflex box with a drumhead
    for a driver.

    This was a tom with the decay turned up and tonal_dampening raised, on the
    bare Bessel set -- a membrane in vacuo. A kick is not that. Its front head is
    normally ported, and a port is not a leak: the plug of air in the hole has
    mass, the cavity behind it has compliance, and together they are a Helmholtz
    resonator coupled to the batter head exactly as a reflex port couples to a
    loudspeaker cone.

        head    M_as = sigma*pi*a^2*J1(j01)^2 / A_eff^2,  A_eff = 2*pi*a^2*J1(j01)/j01
        cavity  C_ab = V/(rho*c^2)
        port    M_ap = rho*L_eff/A_p,  L_eff ~ 1.7*r for a flanged hole
        alpha = C_as/C_ab,   h = omega_port/omega_head

    and the roots of u^2 - u(1 + h^2 + alpha*h^2) + h^2 = 0 are the drum's two
    resonances. For a 22x16 shell with a 5" port and a 10 mil head whose own
    (0,1) is 62 Hz: the port resonates at 59.2 Hz, alpha is 4.52, and the roots
    are 0.394 and 2.424 of the head -- 24 Hz and 150 Hz.

    SO THE THUMP IS THE PORT, NOT THE HEAD. That is the whole point of the
    model, and it is why a kick reads as a thump plus a knock rather than as a
    low tom: the head's own modes are pushed up into a cluster from 250 Hz, and
    what you hear at the bottom is the cavity breathing through the hole. The
    ratios below are normalised to the AIR mode rather than to the head, so the
    base frequency still means what it always did -- the drum's sounding
    fundamental, 62 Hz for GM 36 -- and the pitch tuned by ear does not move.
    What changes is everything above it:

        band            30-60  60-120  120-250  250-500  500-1k
        bare Bessel      -8.7    -0.7    -19.9    -50.7   -70.5
        ported cavity    -8.4    -0.7    -47.9    -42.1   -59.4

    The thump is untouched and the 120-250 Hz shelf -- the boxy region, where a
    real kick is cut and where the old model put the whole Bessel cluster --
    drops 28 dB, reappearing an octave up as knock.

    The (0,2) and (0,3) modes sit far above the port's own resonance, where the
    plug is inertial and the cavity is effectively SEALED, so they take the
    closed-cavity split instead (see TomTomProperties). Modes with a nodal
    diameter move no net air and are untouched.

    NO REFERENCE, and one omission that matters more here than in the toms. A
    real kick is damped with a pillow or a felt strip against the head, which
    kills the 250-650 Hz head cluster -- the boxy region -- while barely
    touching the port mode, because that is a cavity resonance and not a head
    one. This engine's decay is a function of frequency alone, so it cannot damp
    the head modes selectively; the 1/ratio**1.6 gain law already puts that
    cluster about 20 dB down, which stands in for the pillow without being it.
    If this reads as boxy, that is the missing piece, and the honest fix is
    per-mode damping rather than a gain tweak.
    """
    # air/port mode first, then the head's own modes above it
    mode_ratios = (1.000, 4.044, 5.423, 5.826, 6.153, 6.708, 6.735, 7.405,
                   8.009, 8.885, 9.137, 9.258, 9.379, 10.304, 10.490)
    mode_gains  = (1.000, 0.106, 0.069, 0.063, 0.058, 0.051, 0.051, 0.044,
                   0.039, 0.033, 0.032, 0.031, 0.031, 0.026, 0.026)
    max_harmonic = 15
    initial_gain = 0.952381  # solved to hold the level the ear had set
    tension_bend = 0.045       # a kick drops hardest of all: a slack, wide head
    tension_settle_time = 0.13
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


class CrotaleProperties(TunedBarProperties):
    """A crotale: a thick tuned DISC, and the only PLATE in the mallet family.

    MEASURED: Iowa crotales, ff, the full chromatic set C6-C8, 25 notes.

    Everything else here is a BAR -- a glockenspiel, a marimba, a vibraphone --
    and a bar and a plate have different mode families. A free circular plate
    runs 1 : 2.08 : 3.41, where a free bar runs 1 : 2.76 : 5.40. Measured across
    the set the crotale gives median 1 : 2.03 : 3.38, which is the plate law and
    not the bar's.

    So this cannot use bar_modes alone: those pick whole-numbered harmonics, and
    3.41 is not one. Modes 1, 2 and 3 are selected and the inharmonicity stretch
    bends them out to 1 : 2.12 : 3.40, which is within the spread of the
    measurement (f2/f1 runs 2.14 at C6 down to 1.90 at C8).

    THE RING TIME HALVES EVERY 10.3 SEMITONES, from 12.4 s at C6 to 2.5 s at C8
    -- fitted across the set. decay_register_slope carries that: it is the same
    knob the piano uses for the same reason, a small light body losing its
    energy faster than a large heavy one.

    The set also sounds consistently SHARP of its nominal pitch, +6 to +32 cents
    with a mean near +17. That is left alone: it is this particular set's tuning
    and not a property of crotales, and our pitch comes from the tuner.

    General MIDI has no crotale, so nothing routes here by program. GM
    percussion note 84 (Belltree) does -- a belltree is a stack of small tuned
    discs, the same object in a different mounting -- and it was unmapped.
    """
    # MEASURED at last, on twenty-five Iowa crotale takes that had been sitting
    # unused. This was a stretched harmonic series with three partials.
    #
    # Twenty-five pitches is what makes it checkable: a real mode set is the same
    # RATIOS at every pitch, so a ratio that recurs across the set is the
    # instrument and one that does not is that disc. Anchored on the SOUNDING
    # partial rather than the loudest, because on most of these the loudest is
    # the octave. Clustered at 40 cents, over the sixteen takes in the octave
    # that resolves well (the 7th-octave ones are short and near Nyquist):
    #
    #     ratio   in takes   spread   gain
    #     1.000     16/16      0.0     0.437
    #     2.006     14/16      2.0     0.131
    #     2.058      8/16      2.1     0.832   <- the loudest partial
    #     2.132      9/16      2.7     0.419
    #     3.061      9/16      1.7     0.017
    #     3.522      7/16      1.9     0.287
    #     4.091      9/16      2.1     0.002
    #
    # THREE PARTIALS CROWD THE OCTAVE -- 2.006, 2.058 and 2.132 -- and the
    # strongest of all is 2.058 rather than the fundamental. That cluster beating
    # against itself is what a crotale sounds like, and it is why the ear hears a
    # shimmer over the note rather than a clean bell. Spreads of about 2 per cent
    # across sixteen different discs is the measurement agreeing with itself.
    mode_ratios = (1.0000, 2.0059, 2.0578, 2.1324, 3.0606, 3.5218, 4.0912)
    mode_gains  = (0.4372, 0.1309, 0.8323, 0.4194, 0.0168, 0.2867, 0.0100)
    max_harmonic = 7
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False

    bar_modes = ((1, 1.0), (2, 0.72), (3, 0.55))
    # bends modes 2 and 3 to the plate's 2.08 and 3.41 rather than 2 and 3
    inharmonicity_dynamic = False
    # 12.4 s at C6 down to 2.5 s at C8: halves every 10.3 semitones
    decay_register_slope = 1.17


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

    NOT QUITE WHOLE NUMBERS, though. Measured on real kettledrums the (1,1) to
    (5,1) modes come out near 1.00 : 1.50 : 1.97 : 2.44 : 2.90 -- the upper ones
    sit slightly FLAT of 2, 2.5 and 3. That small compression is part of why a
    timpano still reads as a drum and not as a pitched pipe; exactly harmonic
    ratios are the idealisation, not the instrument. This class used to carry
    the idealisation.

    Iowa has no timpani, so neither set is fitted to a recording here. These are
    the standard measured ratios rather than the textbook ones -- better
    sourced, still not verified against a reference in this collection.
    """
    mode_ratios = (1.00, 1.50, 1.97, 2.44, 2.90)
    mode_gains  = (0.55, 1.00, 0.70, 0.42, 0.22)
    inharmonicity_coefficient = 0.0    # the ratios are absolute
    inharmonicity_dynamic = False
    max_harmonic = 5

    # Less drift than a tom: a timpano's head is already at high tension to be
    # tuned at all, so the same stroke stretches it proportionally less -- and a
    # big head settles more slowly.
    tension_bend = 0.016       # ~27 cents at full velocity
    tension_settle_time = 0.30

    # +4.39 dB over the old 1/7.3, in two parts.
    #
    # 1.39 of it is restoring what the ratio change cost. Nothing about the
    # ENERGY moved -- short-term loudness fell 0.34 dB, K-weighted 0.19 -- but
    # the PEAK fell 1.39, because 1 : 1.5 : 2 : 2.5 : 3 re-align in phase at
    # every strike and 1 : 1.5 : 1.97 : 2.44 : 2.90 never quite do. That phase
    # incoherence is the physics working, and the attack is most of what a
    # struck drum's loudness is, so the level came back by peak rather than RMS.
    #
    # The other 3 dB is Ben's ear against the rest of the orchestra, not a
    # measurement. A timpano is a big drum and the balance here was set before
    # any of the percussion was measured; if the kit is ever levelled as a whole
    # this is the first number to revisit.
    initial_gain = (1.0 / 7.3) * 1.659
    tonal_dampening = 1.75
    # A kettle sings rather than thumps, and its higher modes go first. The old
    # implementation smuggled the modes in as unison voices and scaled each
    # one's decay by its RATIO -- 10.5 12.9 15.1 17.3 19.5 dB/s. mode_ratios
    # indexes decay by mode NUMBER instead, so these coefficients are
    # re-derived to land on the same profile: 10.5 12.8 15.1 17.4 19.7.
    decay_db = 8.2
    harmonic_decay_db = 2.3
    harmonic_decay_dampening = 0.0


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
        # mode_ratio: _hf_rolloff wants WHERE the partial is, and with a measured
        # mode set that is not f0*m. (chiff_harmonic_gain below is already handed
        # a ratio by both renderers, so it needs no conversion.) Identity for
        # every harmonic voice.
        return 0.0 if v == 0.0 else v * self._hf_rolloff(self.mode_ratio(harmonic))

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
    """Snare: a membrane with wires rattling against its underside.

    THIS HAD NO MODE SET. It was a harmonic series stretched by 20x the
    2nd-harmonic coefficient with the chiff cranked to 3.0 and sustain_jitter at
    1.0 -- a few loud partials under a permanent hiss, which is exactly the
    construction the crashes proved wrong, and for the same reason: a hiss can
    neither decay per band nor change with the stroke.

    A SNARE IS TWO THINGS AND ONLY ONE OF THEM IS NOISE.

    The batter head is a clamped circular membrane, so its modes are the Bessel
    zeros -- analytic, no recording needed, the same set the toms use. That is
    the pitched half, and it is why a snare with the wires thrown off is just a
    high tom. inharmonicity_coefficient goes to 0 with it: the mode set is
    absolute and both renderers stretch mode_ratios on top of it otherwise, which
    is the bug that had every measured cymbal landing in the wrong place.

    The wires are the other half, and they ARE aperiodic -- unlike a cymbal,
    whose apparent noise turned out to be hundreds of resolvable modes, a snare's
    buzz is genuinely broadband, so here a wash is the right model. What was
    wrong was its shape in time: the wires rattle only while the head is moving
    hard enough to throw them against it, so the buzz dies well before the head
    does. chiff_width carries that; sustain_jitter drops to a floor rather than
    running the whole note.

    AND IT IS THE MOST VELOCITY-DEPENDENT THING IN THE KIT. A ghost note barely
    rattles; a rimshot is almost all wires. strike_noise_slope makes the buzz
    follow the stroke, which the old fixed chiff could not do at all.

    NO REFERENCE. Iowa has no drum kit -- no snare, no bass drum, no toms -- so
    unlike the cymbals none of this is fitted to a recording. The Bessel ratios
    are physics; the gains, the wire balance and the decays are judgement, and
    are marked as such rather than dressed up as measurement.
    """
    # The batter head. Bessel zeros j(m,n)/j(0,1) for a clamped circular
    # membrane -- see MembraneDrumProperties, which derives the same set.
    mode_ratios = (1.000, 1.593, 2.136, 2.295, 2.653, 2.917,
                   3.155, 3.500, 3.599, 3.647, 4.059, 4.132)
    # 1/ratio**1.6, as the toms use: a struck head puts most of its energy in
    # the fundamental and the upper modes fall away fast.
    mode_gains  = (1.000, 0.475, 0.297, 0.265, 0.210, 0.180,
                   0.159, 0.135, 0.129, 0.126, 0.106, 0.103)
    max_harmonic = 12
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    # Twelve modes, and the strike point still sets each one's sign.
    strike_phase_spread = 1.0

    initial_gain = 0.190312
    tonal_dampening = 0.3
    one_shot = True
    release_floor_db = -45.0
    # A snare head is small, tight and heavily damped -- much shorter than a tom
    # at 34 dB/s, and the upper modes go first.
    decay_db = 46.0
    harmonic_decay_db = 22.0
    harmonic_decay_dampening = 0.0

    # A head struck hard is stretched, so it starts sharp and settles: the same
    # mechanism the toms use, smaller here because a snare head is already tight.
    tension_bend = 0.018
    tension_settle_time = 0.14

    # THE WIRES. A burst that dies with the head's motion rather than a hiss that
    # runs the whole note: ~90 ms of rattle under a head that rings ~300.
    chiff_volume = 12.0
    chiff_width = 0.090
    chiff_cycle = 0.9               # near-full phase decorrelation -> broadband
    chiff_release = 0.0
    sustain_jitter = 0.03           # a floor, not the sound
    chiff_min_valve_time = 0.002
    chiff_max_valve_time = 0.012
    # Ghost note to rimshot: the wires are what changes, not the head. But not
    # by THIS much -- at 1.3 the buzz scaled by attack_volume**1.3, which is
    # 26 dB from ff down to pp, and the wires simply left. What remained was the
    # Bessel head alone, and that head spans 260 to 1074 Hz, so below about
    # forte this voice was a small tom. Ben, hearing two hits at velocity 58 in
    # a jazz pattern: "The snare sounds like a bass drum?"
    #
    #     slope      v40      v58      v80     v100     v127   (centroid)
    #      1.30   335 Hz   490 Hz  1225 Hz  2815 Hz  5812 Hz
    #      0.35  2175 Hz  3141 Hz  4188 Hz  4941 Hz  5812 Hz
    #
    # at 1.30, 92% of a ghost note's energy sat in 200-500 Hz and 0.2% above
    # 2 kHz. A ghost note is QUIET, not toneless: the wires still rattle, which
    # is the whole reason a ghost note reads as a snare at all. The docstring
    # above used to say "a ghost note barely rattles" and that judgement was the
    # error -- nothing measured it, because Iowa has no drum kit.
    #
    # 0.35 keeps the wires at every dynamic and still opens the drum up with the
    # stroke. For scale, the one dynamic-brightness figure in this file that IS
    # measured -- the Iowa suspended cymbals, mf to ff -- is a median 0.02 dB of
    # brightening per dB of level. Struck metal and membrane hardly brighten at
    # all; 26 dB across the dynamic was never defensible. Still judgement, and
    # still Ben's ear as the outer loop.
    strike_noise_slope = 0.35


class ElectricSnareProperties(SnareDrumProperties):
    """Note 40. A drum machine's snare, which is not a snare drum.

    It had been the acoustic snare at a different pitch. What GM means by
    Electric Snare is the 808/909 sound: a short burst of noise over a pitched
    body that DROPS, and no wires at all -- the rattle an acoustic snare gets
    from forty steel spirals under the head is replaced by a filtered noise
    generator, which is why a drum machine's snare is so much cleaner and so
    much shorter.

    THE DROP IS tension_bend, the fourth voice in this file to use it and the
    second as a drum-machine sweep: the synth drum's 808 tom falls a fifth, and
    a snare's body falls less and faster.
    """
    # The body drops, fast. Less than the tom's fifth -- a snare is a crack.
    tension_bend = 0.22
    tension_bend_max = 0.35
    tension_settle_time = 0.022
    tension_settle_cutoff = 0.3

    # Fewer modes than a head has: an oscillator and a noise band, not forty
    # wires and a membrane.
    max_harmonic = 8
    tonal_dampening = 1.15
    decay_db = 40.0
    harmonic_decay_db = 26.0
    strike_noise_slope = 0.0    # a machine does not get rattlier when hit harder



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

    AND IT REALLY IS OFF NOW. That sentence was written and not carried out:
    what had been switched off was sustain_jitter, while section_players stayed
    at the 7 this class inherits from BowedStringProperties. So GM 80 and 81
    shipped as SEVEN oscillators 6 cents apart, each with its own 5-cent
    vibrato -- a supersaw, which is a fine sound and is not a sawtooth, and is
    flatly at odds with this family being exact. A docstring is not a test,
    which is why there is now a check for it in live.py's selftest.
    """
    # CC71-78: a synthesiser IS the instrument these controls were named for:
    # every one lands.
    sound_controls = frozenset(('resonance', 'release', 'attack', 'brightness',
                                'decay', 'vib_rate', 'vib_depth', 'vib_delay'))

    # AND ITS GLIDE IS A CIRCUIT, NOT AN ARM. This inherits from the bowed
    # string, so it has to say so or a saw lead would portamento like a
    # violinist: a hand speed, an asymmetry between going up and going down,
    # and a reach of a fifth. A voltage-controlled oscillator behind a lag has
    # none of those -- it settles exponentially in PITCH rather than in length,
    # both directions alike, as far as it is asked. This is the one place in
    # the bank where the synthetic answer is the correct one rather than the
    # cheap one, which is the same argument this class was created to make.
    glide_mechanism = 'circuit'
    glide_reach_semitones = None
    # ...AND A SYNTHESISER TAKES IT BACK. This sits under the bowed string for
    # its spectrum, not for its dampers: a pedal on a synth holds the gate.
    damper_pedal = True
    odd_only = False
    # ONE oscillator. Not a section, and not an ensemble.
    section_players = 1
    section_spread_cents = 0.0
    section_vibrato_cents = 0.0
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
    # RE-CALIBRATED after the section was switched off (see above): the old
    # divisor was measured with seven oscillators running, so it described a
    # supersaw's level and not a saw's. Against the church organ on the same
    # passage in the same room, as the whole lead family now is.
    initial_gain = 0.05263

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
    initial_gain = 0.06238         # measured the same way; a square sits ~1.5 dB over a saw

    def harmonic_volume(self, harmonic):
        if harmonic % 2 != 1:
            return 0.0
        if self.max_harmonic and harmonic > self.max_harmonic:
            return 0.0
        return self.gain / harmonic



# ------------------------------------------------------------- the synth leads
# GM 82-87 all shared SynthLeadProperties, which is a FlueOrganProperties: an
# organ pipe standing in for a synthesiser. 80 and 81 already had their own
# classes and this finishes the family.
#
# THE TARGET HERE IS A SPECIFICATION, NOT AN INSTRUMENT, and that inverts the
# usual problem. Everywhere else in this bank the model is an approximation of
# a physical object and a recording can contradict it. A sawtooth is not an
# approximation of anything: it IS the harmonic series at 1/n, exactly, and a
# square IS the odd harmonics at 1/n. There is no object to measure and nothing
# a recording could correct, so an additive engine renders these EXACTLY rather
# than approximately -- which is the one family where this renderer has an
# advantage over sampling rather than a handicap.
#
# WHAT IS NOT SPECIFIED is everything that makes a waveform a LEAD rather than a
# buzz: the resonant low-pass, its envelope, the vibrato, the doubling. General
# MIDI names eight leads and defines none of them, so the reading used here is
# the Roland SC-55's, which is what the files in the wild were written for.
# Those choices are judgement and are marked as such.
#
# The filter envelope is not new machinery either. A lead's low-pass sweeping
# shut is upper partials dying faster than lower ones, which is exactly
# harmonic_decay_db -- so the classic filter envelope falls out of the decay law
# the same way the Rhodes' growl did.


class TriangleSynthProperties(SquareSynthProperties):
    """GM 82, Lead 3 (calliope): the soft one. A TRIANGLE, exactly.

    A triangle is the odd harmonics at 1/n^2 where a square is the odd harmonics
    at 1/n -- so it is the same hollow interval structure falling away four times
    faster, which is why it sounds round and flute-like where a square sounds
    hollow and reedy. That is the calliope lead: soft, nearly pure, a little
    breathy, and the GM name is misleading -- a real calliope is a steam whistle
    organ and this patch is nothing like one. The SC-55 reading is the soft lead,
    and that is what files expect.

    Exact, like its siblings. The 1/n^2 is the waveform's definition.
    """
    # A little vibrato, because the soft leads are always played with some and
    # a naked triangle is a test tone. Judgement, not specification.
    section_players = 1
    initial_gain = 0.06754          # 1/n^2 sums to far less than 1/n, hence the larger number

    def harmonic_volume(self, harmonic):
        if harmonic % 2 != 1:
            return 0.0
        if self.max_harmonic and harmonic > self.max_harmonic:
            return 0.0
        return self.gain / (harmonic * harmonic)


class ChiffLeadProperties(SawtoothSynthProperties):
    """GM 83, Lead 4 (chiff): a saw with a BREATH on the front.

    The chiff is the whole patch -- a soft-attacking lead whose onset carries a
    noisy, pitched-up transient, imitating the way a flue pipe's air jet finds
    its edge before the tone settles. The renderer already models that, for the
    instrument the effect is named after, so this is the organ's chiff on a
    synthetic waveform rather than anything new.
    """
    # The chiff SawtoothSynthProperties deliberately switched off, switched back
    # on: it is the one thing this patch is named for.
    chiff_volume = 0.55
    chiff_cycle = 1.0 / 4.0
    chiff_min_valve_time = 0.010
    chiff_max_valve_time = 0.032
    # ...and the body settles darker than a raw saw once the breath has gone,
    # which is the filter closing after the attack. See the note on the family:
    # a filter envelope is upper partials dying faster.
    harmonic_decay_db = 0.9
    max_harmonic = 48
    initial_gain = 0.05916


class CharangLeadProperties(SawtoothSynthProperties):
    """GM 84, Lead 5 (charang): the hard, guitar-like one.

    A charango is a small Andean lute, and as with the calliope the GM name
    describes an association rather than an instrument: the patch is a bright
    aggressive lead with a guitar's bite. What gives it that is distortion, and
    the renderer has a valve -- so this is a saw through the amplifier the
    electric guitars use.

    amp_reference scales with initial_gain, as the guitar work established: the
    reference is the level the drive is measured against, so the two move
    together or the voice gets louder AND dirtier.
    """
    amp_drive = 1.46
    amp_reference = None            # set below, from this class's own gain
    max_harmonic = 48
    # Hard and bright, with the low end tightened the way a driven amp does.
    harmonic_decay_db = 0.25
    initial_gain = 0.05685


class VoiceLeadProperties(FormantBody, SawtoothSynthProperties):
    """GM 85, Lead 6 (voice): a waveform sung through a vocal tract.

    The formants are the patch. A voice lead is not a vowel sample -- it is an
    oscillator behind a fixed pair of vocal resonances, which is precisely what
    FormantBody is for, and the same reason a bassoon's fourth harmonic can
    stand above its fundamental.

    The vowel is an open /a/, from vowels.py's table (Peterson & Barney where it
    overlaps them), copied rather than imported: tonelib does not depend on the
    singing pipeline and should not start here for three numbers.
    """
    # vowels.py VOWELS['a'], an adult male tract.
    formants = ((730.0, 130.0, 1.00), (1090.0, 90.0, 0.55), (2440.0, 130.0, 0.22))
    formant_floor = 0.06
    bore_corner_hz = 4000.0
    bore_order = 2.0
    bell_cutoff_hz = 0.0
    bell_order = 1.0
    max_harmonic = 48
    initial_gain = 0.04470

    def harmonic_volume(self, harmonic):
        # THE MIXIN HAD TO BE WIRED UP BY HAND, and it is worth saying why.
        # SawtoothSynthProperties overrides harmonic_volume to return
        # `self.gain / harmonic` directly -- deliberately, so a saw is exactly
        # 1/n and nothing downstream can bend it. That also bypasses bore_gain,
        # which is the hook FormantBody works through, so inheriting FormantBody
        # here did exactly nothing: measured, this voice rendered as a plain saw,
        # partial for partial, with three vocal formants declared and inert.
        # The same trap as PluckedStringProperties having no `formants`
        # attribute at all -- inheriting a body is not the same as sounding
        # through it.
        if self.max_harmonic and harmonic > self.max_harmonic:
            return 0.0
        f0 = self.frequency_x * (2.0 ** self.octave_position)
        return (self.gain / harmonic) * self.bore_gain(f0 * harmonic) * self._bore_norm()



class SynthPadProperties(FormantBody, SawtoothSynthProperties):
    """GM 88-95, the pads. One BowedStringProperties served all eight.

    Together with the effects at 96-103 that was sixteen programs on one voice,
    and the largest single gap in the bank.

    WHAT MAKES A PAD A PAD is the swell: a long attack, a filter that opens with
    it, and a sustain that holds. Everything here has that, and it is why none
    of them is a lead. What separates the eight from each other is not a tweak
    to the same sound -- General MIDI's own names point at eight different
    MECHANISMS, and each subclass below gets one it does not share:

      88 new age    a glassy bell, slightly stretched -- not quite harmonic
      89 warm       a low cutoff and a wide chorus, and nothing else
      90 polysynth  the bright one, and the only pad with a fast enough front
                    to play chords rhythmically
      91 choir      VOCAL FORMANTS, from vowels.py's own table
      92 bowed      a slow swell over a ringing body -- bowed glass
      93 metallic   INHARMONIC partials: the only voice here whose overtones
                    are not whole multiples, which is what metal means
      94 halo       hollow: odd harmonics, with an airy formant high up
      95 sweep      the filter sweep itself, far deeper than any other pad's

    General MIDI specifies none of this. Level 1 is a name list; the readings
    are the Roland SC-55's, which is what the files in the wild expect.
    """
    damper_pedal = True         # the gate, not a felt -- see SynthProperties
    max_harmonic = 40

    # The swell. Long, and fixed in seconds: a pad's attack owes nothing to the
    # note's wavelength, which is why speech_cycles stays zero throughout.
    attack_time = 0.28
    speech_cycles = 0.0
    chiff_volume = 0.0
    decay_db = 0.8
    harmonic_decay_db = 1.1
    harmonic_decay_dampening = 0.0
    sustain_level = 0.93

    # A chorus, as the string machine has: fixed offsets, swept slowly. Every
    # pad of the era had one, and it is the same systematic-not-drawn argument.
    chorus_cents = (-8.0, 8.0)
    chorus_gain = 0.70
    section_vibrato_cents = 3.0
    section_vibrato_hz = (0.3, 0.8)

    formants = ((1200.0, 1300.0, 0.60),)
    formant_floor = 0.16
    bore_corner_hz = 3400.0
    bore_order = 2.0
    bell_cutoff_hz = 0.0
    bell_order = 1.0

    initial_gain = 0.02         # balance-normalised per subclass below

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        return [(self.chorus_gain, 0.0, 2.0 ** (c / 1200.0) - 1.0,
                 harmonic_decay, 1.5707963 * (i + 1))
                for i, c in enumerate(self.chorus_cents)]

    def harmonic_volume(self, harmonic):
        # Hand-wired, as on every oscillator voice with a body: the sawtooth
        # parent returns gain/n directly and never reaches bore_gain.
        if self.max_harmonic and harmonic > self.max_harmonic:
            return 0.0
        if self.odd_only and harmonic % 2 == 0:
            return 0.0
        f0 = self.frequency_x * (2.0 ** self.octave_position)
        return (self.gain / harmonic) * self.bore_gain(f0 * harmonic) * self._bore_norm()


class NewAgePadProperties(SynthPadProperties):
    """GM 88, Pad 1 (new age). Glassy, and very slightly STRETCHED.

    The SC-55's "Fantasia" -- a bell-like pad with a soft attack. What makes it
    glassy rather than merely bright is that its partials are not quite whole
    multiples: a small stretch, an order of magnitude under the metallic pad's,
    so it shimmers where GM 93 clangs.
    """
    inharmonicity_coefficient = 0.00035
    inharmonicity_dynamic = False
    # A STRETCHED SERIES MUST BE SHORTER THAN A HARMONIC ONE. The stretch law is
    # 1 + 0.5*(h^2-1)*B, so it grows with the SQUARE of the partial index: at 40
    # partials this voice's h40 lands at 51 x f0, which is 17 kHz on an E4 and
    # nothing like a mode anything has. Real glass rings in a couple of dozen.
    max_harmonic = 24
    formants = ((2400.0, 1800.0, 0.85),)
    formant_floor = 0.10
    bore_corner_hz = 5200.0
    attack_time = 0.20
    chorus_cents = (-5.0, 5.0, 12.0)
    # Balance-normalised against the acoustic string ensemble (GM 48) on the
    # same passage in the same room -- what a pad is reached for INSTEAD of,
    # so it is the comparison a sequencer actually makes.
    initial_gain = 0.0495371


class WarmPadProperties(SynthPadProperties):
    """GM 89, Pad 2 (warm). A low cutoff and a wide chorus, and nothing else.

    The plainest member, deliberately: it is the pad you put underneath
    something, and its whole job is to take up room without asking for
    attention. No formant high up, no stretch, no sweep.
    """
    formants = ((700.0, 700.0, 0.55),)
    formant_floor = 0.20
    bore_corner_hz = 2000.0
    attack_time = 0.34
    chorus_cents = (-13.0, 11.0, 20.0)
    chorus_gain = 0.78
    initial_gain = 0.0390393


class PolysynthPadProperties(SynthPadProperties):
    """GM 90, Pad 3 (polysynth). The bright one, and the only one you can play.

    A Prophet or a Juno playing chords: detuned saws, an open filter, and an
    attack short enough to articulate a rhythm. It is in the pad family by name
    and is really a poly patch, which is why its front is four times faster than
    its neighbours'.
    """
    attack_time = 0.045
    decay_db = 2.2
    harmonic_decay_db = 2.0
    sustain_level = 0.84
    formants = ((2000.0, 1600.0, 0.80),)
    formant_floor = 0.12
    bore_corner_hz = 5000.0
    chorus_cents = (-7.0, 7.0)
    chorus_gain = 0.85
    initial_gain = 0.0495865


class ChoirPadProperties(SynthPadProperties):
    """GM 91, Pad 4 (choir). An oscillator behind a VOCAL TRACT.

    The formants are the patch, and they are the same table the singing
    pipeline uses -- vowels.py's own, Peterson & Barney where it overlaps them.
    An open /O/ rather than the voice lead's /a/: rounder, which is what a choir
    pad is against a solo synth voice.

    A THIRD FORMANT AND A FLOOR, because a choir is many people. The floor is
    what a section passes between its resonances; a soloist's is lower.
    """
    # vowels.py VOWELS['O'], widened: a section's formants are the average of
    # many tracts and so are broader than any one singer's.
    formants = ((570.0, 180.0, 1.00), (840.0, 220.0, 0.70), (2410.0, 400.0, 0.30))
    formant_floor = 0.10
    bore_corner_hz = 3600.0
    attack_time = 0.24
    chorus_cents = (-9.0, 6.0, 14.0)
    initial_gain = 0.0453122


class BowedPadProperties(SynthPadProperties):
    """GM 92, Pad 5 (bowed). Bowed glass: a slow swell over a ringing body.

    The SC-55 calls it "Bowed Glass". What it is not is a bowed STRING -- GM 48
    and 49 are that, and this is a struck-glass resonance excited slowly, which
    is why the swell is the longest in the family and the body rings high and
    narrow rather than broadly.
    """
    attack_time = 0.42
    decay_db = 0.4
    harmonic_decay_db = 0.7
    sustain_level = 0.95
    formants = ((3000.0, 900.0, 1.10),)
    formant_floor = 0.08
    bore_corner_hz = 6000.0
    chorus_cents = (-4.0, 4.0)
    initial_gain = 0.0617642


class MetallicPadProperties(SynthPadProperties):
    """GM 93, Pad 6 (metallic). The only pad whose partials are NOT harmonic.

    That is what metal means, and it is the one distinction here that is a
    matter of physics rather than of filtering. A struck or bowed plate rings in
    modes that are not whole multiples of anything, so the overtones beat
    against each other instead of fusing into a pitch -- which is why a metallic
    pad has an edge no amount of brightness gives a harmonic one.

    The stretch is the mallet family's order of magnitude, not the piano's: a
    piano is a stiff STRING and barely stretched, where a bar or a plate is
    stretched enough to hear.
    """
    inharmonicity_coefficient = 0.0062
    inharmonicity_dynamic = False
    # And far shorter again, because B here is eighteen times the glassy pad's:
    # at 40 partials h40 sat at 238 x f0, which is 78 kHz on an E4 -- partials
    # the renderer would carry to the edge of the band and throw away. A struck
    # plate has a handful of modes, not forty. Capped, h14 lands at 7.4 kHz.
    max_harmonic = 14
    formants = ((2800.0, 2000.0, 0.90),)
    formant_floor = 0.12
    bore_corner_hz = 6500.0
    attack_time = 0.18
    chorus_cents = (-6.0, 9.0)
    initial_gain = 0.0571093


class HaloPadProperties(SynthPadProperties):
    """GM 94, Pad 7 (halo). Hollow, and airy above it.

    ODD HARMONICS ONLY, which is an exact distinction rather than a tuned one --
    a square IS the odd harmonics at 1/n, as GM 80 and GM 39 are -- and it is
    what makes a halo pad hollow where the warm pad is full. Over that, a formant
    placed high and wide: the "air" the name is pointing at.
    """
    odd_only = True
    formants = ((3400.0, 2600.0, 0.75),)
    formant_floor = 0.14
    bore_corner_hz = 5600.0
    attack_time = 0.30
    chorus_cents = (-10.0, 7.0)
    initial_gain = 0.0608278


class SweepPadProperties(SynthPadProperties):
    """GM 95, Pad 8 (sweep). The filter sweep IS the patch.

    Every pad here has a filter that shuts as the note holds -- upper partials
    dying faster than lower ones, which is harmonic_decay_db. On the others that
    is a colour. Here it is the sound, and it is set an order of magnitude
    deeper: measured, the fundamental holds while the sixteenth harmonic falls
    at over a hundred dB a second, so the note visibly closes while it sustains.

    WHAT IS NOT MODELLED is the sweep going back UP. A real sweep pad's filter
    is driven by an LFO or a slow envelope that opens as well as closes, and
    this renderer's decay law is monotonic per partial -- a partial can fall
    faster than its neighbour but cannot rise. A rising sweep needs a partial
    whose amplitude envelope has a positive segment, which is machinery this
    engine does not have and which is a larger change than this voice justifies.
    """
    decay_db = 0.5
    harmonic_decay_db = 7.5     # an order of magnitude past the other pads'
    sustain_level = 0.88
    formants = ((1600.0, 1500.0, 0.90),)
    formant_floor = 0.10
    bore_corner_hz = 4400.0
    attack_time = 0.26
    chorus_cents = (-8.0, 8.0)
    initial_gain = 0.0574479



class SynthEffectProperties(SynthPadProperties):
    """GM 96-103, the synth effects. The last eight programs on one voice.

    Built on the pads, because most of these ARE pads with something extra --
    what General MIDI calls an effect here is a pad with one unusual property
    pushed to the front. Each subclass below gets one the others do not.

    DELAYED ENTRIES COST NOTHING, and how far that gets is worth stating
    precisely, because it is less far than it first looked. The renderer already
    gives each player of a SECTION their own entry instant -- `non` is a
    per-partial column and blockrender adds `onsets[ui+1]` to it -- so evenly
    spaced entries at falling gain are available for free, the same shape of
    reuse as the string machine's chorus.

    WHAT THAT IS NOT is a delay line. A delay repeats a SIGNAL; this repeats an
    ONSET. Each tap is a fresh set of partials starting while the original is
    still ringing, and being at the same pitch they comb against it rather than
    arriving as a separate event -- measured, a note with four taps rose again
    ten times in its first second. Drifting each tap a few cents, which is what
    tape and bucket-brigade delays do on every pass and which should have
    decorrelated them, took that from ten to nine. The drift is kept because it
    is what the hardware does; it did not buy what it was meant to buy.

    So what these voices actually have is a REPEATED ATTACK at falling gain,
    which on a decaying note reads as repeats and on a sustaining one reads as
    thickening. That is why GM 102's envelope is set percussive below. A true
    delay line wants the renderer to sum a delayed copy of the OUTPUT, which is
    a pass like tremolo.py or cabinet.py and not a property of a voice.

    `section_onsets_at` is overridden rather than reused, because the section's
    version DRAWS its offsets (a scatter, which is what an ensemble wants) and
    an echo needs them evenly spaced and repeatable. Systematic against drawn,
    one more time.

    WHAT LIMITS IT, stated because it is a real constraint and not a choice:
    blockrender caps a player's entry at a QUARTER of the note's duration, so
    the echo shortens with the note instead of standing at a fixed time the way
    a delay pedal does. On a held chord it is an echo; on a short note it is a
    thickening. Raising that cap is a renderer change, not a voice one.
    """
    echo_taps = ()              # seconds, per extra voice; () = no echo
    echo_falloff = 0.55         # each tap this fraction of the one before

    def section_onsets_at(self, frequency):
        if not self.echo_taps:
            return super().section_onsets_at(frequency)
        # index 0 is the main voice and must be on time.
        return [0.0] + list(self.echo_taps)

    echo_drift_cents = 2.5      # per pass; see below

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        if not self.echo_taps:
            return super().unison_voices(frequency, harmonic, harmonic_decay)
        # A TAP MUST DRIFT, or it is not a repeat but an interference pattern.
        # Measured on the first attempt with the taps at exactly the note's
        # pitch: four identical, phase-coherent copies of the same partials
        # starting at different instants do not read as four repeats, they comb
        # against the still-ringing original. The envelope rose again TEN times
        # in the first second where there are four taps, which is beating and
        # not echo.
        #
        # A real delay does not have that problem, and the reason is physical:
        # tape and bucket-brigade delays accumulate wow on every pass, so the
        # nth repeat is a few cents off the (n-1)th and the copies cannot lock
        # together. Drifting each tap progressively is therefore both the fix
        # and what the hardware does.
        return [(self.chorus_gain * (self.echo_falloff ** (i + 1)),
                 0.0,
                 2.0 ** (self.echo_drift_cents * (i + 1) / 1200.0) - 1.0,
                 harmonic_decay, 0.0)
                for i in range(len(self.echo_taps))]


class RainFXProperties(SynthEffectProperties):
    """GM 96, FX 1 (rain). Glassy droplets, falling.

    The SC-55's "Ice Rain": a bright bell-like tone that repeats. Two mechanisms
    at once, and it is the only voice here with both -- a stretched, glassy
    series and an ECHO, because the repeats are what makes it rain rather than
    a chime.
    """
    inharmonicity_coefficient = 0.0022
    inharmonicity_dynamic = False
    max_harmonic = 16           # stretched, so short: see SynthPadProperties
    echo_taps = (0.11, 0.23, 0.37)
    echo_falloff = 0.62
    attack_time = 0.02          # a droplet does not swell
    decay_db = 3.0
    harmonic_decay_db = 3.0
    sustain_level = 0.40
    formants = ((3200.0, 2200.0, 0.95),)
    formant_floor = 0.10
    bore_corner_hz = 7000.0
    # Balance-normalised against the acoustic string ensemble (GM 48), as the
    # pads are: what one of these is reached for INSTEAD of.
    initial_gain = 0.12368


class SoundtrackFXProperties(SynthEffectProperties):
    """GM 97, FX 2 (soundtrack). The widest thing in the bank.

    A slow sweeping pad with the chorus opened as far as it goes -- this is the
    voice whose whole character is WIDTH, where the warm pad's is weight. The
    sweep is deep and the swell is long.
    """
    attack_time = 0.55          # the longest front of any voice here
    harmonic_decay_db = 5.0
    sustain_level = 0.92
    chorus_cents = (-22.0, 17.0, 29.0, -13.0)
    chorus_gain = 0.80
    section_vibrato_hz = (0.2, 0.5)
    formants = ((1300.0, 1500.0, 0.75),)
    formant_floor = 0.16
    bore_corner_hz = 3800.0
    initial_gain = 0.0416079


class CrystalFXProperties(SynthEffectProperties):
    """GM 98, FX 3 (crystal). The most inharmonic voice in the bank.

    A struck glass bell: the stretch here is larger than the metallic pad's, so
    the overtones are further from whole multiples and beat harder. Short
    series, for the reason the pads recorded -- the stretch grows as the square
    of the index, so a strongly stretched voice must carry few partials or its
    top ones leave the band.
    """
    inharmonicity_coefficient = 0.0105
    inharmonicity_dynamic = False
    max_harmonic = 10
    attack_time = 0.015
    decay_db = 1.6
    harmonic_decay_db = 2.2
    sustain_level = 0.55
    formants = ((4000.0, 2600.0, 1.05),)
    formant_floor = 0.08
    bore_corner_hz = 8000.0
    chorus_cents = (-4.0, 4.0)
    initial_gain = 0.0754605


class AtmosphereFXProperties(SynthEffectProperties):
    """GM 99, FX 4 (atmosphere). The breathy one.

    BREATH is its mechanism, and it is the only voice in these two families to
    use it: sustain_jitter broadens every partial into a band, which is what the
    pan pipe and the shakuhachi use for air past an edge. Here there is no edge
    -- it is an oscillator -- but the effect a synthesist reaches for is the
    same, and the renderer makes it the same way.
    """
    sustain_jitter = 0.55       # the pan pipe's value; see PanFluteProperties
    attack_time = 0.34
    formants = ((1100.0, 1400.0, 0.60),)
    formant_floor = 0.22
    bore_corner_hz = 3000.0
    chorus_cents = (-12.0, 9.0)
    initial_gain = 0.0494635


class BrightnessFXProperties(SynthEffectProperties):
    """GM 100, FX 5 (brightness). The brightest, and the hardest front.

    Its mechanism is the attack: a fast, hard onset on a wide-open filter, which
    is what separates it from every other pad here. Where the polysynth pad is
    merely quick, this one is quick AND has nothing rolled off above it.
    """
    attack_time = 0.012
    decay_db = 3.5
    harmonic_decay_db = 1.6
    sustain_level = 0.80
    formants = ((5000.0, 3500.0, 0.95),)
    formant_floor = 0.30        # very little taken out anywhere
    bore_corner_hz = 9000.0
    chorus_cents = (-6.0, 6.0)
    initial_gain = 0.0563511


class GoblinsFXProperties(SynthEffectProperties):
    """GM 101, FX 6 (goblins). Dark, and WOBBLING.

    The unsettling one, and what unsettles is a deep slow pitch modulation --
    far deeper than any vibrato and far slower, so it reads as the instrument
    being unstable rather than as a player's expression. That is its mechanism:
    section_vibrato_cents at twenty times a violinist's depth.

    Dark with it, because the two together are the effect: a wobble on a bright
    sound is a broken synth, and on a dark one it is a cave.
    """
    section_vibrato_cents = 55.0        # a violinist uses 5
    section_vibrato_hz = (0.18, 0.45)
    attack_time = 0.30
    formants = ((480.0, 420.0, 0.70),)
    formant_floor = 0.10
    bore_corner_hz = 1500.0
    chorus_cents = (-16.0, 13.0)
    initial_gain = 0.0490219


class EchoesFXProperties(SynthEffectProperties):
    """GM 102, FX 7 (echoes). The delay line itself.

    Four evenly spaced repeated ATTACKS at falling gain, built out of the
    section's own per-player entry offsets -- see SynthEffectProperties, which
    records both how that works and how far short of a real delay line it
    falls. Unlike the chorus every other voice here has, the taps are at the
    note's own pitch save for a few cents of tape-style drift per pass.
    """
    echo_taps = (0.16, 0.32, 0.48, 0.64)
    echo_falloff = 0.60
    chorus_gain = 0.95          # the first tap is nearly as loud as the note

    # AND THE NOTE MUST DECAY, or the taps are not an echo. Measured on the
    # first attempt, with a pad's slow front and a 0.70 sustain, the four
    # repeats merged into the note they were repeating: the envelope rose
    # smoothly from 0.72 to 1.00 over 0.6 s with no step at any tap time. Each
    # copy was there and none of them was audible AS a copy.
    #
    # A delay is only heard when what it repeats has ENDED. The SC-55 calls
    # this one "Echo Drops" and it is a plucky tone, not a pad, for exactly
    # that reason -- so the front is fast, the decay steep and the sustain low,
    # and each tap then lands in the gap the last one left.
    attack_time = 0.008
    decay_db = 7.0
    harmonic_decay_db = 4.0
    sustain_level = 0.12
    formants = ((1800.0, 1600.0, 0.80),)
    formant_floor = 0.12
    bore_corner_hz = 4200.0
    initial_gain = 0.220825


class SciFiFXProperties(SynthEffectProperties):
    """GM 103, FX 8 (sci-fi). Hollow, bright, and sweeping.

    The only voice in these two families to combine ODD HARMONICS with a deep
    sweep: hollow like the halo pad, closing like the sweep pad, and brighter
    than either. Two exact mechanisms stacked rather than a new one.
    """
    odd_only = True
    harmonic_decay_db = 6.5
    attack_time = 0.10
    decay_db = 1.0
    sustain_level = 0.82
    formants = ((2600.0, 2000.0, 0.95),)
    formant_floor = 0.10
    bore_corner_hz = 6000.0
    chorus_cents = (-9.0, 9.0)
    initial_gain = 0.0708722



class SynthStringsProperties(FormantBody, SawtoothSynthProperties):
    """GM 50 and 51. A STRING MACHINE: sawtooths through a chorus, not a section.

    Both were in BOWED_ENSEMBLE, so they routed per register to the four
    MEASURED string bodies -- which meant GM 50 and GM 51 rendered identically
    to GM 48, the acoustic string ensemble. Three programs, one voice. The same
    redundancy the synth brass fell into by being tuned onto the modelled horn,
    except here it was not even a resemblance: it was the same class.

    THE CHORUS IS THE INSTRUMENT, and it is a different mechanism from a
    section. An ARP or Solina string machine has ONE oscillator per key and gets
    its width from a bucket-brigade chorus: a small number of copies at FIXED
    offsets, each slowly swept by its own low-frequency oscillator. A string
    section has many players whose spread is random, per player, per note, and
    who never agree. Systematic against drawn -- the accordion's musette
    argument, one more time.

    That difference is audible and is most of why nobody mistakes a string
    machine for an orchestra: the machine's width is periodic and identical on
    every note, and a section's is not.

    THE SWEEP COSTS NOTHING. Each chorus voice's slow detune modulation is
    voice_vibrato, which SectionMixin already provides per player index and
    which the renderer already reads as vd/vr/vp -- so a BBD chorus is the
    section's own per-player vibrato machinery running at a chorus rate instead
    of a violinist's. Set slow and shallow, it IS the effect.

    AND THE ATTACK IS THE OTHER HALF. A string pad swells: the filter and the
    amplifier open together over a fixed time with nothing to do with the note's
    wavelength, which is why speech_cycles stays zero where every acoustic wind
    and bowed voice sets it.
    """
    max_harmonic = 40

    # The swell. Long enough to read as a pad rather than a lead.
    attack_time = 0.16
    speech_cycles = 0.0
    chiff_volume = 0.0
    decay_db = 1.2
    harmonic_decay_db = 1.4
    harmonic_decay_dampening = 0.0
    sustain_level = 0.90

    # The chorus: fixed offsets in cents, the same on every note and every time.
    chorus_cents = (-7.0, 7.0, 13.0)
    chorus_gain = 0.72
    # ...each swept by its own slow LFO. A chorus rate, not a vibrato rate:
    # a player's vibrato is 4.6-6.4 Hz and this must not be mistaken for one.
    section_vibrato_cents = 3.0
    section_vibrato_hz = (0.35, 0.85)

    formants = ((1500.0, 1400.0, 0.70),)
    formant_floor = 0.14
    bore_corner_hz = 3600.0
    bore_order = 2.0
    bell_cutoff_hz = 0.0
    bell_order = 1.0

    initial_gain = 0.02         # balance-normalised per subclass below

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        # FIXED, not drawn. Phase 0.25 apart so the copies do not all start
        # together the way a struck body's do -- a BBD chorus's taps are
        # staggered by construction.
        return [(self.chorus_gain, 0.0, 2.0 ** (c / 1200.0) - 1.0,
                 harmonic_decay, 1.5707963 * (i + 1))
                for i, c in enumerate(self.chorus_cents)]

    def harmonic_volume(self, harmonic):
        # Hand-wired, as on the voice lead, the synth brass and the synth bass:
        # the sawtooth parent returns gain/n directly and never reaches
        # bore_gain, which is the hook FormantBody works through.
        if self.max_harmonic and harmonic > self.max_harmonic:
            return 0.0
        f0 = self.frequency_x * (2.0 ** self.octave_position)
        return (self.gain / harmonic) * self.bore_gain(f0 * harmonic) * self._bore_norm()


class SynthStrings1Properties(SynthStringsProperties):
    """GM 50. The brighter one, and the faster swell.

    General MIDI names two and specifies neither; the reading is the SC-55's,
    where 50 is the brighter string pad and 51 the slower, warmer one.
    """
    attack_time = 0.12
    formants = ((1800.0, 1500.0, 0.75),)
    bore_corner_hz = 4200.0
    chorus_cents = (-6.0, 6.0, 11.0)
    # Balance-normalised against the acoustic string ensemble (GM 48) on the
    # same passage in the same room -- the neighbour these two are chosen
    # INSTEAD of, so it is the comparison a sequencer actually makes.
    initial_gain = 0.0462611


class SynthStrings2Properties(SynthStringsProperties):
    """GM 51. The slow one: a longer swell and a lower cutoff.

    Darker and slower is one decision rather than two, the argument
    SlowBowedStringProperties makes about the bow and GM 63 about its filter: an
    envelope that opens gently never reaches as far up the series.

    And the chorus is WIDER, which is where the extra warmth comes from -- more
    of that periodic width is exactly what a string machine's depth switch does.
    """
    attack_time = 0.30
    formants = ((1000.0, 1000.0, 0.62),)
    bore_corner_hz = 2600.0
    chorus_cents = (-11.0, 9.0, 18.0)
    section_vibrato_hz = (0.25, 0.6)
    initial_gain = 0.045397     # against the string ensemble, as GM 50


class SynthBassProperties(FormantBody, SawtoothSynthProperties):
    """GM 38 and 39. An oscillator through a resonant low-pass, in the bass.

    Both fell through to PluckedStringProperties -- the GENERIC plucked string,
    which has no `formants` attribute at all, so a synth bass was a bare string
    series with no body, no filter and nothing synthetic about it. The third
    family to be caught by that same hole, after the pizzicato and the harp.

    THE FILTER ENVELOPE IS THE PLUCK, and on a bass it is the whole gesture: the
    amplitude holds while the FILTER shuts, which is why a synth bass note has a
    bright attack and a round body without getting quieter. That is
    harmonic_decay_db running well ahead of decay_db -- the fundamental sits
    near 4 dB/s and the eighth harmonic near 30, so the note keeps its weight
    while the top of it disappears.

    ONE OSCILLATOR, AND NO DETUNE, which is the opposite of the synth brass and
    is deliberate. Two oscillators a few cents apart beat at a rate proportional
    to frequency: at C3 that is a shimmer, and at E1 it is 0.2 Hz -- a slow
    wobble in and out of phase across a whole bar, which in the bass reads as
    the part being out of tune rather than as thickness. Synth bass patches are
    voiced tight for exactly that reason, and where they do use a second
    oscillator it is an OCTAVE down, not a detune, because an octave does not
    beat.

    NOT TUNED ONTO THE ELECTRIC BASSES. GM 33-37 are modelled instruments in
    this renderer, so resemblance would be redundancy -- the lesson the synth
    brass taught the hard way. A synth bass is not a bass guitar with a filter:
    it has no pluck comb, no string body, no fret, and its spectrum falls
    monotonically from a waveform rather than being shaped by a box.
    """
    damper_pedal = True         # the gate, not a felt -- see SynthProperties
    max_harmonic = 40

    # The pluck: the filter shuts fast while the amplitude holds.
    decay_db = 0.5
    harmonic_decay_db = 3.5
    harmonic_decay_dampening = 0.0
    sustain_level = 0.86

    attack_time = 0.006         # a synth bass speaks at once
    speech_cycles = 0.0
    chiff_volume = 0.0

    # Tight: no second oscillator. See the docstring.
    def unison_voices(self, frequency, harmonic, harmonic_decay):
        return []

    formants = ((420.0, 260.0, 1.30),)
    formant_floor = 0.08
    bore_corner_hz = 1600.0
    bore_order = 2.0
    bell_cutoff_hz = 0.0
    bell_order = 1.0

    initial_gain = 0.02         # balance-normalised per subclass below

    def harmonic_volume(self, harmonic):
        # Hand-wired, as on the voice lead and the synth brass: the sawtooth
        # parent returns gain/n directly and never reaches bore_gain, which is
        # the hook FormantBody works through.
        if self.max_harmonic and harmonic > self.max_harmonic:
            return 0.0
        f0 = self.frequency_x * (2.0 ** self.octave_position)
        return (self.gain / harmonic) * self.bore_gain(f0 * harmonic) * self._bore_norm()


class SynthBass1Properties(SynthBassProperties):
    """GM 38. The round one: a SAWTOOTH under a low, moderately resonant filter.

    Every harmonic present at 1/n, then a cutoff low enough that only the first
    handful survive -- which is what makes it round rather than dark. The
    reading is the SC-55's, where 38 is the warm analogue bass and 39 the
    brighter, harder one; General MIDI names them and specifies nothing.
    """
    formants = ((380.0, 240.0, 1.25),)
    bore_corner_hz = 1400.0
    decay_db = 0.5
    harmonic_decay_db = 3.2
    # Balance-normalised against the fingered electric bass (GM 33) on the same
    # passage in the same room -- the family's representative, itself anchored
    # to the measured nylon guitar.
    initial_gain = 0.126117


class SynthBass2Properties(SynthBassProperties):
    """GM 39. The hard one: a SQUARE, which is hollow where a saw is full.

    The odd-only series is an exact distinction rather than a tuned one -- a
    square IS the odd harmonics at 1/n, as GM 80 is -- and it is audibly a
    different instrument from its neighbour rather than the same one brighter.
    With the cutoff higher and the resonance up, this is the aggressive synth
    bass: hollow, edged, and with more of the filter's ring in it.
    """
    odd_only = True
    formants = ((620.0, 300.0, 1.55),)
    bore_corner_hz = 2400.0
    decay_db = 0.6
    harmonic_decay_db = 4.2
    # Higher than GM 38's, because a square's absent evens take energy out that
    # the level has to make back: same passage, same anchor.
    initial_gain = 0.170884

    def harmonic_volume(self, harmonic):
        if harmonic % 2 != 1:
            return 0.0
        return super().harmonic_volume(harmonic)


class SynthBrassProperties(FormantBody, SawtoothSynthProperties):
    """GM 62 and 63. A SAWTOOTH THROUGH A FILTER ENVELOPE -- not a brass instrument.

    Both programs sat on BrassProperties, the abstract acoustic brass base. That
    class carries a bore, a register centre, an effort tilt and the intonation
    tendencies of a played horn, and a synthesiser has none of those: the same
    category error as the synth leads rendering through an organ pipe, in the
    family next door.

    WHAT A SYNTH BRASS PATCH ACTUALLY IS, on every machine that made the sound
    famous: one or two sawtooth oscillators, a resonant low-pass, and an
    envelope on the FILTER rather than on the amplitude. The filter opens fast,
    falls back to a sustain point, and that sweep is the whole character -- it is
    why the patch reads as "brassy" without any brass in it, because a real horn
    also gets brighter as it is pushed and settles as the note steadies.

    AND THE FILTER ENVELOPE NEEDED NO MACHINERY, for the reason the leads
    established: a low-pass closing is upper partials dying faster than lower
    ones, which is harmonic_decay_db, and a front that blooms and settles is
    decay_db against sustain_level. Those three numbers ARE the filter envelope.
    The acoustic brass base was already using them for the same purpose, which is
    why it was a passable stand-in and still the wrong class.

    TWO OSCILLATORS, DETUNED BY A FIXED AMOUNT. The thickness of a synth brass
    patch is a second saw a few cents off, and it is a KNOB: the same offset on
    every note, every time. That is a different thing from a piano's unisons,
    which are meant to be identical and are imperfectly tuned (random, per note),
    and from a section, which is many players who cannot agree (random, per
    player). It is the accordion's musette argument again -- systematic, not
    drawn -- so it does not reuse either of their mechanisms.
    """
    # The oscillator: every harmonic at 1/n, exactly, as its parent. The colour
    # comes from the envelope, not from the waveform.
    max_harmonic = 40

    # THE FILTER ENVELOPE. decay_db is how far the front blooms above the
    # sustain and harmonic_decay_db how much faster the top of the spectrum
    # gets there -- a sweep down through the series rather than a level change.
    decay_db = 16.0
    harmonic_decay_db = 5.5
    harmonic_decay_dampening = 0.0
    sustain_level = 0.62

    # The onset. A synth brass patch does not speak like a horn, it RAMPS --
    # the filter and the amplifier open together over a fixed time that has
    # nothing to do with the note's wavelength, which is why speech_cycles
    # stays zero here where every acoustic wind voice sets it.
    attack_time = 0.018
    speech_cycles = 0.0
    chiff_volume = 0.0

    detune_cents = 7.0          # the second oscillator, a knob and not a spread
    detune_gain = 0.80

    # A RESONANCE, NOT A BODY. Ben, on an earlier version of these two that had
    # been tuned until GM 63 sat within 1.7 dB of the measured horn: "Is it
    # imitating the instrument, or just mapping directly to it? The proper
    # trumpet and horn patches are literally synthesized, after all."
    #
    # Which is exactly right and is the trap this family sets. GM 56 and GM 60
    # in this renderer are not samples -- they are additive models with their own
    # formants and envelopes. So "make GM 63 sound like a horn" collapses into
    # "make GM 63 BE the horn", and a check that it resembles one is a check
    # that it has become redundant. The first version made 62 and 63 identical
    # to each other; tuning them onto the acoustic voices merely moved the
    # collision.
    #
    # WHAT A SYNTH BRASS ACTUALLY IS is a caricature, and its character lives in
    # the ways it FAILS to be brass. A bore-shaped spectrum RISES to a formant
    # -- the Iowa trumpet puts h4 about 19 dB above its fundamental -- where a
    # sawtooth falls monotonically and a filter can only carve a bump into that
    # fall. The filter sits where the knob is instead of moving with register or
    # dynamic. Two oscillators beat at a fixed rate where a section's spread is
    # random. None of that is a deficiency to be tuned away; it is the sound.
    #
    # So the resonances below are NARROW and STRONG -- a filter with its Q up,
    # which is what the machines did -- rather than the broad gentle colour a
    # body gives. The trumpet and horn centres set which DIRECTION each preset
    # leans, and nothing is tuned toward matching them.
    #
    # THE FILTER ITSELF, not just its envelope. A first pass gave these voices
    # the sweep (decay_db, harmonic_decay_db) and left the spectrum a bare 1/n
    # saw -- which is a synth brass patch with the resonance turned off, and
    # measured, it made GM 62 and GM 63 spectrally IDENTICAL, differing only in
    # an envelope the audio would not clearly show. The bite of the sound is the
    # RESONANT PEAK at the cutoff, and a peak is what FormantBody makes.
    #
    # Which is the same thing a real horn's bell does -- measured, the trumpet
    # puts h4 to h6 about 19 dB ABOVE its fundamental, and that peak is why a
    # saw with a resonant filter reads as brass at all while a bare saw does not.
    formants = ((1800.0, 1100.0, 0.85),)
    formant_floor = 0.10
    bore_corner_hz = 3200.0     # the low-pass above the resonance
    bore_order = 2.0
    bell_cutoff_hz = 0.0
    bell_order = 1.0

    initial_gain = 0.02         # balance-normalised per subclass below

    def harmonic_volume(self, harmonic):
        # WIRED BY HAND, because SawtoothSynthProperties overrides
        # harmonic_volume to return gain/n directly and so never reaches
        # bore_gain -- which is the hook FormantBody works through. Inheriting
        # the mixin alone does nothing, exactly as it did nothing on the voice
        # lead until this was written there. Inheriting a body is not the same
        # as sounding through it.
        if self.max_harmonic and harmonic > self.max_harmonic:
            return 0.0
        f0 = self.frequency_x * (2.0 ** self.octave_position)
        return (self.gain / harmonic) * self.bore_gain(f0 * harmonic) * self._bore_norm()

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        if self.detune_gain <= 0.0:
            return []
        return [(self.detune_gain, 0.0,
                 2.0 ** (self.detune_cents / 1200.0) - 1.0, harmonic_decay, 0.0)]


class SynthBrass1Properties(SynthBrassProperties):
    """GM 62. The TRUMPET reading: bright and hard.

    General MIDI names two synth brasses and distinguishes them nowhere, so the
    reading is the Roland SC-55's, which is what the files were written for: 62
    is the bright aggressive stab and 63 the softer, slower pad. They differ in
    the ENVELOPE, which is correct -- on the machines these imitate, that is
    mostly what the two presets did differ in.
    """
    # THE TRUMPET READING. Ben's: rather than two cutoffs an octave apart chosen
    # for contrast, make one patch imitate a TRUMPET and the other a HORN --
    # which is bright-and-hard against soft-and-slow, and is what arrangers
    # actually reach for these two presets to do. It replaces two invented
    # numbers with two measured ones.
    #
    # Measured on the Iowa trumpet, its spectral peak sits at 1308, 1308 and
    # 1570 Hz at C3, C4 and C5 -- very nearly FIXED against pitch, which is what
    # a body resonance is and confirms modelling it as a formant rather than as
    # a tilt. 1400 Hz is the middle of that. Its envelope is the trumpet's too:
    # decay 20, sustain 0.58, harmonic decay 5.5.
    attack_time = 0.014
    decay_db = 20.0
    harmonic_decay_db = 5.5
    sustain_level = 0.58
    detune_cents = 6.0
    formants = ((1400.0, 480.0, 1.60),)
    formant_floor = 0.07
    bore_corner_hz = 3000.0
    # Balance-normalised against the MEASURED trumpet (GM 56) on the same
    # passage in the same room -- this family's reference-audio member.
    initial_gain = 0.060868


class SynthBrass2Properties(SynthBrassProperties):
    """GM 63. The HORN reading: soft and slow.

    Slower and warmer is not two decisions. A filter that opens gently never
    reaches as far up the series, so the patch is darker as well as softer --
    the colour follows from the envelope rather than standing on its own, the
    same argument SlowBowedStringProperties makes about the bow.
    """
    # THE HORN READING, against GM 62's trumpet. Measured on the Iowa horn, its
    # spectral peak sits at 392, 262 and 523 Hz across C3-C5 and its centroid at
    # 382, 338, 533 -- again nearly fixed, and 420 Hz is the middle. That is
    # 3.4 times lower than the trumpet's 1400, where the two cutoffs this class
    # carried before were an invented octave apart.
    #
    # And the envelope is the horn's: decay 13 against the trumpet's 20, sustain
    # 0.70 against 0.58, harmonic decay 2.0 against 5.5. Soft and slow is not a
    # separate decision from dark -- a gentler front never drives the upper
    # partials as far, the same argument SlowBowedStringProperties makes.
    attack_time = 0.075
    decay_db = 13.0
    harmonic_decay_db = 2.0
    sustain_level = 0.70
    detune_cents = 11.0         # wider, which is where the "warm" comes from
    detune_gain = 0.88
    formants = ((420.0, 200.0, 1.30),)
    formant_floor = 0.09
    bore_corner_hz = 1500.0
    initial_gain = 0.0433277    # against the measured trumpet, as GM 62


class FifthsLeadProperties(SawtoothSynthProperties):
    """GM 86, Lead 7 (fifths): the waveform and its FIFTH, together.

    Exactly that, and exactly specifiable: a second oscillator a perfect fifth
    above, which is a frequency ratio of 3/2. Not a detune and not a chorus --
    a fixed interval, so the patch plays parallel fifths whatever is written,
    which is the whole character and the reason it is used for a certain kind
    of lead line.

    A TEMPERED FIFTH, NOT A JUST ONE. A GM synth's second oscillator is offset
    by seven SEMITONES on the keyboard, so it tracks the tuning in force rather
    than sitting at 3/2 -- and under an unequal temperament the difference is
    audible. 2^(7/12) is 1.4983, two cents under just.
    """
    fifth_gain = 0.62               # under the root, so the fifth colours it
    fifth_ratio = 2.0 ** (7.0 / 12.0)
    # Lower than its siblings because the second voice adds level: a fixed
    # interval is two oscillators, and the patch must not be louder for it.
    initial_gain = 0.04319

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        return [(self.fifth_gain, 0.0, self.fifth_ratio - 1.0, harmonic_decay, 0.0)]


class BassLeadProperties(SawtoothSynthProperties):
    """GM 87, Lead 8 (bass + lead): the waveform and an octave BELOW it.

    The other fixed-interval lead, and the reason the two sit next to each other
    in the specification. An octave is a ratio of 2 in any temperament, so unlike
    the fifth there is nothing to decide: 0.5 is 0.5.

    The lower voice carries MORE than the upper one does in GM 86, because this
    patch is meant to play its own bass line -- the name is an instruction about
    arrangement, not a colour.
    """
    bass_gain = 0.85
    bass_ratio = 0.5
    # Lower than its siblings because the second voice adds level: a fixed
    # interval is two oscillators, and the patch must not be louder for it.
    initial_gain = 0.03291

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        return [(self.bass_gain, 0.0, self.bass_ratio - 1.0, harmonic_decay, 0.0)]


# The valve is measured against the voice's own level, never a shared constant.
# The valve is measured against the voice's OWN level, never a shared constant,
# and the two move together -- raising the gain alone drives the valve harder and
# makes the voice louder AND dirtier. The electric bass taught this the hard way.
CharangLeadProperties.amp_reference = CharangLeadProperties.initial_gain * 2.0


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


class CuicaProperties(SynthProperties):
    """GM 78/79. A FRICTION drum -- the only one in the set, and it was a
    struck membrane, which is the wrong mechanism rather than the wrong size.

    NOT under PercussionProperties, whose docstring says "struck onset... fast
    decay". Nobody hits a cuica. A thin bamboo stick is tied to the INSIDE
    CENTRE of the head and the player strokes it with a damp cloth; stick-slip
    friction drives the stick longitudinally and the stick drives the head.
    Three things follow, and the old voice had none of them.

    IT IS BOWED, NOT STRUCK. "Rubbing the bamboo rod gives a primitive
    saw-toothed excitation, similar to a bowed violin string, which is connected
    to the center of a membrane which modifies and radiates the sound." So the
    drive is a sawtooth and the voice SUSTAINS while it is rubbed -- decay_db
    and harmonic_decay_db are zero, as they are on a bowed string and an organ
    pipe, and tonal_dampening is 1.0 because a sawtooth's harmonics go as 1/n.
    A struck membrane's fast decay was modelling the wrong thing entirely.

    DRIVEN AT THE CENTRE, SO MOST OF THE DRUM CANNOT SPEAK. Every membrane mode
    with an angular node -- (1,1), (2,1), (3,1) and the rest -- has a NODE at
    the centre of the head, so a centre drive cannot excite any of them. What is
    left is the axisymmetric series alone, j(0,n)/j(0,1):

        1.000   2.295   3.598   4.903   6.209

    MembraneDrumProperties hands out the full Bessel set, twelve modes including
    1.593 and 2.136, and on a cuica none of those exist.

    AND BECAUSE IT IS DRIVEN, IT MODE-LOCKS. The same argument the organ pipes
    make: a nonlinearly driven oscillator pulls its passive resonances into one
    exactly periodic waveform, so the STEADY tone is harmonic and the passive
    inharmonicity is an ONSET transient. That is why this class has no
    mode_ratios -- it would be asserting the passive modes sound forever -- and
    instead carries the departure in mode_lock_spread. Fitted against those five
    axisymmetric ratios the engine's existing law reproduces them to three
    decimal places: 2.296, 3.597, 4.905, 6.208, rms 0.0004. A cuica's onset is
    therefore a genuine squeak from a wildly inharmonic membrane settling into a
    harmonic tone, which is most of what makes it recognisable.

    THE PITCH IS THE OTHER HAND. "The pitch is increased or decreased by
    changing the pressure on the head" -- a finger pressed near the centre
    raises the tension, and a membrane's pitch goes as sqrt(T), which is
    tension_bend exactly. On every other voice here that bend is an attack
    transient nobody asked for; on a cuica it IS the instrument, which is why
    it is an order of magnitude larger and why tension_bend_slope is zero: the
    glide is a finger, not a register.

    WHICH WAY IT GLIDES IS A CHOICE, not a measurement. GM gives two notes and
    does not say what they do, so they are set to glide in OPPOSITE directions
    -- the mute rises into pitch, the open falls away from it -- which is what
    makes an alternating 78/79 figure sound like the instrument talking. Any
    real player does both on either.

    NO REFERENCE. Iowa has no cuica and no friction drum of any kind. The
    mechanism above is measured physics; the numbers below are not.
    """

    # Supplied rather than inherited. The attributes below live on
    # PluckedStringProperties, and inheriting them would mean claiming this is a
    # struck string to borrow its defaults -- which is the error being fixed.
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    plucked_harmonic = 0.0
    pluck_dampening = 1.0
    strike_point = 0.0
    strike_depth = 0.0
    odd_only = False
    harmonic_decay_dampening = 0.0
    octave_gain = 0.0
    octave_modulo = 0

    # Driven, so it rings while it is driven and not a moment longer.
    one_shot = False
    decay_db = 0.0
    harmonic_decay_db = 0.0
    attack_time = 0.018           # friction takes a moment to catch
    max_harmonic = 24
    tonal_dampening = 1.0         # a sawtooth drive: harmonics go as 1/n
    octave_dampening = 0.0

    # The passive membrane, as an ONSET departure from harmonic. Fitted to
    # j(0,n)/j(0,1) = 1, 2.295, 3.598, 4.903, 6.209 -- rms 0.0004.
    mode_lock_spread = 0.2748
    mode_lock_knee = 1.8522
    mode_lock_time = 0.060        # slower than a pipe's 0.035: a weaker drive

    # The damp cloth on the stick. Broadband, and it lasts as long as the stroke.
    chiff_volume = 0.55
    chiff_cycle = 0.9
    chiff_min_valve_time = 0.004
    chiff_max_valve_time = 0.03

    # The other hand. Open: the finger lifts, the head slackens, the pitch falls
    # away from the note. ~155 cents at full stroke.
    tension_bend = 0.095
    tension_bend_max = 0.30
    tension_bend_slope = 0.0      # a finger, not a register
    tension_settle_time = 0.13
    tension_settle_cutoff = 0.9

    initial_gain = 1.0 / 9.0


class MuteCuicaProperties(CuicaProperties):
    """GM 78. The same drum with the finger pressed: tighter, higher, shorter,
    and gliding the other way -- UP into the note as the pressure comes on."""

    tension_bend = -0.085         # starts flat and rises to pitch
    tension_settle_time = 0.10
    chiff_volume = 0.38           # the finger damps the head, and the noise with it
    tonal_dampening = 1.25        # and takes the top off


class CowbellProperties(MetalPercussionProperties):
    """GM 56. A folded steel plate, not a bell.

    It was a stretched harmonic series -- mode 2 at 2.05x, mode 3 at 3.1x --
    which is a pitched note with a bit of edge on it. A cowbell is a sheet bent
    into a box and welded: its walls are plates, its modes are plate modes, and
    they have no musical relationship to each other. That clash is the whole
    character -- it is why a cowbell cuts through a mix at any pitch and why two
    of them a semitone apart still sound like "a cowbell" rather than two notes.

    Two strong low partials about a fifth apart, then a clangy inharmonic spray
    thinning upward.

    JUDGEMENT, NOT MEASUREMENT. Iowa has no cowbell, and unlike the agogos there
    is no near relative in the collection to borrow from -- a crotale and a
    cowbell are not the same body in any useful sense. What IS defensible is
    that the ratios are inharmonic: a folded plate cannot produce a harmonic
    series, whatever the exact numbers turn out to be.
    """
    mode_ratios = (1.0000, 1.4820, 2.1470, 2.6180, 3.3110, 3.9400, 4.6170, 5.4020,
                   6.1150, 7.0330, 8.2160, 9.4700)
    mode_gains  = (1.0000, 0.7600, 0.4800, 0.3600, 0.2500, 0.2000, 0.1500, 0.1200,
                   0.1000, 0.0800, 0.0650, 0.0500)
    max_harmonic = 12
    initial_gain = 0.392225  # holds the level it had before the rebuild
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False


class SteelPanProperties(MetalPercussionProperties):
    """GM 114. A Caribbean steelpan: a tuned dish hammered into an oil drum.

    ASSERTION, NOT MEASUREMENT, and flagged as such throughout. Neither
    reference collection has one -- Iowa's percussion is marimba, xylophone,
    vibraphone and bells, and VCSL's Struck Idiophones has forty-one entries
    including anvils, brake drums and slit drums but no steel pan. A CC0
    recording exists on Freesound and has not been looked at yet. So this is
    built from the instrument's design and labelled the way the toms are:
    the ratios are physics, the gains are judgement.

    THE ONE THING THAT IS REALLY PHYSICS IS THE TUNING, and it is unusual
    enough to be worth stating plainly: a steelpan's overtones are HARMONIC BY
    INTENTION. The panmaker hammers each dished note area until its principal
    modes sit at the fundamental, the OCTAVE and the TWELFTH -- 1 : 2 : 3 --
    and checks them by ear one at a time. That is a design intention, not an
    emergent property of the shape, and it is the whole reason a steelpan
    sounds sweet and pitched where a gong, which is the same steel and nearly
    the same geometry, sounds like a gong. It is also why a mode SET is the
    right shape for this voice and a harmonic series with a comb is not: the
    instrument's maker put the modes where they are.

    THE FUNDAMENTAL DOMINATES, and I guessed the opposite. The first version
    of this class asserted that "the octave is nearly as loud as the
    fundamental, which is where the instrument's brightness comes from" and put
    it 1.9 dB down. Measured afterwards on 26 single-note strikes from a CC0
    recording, the octave is **29 dB** down and the twelfth **37** -- and the
    fundamental is the strongest peak in 20 of 20 strikes where all three modes
    could be read. The tuned modes are exactly where the maker put them and
    they are QUIET; the instrument is strongly fundamental-dominated, and its
    brightness is not where I said it was.

    Not an envelope effect either, which was the obvious escape: the upper
    modes are 24-30 dB down in every window from the first 80 ms to 1.5 s, so
    they are not strong in the attack and fading.

    ABOVE THE TUNED THREE, NOTHING IS TUNED -- and that part held up. Pooling
    128 partials above 3.2x from those 26 strikes, they spread from 3.2 to 9.2
    with no tuning to speak of, and sit at a median of -43 dB. So the SHAPE of
    the assertion was right and its LEVEL was not: the ratios below stay
    placeholders, still deliberately non-integer and still imprecise, but their
    gains are now the measured -43 rather than the -16 to -31 I invented.

    WHAT IS NOT MODELLED, and both are real:

      - SYMPATHETIC COUPLING, and the recording says how much: across 40
        isolated strikes, a median of 23% of the peak energy is NOT a harmonic
        of the note struck. It shows up as partials at 0.75, 0.80, 1.33, 1.50
        of the fundamental -- fourths, thirds and fifths, which are musical
        intervals and not modes, because they are the neighbouring note areas
        answering through the shared steel. A quarter of what you hear is
        notes nobody hit, and this engine has no cross-note coupling at all.
      - THE BLOOM'S SIZE. Thin steel struck hard is nonlinear and the pitch
        moves as the note settles. The DIRECTION is now argued below and is
        not a guess; the magnitude is, because the recording cannot resolve it
        (see tension_bend).

    RANGE. A tenor pan runs roughly C4-E6 and the lower pans are separate
    instruments with fewer tuned modes per note. Played far outside that this
    is extrapolation, like every other voice here whose reference covers one
    octave.
    """
    # A CURVED PLATE BENDS FLAT, WHERE A STRING BENDS SHARP. A string and a
    # drumhead are tuned BY tension, so striking them raises it and the pitch
    # blooms sharp. A pan note is neither: it is a shallow curved shell, and a
    # shallow shell's nonlinearity is dominated by a QUADRATIC term that comes
    # from its curvature rather than the cubic stretching term a flat plate has.
    # In the amplitude-frequency relation the quadratic coefficient enters
    # SQUARED with a minus sign,
    #
    #     w(a) = w0 * [1 + (3*a3/(8*w0^2) - 5*a2^2/(12*w0^4)) * a^2]
    #
    # so curvature ALWAYS softens, whatever its sign, while stretching hardens.
    # The pan is curvature-dominated -- which is not an assumption here, it is
    # the reason this class exists: the maker tunes 1:2:3 precisely BECAUSE the
    # quadratic term pumps energy from the fundamental into 2f and 3f. A voice
    # cannot claim that tuning and then claim a hardening nonlinearity.
    #
    # SO THE SIGN IS ARGUED AND THE MAGNITUDE IS ASSERTED, and the difference
    # matters. I tried to measure it off Freesound 742254 and could not: a pan's
    # fundamental is beaten on continuously by the neighbouring note areas this
    # very class models as sympathetic responders -- measured, D4 and F#4 ring
    # 36-42 Hz from a struck E4 and sometimes only 2.3 dB down -- so its
    # instantaneous frequency wanders several cents at all times. Averaged over
    # 24 isolated strikes the attack sat at -1.4 cents with a bootstrap 95%
    # interval of -6.4 to +4.0, and splitting by strike force gave +3.0, +2.2
    # and -9.2 cents with a correlation of -0.30. That is not a small effect
    # measured imprecisely; it is no measurement at all.
    #
    # -0.004 is therefore deliberately conservative: about 7 cents at full
    # velocity, comfortably inside what the recording could not have seen, and
    # in the direction the shell says. Half of what the 17" crash carries.
    tension_bend = -0.004
    tension_settle_time = 0.06
    tension_settle_cutoff = 0.5

    # 1 : 2 : 3 is the maker's tuning, and MEASURED at 1.9978 and 2.9972 --
    # two cents flat of an exact octave and twelfth, across 26 strikes. The
    # rest are placeholders; see above.
    mode_ratios = (1.000, 2.000, 3.000, 3.92, 4.63, 5.41, 6.28, 7.35, 8.61)
    # MEASURED, and nothing like what this class first asserted. Octave -29 dB
    # (10th-90th percentile -36 to -16), twelfth -37 (-48 to -27), everything
    # above -43. The spread is wide because a pan's note areas differ and
    # because this is one instrument, one microphone and one player.
    mode_gains = (1.000, 0.036, 0.014, 0.007, 0.007, 0.007, 0.007, 0.007, 0.007)

    # A TUNED MODE SET MUST NOT ALSO BE STRETCHED, and this class was the only
    # one in the file that got that wrong. MetalPercussionProperties carries a
    # stiffness term (20x the base coefficient) because its voices -- cowbell,
    # triangle, agogo -- have no mode set and need their inharmonicity from
    # somewhere. This one has a mode set, and a very particular one: the whole
    # point is that a panmaker put the modes at 1 : 2 : 3 by hand.
    #
    # Inherited, it rendered them at 1.000, 2.078 and 3.310 -- the octave 66
    # cents sharp and the twelfth 170 -- so the voice shipped claiming a tuning
    # confirmed to two cents while the renderer was pulling it a sixth of a
    # semitone out. Every other mode_ratios voice in this file (toms, crotale,
    # timpani, snare, kick) already sets this to zero; this one now does too.
    #
    # The selftest was no help because it checked mode_ratio(), which is the
    # INTENT, and the stretch happens downstream of it. It now checks where the
    # partials land.
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False

    # Thin steel, lightly damped, and nothing touching it: a pan rings for
    # seconds where a cowbell does not. The upper modes go first, as they do
    # on anything struck.
    # JUDGEMENT, and the SECOND thing a recording should replace after the
    # untuned ratios. one_shot means note-off is ignored, so this alone decides
    # how long a note lives.
    #
    # It is not, as I first assumed, what decides whether a fast run turns to
    # mush -- measured on a fifteen-note run at 150 bpm, the buildup from the
    # first note to the last is +7.7 dB at 2.0 and +7.1 dB at both 3.0 and
    # 6.0. Over a second and a half the decay barely enters into it; that
    # buildup is simply what a ringing instrument does, and a pan does wash.
    # What the number really sets is RING LENGTH: 12.5 s to -40 dB at 2.0,
    # 9.5 at 3.0, 5.6 at 6.0. A tenor pan rings for seconds and not for ten of
    # them, so this is 5.0, which is 6.5 s.
    decay_db = 5.0
    harmonic_decay_db = 1.2
    harmonic_decay_dampening = 0.15

    # Balance is a guess like the rest; a pan is a loud instrument outdoors
    # and this sits it with the other struck metal rather than over it.
    initial_gain = MetalPercussionProperties.initial_gain

    # SYMPATHETIC RESONANCE: the measured 23%. A pan is ONE SHEET of steel, so
    # its note areas are not separate oscillators loosely coupled -- they are
    # regions of the same plate, and a strike kicks all of them mechanically.
    # That is `contact`, and the recording forced the choice: at this voice's
    # Q of 2300 a coincidence model answers only at exact octaves, giving the
    # fifth 0.0000024 against the octave's 0.0071, where the recording shows a
    # broad spread with the fifth at 20% and a major second at 27%.
    sympathetic_mode = 'contact'
    # CALIBRATED against the recording's 23%: modelled 23%, real 23%.
    #
    # AND THE SHAPE IS BETTER THAN THE RAW HISTOGRAM SUGGESTED, because most of
    # what disagreed with it was not resonance at all. A sounding neighbour is
    # a NOTE, so it must carry its own tuned octave and twelfth -- 1:2:3 is
    # what a pan note IS. Testing every non-harmonic partial for that:
    #
    #     P4   76% carry their own octave, 84% their own twelfth, -29.5 dB
    #     P5   74%                         54%                    -25.7 dB
    #     M2   58%                         32%                    -32.6 dB
    #     m2    3%                         25%                    -37.8 dB
    #     TT    4%                          0%                    -37.1 dB
    #     m3   11%                         22%                    -39.9 dB
    #
    # The fourth and fifth behave like notes; the semitone, tritone and minor
    # third do not, and are 10 dB quieter besides -- peak-picking noise that
    # the raw histogram was counting as coupling. So the real neighbours are
    # exactly ONE STEP round the cycle of fifths, which is what this model
    # says, and the earlier worry that it over-weighted them came from a
    # contaminated target rather than from the model.
    #
    # What one recording of one pan cannot settle is the finer distribution:
    # M2 against M6 against M7 moves a lot with how the analysis is sliced. It
    # is not fitted.
    sympathetic_gain = 0.23
    sympathetic_falloff = 2.0    # dB per step round the cycle of fifths
    sympathetic_span = 19
    sympathetic_max = 14         # far enough round the cycle to reach M2
    sympathetic_floor = 0.01


class AgogoProperties(MetalPercussionProperties):
    """GM 67 and 68: the two bells of an agogo.

    They were a stretched harmonic series -- mode 2 at 2.05x and mode 3 at 3.1x,
    which is very nearly harmonic and so very nearly a pitched note. A small
    struck bronze bell is not that: its partials crowd the octave and beat.

    NO AGOGO IN THE COLLECTION, so this borrows the CROTALE's measured set --
    the nearest measured relative, small struck bronze with the same octave
    cluster, twenty-five takes behind it. It is a transplant and not a
    measurement of an agogo: a crotale is a thick flat disc where an agogo bell
    is a cone, and their modes will not be identical. It is a far better
    starting point than a harmonic series, and it is labelled for what it is.

    ONE INSTRUMENT, TWO BELLS: 67 and 68 are the high and low bells of the same
    handle, so they share this class and differ in base frequency and ring --
    the pattern the hats, the ride bell, the triangle and the whistles follow.
    The interval between them is left where it was: nothing measured it.
    """
    mode_ratios = (1.0000, 2.0059, 2.0578, 2.1324, 3.0606, 3.5218, 4.0912)
    mode_gains  = (0.4372, 0.1309, 0.8323, 0.4194, 0.0168, 0.2867, 0.0100)
    max_harmonic = 7
    initial_gain = 0.759108  # holds the level it had before the rebuild
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False


class RattleProperties(NoisyPercussionMixin, PercussionProperties):
    """One impact of a rattle: a seed on a gourd, a steel bead on a cylinder.

    The three rattles kept NoiseDrumProperties when their STRUCTURE was fixed --
    a burst of impacts instead of one hit -- and that class is a stretched
    harmonic series on a tuned base. So every seed struck the same note, forty
    times a shake, and the ear integrates a repeated identical spectrum into a
    pitch however flat any single window looks. Ben: "The Maracas seem to have
    too much tonality."

    Two things fix it and both are what the instrument does. The body becomes a
    dense inharmonic set with a broad hump and no dominant mode -- a click, not
    a note. And the impacts stop being identical: real seeds hit different parts
    of the gourd with different force, so each stroke now carries its own pitch
    scale (see PERCUSSION_RATTLE), which is the same per-stroke mechanism the
    bell tree uses to sweep, scattered instead of swept.

    NO REFERENCE: Iowa has no rattle of any kind.
    """
    one_shot = True
    release_floor_db = -50.0
    decay_db = 20.0
    harmonic_decay_db = 2.0
    harmonic_decay_dampening = 0.0
    tonal_dampening = 0.15
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    chiff_volume = 2.0
    chiff_cycle = 0.95
    chiff_release = 0.0
    sustain_jitter = 1.0
    initial_gain = 1.0 / 11.0
    attack_time = 0.0015
    mode_ratios = (1.0000, 1.1480, 1.2284, 1.3141, 1.4054, 1.6131, 1.7263, 1.8468,
                   1.9752, 2.2667, 2.4258, 2.5953, 2.7759, 3.1851, 3.4088, 3.6472,
                   3.9012, 4.4756, 4.7901, 5.1254, 5.4826, 6.2888, 6.7311, 7.2026,
                   7.7049, 8.2399, 9.4585, 10.1215, 10.8280, 11.5804, 13.2908, 14.2232,
                   15.2168, 16.2751, 18.6758, 19.9869, 21.3842, 22.8727, 26.2423, 28.0860,
                   30.0511, 32.1445, 36.8741, 39.4667)
    mode_gains  = (0.4385, 0.4597, 0.4830, 0.5083, 0.5356, 0.5646, 0.5953, 0.6275,
                   0.6607, 0.6947, 0.7290, 0.7634, 0.7971, 0.8299, 0.8611, 0.8902,
                   0.9168, 0.9404, 0.9605, 0.9768, 0.9890, 0.9968, 1.0000, 0.9987,
                   0.9927, 0.9824, 0.9678, 0.9492, 0.9270, 0.9016, 0.8735, 0.8431,
                   0.8109, 0.7775, 0.7433, 0.7089, 0.6747, 0.6411, 0.6085, 0.5772,
                   0.5474, 0.5194, 0.4933, 0.4691)
    max_harmonic = 44


class CabasaProperties(RattleProperties):
    """GM 69. Steel ball chain twisted against a ridged metal cylinder --
    brighter and harder than a gourd, with the beads audible individually.
    Its hump sits an octave above the maracas'."""
    mode_ratios = (1.0000, 1.1454, 1.2228, 1.3052, 1.3927, 1.5949, 1.7028, 1.8176,
                   1.9395, 2.2207, 2.3712, 2.5311, 2.7010, 3.0922, 3.3018, 3.5247,
                   3.7615, 4.3055, 4.5976, 4.9082, 5.2383, 5.9950, 6.4020, 6.8348,
                   7.2949, 7.7836, 8.9144, 9.5176, 10.1587, 10.8399, 12.4126, 13.2532,
                   14.1467, 15.0962, 17.2836, 18.4548, 19.7001, 21.0234, 24.0657, 25.6978,
                   27.4332, 29.2775, 33.5088, 35.7832)
    mode_gains  = (0.3464, 0.3563, 0.3678, 0.3811, 0.3963, 0.4135, 0.4329, 0.4545,
                   0.4783, 0.5043, 0.5324, 0.5625, 0.5945, 0.6280, 0.6626, 0.6981,
                   0.7340, 0.7697, 0.8048, 0.8386, 0.8706, 0.9001, 0.9268, 0.9499,
                   0.9691, 0.9840, 0.9942, 0.9996, 1.0000, 0.9954, 0.9859, 0.9718,
                   0.9532, 0.9307, 0.9046, 0.8754, 0.8438, 0.8102, 0.7754, 0.7397,
                   0.7038, 0.6682, 0.6334, 0.5997)
    max_harmonic = 44


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
    # a time-keeping click belongs. Part of 1/5.0 was paying for a broadband
    # wash that is now gone -- removing it dropped this voice 4.59 dB -- so the
    # trim comes back to 1/2.95 and the balance against the kit is preserved.
    initial_gain = 1.0 / 2.95
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
    # MEASURED, and this was the "static" on every clave and guiro ridge.
    # Spectral flatness of one stroke (1.0 = white noise, 0 = pure tone):
    #
    #     Iowa clave      0.0002        ours at chiff 0.65   0.2442
    #     Iowa woodblock  0.0000        ours at chiff 0.10   0.0158
    #     Iowa guiro      0.0044        ours now             0.0010
    #
    # Struck wood is a PITCHED BOX, not a wash. The old 0.65 with a full
    # sustain_jitter made every stroke a burst of broadband noise -- three
    # orders of magnitude flatter than the recording -- and on a guiro, where a
    # single note is nine of those strokes in a tenth of a second, it read as
    # static rather than as a scrape. Reducing the partial count does not help:
    # the wash, not the harmonic stack, is what was flat.
    #
    # A little is kept for the stick's contact transient, which is real.
    chiff_volume = 0.10
    chiff_cycle = 0.5
    chiff_release = 0.0
    # The noise must persist through the (very short) ring, not just the onset --
    # a cymbal does this too. With noise only at the attack, what was left after
    # the first few milliseconds was a handful of decaying sinusoids, and that is
    # a pitch no matter how quickly it dies.
    # A struck body is a DECAYING RESONANCE, not a breath that keeps moving.
    # 1.0 kept the noise alive through the whole stroke.
    sustain_jitter = 0.20
    chiff_min_valve_time = 0.001
    chiff_max_valve_time = 0.004
    one_shot = True                 # a struck block ignores note-off; it is already gone
    release_floor_db = -50.0
    decay_db = 260.0                # ~0.23 s to -60 dB (metal percussion: 10.9 s)
    harmonic_decay_db = 40.0        # the upper modes go first: a tock, not a ring
    harmonic_decay_dampening = 0.0



class ClavesProperties(WoodPercussionProperties):
    """GM 75. MEASURED: Iowa hp_clave1.mf.

    A clave is a solid wooden cylinder and rings as a BAR, not as a harmonic
    series -- 1 : 1.08 : 1.14 : 1.23 : 1.35 : 1.66 : 1.78 : 2.61 : 2.95 : 8.84,
    with the loudest mode the seventh at 1612 Hz rather than the lowest. That
    cluster of near-unison low modes is what gives a clave its crack: they beat
    against each other for the few milliseconds they last.

    WEAK EVIDENCE, and marked as such. Iowa has three clave takes and their mode
    sets do NOT reproduce -- f0 comes out 905, 635 and 728 Hz with different
    ratios -- so they are three different pairs rather than three strikes of one,
    and there is nothing to cross-check against. This is take 1 alone.
    """
    mode_ratios = (1.0000, 1.1647, 1.2954, 1.5972, 1.8736, 2.0788, 2.2994, 2.4965,
                   2.6695, 2.7878, 3.0396, 3.1742, 3.3511, 3.5265, 3.7414, 3.8866,
                   4.3605, 4.5330, 5.2271, 5.7371, 6.4959, 7.4619, 8.5071, 9.9413,
                   11.3101, 12.9919, 14.9237, 17.1429, 19.6237, 22.4635, 25.7143)
    mode_gains = (0.01401, 0.01295, 0.24615, 0.09827, 0.01576, 0.01367, 1.00000, 0.05383,
                   0.02522, 0.02902, 0.02165, 0.02033, 0.03318, 0.01823, 0.02411, 0.02788,
                   0.04665, 0.01894, 0.02059, 0.05080, 0.01358, 0.01390, 0.02288, 0.06846,
                   0.03515, 0.03829, 0.03876, 0.04046, 0.09581, 0.09151, 0.11902)
    max_harmonic = 31
    initial_gain = 0.635204  # holds the level this voice had before it was measured
    tonal_dampening = 0.15
    hf_corner_hz = 45000.0
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False


class WoodBlockHiProperties(WoodPercussionProperties):
    """GM 76. MEASURED: Iowa hp_5.5wb.mf, a 5.5 inch block.

    A woodblock is a HOLLOW BOX, so unlike the clave it is dominated by one
    resonance -- the cavity -- with a couple of weak body modes above it. Four
    modes survive at all once anything under 2% of the peak is dropped, and the
    top two are 0.11 and 0.03. That sparseness is the instrument, not a failure
    to measure: it is why a woodblock has a definite pitch where a clave has a
    crack.

    It is also the SHORTEST sound in the collection -- 40 dB down in 26 ms.
    """
    mode_ratios = (1.0000, 1.1855, 1.3807, 1.6477, 1.8728, 2.1811, 2.5055, 2.8780,
                   3.3060, 3.7976, 4.3623, 5.0109, 5.6844, 6.5303, 7.5951, 9.0753,
                   9.6018, 9.9090, 10.1859, 12.4927, 14.3410, 16.9031, 17.9985, 19.3386,
                   19.8371, 21.6776, 22.9599, 24.5616, 25.5695)
    mode_gains = (0.00012, 0.00000, 0.00000, 0.00000, 0.00000, 1.00000, 0.38541, 0.02482,
                   0.01355, 0.00885, 0.01412, 0.05924, 0.00995, 0.00614, 0.00934, 0.00002,
                   0.00000, 0.00000, 0.00001, 0.00001, 0.00001, 0.00000, 0.00000, 0.00000,
                   0.00000, 0.00000, 0.00000, 0.00000, 0.00000)
    max_harmonic = 29
    initial_gain = 2.881338  # holds the level this voice had before it was measured
    tonal_dampening = 0.15
    hf_corner_hz = 45000.0
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False


class WoodBlockLoProperties(WoodBlockHiProperties):
    """GM 77. MEASURED: Iowa hp_10wb.mf, a 10 inch block -- a different
    instrument from the 5.5, not the same one played lower, so it gets its own
    set. Two modes: the cavity at 778 Hz and one body mode 3.3 octaves up at 2%.
    """
    mode_ratios = (1.0000, 1.2206, 1.4216, 1.5415, 1.6557, 1.7790, 1.9996, 2.0835,
                   2.2150, 2.4113, 2.6830, 2.8620, 3.3010, 3.4018, 3.7452, 4.0190,
                   4.4909, 4.7413, 4.9563, 5.1804, 5.3785, 5.5774, 5.7933, 6.5065)
    mode_gains = (1.00000, 0.01062, 0.00381, 0.00093, 0.00125, 0.00064, 0.01318, 0.03928,
                   0.00179, 0.03061, 0.00097, 0.00929, 0.07052, 0.02087, 0.00180, 0.00000,
                   0.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000)
    max_harmonic = 24
    initial_gain = 0.550465  # holds the level this voice had before it was measured
    tonal_dampening = 0.15
    hf_corner_hz = 9000.0


class CastanetsProperties(WoodPercussionProperties):
    """GM 85. MEASURED: Iowa hp_castanet2.mf.

    Two shells clapping, and the spectrum says so: twelve modes packed between
    1.0 and 2.0 with the loudest at 4713 Hz, nearly two octaves above the lowest.
    The centroid is 6110 Hz -- brighter than any of the wooden voices -- which is
    the clack of shell on shell rather than a body ringing.

    Two takes, not reproducing, so this is take 2 alone.
    """
    mode_ratios = (1.0000, 1.0800, 1.3237, 1.4494, 1.6791, 1.9451, 2.2534, 2.6104,
                   3.0403, 3.5409, 3.9448, 4.3237, 4.5646, 5.1066, 5.5107, 5.7227,
                   6.6901, 7.3810, 8.4786, 9.7393, 11.1875, 12.8511, 13.9159, 15.1619,
                   17.2396, 18.0088, 19.0251, 19.7001, 22.3751, 25.7022, 30.4768, 31.4529,
                   33.7152, 41.1656, 43.4768, 51.2261, 58.6393, 67.1252)
    mode_gains = (0.00303, 0.00165, 0.00265, 0.00072, 0.00246, 0.00192, 0.00186, 0.00154,
                   0.00317, 0.00502, 0.00561, 0.00588, 0.00854, 0.00907, 0.00932, 0.06393,
                   0.06485, 0.01219, 0.01042, 0.00812, 0.01035, 0.03273, 0.05509, 0.04268,
                   0.18240, 0.09581, 0.15768, 0.05541, 0.04480, 0.11795, 0.25493, 0.21793,
                   0.24209, 0.17305, 0.16562, 1.00000, 0.57068, 0.70579)
    max_harmonic = 38
    initial_gain = 2.704684  # holds the level this voice had before it was measured
    tonal_dampening = 0.15
    hf_corner_hz = 45000.0
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False


class TriangleProperties(MetalPercussionProperties):
    """GM 80 and 81. MEASURED: Iowa hp_8triangle.mf.

    A bent steel rod, and the best-measured of the hand percussion: sixteen modes
    from 1519 Hz up, the loudest at 5585, a centroid of 6417 Hz and a ring of
    4.36 s to -40 dB. Nothing about that is a harmonic series, which is what this
    voice carried -- a stretched one at inharmonicity 0.026.

    A triangle has no strong low mode at all. Its lowest is 16% of the loudest,
    and the ear hears the cluster around 5-7 kHz, which is why a triangle cuts
    through an orchestra at any dynamic and why it has no definite pitch.

    ONE BAR, TWO ARTICULATIONS -- the pattern the hi-hats and the ride bell
    already follow. GM 80 is the triangle held (muted) and 81 is it left to ring;
    same modes, and PERCUSSION_RING carries the difference.
    """
    mode_ratios = (1.0000, 1.1457, 1.2369, 1.3343, 1.5540, 1.8634, 1.9215, 2.1352,
                   2.4214, 2.7814, 3.1950, 3.4804, 3.9433, 4.2158, 4.4908, 4.8427,
                   5.6643, 5.9054, 6.1589, 7.3402, 8.0312, 9.6922, 10.0359, 10.9305,
                   11.6265, 12.7800, 14.6803, 15.6988, 17.5721, 18.2799, 20.7863, 22.0972,
                   25.2949)
    mode_gains = (0.00130, 0.00021, 0.00202, 0.00022, 0.00027, 0.00740, 0.00280, 0.01500,
                   0.00021, 0.00022, 0.00020, 0.00389, 0.00871, 0.00016, 0.02641, 0.00359,
                   0.14419, 0.06561, 0.02209, 0.00144, 0.17804, 0.29622, 0.12492, 0.08790,
                   0.19017, 0.02428, 0.00636, 0.02722, 1.00000, 0.62983, 0.45883, 0.25814,
                   0.26973)
    max_harmonic = 33
    initial_gain = 1.847336  # holds the level this voice had before it was measured
    tonal_dampening = 0.15
    hf_corner_hz = 9000.0
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False


class HandClapProperties(NoiseDrumProperties):
    """GM 39. Two hands colliding: a broadband burst with no pitch in it.

    It shared NoiseDrumProperties with the rattles, on a 260 Hz base, and 16
    per cent of its energy sat in one narrow band there. A dense hump about
    1.5 kHz with a floor under it takes that to 2.6 -- below the maracas.

    THE WASH STAYS WHITE, and that is a decision rather than an oversight.
    Banding it (chiff_bandwidth) pulls the centroid from 5.5 kHz down to 1.0,
    which is closer to where a clap sounds -- but it concentrates the noise
    onto the modes and the strongest band goes back up to 7.8 per cent, which
    is the thing being fixed. A clap is two hands slapping: the noise radiates
    straight off them, it is not a plate's modes broadened by coupling, so
    white is the right model and the brightness is the price.
    """
    mode_ratios = (1.0000, 1.1276, 1.1972, 1.2708, 1.3486, 1.5205, 1.6144, 1.7137,
                   1.8187, 2.0503, 2.1769, 2.3109, 2.4527, 2.7646, 2.9355, 3.1164,
                   3.3076, 3.7279, 3.9585, 4.2025, 4.4606, 5.0267, 5.3378, 5.6670,
                   6.0153, 6.3837, 7.1977, 7.6420, 8.1120, 8.6090, 9.7056, 10.3051,
                   10.9393, 11.6101, 13.0873, 13.8961, 14.7519, 15.6571, 17.6472, 18.7384,
                   19.8932, 21.1147, 23.7956, 25.2680, 26.8261, 28.4744, 30.2175, 34.0725,
                   36.1749, 38.3991, 40.7515, 45.9447)
    mode_gains  = (0.4987, 0.5258, 0.5542, 0.5840, 0.6147, 0.6463, 0.6784, 0.7108,
                   0.7431, 0.7751, 0.8062, 0.8362, 0.8647, 0.8914, 0.9158, 0.9376,
                   0.9565, 0.9723, 0.9847, 0.9935, 0.9987, 1.0000, 0.9975, 0.9913,
                   0.9814, 0.9680, 0.9512, 0.9314, 0.9088, 0.8837, 0.8565, 0.8275,
                   0.7971, 0.7657, 0.7336, 0.7012, 0.6689, 0.6369, 0.6055, 0.5751,
                   0.5457, 0.5176, 0.4910, 0.4659, 0.4424, 0.4207, 0.4006, 0.3822,
                   0.3655, 0.3504, 0.3368, 0.3246)
    max_harmonic = 52
    # AND IT WAS SWELLING. attack_time was None, so the onset ramp came from
    # chiff_max_valve_time at 10 ms and the clap took 23.6 ms to reach its own
    # peak -- a swell, not a slap. Ben: "side stick has too much of an
    # envelope? They both do." Pinned at 2 ms it peaks at 5.1.
    attack_time = 0.002
    initial_gain = 0.069836
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False


class SideStickProperties(WoodPercussionProperties):
    """GM 37, side stick: the shaft of the stick on the RIM, no wires at all.

    It shared SnareDrumProperties, which gave a rim click a set of snare wires
    it does not have and a membrane it barely excites. A cross-stick is wood
    against wood and metal -- short, dry and pitched by the shell, much closer to
    a woodblock than to the drum it is played on. Judgement, like the snare
    above: there is no Iowa reference for any of this.
    """
    # A SIDE STICK IS A CLICK, NOT A NOTE. It carried a stretched harmonic
    # series on a 340 Hz base, and 69 per cent of its energy sat in one narrow
    # band there -- a pitched wooden note with a click on it. Ben: "side stick
    # and hand clap ... are not atonal enough."
    #
    # A stick laid across a rim and struck against it radiates from a short,
    # heavily damped contact: broad, bright, and with no mode standing out of
    # the others. So a dense set with a broad hump about 2.1 kHz and a floor
    # under it, nothing dominant, and enough wash to fill between the modes.
    # Measured, share of the energy in the strongest narrow band:
    #
    #     stretched harmonic series   69.4 per cent   centroid  470 Hz
    #     dense hump, wash 0.35        5.7            centroid 1017
    #     dense hump, wash 4.0          5.5            centroid 2002
    #
    # For scale the maracas sit at 4.1 and the closed hat at 5.6, so under about
    # six is what atonal means in this kit.
    mode_ratios = (1.0000, 1.1245, 1.1907, 1.2605, 1.3340, 1.5000, 1.5883, 1.6814,
                   1.7797, 2.0008, 2.1187, 2.2430, 2.3741, 2.6688, 2.8261, 2.9921,
                   3.1671, 3.5598, 3.7697, 3.9913, 4.2249, 4.7482, 5.0284, 5.3241,
                   5.6360, 5.9650, 6.7074, 7.1020, 7.5184, 7.9575, 8.9468, 9.4736,
                   10.0294, 10.6155, 11.9338, 12.6370, 13.3788, 14.1613, 15.9180, 16.8566,
                   17.8468, 18.8913, 21.2323, 22.4849, 23.8067, 25.2010, 26.6713, 29.9924,
                   31.7567, 33.6179, 35.5807, 40.0063)
    mode_gains  = (0.4211, 0.4445, 0.4698, 0.4970, 0.5259, 0.5564, 0.5884, 0.6215,
                   0.6555, 0.6900, 0.7247, 0.7591, 0.7929, 0.8256, 0.8567, 0.8858,
                   0.9124, 0.9362, 0.9566, 0.9734, 0.9864, 0.9952, 0.9998, 1.0000,
                   0.9959, 0.9874, 0.9749, 0.9584, 0.9383, 0.9149, 0.8886, 0.8597,
                   0.8288, 0.7962, 0.7625, 0.7281, 0.6934, 0.6588, 0.6248, 0.5916,
                   0.5595, 0.5288, 0.4997, 0.4724, 0.4469, 0.4233, 0.4016, 0.3819,
                   0.3641, 0.3481, 0.3339, 0.3213)
    max_harmonic = 52
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    chiff_volume = 4.0
    # A CLICK HAS NO ENVELOPE TO SPEAK OF. attack_time was None, which makes
    # blockrender derive the onset ramp from chiff_max_valve_time -- the trap
    # that had every crash sounding lightly touched. Here that is 4 ms and so
    # the attack was already sharp, but it is pinned rather than inherited so a
    # later change to the chiff cannot slow the click down.
    attack_time = 0.0015
    sustain_jitter = 0.30

    one_shot = True
    release_floor_db = -50.0
    decay_db = 150.0                # a click, gone in well under a tenth
    harmonic_decay_db = 30.0
    # (chiff_volume and sustain_jitter are set above, with the mode set: the
    #  wash is what fills between 52 modes so the click has no gaps to ring in)
    chiff_width = 0.012
    strike_noise_slope = 0.8
    initial_gain = 0.252227

class GuiroProperties(WoodPercussionProperties):
    """The guiro's body: struck wood, but the NOISIEST wood in the kit.

    A guiro is a notched gourd and the stick catching a notch excites the body,
    so it belongs with the claves and woodblocks rather than with the rattles --
    it was on NoiseDrumProperties and every ridge arrived as a burst of static.
    But it is measurably not as PURE as a clave either, and tuning it to the
    clave's target made it sing: nine strokes in a tenth of a second, each one a
    clean pitched tock, sum into a held tone at the body pitch.

    Spectral flatness over a whole scrape (1.0 = white noise):

        Iowa guiro    0.0036 - 0.0107      Iowa clave   0.0002
        this          0.0065               a clave here 0.0011

    so it sits where the recording does, an order of magnitude noisier than the
    clave beside it.

    WHAT IS STILL WRONG, and the knobs here cannot fix it: the recording spreads
    its energy across many modes -- the top 20 spectral bins hold about 25% of
    it -- where this holds 66%. A gourd with a slot cut in it has an irregular
    mode set, and everything in this file builds a harmonic series, stretched or
    not. Raising the inharmonicity pushes partials past Nyquist and thins the
    spectrum instead of filling it. That would want a real modal model.
    """
    # THE MEASURED MODE SET -- FROM THE FREE TAIL, NOT THE SCRAPE.
    #
    # A scrape is a periodic impulse train at about 230 Hz, so the spectrum of
    # the scrape ITSELF is the body's response convolved with a comb at
    # multiples of the ridge rate. Measuring modes there measures the comb as
    # much as the gourd: the first attempt gave 1.000 1.068 1.179 1.273 and then
    # nothing until 2.002, and that gap is where a comb null sits, not where the
    # body is quiet.
    #
    # So these come from the 50 ms of free decay AFTER the last ridge, where
    # there is no repetition to alias -- and only from modes present in BOTH
    # guiro.away and guiro.toward within 3%. A mode in one take is that scrape's
    # excitation; a mode in both is the body. 19 of 30 peaks survived that.
    mode_ratios = (1.000, 1.072, 1.235, 1.309, 1.537, 1.627, 1.710, 1.928,
                   1.958, 2.156, 2.315, 2.476, 2.619, 2.658, 2.759, 2.998,
                   3.047, 3.235, 3.395)
    mode_gains  = (0.241, 0.605, 0.090, 0.103, 0.202, 1.000, 0.185, 0.435,
                   0.356, 0.127, 0.121, 0.990, 0.190, 0.300, 0.162, 0.076,
                   0.077, 0.290, 0.084)
    max_harmonic = 19
    # 120 against the 40 it inherits from the wood, for the mode-ratio
    # correction in harmonic_decay: the guiro's 19 modes span ratios 1.00-3.40.
    # Band drift 1.53 -> 0.89 dB. The other wood has no mode set and so is not
    # affected, which is why this is set here and not on the parent.
    harmonic_decay_db = 120.0
    # the modes are measured absolutely; nothing left to stretch
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    chiff_volume = 0.20
    sustain_jitter = 0.30

class CymbalProperties(NoisyPercussionMixin, PercussionProperties):
    """Cymbal (crash, ride, splash, china): a bright broadband noise wash --
    the snare's wide-chiff noise, but a fast splash that rings out over a
    second or two instead of a punchy die. A few inharmonic modes give the
    metallic edge under the hiss."""
    initial_gain = 1.0 / 10
    max_harmonic = 80               # very bright, energy well up top
    # A MEASURED MODE SET MUST NOT BE STRETCHED AGAIN. This was 25x the 2nd-
    # harmonic coefficient, from when a cymbal was a stretched harmonic series
    # and the stretch WAS the model. Every cymbal below now carries a measured
    # mode set, and both renderers apply the stretch on top of mode_ratios --
    # so the modes were landing nowhere near where they were measured:
    #
    #     mode  60   948 Hz measured  ->  1099 Hz rendered   (x1.16)
    #     mode 120  2319 Hz           ->  4706 Hz            (x2.03)
    #     mode 171  4488 Hz           -> 21982 Hz            (x4.90)
    #     mode 200  6430 Hz           -> 57979 Hz, past Nyquist and DROPPED
    #
    # So a 300-mode crash rendered 171 of them, nothing above 4.5 kHz was a mode
    # at all, and everything up there was wash -- which is why the top could not
    # be made to decay per band, and why adding modes kept giving less than it
    # should have. HiHatProperties and RideBellProperties already set this to
    # zero, for exactly this reason; the six classes added after them did not.
    inharmonicity_coefficient = 0.0
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
    # A CYMBAL'S MODES DO NOT BEND, and this carried 0.007 -- about 16 cents at
    # ff -- on a measurement that was not measuring what it thought.
    #
    # REMEASURED on the same Iowa takes, tracking individual WELL-ISOLATED
    # partials by phase derivative (which, unlike a spectral peak, does not
    # care that the mode is decaying), across the whole family:
    #
    #     crash / chinese / splash   96 partials, 16 files   median +0.03 cents
    #     ride and ride bell         36 partials             median -0.27
    #     hi-hat                     13 partials             median +0.39
    #     orchestral clash pairs     58 partials             median +0.61
    #
    # and no correlation with how hard it was struck (-0.08), with mf and ff
    # indistinguishable. The probe was checked against planted bends first:
    # +10.0 cents came back +9.65, -10.0 came back -9.74, zero came back -0.01.
    # So the drift is bounded well under two cents where this class was
    # asserting sixteen.
    #
    # WHAT THE EARLIER NUMBER ACTUALLY CAUGHT was almost certainly the
    # SPECTRUM, not the modes. A cymbal's bright modes decay far faster than its
    # low ones, so its centroid falls 1400 to 2100 cents through the ring --
    # measured on these same files -- while every individual partial stands
    # still. That is differential decay, which harmonic_decay_db already does
    # and which needs no nonlinearity anywhere. The giveaway is that the old
    # note's three numbers disagreed in SIGN (+7.8, -2.0, -24.9): that is an
    # estimator being dragged around by neighbouring modes dying at different
    # rates, not an effect.
    #
    # AND THE SHALLOW-SHELL ARGUMENT DOES NOT RESCUE IT EITHER. A domed plate
    # should SOFTEN (see SteelPanProperties), so this value had the wrong sign
    # as well as the wrong size -- but the measurement says the honest answer is
    # neither, because the effect goes as amplitude squared and an orchestral
    # stick stroke never reaches the regime where a cymbal's nonlinearity
    # speaks. Predicting the old value was wrong is not the same as predicting
    # the right one.
    #
    # Removing it costs nothing that was doing work: the model's brightening
    # from v70 to v127 goes from +98 cents to +84.
    tension_bend = 0.0
    chiff_cycle = 0.95
    chiff_release = 0.0
    sustain_jitter = 1.0
    chiff_min_valve_time = 0.002
    chiff_max_valve_time = 0.02     # fast splash onset

    # A STRUCK CYMBAL ARRIVES AT ONCE. attack_time was left None here, which
    # makes blockrender derive the onset ramp from chiff_max_valve_time above --
    # 20 ms, chosen as a "fast splash onset" and about fifteen times too slow for
    # a stick hitting a plate. MEASURED on the Iowa suspended-cymbal stick takes,
    # time from the strike to within 3 dB of peak:
    #
    #   13/17/18/20" crash ff   1.33  1.33  1.67  1.67 ms
    #   16" chinese ff          1.33 ms      splash ff   3.67 ms
    #
    # against 17.0 ms for this class as it stood. That is the whole of "realistic,
    # but lightly touched": the plate and the ring were right and the crack at the
    # front was being ramped away, so every crash read as a soft one no matter how
    # hard the part asked for it. Velocity was not the problem -- between mf and ff
    # a real cymbal's brightness moves by a median 0.02 dB per dB of level, so it
    # genuinely is the same sound louder.
    #
    # NOTE THE FAST RENDERER CANNOT FULLY HONOUR THIS. synthkernel interpolates
    # the amplitude envelope across BLK = 512 samples = 10.7 ms, so no attack
    # shorter than one block survives it; this takes the crash from 17.0 to 9.3 ms
    # there, and the reference renderer, which has no such grid, gets the 1.5 ms.
    attack_time = 0.0015

    # A CYMBAL'S RING TIME PEAKS IN THE MIDDLE, and no setting of the inherited
    # law can say that. harmonic_decay is decay_db + harmonic_decay_db * h * (h **
    # harmonic_decay_dampening) -- monotonic in h, so the top either always dies
    # faster than the bottom or always slower. MEASURED, T60 by band on the two
    # orchestral clashes (mean), against what we were rendering:
    #
    #      275 Hz  600   1200   2400   4800   8700  13500
    #       1.16   3.33  4.21   3.29   2.94   1.91   0.87   the clash
    #       1.92   1.82  2.40   2.27   2.29   2.46   2.45   ours, near enough flat
    #
    # The plate rings longest around 1.2 kHz and both ends fall away -- the bass
    # modes are heavily damped by the mount and the air, the top by radiation and
    # internal loss. That is a parabola in log frequency, not a slope, and it is
    # why our late spectrum came out flat at -18 dB across when the recording is
    # mid-focused with a dead top.
    #
    # Asymmetric, because the low side falls faster than the high side: a single
    # symmetric parabola leaves 10.4 dB/s of residual, most of it at 275 Hz.
    # OFF by default (0.0 = use the inherited law), because every cymbal voice
    # here was fitted under the old one. Switch it on per class as each is
    # refitted; the numbers below are what the clash measures.
    # A STRUCK PLATE DOES NOT DECAY AS ONE EXPONENTIAL. It loses energy fast at
    # first -- radiation, and nonlinear coupling carrying energy out of the
    # struck modes while the amplitude is still large -- and then settles to the
    # slower intrinsic loss of the metal. The envelope stage on the ride, bell,
    # china and crash-ride ran into exactly that: their envelopes could only be
    # improved by steepening ring_decay_above, which is FREQUENCY-dependent, so
    # every dB of envelope was paid for in tail colour (the ride's tail error
    # went 0.97 -> 3.50 buying 1.9 dB of envelope).
    #
    # The engine has had the mechanism all along, under another name. Both
    # renderers compute the amplitude as
    #     (1 - af)*exp(-t*lr) + af*exp(-t*lrA)
    # -- the piano's coupled-string aftersound -- and af is frequency
    # INDEPENDENT, so it bends the envelope without tilting the spectrum. That
    # is the lever the envelope needed and ring_decay_above never was.
    #
    # 0.0 keeps the single exponential, so every voice that does not set it
    # renders exactly as before.
    aftersound_fraction = 0.0      # share of the energy on the slow component
    aftersound_ratio = 1.0         # its rate, as a fraction of the fast one

    def aftersound(self, frequency, decay_rate):
        if self.aftersound_fraction <= 0.0:
            return (0.0, decay_rate)
        return (self.aftersound_fraction, decay_rate * self.aftersound_ratio)

    ring_peak_hz = 0.0
    ring_decay_floor = 14.4        # dB/s at the peak
    ring_decay_below = 12.0        # dB/s per octave^2 under the peak
    ring_decay_above = 4.0         # dB/s per octave^2 over it

    def harmonic_decay(self, harmonic):
        """Decay rate for one partial, from where it sits rather than its index."""
        if self.ring_peak_hz <= 0.0:
            return super().harmonic_decay(harmonic)
        f = self.frequency_x * (2.0 ** self.octave_position) * self.mode_ratio(harmonic)
        if f <= 0.0:
            return super().harmonic_decay(harmonic)
        from math import log
        oct_from_peak = log(f / self.ring_peak_hz) / log(2.0)
        k = self.ring_decay_below if oct_from_peak < 0.0 else self.ring_decay_above
        base = self.ring_decay_floor + k * oct_from_peak * oct_from_peak
        return base * self.decay_register_factor


class HiHatProperties(CymbalProperties):
    """Two cymbals on a stand, and GM asks for three sounds from them -- but
    there is only ONE PLATE, and a plate's modes do not move when you clamp it.
    MEASURED: Iowa hihat.normal, hihat.footclose and hihat.footsplash at pp, mf
    and ff.

    The three used to carry three DIFFERENT mode sets, measured separately: the
    closed hat an 18-mode body based at 225.4 Hz with its strongest line at
    4696, the pedal 18 more based at 196.4 with its strongest at 15842, the open
    hat 90 modes based at 400 whose strongest were 543 and 547. Three pitches
    from one pair of cymbals, which is what Ben heard: "the hi-hat tonality
    seems to differ too much between the 3 modes."

    TWO OF THE THREE WERE NEVER MEASURABLE. A mode is a line; a stick on clamped
    hats is a contact noise. How far the peaks stand above the local continuum,
    by band:

                                200-800  800-2k    2-5k   5-10k  10-20k
        closed, its own 0-130 ms    1.9     3.1     5.5     6.4     7.4
        pedal,  its own 0-108 ms    2.4     2.6     5.6     5.2     6.1
        open,   its own 0-150 ms    2.3     4.5     7.0     8.3     8.3
        open,   its RING 0.3-2 s   15.9    31.1    39.9    41.5    23.4

    The first 130 ms IS the whole life of the closed and pedal takes, and 2-7 dB
    is the Rayleigh ripple of a noise spectrum -- there is nothing there to
    measure. Only the free ring has lines. Nor do the peaks repeat: 60 strongest
    peaks, ff against mf, against a null made by detuning one set by an
    irrational factor (density and count preserved, correspondence destroyed):

                             tol%   real   chance
        closed 0-130 ms       0.2      9      6.2     1.5x -- noise
        open RING 0.3-2 s     0.2     32      5.5     5.8x -- real lines

    AND THE OLD CRITERION ADMITTED NOISE. The three sets were kept where two
    dynamics agreed within 1.5%; at that tolerance chance alone gives 29 of 60.

    So there is one mode set, taken where the plate rings free, and the
    articulations differ by DAMPING. Confirmed peaks (ff and mf within 0.2%)
    give 136 modes from 465 to 14085 Hz, and their density per octave runs
    2, 7, 18, 37, 59 -- doubling, which is what a 2D plate does. Filled to that
    measured density (0.0105 modes/Hz) the set is 224.0 modes.

    THE TOP OCTAVE IS THE STRIKE, NOT THE RING. It carries -1.8 to -2.4 dB of
    the total energy in all three strikes -- about two thirds of the sound --
    and by 0.3 s it is at -36.2 dB, which is why the ring could not show those
    modes and the first set stopped at 15.9 kHz. Continuing the density law to
    20 kHz gives them back; ring_decay_above is what makes them die fast.

    BELOW 400 Hz IS NOT A MODE. Line excess there is 1.1-1.6 dB and the peak
    wanders between dynamics -- 295 Hz at ff against 386 at mf on the closed
    hat, 268 against 80 on the splash. It is the contact and the mechanism, not
    the plate. Those partials are in the set because the wash is emitted per
    partial and so needs something to ride on; how much each articulation uses
    is read off its own recording, which is why the foot-close has 10 dB more
    down there than the other two.

    THE PLATE RINGS LONGEST AT 1.2 kHz, fitted on all three takes at once. The
    orchestral clash measures its longest ring at 1.2 kHz too, and that number
    was not used here -- it comes out of three hi-hat recordings on its own.
    """
    inharmonicity_coefficient = 0.0    # the modes are measured absolutely
    inharmonicity_dynamic = False

    mode_ratios = (1.0000, 1.4365, 1.8730, 2.0219, 2.5687, 3.1155, 3.3017, 3.7451,
                   4.1145, 4.7115, 5.0438, 5.3486, 5.7674, 6.1862, 6.7643, 7.2706,
                   7.3016, 7.6454, 7.8316, 8.2433, 8.6550, 8.8920, 9.3540, 9.5981,
                   9.6431, 9.9741, 10.2031, 10.2783, 10.4107, 10.8078, 10.9676, 11.1745,
                   11.3417, 11.5119, 11.7807, 12.1179, 12.6446, 12.8270, 13.2902, 13.4808,
                   13.7227, 14.0647, 14.4456, 14.8190, 15.0445, 15.3120, 15.5300, 15.8186,
                   16.1103, 16.2713, 16.3482, 16.5068, 16.8284, 17.0278, 17.1783, 17.3588,
                   17.7317, 17.9567, 18.1456, 18.3271, 18.5587, 18.9846, 19.3178, 19.5058,
                   19.8969, 20.2879, 20.4474, 20.6876, 20.9119, 21.2684, 21.6524, 22.0363,
                   22.4202, 22.8042, 23.3840, 23.5974, 23.7337, 24.4137, 24.6534, 24.8395,
                   25.1708, 25.4147, 25.5799, 25.9786, 26.3847, 26.6921, 26.8577, 27.0552,
                   27.4556, 27.7495, 28.4177, 28.9876, 29.1933, 29.3552, 29.5791, 29.7247,
                   30.2094, 30.5440, 30.8049, 31.0023, 31.2056, 31.3598, 31.6659, 31.8460,
                   32.0314, 32.3181, 32.6853, 33.0892, 33.4439, 33.8516, 34.2594, 34.6671,
                   35.0067, 35.4338, 35.8424, 36.2510, 36.9559, 37.1746, 37.5243, 38.0295,
                   38.2462, 38.7344, 38.9577, 39.5009, 40.2226, 40.5586, 40.9872, 41.2445,
                   41.8467, 42.5502, 43.0565, 43.4825, 43.9084, 44.1669, 44.5457, 44.9940,
                   45.4105, 45.8270, 46.2435, 46.6600, 47.0765, 47.4930, 48.0151, 48.3433,
                   48.6902, 49.2884, 49.7147, 50.1492, 50.5836, 51.0416, 51.4996, 51.9575,
                   52.3688, 52.7801, 53.1915, 53.7238, 54.2561, 54.6415, 55.0268, 55.4122,
                   55.7976, 56.1763, 56.6960, 57.0800, 57.4639, 57.8479, 58.2319, 58.6159,
                   58.9998, 59.3838, 59.7678, 60.1518, 60.5357, 60.9197, 61.3037, 61.6877,
                   62.0716, 62.4556, 62.8396, 63.2236, 63.6075, 63.9915, 64.3755, 64.7595,
                   65.1434, 65.5274, 65.9114, 66.2954, 66.6793, 67.0633, 67.4473, 67.8313,
                   68.2152, 68.5992, 68.9832, 69.3672, 69.7511, 70.1351, 70.5191, 70.9031,
                   71.2870, 71.6710, 72.0550, 72.4390, 72.8229, 73.2069, 73.5909, 73.9749,
                   74.3588, 74.7428, 75.1268, 75.5108, 75.8947, 76.2787, 76.6627, 77.0467,
                   77.4306, 77.8146, 78.1986, 78.5826, 78.9665, 79.3505, 79.7345, 80.1185)
    max_harmonic = 224

    # One plate, one loss curve. ring_decay_above is the only part of it that
    # varies, because contact damping is not uniform: where the plates touch,
    # friction kills the short-wavelength modes fastest while the long ones
    # still swing the whole plate and survive.
    # AND THE DECAY WAS BEING DECIDED BY THE WRONG MEASUREMENT, twice.
    #
    # First: while the mode gains were the only thing carrying the spectrum, any
    # decay fast enough to make a strike shape stole energy out of the 130 ms
    # window the band profile is measured in, so the fit could not buy it and
    # ring_decay_above pinned near 2. With the wash banded and the gains
    # re-solved against whatever decay is chosen, that constraint lifts.
    #
    # Then, freed, it went straight past the answer: fitted on the ENVELOPE the
    # top loss ran to 140 dB/s/oct^2, which gave the shape in time (rms 9.14 ->
    # 1.47 dB) by killing the plate's top, and the tail came out a low hum where
    # the recording is still sizzling --
    #
    #     tail, 0.15-0.8 s      400    800    1k6    3k1    6k3   12k5    22k
    #         the recording   -18.1   -5.9  -20.9  -13.2   -2.7  -17.6  -19.4
    #         envelope-fitted  -2.1   -6.5  -13.6  -10.8  -19.1  -30.5  -33.3
    #
    # -- 200-400 Hz dominant where the recording's tail lives at 3-6 kHz, 11.6 dB
    # of error that the strike window is blind to. AN ENVELOPE IS ONE NUMBER PER
    # WINDOW AND CANNOT SAY WHICH PARTIALS SHOULD HAVE GONE. The band profile in
    # the tail can, so the loss curve is fitted against both windows and the
    # envelope together -- the decay IS what the spectrum does between them.
    #
    #                    strike   continuum   envelope   tail
    #     gains only       0.06        0.28       9.14   11.63 dB
    #     envelope only    0.27        0.67       1.47   11.63
    #     both windows     0.04        0.59       2.38    5.77
    #
    # The peak moved with it, 1200 Hz -> 2500, and the long rings the envelope
    # fit wanted (7.7 s on a closed hat) came back to 1.4.
    ring_peak_hz = 2500.0
    ring_decay_below = 4.0
    ring_decay_floor = 14.4
    hf_corner_hz = 45000.0
    hf_order = 4.0
    tonal_dampening = 0.15

    # THE WASH IS NOT A FREE PARAMETER ANY MORE. Every round of the refit ran
    # chiff_volume to its bound and then paid for it in the spectrum, because a
    # big enough noise can imitate any band profile badly. It was only ever
    # there to stand in for a sparse mode set -- at 18 modes there is no
    # continuum, so noise had to be one. At 224.0 there is: the mode gains alone,
    # with no wash and no roll-off, hold every band of every take to 1.9 dB. So
    # it goes back to the cymbal family's value and stays there.
    # THE WASH IS A BAND AROUND EACH MODE, NOT A HISS UNDER ALL OF THEM, and
    # that is what let the spectrum and the continuum stop fighting. Ben, on the
    # waterfall of the previous commit: "the modal shape is better, but there
    # needs to be more jitter/noise/wash in between. You can see how very tonal
    # it is." Measured -- how far the peaks stand above the continuum between
    # them, over the strike:
    #
    #                        0.3-0.8k  0.8-2k    2-5k   5-10k  10-20k
    #     the recording           1.9     3.4     5.6     6.8     7.6
    #     224 modes, wash 1.8     3.5     5.6    24.0    28.3    26.9
    #
    # 24-30 dB of line spectrum where the recording has 6-8. Density cannot fix
    # it: in a 150 ms window a partial is 6.7 Hz wide and these sit 95 Hz apart,
    # fourteen Rayleigh widths, fully resolved; merging them would want ~2800
    # modes. A real cymbal has them, so the wash has to stand in -- and with the
    # wash WHITE, turning it up far enough to fill between the modes fills the
    # notches between the bands just as fast:
    #
    #     closed hat, chiff 150        line excess err   band err
    #     white                               0.41 dB      5.82 dB
    #     banded, 0.05 of f                   0.54         1.19
    #     banded, 0.15 of f                   0.20         1.45
    #     banded, 400 Hz absolute             0.39         1.68
    #
    # See chiff_bandwidth. The width is a FRACTION of each partial's frequency,
    # which is both what fits better and what the physics nominates: of the
    # three things that broaden a mode, damping gives a Lorentzian of alpha/pi
    # (1-7 Hz here, set by the decay rate, not by f) and unresolved neighbours
    # give the mode spacing (constant in Hz for a plate), but the one that
    # dominates a struck cymbal is nonlinear frequency modulation -- the plate is
    # driven hard enough that its modes wobble by a fraction of their own
    # frequency -- and that scales with f.
    #
    # chiff_volume is per articulation below, because how hard the plate is
    # driven into that nonlinearity is exactly what the three gestures differ in.
    strike_phase_spread = 1.0
    strike_noise_slope = 0.6


class ClosedHiHatProperties(HiHatProperties):
    """GM 42. A stick on clamped hats: short, and BRIGHT.

    Its gains are the plate's, weighted by what THIS gesture excites. Reading
    them by energy partition -- splitting the spectrum at the geometric
    midpoints between neighbouring modes and giving each partial its region's
    energy -- puts the clamped hat's weight +4.6 dB toward the top against the
    open hat's +2.0: the clamp kills the whole-plate modes and leaves the dense
    short-wavelength top, which is the tick a drummer is actually playing.

    THE GAINS ARE STRIKE AMPLITUDES, NOT WINDOW AVERAGES, and getting that
    wrong is what made every earlier fit choose between a top that decays
    (right in time, short in the band profile) and one that does not (right in
    the profile, wrong in time). Energy partition over 0-130 ms gives each mode
    its energy across the WHOLE window, so a mode that dies inside the window
    contributes less than one that does not -- which under-states exactly the
    modes that decay fastest. For a partial decaying at d dB/s its energy over
    [0,T] relative to no decay is (1-e^(-2aT))/(2aT), a = d*ln10/20; dividing
    that out turns the partition back into the amplitude at the strike. The
    correction depends on the decay and the decay fit depends on the gains, so
    it is iterated to a fixed point (four passes). It bought both errors at
    once: band 1.95 -> 1.65 dB and envelope 10.65 -> 9.12.
    """
    mode_gains  = (0.0270, 0.0239, 0.0113, 0.0118, 0.0118, 0.0030, 0.0036, 0.0036,
                   0.0029, 0.0011, 0.0024, 0.0022, 0.0023, 0.0044, 0.0038, 0.0030,
                   0.0040, 0.0029, 0.0068, 0.0072, 0.0062, 0.0047, 0.0057, 0.0072,
                   0.0035, 0.0032, 0.0010, 0.0020, 0.0023, 0.0032, 0.0031, 0.0023,
                   0.0022, 0.0033, 0.0072, 0.0124, 0.0070, 0.0104, 0.0067, 0.0060,
                   0.0056, 0.0073, 0.0409, 0.0074, 0.0056, 0.0066, 0.0081, 0.0086,
                   0.0052, 0.0057, 0.0072, 0.0121, 0.0113, 0.0080, 0.0060, 0.0060,
                   0.0101, 0.0122, 0.0188, 0.0102, 0.0092, 0.0213, 0.0048, 0.0093,
                   0.0385, 0.0119, 0.0070, 0.0103, 0.0155, 0.0123, 0.0090, 0.0163,
                   0.0135, 0.0110, 0.0946, 0.0129, 0.0121, 0.0102, 0.0104, 0.0109,
                   0.0139, 0.0275, 0.0365, 0.0257, 0.0119, 0.0169, 0.0236, 0.0252,
                   0.0262, 0.0297, 0.0690, 0.0154, 0.0098, 0.0178, 0.0146, 0.0131,
                   0.0151, 0.0165, 0.0114, 0.0154, 0.0091, 0.0089, 0.0149, 0.0114,
                   0.0162, 0.0167, 0.0221, 0.0220, 0.0256, 0.0237, 0.0346, 0.0149,
                   0.0430, 0.0476, 0.0281, 0.0175, 0.0185, 0.0127, 0.0280, 0.0188,
                   0.0179, 0.0154, 0.0243, 0.0371, 0.0374, 0.0520, 0.0722, 0.0472,
                   0.0375, 0.0413, 0.0386, 0.0210, 0.0272, 0.0144, 0.0259, 0.0448,
                   0.0433, 0.0262, 0.0220, 0.0434, 0.0267, 0.0542, 0.0430, 0.0230,
                   0.0488, 0.0582, 0.0510, 0.0443, 0.0634, 0.0937, 0.0551, 0.0998,
                   0.1036, 0.0441, 0.0564, 0.0999, 0.0674, 0.0739, 0.0570, 0.0694,
                   0.0836, 0.0654, 0.0861, 0.0591, 0.0591, 0.0664, 0.0816, 0.0624,
                   0.0856, 0.0580, 0.0576, 0.0738, 0.1034, 0.0898, 0.0993, 0.0529,
                   0.0494, 0.0883, 0.0962, 0.0823, 0.1029, 0.1025, 0.1056, 0.0439,
                   0.0973, 0.0742, 0.0949, 0.1728, 0.1555, 0.0861, 0.0974, 0.0956,
                   0.1335, 0.1033, 0.0936, 0.1312, 0.1055, 0.0803, 0.1218, 0.0588,
                   0.0874, 0.0764, 0.1483, 0.1020, 0.2101, 0.1127, 0.1015, 0.1199,
                   0.1618, 0.0760, 0.1328, 0.1480, 0.0831, 0.1117, 0.2077, 0.1221,
                   0.1958, 0.1457, 0.1561, 0.1493, 0.1945, 0.1631, 0.2151, 1.0000)
    ring_decay_above = 54.7
    aftersound_ratio = 1.00
    aftersound_fraction = 0.00
    sustain_jitter = 0.40
    chiff_volume = 100.0
    chiff_bandwidth = 0.15
    # THE BALANCE IS NOT RE-DERIVED HERE. The three sit where Ben's ear put
    # them before the rebuild -- the open hat 1.2 dB over the closed one --
    # and initial_gain is solved to hold each voice's K-weighted loudness
    # exactly where it was, so this commit changes the timbre and the decay
    # and nothing about the mix.
    initial_gain = (0.014036) * 1.2735   # +2.1 dB: K-weighted to the string reference

class PedalHiHatProperties(HiHatProperties):
    """GM 44. The foot closing the hats: two plates clapping together.

    Its weight runs the other way from the closed hat's, -6.0 dB toward the
    BOTTOM, and it has 10 dB more below 400 Hz than either of the others. That
    is the mechanism, not the plate -- the pedal, the rod and the seat -- and it
    is why a chick reads as a low broadband contact rather than as a pitch.

    Its old anchor was the weakest of the three and still is: it was set from
    footclose.mf against footsplash.mf, and a foot CLOSE and a foot SPLASH are
    not the same effort, so Iowa's "mf" does not mean the same thing in both.
    """
    mode_gains  = (0.0335, 0.0183, 0.0093, 0.0070, 0.0089, 0.0041, 0.0066, 0.0046,
                   0.0030, 0.0028, 0.0027, 0.0042, 0.0047, 0.0050, 0.0012, 0.0021,
                   0.0009, 0.0027, 0.0031, 0.0021, 0.0031, 0.0018, 0.0011, 0.0009,
                   0.0009, 0.0014, 0.0011, 0.0010, 0.0020, 0.0019, 0.0012, 0.0012,
                   0.0007, 0.0017, 0.0021, 0.0024, 0.0023, 0.0036, 0.0027, 0.0046,
                   0.0031, 0.0050, 0.0134, 0.0101, 0.0044, 0.0032, 0.0051, 0.0030,
                   0.0044, 0.0019, 0.0025, 0.0035, 0.0073, 0.0054, 0.0011, 0.0038,
                   0.0049, 0.0031, 0.0037, 0.0043, 0.0044, 0.0315, 0.0037, 0.0107,
                   0.0163, 0.0121, 0.0036, 0.0043, 0.0066, 0.0061, 0.0040, 0.0053,
                   0.0056, 0.0061, 0.0273, 0.0096, 0.0052, 0.0089, 0.0071, 0.0094,
                   0.0079, 0.0160, 0.0123, 0.0152, 0.0131, 0.0168, 0.0057, 0.0187,
                   0.0235, 0.0271, 0.0547, 0.0266, 0.0134, 0.0134, 0.0101, 0.0145,
                   0.0214, 0.0158, 0.0096, 0.0145, 0.0165, 0.0220, 0.0118, 0.0216,
                   0.0129, 0.0074, 0.0138, 0.0074, 0.0155, 0.0167, 0.0227, 0.0186,
                   0.0233, 0.0178, 0.0213, 0.0266, 0.0100, 0.0100, 0.0138, 0.0185,
                   0.0213, 0.0277, 0.0172, 0.0252, 0.0242, 0.0326, 0.0393, 0.0338,
                   0.0288, 0.0269, 0.0191, 0.0208, 0.0226, 0.0334, 0.0268, 0.0347,
                   0.0375, 0.0223, 0.0226, 0.0245, 0.0290, 0.0247, 0.0328, 0.0391,
                   0.0773, 0.0338, 0.0353, 0.0304, 0.0313, 0.0692, 0.0301, 0.0873,
                   0.0919, 0.0808, 0.0587, 0.0791, 0.0855, 0.0774, 0.0687, 0.0559,
                   0.0572, 0.0504, 0.0699, 0.0637, 0.0856, 0.0599, 0.0546, 0.0623,
                   0.0612, 0.0299, 0.0549, 0.0679, 0.0806, 0.0618, 0.0501, 0.0448,
                   0.0588, 0.0686, 0.0584, 0.0909, 0.0696, 0.0587, 0.0663, 0.0634,
                   0.0621, 0.0815, 0.1337, 0.1552, 0.1416, 0.0889, 0.1198, 0.1239,
                   0.1449, 0.1323, 0.2093, 0.0952, 0.0844, 0.1170, 0.1354, 0.1838,
                   0.1735, 0.1057, 0.2484, 0.1401, 0.1566, 0.1408, 0.2047, 0.1553,
                   0.1344, 0.1700, 0.1766, 0.1267, 0.2122, 0.1891, 0.1782, 0.1314,
                   0.1597, 0.1669, 0.3073, 0.1261, 0.1208, 0.1978, 0.2188, 1.0000)
    ring_decay_above = 288.7
    aftersound_ratio = 0.02
    aftersound_fraction = 0.02
    sustain_jitter = 0.05
    chiff_volume = 220.0
    chiff_bandwidth = 0.06
    # THE BALANCE IS NOT RE-DERIVED HERE. The three sit where Ben's ear put
    # them before the rebuild -- the open hat 1.2 dB over the closed one --
    # and initial_gain is solved to hold each voice's K-weighted loudness
    # exactly where it was, so this commit changes the timbre and the decay
    # and nothing about the mix.
    initial_gain = (0.098139) * 1.3964   # +2.9 dB: K-weighted to the string reference

class OpenHiHatProperties(HiHatProperties):
    """GM 46. Hats apart and ringing: the plate speaks.

    This is the take the whole mode set comes from -- the only long hi-hat
    recording Iowa has -- and it is not quite the gesture GM 46 means: a splash
    opens the hats and lets them ring for 7.25 s to -40 dB, where a stick on
    open hats is damped by the hats still being loosely together. The modes are
    the same plate either way; the ring is capped well below the measurement for
    that reason.

    ITS REFERENCE WAS PLAYED SOFT, which is measurable rather than a guess.
    Where each hat's mf sits inside its OWN pp/mf/ff range: the open hat's is
    12.5 dB under its ff, the closed hat's 8.6, the pedal's 8.3. So this voice
    is anchored to a take about 4 dB softer, in its own terms, than the takes
    the other two are anchored to. 2.4 dB of that is taken -- Ben's ear set the
    last 1.5 ("now just a little too loud") -- which puts the open hat 0.8 dB
    above the closed one. That is also what a kit does: more of the cymbal is
    free to move, so it speaks louder for the same stroke.
    """
    mode_gains  = (0.0860, 0.0895, 0.0665, 0.1149, 0.0627, 0.0286, 0.0240, 0.0455,
                   0.0344, 0.0196, 0.0091, 0.0278, 0.0344, 0.0224, 0.0155, 0.0133,
                   0.0065, 0.0142, 0.0190, 0.0237, 0.0406, 0.0234, 0.0155, 0.0226,
                   0.0178, 0.0122, 0.0069, 0.0042, 0.0050, 0.0148, 0.0119, 0.0186,
                   0.0140, 0.0107, 0.0256, 0.0668, 0.0256, 0.0242, 0.0275, 0.0120,
                   0.0352, 0.0253, 0.0244, 0.0092, 0.0092, 0.0210, 0.0459, 0.0424,
                   0.0308, 0.0236, 0.0217, 0.0166, 0.0146, 0.0255, 0.0448, 0.0231,
                   0.0290, 0.0114, 0.0279, 0.0273, 0.0311, 0.1208, 0.0150, 0.0325,
                   0.0673, 0.0376, 0.0338, 0.0487, 0.0365, 0.0386, 0.0175, 0.0815,
                   0.0259, 0.0345, 0.0898, 0.0217, 0.0260, 0.0287, 0.0325, 0.0573,
                   0.0492, 0.0883, 0.0321, 0.0853, 0.0604, 0.0216, 0.0244, 0.0438,
                   0.0454, 0.0661, 0.2175, 0.0241, 0.0244, 0.0427, 0.0522, 0.0215,
                   0.0512, 0.0698, 0.0237, 0.0166, 0.0163, 0.0148, 0.0493, 0.0181,
                   0.0240, 0.0178, 0.0365, 0.0393, 0.0521, 0.0417, 0.0532, 0.0496,
                   0.0776, 0.0721, 0.0489, 0.0598, 0.0343, 0.0317, 0.0657, 0.0650,
                   0.0460, 0.0395, 0.0583, 0.0660, 0.0710, 0.0700, 0.1119, 0.0933,
                   0.0840, 0.0956, 0.0875, 0.0537, 0.0581, 0.0779, 0.0536, 0.0380,
                   0.0419, 0.0586, 0.0463, 0.0350, 0.0616, 0.0769, 0.0424, 0.0441,
                   0.1334, 0.1024, 0.0871, 0.0453, 0.1011, 0.1484, 0.0660, 0.1092,
                   0.1257, 0.0732, 0.1210, 0.1215, 0.1207, 0.0817, 0.0595, 0.0849,
                   0.1499, 0.1502, 0.1018, 0.0469, 0.0808, 0.0973, 0.1008, 0.0973,
                   0.1125, 0.0565, 0.0406, 0.0664, 0.1244, 0.1115, 0.1898, 0.0593,
                   0.0612, 0.0904, 0.1208, 0.1249, 0.1240, 0.1281, 0.0676, 0.0553,
                   0.0854, 0.0859, 0.1147, 0.1804, 0.2048, 0.0932, 0.1050, 0.1394,
                   0.1331, 0.1238, 0.2490, 0.1310, 0.0960, 0.1374, 0.1513, 0.1192,
                   0.1298, 0.1048, 0.1817, 0.1970, 0.0950, 0.1250, 0.1440, 0.0836,
                   0.1359, 0.1280, 0.2141, 0.2437, 0.1577, 0.1213, 0.1151, 0.1671,
                   0.1729, 0.2742, 0.1725, 0.1713, 0.1910, 0.2179, 0.2278, 1.0000)
    ring_decay_above = 10.0
    aftersound_ratio = 0.20
    aftersound_fraction = 0.50
    sustain_jitter = 0.40
    chiff_volume = 60.0
    chiff_bandwidth = 0.10
    # THE BALANCE IS NOT RE-DERIVED HERE. The three sit where Ben's ear put
    # them before the rebuild -- the open hat 1.2 dB over the closed one --
    # and initial_gain is solved to hold each voice's K-weighted loudness
    # exactly where it was, so this commit changes the timbre and the decay
    # and nothing about the mix.
    initial_gain = (0.029231) * 1.2589   # +2.0 dB: K-weighted to the string reference

class CrashCymbal1Properties(CymbalProperties):
    """GM 49, Crash Cymbal 1. MEASURED: Iowa 17" suspended crash, stick on
    the bow, pp/mf/ff -- the kit gesture. (Iowa's "orchcrash" files are the
    orchestral CLASH pair, two plates struck together, which is a different
    instrument.)

    This and the other four kit cymbals shared one CymbalProperties with a
    stretched harmonic series on a GUESSED base frequency -- 520 Hz here against
    a measured 313.8 -- so every mode sat about a sixth too high and the plate
    had no low end: 100-500 Hz came out 7.6 dB under the recording while
    10-16 kHz ran 2 dB over. Thin and fizzy where the recording is full.
    Band rms error 3.61 -> 1.98 dB.
    """
    # A CRASH IS A CONTINUUM, NOT A LINE SPECTRUM, and half our energy was one
    # low tone. Ben, on the A/B against the clash: "our crashes sound completely
    # different... a lot of it seems to be the jitter amount, both bandwidth and
    # volume, is still an order of magnitude off." The jitter itself turned out
    # to be fine -- the kernel redraws its phase every sample, so it is already
    # full-bandwidth white -- but it was being buried. Measured 0.1-0.3 s after
    # the strike, band by band, against the clash:
    #
    #                       300-700   700-1.5k   1.5-3k    3-6k
    #     energy, clash       -24.1      -13.7     -5.7    -3.2
    #     energy, ours         -3.0      -12.1     -8.7   -11.4
    #     peak/median, clash    10.4       20.0     24.8    20.2
    #     peak/median, ours     35.4       25.1     32.1    25.2
    #
    # Half the energy sat in a 300-700 Hz tone the clash barely has, so the wash
    # was spread thin under it, and the partials stood 24-35 dB above the floor
    # between them where a real crash's stand 10-25. That is what "an order of
    # magnitude of jitter" sounds like from the outside; the fix is where the
    # energy is, not how much noise there is.
    #
    # Two changes. The mode gains carry a high-pass shelf so the plate's own low
    # modes stop dominating -- fitted, not chosen -- and the mode set goes from 26
    # to 100, because a sparse set cannot be a continuum however it is weighted.
    # Denser is measurably better on both counts (crash 2's energy error 4.61 ->
    # 1.33 dB, its line-excess 8.0 -> 5.7). It costs partials: 78 per hit.
    # LOOK AT THE WATERFALL. Ben: "Have you been comparing the FFT waterfalls at
    # all?" No -- everything measured up to here was a scalar in a fixed window,
    # which is why three rounds of matching numbers still sounded wrong. The
    # spectrogram says it in one glance: the clash fills the whole time-frequency
    # plane for a second and a half, and ours was a bright vertical smear at the
    # strike and then blue, with a handful of horizontal lines ringing on. A click
    # plus a few resonances. That is "tinny", and it is also "not wet".
    #
    # IT ALSO SHOWED A CONCLUSION OF MINE WAS BACKWARDS. Two commits ago I read
    # the recording's ring flatness of 0.002 as "the noise is a transient, the
    # ring is tonal" and turned the sustained wash off. But low flatness means a
    # PEAKY spectrum, and a cymbal's ring is peaky because it is hundreds of
    # dense resolved modes -- not because it is quiet. The waterfall shows that
    # ring is full of energy. Killing the wash was removing the wrong thing.
    #
    # So: 300 modes, not 26. Measured peaks give the frequencies that can be
    # resolved; the rest are filled to the density a cymbal actually has, with
    # gains read off the clash's own smoothed spectrum. Plus a modest sustained
    # wash, refitted against band energy at FOUR times (0.02, 0.10, 0.35, 0.70 s)
    # rather than one window, so the decay is fitted and not assumed.
    #
    # WHAT IS STILL WRONG, measured at 0.70 s: the clash is mid-focused and dead
    # on top (-9.5 dB at 3-6 kHz, -32 at 10-16); ours is flat at about -18 across.
    # A broadband wash decays with the note's amplitude envelope, uniformly in
    # frequency, so it cannot make that shape -- only modes have per-mode decay.
    # Closing it means either enough modes to carry the sustain alone, or a
    # frequency-dependent wash decay in the kernel. Fit error 5.1 and 6.3 dB.
    # REFITTED on honest frequencies. Everything above was fitted while the
    # measured modes were being stretched by the family's inharmonicity (see
    # CymbalProperties), so every gain, decay, wash and level was compensating
    # for modes in the wrong place. All of it is re-solved here against the
    # recording's band energy at FOUR times -- 0.02, 0.10, 0.35 and 0.70 s --
    # plus how far the lines stand above the continuum, with the level held to
    # what Ben balanced by ear so this changes the sound and not the mix.
    #
    # The ring law is ON here (see CymbalProperties.harmonic_decay): a plate's
    # ring time peaks in the middle and dies at both ends, which the inherited
    # monotonic law cannot express.
    mode_ratios = (1.0000, 1.0890, 1.1210, 1.2190, 1.3650, 1.3875, 1.3875, 1.4218,
                   1.4261, 1.4283, 1.4703, 1.4706, 1.5020, 1.5539, 1.5818, 1.6041,
                   1.6555, 1.6989, 1.7089, 1.7226, 1.7395, 1.7807, 1.7967, 1.8123,
                   1.8712, 1.8773, 1.8847, 1.8861, 1.9955, 1.9990, 2.0310, 2.0572,
                   2.1454, 2.1700, 2.1768, 2.1910, 2.2459, 2.2934, 2.3070, 2.3275,
                   2.3845, 2.4239, 2.4264, 2.4865, 2.5805, 2.5940, 2.7011, 2.7043,
                   2.7496, 2.8414, 2.8477, 2.8955, 2.9180, 2.9236, 2.9734, 2.9920,
                   3.0267, 3.0871, 3.1780, 3.1860, 3.2892, 3.3029, 3.3297, 3.3543,
                   3.4242, 3.6002, 3.6473, 3.6906, 3.7504, 3.7815, 3.9087, 3.9389,
                   4.0451, 4.0854, 4.2292, 4.2495, 4.2758, 4.2791, 4.3983, 4.4529,
                   4.5975, 4.6723, 4.8252, 4.8487, 4.8590, 4.8665, 4.9560, 5.0005,
                   5.0240, 5.1858, 5.1950, 5.3509, 5.5990, 5.6116, 5.6850, 5.7080,
                   5.7083, 5.7156, 5.8392, 6.0222, 6.1616, 6.3295, 6.4227, 6.4354,
                   6.4503, 6.5383, 6.8295, 6.8528, 7.0560, 7.1290, 7.1860, 7.3250,
                   7.3519, 7.3857, 7.3900, 7.5457, 7.6732, 7.8604, 7.8690, 7.9229,
                   8.0447, 8.0707, 8.0962, 8.2392, 8.3410, 8.4799, 8.7426, 8.7628,
                   8.8780, 9.1110, 9.2441, 9.2647, 9.5069, 9.9700, 10.1285, 10.2092,
                   10.2593, 10.3895, 10.6700, 10.8880, 10.9258, 11.0593, 11.0780,
                   11.2389, 11.2720, 11.4952, 11.7785, 12.0234, 12.2020, 12.2460,
                   12.3100, 12.3750, 12.5920, 12.6493, 12.6812, 12.6870, 12.7925,
                   12.8041, 12.8220, 12.8718, 13.2611, 13.2827, 13.2870, 13.3116,
                   14.0005, 14.0420, 14.2577, 14.9946, 15.0489, 15.3840, 15.4731,
                   15.5682, 15.9970, 16.0290, 16.1020, 16.1688, 16.6400, 16.7780,
                   17.2223, 17.2380, 17.3090, 17.3771, 17.4172, 17.6368, 17.8140,
                   17.8219, 17.9330, 18.5819, 19.1155, 19.2582, 19.3193, 19.5040,
                   19.5875, 20.4670, 21.0525, 21.6970, 21.7122, 21.7370, 21.8395,
                   21.9761, 22.3038, 22.5363, 22.7711, 23.6631, 23.7846, 23.8312,
                   24.2936, 24.3500, 24.7678, 25.0580, 25.2640, 25.3460, 25.7060,
                   25.8256, 25.9586, 26.2260, 26.4450, 26.6140, 26.9740, 27.0616,
                   27.5008, 27.7640, 28.0460, 28.2060, 28.3034, 28.7963, 28.9034,
                   29.3627, 29.7840, 29.8710, 31.0520, 31.2080, 31.2142, 31.3150,
                   31.4651, 31.5772, 31.7850, 31.9040, 32.2250, 32.5580, 32.8120,
                   33.0151, 33.0370, 33.5250, 33.5562, 33.5866, 33.9350, 34.0861,
                   34.1027, 34.2600, 34.5660, 35.2110, 35.4110, 35.9210, 36.2623,
                   36.7100, 36.9510, 37.3470, 37.9676, 37.9881, 38.2280, 38.2605,
                   38.3310, 38.4246, 38.4680, 38.9900, 39.0521, 39.1130, 39.7580,
                   40.0350, 40.3750, 40.7200, 40.8205, 40.8580, 41.3993, 41.8037,
                   42.0990, 42.3960, 42.8455, 43.2580, 44.7522, 45.2068, 45.4466,
                   45.4520, 45.5001, 45.5690, 45.8040, 45.8707, 45.9200, 47.1740,
                   47.5880, 49.4121, 49.4657, 50.4210, 51.5536, 52.9604, 53.1040,
                   53.6166, 54.0453, 55.2306)
    # THE GAINS COME FROM THE STRIKE, NOT THE RING, and that is the wah. Ben:
    # "The left crash is still wah sounding at the beginning." A rising band of
    # energy is a filter sweep, and the spectral centroid says ours was doing
    # exactly that:
    #
    #                    at 10 ms    at 0.5 s
    #     clash            8129 Hz     3428 Hz    falls -- bright hit, darker ring
    #     17" stick        8673        2601      falls
    #     ours             3630        4012      RISES
    #
    # -- and ours rose with the bloom switched OFF, so it was never the bloom. I
    # had read these mode gains off the clash's envelope at 0.10-0.30 s, which is
    # its RING, so our strike inherited the ring's balance and then brightened
    # toward it. The gains belong to the strike; the ring law is what darkens the
    # tail afterwards. Re-read from 2-32 ms, the centroid falls: 7074 -> 6082.
    #
    # The same window mistake as the hi-hat's mode set and the guiro's, in the
    # third place: measuring the right quantity over the wrong span of the note.
    mode_gains  = (0.7397, 0.2732, 0.2590, 0.3719, 0.4285, 0.0854, 0.0854, 0.1043,
                   0.1063, 0.1073, 0.1230, 0.1231, 0.1303, 0.1325, 0.1302, 0.1270,
                   0.1161, 0.1039, 0.1008, 0.0963, 0.0907, 0.0766, 0.0712, 0.0664,
                   0.0486, 0.0470, 0.0448, 0.0444, 0.0316, 0.0314, 0.0304, 0.0297,
                   0.0256, 0.0238, 0.0233, 0.0222, 0.0185, 0.0182, 0.0186, 0.0191,
                   0.0215, 0.0226, 0.0227, 0.0283, 0.0540, 0.0581, 0.0776, 0.0781,
                   0.0844, 0.1230, 0.1246, 0.1251, 0.1234, 0.1229, 0.1184, 0.1165,
                   0.1129, 0.1101, 0.0998, 0.0984, 0.0839, 0.0822, 0.0822, 0.0843,
                   0.0943, 0.1949, 0.2228, 0.2452, 0.2629, 0.2637, 0.2544, 0.2498,
                   0.2024, 0.1790, 0.0812, 0.0749, 0.0660, 0.0648, 0.0474, 0.0466,
                   0.0610, 0.0973, 0.1508, 0.1577, 0.1592, 0.1592, 0.1583, 0.1578,
                   0.1581, 0.1547, 0.1535, 0.1347, 0.1505, 0.1511, 0.1720, 0.1789,
                   0.1790, 0.1811, 0.2052, 0.2131, 0.2106, 0.2070, 0.1934, 0.1915,
                   0.1892, 0.1754, 0.1248, 0.1202, 0.0967, 0.0903, 0.0848, 0.0706,
                   0.0783, 0.0871, 0.0882, 0.1202, 0.1418, 0.1601, 0.1604, 0.1628,
                   0.1645, 0.1635, 0.1626, 0.1575, 0.1545, 0.1503, 0.1293, 0.1291,
                   0.1278, 0.1545, 0.1814, 0.1849, 0.1722, 0.1731, 0.1843, 0.1742,
                   0.1677, 0.1493, 0.1452, 0.1438, 0.1435, 0.1690, 0.1680, 0.1597,
                   0.1580, 0.1501, 0.1485, 0.1587, 0.1708, 0.1740, 0.1786, 0.1832,
                   0.2114, 0.2194, 0.2236, 0.2243, 0.2378, 0.2385, 0.2388, 0.2399,
                   0.2523, 0.2538, 0.2541, 0.2559, 0.2602, 0.2573, 0.2414, 0.2140,
                   0.2077, 0.1879, 0.1927, 0.1976, 0.1923, 0.1908, 0.1874, 0.1841,
                   0.1583, 0.1657, 0.1931, 0.1930, 0.1921, 0.1912, 0.1907, 0.1880,
                   0.2167, 0.2182, 0.2390, 0.2872, 0.2862, 0.2852, 0.2845, 0.2810,
                   0.2793, 0.1886, 0.2210, 0.2192, 0.2189, 0.2185, 0.2167, 0.3765,
                   0.3657, 0.3645, 0.3650, 0.2569, 0.2470, 0.2470, 0.2475, 0.2476,
                   0.2407, 0.2348, 0.2336, 0.2339, 0.2355, 0.2361, 0.2386, 0.2477,
                   0.2549, 0.2602, 0.2652, 0.2662, 0.2721, 0.2821, 0.2927, 0.2985,
                   0.3013, 0.3035, 0.3039, 0.3014, 0.2952, 0.2939, 0.3498, 0.3548,
                   0.3549, 0.3581, 0.3627, 0.3663, 0.3725, 0.3725, 0.3704, 0.3683,
                   0.3674, 0.3686, 0.3687, 0.3715, 0.3717, 0.3718, 0.3662, 0.3611,
                   0.3606, 0.3555, 0.3450, 0.3027, 0.2860, 0.2597, 0.2739, 0.2914,
                   0.2957, 0.2937, 0.2936, 0.2954, 0.3155, 0.3181, 0.3236, 0.3309,
                   0.3343, 0.3720, 0.3762, 0.3776, 0.3832, 0.3856, 0.3905, 0.3981,
                   0.4003, 0.4011, 0.4126, 0.4408, 0.4613, 0.4811, 0.5023, 0.5111,
                   0.8755, 0.8996, 0.9117, 0.9120, 0.9144, 0.9178, 0.9294, 0.9326,
                   0.9350, 0.9865, 1.0000, 0.9155, 0.9144, 0.8943, 0.8453, 0.7422,
                   0.7284, 0.6775, 0.6402, 0.6330)
    max_harmonic = 300
    aftersound_fraction = 0.08
    aftersound_ratio = 0.06
    # Each mode gets its own strike sign (see strike_phase_spread): with 300
    # modes all starting in phase the note peaked 16.0 dB above its own loudness against the 18" clash's 14.7.
    # AND ITS PARTIALS WERE HALF IN PHASE. At 0.5 the mode signs are only
    # half decorrelated, so 300 partials stack at the strike: the raw sum peaked
    # at 4.436 for a K-weighted -16.91, a crest factor of 29.8 dB, which no
    # cymbal has. It did not matter while the bloom carried most of the note's
    # energy; with the bloom cut to a trace the level has to come back onto the
    # strike, and at 0.5 that clipped -- 1.520 after the default -9.3 dB master.
    #
    #     spread   raw peak     LKFS   crest
    #       0.50      4.436   -16.91   29.8 dB
    #       0.75      2.535   -17.53   25.6
    #       1.00      1.427   -18.05   21.1
    #
    # Full spread costs 1.1 dB of loudness and buys 9.9 dB of peak. Every other
    # measured plate in this file already uses 1.0.
    strike_phase_spread = 1.0
    # THE MODES CARRY THE TOP. The refit before this chose hf_corner_hz = 3153 at
    # order 5, which annihilates modal energy above 3 kHz -- 0.03 of it left at
    # 6.3 kHz, 0.0003 at 15.9 -- so nothing up there was a mode and the WASH was
    # the whole top of the instrument. The fit was free to do that because the
    # chiff is a phase-randomised copy of each partial and so spreads broadband
    # whatever its partial's frequency: turn the modes off up top and the wash
    # covers, and no measure of the spectrum alone can tell the difference.
    #
    # It matters because a wash cannot decay per band and cannot arrive late.
    # Both of the last two commits -- the ring law, and the bloom -- were being
    # smothered by it. Refitted with the roll-off held gentle and well above the
    # band, so the modes reach 16 kHz on their own:
    #
    #     crash 1   grid 5.57 -> 4.94 dB   line excess 5.3 -> 3.7   chiff 11.3 -> 4.0
    #     crash 2   grid 7.02 -> 3.63      line excess 6.5 -> 7.0   chiff  6.9 -> 4.0
    ring_peak_hz = 2000
    # The bloom. Sized from the takes that actually bloom rather than the median
    # of all of them: at the median 139 ms the strike transient still outranks it
    # and no delayed peak appears at all, which is a threshold, not a gradient.
    # 205 ms puts the 3.2-6.4 kHz peak at 427 ms against the 18" clash's 416,
    # and it is scaled by strike force, so a soft crash does not bloom.
    # FITTED AGAINST T60 AND THE ATTACK, not through the band grid. The ring
    # coefficients had been coming along for the ride in a fit that optimised
    # band energy, and the bloom was set by hand to one number for both crashes.
    # Ben, listening to grunge.mid: "one of them has a weirdly gradual attack...
    # positioned on the right" -- which is crash 2, panned +0.6, playing eight
    # hits at velocity 127 and so getting the full bloom.
    #
    # THE BLOOM WAS ON A CRASH WHOSE OWN RECORDING DOES NOT BLOOM. The 18" clash
    # has a 416 ms mid-band delay and the 17" has 32 ms; I measured that, wrote
    # it down, and then set both crashes to 205 ms anyway. Measured as the time
    # to reach 3 dB below peak, ours took 187-191 ms where the real clashes take
    # 26-35: a real plate blooms in the MIDDLE while its low and high still
    # arrive at once, so delaying too wide a slice softens the whole attack.
    #
    #                 attack        bloom depth        T60 error
    #     crash 1   191 -> 63 ms   +8.1 vs +8.1 dB    1.35 octaves
    #     crash 2   187 -> 24 ms   -6.9 vs -3.4       0.87 octaves
    #
    # (crash 2's target attack is 26 ms and its bloom_seconds now 16 -- which is
    # its recording saying it does not bloom, rather than a knob turned down.)
    # THE BLOOM IS AN ADDED LATE COPY, not a delayed partial, and getting that
    # backwards is what made monocas2's crash lag. Ben: "The crash in
    # monocas2.mid... has a weird laggy start" -- that file plays note 49, forty
    # five hits at velocity 127, so it was getting the full delay.
    #
    # Delaying the partial WITHHOLDS the middle of the spectrum, and a crash's
    # strike energy IS its middle, so the attack softens by construction. The
    # first attempt at a fix -- a steeper skirt, to confine the delay to a band --
    # made it worse, 64 ms -> 100, because a tighter delay lands more squarely on
    # the band that defines the onset. The real plate has its middle at full
    # strength immediately and then gains MORE: the cascade adds, it does not
    # withhold. So the partials keep their own onset and a second, quieter copy
    # of each mid partial arrives late beside it.
    #
    #                     attack        bloom depth
    #     delayed partial   64 ms          +8.1 dB
    #     late copy          7 ms          +4.2      <- this
    #     no bloom at all    7 ms          -7.5
    #
    # The depth is short of the clash's +8.1 and that is a deliberate stop: past
    # bloom_gain 3.2 the late copy outgrows the strike, the envelope's peak
    # becomes the bloom rather than the hit, and the laggy start comes straight
    # back (86 ms at gain 3.6). Reaching +8 dB honestly needs the late copy to
    # decay from its own arrival rather than share the partial's envelope.
    # THE BLOOM IS SHORT, AND SHORTEST WHEN HIT HARDEST. Ben, on the two crashes
    # side by side: "Why does the crash on the right not have a wah, and the
    # crash on the left does", then "Crash 1 sounds like it is being hit by a
    # mallet, not a stick", then "the bloom length should be shorter in
    # proportion to attack velocity."
    #
    # He is right and the scaling was inverted. A cascade is nonlinear, so the
    # harder the plate is driven the FASTER energy finds its way up: a stick hit
    # cascades almost at once, a soft mallet stroke swells. bloom_seconds was
    # multiplied by attack_volume**1.5, so a full-velocity crash got the longest
    # swell of all -- 84 ms of late mid arriving under the hit, which is a mallet
    # by construction. It is now the delay at FULL velocity, the shortest it ever
    # is, and softer strokes stretch it:
    #
    #     velocity   127    100     70     40
    #     bloom     25.0   31.8   45.4   79.4 ms
    #     attack    30.8   35.6   53.0   83.8 ms   (the clash's attack is 35.3)
    #
    # At 25 ms the bloom brings the attack TOWARD the recording rather than away
    # from it: with the bloom off entirely this crash starts in 7.6 ms, far
    # sharper than any real clash. Short, it is the difference between a crack
    # and a click; long, it was a mallet.
    #
    # AND THE DECAY UNDERNEATH WAS WRONG, which the long bloom had been masking.
    # ring_peak_hz sat at 5999 against a fit bound of 6000 -- the frequency that
    # rang LONGEST was 6 kHz -- with coefficients so small the decay was nearly
    # flat across frequency. The spectral centroid, which is what "wah" measures:
    #
    #     as it was      6655 -> 4765 -> 4866 Hz   plateaus, then climbs
    #     bloom off only 4993 -> 4766 -> 5525      rises outright
    #     now            5440 -> 4213 -> 3696      falls
    #     the clash      8129 -> 4351 -> 3428
    #
    # A rising centroid is a filter sweep, which is what a wah is. Still 0.6
    # octaves dim at the strike, and that is the 6.4-16 kHz shortfall noted
    # earlier rather than anything the decay can reach.
    # THE BLOOM WAS THREE TIMES THE PARTIAL IT FOLLOWED. bloom_gain 3.2 means
    # the late copy of each partial arrives 25 ms behind it at 3.2x its
    # amplitude, so the note got LOUDER after the strike: at velocity 127 the
    # 30-80 ms window sat +3.2 dB where the recording falls 5.3, and that swell
    # is what a mallet sounds like. (Crash 2, the same family, carries
    # bloom_gain 0.0 and only a delay -- which is why Ben heard the difference
    # between them as "hit by a mallot, not a stick".)
    #
    # Refitted at velocity 127 against the envelope, with the mode gains
    # re-solved inside each candidate so only the time shape moves:
    #
    #     gain 3.20 sec 0.025   env 5.78  total 13.46   as shipped
    #     gain 0.15 sec 0.008   env 3.54  total  9.61   fitted
    #     gain 0.00             env 3.54  total  9.79   no bloom at all
    #
    # AND THAT LAST ROW IS THE HONEST PART: the bloom is now worth 0.18 dB. It
    # survives as a trace rather than as an audible mechanism, because the
    # measurement cannot tell 0.15 from 0 and a real crash does take tens of
    # milliseconds to spread energy through the plate. If it should be audible
    # again that is an ear call, not a fit -- the fit says it earns nothing.
    bloom_seconds = 0.008
    bloom_gain = 0.15
    bloom_center_hz = 1834.48
    bloom_octaves = 1.73876
    ring_decay_floor = 20
    ring_decay_below = 8
    ring_decay_above = 8
    decay_db = 108.636
    harmonic_decay_db = 0.0200571
    hf_corner_hz = 12305.2
    hf_order = 1.17111
    tonal_dampening = 0.005
    # THE NOISE IS A TRANSIENT, NOT A SUSTAIN. Measured as spectral flatness
    # (1.0 = white noise, 0 = pure tone) at three points in the note, the
    # recording collapses from 0.167 at the strike to 0.002 by 0.4 s: a cymbal is
    # noisy while it is being struck and almost purely tonal once it rings.
    # Ours held 0.49 for the whole note -- a hiss, not a crash, which is why the
    # hit did not stand out from the ring.
    #
    # There was no way to say this before: chiff_volume gates the noise, the
    # attack burst is tied to the speech fade (1.5 ms, since the attack fix),
    # and sustain_jitter is a floor that never decays -- so the wash was either
    # permanently on or a flick. chiff_width decouples the burst from the fade,
    # and that is what lets the noise die on its own schedule.
    # Flatness now 0.168 / 0.001 / 0.000 against the recording's 0.167 / 0.044 / 0.002.
    #
    # It costs band accuracy: 1.98 -> 4.79 dB rms over 0.30 s, because with no
    # sustained wash the ring is only these modes and a real cymbal's is dense.
    # More modes do not recover it (110 modes reaches 4.48). The two measures
    # genuinely disagree and this one is chosen by ear.
    # WET, from the ORCHESTRAL CLASH. Ben: "Real crash cymbals have noise, and
    # the noise is not wet enough by an order of magnitude. Compare with the
    # orchestra crash?" He is right and the factor is literal. Iowa's five clash
    # takes -- two plates slammed together, the one thing in the collection that
    # is properly hit -- against the 17" suspended crash struck with a stick:
    #
    #                        strike   0.1-0.3s     ring
    #     orchestral clash    0.323      0.135    0.020
    #     17" stick crash     0.167      0.044    0.002
    #                          1.9x       3.1x      10x
    #
    # and the clash is 12 dB louder besides. The stick takes are a percussionist
    # controlling a suspended cymbal; a crash in a kit is the clash gesture. What
    # makes it "wet" is not the strike -- that was only 1.9x -- but that the noise
    # LASTS: 0.135 still at a third of a second, where our fit had it collapsing
    # to nothing by then. chiff_width carries that, and it is why this needed
    # three parameters and not a louder wash.
    #
    # Fitted to the clash trajectory at full velocity. The mode set is still this
    # plate's own recording; only how hard it is hit comes from the clash.
    chiff_volume = 3.99359
    sustain_jitter = 0.02
    chiff_width = 0.25078
    # how much noisier this plate gets as it is struck harder, fitted so the
    # flatness at the mf velocity matches the mf recording.
    strike_noise_slope = 0.8321
    # The wobble, scaled by how hard it was struck: one voice per partial
    # offset 1.6 Hz, beating in the measured 0.7-3 Hz band. Depth comes out
    # 19.3% at velocity 127 and 9.5% at 70, against the 17" crash's measured
    # 16.2% at ff and 9.0% at mf.
    strike_wobble_hz = 1.6
    strike_wobble_gain = 0.3
    # +9 dB by ear (Ben, against the hi-hat, which is the loudest thing in
    # the kit and the reference here): "The hi-hat sounds the loudest. The ride
    # could probably be another 3 dB louder, and the other cymbals more like 9."
    # Levels BETWEEN cymbals are not measurable from the Iowa set -- its ff
    # varies 10 dB between crash takes -- so this one is a mix decision and is
    # labelled as one. The band profiles above are the measurement.
    # ...then the whole group down 8 dB together, so the balance above is kept
    # while the kit stops crowding the bass. Ben, on a drum-and-bass track:
    # "The bass is now too quiet, so I think the whole kit needs to go lower."
    initial_gain = 0.196926

class TelephoneRingProperties(MetalPercussionProperties):
    """GM 124. A BELL STRUCK TWENTY TIMES A SECOND, which is what a telephone is.

    Ben: "Telephone ring is just a percussion instrument repeated, like the bell
    sweep. We can model that physically, no problem." That is right, and it is a
    better reading than the one this file used to carry -- a note saying US
    ringback is 440+480 Hz gated. That IS the ringback, but ringback is the tone
    the CALLER hears in the earpiece, generated by the exchange. The thing in the
    room, the thing GM names, is a pair of gongs and an electromagnet slamming a
    clapper between them at the armature's rate.

    So it is a struck metal percussion voice -- an inharmonic bell -- repeated at
    the clapper rate. The repetition uses the mechanism GM 102 established, and
    its one limitation there is exactly right here: those taps are repeated
    ONSETS rather than a repeated signal, which is wrong for an echo and is
    precisely what a clapper does.

    ONE THING HAD TO GIVE. The renderer caps an extra voice's entry at a quarter
    of the note so a section's scatter cannot begin after a short note ends. A
    ring is struck for its whole length, so unison_onset_fraction_max is raised
    -- otherwise the bell rings for the first quarter of each burst and then
    sits silent, which is not a telephone.

    THE CADENCE IS THE SCORE'S, not the voice's. British ring is two short
    bursts and a long gap, American one long burst and a longer gap, and a voice
    that baked either in would be wrong wherever it went. The note IS the burst.
    """
    # A small steel gong pair. Two gongs tuned slightly apart is what gives a
    # telephone its warble, and the second is a cent-level offset rather than a
    # separate mode -- so it is in the taps below, not here.
    # NOT ALSO STRETCHED. MetalPercussionProperties carries an
    # inharmonicity coefficient of 0.026, and a stated mode set riding a
    # stiffness stretch on top of it lands at neither -- which is exactly
    # the bug that put the steelpan's octave 66 cents sharp. The selftest
    # check written for that caught this one before it was ever heard.
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    mode_ratios = (1.0, 2.76, 5.40, 8.93)
    mode_gains = (1.0, 0.62, 0.30, 0.12)
    max_harmonic = 4

    # THE CLAPPER. About twenty strikes a second is a common armature rate;
    # these are 48 ms apart, and they do not fall away, because an electromagnet
    # does not get tired. Alternating gongs: the taps sit a few cents apart, the
    # two bells the clapper is bouncing between.
    ring_taps = tuple(0.048 * (i + 1) for i in range(18))
    ring_detune_cents = 9.0     # the second gong
    ring_gain = 0.92
    unison_onset_fraction_max = 0.96

    decay_db = 26.0             # each strike is short: the next one is coming
    harmonic_decay_db = 9.0
    sustain_level = 0.0
    one_shot = False            # the ring lasts as long as it is written to
    initial_gain = MetalPercussionProperties.initial_gain

    def section_onsets_at(self, frequency):
        return [0.0] + list(self.ring_taps)

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        # Alternate gongs: every other strike is the other bell.
        out = []
        for i in range(len(self.ring_taps)):
            det = (2.0 ** (self.ring_detune_cents / 1200.0) - 1.0) if i % 2 else 0.0
            out.append((self.ring_gain, 0.0, det, harmonic_decay, 0.0))
        return out


class HelicopterProperties(SawtoothSynthProperties):
    """GM 125. THE BLADE PASSING FREQUENCY, which is a sawtooth at 15 Hz.

    Ben: "The helicopter is simply a very low sawtooth, with maybe some chiff?"
    Which is the physics. A rotor with N blades turning at R revolutions per
    second slams a pressure pulse past any fixed point N*R times a second: four
    blades at four revolutions is sixteen pulses, and that is far below pitch,
    so it is heard as CHOPPING rather than as a note. The harmonics of that
    pulse train are the whole sound, and a sawtooth is a pulse train.

    It is the only voice in this bank whose fundamental is below hearing. What
    reaches the ear is the series above it -- which is why a helicopter is
    recognisable at all, and why it sounds different near and far: distance
    removes the top of the series and leaves the chop.

    FOUR OCTAVES DOWN, so the written note picks the rotor speed instead of a
    pitch. Middle C gives about 16 Hz, which is a medium helicopter; an octave
    down is a heavy-lift machine and an octave up a small one. Without the shift
    a written C4 would be a 261 Hz buzz, which is a wasp.

    AND THE CHIFF IS THE ROTOR WASH. Ben's "maybe some chiff" is exactly the
    right hook: turbulence off the blade tips and the turbine behind them are
    broadband, and sustain_jitter broadens every partial into a band -- the same
    mechanism the pan pipe uses for air past an edge, turned well up.
    """
    # Four octaves down: the note chooses the rotor, not the pitch.
    sounding_octaves = -4.0

    max_harmonic = 64           # the audible sound is ALL harmonics, no fundamental
    decay_db = 0.0
    harmonic_decay_db = 0.0
    sustain_level = 1.0
    attack_time = 0.35          # a rotor takes a moment to come up
    speech_cycles = 0.0
    chiff_volume = 0.0

    sustain_jitter = 0.75       # the wash: broader than any other voice here
    section_players = 1
    section_spread_cents = 0.0
    section_vibrato_cents = 0.0

    initial_gain = 0.02         # balance-normalised below


class BirdTweetProperties(MetalPercussionProperties):
    """GM 123. A CHIRP: a nearly pure tone whose pitch sweeps, fast.

    Ben: "The bird tweet is just a chirp. That should be easy?" It is, because
    the two things it needs both exist. A songbird's syrinx produces a very pure
    tone -- two or three partials, not a spectrum -- and what makes it a bird
    rather than a whistle is that the pitch MOVES, a long way and in a tenth of
    a second.

    THE SWEEP IS tension_bend, for the third time in this file and in the third
    direction. It is a pitch transient that blooms and settles, written for the
    piano, where a hard blow stretches the string and the pitch sags back; the
    synth drum uses it falling, at a fifth, for an 808 tom. A bird rises, so the
    bend is NEGATIVE -- the note starts flat and climbs to its written pitch --
    which the steelpan work made possible when it fixed a register scaling that
    silently skipped any voice whose bend was not positive.

    A TWEET IS NOT ONE CHIRP. Birds repeat, fast, and the repetition is as much
    of the identity as the sweep -- so this uses the telephone's clapper
    mechanism at a bird's rate. Four chirps in a third of a second.

    ASSERTED, NOT MEASURED, and the gap is worth naming: real birdsong sweeps
    are not exponential settles, they are arbitrary contours, and several
    species sweep DOWN or up-then-down. This is one chirp shape standing in for
    a very large family.
    """
    # Two partials and a whisper of a third: a syrinx is close to a sine.
    # NOT ALSO STRETCHED. MetalPercussionProperties carries an
    # inharmonicity coefficient of 0.026, and a stated mode set riding a
    # stiffness stretch on top of it lands at neither -- which is exactly
    # the bug that put the steelpan's octave 66 cents sharp. The selftest
    # check written for that caught this one before it was ever heard.
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    mode_ratios = (1.0, 2.0, 3.0)
    mode_gains = (1.0, 0.09, 0.02)
    max_harmonic = 3

    # UP a major third in a tenth of a second, and it is the sweep that makes it
    # a bird. Negative: start flat, climb to the written pitch.
    tension_bend = -0.20
    tension_bend_max = 0.30
    tension_settle_time = 0.035
    tension_settle_cutoff = 0.4

    chirp_taps = (0.085, 0.170, 0.255)
    unison_onset_fraction_max = 0.92
    chirp_gain = 0.85

    decay_db = 16.0
    harmonic_decay_db = 6.0
    sustain_level = 0.0
    one_shot = False
    initial_gain = MetalPercussionProperties.initial_gain

    def section_onsets_at(self, frequency):
        return [0.0] + list(self.chirp_taps)

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        # Each chirp a little higher than the last, as a bird's phrase rises.
        return [(self.chirp_gain, 0.0, 2.0 ** (0.9 * (i + 1) / 12.0) - 1.0,
                 harmonic_decay, 0.0)
                for i in range(len(self.chirp_taps))]


class ReverseCymbalProperties(CrashCymbal1Properties):
    """GM 119. A crash cymbal played BACKWARDS, which the coverage doc listed as
    a category error needing machinery this renderer did not have.

    It has it, and the machinery is the attack. Everything else in this bank
    decays -- a partial can be made to fall faster than its neighbour but not to
    rise -- so a reversed envelope looked impossible. But an ATTACK is a rise,
    and the only thing standing in the way was blockrender's flat cap of 0.45 of
    the note's duration, which is right for every acoustic voice and wrong for
    this one. With attack_fraction_max raised, the attack IS the note: it swells
    for almost its whole length and then stops dead, which is what a reversed
    tape does.

    THE SPECTRUM IS THE MEASURED CYMBAL'S, unchanged. This inherits
    CrashCymbal1Properties and its 300 modes from the Iowa recording -- playing
    a cymbal backwards does not change which modes a cymbal has, only when you
    hear them, so there was nothing to re-fit and nothing to assert. The one
    thing reversal genuinely changes in the spectrum is the ORDER the modes
    arrive in, since a real reversed recording brings the longest-lived ones up
    first; that is not modelled, and it is the honest gap here.
    """
    # The note is the swell. 0.92 rather than 1.0 so a release still exists to
    # stop it with: a reversed cymbal ends abruptly, but a step is a click.
    attack_fraction_max = 0.92
    attack_time = 6.0           # longer than any note; the cap is what binds
    release_valve_time = 0.010  # it stops dead

    # AND IT IS NOT A ONE-SHOT, which every other cymbal here is. A struck
    # cymbal ignores note-off and rings out because nothing stops it, so
    # blockrender extends it to 8 s -- and with the attack capped at a fraction
    # of the DURATION, that made this voice swell for 7.4 s whatever was
    # written. Measured, a 3-second note peaked at 4.84 s: past its own end.
    #
    # A reverse cymbal is the opposite case. It is a recording played backwards
    # and it stops when the recording stops, which is the whole point of the
    # effect: it exists to ARRIVE somewhere, and an arrival that lands a second
    # and a half after the downbeat is not one. So the written note-off is the
    # arrival, and the swell is fitted to it.
    one_shot = False

    # NOT decaying while it swells. The crash it inherits from falls away over
    # seconds, which fought the rise and left a hump in the middle.
    decay_db = 0.0
    harmonic_decay_db = 0.0
    sustain_level = 1.0
    initial_gain = CrashCymbal1Properties.initial_gain


class SynthDrumProperties(MembraneDrumProperties):
    """GM 118. An ELECTRONIC drum, which is not a membrane and not a bar.

    Also listed as a category error, and it was on the generic mallet base.
    What a synth drum is -- a Simmons pad, a TR-808 tom, every drum machine of
    that era -- is an oscillator with a fast DOWNWARD PITCH SWEEP and a fast
    decay. The sweep is the entire signature: without it the sound is a dull
    thud, and with it, it is unmistakably a drum machine.

    THE SWEEP NEEDED NOTHING NEW. tension_bend is a pitch transient that blooms
    and settles to the tuned pitch, scaled by how hard the note was struck --
    written for the piano, where a hard blow stretches the string and the pitch
    sags back. An 808 tom is the same shape and far more of it: start sharp,
    fall to pitch, and do it in a fifth of a second.

    It keeps a membrane's mode set rather than a bar's, because a drum machine's
    designers were imitating a drum and voiced their filters to match -- but
    with very few modes, because an oscillator has few and the pads famously
    sound nothing like a real head.
    """
    # THE SWEEP. tension_bend_max is raised because the piano's 0.04 cap exists
    # to stop a bass fff bending absurdly, and here the bend IS the sound -- the
    # same argument GuitarFretNoiseProperties makes for a slide up the neck.
    tension_bend = 0.55         # start a fifth-ish sharp
    tension_bend_max = 0.70
    tension_settle_time = 0.055 # and fall to pitch in a fifth of a second
    tension_settle_cutoff = 0.5

    # Few modes, and mostly the fundamental: an oscillator, not a head.
    mode_ratios = (1.0, 1.58, 2.14)
    mode_gains = (1.0, 0.14, 0.05)
    max_harmonic = 3

    decay_db = 9.0
    harmonic_decay_db = 5.0
    sustain_level = 0.0
    initial_gain = MembraneDrumProperties.initial_gain


class ElectronicKickProperties(SynthDrumProperties):
    """Note 36 of the Electronic set (SC-55 p.70, "Elec BD"). A synth tom
    tuned down to a kick: the same oscillator and the same downward sweep, but
    a narrower one and a faster one -- a kick has to land on the beat, so its
    fall must be over before the next sixteenth, and a fifth of drop at 55 Hz
    already sounds like the pad it is.

    NOT register-scaled: tension_bend_slope is 0, so the drop is what is
    written here at any tuning, the argument GuitarFretNoiseProperties makes.
    """
    tension_bend = 0.45
    tension_bend_max = 0.45
    tension_bend_slope = 0.0
    tension_settle_time = 0.035
    tension_settle_cutoff = 0.35
    mode_ratios = (1.0, 1.58)
    mode_gains = (1.0, 0.08)
    max_harmonic = 2
    decay_db = 7.0


class ElectronicSnareProperties(ElectricSnareProperties):
    """Note 38 of the Electronic set ("Elec SD"). The Simmons snare, which is
    the drum machine's snare with its body let loose: where note 40 of the
    Standard kit is an 808 -- a crack, a body that barely drops -- a Simmons
    pad pitch-sweeps its snare as it does its toms, and that "pew" under the
    noise is the sound of the whole decade.
    """
    tension_bend = 0.35
    tension_bend_max = 0.50
    tension_bend_slope = 0.0
    tension_settle_time = 0.045
    tension_settle_cutoff = 0.4
    decay_db = 32.0             # a little longer than the 808's crack


class GatedSnareProperties(SnareDrumProperties):
    """Note 40 of the Electronic set ("Gated SD"). An acoustic snare in a big
    room with a noise gate on the reverb: the tail HOLDS, then stops dead.

    THE STOP IS THE SOUND, and nothing here decays into it. So this is the
    snare's own modes with the decay slowed to let the room carry, and a GATE:
    `gate_time` is the one-shot's length instead of the eight seconds every
    other struck voice is allowed to ring, and release_valve_time is the
    gate's own close -- fast, but not a step, because a step is a click.
    """
    decay_db = 14.0
    harmonic_decay_db = 10.0
    gate_time = 0.30
    release_valve_time = 0.015


# ---- the Brush set (SC-55 p.70, program 40): three notes, all on the snare ---
# A wire brush is a fan of a hundred-odd fine wires. What that changes about a
# snare stroke, and nothing here goes further than this:
#
#   the wires land over a few milliseconds, not in one instant, so the attack
#   is a soft smear where a stick is a click;
#   they strike an AREA, and an area excites a membrane's high modes less than
#   a point does -- the high modes' nodal lines fall inside the contact and
#   cancel -- so the head is darker;
#   and the brush is light, so the head is driven less and the snare wires
#   under it are a larger share of what is heard.
#
# No reference: the SC-55's samples are not to hand and Iowa has no kit. The
# gains and times are judgement, the level is matched to the Standard note each
# replaces (examples/drumset_check.py), and Ben's ear is the calibration.
_BRUSH_GAINS = tuple(g ** 1.6 for g in SnareDrumProperties.mode_gains)


class BrushTapProperties(SnareDrumProperties):
    """Note 38 of the Brush set: a brush tapped on the head, snares on."""
    mode_gains = _BRUSH_GAINS
    chiff_min_valve_time = 0.005    # the wires land over ~5-18 ms
    chiff_max_valve_time = 0.018
    attack_time = 0.006
    chiff_volume = 9.0
    tension_bend = 0.008            # a light blow stretches the head less
    decay_db = 58.0                 # the brush stays on a moment and damps it
    strike_noise_slope = 0.25


class BrushSlapProperties(BrushTapProperties):
    """Note 39: the brush slapped FLAT onto the head. More wires, harder, and
    it lies there afterwards -- a loud wash with the head choked under it."""
    chiff_min_valve_time = 0.003
    chiff_max_valve_time = 0.010
    attack_time = 0.003
    chiff_volume = 16.0
    chiff_width = 0.060
    decay_db = 85.0


class BrushSwirlProperties(SnareDrumProperties):
    """Note 40: the brush swept round the head in circles. There is no strike
    at all: friction drives the head CONTINUOUSLY, so what sounds is the head's
    own modes excited by noise -- each broadened into a band -- with the wires
    faintly buzzing under it. That is sustain_jitter at full with the strike
    ramped away, and a slow decay rather than a ring."""
    mode_gains = _BRUSH_GAINS
    chiff_volume = 6.0
    chiff_cycle = 1.0
    sustain_jitter = 1.0            # the noise runs the whole note
    attack_time = 0.12              # it swells in; nothing strikes
    tension_bend = 0.0
    strike_noise_slope = 0.0
    decay_db = 9.0
    harmonic_decay_db = 6.0



class CrashCymbal2Properties(CymbalProperties):
    """GM 57, Crash Cymbal 2. MEASURED: Iowa 18" suspended crash. GM asks
    for two crashes and they were the same voice 20 Hz apart; these are two
    different cymbals, and the 18" is the darker and longer of the pair.
    Band rms error 4.17 -> 3.13 dB.
    """
    # A CRASH IS A CONTINUUM, NOT A LINE SPECTRUM, and half our energy was one
    # low tone. Ben, on the A/B against the clash: "our crashes sound completely
    # different... a lot of it seems to be the jitter amount, both bandwidth and
    # volume, is still an order of magnitude off." The jitter itself turned out
    # to be fine -- the kernel redraws its phase every sample, so it is already
    # full-bandwidth white -- but it was being buried. Measured 0.1-0.3 s after
    # the strike, band by band, against the clash:
    #
    #                       300-700   700-1.5k   1.5-3k    3-6k
    #     energy, clash       -24.1      -13.7     -5.7    -3.2
    #     energy, ours         -3.0      -12.1     -8.7   -11.4
    #     peak/median, clash    10.4       20.0     24.8    20.2
    #     peak/median, ours     35.4       25.1     32.1    25.2
    #
    # Half the energy sat in a 300-700 Hz tone the clash barely has, so the wash
    # was spread thin under it, and the partials stood 24-35 dB above the floor
    # between them where a real crash's stand 10-25. That is what "an order of
    # magnitude of jitter" sounds like from the outside; the fix is where the
    # energy is, not how much noise there is.
    #
    # Two changes. The mode gains carry a high-pass shelf so the plate's own low
    # modes stop dominating -- fitted, not chosen -- and the mode set goes from 26
    # to 100, because a sparse set cannot be a continuum however it is weighted.
    # Denser is measurably better on both counts (crash 2's energy error 4.61 ->
    # 1.33 dB, its line-excess 8.0 -> 5.7). It costs partials: 90 per hit.
    # LOOK AT THE WATERFALL. Ben: "Have you been comparing the FFT waterfalls at
    # all?" No -- everything measured up to here was a scalar in a fixed window,
    # which is why three rounds of matching numbers still sounded wrong. The
    # spectrogram says it in one glance: the clash fills the whole time-frequency
    # plane for a second and a half, and ours was a bright vertical smear at the
    # strike and then blue, with a handful of horizontal lines ringing on. A click
    # plus a few resonances. That is "tinny", and it is also "not wet".
    #
    # IT ALSO SHOWED A CONCLUSION OF MINE WAS BACKWARDS. Two commits ago I read
    # the recording's ring flatness of 0.002 as "the noise is a transient, the
    # ring is tonal" and turned the sustained wash off. But low flatness means a
    # PEAKY spectrum, and a cymbal's ring is peaky because it is hundreds of
    # dense resolved modes -- not because it is quiet. The waterfall shows that
    # ring is full of energy. Killing the wash was removing the wrong thing.
    #
    # So: 300 modes, not 26. Measured peaks give the frequencies that can be
    # resolved; the rest are filled to the density a cymbal actually has, with
    # gains read off the clash's own smoothed spectrum. Plus a modest sustained
    # wash, refitted against band energy at FOUR times (0.02, 0.10, 0.35, 0.70 s)
    # rather than one window, so the decay is fitted and not assumed.
    #
    # WHAT IS STILL WRONG, measured at 0.70 s: the clash is mid-focused and dead
    # on top (-9.5 dB at 3-6 kHz, -32 at 10-16); ours is flat at about -18 across.
    # A broadband wash decays with the note's amplitude envelope, uniformly in
    # frequency, so it cannot make that shape -- only modes have per-mode decay.
    # Closing it means either enough modes to carry the sustain alone, or a
    # frequency-dependent wash decay in the kernel. Fit error 5.1 and 6.3 dB.
    # REFITTED on honest frequencies. Everything above was fitted while the
    # measured modes were being stretched by the family's inharmonicity (see
    # CymbalProperties), so every gain, decay, wash and level was compensating
    # for modes in the wrong place. All of it is re-solved here against the
    # recording's band energy at FOUR times -- 0.02, 0.10, 0.35 and 0.70 s --
    # plus how far the lines stand above the continuum, with the level held to
    # what Ben balanced by ear so this changes the sound and not the mix.
    #
    # The ring law is ON here (see CymbalProperties.harmonic_decay): a plate's
    # ring time peaks in the middle and dies at both ends, which the inherited
    # monotonic law cannot express.
    mode_ratios = (1.0000, 1.0390, 1.1510, 1.1987, 1.1987, 1.2060, 1.2283, 1.2300,
                   1.2321, 1.2339, 1.2702, 1.2706, 1.3425, 1.3666, 1.3859, 1.4303,
                   1.4678, 1.4764, 1.4883, 1.5028, 1.5384, 1.5523, 1.5657, 1.6166,
                   1.6219, 1.6282, 1.6295, 1.7241, 1.7547, 1.7773, 1.8535, 1.8600,
                   1.8806, 1.8929, 1.9404, 1.9814, 2.0109, 2.0601, 2.0680, 2.0942,
                   2.0963, 2.1482, 2.2295, 2.3336, 2.3364, 2.3540, 2.3755, 2.4460,
                   2.4548, 2.4602, 2.5015, 2.5258, 2.5689, 2.6149, 2.6620, 2.6671,
                   2.8417, 2.8535, 2.8767, 2.8980, 2.9584, 3.1104, 3.1511, 3.1885,
                   3.2401, 3.2670, 3.3200, 3.3769, 3.4030, 3.4948, 3.5296, 3.6538,
                   3.6713, 3.6940, 3.6969, 3.7600, 3.7670, 3.7999, 3.8471, 3.9720,
                   4.0367, 4.1688, 4.1890, 4.2044, 4.3201, 4.4803, 4.4882, 4.6229,
                   4.6380, 4.6500, 4.8481, 4.9314, 4.9317, 4.9380, 5.0448, 5.0470,
                   5.2029, 5.3233, 5.4683, 5.5120, 5.5489, 5.5599, 5.5727, 5.6487,
                   5.9003, 5.9205, 6.3516, 6.3808, 6.3845, 6.5191, 6.6292, 6.7070,
                   6.7800, 6.7910, 6.8450, 6.8770, 6.9250, 6.9502, 6.9726, 6.9947,
                   7.0190, 7.0600, 7.1183, 7.1490, 7.1920, 7.3262, 7.5532, 7.5706,
                   7.7180, 7.9865, 8.0042, 8.2135, 8.6070, 8.6136, 8.7505, 8.8203,
                   8.8635, 8.8970, 8.9760, 9.0490, 9.1330, 9.2060, 9.2184, 9.2550,
                   9.4394, 9.5547, 9.7099, 9.7384, 9.9312, 10.1760, 10.3300,
                   10.3877, 10.8300, 10.9284, 10.9559, 11.0521, 11.0621, 11.1190,
                   11.1206, 11.2900, 11.4569, 11.4756, 11.5005, 11.8860, 12.0958,
                   12.1450, 12.3179, 12.8040, 12.9546, 13.0015, 13.3680, 13.4502,
                   13.6170, 13.6430, 13.9113, 13.9691, 14.0200, 14.4620, 14.4900,
                   14.5770, 14.8792, 15.0129, 15.0476, 15.2373, 15.2720, 15.3904,
                   15.3972, 15.5970, 15.6490, 16.0539, 16.2470, 16.5148, 16.6381,
                   16.6909, 16.8505, 16.9226, 17.1340, 18.1320, 18.1883, 18.7583,
                   18.7750, 18.8682, 18.9862, 19.1170, 19.1620, 19.2694, 19.4703,
                   19.6270, 19.6731, 20.4437, 20.5487, 20.5890, 20.6420, 20.9885,
                   21.3982, 21.6840, 21.8810, 22.3120, 22.4269, 22.8560, 22.9220,
                   23.0420, 23.3799, 23.7593, 23.9867, 24.2090, 24.4527, 24.8785,
                   24.9711, 25.1740, 25.3080, 25.3679, 25.5020, 26.2410, 26.5440,
                   26.8700, 26.9675, 27.1842, 27.2811, 27.4940, 27.5634, 27.7140,
                   27.7660, 28.5234, 28.9909, 29.0171, 29.4486, 29.4630, 29.9820,
                   30.0980, 30.8370, 30.9370, 31.1670, 31.3288, 31.8820, 32.1460,
                   32.4590, 32.8021, 32.8198, 33.0551, 33.1969, 33.7390, 33.8420,
                   34.0330, 34.9790, 35.0670, 35.1570, 35.2668, 35.7669, 35.9390,
                   36.0420, 36.1163, 36.4190, 37.0164, 37.3400, 37.4370, 37.8020,
                   38.6636, 38.8090, 39.0564, 39.2636, 39.3098, 39.6299, 40.0860,
                   40.2760, 40.4430, 40.8000, 42.6896, 42.7359, 42.9190, 43.1220,
                   43.3620, 43.5612, 44.2380, 44.5398, 45.7551, 45.9850, 46.3220,
                   46.6924, 47.7164)
    # THE GAINS COME FROM THE STRIKE, NOT THE RING, and that is the wah. Ben:
    # "The left crash is still wah sounding at the beginning." A rising band of
    # energy is a filter sweep, and the spectral centroid says ours was doing
    # exactly that:
    #
    #                    at 10 ms    at 0.5 s
    #     clash            8129 Hz     3428 Hz    falls -- bright hit, darker ring
    #     17" stick        8673        2601      falls
    #     ours             3630        4012      RISES
    #
    # -- and ours rose with the bloom switched OFF, so it was never the bloom. I
    # had read these mode gains off the clash's envelope at 0.10-0.30 s, which is
    # its RING, so our strike inherited the ring's balance and then brightened
    # toward it. The gains belong to the strike; the ring law is what darkens the
    # tail afterwards. Re-read from 2-32 ms, the centroid falls: 7074 -> 6082.
    #
    # The same window mistake as the hi-hat's mode set and the guiro's, in the
    # third place: measuring the right quantity over the wrong span of the note.
    mode_gains  = (1.0000, 0.9407, 0.5889, 0.1006, 0.1006, 0.1030, 0.1080, 0.1080,
                   0.1081, 0.1081, 0.1079, 0.1079, 0.1833, 0.2402, 0.2836, 0.3592,
                   0.3828, 0.3801, 0.3763, 0.3695, 0.3233, 0.3012, 0.2762, 0.1760,
                   0.1651, 0.1510, 0.1480, 0.0965, 0.0966, 0.0948, 0.0887, 0.0881,
                   0.0861, 0.0849, 0.0783, 0.0688, 0.0599, 0.0483, 0.0462, 0.0485,
                   0.0488, 0.0588, 0.0784, 0.1185, 0.1216, 0.1397, 0.1590, 0.1646,
                   0.1678, 0.1698, 0.1739, 0.1739, 0.1709, 0.1650, 0.1461, 0.1436,
                   0.0659, 0.0634, 0.0605, 0.0592, 0.0562, 0.0620, 0.1324, 0.1951,
                   0.3164, 0.3989, 0.5259, 0.6446, 0.6923, 0.7442, 0.7505, 0.6990,
                   0.6781, 0.6499, 0.6462, 0.5475, 0.5339, 0.4650, 0.3565, 0.2210,
                   0.1864, 0.1474, 0.1436, 0.1474, 0.1912, 0.2140, 0.2182, 0.2652,
                   0.2659, 0.2665, 0.1350, 0.1285, 0.1285, 0.1281, 0.1128, 0.1122,
                   0.0715, 0.0635, 0.1157, 0.1292, 0.1395, 0.1424, 0.1458, 0.1659,
                   0.2066, 0.2070, 0.1466, 0.1379, 0.1367, 0.0874, 0.1034, 0.1133,
                   0.1171, 0.1176, 0.1202, 0.1217, 0.1229, 0.1224, 0.1219, 0.1215,
                   0.1210, 0.1201, 0.1189, 0.1185, 0.1179, 0.1160, 0.0792, 0.0829,
                   0.1095, 0.2192, 0.2256, 0.3019, 0.4484, 0.4484, 0.4456, 0.4356,
                   0.4293, 0.4244, 0.4125, 0.3992, 0.3823, 0.3670, 0.3643, 0.3563,
                   0.2516, 0.4048, 0.3553, 0.3454, 0.3687, 0.4682, 0.4991, 0.5101,
                   0.6421, 0.6413, 0.6410, 0.6402, 0.6390, 0.6283, 0.6280, 0.5953,
                   0.5651, 0.5622, 0.5583, 0.5204, 0.5210, 0.5269, 0.5470, 0.5712,
                   0.5642, 0.5620, 0.6132, 0.6383, 0.6806, 0.6840, 0.7174, 0.7244,
                   0.7323, 0.7897, 0.7888, 0.7857, 0.7667, 0.7395, 0.7323, 0.6914,
                   0.6836, 0.6403, 0.6377, 0.5567, 0.5337, 0.5446, 0.5729, 0.6180,
                   0.6377, 0.6440, 0.6452, 0.6456, 0.6473, 0.6025, 0.5956, 0.5267,
                   0.5250, 0.5154, 0.5553, 0.5399, 0.5344, 0.5212, 0.5279, 0.5404,
                   0.5439, 0.4993, 0.4893, 0.4860, 0.4817, 0.4521, 0.4724, 0.4988,
                   0.5796, 0.7518, 0.7731, 0.7775, 0.7781, 0.7795, 0.8029, 0.8251,
                   0.8190, 0.8130, 0.8017, 0.6789, 0.6492, 0.5821, 0.5689, 0.5628,
                   0.5490, 0.4858, 0.4677, 0.4720, 0.4785, 0.4926, 0.4988, 0.5129,
                   0.5202, 0.5357, 0.5410, 0.5961, 0.6047, 0.6053, 0.6336, 0.6347,
                   0.6762, 0.6742, 0.6379, 0.6313, 0.6086, 0.5920, 0.5397, 0.5461,
                   0.5533, 0.5595, 0.5589, 0.5498, 0.5442, 0.5223, 0.5341, 0.5589,
                   0.6661, 0.6746, 0.6832, 0.6935, 0.7387, 0.7364, 0.7331, 0.7307,
                   0.7211, 0.7082, 0.7114, 0.7123, 0.6753, 0.7088, 0.7151, 0.7259,
                   0.7325, 0.7338, 0.7432, 0.7562, 0.7626, 0.7742, 0.7985, 0.8943,
                   0.8928, 0.8861, 0.8785, 0.8697, 0.8621, 0.8241, 0.7985, 0.7097,
                   0.6986, 0.6819, 0.6616, 0.5800)
    max_harmonic = 300
    aftersound_fraction = 0.08
    aftersound_ratio = 0.06
    # Each mode gets its own strike sign (see strike_phase_spread): with 300
    # modes all starting in phase the note peaked 21.5 dB above its own loudness against the 17" clash's 13.1.
    strike_phase_spread = 1.0
    # THE MODES CARRY THE TOP. The refit before this chose hf_corner_hz = 3153 at
    # order 5, which annihilates modal energy above 3 kHz -- 0.03 of it left at
    # 6.3 kHz, 0.0003 at 15.9 -- so nothing up there was a mode and the WASH was
    # the whole top of the instrument. The fit was free to do that because the
    # chiff is a phase-randomised copy of each partial and so spreads broadband
    # whatever its partial's frequency: turn the modes off up top and the wash
    # covers, and no measure of the spectrum alone can tell the difference.
    #
    # It matters because a wash cannot decay per band and cannot arrive late.
    # Both of the last two commits -- the ring law, and the bloom -- were being
    # smothered by it. Refitted with the roll-off held gentle and well above the
    # band, so the modes reach 16 kHz on their own:
    #
    #     crash 1   grid 5.57 -> 4.94 dB   line excess 5.3 -> 3.7   chiff 11.3 -> 4.0
    #     crash 2   grid 7.02 -> 3.63      line excess 6.5 -> 7.0   chiff  6.9 -> 4.0
    ring_peak_hz = 2672.65
    # The bloom. Sized from the takes that actually bloom rather than the median
    # of all of them: at the median 139 ms the strike transient still outranks it
    # and no delayed peak appears at all, which is a threshold, not a gradient.
    # 205 ms puts the 3.2-6.4 kHz peak at 427 ms against the 18" clash's 416,
    # and it is scaled by strike force, so a soft crash does not bloom.
    # FITTED AGAINST T60 AND THE ATTACK, not through the band grid. The ring
    # coefficients had been coming along for the ride in a fit that optimised
    # band energy, and the bloom was set by hand to one number for both crashes.
    # Ben, listening to grunge.mid: "one of them has a weirdly gradual attack...
    # positioned on the right" -- which is crash 2, panned +0.6, playing eight
    # hits at velocity 127 and so getting the full bloom.
    #
    # THE BLOOM WAS ON A CRASH WHOSE OWN RECORDING DOES NOT BLOOM. The 18" clash
    # has a 416 ms mid-band delay and the 17" has 32 ms; I measured that, wrote
    # it down, and then set both crashes to 205 ms anyway. Measured as the time
    # to reach 3 dB below peak, ours took 187-191 ms where the real clashes take
    # 26-35: a real plate blooms in the MIDDLE while its low and high still
    # arrive at once, so delaying too wide a slice softens the whole attack.
    #
    #                 attack        bloom depth        T60 error
    #     crash 1   191 -> 63 ms   +8.1 vs +8.1 dB    1.35 octaves
    #     crash 2   187 -> 24 ms   -6.9 vs -3.4       0.87 octaves
    #
    # (crash 2's target attack is 26 ms and its bloom_seconds now 16 -- which is
    # its recording saying it does not bloom, rather than a knob turned down.)
    bloom_seconds = 0.0161662
    bloom_center_hz = 5661.91
    bloom_octaves = 1.70142
    ring_decay_floor = 44.2985
    ring_decay_below = 6.65704
    ring_decay_above = 151.364
    decay_db = 5.69981
    harmonic_decay_db = 0.325081
    hf_corner_hz = 38680.9
    hf_order = 1.00984
    tonal_dampening = 0.01806
    # THE NOISE IS A TRANSIENT, NOT A SUSTAIN. Measured as spectral flatness
    # (1.0 = white noise, 0 = pure tone) at three points in the note, the
    # recording collapses from 0.140 at the strike to 0.006 by 0.4 s: a cymbal is
    # noisy while it is being struck and almost purely tonal once it rings.
    # Ours held 0.56 for the whole note -- a hiss, not a crash, which is why the
    # hit did not stand out from the ring.
    #
    # There was no way to say this before: chiff_volume gates the noise, the
    # attack burst is tied to the speech fade (1.5 ms, since the attack fix),
    # and sustain_jitter is a floor that never decays -- so the wash was either
    # permanently on or a flick. chiff_width decouples the burst from the fade,
    # and that is what lets the noise die on its own schedule.
    # Flatness now 0.140 / 0.044 / 0.006 against the recording's 0.140 / 0.044 / 0.006.
    #
    # It costs band accuracy: 3.13 -> 6.14 dB rms over 0.30 s, because with no
    # sustained wash the ring is only these modes and a real cymbal's is dense.
    # More modes do not recover it (110 modes reaches 4.48). The two measures
    # genuinely disagree and this one is chosen by ear.
    # WET, from the ORCHESTRAL CLASH. Ben: "Real crash cymbals have noise, and
    # the noise is not wet enough by an order of magnitude. Compare with the
    # orchestra crash?" He is right and the factor is literal. Iowa's five clash
    # takes -- two plates slammed together, the one thing in the collection that
    # is properly hit -- against the 17" suspended crash struck with a stick:
    #
    #                        strike   0.1-0.3s     ring
    #     orchestral clash    0.323      0.135    0.020
    #     17" stick crash     0.167      0.044    0.002
    #                          1.9x       3.1x      10x
    #
    # and the clash is 12 dB louder besides. The stick takes are a percussionist
    # controlling a suspended cymbal; a crash in a kit is the clash gesture. What
    # makes it "wet" is not the strike -- that was only 1.9x -- but that the noise
    # LASTS: 0.135 still at a third of a second, where our fit had it collapsing
    # to nothing by then. chiff_width carries that, and it is why this needed
    # three parameters and not a louder wash.
    #
    # Fitted to the clash trajectory at full velocity. The mode set is still this
    # plate's own recording; only how hard it is hit comes from the clash.
    chiff_volume = 3.99984
    sustain_jitter = 0.0113248
    chiff_width = 0.367686
    # how much noisier this plate gets as it is struck harder, fitted so the
    # flatness at the mf velocity matches the mf recording.
    strike_noise_slope = 0.6763
    # The wobble, scaled by how hard it was struck: one voice per partial
    # offset 1.6 Hz, beating in the measured 0.7-3 Hz band. Depth comes out
    # 19.3% at velocity 127 and 9.5% at 70, against the 17" crash's measured
    # 16.2% at ff and 9.0% at mf.
    strike_wobble_hz = 1.6
    strike_wobble_gain = 0.3
    # +9 dB by ear (Ben, against the hi-hat, which is the loudest thing in
    # the kit and the reference here): "The hi-hat sounds the loudest. The ride
    # could probably be another 3 dB louder, and the other cymbals more like 9."
    # Levels BETWEEN cymbals are not measurable from the Iowa set -- its ff
    # varies 10 dB between crash takes -- so this one is a mix decision and is
    # labelled as one. The band profiles above are the measurement.
    # ...then the whole group down 8 dB together, so the balance above is kept
    # while the kit stops crowding the bass. Ben, on a drum-and-bass track:
    # "The bass is now too quiet, so I think the whole kit needs to go lower."
    initial_gain = 0.088314

class SplashCymbalProperties(CymbalProperties):
    """GM 55, Splash Cymbal.

    The last plate still on a first-pass wash, and its fault was the hi-hats'
    rather than the ride's: 200 modes is already a continuum, but with the wash
    WHITE its lines stood 5 dB further above that continuum than the recording's
    do, and turning the wash up would have flattened the spectrum as fast as it
    filled between them. Banded (see chiff_bandwidth), it lands at 1.5 dB.

    The plate is re-extracted too. The old one was floored at 400 Hz; a splash
    has confirmed modes down to 143.

    Loss curve fitted on both windows, strike and tail, like the rest of the
    family: this plate rings longest at 700 Hz -- the lowest of any of them,
    which is what a small thin cymbal should do, since a splash is all edge and
    almost no bell.
    """
    mode_ratios = (1.0000, 1.5254, 1.9055, 2.1447, 2.2169, 3.0188, 3.9539, 4.0657,
                   4.2903, 4.6542, 4.6953, 5.0602, 5.1969, 6.0214, 6.4632, 6.8891,
                   7.3461, 7.6114, 8.7373, 9.8870, 10.4356, 10.8609, 12.4332, 12.7311,
                   12.9789, 14.1714, 14.4262, 15.3409, 16.2557, 16.9387, 18.5001, 18.8333,
                   18.9718, 19.5911, 19.9395, 20.9208, 21.2606, 21.6137, 21.8750, 22.6416,
                   23.5057, 23.9269, 24.5242, 25.3006, 25.6636, 26.1063, 26.2832, 26.9718,
                   28.4488, 29.1209, 29.6616, 30.2031, 30.4999, 30.8048, 31.4761, 32.3710,
                   33.3452, 33.7631, 34.0561, 34.3930, 35.7658, 36.9674, 37.2736, 37.9260,
                   38.9519, 40.0954, 40.2686, 41.2210, 41.8013, 42.4168, 43.1773, 44.2809,
                   44.5685, 44.8224, 45.2979, 45.6416, 46.4502, 46.9436, 47.7781, 48.2659,
                   48.7587, 49.0156, 49.2727, 49.7276, 50.1876, 50.7884, 51.4963, 51.7552,
                   52.2278, 52.7796, 53.4494, 53.8524, 54.2868, 55.0963, 55.3563, 56.6278,
                   57.3945, 58.3000, 59.3164, 60.3328, 61.3622, 61.6249, 61.9930, 62.3669,
                   63.4030, 64.4391, 65.1218, 65.4009, 65.7173, 66.2824, 67.5415, 68.5853,
                   68.9762, 70.0652, 70.9453, 71.8254, 72.8597, 73.4338, 73.9140, 74.8301,
                   75.7461, 76.3193, 76.7332, 77.2650, 77.7159, 78.2753, 78.7652, 79.6628,
                   80.5040, 81.0746, 81.8265, 82.6390, 82.9859, 83.8061, 84.6264, 85.7787,
                   86.3023, 87.1127, 87.8183, 88.5718, 89.6265, 90.6812, 91.7097, 92.7382,
                   94.1435, 95.1479, 95.7291, 96.4388, 97.1873, 97.8776, 98.7790, 99.6403,
                   100.5016, 101.0326, 101.9388, 102.8450, 103.8914, 104.8386, 105.4717, 106.7323,
                   107.2744, 108.1189, 108.9675, 109.8162, 110.6648, 111.5324, 112.3338, 113.1351,
                   113.9364, 114.7377, 115.5390, 116.3404, 117.1417, 117.9430, 118.7443, 119.5457,
                   120.3470, 121.1483, 121.9496, 122.7509, 123.5523, 124.3536, 125.1549, 125.9562,
                   126.7576, 127.5589, 128.3602, 129.1615, 129.9628, 130.7642, 131.5655, 132.3668,
                   133.1681, 133.9695, 134.7708, 135.5721, 136.3734, 137.1747, 137.9761, 138.7774)
    mode_gains  = (0.0083, 0.0004, 0.0009, 0.0010, 0.0008, 0.0000, 0.0000, 0.0000,
                   0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0415, 0.0224, 0.0355,
                   0.0295, 0.1068, 0.4156, 0.2665, 0.2375, 0.2152, 0.0457, 0.0189,
                   0.0344, 0.0435, 0.0292, 0.0775, 0.0446, 0.0435, 0.0358, 0.0102,
                   0.0151, 0.0242, 0.0341, 0.0853, 0.0446, 0.0483, 0.0524, 0.5331,
                   0.1824, 0.1488, 0.1455, 0.0690, 0.0602, 0.0846, 0.0697, 0.0683,
                   0.0927, 0.0775, 0.2024, 0.1299, 0.1540, 0.4777, 0.3544, 0.4467,
                   0.1024, 0.0733, 0.0626, 0.1185, 0.1875, 0.1455, 0.1187, 0.2123,
                   0.3076, 0.1303, 0.2128, 0.3919, 0.2958, 0.1061, 0.1149, 0.2857,
                   0.1694, 0.2198, 0.0886, 0.2175, 0.3899, 0.4219, 0.4699, 0.2460,
                   0.3498, 0.2681, 0.5709, 0.4865, 0.2437, 0.2628, 0.4004, 0.1491,
                   0.2503, 0.1183, 0.1439, 0.1355, 0.2216, 0.5561, 0.4690, 0.6223,
                   0.4360, 0.2551, 0.2984, 0.5283, 0.2322, 0.2160, 0.3505, 0.5539,
                   0.5905, 0.2284, 0.0952, 0.0759, 0.1265, 0.2723, 0.3483, 0.2496,
                   0.3796, 0.3010, 0.2973, 0.3349, 0.0878, 0.1621, 0.1349, 0.1227,
                   0.1788, 0.1245, 0.0852, 0.0781, 0.1486, 0.1267, 0.1974, 0.1333,
                   0.0837, 0.0933, 0.2008, 0.1240, 0.1422, 0.1508, 0.1881, 0.1520,
                   0.2140, 0.3111, 0.3385, 0.4862, 0.5765, 0.4692, 0.6549, 0.5014,
                   0.5970, 0.2096, 0.3727, 0.3676, 0.3327, 0.3906, 0.4205, 0.2355,
                   0.4384, 0.3396, 0.4738, 0.4207, 0.3022, 0.2325, 0.2240, 0.4991,
                   0.3433, 0.5609, 0.4336, 0.2677, 0.1137, 0.3543, 0.2861, 0.1360,
                   0.4492, 0.3033, 0.3943, 0.2139, 0.2233, 0.2741, 0.3015, 0.2576,
                   0.4203, 0.2495, 0.1831, 0.2930, 0.2753, 0.2679, 0.2447, 0.4476,
                   0.1937, 0.1735, 0.2355, 0.1402, 0.3330, 0.3647, 0.2608, 0.3980,
                   0.2642, 0.3054, 0.1749, 0.3601, 0.3433, 0.2146, 0.2346, 1.0000)
    max_harmonic = 200
    aftersound_fraction = 0.50
    aftersound_ratio = 0.20
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    strike_phase_spread = 1.0
    ring_peak_hz = 700.0
    ring_decay_below = 5.0
    ring_decay_floor = 14.4
    ring_decay_above = 3.0
    chiff_volume = 30.0
    chiff_bandwidth = 0.30
    # REFITTED on honest frequencies. Everything above was fitted while the
    # measured modes were being stretched by the family's inharmonicity (see
    # CymbalProperties), so every gain, decay, wash and level was compensating
    # for modes in the wrong place. All of it is re-solved here against the
    # recording's band energy at FOUR times -- 0.02, 0.10, 0.35 and 0.70 s --
    # plus how far the lines stand above the continuum, with the level held to
    # what Ben balanced by ear so this changes the sound and not the mix.
    #
    # The ring law is ON here (see CymbalProperties.harmonic_decay): a plate's
    # ring time peaks in the middle and dies at both ends, which the inherited
    # monotonic law cannot express.
    # Each mode gets its own strike sign (see strike_phase_spread): with 200
    # modes all starting in phase the note peaked 20.9 dB above its own loudness against the Iowa splash's 14.0.
    # THE NOISE IS A TRANSIENT, NOT A SUSTAIN. Measured as spectral flatness
    # (1.0 = white noise, 0 = pure tone) at three points in the note, the
    # recording collapses from 0.283 at the strike to 0.015 by 0.4 s: a cymbal is
    # noisy while it is being struck and almost purely tonal once it rings.
    # Ours held 0.02 for the whole note -- a hiss, not a crash, which is why the
    # hit did not stand out from the ring.
    #
    # There was no way to say this before: chiff_volume gates the noise, the
    # attack burst is tied to the speech fade (1.5 ms, since the attack fix),
    # and sustain_jitter is a floor that never decays -- so the wash was either
    # permanently on or a flick. chiff_width decouples the burst from the fade,
    # and that is what lets the noise die on its own schedule.
    # Flatness now 0.240 / 0.031 / 0.028 against the recording's 0.283 / 0.114 / 0.015.
    #
    # It costs band accuracy: 3.72 -> 3.69 dB rms over 0.30 s, because with no
    # sustained wash the ring is only these modes and a real cymbal's is dense.
    # More modes do not recover it (110 modes reaches 4.48). The two measures
    # genuinely disagree and this one is chosen by ear.
    sustain_jitter = 0.17656
    chiff_width = 0.159161
    # how much noisier this plate gets as it is struck harder, fitted so the
    # flatness at the mf velocity matches the mf recording.
    strike_noise_slope = 0.9312
    # The wobble, scaled by how hard it was struck: one voice per partial
    # offset 1.6 Hz, beating in the measured 0.7-3 Hz band. Depth comes out
    # 19.3% at velocity 127 and 9.5% at 70, against the 17" crash's measured
    # 16.2% at ff and 9.0% at mf.
    strike_wobble_hz = 1.6
    strike_wobble_gain = 0.3
    # +9 dB by ear (Ben, against the hi-hat, which is the loudest thing in
    # the kit and the reference here): "The hi-hat sounds the loudest. The ride
    # could probably be another 3 dB louder, and the other cymbals more like 9."
    # Levels BETWEEN cymbals are not measurable from the Iowa set -- its ff
    # varies 10 dB between crash takes -- so this one is a mix decision and is
    # labelled as one. The band profiles above are the measurement.
    # ...then the whole group down 8 dB together, so the balance above is kept
    # while the kit stops crowding the bass. Ben, on a drum-and-bass track:
    # "The bass is now too quiet, so I think the whole kit needs to go lower."
    initial_gain = 0.299658

class ChineseCymbalProperties(CymbalProperties):
    """GM 52, Chinese Cymbal: a 16" china.

    Dense rebuild, and the plate now reaches its own bottom. The first
    extraction was floored at 400 Hz and its lowest confirmed mode came out at
    497, which cut the cymbal off ABOVE its fundamental -- a china rings down
    into the low 200s, and the recording has real energy there, 21 dB above its
    own room floor in the tail where we had nothing. Confirmed modes go down to
    182 Hz once the floor is lowered.

    THE WASH IS BANDED, not white -- see chiff_bandwidth. THE LOSS CURVE IS
    FITTED ON BOTH WINDOWS, the strike and the tail, because the decay is what
    the spectrum does between them and an envelope alone cannot say which
    partials should have gone.
    """
    mode_ratios = (1.0000, 1.0134, 1.0809, 1.2804, 1.5828, 1.6595, 1.9859, 2.0233,
                   2.7330, 2.9089, 3.1662, 3.2425, 3.3946, 3.5712, 3.8916, 3.9341,
                   3.9669, 4.4762, 4.8671, 4.8890, 4.9237, 4.9942, 5.1761, 5.3190,
                   5.4734, 5.6713, 5.7256, 5.7968, 5.9947, 6.0550, 6.4489, 6.5307,
                   6.5714, 6.6535, 7.1093, 7.1993, 7.3530, 7.9286, 8.1475, 8.3137,
                   8.3502, 8.6512, 8.6933, 8.7402, 8.9547, 9.1294, 9.2000, 9.3548,
                   9.4614, 9.5758, 9.6313, 9.8259, 10.0548, 10.3793, 10.4281, 10.6995,
                   10.7471, 10.9466, 11.0395, 11.3881, 11.5691, 11.6373, 11.7404, 11.8675,
                   12.1170, 12.3195, 12.4404, 12.6227, 12.9417, 13.0055, 13.1521, 13.3955,
                   13.7649, 14.0673, 14.1942, 14.4103, 14.5046, 15.3084, 15.5009, 15.6930,
                   15.8077, 16.2425, 16.4787, 16.6879, 16.9503, 17.3981, 17.7328, 17.8463,
                   18.1052, 18.2559, 18.5865, 18.8608, 18.9713, 19.0620, 19.1412, 19.5169,
                   19.6798, 20.3155, 20.6049, 20.7725, 21.0497, 21.2441, 21.5975, 21.8500,
                   22.0086, 22.4988, 22.6246, 23.1304, 23.5215, 24.2545, 24.5936, 24.8740,
                   25.1489, 25.6875, 25.8941, 26.1697, 26.4101, 26.7175, 26.9191, 27.1856,
                   28.0455, 28.3828, 28.7887, 29.3331, 29.5187, 29.6375, 29.9857, 30.2718,
                   30.5703, 30.7638, 31.2298, 31.8509, 32.4674, 32.6056, 32.8534, 33.4260,
                   33.8858, 34.0975, 34.2450, 34.6745, 35.4760, 35.6995, 36.1743, 36.3347,
                   36.9378, 37.7596, 38.4528, 38.8946, 39.5044, 39.7011, 40.3174, 40.5730,
                   40.8058, 40.9868, 41.6574, 42.3280, 43.1794, 43.4549, 43.9905, 44.4089,
                   44.9919, 45.5748, 46.1577, 46.7406, 47.4367, 48.1801, 49.1956, 49.9898,
                   50.6389, 51.2880, 51.9371, 52.5862, 53.1535, 53.7208, 54.2880, 55.0733,
                   55.7767, 56.4911, 57.2055, 57.6093, 58.1866, 58.7638, 59.3410, 59.9183,
                   60.4955, 61.0727, 61.6500, 62.2272, 62.8044, 63.4461, 64.0877, 64.7293,
                   65.5134, 66.2975, 66.8569, 67.4162, 67.9756, 68.5349, 69.0943, 69.6536,
                   70.2130, 70.7723, 71.3317, 71.8910, 72.4504, 73.0098, 73.5691, 74.1285,
                   74.6878, 75.2472, 75.8065, 76.3659, 76.9252, 77.4846, 78.0439, 78.6033,
                   79.1626, 79.7220, 80.2814, 80.8407, 81.4001, 81.9594, 82.5188, 83.0781,
                   83.6375, 84.1968, 84.7562, 85.3155, 85.8749, 86.4342, 86.9936, 87.5530,
                   88.1123, 88.6717, 89.2310, 89.7904, 90.3497, 90.9091, 91.4684, 92.0278,
                   92.5871, 93.1465, 93.7058, 94.2652, 94.8246, 95.3839, 95.9433, 96.5026,
                   97.0620, 97.6213, 98.1807, 98.7400, 99.2994, 99.8587, 100.4181, 100.9774,
                   101.5368, 102.0962, 102.6555, 103.2149, 103.7742, 104.3336, 104.8929, 105.4523,
                   106.0116, 106.5710, 107.1303, 107.6897, 108.2490, 108.8084, 109.3678)
    mode_gains  = (0.0620, 0.0089, 0.0779, 0.0023, 0.0118, 0.0377, 0.0047, 0.0095,
                   0.1048, 0.0089, 0.0035, 0.0071, 0.0142, 0.4405, 0.0213, 0.0355,
                   0.0248, 0.0569, 0.1089, 0.0368, 0.0469, 0.0251, 0.0285, 0.0519,
                   0.1825, 0.0167, 0.0150, 0.0201, 0.0486, 0.0134, 0.5995, 0.3667,
                   0.5007, 0.5341, 0.2060, 0.1758, 0.0503, 0.0435, 0.0988, 0.0753,
                   0.0920, 0.1005, 0.0787, 0.1239, 0.0660, 0.0864, 0.0440, 0.0322,
                   0.0118, 0.0085, 0.0237, 0.0085, 0.0186, 0.1355, 0.0660, 0.0118,
                   0.0136, 0.0153, 0.0118, 0.0898, 0.1371, 0.0915, 0.0271, 0.0457,
                   0.0186, 0.0915, 0.0440, 0.0169, 0.1220, 0.1998, 0.1524, 0.0305,
                   0.0796, 0.0542, 0.0931, 0.0982, 0.1100, 0.0762, 0.0728, 0.0407,
                   0.0356, 0.0542, 0.0237, 0.0169, 0.0136, 0.0284, 0.0185, 0.0313,
                   0.1535, 0.1734, 0.3937, 0.0511, 0.0156, 0.0952, 0.0511, 0.0952,
                   0.2189, 0.6226, 0.0696, 0.0754, 0.0241, 0.0241, 0.0426, 0.2843,
                   0.0597, 0.0995, 0.2530, 0.0554, 0.1094, 0.1877, 0.1933, 0.2728,
                   0.3340, 0.2132, 0.0540, 0.2289, 0.0398, 0.6538, 0.4677, 0.4022,
                   0.0469, 0.2161, 0.2019, 0.2061, 0.0270, 0.0540, 0.0725, 0.1393,
                   0.0441, 0.3156, 0.0583, 0.1109, 0.4762, 0.1051, 0.3226, 0.0981,
                   0.0923, 0.3340, 0.1961, 0.2366, 0.1489, 0.1499, 0.1167, 0.0237,
                   0.2570, 0.2762, 0.2698, 0.0849, 0.2941, 0.6703, 0.0376, 0.3806,
                   0.4558, 0.3129, 0.2650, 0.4473, 0.1774, 0.4225, 0.0296, 0.1532,
                   0.2693, 0.1397, 0.1607, 0.1833, 0.6805, 0.1828, 0.3381, 0.2531,
                   0.3833, 0.0828, 0.1838, 0.2994, 0.2015, 0.0790, 0.4267, 0.1112,
                   0.2177, 0.2747, 0.2843, 0.1806, 0.1634, 0.2854, 0.0683, 0.2290,
                   0.1209, 0.1081, 0.1601, 0.0957, 0.2048, 0.1069, 0.0903, 0.4085,
                   0.1505, 0.2262, 0.0581, 0.0699, 0.2462, 0.1236, 0.2525, 0.1163,
                   0.1065, 0.5865, 0.2008, 0.3462, 0.4574, 0.4471, 0.1997, 0.8864,
                   0.0964, 0.2418, 0.2729, 0.3652, 0.1690, 0.2671, 0.0724, 0.3012,
                   0.9389, 0.4558, 0.5233, 0.3211, 0.0986, 0.2864, 1.0000, 0.3545,
                   0.5573, 0.7787, 0.0455, 0.3002, 0.2756, 0.1674, 0.2197, 0.2495,
                   0.1116, 0.1395, 0.2599, 0.2164, 0.2053, 0.9081, 0.2118, 0.2888,
                   0.1695, 0.1443, 0.0381, 0.4527, 0.1069, 0.0288, 0.2194, 0.1279,
                   0.0437, 0.2648, 0.1680, 0.0425, 0.1423, 0.1412, 0.0949, 0.0397,
                   0.0528, 0.0320, 0.0338, 0.0431, 0.0238, 0.0346, 0.0606, 0.0449,
                   0.0206, 0.0254, 0.0222, 0.0385, 0.0250, 0.0234, 0.2260)
    max_harmonic = 271
    aftersound_fraction = 0.25
    aftersound_ratio = 0.20
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    strike_phase_spread = 1.0
    ring_peak_hz = 1500.0
    ring_decay_below = 5.0
    ring_decay_floor = 14.4
    ring_decay_above = 24.0
    chiff_volume = 2.00
    chiff_bandwidth = 1.50
    # REFITTED on honest frequencies. Everything above was fitted while the
    # measured modes were being stretched by the family's inharmonicity (see
    # CymbalProperties), so every gain, decay, wash and level was compensating
    # for modes in the wrong place. All of it is re-solved here against the
    # recording's band energy at FOUR times -- 0.02, 0.10, 0.35 and 0.70 s --
    # plus how far the lines stand above the continuum, with the level held to
    # what Ben balanced by ear so this changes the sound and not the mix.
    #
    # The ring law is ON here (see CymbalProperties.harmonic_decay): a plate's
    # ring time peaks in the middle and dies at both ends, which the inherited
    # monotonic law cannot express.
    # Each mode gets its own strike sign (see strike_phase_spread): with 18
    # modes all starting in phase the note peaked far above what the recording does.
    # THE NOISE IS A TRANSIENT, NOT A SUSTAIN. Measured as spectral flatness
    # (1.0 = white noise, 0 = pure tone) at three points in the note, the
    # recording collapses from 0.098 at the strike to 0.000 by 0.4 s: a cymbal is
    # noisy while it is being struck and almost purely tonal once it rings.
    # Ours held 0.14 for the whole note -- a hiss, not a crash, which is why the
    # hit did not stand out from the ring.
    #
    # There was no way to say this before: chiff_volume gates the noise, the
    # attack burst is tied to the speech fade (1.5 ms, since the attack fix),
    # and sustain_jitter is a floor that never decays -- so the wash was either
    # permanently on or a flick. chiff_width decouples the burst from the fade,
    # and that is what lets the noise die on its own schedule.
    # Flatness now 0.100 / 0.016 / 0.000 against the recording's 0.098 / 0.008 / 0.000.
    #
    # It costs band accuracy: 3.41 -> 3.64 dB rms over 0.30 s, because with no
    # sustained wash the ring is only these modes and a real cymbal's is dense.
    # More modes do not recover it (110 modes reaches 4.48). The two measures
    # genuinely disagree and this one is chosen by ear.
    sustain_jitter = 1.000
    chiff_width = 0.290963
    # how much noisier this plate gets as it is struck harder, fitted so the
    # flatness at the mf velocity matches the mf recording.
    strike_noise_slope = 0.2204
    # The wobble, scaled by how hard it was struck: one voice per partial
    # offset 1.6 Hz, beating in the measured 0.7-3 Hz band. Depth comes out
    # 19.3% at velocity 127 and 9.5% at 70, against the 17" crash's measured
    # 16.2% at ff and 9.0% at mf.
    strike_wobble_hz = 1.6
    strike_wobble_gain = 0.3
    # +9 dB by ear (Ben, against the hi-hat, which is the loudest thing in
    # the kit and the reference here): "The hi-hat sounds the loudest. The ride
    # could probably be another 3 dB louder, and the other cymbals more like 9."
    # Levels BETWEEN cymbals are not measurable from the Iowa set -- its ff
    # varies 10 dB between crash takes -- so this one is a mix decision and is
    # labelled as one. The band profiles above are the measurement.
    # ...then the whole group down 8 dB together, so the balance above is kept
    # while the kit stops crowding the bass. Ben, on a drum-and-bass track:
    # "The bass is now too quiet, so I think the whole kit needs to go lower."
    initial_gain = 0.380497

class RideCymbalProperties(CymbalProperties):
    """GM 51, Ride Cymbal 1: the stick on the bow of a 21" ride.

    DENSE, at last. This kept the 18-mode set from the first measurement pass
    long after the crashes went to 300 and the hats to 224, and 18 modes cannot
    be a plate: only 4 of them sat between 2 and 5 kHz and one above 10, so most
    of the spectrum had no mode in it at all and everything up there was wash.
    Measured against the recording -- how far the peaks stand above the
    continuum, which is the one thing a band profile cannot see:

                          2-5k   5-10k  10-20k
        the recording     15.1    19.8    16.2
        ours, 18 modes     4.8     6.5     7.7
        ours, dense       14.7    18.4    15.6

    A ride's ping is resolvable modes. Ours was white noise standing in for
    them, which is why it read as mush rather than as a stick on a bell-bronze
    plate.

    THE WASH IS BANDED, not white -- see chiff_bandwidth. THE LOSS CURVE IS
    FITTED ON BOTH WINDOWS, the strike and the tail, because the decay is what
    the spectrum does between them and an envelope alone cannot say which
    partials should have gone.
    """
    mode_ratios = (1.0000, 1.0071, 1.3312, 1.3757, 1.3877, 1.7965, 2.0003, 2.3401,
                   2.5516, 2.6545, 2.9726, 3.2871, 3.3170, 3.3649, 3.4963, 3.9609,
                   4.3814, 4.4116, 4.6420, 5.1742, 5.2377, 5.2816, 5.5239, 5.8478,
                   5.9550, 6.0553, 6.5291, 6.6186, 7.1964, 7.3244, 7.5593, 7.9336,
                   7.9954, 8.2557, 8.4860, 8.7377, 8.9438, 9.3030, 9.5219, 9.5944,
                   10.2731, 10.3412, 10.4860, 10.6377, 11.0519, 11.4279, 11.8042, 12.4792,
                   12.6055, 12.9048, 12.9818, 13.3623, 13.4302, 13.6918, 13.9173, 14.2235,
                   14.5633, 14.8709, 15.3027, 15.6457, 15.7905, 16.5536, 16.8304, 16.8994,
                   17.5550, 17.8894, 18.0433, 18.5242, 18.7489, 18.9552, 19.6725, 19.9607,
                   20.3552, 20.9490, 21.4313, 21.7129, 21.9698, 22.2107, 22.5547, 22.8617,
                   23.2893, 23.6950, 23.7925, 24.0180, 24.5562, 25.1708, 25.4461, 25.6668,
                   26.4279, 26.6665, 27.1842, 27.5716, 27.9236, 28.2503, 28.4604, 29.1930,
                   29.4895, 30.0026, 30.2694, 30.5821, 31.0430, 31.2979, 31.5536, 31.9758,
                   32.5296, 33.0103, 33.4151, 33.6306, 34.1388, 34.3213, 35.0143, 35.3204,
                   35.6759, 36.1602, 36.4504, 37.0955, 37.4344, 37.8763, 38.2052, 38.6135,
                   38.8558, 39.0998, 39.8261, 40.1083, 40.4273, 40.6736, 40.8469, 41.3766,
                   42.2551, 42.6183, 42.8780, 43.5621, 43.9681, 44.6836, 45.0519, 45.4245,
                   45.8677, 46.1585, 46.6271, 47.0416, 47.2970, 47.5533, 48.1428, 48.7375,
                   49.3321, 49.8951, 50.1078, 50.9823, 51.8845, 52.0949, 52.6973, 53.2910,
                   53.8848, 54.3883, 55.3039, 55.8132, 56.3225, 56.8318, 57.4332, 58.0345,
                   58.7782, 59.5219, 59.8287, 60.7708, 61.4756, 62.1804, 62.5952, 62.8461,
                   63.1574, 63.5257, 63.8387, 64.5616, 65.1090, 65.6564, 66.2038, 66.7739,
                   67.3792, 67.9845, 68.5897, 69.1950, 69.7982, 70.3040, 70.8099, 71.3158,
                   71.8216, 72.3275, 72.8333, 73.3392, 73.8451, 74.3509, 74.8568, 75.3626,
                   75.8685, 76.3744, 76.8802, 77.3861, 77.8919, 78.3978, 78.9037, 79.4095,
                   79.9154, 80.4212, 80.9271, 81.4330, 81.9388, 82.4447, 82.9506, 83.4564,
                   83.9623, 84.4681, 84.9740, 85.4799, 85.9857, 86.4916, 86.9974, 87.5033,
                   88.0092, 88.5150, 89.0209, 89.5267, 90.0326, 90.5385, 91.0443, 91.5502,
                   92.0560, 92.5619, 93.0678, 93.5736, 94.0795, 94.5853, 95.0912, 95.5971,
                   96.1029, 96.6088, 97.1146, 97.6205, 98.1264, 98.6322, 99.1381, 99.6440,
                   100.1498, 100.6557, 101.1615, 101.6674, 102.1733, 102.6791, 103.1850, 103.6908,
                   104.1967, 104.7026, 105.2084, 105.7143, 106.2201, 106.7260, 107.2319, 107.7377,
                   108.2436, 108.7494, 109.2553, 109.7612, 110.2670, 110.7729, 111.2787, 111.7846,
                   112.2905, 112.7963, 113.3022, 113.8080, 114.3139, 114.8198, 115.3256, 115.8315,
                   116.3374, 116.8432, 117.3491, 117.8549, 118.3608, 118.8667, 119.3725, 119.8784,
                   120.3842, 120.8901, 121.3960, 121.9018, 122.4077, 122.9135, 123.4194, 123.9253,
                   124.4311, 124.9370, 125.4428, 125.9487, 126.4546, 126.9604, 127.4663, 127.9721,
                   128.4780, 128.9839, 129.4897, 129.9956, 130.5014, 131.0073, 131.5132, 132.0190,
                   132.5249, 133.0308, 133.5366, 134.0425, 134.5483, 135.0542)
    mode_gains  = (0.0014, 0.0016, 0.0040, 0.0020, 0.0019, 0.0021, 0.0145, 0.1289,
                   0.1011, 0.0984, 0.0612, 0.1522, 0.0473, 0.1106, 0.0385, 0.1890,
                   0.1208, 0.0512, 0.0715, 0.0204, 0.0135, 0.0221, 0.2362, 0.0170,
                   0.0145, 0.0684, 0.0270, 0.0300, 0.0058, 0.0202, 0.0052, 0.0204,
                   0.0143, 0.0178, 0.0082, 0.0271, 0.0717, 0.0072, 0.0254, 0.0157,
                   0.0354, 0.0178, 0.0094, 0.0113, 0.0025, 0.0083, 0.0023, 0.0401,
                   0.0210, 0.0098, 0.0058, 0.0034, 0.0029, 0.0014, 0.0127, 0.0110,
                   0.0054, 0.0031, 0.0665, 0.0057, 0.0028, 0.0736, 0.0243, 0.0475,
                   0.0073, 0.0134, 0.0264, 0.0105, 0.0211, 0.0292, 0.0048, 0.0043,
                   0.0082, 0.0019, 0.0850, 0.0841, 0.0430, 0.1458, 0.1973, 0.1047,
                   0.0497, 0.0220, 0.0112, 0.1214, 0.0435, 0.2187, 0.1855, 0.0257,
                   0.0073, 0.0177, 0.0357, 0.0074, 0.0077, 0.0204, 0.0244, 0.0529,
                   0.0136, 0.0252, 0.0278, 0.0274, 0.0749, 0.0726, 0.0101, 0.0500,
                   0.1549, 0.0984, 0.1480, 0.0390, 0.0297, 0.0551, 0.0156, 0.0314,
                   0.0419, 0.0379, 0.0471, 0.0567, 0.0120, 0.0532, 0.0681, 0.0086,
                   0.0309, 0.0528, 0.0226, 0.0895, 0.0848, 0.0097, 0.1044, 0.1638,
                   0.1536, 0.0579, 0.1982, 0.1286, 0.0481, 0.0664, 0.0315, 0.0218,
                   0.0381, 0.0371, 0.0273, 0.1988, 0.0891, 0.0851, 0.1151, 0.0092,
                   0.1109, 0.1563, 0.2362, 0.1127, 0.2304, 0.0639, 0.2919, 0.1775,
                   0.0242, 0.0309, 0.2051, 0.0299, 0.0725, 0.1271, 0.1386, 0.4832,
                   0.1567, 0.4241, 0.3670, 0.4986, 0.1322, 0.3928, 0.0129, 0.1668,
                   0.0775, 0.0813, 0.0934, 0.0743, 0.2502, 0.1009, 0.1076, 0.1283,
                   0.1416, 0.0450, 0.1088, 0.2270, 0.1455, 0.3592, 0.0578, 0.2231,
                   0.2243, 0.4975, 0.1300, 0.2278, 0.0329, 0.1306, 0.2349, 0.1157,
                   0.0792, 0.0938, 0.0327, 0.0281, 0.1483, 0.0204, 0.0338, 0.0131,
                   0.0198, 0.0151, 0.0250, 0.0129, 0.0351, 0.0313, 0.0100, 0.0506,
                   0.0328, 0.0173, 0.0691, 0.0432, 0.0638, 0.0314, 0.0732, 0.0645,
                   0.2013, 0.1233, 0.1603, 0.0814, 0.0389, 0.0769, 0.0191, 0.0838,
                   0.3069, 0.1528, 0.3217, 0.3665, 0.0270, 0.0736, 0.0635, 0.2766,
                   0.0490, 0.1271, 0.0927, 0.1424, 0.1237, 0.1465, 0.2269, 0.0641,
                   0.4625, 0.2118, 0.3538, 0.0912, 0.1479, 0.1382, 0.3345, 0.1720,
                   0.0457, 0.1814, 0.0771, 0.1328, 0.1859, 0.3646, 0.1947, 0.0273,
                   0.1210, 0.1300, 0.1725, 0.1012, 0.3978, 0.3517, 0.0543, 0.1265,
                   0.0660, 0.1269, 0.0157, 0.1251, 0.2366, 0.2199, 0.0839, 0.1155,
                   0.3592, 0.0965, 0.1783, 0.3026, 0.1528, 0.1646, 0.0699, 0.1602,
                   0.4917, 0.2595, 0.1288, 0.3480, 0.2157, 0.1023, 0.2387, 0.0739,
                   0.0169, 0.1060, 0.2675, 0.1571, 0.0356, 0.0963, 0.2678, 0.0436,
                   0.1815, 0.1966, 0.1309, 0.1473, 0.1317, 0.5301, 0.1626, 0.1480,
                   0.1203, 0.0594, 0.1009, 0.1290, 0.2236, 1.0000)
    max_harmonic = 310
    aftersound_fraction = 0.08
    aftersound_ratio = 0.06
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    strike_phase_spread = 1.0
    ring_peak_hz = 1500.0
    ring_decay_below = 5.0
    ring_decay_floor = 14.4
    ring_decay_above = 12.0
    chiff_volume = 2.00
    chiff_bandwidth = 0.05
    # REFITTED on honest frequencies. Everything above was fitted while the
    # measured modes were being stretched by the family's inharmonicity (see
    # CymbalProperties), so every gain, decay, wash and level was compensating
    # for modes in the wrong place. All of it is re-solved here against the
    # recording's band energy at FOUR times -- 0.02, 0.10, 0.35 and 0.70 s --
    # plus how far the lines stand above the continuum, with the level held to
    # what Ben balanced by ear so this changes the sound and not the mix.
    #
    # The ring law is ON here (see CymbalProperties.harmonic_decay): a plate's
    # ring time peaks in the middle and dies at both ends, which the inherited
    # monotonic law cannot express.
    # Each mode gets its own strike sign (see strike_phase_spread): with 18
    # modes all starting in phase the note peaked far above what the recording does.
    # THE NOISE IS A TRANSIENT, NOT A SUSTAIN. Measured as spectral flatness
    # (1.0 = white noise, 0 = pure tone) at three points in the note, the
    # recording collapses from 0.122 at the strike to 0.000 by 0.4 s: a cymbal is
    # noisy while it is being struck and almost purely tonal once it rings.
    # Ours held 0.43 for the whole note -- a hiss, not a crash, which is why the
    # hit did not stand out from the ring.
    #
    # There was no way to say this before: chiff_volume gates the noise, the
    # attack burst is tied to the speech fade (1.5 ms, since the attack fix),
    # and sustain_jitter is a floor that never decays -- so the wash was either
    # permanently on or a flick. chiff_width decouples the burst from the fade,
    # and that is what lets the noise die on its own schedule.
    # Flatness now 0.135 / 0.029 / 0.000 against the recording's 0.122 / 0.004 / 0.000.
    #
    # It costs band accuracy: 3.30 -> 5.51 dB rms over 0.30 s, because with no
    # sustained wash the ring is only these modes and a real cymbal's is dense.
    # More modes do not recover it (110 modes reaches 4.48). The two measures
    # genuinely disagree and this one is chosen by ear.
    sustain_jitter = 0.00127826
    chiff_width = 0.31383
    # how much noisier this plate gets as it is struck harder, fitted so the
    # flatness at the mf velocity matches the mf recording.
    strike_noise_slope = 0.1637
    # The wobble, scaled by how hard it was struck: one voice per partial
    # offset 1.6 Hz, beating in the measured 0.7-3 Hz band. Depth comes out
    # 19.3% at velocity 127 and 9.5% at 70, against the 17" crash's measured
    # 16.2% at ff and 9.0% at mf.
    strike_wobble_hz = 1.6
    strike_wobble_gain = 0.3
    # LEVEL, from the one comparison the recordings can actually settle. Levels
    # between different cymbals are not measurable here -- Iowa's ff varies 10 dB
    # between crash takes, so it records how hard that cymbal was hit that day,
    # not how loud a crash is against a ride. But the bow and the BELL are the
    # same 21" plate in the same take, and there the recording is unambiguous:
    # the bell is 5.6 dB louder, K-weighted. Ours had the bow 6.5 dB louder than
    # the bell -- the relationship inverted, by 12.1 dB. That is the -12.1 here.
    # +3 dB by ear (Ben, against the hi-hat, which is the loudest thing in
    # the kit and the reference here): "The hi-hat sounds the loudest. The ride
    # could probably be another 3 dB louder, and the other cymbals more like 9."
    # Levels BETWEEN cymbals are not measurable from the Iowa set -- its ff
    # varies 10 dB between crash takes -- so this one is a mix decision and is
    # labelled as one. The band profiles above are the measurement.
    # ...then the whole group down 8 dB together, so the balance above is kept
    # while the kit stops crowding the bass. Ben, on a drum-and-bass track:
    # "The bass is now too quiet, so I think the whole kit needs to go lower."
    initial_gain = (0.094449) * 2.6607   # +8.5 dB: K-weighted to the string reference

class CrashRideProperties(CymbalProperties):
    """GM 59, Ride Cymbal 2: the 20" crash played as a ride.

    Dense rebuild, 26 modes to 282.

    THE WASH IS BANDED, not white -- see chiff_bandwidth. THE LOSS CURVE IS
    FITTED ON BOTH WINDOWS, the strike and the tail, because the decay is what
    the spectrum does between them and an envelope alone cannot say which
    partials should have gone.
    """
    mode_ratios = (1.0000, 1.3397, 1.3525, 1.8469, 2.2119, 2.5496, 3.2088, 3.4426,
                   3.5319, 3.8408, 4.0385, 4.1814, 4.3380, 4.4897, 4.7845, 5.4581,
                   5.4809, 5.7862, 6.0746, 6.1570, 6.4418, 6.7160, 6.8539, 6.9318,
                   7.3195, 7.4273, 7.5150, 7.6464, 7.7535, 8.0011, 8.0743, 8.2377,
                   8.6986, 9.0094, 9.5602, 9.8744, 10.1489, 10.4265, 10.5211, 10.7726,
                   10.9132, 10.9942, 11.1999, 11.4742, 11.5427, 11.9382, 12.7024, 12.7812,
                   13.4182, 13.7202, 13.9814, 14.0591, 14.4806, 14.8394, 14.9079, 15.1342,
                   15.7770, 16.2260, 16.4309, 16.5011, 16.6869, 17.0380, 17.1450, 17.6226,
                   17.7823, 17.9010, 18.0710, 18.3350, 18.4814, 19.0458, 19.4340, 19.6861,
                   20.3292, 20.6359, 20.7621, 20.9032, 21.2626, 21.8275, 21.9509, 22.2163,
                   23.2576, 23.5374, 23.9032, 24.2299, 24.6259, 24.7443, 25.0402, 25.2696,
                   25.4903, 26.3813, 26.7069, 26.9889, 27.2909, 27.5596, 27.8317, 28.0485,
                   28.4343, 28.7915, 29.3974, 29.6694, 29.8869, 30.3489, 30.7035, 30.8458,
                   31.0593, 31.3882, 32.0469, 32.2557, 32.6015, 33.4599, 34.3184, 34.5297,
                   35.0424, 35.9224, 36.5427, 37.1531, 37.7634, 38.1608, 38.7160, 39.7474,
                   40.1755, 40.5358, 41.1812, 41.8267, 42.3774, 42.9770, 43.5682, 44.0031,
                   44.3957, 44.6850, 44.9834, 45.3062, 45.5865, 45.8722, 46.1750, 46.8611,
                   47.2438, 47.5749, 47.9881, 48.7230, 49.0485, 49.2629, 49.5710, 50.4742,
                   51.2881, 51.6889, 51.9018, 52.8924, 53.5103, 53.9670, 54.4434, 55.4271,
                   55.7720, 56.1822, 56.5080, 57.2937, 58.0793, 58.3613, 58.8134, 59.1500,
                   59.4268, 60.4146, 60.6988, 61.5177, 61.9778, 62.7765, 63.5623, 64.3480,
                   65.1642, 65.5535, 66.5211, 67.0585, 67.5926, 68.3888, 68.7316, 69.0699,
                   69.9659, 70.6420, 71.3181, 71.6969, 72.8114, 73.3977, 73.9839, 74.5702,
                   75.1528, 75.6772, 76.2757, 76.8742, 77.4728, 78.0713, 78.6491, 79.2269,
                   79.8048, 80.3826, 80.9604, 81.5383, 82.1169, 82.6955, 83.2741, 83.8526,
                   84.4312, 85.0098, 85.5884, 86.1670, 86.7456, 87.3242, 87.9028, 88.4814,
                   89.0600, 89.6386, 90.2172, 90.7958, 91.3744, 91.9530, 92.5316, 93.1101,
                   93.6887, 94.2673, 94.8459, 95.4245, 96.0031, 96.5817, 97.1603, 97.7389,
                   98.3175, 98.8961, 99.4747, 100.0533, 100.6319, 101.2105, 101.7891, 102.3677,
                   102.9462, 103.5248, 104.1034, 104.6820, 105.2606, 105.8392, 106.4178, 106.9964,
                   107.5750, 108.1536, 108.7322, 109.3108, 109.8894, 110.4680, 111.0466, 111.6252,
                   112.2038, 112.7823, 113.3609, 113.9395, 114.5181, 115.0967, 115.6753, 116.2539,
                   116.8325, 117.4111, 117.9897, 118.5683, 119.1469, 119.7255, 120.3041, 120.8827,
                   121.4613, 122.0399, 122.6184, 123.1970, 123.7756, 124.3542, 124.9328, 125.5114,
                   126.0900, 126.6686, 127.2472, 127.8258, 128.4044, 128.9830, 129.5616, 130.1402,
                   130.7188, 131.2974)
    mode_gains  = (0.0157, 0.0054, 0.0092, 0.2828, 0.1920, 0.2299, 0.0801, 0.0925,
                   0.0666, 0.0183, 0.0088, 0.0352, 0.0518, 0.1558, 0.0500, 0.0810,
                   0.0759, 0.0124, 0.0290, 0.0320, 0.0176, 0.0190, 0.0818, 0.0474,
                   0.0442, 0.0231, 0.0203, 0.0620, 0.1305, 0.0860, 0.0274, 0.0122,
                   0.0915, 0.0170, 0.1404, 0.0158, 0.0192, 0.0294, 0.0474, 0.0104,
                   0.0150, 0.0073, 0.0109, 0.0189, 0.0241, 0.0230, 0.0107, 0.0175,
                   0.0648, 0.0391, 0.0254, 0.0193, 0.0113, 0.0432, 0.1639, 0.0233,
                   0.0103, 0.0552, 0.0091, 0.0077, 0.0175, 0.0030, 0.0055, 0.0378,
                   0.0468, 0.1138, 0.0531, 0.0109, 0.0095, 0.0345, 0.1678, 0.0250,
                   0.0362, 0.0079, 0.0106, 0.0087, 0.1603, 0.2995, 0.1625, 0.2520,
                   0.1206, 0.1359, 0.0357, 0.0877, 0.0635, 0.0389, 0.0104, 0.1186,
                   0.1020, 0.0983, 0.0260, 0.0285, 0.1928, 0.1372, 0.0077, 0.0125,
                   0.1464, 0.2205, 0.1393, 0.0136, 0.1930, 0.2369, 0.0341, 0.1386,
                   0.1123, 0.2228, 0.1123, 0.1641, 0.1709, 0.0258, 0.1074, 0.1299,
                   0.0736, 0.1670, 0.1345, 0.2326, 0.0400, 0.1524, 0.4208, 0.1834,
                   0.1337, 0.1371, 0.0633, 0.1361, 0.2023, 0.3789, 0.0661, 0.1287,
                   0.0559, 0.1310, 0.1133, 0.3156, 0.0331, 0.0317, 0.1856, 0.3820,
                   0.2947, 0.4551, 0.2230, 0.2224, 0.1388, 0.1451, 0.6338, 0.2529,
                   0.1739, 0.0972, 0.3953, 0.3393, 0.2509, 0.2582, 0.2713, 0.1729,
                   0.2246, 0.0654, 0.2934, 0.3810, 0.8721, 0.1476, 0.2665, 0.3168,
                   0.6864, 0.1501, 0.1095, 0.1959, 0.5865, 0.1880, 0.2076, 0.9537,
                   0.1197, 0.2550, 0.2572, 0.4779, 0.3180, 0.3511, 0.0249, 0.4369,
                   0.7151, 0.3475, 0.3945, 0.1472, 0.4728, 0.3925, 0.1253, 0.3853,
                   0.6272, 0.3460, 0.6171, 0.4845, 0.4204, 0.5578, 0.4026, 0.2090,
                   0.4398, 0.4424, 0.2070, 0.4335, 0.0921, 0.4600, 0.2932, 0.7888,
                   0.8764, 0.4088, 0.5329, 0.1319, 1.0000, 0.9351, 0.6209, 0.2359,
                   0.3719, 0.4402, 0.5818, 0.8757, 0.3176, 0.4854, 0.8780, 0.7602,
                   0.7102, 0.2208, 0.0447, 0.3429, 0.3348, 0.3913, 0.2875, 0.0957,
                   0.2383, 0.1885, 0.1644, 0.2793, 0.0569, 0.1502, 0.2928, 0.1271,
                   0.0805, 0.1164, 0.0876, 0.0932, 0.2434, 0.0903, 0.1547, 0.3321,
                   0.0606, 0.0619, 0.2134, 0.2097, 0.0938, 0.0956, 0.1503, 0.0235,
                   0.1619, 0.0948, 0.0822, 0.1199, 0.0534, 0.0554, 0.0828, 0.0771,
                   0.4169, 0.0868, 0.1690, 0.1157, 0.1504, 0.1357, 0.1243, 0.0967,
                   0.1135, 0.0676, 0.0593, 0.0972, 0.0804, 0.2141, 0.0444, 0.0371,
                   0.0842, 0.0359, 0.0439, 0.1500, 0.0934, 0.0206, 0.0759, 0.0782,
                   0.0933, 0.6887)
    max_harmonic = 282
    aftersound_fraction = 0.25
    aftersound_ratio = 0.20
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    strike_phase_spread = 1.0
    ring_peak_hz = 1500.0
    ring_decay_below = 5.0
    ring_decay_floor = 14.4
    ring_decay_above = 12.0
    chiff_volume = 2.00
    chiff_bandwidth = 0.50
    # REFITTED on honest frequencies. Everything above was fitted while the
    # measured modes were being stretched by the family's inharmonicity (see
    # CymbalProperties), so every gain, decay, wash and level was compensating
    # for modes in the wrong place. All of it is re-solved here against the
    # recording's band energy at FOUR times -- 0.02, 0.10, 0.35 and 0.70 s --
    # plus how far the lines stand above the continuum, with the level held to
    # what Ben balanced by ear so this changes the sound and not the mix.
    #
    # The ring law is ON here (see CymbalProperties.harmonic_decay): a plate's
    # ring time peaks in the middle and dies at both ends, which the inherited
    # monotonic law cannot express.
    # Each mode gets its own strike sign (see strike_phase_spread): with 26
    # modes all starting in phase the note peaked far above what the recording does.
    # THE NOISE IS A TRANSIENT, NOT A SUSTAIN. Measured as spectral flatness
    # (1.0 = white noise, 0 = pure tone) at three points in the note, the
    # recording collapses from 0.207 at the strike to 0.002 by 0.4 s: a cymbal is
    # noisy while it is being struck and almost purely tonal once it rings.
    # Ours held 0.53 for the whole note -- a hiss, not a crash, which is why the
    # hit did not stand out from the ring.
    #
    # There was no way to say this before: chiff_volume gates the noise, the
    # attack burst is tied to the speech fade (1.5 ms, since the attack fix),
    # and sustain_jitter is a floor that never decays -- so the wash was either
    # permanently on or a flick. chiff_width decouples the burst from the fade,
    # and that is what lets the noise die on its own schedule.
    # Flatness now 0.209 / 0.040 / 0.001 against the recording's 0.207 / 0.034 / 0.002.
    #
    # It costs band accuracy: 1.06 -> 5.37 dB rms over 0.30 s, because with no
    # sustained wash the ring is only these modes and a real cymbal's is dense.
    # More modes do not recover it (110 modes reaches 4.48). The two measures
    # genuinely disagree and this one is chosen by ear.
    sustain_jitter = 0.00145763
    chiff_width = 0.310107
    # how much noisier this plate gets as it is struck harder, fitted so the
    # flatness at the mf velocity matches the mf recording.
    strike_noise_slope = 0.1637
    # The wobble, scaled by how hard it was struck: one voice per partial
    # offset 1.6 Hz, beating in the measured 0.7-3 Hz band. Depth comes out
    # 19.3% at velocity 127 and 9.5% at 70, against the 17" crash's measured
    # 16.2% at ff and 9.0% at mf.
    strike_wobble_hz = 1.6
    strike_wobble_gain = 0.3
    # solved to hold note 59 at exactly the loudness it had while it was
    # borrowing the 21" ride, so this changes the plate and not the balance.
    initial_gain = 0.071361

class RideBellProperties(CymbalProperties):
    """GM 53, Ride Bell: the same 21" ride, struck on the cup.

    ONE CYMBAL, TWO STRIKE POINTS -- the same argument as the three hi-hats, and
    tested rather than assumed. Confirmed modes from the bell's own free ring,
    matched against the bow's within 0.3%:

        300-800 Hz   65% match against 8% by chance    7.8x
        800-1600     79% against 18%                   4.4x
        1600-3200    76% against 26%                   2.9x
        3200-6400    84% against 42%                   2.0x
        6400-12000   83% against 31%                   2.7x

    Shared in every band, most decisively at the bottom where the modes need the
    whole plate to move. So the bell inherits the ride's plate and differs by
    what the cup excites -- its gains, read off its own recording by energy
    partition -- and by its own damping. (An earlier aggregate version of this
    test read 2.0x overall and looked negative; it pooled bands whose chance
    rates differ fivefold and was swamped by the high ones.)

    THE WASH IS BANDED, not white -- see chiff_bandwidth. THE LOSS CURVE IS
    FITTED ON BOTH WINDOWS, the strike and the tail, because the decay is what
    the spectrum does between them and an envelope alone cannot say which
    partials should have gone.
    """
    mode_ratios = (1.0000, 1.0071, 1.3312, 1.3757, 1.3877, 1.7965, 2.0003, 2.3401,
                   2.5516, 2.6545, 2.9726, 3.2871, 3.3170, 3.3649, 3.4963, 3.9609,
                   4.3814, 4.4116, 4.6420, 5.1742, 5.2377, 5.2816, 5.5239, 5.8478,
                   5.9550, 6.0553, 6.5291, 6.6186, 7.1964, 7.3244, 7.5593, 7.9336,
                   7.9954, 8.2557, 8.4860, 8.7377, 8.9438, 9.3030, 9.5219, 9.5944,
                   10.2731, 10.3412, 10.4860, 10.6377, 11.0519, 11.4279, 11.8042, 12.4792,
                   12.6055, 12.9048, 12.9818, 13.3623, 13.4302, 13.6918, 13.9173, 14.2235,
                   14.5633, 14.8709, 15.3027, 15.6457, 15.7905, 16.5536, 16.8304, 16.8994,
                   17.5550, 17.8894, 18.0433, 18.5242, 18.7489, 18.9552, 19.6725, 19.9607,
                   20.3552, 20.9490, 21.4313, 21.7129, 21.9698, 22.2107, 22.5547, 22.8617,
                   23.2893, 23.6950, 23.7925, 24.0180, 24.5562, 25.1708, 25.4461, 25.6668,
                   26.4279, 26.6665, 27.1842, 27.5716, 27.9236, 28.2503, 28.4604, 29.1930,
                   29.4895, 30.0026, 30.2694, 30.5821, 31.0430, 31.2979, 31.5536, 31.9758,
                   32.5296, 33.0103, 33.4151, 33.6306, 34.1388, 34.3213, 35.0143, 35.3204,
                   35.6759, 36.1602, 36.4504, 37.0955, 37.4344, 37.8763, 38.2052, 38.6135,
                   38.8558, 39.0998, 39.8261, 40.1083, 40.4273, 40.6736, 40.8469, 41.3766,
                   42.2551, 42.6183, 42.8780, 43.5621, 43.9681, 44.6836, 45.0519, 45.4245,
                   45.8677, 46.1585, 46.6271, 47.0416, 47.2970, 47.5533, 48.1428, 48.7375,
                   49.3321, 49.8951, 50.1078, 50.9823, 51.8845, 52.0949, 52.6973, 53.2910,
                   53.8848, 54.3883, 55.3039, 55.8132, 56.3225, 56.8318, 57.4332, 58.0345,
                   58.7782, 59.5219, 59.8287, 60.7708, 61.4756, 62.1804, 62.5952, 62.8461,
                   63.1574, 63.5257, 63.8387, 64.5616, 65.1090, 65.6564, 66.2038, 66.7739,
                   67.3792, 67.9845, 68.5897, 69.1950, 69.7982, 70.3040, 70.8099, 71.3158,
                   71.8216, 72.3275, 72.8333, 73.3392, 73.8451, 74.3509, 74.8568, 75.3626,
                   75.8685, 76.3744, 76.8802, 77.3861, 77.8919, 78.3978, 78.9037, 79.4095,
                   79.9154, 80.4212, 80.9271, 81.4330, 81.9388, 82.4447, 82.9506, 83.4564,
                   83.9623, 84.4681, 84.9740, 85.4799, 85.9857, 86.4916, 86.9974, 87.5033,
                   88.0092, 88.5150, 89.0209, 89.5267, 90.0326, 90.5385, 91.0443, 91.5502,
                   92.0560, 92.5619, 93.0678, 93.5736, 94.0795, 94.5853, 95.0912, 95.5971,
                   96.1029, 96.6088, 97.1146, 97.6205, 98.1264, 98.6322, 99.1381, 99.6440,
                   100.1498, 100.6557, 101.1615, 101.6674, 102.1733, 102.6791, 103.1850, 103.6908,
                   104.1967, 104.7026, 105.2084, 105.7143, 106.2201, 106.7260, 107.2319, 107.7377,
                   108.2436, 108.7494, 109.2553, 109.7612, 110.2670, 110.7729, 111.2787, 111.7846,
                   112.2905, 112.7963, 113.3022, 113.8080, 114.3139, 114.8198, 115.3256, 115.8315,
                   116.3374, 116.8432, 117.3491, 117.8549, 118.3608, 118.8667, 119.3725, 119.8784,
                   120.3842, 120.8901, 121.3960, 121.9018, 122.4077, 122.9135, 123.4194, 123.9253,
                   124.4311, 124.9370, 125.4428, 125.9487, 126.4546, 126.9604, 127.4663, 127.9721,
                   128.4780, 128.9839, 129.4897, 129.9956, 130.5014, 131.0073, 131.5132, 132.0190,
                   132.5249, 133.0308, 133.5366, 134.0425, 134.5483, 135.0542)
    mode_gains  = (0.0001, 0.0002, 0.0002, 0.0001, 0.0002, 0.0005, 0.0006, 0.1210,
                   0.0844, 0.0781, 0.0044, 0.0853, 0.0243, 0.0470, 0.0052, 0.0595,
                   0.1481, 0.0858, 0.0174, 0.0012, 0.0016, 0.0011, 0.0440, 0.0014,
                   0.0060, 0.2294, 0.0796, 0.0062, 0.0010, 0.0014, 0.0009, 0.0250,
                   0.0175, 0.0035, 0.0017, 0.0052, 0.3251, 0.0417, 0.0220, 0.0178,
                   0.3320, 0.1376, 0.0199, 0.0019, 0.0008, 0.0018, 0.0010, 0.0370,
                   0.0045, 0.0267, 0.0163, 0.0082, 0.0024, 0.0017, 0.0025, 0.0062,
                   0.0013, 0.0005, 0.0076, 0.0011, 0.0018, 0.0984, 0.4565, 0.1498,
                   0.0558, 0.0034, 0.0034, 0.0037, 0.2144, 0.2072, 0.0111, 0.0054,
                   0.0061, 0.0021, 0.5249, 0.0724, 0.1173, 0.7880, 0.5647, 0.1748,
                   0.0232, 0.0018, 0.0017, 0.0174, 0.0053, 0.5256, 0.6674, 0.0400,
                   0.0049, 0.0476, 0.0972, 0.0694, 0.1067, 0.0194, 0.0104, 0.1267,
                   0.1688, 0.0417, 0.1940, 0.0161, 0.0370, 0.0080, 0.0094, 0.1369,
                   0.0930, 0.2219, 0.0068, 0.0113, 0.0265, 0.0050, 0.0309, 0.0614,
                   0.0158, 0.0051, 0.0414, 0.2633, 0.0452, 0.0084, 0.0094, 0.0237,
                   0.0095, 0.0642, 0.0998, 0.0079, 0.0106, 0.0073, 0.0346, 0.0771,
                   0.0083, 0.0045, 0.0431, 0.6247, 0.0528, 0.0292, 0.0931, 0.0830,
                   0.1057, 0.1249, 0.1928, 0.0647, 0.0307, 0.0573, 0.5838, 0.0292,
                   0.0234, 0.0247, 0.0616, 0.5434, 0.1479, 0.0213, 0.3772, 0.1612,
                   0.1205, 0.8504, 0.2499, 0.1576, 0.1219, 0.0880, 0.5890, 0.3281,
                   0.0403, 0.0085, 0.1250, 0.3276, 0.8662, 0.0204, 0.0069, 0.0294,
                   0.1508, 0.0673, 0.0349, 1.0000, 0.2949, 0.4742, 0.1162, 0.0660,
                   0.1486, 0.0944, 0.2432, 0.2178, 0.0546, 0.0209, 0.0250, 0.0541,
                   0.0476, 0.1153, 0.3107, 0.0528, 0.0195, 0.0263, 0.2089, 0.0391,
                   0.0772, 0.1172, 0.0319, 0.0373, 0.0347, 0.0136, 0.0080, 0.0108,
                   0.0146, 0.0182, 0.0700, 0.0230, 0.0153, 0.0105, 0.0094, 0.0308,
                   0.0378, 0.1259, 0.5854, 0.1562, 0.1126, 0.0264, 0.1655, 0.0473,
                   0.1634, 0.0463, 0.0868, 0.2103, 0.1207, 0.0339, 0.0496, 0.1343,
                   0.0588, 0.0454, 0.1463, 0.2998, 0.0693, 0.0491, 0.0470, 0.0143,
                   0.0218, 0.0634, 0.1622, 0.1638, 0.0977, 0.0551, 0.0638, 0.0294,
                   0.0856, 0.0316, 0.0669, 0.0254, 0.2109, 0.2061, 0.0490, 0.0390,
                   0.0280, 0.1789, 0.0637, 0.0539, 0.0505, 0.0778, 0.0779, 0.0255,
                   0.0983, 0.0315, 0.0789, 0.0245, 0.1096, 0.0543, 0.1381, 0.1456,
                   0.1817, 0.0593, 0.0533, 0.0495, 0.0111, 0.0490, 0.0345, 0.0165,
                   0.0792, 0.0291, 0.1040, 0.0799, 0.1899, 0.2195, 0.0465, 0.0129,
                   0.1559, 0.0590, 0.1601, 0.1339, 0.2334, 0.1407, 0.0377, 0.0664,
                   0.0080, 0.0713, 0.0403, 0.0858, 0.0269, 0.0648, 0.1746, 0.2638,
                   0.2259, 0.2805, 0.0724, 0.1748, 0.2291, 0.0636, 0.1522, 0.1570,
                   0.1380, 0.1082, 0.1572, 0.0380, 0.0768, 0.6469)
    max_harmonic = 310
    aftersound_fraction = 0.25
    aftersound_ratio = 0.20
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    strike_phase_spread = 1.0
    ring_peak_hz = 1500.0
    ring_decay_below = 5.0
    ring_decay_floor = 14.4
    ring_decay_above = 15.0
    chiff_volume = 0.22
    chiff_bandwidth = 0.05
    # -8 dB with the rest of the kit; this class used to inherit the cymbal
    # family's 1/10 and so would not have moved with the others.
    initial_gain = 0.078217
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


class MembraneBodyProperties(FormantBody, PluckedStringProperties):
    """A string over a DRUMHEAD. The banjo and the shamisen, and nothing else.

    Every other plucked instrument in this bank radiates through a wooden box.
    These two radiate through a stretched skin, and it is not a variation on a
    soundboard -- a membrane is light, heavily damped, and cannot move enough
    air at low frequencies to radiate them. That single fact gives both
    instruments their character:

      - a THIN low end, because the head does not radiate it. Modelled with the
        same bell_cutoff highpass the violin family uses for "a body that small
        cannot radiate that low", set high.
      - a FAST decay, because a light damped radiator takes energy out of the
        string quickly. A banjo note is gone while a guitar's is still ringing.
      - a BRIGHT spectrum, because what the head does radiate well is the top.

    The head's own modes are not modelled as modes. A drumhead driven at its
    edge by a bridge is not a free membrane ringing in Bessel patterns -- it is
    loaded, damped, and driven off-centre -- so what survives is a broad
    resonance rather than a mode set. That is a formant, and it is asserted:
    neither reference collection has a banjo or a shamisen.
    """
    formants = ((900.0, 800.0, 0.70), (2600.0, 1800.0, 0.55))
    formant_floor = 0.18
    bore_corner_hz = 6000.0
    bore_order = 2.0
    bell_cutoff_hz = 320.0      # the head cannot radiate below this
    bell_order = 2.0

    decay_db = 4.5              # a light damped radiator empties the string
    harmonic_decay_db = 2.2
    harmonic_decay_dampening = 0.0
    tonal_dampening = 0.95
    max_harmonic = 48


class BanjoProperties(MembraneBodyProperties):
    """GM 105. Five steel strings over a drumhead, picked near the bridge.

    Steel and a fingerpick: brighter and faster than the shamisen's silk and
    horn plectrum, and picked closer to the bridge, so the comb's first null
    sits higher and the low partials are thinner still.

    ASSERTED, NOT MEASURED. Neither collection has one.
    """
    strike_point = 0.12
    strike_depth = 0.85
    strike_fills_with_force = False
    inharmonicity_coefficient = 8.0e-05     # short steel, estimated
    inharmonicity_dynamic = False
    tonal_dampening = 0.80                  # steel: brighter than silk
    decay_db = 5.2
    bell_cutoff_hz = 380.0                  # a small head, and a tight one
    # Balance-normalised against the MEASURED nylon guitar (GM 24) on the same
    # passage in the same room -- the plucked family's reference-audio member.
    initial_gain = 0.0818031
                    # balance-normalised below


class ShamisenProperties(MembraneBodyProperties):
    """GM 106. Silk over a skin, struck with a bachi -- and a SAWARI buzz.

    The sawari is the same idea as the sitar's jawari and is the reason both
    instruments sound related despite sharing no geometry: the lowest string is
    left to graze a deliberately shallow ledge at the nut, so it rattles against
    it and the upper partials are sustained instead of being damped away. It is
    modelled as the sitar models its own -- a very shallow spectral rolloff and
    an upper series that decays barely faster than the fundamental -- rather
    than as a contact, because a grazing contact is a nonlinearity the renderer
    has no way to integrate.

    ONLY THE LOWEST STRING HAS IT on the real instrument, and here it is applied
    across the compass. A per-register version would need the strike and the
    rolloff to move with pitch, which is the koto's movable-bridge problem in
    reverse and is not worth the machinery for a voice with no reference.

    A bachi is a large heavy plectrum, so the exciter is WIDE where the banjo's
    fingerpick is narrow: the comb notch fills and the attack is a thud rather
    than a click.
    """
    strike_point = 0.18
    strike_depth = 0.55         # a wide plectrum fills its own notch
    strike_fills_with_force = False
    tonal_dampening = 0.45      # the sawari: shallower even than the sitar's
    harmonic_decay_db = 0.9     # ...and the top survives
    decay_db = 3.8
    max_harmonic = 64
    initial_gain = 0.032913


class KotoProperties(FormantBody, PluckedStringProperties):
    """GM 107. Thirteen long silk strings over a long hollow paulownia box.

    The opposite instrument to the banjo in every way that matters here. A koto
    string is long, slack and silk or nylon, and it runs over a large light
    WOODEN body -- so where a banjo is bright, thin and quick, a koto is round,
    full and rings for a long time.

    THE MOVABLE BRIDGES ARE WHY IT IS NOT A HARP. Each string has its own ji
    that the player positions, so the speaking length is set per string and the
    pitch comes from where the bridge sits rather than from the string's own
    tension being tuned. What that means for the model is that the strings are
    all of similar make and length: the inharmonicity is uniform and very low
    across the compass, which is unlike a piano or a harp, whose bass strings
    are wound and different in kind.

    ASSERTED, NOT MEASURED.
    """
    # A long light box: a broad low resonance and a second in the low-mid,
    # with plenty radiated below them -- a koto has real bottom.
    formants = ((280.0, 200.0, 0.75), (900.0, 700.0, 0.45))
    formant_floor = 0.16
    bore_corner_hz = 3200.0
    bore_order = 2.0
    bell_cutoff_hz = 110.0
    bell_order = 2.0

    # Tsume: picks on three fingers, plucked well away from the bridge.
    strike_point = 0.22
    strike_depth = 0.70
    strike_fills_with_force = False

    # Long, slack, silk: almost no stiffness, and it rings.
    inharmonicity_coefficient = 6.0e-06
    inharmonicity_dynamic = False
    decay_db = 0.9
    harmonic_decay_db = 1.3
    harmonic_decay_dampening = 0.0
    tonal_dampening = 1.35
    max_harmonic = 40
    initial_gain = 0.0571298


class KalimbaProperties(FormantBody, PluckedStringProperties):
    """GM 108. A plucked metal TINE, which is not a string and not a bar.

    It was on MalletProperties, which is a struck bar. A kalimba's tine is a
    CANTILEVER -- clamped at one end and free at the other -- and a cantilever's
    modes are not a bar's and certainly not a string's. The free-free bar a
    marimba uses runs 1 : 3.01 : 5.03; a clamped-free cantilever runs

        1 : 6.267 : 17.55

    which is far wider, and it is why a kalimba's overtones do not fuse into a
    pitch the way a marimba's do but sit above the note as separate pings.

    Those are the same ratios the Rhodes tine has, and for the same reason --
    a Rhodes tine is also a cantilever -- but the two instruments make opposite
    use of them. A Rhodes damps its tine's overtones with a tonebar and reads
    the fundamental with a pickup; a kalimba has neither, so the overtones
    radiate and are most of the attack.

    THE SECOND MODE IS BARELY THERE, though, because a thumb plucks the tine
    near its free END, where the second mode has a node close by. That is the
    same comb argument every plucked string here uses, applied to a cantilever.

    ASSERTED, NOT MEASURED.
    """
    mode_ratios = (1.0, 6.267, 17.55)
    mode_gains = (1.0, 0.16, 0.05)
    max_harmonic = 3

    # A slotted wooden box or a gourd: one broad resonance, and it is what
    # makes a kalimba audible at all -- the tine alone moves almost no air.
    formants = ((420.0, 500.0, 0.85),)
    formant_floor = 0.22
    bore_corner_hz = 4500.0
    bore_order = 2.0
    bell_cutoff_hz = 180.0
    bell_order = 2.0

    # Metal, plucked and undamped: the fundamental rings and the high modes go
    # first, which is what a thin tine's radiation does.
    decay_db = 1.8
    harmonic_decay_db = 2.6
    harmonic_decay_dampening = 0.0
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False
    initial_gain = 0.056563


# HOW LOUD THE DRONES ARE, 0 to switch them off entirely. A bagpipe patch that
# drones is right -- the reference implementation does it and the program is
# called Bag pipe, not Chanter -- but a score that writes its own drone as held
# notes would then have it twice, and a voice cannot tell. So it is a setting,
# the way the electric piano's voicing and the honky-tonk's detune are.
#
# A COUNT, NOT A GAIN. This was a continuous volume multiplier, and a piper does
# not turn a drone down: they CORK it. So the wheel selects how many drones are
# sounding, out of the set the instrument actually has -- and each step is a
# pipe that existed, because the Great Highland Bagpipe carried two tenors for
# most of its history and the bass drone was added later:
#
#     0 drones   the chanter alone, which is what a practice chanter is
#     1 drone    a tenor -- what you hear while a piper tunes one at a time
#     2 drones   two tenors: the instrument before the bass was added
#     3 drones   two tenors and a bass: the modern pipe
#
# Three is the default, because a bagpipe's resting state is DRONING and most
# files carry no CC1 at all. (The Rhodes is the opposite case: its panel
# tremolo is off until asked for, so absence there means silence.)
# GM Level 1's power-on channel volume. NOT 127, which is what both renderers
# assumed: the spec says a channel that has never been told otherwise sits at
# 100, four decibels down, leaving room for a part to be turned UP as well as
# down. 53 of the 217 files in the corpus never send CC7 at all and every one
# of them is now 4.2 dB quieter, which is the point -- a mix where nothing can
# rise above the default is not a mix.
#
# ONE CONSTANT, read by blockrender.cv() and live._chan_gain, because two
# numbers in two files that happen to agree is not agreement.
GM_DEFAULT_VOLUME = 100
# AFTERTOUCH, in one place. live.Live carried press_db = 8.0 and press_tilt =
# 0.30 as its own numbers and blockrender had none at all; two constants in two
# files that happen to match is not agreement. A wind player leaning in is
# louder AND brighter together, which is why this is a dB and a tilt rather
# than a gain: see Slab.press and _press_tilt.
PRESS_DB = 8.0
PRESS_TILT = 0.30
# GM's default pitch-bend range: +/- 2 semitones at full wheel. RPN 0 changes
# it; live.Live.bend_range is the same number, and both read this one.
BEND_RANGE_SEMITONES = 2.0


def bend_ratio(pitch, semitones=None):
    """A MIDI pitch-wheel value, -8192..8191, as a frequency ratio."""
    st = BEND_RANGE_SEMITONES if semitones is None else semitones
    return 2.0 ** (float(pitch) / 8192.0 * st / 12.0)

# ------------------------------------------------- CC5, the portamento speed
#
# ROLAND SAYS RATE AND DOES NOT SAY HOW MUCH. The VE-GS Pro MIDI Implementation
# -- the primary source, since the SC-55 manual is a scan with no text layer --
# specifies only that CC5 "adjusts the RATE of pitch change" and that "a value
# of 0 results in the fastest change", with an initial value of 0. The curve
# from the 0-127 byte to a real speed is not published by anyone, so it is
# chosen here, once, and both renderers read it from this one place rather than
# each having an opinion.
#
# Anchored on a SEMITONE because that is the interval a player is thinking in:
# a semitone glide takes 2 ms at CC5=0 -- which is to say it does not sound
# like a glide at all, which is what "fastest" has to mean -- and 300 ms at
# CC5=127. Geometric in between, because a linear ramp through a range this
# wide spends most of its travel in the part nobody uses.
PORTA_SEMITONE_FAST = 0.002     # seconds at CC5 = 0
PORTA_SEMITONE_SLOW = 0.300     # seconds at CC5 = 127

# WHAT A HAND ACTUALLY COVERS. A slide moves in metres and a string is stopped
# at a place, so the distance in a glide is a LENGTH DIFFERENCE -- and since f
# is 1/L, that is |1/f_src - 1/f_tgt| up to the instrument's own scale. Measured
# against a semitone at A440, so CC5 has a fixed meaning to anchor to.
#
# TWO CONSEQUENCES, BOTH TRUE OF A TROMBONE AND NEITHER PUT IN BY HAND. The
# same interval takes the same time in either direction, because it is the same
# travel; and the same interval takes LONGER LOW than high, because a semitone
# down in the pedal register is far more slide than a semitone at the top. An
# earlier draft normalised the travel by the target length instead, which made
# a glide up 25% slower than the identical glide down -- an artefact of the
# normalisation that would have had to be defended as if it were physics.
_PORTA_REF_HZ = 440.0
_PORTA_D_SEMI = (1.0 - 2.0 ** (-1.0 / 12.0)) / _PORTA_REF_HZ


def porta_semitone_time(cc5):
    """The settle time constant CC5 asks for, for a glide of one semitone."""
    v = min(127.0, max(0.0, float(cc5))) / 127.0
    return PORTA_SEMITONE_FAST * (PORTA_SEMITONE_SLOW / PORTA_SEMITONE_FAST) ** v


def glide_g(f_target, f_source):
    """The kernel's glide coefficient: f_target/f_source - 1.

    The frequency factor is 1/(1 + g*e^(-t/tau)), so t=0 gives the source pitch
    exactly and t->infinity the target the note was built at. It is also, read
    the other way, the fractional change in LENGTH: L is 1/f, so L_source over
    L_target is f_target over f_source, and g is how much of the length the
    hand has to cover. That is why it, and not the interval in cents, is what
    the speed divides into below.
    """
    return float(f_target) / float(f_source) - 1.0


def glide_travel(f_target, f_source):
    """How far the mechanism has to move, in units of 1/Hz -- i.e. of length."""
    return abs(1.0 / float(f_source) - 1.0 / float(f_target))


def glide_tau(cc5, f_target, f_source, mechanism='slide'):
    """Settle time constant for a glide, from CC5 and how far it has to go.

    TWO LAWS, AND THE DIFFERENCE IS THE POINT. A hand holds a SPEED, so the
    time it needs is proportional to the DISTANCE -- which is what Roland's
    word "rate" means, and which is why the travel above is in length and not
    in cents. A lag circuit holds a TIME: its capacitor does not know how far
    the control voltage moved, so a synthesiser's portamento takes about as
    long for an octave as for a semitone.

    The two agree at a semitone around A440, by construction, so CC5 means one
    thing on a trombone and on a saw lead until the interval -- or the register
    -- opens up.
    """
    t1 = porta_semitone_time(cc5)
    if mechanism == 'circuit':
        return max(1e-4, t1)
    return max(1e-4, t1 * glide_travel(f_target, f_source) / _PORTA_D_SEMI)


# How many time constants of glide to render before calling it arrived. An
# exponential settle never actually lands, and 5 tau is 99.3% of the length
# travelled -- under a cent for anything short of a two-octave sweep.
PORTA_SETTLE_TAUS = 5.0

# ------------------------------------------ the RPNs, arithmetic in one place
#
# BOTH RENDERERS CALL THESE. live.py had the only copy of this arithmetic and
# the file renderer had none at all -- a file that asked for a bend range of 12
# was bent over 2, and fine and coarse tuning were read by nobody. Writing it a
# second time in blockrender would have produced two implementations of one
# number, which is how this codebase has twice ended up with the two renderers
# disagreeing by a quantisation step nobody could explain. So it lives here,
# pure, with the state passed in and the new value passed back.

def rpn_bend_range(cc, value, current):
    """RPN 0/0, pitch bend sensitivity, in semitones.

    CC6 is semitones and ZEROES the cents -- the universal convention, and what
    makes a bare 101/100/6 exact, which is what almost every file sends. CC38
    then adds cents to whatever whole semitones are there.
    """
    if cc == 6:
        return float(value)
    return float(int(current)) + value / 100.0


def rpn_fine(cc, value, msb):
    """RPN 0/1, channel fine tuning: 14-bit, +/-100 cents.

    Returns (msb to keep, cents). CC6 alone is a coarse step with the LSB
    taken as zero; CC38 fills in the LSB under the last MSB seen.
    """
    if cc == 6:
        msb = value
    lsb = value if cc == 38 else 0
    return msb, ((msb << 7 | lsb) - 8192) / 8192.0 * 100.0


def rpn_coarse(cc, value):
    """RPN 0/2, channel coarse tuning, whole semitones from 64. MSB only."""
    return float(value - 64) if cc == 6 else None


# RPN 0/5 is GM 2's MODULATION DEPTH RANGE: how far the mod wheel's vibrato
# reaches at full. MSB in semitones, LSB in 128ths of a semitone. Roland's
# VE-GS Pro does not implement it, so there is no reference text to quote here
# and this is the GM 2 definition as understood -- the LSB unit in particular.
RPN_MOD_LSB_CENTS = 100.0 / 128.0

def rpn_mod_range(cc, value, current_cents):
    """RPN 0/5, modulation depth range, in cents."""
    if cc == 6:
        return float(value) * 100.0
    return float(int(current_cents // 100.0)) * 100.0 + value * RPN_MOD_LSB_CENTS


def rpn_tuning_program(cc, value):
    """RPN 0/3, MIDI Tuning Standard program select: the data entry MSB.

    Read by every renderer and ACTED ON only under the `gm2` tuner, which is
    the one that keeps a store to select from (mts.TuningStore). The MTS text:
    "Bn 64 03 65 00 06 tt" -- the data entry MSB is the program, shown to
    users as 1-128 and sent as 0-127. Data increment and decrement (CC96/97)
    step it by one: see rpn_step.
    """
    return int(value) if cc == 6 else None


def rpn_tuning_bank(cc, value):
    """RPN 0/4, MIDI Tuning Standard bank select: the data entry MSB."""
    return int(value) if cc == 6 else None


# CC96/97, DATA INCREMENT AND DECREMENT: one unit of the parameter's FINEST
# byte, clamped to its range. The MTS text is the only primary source to hand,
# and it uses them to step a tuning program ("Bn 64 03 65 00 60 7F (data
# increment)"), where one is the only unit there is; this generalises that to
# the least significant byte each RPN uses, and is a convention, stated as one.
# The value byte is ignored, as in the MTS example.
RPN_STEP = {
    (0, 0): (0.01, 0.0, 127.99),                       # bend range, 1 cent
    (0, 1): (100.0 / 8192.0, -100.0, 100.0 * 8191.0 / 8192.0),   # fine, 1 LSB
    (0, 2): (1.0, -64.0, 63.0),                        # coarse, 1 semitone
    (0, 3): (1.0, 0.0, 127.0),                         # MTS tuning program
    (0, 4): (1.0, 0.0, 127.0),                         # MTS tuning bank
    (0, 5): (100.0 / 128.0, 0.0, 127.0 * 100.0 + 127.0 * 100.0 / 128.0),  # mod range
}


def rpn_step(sel, current, up):
    """The selected RPN's value after one CC96 (up) or CC97 (down), or None."""
    st = RPN_STEP.get(sel)
    if st is None:
        return None
    step, lo, hi = st
    v = float(current) + (step if up else -step)
    v = min(hi, max(lo, v))
    if sel in ((0, 2), (0, 3), (0, 4)):
        v = float(int(round(v)))
    return v


def rpn_fine_msb(cents):
    """The data-entry MSB a fine-tuning value in cents corresponds to."""
    code = int(round(float(cents) / 100.0 * 8192.0)) + 8192
    return max(0, min(16383, code)) >> 7


# ---------------------------------------------- the legato attack
#
# A SLUR IS ONE NUMBER. The previous note ran up to this one, so the exciter
# never stopped and there is no onset to make: the attack time becomes the
# voice's legato_attack_s where that is shorter, and everything the attack
# feeds -- the wavelength-scaled speech, CC73, the caps, the fade (`fa`) and the
# chiff width (`ch`) -- follows from it unchanged. Onset, phases, strike noise
# and a bloom copy's own swell are not the attack and do not move.
#
# WHY LIVE MAY APPLY IT AFTER THE STAMP. Every step from the attack time to
# `fa` and `ch` is non-decreasing: speech_time adds, CC73 multiplies by a
# positive factor, the caps are min()s, and chiff_time returns its argument or
# a min of it. So for any such chain F, F(min(at, lg)) == min(F(at), F(lg)),
# and a template built with the full attack can be slurred by taking the min
# of what it holds and what the legato attack alone would give.


def slur_attack(at, cls):
    """The attack time of a SLURRED note: `at`, or the voice's legato attack
    where that is shorter. Voices with none (struck, plucked, the organ, whose
    every pipe has its own valve) are returned unchanged."""
    lg = getattr(cls, 'legato_attack_s', None)
    return at if lg is None else min(at, lg)


def slur_fade(cls, f0):
    """(fade, chiff) in seconds for the legato attack alone, before CC73 and
    before the note-length caps -- the F(lg) above -- or None if the voice has
    no legato attack. Read off the CLASS: speech_time and chiff_time touch only
    class attributes, and a live note must not build a properties instance on
    the audio thread to ask."""
    lg = getattr(cls, 'legato_attack_s', None)
    if lg is None:
        return None
    s = cls.speech_time(cls, lg, f0)
    return s, cls.chiff_time(cls, f0, s)


# ---------------------------------------------- CC0/CC32, bank select
#
# LATCHED: "Bank select is suspended until receiving Program change" (SC-55
# owner's manual p.74; the VE-GS Pro text says the same). CC0 and CC32 are
# remembered per channel and only a program change reads them -- and goes on
# reading them, since nothing clears them but a reset.
#
# THREE DIALECTS SHARE THE TWO BYTES, and this is the one place they meet:
#
#   GS (SC-55/88)   MSB = the variation number, 0 the capital tone. The SC-55
#                   ignores the LSB; later modules use it to pick a sound map.
#                   A drum part's set is chosen by program change alone.
#   GM 2            MSB 121 melodic with LSB = the variation, 120 drums.
#   XG              MSB 0 normal, 127 drums, 64 sound effects.
#
# RESOLVED FOR GS FIRST, because the SC-55 is what the corpus was written for,
# and GM 2's two values are taken because nothing in GS uses them. A drum
# channel stays drums under any other MSB: GS files send CC0 = 0 on channel 10
# as a matter of course, and reading that as XG's "MSB 0 is melodic" would turn
# every such kit into a piano. MSB 127 on a MELODIC channel is therefore the
# GS CM-64 map (a variation, falling back to capital), not XG drums.
#
# rx_bank is Roland's Rx.BANK SELECT: "set to OFF by Turn General MIDI System
# On, and set to ON by GS RESET" (VE-GS Pro MIDI Implementation), and on by GM 2
# System On, whose whole sound set is addressed through it.
GM2_DRUM_BANK = 120
GM2_MELODIC_BANK = 121


def resolve_patch(msb, lsb, program, was_drums, rx_bank=True):
    """(drums, program, variation) for a program change under a latched bank.

    `was_drums` is what the channel was before -- channel 10 starts as drums.
    Variation 0 is the capital tone; patch_map.variation_class falls back to it
    for any variation not built, as a Sound Canvas does.
    """
    if not rx_bank:
        return bool(was_drums), int(program), 0
    if msb == GM2_DRUM_BANK:
        return True, int(program), 0
    if msb == GM2_MELODIC_BANK:
        return False, int(program), int(lsb)
    if was_drums:
        return True, int(program), 0
    return False, int(program), int(msb)


# ---------------------------------------------- CC71-78, the sound controllers
#
# RELATIVE AND CENTRED, as Roland defines the same controls in GS: its NRPNs
# 01 08/09/0A (vibrato rate, depth, delay), 01 20/21 (cutoff, resonance) and
# 01 63/64/66 (attack, decay, release) are each a "relative change -64 ... +63"
# stacked on the sound's own setting. GM 2 gave them CC numbers; both forms are
# read. Value 64, or no message, is the voice exactly as it is.
#
# THE LAWS ARE CHOSEN, NOT PUBLISHED. Roland gives the range and not the amount,
# and no GM 2 text was to hand when these were written. One shape per kind of
# quantity: times scale by up to four either way, a rate by two, a cutoff by two
# octaves, brightness by the +/-12 dB of effort velocity already clamps to.
SOUND_CC = {71: 'resonance', 72: 'release', 73: 'attack', 74: 'brightness',
            75: 'decay', 76: 'vib_rate', 77: 'vib_depth', 78: 'vib_delay'}
GS_SOUND_NRPN = {(1, 0x08): 76, (1, 0x09): 77, (1, 0x0A): 78, (1, 0x20): 74,
                 (1, 0x21): 71, (1, 0x63): 73, (1, 0x64): 75, (1, 0x66): 72}
SOUND_EFFORT_DB = 12.0          # brightness at the extremes, as effort
SOUND_TIME_RANGE = 4.0          # attack, decay, release: x/ 4
SOUND_CORNER_RANGE = 4.0        # a synth's cutoff: two octaves either way
SOUND_Q_RANGE = 4.0             # resonance: Q x/ 4 about Butterworth
SOUND_VIB_RATE_RANGE = 2.0      # vibrato rate x/ 2
SOUND_VIB_DEPTH_CENTS = 30.0    # vibrato depth added at full
SOUND_VIB_DELAY_S = 1.0         # vibrato delay at full
VIB_BLOOM_S = 0.25              # how long a delayed vibrato takes to bloom in;
                                # synthkernel.c's VIB_BLOOM must match


def sound_offset(value):
    """d in -1 ... +0.98 from a 0-127 controller value; 64 is 0."""
    return (float(value) - 64.0) / 64.0


def sound_time_scale(d):
    return SOUND_TIME_RANGE ** d


def sound_vib_rate(d):
    return SOUND_VIB_RATE_RANGE ** d


def sound_vib_depth_add(d, base_mean):
    """Depth to ADD to a voice's own, as a fraction of frequency.

    Upward it adds up to SOUND_VIB_DEPTH_CENTS, because most solo voices have
    no vibrato and a multiple of nothing is nothing. Downward it takes the
    voice's own depth toward zero.
    """
    if d >= 0.0:
        return d * (2.0 ** (SOUND_VIB_DEPTH_CENTS / 1200.0) - 1.0)
    return d * float(base_mean)


def sound_vib_delay(d):
    return max(0.0, d) * SOUND_VIB_DELAY_S


def sound_controls_of(cls):
    """What this instrument answers of CC71-78, after the two blanket rules.

    A registerable instrument answers none: it is set up by its stops, not
    shaded by a player. A one-shot answers decay alone: nothing it does after
    the strike is a player's, but how long it rings is the instrument's.
    """
    if cls is None or getattr(cls, 'registerable', False):
        return frozenset()
    if getattr(cls, 'one_shot', False):
        return frozenset(('decay',))
    return getattr(cls, 'sound_controls', frozenset())


def _two_pole(x, q):
    """|H| of a two-pole low-pass at x = f/fc, with quality q."""
    import numpy as np
    return 1.0 / np.sqrt((1.0 - x * x) ** 2 + (x / q) ** 2)


def sound_shape(cls, nf, d_bright, d_res):
    """A per-partial gain for brightness and resonance, NOT yet normalised.

    The caller normalises it to keep the note's power: both controls are
    COLOUR, not level, the separation the bore filter and aftertouch keep. The
    same function shapes the note in both renderers, so they agree by
    construction rather than by algebra.

      brightness, effort voices:   (f/f0)^(effort_tilt * dB / 6.0206), the
                                   aftertouch law -- a harder breath
      brightness, synthesisers:    the low-pass corner moved, as a ratio of the
                                   voice's own filter to the moved one
      resonance, synthesisers:     a resonant peak at that corner, as a ratio
                                   of a two-pole response at Q to a Butterworth
                                   one -- exactly 1 when the Q is unchanged
      resonance, a mute:           its own resonance's Q
    """
    import numpy as np
    nf = np.asarray(nf, dtype=np.float64)
    g = np.ones_like(nf)
    ctl = sound_controls_of(cls)
    if not len(nf):
        return g
    if d_bright and 'brightness' in ctl:
        et = getattr(cls, 'effort_tilt', 0.0)
        corner = getattr(cls, 'bore_corner_hz', 0.0)
        if et:
            k = et * (SOUND_EFFORT_DB * d_bright) / 6.0206
            g *= (nf / max(float(nf.min()), 1e-9)) ** k
        elif corner:
            order = getattr(cls, 'bore_order', 2.0)
            c2 = corner * SOUND_CORNER_RANGE ** d_bright
            g *= (1.0 + (nf / corner) ** order) / (1.0 + (nf / c2) ** order)
    if d_res and 'resonance' in ctl:
        mq = getattr(cls, 'mute_resonance_q', 0.0)
        corner = getattr(cls, 'bore_corner_hz', 0.0)
        if mq and getattr(cls, 'mute_resonance_hz', 0.0):
            hz = cls.mute_resonance_hz
            boost = 10.0 ** (getattr(cls, 'mute_resonance_db', 0.0) / 20.0) - 1.0
            r = nf / hz
            q2 = mq * SOUND_Q_RANGE ** d_res
            g *= ((1.0 + boost / (1.0 + (q2 * (r - 1.0 / r)) ** 2))
                  / (1.0 + boost / (1.0 + (mq * (r - 1.0 / r)) ** 2)))
        elif corner:
            c = corner * (SOUND_CORNER_RANGE ** d_bright
                          if (d_bright and 'brightness' in ctl
                              and not getattr(cls, 'effort_tilt', 0.0)) else 1.0)
            x = nf / c
            q0 = 0.5 ** 0.5
            g *= _two_pole(x, q0 * SOUND_Q_RANGE ** d_res) / _two_pole(x, q0)
    return g


def normalise_power(amp, gain):
    """Scale `gain` so amp*gain carries amp's power: colour, not level."""
    import numpy as np
    amp = np.asarray(amp, dtype=np.float64)
    p0 = float((amp * amp).sum())
    p1 = float(((amp * gain) ** 2).sum())
    return gain * ((p0 / p1) ** 0.5 if p1 > 0.0 and p0 > 0.0 else 1.0)


def channel_pitch_ratio(range_st, wheel, coarse_st, fine_cents,
                        master_coarse_st=0.0, master_fine_cents=0.0):
    """The one number everything that tunes a channel reduces to.

    Wheel over its range, plus the channel's coarse and fine tuning, plus the
    device's master coarse and fine tuning. Five inputs, one ratio -- which is
    why any of them can move without fighting the others, and why the file
    renderer's tuning/gesture split can be run on the product rather than on
    each input separately.
    """
    st = (range_st * wheel / 8192.0 + coarse_st + fine_cents / 100.0
          + master_coarse_st + master_fine_cents / 100.0)
    return 2.0 ** (st / 12.0)


# Master Volume, Universal Realtime F0 7F dd 04 01 ll mm F7. Roland's text says
# the LSB "will be handled as 00H"; it is read here, since a device that uses
# it is not wrong. The LAW is the one CC7 uses, squared, because the GM 2 text
# for it is not to hand and a master fader that tapered differently from a
# channel fader would be a surprise nobody asked for.
def master_volume_gain(v14):
    return (max(0, min(16383, int(v14))) / 16383.0) ** 2

GM_DEFAULT_EXPRESSION = 127     # CC11 does start at full: it is an attenuator
GM_DEFAULT_PAN = 64             # centre

# CC67 for the note being built, set by the renderer exactly as
# bagpipe_drones and honky_detune are: a per-note fact that reaches the voice
# through the one place that knows both the file and the class.
soft_pedal_down = False

bagpipe_drones = int(os.environ.get("TUNING_BAGPIPE_DRONE", "3") or 3)
# WHERE LOW A ACTUALLY LANDED, which only the renderer knows: it owns the
# tuning table, and the drones are tuned to the chanter rather than to a fork.
# 440 is the fallback and the equal-tempered answer, so nothing that never sets
# it moves. See BagpipeProperties.drone_ratios.
bagpipe_tonic_hz = 440.0


class BagpipeProperties(ReedPipeProperties):
    """GM 109. A chanter, and the DRONES -- which are the instrument.

    109 and 111 shared one ReedPipeProperties, and the thing that most obviously
    separates a bagpipe from a shawm is not its reed: it is that a bagpipe plays
    a continuous drone underneath everything, at a FIXED pitch, which never
    changes with the melody. No other voice in this bank does that.

    A FIXED PITCH IS EXPRESSIBLE, and it takes one line. unison_voices is handed
    the note's own frequency, so a voice at `drone_hz / frequency` sounds at
    drone_hz whatever is played -- every other user of that hook returns a
    RATIO, which tracks the note by construction. A drone is the one thing that
    must not.

    AND IT IS A CHANNEL EVENT, which took the renderer change this class
    first only promised. The drones were attached to the note and so
    restarted on every one. They now sound ONCE for the channel, from its
    first note-on to its last note-off, which is what a bag under pressure
    does -- see unison_spans_part on SynthProperties.

    AND CC1 CORKS THEM, which is not a hedge. Including the drones matches the
    reference implementation and the program's own name -- a bagpipe without
    them is a chanter, which is a different instrument -- but an arranger who
    writes the drone as held notes in the score would then have it TWICE, and a
    voice cannot detect that.

    ON THE WHEEL, AND READ ONCE. No real module gives you this: General MIDI
    specifies no control and the SC-55 bakes the drone into the patch. But CC1
    in this renderer is consistently the one panel control a voice has -- the
    Rhodes' tremolo depth, the Hammond's half-moon switch, the clavinet's tone
    rockers, the honky-tonk's detune -- and there is a real-instrument answer
    too: a piper CORKS a drone before playing, not during. Playing with one
    tenor corked is ordinary practice. So it is a setup value taken from the
    channel's first CC1, exactly as the clavinet's rockers and the amplifier's
    drive are, rather than a control moved mid-phrase.

    64 is the voiced default and 0 corks them all, which is the honky-tonk's
    convention: a file with no CC1 gets the instrument as voiced, because the
    default position of a bagpipe is DRONING. (The Rhodes is the opposite case
    -- its panel default is off, so silence is what no CC1 should give.)
    TUNING_BAGPIPE_DRONE sets it for a whole render.

    THREE DRONES, NOT TWO, and the third is the point. A Highland pipe carries
    TWO TENOR drones at A3 and one BASS at A2 -- and the two tenors are at the
    same nominal pitch, which makes them a chorus rather than a doubling. They
    beat, they always beat, and a piper spends real effort getting that beat
    slow: "drone lock" is the sound of two reeds almost agreeing. Rendering one
    tenor loses it completely, which is what this class did first.

    Three cents apart is about 0.38 Hz at A3 -- a shimmer over a couple of
    seconds, which is a well-tuned pipe. A badly tuned one beats far faster and
    is unmistakable; that is the same knob, turned up.

    THE PITCH IS FIXED BECAUSE THE INSTRUMENT IS. A chanter has nine notes and
    the drones are tuned to it, so a piper cannot change key -- which means a
    drone that ignores the melody is not a limitation of this model, it is the
    instrument. (The chanter's A is famously sharp of concert, nearer 480 Hz
    than 440, but the drones are tuned to the chanter rather than to a fork, so
    what matters here is the interval and not the reference.)
    """
    # CC71-78: NOTHING: the bag is at the pressure the arm holds, the chanter
    # has no dynamics, and a piper does not vibrate.
    sound_controls = frozenset()
    # Nine holes and a bag at constant pressure: see scale_cents.
    pitch_bendable = False
    # Two tenors and a bass. The tenors are a chorus: same nominal pitch, a few
    # cents apart, beating slowly.
    # THE DRONES ARE THE PART, NOT THE NOTE. Ben: "The drones seem to me
    # to be a channel event?" -- and they are. A real drone sounds
    # continuously from the moment the bag is under pressure; attaching it
    # to the note made it restart on every one, inaudible on a legato line
    # and wrong on a detached one. This tells the renderer to emit them
    # once for the channel, across its whole range.
    unison_spans_part = True
    drone_wheel = True          # CC1 corks them; see the docstring

    # AND IT IS NOT TOUCH SENSITIVE, which is the same argument as the organ's
    # and reaches it by a different route. Ben: "it should be more like an
    # organ: not touch sensitive. Channel volumes only."
    #
    # A BAG IS A PRESSURE REGULATOR. That is what it is FOR: the piper's arm
    # holds the bag at a constant pressure and the reeds see that pressure and
    # nothing else, which is precisely why a piper can breathe without the
    # sound stopping. There is no dynamic marking in pipe music and no way to
    # play one -- a Highland pipe has exactly one volume, and the expression is
    # entirely in grace notes and in time.
    #
    # It got True by default rather than by a claim: ReedPipeProperties sits
    # under ReedOrganProperties, but the False lives on FlueOrganProperties, so
    # the whole reed-pipe chain fell through to SynthProperties' default. That
    # is right for the shanai, which is mouth-blown -- a shawm player's breath
    # IS the dynamic -- and wrong for the one pipe with a bag in the way.
    #
    # ONLY attack_volume IS NEUTRALISED, as everywhere: CC7 and CC11 still
    # work, and on a pipe band that is the only balance there is.
    touch_sensitive = False

    # A BAGPIPE IS ALWAYS LEGATO, and it is the only voice in this bank for
    # which that is a fact about the instrument rather than a choice by the
    # player. Every other voice that declares legato_attack_s -- the clarinet,
    # the flute, the bowed strings -- is describing a SLUR, which a player
    # elects instead of tonguing or re-bowing. A piper has no such election:
    # the reed is fed by a bag under constant arm pressure, there is no tongue
    # anywhere near it, and the chanter cannot be stopped. Notes change by
    # moving fingers on a sounding pipe, and that is the only way they change.
    #
    # Hence a legato attack shorter than any other voice's, and hence also the
    # grace notes in examples/scotland.py: with no way to put a gap between two
    # of the same note, a piper flicks a higher finger for a few milliseconds,
    # and that flick is the instrument's entire articulation.
    legato_attack_s = 0.004     # the clarinet's is 0.012, and it can tongue

    # ---- THE PIPER'S SCALE, which is not a temperament ---------------------
    # Nine holes, cut once, and the reason they are where they are is sounding
    # three feet away over the piper's shoulder. Every note of a chanter is
    # tuned to BEAT CLEANLY AGAINST A FIXED A DRONE, which makes the scale
    # just intonation on Low A and not a compromise between keys -- a pipe
    # cannot change key, so it has nothing to compromise for.
    #
    #        Low G   -204   9/8 below the tonic
    #        Low A      0   the drone's own note
    #        B       +204   9/8
    #        C#      +386   5/4   (14 cents FLAT of equal, and audibly so)
    #        D       +498   4/3
    #        E       +702   3/2
    #        F#      +884   5/3   (16 cents flat)
    #        High G  +996   16/9  the famous flat seventh: there is no leading
    #                             tone on a chanter, which is why a song has to
    #                             be adapted rather than transposed to play it
    #        High A +1200
    #
    # THE TONIC STILL FOLLOWS THE RENDER'S TEMPERAMENT, so a pipe band sits
    # with an orchestra at whatever pitch the orchestra is at; only the
    # intervals inside the instrument are the instrument's own. (A real chanter
    # is also famously sharp -- its A is nearer 470 or 480 Hz than 440 -- but
    # that is a reference and not a scale, and pinning it here would make the
    # patch unable to play with anything else. The interval is the physics.)
    scale_tonic_note = 69                       # Low A
    scale_cents = {-2: -203.910, 0: 0.0, 2: 203.910, 4: 386.314,
                   5: 498.045, 7: 701.955, 9: 884.359, 10: 996.090,
                   12: 1200.0}

    # AND THE DRONES ARE RATIOS OF THAT TONIC, not frequencies. They were
    # absolute -- 220, 220.4 and 110 Hz -- which is exactly right under equal
    # temperament at A=440 and silently wrong under every other tuner this
    # renderer has: at `hybrid` the chanter drops to A=415 and the drones
    # stayed at 440, a hundred cents out against the one note they exist to
    # reinforce. A drone is tuned TO THE CHANTER, by ear, before playing.
    #
    # Two tenors an octave below Low A and a bass two octaves below; the three
    # cents between the tenors is the beat, and it is a ratio too.
    drone_ratios = (0.5, 0.5 * 2.0 ** (3.0 / 1200.0), 0.25)
    # NOT EQUAL, and that matters more than it looks. At 0.34 against 0.32 the
    # two tenors very nearly cancel at the trough of their beat -- measured in
    # a rendered tune the 220 Hz band fell to 0.02 of its peak, a 34 dB null.
    # Two reeds in two pipes never do that: they differ in reed, in bore and in
    # how far each sits from the ear, so the beat is a breathing rather than a
    # gap. Unequal gains put the trough at about a quarter rather than at zero.
    drone_gain = (0.36, 0.25, 0.30)

    # A chanter is a loud, bright, double-reed pipe with a narrow conical bore.
    tonal_dampening = 1.05
    max_harmonic = 40
    # Against the MEASURED oboe (GM 68), not the plucked anchor: this class
    # inherits the organ's gain scale, where 0.02 is a hundred times hot.
    initial_gain = 0.000163928

    @property
    def drone_hz(self):
        """The drones, in Hz, against wherever the render put Low A."""
        return tuple(bagpipe_tonic_hz * r for r in self.drone_ratios)

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        f = float(frequency)
        n = max(0, min(int(bagpipe_drones), len(self.drone_ratios)))
        if f <= 0.0 or not n:
            return []
        # A SLICE, because drone_hz is already in the order a piper corks them:
        # (tenor, tenor, bass). Taking the first n therefore walks the
        # instrument's own history backwards, and every intermediate state is a
        # pipe somebody once played.
        return [(g, 0.0, hz / f - 1.0, harmonic_decay, 0.0)
                for hz, g in zip(self.drone_hz[:n], self.drone_gain[:n])]


class ShanaiProperties(ReedPipeProperties):
    """GM 111. A double reed in a CONICAL bore, and no drone at all.

    The other half of the pair 109 and 111 used to share. A shehnai is a shawm:
    a wide double reed driving a conical bore that flares to a metal bell, which
    is an oboe's geometry rather than a bagpipe chanter's, and it is played with
    no drone from the instrument itself -- the drone in the ensemble comes from
    a second player on a sur peti or a second shehnai.

    A CONE PASSES THE WHOLE SERIES where a cylinder favours the odd, so the even
    harmonics that ReedOrganProperties suppresses have to come back. Bright and
    nasal with it: the reed is wide and the bell is metal.

    ASSERTED, NOT MEASURED.
    """
    odd_only = False
    even_harmonic_db = None
    # A shehnai player CAN tongue, so this is a slur they elect -- the clarinet's
    # value, and the distinction the bagpipe above does not get to make.
    legato_attack_s = 0.012
    tonal_dampening = 0.85      # brighter and more nasal than the chanter
    max_harmonic = 48
    bore_corner_hz = 4200.0
    initial_gain = 0.000174797


class OpenPipeProperties(StoppedPipeProperties):
    """An OPEN pipe: flute, piccolo, recorder, whistle, shakuhachi.

    StoppedPipeProperties carries odd_only = True, which is right for the stopped
    ranks our organ pipeline drives through it (a Gedackt is closed at one end
    and resonates at odd multiples only). It is wrong for an orchestral flute,
    which is open at both ends and has the full series. Measured against the
    Iowa MIS flute (nonvib, mf, C5): h2 is 7.1 dB below the fundamental and h3
    is 7.0 -- the second harmonic is as strong as the third, where this model
    was rendering it at -134 dB, which is to say not at all.

    The series also falls away faster above h3 than any single 1/n^d can follow
    (real: -20.5 at h4, -35.7 at h6), so a radiation corner carries that.

    RE-MEASURED against the whole Iowa flute FAMILY -- concert (nonvib), alto
    and bass, 110 notes from concert C3 to C7, four octaves. The first fit here
    used three registers of the concert flute alone.

    THE HEADLINE IS A NEGATIVE RESULT, and it is why octave_dampening is now
    zero. The same test that found the clarinet's register law -- measure the
    quantity across three instruments of one family and see whether it tracks
    absolute pitch -- comes back FLAT for the flute. Spectral tilt sits near
    -15 dB per doubling of harmonic across the whole four octaves, the three
    instruments agree closely at the same concert pitch (at 261.6 Hz: bass
    -15.5, alto -15.5, concert -12.5), and the slope against pitch is only
    -0.45 dB/octave with the three instruments disagreeing on its SIGN.

    That is physically what you would expect. The clarinet's law comes from a
    stopped cylinder ceasing to be stopped as the tonehole lattice opens; a
    flute is open at both ends in every register and has no such transition. So
    the octave_dampening = 0.3 this class used to carry was a register
    dependence in the MODEL that is not in the INSTRUMENT. The fit, run
    independently, put it at -0.013.

    Fitted on the CONCERT flute alone, since GM 73 is a concert flute, with the
    alto and bass HELD OUT ENTIRELY:

                              shape      HF
        concert     before     5.62    7.39
        concert     after      5.75    3.63
        alto+bass   before     7.36   12.11    <- never seen
        alto+bass   after      6.52    6.68

    The broadband error halves on the fitted instrument and on both held-out
    ones, and the held-out shape improves too. Shape on the concert flute itself
    goes 0.13 dB the wrong way, which is the price of the top end being right.

    max_harmonic 32 -> 49: h32 is only 4.2 kHz on the bass flute's low C, where
    the recording still carries 24 harmonics clear of its noise floor.
    """
    # CC71-78: the flutes: breath has an onset, a release and a vibrato.
    sound_controls = frozenset(('attack', 'release', 'vib_rate', 'vib_depth', 'vib_delay'))
    legato_attack_s = 0.012   # a slurred flute: the embouchure holds, the fingering changes
    # A BLOWN INSTRUMENT IS NEVER SILENT BETWEEN ITS HARMONICS, and this was 0.
    # sustain_jitter is the wash's SUSTAINED level in the kernel, so with it at
    # zero the chiff was an attack transient only and the held note was pure
    # sinusoids: the region midway between harmonics measured 138 dB below them,
    # which is numerical silence. The Iowa flute's sits 65 and 57 dB below its
    # first two, with its own room subtracted and only counted where the
    # recording stands at least 6 dB clear of that room. Fitted white (1.9 dB
    # rms) against banded (2.2); a flute's turbulence radiates from the
    # embouchure as well as through the tube, so it is not a plate's wash.
    #
    # WHAT THAT REFERENCE ENERGY IS HAS NOT BEEN ESTABLISHED, and the number
    # above should be read with that caveat. Its spectral flatness is 0.0008 --
    # very peaky, where broadband breath would be near 1 -- so some or most of
    # it may be vibrato sidebands, room reflections, or the skirts of the
    # harmonics leaking into the window rather than breath. An attempt to
    # separate them by tracking the fundamental's instantaneous frequency failed
    # (it returned 42% rms pitch wobble, which is the tracker breaking, not the
    # player). What IS certain is that zero is wrong: a flute's breath is a
    # defining part of its sound and this voice had none of it.
    #
    # The brass are deliberately NOT changed to match. TrumpetProperties already
    # argues that sustain_jitter modulates each partial's phase and so buys the
    # number with the wrong sound, and nothing measured here refutes that -- so
    # its trace value stands. (That note's stated cause, a chiff table that
    # repeated for round frequencies, is gone; its conclusion may not be.) The
    # organ, pan flute, ocarina and blown bottle are left alone for the same
    # reason: same physics, no reference, and the organ corpus is already
    # approved by ear.
    sustain_jitter = 0.2

    odd_only = False
    # FITTED across B3B4, C5B5 and C6B6: RMS 9.27 -> 3.28 dB.
    # Its own gain, trimmed for the fit: it used to inherit
    # StoppedPipeProperties', and trimming that would have moved every pipe voice.
    # +1.03 dB from the first fit, then -0.24 dB more for this one.
    # ...and held against it, since the wash is real energy. The kernel scales
    # the chiff by f0/440, so a piccolo picks up more of it than a flute -- 2.9
    # dB against 1.5 -- and one class-level number cannot hold both. The mean,
    # -2.23 dB, leaves each 0.7 dB from where it was.
    initial_gain = StoppedPipeProperties.initial_gain * 1.0952 * 0.7732
    tonal_dampening = 1.256
    # ZERO, and measured to be: see the class docstring. It was 0.3.
    octave_dampening = -0.0131
    bore_corner_hz = 1580.8
    bore_order = 1.310
    max_harmonic = 49
    # The tube stops radiating below its own lowest resonance.
    bell_cutoff_hz = 319.9
    bell_order = 2.638



class VesselFluteProperties(OpenPipeProperties):
    """An ocarina or a blown bottle: a HELMHOLTZ RESONATOR, not a pipe.

    A vessel flute has no standing wave along a tube. The air in its neck moves
    as a lump against the springiness of the air in the cavity, which is a mass
    on a spring -- ONE resonance, and no harmonic series above it. That is why
    an ocarina is famously close to a pure tone, and why the harmonics it does
    have come from the jet rather than from the body.

    So it is neither of the two voices this family had. It is not an open pipe
    (a full series, which is a flute) and it is not a stopped pipe (odd
    harmonics only, which is a pan pipe -- correctly, since a pan pipe IS closed
    at the bottom). Programs 76 and 79 had been falling through to the stopped
    voice, which gave a bottle and an ocarina the odd-harmonic spectrum of an
    organ rank.

    This is the shared BODY. What separates an ocarina from a blown bottle is
    not the resonator, it is the EDGE that drives it -- see the two subclasses.

    NOT MEASURED. Iowa has no ocarina and no bottle, so unlike every other class
    in this file the numbers here are asserted from the physics rather than
    fitted to a recording: a steep tonal_dampening for the fast harmonic
    fall-off a resonator gives, and a low ceiling because there is nothing up
    there to render. If a reference ever turns up, this is the class to fit.
    """
    odd_only = False
    even_harmonic_db = None
    # Steep: a Helmholtz resonance does not feed a series the way a tube does.
    tonal_dampening = 3.4
    octave_dampening = 0.0
    max_harmonic = 12
    # The cavity radiates from a small mouth, so there is no bell high-pass and
    # the top rolls off early.
    bore_corner_hz = 2200.0
    bore_order = 2.0
    bell_cutoff_hz = 0.0



class OcarinaProperties(VesselFluteProperties):
    """GM 79. A vessel flute with a FIPPLE: a moulded windway aims the breath at
    a sharp labium, the way a recorder does. That is an efficient edge, so most
    of the air goes into driving the resonance and the tone dominates the
    breath. Hence a modest chiff, and the pure singing quality the instrument is
    known for."""
    chiff_volume = 1.0
    chiff_cycle = 0.2


class SambaWhistleProperties(OcarinaProperties):
    """PERCUSSION 71 and 72: the samba/referee whistle, the one with a pea.

    NOT GM PROGRAM 78, which is a HUMAN whistle and is WhistleProperties far
    below. Both classes were called WhistleProperties for a while, and Python
    keeps whichever definition it reads last -- so percussion 71 and 72 were
    built from the whistled note instead of from this. Class attributes, and
    then the table they produce:

        unison_detune   (25, 50, 75, 100)   against  ()       -- the pea
        max_harmonic    64                  against  8
        chiff_volume    6.0                 against  0.55
        sustain_jitter  3.0                 against  0.22

        partials        5598                against  80
        distinct freqs  1117                against  16

    AND THE RENDER BARELY MOVED, which is the part worth keeping. Gross level
    changed 0.5 dB, the 2-3 kHz chamber band 0.8 dB, and the warble depth in
    that band went 0.077 against 0.079 -- because this voice is mostly
    broadband air in either reading, and the air was drowning the difference.
    A seventy-fold change in the partial table arrived as half a decibel.

    That is why the collision survived: nothing raised, nothing logged, and the
    audio was not obviously wrong either. It was found by reading, not by
    listening, and the check that now guards it is the general one -- no two
    classes in this file may share a name -- because the specific check only
    ever gets written after somebody has already noticed.

    THESE WERE DRUMS. Both sat on NoiseDrumProperties with a tuned base of 900
    and 880 Hz -- a struck membrane standing in for a blown resonator, which is
    the wrong family entirely, not a wrong number. A whistle is a fipple over a
    small chamber: air is blown across an edge and the chamber resonates, which
    is an ocarina with a mouthpiece, so it inherits one.

    A whistle is HIGH and NEARLY PURE. It sits around 2.4 kHz with very little
    above its fundamental -- the ocarina's tonal_dampening of 3.4 is already the
    right shape -- and it is very breathy, because the player is forcing a lot of
    air through a small hole. sustain_jitter carries that, higher than the
    ocarina's since a whistle is nothing but breath and one resonance.

    AND IT WARBLES, because of the pea. A cork or plastic ball rattling around
    the chamber interrupts the jet a few dozen times a second, which is the sound
    that makes a whistle a whistle rather than a high recorder. That is
    unison_detune below, NOT strike_wobble_hz, which this paragraph named until
    the mechanism changed underneath it -- see the argument further down for why
    one detuned voice beats smoothly where a pea interrupts.

    ONE WHISTLE, TWO BLASTS: GM 71 is a short toot and 72 a long one, so they
    share this class and differ only in PERCUSSION_RING -- the pattern the hats,
    the ride bell and the triangle all follow.

    NO REFERENCE. Iowa has no whistle, so the frequency, the breath and the pea
    rate are physics and judgement. What is not judgement is that it belongs in
    the pipe family rather than the drum family.
    """
    # A WHISTLE IS NOISE WITH A RESONANCE IN IT, not a resonance with noise on
    # top. Ben: "The whistles were noise driven, not Ocarina-like, with little
    # noise." The first pass inherited the ocarina's eight harmonics, and on a
    # 2.4 kHz base the ninth is past Nyquist -- so the voice had eight partials,
    # the wash had eight places to sit, and forty times the chiff moved its
    # spectral flatness only from 0.039 to 0.105. Broadband air needs partials
    # across the band to ride on, which is what the hi-hat's sub-400 Hz contact
    # region taught.
    #
    # So it is a BODY: 64 modes from 520 Hz to 19 kHz, all weak except the
    # chamber at 2400 and its octave, which are what give the shriek its pitch.
    # Everything else is there to carry air. Measured as the share of energy
    # OUTSIDE the two resonance bands:
    #
    #     weak 0.120   short 27 per cent tonal, long 37   -- barely pitched
    #     weak 0.080         44                      55
    #     weak 0.050         64                      72
    #     weak 0.035         77                      82   -- the air is gone
    #
    # Ben, on 0.120: "Just a little bit more tonality. The high one is still
    # barely tonal. The lower one is a little more, but not enough." Which is
    # what the table says, including the asymmetry: the high whistle is the
    # airier of the two by about nine points at any setting, because its
    # resonance sits higher up the same fixed comb of weak modes.
    #
    # 0.050: clearly pitched, and still half air.
    mode_ratios = (1.0000, 1.0588, 1.1210, 1.1869, 1.2567, 1.3305, 1.4087, 1.4916,
                   1.5792, 1.6721, 1.7703, 1.8744, 1.9846, 2.1012, 2.2247, 2.3555,
                   2.4940, 2.6406, 2.7958, 2.9601, 3.1341, 3.3183, 3.5134, 3.7199,
                   3.9385, 4.1700, 4.4151, 4.6154, 4.9494, 5.2404, 5.5484, 5.8745,
                   6.2198, 6.5854, 6.9725, 7.3823, 7.8163, 8.2757, 8.7622, 9.2308,
                   9.8225, 10.3999, 11.0112, 11.6584, 12.3437, 13.0692, 13.8374, 14.6508,
                   15.5120, 16.4238, 17.3891, 18.4113, 19.4935, 20.6393, 21.8525, 23.1369,
                   24.4969, 25.9368, 27.4614, 29.0756, 30.7846, 32.5941, 34.5100, 36.5385)
    mode_gains = (0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500,
                   0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500,
                   0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500,
                   0.0500, 0.0500, 0.0500, 1.0000, 0.0500, 0.0500, 0.0500, 0.0500,
                   0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.2200,
                   0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500,
                   0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500,
                   0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500)
    max_harmonic = 64
    inharmonicity_coefficient = 0.0
    inharmonicity_dynamic = False

    tonal_dampening = 3.4
    sustain_jitter = 3.0           # a whistle is mostly air
    chiff_volume = 6.0
    one_shot = False
    initial_gain = OcarinaProperties.initial_gain

    # THE PEA CHOPS THE JET, IT DOES NOT WOBBLE THE PITCH. Ben: "Isn't the fipple
    # in the small chamber just a low frequency with a lot of harmonics over the
    # whistle tone?" -- which is the mechanism. A ball circulating in the chamber
    # interrupts the airflow abruptly and repeatedly, and an abrupt periodic
    # interruption at 25 Hz is a low fundamental with a long harmonic series.
    # Multiplied against the tone it puts a COMB of sidebands either side of the
    # resonance at 25, 50, 75, 100 Hz and on, which is most of why a whistle
    # sounds shrill and rough rather than like a very high recorder.
    #
    # strike_wobble_hz, which this used, adds ONE detuned voice -- a single
    # sideband pair, i.e. a vibrato. That is the wrong shape: it modulates
    # smoothly where a pea interrupts. unison_detune takes as many offsets as it
    # is given, so the comb is written out directly, with the partner gains
    # falling as 1/k the way a pulse train's harmonics do.
    # A generator expression in a class body cannot see class-level names, so
    # the comb is written out. 25 Hz and its first three harmonics.
    #
    # DEPTH: THE PEA FLUTTERS THE TONE, IT DOES NOT GATE IT. Ben: "too much
    # stopping, the tone barely comes through." At gain 0.55 the partners sum
    # to 2.85x the carrier, so half the energy in the resonance region was
    # chop rather than tone. Measured as the share within +-8 Hz of the
    # resonance against the sidebands out to +-200 Hz:
    #
    #     gain 0.55   carrier 50 per cent   -- gated
    #     gain 0.30           76
    #     gain 0.20           86            -- the tone leads, the pea flutters
    #     gain 0.15           90
    #
    # And seven comb harmonics is a very sharp interruption; four is a softer
    # one, which is what a ball rolling round a chamber does rather than a
    # shutter. It also halves the partners, from fourteen per partial to eight.
    unison_detune = (25.0, 50.0, 75.0, 100.0)
    unison_gain = 0.20

    def unison_voices(self, frequency, harmonic, harmonic_decay):
        """The pea's comb: partners at +-k*25 Hz with gains falling as 1/k,
        which is the harmonic series of a pulse train."""
        out = []
        for k, offset in enumerate(self.unison_detune, start=1):
            g = self.unison_gain / float(k)
            out.append((g, offset, 0.0, harmonic_decay, 0.0))
            out.append((g, -offset, 0.0, harmonic_decay, 0.0))
        return out

    # AND IT ARRIVES FROM BELOW. Ben: "And the low frequency grows quickly to the
    # sustained pitch?" -- yes, and it is the most recognisable thing about a
    # blown whistle. The chamber will not hold its note until the jet is fully
    # established, so the tone starts flat and sweeps up into place in a few tens
    # of milliseconds: the "wheep" at the front of every whistle blast.
    #
    # tension_bend is the mechanism, running backwards. On a drum it is positive
    # -- a head struck hard is stretched, so the note starts SHARP and settles --
    # and the kernel computes f*(1 + tbav*e^(-t/tau)). A negative value starts it
    # flat and lets it rise, which is what a pressure-driven resonator does.
    tension_bend = -0.045          # ~80 cents flat at the attack, at full blow
    tension_settle_time = 0.045    # and up into place inside 50 ms
    tension_settle_cutoff = 3.0

class BlownBottleProperties(VesselFluteProperties):
    """GM 76. The same Helmholtz body, driven by a MUCH WORSE EDGE.

    Blowing across a bottle top has no windway and no labium -- you aim a
    turbulent jet across an opening and hope. Most of the energy never couples
    into the resonance at all; it stays as broadband turbulence. So a bottle is
    mostly BREATH with a weak tone inside it, which is the opposite balance to
    an ocarina even though the resonator is the same shape of thing.

    The chiff therefore carries the sound rather than starting it. It sits
    between the ocarina's 1.0 and BreathNoiseProperties' 2.4 (GM 121, which is
    breath with no note in it at all), and it SUSTAINS: you keep blowing, and
    the noise keeps moving while the note is held. A wider chiff_cycle makes it
    noise rather than shimmer, the same reason GM 121 uses 0.95.

    Also darker and weaker in the tone than an ocarina: a jet that couples badly
    feeds the resonance badly.

    NOT MEASURED, like its parent -- asserted from how the instrument is played.
    """
    chiff_volume = 2.0
    chiff_cycle = 0.7
    chiff_release = 0.8
    # the breath keeps moving while the note is held (cf. BreathNoiseProperties)
    sustain_jitter = 0.5
    # a badly coupled jet drives the resonance weakly: even less series than an
    # ocarina, and a softer top.
    tonal_dampening = 3.9
    bore_corner_hz = 1600.0

# ----------------------------------------------------------- the rest of 72-79
# The pipe family was two measured flutes (72, 73), two vessel flutes (76, 79),
# and four programs on a generic base. The four are not variations on a flute:
# they differ in the three things that decide what a flue instrument sounds
# like -- whether the tube is open or closed, how the jet is aimed, and how much
# of the breath misses the edge.


class RecorderProperties(OpenPipeProperties):
    """GM 74. A FIPPLE flute: the windway is built into the instrument.

    That single fact is the whole difference from the flute beside it. A
    flautist forms the jet with their lips and can change its length, its angle
    and its width while playing -- which is where a flute's shading, its
    dynamics and its colour come from. A recorder's windway is a duct cut in
    wood: the jet arrives at the labium the same way every time, for every
    player, at every dynamic.

    So a recorder is PURER and more uniform than a flute, and its chiff is
    consistent where a flute's varies with the player. Both follow from the duct
    rather than being separate observations.

    WHAT IS DELIBERATELY NOT MODELLED. A recorder has almost no dynamic range,
    because blowing harder mostly raises the PITCH instead of the level -- there
    are no lips to compensate, which is why recorder consorts play with dynamics
    written into the scoring rather than into the breath. It is tempting to wire
    that to velocity, and it would be wrong here: velocity in a MIDI file is mix
    balance, not effort (see the note on effort being a relative signal), so a
    loud passage would simply play sharp. The attack bloom below is the part of
    it that is honestly velocity-scaled, being a transient that settles.
    """
    # A narrow cylindrical bore, and a duct that puts the jet where it belongs:
    # strong fundamental, and less of the upper development a flute gets from a
    # jet the player is steering.
    # Purer than the flute, and audibly so rather than arguably so: at 1.55 this
    # sat 0.9 dB from the flute at the second harmonic, which is a difference
    # no one could hear and not much of a claim. How MUCH purer is a judgement
    # -- there is no recorder in the reference set -- but that it is purer
    # follows from the duct, and it should be worth saying.
    tonal_dampening = 1.90
    max_harmonic = 32
    bore_corner_hz = 2600.0
    octave_dampening = 0.0

    # The fixed windway again: a crisp, repeatable speech, shorter than a
    # flute's because there is no lip to find the edge with.
    chiff_volume = 1.15
    chiff_min_valve_time = 0.008
    chiff_max_valve_time = 0.020
    # Less breath past the edge than any other member of this family: a duct
    # aims the whole jet at the labium, which is what a duct is for.
    sustain_jitter = 0.12

    # The pressure bloom as the jet establishes -- an attack transient that
    # settles to the tuned pitch, not a sustained offset. See the docstring.
    tension_bend = 0.004
    tension_settle_time = 0.06
    tension_bend_max = 0.01

    # Balance-normalised against the MEASURED flute (GM 73) on the same passage
    # in the same room -- this family's one reference-audio member, and so the
    # only anchor in it that answers to something outside the model.
    initial_gain = 0.000144868


class PanFluteProperties(StoppedPipeProperties):
    """GM 75. A CLOSED tube, and most of the breath missing it.

    The closed end is already right -- 75 was mapped to the stopped pipe, which
    is the one thing about this instrument the old mapping got correct, and it
    matters: a pipe closed at the bottom resonates at ODD multiples and overblows
    at the twelfth rather than the octave. What was missing is everything else.

    A PAN PIPE IS THE BREATHIEST INSTRUMENT IN THIS FAMILY, and it had no breath
    at all: StoppedPipeProperties ships sustain_jitter = 0, so GM 75 rendered as
    a clean odd-harmonic tone -- an organ's Gedackt rank, which is exactly what
    that class is for and is not a pan pipe. The player blows across the open top
    of a tube with no windway and no labium, so a large part of the jet never
    couples into the resonance and stays as turbulence. That noise is not a
    defect of the instrument; it is most of its sound.
    """
    # Broadens every partial into a band: the sustained-chiff mechanism, which
    # is what breath past an edge actually does to a spectrum.
    sustain_jitter = 0.55
    chiff_volume = 1.8
    chiff_min_valve_time = 0.018
    chiff_max_valve_time = 0.055

    # Odd-only is inherited and is the point. A wide, short tube: the series
    # falls away fast above the first few.
    tonal_dampening = 2.4
    max_harmonic = 24
    bore_corner_hz = 2200.0
    bore_order = 2.0

    initial_gain = 7.51211e-05          # against the measured flute, as above


class ShakuhachiProperties(OpenPipeProperties):
    """GM 77. An open tube, a knife edge, and the breath as the instrument.

    End-blown: the player blows across a sharply bevelled notch cut into the rim
    (the utaguchi) rather than into a duct or across a side hole. There is no
    windway, the bore is wide for its length, and the edge is deliberately
    severe -- so more of the breath stays as turbulence than in any other member
    of this family except the bottle.

    That is why a shakuhachi sounds the way it does, and it is a spectral fact
    rather than an effect: the breath broadens every partial into a band. The
    same mechanism the pan pipe uses, further.

    MERI AND KARI ARE NOT MODELLED. Tilting the head down across the utaguchi
    (meri) flattens the note by up to a semitone and darkens it; raising it
    (kari) does the reverse, and the technique is central to the repertoire --
    it is how the instrument plays the pitches its five holes do not give. It
    belongs on a controller rather than in the voice, for the same reason the
    recorder's pressure-sharpening does: it is a gesture the player makes, not a
    property of the note. Left for whoever wires a breath controller.
    """
    sustain_jitter = 0.62
    chiff_volume = 1.5
    chiff_min_valve_time = 0.020
    chiff_max_valve_time = 0.060

    # Wide bore, strong low end, and a rich series -- the notch is a hard edge
    # and drives the upper partials well even as the breath blurs them.
    tonal_dampening = 1.15
    max_harmonic = 40
    bore_corner_hz = 3400.0

    initial_gain = 6.68141e-05          # against the measured flute, as above


class WhistleProperties(VesselFluteProperties):
    """GM 78. A HUMAN whistle -- which is a Helmholtz resonator, not a pipe.

    This is a category correction, not a refinement. GM 78 sat on the open pipe
    with the flutes, and a whistled note is not produced by a standing wave in a
    tube at all: the mouth cavity is a vessel, the lips are its neck, and the air
    in that neck moves as a lump against the springiness of the cavity behind
    it. One resonance, tuned by changing the cavity's volume with the tongue --
    which is why whistling has no registers, no overblowing, and no fingering.

    And it is why a whistle is the closest thing to a pure sine tone a person
    can make: with no tube there is no harmonic series for the body to
    reinforce, so what little is there comes from the jet. It sits with the
    ocarina and the blown bottle, next to which General MIDI already put it.

    THE OTHER READING, stated because the name is ambiguous: GM 78 could be a
    tin or penny whistle, which IS a pipe and a fipple one. Against that -- the
    Roland SC-55 sound every file was written for is the human whistle; a tin
    whistle would duplicate the recorder two programs earlier, since both are
    duct flutes; and the specification puts 78 between the shakuhachi and the
    ocarina rather than with the flutes. If a tin whistle is wanted it is
    RecorderProperties with a wider bore, not this.
    """
    # Purer than the ocarina, which at least has a chamber with real walls and
    # finger holes breaking it up. A whistle is almost the fundamental alone.
    tonal_dampening = 5.2
    max_harmonic = 8
    bore_corner_hz = 1800.0
    bore_order = 2.0

    # Lips are a poor edge but a small one: some breath, far less than a bottle.
    sustain_jitter = 0.22
    chiff_volume = 0.55
    chiff_min_valve_time = 0.012
    chiff_max_valve_time = 0.040

    initial_gain = 0.000152137          # against the measured flute, as above


class AltoFluteProperties(OpenPipeProperties):
    """A flute part below B3 is an alto flute part. MEASURED: Iowa AltoFlute.mf,
    four registers, G3-G6.

    NARROW FIT, deliberately. The family measurement found no register law and
    near-identical spectral tilt across all three flutes, so what separates them
    is SIZE and not physics: only the radiation corner, the low cutoff and the
    harmonic ceiling are fitted, and the tilt is inherited from the concert
    flute. Turning six parameters loose on data that says the rest is shared is
    how a fit ends up describing its measurement instead of its instrument.

    The gain is small and honest -- concert class 6.62/5.75 dB, this 6.60/5.37 --
    which is what "they share their physics" predicts. It is here because it is
    the right instrument for G3-A#3, not because it rescues the numbers.
    """
    bore_corner_hz = 1947.7
    bell_cutoff_hz = 205.1
    bell_order = 3.635
    max_harmonic = 59


class BassFluteProperties(OpenPipeProperties):
    """Below G3 an alto flute runs out too. MEASURED: Iowa BassFlute.mf, three
    registers, C3-A#5.

    Same narrow fit as the alto, and it earns more: concert class 6.40/7.67 dB,
    this 5.54/5.27. A bigger tube radiates less top, which is the one thing the
    concert flute's corner cannot express when simply transposed down.
    """
    bore_corner_hz = 1156.9
    bell_cutoff_hz = 160.4
    bell_order = 3.135
    max_harmonic = 82

class CylindricalReedProperties(ReedOrganProperties):
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
    legato_attack_s = 0.012   # slurred rather than tongued: the reed keeps going, the fingering changes
    registerable = False


class ConicalReedProperties(FormantBody, CylindricalReedProperties):
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
    # FITTED across Bb3B3, C4B4 and C5B5: RMS 10.14 -> 4.55 dB.
    tonal_dampening = 1.6
    octave_dampening = 0.3
    # Trimmed +2.56 dB so the fit changes COLOUR and not LEVEL.
    initial_gain = (1.0 / 8050) * 1.3428
    # FORMANT, measured. The Iowa oboe at C4 peaks at its 5th harmonic, 1295 Hz,
    # 12.6 dB ABOVE the fundamental -- the oboe's characteristic resonance, and
    # the reason it cuts through an orchestra. The bassoon peaks at its 4th,
    # 524 Hz, 19.3 dB above. A conical reed is a resonator with a strong peak
    # well up the series, which is exactly what a 1/n^d rolloff cannot be.
    formants = ((1300.0, 700.0, 3.0), (3000.0, 1400.0, 0.6))
    formant_floor = 0.18
    bore_corner_hz = 5000.0
    bore_order = 1.6


class BassoonProperties(ConicalReedProperties):
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


class SaxophoneProperties(ConicalReedProperties):
    """A big conical reed. MEASURED now: Iowa SopSax.NoVib.mf (Ab3B3, C4B4,
    C5B5) and AltoSax.NoVib.mf (Db3B3, C4B4, C5Ab5).

    The asserted formant POSITIONS turned out well judged -- 900 and 2000 Hz
    guessed against real peaks at ~870 (+8.0 dB) and ~1850 (+4.4). What was wrong
    was the tilt, which ran 7-10 dB hot through h2-h12. Two features were also
    missing: a third resonance near 3100 (+5.1), and a DIP at 1200-1427 (-7.6)
    that a list of poles cannot make and an antiformant can.

    FITTED ON BOTH INSTRUMENTS TOGETHER, not on one and validated against the
    other. Fitting the soprano alone gave soprano 3.07 dB and alto 6.07; fitting
    both gives 3.78 and 4.77. One class covers programs 64-67, so the compromise
    that serves the family beats the fit that serves one member -- and the corpus
    only plays the soprano (1121 notes, one file), so 65-67 would otherwise have
    inherited a soprano wholesale.
    """
    formants = ((870.0, 400.0, 1.0), (1850.0, 700.0, 0.6), (3100.0, 900.0, 0.1))
    antiformants = ((1300.0, 400.0, 0.3),)
    tonal_dampening = 1.40
    octave_dampening = 0.00
    formant_floor = 0.65
    bore_corner_hz = 5500.0
    bore_order = 2.6
    # Its own gain, as a LITERAL rather than a reference to
    # ConicalReedProperties.initial_gain: this class is defined after that one, so
    # a reference picks up the oboe's trim and hands the saxophone a rise it
    # never asked for. (It did, 2.56 dB of it, the first time.)
    # ...trimmed +2.21 dB, the energy the fit moved, so this changes COLOUR and
    # not LEVEL.
    initial_gain = 1.24224e-04 * 1.2891

class ClarinetProperties(CylindricalReedProperties):
    """A cylindrical bore stopped by the reed: the one orchestral wind whose
    odd harmonics really do dominate -- but only in the low register.

    MEASURED across the whole Iowa clarinet FAMILY: Bb, Eb and bass, four
    registers each, 133 notes from concert C#2 to B6. The noise floor comes from
    Iowa's own `ambient.silence` recordings, not from the analysis window.

    THE OLD MODEL'S DEFECT WAS REAL AND THIS IS THE FIX. A single
    even_harmonic_db cannot describe a clarinet, and the docstring here used to
    say so and stop there. Measuring the even-minus-odd balance directly:

        below C3   -25.3 dB        C5-C6      +4.5 dB
        C3-C4      -14.9           above C6   +8.1
        C4-C5       -5.9           +8.33 dB per octave

    A 33 dB swing that CHANGES SIGN -- above C5 the evens are stronger than the
    odds. The old constant -8.0 dB is right only around C4-C5, and it left the
    model +14.8 dB out at the bottom and -11.1 dB out at the top: a 26 dB
    sign-reversing error that no constant could have removed.

    The physics is that a stopped cylinder is only stopped while the tonehole
    lattice below the first open hole is long enough to act like one. Play
    higher, the lattice is wide open, the bore stops behaving like a closed pipe,
    and the evens come back. So the suppression belongs on a per-octave slope --
    see even_harmonic_db_per_octave on SynthProperties.

    IT TRACKS ABSOLUTE FREQUENCY, NOT EACH INSTRUMENT'S OWN REGISTER BREAK, and
    that is the one thing a single instrument could not have shown: the bass
    clarinet crosses zero at the same concert pitch as the Bb (~480 Hz) rather
    than an octave lower, where its own chalumeau/clarion break sits.

    FITTED ON THE Bb ALONE, because GM 71 is a Bb clarinet and a measured fit
    must not let other instruments redefine it -- the Bb spans 3.3 octaves and
    four registers by itself. The Eb and bass were HELD OUT ENTIRELY, and are
    the evidence that this is physics rather than a curve fit:

                              shape      HF   even/odd
        Bb          before     8.55   13.45      9.21
        Bb          after      8.45    4.16      5.10
        Eb + bass   before     8.54   22.09     10.06     <- never seen
        Eb + bass   after      9.65   10.70      5.16

    Both quantities the fit targets roughly HALVE on two instruments it never
    saw. The register error is now within +/-2.4 dB everywhere, against the old
    +14.8 to -11.1. Aggregate shape drifts 1.1 dB on the held-out pair, which is
    expected: the bore and its cutoff were tuned to the Bb, and a bass clarinet
    is a bigger instrument.

    The even/odd balance is in the OBJECTIVE explicitly. A first attempt left it
    to an aggregate shape RMS, which barely feels it: that fit flattened the
    slope correctly and then sat 6 dB biased, fixing the register error and
    replacing it with a uniform one. If a quantity is the point of the fit, it
    has to be in the objective -- the same lesson the guitar's top end taught.
    """
    # CC71-78: and the clarinet has a measured effort-to-colour law, +0.13 dB
    # of tilt per dB.
    sound_controls = ReedOrganProperties.sound_controls | frozenset(('brightness',))
    # EFFORT. Measured the same way as the brass, and the answer is the
    # difference every player knows: +0.13 dB of flattening per dB of level
    # against a trombone's +0.68. A clarinet is famously stable in colour across
    # its dynamic range; it gets louder far more than it gets brighter. Set here
    # rather than on CylindricalReedProperties because this is where it was
    # measured -- the saxophones and double reeds keep the 0.0 default until
    # someone measures them.
    effort_tilt = 0.13
    even_harmonic_db = -7.161
    even_harmonic_db_per_octave = 6.794
    tonal_dampening = 1.386       # fitted
    octave_dampening = 0.1078
    bore_corner_hz = 859.1        # it had NO lowpass at all, hence the bright top
    bore_order = 1.002
    # The bore stops radiating below its own lowest resonance, as the guitar box
    # does; without it the model kept a fundamental the instrument does not.
    bell_cutoff_hz = 269.2
    bell_order = 2.767
    # h32 was only 2.6 kHz on the bass clarinet's bottom notes, where the
    # recording carries 39 harmonics clear of the floor.
    max_harmonic = 64
    # Trimmed so the fit changes COLOUR and not LEVEL: +1.00 dB from the first
    # fit, then -0.30 dB more when the register law moved this voice's energy.
    initial_gain = (1.0 / 6400) * 1.0841



class BassClarinetProperties(ClarinetProperties):
    """The instrument that actually plays a clarinet part below D3.

    MEASURED: Iowa BassClarinet.mf, four registers, C#2-A#5, 43 notes.

    Routed from SOLO_SPLIT[71] below D3, the Bb clarinet's lowest sounding note.
    A Bb clarinet cannot play below it at all, and the collection writes down to
    MIDI 24 -- two octaves under the instrument the patch names. Those notes were
    a Bb clarinet extrapolated into a register it does not have.

    It earns its own class: judged on the Iowa bass clarinet, the shipped Bb
    class scores shape 11.27 / HF 16.37 dB, this scores 9.95 / 3.72.

    THE REGISTER LAW HOLDS ON A SECOND INSTRUMENT. Fitted independently, this
    wants even_harmonic_db_per_octave = 7.331 against the Bb clarinet's 6.794 --
    and that is the strongest evidence yet that the law is physics rather than a
    curve through one instrument's data.

    max_harmonic 128 by the bass trombone's argument: at its lowest note 64
    harmonics stop at 4.4 kHz (HF 10.66 dB) where 128 reaches 8.9 kHz (3.72),
    and 192 is no better.
    """
    even_harmonic_db = -6.261
    even_harmonic_db_per_octave = 7.331
    tonal_dampening = 0.975
    octave_dampening = 0.0438
    bore_corner_hz = 2719.3
    bore_order = 1.935
    bell_cutoff_hz = 398.8
    bell_order = 1.719
    max_harmonic = 128

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
    # RE-BALANCED after the string family was raised 4.3 dB. These three carry
    # their own absolute gains rather than deriving from the bowed base, so they
    # did NOT ride that change and the choir silently dropped 4.3 dB relative to
    # the orchestra it sings with -- the one family that lost ground. Re-measured
    # register-averaged (five pitches, C3-C5) rather than at a single note, which
    # also caught the vowels drifting 5 dB apart from each other: "oo" sat 1.7
    # under the strings while the synth voice sat 3.3 over. All three now land on
    # the string reference, as the equal-velocity convention asks.

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




# Named voice parts, as multipliers on the ensemble-average vocal tract.
# Registration beats inference: a COUNTERTENOR sings the alto line on a male
# tract, and no rule based on pitch can ever get that right -- nor a contralto,
# nor a boys' choir, where a treble is a child and his tract is shorter than a
# woman's, not longer. So when a part says what it is, believe it; the
# tessitura rule below is only for when it does not.
VOICE_BODIES = {
    'bass':         0.92,
    'basso':        0.92,
    'baritone':     0.94,
    'tenor':        0.97,
    'tenore':       0.97,   # the Italian, as LilyPond and Italian scores write it
    'countertenor': 0.98,   # male tract, alto range: the case inference cannot do
    'contralto':    1.03,
    'alto':         1.05,
    'mezzo':        1.07,
    'soprano':      1.09,
    'sopran':       1.09,
    'treble':       1.20,   # a boy, not a woman: shorter tract, higher formants
    'boy':          1.20,
    # A CASTRATO IS THE CASE THAT PROVES THE POINT. Castration before puberty
    # leaves the larynx a boy's -- so the range is soprano or alto -- while the
    # rest of the body grows on, and grows LONG, because the growth plates never
    # close. A boy's folds in an unusually large man's tract. Singing the very
    # note a soprano sings, his formants sit BELOW hers, not above. Nothing
    # inferred from pitch can produce that; only a declaration can.
    'castrato':     0.90,
    'sopranist':    0.95,   # a modern male alto/soprano: adult tract, falsetto
}


# Names that contain a part name but are not a voice at all. "Bassoon" is not
# a bass, and neither is a double bass, a bass drum or a bass guitar -- matching
# on substrings turns all four into singers.
_NOT_A_VOICE = ('bassoon', 'contrabass', 'double bass', "d'bass", 'dbass',
                'bass drum', 'bass gtr', 'bass guitar', 'bassi', 'string')


def voice_body(name):
    """The named voice part in a track label, or None.

    Tokenised rather than substring-matched, so "bassoon" does not read as a
    bass. The final authority is still the voice CLASS: this is only consulted
    for a part already being sung.
    """
    if not name:
        return None
    low = str(name).lower()
    if any(bad in low for bad in _NOT_A_VOICE):
        return None
    hit = None
    for word in _re.findall(r'[a-z]+', low):
        if word in VOICE_BODIES and (hit is None or len(word) > len(hit)):
            hit = word
    return hit


class _VocalBody:
    """Male and female bodies for the same vowel, and the draw between them.

    The vowel formants above are one averaged singer. But a formant is a tract
    resonance, and an adult male tract is 17-18 cm against 14-15 for a female:
    formants scale INVERSELY with length, so the same vowel sits about 17%
    higher in a woman. Peterson & Barney's /a/ is F1 730 / F2 1090 for men and
    850 / 1220 for women -- a soprano and a bass singing "ah" do not share
    formants, they share a vowel.

    The split is symmetric about the existing values (each body moves by
    sqrt(ratio), not one by the whole of it) so the geometric mean is unchanged
    and the measured initial_gain calibration still holds.

    Pitch is the only clue MIDI gives us about who is singing. Below ~G3 it is
    men, above ~A4 women, and in between either -- so this DRAWS from a smooth
    probability rather than switching at a boundary, seeded on the note so a
    given pitch is always sung by the same person.
    """
    # TUNING_VOCAL_BODIES=0 collapses the split back to one averaged singer,
    # so the change can be A/B'd against the old behaviour.
    tract_ratio = 1.17 if os.environ.get('TUNING_VOCAL_BODIES', '1') != '0' else 0.0
    tract_sigma = 0.015         # individual tracts vary within each sex
    mixture_broadening = 0.9    # extra bandwidth where both sexes sing
    voice_crossover_hz = 294.0  # ~D4: the boundary sits between alto and tenor
    voice_crossover_oct = 0.20  # sharp: the key is a stable part tessitura,
                                # not a per-note pitch, so nothing can flip
    # The singer's formant (~2.8-3 kHz) is a trained MALE phenomenon; sopranos
    # have far less of it, so the top resonance is not shared either -- but only
    # when the top resonance IS one. "Oo" puts its third formant at 2240 Hz,
    # below the cluster, and attenuating that is just making the vowel duller.
    female_top_formant = 0.55
    singers_formant_hz = 2600.0

    # TUNING_VOCAL_FLAT=1 renders the SOURCE only -- the glottal buzz with its
    # pitch, vibrato, section spread and mouth radiation, and no tract at all --
    # so vocaltract.py can apply the formants as a filter that MOVES. Formants
    # baked into a note are formants that jump, and a tract cannot jump.
    vocal_flat = os.environ.get('TUNING_VOCAL_FLAT', '0') == '1'

    def _sung_formants(self, frequency, part=None, base=None):
        if self.vocal_flat:
            self.formant_floor = 1.0
            return ()
        # base overrides the class vowel, so a sung TEXT can choose it
        base = base if base is not None else type(self).formants
        if not base or not self.tract_ratio:
            return base
        if part:
            # Declared. No crossover, no draw, no broadening: we were told.
            ratio = VOICE_BODIES[part]
            out = []
            for i, (centre, bandwidth, amp) in enumerate(base):
                a = amp * (self.female_top_formant
                           if (ratio > 1.0 and i == len(base) - 1
                               and centre * ratio >= self.singers_formant_hz)
                           else 1.0)
                out.append((centre * ratio, bandwidth * ratio, a))
            return tuple(self._formant_tune(out, float(frequency) or 1.0))
        f = float(frequency) or 1.0
        midi = int(round(69 + 12 * _log(f / 440.0) / _log(2)))
        # How female this pitch is. NOT a coin flip per note: a tenor is a man
        # for the whole piece, and drawing per pitch would flip the body from
        # note to note inside one line, which is worse than either answer.
        x = (_log(f / self.voice_crossover_hz) / _log(2)) / self.voice_crossover_oct
        w = 1.0 / (1.0 + _exp(-max(-40.0, min(40.0, x))))
        half = self.tract_ratio ** 0.5          # symmetric about the mean body
        ratio = half ** (2.0 * w - 1.0)         # 1/half at w=0, half at w=1
        rng = _random.Random(0x5117 + midi * 2654435761)
        ratio *= _exp(rng.gauss(0.0, self.tract_sigma))
        # In the overlap BOTH sexes are singing the note, on tracts a whole
        # 17% apart. That is not one resonance in the middle, it is two close
        # together -- which a single wider, flatter formant approximates far
        # better than a narrow one at the average. Widest where the mixture is
        # most even, and back to normal at either end of the range.
        blend = 1.0 + self.mixture_broadening * 4.0 * w * (1.0 - w)
        out = []
        for i, (centre, bandwidth, amp) in enumerate(base):
            a = amp
            if i == len(base) - 1 and centre * ratio >= self.singers_formant_hz:
                a *= (1.0 - w) + w * self.female_top_formant
            out.append((centre * ratio, bandwidth * ratio * blend, a))
        # FORMANT TUNING. A soprano above about G5 sings a fundamental higher
        # than her own F1 and would be filtering out her loudest partial, so she
        # raises F1 onto it. "Fixed formants" is true of speech and stops being
        # true at the top of the female range.
        out = self._formant_tune(out, f)
        return tuple(out)

    @staticmethod
    def _formant_tune(out, f):
        """A singer whose fundamental has risen above her own F1 raises F1 onto
        it rather than filtering out her loudest partial.

        She does it by OPENING the vowel, though, and that has a limit she
        cannot pass: F1 must stay below F2. Unbounded, a dark vowel breaks --
        "oo" has F1 at 300 Hz, so the rule fires from G4 upward and by C6 put
        F1 (1047) above F2 (948), which is not a vocal tract at all. Bounded,
        the vowel migrates toward open, which is what actually happens: nobody
        sings a true "oo" at the top of the staff.
        """
        if not out or f <= out[0][0]:
            return out
        c, bw, a = out[0]
        ceiling = out[1][0] * 0.8 if len(out) > 1 else f
        new = min(f, ceiling)
        if new > c:
            out[0] = (new, bw * (new / c) ** 0.5, a)
        return out

    def __init__(self, frequency=256.0, *args, **kwargs):
        super().__init__(frequency, *args, **kwargs)
        self.formants = self._sung_formants(frequency)


class ChoirAahsProperties(_VocalBody, VocalProperties):
    """GM 52. An open "ah": the first formant high and the tract wide open."""
    # BALANCE, per vowel: the formant filter is power-normalised, but the vowels
    # still land differently because they weight the source's harmonics
    # differently -- "oo" throws away everything above its low F2. Measured
    # K-weighted at velocity 100 like the rest of the set and brought to the
    # orchestra's level. /sqrt(players) as for any section.
    initial_gain = (1.0 / 6875 / (VocalProperties.section_players ** 0.5)) * 1.1521   # +1.23 dB, see VocalProperties


class VoiceOohsProperties(_VocalBody, VocalProperties):
    """GM 53. A rounded "oo": lips narrowed, so F1 and F2 drop a long way and
    the vowel goes dark. The single biggest audible difference between vowels
    is F2, and it moves by more than an octave between these two."""
    formants = ((300.0, 90.0, 1.00), (870.0, 100.0, 0.42), (2240.0, 140.0, 0.12))
    bore_corner_hz = 3000.0
    initial_gain = (1.0 / 6127 / (VocalProperties.section_players ** 0.5)) * 1.2134   # +1.68 dB, see VocalProperties


class SynthVoiceProperties(VocalProperties):
    # no male/female split: the thing being imitated is a synthesizer, which
    # has one body and no anatomy
    """GM 54. A synthesized voice: an "eh" between the other two, and steadier
    than people are -- less spread, less vibrato, because the thing being
    imitated is a synthesizer imitating a choir."""
    formants = ((530.0, 110.0, 1.00), (1840.0, 110.0, 0.55), (2480.0, 140.0, 0.25))
    section_spread_cents = 4.0
    section_vibrato_cents = 3.0
    initial_gain = (1.0 / 4542 / (VocalProperties.section_players ** 0.5)) * 0.6823   # -3.32 dB, see VocalProperties


# --- Sound effects (GM 120-127) --------------------------------------------
# The whole effects bank fell through to MalletProperties, a struck bar, so a
# gunshot rang as a tuned bell. These are not pitched instruments at all: they
# are bands of noise, built the way the percussion voices build theirs -- hard
# inharmonicity to scatter the partials off the harmonic grid, a near-flat
# tonal_dampening so no mode stands out of the wash, and a wide running phase
# jitter (the chiff mechanism) to smear what is left into continuous noise.

class ConsonantProperties(FormantBody, NoisyPercussionMixin, StoppedPipeProperties):
    """One consonant, as its own brief band of noise.

    Riding the vowel's own partials could never work: the chiff makes noise by
    scattering the phase of partials that are ALREADY THERE, and a voice has
    essentially nothing where a consonant lives -- the glottal source falls
    11 dB/octave and the mouth stops radiating at 4 kHz, so the body gain at
    6 kHz is -35 dB. You cannot make an /s/ out of harmonics that are absent.

    So a consonant gets a source of its own, built the way the noise percussion
    is: a hard inharmonicity that scatters the partials off the harmonic grid so
    no mode stands out, a near-flat rolloff so the band is filled rather than
    tilted, and a wide running phase jitter to smear what is left into a
    continuum. A single formant then carves out the band the constriction makes
    -- which is the whole difference between /s/, /S/ and /f/ -- and the note's
    own length is the burst.

    Its base frequency is deliberately low and unrelated to the sung pitch: it
    only sets how DENSE the partials are, and a consonant needs them dense
    enough to fill a band, not tuned to anything.
    """
    odd_only = False
    # A SMALL inharmonicity, not a large one. The percussion voices scatter
    # their partials hard because they have modes to scatter; a consonant needs
    # the opposite -- partials packed CLOSE so the phase jitter can smear them
    # into a continuum. At the percussion value they ran away quadratically and
    # only two of them landed anywhere near the /s/ band, which is a whistle,
    # not a hiss. Dense spacing plus a banded wash is what makes noise.
    inharmonicity_coefficient = 0.0009
    tonal_dampening = 0.25                             # near flat: fill the band
    chiff_volume = 2.4
    chiff_cycle = 0.95
    # AND THE WASH MUST BE BANDED. Left white, every partial's noise spreads
    # flat to Nyquist, so the band the formant carved is thrown away again and
    # the body rolloff cannot catch it -- the noise is no longer AT the
    # frequencies being filtered. Kept near its own partial, the formant's band
    # survives into the wash, which is the entire point of choosing /s/ over /S/.
    chiff_bandwidth_hz = 2000
    decay_db = 0.0
    harmonic_decay_db = 0.0
    harmonic_decay_dampening = 0.0
    formants = ((4000.0, 1400.0, 1.0),)
    formant_floor = 0.008         # tight: outside the band there is nothing
    bore_corner_hz = 11000.0
    bore_order = 2.0
    # The wash runs flat to Nyquist if nothing stops it, and a mouth does not
    # radiate at 12 kHz -- unchecked it read as fizz rather than as friction,
    # +18 dB in a band where no consonant lives -- though the real cure for that
    # was banding the wash, not lowering these, which had merely muted /s/ too.
    hf_corner_hz = 10000.0
    hf_order = 2.0
    # A BURST MUST BE ABLE TO START AND THEN HOLD. Inherited, the attack was
    # chiff_max_valve_time -- 18 ms, longer than the 15 ms plosive it was
    # supposed to open -- so a /t/ never reached level at all, and
    # sustain_level 0 then took away what little it had. A consonant is not a
    # struck note that rings and dies; it is friction that lasts exactly as
    # long as the constriction does.
    attack_time = 0.002
    sustain_level = 1.0
    release_valve_time = 0.004
    initial_gain = 3.5217467864060575e-05 * 0.55

    def chiff_harmonic_gain(self, harmonic):
        """THE WASH MUST GET THE BAND, not merely a roll-off.

        By default this returns 1.0 at every harmonic, so the noise runs flat
        while only the tonal partials are shaped -- the same fault
        NoisyPercussionMixin records for the drums, where the wash was carrying
        nearly all the energy. For a consonant the noise IS the sound, so a
        flat wash throws away the band the formant just carved: the model put
        92% of an /s/ between 5 and 7.5 kHz and the render came back with a
        centroid of 1233 Hz, which is not a sibilant, it is a rustle.

        Weighting the chiff by the same body gain the partials get makes the
        noise land where the constriction is.
        """
        fn = self.frequency_x * (2.0 ** self.octave_position) * harmonic
        return self.bore_gain(fn) * self._hf_rolloff(harmonic)


class GuitarFretNoiseProperties(NoisyPercussionMixin, FormantBody,
                                PluckedStringProperties):
    """GM 120. A fingertip dragged along a wound string.

    NOT the same thing as GM 31, which is a guitar HARMONIC -- a finger resting
    on a node so that most of the string cannot speak. This is the noise
    between the notes: the squeak a hand makes shifting position, which on a
    real guitar track is most of what tells you a human is playing it.

    THE BAND IS FIXED, AND THAT IS THE WHOLE POINT. A round-wound string is a
    helix of wire, and a fingertip riding over the windings crosses a ridge
    every winding pitch -- so the squeak's frequency is slide speed divided by
    winding pitch, and has NOTHING to do with the note being fretted. With a
    wrap around 0.35 mm and a hand moving 0.25 to 1 m/s that is roughly 700 Hz
    to 3 kHz, wherever the left hand happens to be.

    The first version of this voice let the note set the band, on the argument
    that the note could stand in for hand speed. It cannot, and the reason is
    worth keeping: written into a guitar part the squeak then lands on a
    musical pitch, in the middle of the guitar's own register, and is heard as
    another note. Measured, 58% of its energy sat in 300-700 Hz. Ben, hearing
    it: "it just sounds like a regular guitar, not frets."

    So the band is a FORMANT -- the mechanism this codebase already has for
    resonances that stay put while the harmonics slide through them. Two
    octaves apart, this voice now puts 99% of its energy in the same
    700 Hz - 3 kHz either way, which is what "the pitch is the hand, not the
    fret" has to mean in practice.

    AND THE WASH HAD TO BE BANDED, NOT JUST TURNED DOWN. The chiff that makes
    this a scrape rather than a buzz defaults to spraying white noise from
    every partial regardless of where that partial sits, and shaping its LEVEL
    does not fix that: with the band on the partials and the level on the
    chiff, the partial table was 99.6% right and the RENDER still came back 72%
    above 6 kHz with a centroid near 11 kHz. Switching the wash off puts it
    back in band and turns it into a TONE -- periodicity 0.91, which is the
    "which is a beep" failure noisegen.py records for fricatives built out of
    partials. Only chiff_bandwidth gets both at once. The two failures sit on
    either side of it and neither is a matter of degree.

    THE GLIDE IS THE RECOGNISABLE PART, and it is already modelled -- as the
    piano's tension bloom, which has exactly the shape a position shift has: it
    starts displaced and settles exponentially, because a hand is fastest when
    it leaves and stops when it arrives. What the piano does not need is the
    RANGE; tension_bend was capped at 0.04 (68 cents) for it, and a slide
    sweeps most of an octave, which is what tension_bend_max is for. Velocity
    scales it, so a hard note is a long fast shift and a soft one a short one.

    ONLY WOUND STRINGS SQUEAK. The plain trebles have no helix to ride over, so
    octave_gain takes 9 dB an octave out as the part climbs into the register
    where the strings would be plain -- which is the same fact that makes fret
    noise a bass-string phenomenon on every recording.
    """
    # THE SQUEAK'S OWN BAND, independent of the note: slide speed over winding
    # pitch, not anything the left hand is doing. Wide, because a hand does not
    # move at one speed.
    formants = ((1700.0, 2000.0, 1.0),)
    formant_floor = 0.025          # almost nothing outside the band
    bore_corner_hz = 3500.0
    bore_order = 2.5
    bell_cutoff_hz = 650.0         # below this there is no ridge-crossing left
    bell_order = 2.5

    # A slide, not a bloom: most of an octave, settling in the tenth of a
    # second a position shift takes, and independent of register because it is
    # the hand's speed and not the string's tension.
    tension_bend = 0.45
    tension_bend_max = 0.80
    tension_bend_slope = 0.0
    tension_settle_time = 0.10
    tension_settle_cutoff = 0.6

    # Dense and strongly stretched, so the partials decorrelate into noise
    # rather than ringing as a chord -- the same trick the percussion and the
    # breath voices use, and the reason this is not simply a bright pluck.
    tonal_dampening = 0.35
    max_harmonic = 64
    # MODERATE, WHERE BREATH AND A GUNSHOT USE 45x, and the band is the reason.
    # harmonic_volume evaluates the body filter at f0*m, not at where the
    # partial actually lands once stiffness has stretched it -- so heavy
    # inharmonicity and a FORMANT are incompatible: at 45x a partial nominally
    # at 8.8 kHz sounds at 43, and the band gets applied to a frequency the
    # partial is nowhere near. Breath and a gunshot can use 45x precisely
    # because they want no band at all. Here the decorrelation comes mostly
    # from the wash, and this only has to roughen.
    inharmonicity_coefficient = (
        SynthProperties.inharmonicity_coefficient_2nd_harmonic * 3.0)
    inharmonicity_dynamic = False

    def chiff_harmonic_gain(self, harmonic):
        """THE WASH MUST GET THE BAND, not merely a roll-off.

        NoisyPercussionMixin gives the chiff `_hf_rolloff` and nothing else, so
        the noise ignores the formant entirely -- and for this voice the noise
        IS the sound, so a flat wash throws away the band that makes it a
        squeak. Measured: with the formant on the partials alone, the rendered
        voice still had 54-72% of its energy above 6 kHz and a centroid near
        10 kHz. That is a hiss with a squeak somewhere inside it.

        Exactly the fault the consonant voice above records for an /s/, and the
        same fix: weight the chiff by the same body gain the partials get, so
        the noise lands where the ridges are.
        """
        fn = self.frequency_x * (2.0 ** self.octave_position) * harmonic
        return self.bore_gain(fn) * self._hf_rolloff(harmonic)

    # A fingertip is soft and it bounces, so the ridge crossings are not
    # regular. The wash is what makes it a scrape rather than a buzz, and it
    # has to keep moving while the hand does.
    #
    # BANDED, WHICH IS THE WHOLE DIFFERENCE. The wash defaults to RAND_GRAN --
    # effectively unbounded, so each partial sprays white noise regardless of
    # where it sits. Shaping its LEVEL is not enough: with the band on the
    # partials and the level on the chiff, the partial table was 99.6% correct
    # and the RENDER still came back 72% above 6 kHz with a centroid near
    # 11 kHz, because the noise was being made everywhere. Measured against
    # chiff_volume 0, which is in band (99.6%) and a TONE (periodicity 0.91,
    # the "which is a beep" failure noisegen.py records for partial-built
    # fricatives). Banding the wash gets both: 84% in 700 Hz - 3 kHz and
    # periodicity 0.12-0.26. Wider (2.6) loses the band again, narrower (0.8)
    # goes tonal.
    chiff_bandwidth = 1.2
    chiff_volume = 1.8
    chiff_cycle = 0.90
    chiff_min_valve_time = 0.010
    chiff_max_valve_time = 0.030
    chiff_release = 0.5
    sustain_jitter = 1.0

    hf_corner_hz = 3800.0          # see above: the wash, not the partials
    hf_order = 2.0
    octave_gain = -9.0             # plain strings have no winding to ride over
    # LEVELLED BY EAR, AND THE PLACEMENT MATTERS MORE THAN THIS DOES. Written
    # on a low (wound) string at a hard shift, a squeak peaks about 21 dB under
    # the guitar beside it -- present as a hand moving, not as an effect. The
    # same squeak written up at G5 is 36 dB under, because a plain treble
    # string has no winding to ride over and this voice says so; that is the
    # model being right, not the level being wrong, and raising the gain to
    # bring a treble squeak up would put a bass one over the note.
    #
    # 1/2300 measured 14.6 dB under and Ben called it "a bit too loud", which
    # is the same judgement the recordings make: fret noise is evidence, not a
    # part. The level scales linearly, so this is the one knob to turn.
    initial_gain = 1.0 / 4600


class BreathNoiseProperties(NoisyPercussionMixin, StoppedPipeProperties):
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


class ApplauseProperties(BreathNoiseProperties):
    """GM 126. A room full of hands, which is noise but not surf.

    It had been a struck BAR, which is the same category error fret noise was:
    a mallet voice has a few sharp modes and a decay where this has neither.
    The noise family next door already had the machinery.

    Between its two neighbours, and closer to breath than to the sea. Surf
    swells in over a third of a second and is weighted low, because a wave is
    a large slow thing; a clap is a small fast one, and a thousand of them are
    still a thousand small fast ones. So the onset is quick and the weighting
    is brighter -- but not as flat as breath, because a hall full of people is
    a hall, and the room takes the very top off before anyone hears it.
    """
    tonal_dampening = 0.32         # brighter than surf (0.5), darker than breath
    hf_corner_hz = 5500.0
    chiff_min_valve_time = 0.02    # claps start; they do not swell
    chiff_max_valve_time = 0.06
    chiff_release = 0.5
    initial_gain = BreathNoiseProperties.initial_gain


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
            self.reg_state = self.sampler.reg_state_for(self.midi_channel, self.property_class)
            self._build_registered_partials()
            if self.max_fade is not None:
                for partial in self.partials:
                    partial.max_fade = self.max_fade
            return
        self.reg_state = None

        volume = 0.0
        transverse = []                       # (freq, raw gain, decay) for phantom-partial pairing
        # THE COUNT IS NOT nyquist/f0. That bound assumes partial m sits at m*f0,
        # which is the fifth place in this file to assume it (see harmonic_decay,
        # which counted four) and the only one that silently DROPS partials rather
        # than mis-placing them. With a measured mode set the ratios are not the
        # index: a closed hi-hat's 224 modes run to ratio 80, every one of them
        # under Nyquist, and 22050/248.4 stopped the loop at 87 -- 137 modes of a
        # cymbal thrown away. That is the strike. It is why this renderer played a
        # hi-hat as a flat wash where the block engine struck it, 20 dB apart over
        # the first 50 ms and in agreement after 80.
        #
        # The right bound is max_harmonic, exactly as blockrender uses, with the
        # per-partial guards below (mode_ratio <= 0, and frequency past Nyquist)
        # doing the cutting. For a harmonic voice they cut in the same place the
        # old bound did, so nothing else moves.
        max_partials = getattr(self.properties, 'max_harmonic', 64) or 64
        for harmonic in range(1, max_partials + 1):
            if self.properties.inharmonicity_dynamic:
                self.properties.inharmonicity_coefficient = self.properties.inharmonicity_coefficient_for_frequency(
                    frequency)

            hr = self.properties.mode_ratio(harmonic)
            if hr <= 0.0:
                break
            if self.properties.inharmonicity_coefficient > 0.0:
                harmonic_frequency = self.frequency * hr * (
                            1.0 + 0.5 * (hr ** 2 - 1) * self.properties.inharmonicity_coefficient)
            else:
                harmonic_frequency = self.frequency * hr

            if harmonic_frequency > self.nyquist:
                break

            harmonic_volume_raw = self.properties.harmonic_volume(harmonic)
            main_inc, main_delay = (self.seats[0] if self.seats
                                    else (getattr(self, 'incidence', 0.0), self.delay))
            # Radiation is a fact about the instrument and the air between it
            # and here, not about a head, so it applies whether or not the
            # binaural model does.
            harmonic_volume = harmonic_volume_raw * self.pan * self.properties.radiation_gain(harmonic_frequency)
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
            # EACH MODE'S SIGN, from where the stick landed relative to its nodes.
            # See SynthProperties.strike_phase_spread, whose own comment says why:
            # with three hundred partials, starting them all in phase means "they
            # all add at t=0 and the note gets a spike that is an artefact of the
            # synthesis, not of the plate". blockrender has flipped these since the
            # plates were rebuilt; this path never did, so a dense mode set summed
            # COHERENTLY here (224x) against INCOHERENTLY there (sqrt(224), 15x) --
            # 23 dB, and it showed up as +6.9 dB on a closed hi-hat once the mode
            # count was fixed. start_phase is in cycles, so a sign flip is 0.5.
            sps = self.properties.strike_phase_spread
            if sps > 0.0:
                main.start_phase += 0.5 * sps * (_strike_bit(self.frequency, harmonic))
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
                uvol = harmonic_volume_raw * self.pan * self.properties.radiation_gain(harmonic_frequency)
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
                                       gain * self.pan * self.properties.radiation_gain(f_ph),
                                       da + db_, self.delay, self.ref_count)
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
                    # WHERE PARTIAL m ACTUALLY SITS. This read `eff_ratio * m`, which
                    # assumes the rank's partials are a harmonic series -- true of every
                    # organ rank, and the reason it went unnoticed, but not of a
                    # registered voice built on a MEASURED mode set, whose partial m sits
                    # at mode_ratio(m). blockrender has always used the mode ratio here,
                    # so the two renderers silently disagreed for any such voice. Identity
                    # for a harmonic voice, so no existing render moves.
                    mr = self.properties.mode_ratio(m)
                    if mr <= 0.0:
                        break             # past the end of a measured mode set
                    h = eff_ratio * mr
                    stretch = (1.0 + 0.5 * (h * h - 1.0) * rank_B) if rank_B > 0.0 else 1.0
                    hf = f * h * stretch
                    if hf > self.nyquist:
                        break
                    hv = hv_fn(m)
                    if hv == 0.0:
                        continue
                    vol = hv * self.pan * props.radiation_gain(hf)
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

    def __init__(self, props=None):
        self.swell = 1.0
        # Seeded from the VOICE's own default registration, not from a literal
        # rank name: an organ's default_stops of 1 gives {"8": 1.0} exactly as
        # before, but a voice whose ranks are not called "8" -- an orchestra hit
        # is bass/tenor/string/... -- would otherwise start with every rank
        # gated off, since sum_values reads gate.get(rank, 0.0). That silenced
        # the whole voice on this path while the block renderer played it.
        ranks = getattr(props, 'stop_ranks', None) if props is not None else None
        if ranks:
            ds = getattr(props, 'default_stops', 1)
            self.gate = {r[0]: 1.0 for i, r in enumerate(ranks) if (ds >> i) & 1}
        else:
            self.gate = {"8": 1.0}


class SynthSampler(BaseSampler):
    def __init__(self, audio_channel=0, sample_rate=44100, sample_depth=16, sample_packing="h"):
        BaseSampler.__init__(self, sample_rate, sample_depth, sample_packing)
        self.audio_channel = audio_channel
        self.tones = {}
        # midi_channel -> RegState, created on demand. The MIDI layer's
        # per-sample stepper writes here; registerable tones read it.
        self.channel_state = {}

    def reg_state_for(self, midi_channel, props=None):
        st = self.channel_state.get(midi_channel)
        if st is None:
            st = RegState(props)
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


def sympathetic_partials(driver, responder, gain=None):
    """[(freq, amp)] that `responder` sounds when `driver` is struck.

    TWO WAYS A NOTE CAN RING WITHOUT BEING HIT, and they are different physics
    rather than two settings of one:

      COINCIDENCE. The responder is a separate oscillator coupled loosely to
      the driver -- a sitar's sympathetic strings through the bridge, a piano's
      undamped strings through the plate. It answers only where one of the
      driver's partials lands INSIDE one of its own modes, so a fifth rings and
      a major second does not. The Lorentzian below is that resonance, and its
      width comes from the mode's own decay, which the model already knows:
      a mode falling at R dB/s has a time constant 8.686/R and a half-power
      bandwidth 1/(pi*tau).

      CONTACT. The responder shares a BODY with the driver, so the strike sends
      a mechanical impulse through the material and kicks every note area at
      once. An impulse is broadband, so the responder rings at its own modes
      whatever interval it happens to sit at, and coincidence has nothing to do
      with it. A steelpan is one continuous sheet of steel; its note areas are
      not separate oscillators loosely coupled, they are regions of the same
      plate.

    Which of those a steelpan actually does is settled by measurement and not
    by argument -- see examples/steelpan_check.py, which compares both against
    the interval histogram of a real pan.
    """
    g = responder.sympathetic_gain if gain is None else gain
    if g <= 0.0:
        return []
    dpar = _voice_partials(driver)
    rpar = _voice_partials(responder)
    if not dpar or not rpar:
        return []
    out = []
    if responder.sympathetic_mode == 'contact':
        # Broadband kick: the responder's own spectrum, scaled. Nothing about
        # the driver's partials enters except how hard it was hit.
        drive = _sqrt(sum(a * a for _, a in dpar))
        if responder.sympathetic_falloff:
            df = driver.frequency_x * (2.0 ** driver.octave_position)
            rf = responder.frequency_x * (2.0 ** responder.octave_position)
            semis = 12.0 * _log(max(rf, 1e-9) / max(df, 1e-9)) / _log(2.0)
            drive *= 10.0 ** (-responder.sympathetic_falloff
                              * body_distance(semis, responder) / 20.0)
        for f, a in rpar:
            out.append((f, a * g * drive))
        return out
    # Coincidence: each responder mode is driven by whatever lands in it.
    #
    # THE COUPLING IS DIMENSIONLESS. The driver's partials are already in the
    # renderer's absolute amplitude units, and so are the responder's, so
    # multiplying them applies the instrument's gain TWICE -- which made an
    # exact octave coincidence come out at 0.00005 and vanish under any
    # sensible floor. Normalising by the driver's own strongest partial makes
    # `d` a coupling FRACTION: 1.0 means this responder mode sits exactly under
    # the driver's loudest partial, and the responder then rings at its own
    # natural amplitude times the gain.
    ref = max(a for _, a in dpar) or 1.0
    for j, (fj, aj) in enumerate(rpar, start=1):
        bw = _mode_bandwidth(responder, j)
        d = 0.0
        for fi, ai in dpar:
            x = (fi - fj) / max(bw, 1e-9)
            d += (ai / ref) / (1.0 + x * x)
        if d > 0.0:
            out.append((fj, aj * g * d))
    return out


def body_distance(semis, props):
    """How far apart two notes are ON THE INSTRUMENT, in steps.

    For a steelpan that is distance round the cycle of FIFTHS, because that is
    the order the note areas are hammered into the pan: seven semitones is ONE
    step and a semitone is five. Plus half a step per octave, since a tenor
    pan's inner ring is the octave above its outer one.
    """
    semis = int(round(semis))
    pc = semis % 12
    # 7k = pc (mod 12); 7 is coprime with 12 so every pitch class is reachable.
    k = min((abs(j) for j in range(-6, 7) if (7 * j) % 12 == pc), default=6)
    octs = abs(semis - (semis % 12 if semis >= 0 else -((-semis) % 12))) / 12.0
    return k + getattr(props, 'sympathetic_octave_step', 0.5) * abs(semis) / 12.0


def _voice_partials(p, top=24):
    """(freq, amp) for one voice, as the renderer would build it."""
    f0 = p.frequency_x * (2.0 ** p.octave_position)
    out = []
    for h in range(1, min(top, p.max_harmonic or top) + 1):
        v = p.harmonic_volume(h)
        if v <= 0.0:
            continue
        f = f0 * p.mode_ratio(h)
        if f <= 0.0 or f > 20000.0:
            continue
        out.append((f, v))
    return out


def _mode_bandwidth(p, harmonic):
    """Half-power bandwidth of one mode, in Hz, from how fast it rings down.

    A mode falling at R dB/s has amplitude e^(-t/tau) with tau = 8.686/R, and
    a Lorentzian of half-power half-width 1/(2*pi*tau). Steel rings for a long
    time, so these are NARROW -- a steelpan mode at 260 Hz decaying at
    6.2 dB/s is 0.11 Hz wide, a Q above two thousand. That sharpness is the
    whole reason coincidence and contact give different answers.
    """
    r = max(p.harmonic_decay(harmonic), 1e-6)
    tau = 8.685889638 / r
    return 1.0 / (2.0 * _pi * tau)


# ---------------------------------------------------------------- room presets
#
# The hall above is the default because the corpus is orchestral. An organ is
# not in a hall: it is in a stone building four times the volume with a tenth
# the absorption, and the difference is not a reverb setting but the room the
# reflections and the tail are both computed from. TUNING_ROOM=church selects it.
# Captured before any preset is applied, so 'hall' can restore them. An empty
# dict meaning "the class defaults" is only true until something overwrites
# them, and these ARE class attributes -- selecting chamber and then hall left
# the hall 461 m3 with a 102 Hz Schroeder frequency.
_ROOM_DEFAULTS = {k: getattr(SynthProperties, k) for k in (
    'room_left', 'room_right', 'room_front', 'room_back',
    'room_ceiling', 'room_floor', 'radiation_distance',
    'SURFACE_ALPHA', 'SURFACE_SCATTER')}

ROOM_PRESETS = {
    'hall': _ROOM_DEFAULTS,           # the orchestral default, restorable
    # Bach's church, not a cathedral. The Thomaskirche is a HALL church --
    # about 18000 m3, stuffed with timber galleries, a wooden roof, box pews and
    # a congregation -- and it reverberates for something like two seconds
    # occupied. A French cathedral at six or seven seconds is a different
    # building, and playing Bach in one is a modern habit rather than his.
    #
    # Note what does NOT dry a church: its decoration. Ornament, columns and
    # tracery SCATTER, which softens the early reflections and is already
    # modelled below, but scattered energy stays in the room and the
    # reverberation time barely moves. Wood, pews and people are what absorb.
    # A salon: where modes actually live. Schroeder lands near 90 Hz here, so
    # the bottom two octaves of a harpsichord or a chamber organ sit inside the
    # modal region and the room's own resonances colour them -- which is the
    # whole reason a small room sounds like a place and a hall sounds like air.
    'chamber': dict(
        room_left=4.0, room_right=4.0,
        room_front=3.0, room_back=9.0,
        room_ceiling=3.6, room_floor=1.2,
        # 2 m, and the room FURNISHED. The first version had bare plaster over
        # a bare floor, which gave a 461 m3 salon a 1.21 s reverberation and a
        # critical distance of 1.15 m -- so a listener at 2.5 m sat more than
        # twice beyond it and heard mostly room. A room with a harpsichord in it
        # has rugs, hangings, bookcases and furniture, and those take the
        # critical distance out to where a player actually sits.
        # r_c 1.45 m; 1.03 m puts the room 3 dB under the direct sound.
        # A seat is 2.0 m (+2.8 dB) -- TUNING_DISTANCE=2 for that.
        radiation_distance=1.03,
        SURFACE_ALPHA={
            'left':    (0.25, 0.22, 0.20, 0.18, 0.18, 0.18),   # hangings, shelves
            'right':   (0.25, 0.22, 0.20, 0.18, 0.18, 0.18),
            'front':   (0.25, 0.22, 0.20, 0.18, 0.18, 0.18),
            'back':    (0.30, 0.26, 0.24, 0.22, 0.22, 0.22),
            'ceiling': (0.20, 0.18, 0.15, 0.14, 0.14, 0.14),   # plaster
            'floor':   (0.15, 0.20, 0.30, 0.40, 0.45, 0.45),   # boards and rugs
        },
        SURFACE_SCATTER={
            'left':    (0.10, 0.15, 0.25, 0.35, 0.45, 0.50),
            'right':   (0.10, 0.15, 0.25, 0.35, 0.45, 0.50),
            'front':   (0.10, 0.15, 0.25, 0.35, 0.45, 0.50),
            'back':    (0.15, 0.20, 0.30, 0.40, 0.50, 0.55),
            'ceiling': (0.10, 0.15, 0.25, 0.35, 0.45, 0.50),
            'floor':   (0.20, 0.25, 0.35, 0.45, 0.50, 0.55),
        },
    ),
    # The Pieta: a Venetian ospedale chapel, which is what Vivaldi's Op. 8 was
    # written for and played in by the girls of the orphanage. Between the salon
    # and Bach's Leipzig in every dimension -- masonry and plaster, but small,
    # and full of people, who are most of its absorption. A baroque concerto
    # wants a room short enough not to smear its passagework and live enough to
    # bloom, and neither the hall (built for a Beethoven orchestra) nor the
    # church (three times the volume) is it.
    'chapel': dict(
        room_left=7.5, room_right=7.5,
        room_front=9.0, room_back=21.0,
        room_ceiling=10.8, room_floor=1.2,
        # 5 m, not 7. Critical distance here is 3.3 m and an audience in a small
        # chapel sits close to the players; at 7 m it was +6.5 dB and I have
        # built every room in this session too wet by putting the listener too
        # far back. Baroque passagework wants the room present, not dominant.
        # r_c 3.28 m; 2.32 m puts the room 3 dB under the direct sound.
        # A seat is 5.0 m (+3.7 dB) -- TUNING_DISTANCE=5 for that.
        radiation_distance=2.32,
        SURFACE_ALPHA={
            'left':    (0.10, 0.09, 0.08, 0.08, 0.09, 0.10),   # plaster on masonry
            'right':   (0.10, 0.09, 0.08, 0.08, 0.09, 0.10),
            'front':   (0.10, 0.09, 0.08, 0.08, 0.09, 0.10),
            'back':    (0.14, 0.12, 0.11, 0.11, 0.12, 0.13),
            'ceiling': (0.12, 0.10, 0.09, 0.09, 0.10, 0.11),
            'floor':   (0.35, 0.50, 0.65, 0.72, 0.74, 0.72),   # a congregation
        },
        SURFACE_SCATTER={
            'left':    (0.15, 0.25, 0.40, 0.55, 0.65, 0.70),
            'right':   (0.15, 0.25, 0.40, 0.55, 0.65, 0.70),
            'front':   (0.10, 0.20, 0.30, 0.40, 0.50, 0.55),
            'back':    (0.20, 0.30, 0.45, 0.55, 0.65, 0.70),
            'ceiling': (0.15, 0.25, 0.40, 0.55, 0.65, 0.70),
            'floor':   (0.35, 0.45, 0.55, 0.65, 0.70, 0.70),
        },
    ),
    'church': dict(
        room_left=11.0, room_right=11.0,
        room_front=12.0, room_back=38.0,     # organ gallery ahead, nave behind
        room_ceiling=15.8, room_floor=1.2,
        # r_c 5.86 m; 4.15 m puts the room 3 dB under the direct sound.
        # A seat is 8.0 m (+2.7 dB) -- TUNING_DISTANCE=8 for that.
        radiation_distance=4.15,
        # THE SHAPE MATTERS AS MUCH AS THE DEPTH. Flat absorption across
        # frequency is the signature of masonry: brick and concrete take about
        # equally little everywhere, so they ring in the bass and reflect the top
        # hard, and a room built of them sounds like one however much you
        # increase the numbers. Timber does the opposite. A panel on an airspace
        # is a membrane, resonating and absorbing where its own compliance is --
        # 0.30 at 125 Hz falling to 0.10 by 4 kHz -- and lath-and-plaster is the
        # same kind of thing. That downward tilt is what a wooden room IS.
        SURFACE_ALPHA={
            'left':    (0.28, 0.20, 0.15, 0.12, 0.11, 0.10),   # timber galleries
            'right':   (0.28, 0.20, 0.15, 0.12, 0.11, 0.10),
            'front':   (0.20, 0.15, 0.12, 0.10, 0.10, 0.10),   # plaster and the case
            'back':    (0.28, 0.20, 0.15, 0.12, 0.11, 0.10),
            'ceiling': (0.30, 0.25, 0.20, 0.17, 0.15, 0.12),   # timber roof
            'floor':   (0.35, 0.50, 0.62, 0.70, 0.72, 0.70),   # pews and congregation
        },
        SURFACE_SCATTER={
            'left':    (0.15, 0.25, 0.40, 0.55, 0.65, 0.70),
            'right':   (0.15, 0.25, 0.40, 0.55, 0.65, 0.70),
            'front':   (0.10, 0.20, 0.30, 0.40, 0.50, 0.55),
            'back':    (0.15, 0.25, 0.40, 0.55, 0.65, 0.70),
            'ceiling': (0.20, 0.30, 0.45, 0.55, 0.65, 0.70),
            # The roughest surface in the building by far -- pews, hymnals,
            # heads, shoulders -- and the one whose reflection arrives soonest
            # and colours worst. At 1 ms it does not echo, it combs, and it put
            # a null at 487 Hz in the middle of the organ.
            'floor':   (0.55, 0.65, 0.75, 0.82, 0.85, 0.85),
        },
    ),
}


def critical_distance(props=None, q=1.0):
    """Where the direct sound and the reverberant field carry equal energy.

    Direct sound falls with the inverse square; the reverberant field does not
    fall off at all, being the accumulated arrivals of thousands of reflections
    from every direction. So their RATIO is what distance changes, and this is
    where it passes unity: inside it you hear the instrument, outside it you
    hear the room.
    """
    from math import exp, log, sqrt, pi
    p = props or SynthProperties
    w = p.room_left + p.room_right
    d = p.room_front + p.room_back
    h = p.room_ceiling + p.room_floor
    areas = {'floor': w * d, 'ceiling': w * d, 'left': d * h,
             'right': d * h, 'front': w * h, 'back': w * h}
    surface = sum(areas.values())
    # SynthProperties is not directly constructible; any concrete voice carries
    # the same room tables, since they are class attributes on the base.
    inst = p if not isinstance(p, type) else StoppedPipeProperties(261.6, 0, 1, 1)
    absorbed = sum(a * inst._octave_interp(inst.SURFACE_ALPHA[s], 500.0)
                   for s, a in areas.items())
    mean = absorbed / surface
    R = surface * mean / max(1e-6, 1.0 - mean)
    return sqrt(q * R / (16.0 * pi))


def set_wetness(target_db, q=1.0):
    """Place the listener so the reverberant field sits target_db against the
    direct sound, and return the distance.

    Ben's measurement, from the scale-space tools in ../recept: two sounds
    interfere harmonically to first order only while they are within about 3 dB
    of each other. So a reverberant field 3 dB BELOW the direct sound is plainly
    audible as space and yet does not enter the harmony -- it colours the room
    without muddying the chords. That makes -3 dB a criterion rather than a
    preference, and it is a far better thing to ask for than a distance, since
    the distance that achieves it differs in every room.

    Every room default in this file was built about 6 dB wetter than that.
    """
    from math import sqrt
    rc = critical_distance(q=q)
    dist = rc * (10.0 ** (target_db / 20.0))
    SynthProperties.radiation_distance = dist
    return dist


# ROOM STAGGER: no two surfaces the same distance away.
#
# A shoebox is laterally symmetric and a player stands near its centre line, so
# the left and right walls are equidistant and their images arrive together.
# Every preset above does that, and the hall does it three times over, because
# room_left, room_right and room_ceiling were all written as 12 m -- three
# different surfaces returning within 0.66 ms of each other and summing
# COHERENTLY. Three -19 dB copies become one -14 dB arrival: +9.5 dB over any
# one of them, energy the room never actually sent.
#
# Measured on the solo violin in the hall, that cost two audible things. In the
# frequency domain the six reflections combed the musical band with a PERIODIC
# 34 Hz ripple (autocorrelation 0.83 over 80-2000 Hz, 17.3 dB peak to trough),
# which is heard as a hollow boom -- a regular ripple reads as coloration where
# an irregular one of the same depth reads as neutral. In the time domain the
# tripled arrival landed 60 ms after every note, past the ~50 ms fusion limit,
# so a fast passage got a discrete echo of each note in the gap before the next
# one: the click.
#
# The coincidence is an artefact of the idealisation, not a fact about halls.
# A real wall is not a plane at a round number of metres -- it has relief,
# boxes, splay, an organ case -- so its specular return comes off an irregular
# surface spread over a range of path lengths, and no two surfaces in a real
# room agree to the centimetre. Offsetting the image planes is the standard
# repair for this in image-source models, and that is all this is. It is NOT a
# claim that halls are asymmetric.
#
# Deterministic and seeded on the room name, so a render is reproducible, and
# renormalised to preserve the VOLUME exactly -- so T60, the Schroeder
# frequency, the room constant, the critical distance and hence the -3 dB
# wetness target all stay precisely what the preset asked for. Rather than
# trust one draw, it keeps the draw that best separates the arrivals, which is
# the quantity that actually matters.
#
# The FLOOR is left alone. 1.2 m is ear height above the floor, a measurement
# rather than a round number, and its 2 ms bounce is the cue that tells you
# there is a floor under the player. That comb is real and belongs.
ROOM_STAGGER = float(__import__('os').environ.get('TUNING_STAGGER') or 0.10)
_STAGGER_PLANES = ('room_left', 'room_right', 'room_back', 'room_front',
                   'room_ceiling')


def _room_arrivals(planes, floor, sx, sy, sz):
    """Path length to the listener for each of the six first-order images."""
    L, R, B, F, C = planes
    out = []
    for axis, plane in ((0, -L), (0, R), (1, -B), (1, F), (2, C), (2, -floor)):
        img = [sx, sy, sz]
        img[axis] = 2.0 * plane - img[axis]
        out.append(_sqrt(img[0] ** 2 + img[1] ** 2 + img[2] ** 2))
    return out


def stagger_room(name, amount=None, tries=256):
    """Offset the shell planes so no two first-order images coincide.

    Returns the smallest gap between adjacent arrivals, in METRES of path.
    """
    amount = ROOM_STAGGER if amount is None else amount
    if amount <= 0.0:
        return 0.0
    import zlib
    S = SynthProperties
    base = [getattr(S, k) for k in _STAGGER_PLANES]
    floor = S.room_floor
    # Judge a draw on the centre line, where the symmetry is worst.
    sy = S.radiation_distance
    W0 = base[0] + base[1]; D0 = base[2] + base[3]; H0 = base[4] + floor
    V0 = W0 * D0 * H0
    A0 = 2.0 * (W0 * D0 + W0 * H0 + D0 * H0)
    # crc32, not hash(): str hashing is salted per process and would make a
    # render irreproducible across runs.
    rng = _random.Random(0x52004D ^ zlib.crc32(name.encode()))
    best, best_gap = None, -1.0
    for _ in range(tries):
        offs = [rng.uniform(-amount, amount) for _ in base]
        # Straddle the preset: the mean offset is removed, so the draw moves
        # the walls apart without moving the room as a whole.
        m = sum(offs) / len(offs)
        cand = [b * (1.0 + o - m) for b, o in zip(base, offs)]
        # Restore the volume EXACTLY by scaling the three extents; the floor is
        # fixed, so the ceiling absorbs its axis' share.
        k = (V0 / ((cand[0] + cand[1]) * (cand[2] + cand[3])
                   * (cand[4] + floor))) ** (1.0 / 3.0)
        cand = [cand[0] * k, cand[1] * k, cand[2] * k, cand[3] * k,
                (cand[4] + floor) * k - floor]
        if min(cand) <= 0.0:
            continue
        # Hold the SURFACE AREA too, not just the volume. Eyring's T60 goes as
        # V/(S*alpha), so letting S drift would quietly retune the reverberation
        # the preset was written to have -- an unstaggered hall's area moves
        # 2.4% on a free draw. One per cent is under a tenth of a dB of wetness.
        w, d, h = cand[0] + cand[1], cand[2] + cand[3], cand[4] + floor
        if abs(2.0 * (w * d + w * h + d * h) / A0 - 1.0) > 0.01:
            continue
        # Compare PATH LENGTHS. The separation that matters is a time, but
        # the speed of sound is a constant factor and drops out of a
        # comparison between draws.
        t = sorted(_room_arrivals(cand, floor, 0.0, sy, 0.0))
        gap = min(b - a for a, b in zip(t, t[1:]))
        if gap > best_gap:
            best, best_gap = cand, gap
    if best is None:
        return 0.0
    for k, v in zip(_STAGGER_PLANES, best):
        setattr(S, k, v)
    return best_gap


def set_room(name, stagger=True):
    """Apply a room preset to SynthProperties, for every voice at once."""
    preset = ROOM_PRESETS.get(name)
    if preset is None:
        raise ValueError("unknown room %r; have %s"
                         % (name, ", ".join(sorted(ROOM_PRESETS))))
    for k, v in preset.items():
        setattr(SynthProperties, k, v)
    if stagger:
        stagger_room(name)
    return name


import os as _os
# The default room is the hall, and it needs the stagger as much as any other --
# it is the one with three coincident surfaces.
set_room(_os.environ.get('TUNING_ROOM') or 'hall')
# WHERE YOU LISTEN FROM, in metres, independent of which room. This is the
# strongest single control over how a render sounds and it is not a reverb
# setting: the direct-to-reverberant ratio goes as (distance / critical
# distance)^2, so a listener at twice the critical distance hears four times as
# much room as direct sound, and reads it as far away, dull and boomy all at
# once. A microphone is placed at or inside the critical distance, which is
# most of why records sound closer than seats do.
if _os.environ.get('TUNING_DISTANCE'):
    SynthProperties.radiation_distance = float(_os.environ['TUNING_DISTANCE'])
# TUNING_WET asks for a direct-to-reverberant RATIO instead, and solves for the
# distance that gives it. -3 is the harmonic-transparency target.
if _os.environ.get('TUNING_WET'):
    set_wetness(float(_os.environ['TUNING_WET']))
