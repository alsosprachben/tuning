#!/usr/bin/env python3
"""What a held chord on a Moog voice costs live, per 128-frame block.

    python3 examples/moog_cpu.py [GM ...] [--notes N]

For each program (default the Moog pads), N notes (default 8) are struck and
held, and the live callback is timed over a few seconds of blocks once the
swells are up. The budget at 48 kHz is 2.67 ms a block; a pad holds chords
under the damper, so this is the load it actually asks for. Run it with
nothing else playing -- it measures this machine, not the code alone.
"""
import os
import sys
import time

import mido
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import live as L

CHORD = [36, 48, 55, 60, 64, 67, 72, 76, 79, 84, 88, 91]


def bench(prog, notes, rate=48000, frames=128):
    lv = L.Live(program=prog, rate=rate, frames=frames, verbose=False)
    lv.warm()
    for n in CHORD[:notes]:
        lv.on_midi(mido.Message("note_on", channel=0, note=n, velocity=100))
    for _ in range(int(1.5 * rate / frames)):       # let the swells arrive
        lv.callback(None, frames, None, 0)
    ts = []
    for _ in range(int(3.0 * rate / frames)):
        t0 = time.perf_counter()
        lv.callback(None, frames, None, 0)
        ts.append((time.perf_counter() - t0) * 1e3)
    parts = sum(len(v) for v in lv.slab.live.values())
    lv.shutdown()
    ts = np.asarray(ts)
    return parts, float(np.median(ts)), float(np.percentile(ts, 99)), 1e3 * frames / rate


def main(argv):
    args = argv[1:]
    notes = 8
    if '--notes' in args:
        i = args.index('--notes'); notes = int(args[i + 1]); del args[i:i + 2]
    progs = [int(a) for a in args] or [50, 51, 89, 90, 94, 95, 97]
    for prog in progs:
        parts, med, p99, budget = bench(prog, notes)
        print("GM %3d  %d notes  %5d partials  median %.2f ms  p99 %.2f ms  (budget %.2f)"
              % (prog, notes, parts, med, p99, budget), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
