#!/usr/bin/env python3
"""The Electronic kit (program 24 on the drum channel), before and after
examples/elkit_fit.py -- and FluidR3's own Electronic kit for reference.

    python3 examples/elkit_ab.py [--root=TREE] [--tag=NAME] [--fluid | --sf=SF2] [OUTDIR]
                                                         # default ~/Downloads/elkit_ab

Four bars of an 80s pattern -- kick on one and three, the Simmons snare on two
and four, eighths on the Standard closed hat, the gated snare taking bar
three's backbeat, a fill down the six toms -- then each Electronic note alone,
a second apart. --root renders from another tree; --fluid (or --sf=, any
SoundFont: GeneralUser GS is the GS-modelled one) renders the same file
through timidity (measured only: a local reference, never redistributed).
"""
import os
import subprocess
import sys
import tempfile

import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPB = 480
ALONE = (36, 38, 40, 41, 43, 45, 47, 48, 50)


def build(path):
    m = mido.MidiFile(type=1, ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / 112), time=0))
    tr.append(mido.Message("program_change", channel=9, program=24, time=0))
    ev, e8 = [], TPB // 2
    for bar in range(4):
        t0 = bar * 4 * TPB
        for k in range(8):
            ev.append((t0 + k * e8, 42, 70 if k % 2 else 90))
        ev += [(t0, 36, 110), (t0 + 2 * TPB, 36, 105)]
        sn = 40 if bar == 2 else 38
        ev += [(t0 + TPB, sn, 105), (t0 + 3 * TPB, sn, 110)]
        if bar == 3:
            ev = [e for e in ev if not (e[0] >= t0 + 2 * TPB and e[1] in (38, 42))]
            for k, n in enumerate((50, 48, 47, 45, 43, 41)):
                ev.append((t0 + 2 * TPB + k * (2 * TPB // 6), n, 100))
    t = 4 * 4 * TPB + 2 * TPB
    ev.append((t, 36, 110)); ev.append((t, 49, 100))          # land on a crash
    t += 4 * TPB
    for n in ALONE:
        ev.append((t, n, 105)); t += 2 * TPB
    msgs = sorted([(at, 1, n, v) for at, n, v in ev] + [(at + 60, 0, n, 0) for at, n, _v in ev])
    now = 0
    for at, on, n, v in msgs:
        tr.append(mido.Message("note_on" if on else "note_off", channel=9, note=n, velocity=v,
                               time=at - now)); now = at
    tr.append(mido.MetaMessage("end_of_track", time=4 * TPB))
    m.save(path)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.expanduser("~/Downloads/elkit_ab")
    root = next((a.split("=", 1)[1] for a in argv if a.startswith("--root=")), HERE)
    tag = next((a.split("=", 1)[1] for a in argv if a.startswith("--tag=")), "after")
    os.makedirs(out, exist_ok=True)
    P = lambda f: os.path.join(out, tag + f)                 # noqa: E731
    build(P(".mid"))
    sf = next((a.split("=", 1)[1] for a in argv if a.startswith("--sf=")), None)
    if "--fluid" in argv:
        sf = "/usr/share/sounds/sf2/FluidR3_GM.sf2"
    if sf:
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "k.cfg")
            with open(cfg, "w") as f:
                f.write("drumset 24\n")
                for n in range(27, 88):
                    f.write('%d %%font "%s" 128 24 %d\n' % (n, sf, n))
            subprocess.check_call(["timidity", "-c", cfg, "-Ow", "-o", P(".dry.wav"), "-s", "44100",
                                   "-EFreverb=d", "-EFchorus=d", "--quiet=2", P(".mid")],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        env = dict(os.environ, TUNING_REFLECT="0")
        subprocess.check_call([sys.executable, os.path.join(root, "blockrender.py"), P(".mid"), P(".dry.wav"),
                               "hybrid"], env=env, cwd=root)
    subprocess.check_call(["sox", P(".dry.wav"), P(".norm.wav"), "reverb", "40", "50", "60", "100", "0", "-9",
                           "gain", "-n", "-1"])
    subprocess.check_call(["lame", "-b", "256", "--quiet", P(".norm.wav"), P(".mp3")])
    for f in (".dry.wav", ".norm.wav"):
        os.remove(P(f))
    print("  -> " + P(".mp3"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
