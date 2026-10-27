#!/usr/bin/env python3
"""The uilleann chanter's cut, for the ear: a reel phrase in D on GS 109.11
"UillnPipe Or" (the SC-8850 map's), rendered by the tree it is run from.

    python3 examples/cut_ab.py OUT.wav

Run in two trees (an old commit's worktree and the working tree) for an A/B.
Quavers at 100 bpm a quaver 0.3 s -- every note past three cuts' length, so
each is cut (blockrender's cut) -- with a held note to end.
"""
import os
import sys

import mido
import numpy as np

sys.path.insert(0, os.getcwd())            # the tree being heard
import blockrender as B                    # noqa: E402

# D E F# A  B A F# E  D F# A d  B A F# A  D (held): the chanter's bottom octave
TUNE = [62, 64, 66, 69, 71, 69, 66, 64, 62, 66, 69, 74, 71, 69, 66, 69]


def reel():
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=600000, time=0))
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41]))   # GS reset
    tr.append(mido.Message("control_change", channel=0, control=0, value=11))
    tr.append(mido.Message("control_change", channel=0, control=32, value=4))
    tr.append(mido.Message("program_change", channel=0, program=109))
    q = 240                                  # a quaver
    for i, n in enumerate(TUNE + [62]):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=96, time=0))
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0,
                               time=q * 6 if i == len(TUNE) else q))     # the last D held
    tr.append(mido.Message("note_off", channel=0, note=0, velocity=0, time=480 * 2))
    return mf


def main(argv):
    L, R = B.render(reel(), "even")[:2]
    g = 10 ** (-1 / 20) / max(1e-9, float(np.abs(L).max()), float(np.abs(R).max()))
    B.write_wav(argv[1], np.asarray(L) * g, np.asarray(R) * g)
    print("wrote", argv[1])


if __name__ == "__main__":
    main(sys.argv)
