#!/usr/bin/env python3
"""The kit's kick and toms fit, by ear: before and after, at one gain a pair.

    python3 examples/drum_ab.py [outdir] [--old=REV | --old-tree=DIR] [--src=groove,crashes,...]

Rendered as the drums were at REV (default HEAD, from a git worktree of it,
since the fit changed four classes and the percussion map) and as they are
now, in the hall, hybrid440, master -14 dB, through roomtail --
examples/pizz_ab.py's recipe:

  groove     kick and toms alone, then under a snare and hats: four bars of a
             rock beat at three dynamics, a tom fill down the six toms, single
             strokes on each drum left to ring, and the same at pp
  qkbttl03   the first 45 s of qkbttl03.mid (toms throughout)
  cathartic  the first 45 s of Cathartic Age.mid (a busy kick)
  crashes    each crash alone at four strokes, left to ring, then both over a
             beat at mf and ff

Default outdir ~/Downloads/drums.
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

TOMS = (50, 48, 47, 45, 43, 41)


def groove(dst):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    ev = []
    now = 0
    q = 480

    def hit(tk, n, v):
        ev.append((tk, "note_on", n, v))
        ev.append((tk + 120, "note_off", n, 0))
    # single strokes, each left to ring: kick, then every tom, mf then ff
    for v in (70, 115):
        for n in (36, 35) + TOMS[::-1]:
            hit(now, n, v)
            now += 3 * q
    # the beat, kick and toms alone, then with snare and hats; pp, mf, ff
    for v in (45, 80, 115):
        for band in (False, True):
            for bar in range(2):
                for b in range(4):
                    s = now + b * q
                    if b in (0, 2):
                        hit(s, 36, v)
                    if b == 2:
                        hit(s + q // 2, 36, int(v * 0.8))
                    if band:
                        if b in (1, 3):
                            hit(s, 38, v)
                        hit(s, 42, int(v * 0.8))
                        hit(s + q // 2, 42, int(v * 0.6))
                    elif b in (1, 3):
                        hit(s, 45 if b == 1 else 43, int(v * 0.9))
                now += 4 * q
            # the fill: sixteenths down the toms, into a kick and crash
            for i in range(16):
                hit(now + i * q // 4, TOMS[min(5, i * 6 // 16)], v if i % 4 == 0 else int(v * 0.85))
            now += 4 * q
            hit(now, 36, v)
            hit(now, 49, v)
            now += 4 * q
    ev.sort(key=lambda e: (e[0], e[1] == "note_on"))
    last = 0
    for tk, kind, n, v in ev:
        t.append(mido.Message(kind, channel=9, note=n, velocity=v, time=tk - last))
        last = tk
    m.save(dst)
    return dst


def crashes(dst):
    """Each crash alone at four strokes, left to ring; then both over a beat,
    crash on every bar's downbeat, at mf and ff."""
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    ev = []
    now = 0
    q = 480

    def hit(tk, n, v):
        ev.append((tk, "note_on", n, v))
        ev.append((tk + 120, "note_off", n, 0))
    for n in (49, 57):
        for v in (40, 70, 100, 127):
            hit(now, n, v)
            now += 8 * q
    for v in (85, 120):
        for bar in range(8):
            for b in range(4):
                s_ = now + b * q
                if b == 0:
                    hit(s_, 49 if bar % 2 == 0 else 57, v)
                if b in (0, 2):
                    hit(s_, 36, int(v * 0.85))
                if b in (1, 3):
                    hit(s_, 38, int(v * 0.85))
                hit(s_ + q // 2, 42, int(v * 0.5))
            now += 4 * q
    hit(now, 49, 127)
    hit(now, 57, 127)
    hit(now, 36, 110)
    ev.sort(key=lambda e: (e[0], e[1] == "note_on"))
    last = 0
    for tk, kind, n, v in ev:
        t.append(mido.Message(kind, channel=9, note=n, velocity=v, time=tk - last))
        last = tk
    m.save(dst)
    return dst


def render(mid, wav, which, tree):
    env = dict(os.environ, TUNING_ROOM="hall", TUNING_MASTER_DB="-14")
    dry = wav[:-4] + "_dry.wav"
    subprocess.run([sys.executable, os.path.abspath(__file__), "--blockrender", tree, mid, dry],
                   env=env, check=True, stdout=subprocess.DEVNULL)
    import lib
    lib.roomtail(dry, wav, env={"TUNING_ROOM": "hall"})
    return wav


def blockrender(tree, mid, dry):
    sys.path.insert(0, tree)
    os.chdir(tree)
    sys.argv = [os.path.join(tree, "blockrender.py"), mid, dry, "hybrid440"]
    runpy.run_path(os.path.join(tree, "blockrender.py"), run_name="__main__")


def main(argv):
    if len(argv) > 1 and argv[1] == "--blockrender":
        return blockrender(argv[2], argv[3], argv[4])
    from bitident import excerpt
    pos = [a for a in argv[1:] if not a.startswith("--")]
    rev = next((a.split("=", 1)[1] for a in argv if a.startswith("--old=")), "HEAD")
    out = pos[0] if pos else os.path.expanduser("~/Downloads/drums")
    os.makedirs(out, exist_ok=True)
    d = tempfile.mkdtemp(prefix="drum_")
    old = os.path.join(d, "old_tree")
    # --old-tree=DIR: a tree already made (say, today's with one change undone),
    # copied in so it sits beside the siblings as a worktree would
    given = next((a.split("=", 1)[1] for a in argv if a.startswith("--old-tree=")), None)
    if given:
        import shutil
        shutil.copytree(given, old, symlinks=True)
    else:
        subprocess.run(["git", "-C", HERE, "worktree", "add", "--detach", old, rev], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # the tree imports its siblings (../path), and the kernel is built, not committed
    for sib in os.listdir(os.path.dirname(HERE)):
        src = os.path.join(os.path.dirname(HERE), sib)
        if os.path.isdir(src) and not os.path.exists(os.path.join(d, sib)):
            os.symlink(src, os.path.join(d, sib))
    for f in os.listdir(HERE):
        if f.endswith(".so") and not os.path.exists(os.path.join(old, f)):
            os.symlink(os.path.join(HERE, f), os.path.join(old, f))
    try:
        srcs = {"groove": groove(os.path.join(d, "groove.mid")),
                "crashes": crashes(os.path.join(d, "crashes.mid"))}
        p = os.path.join(d, "qkbttl03.mid")
        excerpt(os.path.expanduser("~/Downloads/midi/qkbttl03.mid"), 45.0).save(p)
        srcs["qkbttl03"] = p
        p = os.path.join(d, "cathartic.mid")
        excerpt(os.path.expanduser("~/Downloads/midi/Cathartic%20Age.mid"), 45.0).save(p)
        srcs["cathartic"] = p
        only = next((a.split("=", 1)[1].split(",") for a in argv if a.startswith("--src=")), None)
        if only:
            srcs = {k: v for k, v in srcs.items() if k in only}
        trees = (("old", old), ("new", HERE))
        for name, mid in srcs.items():
            w = {k: render(mid, os.path.join(d, "%s_%s.wav" % (name, k)), k, tr) for k, tr in trees}
            gain = -1.0 - 20 * np.log10(max(peak(q) for q in w.values()))
            for i, (k, _) in enumerate(trees):
                mp3 = os.path.join(out, "%s_%d_%s.mp3" % (name, i + 1, k))
                tmp = os.path.join(d, "g.wav")
                subprocess.run(["sox", w[k], "-b", "24", tmp, "gain", "%.2f" % gain], check=True)
                subprocess.run(["lame", "-b", "320", "--quiet", tmp, mp3], check=True)
                print("  -> %s" % mp3)
    finally:
        subprocess.run(["git", "-C", HERE, "worktree", "remove", "--force", old],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("  work in %s" % d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
