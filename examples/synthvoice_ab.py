#!/usr/bin/env python3
"""The three synthesized voices -- GM 54 Synth Voice, 85 Lead 6 (voice), 91
Pad 4 (choir) -- A/B between two trees.

    python3 examples/synthvoice_ab.py OUTDIR TAG=ROOT [TAG=ROOT ...]

One file, three passages: 54 sings a four-chord progression, 85 a melody over
it, 91 the same chords slowly. Each ROOT's blockrender renders it (a copy of
HEAD against the working tree: a class patched in this process would not
reach blockrender's spawned workers), the hall at -3 dB wet, -12 dB master.
"""
import os
import subprocess
import sys

import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHORDS = ((48, 55, 60, 64), (45, 52, 57, 60), (41, 48, 57, 65), (43, 50, 55, 62))   # C Am F G
MELODY = (72, 74, 76, 79, 77, 76, 74, 72, 74, 71, 72)


def build(out):
    m = mido.MidiFile(type=1, ticks_per_beat=960)          # 120 bpm: 1920 ticks/s
    T = 1920

    def track(ch, prog, name, notes):
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.MetaMessage("track_name", name=name, time=0))
        t.append(mido.Message("program_change", channel=ch, program=prog, time=0))
        ev = []
        for on, off, key, vel in notes:
            ev += [(int(on * T), 1, key, vel), (int(off * T), 0, key, 0)]
        now = 0
        for at, kind, key, vel in sorted(ev, key=lambda e: (e[0], e[1])):
            t.append(mido.Message("note_on", channel=ch, note=key, velocity=vel, time=at - now))
            now = at

    # 54: the progression, 2 s a chord, from 0 s
    track(0, 54, "Synth Voice", [(i * 2.0, i * 2.0 + 1.9, k, 80)
                                 for i, c in enumerate(CHORDS) for k in c])
    # 85: a melody over the same progression, from 9 s
    mel, t0 = [], 9.0
    for i, k in enumerate(MELODY):
        d = 0.7 if i < len(MELODY) - 1 else 1.6
        mel.append((t0, t0 + d * 0.95, k, 90))
        t0 += d
    track(1, 85, "Lead 6 (voice)", mel)
    track(2, 54, "Synth Voice under the lead", [(9.0 + i * 2.0, 9.0 + i * 2.0 + 1.9, k, 60)
                                                for i, c in enumerate(CHORDS) for k in c])
    # 91: the chords slowly, 3.5 s each, from 19 s
    track(3, 91, "Pad 4 (choir)", [(19.0 + i * 3.5, 19.0 + i * 3.5 + 3.3, k, 80)
                                   for i, c in enumerate(CHORDS) for k in c])
    m.save(out)


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    mid = os.path.join(out, "synthvoices.mid")
    build(mid)
    env = dict(os.environ, TUNING_ROOM="hall", TUNING_WET="-3", TUNING_MASTER_DB="-12")
    for tag, root in (a.split("=", 1) for a in argv[2:]):
        P = lambda f: os.path.join(out, "synthvoices_%s%s" % (tag, f))   # noqa: E731
        subprocess.check_call([sys.executable, os.path.join(root, "blockrender.py"), mid,
                               P(".dry.wav"), "hybrid440"], env=env, cwd=root)
        subprocess.check_call([sys.executable, os.path.join(HERE, "roomtail.py"),
                               P(".dry.wav"), P(".wav")], env=env)
        subprocess.check_call(["sox", P(".wav"), P(".norm.wav"), "gain", "-n", "-1"])
        subprocess.check_call(["lame", "-b", "256", "--quiet", P(".norm.wav"), P(".mp3")])
        for f in (".dry.wav", ".dry.send.wav", ".norm.wav", ".wav"):
            if os.path.exists(P(f)):
                os.remove(P(f))
        print("  -> " + P(".mp3"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
