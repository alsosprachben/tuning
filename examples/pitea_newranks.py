#!/usr/bin/env python3
"""The church organ's recorded ranks on bits 14-24, each fitted to its Pitea
stop and written into its class in tonelib.py.

    python3 -I examples/pitea_newranks.py [--stop=NAME ...] [--dry] [--hold-level]

--hold-level keeps the stop's level where the console has it (ours measured
before the fit, restored after) instead of Pitea's balance: for a stop measured
on BORROWED pipes, whose recorded level is another rank's.

Per stop, in order (the tools the console's other Pitea stops were built
with):

  1  SERIES  pitea_fit.fit_tables: h1-h32 at three anchor pitches, measured
             on the stop's pipes, three passes of recorded - ours
  2  SPEECH  pitea_stops.fit_speech: speech_cycles, the upper harmonics'
             lead and the valve's floor, against the attack's courses
  3  LEVEL   PITEA'S OWN BALANCE, there being no level of ours to hold: the
             stop's steady power against the Principal 8's on the same keys,
             each scaled as GrandOrgue plays them (the stop's AmplitudeLevel
             and its rank's Gain in the set's .organ files) -- and ours put the
             same distance from our principal 8
  4  WRITE   the class's stub in tonelib.py replaced by the fitted body
             (--dry prints it instead)
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)
import pitea_fit as P  # noqa: E402
import pitea_stops as PS  # noqa: E402
import tonelib as T  # noqa: E402

NEW = ("koppelflute 4", "waldflute 2", "nazard 2-2/3", "tierce 1-3/5", "subbass 16",
       "contrabassoon 32", "gamba 8", "celeste 8", "oboe 8", "vox humana 8", "trompette 8")
LEVEL_KEYS = (48, 55, 60, 67, 72)          # inside every new rank's compass but the pedal's top


def organ_scale(folder):
    """GrandOrgue's playback scale for a folder's pipes, dB: its stop's
    AmplitudeLevel (100 = unity) and the rank's Gain, from the first .organ
    file that names them."""
    for f in sorted(glob.glob(os.path.join(P.PITEA, "*.organ"))):
        txt = open(f, "rb").read().decode("latin-1").replace("\r", "")
        i = txt.find("Pipe001=%s\\" % folder)
        if i < 0:
            continue
        sec = txt[txt.rfind("\n[", 0, i):i]
        amp = re.search(r"\nAmplitudeLevel=([0-9.]+)", sec)
        gain = re.search(r"\nGain=(-?[0-9.]+)", sec)
        db = 20 * np.log10(float(amp.group(1)) / 100.0) if amp else 0.0
        return db + (float(gain.group(1)) if gain else 0.0), os.path.basename(f)
    return 0.0, None


def rec_level(stop):
    """The stop's recorded steady power (1-3 s, dB) over LEVEL_KEYS, as
    GrandOrgue would play it."""
    folder = P.FOLDER[stop]
    p = []
    for key in LEVEL_KEYS:
        path = PS.pipe_file(stop, key) if stop in PS.BORROWED else (
            (glob.glob(os.path.join(P.PITEA, folder, "%03d-*.wav" % key)) or [None])[0])
        if not path:
            continue
        x, sr = P.read(path)
        s = x[int(1.0 * sr):int(3.0 * sr)]
        p.append(np.mean(s ** 2))
    db, _ = organ_scale(folder)
    return 10 * np.log10(np.mean(p)) + db


def ours_level(stop):
    p = []
    for key in LEVEL_KEYS:
        y, sr = P.render(stop, key, 3.5)
        s = y[int(1.0 * sr):int(3.0 * sr)]
        p.append(np.mean(s ** 2))
    return 10 * np.log10(np.mean(p))


def body(cls, stop, rec_d, ours_ref):
    lines = ["    mode_gains_points = ("]
    for f, t in cls.mode_gains_points:
        vals = ", ".join("%.5f" % v for v in t)
        lines.append("        (%.1f, (%s))," % (f, vals))
    lines += ["    )",
              "    mode_gains = mode_gains_points[-1][1]      # (series_volume's switch; the treble's)",
              "    mode_gains_low = None",
              "    max_harmonic = 32",
              "    bore_corner_hz = 0.0",
              ("    # LEVEL: HELD where the console had it, %+.1f dB re our principal 8 --" % rec_d
               if "--hold-level" in sys.argv else
               "    # LEVEL: Pitea's own balance -- %+.1f dB re its Principal 8 on the same" % rec_d),
              ("    # borrowed pipes carry another rank's level (pitea_newranks.py --hold-level)"
               if "--hold-level" in sys.argv else
               "    # keys, as GrandOrgue plays them (pitea_newranks.py) -- held against ours"),
              "    initial_gain = %.6g" % cls.initial_gain,
              "    # ITS SPEECH, fitted on its Pitea stop's attack (pitea_stops.py --fit=speech)",
              "    speech_cycles = %r" % cls.speech_cycles,
              "    speech_harmonic_exp = %r" % cls.speech_harmonic_exp,
              "    attack_time = %r" % cls.attack_time,
              "    rank_speech = True"]
    return "\n".join(lines) + "\n"


def write(cls, text):
    p = os.path.join(HERE, "tonelib.py")
    s = open(p).read()
    m = re.search(r"\nclass %s\(([A-Za-z]+)\):\n    \"\"\"(.*?)\"\"\"\n" % cls.__name__, s, re.S)
    assert m, cls.__name__
    end = m.end()
    # replace whatever fitted body followed the docstring before (a rerun)
    nxt = re.compile(r"\n(class |CELESTE_CENTS|FlueOrganProperties\.|# \.\.\.and the two stops)").search(s, end)
    s = s[:end] + text + "\n" + s[nxt.start():]
    open(p, "w").write(s)


def main(argv):
    import warnings
    warnings.simplefilter("ignore")
    stops = [a.split("=", 1)[1] for a in argv if a.startswith("--stop=")] or list(NEW)
    ref_rec = rec_level("principal 8")
    ref_ours = ours_level("principal 8")
    print("principal 8: Pitea %.1f dB, ours %.1f dB" % (ref_rec, ref_ours), flush=True)
    for stop in stops:
        cls = PS._rank_class(stop)
        print("\n== %s (%s, %s)" % (stop, cls.__name__, P.FOLDER[stop]), flush=True)
        hold = ours_level(stop) - ref_ours if "--hold-level" in argv else None
        P.fit_tables(rank=stop)
        PS.fit_speech(stop)
        rec_d = hold if hold is not None else rec_level(stop) - ref_rec
        for _ in range(2):
            d = (ref_ours + rec_d) - ours_level(stop)
            cls.initial_gain *= 10 ** (d / 20.0)
        print("  level: Pitea %+.1f dB re the principal 8; ours now %+.1f" % (
            rec_d, ours_level(stop) - ref_ours), flush=True)
        text = body(cls, stop, rec_d, ref_ours)
        if "--dry" in argv:
            print(text)
        else:
            write(cls, text)
            print("  written to tonelib.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
