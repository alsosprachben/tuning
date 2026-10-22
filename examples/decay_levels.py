#!/usr/bin/env python3
"""Where our notes carry more energy than GeneralUser GS's AFTER the onset the
trims match -- the decay while held and the release after note-off.

    python3 examples/decay_levels.py [--vel=100] [--progs=0,30,...] [--out=FILE.tsv]

The trims (sfx_levels.py --trim) match each program's loudest 150 ms, the
onset, so a modelled decay or ring longer than a sample's envelope never
enters them -- but in a dense passage those tails overlap and stack: storm_pro
at the default master clipped on 3.6% of its samples and needed 12 dB less;
Tokei did not clip at all.

Each program's note as sfx_levels.py plays it (onset at 0.25 s, held 1.5 s,
then let go), and the kit's core notes, through GeneralUser GS (timidity,
reverb and chorus off) and ours (dry, no reflections). K-weighted power
(BS.1770), each note re ITS OWN loudest 150 ms, so the onset trims drop out:

  sustain   mean power from 150 ms after the peak to note-off, dB re peak
  release   energy from note-off to 2 s after, in seconds at peak power
  total     the note's whole energy in seconds at peak power -- what a dense
            passage stacks; ours less GU's in dB is how much louder a mix of
            such notes plays than its onsets say
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

import mido  # noqa: E402

from drum_fit import read  # noqa: E402
from gm_coverage import GM  # noqa: E402
from kit_levels import kweight  # noqa: E402
from sfx_levels import ALL, KIT, drum_mid, gu_path, note_mid  # noqa: E402

NAMES = GM               # gm_coverage: the 128 names, in order
WIN = 0.15          # the trims' window (crash_fit.level)
HOLD = 1.5          # note_mid's held length
DRUM_HOLD = 0.125   # drum_mid's
AFTER = 2.0         # the release read up to this long after note-off


def measure(chs, sr, hold):
    """(sustain dB, release s, total s) re the loudest WIN, or None if silent."""
    p = sum(kweight(c, sr) ** 2 for c in chs)
    if p.max() <= 0:
        return None
    n = int(WIN * sr)
    c = np.concatenate(([0.0], np.cumsum(p)))
    w = (c[n:] - c[:-n]) / n
    i_pk = int(np.argmax(w))
    peak = w[i_pk]
    # the onset: the first sample within 60 dB of the loudest window
    on = int(np.flatnonzero(p > peak * 1e-6)[0])
    off = on + int(hold * sr)
    end = min(len(p), off + int(AFTER * sr))
    s0 = i_pk + n
    sus = 10 * np.log10(p[s0:off].mean() / peak + 1e-30) if off > s0 + n else float('nan')
    rel = p[off:end].sum() / sr / peak if end > off else 0.0
    tot = p[on:end].sum() / sr / peak
    return sus, rel, tot


def gu(jobs, vel, d):
    sf = gu_path()
    cfg = os.path.join(d, "g.cfg")
    with open(cfg, "w") as f:
        f.write("bank 0\n")
        for key, _, _ in jobs:
            if key[0] != "kit":
                f.write('%d %%font "%s" 0 %d\n' % (key[0], sf, key[0]))
        f.write("drumset 0\n")
        for n in range(27, 88):
            f.write('%d %%font "%s" 128 0 %d\n' % (n, sf, n))
    out = {}
    for key, make, args in jobs:
        mid, wav = os.path.join(d, "g.mid"), os.path.join(d, "g.wav")
        make(*args, vel, mid)
        subprocess.run(["timidity", "-c", cfg, "-Ow", "-o", wav, "-s", "44100",
                        "-EFreverb=d", "-EFchorus=d", "--quiet=2", mid],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        a, sr = read(wav)
        out[key] = measure([a[:, i] for i in range(a.shape[1])], sr,
                           DRUM_HOLD if key[0] == "kit" else HOLD)
    return out


def ours(jobs, vel, d):
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    import blockrender as B
    out = {}
    for key, make, args in jobs:
        mid = os.path.join(d, "o.mid")
        make(*args, vel, mid)
        L, R = B.render(mido.MidiFile(mid))[:2]
        out[key] = measure([np.asarray(L, np.float64), np.asarray(R, np.float64)], B.SR,
                           DRUM_HOLD if key[0] == "kit" else HOLD)
    return out


def main(argv):
    vel = next((int(a.split("=")[1]) for a in argv if a.startswith("--vel=")), 100)
    progs = ALL
    for a in argv:
        if a.startswith("--progs="):
            want = {int(x) for x in a.split("=")[1].split(",")}
            progs = tuple(pk for pk in ALL if pk[0] in want)
    out_path = next((a.split("=", 1)[1] for a in argv if a.startswith("--out=")), None)
    jobs = [((p, k), note_mid, (p, k)) for p, k in progs] + \
           [(("kit", n), drum_mid, (n,)) for n in KIT]
    with tempfile.TemporaryDirectory() as d:
        g = gu(jobs, vel, d)
        o = ours(jobs, vel, d)
    rows = []
    for key, _, _ in jobs:
        if g.get(key) is None or o.get(key) is None:
            continue
        name = ("kit %d" % key[1]) if key[0] == "kit" else "%3d %s" % (key[0], NAMES[key[0]])
        d_tot = 10 * np.log10(o[key][2] / g[key][2])
        rows.append((d_tot, name, o[key], g[key]))
    rows.sort(key=lambda r: -r[0])
    hdr = "%-34s %18s %18s %18s %8s" % ("program", "sustain dB o / gu", "release s o / gu",
                                        "total s o / gu", "d total")
    lines = [hdr]
    for d_tot, name, oo, gg in rows:
        lines.append("%-34s %8.1f / %7.1f %8.2f / %7.2f %8.2f / %7.2f %+7.1f dB"
                     % (name[:34], oo[0], gg[0], oo[1], gg[1], oo[2], gg[2], d_tot))
    d = np.array([r[0] for r in rows])
    lines.append("\n%d notes at velocity %d: total energy ours re GU, median %+.1f dB, "
                 "mean %+.1f dB; %d over +3 dB, %d over +6 dB"
                 % (len(d), vel, np.median(d), d.mean(), (d > 3).sum(), (d > 6).sum()))
    print("\n".join(lines))
    if out_path:
        with open(out_path, "w") as f:
            f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
