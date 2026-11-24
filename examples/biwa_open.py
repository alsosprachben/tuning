#!/usr/bin/env python3
"""THE SATSUMA BIWA FROM OPEN RECORDINGS (since 2026-11-23, licences.md L4:
PARADISEC's CC BY-NC-SA tape no longer read). The strokes are staged by
examples/pluck_fit.py (BIWA_REF=open --voice=biwa --stage): Takahisa Suda's
own CC BY videos and Yuuka Yamana's concert at INAH (CC BY).

    python3 examples/biwa_open.py --survey      the strokes against ours
    python3 examples/biwa_open.py --fit=strike  strike_noise_db toward them
    python3 examples/biwa_open.py --fit=buzz    the sawari: drain and top, a grid

Each stroke, three measures (pluck_fit's render at the stroke's own pitch):
  FALL   its level 50/100/200/400 ms after the peak, dB re the peak
  HARM   h1-h12 over its first 0.3 s, dB re the loudest of h1-h3
  NOISE  energy BETWEEN the partials (0.8 f0 - 8 kHz) re energy on them --
         the bachi slapping the wooden belly with the string, the sawari
And THE BACHI: the first 30 ms between the partials, third-octave bands,
fitted band by band as koto_fit.py fits the tsume (koto_fit.pluck)."""
import glob
import os
import re
import sys
import warnings

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
STAGED = os.path.expanduser("~/Documents/refs/freesound/staged/biwa")


def _pf():
    import pluck_fit as P
    P.PROG, P.CLS, P.BANK = 120, "BiwaProperties", 12
    return P


def mono(p):
    from scipy.io import wavfile
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sr, y = wavfile.read(p)
    y = y.astype(np.float64)
    return (y.mean(1) if y.ndim > 1 else y), sr


def strokes(min_secs=0.45):
    out = []
    for p in sorted(glob.glob(os.path.join(STAGED, "*.wav"))):
        f0 = float(re.search(r"_f0_([0-9.]+)\.wav$", p).group(1))
        y, sr = mono(p)
        if len(y) >= int(min_secs * sr):
            out.append((f0, y, sr))
    return out


def ours(f0, secs=0.6):
    y, sr = _pf().render(f0, secs)
    y = np.asarray(y, np.float64)
    return (y.mean(1) if y.ndim > 1 else y), sr


def measure(y, sr, f0, N=12):
    y = y / np.abs(y).max()
    w = int(0.01 * sr)
    e = 20 * np.log10(np.sqrt(np.convolve(y * y, np.ones(w) / w, "same")) + 1e-9)
    pk = int(np.argmax(e[:int(0.1 * sr)]))
    fall = np.array([e[min(len(e) - 1, pk + int(t * sr))] - e[pk] for t in (0.05, 0.1, 0.2, 0.4)])
    s = y[pk:pk + int(0.3 * sr)]
    X = np.abs(np.fft.rfft(s * np.hanning(len(s)), 1 << 15))
    f = np.fft.rfftfreq(1 << 15, 1.0 / sr)
    h = np.array([20 * np.log10(X[(f > f0 * n * 0.97) & (f < f0 * n * 1.03)].max() + 1e-12) for n in range(1, N + 1)])
    h -= h[:3].max()
    P2 = X ** 2
    on = np.zeros(len(f), bool)
    for n in range(1, 40):
        on |= (f > f0 * n * 0.97) & (f < f0 * n * 1.03)
    sel = (f > 0.8 * f0) & (f < 8000)
    noise = 10 * np.log10(P2[sel & ~on].sum() / P2[sel & on].sum())
    # COURSE: the band under 1 kHz against the band over 1.5 kHz at 10, 50,
    # 100, 200, 300 ms -- the sawari draining the low harmonics into the top
    # (the sitar's measure, pluck_fit's prompt/quick bands, here as one curve)
    course = []
    for t in (0.01, 0.05, 0.1, 0.2, 0.3):
        a = pk + int(t * sr)
        seg = y[a:a + int(0.04 * sr)]
        if len(seg) < int(0.04 * sr):
            course.append(np.nan)
            continue
        Z = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 13)) ** 2
        fz = np.fft.rfftfreq(1 << 13, 1.0 / sr)
        course.append(10 * np.log10(Z[(fz > 0.8 * f0) & (fz < 1000)].sum() / Z[(fz > 1500) & (fz < 8000)].sum()))
    return fall, h, noise, np.array(course)


def survey():
    S = strokes()
    R = [measure(y, sr, f0) for f0, y, sr in S]
    O = [measure(*ours(f0), f0) for f0, _, _ in S]
    for nm, k in (("fall 50/100/200/400 ms", 0), ("h1-h12", 1)):
        print("  %-22s takes %s" % (nm, " ".join("%5.1f" % v for v in np.median([r[k] for r in R], 0))))
        print("  %-22s ours  %s" % ("", " ".join("%5.1f" % v for v in np.median([o[k] for o in O], 0))))
    print("  low/high band 10-300ms takes %s" % " ".join("%5.1f" % v for v in np.nanmedian([r[3] for r in R], 0)))
    print("                         ours  %s" % " ".join("%5.1f" % v for v in np.nanmedian([o[3] for o in O], 0)))
    print("  between/on partials    takes %.1f dB  ours %.1f dB  (%d strokes)"
          % (np.median([r[2] for r in R]), np.median([o[2] for o in O]), len(S)))


def fit_strike(passes=4):
    from koto_fit import pluck, S3
    import tonelib as T
    cls = T.BiwaProperties
    cen = np.sqrt(S3[:-1] * S3[1:])
    if not getattr(cls, "strike_noise_db", ()):
        cls.strike_noise_db = tuple((int(round(c)), -20.0) for c in cen)
    S = strokes(0.1)
    R = [pluck(y, sr, f0, B=float(cls.inharmonicity_coefficient)) for f0, y, sr in S]
    for k in range(passes + 1):
        O = []
        for f0, _, _ in S:
            y, sr = ours(f0)
            O.append(pluck(y, sr, f0, B=float(cls.inharmonicity_coefficient)))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = np.nanmedian(np.array(R) - np.array(O), 0)
        print("  pass %d: bachi takes - ours, rms %.1f dB" % (k, np.sqrt(np.nanmean(d ** 2))), flush=True)
        if k == passes:
            break
        cls.strike_noise_db = tuple((hz, max(-60.0, round(db + (float(dd) if np.isfinite(dd) else 0.0), 1)))
                                    for (hz, db), dd in zip(cls.strike_noise_db, d))
    print("    strike_noise_db = %s" % (cls.strike_noise_db,))


def fit_buzz():
    """--fit=buzz: THE SAWARI as the sitar's (SitarProperties): a prompt fall
    on the partials under prompt_max_hz -- the contact draining the low
    harmonics -- and a quick banded late copy of the top (the bloom, its
    timing the sitar's), sized by a grid on all four measures at once."""
    import itertools
    import tonelib as T
    B = T.BiwaProperties
    S = strokes()
    R = [measure(y, sr, f0) for f0, y, sr in S]
    med = [np.nanmedian([r[k] for r in R], 0) for k in range(4)]
    res = []
    for pd, sh, mx, bg in itertools.product((26.0, 60.0, 113.0), (0.2, 0.45), (976.0, 2000.0), (0.0, 2.5)):
        B.prompt_dbs, B.aftersound_share, B.prompt_max_hz, B.bloom_gain = pd, sh, mx, bg
        O = [measure(*ours(f0), f0) for f0, _, _ in S]
        om = [np.nanmedian([o[k] for o in O], 0) for k in range(4)]
        e = [float(np.sqrt(np.nanmean((om[k] - med[k]) ** 2))) for k in range(4)]
        score = e[0] + e[1] / 3 + e[2] / 3 + e[3] / 2
        res.append((score, pd, sh, mx, bg, e))
        print("  drain %5.1f dB/s share %.2f under %4.0f Hz, top %.1f: fall %.1f harm %.1f between %.1f course %.1f"
              % (pd, sh, mx, bg, *e), flush=True)
    res.sort(key=lambda r: r[0])
    print("  BEST", res[:3])


if __name__ == "__main__":
    if "--fit=buzz" in sys.argv:
        fit_buzz()
    if "--survey" in sys.argv:
        survey()
    elif "--fit=strike" in sys.argv:
        fit_strike()
