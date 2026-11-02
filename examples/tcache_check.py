#!/usr/bin/env python3
"""Does the native template cache hold what live.Patch holds?

    python3 examples/tcache_check.py [--programs=0,1,2,3] [--keys=21-96] [--tuner=hybrid]
    python3 examples/tcache_check.py --drums [--programs=0] [--keys=0-127]

live.Patch.warm builds each key of a part at every velocity bucket's centre
and every wheel step (_raw_template, at live's 48 kHz and 128 a block); the
native cache (native/live.cpp, native.TemplateCache) builds the same. Per
(key, bucket, step) every field a piano's template carries is compared with
==: the slab's columns (live.ALL_COLS, in their types), P, hrel, dur, the
velocity it was built at, fa_at, the masks (sym, ring, push, lflip), the
send, the scatter, and the offsets and extras a piano has none of.
--drums: the programs are drum sets (live.Patch(program, True): each key on
GM's percussion channel), and a drum's one-shot, its rows' own ends (rof)
and its strokes' offsets (sof) are compared too.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main(argv):
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    os.environ["TUNING_NATIVE_TONE"] = "off"
    import numpy as np
    import blockrender as B
    B.set_sample_rate(48000)
    B.BLK = 128
    import live as L
    import native as N
    drums = "drums" in opt
    progs = [int(x) for x in (opt.get("programs") or ("0" if drums else "0,1,2,3")).split(",")]
    lo, hi = (int(x) for x in (opt.get("keys") or ("0-127" if drums else "21-96")).split("-"))
    tuner = opt.get("tuner") or "hybrid"
    same = differ = 0
    for prog in progs:
        pt = L.Patch(prog, drums, tuner, 0)
        pt.range = (lo, hi)
        pt.warm()
        nc = N.TemplateCache(prog, tuner, drums=drums)
        nc.warm(lo, hi, pt.nbuckets, pt.speeds)
        for (note, b, sp), t in sorted(pt.templates.items(), key=lambda kv: (kv[0][0], kv[0][1], str(kv[0][2]))):
            q = nc.get(note, b, sp)
            bad = []
            if q is None:
                bad.append("missing")
            else:
                for c in L.ALL_COLS:
                    a, x = np.asarray(t[c]), np.asarray(q[c])
                    if a.dtype != x.dtype or not np.array_equal(a, x):
                        bad.append(c)
                for c in ("hrel", "fa_at", "sym", "ring", "push", "lflip"):
                    a, x = np.asarray(t[c]), np.asarray(q[c])
                    if a.dtype != x.dtype or not np.array_equal(a, x):
                        bad.append(c)
                for c in ("P", "dur", "vel", "oneshot", "send", "scatter_ms", "grain", "rel"):
                    if t.get(c) != q.get(c):
                        bad.append("%s (%r vs %r)" % (c, t.get(c), q.get(c)))
                for c in ("gof", "sof", "cof", "rof"):
                    a, x = t.get(c), q.get(c)
                    if (a is None) != (x is None) or (a is not None and not (
                            np.asarray(a).dtype == np.asarray(x).dtype and np.array_equal(a, x))):
                        bad.append(c)
                if t.get("ranks") or t.get("rel_rank") or t.get("FT") is not None:
                    bad.append("a field a piano does not have")
            if bad:
                differ += 1
                if differ <= 10:
                    print("  program %d key %d bucket %d step %r DIFFERS: %s" % (prog, note, b, sp, " ".join(bad[:6])))
            else:
                same += 1
        print("  program %d: %d buckets, steps %r" % (prog, pt.nbuckets, pt.speeds))
    print("template cache: %d identical, %d differ" % (same, differ))
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
