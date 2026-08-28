#!/usr/bin/env python3
"""Valve-and-pipe intonation for brass, from a fingering chart.

A brass instrument is a pipe of fixed length sounding a harmonic series; the
valves add fixed lengths of tubing to lower it. Both facts make it play out of
tune in specific, well-known ways, and a synthesis that tunes every note to the
temperament throws that character away.

TWO SOURCES OF DEVIATION, both physical:

1. VALVE COMBINATIONS RUN SHARP. Each valve's slide is cut to lower the OPEN
   horn by its interval. Engage two and the horn is already longer, so the same
   added length is no longer enough -- the deficit compounds. This is why 1+3
   and 1+2+3 need a trigger or a kicked slide, and why 1+2 sits sharper than 3
   alone even though both nominally lower a minor third.

2. THE HARMONIC SERIES IS NOT THE TEMPERAMENT. The 5th partial is ~14 cents
   flat of an equal-tempered major third, the 7th ~31 cents flat, the 11th
   sits between F and F#. Players lip these, but the horn's tendency is real
   and is part of why a section has a sound.

The chart below is the standard one. Given a target pitch we pick the fingering
a player would use -- the lowest harmonic that reaches it with the fewest valves
-- then compute what that tube ACTUALLY sounds, and return the difference.
"""
import math

SEMI = 2.0 ** (1.0 / 12.0)

# valve -> semitones it lowers the open horn
VALVE_DROP = {1: 2.0, 2: 1.0, 3: 3.0}

# The usable partials on each instrument, and the written pitch of partial 1.
INSTRUMENTS = {
    # B-flat trumpet: partial 2 is written C4 (sounds B-flat 3)
    "trumpet": dict(open_hz=116.54,          # B-flat 2 as partial 1 (the pedal)
                    partials=(2, 3, 4, 5, 6, 7, 8, 9, 10),
                    valves=(1, 2, 3)),
    # B-flat tuba, an octave and a half below; same valve geometry
    "tuba":    dict(open_hz=29.14,           # B-flat 0
                    partials=(2, 3, 4, 5, 6, 7, 8, 9, 10),
                    valves=(1, 2, 3, 4)),
}
# a 4th valve (tuba/euphonium) lowers a perfect fourth and exists partly TO fix
# the 1+3 / 1+2+3 problem: 4 replaces 1+3, and 2+4 replaces 1+2+3.
VALVE_DROP[4] = 5.0

# Standard combinations in the order a player prefers them.
COMBOS = [(), (2,), (1,), (1, 2), (2, 3), (1, 3), (1, 2, 3)]
COMBOS_4 = [(), (2,), (1,), (1, 2), (2, 3), (4,), (2, 4), (1, 4), (1, 2, 4), (2, 3, 4), (1, 2, 3)]


def _length_ratio(combo):
    """Tube length as a multiple of the open horn, for a valve combination.

    Each slide is cut so that ALONE it lowers the open horn by its interval:
    L_k = L0 * (2^(n/12) - 1). Engaging several just adds those same lengths --
    the instrument cannot know they are being combined. That additivity is the
    whole problem.
    """
    return 1.0 + sum(SEMI ** VALVE_DROP[v] - 1.0 for v in combo)


def fingering(target_hz, instrument="trumpet"):
    """-> (partial, combo, cents_off, sounding_hz) for the fingering a player
    would choose, or None if the note is out of range."""
    spec = INSTRUMENTS[instrument]
    combos = COMBOS_4 if 4 in spec["valves"] else COMBOS
    best = None
    for h in spec["partials"]:
        for combo in combos:
            f = spec["open_hz"] * h / _length_ratio(combo)
            cents = 1200.0 * math.log2(target_hz / f)
            # a player picks a fingering within about a semitone and lips the rest
            if abs(cents) > 60.0:
                continue
            # A player does not simply take the fewest valves: they avoid a
            # fingering that is badly out of tune when a decent alternate exists.
            # That is why the flat 7th partial is skipped in favour of 2+3 an
            # octave down, and why the 1+3 notes get the slide. Group fingerings
            # into 25-cent bands first, and only then prefer the simpler one.
            rank = (int(abs(cents) // 25), len(combo), -h)
            if best is None or rank < best[0]:
                best = (rank, h, combo, -cents, f)
    if best is None:
        return None
    _, h, combo, cents, f = best
    return h, combo, cents, f


# How much of the horn's error a player removes -- by lipping, by the third-valve
# slide, by choosing the note's placement in the embouchure. A professional in a
# classical setting corrects nearly all of it; what survives is a tendency, not
# an out-of-tune note. Keep some, or the model has no audible point.
LIP_CORRECTION = 0.80


def cents_offset(target_hz, instrument="trumpet", lip=None):
    """Residual deviation in cents after the player corrects.
    Positive = the horn still sounds sharp of the tempered pitch."""
    r = fingering(target_hz, instrument)
    if r is None:
        return 0.0
    lip = LIP_CORRECTION if lip is None else lip
    return r[2] * (1.0 - lip)
