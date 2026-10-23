#!/usr/bin/env python3
"""GS 35.2 "FretlessBs3" and 35.3 "FretlessBs4": the fretless on one coil,
the neck's and the bridge's -- fitted to mrforfs' takes of each (CC0,
sources.md: a Harley Benton B-550FL, flatwounds, direct; five open strings
on the neck pickup, the bridge pickup and both).

    python3 examples/fretless_pickup_fit.py         fit both coils (and score 'both')

Run egtr_fit.py --stage first (it links the takes under idmt/staged/).

TWO MEASURES, BECAUSE EACH SEES HALF. Fretless Bs2 was fitted on the
envelope by absolute frequency (egtr_fit's --envelope), which starts where
a third-octave band holds five harmonics -- 200 Hz -- and so never sees the
open strings' fundamentals (31-98 Hz), which is where a bridge coil thins
the note: re both coils, the bridge take is 7 dB down at h1 and 6-9 dB up
at h5-h7. So the fit's objective is the sum of
  ladder    h1-h16 of each note, each its peak over 0.04-0.54 s past the
            strike, dB re the mean of h1-h6 (harmonics under 10x the 3-6 kHz
            floor left out), against the class's own harmonic levels
  envelope  egtr_fit's, bands to -60 dB
over the coil's position (pickup_points, one coil), its width, the source's
tilt and the low-pass. A difference re 'both' did not fit (4.4 dB): our two
point coils carve notches 30 dB deep that the takes never show.
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

from drum_fit import read  # noqa: E402
import egtr_fit as E  # noqa: E402
import tonelib as T  # noqa: E402

F0 = dict(B0=30.87, E1=41.2, A1=55.0, D2=73.42, G2=98.0)
NH = 16
KNOBS = ("pickup_points", "pickup_width", "tonal_dampening", "lowpass_hz", "lowpass_order")
BS2 = dict(tonal_dampening=2.315, lowpass_hz=455.7, lowpass_order=3.605)


def ladder(path, f0):
    x, sr = read(path)
    x = x.mean(1)
    k = int(np.argmax(np.abs(x)))
    seg = x[k + int(0.04 * sr):k + int(0.54 * sr)]
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 8 * len(seg)))
    f = np.fft.rfftfreq(8 * len(seg), 1 / sr)
    fl = np.median(S[(f > 3000) & (f < 6000)])
    L = []
    for m in range(1, NH + 1):
        pk = S[(f > f0 * (m - 0.2)) & (f < f0 * (m + 0.2))].max()
        L.append(20 * np.log10(pk) if pk > 10 * fl else np.nan)
    L = np.array(L)
    return L - np.nanmean(L[:6])


def ours(over, f0):
    pr = type("X", (T.FretlessBassProperties,), over)(f0, 0.0, 0.5, 1.0)
    L = 20 * np.log10(np.maximum([abs(pr.harmonic_volume(m)) for m in range(1, NH + 1)], 1e-12))
    return L - np.mean(L[:6])


def attrs(v):
    return dict(pickup_points=(v[0],) if v[0] else T.FretlessBassProperties.pickup_points,
                pickup_width=v[1], tonal_dampening=v[2], lowpass_hz=v[3], lowpass_order=v[4])


def scorer(pickup):
    paths = sorted(glob.glob(os.path.join(E.STAGED, "fretless_open_%s" % pickup, "*.wav")))
    R = {os.path.basename(p)[:2]: ladder(p, F0[os.path.basename(p)[:2]]) for p in paths}
    Renv, notes = E.env_obs(("fretless_open_%s" % pickup,))

    def parts(v):
        o = attrs(v)
        el = float(np.mean([np.nanmean(np.abs(ours(o, F0[n]) - R[n])) for n in R]))
        M = E.env_model(type("X", (T.FretlessBassProperties,), o), notes)
        ok = np.isfinite(Renv) & np.isfinite(M) & (Renv > -60)
        d = M[ok] - Renv[ok]
        return el, float(np.mean(np.abs(d - d.mean())))
    return parts


def fit(pickup, q0):
    from scipy.optimize import minimize
    parts = scorer(pickup)

    def err(v):
        if not ((v[0] == 0 or 0.03 < v[0] < 0.4) and 0.0 <= v[1] < 0.1 and 0.3 < v[2] < 4
                and 150 < v[3] < 3000 and 0.5 < v[4] < 6):
            return 99.0
        return sum(parts(v))
    best = None
    for q in ((0.0,) if not q0 else (q0 * 0.8, q0, q0 * 1.25)):
        for lp in (450.0, 1200.0):
            x0 = [q, 0.0116, 2.2, lp, 3.6]
            sim = [x0] + [list(np.array(x0) + d) for d in np.diag([0.02 if q0 else 0.0, 0.01, 0.3, lp * 0.3, 0.8])]
            r = minimize(err, x0, method="Nelder-Mead",
                         options=dict(xatol=1e-4, fatol=1e-3, maxfev=500, initial_simplex=sim))
            if best is None or r.fun < best.fun:
                best = r
    a, b = parts(best.x)
    a0, b0 = parts([q0, T.FretlessBassProperties.pickup_width, BS2["tonal_dampening"],
                    BS2["lowpass_hz"], BS2["lowpass_order"]])
    print("  %-6s %s" % (pickup, ", ".join("%s %.4g" % (k, v) for k, v in zip(KNOBS, best.x))))
    print("         ladder %.2f + envelope %.2f dB  (Fretless Bs2's top on this coil: %.2f + %.2f)" % (a, b, a0, b0))


def main(argv):
    for pickup, q0 in (("both", 0.0), ("neck", 0.168), ("bridge", 0.098)):
        fit(pickup, q0)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
