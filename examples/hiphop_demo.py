"""The Hip-Hop set (program 9 on the drums; percussion_gs) in a boom-bap
groove at 90 BPM, sixteenths swung 58% as an MPC swings them: Hip-Hop Kick 1
(36) and 2 (35), the Rap Snare (38) on two and four, Hip-Hop Snare 2 (40) in
the second half, the hats (42/46), a crash to close. Then each of 35, 36, 38
and 40 alone. Writes OUT/hiphop.wav (and _room.wav).

    python3 examples/hiphop_demo.py OUT
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402

BPM = 90.0
SWING = 0.58


def _t(beat16):
    """Sixteenth index -> beats, the off sixteenths late."""
    pair, odd = divmod(beat16, 2)
    return pair * 0.5 + (SWING * 0.5 if odd else 0.0)


def groove():
    ev = []
    for bar in range(8):
        b0 = bar * 16
        snare = 38 if bar < 4 else 40
        kick = (0, 3, 7, 10) if bar % 2 == 0 else (0, 6, 10, 11)
        for s in kick:
            ev.append((_t(b0 + s), 36 if s == 0 or bar % 2 == 0 else 35, 112 if s == 0 else 100))
        ev += [(_t(b0 + 4), snare, 112), (_t(b0 + 12), snare, 112)]
        for s in range(0, 16, 2):
            ev.append((_t(b0 + s), 46 if s == 14 and bar % 4 == 3 else 42, 84 if s % 4 == 0 else 64))
    ev += [(_t(128), 36, 112), (_t(128), 49, 100)]
    for i, k in enumerate((36, 35, 38, 40)):
        ev.append((_t(128) + 4 + 2 * i, k, 110))
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / BPM), time=0))
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    tr.append(mido.Message("program_change", channel=9, program=9, time=0))
    msgs = []
    for b, n, v in ev:
        t = int(round((b + 0.5) * 480))
        msgs += [(t, mido.Message("note_on", channel=9, note=n, velocity=v)),
                 (t + 120, mido.Message("note_off", channel=9, note=n, velocity=0))]
    msgs.sort(key=lambda m: (m[0], m[1].type == "note_on"))
    now = 0
    for t, m in msgs:
        tr.append(m.copy(time=t - now))
        now = t
    tr.append(mido.MetaMessage("end_of_track", time=4 * 480))
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(groove())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "hiphop.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
