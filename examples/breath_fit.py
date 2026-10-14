#!/usr/bin/env python3
"""Fit the breath (GM 121) to two takes of breathing: a coloured noise that
swells in, no pitch. sources.md "Sound effects".

    python3 -I examples/breath_fit.py measure      the breaths, and ours
    python3 -I examples/breath_fit.py fit          the noise table and its swell (writes tonelib.py)
    python3 -I examples/breath_fit.py ab OUT.wav   breaths, then ours

THE TAKES (CC0, Freesound): beerre's relaxed breathing, unprocessed, Zoom H4n
(622601, 105 s); superEGsonic's slow inhale and nervous exhale (273979).
Each breath found where the level stands 12 dB over the take's floor.

WHAT THEY HOLD, from 250 Hz up: the breath's colour, the same whatever key
-- a breath has no pitch. Under 250 Hz the takes are the breath blowing on
the microphone (beerre's 63 Hz octave is its loudest): not read. Ours had
been 64 partials at the key, dithered into noise -- its colour following
the key, brightest at 16 kHz.
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import upright_fit as U

FS = os.path.expanduser("~/Documents/refs/freesound/breath")
CEN = tuple(int(round(250 * 2 ** (k / 3.0))) for k in range(0, 19))     # 250 Hz - 15.9 kHz
LOW = (63, 80, 101, 127, 160, 202)                                      # under the read: held low
KEY = 60


def load(p):
    from scipy.io import wavfile
    import warnings
    warnings.simplefilter("ignore")
    sr, x = wavfile.read(p)
    x = x.astype(np.float64)
    x = x.mean(1) if x.ndim > 1 else x
    return x / np.abs(x).max(), sr


def _mov(x, w):
    c = np.concatenate(([0.0], np.cumsum(x)))
    return (c[w:] - c[:-w]) / w


def breaths(x, sr):
    """[(start, end) samples] where the 50 ms level stands 12 dB over the
    take's 10th percentile, 0.4 s or longer."""
    w = int(0.05 * sr)
    e = 10 * np.log10(_mov(x * x, w)[::w] + 1e-12)
    on = e > np.percentile(e, 10) + 12
    out, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            if (j - i) * 0.05 >= 0.4:
                out.append((i * w, j * w))
            i = j
        else:
            i += 1
    return out


def thirds(x, sr):
    """Energy in CEN's third-octave bands (linear)."""
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)), 1 << 16)) ** 2
    f = np.fft.rfftfreq(1 << 16, 1.0 / sr)
    return np.array([X[(f >= c / 2 ** (1 / 6.0)) & (f < c * 2 ** (1 / 6.0))].sum() for c in CEN])


def rise(x, sr, a, b):
    w = int(0.05 * sr)
    e = 10 * np.log10(_mov(x[a:b] ** 2, w)[::w] + 1e-12)
    return float(np.flatnonzero(e > e.max() - 6)[0] * 0.05)


def target():
    specs, rises = [], []
    for p in sorted(glob.glob(os.path.join(FS, "*.wav"))):
        x, sr = load(p)
        S = np.zeros(len(CEN))
        for a, b in breaths(x, sr):
            # each breath in 0.4 s pieces, summed: energy-weighted
            for k in range(a, b - int(0.4 * sr), int(0.4 * sr)):
                S += thirds(x[k:k + int(0.4 * sr)], sr)
            rises.append(rise(x, sr, a, b))
        S = 10 * np.log10(S + 1e-30)
        specs.append(S - S.max())
    return np.mean(specs, 0), float(np.median(rises))


def ours():
    y, sr = U.render(121, KEY, 100, 2.5)
    a = int(np.flatnonzero(np.abs(y) > 0.01 * np.abs(y).max())[0])
    S = np.zeros(len(CEN))
    for k in range(a + int(0.5 * sr), a + int(2.0 * sr), int(0.4 * sr)):
        S += thirds(y[k:k + int(0.4 * sr)], sr)
    S = 10 * np.log10(S + 1e-30)
    return S - S.max(), rise(y, sr, a, a + int(2.4 * sr))


def measure():
    R, r = target()
    print("  breaths: thirds from 250 Hz %s | rise to -6 dB %.2f s" % (" ".join("%+4.0f" % v for v in R), r))
    O, ro = ours()
    print("  ours:    thirds from 250 Hz %s | rise to -6 dB %.2f s" % (" ".join("%+4.0f" % v for v in O), ro))


def fit(passes=6):
    """breath_noise_db (dB re the note's gain) band by band toward the
    breaths' colour, and breath_noise_fade_s toward their rise."""
    import tonelib as T
    cls = T.BreathNoiseProperties
    R, r = target()
    tab = np.zeros(len(CEN))
    cls.breath_noise_fade_s = max(0.05, 2.0 * r)
    for it in range(passes + 1):
        cls.breath_noise_db = tuple([(c, round(float(tab[0] - 20.0), 1)) for c in LOW] +
                                    [(c, round(float(v), 1)) for c, v in zip(CEN, tab)])
        O, ro = ours()
        d = R - O
        print("  pass %d: breaths - ours rms %.1f dB over %d thirds; rise %.2f against %.2f (fade %.2f s)" % (
            it, np.sqrt(np.mean(d ** 2)), len(d), ro, r, cls.breath_noise_fade_s), flush=True)
        if it == passes:
            break
        tab += 0.8 * d
        cls.breath_noise_fade_s = float(np.clip(cls.breath_noise_fade_s * (r / max(ro, 0.02)) ** 0.7, 0.03, 3.0))
    path = os.path.join(os.path.dirname(HERE), "tonelib.py")
    src = open(path).read()
    a = src.index("class BreathNoiseProperties(")
    b = a + re.search(r"\n(?=\S)", src[a + 10:]).start() + 10
    body = src[a:b].rstrip("\n")
    for k in ("breath_noise_db", "breath_noise_fade_s"):
        body = re.sub(r"^    %s = .*\n?" % k, "", body, flags=re.M)
    body += "\n    breath_noise_fade_s = %.3f\n    breath_noise_db = %s\n" % (cls.breath_noise_fade_s, cls.breath_noise_db)
    open(path, "w").write(src[:a] + body + src[b:])
    print("  written")


def ab(out):
    import harpsi_ab as A
    from roomtail import write_wav
    gap = np.zeros(int(0.5 * A.SR))
    parts = []
    for p in sorted(glob.glob(os.path.join(FS, "*.wav"))):
        x, sr = load(p)
        for a, b in breaths(x, sr)[:3]:
            A.NOTE_S = (b - a) / sr + 0.3
            parts += [A.fit_note(x[a:b + int(0.3 * sr)], sr), gap]
    y, sr2 = U.render(121, KEY, 100, 2.0)
    A.NOTE_S = 2.5
    parts += [gap, A.fit_note(y, sr2)]
    z = np.concatenate(parts)
    write_wav(out, np.stack([z, z], 1), A.SR)


def main(argv):
    if argv[1:2] == ["measure"]:
        measure()
    elif argv[1:2] == ["fit"]:
        fit()
    elif argv[1:2] == ["ab"]:
        ab(argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
