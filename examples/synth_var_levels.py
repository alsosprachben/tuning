#!/usr/bin/env python3
"""Level a synth variation against a reference program: the trim that puts it
where the reference sits (patch_map.VARIATION_TRIM_DB).

    python3 examples/synth_var_levels.py PROG:BANK:REF [...]

Each variation and its reference program -- a Moog program of its kind,
already trimmed to GeneralUser GS (PROGRAM_TRIM_DB) -- play the same phrase,
an arpeggiated triad held and a line, C3 to C5, on the SC-88 Pro map (GS).
The loud frames (the 90th percentile of 50 ms levels) are compared, and the
trim printed is the reference's own plus the difference, with the trim the
variation has now beside it.
"""
import os
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import patch_map as P        # noqa: E402

PHRASE = [((48, 52, 55), 2.0), ((60,), 0.5), ((64,), 0.5), ((67,), 0.5), ((72,), 0.5), ((65, 69, 72), 2.0)]


def song(prog, bank):
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    tr.append(mido.Message("control_change", control=0, value=bank, time=0))
    tr.append(mido.Message("control_change", control=32, value=3, time=0))
    tr.append(mido.Message("program_change", program=prog, time=0))
    gap = 240
    for notes, beats in PHRASE:
        for i, n in enumerate(notes):
            tr.append(mido.Message("note_on", note=n, velocity=100, time=gap if i == 0 else 0))
        for i, n in enumerate(notes):
            tr.append(mido.Message("note_off", note=n, time=int(beats * 480 * 0.9) if i == 0 else 0))
        gap = int(beats * 480 * 0.1)
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return mf


def loud(prog, bank):
    L, R = B.render(song(prog, bank))[:2]
    x = (np.asarray(L, float) + np.asarray(R, float)) / 2.0
    h = int(0.05 * B.SR)
    e = [20 * np.log10(np.sqrt(np.mean(x[i:i + h] ** 2)) + 1e-12) for i in range(0, len(x) - h, h)]
    return float(np.percentile(e, 90))


def main(argv):
    for a in argv[1:]:
        p, b, ref = (int(v) for v in a.split(":"))
        lv, lr = loud(p, b), loud(ref, 0)
        now = P.VARIATION_TRIM_DB.get((p, b), P.PROGRAM_TRIM_DB.get(p, 0.0))
        want = now + (lr - lv)
        print("%d.%d (%s): %.1f dB against program %d's %.1f; trim now %+.1f, wanted %+.1f"
              % (p, b, P.VARIATION_NAMES.get((p, b), "?"), lv, ref, lr, now, want))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
