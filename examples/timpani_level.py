#!/usr/bin/env python3
"""Keep the timpani at the level it was balanced to, after the fit.

    python3 examples/timpani_level.py

examples/harp_level.py's method on GM 47: strokes across the drums' range
(E2 to G3, every second semitone, velocity 80, dry), rendered as the class
stands and with the values it had before examples/timpani_fit.py put back --
its gain included -- and the energy ratio is what is left for initial_gain to
move by. The old balance had 3 dB of Ben's ear in it, against the orchestra;
this keeps that.
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

OLD = dict(mode_ratios=(1.00, 1.50, 1.97, 2.44, 2.90), mode_gains=(0.55, 1.00, 0.70, 0.42, 0.22),
           mode_stroke_tilt=0.0, mode_decays=(), decay_db=8.2, harmonic_decay_db=2.3,
           harmonic_decay_dampening=0.0, decay_register_slope=0.0,
           initial_gain=(1.0 / 7.3) * 1.659)
LO, HI = 40, 55


def energy():
    L, R = B.render(passage(47, LO, HI))[:2]
    return float(np.sum(L * L + R * R))


def main(argv):
    cls = T.TimpaniProperties
    new = energy()
    old = with_attrs(cls, OLD, energy)
    print("  GM 47  %+.2f dB -> gain x%.3f" % (10 * np.log10(new / old), np.sqrt(old / new)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
