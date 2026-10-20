#!/usr/bin/env python3
"""An A/B of one GS effect on a file: the same excerpt rendered with the effect
and without it (its environment switch off), for the ear.

    python3 examples/gs_effect_ab.py FILE.mid OUT_DIR SWITCH [SECONDS] [TUNER]

SWITCH is the environment variable that turns the effect off when "0" -- e.g.
TUNING_GS_DELAY -- or several, comma-separated, flipped together. Writes OUT_DIR/<name>_on.wav and _off.wav (44.1 kHz), the
excerpt cut as bitident cuts it (notes closed at the cut).
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import bitident as BI     # noqa: E402
import blockrender as B   # noqa: E402


def main(argv):
    path, out, switch = argv[1], argv[2], argv[3]
    secs = float(argv[4]) if len(argv) > 4 else 40.0
    tuner = argv[5] if len(argv) > 5 else "even"
    name = os.path.splitext(os.path.basename(path))[0]
    m = BI.excerpt(path, secs)
    for tag, val in (("on", "1"), ("off", "0")):
        for sw in switch.split(","):
            os.environ[sw] = val
        L, R = B.render(m, tuner)[:2]
        B.write_wav(os.path.join(out, "%s_%s.wav" % (name, tag)), L, R)
        print("  %s %s" % (name, tag))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
