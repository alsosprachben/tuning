#!/usr/bin/env python3
"""Fade by DISTANCE rather than by volume.

An amplitude fade scales a source and its share of the room together, so it
gets quieter while staying exactly as present -- a player told to play softer.
A source that actually recedes loses its DIRECT sound with distance while
feeding the room the same power, because the reverberant field depends on what
is radiated and not on where it is radiated from. So it goes quieter,
RELATIVELY WETTER, and duller as the air takes its top. That is what "lost in
the distance" sounds like, and it is the soloforward.py mechanism run
backwards.

    out = band + g(t)*receding_direct        + tail(band + receding)
                 ^^^^ direct falls, top rolls  ^^^^ room keeps its power

Written for the end of Neptune, where Holst asks for a chorus "repeated until
it is lost in the distance" -- an instruction about where the singers are, not
about how loudly they sing.

Usage: recede.py BAND.wav RECEDING.wav OUT.wav START_S END_S END_DB
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from roomtail import read_wav, write_wav

# Where the top ends up. Crude against ISO 9613-1, which the renderer uses
# per partial, but this is acting on a finished stem and the audible part of
# receding is that the air has taken the top, not the exact slope.
END_HZ_DECADES = 1.1
START_HZ = 18000.0


def main(argv):
    if len(argv) < 7:
        print(__doc__.strip().splitlines()[-1])
        return 2
    band, sr = read_wav(argv[1])
    receding, sr2 = read_wav(argv[2])
    outp = argv[3]
    t0, t1, end_db = float(argv[4]), float(argv[5]), float(argv[6])
    if sr != sr2:
        print("sample rates differ: %d vs %d" % (sr, sr2))
        return 1

    n = min(len(band), len(receding))
    band, receding = band[:n], receding[:n]
    t = np.arange(n) / float(sr)

    # Direct sound falls with distance: 1/d in amplitude.
    frac = np.clip((t - t0) / max(t1 - t0, 1e-6), 0.0, 1.0)
    g = 10.0 ** (frac * end_db / 20.0)

    # A one-pole whose corner closes along the same ramp. Time-varying, so it
    # is a genuine per-sample recurrence and cannot be vectorised away.
    fc = START_HZ * (10.0 ** (frac * -END_HZ_DECADES))
    alpha = 1.0 - np.exp(-2.0 * math.pi * fc / sr)
    out_ch = []
    for c in range(receding.shape[1]):
        x = receding[:, c] * g
        y = np.empty_like(x)
        prev = 0.0
        for i in range(len(x)):
            prev += alpha[i] * (x[i] - prev)
            y[i] = prev
        out_ch.append(y)

    out = band + np.stack(out_ch, axis=1)
    write_wav(outp, out, sr)
    print("  recedes %.1f->%.1f s, direct %+.0f dB, top rolled to %.0f Hz"
          % (t0, t1, end_db, START_HZ * (10.0 ** -END_HZ_DECADES)))
    print("  peak %.3f -> %s" % (np.abs(out).max(), outp))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
