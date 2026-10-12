#!/usr/bin/env python3
"""The RELEASE's colour, against the Pitea organ's (GM 19): which harmonics die
first when the key lifts.

    python3 examples/pitea_release.py [--stop=NAME ...]

Ben heard a squeak on the release of some of Pitea's pipes: not louder, but
the low harmonics going before the upper ones. Per stop and key, from its
release samples (relNNNNN: the pipe after a note of NNNNN ms, the key lifting
at the file's start), four courses -- the fundamental, h2-h4, h5-h8, h9 and up
-- in dB re each one's own level over the first 20 ms, and the time each
takes to fall 10 dB. The hall is in the samples, and it is the same hall for
every harmonic, so it lengthens every course alike: what is the pipe's is
the ORDER, and how far a band rises over its own start (a squeak).

Ours: the stop alone, held as long as the sample's note, its release read
from the note-off, dry -- the same measurement.
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
import pitea_fit as P  # noqa: E402

HOP, WIN = 0.005, 0.03
GROUPS = ((1, 1), (2, 4), (5, 8), (9, 24))
NAMES = ("h1", "h2-4", "h5-8", "h9+")


def courses(x, sr, f0, a, secs):
    x = x.mean(1) if x.ndim == 2 else x
    W = int(WIN * sr)
    N = 1 << 15
    fr = np.fft.rfftfreq(N, 1.0 / sr)
    win = np.hanning(W)
    lines = {m: np.abs(fr - m * f0) < max(0.2 * f0, 2 * sr / W) for m in range(1, 25) if m * f0 < 0.45 * sr}
    out = []
    for i in range(int(secs / HOP)):
        s = x[a + int(i * HOP * sr): a + int(i * HOP * sr) + W]
        if len(s) < W:
            break
        P2 = np.abs(np.fft.rfft(s * win, N)) ** 2
        out.append([sum(P2[lines[m]].max() for m in range(lo, hi + 1) if m in lines) + 1e-30
                    for lo, hi in GROUPS])
    c = 10 * np.log10(np.array(out))
    return c - c[:4].mean(0)


def t10(c):
    return [(np.flatnonzero(c[:, j] < -10)[0] * HOP * 1000 if (c[:, j] < -10).any() else np.nan)
            for j in range(c.shape[1])]


def main(argv):
    stops = [a.split("=", 1)[1] for a in argv if a.startswith("--stop=")] or \
        ["principal 8", "octave 4", "flute 8", "reed 8", "reed 16", "reed 4", "trumpet 8"]
    for stop in stops:
        ratio = dict((r[0], r[1]) for r in P.T.FlueOrganProperties.stop_ranks)[stop]
        folder = os.path.join(P.PITEA, P.FOLDER[stop])
        rel = sorted(d for d in os.listdir(folder) if d.startswith("rel"))
        rel = min(rel, key=lambda d: abs(int(d[3:]) - 500))
        held = int(rel[3:]) / 1000.0
        print("== %s (%s, after %d ms): ms to -10 dB %s, and each band's rise over its start" % (
            stop, rel, held * 1000, "/".join(NAMES)), flush=True)
        for key in (48, 60, 72, 84):
            p = glob.glob(os.path.join(folder, rel, "%03d-*.wav" % key))
            if not p:
                continue
            f0 = 440.0 * 2 ** ((key - 69) / 12.0) * ratio
            x, sr = P.read(p[0])
            rc = courses(x, sr, f0, 0, 0.6)
            y, s2 = P.render(stop, key, held)
            oc = courses(y, s2, f0, int(held * s2), 0.6)
            print("  %d  rec %s  rise %s   | ours %s  rise %s" % (
                key, " ".join("%4.0f" % v for v in t10(rc)), " ".join("%+4.1f" % v for v in rc[:40].max(0)),
                " ".join("%4.0f" % v for v in t10(oc)), " ".join("%+4.1f" % v for v in oc[:40].max(0))), flush=True)
    return 0


def hall(y, sr):
    """Ours through PITEA_HALL (pitea_fit.py), as the A/B plays it."""
    import subprocess
    import tempfile
    from scipy.io import wavfile
    y = y.mean(1) if y.ndim == 2 else y
    with tempfile.TemporaryDirectory() as d:
        wavfile.write(os.path.join(d, "a.wav"), sr, (y / max(np.abs(y).max(), 1e-9) * 0.5).astype(np.float32))
        subprocess.run(["sox", os.path.join(d, "a.wav"), "-e", "floating-point", "-b", "32",
                        os.path.join(d, "b.wav")] + P.PITEA_HALL.split(), check=True, stderr=subprocess.DEVNULL)
        z = wavfile.read(os.path.join(d, "b.wav"))[1].astype(np.float64)
    return z.mean(1) if z.ndim == 2 else z


def _ratios(c):
    t = np.array(t10(c))
    return np.log2(t[1:] / t[0])


def fit_release(stops, keys=range(36, 97, 6),
                mus=(0.0, 0.5, 1.0, 1.5), sigmas=(0.0, 0.5, 1.0, 1.5)):
    """--fit=release --stop=...: release_band_mu and release_band_sigma of
    the stops' speech class (tonelib.release_band_scale), against the SPREAD
    of Pitea's release order across the keyboard: per band, the 20th, 50th
    and 80th percentiles of log2(its time to -10 dB / the fundamental's),
    pooled over the stops, ours through the matched hall."""
    import warnings
    warnings.simplefilter("ignore")
    rec, cases = [], []
    for stop in stops:
        row = next(r for r in P.T.FlueOrganProperties.stop_ranks if r[0] == stop)
        folder = os.path.join(P.PITEA, P.FOLDER[stop])
        rel = min((d for d in os.listdir(folder) if d.startswith("rel")), key=lambda d: abs(int(d[3:]) - 500))
        for key in keys:
            p = glob.glob(os.path.join(folder, rel, "%03d-*.wav" % key))
            if p:
                f0 = 440.0 * 2 ** ((key - 69) / 12.0) * row[1]
                x, sr = P.read(p[0])
                rec.append(_ratios(courses(x, sr, f0, 0, 0.8)))
                cases.append((stop, key, f0, int(rel[3:]) / 1000.0))
    Q = (20, 50, 80)
    want = np.nanpercentile(np.array(rec), Q, axis=0)
    print("  Pitea, %d pipes: log2(band / h1) at the 20/50/80th percentile, h2-4 h5-8 h9+:\n%s"
          % (len(rec), want.round(2)), flush=True)
    row = next(r for r in P.T.FlueOrganProperties.stop_ranks if r[0] == stops[0])
    rc = row[3] if len(row) > 3 and isinstance(row[3], type) else None
    cls = rc if rc is not None and (getattr(rc, "rank_speech", False) or getattr(rc, "rank_is_pipe", False)) \
        else P.T.FlueOrganProperties
    best = None
    for mu in mus:
        for sd in sigmas:
            cls.release_band_mu, cls.release_band_sigma = mu, sd
            ours = []
            for stop, key, f0, held in cases:
                y, sr = P.render(stop, key, held)
                ours.append(_ratios(courses(hall(y, sr), sr, f0, int(held * sr), 0.8)))
            got = np.nanpercentile(np.array(ours), Q, axis=0)
            err = float(np.sqrt(np.nanmean((got - want) ** 2)))
            print("  %s mu %.1f sigma %.1f: %.2f octaves rms" % (cls.__name__, mu, sd, err), flush=True)
            if best is None or err < best[0] - 0.01:
                best = (err, mu, sd, got)
    cls.release_band_mu, cls.release_band_sigma = best[1], best[2]
    print("  %s.release_band_mu = %s, release_band_sigma = %s  (%.2f octaves); ours:\n%s"
          % (cls.__name__, best[1], best[2], best[0], best[3].round(2)), flush=True)


if __name__ == "__main__":
    if "--fit=release" in sys.argv:
        fit_release([a.split("=", 1)[1] for a in sys.argv if a.startswith("--stop=")])
        sys.exit(0)
    sys.exit(main(sys.argv))
