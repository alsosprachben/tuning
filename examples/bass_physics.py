#!/usr/bin/env python3
"""The ELECTRIC BASS'S STRING from physics (since 2026-11-23: IDMT-SMT-Bass
no longer read, licences.md L3) -- every note's harmonics' decay rates
computed, then the class's decay law fitted to them.

The losses are lapsteel_physics's (Issanchou et al., JSV 2017 / JASA 2018:
air, visco-elastic, thermo-elastic -- its WOUND figures are a wound steel
BASS string's -- and Pate, Le Carrou & Fabre's +1.3 dB/s for a solid body's
mounting). THE INSTRUMENT: a 34" scale (864 mm), a standard nickel roundwound
set, .045 .065 .080 .100 (G2 D2 A1 E1), all wound: the core 0.40 of the gauge
and the mass 0.78 of solid steel's (lapsteel_physics' assumption; it gives
the G 180 N, 40 lb, a 045's usual tension). Each note on its lowest fret, as
ElectricGuitarProperties places it: a fretted note is the shorter string at
the open string's tension. The STRETCH is not from here: a wound string's
stiffness needs its core, which no maker publishes -- its partials'
frequencies are read from recordings instead (a recording gives those up
whatever the rig).

THE LOSSES STRING PHYSICS ALONE MISSES (Ben: "what if you added physics
for those parts into the model?"): alone, it decays the strings ~3x slower
than two open basses measure (h1 1.5-2 dB/s against 4-7). Zollner (Physics
of the Electric Guitar, 7.7) names both: the BEARINGS -- each reflection at
nut or fret and bridge loses 4 W G of the wave's power (W = sqrt(T mu), G the
bearing's conductance, ~0.001 s/kg: "about 1% ... for the E1-string on an
electric bass"), the same dB/s for every partial -- and the WOUND string's
own losses, core, winding and the friction between them, which a solid
cylinder's visco-elastic figure understates. Both fitted (--fit) to the
open basses' partial decays, each at its own scale and fret: G, and the
winding's visco-elastic loss.

    python3 examples/bass_physics.py          the rates and the law
    python3 examples/bass_physics.py --fit    G and the winding's loss, from the open basses
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

from lapsteel_physics import rates  # noqa: E402

SCALE = 0.8636
STRINGS = ((41.20, 0.100), (55.00, 0.080), (73.42, 0.065), (98.00, 0.045))   # (open Hz, gauge in)
# THE CORES, from the stretch: B = pi^3 E d_c^4 / (64 T L^2) set against 107
# notes' measured B on the two open basses (their medians per string agree:
# E 0.21-0.23 of the gauge, A 0.28-0.29, D 0.32-0.43, G 0.41) -- about the
# same wire, ~0.021", under every string, as a bass set is made: the heavier
# strings carry more winding, not more core
CORES = (0.0214, 0.0224, 0.0211, 0.0186)                                    # (inches)
FRETS = 12
NM = 8                                   # partials per note, as egtr_fit's decays()
REF_HZ = 415.0


def notes():
    """(sounding Hz, open Hz, gauge, fret) for every note E1 to G3, each on
    its lowest fret."""
    out = []
    for k in range(0, 12 * 2 + 3 + 1):
        f = 41.20 * 2 ** (k / 12.0)
        under = [s for s in STRINGS if s[0] <= f * 1.0001]
        o, g = max(under)
        fret = 12.0 * np.log2(f / o)
        if fret <= FRETS + 1e-6:
            out.append((f, o, g, fret))
    return out


G_BEARINGS = 9.3e-4           # s/kg, the two bearings together AT THE NUT (--fit: Zollner's typical 0.001)
# (both fitted to nil on the two open basses -- a constant G fits them best,
# 0.39 |log err| against 0.49-0.61 with any fall by frequency -- and kept:
# a neck held stiffer at its joint, or a mass-like one, is a player's choice)
G_FALL = 0.0                  # how fast the neck's conductance falls toward the joint
G_FREQ_EXP = 0.0              # ...and with frequency, (f/100 Hz)^-q
NECK_JOINT = 0.53             # the body joint, a fraction of the scale from the nut (the 13th fret)
BODY_SHARE = 0.1              # the conductance left at the joint: the body and bridge
DVE_WOUND = 0.0346            # the winding's visco-elastic loss (--fit; Issanchou's single string 0.01)
OPEN_SETS = (("open_qt_gretsch", 0.7696, (3, 4, 5, 6)), ("open_fp_rbx_finger", SCALE, None),
             ("open_fp_rbx_pick", SCALE, None))     # (set, its scale in m, velocities used)


def measured():
    """Every open bass note's partial decays (egtr_fit.decays, h1-h8, dB/s),
    with its string, fret and scale -- cached in the scratch MODEL folder."""
    import glob
    import re
    import egtr_fit as E
    from voicefit import note_of
    cache = os.path.join(E.MODEL, "bass_open_decays.npy")
    if os.path.exists(cache):
        return list(np.load(cache, allow_pickle=True))
    out = []
    for name, L, vels in OPEN_SETS:
        for p in sorted(glob.glob(os.path.join(E.STAGED, name, "*.wav"))):
            g = re.search(r"\.s(\d)f(\d+)(?:\.v(\d+))?", os.path.basename(p))
            st, fret = int(g.group(1)), int(g.group(2))
            if vels and int(g.group(3)) not in vels:
                continue
            f = 440.0 * 2 ** ((note_of(p) - 69) / 12.0)
            out.append((name, f, st, fret, L, np.asarray(E.decays(p), float)))
    os.makedirs(E.MODEL, exist_ok=True)
    np.save(cache, np.array(out, dtype=object), allow_pickle=True)
    return out


def bearing_g(fret, G_nut, p, joint=NECK_JOINT):
    """THE NECK'S CONDUCTANCE WHERE THE NOTE IS STOPPED (Fleischer & Zwicker;
    Zollner 7.7.4.4): largest at the nut, falling toward the body joint where
    the neck is held -- as the distance to the joint, (1 - x/joint)^p, x the
    fret's distance from the nut as a fraction of the scale; at and past the
    joint the body's own (G_nut's floor share, BODY_SHARE). The bridge's,
    small on a solid body, is in the floor."""
    x = 1.0 - 2.0 ** (-fret / 12.0)
    return G_nut * (BODY_SHARE + (1.0 - BODY_SHARE) * max(1.0 - x / joint, 0.0) ** p)


def bearing_gf(fret, G_nut, p, q):
    """...and BY FREQUENCY: above its own bending modes a neck moves like a
    mass, its conductance falling with frequency (Zollner 7.7.4.4, the Les
    Paul's nut: the peaks aside, the floor falls) -- (f/100 Hz)^-q."""
    g0 = bearing_g(fret, G_nut, p)
    return lambda nu: g0 * (nu / 100.0) ** (-q)


def predicted(f, st, fret, L, G, dve, p=0.0, q=0.0):
    o, g = STRINGS[st - 1]
    return rates(f, g, True, nh=NM, L=L * 2 ** (-fret / 12.0), dve=dve, G=bearing_gf(fret, G, p, q),
                 core=CORES[st - 1])[0]


def fit():
    from scipy.optimize import minimize
    rows = measured()

    def err(x, show=False):
        G, dve = np.exp(x[:2])
        p, q = float(x[2]), float(x[3])
        if p < 0.0 or q < -1.0 or q > 3.0:
            return 10.0 + abs(p)
        e, by = [], {}
        for name, f, st, fret, L, D in rows:
            P = predicted(f, st, fret, L, G, dve, p, q)
            ok = np.isfinite(D) & (D > 0.2)
            d = np.log(D[ok]) - np.log(P[ok])
            e.extend(d)
            if show:
                by.setdefault((name, int(np.log2(f / 32.70))), []).append((D, P))
        if show:
            for k in sorted(by):
                v = by[k]
                print("  %-20s oct %d (%2d) measured %s | model %s" % (
                    k[0], k[1] + 1, len(v),
                    " ".join("%5.1f" % q for q in np.nanmedian([a[0] for a in v], 0)[:6]),
                    " ".join("%5.1f" % q for q in np.median([a[1] for a in v], 0)[:6])))
        return float(np.median(np.abs(e)))
    # (from the constant G's fit, the fall in its own units: it may be nil)
    x0 = np.array([np.log(9.3e-4), np.log(0.0227), 0.0, 0.0])
    e0 = err(np.array([np.log(1e-12), np.log(0.01), 0.0, 0.0]))
    e1 = err(x0)
    r = minimize(err, x0, method="Nelder-Mead", options=dict(xatol=1e-3, fatol=1e-4, maxfev=600, initial_simplex=np.vstack(
        [x0, x0 + [0.5, 0, 0, 0], x0 + [0, 0.5, 0, 0], x0 + [0, 0, 1.0, 0], x0 + [0, 0, 0, 0.8]])))
    G, dve = np.exp(r.x[:2])
    p, q = float(r.x[2]), float(r.x[3])
    print("  %d notes: median |log err| %.2f (string physics alone %.2f; G constant along the neck %.2f)"
          % (len(rows), r.fun, e0, e1))
    print("    G_BEARINGS = %.3g   (s/kg at the nut and 100 Hz, both bearings)\n    G_FALL = %.3g\n"
          "    G_FREQ_EXP = %.3g\n    DVE_WOUND = %.3g" % (G, p, q, dve))
    err(r.x, show=True)
    return G, dve, p, q


def law():
    from scipy.optimize import least_squares
    pts = []
    for f, o, g, fret in notes():
        c = CORES[[s_[0] for s_ in STRINGS].index(o)]
        r, T = rates(f, g, True, nh=NM, L=SCALE * 2 ** (-fret / 12.0), dve=DVE_WOUND,
                     G=bearing_gf(fret, G_BEARINGS, G_FALL, G_FREQ_EXP), core=c)
        pts.extend((m, f, d / 2.0) for m, d in enumerate(r, 1))
    m = np.array([q[0] for q in pts], float)
    f = np.array([q[1] for q in pts]); D = np.array([q[2] for q in pts])

    def res(q):
        a, b, sl = q
        return np.log(np.maximum(a + b * m, 1e-6)) + sl * np.log(f / REF_HZ) - np.log(D)
    r = least_squares(res, [2.0, 1.0, 0.0], bounds=([0.0, 0.0, -1.0], [100.0, 50.0, 3.0]),
                      loss="soft_l1", f_scale=0.3)
    return r.x, float(np.median(np.abs(res(r.x)))), len(pts)


if __name__ == "__main__":
    if "--fit" in sys.argv:
        fit()
        sys.exit(0)
    for o, g in STRINGS:
        r, T = rates(o, g, True, nh=NM, L=SCALE)
        print("  open %5.1f Hz  .%03d  T %5.1f N (%4.1f lb)  h1-h%d dB/s: %s"
              % (o, round(g * 1000), T, T / 4.448, NM, " ".join("%4.1f" % v for v in r)))
    (a, b, sl), e, n = law()
    print("  the class's law over %d partials (halved, (a + b m)(f0/415)^s; median |log err| %.2f):" % (n, e))
    print("    decay_db = %.4g\n    harmonic_decay_db = %.4g\n    decay_register_slope = %.4g" % (a, b, sl))
