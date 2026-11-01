#!/usr/bin/env python3
"""Does the native slab stamp, release and reap as live.Slab does?

    python3 examples/slab_check.py [EVENTS] [--seed=N] [--capacity=N] [--program=N]

live's partial table, the slab: a press stamps its key's template into free
slots, a key-up releases them, a finished release is reaped. Both slabs --
live.Slab and native/slab.cpp's -- are fed the same piano templates (the
engine's, native.template, with live's derived fields: hrel, dur, the send)
and the same random sequence of EVENTS (default 400) presses, releases and
reaps at rising sample times, live's rate and block; then every slot column,
the slab's bookkeeping (send, the levels at stamp, hrel, the vibrato's base
and scale, the slot's channel, busy) and the free queue's order are compared
with ==. Run at checkpoints along the way, so a difference is found near
where it starts.
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def live_template(N, B, prog, note, vel):
    """native.template plus the fields live._raw_template derives for a piano."""
    import numpy as np
    t = N.template(prog, note, vel)
    t = {k: (np.asarray(v) if hasattr(v, "__len__") and not isinstance(v, (str, tuple, list, dict)) else v)
         for k, v in t.items()}
    nf = np.asarray(t["nf"]).astype(np.float64)
    t["hrel"] = (nf / max(nf.min(), 1e-9)).astype(np.float32) if len(nf) else np.zeros(0, np.float32)
    t["oneshot"] = False
    t["dur"] = int(t["noff"][0] - t["non"][0]) if t["P"] else 0
    cls = B.property_class_for_note(prog, note)
    t["send"] = getattr(cls, "reverb_distance", None)
    t["scatter_ms"] = getattr(cls, "section_onset_ms", 0.0) or 0.0
    for k in ("cof", "gof", "sof", "rof"):
        t[k] = None
    t["vel"] = vel
    return t


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    os.environ["TUNING_NATIVE_TONE"] = "off"
    import numpy as np
    import blockrender as B
    import live as L
    import native as N
    B.set_sample_rate(48000)
    B.BLK = 128
    events = int(args[0]) if args else 400
    rng = random.Random(int(opt.get("seed", 7)))
    cap = int(opt.get("capacity", 16384))
    prog = int(opt.get("program", 0))
    head = 10.0 ** (-4.0 / 20.0)
    py = L.Slab(cap)
    py.headroom = head
    nv = N.Slab(cap, head)
    cache = {}
    held = []
    n = 0
    bad = []

    def compare(at):
        for c in L.ALL_COLS + ("sw",):
            a, b = np.asarray(py.a[c]), nv.col(c)
            if a.dtype != b.dtype or not np.array_equal(a, b):
                bad.append("%s after event %d" % (c, at))
        for c in ("aL0", "aR0", "sg", "sre", "hrel", "vbase", "vrbase", "vsc"):
            a = np.asarray(getattr(py, c))
            if not np.array_equal(a, nv.col(c).astype(a.dtype)):
                bad.append("%s after event %d" % (c, at))
        if not np.array_equal(np.asarray(py.a["dk"], np.int32), nv.col("dk")):
            bad.append("dk after event %d" % at)
        if not np.array_equal(np.asarray(py.busy, np.int32), nv.col("busy")):
            bad.append("busy after event %d" % at)
        if not np.array_equal(np.asarray(py.slot_ch, np.int32), nv.col("slot_ch")):
            bad.append("slot_ch after event %d" % at)
        if list(py.free) != nv.free_list():
            bad.append("the free queue after event %d" % at)

    stamped = released = 0
    for e in range(events):
        n += rng.randint(0, 3000)
        r = rng.random()
        if r < 0.5 or not held:
            note, vel, ch = rng.randint(21, 108), rng.randint(1, 127), rng.randint(0, 3)
            b = (note, vel)
            if b not in cache:
                cache[b] = live_template(N, B, prog, note, vel)
            t = cache[b]
            key = (1, ch, note, None)
            scale = rng.choice((1.0, 1.0, rng.uniform(0.2, 1.5)))
            a, c = py.stamp(t, key, n, scale), nv.stamp(t, key, n, scale)
            if a != c:
                bad.append("stamp %d: %r vs %r" % (e, a, c))
            if a:
                held.append(key)
                stamped += 1
        elif r < 0.85:
            key = held.pop(rng.randrange(len(held)))
            py.release(key, n)
            nv.release(key, n)
            released += 1
        else:
            py.reap(n)
            nv.reap(n, B.BLK)
        if e % 50 == 49 or e == events - 1:
            compare(e)
            if bad:
                break
    for x in bad[:10]:
        print("  DIFFERS: %s" % x)
    print("slab: %d events (%d stamps, %d releases), %s"
          % (events, stamped, released, "identical" if not bad else "%d differences" % len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
