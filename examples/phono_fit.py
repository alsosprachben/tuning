#!/usr/bin/env python3
"""A record's surface noise, measured: the reference for GS 124.10 "Phono
Noise" (tonelib.PhonoNoiseProperties).

    python3 examples/phono_fit.py            measure the take, and ours beside it

THE TAKE: nervousneal's "Vinyl Surface Noise 3 blank groove 22 minutes"
(Freesound 586430, CC0; sources.md) -- the unused side of a 1961 MGM test
pressing, stereo, 24-bit, "nothing looped or enhanced"; its first 20 minutes
(the last 28 s are the lock groove).

  hiss      the bed under the clicks: each third-octave band's MEDIAN level
            over 50 ms frames (a click is in few frames), dB re 1 kHz --
            against the RIAA playback curve (time constants 3180, 318, 75 us)
  clicks    an impulse is the 1 ms envelope of the signal's first difference
            standing CLICK_DB over its own running median; per click its peak
            re the bed, its balance (atan of R over L peak, 0 left, 90 right),
            whether the two sides share its polarity; the rate a second, the
            level spread, and the clicks' spectrum (2 ms at each, less the bed)
  together  the bed's correlation between the channels, band by band
  rhythm    the click train's autocorrelation at a revolution (33 1/3: 1.8 s)
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

SRC = os.path.expanduser("~/Documents/refs/freesound/vinyl_blank_groove/"
                         "586430__nervousneal__vinyl-surface-noise-3-blank-groove-22-minutes.wav")
SECS = 1200.0
CLICK_DB = 12.0
BANDS = 50.0 * 2 ** (np.arange(0, 28) / 3.0)            # 50 Hz .. 12.7 kHz


def load(path, secs=SECS):
    """Stereo float32, the first SECS (a float copy beside the scratch: memory-mapped)."""
    from scipy.io import wavfile
    tmp = os.path.join(os.path.dirname(path), "_f32.wav")
    if not os.path.exists(tmp):
        subprocess.run(["sox", path, "-e", "floating-point", "-b", "32", tmp, "trim", "0", str(secs)],
                       check=True)
    sr, x = wavfile.read(tmp, mmap=True)
    return np.asarray(x, np.float32), sr


def riaa_db(f):
    """The RIAA playback response, dB re 1 kHz."""
    def h(f):
        w = 2 * np.pi * np.asarray(f, float)
        t1, t2, t3 = 3180e-6, 318e-6, 75e-6
        return np.abs((1 + 1j * w * t2) / ((1 + 1j * w * t1) * (1 + 1j * w * t3)))
    return 20 * np.log10(h(f) / h(1000.0))


def bed(x, sr, frame=0.05):
    """The median third-octave spectrum over FRAME s frames, dB re 1 kHz; and
    each band's L/R correlation."""
    n = int(frame * sr)
    f = np.fft.rfftfreq(n, 1 / sr)
    edges = [(c * 2 ** (-1 / 6), c * 2 ** (1 / 6)) for c in BANDS]
    idx = [np.flatnonzero((f >= a) & (f < b)) for a, b in edges]
    win = np.hanning(n)
    P, C = [], []
    for i in range(0, len(x) - n, n * 7):                      # every 7th frame: 2.4k frames
        XL = np.fft.rfft(x[i:i + n, 0] * win); XR = np.fft.rfft(x[i:i + n, 1] * win)
        S = 0.5 * (np.abs(XL) ** 2 + np.abs(XR) ** 2)
        P.append([S[k].sum() for k in idx])
        C.append([(np.real(XL[k] * np.conj(XR[k])).sum(), (np.abs(XL[k]) ** 2).sum(), (np.abs(XR[k]) ** 2).sum())
                  for k in idx])
    P = np.array(P); C = np.array(C)
    med = 10 * np.log10(np.median(P, 0) + 1e-30)
    k1 = int(np.argmin(np.abs(BANDS - 1000)))
    corr = C[:, :, 0].sum(0) / np.sqrt(C[:, :, 1].sum(0) * C[:, :, 2].sum(0))
    return med - med[k1], corr


def clicks(x, sr):
    w = int(0.001 * sr)
    d = np.diff(x, axis=0, prepend=x[:1])
    def env(y):
        return np.sqrt(np.convolve(y.astype(np.float64) ** 2, np.ones(w) / w, "same")[::w] + 1e-20)
    eL, eR = env(d[:, 0]), env(d[:, 1])
    eM = np.maximum(eL, eR)
    from scipy.ndimage import median_filter
    base = median_filter(eM, size=501, mode="nearest")
    hi = np.flatnonzero(20 * np.log10(eM / base) > CLICK_DB)
    ev = []
    for j in hi:
        if ev and j - ev[-1][0] <= 3:
            if eM[j] > eM[ev[-1][0]]:
                ev[-1] = (j, ev[-1][1])
            continue
        ev.append((j, base[j]))
    out = []
    for j, b in ev:
        s = slice(max(0, j - 2), j + 3)
        l, r = eL[s].max(), eR[s].max()
        i0 = j * w
        seg = d[max(0, i0 - w):i0 + 2 * w]
        same = float(np.sign(np.sum(seg[:, 0].astype(np.float64) * seg[:, 1])))
        out.append(dict(t=j / 1000.0, db=20 * np.log10(max(l, r) / b), bal=np.degrees(np.arctan2(r, l)), same=same))
    return out


def click_spectrum(x, sr, ev, n=300):
    """The clicks' own spectrum: 5 ms around the loudest N (3 ms after their
    onsets), against as many 5 ms frames of bed between them -- the ratio,
    third-octave from 400 Hz (a 5 ms frame resolves no lower), dB re 1 kHz."""
    m = int(0.005 * sr)
    f = np.fft.rfftfreq(8 * m, 1 / sr)
    edges = [(c * 2 ** (-1 / 6), c * 2 ** (1 / 6)) for c in BANDS]
    idx = [np.flatnonzero((f >= a) & (f < b)) for a, b in edges]
    top = sorted(ev, key=lambda e: -e["db"])[:n]
    win = np.hanning(m)
    def spec(i):
        seg = x[i:i + m].astype(np.float64)
        S = (np.abs(np.fft.rfft(seg[:, 0] * win, 8 * m)) ** 2 + np.abs(np.fft.rfft(seg[:, 1] * win, 8 * m)) ** 2)
        return np.array([S[k].sum() if len(k) else np.nan for k in idx])
    C = np.mean([spec(int(e["t"] * sr) - int(0.002 * sr)) for e in top], 0)
    rng = np.random.default_rng(0)
    B = np.mean([spec(int(rng.uniform(1, len(x) / sr - 1) * sr)) for _ in range(n)], 0)
    d = 10 * np.log10(np.maximum(C - B, 1e-3 * C))
    d[BANDS < 400] = np.nan
    k1 = int(np.argmin(np.abs(BANDS - 1000)))
    return d - d[k1]


def ours(secs=60.0, vel=100):
    """A held, centred Phono Noise note, rendered: stereo float32."""
    import mido
    import blockrender as B
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack(); m.tracks.append(t)
    for x in (mido.Message('control_change', channel=0, control=0, value=10),
              mido.Message('control_change', channel=0, control=32, value=3),
              mido.Message('program_change', channel=0, program=124),
              mido.Message('note_on', channel=0, note=60, velocity=vel, time=240),
              mido.Message('note_off', channel=0, note=60, velocity=0, time=int(secs * 960))):
        t.append(x)
    L, R = B.render(m, "even")[:2]
    s0 = int(1.0 * B.SR)
    return np.stack([np.asarray(L[s0:s0 + int((secs - 1.5) * B.SR)]),
                     np.asarray(R[s0:s0 + int((secs - 1.5) * B.SR)])], 1).astype(np.float32), B.SR


def main(argv):
    if "--ours" in argv:
        x, sr = ours()
        med, corr = bed(x, sr)
        print("  OURS, a held note: %.0f s" % (len(x) / sr))
        print("    Hz     " + " ".join("%6.0f" % c for c in BANDS))
        print("    hiss   " + " ".join("%6.1f" % v for v in med))
        ev = clicks(x, sr)
        dbs = np.array([e["db"] for e in ev])
        print("  clicks: %.1f a second; over the bed 10/25/50/75/90/99%%: %s dB; over 20/30 dB %.2f, %.2f a second"
              % (len(ev) / (len(x) / sr), np.percentile(dbs, [10, 25, 50, 75, 90, 99]).round(1),
                 (dbs > 20).sum() / (len(x) / sr), (dbs > 30).sum() / (len(x) / sr)))
        print("  rms %.1f dB" % (10 * np.log10(np.mean(x.astype(np.float64) ** 2))))
        return 0
    x, sr = load(SRC)
    print("  the take: %.0f s, %d Hz stereo" % (len(x) / sr, sr))
    med, corr = bed(x, sr)
    print("  HISS (median, dB re 1 kHz) against RIAA playback:")
    print("    Hz     " + " ".join("%6.0f" % c for c in BANDS))
    print("    take   " + " ".join("%6.1f" % v for v in med))
    print("    RIAA   " + " ".join("%6.1f" % v for v in riaa_db(BANDS)))
    print("    L/R r  " + " ".join("%6.2f" % v for v in corr))
    ev = clicks(x, sr)
    dbs = np.array([e["db"] for e in ev]); bal = np.array([e["bal"] for e in ev])
    same = np.array([e["same"] for e in ev])
    print("  CLICKS (%.0f dB over the bed): %d in %.0f s, %.1f a second" % (CLICK_DB, len(ev), len(x) / sr, len(ev) / (len(x) / sr)))
    print("    level over the bed, 10/25/50/75/90/99%%: %s dB" % np.percentile(dbs, [10, 25, 50, 75, 90, 99]).round(1))
    print("    rate over 20/30/40 dB: %.2f, %.2f, %.2f a second" % tuple((dbs > q).sum() / (len(x) / sr) for q in (20, 30, 40)))
    print("    balance (0 L, 45 centre, 90 R), 5/25/50/75/95%%: %s" % np.percentile(bal, [5, 25, 50, 75, 95]).round(0))
    print("    the two sides' polarity the same in %.0f%% of clicks" % (100 * (same > 0).mean()))
    cs = click_spectrum(x, sr, ev)
    print("    their spectrum (dB re 1 kHz):")
    print("    take   " + " ".join("%6.1f" % v for v in cs))
    t = np.array([e["t"] for e in ev])
    train = np.zeros(int(len(x) / sr * 100) + 2); train[np.minimum((t * 100).astype(int), len(train) - 1)] = 1.0
    ac = np.correlate(train - train.mean(), train - train.mean(), "full")[len(train) - 1:]
    ac = ac / ac[0]
    for lag_s, nm in ((1.8, "33 1/3 rpm"), (1.333, "45 rpm"), (0.769, "78 rpm")):
        k = int(lag_s * 100)
        print("    click train's autocorrelation at %s (%.2f s): %.3f (around it %.3f)"
              % (nm, lag_s, ac[k - 2:k + 3].max(), np.median(np.abs(ac[k - 40:k + 40]))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
