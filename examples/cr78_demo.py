"""The CR-78 set (drum program 27) in a late-70s preset-style groove: closed
hats in eighths, the open hat on the and of four, the kick on one and three,
snare 1 on two and four, rim and bongos between, the guiro every other bar,
the tambourine on the off-beats, a metallic beat on each bar's last
sixteenth, a fill down the six toms. Writes OUT/cr78_groove.wav (and
_room.wav), and each of the set's own voices alone as OUT/cr78_voices.wav.

    python3 examples/cr78_demo.py OUT
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import tr909_demo as D       # noqa: E402

D.TEMPO = 116.0
VOICES = (36, 35, 37, 38, 40, 41, 43, 45, 47, 48, 50, 42, 46, 54, 60, 61, 70, 74, 75, 80, 81)


def groove():
    ev = []
    for bar in range(8):
        b0 = bar * 4
        for k in range(8):
            if k == 7:
                ev.append((b0 + 3.5, 46, 80))
            else:
                ev.append((b0 + k / 2.0, 42, 84 if k % 2 == 0 else 64))
        ev.append((b0, 36, 110))
        ev.append((b0 + 2, 36, 104))
        if bar == 7:
            ev.append((b0 + 1, 38, 104))
            for i, n in enumerate((50, 48, 47, 45, 43, 41)):
                ev.append((b0 + 2 + i / 3.0, n, 100 - 3 * i))
            continue
        ev.append((b0 + 1, 38, 104))
        ev.append((b0 + 3, 38, 104))
        ev.append((b0 + 1.75, 37, 70))
        ev.append((b0 + 2.75, 60, 76))
        ev.append((b0 + 3.25, 61, 72))
        for k in range(4):
            ev.append((b0 + k + 0.5, 54, 58))
        if bar % 2:
            ev.append((b0 + 2, 74, 80))
        ev.append((b0 + 3.75, 80 if bar % 2 else 81, 74))
        if bar in (3, 6):
            ev.append((b0 + 0.5, 70, 70))
            ev.append((b0 + 1.5, 75, 78))
    ev.append((32, 36, 112))
    return D._mid(ev, 36, program=27)


def voices():
    return D._mid([(1.5 * i, n, 100) for i, n in enumerate(VOICES)], 1.5 * len(VOICES) + 2,
                  program=27)


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    for name, mf in (("cr78_groove", groove()), ("cr78_voices", voices())):
        L, R = B.render(mf)[:2]
        L, R = np.asarray(L, float), np.asarray(R, float)
        g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
        f = os.path.join(out, name + ".wav")
        B.write_wav(f, L * g, R * g)
        if name == "cr78_groove":
            subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                            os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
        print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
