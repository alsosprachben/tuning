#!/usr/bin/env python3
"""A built set's balance WITHIN itself, as GeneralUser GS has it.

    python3 -I examples/elkit_balance.py [--kit=0|8|16|24|25|40|48|56] [--write]

The snare stays where examples/drumset_check.py put it (on the Standard
snare); every other Electronic note takes the K-weighted level GeneralUser GS
gives it against ITS snare -- the loudest 150 ms, as drumset_check reads.
Balancing each note to the Standard note on its key had left the kick 1.9 dB
and the toms ~5 dB under the snare where GeneralUser's sit (Ben: "Our kick
seems quieter"). --write scales percussion_map.KIT_LEVEL[kit] by the misses.

THE TR-808 (--kit=25) the same way. Michael Fischer's recordings cannot
balance it: every hit peaks within -2.4 to -5 dBFS, each recorded or
normalized to its own level, so they hold the voices' shapes and not the
machine's mix.
"""
import os
import re
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
import elkit_fit as E                       # noqa: E402
from kit_levels import kweight              # noqa: E402

GU = os.path.expanduser("~/Documents/refs/soundfonts/GeneralUser-GS.sf2")
NOTES = {0: (27, 28, 29, 30, 31, 32, 33, 34),     # Standard's GS eight (PERCUSSION_LEVEL)
         24: (36, 40, 41, 43, 45, 47, 48, 50),
         25: (36, 37, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 56, 62, 63, 64, 70, 75),
         48: (27, 28, 29, 30, 35, 36, 39, 40) + tuple(range(41, 54)) + (57, 59, 88),
         40: (39, 40),
         8: (41, 43, 45, 47, 48, 50),
         16: (36, 41, 43, 45, 47, 48, 50),
         56: (47, 58, 70, 72, 78, 82, 79, 80, 81, 83, 84, 63, 66, 68, 69, 64, 65, 67, 71,
             39, 40, 41, 42, 43, 44, 45, 46, 48, 49, 50, 51, 59, 60, 61, 62, 73, 74, 75,
             52, 53, 54, 55, 56, 57, 76, 77),
         # the CM-64/32L set (percussion_map._cm32l): every key it sounds
         127: (35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 54, 56)
              + tuple(range(60, 74)) + (75,) + tuple(range(76, 109))}
ANCHOR_STANDARD = {56}
# A KEY GENERALUSER RENDERS SILENT (timidity plays the SFX set's train as
# nothing, -94 dBFS; the starship as a 4409 Hz whine, its noise once and
# under its own attack, -48.8 dB): levelled to a stand-in key of its kind
# instead -- the train and the starship to the jet, each a vehicle's held roar
# ...and the gallop, which GeneralUser GS means as a loop swelling in over 5
# s (its zone's attack 2786 timecents) 20 dB down -- a held note's design, its
# first 2 s 34 dB under the snare: levelled to the footsteps, a step on hard
# ground
# ...as in its CM-64/32L kit, the same three (92, 95, 101)
STAND_IN = {56: {68: 69, 71: 69, 77: 56}, 127: {92: 93, 95: 93, 101: 80}}


def k150(x, sr):
    x = kweight(np.asarray(x, float), sr)
    n, hop = int(0.15 * sr), int(0.01 * sr)
    return 20 * np.log10(max(np.sqrt(np.mean(x[i:i + n] ** 2))
                             for i in range(0, max(1, min(len(x), 2 * sr) - n), hop)) + 1e-12)


def main(argv):
    import percussion_map as P
    kit = int(next((a.split("=")[1] for a in argv if a.startswith("--kit=")), 24))
    E.KIT = kit
    miss = {}
    with tempfile.TemporaryDirectory() as d:
        if kit in ANCHOR_STANDARD:
            # a set with no snare of its own (SFX): its keys against Standard's
            E.KIT = 0
        g38, o38 = k150(*E.theirs(GU, 38, d)), k150(*E.ours(38, d))
        E.KIT = kit
        for n in NOTES[kit]:
            g, o = k150(*E.theirs(GU, STAND_IN.get(kit, {}).get(n, n), d)) - g38, k150(*E.ours(n, d)) - o38
            miss[n] = g - o
            print("  %d %-16s GeneralUser %+5.1f  ours %+5.1f  (re the snare, K)  -> %+.1f dB"
                  % (n, (P.KITS[kit] if kit else P.PERCUSSION)[n][0], g, o, miss[n]))
    if "--write" in argv and kit == 0:
        # STANDARD's levels are PERCUSSION_LEVEL's: each note's trim set (or
        # added after the table's opening comment), its old value carried
        p = os.path.join(HERE, "percussion_map.py")
        s = open(p).read()
        base = s.index("PERCUSSION_LEVEL = {")
        for n, dv in miss.items():
            cur = P.PERCUSSION_LEVEL.get(n, 1.0) * 10 ** (dv / 20.0)
            m = re.search(r"\n    %d: [0-9.]+," % n, s[base:])
            line = "\n    %d: %.4f," % (n, cur)
            if m:
                s = s[:base + m.start()] + line + s[base + m.end():]
            else:
                k = s.index("\n    73: 5.0, 74: 5.0,", base)
                s = s[:k] + line + "  # GS's %d, balanced to GeneralUser GS (examples/elkit_balance.py --kit=0)" % n + s[k:]
            print("  PERCUSSION_LEVEL[%d] = %.4f" % (n, cur))
        open(p, "w").write(s)
        return 0
    if "--write" in argv:
        p = os.path.join(HERE, "percussion_map.py")
        s = open(p).read()
        m = re.search(r"(\{|\n             )%d: \{([^}]*)\}" % kit, s[s.index("KIT_LEVEL = "):])
        base = s.index("KIT_LEVEL = ")
        # from the levels the set plays at: a derived set's (the CM-64/32L,
        # percussion_map._cm32l) are its sources' under its own literal
        cur = dict(P.KIT_LEVEL.get(kit, {}))
        cur.update({int(a): float(b) for a, b in re.findall(r"(\d+): ([0-9.]+)", m.group(2))})
        for n, dv in miss.items():
            cur[n] = cur.get(n, 1.0) * 10 ** (dv / 20.0)
        new = "%s%d: {%s}" % (m.group(1), kit, ", ".join("%d: %.3f" % (n, cur[n]) for n in sorted(cur)))
        open(p, "w").write(s[:base + m.start()] + new + s[base + m.end():])
        print("  " + new.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
