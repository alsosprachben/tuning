#!/usr/bin/env python3
"""The STRATOCASTER'S NECK COIL from its circuit (since 2026-11-23: IDMT-SMT-
Guitar's Stratocaster no longer read, licences.md L2) -- the load's resonance
and Q that ElectricGuitarProperties (GM 27) and patch_map's "strat" family
carry, under the same condition the Jazz Guitar was fitted in: DI, a short
cable into an instrument input.

A single coil is an inductance L with its winding's resistance Rs in series
and its own capacitance Cp across it, loaded by the guitar's controls and the
input: a second-order low-pass whose peak is the pickup's "resonance".
    f0 = 1 / (2 pi sqrt(L C)),   C = Cp + cable
    1/Q = 1/Q_load + 1/Q_coil,   Q_load = R sqrt(C/L),  Q_coil = sqrt(L/C)/Rs
    R = volume pot || tone pot (to ground through its capacitor: a short at
        the resonance, the knob full up) || the input
PUBLISHED VALUES (Zollner, Physik der Elektrogitarre, ch. 5; Lemme, The
Secrets of Electric Guitar Pickups): a vintage-wound Strat coil 2.4 H, 5.8 k,
~110 pF; 250 k volume and tone pots; a 1 M instrument input; a 3 m cable at
~100 pF/m. The coil's eddy-current loss (it lowers Q further) not modelled.

    python3 examples/strat_coil.py
"""
import math

L, RS, CP = 2.4, 5.8e3, 110e-12
CABLE = 3.0 * 100e-12
POTS = (250e3, 250e3)
INPUT = 1.0e6


def coil(L=L, Rs=RS, Cp=CP, cable=CABLE, pots=POTS, rin=INPUT):
    C = Cp + cable
    R = 1.0 / (sum(1.0 / p for p in pots) + 1.0 / rin)
    f0 = 1.0 / (2.0 * math.pi * math.sqrt(L * C))
    q_load = R * math.sqrt(C / L)
    q_coil = math.sqrt(L / C) / Rs
    return f0, 1.0 / (1.0 / q_load + 1.0 / q_coil), R, C


if __name__ == "__main__":
    f0, q, R, C = coil()
    print("load %.0f k, %.0f pF: resonance %.0f Hz, Q %.2f" % (R / 1e3, C * 1e12, f0, q))
