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
import math

import numpy as np

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


TRI, SAW, SQUARE = 0.4, 0.5, 0.6       # the landmarks on WAVESHAPE (0 = CCW)
FOLD_MAX = 5.0                         # the folder's gain at fully CCW
PULSE_MIN = 0.02                       # the narrowest pulse, at fully CW
Q = 250                                # knob positions cached: 250 steps put
                                       # every landmark (0.4, 0.5, 0.6) on one


@functools.lru_cache(maxsize=4 * Q)
def _osc_cached(q, n):
    s = q / float(Q)
    if s < TRI:                                    # folded triangle
        g = 1.0 + (FOLD_MAX - 1.0) * (TRI - s) / TRI
        return _segments_coeffs(_fold(_skewed_triangle(0.5), g), n)
    if s < SAW:                                    # triangle skewed to a saw
        return _segments_coeffs(_skewed_triangle(0.5 + 0.5 * (s - TRI) / (SAW - TRI)), n)
    if s < SQUARE:                                 # saw crossfaded to square
        a = (s - SAW) / (SQUARE - SAW)
        return ((1.0 - a) * _segments_coeffs(_skewed_triangle(1.0), n)
                + a * _segments_coeffs(_pulse(0.5), n))
    d = 0.5 - (0.5 - PULSE_MIN) * (s - SQUARE) / (1.0 - SQUARE)
    return _segments_coeffs(_pulse(d), n)


def osc_spectrum(shape, n):
    """OSC 1 or 2 at WAVESHAPE `shape` (0 = fully CCW, 1 = fully CW): the
    complex coefficients c_k of harmonics 1..n. The partial for harmonic k has
    amplitude 2|c_k| and phase arg c_k, on a wave that swings +-1."""
    q = int(round(max(0.0, min(1.0, shape)) * Q))
    return _osc_cached(q, int(n)).copy()


SUB_SQUARE = 0.4                       # SUB WAVE's square, at ~11 o'clock


@functools.lru_cache(maxsize=4 * Q)
def _sub_cached(q, n):
    s = q / float(Q)
    if s < SUB_SQUARE:                             # triangle clipped to a square
        u = s / SUB_SQUARE
        g = 1.0 / max(1e-3, 1.0 - u)               # gain 1 (triangle) -> 1000
        return _segments_coeffs(_clip(_skewed_triangle(0.5), g), n)
    d = 0.5 - (0.5 - PULSE_MIN) * (s - SUB_SQUARE) / (1.0 - SUB_SQUARE)
    return _segments_coeffs(_pulse(d), n)


def sub_spectrum(shape, n):
    """The SUB OSC at SUB WAVE `shape`: c_k of ITS harmonics 1..n (at half of
    OSC 1's frequency)."""
    q = int(round(max(0.0, min(1.0, shape)) * Q))
    return _sub_cached(q, int(n)).copy()


# ---------------------------------------------------------------- the ladder
LP4, LP2, BP, HP = 0, 1, 2, 3
MODES = ('4P LOW PASS', '2P LOW PASS', 'BAND PASS', 'HIGH PASS')
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
    g = 1.0 / (1.0 + 1j * np.asarray(f, float) / fc)
    u = 1.0 / (1.0 + k * g ** 4)
    if mode == LP4:
        h = g ** 4 * u
    elif mode == LP2:
        h = g ** 2 * u
    elif mode == BP:
        h = 4.0 * g ** 2 * (1.0 - g) ** 2 * u
    else:
        h = (1.0 - g) ** 2 * u
    if res_bass and mode in (LP4, LP2):
        h = h * (1.0 + k)
    return h


def ladder_gain(f, fc, k, mode=LP4, res_bass=False):
    """|H|, the magnitude alone -- what the kernel applies. The phase response
    is dropped, which only changes the wave's SHAPE, never what one hears,
    and is exact between partials at the same frequency."""
    x = np.asarray(f, float) / fc
    # (1 + jx)^4 = (1 - 6x^2 + x^4) + j(4x - 4x^3): |den| = |(1+jx)^4 + k|
    re4, im4 = 1.0 - 6.0 * x * x + x ** 4, 4.0 * x - 4.0 * x ** 3
    den = np.hypot(re4 + k, im4)
    if mode == LP4:
        num = 1.0
    elif mode == LP2:
        num = 1.0 + x * x                       # |(1+jx)^2|
    elif mode == BP:
        num = 4.0 * x * x                       # |4 (jx)^2|
    else:
        num = x * x * (1.0 + x * x)             # |(jx)^2 (1+jx)^2|
    h = num / den
    if res_bass and mode in (LP4, LP2):
        h = h * (1.0 + k)
    return h


# ---------------------------------------------------------------- envelopes
def adsr(t, A, D, S, R, t_off=None):
    """The contour at time t (s) after the key went down, released at t_off.

    Analog envelope generators charge and discharge a capacitor, so every
    stage is exponential. The attack charges toward 1.5 and is cut at 1 --
    which lands at exactly A seconds -- the decay falls toward S and the
    release toward 0, each with a time constant a quarter of its knob's time
    (98% of the way there by then). Stateless: the level at release is the
    ADSR's own value at t_off, so the kernel can evaluate any instant alone."""
    t = np.asarray(t, float)
    def held(tt):
        before = tt < 0.0                        # the key is not down yet
        tt = np.maximum(tt, 0.0)
        ta = max(A, 1e-6) / math.log(3.0)
        att = 1.5 * (1.0 - np.exp(-tt / ta))
        dec = S + (1.0 - S) * np.exp(-(tt - A) / (max(D, 1e-6) / 4.0))
        return np.where(before, 0.0, np.where(tt < A, att, dec))
    e = held(t)
    if t_off is not None:
        lo = held(np.asarray(t_off, float))
        rel = lo * np.exp(-(t - t_off) / (max(R, 1e-6) / 4.0))
        e = np.where(t >= t_off, rel, e)
    return e


# ---------------------------------------------------------------- the knobs
def knob_time(v):
    """ATTACK/DECAY/RELEASE: 1 ms fully CCW to 10 s fully CW, exponentially."""
    return 0.001 * 10000.0 ** max(0.0, min(1.0, v))


def knob_cutoff(v):
    """CUTOFF: 20 Hz fully CCW to 20 kHz fully CW, exponentially."""
    return 20.0 * 1000.0 ** max(0.0, min(1.0, v))


def knob_k(v):
    """RESONANCE: the ladder's feedback, 0 to K_MAX."""
    return K_MAX * max(0.0, min(1.0, v))


EG_OCTAVES = 7.0    # EG AMOUNT fully CW opens the cutoff this far at the peak
KB_REF_HZ = 261.6256   # key tracking pivots on middle C, the 8' bottom key


def cutoff_at(fc0, note_hz, track):
    """KB TRACKING: the cutoff follows the key (track 1 = 1 V/oct, 2/3, 0)."""
    return fc0 * (note_hz / KB_REF_HZ) ** track


# The panel, as knob name -> default (0..1 unless a switch). A lead is a dict
# of overrides on these. Bipolar knobs (OSC 2 FREQ, TUNE, EG AMOUNT) are 0.5 at
# the centre detent.
PANEL = dict(
    osc1_octave=8, osc1_wave=SAW,
    osc2_octave=8, osc2_wave=SAW, osc2_freq=0.5, tune=0.5,
    sub_wave=SUB_SQUARE,
    osc1_level=1.0, osc2_level=0.0, sub_level=0.0, noise_level=0.0,
    cutoff=0.75, resonance=0.0, eg_amount=0.5, kb_track=1.0,
    mode=LP4, res_bass=False,
    f_attack=0.0, f_decay=0.4, f_sustain=0.5, f_release=0.3,
    a_attack=0.0, a_decay=0.4, a_sustain=1.0, a_release=0.3,
    glide=0.0,
)


def bipolar(v, span):
    """A centre-detent knob: 0.5 is 0, the ends are -span and +span."""
    return (max(0.0, min(1.0, v)) - 0.5) * 2.0 * span


def panel_of(props, overrides=None):
    """A voice's knobs: the panel's defaults, the voice's patch over them
    (its class's `messenger` dict), and a part's own settings over that."""
    out = dict(PANEL)
    out.update(getattr(props, 'messenger', None) or {})
    out.update(overrides or {})
    return out


# ---------------------------------------------------------------- to partials
# What the kernel is handed. Both renderers build a Moog note from these three,
# so they cannot disagree about what a knob means.
FT_W, KN_W = 12, 5      # must match FTW and KNW in synthkernel.c
FMAX_HZ = 12000.0       # highest partial: past it a saw's harmonics are 27 dB
                        # down at 440 Hz, the ladder usually has them lower
                        # still, and three oscillators' worth is the CPU bill
OSC_HARMONICS, SUB_HARMONICS = 64, 32
FOOT = {32: 0.25, 16: 0.5, 8: 1.0, 4: 2.0}      # OCTAVE, against 8'
SEMIS = 7.0                                     # TUNE and OSC 2 FREQ: +-7
OSC1, OSC2, SUB = 1, 2, 3


def partials(panel, f0, fmax=FMAX_HZ):
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
    out = []
    for osc, f, lvl, c in (
            (OSC1, f1, panel['osc1_level'], lambda n: osc_spectrum(panel['osc1_wave'], n)),
            (OSC2, f2, panel['osc2_level'], lambda n: osc_spectrum(panel['osc2_wave'], n)),
            (SUB, f1 * 0.5, panel['sub_level'], lambda n: sub_spectrum(panel['sub_wave'], n))):
        if lvl <= 0.0 or f <= 0.0:
            continue
        n = min(OSC_HARMONICS if osc != SUB else SUB_HARMONICS, int(fmax // f))
        if n < 1:
            continue
        cs = c(n)
        for k in range(1, n + 1):
            a = 2.0 * abs(cs[k - 1]) * lvl
            if a > 1e-9:
                out.append((osc, k, f * k, a, cmath.phase(cs[k - 1])))
    return out


def ft_row(panel, f0, krow):
    """The note's fixed row (FT): what is set at the key. Slot 10 keeps the
    key's own frequency, so a row can be rebuilt when a knob moves."""
    return [
        (f0 / KB_REF_HZ) ** float(panel['kb_track']),
        knob_time(panel['f_attack']), knob_time(panel['f_decay']), knob_time(panel['f_release']),
        knob_time(panel['a_attack']), knob_time(panel['a_decay']), knob_time(panel['a_release']),
        float(panel['mode']), 1.0 if panel['res_bass'] else 0.0, float(krow), float(f0), 0.0]


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
    for o, lvl, n, spec, shape in ((OSC1, 'osc1_level', OSC_HARMONICS, osc_spectrum, 'osc1_wave'),
                                   (OSC2, 'osc2_level', OSC_HARMONICS, osc_spectrum, 'osc2_wave'),
                                   (SUB, 'sub_level', SUB_HARMONICS, sub_spectrum, 'sub_wave')):
        m = osc == o
        if not m.any():
            continue
        c = spec(panel[shape], n)
        kk = np.clip(k[m], 1, n) - 1
        r = osc_ratio(panel, o)
        rt[m] = r
        w[m] = 2.0 * np.abs(c[kk]) * float(panel[lvl])
        ph[m] = np.angle(c[kk])
        w[m] = np.where(np.asarray(nf, float)[m] * r > fmax, 0.0, w[m])
    return w, ph, rt


# GM's SOUND CONTROLLERS, on a Moog: what a file's CC74/71/73/72/75 mean when
# the instrument is this one. Offsets from 64 (-1..+1) on the knobs they name,
# at the ranges midi.md gives every synth: cutoff +-2 octaves (0.2 of CUTOFF's
# ten), resonance +-half the knob, times x/+ 4 (0.15 of the knobs' four decades).
GM_SOUND = {'brightness': ('cutoff', 0.2), 'resonance': ('resonance', 0.5),
            'attack': ('a_attack', 0.15), 'release': ('a_release', 0.15),
            'decay': ('a_decay', 0.15)}


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


# Knobs by what moving one under a sounding note has to touch.
KNOB_ROW = ('cutoff', 'resonance', 'eg_amount', 'f_sustain', 'a_sustain')     # KN, per block
NOTE_ROW = ('kb_track', 'f_attack', 'f_decay', 'f_release', 'a_attack', 'a_decay',
            'a_release', 'mode', 'res_bass')                                      # FT, per note
TIMBRE = ('osc1_wave', 'osc2_wave', 'sub_wave', 'osc1_level', 'osc2_level',
          'sub_level', 'osc1_octave', 'osc2_octave', 'osc2_freq', 'tune')         # the partials


def kn_row(panel):
    """The knob row (KN): what a knob moves while a note sounds."""
    return [knob_cutoff(panel['cutoff']), knob_k(panel['resonance']),
            bipolar(panel['eg_amount'], EG_OCTAVES),
            float(panel['f_sustain']), float(panel['a_sustain'])]


def release_span(panel):
    """How long a released note sounds: 1.5 release times, -52 dB."""
    return 1.5 * knob_time(panel['a_release'])


def gain_at(panel, f, t, t_off=None):
    """The reference for the kernel's per-partial gain at time t: the amp
    contour times the ladder at the cutoff the filter contour has reached.
    A partial at frequency f of a note at KB_REF_HZ (kbfac 1)."""
    fe = adsr(t, knob_time(panel['f_attack']), knob_time(panel['f_decay']),
              panel['f_sustain'], knob_time(panel['f_release']), t_off)
    fc = knob_cutoff(panel['cutoff']) * 2.0 ** (bipolar(panel['eg_amount'], EG_OCTAVES) * fe)
    h = ladder_gain(f, np.maximum(fc, 1.0), knob_k(panel['resonance']),
                    int(panel['mode']), bool(panel['res_bass']))
    return adsr(t, knob_time(panel['a_attack']), knob_time(panel['a_decay']),
                panel['a_sustain'], knob_time(panel['a_release']), t_off) * h


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
    r = adsr(np.array([1.0, 1.5]), 0.01, 0.1, 0.6, 0.5, t_off=1.0)
    check("ADSR: release starts at the held level and falls 98%",
          abs(r[0] - 0.6) < 1e-6 and abs(r[1] / r[0] - math.exp(-4)) < 1e-9)
    return ok


if __name__ == '__main__':
    import sys
    sys.exit(0 if selftest() else 1)
