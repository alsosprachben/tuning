#!/usr/bin/env python3
"""Keep the tubular bells at the level they were balanced to, after the fit.

    python3 examples/tubular_level.py

examples/harp_level.py's method on GM 14: strokes across the chimes' range
(C4 to F5, every second semitone, velocity 80, dry), rendered as the class
stands and as it was before examples/tubular_fit.py -- harmonics 2-6 at set
levels, one decay law, its methods and gain put back -- and the energy ratio
is what is left for initial_gain to move by.
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

OLD = dict(bar_modes=((2, 1.0), (3, 0.75), (4, 0.50), (5, 0.30), (6, 0.16)), max_harmonic=6,
           mode_ratios=None, mode_ratio=T.TunedBarProperties.mode_ratio,
           series_volume=T.TunedBarProperties.series_volume,
           harmonic_decay=T.TunedBarProperties.harmonic_decay,
           decay_db=0.55, harmonic_decay_db=0.5, decay_register_slope=0.0,
           initial_gain=1.0 / 7.9)
LO, HI = 60, 77


def energy():
    L, R = B.render(passage(14, LO, HI))[:2]
    return float(np.sum(L * L + R * R))


def main(argv):
    cls = T.TubularBellProperties
    new = energy()
    old = with_attrs(cls, OLD, energy)
    print("  GM 14  %+.2f dB -> gain x%.3f" % (10 * np.log10(new / old), np.sqrt(old / new)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
