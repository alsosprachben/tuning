#!/usr/bin/env python3
"""The worst blocks of nvlive --test runs, side by side:

    python3 examples/blocktimes.py LABEL=FILE[,FILE...] [LABEL=FILE...] [--block-ms=2.667]

Each FILE is what NV_BLOCK_TIMES=FILE wrote (nvlive --test: one line a
block, its whole time and its render's, ms). A click is one late block, so
the mean says little: this prints, per label and over all its runs pooled,
the mean, the slowest 1%, 0.1% and 0.01%, the worst, and how many blocks
ran over the block's own length -- for the whole block and for the render.
Run the cases being compared interleaved (A B A B ...), so a warm machine
or a background job falls on both.
"""
import sys

import numpy as np


def main():
    blk = 1000.0 * 128 / 48000
    groups = []
    for a in sys.argv[1:]:
        if a.startswith("--block-ms="):
            blk = float(a.split("=", 1)[1])
            continue
        lab, files = a.split("=", 1)
        groups.append((lab, files.split(",")))
    if not groups:
        print(__doc__)
        return 2
    print("%-14s %7s %8s %8s %8s %8s %8s %8s  (ms; block %.3f ms)" % ("", "blocks", "mean", "p99", "p99.9", "p99.99",
                                                                     "worst", "over", blk))
    for lab, files in groups:
        d = np.concatenate([np.loadtxt(f, ndmin=2) for f in files])
        for col, what in ((0, "block"), (1, "render")):
            x = d[:, col]
            q = np.percentile(x, [99, 99.9, 99.99])
            print("%-14s %7d %8.3f %8.3f %8.3f %8.3f %8.3f %8d" % ("%s %s" % (lab, what), len(x), x.mean(), q[0], q[1],
                                                                   q[2], x.max(), int((x > blk).sum())))
        worst = [np.loadtxt(f, ndmin=2)[:, 0].max() for f in files]
        print("%-14s each run's worst: %s" % ("", " ".join("%.2f" % w for w in worst)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
