#!/usr/bin/env python3
"""The pizzicato fit, by ear: before and after, at one gain a pair.

    python3 examples/pizz_ab.py [outdir]

Four pairs, each rendered as it was before the Iowa fit (the old values put
back, from examples/pizz_level.py) and as it is now, in the hall, hybrid440,
master -14 dB, through roomtail -- render-corpus.sh's recipe:

  gm45_line   GM 45 across the section, a line from the bass's E1 up to the
              violin's G6 and back -- every register's own instrument.
  gm32_walk   GM 32, a walking line over two octaves.
  prelude2    the first 45 s of prelude2.mid, which writes GM 45.
  canon       the first 45 s of CANON.MID, whose bass is GM 32.

Default outdir ~/Downloads/pizz.

    python3 examples/pizz_ab.py --stage1 [outdir]

compares instead the first fit (approved by ear) with the violin's and viola's
two-stage decay since: a line through each one's range, and prelude2.

    python3 examples/pizz_ab.py --pluck [outdir]

the pluck point on CC74 (tonelib.pluck_point_moved): the GM 45 line, the GM 32
walk and prelude2, each at CC74 = 0 (the middle of the string), 64 (the
instrument's own point) and 127 (at the bridge), sent on every channel.
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


def line(prog, notes, beat=0.25, dst=None):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", program=prog, time=0))
    tk = int(beat * 960)
    for n in notes:
        t.append(mido.Message("note_on", note=n, velocity=80, time=0))
        t.append(mido.Message("note_off", note=n, time=tk))
    t.append(mido.Message("note_off", note=notes[-1], time=1920))
    m.save(dst)
    return dst


def with_cc74(src, value, dst):
    """src with CC74 = value on every melodic channel, before anything plays."""
    m = mido.MidiFile(src)
    t = mido.MidiTrack()
    t.extend(mido.Message("control_change", channel=c, control=74, value=value, time=0)
             for c in range(16) if c != 9)
    m.tracks.insert(0, t)
    if m.type == 0:
        m = mido.MidiFile(ticks_per_beat=m.ticks_per_beat)
        m.tracks.append(mido.merge_tracks([t, mido.MidiFile(src).tracks[0]]))
    m.save(dst)
    return dst


def render(mid, wav, old):
    env = dict(os.environ, TUNING_ROOM="hall", TUNING_MASTER_DB="-14")
    dry = wav[:-4] + "_dry.wav"
    which = old if isinstance(old, str) else ("old" if old else "new")
    cmd = [sys.executable, os.path.abspath(__file__), "--blockrender", which, mid, dry]
    subprocess.run(cmd, env=env, check=True, stdout=subprocess.DEVNULL)
    import lib
    lib.roomtail(dry, wav, env={"TUNING_ROOM": "hall"})
    return wav


# the first fit's violin and viola, before their decay went two-stage
STAGE1 = {"ViolinProperties": dict(decay_db=27.28, harmonic_decay_db=8.57, decay_register_slope=1.236,
                                   aftersound_fraction=0.0, initial_gain=0.2366),
          "ViolaProperties": dict(decay_db=23.16, harmonic_decay_db=11.56, decay_register_slope=0.941,
                                  aftersound_fraction=0.0, initial_gain=0.2326)}


def blockrender(which, mid, dry):
    """blockrender.py's own command line, with the old values swapped into the
    classes first if asked -- the renderer imports the same tonelib."""
    sys.path.insert(0, HERE)
    if which == "old":
        import tonelib as T
        from pizz_level import OLD_GM32, OLD_PIZZ
        for b in (T.ViolinProperties, T.ViolaProperties, T.CelloProperties, T.ContrabassProperties):
            for k, v in OLD_PIZZ.items():
                setattr(T.pizzicato(b), k, v)
        for k, v in OLD_GM32.items():
            setattr(T.AcousticBassProperties, k, v)
    if which == "stage1":
        import tonelib as T
        for b in (T.ViolinProperties, T.ViolaProperties):
            for k, v in STAGE1[b.__name__].items():
                setattr(T.pizzicato(b), k, v)
    sys.argv = [os.path.join(HERE, "blockrender.py"), mid, dry, "hybrid440"]
    runpy.run_path(os.path.join(HERE, "blockrender.py"), run_name="__main__")


def peak(p):
    s = subprocess.run(["sox", p, "-n", "stat"], capture_output=True, text=True).stderr
    return max(abs(float([l for l in s.splitlines() if l.startswith(k)][0].split()[-1]))
               for k in ("Maximum amplitude", "Minimum amplitude"))


def main(argv):
    if len(argv) > 1 and argv[1] == "--blockrender":
        return blockrender(argv[2], argv[3], argv[4])
    from bitident import excerpt
    stage1 = "--stage1" in argv
    pluck = "--pluck" in argv
    argv = [a for a in argv if a not in ("--stage1", "--pluck")]
    out = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/pizz")
    os.makedirs(out, exist_ok=True)
    d = tempfile.mkdtemp(prefix="pizz_")
    up = list(range(28, 91, 3))
    walk = [28, 31, 33, 35, 36, 38, 40, 43, 45, 47, 48, 47, 45, 43, 40, 38, 36, 35, 33, 31, 28]
    if pluck:
        srcs = {"gm45_line": line(45, up + up[::-1][1:], dst=os.path.join(d, "gm45_line.mid")),
                "gm32_walk": line(32, walk, beat=0.5, dst=os.path.join(d, "gm32_walk.mid"))}
        pieces = (("prelude2", "prelude2.mid"),)
        pair = ("cc0", "cc64", "cc127")
    elif stage1:
        hi = list(range(48, 92, 2))
        srcs = {"upper_line": line(45, hi + hi[::-1][1:], dst=os.path.join(d, "upper_line.mid"))}
        pieces = (("prelude2", "prelude2.mid"),)
        pair = ("stage1", "twostage")
    else:
        srcs = {"gm45_line": line(45, up + up[::-1][1:], dst=os.path.join(d, "gm45_line.mid")),
                "gm32_walk": line(32, walk, beat=0.5, dst=os.path.join(d, "gm32_walk.mid"))}
        pieces = (("prelude2", "prelude2.mid"), ("canon", "CANON.MID"))
        pair = ("old", "new")
    for name, f in pieces:
        p = os.path.join(d, name + ".mid")
        excerpt(os.path.expanduser("~/Downloads/midi/" + f), 45.0).save(p)
        srcs[name] = p
    for name, mid in srcs.items():
        if pluck:
            w = {k: render(with_cc74(mid, int(k[2:]), os.path.join(d, "%s_%s.mid" % (name, k))),
                           os.path.join(d, "%s_%s.wav" % (name, k)), "new") for k in pair}
        else:
            w = {k: render(mid, os.path.join(d, "%s_%s.wav" % (name, k)),
                           "stage1" if k == "stage1" else (k == "old")) for k in pair}
        gain = -1.0 - 20 * np.log10(max(peak(p) for p in w.values()))
        for i, k in enumerate(pair):
            mp3 = os.path.join(out, "pizz_%s_%d_%s.mp3" % (name, i + 1, k))
            tmp = os.path.join(d, "g.wav")
            subprocess.run(["sox", w[k], "-b", "24", tmp, "gain", "%.2f" % gain], check=True)
            subprocess.run(["lame", "-b", "320", "--quiet", tmp, mp3], check=True)
            print("  -> %s" % mp3)
    print("  work in %s" % d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
