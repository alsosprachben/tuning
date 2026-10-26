#!/usr/bin/env python3
"""Fit the Chinese opera gongs (the Asia set's Bend Gong, Hu Yin Luo, Shou
Luo; the Ethnic set's Bend Gong) to the Beijing Opera Percussion Instrument
Dataset (Mi Tian, Ying Wan; CompMusic/QMUL 2013, Zenodo 1285212, CC BY 4.0 --
measured only; ~/Documents/refs/jingju_perc, sources.md).

    operagong_fit.py              the fits: glide, modes, decays
    operagong_fit.py --tuples     ...as the classes' TR-808 patches

THE TWO GONGS OF BEIJING OPERA. The DALUO, the great gong, falls in pitch
after the strike; the XIAOLUO, the small gong, rises. A gong plate is
stiffer the further it moves (its curvature), so its modes sit higher the
louder it rings: the daluo's flat face lets its pitch sag as it dies; the
xiaoluo's shaped face does the opposite. Each read from its OPEN strokes (the
dataset's others are damped, or struck elsewhere): the daluo's low mode at
194-203 Hz, ringing 2-9 s (26-29, 41-46); the xiaoluo's at ~650 Hz (54-65).

Per stroke:
  the GLIDE   the low mode tracked every 20 ms (46 ms windows, zero-padded,
              its peak interpolated) and fitted f(t) = f_end 2^(b e^(-t/tau)):
              b octaves above (b > 0, falling) or below (b < 0, rising), tau s
  the MODES   the strongest peaks 150 Hz - 6 kHz over 0.05-0.35 s, as ratios
              to the low mode then (a bend moves them together), dB re the
              strongest
  the DECAYS  each mode's level 0.1-0.3 s against later, as seconds to -60
The strokes' medians, modes matched across strokes within 2%.
"""
import glob
import os
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
D = os.path.expanduser("~/Documents/refs/jingju_perc/raw/beijing_opera_percussion_instrument_1.0")
# gong: (file stem, stroke numbers, low mode's band Hz)
GONGS = {
    "daluo": ("daluo", (26, 27, 28, 29, 41, 43, 44, 45, 46), (170.0, 240.0)),
    "xiaoluo": ("xiaoluo", (54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65), (560.0, 760.0)),
}


def load(stem, n):
    from scipy.io import wavfile
    f = glob.glob(os.path.join(D, "*__%s-%02d.wav" % (stem, n)))[0]
    sr, x = wavfile.read(f)
    x = x.astype(np.float64)
    x = x.mean(1) if x.ndim > 1 else x
    k = int(np.argmax(np.abs(x)))
    return x[k:], sr


def peak_hz(seg, sr, lo, hi, N=1 << 16):
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    m = np.flatnonzero((f > lo) & (f < hi))
    i = m[int(np.argmax(S[m]))]
    a, b, c = np.log(S[i - 1:i + 2] + 1e-20)
    d = 0.5 * (a - c) / (a - 2 * b + c)
    return f[i] + d * (f[1] - f[0]), 20 * np.log10(S[i] + 1e-20)


def glide(x, sr, band):
    w = int(0.046 * sr)
    out = []
    top = None
    for t in np.arange(0.03, min(2.0, len(x) / sr - 0.06), 0.02):
        a = int(t * sr)
        hz, db = peak_hz(x[a:a + w], sr, *band)
        top = db if top is None else max(top, db)
        if db < top - 30:
            break
        out.append((t, hz))
    t = np.array([p[0] for p in out])
    f = np.array([p[1] for p in out])
    best = None
    for tau in np.geomspace(0.02, 2.0, 60):
        e = np.exp(-t / tau)
        # log2 f = log2 f_end + b e: linear in (log2 f_end, b)
        A = np.stack([np.ones_like(e), e], 1)
        sol, *_ = np.linalg.lstsq(A, np.log2(f), rcond=None)
        r = np.sum((A @ sol - np.log2(f)) ** 2)
        if best is None or r < best[0]:
            best = (r, 2 ** sol[0], sol[1], tau)
    return best[1], best[2], best[3], (f[0], f[-1], t[-1])


def modes(x, sr, f_low):
    from scipy.signal import find_peaks
    a, b = int(0.05 * sr), int(0.35 * sr)
    seg = x[a:b]
    N = 1 << 16
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    m = (f > 150) & (f < 6000)
    db = 20 * np.log10(S + 1e-20)
    top = db[m].max()
    pk, _ = find_peaks(np.where(m, db, -300), height=top - 40, distance=int(15 / (f[1] - f[0])))
    pk = sorted(pk, key=lambda i: -db[i])[:16]
    out = []
    for i in sorted(pk):
        hz = f[i]
        early = peak_hz(x[int(0.1 * sr):int(0.3 * sr)], sr, hz * 0.985, hz * 1.015)[1]
        t1 = min(len(x) / sr - 0.25, 1.2)
        late = peak_hz(x[int(t1 * sr):int((t1 + 0.2) * sr)], sr, hz * 0.97, hz * 1.03)[1]
        dbs = max((early - late) / (t1 - 0.1), 1.0)
        out.append((hz / f_low, db[i] - top, 60.0 / dbs))
    return out


def fit(name):
    stem, nums, band = GONGS[name]
    G, M = [], []
    for n in nums:
        x, sr = load(stem, n)
        f_end, b, tau, (fa, fb, tl) = glide(x, sr, band)
        f_low = peak_hz(x[int(0.05 * sr):int(0.35 * sr)], sr, *band)[0]
        G.append((f_end, b, tau, fa, fb, tl))
        M.append(modes(x, sr, f_low))
    G = np.array(G)
    print("== %s: %d strokes" % (name, len(nums)))
    for (f_end, b, tau, fa, fb, tl), n in zip(G, nums):
        print("  %02d  low mode %.0f -> %.0f Hz over %.2f s; fit: ends %.1f Hz, %+.3f oct, tau %.3f s"
              % (n, fa, fb, tl, f_end, b, tau))
    med = np.median(G, 0)
    print("  median: ends %.1f Hz, bend %+.3f oct (%+.1f semitones), tau %.3f s" % (
        med[0], med[1], 12 * med[1], med[2]))
    # modes matched across strokes
    allm = sorted((r, d, s) for ms in M for r, d, s in ms)
    groups = []
    for r, d, s in allm:
        if groups and abs(r / groups[-1][0][0] - 1) < 0.02:
            groups[-1].append((r, d, s))
        else:
            groups.append([(r, d, s)])
    keep = [g for g in groups if len(g) >= max(3, len(nums) // 3)]
    res = []
    for g in keep:
        r = float(np.median([q[0] for q in g]))
        d = float(np.median([q[1] for q in g]))
        s = float(np.median([q[2] for q in g]))
        res.append((round(r, 4), round(d, 1), round(s, 3), len(g)))
    print("  modes (ratio to the low mode, dB, s to -60, strokes):")
    for r in res:
        print("    %.4f  %6.1f dB  %6.2f s  (%d)" % r)
    return med, res


def main(argv):
    out = {g: fit(g) for g in GONGS}
    if "--tuples" in argv:
        for g, (med, res) in out.items():
            low = min(res, key=lambda r: abs(r[0] - 1.0))
            ref = low[1]
            print("%s: tune_hz %.1f, decay_s %.2f, bend_oct %.3f, bend_ms %.0f" % (
                g, med[0], low[2], med[1], 1000 * med[2]))
            print("  res = %s" % (tuple((r, round(d - ref, 1), s) for r, d, s, _n in res if r != low[0]),))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
