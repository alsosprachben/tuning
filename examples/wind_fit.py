#!/usr/bin/env python3
"""Fit a sustained fipple voice -- the recorder (GM 74), the ocarina (GM 79) --
to VCSL's sustains (CC0; ~/Documents/refs/vcsl/{recorder,ocarina}, sources.md).

    wind_fit.py --voice=recorder              measure: recorded against ours
    wind_fit.py --voice=recorder --fit        fit the spectrum knobs
    wind_fit.py --voice=ocarina --fit=breath  fit sustain_jitter to the breath

Everything is measured the same way on both sides, over the steady part of the
note (0.4-1.9 s after it speaks), so the fit is fitted to the measurement made
the way the reference was:

  LADDER   each harmonic's peak, dB re the fundamental, to h12
  PARTIALS each partial's frequency against the series m*f0 (cents) -- a
           sustained pipe is mode-locked, so this is the test of whether an
           open pipe has any inharmonicity to model
  BREATH   the spectrum midway between harmonics (the middle 40% of each
           gap, its median), dB re the fundamental's peak, gaps 1-8
  THIRDS   third-octave bands from the fundamental up, dB re the strongest

VCSL NAMES THESE AN OCTAVE BELOW THEIR SOUNDING PITCH: the alto's "F3" sounds
349 Hz. Sounding = the name + 12, for every set here (checked by f0).
"""
import glob
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import voicefit as V

REFS = os.path.expanduser("~/Documents/refs/vcsl")
VOICES = {
    # GM 74: VCSL's baroque soprano, alto and tenor recorders, pooled -- a GM
    # recorder is not one size, and the three agree where they overlap.
    "recorder": (74, "RecorderProperties", "recorder", "*Recorder_Sus_*.wav"),
    # GM 79: the typical (alto C) ocarina; the small one is the sopranino.
    "ocarina": (79, "OcarinaProperties", "ocarina", "*.wav"),
}
T0, T1 = 0.4, 1.9
VEL = 80
NH = 12
E3 = 2 ** np.arange(np.log2(45), np.log2(16000), 1 / 3.0)


def recordings(voice):
    _, _, d, pat = VOICES[voice]
    out = []
    for p in sorted(glob.glob(os.path.join(REFS, d, pat))):
        n = V.note_of(p)
        if n is not None:
            out.append((n + 12, p))
    return out


def speaks(x, sr):
    """Where the note has spoken: the envelope first within 20 dB of its peak
    (a sustain's peak can come seconds in, so not argmax)."""
    w = int(0.005 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
    return int(np.flatnonzero(e > e.max() * 0.1)[0])


def f0_near(seg, sr, key):
    """Autocorrelation within a semitone of the expected pitch: unseeded it
    locks an octave low on a third of these."""
    f = 440.0 * 2 ** ((key - 69) / 12.0)
    got = V.detect_f0(seg, sr, f / 1.06, f * 1.06)
    if got:
        return got
    # Near 2 kHz a semitone is two lags wide and the search has no room: the
    # spectrum's peak instead (the ladder refines every partial anyway).
    N = 1 << 18
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    a, b = int(f / 1.06 * N / sr), int(f * 1.06 * N / sr)
    return (a + int(np.argmax(X[a:b]))) * sr / N


def analyse(x, sr, key):
    i = speaks(x, sr)
    seg = x[i + int(T0 * sr): i + int(T1 * sr)]
    seg = seg - seg.mean()
    f0 = f0_near(seg, sr, key)
    N = 1 << 19
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    df = sr / N
    peaks = []
    for m in range(1, NH + 1):
        fm = m * f0
        if fm > 0.45 * sr:
            break
        a, b = int((fm - 0.2 * f0) / df), int((fm + 0.2 * f0) / df)
        k = a + int(np.argmax(X[a:b]))
        y0, y1, y2 = np.log(X[k - 1:k + 2] + 1e-30)
        d = y0 - 2 * y1 + y2
        off = 0.5 * (y0 - y2) / d if d != 0 else 0.0
        peaks.append(((k + off) * df, X[k]))
    fr = np.array([p[0] for p in peaks])
    amp = np.array([p[1] for p in peaks])
    ladder = 20 * np.log10(amp / amp[0])
    # The series' own f0, least squares over the partials that stand up.
    m = np.arange(1, len(fr) + 1)
    ok = ladder > -45
    f0s = float(np.sum(fr[ok] * m[ok]) / np.sum(m[ok] ** 2))
    cents = np.where(ok, 1200 * np.log2(fr / (m * f0s)), np.nan)
    breath = []
    for g in range(1, 9):
        a, b = int((g + 0.3) * f0 / df), int((g + 0.7) * f0 / df)
        if b * df > 0.45 * sr:
            break
        breath.append(20 * np.log10(np.median(X[a:b]) / amp[0] + 1e-30))
    P = X ** 2
    f = np.arange(len(X)) * df
    th = np.array([P[(f >= lo) & (f < hi)].sum() for lo, hi in zip(E3[:-1], E3[1:])])
    th = 10 * np.log10(th + 1e-30)
    th = np.maximum(th - th.max(), -60.0)
    th = np.where(E3[1:] > f0 * 0.89, th, np.nan)
    return dict(f0=f0s, ladder=ladder, cents=cents, breath=np.array(breath), thirds=th)


def load(p):
    x, sr = V.mono(p)
    return x.astype(np.float64), sr


def use_class(voice):
    import patch_map
    import tonelib
    prog, cls, _, _ = VOICES[voice]
    patch_map.PROGRAM_CLASS[prog] = getattr(tonelib, cls)
    return prog, getattr(tonelib, cls)


def render(program, key, secs=2.4):
    import mido
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=program, time=0))
    t.append(mido.Message("note_on", channel=0, note=key, velocity=VEL, time=0))
    t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(secs * 960)))
    L, R = B.render(m)[:2]
    return 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64)), B.SR


def table(rows, field, n, fmt="%6.1f"):
    v = [r[field][:n] for r in rows]
    v = [np.concatenate([a, np.full(n - len(a), np.nan)]) for a in v]
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.nanmean(np.array(v), 0)


def report(voice, prog):
    rec, ours = [], []
    for key, p in recordings(voice):
        x, sr = load(p)
        r = analyse(x, sr, key)
        y, sr2 = render(prog, key)
        o = analyse(y, sr2, key)
        rec.append(r)
        ours.append(o)
        print("  %-36s key %3d  f0 %7.1f  h2 %+6.1f/%+6.1f  h3 %+6.1f/%+6.1f  breath1 %+6.1f/%+6.1f"
              % (os.path.basename(p), key, r["f0"], r["ladder"][1], o["ladder"][1],
                 r["ladder"][2], o["ladder"][2], r["breath"][0], o["breath"][0]))
    for name, rows in (("recorded", rec), ("ours", ours)):
        print("  %-9s ladder " % name + " ".join("%6.1f" % v for v in table(rows, "ladder", NH)))
    for name, rows in (("recorded", rec), ("ours", ours)):
        print("  %-9s cents  " % name + " ".join("%6.1f" % v for v in table(rows, "cents", NH)))
    for name, rows in (("recorded", rec), ("ours", ours)):
        print("  %-9s breath " % name + " ".join("%6.1f" % v for v in table(rows, "breath", 8)))
    return rec, ours


# The knobs are fitted against REGISTER MEANS, not single notes: one fingering's
# h2 sits at -10 dB and its neighbour's at -62 (the recorder's), which is the
# instrument's fingering character and no single voice can follow it -- fitted
# note by note the error stalled at 8 dB on that scatter. Each register's mean
# ladder (h2-h10, where the recording stands within 70 dB), its third-octave
# bands (within 40 dB) and its breath (gaps 1-6) against ours.
SPECTRUM = ("tonal_dampening", "bore_corner_hz", "bore_order", "even_harmonic_db")
REGISTERS = ((0, 72), (72, 84), (84, 128))


def _mean(rows, field, n):
    v = [np.concatenate([r[field][:n], np.full(max(0, n - len(r[field])), np.nan)])[:n] for r in rows]
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.nanmean(np.array(v), 0)


def error(keys, rec, ours, parts=False):
    out = {"ladder": [], "thirds": [], "breath": []}
    for lo, hi in REGISTERS:
        idx = [i for i, k in enumerate(keys) if lo <= k < hi]
        if not idx:
            continue
        R = [rec[i] for i in idx]
        O = [ours[i] for i in idx]
        r, o = _mean(R, "ladder", 10), _mean(O, "ladder", 10)
        w = np.isfinite(r) & np.isfinite(o) & (r > -70)
        out["ladder"].extend((o - r)[w][1:])
        r = _mean(R, "thirds", len(E3) - 1)
        o = _mean(O, "thirds", len(E3) - 1)
        w = np.isfinite(r) & np.isfinite(o) & (r > -40)
        out["thirds"].extend((o - r)[w])
        r, o = _mean(R, "breath", 6), _mean(O, "breath", 6)
        w = np.isfinite(r) & np.isfinite(o)
        out["breath"].extend((o - r)[w])
    rms = {k: float(np.sqrt(np.mean(np.square(v)))) for k, v in out.items() if v}
    e = float(np.sqrt(np.mean(np.square(sum(out.values(), [])))))
    return (e, rms) if parts else e


def fit(voice, prog, cls, knobs, maxfev=150):
    from scipy.optimize import minimize
    refs = []
    for key, p in recordings(voice):
        x, sr = load(p)
        refs.append((key, analyse(x, sr, key)))
    # dB knobs (even_harmonic_db) move additively, 10 dB a unit; the rest in log.
    db = np.array([k.endswith("_db") for k in knobs])
    start = {"even_harmonic_db": -6.0, "chiff_bandwidth": 0.5}
    x0 = np.array([float(getattr(cls, k) if getattr(cls, k) is not None else start[k]) for k in knobs])
    best = [1e9, x0]

    def val(z):
        return np.where(db, x0 + 10.0 * z, np.exp(z) * x0)

    def f(z):
        v = val(z)
        for k, q in zip(knobs, v):
            setattr(cls, k, float(q))
        ours = [analyse(*render(prog, key), key) for key, _ in refs]
        e, parts = error([k for k, _ in refs], [r for _, r in refs], ours, True)
        if e < best[0]:
            best[:] = [e, v]
            print("  %6.2f dB (%s)  %s" % (e, " ".join("%s %.1f" % kv for kv in parts.items()),
                                          " ".join("%s=%.4g" % (k, q) for k, q in zip(knobs, v))), flush=True)
        return e
    n = len(knobs)
    simplex = np.vstack([np.zeros(n)] + [0.4 * np.eye(n)[i] for i in range(n)])
    minimize(f, np.zeros(n), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02})
    for k, q in zip(knobs, best[1]):
        setattr(cls, k, float(q))
    return best


def runs(path, first):
    """An Iowa run (one note after another, silence between): each note's
    samples and key, ascending from FIRST."""
    x, sr = load(path)
    w = int(0.02 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
    on = e > e.max() * 0.03
    edges = np.flatnonzero(np.diff(on.astype(int)))
    segs, i = [], 0
    if on[0]:
        edges = np.concatenate(([0], edges))
    while i + 1 < len(edges):
        a, b = edges[i], edges[i + 1]
        if b - a > 1.0 * sr:
            segs.append(x[max(0, a - int(0.05 * sr)):b])
        i += 2
    return [(first + n, s) for n, s in enumerate(segs)], sr


def inharm(spec):
    """--inharm=FILE:FIRSTKEY[,...]: each partial's cents off the series."""
    rows = []
    for item in spec.split(","):
        path, first = item.rsplit(":", 1)
        notes, sr = runs(os.path.expanduser(path), int(first))
        for key, x in notes:
            rows.append(analyse(x, sr, key))
            print("  %-22s key %3d  f0 %7.1f  " % (os.path.basename(path), key, rows[-1]["f0"]) +
                  " ".join("%5.1f" % c for c in rows[-1]["cents"][:10]))
    print("  mean cents  " + " ".join("%5.1f" % v for v in table(rows, "cents", 10)))
    print("  |dev| max   %.2f cents over %d notes (a partial near the noise reads loose)" % (np.nanmax(np.abs(np.concatenate([r["cents"][:10] for r in rows]))), len(rows)))


def ab(voice, prog, out, n=7, head=2.0, xf=0.1):
    """--ab=OUT.wav: each recording, then ours at the same pitch, matched in
    level -- every n-th note across the compass. A recording sustains 6-20 s,
    so it is its first HEAD seconds spliced (an XF crossfade, inside its
    steady sustain) to its own release and tail: the ending is the real one,
    not a cut. Ours is held as long and released, its tail kept as long."""
    import wave
    from scipy.signal import resample_poly
    recs = sorted(recordings(voice))
    pick = [recs[int(i)] for i in np.linspace(0, len(recs) - 1, n)]
    parts, sr = [], 44100
    for key, p in pick:
        x, sr = load(p)
        i = speaks(x, sr)
        w = int(0.005 * sr)
        e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
        st = np.median(e[i + int(0.5 * sr):i + int(1.5 * sr)])
        r0 = int(np.flatnonzero(e > st * 0.5)[-1])          # where the release begins
        tail = x[r0 - int(0.4 * sr):]                        # its last 0.4 s of sustain, on
        nx = int(xf * sr)
        a = x[i:i + int(head * sr)]
        ramp = np.linspace(0.0, 1.0, nx)
        a[-nx:] = a[-nx:] * (1.0 - ramp) + tail[:nx] * ramp
        x = np.concatenate([a, tail[nx:]])
        held = (len(a) + int(0.4 * sr) - nx) / sr
        y, sr2 = render(prog, key, held)
        j = speaks(y, sr2)
        y = y[j:j + int(len(x) * sr2 / sr)]
        if sr2 != sr:
            y = resample_poly(y, sr, sr2)
        y = y * np.sqrt(np.mean(x[int(0.3 * sr):int(1.8 * sr)] ** 2) / np.mean(y[int(0.3 * sr):int(1.8 * sr)] ** 2))
        gap = np.zeros(int(0.35 * sr))
        parts += [x, gap, y, gap, gap]
        print("  %s key %d" % (os.path.basename(p), key))
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


def main(argv):
    spec = next((a.split("=", 1)[1] for a in argv if a.startswith("--inharm=")), None)
    if spec:
        return inharm(spec) or 0
    voice = next((a.split("=")[1] for a in argv if a.startswith("--voice=")), "recorder")
    prog, cls = use_class(voice)
    fitarg = next((a for a in argv if a.startswith("--fit")), None)
    if fitarg == "--fit=breath":
        fit_breath(voice, prog, cls)
        fitarg = None
    elif fitarg == "--fit=wobble":
        fit_wobble(voice, prog, cls)
        return 0
    elif fitarg == "--fit=skirt":
        fit_skirt(voice, prog, cls)
        return 0
    if fitarg:
        knobs = SPECTRUM
        if "=" in fitarg:
            knobs = tuple(fitarg.split("=")[1].split(","))
        e, v = fit(voice, prog, cls, knobs)
        print("  fitted %.2f dB:" % e)
        for k, q in zip(knobs, v):
            print("    %s = %.4g" % (k, q))
    if "--turb" in argv:
        return turb_report(voice, prog) or 0
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--ab=")), None)
    if out:
        return ab(voice, prog, out) or 0
    report(voice, prog)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
