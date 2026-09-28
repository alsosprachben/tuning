#!/usr/bin/env python3
"""Every number in temperament.md, recomputed.

    python3 examples/cordier.py

Cordier's equal temperament with pure fifths, Ben's equal Pythagorean, the
hybrid family and hybridmean -- the identities, the inharmonicity, the beat
rates and the interval tempering, from one place, so the notes cannot drift
from the arithmetic.

Partials of a stiff string: partial n of a note whose FUNDAMENTAL (partial 1)
is f1 sits at  n f1 sqrt((1 + B n^2) / (1 + B)).  B(f) is the renderer's
grand-piano curve (tonelib.GrandPianoProperties), which is the same Steinway
fit path.py uses.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import tonelib
import tunelib
import inharmonicity as ih

PURE5 = 1200 * math.log2(1.5)
COMMA = 12 * PURE5 - 8400                        # Pythagorean
c = lambda r: 1200 * math.log2(r)
H = lambda f: 0.0
_gp = tonelib.GrandPianoProperties(261.6, 0, 1, 1)
STEINWAY = _gp.inharmonicity_coefficient_for_frequency


def partial(f1, n, B):
    b = B(f1)
    return n * f1 * math.sqrt((1 + b * n * n) / (1 + b))


def bisect(g, lo, hi, it=200):
    for _ in range(it):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if g(lo) * g(m) > 0 else (lo, m)
    return (lo + hi) / 2


def section(t):
    print('\n== %s' % t)


def equivalence():
    section('1. Equal Pythagorean = Cordier: pure fifths, octave stretched by comma/7')
    s = ih.stretch_interval
    print('octave %.4f c (+%.4f = comma/7 = %.4f); semitone %.4f c; fifth %.4f c (pure %.4f)'
          % (c(2 * s), c(2 * s) - 1200, COMMA / 7, c(2 * s) / 12, 7 * c(2 * s) / 12, PURE5))
    steps = sorted(c(r) % c(2 * s) for r in tunelib.StretchTuner.intervals.values())
    print('the Pythagorean chain folded by that octave, its 11 steps:',
          ' '.join('%.3f' % (b - a) for a, b in zip(steps, steps[1:])))
    print('B that gives this stretch by octave alignment: on the 2nd partial %.6f, on the 3rd %.6f'
          % (ih.inharmonicity_coefficient_2nd_harmonic, ih.inharmonicity_coefficient_3rd_harmonic))


def cordier_1994():
    section('2. Cordier 1994, table 12 (Steinway D): fifth FA3-DO4 (F4-C5) = 1.50053, beating -0.29/s')
    F = 348.952

    def ratio(B, beats):
        return bisect(lambda m: partial(F * m, 2, B) - partial(F, 3, B) - beats, 1.49, 1.51)
    for label, B in (('harmonic', H), ('Steinway B(f)', STEINWAY)):
        print('%-14s B(F4)=%.5f B(C5)=%.5f  beatless %.5f  at -0.29/s %.5f'
              % (label, B(F), B(F * 1.5), ratio(B, 0), ratio(B, -0.29)))
    b = bisect(lambda m: ratio(lambda f: m, -0.29) - 1.50053, 0.0, 0.01)
    print('constant B reproducing 1.50053: %.5f' % b)


def pleyel():
    section('3. The Pleyel rule: sixth Ab3-F4 against third Db4-F4 (beats per second)')
    F4 = 349.228

    def beats(s, B):
        Ab, Db = F4 * s ** -9, F4 * s ** -4
        return partial(F4, 3, B) - partial(Ab, 5, B), partial(F4, 4, B) - partial(Db, 5, B)

    def equal_beating(B):
        return bisect(lambda s: (lambda a, b: a - b)(*beats(s, B)), 1.055, 1.066)

    def beatless_fifths(B):
        return bisect(lambda s: partial(F4, 2, B) - partial(F4 * s ** -7, 3, B), 1.058, 1.062)
    rows = (('equal temperament', 2 ** (1 / 12.), H),
            ('Cordier, harmonic', 1.5 ** (1 / 7.), H),
            ('Cordier, Steinway (beatless)', beatless_fifths(STEINWAY), STEINWAY),
            ('equal beating, harmonic', equal_beating(H), H),
            ('equal beating, Steinway', equal_beating(STEINWAY), STEINWAY))
    print('%-30s %7s %7s %6s %9s %9s' % ('', 'sixth', 'third', 'ratio', 'octave', 'fifth'))
    for name, s, B in rows:
        a, b = beats(s, B)
        print('%-30s %7.2f %7.2f %6.3f %+8.2fc %+8.2fc' % (name, a, b, a / b, c(s ** 12) - 1200,
                                                          c(s ** 7) - PURE5))
    print('closed form: sixth/third = 3/4 (1 + d4/d3); equal when the fourth is widened by 1/3 of the third')
    for name, s in (('ET', 2 ** (1 / 12.)), ('Cordier', 1.5 ** (1 / 7.))):
        d3, d4 = 4 * c(s) - c(1.25), 5 * c(s) - c(4 / 3.)
        print('  %-8s d3 %+.2f c  d4 %+.2f c  ->  %.3f' % (name, d3, d4, 0.75 * (1 + d4 / d3)))


def tempering():
    section('4. Tempering at the coinciding partials, from C4 (cents)')
    iv = (('2nd', 2, 9, 8), ('m3', 3, 6, 5), ('M3', 4, 5, 4), ('4th', 5, 4, 3),
          ('5th', 7, 3, 2), ('M6', 9, 5, 3), ('8ve', 12, 2, 1))
    print('%-26s' % '' + ''.join('%8s' % n for n, *_ in iv))
    for name, s, B in (('ET, harmonic', 2 ** (1 / 12.), H), ('Cordier, harmonic', 1.5 ** (1 / 7.), H),
                       ('ET, Steinway', 2 ** (1 / 12.), STEINWAY),
                       ('Cordier, Steinway', 1.5 ** (1 / 7.), STEINWAY)):
        lo = 261.63
        print('%-26s' % name + ''.join('%+8.2f' % c(partial(lo * s ** k, m, B) / partial(lo, n, B))
                                      for _, k, n, m in iv))
    section('5. Masking: second-inversion F major C4-F4-A4, Cordier on Steinway strings')
    s, lo = 1.5 ** (1 / 7.), 261.63
    C, F, A = lo, lo * s ** 5, lo * s ** 9
    for name, a, n, b, m in (('fourth C-F', C, 4, F, 3), ('third F-A', F, 5, A, 4), ('sixth C-A', C, 5, A, 3)):
        print('  %-11s %.2f beats/s' % (name, abs(partial(a, n, STEINWAY) - partial(b, m, STEINWAY))))


def chains():
    section('6. Two chains of pure fifths bridged D-F# by a third X (pure octaves)')
    names = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
    for label, X in (('pure 5:4 (hybrid)', c(1.25)), ('mean of 5:4 and 81:64 (hybridmean)',
                                                     c(math.sqrt(1.25 * 81 / 64.))), ('ET 400', 400.0)):
        p = {}
        for i, n in enumerate((0, 7, 2, 9, 4, 11)):
            p[n] = (i * PURE5) % 1200
        p[6] = (p[2] + X) % 1200
        p[1] = (p[6] + PURE5) % 1200
        for i, n in enumerate((8, 3, 10, 5), 1):
            p[n] = (p[1] + i * PURE5) % 1200
        d = lambda a, b: (p[b] - p[a]) % 1200
        gaps = ['%s%+.2f' % (names[i], d(i, (i + 7) % 12) - PURE5) for i in range(12)
                if abs(d(i, (i + 7) % 12) - PURE5) > 0.01]
        dev = [p[i] - 100 * i for i in range(12)]
        m = sum(dev) / 12
        rms = math.sqrt(sum((x - m) ** 2 for x in dev) / 12)
        thirds = [d(i, (i + 4) % 12) - c(1.25) for i in range(12)]
        print('%-36s X=%.2f  gaps %s  thirds %+.1f..%+.1f (mean %+.2f)  rms from ET %.1f'
              % (label, X, ' '.join(gaps), min(thirds), max(thirds), sum(thirds) / 12, rms))
    print('any closed 12-note tuning, pure octaves: mean major third = %+.2f c (ET), mean fifth = %+.3f c'
          % (400 - c(1.25), -COMMA / 12))


if __name__ == '__main__':
    equivalence()
    cordier_1994()
    pleyel()
    tempering()
    chains()
