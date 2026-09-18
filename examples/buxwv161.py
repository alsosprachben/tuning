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
them, plus one at the four-voice chordal transition into the final section.
Nothing is ever taken away, which is what makes it a crescendo rather than a
sequence of registrations.

THE FIRST BRIGHTENING ADDS NOTHING. D minor is a stopped flute over a stopped
pedal; F major moves BOTH to the principal 8'. No rank is drawn -- a stopped
pipe and an open one are different sounds at the same pitch and the same
count, so the change of colour IS the change. Everything after that is
accumulation, and it can be because this step was not.

THE OPENING PEDAL IS THE STOPPED RANK, and the reason is measurable. A stopped
pipe has no even harmonics: on D2 its second partial is 132 dB down, so it is
very nearly the fundamental alone, which is what a Positiv registration wants
under it. The open principal is the opposite -- a full series with the second
only 6 dB down -- and the church's two first-order images land destructively
on that second partial (0.469 and 0.200, so 1 - 0.669 = -9.6 dB) and take it
out. What is left is a strong fundamental, no second, and a third at -9 dB,
which is within a decibel of the REED's own spectrum. Ben heard the opening
pedal as a reed and it was one, in every way that a spectrum can be.
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
# WHERE IN THE BAR A STOP IS DRAWN, and it is not a matter of taste.
#
# Drawing a stop while a note is held makes that note louder -- which is what
# a real organ does too, and is why an organist changes between notes. At
# 0.35 s before the downbeat, which is where this used to sit, EIGHT notes of
# the previous variation were still sounding and ended a quarter-second later:
# the old section's last chord swelled and stopped. Ben heard it as "the last
# note gets suddenly loud".
#
# Measured across the seams, anything from -100 ms to +50 ms catches ZERO
# held notes; -200 ms and earlier catches eight. The texture never rests --
# four voices minimum, all the way through -- so there is no silence to change
# in, only the instant where the old chord has released and the new has not
# yet spoken. 50 ms before the downbeat is inside that window and still leaves
# the controller ahead of the note-ons it applies to.
LEAD = 0.05


def at(t):
    return max(0.0, t - LEAD)


PLAN = {
    # manual flue
    0: [(0.0,           ['flute']),                              # Positiv
        (at(KEY['F']),  ['8']),                                  # first brightening
        (at(KEY['A']),  ['8', '4', '2', '2-2/3']),
        (at(WALL),      ['8', '4', '2', '2-2/3', 'mixture']),
        (at(KEY['D2']), ['8', '4', '2', '2-2/3', '16', '5-1/3', 'mixture'])],
    # pedal flue
    1: [(0.0,           ['flute']),                             # stopped, not open
        (at(KEY['F']),  ['8']),                                  # principal, with the manual
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
