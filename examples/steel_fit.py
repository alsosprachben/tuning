#!/usr/bin/env python3
"""Fit the steel-string acoustic's body (GM 25) to NYU's GuitarSet.

    python3 examples/steel_fit.py --body [--passes=N] [--step=K]
    python3 examples/steel_fit.py --env [--step=K]

The string (decay law, stretch) is fitted by examples/egtr_fit.py
--string=steel; this is what is left, the BODY: SteelGuitarProperties borrows
the Iowa classical's measured formants, and a dreadnought is not a classical.
The notes are egtr_fit's staged set acoustic_steel_mic (GuitarSet's notes that
sound alone, on its microphone).

THE ENVELOPE BY ABSOLUTE FREQUENCY, as the classical's was fitted: a body's
resonances stay put while a note's harmonics slide through them, so every
harmonic of every note (40-140 ms from the pluck, to 12 kHz) is pooled by
WHERE IT SOUNDS into third-octave bands, each note's level removed (its
harmonics' power-mean over 150 Hz-3 kHz). The median per band, recorded and
ours at the same notes, rendered dry; their difference is what the body owes.

  --env    the two envelopes and their difference, by band
  --body   PASSES rounds (3): the difference, damped by half, added to
           body_trim_db (tonelib.FormantBody) and written into tonelib.py
"""
import glob
import os
import re
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)
os.environ.setdefault("TUNING_REFLECT", "0")

import egtr_fit as E  # noqa: E402
from voicefit import mono, note_of  # noqa: E402

PROG = 25
SET = "acoustic_steel_mic"
BANDS = 100.0 * 2 ** (np.arange(0, 23) / 3.0)          # 100 Hz .. 10 kHz centres
FMAX = 12000.0


def harmonics(path):
    """(Hz, dB) of each harmonic, 40-140 ms after the pluck, re the note."""
    x, sr = mono(path)
    x = np.asarray(x, np.float64)
    f0 = 440.0 * 2 ** ((note_of(path) - 69) / 12.0)
    w = int(0.005 * sr)
    e = np.convolve(x * x, np.ones(w) / w, "same")
    on = int(np.flatnonzero(e > e.max() * 0.01)[0])
    seg = x[on + int(0.04 * sr):on + int(0.14 * sr)]
    if len(seg) < int(0.09 * sr):
        return None
    N = 1 << 16
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    out = []
    m = 1
    while m * f0 < FMAX:
        fm = m * f0
        b = (f > fm * 0.97) & (f < fm * 1.03)
        if b.any():
            k = np.argmax(X[b])
            out.append((f[b][k], 10 * np.log10(X[b][k] + 1e-30)))
        m += 1
    if not out:
        return None
    hz = np.array([h for h, _ in out]); db = np.array([d for _, d in out])
    ref = (hz > 150) & (hz < 3000)
    if not ref.any():
        return None
    db -= 10 * np.log10(np.mean(10 ** (db[ref] / 10)))
    return hz, db


def envelope(paths):
    pool = [[] for _ in BANDS]
    for p in paths:
        r = harmonics(p)
        if r is None:
            continue
        for hz, db in zip(*r):
            k = int(np.argmin(np.abs(np.log2(hz / BANDS))))
            if abs(np.log2(hz / BANDS[k])) <= 1 / 6.0:
                pool[k].append(db)
    return np.array([np.median(v) if len(v) >= 5 else np.nan for v in pool]), [len(v) for v in pool]


def ours(paths):
    d = tempfile.mkdtemp(prefix="steel_")
    out = []
    for p in paths:
        q = os.path.join(d, os.path.basename(p))
        E.render_note(PROG, note_of(p), q)
        out.append(q)
    return out


def compare(step):
    rec_paths = sorted(glob.glob(os.path.join(E.STAGED, SET, "*.wav")))[::step]
    R, n = envelope(rec_paths)
    O, _ = envelope(ours(rec_paths))
    return R, O, n


def show(R, O, n):
    print("   band Hz    n   recorded     ours   ours-rec")
    for c, r, o, k in zip(BANDS, R, O, n):
        print("   %7.0f %4d   %8.1f %8.1f %8.1f" % (c, k, r, o, o - r))
    d = O - R
    print("   median |ours-rec| %.2f dB" % np.nanmedian(np.abs(d - np.nanmedian(d))))


def write_trim(pts):
    path = os.path.join(HERE, "tonelib.py")
    s = open(path).read()
    i = s.index("class SteelGuitarProperties(")
    j = s.index("\nclass ", i + 10)
    blk = s[i:j]
    line = "    body_trim_db = (%s)\n" % ", ".join("(%.0f, %.1f)" % (c, v) for c, v in pts)
    if re.search(r"(?m)^    body_trim_db = ", blk):
        blk = re.sub(r"(?m)^    body_trim_db = .*\n", line, blk)
    else:
        blk = blk.rstrip("\n") + "\n" + line
    open(path, "w").write(s[:i] + blk + s[j:])


def fit_body(passes, step):
    import tonelib as T
    trim = dict(T.SteelGuitarProperties.body_trim_db)
    for k in range(passes):
        R, O, n = compare(step)
        d = O - R
        d -= np.nanmedian(d)                 # colour, not level
        print("== pass %d" % (k + 1))
        show(R, O, n)
        for c, v in zip(BANDS, d):
            if np.isfinite(v):
                trim[c] = trim.get(c, 0.0) - 0.5 * v
        pts = sorted((c, v) for c, v in trim.items())
        T.SteelGuitarProperties.body_trim_db = tuple(pts)
        write_trim(pts)
        print("   body_trim_db written: " + " ".join("%.0f:%+.1f" % (c, v) for c, v in pts))


def main(argv):
    step = int(next((a.split("=")[1] for a in argv if a.startswith("--step=")), 3))
    if "--env" in argv:
        show(*compare(step))
        return 0
    if "--body" in argv:
        fit_body(int(next((a.split("=")[1] for a in argv if a.startswith("--passes=")), 3)), step)
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
