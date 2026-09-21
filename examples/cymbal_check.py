#!/usr/bin/env python3
"""Do a cymbal's modes bend when you hit it harder? Measured: no.

    python3 examples/cymbal_check.py [refdir]

CymbalProperties once carried tension_bend = 0.007 -- about 16 cents of upward
pitch bloom at ff -- citing "+7.8 cents of drift through the ring at ff against
-2.0 at mf, and -24.9 on the hardest-hit take". Three numbers that disagree in
SIGN are not a measurement of an effect, they are an estimator being dragged
around, so this remeasures it properly and the answer is that there is no bend.

THE METHOD, and why it is not the obvious one. A spectral peak estimator is
biased by a decaying amplitude and by neighbouring modes decaying at different
rates, which is exactly the situation on a cymbal -- its modes sit as little as
15 Hz apart. So each partial is isolated with a narrow band and its
INSTANTANEOUS FREQUENCY read from the phase derivative of the analytic signal,
which does not care about the envelope at all. Only partials with nothing else
within 55 Hz above -10 dB are tracked, because a band holding two modes
measures their beat and not their pitch.

AND THE PROBE IS CHECKED FIRST, against bends planted in a synthetic decaying
sinusoid. A probe that cannot see a known 10-cent bend has no business
reporting that a real one is absent.

Wants the Iowa MIS percussion references in ~/Documents/refs (see sources.md
for the filename mapping).
"""
import glob
import math
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

warnings.filterwarnings('ignore')

REFDIR = os.path.expanduser('~/Documents/refs')
BW = 20.0          # +-20 Hz: ~50 ms of smear, against a bend that would settle
                   # over ~280 ms, and narrow enough to hold one mode

# What this script found, recorded so a rerun can be compared against it.
# Medians of the per-partial drift from 60-200 ms to the settled pitch.
FOUND = (("crash / chinese / splash", 96, +0.03),
         ("ride and ride bell", 36, -0.27),
         ("hi-hat", 13, +0.39),
         ("orchestral clash pairs", 58, +0.61))


def load(path):
    """24-bit big-endian AIFF. Reading one as int16 is the trap that once had
    me reporting 68% of a render's energy above 7 kHz."""
    import aifc
    a = aifc.open(path)
    nf, sw, ch, sr = a.getnframes(), a.getsampwidth(), a.getnchannels(), a.getframerate()
    raw = np.frombuffer(a.readframes(nf), dtype=np.uint8).reshape(-1, sw)
    if sw == 3:
        v = ((raw[:, 0].astype(np.int32) << 16) | (raw[:, 1].astype(np.int32) << 8)
             | raw[:, 2].astype(np.int32))
        v = np.where(v >= 1 << 23, v - (1 << 24), v).astype(np.float64) / (1 << 23)
    elif sw == 2:
        v = (raw[:, 0].astype(np.int32) << 8 | raw[:, 1]).astype(np.int32)
        v = np.where(v >= 1 << 15, v - (1 << 16), v).astype(np.float64) / (1 << 15)
    else:
        raise ValueError("unhandled sample width %d" % sw)
    return v.reshape(-1, ch).mean(1), int(sr)


def isolated_partials(x, sr, on, settle=1.5, want=6):
    """Strong partials with nothing near enough to share their band."""
    a, w = on + int(settle * sr), int(settle * sr)
    if a + w > len(x):
        return []
    X = np.abs(np.fft.rfft(x[a:a + w] * np.hanning(w), 1 << 19))
    fr = np.fft.rfftfreq(1 << 19, 1 / sr)
    X[(fr < 250) | (fr > 6000)] = 0
    out, Y = [], X.copy()
    step = int(50 / (fr[1] - fr[0]))
    for _ in range(40):
        k = int(np.argmax(Y))
        if Y[k] <= 0:
            break
        f = fr[k]
        near = (np.abs(fr - f) > BW + 5) & (np.abs(fr - f) < 55)
        if X[near].max() < X[k] * 10 ** (-10 / 20.0):
            out.append(f)
        Y[max(0, k - step):k + step] = 0
        if len(out) >= want:
            break
    return out


def drift(x, sr, on, f0, lo=1.6, hi=3.0):
    """Cents from the attack to the settled pitch, by phase derivative."""
    from scipy.signal import hilbert
    a, b = on - int(0.05 * sr), on + int((hi + 0.2) * sr)
    if a < 0 or b > len(x):
        return None
    seg = x[a:b]
    X = np.fft.rfft(seg)
    fr = np.fft.rfftfreq(len(seg), 1 / sr)
    X[(fr < f0 - BW) | (fr > f0 + BW)] = 0
    f = np.gradient(np.unwrap(np.angle(hilbert(np.fft.irfft(X, len(seg)))))) * sr / (2 * np.pi)
    o = int(0.05 * sr)
    early = np.median(f[o + int(0.06 * sr):o + int(0.20 * sr)])
    late = np.median(f[o + int(lo * sr):o + int(hi * sr)])
    if not (0.9 < early / late < 1.1):
        return None                    # the band lost the partial
    return 1200 * math.log2(early / late)


def control():
    """Plant known bends and see whether the probe returns them."""
    from scipy.signal import hilbert
    sr, f0 = 44100, 1644.9
    print("  planted (at 60-200 ms)      recovered")
    rng = np.random.default_rng(1)
    for tb in (0.0, 0.0092, 0.0046, -0.0092):
        o, n = int(0.05 * sr), int(3.6 * sr)   # long enough for drift()'s settled window
        t = (np.arange(n) - o) / sr
        inst = f0 * (1.0 + tb * np.exp(-np.maximum(t, 0) / 0.28) * (t >= 0))
        seg = (np.where(t >= 0, np.exp(-np.maximum(t, 0) / 3.0), 0.0)
               * np.sin(2 * np.pi * np.cumsum(inst) / sr)
               + 1e-4 * rng.standard_normal(n))
        want = 1200 * math.log2(1 + tb * math.exp(-0.13 / 0.28))
        got = drift(seg, sr, o, f0)
        print("   %+7.4f  (%+6.1f cents)     %+6.2f cents" % (tb, want, got))


def family(pats, label, settle=1.5, lo=1.6, hi=3.0):
    v = []
    for pat in pats:
        for path in sorted(glob.glob(os.path.join(REFDIR, pat))):
            x, sr = load(path)
            on = int(np.argmax(np.abs(x) > 0.05 * np.abs(x).max()))
            for f0 in isolated_partials(x, sr, on, settle):
                d = drift(x, sr, on, f0, lo, hi)
                if d is not None:
                    v.append(d)
    if not v:
        print("   %-26s no trackable partials" % label)
        return
    v = np.array(v)
    print("   %-26s n=%-4d median %+6.2f   mean %+6.2f   10th/90th %+6.1f / %+6.1f"
          % (label, len(v), np.median(v), v.mean(),
             np.percentile(v, 10), np.percentile(v, 90)))


def centroid_drift():
    """What DOES move on a cymbal, and it is not the modes."""
    print("   file                 attack centroid -> settled          in cents")
    for path in sorted(glob.glob(os.path.join(REFDIR, 'cy_1[378]crash.*.aiff'))):
        x, sr = load(path)
        on = int(np.argmax(np.abs(x) > 0.05 * np.abs(x).max()))
        if on + int(3.0 * sr) > len(x):
            continue
        def cen(t0, t1):
            a, b = on + int(t0 * sr), on + int(t1 * sr)
            X = np.abs(np.fft.rfft(x[a:b] * np.hanning(b - a)))
            fr = np.fft.rfftfreq(b - a, 1 / sr)
            m = (fr > 200) & (fr < 12000)
            return float((fr[m] * X[m]).sum() / X[m].sum())
        e, l = cen(0.06, 0.20), cen(1.60, 3.00)
        print("   %-20s %8.0f Hz -> %8.0f Hz     %+9.0f"
              % (os.path.basename(path), e, l, 1200 * math.log2(e / l)))


def main(argv):
    global REFDIR
    if len(argv) > 1:
        REFDIR = argv[1]
    if not glob.glob(os.path.join(REFDIR, 'cy_*.aiff')):
        print("no Iowa cymbal references in %s -- see sources.md" % REFDIR)
        return 1
    print("\n1. THE PROBE, before it is believed about anything")
    print("-" * 52)
    control()

    print("\n2. THE MODES, across the cymbal family")
    print("-" * 52)
    family(('cy_*crash.*.aiff', 'cy_*chinese.*.aiff', 'cy_splash.*.aiff'),
           "crash / chinese / splash")
    family(('cy_ride*.aiff',), "ride and ride bell", 1.0, 1.0, 2.0)
    family(('hh_*.aiff',), "hi-hat", 1.0, 1.0, 2.0)
    family(('oc_*.aiff',), "orchestral clash pairs", 1.0, 1.0, 2.0)
    print("\n   what this script found when it was written:")
    for label, n, med in FOUND:
        print("   %-26s n=%-4d median %+6.2f" % (label, n, med))
    print("   -- all under a cent, where the class once asserted sixteen.")

    print("\n3. WHAT DOES DRIFT, and it is not a nonlinearity")
    print("-" * 52)
    centroid_drift()
    print("   The bright modes die faster than the low ones, so the SPECTRUM")
    print("   falls more than an octave while every partial stands still.")
    print("   harmonic_decay_db already does that; tension_bend never did.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
