#!/usr/bin/env python3
"""Fit a Moog panel to a Yamaha CS-30L's notes: the SC-88 map's CS tones.

    python3 -I examples/cs_fit.py [REFDIR]          # REFDIR ~/Documents/refs/cs30l

THE TAKES (Modular Samples, Freesound, CC0; sources.md): CS-30L patches
sampled key by key. Every pack sounds two octaves under its file names (its
footage set low): the fit takes the pitch that sounds. The Saw pack is the
oscillator with the filter open -- a saw within a dB of 1/k at every key,
which the engine's saw already is; the filter is in the two bass packs:
"bass" (dark, resonant, held) and "simple bass" (a 0.3 s pluck).

THE CS SERIES' FILTER is Yamaha's 12 dB/octave, not a ladder: the fit tries
the 2-pole and the 4-pole and lets the takes choose. Per patch (juno_fit's
stages): 1 the wave (saw to square), the resonance and the mode, a cutoff
for every frame of every note; 2 the contour on those cutoffs, the key
tracking fitted; 3 the amplifier.
"""
import os
import sys

import numpy as np
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import moog                  # noqa: E402
import juno_fit as J         # noqa: E402

REF = os.path.expanduser("~/Documents/refs/cs30l")
PATCHES = {"bass": (60, 66, 72, 78, 84), "simple-bass": (48, 60, 72, 84)}
UNDER = 24                  # the packs sound two octaves under their names


def panel_of(v, mode):
    w, res = np.clip(v, (0.45, 0.0), (0.9, 0.75))
    return dict(moog.PANEL, osc1_wave=float(w), osc1_level=1.0, osc2_level=0.0, sub_level=0.0,
                noise_level=0.0, osc1_octave=8, osc2_octave=8, osc2_freq=0.5, tune=0.5, sync=False,
                resonance=float(res), mode=mode, res_bass=False, kb_track=0.0, mod_amount=0.5,
                lfo1_depth=0.5, eg_amount=0.5)


def cost(v, mode, meas):
    r = J.best_cuts(panel_of(v, mode), meas)
    return float(np.sqrt(np.mean([q[3] ** 2 for q in r])))


def fit_patch(ref, patch):
    meas = []
    for n in PATCHES[patch]:
        x, r = J.take(ref, patch, n)
        f0 = 440.0 * 2 ** ((n - UNDER - 69) / 12.0)
        meas.append((f0, J.frames(x, r, f0)))
    best = None
    for mode in (moog.LP4, moog.LP2):
        for w in (0.5, 0.65):
            for res in (0.2, 0.5):
                r = minimize(cost, np.array([w, res]), args=(mode, meas), method="Nelder-Mead",
                             options=dict(xatol=2e-3, fatol=2e-3, maxiter=200))
                if best is None or r.fun < best[0]:
                    best = (r.fun, mode, r.x)
        print("  %s %s: %.2f dB so far" % (patch, moog.MODES[mode], best[0]), flush=True)
    err, mode, v = best
    other = min(minimize(cost, v, args=(1 - mode, meas), method="Nelder-Mead",
                         options=dict(xatol=2e-3, fatol=2e-3, maxiter=200)).fun, 99)
    panel = panel_of(v, mode)
    rows = J.best_cuts(panel, meas)
    print("%s 1  rms %.2f dB over %d frames: %s (the other mode %.2f), wave %.3f, resonance %.3f"
          % (patch, err, len(rows), moog.MODES[mode], other, panel['osc1_wave'], panel['resonance']))
    e2, (cut, eg, fa, fd, fs, tr) = J.stage2(rows)
    print("%s 2  contour: rms %.2f octaves; cutoff %.3f (%.0f Hz), eg_amount %.3f (%.1f oct), f_attack %.3f, "
          "f_decay %.3f (%.2f s), f_sustain %.3f, kb_track %.2f"
          % (patch, e2, cut, moog.knob_cutoff(cut), eg, moog.eg_octaves(eg), fa, fd, moog.knob_time(fd), fs, tr))
    e3, (aa, ad, as_) = J.stage3(rows)
    print("%s 3  amplifier: rms %.2f dB; a_attack %.3f, a_decay %.3f (%.2f s), a_sustain %.3f"
          % (patch, e3, aa, ad, moog.knob_time(ad), as_))
    out = dict(mode=mode, osc1_wave=round(float(panel['osc1_wave']), 3), resonance=round(float(panel['resonance']), 3),
               kb_track=round(float(tr), 3), cutoff=round(float(cut), 3), eg_amount=round(float(eg), 3),
               f_attack=round(float(fa), 3), f_decay=round(float(fd), 3), f_sustain=round(float(fs), 3),
               a_attack=round(float(aa), 3), a_decay=round(float(ad), 3), a_sustain=round(float(as_), 3))
    print("%s PANEL %s" % (patch, out))


def main(argv):
    rest = [a for a in argv[1:] if not a.startswith('--')]
    ref = rest[0] if rest else REF
    for patch in PATCHES:
        fit_patch(ref, patch)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
