#!/usr/bin/env python3
"""THE CHOIR SECTION from the Choral Singing Dataset v3 (Cuesta et al., ICMPC
2018; Zenodo record 1286570, CC BY 4.0 -- v5 is NC, not used): the Anton
Bruckner Choir, four singers a part singing together, each on a close
cardioid microphone, in three pieces (El Rossinyol, Locus Iste, Nino Dios).
Since 2026-11-23 in Dagstuhl ChoirSet's place (CC BY-NC-SA, licences.md L8).

Each singer's pitch by YIN (de Cheveigne & Kawahara 2002) at 10 ms. The four
of a part sang together, so their tracks line up without a score: where the
part holds one note 0.4 s or more (past its first 0.15 s and its last 0.1),
each singer's median against the PART's median, note by note -- with each
singer's own steady offset (a voice) taken out, the rest the scatter; and on
notes of 0.8 s or more, each singer's vibrato (depth, rate) about a 0.25 s
trend. What tonelib's SectionMixin draws:
  section_spread_cents   uniform +/-S has sd S/sqrt(3): S = sqrt(3) sd
  section_vibrato_cents  each player's depth is 0.7-1.0 of it: the median / 0.85
  section_vibrato_hz     the rates' 10-90 %

    python3 examples/csd_section.py           the measure, by part
"""
import glob
import os
import sys

import numpy as np

CSD = os.path.expanduser("~/Documents/refs/csd_v3/ChoralSingingDataset")
HOP_S = 0.010
PARTS = (("S", "Soprano"), ("A", "ContraAlt"), ("T", "enor"), ("B", "Bajos"))


def yin(x, sr, fmin=60.0, fmax=1100.0, hop=HOP_S, thresh=0.15):
    """f0 per frame (NaN unvoiced) and each frame's level, dB: YIN's
    cumulative-mean-normalised difference, batched by FFT."""
    W = int(2 ** np.ceil(np.log2(2.2 * sr / fmin)))
    tmax = int(sr / fmin) + 1
    tmin = int(sr / fmax)
    h = int(hop * sr)
    n = (len(x) - W) // h
    f0 = np.full(n, np.nan)
    lv = np.full(n, -200.0)
    B = 512
    for b0 in range(0, n, B):
        idx = np.arange(b0, min(n, b0 + B))
        fr = np.stack([x[i * h:i * h + W] for i in idx]).astype(np.float64)
        fr -= fr.mean(1, keepdims=True)
        lv[idx] = 10 * np.log10(np.mean(fr * fr, 1) + 1e-20)
        F = np.fft.rfft(fr, 2 * W, axis=1)
        r = np.fft.irfft(F * np.conj(F), axis=1)[:, :tmax + 1]
        sq = np.cumsum(fr * fr, 1)
        e0 = sq[:, W // 2 - 1]
        # d(tau) over the first W/2 samples: sum x^2 + sum shifted x^2 - 2 r
        tau = np.arange(tmax + 1)
        csum = np.concatenate([np.zeros((len(idx), 1)), sq], 1)
        sh = csum[:, tau + W // 2] - csum[:, tau]
        d = e0[:, None] + sh - 2 * r
        d[:, 0] = 0.0
        cm = d[:, 1:] * np.arange(1, tmax + 1) / np.maximum(np.cumsum(d[:, 1:], 1), 1e-20)
        cm = np.concatenate([np.ones((len(idx), 1)), cm], 1)
        for j, row in enumerate(cm):
            c = row[tmin:]
            below = np.flatnonzero(c < thresh)
            if not len(below):
                continue
            t = below[0]
            while t + 1 < len(c) and c[t + 1] < c[t]:
                t += 1
            T = t + tmin
            if 1 <= T < tmax:
                a, b_, cc = row[T - 1], row[T], row[T + 1]
                den = a - 2 * b_ + cc
                T = T + (0.5 * (a - cc) / den if den != 0 else 0.0)
            f0[idx[j]] = sr / T
    return f0, lv


def load(p):
    from scipy.io import wavfile
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sr, y = wavfile.read(p)
    y = y.astype(np.float64)
    return (y.mean(1) if y.ndim > 1 else y), sr


def tracks(piece, part_key):
    fs = sorted(glob.glob(os.path.join(CSD, piece, "Individual voices", "*%s*.wav" % part_key)))
    out = []
    for p in fs:
        cache = p[:-4] + ".yin.npz"
        if os.path.exists(cache):
            z = np.load(cache)
            out.append((z["f0"], z["lv"]))
            continue
        x, sr = load(p)
        f0, lv = yin(x, sr)
        np.savez(cache, f0=f0, lv=lv)
        out.append((f0, lv))
    return out


def measure():
    pieces = sorted(d for d in os.listdir(CSD) if os.path.isdir(os.path.join(CSD, d)))
    rows = {}
    for tag, key in PARTS:
        offs, vib = [], []
        for piece in pieces:
            tr = tracks(piece, key)
            if len(tr) < 2:
                continue
            n = min(len(f) for f, _ in tr)
            C = np.stack([1200 * np.log2(f[:n] / 440.0) for f, _ in tr])          # cents re A4
            L = np.stack([lv[:n] for _, lv in tr])
            ok = np.isfinite(C).all(0) & (L > L.max(1, keepdims=True) - 35).all(0)
            med = np.where(ok, np.median(np.where(np.isfinite(C), C, 0.0), 0), np.nan)
            note = np.round(med / 100.0)
            # held notes: the part's median within 60 cents of one semitone, 0.4 s on
            seg, start = [], None
            for i in range(n + 1):
                good = i < n and ok[i] and abs(med[i] - 100 * note[i]) < 60 and (start is None or note[i] == note[start])
                if good and start is None:
                    start = i
                elif not good and start is not None:
                    if (i - start) * HOP_S >= 0.4:
                        seg.append((start, i))
                    start = i if (i < n and ok[i] and abs(med[i] - 100 * note[i]) < 60) else None
            for a, b in seg:
                a2, b2 = a + int(0.15 / HOP_S), b - int(0.10 / HOP_S)
                if b2 - a2 < 10:
                    continue
                d = C[:, a2:b2] - med[None, a2:b2]
                offs.append(np.median(d, 1))
                if (b2 - a2) * HOP_S >= 0.8:
                    w = 25
                    for s in range(C.shape[0]):
                        c = C[s, a2:b2]
                        trend = np.convolve(c, np.ones(w) / w, "same")[w:-w]
                        v = c[w:-w] - trend
                        if len(v) < 40:
                            continue
                        P = np.abs(np.fft.rfft(v * np.hanning(len(v)), 8 * len(v))) ** 2
                        fr = np.fft.rfftfreq(8 * len(v), HOP_S)
                        sel = (fr > 3) & (fr < 9)
                        vib.append((np.sqrt(2) * v.std(), fr[sel][np.argmax(P[sel])]))
        O = np.array(offs)                                   # notes x singers
        O = O - np.median(O, 0)                              # each singer's steady offset: a voice
        O = O[(np.abs(O) < 100).all(1)]                      # a wrong note, a slip
        k = O.shape[1]
        sd = 1.4826 * np.median(np.abs(O)) / np.sqrt(1.0 - 1.0 / k)   # (re the part's median of k)
        V = np.array(vib)
        rows[tag] = (len(O), sd, np.median(V[:, 0]), np.percentile(V[:, 1], 10), np.percentile(V[:, 1], 90),
                     np.median(V[:, 1]), len(V))
    return rows


if __name__ == "__main__":
    rows = measure()
    print("  part  notes  scatter sd (c)  |  vibrato depth c (median)  rate Hz 10-50-90 %  (n)")
    for tag, (n, sd, dep, r10, r90, r50, nv) in rows.items():
        print("   %s   %5d    %5.1f          |  %5.1f                      %4.2f %4.2f %4.2f  (%d)"
              % (tag, n, sd, dep, r10, r50, r90, nv))
    sd = np.median([r[1] for r in rows.values()])
    dep = np.median([r[2] for r in rows.values()])
    lo = np.median([r[3] for r in rows.values()])
    hi = np.median([r[4] for r in rows.values()])
    print("  -> section_spread_cents %.1f (sd %.1f x sqrt 3); section_vibrato_cents %.1f (%.1f / 0.85); "
          "section_vibrato_hz (%.1f, %.1f)" % (np.sqrt(3) * sd, sd, dep / 0.85, dep, lo, hi))
