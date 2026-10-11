#!/usr/bin/env python3
"""Fit the electric guitars (GM 26-31) and basses (GM 33-37) to Fraunhofer's
IDMT-SMT-Guitar and IDMT-SMT-Bass (CC BY-NC-ND 4.0: measured only, never
redistributed; ~/Documents/refs/idmt, sources.md).

    egtr_fit.py --stage                 link every single note under its sounding name
                                        (and cut GuitarSet's isolated notes, GM 25)
    egtr_fit.py SET [SET ...]           measure: recorded against ours, by octave
    egtr_fit.py --list                  the sets
    egtr_fit.py SET --model=PROG        ...and ours, DI, at every third of its notes
    egtr_fit.py --string=guitar|bass|fretless|steel    the family's decay law and stretch law
    egtr_fit.py --ladder=PROG           the program's pick, notch, tilt, pickup resonance
    egtr_fit.py --envelope=PROG         its top: the pickup's resonance, Q and tilt, by absolute frequency
    egtr_fit.py --ab=PROG:OUT.wav       recorded notes, each then ours (DI)
    egtr_fit.py --damp                  the basses' release, from the damps ending their notes
    egtr_fit.py --mute                  the palm mute's decay against the open string
    egtr_fit.py --technique=mute|harm   palm-muted or harmonic notes: recorded against ours
    egtr_fit.py --fit-technique=mute|harm   GM 28/31's pluck, notch, tilt and decay law
    egtr_fit.py --abtech=mute|harm:OUT.wav  recorded notes, each then ours (DI)
    egtr_fit.py --pluck=harm                the harmonics' pluck: strike_noise_db fitted
    egtr_fit.py --leak                      the touched string's other modes, in its place
    egtr_fit.py --abdamp=PROG:OUT.wav   recorded notes through their damp, each then ours

BOTH ARE DI RECORDINGS: "the guitars were mostly plugged directly into the
Line-In channel of the audio interface" (the guitar set's description; the one
exception, a miked acoustic in dataset 4, is not used), and the basses the
same. So what is measured is the string and the pickup -- the comb of the pick,
the comb of the coil, its velocity response and whatever its electrical load
does -- with no amplifier and no cabinet, and ours is rendered the same way:
the class with its amp_drive at 0 and no cabinet.

THE SETS. Guitar dataset 1: single picked notes, frets 0-12 on all six strings,
one XML each (pitch, string, fret, technique) -- a Fender Stratocaster on its
neck single coil, and an Ibanez RG2820 on its bridge humbucker, its neck
humbucker and its bridge+neck single coils. Bass: three basses (1 Fame
Baphomet, 2 Warwick, 3 Yamaha BB604 Jazz), three pickup settings (1 neck,
2 both, 3 bridge), five plucking styles (FS finger, PK pick, MU muted, ST slap
thumb, SP slap pluck), strings E1 A1 D2 G2, frets 0-12, the file name carrying
it all: BS_<bass>_EQ_<pickup>_<style>_<expr>_<string>_<fret>.wav.

Staged as <note><octave>.s<string>f<fret>.wav links (pizz_measure reads the
pitch from the name, the string from the second field), one folder per set
under REFS/staged/.
"""
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

from pizz_measure import measure, report  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs/idmt")
STAGED = os.path.join(REFS, "staged")
NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
G1 = os.path.join(REFS, "guitar", "IDMT-SMT-GUITAR_V2", "dataset1")
GUITARS = {                       # set name: dataset 1 folder
    "strat_neck_sc": "Fender Strat Clean Neck SC",
    "ibanez_bridge_hu": "Ibanez Power Strat Clean Bridge HU",
    "ibanez_neck_hu": "Ibanez Power Strat Clean Neck HU",
    "ibanez_bridge_neck_sc": "Ibanez Power Strat Clean Bridge+Neck SC",
}
BASS_OPEN = {1: 28, 2: 33, 3: 38, 4: 43}      # E1 A1 D2 G2
BASSES = {1: "fame", 2: "warwick", 3: "yamaha"}
PICKUPS = {1: "neck", 2: "both", 3: "bridge"}
STYLES = ("FS", "PK", "MU", "ST", "SP")


def _name(midi):
    return "%s%d" % (NAMES[midi % 12], midi // 12 - 1)


def _link(src, folder, midi, string, fret):
    os.makedirs(folder, exist_ok=True)
    dst = os.path.join(folder, "%s.s%df%02d.wav" % (_name(midi), string, fret))
    if not os.path.lexists(dst):
        os.symlink(src, dst)


def stage():
    n = 0
    for name, sub in GUITARS.items():
        for x in glob.glob(os.path.join(G1, sub, "annotation", "*.xml")):
            ev = ET.parse(x).getroot().find("transcription/event")
            wav = os.path.join(G1, sub, "audio", os.path.basename(x)[:-4] + ".wav")
            if ev is None or not os.path.exists(wav):
                continue
            _link(wav, os.path.join(STAGED, name), int(ev.findtext("pitch")),
                  int(ev.findtext("stringNumber")), int(ev.findtext("fretNumber")))
            n += 1
    pat = re.compile(r"BS_(\d)_EQ_(\d)_([A-Z]{2})_NO_(\d)_(\d+)\.wav$")
    skipped = 0
    for wav in glob.glob(os.path.join(REFS, "bass", "PS", "*", "*.wav")):
        m = pat.search(os.path.basename(wav))
        if not m:
            continue
        b, p, st, s, f = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4)), int(m.group(5))
        if s not in BASS_OPEN:
            # a "string 5" on the Yamaha alone, its open note sounding G2
            # again: not a fifth string that can be placed -- left out
            skipped += 1
            continue
        _link(wav, os.path.join(STAGED, "bass_%s_%s_%s" % (BASSES[b], PICKUPS[p], st)),
              BASS_OPEN[s] + f, s, f)
        n += 1
    n += stage_fretless()
    n += stage_guitarset()
    print("  staged %d notes in %d sets (%d bass files on an unplaceable string 5 left out)"
          % (n, len(sets()), skipped))


# THE FRETLESS (GM 35), from Freesound (~/Documents/refs/sources.md): no IDMT
# fretless. FaireDesVagues' 15 notes (CC BY 3.0), a four-string into a Zoom H2's
# line input, named by pitch (checked: each within 13 cents -- a fretless's own
# intonation); four of them open strings (E1 A1 D2 G2), eleven STOPPED on the
# wood, placed where a player puts them (the lowest string, frets 0-4, the
# G string above). mrforfs' open strings (CC0), a five-string B0 E1 A1 D2 G2 on
# the neck pickup, the bridge pickup and both: string 0 its low B.
FRETLESS = os.path.expanduser("~/Documents/refs/freesound/fretless")
FDV_PLACE = {"e1": (1, 0), "f1": (1, 1), "g1": (1, 3), "a1": (2, 0), "b1": (2, 2), "c2": (2, 3),
             "d2": (3, 0), "e2": (3, 2), "f2": (3, 3), "g2": (4, 0), "a2": (4, 2), "b2": (4, 4),
             "c3": (4, 5), "d3": (4, 7), "e3": (4, 9)}
MRF_OPEN = {"b": (0, 23), "e": (1, 28), "a": (2, 33), "d": (3, 38), "g": (4, 43)}


def stage_fretless():
    n = 0
    for p in glob.glob(os.path.join(FRETLESS, "fairedesvagues", "*fdv_basse1_*.wav")):
        key = re.search(r"fdv_basse1_([a-g]\d)\.wav$", p).group(1)
        s, f = FDV_PLACE[key]
        midi = BASS_OPEN[s] + f
        _link(p, os.path.join(STAGED, "fretless_fdv"), midi, s, f)
        if f:
            _link(p, os.path.join(STAGED, "fretless_fdv_stopped"), midi, s, f)
        n += 1
    for p in glob.glob(os.path.join(FRETLESS, "mrforfs", "*fretless-bass-open-*.wav")):
        m = re.search(r"open-([a-g])-(neck|bridge|both)", p)
        s, midi = MRF_OPEN[m.group(1)]
        _link(p, os.path.join(STAGED, "fretless_open_%s" % m.group(2)), midi, s, 0)
        n += 1
    return n


# THE STEEL-STRING (GM 25): NYU's GuitarSet (CC BY 4.0; sources.md), a steel-string
# acoustic on a MICROPHONE -- no DI here: what is measured is the string, the
# pluck and the BODY, as GM 25 renders them. Recorded as music, so a note is
# taken only where it sounds ALONE: no other note starting within 0.6 s of it
# or still sounding at its onset, and at least 0.4 s long by the annotation
# (JAMS note_midi, per string). 493 of 62476. Each cut from 50 ms before its
# onset to the next note (at most 3 s) and written -- clips, not links -- as
# <note><octave>.s<string>f<fret>.wav, strings numbered 1-6 from the low E.
GUITARSET = os.path.expanduser("~/Documents/refs/guitarset")
GS_OPEN = (40, 45, 50, 55, 59, 64)


def stage_guitarset():
    import json
    from scipy.io import wavfile
    out = os.path.join(STAGED, "acoustic_steel_mic")
    if os.path.isdir(out) and glob.glob(os.path.join(out, "*.wav")):
        return len(glob.glob(os.path.join(out, "*.wav")))
    os.makedirs(out, exist_ok=True)
    n = 0
    for jp in sorted(glob.glob(os.path.join(GUITARSET, "annotation", "*.jams"))):
        wav = os.path.join(GUITARSET, "audio_mono-mic", os.path.basename(jp)[:-5] + "_mic.wav")
        if not os.path.exists(wav):
            continue
        notes = []
        for a in json.load(open(jp))["annotations"]:
            if a["namespace"] == "note_midi":
                st = int(a["annotation_metadata"]["data_source"])
                notes += [(d["time"], d["time"] + d["duration"], d["value"], st) for d in a["data"]]
        notes.sort()
        sr, x = None, None
        for k, (t0, t1, m, st) in enumerate(notes):
            if t1 - t0 < 0.4 or any(o is not notes[k] and o[0] < t0 + 0.6 and o[1] > t0 - 0.05 for o in notes):
                continue
            if x is None:
                sr, x = wavfile.read(wav)
            nxt = min([o[0] for o in notes if o[0] > t0] + [t0 + 3.0])
            midi = int(round(m))
            fret = midi - GS_OPEN[st]
            if not 0 <= fret <= 22:
                continue
            seg = x[max(0, int((t0 - 0.05) * sr)):int(min(nxt, t0 + 3.0) * sr)]
            dst = os.path.join(out, "%s.s%df%02d.%s_%d.wav" % (_name(midi), st + 1, fret,
                                                               os.path.basename(jp)[:-5].replace(".", ""), k))
            wavfile.write(dst, sr, seg)
            n += 1
    return n


def sets():
    return sorted(os.path.basename(d) for d in glob.glob(os.path.join(STAGED, "*")) if os.path.isdir(d))


def rows_of(name):
    return [r for r in (measure(p) for p in sorted(glob.glob(os.path.join(STAGED, name, "*.wav")))) if r]


def decays(path, nm=8, t0=0.05, t1=1.8):
    """Each partial's decay, dB/s: its band (+-10 % around m f0, the
    stretch from the name's pitch), a 20 ms envelope, and a straight line
    through its dB from t0 to t1 after its peak. A FIT, because the partials
    BEAT -- two polarisations trading energy, a recorded E3's fundamental
    -11 dB at 0.6 s, -33 at 1.0, -15 at 1.5 -- and pizz_measure's
    partial_slope locked onto a beat or read nothing (and read our steady
    fundamental at -100 dB/s). The recordings end at ~2.5 s, so t1 stays
    under it."""
    from scipy.signal import butter, sosfiltfilt
    from voicefit import mono, note_of
    x, sr = mono(path)
    x = np.asarray(x, np.float64)
    f0 = 440.0 * 2 ** ((note_of(path) - 69) / 12.0)
    w = int(0.02 * sr)
    # THE NOTE'S OWN SPAN: its onset (the 20 ms envelope first within 20 dB
    # of its peak -- the basses start at ~0.48 s, the guitars at ~0.2), and
    # its end before any DAMP (the basses are stopped at ~2 s: a fall of more
    # than 12 dB inside 100 ms), so the line is the ring's alone
    E = 20 * np.log10(np.sqrt(np.convolve(x * x, np.ones(w) / w, "same")) + 1e-12)
    on = int(np.flatnonzero(E > E.max() - 20)[0])
    end = len(E)
    h = int(0.1 * sr)
    for i in range(on + int(0.2 * sr), len(E) - h, w):
        if E[i + h] < E[i] - 12:
            end = i - int(0.05 * sr)
            break
    out = []
    for m in range(1, nm + 1):
        fm = m * f0
        if fm * 1.1 > 0.45 * sr:
            break
        y = sosfiltfilt(butter(4, [fm * 0.9, fm * 1.1], btype="band", fs=sr, output="sos"), x)
        e = 20 * np.log10(np.sqrt(np.convolve(y * y, np.ones(w) / w, "same")) + 1e-12)
        pk = on + int(np.argmax(e[on:on + int(0.3 * sr)]))
        a, b = pk + int(t0 * sr), min(end, pk + int(t1 * sr))
        if b - a < int(0.5 * sr) or e[pk] < e.max() - 60:
            out.append(np.nan)
            continue
        t = np.arange(a, b, w) / sr
        out.append(-float(np.polyfit(t, e[a:b:w], 1)[0]))
    return np.array(out + [np.nan] * (nm - len(out)))


def decay_report(paths, title):
    """Median decay per partial, by octave."""
    from voicefit import note_of
    by = {}
    for p in paths:
        by.setdefault(note_of(p) // 12 - 1, []).append(decays(p))
    print("   %s: decay dB/s, partials 1-8, median by octave" % title)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for o in sorted(by):
            print("     oct %d (%2d)  " % (o, len(by[o])) + " ".join("%5.1f" % v for v in np.nanmedian(np.array(by[o]), 0)))


# THE STRING, SHARED BY A FAMILY: what is fitted on the base classes. The
# decay and the stretch are the string's, not the pickup's or the hand's, so
# every guitar setup is pooled for ElectricGuitarProperties (26-31 inherit)
# and the finger and pick sets of all three basses for ElectricBassProperties.
STRING_SETS = {
    "guitar": ("strat_neck_sc", "ibanez_bridge_hu", "ibanez_neck_hu", "ibanez_bridge_neck_sc"),
    "bass": tuple("bass_%s_both_%s" % (b, st) for b in ("fame", "warwick", "yamaha") for st in ("FS", "PK")),
    # the fretless's own string: its STOPPED notes, where the finger on the
    # wood is the termination (FretlessBassProperties)
    "fretless": ("fretless_fdv_stopped",),
    # the steel-string acoustic (GM 25): GuitarSet's isolated notes, on a
    # microphone -- the string's decay heard through the body
    "steel": ("acoustic_steel_mic",),
}
REF_HZ = 415.0


def fit_string(family, step=1):
    """The decay law and the stretch law of a family's string.

    DECAY, pizz_fit's convention: the class's dB/s is half the envelope's
    (harmonic_decay of 1 renders 2 dB/s an harmonic, measured), so the
    measured rates are halved and fitted as (decay_db + harmonic_decay_db m)
    (f0/415)^decay_register_slope, in logs, soft_l1. STRETCH: each note's B
    (pizz_measure, partials 2-12) fitted as B = k f0^p, the upright's wound
    law with one segment -- a guitar's pitch does not say which string."""
    from scipy.optimize import least_squares
    from voicefit import note_of
    pts, Bs = [], []
    for name in STRING_SETS[family]:
        for p in sorted(glob.glob(os.path.join(STAGED, name, "*.wav")))[::step]:
            f0 = 440.0 * 2 ** ((note_of(p) - 69) / 12.0)
            for m, d in enumerate(decays(p), 1):
                if np.isfinite(d) and d > 0.2:
                    pts.append((m, f0, d / 2.0))
            r = measure(p)
            if r and r["B"] > 0:
                Bs.append((r["f0"], r["B"]))
    m = np.array([q[0] for q in pts], float)
    f = np.array([q[1] for q in pts], float)
    D = np.array([q[2] for q in pts], float)

    def res(q):
        a, b, sl = q
        return np.log(np.maximum(a + b * m, 1e-6)) + sl * np.log(f / REF_HZ) - np.log(D)
    r = least_squares(res, [2.0, 1.0, 0.0], bounds=([0.0, 0.0, -1.0], [100.0, 50.0, 3.0]),
                      loss="soft_l1", f_scale=0.3)
    a, b, sl = r.x
    err = float(np.median(np.abs(res(r.x))))
    fB = np.array([q[0] for q in Bs]); vB = np.array([q[1] for q in Bs])
    pB, lk = np.polyfit(np.log(fB), np.log(vB), 1)
    eB = float(np.median(np.abs(np.log(vB) - (lk + pB * np.log(fB)))))
    print("  %s: %d decay points, %d stretches" % (family, len(pts), len(Bs)))
    print("    decay_db = %.3f\n    harmonic_decay_db = %.3f\n    decay_register_slope = %.3f"
          "   (median |log err| %.2f)" % (a, b, sl, err))
    print("    inharmonicity_law = (%.4g, %.3f)   B = k f0^p: %.2e at 82 Hz, %.2e at 330   (median |log err| %.2f)"
          % (np.exp(lk), pB, np.exp(lk) * 82.4 ** pB, np.exp(lk) * 329.6 ** pB, eB))
    return a, b, sl, (float(np.exp(lk)), float(pB))


# EACH PROGRAM'S SPECTRUM, against the setup it is fitted to: GM 26 jazz the
# neck humbucker, 27 clean the Stratocaster's neck single coil, 29/30 the
# bridge humbucker (their amplifier downstream, unchanged), 33/34/36/37 the
# basses' finger, pick, slap-thumb and slap-pluck on both pickups.
PROGRAM_SETS = {
    26: ("ibanez_neck_hu",),
    27: ("strat_neck_sc",),
    29: ("ibanez_bridge_hu",),
    30: ("ibanez_bridge_hu",),
    33: tuple("bass_%s_both_FS" % b for b in ("fame", "warwick", "yamaha")),
    34: tuple("bass_%s_both_PK" % b for b in ("fame", "warwick", "yamaha")),
    36: tuple("bass_%s_both_ST" % b for b in ("fame", "warwick", "yamaha")),
    37: tuple("bass_%s_both_SP" % b for b in ("fame", "warwick", "yamaha")),
    # the fretless: FaireDesVagues' fifteen, open and stopped
    35: ("fretless_fdv",),
    # the steel-string acoustic: GuitarSet's notes that sound alone, on its
    # microphone (the --ab's reference; its body is examples/steel_fit.py's)
    25: ("acoustic_steel_mic",),
}
# THE PICKUPS THE REFERENCES WERE PLAYED ON, as fractions of a 648 mm scale
# from the bridge: a Stratocaster neck coil ~160 mm (0.247, its ~9 mm coil
# 0.014 wide); the RG2820's humbuckers two coils ~18 mm apart, the bridge's
# centre ~40 mm (0.049, 0.077: GM 30's class already) and the neck's ~155 mm
# (0.23, 0.258: GM 26's). The basses' "both" is two coils; a Jazz bass's sit
# ~85 and ~145 mm along an 864 mm scale (0.098, 0.168).
PICKUP_GEOMETRY = {
    26: dict(pickup_points=(0.23, 0.258)),
    27: dict(pickup_points=(0.247,)),
    29: dict(pickup_points=(0.049, 0.077)),
    30: dict(pickup_points=(0.049, 0.077)),
    33: dict(pickup_points=(0.098, 0.168)),
    34: dict(pickup_points=(0.098, 0.168)),
    36: dict(pickup_points=(0.098, 0.168)),
    37: dict(pickup_points=(0.098, 0.168)),
    # FaireDesVagues does not say which bass: a Jazz bass's two coils, as 33's
    35: dict(pickup_points=(0.098, 0.168)),
}
BASS_PICKUP = (4867.0, 1.046)      # --ladder=34's, the pick's
LADDER_KNOBS = ("strike_point", "strike_depth", "tonal_dampening", "pickup_resonance_hz", "pickup_q")
BOUNDS = {"strike_point": (0.03, 0.45), "strike_depth": (0.0, 1.0), "tonal_dampening": (0.5, 4.0),
          "pickup_resonance_hz": (800.0, 12000.0), "pickup_q": (0.3, 4.0)}


def ladder_at(cls, f0, fret, nm=10, vel=80):
    """The class's ladder (pizz_fit.ladder_of's window and decay) for a note
    played at FRET, as the reference was -- not where the class would put it."""
    pr = cls(f0, 0.0, (vel / 127.0) ** 2, 1.0)
    base = cls.__mro__[1] if cls.__name__ == "Fit" else cls
    sc = 2.0 ** (fret / 12.0)
    pr.pickup_points = tuple(min(q * sc, 0.5) for q in cls.pickup_points)
    pr.strike_point = min(cls.strike_point * sc, 0.5)
    a = np.array([abs(pr.harmonic_volume(m)) * pr.radiation_gain(m * f0) for m in range(1, nm + 1)])
    D = np.array([pr.harmonic_decay(m) for m in range(1, nm + 1)])
    return 20 * np.log10(np.maximum(a, 1e-12) / max(a[0], 1e-12)) - 2 * 0.035 * (D - D[0])


# HOW HIGH A PROGRAM'S LADDER IS JUDGED. h2-h10 by default; the fretless to
# h16, all pizz_measure reads: judged to h10 it fitted its pickup's
# resonance at 6.6 kHz, past every harmonic it saw (h10 of E2 is 820 Hz),
# and rang bright to 3 kHz where FaireDesVagues' falls 40-55 dB by h12-16 --
# Ben: "starts too high", and its pickups' comb, laid bare up there, "a
# phaser"
LADDER_NM = {35: 16}


def ladder_obs(names, nm=10):
    obs = []
    for name in names:
        for p in sorted(glob.glob(os.path.join(STAGED, name, "*.wav"))):
            r = measure(p)
            fret = int(re.search(r"f(\d+)\.", os.path.basename(p)).group(1))
            if r and len(r["ladder"]) >= nm:
                obs.append((r["f0"], fret, np.asarray(r["ladder"][:nm])))
    return obs


def ladder_error(cls, obs):
    errs = []
    for f0, fret, L in obs:
        M = ladder_at(cls, f0, fret, nm=len(L))
        ok = L[1:] > -60
        errs.extend(np.abs(M[1:] - L[1:])[ok])
    return float(np.median(errs))


def fit_ladder(prog, knobs=LADDER_KNOBS, **fixed):
    """The pick, its notch, the tilt and the pickup's resonance, fitted to
    the program's references' ladders (h2-h10, where the recording stands
    within 60 dB of its fundamental), each note at its own fret. Nelder-Mead
    in logs, out of bounds a penalty."""
    from scipy.optimize import minimize
    import patch_map
    base = type("Base", (patch_map.property_class_for_program(prog),),
                dict(PICKUP_GEOMETRY.get(prog, {}), **fixed))
    if "pickup_resonance_hz" in knobs and not base.pickup_resonance_hz:
        base.pickup_resonance_hz, base.pickup_q = 4000.0, 1.0
    obs = ladder_obs(PROGRAM_SETS[prog], LADDER_NM.get(prog, 10))
    x0 = np.log([getattr(base, k) or 1e-3 for k in knobs])
    e0 = ladder_error(type("Fit", (base,), {}), obs)

    def f(x):
        v = np.exp(x)
        pen = sum(max(0.0, BOUNDS[k][0] - q) + max(0.0, q - BOUNDS[k][1]) for k, q in zip(knobs, v))
        if pen:
            return 100.0 + pen
        return ladder_error(type("Fit", (base,), dict(zip(knobs, v))), obs)
    # a WIDE first simplex: the default 5 % of each log is ~0.08, and the
    # search never left its start (6.71 -> 6.20 on the first try)
    sim = np.vstack([x0] + [x0 + 0.4 * np.eye(len(x0))[i] for i in range(len(x0))])
    r = minimize(f, x0, method="Nelder-Mead",
                 options=dict(maxfev=600, xatol=1e-3, fatol=1e-3, initial_simplex=sim))
    v = np.exp(r.x)
    print("  GM %d: %d notes, ladder miss %.2f dB (from %.2f)" % (prog, len(obs), r.fun, e0))
    for k, q in zip(knobs, v):
        print("    %s = %.4g" % (k, q))
    return dict(zip(knobs, v)), r.fun


ENV_BANDS = 50.0 * 2 ** (np.arange(0, 22) / 3.0)        # 50 Hz .. 6.4 kHz


def env_obs(names):
    """The recorded envelope BY ABSOLUTE FREQUENCY (examples/steel_fit.py's:
    every harmonic of every note, 40-140 ms, each note's level removed,
    third-octave medians), and each note's (f0, fret) to place ours at."""
    import steel_fit as SF
    SF.BANDS = ENV_BANDS
    paths = [p for name in names for p in sorted(glob.glob(os.path.join(STAGED, name, "*.wav")))]
    R, n = SF.envelope(paths)
    notes = []
    for p in paths:
        r = measure(p)
        if r:
            notes.append((r["f0"], int(re.search(r"f(\d+)\.", os.path.basename(p)).group(1))))
    return R, notes


def env_model(cls, notes):
    """Ours, the same way, from the class's own harmonic levels (ladder_at)."""
    pool = [[] for _ in ENV_BANDS]
    for f0, fret in notes:
        nm = int(min(6000.0 / f0, 80))
        L = ladder_at(cls, f0, fret, nm=nm)
        hz = f0 * np.arange(1, nm + 1)
        ref = (hz > 150) & (hz < 3000)
        if not ref.any():
            continue
        L = L - 10 * np.log10(np.mean(10 ** (L[ref] / 10)))
        for h, d in zip(hz, L):
            k = int(np.argmin(np.abs(np.log2(h / ENV_BANDS))))
            if abs(np.log2(h / ENV_BANDS[k])) <= 1 / 6.0:
                pool[k].append(d)
    return np.array([np.median(v) if len(v) >= 5 else np.nan for v in pool])


def fit_envelope(prog, knobs=("lowpass_hz", "lowpass_order", "tonal_dampening")):
    """--envelope=PROG: the knobs that shape the TOP, fitted on the envelope
    by absolute frequency (bands with 5+ harmonics, down to -60 dB), where a
    ladder of the first ten or sixteen harmonics never reaches it. The
    pickup's two-pole resonance could not reach it (it sat at 9 kHz, 1-3 kHz
    15-20 dB over FaireDesVagues'): a LOW-PASS (tonelib lowpass_hz, its order)
    at one frequency whatever the note, which is what the takes show."""
    from scipy.optimize import minimize
    import patch_map
    R, notes = env_obs(PROGRAM_SETS[prog])
    base = type("Base", (patch_map.property_class_for_program(prog),), dict(PICKUP_GEOMETRY.get(prog, {})))
    lo = dict(BOUNDS, lowpass_hz=(150.0, 12000.0), lowpass_order=(0.5, 6.0))

    def err(cls):
        M = env_model(cls, notes)
        ok = np.isfinite(R) & np.isfinite(M) & (R > -60)
        d = M[ok] - R[ok]
        # the MEAN: a median let the top bands -- the ones in question --
        # sit 20-40 dB out and scored 0.72 dB
        return float(np.mean(np.abs(d - np.mean(d))))
    start = dict(lowpass_hz=800.0, lowpass_order=2.0)
    x0 = np.log([getattr(base, k) or start[k] for k in knobs])
    e0 = err(type("Fit", (base,), {}))

    def f(x):
        v = np.exp(x)
        pen = sum(max(0.0, lo[k][0] - q) + max(0.0, q - lo[k][1]) for k, q in zip(knobs, v))
        return 100.0 + pen if pen else err(type("Fit", (base,), dict(zip(knobs, v))))
    sim = np.vstack([x0] + [x0 + 0.6 * np.eye(len(x0))[i] for i in range(len(x0))])
    r = minimize(f, x0, method="Nelder-Mead", options=dict(maxfev=400, xatol=1e-3, fatol=1e-3,
                                                          initial_simplex=sim))
    v = np.exp(r.x)
    M = env_model(type("Fit", (base,), dict(zip(knobs, v))), notes)
    print("  GM %d: %d notes, envelope miss %.2f dB (from %.2f)" % (prog, len(notes), r.fun, e0))
    for k, q in zip(knobs, v):
        print("    %s = %.4g" % (k, q))
    print("   band Hz  " + " ".join("%5.0f" % c for c in ENV_BANDS))
    print("   recorded " + " ".join("%5.0f" % q if np.isfinite(q) else "   --" for q in R))
    print("   ours     " + " ".join("%5.0f" % q if np.isfinite(q) else "   --" for q in M))
    return dict(zip(knobs, v)), r.fun


MODEL = os.path.join(REFS, "model")


def di_class(prog, **over):
    """The GM program's class as a DI recording hears it: no amplifier, no
    cabinet -- the string and the pickup."""
    import patch_map
    base = patch_map.property_class_for_program(prog)
    return type("DI", (base,), dict(dict(amp_drive=0.0, cabinet=None), **over))


def render_note(prog, key, out, secs=2.5, vel=90):
    import mido
    import wave
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=prog, time=0))
    t.append(mido.Message("note_on", channel=0, note=key, velocity=vel, time=0))
    t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(secs * 960)))
    L, R = B.render(m)[:2]
    x = 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64))
    x = x / max(np.abs(x).max(), 1e-12) * 0.5
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(B.SR)
    w.writeframes((x * 32767).astype("<i2").tobytes()); w.close()


def model_rows(name, prog, cls=None, step=1):
    """Ours at every staged note of NAME (or every STEP-th), rendered DI
    through program PROG's class (or CLS), measured the same way."""
    import patch_map
    from voicefit import note_of
    keep = patch_map.PROGRAM_CLASS.get(prog)
    patch_map.PROGRAM_CLASS[prog] = cls or di_class(prog)
    d = os.path.join(MODEL, "%s_%d" % (name, prog))
    os.makedirs(d, exist_ok=True)
    rows = []
    try:
        for p in sorted(glob.glob(os.path.join(STAGED, name, "*.wav")))[::step]:
            out = os.path.join(d, os.path.basename(p))
            render_note(prog, note_of(p), out)
            r = measure(out)
            if r:
                rows.append(r)
    finally:
        if keep is not None:
            patch_map.PROGRAM_CLASS[prog] = keep
    return rows


def damp(path):
    """The player's damp at the end of a bass note: (rate dB/s, the level it
    falls from re the note's peak), or None. Its start is the first 20 ms
    step after the ring where the 5 ms envelope falls more than 12 dB inside
    100 ms; the rate a line through its first 25 dB (or to 10 dB over the
    floor, whichever comes first)."""
    from voicefit import mono
    x, sr = mono(path)
    x = np.asarray(x, np.float64)
    w = int(0.005 * sr)
    E = 20 * np.log10(np.sqrt(np.convolve(x * x, np.ones(w) / w, "same")) + 1e-12)
    pk = int(np.argmax(E))
    floor = float(np.percentile(E[-int(0.1 * sr):], 50))
    h, st = int(0.1 * sr), int(0.02 * sr)
    for i in range(pk + int(0.3 * sr), len(E) - h, st):
        if E[i + h] < E[i] - 12:
            # back up to where the fall really begins
            j = i
            while j > pk and E[j - st] < E[j] + 1.0:
                j -= st
            stop = min(E[j] - 25, floor + 10)
            if E[j] - stop < 10:
                return None
            k = j + int(np.argmax(E[j:] < stop))
            if k <= j + w:
                return None
            t = np.arange(j, k) / sr
            return -float(np.polyfit(t, E[j:k], 1)[0]), float(E[j] - E[pk])
    return None


def fit_damp(styles=("FS", "PK", "ST", "SP")):
    """--damp: the release of the basses, from the damps that end their notes
    (IDMT-SMT-Bass: every note is stopped by hand at ~2 s). Per style, the
    median rate over the three basses and both pickups' notes; mapped to our
    release as gm_release does, at the same -40 dB point: a damp falling R
    dB/s reaches -40 dB in 40/R s, our smoothstep at 0.94 of its length."""
    from voicefit import note_of
    out = {}
    for st in styles:
        rates, by = [], {}
        for b in ("fame", "warwick", "yamaha"):
            for pu in ("neck", "both", "bridge"):
                for p in sorted(glob.glob(os.path.join(STAGED, "bass_%s_%s_%s" % (b, pu, st), "*.wav"))):
                    d = damp(p)
                    if d:
                        rates.append(d[0])
                        by.setdefault(note_of(p) // 12 - 1, []).append(d[0])
        R = float(np.median(rates))
        L = 40.0 / R / 0.94
        out[st] = L
        print("  %s: %d damps, median %.0f dB/s (quartiles %.0f-%.0f); -40 dB in %.3f s -> release_valve_time %.3f"
              "   by octave %s" % (st, len(rates), R, np.percentile(rates, 25), np.percentile(rates, 75),
                                   40.0 / R, L, " ".join("%d:%.0f" % (o, np.median(v)) for o, v in sorted(by.items()))))
    return out


G2 = os.path.join(REFS, "guitar", "IDMT-SMT-GUITAR_V2", "dataset2")


def _events(xml):
    out = []
    for ev in ET.parse(xml).getroot().iter("event"):
        out.append(dict(pitch=int(ev.findtext("pitch")), on=float(ev.findtext("onsetSec")),
                        off=float(ev.findtext("offsetSec")), fret=int(ev.findtext("fretNumber")),
                        style=ev.findtext("excitationStyle")))
    return out


def seg_decays(x, sr, f0, a, b, nm=4):
    """Partials 1-NM's decay (dB/s, a line through the band's 10 ms
    envelope) between A and B seconds, from its peak in the first 50 ms."""
    from scipy.signal import butter, sosfiltfilt
    seg = x[int(a * sr):int(b * sr)]
    w = int(0.01 * sr)
    out = []
    for m in range(1, nm + 1):
        y = sosfiltfilt(butter(4, [m * f0 * 0.9, m * f0 * 1.1], btype="band", fs=sr, output="sos"), seg)
        e = 20 * np.log10(np.sqrt(np.convolve(y * y, np.ones(w) / w, "same")) + 1e-12)
        pk = int(np.argmax(e[:int(0.05 * sr)]))
        k = len(e) - int(0.02 * sr)
        if k - pk < int(0.08 * sr):
            out.append(np.nan)
            continue
        t = np.arange(pk, k, w) / sr
        out.append(-float(np.polyfit(t, e[pk:k:w], 1)[0]))
    return out


def fit_mute():
    """--mute: the PALM MUTE, measured like for like. IDMT-SMT-Guitar's
    dataset 2 has three guitars (Aristides, Stratocaster, Les Paul) playing
    five palm-muted notes at the fifth fret of each string, and the same
    strings run open, fret by fret: each muted note's decay against the open
    note at the same fret of the same string on the same guitar, partials
    1-4, over each note's annotated span."""
    from voicefit import mono
    rat = {m: [] for m in range(1, 5)}
    absd = {m: [] for m in range(1, 5)}
    lad_pairs = []
    for mx in sorted(glob.glob(os.path.join(G2, "annotation", "*_muted5.xml"))):
        stem = os.path.basename(mx)[:-len("_muted5.xml")]
        fx = os.path.join(G2, "annotation", stem + "_fret_0-20.xml")
        if not os.path.exists(fx):
            continue
        xm, sr = mono(os.path.join(G2, "audio", stem + "_muted5.wav"))
        xf, _ = mono(os.path.join(G2, "audio", stem + "_fret_0-20.wav"))
        xm, xf = np.asarray(xm, np.float64), np.asarray(xf, np.float64)
        muted = _events(mx)
        opens = {e["fret"]: e for e in _events(fx)}
        for e in muted:
            o = opens.get(e["fret"])
            if o is None:
                continue
            f0 = 440.0 * 2 ** ((e["pitch"] - 69) / 12.0)
            dm = seg_decays(xm, sr, f0, e["on"], e["off"])
            do = seg_decays(xf, sr, f0, o["on"], o["off"])
            lm = seg_ladder(xm, sr, f0, e["on"], e["off"])
            lo = seg_ladder(xf, sr, f0, o["on"], o["off"])
            if lm is not None and lo is not None and len(lm) >= 6 and len(lo) >= 6:
                lad_pairs.append((lm[1:6], lo[1:6]))
            for m in range(1, 5):
                if np.isfinite(dm[m - 1]) and np.isfinite(do[m - 1]) and do[m - 1] > 0.5:
                    rat[m].append(dm[m - 1] / do[m - 1])
                    absd[m].append(dm[m - 1])
    print("  palm mute against the open string, same guitar, string and fret:")
    if lad_pairs:
        print("    ladder h2-h6 at onset, muted | open: %s | %s" % (
            " ".join("%5.1f" % v for v in np.nanmedian([p_[0] for p_ in lad_pairs], 0)),
            " ".join("%5.1f" % v for v in np.nanmedian([p_[1] for p_ in lad_pairs], 0))))
    for m in range(1, 5):
        print("    h%d: %d pairs, muted decays %.1f x the open (quartiles %.1f-%.1f); muted %.0f dB/s (median)"
              % (m, len(rat[m]), np.median(rat[m]), np.percentile(rat[m], 25), np.percentile(rat[m], 75),
                 np.median(absd[m])))
    return {m: float(np.median(rat[m])) for m in rat}, {m: float(np.median(absd[m])) for m in absd}


def seg_ladder(x, sr, f0, a, b, nm=10):
    """A segment's ladder, as pizz_measure reads a file's: partials 1-NM in
    the 60 ms after the envelope's peak, dB under the first, each the peak
    within a quarter of f0 of m f0."""
    seg = x[int(a * sr):int(b * sr)]
    w = int(0.01 * sr)
    e = np.sqrt(np.convolve(seg * seg, np.ones(w) / w, "same"))
    pk = int(np.argmax(e[:int(0.1 * sr)]))
    s2 = seg[pk + int(0.005 * sr):pk + int(0.065 * sr)]
    if len(s2) < int(0.05 * sr):
        return None
    N = 1 << 18
    X = np.abs(np.fft.rfft(s2 * np.hanning(len(s2)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    lad = []
    for m in range(1, nm + 1):
        bw = (f > m * f0 - 0.25 * f0) & (f < m * f0 + 0.25 * f0)
        if m * f0 > 0.45 * sr:
            break
        lad.append(X[bw].max())
    lad = np.array(lad)
    return 20 * np.log10(np.maximum(lad, 1e-12) / max(lad[0], 1e-12))


TOUCH = {"XII": 2, "VII": 3, "V": 4, "IV": 5, "IX": 5}


def technique_notes(kind):
    """Dataset 2's palm-muted notes (kind 'mute': five at the fifth fret of
    each string) or natural harmonics (kind 'harm': touched over frets 12, 7,
    5, 4 and 9 -- harmonics 2, 3, 4, 5, 5 -- on each string), three guitars:
    (audio, onset, offset, sounding Hz, fret, touch)."""
    out = []
    pat = "*_muted5.xml" if kind == "mute" else "*_NH_*.xml"
    for x in sorted(glob.glob(os.path.join(G2, "annotation", pat))):
        stem = os.path.basename(x)[:-4]
        n = TOUCH[stem.split("_NH_")[1]] if kind == "harm" else 1
        for e in _events(x):
            out.append((os.path.join(G2, "audio", stem + ".wav"), e["on"], e["off"],
                        440.0 * 2 ** ((e["pitch"] - 69) / 12.0), e["fret"], n))
    return out


def technique_report(kind, prog):
    """--technique=mute|harm: the recorded notes' ladders and decays by
    octave, and ours (GM PROG, DI) at the same sounding pitches."""
    from voicefit import mono
    import patch_map
    rows = technique_notes(kind)
    cache, R = {}, []
    for wav, a, b, f0, fret, n in rows:
        if wav not in cache:
            x, sr = mono(wav)
            cache[wav] = (np.asarray(x, np.float64), sr)
        x, sr = cache[wav]
        L = seg_ladder(x, sr, f0, a, b)
        D = seg_decays(x, sr, f0, a, b)
        if L is not None and len(L) >= 6:
            R.append((f0, n, L[:6], D))
    keep = patch_map.PROGRAM_CLASS.get(prog)
    patch_map.PROGRAM_CLASS[prog] = di_class(prog)
    O = []
    tmp = os.path.join(MODEL, "_t.wav")
    os.makedirs(MODEL, exist_ok=True)
    try:
        done = {}
        for f0, n, L, D in R:
            key = int(round(69 + 12 * np.log2(f0 / 440.0)))
            if key not in done:
                render_note(prog, key, tmp, secs=0.8 if kind == "mute" else 1.6)
                y, sr = mono(tmp)
                y = np.asarray(y, np.float64)
                E = np.sqrt(np.convolve(y * y, np.ones(441) / 441, "same"))
                if not E.max() > 0:
                    print("    (ours is silent at key %d)" % key)
                    done[key] = (np.full(6, np.nan), [np.nan] * 4)
                    O.append(done[key])
                    continue
                on = np.flatnonzero(E > E.max() * 0.1)[0] / sr
                done[key] = (seg_ladder(y, sr, f0, max(0, on - 0.01), on + (0.7 if kind == "mute" else 1.5)),
                             seg_decays(y, sr, f0, max(0, on - 0.01), on + (0.7 if kind == "mute" else 1.5)))
            else:
                O.append(done[key])
                continue
            O.append(done[key])
    finally:
        if keep is not None:
            patch_map.PROGRAM_CLASS[prog] = keep
    by = {}
    for (f0, n, L, D), (Lo, Do) in zip(R, O):
        by.setdefault(int(np.log2(f0 / 32.70)), []).append((L, D, Lo[:6], Do))
    import warnings
    warnings.simplefilter("ignore")
    print("  %s: %d notes; ladder h2-h6 dB re h1, decay h1-h4 dB/s -- recorded | ours" % (kind, len(R)))
    for o in sorted(by):
        v = by[o]
        print("   oct %d (%2d)  lad %s | %s    dec %s | %s" % (
            o + 1, len(v),
            " ".join("%5.1f" % q for q in np.nanmedian([a[0][1:] for a in v], 0)),
            " ".join("%5.1f" % q for q in np.nanmedian([a[2][1:] for a in v], 0)),
            " ".join("%4.0f" % q for q in np.nanmedian([a[1] for a in v], 0)),
            " ".join("%4.0f" % q for q in np.nanmedian([a[3] for a in v], 0))))


def technique_obs(kind):
    """Each recorded note of the technique: (sounding Hz, touch, string fret,
    onset ladder h1-h6, decays h1-h4)."""
    from voicefit import mono
    cache, out = {}, []
    for wav, a, b, f0, fret, n in technique_notes(kind):
        if wav not in cache:
            x, sr = mono(wav)
            cache[wav] = (np.asarray(x, np.float64), sr)
        x, sr = cache[wav]
        L = seg_ladder(x, sr, f0, a, b, nm=6)
        if L is not None and len(L) >= 6:
            out.append((f0, n, 0 if kind == "harm" else fret, L, seg_decays(x, sr, f0, a, b)))
    return out


def technique_ladder(cls, f0, n, fret, nm=6, vel=80):
    """The class's onset ladder for a note at touch N on its string's FRET,
    as the recording played it (not where the class would choose)."""
    sub = type("T", (cls,), dict(touches=(), harmonic_touch=n if n > 1 else 0))
    pr = sub(f0, 0.0, (vel / 127.0) ** 2, 1.0)
    sc = 2.0 ** (fret / 12.0)
    pr.pickup_points = tuple(min(q * sc, 0.5) for q in cls.pickup_points)
    pr.strike_point = min(cls.strike_point * sc, 0.5)
    a = np.array([abs(pr.harmonic_volume(m)) * pr.radiation_gain(m * f0) for m in range(1, nm + 1)])
    D = np.array([pr.harmonic_decay(m) for m in range(1, nm + 1)])
    return 20 * np.log10(np.maximum(a, 1e-12) / max(a[0], 1e-12)) - 2 * 0.035 * (D - D[0])


def fit_technique(kind):
    """--fit-technique=mute|harm: GM 28 or 31's pluck point, notch and tilt
    against the onset ladders (h2-h6, within 60 dB), each note at its own
    touch and fret, Nelder-Mead in logs; and its own decay law, (a + b m)
    (f0/415)^s fitted to its notes' measured decays (halved, as fit_string)."""
    from scipy.optimize import minimize, least_squares
    import patch_map
    prog = 28 if kind == "mute" else 31
    base = patch_map.property_class_for_program(prog)
    obs = technique_obs(kind)
    pts = [(m, f0, d / 2.0) for f0, n, fr, L, D in obs for m, d in enumerate(D, 1) if np.isfinite(d) and d > 0.2]
    mm = np.array([q[0] for q in pts], float); ff = np.array([q[1] for q in pts]); DD = np.array([q[2] for q in pts])

    def dres(q):
        a, b, sl = q
        return np.log(np.maximum(a + b * mm, 1e-6)) + sl * np.log(ff / REF_HZ) - np.log(DD)
    r = least_squares(dres, [5.0, 1.0, 0.0], bounds=([0.0, 0.0, -1.0], [200.0, 100.0, 3.0]),
                      loss="soft_l1", f_scale=0.3)
    da, db, ds = r.x
    dec = dict(decay_db=float(da), harmonic_decay_db=float(db), decay_register_slope=float(ds))
    # GM 31 fits its COIL too: a touched harmonic reads only modes n m, and a
    # coil on one of their nodes reads nothing (the neck coil's 0.247 is the
    # quarter point: touch 2's h2, string mode 4, came out 37 dB under the
    # recordings'), and dataset 2 does not say which pickups its three
    # guitars were on, so the comb is the data's to place
    knobs = ("strike_point", "strike_depth", "tonal_dampening") + (("pickup_at",) if kind == "harm" else ())

    def mk(b, vals):
        d = dict(vals)
        if "pickup_at" in d:
            d["pickup_points"] = (d.pop("pickup_at"),)
        return type("F", (b,), d)

    def err(cls):
        e = []
        for f0, n, fr, L, D in obs:
            M = technique_ladder(cls, f0, n, fr)
            ok = L[1:] > -60
            e.extend(np.abs(M[1:] - L[1:])[ok])
        return float(np.median(e))
    b0 = type("B", (base,), dec)
    e0 = err(base)
    x0 = np.log([getattr(base, k) if k != "pickup_at" else 0.16 for k in knobs])
    sim = np.vstack([x0] + [x0 + 0.4 * np.eye(len(knobs))[i] for i in range(len(knobs))])
    bnd = dict(BOUNDS, pickup_at=(0.04, 0.3))

    def f(x):
        v = np.exp(x)
        pen = sum(max(0.0, bnd[k][0] - q) + max(0.0, q - bnd[k][1]) for k, q in zip(knobs, v))
        return 100.0 + pen if pen else err(mk(b0, zip(knobs, v)))
    rr = minimize(f, x0, method="Nelder-Mead", options=dict(maxfev=500, xatol=1e-3, fatol=1e-3, initial_simplex=sim))
    v = np.exp(rr.x)
    print("  GM %d (%s): %d notes; ladder miss %.2f dB (from %.2f); decay median |log err| %.2f over %d partials"
          % (prog, kind, len(obs), rr.fun, e0, float(np.median(np.abs(dres(r.x)))), len(pts)))
    for k, q in list(zip(knobs, v)) + list(dec.items()):
        print("    %s = %.4g" % (k, q))
    return dict(zip(knobs, v)), dec


S3 = 2 ** np.arange(np.log2(140), np.log2(16000), 1 / 3.0)


def between(x, sr, f0, t0, a=0.0, b=0.03):
    """THE PLUCK UNDER A HARMONIC: third-octave bands BETWEEN the sounding
    note's partials (each masked, +-12 % of f0), over A-B seconds after the
    onset T0 (samples), dB re the window's whole energy -- koto_fit.pluck's
    measure, on a segment. On a touched string that is the pick's click and
    the modes the finger has not yet killed."""
    n = 1 << 15
    f = np.fft.rfftfreq(n, 1.0 / sr)
    near = np.zeros_like(f, bool)
    for m in range(1, 200):
        if m * f0 > 0.5 * sr:
            break
        near |= np.abs(f - m * f0) < max(0.12 * f0, 15.0)
    seg = x[t0 + int(a * sr):t0 + int(b * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n)) ** 2 / len(seg)
    tot = X.sum()
    out = []
    for lo, hi in zip(S3[:-1], S3[1:]):
        m_ = (f >= lo) & (f < hi) & ~near
        out.append(10 * np.log10(X[m_].mean() * ((f >= lo) & (f < hi)).sum() / tot + 1e-30)
                   if m_.sum() > 3 else np.nan)
    return np.array(out), 10 * np.log10(X[~near].sum() + 1e-30)


def _onset(x, sr):
    w = max(1, int(0.001 * sr))
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
    return int(np.flatnonzero(e > e.max() * 0.1)[0])


def harm_pluck(passes=4, dbs=None):
    """--pluck=harm: the harmonics' pluck (Ben: "missing the pluck sound").
    Each recorded harmonic's between-the-partials bands over its first 30 ms
    and how far that energy has fallen by 30-80 ms; ours (GM 31, DI) measured
    the same way at the same pitch; strike_noise_db, a third-octave table,
    moved band by band toward the recordings (the median of recorded - ours),
    and strike_noise_dbs set from the measured fall."""
    from voicefit import mono
    import tonelib
    import patch_map
    cls = tonelib.GuitarHarmonicsProperties
    cen = np.sqrt(S3[:-1] * S3[1:])
    R, falls, keys = [], [], []
    cache = {}
    for wav, a, b, f0, fret, n in technique_notes("harm"):
        if wav not in cache:
            x, sr = mono(wav)
            cache[wav] = (np.asarray(x, np.float64), sr)
        x, sr = cache[wav]
        seg = x[int(a * sr) - int(0.02 * sr):int(b * sr)]
        t0 = _onset(seg, sr)
        b0, e0 = between(seg, sr, f0, t0, 0.0, 0.03)
        _, e1 = between(seg, sr, f0, t0, 0.03, 0.08)
        R.append(b0); falls.append((e0 - e1) / 0.05 * 0.5)
        keys.append(int(round(69 + 12 * np.log2(f0 / 440.0))))
    rate = float(np.median(falls))           # dB/s of the inter-partial energy, halved
    if not getattr(cls, "strike_noise_db", ()):
        cls.strike_noise_db = tuple((int(round(c)), -20.0) for c in cen)
    # THE FALL IS FITTED, NOT TAKEN: between-the-partials energy on OUR render
    # also holds the partials' slow skirts, so a table set to the recordings'
    # rate measured 100-126 dB/s where they read 230-280 (Ben: the low notes
    # "could use a little bit tighter pick"). Scanned (scratch pluckfall):
    # 320 reads 250-260 in octaves 4-5, as recorded.
    cls.strike_noise_dbs = dbs if dbs else round(max(rate, 50.0), 1)
    cls.strike_noise_fade_s = 0.001
    keep = patch_map.PROGRAM_CLASS.get(31)
    patch_map.PROGRAM_CLASS[31] = di_class(31)
    tmp = os.path.join(MODEL, "_p.wav")
    os.makedirs(MODEL, exist_ok=True)
    import warnings
    warnings.simplefilter("ignore")
    try:
        for k in range(passes + 1):
            patch_map.PROGRAM_CLASS[31] = di_class(31)
            O, done = [], {}
            for key in keys:
                if key not in done:
                    render_note(31, key, tmp, secs=0.5)
                    y, sr = mono(tmp)
                    y = np.asarray(y, np.float64)
                    done[key] = between(y, sr, 440.0 * 2 ** ((key - 69) / 12.0), _onset(y, sr))[0]
                O.append(done[key])
            d = np.nanmedian(np.array(R) - np.array(O), 0)
            print("  pass %d: pluck bands rec - ours, rms %.1f dB (fall %.0f dB/s halved)"
                  % (k, np.sqrt(np.nanmean(d ** 2)), cls.strike_noise_dbs), flush=True)
            if k == passes:
                break
            cls.strike_noise_db = tuple((hz, round(db + (float(dd) if np.isfinite(dd) else 0.0), 1))
                                        for (hz, db), dd in zip(cls.strike_noise_db, d))
    finally:
        if keep is not None:
            patch_map.PROGRAM_CLASS[31] = keep
    print("    strike_noise_db = %s" % (cls.strike_noise_db,))
    print("    strike_noise_dbs = %.1f\n    strike_noise_fade_s = 0.001" % cls.strike_noise_dbs)


def fit_leak(levels=(-20.0, -12.0, -6.0, 0.0), rates=(200.0, 400.0, 800.0), step=2, noise=False):
    """--leak: the touched string's other modes (tonelib touch_leak_db,
    touch_leak_dbs), in place of the noise pluck. A grid, each point rendered
    at every STEP-th recorded harmonic and scored three ways, summed: the
    first 30 ms between the partials (between(), median band difference), how
    far that falls by 30-80 ms, and the onset ladder (h2-h6, where a killed
    mode near a harmonic shows)."""
    from voicefit import mono
    import patch_map
    import warnings
    warnings.simplefilter("ignore")
    notes = technique_notes("harm")[::step]
    cache, R = {}, []
    for wav, a, b, f0, fret, n in notes:
        if wav not in cache:
            x, sr = mono(wav)
            cache[wav] = (np.asarray(x, np.float64), sr)
        x, sr = cache[wav]
        seg = x[int(a * sr) - int(0.02 * sr):int(b * sr)]
        t0 = _onset(seg, sr)
        b0, e0 = between(seg, sr, f0, t0)
        _, e1 = between(seg, sr, f0, t0, 0.03, 0.08)
        L = seg_ladder(seg, sr, f0, t0 / sr, len(seg) / sr, nm=6)
        R.append((f0, b0, e0 - e1, L))
    base = di_class(31)
    tmp = os.path.join(MODEL, "_l.wav")
    os.makedirs(MODEL, exist_ok=True)
    keep = patch_map.PROGRAM_CLASS.get(31)
    best = None
    try:
        for lv in levels:
            for rt in rates:
                d = dict(touch_leak_db=lv, touch_leak_dbs=rt)
                if not noise:
                    d["strike_noise_db"] = ()
                cls = type("L", (base,), d)
                patch_map.PROGRAM_CLASS[31] = cls
                eb, ef, el, done = [], [], [], {}
                for f0, b0, fall, L in R:
                    key = int(round(69 + 12 * np.log2(f0 / 440.0)))
                    if key not in done:
                        render_note(31, key, tmp, secs=0.6)
                        y, sr = mono(tmp)
                        y = np.asarray(y, np.float64)
                        u0 = _onset(y, sr)
                        o0, g0 = between(y, sr, f0, u0)
                        _, g1 = between(y, sr, f0, u0, 0.03, 0.08)
                        done[key] = (o0, g0 - g1, seg_ladder(y, sr, f0, u0 / sr, len(y) / sr, nm=6))
                    o0, ofall, M = done[key]
                    eb.append(np.nanmedian(np.abs(o0 - b0)))
                    ef.append(abs(ofall - fall))
                    if L is not None and M is not None and len(L) >= 6 and len(M) >= 6:
                        ok = L[1:] > -60
                        el.extend(np.abs(M[1:] - L[1:])[ok])
                sc = float(np.median(eb) + 0.5 * np.median(ef) + np.median(el))
                print("  leak %s dB, %4.0f dB/s%s: between %.1f dB, fall miss %.1f dB, onset ladder %.1f dB -> %.1f"
                      % ("none" if lv is None else "%+5.1f" % lv, rt, " + noise" if noise else "",
                         np.median(eb), np.median(ef), np.median(el), sc), flush=True)
                if best is None or sc < best[0]:
                    best = (sc, lv, rt)
    finally:
        if keep is not None:
            patch_map.PROGRAM_CLASS[31] = keep
    print("    touch_leak_db = %.1f\n    touch_leak_dbs = %.0f" % best[1:])
    return best


def ab_technique(kind, out, n=8):
    """--abtech=mute|harm:OUT.wav: N of dataset 2's palm-muted or harmonic
    notes across the range, each recorded then ours (GM 28 or 31, DI, at the
    same sounding pitch, held as long), level-matched on their first 0.3 s.
    Ours chooses its own touch, as the voice plays."""
    import wave
    from scipy.signal import resample_poly
    from voicefit import mono
    import patch_map
    prog = 28 if kind == "mute" else 31
    rows = sorted(technique_notes(kind), key=lambda r: r[3])
    pick = [rows[int(i)] for i in np.linspace(0, len(rows) - 1, n)]
    keep = patch_map.PROGRAM_CLASS.get(prog)
    patch_map.PROGRAM_CLASS[prog] = di_class(prog)
    tmp = os.path.join(MODEL, "_ab.wav")
    os.makedirs(MODEL, exist_ok=True)
    parts, sr = [], 44100
    try:
        for wav, a, b, f0, fret, t in pick:
            x, sr = mono(wav)
            x = np.asarray(x, np.float64)
            seg = x[max(0, int((a - 0.01) * sr)):int((b + 0.25) * sr)]
            key = int(round(69 + 12 * np.log2(f0 / 440.0)))
            render_note(prog, key, tmp, secs=b - a)
            y, sr2 = mono(tmp)
            y = np.asarray(y, np.float64)
            if sr2 != sr:
                y = resample_poly(y, sr, sr2)
            E = np.sqrt(np.convolve(y * y, np.ones(441) / 441, "same"))
            j = int(np.flatnonzero(E > E.max() * 0.1)[0])
            y = y[max(0, j - 441):max(0, j - 441) + len(seg)]
            k = int(0.3 * sr)
            y *= np.sqrt(np.mean(seg[:k] ** 2) / max(np.mean(y[:k] ** 2), 1e-20))
            g = np.zeros(int(0.3 * sr))
            parts += [seg, g, y, g, g]
    finally:
        if keep is not None:
            patch_map.PROGRAM_CLASS[prog] = keep
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


def ab(prog, out, n=6, secs=1.6):
    """--ab=PROG:OUT.wav: N of the program's reference notes across its range,
    each recorded then ours (DI, at the same pitch), matched in level over
    their first half-second. Through the amplifier is how the voice plays;
    this is how the fit is judged."""
    import wave
    from scipy.signal import resample_poly
    from voicefit import mono, note_of
    import patch_map
    paths = sorted(glob.glob(os.path.join(STAGED, PROGRAM_SETS[prog][0], "*.wav")),
                   key=lambda p: note_of(p))
    pick = [paths[int(i)] for i in np.linspace(0, len(paths) - 1, n)]
    keep = patch_map.PROGRAM_CLASS.get(prog)
    patch_map.PROGRAM_CLASS[prog] = di_class(prog)
    parts, sr = [], 44100
    tmp = os.path.join(MODEL, "_ab.wav")
    os.makedirs(MODEL, exist_ok=True)
    try:
        for p in pick:
            x, sr = mono(p)
            x = np.asarray(x, np.float64)
            E = np.sqrt(np.convolve(x * x, np.ones(441) / 441, "same"))
            i = int(np.flatnonzero(E > E.max() * 0.1)[0])
            x = x[max(0, i - 441):i + int(secs * sr)]
            render_note(prog, note_of(p), tmp, secs=secs)
            y, sr2 = mono(tmp)
            y = np.asarray(y, np.float64)
            if sr2 != sr:
                y = resample_poly(y, sr, sr2)
            E = np.sqrt(np.convolve(y * y, np.ones(441) / 441, "same"))
            j = int(np.flatnonzero(E > E.max() * 0.1)[0])
            y = y[max(0, j - 441):j + int(secs * sr)]
            k = min(len(x), len(y))
            x, y = x[:k], y[:k]
            y *= np.sqrt(np.mean(x[:sr // 2] ** 2) / max(np.mean(y[:sr // 2] ** 2), 1e-20))
            f = np.ones(k); f[-int(0.1 * sr):] = np.linspace(1, 0, int(0.1 * sr))
            g = np.zeros(int(0.3 * sr))
            parts += [x * f, g, y * f, g, g]
    finally:
        if keep is not None:
            patch_map.PROGRAM_CLASS[prog] = keep
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


def ab_damp(prog, out, n=6):
    """--abdamp=PROG:OUT.wav: N reference notes heard through their damp,
    each then ours released at the same moment (DI), level-matched on the
    first half-second."""
    import wave
    from scipy.signal import resample_poly
    from voicefit import mono, note_of
    import patch_map
    paths = sorted(glob.glob(os.path.join(STAGED, PROGRAM_SETS[prog][0], "*.wav")), key=lambda p: note_of(p))
    keep = patch_map.PROGRAM_CLASS.get(prog)
    patch_map.PROGRAM_CLASS[prog] = di_class(prog)
    tmp = os.path.join(MODEL, "_ab.wav")
    os.makedirs(MODEL, exist_ok=True)
    parts, sr, used = [], 44100, 0
    try:
        for p in [paths[int(i)] for i in np.linspace(0, len(paths) - 1, 3 * n)]:
            if used == n:
                break
            x, sr = mono(p)
            x = np.asarray(x, np.float64)
            w = int(0.005 * sr)
            E = 20 * np.log10(np.sqrt(np.convolve(x * x, np.ones(w) / w, "same")) + 1e-12)
            on = int(np.flatnonzero(E > E.max() - 20)[0])
            h, st, td = int(0.1 * sr), int(0.02 * sr), None
            for i in range(int(np.argmax(E)) + int(0.3 * sr), len(E) - h, st):
                if E[i + h] < E[i] - 12:
                    td = i
                    break
            if td is None:
                continue
            hold = (td - on) / sr
            seg = x[max(0, on - 441):td + int(0.8 * sr)]
            render_note(prog, note_of(p), tmp, secs=hold)
            y, sr2 = mono(tmp)
            y = np.asarray(y, np.float64)
            if sr2 != sr:
                y = resample_poly(y, sr, sr2)
            F = np.sqrt(np.convolve(y * y, np.ones(441) / 441, "same"))
            j = int(np.flatnonzero(F > F.max() * 0.1)[0])
            y = y[max(0, j - 441):max(0, j - 441) + len(seg)]
            y *= np.sqrt(np.mean(seg[:sr // 2] ** 2) / max(np.mean(y[:sr // 2] ** 2), 1e-20))
            g = np.zeros(int(0.3 * sr))
            parts += [seg, g, y, g, g]
            used += 1
    finally:
        if keep is not None:
            patch_map.PROGRAM_CLASS[prog] = keep
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


def main(argv):
    if "--stage" in argv:
        stage()
        return 0
    if "--list" in argv:
        for s in sets():
            print("  %-34s %3d notes" % (s, len(glob.glob(os.path.join(STAGED, s, "*.wav")))))
        return 0
    for a in argv:
        if a == "--leak":
            fit_leak()
            return 0
        if a.startswith("--leak="):
            # --leak=LEVEL,RATE[,noise]: one point, scored the same way; a LEVEL
            # of 'none' is the noise pluck alone
            v = a.split("=")[1].split(",")
            fit_leak(levels=(None if v[0] == "none" else float(v[0]),), rates=(float(v[1]),),
                     noise=len(v) > 2)
            return 0
        if a == "--pluck=harm":
            harm_pluck(dbs=320.0)
            return 0
        if a.startswith("--abtech="):
            k, out = a.split("=", 1)[1].split(":", 1)
            ab_technique(k, out)
            return 0
        if a.startswith("--fit-technique="):
            fit_technique(a.split("=")[1])
            return 0
        if a.startswith("--technique="):
            k = a.split("=")[1]
            technique_report(k, 28 if k == "mute" else 31)
            return 0
        if a == "--mute":
            fit_mute()
            return 0
        if a == "--damp":
            fit_damp()
            return 0
        if a.startswith("--abdamp="):
            g, out = a.split("=", 1)[1].split(":", 1)
            ab_damp(int(g), out)
            return 0
        if a.startswith("--ab="):
            g, out = a.split("=", 1)[1].split(":", 1)
            ab(int(g), out)
            return 0
        if a.startswith("--envelope="):
            fit_envelope(int(a.split("=")[1]))
            return 0
        if a.startswith("--ladder="):
            g = int(a.split("=")[1])
            if g in (33, 36, 37):
                # THE PICKUP IS THE BASS'S, NOT THE HAND'S: its resonance is
                # electrical, the same whichever way the string is played. Fitted
                # free, the finger's came out at 2.6 kHz against the pick's 4.9
                # -- the fit making the pickup dull because a soft wide finger
                # had nothing else to be. Held at the pick's (the hard narrow
                # pluck shows the pickup's top best); the hand is the rest.
                fit_ladder(g, ("strike_point", "strike_depth", "tonal_dampening"),
                           pickup_resonance_hz=BASS_PICKUP[0], pickup_q=BASS_PICKUP[1])
            else:
                fit_ladder(g)
            return 0
        if a.startswith("--string="):
            fit_string(a.split("=")[1])
            return 0
    prog = next((int(a.split("=")[1]) for a in argv if a.startswith("--model=")), None)
    for s in [a for a in argv[1:] if not a.startswith("--")]:
        report(rows_of(s), s)
        refs = sorted(glob.glob(os.path.join(STAGED, s, "*.wav")))
        decay_report(refs[::3], "recorded")
        if prog is not None:
            report(model_rows(s, prog, step=3), "ours, GM %d DI, at %s's notes" % (prog, s))
            decay_report(sorted(glob.glob(os.path.join(MODEL, "%s_%d" % (s, prog), "*.wav"))), "ours")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
