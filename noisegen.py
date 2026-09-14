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
    y = np.fft.irfft(X * g, n)
    p = float(np.sqrt((y * y).mean()))
    return (y / p).astype(np.float32) if p > 1e-12 else np.zeros(n, np.float32)


def envelope(n, sr, attack=0.003, release=0.012):
    """Open fast, hold, close fast. A constriction is held and then released;
    it does not ring, so there is no decay to model -- which is why the burst
    inherited the wrong envelope when it was pretending to be a note."""
    e = np.ones(n, np.float32)
    a = min(int(attack * sr), n // 2)
    r = min(int(release * sr), n // 2)
    if a > 0: e[:a] = np.linspace(0.0, 1.0, a, dtype=np.float32)
    if r > 0: e[n - r:] = np.linspace(1.0, 0.0, r, dtype=np.float32)
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
