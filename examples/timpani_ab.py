#!/usr/bin/env python3
"""The timpani fit, by ear: before and after, at one gain a pair.

    python3 examples/timpani_ab.py [outdir]

Rendered as GM 47 was before examples/timpani_fit.py (examples/
timpani_level.py's OLD values put back) and as it is now, in the hall,
hybrid440, master -14 dB, through roomtail -- examples/pizz_ab.py's recipe:

  timp_line   the five drums' notes struck pp, mf and ff, each left to ring,
              then a roll on the middle one swelling pp to ff and back
  thememat    the first 45 s of thememat.mid (timpani from 3.4 s)
  djchp210    the first 45 s of djchp210.mid (timpani from 9 s)

Default outdir ~/Downloads/timpani.
"""
import os
import runpy
import subprocess
import sys
import tempfile

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))

from pizz_ab import peak  # noqa: E402

NOTES = (41, 47, 49, 52, 55)          # the five drums' nearest notes


def timp_line(dst):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", program=47, time=0))
    gap = 0
    for vel in (30, 67, 120):
        for n in NOTES:
            t.append(mido.Message("note_on", note=n, velocity=vel, time=gap))
            t.append(mido.Message("note_off", note=n, time=480))
            gap = 480
    # a roll: sixteenths for four bars, swelling and falling
    k = 64
    for i in range(k):
        vel = int(25 + 95 * np.sin(np.pi * i / (k - 1)))
        t.append(mido.Message("note_on", note=49, velocity=vel, time=gap if i == 0 else 0))
        t.append(mido.Message("note_off", note=49, time=120))
        gap = 0
    t.append(mido.Message("note_off", note=49, time=1920))
    m.save(dst)
    return dst


def render(mid, wav, which):
    env = dict(os.environ, TUNING_ROOM="hall", TUNING_MASTER_DB="-14")
    dry = wav[:-4] + "_dry.wav"
    subprocess.run([sys.executable, os.path.abspath(__file__), "--blockrender", which, mid, dry],
                   env=env, check=True, stdout=subprocess.DEVNULL)
    import lib
    lib.roomtail(dry, wav, env={"TUNING_ROOM": "hall"})
    return wav


def blockrender(which, mid, dry):
    sys.path.insert(0, HERE)
    if which == "old":
        import tonelib as T
        from timpani_level import OLD
        for k, v in OLD.items():
            setattr(T.TimpaniProperties, k, v)
    sys.argv = [os.path.join(HERE, "blockrender.py"), mid, dry, "hybrid440"]
    runpy.run_path(os.path.join(HERE, "blockrender.py"), run_name="__main__")


def main(argv):
    if len(argv) > 1 and argv[1] == "--blockrender":
        return blockrender(argv[2], argv[3], argv[4])
    from bitident import excerpt
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/timpani")
    os.makedirs(out, exist_ok=True)
    d = tempfile.mkdtemp(prefix="timp_")
    srcs = {"timp_line": timp_line(os.path.join(d, "timp_line.mid"))}
    for name in ("thememat", "djchp210"):
        p = os.path.join(d, name + ".mid")
        excerpt(os.path.expanduser("~/Downloads/midi/%s.mid" % name), 45.0).save(p)
        srcs[name] = p
    pair = ("old", "new")
    for name, mid in srcs.items():
        w = {k: render(mid, os.path.join(d, "%s_%s.wav" % (name, k)), k) for k in pair}
        gain = -1.0 - 20 * np.log10(max(peak(q) for q in w.values()))
        for i, k in enumerate(pair):
            mp3 = os.path.join(out, "%s_%d_%s.mp3" % (name, i + 1, k))
            tmp = os.path.join(d, "g.wav")
            subprocess.run(["sox", w[k], "-b", "24", tmp, "gain", "%.2f" % gain], check=True)
            subprocess.run(["lame", "-b", "320", "--quiet", tmp, mp3], check=True)
            print("  -> %s" % mp3)
    print("  work in %s" % d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
