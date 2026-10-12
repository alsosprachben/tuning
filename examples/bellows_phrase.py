#!/usr/bin/env python3
"""A phrase for the bellows' push (tonelib.bellows_push_weight): three detached
notes, each from silence -- each a push -- then a legato run, slurred, which
takes none.

    python3 examples/bellows_phrase.py OUT.wav [PROGRAM]     (21, the accordion)
"""
import os
import subprocess
import sys

import mido
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import blockrender as B  # noqa: E402


def build(prog):
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=600000, time=0))
    t.append(mido.Message("program_change", channel=0, program=prog, time=0))
    now = 0
    ev = []
    for i, n in enumerate((57, 64, 69)):                 # detached, a rest between
        on = i * 960
        ev += [(on, 1, n), (on + 600, 0, n)]
    s = 3 * 960
    run = (69, 71, 72, 74, 76, 74, 72, 71, 69)            # legato: each overlaps the next
    for i, n in enumerate(run):
        on = s + i * 240
        ev += [(on, 1, n), (on + 250 if i < len(run) - 1 else on + 720, 0, n)]
    ev.sort(key=lambda e: (e[0], e[1]))
    for tk, k, n in ev:
        t.append(mido.Message("note_on" if k else "note_off", channel=0, note=n,
                              velocity=96 if k else 0, time=tk - now))
        now = tk
    t.append(mido.MetaMessage("end_of_track", time=960))
    return m


def main(out, prog=21):
    L, R = B.render(build(prog))[:2]
    x = np.stack([np.asarray(L, np.float64), np.asarray(R, np.float64)], 1)
    x *= 0.89 / max(np.abs(x).max(), 1e-9)
    raw = out + ".raw"
    (x * 32767).astype("<i2").tofile(raw)
    subprocess.run(["sox", "-r", str(B.SR), "-e", "signed", "-b", "16", "-c", "2", raw, out], check=True)
    os.remove(raw)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 21)
