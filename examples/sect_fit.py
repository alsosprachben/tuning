#!/usr/bin/env python3
"""Fit GM 48's section to VSCO 2 CE's sustained sections: onset, roughness, smear.

    python3 examples/sect_fit.py [REFS] [--files] [--model]

REFS (default ~/Documents/refs/sect/raw) holds violin/, viola/ and cello/,
Versilian's sections holding a note with vibrato (CC0; ~/Documents/refs/
sources.md), at two or three dynamics. As with their tremolos the note names
run an OCTAVE LOW (VSCO's C3 is middle C), so +12.

GM 48 builds a section out of one measured instrument: section_players
stacks, section_spread_cents apart, each with its own vibrato
(section_vibrato_cents at section_vibrato_hz), entering within
section_onset_ms over a bow onset of chiff_min/max_valve_time. None of those
was measured. What they add up to is, off the summed sound:

  rise     the onset: 10% to 90% of the steady level (20 ms RMS), ms
  swing    the steady level's std/mean (10 ms RMS, 0.8 s in to 0.4 s from the
           end): how rough the section is -- players beating against each
           other, and the bow
  slow     the same swing band-passed 0.5-4 Hz and 4-12 Hz: the slow drift
           of the beating against the vibrato band's
  width    each partial's line width, cents (-6 dB, 2 s) -- which turned out
           to be the window's own resolution, about 1 Hz on both sides, and is
           kept only to say so
  wobble   the pitch's own movement: partials 2-4 band-passed (+/-60 cents),
           their instantaneous frequency (20 ms smoothed), its std in cents and
           the peak of its spectrum in 3-9 Hz: the vibrato the section sums to

--model renders GM 48 at the same notes and dynamics (v1 velocity 60, v2 100,
v3 120) and reads it the same way.
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

from trem_fit import note_of  # noqa: E402
from voicefit import mono  # noqa: E402

VEL = {1: 60, 2: 100, 3: 120}


def band_swing(env, sr, lo, hi):
    e = env - env.mean()
    E = np.fft.rfft(e)
    f = np.fft.rfftfreq(len(e), 1.0 / sr)
    E[(f < lo) | (f > hi)] = 0.0
    return float(np.sqrt(2.0) * np.fft.irfft(E, len(e)).std() / env.mean())


def line_width(x, sr, fm):
    """-6 dB width of the line near fm, cents (zero-padded, Hann, 2 s)."""
    N = 1 << 20
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    b = (f > fm * 2 ** (-60 / 1200.0)) & (f < fm * 2 ** (60 / 1200.0))
    if not b.any():
        return None
    Xb, fb = X[b], f[b]
    i = int(np.argmax(Xb))
    half = Xb[i] / 2.0
    lo = i
    while lo > 0 and Xb[lo] > half:
        lo -= 1
    hi = i
    while hi < len(Xb) - 1 and Xb[hi] > half:
        hi += 1
    if lo == 0 or hi == len(Xb) - 1:
        return None
    return 1200.0 * np.log2(fb[hi] / fb[lo])


def wobble(x, sr, fm):
    """(cents std, rate Hz) of the instantaneous frequency in fm's band."""
    N = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(N, 1.0 / sr)
    X[(f < fm * 2 ** (-60 / 1200.0)) | (f > fm * 2 ** (60 / 1200.0))] = 0.0
    full = np.zeros(N, complex)
    full[:len(X)] = X
    full[1:len(X) - (1 if N % 2 == 0 else 0)] *= 2.0
    a = np.fft.ifft(full)
    ph = np.unwrap(np.angle(a))
    inst = np.diff(ph) * sr / (2 * np.pi)
    w = int(0.02 * sr)
    inst = np.convolve(inst, np.ones(w) / w, 'valid')[w:-w]
    c = 1200.0 * np.log2(np.maximum(inst, 1.0) / fm)
    c = c - c.mean()
    S = np.abs(np.fft.rfft(c * np.hanning(len(c)), 1 << 18)) ** 2
    fr = np.fft.rfftfreq(1 << 18, 1.0 / sr)
    b = (fr >= 3.0) & (fr <= 9.0)
    return float(c.std()), float(fr[b][np.argmax(S[b])])


def measure(path, offset=12):
    x, sr = mono(path)
    n = note_of(path, offset)
    if n is None:
        return None
    f0 = 440.0 * 2 ** ((n - 69) / 12.0)
    w = int(0.02 * sr)
    env20 = np.sqrt(np.convolve(x * x, np.ones(w) / w, 'same'))
    on = int(np.flatnonzero(env20 > env20.max() * 0.02)[0])
    steady = float(np.median(env20[on + int(0.8 * sr):len(x) - int(0.4 * sr)]))
    t10 = np.flatnonzero(env20[on:] >= 0.1 * steady)
    t90 = np.flatnonzero(env20[on:] >= 0.9 * steady)
    rise = (t90[0] - t10[0]) / sr * 1000.0 if len(t10) and len(t90) else None
    a, b = on + int(0.8 * sr), len(x) - int(0.4 * sr)
    if b - a < int(1.5 * sr):
        return None
    seg = x[a:b]
    w = int(0.01 * sr)
    env = np.sqrt(np.convolve(seg * seg, np.ones(w) / w, 'same'))[w:-w]
    two = seg[:int(2.0 * sr)]
    widths = [line_width(two, sr, m * f0) for m in range(1, 7)]
    wb = [wobble(seg, sr, m * f0) for m in (2, 3, 4) if m * f0 < 0.4 * sr]
    m = re.search(r'_v(\d)', os.path.basename(path))
    return dict(note=n, f0=f0, vel=int(m.group(1)) if m else 0, rise=rise,
                swing=float(env.std() / env.mean()), slow=band_swing(env, sr, 0.5, 4.0),
                vib=band_swing(env, sr, 4.0, 12.0), widths=widths,
                wob=float(np.median([w_[0] for w_ in wb])), wrate=float(np.median([w_[1] for w_ in wb])))


def show(rows, title):
    print("== %s: %d notes" % (title, len(rows)))
    print("   v  rise ms  swing   0.5-4Hz  4-12Hz   wobble cents @ Hz   line width, cents, partials 1-6")
    for v in sorted({r['vel'] for r in rows}):
        rs = [r for r in rows if r['vel'] == v]
        rise = [r['rise'] for r in rs if r['rise']]
        wd = [np.median([r['widths'][i] for r in rs if r['widths'][i]] or [np.nan]) for i in range(6)]
        print("   %d  %6.0f   %.3f   %.3f    %.3f    %5.1f @ %4.1f    %s   (%d)" % (
            v, np.median(rise) if rise else np.nan, np.median([r['swing'] for r in rs]),
            np.median([r['slow'] for r in rs]), np.median([r['vib'] for r in rs]),
            np.median([r['wob'] for r in rs]), np.median([r['wrate'] for r in rs]),
            " ".join("%5.1f" % x for x in wd), len(rs)))


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    refs = pos[0] if pos else os.path.expanduser("~/Documents/refs/sect/raw")
    every = []
    for inst in ("violin", "viola", "cello"):
        rows = [r for r in (measure(p) for p in sorted(glob.glob(os.path.join(refs, inst, "*.wav")))) if r]
        if "--files" in argv:
            for r in sorted(rows, key=lambda r: (r['vel'], r['note'])):
                print("  %-6s %3d v%d  rise %5s  swing %.3f  slow %.3f  vib %.3f  w1 %s"
                      % (inst, r['note'], r['vel'], "%.0f" % r['rise'] if r['rise'] else "-",
                         r['swing'], r['slow'], r['vib'],
                         "%.1f" % r['widths'][0] if r['widths'][0] else "-"))
        show(rows, inst)
        every += [(inst, r) for r in rows]
    if "--model" in argv:
        os.environ.setdefault("TUNING_REFLECT", "0")
        os.environ.setdefault("TUNING_MASTER_DB", "-14")
        import blockrender as B
        import patch_map as PM
        from pizz_model_notes import NAMES, one
        from roomtail import write_wav
        out = os.path.join(os.path.dirname(os.path.normpath(refs)), "model")
        prog = int(next((a.split("=")[1] for a in argv if a.startswith("--prog=")), 48))
        done = set() if "--no-render" not in argv else {(i, r['note'], r['vel']) for i, r in every}
        for inst, r in every:
            key = (inst, r['note'], r['vel'])
            if key in done:
                continue
            done.add(key)
            d = os.path.join(out, inst)
            os.makedirs(d, exist_ok=True)
            n = r['note']
            write_wav(os.path.join(d, "m_%s%d_v%d.wav" % (NAMES[n % 12], n // 12 - 2, r['vel'])),
                      one(PM.BOWED_SPLIT, prog, n, vel=VEL.get(r['vel'], 100), secs=6.0), B.SR)
        for inst in ("violin", "viola", "cello"):
            rows = [m for m in (measure(p) for p in sorted(glob.glob(os.path.join(out, inst, "*.wav")))) if m]
            show(rows, "model %s (GM %d)" % (inst, prog))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
