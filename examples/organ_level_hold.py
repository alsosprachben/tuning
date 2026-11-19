#!/usr/bin/env python3
"""A tonewheel voice's level held across a change of its cabinet or valve.

    python3 examples/organ_level_hold.py PROGRAM [ATTR=VALUE ...]

The level the organs were HELD at (tonelib: "the mean of C4-G5's first second
at velocity 100"), read twice in one process -- the class as it stands, then
with ATTR=VALUE set on it (leslie=False cabinet=hammond amp_drive=0.5) --
and the initial_gain factor (dB) that puts the second back on the first.
Each note rendered alone (blockrender, the hall), its first second's RMS
over both channels; the mean of the twenty in dB.
"""
import ast
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import blockrender as B  # noqa: E402
import mido  # noqa: E402
import patch_map as PM  # noqa: E402

NOTES = range(60, 80)          # C4-G5


def level(program):
    out = []
    for n in NOTES:
        m = mido.MidiFile(type=1, ticks_per_beat=480)
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.Message("program_change", channel=0, program=program, time=0))
        t.append(mido.Message("note_on", channel=0, note=n, velocity=100, time=0))
        t.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=960 * 2))
        L, R = B.render(m)[:2]
        x = np.stack([np.asarray(L, float), np.asarray(R, float)])
        on = np.flatnonzero(np.abs(x).max(0) > 1e-4)
        s = x[:, on[0]:on[0] + B.SR] if len(on) else x[:, :B.SR]
        out.append(10 * np.log10(np.mean(s ** 2) + 1e-30))
    return float(np.mean(out))


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    prog = int(argv[1])
    cls = PM.property_class_for_program(prog)
    before = level(prog)
    for kv in argv[2:]:
        k, v = kv.split("=", 1)
        try:
            v = ast.literal_eval(v)
        except (ValueError, SyntaxError):
            pass
        setattr(cls, k, v)
    after = level(prog)
    print("program %d (%s): %.2f dB as it stands, %.2f dB with %s: initial_gain %+.3f dB to hold it"
          % (prog, cls.__name__, before, after, " ".join(argv[2:]), before - after))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
