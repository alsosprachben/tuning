#!/usr/bin/env python3
"""Does a MIDI 1.0 file render the same once carried to MIDI 2.0?

    python3 examples/midi2ident.py [SECONDS] file.mid ...

For each file: the same excerpt examples/bitident.py cuts, rendered three
ways -- as MIDI 1.0, as a MIDI Clip File and as a raw UMP stream, both made by
ump.Midi1to2 -- and the three SHA-1s compared. One line per file, "same" or
"DIFF", and a count at the end.
"""
import hashlib
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blockrender as B  # noqa: E402
import ump as U  # noqa: E402
from bitident import excerpt  # noqa: E402


def _hash(src):
    L, R = B.render(src)[:2]
    return hashlib.sha1(np.asarray(L, np.float32).tobytes()
                        + np.asarray(R, np.float32).tobytes()).hexdigest()


def main(argv):
    args = argv[1:]
    seconds = 20.0
    if args and args[0].replace('.', '', 1).isdigit():
        seconds = float(args.pop(0))
    same = 0
    for p in args:
        ex = excerpt(p, seconds)
        h1 = _hash(ex)
        hs = []
        for raw in (False, True):
            fd, tmp = tempfile.mkstemp(suffix=".ump" if raw else ".midi2"); os.close(fd)
            try:
                U.midi1_to_clip(ex, tmp, raw=raw)
                hs.append(_hash(U.UmpMidi.open(tmp)))
            finally:
                os.unlink(tmp)
        ok = hs == [h1, h1]
        same += ok
        print("%s %s%s" % ("same" if ok else "DIFF", os.path.basename(p),
                           "" if ok else "  (midi1 %s clip %s raw %s)" % (h1[:8], hs[0][:8], hs[1][:8])))
        sys.stdout.flush()
    print("%d of %d identical" % (same, len(args)))
    return 0 if same == len(args) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
