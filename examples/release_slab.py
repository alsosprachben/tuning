#!/usr/bin/env python3
"""How many of live's slab slots a fast glissando holds, now that a plucked
note rings on after its note-off (gm_release.py, release_valve_time).

    python3 examples/release_slab.py [PROGRAM ...]     (default 46 107 24)

Twenty-four notes 40 ms apart, each released 50 ms after it starts, played
through Live at 48 kHz, 128-frame blocks; the peak number of slots in use
(the slab's capacity less its free list) over four seconds. Run it in a
tree before the release change (2025a06) and in one after (03f41c3):

    harp 192 -> 1756, koto 248 -> 2638, nylon guitar 230 -> 946, of 16384

The release commit's message gives 384-488 -> 1332-4166: a scratch probe
that dropped some note-offs at the multiples of 40 ms (see below), so held
notes inflated both sides. The conclusion stands, the worst case now 16 %
of the slab rather than 25.
"""
import os
import sys

import mido

sys.path.insert(0, os.getcwd())          # the tree being measured
from live import Live                    # noqa: E402


def peak(prog, rate=48000, frames=128, n=24, step_ms=40.0, hold_ms=50.0, secs=4.0):
    lv = Live(program=prog, rate=rate, frames=frames, verbose=False)
    lv.warm()
    cap = len(lv.slab.free)
    notes = [48 + 2 * i for i in range(n)]
    # EACH EVENT AT AN EXACT BLOCK, worked out once in samples. Testing "is
    # one due?" as t % 40 ms < a block let float rounding at the multiples of
    # 40 decide, and two spellings of t missed different events (the scratch
    # probe behind the release commit's figures was one of them).
    at = {}
    for i, nt in enumerate(notes):
        at.setdefault(int(round(i * step_ms * rate / 1000.0)) // frames, []).append(("note_on", nt, 100))
        at.setdefault(int(round((i * step_ms + hold_ms) * rate / 1000.0)) // frames, []).append(("note_off", nt, 0))
    top = 0
    for b in range(int(secs * rate) // frames):
        for kind, nt, v in at.get(b, ()):
            lv.on_midi(mido.Message(kind, channel=0, note=nt, velocity=v))
        lv.callback(None, frames, None, 0)
        top = max(top, cap - len(lv.slab.free))
    lv.renderer.close()
    return top, cap


if __name__ == "__main__":
    for p in [int(a) for a in sys.argv[1:]] or [46, 107, 24]:
        used, cap = peak(p)
        print("  GM %3d: peak %5d slots of %d" % (p, used, cap), flush=True)
