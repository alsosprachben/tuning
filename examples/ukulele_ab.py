#!/usr/bin/env python3
"""Ben's ukulele against ours (tonelib.UkuleleProperties, GS 24.8): eight of
his chromatic take's notes across the range, each his then ours, level-matched
on the first second; then his phrase as he played it. His own recording
(sources.md, ukulele_ben/), so it may be sent.

    python3 examples/ukulele_ab.py OUT.wav
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]


def main(out):
    import blockrender as B
    import pluck_fit as PL
    import plectrum_fit as PF
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    sr = B.SR
    staged = sorted(glob.glob(os.path.join(PL.REFS, "staged", "ukulele", "*.wav")),
                    key=lambda p: float(p.split("_f0_")[1][:-4]))
    pick = [staged[int(i)] for i in np.linspace(0, len(staged) - 1, 8)]
    gap, n = np.zeros(int(0.4 * sr)), int(2.4 * sr)
    parts = []
    for p in pick:
        f0 = float(p.split("_f0_")[1][:-4])
        x, xsr = PL.read(p)
        if xsr != sr:
            x = resample_poly(x, sr // 100, xsr // 100)
        a = int(np.flatnonzero(np.abs(x) > 0.05 * np.abs(x).max())[0])
        x = x[max(0, a - int(0.01 * sr)):][:n]
        o = PF.ours("UkuleleProperties", 24, 8, int(round(69 + 12 * np.log2(f0 / 440.0))))
        b = int(np.flatnonzero(np.abs(o) > 0.05 * np.abs(o).max())[0])
        o = o[max(0, b - int(0.01 * sr)):][:n]
        g = np.sqrt((x[:sr] ** 2).mean() / max((o[:sr] ** 2).mean(), 1e-30))
        parts += [np.pad(x, (0, n - len(x))), gap, np.pad(o * g, (0, n - len(o))), gap, gap]
    ph, psr = PL.read(os.path.expanduser("~/Documents/refs/ukulele_ben/06_phrase.wav"))
    if psr != sr:
        ph = resample_poly(ph, sr // 100, psr // 100)
    y = np.concatenate(parts + [gap, gap, ph])
    wavfile.write(out, sr, (y / np.abs(y).max() * 0.8 * 32767).astype(np.int16))
    print("  %s" % out)


if __name__ == "__main__":
    main(sys.argv[1])
