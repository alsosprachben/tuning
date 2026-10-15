#!/usr/bin/env python3
"""The church organ's OTHER stops (GM 19) against the Pitea organ's.

    python3 examples/pitea_stops.py [--stop=NAME ...] [--keys=36,48,60,72,84]

pitea_fit.py fitted the three principals; every other stop on the console has
a Pitea stop of its kind (sources.md "Pipe organ"), mapped in STOPS below. Per
stop and key, the two measurements the principals were fitted on:

  TONE    the steady ladder (1.0-3.0 s), h1-h12 dB re the fundamental of the
          rank's own pitch (pitea_fit.measure)
  SPEECH  the attack's courses -- the fundamental, h2-h4, h5 and up, the breath
          between the partials -- dB re steady (pitea_speech.courses), and the
          time each course first reaches -3 dB of steady, and its overshoot

Ours: the stop drawn alone on GM 19 (pitea_fit.render).
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
import pitea_fit as P  # noqa: E402
import pitea_speech as S  # noqa: E402
import tonelib as T  # noqa: E402

STOPS = dict(P.MORE_STOPS)
# STOPS PITEA DOES NOT HAVE, MEASURED ON PIPES IT DOES: a pipe is a pipe at its
# own pitch. Each borrows by key range: (lowest key, folder, key shift).
#   principal 16  an octave down: the Principal 8's pipe at key-12, and for its
#                 bottom octave the pedal Oktava 8's (open, principal scale,
#                 down to C1 at 32.7 Hz) -- an organ's own extension
#   quint 5-1/3   the Kvinta 2 2/3's pipe at key-12, which sounds the 5 1/3's
#                 pitch (3 x pitch(key-12) = 1.5 x pitch(key)); from C3, the
#                 Kvinta having nothing under its own C2
# (The pedal Mixtur's "quint" is the plein-jeu's 2 2/3, HarmonicNumber 24 in
# PiteaExtended.organ: no true 5 1/3 rank exists in the set.)
BORROWED = {
    "principal 16": ("HVPrincipal8 an octave down; pedal Oktava 8 under C3",
                     ((36, "PEDOktava8", -12), (48, "HVPrincipal8", -12))),
    "quint 5-1/3":  ("Positiv Kvinta 2 2/3, its pipe an octave down",
                     ((48, "POSKvinta223", -12),)),
}
for _k, (_w, _r) in BORROWED.items():
    STOPS[_k] = (_r[-1][1], _w)


def pipe_file(stop, key):
    """The recorded pipe that sounds STOP's pitch at KEY, or None."""
    if stop in BORROWED:
        use = [r for r in BORROWED[stop][1] if key >= r[0]]
        if not use:
            return None
        _, folder, sh = use[-1]
        p = glob.glob(os.path.join(P.PITEA, folder, "%03d-*.wav" % (key + sh)))
    else:
        p = glob.glob(os.path.join(P.PITEA, STOPS[stop][0], "%03d-*.wav" % key))
    return p[0] if p else None
T_ATT = (0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.2, 0.3)
NAMES = ("fund", "h2-4", "h5+", "breath")


def ratio_of(stop):
    r = dict((r[0], r[1]) for r in T.FlueOrganProperties.stop_ranks)[stop]
    return 1.0 if isinstance(r, (list, tuple)) else r


def speak(c):
    """(ms to first reach -3 dB of steady, overshoot dB over steady, ms of it)
    per course."""
    out = []
    for j in range(3):
        k = np.flatnonzero(c[:, j] > -3.0)
        t3 = k[0] * S.HOP * 1000 if len(k) else np.nan
        pk = int(np.argmax(c[:, j]))
        out.append((t3, c[pk, j], pk * S.HOP * 1000))
    return out


def main(argv):
    stops = [a.split("=", 1)[1] for a in argv if a.startswith("--stop=")] or list(STOPS)
    keys = next((tuple(int(k) for k in a.split("=")[1].split(","))
                 for a in argv if a.startswith("--keys=")), S.KEYS)
    for stop in stops:
        folder, what = STOPS[stop]
        ratio = ratio_of(stop)
        print("== %s against %s" % (stop, what), flush=True)
        for key in keys:
            p = pipe_file(stop, key)
            if not p:
                continue
            f0 = 440.0 * 2 ** ((key - 69) / 12.0) * ratio
            x, sr = P.read(p)
            a = S.onset(x)
            y, s2 = P.render(stop, key, 3.0)
            lr = P.measure(x[a:], sr, f0)[0]
            lo = P.measure(y, s2, f0)[0]
            st, sto = S.steady(x, sr, f0, a), S.steady(y, s2, f0, 0)
            rc = S.courses(x, sr, f0, a, 0.4, ref=st)
            oc = S.courses(y, s2, f0, 0, 0.4, ref=sto)
            print("  key %d, %.0f Hz" % (key, f0))
            print("    tone rec  " + " ".join("%6.1f" % v for v in lr[1:12]))
            print("    tone ours " + " ".join("%6.1f" % v for v in lo[1:12]))
            for j in range(3):
                print("    %-5s rec  %s   ours %s" % (NAMES[j],
                      " ".join("%+5.1f" % rc[int(t / S.HOP), j] for t in T_ATT),
                      " ".join("%+5.1f" % oc[int(t / S.HOP), j] for t in T_ATT)))
            sr_, so_ = speak(rc), speak(oc)
            print("    -3 dB at (ms) fund/h2-4/h5+: rec %s  ours %s;  peak rec %s  ours %s" % (
                "/".join("%.0f" % s[0] for s in sr_), "/".join("%.0f" % s[0] for s in so_),
                " ".join("%+.1f@%.0f" % (s[1], s[2]) for s in sr_),
                " ".join("%+.1f@%.0f" % (s[1], s[2]) for s in so_)))
            print("    breath re fund: rec %+.1f ours %+.1f" % (st[3] - st[0], sto[3] - sto[0]), flush=True)
    return 0




LEVEL_KEYS = (36, 48, 60, 72, 84)


def level(stop):
    """Our stop's steady level, dB: the power of 1.0-3.0 s, averaged as power
    over LEVEL_KEYS -- what a refit of its tone must hold (the console's
    balance is Ben's ear's, not Pitea's)."""
    p = []
    for key in LEVEL_KEYS:
        y, sr = P.render(stop, key, 3.5)
        s = y[int(1.0 * sr):int(3.0 * sr)]
        p.append(np.mean(s ** 2))
    return 10 * np.log10(np.mean(p))


SPEECH_KEYS = (48, 60, 72, 84)
SPEECH_T = 0.3


def _rank_class(stop):
    row = next(r for r in T.FlueOrganProperties.stop_ranks if r[0] == stop)
    return row[3]


def fit_speech(stop, rounds=2):
    """--fit=speech --stop=NAME: the stop's class's speech_cycles,
    speech_harmonic_exp and attack floor, by coordinate search, against its
    Pitea stop's attack courses (fundamental, h2-h4, h5 and up, dB re steady,
    clipped to -30..+10) over the first SPEECH_T s at SPEECH_KEYS. The bass
    octave is left out: its fundamentals are the hall's (pitea_fit.py)."""
    import warnings
    warnings.simplefilter("ignore")
    cls = _rank_class(stop)
    folder = STOPS[stop][0]
    ratio = ratio_of(stop)
    rec = {}
    for key in SPEECH_KEYS:
        p = pipe_file(stop, key)
        if not p:
            continue
        f0 = 440.0 * 2 ** ((key - 69) / 12.0) * ratio
        x, sr = P.read(p)
        a = S.onset(x)
        rec[key] = (f0, np.clip(S.courses(x, sr, f0, a, SPEECH_T, ref=S.steady(x, sr, f0, a))[:, :3], -30, 10))

    def cost():
        e = []
        for key, (f0, rc) in rec.items():
            y, s2 = P.render(stop, key, 2.6)
            oc = np.clip(S.courses(y, s2, f0, 0, SPEECH_T, ref=S.steady(y, s2, f0, 0))[:, :3], -30, 10)
            n = min(len(rc), len(oc))
            e.append(np.mean((rc[:n] - oc[:n]) ** 2))
        return float(np.sqrt(np.mean(e)))

    if cls.attack_time is None:
        cls.attack_time = float(cls.chiff_max_valve_time)
    grids = {
        "speech_cycles": (0.0, 2.0, 4.0, 8.0, 12.0, 18.0, 24.0, 32.0, 48.0),
        "speech_harmonic_exp": (0.0, 0.3, 0.6, 0.9, 1.2),
        "attack_time": (0.002, 0.008, 0.016, 0.03, 0.05, 0.08),
    }
    if "--push" in sys.argv:
        # THE PRESSURE BOOST: the overshoot of a band of harmonics
        # (tonelib.bellows_push_weight's band), its rise and its fall -- the
        # speech held as fitted
        cls.bellows_push_band = getattr(cls, "bellows_push_band", None) or (4.0, 0.8)
        cls.bellows_push_rise_s = getattr(cls, "bellows_push_rise_s", 0.12) or 0.12
        cls.bellows_push_dbs = getattr(cls, "bellows_push_dbs", 25.0) or 25.0
        cls.bellows_push_settle_db = -20.0
        cls.bellows_push_gain = 0.6
        grids = {
            "bellows_push_gain": (0.0, 0.3, 0.6, 1.0, 1.5),
            "bellows_push_band": ((2.5, 0.8), (3.5, 0.8), (5.0, 0.8), (3.5, 1.4)),
            "bellows_push_rise_s": (0.04, 0.08, 0.12, 0.2, 0.3),
            "bellows_push_dbs": (10.0, 18.0, 25.0, 40.0),
        }
    best = cost()
    print("  %s speech, start: %.2f dB  (%s)" % (stop, best, "  ".join(
        "%s=%s" % (k, getattr(cls, k, 0.0)) for k in grids)), flush=True)
    for _ in range(rounds):
        for k, grid in grids.items():
            keep = getattr(cls, k, 0.0)
            for v in grid:
                if v == keep:
                    continue
                setattr(cls, k, v)
                c = cost()
                if c < best - 0.05:
                    best, keep = c, v
            setattr(cls, k, keep)
        print("  %s speech: %.2f dB  (%s)" % (stop, best, "  ".join(
            "%s=%s" % (k, getattr(cls, k, 0.0)) for k in grids)), flush=True)
    return best


if __name__ == "__main__" and "--fit=speech" in sys.argv:
    for _s in [a.split("=", 1)[1] for a in sys.argv if a.startswith("--stop=")]:
        fit_speech(_s)
    sys.exit(0)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
