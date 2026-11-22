"""The grand's felt refitted for brightness without jumps in its touch.

Ben (2026-11-21), on the grand after the worn layer was hardened: "very quiet
to the touch, and then suddenly get very loud" -- the layer engaged like a
wall (E4 +9 dB in one velocity step). Taken out, the touch was even but the
grand was 7-13 dB short above 1 kHz, E2-C4, against both VCSL's Steinway B
and GU ("the grand could definitely be brighter").

Fitted on renders: each note's band levels (half octaves, 100 Hz - 11 kHz,
dB re the note's own energy, its first 0.4 s), ours less the Steinway's, at
three dynamics (v40/80/120), weighted where the take has energy; plus a
penalty on any kink in the K loudness by velocity (32..120 by 8) at the keys
where the jumps were heard.

    python3 examples/grand_hammer/grand_bright_fit.py [maxfev] [--resume]
"""
import sys, os, json, time
import numpy as np
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))
os.environ.setdefault("TUNING_REFLECT", "0")
os.environ.setdefault("TUNING_MASTER_DB", "-14")

KEYS = (28, 40, 46, 52, 58, 64, 70, 76, 84)
DYNS = {1: 40, 2: 80, 3: 120}
CURVE_KEYS = (52, 64, 66, 68, 72)
CURVE_VELS = tuple(range(32, 121, 8))
EDGES = 100.0 * 2.0 ** (np.arange(0, 14) / 2.0)        # 100 Hz .. 11.3 kHz
WIN = 0.4

# (attribute, low, high): the felt, its memory, its blow, the worn layer
PARAMS = [("hammer_logk", 8.5, 11.5), ("hammer_logk_slope", 0.2, 1.0),
          ("hammer_p_lo", 1.8, 3.2), ("hammer_p_hi", 2.2, 3.8),
          ("hammer_speed_lo", 0.3, 1.0), ("tonal_dampening", 0.1, 1.5),
          ("hammer_alpha", 0.05, 0.6), ("strike_depth", 0.5, 1.0),
          ("hammer_core_mm", 0.0, 0.8), ("hammer_core_logk", 14.0, 18.5),
          ("hammer_logk_curve", -0.1, 0.2), ("lid_db", 0.0, 9.0)]
LOG = os.environ.get("FIT_LOG", os.path.join(HERE, "grand_bright_fit.log"))


def bands(x, sr):
    x = np.asarray(x, np.float64)
    i = int(np.argmax(np.abs(x) > np.abs(x).max() * 0.05))
    s = x[i:i + int(WIN * sr)]
    P = np.abs(np.fft.rfft(s * np.hanning(len(s)))) ** 2
    f = np.fft.rfftfreq(len(s), 1.0 / sr)
    tot = P[(f > 40) & (f < 16000)].sum() + 1e-30
    return np.array([10 * np.log10(P[(f >= a) & (f < b)].sum() / tot + 1e-6)
                     for a, b in zip(EDGES[:-1], EDGES[1:])])


def _setup(vals):
    import tonelib as T
    G = T.GrandPianoProperties
    for (n, _, _), v in zip(PARAMS, vals):
        setattr(G, n, float(v))
    G.hammer_core_edge_mm = float(vals[[p[0] for p in PARAMS].index("hammer_core_mm")])


def _job(args):
    vals, kind, key, vel = args
    _setup(vals)
    import upright_fit as U
    import sfx_levels as S
    x, sr = U.render(0, key, vel, 1.2)
    if kind == "b":
        return bands(x, sr)
    return S.levels([x], sr)[1]


def targets():
    import upright_fit as U
    U.REF[0] = "steinway"
    out = {}
    for d in DYNS:
        R = U.recordings(d)
        for k in KEYS:
            x, sr = U.load(R[k])
            out[(k, d)] = bands(x, sr)
    return out


def score(vals, pool, tgt, detail=False):
    jobs = [(vals, "b", k, v) for k in KEYS for d, v in DYNS.items()]
    jobs += [(vals, "c", k, v) for k in CURVE_KEYS for v in CURVE_VELS]
    res = pool.map(_job, jobs)
    nb = len(KEYS) * len(DYNS)
    spec = 0.0
    per = {}
    for (_, _, k, v), b, d in zip(jobs[:nb], res[:nb], [d for k in KEYS for d in DYNS]):
        t = tgt[(k, d)]
        w = np.clip((t + 40.0) / 20.0, 0.0, 1.0)
        e = (b - t) * w
        spec += float(np.mean(e ** 2))
        hi = EDGES[:-1] >= 1000
        per[(k, d)] = float(10 * np.log10(np.sum(10 ** (b[hi] / 10)))
                            - 10 * np.log10(np.sum(10 ** (t[hi] / 10))))
    spec /= nb
    kinks = 0.0
    curves = {}
    L = res[nb:]
    for j, k in enumerate(CURVE_KEYS):
        c = np.array(L[j * len(CURVE_VELS):(j + 1) * len(CURVE_VELS)])
        curves[k] = c
        d2 = c[2:] - 2 * c[1:-1] + c[:-2]
        kinks += float(np.sum(np.maximum(np.abs(d2) - 0.7, 0.0) ** 2))
    total = spec + 4.0 * kinks
    if detail:
        return total, spec, kinks, per, curves
    return total, spec, kinks


def main(argv):
    maxfev = int(next((a for a in argv[1:] if a.isdigit()), 300))
    import tonelib as T
    G = T.GrandPianoProperties
    x0 = np.array([getattr(G, n) for n, _, _ in PARAMS], float)
    x0[[p[0] for p in PARAMS].index("hammer_core_mm")] = 0.1
    x0[[p[0] for p in PARAMS].index("hammer_core_logk")] = 16.3
    if "--resume" in argv and os.path.exists(LOG):
        rows = [json.loads(l) for l in open(LOG) if l.startswith("{")]
        if rows:
            x0 = np.array(min(rows, key=lambda r: r["total"])["vals"], float)
    lo = np.array([p[1] for p in PARAMS]); hi = np.array([p[2] for p in PARAMS])
    tgt = targets()
    best = [np.inf, x0]
    with Pool(int(os.environ.get("WORKERS", "6"))) as pool:
        def f(z):
            vals = lo + (hi - lo) * np.clip(z, 0.0, 1.0)
            t0 = time.time()
            tot, sp, kk = score(vals, pool, tgt)
            pen = 100.0 * float(np.sum(np.maximum(np.abs(z - 0.5) - 0.5, 0.0) ** 2))
            with open(LOG, "a") as fh:
                fh.write(json.dumps({"total": tot + pen, "spec": sp, "kinks": kk,
                                     "vals": [float(v) for v in vals], "s": round(time.time() - t0, 1)}) + "\n")
            if tot + pen < best[0]:
                best[0], best[1] = tot + pen, vals
                print("best %.3f (spectrum %.3f, kinks %.3f): %s" % (
                    tot + pen, sp, kk, " ".join("%s=%.4g" % (n, v) for (n, _, _), v in zip(PARAMS, vals))), flush=True)
            return tot + pen
        from scipy.optimize import minimize
        z0 = (np.clip(x0, lo, hi) - lo) / (hi - lo)
        minimize(f, z0, method="Powell", options={"maxfev": maxfev, "xtol": 1e-3, "ftol": 1e-4})
        tot, sp, kk, per, curves = score(best[1], pool, tgt, detail=True)
    print("FINAL %.3f spectrum %.3f kinks %.3f" % (tot, sp, kk))
    print("above 1 kHz, ours less Steinway (v40/v80/v120):")
    for k in KEYS:
        print("  key %d: %s" % (k, " ".join("%+5.1f" % per[(k, d)] for d in DYNS)))
    for k, c in curves.items():
        print("  curve %d steps: %s" % (k, " ".join("%+.1f" % v for v in np.diff(c))))
    print("VALS " + json.dumps({n: float(v) for (n, _, _), v in zip(PARAMS, best[1])}))


if __name__ == "__main__":
    main(sys.argv)
