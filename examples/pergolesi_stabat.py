#!/usr/bin/env python3
"""Pergolesi, Stabat Mater P.77 -- all twelve movements, sung in Latin.

    python3 examples/pergolesi_stabat.py CORPUS [outdir] [--only 1,5] [--choir-db 9]

CORPUS is the DCML annotated corpus (github.com/DCMLab/pergolesi_stabat_mater,
CC BY-NC-SA 4.0): one MuseScore 3 file per movement in CORPUS/MS3, Soprano and
Alto with their Latin text on the notes, and a PIANO reduction of the strings
and continuo -- a vocal score, not the full score.

Each movement goes through the MuseScore CLI to MIDI (lyrics as meta events,
which is what the choir pipeline reads), then choral.py: the voices through
the tract, the piano through blockrender, the hall once over both.

THE BALANCE. The export keeps the score's dynamics, and on a keyboard
reduction that leaves two soloists 4 dB UNDER the piano where they sing
(movement 1, measured). --choir-db 9 puts them where the Mozart choir was set
by ear, about +5 dB over the rest: the same forces-against-accompaniment
target, not a new number.
"""
import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import choral  # noqa: E402


def slug(path):
    """'01. Stabat Mater dolorosa.mscx' -> '01_stabat_mater_dolorosa'."""
    b = os.path.splitext(os.path.basename(path))[0]
    n, _, name = b.partition('. ')
    return n + '_' + '_'.join(name.lower().replace(',', '').split())


def to_midi(mscx, dest):
    if os.path.exists(dest) and os.path.getmtime(dest) > os.path.getmtime(mscx):
        return dest
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    subprocess.run(['musescore', '-o', dest, mscx], check=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dest


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip()); return 2
    corpus = argv[1]
    outdir = argv[2] if len(argv) > 2 and not argv[2].startswith('--') else '.'
    only = None
    if '--only' in argv:
        only = {int(x) for x in argv[argv.index('--only') + 1].split(',')}
    db = argv[argv.index('--choir-db') + 1] if '--choir-db' in argv else '9'
    os.makedirs(outdir, exist_ok=True)
    for mscx in sorted(glob.glob(os.path.join(corpus, 'MS3', '*.mscx'))):
        num = int(os.path.basename(mscx).split('.')[0])
        if only and num not in only:
            continue
        mid = to_midi(mscx, os.path.join(outdir, slug(mscx) + '.mid'))
        print("== %s" % os.path.basename(mscx))
        choral.main(['choral.py', mid, outdir, '--lang', 'latin', '--choir-db', db])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
