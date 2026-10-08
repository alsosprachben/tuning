#!/usr/bin/env python3
"""Fit the timpani (GM 47) to VSCO 2 CE's: the modes, their levels and decays.

    python3 examples/timpani_fit.py [REFS] [--files] [--model]

REFS (default ~/Documents/refs/timpani/raw) holds Versilian's single strokes,
Timpani<drum>_Hit_v<velocity>_rr<take>_Sum.wav: five drums, velocities 1, 3
and 4 (drum 1 has no 4), two takes each (CC0; ~/Documents/refs/sources.md).
The files are not named by note, and every other kettle on the stage rings in
sympathy under each stroke, so each one is read by its MODE SERIES:

  principal  the (1,1) mode, per drum: DRUM_F1, read where the struck
             drum's own modes outlast the stick (0.3-1 s) and every
             neighbour is quieter -- a search over the whole series latched
             onto the NEIGHBOURS' principals, which ring under every stroke --
             and refined per file within 3%
  ratios     each mode's own peak near its expected place, as a ratio to f1
  levels     dB under the principal, 50-300 ms (after the stick's noise)
  decay      each mode's amplitude decay, dB/s, from its band's envelope (mode_decay)
  thump      the (0,1) mode, the low thud a stroke has and a pitch does not:
             the strongest peak at 0.45-0.90 f1 in the first 60 ms, and how
             fast it goes

--files prints each file; otherwise per drum and velocity, then overall.
--fit fits the class's numbers to every stroke (fit()).
--model renders GM 47 at each drum's nearest note and each layer's velocity,
dry, and reads it the same way.
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from voicefit import analytic_env, mono, partial_slope  # noqa: E402

EXPECT = (1.0, 1.5, 2.0, 2.45, 2.9)
TOL = 0.05
# Each drum's principal, read late in its own strokes (0.3-1 s): 89.7 Hz
# with 1.54 and 2.02 over it, 121.8 (1.48, 1.99, 2.43), 142.5 (1.48, 1.94,
# 2.40), 168.9 (1.46, 1.92), 191.2 (1.48, 1.92, 2.35). Not equal-tempered
# notes; the drums are tuned as the player left them.
DRUM_F1 = {1: 89.7, 2: 121.8, 3: 142.5, 4: 168.9, 5: 191.2}


def spectrum(x, sr, t0, t1):
    seg = x[int(t0 * sr):int(t1 * sr)]
    N = 1 << 19
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    return np.fft.rfftfreq(N, 1.0 / sr), X


def peak_near(f, X, fc, tol):
    b = (f > fc * (1 - tol)) & (f < fc * (1 + tol))
    if not b.any():
        return None, 0.0
    i = int(np.argmax(X[b]))
    return float(f[b][i]), float(X[b][i])


def mode_decay(x, sr, fm, wd, t0=0.08, t1=1.5, drop=25.0):
    """A mode's amplitude decay, dB/s: its band's envelope, smoothed over
    50 ms -- longer than the beat against a neighbour's sympathetic ring --
    fitted as a line from t0 until it has fallen `drop` dB, or t1.
    voicefit.partial_slope reads its floor from the file's last tenth, and
    these files end with the drums still ringing."""
    e = analytic_env(x, sr, fm - wd, fm + wd)
    w = int(0.05 * sr)
    e = np.convolve(e, np.ones(w) / w, 'same')
    a, b = int(t0 * sr), min(len(e) - w, int(t1 * sr))
    if b - a < int(0.2 * sr):
        return None
    db = 20 * np.log10(np.maximum(e[a:b], 1e-12) / max(e[a], 1e-12))
    under = np.flatnonzero(db < -drop)
    if len(under):
        db = db[:under[0]]
    if len(db) < int(0.15 * sr):
        return None
    t = np.arange(len(db)) / float(sr)
    s, _ = np.polyfit(t, db, 1)
    return -s if s < 0 else None


def measure(path):
    x, sr = mono(path)
    w = int(0.005 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, 'same'))
    pk = int(np.argmax(e))
    x = x[pk:]
    m = re.search(r'Timpani(\d)_Hit_v(\d)_rr(\d)', os.path.basename(path))
    drum = int(m.group(1))
    f, X = spectrum(x, sr, 0.05, 0.30)
    f1, _ = peak_near(f, X, DRUM_F1[drum], 0.03)
    modes = []
    a1 = peak_near(f, X, f1, 0.01)[1]
    for r in EXPECT:
        fm, a = peak_near(f, X, f1 * r, TOL)
        # the band: 6% of the mode, short of half-way to the next mode or a
        # neighbour's principal, whichever is nearer
        near = [abs(fm - g) for g in DRUM_F1.values() if abs(fm - g) > 0.02 * fm]
        near += [abs(fm - f1 * q) for q in EXPECT if abs(fm - f1 * q) > 0.02 * fm]
        wd = max(1.5, min(0.06 * fm, 0.45 * min(near)))
        d = mode_decay(x, sr, fm, wd)
        modes.append((fm / f1, 20 * np.log10(max(a, 1e-12) / a1), d))
    # the thump, early
    fe, Xe = spectrum(x, sr, 0.0, 0.06)
    b = (fe > 0.45 * f1) & (fe < 0.9 * f1)
    i = int(np.argmax(Xe[b]))
    ft = float(fe[b][i])
    ae = peak_near(fe, Xe, f1, 0.02)[1]
    dt = partial_slope(x, sr, ft, 0.05 * ft, f1)
    return dict(drum=drum, vel=int(m.group(2)), take=int(m.group(3)), f1=f1,
                modes=modes, thump=(ft / f1, 20 * np.log10(Xe[b][i] / max(ae, 1e-12)),
                                    None if dt is None else -dt),
                peak=float(np.max(np.abs(x))))


def note_name(f):
    n = 69 + 12 * np.log2(f / 440.0)
    k = int(round(n))
    return "%s%d%+.0fc" % (['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][k % 12],
                           k // 12 - 1, 100 * (n - k))


def show(rows, title):
    print("== %s: %d strokes" % (title, len(rows)))
    print("   drum v  f1 (note)          ratios                         levels dB re (1,1)          decays dB/s"
          "                 thump: ratio dB t-dec")
    keys = sorted({(r['drum'], r['vel']) for r in rows})
    for k in keys:
        rs = [r for r in rows if (r['drum'], r['vel']) == k]
        f1 = np.median([r['f1'] for r in rs])
        rat = np.median([[m[0] for m in r['modes']] for r in rs], 0)
        lev = np.median([[m[1] for m in r['modes']] for r in rs], 0)
        dec = [np.median([m[i][2] for m in (r['modes'] for r in rs) if m[i][2] is not None] or [np.nan])
               for i in range(len(EXPECT))]
        th = np.median([r['thump'][:2] for r in rs], 0)
        tdc = [r['thump'][2] for r in rs if r['thump'][2] is not None]
        print("   %d    %d  %6.1f (%-8s) %s   %s   %s   %.2f %+5.1f %5.0f" % (
            k[0], k[1], f1, note_name(f1),
            " ".join("%.3f" % v for v in rat), " ".join("%5.1f" % v for v in lev),
            " ".join("%5.1f" % v for v in dec), th[0], th[1], np.median(tdc) if tdc else np.nan))
    rat = np.median([[m[0] for m in r['modes']] for r in rows], 0)
    lev = np.median([[m[1] for m in r['modes']] for r in rows], 0)
    print("   ALL ratios %s   levels %s" % (" ".join("%.3f" % v for v in rat),
                                          " ".join("%5.1f" % v for v in lev)))


def fit(rows):
    """The class's numbers from every stroke.

    LEVELS AND THE STROKE. A stroke's level P is its peak against its own
    drum's loudest layer (v4; drum 1 has none, so its v3 + the 11 dB the
    others' v3 sit under their v4). Each mode's level under the principal is
    fitted as a_m + c log2(ratio_m) (P - P_mf): a_m its level at mf (v3, P_mf
    = -11 dB), c how far a harder stroke tilts the modes toward the top, in dB
    per octave of mode ratio per dB of stroke.

    DECAYS, per mode, with one register law: log D = log d_m + s log(f1/415),
    D in tonelib's convention (half the amplitude dB/s), soft-L1 so a mode
    beating against a neighbour's ring cannot steer it."""
    from scipy.optimize import least_squares
    top = {}
    for d in {r['drum'] for r in rows}:
        v4 = [r['peak'] for r in rows if r['drum'] == d and r['vel'] == 4]
        v3 = [r['peak'] for r in rows if r['drum'] == d and r['vel'] == 3]
        top[d] = (20 * np.log10(np.median(v4)) if v4 else 20 * np.log10(np.median(v3)) + 11.0)
    P = np.array([20 * np.log10(r['peak']) - top[r['drum']] for r in rows])
    ratios = np.median([[m[0] for m in r['modes']] for r in rows], 0)
    L = np.array([[m[1] for m in r['modes']] for r in rows])
    lr = np.log2(ratios)

    def res(p):
        a, c = p[:len(EXPECT) - 1], p[-1]
        return (a[None, :] + c * lr[None, 1:] * (P[:, None] + 11.0) - L[:, 1:]).ravel()
    r = least_squares(res, [0.0] * (len(EXPECT) - 1) + [0.5], loss='soft_l1', f_scale=3.0)
    a, c = r.x[:-1], r.x[-1]
    miss = float(np.median(np.abs(res(r.x))))
    pts = [(i, r_['f1'], m[2] / 2.0) for r_ in rows for i, m in enumerate(r_['modes'])
           if m[2] is not None and m[2] > 0]
    mi = np.array([p_[0] for p_ in pts])
    fr = np.array([p_[1] for p_ in pts])
    D = np.array([p_[2] for p_ in pts])

    def rd(p):
        return np.log(p[mi]) + p[-1] * np.log(fr / 415.0) - np.log(D)
    q = least_squares(rd, [10.0] * len(EXPECT) + [0.5], bounds=([0.1] * len(EXPECT) + [-1.0],
                                                                  [500.0] * len(EXPECT) + [3.0]),
                      loss='soft_l1', f_scale=0.3)
    return dict(ratios=ratios, gains_db=np.concatenate([[0.0], a]), tilt=c, level_miss=miss,
                decays=q.x[:-1], slope=q.x[-1], decay_miss=float(np.median(np.abs(rd(q.x)))),
                n_decay=len(pts))


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    refs = pos[0] if pos else os.path.expanduser("~/Documents/refs/timpani/raw")
    rows = [measure(p) for p in sorted(glob.glob(os.path.join(refs, "Timpani*_Hit_*.wav")))]
    if "--files" in argv:
        for r in rows:
            print("  %d v%d rr%d f1 %6.1f  %s" % (r['drum'], r['vel'], r['take'], r['f1'],
                                                 " ".join("%.3f" % m[0] for m in r['modes'])))
    show(rows, "VSCO timpani")
    if "--model" in argv:
        # each drum at its nearest note, each layer at the velocity its stroke
        # level maps to under the renderer's (velocity/127)^2: v1 -28 dB under
        # the loudest, v3 -11, v4 0
        os.environ.setdefault("TUNING_REFLECT", "0")
        os.environ.setdefault("TUNING_MASTER_DB", "-14")
        import blockrender as B
        import patch_map as PM
        from pizz_model_notes import one
        from roomtail import write_wav
        out = os.path.join(os.path.dirname(os.path.normpath(refs)), "model")
        os.makedirs(out, exist_ok=True)
        notes = {d: int(round(69 + 12 * np.log2(f / 440.0))) for d, f in DRUM_F1.items()}
        for d, n in notes.items():
            for v, vel in ((1, 23), (3, 67), (4, 127)):
                write_wav(os.path.join(out, "Timpani%d_Hit_v%d_rr1_Sum.wav" % (d, v)),
                          one(PM.BOWED_SPLIT, 47, n, vel=vel, secs=4.0), B.SR)
        DRUM_F1.update({d: 440.0 * 2 ** ((n - 69) / 12.0) for d, n in notes.items()})
        show([measure(p_) for p_ in sorted(glob.glob(os.path.join(out, "Timpani*_Hit_*.wav")))],
             "model")
    if "--fit" in argv:
        F = fit(rows)
        print("mode_ratios %s" % " ".join("%.3f" % v for v in F['ratios']))
        print("mode levels at mf, dB re (1,1): %s  (gains %s)" % (
            " ".join("%.1f" % v for v in F['gains_db']),
            " ".join("%.3f" % 10 ** (v / 20) for v in F['gains_db'])))
        print("stroke tilt %.2f dB per octave of ratio per dB of stroke  (median miss %.1f dB)"
              % (F['tilt'], F['level_miss']))
        print("mode decays at 415 Hz (tonelib's D): %s  register slope %.2f  (%d points, median |log err| %.2f)"
              % (" ".join("%.1f" % v for v in F['decays']), F['slope'], F['n_decay'], F['decay_miss']))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
