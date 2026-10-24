"""The Techno set (program 11 on the drums; percussion_gs) four on the floor
at 130 BPM: Techno Kick 1 (36) on every beat, Kick 2 (35) in the second
half, the 707's clap and Techno Snare 1 (38) on two and four, Snare 2 (40)
in the second half, the 707's closed hats on the sixteenths and the 909's
open hat off the beat, an 808 tom fill, a crash to close. Then each driven
drum alone beside the 909 drum it is driven from (the TR-909 set's 36, 35,
38, 40). Writes OUT/techno.wav (and _room.wav).

    python3 examples/techno_demo.py OUT
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402

BPM = 130.0


def groove():
    ev = []                       # (beat, program, note, velocity); program None = as set
    for bar in range(8):
        b0 = bar * 4
        kick = 36 if bar < 4 else 35
        snare = 38 if bar < 4 else 40
        for b in range(4):
            ev.append((b0 + b, None, kick, 116))
            ev.append((b0 + b + 0.5, None, 46, 88))
        for s in range(16):
            if s % 4 != 2:
                ev.append((b0 + s / 4.0, None, 42, 70 if s % 2 else 84))
        ev += [(b0 + 1, None, 39, 100), (b0 + 3, None, 39, 100), (b0 + 1, None, snare, 96), (b0 + 3, None, snare, 96)]
        if bar == 7:
            for i, n in enumerate((50, 48, 47, 45, 43, 41)):
                ev.append((b0 + 2.5 + i * 0.25, None, n, 104))
    ev += [(32, None, 36, 116), (32, None, 49, 104)]
    t = 36.0
    for ours, theirs in ((36, 36), (35, 35), (38, 38), (40, 40)):
        ev.append((t, 30, theirs, 112))
        ev.append((t + 1.5, None, ours, 112))
        t += 3.0
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / BPM), time=0))
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    msgs = [(0, mido.Message("program_change", channel=9, program=11))]
    cur = 11
    for b, prog, n, v in sorted(ev, key=lambda e: e[0]):
        tk = int(round((b + 0.5) * 480))
        want = 11 if prog is None else prog
        if want != cur:
            msgs.append((tk, mido.Message("program_change", channel=9, program=want)))
            cur = want
        msgs += [(tk, mido.Message("note_on", channel=9, note=n, velocity=v)),
                 (tk + 100, mido.Message("note_off", channel=9, note=n, velocity=0))]
    msgs.sort(key=lambda m: (m[0], {"note_off": 0, "program_change": 1, "note_on": 2}[m[1].type]))
    now = 0
    for tk, m in msgs:
        tr.append(m.copy(time=tk - now))
        now = tk
    tr.append(mido.MetaMessage("end_of_track", time=4 * 480))
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(groove())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "techno.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
