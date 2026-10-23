"""The TR-909 set (drum program 30) in a house groove: the kick on every
beat, the open hat on the off-beats, snare 1 on two and four, a snare 2
roll and the six toms falling into the crash, two bars of ride after.
Writes OUT/tr909_groove.wav (and _room.wav), and each of the set's own
voices alone as OUT/tr909_voices.wav.

    python3 examples/tr909_demo.py OUT
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402

TEMPO = 125.0
VOICES = (36, 35, 37, 38, 40, 41, 43, 45, 47, 48, 50, 46, 49, 51)


def _mid(events, beats):
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / TEMPO), time=0))
    tr.append(mido.Message("program_change", channel=9, program=30, time=0))
    ev = []
    for beat, note, vel in events:
        t = int(round(beat * 480))
        ev.append((t, 1, note, vel))
        ev.append((t + 120, 0, note, 0))
    ev.sort()
    now = 0
    for t, on, note, vel in ev:
        tr.append(mido.Message("note_on", channel=9, note=note, velocity=vel, time=t - now))
        now = t
    tr.append(mido.MetaMessage("end_of_track", time=int(beats * 480) - now))
    return mf


def groove():
    ev = []
    for bar in range(8):
        b0 = bar * 4
        for k in range(4):
            ev.append((b0 + k, 36, 112))
            ev.append((b0 + k + 0.5, 46, 84 if k % 2 else 76))
        if bar in (5, 6, 7):
            for k in range(4):
                ev.append((b0 + k + 0.25, 51, 60))
                ev.append((b0 + k + 0.75, 51, 56))
        if bar == 3:
            for i, n in enumerate((50, 48, 47, 45, 43, 41)):
                ev.append((b0 + 2 + i / 3.0, n, 100 - 3 * i))
            ev.append((b0 + 1, 38, 104))
            ev.append((b0 + 1.5, 40, 70))
            ev.append((b0 + 1.75, 40, 80))
        else:
            ev.append((b0 + 1, 38, 104))
            ev.append((b0 + 3, 38, 108))
            if bar % 2:
                ev.append((b0 + 3.75, 37, 80))
        if bar in (0, 4):
            ev.append((b0, 49, 110))
    return _mid(ev, 33)


def voices():
    return _mid([(1.5 * i, n, 100) for i, n in enumerate(VOICES)], 1.5 * len(VOICES) + 2)


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    for name, mf in (("tr909_groove", groove()), ("tr909_voices", voices())):
        L, R = B.render(mf)[:2]
        L, R = np.asarray(L, float), np.asarray(R, float)
        g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
        f = os.path.join(out, name + ".wav")
        B.write_wav(f, L * g, R * g)
        if name == "tr909_groove":
            subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                            os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
        print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
