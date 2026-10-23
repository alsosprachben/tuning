#!/usr/bin/env python3
"""A drum set's A/B pairs as one reel: for each note in order, the take, a
short gap, ours, a longer gap -- written as WAV and MP3 (lame) beside the
pairs. The pairs are the NN_TAG.wav / NN_ours.wav files a fit script's
--wav=DIR writes (examples/tr808_fit.py write_wavs), each already cut to
1.6 s and peaked at -6 dB. The reel holds the takes: keep it local.

    python3 examples/ab_reel.py DIR TAG          e.g. ~/Music/tr909/ab 909
"""
import os
import re
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

GAP_S, PAIR_GAP_S = 0.35, 1.0


def trim(x, sr, floor_db=-60.0):
    """Cut a hit's silent end (its 1.6 s window outlasts most of them)."""
    e = np.abs(x)
    keep = np.flatnonzero(e > e.max() * 10 ** (floor_db / 20.0))
    return x[:keep[-1] + int(0.02 * sr)] if len(keep) else x


def main(argv):
    d, tag = os.path.expanduser(argv[1]), argv[2]
    notes = sorted(int(m.group(1)) for f in os.listdir(d)
                   for m in [re.match(r"(\d+)_%s\.wav$" % re.escape(tag), f)] if m)
    out, sr = [], None
    for n in notes:
        for name in ("%d_%s.wav" % (n, tag), "%d_ours.wav" % n):
            r, x = wavfile.read(os.path.join(d, name))
            sr = sr or r
            out.append(trim(x.astype(float) / 32768.0, r))
            out.append(np.zeros(int(GAP_S * r)))
        out[-1] = np.zeros(int(PAIR_GAP_S * sr))
    y = np.concatenate(out)
    base = os.path.join(os.path.dirname(d.rstrip("/")), "ab_reel_%s" % tag)
    wavfile.write(base + ".wav", sr, (y * 32767).astype(np.int16))
    subprocess.run(["lame", "--quiet", "-V2", base + ".wav", base + ".mp3"], check=True)
    print("  %s.mp3: notes %s, take then ours" % (base, " ".join(map(str, notes))))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
