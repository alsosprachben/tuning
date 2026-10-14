#!/usr/bin/env python3
"""Fit the celesta (GM 8) and the music box (GM 10) to recordings: each
instrument's mode set, every mode's level and decay, and how the decay climbs
the register. Read with examples/steelbar_peaks.py first; sources.md.

    python3 -I examples/steelbar_fit.py measure --voice=celesta|musicbox [--ours]
    python3 -I examples/steelbar_fit.py fit --voice=celesta|musicbox   (prints the class values)
    python3 -I examples/steelbar_fit.py calibrate --voice=...   (the gains through the renderer; writes tonelib.py)
    python3 -I examples/steelbar_fit.py ab --voice=... OUT.wav          each take, then ours

THE TAKES (all CC0, Freesound):
  celesta   Macsat-Rd's pack 23781: twelve notes A4-G#5 ("Medium"), ~10 c sharp
  musicbox  folkman's pack 4540 (a box in D, 16 teeth F#5-E7) and rbnuser's
            pack 19724 (13 teeth D5-G7, iPad)

WHAT THEY HOLD, both instruments alike in kind:
  * the FUNDAMENTAL, dominant;
  * EXACT HARMONICS (2x, 3x, 5x, 7x ...), 10-50 dB down, decaying with the
    fundamental -- no free bar or cantilever makes integer ratios, so this is
    the steel's motion or its radiation (two recorders, two instruments: not
    either recorder);
  * the BAR'S OWN MODES, quiet and gone in a fraction of a second: the
    celesta's are a free bar's (2.76x, 5.42x); the music box's tooth is a
    CANTILEVER (~6x, ~10-15x, 17.6x on the low teeth) -- not the free bar the
    class had.

Each mode is read at its ratio to the strongest peak (the note): its level
0.03-0.13 s after the strike re the fundamental's, and its decay (dB/s of the
band, a line to -30 dB or 1.5 s). The class's decay is tonelib's D, half the
band's rate, at 415 Hz with one register slope (as the timpani's).
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import upright_fit as U

FS = os.path.expanduser("~/Documents/refs/freesound")
VOICES = {
    "celesta": dict(program=8, globs=("celesta/*.wav",),
                    modes=(1.0, 2.0, 2.76, 3.0, 5.0, 5.42, 7.0)),
    "musicbox": dict(program=10, globs=("musicbox_folkman/*.wav", "musicbox_rbnuser_wav/*.wav"),
                     modes=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 17.6)),
}
VEL = 90


def takes(voice):
    """[(path, x, sr)]: each take's first strike (some takes hold a second,
    or a melody: the first note is the one named)."""
    out = []
    for g in VOICES[voice]["globs"]:
        for p in sorted(glob.glob(os.path.join(FS, g))):
            x, sr = U.load(p)
            out.append((p, x, sr))
    return out


def fundamental(x, sr):
    t0 = U.onset(x, sr)
    seg = x[t0 + int(0.01 * sr):t0 + int(0.3 * sr)]
    N = 1 << 17
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1 / sr)
    ok = (f > 200) & (f < 6000)
    return float(f[ok][np.argmax(X[ok])])


def mode_reading(x, sr, f0, ratio):
    """(level dB re the fundamental, 0.03-0.13 s; decay dB/s), or NaNs where
    the mode is not found within 3% of its ratio or is above 0.45 sr."""
    from scipy.signal import butter, sosfiltfilt
    t0 = U.onset(x, sr)
    fm = f0 * ratio
    if fm > 0.45 * sr:
        return np.nan, np.nan
    seg = x[t0 + int(0.03 * sr):t0 + int(0.13 * sr)]
    N = 1 << 17
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) ** 2
    f = np.fft.rfftfreq(N, 1 / sr)
    lev = lambda fc, tol: 10 * np.log10(X[(f > fc * (1 - tol)) & (f < fc * (1 + tol))].max() + 1e-30)
    tol = 0.03 if ratio != 1.0 else 0.01
    l = lev(fm, tol) - lev(f0, 0.01)
    bw = max(6.0, 0.015 * fm)
    y = sosfiltfilt(butter(2, [fm - bw, min(fm + bw, 0.49 * sr)], btype="band", fs=sr, output="sos"), x[t0:])
    w = int(0.01 * sr)
    e = 10 * np.log10(np.array([np.mean(y[j:j + w] ** 2) for j in range(0, min(len(y), int(1.5 * sr)) - w, w)]) + 1e-20)
    a = 3
    k = np.flatnonzero(e[a:] < e[a] - 30)
    b = a + (k[0] if len(k) else len(e) - a)
    d = -np.polyfit(np.arange(a, b) * 0.01, e[a:b], 1)[0] if b - a >= 4 else np.nan
    return l, d


def measure(voice, ours=False):
    modes = VOICES[voice]["modes"]
    rows = []
    for p, x, sr in takes(voice):
        f0 = fundamental(x, sr)
        k = int(round(69 + 12 * np.log2(f0 / 440.0)))
        if ours:
            x, sr = U.render(VOICES[voice]["program"], k, VEL, 2.0)
            f0 = fundamental(x, sr)
        rows.append((k, f0, [mode_reading(x, sr, f0, r) for r in modes]))
    return rows


def show(voice, rows):
    modes = VOICES[voice]["modes"]
    print("   key    f0   " + " ".join("%13s" % ("x%g lvl/dec" % r) for r in modes))
    for k, f0, rd in sorted(rows):
        print("   %3d %7.1f " % (k, f0) + " ".join(
            "%6s/%6s" % ("%.0f" % l if np.isfinite(l) else ".", "%.0f" % d if np.isfinite(d) else ".")
            for l, d in rd))


def fit(voice):
    """The class values: mode_gains (median amplitude re the fundamental,
    over the takes that found the mode above -60 dB), the register slope of
    the fundamental's decay, and mode_decays (tonelib's D at 415 Hz: the
    median of each mode's measured band rate, halved and taken back to 415
    Hz along that slope)."""
    modes = VOICES[voice]["modes"]
    rows = measure(voice)
    f0s = np.array([f0 for _, f0, _ in rows])
    d1 = np.array([rd[0][1] for _, _, rd in rows])
    ok = np.isfinite(d1) & (d1 > 0.5)
    slope, c = np.polyfit(np.log2(f0s[ok] / 415.0), np.log2(d1[ok]), 1)
    gains, decs = [], []
    for j, r in enumerate(modes):
        L = np.array([rd[j][0] for _, _, rd in rows])
        D = np.array([rd[j][1] for _, _, rd in rows])
        okl = np.isfinite(L) & (L > -60)
        gains.append(float(10 ** (np.median(L[okl]) / 20)) if okl.any() else 0.0)
        # a decay only where the mode stands clear of the take's floor: at
        # -47 to -50 dB the band is the noise, which does not decay, and the
        # music box's 6x and 11.5x read 1.2 and 0.6 dB/s from it
        okd = np.isfinite(D) & (D > 0.5) & np.isfinite(L) & (L > -45)
        at415 = D[okd] / 2.0 / 2.0 ** (slope * np.log2(f0s[okd] / 415.0))
        decs.append(float(np.median(at415)) if okd.any() else np.nan)
        print("   x%-5g level %+6.1f dB (%d of %d takes), D at 415 Hz %6.2f" % (
            r, 20 * np.log10(max(gains[-1], 1e-9)), okl.sum(), len(L), decs[-1]))
    print("  decay_register_slope = %.3f   (the fundamental's D: %.1f at 415 Hz)" % (slope, 2 ** c / 2))
    print("  mode_ratios = %s" % (tuple(modes),))
    print("  mode_gains = %s" % (tuple(round(g, 4) for g in gains),))
    print("  mode_decays = %s" % (tuple(round(d, 2) for d in decs),))


def calibrate(voice, passes=2):
    """The gains THROUGH THE RENDERER: a mode read 0.03-0.13 s after the
    strike has already fallen by what its own decay takes in that window --
    the celesta's plate modes (D 62-77) ~10-13 dB -- in the take and in ours
    alike, so a gain read off a take is a window's level, not the strike's.
    Each mode's gain is moved by the median of (take - ours) over the notes,
    measured the same way; rewrites mode_gains in tonelib.py."""
    import re
    import tonelib as T
    import patch_map as PM
    cls = PM.property_class_for_program(VOICES[voice]["program"])
    rec = measure(voice)
    for it in range(passes + 1):
        mine = measure(voice, ours=True)
        g = list(cls.mode_gains)
        msg = []
        # the fitted modes by RATIO: the class may hold more (the music box's
        # tooth an octave below, drawn per key, is not one of them)
        ix = [list(cls.mode_ratios).index(r) for r in VOICES[voice]["modes"]]
        for j in range(len(ix)):
            d = [r[2][j][0] - o[2][j][0] for r, o in zip(rec, mine)
                 if np.isfinite(r[2][j][0]) and np.isfinite(o[2][j][0]) and r[2][j][0] > -60]
            dd = float(np.median(d)) if d else 0.0
            msg.append("%+.1f" % dd)
            if it < passes and j > 0:
                g[ix[j]] = round(g[ix[j]] * 10 ** (dd / 20), 5)
        print("  pass %d: take - ours by mode, median dB: %s" % (it, " ".join(msg)), flush=True)
        if it == passes:
            break
        cls.mode_gains = tuple(g)
    path = os.path.join(os.path.dirname(HERE), "tonelib.py")
    src = open(path).read()
    a = src.index("class %s(" % cls.__name__)
    body = re.sub(r"^    mode_gains = .*$", "    mode_gains = %s" % (tuple(cls.mode_gains),), src[a:], count=1, flags=re.M)
    open(path, "w").write(src[:a] + body)
    print("  mode_gains = %s" % (tuple(cls.mode_gains),))


# third octaves, 250 Hz - 16 kHz
A3 = 2 ** np.arange(np.log2(250), np.log2(16000), 1 / 3.0)
A3C = np.sqrt(A3[:-1] * A3[1:])


def attack_bands(x, sr, f0, modes, a=0.0, b=0.03, masked=False):
    """Third-octave levels over a..b s after the onset, dB re the
    fundamental's peak 0.03-0.13 s (immune to the recorder's EQ below the
    note); masked: only what lies OUTSIDE the modes and the harmonics (noise)."""
    t0 = U.onset(x, sr)
    n = 1 << 16
    f = np.fft.rfftfreq(n, 1.0 / sr)

    def spec(a_, b_):
        seg = x[t0 + int(a_ * sr):t0 + int(b_ * sr)]
        return np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n)) ** 2 / len(seg)
    ref = spec(0.03, 0.13)
    ref = ref[np.abs(f - f0) < 0.02 * f0].max()
    X = spec(a, b)
    near = np.zeros_like(f, bool)
    if masked:
        for r in sorted(set(list(modes) + list(range(1, 40)))):
            near |= np.abs(f - r * f0) < max(0.15 * f0, 20.0)
    out = []
    for lo, hi in zip(A3[:-1], A3[1:]):
        m = (f >= lo) & (f < hi) & ~near & (hi < 0.45 * sr)
        out.append(10 * np.log10(X[m].sum() / ref + 1e-30) if m.sum() > 3 else np.nan)
    return np.array(out)


def attack(voice, a=0.0, b=0.03):
    """`attack`: what the takes hold over ours in the first 30 ms, all of it
    and outside the partials (the pluck's noise), by third octave."""
    modes = VOICES[voice]["modes"]
    rows = {"all": [], "noise": [], "late": []}
    for p, x, sr in takes(voice):
        f0 = fundamental(x, sr)
        k = int(round(69 + 12 * np.log2(f0 / 440.0)))
        y, sr2 = U.render(VOICES[voice]["program"], k, VEL, 1.0)
        g0 = fundamental(y, sr2)
        rows["all"].append(attack_bands(x, sr, f0, modes, a, b) - attack_bands(y, sr2, g0, modes, a, b))
        rows["noise"].append(attack_bands(x, sr, f0, modes, a, b, True) - attack_bands(y, sr2, g0, modes, a, b, True))
        rows["late"].append(attack_bands(x, sr, f0, modes, 0.1, 0.2) - attack_bands(y, sr2, g0, modes, 0.1, 0.2))
        print("  %3d %s" % (k, " ".join("%4.0f" % v if np.isfinite(v) else "   ." for v in rows["all"][-1])))
    print("  Hz  " + " ".join("%4.0f" % (c / 1000) if c >= 1000 else "%4.1f" % (c / 1000) for c in A3C))
    for nm, r in rows.items():
        print("  %-5s" % nm + " ".join("%4.0f" % v if np.isfinite(v) else "   ."
                                       for v in np.nanmedian(np.array(r), 0)))
    # how noise-like the takes' first 30 ms is, outside the partials, re all
    # of the band: near 0 dB = the band IS noise; far under = partials
    fr = []
    for p, x, sr in takes(voice):
        f0 = fundamental(x, sr)
        fr.append(attack_bands(x, sr, f0, modes, a, b, True) - attack_bands(x, sr, f0, modes, a, b))
    print("  take noise share of band " + " ".join("%4.0f" % v if np.isfinite(v) else "   ."
                                                 for v in np.nanmedian(np.array(fr), 0)))


PLUCK_WINDOWS = ((0.0, 0.005), (0.005, 0.015), (0.015, 0.03), (0.03, 0.06))


def noise_profile(x, sr, f0, modes):
    """The noise between the partials: third octaves (A3C) in each of
    PLUCK_WINDOWS, dB re the fundamental, normalised to a 30 ms window."""
    return np.array([attack_bands(x, sr, f0, modes, a, b, True) + 10 * np.log10(0.03 / (b - a))
                     for a, b in PLUCK_WINDOWS])


def pluck(voice, passes=4):
    """`pluck`: the PIN'S SNAP -- tonelib's strike_noise rows and their
    slower tail (strike_noise_tail) to the noise between the takes'
    partials. The table from the first 5 ms (band by band, with an octave
    slope over the keys), the tail's level from 15-60 ms, the two rates from
    5-15 and 30-60 ms; all through the renderer, as calibrate. Prints the
    class values."""
    import tonelib as T
    import patch_map as PM
    cls = PM.property_class_for_program(VOICES[voice]["program"])
    modes = VOICES[voice]["modes"]
    rec, keys = [], []
    for p, x, sr in takes(voice):
        f0 = fundamental(x, sr)
        keys.append(int(round(69 + 12 * np.log2(f0 / 440.0))))
        rec.append(noise_profile(x, sr, f0, modes))
    rec = np.array(rec)
    if not getattr(cls, 'strike_noise_db', ()):
        cls.strike_noise_db = tuple((int(round(c)), -30.0) for c in A3C)
        cls.strike_noise_octave_db = 0.0
        cls.strike_noise_dbs = 3000.0
        cls.strike_noise_fade_s = 0.0005
        cls.strike_noise_tail = (-20.0, 350.0)
        cls.strike_noise_len_s = 0.25
    reg = np.log2(440.0 * 2 ** ((np.array(keys) - 69) / 12.0) / 440.0)
    for it in range(passes + 1):
        ours = []
        for k in keys:
            y, sr2 = U.render(VOICES[voice]["program"], k, VEL, 0.5)
            ours.append(noise_profile(y, sr2, fundamental(y, sr2), modes))
        D = rec - np.array(ours)           # [take, window, band]
        hi = A3C > 1500                    # where the partials' own splatter is under it
        w = [float(np.nanmedian(D[:, j][:, hi])) for j in range(len(PLUCK_WINDOWS))]
        print("  pass %d: take - ours by window (median over the bands > 1.5 kHz): %s"
              % (it, " ".join("%+.1f" % v for v in w)), flush=True)
        if it == passes:
            break
        band = np.nanmedian(D[:, 0], 0)
        km = np.nanmedian(D[:, 0] - band, 1)
        cls.strike_noise_octave_db += 0.7 * float(np.polyfit(reg, np.nan_to_num(km), 1)[0])
        old = dict(cls.strike_noise_db)
        cls.strike_noise_db = tuple(
            (int(round(c)), round(float(np.interp(np.log(c), np.log(list(old)), list(old.values()))
                                        + np.clip(np.nan_to_num(b), -12, 12)), 1))
            for c, b in zip(A3C, band))
        # the tail's level by 15-60 ms; its rate by how 30-60 falls from
        # 15-30 against ours; the strike's by 5-15 against 0-5
        tl = 0.5 * (w[2] + w[3]) - w[0]
        cls.strike_noise_tail = (round(cls.strike_noise_tail[0] + 0.7 * tl, 2),
                                 round(max(50.0, cls.strike_noise_tail[1] - 0.7 * (w[3] - w[2]) / 0.03), 1))
        cls.strike_noise_dbs = round(max(300.0, cls.strike_noise_dbs - 0.7 * (w[1] - w[0]) / 0.0075), 1)
    print("    strike_noise_db = %s" % (cls.strike_noise_db,))
    print("    strike_noise_octave_db = %.3f" % cls.strike_noise_octave_db)
    print("    strike_noise_dbs = %.1f" % cls.strike_noise_dbs)
    print("    strike_noise_tail = %s" % (cls.strike_noise_tail,))
    print("  residual take - ours by band (median over takes), per window:")
    print("  Hz      " + " ".join("%5.1f" % (c / 1000) for c in A3C))
    for j, (a, b) in enumerate(PLUCK_WINDOWS):
        print("  %3.0f-%3.0f " % (a * 1e3, b * 1e3) + " ".join("%5.0f" % v for v in np.nanmedian(D[:, j], 0)))


def ab(voice, out, note_s=2.0):
    import harpsi_ab as A
    from roomtail import write_wav
    A.NOTE_S = note_s
    gap, rest = np.zeros(int(A.GAP_S * A.SR)), np.zeros(int(0.5 * A.SR))
    parts = []
    for p, x, sr in takes(voice):
        k = int(round(69 + 12 * np.log2(fundamental(x, sr) / 440.0)))
        y, sr2 = U.render(VOICES[voice]["program"], k, VEL, note_s)
        parts += [A.fit_note(x, sr), gap, A.fit_note(y, sr2), rest]
    z = np.concatenate(parts)
    write_wav(out, np.stack([z, z], 1), A.SR)


def main(argv):
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    voice = opts.get("voice", "celesta")
    args = [a for a in argv if not a.startswith("--")]
    if args[:1] == ["measure"]:
        show(voice, measure(voice, "--ours" in argv))
    elif args[:1] == ["fit"]:
        fit(voice)
    elif args[:1] == ["calibrate"]:
        calibrate(voice)
    elif args[:1] == ["pluck"]:
        pluck(voice)
    elif args[:1] == ["attack"]:
        attack(voice)
    elif args[:1] == ["ab"]:
        ab(voice, args[1])
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
