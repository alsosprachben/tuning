"""The Techno set's kick and snare, A/B: four bars of a techno groove each on
  1. the SC-8850's sources through our valve -- its TR-808 Kick (35) and TR-606
     Snare 2 (38), driven: the Techno set's own now (Ben)
  2. the SC-88 Pro's Techno Kick 2 and Techno Snare 1 (driven 909s), which
     they replace (from Kick & Snare 2: 36, 79)
  3. the same machines clean (the TR-808 set's kick, the TR-606's Snare 2)
The hats, clap and crash on a second drum part (part 11), the Techno set, so
only the kick and snare change. Writes OUT/techno_ab.wav (and _room.wav).

    python3 examples/techno_ab_demo.py OUT
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402

TEMPO = 130.0
BARS = 4
# (program, kick key, snare key); the clean pair from two sets
PAIRS = ((11, 35, 38), (51, 36, 79), ((25, 36), (28, 40)))


def gs(addr, data):
    body = list(addr) + list(data)
    return [0x41, 0x10, 0x42, 0x12] + body + [(128 - sum(body) % 128) % 128]


def song():
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / TEMPO), time=0))
    tr.append(mido.Message("sysex", data=gs((0x40, 0x00, 0x7F), (0x00,)), time=0))
    # parts 11 and 12 (channels 11, 12) drum parts too: the hats; the clean snare
    tr.append(mido.Message("sysex", data=gs((0x40, 0x1A, 0x15), (0x02,)), time=0))
    tr.append(mido.Message("sysex", data=gs((0x40, 0x1B, 0x15), (0x02,)), time=0))
    tr.append(mido.Message("program_change", channel=10, program=11, time=0))
    ev = []

    def hit(beat, ch, note, vel, dur=0.25):
        ev.append((beat, 0, ch, note, vel))
        ev.append((beat + dur, 0, ch, note, 0))
    sec = BARS * 4 + 2
    for i, pair in enumerate(PAIRS):
        s0 = i * sec
        if isinstance(pair[0], tuple):
            (kp, kk), (sp, sk) = pair
            ev.append((s0 - 0.5, 1, 9, kp, None))
            ev.append((s0 - 0.5, 1, 11, sp, None))
            # ...10 dB down (CC7 100 -> 56): the machines' own sets sit hotter
            # than the Techno set's -32 dB, and louder would win the A/B
            ev.append((s0 - 0.5, 2, 9, 7, 56))
            ev.append((s0 - 0.5, 2, 11, 7, 56))
            kch, sch = 9, 11
        else:
            kp, kk, sk = pair
            ev.append((s0 - 0.5, 1, 9, kp, None))
            kch = sch = 9
        for bar in range(BARS):
            b0 = s0 + bar * 4
            for k in range(4):
                hit(b0 + k, kch, kk, 116)
                hit(b0 + k + 0.5, 10, 46 if k % 2 else 42, 80)
                hit(b0 + k + 0.25, 10, 42, 50)
                hit(b0 + k + 0.75, 10, 42, 58)
            hit(b0 + 1, sch, sk, 104)
            hit(b0 + 3, sch, sk, 108)
            hit(b0 + 3, 10, 39, 80)
            if bar == BARS - 1:
                hit(b0 + 3.5, sch, sk, 84)
                hit(b0 + 3.75, sch, sk, 96)
        hit(s0 + BARS * 4, kch, kk, 116)
        hit(s0 + BARS * 4, 10, 49, 100)
    ev.sort(key=lambda e: (e[0], e[1] == 0, e[1] == 0 and e[4] > 0))
    now = 0
    for beat, kind, ch, note, vel in ev:
        t = max(0, int(round(beat * 480)))
        if kind == 1:
            tr.append(mido.Message("program_change", channel=ch, program=note, time=t - now))
        elif kind == 2:
            tr.append(mido.Message("control_change", channel=ch, control=note, value=vel, time=t - now))
        else:
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
    f = os.path.join(out, "techno_ab.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
