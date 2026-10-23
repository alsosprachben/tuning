"""The TR-707 set (drum program 29) in a mid-80s groove: closed hats in
eighths (the open hat closing each bar), the kick on one and the and of
two, snare 1 with the clap on two and four, a rim on the off-beats, a fill
down the six toms into the 909 crash. Writes OUT/tr707_groove.wav (and
_room.wav), and each of the set's own voices alone as OUT/tr707_voices.wav.

    python3 examples/tr707_demo.py OUT
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import tr909_demo as D       # noqa: E402

D.TEMPO = 112.0
VOICES = (36, 35, 37, 38, 40, 39, 41, 43, 45, 47, 48, 50, 42, 46)


def groove():
    ev = []
    for bar in range(8):
        b0 = bar * 4
        for k in range(8):
            if k == 7:
                ev.append((b0 + 3.5, 46, 82))
            else:
                ev.append((b0 + k / 2.0, 42, 88 if k % 2 == 0 else 66))
        ev.append((b0, 36, 112))
        ev.append((b0 + 1.5, 36, 96))
        if bar == 7:
            for i, n in enumerate((50, 48, 47, 45, 43, 41)):
                ev.append((b0 + 2 + i / 3.0, n, 104 - 3 * i))
            ev.append((b0 + 1, 38, 106))
            ev.append((b0 + 1, 39, 90))
        else:
            for k in (1, 3):
                ev.append((b0 + k, 38, 106))
                ev.append((b0 + k, 39, 90))
            ev.append((b0 + 2.5, 36, 96))
            if bar % 2:
                ev.append((b0 + 3.75, 40, 70))
            ev.append((b0 + 0.75, 37, 64))
        if bar == 0:
            ev.append((b0, 49, 108))
    ev.append((32, 49, 110))
    ev.append((32, 36, 112))
    return D._mid(ev, 36, program=29)


def voices():
    return D._mid([(1.5 * i, n, 100) for i, n in enumerate(VOICES)], 1.5 * len(VOICES) + 2,
                  program=29)


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    for name, mf in (("tr707_groove", groove()), ("tr707_voices", voices())):
        L, R = B.render(mf)[:2]
        L, R = np.asarray(L, float), np.asarray(R, float)
        g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
        f = os.path.join(out, name + ".wav")
        B.write_wav(f, L * g, R * g)
        if name == "tr707_groove":
            subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                            os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
        print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
