#!/usr/bin/env python3
"""The guiro's scrape, by its level: each of Iowa's takes' energy (300 Hz
up, 5 ms) from its onset to where it falls 15 dB under its peak, in tenths
of the scrape, dB re its loudest tenth -- and ours (GM 73, velocity 100, a
0.2 s note). What percussion_map.PERCUSSION_RASP_SHAPE is set from.

    python3 -I examples/guiro_curve.py
"""
import sys, os
import numpy as np
from scipy.signal import butter, sosfiltfilt
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(HERE, "examples"), HERE]
os.environ.setdefault("TUNING_REFLECT", "0")
import perc_fit as P
NB = 10
def curve(x, sr):
    y = sosfiltfilt(butter(4, 300, btype="high", fs=sr, output="sos"), x)
    n = int(0.005 * sr)
    e = np.convolve(y * y, np.ones(n) / n, "same")[::n]
    db = 10 * np.log10(e / e.max() + 1e-12)
    t0 = int(np.argmax(db > -30))
    pk = int(np.argmax(db))
    t1 = pk + int(np.argmax(db[pk:] < -15)) if (db[pk:] < -15).any() else len(db)
    seg = e[t0:t1]
    b = np.array_split(seg, NB)
    c = 10 * np.log10(np.array([v.mean() for v in b]))
    return (t1 - t0) * 5, c - c.max()
for p in P.files("guiro"):
    chs, sr = P.load(p)
    ms, c = curve(chs[0] + chs[1], sr)
    print("%-22s %3d ms  %s" % (os.path.basename(p), ms, " ".join("%5.1f" % v for v in c)))
P.HOLD[0] = 0.2
chs, sr = P.C.render(73, 100)
ms, c = curve(chs[0] + chs[1], sr)
print("%-22s %3d ms  %s" % ("ours", ms, " ".join("%5.1f" % v for v in c)))
