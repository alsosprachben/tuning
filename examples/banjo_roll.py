#!/usr/bin/env python3
"""A short open-G banjo roll (GM 105) whose notes END: forward rolls of eighths,
then two bars of staccato pinches with rests between, so the note-off's release
(BanjoProperties.release_valve_time) is heard against the ring.

    python3 examples/banjo_roll.py OUT.wav
"""
import os
import subprocess
import sys

import mido
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import blockrender as B  # noqa: E402

TPB = 480
ROLL = (67, 59, 62, 67, 59, 62, 67, 74)          # g B d g B d g d'
PINCH = ((55, 74), (59, 67), (62, 74), (55, 71))


def build():
    m = mido.MidiFile(type=1, ticks_per_beat=TPB)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=105, time=0))
    ev = []                                       # (tick, kind, note, vel)
    e = TPB // 2
    for b in range(4):                            # four bars of rolls, legato eighths
        for i, n in enumerate(ROLL):
            on = (b * 8 + i) * e
            ev += [(on, 1, n, 96 if i % 3 == 0 else 80), (on + e - 10, 0, n, 0)]
    s = 32 * e
    for j, ch in enumerate(PINCH * 2):            # staccato pinches, a beat apart
        on = s + j * TPB
        for n in ch:
            ev += [(on, 1, n, 100), (on + TPB // 4, 0, n, 0)]
    ev.sort(key=lambda q: (q[0], q[1]))
    now = 0
    for tk, k, n, v in ev:
        t.append(mido.Message("note_on" if k else "note_off", channel=0, note=n,
                              velocity=v, time=tk - now))
        now = tk
    t.append(mido.MetaMessage("end_of_track", time=2 * TPB))
    return m


def main(out):
    L, R = B.render(build())[:2]
    x = np.stack([np.asarray(L, np.float64), np.asarray(R, np.float64)], 1)
    x *= 0.89 / max(np.abs(x).max(), 1e-9)
    raw = out + ".raw"
    (x * 32767).astype("<i2").tofile(raw)
    subprocess.run(["sox", "-r", str(B.SR), "-e", "signed", "-b", "16", "-c", "2", raw, out], check=True)
    os.remove(raw)


if __name__ == "__main__":
    main(sys.argv[1])
