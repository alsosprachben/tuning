#!/usr/bin/env python3
"""NATURAL TUNINGS (tonelib natural_tuner): which voices play their own, and
does every engine resolve them alike?

    python3 examples/natural_tuning_check.py [-v]

1. Every tone in the program map and its variations whose class names a
   natural tuner, by tuner -- so a class that inherits one by accident (a
   brass voice under the organ's base) shows up here. -v lists them all.
2. For each natural tuner under a set of rig tuners (and a= references):
   blockrender.natural_table's A4 is the rig table's A4 (to the last bit or
   two of the rescale); the
   native engine's table for the same name (name~Hz) is Python's, key for
   key; live.tuner_for gives the same name as blockrender.natural_spec.
3. The rule's other branches: a part's own choice, "rig", a drum set, the
   natural switch off, the rig already in the natural tuner.
"""
import collections
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main(argv):
    import blockrender as B
    import live as L
    import native as N
    import patch_map as P
    import tunelib as TL
    verbose = "-v" in argv
    bad = 0
    # 1. the voices
    by = collections.defaultdict(list)
    tones = [(p, 0) for p in range(128)] + sorted(k for k in P.VARIATIONS if k[1] & P.CAB_MASK == k[1])
    for prog, var in tones:
        pc = P.variation_class(prog, var)
        t = getattr(pc, "natural_tuner", None)
        if t:
            by[t].append("%d.%d %s" % (prog, var, pc.__name__))
    for t in sorted(by):
        print("%s: %d tones%s" % (t, len(by[t]), (" -- " + ", ".join(by[t])) if verbose else
                                  (" -- e.g. " + ", ".join(by[t][:4]))))
    # 2. the tables, three engines
    n = 0
    for ref in (None, dict(a=432.0), dict(c=256.0)):
        TL.set_reference(**(ref or {}))
        for rig in ("gm2", "hybrid440", "even", "hybrid", "pyth", "hybridharm:466"):
            R = B.tuning_table(rig)
            for name in sorted(by):
                pc = P.variation_class(*map(int, by[name][0].split()[0].split(".")))
                spec = B.natural_spec(pc, R, rig, on=True)
                if rig.split(":")[0] == name:
                    if spec is not None:
                        print("%s under %s: resolved again (%s)" % (name, rig, spec))
                        bad += 1
                    continue
                t = B.natural_table(pc, R, rig, on=True)
                if abs(t[69] / R[69] - 1.0) > 1e-12:      # (the rescale's last bit: a table times a ratio)
                    print("%s under %s %s: A4 %r, the rig's %r" % (name, rig, ref, t[69], R[69]))
                    bad += 1
                nv = N.tuning_table(spec)
                if nv != t:
                    k = [x for x in range(128) if nv.get(x) != t.get(x)]
                    print("%s (%s, reference %s): native differs at %d keys, e.g. %d: %r %r"
                          % (spec, rig, ref, len(k), k[0], t.get(k[0]), nv.get(k[0])))
                    bad += 1
                prog, var = map(int, by[name][0].split()[0].split("."))
                lv = L.tuner_for(prog, False, rig, None, var)
                if lv != spec:
                    print("%s.%s under %s: live %r, blockrender %r" % (prog, var, rig, lv, spec))
                    bad += 1
                n += 1
    TL.set_reference()
    # 3. the rule's other branches
    hp = (6, 0)
    cases = [((6, False, "hybrid440", None, 0, "rig"), "hybrid440"),
             ((6, False, "hybrid440", None, 0, "even"), "even"),
             ((6, False, "hybrid440", None, 0, "pleyel~440"), "pleyel~440"),
             ((6, True, "gm2", None, 0, None), "gm2"),
             ((0, False, "gm2", None, 0, None), "gm2"),
             ((6, False, "hybridmean:415", None, 0, None), "hybridmean:415")]
    for args, want in cases:
        got = L.tuner_for(*args)
        if got != want:
            print("tuner_for%r: %r, not %r" % (args, got, want))
            bad += 1
    L.NATURAL_TUNINGS[0] = False
    if L.tuner_for(hp[0], False, "hybrid440", None, hp[1]) != "hybrid440":
        print("natural tunings off: the harpsichord still plays its own")
        bad += 1
    L.NATURAL_TUNINGS[0] = True
    print("natural tunings: %d tables resolved alike in Python, native and live; %d cases; %s"
          % (n, len(cases) + 1, "all ok" if not bad else "%d WRONG" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
