"""GS 105.16 Gopichant against Rajobrata's ektara (Pianobook, "The Ektara";
measure only, never sent): each note's medium BENT take, C3-A3, then ours at
its pitch and velocity 90 -- the scoop heard side by side. Writes
OUT/gopichant_ab.wav, the take then ours per note, 2.2 s each.

    python3 examples/gopichant_ab.py OUT
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
from drum_fit import read  # noqa: E402

D = os.path.expanduser("~/Documents/refs/ektara_pianobook/unz/The Ektara - Decent Samples Patch/"
                       "The Ektara/Processed/Bends")
NOTES = (("C", 48), ("D", 50), ("E", 52), ("G", 55), ("A", 57))
SEG = 2.2


def main(argv):
    import blockrender as B
    import pluck_fit as P
    P.PROG, P.CLS, P.BANK = 105, "GopichantProperties", 16
    out = []
    for n, m in NOTES:
        p = sorted(glob.glob(os.path.join(D, "*Bend %s3 %d RR1 Medium*.wav" % (n, m))))[0]
        x, sr = read(p)
        x = x.reshape(len(x), -1).mean(1)
        a = int(np.flatnonzero(np.abs(x) > 0.05 * np.abs(x).max())[0])
        x = x[a:a + int(SEG * sr)]
        y, s2 = P.render(440.0 * 2 ** ((m - 69) / 12.0), SEG)
        y = y[int(np.flatnonzero(np.abs(y) > 0.05 * np.abs(y).max())[0]):][:int(SEG * sr)]
        for z in (x, y):
            seg = np.zeros(int(SEG * sr))
            seg[:len(z)] = z * 0.5 / np.abs(z).max()
            out.append(seg)
    w = np.concatenate(out)
    f = os.path.join(argv[1], "gopichant_ab.wav")
    B.write_wav(f, w, w)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
