#!/usr/bin/env python3
"""The SC-88 map's brass variations, from Iowa's pp and ff runs: each a
dynamic of its GM voice, fitted as a difference from the mf takes the GM
voices were fitted to (the harmonium registers' rule).

    python3 examples/brass_dyn_fit.py              measure pp and ff re mf, per instrument and register

Each Iowa file is a chromatic run, one note per breath with silence between
(~/Documents/refs/brass_dyn, sources.md):

  notes    a 20 ms RMS envelope over -40 dB re the file's loudest and 6 dB over
           its floor (the 3rd percentile: the tuba's runs sit on hiss), held 0.6 s
  steady   0.25 s after the note speaks to 0.25 s before it stops
  pitch    of the semitones over the run's octave (its Iowa name), the one
           whose harmonics stand highest over the spectrum midway between them
  ladder   h1-h16 each its peak, dB re the strongest of them; left out where
           it stands under SNR_DB (20) over the spectrum midway to the next
  level    the steady part's RMS, dB (Iowa's gain is fixed across a set)

Matched note for note by semitone, so a difference is the dynamic's and not
the register's; reported as the median over each octave, and its TILT, the
least-squares slope against log2(harmonic) in dB per doubling. A difference
is taken re its own h1-h3 (low_aligned).

THE FIT is three numbers on GM's own voices at the matched notes
(tonelib.SynthProperties.blare_db_per_khz): above a knee the change runs in dB
per kHz, held at a cap -- the same line in every register, where a tilt (a
power of the harmonic number) or the bore's corner missed it by 2 dB on the
trombone's ff; this misses by 0.9.

    python3 examples/brass_dyn_fit.py --fit INST.DYN   fit the difference on GM's own voices
"""
import glob
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

from drum_fit import read  # noqa: E402
from sax_exp_fit import vibrato  # noqa: E402

DYN = os.path.expanduser("~/Documents/refs/brass_dyn")
INSTRUMENTS = {
    "trumpet": dict(mf="Trumpet.novib.mf.*.aiff", pp="Trumpet.novib.pp.*.aiff",
                    ff="Trumpet.novib.ff.*.aiff", vib="Trumpet.vib.mf.*.aiff", program=56),
    "trombone": dict(mf="TenorTrombone.mf.*.aiff", pp="TenorTrombone.pp.*.aiff",
                     ff="TenorTrombone.ff.*.aiff", program=57),
    "tuba": dict(mf="Tuba.mf.*.aiff", pp="Tuba.pp.*.aiff", ff="Tuba.ff.*.aiff", program=58),
    "horn": dict(mf="Horn.mf.*.aiff", pp="Horn.pp.*.aiff", ff="Horn.ff.*.aiff", program=60),
}
# the mf runs the GM fits used, already under refs/ by other names
MF_ELSEWHERE = {
    "trumpet": ("tp_E3B3.aiff", "tp_C4B4.aiff", "tp_C5B5.aiff"),
    "trombone": ("tbn_E2B2.aiff", "trombone.aiff", "tbn_C4B4.aiff"),
    "tuba": ("tuba_C1B1.aiff", "tuba.aiff", "tuba_C3C4.aiff"),
    "horn": ("horn.aiff", "horn_c4.aiff"),
}
LOWEST = {"tp_E3B3.aiff": 52, "tp_C4B4.aiff": 60, "tp_C5B5.aiff": 72, "tbn_E2B2.aiff": 40,
          "trombone.aiff": 48, "tbn_C4B4.aiff": 60, "tuba_C1B1.aiff": 24, "tuba.aiff": 36,
          "tuba_C3C4.aiff": 48, "horn.aiff": 36, "horn_c4.aiff": 60}
NH = 16
SNR_DB = float(os.environ.get("SNR_DB", 20.0))      # 10 let the horn's and tuba's pp hiss through
NAMES = dict(C=0, Db=1, D=2, Eb=3, E=4, F=5, Gb=6, G=7, Ab=8, A=9, Bb=10, B=11)


def lowest_of(path):
    b = os.path.basename(path)
    if b in LOWEST:
        return LOWEST[b]
    m = re.search(r"\.([A-G]b?)(\d)(?:[A-G]b?\d)?\.aiff$", b)
    return 12 * (int(m.group(2)) + 1) + NAMES[m.group(1)]


def wav_of(aiff):
    out = os.path.join(os.environ.get("TMPDIR", "/tmp"), "brassdyn_" + os.path.basename(aiff) + ".wav")
    if not os.path.exists(out):
        subprocess.run(["sox", aiff, "-b", "16", out], check=True)
    x, sr = read(out)
    return x.mean(1), sr


def notes(x, sr):
    n = int(0.02 * sr)
    e = np.sqrt(np.convolve(x ** 2, np.ones(n) / n, 'same'))
    floor = np.percentile(e[e > 0], 3)
    on = e > max(e.max() * 10 ** (-40 / 20.0), floor * 2.0)
    d = np.diff(np.concatenate(([0], on.astype(int), [0])))
    st, en = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    return [(a, b) for a, b in zip(st, en) if b - a > 0.6 * sr]


def f0_of(seg, sr, lo_midi):
    """The run's note: of the semitones lo_midi-1 .. lo_midi+13 (a run spans an
    octave), the one whose harmonics h1-h8 stand highest over the spectrum
    midway between them -- an octave up leaves the odd harmonics between its
    own, an octave down puts its own between the real ones -- then its h1 peak."""
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 8 * len(seg)))
    f = np.fft.rfftfreq(8 * len(seg), 1 / sr)
    df = f[1]

    def at(hz):
        k = int(round(hz / df)); w = max(2, int(0.02 * hz / df))
        return np.log(S[max(0, k - w):k + w + 1].max() + 1e-12)
    best, f0 = -1e9, None
    for m in range(lo_midi - 1, lo_midi + 14):
        c = 440.0 * 2 ** ((m - 69) / 12.0)
        sc = np.mean([at(c * h) for h in range(1, 9)]) - np.mean([at(c * (h + 0.5)) for h in range(1, 9)])
        if sc > best:
            best, f0 = sc, c
    k = (f > f0 * 0.97) & (f < f0 * 1.03)
    return float(f[k][np.argmax(S[k])])


def ladder(seg, sr, f0):
    """h1-h16 dB re the strongest; NaN where a harmonic stands less than
    SNR_DB over the spectrum midway to the next (the hiss under a pp)."""
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 4 * len(seg)))
    f = np.fft.rfftfreq(4 * len(seg), 1 / sr)
    out = np.full(NH, np.nan)
    for m in range(1, NH + 1):
        if f0 * (m + 0.7) >= sr / 2:
            break
        pk = 20 * np.log10(S[(f > f0 * (m - 0.3)) & (f < f0 * (m + 0.3))].max() + 1e-12)
        fl = 20 * np.log10(np.median(S[(f > f0 * (m + 0.35)) & (f < f0 * (m + 0.65))]) + 1e-12)
        if pk - fl >= SNR_DB:
            out[m - 1] = pk
    return out - np.nanmax(out)


def tilt(d):
    ok = np.isfinite(d)
    return float(np.polyfit(np.log2(np.arange(1, NH + 1))[ok], d[ok], 1)[0])


def low_aligned(d):
    """A difference of ladders, re its own h1-h3: what changes ABOVE the
    harmonics carrying the note (a ladder re its strongest moves its bottom
    whenever its top overtakes it)."""
    return d - np.nanmean(d[:3])


def measure(paths):
    out = {}
    for p in paths:
        x, sr = wav_of(p)
        for a, b in notes(x, sr):
            seg = x[a + int(0.25 * sr):b - int(0.25 * sr)]
            if len(seg) < 0.3 * sr:
                continue
            f0 = f0_of(seg, sr, lowest_of(p))
            midi = int(round(69 + 12 * np.log2(f0 / 440.0)))
            q = dict(f0=f0, level=10 * np.log10(np.mean(seg ** 2) + 1e-20), ladder=ladder(seg, sr, f0),
                     vib=vibrato(seg, sr, f0))
            if midi not in out or q["level"] > out[midi]["level"]:
                out[midi] = q
    return out


def sets(inst):
    spec = INSTRUMENTS[inst]
    S = {}
    for k in ("mf", "pp", "ff", "vib"):
        if k in spec:
            S[k] = sorted(glob.glob(os.path.join(DYN, spec[k])))
    refs = os.path.dirname(DYN)
    S["mf"] += [os.path.join(refs, f) for f in MF_ELSEWHERE[inst]
                if not any(lowest_of(os.path.join(refs, f)) == lowest_of(q) for q in S["mf"])]
    return S


def differences(inst):
    M = {k: measure(v) for k, v in sets(inst).items()}
    out = {}
    for k in M:
        if k == "mf":
            continue
        common = sorted(set(M[k]) & set(M["mf"]))
        out[k] = dict(notes=common,
                      d=np.array([low_aligned(M[k][n]["ladder"] - M["mf"][n]["ladder"]) for n in common]),
                      dl=np.array([M[k][n]["level"] - M["mf"][n]["level"] for n in common]),
                      f0=[M["mf"][n]["f0"] for n in common],
                      vib=[M[k][n]["vib"] for n in common if M[k][n]["vib"]],
                      vib_mf=[M["mf"][n]["vib"] for n in common if M["mf"][n]["vib"]])
    return M, out


REGISTER = 12          # the fit's groups, semitones from MIDI 0


def ours(cls, f0):
    pr = cls(f0, 0.0, (90 / 127.0) ** 2, 1.0)
    a = np.array([abs(pr.harmonic_volume(m)) if m <= getattr(pr, "max_harmonic", NH) else 0.0
                  for m in range(1, NH + 1)])
    L = 20 * np.log10(np.maximum(a, 1e-12))
    return L - L.max()


def delta_attrs(v):
    """The difference, on every class the program routes to: the blare above
    its knee (tonelib.SynthProperties.blare_db_per_khz), held at a cap."""
    k, knee, cap = v
    return dict(blare_db_per_khz=k, blare_knee_hz=knee, blare_cap_db=cap)


def fit(inst, q):
    """The three knobs on GM's own voices at the matched notes, fitted to the
    difference's per-register medians (the noise-masked harmonics left out)."""
    from scipy.optimize import minimize
    import patch_map as P
    prog = INSTRUMENTS[inst]["program"]
    notes = q["notes"]
    regs = sorted({n // REGISTER for n in notes})
    groups = {r: [i for i, n in enumerate(notes) if n // REGISTER == r] for r in regs}
    groups = {r: g for r, g in groups.items() if len(g) >= 3}
    want = {r: np.nanmedian(q["d"][g], axis=0) for r, g in groups.items()}
    base = {i: P.property_class_for_note(prog, notes[i]) for i in range(len(notes))}
    L0 = {i: ours(base[i], q["f0"][i]) for i in base}
    cache = {}

    def model(v):
        at = delta_attrs(v)
        out = {}
        for r, g in groups.items():
            d = []
            for i in g:
                c = base[i]
                key = (c, tuple(np.round(v, 6)))
                if key not in cache:
                    cache[key] = type("Fit", (c,), at)
                d.append(low_aligned(ours(cache[key], q["f0"][i]) - L0[i]))
            out[r] = np.median(d, axis=0)
        return out

    def err(v):
        if not -60 < v[0] < 60 or not 100 < v[1] < 3000 or not 3 < v[2] < 60:
            return 99.0
        m = model(v)
        e = [np.abs(m[r][1:] - want[r][1:]) for r in groups]
        e = np.concatenate(e)
        return float(np.nanmean(e))
    x0 = np.array([0.0, 600.0, 30.0])
    s0 = 10.0 if np.nanmean([np.nanmean(w[4:]) for w in want.values()]) > 0 else -10.0
    r = minimize(err, x0, method="Nelder-Mead", options=dict(xatol=1e-2, fatol=1e-3, maxfev=600,
                                                             initial_simplex=[[s0, 600, 30], [s0 * 0.5, 600, 30],
                                                                              [s0, 1000, 30], [s0, 600, 15]]))
    return r.x, err(x0), r.fun, want, model(r.x)


def main(argv):
    if "--fit" in argv:
        inst, dyn = argv[argv.index("--fit") + 1].split(".")
        M, D = differences(inst)
        v, e0, e1, want, got = fit(inst, D[dyn])
        print("  %s %s re mf: blare %+.1f dB/kHz over %.0f Hz, held at %.1f dB  (miss %.2f -> %.2f dB)"
              % (inst, dyn, v[0], v[1], v[2], e0, e1))
        for r in want:
            print("    oct %d  Iowa %s" % (r - 1, " ".join("%+4.0f" % x if np.isfinite(x) else "  --" for x in want[r])))
            print("           ours %s" % " ".join("%+4.0f" % x for x in got[r]))
        return 0
    for inst in [a for a in argv[1:] if a in INSTRUMENTS] or list(INSTRUMENTS):
        M, D = differences(inst)
        print("== %s: mf %d notes (MIDI %d-%d)" % (inst, len(M["mf"]), min(M["mf"]), max(M["mf"])))
        for k, q in D.items():
            print("  %s re mf: %d notes matched, %+.1f dB louder (median)" % (k, len(q["notes"]), np.median(q["dl"])))
            for lo in range(min(q["notes"]) // 12 * 12, max(q["notes"]) + 1, 12):
                sel = [i for i, n in enumerate(q["notes"]) if lo <= n < lo + 12]
                if len(sel) < 3:
                    continue
                d = np.nanmedian(q["d"][sel], axis=0)
                print("    oct %d (%2d): tilt %+5.1f  h1-h16 %s" % (lo // 12 - 1, len(sel), tilt(d),
                                                          " ".join("%+4.0f" % v if np.isfinite(v) else "  --" for v in d)))
            if k == "vib":
                print("    vibrato %.2f Hz, %.1f cents (median of %d); mf %.2f Hz, %.1f cents"
                      % (np.median([v[0] for v in q["vib"]]), np.median([v[1] for v in q["vib"]]), len(q["vib"]),
                         np.median([v[0] for v in q["vib_mf"]]), np.median([v[1] for v in q["vib_mf"]])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
