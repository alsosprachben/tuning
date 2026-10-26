"""The Rhythm FX sets' voices and effects, a group at a time, each sound
twice on its key (program 58 Rhythm FX, 59 Rhythm FX 2; tonelib.Rfx*), in
the studio. Writes OUT/rfx_GROUP.wav (and _room.wav).

    TUNING_ROOM=studio python3 examples/rfx_demo.py OUT GROUP

GROUP a: the synth hits -- Techno Thip, Pop Drop, Distortion Kick, Syn.
Drops, Pipe (Rhythm FX 64, 65, 67, 68, 70); Bounce, Reverse Bounce,
Distortion Knock, Sub Marine, Noise Attack (Rhythm FX 2 82-84, 86, 87).
GROUP b: the swept and moving -- Swish, Velocity Noise FX, Spark, Missile,
Space Birds, Flying Monster, Tape Stop 1 and 2 (Rhythm FX 79, 77, 75, 86-88,
84, 85); Guitar Slide, Space Worms, Emergency !, Calculating..., Saw LFO Saw
(Rhythm FX 2 85, 88-91).
GROUP c: the struck and processed -- Woody Slap, Ice Block, Metallic
Percussion, Modulated Bell, Digital Tambourine, Alias, Stereo Noise Clap,
Slappy (Rhythm FX 66, 71, 76, 74, 72, 73, 78, 80).
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402

# group: ((program, note, seconds to the next), ...)
GROUPS = {
    "sonar": ((58, 86, 3.5), (58, 86, 3.5)),
    "missile": ((57, 86, 3.0), (57, 86, 3.0)),
    "alias": ((57, 73, 1.5), (57, 73, 1.5), (57, 73, 1.5)),
    "c": ((57, 66, 0.6), (57, 66, 1.0), (57, 71, 0.6), (57, 71, 1.0), (57, 76, 0.8), (57, 76, 1.2),
          (57, 74, 2.2), (57, 72, 0.6), (57, 72, 1.0), (57, 73, 0.7), (57, 73, 1.1), (57, 78, 0.7),
          (57, 78, 1.1), (57, 80, 0.8), (57, 80, 1.2)),
    "b": ((57, 79, 0.8), (57, 79, 1.2), (57, 77, 0.8), (57, 77, 1.2), (57, 75, 0.8), (57, 75, 1.2),
          (57, 86, 3.0), (57, 87, 1.4), (57, 87, 1.6), (57, 88, 3.0), (57, 84, 1.6), (57, 85, 1.4),
          (58, 85, 0.8), (58, 85, 1.2), (58, 88, 1.2), (58, 88, 1.4), (58, 89, 2.6), (58, 90, 1.4),
          (58, 90, 1.6), (58, 91, 1.5), (58, 91, 1.5)),
    "a": ((57, 64, 0.7), (57, 64, 1.2), (57, 65, 0.7), (57, 65, 1.2), (57, 67, 0.8), (57, 67, 1.4),
          (57, 68, 0.6), (57, 68, 1.2), (57, 70, 0.8), (57, 70, 1.4),
          (58, 82, 2.0), (58, 83, 2.0), (58, 84, 0.7), (58, 84, 1.4), (58, 86, 3.0),
          (58, 87, 0.8), (58, 87, 1.4)),
}


def song(group):
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    prog, gap = None, 240
    for p, n, nxt in GROUPS[group]:
        if p != prog:
            tr.append(mido.Message("program_change", channel=9, program=p, time=gap))
            prog, gap = p, 0
        tr.append(mido.Message("note_on", channel=9, note=n, velocity=100, time=gap))
        tr.append(mido.Message("note_off", channel=9, note=n, velocity=0, time=120))
        gap = int(nxt * 960) - 120
    tr.append(mido.MetaMessage("end_of_track", time=1920))
    return mf


def main(argv):
    out, group = argv[1], argv[2]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(song(group))[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "rfx_%s.wav" % group)
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
