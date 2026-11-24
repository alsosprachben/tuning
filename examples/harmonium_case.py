#!/usr/bin/env python3
"""THE HARMONIUM'S CASE AND BOX (L10, step 2: Ben, 2026-11-23, "build the
case and box"). The reed simulated (examples/freereed_sim.py) is the reed
heard bare, out of its cell; a harmonium is heard through its cabinet, and
Mustel's back stops sound into a box whose lids stay shut unless a Forte is
drawn (L'Orgue-Expressif, Tome I, pp. 116-120).

THE CALIBRATION: donyaquick's harmonium (Freesound 330410, CC0; our
foundation's own recording -- an instrument, unprocessed): each sustained
note's harmonic levels against our simulated foundation's at the same pitch,
the differences gathered by ABSOLUTE frequency in third octaves -- what that
instrument's case, room and microphone do to the bare reed. The case filter
is fitted to that curve.

    python3 examples/harmonium_case.py --measure     the difference, band by band
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

REF = os.path.expanduser("~/Documents/refs/freesound/harmonium/"
                         "330410__donyaquick__harmonium-samples-all-keys-and-drones.wav")
BANDS = 2.0 ** np.arange(np.log2(100.0), np.log2(12000.0), 1.0 / 3.0)
NH = 40


def ref_notes(min_s=1.2):
    """[(f0, harmonic dB re the strongest)] of the recording's sustained notes."""
    from freesound_slice import onsets, track
    from scipy.io import wavfile
    sr, x = wavfile.read(REF)
    x = x.astype(float)
    x = x.mean(1) if x.ndim > 1 else x
    x /= np.abs(x).max()
    on = onsets(x, sr, rise_db=12.0, top_db=-40.0, gap=0.3) + [len(x)]
    out = []
    for i, j in zip(on[:-1], on[1:]):
        if j - i < min_s * sr:
            continue
        seg = x[i + int(0.5 * sr):i + int(1.1 * sr)]
        T = track(seg, sr, 60, 1500)
        if len(T) < 10:
            continue
        f0 = float(np.median(T[:, 0]))
        if not np.isfinite(f0) or not 100.0 < f0 < 600.0 or np.std(1200 * np.log2(T[:, 0] / f0)) > 15:
            continue
        out.append((f0, harmonics(seg, sr, f0)))
    return out


def harmonics(y, sr, f0, n=NH):
    X = np.abs(np.fft.rfft(y * np.hanning(len(y)), 1 << 18)) ** 2
    fr = np.fft.rfftfreq(1 << 18, 1.0 / sr)
    h = np.full(n, np.nan)
    for k in range(1, n + 1):
        if k * f0 > 0.45 * sr or k * f0 > 12000:
            break
        w = (fr > k * f0 * 0.985) & (fr < k * f0 * 1.015)
        h[k - 1] = X[w].max()
    return 10 * np.log10(h / np.nanmax(h))


def measure(n_sim=8):
    import harmonium_stops as H
    notes = sorted(ref_notes())
    print("  %d sustained notes in the recording, %.0f-%.0f Hz" % (len(notes), notes[0][0], notes[-1][0]))
    pick = [notes[int(i)] for i in np.linspace(0, len(notes) - 1, n_sim)]
    rows = []
    for f0, href in pick:
        y = H.sound(H.FOUNDATION, f0, secs=1.0)
        hsim = harmonics(y[int(0.5 * 48000):], 48000, f0)
        # (each note's level is free: both ladders re their own total power --
        # aligned on h1-h3 the real one's weak fundamental (-11 dB at C4)
        # tilted the whole difference)
        tot = lambda h: 10 * np.log10(np.nansum(10 ** (h / 10)))
        d = (href - tot(href)) - (hsim - tot(hsim))
        rows.append((f0, d))
        print("  %6.1f Hz: ref - ours h1-12 %s" % (f0, " ".join("%4.0f" % v for v in d[:12])), flush=True)
    # gathered by absolute frequency
    out = []
    for lo, hi in zip(BANDS[:-1], BANDS[1:]):
        vals = [d[k] for f0, d in rows for k in range(NH) if lo <= (k + 1) * f0 < hi and np.isfinite(d[k])]
        out.append((np.sqrt(lo * hi), float(np.median(vals)) if len(vals) >= 3 else np.nan, len(vals)))
    print("  band Hz : ref - ours (median dB, n)")
    for c, v, n in out:
        print("   %6.0f : %6.1f  (%d)" % (c, v, n))
    return out


if __name__ == "__main__":
    if "--measure" in sys.argv:
        measure()
