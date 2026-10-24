"""The Jungle set (program 10 on the drums; percussion_gs) in an Amen-style
break at 165 BPM: Jungle Kick 1 (36) and Snare 1 (38) in the break's
pattern, Snare 2 (40) on its ghost notes, the Jungle Hi-Hat (44) on the
eighths, Jungle Kick 2 (35, the sub) on each bar's downbeat; the second
half the snares swapped. Then 36, 35, 38, 40 and 44 alone. Writes
OUT/jungle.wav (and _room.wav).

    python3 examples/jungle_demo.py OUT
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402

BPM = 165.0
KICK = (0, 2, 10, 11)
SNARE = (4, 12)
GHOST = (7, 9, 15)


def groove():
    ev = []
    for bar in range(8):
        b0 = bar * 4
        main, ghost = (38, 40) if bar < 4 else (40, 38)
        ev.append((b0, 35, 112))
        ev += [(b0 + s / 4.0, 36, 108) for s in KICK]
        ev += [(b0 + s / 4.0, main, 112) for s in SNARE]
        ev += [(b0 + s / 4.0, ghost, 72) for s in GHOST]
        ev += [(b0 + s / 2.0, 44, 80 if s % 2 == 0 else 62) for s in range(8)]
    ev += [(32, 35, 112), (32, 49, 100)]
    for i, k in enumerate((36, 35, 38, 40, 44)):
        ev.append((36 + 2 * i, k, 110))
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / BPM), time=0))
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    tr.append(mido.Message("program_change", channel=9, program=10, time=0))
    msgs = []
    for b, n, v in ev:
        t = int(round((b + 0.5) * 480))
        msgs += [(t, mido.Message("note_on", channel=9, note=n, velocity=v)),
                 (t + 100, mido.Message("note_off", channel=9, note=n, velocity=0))]
    msgs.sort(key=lambda m: (m[0], m[1].type == "note_on"))
    now = 0
    for t, m in msgs:
        tr.append(m.copy(time=t - now))
        now = t
    tr.append(mido.MetaMessage("end_of_track", time=6 * 480))
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(groove())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "jungle.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
