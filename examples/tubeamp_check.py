#!/usr/bin/env python3
"""What the valve stage actually does, measured rather than asserted.

The amplifier emits partials, so every claim about it is checkable against the
signal the same curve produces per sample. That is the point of this script:
`emit` says "here are the distortion products", and the only honest test is to
add those products up and compare them with the real thing.

Run: python3 examples/tubeamp_check.py
"""
import sys, os, time, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import tubeamp as T

SR = 44100.0
# A Hammond's drawbars are WHEELS of the tempered scale, not harmonics: the
# "third harmonic" is the tempered twelfth at 2.9966 and the "fifth" is 5.0397,
# 13.7 cents sharp. Every measurement below depends on that -- it is why the
# products land on a near-harmonic lattice instead of scattering.
DRAWBAR = [0.5, 1.4983, 1.0, 2.0, 2.9966, 4.0, 5.0397, 5.9932, 8.0]
LEVEL = [0.7, 0.5, 1.0, 0.8, 0.6, 0.4, 0.3, 0.25, 0.2]


def voicing(keys, seed=1):
    rng = np.random.default_rng(seed)
    f, a, p = [], [], []
    for k in keys:
        for r, L in zip(DRAWBAR, LEVEL):
            if k * r < 20.0 or k * r > 18000.0:
                continue
            f.append(k * r); a.append(L); p.append(rng.uniform(0, 2 * np.pi))
    return np.array(f), np.array(a), np.array(p)


def truth(f, a, p, drive, sr=SR, os_=T.OVERSAMPLE, window_s=T.WINDOW_S):
    """The residual the curve really makes, band-limited to Nyquist."""
    n0 = int(round(window_s * sr))
    n = (1 << max(8, int(math.ceil(math.log(n0, 2))))) * os_
    fs = sr * os_
    t = np.arange(n) / fs
    x = (a[:, None] * np.cos(2 * np.pi * f[:, None] * t[None, :]
                             + p[:, None])).sum(axis=0)
    unit = drive * T.BIAS / np.abs(x).max()
    r = (T.curve(x * unit) - T.small_signal() * x * unit) / unit
    r -= r.mean()
    R = np.fft.rfft(r)
    R[int(sr * 0.5 / (fs / n)):] = 0.0          # the analog stage does not alias
    return np.fft.irfft(R, n), t, fs, n


def rebuild(parts, t):
    y = np.zeros(len(t))
    for fq, am, ph in parts:
        y += am * np.cos(2 * np.pi * fq * t + ph)
    return y


def band_err(r, y, n, fs, per_oct=12):
    """Energy error in 1/12-octave bands: is the distortion in the right PLACES.

    The waveform error below is a strict test and has a floor that is nothing
    to do with calibration: a single key's products include pairs 0.374 Hz
    apart, which no window resolves, and two unresolved lines emitted as one
    carry the right energy at the right pitch but not the slow beat between
    them. What a listener has instead of a sample-by-sample match is the
    spectrum, so measure that too.
    """
    R = np.abs(np.fft.rfft(r)) ** 2
    Y = np.abs(np.fft.rfft(y)) ** 2
    k = np.arange(len(R)) * fs / n
    lo, num, den = 20.0, 0.0, 0.0
    step = 2.0 ** (1.0 / per_oct)
    while lo < 20000.0:
        m = (k >= lo) & (k < lo * step)
        if m.any():
            a_, b_ = R[m].sum(), Y[m].sum()
            num += (math.sqrt(a_) - math.sqrt(b_)) ** 2
            den += a_
        lo *= step
    return 100.0 * math.sqrt(num / max(den, 1e-30))


def hdr(s):
    print("\n" + s + "\n" + "-" * len(s))


# ---------------------------------------------------------------- 1. agreement
hdr("1. numerical vs analytic, where the analytic one is right")
print("  At low drive three orders are accurate, so `products` is a true answer")
print("  to compare against -- and its ~2-8% here is what validates the harness.")
print("  `emit` is NOT expected to match it on the waveform: even one key makes")
print("  product pairs 0.374 Hz apart, which no window resolves, and two lines")
print("  emitted as one carry the right energy at the right pitch but not the")
print("  slow beat between them. The band error is the one that matters.")
print("   drive | emit wave | emit band | products wave   (vs the curve's residual)")
f, a, p = voicing([220.0])
for drive in (0.05, 0.1, 0.2, 0.4):
    r, t, fs, n = truth(f, a, p, drive)
    e0 = float((r ** 2).sum())
    en = rebuild(T.emit(f.tolist(), a.tolist(), p.tolist(), SR, drive), t)
    # the analytic path, driven to the SAME peak -- comparing it at its own
    # crest-factor estimate would measure that estimate rather than the series
    n0 = int(round(T.WINDOW_S * SR))
    nn = (1 << max(8, int(math.ceil(math.log(n0, 2))))) * T.OVERSAMPLE
    tt = np.arange(nn) / (SR * T.OVERSAMPLE)
    xx = (a[:, None] * np.cos(2 * np.pi * f[:, None] * tt[None, :]
                              + p[:, None])).sum(axis=0)
    unit = drive * T.BIAS / float(np.abs(xx).max())
    # series() expands the CUTOFF law only and is normalised to c1 == 1, so its
    # products are in units of f/g -- and the curve it expands is the one
    # WITHOUT the ceiling. Compared against the full curve, or without putting
    # the gain back, it measures neither the series nor the stage.
    NC = dict(ceiling=1e12, knee=1.0)
    gnc = T.small_signal(**NC)
    rnc = (T.curve(xx * unit, **NC) - gnc * xx * unit) / unit
    rnc -= rnc.mean()
    cs = T.series()
    an = rebuild([(fq, gnc * am / unit, ph) for fq, am, ph in
                  T.products(f.tolist(), (a * unit).tolist(), p.tolist(), cs,
                             keep=20, floor=1e-12, nyquist=SR * 0.5)], t)
    ee = float(((r - en) ** 2).sum() / e0)
    ae = float(((rnc - an) ** 2).sum() / float((rnc ** 2).sum()))
    be = band_err(r, en, n, fs)
    print(f"   {drive:5.2f} |   {100*math.sqrt(ee):6.1f}%  |   {be:6.1f}%  |   {100*math.sqrt(ae):6.1f}%")

# ---------------------------------------------------------------- 3. the orders
hdr("3. the orders arrive, and push-pull symmetry survives the ceiling")
one = (np.array([220.0]), np.array([1.0]), np.array([0.0]))
for imb, name in ((0.0, "balanced  "), (T.IMBALANCE, "imbalanced")):
    for drive in (1.0, 3.0):
        f1, a1, p1 = one
        n0 = int(round(T.WINDOW_S * SR))
        n = (1 << max(8, int(math.ceil(math.log(n0, 2))))) * T.OVERSAMPLE
        fs = SR * T.OVERSAMPLE
        t = np.arange(n) / fs
        x = np.cos(2 * np.pi * 220.0 * t)
        y = T.curve(x * drive, imbalance=imb)
        Y = np.abs(np.fft.rfft(y * T._window(n)))
        k = np.round(220.0 * n / fs).astype(int)
        h = [float(Y[int(round(220.0 * m * n / fs))]) for m in range(1, 10)]
        h = [20 * math.log10(max(v, 1e-12) / h[0]) for v in h]
        print(f"  {name} drive {drive:3.1f}: " +
              " ".join(f"h{m}={v:6.1f}" for m, v in enumerate(h[1:], 2)) + " dB")

# ----------------------------------------------------------- 4/5. energy, IHD
hdr("4/5. how much of the distortion is emitted, and how much of it is IHD")
print("  'captured' is emitted energy over the curve's real residual energy.")
print("  'IHD' is the share NOT on a harmonic of any sounding note -- the part")
print("  a per-partial harmonic model would miss entirely.")
print("   voicing      drive | captured | wave | band | IHD true | IHD emitted | peaks")
for keys, name in (([220.0], "1 key     "),
                   ([220.0, 277.18, 329.63], "triad     "),
                   ([220.0, 277.18, 329.63, 415.30], "triad+7th ")):
    f, a, p = voicing(keys)
    for drive in (1.0, 3.0):
        r, t, fs, n = truth(f, a, p, drive)
        st = {}
        parts = T.emit(f.tolist(), a.tolist(), p.tolist(), SR, drive, stats=st)
        y = rebuild(parts, t)
        e0 = float((r ** 2).sum())
        cap = float((y ** 2).sum()) / e0
        err = math.sqrt(float(((r - y) ** 2).sum()) / e0)

        def ihd_of(sig_parts):
            tot = sum(am ** 2 for _, am, _ in sig_parts) or 1.0
            har = 0.0
            for fq, am, _ in sig_parts:
                if any(abs(fq - k0 * round(fq / k0)) < 0.03 * k0
                       for k0 in keys if fq > k0 * 0.5):
                    har += am ** 2
            return 100.0 * (1.0 - har / tot)
        # truth's IHD, by notching harmonic neighbourhoods out of its spectrum
        R = np.abs(np.fft.rfft(r * T._window(n))) ** 2
        kk = np.arange(len(R)) * fs / n
        mask = np.zeros(len(R), bool)
        for k0 in keys:
            for m in range(1, int(SR * 0.5 / k0) + 1):
                mask |= np.abs(kk - m * k0) < 8.0
        ihd_t = 100.0 * (1.0 - R[mask].sum() / max(R.sum(), 1e-30))
        be = band_err(r, y, n, fs)
        print(f"   {name} {drive:4.1f} |  {100*cap:5.1f}%  | {100*err:3.0f}% | {be:3.0f}% |"
              f"  {ihd_t:5.1f}%  |    {ihd_of(parts):5.1f}%    | {st['peaks']:4d}")

# ------------------------------------------------------------------- 7. cost
hdr("7. cost")
f, a, p = voicing([220.0, 277.18, 329.63, 415.30])
fc, ac, pc = T.combine(f, a, p)
print(f"  a four-note chord on nine drawbars: {len(f)} partials,"
      f" {len(fc)} distinct frequencies after combine()")
t0 = time.time()
N = 20
for _ in range(N):
    parts = T.emit(f.tolist(), a.tolist(), p.tolist(), SR, 2.0)
dt = (time.time() - t0) / N
print(f"  {dt*1000:.1f} ms per segment, {len(parts)} partials emitted")
print(f"  (fifth order alone over these would be 5,068,131 distinct product")
print(f"   frequencies to enumerate; seventh, far more.)")
