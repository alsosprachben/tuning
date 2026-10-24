#!/usr/bin/env python3
"""The vibraslap's swing: each take's strikes folded at the rod's period.

    python3 -I examples/vibraslap_swing.py [--model]

Above 1 kHz (the pins, not the box), the power envelope folded at the swing
(the period of best fold contrast, 26.5-28.5 Hz) into 18 phase bins, over
spans of the decay, dB re each span's loudest bin. Two peaks half a swing
apart are the two sides struck; one is a side no longer reached. --model
folds ours (velocity 100, examples/perc_fit.py's note) beside them.
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(HERE, "examples"), HERE]

TAKES = os.path.expanduser("~/Documents/refs/vsco2/VSCO 1 Percussion/varWood/vibraslap[0-9].wav")
SPANS = ((0.1, 0.5), (0.5, 0.9), (0.9, 1.3), (1.3, 1.7), (1.7, 2.1), (2.1, 2.5))


def fold(name, x, sr):
    from scipy.signal import butter, sosfiltfilt
    y = sosfiltfilt(butter(4, 1000, btype="high", fs=sr, output="sos"), x)
    e = y * y
    t0 = int(np.argmax(np.abs(y) > np.abs(y).max() * 0.1))
    best = None
    for f in np.arange(26.5, 28.5, 0.02):
        P = sr / f
        idx = np.arange(t0, min(len(e), t0 + int(2.0 * sr)))
        h = np.bincount(((idx - t0) % P / P * 36).astype(int), e[idx], 36)
        if best is None or h.max() / h.mean() > best[0]:
            best = (h.max() / h.mean(), f)
    P = sr / best[1]
    print("== %s  swing %.2f Hz" % (name, best[1]))
    for a0, a1 in SPANS:
        idx = np.arange(t0 + int(a0 * sr), min(len(e), t0 + int(a1 * sr)))
        if len(idx) < sr * 0.2:
            break
        b = ((idx - t0) % P / P * 18).astype(int)
        h = np.bincount(b, e[idx], 18) / np.bincount(b, None, 18)
        db = 10 * np.log10(h / h.max() + 1e-12)
        lvl = 10 * np.log10(e[idx].mean() / e[t0:t0 + int(0.4 * sr)].mean())
        print("  %.1f-%.1f s (%5.1f dB): %s" % (a0, a1, lvl, " ".join("%4.0f" % v for v in db)))


def main(argv):
    from drum_fit import read
    for p in sorted(glob.glob(TAKES)):
        a, sr = read(p)
        fold(os.path.basename(p), a.sum(1), sr)
    if "--model" in argv:
        os.environ.setdefault("TUNING_REFLECT", "0")
        import perc_fit as P
        chs, sr = P.C.render(58, 100, P.INSTS["vibraslap"]["hold"])
        fold("ours", chs[0] + chs[1], sr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
