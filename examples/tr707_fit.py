#!/usr/bin/env python3
"""The TR-707 set (program 29 on the drum channel) fitted to a TR-707's ROM.

    python3 -I examples/tr707_fit.py                 score every note against its take
    python3 -I examples/tr707_fit.py --fit=VOICE[,VOICE] [--write]
    python3 -I examples/tr707_fit.py --wav=DIR       write each take and ours beside it

The 707 plays each voice's ROM recording once, through a VCA: no knobs to
choose between, so there is no level one -- each note's take is THE take
(hyperreal's set, ~/Documents/refs/tr707_hyperreal, sources.md: all fifteen
voices). Level two fits each patch to it through examples/tr909_fit.py's
score (tr808_fit's, ours cut where the take ends) and its tuning rule.
"""
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))

import elkit_fit as E          # noqa: E402
import tr808_fit as F          # noqa: E402
import tr909_fit as T9         # noqa: E402  (its score, tuning rule and report)

KIT = 29
E.KIT = F.KIT = T9.KIT = KIT
PACK = os.path.expanduser("~/Documents/refs/tr707_hyperreal/all")

# each note's take; 43, 47, 50 are 41, 45, 48 played two semitones up
HITS = {35: "BassDrum2", 36: "BassDrum1", 37: "RimShot", 38: "Snare1", 39: "HandClap",
        40: "Snare2", 41: "LowTom", 42: "HhC", 45: "MedTom", 46: "HhO", 48: "HiTom"}

_T = ("decay_s", True, 0.3), ("h2_db", False, 6.0), ("h3_db", False, 6.0)
_CLICK = (("click_db", False, 6.0), ("click_dbs", True, 0.4), ("click_tilt", False, 2.0))
_RES2 = ((("res", 0, 0), True, 0.05), (("res", 0, 1), False, 4.0), (("res", 0, 2), True, 0.3),
         (("res", 1, 0), True, 0.05), (("res", 1, 1), False, 4.0), (("res", 1, 2), True, 0.3))
# the kick's take holds, then its VCA closes (-2 dB at 35-60 ms, -29 after);
# its beater's click is a band near 2 kHz
_KICK = _T + (("bend_oct", False, 0.3), ("bend_ms", True, 0.3), ("gate_ms", True, 0.2),
              ("click_hp_hz", True, 0.4), ("click_lp_hz", True, 0.4)) + _CLICK
_TOM = _T + _RES2 + (("bend_oct", False, 0.15), ("bend_ms", True, 0.3), ("noise_db", False, 6.0),
                     ("noise_decay_s", True, 0.3)) + _CLICK
_SNARE = _T + _RES2 + (("bend_oct", False, 0.1), ("bend_ms", True, 0.3), ("noise_db", False, 4.0),
                       ("noise_hp_hz", True, 0.4), ("noise_lp_hz", True, 0.4),
                       ("noise_decay_s", True, 0.3), ("gate_ms", True, 0.2)) + _CLICK
_HAT = (("noise_hp_hz", True, 0.3), ("noise_lp_hz", True, 0.3), ("noise_tilt", False, 2.0),
        ("noise_decay_s", True, 0.3), ("noise_rise_ms", True, 0.5))
F.KNOBS = {
    "kick": (36, "TR707KickProperties", _KICK),
    "kick2": (35, "TR707Kick2Properties", _KICK),
    "snare": (38, "TR707SnareProperties", _SNARE),
    "snare2": (40, "TR707Snare2Properties", _SNARE),
    "lowtom": (41, "TR707TomProperties", _TOM),
    "midtom": (45, "TR707MidTomProperties", _TOM),
    "hitom": (48, "TR707HiTomProperties", _TOM),
    "rim": (37, "TR707RimProperties", _T + _RES2 + _CLICK + (("gate_ms", True, 0.2),)),
    # the clap's four bursts are the take's (0, 10, 20, 31 ms); their colour,
    # their fall and the tail after them are fitted
    "clap": (39, "TR707ClapProperties", (
        ("click_hp_hz", True, 0.3), ("click_lp_hz", True, 0.3), ("click_tilt", False, 2.0),
        ("click_dbs", True, 0.4), ("noise_db", False, 4.0), ("noise_hp_hz", True, 0.3),
        ("noise_lp_hz", True, 0.3), ("noise_decay_s", True, 0.3), ("noise_rise_ms", True, 0.5),
        ("gate_ms", True, 0.2))),
    "closedhat": (42, "TR707ClosedHatProperties", _HAT + (("gate_ms", True, 0.2),)),
    "openhat": (46, "TR707OpenHatProperties", _HAT + (("noise_len_ms", True, 0.3), ("gate_ms", True, 0.2))),
}
F.HITS = T9.HITS = HITS
F.VOICE = {n: None for n in HITS}


def hit(name):
    return E.read(os.path.join(PACK, name + ".wav"))


F.hit = T9.hit = hit
_settled = F.settled


def settled(y, sr, fmax, short=False):
    """tr909_fit's tuning; a take under 0.15 s (the kicks, 0.1 s), from its
    zero crossings over 25-60 ms. Its short window (2-40 ms) is mid-sweep
    and read 79 Hz, and a 20 ms FFT frame cannot resolve 55 Hz (the track
    wandered 49-70): the crossings put the kicks at ~55 by 46 ms. Only
    under 100 Hz: a 0.14 s snare's crossings counted its wires, 1240 Hz."""
    if F.sounding(y, sr) < 0.15:
        y = np.asarray(y, float)
        a = F.onset(y)
        seg = y[a + int(0.025 * sr):a + int(0.060 * sr)]
        neg = np.signbit(seg)
        up = np.flatnonzero(neg[:-1] & ~neg[1:])
        if len(up) >= 2:
            t = up + seg[up] / (seg[up] - seg[up + 1])
            f = float(sr * (len(t) - 1) / (t[-1] - t[0]))
            if f < 100.0:      # a kick's regime: a snare's crossings count its noise
                return f
    return _settled(y, sr, fmax, short)


F.settled = settled


def main(argv):
    with tempfile.TemporaryDirectory() as d:
        args = dict(a.split("=", 1) if "=" in a else (a, "") for a in argv)
        if "--fit" in args:
            for v in args["--fit"].split(","):
                F.fit(v, d, int(args.get("--maxfev", 400)))
            T9.report(d)
            if "--write" in args:
                for cls_name, patch in F.fit.done:
                    F.write(cls_name, patch)
        elif "--wav" in args:
            F.write_wavs(args["--wav"], d, tag="707")
        else:
            T9.report(d)


if __name__ == "__main__":
    main(sys.argv[1:])
