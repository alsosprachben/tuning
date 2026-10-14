#!/usr/bin/env python3
"""The peaks of a struck or plucked steel bar's recording: each strong
spectral peak as a ratio to the fundamental (the lowest strong peak), its
level re the strongest at the strike, and its decay -- to read which mode
set an instrument has (a free bar's 1 : 2.756 : 5.404, a cantilever's
1 : 6.267 : 17.55, a tuned bar's 1 : 4 : 10) before modelling it.

    python3 -I examples/steelbar_peaks.py FILE.wav [FILE ...] [--n=8] [--onset=SEC]

The fundamental is the strongest peak; a mode is a ratio to it. A file
holding several strikes (a comb plucked tooth by tooth) is split at
its onsets.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import upright_fit as U


def onsets(x, sr, gap=0.25, rise_db=15.0):
    w = int(0.005 * sr)
    e = 10 * np.log10(np.array([np.mean(x[i:i + w] ** 2) for i in range(0, len(x) - w, w)]) + 1e-20)
    top = e.max()
    out = []
    for i in range(4, len(e)):
        if e[i] - e[i - 4] > rise_db and e[i] > top - 45 and (not out or (i - out[-1]) * w / sr > gap):
            out.append(i)
    return [i * w for i in out]


def peaks(x, sr, n=8):
    t0 = U.onset(x, sr)
    seg = x[t0 + int(0.01 * sr):t0 + int(0.3 * sr)]
    N = 1 << 17
    X = 20 * np.log10(np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) + 1e-12)
    f = np.fft.rfftfreq(N, 1 / sr)
    ok = (f > 80) & (f < 18000)
    idx = np.flatnonzero(ok)
    loc = [i for i in idx[1:-1] if X[i] > X[i - 1] and X[i] >= X[i + 1]]
    loc = sorted(loc, key=lambda i: -X[i])
    pick = []
    for i in loc:
        if all(abs(f[i] / f[j] - 1) > 0.03 for j in pick):
            pick.append(i)
        if len(pick) >= n:
            break
    # THE NOTE IS THE STRONGEST PEAK: the lowest strong one was room rumble
    # 30-50 dB down (the celesta takes' ~90 Hz) on every take. Peaks under
    # 0.8 of it are dropped.
    f0i = pick[0]
    pick = [i for i in pick if X[i] > X[pick[0]] - 50 and f[i] > 0.8 * f[f0i]]
    out = []
    from scipy.signal import butter, sosfiltfilt
    w = int(0.02 * sr)
    for i in sorted(pick, key=lambda i: f[i]):
        fc = f[i]
        bw = max(8.0, 0.02 * fc)
        y = sosfiltfilt(butter(2, [fc - bw, min(fc + bw, 0.49 * sr)], btype="band", fs=sr, output="sos"), x[t0:])
        e = 10 * np.log10(np.array([np.mean(y[j:j + w] ** 2) for j in range(0, min(len(y), 3 * sr) - w, w)]) + 1e-20)
        a, b = 2, min(len(e), 40)
        k = np.flatnonzero(e[a:b] < e[a] - 30)
        bb = a + (k[0] if len(k) else b - a)
        dec = -np.polyfit(np.arange(a, bb) * 0.02, e[a:bb], 1)[0] if bb - a >= 3 else np.nan
        out.append((fc, fc / f[f0i], X[i] - X[pick[0]], dec))
    return out


def main(argv):
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    for p in [a for a in argv if not a.startswith("--")]:
        x, sr = U.load(p)
        segs = [(0, len(x))]
        os_ = onsets(x, sr)
        if len(os_) > 1:
            segs = list(zip(os_, os_[1:] + [len(x)]))
        for a, b in segs:
            pk = peaks(x[max(0, a - int(0.01 * sr)):b], sr, int(opts.get("n", 8)))
            f0 = next(q[0] for q in pk if abs(q[1] - 1.0) < 1e-9)
            k = 69 + 12 * np.log2(f0 / 440.0)
            print("%s @%.2fs  f0 %.1f Hz (key %.2f)" % (os.path.basename(p)[:40], a / sr, f0, k))
            print("   " + "  ".join("x%.3f %+.0fdB %sdB/s" % (r, l, "%.0f" % d if np.isfinite(d) else "?")
                                   for _, r, l, d in pk))


if __name__ == "__main__":
    main(sys.argv[1:])
