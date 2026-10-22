#!/usr/bin/env python3
"""The Mellotron's "3 Violins" tape (GS 50.24 "Tron Strings"): our string
section, three violins, coloured as the tape is.

    python3 examples/mellotron_fit.py          measure the tape's notes, fit ours to them

THE REFERENCE is menegass' "MELLOTRON VIOLIN" pack (Freesound 6815, CC0;
sources.md): twelve notes, C4-B4 at A440, 0.6 s each -- long enough for the
tape's COLOUR, not for its transport (wow, flutter, the 8 s run-out), which
tonelib.MellotronMixin builds from the M400's mechanism instead.

Both sides read by absolute frequency, egtr_fit's envelope: every harmonic
of every note to 8 kHz over 0.1-0.45 s, each note's level removed (the mean
over 150 Hz-3 kHz), third-octave medians; ours from the class's own
harmonic levels at the same pitches. Fitted: the low-pass the tape and its
replay head put over the violins (lowpass_hz, lowpass_order), and the
violins' own top (tonal_dampening, the body's bore_corner_hz): the tape's are
brighter at 3-5 kHz than ours before they are cut.
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

from drum_fit import read  # noqa: E402
import voicefit as V  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs/freesound/mellotron_violin")
BANDS = 150.0 * 2 ** (np.arange(0, 17) / 3.0)          # 150 Hz .. 6 kHz
TOP_HZ = 8000.0


def pool(f0s, ladders):
    out = [[] for _ in BANDS]
    for f0, L in zip(f0s, ladders):
        hz = f0 * np.arange(1, len(L) + 1)
        ref = (hz > 150) & (hz < 3000)
        L = L - 10 * np.log10(np.mean(10 ** (L[ref] / 10)))
        for h, d in zip(hz, L):
            k = int(np.argmin(np.abs(np.log2(h / BANDS))))
            if abs(np.log2(h / BANDS[k])) <= 1 / 6.0:
                out[k].append(d)
    return np.array([np.median(v) if len(v) >= 3 else np.nan for v in out])


def measured():
    f0s, lads = [], []
    for p in sorted(glob.glob(os.path.join(REFS, "*.wav"))):
        x, sr = read(p)
        x = x.mean(1) if x.ndim > 1 else x
        seg = x[int(0.1 * sr):int(0.45 * sr)]
        f0 = V.detect_f0(seg, sr, 150, 2000)
        n = int(TOP_HZ / f0)
        S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 4 * len(seg)))
        f = np.fft.rfftfreq(4 * len(seg), 1 / sr)
        L = []
        for m in range(1, n + 1):
            w = (f > f0 * (m - 0.3)) & (f < f0 * (m + 0.3))
            L.append(20 * np.log10(S[w].max() + 1e-12))
        f0s.append(f0); lads.append(np.array(L))
    return f0s, lads


def ours(cls, f0, vel=100):
    pr = cls(f0, 0.0, (vel / 127.0) ** 2, 1.0)
    n = int(TOP_HZ / f0)
    a = np.array([abs(pr.harmonic_volume(m)) for m in range(1, n + 1)])
    return 20 * np.log10(np.maximum(a, 1e-12))


def base_class(note=64):
    import patch_map as P
    return P.property_class_for_note(48, note)


def main(argv):
    from scipy.optimize import minimize
    f0s, lads = measured()
    R = pool(f0s, lads)
    base = base_class()
    # THE VIOLIN'S BODY is one resonance (2.3 kHz, 1.4 wide) over a floor 26 dB
    # down: above ~3 kHz only the floor is left, where the tape's violins carry
    # on to ~5 kHz and are then cut steeply. So the resonance moves (its centre,
    # width), the floor lifts, and a low-pass cuts: the tape and its head
    knobs = ("formant_hz", "formant_bw", "formant_floor", "lowpass_hz", "lowpass_order")
    g0 = base.formants[0][2]

    def attrs(v):
        return dict(formants=((v[0], v[1], g0),), formant_floor=v[2], lowpass_hz=v[3], lowpass_order=v[4])

    def err(v):
        if v[0] < 800 or v[1] < 200 or not 0.005 < v[2] < 0.9 or v[3] < 1500 or not 0.5 < v[4] < 16:
            return 99.0
        cls = type("Fit", (base,), attrs(v))
        M = pool(f0s, [ours(cls, f) for f in f0s])
        ok = np.isfinite(R) & np.isfinite(M)
        d = M[ok] - R[ok]
        return float(np.mean(np.abs(d - d.mean())))
    x0 = np.array([base.formants[0][0], base.formants[0][1], base.formant_floor, 5500.0, 6.0])
    e_none = (lambda M: float(np.nanmean(np.abs((M - R) - np.nanmean(M - R)))))(pool(f0s, [ours(base, f) for f in f0s]))
    r = minimize(err, x0, method="Nelder-Mead", options=dict(xatol=1e-3, fatol=1e-3, maxfev=400))
    cls = type("Fit", (base,), attrs(r.x))
    M = pool(f0s, [ours(cls, f) for f in f0s])
    M0 = pool(f0s, [ours(base, f) for f in f0s])
    print("  %d notes, C4-B4; ours (%s) as it is misses %.2f dB, fitted %.2f" % (len(f0s), base.__name__, e_none, r.fun))
    for k, v in zip(knobs, r.x):
        print("    %s = %.4g" % (k, v))
    sh = lambda A: np.nanmean(A - R)
    print("   band Hz  " + " ".join("%5.0f" % c for c in BANDS))
    print("   tape     " + " ".join("%5.0f" % q if np.isfinite(q) else "   --" for q in R))
    print("   ours     " + " ".join("%5.0f" % q if np.isfinite(q) else "   --" for q in M0 - sh(M0)))
    print("   fitted   " + " ".join("%5.0f" % q if np.isfinite(q) else "   --" for q in M - sh(M)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
