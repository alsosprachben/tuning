#!/usr/bin/env python3
"""A dynamics ladder on an electric piano: each key at v40, v64, v96, v127,
low to high, so how much soft and loud differ -- in level and in buzz -- is
heard rather than read. Renders each setting given, one after another.

    python3 examples/ep_dynamics.py OUT.wav [--program=4] [--keys=36,43,48]
            [--set=level_swing_share=0,level_swing_share=0.5]

Each --set entry is one pass, the class attribute set for it (the class is
the program's); the passes are separated by a second of silence. Cabinet on,
dry, peak-normalised over the whole file so the passes keep their levels
against each other.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import upright_fit as U

VELS = (40, 64, 96, 127)


def ladder(program, keys, note_s=0.9):
    out = []
    for k in keys:
        for v in VELS:
            y, sr = U.render(program, k, v, note_s)
            t0 = U.onset(y, sr)
            out.append(y[t0:t0 + int(1.1 * sr)])
    return np.concatenate(out), sr


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__.strip())
        return 2
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    program = int(opts.get("program", 4))
    keys = [int(k) for k in opts.get("keys", "36,43,48").split(",")]
    sets = opts.get("set", "level_swing_share=0").split(",")
    import patch_map as PM
    import tonelib as T
    from roomtail import write_wav
    cls = PM.property_class_for_program(program)
    parts = []
    for s_ in sets:
        k, v = s_.split("=")
        was = getattr(cls, k)
        setattr(cls, k, float(v))
        T._EP_PICKUP_CACHE.clear()
        x, sr = ladder(program, keys)
        setattr(cls, k, was)
        parts += [x, np.zeros(sr)]
    x = np.concatenate(parts)
    x = 0.5 * x / max(np.abs(x).max(), 1e-12)
    write_wav(args[0], np.stack([x, x], 1), sr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
