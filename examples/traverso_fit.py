#!/usr/bin/env python3
"""GS 73.3 "Flt Travelso": the traverso, the baroque wooden flute, as a
difference from GM 73 (the modern flute, fitted to Iowa's Flute.nonvib.mf).

    python3 examples/traverso_fit.py           measure both, fit the difference

THE REFERENCE IS A PERFORMANCE, not a run of notes: Alex Murray playing
Bach's Sarabande from the solo Partita, BWV 1013, on a late-1700s Goulding
flute at A=440 (Wikimedia Commons, CC BY-SA 2.0; sources.md) -- the only
traverso recording found with nothing else playing. So both sides are read
the same way, frame by frame, and compared register by register:

  frames   0.3 s, every 0.1 s, kept where the pitch holds within +-15 cents
           over the frame (three 0.1 s pitches) and the level is within 25
           dB of the take's loudest
  ladder   h1-h8 each its peak, dB re h1
  breath   the spectrum midway between harmonics 1-6 (median), dB re h1
  register the frames grouped by octave from D4 (the traverso's lowest);
           each group's median, the traverso's less Iowa's

and the difference fitted on ours as a difference (ours at the traverso's
frames' pitches, re GM 73 at the same), so a miss shared by both sides
cancels -- the harmonium registers' rule.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

from drum_fit import read  # noqa: E402
import voicefit as V  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs")
TRAVERSO = (os.path.join(REFS, "commons", "traverso", "sarabande.wav"),)
IOWA = tuple(os.path.join(REFS, f) for f in ("flute_B3B4.wav", "flute.wav", "flute_C6B6.wav"))
NH = 8
OCTAVES = ((62, 74), (74, 86), (86, 98))        # D4-C#5, D5-C#6, D6-C#7


def frames(path):
    x, sr = read(path)
    x = x.mean(1) if x.ndim > 1 else x
    w, hop = int(0.3 * sr), int(0.1 * sr)
    rms = np.array([np.sqrt(np.mean(x[i:i + w] ** 2)) for i in range(0, len(x) - w, hop)])
    top = rms.max()
    out = []
    for j, i in enumerate(range(0, len(x) - w, hop)):
        if rms[j] < top * 10 ** (-25 / 20.0):
            continue
        seg = x[i:i + w]
        fs = [V.detect_f0(seg[k * hop:(k + 1) * hop], sr, 250.0, 2200.0) for k in range(3)]
        if any(f is None for f in fs):
            continue
        c = 1200 * np.log2(np.array(fs) / np.median(fs))
        if np.abs(c).max() > 15:
            continue
        f0 = float(np.median(fs))
        S = np.abs(np.fft.rfft(seg * np.hanning(w), 4 * w)); f = np.fft.rfftfreq(4 * w, 1 / sr)
        # the fundamental's own peak near the autocorrelation's pitch
        lad, gaps = [], []
        for m in range(1, NH + 1):
            k = (f > f0 * (m - 0.25)) & (f < f0 * (m + 0.25))
            lad.append(20 * np.log10(S[k].max() + 1e-12))
        for m in range(1, 7):
            k = (f > f0 * (m + 0.3)) & (f < f0 * (m + 0.7))
            gaps.append(20 * np.log10(np.median(S[k]) + 1e-12))
        lad = np.array(lad)
        out.append(dict(midi=69 + 12 * np.log2(f0 / 440.0), f0=f0, ladder=lad - lad[0],
                        breath=float(np.median(gaps) - lad[0])))
    return out


def by_octave(fr):
    g = {}
    for lo, hi in OCTAVES:
        s = [q for q in fr if lo <= q["midi"] < hi]
        if len(s) >= 8:
            g[(lo, hi)] = dict(n=len(s), ladder=np.median([q["ladder"] for q in s], axis=0),
                               breath=float(np.median([q["breath"] for q in s])),
                               f0=[q["f0"] for q in s])
    return g


def ours(cls, f0, vel=90):
    pr = cls(f0, 0.0, (vel / 127.0) ** 2, 1.0)
    a = np.array([abs(pr.harmonic_volume(m)) for m in range(1, NH + 1)])
    return 20 * np.log10(np.maximum(a, 1e-12) / a[0])


def main(argv):
    from scipy.optimize import minimize
    import patch_map as P
    T = by_octave([q for p in TRAVERSO for q in frames(p)])
    I = by_octave([q for p in IOWA for q in frames(p)])
    regs = [r for r in T if r in I]
    names = {62: "D4", 74: "D5", 86: "D6"}
    want = {}
    for r in regs:
        want[r] = T[r]["ladder"] - I[r]["ladder"]
        print("  %s-: traverso %3d frames, Iowa %3d; traverso re Iowa h1-h8:%s; breath %+5.1f re %+5.1f dB"
              % (names[r[0]], T[r]["n"], I[r]["n"], "".join(" %+5.1f" % v for v in want[r]),
                 T[r]["breath"], I[r]["breath"]))
    base = P.property_class_for_note(73, 72)
    knobs = ("tonal_dampening", "bore_corner_hz", "even_harmonic_db")
    pts = {r: np.random.default_rng(0).choice(T[r]["f0"], size=min(12, len(T[r]["f0"])), replace=False)
           for r in regs}
    L0 = {r: np.array([ours(base, f) for f in pts[r]]) for r in regs}

    def err(v):
        if v[0] <= 0.1 or v[1] < 100 or v[2] > 0:
            return 99.0
        cls = type("Fit", (base,), dict(zip(knobs, v)))
        e = []
        for r in regs:
            d = np.median(np.array([ours(cls, f) for f in pts[r]]) - L0[r], axis=0)
            e.append(np.abs(d[1:] - want[r][1:]))
        return float(np.mean(e))
    x0 = np.array([getattr(base, k) or 0.0 for k in knobs], float)
    x0[2] = -3.0                                      # a start off the boundary
    r = minimize(err, x0, method="Nelder-Mead", options=dict(xatol=1e-3, fatol=1e-3, maxfev=300))
    print("  fit: %s  (miss %.2f dB from %.2f)"
          % (", ".join("%s %.4g -> %.4g" % (k, a, b) for k, a, b in zip(knobs, x0, r.x)), r.fun, err(x0)))
    cls = type("Fit", (base,), dict(zip(knobs, r.x)))
    for q in regs:
        d = np.median(np.array([ours(cls, f) for f in pts[q]]) - L0[q], axis=0)
        print("  %s- ours re GM 73:%s" % (names[q[0]], "".join(" %+5.1f" % v for v in d)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
