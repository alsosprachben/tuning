#!/usr/bin/env python3
"""The section fit, by ear: before and after, at one gain a pair.

    python3 examples/sect_ab.py [outdir]

The bowed sections as they were before examples/sect_fit.py (+/-5 cents of
vibrato a player, GM 49's entry on its 0.30 s valve time) and as they are
now (+/-15, GM 49 swelling in over 1.1 s), in the hall, hybrid440, master
-14 dB, through roomtail -- examples/pizz_ab.py's recipe:

  beethoven  the first 45 s of beethoven5_1.mid, whose strings are GM 40-43
  slow       chords held on GM 49, the pad Roland's SlowStr is

Default outdir ~/Downloads/sect.
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

CHORDS = ((48, 55, 64, 72), (45, 57, 64, 72), (41, 57, 65, 69), (43, 55, 62, 71), (48, 55, 64, 72))


def slow(dst):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=750000, time=0))
    t.append(mido.Message("program_change", program=49, time=0))
    for ch in CHORDS:
        for n in ch:
            t.append(mido.Message("note_on", note=n, velocity=75, time=0))
        t.append(mido.Message("note_off", note=ch[0], time=3840))
        for n in ch[1:]:
            t.append(mido.Message("note_off", note=n, time=0))
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
        for c in (T.ViolinProperties, T.ViolaProperties, T.CelloProperties, T.ContrabassProperties):
            c.section_vibrato_cents = 5.0
            T.slow_bow(c).attack_time = None
    sys.argv = [os.path.join(HERE, "blockrender.py"), mid, dry, "hybrid440"]
    runpy.run_path(os.path.join(HERE, "blockrender.py"), run_name="__main__")


def main(argv):
    if len(argv) > 1 and argv[1] == "--blockrender":
        return blockrender(argv[2], argv[3], argv[4])
    from bitident import excerpt
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/sect")
    os.makedirs(out, exist_ok=True)
    d = tempfile.mkdtemp(prefix="sect_")
    p = os.path.join(d, "beethoven.mid")
    excerpt(os.path.expanduser("~/Downloads/midi/beethoven5_1.mid"), 45.0).save(p)
    srcs = {"beethoven": p, "slow": slow(os.path.join(d, "slow.mid"))}
    pair = ("old", "new")
    for name, mid in srcs.items():
        w = {k: render(mid, os.path.join(d, "%s_%s.wav" % (name, k)), k) for k in pair}
        gain = -1.0 - 20 * np.log10(max(peak(q) for q in w.values()))
        for i, k in enumerate(pair):
            mp3 = os.path.join(out, "sect_%s_%d_%s.mp3" % (name, i + 1, k))
            tmp = os.path.join(d, "g.wav")
            subprocess.run(["sox", w[k], "-b", "24", tmp, "gain", "%.2f" % gain], check=True)
            subprocess.run(["lame", "-b", "320", "--quiet", tmp, mp3], check=True)
            print("  -> %s" % mp3)
    print("  work in %s" % d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
