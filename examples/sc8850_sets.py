#!/usr/bin/env python3
"""Write percussion_sc8850.py: the SC-8850 map's own drum sets (CC32 = 4), from
its owner's manual's drum set lists (examples/gs_drumsets.py parse, cleaned to
~/Documents/refs/roland/sc8850_drumsets.tsv: keys 22-96, the "[ Pro ]" tag a
column of its own).

    python3 -I examples/sc8850_sets.py              what each set needs, and the names with no voice
    python3 -I examples/sc8850_sets.py --write      ...into percussion_sc8850.py

THE SC-8850's VERSIONS ARE OURS (Ben: its revisions add specificity, the
role of each key kept, so one set per program -- the SC-8850's -- whatever map
a file names). A set it shares with the SC-88 Pro ("[ Pro ]" on its header)
needs nothing here. A set it REVISED extends the native kit (program - 1,
SET_EXTEND): its keys that differ from the SC-88 Pro's same set, a renaming no
difference. A program it ADDED is a native kit of its own: standing alone
(ALONE), on its parent set (PARENT: an L/R set on its set), or on Standard.
Its names as Roland prints them, read for our voices: a "[Pro]", "[88]" or
"[55]" before a name is that model's same sound (our voice of that name);
"[RND]" the voice each strike varied, as Standard 3's; the SC-8850's renamings
of what we have through ALIAS; and a set's own reading of a name through
SET_VOICE (the Techno set's machine drums, driven). A name with no voice yet
is listed and left out (percussion_gs's rule): the set's own drum stays, or
Standard's, or silence where it stands alone.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
TSV = os.path.expanduser("~/Documents/refs/roland/sc8850_drumsets.tsv")

# sets that stand ALONE (their blanks no sound): the SC-8850's own lists show
# no "<-" in them
ALONE = {52, 55, 56, 60, 61, 62, 63}

# THE SC-8850's RENAMINGS of what we have: its name -> ours (percussion_gs.VOICE)
ALIAS = {
    'Closed Hi-Hat 1': 'Closed Hi-Hat', 'Open Hi-Hat 1': 'Open Hi-Hat', 'Shimetaiko': 'Shimedaiko',
    'Stantard 1 Snare 1': 'Standard 1 Snare 1', 'Frog Vpoce': 'Frog Voice', 'Reverse bounce': 'Reverse Bounce',
    'Saw LFO': 'Saw LFO Saw', 'Yyooh Dude': 'Yyoo Dude', 'Reverse Yyooh': 'Reverse Yyoo Dude',
    'TR-808 Kick': 'TR-808 Kick 1', 'Dance Snare': 'Dance Snare 1',
}


# ADDED SETS ON A PARENT (the L/R sets on their set): program -> parent's program
PARENT = {13: 9, 34: 33, 42: 41, 43: 41}

# A SET'S OWN READING of a name: (program, key) -> our VOICE name. The Techno
# set: the SC-88 Pro's had Techno (distorted) drums on 35, 36, 38 and 40; the
# SC-8850 names the machines -- so those machines through our valve (Ben)
SET_VOICE = {(12, 35): 'Techno TR-808 Kick', (12, 36): 'Techno Kick 1', (12, 38): 'Techno TR-606 Snare 2'}

# NOT YET: Standard 1's (its kit the built-in default; its only change the
# Room Snares on 95/96, not built)
SKIP = {1}


def norm(name):
    """(our VOICE name, spec kind override or None) for a name as printed."""
    n = re.sub(r"^\[(Pro|88|55)\]\s*", "", name).strip()
    rnd = n.startswith("[RND] ")
    n = n[6:] if rnd else n
    n = ALIAS.get(n, n)
    return n, rnd


def read():
    sets = {}
    for line in open(TSV).read().strip().split("\n")[1:]:
        pc, sn, key, name, flags, pro = line.split("\t")
        sets.setdefault(int(pc), [sn, pro == "1", {}])[2][int(key)] = name
    return sets


PRO_TSV = os.path.expanduser("~/Documents/refs/roland/sc88pro_drumsets.tsv")
SAME = ("<\u2013", "<-", "\u2190")


def pro_sets():
    out = {}
    for line in open(PRO_TSV).read().split("\n")[1:]:
        f = line.split("\t")
        if len(f) >= 5 and f[0] == "native":
            out.setdefault(int(f[1]), {})[int(f[3])] = f[4]
    return out


def plan():
    """{pc: (name, {key: (our name, RND spec or None)})}: each set's keys where
    the SC-8850 differs -- from the SC-88 Pro's same set where it has one (a
    renaming no difference), else from the SC-8850's Standard 1."""
    import percussion_gs as G
    sets = read()
    pro = pro_sets()
    std = sets[1][2]
    out, missing = {}, {}
    for pc, (sn, tagged, ks) in sorted(sets.items()):
        if tagged or pc in SKIP:
            continue
        old = pro.get(pc)
        own = {}
        for key, name in sorted(ks.items()):
            if old is not None:
                o = old.get(key, "---")
                if name in SAME and o in SAME:
                    continue
                if norm(name)[0].replace(" ", "").lower() == norm(o)[0].replace(" ", "").lower():
                    continue
            if name in SAME:
                if pc in ALONE:
                    own[key] = std.get(key, "---")
                continue
            own[key] = name
        if not own:
            continue
        rows = {}
        for key, name in own.items():
            if name in ("---", ""):
                rows[key] = ("---", None)
                continue
            n, rnd = norm(name)
            n = SET_VOICE.get((pc, key), n)
            spec = G.VOICE.get(n)
            if spec is None:
                missing.setdefault(name, []).append((pc, key))
            # [RND]: a kit's voice ('n', set, key) or a class ('nc', class, Hz), each strike varied
            r = None
            if rnd and spec and spec[0] in ("k", "c"):
                r = ("n" if spec[0] == "k" else "nc",) + tuple(spec[1:3])
            rows[key] = (n, r)
        if old is not None:
            rows = {k: v for k, v in rows.items() if v[0] != norm(old.get(k, "---"))[0]}
        if rows:
            out[pc] = (sn, rows)
    return out, missing


def write(out):
    L = ['"""THE SC-8850\'S DRUM SETS, OURS: written by examples/sc8850_sets.py from the',
         'SC-8850 owner\'s manual\'s drum set lists -- do not edit by hand. A set it',
         'revised extends the native kit (program - 1: SET_EXTEND, its keys that differ',
         'from the SC-88 Pro\'s); a set it added is a native kit of its own, alone',
         '(SET_ALONE), on its parent (SET_BASE) or on Standard. "---" silences a key',
         '(SET_SILENCE). Read in by percussion_gs. RND: a name the SC-8850 marks [RND],',
         'our voice each strike varied."""',
         '', 'SETS = {']
    pro = pro_sets()
    rnd = {}
    for pc, (sn, rows) in out.items():
        L.append("    ('sc8850', %d): {  # %s" % (pc, sn))
        items = ["%d: %r" % (k, ("[RND] " + n) if r else n) for k, (n, r) in sorted(rows.items())]
        line = "       "
        for it in items:
            if len(line) + len(it) + 2 > 100:
                L.append(line)
                line = "       "
            line += " " + it + ","
        L.append(line)
        L.append("    },")
        for k, (n, r) in rows.items():
            if r:
                rnd["[RND] " + n] = r
    L.append("}")
    L.append("SET_KIT = {%s}" % ", ".join("('sc8850', %d): %d" % (pc, pc - 1) for pc in out))
    L.append("SET_NAME = {%s}" % ", ".join("%d: %r" % (pc - 1, sn.title()) for pc, (sn, _r) in out.items()
                                           if pc not in pro))
    L.append("SET_ALONE = {%s}" % ", ".join(str(pc - 1) for pc in out if pc in ALONE))
    L.append("SET_EXTEND = {%s}" % ", ".join(str(pc - 1) for pc in out if pc in pro))
    L.append("SET_BASE = {%s}" % ", ".join("%d: %d" % (pc - 1, PARENT[pc] - 1) for pc in out if pc in PARENT))
    L.append("SET_SILENCE = {%s}" % ", ".join(str(pc - 1) for pc in out))
    L.append("RND = %r" % (rnd,))
    open(os.path.join(HERE, "percussion_sc8850.py"), "w").write("\n".join(L) + "\n")


def main(argv):
    out, missing = plan()
    for pc, (sn, rows) in out.items():
        print("  PC%-3d %-15s %2d keys of its own" % (pc, sn, len(rows)))
    print("  %d names with no voice yet" % len(missing))
    if "--names" in argv:
        for n, w in sorted(missing.items()):
            print("    %-36s %s" % (n, " ".join("%d/%d" % x for x in w[:4])))
    if "--write" in argv:
        write(out)
        print("  wrote percussion_sc8850.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
