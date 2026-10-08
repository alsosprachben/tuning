#!/usr/bin/env python3
"""Fit the kit's crashes (GM 49, 57) to DrumGizmo DRSKit's, struck hard.

    python3 examples/crash_fit.py [REFS] [--model] [--fit [--maxfev=N]] [--crash=49,57]

REFS (default ~/Documents/refs/drums/drskit) holds Crash_left_shank/ and
Crash_right_shank/ as examples/remote_zip.py pulled them from DRSKit 2.1
(CC-BY 4.0; ~/Documents/refs/sources.md): 11 and 12 strokes of the stick's
shank on the edge, the way a kit drummer crashes, ~35 dB from the softest to
the hardest, 6-10 s each, so the whole ring is there. Each is read on the
overheads (OHL and OHR, summed in power): a crash has no close microphone.
The left crash stands for 49 (panned left), the right for 57.

WHY THESE AND NOT IOWA'S. The crashes were fitted to Iowa's 17" and 18"
suspended cymbals, stick on the bow, pp/mf/ff -- a percussionist controlling
the plate. A kit crash is hit far harder, and a hard hit is a different
sound, not a louder one: the stick's shank excites the low modes, and the
plate's nonlinearity then carries that energy UP, so 2-16 kHz swells for
100-400 ms after the strike. Iowa's strokes never reach that regime.

What a stroke is, on a GRID of octave bands (250 Hz - 16 kHz) by time windows
(T below): each cell's mean power in dB, re the stroke's loudest cell, and the
stroke's level (its loudest 150 ms, as drumset_check reads one). Strokes are
grouped by level into soft, mid and loud, and the model is rendered at the
velocities whose level sits as far under velocity 127 as each group sits under
the loudest stroke.

--model renders the GM notes dry and reads them the same way (L and R summed
in power).
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

from drum_fit import CH, read  # noqa: E402

CRASH = {49: "Crash_left_shank", 57: "Crash_right_shank"}
EDGES = (250, 500, 1000, 2000, 4000, 8000, 16000)
T = ((0.000, 0.010), (0.010, 0.030), (0.030, 0.060), (0.060, 0.120), (0.12, 0.25),
     (0.25, 0.50), (0.50, 1.00), (1.0, 1.5), (1.5, 2.5), (2.5, 4.0))
GROUPS = ("soft", "mid", "loud")


def onset(chs, sr):
    p = sum(c * c for c in chs)
    w = int(0.0005 * sr)
    e = np.convolve(p, np.ones(w) / w, 'same')
    return max(0, int(np.flatnonzero(e > 0.01 * e.max())[0]) - int(0.001 * sr))


def level(chs, sr):
    """The loudest 150 ms, RMS dB (drumset_check's reading)."""
    p = sum(c * c for c in chs)
    c = np.concatenate(([0.0], np.cumsum(p)))
    n = int(0.15 * sr)
    m = (c[n:] - c[:-n]).max() / n
    return 10 * np.log10(m + 1e-30)


def grid(chs, sr):
    """Octave bands x windows, mean power dB, absolute."""
    t0 = onset(chs, sr)
    out = np.full((len(EDGES) - 1, len(T)), -200.0)
    for j, (a, b) in enumerate(T):
        i0, i1 = t0 + int(a * sr), t0 + int(b * sr)
        if i1 > len(chs[0]):
            continue
        n = i1 - i0
        N = max(n, 4096)
        f = np.fft.rfftfreq(N, 1.0 / sr)
        P = sum(np.abs(np.fft.rfft(c[i0:i1] * np.hanning(n), N)) ** 2 for c in chs)
        P = P / (n * 0.375)            # mean power, Hann's energy
        for i, (lo, hi) in enumerate(zip(EDGES[:-1], EDGES[1:])):
            out[i, j] = 10 * np.log10(P[(f >= lo) & (f < hi)].sum() * (N / n) / N + 1e-30)
    return out


def layer_of(p):
    return int(re.match(r"(\d+)-", os.path.basename(p)).group(1))


def refs_for(refs, note):
    d = os.path.join(refs, CRASH[note])
    out = []
    for p in sorted(glob.glob(os.path.join(d, "*.wav")), key=layer_of):
        a, sr = read(p)
        chs = [a[:, CH["OHL"]], a[:, CH["OHR"]]]
        out.append((layer_of(p), level(chs, sr), grid(chs, sr)))
    return out


def grouped(strokes):
    """soft / mid / loud: (level re the loudest, mean grid re its own top cell)."""
    top = max(l for _, l, _ in strokes)
    n = len(strokes)
    picks = {"soft": strokes[n // 6:n // 3 + 1], "mid": strokes[n // 2:2 * n // 3 + 1],
             "loud": strokes[-max(2, n // 6):]}
    out = {}
    for g, ss in picks.items():
        gr = np.mean([s[2] - s[2].max() for s in ss], 0)
        out[g] = (float(np.mean([s[1] for s in ss])) - top, gr)
    return out


def render(note, vel, secs=4.2):
    import blockrender as B
    from drumset_check import note_file
    L, R = B.render(note_file(0, note, vel=vel, hold=secs))[:2]
    return [np.asarray(L, np.float64), np.asarray(R, np.float64)], B.SR


def model_velocity(note, drop_db, cache):
    """The velocity whose level sits drop_db under velocity 127's."""
    def lv(v):
        if v not in cache:
            chs, sr = render(note, v, 0.6)
            cache[v] = level(chs, sr)
        return cache[v]
    top = lv(127)
    lo, hi = 1, 127
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if lv(mid) - top < drop_db:
            lo = mid
        else:
            hi = mid
    return hi


def show(title, g):
    print("  %s" % title)
    print("      Hz  " + " ".join("%6s" % ("%g" % (1000 * a)) for a, _ in T) + "   (window start, ms)")
    for i, lo in enumerate(EDGES[:-1]):
        print("   %5d  " % lo + " ".join("%6.1f" % v for v in g[i]))


# THE FIT. Shape parameters searched (in log space, from the class's own
# values); the band trim solved inside each candidate in closed form, because
# a trim scales a band's every cell alike and so cannot be told apart from
# what the shape is doing unless it is re-solved under each shape.
PARAMS = ("ring_peak_hz", "ring_decay_floor", "ring_decay_below", "ring_decay_above",
          "aftersound_fraction", "aftersound_dbs", "bloom_gain", "bloom_seconds",
          "bloom_center_hz", "bloom_octaves", "bloom_swell", "bloom_gain_slope",
          "chiff_volume", "chiff_width")
FLOOR = {"aftersound_fraction": 0.01, "aftersound_dbs": 12.0, "bloom_gain": 0.05,
         "bloom_gain_slope": 0.1, "bloom_seconds": 0.004, "bloom_swell": 0.2,
         "ring_decay_below": 0.5, "ring_decay_above": 0.5}
CENTRES = tuple(float(np.sqrt(a * b)) for a, b in zip(EDGES[:-1], EDGES[1:]))
# 0-10 ms is under one kernel block (BLK = 512): no onset shorter than that
# survives the fast renderer, so that window is weighed lightly
COL_W = np.array([0.3] + [1.0] * (len(T) - 1))


def norm(g):
    """dB re the grid's total energy, so a level offset is not a shape error."""
    return g - 10 * np.log10((10 ** (g / 10)).sum())


def weights(rec):
    # the tail counts: weighted by level alone, a ring 15 dB too long at 2.5 s
    # cost the first fit almost nothing, and that is a crash that will not stop
    # and a cell under -100 dB is past the end of the file (DRSKit's soft
    # snare strokes stop at 0.25 s): silence, not a level, so it weighs nothing
    w = np.clip((rec + 75.0) / 45.0, 0.15, 1.0) * COL_W
    return np.where(rec < -100.0, 0.0, w)


def score(model, recs):
    """(rms dB, trim): the weighted rms over every group's cells after the
    band trim common to all groups is solved for."""
    trim = np.zeros(len(CENTRES))
    for _ in range(4):
        num = np.zeros(len(CENTRES))
        den = np.zeros(len(CENTRES))
        for m, r in zip(model, recs):
            mm = norm(m + trim[:, None])
            w = weights(r)
            num += (w * (mm - r)).sum(1)
            den += w.sum(1)
        trim -= num / den
    trim -= trim.mean()                # a level, which norm() ignores anyway
    err = []
    wsum = 0.0
    for m, r in zip(model, recs):
        w = weights(r)
        err.append((w * (norm(m + trim[:, None]) - r) ** 2).sum())
        wsum += w.sum()
    return float(np.sqrt(sum(err) / wsum)), trim


def set_params(cls, vals):
    for k, v in zip(PARAMS, vals):
        setattr(cls, k, float(v))


def fit(note, recs, vels, maxfev):
    from scipy.optimize import minimize
    import percussion_map as PM
    cls = PM.PERCUSSION[note][1]
    cls.band_trim_db = ()
    x0 = [max(float(getattr(cls, k)), FLOOR.get(k, 1e-3)) for k in PARAMS]
    best = [1e9, None, None]

    def f(z):
        vals = np.exp(z) * np.array(x0)
        set_params(cls, vals)
        model = [norm(grid(*render(note, v))) for v in vels]
        e, trim = score(model, recs)
        if e < best[0]:
            best[:] = [e, vals, trim]
            print("   %6.3f dB  %s  trim %s" % (e, " ".join("%s=%.4g" % (k[:12], v) for k, v in zip(PARAMS, vals)),
                                                " ".join("%+.1f" % t for t in trim)), flush=True)
        return e
    # steps of x1.6 each way in every parameter: zero is not a scale
    n = len(PARAMS)
    simplex = np.vstack([np.zeros(n)] + [0.47 * np.eye(n)[i] * (1 if i % 2 else -1) for i in range(n)])
    minimize(f, np.zeros(n), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02,
                      "adaptive": True})
    return best


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    refs = pos[0] if pos else os.path.expanduser("~/Documents/refs/drums/drskit")
    notes = next((tuple(int(n) for n in a.split("=")[1].split(","))
                  for a in argv if a.startswith("--crash=")), tuple(CRASH))
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    for note in notes:
        strokes = refs_for(refs, note)
        if "--fit" in argv:
            gs = grouped(strokes)
            cache = {}
            vels = [model_velocity(note, gs[g][0], cache) for g in GROUPS]
            recs = [norm(gs[g][1]) for g in GROUPS]
            maxfev = int(next((a.split("=")[1] for a in argv if a.startswith("--maxfev=")), 300))
            print("== GM %d fit at velocities %s" % (note, vels), flush=True)
            e, vals, trim = fit(note, recs, vels, maxfev)
            print("   BEST %.3f dB" % e)
            for k, v in zip(PARAMS, vals):
                print("    %s = %.6g" % (k, v))
            print("    band_trim_db = (%s)" % ", ".join("(%.0f, %.1f)" % (c, t) for c, t in zip(CENTRES, trim)))
            continue
        gs = grouped(strokes)
        print("== GM %d: DRSKit %s, %d strokes, levels %s dB re the loudest" % (
            note, CRASH[note], len(strokes),
            " ".join("%.0f" % (l - max(s[1] for s in strokes)) for _, l, _ in strokes)))
        cache = {}
        for g in GROUPS:
            drop, gr = gs[g]
            show("recorded %s (%.1f dB)" % (g, drop), gr)
            if "--model" in argv:
                v = model_velocity(note, drop, cache)
                chs, sr = render(note, v)
                m = grid(chs, sr)
                m = m - m.max()
                show("model v%d, minus recorded" % v, m - gr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
