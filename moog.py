#!/usr/bin/env python3
"""A Moog Messenger, as partials.

Ben has a Messenger, and wanted the synth leads to be one: the analog
oscillators and the ladder filter simulated, each lead a patch on it, and the
panel's knobs on the TUI. It is built the way the amplifier was (tubeamp.py):
synthkernel.c is ADDITIVE, so an analog stage has to become something done to
partials, and every stage here can be.

  OSCILLATOR   a periodic wave IS its Fourier series. The partials are the
               oscillator; WAVESHAPE only sets their levels and phases.
  FILTER       a linear filter multiplies each partial by its transfer function
               at that partial's frequency, |H(f)|. The ladder's cutoff moving
               inside a note is |H| moving -- evaluated per partial per block in
               the kernel, the way the organ's swell shutter already is.
  ENVELOPES    functions of time since the note began, so stateless: the
               kernel evaluates them at each block's ends, offline and live alike.

THE MESSENGER, from its manual (the 20250618 revision). Two VCOs, each an
OCTAVE switch (32'-4') and a WAVESHAPE knob that sweeps, clockwise:

    folded triangle (more fold further CCW)   fully CCW
    triangle                                   ~11 o'clock
    sawtooth                                   noon
    square                                     ~1 o'clock
    pulse, narrowing to ~2%                    fully CW

a SUB OSC an octave under OSC 1 (triangle -> square at ~11 o'clock -> 2%
pulse), noise, a clean mixer, and a ladder filter with four modes made by
"creative mixing of the filter pole outputs": 4-pole low-pass, 2-pole low-pass,
band-pass, high-pass; RESONANCE, which self-oscillates at the top; RES BASS,
which keeps the bass a ladder loses as its resonance rises.

WHAT THE MANUAL DOES NOT SAY, AND WHAT IS MODELLED HERE INSTEAD. It gives the
waveshape's landmarks, not the paths between them. On a pot's 300-degree sweep,
noon is 0.5, 11 o'clock 0.4 and 1 o'clock 0.6, so:

    0.0 - 0.4   the triangle folded, gain 5 -> 1: a triangle folder reflects
                what passes +-1 back inside, so more gain is more folds
    0.4 - 0.5   the triangle SKEWED into a sawtooth: its peak moves from the
                middle of the period to the end, which is what a ramp-core
                oscillator's morph does
    0.5 - 0.6   sawtooth crossfaded into square
    0.6 - 1.0   square narrowed to a 2% pulse

and the sub's triangle becomes a square by CLIPPING -- the triangle driven
harder into a limit, a trapezoid, then a square -- which is the analog way to
square a triangle. The pole mix for the band-pass and high-pass is the
Oberheim Xpander's (4y2-8y3+4y4, y0-2y1+y2); Moog does not publish its own.
None of this is measured from a Messenger; Ben's is the instrument to check
it against.

EXACT, AND NEEDING NO BAND-LIMITING. Every shape above is PIECEWISE LINEAR --
ramps, steps, a folded triangle is still straight lines -- and a piecewise
linear wave has a closed-form Fourier series: each straight segment integrates
exactly. So the coefficients are computed, not sampled; there is no FFT to
alias and no table to interpolate, and a coefficient at harmonic 64 is as
exact as the fundamental's.
"""
import cmath
import functools
import json
import math
import os

import numpy as np

import mf104

# ---------------------------------------------------------------- the waves
# A wave is one period on [0, 1) as straight segments (t0, t1, y0, y1).

def _segments_coeffs(segs, n):
    """c_k for k = 1..n of a piecewise linear period, exactly.

    On a segment y = y0 + m(t - t0), with w = 2 pi k and E(t) = exp(-i w t),
        integral y E dt = i (y1 E(t1) - y0 E(t0)) / w + m (E(t1) - E(t0)) / w^2
    and c_k is the sum over segments. The real wave is
    sum_k 2|c_k| cos(2 pi k t + arg c_k)."""
    k = np.arange(1, n + 1, dtype=float)
    w = 2.0 * np.pi * k
    c = np.zeros(n, complex)
    for t0, t1, y0, y1 in segs:
        if t1 <= t0:
            continue
        m = (y1 - y0) / (t1 - t0)
        e0, e1 = np.exp(-1j * w * t0), np.exp(-1j * w * t1)
        c += 1j * (y1 * e1 - y0 * e0) / w + m * (e1 - e0) / (w * w)
    return c


def _skewed_triangle(peak):
    """-1 up to +1 at `peak`, back down to -1 at the period's end.
    peak 0.5 is the triangle, peak 1 the rising sawtooth."""
    if peak >= 1.0:
        return [(0.0, 1.0, -1.0, 1.0)]
    return [(0.0, peak, -1.0, 1.0), (peak, 1.0, 1.0, -1.0)]


def _pulse(duty):
    """+1 for `duty` of the period, -1 for the rest (its DC is not a partial)."""
    return [(0.0, duty, 1.0, 1.0), (duty, 1.0, -1.0, -1.0)]


def _pulse_centred(duty, centre=0.75):
    """+1 for `duty` of the period about `centre`. About the three-quarter
    point the square (duty 0.5) is IN PHASE with the rising saw -- their
    fundamentals add, as the Messenger's do across the crossfade; about the
    half, with the triangle (the sub's). Narrowing it keeps that phase."""
    a, b = centre - duty / 2.0, centre + duty / 2.0
    return [(0.0, a, -1.0, -1.0), (a, b, 1.0, 1.0), (b, 1.0, -1.0, -1.0)]


def _fold(segs, gain):
    """A triangle folder after `gain`: whatever passes +-1 is reflected back.
    Straight lines stay straight, so the result is split at every crossing of
    an odd level and each piece reflected -- still piecewise linear."""
    out = []
    for t0, t1, y0, y1 in segs:
        a, b = gain * y0, gain * y1
        lo, hi = min(a, b), max(a, b)
        cuts = [2 * j + 1 for j in range(int(math.floor((lo - 1) / 2)), int(math.ceil((hi - 1) / 2)) + 1)
                if lo < 2 * j + 1 < hi]
        cuts.sort(reverse=(a > b))
        pts = [a] + cuts + [b]
        for u, v in zip(pts, pts[1:]):
            s0 = t0 + (t1 - t0) * (u - a) / (b - a) if b != a else t0
            s1 = t0 + (t1 - t0) * (v - a) / (b - a) if b != a else t1
            out.append((s0, s1, _reflect(u), _reflect(v)))
    return out


def _reflect(x):
    """x folded into [-1, 1] by reflection at +-1 (period 4)."""
    x = (x + 1.0) % 4.0
    return x - 1.0 if x <= 2.0 else 3.0 - x


def _clip(segs, gain):
    """gain, then a hard limit at +-1: a triangle becomes a trapezoid, and at
    high gain a square. Split where the line crosses +-1."""
    out = []
    for t0, t1, y0, y1 in segs:
        a, b = gain * y0, gain * y1
        cuts = sorted({c for c in (-1.0, 1.0) if min(a, b) < c < max(a, b)}, reverse=(a > b))
        pts = [a] + cuts + [b]
        for u, v in zip(pts, pts[1:]):
            s0 = t0 + (t1 - t0) * (u - a) / (b - a) if b != a else t0
            s1 = t0 + (t1 - t0) * (v - a) / (b - a) if b != a else t1
            out.append((s0, s1, max(-1.0, min(1.0, u)), max(-1.0, min(1.0, v))))
    return out


# WAVESHAPE (0 = CCW), as Ben's Messenger has it -- the whole knob swept, h1
# to h10 at every 0.025 (examples/messenger_fit.py 'wave'). Between its
# landmarks it CROSSFADES the two waves, each swinging +-1 (their levels say
# so: the square's fundamental 6.0 dB over the saw's, the triangle's 2.1):
# triangle to saw from 0.335 to 0.5 (0.13-0.7 dB per position; a skew of the
# triangle, the first model's, was 6-15 dB off), saw to square to 0.68 (the
# odd harmonics hold at 1/k, the even fade; h2 and h4 null at 0.68), and past
# it the pulse narrows to a duty of 0.025 at 1 (its nulls at k = 1/d). Below
# the triangle the Messenger folds, and not as this folder does -- its fold has
# no even harmonics, nulls the fundamental near 0.3, and fits neither a
# reflecting nor a sine folder; no patch uses it, so it is left as it was.
# The first model's landmarks were 0.4/0.5/0.6, the second's 0.35/0.5/0.635.
# synthkernel.c's ms_parts mirrors all of it.
TRI, SAW, SQUARE = 0.335, 0.5, 0.68
FOLD_MAX = 5.0                         # the folder's gain at fully CCW
PULSE_MIN = 0.025                      # the narrowest pulse, at fully CW
SUB_PULSE_MIN = 0.0033                 # SUB WAVE's narrowest, at fully CW
Q = 400                                # knob positions cached: 400 steps put
                                       # every landmark (0.335, 0.5, 0.68) on one


def _osc_parts(s):
    """WAVESHAPE at s as [(weight, segments)]: one wave, or the two a
    crossfade is between."""
    if s < TRI:                                    # folded triangle
        g = 1.0 + (FOLD_MAX - 1.0) * (TRI - s) / TRI
        return [(1.0, _fold(_skewed_triangle(0.5), g))]
    if s < SAW:                                    # triangle crossfaded to saw
        a = (s - TRI) / (SAW - TRI)
        return [(1.0 - a, _skewed_triangle(0.5)), (a, _skewed_triangle(1.0))]
    if s < SQUARE:                                 # saw crossfaded to square
        a = (s - SAW) / (SQUARE - SAW)
        return [(1.0 - a, _skewed_triangle(1.0)), (a, _pulse_centred(0.5))]
    d = 0.5 - (0.5 - PULSE_MIN) * (s - SQUARE) / (1.0 - SQUARE)
    return [(1.0, _pulse_centred(d))]


@functools.lru_cache(maxsize=4 * Q)
def _osc_cached(q, n):
    parts = _osc_parts(q / float(Q))
    c = parts[0][0] * _segments_coeffs(parts[0][1], n)
    for w, segs in parts[1:]:
        c = c + w * _segments_coeffs(segs, n)
    return c


def _synced(segs, r):
    """A wave of period 1/r hard-synced to period 1: each of OSC 1's periods
    holds r of OSC 2's, restarted at its start -- still straight segments, so
    its series is as exact as the free waves'."""
    out, c = [], 0
    while c < r:
        for t0, t1, y0, y1 in segs:
            u0, u1 = c + t0, c + t1
            if u0 >= r:
                break
            if u1 > r:
                y1 = y0 + (y1 - y0) * (r - u0) / (u1 - u0)
                u1 = r
            out.append((u0 / r, u1 / r, y0, y1))
        c += 1
    return out


@functools.lru_cache(maxsize=1024)
def _sync_cached(q, rq, n):
    r = rq / 10000.0
    c = np.zeros(n, complex)
    for w, segs in _osc_parts(q / float(Q)):
        c += w * _segments_coeffs(_synced(segs, r), n)
    return c


def sync_spectrum(shape, r, n):
    """OSC 2 at WAVESHAPE `shape`, r times OSC 1's frequency, hard-synced to
    it (SYNC 1->2): c_k of the harmonics of OSC 1. The classic tearing sweep
    is r moving -- OSC 2 FREQ turned while the sync holds the pitch."""
    q = int(round(max(0.0, min(1.0, shape)) * Q))
    return _sync_cached(q, int(round(max(r, 1e-3) * 10000)), int(n)).copy()


def osc_spectrum(shape, n):
    """OSC 1 or 2 at WAVESHAPE `shape` (0 = fully CCW, 1 = fully CW): the
    complex coefficients c_k of harmonics 1..n. The partial for harmonic k has
    amplitude 2|c_k| and phase arg c_k, on a wave that swings +-1."""
    q = int(round(max(0.0, min(1.0, shape)) * Q))
    return _osc_cached(q, int(n)).copy()


# SUB WAVE, measured as WAVESHAPE was (h1-h10 at every 0.05): a triangle at
# 0 CROSSFADED to a square at 0.3 (0.1-0.5 dB per position; the first model
# clipped the triangle, 5-6 dB off -- the crossfade's thirds cancel near 0.05,
# a clip's cannot), both about the half period, then a pulse narrowing to all
# but nothing at 1 (its nulls at k = 1/d; h1 39.7 dB under the square's).
SUB_SQUARE = 0.3
V2_SUB_SQUARE = 0.4                    # the first models' (synth_units 3 and before)


@functools.lru_cache(maxsize=4 * Q)
def _sub_cached(q, n):
    s = q / float(Q)
    if s < SUB_SQUARE:                             # triangle crossfaded to square
        a = s / SUB_SQUARE
        return ((1.0 - a) * _segments_coeffs(_skewed_triangle(0.5), n)
                + a * _segments_coeffs(_pulse_centred(0.5, 0.5), n))
    d = 0.5 - (0.5 - SUB_PULSE_MIN) * (s - SUB_SQUARE) / (1.0 - SUB_SQUARE)
    return _segments_coeffs(_pulse_centred(d, 0.5), n)


def sub_spectrum(shape, n):
    """The SUB OSC at SUB WAVE `shape`: c_k of ITS harmonics 1..n (at half of
    OSC 1's frequency)."""
    q = int(round(max(0.0, min(1.0, shape)) * Q))
    return _sub_cached(q, int(n)).copy()


# ---------------------------------------------------------------- the ladder
LP4, LP2, BP, HP = 0, 1, 2, 3
MODES = ('4P LOW PASS', '2P LOW PASS', 'BAND PASS', 'HIGH PASS')
# THE MODES, measured (examples/messenger_fit.py modes; noise at CUTOFF 0.35,
# RESONANCE 0, |H| in half-octave steps): the two low-passes are the
# ladder's own within a dB. The BAND PASS is the mixed poles' shape 7.6 dB
# down with its corner 5% up (0.78 dB rms); the HIGH PASS 6.4 dB down, its
# corner 9% down, and a LEAK of the dry signal under it -- flat at -23 dB
# through the stop band (0.95 dB rms).
BP_GAIN, BP_CORNER = 10 ** (-7.6 / 20.0), 1.05
HP_GAIN, HP_CORNER, HP_LEAK = 10 ** (-6.4 / 20.0), 0.91, 0.071
K_MAX = 3.9      # feedback at full RESONANCE: 4 is the edge of self-oscillation,
                 # where a partial on the peak would be amplified without limit


def ladder(f, fc, k, mode=LP4, res_bass=False):
    """The transistor ladder's complex response at frequency f (array ok).

    Four identical one-pole stages g = 1/(1 + j f/fc), the fourth's output fed
    back inverted with gain k: the stages see u = X / (1 + k g^4), and pole i
    puts out y_i = g^i u. Low-pass is the fourth pole (24 dB/oct) or the second
    (12); the band-pass and high-pass MIX the poles.

    A ladder's resonance costs it its bass: at DC the loop gain is k, so the
    low-pass passes 1/(1+k). RES BASS restores it -- a gain of (1+k) on the
    low-pass modes, which is what compensation does -- so the peak stands up
    out of the passband instead of the passband sinking under the peak."""
    fc = fc * (BP_CORNER if mode == BP else HP_CORNER if mode == HP else 1.0)
    g = 1.0 / (1.0 + 1j * np.asarray(f, float) / fc)
    u = 1.0 / (1.0 + k * g ** 4)
    if mode == LP4:
        h = g ** 4 * u
    elif mode == LP2:
        h = g ** 2 * u
    elif mode == BP:
        h = BP_GAIN * 4.0 * g ** 2 * (1.0 - g) ** 2 * u
    else:
        h = HP_GAIN * (1.0 - g) ** 2 * u + HP_LEAK
    if res_bass and mode in (LP4, LP2):
        h = h * (1.0 + k)
    return h


# THE OUTPUT STAGE: after the ladder and the VCA, a fixed gentle low-pass --
# measured with the ladder wide open (CUTOFF 0.6-1, its own corner far above
# the band: a resonant peak there leaves it, rather than standing at 20 kHz),
# a saw's harmonics 1.4 dB under 1/k at 8 kHz and 4.3 at 16 kHz once the
# mixer's own path (swept from the laptop: -1.2 and -3.8) is taken out --
# one pole at 12.5 kHz (within 0.3 dB, 2.7-16 kHz).
OUT_HZ = 12500.0


def output_gain(f):
    """|H| of the output stage at f: every partial passes it, sidebands and
    the ladder's own sine included, once."""
    return 1.0 / np.sqrt(1.0 + (np.asarray(f, float) / OUT_HZ) ** 2)


def ladder_gain(f, fc, k, mode=LP4, res_bass=False):
    """|H|, the magnitude alone -- what the kernel applies. The phase response
    is dropped, which only changes the wave's SHAPE, never what one hears,
    and is exact between partials at the same frequency."""
    x = np.asarray(f, float) / (fc * (BP_CORNER if mode == BP else HP_CORNER if mode == HP else 1.0))
    # (1 + jx)^4 = (1 - 6x^2 + x^4) + j(4x - 4x^3): |den| = |(1+jx)^4 + k|
    re4, im4 = 1.0 - 6.0 * x * x + x ** 4, 4.0 * x - 4.0 * x ** 3
    den = np.hypot(re4 + k, im4)
    if mode == LP4:
        num = 1.0
    elif mode == LP2:
        num = 1.0 + x * x                       # |(1+jx)^2|
    elif mode == BP:
        num = BP_GAIN * 4.0 * x * x             # |4 (jx)^2|
    else:
        # the leak adds to the high-pass itself, so the phase counts here:
        # (jx)^2 (1+jx)^2 = (x^4 - x^2) - 2j x^3, over (1+jx)^4 + k
        nr, ni = x ** 4 - x * x, -2.0 * x ** 3
        dr = re4 + k
        d2 = dr * dr + im4 * im4
        hr = HP_GAIN * (nr * dr + ni * im4) / d2 + HP_LEAK
        hi = HP_GAIN * (ni * dr - nr * im4) / d2
        return np.hypot(hr, hi)
    h = num / den
    if res_bass and mode in (LP4, LP2):
        h = h * (1.0 + k)
    return h


# ---------------------------------------------------------------- envelopes
def adsr(t, A, D, S, R, t_off=None):
    """The contour at time t (s) after the key went down, released at t_off.

    Every stage is exponential, each heading a little PAST where it stops,
    as measured on the Messenger: the attack charges toward ATTACK_TARGET and
    is cut at 1 -- which lands at exactly A seconds -- the decay falls toward
    S, the release toward -EG_UNDER, and the contour stops at zero. S is the
    decay's target (sustain_target), so a low SUSTAIN is below zero too: the
    contour falls through and closes, as the hardware's does, about 25 dB
    down. D and R are four time constants. Stateless: the level at release is
    the ADSR's own value at t_off, so the kernel can evaluate any instant
    alone."""
    t = np.asarray(t, float)
    def held(tt):
        before = tt < 0.0                        # the key is not down yet
        tt = np.maximum(tt, 0.0)
        ta = max(A, 1e-6) / _ATK_TO_1
        att = ATTACK_TARGET * (1.0 - np.exp(-tt / ta))
        dec = np.maximum(0.0, S + (1.0 - S) * np.exp(-(tt - A) / (max(D, 1e-6) / 4.0)))
        return np.where(before, 0.0, np.where(tt < A, att, dec))
    e = held(t)
    if t_off is not None:
        lo = held(np.asarray(t_off, float))
        rel = np.maximum(0.0, (lo + EG_UNDER) * np.exp(-(t - t_off) / (max(R, 1e-6) / 4.0)) - EG_UNDER)
        e = np.where(t >= t_off, rel, e)
    return e


# ---------------------------------------------------------------- the knobs
# THE KNOBS' LAWS ARE BEN'S MESSENGER'S (1.1.0), measured through a mixer and
# back (examples/messenger_fit.py, 2026-10-01): a knob here means what the
# same knob position means on the hardware, so a panel sent to it is the
# panel heard. Where the measurement did not reach, the law runs on
# geometrically to the first model's end, and says so. The first laws are
# kept as V1 below: every patch was converted through them (convert_v1), so
# each sounds as it did and its knobs are now the hardware's.
def _clip01(v):
    return max(0.0, min(1.0, float(v)))


# THE CONTOURS, measured (examples/messenger_fit.py attack, times; A5 through
# a 2.3 ms RMS). ATTACK, DECAY and RELEASE share one law: the time constant
# below, the three agreeing within 5% at every position (the attack's from
# its t90 / ln 10). Every stage overshoots where it stops: the attack charges
# toward ATTACK_TARGET and the decay begins at 1 (t50/t90 = 0.30 throughout,
# the peak with sustain 0 at 1.5 t90); decay and release fall toward
# -EG_UNDER and the amplifier closes at zero -- a straight line in dB for
# ~20 dB, then a plunge (fitted within 1 dB at every position, g 0.052-0.057).
# Log-interpolated between the tenths; 0's is under the probe's resolution.
EG_TAU = (0.001, 0.0182, 0.0452, 0.0878, 0.1566, 0.2644, 0.4341, 0.6990, 1.137, 1.892, 5.68)
EG_UNDER = 0.055
ATTACK_TARGET = 1.03
_ATK_TO_1 = math.log(ATTACK_TARGET / (ATTACK_TARGET - 1.0))      # time constants to 1
_ATK_T90 = math.log(10.0)                                         # ...to 90% of the target
_EG_V = np.linspace(0.0, 1.0, len(EG_TAU))
_EG_LOG = np.log(np.array(EG_TAU))


def knob_tau(v):
    """A contour knob's time constant, seconds."""
    return float(np.exp(np.interp(_clip01(v), _EG_V, _EG_LOG)))


def tau_knob(tau):
    return float(np.interp(math.log(max(tau, 1e-6)), _EG_LOG, _EG_V))


def knob_attack(v):
    """ATTACK: the time to the top of the charge, in seconds."""
    return knob_tau(v) * _ATK_TO_1


def attack_knob(seconds):
    return tau_knob(seconds / _ATK_TO_1)


def knob_time(v):
    """DECAY / RELEASE: four time constants, the model's knob time."""
    return 4.0 * knob_tau(v)


def time_knob(t):
    return tau_knob(t / 4.0)


# SUSTAIN: the level the decay heads for, measured as where it settles (the
# amp's, A5): nothing to 0.1, 0.006 at 0.25, 0.23 at 0.5, 0.55 at 0.75, 0.80
# at 0.9 -- steeply curved, not the knob's position. Its bottom is the
# release's -EG_UNDER (sustain 0 falls as a release does); between 0 and 0.25
# not resolved, a line. The filter contour's sustain is taken to be the same
# (one firmware contour; not measured through the ladder).
SUS_V = (0.0, 0.25, 0.5, 0.75, 0.9, 1.0)
SUS_TARGET = (-EG_UNDER, 0.006, 0.23, 0.5466, 0.8015, 1.0)


def sustain_target(v):
    """SUSTAIN: where the decay heads (below zero: it closes)."""
    return float(np.interp(_clip01(v), SUS_V, SUS_TARGET))


def sustain_knob(level):
    return float(np.interp(level, SUS_TARGET, SUS_V))


def sustain_level(v):
    """What a SUSTAIN holds at: its target, or nothing."""
    return max(0.0, sustain_target(v))


# THE SECOND MODEL'S CONTOURS (synth_units 2, committed 52a805d): decay and
# release 1.19 s at 0.5 e-folding every 1/4.75 above, geometric to 1 ms below;
# the attack the first model's; sustain the level itself. convert_v2 maps a
# panel written in them; convert_v1 goes straight to these laws.
V2_DR = (0.5, 1.19, 4.75, 0.001)


def v2_knob_time(v):
    v = _clip01(v)
    mv, ms, rate, lo = V2_DR
    if v >= mv:
        return ms * math.exp(rate * (v - mv))
    return lo * (ms / lo) ** (v / mv)


def v1_knob_attack(v):
    return 0.001 * 10000.0 ** _clip01(v)


# CUTOFF: by white noise through the ladder, fitted with |H| above the
# hardware's own floor (~60 dB under): 187 Hz fully CCW, 416 at 0.1, 884 at
# 0.2, 1.88 k at 0.3, 4.12 k at 0.4, 9.3 k at 0.5 -- 11.14 octaves a unit, a
# straight line to 0.05 octave; past 0.55 the corner is above the band. Its
# BOTTOM IS ~190 Hz, not 20: a first fit, misled by the floor, guessed the
# low end and put every converted patch's corner far too low on the knob.
CUT_LO_HZ, CUT_OCT = 189.0, 11.14


def knob_cutoff(v):
    """CUTOFF: the ladder's corner, Hz."""
    return CUT_LO_HZ * 2.0 ** (CUT_OCT * _clip01(v))


def cutoff_knob(hz):
    """knob_cutoff backwards."""
    return _clip01(math.log2(max(float(hz), CUT_LO_HZ) / CUT_LO_HZ) / CUT_OCT)


# LFO 1 RATE: 0.40 Hz at 0.3, 0.84 at 0.4, 1.55 at 0.5 -- 0.05 Hz to ~44 Hz
# over the knob, where the first model had 12.
LFO_RATE_LO, LFO_RATE_SPAN = 0.05, 870.0


def knob_lfo_rate(v):
    """LFO 1 RATE, Hz."""
    return LFO_RATE_LO * LFO_RATE_SPAN ** _clip01(v)


def lfo_rate_knob(hz):
    return _clip01(math.log(max(float(hz), LFO_RATE_LO) / LFO_RATE_LO) / math.log(LFO_RATE_SPAN))


# LFO 1, measured (examples/messenger_fit.py lfo; a slow LFO from the key,
# the cutoff by noise in 0.25 s windows, the pitch tracked): the TRIANGLE
# swings both ways about the panel; the SAWTOOTH (falling, as Moog names it),
# the RAMP (rising) and the SQUARE (high first) only one way -- up for DEPTH
# past the centre, down short of it. DEPTH is a CUBE of its distance from
# the centre: the cutoff 87 x^3 octaves (0.30 at 0.65, 1.36 at 0.75, 2.38 at
# 0.8, each within 2%; ~11 at the end), the pitch 37.2 x^3 (35-37.4 a unit at
# every depth 0.6-0.9), a waveshape 7.8 x^3 of its knob (a square LFO from the
# triangle, the shifted wave read off its spectrum: 0.057 at 0.7, 0.112 at
# 0.75, 0.515 at 0.9) -- which is the cutoff's law in the cutoff knob's own
# units (87 / 11.14 = 7.81): LFO 1 turns the knob it is sent to.
LFO_CUT_CUBE, LFO_PITCH_CUBE = 87.0, 37.2
LFO_KNOB_CUBE = LFO_CUT_CUBE / 11.14
V4_LFO_WAVE_SPAN = 0.5                 # the first models' reach on a waveshape, linear
V4_LFO_OCTAVES, V4_LFO_PITCH_OCTAVES = 3.0, 4.0     # the first models': linear, bipolar
LFO_SHAPES = ('triangle', 'sawtooth', 'ramp', 'square')
LFO_DESTS = ('cutoff', 'osc 2 freq', 'osc 1 wave', 'sub wave')


def lfo(x, shape):
    """LFO 1 at phase x (cycles): the triangle -1..1, the others 0..1 -- the
    sawtooth falling, the ramp rising, the square high for the first half."""
    x = np.asarray(x, float) % 1.0
    if shape == 0:
        return 1.0 - 4.0 * np.abs(x - 0.5)
    if shape == 1:
        return 1.0 - x
    if shape == 2:
        return x
    return np.where(x < 0.5, 1.0, 0.0)


def _cube(v, k):
    x = _clip01(v) - 0.5
    return k * x * x * x


def _cube_knob(octaves, k):
    return 0.5 + math.copysign(abs(octaves / k) ** (1.0 / 3.0), octaves)


def lfo_cut_octaves(v):
    """LFO 1 DEPTH on the cutoff: the octaves at the shape's +1."""
    return _cube(v, LFO_CUT_CUBE)


def lfo_cut_knob(octaves):
    return _cube_knob(octaves, LFO_CUT_CUBE)


def lfo_pitch_octaves(v):
    """LFO 1 DEPTH on OSC 2's pitch: the octaves at the shape's +1."""
    return _cube(v, LFO_PITCH_CUBE)


def lfo_pitch_knob(octaves):
    return _cube_knob(octaves, LFO_PITCH_CUBE)


def lfo_wave_reach(v):
    """LFO 1 DEPTH on a waveshape: the knob travel at the shape's +1."""
    return _cube(v, LFO_KNOB_CUBE)


def lfo_wave_knob(reach):
    return _cube_knob(reach, LFO_KNOB_CUBE)


# SELF-OSCILLATION. The Messenger's resonance "self-oscillates to a sine at
# fully clockwise"; measured, it sings alone from about 0.7 (a tone at the
# corner, -39 dBFS there against a saw's -29 rms, -34 at full), and the
# ladder's feedback rises 5.7 a unit of knob (fitted against |H|, 0.57 at 0.1
# to 3.42 at 0.6) -- K_MAX by 0.684, where the sine begins. Past it the sine
# comes in at the cutoff, rising as the square of how far past SELF_FROM, up to SELF_AMP
# (about a saw's own level). The ladder's feedback itself stops at K_MAX, where
# a partial on the peak is already 30 dB up. The sine stands at the cutoff the
# contour SUSTAINS at: a sine that swept with the contour would need its phase
# integrated over the note's history, which a stateless kernel cannot carry.
RES_PER_UNIT = 5.7
SELF_FROM, SELF_AMP = K_MAX / RES_PER_UNIT, 0.5


def self_amp(v):
    return SELF_AMP * max(0.0, (v - SELF_FROM) / (1.0 - SELF_FROM)) ** 2


def knob_k(v):
    """RESONANCE: the ladder's feedback, RES_PER_UNIT a unit of knob, to K_MAX."""
    return min(K_MAX, RES_PER_UNIT * _clip01(v))


V1_EG_OCTAVES = 7.0    # the first model's EG AMOUNT: linear, +-7 octaves at the ends
EG_CURVE = 45.0        # measured: the contour opens 45 x|x| octaves, x the knob off centre


def eg_octaves(v):
    """EG AMOUNT: how far the filter contour's peak moves the cutoff, in octaves.
    Measured on the Messenger (examples/messenger_fit.py eg): centred, flat
    near the detent and a square law away from it -- 45 x|x|, x = v - 0.5, fit
    within a few percent from 0.25 to 0.8, about +-11 octaves at the ends."""
    x = _clip01(v) - 0.5
    return EG_CURVE * x * abs(x)


def eg_knob(octaves):
    return 0.5 + math.copysign(math.sqrt(abs(octaves) / EG_CURVE), octaves)
KB_REF_HZ = 261.6256   # key tracking pivots on middle C, the 8' bottom key


def cutoff_at(fc0, note_hz, track):
    """KB TRACKING: the cutoff follows the key -- OFF (0) or 1 V/oct (1), the
    only two the hardware has: measured, CC78 below 64 is off and 64 up is
    1:1 about middle C (A2's corner 1.25 octaves under, A4's 0.75 over), with
    no 2/3 between -- the manual's three ranges are not what it does."""
    return fc0 * (note_hz / KB_REF_HZ) ** track


# The panel, as knob name -> default (0..1 unless a switch). A lead is a dict
# of overrides on these. Bipolar knobs (OSC 2 FREQ, TUNE, EG AMOUNT) are 0.5 at
# the centre detent.
PANEL_V1 = dict(          # the first model's units; PANEL itself is converted below
    osc1_octave=8, osc1_wave=SAW,
    osc2_octave=8, osc2_wave=SAW, osc2_freq=0.5, tune=0.5,
    sub_wave=SUB_SQUARE,
    osc1_level=1.0, osc2_level=0.0, sub_level=0.0, noise_level=0.0,
    cutoff=0.75, resonance=0.0, eg_amount=0.5, kb_track=1.0,
    mode=LP4, res_bass=False,
    f_attack=0.0, f_decay=0.4, f_sustain=0.5, f_release=0.3,
    a_attack=0.0, a_decay=0.4, a_sustain=1.0, a_release=0.3,
    glide=0.0,
    sync=False,
    lfo1_rate=0.5, lfo1_shape=0, lfo1_depth=0.5, lfo1_dest=0, lfo1_reset=False,
    mod_amount=0.5, mod_dest=1,
    # THE MF-104M ANALOG DELAY after it (mf104.py): Moog's own echo, in the
    # panel so a part saves it and a preset recalls it as it does every knob
    **mf104.PANEL,
)


def bipolar(v, span):
    """A centre-detent knob: 0.5 is 0, the ends are -span and +span."""
    return (max(0.0, min(1.0, v)) - 0.5) * 2.0 * span


def panel_of(props, overrides=None, layer='a'):
    """A voice's knobs: the panel's defaults, the voice's patch over them
    (its class's `messenger` dict), TUNING_MOOG_PANEL over that (JSON knob
    positions, for a file render -- the panel a file cannot turn), and a
    part's own settings over everything. Layer 'b' is a LAYERED voice's
    second Messenger: its class's `messenger_b`, TUNING_MOOG_PANEL_B."""
    out = dict(PANEL)
    out.update(getattr(props, 'messenger' if layer == 'a' else 'messenger_b', None) or {})
    env = os.environ.get('TUNING_MOOG_PANEL' if layer == 'a' else 'TUNING_MOOG_PANEL_B')
    if env:
        out.update({k: v for k, v in json.loads(env).items() if k in PANEL})
    out.update(overrides or {})
    return out


def layers_of(props):
    """A LAYERED VOICE is two Messengers on one MIDI channel -- as a Moog Muse
    stacks its two timbres on a key -- each a whole panel (MF-104M included),
    their sounds summed: ('a', 'b') when the class declares `messenger_b`."""
    return ('a', 'b') if getattr(props, 'messenger_b', None) else ('a',)


# ---------------------------------------------------------------- to partials
# What the kernel is handed. Both renderers build a Moog note from these three,
# so they cannot disagree about what a knob means.
FT_W, KN_W = 30, 9      # must match FTW and KNW in synthkernel.c
FT_FM = 16              # FT slot 12 flag: OSC 1 frequency-modulates OSC 2 (slots 13-29)
FT_PITCH = 1            # FT slot 12, a flag: OSC 2 follows the note's pitch rows
FT_SHAPE = {1: 2, 2: 4, 3: 8}   # ...and these: OSC 1 / OSC 2 / SUB's shape moves (rows)
FMAX_HZ = 12000.0       # highest partial: past it a saw's harmonics are 27 dB
                        # down at 440 Hz, the ladder usually has them lower
                        # still, and three oscillators' worth is the CPU bill
OSC_HARMONICS, SUB_HARMONICS = 64, 32
FOOT = {32: 0.25, 16: 0.5, 8: 1.0, 4: 2.0}      # OCTAVE, against 8'
SEMIS = 7.0                                     # TUNE and OSC 2 FREQ: +-7
OSC1, OSC2, SUB, NOISE, SELF = 1, 2, 3, 4, 5

# THE NOISE OSCILLATOR, as partials. White noise is a flat spectrum, so it is
# a bank of noise BANDS: a third of an octave apart from 40 Hz to the top, each
# a partial whose phase is redrawn at random as fast as its own bandwidth
# (synthkernel.c, a Moog partial with a negative wash bandwidth). A band's
# power goes as its width, so its amplitude as the square root of its centre;
# the bank together is noise of NOISE_RMS at NOISE fully up -- a saw's own rms
# is 0.58. Fixed in hertz, not following the key: noise has no pitch. And it
# is a Moog partial like the others, so the ladder filters it by frequency and
# the amp contour shapes it -- the Messenger's mixer, filter, VCA.
NOISE_LO_HZ, NOISE_STEP = 40.0, 2.0 ** (1.0 / 3.0)
NOISE_BW = NOISE_STEP - 1.0          # a band's width, as a fraction of its centre
# measured against a saw at the same level: in 100 Hz-2 kHz (above it the
# mixer's own roll-off takes as much as the noise does) its rms is 1.7 dB
# under the saw's fundamental -- 4.6 dB over the first model's 0.5
NOISE_RMS = 0.5 * 10 ** (4.6 / 20.0)
V5_NOISE_RMS = 0.5


def _noise_bank():
    f = []
    while NOISE_LO_HZ * NOISE_STEP ** len(f) <= FMAX_HZ:
        f.append(NOISE_LO_HZ * NOISE_STEP ** len(f))
    f = np.array(f)
    a = np.sqrt(f)
    a *= NOISE_RMS / np.sqrt(0.5 * (a * a).sum())
    return f, a


NOISE_HZ, NOISE_AMP = _noise_bank()


def partials(panel, f0, fmax=FMAX_HZ):
    """(see below)"""
    return _partials(panel, f0, fmax)


def _partials(panel, f0, fmax=FMAX_HZ):
    """[(osc, harmonic, Hz, amplitude, phase)] for one key at f0.

    Each oscillator is its own set of partials -- never merged where two
    coincide -- so the mixer, the octave switches and OSC 2 FREQ can each move
    one oscillator of a sounding note. The SUB follows OSC 1 an octave down.
    Oscillators start in phase at the key: a deterministic choice (the
    Messenger's own may free-run), so the two renderers agree exactly."""
    t = 2.0 ** (bipolar(panel['tune'], SEMIS) / 12.0)
    f1 = f0 * t * FOOT.get(int(panel['osc1_octave']), 1.0)
    f2 = (f0 * t * FOOT.get(int(panel['osc2_octave']), 1.0)
          * 2.0 ** (bipolar(panel['osc2_freq'], SEMIS) / 12.0))
    out = [(NOISE, k + 1, float(NOISE_HZ[k]), float(NOISE_AMP[k]) * panel['noise_level'], 0.0)
           for k in range(len(NOISE_HZ))
           if panel['noise_level'] > 0.0 and NOISE_HZ[k] <= fmax]
    sa = self_amp(panel['resonance'])
    if sa > 0.0:
        fs = self_hz(panel, f0)
        if fs <= fmax:
            out.append((SELF, 1, fs, sa, 0.0))
    # SYNC: OSC 2 restarts at every one of OSC 1's periods, so it sounds on
    # OSC 1's harmonics, its wave the synced one
    sync = bool(panel['sync'])
    osc2 = ((OSC2, f1, panel['osc2_level'],
             lambda n: sync_spectrum(panel['osc2_wave'], f2 / f1, n)) if sync else
            (OSC2, f2, panel['osc2_level'], lambda n: osc_spectrum(panel['osc2_wave'], n)))
    moving = shape_flags(panel)
    for osc, f, lvl, c in (
            (OSC1, f1, panel['osc1_level'], lambda n: osc_spectrum(panel['osc1_wave'], n)),
            osc2,
            (SUB, f1 * 0.5, panel['sub_level'], lambda n: sub_spectrum(panel['sub_wave'], n))):
        if moving & FT_SHAPE[osc]:
            # ITS SHAPE MOVES: the kernel multiplies in the coefficient from the
            # note's shape rows, so the partial carries only 2 x level
            c = lambda n: np.ones(n, complex)
        if lvl <= 0.0 or f <= 0.0:
            continue
        n = min(OSC_HARMONICS if osc != SUB else SUB_HARMONICS, int(fmax // f))
        if osc == OSC2 and pitch_params(panel) is not None:
            # its pitch will move: every harmonic, and the kernel fades those
            # a sweep carries up toward Nyquist (a sweep down reveals them)
            n = OSC_HARMONICS
        if n < 1:
            continue
        cs = c(n)
        for k in range(1, n + 1):
            a = 2.0 * abs(cs[k - 1]) * lvl
            if a > 1e-9:
                out.append((osc, k, f * k, a, cmath.phase(cs[k - 1])))
    return out


# ---------------------------------------------------------------- MOD: FM
# 1 -> 2 FM: OSC 1's own wave modulates OSC 2's frequency -- linearly, a
# deviation of I x OSC 1's frequency x OSC 1's wave, which is phase modulation
# by the wave's integral A = sum_j (2|c_j|/j) sin(j theta1 + phi_j): harmonic k
# of OSC 2 moves by k I A. OSC 1's first FM_J harmonics carry it (a saw's fall
# as 1/j^2 in A). The index against MOD AMOUNT is measured (FM_INDEX_V/I).
# THE LADDER COMES AFTER: harmonic k is sum_m D_m e^{i(k th2 + m th1)}
# (fm_sidebands), and each sideband is filtered at its own frequency
# |k f2 + m f1| -- so a closing contour mellows an FM bell, as on the hardware.
# The kernel does the same sum (synthkernel.c, fm_sidebands); filtering the
# whole harmonic at its carrier, as it first did, was 0.17-0.91 off under a
# shut ladder.
FM_J = 8
# MOD AMOUNT on 1 -> 2 FM, measured (examples/messenger_fit.py fm; triangles
# at unison): the index of the linear FM whose spectrum is the hardware's,
# within 1 dB to 0.64 -- nothing to 0.52, then steeply. Past ~0.65 the
# Messenger's FM is EXPONENTIAL: the carrier's mean pitch drifts off the
# modulator's and every line splits (0.97 and 1.03 of the key at full), which
# no index of this FM makes; the table goes on with the nearest fits (2-4 dB
# off) and a guess at the end. Symmetric about the centre, as measured.
FM_INDEX_V = (0.5, 0.525, 0.55, 0.5625, 0.575, 0.5875, 0.6, 0.625, 0.65, 0.675, 0.7, 0.75, 1.0)
FM_INDEX_I = (0.0, 0.03, 0.12, 0.21, 0.31, 0.41, 0.93, 1.31, 1.80, 2.27, 2.40, 2.92, 4.0)
V1_FM_INDEX_MAX = 3.0                  # the first models' index at either end, linear


def fm_amount_index(v):
    """MOD AMOUNT (on FM) as the index, signed about the centre."""
    x = _clip01(v) - 0.5
    return math.copysign(float(np.interp(0.5 + abs(x), FM_INDEX_V, FM_INDEX_I)), x)


def fm_index_knob(index):
    return 0.5 + math.copysign(float(np.interp(abs(index), FM_INDEX_I, FM_INDEX_V)) - 0.5, index)


def fm_sidebands(panel, k, n=2048, phi1=None):
    """Harmonic k's FM sidebands: (m, D_m), the Fourier coefficients of
    e^{i k I A(th1)} over one turn of OSC 1 -- what the kernel weighs by the
    ladder at k f2 + m f1, one sideband at a time."""
    b = fm_coeffs(panel, phi1)
    th = 2.0 * np.pi * np.arange(n) / n
    a = sum(b[j].real * np.sin((j + 1) * th) + b[j].imag * np.cos((j + 1) * th) for j in range(FM_J))
    return np.fft.fftfreq(n, 1.0 / n).astype(int), np.fft.fft(np.exp(1j * k * fm_index(panel) * a)) / n


def fm_index(panel):
    return fm_amount_index(panel['mod_amount']) if int(panel['mod_dest']) == 0 else 0.0


def fm_coeffs(panel, phi1=None):
    """The modulator's B_j = (2|c_j|/j) e^{i(phi_j - j phi1)}, against the
    phase OSC 1's fundamental partial carries (phi1: arg c_1 unless given),
    so the kernel can read OSC 1's angle straight off that partial."""
    c = osc_spectrum(panel['osc1_wave'], FM_J)
    j = np.arange(1, FM_J + 1)
    p1 = cmath.phase(c[0]) if phi1 is None else phi1
    return 2.0 * np.abs(c) / j * np.exp(1j * (np.angle(c) - j * p1))


def ft_row(panel, f0, krow, pre_amp=False, flags=0, fm_phi1=None):
    """The note's fixed row (FT): what is set at the key. Slot 10 keeps the
    key's own frequency, so a row can be rebuilt when a knob moves; slot 11
    says the partials already carry the filter at its sustain (sustain_gain)
    -- a voice with an amplifier after the ladder -- so the kernel applies
    only the contour's movement about it. Slot 12 is the flags; 13-29 are
    1 -> 2 FM's index and modulator (fm_coeffs)."""
    row = [
        (f0 / KB_REF_HZ) ** float(panel['kb_track']),
        knob_attack(panel['f_attack']), knob_time(panel['f_decay']), knob_time(panel['f_release']),
        knob_attack(panel['a_attack']), knob_time(panel['a_decay']), knob_time(panel['a_release']),
        float(panel['mode']), 1.0 if panel['res_bass'] else 0.0, float(krow), float(f0),
        1.0 if pre_amp else 0.0]
    fi = fm_index(panel)
    row.append(float((int(flags) & ~FT_FM) | (FT_FM if fi != 0.0 else 0)))
    row.append(fi)
    b = fm_coeffs(panel, fm_phi1) if fi != 0.0 else np.zeros(FM_J, complex)
    for z in b:
        row += [float(z.real), float(z.imag)]
    return row


def sustain_gain(panel, f0, f):
    """|H| at the cutoff the filter contour holds while the key is down: what
    an amplifier AFTER the ladder hears of a partial at f, for a key at f0.
    The amplifier's products are computed once, from this; the kernel then
    moves the partials by H(t) / H(sustain) (FT slot 11)."""
    fcs = (knob_cutoff(panel['cutoff']) * (f0 / KB_REF_HZ) ** float(panel['kb_track'])
           * 2.0 ** (eg_octaves(panel['eg_amount']) * sustain_level(panel['f_sustain'])))
    return ladder_gain(f, max(fcs, 1.0), knob_k(panel['resonance']),
                       int(panel['mode']), bool(panel['res_bass']))


def osc_ratio(panel, osc):
    """How far an oscillator sounds from its NOMINAL frequency -- OSC 1 and 2
    at the key, the SUB an octave under it -- given OCTAVE, TUNE and OSC 2 FREQ."""
    t = 2.0 ** (bipolar(panel['tune'], SEMIS) / 12.0)
    if osc == OSC2:
        return (t * FOOT.get(int(panel['osc2_octave']), 1.0)
                * 2.0 ** (bipolar(panel['osc2_freq'], SEMIS) / 12.0))
    return t * FOOT.get(int(panel['osc1_octave']), 1.0)


def weights(panel, mk, nf, fmax=FMAX_HZ):
    """For the partials of a KNOB-NEUTRAL note -- every harmonic of every
    oscillator at unit weight and phase 0, tagged mk = osc * 4096 + k at its
    nominal frequency nf -- what the panel makes of each: (weight, phase,
    frequency ratio). A partial the ratio puts over fmax weighs nothing, so
    the octave switch band-limits the way a fresh note would be."""
    mk = np.asarray(mk, np.int64)
    osc, k = mk // 4096, mk % 4096
    w = np.zeros(len(mk)); ph = np.zeros(len(mk)); rt = np.ones(len(mk))
    m = osc == NOISE                     # the noise bands: level only, in hertz
    if m.any():
        kk = np.clip(k[m], 1, len(NOISE_AMP)) - 1
        w[m] = np.where(np.asarray(nf, float)[m] > fmax, 0.0,
                        NOISE_AMP[kk] * float(panel['noise_level']))
    m = osc == SELF                      # the ladder's own sine, at its cutoff
    if m.any():
        f0s = np.asarray(nf, float)[m]
        fs = np.array([self_hz(panel, f) for f in f0s])
        rt[m] = fs / f0s
        w[m] = np.where(fs > fmax, 0.0, self_amp(panel['resonance']))
    sync = bool(panel['sync'])
    r12 = osc_ratio(panel, OSC2) / osc_ratio(panel, OSC1)
    for o, lvl, n, spec, shape in ((OSC1, 'osc1_level', OSC_HARMONICS, osc_spectrum, 'osc1_wave'),
                                   (OSC2, 'osc2_level', OSC_HARMONICS, osc_spectrum, 'osc2_wave'),
                                   (SUB, 'sub_level', SUB_HARMONICS, sub_spectrum, 'sub_wave')):
        m = osc == o
        if not m.any():
            continue
        if o == OSC2 and sync:              # on OSC 1's harmonics, synced
            c = sync_spectrum(panel[shape], r12, n)
            r = osc_ratio(panel, OSC1)
        else:
            c = spec(panel[shape], n)
            r = osc_ratio(panel, o)
        if shape_flags(panel) & FT_SHAPE[o]:
            c = np.ones(n, complex)                 # the shape rows carry it
        kk = np.clip(k[m], 1, n) - 1
        rt[m] = r
        w[m] = 2.0 * np.abs(c[kk]) * float(panel[lvl])
        ph[m] = np.angle(c[kk])
        if not (o == OSC2 and pitch_params(panel) is not None):   # as partials() keeps them
            w[m] = np.where(np.asarray(nf, float)[m] * r > fmax, 0.0, w[m])
    return w, ph, rt


# GM's SOUND CONTROLLERS, on a Moog: what a file's CC74/71/73/72/75 mean when
# the instrument is this one. Offsets from 64 (-1..+1) on the knobs they name,
# at the ranges midi.md gives every synth: cutoff +-2 octaves (0.2 of CUTOFF's
# ten), resonance +-half the knob, times x/+ 4 (0.15 of the knobs' four decades).
GM_SOUND = {'brightness': ('cutoff', 0.2), 'resonance': ('resonance', 0.5),
            'attack': ('a_attack', 0.15), 'release': ('a_release', 0.15),
            'decay': ('a_decay', 0.15)}


# THE OTHER WAY ROUND: a Messenger's knobs on a part that is NOT a Moog. Each
# knob that has a General MIDI counterpart turns that sound controller (CC71-
# 78), so the hardware's CUTOFF is a piano's nothing and a pizzicato's pluck
# point -- whatever brightness means on the instrument (tonelib.sound_shape).
# GM_SOUND's pairs, inverted, and the LFO as the vibrato; the delay has no
# knob. The knob's whole travel is the controller's, its centre the voice as
# it stands.
MESSENGER_GM = {'cutoff': 74, 'resonance': 71, 'a_attack': 73, 'a_decay': 75,
                'a_release': 72, 'lfo1_rate': 76, 'lfo1_depth': 77}


def apply_gm(panel, sd):
    """The panel with GM sound-controller offsets `sd` (name -> -1..+1) on it."""
    if not sd:
        return panel
    out = dict(panel)
    for name, (knob, span) in GM_SOUND.items():
        d = sd.get(name)
        if d:
            out[knob] = max(0.0, min(1.0, out[knob] + d * span))
    return out


# THE MESSENGER'S OWN CC CHART (its manual, Appendix A): what a part set to
# listen to one reads on its channel INSTEAD of General MIDI -- the two
# disagree about half the numbers (CC10 is TUNE, not pan; CC71-79 are panel
# switches, not sound controllers). Knobs are 14-bit, the fine value on CC+32,
# and a bipolar one is centred at 8192. (panel name, how the value reads);
# None is a control the Messenger has and this simulator does not model yet
# -- taken all the same, so it cannot land on a GM meaning by accident.
# The switch ranges for KB TRACKING and MODE are not in the manual, which
# gives only their positions; even thirds and quarters are the assumption.
MESSENGER_CC = {
    9: ('osc1_wave', '14'), 14: ('osc2_wave', '14'), 10: ('tune', 'tune'),
    12: ('osc2_freq', '14'), 15: ('osc1_level', '14'), 16: ('osc2_level', '14'),
    17: ('sub_level', '14'), 8: ('noise_level', '14'),
    19: ('cutoff', '14'), 21: ('resonance', '14'), 22: ('eg_amount', '14'),
    23: ('f_attack', '14'), 24: ('f_decay', '14'), 25: ('f_sustain', '14'), 26: ('f_release', '14'),
    28: ('a_attack', '14'), 29: ('a_decay', '14'), 30: ('a_sustain', '14'), 31: ('a_release', '14'),
    71: ('sub_wave', '7'), 75: ('osc1_octave', 'foot'), 76: ('osc2_octave', 'foot'),
    78: ('kb_track', 'track'), 79: ('res_bass', 'onoff'), 109: ('mode', 'mode'),
    13: ('mod_amount', '14'), 72: ('mod_dest', 'mode'),
    77: ('sync', 'onoff'), 3: ('lfo1_rate', '14'), 4: ('lfo1_depth', '14'),
    83: ('lfo1_shape', 'mode'), 85: ('lfo1_dest', 'mode'), 93: ('lfo1_reset', 'onoff'),
    2: None, 18: None, 20: None, 27: None,
    73: None, 80: None, 81: None, 89: None,
    102: None, 107: None, 108: None, 112: None, 113: None, 114: None, 116: None,
    117: None, 118: None,
}
# THE OCTAVE SWITCH RISES WITH ITS CC: 0-31 is 32', 32-63 16', 64-95 8',
# 96-127 4' -- measured on Ben's Messenger (1.1.0), A4 sounding at 112, 225,
# 449 and 898 Hz for CC75 = 16, 48, 80, 112. The chart first had it the
# other way round, and every patch sent to the hardware played an octave low.
FOOT_CC = (32, 16, 8, 4)
# the fine halves of the 14-bit knobs
FOURTEEN = ('14', 'tune')
MESSENGER_LSB = {cc + 32: cc for cc, v in MESSENGER_CC.items() if v and v[1] in FOURTEEN}
# BEN'S MESSENGER'S A440 is not at its TUNE knob's centre: it plays 40.5 cents
# sharp there (examples/messenger_fit.py tune; still so after its own tuning
# procedure, and creeping -- 36.7, 38.5, 40.5 over one warm session -- so a
# property of this unit: re-measure, and set this). TUNE is its master tune,
# 1401 cents a unit, so the chart moves it by that much each way: the panel's
# 0.5, A440 here, is sent as the hardware's own A440 and read back as 0.5.
# (The panel's bottom 40 cents are then past the hardware knob's end.)
MESSENGER_TUNE_CENTS = 40.5
_TUNE_TRIM = MESSENGER_TUNE_CENTS / (2.0 * SEMIS * 100.0)


def messenger_value(kind, msb, lsb=None):
    """A Messenger CC's value as the panel knob's (moog.PANEL units)."""
    if kind == '14':
        return ((msb << 7) | (lsb or 0)) / 16383.0 if lsb is not None else msb / 127.0
    if kind == 'tune':
        return messenger_value('14', msb, lsb) + _TUNE_TRIM
    if kind == '7':
        return msb / 127.0
    if kind == 'foot':
        return FOOT_CC[min(3, msb // 32)]
    if kind == 'track':                 # measured: OFF below 64, 1:1 from it
        return 0.0 if msb < 64 else 1.0
    if kind == 'mode':
        return min(3, msb // 32)
    if kind == 'onoff':
        return msb >= 64
    raise ValueError(kind)


# THE FIRMWARE MOVED A KNOB. Before 1.0.7 SUB WAVE was on CC11 (and, 14-bit,
# CC43) -- the release notes: "Expression Input now sends/receives on CC11.
# SUB WAVE now sends/receives on CC71" -- and on Ben's own unit CC11 still
# turns it (captured, SUB WAVE sweeping: CC11/43). Same chart otherwise.
MESSENGER_CC_PRE107 = dict(MESSENGER_CC)
MESSENGER_CC_PRE107.pop(71)
MESSENGER_CC_PRE107[11] = ('sub_wave', '14')
FIRMWARES = ('1.0.7+', 'pre-1.0.7')


def messenger_chart(firmware='1.0.7+'):
    """(the CC chart, its fine halves) for a Messenger on this firmware."""
    ch = MESSENGER_CC_PRE107 if firmware == 'pre-1.0.7' else MESSENGER_CC
    return ch, {cc + 32: cc for cc, v in ch.items() if v and v[1] in FOURTEEN}


def messenger_cc_value(kind, v):
    """A panel knob's value as the Messenger's CC: (MSB, LSB) for a 14-bit
    knob, (value, None) otherwise -- messenger_value backwards, each switch
    position at the middle of its range so a firmware's edges cannot move it."""
    if kind == '14':
        x = int(round(max(0.0, min(1.0, float(v))) * 16383))
        return x >> 7, x & 0x7F
    if kind == 'tune':
        return messenger_cc_value('14', float(v) - _TUNE_TRIM)
    if kind == '7':
        return int(round(max(0.0, min(1.0, float(v))) * 127)), None
    if kind == 'foot':
        return FOOT_CC.index(int(v)) * 32 + 16, None
    if kind == 'track':
        return (32 if v < 0.5 else 96), None
    if kind == 'mode':
        return int(v) * 32 + 16, None
    if kind == 'onoff':
        return (127 if v else 0), None
    raise ValueError(kind)


def messenger_messages(panel, firmware='1.0.7+', knobs=None):
    """[(CC, value)] that set a Messenger's panel to `panel` -- every knob its
    chart carries (or just `knobs`), the coarse half of a 14-bit knob first, as
    the hardware reads them. What the Messenger has no CC for (GLIDE here, the
    MF-104M, which is another box) is not sent."""
    chart, _lsb = messenger_chart(firmware)
    out = []
    for cc, ent in sorted(chart.items()):
        if ent is None or (knobs is not None and ent[0] not in knobs):
            continue
        hi, lo = messenger_cc_value(ent[1], panel[ent[0]])
        out.append((cc, hi))
        if lo is not None:
            out.append((cc + 32, lo))
    return out


# Knobs by what moving one under a sounding note has to touch.
KNOB_ROW = ('cutoff', 'resonance', 'eg_amount', 'f_sustain', 'a_sustain')     # KN, per block
NOTE_ROW = ('kb_track', 'f_attack', 'f_decay', 'f_release', 'a_attack', 'a_decay',
            'a_release', 'mode', 'res_bass')                                      # FT, per note
TIMBRE = ('osc1_wave', 'osc2_wave', 'sub_wave', 'osc1_level', 'osc2_level',
          'sub_level', 'noise_level', 'osc1_octave', 'osc2_octave', 'osc2_freq', 'tune')         # the partials


# ---------------------------------------------------------------- MOD: pitch
# THE MOD SECTION'S F ENV -> OSC 2 FREQ, and LFO 1 -> OSC 2 FREQ. OSC 2 sounds
# at its ratio times 2^x(t) with x = A_env*e(t) + A_lfo*l(t): e the filter
# contour, l LFO 1, in octaves. The manual gives MOD AMOUNT as +-100% and not
# how far that is; four octaves is the choice until Ben's Messenger is
# recorded, and an octave for the LFO's own reach at full depth.
MOD_DESTS = ('1>2 FM', 'F ENV>OSC 2 FREQ', 'F ENV>OSC 2 WAVE', 'F ENV>SUB WAVE')
# MEASURED: MOD AMOUNT moves OSC 2 exactly 10 octaves a unit of knob (+-0.498
# octave at +-0.05) -- +-5 at full; LFO 1's full DEPTH on OSC 2 FREQ swings
# it about +-4 octaves. The first model had 4 and 1.
MOD_PITCH_OCTAVES = 5.0
LFO_PITCH_OCTAVES = 4.0


# ---------------------------------------------------------------- the first laws
# V1: what the panel's knobs meant before Ben's Messenger was measured -- kept
# to convert what was written in them (every patch, and any part's knobs saved
# in a session or a preset before this) to the hardware's positions for the
# SAME sound: through the physical quantity, the corner in Hz, the time in
# seconds, the feedback, the rate, the pitch, onto the knob that gives it now.
V1_TRI, V1_SQUARE = 0.4, 0.6
V1_K_MAX = K_MAX
V1_MOD_PITCH_OCTAVES, V1_LFO_PITCH_OCTAVES = 4.0, 1.0


def v1_knob_time(v):
    return 0.001 * 10000.0 ** _clip01(v)


def v1_knob_cutoff(v):
    return 20.0 * 1000.0 ** _clip01(v)


def v1_knob_lfo_rate(v):
    return 0.05 * 240.0 ** _clip01(v)


V2_TRI, V2_SQUARE = 0.35, 0.635


def _wave_v2(v):
    """A WAVESHAPE position, the second model's landmarks to these."""
    xs, ys = (0.0, V2_TRI, SAW, V2_SQUARE, 1.0), (0.0, TRI, SAW, SQUARE, 1.0)
    return float(np.interp(_clip01(v), xs, ys))


def _wave_sweeps(knobs, ctx, out, remap, cube=True):
    """A SWEEP OF THE WAVESHAPE (LFO 1 on OSC 1 WAVE, or F ENV on OSC 2 WAVE)
    moves the KNOB, and the landmarks moved under it: its span is rescaled to
    cover the same shapes, the remapped ends of the old sweep -- exact at its
    ends, not between them, the remap being piecewise. `cube`: the new depth
    in the measured laws (lfo_wave_reach, MOD_WAVE_REACH), else still in the
    first models' (for convert_v4 to take on)."""
    if 'lfo1_depth' in knobs and int(ctx.get('lfo1_dest', 0)) == 2 and 'osc1_wave' in ctx:
        c, h = _clip01(ctx['osc1_wave']), bipolar(knobs['lfo1_depth'], V4_LFO_WAVE_SPAN / 2.0)
        nh = math.copysign((remap(c + abs(h)) - remap(c - abs(h))) / 2.0, h)
        # the depth to LFO 1's own law (cube), or still the first models'
        # (convert_v3: convert_v4 then takes it on)
        out['lfo1_depth'] = lfo_wave_knob(nh) if cube else 0.5 + nh / (V4_LFO_WAVE_SPAN / 2.0) / 2.0
    if 'mod_amount' in knobs and int(ctx.get('mod_dest', 1)) == 2 and 'osc2_wave' in ctx:
        c, h = _clip01(ctx['osc2_wave']), bipolar(knobs['mod_amount'], V4_MOD_WAVE_SPAN / 2.0)
        nh = remap(c + h) - remap(c)
        out['mod_amount'] = 0.5 + (nh / MOD_WAVE_REACH if cube else nh / (V4_MOD_WAVE_SPAN / 2.0)) / 2.0
    for k in ('osc1_wave', 'osc2_wave'):
        if k in out:
            out[k] = remap(out[k])


def _wave_v1(v):
    """A WAVESHAPE position, first landmarks to measured: piecewise linear,
    so each region's shape is the same shape at the same fraction across it."""
    xs, ys = (0.0, V1_TRI, SAW, V1_SQUARE, 1.0), (0.0, TRI, SAW, SQUARE, 1.0)
    return float(np.interp(_clip01(v), xs, ys))


def convert_v1(knobs, context=None):
    """Knob positions written in the first model's units, as the measured
    panel's for the same sound. `knobs` may be a whole panel or a few knobs;
    `context` supplies the switches a knob's meaning depends on (MOD and LFO
    1's destinations) when `knobs` does not carry them."""
    ctx = dict(context or {})
    ctx.update(knobs)
    out = dict(knobs)
    for k in ('f_decay', 'f_release', 'a_decay', 'a_release'):
        if k in out:
            out[k] = time_knob(v1_knob_time(out[k]))
    for k in ('f_sustain', 'a_sustain'):     # the first model's sustain was the level
        if k in out:
            out[k] = sustain_knob(float(out[k])) if float(out[k]) > 0.0 else 0.0
    # ATTACK keeps its t90 (0.834 of the first model's time, charging to 1.5):
    # the curve is the hardware's now, so its corner comes a little later
    for k in ('f_attack', 'a_attack'):
        if k in out:
            t90 = 0.834 * v1_knob_attack(out[k])
            out[k] = attack_knob(t90 * _ATK_TO_1 / _ATK_T90)
    if 'cutoff' in out:
        out['cutoff'] = cutoff_knob(v1_knob_cutoff(out['cutoff']))
    if 'resonance' in out:
        v = _clip01(out['resonance'])
        out['resonance'] = (V1_K_MAX * v / RES_PER_UNIT if v <= 0.9          # the same feedback
                            else SELF_FROM + (v - 0.9) / 0.1 * (1.0 - SELF_FROM))   # the singing tenth
    if 'eg_amount' in out:
        out['eg_amount'] = eg_knob(bipolar(out['eg_amount'], V1_EG_OCTAVES))
    if 'lfo1_rate' in out:
        out['lfo1_rate'] = lfo_rate_knob(v1_knob_lfo_rate(out['lfo1_rate']))
    if 'mod_amount' in out and int(ctx.get('mod_dest', 1)) == 1:
        out['mod_amount'] = 0.5 + (out['mod_amount'] - 0.5) * V1_MOD_PITCH_OCTAVES / MOD_PITCH_OCTAVES
    if 'mod_amount' in out and int(ctx.get('mod_dest', 1)) == 0:
        out['mod_amount'] = fm_index_knob(bipolar(out['mod_amount'], V1_FM_INDEX_MAX))
    if 'lfo1_depth' in out and int(ctx.get('lfo1_dest', 0)) == 1:
        out['lfo1_depth'] = lfo_pitch_knob(bipolar(out['lfo1_depth'], V1_LFO_PITCH_OCTAVES))
    if 'lfo1_depth' in out and int(ctx.get('lfo1_dest', 0)) == 0:
        out['lfo1_depth'] = lfo_cut_knob(bipolar(out['lfo1_depth'], V4_LFO_OCTAVES))
    if 'lfo1_shape' in out and int(out['lfo1_shape']) in (1, 2):    # its saw rose: the ramp
        out['lfo1_shape'] = 3 - int(out['lfo1_shape'])
    _wave_sweeps(knobs, ctx, out, _wave_v1)
    if 'kb_track' in out:                   # OFF or 1:1: the first model's 2/3 is not
        out['kb_track'] = 1.0 if float(out['kb_track']) >= 0.5 else 0.0   # a setting the hardware has
    return out



def convert_v2(knobs):
    """A panel written in the second model's contours (synth_units 2) as these:
    each decay and release keeps its time constant, each sustain its level."""
    out = dict(knobs)
    for k in ('f_decay', 'f_release', 'a_decay', 'a_release'):
        if k in out:
            out[k] = time_knob(v2_knob_time(out[k]))
    for k in ('f_attack', 'a_attack'):       # the second model's own attack law
        if k in out:
            t90 = 0.834 * v1_knob_attack(out[k])
            out[k] = attack_knob(t90 * _ATK_TO_1 / _ATK_T90)
    for k in ('f_sustain', 'a_sustain'):
        if k in out:
            out[k] = sustain_knob(float(out[k])) if float(out[k]) > 0.0 else 0.0
    return out


def convert_v3(knobs, context=None):
    """A panel written in the second waveshape (synth_units 3 and before: the
    triangle at 0.35, the square at 0.635) as this: each wave its landmark,
    and 1 -> 2 FM's MOD AMOUNT its index (the first models' linear 3 at the
    ends)."""
    ctx = dict(context or {})
    ctx.update(knobs)
    out = dict(knobs)
    _wave_sweeps(knobs, ctx, out, _wave_v2, cube=False)
    if 'mod_amount' in out and int(ctx.get('mod_dest', 1)) == 0:      # 1 -> 2 FM's index
        out['mod_amount'] = fm_index_knob(bipolar(out['mod_amount'], V1_FM_INDEX_MAX))
    if 'sub_wave' in out:
        out['sub_wave'] = _sub_v2(out['sub_wave'])
    return out


def _sub_v2(v):
    """A SUB WAVE position, the first models' square (0.4) to this one's."""
    return float(np.interp(_clip01(v), (0.0, V2_SUB_SQUARE, 1.0), (0.0, SUB_SQUARE, 1.0)))


def convert_v4(knobs, context=None):
    """A panel written before LFO 1 and MOD on the waveshapes were measured
    (synth_units 4 and before: LFO 1's depth linear, 3 octaves on the cutoff,
    4 on the pitch and a quarter of the knob on a wave either way at the
    ends, every shape both ways; MOD's reach on a wave half its travel) as
    this: each depth its swing. The triangle is exact; a sawtooth (which
    rose) becomes the ramp."""
    ctx = dict(context or {})
    ctx.update(knobs)
    out = dict(knobs)
    if 'lfo1_depth' in out and int(ctx.get('lfo1_dest', 0)) == 0:
        out['lfo1_depth'] = lfo_cut_knob(bipolar(out['lfo1_depth'], V4_LFO_OCTAVES))
    if 'lfo1_depth' in out and int(ctx.get('lfo1_dest', 0)) == 1:
        out['lfo1_depth'] = lfo_pitch_knob(bipolar(out['lfo1_depth'], V4_LFO_PITCH_OCTAVES))
    if 'lfo1_depth' in out and int(ctx.get('lfo1_dest', 0)) in (2, 3):
        out['lfo1_depth'] = lfo_wave_knob(bipolar(out['lfo1_depth'], V4_LFO_WAVE_SPAN / 2.0))
    if 'mod_amount' in out and int(ctx.get('mod_dest', 1)) in (2, 3):
        out['mod_amount'] = 0.5 + bipolar(out['mod_amount'], V4_MOD_WAVE_SPAN / 2.0) / MOD_WAVE_REACH / 2.0
    if 'lfo1_shape' in out and int(out['lfo1_shape']) in (1, 2):
        out['lfo1_shape'] = 3 - int(out['lfo1_shape'])
    return out

PANEL = convert_v1(PANEL_V1)
MG = 128                 # the grid the kernel reads rows on (synthkernel MOOG_GRID)


def pitch_params(panel):
    """What the pitch rows need of the panel, or None if nothing moves OSC 2's
    pitch: (A_env, fA, fD, fS, fR, A_lfo, lfo_hz, lfo_shape, lfo_reset).
    SYNC turns OSC 2 FREQ into a spectrum, not a pitch -- not these rows."""
    if panel['sync']:
        return None
    ae = bipolar(panel['mod_amount'], MOD_PITCH_OCTAVES) if int(panel['mod_dest']) == 1 else 0.0
    al = lfo_pitch_octaves(panel['lfo1_depth']) if int(panel['lfo1_dest']) == 1 else 0.0
    if ae == 0.0 and al == 0.0:
        return None
    return (ae, knob_attack(panel['f_attack']), knob_time(panel['f_decay']),
            sustain_target(panel['f_sustain']), knob_time(panel['f_release']),
            al, knob_lfo_rate(panel['lfo1_rate']), float(int(panel['lfo1_shape'])),
            1.0 if panel['lfo1_reset'] else 0.0)


# ---------------------------------------------------------------- MOD: shape
# THE WAVESHAPES THAT MOVE: F ENV -> OSC 2 WAVE and -> SUB WAVE (the MOD
# section), LFO 1 -> OSC 1 WAVE and -> SUB WAVE, and the SYNC SWEEP -- OSC 2
# FREQ moved (by the contour or LFO 1) while it is synced, which moves the
# synced spectrum and not the pitch. MOD AMOUNT, measured (the contour held at
# full, the moved wave read off its spectrum), is linear and reaches the whole
# WAVESHAPE travel either way at full: 2.02 of it a unit of knob at every
# amount 0.55-0.8. (The first model meant that and reached half: its span was
# read as +-SPAN/2.) LFO 1's reach is its cube (lfo_wave_reach).
MOD_WAVE_REACH = 1.0
V4_MOD_WAVE_SPAN = 1.0
SHAPE_K = OSC_HARMONICS          # coefficients per oscillator per grid point
SHAPE_W = 25                     # shape_params' length


def shape_flags(panel):
    """Which oscillators' shapes move: FT_SHAPE bits."""
    f = 0
    amt = panel['mod_amount'] != 0.5
    dep = panel['lfo1_depth'] != 0.5
    md, ld = int(panel['mod_dest']), int(panel['lfo1_dest'])
    if (md == 2 and amt) or (panel['sync'] and ((md == 1 and amt) or (ld == 1 and dep))):
        f |= FT_SHAPE[OSC2]
    if (md == 3 and amt) or (ld == 3 and dep):
        f |= FT_SHAPE[SUB]
    if ld == 2 and dep:
        f |= FT_SHAPE[OSC1]
    return f


def shape_params(panel):
    """What the shape rows need of the panel, as one vector (SHAPE_W)."""
    md, ld = int(panel['mod_dest']), int(panel['lfo1_dest'])
    pp = pitch_params(dict(panel, sync=False))      # the sweep's ratio, if synced
    v = np.zeros(SHAPE_W)
    v[0] = shape_flags(panel)
    v[1], v[2], v[3] = panel['osc1_wave'], panel['osc2_wave'], panel['sub_wave']
    v[4] = md if md in (2, 3) else 0
    v[5] = bipolar(panel['mod_amount'], MOD_WAVE_REACH)
    v[6] = {2: 1, 3: 3}.get(ld, 0)
    v[7] = lfo_wave_reach(panel['lfo1_depth'])
    v[8], v[9], v[10] = knob_lfo_rate(panel['lfo1_rate']), int(panel['lfo1_shape']), 1.0 if panel['lfo1_reset'] else 0.0
    v[11], v[12] = knob_attack(panel['f_attack']), knob_time(panel['f_decay'])
    v[13], v[14] = sustain_target(panel['f_sustain']), knob_time(panel['f_release'])
    v[15] = (osc_ratio(panel, OSC2) / osc_ratio(panel, OSC1)) if panel['sync'] else 0.0
    if pp is not None and panel['sync']:
        v[16:25] = pp
    return v


def shape_values(g, a0, toff, par, sr):
    """At absolute samples g, for notes keyed at a0, released at toff: the
    shapes of OSC 1, OSC 2 and the SUB, and OSC 2's sync ratio (0: free).
    par is (..., SHAPE_W); everything broadcasts."""
    par = np.asarray(par, float)
    g = np.asarray(g, float)
    q = lambda i: par[..., i]
    t = (g - a0) / sr
    fe = np.where(t < 0.0, 0.0, _adsr_v(t, q(11), q(12), q(13), q(14), (toff - a0) / sr))
    tl = np.where(q(10) > 0.5, t, g / sr)
    ph = (tl * q(8)) % 1.0
    sh = q(9)
    lv = np.select([sh == 0, sh == 1, sh == 2],
                   [1.0 - 4.0 * np.abs(ph - 0.5), 2.0 * ph - 1.0, 1.0 - 2.0 * ph],
                   np.where(ph < 0.5, 1.0, -1.0))
    s1 = q(1) + np.where(q(6) == 1, q(7) * lv, 0.0)
    s2 = q(2) + np.where(q(4) == 2, q(5) * fe, 0.0)
    ss = q(3) + np.where(q(4) == 3, q(5) * fe, 0.0) + np.where(q(6) == 3, q(7) * lv, 0.0)
    P = tuple(par[..., 16 + i] for i in range(9))
    rt = pitch_ratio(g, a0, toff, P, sr)
    r = np.where(q(15) > 0.0, q(15) * rt, 0.0)
    clip = lambda x: np.clip(x, 0.0, 1.0)
    return clip(s1), clip(s2), clip(ss), r


def shape_rows_c(par, a0, toff, j0, nj, sr, mg, base, stride, offs, out, K=SHAPE_K):
    """The shape rows of several notes, written into `out` (synthkernel.c
    moog_shape_rows): what both renderers call."""
    import ctypes
    lib = _lib()
    if not getattr(lib, '_shape_typed', False):
        d, l, i4 = ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_int)
        lib.moog_shape_rows.argtypes = [ctypes.c_int, d, d, d, l, i4, ctypes.c_int, ctypes.c_double,
                                        ctypes.c_int, l, i4, i4, ctypes.POINTER(ctypes.c_float)]
        lib.moog_shape_rows.restype = None
        lib._shape_typed = True
    par = np.ascontiguousarray(np.asarray(par, np.float64).reshape(-1, SHAPE_W))
    n = len(par)
    f8 = lambda v: np.ascontiguousarray(np.broadcast_to(np.asarray(v, np.float64), (n,)))
    i8 = lambda v: np.ascontiguousarray(np.broadcast_to(np.asarray(v, np.int64), (n,)))
    i4 = lambda v, m=1: np.ascontiguousarray(np.broadcast_to(np.asarray(v, np.int32), (n * m,) if m == 1 else (n, m)).reshape(-1))
    a0, toff, j0, base = f8(a0), f8(toff), i8(j0), i8(base)
    nj, stride, offs = i4(nj), i4(stride), i4(offs, 3)
    P = lambda x, t: x.ctypes.data_as(ctypes.POINTER(t))
    lib.moog_shape_rows(n, P(par, ctypes.c_double), P(a0, ctypes.c_double), P(toff, ctypes.c_double),
                        P(j0, ctypes.c_long), P(nj, ctypes.c_int), int(mg), float(sr), int(K),
                        P(base, ctypes.c_long), P(stride, ctypes.c_int), P(offs, ctypes.c_int),
                        P(out, ctypes.c_float))


def shape_rows(par, a0, toff, end, sr, mg=MG):
    """A note's shape rows for the file renderer: (j0, n, stride, offsets,
    data) -- per grid point, for each oscillator whose shape moves, its K
    complex coefficients as float pairs; offsets -1 for one that does not."""
    flags = int(par[0])
    j0 = int(a0 // mg)
    n = max(2, int(-(-end // mg)) - j0 + 1)
    offs, nslot = [-1, -1, -1], 0
    for i, o in enumerate((OSC1, OSC2, SUB)):
        if flags & FT_SHAPE[o]:
            offs[i] = nslot * SHAPE_K * 2
            nslot += 1
    stride = nslot * SHAPE_K * 2
    out = np.zeros(n * stride, np.float32)
    shape_rows_c(par, a0, toff, j0, n, sr, mg, 0, stride, offs, out)
    return j0, n, stride, offs, out


def _adsr_v(t, A, D, S, R, toff):
    """adsr() with every argument an array (numpy broadcasting)."""
    t = np.asarray(t, float)
    def held(tt):
        before = tt < 0.0
        tt = np.maximum(tt, 0.0)
        att = ATTACK_TARGET * (1.0 - np.exp(-tt * _ATK_TO_1 / np.maximum(A, 1e-6)))
        dec = np.maximum(0.0, S + (1.0 - S) * np.exp(-(tt - A) / (np.maximum(D, 1e-6) / 4.0)))
        return np.where(before, 0.0, np.where(tt < A, att, dec))
    with np.errstate(over='ignore', invalid='ignore'):   # toff inf: held, rel unused
        rel = np.maximum(0.0, (held(toff) + EG_UNDER) * np.exp(-(t - toff) / (np.maximum(R, 1e-6) / 4.0))
                         - EG_UNDER)
    return np.where(t >= toff, rel, held(t))


def pitch_ratio(n, a0, toff, P, sr):
    """OSC 2's pitch ratio 2^x at absolute sample(s) n, for a note whose key
    went down at sample a0 and up at toff (np.inf while held); P from
    pitch_params, each field scalar or array. 1 before the key."""
    ae, fA, fD, fS, fR, al, lhz, lsh, lres = P
    t = (np.asarray(n, float) - a0) / sr
    x = ae * _adsr_v(t, fA, fD, fS, fR, (toff - a0) / sr)
    if np.any(np.asarray(al) != 0.0):
        tl = np.where(lres > 0.5, t, np.asarray(n, float) / sr)
        ph = (tl * lhz) % 1.0
        lv = np.select([lsh == 0, lsh == 1, lsh == 2],
                       [1.0 - 4.0 * np.abs(ph - 0.5), 1.0 - ph, ph],
                       np.where(ph < 0.5, 1.0, 0.0))
        x = x + al * lv
    return np.where(t < 0.0, 1.0, 2.0 ** x)


_GL_X, _GL_W = np.polynomial.legendre.leggauss(8)
_GL_X, _GL_W = 0.5 * (_GL_X + 1.0), 0.5 * _GL_W


def pitch_cells(g, a0, toff, P, sr, mg=MG):
    """For cells starting at absolute samples g (array): the integral of
    (ratio - 1) over each, in samples, and the ratio at each cell's start.
    8-point Gauss-Legendre on every piece between the cell's KINKS -- the key,
    the attack's end, the key's release, LFO 1's corners -- where the ratio
    turns a corner and a quadrature across it would not be exact. Both
    renderers build a note's rows from this one function, so they agree."""
    g = np.asarray(g, float)
    ae, fA, fD, fS, fR, al, lhz, lsh, lres = [np.broadcast_to(np.asarray(v, float), g.shape)
                                               for v in P]
    a0 = np.broadcast_to(np.asarray(a0, float), g.shape)
    toff = np.broadcast_to(np.asarray(toff, float), g.shape)
    ks = [a0, a0 + fA * sr, toff]
    # LFO 1's next corner after the cell's start (at most one per cell: 12 Hz
    # moves the phase 0.03 of a cycle in 128 samples)
    tl0 = np.where(lres > 0.5, (g - a0) / sr, g / sr)
    ph0 = (tl0 * np.maximum(lhz, 1e-9)) % 1.0
    nxt = np.where(ph0 < 0.5, 0.5, 1.0)
    ks.append(np.where(al != 0.0, g + (nxt - ph0) / np.maximum(lhz, 1e-9) * sr, np.inf))
    cuts = np.sort(np.stack([np.clip(k, g, g + mg) for k in ks]), axis=0)
    edges = np.concatenate([g[None], cuts, (g + mg)[None]])       # 6 x shape
    # every node of every piece at once: (5 pieces x 8 nodes) x shape
    e0, h = edges[:-1], edges[1:] - edges[:-1]
    nodes = e0[:, None] + _GL_X[None, :, None] * h[:, None] if g.ndim == 1 else \
        e0[:, None] + _GL_X.reshape((1, -1) + (1,) * g.ndim) * h[:, None]
    shp = nodes.shape
    Pb = tuple(np.broadcast_to(v, shp) for v in (ae, fA, fD, fS, fR, al, lhz, lsh, lres))
    rat = pitch_ratio(nodes, np.broadcast_to(a0, shp), np.broadcast_to(toff, shp), Pb, sr)
    wts = _GL_W.reshape((1, -1) + (1,) * g.ndim) * h[:, None]
    # summed piece by piece, node by node, in a fixed order: the same
    # additions for one note in the file as for many at once live
    total = np.zeros(g.shape)
    for i in range(rat.shape[0]):
        for k in range(rat.shape[1]):
            total = total + wts[i, k] * (rat[i, k] - 1.0)
    return total, pitch_ratio(g, a0, toff, (ae, fA, fD, fS, fR, al, lhz, lsh, lres), sr)


_LIB = [None]


def _lib():
    if _LIB[0] is None:
        import ctypes
        import blockrender
        lib = blockrender.ensure_lib()
        d = ctypes.POINTER(ctypes.c_double)
        lib.moog_pitch_cells.argtypes = [ctypes.c_int, d, d, d, d, ctypes.c_double, ctypes.c_int, d, d]
        lib.moog_pitch_cells.restype = None
        _LIB[0] = lib
    return _LIB[0]


def pitch_cells_c(g, a0, toff, P, sr, mg=MG):
    """pitch_cells, in C (synthkernel.c moog_pitch_cells): what both renderers
    use. P rows are notes (n x 9), or one tuple for every cell."""
    import ctypes
    g = np.ascontiguousarray(np.asarray(g, np.float64).ravel())
    n = len(g)
    bc = lambda v: np.ascontiguousarray(np.broadcast_to(np.asarray(v, np.float64), (n,)))
    Pm = np.asarray(P, np.float64)
    Pm = np.ascontiguousarray(np.broadcast_to(Pm.reshape(1, 9) if Pm.ndim == 1 else Pm.reshape(-1, 9), (n, 9)))
    a0, toff = bc(a0), bc(toff)
    dc = np.zeros(n); r = np.zeros(n)
    dp = lambda x: x.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
    _lib().moog_pitch_cells(n, dp(g), dp(a0), dp(toff), dp(Pm), float(sr), int(mg), dp(dc), dp(r))
    return dc, r


def coeff_rows(kind, s, r, K=OSC_HARMONICS):
    """c_k, k = 1..K, of WAVESHAPE (kind 0) or SUB WAVE (kind 1) at each shape
    in s, OSC 2 synced at ratio r where r > 0 -- in C (moog_coeff_rows), for a
    shape that moves: an (n, K) complex array."""
    import ctypes
    s = np.ascontiguousarray(np.asarray(s, np.float64).ravel())
    n = len(s)
    kind = np.ascontiguousarray(np.broadcast_to(np.asarray(kind, np.int32), (n,)))
    r = np.ascontiguousarray(np.broadcast_to(np.asarray(r, np.float64), (n,)))
    out = np.zeros(n * K * 2, np.float32)
    lib = _lib()
    if not getattr(lib, '_coeff_typed', False):
        d = ctypes.POINTER(ctypes.c_double)
        lib.moog_coeff_rows.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int), d, d, ctypes.c_int,
                                        ctypes.POINTER(ctypes.c_float)]
        lib.moog_coeff_rows.restype = None
        lib._coeff_typed = True
    lib.moog_coeff_rows(n, kind.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),
                        s.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                        r.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), int(K),
                        out.ctypes.data_as(ctypes.POINTER(ctypes.c_float)))
    o = out.reshape(n, K, 2).astype(np.float64)
    return o[..., 0] + 1j * o[..., 1]


def pitch_rows(P, a0, toff, end, sr, mg=MG):
    """A note's rows for the file renderer: (j0, C, R) on the grid from the
    cell holding its key to `end` -- C the extra phase in samples up to each
    grid point, R the ratio there."""
    j0 = int(a0 // mg)
    n = max(2, int(-(-end // mg)) - j0 + 1)
    g = (j0 + np.arange(n)) * float(mg)
    dc, r = pitch_cells_c(g, a0, toff, P, sr, mg)
    # the running sum one cell at a time, as live adds them block by block
    c = np.zeros(n)
    for i in range(1, n):
        c[i] = c[i - 1] + dc[i - 1]
    return j0, c, r


def _stage_integral(A_oct, p, q, tau, u0, u1):
    """Closed form of the integral of 2^{A(p + q e^{-u/tau})} over [u0, u1]
    (seconds): 2^{Ap} tau [ (u1-u0)/tau + sum (a^n - b^n)/(n n!) ], the
    exponential integral with its logarithm cancelled -- the reference the
    quadrature is checked against."""
    c = A_oct * q * math.log(2.0)
    a, b = c * math.exp(-u0 / tau), c * math.exp(-u1 / tau)
    tot, fa, fb, fact = 0.0, 1.0, 1.0, 1.0
    for n in range(1, 80):
        fa *= a; fb *= b; fact *= n
        tot += (fa - fb) / (n * fact)
    return 2.0 ** (A_oct * p) * tau * ((u1 - u0) / tau + tot)


def kn_row(panel):
    """The knob row (KN): what a knob moves while a note sounds -- and LFO 1,
    whose depth only reaches the cutoff when that is where it is sent."""
    on = int(panel['lfo1_dest']) == 0
    return [knob_cutoff(panel['cutoff']), knob_k(panel['resonance']),
            eg_octaves(panel['eg_amount']),
            sustain_target(panel['f_sustain']), sustain_target(panel['a_sustain']),
            knob_lfo_rate(panel['lfo1_rate']),
            lfo_cut_octaves(panel['lfo1_depth']) if on else 0.0,
            float(int(panel['lfo1_shape'])), 1.0 if panel['lfo1_reset'] else 0.0]


def self_hz(panel, f0):
    """Where the ladder's own sine stands for a key at f0: the cutoff the
    filter contour sustains at, key tracking and all."""
    return (knob_cutoff(panel['cutoff']) * (f0 / KB_REF_HZ) ** float(panel['kb_track'])
            * 2.0 ** (eg_octaves(panel['eg_amount']) * sustain_level(panel['f_sustain'])))


def release_span(panel):
    """How long a released note sounds: until the release, falling toward
    -EG_UNDER, crosses zero from the top (ln((1 + g)/g) time constants), and
    a time constant more. (Toward zero itself it never ended: 2.5 release
    times, -87 dB, was the cut -- at 1.5 a step to silence was heard.)"""
    tau = knob_tau(panel['a_release'])
    return tau * (math.log((1.0 + EG_UNDER) / EG_UNDER) + 1.0)


def gain_at(panel, f, t, t_off=None):
    """The reference for the kernel's per-partial gain at time t: the amp
    contour times the ladder at the cutoff the filter contour has reached,
    and the output stage. A partial at frequency f of a note at KB_REF_HZ
    (kbfac 1)."""
    fe = adsr(t, knob_attack(panel['f_attack']), knob_time(panel['f_decay']),
              sustain_target(panel['f_sustain']), knob_time(panel['f_release']), t_off)
    fc = knob_cutoff(panel['cutoff']) * 2.0 ** (eg_octaves(panel['eg_amount']) * fe)
    kn = kn_row(panel)
    if kn[6]:        # LFO 1 on the cutoff: from the key (KB RESET), as tested
        fc = fc * 2.0 ** (kn[6] * lfo(np.asarray(t, float) * kn[5], int(kn[7])))
    h = ladder_gain(f, np.maximum(fc, 1.0), knob_k(panel['resonance']),
                    int(panel['mode']), bool(panel['res_bass'])) * output_gain(f)
    return adsr(t, knob_attack(panel['a_attack']), knob_time(panel['a_decay']),
                sustain_target(panel['a_sustain']), knob_time(panel['a_release']), t_off) * h


def selftest():
    """Closed forms: the waves' Fourier series and the ladder's landmarks."""
    ok = True
    def check(name, cond, detail=''):
        nonlocal ok
        ok &= bool(cond)
        print("   %-58s %s  %s" % (name, 'ok' if cond else 'FAIL', detail))
    n = 64
    k = np.arange(1, n + 1)
    saw = 2 * np.abs(osc_spectrum(SAW, n))
    check("sawtooth is 2/(pi k)", np.allclose(saw, 2 / (np.pi * k), rtol=1e-9),
          "(err %.1e)" % np.max(np.abs(saw / (2 / (np.pi * k)) - 1)))
    sq = 2 * np.abs(osc_spectrum(SQUARE, n))
    ref = np.where(k % 2 == 1, 4 / (np.pi * k), 0.0)
    check("square is 4/(pi k), odd k only", np.allclose(sq, ref, atol=1e-12))
    tri = 2 * np.abs(osc_spectrum(TRI, n))
    ref = np.where(k % 2 == 1, 8 / (np.pi * k) ** 2, 0.0)
    check("triangle is 8/(pi k)^2, odd k only", np.allclose(tri, ref, atol=1e-12))
    d = 0.25
    pu = 2 * np.abs(_segments_coeffs(_pulse(d), n))
    check("a 25% pulse is (4/pi k)|sin(pi k d)|",
          np.allclose(pu, 4 / (np.pi * k) * np.abs(np.sin(np.pi * k * d)), atol=1e-12))
    fold = _fold(_skewed_triangle(0.5), 3.0)
    t = np.linspace(0, 1, 2001)[:-1]
    y = sum(2 * abs(c) * np.cos(2 * np.pi * (i + 1) * t + cmath.phase(c))
            for i, c in enumerate(_segments_coeffs(fold, 400)))
    direct = np.array([_reflect(3.0 * (4 * x - 1 if x < 0.5 else 3 - 4 * x)) for x in t])
    check("the folded triangle's series rebuilds the folded wave",
          np.max(np.abs(y - direct)) < 0.02, "(max err %.3f)" % np.max(np.abs(y - direct)))
    kk = 2.0
    check("LP4 passes 1/(1+k) at DC", abs(ladder_gain(1e-6, 1000, kk) - 1 / (1 + kk)) < 1e-6)
    check("RES BASS brings DC back to 1", abs(ladder_gain(1e-6, 1000, kk, LP4, True) - 1) < 1e-6)
    f = np.array([1e5, 2e5])
    s4 = 20 * np.log10(ladder_gain(f, 1000, 0.0))
    s2 = 20 * np.log10(ladder_gain(f, 1000, 0.0, LP2))
    check("LP4 falls 24 dB/oct, LP2 12", abs((s4[0] - s4[1]) - 24.08) < 0.05 and abs((s2[0] - s2[1]) - 12.04) < 0.05,
          "(%.2f, %.2f)" % (s4[0] - s4[1], s2[0] - s2[1]))
    ff = np.geomspace(100, 10000, 4001)
    pk = ff[np.argmax(ladder_gain(ff, 1000, 3.8))]
    # the peak sits a little under fc until k reaches 4 (987 Hz at k 3.8)
    check("near self-oscillation the peak sits at the cutoff", abs(pk / 1000 - 1) < 0.02, "(%.0f Hz)" % pk)
    hh = ladder(ff, 1000, 1.3, BP)
    check("|ladder| matches ladder_gain in every mode",
          all(np.allclose(np.abs(ladder(ff, 1000, 1.3, m, rb)), ladder_gain(ff, 1000, 1.3, m, rb))
              for m in (LP4, LP2, BP, HP) for rb in (False, True)))
    check("band-pass has nothing at DC or at the top", abs(hh[0]) < 0.05 and abs(hh[-1]) < 0.05)
    e = adsr(np.array([0.0, 0.1, 0.1 + 5.0]), 0.1, 1.0, 0.4, 0.5)
    check("ADSR: 0 at the key, 1 at A, S after the decay",
          abs(e[0]) < 1e-12 and abs(e[1] - 1) < 1e-9 and abs(e[2] - 0.4) < 1e-6)
    r = adsr(np.array([1.0, 1.125, 1.5]), 0.01, 0.1, 0.6, 0.5, t_off=1.0)
    check("ADSR: release starts at the held level, falls past zero, and stops there",
          abs(r[0] - 0.6) < 1e-6 and abs(r[1] - ((0.6 + EG_UNDER) * math.exp(-1) - EG_UNDER)) < 1e-9
          and r[2] == 0.0)
    saw = osc_spectrum(SAW, 64)
    check("SYNC at unison is the free wave",
          np.allclose(sync_spectrum(SAW, 1.0, 64), saw, atol=1e-12))
    s2 = sync_spectrum(SAW, 2.0, 64)
    check("...and at an octave, the wave an octave up: even harmonics only",
          np.allclose(s2[1::2], saw[:32], atol=1e-12) and np.allclose(s2[0::2], 0, atol=1e-12))
    s15 = 2 * np.abs(sync_spectrum(SAW, 1.5, 64))
    t = np.linspace(0, 1, 4001)[:-1]
    y = sum(2 * abs(c) * np.cos(2 * np.pi * (i + 1) * t + cmath.phase(c))
            for i, c in enumerate(sync_spectrum(SAW, 1.5, 800)))
    direct = 2 * ((1.5 * t) % 1.0) - 1
    direct -= direct.mean()                 # its DC (-1/6) is not a partial
    err = np.median(np.abs(y - direct))
    check("...and between, the synced wave itself", err < 0.02,
          "(r 1.5: median err %.3f; the fundamental is OSC 1's, at %.2f)" % (err, s15[0]))
    check("LFO 1's shapes: triangle both ways; falling saw, rising ramp, square one way",
          np.allclose(lfo([0, 0.25, 0.5], 0), [-1, 0, 1]) and np.allclose(lfo([0, 0.5], 1), [1, 0.5])
          and np.allclose(lfo([0, 0.5], 2), [0, 0.5]) and np.allclose(lfo([0.25, 0.75], 3), [1, 0]))
    check("RESONANCE sings alone from where the hardware does",
          self_amp(SELF_FROM) == 0.0 and abs(self_amp(1.0) - SELF_AMP) < 1e-12
          and self_amp(0.72) > 0 and abs(knob_k(SELF_FROM) - K_MAX) < 1e-12,
          "(from %.3f, where the feedback reaches K_MAX: measured, about 0.7)" % SELF_FROM)
    # the pitch rows' quadrature against the closed form, through attack,
    # decay and release, over cells that straddle both corners
    sr = 48000.0
    P = (3.0, 0.02, 0.3, 0.4, 0.2, 0.0, 1.0, 0.0, 0.0)
    a0, toff = 1000.3, 1000.3 + 0.5 * sr
    g = np.arange(0, 60000, MG, dtype=float)
    dc, _ = pitch_cells(g, a0, toff, P, sr)
    num = float(np.sum(dc))                          # integral of (R - 1), samples
    ae, fA, fD, fS, fR = P[:5]
    lo = ATTACK_TARGET * (1 - math.exp(-(toff - a0) / sr * _ATK_TO_1 / fA)) if (toff - a0) / sr < fA else         fS + (1 - fS) * math.exp(-((toff - a0) / sr - fA) / (fD / 4))
    T = (g[-1] + MG - a0) / sr
    rz = (fR / 4) * math.log((lo + EG_UNDER) / EG_UNDER)     # the release reaches zero
    tr = T - (toff - a0) / sr
    ref = (_stage_integral(ae, ATTACK_TARGET, -ATTACK_TARGET, fA / _ATK_TO_1, 0.0, fA)
           + _stage_integral(ae, fS, 1 - fS, fD / 4, 0.0, (toff - a0) / sr - fA)
           + _stage_integral(ae, -EG_UNDER, lo + EG_UNDER, fR / 4, 0.0, min(rz, tr))
           + max(0.0, tr - rz)) * sr
    ref -= (g[-1] + MG - a0)                          # the "- 1" over the note's span
    dcc, rc = pitch_cells_c(g, a0, toff, P, sr)
    Pl = (2.0, 0.01, 0.2, 0.5, 0.2, 0.7, 3.3, 0.0, 1.0)
    dl, _ = pitch_cells(g, a0, toff, Pl, sr); dlc, _ = pitch_cells_c(g, a0, toff, Pl, sr)
    check("the C cells are the numpy reference's",
          np.allclose(dcc, dc, rtol=1e-12, atol=1e-9) and np.allclose(dlc, dl, rtol=1e-12, atol=1e-9),
          "(worst %.1e samples, with and without LFO 1)" % max(np.abs(dcc - dc).max(), np.abs(dlc - dl).max()))
    qs = np.arange(Q + 1) / float(Q)
    cw = coeff_rows(0, qs, 0.0)
    cs = coeff_rows(1, qs, 0.0, SUB_HARMONICS)
    ew = max(np.abs(cw[i] - osc_spectrum(v, 64)).max() for i, v in enumerate(qs))
    es = max(np.abs(cs[i] - sub_spectrum(v, SUB_HARMONICS)).max() for i, v in enumerate(qs[:-1]))
    rs = [1.0, 1.37, 2.0, 2.5, 3.99, 7.3]
    ey = max(np.abs(coeff_rows(0, v, rr)[0] - sync_spectrum(v, rr, 64)).max()
             for v in (0.1, 0.35, 0.4475, 0.5, 0.5525, 0.635, 0.8) for rr in rs)
    check("the C waveshape coefficients are moog.py's, free and synced",
          ew < 1e-6 and es < 1e-6 and ey < 1e-6,
          "(every knob position: worst %.1e / %.1e sub / %.1e synced, float32)" % (ew, es, ey))
    check("the pitch rows' phase is the closed form's",
          abs(num / ref - 1) < 1e-9, "(%.1f samples of extra phase, rel err %.1e)" % (ref, abs(num / ref - 1)))
    check("the noise bank is white noise of NOISE_RMS",
          abs(np.sqrt(0.5 * (NOISE_AMP ** 2).sum()) - NOISE_RMS) < 1e-12
          and np.allclose(NOISE_AMP ** 2 / NOISE_HZ, NOISE_AMP[0] ** 2 / NOISE_HZ[0]),
          "(%d bands, 40 Hz to %.1f kHz, power per band as its width)"
          % (len(NOISE_HZ), NOISE_HZ[-1] / 1000))
    # THE CHART BACKWARDS: a panel sent to a Messenger and read back as the
    # Messenger would send it lands on the same knobs -- 14-bit to 1/16383,
    # every switch on its own position -- on either firmware's chart.
    import random
    rnd = random.Random(7)
    worst, bad = 0.0, []
    for fw in FIRMWARES:
        chart, lsb = messenger_chart(fw)
        for _ in range(50):
            pan = dict(PANEL)
            for knob, kind in (v for v in chart.values() if v):
                pan[knob] = (rnd.random() if kind in ('14', '7') else
                             rnd.uniform(_TUNE_TRIM, 1.0) if kind == 'tune' else   # what the hardware reaches
                             rnd.choice((4, 8, 16, 32)) if kind == 'foot' else
                             rnd.choice((0.0, 1.0)) if kind == 'track' else
                             rnd.randrange(4) if kind == 'mode' else rnd.random() < 0.5)
            got, msb = {}, {}
            for cc, val in messenger_messages(pan, fw):
                if cc in lsb:
                    knob, kind = chart[lsb[cc]]
                    got[knob] = messenger_value(kind, msb[lsb[cc]], val)
                elif chart.get(cc):
                    knob, kind = chart[cc]
                    msb[cc] = val
                    got[knob] = messenger_value(kind, val)
            for knob, v in got.items():
                kind = next(e[1] for e in chart.values() if e and e[0] == knob)
                if kind in ('14', '7', 'tune'):
                    worst = max(worst, abs(v - pan[knob]) * (127 if kind == '7' else 16383))
                elif v != pan[knob]:
                    bad.append((fw, knob))
    check("a panel sent to a Messenger reads back as itself",
          worst <= 0.5 + 1e-9 and not bad and ('sub_wave', '14') == MESSENGER_CC_PRE107[11],
          "(half a step at worst, %d switches wrong; SUB WAVE on CC71, or CC11 before 1.0.7)" % len(bad))
    return ok


if __name__ == '__main__':
    import sys
    sys.exit(0 if selftest() else 1)
