#!/usr/bin/env python3
"""A drum set built against the same set falling back, in a file's own
context, for the ear: some tracks of a window of the file (tone_ab.window:
every track's setup kept at its time), rendered with the set as
percussion_map builds it and with it removed -- what played before it was
built (Standard's instruments, or silence for a kit-only set) -- each with
the room's tail as a full render has it (tone_ab.sidecar, roomtail.py).

    python3 examples/kit_ab.py FILE.mid TRACKS START_S SECONDS OUT_DIR PROGRAM

Writes OUT_DIR/<file>_kit<PROGRAM>_{before,built}_room.wav at one common
gain (the louder's peak to -1 dB), so levels compare.
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import percussion_map as PM  # noqa: E402
import tone_ab as TA         # noqa: E402


def main(argv):
    path, tracks = argv[1], {int(v) for v in argv[2].split(',')}
    t0, secs, out, prog = float(argv[3]), float(argv[4]), argv[5], int(argv[6])
    name = os.path.splitext(os.path.basename(path))[0].lower()
    m = TA.window(path, tracks, t0, secs)
    kit, only = PM.KITS.get(prog), prog in PM.KIT_ONLY
    got = []
    try:
        for tag in ("before", "built"):
            if tag == "before":
                PM.KITS.pop(prog, None)
                PM.KIT_ONLY.discard(prog)
            else:
                if kit is not None:
                    PM.KITS[prog] = kit
                if only:
                    PM.KIT_ONLY.add(prog)
            L, R = B.render(m, "even")[:2]
            f = os.path.join(out, "%s_kit%d_%s.wav" % (name, prog, tag))
            TA.sidecar(f)
            got.append((f, np.asarray(L, float), np.asarray(R, float)))
    finally:
        if kit is not None:
            PM.KITS[prog] = kit
        if only:
            PM.KIT_ONLY.add(prog)
    pk = max(max(np.abs(l).max(), np.abs(r).max()) for _, l, r in got)
    g = 10 ** (-1 / 20.0) / pk
    k0 = int(t0 * B.SR)
    for f, l, r in got:
        B.write_wav(f, l * g, r * g)
        fr = os.path.splitext(f)[0] + "_room.wav"
        subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f, fr], check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run(["sox", fr, os.path.splitext(fr)[0] + "_cut.wav", "trim", "%.3f" % (k0 / B.SR)],
                       check=True)
        print("  %s" % (os.path.splitext(fr)[0] + "_cut.wav"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
