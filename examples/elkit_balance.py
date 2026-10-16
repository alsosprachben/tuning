#!/usr/bin/env python3
"""A built set's balance WITHIN itself, as GeneralUser GS has it.

    python3 -I examples/elkit_balance.py [--kit=24|25|40|48] [--write]

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
NOTES = {24: (36, 40, 41, 43, 45, 47, 48, 50),
         25: (36, 37, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 56, 62, 63, 64, 70, 75),
         48: (27, 28, 29, 30, 35, 36, 39, 40) + tuple(range(41, 54)) + (57, 59, 88),
         40: (39, 40)}


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
        g38, o38 = k150(*E.theirs(GU, 38, d)), k150(*E.ours(38, d))
        for n in NOTES[kit]:
            g, o = k150(*E.theirs(GU, n, d)) - g38, k150(*E.ours(n, d)) - o38
            miss[n] = g - o
            print("  %d %-16s GeneralUser %+5.1f  ours %+5.1f  (re the snare, K)  -> %+.1f dB"
                  % (n, P.KITS[kit][n][0], g, o, miss[n]))
    if "--write" in argv:
        p = os.path.join(HERE, "percussion_map.py")
        s = open(p).read()
        m = re.search(r"(\{|\n             )%d: \{([^}]*)\}" % kit, s[s.index("KIT_LEVEL = "):])
        base = s.index("KIT_LEVEL = ")
        cur = {int(a): float(b) for a, b in re.findall(r"(\d+): ([0-9.]+)", m.group(2))}
        for n, dv in miss.items():
            cur[n] = cur.get(n, 1.0) * 10 ** (dv / 20.0)
        new = "%s%d: {%s}" % (m.group(1), kit, ", ".join("%d: %.3f" % (n, cur[n]) for n in sorted(cur)))
        open(p, "w").write(s[:base + m.start()] + new + s[base + m.end():])
        print("  " + new.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
