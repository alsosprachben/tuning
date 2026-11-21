#!/usr/bin/env python3
"""The CP80's attack, brilliance and top decay together (Ben, on the refit:
"the louder ones are missing a little brilliance. The high seems to be
decaying too much. The attack needs some care.").

    cp80_attack_fit.py [--maxfev=N] [--params=a,b,...]   (run from the tuning root)
    cp80_attack_fit.py show                               per key, as it stands

THE MEASURE: four bands (0.4-1.6, 1.6-3.2, 3.2-8, 8-14 kHz, each from 1.5 f0
up), in windows from the first 5 ms to 0.64 s, each re THE WHOLE NOTE'S level
at 0.3-0.6 s -- so a band's brightness and its fall both count, and the takes'
normalising (Greg Sullivan's CP80, every take near full scale) does not.
Every key, the soft (MP, else PP) and the hard (FF) layer. Nelder-Mead on the
parameters (additive steps, each its own scale).
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
os.environ.setdefault("TUNING_REFLECT", "0")
import upright_fit as U  # noqa: E402
import tonelib as T  # noqa: E402
from scipy.signal import butter, sosfiltfilt  # noqa: E402

U.REF[0] = "cp80"
M = U._cp80_map()
W = [(0, .005), (.005, .01), (.01, .02), (.02, .04), (.04, .08), (.08, .16), (.16, .32), (.32, .64)]
BANDS = [(400, 1600), (1600, 3200), (3200, 8000), (8000, 14000)]
STEP = {"hammer_open_slope": 300.0, "hammer_order": 0.5, "harmonic_decay_db": 0.6,
        "harmonic_decay_dampening": 0.2, "attack_time": 0.0015, "wound_decay_db": 15.0,
        "wound_zing_db": 8.0, "hammer_corner_hz": 3.0, "hammer_open_lo": 0.7, "hammer_open_power": 0.5, "bridge_peak_db": 4.0, "bridge_peak_hz": 1500.0, "bridge_peak_width": 0.2, "tonal_dampening": 0.2}


def course(x, sr, k):
    f0 = 440.0 * 2 ** ((k - 69) / 12.0)
    ref = 10 * np.log10(np.mean(x[int(.3 * sr):int(.6 * sr)] ** 2) + 1e-20)
    out = []
    for lo, hi in BANDS:
        lo = max(lo, 1.5 * f0)
        if lo >= hi:
            out.append(np.full(len(W), np.nan))
            continue
        s = sosfiltfilt(butter(4, [lo, hi], 'band', fs=sr, output='sos'), x)
        out.append(np.array([10 * np.log10(np.mean(s[int(a * sr):int(b * sr)] ** 2) + 1e-20) for a, b in W]) - ref)
    return np.concatenate(out)


def cut(x, sr):
    return x[max(U.onset(x, sr) - int(.001 * sr), 0):]


REC = {}
for k in sorted(M):
    for lay in (next((l for l in ("MP", "PP") if l in M[k]), None), "FF"):
        if lay and lay in M[k]:
            x, sr = U.load(M[k][lay])
            r = course(cut(x, sr), sr, k)
            r[3 * len(W)] = np.nan          # (8-14 kHz's first 5 ms: the takes' onsets, not a sound)
            REC[(k, lay)] = r


def err(verbose=False):
    e, rows = [], []
    for (k, lay), r in REC.items():
        y, s2 = U.render(2, k, U.CP80_LAYERS[lay], 1.0)
        o = course(cut(y, s2), s2, k)
        # (a band the take holds under -60 dB re the note is its floor, not the instrument)
        d = np.where(np.isfinite(r) & (r > -60.0), o - r, np.nan)
        d = d[np.isfinite(d)]
        e.append(d)
        rows.append((k, lay, float(np.sqrt(np.mean(d ** 2))), o, r))
    if verbose:
        for k, lay, v, o, r in rows:
            print("   %-4s %-2s %5.1f   3.2-8k ours-rec %s   8-14k %s" % (
                U.name(k), lay, v, " ".join("%4.0f" % q for q in (o - r)[16:24]),
                " ".join("%4.0f" % q for q in (o - r)[24:32])))
    return float(np.sqrt(np.mean(np.concatenate(e) ** 2)))


def main(argv):
    C = T.ElectricGrandProperties
    if "show" in argv:
        print("rms %.2f dB" % err(True))
        return
    opts = dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    names = opts.get("--params", "hammer_open_slope,hammer_order,harmonic_decay_db,harmonic_decay_dampening,"
                                 "attack_time,wound_decay_db").split(",")
    x0 = np.array([float(getattr(C, n)) for n in names])
    sc = np.array([STEP[n] for n in names])
    best = [1e9, x0]
    from scipy.optimize import minimize

    def f(z):
        v = x0 + z * sc
        # (an onset under 1.5 ms clicks: the soft bass's 8-14 kHz 30-50 dB over the take's)
        if "attack_time" in names and not 0.0015 <= v[names.index("attack_time")] <= 0.006:
            return 99.0
        if "hammer_open_power" in names and v[names.index("hammer_open_power")] < 0.2:
            return 99.0
        for n, q in zip(names, v):
            setattr(C, n, float(q))
        e = err()
        if e < best[0]:
            best[:] = [e, v]
            print("  %6.2f dB  %s" % (e, " ".join("%s=%.4g" % (n, q) for n, q in zip(names, v))), flush=True)
        return e
    n = len(names)
    minimize(f, np.zeros(n), method="Nelder-Mead",
             options={"maxfev": int(opts.get("--maxfev", 90)), "xatol": 0.02, "fatol": 0.02,
                      "initial_simplex": np.vstack([np.zeros(n)] + [np.eye(n)[i] for i in range(n)])})
    for n_, q in zip(names, best[1]):
        setattr(C, n_, float(q))
        print("    %s = %.5g" % (n_, q))
    print("rms %.2f dB" % err(True))


if __name__ == "__main__":
    main(sys.argv[1:])
