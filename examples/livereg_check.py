#!/usr/bin/env python3
"""Does native/livereg.cpp answer live's register jobs as register.LiveChannel does?

    python3 examples/livereg_check.py [JOBS] [--program=N] [--seed=N] [--scale=X]

A piano part's string bank (register.Strings as live's worker builds it,
and native/strings.c's), and a LiveChannel and a native.LiveReg on it, fed
the same random jobs as live's audio thread makes them: strikes (each key's
direct rows from its live template -- native.template, the direct sound
_reg_pump picks, at the strike's sample -- with the keys free then: those
held, the pedal's, the undamped top), releases (a strike's damper fell),
damps (the keys no longer free), and the felt (the pedal in the band: random
keys' contact, damper.py's rate). Every answer compared with ==: the modes,
their state, the floor, a strike's forced rows.
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    import numpy as np
    import blockrender as B
    B.set_sample_rate(48000)
    B.BLK = 128
    import damper as DMP
    import native as N
    import register as RG
    jobs = int(args[0]) if args else 400
    prog = int(opt.get("program", 0))
    scale = float(opt.get("scale", getattr(B, 'REGISTER_SCALE', 1.0)))
    tuner = opt.get("tuner", "hybrid440")
    rng = random.Random(int(opt.get("seed", 1)))
    sr = 48000.0
    cls = B.property_class_for_note(prog, 60)
    table = B.tuning_table(tuner)
    Sg = RG.Strings(cls, table, 0.0, 1.0, sr, (B.string_partial, B.partial_decay, B.unison_partial))
    py = RG.LiveChannel(Sg, RG._isolated(cls, 261.63, 0.0, 1.0), sr, scale)
    nv = N.LiveReg(cls, table, sr, scale)
    if nv.M != len(Sg.f):
        print("string banks differ: %d modes vs %d" % (nv.M, len(Sg.f)))
        return 1
    top = py.top
    tcache = {}

    def drv_of(note, vel, at, base):
        if (note, vel) not in tcache:
            tcache[(note, vel)] = N.template(prog, note, vel, tuner)
        t = tcache[(note, vel)]
        if t is None:
            return None
        dl = t["delL"].astype(np.float64) + t["delR"].astype(np.float64)
        ix = np.flatnonzero(dl <= dl.min() + 2.0)
        drv = dict(om=t["om"][ix].astype(np.float64), p0=t["p0"][ix].astype(np.float64),
                   delL=t["delL"][ix].astype(np.float64),
                   aM=0.5 * (t["aL"][ix].astype(np.float64) + t["aR"][ix].astype(np.float64)),
                   non=t["non"][ix].astype(np.float64) + at, slot=ix + base)
        for c in ("logr", "logrA", "aft", "sus", "tbav", "tau", "tcut"):
            drv[c] = t[c][ix].astype(np.float64)
        return drv

    held, pedal, sid, at = {}, False, 0, 0.0
    strikes = {}                  # key -> its latest strike's id (live's reg_strike_of)
    bad = []
    counts = dict(strike=0, release=0, damp=0, felt=0, modes=0, forced=0)

    def free_now():
        keys = set(held) | set(range(top, 109))
        if pedal:
            keys |= set(range(21, 109))
        return sorted(keys)

    def same(what, a, b):
        ia, za = a[0], a[1]
        ib, zb = b[0], b[1]
        ok = np.array_equal(np.asarray(ia, np.int64), ib) and np.array_equal(np.asarray(za, complex), zb)
        if len(a) > 2:
            ok = ok and a[2] == b[2]
        ok = ok and py.fl * max(py.loud, 1e-30) == nv.floor()
        if not ok:
            bad.append(what)
            print("  job %d (%s) DIFFERS: %d vs %d modes%s" % (
                counts['strike'] + counts['release'] + counts['felt'], what, len(ia), len(ib),
                "" if len(ia) != len(ib) or not len(ia) else
                ", max |dz| %g" % float(np.max(np.abs(np.asarray(za) - zb)))))
            if len(a) > 2 and a[2] != b[2]:
                print("    forced: %d vs %d rows" % (len(a[2]), len(b[2])))
        counts['modes'] += len(ia)
        return ok

    for _ in range(jobs):
        at += rng.choice((0, 0, 128, 256, 1280, 4800, 24000))
        r = rng.random()
        if r < 0.45 or not held:
            note = rng.randint(21, 108)
            vel = rng.choice((20, 50, 80, 110, 127))
            sid += 1
            drv = drv_of(note, vel, at, 1000 * sid)
            if drv is None:
                continue
            held[note] = sid
            strikes[note] = sid
            fk = free_now()
            a = py.strike(sid, note, at, drv, fk)
            b = nv.strike(sid, note, at, drv, fk)
            counts['strike'] += 1
            counts['forced'] += len(a[2])
            if not same("strike %d" % note, a, b):
                break
        elif r < 0.8:
            note = rng.choice(sorted(held))
            held.pop(note)
            fk = free_now()
            if note not in fk:
                s = strikes.pop(note, None)
                if s is not None:
                    a = py.release(s, at, fk)
                    b = nv.release(s, at, fk)
                    counts['release'] += 1
                    if not same("release %d" % note, a, b):
                        break
                damp = sorted(set(range(21, 109)) - set(fk))
                py.damp(damp)
                nv.damp(damp)
                counts['damp'] += 1
        elif r < 0.9:
            pedal = not pedal
            if not pedal:            # its dampers fall: the released strikes hand over, the rest damp
                fk = free_now()
                for note in [k for k in strikes if k not in fk]:
                    s = strikes.pop(note)
                    a = py.release(s, at, fk)
                    b = nv.release(s, at, fk)
                    counts['release'] += 1
                    if not same("pedal-up release %d" % note, a, b):
                        break
                if bad:
                    break
                damp = sorted(set(range(21, 109)) - set(fk))
                py.damp(damp)
                nv.damp(damp)
                counts['damp'] += 1
        else:
            keys = sorted(rng.sample(range(21, 109), rng.randint(1, 30)))
            rates = [DMP.rate_db_s(rng.random(), False) * DMP.LN10_20 if rng.random() < 0.8 else 0.0
                     for _ in keys]
            a = py.felt(at, keys, rates)
            b = nv.felt(at, keys, rates)
            counts['felt'] += 1
            if not same("felt", a, b):
                break
    print("live register (program %d, scale %g): %d strikes (%d forced rows), %d releases, %d damps, %d felt; "
          "%d modes answered, %s" % (prog, scale, counts['strike'], counts['forced'], counts['release'],
                                     counts['damp'], counts['felt'], counts['modes'],
                                     "identical" if not bad else "differs"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
