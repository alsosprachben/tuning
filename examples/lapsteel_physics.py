#!/usr/bin/env python3
"""The LAP STEEL's decay from string physics (since 2026-11-22: the Pianobook
Lapsteel Articulations takes no longer read, licences.md L7) -- each open string's
harmonics' decay rates computed, then the class's decay law fitted to them.

THE STRING'S OWN LOSSES (Issanchou, Bilbao, Le Carrou, Touze, Doare, JSV 2017,
s2.3.1; JASA 143(5) 2018, eqs. A4-A5), per partial at frequency nu:
    1/Q_air = R / (2 pi mu nu),   R = 2 pi eta + 2 pi d sqrt(pi eta rho nu)
    1/Q_ve  = 4 pi^2 mu E I delta_ve nu^2 / T^2   (wound: the core's E I only)
    1/Q_te  = constant
  plain steel: delta_ve 4.5e-3, 1/Q_te 2.03e-4 (a D'Addario electric string)
  wound:       delta_ve 0.01,   1/Q_te 6e-6     (a wound steel bass string),
               the air term on d_eq = (pi/2)((1 + 2/pi) 2 r_wind + 2 r_core)
  air:         eta 1.8e-5 kg/(m s), rho 1.2 kg/m^3
THE MOUNTING: a solid body adds a little -- Pate, Le Carrou & Fabre (JASA
135(5) 2014): the same open G3 decays in T30 7.7 s on a solid-body guitar
(their Fig. 12) against ~11.5 s on a rigid frame (Fig. 5, Q ~2100 at 196 Hz):
+1.3 dB/s, taken as one rate for every partial.
THE INSTRUMENT: GHS LAP-E (E tuning 013-056: .013 .017 .024 plain, .032 .042
.056 wound), open E2 B2 E3 G#3 B3 E4, Fender's 22.5" scale (572 mm). Wound
strings: the core 0.40 of the gauge (hex core), the mass 0.78 of solid
steel's at the gauge.

    python3 examples/lapsteel_physics.py          the rates, ours, and the fit
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

L = 0.5715
RHO_STEEL, E_STEEL = 7850.0, 2.0e11
ETA, RHO_AIR = 1.8e-5, 1.2
MOUNT_DBS = 1.3
INCH = 0.0254
# (note, f0, gauge in inches, wound)
STRINGS = (("E2", 82.41, 0.056, True), ("B2", 123.47, 0.042, True), ("E3", 164.81, 0.032, True),
           ("G#3", 207.65, 0.024, False), ("B3", 246.94, 0.017, False), ("E4", 329.63, 0.013, False))
DB = 20.0 / np.log(10.0)


def rates(f0, gauge, wound, nh=12):
    """dB/s of h1..nh (the amplitude's decay)."""
    d = gauge * INCH
    if wound:
        dc = 0.40 * d
        mu = 0.78 * RHO_STEEL * np.pi * d * d / 4.0
        rw, rc = (d - dc) / 4.0, dc / 2.0
        d_air = (np.pi / 2.0) * ((1.0 + 2.0 / np.pi) * 2.0 * rw + 2.0 * rc)
        EI = E_STEEL * np.pi * rc ** 4 / 4.0
        dve, qte = 0.01, 6e-6
    else:
        mu = RHO_STEEL * np.pi * d * d / 4.0
        d_air = d
        EI = E_STEEL * np.pi * (d / 2.0) ** 4 / 4.0
        dve, qte = 4.5e-3, 2.03e-4
    T = mu * (2.0 * L * f0) ** 2
    out = []
    for k in range(1, nh + 1):
        nu = k * f0
        R = 2 * np.pi * ETA + 2 * np.pi * d_air * np.sqrt(np.pi * ETA * RHO_AIR * nu)
        iq = R / (2 * np.pi * mu * nu) + 4 * np.pi ** 2 * mu * EI * dve * nu ** 2 / T ** 2 + qte
        out.append(DB * np.pi * nu * iq + MOUNT_DBS)
    return np.array(out), T


def main(argv):
    import pluck_fit as P
    import tonelib as T_
    P.PROG, P.CLS, P.BANK = 26, "HawaiianGuitarProperties", 8
    C = T_.HawaiianGuitarProperties
    targets = []
    for n, f0, g, w in STRINGS:
        r, T = rates(f0, g, w)
        targets.append((f0, r))
        print("  %-3s %6.1f Hz  T %5.1f N  physics h1-h12 dB/s: %s" % (n, f0, T, " ".join("%4.1f" % v for v in r)))

    def mono(y):
        y = np.asarray(y, float)
        return y.mean(1) if y.ndim > 1 else y

    def err(show=False):
        e = []
        for f0, R in targets:
            y, sr = P.render(f0, 6.0)
            O = P.measure(mono(y), sr, f0)[0][:12]
            ok = np.isfinite(O)
            e.extend((O - R)[ok])
            if show:
                print("        ours %6.1f Hz: %s" % (f0, " ".join("%4.1f" % v for v in O)))
        return float(np.sqrt(np.mean(np.square(e))))
    print("as it stands: %.2f dB/s rms" % err(True))
    if "--fit" not in argv:
        return 0
    from scipy.optimize import minimize
    keys = ("decay_db", "harmonic_decay_db", "decay_register_slope")
    x0 = np.array([float(getattr(C, k)) for k in keys])
    best = [1e9, x0]

    def f(z):
        v = np.array([x0[0] * np.exp(z[0]), x0[1] * np.exp(z[1]), x0[2] + z[2]])
        for k, q in zip(keys, v):
            setattr(C, k, float(q))
        e = err()
        if e < best[0]:
            best[:] = [e, v]
            print("  %5.2f dB/s  %s" % (e, " ".join("%s=%.4g" % kv for kv in zip(keys, v))), flush=True)
        return e
    minimize(f, np.zeros(3), method="Nelder-Mead",
             options={"maxfev": 50, "initial_simplex": np.vstack([np.zeros(3), np.diag([0.5, 0.7, 0.3])]),
                      "xatol": 0.02, "fatol": 0.05})
    for k, q in zip(keys, best[1]):
        setattr(C, k, float(q))
        print("    %s = %.4g" % (k, q))
    err(True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
