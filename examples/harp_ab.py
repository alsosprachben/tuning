#!/usr/bin/env python3
"""The harp fit, by ear: before and after, at one gain a pair.

    python3 examples/harp_ab.py [outdir]

Rendered as GM 46 was before examples/harp_fit.py (examples/harp_level.py's
OLD values put back) and as it is now, in the hall, hybrid440, master -14 dB,
through roomtail -- examples/pizz_ab.py's recipe:

  harp_line   arpeggiated across the compass, E1 to F7 and back, each note
              left to ring under the next as a harp's does
  prelude2    the first 45 s of prelude2.mid, whose channel 6 is the harp

Default outdir ~/Downloads/harp.
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


def harp_line(dst):
    """Rising and falling arpeggios, each note held a bar: no damping."""
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", program=46, time=0))
    chord = (0, 4, 7)
    notes = [o * 12 + c for o in range(2, 9) for c in chord if 28 <= o * 12 + c <= 101]
    notes = notes + notes[::-1][1:]
    ev = []
    for i, n in enumerate(notes):
        ev.append((i * 240, "note_on", n))
        ev.append((i * 240 + 1920, "note_off", n))
    ev.sort()
    now = 0
    for tk, kind, n in ev:
        t.append(mido.Message(kind, note=n, velocity=80, time=tk - now))
        now = tk
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
        from harp_level import OLD
        for k, v in OLD.items():
            setattr(T.HarpProperties, k, v)
    sys.argv = [os.path.join(HERE, "blockrender.py"), mid, dry, "hybrid440"]
    runpy.run_path(os.path.join(HERE, "blockrender.py"), run_name="__main__")


def main(argv):
    if len(argv) > 1 and argv[1] == "--blockrender":
        return blockrender(argv[2], argv[3], argv[4])
    from bitident import excerpt
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/harp")
    os.makedirs(out, exist_ok=True)
    d = tempfile.mkdtemp(prefix="harp_")
    srcs = {"harp_line": harp_line(os.path.join(d, "harp_line.mid"))}
    p = os.path.join(d, "prelude2.mid")
    excerpt(os.path.expanduser("~/Downloads/midi/prelude2.mid"), 45.0).save(p)
    srcs["prelude2"] = p
    pair = ("old", "new")
    for name, mid in srcs.items():
        w = {k: render(mid, os.path.join(d, "%s_%s.wav" % (name, k)), k) for k in pair}
        gain = -1.0 - 20 * np.log10(max(peak(q) for q in w.values()))
        for i, k in enumerate(pair):
            mp3 = os.path.join(out, "harp_%s_%d_%s.mp3" % (name, i + 1, k))
            tmp = os.path.join(d, "g.wav")
            subprocess.run(["sox", w[k], "-b", "24", tmp, "gain", "%.2f" % gain], check=True)
            subprocess.run(["lame", "-b", "320", "--quiet", tmp, mp3], check=True)
            print("  -> %s" % mp3)
    print("  work in %s" % d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
