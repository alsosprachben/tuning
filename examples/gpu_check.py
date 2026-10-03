#!/usr/bin/env python3
"""Does the GPU renderer play what the CPU plays?

    python3 examples/gpu_check.py [--programs 0,48,81] [--frames 128] [--time] [--no-gpu]

Each scene is played three times through the live engine, block by block, at
48 kHz and 128 frames (or --frames): by the CPU renderer (synth_voice), by GpuRenderer with
the C reference sample pass (backend "c": the descriptors voice_block wrote,
run through voice_samples) and by GpuRenderer on the GPU (backend "cl"). Two
differences are printed per scene, relative to the CPU's peak:

  setup   C reference against the CPU: whether the descriptors carry all
          synth_voice does per sample (only the phasors' evaluation and the
          summing order differ, ~1e-6)
  gpu     the GPU against the CPU

A scene: a chord struck, the mod wheel brought in, a bend, aftertouch, and a
release, so vibrato, the bends, the chiff in and out, a Moog's contours and
whatever its panel draws (LFO, noise, sync, FM) all play. --time also times
each backend per block (median and 99th percentile, ms).
"""
import os
import sys
import time

import numpy as np
import mido

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import live as LV                                       # noqa: E402

# the acoustic voices that exercise the setup (strings: chiff and vibrato;
# piano: the tension bend; organ; brass: mode lock; guitar, flute), and every
# synth program, which is where the Moogs are
PROGRAMS = [0, 19, 24, 48, 56, 61, 73] + list(range(80, 104))
FRAMES, RATE = 128, 48000


def play(prog, backend, timing=False):
    lv = LV.Live(program=prog, rate=RATE, frames=FRAMES, verbose=False, tuner="even")
    lv.warm()
    if backend:
        lv.renderer.close()
        lv.renderer = LV.GpuRenderer(lv.slab, FRAMES, 1, backend=backend, gpu_min=0)
        lv.slab.dirty = True
    lv.renderer.send = True
    out, snd, ms, flags = [], [], [], 0
    ev = {0: [mido.Message("note_on", channel=0, note=n, velocity=100) for n in (48, 55, 60, 64)],
          60: [mido.Message("control_change", channel=0, control=1, value=90)],
          120: [mido.Message("pitchwheel", channel=0, pitch=3000)],
          160: [mido.Message("aftertouch", channel=0, value=100)],
          200: [mido.Message("note_off", channel=0, note=n) for n in (48, 55, 60, 64)]}
    for blk in range(300 * 128 // FRAMES):
        for m in ev.get(blk * FRAMES // 128 if blk * FRAMES % 128 == 0 else -1, ()):
            lv.on_midi(m)
        n0 = lv.n
        lv.apply(n0); lv.sweep(n0); lv.slab.reap(n0)
        t0 = time.perf_counter()
        L, R = lv.renderer.render(n0, FRAMES)
        ms.append((time.perf_counter() - t0) * 1e3)
        if backend and lv.renderer.on_gpu and lv.renderer.tab.nact:
            flags |= int(np.bitwise_or.reduce(lv.renderer.tab.D['flags'][:lv.renderer.tab.nact]))
        out.append(np.stack([L, R]).copy())
        snd.append(np.stack([lv.renderer.SL[:FRAMES], lv.renderer.SR[:FRAMES]]).copy())
        lv.n = n0 + FRAMES
    act = lv.renderer.act
    lv.renderer.close()
    return np.concatenate(out, 1), np.concatenate(snd, 1), np.array(ms[20 * 128 // FRAMES:]), act, flags


def rel(a, b):
    return float(np.abs(a - b).max()) / max(float(np.abs(b).max()), 1e-30)


def main(argv):
    global FRAMES
    if "--frames" in argv:
        FRAMES = int(argv[argv.index("--frames") + 1])
    progs = PROGRAMS
    if "--programs" in argv:
        progs = [int(x) for x in argv[argv.index("--programs") + 1].split(",")]
    backs = ["c"] + ([] if "--no-gpu" in argv else ["cl"])
    timing = "--time" in argv
    worst = {}
    print("prog  active   setup       gpu        send(gpu)" + ("   cpu ms     gpu ms" if timing else ""))
    for p in progs:
        ref, rsnd, rms_, act, _ = play(p, None)
        line = "%4d  %6d" % (p, act)
        res = {}
        for bk in backs:
            o, s, ms, _, fl = play(p, bk)
            res[bk] = (rel(o, ref), rel(s, rsnd), ms, fl)
            worst[bk] = max(worst.get(bk, 0.0), res[bk][0])
        line += "   %.1e" % res["c"][0]
        if "cl" in res:
            line += "    %.1e    %.1e" % (res["cl"][0], res["cl"][1])
            if timing:
                q = lambda m: "%.2f/%.2f" % (np.median(m), np.percentile(m, 99))   # noqa: E731
                line += "   %s  %s" % (q(rms_), q(res["cl"][2]))
        fl = res["c"][3]
        line += "   " + " ".join(n for b, n in ((1, "noise"), (2, "shape"), (4, "fm"), (8, "fm-sb"), (16, "pitch"))
                                 if fl & b)
        print(line, flush=True)
    print("worst: " + "  ".join("%s %.1e" % kv for kv in worst.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
