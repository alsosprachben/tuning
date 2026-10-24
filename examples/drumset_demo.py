"""Every key a drum set has of its own, in key order, each struck once -- to
hear a set whole. GS sets are chosen by program on the drum channel (and by
CC32 for a map's own: 282 = the SC-88 map's Dance is CC32 2, program 26).
Writes OUT/drumset_<kit>.wav and prints each key's name as it plays.

    python3 examples/drumset_demo.py OUT KIT [KIT ...]
"""
import os
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B          # noqa: E402
import percussion_map as PM      # noqa: E402

STEP = 0.7


def sweep(kit):
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    tr.append(mido.Message("control_change", channel=9, control=32, value=kit // 128, time=0))
    tr.append(mido.Message("program_change", channel=9, program=kit % 128, time=0))
    keys = sorted(PM.KITS[kit])
    now = 0
    for i, k in enumerate(keys):
        on = int(round((0.25 + i * STEP) * 960))
        tr.append(mido.Message("note_on", channel=9, note=k, velocity=100, time=on - now))
        tr.append(mido.Message("note_off", channel=9, note=k, velocity=0, time=int(0.5 * 960)))
        now = on + int(0.5 * 960)
    tr.append(mido.MetaMessage("end_of_track", time=int(1.5 * 960)))
    return mf, keys


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    for kit in (int(a) for a in argv[2:]):
        mf, keys = sweep(kit)
        print("== %d %s: %d keys" % (kit, PM.DRUM_SETS.get(kit), len(keys)))
        for i, k in enumerate(keys):
            print("   %5.2f s  %3d  %s" % (0.25 + i * STEP, k, PM.KITS[kit][k][0]))
        L, R = B.render(mf)[:2]
        L, R = np.asarray(L, float), np.asarray(R, float)
        g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max(), 1e-9)
        f = os.path.join(out, "drumset_%d.wav" % kit)
        B.write_wav(f, L * g, R * g)
        print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
