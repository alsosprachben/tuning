"""The SC-88 map's TR-808/909 set (CC32 = 2, program 26 on the drums) in a
groove: the 909's kick (35) and the 808's (36) trading beats, the 808's snare
(38) and the 909's (40) on two and four in turn, the 808's hats, cowbell and
cymbal over them. Writes OUT/sc88_808_909.wav (and _room.wav).

    python3 examples/sc88_808_909_demo.py OUT
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import tr909_demo as D       # noqa: E402

D.TEMPO = 112.0


def groove():
    ev = []
    for bar in range(8):
        b0 = bar * 4
        for k in range(8):
            ev.append((b0 + k / 2.0, 46 if k == 7 else 42, 90 if k % 2 == 0 else 66))
        ev.append((b0, 35 if bar % 2 else 36, 112))
        ev.append((b0 + 2.5, 36 if bar % 2 else 35, 104))
        ev.append((b0 + 1, 38 if bar % 2 == 0 else 40, 104))
        ev.append((b0 + 3, 40 if bar % 2 == 0 else 38, 108))
        if bar % 4 == 3:
            ev.append((b0 + 3.5, 56, 90))
    ev.append((32, 35, 112))
    ev.append((32, 49, 110))
    mf = D._mid(ev, 34, program=25)
    tr = mf.tracks[0]
    # a GS reset, then the SC-88 map (CC32 = 2) before the drum set's program
    i = next(j for j, m in enumerate(tr) if m.type == "program_change")
    tr.insert(i, mido.Message("control_change", channel=9, control=32, value=2, time=0))
    tr.insert(1, mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(groove())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "sc88_808_909.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
