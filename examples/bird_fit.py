#!/usr/bin/env python3
"""The bird tweet (GM 123) against three birds: each chirp's pitch contour,
length and spacing. sources.md "Sound effects".

    python3 -I examples/bird_fit.py measure      the chirps, and ours
    python3 -I examples/bird_fit.py ab OUT.wav   each take, then ours

THE TAKES (CC0, Freesound): Profispiesser's house sparrows, close (543827);
Zott820's white-crowned sparrow (695297); qubodup's caged bird (812030).

WHAT THEY HOLD: the sparrows' cheeps 100-140 ms, FALLING ~900-1300 cents
(4.2-6.3 kHz down to 2.3-3.3, a brief lift first), about every half second;
the white-crowned's trill, notes of 50-100 ms falling 150-600 cents, 68-120
ms apart; nearly pure, h2 ~30 dB under the note, h3 ~40. The class had them
rising a major third, each chirp a step higher. Read by eye off the tracks
this prints; the class's values are set from them (tonelib.BirdTweetProperties).
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import upright_fit as U

FS = os.path.expanduser("~/Documents/refs/freesound/birdtweet")


def load(p):
    from scipy.io import wavfile
    import warnings
    warnings.simplefilter("ignore")
    sr, x = wavfile.read(p)
    x = x.astype(np.float64)
    x = x.mean(1) if x.ndim > 1 else x
    return x / np.abs(x).max(), sr


def chirps(x, sr, floor_db=-25.0):
    """[(start s, length s, first Hz, peak Hz, last Hz)]: runs of 4 ms frames
    whose strongest peak (above 1.5 kHz) stands within floor_db of the take's."""
    from scipy.signal import butter, sosfiltfilt
    y = sosfiltfilt(butter(4, 1500, btype="high", fs=sr, output="sos"), x)
    hop, N = int(0.004 * sr), 1024
    f = np.fft.rfftfreq(4096, 1.0 / sr)
    fr, lv = [], []
    for i in range(0, len(y) - N, hop):
        X = np.abs(np.fft.rfft(y[i:i + N] * np.hanning(N), 4096))
        j = int(np.argmax(X))
        fr.append(f[j])
        lv.append(20 * np.log10(X[j] + 1e-12))
    fr, lv = np.array(fr), np.array(lv) - max(lv)
    out, i = [], 0
    while i < len(lv):
        if lv[i] > floor_db:
            j = i
            while j < len(lv) and lv[j] > floor_db:
                j += 1
            if j - i >= 3:
                t = fr[i:j]
                out.append((i * hop / sr, (j - i) * hop / sr, float(t[0]), float(t.max()), float(t[-1])))
            i = j
        else:
            i += 1
    return out


def show(name, cs):
    print("  %s: %d chirps" % (name, len(cs)))
    for t, n, a, p, b in cs[:8]:
        print("    %5.2f s %4.0f ms  %5.0f -> %5.0f -> %5.0f Hz  (%+5.0f / %+5.0f cents)" % (
            t, n * 1e3, a, p, b, 1200 * np.log2(p / a), 1200 * np.log2(b / p)))


def measure():
    for p in sorted(glob.glob(os.path.join(FS, "*.wav"))):
        show(os.path.basename(p)[:40], chirps(*load(p)))
    show("ours (E7)", chirps(*U.render(123, 100, 100, 0.5)))


def ab(out):
    import harpsi_ab as A
    from roomtail import write_wav
    gap = np.zeros(int(0.5 * A.SR))
    parts = []
    for p in sorted(glob.glob(os.path.join(FS, "*.wav"))):
        x, sr = load(p)
        cs = chirps(x, sr)
        if not cs:
            continue
        a = max(0, int((cs[0][0] - 0.05) * sr))
        A.NOTE_S = min(2.5, len(x) / sr - a / sr)
        parts += [A.fit_note(x[a:a + int(A.NOTE_S * sr)], sr), gap]
        y, sr2 = U.render(123, 100, 100, 0.5)
        A.NOTE_S = 0.8
        parts += [A.fit_note(y, sr2), gap, gap]
    z = np.concatenate(parts)
    write_wav(out, np.stack([z, z], 1), A.SR)


def main(argv):
    if argv[1:2] == ["measure"]:
        measure()
    elif argv[1:2] == ["ab"]:
        ab(argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
