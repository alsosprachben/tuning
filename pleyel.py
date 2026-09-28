"""The Pleyel temperament: the traditional French aural tuning, simulated.

Not a table but a PROCEDURE, done by ear on a particular piano -- so what it
yields depends on that piano's inharmonicity. Cordier (1996, AFARP congress,
"Influence de l'inharmonicité sur les rapidités d'intervalles") shows by hand
calculation that a tuner who hits the textbook beat rates on real strings
ends up at octaves of about 2.004 and pure fifths: his equal temperament with
pure fifths. This does his calculation for the whole keyboard.

The procedure, from Cordier 1974 (G.A.M. lecture, pp. 31-32) and 1996:

  1. A3 = 220 from the fork (French LA2), and the rest of the piano from it.
  2. THE PARTITION, F3-F4 (French FA2-FA3): its thirds F-A, F#-A#, G-B, Ab-C,
     A-C#, Bb-D, B-D#, C-E, C#-F and sixths F-D, F#-D#, G-E, Ab-F are made to
     beat at the textbook rates -- those of equal temperament on HARMONIC
     strings (the thirds splitting the octave at 7, 9 and 11) -- by ear, on
     inharmonic ones. With `pleyel_sixth`, the Pleyel tradition's own mark:
     the sixth Ab-F beats like the third Db-F.
  3. UPWARD: each note makes a 10th with the note 16 below beat like that
     bass note's third ("réb3/fa3 = réb3/fa4 = réb3/fa5"); the three just
     above the partition, which have no tuned 10th below, by beatless octave.
  4. DOWNWARD: beatless octaves (the bass's 2nd partial on the note above).
     A 10th or 17th beating like the third on the SAME bass cannot tune the
     bass -- the bass's own 5th partial cancels out of the comparison, which
     is why the rule is an upward one: there it is a 4:2 octave.

A beat is heard between coinciding PARTIALS, and a stiff string's partial n
sits at n f1 sqrt((1 + B n^2) / (1 + B)). The textbook rates ignore that; the
tuner's ear does not -- which is the whole point.
"""
import math

import numpy as np
from scipy.optimize import least_squares

A3 = 57
PARTITION = range(53, 66)                                  # F3..F4
THIRDS = [(n, n + 4) for n in range(53, 62)]               # F-A .. C#-F
SIXTHS = [(53, 62), (54, 63), (55, 64), (56, 65)]          # F-D F#-D# G-E Ab-F


def partial(f1, n, b):
    return n * f1 * math.sqrt((1 + b * n * n) / (1 + b))


def et(n, a4=440.0):
    return a4 * 2 ** ((n - 69) / 12.0)


def third_rate(f, lo, B, k=1):
    """Beat of the major third (k=1), 10th (k=2) or 17th (k=4) on the bass lo:
    the bass's 5th partial against the upper note's 4/k-th... expressed as
    (upper partial) - (bass 5th partial), positive when wide."""
    hi = lo + 4 + 12 * {1: 0, 2: 1, 4: 2}[k]
    return partial(f[hi], 4 // k, B(f[hi])) - partial(f[lo], 5, B(f[lo]))


def sixth_rate(f, lo, B):
    return partial(f[lo + 9], 3, B(f[lo + 9])) - partial(f[lo], 5, B(f[lo]))


def textbook(a4=440.0):
    """The rates the tuner aims for: equal temperament on harmonic strings."""
    f = {n: et(n, a4) for n in range(0, 128)}
    zero = lambda x: 0.0
    return ({lo: third_rate(f, lo, zero) for lo, _ in THIRDS},
            {lo: sixth_rate(f, lo, zero) for lo, _ in SIXTHS})


def tune(B, a4=440.0, pleyel_sixth=True, low=21, high=108):
    """{midi: fundamental Hz} for a piano whose strings have inharmonicity B(f)."""
    t3, t6 = textbook(a4)
    f = {A3: a4 / 2.0}
    free = [n for n in PARTITION if n != A3]

    def residual(x):
        g = dict(f)
        g.update(zip(free, x))
        r = [third_rate(g, lo, B) - t3[lo] for lo, _ in THIRDS]
        for lo, _ in SIXTHS:
            target = t6[lo]
            if pleyel_sixth and lo == 56:                   # Ab-F beats like Db-F
                target = third_rate(g, 61, B)
                r.append(sixth_rate(g, lo, B) - target)
            else:
                r.append(sixth_rate(g, lo, B) - target)
        return r

    x0 = [et(n, a4) for n in free]
    sol = least_squares(residual, x0, xtol=1e-12, ftol=1e-12)
    f.update(zip(free, sol.x))

    def solve(fn, lo, hi):
        a, b = lo, hi
        for _ in range(200):
            m = (a + b) / 2
            if (fn(a) > 0) == (fn(m) > 0):
                a = m
            else:
                b = m
        return (a + b) / 2

    for n in range(66, high + 1):                          # upward
        if n - 16 in f:
            bass = n - 16
            target = third_rate(f, bass, B)                # its third, already tuned
            g = lambda x, n=n, bass=bass: (partial(x, 2, B(x)) - partial(f[bass], 5, B(f[bass]))) - target
        else:                                              # beatless octave
            g = lambda x, n=n: partial(x, 1, B(x)) - partial(f[n - 12], 2, B(f[n - 12]))
        f[n] = solve(g, et(n, a4) * 0.97, et(n, a4) * 1.03)
    for n in range(52, low - 1, -1):                       # downward, beatless octaves
        g = lambda x, n=n: partial(f[n + 12], 1, B(f[n + 12])) - partial(x, 2, B(x))
        f[n] = solve(g, et(n, a4) * 0.97, et(n, a4) * 1.03)
    return f
