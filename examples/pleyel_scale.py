"""THE PLEYEL's STRINGS FROM ITS SCALE: Pleyel no. 14174 (Paris, 1847, a
demi-queue of 82 notes), its speaking lengths and wire diameters as its
owner measured them (Louchet, Registre Pleyel, entry 48, pp. 98-100,
jean.louchet.free.fr/pleyel.pdf) -- each plain string's tension
T = mu (2 L f)^2 and stiffness B = pi^3 E d^4 / (64 T L^2), iron wire
(rho 7850, E 190 GPa), at a' = 440 -- and the stiffness law
B(f) = a + b f + c f^2 + d/f + e/f^2 (InharmonicStringProperties') fitted
to them in log B. The wound bass (CC-E, no core sizes published) follows
the grand's own law's shape, joined to the plain wire's at F2.

    python3 examples/pleyel_scale.py            -> the table, the law's five numbers
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

RHO, E, A4 = 7850.0, 190e9, 440.0
# (MIDI note, speaking length mm, diameter mm): each diameter holds to the next listed
SCALE = [(41, 1387.0, 1.20), (45, 1220.0, 1.15), (47, 1135.0, 1.10), (48, 1093.0, 1.05), (50, 1006.0, 1.025),
         (54, 836.0, 1.00), (59, 643.0, 0.95), (60, 608.0, 0.95), (65, 455.5, 0.90), (69, 364.0, 0.90),
         (71, 325.5, 0.875), (79, 211.0, 0.85), (84, 160.8, 0.85), (85, 153.2, 0.825), (91, 113.3, 0.80),
         (96, 87.7, 0.80), (97, 83.4, 0.75), (105, 58.4, 0.75)]


def freq(m):
    return A4 * 2.0 ** ((m - 69) / 12.0)


def strings():
    """(note, f, L m, d m, T N, B) for each measured plain string."""
    out = []
    for m, L, d in SCALE:
        L, d, f = L / 1000.0, d / 1000.0, freq(m)
        mu = RHO * math.pi * d * d / 4.0
        T = mu * (2.0 * L * f) ** 2
        B = math.pi ** 3 * E * d ** 4 / (64.0 * T * L * L)
        out.append((m, f, L, d, T, B))
    return out


def law(f, a, b, c, d, e):
    return a + b * f + c * f * f + d / f + e / (f * f)


def fit():
    """The five numbers: the plain strings' B, and below F2 the grand's law
    scaled to meet them there."""
    import tonelib as T
    g = T.GrandPianoProperties
    gl = (g.a, g.b, g.c, g.d, g.e)
    ss = strings()
    f2 = freq(41)
    k = ss[0][5] / law(f2, *gl)
    fs = [s[1] for s in ss] + [freq(m) for m in range(21, 41, 2)]
    Bs = [s[5] for s in ss] + [k * law(freq(m), *gl) for m in range(21, 41, 2)]
    # (least squares in log B: Gauss-Newton from the grand's own law)
    p = np.array(gl, float)
    for _ in range(200):
        r = np.array([math.log(max(1e-12, law(f, *p))) - math.log(B) for f, B in zip(fs, Bs)])
        J = np.array([[x / max(1e-12, law(f, *p)) for x in (1.0, f, f * f, 1.0 / f, 1.0 / (f * f))] for f in fs])
        sc = np.abs(J).max(0)
        dp = np.linalg.lstsq(J / sc, -r, rcond=None)[0] / sc
        p = p + 0.5 * dp
    rms = math.sqrt(sum((math.log(max(1e-12, law(f, *p))) - math.log(B)) ** 2 for f, B in zip(fs, Bs)) / len(fs))
    return p, rms, k


def main():
    import tonelib as T
    g = T.GrandPianoProperties
    print("note    f Hz   L mm   d mm   T N   stress MPa   B          the grand's B")
    for m, f, L, d, Tn, B in strings():
        print("%4d %8.1f %6.1f %6.3f %5.0f %8.0f   %.3e   %.3e" % (
            m, f, L * 1000, d * 1000, Tn, Tn / (math.pi * d * d / 4) / 1e6, B, law(f, g.a, g.b, g.c, g.d, g.e)))
    ts = [s[4] for s in strings()]
    print("tension: mean %.0f N, %.0f-%.0f" % (sum(ts) / len(ts), min(ts), max(ts)))
    p, rms, k = fit()
    print("the wound bass: the grand's law x %.2f (joined at F2)" % k)
    print("law: a=%.6g b=%.6g c=%.6g d=%.6g e=%.6g  (rms %.3f in log B)" % (tuple(p) + (rms,)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
