"""The SC-8850's Room and Jazz sets' own, and the L/R sets' left foot:
  1. JAZZ (program 33): a swung ride (Jazz Ride Cymbal), the bell on the
     off-beats of the last bars, the hat's foot on two and four, the
     kick feathered, a fill round both toms (Jazz Low and Mid/High Toms), the
     Jazz Crash to close -- soneproject's jazz-bar kit, fitted
  2. ROOM (program 9): a rock groove on its kick, snare, hats, ride, bell and
     crash -- Standard's in the live room
  3. STANDARD L/R (program 3): sixteenth double kicks, the right foot (36) and
     the left ([L] Standard Kick 1, 96) alternating under a backbeat
Writes OUT/roomjazz.wav (and _room.wav).

    python3 examples/roomjazz_demo.py OUT
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402


def song():
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / 140.0), time=0))
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    ev = []                       # (beat, kind, value, velocity): kind 'p' a program, 'n' a note

    def hit(b, n, v):
        ev.append((b, "n", n, v))

    # 1. JAZZ, swung (the off-beat at 2/3 of the beat), 8 bars
    ev.append((-0.5, "p", 32, 0))
    for bar in range(8):
        b0 = bar * 4
        for k in range(4):
            ride = 53 if (bar >= 6 and k % 2) else 51
            hit(b0 + k, ride, 96 if k % 2 else 84)
            if k % 2:
                hit(b0 + k + 2.0 / 3.0, ride, 70)
                hit(b0 + k, 44, 70)
            hit(b0 + k, 36, 38)
        if bar == 3:
            hit(b0 + 3 + 2.0 / 3.0, 38, 60)
    for i, n in enumerate((50, 50, 48, 47, 45, 43, 43, 41)):
        hit(28 + 2 + i * 0.25, n, 92 if i % 2 == 0 else 80)
    hit(32, 49, 108)
    hit(32, 36, 100)
    # 2. ROOM, 8 bars at the same tempo
    s0 = 38
    ev.append((s0 - 0.5, "p", 8, 0))
    for bar in range(8):
        b0 = s0 + bar * 4
        top = 51 if bar >= 4 else 42
        for e in range(8):
            v = 92 if e % 2 == 0 else 70
            hit(b0 + e * 0.5, 53 if (top == 51 and e % 4 == 2) else top, v)
        hit(b0, 36, 110)
        hit(b0 + 2.5, 36, 96)
        hit(b0 + 1, 38, 108)
        hit(b0 + 3, 38, 112)
        if bar in (3, 7):
            hit(b0 + 3.5, 46, 96)
    hit(s0, 49, 110)
    hit(s0 + 16, 49, 104)
    for i, n in enumerate((50, 48, 47, 45, 43, 41)):
        hit(s0 + 30 + i * 0.33, n, 104)
    hit(s0 + 32, 49, 112)
    hit(s0 + 32, 36, 112)
    # 3. STANDARD L/R: double kicks, 4 bars
    s1 = s0 + 38
    ev.append((s1 - 0.5, "p", 2, 0))
    for bar in range(4):
        b0 = s1 + bar * 4
        for x in range(16):
            hit(b0 + x * 0.25, 36 if x % 2 == 0 else 96, 100)
        hit(b0 + 1, 38, 110)
        hit(b0 + 3, 38, 112)
        for e in range(4):
            hit(b0 + e, 42, 80)
    hit(s1 + 16, 49, 110)
    hit(s1 + 16, 36, 110)
    ev.sort(key=lambda e: (e[0], e[1] == "n"))
    msgs = []
    for b, kind, val, vel in ev:
        tk = int(round((b + 0.5) * 480))
        if kind == "p":
            msgs.append((tk, 1, mido.Message("program_change", channel=9, program=val)))
        else:
            msgs.append((tk, 2, mido.Message("note_on", channel=9, note=val, velocity=vel)))
            msgs.append((tk + 60, 0, mido.Message("note_off", channel=9, note=val, velocity=0)))
    msgs.sort(key=lambda m: (m[0], m[1]))
    now = 0
    for tk, _o, m in msgs:
        tr.append(m.copy(time=tk - now))
        now = tk
    tr.append(mido.MetaMessage("end_of_track", time=4 * 480))
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(song())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "roomjazz.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
