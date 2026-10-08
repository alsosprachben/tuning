#!/usr/bin/env python3
"""Measure a trumpet mute: VSCO 2 CE's trumpet, open against muted, note by note.

    python3 examples/mute_fit.py [REFS] [--fit] [--table] [--model]

REFS (default ~/Documents/refs/mute/raw) holds sus/, harmonM-sus/ and
straightM-sus/, Versilian's trumpet holding notes open, in a harmon mute and in
a straight mute (CC0; ~/Documents/refs/sources.md), at two dynamics (v1, v3).
Names run an octave low, as everywhere in VSCO 2 CE.

A MUTE IS A FILTER ON THE BELL, and the open trumpet is the same player, horn
and microphone, so for every pitch and dynamic recorded both ways each
partial's level muted minus open, in dB, is the mute's response at that
partial's frequency: the trumpet cancels and the mute is left. Partials 1-40
under 12 kHz, the steady 0.5-2.5 s, each read at its own peak.

Prints, per mute, the response in sixth-octave bands (median over every pair
and partial in the band) and the overall level change. --fit fits it to the
class's terms: the bell's high-pass (bell_cutoff_hz, bell_order) and the mute's
resonance (mute_resonance_hz, _q, _db), over the open trumpet's own -- which
misses a harmon by 7.5 dB, its notch and its climbing top being beyond one
peak; --table prints the response as the class carries it instead.
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

from timpani_fit import peak_near, spectrum  # noqa: E402
from voicefit import mono  # noqa: E402

NOTE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
MUTES = ("harmonM-sus", "straightM-sus")


def key_of(path):
    m = re.search(r'_([A-G])(#?)(\d)_v(\d)', os.path.basename(path))
    n = (int(m.group(3)) + 1) * 12 + NOTE[m.group(1)] + (1 if m.group(2) else 0) + 12
    return n, int(m.group(4))


def partials(path):
    x, sr = mono(path)
    n, _ = key_of(path)
    f0 = 440.0 * 2 ** ((n - 69) / 12.0)
    f, X = spectrum(x, sr, 0.5, 2.5)
    f1, _ = peak_near(f, X, f0, 0.03)
    out = []
    for m in range(1, 41):
        if m * f1 > 12000.0:
            break
        fm, a = peak_near(f, X, m * f1, 0.015)
        out.append((m * f1, 20 * np.log10(max(a, 1e-12))))
    rms = 20 * np.log10(np.sqrt(np.mean(x[int(0.5 * sr):int(2.5 * sr)] ** 2)))
    return f1, out, rms


def response(refs, mute):
    opens = {key_of(p): p for p in glob.glob(os.path.join(refs, "sus", "*.wav"))}
    pts, dl, pairs = [], [], []
    for p in sorted(glob.glob(os.path.join(refs, mute, "*.wav"))):
        k = key_of(p)
        if k not in opens:
            continue
        _, mo, mr = partials(p)
        _, op, orr = partials(opens[k])
        for (fm, am), (_, ao) in zip(mo, op):
            if ao > max(a for _, a in op) - 50.0:         # the open partial is above the floor
                pts.append((fm, am - ao))
        dl.append(mr - orr)
        pairs.append(k)
    return np.array(pts), float(np.median(dl)), pairs


def model_db(f, p):
    """The class's terms: a high-pass and one resonance, plus a level."""
    hc, order, rh, q, rdb, g = p
    hp = -10 * np.log10(1.0 + (hc / f) ** (2 * order))
    r = f / rh
    boost = 10 ** (rdb / 20.0) - 1.0
    res = 20 * np.log10(1.0 + boost / (1.0 + (q * (r - 1.0 / r)) ** 2))
    return g + hp + res


def table(pts, lo=200.0, hi=10000.0, per_oct=3, min_n=4):
    """The response as third-octave medians, each band widened until it holds
    min_n partials -- a band with two is two notes' accidents -- as
    (Hz, dB) pairs for the class to interpolate in log frequency."""
    out = []
    lf = np.log2(pts[:, 0])
    for c in 2 ** np.arange(np.log2(lo), np.log2(hi) + 1e-9, 1.0 / per_oct):
        half = 0.5 / per_oct
        while True:
            b = np.abs(lf - np.log2(c)) <= half
            if b.sum() >= min_n or half > 1.0:
                break
            half *= 1.5
        if b.sum():
            out.append((round(float(c)), round(float(np.median(pts[b, 1])), 1)))
    return out


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    refs = pos[0] if pos else os.path.expanduser("~/Documents/refs/mute/raw")
    edges = 2 ** np.arange(np.log2(150.0), np.log2(12000.0), 1 / 6.0)
    if "--model" in argv:
        # GM 56 open and GM 59 muted at the recorded pitches and dynamics, dry,
        # named as the references are so the same reader takes them
        os.environ.setdefault("TUNING_REFLECT", "0")
        os.environ.setdefault("TUNING_MASTER_DB", "-14")
        import blockrender as B
        import patch_map as PM
        from pizz_model_notes import NAMES, one
        from roomtail import write_wav
        out = os.path.join(os.path.dirname(os.path.normpath(refs)), "model")
        keys = {key_of(p_) for p_ in glob.glob(os.path.join(refs, "harmonM-sus", "*.wav"))}
        for sub, prog in (("sus", 56), ("harmonM-sus", 59)):
            os.makedirs(os.path.join(out, sub), exist_ok=True)
            for n, v in sorted(keys):
                nm = "%s%d" % (NAMES[n % 12], n // 12 - 2)
                write_wav(os.path.join(out, sub, "m_%s_v%d.wav" % (nm, v)),
                          one(PM.BOWED_SPLIT, prog, n, vel=60 if v == 1 else 100, secs=3.0), B.SR)
        refs = out
        MUTES_ = ("harmonM-sus",)
    else:
        MUTES_ = MUTES
    for mute in MUTES_:
        pts, dl, pairs = response(refs, mute)
        print("== %s: %d pairs (%s), %d partials; level %+.1f dB" % (
            mute, len(pairs), " ".join("%d/v%d" % k for k in pairs), len(pts), dl))
        for lo, hi in zip(edges[:-1], edges[1:]):
            b = (pts[:, 0] >= lo) & (pts[:, 0] < hi)
            if b.sum() >= 2:
                v = np.median(pts[b, 1])
                print("   %6.0f Hz  %+6.1f dB  %s  (%d)" % (np.sqrt(lo * hi), v,
                                                        "#" * int(max(0, v + 40) / 2), b.sum()))
        if "--table" in argv:
            print("   table: %s" % (tuple(table(pts)),))
        if "--fit" in argv:
            from scipy.optimize import least_squares
            r = least_squares(lambda p: model_db(pts[:, 0], p) - pts[:, 1],
                              [800.0, 2.0, 1800.0, 2.0, 10.0, -10.0],
                              bounds=([50, 0.5, 300, 0.3, 0, -60], [5000, 8, 9000, 20, 40, 20]),
                              loss='soft_l1', f_scale=4.0)
            hc, order, rh, q, rdb, g = r.x
            print("   fit: high-pass %.0f Hz order %.1f, resonance %.0f Hz Q %.2f %+.1f dB, level %+.1f"
                  " (median miss %.1f dB)" % (hc, order, rh, q, rdb, g,
                                              np.median(np.abs(r.fun))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
