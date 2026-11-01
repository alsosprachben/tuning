#!/usr/bin/env python3
"""Do the native tuners (native/tuner.cpp) give blockrender.tuning_table's tables?

    python3 examples/tuner_check.py

Every name in midilib's registry; every key (@C .. @B) and a set of
pitches (:415, :432, :440, :466, :392.5) on the tuners that take them, and
both at once; Indian intonation over every raga system, several ragas and
keys, with and without Sa's own pitch -- each at the tuners' own pitch, and
again under tunelib.set_reference's a=432 and c=256. Each table compared
with ==, key for key, and which keys have a frequency; the names a tuner
refuses (a key on a twelve-tone one) refused by both.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main(argv):
    import blockrender as B
    import midilib
    import native as N
    import ragas
    import tunelib as TL
    names = list(midilib.tuner_registry)
    keys = ["c", "c#", "db", "d", "eb", "e", "f", "f#", "g", "ab", "a", "bb", "b"]
    pitches = ["415", "432", "440", "466", "392.5"]
    path = [n for n, c in midilib.tuner_registry.items() if issubclass(c, TL.PathTuner)]
    specs = list(names)
    specs += ["%s@%s" % (n, k) for n in path for k in keys]
    specs += ["%s:%s" % (n, p) for n in path for p in pitches]
    specs += ["%s@%s:%s" % (n, k, p) for n in path for k in ("d", "f#", "bb") for p in ("466", "430")]
    specs += ["even@d", "pyth:466", "hybrid@h", "nosuch", "hybrid:abc"]          # refused
    specs += ["raga:%s@%s" % (s, k) for s in ragas.SYSTEMS for k in ("c", "c#", "a")]
    specs += ["raga:%s/%s@d:%s" % (s, r, hz) for s in ("just5", "et", "bel_todi")
              for r in ("todi", "yaman", "bhairavi") for hz in ("146.83", "150")]
    specs += ["raga:just5/nosuch@c", "raga:nosuch@c", "raga:just5"]               # refused
    n_ok = n_ref = 0
    for ref in (None, dict(a=432.0), dict(c=256.0)):
        TL.set_reference(**(ref or {}))
        for spec in specs:
            try:
                py = B.tuning_table(spec)
            except Exception as e:
                py = e
            try:
                nv = N.tuning_table(spec)
            except ValueError as e:
                nv = e
            if isinstance(py, Exception) or isinstance(nv, Exception):
                if not (isinstance(py, Exception) and isinstance(nv, Exception)):
                    print("%s (reference %s): python %r, native %r" % (spec, ref, py, nv))
                    return 1
                n_ref += 1
                continue
            if py != nv:
                bad = [n for n in range(128) if py.get(n) != nv.get(n)]
                print("%s (reference %s): %d keys differ, e.g. %d: python %r native %r"
                      % (spec, ref, len(bad), bad[0], py.get(bad[0]), nv.get(bad[0])))
                return 1
            n_ok += 1
    TL.set_reference()
    print("tuners: %d tables identical, %d names refused by both" % (n_ok, n_ref))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
