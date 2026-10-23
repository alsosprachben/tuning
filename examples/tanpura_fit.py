"""GS 104.16 Tamboura, fitted to sankalp's tanpura (Freesound pack 9571,
CC BY 4.0; sources.md) -- measure only, the takes never leave this machine.

THE TAKES ARE A DRONE: the four strings re-plucked every 3-3.5 s, each over
the others, and nothing ever rings out. They come apart by the tuning. Pa
(206 Hz) under Sa (275) and a low Sa (138): every partial on one comb at the
low Sa's pitch b, but Pa's ODD harmonics sit at odd multiples of 1.5 b, where
no Sa string has one, and the low Sa's harmonics k that are not multiples of
2 or 3 (1, 5, 7, 11, 13 ...) are its alone. So each string is followed
through its own partials, from each of its plucks (found by them) to its
next, and averaged over the plucks: a table of (harmonic, time) cells, dB
under the string's loudest cell. Ours, one note at the string's pitch, read
the same way.

    python3 examples/tanpura_fit.py              # the cells, takes and ours
    python3 examples/tanpura_fit.py --fit        # the decay, bloom and prompt fall
    python3 examples/tanpura_fit.py --body       # the colour, by third octave
    python3 examples/tanpura_fit.py --alt=3      # the two alternated, 3 rounds
    ... --take=1 --cls=TambraProperties          # GS 104.8, take 1
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
from drum_fit import read  # noqa: E402

# ONE TAKE: within it a string's plucks agree to 2-3.5 dB rms (odd against
# even), but take 1 and take 2 differ by 9-13 -- two settings of the jawari
# (or a retune), so an average of them is neither. Take 2: 14 plucks a string
# Take 1 is the other setting: GS 104.8 Tambra (--take=1 --cls=TambraProperties)
TAKE_FILES = {1: "153247__sankalp__acoustic-tanpura-1.wav", 2: "153248__sankalp__acoustic-tanpura-2.wav"}
TAKES = [os.path.expanduser("~/Documents/refs/freesound/tanpura/" + TAKE_FILES[2])]
# each string: its pitch over b, the harmonics that are its alone
STRINGS = {"pa": (1.5, [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23]),
           "lowsa": (1.0, [1, 5, 7, 11, 13, 17, 19, 23, 25, 29, 31, 35])}
TS = (0.03, 0.08, 0.15, 0.25, 0.4, 0.6, 0.85, 1.2, 1.6, 2.1, 2.5)
WIN = 0.08
FLOOR = -50.0
CLS = "TambouraProperties"
# (not decay_register_slope: two pitches 0.58 octave apart ran it to 2.5, a
# note two octaves up 32x faster; the two fundamentals' own rates, 9.6 and 6.0
# dB/s, set it -- tonelib.TambouraProperties)
FIT = ("decay_db", "harmonic_decay_db", "tonal_dampening",
       "bloom_gain", "bloom_seconds", "bloom_center_hz", "bloom_octaves", "bloom_swell",
       "bloom_decay_dbs", "prompt_dbs", "aftersound_share", "prompt_max_hz")


def _peaks(x, sr):
    N = 1 << 22
    seg = x[:int(min(len(x), 20 * sr))]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1 / sr)

    def pk(c, w):
        i = (f > c - w) & (f < c + w)
        return f[i][np.argmax(X[i])]
    return float(np.median([pk(137.8 * h, 0.012 * 137.8 * h) / h for h in (5, 7, 11, 13)]))


def cells(x, sr, t0s, f0, hs, ts=TS):
    """dB at each (harmonic, time) after each onset in t0s, averaged in dB."""
    win = int(WIN * sr)
    w = np.hanning(win)
    NN = 1 << 15
    ff = np.fft.rfftfreq(NN, 1 / sr)
    out = []
    for t0 in t0s:
        M = []
        for t in ts:
            s = int((t0 + t) * sr)
            Y = 20 * np.log10(np.abs(np.fft.rfft(x[s:s + win] * w, NN)) + 1e-9)
            M.append([Y[(ff > h * f0 * 0.99) & (ff < h * f0 * 1.01)].max() for h in hs])
        out.append(M)
    return np.mean(out, 0)


def plucks(x, sr, f0, hs):
    """Onsets of the string whose own partials are hs (at f0)."""
    win = int(0.08 * sr)
    hop = int(0.02 * sr)
    w = np.hanning(win)
    NN = 1 << 15
    ff = np.fft.rfftfreq(NN, 1 / sr)
    e = []
    for s in range(0, len(x) - win, hop):
        Y = np.abs(np.fft.rfft(x[s:s + win] * w, NN)) ** 2
        e.append(10 * np.log10(sum(Y[(ff > h * f0 * 0.99) & (ff < h * f0 * 1.01)].max()
                                   for h in hs[:6]) + 1e-12))
    e = np.array(e)
    ons = []
    for i in range(3, len(e) - 3):
        if e[i + 2] - e[i - 2] > 6 and e[i + 2] > e.max() - 30 and (not ons or i - ons[-1] > 25):
            ons.append(i)
    # the onset itself: where the rise is steepest, a frame either side
    return [(i + int(np.argmax(np.diff(e[i - 2:i + 4])) - 1) * 1.0) * 0.02 for i in ons]


def targets():
    """{string: (f0, cells dB re its max)}, over both takes' plucks that ring
    long enough before the string's next."""
    acc = {k: [] for k in STRINGS}
    f0s = {k: [] for k in STRINGS}
    for p in TAKES:
        x, sr = read(p)
        x = x.mean(1) if x.ndim > 1 else x
        b = _peaks(x, sr)
        for k, (r, hs) in STRINGS.items():
            on = plucks(x, sr, b * r, hs)
            ok = [t for t, n in zip(on, on[1:] + [len(x) / sr]) if n - t > TS[-1] + WIN + 0.05]
            M = cells(x, sr, ok, b * r, hs)
            acc[k].append((M, len(ok)))
            f0s[k].append(b * r)
    out = {}
    for k in STRINGS:
        n = sum(c for _, c in acc[k])
        M = sum(m * c for m, c in acc[k]) / n
        out[k] = (float(np.mean(f0s[k])), M - M.max(), n)
    return out


def ours(f0, secs=TS[-1] + 0.3):
    import pluck_fit as P
    P.PROG, P.CLS, P.BANK = 104, CLS, {"TambouraProperties": 16, "TambraProperties": 8}[CLS]
    y, sr = P.render(f0, secs)
    return y, sr


def ours_cells(T):
    out = {}
    for k, (f0, _, _) in T.items():
        y, sr = ours(f0)
        on = int(np.flatnonzero(np.abs(y) > 0.02 * np.abs(y).max())[0])
        M = cells(y, sr, [on / sr], f0, STRINGS[k][1])
        out[k] = M - M.max()
    return out


def score(T, O, show=False):
    err = []
    for k, (f0, M, n) in T.items():
        m = M > FLOOR
        d = (np.maximum(O[k], FLOOR - 10) - M)[m]
        err.append(d)
        if show:
            hs = STRINGS[k][1]
            print("== %s %.2f Hz, %d plucks: take / ours, dB re each's loudest" % (k, f0, n))
            print("      " + " ".join("%9s" % t for t in TS))
            for j, h in enumerate(hs):
                print("h%-3d  " % h + " ".join("%4.0f/%-4.0f" % (M[i, j], O[k][i, j]) for i in range(len(TS))))
    e = np.concatenate(err)
    r = float(np.sqrt(np.mean(e ** 2)))
    if show:
        print("rms %.2f dB over %d cells" % (r, len(e)))
    return r


def _set(vals):
    import tonelib
    C = getattr(tonelib, CLS)
    for a, v in zip(FIT, vals):
        setattr(C, a, float(v))


def fit(T, maxfev=160):
    import tonelib
    from scipy.optimize import minimize
    C = getattr(tonelib, CLS)
    x0 = np.array([getattr(C, a) for a in FIT], float)
    lo = np.array([1.0, 0.0, 0.1, 0.0, 0.01, 500.0, 0.3, 0.05, 1.0, 0.0, 0.0, 100.0])
    hi = np.array([40.0, 4.0, 2.0, 30.0, 1.5, 9000.0, 4.0, 3.0, 150.0, 60.0, 1.0, 4000.0])
    best = [1e9, x0]

    def f(u):
        v = np.clip(x0 * np.exp(u), lo, hi)
        _set(v)
        s = score(T, ours_cells(T))
        if s < best[0]:
            best[:] = [s, v]
            print("  %.2f dB  " % s + " ".join("%s=%.4g" % (a, b) for a, b in zip(FIT, v)), flush=True)
        return s
    minimize(f, np.zeros(len(x0)), method="Nelder-Mead",
             options=dict(maxfev=maxfev, initial_simplex=np.vstack([np.zeros(len(x0)),
                                                                    0.4 * np.eye(len(x0))])))
    _set(best[1])
    return best


CEN = 2 ** np.arange(np.log2(160), np.log2(13000), 1 / 3.0)


def body(T, passes=3):
    """The colour: each third octave's mean (ours - take) over the cells
    0.15-0.6 s in, both strings, the overall level difference taken out first
    (each table is re its own loudest cell, which a trim moves); bands with no
    cell interpolated from their neighbours. Trimmed into body_trim_db, from
    flat: the sitar's gourd is not the tanpura's."""
    import tonelib
    C = getattr(tonelib, CLS)
    keys = [int(round(c)) for c in CEN]
    if "--from-flat" in sys.argv or not getattr(C, "body_trim_db", None) \
            or [k for k, _ in C.body_trim_db] != keys:
        C.body_trim_db = tuple((k, 0.0) for k in keys)
    for _ in range(passes):
        O = ours_cells(T)
        trim = dict(C.body_trim_db)
        rows = []
        for k, (f0, M, n) in T.items():
            for j, h in enumerate(STRINGS[k][1]):
                for i, t in enumerate(TS):
                    if 0.15 <= t <= 0.6 and M[i, j] > FLOOR:
                        rows.append((h * f0, O[k][i, j] - M[i, j]))
        hz = np.array([r[0] for r in rows])
        d = np.array([r[1] for r in rows])
        d -= d.mean()
        lc = np.log2(CEN)
        have, mean = [], []
        for c, l in zip(CEN, lc):
            m = np.abs(np.log2(hz) - l) <= 1 / 6.0
            if m.any():
                have.append(l)
                mean.append(float(d[m].mean()))
        full = np.interp(lc, have, mean)
        C.body_trim_db = tuple((kk, round(float(np.clip(trim[kk] - v, -30, 30)), 1))
                               for kk, v in zip(keys, full))
        print("  body rms %.2f -> trim %s" % (score(T, O), C.body_trim_db), flush=True)
    score(T, ours_cells(T), show=True)


def show_class():
    """The class's fitted values, to write into tonelib."""
    import tonelib
    C = getattr(tonelib, CLS)
    for a in FIT:
        print("    %s = %.4g" % (a, getattr(C, a)))
    print("    body_trim_db = %s" % (C.body_trim_db,))


def main(argv):
    global TAKES, CLS
    for a in argv:
        if a.startswith("--take="):
            TAKES = [os.path.expanduser("~/Documents/refs/freesound/tanpura/" + TAKE_FILES[int(a[7:])])]
        if a.startswith("--cls="):
            CLS = a[6:]
    T = targets()
    if "--fit" in argv:
        fit(T)
    if "--body" in argv:
        body(T)
    rounds = next((int(a[6:]) for a in argv if a.startswith("--alt=")), 0)
    # THE BEST STATE IS KEPT: a body pass re-reads each table against its own
    # loudest cell, which the trim moves, so a round can end worse than it began
    import tonelib
    C = getattr(tonelib, CLS)

    def snap():
        return {a: getattr(C, a) for a in FIT + ("body_trim_db",)}
    best = (score(T, ours_cells(T)), snap())
    for r in range(rounds):
        body(T, passes=2)
        s, _ = fit(T, maxfev=120)
        print("ROUND %d: %.2f dB" % (r, s), flush=True)
        if s < best[0]:
            best = (s, snap())
    if rounds:
        for a, v in best[1].items():
            setattr(C, a, v)
        print("BEST %.2f dB" % best[0])
    score(T, ours_cells(T), show=True)
    if "--fit" in argv or "--body" in argv or rounds:
        show_class()


if __name__ == "__main__":
    main(sys.argv[1:])
