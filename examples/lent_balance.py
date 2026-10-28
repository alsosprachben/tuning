#!/usr/bin/env python3
"""The keys one drum set lends another, balanced AT HOME to GeneralUser GS.

    python3 -I examples/lent_balance.py [--home=27,28] [--keys=0:86,40:42] [--write]

A set that borrows a key (percussion_gs: another set's voice on it) plays it at
its HOME set's level (percussion_map._build_gs_sets), so the home is where it is
set right, once, for every set that borrows it. The CR-78 set's levels were
never set -- its recordings each normalized to their own peak -- and its
tambourine stood 27 dB over its snare; the TR-808 set borrows it, and SHIRO's
tambourine came in 17 dB over GeneralUser's.

THE YARDSTICK IS THE STANDARD SNARE, not the set's own: the sets' snares sit
apart by 14 dB (Power +2.7, Brush -11.1, here as in GeneralUser), so a level
re the home set's snare means something else in each set that borrows it. So
a key takes GeneralUser's K-weighted level (the loudest 150 ms, as
elkit_balance reads) re GeneralUser's Standard snare: in its home set where
GeneralUser has that set, else in a set of GeneralUser's that plays the same
Roland voice (the CR-78 Tambourine in its 808/909 set). A key no set of
GeneralUser's plays is listed and left as it is.

--write scales the home set's KIT_LEVEL (PERCUSSION_LEVEL for Standard's);
--keys=set:key,... measures and writes just those (a set already balanced by
other means -- in-set, by ear, its room -- takes only the misses that are its
own: the Brush hat 22 dB hot, Standard's surdos 12-16).
"""
import os
import re
import sys
import tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
import elkit_fit as E                       # noqa: E402
import elkit_balance as EB                  # noqa: E402

GU_SETS = {0, 1, 2, 8, 16, 24, 25, 26, 32, 40, 48, 56, 127}    # GeneralUser GS's drum presets
MIN_DB = 1.0            # a miss under this is left alone


def lent():
    """{home set: {key: GeneralUser (set, key) to read it from, or None}}."""
    import percussion_gs as G
    out = defaultdict(dict)
    for w, keys in G.SETS.items():
        b = G.SET_KIT[w]
        for key, name in keys.items():
            sp = G.VOICE.get(name)
            if not sp or sp[0] not in ('k', 'n', 'r'):
                continue
            h, k = sp[1], sp[2]
            ref = out[h].get(k)
            if h in GU_SETS:
                ref = (h, k)
            elif ref is None and b in GU_SETS and sp[0] != 'r':
                ref = (b, key)
            out[h][k] = ref
    return out


def level(fn, kit, key, d):
    E.KIT = kit
    return EB.k150(*fn(key, d))


def main(argv):
    import percussion_map as P
    only = next((a.split("=")[1] for a in argv if a.startswith("--home=")), None)
    keys = next((a.split("=")[1] for a in argv if a.startswith("--keys=")), None)
    keys = {tuple(int(v) for v in kk.split(":")) for kk in keys.split(",")} if keys else None
    homes = lent()
    miss = defaultdict(dict)
    with tempfile.TemporaryDirectory() as d:
        g0 = level(lambda n, dd: E.theirs(EB.GU, n, dd), 0, 38, d)
        o0 = level(E.ours, 0, 38, d)
        for h in sorted(homes):
            if only and str(h) not in only.split(","):
                continue
            for k, ref in sorted(homes[h].items()):
                if keys is not None and (h, k) not in keys:
                    continue
                name = (P.KITS[h] if h else P.PERCUSSION).get(k, ("?",))[0]
                if ref is None:
                    print("  set %3d key %3d %-24s no GeneralUser reference" % (h, k, name), flush=True)
                    continue
                g = level(lambda n, dd: E.theirs(EB.GU, n, dd), ref[0], ref[1], d) - g0
                o = level(E.ours, h, k, d) - o0
                if g < -45:
                    print("  set %3d key %3d %-24s GeneralUser's (%d/%d) silent (%+.1f): left" % (h, k, name, ref[0], ref[1], g), flush=True)
                    continue
                miss[h][k] = g - o
                print("  set %3d key %3d %-24s GeneralUser %+6.1f (its %d/%d)  ours %+6.1f  -> %+.1f dB"
                      % (h, k, name, g, ref[0], ref[1], o, g - o), flush=True)
    if "--write" not in argv:
        return 0
    p = os.path.join(HERE, "percussion_map.py")
    s = open(p).read()
    for h, ms in miss.items():
        ms = {k: dv for k, dv in ms.items() if abs(dv) >= MIN_DB}
        if not ms:
            continue
        if h == 0:
            base = s.index("PERCUSSION_LEVEL = {")
            for k, dv in ms.items():
                cur = P.PERCUSSION_LEVEL.get(k, 1.0) * 10 ** (dv / 20.0)
                m = re.search(r"\n    %d: [0-9.]+," % k, s[base:])
                if m:
                    s = s[:base + m.start()] + "\n    %d: %.4f," % (k, cur) + s[base + m.end():]
                else:
                    # ...a key with no line yet: one added at the table's end
                    end = s.index("\n}\n", base)
                    s = s[:end] + "\n    %d: %.4f,   # balanced to GeneralUser GS (examples/lent_balance.py)" % (k, cur) + s[end:]
            print("  PERCUSSION_LEVEL: %s" % ", ".join("%d %+.1f" % (k, dv) for k, dv in sorted(ms.items())))
            continue
        base = s.index("KIT_LEVEL = ")
        m = re.search(r"(\{|\n             )%d: \{([^}]*)\}" % h, s[base:])
        if m is None:
            # a set with no levels yet: its line added after the table's first
            m = re.search(r"KIT_LEVEL = \{", s[base:])
            cur = {k: 10 ** (dv / 20.0) for k, dv in ms.items()}
            new = "KIT_LEVEL = {%d: {%s},\n             " % (h, ", ".join("%d: %.3f" % (k, cur[k]) for k in sorted(cur)))
            s = s[:base + m.start()] + new + s[base + m.end():]
        else:
            cur = {int(a): float(b) for a, b in re.findall(r"(\d+): ([0-9.]+)", m.group(2))}
            for k, dv in ms.items():
                cur[k] = cur.get(k, 1.0) * 10 ** (dv / 20.0)
            new = "%s%d: {%s}" % (m.group(1), h, ", ".join("%d: %.3f" % (k, cur[k]) for k in sorted(cur)))
            s = s[:base + m.start()] + new + s[base + m.end():]
        print("  KIT_LEVEL[%d]: %s" % (h, ", ".join("%d %+.1f" % (k, dv) for k, dv in sorted(ms.items()))))
    open(p, "w").write(s)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
