#!/usr/bin/env python3
"""Does the GPU file renderer render what the CPU renders?

    python3 examples/gpu_filecheck.py [--seconds 20] [--window 32] [--where] FILE.mid [...]

--where prints the sample of each file's largest difference and the partials
sounding there.

Each file's first SECONDS (bitident's excerpt, notes closed at the cut) is
prepared once and its partials rendered twice: by synth_partials on the CPU,
in block-aligned windows (see below), and by gpurender.FileRenderer. Printed per file:
the difference relative to the CPU's peak (best-fit gain, as the live
selftests measure it, and the plain maximum), and both kernels' times.
"""
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
import blockrender as B                                 # noqa: E402
import gpurender as G                                   # noqa: E402
from bitident import excerpt                            # noqa: E402


def main(argv):
    seconds, window = 20.0, 32
    where = "--where" in argv
    argv = [x for x in argv if x != "--where"]
    for opt in ("--seconds", "--window"):
        if opt in argv:
            i = argv.index(opt)
            v = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
            if opt == "--seconds":
                seconds = float(v)
            else:
                window = int(v)
    gpu = G.Gpu()
    worst = 0.0
    print("%-24s %9s  %8s %8s   %8s %8s" % ("file", "partials", "rel max", "rel fit", "cpu s", "gpu s"))
    for f in argv[1:]:
        prep = B.prepare(excerpt(f, seconds), "hybridmean:440")
        N, P = prep['N'], prep['P']
        # the CPU in windows of whole blocks, as the GPU and live take them
        # (since blockrender._chunk the CPU's own chunks are too; before it, a
        # block a one-second chunk edge fell in was set up in two halves)
        L = np.zeros(N, np.float32); R = np.zeros(N, np.float32)
        t0 = time.time()
        W = B.BLK * (B.SR // B.BLK)
        for n0 in range(0, N, W):
            w = min(W, N - n0)
            a_ = np.zeros(w, np.float32); b_ = np.zeros(w, np.float32)
            B.synth_partials(prep, n0, w, 0, P, a_, b_)
            L[n0:n0 + w] = a_; R[n0:n0 + w] = b_
        tc = time.time() - t0
        t0 = time.time()
        gL, gR, _, _ = G.FileRenderer(prep, gpu, window_blocks=window).render(N)
        tg = time.time() - t0
        a = np.concatenate([L, R]).astype(float)
        b = np.concatenate([gL, gR]).astype(float)
        pk = max(float(np.abs(a).max()), 1e-30)
        rmax = float(np.abs(b - a).max()) / pk
        g = float(np.dot(a, b) / max(np.dot(b, b), 1e-30))
        rfit = float(np.sqrt(np.mean((g * b - a) ** 2)) / max(np.sqrt(np.mean(a ** 2)), 1e-30))
        worst = max(worst, rmax)
        print("%-24s %9d  %8.1e %8.1e   %8.2f %8.2f" % (os.path.basename(f), P, rmax, rfit, tc, tg), flush=True)
        if where:
            # WHERE the two part: the sample of the largest difference, and the
            # partials sounding there -- by their size at that sample's block
            k = int(np.argmax(np.abs(b - a)))
            ear, n = ("L", k) if k < N else ("R", k - N)
            print("   largest at %.4f s (sample %d, block %d +%d, %s): CPU %.3e GPU %.3e"
                  % (n / B.SR, n, n // B.BLK, n % B.BLK, ear, a[k], b[k]))
            non, noff = np.asarray(prep["non"]), np.asarray(prep["noff"])
            amp = np.maximum(np.abs(np.asarray(prep["aL"])), np.abs(np.asarray(prep["aR"])))
            act = np.flatnonzero((non <= n + B.BLK) & (noff + np.asarray(prep["re"]) >= n - B.BLK))
            top = act[np.argsort(-amp[act])][:12]
            for j in top:
                print("     row %7d  nf %8.1f Hz  amp %.2e  non %.4f s  fade %5.0f  cbw %+.3f  logr %+.1f  mk %d"
                      % (j, prep["nf"][j], amp[j], non[j] / B.SR, prep["fa"][j], prep["cbw"][j],
                         prep["logr"][j], prep["mk"][j]))
    print("worst %.1e" % worst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
