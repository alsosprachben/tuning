#!/usr/bin/env python3
"""A short passage on GM 15, to hear the string bank build: an original tune
in D in the dulcimer's way -- running eighths in the treble, the bass courses
on the strong beats, a roll and a ringing chord to end.

    python3 examples/dulcimer_piece.py OUT.wav [--dry]

Every pitch is one of the instrument's courses (tonelib.HammeredDulcimer
Properties.course_keys), and each note is let ring 1.5 s -- a dulcimer has
no dampers, so a played note is not stopped by the next. The render goes
through sox's reverb for a small room, 3 dB under the direct sound
(--dry: none).
"""
import os
import random
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from roomtail import write_wav

N = dict(D3=50, E3=52, G3=55, A3=57, B3=59, D4=62, Fs4=66, A4=69, B4=71, Cs5=73, D5=74, E5=76,
         Fs5=78, G5=79, A5=81, B5=83, D6=86)
# (eighths of the treble, the bass on beats 1 and 3)
TUNE = (
    ("A4 D5 Fs5 D5 A4 D5 Fs5 A5", "D3 A3"),
    ("G5 Fs5 E5 D5 E5 Fs5 G5 E5", "G3 D3"),
    ("Fs5 D5 A4 D5 Fs5 A5 D6 A5", "D3 A3"),
    ("B5 A5 G5 Fs5 E5 Cs5 A4 Cs5", "A3 E3"),
    ("D5 Fs5 A5 Fs5 G5 B5 A5 G5", "D3 G3"),
    ("Fs5 E5 D5 Cs5 B4 D5 G5 B4", "B3 G3"),
    ("A4 Cs5 E5 A5 G5 Fs5 E5 Cs5", "A3 A3"),
)
BPM = 112.0
RING = 1.5


def events():
    """[(seconds, key, velocity, length)]: the tune, a little unevenly
    played -- each stroke within a few ms, the downbeats a touch harder."""
    rng = random.Random(15)
    e8 = 30.0 / BPM
    out, t = [], 0.6
    for treble, bass in TUNE:
        for i, nm in enumerate(treble.split()):
            v = 92 if i % 4 == 0 else 80 if i % 2 == 0 else 72
            out.append((t + i * e8 + rng.uniform(-0.006, 0.006), N[nm], v + rng.randint(-4, 4), RING))
        for i, nm in enumerate(bass.split()):
            out.append((t + i * 4 * e8 + rng.uniform(-0.004, 0.004), N[nm], 84, RING))
        t += 8 * e8
    # the close: D5 on the beat, a roll on it (the two hammers in turn,
    # sixteenths), then the chord from the bass up, left to ring
    out.append((t, N["D5"], 90, RING))
    out.append((t, N["D3"], 86, RING))
    r = t + 2 * e8
    for i in range(10):
        out.append((r + i * e8 / 2 + rng.uniform(-0.004, 0.004), N["D5"], 62 + 3 * (i % 2) + 2 * i, 0.3))
    c = r + 5 * e8
    for i, nm in enumerate(("D3", "A3", "D4", "Fs4", "A4", "D5")):
        out.append((c + 0.045 * i, N[nm], 88, 5.0))
    return out, c + 5.5


def render(out_path, dry):
    import mido
    import blockrender as B
    ev, end = events()
    m = mido.MidiFile(type=1, ticks_per_beat=960)
    tr = mido.MidiTrack()
    m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=15, time=0))
    msgs = []
    for t, k, v, ln in ev:
        msgs.append((t, 1, mido.Message("note_on", channel=0, note=k, velocity=v)))
        msgs.append((t + ln, 0, mido.Message("note_off", channel=0, note=k, velocity=0)))
    msgs.sort(key=lambda q: (q[0], q[1]))
    now = 0
    for t, _, msg in msgs:
        tick = int(round(t * 1920))       # 960 ticks a beat at 120 bpm
        tr.append(msg.copy(time=tick - now))
        now = tick
    L, R = B.render(m)[:2]
    x = np.stack([np.asarray(L, np.float64), np.asarray(R, np.float64)], 1)[:int(end * B.SR)]
    x = 0.5 * x / max(np.abs(x).max(), 1e-12)
    if dry:
        write_wav(out_path, x, B.SR)
        return
    tmp = out_path + ".dry.wav"
    write_wav(tmp, x, B.SR)
    # a small room, its tail 3 dB under the direct sound (the chamber the
    # piano gets, a little smaller: sources.md, wetness)
    subprocess.run(["sox", tmp, out_path, "reverb", "45", "50", "55", "100", "8", "-3",
                    "gain", "-n", "-1"], check=True)
    os.remove(tmp)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__.strip())
        sys.exit(2)
    render(args[0], "--dry" in sys.argv)
