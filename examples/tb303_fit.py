#!/usr/bin/env python3
"""Fit a Moog panel to a TB-303's notes: the SC-88 map's 303 tones.

    python3 -I examples/tb303_fit.py [REFDIR]          # REFDIR ~/Documents/refs/tb303
    python3 -I examples/tb303_fit.py --slide [REFDIR]  # the TD-3's slide, timed

THE TAKES (Freesound, CC0; sources.md): DJMini's own TB-303, one note (C3,
131 Hz, its saw) held 1.75 s -- the filter's pluck and where it settles; and
laffik's Behringer TD-3 (the 303's circuit, cloned), a low note (128 Hz) held
while the cutoff is swept down by hand over 1.3 s -- the same filter at
every cutoff it passes, which pins its slope and resonance.

THE 303: one VCO (a saw; the square made from it), no key tracking, the
diode ladder -- four poles, but not the Moog's: its peak is broader and its
slope between the 2-pole's and the 4-pole's, so both modes are tried -- one
filter envelope, decaying, that never sustains, and a VCA that holds while
the gate does. On the engine: OSC 1 alone, OSC 2 and the sub off, KB
TRACKING 0.

THE FIT (juno_fit's stages): 1 the wave, the resonance and the mode, with a
cutoff found for every frame of both takes; 2 the 303's contour on its own
note's cutoffs (attack, EG AMOUNT, decay; sustain free, to see that it
falls to nothing); 3 its amplifier. --slide: the TD-3 take's slides, their
pitch every 2 ms, each slide's time constant (the 303's is an RC, ~60 ms).
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

REF = os.path.expanduser("~/Documents/refs/tb303")
TAKES = (("89075_*.wav", 131.25, J.TIMES),
         ("690404_*.wav", 127.86, tuple(np.round(np.arange(0.02, 1.5, 0.06), 3))))


def panel_of(v, mode):
    w, res = np.clip(v, (0.45, 0.0), (0.62, 0.75))
    return dict(moog.PANEL, osc1_wave=float(w), osc1_level=1.0, osc2_level=0.0, sub_level=0.0,
                noise_level=0.0, osc1_octave=8, osc2_octave=8, osc2_freq=0.5, tune=0.5, sync=False,
                resonance=float(res), mode=mode, res_bass=False, kb_track=0.0, mod_amount=0.5,
                lfo1_depth=0.5, eg_amount=0.5)


def cost(v, mode, meas):
    r = J.best_cuts(panel_of(v, mode), meas)
    return float(np.sqrt(np.mean([q[3] ** 2 for q in r])))


def slide(ref):
    """Each slide's pitch every 2 ms (the fundamental, a running peak) and the
    time it takes, as a time constant (63% of the way)."""
    x, r = J.read(glob.glob(os.path.join(ref, "583823_*.pcm24.wav"))[0])   # sox of the float original
    W, hop = int(0.03 * r), int(0.002 * r)
    F = np.fft.rfftfreq(8 * W, 1 / r)
    f = []
    for i in range(0, len(x) - W, hop):
        S = np.abs(np.fft.rfft(x[i:i + W] * np.hanning(W), 8 * W))
        m = (F > 25) & (F < 1200)
        lv = 20 * np.log10(np.sqrt(np.mean(x[i:i + W] ** 2)) + 1e-12)
        f.append(F[m][np.argmax(S[m])] if lv > -50 else np.nan)
    f = np.array(f)
    c = 12 * np.log2(f / np.nanmedian(f))
    d = np.diff(c)
    print("pitch every 2 ms, semitones re the median (NaN = silence):")
    for i in range(0, len(c), 25):
        print("  %5.2f s %s" % (i * hop / r, " ".join("%5.1f" % v for v in c[i:i + 25])))
    return 0


def main(argv):
    rest = [a for a in argv[1:] if not a.startswith('--')]
    ref = rest[0] if rest else REF
    if '--slide' in argv:
        return slide(ref)
    meas = []
    for pat, f0, times in TAKES:
        x, r = J.read(glob.glob(os.path.join(ref, pat))[0])
        meas.append((f0, J.frames(x, r, f0, 8, times)))
        print("%s: %d frames" % (pat, len(meas[-1][1])))
    best = None
    for mode in (moog.LP4, moog.LP2):
        for w in (0.48, 0.52):
            for res in (0.3, 0.55):
                r = minimize(cost, np.array([w, res]), args=(mode, meas), method="Nelder-Mead",
                             options=dict(xatol=2e-3, fatol=2e-3, maxiter=200))
                if best is None or r.fun < best[0]:
                    best = (r.fun, mode, r.x)
        print("  mode %s: %.2f dB so far" % (moog.MODES[mode], best[0]), flush=True)
    err, mode, v = best
    panel = panel_of(v, mode)
    rows = J.best_cuts(panel, meas)
    print("1  rms %.2f dB over %d frames: %s, wave %.3f, resonance %.3f"
          % (err, len(rows), moog.MODES[mode], panel['osc1_wave'], panel['resonance']))
    for f0 in sorted(set(q[0] for q in rows)):
        print("   %6.1f Hz cutoffs: " % f0 + " ".join("%.0f@%.2f(%.1f)" % (moog.knob_cutoff(q[2]), q[1], q[3])
                                                    for q in rows if q[0] == f0))
    own = [q for q in rows if q[0] == TAKES[0][1]]
    e2, (cut, eg, fa, fd, fs, _tr) = J.stage2(own, track=0.0)
    print("2  contour: rms %.2f octaves; cutoff %.3f (%.0f Hz), eg_amount %.3f (%.1f oct), f_attack %.3f, "
          "f_decay %.3f (%.2f s), f_sustain %.3f" % (e2, cut, moog.knob_cutoff(cut), eg, moog.eg_octaves(eg), fa,
                                                     fd, moog.knob_time(fd), fs))
    e3, (aa, ad, as_) = J.stage3(own)
    print("3  amplifier: rms %.2f dB; a_attack %.3f, a_decay %.3f, a_sustain %.3f" % (e3, aa, ad, as_))
    out = dict(mode=mode, osc1_wave=round(float(panel['osc1_wave']), 3), resonance=round(float(panel['resonance']), 3),
               cutoff=round(float(cut), 3), eg_amount=round(float(eg), 3), f_attack=round(float(fa), 3),
               f_decay=round(float(fd), 3), f_sustain=round(float(fs), 3), a_attack=round(float(aa), 3),
               a_decay=round(float(ad), 3), a_sustain=round(float(as_), 3))
    print("PANEL %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
