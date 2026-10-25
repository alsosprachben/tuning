"""The SC-88 Pro's Cymbal & Claps set (program 54 on the drums): its new
strokes in turn -- the hats closed (40), Half-Open 1 and 2 (49, 50), open
(54); the ride's zones, inner then edge, low, mid, high (81/84, 82/85, 83/86);
Crash 1 (61) and the Brush Crash (64); a crash choked (68, the Mute Crash);
a crash backwards into Crash 1 (70, then 61) -- then a groove on its hats
and ride. In the studio. Writes OUT/cymclaps.wav (and _room.wav).

    TUNING_ROOM=studio python3 examples/cymclaps_demo.py OUT
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import percussion_map as P   # noqa: E402

TEMPO = 100.0


def song():
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / TEMPO), time=0))
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    tr.append(mido.Message("program_change", channel=9, program=53, time=0))
    ev = []

    def hit(beat, note, vel=100, dur=0.25):
        ev.append((beat, note, vel))
        ev.append((beat + dur, note, 0))
    b = 0.0
    for n in (40, 49, 50, 54):                       # the hats, closed to open
        hit(b, n)
        b += 2
    b += 1
    for inner, edge in ((81, 84), (82, 85), (83, 86)):
        hit(b, inner)
        hit(b + 2, edge)
        b += 4
    hit(b, 61)
    hit(b + 4, 64)
    b += 8
    hit(b, 68)                                       # choked
    b += 2
    swell = P.KIT_GATE[53][70] * TEMPO / 60.0        # backwards into a crash
    hit(b + 4 - swell, 70, dur=swell)
    hit(b + 4, 61)
    b += 10
    for bar in range(4):                             # the hats and the ride, swung
        for k in range(4):
            hit(b + k, 85 if bar % 2 else 82, 96)
            hit(b + k + 0.66, 82 if bar % 2 else 81, 70)
        hit(b + 1, 47 if bar % 2 else 46, 90)
        hit(b + 3, 47, 90)
        hit(b + 3.5, 49, 84)
        b += 4
    hit(b, 61)
    ev.sort(key=lambda e: (e[0], e[2] > 0))
    now = 0
    for beat, note, vel in ev:
        t = int(round(beat * 480))
        tr.append(mido.Message("note_on", channel=9, note=note, velocity=vel, time=t - now))
        now = t
    tr.append(mido.MetaMessage("end_of_track", time=480 * 8))
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(song())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "cymclaps.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
