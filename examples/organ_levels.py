#!/usr/bin/env python3
"""EACH RANK'S LEVEL ACROSS THE KEYBOARD, FROM THE SIMULATED PIPE (Ben
2026-11-25: "use simulated physics"). The bake (examples/organ_bake.py) wrote
each class's harmonic tables with the fundamental at 1 on every key and one
level a rank, held over C3-C5; nothing set the level from bass to treble but
that, and the bass reeds and the Bourdon lost what the Piteå tables had
carried. Here each rank's pipe is simulated over its compass at its own
sounding pitch (fluepipe_sim's harmonic balance for the flues,
reedpipe_sim's tongue for the reeds) and its radiated power read key by key.

    python3 examples/organ_levels.py --simulate [CLASS ...]   solve, cache, print
    python3 examples/organ_levels.py --show [CLASS ...]       the cached levels against the tables'
    python3 examples/organ_levels.py --write [CLASS ...]      each class's tables carrying its level (tonelib)

A STEP OF THE ORGAN'S BUILD (examples/organ_build.py: bake, wind, levels,
regulate). The write starts from the bake's bare tables (examples/
organ_bare_tables.json) every time, so it can be rerun; it folds in the voicer's
regulation (examples/organ_regulation.json) where there is one. A rank's
level is held where its balance was set by ear: the manuals' C3-C5, the
Pedal's own compass (PEDAL_LEVEL_KEYS).

Levels are the simulator's own dB (alike for every stop on its wind), at
written C1-C7 times the rank's ratio; a pipe too small to speak in the jet
model holds the highest that does, and below 16 Hz the lowest simulated.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]

import organ_bake as OB  # noqa: E402

WRITTEN = (24, 36, 48, 60, 72, 84, 96)      # C1..C7, the keys the levels are read at
LOWEST_HZ = 16.0                            # under it the lowest simulated pipe's level holds


def _ratio(rank):
    import tonelib as T
    r = next(r[1] for r in T.FlueOrganProperties.stop_ranks if r[0] == rank)
    return r


def pitches(name):
    """The rank's sounding pitches at WRITTEN (Hz), those under LOWEST_HZ dropped."""
    rank = OB.CLASSES[name][1]
    return [f for f in (261.63 * _ratio(rank) * 2 ** ((k - 60) / 12.0) for k in WRITTEN) if f >= LOWEST_HZ]


def simulate(name, cache):
    """{Hz: radiated dB} over the rank's compass, from the cache where its
    stop and the simulator's constants are unchanged."""
    import fluepipe_sim as F
    stop = OB.CLASSES[name][0]
    k = "K|" + OB._key(F, stop) + name + json.dumps(WRITTEN)
    if k in cache:
        return {float(a): b for a, b in cache[k].items()}
    fs = pitches(name)
    out = {}
    if stop.startswith("reed:"):
        import reedpipe_sim as R
        last = None
        for f in fs:
            lvl = R.tuned_tone(stop[5:], f, secs=0.8)[2]
            if lvl < -100:              # past the highest that speaks: its level holds
                lvl = last
            if lvl is not None:
                out[f] = float(lvl)
                last = lvl
            print("    %s %.1f Hz: %s" % (name, f, "%.1f dB" % lvl if lvl is not None else "silent"), flush=True)
    else:
        start = min(fs, key=lambda f: abs(math.log(f / 250.0)))
        tab = OB._sweep(F, stop, min(fs) * 0.97, max(fs) * 1.03, start)
        top = max(tab)
        for f in fs:
            out[f] = float(F.at(tab, min(f, top))[2])
            print("    %s %.1f Hz: %.1f dB%s" % (name, f, out[f], " (the top's)" if f > top * 1.03 else ""),
                  flush=True)
    cache[k] = {str(a): b for a, b in out.items()}
    with open(OB.CACHE, "w") as fh:
        json.dump(cache, fh)
    return out


def table_db(cls, f):
    """The class's harmonic table at f as the renderer blends it: its power, dB."""
    g = np.asarray(cls.mode_gains_at(cls, f) if isinstance(cls, type) else cls.mode_gains_at(f), float)
    return 10 * math.log10(float(np.sum(g * g)) + 1e-30)


MAX_ANCHORS = 8                 # the native voice's tables (nv.h pts_hz[8])
# THE TABLES AS THE BAKE LEFT THEM, before their levels (organ_bare_tables.json):
# each write starts from these (a write over levelled tables would drift)
# WHERE A RANK'S LEVEL IS HELD: where its balance was set by ear -- the
# manuals' C3-C5 (organ_bake.LEVEL_KEYS); the Pedal's own compass, C2-C3 (Ben:
# held at C3-C5 its bottom rose +5..12 dB, "a large bias around the bottom of the 16'")
PEDAL_LEVEL_KEYS = (36, 43, 48)
_BASE = {}


BARE = os.path.join(HERE, "organ_bare_tables.json")


def base_points(name):
    """The class's mode_gains_points as the bake wrote them, bare (examples/
    organ_bare_tables.json, which organ_bake.py --write keeps)."""
    if "bare" not in _BASE:
        _BASE["bare"] = json.load(open(BARE))
    return tuple((a, tuple(g)) for a, g in _BASE["bare"][name])


def level_keys(name):
    """The written keys a rank's level is held at."""
    import tonelib as T
    rank = OB.CLASSES[name][1]
    pc = T.FlueOrganProperties
    ped = (getattr(pc, 'divisions', None) or ("",))
    d = T.rank_division(pc, rank)
    return PEDAL_LEVEL_KEYS if d < len(ped) and ped[d] == "Pedal" else OB.LEVEL_KEYS
HELD = ("OrganVoxHumanaProperties",)    # its level by ear (the sim's is not credible): its tables as they are


def _interp_db(lv, f):
    """The simulated levels at f: linear in dB along log frequency, held past the ends."""
    fs = sorted(lv)
    if f <= fs[0]:
        return lv[fs[0]]
    if f >= fs[-1]:
        return lv[fs[-1]]
    for a, b in zip(fs, fs[1:]):
        if f <= b:
            w = math.log(f / a) / math.log(b / a)
            return lv[a] + w * (lv[b] - lv[a])


def anchors(old, cand):
    """The class's anchor pitches: its own (the tone as Ben approved it), the
    compass's ends, then the widest gaps filled from the candidates, to MAX_ANCHORS."""
    out = sorted(old)
    for f in (min(cand), max(cand)):
        if all(abs(math.log2(f / a)) > 1 / 3.0 for a in out) and len(out) < MAX_ANCHORS:
            out = sorted(out + [f])
    while len(out) < MAX_ANCHORS:
        gaps = sorted(((math.log2(b / a), a, b) for a, b in zip(out, out[1:])), reverse=True)
        w, a, b = gaps[0]
        if w <= 1.0:
            break
        mid = math.sqrt(a * b)
        f = min(cand, key=lambda c: abs(math.log(c / mid)))
        if not a < f < b or min(math.log2(f / a), math.log2(b / f)) < 1 / 3.0:
            f = mid
        out = sorted(out + [round(f, 1)])
    return out


def leveled_points(name, cache):
    """The class's mode_gains_points with each anchor's table carrying the
    simulated level there (its tone, the table the renderer had at that pitch),
    re its own where its balance was set by ear (level_keys), kept."""
    import tonelib as T
    cls = getattr(T, name)
    keep = cls.__dict__.get('mode_gains_points')
    cls.mode_gains_points = base_points(name)          # (the tone, unlevelled)
    try:
        inst = cls(261.63, 0, 1, 1)
        lv = simulate(name, cache)
        rat = _ratio(OB.CLASSES[name][1])
        rat = rat if not isinstance(rat, (list, tuple)) else 1.0
        delta = lambda f: _interp_db(lv, f) - table_db(inst, f)
        ref = float(np.mean([delta(261.63 * rat * 2 ** ((k - 60) / 12.0)) for k in level_keys(name)]))
        # ...AND THE VOICER'S REGULATION over it (examples/organ_regulate.py)
        reg = regulation().get(name)
        rg = {float(a): b for a, b in reg} if reg else None
        pts = []
        for a in anchors([a for a, _ in cls.mode_gains_points], list(lv)):
            g = inst.mode_gains_at(a)
            s = 10 ** ((delta(a) - ref + (_interp_db(rg, a) if rg else 0.0)) / 20.0)
            pts.append([a, [round(x * s, 7) for x in g]])
            print("    %s %.1f Hz: %+.1f dB" % (name, a, 20 * math.log10(s)), flush=True)
    finally:
        cls.mode_gains_points = keep
    return pts


REG = os.path.join(HERE, "organ_regulation.json")


def regulation():
    """{class: [[rank Hz, dB], ...]} the voicer's regulation (organ_regulate.py), {} none."""
    return json.load(open(REG)) if os.path.exists(REG) else {}


def anchor_pitches(name, cache=None):
    """The class's anchor pitches as leveled_points places them (Hz)."""
    if cache is None:
        cache = json.load(open(OB.CACHE)) if os.path.exists(OB.CACHE) else {}
    return anchors([a for a, _ in base_points(name)], list(simulate(name, cache)))


def write_one(name, cache=None):
    """The class's levelled tables into the running tonelib (no file): what a
    render in this process now hears."""
    import tonelib as T
    if name in HELD:
        return
    if cache is None:
        cache = json.load(open(OB.CACHE)) if os.path.exists(OB.CACHE) else {}
    pts = tuple((a, tuple(g)) for a, g in leveled_points(name, cache))
    cls = getattr(T, name)
    cls.mode_gains_points, cls.mode_gains = pts, pts[-1][1]


def write(names, cache):
    import re
    path = os.path.join(ROOT, "tonelib.py")
    src = open(path).read()
    for n in names:
        if n in HELD:
            print("  %s: held (its level by ear)" % n)
            continue
        pts = leveled_points(n, cache)
        i = src.index("\nclass %s(" % n) + 1
        j = src.find("\nclass ", i + 1)
        j = len(src) if j < 0 else j
        body = src[i:j]
        marker = ("    # ...AND ITS LEVEL ACROSS THE KEYBOARD, SIMULATED (examples/organ_levels.py:\n"
                  "    # the pipe's radiated power key by key, re its own where its balance was set): each\n"
                  "    # anchor's table at its level there, the tone the table it had\n")
        body, k = re.subn(r"(?:    # \.\.\.AND ITS LEVEL ACROSS[^\n]*\n(?:    #[^\n]*\n)*)?    mode_gains_points = \(\n.*?\n    \)\n",
                          lambda _m: marker + fmt_points(pts) + "\n", body, count=1, flags=re.S)
        if k != 1:
            raise SystemExit("%s: no mode_gains_points of its own" % n)
        src = src[:i] + body + src[j:]
    open(path, "w").write(src)


def fmt_points(pts):
    """organ_bake._fmt_points, with the precision a scaled table needs."""
    lines = ["    mode_gains_points = ("]
    for a, g in pts:
        toks = ["%.6g" % x for x in g]
        chunks, cur = [], ""
        for tok in toks:
            if len(cur) + len(tok) + 2 > 86:
                chunks.append(cur)
                cur = tok
            else:
                cur = tok if not cur else cur + ", " + tok
        chunks.append(cur)
        if len(chunks) == 1:
            lines.append("        (%s, (%s,))," % (a, chunks[0]))
            continue
        lines.append("        (%s, (%s," % (a, chunks[0]))
        for c in chunks[1:-1]:
            lines.append("                  %s," % c)
        lines.append("                  %s))," % chunks[-1])
    lines.append("    )")
    return "\n".join(lines)


def main(argv):
    names = [a for a in argv[1:] if not a.startswith("--")] or list(OB.CLASSES)
    cache = json.load(open(OB.CACHE)) if os.path.exists(OB.CACHE) else {}
    if "--simulate" in argv:
        for n in names:
            print(n, flush=True)
            simulate(n, cache)
    if "--write" in argv:
        write(names, cache)
    if "--show" in argv:
        import tonelib as T
        for n in names:
            lv = simulate(n, cache)
            cls = getattr(T, n)
            inst = cls(261.63, 0, 1, 1)
            ref = np.mean([lv[f] - table_db(inst, f) for f in lv][2:5]) if len(lv) >= 5 else 0.0
            print("%-30s %s" % (n, "  ".join("%.0fHz %+.1f" % (f, lv[f] - table_db(inst, f) - ref)
                                          for f in sorted(lv))))


if __name__ == "__main__":
    main(sys.argv)
