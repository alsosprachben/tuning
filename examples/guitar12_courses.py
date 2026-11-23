#!/usr/bin/env python3
"""The 12-string's COURSES, read off played recordings (no open per-note set):
markiboy123's "12 String Waves" (Freesound 422047, CC0: a melody with chords)
and Vladan Kuzmanovic's "Bravoure for 12 String Guitar" (Commons, CC BY-SA
4.0), in ~/Documents/refs/guitar12_open -- since 2026-11-22, John Magner's
Pianobook takes no longer read (licences.md L7).

  NOTES     each onset (spectral flux) to the next, 0.7 s or longer, kept
            where one harmonic series holds most of the energy (a single
            note, ringing out over what came before): its f0 by a harmonic
            sum over 70-1100 Hz
  COURSES   each harmonic's beating (course_sympathy.courses): the split in
            cents and the partner's level. Below B3 the partner is an OCTAVE
            string on the even harmonics: the even harmonics beat, the odd
            ones hardly; B3 and up a UNISON string on every one
  OCTAVE    below B3, the even harmonics' level over the odd neighbours'
            (dB, the mean of h2 h4 h6 against h1 h3 h5 h7) -- against ours,
            octave_partner_gain is what closes it

    python3 examples/guitar12_courses.py            the takes' notes and ours
"""
import glob
import os
import sys

import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
import course_sympathy as CS  # noqa: E402

REF = os.path.expanduser("~/Documents/refs/guitar12_open")


def load(p):
    from scipy.io import wavfile
    sr, x = wavfile.read(p)
    x = x.astype(np.float64).reshape(len(x), -1).mean(1) / 32768.0
    return sosfiltfilt(butter(4, 40.0, "hp", fs=sr, output="sos"), x), sr


def onsets(x, sr):
    """Spectral-flux onsets (s)."""
    H, W = 512, 2048
    n = (len(x) - W) // H
    win = np.hanning(W)
    prev = None
    flux = np.zeros(n)
    for i in range(n):
        S = np.log1p(100 * np.abs(np.fft.rfft(x[i * H:i * H + W] * win)))
        if prev is not None:
            flux[i] = np.maximum(S - prev, 0).sum()
        prev = S
    flux = flux - np.convolve(flux, np.ones(31) / 31, "same")
    pk, _ = find_peaks(flux, height=np.percentile(flux, 90), distance=int(0.08 * sr / H))
    return (pk * H + W // 2) / sr


def f0_share(x, sr):
    """(f0, share of 60 Hz-6 kHz energy in its harmonics) over a segment."""
    N = 1 << 17
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)), N)) ** 2
    f = np.fft.rfftfreq(N, 1 / sr)
    band = (f > 60) & (f < 6000)
    tot = X[band].sum() + 1e-30
    best = (0.0, 0.0)
    for f0 in 70.0 * 2 ** (np.arange(0, 12 * 4 * 4) / 48.0):
        if f0 > 1100:
            break
        e = 0.0
        for k in range(1, int(6000 / f0) + 1):
            e += X[np.abs(f - k * f0) < max(3.0, 0.006 * k * f0)].sum()
        if e / tot > best[1] * 1.02 or (e / tot > best[1] * 0.98 and f0 < best[0] * 0.6):
            # (a lower f0 nearly as good: its harmonics hold the higher one's)
            best = (f0, e / tot) if e / tot >= best[1] * 0.98 else best
    f0 = CS.f0_of(x, sr, best[0] * 0.98, best[0] * 1.02)
    return f0, best[1]


def notes(min_len=0.5, min_share=0.45):
    out = []
    # (decoded to 16-bit WAV: markiboy_waves.wav, kuzmanovic_bravoure.wav)
    for p in sorted(glob.glob(os.path.join(REF, "*.wav"))):
        x, sr = load(p)
        on = list(onsets(x, sr)) + [len(x) / sr]
        for a, b in zip(on, on[1:]):
            if b - a < min_len:
                continue
            seg = x[int(a * sr):int(min(b, a + 2.0) * sr)]
            f0, sh = f0_share(seg[int(0.05 * sr):], sr)
            if sh >= min_share:
                out.append((os.path.basename(p)[:12], a, b - a, f0, sh, seg, sr))
    return out


def octave_excess(x, sr, f0):
    """Even harmonics over the odd neighbours, dB (h2 h4 h6 vs h1 h3 h5 h7),
    0.1-0.6 s."""
    s = x[int(0.1 * sr):int(0.6 * sr)]
    N = 1 << 17
    X = 20 * np.log10(np.abs(np.fft.rfft(s * np.hanning(len(s)), N)) + 1e-12)
    f = np.fft.rfftfreq(N, 1 / sr)
    L = [X[np.abs(f - k * f0) < max(4.0, 0.01 * k * f0)].max() for k in range(1, 8)]
    return float(np.mean([L[1] - 0.5 * (L[0] + L[2]), L[3] - 0.5 * (L[2] + L[4]), L[5] - 0.5 * (L[4] + L[6])]))


def main(argv):
    N = notes()
    print("%d single notes" % len(N))
    lo, hi = [], []
    for take, a, d, f0, sh, seg, sr in N:
        key = 69 + 12 * np.log2(f0 / 440.0)
        rows = CS.courses(seg, sr, f0, hs=range(1, 9))
        ox = octave_excess(seg, sr, f0)
        tag = "octave" if key < 58.5 else "unison"
        print("  %s %6.2fs %4.2fs  %6.1f Hz (%5.1f) share %.2f  %s  even-odd %+5.1f dB  %s"
              % (take, a, d, f0, key, sh, tag, ox,
                 " ".join("h%d %.1fc %.0f" % r for r in rows)))
        (lo if key < 58.5 else hi).append((f0, ox, rows))
    for name, grp, hs in (("octave courses (below B3), the even harmonics", lo, (2, 4, 6, 8)),
                          ("unison courses (B3 up), every harmonic", hi, range(1, 9))):
        c = [r[1] for _, _, rows in grp for r in rows if r[0] in hs]
        g = [r[2] for _, _, rows in grp for r in rows if r[0] in hs]
        if c:
            print("%s: %d notes, split median %.1f c (IQR %.1f-%.1f), partner median %.1f dB"
                  % (name, len(grp), np.median(c), *np.percentile(c, [25, 75]), np.median(g)))
    if lo:
        print("octave courses: even over odd harmonics, median %+.1f dB" % np.median([o for _, o, _ in lo]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
