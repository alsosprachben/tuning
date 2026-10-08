#!/usr/bin/env python3
"""Fit the tubular bells (GM 14) to VSCO 2 CE's: every mode, by register.

    python3 examples/tubular_fit.py [REFS] [--model]

REFS (default ~/Documents/refs/tubular/raw) holds Versilian's four strokes,
TB_hit_<note>_v<layer>_rr1.wav: C4, G4, C5 (v4) and F5 (v3) (CC0;
~/Documents/refs/sources.md). A chime is a free-free TUBE: its modes run near
(2n+1)^2, and the note heard is the octave under the fourth, which the fifth
and sixth sit near 3/2 and 2 of. Each mode is read where SEED puts it, as a
ratio to the written note:

  ratio   the mode's own peak within 6% of its seed, 20-300 ms after the stroke
  level   dB under the fourth mode (the one at twice the note), same window
  decay   amplitude dB/s from its band's envelope (timpani_fit.mode_decay),
          from 80 ms until it has fallen 30 dB or 8 s

Four notes over an octave and a half, so each is fitted as a line in octaves
from G4 (392 Hz): the ratios because a short tube's upper modes compress (the
sixth runs 4.09 at C4 to 3.95 at F5), the levels because the radiation and
the stroke change with the tube; the decays share one register law, as
tonelib's does.
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

from timpani_fit import mode_decay, peak_near, spectrum  # noqa: E402
from voicefit import mono, note_of  # noqa: E402

# the modes, as first read off the four notes (n = 1..10); (2n+1)^2 / 40.5
# gives 0.222 0.617 1.210 2.000 2.988 4.173 5.556 7.136 8.914 10.889
SEED = (0.236, 0.635, 1.230, 2.006, 2.950, 4.040, 5.260, 6.600, 8.150, 9.900)
REF_HZ = 392.0
FLOOR_DB = -45.0


def measure(path):
    x, sr = mono(path)
    w = int(0.005 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, 'same'))
    x = x[int(np.argmax(e)):]
    n = note_of(path)
    fn = 440.0 * 2 ** ((n - 69) / 12.0)
    f, X = spectrum(x, sr, 0.02, 0.30)
    f4, a4 = peak_near(f, X, fn * SEED[3], 0.03)
    modes = []
    for s in SEED:
        fm, a = peak_near(f, X, fn * s, 0.06)
        db = 20 * np.log10(max(a, 1e-12) / a4)
        if db < FLOOR_DB or fm > 0.45 * sr:
            modes.append(None)
            continue
        d = mode_decay(x, sr, fm, max(1.5, 0.02 * fm), t1=8.0, drop=30.0)
        modes.append((fm / fn, db, d))
    return dict(note=n, fn=fn, modes=modes)


def fit(rows):
    from scipy.optimize import least_squares
    out = []
    for i in range(len(SEED)):
        pts = [(np.log2(r['fn'] / REF_HZ), r['modes'][i]) for r in rows if r['modes'][i]]
        if len(pts) < 2:
            out.append(None)
            continue
        o = np.array([p[0] for p in pts])
        rk, r0 = np.polyfit(o, [p[1][0] for p in pts], 1)
        lk, l0 = np.polyfit(o, [p[1][1] for p in pts], 1)
        out.append(dict(r0=r0, rk=rk, l0=l0, lk=lk, n=len(pts)))
    pts = [(i, r['fn'], r['modes'][i][2] / 2.0) for r in rows for i in range(len(SEED))
           if r['modes'][i] and r['modes'][i][2]]
    mi = np.array([p[0] for p in pts])
    fr = np.array([p[1] for p in pts])
    D = np.array([p[2] for p in pts])

    def rd(p):
        return np.log(p[mi]) + p[-1] * np.log(fr / 415.0) - np.log(D)
    q = least_squares(rd, [2.0] * len(SEED) + [0.5],
                      bounds=([0.01] * len(SEED) + [-1.0], [500.0] * len(SEED) + [3.0]),
                      loss='soft_l1', f_scale=0.3)
    used = sorted(set(mi.tolist()))
    return out, {i: q.x[i] for i in used}, q.x[-1], float(np.median(np.abs(rd(q.x))))


def show(rows, title):
    print("== %s" % title)
    for r in rows:
        print("   %3d %6.1f Hz" % (r['note'], r['fn']))
        print("      ratio " + " ".join("%6.3f" % m[0] if m else "     -" for m in r['modes']))
        print("      dB    " + " ".join("%6.1f" % m[1] if m else "     -" for m in r['modes']))
        print("      dB/s  " + " ".join("%6.1f" % m[2] if m and m[2] else "     -" for m in r['modes']))


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    refs = pos[0] if pos else os.path.expanduser("~/Documents/refs/tubular/raw")
    rows = [measure(p) for p in sorted(glob.glob(os.path.join(refs, "TB_hit_*.wav")))]
    rows.sort(key=lambda r: r['note'])
    show(rows, "VSCO tubular bells")
    out, dec, slope, miss = fit(rows)
    print("== fit, in octaves from G4")
    for i, o in enumerate(out):
        if o:
            print("   mode %2d  ratio %.3f %+.3f/oct   level %6.1f %+5.1f dB/oct   D %s  (%d notes)"
                  % (i + 1, o['r0'], o['rk'], o['l0'], o['lk'],
                     "%.2f" % dec[i] if i in dec else "-", o['n']))
    print("   decay register slope %.2f  (median |log err| %.2f)" % (slope, miss))
    if "--model" in argv:
        os.environ.setdefault("TUNING_REFLECT", "0")
        os.environ.setdefault("TUNING_MASTER_DB", "-14")
        import blockrender as B
        import patch_map as PM
        from pizz_model_notes import one
        from roomtail import write_wav
        outd = os.path.join(os.path.dirname(os.path.normpath(refs)), "model")
        os.makedirs(outd, exist_ok=True)
        names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        for r in rows:
            n = r['note']
            write_wav(os.path.join(outd, "TB_hit_%s%d_model.wav" % (names[n % 12], n // 12 - 1)),
                      one(PM.BOWED_SPLIT, 14, n, vel=110, secs=10.0), B.SR)
        m = sorted([measure(p) for p in glob.glob(os.path.join(outd, "TB_hit_*.wav"))],
                   key=lambda r: r['note'])
        show(m, "model")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
