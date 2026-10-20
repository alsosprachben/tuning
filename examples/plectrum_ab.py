#!/usr/bin/env python3
"""The plectrum's A/B (tonelib.Plectrum, fitted by examples/plectrum_fit.py):
per note, the recorded take, ours with the pick, ours without it.

    python3 examples/plectrum_ab.py [OUTDIR] [VOICE ...]

Writes OUTDIR/<voice>_pick_recorded_vs_ours.wav (the takes are third-party:
measure and listen locally, never send) and OUTDIR/<voice>_pick_ours.wav (ours
only: with, then without, the same notes). OUTDIR defaults to ~/Downloads.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import plectrum_fit as PF  # noqa: E402

NO_PICK = dict(pick_noise_db=None, pick_slope_db=0.0, course_stagger_s=0.0, chiff_volume=0.0)


def both(voice):
    import tonelib as T
    C = getattr(T, PF.VOICES[voice][0])
    cls, prog, bank, notes, _ = PF.VOICES[voice]
    with_, without = [], []
    for f, midi in notes:
        with_.append(PF.ours(cls, prog, bank, midi))
    keep = {k: getattr(C, k) for k in NO_PICK}
    for k, v in NO_PICK.items():
        setattr(C, k, v)
    try:
        for f, midi in notes:
            without.append(PF.ours(cls, prog, bank, midi))
    finally:
        for k, v in keep.items():
            setattr(C, k, v)
    return with_, without


def main(out, voices):
    from scipy.io import wavfile
    import blockrender as B
    sr = B.SR
    gap = np.zeros(int(0.35 * sr))
    n = int(1.3 * sr)

    def fit(x):
        x = x[:n]
        return np.concatenate([x, np.zeros(n - len(x))]) * 0.5

    for v in voices:
        w, wo = both(v)
        rec = [PF.load(f) for f, _ in PF.VOICES[v][3]]
        ab, ours = [], [[], []]
        for r, a, b in zip(rec, w, wo):
            a0 = int(np.flatnonzero(np.abs(r) > 0.02)[0])
            ab += [fit(r[max(0, a0 - int(0.01 * sr)):]), gap, fit(a), gap, fit(b), gap, gap]
            ours[0] += [fit(a), gap]
            ours[1] += [fit(b), gap]
        d = os.path.join(out, "%s_ab" % v)
        os.makedirs(d, exist_ok=True)
        wavfile.write(os.path.join(d, "%s_pick_recorded_vs_ours.wav" % v), sr,
                      (np.concatenate(ab) * 32767).astype(np.int16))
        o = np.concatenate(ours[0] + [gap, gap] + ours[1])
        wavfile.write(os.path.join(out, "%s_pick_ours.wav" % v), sr, (o * 32767).astype(np.int16))
        print("  %s: %s, %s" % (v, d, os.path.join(out, "%s_pick_ours.wav" % v)))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/Downloads")
    main(out, sys.argv[2:] or ["12str", "mandolin"])
