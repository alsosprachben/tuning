#!/usr/bin/env python3
"""GS 66.8 "BreathyTnr.": the tenor saxophone played airy -- the reed barely
closing, the tone darker and the air through it heard -- fitted as a
difference on GM 66 (tonelib.SaxophoneProperties).

    python3 examples/breathy_fit.py            measure the airy note and the plain frames
    python3 examples/breathy_fit.py --fit      the breath and the ladder, through the renderer
    python3 examples/breathy_fit.py --crackle-share   the crackle's spectrum AND level, no detector (the one used)
    python3 examples/breathy_fit.py --crackle-spectrum   the clicks' spectrum: what each adds over the sax, by band
    python3 examples/breathy_fit.py --crackle  the wet reed's clicks: the crackle layer's level, through the renderer
    python3 examples/breathy_fit.py --register OUT.wav  66.8 held C3 to G5: its breath with register (-5 dB an octave up)
    python3 examples/breathy_fit.py --legato OUT.wav  a line on 66.8 slurred, then the same line detached
    python3 examples/breathy_fit.py --ab OUT.wav    the airy take, then ours (66.8) at its pitch; and GM 66

THE TAKES (cemorse100, CC0; sources.md): one tenor playing C5 "soft, airy"
(660042, 4 s) and the same player's ordinary tone in a solo phrase (660699,
4.5 s). Both read the same way, the traverso's (examples/traverso_fit.py):

  frames   0.1 s every 0.05 s, kept where the pitch holds within +-15 cents
           over three 0.033 s parts and the level is within 20 dB of the
           take's loudest; for the phrase, only frames within an octave of C5
  ladder   h1-h12 each its peak, dB re h1
  breath   the spectrum BETWEEN the harmonics (each harmonic +-25% of f0 left
           out), its power by third octave 400 Hz-12.7 kHz, dB re h1's power,
           per Hz of what was kept -- noise density re the note

The airy note re the plain frames, and both re ours (GM 66 at the same
pitch, which has no breath of its own: tonelib breath_noise_db empty).
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

from drum_fit import read  # noqa: E402
import voicefit as V  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs/freesound/tenor_sax_cemorse100")
AIRY = os.path.join(REFS, "660042__cemorse100__airy-sax-c5.wav")
PLAIN = os.path.join(REFS, "660699__cemorse100__cb-sax-phrase.wav")
NH = 12
BANDS = 400.0 * 2 ** (np.arange(0, 16) / 3.0)          # 400 Hz .. 12.7 kHz


def frames(x, sr, near_hz=None):
    w, hop = int(0.1 * sr), int(0.05 * sr)
    rms = np.array([np.sqrt(np.mean(x[i:i + w] ** 2)) for i in range(0, len(x) - w, hop)])
    out = []
    for j, i in enumerate(range(0, len(x) - w, hop)):
        if rms[j] < rms.max() * 0.1:
            continue
        seg = x[i:i + w]
        p = w // 3
        fs = [V.detect_f0(seg[k * p:(k + 1) * p], sr, 90.0, 1400.0) for k in range(3)]
        if any(f is None for f in fs):
            continue
        if np.abs(1200 * np.log2(np.array(fs) / np.median(fs))).max() > 15:
            continue
        f0 = float(np.median(fs))
        if near_hz and abs(np.log2(f0 / near_hz)) > 1.0:
            continue
        out.append(read_frame(seg, sr, f0))
    return out


def read_frame(seg, sr, f0):
    N = 8 * len(seg)
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) ** 2
    f = np.fft.rfftfreq(N, 1 / sr)
    # the harmonic's own peak near the autocorrelation's pitch
    lad = np.array([10 * np.log10(X[(f > f0 * (m - 0.25)) & (f < f0 * (m + 0.25))].max() + 1e-30)
                    for m in range(1, NH + 1)])
    h1 = X[(f > f0 * 0.75) & (f < f0 * 1.25)].sum()
    r = (f / f0) % 1.0
    between = (r > 0.25) & (r < 0.75)
    df = f[1] - f[0]
    br = []
    for c in BANDS:
        m = between & (f >= c * 2 ** (-1 / 6)) & (f < c * 2 ** (1 / 6))
        br.append(10 * np.log10(X[m].sum() / (m.sum() * df) / h1 + 1e-30) if m.sum() > 4 else np.nan)
    return dict(f0=f0, ladder=lad - lad[0], breath=np.array(br))


def summary(fr):
    return (np.median([q["f0"] for q in fr]), np.median([q["ladder"] for q in fr], 0),
            np.nanmedian([q["breath"] for q in fr], 0))


def mono(path):
    x, sr = read(path)
    return x.mean(1), sr


def _render(f0, secs=1.5, bank=0):
    """GM 66 (or 66.BANK, the SC-88 map) at f0 exactly, rendered."""
    from gender_fit import _ours_at
    return _ours_at(66, bank, f0, secs)


def measure(show=True):
    xa, sr = mono(AIRY)
    xp, _ = mono(PLAIN)
    A = frames(xa, sr)
    f0a = summary(A)[0]
    P = frames(xp, sr, near_hz=f0a)
    out = {"airy": summary(A), "plain": summary(P)}
    y, sr2 = _render(f0a)
    O = frames(y[int(0.2 * sr2):], sr2)
    out["ours"] = summary(O)
    if show:
        for k, n in (("airy", len(A)), ("plain", len(P)), ("ours", len(O))):
            f0, lad, br = out[k]
            print("  %-5s %3d frames, %.1f Hz" % (k, n, f0))
            print("        ladder h1-h12 %s" % " ".join("%+4.0f" % v for v in lad))
            print("        breath        %s" % " ".join("%4.0f" % v if np.isfinite(v) else "  --" for v in br))
        print("        bands Hz      %s" % " ".join("%4.1f" % (c / 1000) for c in BANDS))
    return out


def class_ladder(cls, f0):
    pr = cls(f0, 0.0, (100 / 127.0) ** 2, 1.0)
    a = np.array([abs(pr.harmonic_volume(m)) for m in range(1, NH + 1)])
    L = 20 * np.log10(np.maximum(a, 1e-12))
    return L - L[0]


def fit(passes=6):
    """The ladder first, on the class (its harmonic levels at the airy note's
    pitch, h2-h12): tonal_dampening and formant_floor, as AltoSax Exp.'s.
    Then the breath through the renderer: a table at BANDS (and held under
    400 Hz), moved each pass by the airy take's breath less ours, read the
    same way. Prints the class values."""
    from scipy.optimize import minimize
    import patch_map as P
    import tonelib as T
    M = measure(show=False)
    f0, want, breath = M["airy"]
    base = T.SaxophoneProperties
    knobs = ("tonal_dampening", "formant_floor")

    def err(v):
        # the floor at most the formant's own gain: above it, no formant at all
        if not (0.2 < v[0] < 4 and 0.01 < v[1] <= 1.0):
            return 99.0
        return float(np.mean(np.abs(class_ladder(type("F", (base,), dict(zip(knobs, v))), f0)[1:] - want[1:])))
    x0 = np.array([getattr(base, k) for k in knobs])
    r = minimize(err, x0, method="Nelder-Mead", options=dict(xatol=1e-3, fatol=1e-3, maxfev=400))
    lad = dict(zip(knobs, (round(float(v), 3) for v in r.x)))
    print("  ladder: %s  (h2-h12 miss %.2f dB from %.2f)" % (lad, r.fun, err(x0)))
    # a band the measurement cannot read (under the fundamental's skirt)
    # takes its neighbours' level, not a hole
    ok = np.isfinite(breath)
    filled = np.interp(np.log(BANDS), np.log(BANDS[ok]), breath[ok])
    table = {int(round(c)): float(b) + 40.0 for c, b in zip(BANDS, filled)}
    for it in range(passes + 1):
        rows = tuple(sorted([(160, None), (202, None), (255, None), (321, None)] + list(table.items())))
        first = next(v for k, v in rows if v is not None)
        rows = tuple((k, round(v if v is not None else first, 1)) for k, v in rows)
        P.VARIATIONS[(66, 8)] = P.routed_variation(66, "breathyfit%d" % it, breath_noise_db=rows, **lad)
        y, sr = _render(f0, bank=8)
        got = summary(frames(y[int(0.2 * sr):], sr))[2]
        d = breath - got
        ok = np.isfinite(d)
        print("  pass %d: breath, airy - ours by band: %s  (mean |miss| %.2f dB)"
              % (it, " ".join("%+4.0f" % v if np.isfinite(v) else "  --" for v in d), np.mean(np.abs(d[ok]))))
        if it == passes:
            break
        for c, v in zip(BANDS, d):
            if np.isfinite(v):
                table[int(round(c))] += 0.8 * float(np.clip(v, -15, 15))
    print("    %s" % ", ".join("%s=%r" % kv for kv in lad.items()))
    print("    breath_noise_db = %s" % (rows,))


CRACKLE_DB = 9.0         # a click: the 1 ms envelope of the first difference this far over its median


def click_stats(x, sr):
    """phono_fit's clicks, at CRACKLE_DB: (a second, their levels over the bed
    25/50/75/90th percentile), over 0.3 s to the end less 0.3 s."""
    import phono_fit as F
    F.CLICK_DB = CRACKLE_DB
    x = np.asarray(x, np.float32)
    x2 = np.stack([x, x], 1)
    ev = [e for e in F.clicks(x2, sr) if 0.3 < e["t"] < len(x) / sr - 0.3]
    d = np.array([e["db"] for e in ev])
    span = len(x) / sr - 0.6
    return len(ev) / span, (np.percentile(d, [25, 50, 75, 90]) if len(d) else np.full(4, np.nan))


CURVE_DB = (5, 6, 7, 8, 9, 10, 11)


def click_curve(x, sr):
    """Clicks a second over each of CURVE_DB."""
    global CRACKLE_DB
    out = []
    for t in CURVE_DB:
        CRACKLE_DB = float(t)
        out.append(click_stats(x, sr)[0])
    CRACKLE_DB = 9.0
    return np.array(out)


def mean_click(x, sr, thr=7.0):
    """The clicks' MEAN SHAPE in their band (1-5 kHz): every click over THR
    aligned on its envelope's peak, the excess power over the band's bed
    averaged -2..+8 ms -- (clicks, width at half and at a tenth of the peak,
    ms; the peak over the bed, dB). A count cannot tell a click's length (Ben
    heard ours "quieter and shorter" in the take with the counts matched),
    and one click's width read near the bed is the bed's ripple."""
    import phono_fit as F
    from scipy.signal import butter, sosfiltfilt
    F.CLICK_DB = thr
    x = np.asarray(x, np.float64)
    ev = [e for e in F.clicks(np.stack([x, x], 1).astype(np.float32), sr) if 0.3 < e["t"] < len(x) / sr - 0.3]
    y = sosfiltfilt(butter(4, [1000, 5000], btype="band", fs=sr, output="sos"), x)
    w = max(1, int(0.0001 * sr))
    pw = np.convolve(y ** 2, np.ones(w) / w, "same")
    bed = np.median(pw)
    acc = []
    for e in ev:
        c = int(e["t"] * sr)
        k = c - int(0.004 * sr) + int(np.argmax(pw[c - int(0.004 * sr):c + int(0.006 * sr)]))
        acc.append(pw[k - int(0.002 * sr):k + int(0.008 * sr)] - bed)
    m = np.mean(acc, 0)
    pk = m.max()
    return len(ev), np.sum(m > pk / 2) / sr * 1000, np.sum(m > pk / 10) / sr * 1000, 10 * np.log10((pk + bed) / bed)


EXCESS_BANDS = 250.0 * 2 ** (np.arange(0, 19) / 3.0)


def click_excess(x, sr, thr=7.0, f0=None):
    """What each click ADDS, by third octave, BETWEEN THE HARMONICS: an 8 ms
    window on it (the one within +-2 ms holding most power over 2 kHz) less
    the mean of 8 ms windows 10 and 18 ms before it, averaged over the clicks
    over THR, every bin within a quarter of f0 of a harmonic left out (Ben:
    "are you picking up the tone in the crackle fit?" -- a 2 ms window's 500
    Hz bins could not tell a click from the note's own harmonics wavering
    under it: the take's clicks read strongest at 1.6-2.5 kHz, its 3rd and
    4th); dB re the bed's own power there (NaN where it adds nothing)."""
    import phono_fit as F
    F.CLICK_DB = thr
    x = np.asarray(x, np.float64)
    ev = [e for e in F.clicks(np.stack([x, x], 1).astype(np.float32), sr) if 0.3 < e["t"] < len(x) / sr - 0.3]
    n, N = int(0.008 * sr), 4096
    f = np.fft.rfftfreq(N, 1 / sr)
    win = np.hanning(n)
    between = np.ones(len(f), bool) if not f0 else (np.abs(f / f0 - np.round(f / f0)) > 0.25)

    def spec(a):
        return np.abs(np.fft.rfft(x[a:a + n] * win, N)) ** 2
    idx = [np.flatnonzero((f >= c * 2 ** (-1 / 6)) & (f < c * 2 ** (1 / 6)) & between) for c in EXCESS_BANDS]
    E, Bd = [], []
    for e in ev:
        c = int(e["t"] * sr) - n // 2
        a = max(range(c - int(0.002 * sr), c + int(0.002 * sr), int(0.0005 * sr)),
                key=lambda q: spec(q)[f > 2000].sum())
        on = spec(a)
        bed = 0.5 * (spec(a - int(0.010 * sr)) + spec(a - int(0.018 * sr)))
        E.append([on[i].sum() - bed[i].sum() if len(i) else 0.0 for i in idx])
        Bd.append([bed[i].sum() if len(i) else 1.0 for i in idx])
    if not E:
        return np.full(len(EXCESS_BANDS), np.nan)
    E, Bd = np.mean(E, 0), np.mean(Bd, 0)
    return np.where(E > 0, 10 * np.log10(np.maximum(E, 1e-30) / Bd), np.nan)


def crackle_share(x, sr, f0):
    """THE CRACKLE'S SHARE, no detector: over the whole note, 8 ms frames
    every 2 ms, each band's power BETWEEN THE HARMONICS (a quarter of f0
    round each left out); the median frame is the steady breath, the mean's
    excess over it the impulsive part -- dB of (mean - median) re the median,
    by band. A count or a per-click average only sees the clicks the
    detector finds, and moved with the level the wrong way (a quieter layer
    leaves the detector its loudest clicks)."""
    x = np.asarray(x, np.float64)
    n, N = int(0.008 * sr), 4096
    f = np.fft.rfftfreq(N, 1 / sr)
    win = np.hanning(n)
    between = np.abs(f / f0 - np.round(f / f0)) > 0.25
    idx = [np.flatnonzero((f >= c * 2 ** (-1 / 6)) & (f < c * 2 ** (1 / 6)) & between) for c in EXCESS_BANDS]
    P = np.array([[(np.abs(np.fft.rfft(x[a:a + n] * win, N)) ** 2)[i].sum() if len(i) else np.nan for i in idx]
                  for a in range(int(0.3 * sr), len(x) - int(0.3 * sr) - n, int(0.002 * sr))])
    med, mean = np.nanmedian(P, 0), np.nanmean(P, 0)
    return np.where(mean > med, 10 * np.log10(np.maximum(mean - med, 1e-30) / med), np.nan)


SPECTRUM_THR = 6.0


def crackle_spectrum(passes=4):
    """THE CLICK'S SPECTRUM, what it adds over the sax (click_excess), take
    against ours through the renderer: the table moved by the difference
    band by band. Under the band where the take adds nothing at all -- ~1
    kHz: the reed's own low partials take a disturbance there into its
    oscillation (Ben: "the lower parts of the reed are phase-locking out the
    bottom end of the clicks") -- the table 12 dB under its top there and
    falling 48 dB an octave (24 left ours adding at 794 Hz). Prints the
    table; then --crackle sets the level."""
    import tonelib as T
    import patch_map as P
    xa, sr = mono(AIRY)
    f0 = summary(frames(xa, sr))[0]
    want = click_excess(xa, sr, SPECTRUM_THR, f0)
    floor = EXCESS_BANDS[np.flatnonzero(np.isfinite(want))[0]]
    print("  band Hz  " + " ".join("%5.0f" % c for c in EXCESS_BANDS))
    print("  take     " + " ".join("%5.1f" % v if np.isfinite(v) else "   --" for v in want))
    cls = T.ReedCrackleProperties
    for it in range(passes + 1):
        P._LAYER_CLASSES.clear()
        y, sr2 = _render(f0, secs=4.0, bank=8)
        got = click_excess(y[int(0.1 * sr2):], sr2, SPECTRUM_THR, f0)
        # THE SHAPE ONLY: each curve less its mean over the bands both hold
        # (the level is --crackle's: moving it here slid the clicks under the
        # detector); where ours adds and the take does not, ours is over
        both = np.isfinite(want) & np.isfinite(got)
        if not both.any():
            print("  pass %d: no clicks" % it)
            break
        d = (want - np.nanmean(want[both])) - (got - np.nanmean(got[both]))
        d = np.where(np.isfinite(got) & ~np.isfinite(want), -12.0, d)
        ok = np.isfinite(d)
        print("  pass %d   " % it + " ".join("%5.1f" % v if np.isfinite(v) else "   --" for v in got)
              + "   shape miss %.2f dB" % np.mean(np.abs(d[ok])), flush=True)
        if it == passes:
            break
        tab = []
        for c, v in cls.strike_noise_db:
            k = int(np.argmin(np.abs(np.log2(EXCESS_BANDS / c))))
            if c < floor * 2 ** (-1 / 6):
                v = cls_top(cls) - 12.0 - 48.0 * np.log2(floor / c)
            elif np.isfinite(d[k]):
                v = v + 0.8 * float(np.clip(d[k], -10, 10))
            tab.append((c, float(v)))
        # the burst's POWER held (a top held lost the clicks under the detector)
        p0 = 10 * np.log10(sum(10 ** (v / 10.0) for _, v in cls.strike_noise_db))
        p1 = 10 * np.log10(sum(10 ** (v / 10.0) for _, v in tab))
        cls.strike_noise_db = tuple((c, round(v - p1 + p0, 1)) for c, v in tab)
    print("    strike_noise_db = %s" % (cls.strike_noise_db,))


def crackle_share_fit(passes=6, db=-6.0):
    """THE CRACKLE, SPECTRUM AND LEVEL TOGETHER, by crackle_share (no
    detector): the table's rows moved by the take's share less ours, band by
    band over 0.9-11 kHz, and the layer's level by their mean over 1.2-5
    kHz. Under ~1 kHz the take holds no crackle at all: the rows there stay
    cut. Prints the table and BREATHY_CRACKLE_DB."""
    import tonelib as T
    import patch_map as P
    cls = T.ReedCrackleProperties
    xa, sr = mono(AIRY)
    f0 = summary(frames(xa, sr))[0]
    want = crackle_share(xa, sr, f0)
    mid = (EXCESS_BANDS >= 1200) & (EXCESS_BANDS <= 5200)
    fit_b = (EXCESS_BANDS >= 900) & (EXCESS_BANDS <= 11000)
    print("  band Hz  " + " ".join("%5.0f" % c for c in EXCESS_BANDS))
    print("  take     " + " ".join("%5.1f" % v if np.isfinite(v) else "   --" for v in want))
    best = None
    for it in range(passes + 1):
        P.LAYERED[(66, 8)] = (P.LAYERED[(66, 8)][0], (P.LAYERED[(66, 8)][1][0], 0, db))
        P._LAYER_CLASSES.clear()
        y, sr2 = _render(f0, secs=4.0, bank=8)
        got = crackle_share(y[int(0.1 * sr2):], sr2, f0)
        d = want - got
        ok = fit_b & np.isfinite(d)
        if not (mid & np.isfinite(d)).any():
            # no crackle shows over the breath at all: louder, and again
            print("  %+5.1f dB  no crackle over the breath" % db, flush=True)
            db += 6.0
            continue
        miss = float(np.mean(np.abs(d[ok])))
        lev = float(np.mean(d[mid & np.isfinite(d)]))
        print("  %+5.1f dB " % db + " ".join("%5.1f" % v if np.isfinite(v) else "   --" for v in got)
              + "   miss %.2f, level %+.1f" % (miss, lev), flush=True)
        if best is None or miss < best[0]:
            best = (miss, cls.strike_noise_db, db)
        if it == passes:
            break
        db += 0.8 * lev
        tab = []
        for c, v in cls.strike_noise_db:
            k = int(np.argmin(np.abs(np.log2(EXCESS_BANDS / c))))
            if fit_b[k] and np.isfinite(d[k]):
                v = v + 0.7 * float(np.clip(d[k] - lev, -8, 8))
            tab.append((c, round(float(v), 1)))
        cls.strike_noise_db = tuple(tab)
    miss, cls.strike_noise_db, db = best
    print("  best: miss %.2f" % miss)
    print("    strike_noise_db = %s" % (cls.strike_noise_db,))
    print("    BREATHY_CRACKLE_DB = %.2f" % db)


def cls_top(cls):
    return max(v for c, v in cls.strike_noise_db)


def crackle():
    """The crackle layer's level (patch_map.BREATHY_CRACKLE_DB): the take's
    clicks counted over 5-11 dB (click_curve), ours the same through the
    renderer, the level scanned for the least miss in log count (the class
    sets the rate and the levels' exponential scale). Ours without the layer
    holds none at any of them: every click the take shows is the crackle."""
    import patch_map as P
    xa, sr = mono(AIRY)
    want = click_curve(xa, sr)
    f0 = summary(frames(xa, sr))[0]
    print("  over dB    " + " ".join("%5d" % t for t in CURVE_DB))
    print("  take       " + " ".join("%5.1f" % v for v in want))

    def at(db):
        P.LAYERED[(66, 8)] = (P.LAYERED[(66, 8)][0], (P.LAYERED[(66, 8)][1][0], 0, db))
        y, sr2 = _render(f0, secs=4.0, bank=8)
        got = click_curve(y[int(0.1 * sr2):], sr2)
        miss = float(np.mean(np.abs(np.log((got + 0.1) / (want + 0.1)))))
        print("  %+5.1f dB   " % db + " ".join("%5.1f" % v for v in got) + "   miss %.2f (log)" % miss, flush=True)
        return miss
    best = min((at(db), db) for db in np.arange(-24.0, -5.0, 3.0))
    fine = min((at(db), db) for db in (best[1] - 1.5, best[1] - 0.75, best[1] + 0.75, best[1] + 1.5))
    best = min(best, fine)
    print("    BREATHY_CRACKLE_DB = %.2f" % best[1])
    at(best[1])
    y, sr2 = _render(f0, secs=4.0, bank=8)
    for lab, z, r in (("take", xa, sr), ("ours", y[int(0.1 * sr2):], sr2)):
        print("  %s: mean click over 7 dB (%d), %.2f ms at half, %.2f at a tenth, %.1f dB over the bed"
              % ((lab,) + mean_click(z, r)))


LINE = (72, 74, 76, 77, 79, 77, 76, 74, 72)


def register(out):
    """BreathyTnr. (66.8) holding C3, G3, C4, G4, C5, G5, a second each, apart:
    the breath 5 dB more an octave down (breath_noise_octave_db)."""
    import mido
    import blockrender as BR
    from efx_demo import _sx
    from scipy.io import wavfile
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); mf.tracks.append(tr)
    tr.append(_sx(0x40, 0x00, 0x7F, 0x00))
    for c, v in ((0, 8), (32, 2)):
        tr.append(mido.Message("control_change", channel=0, control=c, value=v))
    tr.append(mido.Message("program_change", channel=0, program=66))
    gap = 240
    for n in (48, 55, 60, 67, 72, 79):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=100, time=gap))
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=1200))
        gap = 480
    L, R = BR.render(mf, "even")[:2]
    x = np.stack([np.asarray(L), np.asarray(R)], 1)
    wavfile.write(out, BR.SR, (x / np.abs(x).max() * 0.89 * 32767).astype(np.int16))
    print("  wrote %s" % out)


def legato(out):
    """BreathyTnr. (66.8) playing LINE twice: slurred (each note on 20 ticks
    before the last is off: the tone and the breath take the legato attack),
    then detached (120 ticks apart: each note speaks from silence)."""
    import mido
    import blockrender as BR
    from efx_demo import _sx
    from scipy.io import wavfile
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); mf.tracks.append(tr)
    tr.append(_sx(0x40, 0x00, 0x7F, 0x00))
    for c, v in ((0, 8), (32, 2)):
        tr.append(mido.Message("control_change", channel=0, control=c, value=v))
    tr.append(mido.Message("program_change", channel=0, program=66))
    ev = []
    t = 240
    for n in LINE:                      # slurred
        ev.append((t, "on", n)); ev.append((t + 500, "off", n)); t += 480
    t += 960
    for n in LINE:                      # detached
        ev.append((t, "on", n)); ev.append((t + 360, "off", n)); t += 480
    ev.sort(key=lambda e: (e[0], e[1] == "on"))
    last = 0
    for at, k, n in ev:
        tr.append(mido.Message("note_on" if k == "on" else "note_off", channel=0, note=n,
                               velocity=100 if k == "on" else 0, time=at - last))
        last = at
    L, R = BR.render(mf, "even")[:2]
    x = np.stack([np.asarray(L), np.asarray(R)], 1)
    wavfile.write(out, BR.SR, (x / np.abs(x).max() * 0.89 * 32767).astype(np.int16))
    print("  wrote %s" % out)


def ab(out):
    """The airy take, then ours (66.8) at its pitch, levelled on their bodies;
    then the plain GM 66 there, for the difference."""
    from gender_fit import ab_pairs
    ab_pairs([(AIRY, 66, 8, 3.5, 300, 900), (AIRY, 66, 0, 3.5, 300, 900)], out)


def main(argv):
    if "--register" in argv:
        register(argv[argv.index("--register") + 1])
        return 0
    if "--legato" in argv:
        legato(argv[argv.index("--legato") + 1])
        return 0
    if "--crackle-share" in argv:
        crackle_share_fit()
        return 0
    if "--crackle-spectrum" in argv:
        crackle_spectrum()
        return 0
    if "--crackle" in argv:
        crackle()
        return 0
    if "--ab" in argv:
        ab(argv[argv.index("--ab") + 1])
        return 0
    if "--fit" in argv:
        fit()
        return 0
    measure()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
