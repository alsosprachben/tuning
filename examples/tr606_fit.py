#!/usr/bin/env python3
"""The TR-606 set (program 28 on the drum channel) fitted to real TR-606s.

    python3 -I examples/tr606_fit.py                 score every note against its take
    python3 -I examples/tr606_fit.py --fit=VOICE[,VOICE] [--write]
    python3 -I examples/tr606_fit.py --wav=DIR       write each take and ours beside it

The 606 has no TUNE or DECAY but the hats': each voice is one setting,
and its take is the target. Ed Vargo's set (~/Documents/refs/tr606_hyperreal)
holds every voice at full length; bdu's (~/Documents/refs/tr606_bdu, CC0, a
second unit -- its toms a semitone apart from Vargo's) each plain and
ACCENTED, and its accented snare is the set's Snare 2. Level two only,
through examples/tr909_fit.py's score.
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
_909 = dict((k, v[2]) for k, v in F.KNOBS.items())

KIT = 28
E.KIT = F.KIT = T9.KIT = KIT
VARGO = os.path.expanduser("~/Documents/refs/tr606_hyperreal/all")
BDU = os.path.expanduser("~/Documents/refs/tr606_bdu/wav")

# each note's take; 43, 45, 47, 50 are the two toms played at other pitches
HITS = {36: "606BASS", 38: "606SNAR", 40: "bdu:snareac", 41: "606LTOM", 42: "606CHAT",
        46: "606OHAT", 48: "606HTOM", 51: "606CYMB"}

# the metal voices' takes all start with a thump under 250 Hz (-35 dB, the
# trigger leaking through): the click, low-passed
_THUMP = (("click_db", False, 6.0), ("click_lp_hz", True, 0.4), ("click_dbs", True, 0.4))
_METAL = (("osc_duty", False, 0.05), (("bands", 0, 0), True, 0.2), (("bands", 0, 1), True, 0.3),
          (("bands", 0, 3), True, 0.3), ("hp_hz", True, 0.2), ("hp_q", True, 0.3),
          ("noise_db", False, 4.0), ("noise_decay_s", True, 0.3)) + _THUMP
# the kick and snares were fitted on the 909's knobs (the sweep, h2, h3, the
# click; no first-cycle jump), the toms on the 808's (its diodes)
F.KNOBS = {
    "kick": (36, "TR606KickProperties", _909["kick"]),
    "snare": (38, "TR606SnareProperties", _909["snare"]),
    "snare2": (40, "TR606Snare2Properties", _909["snare"]),
    "lowtom": (41, "TR606TomProperties", _808["lowtom"]),
    "hitom": (48, "TR606HiTomProperties", _808["lowtom"]),
    "closedhat": (42, "TR606ClosedHatProperties", _METAL),
    "openhat": (46, "TR606OpenHatProperties", _METAL),
    # THE CYMBAL as the 808's: three bands, each its own VCA's decay (its 8 kHz
    # falls 20 dB in 0.1 s while 1-2 kHz holds), centres free -- the 606's are
    # not the 808's
    "cymbal": (51, "TR606CymbalProperties", (
        ("osc_duty", False, 0.05),) + tuple(
        ((("bands", b, 0), True, 0.2), (("bands", b, 1), True, 0.3), (("bands", b, 2), False, 4.0),
         (("bands", b, 3), True, 0.3))[k] for b in range(3) for k in range(4)) + (
        ("hp_hz", True, 0.3), ("noise_db", False, 4.0), ("noise_decay_s", True, 0.3),
        ("after_db", False, 4.0), ("after_s", True, 0.3)) + _THUMP),
}
F.SHARED = {}
F.HITS = T9.HITS = HITS
F.VOICE = {n: None for n in HITS}


def hit(name):
    if name.startswith("bdu:"):
        return E.read(os.path.join(BDU, name[4:] + ".WAV"))
    return E.read(os.path.join(VARGO, name + ".WAV"))


F.hit = T9.hit = hit
_score = F.score


def tail(x, sr, span):
    """The 50 ms level, dB re its loudest, from 0.1 s to the take's end."""
    x = np.asarray(x, float)
    x = x[F.onset(x):]
    out = []
    for a in np.arange(0.1, span - 0.05, 0.05):
        s = x[int(a * sr):int((a + 0.05) * sr)]
        out.append(10 * np.log10(np.mean(s * s) + 1e-20))
    return np.array(out)


def score(ours, theirs, sr, pitch=True, fmax=1500.0, win=0.02):
    """tr909_fit's score, PLUS the ring: the 50 ms envelope from 0.1 s on,
    dB re the strike, to -80 -- the grid floors its cells at -60 under the
    loudest, and the cymbal's tail (-21 at 0.25 s, -43 at 0.9) weighed so
    little the fit let it fall at 100 dB/s against the take's 40 (Ben: "more
    ring to it than ours")."""
    s = _score(ours, theirs, sr, pitch, fmax, win)
    t = np.asarray(theirs, float)
    span = (len(t) - F.onset(t)) / sr
    if span > 0.3:
        o, h = np.asarray(ours, float), t
        po = 10 * np.log10(np.max(o[F.onset(o):][:int(0.05 * sr)] ** 2) + 1e-20)
        ph = 10 * np.log10(np.max(h[F.onset(h):][:int(0.05 * sr)] ** 2) + 1e-20)
        a, b = np.maximum(tail(o, sr, span) - po, -80), np.maximum(tail(h, sr, span) - ph, -80)
        n = min(len(a), len(b))
        s += float(np.sqrt(np.mean((a[:n] - b[:n]) ** 2)))
    return s


F.score = T9.score = score


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
            F.write_wavs(args["--wav"], d, tag="606")
        else:
            T9.report(d)


if __name__ == "__main__":
    main(sys.argv[1:])
