#!/usr/bin/env python3
"""GS 71.8 "Bs Clarinet": the bass clarinet over its whole compass, and how
its colour moves with effort -- measured on Iowa's pp, mf and ff runs.

    python3 examples/bsclar_fit.py             measure the three dynamics, fit effort_tilt
    python3 examples/bsclar_fit.py --demo OUT.wav   71.8 swelling pp -> ff -> pp, for the ear

tonelib.BassClarinetProperties was fitted to the mf runs alone (it plays GM
71's notes below D3); the pp and ff runs (~/Documents/refs/bassclarinet_dyn,
sources.md) give its EFFORT law, measured as the brass's and the Bb
clarinet's were (tonelib, effort_tilt):

  notes    a 20 ms RMS envelope over -40 dB re the file's loudest, held 0.6 s
  steady   0.25 s after the note speaks to 0.25 s before it stops
  pitch    the lowest spectral peak over 0.3 x the strongest, no lower than
           the run's first note (its Iowa name), to the semitone
  level    the steady part's RMS, dB (Iowa's gain is fixed across a set)
  ladder   h1-h12 each its peak, dB re h1; its TILT the least-squares slope
           against log2(harmonic), dB per doubling

Matched note for note by semitone across the dynamics; effort_tilt is the
tilt's change per dB of the level's change, a regression through zero over
every pp->mf, mf->ff and pp->ff pair.
"""
import glob
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

from drum_fit import read  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs")
SETS = {"pp": os.path.join(REFS, "bassclarinet_dyn", "clar_bs_pp_*.aiff"),
        "mf": os.path.join(REFS, "clar_bs_*.aiff"),
        "ff": os.path.join(REFS, "bassclarinet_dyn", "clar_bs_ff_*.aiff")}
NH = 12


def wav_of(aiff):
    """The run as a wav beside a scratch copy (sox), read as float."""
    out = os.path.join(os.environ.get("TMPDIR", "/tmp"), "bsclar_" + os.path.basename(aiff) + ".wav")
    if not os.path.exists(out):
        subprocess.run(["sox", aiff, "-b", "16", out], check=True)
    x, sr = read(out)
    return x.mean(1), sr


def notes(x, sr):
    n = int(0.02 * sr)
    e = np.sqrt(np.convolve(x ** 2, np.ones(n) / n, 'same'))
    on = e > e.max() * 10 ** (-40 / 20.0)
    d = np.diff(np.concatenate(([0], on.astype(int), [0])))
    st, en = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    return [(a, b) for a, b in zip(st, en) if b - a > 0.6 * sr]


NAMES = dict(C=0, Db=1, D=2, Eb=3, E=4, F=5, Gb=6, G=7, Ab=8, A=9, Bb=10, B=11)


def lowest_of(path):
    """The run's lowest note from its Iowa name ("..._Db2B2.aiff": Db2), MIDI."""
    import re
    m = re.search(r"([A-G]b?)(\d)[A-G]b?\d\.aiff$", path)
    return 12 * (int(m.group(2)) + 1) + NAMES[m.group(1)]


def f0_of(seg, sr, lo_midi):
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 8 * len(seg)))
    f = np.fft.rfftfreq(8 * len(seg), 1 / sr)
    ok = (f > 440.0 * 2 ** ((lo_midi - 1.5 - 69) / 12.0)) & (f < 1000)
    idx = np.flatnonzero(ok & (S > 0.3 * S[ok].max()))
    return float(f[idx[0]])


def ladder(seg, sr, f0):
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 4 * len(seg)))
    f = np.fft.rfftfreq(4 * len(seg), 1 / sr)
    out = [20 * np.log10(S[(f > f0 * (m - 0.3)) & (f < f0 * (m + 0.3))].max() + 1e-12)
           for m in range(1, NH + 1)]
    return np.array(out) - out[0]


def tilt(lad):
    return float(np.polyfit(np.log2(np.arange(1, NH + 1)), lad, 1)[0])


def measure(pattern):
    out = {}
    for p in sorted(glob.glob(pattern)):
        x, sr = wav_of(p)
        for a, b in notes(x, sr):
            seg = x[a + int(0.25 * sr):b - int(0.25 * sr)]
            if len(seg) < 0.3 * sr:
                continue
            f0 = f0_of(seg, sr, lowest_of(p))
            midi = int(round(69 + 12 * np.log2(f0 / 440.0)))
            lad = ladder(seg, sr, f0)
            q = dict(level=10 * np.log10(np.mean(seg ** 2) + 1e-20), ladder=lad, tilt=tilt(lad))
            if midi not in out or q["level"] > out[midi]["level"]:
                out[midi] = q
    return out


def demo(out):
    """Bs Clarinet (71.8, the SC-88 map) on G2 and on G3, eight notes each,
    velocity 40 -> 127 -> 40: effort is velocity against the part's median, so
    the swell spans about -9 to +8 dB."""
    import mido
    import blockrender as B
    from efx_demo import _sx
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); mf.tracks.append(tr)
    tr.append(_sx(0x40, 0x00, 0x7F, 0x00))
    for c, v in ((0, 8), (32, 2)):
        tr.append(mido.Message("control_change", channel=0, control=c, value=v))
    tr.append(mido.Message("program_change", channel=0, program=71))
    vels = (40, 64, 88, 112, 127, 104, 72, 40)
    for note in (43, 55):
        for i, v in enumerate(vels):
            tr.append(mido.Message("note_on", channel=0, note=note, velocity=v, time=480 if i or note == 55 else 0))
            tr.append(mido.Message("note_off", channel=0, note=note, velocity=0, time=600))
    L, R = B.render(mf, "even")[:2]
    x = np.stack([np.asarray(L), np.asarray(R)], 1)
    x = x / np.abs(x).max() * 10 ** (-1 / 20.0)
    from scipy.io import wavfile
    wavfile.write(out, B.SR, (x * 32767).astype(np.int16))
    print("  wrote %s" % out)


def main(argv):
    if "--demo" in argv:
        return demo(argv[argv.index("--demo") + 1]) or 0
    M = {k: measure(v) for k, v in SETS.items()}
    for k in M:
        print("  %s: %d notes, MIDI %d-%d" % (k, len(M[k]), min(M[k]), max(M[k])))
    dl, dt, rows = [], [], []
    for a, b in (("pp", "mf"), ("mf", "ff"), ("pp", "ff")):
        common = sorted(set(M[a]) & set(M[b]))
        L = np.array([M[b][n]["level"] - M[a][n]["level"] for n in common])
        T = np.array([M[b][n]["tilt"] - M[a][n]["tilt"] for n in common])
        rows.append((a, b, len(common), np.median(L), np.median(T)))
        if a + b != "ppff":
            dl += list(L); dt += list(T)
    print("  pair      notes  louder (median)  tilt (median)  dB/dB")
    for a, b, n, l, t in rows:
        print("  %s->%s  %5d  %+8.2f dB     %+7.2f dB    %.2f" % (a, b, n, l, t, t / l if l else np.nan))
    dl, dt = np.array(dl), np.array(dt)
    k = float(np.sum(dl * dt) / np.sum(dl * dl))
    r = float(np.corrcoef(dl, dt)[0, 1])
    print("  effort_tilt = %.3f dB of tilt per dB of level (through zero, %d pairs; r %.2f)" % (k, len(dl), r))
    for reg, lo, hi in (("below D3", 0, 50), ("D3-C#4", 50, 61), ("D4-", 62, 128)):
        s = [(l, t) for (l, t, n) in zip(dl, dt, [n for a, b in (("pp", "mf"), ("mf", "ff"))
                                                  for n in sorted(set(M[a]) & set(M[b]))]) if lo <= n < hi]
        if len(s) > 3:
            s = np.array(s)
            print("    %-9s %3d pairs: %.3f" % (reg, len(s), np.sum(s[:, 0] * s[:, 1]) / np.sum(s[:, 0] ** 2)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
