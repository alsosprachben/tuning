#!/usr/bin/env python3
"""Does the native piano part play live MIDI as live.Live does?

    python3 examples/livepiano_check.py [BLOCKS] [--program=N] [--seed=N] [--every=N] [--render]

live.Live(program, 48 kHz, 128 a block, on the CPU: no register) and the
native piano part (native/slab.cpp: its template cache, its slab, live's
events for it) are fed the same random MIDI block by block -- presses and
key-ups across the keyboard, the sustain pedal as a switch, CC7, CC11, CC10,
CC67 -- through on_midi and live's own callback on one side and the native
part's block on the other. Every EVERY blocks (default 1) the two slabs are
compared with ==: every slot column, the bookkeeping, the free queue's
order. The first block that differs is reported with its events. Live's
governor (Slab.shed, by the wall-clock render time) is off: a host policy,
not arithmetic to match. --render: each block's dry render too -- live's
Renderer.render (and its room send, when on) against the native part's.
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "") for a in argv[1:] if a.startswith("--"))
    os.environ["TUNING_NATIVE_TONE"] = "off"
    import mido
    import numpy as np
    import blockrender as B
    import live as L
    import native as N
    blocks = int(args[0]) if args else 2000
    prog = int(opt.get("program", 0))
    every = int(opt.get("every", 1))
    rng = random.Random(int(opt.get("seed", 1)))
    lv = L.Live(program=prog, rate=48000, frames=128, verbose=False, threads=1, gpu=False)
    part = lv.parts[0]
    pt = part.patch
    pt.warm()           # live warms off the audio thread; here, before the first press
    lv.slab.shed = lambda n, frac: 0    # the governor sheds by wall-clock render time: not a reference
    lo, hi = pt.range
    cache = N.TemplateCache(prog, pt.tuner)
    cache.warm(lo, hi, pt.nbuckets, pt.speeds)
    speed = None if pt.speeds == (None,) else (lv.detune_step.get(part.pid, pt.leslie_default)
                                               if pt.detune_wheel else pt.leslie_default)
    nv = N.LivePiano(cache, part.pid, part.level_db, pt.nbuckets, speed, pt.damper_pedal, pt.soft_pedal_strings,
                     pt.soft_pedal_top, 48000, capacity=lv.slab.cap, headroom=lv.slab.headroom)
    held = set()
    M = mido.Message
    dry = []
    if "render" in opt:
        _rend = lv.renderer.render

        def _cap(n0, frames):
            oL, oR = _rend(n0, frames)
            r = lv.renderer
            dry.append((n0, frames, oL.copy(), oR.copy(), bool(r.send),
                        r.SL[:frames].copy() if r.send else None, r.SR[:frames].copy() if r.send else None))
            return oL, oR
        lv.renderer.render = _cap
    rbad = []
    bad, log = [], []

    def compare(b):
        S = lv.slab
        for c in L.ALL_COLS + ("sw",):
            a, x = np.asarray(S.a[c]), nv.slab.col(c)
            if a.dtype != x.dtype or not np.array_equal(a, x):
                bad.append(c)
        for c in ("aL0", "aR0", "sg", "sre", "hrel", "vbase", "vrbase", "vsc"):
            a = np.asarray(getattr(S, c))
            if not np.array_equal(a, nv.slab.col(c).astype(a.dtype)):
                bad.append(c)
        if not np.array_equal(np.asarray(S.busy, np.int32), nv.slab.col("busy")):
            bad.append("busy")
        if list(S.free) != nv.slab.free_list():
            bad.append("the free queue")
        return bad

    for b in range(blocks):
        msgs = []
        for _ in range(rng.choice((0, 0, 0, 1, 1, 2, 3))):
            r = rng.random()
            ch = rng.choice((0, 0, 0, 1))
            if r < 0.4 or not held:
                note = rng.randint(lo, hi)
                msgs.append(M("note_on", channel=ch, note=note, velocity=rng.randint(1, 127)))
                held.add((ch, note))
            elif r < 0.8:
                ch, note = rng.choice(sorted(held))
                held.discard((ch, note))
                msgs.append(M("note_off", channel=ch, note=note, velocity=0))
            elif r < 0.9:
                msgs.append(M("control_change", channel=ch, control=64, value=rng.choice((0, 127))))
            else:
                cc = rng.choice((7, 11, 10, 67))
                msgs.append(M("control_change", channel=ch, control=cc, value=rng.randint(0, 127)))
        n0 = lv.n
        for m in msgs:
            lv.on_midi(m)
            nv.event(m)
        lv.callback(None, 128, None, 0)
        nv.block(n0, 128)
        while dry:
            rn0, fr, dL, dR, snd, sL, sR = dry.pop(0)
            got = nv.render(rn0, fr, send=snd)
            ok = np.array_equal(dL, got[0]) and np.array_equal(dR, got[1]) and (
                not snd or (np.array_equal(sL, got[2]) and np.array_equal(sR, got[3])))
            if not ok:
                rbad.append(b)
                bad.append("render")
        log.append((b, n0, msgs))
        if b % every == every - 1 or b == blocks - 1:
            if compare(b):
                print("  block %d (sample %d) DIFFERS: %s" % (b, n0, " ".join(bad[:8])))
                for x in log[-4:]:
                    print("    block %d at %d: %s" % (x[0], x[1], "; ".join(str(m) for m in x[2]) or "-"))
                break
    sounding = sum(len(v) for v in lv.slab.live.values())
    print("live piano: %d blocks, program %d, %s%s (%d slots sounding at the end)"
          % (b + 1, prog, "identical" if not bad else "differs",
             ", every block's render too" if "render" in opt and not rbad else "", sounding))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
