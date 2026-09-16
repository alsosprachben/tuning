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
Mozart's, and --choir-db is the correction.

That correction is 10, arrived at by matching the Lacrimosa rather than by
picking a number: the two movements are the same forces in the same hall, so
once one balance is right by ear the other should measure like it. 7 put the
median at +1.8 dB where the Lacrimosa sits at +5.1, and the quiet choral
writing at -7.5 where the Lacrimosa has -3.5. 10 gives +4.8 and -4.5.
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
        argv += ['--choir-db', '10']
    sys.exit(choral.main(argv))
