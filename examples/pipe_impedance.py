#!/usr/bin/env python3
"""THE ORGAN PIPE AS A RESONATOR, IN THE FREQUENCY DOMAIN: input impedance
Z(f) from the pipe's dimensions, for the flue and reed simulators
(examples/fluepipe_sim.py, reedpipe_sim.py). No recording: dimensions in,
acoustics out (the pipe organ off the Piteå set, 2026-11-24).

    python3 examples/pipe_impedance.py           the self-test against the textbook

A pipe is a chain of SECTIONS from its driven end to its far end, each a 2x2
transmission matrix in (pressure, volume flow):

  cylinder   viscothermal losses on the wall by Keefe's (JASA 75, 1984)
             series in rv = a sqrt(rho w / mu): the characteristic impedance
             and wavenumber both complex. Wood's rough bore loses more than
             tin's: WOOD_LOSS multiplies the loss terms (a named variable).
  cone       a run of short cylinders (CONE_STEPS a cone), each at its own
             radius: any bore, a flare or a reed's bell included.

and a TERMINATION at the far end:

  open       radiation from an unflanged pipe end: Levine & Schwinger's
             (1948) low-ka resistance and Norris & Sheng's end correction
             (JSV 135, 1989), going to a matched end at high ka.
  closed     a stopper: rigid.
  chimney    a stopper pierced by a small open tube (a Rohrflöte's chimney):
             the body ends in the chimney's own input impedance.

Z(f) seen from the driven end; its peaks (a reed's, driven at a closed end) or
its dips (a flue's, driven through its open mouth) are the pipe's MODES, each
a frequency, a Q and a weight (modes()): the renderer's partials.
"""
import math

import numpy as np

RHO = 1.204            # kg/m^3, air at 20 C
C = 343.2              # m/s
MU = 1.813e-5          # Pa s, air's viscosity
WOOD_LOSS = 1.6        # wood's wall loss over a smooth metal bore's (by ear: no figure found)
CONE_STEPS = 24        # cylinders a cone is built of


def keefe(w, a, loss=1.0):
    """(Zc, Gamma) of a cylinder of radius a at angular frequencies w: Keefe
    1984's large-rv series (accurate for rv > ~3, every pipe here)."""
    w = np.maximum(np.asarray(w, float), 1e-6)
    S = math.pi * a * a
    rv = a * np.sqrt(RHO * w / MU)
    iv = loss / rv
    zc = RHO * C / S * (1 + 0.369 * iv - 1j * (0.369 * iv + 1.149 * iv ** 2 + 0.303 * iv ** 3))
    gam = w / C * (1.045 * iv + 1.080 * iv ** 2 + 0.750 * iv ** 3 + 1j * (1 + 1.045 * iv))
    return zc, gam


def cylinder(L, a, wood=False):
    return ("cyl", float(L), float(a), WOOD_LOSS if wood else 1.0)


def cone(L, a_in, a_out, wood=False, steps=None):
    """A truncated cone from radius a_in (the driven side) to a_out."""
    n = steps or CONE_STEPS
    return [("cyl", L / n, a_in + (a_out - a_in) * (k + 0.5) / n, WOOD_LOSS if wood else 1.0) for k in range(n)]


def radiation(w, a):
    """An unflanged open end's impedance. At low ka Levine & Schwinger's
    resistance (ka)^2/4 and the end correction delta (Norris & Sheng's fit,
    0.6133 a at ka -> 0); toward high ka the end stops reflecting (Z -> Zc):
    z = (r + j k delta) / (1 + r + j k delta), r = (ka)^2/4, which keeps
    both limits (an approximation between them, ka ~ 1-3)."""
    w = np.asarray(w, float)
    k = w / C
    ka = k * a
    dl = a * 0.6133 * (1 + 0.044 * ka ** 2) / (1 + 0.19 * ka ** 2)
    z = 0.25 * ka ** 2 + 1j * k * dl
    zc = RHO * C / (math.pi * a * a)
    return zc * z / (1 + z)


def _flat(sections):
    out = []
    for s in sections:
        out.extend(s if isinstance(s, list) else [s])
    return out


def input_impedance(f, sections, end=("open",)):
    """Z(f) (Pa s/m^3) at the first section's driven end of the chain, the
    far end terminated by end: ("open",), ("closed",) or ("chimney", L, a)."""
    f = np.asarray(f, float)
    w = 2 * math.pi * f
    secs = _flat(sections)
    kind = end[0]
    if kind == "open":
        Z = radiation(w, secs[-1][2])
    elif kind == "closed":
        Z = np.full(w.shape, 1e15 + 0j)
    elif kind == "chimney":
        Z = input_impedance(f, [cylinder(end[1], end[2])], ("open",))
    else:
        raise ValueError(kind)
    for _, L, a, loss in reversed(secs):
        zc, g = keefe(w, a, loss)
        ch, sh = np.cosh(g * L), np.sinh(g * L)
        Z = (ch * Z + zc * sh) / (sh * Z / zc + ch)
    return Z


def modes(f, H, nmax=40):
    """The resonances of a response H(f) on the grid f: its local maxima of
    |H|, each (frequency, Q, |H| at the peak), the frequency and the -3 dB
    width by parabolic interpolation in dB."""
    m = 20 * np.log10(np.abs(H) + 1e-300)
    out = []
    for i in range(1, len(f) - 1):
        if m[i] > m[i - 1] and m[i] >= m[i + 1]:
            d = 0.5 * (m[i - 1] - m[i + 1]) / (m[i - 1] - 2 * m[i] + m[i + 1])
            fp = f[i] + d * (f[i + 1] - f[i])
            top = m[i] - 0.25 * (m[i - 1] - m[i + 1]) * d
            lo, hi = i, i
            while lo > 0 and m[lo] > top - 3.0:
                lo -= 1
            while hi < len(f) - 1 and m[hi] > top - 3.0:
                hi += 1
            bw = f[hi] - f[lo]
            out.append((fp, fp / bw if bw > 0 else float("inf"), 10 ** (top / 20)))
            if len(out) >= nmax:
                break
    return out


def selftest():
    """Against the textbook: an open-open cylinder resonates near n c / 2(L +
    2 x 0.61 a), a closed-open one at odd n near n c / 4(L + 0.61 a); a cone
    driven at its narrow, closed end (a reed's) has a complete series."""
    ok = True
    L, a = 1.2, 0.04
    f = np.linspace(20, 2000, 40000)
    # driven at an open end = the admittance's peaks (a flue sees 1/(Zmouth + Zpipe))
    Z = input_impedance(f, [cylinder(L, a)], ("open",))
    Zm = radiation(2 * math.pi * f, a)
    md = modes(f, 1 / (Z + Zm))[:4]
    want = [n * C / (2 * (L + 2 * 0.6133 * a)) for n in (1, 2, 3, 4)]
    print("open-open  %.2f m, r %.0f mm: modes %s Hz, Q %s; textbook %s Hz"
          % (L, a * 1e3, [round(m[0], 1) for m in md], [round(m[1]) for m in md], [round(x, 1) for x in want]))
    ok &= all(abs(m[0] / x - 1) < 0.012 for m, x in zip(md, want))
    Zc = input_impedance(f, [cylinder(L, a)], ("closed",))
    md = modes(f, 1 / (Zc + Zm))[:3]
    want = [n * C / (4 * (L + 0.6133 * a)) for n in (1, 3, 5)]
    print("stopped    %.2f m: modes %s Hz; textbook (odd) %s Hz"
          % (L, [round(m[0], 1) for m in md], [round(x, 1) for x in want]))
    ok &= all(abs(m[0] / x - 1) < 0.012 for m, x in zip(md, want))
    Zk = input_impedance(f, cone(1.5, 0.004, 0.06), ("open",))
    md = modes(f, Zk)[:5]
    print("cone 1.5 m (reed-driven): impedance peaks %s Hz (ratios %s)"
          % ([round(m[0], 1) for m in md], [round(m[0] / md[0][0], 2) for m in md]))
    # Q of the 8' C principal's fundamental: thermoviscous + radiation, ~30-60
    f8 = np.linspace(40, 80, 8000)
    Z8 = input_impedance(f8, [cylinder(2.30, 0.074)], ("open",))
    m8 = modes(f8, 1 / (Z8 + radiation(2 * math.pi * f8, 0.074)))[0]
    print("8' C (2.30 m, r 74 mm): %.1f Hz, Q %.0f" % (m8[0], m8[1]))
    print("ok" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(selftest())
