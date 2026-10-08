#!/usr/bin/env python3
"""The tremolo fit, by ear: before and after, at one gain a pair.

    python3 examples/trem_ab.py [outdir]

GM 44 as it was before examples/trem_fit.py (9.5 Hz, depth 0.70, +/-20% per
player) and as it is now, in the hall, hybrid440, master -14 dB, through
roomtail -- examples/pizz_ab.py's recipe. No corpus file plays GM 44, so:

  chords   a progression held in tremolo across the section -- cellos,
           violas, violins each in their register -- pp swelling to ff
           (CC11) and back
  line     a melody on GM 48 over a held tremolo bass and inner voices

Default outdir ~/Downloads/trem.
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

OLD = dict(tremolo_hz=9.5, tremolo_depth=0.70, tremolo_scatter=0.20)
PROG = ((43, 55, 62, 70), (41, 53, 60, 69), (38, 50, 57, 65), (43, 50, 59, 67), (36, 48, 55, 64))


def chords(dst):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=750000, time=0))
    t.append(mido.Message("program_change", program=44, time=0))
    bar = 1920
    swell = [int(30 + 97 * np.sin(np.pi * i / (len(PROG) * 8 - 1))) for i in range(len(PROG) * 8)]
    k = 0
    for ch in PROG:
        for n in ch:
            t.append(mido.Message("note_on", note=n, velocity=80, time=0))
        for _ in range(8):
            t.append(mido.Message("control_change", control=11, value=swell[k], time=bar // 8))
            k += 1
        for i, n in enumerate(ch):
            t.append(mido.Message("note_off", note=n, time=0))
    m.save(dst)
    return dst


def line(dst):
    m = mido.MidiFile(ticks_per_beat=480)
    trem, mel = mido.MidiTrack(), mido.MidiTrack()
    m.tracks += [trem, mel]
    trem.append(mido.MetaMessage("set_tempo", tempo=600000, time=0))
    trem.append(mido.Message("program_change", channel=0, program=44, time=0))
    mel.append(mido.Message("program_change", channel=1, program=48, time=0))
    for ch in PROG:
        for n in ch[:3]:
            trem.append(mido.Message("note_on", channel=0, note=n, velocity=60, time=0))
        trem.append(mido.Message("note_off", channel=0, note=ch[0], time=1920))
        for n in ch[1:3]:
            trem.append(mido.Message("note_off", channel=0, note=n, time=0))
    tune = (74, 72, 70, 69, 72, 70, 69, 67, 69, 65, 67, 69, 67, 66, 67, 67, 64, 65, 67, 72)
    for n in tune:
        mel.append(mido.Message("note_on", channel=1, note=n, velocity=85, time=0))
        mel.append(mido.Message("note_off", channel=1, note=n, time=480))
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
            for k, v in OLD.items():
                setattr(T.tremolo_bow(c), k, v)
    sys.argv = [os.path.join(HERE, "blockrender.py"), mid, dry, "hybrid440"]
    runpy.run_path(os.path.join(HERE, "blockrender.py"), run_name="__main__")


def main(argv):
    if len(argv) > 1 and argv[1] == "--blockrender":
        return blockrender(argv[2], argv[3], argv[4])
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/trem")
    os.makedirs(out, exist_ok=True)
    d = tempfile.mkdtemp(prefix="trem_")
    srcs = {"chords": chords(os.path.join(d, "chords.mid")), "line": line(os.path.join(d, "line.mid"))}
    pair = ("old", "new")
    for name, mid in srcs.items():
        w = {k: render(mid, os.path.join(d, "%s_%s.wav" % (name, k)), k) for k in pair}
        gain = -1.0 - 20 * np.log10(max(peak(q) for q in w.values()))
        for i, k in enumerate(pair):
            mp3 = os.path.join(out, "trem_%s_%d_%s.mp3" % (name, i + 1, k))
            tmp = os.path.join(d, "g.wav")
            subprocess.run(["sox", w[k], "-b", "24", tmp, "gain", "%.2f" % gain], check=True)
            subprocess.run(["lame", "-b", "320", "--quiet", tmp, mp3], check=True)
            print("  -> %s" % mp3)
    print("  work in %s" % d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
