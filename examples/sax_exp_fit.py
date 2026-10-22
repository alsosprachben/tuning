#!/usr/bin/env python3
"""GS 65.8 "AltoSax Exp." (the SC-88's "Hyper Alto"): the alto saxophone
played out -- what Iowa's AltoSax.Vib.ff takes have that the NoVib.mf ones GM
65 was fitted to (tonelib.SaxophoneProperties) have not.

    python3 examples/sax_exp_fit.py            measure both sets, fit the difference

FITTED AS A DIFFERENCE from the foundation, not absolutely (the harmonium
registers' rule): GM 65 is already fitted to the mf takes, so what the ff
vibrato takes add -- a brighter ladder, a vibrato of their own -- is fitted
onto it, and the fit's own misses on the shared foundation cancel.

Each Iowa file is a chromatic run, one note per breath with silence between
(~/Documents/refs/sax_a_*.wav, sources.md):

  notes    a 20 ms RMS envelope over -35 dB re the file's loudest, held 0.6 s
  steady   0.25 s after the note speaks to 0.25 s before it stops
  ladder   each harmonic's peak, h1-h12, dB re h1, over the steady part
  vibrato  the fundamental's frequency every 10 ms (its spectral peak,
           parabolic), detrended over 0.5 s: the rate the strongest
           modulation between 3 and 9 Hz, the depth its peak deviation in
           cents (sqrt 2 x rms)

Matched note for note by pitch (the same semitone in both sets), so the
ladder's change is the dynamic's and the player's, not the register's.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

from drum_fit import read  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs")
RUNS = ("Db3B3", "C4B4", "C5Ab5")
SETS = {"mf": "sax_a_%s.wav", "ff_vib": "sax_a_vib_ff_%s.wav"}
NH = 12


def notes(x, sr):
    n = int(0.02 * sr)
    e = np.sqrt(np.convolve(x ** 2, np.ones(n) / n, 'same'))
    on = e > e.max() * 10 ** (-35 / 20.0)
    d = np.diff(np.concatenate(([0], on.astype(int), [0])))
    st, en = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    return [(a, b) for a, b in zip(st, en) if b - a > 0.6 * sr]


def f0_of(seg, sr):
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 8 * len(seg)))
    f = np.fft.rfftfreq(8 * len(seg), 1 / sr)
    ok = (f > 120) & (f < 1100)
    # the lowest strong peak: a harmonic over half the strongest's level
    pk = S[ok].max()
    idx = np.flatnonzero(ok & (S > 0.5 * pk))
    return float(f[idx[0]] if len(idx) else f[ok][np.argmax(S[ok])])


def ladder(seg, sr, f0):
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 4 * len(seg)))
    f = np.fft.rfftfreq(4 * len(seg), 1 / sr)
    out = []
    for m in range(1, NH + 1):
        w = (f > f0 * (m - 0.3)) & (f < f0 * (m + 0.3))
        out.append(20 * np.log10(S[w].max() + 1e-12) if w.any() else -200.0)
    return np.array(out) - out[0]


def vibrato(seg, sr, f0):
    hop, win = int(0.01 * sr), int(0.06 * sr)
    tr = []
    for i in range(0, len(seg) - win, hop):
        c = seg[i:i + win] * np.hanning(win)
        S = np.abs(np.fft.rfft(c, 8 * win)); f = np.fft.rfftfreq(8 * win, 1 / sr)
        w = np.flatnonzero((f > f0 * 0.94) & (f < f0 * 1.06))
        k = w[np.argmax(S[w])]
        a, b, g = np.log(S[k - 1] + 1e-12), np.log(S[k] + 1e-12), np.log(S[k + 1] + 1e-12)
        tr.append(f[k] + 0.5 * (a - g) / (a - 2 * b + g) * (f[1] - f[0]))
    c = 1200 * np.log2(np.array(tr) / f0)
    n = 50                                            # 0.5 s detrend
    c = c - np.convolve(c, np.ones(n) / n, 'same')
    c = c[n // 2:-n // 2]
    if len(c) < 64:
        return None
    C = np.abs(np.fft.rfft(c * np.hanning(len(c)), 8 * len(c)))
    fr = np.fft.rfftfreq(8 * len(c), 0.01)
    ok = (fr > 3) & (fr < 9)
    return float(fr[ok][np.argmax(C[ok])]), float(np.sqrt(2) * c.std())


def measure(which):
    out = {}
    for r in RUNS:
        x, sr = read(os.path.join(REFS, SETS[which] % r))
        x = x[:, 0] if x.ndim > 1 else x
        for a, b in notes(x, sr):
            seg = x[a + int(0.25 * sr):b - int(0.25 * sr)]
            if len(seg) < int(0.4 * sr):
                continue
            f0 = f0_of(seg, sr)
            midi = int(round(69 + 12 * np.log2(f0 / 440.0)))
            if midi in out:
                continue
            out[midi] = dict(f0=f0, ladder=ladder(seg, sr, f0), vib=vibrato(seg, sr, f0))
    return out


def ours(cls, f0, vel=100):
    pr = cls(f0, 0.0, (vel / 127.0) ** 2, 1.0)
    a = np.array([abs(pr.harmonic_volume(m)) for m in range(1, NH + 1)])
    return 20 * np.log10(np.maximum(a, 1e-12) / a[0])


def main(argv):
    from scipy.optimize import minimize
    import tonelib as T
    M = {k: measure(k) for k in SETS}
    keys = sorted(set(M["mf"]) & set(M["ff_vib"]))
    print("  notes: mf %d, ff vib %d, matched %d (MIDI %d-%d)"
          % (len(M["mf"]), len(M["ff_vib"]), len(keys), keys[0], keys[-1]))
    d = np.array([M["ff_vib"][k]["ladder"] - M["mf"][k]["ladder"] for k in keys])
    want = np.median(d, axis=0)
    print("  ff vib re mf, h1-h12 (median dB):", " ".join("%+5.1f" % v for v in want))
    vib = [M["ff_vib"][k]["vib"] for k in keys if M["ff_vib"][k]["vib"]]
    vib0 = [M["mf"][k]["vib"] for k in keys if M["mf"][k]["vib"]]
    rate = float(np.median([v[0] for v in vib])); depth = float(np.median([v[1] for v in vib]))
    print("  vibrato: ff vib %.2f Hz, %.1f cents (median of %d); mf %.2f Hz, %.1f cents"
          % (rate, depth, len(vib), np.median([v[0] for v in vib0]), np.median([v[1] for v in vib0])))
    # THE DIFFERENCE, fitted on ours: the knobs that tilt the ladder
    base = T.SaxophoneProperties
    f0s = [M["mf"][k]["f0"] for k in keys]
    L0 = np.array([ours(base, f) for f in f0s])
    knobs = ("tonal_dampening", "formant_floor")

    def err(v):
        cls = type("Fit", (base,), dict(zip(knobs, v)))
        L = np.array([ours(cls, f) for f in f0s])
        return float(np.mean(np.abs(np.median(L - L0, axis=0)[1:] - want[1:])))
    x0 = np.array([getattr(base, k) for k in knobs])
    r = minimize(err, x0, method="Nelder-Mead", options=dict(xatol=1e-3, fatol=1e-3, maxfev=300))
    print("  fit: %s  (miss %.2f dB from %.2f)"
          % (", ".join("%s %.3f -> %.3f" % (k, a, b) for k, a, b in zip(knobs, x0, r.x)), r.fun, err(x0)))
    cls = type("Fit", (base,), dict(zip(knobs, r.x)))
    got = np.median(np.array([ours(cls, f) for f in f0s]) - L0, axis=0)
    print("  ours re GM 65, h1-h12:          ", " ".join("%+5.1f" % v for v in got))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
