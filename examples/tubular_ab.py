#!/usr/bin/env python3
"""The tubular bells fit, by ear: before and after, at one gain a pair.

    python3 examples/tubular_ab.py [outdir]

Rendered as GM 14 was before examples/tubular_fit.py (examples/
tubular_level.py's OLD values put back) and as it is now, in the hall,
hybrid440, master -14 dB, through roomtail -- examples/pizz_ab.py's recipe:

  chimes      the Westminster quarters, in the chimes' own octave and a
              half, each stroke left to ring under the next, at mf then ff
  546         the first 45 s of 546(4).mid (chimes from the start)
  wmetune2    the first 45 s of wmetune2.mid (chimes from the start)

Default outdir ~/Downloads/tubular.
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

# the four Westminster changes, up an octave and a third into C4-F5
CHANGES = ((76, 74, 72, 67), (72, 76, 74, 67), (72, 74, 76, 72), (76, 72, 74, 67), (67, 74, 76, 72))


def chimes(dst):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=600000, time=0))
    t.append(mido.Message("program_change", program=14, time=0))
    ev = []
    now = 0
    for vel in (70, 115):
        for ch in CHANGES:
            for i, n in enumerate(ch):
                ev.append((now, "note_on", n, vel))
                ev.append((now + 1920, "note_off", n, 0))
                now += 960 if i == 3 else 480
        now += 1920
    ev.sort(key=lambda e: (e[0], e[1] == "note_on"))
    last = 0
    for tk, kind, n, v in ev:
        t.append(mido.Message(kind, note=n, velocity=v, time=tk - last))
        last = tk
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
        from tubular_level import OLD
        for k, v in OLD.items():
            setattr(T.TubularBellProperties, k, v)
    sys.argv = [os.path.join(HERE, "blockrender.py"), mid, dry, "hybrid440"]
    runpy.run_path(os.path.join(HERE, "blockrender.py"), run_name="__main__")


def main(argv):
    if len(argv) > 1 and argv[1] == "--blockrender":
        return blockrender(argv[2], argv[3], argv[4])
    from bitident import excerpt
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/tubular")
    os.makedirs(out, exist_ok=True)
    d = tempfile.mkdtemp(prefix="tube_")
    srcs = {"chimes": chimes(os.path.join(d, "chimes.mid"))}
    for name, f in (("546", "546(4).mid"), ("wmetune2", "wmetune2.mid")):
        p = os.path.join(d, name + ".mid")
        excerpt(os.path.expanduser("~/Downloads/midi/" + f), 45.0).save(p)
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
