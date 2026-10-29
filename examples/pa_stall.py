#!/usr/bin/env python3
"""Does PortAudio stop calling a stream with none of our code in it?

    python3 examples/pa_stall.py [--secs=600] [--frames=128] [--busy=1.5,4.5] [--cycle=30] [--spawn=S]

A bare PyAudio output stream (silence) whose callback only spins for a random
1.5-4.5 ms -- live's piano callbacks, which overrun their 2.7 ms slot one time
in ten -- into a null PipeWire sink made for it (nothing reaches the
speakers), for --secs. Prints every gap between callbacks over 1 s as it
happens, and a summary.

Why: live went silent for ~6-15 s every few minutes (2026-10-28/29), each time
after ordinary callbacks -- PortAudio's ALSA backend polling in 3 ms steps,
recovering only after 2048 timeouts (pa_linux_alsa.c, PaAlsaStream_
WaitForFrames). If this bare stream stalls too, the fault is under us
(PortAudio 19.6 / pipewire-alsa), not in live.
"""
import os
import random
import subprocess
import sys
import time

SINK = "tuning_pastall"


def child(secs, frames, busy, cycle, spawn=0.0):
    import pyaudio
    pa = pyaudio.PyAudio()
    ts = []
    rnd = random.Random(3)
    out = b"\0" * (frames * 8)

    def cb(a, n, ti, st):
        ts.append(time.perf_counter())
        t = time.perf_counter() + rnd.uniform(*busy)
        while time.perf_counter() < t:
            pass
        return (out, pyaudio.paContinue)

    t0 = time.perf_counter()
    kids = []
    gaps = []
    opens = 0
    while time.perf_counter() - t0 < secs:
        # A FRESH STREAM EACH CYCLE: live's stalls came 3-16 s after its
        # stream opened, so the first seconds are sampled again and again
        s = pa.open(format=pyaudio.paFloat32, channels=2, rate=48000, output=True,
                    frames_per_buffer=frames, stream_callback=cb)
        opens += 1
        del ts[:]
        s.start_stream()
        tc = time.perf_counter()
        nxt = tc + spawn
        while time.perf_counter() - tc < cycle and time.perf_counter() - t0 < secs:
            time.sleep(0.25)
            if spawn and time.perf_counter() > nxt:
                # A PROCESS STARTED BESIDE THE STREAM, as live starts its
                # workers (multiprocessing 'spawn': fork, then exec)
                nxt += spawn
                import multiprocessing as mp
                pr = mp.get_context("spawn").Process(target=time.sleep, args=(0.5,), daemon=True)
                pr.start()
                kids.append(pr)
        s.stop_stream(); s.close()
        g = [b - a for a, b in zip(ts, ts[1:])]
        for k, x in enumerate(g):
            if x > 1.0:
                print("  gap %.2f s, %.1f s after stream %d opened" % (x, ts[k] - tc, opens), flush=True)
        gaps.extend(g)
    pa.terminate()
    g = gaps
    big = [x for x in g if x > 1.0]
    print("spawned %d processes" % len(kids))
    print("frames %d, %.0f s, %d streams of %g s: %d callbacks, %d gaps over 1 s%s, longest %.3f s"
          % (frames, secs, opens, cycle, len(g) + opens, len(big),
             (" (%s s)" % ", ".join("%.1f" % x for x in big)) if big else "", max(g)), flush=True)


def main(argv):
    opt = dict(a.split("=", 1) for a in argv[1:] if a.startswith("--") and "=" in a)
    secs = float(opt.get("--secs", 600))
    frames = int(opt.get("--frames", 128))
    busy = tuple(float(x) / 1000.0 for x in opt.get("--busy", "1.5,4.5").split(","))
    if "--child" in argv:
        child(secs, frames, busy, float(opt.get("--cycle", 30)), float(opt.get("--spawn", 0)))
        return 0
    mod = subprocess.run(["pactl", "load-module", "module-null-sink", "sink_name=" + SINK],
                         capture_output=True, text=True)
    if mod.returncode != 0:
        print("no null sink: %s" % mod.stderr.strip())
        return 1
    try:
        env = dict(os.environ, PIPEWIRE_ALSA='{ target.object = "%s" }' % SINK)
        subprocess.run([sys.executable, os.path.abspath(__file__), "--child"] + argv[1:],
                       env=env, stderr=subprocess.DEVNULL)
    finally:
        subprocess.run(["pactl", "unload-module", mod.stdout.strip()], capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
