#!/usr/bin/env python3
"""The TR-909 set (program 30 on the drum channel) fitted to a real TR-909.

    python3 -I examples/tr909_fit.py                 score every note against its hit
    python3 -I examples/tr909_fit.py --select        level one: which hit each note plays
    python3 -I examples/tr909_fit.py --fit=VOICE[,VOICE] [--write]
                                                     level two: fit a patch's knobs to its hit
    python3 -I examples/tr909_fit.py --wav=DIR       write each hit and ours beside it

THE 808's TWO LEVELS (examples/tr808_fit.py, whose score and fitter this
uses). Jason Baker's set (~/Documents/refs/tr909_hyperreal, sources.md) is
one 909 (Manna Studios, 1995), dry, mono, every knob at 0, 3, 7 and 10 (the
cymbals' at 0-10 by 2): BT{tune}A{attack}D{decay}, ST{tune}T{tone}S{snappy},
LT/MT/HT{tune}D{decay}, HHO/HHC/CSH/RIDE D{knob}, RIM{velocity}. Level one
picks the setting a note plays where a GM set has a 909 sample for it --
GeneralUser GS's "TR-909 Kick", "TR-909 Snare 1" and "2"; the toms, open hat
and cymbals have no such witness and play the panel's middle (TUNE 3 for the
lower tom of each pair, 10 for the upper -- the 808 set's two tunings a
circuit; DECAY 7; the cymbals' knob at 4).

THE TAKES ARE CUT SHORT: the sampler held ~0.5 s of a kick at full DECAY,
and the hit ends while the drum still sounds. Ours is cut where the take
ends before it is scored, so the fit matches what the take holds and leaves
the tail to the decay it fitted.
"""
import os
import sys
import tempfile
import warnings

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
warnings.simplefilter("ignore")

import elkit_fit as E          # noqa: E402
import tr808_fit as F          # noqa: E402

KIT = 30
E.KIT = KIT
F.KIT = KIT
PACK = os.path.expanduser("~/Documents/refs/tr909_hyperreal/all")
GU = os.path.expanduser("~/Documents/refs/soundfonts/GeneralUser-GS.sf2")

# the GM sample each selectable note is chosen by (GeneralUser GS's 808/909 set)
SELECTOR = {36: "TR-909 Kick", 38: "TR-909 Snare 1", 40: "TR-909 Snare 2"}
CANDIDATES = {36: "BT", 35: "BT", 38: "ST", 40: "ST"}

# LEVEL ONE's answer (--select for 36, 38, 40; the rest the panel's middle)
# GeneralUser's two snares ARE Baker's takes (scores 0.9 and 0.7); its kick is
# another 909's, cut at 0.13 s, and says only that the sweep is TUNE's deepest:
# kick 1 is TUNE, ATTACK and DECAY full, kick 2 the panel's middle.
HITS = {35: "BT7A0D7", 36: "BTAAADA", 37: "RIM127", 38: "ST0T3S3", 40: "STATASA",
        41: "LT3D7", 43: "LTAD7", 45: "MT3D7", 47: "MTAD7", 48: "HT3D7", 50: "HTAD7",
        46: "HHOD4", 49: "CSHD4", 51: "RIDED4"}

_T = ("decay_s", True, 0.3), ("h2_db", False, 6.0), ("h3_db", False, 6.0)
_CLICK = (("click_db", False, 6.0), ("click_dbs", True, 0.4), ("click_tilt", False, 2.0))
_KICK = _T + (("bend_oct", False, 0.3), ("bend_ms", True, 0.3)) + _CLICK
_TOM = _T + ((("res", 0, 0), True, 0.05), (("res", 0, 1), False, 4.0), (("res", 0, 2), True, 0.3),
             ("bend_oct", False, 0.15), ("bend_ms", True, 0.3), ("noise_db", False, 6.0),
             ("noise_decay_s", True, 0.3)) + _CLICK
_SNARE = _T + ((("res", 0, 0), True, 0.05), (("res", 0, 1), False, 4.0), (("res", 0, 2), True, 0.3),
               ("bend_oct", False, 0.15), ("bend_ms", True, 0.3), ("noise_db", False, 4.0),
               ("noise_hp_hz", True, 0.4), ("noise_lp_hz", True, 0.4), ("noise_decay_s", True, 0.3)) + _CLICK
_HAT = (("noise_hp_hz", True, 0.3), ("noise_lp_hz", True, 0.3), ("noise_tilt", False, 2.0),
        ("noise_decay_s", True, 0.3), ("noise_rise_ms", True, 0.5), ("noise_len_ms", True, 0.3))
_CYM = (("noise_db", False, 4.0), ("noise_hp_hz", True, 0.3), ("noise_lp_hz", True, 0.3),
        ("noise_decay_s", True, 0.3), ("noise_rise_ms", True, 0.5),
        ("noise2_hp_hz", True, 0.3), ("noise2_lp_hz", True, 0.3), ("noise2_tilt", False, 2.0),
        ("noise2_decay_s", True, 0.3), ("noise2_rise_ms", True, 0.5))
F.KNOBS = {
    "kick": (36, "TR909KickProperties", _KICK),
    "kick2": (35, "TR909Kick2Properties", _KICK),
    "snare": (38, "TR909SnareProperties", _SNARE),
    "snare2": (40, "TR909Snare2Properties", _SNARE),
    "lowtom": (41, "TR909TomProperties", _TOM),
    "lowtom1": (43, "TR909LowTom1Properties", _TOM),
    "midtom": (45, "TR909MidTomProperties", _TOM),
    "midtom1": (47, "TR909MidTom1Properties", _TOM),
    "hitom": (48, "TR909HiTomProperties", _TOM),
    "hitom1": (50, "TR909HiTom1Properties", _TOM),
    "rim": (37, "TR909RimProperties", _T + ((("res", 0, 0), True, 0.1), (("res", 0, 1), False, 4.0),
                                            (("res", 0, 2), True, 0.3)) + _CLICK),
    "openhat": (46, "TR909OpenHatProperties", _HAT),
    "crash": (49, "TR909CrashProperties", _CYM),
    "ride": (51, "TR909RideProperties", _CYM),
}
F.SHARED = {}
F.HITS = HITS
F.VOICE = {n: None for n in HITS}


def hit(name):
    return E.read(os.path.join(PACK, name + ".WAV"))


F.hit = hit
_ours = F.ours
_score = F.score


def score(ours, theirs, sr, pitch=True, fmax=1500.0, win=0.02):
    """tr808_fit's score, ours cut where the take ends."""
    ours = np.asarray(ours, float)
    a, b = F.onset(ours), F.onset(theirs)
    ours = ours[:a + len(theirs) - b]
    return _score(ours, theirs, sr, pitch, fmax, win)


F.score = score
_settled = F.settled


def settled(y, sr, fmax, short=False):
    """tr808_fit's tuning, unless the pitch track over 25-75 ms disagrees by
    more than a third: snare 2 at full SNAPPY, whose noise outweighs its
    tone after ~80 ms -- the long window read 1240 Hz, the track 234."""
    f = _settled(y, sr, fmax, short)
    tr = F.track(y, sr, fmax)
    if len(tr) >= 15:
        g = float(np.median(tr[5:15]))
        if abs(np.log(f / g)) > np.log(4 / 3.0):
            return g
    return f


F.settled = settled


def report(d, notes=None):
    """Every note's score: tr808_fit's, each tom at its own pitch."""
    import percussion_map as P
    tot = []
    for n in notes or sorted(HITS):
        y, sr = hit(HITS[n])
        x, _ = F.ours(n, d)
        cls = P.KITS[KIT][n][1]
        pitch = cls.tr808_patch["circuit"] == "resonator" and cls.tr808_patch["tone_db"] > -90
        s = score(x, y, sr, pitch, F.fmax(cls), F.win(cls))
        tot.append(s)
        print("%3d %-16s %-8s score %5.1f" % (n, P.KITS[KIT][n][0], HITS[n], s))
    print("mean %.1f" % np.mean(tot))


F.report = report


def gu_sample(name):
    """A GeneralUser GS sample by its name, as recorded (no envelope)."""
    from gm_release import _chunks, _recs
    b = open(GU, "rb").read()
    d, smpl = None, None
    for cid, o, sz in _chunks(b, 12, len(b)):
        if cid == b"LIST" and b[o:o + 4] == b"pdta":
            d = {c.decode(): b[oo:oo + s] for c, oo, s in _chunks(b, o + 4, o + sz)}
        if cid == b"LIST" and b[o:o + 4] == b"sdta":
            for c, oo, s in _chunks(b, o + 4, o + sz):
                if c == b"smpl":
                    smpl = oo
    for s in _recs(d["shdr"], "<20sIIIIIBbHH", 46):
        if s[0].split(b"\0")[0].decode("latin1") == name:
            x = np.frombuffer(b[smpl + 2 * s[1]:smpl + 2 * s[2]], "<i2").astype(float) / 32768.0
            return x, s[5]
    raise KeyError(name)


def select(d, notes=None):
    """Each selectable note's closest hit to its GeneralUser sample -- the
    score with pitch, since GeneralUser's sample is unrepitched at its key."""
    from scipy.signal import resample_poly
    for n in notes or sorted(SELECTOR):
        g, sr = gu_sample(SELECTOR[n])
        if sr != 44100:
            g = resample_poly(g, 44100, sr)
        names = sorted(p[:-4] for p in os.listdir(PACK)
                       if p.upper().endswith(".WAV") and p.startswith(CANDIDATES[n]))
        res = sorted((score(hit(m)[0], g, 44100), m) for m in names)
        print("%3d %-15s -> %s  (%s)" % (n, SELECTOR[n], res[0][1],
                                          "  ".join("%s %.1f" % (m, s) for s, m in res[:5])))


def main(argv):
    with tempfile.TemporaryDirectory() as d:
        args = dict(a.split("=", 1) if "=" in a else (a, "") for a in argv)
        if "--select" in args:
            select(d)
        elif "--fit" in args:
            for v in args["--fit"].split(","):
                F.fit(v, d, int(args.get("--maxfev", 400)))
            F.report(d)
            if "--write" in args:
                for cls_name, patch in F.fit.done:
                    F.write(cls_name, patch)
        elif "--wav" in args:
            F.write_wavs(args["--wav"], d, tag="909")
        else:
            F.report(d)


if __name__ == "__main__":
    main(sys.argv[1:])
