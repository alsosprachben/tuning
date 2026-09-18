#!/usr/bin/env python3
"""Buxtehude, Passacaglia in D minor BuxWV 161 -- as one long crescendo.

    python3 examples/buxwv161.py SCORE.mid [outdir]

A passacaglia is not registered once and played. It is built: the organist
starts on the Positiv and adds through the piece, so the ostinato that opens
almost inaudibly is thundering by the close. BWV 582 is played this way by
everybody, and so is this.

The structure does the scheduling. The pedal states its 7-note ostinato 28
times, in four groups of seven, transposed D - F - A - D, each statement
10.9 seconds:

    D  var  1   1.8 s      A  var 15  170.9 s
    F  var  8  86.4 s      D  var 22  255.5 s

Registration changes go AT THE KEY CHANGES, which is where an organist puts
them -- F major is the first brightening -- plus one at the four-voice chordal
transition into the final section. Nothing is ever taken away, which is what
makes it a crescendo rather than a sequence of registrations.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import organ

# The seams, taken from the ostinato and from the texture.
#
# CHANGES GO AT THE KEY CHANGES. That is where an organist puts them, and the
# structure is built for it: the ostinato states itself 28 times in four groups
# of seven, transposed D - F - A - D. Changing inside a group instead puts a
# stop in the middle of a statement, which is the one place it never goes.
KEY = {'D1': 1.8, 'F': 86.4, 'A': 170.9, 'D2': 255.5}

# ...with one addition that is not a key change. Four-voice quarter-note chords
# arrive at 249.5 s and run to the D return -- measured, 4.1 voices at 487 ms,
# the steadiest stacked writing in the piece. It is a cadenza made of weight
# rather than of runs, and it is the approach to the final section, so the
# blaze starts there and arrives rather than switching on at the double bar.
WALL = 249.5
LAST = 320.9          # the 28th and final statement
LEAD = 0.35           # speaking BY the downbeat, not arriving during it


def at(t):
    return max(0.0, t - LEAD)


PLAN = {
    # manual flue
    0: [(0.0,           ['flute']),                              # Positiv
        (at(KEY['F']),  ['8', '4']),                             # first brightening
        (at(KEY['A']),  ['8', '4', '2', '2-2/3']),
        (at(WALL),      ['8', '4', '2', '2-2/3', 'mixture']),
        (at(KEY['D2']), ['8', '4', '2', '2-2/3', '16', '5-1/3', 'mixture'])],
    # pedal flue
    1: [(0.0,           ['8']),
        (at(KEY['F']),  ['16', '8']),
        (at(KEY['A']),  ['16', '8', '4']),
        (at(KEY['D2']), ['16', '8', '4', '5-1/3'])],
    # pedal reed: the weight, entering with the wall
    2: [(0.0,           []),
        (at(WALL),      ['16']),
        (at(KEY['D2']), ['16', '8'])],
    # manual reed: the last statement only
    3: [(0.0,           []),
        (at(LAST),      ['trumpet'])],
}


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip()); return 2
    score = argv[1]
    outdir = argv[2] if len(argv) > 2 else '.'
    os.makedirs(outdir, exist_ok=True)
    graded = os.path.join(outdir, 'buxwv161_graded.mid')
    lib.set_stops(score, graded, PLAN)
    return organ.main([argv[0], graded, outdir])


if __name__ == '__main__':
    sys.exit(main(sys.argv))
