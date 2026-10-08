#!/usr/bin/env python3
"""Fit GM 44, bowed tremolo, to VSCO 2 CE's section tremolos: the stroke.

    python3 examples/trem_fit.py [REFS] [--files] [--model]

REFS (default ~/Documents/refs/trem/raw) holds violin/, viola/ and cello/,
Versilian's section tremolos (CC0; ~/Documents/refs/sources.md): one sustained
note a file, 7-11 s, two dynamic layers (v1 soft, v2 loud). Their note names
run an OCTAVE LOW -- VSCO's C3 is middle C: the violins' lowest file is
"G2" -- and +12 puts the fundamental where the spectrum has it.

What a section's tremolo IS, measured off the summed sound: its level
envelope (10 ms RMS), over the steady part (0.6 s in to 0.4 s from the end,
past the onset and before any release), as

  rate     the peak of the envelope's modulation spectrum, 3-25 Hz: the
           players' common stroke rate
  spread   that peak's width (its half-power bandwidth, Hz): how far the
           players' rates differ -- one player is a line, a section a band
  depth    the envelope's swing, std/mean -- which turns out to be mostly
           NOT the tremolo: seven players a few cents apart beat against each
           other, and a render with the tremolo OFF reads 0.41 on it
  trem     the swing WITHIN 1.5 Hz of the stroke rate (the envelope band-
           passed there, its RMS x sqrt 2 over its mean): what the section
           keeps of each player's modulation once their phases have drifted
           apart -- and what the beating barely reaches
  band     the same three on the band 2-6 kHz, where the bow's scrape lives,
           against the fundamental's band: does the stroke modulate the
           TOP more than the note?

The model's tremolo_hz, tremolo_scatter and tremolo_depth are PER PLAYER;
these are what the section sums to. --model renders GM 44 at the same notes
and reads it the same way, so the two are compared like for like.
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

from voicefit import analytic_env, mono  # noqa: E402

NOTE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def note_of(path, offset=12):
    m = re.search(r'_([A-G])(#?)(\d)_', os.path.basename(path))
    if not m:
        return None
    return (int(m.group(3)) + 1) * 12 + NOTE[m.group(1)] + (1 if m.group(2) else 0) + offset


def modulation(env, sr):
    """(rate Hz, half-power width Hz, depth std/mean) of a level envelope."""
    e = env - env.mean()
    N = 1 << 18
    S = np.abs(np.fft.rfft(e * np.hanning(len(e)), N)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    b = (f >= 3.0) & (f <= 25.0)
    i = int(np.argmax(S[b]))
    fp, Sp = f[b][i], S[b][i]
    above = f[b][S[b] >= 0.5 * Sp]
    near = above[np.abs(above - fp) < 6.0]
    return float(fp), float(near.max() - near.min()), float(env.std() / env.mean())


def band_depth(env, sr, rate, half=1.5):
    """The envelope's swing within `half` Hz of `rate`, as an AM depth."""
    e = env - env.mean()
    E = np.fft.rfft(e)
    f = np.fft.rfftfreq(len(e), 1.0 / sr)
    E[np.abs(f - rate) > half] = 0.0
    b = np.fft.irfft(E, len(e))
    return float(np.sqrt(2.0) * b.std() / env.mean())


def measure(path, offset=12):
    x, sr = mono(path)
    n = note_of(path, offset)
    f0 = 440.0 * 2 ** ((n - 69) / 12.0)
    a, b = int(0.6 * sr), len(x) - int(0.4 * sr)
    if b - a < sr:
        return None
    x = x[a:b]
    w = int(0.01 * sr)
    k = np.ones(w) / w
    env = np.sqrt(np.convolve(x * x, k, 'same'))[w:-w]
    top = np.sqrt(np.convolve(analytic_env(x, sr, 2000.0, 6000.0) ** 2, k, 'same'))[w:-w]
    fun = np.sqrt(np.convolve(analytic_env(x, sr, f0 * 0.9, f0 * 1.1) ** 2, k, 'same'))[w:-w]
    m = re.search(r'_v(\d)', os.path.basename(path))
    tm = modulation(top, sr)
    return dict(note=n, f0=f0, vel=int(m.group(1)) if m else 0,
                all=modulation(env, sr), top=tm, fun=modulation(fun, sr),
                trem=band_depth(env, sr, tm[0]), trem_top=band_depth(top, sr, tm[0]))


def show(rows, title):
    print("== %s: %d notes" % (title, len(rows)))
    print("   v   rate Hz  spread Hz  depth   |  top: rate depth  |  fundamental: rate depth"
          "  |  trem (all, top)")
    for v in sorted({r['vel'] for r in rows}):
        rs = [r for r in rows if r['vel'] == v]
        med = lambda key, i: np.median([r[key][i] for r in rs])
        print("   %d   %6.2f    %5.2f    %.3f   |       %5.2f %.3f   |              %5.2f %.3f"
              "   |  %.3f %.3f  (%d)"
              % (v, med('all', 0), med('all', 1), med('all', 2), med('top', 0), med('top', 2),
                 med('fun', 0), med('fun', 2), np.median([r['trem'] for r in rs]),
                 np.median([r['trem_top'] for r in rs]), len(rs)))
    # register: the rate against the note
    f = np.array([r['f0'] for r in rows])
    rt = np.array([r['all'][0] for r in rows])
    if len(rows) > 3:
        print("   rate vs pitch: %+.2f Hz per octave" % np.polyfit(np.log2(f), rt, 1)[0])


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    refs = pos[0] if pos else os.path.expanduser("~/Documents/refs/trem/raw")
    every = []
    for inst in ("violin", "viola", "cello"):
        rows = [r for r in (measure(p) for p in sorted(glob.glob(os.path.join(refs, inst, "*.wav")))) if r]
        if "--files" in argv:
            for r in sorted(rows, key=lambda r: (r['vel'], r['note'])):
                print("  %-6s %3d v%d  rate %5.2f  spread %4.2f  depth %.3f  top %.3f  fund %.3f"
                      % (inst, r['note'], r['vel'], r['all'][0], r['all'][1], r['all'][2],
                         r['top'][2], r['fun'][2]))
        show(rows, inst)
        every += [(inst, r) for r in rows]
    if "--model" in argv:
        os.environ.setdefault("TUNING_REFLECT", "0")
        os.environ.setdefault("TUNING_MASTER_DB", "-14")
        import blockrender as B
        from pizz_model_notes import NAMES, one
        import patch_map as PM
        from roomtail import write_wav
        out = os.path.join(os.path.dirname(os.path.normpath(refs)), "model")
        os.makedirs(out, exist_ok=True)
        done = set()
        for inst, r in every:
            key = (inst, r['note'], r['vel'])
            if key in done:
                continue
            done.add(key)
            d = os.path.join(out, inst)
            os.makedirs(d, exist_ok=True)
            n = r['note']
            # named as the reference is, an octave low, so one reader serves both
            write_wav(os.path.join(d, "m_%s%d_v%d.wav" % (NAMES[n % 12], n // 12 - 2, r['vel'])),
                      one(PM.BOWED_SPLIT, 44, n, vel=(60 if r['vel'] == 1 else 100), secs=7.0), B.SR)
        for inst in ("violin", "viola", "cello"):
            rows = [m for m in (measure(p) for p in sorted(glob.glob(os.path.join(out, inst, "*.wav")))) if m]
            show(rows, "model " + inst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
