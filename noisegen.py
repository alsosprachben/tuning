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
import numpy as np


def burst(n, sr, centre_hz, bandwidth_hz, seed=0, tilt=0.0):
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
    d = (f - float(centre_hz)) / max(1.0, float(bandwidth_hz) * 0.5)
    g = 1.0 / (1.0 + d * d)
    if tilt:
        g *= (np.maximum(f, 1.0) / max(1.0, float(centre_hz))) ** tilt
    # AND A TOP THAT FALLS AWAY. A band that runs flat to Nyquist is a splash:
    # the mouth does not radiate up there and neither should this.
    g *= 1.0 / (1.0 + (np.maximum(f, 1.0) / 9000.0) ** 3)
    y = np.fft.irfft(X * g, n)
    p = float(np.sqrt((y * y).mean()))
    return (y / p).astype(np.float32) if p > 1e-12 else np.zeros(n, np.float32)


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
    """Add every burst overlapping the window [n0, n0+len(L)) into L/R."""
    if not bursts:
        return
    w = len(L)
    for i, b in enumerate(bursts):
        s, n, ctr, bw, amp, gl, gr = b
        if s + n <= n0 or s >= n0 + w:
            continue
        y = burst(n, sr, ctr, bw, seed=i) * envelope(n, sr) * amp
        a = max(s, n0); z = min(s + n, n0 + w)
        L[a - n0:z - n0] += y[a - s:z - s] * gl
        R[a - n0:z - n0] += y[a - s:z - s] * gr
