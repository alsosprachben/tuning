"""The kit's hats in a groove, for an A/B of the hats' refit (crash_fit.py
--hats: DRSKit's kit hats, the pedal's stand thump cut, set by their sizzle):
eight bars on Standard -- closed hats in eighths, the open hat on the "and" of
four, the kick and snare; then the pedal hat on two and four under the ride;
the crash to close. Renders with the tree it is run from, or TUNING_ROOT's
(the old tree, for the A). Writes OUT/NAME.wav (and _room.wav).

    python3 examples/hats_ab_demo.py OUT [NAME]
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.environ.get("TUNING_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402


def song():
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / 108.0), time=0))
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    ev = []

    def hit(b, n, v):
        ev.append((b, n, v))
    for bar in range(8):
        b0 = bar * 4
        ride = bar >= 4
        for e in range(8):
            if ride:
                hit(b0 + e * 0.5, 51, 96 if e % 2 == 0 else 76)
            elif e == 7:
                hit(b0 + e * 0.5, 46, 92)
            else:
                hit(b0 + e * 0.5, 42, 96 if e % 2 == 0 else 72)
        if ride:
            hit(b0 + 1, 44, 90)
            hit(b0 + 3, 44, 90)
        hit(b0, 36, 108)
        hit(b0 + 2.5, 36, 92)
        hit(b0 + 1, 38, 104)
        hit(b0 + 3, 38, 108)
    hit(32, 49, 110)
    hit(32, 36, 110)
    msgs = []
    for b, n, v in ev:
        tk = int(round((b + 0.5) * 480))
        msgs.append((tk, 1, mido.Message("note_on", channel=9, note=n, velocity=v)))
        msgs.append((tk + 60, 0, mido.Message("note_off", channel=9, note=n, velocity=0)))
    msgs.sort(key=lambda m: (m[0], m[1]))
    now = 0
    for tk, _o, m in msgs:
        tr.append(m.copy(time=tk - now))
        now = tk
    tr.append(mido.MetaMessage("end_of_track", time=4 * 480))
    return mf


def main(argv):
    out = argv[1]
    name = argv[2] if len(argv) > 2 else "hats"
    os.makedirs(out, exist_ok=True)
    L, R = B.render(song())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, name + ".wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
