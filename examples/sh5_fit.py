#!/usr/bin/env python3
"""Fit a Moog panel to a Roland SH-5's sample-and-hold steps: the SC-88 map's
SH-5 tones.

    python3 -I examples/sh5_fit.py [REFDIR]        # REFDIR ~/Documents/refs/sh5

THE TAKES (xanthorp, Freesound pack 3305, CC0; sources.md): five patterns,
"Sample and Hold + VCF and manual filter sweeps" -- no held note, but each
sample-and-hold STEP holds a pitch and a cutoff for a tenth of a second or
more, so each step is a note at its own cutoff: the oscillators, the
filter's slope and its resonance are in them; its contour is not.

THE SH-5: two VCOs (saw, square, pulse...), the second at its own footage, a
24 dB low-pass. Each step's frame (30-90 ms into the step, its own f0 found
from its lowest strong partial) is a note to juno_fit's stage 1: the waves,
OSC 2's footage (off, 16', 8', 4') and level, the resonance and the mode,
every frame at its own best cutoff. Frames that fit worse than 8 dB at the
best panel (a transition caught, a sweep moving) are dropped and it is fitted
again. Prints the panel and its error per take.
"""
import glob
import os
import sys

import numpy as np
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import moog                  # noqa: E402
import juno_fit as J         # noqa: E402

REF = os.path.expanduser("~/Documents/refs/sh5")
FOOT2 = (None, 16, 8, 4)


def steps(x, r):
    """[(f0, start s)]: each step -- a jump in level or spectrum -- and its pitch."""
    hop = int(0.01 * r)
    W = int(0.04 * r)
    F = np.fft.rfftfreq(W * 4, 1 / r)
    prev, out, last = None, [], -1.0
    for i in range(0, len(x) - W, hop):
        S = np.abs(np.fft.rfft(x[i:i + W] * np.hanning(W), 4 * W))
        sp = np.log(S[(F > 30) & (F < 4000)] + 1e-9)
        t = i / r
        if prev is not None and np.mean(np.abs(sp - prev)) > 0.6 and t - last > 0.09:
            out.append(t)
            last = t
        prev = sp
    res = []
    for t in out:
        seg = x[int((t + 0.03) * r):int((t + 0.09) * r)]
        if len(seg) < int(0.05 * r) or np.sqrt(np.mean(seg ** 2)) < 1e-3:
            continue
        S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 15))
        Fq = np.fft.rfftfreq(1 << 15, 1 / r)
        m = (Fq > 30) & (Fq < 600)
        L = 20 * np.log10(S / S[m].max() + 1e-12)
        pk = [k for k in np.flatnonzero(m) if L[k] > -12 and L[k] == L[max(0, k - 20):k + 21].max()]
        if pk:
            res.append((float(Fq[pk[0]]), t))
    return res


def meas_of(ref):
    meas, per = [], []
    for f in sorted(glob.glob(os.path.join(ref, "513*.wav"))):
        x, r = J.read(f)
        n = 0
        for f0, t in steps(x, r):
            fr = J.frames(x[int(t * r):], r, f0, 8, (0.03,))      # the grid on f0/2: a 16' OSC 2 on it too
            if fr:
                meas.append((f0, fr))
                per.append(os.path.basename(f)[:5])
                n += 1
        print("%s: %d steps" % (os.path.basename(f)[:5], n))
    return meas, per


def panel_of(v, foot2, mode):
    w1, w2, l2, res = np.clip(v, (0.3, 0.3, 0.0, 0.0), (1.0, 1.0, 1.0, 0.75))
    p = dict(moog.PANEL, osc1_wave=float(w1), osc1_level=1.0, osc2_wave=float(w2),
             osc2_level=float(l2) if foot2 else 0.0, osc1_octave=8, osc2_octave=foot2 or 8,
             osc2_freq=0.5, sub_level=0.0, noise_level=0.0, tune=0.5, sync=False, resonance=float(res),
             mode=mode, res_bass=False, kb_track=0.0, mod_amount=0.5, lfo1_depth=0.5, eg_amount=0.5)
    return p


def errs(v, foot2, mode, meas):
    return np.array([q[3] for q in J.best_cuts(panel_of(v, foot2, mode), meas)])


def fit(meas):
    best = None
    for mode in (moog.LP4, moog.LP2):
        for foot2 in FOOT2:
            for w in (0.5, 0.7):
                v0 = np.array([w, 0.5, 0.6, 0.4])
                r = minimize(lambda v: float(np.sqrt(np.mean(errs(v, foot2, mode, meas) ** 2))), v0,
                             method="Nelder-Mead", options=dict(xatol=2e-3, fatol=2e-3, maxiter=200))
                if best is None or r.fun < best[0]:
                    best = (r.fun, foot2, mode, r.x)
            print("  %s, OSC 2 %s: %.2f dB so far" % (moog.MODES[mode], best[1], best[0]), flush=True)
    return best


def main(argv):
    rest = [a for a in argv[1:] if not a.startswith('--')]
    ref = rest[0] if rest else REF
    meas, per = meas_of(ref)
    err, foot2, mode, v = fit(meas)
    e = errs(v, foot2, mode, meas)
    keep = e < 8.0
    print("first pass %.2f dB; %d of %d steps under 8 dB, refitted on those" % (err, keep.sum(), len(e)))
    meas = [m for m, k in zip(meas, keep) if k]
    per = [p for p, k in zip(per, keep) if k]
    err, foot2, mode, v = fit(meas)
    p = panel_of(v, foot2, mode)
    e = errs(v, foot2, mode, meas)
    print("fit: rms %.2f dB over %d steps; %s; OSC 1 wave %.3f; OSC 2 %s, wave %.3f, level %.3f; resonance %.3f"
          % (err, len(meas), moog.MODES[mode], p['osc1_wave'], ("%d'" % foot2) if foot2 else "off",
             p['osc2_wave'], p['osc2_level'], p['resonance']))
    for t in sorted(set(per)):
        k = np.array([q == t for q in per])
        print("  %s: %d steps, rms %.2f dB" % (t, k.sum(), np.sqrt(np.mean(e[k] ** 2))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
