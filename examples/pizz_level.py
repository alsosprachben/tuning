#!/usr/bin/env python3
"""Keep each pizzicato voice at the level it was balanced to, after the fit.

    python3 examples/pizz_level.py

The Iowa fit (examples/pizz_fit.py, tonelib.PIZZ_FIT) moved the plucks'
colour and length, and so their energy -- GM 45 up 0.1 to 1.7 dB by
instrument, GM 32 down 0.7; but their LEVEL was never the fit's to change -- GM 45 was balanced against the measured violin, GM 32 against the
plucked family. So each is rendered over a passage across its range (eighth
notes, velocity 80, dry), once as the class stands and once with the values
it had before the fit put back -- its gain included -- and the energy ratio
is what is left for its gain to move by: x1.000 once tonelib carries it.
"""
import os
import sys

os.environ.setdefault("TUNING_REFLECT", "0")
os.environ.setdefault("TUNING_MASTER_DB", "-14")

import mido  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import blockrender as B  # noqa: E402
import patch_map as PM  # noqa: E402
import tonelib as T  # noqa: E402

# what the classes carried before the fit
OLD_PIZZ = dict(decay_db=16.0, harmonic_decay_db=8.0, decay_register_slope=0.85,
                tonal_dampening=1.45, octave_dampening=0.0, strike_point=0.20, strike_depth=0.70,
                inharmonicity_coefficient=T.SynthProperties.inharmonicity_coefficient_2nd_harmonic,
                pluck_open=None, initial_gain=0.2383, aftersound_fraction=0.0)
OLD_GM32 = dict(decay_db=1.2, harmonic_decay_db=2.6, decay_register_slope=0.0,
                tonal_dampening=1.35, octave_dampening=0.0, strike_point=0.25, strike_depth=0.75,
                inharmonicity_coefficient=T.SynthProperties.inharmonicity_coefficient_2nd_harmonic,
                pluck_open=None, initial_gain=0.1900)
RANGES = {"violin": (55, 91), "viola": (48, 84), "cello": (36, 72), "bass": (28, 60)}
BODY = {"violin": T.ViolinProperties, "viola": T.ViolaProperties,
        "cello": T.CelloProperties, "bass": T.ContrabassProperties}


def passage(prog, lo, hi):
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", program=prog, time=0))
    for n in list(range(lo, hi + 1, 2)) + list(range(hi, lo - 1, -2)):
        t.append(mido.Message("note_on", note=n, velocity=80, time=0))
        t.append(mido.Message("note_off", note=n, time=240))
    t.append(mido.Message("note_off", note=lo, time=1920))
    return m


def energy(prog, lo, hi):
    L, R = B.render(passage(prog, lo, hi))[:2]
    return float(np.mean(np.square(L)) + np.mean(np.square(R)))


def with_attrs(cls, attrs, fn):
    saved = {k: cls.__dict__.get(k, None) for k in attrs}
    had = {k: k in cls.__dict__ for k in attrs}
    for k, v in attrs.items():
        setattr(cls, k, v)
    try:
        return fn()
    finally:
        for k in attrs:
            if had[k]:
                setattr(cls, k, saved[k])
            else:
                delattr(cls, k)


def main(argv):
    for inst, (lo, hi) in RANGES.items():
        PM.BOWED_SPLIT = ((128, BODY[inst]),)
        cls = T.pizzicato(BODY[inst])
        new = energy(45, lo, hi)
        old = with_attrs(cls, OLD_PIZZ, lambda: energy(45, lo, hi))
        print("  GM 45 %-6s  %+.2f dB -> gain x%.3f" % (inst, 10 * np.log10(new / old), np.sqrt(old / new)))
    new = energy(32, *RANGES["bass"])
    old = with_attrs(T.AcousticBassProperties, OLD_GM32, lambda: energy(32, *RANGES["bass"]))
    print("  GM 32         %+.2f dB -> gain x%.3f" % (10 * np.log10(new / old), np.sqrt(old / new)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
