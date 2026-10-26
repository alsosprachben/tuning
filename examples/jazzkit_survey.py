"""Survey soneproject's jazz-bar kit (Freesound pack 25895, CC0; sources.md:
jazz_kit_soneproject): per take its length, peak, strikes (onsets), the
lowest strong spectral peak of its first strike (a tom's pitch), the strike's
decay to -30 dB, and its spectral centroid -- to tell which drum each file
group is (the suffix: -5, -6, -9 or none), and which are brushed.

    python3 -I examples/jazzkit_survey.py PREFIX...    (tom crash ride cymb hat)
"""
import glob
import os
import sys
import wave

import numpy as np

WAV = os.path.expanduser("~/Documents/refs/jazz_kit_soneproject/wav/")


def load(p):
    w = wave.open(p)
    sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    y = np.frombuffer(w.readframes(n), np.int16).reshape(-1, ch).mean(1) / 32768.0
    return y, sr


def onsets(y, sr, ms=10, rise_db=12.0):
    """Strike times: a 10 ms frame 12 dB over the one 30 ms before, and
    within 25 dB of the take's loudest."""
    h = int(sr * ms / 1000)
    e = np.array([np.sqrt(np.mean(y[i:i + h] ** 2)) + 1e-9 for i in range(0, len(y) - h, h)])
    db = 20 * np.log10(e)
    top = db.max()
    out = []
    for i in range(3, len(db)):
        if db[i] > top - 25 and db[i] - db[i - 3] > rise_db and (not out or i - out[-1] > 15):
            out.append(i)
    return [i * h / sr for i in out], db, h


def first_strike(y, sr, t0, secs=1.5):
    a = int(t0 * sr)
    return y[a:a + int(secs * sr)]


def low_peak(x, sr, lo=50, hi=1000):
    """The lowest spectral peak within 10 dB of the band's strongest."""
    n = 1 << 16
    s = np.abs(np.fft.rfft(x[: int(0.5 * sr)] * np.hanning(min(len(x), int(0.5 * sr))), n))
    f = np.fft.rfftfreq(n, 1 / sr)
    m = (f >= lo) & (f <= hi)
    db = 20 * np.log10(s[m] + 1e-12)
    ff = f[m]
    top = db.max()
    for i in range(1, len(db) - 1):
        if db[i] > top - 10 and db[i] >= db[i - 1] and db[i] >= db[i + 1]:
            return ff[i]
    return ff[np.argmax(db)]


def decay(x, sr):
    h = int(sr * 0.01)
    e = np.array([np.sqrt(np.mean(x[i:i + h] ** 2)) + 1e-9 for i in range(0, len(x) - h, h)])
    db = 20 * np.log10(e / e.max())
    k = np.argmax(db)
    under = np.nonzero(db[k:] < -30)[0]
    return (under[0] * 0.01) if len(under) else len(db[k:]) * 0.01


def centroid(x, sr):
    s = np.abs(np.fft.rfft(x[: int(0.3 * sr)]))
    f = np.fft.rfftfreq(len(x[: int(0.3 * sr)]), 1 / sr)
    return float((s * f).sum() / (s.sum() + 1e-12))


def main(argv):
    for pre in argv[1:]:
        for p in sorted(glob.glob(WAV + pre + "*.wav")):
            y, sr = load(p)
            ts, _db, _h = onsets(y, sr)
            t0 = ts[0] if ts else 0.0
            x = first_strike(y, sr, max(0.0, t0 - 0.005))
            print("%-18s %5.2f s  peak %6.1f dB  %2d strikes  low peak %5.0f Hz  -30 dB in %4.2f s  centroid %5.0f Hz" % (
                os.path.basename(p)[:-4], len(y) / sr, 20 * np.log10(np.abs(y).max() + 1e-9), len(ts),
                low_peak(x, sr), decay(x, sr), centroid(x, sr)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
