#!/usr/bin/env python3
"""A program's level against the rest of a file, for the ear: a window of the
whole mix (tone_ab.window: every track, each one's setup kept at its time),
rendered with the named programs -- every variation of them too -- raised by
each of several dB, with the room's tail as a full render has it
(tone_ab.sidecar, roomtail.py).

    python3 examples/level_ab.py FILE.mid START_S SECONDS OUT_DIR PROGRAMS DB,DB,...

PROGRAMS is a comma list (0-based, e.g. 29,30). The raise is on the bank's
balance (patch_map.PROGRAM_TRIM_DB / VARIATION_TRIM_DB), which is on the
channel volume -- after a voice's valve, whose reference the volume is
taken back out of -- so it is level alone, the drive unchanged. Writes
OUT_DIR/<file>_p<PROGRAMS>_<+DB>_room_cut.wav at one common gain (the
loudest's peak to -1 dB), so levels compare.
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import patch_map as PM       # noqa: E402
import tone_ab as TA         # noqa: E402


def main(argv):
    path, t0, secs, out = argv[1], float(argv[2]), float(argv[3]), argv[4]
    progs = [int(v) for v in argv[5].split(',')]
    raises = [float(v) for v in argv[6].split(',')]
    name = os.path.splitext(os.path.basename(path))[0].lower()
    import mido
    tracks = set(range(len(mido.MidiFile(path).tracks)))
    m = TA.window(path, tracks, t0, secs)
    base = {p: PM.PROGRAM_TRIM_DB.get(p, 0.0) for p in progs}
    vbase = {k: v for k, v in PM.VARIATION_TRIM_DB.items() if k[0] in progs}
    got = []
    try:
        for db in raises:
            for p in progs:
                PM.PROGRAM_TRIM_DB[p] = base[p] + db
            for k, v in vbase.items():
                PM.VARIATION_TRIM_DB[k] = v + db
            L, R = B.render(m, "even")[:2]
            f = os.path.join(out, "%s_p%s_%+.1fdB.wav" % (name, '-'.join(map(str, progs)), db))
            TA.sidecar(f)
            got.append((f, np.asarray(L, float), np.asarray(R, float)))
    finally:
        PM.PROGRAM_TRIM_DB.update(base)
        PM.VARIATION_TRIM_DB.update(vbase)
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
