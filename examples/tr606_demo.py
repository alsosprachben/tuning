"""The TR-606 set (drum program 28) in an acid-era groove: closed hats in
sixteenths with every fourth accented, the open hat on the and of four,
the kick on every beat with a push, snare 1 on two and four and snare 2
(the accented 606 snare) for the ghost notes, a fill down the six toms
into the cymbal. Writes OUT/tr606_groove.wav (and _room.wav), and each of
the set's own voices alone as OUT/tr606_voices.wav.

    python3 examples/tr606_demo.py OUT
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import tr909_demo as D       # noqa: E402

D.TEMPO = 126.0
VOICES = (36, 38, 40, 41, 43, 45, 47, 48, 50, 42, 46, 51)


def groove():
    ev = []
    for bar in range(8):
        b0 = bar * 4
        for k in range(16):
            if k == 14:
                ev.append((b0 + 3.5, 46, 84))
            elif k != 15:
                ev.append((b0 + k / 4.0, 42, 96 if k % 4 == 2 else 62))
        for k in range(4):
            ev.append((b0 + k, 36, 110))
        if bar % 2:
            ev.append((b0 + 3.75, 36, 90))
        if bar == 7:
            ev.append((b0 + 1, 38, 106))
            for i, n in enumerate((50, 48, 47, 45, 43, 41)):
                ev.append((b0 + 2 + i / 3.0, n, 104 - 3 * i))
        else:
            ev.append((b0 + 1, 38, 106))
            ev.append((b0 + 3, 38, 106))
            ev.append((b0 + 2.75, 40, 64))
        if bar == 0:
            ev.append((b0, 51, 100))
    ev.append((32, 51, 108))
    ev.append((32, 36, 112))
    return D._mid(ev, 36, program=28)


def voices():
    return D._mid([(1.5 * i, n, 100) for i, n in enumerate(VOICES)], 1.5 * len(VOICES) + 2,
                  program=28)


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    for name, mf in (("tr606_groove", groove()), ("tr606_voices", voices())):
        L, R = B.render(mf)[:2]
        L, R = np.asarray(L, float), np.asarray(R, float)
        g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
        f = os.path.join(out, name + ".wav")
        B.write_wav(f, L * g, R * g)
        if name == "tr606_groove":
            subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                            os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
        print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
