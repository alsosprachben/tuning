#!/usr/bin/env python3
"""Fit the kalimba (GM 108) to VCSL's Tanzanian mbira (CC0; 27 tines G1-C#6,
~/Documents/refs/vcsl/kalimba/MBira3_*, sources.md).

    kalimba_fit.py                 measure: recorded against ours, per tine
    kalimba_fit.py --ring          the other tines: which ring along, how loud
    kalimba_fit.py --fit           the tine: mode gains, decay law, radiation
    kalimba_fit.py --fit=ring      the ring table's levels, row by row
    kalimba_fit.py --fit=pluck     the thumb: strike noise rows, band by band
    kalimba_fit.py --ab=OUT.wav    each recording, then ours

A TINE IS A CANTILEVER, but what radiates is not its ideal 1 : 6.27 : 17.55.
Measured: the fundamental; an OCTAVE (x2.00, 15-25 dB down in the bass, the
tine against its bridge); the cantilever's second mode at x6.0-6.6 (tapered,
weighted tines), LOUDER than the fundamental at the attack in the bass and
20-55 dB down above -- radiation, not the tine: a 100 Hz fundamental barely
moves air and its 650 Hz mode does. Each decays faster the higher the tine,
about doubling an octave (9 dB/s at 100 Hz, 160 at 1.5 kHz).

AND THE OTHER TINES RING. The same frequencies recur in note after note, 18-45
dB under the plucked one: the instrument's own tines (and their octaves and
cantilever modes), rung through the bridge -- tonelib's ring_db.

The tunings are the instrument's own, up to 50 cents off A440, and VCSL names
each tine an octave below it: the note is the measured pitch's nearest key.
"""
import glob
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import voicefit as V

REFS = os.path.expanduser("~/Documents/refs/vcsl/kalimba")
PROG = 108
VEL = 100
R6 = (5.8, 6.9)          # where the cantilever's second mode is looked for, x f1


def recordings():
    """(key, measured f1, path), lowest first: the key is the measured pitch's
    nearest, the name + 12 the starting guess."""
    out = []
    for p in sorted(glob.glob(os.path.join(REFS, "MBira3_*.wav"))):
        n = V.note_of(p)
        if n is None:
            continue
        x, sr = load(p)
        f1 = tine(x, sr, 440.0 * 2 ** ((n + 12 - 69) / 12.0))["f1"]
        out.append((int(round(69 + 12 * math.log2(f1 / 440.0))), f1, p))
    return sorted(out)


def load(p):
    x, sr = V.mono(p)
    return x.astype(np.float64), sr


def _spec(x, sr, a, b, N=1 << 17):
    i = V.onset(x, sr)
    y = x[i + int(a * sr):i + int(b * sr)]
    return 20 * np.log10(np.abs(np.fft.rfft(y * np.hanning(len(y)), N)) + 1e-12), np.fft.rfftfreq(N, 1.0 / sr)


def tine(x, sr, near):
    """The plucked tine: its pitch, its octave's and its second mode's levels
    re the fundamental (30-130 ms), and the three decays (dB/s, 30-130 ms
    against 330-430 ms)."""
    X1, f = _spec(x, sr, 0.03, 0.13)
    X2, _ = _spec(x, sr, 0.33, 0.43)

    def pk(lo, hi):
        s = (f > lo) & (f < hi)
        k = np.flatnonzero(s)[np.argmax(X1[s])]
        return f[k], X1[k], (X1[k] - X2[k]) / 0.3
    f1, L1, d1 = pk(near / 1.08, near * 1.08)
    _, L2, d2 = pk(2 * f1 / 1.02, 2 * f1 * 1.02)
    f6, L6, d6 = pk(R6[0] * f1, min(R6[1] * f1, 0.45 * sr))
    return dict(f1=f1, h2=L2 - L1, m6=L6 - L1, r6=f6 / f1, d1=d1, d2=d2, d6=d6, L1=L1)


def ring(x, sr, f1, freqs):
    """Each of FREQS (a ring row's frequency): its level re the note's
    fundamental (30-330 ms) and its decay (to 600-900 ms); NaN where the
    row is the note's own mode."""
    X1, f = _spec(x, sr, 0.03, 0.33)
    X2, _ = _spec(x, sr, 0.6, 0.9)
    s = (f > f1 / 1.03) & (f < f1 * 1.03)
    L1 = X1[s].max()
    lv, dc = [], []
    for hz in freqs:
        if any(abs(hz / (f1 * r) - 1.0) < 0.03 for r in (1.0, 2.0)) or hz > 0.45 * sr:
            lv.append(np.nan); dc.append(np.nan)
            continue
        s = (f > hz / 1.01) & (f < hz * 1.01)
        k = np.flatnonzero(s)[np.argmax(X1[s])]
        lv.append(X1[k] - L1)
        dc.append((X1[k] - X2[k]) / 0.57)
    return np.array(lv), np.array(dc)


def use_class():
    import patch_map
    import tonelib
    patch_map.PROGRAM_CLASS[PROG] = tonelib.KalimbaProperties
    return tonelib.KalimbaProperties


def render(key, secs=1.2):
    import mido
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=PROG, time=0))
    t.append(mido.Message("note_on", channel=0, note=key, velocity=VEL, time=0))
    t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(secs * 960)))
    L, R = B.render(m)[:2]
    return 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64)), B.SR


def ours_tine(key):
    y, sr = render(key)
    return tine(y, sr, 440.0 * 2 ** ((key - 69) / 12.0)), (y, sr)


FIELDS = ("h2", "m6", "d1", "d2", "d6")


def report(cls, step=1):
    recs = recordings()[::step]
    print("   key    f1   h2 rec/ours   m6 rec/ours   r6    decay h1 / h2 / m6, rec | ours (dB/s)")
    for key, f1, p in recs:
        x, sr = load(p)
        r = tine(x, sr, f1)
        o, _ = ours_tine(key)
        print("   %3d %6.0f  %+6.1f/%+6.1f  %+6.1f/%+6.1f  %4.2f   %4.0f %4.0f %4.0f | %4.0f %4.0f %4.0f"
              % (key, f1, r["h2"], o["h2"], r["m6"], o["m6"], r["r6"], r["d1"], r["d2"], r["d6"],
                 o["d1"], o["d2"], o["d6"]))


def tine_error(R, O):
    """Levels in dB; decays as 10 log2 of the ratio (an octave off in decay
    costs as much as 10 dB of level)."""
    e = []
    for r, o in zip(R, O):
        e += [o["h2"] - r["h2"], o["m6"] - r["m6"]]
        e += [10.0 * math.log2(max(o[k], 1.0) / max(r[k], 1.0)) for k in ("d1", "d2", "d6")]
    return float(np.sqrt(np.mean(np.square(e))))


def getk(cls, k):
    name, *idx = k.split(".")
    v = getattr(cls, name)
    for i in idx:
        v = v[int(i)]
    return v


def setk(cls, k, q):
    name, *idx = k.split(".")
    if not idx:
        setattr(cls, name, q)
        return

    def put(t, path):
        t = list(t)
        t[path[0]] = q if len(path) == 1 else put(t[path[0]], path[1:])
        return tuple(t)
    setattr(cls, name, put(getattr(cls, name), [int(i) for i in idx]))


# The tine's knobs: the octave's and the second mode's gains, the decay law,
# and the radiation (the box's high-pass, its resonance, its top).
TINE = ("mode_gains.1", "mode_gains.2", "decay_db", "harmonic_decay_db", "decay_register_slope",
        "harmonic_decay_dampening", "bell_cutoff_hz", "bell_order", "formants.0.0", "formants.0.1",
        "formants.0.2")


def fit_tine(cls, step=2, maxfev=200):
    from scipy.optimize import minimize
    recs = recordings()[::step]
    R = []
    for key, f1, p in recs:
        x, sr = load(p)
        R.append(tine(x, sr, f1))
    add = np.array([k in ("harmonic_decay_dampening", "decay_register_slope") for k in TINE])
    x0 = np.array([float(getk(cls, k)) for k in TINE])
    best = [1e9, x0]

    def f(z):
        v = np.where(add, x0 + 0.5 * z, np.exp(z) * x0)
        for k, q in zip(TINE, v):
            setk(cls, k, float(q))
        try:
            O = [ours_tine(key)[0] for key, _, _ in recs]
        except (IndexError, ValueError):
            return 1e3
        e = tine_error(R, O)
        if e < best[0]:
            best[:] = [e, v]
            print("  %6.2f  %s" % (e, " ".join("%s=%.4g" % kv for kv in zip(TINE, v))), flush=True)
        return e
    n = len(TINE)
    simplex = np.vstack([np.zeros(n)] + [0.4 * np.eye(n)[i] for i in range(n)])
    minimize(f, np.zeros(n), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02})
    for k, q in zip(TINE, best[1]):
        setk(cls, k, float(q))
        print("    %s = %.5g" % (k, q))


def fit_ring(cls, passes=3, step=1):
    """The ring table's levels, row by row: each pass adds the median over the
    tines of recorded - ours (dB re the note's fundamental) to every row; the
    decays are measured, as the recordings give them."""
    recs = recordings()[::step]
    freqs = [hz for hz, _, _ in cls.ring_db]
    RL = []
    for key, f1, p in recs:
        x, sr = load(p)
        RL.append(ring(x, sr, f1, freqs)[0])
    RL = np.array(RL)
    import warnings
    for n in range(passes + 1):
        OL = []
        for key, f1, p in recs:
            y, sr = render(key)
            OL.append(ring(y, sr, 440.0 * 2 ** ((key - 69) / 12.0), freqs)[0])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = np.nanmedian(RL - np.array(OL), 0)
        print("  pass %d: ring rows rec - ours, rms %.1f dB" % (n, np.sqrt(np.nanmean(d ** 2))), flush=True)
        if n == passes:
            break
        cls.ring_db = tuple((hz, round(db + (float(dd) if np.isfinite(dd) else 0.0), 1), dps)
                            for (hz, db, dps), dd in zip(cls.ring_db, d))
    print("    ring_db = %s" % (cls.ring_db,))


def survey(min_notes=6):
    """--ring: the peaks that recur across the tines and are not the note's own
    (the ring rows): (Hz, dB re the note's fundamental, decay dB/s), medians."""
    peaks = []
    recs = recordings()
    for key, f1, p in recs:
        x, sr = load(p)
        X1, f = _spec(x, sr, 0.03, 0.33)
        X2, _ = _spec(x, sr, 0.6, 0.9)
        s = (f > f1 / 1.03) & (f < f1 * 1.03)
        L1 = X1[s].max()
        for k in np.flatnonzero((f > 60) & (f < 8000))[1:-1]:
            if X1[k] == X1[max(0, k - 25):k + 25].max() and X1[k] > L1 - 50:
                r = f[k] / f1
                if any(abs(r / q - 1) < 0.03 for q in (1.0, 2.0, 3.0)) or R6[0] < r < R6[1]:
                    continue
                peaks.append((f[k], X1[k] - L1, (X1[k] - X2[k]) / 0.57, p))
    peaks.sort()
    cl = []
    for q in peaks:
        if cl and q[0] / cl[-1][-1][0] < 1.015:
            cl[-1].append(q)
        else:
            cl.append([q])
    rows = []
    for c in cl:
        if len({q[3] for q in c}) >= min_notes:
            rows.append((int(round(np.median([q[0] for q in c]))), round(float(np.median([q[1] for q in c])), 1),
                         round(float(np.median([q[2] for q in c])), 1)))
            print("  %6d Hz  in %2d of %d  %+6.1f dB  %5.1f dB/s" % (rows[-1][0], len({q[3] for q in c}),
                                                                   len(recs), rows[-1][1], rows[-1][2]))
    print("    ring_db = %s" % (tuple(rows),))
    return rows


S3 = 2 ** np.arange(np.log2(140), np.log2(16000), 1 / 3.0)


def start(x, sr):
    """Where the pluck begins: the 1 ms envelope first within 20 dB of its
    peak (argmax is the loudest cycle, a few ms after the thumb)."""
    w = max(1, int(0.001 * sr))
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
    return int(np.flatnonzero(e > e.max() * 0.1)[0])


def pluck(x, sr, f1, freqs, a=0.0, b=0.03):
    """THE THUMB: the first 30 ms between the partials -- third-octave bands,
    every one of the note's own modes (x1, x2, x6.4 and its spread) and every
    ring row masked out, dB re the window's total; and how far that noise has
    fallen by 30-80 ms (dB)."""
    t0 = start(x, sr)
    n = 1 << 15
    f = np.fft.rfftfreq(n, 1.0 / sr)
    near = np.zeros_like(f, bool)
    for r in (1.0, 2.0):
        near |= np.abs(f - r * f1) < max(0.06 * f1, 15.0)
    near |= (f > R6[0] * f1) & (f < R6[1] * f1)
    for hz in freqs:
        near |= np.abs(f - hz) < max(0.02 * hz, 8.0)

    def spec(a_, b_):
        seg = x[t0 + int(a_ * sr):t0 + int(b_ * sr)]
        return np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n)) ** 2 / len(seg)
    X0 = spec(a, b)
    tot = X0.sum()
    out = []
    for lo, hi in zip(S3[:-1], S3[1:]):
        m = (f >= lo) & (f < hi) & ~near
        out.append(10 * np.log10(X0[m].mean() * ((f >= lo) & (f < hi)).sum() / tot + 1e-30) if m.sum() > 3 else np.nan)
    X1 = spec(0.03, 0.08)
    off = ~near & (f > 200) & (f < 12000)
    fall = 10 * np.log10(X1[off].sum() / max(X0[off].sum(), 1e-30) + 1e-30)
    return np.array(out), fall


def fit_pluck(cls, passes=4, step=2):
    """--fit=pluck: strike_noise_db (the thumb on the tine: noise rows a third
    octave apart, tonelib) band by band toward the recordings, the median over
    the tines of recorded - ours; a band neither measures keeps its value."""
    import warnings
    recs = recordings()[::step]
    freqs = [hz for hz, _, _ in cls.ring_db]
    cen = np.sqrt(S3[:-1] * S3[1:])
    if not cls.strike_noise_db:
        cls.strike_noise_db = tuple((int(round(c)), -20.0) for c in cen)
    R, RF = [], []
    for key, f1, p in recs:
        x, sr = load(p)
        b, fl = pluck(x, sr, f1, freqs)
        R.append(b); RF.append(fl)
    for n in range(passes + 1):
        O, OF = [], []
        for key, f1, p in recs:
            y, sr = render(key, 0.6)
            b, fl = pluck(y, sr, 440.0 * 2 ** ((key - 69) / 12.0), freqs)
            O.append(b); OF.append(fl)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = np.nanmedian(np.array(R) - np.array(O), 0)
        print("  pass %d: thumb rec - ours, rms %.1f dB; fall by 30-80 ms rec %.1f ours %.1f dB"
              % (n, np.sqrt(np.nanmean(d ** 2)), np.median(RF), np.median(OF)), flush=True)
        if n == passes:
            break
        cls.strike_noise_db = tuple((hz, round(db + (float(dd) if np.isfinite(dd) else 0.0), 1))
                                    for (hz, db), dd in zip(cls.strike_noise_db, d))
    print("    strike_noise_db = %s" % (cls.strike_noise_db,))


def ab(out, n=7):
    import wave
    from scipy.signal import resample_poly
    recs = recordings()
    pick = [recs[int(i)] for i in np.linspace(0, len(recs) - 1, n)]
    parts, sr = [], 44100
    for key, f1, p in pick:
        x, sr = load(p)
        i = V.onset(x, sr)
        x = x[max(0, i - int(0.01 * sr)):i + int(2.5 * sr)]
        y, sr2 = render(key, 2.5)
        j = V.onset(y, sr2)
        y = y[max(0, j - int(0.01 * sr2)):j + int(2.5 * sr2)]
        if sr2 != sr:
            y = resample_poly(y, sr, sr2)
        y = y * np.sqrt(np.mean(x[:int(0.3 * sr)] ** 2) / np.mean(y[:int(0.3 * sr)] ** 2))
        n_ = min(len(x), len(y))
        x, y = x[:n_], y[:n_]
        fade = np.ones(n_); fade[-int(0.3 * sr):] = np.linspace(1, 0, int(0.3 * sr))
        gap = np.zeros(int(0.35 * sr))
        parts += [x * fade, gap, y * fade, gap, gap]
        print("  %s key %d" % (os.path.basename(p), key))
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


def main(argv):
    cls = use_class()
    if "--ring" in argv:
        return survey() and 0
    if "--fit=pluck" in argv:
        fit_pluck(cls)
        return 0
    if "--fit=ring" in argv:
        fit_ring(cls)
        return 0
    if "--fit" in argv:
        fit_tine(cls)
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--ab=")), None)
    if out:
        return ab(out) or 0
    report(cls)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
