#!/usr/bin/env python3
"""The vibraphone, celesta and tubular bells with their dampers, before and after.

    python3 examples/damper_ab.py [--root=TREE] [--tag=NAME] [OUTDIR]   # default ~/Downloads/damper_ab

Each voice plays the same four bars twice: DETACHED, the keys up between notes
(the damper falls on each), then under the DAMPER PEDAL, changed each bar (the
notes ring into each other until the foot comes up). GM 11, 8, 14 in turn,
two seconds apart. --root renders from another tree, for the A/B: before,
these voices were one-shots and both halves rang out alike.
"""
import os
import subprocess
import sys

import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPB = 480
# (program, transpose): a phrase in F, eighth notes, four bars
VOICES = [(11, 0), (8, 12), (14, -5)]
PHRASE = [65, 69, 72, 76, 74, 72, 69, 72,  64, 67, 70, 74, 72, 70, 67, 70,
          62, 65, 69, 72, 70, 69, 65, 69,  60, 64, 67, 72, 77, 76, 72, 65]


def build(path):
    m = mido.MidiFile(type=1, ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / 96), time=0))
    ev, t, e8 = [], 0, TPB // 2
    for prog, tp in VOICES:
        ev.append((t, 0, mido.Message("program_change", channel=0, program=prog)))
        for pedal in (False, True):
            for k, n in enumerate(PHRASE):
                at = t + k * e8
                if pedal and k % 8 == 0:
                    ev += [(at, 0, mido.Message("control_change", channel=0, control=64, value=0)),
                           (at + 20, 1, mido.Message("control_change", channel=0, control=64, value=127))]
                ev += [(at, 2, mido.Message("note_on", channel=0, note=n + tp, velocity=90)),
                       (at + e8 // 2, 1, mido.Message("note_off", channel=0, note=n + tp, velocity=0))]
            t += len(PHRASE) * e8
            if pedal:
                ev.append((t + 2 * TPB, 0, mido.Message("control_change", channel=0, control=64, value=0)))
            t += 4 * TPB
        t += 2 * TPB
    now = 0
    for at, _, msg in sorted(ev, key=lambda e: (e[0], e[1])):
        tr.append(msg.copy(time=at - now)); now = at
    tr.append(mido.MetaMessage("end_of_track", time=TPB * 8))
    m.save(path)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.expanduser("~/Downloads/damper_ab")
    root = next((a.split("=", 1)[1] for a in argv if a.startswith("--root=")), HERE)
    tag = next((a.split("=", 1)[1] for a in argv if a.startswith("--tag=")), "after")
    os.makedirs(out, exist_ok=True)
    P = lambda f: os.path.join(out, tag + f)                 # noqa: E731
    build(P(".mid"))
    env = dict(os.environ, TUNING_REFLECT="0")
    subprocess.check_call([sys.executable, os.path.join(root, "blockrender.py"), P(".mid"), P(".dry.wav"),
                           "hybrid"], env=env, cwd=root)
    subprocess.check_call(["sox", P(".dry.wav"), P(".norm.wav"), "reverb", "60", "50", "100", "100", "0", "-6",
                           "gain", "-n", "-1"])
    subprocess.check_call(["lame", "-b", "256", "--quiet", P(".norm.wav"), P(".mp3")])
    for f in (".dry.wav", ".norm.wav"):
        os.remove(P(f))
    print("  -> " + P(".mp3"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
