#!/usr/bin/env python3
"""Mozart, Requiem K.626, Dies Irae -- kept as a named entry point.

    python3 examples/dies_irae.py SCORE.mid [outdir] [--choir-db 7]

The work is in choral.py. This movement is worth naming for two things it
taught that pipeline. Its LilyPond export carries the lyrics per voice on
SEPARATE TRACKS with no notes on them, one per part -- so a choir cannot be
found by looking for lyrics either, only by notes AND lyrics together. And it
has no dynamics at all: every choir note is velocity 95, every first violin
101, one flat value per staff. Summed at unit gain the choir sits 6 dB under
the orchestra where they play together, which is LilyPond's opinion and not
Mozart's, and --choir-db 7 is the correction.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import choral

if __name__ == '__main__':
    argv = list(sys.argv)
    if '--lang' not in argv:
        argv += ['--lang', 'latin']
    if '--choir-db' not in argv:
        argv += ['--choir-db', '7']
    sys.exit(choral.main(argv))
