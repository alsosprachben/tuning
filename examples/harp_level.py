#!/usr/bin/env python3
"""Keep the harp at the level it was balanced to, after the fit.

    python3 examples/harp_level.py

examples/pizz_level.py's method on GM 46: a passage across the compass,
eighth notes at velocity 80, dry, rendered as the class stands and with the
values it had before examples/harp_fit.py put back -- its gain included -- and
the energy ratio is what is left for initial_gain to move by. Printed twice:
over the whole passage and over each note's first 150 ms, because the old
harp's treble rang twenty times too long, and its energy was ring, not pluck.
"""
import os
import sys

os.environ.setdefault("TUNING_REFLECT", "0")
os.environ.setdefault("TUNING_MASTER_DB", "-14")

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))

import blockrender as B  # noqa: E402
import tonelib as T  # noqa: E402
from pizz_level import passage, with_attrs  # noqa: E402

OLD = dict(strike_point=0.38, strike_depth=0.80, decay_db=0.35, harmonic_decay_db=0.9,
           inharmonicity_coefficient=T.SynthProperties.inharmonicity_coefficient_2nd_harmonic,
           decay_register_slope=0.0, tonal_dampening=1.25, bell_order=2.0, initial_gain=0.1183)
LO, HI = 28, 100


def energies():
    L, R = B.render(passage(46, LO, HI))[:2]
    x = L * L + R * R
    sr = 44100
    step, w = int(0.25 * sr), int(0.15 * sr)        # eighth notes at 120 bpm
    heads = sum(float(x[i:i + w].sum()) for i in range(0, len(x) - w, step))
    return float(x.sum()), heads


def main(argv):
    cls = T.HarpProperties
    new = energies()
    old = with_attrs(cls, OLD, energies)
    for what, n, o in (("whole passage", new[0], old[0]), ("first 150 ms", new[1], old[1])):
        print("  GM 46 %-14s %+.2f dB -> gain x%.3f" % (what, 10 * np.log10(n / o), np.sqrt(o / n)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
