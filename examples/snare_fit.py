#!/usr/bin/env python3
"""Fit the kit's snare (GM 38) to DrumGizmo DRSKit's.

    python3 examples/snare_fit.py [REFS] [--modes] [--model] [--fit [--maxfev=N]]

REFS (default ~/Documents/refs/drums/drskit) holds Snare/ as
examples/remote_zip.py pulled it from DRSKit 2.1 (CC-BY 4.0; ~/Documents/refs/
sources.md): 29 stick strokes, wires on, about 30 dB from the softest to the
hardest, read on the snare's two close microphones, top and bottom, summed in
power -- the top hears the head, the bottom the wires.

WHY NOT drum_fit.py. A snare is not a tom with a buzz. Its head is damped and
its wires are loud, so by the 0.15 s drum_fit reads the settled modes at, the
drum has fallen 50 dB and what is left is the rack tom ringing in sympathy
(121 Hz, on the snare mics). So:

  --modes  the head's modes from the EARLY spectrum (5-60 ms) of the upper
           half of the strokes: every peak within 30 dB of the strongest,
           150 Hz - 2.5 kHz, as ratios to the lowest (196 Hz, every stroke)
           and amplitude gains
  --model  the band-by-time grid, recorded against our render, as
           examples/crash_fit.py reads a crash, on windows sized to a snare
  --fit    the class's decay and wires, with the band trim solved inside
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

import crash_fit as C  # noqa: E402
from drum_fit import CH, read  # noqa: E402

NOTE = 38
MICS = ("Snare_top", "Snare_bottom")
# a snare is over in a third of a second: windows sized to it
C.EDGES = (125, 250, 500, 1000, 2000, 4000, 8000, 16000)
C.T = ((0.000, 0.005), (0.005, 0.015), (0.015, 0.030), (0.030, 0.060), (0.060, 0.100),
       (0.10, 0.16), (0.16, 0.25), (0.25, 0.40), (0.40, 0.70))
C.CENTRES = tuple(float(np.sqrt(a * b)) for a, b in zip(C.EDGES[:-1], C.EDGES[1:]))
# THE FIRST 15 MS ARE THE KERNEL'S, NOT THE FIT'S. The fast renderer ramps
# every onset over one block (BLK = 512, 10.7 ms), so the crack of a stick on
# a snare -- most of this drum -- cannot arrive in the first two windows at
# full level whatever the parameters say. Weighed by the stroke's TOTAL
# energy, that shortfall made everything after it read as too long, and the
# fit paid for the onset with the decay. So the grid is levelled on the energy
# after 15 ms, and the first two windows weigh little.
C.COL_W = np.array([0.1, 0.2] + [1.0] * (len(C.T) - 2))


def _norm(g):
    return g - 10 * np.log10((10 ** (g[:, 2:] / 10)).sum())


C.norm = _norm
# the head's two rates and its slow remainder; the wires' level, rate and
# stroke law; the noise that makes them a buzz rather than a chord
C.PARAMS = ("fund_dbs", "head_dbs", "slow_share", "slow_dbs", "click_cal_db", "click_dbs",
            "click_stroke_slope", "chiff_volume", "chiff_width", "chiff_bandwidth",
            "sustain_jitter")
C.FLOOR = {"sustain_jitter": 0.005, "slow_share": 0.005, "click_stroke_slope": 0.05,
           "click_cal_db": 1.0}
_render = C.render
C.render = lambda note, vel, secs=1.0: _render(note, vel, secs)   # a snare is over in 0.7 s


def strokes(refs):
    out = []
    for p in sorted(glob.glob(os.path.join(refs, "Snare", "*.wav")), key=C.layer_of):
        a, sr = read(p)
        out.append((C.layer_of(p), [a[:, CH[m]] for m in MICS], sr))
    return out


def modes(ss, lo=150.0, hi=2500.0, floor_db=-30.0):
    acc = None
    for _, chs, sr in ss[len(ss) // 2:]:
        t0 = C.onset(chs, sr)
        P = None
        for c in chs:
            seg = c[t0 + int(0.005 * sr):t0 + int(0.060 * sr)]
            X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 16)) ** 2
            P = X if P is None else P + X
        acc = P if acc is None else acc + P
    f = np.fft.rfftfreq(1 << 16, 1.0 / sr)
    A = np.sqrt(acc)
    b = (f > lo) & (f < hi)
    fb, Ab = f[b], A[b]
    pk = []
    for i in np.flatnonzero((Ab[1:-1] > Ab[:-2]) & (Ab[1:-1] >= Ab[2:])) + 1:
        near = np.abs(fb - fb[i]) < 0.025 * fb[i]
        if Ab[i] >= Ab[near].max():
            pk.append(i)
    top = max(Ab[i] for i in pk)
    pk = [i for i in pk if Ab[i] > top * 10 ** (floor_db / 20.0)]
    f1 = fb[pk[0]]
    return [(float(fb[i] / f1), float(Ab[i] / top)) for i in pk], float(f1)


def flatness(chs, sr):
    """1-8 kHz spectral flatness (1 = white, 0 = a tone) at 15-60 and 60-150
    ms: whether the wires BUZZ. The grid cannot tell a buzz from a chord of
    sines at the same band levels, and a chord is what the first fit made."""
    t0 = C.onset(chs, sr)
    x = sum(chs)
    out = []
    for a, b in ((0.015, 0.060), (0.060, 0.150)):
        seg = x[t0 + int(a * sr):t0 + int(b * sr)]
        X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 14)) ** 2
        f = np.fft.rfftfreq(1 << 14, 1.0 / sr)
        P = X[(f > 1000) & (f < 8000)] + 1e-30
        out.append(float(np.exp(np.mean(np.log(P))) / np.mean(P)))
    return np.array(out)


def full_score(model, recs, mflat, rflat):
    """The grid (levelled after 15 ms), plus what it is blind to: the
    strike's spectral BALANCE in its first two windows -- the renderer's
    ramp limits how fast it arrives, not its colour -- and the buzz."""
    e, trim = C.score(model, recs)
    on = []
    for m, r in zip(model, recs):
        for j in (0, 1):
            mm = m[:, j] + trim
            ok = r[:, j] > r[:, j].max() - 40.0
            d = (mm - mm[ok].mean()) - (r[:, j] - r[ok, j].mean())
            on.extend(d[ok])
    fl = 10 * np.log10(np.asarray(mflat) / np.asarray(rflat))
    eo = float(np.sqrt(np.mean(np.square(on))))
    ef = float(np.sqrt(np.mean(np.square(fl))))
    return float(np.sqrt(e * e + 0.5 * eo * eo + ef * ef)), trim, (e, eo, ef)


def fit(recs, rflat, vels, maxfev):
    from scipy.optimize import minimize
    import percussion_map as PM
    cls = PM.PERCUSSION[NOTE][1]
    cls.band_trim_db = ()
    x0 = [max(float(getattr(cls, k)), C.FLOOR.get(k, 1e-3)) for k in C.PARAMS]
    best = [1e9, None, None]

    def f(z):
        vals = np.exp(z) * np.array(x0)
        for k, v in zip(C.PARAMS, vals):
            setattr(cls, k, float(v))
        model, mflat = [], []
        for v in vels:
            chs, sr = C.render(NOTE, v)
            model.append(C.norm(C.grid(chs, sr)))
            mflat.append(flatness(chs, sr))
        e, trim, parts = full_score(model, recs, mflat, rflat)
        if e < best[0]:
            best[:] = [e, vals, trim]
            print("   %6.3f dB (grid %.2f onset %.2f buzz %.2f)  %s  trim %s" % (
                e, *parts, " ".join("%s=%.4g" % (k[:12], v) for k, v in zip(C.PARAMS, vals)),
                " ".join("%+.1f" % t for t in trim)), flush=True)
        return e
    n = len(C.PARAMS)
    simplex = np.vstack([np.zeros(n)] + [0.4 * np.eye(n)[i] * (1 if i % 2 else -1) for i in range(n)])
    minimize(f, np.zeros(n), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02,
                      "adaptive": True})
    return best


def grouped(rows):
    """By level, not by layer: DRSKit's layers bunch at the loud end (half of
    them within 5 dB of the hardest), so a third of the layers is no ghost
    note. soft = 15 dB and more under the loudest, mid 6-12, loud the top 3."""
    top = max(l for _, l, _ in rows)
    picks = {"soft": [r for r in rows if r[1] - top <= -15.0],
             "mid": [r for r in rows if -12.0 <= r[1] - top <= -6.0],
             "loud": [r for r in rows if r[1] - top >= -3.0]}
    return {g: (float(np.mean([r[1] for r in rr])) - top,
                np.mean([r[2] - r[2].max() for r in rr], 0)) for g, rr in picks.items()}


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    refs = pos[0] if pos else os.path.expanduser("~/Documents/refs/drums/drskit")
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    ss = strokes(refs)
    if "--modes" in argv:
        ms, f1 = modes(ss)
        print("== %d modes over %.1f Hz" % (len(ms), f1))
        print("    mode_ratios = (%s)" % ", ".join("%.3f" % r for r, _ in ms))
        print("    mode_gains  = (%s)" % ", ".join("%.3f" % g for _, g in ms))
        # the gains re the FIRST mode, which is what mode_gains[0] = 1 means
        g0 = ms[0][1]
        print("    re the first: (%s)" % ", ".join("%.3f" % (g / g0) for _, g in ms))
    rows = [(l, C.level(chs, sr), C.grid(chs, sr)) for l, chs, sr in ss]
    flat = {l: flatness(chs, sr) for l, chs, sr in ss}
    gs = grouped(rows)
    top = max(r[1] for r in rows)
    rflat = [np.mean([flat[r[0]] for r in rows if sel(r[1] - top)], 0) for sel in (
        lambda d: d <= -15.0, lambda d: -12.0 <= d <= -6.0, lambda d: d >= -3.0)]
    print("== DRSKit snare, %d strokes, levels %s dB re the loudest" % (
        len(rows), " ".join("%.0f" % (l - max(r[1] for r in rows)) for _, l, _ in rows)))
    cache = {}
    if "--fit" in argv:
        vels = [C.model_velocity(NOTE, gs[g][0], cache) for g in C.GROUPS]
        recs = [C.norm(gs[g][1]) for g in C.GROUPS]
        maxfev = int(next((a.split("=")[1] for a in argv if a.startswith("--maxfev=")), 200))
        print("== fit at velocities %s" % vels, flush=True)
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
            chs, sr = C.render(NOTE, v, 1.0)
            m = C.grid(chs, sr)
            C.show("model v%d, minus recorded" % v, (m - m.max()) - gr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
