#!/usr/bin/env python3
"""The CR-78 set (program 27 on the drum channel) fitted to real CR-78s.

    python3 -I examples/cr78_fit.py                 score every note against its take
    python3 -I examples/cr78_fit.py --fit=VOICE[,VOICE] [--write]
    python3 -I examples/cr78_fit.py --wav=DIR       write each take and ours beside it

The CR-78 has no knobs on its voices: each is one setting, and its take is
the target. Two units (sources.md): Bjornmossa's (CC BY 4.0, recorded
direct, 96 kHz, here at 44.1: ~/Documents/refs/cr78_bjornmossa/wav44) for
the kicks, snares, tom, hats, tambourine, guiro, metallic beats ("ping") and
rim shot, and wikter's (CC0, cut tight: ~/Documents/refs/cr78_wikter/wav)
for the bongos, maracas and claves. Bjornmossa's labels are not all his
machine's: his "clave_2" is the rim shot (wikter's, 1.4 kHz -- whose take is
cut at 4.7 ms, inside the score's first frame, so the 8.9 ms one is fitted),
and his "clave_1" (547 Hz) matches no CR-78 voice, so it is not used. Level two only,
through examples/tr909_fit.py's score and examples/tr606_fit.py's ring term.
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
_808 = dict((k, v[2]) for k, v in F.KNOBS.items())     # before tr909_fit replaces them
import tr909_fit as T9         # noqa: E402  (its score, tuning rule and report)
import tr606_fit as T6         # noqa: E402  (its ring term: tr606_fit.score)

KIT = 27
E.KIT = F.KIT = T9.KIT = T6.KIT = KIT
BJ = os.path.expanduser("~/Documents/refs/cr78_bjornmossa/wav44")
WK = os.path.expanduser("~/Documents/refs/cr78_wikter/wav")

# each note's take; 41-50 are the one tom at six pitches (47 its own)
HITS = {35: "bj:kick_3", 36: "bj:kick_2", 37: "bj:clave_2", 38: "bj:snare_1", 40: "bj:snare_2",
        42: "bj:hihat_closed_1", 46: "bj:hihat_open_1", 47: "bj:tom", 54: "bj:tambourine_1",
        60: "wk:hb-hi-bongo", 61: "wk:low-bongo", 70: "wk:maraca", 74: "bj:guiro_1",
        75: "wk:clave", 80: "bj:ping_1", 81: "bj:ping_2"}

# the noise voices' takes start with the trigger's thump under 250 Hz, as the
# 606's do: the click, low-passed
_NOISE = (("noise_hp_hz", True, 0.3), ("noise_lp_hz", True, 0.3), ("noise_tilt", False, 2.0),
          ("noise_decay_s", True, 0.3), ("noise_rise_ms", True, 0.5),
          ("click_db", False, 6.0), ("click_lp_hz", True, 0.4), ("click_dbs", True, 0.4))
_RING = (("decay_s", True, 0.3), ("h2_db", False, 6.0), ("h3_db", False, 6.0),
         ("click_db", False, 6.0), ("click_dbs", True, 0.4), ("click_tilt", False, 2.0))
F.KNOBS = {
    "kick": (36, "CR78KickProperties", _808["kick"]),
    "kick2": (35, "CR78Kick2Properties", _808["kick"]),
    "snare": (38, "CR78SnareProperties", _RING + (
        ("noise_db", False, 4.0), ("noise_hp_hz", True, 0.4), ("noise_lp_hz", True, 0.4),
        ("noise_decay_s", True, 0.3))),
    "snare2": (40, "CR78Snare2Properties", _RING + (
        ("noise_db", False, 4.0), ("noise_hp_hz", True, 0.4), ("noise_lp_hz", True, 0.4),
        ("noise_decay_s", True, 0.3))),
    "rim": (37, "CR78RimProperties", _RING + ((("res", 0, 0), True, 0.1),
                                              (("res", 0, 1), False, 4.0), (("res", 0, 2), True, 0.3))),
    "tom": (47, "CR78TomProperties", _808["lowtom"]),
    "hibongo": (60, "CR78HiBongoProperties", _RING),
    "lowbongo": (61, "CR78LowBongoProperties", _RING),
    "claves": (75, "CR78ClavesProperties", _RING),
    "closedhat": (42, "CR78ClosedHatProperties", _NOISE),
    "openhat": (46, "CR78OpenHatProperties", _NOISE),
    "maracas": (70, "CR78MaracasProperties", _NOISE + (("noise_len_ms", True, 0.3),)),
    "tambourine": (54, "CR78TambourineProperties", _NOISE),
    # the guiro's ratchet (its bursts' times) is the take's; their colour and
    # fall are fitted. (The first fit's bursts ran together: Standard's long
    # guiro was scraping the key -- see percussion_map.rasp_strokes)
    "guiro": (74, "CR78GuiroProperties", (
        ("click_hp_hz", True, 0.3), ("click_lp_hz", True, 0.3), ("click_tilt", False, 2.0),
        ("click_dbs", True, 0.4))),
    "metalbeat": (80, "CR78MetalBeatProperties", _RING + (
        (("res", 0, 0), True, 0.05), (("res", 0, 1), False, 4.0), (("res", 0, 2), True, 0.3))),
    "metalbeat2": (81, "CR78MetalBeat2Properties", _NOISE),
}
F.SHARED = {}
F.HITS = T9.HITS = HITS
F.VOICE = {n: None for n in HITS}


def hit(name):
    pack, n = name.split(":", 1)
    return E.read(os.path.join(BJ if pack == "bj" else WK, n + ".wav"))


F.hit = T9.hit = T6.hit = hit
F.score = T9.score = T6.score
_track = F.track


def track(x, sr, fmax=1500.0, span=0.15, win=0.02):
    """tr808_fit's pitch track while the TONE holds it: the leading frames
    within half an octave of the first. A CR-78 snare's 312 Hz rings for
    three frames, then its noise takes the track (968-1434 Hz) and, past the
    74 ms take, the silence (26 Hz): scored there, the pitch term was 59 of
    the snare's 73.5 and measured nothing but the noise."""
    tr = _track(x, sr, fmax, span, win)
    if len(tr) < 2:
        return tr
    ok = np.abs(np.log2(tr / tr[0])) <= 0.5
    n = int(np.argmin(ok)) if not ok.all() else len(tr)
    return tr[:max(1, n)]


F.track = track


def main(argv):
    with tempfile.TemporaryDirectory() as d:
        args = dict(a.split("=", 1) if "=" in a else (a, "") for a in argv)
        if "--fit" in args:
            for v in args["--fit"].split(","):
                F.fit(v, d, int(args.get("--maxfev", 400)))
                if "--write" in args:          # each written as it is done
                    F.write(*F.fit.done[-1])
            T9.report(d)
        elif "--wav" in args:
            F.write_wavs(args["--wav"], d, tag="cr78")
        else:
            T9.report(d)


if __name__ == "__main__":
    main(sys.argv[1:])
