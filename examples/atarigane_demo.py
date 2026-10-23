"""GS 113.8 Atarigane in a festival figure: the "chan, chiki" of matsuri
bayashi at C6 (~1 kHz, where a hand gong sounds), each stroke let go after
0.12 s as the holding hand damps it, the accented "chan"s held longer.
Writes OUT/atarigane_pattern.wav (and _room.wav).

    python3 examples/atarigane_demo.py OUT
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
from efx_demo import _sx     # noqa: E402

# (beat, velocity, held beats): a bar of chan . chiki chan . chiki chan chan, twice
BAR = ((0.0, 110, 0.6), (1.0, 80, 0.15), (1.5, 80, 0.15), (2.0, 110, 0.6), (3.0, 80, 0.15),
       (3.5, 80, 0.15))
KEY = 84


def pattern():
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=400000, time=0))
    tr.append(_sx(0x40, 0x00, 0x7F, 0x00))
    tr.append(mido.Message("control_change", channel=0, control=0, value=8))
    tr.append(mido.Message("control_change", channel=0, control=32, value=3))
    tr.append(mido.Message("program_change", channel=0, program=113))
    ev = []
    for bar in range(4):
        for beat, vel, held in BAR:
            t = (bar * 4 + beat) * 480
            ev.append((int(t), 1, vel))
            ev.append((int(t + held * 480), 0, 0))
    ev.sort()
    now = 0
    for t, on, vel in ev:
        tr.append(mido.Message("note_on", channel=0, note=KEY, velocity=vel if on else 0, time=t - now))
        now = t
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(pattern())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "atarigane_pattern.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
