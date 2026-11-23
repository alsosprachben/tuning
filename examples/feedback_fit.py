#!/usr/bin/env python3
"""The guitar held into FEEDBACK (tonelib.Feedback: GS 30.8 "Feedback Gt.",
31.8 "Gt. Feedback"), measured on open takes (since 2026-11-22: the Pianobook
packs are no longer read, licences.md L7) against ours -- each harmonic's
level over the held note, in 0.2 s frames.

    python3 examples/feedback_fit.py [--ab]

  DISTORTED SpeedY's F4, the G string's 10th fret (Freesound 11805, CC0): its
          fundamental swelling 31 dB over the pluck in ~3 s, then holding
          -> 30.8 (and the swell of 31.8)
  CLEAN   airlynx99's Feedback4/5 (Freesound pack 1365, CC0): the loop's tone
          nearly pure -> 31.8's series (no pluck in them: the series only)
--ab writes each, recorded then ours, to ~/Music/licence_refits.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

R = os.path.expanduser("~/Documents/refs/")
# (reference take, GS program on bank 8, its note, label)
TAKES = (("feedback_open/11805__speedy__dist_feedback_g-3rd_str_10th_fret.wav", 30, 65, "feedback_30_8_vs_speedy_F4"),
         ("feedback_open/11805__speedy__dist_feedback_g-3rd_str_10th_fret.wav", 31, 65, "feedback_31_8_vs_speedy_F4"))
TIMES = (0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0)


def ours(prog, note, secs):
    import sfx_variations as V
    return V.render(V.midi([(0, "cc", 0, 0, 8), (0, "pc", 0, prog, 0), (0.25, "on", 0, note, 100),
                            (0.25 + secs, "off", 0, note, 0)], secs + 1.0)).mean(1)


def ladder(x, sr, f0, times=TIMES, K=8):
    """Each harmonic's level (dB) at each time from the onset."""
    a = int(np.flatnonzero(np.abs(x) > 0.05 * np.abs(x).max())[0])
    x = x[a:]
    N = 1 << 15
    fr = np.fft.rfftfreq(N, 1.0 / sr)
    out = []
    for t in times:
        s = x[int(t * sr):int(t * sr) + int(0.2 * sr)]
        if len(s) < int(0.2 * sr):
            break
        X = np.abs(np.fft.rfft(s * np.hanning(len(s)), N))
        out.append([20 * np.log10(X[np.abs(fr - k * f0) < max(6.0, 0.02 * k * f0)].max() + 1e-9)
                    for k in range(1, K + 1)])
    return np.array(out)


def main(argv):
    import blockrender as B
    from pluck_fit import read
    from scipy.signal import resample_poly
    for rel, prog, note, label in TAKES:
        r, rs = read(R + rel)
        if rs != B.SR:
            r = resample_poly(r, B.SR // 100, rs // 100)
        o = ours(prog, note, 7.5)
        f0 = 440.0 * 2 ** ((note - 69) / 12.0)
        Lr, Lo = ladder(r, B.SR, f0), ladder(o, B.SR, f0)
        print("== %s (h1-h8, dB re each's loudest)" % label)
        for t, a, b in zip(TIMES, Lr - Lr.max(), Lo - Lo.max()):
            print("  t%4.1f rec  %s" % (t, " ".join("%5.0f" % v for v in a)))
            print("        ours %s" % " ".join("%5.0f" % v for v in b))
        if "--ab" in argv:
            from scipy.io import wavfile
            n = int(8 * B.SR)
            y = np.concatenate([r[:n] / np.abs(r[:n]).max(), np.zeros(B.SR), o[:n] / np.abs(o[:n]).max()]) * 0.7
            d = os.path.expanduser("~/Music/licence_refits")
            os.makedirs(d, exist_ok=True)
            wavfile.write(os.path.join(d, label + ".wav"), B.SR, (y * 32767).astype(np.int16))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
