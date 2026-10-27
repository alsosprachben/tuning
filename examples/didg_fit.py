#!/usr/bin/env python3
"""The didgeridoo's MOUTH (GM2/SC-88 Pro 109.8, tonelib.DidgeridooProperties):
the player's vocal tract, three formants moving over a held drone -- fitted
to the CC0 takes staged by examples/freesound_slice.py didgeridoo (dethrok's
held drone and Jimmie P. Rodgers' playing, both at 64.6 Hz).

    python3 examples/didg_fit.py              the source, the floor, the mouth's states

Each 93 ms frame (hop 23 ms) is read as h1-h40 (dB, re its own mean), and
explained as a SOURCE (one series for the whole take: the lips' buzz through
the pipe) plus efxfilter's VOWEL response (type 5: three formants at fixed
widths over a floor) at that frame's three centres. Alternating: each frame's
centres the best on a grid, given the source; the source the median of what
the frames leave, given the centres. The floor is chosen by the residual.

The MOUTH is then what a voice can replay: the frames' centres clustered
into STATES (k-means, their shares), how long the mouth DWELLS in one (the
runs of a frame's nearest state, a log-normal's median and spread), and how
fast it GLIDES between (the centres' autocorrelation). Printed as the class's
numbers. The series itself is fitted through the renderer afterwards
(examples/wind_fit.py --voice=didgeridoo --fit=tables), the mouth moving.
"""
import glob
import os
import sys

import numpy as np

STAGED = os.path.expanduser("~/Documents/refs/freesound/staged/didgeridoo")
N, HOP, NH = 4096, 1024, 40
# the formants' search: efxfilter's VOWEL widths (80/110/160 Hz) at these centres
F1 = np.arange(250.0, 1150.0, 25.0)
F2 = np.arange(800.0, 2050.0, 40.0)
F3 = np.arange(1700.0, 2750.0, 75.0)
FLOORS = (0.15, 0.25, 0.4, 0.6)
STATES = 12
SMOOTH = 9
CHUNK = 256


def frames(x, sr):
    """Each frame's h1-NH (dB re the frame's mean over them) and its f0."""
    f = np.fft.rfftfreq(N, 1.0 / sr)
    win = np.hanning(N)
    A, F0 = [], []
    for i in range(0, len(x) - N, HOP):
        S = np.abs(np.fft.rfft(x[i:i + N] * win))
        m = (f > 55) & (f < 78)
        f0 = f[m][np.argmax(S[m])]
        m3 = (f > 3 * f0 - 8) & (f < 3 * f0 + 8)
        f0 = f[m3][np.argmax(S[m3])] / 3.0
        k = np.rint(np.arange(1, NH + 1) * f0 * N / sr).astype(int)
        A.append(20 * np.log10(np.maximum.reduce([S[k - 1], S[k], S[k + 1]]) + 1e-12))
        F0.append(f0)
    return np.array(A), np.array(F0)


def vowel_db(fh, G, floor):
    """efxfilter.response type 5 (gain 1) at harmonics fh, for each grid row
    G (centres), dB re its own mean."""
    h = np.full((len(G), len(fh)), floor)
    for k, (B, a) in enumerate(((80.0, 1.0), (110.0, 0.7), (160.0, 0.5))):
        u = (fh[None, :] - G[:, k:k + 1]) / (0.5 * B)
        h = h + a / (1.0 + u * u)
    L = 20 * np.log10(h)
    return L - L.mean(1, keepdims=True)


def best(R, L, w):
    """Each frame's grid row nearest (weighted squares), in chunks:
    |R-L|^2 = R.R - 2 R.L + L.L, the frames' dot products a matrix product."""
    Lw = L * w
    LL = (L * Lw).sum(1)
    out, err = np.empty(len(R), int), np.empty(len(R))
    for i in range(0, len(R), CHUNK):
        r = R[i:i + CHUNK]
        E = (r * r * w).sum(1)[:, None] - 2.0 * r @ Lw.T + LL[None, :]
        out[i:i + CHUNK] = E.argmin(1)
        err[i:i + CHUNK] = E[np.arange(len(r)), out[i:i + CHUNK]]
    return out, err


def kmeans(X, k, seed=0, iters=40):
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), k, replace=False)]
    for _ in range(iters):
        lab = ((X[:, None, :] - C[None]) ** 2).sum(2).argmin(1)
        C = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
    return C, lab


def main(argv):
    from scipy.io import wavfile
    takes = {}
    for p in sorted(glob.glob(os.path.join(STAGED, "C2_didg_*.wav"))):
        sr, x = wavfile.read(p)
        tag = os.path.basename(p).split("_")[2]
        takes.setdefault(tag, []).append(frames(x.astype(np.float64), sr))
    A = np.concatenate([a for v in takes.values() for a, _ in v])
    F0 = np.concatenate([f for v in takes.values() for _, f in v])
    f0 = float(np.median(F0))
    fh = f0 * np.arange(1, NH + 1)
    A = A - A.mean(1, keepdims=True)
    print("  %d frames, f0 %.2f Hz (%s)" % (len(A), f0, ", ".join("%s %d pieces" % (t, len(v))
                                                                   for t, v in takes.items())))
    G = np.array(np.meshgrid(F1, F2, F3, indexing="ij")).reshape(3, -1).T
    G = G[(G[:, 1] > G[:, 0] + 250) & (G[:, 2] > G[:, 1] + 250)]
    w = np.ones(NH)
    w[:2] = 0.0                   # h1-h2 under every formant: the source's alone
    static = A - np.median(A, 0)
    static = static - static.mean(1, keepdims=True)
    base = np.sqrt((static ** 2 * w).sum(1).mean() / w.sum())
    fits = []
    for floor in FLOORS:
        L = vowel_db(fh, G, floor)
        S = np.median(A, 0)
        for _ in range(4):
            R = A - S
            R = R - R.mean(1, keepdims=True)
            b, err = best(R, L, w)
            S = np.median(A - L[b], 0)
        res = float(np.sqrt(err.mean() / w.sum()))
        print("  floor %.2f: frames %.2f dB rms about the source+mouth (the source alone: %.2f)"
              % (floor, res, base), flush=True)
        fits.append((res, floor, S, b))
    res, floor, S, b = min(fits, key=lambda q: q[0])
    T = G[b]
    dt = HOP / 44100.0
    # THE FRAMES' CENTRES FLICKER on the grid (a frame's best is chosen
    # among near-ties): each smoothed by a running median over SMOOTH frames
    # (0.2 s), within each piece, before the states and their runs are read
    # -- unsmoothed, the runs' median was one frame against a 0.9 s glide
    from scipy.ndimage import median_filter
    ends = np.cumsum([len(a_) for v in takes.values() for a_, _ in v])
    T = np.concatenate([median_filter(T[s0:s1], size=(SMOOTH, 1), mode="nearest")
                        for s0, s1 in zip(np.r_[0, ends[:-1]], ends)])
    C, lab = kmeans(T, STATES)
    share = np.bincount(lab, minlength=STATES) / len(lab)
    # dwell: runs of one state (pieces joined; a run cut at a piece's end is
    # short by at most the piece, 2.5 s)
    runs, n = [], 1
    cut = set(ends.tolist())
    for i in range(1, len(lab)):
        if i in cut:
            n = 1                 # a piece's end: its last run is cut, not ended
            continue
        if lab[i] == lab[i - 1]:
            n += 1
        else:
            runs.append(n * dt)
            n = 1
    runs = np.array(runs)
    lr = np.log(runs)
    # the glide: the lag where the centres' autocorrelation falls to 1/e of
    # its value at one frame -- a first-order lag's time constant
    ac = []
    for k in range(3):
        v = T[:, k] - T[:, k].mean()
        a = [1.0] + [float(np.dot(v[:-j], v[j:]) / np.dot(v, v)) for j in range(1, 40)]
        lag = next((j for j in range(1, 40) if a[j] < a[1] / np.e), 40)
        ac.append(lag * dt)
    # THE GENERATOR CALIBRATED (efxfilter.mouth_track): the run lengths above
    # are a continuum cut into clusters -- a glide crosses several -- so the
    # dwell and glide are chosen instead by what the generator makes: the
    # pair whose tracks have the takes' spread (each formant's sd) and
    # correlation time (its 1/e lag), over 300 s on the frames' grid
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import efxfilter as E

    def stats(tr):
        out = []
        for v in tr:
            v = np.asarray(v) - np.mean(v)
            a_ = [float(np.dot(v[:-j], v[j:]) / np.dot(v, v)) for j in range(1, 300)]
            out.append((float(v.std()), next((j for j in range(len(a_)) if a_[j] < 1 / np.e), 300) * dt))
        return np.array(out)
    want = stats([T[:, k] for k in range(3)])
    states = [(C[i, 0], C[i, 1], C[i, 2], share[i]) for i in range(STATES)]
    tg = np.arange(0.0, 300.0, dt)
    cal = []
    for dw in (0.25, 0.4, 0.6, 0.9, 1.3, 2.0, 3.0):
        for gl in (0.06, 0.12, 0.25, 0.5, 1.0):
            got = np.mean([stats(E.mouth_track(tg, states, (dw, 0.75), gl, seed)) for seed in (1, 2)], 0)
            e = float(np.sqrt(np.mean(np.log(got[:, 0] / want[:, 0]) ** 2)
                              + np.mean(np.log(got[:, 1] / want[:, 1]) ** 2)))
            cal.append((e, dw, gl, got))
    e, dw, gl, got = min(cal, key=lambda q: q[0])
    print("  takes' tracks: sd %s Hz, 1/e %s s" % (" ".join("%.0f" % v for v in want[:, 0]),
                                                  " ".join("%.2f" % v for v in want[:, 1])))
    print("  generator dwell %.2f s, glide %.2f s: sd %s Hz, 1/e %s s (log err %.2f)" % (
        dw, gl, " ".join("%.0f" % v for v in got[:, 0]), " ".join("%.2f" % v for v in got[:, 1]), e))
    o = np.argsort(C[:, 0])
    print("  best floor %.2f (%.2f dB rms against %.2f)" % (floor, res, base))
    print("    MOUTH_FLOOR = %.2f" % floor)
    print("    MOUTH_STATES = (%s)" % ", ".join("(%d, %d, %d, %.3f)" % (C[i, 0], C[i, 1], C[i, 2], share[i])
                                               for i in o))
    print("    (the states' runs: median %.3f s, log spread %.2f, %d runs; the centres' 1/e %s s)" % (
        float(np.exp(np.median(lr))), float(lr.std()), len(runs), " ".join("%.3f" % a for a in ac)))
    print("    MOUTH_DWELL_S = (%.2f, 0.75)" % dw)
    print("    MOUTH_GLIDE_S = %.2f" % gl)
    print("  source dB re h1: " + " ".join("%.0f" % (v - S[0]) for v in S))
    print("    mode_gains = (%s)" % ", ".join("%.5f" % 10 ** ((v - S[0]) / 20.0) for v in S))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
