#!/usr/bin/env python3
"""Fit the telephone ring (GM 124) to bell telephones -- each gong's modes,
the clapper, the ring-out. sources.md "Sound effects".

    python3 -I examples/phone_fit.py modes      each gong's modes off TRP's single strikes
    python3 -I examples/phone_fit.py calibrate  each mode's level to the ringing phones'
    python3 -I examples/phone_fit.py ab OUT.wav  the ringing phones, then ours

THE TAKES (CC0, Freesound): TRP's two gongs of a rotary phone struck one at a
time (616849); a Stromberg-Carlson 1543 (274436) and a Western Electric 500
(456433) ringing with the phone company's cadence. All three carry the same
two gongs, near 1260-1320 and 1590-1610 Hz: the Bell System's pair.

WHAT THEY HOLD: two gongs a major third and a third apart (437 cents), not a
pair a few cents apart; each a dome's modes, ~2.6x, ~4.7x, ~5.2x, ~7.2x the
gong's own note; struck alternately by one clapper, each gong every 50 ms (the
20 Hz ringing current), the other between; ringing on at ~24 dB/s when the
burst stops (11 dB/s struck alone and left).
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import upright_fit as U

FS = os.path.expanduser("~/Documents/refs/freesound/telephone_wav")
TRP = os.path.join(FS, "616849__trp__telephone-bells-two-tones-separated-rotary-dial-phone-2012.wav")
RINGS = (os.path.join(FS, "274436__hockinfinger__stromberg-carlson-1543.wav"),
         os.path.join(FS, "456433__mycompasstv__old-rotary-phone-ringing-western-electric-bell-500-phone.wav"))
# TRP's take: gong A struck at 0 s, gong B at ~7.2 s
STRIKES = (("A", 0.0, 7.0), ("B", 7.2, 16.0))


def load(p):
    from scipy.io import wavfile
    import warnings
    warnings.simplefilter("ignore")
    sr, x = wavfile.read(p)
    x = x.astype(np.float64)
    x = x.mean(1) if x.ndim > 1 else x
    return x / np.abs(x).max(), sr


def gong_modes(x, sr, nmax=8):
    """(Hz, dB re the strongest, band decay dB/s) of a single strike's
    strongest peaks, 0.05-0.35 s after it."""
    from scipy.signal import find_peaks, butter, sosfiltfilt
    t0 = U.onset(x, sr)
    seg = x[t0 + int(0.05 * sr):t0 + int(0.35 * sr)]
    N = 1 << 17
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    ok = (f > 600) & (f < 16000)
    L = 20 * np.log10(X + 1e-12)
    pk, _ = find_peaks(np.where(ok, L, -300), prominence=15, distance=40)
    pk = pk[np.argsort(L[pk])[::-1][:nmax]]
    top = L[pk].max()
    out = []
    for q in sorted(pk, key=lambda q: f[q]):
        fc = f[q]
        y = sosfiltfilt(butter(2, [fc * 0.99, fc * 1.01], btype="band", fs=sr, output="sos"), x[t0:])
        w = int(0.02 * sr)
        e = 10 * np.log10(np.array([np.mean(y[j:j + w] ** 2) for j in range(0, min(len(y), int(3 * sr)) - w, w)]) + 1e-20)
        a = 3
        k = np.flatnonzero(e[a:] < e[a] - 30)
        b = a + (k[0] if len(k) else len(e) - a)
        d = -np.polyfit(np.arange(a, b) * 0.02, e[a:b], 1)[0] if b - a >= 4 else np.nan
        out.append((float(fc), float(L[q] - top), float(d)))
    return out


def modes():
    x, sr = load(TRP)
    for name, a, b in STRIKES:
        seg = x[int(a * sr):int(b * sr)]
        ms = gong_modes(seg, sr)
        f1 = min(ms, key=lambda m: m[0])[0]
        print("  gong %s:" % name)
        for fc, l, d in ms:
            print("    %7.1f Hz  x%5.3f  %+6.1f dB  %5.1f dB/s" % (fc, fc / f1, l, d))


def gong_a(x, sr):
    """Gong A's note in a ringing take: the strongest peak at 1500-1700 Hz."""
    N = 1 << 17
    seg = burst(x, sr)
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    ok = (f > 1500) & (f < 1700)
    return float(f[ok][np.argmax(X[ok])])


def burst(x, sr, secs=1.2):
    """The loudest stretch of a burst: its first SECS from where the ring
    first comes within 10 dB of its loudest."""
    w = int(0.05 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
    i = int(np.flatnonzero(e > 0.3 * e.max())[0])
    return x[i + int(0.2 * sr):i + int((0.2 + secs) * sr)]


def mode_levels(x, sr, fa, ratios):
    """Each mode's peak in a burst, dB re the strongest, the modes found
    within 2% of RATIOS x gong A's note FA (a phone's gongs sit at their own
    pitch)."""
    seg = burst(x, sr)
    N = 1 << 17
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    L = np.array([20 * np.log10(X[np.abs(f - r * fa) < 0.02 * r * fa].max() + 1e-12) for r in ratios])
    return L - L.max()


def calibrate(passes=3):
    """mode_gains toward the ringing phones' mean mode levels in a burst
    (mode_levels), through the renderer; prints the gains."""
    import tonelib as T
    cls = T.TelephoneRingProperties
    R = np.mean([mode_levels(*load(p), gong_a(*load(p)), cls.mode_ratios) for p in RINGS], 0)
    print("  phones (dB re strongest): %s" % " ".join("%+.0f" % v for v in R))
    for it in range(passes + 1):
        y, sr = U.render(124, 92, 100, 2.0)
        fa = 440.0 * 2 ** ((92 - 69) / 12.0)
        O = mode_levels(y, sr, fa, cls.mode_ratios)
        d = R - O
        print("  pass %d: phones - ours %s  rms %.1f dB" % (it, " ".join("%+.0f" % v for v in d), np.sqrt(np.mean(d ** 2))), flush=True)
        if it == passes:
            break
        cls.mode_gains = tuple(round(g * 10 ** (0.8 * v / 20), 4) for g, v in zip(cls.mode_gains, d))
    m = max(cls.mode_gains)
    print("    mode_gains = %s" % (tuple(round(g / m, 4) for g in cls.mode_gains),))


def ab(out, secs=2.0):
    import harpsi_ab as A
    from roomtail import write_wav
    gap = np.zeros(int(0.6 * A.SR))
    parts = []
    for p in RINGS:
        x, sr = load(p)
        w = int(0.05 * sr)
        e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
        on = np.flatnonzero(e > 0.1 * e.max())
        i = on[0]
        A.NOTE_S = secs + 1.0
        parts += [A.fit_note(x[i:i + int((secs + 1.0) * sr)], sr), gap]
        # ours: the note as the burst, at gong A's pitch (the take's)
        y, sr2 = U.render(124, 92, 100, secs)
        parts += [A.fit_note(y, sr2), gap, gap]
    z = np.concatenate(parts)
    write_wav(out, np.stack([z, z], 1), A.SR)


def main(argv):
    if argv[1:2] == ["modes"]:
        modes()
    elif argv[1:2] == ["calibrate"]:
        calibrate()
    elif argv[1:2] == ["ab"]:
        ab(argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
