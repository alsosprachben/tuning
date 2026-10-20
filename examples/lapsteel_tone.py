#!/usr/bin/env python3
"""The lap steel's TONE (GS 26.8): its pickup's resonance and Q -- the coil
loaded by a tone control rolled back -- fitted to the open strings' colour.

    python3 examples/lapsteel_tone.py        grid over (resonance Hz, Q)

An electric's colour is its pickup, its tone pot and its amp, not a body: the
recording runs 10-30 dB under the archtop's from 1.2 to 3.2 kHz, which is a
resonance pulled low and damped. Scored as pluck_fit.py measures BANDS (the
harmonics pooled by third octave at 0.1-0.3 s, re the note's harmonic power),
160 Hz-2.5 kHz only -- above it, at this darkness, the take's harmonics are
under its own hiss (it reads 7-16 dB over any fit at 3-5 kHz).
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
import pluck_fit as PF  # noqa: E402
import tonelib as T  # noqa: E402

PF.PROG, PF.CLS, PF.BANK = 26, "HawaiianGuitarProperties", 8
PF.STAGED = os.path.join(PF.REFS, "staged", "lapsteel")
PF.T_END = 8.0
PF.TUNER = "hybrid440:443.92"
BAND = (PF.CEN >= 160) & (PF.CEN <= 2600)


def recorded():
    out = []
    for p in sorted(glob.glob(os.path.join(PF.STAGED, "*.wav"))):
        f0 = float(re.search(r"_f0_([0-9.]+)\.wav$", p).group(1))
        x, sr = PF.read(p)
        out.append((f0, PF.measure(x, sr, f0)[3]))
    return out


def score(rec, res, q):
    C = T.HawaiianGuitarProperties
    C.pickup_resonance_hz, C.pickup_q = res, q
    d = []
    for f0, rb in rec:
        x, sr = PF.render(f0, 1.5)
        ob = PF.measure(x, sr, f0)[3]
        m = BAND & np.isfinite(rb) & np.isfinite(ob)
        d.append(rb[m] - ob[m])
    d = np.concatenate(d)
    return float(np.sqrt(np.mean((d - d.mean()) ** 2)))


def main():
    rec = recorded()
    best = None
    for res in (500.0, 650.0, 800.0, 1000.0, 1250.0, 1600.0):
        for q in (0.3, 0.5, 0.8, 1.2):
            s = score(rec, res, q)
            print("  resonance %5.0f Hz  Q %.1f  -> %.2f dB rms" % (res, q, s), flush=True)
            if best is None or s < best[0]:
                best = (s, res, q)
    print("  best: pickup_resonance_hz = %.0f, pickup_q = %.2f (%.2f dB rms)" % (best[1], best[2], best[0]))


if __name__ == "__main__":
    main()
