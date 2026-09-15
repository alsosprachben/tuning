#!/usr/bin/env python3
"""Mozart, Requiem K.626, Lacrimosa -- kept as a named entry point.

    python3 examples/lacrimosa_choir.py SCORE.mxl [outdir] [--choir-only] [--both]

The work is all in choral.py; this movement is only notable for the shape of
its engraving. The MusicXML export carries thirteen tracks: four EMPTY staves
named Treble/Alto/Tenor/Bass, four string parts, and four more named
Soprano/Alto/Tenor/Bass that hold the notes and the lyrics. Selecting parts by
name gets the empty ones, which is why the choir is found by having notes AND
lyrics instead.
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
        argv += ['--choir-db', '4']
    sys.exit(choral.main(argv))
