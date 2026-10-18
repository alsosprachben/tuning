#!/usr/bin/env python3
"""Fit the harpsichord's 4' from a recording of the 8' alone and the 8' + 4'.

    harpsi_4ft.py measure SAMPLES_DIR
    harpsi_4ft.py model SAMPLES_DIR
    harpsi_4ft.py fit SAMPLES_DIR [--params=a,b] [--maxfev=N]
    harpsi_4ft.py ab MID OUTDIR [--secs=40]   before / fitted / level-matched, 8'+4'
    harpsi_4ft.py upper-ab MID OUTDIR [--secs=40]   the upper 8', Flemish-carried / English-fitted
    harpsi_4ft.py lute-ab MID OUTDIR [--secs=40]    the lute, VCSL-fitted / Harpsimachord-fitted

SAMPLES_DIR is Douglas Knisely's Harpsimachord (Pianobook) SamplesNR: a Brown
copy of a 1750 Kirckman, every key F1-F6 in seven registrations, at A=415 and
named by the A=440 MIDI number (so each file sounds a semitone under its
name). Lower/ is the lower 8' alone, Lower+4/ the lower 8' with the 4' drawn.

WHY A DIFFERENCE. The pack is EQ'd, reverberated and noise-reduced, and every
registration went through the same chain: the 8'+4' take over the 8' take,
key by key, divides it out. And the 4' lands only on the 8''s EVEN harmonics
(its n-th is the 8''s 2n-th), so the ODD harmonics either side are the same
string plucked twice -- their change is the take-to-take difference (pluck
strength, a normalise), and is subtracted:

    excess(group) = gain of the even harmonics 2n, n in group
                  - gain of the odd harmonics 2n +- 1

pooled as power over the group, then the median over a register's keys (one
key's excess swings +-10 dB -- the pluck's comb, the 4' beating against the
8' a few cents off; the median of twenty does not). Early (0.05-0.45 s) and
late (0.8-1.6 s): the late excess against the early is the 4''s decay against
the 8''s. The model is rendered the same way -- GM 6 with the 8' drawn, and
with the 8' and 4' -- and read by the same estimator, so its biases cancel.
"""
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import voicefit as V
import harpsi_fit as H

GROUPS = ((1,), (2,), (3, 4), (5, 6, 7, 8))
WINS = ((0.05, 0.45), (0.8, 1.6))
BANDS = ((0, 200, "bass"), (200, 500, "tenor"), (500, 1e9, "treble"))
A415 = 415.0 / 440.0
KEYS = range(28, 89)            # file names (A=440 numbers); sounding = name - 1
MODEL_KEYS = range(28, 89, 2)   # every other key: the band medians, at half the renders


def powers(x, sr, f0, t0, t1, mmax=17):
    on = V.onset(x, sr)
    seg = x[on + int(t0 * sr):on + int(t1 * sr)]
    N = 1 << 18
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    P = np.full(mmax + 1, np.nan)
    for m in range(1, mmax + 1):
        fm = m * f0
        if fm > 0.45 * sr:
            break
        w = (f > fm - 0.3 * f0) & (f < fm + 0.3 * f0)
        P[m] = X[w].max()
    return P


def excess(a_path, b_path, f_hint):
    """(f0, [window][group] excess dB) of take B (8'+4') over take A (8')."""
    xa, sr = V.mono(a_path)
    xb, _ = V.mono(b_path)
    f0 = V.detect_f0(V.steady(xa, sr, 0.05, 0.45), sr, lo=0.9 * f_hint, hi=1.1 * f_hint)
    if not f0:
        return None
    out = np.full((len(WINS), len(GROUPS)), np.nan)
    for i, (t0, t1) in enumerate(WINS):
        Pa, Pb = powers(xa, sr, f0, t0, t1), powers(xb, sr, f0, t0, t1)
        for j, g in enumerate(GROUPS):
            ev = [2 * n for n in g]
            od = sorted({m for e in ev for m in (e - 1, e + 1)})
            if max(od) >= len(Pa) or np.isnan(Pa[max(od)]):
                continue
            gain = lambda ms: 10 * np.log10(np.sum(Pb[ms]) / np.sum(Pa[ms]))
            out[i, j] = gain(ev) - gain(od)
    return f0, out


def by_band(rows):
    """{band: (median [window][group], interquartile half-width)}."""
    res = {}
    for lo, hi, name in BANDS:
        e = np.array([r[1] for r in rows if lo <= r[0] < hi])
        if len(e) >= 4:
            q1, med, q3 = np.nanpercentile(e, [25, 50, 75], axis=0)
            res[name] = (med, (q3 - q1) / 2, len(e))
    return res


def measured(d):
    rows = []
    for k in KEYS:
        a, b = os.path.join(d, "Lower", "%d.wav" % k), os.path.join(d, "Lower+4", "%d.wav" % k)
        if os.path.exists(a) and os.path.exists(b):
            r = excess(a, b, H.key_hz(k) * A415)
            if r:
                rows.append(r)
    return by_band(rows)


def model(tmp, cache):
    """The same statistic on renders: key k-1 sounds where file k does."""
    rows = []
    for k in MODEL_KEYS:
        s = k - 1
        a = cache.get(s)
        if a is None:
            a = os.path.join(tmp, "m8_%d.wav" % s)
            H.render(s, 1 << H.BITS["8"], a)
            cache[s] = a
        b = os.path.join(tmp, "m84_%d.wav" % s)
        H.render(s, (1 << H.BITS["8"]) | (1 << H.BITS["4"]), b)
        r = excess(a, b, H.key_hz(s))
        if r:
            rows.append(r)
    return by_band(rows)


def show(title, bands):
    print("  " + title)
    print("     n          " + "  ".join("%-11s" % ",".join(map(str, g)) for g in GROUPS)
          + "| late - early")
    for _, _, name in BANDS:
        if name in bands:
            med, iq, n = bands[name]
            print("     %-6s %2d  " % (name, n)
                  + "  ".join("%5.1f +-%-4.1f" % (med[0, j], iq[0, j]) for j in range(len(GROUPS)))
                  + "| " + " ".join("%5.1f" % (med[1, j] - med[0, j]) for j in range(len(GROUPS))))


def err(mb, rb, late_w=0.5):
    """rms over bands and groups of model - recording, the early excess and
    (weighted late_w) the late-minus-early decay figure; nan cells skipped."""
    e = []
    for n in rb:
        if n in mb:
            m, r = mb[n][0], rb[n][0]
            e += list(m[0] - r[0])
            e += list(late_w * ((m[1] - m[0]) - (r[1] - r[0])))
    e = np.array(e)
    e = e[np.isfinite(e)]
    return float(np.sqrt(np.mean(e ** 2))) if len(e) else 99.0


# THE TWO LEVELS. The fit above (even over odd, at the same frequencies) puts
# the 4' as loud as the 8' -- 1.05. But the recording's 8'+4' is only 0.9 dB
# over its 8' (median of 61 keys, 0.02-0.4 s; the takes are not normalised),
# where the model's at 1.05 is 2.5 dB over: the Harpsimachord's 8' is weaker
# in its even harmonics against its fundamental than ours (VCSL's English), so
# "as loud as its evens" is louder here. Matching the total wants 0.57.
LEVEL_MATCHED = 0.57


def ab(mid, outdir, secs):
    """BWV 847 (or MID) on 8'+4' three ways, through harpsi_ab.piece: HEAD's
    4' (the host class at 2f0, 0.58), the fitted, the fitted at the level
    the totals match."""
    import tonelib as T
    import harpsi_ab as AB
    os.makedirs(outdir, exist_ok=True)
    P = T.HarpsichordProperties
    rows = P.stop_ranks
    i4 = [r[0] for r in rows].index("4")
    fitted, choirs = rows[i4], P.string_choirs
    takes = (("before", ("4", 2.0, 0.58),
              tuple((c, r, None) if c == "C" else (c, r, k) for c, r, k in choirs)),
             ("fitted", fitted, choirs),
             ("levelled", fitted[:2] + (LEVEL_MATCHED,) + fitted[3:], choirs))
    for name, row, ch in takes:
        rows[i4], P.string_choirs = row, ch
        out = os.path.join(outdir, "harpsichord_4ft_%s.wav" % name)
        AB.main(["harpsi_ab.py", "piece", mid, out, "--stop=8+4", "--secs=%g" % secs])
        print(name, out, flush=True)
    rows[i4], P.string_choirs = fitted, choirs


# BEFORE, per stop: the values each stood at before this pack refitted it
BEFORE = {
    # the upper 8', carried from VCSL's Flemish pair as a ratio
    "upper": ("HarpsiUpperProperties", {"strike_point": 0.083, "decay_db": 4.62 * 1.31,
                                        "harmonic_decay_db": 2.29 * 1.31},
              (("8-upper", "upper"), ("8+8-upper", "both8"))),
    # the lute, fitted to VCSL's English Lute set
    "lute": ("HarpsiLuteProperties", {"tonal_dampening": 1.095, "octave_dampening": 0.370,
                                      "decay_db": 14.46},
             (("lute", "lute"),)),
}


def stop_ab(which, mid, outdir, secs):
    """A stop on MID before (BEFORE[which]) and after (tonelib as it stands)."""
    import tonelib as T
    import harpsi_ab as AB
    os.makedirs(outdir, exist_ok=True)
    cname, before, stops = BEFORE[which]
    U = getattr(T, cname)
    after = {n: getattr(U, n) for n in before}
    for name, vals in (("before", before), ("after", after)):
        for n, v in vals.items():
            setattr(U, n, v)
        for stop, tag in stops:
            out = os.path.join(outdir, "harpsichord_%s_%s.wav" % (tag, name))
            AB.main(["harpsi_ab.py", "piece", mid, out, "--stop=" + stop, "--secs=%g" % secs])
            print(name, out, flush=True)
    for n, v in after.items():
        setattr(U, n, v)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    if args[0] == "ab":
        return ab(args[1], args[2], float(opts.get("secs", 40)))
    if args[0] in ("upper-ab", "lute-ab"):
        return stop_ab(args[0][:-3], args[1], args[2], float(opts.get("secs", 40)))
    cmd, d = args[0], args[1]
    rec = measured(d)
    show("recorded: 8'+4' over 8', even over odd, dB (median +- iq/2)", rec)
    if cmd == "measure":
        return
    tmp = tempfile.mkdtemp(prefix="harpsi4_")
    cache = {}
    if cmd == "model":
        mb = model(tmp, cache)
        show("model", mb)
        print("  rms %.2f dB" % err(mb, rec))
        return
    if cmd == "fit":
        import tonelib as T
        from scipy.optimize import minimize
        cls = T.HarpsiFourProperties
        names = opts.get("--params", "gain,strike_point,tonal_dampening,decay_db").split(",")
        rows = T.HarpsichordProperties.stop_ranks
        i4 = [r[0] for r in rows].index("4")

        def get(n):
            return rows[i4][2] if n == "gain" else getattr(cls, n)

        def put(n, x):
            # "gain" is the 4' row's level in stop_ranks; the rest, the class's
            if n == "gain":
                rows[i4] = rows[i4][:2] + (x,) + rows[i4][3:]
            else:
                setattr(cls, n, x)
        x0 = np.array([get(n) for n in names], float)

        def cost(v):
            for n, x in zip(names, v):
                put(n, float(x))
            mb = model(tmp, cache)
            c = err(mb, rec)
            print("   " + " ".join("%s=%.4g" % (n, x) for n, x in zip(names, v)) + "  rms %.2f" % c,
                  flush=True)
            return c
        r = minimize(lambda u: cost(x0 * np.exp(u)), np.zeros(len(x0)), method="Nelder-Mead",
                     options=dict(xatol=0.01, fatol=0.05, maxfev=int(opts.get("--maxfev", 40)),
                                  initial_simplex=np.vstack([np.zeros(len(x0)),
                                                             0.25 * np.eye(len(x0))])))
        best = x0 * np.exp(r.x)
        for n, x in zip(names, best):
            put(n, float(x))
        show("model, fitted", model(tmp, cache))
        print("  " + " ".join("%s = %.4g" % (n, x) for n, x in zip(names, best)))


if __name__ == "__main__":
    main()
