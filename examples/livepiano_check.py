#!/usr/bin/env python3
"""Does the native piano part play live MIDI as live.Live does?

    python3 examples/livepiano_check.py [BLOCKS] [--program=N] [--seed=N] [--every=N] [--render] [--register]
                                        [--half] [--pedal-key=N] [--pressure]
                                        [--gpu=c|cl] [--gpu-min=N]

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
--register: the free strings too (live's register, on the CPU here), its
worker answering each job as it is sent on both sides -- live's through
register.LiveWorker in step with its callback, the native part's in
native/livereg.cpp -- so a reply is placed at the first pump after its job.
--half: the pedal at values through damper.py's band as well (ondine.mid's
0/24/40/.../127; --half=all: any value), so half-pedalled keys take damper
tracks (live._damp_block):
the slabs' dk compared as which slots are on a track and that track's two
values (DM), as a track's number is handed out in a set's order, and dg.
--pedal-key=N: key N held as the sustain pedal and pushed into (channel
aftertouch while it is held) -- live.Route(("note", N), 64) through on_midi
on one side, native.KeyPedal before the part's events on the other.
--pressure: channel aftertouch among the controls (live's Slab.press).
--gpu: each side renders as live.GpuRenderer -- the setup on the CPU
(voice_block), the samples on the OpenCL GPU ("cl": live's through pyopencl,
the native part's through native/gpu.cpp) or the C reference ("c",
voice_samples) -- for a block with GPU-MIN busy slots or more (default
live's GPU_MIN); the blocks each side took to the GPU are counted.
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))


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
    ngpu = [0, 0]
    if "gpu" in opt:
        gmin = int(opt.get("gpu-min", L.GPU_MIN))
        send = lv.renderer.send
        lv.renderer = L.GpuRenderer(lv.slab, 128, 1, backend=opt["gpu"] or "cl", gpu_min=gmin)
        lv.renderer.send = send
        nv.gpu(opt["gpu"] or "cl", gmin)
    if "register" in opt:
        import blockrender as BR
        import regsync
        regsync.sync(lv, part)
        nv.register(pt._voice_class(60), BR.tuning_table(pt.tuner), 48000.0, getattr(BR, 'REGISTER_SCALE', 1.0),
                    [lv._reg_voice(part, n) for n in range(128)])
    held = set()
    ntr = dmb = 0
    pk = int(opt["pedal-key"]) if "pedal-key" in opt else None
    kp = None
    if pk is not None:
        lv.set_routes([L.Route(("note", pk), 64)])
        kp = N.KeyPedal(pk)
    pk_down = set()
    pedal = ((0, 24, 40, 56, 72, 88, 104, 127) if opt.get("half") != "all" else tuple(range(128))) \
        if "half" in opt else (0, 127)
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
        dk, xk = np.asarray(S.a['dk']), nv.slab.col("dk")
        if not np.array_equal(dk >= 0, xk >= 0):
            bad.append("dk")
        else:
            on = np.flatnonzero((dk >= 0) & np.asarray(S.busy, bool))
            ndm = nv.dm()
            if not (np.array_equal(S.DM[2 * dk[on]], ndm[2 * xk[on]])
                    and np.array_equal(S.DM[2 * dk[on] + 1], ndm[2 * xk[on] + 1])):
                bad.append("DM")
        if not np.array_equal(np.asarray(S.a['dg']), nv.slab.col("dg")):
            bad.append("dg")
        return bad

    for b in range(blocks):
        msgs = []
        for _ in range(rng.choice((0, 0, 0, 1, 1, 2, 3))):
            r = rng.random()
            ch = rng.choice((0, 0, 0, 1))
            if r < 0.4 or not held:
                note = rng.randint(lo, hi)
                if note == pk:
                    continue            # the pedal key plays no note
                msgs.append(M("note_on", channel=ch, note=note, velocity=rng.randint(1, 127)))
                held.add((ch, note))
            elif r < 0.8:
                ch, note = rng.choice(sorted(held))
                held.discard((ch, note))
                msgs.append(M("note_off", channel=ch, note=note, velocity=0))
            elif pk is not None and r < 0.9:
                # the pedal key: pressed, let go, or pushed into while down
                if ch in pk_down and rng.random() < 0.7:
                    msgs.append(M("aftertouch", channel=ch, value=rng.randint(0, 127)))
                elif ch in pk_down:
                    pk_down.discard(ch)
                    msgs.append(M("note_off", channel=ch, note=pk, velocity=0))
                else:
                    pk_down.add(ch)
                    msgs.append(M("note_on", channel=ch, note=pk, velocity=rng.randint(1, 127)))
            elif r < 0.9:
                msgs.append(M("control_change", channel=ch, control=64, value=rng.choice(pedal)))
            elif "pressure" in opt and rng.random() < 0.4:
                msgs.append(M("aftertouch", channel=ch, value=rng.choice((0, rng.randint(0, 127)))))
            else:
                cc = rng.choice((7, 11, 10, 67))
                msgs.append(M("control_change", channel=ch, control=cc, value=rng.randint(0, 127)))
        n0 = lv.n
        for m in msgs:
            lv.on_midi(m)
            for x in (kp.feed(m) if kp is not None else [m]):
                nv.event(x)
        lv.callback(None, 128, None, 0)
        nv.block(n0, 128)
        while dry:
            rn0, fr, dL, dR, snd, sL, sR = dry.pop(0)
            got = nv.render(rn0, fr, send=snd)
            if "gpu" in opt:
                ngpu[0] += lv.renderer.on_gpu
                ngpu[1] += nv.on_gpu()
            ok = np.array_equal(dL, got[0]) and np.array_equal(dR, got[1]) and (
                not snd or (np.array_equal(sL, got[2]) and np.array_equal(sR, got[3])))
            if not ok:
                rbad.append(b)
                bad.append("render")
        log.append((b, n0, msgs))
        ntr = max(ntr, len(lv.damp_tracks))
        dmb += bool(lv.damp_tracks)
        if b % every == every - 1 or b == blocks - 1:
            if compare(b):
                print("  block %d (sample %d) DIFFERS: %s" % (b, n0, " ".join(bad[:8])))
                if "debug" in opt:
                    for c in bad[:2]:
                        if c in L.ALL_COLS:
                            x, y = np.asarray(lv.slab.a[c]), nv.slab.col(c)
                            dd = np.flatnonzero(x != y)
                            print("    %s at %d slots, e.g. %s: live %s native %s" % (
                                c, len(dd), dd[:6].tolist(), x[dd[:6]].tolist(), y[dd[:6]].tolist()))
                    own = {int(q): k for k, v in lv.slab.live.items() for q in v}
                    print("    owners:", [own.get(int(q), "reg/retiring") for q in dd[:6]])
                for x in log[-4:]:
                    print("    block %d at %d: %s" % (x[0], x[1], "; ".join(str(m) for m in x[2]) or "-"))
                break
    sounding = sum(len(v) for v in lv.slab.live.values())
    if "register" in opt:
        print("  register: %d rows placed, %d dropped (native %d); live's errors: %d %s" % (
            int(np.sum(lv.slab.busy)) - sounding, lv.reg_dropped, nv.reg_dropped(), lv.errors,
            lv.last_error or ""))
    if "gpu" in opt:
        print("  GPU (%s): live took %d blocks to it, native %d" % (opt["gpu"] or "cl", ngpu[0], ngpu[1]))
    if "half" in opt:
        print("  dampers: up to %d tracks at once, %d blocks with one" % (ntr, dmb))
    print("live piano: %d blocks, program %d, %s%s (%d slots sounding at the end)"
          % (b + 1, prog, "identical" if not bad else "differs",
             ", every block's render too" if "render" in opt and not rbad else "", sounding))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
