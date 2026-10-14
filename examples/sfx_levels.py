#!/usr/bin/env python3
"""The sound effects' balance against other GM implementations: each
program's note played alone, its level re a piano C4 at the same velocity.

    python3 examples/sfx_levels.py [--vel=110] [--progs=127:55,126:60,... | --all] [SF2 ...]
    python3 examples/sfx_levels.py --trim     the bank to GeneralUser GS (writes patch_map.py)

Each SoundFont (examples/gm_release.py's four: FluidR3, GeneralUser GS,
MuseScore General, TimGM6mb) through timidity, reverb and chorus off; ours
rendered dry (no reflections, master -14 dB) as examples/kit_levels.py renders
the kit. Roland's own SC-55 is not on this machine; GeneralUser GS is voiced
after Roland's GS set and is the nearest witness. Two readings, both the
loudest 150 ms (crash_fit.level): plain power, and K-weighted (BS.1770, nearer
what the ear calls loud).
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

import crash_fit as C  # noqa: E402
from drum_fit import read  # noqa: E402
from gm_release import SETS  # noqa: E402
from kit_levels import levels  # noqa: E402

PROGS = ((127, 55), (126, 60), (125, 60), (124, 92), (123, 100), (121, 60), (122, 60))
REF = (0, 60)      # the piano's C4
# --all: every program at a key its instrument plays (C4 unless it lives
# elsewhere: the basses at E2, the high winds and bells up)
KEY_OF = {**{p: 40 for p in (32, 33, 34, 35, 36, 37, 38, 39, 43, 58, 87)},
          **{p: 48 for p in (42, 57, 67, 70, 116, 117, 118)},
          **{p: 72 for p in (8, 13, 73, 79, 112, 113)},
          **{p: 84 for p in (9, 10, 14, 72, 75, 78)},
          123: 100, 124: 92, 127: 55}
ALL = tuple((p, KEY_OF.get(p, 60)) for p in range(128))


def note_mid(prog, key, vel, path, secs=1.5):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=prog, time=0))
    # a quarter-second in: a note at a render's very start is a special case
    # in more than one renderer
    t.append(mido.Message("note_on", channel=0, note=key, velocity=vel, time=240))
    t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(secs * 960)))
    t.append(mido.MetaMessage("end_of_track", time=1920))
    m.save(path)


def sf_levels(sf, progs, vel, d):
    cfg = os.path.join(d, "t.cfg")
    # every program this reads mapped to this font explicitly: timidity's
    # system config maps FluidR3 program by program, and -c only adds to it
    with open(cfg, "w") as f:
        f.write("bank 0\n")
        for p in sorted({p for p, _ in progs} | {REF[0]}):
            f.write('%d %%font "%s" 0 %d\n' % (p, sf, p))
    out = {}
    for p, k in tuple(progs) + (REF,):
        mid, wav = os.path.join(d, "n.mid"), os.path.join(d, "n.wav")
        note_mid(p, k, vel, mid)
        subprocess.run(["timidity", "-c", cfg, "-Ow", "-o", wav, "-s", "44100",
                        "-EFreverb=d", "-EFchorus=d", "--quiet=2", mid],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        a, sr = read(wav)
        a = a.astype(np.float64)
        out[(p, k)] = levels([a[:, 0], a[:, 1]] if a.ndim > 1 else [a], sr) if np.abs(a).max() > 0 else None
    return out


def ours(progs, vel, d):
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    import blockrender as B
    out = {}
    for p, k in tuple(progs) + (REF,):
        mid = os.path.join(d, "o.mid")
        note_mid(p, k, vel, mid)
        L, R = B.render(mido.MidiFile(mid))[:2]
        out[(p, k)] = levels([np.asarray(L, np.float64), np.asarray(R, np.float64)], B.SR)
    return out


KIT = (35, 36, 38, 42, 49)        # the kit's core: kicks, snare, hi-hat, crash


def drum_mid(note, vel, path):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("note_on", channel=9, note=note, velocity=vel, time=240))
    t.append(mido.Message("note_off", channel=9, note=note, velocity=0, time=120))
    t.append(mido.MetaMessage("end_of_track", time=2880))
    m.save(path)


def gu_path():
    return next(p for n, p in SETS if n.startswith("GeneralUser"))


def gu_levels(progs, vel, d):
    """GeneralUser GS: each program, the piano reference, and the kit's core
    notes, K level (dB)."""
    sf = gu_path()
    cfg = os.path.join(d, "g.cfg")
    with open(cfg, "w") as f:
        f.write("bank 0\n")
        for p in sorted({p for p, _ in progs} | {REF[0]}):
            f.write('%d %%font "%s" 0 %d\n' % (p, sf, p))
        f.write("drumset 0\n")
        for n in range(27, 88):
            f.write('%d %%font "%s" 128 0 %d\n' % (n, sf, n))
    out = {}
    jobs = [((p, k), note_mid, (p, k)) for p, k in tuple(progs) + (REF,)] + \
           [(("kit", n), drum_mid, (n,)) for n in KIT]
    for key, make, args in jobs:
        mid, wav = os.path.join(d, "g.mid"), os.path.join(d, "g.wav")
        make(*args, vel, mid)
        subprocess.run(["timidity", "-c", cfg, "-Ow", "-o", wav, "-s", "44100",
                        "-EFreverb=d", "-EFchorus=d", "--quiet=2", mid],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        a, sr = read(wav)
        a = a.astype(np.float64)
        out[key] = levels([a[:, 0], a[:, 1]] if a.ndim > 1 else [a], sr)[1] if np.abs(a).max() > 0 else None
    return out


def our_levels(progs, vel, d):
    """Ours, the same notes, rendered dry (K level, dB)."""
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    import blockrender as B
    out = {}
    jobs = [((p, k), note_mid, (p, k)) for p, k in tuple(progs) + (REF,)] + \
           [(("kit", n), drum_mid, (n,)) for n in KIT]
    for key, make, args in jobs:
        mid = os.path.join(d, "o.mid")
        make(*args, vel, mid)
        L, R = B.render(mido.MidiFile(mid))[:2]
        out[key] = levels([np.asarray(L, np.float64), np.asarray(R, np.float64)], B.SR)[1]
    return out


def trim(progs, vels=(64, 100), passes=2):
    """PROGRAM_TRIM_DB and KIT_TRIM_DB to GeneralUser GS (Ben: "take one
    sample at 64 and another at 100, and average the two differences"): each
    program's K level re a piano C4 at both velocities, GU's less ours,
    averaged; the kit's the median over its core notes. A second pass reads
    ours again through the trims (an amplifier's drive is not linear in
    gain). Written into patch_map.py."""
    import re
    import patch_map as PM
    with tempfile.TemporaryDirectory() as d:
        gu = {v: gu_levels(progs, v, d) for v in vels}
        for it in range(passes + 1):
            ours_ = {v: our_levels(progs, v, d) for v in vels}
            diff = {}
            for key in [(p, k) for p, k in progs] + [("kit", n) for n in KIT]:
                ds = []
                for v in vels:
                    g, o, gr, orf = gu[v].get(key), ours_[v].get(key), gu[v][REF], ours_[v][REF]
                    if g is not None and o is not None and np.isfinite(g) and np.isfinite(o) and o > -200:
                        ds.append((g - gr) - (o - orf))
                if ds:
                    diff[key] = float(np.mean(ds))
            prog_d = {p: diff[(p, k)] for p, k in progs if (p, k) in diff and p != REF[0]}
            kit_d = float(np.median([diff[("kit", n)] for n in KIT if ("kit", n) in diff]))
            rms = float(np.sqrt(np.mean(np.square(list(prog_d.values())))))
            print("  pass %d: programs off GU by %.1f dB rms (worst %s), the kit by %+.1f" % (
                it, rms, ", ".join("%d %+.1f" % kv for kv in sorted(prog_d.items(), key=lambda kv: -abs(kv[1]))[:5]),
                kit_d), flush=True)
            if it == passes:
                break
            for p, dd in prog_d.items():
                PM.PROGRAM_TRIM_DB[p] = round(PM.PROGRAM_TRIM_DB.get(p, 0.0) + dd, 1)
            PM.KIT_TRIM_DB = round(PM.KIT_TRIM_DB + kit_d, 1)
    path = os.path.join(HERE, "patch_map.py")
    src = open(path).read()
    tab = "{" + ", ".join("%d: %.1f" % (p, PM.PROGRAM_TRIM_DB[p]) for p in sorted(PM.PROGRAM_TRIM_DB)) + "}"
    src = re.sub(r"^PROGRAM_TRIM_DB = .*$", lambda _: "PROGRAM_TRIM_DB = " + tab, src, count=1, flags=re.M)
    src = re.sub(r"^KIT_TRIM_DB = .*$", lambda _: "KIT_TRIM_DB = %.1f" % PM.KIT_TRIM_DB, src, count=1, flags=re.M)
    open(path, "w").write(src)
    print("  written: %d program trims, kit %+.1f dB" % (len(PM.PROGRAM_TRIM_DB), PM.KIT_TRIM_DB))


def main(argv):
    if "--trim" in argv:
        trim(ALL)
        return 0
    vel = int(next((a.split("=")[1] for a in argv if a.startswith("--vel=")), 110))
    progs = next((tuple(tuple(int(v) for v in x.split(":")) for x in a.split("=")[1].split(","))
                  for a in argv if a.startswith("--progs=")), ALL if "--all" in argv else PROGS)
    sfs = [a for a in argv[1:] if not a.startswith("--")] or [p for _, p in SETS if p and os.path.exists(p)]
    with tempfile.TemporaryDirectory() as d:
        cols = [("ours", ours(progs, vel, d))]
        for sf in sfs:
            cols.append((os.path.basename(sf).split(".")[0][:14], sf_levels(sf, progs, vel, d)))
    for k, kind in ((0, "rms"), (1, "K")):
        print("\n== velocity %d, %s level re a piano C4, dB" % (vel, kind))
        print("  prog key " + "".join("%15s" % c for c, _ in cols))
        for p, key in progs:
            row = []
            for _, lv in cols:
                v, r = lv.get((p, key)), lv.get(REF)
                row.append("%15s" % ("%+.1f" % (v[k] - r[k]) if v and r else "--"))
            print("  %4d %3d " % (p, key) + "".join(row))
    # ...AND RANKED: ours less GeneralUser GS (K), the most unbalanced first,
    # with the four sets' median beside it
    gu = next((lv for c, lv in cols if c.startswith("GeneralUser")), None)
    if gu:
        import patch_map as PM
        rows = []
        for p, key in progs:
            o, g, r, rg = cols[0][1].get((p, key)), gu.get((p, key)), cols[0][1].get(REF), gu.get(REF)
            if not (o and g and r and rg):
                continue
            others = [lv.get((p, key)) for _, lv in cols[1:]]
            refs = [lv.get(REF) for _, lv in cols[1:]]
            med = float(np.median([v[1] - q[1] for v, q in zip(others, refs) if v and q]))
            rows.append((o[1] - r[1] - (g[1] - rg[1]), p, key, o[1] - r[1], g[1] - rg[1], med))
        print("\n== ours less GeneralUser GS, K, re a piano C4 at velocity %d: the most unbalanced first" % vel)
        print("  %5s  prog key %-22s %7s %7s %7s" % ("off", "", "ours", "GU GS", "median"))
        for d, p, key, o, g, med in sorted(rows, key=lambda r: -abs(r[0])):
            print("  %+5.1f  %4d %3d %-22s %+7.1f %+7.1f %+7.1f" % (
                d, p, key, PM.property_class_for_program(p).__name__.replace("Properties", "")[:22], o, g, med))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
