#!/usr/bin/env python3
"""How many middle reeds an accordion sounds, and how far apart -- read off a
recording of single held notes.

    python3 -I examples/musette_fit.py [FILE]

An accordion's "wetness" is reeds tuned apart on one key: two (MM, the wet one
some cents sharp) or three (M-, M, M+: the French musette). Each harmonic of the
note is then two or three lines a few Hz apart, beating. A held note of a few
seconds resolves them directly (a long FFT, its bins well under a beat), so this
reads the reeds rather than inferring them from a beat rate: per note and per
harmonic the lines within +-45 cents of h x f0 and more than 26 dB under the
harmonic's strongest are dropped; the rest, in cents from the strongest, are the
reeds. And an octave-down line (a 16' bassoon reed) is looked for under f0.

Used for GS 21.8 "Accordion It" on juskiddink's Paolo Soprani (Castelfidardo;
Freesound 120715, CC BY 4.0; sources.md), as the Hohner was for GM 21.
"""
import os
import sys

import numpy as np

REF = os.path.expanduser("~/Documents/refs/freesound/accordion/120715__juskiddink__accordion-notes.wav")


def notes(x, sr, floor_db=-30.0, min_s=1.0):
    """[(t0, t1)] of the held notes: runs of level within floor_db of the peak."""
    hop = int(0.02 * sr)
    e = np.array([np.sqrt((x[i:i + hop] ** 2).mean()) for i in range(0, len(x) - hop, hop)])
    db = 20 * np.log10(e / e.max() + 1e-12)
    on = db > floor_db
    out = []
    i = 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            if (j - i) * hop / sr >= min_s:
                out.append((i * hop / sr, j * hop / sr))
            i = j
        else:
            i += 1
    return out


def lines(seg, sr, f0, h, N=1 << 20):
    """[(cents from h*f0's strongest line, dB under it)] near harmonic h."""
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    fr = np.fft.rfftfreq(N, 1.0 / sr)
    c = h * f0
    m = np.abs(1200 * np.log2(np.maximum(fr, 1e-6) / c)) < 45
    Xm, fm = X[m], fr[m]
    pk = [k for k in range(1, len(Xm) - 1) if Xm[k] > Xm[k - 1] and Xm[k] >= Xm[k + 1]]
    if not pk:
        return []
    top = max(Xm[k] for k in pk)
    ref = fm[max(pk, key=lambda k: Xm[k])]
    out = []
    for k in pk:
        d = 20 * np.log10(Xm[k] / top)
        if d > -26:
            out.append((1200 * np.log2(fm[k] / ref), d))
    return sorted(out)


def beats(seg, sr, f0, h, lo=0.6, hi=30.0):
    """The beat rates (Hz) in harmonic h's envelope, strongest first, with
    their depth (dB re the envelope's mean): band-pass +-40 cents around
    h x f0, the analytic signal's magnitude, its spectrum over lo..hi Hz. Two
    reeds beat once (at h x their difference); three (M-, M, M+) at the
    difference and twice it."""
    from scipy.signal import butter, sosfiltfilt, hilbert, find_peaks
    c = h * f0
    w = c * (2 ** (40 / 1200.0) - 1)
    if c + w >= 0.45 * sr:
        return []
    sos = butter(4, [c - w, c + w], btype="band", fs=sr, output="sos")
    env = np.abs(hilbert(sosfiltfilt(sos, seg)))
    env = env[int(0.1 * sr):-int(0.1 * sr)]
    e = env - env.mean()
    N = 1 << 20
    E = np.abs(np.fft.rfft(e * np.hanning(len(e)), N)) / (env.mean() * len(e) / 4 + 1e-12)
    fr = np.fft.rfftfreq(N, 1.0 / sr)
    m = (fr >= lo) & (fr <= hi)
    Em, fm = E[m], fr[m]
    pk, _ = find_peaks(Em, distance=max(1, int(0.4 / (fr[1] - fr[0]))))
    pk = sorted(pk, key=lambda k: -Em[k])[:3]
    return [(fm[k], 20 * np.log10(Em[k] + 1e-12)) for k in pk]


def f0_of(seg, sr):
    """The note's pitch: the spacing of its strongest spectral lines (their
    median adjacent gap), refined on the line nearest it. A harmonic-sum
    tracker took the bass notes' strong upper partials for the note."""
    from scipy.signal import find_peaks
    N = 1 << 17
    X = 20 * np.log10(np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) + 1e-9)
    fr = np.fft.rfftfreq(N, 1.0 / sr)
    m = (fr > 60) & (fr < 5000)
    pk, _ = find_peaks(X[m], distance=20, prominence=10)
    top = sorted(sorted(pk, key=lambda k: -X[m][k])[:8])
    fs = fr[m][top]
    if len(fs) < 2:
        return float(fs[0]) if len(fs) else 0.0
    g = np.median(np.diff(fs))
    near = fs[np.argmin(np.abs(fs / g - np.round(fs / g)) + (fs < 0.5 * g))]
    return float(near / max(1, round(near / g)))


def main(path):
    from scipy.io import wavfile
    sr, x = wavfile.read(path)
    x = x.astype(np.float64)
    x = x.mean(1) if x.ndim > 1 else x
    for t0, t1 in notes(x, sr):
        a, b = int((t0 + 0.4) * sr), int((t1 - 0.2) * sr)
        seg = x[a:b]
        f0 = f0_of(seg, sr)
        midi = 69 + 12 * np.log2(f0 / 440.0)
        print("  note %.1f-%.1f s  f0 %.1f Hz (MIDI %.1f), %.1f s analysed" % (t0, t1, f0, midi, (b - a) / sr))
        dfs = []
        for h in range(1, 7):
            bs = beats(seg, sr, f0, h)
            if not bs:
                continue
            b = bs[0][0]
            dfs.append(b / h)
            print("     h%d: beats %s  -> reeds %.2f Hz apart = %.1f cents"
                  % (h, "  ".join("%.2f Hz (%.0f dB)" % q for q in bs), b / h,
                     1200 * np.log2(1 + b / h / f0)))
        if dfs:
            d = np.median(dfs)
            print("     median: %.2f Hz = %.1f cents" % (d, 1200 * np.log2(1 + d / f0)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else REF)
