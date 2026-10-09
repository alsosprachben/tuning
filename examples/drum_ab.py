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
  snare      the snare alone at six strokes, then a beat with ghost notes and a
             roll, at mf and ff
  melodic_tom  GM 117: strokes down the range, a fill across the floor/rack
             split, a tune over a floor-tom pedal
  sidestick  the side stick alone at six strokes, a bossa nova on the 3-2
             clave at mf and f, then off-beats beside a snare backbeat
  tambourine the tambourine alone at six strokes, on 2 and 4, in eighths, then
             a written-out roll
  latin      the hand percussion (56, 60-64, 67, 68, 70) alone, three strokes
             each, then a son groove with all of them

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


def snare(dst):
    """The snare alone at six strokes, ghost to rimshot-hard, each left to
    ring; then a beat with backbeats and ghost notes, at mf and ff."""
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    ev = []
    now = 0
    q = 480

    def hit(tk, n, v):
        ev.append((tk, "note_on", n, v))
        ev.append((tk + 60, "note_off", n, 0))
    for v in (30, 50, 70, 90, 110, 127):
        hit(now, 38, v)
        now += 2 * q
    for v in (90, 122):
        for bar in range(4):
            for b in range(4):
                s_ = now + b * q
                if b in (0, 2):
                    hit(s_, 36, int(v * 0.85))
                if b in (1, 3):
                    hit(s_, 38, v)
                for e in range(4):
                    hit(s_ + e * q // 4, 42, int(v * (0.55 if e % 2 else 0.7)))
                # ghost notes on the e and a of 2 and 4
                if b in (1, 3):
                    hit(s_ + 3 * q // 4, 38, 32)
                if b in (0, 2):
                    hit(s_ + 3 * q // 4, 38, 28)
            now += 4 * q
        # a sixteenth-note roll into the next
        for i in range(16):
            hit(now + i * q // 4, 38, int(v * (0.5 + 0.5 * i / 15)))
        now += 4 * q
    hit(now, 36, 110)
    hit(now, 49, 110)
    ev.sort(key=lambda e: (e[0], e[1] == "note_on"))
    last = 0
    for tk, kind, n, v in ev:
        t.append(mido.Message(kind, channel=9, note=n, velocity=v, time=tk - last))
        last = tk
    m.save(dst)
    return dst


def _save(dst, ev):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    ev.sort(key=lambda e: (e[0], e[1] == "note_on"))
    last = 0
    for tk, kind, n, v in ev:
        t.append(mido.Message(kind, channel=9, note=n, velocity=v, time=tk - last))
        last = tk
    m.save(dst)
    return dst


def sidestick(dst):
    """The side stick alone at six strokes, then a bossa nova: the
    cross-stick on the clave's 3-2 under eighth-note hats and the kick's
    1 and the and of 2, at mf and f; then a snare backbeat beside it."""
    ev = []
    q = 480

    def hit(tk, n, v):
        ev.append((tk, "note_on", n, v))
        ev.append((tk + 60, "note_off", n, 0))
    now = 0
    for v in (30, 50, 70, 90, 110, 127):
        hit(now, 37, v)
        now += 2 * q
    clave = (0, 3, 6, 10, 12)          # 3-2 son clave, in eighths over two bars
    for v in (80, 110):
        for rep in range(3):
            for e in range(16):
                tk = now + e * q // 2
                hit(tk, 42, int(v * (0.6 if e % 2 else 0.75)))
                if e % 4 in (0, 3):
                    hit(tk, 36, int(v * 0.8))
                if e in clave:
                    hit(tk, 37, v)
            now += 8 * q
    for bar in range(2):
        for b in range(4):
            tk = now + b * q
            hit(tk, 42, 80)
            hit(tk + q // 2, 42, 60)
            hit(tk, 36 if b in (0, 2) else 38, 100)
            hit(tk + q // 2, 37, 90)
        now += 4 * q
    return _save(dst, ev)


def tambourine(dst):
    """The tambourine alone at six strokes, then on 2 and 4 over a beat,
    then in eighths, then a written-out roll of short notes (as Holst's
    Jupiter writes it)."""
    ev = []
    q = 480

    def hit(tk, n, v, d=60):
        ev.append((tk, "note_on", n, v))
        ev.append((tk + d, "note_off", n, 0))
    now = 0
    for v in (30, 50, 70, 90, 110, 127):
        hit(now, 54, v)
        now += 2 * q
    for eighths in (False, True):
        for bar in range(4):
            for b in range(4):
                tk = now + b * q
                hit(tk, 36 if b in (0, 2) else 38, 100)
                hit(tk, 42, 80)
                hit(tk + q // 2, 42, 60)
                if eighths:
                    hit(tk, 54, 100 if b in (1, 3) else 80)
                    hit(tk + q // 2, 54, 70)
                elif b in (1, 3):
                    hit(tk, 54, 105)
            now += 4 * q
    for i in range(32):
        hit(now + i * 60, 54, int(60 + 50 * i / 31), 50)
    now += 32 * 60 + q
    hit(now, 54, 120)
    hit(now, 36, 110)
    return _save(dst, ev)


def latin(dst):
    """The hand percussion alone -- cowbell, agogo high and low, the three
    congas (muted, open, low), the two bongos, maracas -- each at three
    strokes; then two bars of a son groove, four times over: campana on the
    beat, agogo, a conga tumbao (muted on 2, open tones on 4 and its and),
    bongo martillo, maracas in eighths, kick on 1 and 3."""
    ev = []
    q = 480

    def hit(tk, n, v, d=60):
        ev.append((tk, "note_on", n, v))
        ev.append((tk + d, "note_off", n, 0))
    now = 0
    for n in (56, 67, 68, 62, 63, 64, 60, 61, 70):
        for v in (50, 90, 120):
            hit(now, n, v, 200 if n == 70 else 60)
            now += q
        now += q
    for rep in range(4):
        for bar in range(2):
            for b in range(4):
                tk = now + b * q
                hit(tk, 56, 100 if b == 0 else 85)
                if b in (0, 2):
                    hit(tk, 36, 80)
                hit(tk, 70, 75, 200)
                hit(tk + q // 2, 70, 60, 200)
                hit(tk, 60, 95 if b == 0 else 70)
                hit(tk + q // 2, 61 if b % 2 else 60, 65)
                if b == 1:
                    hit(tk, 62, 85)
                if b == 3:
                    hit(tk, 63, 100)
                    hit(tk + q // 2, 64 if bar else 63, 95)
                if (bar * 4 + b) % 3 == 0:
                    hit(tk + q // 2, 67, 80)
                if (bar * 4 + b) % 3 == 1:
                    hit(tk, 68, 80)
            now += 4 * q
    return _save(dst, ev)


def melodic_tom(dst):
    """GM 117 on a melodic channel: single strokes down the range, left to
    ring (the floor tom under G2, the rack tom from G2 up), a fill
    descending across the split, and a tune of toms in thirds over a
    floor-tom pedal."""
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=117, time=0))
    ev = []
    now = 0
    q = 480

    def hit(tk, n, v, d=120):
        ev.append((tk, "note_on", n, v))
        ev.append((tk + d, "note_off", n, 0))
    for n in (67, 60, 55, 48, 43, 40, 36, 31):
        hit(now, n, 100)
        now += 3 * q
    for v in (80, 115):
        for i, n in enumerate((67, 64, 60, 57, 55, 52, 48, 45, 43, 41, 40, 38, 36, 35, 33, 31)):
            hit(now + i * q // 4, n, v if i % 4 == 0 else int(v * 0.85))
        now += 4 * q + 2 * q
    tune = (60, 64, 67, 64, 62, 65, 69, 65, 64, 67, 72, 67, 65, 62, 60, 55)
    for i, n in enumerate(tune):
        hit(now + i * q // 2, n, 90 if i % 2 == 0 else 75)
        if i % 4 == 0:
            hit(now + i * q // 2, 36, 95)
    now += 8 * q
    hit(now, 31, 110)
    ev.sort(key=lambda e: (e[0], e[1] == "note_on"))
    last = 0
    for tk, kind, n, v in ev:
        t.append(mido.Message(kind, channel=0, note=n, velocity=v, time=tk - last))
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
                "crashes": crashes(os.path.join(d, "crashes.mid")),
                "snare": snare(os.path.join(d, "snare.mid")),
                "melodic_tom": melodic_tom(os.path.join(d, "melodic_tom.mid")),
                "sidestick": sidestick(os.path.join(d, "sidestick.mid")),
                "tambourine": tambourine(os.path.join(d, "tambourine.mid")),
                "latin": latin(os.path.join(d, "latin.mid"))}
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
