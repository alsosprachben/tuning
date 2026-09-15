#!/usr/bin/env python3
"""Band-limited noise bursts, for the sounds that are not made of partials.

Everything else in this renderer is a sum of sinusoidal partials, which is
right for anything with modes -- a string, a pipe, a plate. A fricative has
none. It is air made turbulent at a constriction, and its spectrum is
continuous: no fundamental, no series, no pitch.

Trying to build one out of partials produced exactly what the physics predicts
it must. Phase jitter on eight widely spaced partials leaves eight partials:
the measured burst had a periodicity of 0.9 and a spectrum of discrete peaks
835 Hz apart, which is a harmonic series, which is a beep. Pushing the partials
closer traded the band away instead (an /s/ centred at 1462 Hz rather than
6200) and still only reached 0.58.

So friction gets its own generator: white noise shaped by the band the
constriction makes. Filtering is done on the spectrum directly rather than with
a recursive filter, because a burst is 10-120 ms -- short enough that the
transform is free, and exact where a biquad would need care at these Qs.
"""
import os

import numpy as np

# How alike the two channels' noise is, 1.0 = one mono source panned. A choir
# section's consonants come from many mouths at slightly different times and
# reach the ears by different paths, so they are largely incoherent.
COHERENCE = float(os.environ.get('TUNING_CONSONANT_COHERENCE', '0.30'))

# THE MOUTH IS A BEAM AT THE TOP, and a listener in a hall is off its axis.
# A head radiates its high frequencies forward in a narrowing lobe, so by
# 6 kHz a seat out in the room hears several dB less of them than a microphone
# at the singer's lips would -- and in a choir, where the singers face where
# they are pointed rather than at you, that is the normal case.
#
# It matters here and almost nowhere else, because friction is the ONLY thing
# in a choir with energy up there: measured against the Lacrimosa's vowels the
# bursts ran +22 dB in the 4.5-6.5 kHz band and +27 dB above it. They owned
# the top of the spectrum, which is what "the consonants are too bright" is.
# A vowel has no 6 kHz to lose, so this shelf is specific to the bursts.
BEAM_HZ = float(os.environ.get('TUNING_CONSONANT_BEAM_HZ', '3000.0'))
BEAM_ORDER = float(os.environ.get('TUNING_CONSONANT_BEAM', '1.0'))


def burst(n, sr, centre_hz, bandwidth_hz, seed=0, tilt=0.0, shape=None):
    """`n` samples of noise with a Lorentzian band at centre_hz.

    Same band shape the formants use, so a consonant's /s/ and a vowel's F2 are
    described in one vocabulary.
    """
    if n < 4:
        return np.zeros(max(n, 0), np.float32)
    rng = np.random.default_rng(0xC0FFEE + int(seed))
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / sr)
    if shape is not None:
        # A SHAPE FROM THE TUBE. For a stop, the band is not a parameter: the
        # burst is excited at the constriction, so what filters it is the
        # cavity in FRONT of the closure, and vocaltube.burst() computes that
        # from the same tract the vowel is about to use. `shape` is that
        # response sampled on a reference grid; interpolate it onto this
        # burst's own, which varies with the burst's length.
        fr, gr = shape
        g = np.interp(f, fr, gr, left=gr[0], right=gr[-1])
    else:
        d = (f - float(centre_hz)) / max(1.0, float(bandwidth_hz) * 0.5)
        g = 1.0 / (1.0 + d * d)
    if tilt:
        g *= (np.maximum(f, 1.0) / max(1.0, float(centre_hz))) ** tilt
    # AND A TOP THAT FALLS AWAY. A band that runs flat to Nyquist is a splash:
    # the mouth does not radiate up there and neither should this.
    g *= 1.0 / (1.0 + (np.maximum(f, 1.0) / 9000.0) ** 3)
    beam = 1.0
    if BEAM_ORDER:
        bg = 1.0 / (1.0 + (np.maximum(f, 1.0) / BEAM_HZ) ** BEAM_ORDER)
        e0 = float((g * g).sum())
        g = g * bg
        # THE LOSS HAS TO SURVIVE THE NORMALISATION BELOW. Unit-RMS output is
        # what the gain calibration expects, but it would take a burst the
        # beam had just darkened and hand back its loudness -- an /s/, nearly
        # all of whose energy is above the corner, would come out dimmer and
        # exactly as loud. So the level the shelf removed is measured here and
        # reapplied after.
        beam = np.sqrt(float((g * g).sum()) / e0) if e0 > 0.0 else 1.0
    y = np.fft.irfft(X * g, n)
    p = float(np.sqrt((y * y).mean()))
    if p <= 1e-12:
        return np.zeros(n, np.float32)
    return (y * (beam / p)).astype(np.float32)


def envelope(n, sr, rise=0.33, fall=0.67):
    """A rounded hump, not a flat-topped burst.

    The first version opened in 3 ms, held flat and stopped: a hard-edged
    broadband transient, which is the recipe for a cymbal and is what it
    sounded like. Real friction starts gradually as the constriction closes,
    peaks, and then RELEASES INTO the vowel -- the noise is already fading
    while voicing begins, which is why a sung consonant blends instead of
    cracking. Raised-cosine both sides, weighted toward the fall so the tail
    overlaps the note that follows.
    """
    if n <= 0:
        return np.zeros(0, np.float32)
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    pk = rise / (rise + fall)
    e = np.empty(n, np.float32)
    up = t <= pk
    e[up] = 0.5 - 0.5 * np.cos(np.pi * t[up] / max(pk, 1e-6))
    e[~up] = 0.5 + 0.5 * np.cos(np.pi * (t[~up] - pk) / max(1.0 - pk, 1e-6))
    return e


def mix(L, R, n0, bursts, sr):
    """Add every burst overlapping the window [n0, n0+len(L)) into L/R.

    A burst is now a set of EMISSIONS -- one per singer in the section, plus
    one per room image -- because a consonant sung by a choir is made by all
    of them, from where they are standing, a few milliseconds apart. Each gets
    its own noise; the seats are incoherent and summing correlated copies
    would just rebuild the point source this is here to avoid.
    """
    if not bursts:
        return
    w = len(L)
    for i, b in enumerate(bursts):
        n, ctr, bw, shape, emits = b
        env = None
        for sl, sr_, gl, gr, tag in emits:
            if (sl + n <= n0 or sl >= n0 + w) and (sr_ + n <= n0 or sr_ >= n0 + w):
                continue
            if env is None:
                env = envelope(n, sr)
            y = burst(n, sr, ctr, bw, seed=i * 131 + tag, shape=shape) * env
            _add1(L, y, sl, n, n0, w, gl)
            _add1(R, y, sr_, n, n0, w, gr)


def _add1(buf, y, s, n, n0, w, g):
    if g == 0.0:
        return
    a = max(s, n0)
    z = min(s + n, n0 + w)
    if z <= a:
        return
    buf[a - n0:z - n0] += y[a - s:z - s] * g
