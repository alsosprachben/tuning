#!/usr/bin/env python3
"""Cut a Freesound take of many hits into one file a hit, sorted by drum, for
examples/perc_fit.py to read as it reads VSCO's one-stroke files.

    python3 examples/freesound_slice.py timbales
    python3 examples/freesound_slice.py surdo

TIMBALES: hello_flowers' "50 Timbales Hits" (freesound 41196, CC0; ~/Documents/
refs/sources.md), one 75 s mp3 decoded to float. 53 onsets (a rise of 20 dB in
10 ms, peaking over -30 dB, 0.15 s apart). Read from 20-200 ms, TWO DRUMS, each
at two pitches interleaved through the take: the high drum's lowest mode at
224 or 241 Hz, the low's at 186 or 197, a minor third apart both ways. The
upper pitch of each is the shorter (the high drum -40 dB by 0.22 s against
0.35-0.5): a stroke that presses the head, raising it ~6% and damping it.
The free strokes are taken -- the drum ringing as GM's open timbale does:
high 218-230 Hz (GM 65), low 182-190 (GM 66), the lowest mode within 12 dB of
the hit's strongest peak (an edge stroke that barely moves the head is not
that drum's ring). Each hit runs to the next onset (at most 1.2 s), written
stereo float into
~/Documents/refs/freesound/timbales/hits/{high,low}_<n>.wav.

SURDO: plotzki's "X Surdo 4Bar D" (freesound 36127, CC0), a samba surdo at
67 Hz, 48 kHz mono, four bars of its pattern -- with a second, higher drum
(~120 Hz) answering, left out. Its own strokes are of three kinds, told
apart by the 55-80 Hz band's fall:

  open    left to ring to the next beat (0.55 s): -10 dB at 0.3 s
  first   of a pair, the same ring, cut 0.19 s later by...
  second  ...the muted stroke: it holds -5 dB for 150 ms, then the hand is
          down and it falls 20-45 dB by 0.3 s

Open (GM 87) are the strokes 0.45 s and more from the next; mute (GM 86) the
second of a pair (0.25 s and less after the one before) with 0.3 s to the
next. Every stroke peaks over -25 dB (the take opens on a -32 dB pickup)
and its 55-80 Hz band stays under its first 60 ms' peak from 60 to 150 ms
(one in the fourth bar swells 3 dB there: another stroke on it). Mono, written as a
stereo pair of the same channel into ~/Documents/refs/freesound/surdo/hits/
{open,mute}_<n>.wav.
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))

from drum_fit import read  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs/freesound")


def onsets(x, sr, rise_db=20.0, top_db=-30.0, gap=0.15):
    w = int(0.002 * sr)
    edb = 10 * np.log10(np.convolve(x * x, np.ones(w) / w, "same") + 1e-20)
    lag = int(0.01 * sr)
    out = []
    for i in np.flatnonzero(edb[lag:] - edb[:-lag] > rise_db) + lag:
        if (not out or i - out[-1] > int(gap * sr)) and edb[i:i + lag].max() > top_db:
            out.append(int(i))
    return out


def lowest_mode(x, sr, lo=150.0, hi=300.0):
    """The strongest peak in lo-hi Hz, 20-200 ms after the onset (the head's
    lowest mode), and its level in dB re the strongest peak to 3 kHz."""
    seg = x[int(0.02 * sr):int(0.2 * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 16))
    f = np.fft.rfftfreq(1 << 16, 1.0 / sr)
    b = (f > lo) & (f < hi)
    i = np.argmax(X[b])
    return float(f[b][i]), float(20 * np.log10(X[b][i] / X[(f > lo) & (f < 3000)].max()))


def timbales():
    from scipy.io import wavfile
    src = os.path.join(REFS, "timbales", "41196__hello_flowers__50-timbales-hits.mp3")
    out = os.path.join(REFS, "timbales", "hits")
    os.makedirs(out, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "t.wav")
        subprocess.run(["sox", src, "-e", "floating-point", "-b", "32", wav], check=True,
                       stderr=subprocess.DEVNULL)
        a, sr = read(wav)
    x = a.sum(1)
    on = onsets(x, sr) + [len(x)]
    n = {"high": 0, "low": 0}
    for s, t in zip(on[:-1], on[1:]):
        if t - s < int(0.5 * sr):
            continue                  # a hit cut short by the next
        f1, db = lowest_mode(x[s:], sr)
        drum = "high" if 218 <= f1 <= 230 else "low" if 182 <= f1 <= 190 else None
        if drum is None or db < -12.0:
            continue
        pre = int(0.005 * sr)
        seg = a[max(0, s - pre):s + min(t - s, int(1.2 * sr)) - pre].astype(np.float32)
        n[drum] += 1
        wavfile.write(os.path.join(out, "%s_%02d.wav" % (drum, n[drum])), sr, seg)
        print("%s_%02d  t=%6.2f s  lowest mode %5.1f Hz (%+.0f dB)" % (drum, n[drum], s / sr, f1, db))
    print(n, "->", out)


def surdo():
    from scipy.io import wavfile
    src = os.path.join(REFS, "surdo", "36127__plotzki__x-surdo-4bar-d.aiff")
    out = os.path.join(REFS, "surdo", "hits")
    os.makedirs(out, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "s.wav")
        # padded: the take's first stroke starts in its first sample
        subprocess.run(["sox", src, "-e", "floating-point", "-b", "32", "-c", "2", wav, "pad", "0.05", "0"],
                       check=True, stderr=subprocess.DEVNULL)
        a, sr = read(wav)
    x = a.sum(1)
    on = onsets(x, sr, top_db=-25.0)
    from scipy.signal import butter, sosfiltfilt
    y = sosfiltfilt(butter(2, [55.0, 80.0], btype="band", fs=sr, output="sos"), x)
    w = int(0.005 * sr)
    band = 10 * np.log10(np.convolve(y * y, np.ones(w) / w, "same") + 1e-20)
    n = {"open": 0, "mute": 0}
    for k, s in enumerate(on):
        t = on[k + 1] if k + 1 < len(on) else len(x)
        f1, db = lowest_mode(x[s:], sr, 50.0, 90.0)
        if not 60.0 <= f1 <= 75.0:
            continue                  # the higher drum
        if band[s + int(0.06 * sr):s + int(0.15 * sr)].max() > band[s:s + int(0.06 * sr)].max():
            continue                  # another stroke on it
        if t - s >= int(0.45 * sr):
            kind = "open"
        elif k and s - on[k - 1] <= int(0.25 * sr) and t - s >= int(0.3 * sr):
            kind = "mute"
        else:
            continue                  # the first of a pair, cut short
        pre = int(0.005 * sr)
        seg = a[max(0, s - pre):s + min(t - s, int(1.2 * sr)) - pre].astype(np.float32)
        n[kind] += 1
        wavfile.write(os.path.join(out, "%s_%02d.wav" % (kind, n[kind])), sr, seg)
        print("%s_%02d  t=%6.2f s  %.2f s to the next  lowest mode %5.1f Hz" % (kind, n[kind], s / sr, (t - s) / sr, f1))
    print(n, "->", out)


if __name__ == "__main__":
    {"timbales": timbales, "surdo": surdo}[sys.argv[1]]()
