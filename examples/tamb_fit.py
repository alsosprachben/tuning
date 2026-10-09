#!/usr/bin/env python3
"""Fit the tambourine (GM 54) to Iowa's.

    python3 examples/tamb_fit.py [REFS] [--modes] [--model] [--fit [--maxfev=N]]

REFS (default ~/Documents/refs/tambourine) holds tb<1-3>.normal.<pp|mf|ff>.wav
as converted from the University of Iowa MIS "tambourines" page (~/Documents/
refs/sources.md): three tambourines, each struck once at three dynamics. They
are stereo; the two channels are summed in power.

The grid is examples/crash_fit.py's -- octave bands by time windows, each
group levelled on its own energy, the band trim solved inside the fit --
on windows sized to a tambourine (40 dB down in ~0.4 s). Two things differ
from a DRSKit take:

  - IOWA'S FLOOR IS HIGH. The softest strokes sit 35-40 dB over the room, so
    a cell within 6 dB of the stroke's own pre-onset floor in that band is
    noise, not tambourine, and weighs nothing (-200, as crash_fit masks a cell
    past the end of a file).
  - A STROKE IS ONE GESTURE but a file can hold another: some pp files strike
    again 0.26 s later. Windows from the next onset on are masked the same way.
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

import crash_fit as C  # noqa: E402
from drum_fit import read  # noqa: E402

NOTE = 54
DYN = {"soft": "pp", "mid": "mf", "loud": "ff"}
C.EDGES = (250, 500, 1000, 2000, 4000, 8000, 16000)
C.T = ((0.000, 0.010), (0.010, 0.030), (0.030, 0.060), (0.060, 0.120), (0.12, 0.25),
       (0.25, 0.40), (0.40, 0.60))
C.CENTRES = tuple(float(np.sqrt(a * b)) for a, b in zip(C.EDGES[:-1], C.EDGES[1:]))
C.COL_W = np.array([0.3] + [1.0] * (len(C.T) - 1))
_render = C.render
C.render = lambda note, vel, secs=1.0: _render(note, vel, secs)


def next_onset(x, sr, t0, gap=0.2):
    """The next stroke after t0, if the file has one: a rise of 12 dB over
    the 20 ms before it, past `gap`."""
    n = int(0.01 * sr)
    e = np.convolve(x * x, np.ones(n) / n, "same")
    db = 10 * np.log10(e + 1e-30)
    for i in range(t0 + int(gap * sr), len(x) - n, n):
        if db[i] - db[i - 2 * n] > 12.0 and db[i] > db[t0:].max() - 40.0:
            return i
    return None


def floor_grid(chs, sr, t0):
    """Each band's level in the silence before the stroke, as a mean power."""
    pre = [c[:max(0, t0 - int(0.005 * sr))] for c in chs]
    out = np.full(len(C.EDGES) - 1, -200.0)
    n = len(pre[0])
    if n < 1024:
        return out
    f = np.fft.rfftfreq(n, 1.0 / sr)
    P = sum(np.abs(np.fft.rfft(c * np.hanning(n))) ** 2 for c in pre) / (n * 0.375)
    for i, (lo, hi) in enumerate(zip(C.EDGES[:-1], C.EDGES[1:])):
        out[i] = 10 * np.log10(P[(f >= lo) & (f < hi)].sum() / n + 1e-30)
    return out


def strokes(refs):
    out = []
    for p in sorted(glob.glob(os.path.join(refs, "tb*.normal.*.wav"))):
        a, sr = read(p)
        chs = [a[:, 0], a[:, 1]]
        t0 = C.onset(chs, sr)
        g = C.grid(chs, sr)
        fl = floor_grid(chs, sr, t0)
        g = np.where(g < fl[:, None] + 6.0, -200.0, g)
        nx = next_onset(chs[0] + chs[1], sr, t0)
        if nx is not None:
            for j, (_, b) in enumerate(C.T):
                if t0 + int(b * sr) > nx:
                    g[:, j] = -200.0
        dyn = os.path.basename(p).split(".")[2]
        out.append((dyn, C.level(chs, sr), g, os.path.basename(p)))
    return out


def grouped(ss):
    top = np.mean([l for d, l, _, _ in ss if d == "ff"])
    out = {}
    for g, d in DYN.items():
        rr = [s for s in ss if s[0] == d]
        # mean in dB over the cells every take has; a masked cell in one take
        # is masked in the mean
        gs = np.array([s[2] - s[2].max() for s in rr])
        m = np.where((gs < -100).any(0), -200.0, gs.mean(0))
        out[g] = (float(np.mean([s[1] for s in rr])) - top, m)
    return out


def modes(refs, which="tb2", lo=2000.0, hi=19000.0, floor_db=-25.0, f0=1000.0):
    """The jingles' modes: the peaks of one tambourine's mf and ff strokes,
    20-200 ms, 2-19 kHz, each the highest within +-0.4%, within 25 dB of the
    strongest -- as (ratio to f0, dB re the strongest, amplitude dB/s read
    between 30-90 and 120-250 ms)."""
    sr = None
    win = ((0.02, 0.20), (0.03, 0.09), (0.12, 0.25))
    acc = [0.0, 0.0, 0.0]
    for d in ("mf", "ff"):
        a, sr = read(os.path.join(refs, "%s.normal.%s.wav" % (which, d)))
        x = a[:, 0] + a[:, 1]
        t0 = C.onset([x], sr)
        for k, (a0, a1) in enumerate(win):
            seg = x[t0 + int(a0 * sr):t0 + int(a1 * sr)]
            X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 16)) ** 2 / len(seg)
            acc[k] = acc[k] + X
    f = np.fft.rfftfreq(1 << 16, 1.0 / sr)
    A = 10 * np.log10(acc[0] + 1e-30)
    b = np.flatnonzero((f > lo) & (f < hi))
    pk = [i for i in b if A[i] >= A[(f > f[i] * 0.996) & (f < f[i] * 1.004)].max()]
    top = max(A[i] for i in pk)
    pk = [i for i in pk if A[i] > top + floor_db]
    out = []
    for i in pk:
        e1 = 10 * np.log10(acc[1][i - 2:i + 3].sum() + 1e-30)
        e2 = 10 * np.log10(acc[2][i - 2:i + 3].sum() + 1e-30)
        dbs = max(20.0, (e1 - e2) / (0.185 - 0.06))
        out.append((float(f[i] / f0), float(A[i] - top), float(dbs)))
    return out


C.PARAMS = ("jingle_scale", "slow_share", "slow_dbs", "click_cal_db", "click_dbs",
            "click_stroke_slope", "chiff_volume", "chiff_width", "chiff_bandwidth",
            "jingle_jitter", "sustain_jitter")
C.FLOOR = {"slow_share": 0.005, "click_stroke_slope": 0.05, "click_cal_db": 1.0}


def flatness(chs, sr):
    """4-16 kHz spectral flatness at 30-150 ms: whether the jingles RING
    (0.06-0.12 recorded) -- the grid cannot tell a ring from a hiss at the
    same band levels."""
    t0 = C.onset(chs, sr)
    x = sum(chs)
    seg = x[t0 + int(0.03 * sr):t0 + int(0.15 * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 14)) ** 2
    f = np.fft.rfftfreq(1 << 14, 1.0 / sr)
    P = X[(f > 4000) & (f < 16000)] + 1e-30
    return float(np.exp(np.mean(np.log(P))) / np.mean(P))


def fit(recs, rflat, vels, maxfev):
    from scipy.optimize import minimize
    import percussion_map as PM
    cls = PM.PERCUSSION[NOTE][1]
    cls.band_trim_db = ()
    x0 = [max(float(getattr(cls, k)), C.FLOOR.get(k, 1e-3)) for k in C.PARAMS]
    best = [1e9, None, None]

    def f(z):
        vals = np.exp(z) * np.array(x0)
        C.set_params(cls, vals)
        model, mflat = [], []
        for v in vels:
            chs, sr = C.render(NOTE, v)
            model.append(C.norm(C.grid(chs, sr)))
            mflat.append(flatness(chs, sr))
        e, trim = C.score(model, recs)
        ef = float(np.sqrt(np.mean(np.square(10 * np.log10(np.array(mflat) / np.array(rflat))))))
        tot = float(np.sqrt(e * e + ef * ef))
        if tot < best[0]:
            best[:] = [tot, vals, trim]
            print("   %6.3f dB (grid %.2f flat %.2f)  %s  trim %s" % (
                tot, e, ef, " ".join("%s=%.4g" % (k[:12], v) for k, v in zip(C.PARAMS, vals)),
                " ".join("%+.1f" % t for t in trim)), flush=True)
        return tot
    n = len(C.PARAMS)
    simplex = np.vstack([np.zeros(n)] + [0.4 * np.eye(n)[i] * (1 if i % 2 else -1) for i in range(n)])
    minimize(f, np.zeros(n), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02,
                      "adaptive": True})
    return best


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    refs = pos[0] if pos else os.path.expanduser("~/Documents/refs/tambourine")
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    if "--modes" in argv:
        ms = modes(refs)
        print("== %d jingle modes over 1 kHz" % len(ms))
        print("    DRUM_MODES = (%s)" % ", ".join("(%.4f, %.1f, %.0f)" % m for m in ms))
        return 0
    ss = strokes(refs)
    gs = grouped(ss)
    print("== Iowa tambourines, %d strokes: %s" % (len(ss), "  ".join(
        "%s %.0f" % (n, l - max(s[1] for s in ss)) for _, l, _, n in ss)))
    cache = {}
    if "--fit" in argv:
        vels = [C.model_velocity(NOTE, gs[g][0], cache) for g in C.GROUPS]
        recs = [C.norm(np.where(gs[g][1] < -100, -200.0, gs[g][1])) for g in C.GROUPS]
        recs = [np.where(gs[g][1] < -100, -200.0, r) for g, r in zip(C.GROUPS, recs)]
        maxfev = int(next((a.split("=")[1] for a in argv if a.startswith("--maxfev=")), 200))
        print("== fit at velocities %s" % vels, flush=True)
        rflat = []
        for g in C.GROUPS:
            fl = []
            for p in sorted(glob.glob(os.path.join(refs, "tb*.normal.%s.wav" % DYN[g]))):
                a, sr = read(p)
                fl.append(flatness([a[:, 0], a[:, 1]], sr))
            rflat.append(float(np.mean(fl)))
        print("== recorded flatness %s" % " ".join("%.3f" % x for x in rflat), flush=True)
        e, vals, trim = fit(recs, rflat, vels, maxfev)
        print("   BEST %.3f dB" % e)
        for k, v in zip(C.PARAMS, vals):
            print("    %s = %.6g" % (k, v))
        print("    band_trim_db = (%s)" % ", ".join("(%.0f, %.1f)" % (c, t) for c, t in zip(C.CENTRES, trim)))
        return 0
    for g in C.GROUPS:
        drop, gr = gs[g]
        C.show("recorded %s (%.1f dB)" % (g, drop), gr)
        if "--model" in argv:
            v = C.model_velocity(NOTE, drop, cache)
            chs, sr = C.render(NOTE, v)
            m = C.grid(chs, sr)
            d = (m - m.max()) - gr
            C.show("model v%d, minus recorded" % v, np.where(gr < -100, np.nan, d))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
