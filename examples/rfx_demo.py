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
GROUP gong: the Asia set's opera gongs -- Bend Gong (the daluo), Hu Yin Luo
Low, Mid, Mid 2, High, High 2, Shou Luo (the xiaoluo); Rhythm FX 2's Reverse
Hu Yin Luo; then the great gong and the small answering.
GROUP d: the voices -- One, Two, Three, then each reversed; Tah and reversed;
Ou, Au, Whey, Frog Voice, Reverse Yyoo Dude, Douby and reversed, Baert High
and Low (Rhythm FX 2 65-81).
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
    "gong": ((52, 81, 3.0), (52, 82, 2.2), (52, 83, 2.0), (52, 84, 2.0), (52, 85, 1.8), (52, 86, 1.8),
             (52, 80, 1.5), (52, 80, 1.5), (58, 63, 2.5),
             # an opera exchange: the great gong on the strong beats, the small
             # gong answering
             (52, 81, 0.6), (52, 80, 0.3), (52, 80, 0.3), (52, 81, 0.6), (52, 80, 0.6), (52, 81, 0.3),
             (52, 80, 0.3), (52, 80, 0.3), (52, 81, 3.0)),
    "asia1": ((52, 87, 2.8), (52, 88, 2.0), (52, 77, 0.4), (52, 77, 0.4), (52, 77, 0.8), (52, 76, 0.6),
              (52, 76, 1.0), (52, 78, 1.0), (52, 79, 1.0),
              (52, 50, 1.2), (52, 51, 0.6), (52, 52, 1.0), (52, 53, 0.8), (52, 54, 0.8), (52, 55, 0.8),
              (52, 56, 0.8), (52, 57, 0.8), (52, 58, 1.2),
              # a noh phrase: the call, the small drum's pon and ta, the large's kan
              (52, 59, 1.15), (52, 58, 0.7), (52, 56, 0.9), (52, 57, 0.5), (52, 58, 1.0), (52, 56, 2.0)),
    "asia2": ((52, 60, 0.8), (52, 61, 0.6), (52, 64, 1.2), (52, 62, 1.0), (52, 63, 0.4), (52, 65, 0.4),
              (52, 66, 1.0), (52, 68, 0.8), (52, 67, 0.5), (52, 69, 0.8), (52, 71, 3.0), (52, 70, 2.5),
              (52, 72, 1.0),
              # a samul nori figure: gengari leading, jang-gu, buk, the jing on the cycle
              (52, 71, 0.3), (52, 64, 0.3), (52, 68, 0.3), (52, 63, 0.15), (52, 67, 0.15), (52, 64, 0.3),
              (52, 60, 0.3), (52, 67, 0.3), (52, 63, 0.3), (52, 71, 2.0),
              # the gongs up slendro, the gender, the bonang, the ceng-ceng, the sagat
              (52, 25, 1.0), (52, 27, 0.8), (52, 29, 0.8), (52, 31, 0.8), (52, 34, 1.5),
              (52, 35, 0.4), (52, 36, 0.4), (52, 37, 0.4), (52, 38, 0.4), (52, 39, 1.2),
              (52, 40, 0.3), (52, 41, 0.3), (52, 42, 0.3), (52, 43, 0.3), (52, 44, 1.0),
              (52, 45, 1.2), (52, 46, 1.2), (52, 47, 1.5), (52, 48, 0.6),
              # a gamelan figure: gender and bonang interlocking, the gong closing it
              (52, 37, 0.25), (52, 42, 0.25), (52, 38, 0.25), (52, 41, 0.25), (52, 36, 0.25), (52, 43, 0.25),
              (52, 35, 0.25), (52, 40, 0.25), (52, 25, 4.0)),
    "ethnic": ((49, 33, 1.0), (49, 51, 0.6), (49, 52, 1.2), (49, 53, 0.6), (49, 54, 1.4), (49, 55, 0.9),
               (49, 56, 0.6), (49, 57, 0.5), (49, 58, 0.6), (49, 59, 1.6), (49, 60, 2.0), (49, 61, 1.0),
               (49, 62, 0.8), (49, 63, 1.0), (49, 65, 0.6), (49, 66, 0.6), (49, 78, 0.9), (49, 79, 0.5),
               (49, 80, 0.8), (49, 83, 0.6), (49, 83, 0.8),
               # a tabla phrase: dha (ge with na), tin, na, te, ge rising
               (49, 60, 0.0), (49, 58, 0.25), (49, 59, 0.25), (49, 58, 0.25), (49, 57, 0.125), (49, 57, 0.125),
               (49, 60, 0.0), (49, 58, 0.25), (49, 61, 0.25), (49, 59, 0.25), (49, 57, 0.25), (49, 60, 2.0)),
    "yo": ((52, 59, 1.8), (52, 59, 1.8), (58, 77, 1.8), (58, 77, 1.8)),
    "d": ((58, 65, 0.7), (58, 67, 0.7), (58, 69, 1.4), (58, 66, 0.7), (58, 68, 0.7), (58, 70, 1.4),
          (58, 71, 0.6), (58, 72, 1.2), (58, 73, 0.9), (58, 74, 0.9), (58, 75, 1.2), (58, 76, 1.0),
          (58, 77, 1.2), (58, 78, 0.8), (58, 79, 1.2), (58, 80, 0.8), (58, 81, 1.2)),
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
        if nxt <= 0.0:                 # struck with the next (a tabla's dha)
            tr.append(mido.Message("note_off", channel=9, note=n, velocity=0, time=0))
            gap = 0
            continue
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
