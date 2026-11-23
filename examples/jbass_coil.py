#!/usr/bin/env python3
"""THE JAZZ BASS'S PICKUPS from their circuit (since 2026-11-23: IDMT-SMT-
Bass no longer read, licences.md L3) -- the load's resonance and Q that
ElectricBassProperties (GM 33) and patch_map's "jbass" family carry, in the
condition the guitars were set in (examples/strat_coil.py): DI, a 3 m cable
into a 1 M instrument input.

PUBLISHED: Fender's Pure Vintage '62 Jazz Bass pickups (fender.com, part
0992123000): neck 7.25 k, 3.2 H; bridge 7.5 k, 3.35 H. A Jazz Bass's two
volume pots and its tone pot, 250 k each, all on the output with both
volumes up. Each coil's own capacitance ~110 pF (strat_coil's; not
published). BOTH coils in parallel: their inductances and resistances in
parallel, their capacitances summed.

    python3 examples/jbass_coil.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strat_coil import coil, CP, CABLE  # noqa: E402

NECK, BRIDGE = (3.2, 7.25e3), (3.35, 7.5e3)
POTS = (250e3, 250e3, 250e3)


def setting(which):
    if which == "both":
        L = 1.0 / (1.0 / NECK[0] + 1.0 / BRIDGE[0])
        Rs = 1.0 / (1.0 / NECK[1] + 1.0 / BRIDGE[1])
        return coil(L=L, Rs=Rs, Cp=2 * CP, cable=CABLE, pots=POTS)
    L, Rs = NECK if which == "neck" else BRIDGE
    return coil(L=L, Rs=Rs, Cp=CP, cable=CABLE, pots=POTS)


if __name__ == "__main__":
    for w in ("neck", "both", "bridge"):
        f0, q, R, C = setting(w)
        print("  %-6s load %.0f k, %.0f pF: resonance %.0f Hz, Q %.2f" % (w, R / 1e3, C * 1e12, f0, q))
