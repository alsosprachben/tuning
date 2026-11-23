#!/usr/bin/env python3
"""A melodic voice at a commit against the tree, for Ben's ear: a scale of
single notes across its compass at three velocities, then chords -- 'old'
rendered with the commit's tonelib.py and patch_map.py (DRUMKIT_AB_REF's, else
HEAD's), 'new' with the tree's. (examples/drumkit_ab.py, for a drum set.)

    python3 examples/refit_ab.py PROGRAM[.BANK] NAME [LO HI]     (14.8: GS's variation 8)
        -> ~/Music/licence_refits/NAME_{old,new}.mp3
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
if os.environ.get("REFIT_AB_OLD"):
    sys.path.insert(0, os.environ["REFIT_AB_OLD"])
OUT = os.path.expanduser("~/Music/licence_refits")


def midi(program, lo, hi):
    import mido
    m = mido.MidiFile(type=0, ticks_per_beat=480)
    t = mido.MidiTrack(); m.tracks.append(t)
    program, _, bank = str(program).partition(".")
    if bank:
        t.append(mido.Message("control_change", channel=0, control=0, value=int(bank), time=0))
    program = int(program)
    t.append(mido.Message("program_change", channel=0, program=program, time=0))
    for v in (40, 80, 120):
        for n in range(lo, hi + 1, 5):
            t.append(mido.Message("note_on", channel=0, note=n, velocity=v, time=0))
            t.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=600))
    for ch, v in (((48, 55, 64, 70), 70), ((53, 60, 65, 69, 74), 100), ((43, 50, 59, 65, 71), 120)):
        for n in ch:
            t.append(mido.Message("note_on", channel=0, note=n, velocity=v, time=0))
        for i, n in enumerate(ch):
            t.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=1920 if i == 0 else 0))
    return m


def render(program, name, tag, lo, hi):
    import numpy as np
    import blockrender as B
    from scipy.io import wavfile
    L, R = B.render(midi(program, lo, hi))[:2]
    y = np.stack([L, R], 1); y = y / (np.abs(y).max() + 1e-12) * 0.7
    w = os.path.join(OUT, "%s_%s.wav" % (name, tag))
    wavfile.write(w, B.SR, (y * 32767).astype(np.int16))
    subprocess.run(["lame", "--quiet", "-b", "256", w, w[:-4] + ".mp3"], check=True)
    os.remove(w)


def main(argv):
    program, name = argv[1], argv[2]
    lo, hi = (int(argv[3]), int(argv[4])) if len(argv) > 4 and argv[3] != "old" and argv[3] != "new" else (36, 96)
    if argv[-1] in ("old", "new"):
        return render(program, name, argv[-1], lo, hi)
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        for mod in ("tonelib.py", "patch_map.py"):
            src = subprocess.run(["git", "show", os.environ.get("DRUMKIT_AB_REF", "HEAD") + ":" + mod],
                                 capture_output=True, text=True, check=True, cwd=HERE).stdout
            open(os.path.join(d, mod), "w").write(src)
        for tag in ("old", "new"):
            env = dict(os.environ)
            env.pop("REFIT_AB_OLD", None)
            if tag == "old":
                env["REFIT_AB_OLD"] = d
            subprocess.run([sys.executable, os.path.abspath(__file__)] + argv[1:] + [tag], env=env, check=True)
    print("written %s_{old,new}.mp3" % name)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
