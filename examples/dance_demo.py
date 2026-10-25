"""The SC-88 Pro's native Dance set (program 27 on the drums) in a house
groove -- the 909 Comp Kick on every beat, House Snare and the snap on two
and four, CR-78 hats, the 808's crash, the Hoos answering -- and Rhythm FX 2
(program 60) on a second drum part (GS USE FOR RHYTHM PART, part 11), its
backwards drums swelling into the bars. The crowd (Small Club 1) at the end.
Writes OUT/dance.wav (and _room.wav).

    python3 examples/dance_demo.py OUT
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

TEMPO = 122.0
BARS = 8


def gs(addr, data):
    body = list(addr) + list(data)
    return [0x41, 0x10, 0x42, 0x12] + body + [(128 - sum(body) % 128) % 128]


def song():
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / TEMPO), time=0))
    tr.append(mido.Message("sysex", data=gs((0x40, 0x00, 0x7F), (0x00,)), time=0))
    # part 11 (channel 11) a second drum part
    tr.append(mido.Message("sysex", data=gs((0x40, 0x1A, 0x15), (0x02,)), time=0))
    tr.append(mido.Message("program_change", channel=9, program=26, time=0))
    tr.append(mido.Message("program_change", channel=10, program=59, time=0))
    ev = []

    def hit(beat, ch, note, vel, dur=0.25):
        ev.append((beat, ch, note, vel))
        ev.append((beat + dur, ch, note, 0))
    for bar in range(BARS):
        b0 = bar * 4
        for k in range(4):
            hit(b0 + k, 9, 35, 112)
            hit(b0 + k + 0.5, 9, 46 if k % 2 else 42, 84)
            hit(b0 + k + 0.25, 9, 42, 52)
            hit(b0 + k + 0.75, 9, 42, 60)
        hit(b0 + 1, 9, 38, 100)
        hit(b0 + 3, 9, 38, 104)
        hit(b0 + 1, 9, 26, 90)
        hit(b0 + 3, 9, 26, 94)
        if bar % 2 == 1:
            hit(b0 + 2.5, 9, 78, 100)
            hit(b0 + 3.5, 9, 79, 100)
        if bar % 4 == 0:
            hit(b0, 9, 49, 104)
        # a backwards drum swelling into the next bar: it swells over its
        # voice's ring (percussion_map.KIT_GATE), so it starts that long
        # before the downbeat, where its hit lands
        if bar < BARS - 1:
            rev = (37, 48, 59, 40, 64, 39, 55)[bar]
            swell = P.KIT_GATE[58][rev] * TEMPO / 60.0
            hit(b0 + 4 - swell, 10, rev, 100, dur=swell)
    hit(BARS * 4, 9, 35, 112)
    hit(BARS * 4, 9, 49, 110)
    hit(BARS * 4 + 0.5, 9, 88, 100)
    ev.sort(key=lambda e: (e[0], e[3] > 0))
    now = 0
    for beat, ch, note, vel in ev:
        t = int(round(beat * 480))
        tr.append(mido.Message("note_on", channel=ch, note=note, velocity=vel, time=t - now))
        now = t
    tr.append(mido.MetaMessage("end_of_track", time=480 * 8))
    return mf


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(song())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "dance.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
