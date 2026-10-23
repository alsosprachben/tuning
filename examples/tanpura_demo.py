"""GS 104.16 Tamboura as a tanpura is played: the four strings in turn, Pa,
Sa, Sa, low Sa (G#3 C#4 C#4 C#3, sankalp's take 2 tuning), a pluck every
0.875 s, each string ringing until its next pluck 3.5 s later -- the take's
own cycle. Writes OUT_DIR/tamboura_drone.wav (and _room.wav, the room's tail).

    python3 examples/tanpura_demo.py OUT_DIR [CYCLES]
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

CYCLE = (56, 61, 61, 49)     # Pa, Sa, Sa, low Sa
STEP = 0.875


def drone_file(cycles):
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(_sx(0x40, 0x00, 0x7F, 0x00))                      # GS reset
    tr.append(mido.Message("control_change", channel=0, control=0, value=16))
    tr.append(mido.Message("control_change", channel=0, control=32, value=3))
    tr.append(mido.Message("program_change", channel=0, program=104))
    # the two Sa strings are two strings: each its own channel, so the
    # second's pluck does not cut the first's ring
    tr.append(mido.Message("control_change", channel=1, control=0, value=16))
    tr.append(mido.Message("control_change", channel=1, control=32, value=3))
    tr.append(mido.Message("program_change", channel=1, program=104))
    ev = []
    for c in range(cycles):
        for i, n in enumerate(CYCLE):
            t = (c * len(CYCLE) + i) * STEP
            ch = 1 if i == 2 else 0
            ev.append((t, "note_on", ch, n))
            ev.append((t + len(CYCLE) * STEP - 0.01, "note_off", ch, n))
    ev.sort(key=lambda e: (e[0], e[1] == "note_on"))
    now = 0.0
    for t, kind, ch, n in ev:
        dt = int(round((t - now) * 960))
        tr.append(mido.Message(kind, channel=ch, note=n, velocity=90 if kind == "note_on" else 0, time=dt))
        now += dt / 960.0
    return mf


def main(argv):
    out = argv[1]
    cycles = int(argv[2]) if len(argv) > 2 else 6
    os.makedirs(out, exist_ok=True)
    L, R = B.render(drone_file(cycles))[:2]
    pk = max(np.abs(np.asarray(L)).max(), np.abs(np.asarray(R)).max())
    g = 10 ** (-1 / 20.0) / pk
    f = os.path.join(out, "tamboura_drone.wav")
    B.write_wav(f, np.asarray(L, float) * g, np.asarray(R, float) * g)
    fr = os.path.splitext(f)[0] + "_room.wav"
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f, fr], check=True,
                   stdout=subprocess.DEVNULL)
    print("  " + fr)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
