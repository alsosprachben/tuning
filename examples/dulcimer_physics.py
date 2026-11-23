#!/usr/bin/env python3
"""THE DULCIMER'S STRINGS AND THEIR DECAY, FROM PHYSICS (2026-11-22; Ben: "do
1 for the strings, and physics for decay and halo"). Kemp's Pianobook takes,
the first reference, are no longer read (licences.md L7); iternetcone's
(examples/dulcimer_fit.py: C4-D5, trimmed ~40 dB down after 1-3 s) check it.

    python3 -I examples/dulcimer_physics.py            the strings, B, the loss terms
    python3 -I examples/dulcimer_physics.py [--G=0.0015] [--write]   the decay law (at G) into tonelib
    (Ben chose G = 0.0015, the long ring, of 0.00627 -- the takes' -- 0.003 and 0.0015)

THE STRINGS: Musicmakers' 17/16 kit -- its published gauges by course and its
box and bridge dimensions (examples/dulcimer_fit's sources) -- the side bridges
1" in, a wound string's core half its diameter (assumed); over its last
course (Eb5) a .016" string at that course's tension.

THE DECAY, each partial at f of a note at f0 (amplitude, nepers/s; x8.686 dB/s):
  air       Valette (1995): R = 2 pi eta_a + 2 pi d sqrt(pi eta_a rho_a f) per
            metre, alpha = R / (2 mu)
  internal  the steel's own loss factor ETA_INT (literature order, assumed):
            alpha = pi f ETA_INT
  bridge    the board's conductance G at the bridge, the same for every
            partial of the string: alpha = 2 Z0 G f0, Z0 = sqrt(T mu)
G is the one number nothing publishes: taken from the takes' early decay (each
key's fundamental band, the first 25 dB: harpsi_fit.band_decays), the only
part of the ring the trimmed takes hold. tonelib's law (by hertz: decay_db +
decay_hz_db (f/1 kHz)^decay_hz_power) is then fitted to the physics over the
whole compass, D3-F6, every partial to 8 kHz.
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

IN = 0.0254
E, RHO_S, RHO_PB = 2.0e11, 7850.0, 8800.0
ETA_A, RHO_A = 1.8e-5, 1.2
ETA_INT = 2.0e-4
GAUGES = [(.032, 1)] * 2 + [(.024, 1)] * 2 + [(.022, 0)] * 2 + [(.020, 0)] * 4 + [(.018, 0)] * 4 + [(.016, 0)] * 2
NOTES = [50, 52, 54, 55, 57, 59, 60, 62, 64, 66, 67, 69, 71, 72, 74, 75]
SIDE_INSET, CORE = 1.0, 0.5


def hz(k):
    return 440.0 * 2 ** ((k - 69) / 12.0)


def course(i):
    """(key, L m, d m, core m, mu kg/m, T N) of the bass bridge's course i"""
    g, wound = GAUGES[i]
    u = i / (len(GAUGES) - 1)
    L = (((38.0 - 2 * SIDE_INSET) - (11.5 - SIDE_INSET)) * (1 - u) + ((16.0 - 2 * SIDE_INSET) - (4.0 - SIDE_INSET)) * u) * IN
    D = g * IN
    dc = CORE * D if wound else D
    mu = math.pi / 4 * (RHO_S * dc * dc + (0.785 * RHO_PB * (D * D - dc * dc) if wound else 0.0))
    T = mu * (2 * L * hz(NOTES[i])) ** 2
    return NOTES[i], L, D, dc, mu, T


def string(key):
    """the string a key sounds on: the course at or under it; over the last, a
    .016" at that course's tension"""
    cs = [course(i) for i in range(len(GAUGES))]
    below = [c for c in cs if c[0] <= key]
    k0, L, D, dc, mu, T = below[-1] if below else cs[0]
    return D, mu, T, math.sqrt(T / mu) / (2 * hz(key))


def bass_B():
    out = []
    for i in range(len(GAUGES)):
        k, L, D, dc, mu, T = course(i)
        out.append((k, math.pi ** 3 * E * dc ** 4 / (64 * T * L * L)))
    return out


def rate(key, n, G):
    """partial n's decay, dB/s"""
    D, mu, T, L = string(key)
    f0 = hz(key)
    f = n * f0
    a_air = (2 * math.pi * ETA_A + 2 * math.pi * D * math.sqrt(math.pi * ETA_A * RHO_A * f)) / (2 * mu)
    a_int = math.pi * f * ETA_INT
    a_br = 2 * math.sqrt(T * mu) * G * f0
    return 8.686 * (a_air + a_int + a_br)


def takes_fundamental():
    import harpsi_fit as H
    import dulcimer_fit as DF
    out = {}
    for k, p in sorted(DF.recordings().items()):
        bd = H.band_decays(p, hz(k))
        if bd:
            c = min(bd, key=lambda c: abs(math.log(c / hz(k))))
            out[k] = bd[c]
    return out


def fit_G(meas):
    best = None
    for G in np.geomspace(1e-5, 1e-1, 400):
        e = float(np.sqrt(np.mean([math.log(rate(k, 1, G) / v) ** 2 for k, v in meas.items() if v > 0.5])))
        if best is None or e < best[0]:
            best = (e, G)
    return best


def fit_law(G):
    from scipy.optimize import minimize
    pts = [(n * hz(k), rate(k, n, G)) for k in range(50, 90) for n in range(1, 13) if n * hz(k) < 8000]
    f = np.array([p[0] for p in pts]); r = np.array([p[1] for p in pts])

    def err(x):
        a, b, c = x
        law = a + b * (f / 1000.0) ** c
        return float(np.sqrt(np.mean(np.log(np.maximum(law, 1e-3) / r) ** 2)))
    res = minimize(err, [5.0, 3.0, 1.0], method="Nelder-Mead", options=dict(xatol=1e-4, fatol=1e-6, maxfev=4000))
    return res.x, res.fun


def main(argv):
    print("THE BASS BRIDGE (Musicmakers 17/16): key, B")
    print("  " + "  ".join("%d:%.2e" % kb for kb in bass_B()))
    meas = takes_fundamental()
    e, G = fit_G(meas)
    print("G (the board's conductance at the bridge) %.3g s/kg: fundamentals' log-rate rms %.2f" % (G, e))
    for k, v in meas.items():
        D, mu, T, L = string(k)
        print("  %d  take %5.1f dB/s  physics %5.1f  (air %.1f, internal %.1f, bridge %.1f)" % (
            k, v, rate(k, 1, G), rate(k, 1, 0) - 8.686 * math.pi * hz(k) * ETA_INT,
            8.686 * math.pi * hz(k) * ETA_INT, rate(k, 1, G) - rate(k, 1, 0)))
    (a, b, c), le = fit_law(float(next((x.split('=')[1] for x in argv if x.startswith('--G=')), G)))
    a_, b_, c_ = a, b, c
    print("the law fitted to the physics, D3-F6, partials to 8 kHz: decay_db %.3f, decay_hz_db %.3f, "
          "decay_hz_power %.3f (log-rate rms %.2f)" % (a, b, c, le))
    for k in (50, 57, 62, 69, 74, 81, 89):
        print("  %d  physics h1-h4 %s | law %s" % (k, " ".join("%5.1f" % rate(k, n, G) for n in range(1, 5)),
                                                   " ".join("%5.1f" % (a + b * (n * hz(k) / 1000) ** c) for n in range(1, 5))))
    if "--write" in argv:
        import re
        p = os.path.join(HERE, "tonelib.py")
        src = open(p).read()
        a = src.index("class HammeredDulcimerProperties(")
        b = src.index("\nclass ", a + 10)
        body = src[a:b]
        for name, v in (("decay_db", a_), ("decay_hz_db", b_), ("decay_hz_power", c_)):
            body = re.sub(r"^    %s = .*$" % name, "    %s = %.3f" % (name, v), body, count=1, flags=re.M)
        open(p, "w").write(src[:a] + body + src[b:])
        print("written to tonelib.HammeredDulcimerProperties")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
