#!/usr/bin/env python3
"""TWO CHAINS, ANY BRIDGE (tunelib.ChainsTuner, `chains/<bridge>@<start>`)
against the proved model's test vectors (tuning-lean docs/clavitone-
sequencer.md, section 7; HybridMean.lean, Baroque.lean, Semitones.lean),
measured from the tables the engines play -- the native engine's, which
examples/tuner_check.py holds identical to Python's.

    python3 examples/chains_check.py

Each chain position's fifth and third, and the twelve semitones, read from
the octave C4-B4 of the table (pure octaves: every octave the same), to
1e-6 cents; the sums (thirds 4800, fifths 8400); the good-thirds count
against the proved ceiling floor(4 pyth / (synt - t)); the key the card
offers (the start's fourth fifth up) has its I, IV and V thirds pure on the
5:4 bridge. Exit 1 on the first miss.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import native as N  # noqa: E402

NAMES = ["c", "c#", "d", "eb", "e", "f", "f#", "g", "ab", "a", "bb", "b"]
P = 1200.0 * math.log2(1.5)
L = 1200.0 * math.log2(1.25)
PYTH = 12 * P - 7 * 1200.0
SYNT = 1200.0 * math.log2(81.0 / 80.0)
TOL = 1e-6
bad = 0


def table_cents(spec):
    t = N.tuning_table(spec, reference=(69, 440.0))
    return {n: 1200.0 * math.log2(t[n] / t[60]) for n in range(60, 84)}


def at(start, k):
    """chain position k's pitch class, chain one from start"""
    return (start + 7 * k) % 12


def fifth(c, pc):
    return c[60 + pc + 7] - c[60 + pc]


def third(c, pc):
    return c[60 + pc + 4] - c[60 + pc]


def expect(what, got, want):
    global bad
    ok = abs(got - want) <= TOL
    if not ok:
        bad += 1
    print("  %-38s %12.6f  want %12.6f  %s" % (what, got, want, "ok" if ok else "MISS"))


def model(spec, start, fifths, thirds, good=None, t=None):
    c = table_cents("chains/%s@%s" % (spec, NAMES[start]))
    print("chains/%s@%s" % (spec, NAMES[start]))
    for k, want in fifths.items():
        expect("fifth %d (on %s)" % (k, NAMES[at(start, k)]), fifth(c, at(start, k)), want)
    for ks, want in thirds:
        for k in ks:
            expect("third %d (on %s)" % (k, NAMES[at(start, k)]), third(c, at(start, k)), want)
    expect("thirds' sum", sum(third(c, p) for p in range(12)), 4800.0)
    expect("fifths' sum", sum(fifth(c, p) for p in range(12)), 8400.0)
    if good is not None:
        n = sum(1 for p in range(12) if third(c, p) <= L + t + TOL)
        ceiling = math.floor(4 * PYTH / (SYNT - t))
        expect("good thirds (t = %.4f)" % t, n, good)
        expect("  their proved ceiling", ceiling, good)
    return c


def main():
    mean3 = 1200.0 * math.log2(math.sqrt(1.25 * 81 / 64))
    # Romantic Meantone (X = mean3), chain one from C
    model("mean", 0, {5: 691.201856, 11: 689.248135},
          [((2, 3, 4, 5), 397.066859), ((8, 9, 10, 11), 395.113138), ((0, 1, 6, 7), 407.820003)],
          good=8, t=SYNT / 2)
    # Baroque (X = L), rotated to B-flat
    c = model("pure", 10, {}, [((2, 3, 4, 5), 386.313714), ((8, 9, 10, 11), 405.866283), ((0, 1, 6, 7), 407.820003)],
              good=4, t=0.0)
    for name, pc in (("C", 0), ("G", 7), ("D", 2), ("A", 9)):
        expect("third on %s (pure)" % name, third(c, pc), 386.313714)
    # the key the card names for a start: its fourth fifth up -- B-flat's G, whose I, IV, V thirds are the bridge's
    key = at(10, 3)
    expect("the card's key for B-flat (G = 7)", key, 7)
    for deg in (0, 5, 7):
        expect("  %s's third (degree %d)" % (NAMES[(key + deg) % 12], deg), third(c, (key + deg) % 12), L)
        expect("  %s's fifth" % NAMES[(key + deg) % 12], fifth(c, (key + deg) % 12), P)
    # Baroque's semitones: 5 x 135/128, 5 x 16/15, 2 x 256/243
    semis = sorted(round(c[60 + p + 1] - c[60 + p], 6) for p in range(12))
    want = sorted([1200 * math.log2(135 / 128)] * 5 + [1200 * math.log2(16 / 15)] * 5 + [1200 * math.log2(256 / 243)] * 2)
    for g, w in zip(semis, want):
        expect("semitone", g, w)
    # Stretched Helmholtz on pure octaves (X = helmX)
    model("helm", 0, {11: 701.955001, 5: 678.494990}, [((2, 3, 4, 5), 384.359993)])
    # Romantic Meantone's semitones: 5 x 102.93, 5 x 100.98, 2 x 90.22 (to the spec's two places)
    c = table_cents("chains/mean")
    semis = sorted(c[60 + p + 1] - c[60 + p] for p in range(12))
    for g, w in zip(semis, sorted([102.93] * 5 + [100.98] * 5 + [90.22] * 2)):
        global bad
        ok = abs(g - w) < 0.005
        bad += not ok
        print("  %-38s %12.6f  want %9.2f     %s" % ("semitone (mean)", g, w, "ok" if ok else "MISS"))
    # the named bridges are the numbers, and hybridmean is chains/mean at 415
    for nm, x in (("helm", 6000 - 8 * P), ("pure", L), ("mean", mean3), ("pyth", 1200 * math.log2(81 / 64))):
        expect("chains/%s's bridge D-F#" % nm, third(table_cents("chains/" + nm), 2), x)
    # THE MIRROR (HomeKey.lean rotate_six): bridge X rotated six fifths is bridge 792.179997 - X
    mid = (3600.0 - 4 * P) / 2
    expect("the mirror's sum 3o - 4P", 2 * mid, 792.179997)
    for X in (384.36, 386.3137, 390.0, 395.2, 396.0):
        a, b = table_cents("chains/%r" % X), table_cents("chains/%r@f#" % (2 * mid - X))
        # (chain one from F# is the C chain rotated six fifths: the same notes, each the same interval)
        worst = max(max(abs(fifth(a, p) - fifth(b, p)), abs(third(a, p) - third(b, p))) for p in range(12))
        expect("mirror of %g: worst fifth/third off" % X, worst, 0.0)
    # the midpoint: both gap fifths 690.224996, thirds 2-5 and 8-11 all 396.089998
    model("mid", 0, {5: 690.224996, 11: 690.224996}, [((2, 3, 4, 5, 8, 9, 10, 11), 396.089998)])
    # the key rule: G starts on B-flat, bridge C-E; A starts on C, bridge D-F#
    for key, start, lo, hi in ((7, 10, 0, 4), (9, 0, 2, 6)):
        expect("key %s: start" % NAMES[key], (key - 21) % 12, start)
        expect("  bridge's lower note", at(start, 2), lo)
        expect("  bridge's upper note", at(start, 6), hi)
    # home_key, for G on any bridge: I, IV, V, iii, vi on pure fifths; six chords' major thirds X; ii's fifth the gap
    for spec in ("helm", "pure", "395.5", "mid"):
        c = table_cents("chains/%s@bb" % spec)
        X = c[60 + 4] - c[60]           # (C-E, the bridge)
        for nm, pc in (("I G", 7), ("IV C", 0), ("V D", 2), ("iii B", 11), ("vi E", 4)):
            expect("%s: %s's fifth" % (spec, nm), fifth(c, pc), P)
        for nm, pc in (("G", 7), ("C", 0), ("D", 2), ("A (ii's: A-C#)", 9)):
            expect("%s: third on %s" % (spec, nm), third(c, pc), X)
        for nm, lo in (("e (G-B)", 7), ("b (D-F#)", 2), ("a (C-E)", 0)):
            expect("%s: minor %s's major third" % (spec, nm), third(c, lo), X)
        expect("%s: ii (A)'s fifth, short by (4P - 2o) - X" % spec, P - fifth(c, 9), (4 * P - 2400) - X)
    # good thirds at tolerance synt/2: 395.0 -> 4, 395.2 -> 8, 396.09 -> 8, 397.0 -> 8, 397.2 -> 4
    for X, n in ((395.0, 4), (395.2, 8), (396.09, 8), (397.0, 8), (397.2, 4), (395.113138, 8), (397.066859, 8)):
        c = table_cents("chains/%r" % X)
        expect("good thirds at X = %g" % X, sum(1 for p in range(12) if third(c, p) <= L + SYNT / 2 + TOL), n)
    # a key step G -> D, X pure (start B-flat -> F), from G: B-flat +1.953721, E +21.506290, the rest still
    g, d = table_cents("chains/pure@bb"), table_cents("chains/pure@f")
    for pc in range(12):
        mv = (d[60 + pc] - d[67]) - (g[60 + pc] - g[67])
        expect("G -> D: %s moves" % NAMES[pc], mv, {10: 1.953721, 4: 21.506290}.get(pc, 0.0))
    hm = N.tuning_table("hybridmean", reference=(69, 415.0))
    cm = N.tuning_table("chains/mean", reference=(69, 415.0))
    expect("hybridmean = chains/mean (worst key, Hz)", max(abs(hm[n] - cm[n]) for n in range(128)), 0.0)
    # on a piano's octaves (no proofs: the construction's) -- the hybrid mean's generator made general
    # ...each of the old Clavitone tunings an exact variant (its key, bridge, octaves and route), at its own A
    for old, var in (("hybridmeanpiano", "chains/mean/piano@c"), ("hybrid440", "chains/pure/piano/fourth@bb"),
                     ("hybrid", "chains/pure/piano/fourth@bb:415"), ("stretchedhelmholtz", "chains/helm/piano/octaves@c"),
                     ("hybridharm440", "chains/pure/middle/fourth@bb"), ("hybridharm", "chains/pure/middle/fourth@bb:415"),
                     ("hybridmean", "chains/mean@c:415")):
        a, b = N.tuning_table(old, reference=None), N.tuning_table(var, reference=None)
        expect("%s = %s (worst key, Hz)" % (old, var), max(abs(a[n] - b[n]) for n in range(128)), 0.0)
    # EACH INSTRUMENT's OWN OCTAVES: the classes with strings of their own are
    # the same by Python's test (tunelib.chain_law_token: a piano) and by what
    # the engine sees (nv_class_law_token: kind 0, a dynamic B, law 0-2, the
    # hammer model) -- over every class
    import inspect
    import tonelib as TO
    import tunelib as TU
    odd = []
    for _, c in inspect.getmembers(TO, inspect.isclass):
        if not hasattr(c, 'inharmonicity_dynamic'):
            continue
        try:
            k = N.kit_drum(c)
        except Exception:
            continue
        seen = bool(k == 0 and c.inharmonicity_dynamic and N._b_law(c) in (0, 1, 2) and getattr(c, 'hammer_model', None))
        if seen != (TU.chain_law_token(c) is not None):
            odd.append(c.__name__)
    expect("classes the two tests see differently (%s)" % ",".join(odd[:3]), len(odd), 0)
    print("chains: %s" % ("all as proved" if not bad else "%d MISSED" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
