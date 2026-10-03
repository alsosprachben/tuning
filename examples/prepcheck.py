#!/usr/bin/env python3
"""prepare()'s memos must not change one bit of the partial table.

    python3 examples/prepcheck.py FILE.mid [FILE.mid ...] [--tuner hybridmean:440]

Each file is prepared twice -- with blockrender.PREP_MEMO on and off -- and
every array of the two tables compared by its SHA-1; the times are printed.
A memo keyed on less than its function reads shows up here as arrays that
differ (the first early-reflection memo, keyed on id(), moved 6% of Mars's
partial levels by 0.2%).
"""
import hashlib
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import blockrender as B                                 # noqa: E402


def main(argv):
    tuner = "hybridmean:440"
    if "--tuner" in argv:
        i = argv.index("--tuner")
        tuner = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    bad = 0
    for f in argv[1:]:
        tabs, dts = [], []
        for memo in (False, True):
            B.PREP_MEMO = memo
            B.PREP_MEMO_STATS[:] = [0, 0, 0]
            t0 = time.time()
            p = B.prepare(f, tuner)
            dts.append(time.time() - t0)
            # a fingerprint per array, not the table: two tables of a long
            # piece at once ran a 7 GB machine out of memory
            tabs.append({k: hashlib.sha1(v.tobytes()).hexdigest()
                         for k, v in p.items() if isinstance(v, np.ndarray)})
            P = p['P']
            del p
        a, b = tabs
        diff = sorted(k for k in a if a[k] != b.get(k))
        bad += bool(diff)
        look, miss, emptied = B.PREP_MEMO_STATS
        print("%-28s P=%-8d %6.1fs -> %6.1fs  hits %4.1f%% (emptied %d)  %s" % (
            os.path.basename(f), P, dts[0], dts[1], 100.0 * (look - miss) / max(look, 1), emptied,
            "identical" if not diff else "DIFFERS: " + " ".join(diff)), flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
