#!/usr/bin/env python3
"""Fit the koto (GM 107) to VCSL's Dan Tranh (CC0; ~/Documents/refs/vcsl/dantranh,
sources.md), with examples/harp_fit.py's yardstick (pizz_measure, pizz_fit).

    python3 examples/koto_fit.py [--dyn=mf] [--tilt] [--model]
    python3 examples/koto_fit.py --ring     the open strings' sympathetic ring

THE DAN TRANH IS THE KOTO'S COUSIN, not the koto: a Vietnamese long zither
with movable bridges over a long wooden box, as the koto (and the guzheng)
are, but STEEL-strung where the koto is silk or nylon -- brighter and longer
ringing. It is the nearest recorded relative there is, and the fit reads it
as that: the body, the pluck, the register laws, and not the string's make.

VCSL NAMES IT AN OCTAVE BELOW ITS SOUNDING PITCH, as it does its winds: the
files are staged under their sounding names (links, in REFS/sounding_<dyn>).
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

from pizz_measure import measure, report  # noqa: E402
import pizz_fit  # noqa: E402
from pizz_fit import fit_decay, fit_tilt  # noqa: E402
from harp_fit import fit_point, SDS  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs/vcsl/dantranh")
NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
pizz_fit.TS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.5, 3.0)


def staged(dyn):
    """The DYN plucks, linked under their sounding names (name + 12)."""
    out = os.path.join(REFS, "sounding_" + dyn)
    os.makedirs(out, exist_ok=True)
    for p in glob.glob(os.path.join(REFS, "*_%s_1.wav" % dyn)):
        m = re.match(r"([A-Ga-g]#?)(\d)_", os.path.basename(p))
        n = (int(m.group(2)) + 1) * 12 + NAMES.index(m.group(1).upper()) + 12
        dst = os.path.join(out, "%s%d.wav" % (NAMES[n % 12], n // 12 - 1))
        if not os.path.exists(dst):
            os.symlink(p, dst)
    return sorted(glob.glob(os.path.join(out, "*.wav")))


S3 = 2 ** np.arange(np.log2(140), np.log2(16000), 1 / 3.0)


def render(key, secs=0.6):
    import mido
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=107, time=0))
    t.append(mido.Message("note_on", channel=0, note=key, velocity=80, time=0))
    t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(secs * 960)))
    L, R = B.render(m)[:2]
    return 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64)), B.SR


def pluck(x, sr, f0, B=1.9e-4, a=0.0, b=0.03):
    """THE TSUME OFF THE STRING: the first 30 ms between the partials (each
    one's stretched place masked), third-octave bands, dB re the window's
    total -- attack_audit reads the recording's early top 13 dB over a clean
    onset's, and no onset time gives both its contrast and that."""
    from kalimba_fit import start
    t0 = start(x, sr)
    n = 1 << 15
    f = np.fft.rfftfreq(n, 1.0 / sr)
    near = np.zeros_like(f, bool)
    for m in range(1, 200):
        fm = m * f0 * np.sqrt(1.0 + B * m * m)
        if fm > 0.5 * sr:
            break
        near |= np.abs(f - fm) < max(0.12 * f0, 15.0)

    def spec(a_, b_):
        seg = x[t0 + int(a_ * sr):t0 + int(b_ * sr)]
        return np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n)) ** 2 / len(seg)
    X0 = spec(a, b)
    tot = X0.sum()
    out = []
    for lo, hi in zip(S3[:-1], S3[1:]):
        m_ = (f >= lo) & (f < hi) & ~near
        out.append(10 * np.log10(X0[m_].mean() * ((f >= lo) & (f < hi)).sum() / tot + 1e-30) if m_.sum() > 3 else np.nan)
    return np.array(out)


def fit_pluck(cls, rows, paths, passes=4):
    """--fit=pluck: strike_noise_db band by band toward the recordings (the
    median over the notes of recorded - ours), as the kalimba's thumb."""
    import warnings
    from pizz_measure import mono
    cen = np.sqrt(S3[:-1] * S3[1:])
    if not getattr(cls, "strike_noise_db", ()):
        cls.strike_noise_db = tuple((int(round(c)), -20.0) for c in cen)
    R, keys = [], []
    for r, p in zip(rows, paths):
        x, sr = mono(p)
        R.append(pluck(np.asarray(x, np.float64), sr, r["f0"]))
        keys.append(r["note"])
    for k in range(passes + 1):
        O = []
        for key in keys:
            y, sr = render(key)
            O.append(pluck(y, sr, 440.0 * 2 ** ((key - 69) / 12.0), B=float(cls.inharmonicity_coefficient)))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = np.nanmedian(np.array(R) - np.array(O), 0)
        print("  pass %d: tsume rec - ours, rms %.1f dB" % (k, np.sqrt(np.nanmean(d ** 2))), flush=True)
        if k == passes:
            break
        cls.strike_noise_db = tuple((hz, round(db + (float(dd) if np.isfinite(dd) else 0.0), 1))
                                    for (hz, db), dd in zip(cls.strike_noise_db, d))
    print("    strike_noise_db = %s" % (cls.strike_noise_db,))


# THE OPEN STRINGS: a koto's thirteen, in hirajoshi on D (strings 1 and 5
# both D4), equal-tempered at A440 -- the koto's tuning, not the Dan Tranh's.
# What the recordings give is how loud and how long another string rings.
STRINGS = (196.00, 220.00, 233.08, 293.66, 311.13, 392.00, 440.00, 466.16,
           587.33, 622.25, 783.99, 880.00)


def onset(x, sr):
    w = max(1, int(0.001 * sr))
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
    return int(np.flatnonzero(e > e.max() * 0.1)[0])


def _spec(x, sr, a, b, N=1 << 17):
    s = x[int(a * sr):int(b * sr)]
    return 20 * np.log10(np.abs(np.fft.rfft(s * np.hanning(len(s)), N)) + 1e-12), np.fft.rfftfreq(N, 1.0 / sr)


def survey(min_takes=8):
    """--ring: the peaks that recur across the takes, off every harmonic of
    the plucked note (2%), 30-330 ms after the pluck: (Hz, dB re the plucked
    fundamental, decay dB/s to 600-900 ms), medians. Measured over mf, f and
    ff: 15-18 rows at 150-610 Hz about 40 dB down (-28 to -48), dying 10-60
    dB/s -- the other strings, at the Dan Tranh's own tuning."""
    from pizz_measure import mono
    from voicefit import note_of
    peaks, n = [], 0
    for dyn in ("mf", "f", "ff"):
        for p in staged(dyn):
            f0 = 440.0 * 2 ** ((note_of(p) - 69) / 12.0)
            x, sr = mono(p)
            x = np.asarray(x, np.float64)
            t0 = onset(x, sr) / sr
            X1, f = _spec(x, sr, t0 + 0.03, t0 + 0.33)
            X2, _ = _spec(x, sr, t0 + 0.6, t0 + 0.9)
            L1 = X1[(f > f0 / 1.03) & (f < f0 * 1.03)].max()
            n += 1
            for k in np.flatnonzero((f > 60) & (f < 6000))[1:-1]:
                if X1[k] == X1[max(0, k - 25):k + 25].max() and X1[k] > L1 - 55:
                    r = f[k] / f0
                    if round(r) >= 1 and abs(r / round(r) - 1) < 0.02:
                        continue
                    peaks.append((f[k], X1[k] - L1, (X1[k] - X2[k]) / 0.57, p))
    peaks.sort()
    cl = []
    for q in peaks:
        if cl and q[0] / cl[-1][-1][0] < 1.012:
            cl[-1].append(q)
        else:
            cl.append([q])
    rows = []
    for c in cl:
        if len({q[3] for q in c}) >= min_takes:
            rows.append((float(np.median([q[0] for q in c])), float(np.median([q[1] for q in c])),
                         float(np.median([q[2] for q in c]))))
            print("  %7.1f Hz in %2d of %d takes  %+6.1f dB  %5.1f dB/s"
                  % (rows[-1][0], len({q[3] for q in c}), n, rows[-1][1], rows[-1][2]))
    return rows


def ring(x, sr, f0, freqs):
    """Each of FREQS: its level re the note's fundamental (30-330 ms after
    the pluck); NaN where it is the note's own (within 3% of f0 or 2 f0)."""
    t0 = onset(x, sr) / sr
    X1, f = _spec(x, sr, t0 + 0.03, t0 + 0.33)
    L1 = X1[(f > f0 / 1.03) & (f < f0 * 1.03)].max()
    out = []
    for hz in freqs:
        if any(abs(hz / (f0 * r) - 1.0) < 0.03 for r in (1.0, 2.0)):
            out.append(np.nan)
            continue
        s = (f > hz / 1.01) & (f < hz * 1.01)
        out.append(X1[s].max() - L1)
    return np.array(out)


def fit_ring(cls, rows, passes=3):
    """--ring: the strings at STRINGS, each at the survey's median level
    (dB re the plucked fundamental) and its decay where the survey's rows
    sit (interpolated in log frequency); the table's levels moved toward the
    target over the Dan Tranh's own pitches rendered."""
    from voicefit import note_of
    target = float(np.median([r[1] for r in rows]))
    lf = np.log([r[0] for r in rows])
    order = np.argsort(lf)
    dps = [float(np.interp(np.log(hz), lf[order], np.array([r[2] for r in rows])[order])) for hz in STRINGS]
    # the decays scatter row to row (4-75 dB/s): a running median of five
    sm = [float(np.median(dps[max(0, i - 2):i + 3])) for i in range(len(dps))]
    cls.ring_db = tuple((hz, round(target, 1), round(d, 1)) for hz, d in zip(STRINGS, sm))
    keys = sorted({note_of(p) for p in staged("mf")})
    import warnings
    for n in range(passes + 1):
        O = []
        for key in keys:
            y, sr = render(key, 1.2)
            O.append(ring(y, sr, 440.0 * 2 ** ((key - 69) / 12.0), STRINGS))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = target - np.nanmedian(np.array(O), 0)
        print("  pass %d: strings target - ours, rms %.1f dB (target %.1f)"
              % (n, np.sqrt(np.nanmean(d ** 2)), target), flush=True)
        if n == passes:
            break
        cls.ring_db = tuple((hz, round(db + float(dd), 1), dp) for (hz, db, dp), dd in zip(cls.ring_db, d))
    print("    ring_db = %s" % (cls.ring_db,))


def ab(paths, out, n=7):
    """--ab=OUT.wav: every few recorded notes, then ours at the pitch, 3 s
    each, matched in level over the first 0.5 s."""
    import wave
    from scipy.signal import resample_poly
    from pizz_measure import mono
    from voicefit import note_of
    pick = [paths[int(i)] for i in np.linspace(0, len(paths) - 1, n)]
    parts, sr = [], 44100
    for p in pick:
        x, sr = mono(p)
        x = np.asarray(x, np.float64)
        from kalimba_fit import start
        i = start(x, sr)
        x = x[max(0, i - int(0.01 * sr)):i + int(3.0 * sr)]
        y, sr2 = render(note_of(p), 3.0)
        j = start(y, sr2)
        y = y[max(0, j - int(0.01 * sr2)):j + int(3.0 * sr2)]
        if sr2 != sr:
            y = resample_poly(y, sr, sr2)
        n_ = min(len(x), len(y))
        x, y = x[:n_], y[:n_]
        y = y * np.sqrt(np.mean(x[:int(0.5 * sr)] ** 2) / np.mean(y[:int(0.5 * sr)] ** 2))
        fade = np.ones(n_); fade[-int(0.3 * sr):] = np.linspace(1, 0, int(0.3 * sr))
        gap = np.zeros(int(0.35 * sr))
        parts += [x * fade, gap, y * fade, gap, gap]
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


def main(argv):
    import tonelib as T
    dyn = next((a.split("=")[1] for a in argv if a.startswith("--dyn=")), "mf")
    paths = staged(dyn)
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--ab=")), None)
    if out:
        return ab(paths, out) or 0
    if "--ring" in argv:
        import patch_map
        patch_map.PROGRAM_CLASS[107] = T.KotoProperties
        fit_ring(T.KotoProperties, survey())
        return 0
    rows = [r for r in (measure(p) for p in paths) if r]
    report(rows, "dan tranh " + dyn)
    a, b, s, n, err = fit_decay(rows)
    print("decay_db %.2f  harmonic_decay_db %.2f  decay_register_slope %.3f"
          "  (%d partials, median |log err| %.2f)" % (a, b, s, n, err))
    bp, nb, bs = fit_point(rows)
    print("pluck point %.3f, median of %d notes with r >= 0.7 (%s)"
          % (bp, nb, " ".join("%.2f" % x for x in sorted(bs))))
    if "--body" in argv:
        # THE LOW END (harp_fit's --body): under ~250 Hz the box cannot
        # radiate a fundamental -- the recording's sits under its own upper
        # partials. The high-pass scanned, the colour refitted at each.
        base = type("Fit", (T.KotoProperties,), dict(strike_point=bp))
        for bc in (110.0, 180.0, 250.0, 350.0):
            for bo in (2.0, 4.0):
                cls = type("Fit", (base,), dict(bell_cutoff_hz=bc, bell_order=bo))
                (e, td, od, sd), _ = fit_tilt(rows, cls, coarse=True, sds=SDS)
                print("  bell_cutoff_hz %5.0f order %.0f: ladder miss %.2f dB  (tilt %.1f, %+.1f, notch %.2f)"
                      % (bc, bo, e, td, od, sd), flush=True)
    if "--fit=pluck" in argv:
        import patch_map
        patch_map.PROGRAM_CLASS[107] = T.KotoProperties
        ok = [p for p in paths if measure(p)]
        fit_pluck(T.KotoProperties, rows, ok)
    if "--tilt" in argv:
        base = type("Fit", (T.KotoProperties,), dict(strike_point=bp))
        (e, td, od, sd), e0 = fit_tilt(rows, base, sds=SDS)
        print("tilt: tonal_dampening %.2f  octave_dampening %+.2f  strike_depth %.2f"
              "  (median ladder miss %.1f dB, from %.1f as it stands)" % (td, od, sd, e, e0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
