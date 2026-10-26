#!/usr/bin/env python3
"""Fit a Moog panel to an Oberheim OB-8's held chords: the SC-88 map's OB tones.

    python3 -I examples/obx_fit.py [REFDIR]          # REFDIR ~/Documents/refs/oberheim
    python3 -I examples/obx_fit.py --render [REFDIR] # sc88_synth.OBERHEIM, rendered

THE TAKES (Analogist, Freesound, CC0; sources.md) are all chords -- no OB-8
take anywhere holds a single note. The cleanest: his "jungle pad" (449909)
from 70 s on, where the vibrato of its first half is off and four-note
chords are held two seconds and more: Ebmaj7 (D#3 G3 A#3 D4), Dbmaj7 (C#3 F3
G#3 C4) and again an octave up (C#4-C5), F#maj7 (F#3 A#3 C#4 F4). One patch
throughout.

THE MEASURE: each chord's notes found from its own spectrum (the lowest
unexplained strong peak is a note, its harmonics explained); then the energy
in a band about every harmonic of every note -- wide enough (1.2%, 20 cents)
to hold both oscillators however they are detuned -- bands that overlap
merged, in dB re the chord's strongest. Bands more than 40 dB down are the
floor.

THE MODEL: the engine's own held spectrum (minimoog_fit.model's way:
moog.partials times the ladder's |H|), every note of the chord at the same
level (the OB-8 has no velocity), summed into the same bands. One panel for
all the chords: both waves, OSC 2's level, the cutoff, the resonance, the
4-pole and 2-pole low-pass (the OB-8's filter has both) and KB TRACKING off
and on -- the Dbmaj7 at two octaves decides it.
"""
import glob
import os
import sys

import numpy as np
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import moog                  # noqa: E402
from minimoog_fit import read, render, BASE as MG_BASE   # noqa: E402

REF = os.path.expanduser("~/Documents/refs/oberheim")
TAKE = "449909_*.wav"
# held chords, the vibrato off (the note finder's clean windows)
WINDOWS = ((70.2, 72.2), (74.8, 76.8), (83.8, 85.8), (88.2, 90.2), (92.8, 94.8), (99.5, 101.5),
           (108.5, 110.5), (110.8, 112.8), (113.0, 115.0), (115.2, 117.2))
FLOOR_DB = -40.0
FMAX = 4000.0
BAND = 0.012


def notes(x, r, fmax=2500.0, floor=-36.0):
    """The chord's notes, Hz: the lowest unexplained strong peak is a note,
    and its harmonics are explained."""
    N = len(x)
    S = np.abs(np.fft.rfft(x * np.blackman(N), 2 * N)) ** 2
    F = np.fft.rfftfreq(2 * N, 1 / r)
    L = 10 * np.log10(S / S.max() + 1e-15)
    pk = [i for i in range(8, len(L) - 8)
          if 30 < F[i] < fmax and L[i] > floor and L[i] == L[i - 8:i + 9].max()]
    pf, pl = F[pk], L[pk]
    left = np.ones(len(pf), bool)
    out = []
    while left.any():
        j = np.flatnonzero(left)[0]
        f = pf[j]
        k = np.round(pf / f)
        ex = (k >= 1) & (np.abs(pf - k * f) < 0.012 * k * f + 4)
        if ex.sum() >= 2 or pl[j] > -20:
            out.append(f)
        left &= ~ex
        left[j] = False
    return out


def bands(f0s):
    """Merged bands [(lo, hi)] about every harmonic of every note under FMAX."""
    b = sorted((k * f * (1 - BAND), k * f * (1 + BAND)) for f in f0s for k in range(1, int(FMAX // f) + 1))
    out = []
    for lo, hi in b:
        if out and lo <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def measure(x, r, f0s, bs):
    N = len(x)
    S = np.abs(np.fft.rfft(x * np.blackman(N), 2 * N)) ** 2
    F = np.fft.rfftfreq(2 * N, 1 / r)
    h = np.array([10 * np.log10(S[(F >= lo) & (F < hi)].sum() + 1e-30) for lo, hi in bs])
    return h - h.max()


def model(panel, f0s, bs):
    lo = np.array([b[0] for b in bs])
    hi = np.array([b[1] for b in bs])
    pw = np.zeros(len(bs))
    k = moog.knob_k(panel['resonance'])
    for f0 in f0s:
        fc = (moog.knob_cutoff(panel['cutoff']) * moog.cutoff_at(1.0, f0, panel['kb_track'])
              * 2.0 ** (moog.eg_octaves(panel['eg_amount']) * moog.sustain_level(panel['f_sustain'])))
        for _osc, _h, f, a, _ph in moog.partials(panel, f0, FMAX * 1.05):
            j = np.flatnonzero((f >= lo) & (f < hi))
            if len(j):
                g = moog.ladder_gain(f, max(fc, 1.0), k, int(panel['mode']), bool(panel['res_bass']))
                pw[j[0]] += (a * g * moog.output_gain(f)) ** 2
    h = 10 * np.log10(pw + 1e-30)
    return h - h.max()


# the patch's fixed part: both oscillators at the key, a few cents apart; the
# contour held open (EG AMOUNT at its detent: the cutoff is the knob)
BASE = dict(MG_BASE, osc1_octave=8, osc2_octave=8, osc2_freq=0.5 + 8 / 1400.0)
KEYS = ("osc1_wave", "osc2_wave", "osc2_level", "cutoff", "resonance")
LO = np.array([0.2, 0.2, 0.0, 0.3, 0.0])
HI = np.array([1.0, 1.0, 1.0, 1.0, 0.75])


def panel_of(v, mode, track):
    v = np.clip(v, LO, HI)
    return dict(BASE, mode=mode, kb_track=track, **{k: float(x) for k, x in zip(KEYS, v)})


def errors(panel, meas):
    out = []
    for f0s, bs, h in meas:
        m = model(panel, f0s, bs)
        sel = (h > FLOOR_DB) | (m > FLOOR_DB)
        d = (np.maximum(m, FLOOR_DB) - np.maximum(h, FLOOR_DB))[sel]
        out.append(d - d.mean())
    return out


def cost(v, mode, track, meas):
    return float(np.sqrt(np.mean(np.concatenate(errors(panel_of(v, mode, track), meas)) ** 2)))


def fit(meas):
    best = None
    for mode in (moog.LP4, moog.LP2):
        for track in (0.0, 1.0):
            for w in (0.4, 0.5, 0.65):
                for cut in (0.45, 0.55, 0.65):
                    v0 = np.array([w, w, 0.8, cut, 0.1])
                    r = minimize(cost, v0, args=(mode, track, meas), method="Nelder-Mead",
                                 options=dict(xatol=1e-3, fatol=1e-3, maxiter=500))
                    if best is None or r.fun < best[0]:
                        best = (r.fun, mode, track, np.clip(r.x, LO, HI))
            print("  mode %d track %d: best so far %.2f dB" % (mode, track, best[0]), flush=True)
    return best


def chords(x, r):
    meas = []
    for t0, t1 in WINDOWS:
        seg = x[int(t0 * r):int(t1 * r)]
        f0s = notes(seg, r)
        bs = bands(f0s)
        meas.append((f0s, bs, measure(seg, r, f0s, bs)))
    return meas


def main(argv):
    ref = ([a for a in argv[1:] if not a.startswith('--')] or [REF])[0]
    x, r = read(glob.glob(os.path.join(ref, TAKE))[0])
    meas = chords(x, r)
    for (t0, t1), (f0s, bs, _h) in zip(WINDOWS, meas):
        print("%5.1f-%5.1f s: %s  (%d bands)" % (t0, t1, " ".join("%.1f" % f for f in f0s), len(bs)))
    if '--render' in argv:
        return check(meas, x, r)
    err, mode, track, v = fit(meas)
    panel = panel_of(v, mode, track)
    print("fit: rms %.2f dB, mode %s, kb_track %d" % (err, "LP4" if mode == moog.LP4 else "LP2", track))
    print("  " + ", ".join("%s=%.3f" % (k, panel[k]) for k in KEYS),
          " (cutoff %.0f Hz at middle C)" % moog.knob_cutoff(panel['cutoff']))
    for (t0, _t1), e in zip(WINDOWS, errors(panel, meas)):
        print("  %5.1f s: rms %.2f dB" % (t0, np.sqrt(np.mean(e ** 2))))
    return 0


def check(meas, x, r):
    """sc88_synth.OBERHEIM rendered on each chord, measured as the take is."""
    import json  # noqa: F401
    from sc88_synth import OBERHEIM
    panel = dict(BASE, **OBERHEIM)
    allm = []
    for (f0s, bs, h) in meas:
        midi = [int(round(69 + 12 * np.log2(f / 440.0))) for f0 in [f0s] for f in f0]
        y, ry = read(render(panel, [tuple(midi)], held=2.5))
        seg = y[int(1.2 * ry):int(3.2 * ry)]
        fr = [440.0 * 2 ** ((m - 69) / 12.0) for m in midi]
        m = measure(seg, ry, fr, bands(fr))
        sel = (h > FLOOR_DB) | (m > FLOOR_DB)
        d = (np.maximum(m, FLOOR_DB) - np.maximum(h, FLOOR_DB))[sel]
        allm.append(d - d.mean())
        print("  %s: rms %.2f dB rendered" % (" ".join(map(str, midi)), np.sqrt(np.mean((d - d.mean()) ** 2))))
    print("all: %.2f dB" % np.sqrt(np.mean(np.concatenate(allm) ** 2)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
