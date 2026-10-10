#!/usr/bin/env python3
"""Measure an upright piano against VSCO-2 Community Edition's (Simon Dalzell /
Ivy Audio's upright, CC0 in VSCO-2 CE; sources.md), and our render the same
way.

    python3 examples/upright_fit.py [--ref=steinway] [--dyn=2] [--program=P] [--class=NAME] [--notes=21,45,...]

Each recorded note is read from its KNOWN key (Keys/Upright Piano/
MappingChart.txt: file index k is key 21 + 2k, the last 108), not from an f0
detector -- voicefit's autocorrelation took several of these for other notes,
and its one-slope-per-partial decay rejected 20 of 23, a piano's partials
beating between strings and falling in two stages. Per note:

  B       inharmonicity: every partial's peak found near n f0 sqrt(1 + B n^2)
          (B refined as it goes), then B and f0 fitted to the peaks
  ladder  partials 1-12, dB re the strongest, 30-130 ms after the onset
  T20/T40 seconds for each octave band to fall 20 and 40 dB from its peak
          (energy in 50 ms windows): the two-stage decay read whole
  level   the loudest 150 ms, dB, per dynamic

--beats compares each partial's level wobble in the decay (the unison's
beating: a phaser, overdone). --fit=decay fits the decay rates and the aftersound to each band's T20.
--fit=register sets the level across the keyboard (register_level_db) to
the recording's, re A4, at mf. --fit=spectrum [--maxfev=N] fits the board and the felt to the ladders
(SPECTRUM, FIT_KEYS, at dynamics 1 and 3); pair it with --class.

and the same for our render of PROGRAM (default 0) at that key, velocity
40/80/120 for dynamics 1/2/3, the note held 6 s. Recordings are 16 s, held.
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))

REFS = os.path.expanduser("~/Documents/refs/vsco2/Keys/Upright Piano")
BANDS = ((63, 125), (125, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 8000))
VEL = {1: 40, 2: 80, 3: 120}
HOLD = 6.0


def key_of(k):
    return 108 if k == 44 else 21 + 2 * k


# THE REFERENCE (--ref=): the upright, or VCSL's Steinway B (CC0, Versilian
# Community Sample Library: "Grand Piano, Steinway B", no pedal, close mics,
# 42 keys a whole tone apart A#0-G#7, layers vl2-vl4). The Steinway's samples
# are NORMALIZED (its NORMALIZED.txt), so its levels -- by key and by layer --
# say nothing: its spectra, decays and inharmonicity do.
REF = ["upright"]
STEINWAY = os.path.expanduser("~/Documents/refs/vcsl/steinway")
STEINWAY_KEYS = (22, 30, 38, 46, 54, 62, 70, 78, 86, 94, 102)


def recordings(dyn):
    if REF[0] == "steinway":
        import glob as _g
        out = {}
        for p in _g.glob(os.path.join(STEINWAY, "JHPiano_NoSus_Close_*_vl%d_rr1.wav" % (dyn + 1))):
            nm = os.path.basename(p).split("_")[3]
            k = (int(nm[-1]) + 1) * 12 + {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[nm[0]] \
                + (1 if "#" in nm else 0)
            out[k] = p
        return out
    out = {}
    for k in range(0, 45, 2):
        p = os.path.join(REFS, "Player_dyn%d_rr1_%03d.wav" % (dyn, k))
        if os.path.exists(p):
            out[key_of(k)] = p
    return out


def load(p):
    from drum_fit import read
    a, sr = read(p)
    a = a.astype(np.float64)
    return a.mean(axis=1) if a.ndim > 1 else a, sr


def onset(x, sr):
    p = x * x
    w = int(0.0005 * sr)
    e = np.convolve(p, np.ones(w) / w, "same")
    return max(0, int(np.flatnonzero(e > 0.01 * e.max())[0]) - int(0.001 * sr))


def spectrum(x, sr, t0, a, b, n=1 << 18):
    seg = x[t0 + int(a * sr):t0 + int(b * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n)) ** 2
    return X, np.fft.rfftfreq(n, 1.0 / sr)


def partials(x, sr, key, nmax=24):
    """[(n, Hz, dB)] found near n f0 sqrt(1 + B n^2), and the fitted (f0, B)."""
    t0 = onset(x, sr)
    X, f = spectrum(x, sr, t0, 0.03, 0.53)
    f0 = 440.0 * 2 ** ((key - 69) / 12.0)
    # the fundamental first, within a semitone (an upright is rarely at 440)
    m = (f > f0 * 0.944) & (f < f0 * 1.059)
    if m.any():
        f0 = float(f[m][np.argmax(X[m])])
    B = 1e-4
    found = []
    for n in range(1, nmax + 1):
        fn = n * f0 * np.sqrt(1 + B * n * n)
        if fn > 0.45 * sr:
            break
        w = 0.25 * f0
        m = (f > fn - w) & (f < fn + w)
        if not m.any():
            continue
        i = np.flatnonzero(m)[np.argmax(X[m])]
        found.append((n, float(f[i]), 10 * np.log10(X[i] + 1e-30)))
        if len(found) >= 4:
            ns = np.array([q[0] for q in found], float)
            fs = np.array([q[1] for q in found])
            # (f_n / n)^2 = f0^2 + f0^2 B n^2: linear in n^2
            c1, c0 = np.polyfit(ns ** 2, (fs / ns) ** 2, 1)
            if c0 > 0:
                f0, B = float(np.sqrt(c0)), float(max(0.0, c1 / c0))
    return found, f0, B


def ladder(found):
    top = max(q[2] for q in found)
    lv = {q[0]: q[2] - top for q in found}
    return [lv.get(n, -99.0) for n in range(1, 13)]


def band_decay(x, sr):
    from scipy.signal import butter, sosfiltfilt
    t0 = onset(x, sr)
    out = []
    w = int(0.05 * sr)
    for lo, hi in BANDS:
        y = sosfiltfilt(butter(4, [lo, hi], btype="band", fs=sr, output="sos"), x[t0:])
        e = 10 * np.log10(np.array([np.mean(y[i:i + w] ** 2) for i in range(0, len(y) - w, w)]) + 1e-30)
        k = int(np.argmax(e))
        t = []
        for d in (20, 40):
            below = np.flatnonzero(e[k:] < e[k] - d)
            t.append((below[0] * 0.05) if len(below) else float("nan"))
        out.append(t)
    return out


def level(x, sr):
    c = np.concatenate(([0.0], np.cumsum(x * x)))
    n = int(0.15 * sr)
    return 10 * np.log10((c[n:] - c[:-n]).max() / n + 1e-30)


def render(program, key, vel, secs=HOLD):
    import mido
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=program, time=0))
    t.append(mido.Message("note_on", channel=0, note=key, velocity=vel, time=0))
    t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(secs * 960)))
    L, R = B.render(m)[:2]
    return 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64)), B.SR


def measure(x, sr, key):
    found, f0, B = partials(x, sr, key)
    return dict(f0=f0, B=B, ladder=ladder(found) if found else [-99.0] * 12,
                decay=band_decay(x, sr), level=level(x, sr))


def use_class(argv, prog):
    """--class=NAME: render PROGRAM through that tonelib class (the upright,
    which no program plays until it is fitted)."""
    cls = next((a.split("=")[1] for a in argv if a.startswith("--class=")), None)
    if cls:
        import patch_map
        import tonelib
        patch_map.PROGRAM_CLASS[prog] = getattr(tonelib, cls)


# THE SPECTRUM FIT (--fit=spectrum): the board and the felt against each
# key's THIRD-OCTAVE spectrum, 30-530 ms, dB re its strongest band, where the
# recording is within 40 dB; at the soft and loud dynamics, so the felt's
# opening with force is fitted too. Nelder-Mead in log space. Fitted to the
# single partials' ladder first, it ran degenerate (the bass roll-off to order
# 16 under a +9 dB body bump at 39 Hz) chasing what one partial does -- a
# strike-point notch, a weak 2nd -- where a band is what is heard.
E3 = 2 ** np.arange(np.log2(45), np.log2(14000), 1 / 3.0)


def thirds(x, sr, key):
    """The bands from the note's own fundamental up, dB re the strongest,
    floored at -50: below the fundamental a recording has only its noise,
    and ours nothing at all (-300 dB), which swamped the first try at 57 dB."""
    t0 = onset(x, sr)
    X, f = spectrum(x, sr, t0, 0.03, 0.53, 1 << 16)
    f0 = 440.0 * 2 ** ((key - 69) / 12.0)
    b = np.array([X[(f >= lo) & (f < hi)].sum() for lo, hi in zip(E3[:-1], E3[1:])])
    b = 10 * np.log10(b + 1e-30)
    b = np.maximum(b - b.max(), -50.0)
    return np.where(E3[1:] > f0 * 0.89, b, np.nan)
# The orders are NOT fitted: free, the fit made the bass roll-off a brick
# wall at 37 Hz (order 27), switched the treble one off (54 kHz) and put all
# the darkening in the felt (1.07 kHz) -- 12.2 -> 9.1 dB by gaming them. The
# board's orders are held at physical values (UprightPianoProperties).
SPECTRUM = ("board_low_hz", "board_high_hz", "hammer_corner_hz", "hammer_order",
            "board_body_hz", "board_body_gain")
FIT_KEYS = (21, 29, 37, 45, 53, 61, 69, 77, 85, 93, 101)
FIT_DYNS = (1, 3)


def fit_spectrum(cls, prog, maxfev):
    from scipy.optimize import minimize
    rec = {}
    for d in FIT_DYNS:
        recs = recordings(d)
        for k in FIT_KEYS:
            x, sr = load(recs[k])
            rec[(d, k)] = thirds(x, sr, k)
    x0 = np.array([float(getattr(cls, p)) for p in SPECTRUM])
    best = [1e9, None]

    def f(z):
        v = np.exp(z) * x0
        for p_, q in zip(SPECTRUM, v):
            setattr(cls, p_, float(q))
        errs = []
        for (d, k), r in rec.items():
            y, sr = render(prog, k, VEL[d], 0.7)
            m = thirds(y, sr, k)
            w = r > -40         # NaN (under the fundamental) compares False
            errs.extend((m - r)[w])
        e = float(np.sqrt(np.mean(np.square(errs))))
        if e < best[0]:
            best[:] = [e, v]
            print("  %6.2f dB  %s" % (e, " ".join("%s=%.4g" % (p_[:14], q) for p_, q in zip(SPECTRUM, v))),
                  flush=True)
        return e
    n = len(SPECTRUM)
    simplex = np.vstack([np.zeros(n)] + [0.5 * np.eye(n)[i] for i in range(n)])
    minimize(f, np.zeros(n), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02})
    return best


def residuals(cls, prog):
    """Ours minus recorded, third-octave bands, mean over each register's
    keys and both fitted dynamics: where the spectrum is still wrong."""
    regs = ((21, 40, "A0-E2"), (41, 60, "F2-C4"), (61, 80, "C#4-G#5"), (81, 108, "A5-C8"))
    acc = {r: [] for r in regs}
    for d in FIT_DYNS:
        recs = recordings(d)
        for k in FIT_KEYS:
            x, sr = load(recs[k])
            r = thirds(x, sr, k)
            y, sr2 = render(prog, k, VEL[d], 0.7)
            m = thirds(y, sr2, k)
            for rg in regs:
                if rg[0] <= k <= rg[1]:
                    acc[rg].append(np.where(r > -40, m - r, np.nan))
    cen = np.sqrt(E3[:-1] * E3[1:])
    print("  residual (ours - recorded, dB) by register; bands: " +
          " ".join("%d" % c for c in cen[::3]))
    for rg, rows in acc.items():
        if not rows:
            continue
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                mean = np.nanmean(np.array(rows), 0)
        print("   %-8s " % rg[2] + " ".join("%+4.0f" % v if np.isfinite(v) else "   ." for v in mean[::3]))


def fit_register(cls, prog, dyn=2, rounds=6):
    """register_level_db: at every recorded key, the recording's level re its
    A4 against ours re our A4, lightly smoothed, damped, added to the class's
    table; six rounds, as the table moves the levels it reads."""
    recs = recordings(dyn)
    keys = sorted(recs)
    rl = {k: level(*load(recs[k])) for k in keys}
    for it in range(rounds + 1):
        ol = {k: level(*render(prog, k, VEL[dyn], 0.7)) for k in keys}
        d = np.array([(rl[k] - rl[69]) - (ol[k] - ol[69]) for k in keys])
        print("  round %d: ours - recorded re A4, rms %.2f dB, worst %+.1f" % (
            it, np.sqrt(np.mean(d ** 2)), -d[np.argmax(np.abs(d))]), flush=True)
        if it == rounds:
            break
        # each key's own correction weighted most: a flat three-key mean slid
        # the corrections between keys and the second fit (after the decay)
        # oscillated, 5.9 -> 5.2 -> 4.5 dB, its worst key swinging +16 to -15
        sm = np.convolve(np.pad(d, 1, mode="edge"), np.array([0.25, 0.5, 0.25]), "valid")
        old = dict(cls.register_level_db)
        hz = [440.0 * 2 ** ((k - 69) / 12.0) for k in keys]
        cur = [cls.register_level_db and np.interp(np.log(h), np.log([p[0] for p in cls.register_level_db]),
                                                   [p[1] for p in cls.register_level_db]) or 0.0 for h in hz]
        # ...and DAMPED: a bass key's level is not linear in its gain (the
        # phantom partials, the strings' nonlinear coupling, grow faster), so a
        # whole correction overshot and one key swung sign every round
        cls.register_level_db = tuple((round(h, 1), round(float(c + 0.6 * x), 2)) for h, c, x in zip(hz, cur, sm))
    print("    register_level_db = (%s)" % ", ".join("(%.1f, %.1f)" % p for p in cls.register_level_db))


# THE DECAY FIT (--fit=decay): each band's time to fall 20 dB (T20), ours
# against the recording, as log ratios, wherever the band holds the note's
# partials (its top above the fundamental) and the recording's reading is
# real (0.1-8 s: ours is held 8 s). Not the room's: the same band's T20 runs
# 0.45-6.7 s across the keys (1-2 kHz), which a room cannot do.
DECAY = ("decay_db", "harmonic_decay_db", "decay_register_slope", "aftersound_level_1",
         "aftersound_level_2", "aftersound_level_3", "aftersound_decay_ratio")
DECAY_HOLD = 8.0
# THE TAIL, TOO: T20 is the first 20 dB, and fitted to it alone the grand's
# treble matched there and then died 10-80 dB too soon (D6 at 2 s: -88 dB re
# its peak against the Steinway's -32 -- Ben: "a little faster decay up high").
LATE_S = (1.0, 2.0)


def late(x, sr):
    """The note's level at LATE_S, dB re its loudest 50 ms in the first 0.2 s."""
    t0 = onset(x, sr)
    w = int(0.05 * sr)
    pk = max(np.mean(x[t0 + i:t0 + i + w] ** 2) for i in range(0, int(0.2 * sr), w // 2))
    return [10 * np.log10(np.mean(x[t0 + int(t * sr):t0 + int(t * sr) + w] ** 2) / pk + 1e-30)
            for t in LATE_S]


def fit_decay(cls, prog, maxfev, dyn=2):
    from scipy.optimize import minimize
    recs = recordings(dyn)
    rec = {}
    for k in FIT_KEYS:
        x, sr = load(recs[k])
        f0 = 440.0 * 2 ** ((k - 69) / 12.0)
        t = np.array([d[0] for d in band_decay(x, sr)])
        ok = np.array([hi > f0 for _, hi in BANDS]) & np.isfinite(t) & (t > 0.1) & (t < DECAY_HOLD)
        rec[k] = (t, ok, late(x, sr))
    x0 = np.array([float(getattr(cls, p)) for p in DECAY])
    best = [1e9, None]

    def f(z):
        v = np.exp(z) * x0
        for p_, q in zip(DECAY, v):
            setattr(cls, p_, float(q))
        errs = []
        for k, (t, ok, lt) in rec.items():
            y, sr = render(prog, k, VEL[dyn], DECAY_HOLD)
            m = np.array([d[0] for d in band_decay(y, sr)])
            m = np.where(np.isfinite(m), m, DECAY_HOLD)
            errs.extend(20 * np.log10(np.maximum(m[ok], 0.05) / t[ok]))
            # ...and the tail after them: the whole note's level at 1 and 2 s
            lm = late(y, sr)
            errs.extend(max(b, -90.0) - a for a, b in zip(lt, lm) if a > -45.0)
        e = float(np.sqrt(np.mean(np.square(errs))))
        if e < best[0]:
            best[:] = [e, v]
            print("  %6.2f dB  %s" % (e, " ".join("%s=%.4g" % (p_[:16], q) for p_, q in zip(DECAY, v))),
                  flush=True)
        return e
    n = len(DECAY)
    simplex = np.vstack([np.zeros(n)] + [0.5 * np.eye(n)[i] for i in range(n)])
    minimize(f, np.zeros(n), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02})
    return best


def beating(x, sr, key, nmax=8, a=0.3, b=3.0):
    """Each partial's level wobble in the decay, a to b s after the onset:
    the partial band-passed around its (inharmonic) frequency, its 10 ms dB
    envelope less a straight line (the decay), and the wobble's spread (dB)
    and main rate (Hz) -- what the unison's beating does to it. [(n, dB, Hz)]"""
    from scipy.signal import butter, sosfiltfilt
    found, f0, B = partials(x, sr, key, nmax)
    t0 = onset(x, sr)
    out = []
    for n, fn, _ in found[:nmax]:
        bw = max(4.0, 0.03 * fn)
        if fn + bw > 0.45 * sr or fn - bw < 20:
            continue
        y = sosfiltfilt(butter(2, [fn - bw, fn + bw], btype="band", fs=sr, output="sos"),
                        x[t0 + int(a * sr):t0 + int(b * sr)])
        w = int(0.01 * sr)
        e = 10 * np.log10(np.array([np.mean(y[i:i + w] ** 2) for i in range(0, len(y) - w, w)]) + 1e-30)
        if len(e) < 20 or e.max() - e.min() > 80:
            continue
        t = np.arange(len(e)) * 0.01
        r = e - np.polyval(np.polyfit(t, e, 1), t)
        spec = np.abs(np.fft.rfft(r * np.hanning(len(r)))) ** 2
        fr = np.fft.rfftfreq(len(r), 0.01)
        out.append((n, float(np.std(r)), float(fr[1 + int(np.argmax(spec[1:]))])))
    return out


# THE STRIKE'S NOISE (--strike): a hammer is not a pluck -- the felt's impact,
# the key bottoming, the board knocked into motion put a thump under the note
# and noise between its partials, and from the tenor up a Steinway's first 30
# ms carry 20-60 dB more of both than our grand did (Ben: "more like a pluck
# than a hammer"). Read here as the spectrum OUTSIDE the partials, in third
# octaves, dB re the whole first 30 ms; and how far it falls by 30-80 ms.
S3 = 2 ** np.arange(np.log2(40), np.log2(14000), 1 / 3.0)
S3C = np.sqrt(S3[:-1] * S3[1:])


def strike_noise(x, sr, key, a=0.0, b=0.03):
    found, f0, B = partials(x, sr, key, 40)
    t0 = onset(x, sr)
    n = 1 << 15
    f = np.fft.rfftfreq(n, 1.0 / sr)
    near = np.zeros_like(f, bool)
    for _, fn, _ in found:
        near |= np.abs(f - fn) < max(0.12 * f0, 15.0)

    def spec(a_, b_):
        seg = x[t0 + int(a_ * sr):t0 + int(b_ * sr)]
        X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n)) ** 2 / len(seg)
        return X
    X0 = spec(a, b)
    tot = X0.sum()
    out = []
    for lo, hi in zip(S3[:-1], S3[1:]):
        m = (f >= lo) & (f < hi) & ~near
        out.append(10 * np.log10(X0[m].mean() * ((f >= lo) & (f < hi)).sum() / tot + 1e-30) if m.any() else np.nan)
    X1 = spec(0.03, 0.08)
    off = ~near & (f > 200) & (f < 12000)
    fall = 10 * np.log10(X1[off].sum() / max(X0[off].sum(), 1e-30) + 1e-30)
    return np.array(out), fall


STRIKE_KEYS = (58, 62, 66, 70, 74, 78, 82, 86, 90, 94)


def fit_strike(cls, prog, passes=3, dyn=2):
    """strike_noise_db and strike_noise_slope to the recordings' strike noise
    (strike_noise) over STRIKE_KEYS, A#3 up (below it the dense partials fill
    the gaps in both), written into tonelib.py each pass."""
    import re as _re
    recs = recordings(dyn)
    keys = [k for k in STRIKE_KEYS if k in recs]
    rec = {k: strike_noise(*load(recs[k]), k)[0] for k in keys}
    path = os.path.join(HERE, "tonelib.py")
    for it in range(passes + 1):
        D = []
        for k in keys:
            o = strike_noise(*render(prog, k, VEL[dyn], 1.0), k)[0]
            D.append(rec[k] - o)
        D = np.array(D)
        ok = np.isfinite(D)
        e = float(np.sqrt(np.mean(D[ok] ** 2)))
        print("  pass %d: strike noise rec - ours, rms %.1f dB" % (it, e), flush=True)
        if it == passes:
            break
        band = np.array([np.nanmean(np.where(ok[:, j], D[:, j], np.nan)) if ok[:, j].any() else 0.0
                         for j in range(D.shape[1])])
        reg = np.log2(np.array([440.0 * 2 ** ((k - 69) / 12.0) for k in keys]) / 440.0)
        km = np.array([np.nanmean(np.where(ok[i], D[i], np.nan) - band) for i in range(len(keys))])
        slope_c = float(np.polyfit(reg, km, 1)[0]) if len(keys) > 2 else 0.0
        old = dict(cls.strike_noise_db)
        new = tuple((int(round(c)), round(float(np.interp(np.log(c), np.log(list(old)), list(old.values()))
                                                  + np.clip(b, -12, 12)), 1))
                    for c, b in zip(S3C, band))
        cls.strike_noise_db = new
        cls.strike_noise_slope = float(cls.strike_noise_slope + 0.7 * slope_c)
        src = open(path).read()
        a = src.index("class %s(" % cls.__name__)
        lines = src[a:].split("\n")
        end = next(j for j, l in enumerate(lines[1:], 1) if l and not l[0].isspace())
        body = "\n".join(lines[:end])
        body = _re.sub(r"^    strike_noise_db = \(.*?\)\)\n", lambda _: "    strike_noise_db = %s\n" % (new,),
                       body, count=1, flags=_re.M | _re.S)
        body = _re.sub(r"^    strike_noise_slope = .*$", lambda _: "    strike_noise_slope = %.3f" % cls.strike_noise_slope,
                       body, count=1, flags=_re.M)
        open(path, "w").write(src[:a] + body + "\n" + "\n".join(lines[end:]))
        for f_ in glob.glob(os.path.join(HERE, "__pycache__", "tonelib.*.pyc")):
            os.remove(f_)
    print("    strike_noise_slope = %.3f" % cls.strike_noise_slope)


def name(key):
    return ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][key % 12] + str(key // 12 - 1)


def main(argv):
    os.environ.setdefault("TUNING_REFLECT", "0")
    os.environ.setdefault("TUNING_MASTER_DB", "-14")
    dyn = int(next((a.split("=")[1] for a in argv if a.startswith("--dyn=")), 2))
    prog = next((int(a.split("=")[1]) for a in argv if a.startswith("--program=")), 0)
    only = next((a.split("=")[1] for a in argv if a.startswith("--notes=")), None)
    if any(a == "--ref=steinway" for a in argv):
        REF[0] = "steinway"
        global FIT_KEYS
        FIT_KEYS = STEINWAY_KEYS
    use_class(argv, prog)
    if "--fit=strike" in argv:
        import patch_map
        fit_strike(patch_map.PROGRAM_CLASS[prog], prog)
        return 0
    if "--strike" in argv:
        recs = recordings(dyn)
        keys = sorted(recs) if not only else [int(k) for k in only.split(",")]
        print("key  strike noise outside the partials, dB re the first 30 ms, by third octave from 40 Hz (every 3rd); its fall by 30-80 ms")
        for key in keys:
            r, rf = strike_noise(*load(recs[key]), key)
            o, of = strike_noise(*render(prog, key, VEL[dyn], 1.0), key)
            print("%-4s rec  %s  fall %5.1f" % (name(key), " ".join("%4.0f" % v if np.isfinite(v) else "   ." for v in r[::3]), rf))
            print("     ours %s  fall %5.1f" % (" ".join("%4.0f" % v if np.isfinite(v) else "   ." for v in o[::3]), of))
        return 0
    if "--beats" in argv:
        recs = recordings(dyn)
        keys = sorted(recs) if not only else [int(k) for k in only.split(",")]
        print("key   partial: wobble dB / rate Hz, recorded | ours  (0.3-3 s)")
        for key in keys:
            x, sr = load(recs[key])
            y, sr2 = render(prog, key, VEL[dyn], 4.0)
            r = {n: (d, f) for n, d, f in beating(x, sr, key)}
            o = {n: (d, f) for n, d, f in beating(y, sr2, key)}
            row = ["%d: %.1f/%.1f | %.1f/%.1f" % (n, r[n][0], r[n][1], o[n][0], o[n][1])
                   for n in sorted(set(r) & set(o))]
            print("%-4s %s" % (name(key), "   ".join(row)))
            ra = np.mean([v[0] for v in r.values()]) if r else 0
            oa = np.mean([v[0] for v in o.values()]) if o else 0
            print("      mean wobble: recorded %.2f dB, ours %.2f dB" % (ra, oa))
        return 0
    if "--fit=decay" in argv:
        import patch_map
        cls = patch_map.PROGRAM_CLASS[prog]
        e, v = fit_decay(cls, prog, int(next((a.split("=")[1] for a in argv
                                              if a.startswith("--maxfev=")), 120)))
        print("  BEST %.2f dB (T20, as 20 log10 of ours / recorded)" % e)
        for p_, q in zip(DECAY, v):
            print("    %s = %.6g" % (p_, q))
        return 0
    if "--fit=register" in argv:
        import patch_map
        fit_register(patch_map.PROGRAM_CLASS[prog], prog)
        return 0
    if "--fit=spectrum" in argv:
        import patch_map
        cls = patch_map.PROGRAM_CLASS[prog]
        e, v = fit_spectrum(cls, prog, int(next((a.split("=")[1] for a in argv
                                                 if a.startswith("--maxfev=")), 200)))
        print("  BEST %.2f dB" % e)
        for p_, q in zip(SPECTRUM, v):
            print("    %s = %.6g" % (p_, q))
            setattr(cls, p_, float(q))
        residuals(cls, prog)
        return 0
    recs = recordings(dyn)
    keys = sorted(recs) if not only else [int(k) for k in only.split(",")]
    print("dynamic %d (our velocity %d), program %d; B x1e4, T20/T40 s per octave band from %d Hz"
          % (dyn, VEL[dyn], prog, BANDS[0][0]))
    for key in keys:
        x, sr = load(recs[key])
        r = measure(x, sr, key)
        y, sr2 = render(prog, key, VEL[dyn])
        m = measure(y, sr2, key)
        print("%-4s rec  f0 %7.2f  B %5.2f  lvl %6.1f  ladder %s" % (
            name(key), r["f0"], r["B"] * 1e4, r["level"], " ".join("%4.0f" % v for v in r["ladder"][:8])))
        print("     ours f0 %7.2f  B %5.2f  lvl %6.1f  ladder %s" % (
            m["f0"], m["B"] * 1e4, m["level"], " ".join("%4.0f" % v for v in m["ladder"][:8])))
        print("     T20  rec %s" % " ".join("%5.2f" % d[0] for d in r["decay"]))
        print("          ours %s" % " ".join("%5.2f" % d[0] for d in m["decay"]))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
