#!/usr/bin/env python3
"""Fit a sustained wind voice -- the recorder (GM 74), the ocarina (GM 79), the
harmonica (GM 22) --
to VCSL's sustains (CC0; ~/Documents/refs/vcsl/{recorder,ocarina,harmonica}, sources.md),
and the pan flute, blown bottle, shakuhachi and whistle (GM 75-78) to Freesound
takes' stable notes (examples/freesound_slice.py pipes; VOICE_OPTS).

    wind_fit.py --voice=recorder              measure: recorded against ours
    wind_fit.py --voice=recorder --fit        fit the spectrum knobs
    wind_fit.py --voice=ocarina --fit=breath  fit sustain_jitter to the breath
    wind_fit.py --voice=harmonica --top       the ladder by absolute frequency, to 20 kHz
    wind_fit.py --voice=harmonica --fit=scatter  each reed's own ladder, to the roughness
    wind_fit.py --voice=accordion --fit=push   the bellows' push on a note from silence
    wind_fit.py --voice=bandoneon --fit=speech how fast a note speaks (a grid)
    wind_fit.py --voice=bandoneon --fit=bloom  ...harmonic by harmonic, by register
    wind_fit.py --voice=bandoneon --fit=top:reed_spread,reed_spread_per_octave
                                              knobs to the harmonics by band to 11 kHz
    wind_fit.py --voice=bagpipe --fit=body     body_trim_db, the harmonics by where they sound
    (and the harmonium, GM 20, --voice=reedorgan; the shanai, GM 111)
    wind_fit.py --voice=shakuhachi --fit=tables [--keys=57-62] [--match=uncle] [--low] [--breath]
                                              the series and breath tables, note by note

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
    # GM 22: Hohner's Special 20 in C and in F (diatonic) and the Super 64
    # (chromatic), Normal sustains -- a free reed, named an octave low too.
    "harmonica": (22, "HarmonicaProperties", "harmonica", "*.wav"),
    # GM 75-78: Freesound takes (sources.md "Pipes"), their STABLE notes cut and
    # named by sounding pitch by examples/freesound_slice.py pipes
    "panflute": (75, "PanFluteProperties", "panflute", "*.wav"),
    "bottle": (76, "BlownBottleProperties", "bottle", "*.wav"),
    "shakuhachi": (77, "ShakuhachiProperties", "shakuhachi", "*.wav"),
    "whistle": (78, "WhistleProperties", "whistle", "*.wav"),
    # GM 109: IowaSpaceWizard's Highland chanter, its nine notes alone (the
    # drones corked), staged by examples/freesound_slice.py bagpipe
    "bagpipe": (109, "BagpipeProperties", "bagpipe", "*_iowa_*.wav"),
    # GM 111: cdrk's Turkish zurna standing in for the shehnai (no open-licence
    # shehnai found), its stable notes staged by examples/freesound_slice.py
    # pipes shanai -- G4 and a flat E5, eight notes in all
    "shanai": (111, "ShanaiProperties", "shanai", "*_cdrk_*.wav"),
    "hichiriki": (111, "HichirikiProperties", "hichiriki", "*_gaijin_*.wav"),
    "pungi": (111, "PungiProperties", "pungi", "*_bk_*.wav"),
    "kawala": (75, "KawalaProperties", "kawala", "*.wav"),
    # GM 20: donyaquick's harmonium, its 32 keys G2-D5 held 7-12 s (CC0),
    # staged by examples/freesound_slice.py harmonium
    "reedorgan": (20, "ReedOrganFreeProperties", "reedorgan", "*_donya_*.wav"),
    # GM 21: hammondman's Hohner on musette, 15 keys A3-E6 (CC0), staged by
    # examples/freesound_slice.py accordion
    "accordion": (21, "AccordionProperties", "accordion", "*_hwav_*.wav"),
    # GM 23: Joerg Bleymehl's bandoneon_v2 SoundFont, a 1930 ELA, its 12 notes
    # C2-F6 written out by examples/sf2_extract.py (measured only)
    "bandoneon": (23, "TangoAccordionProperties", "bleymehl_wav", "*_bley_*.wav"),
}
# WHERE A VOICE'S NOTES ARE, how they are named and how long they hold: VCSL's
# are an octave low and sustained for seconds; the staged Freesound notes are
# named as they sound and many are short -- a scale's, a melody's -- so each is
# measured over a window its notes have (a note shorter than it is measured
# over what it has)
VOICE_OPTS = {
    "panflute": dict(refs="~/Documents/refs/freesound/staged", octave=0, t0=0.15, t1=0.6),
    "bottle": dict(refs="~/Documents/refs/freesound/staged", octave=0, t0=0.4, t1=1.9),
    "shakuhachi": dict(refs="~/Documents/refs/freesound/staged", octave=0, t0=0.15, t1=0.7),
    # the kaval's and the ney's held notes, 0.25 s and more: read early
    "kawala": dict(refs="~/Documents/refs/freesound/staged", octave=0, t0=0.05, t1=0.25),
    "whistle": dict(refs="~/Documents/refs/freesound/staged", octave=0, t0=0.08, t1=0.25),
    # THE CHANTER IS AT ITS OWN PITCH: Low A 487.27 Hz, 176.7 cents over A=440.
    # Its files are named by the note that plays each degree, and ours are
    # rendered there under a static bend of as much (a tuning, which every
    # voice honours, the drones following) -- so the two sound at the same
    # Hz and a bore's or a reed's colour lines up where it is. CC1 0 corks
    # the drones: the takes are the chanter alone
    # THE HARMONIUM IS AT ITS OWN PITCH, ~9 cents sharp of A440 (every key):
    # rendered there, as the chanter is
    # ...AND IT PLAYS AN 8' AND A 4' TOGETHER (the even harmonics beat): ours
    # with registers 1 and 3 drawn in both halves, stop word 85 on CC43
    "reedorgan": dict(refs="~/Documents/refs/freesound/staged", octave=0, t0=0.5, t1=4.0,
                      tonic_cents=9.0, ccs=((43, 85), (44, 0))),
    # the musette's keys hold 1.4-2.3 s, ~8 cents sharp of A440
    "accordion": dict(refs="~/Documents/refs/freesound/staged", octave=0, t0=0.25, t1=1.2,
                      tonic_cents=8.0),
    # the bandoneon's notes hold 1.6-3 s, ~10.5 cents sharp of A440 (A=443)
    "bandoneon": dict(refs="~/Documents/refs/bandoneon", octave=0, t0=0.3, t1=1.4,
                      tonic_cents=10.5),
    # the zurna's notes are short: its E5s hold 0.4 s, its G4s 0.85
    "shanai": dict(refs="~/Documents/refs/freesound/staged", octave=0, t0=0.1, t1=0.38),
    # the hichiriki's held notes, 2-4 s (the sho under it, steady, between)
    "hichiriki": dict(refs="~/Documents/refs/freesound/staged", octave=0, t0=0.3, t1=1.8),
    "bagpipe": dict(refs="~/Documents/refs/freesound/staged", octave=0, t0=0.5, t1=3.5,
                    tonic_cents=176.7, cc1=0),
}
TONIC_CENTS = 0.0
CC1 = None
CCS = ()          # (cc, value) sent before the note: a registration (VOICE_OPTS ccs)
T0, T1 = 0.4, 1.9
VEL = 80
NH = 12
E3 = 2 ** np.arange(np.log2(45), np.log2(16000), 1 / 3.0)


def recordings(voice):
    _, _, d, pat = VOICES[voice]
    o = VOICE_OPTS.get(voice, {})
    refs = os.path.expanduser(o.get("refs", REFS))
    shift = 12 * o.get("octave", 1)
    out = []
    for p in sorted(glob.glob(os.path.join(refs, d, pat))):
        n = V.note_of(p)
        if n is not None:
            out.append((n + shift, p))
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
    f = 440.0 * 2 ** ((key - 69) / 12.0 + TONIC_CENTS / 1200.0)
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
    if TONIC_CENTS:
        t.append(mido.Message("pitchwheel", channel=0, pitch=int(round(TONIC_CENTS / 200.0 * 8191)), time=0))
    if CC1 is not None:
        t.append(mido.Message("control_change", channel=0, control=1, value=CC1, time=0))
    for _cc, _v in CCS:
        t.append(mido.Message("control_change", channel=0, control=_cc, value=_v, time=0))
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
    # The breath is reported, not fitted here: it has its own fit (fit_breath),
    # and a voice with none yet is 100 dB off, which would swamp the spectrum.
    e = float(np.sqrt(np.mean(np.square(out["ladder"] + out["thirds"]))))
    return (e, rms) if parts else e


def getk(cls, k):
    """A knob: an attribute, or an element of a tuple one by dotted index
    (formants.1.2 is the second formant's gain)."""
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


BOUNDS = {"reed_spread_per_octave": (-0.3, 0.3), "reed_gate": (-0.6, 1.08), "reed_gate_per_octave": (-0.6, 0.6), "reed_edge": (0.003, 0.5), "reed_spread": (0.02, 0.4),
          "bore_corner_hz": (2000.0, 20000.0), "formants.1.2": (0.05, 2.5), "formants.0.2": (0.05, 6.0),
          "formant_floor": (0.05, 1.0), "formants.1.0": (1000.0, 8000.0), "reed_direct": (0.001, 1.0)}


def fit(voice, prog, cls, knobs, maxfev=150):
    from scipy.optimize import minimize
    refs = []
    for key, p in recordings(voice):
        x, sr = load(p)
        refs.append((key, analyse(x, sr, key)))
    # dB knobs (even_harmonic_db) move additively, 10 dB a unit; the rest in log.
    db = np.array([k.endswith("_db") or "_db_" in k or k.endswith("_per_octave") for k in knobs])
    step = np.array([10.0 if "_db" in k else 0.5 for k in knobs])     # dB, or a gate
    start = {"even_harmonic_db": -6.0, "chiff_bandwidth": 0.5, "even_harmonic_db_per_octave": 0.0,
             "reed_gate_per_octave": 0.0}
    x0 = np.array([float(getk(cls, k) if getk(cls, k) is not None else start[k]) for k in knobs])
    best = [1e9, x0]

    def val(z):
        return np.where(db, x0 + step * z, np.exp(z) * x0)

    def f(z):
        v = val(z)
        for k, q in zip(knobs, v):
            setk(cls, k, float(q))
        # Outside its physical range a knob is a bad fit, not a solution: free,
        # the harmonica's fit switched its case off (360 kHz) and made a +18 dB
        # formant at 7 kHz do the reed's work. And a geometry that silences
        # the voice (a reed gate past ~1.1: the tongue never clears its slot)
        # is a bad fit, not a crash.
        if any(k in BOUNDS and not BOUNDS[k][0] <= q <= BOUNDS[k][1] for k, q in zip(knobs, v)):
            return 1e3
        try:
            ours = [analyse(*render(prog, key), key) for key, _ in refs]
        except (IndexError, ValueError, TypeError):
            return 1e3
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
        setk(cls, k, float(q))
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


def ab(voice, prog, out, n=7, head=2.0, xf=0.1, keys=None):
    """--ab=OUT.wav: each recording, then ours at the same pitch, matched in
    level -- every n-th note across the compass. A recording sustains 6-20 s,
    so it is its first HEAD seconds spliced (an XF crossfade, inside its
    steady sustain) to its own release and tail: the ending is the real one,
    not a cut. Ours is held as long and released, its tail kept as long."""
    import wave
    from scipy.signal import resample_poly
    recs = sorted(recordings(voice))
    pick = ([r for r in recs if r[0] in keys] if keys else
            [recs[int(i)] for i in np.linspace(0, len(recs) - 1, n)])
    parts, sr = [], 44100
    for key, p in pick:
        x, sr = load(p)
        i = speaks(x, sr)
        if len(x) - i < int((head + 0.6) * sr):
            # A SHORT NOTE (a staged melody's, a scale's): played whole, and
            # ours held as long -- there is no sustain to splice
            x = x[i:]
            y, sr2 = render(prog, key, len(x) / sr)
            j = speaks(y, sr2)
            y = y[j:j + int((len(x) / sr + 0.4) * sr2)]
            if sr2 != sr:
                y = resample_poly(y, sr, sr2)
            m = min(len(x), len(y))
            y = y * np.sqrt(np.mean(x[:m] ** 2) / max(np.mean(y[:m] ** 2), 1e-30))
            gap = np.zeros(int(0.35 * sr))
            parts += [x, gap, y, gap, gap]
            print("  %s key %d (whole)" % (os.path.basename(p), key))
            continue
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


def turbulence(x, sr, key, t0=0.5, t1=4.0, nh=6, hop=0.01):
    """Each harmonic's level over the sustain: its wobble (dB rms, after a
    0.5 s running mean takes the player's swell out), the wobble's rate
    (median frequency of its modulation spectrum, Hz), and how the harmonics
    move together (mean correlation of h1's wobble with each of h2..). And the
    breath's colour: the spectrum midway between harmonics, third-octave
    bands, dB re the fundamental."""
    i = speaks(x, sr)
    seg = x[i + int(t0 * sr): i + int(t1 * sr)]
    if len(seg) < int(1.5 * sr):
        return None
    f0 = f0_near(seg[:int(1.0 * sr)], sr, key)
    win = int(0.04 * sr)
    h = int(hop * sr)
    w = np.hanning(win)
    fr = np.fft.rfftfreq(win * 4, 1.0 / sr)
    env = []
    for a in range(0, len(seg) - win, h):
        X = np.abs(np.fft.rfft(seg[a:a + win] * w, win * 4))
        env.append([X[np.argmin(np.abs(fr - m * f0))] for m in range(1, nh + 1)])
    env = 20 * np.log10(np.array(env) + 1e-12)
    k = int(0.5 / hop)
    smooth = np.array([np.convolve(c, np.ones(k) / k, "same") for c in env.T]).T
    d = (env - smooth)[k:-k]
    lvl = env.mean(0) - env.mean(0)[0]
    rms = d.std(0)
    rate = []
    for c in d.T:
        P = np.abs(np.fft.rfft(c * np.hanning(len(c)))) ** 2
        f = np.fft.rfftfreq(len(c), hop)
        cs = np.cumsum(P[1:])
        rate.append(f[1:][np.searchsorted(cs, cs[-1] / 2)])
    corr = [np.corrcoef(d[:, 0], d[:, j])[0, 1] for j in range(1, nh)]
    # THE SHARED PART: the mean wobble of h1-h4 (what the harmonics do
    # together -- the breath's pressure), and the BREATH NOISE's own level:
    # each frame's median between the harmonics, 1-5 kHz, its wobble and its
    # correlation with the shared part. And the fundamental's pitch, cents.
    com = d[:, :4].mean(1)
    mids, pitch = [], []
    for a in range(0, len(seg) - win, h):
        X = np.abs(np.fft.rfft(seg[a:a + win] * w, win * 4))
        ph = (fr / f0) % 1.0
        sel = (ph > 0.3) & (ph < 0.7) & (fr > 1000) & (fr < 5000)
        mids.append(20 * np.log10(np.median(X[sel]) + 1e-12))
        k1 = int(np.argmin(np.abs(fr - f0)))
        y0, y1, y2 = np.log(X[k1 - 1:k1 + 2] + 1e-30)
        dd = y0 - 2 * y1 + y2
        pitch.append(1200 * np.log2((k1 + (0.5 * (y0 - y2) / dd if dd else 0)) * (fr[1]) / f0))
    mids, pitch = np.array(mids), np.array(pitch)
    nz = mids - np.convolve(mids, np.ones(k) / k, "same")
    pz = pitch - np.convolve(pitch, np.ones(k) / k, "same")
    nz, pz = nz[k:-k], pz[k:-k]

    def _rate(c):
        P = np.abs(np.fft.rfft(c * np.hanning(len(c)))) ** 2
        f = np.fft.rfftfreq(len(c), hop)
        cs = np.cumsum(P[1:])
        return f[1:][np.searchsorted(cs, cs[-1] / 2)]
    shared = np.array([com.std(), _rate(com), nz.std(), _rate(nz), np.corrcoef(com, nz)[0, 1],
                       pz.std(), np.corrcoef(com, pz)[0, 1]])
    N = 1 << 19
    seg2 = seg[:int(1.5 * sr)]
    X = np.abs(np.fft.rfft(seg2 * np.hanning(len(seg2)), N)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    ph = (f / f0) % 1.0
    mid = (ph > 0.3) & (ph < 0.7) & (f > 0.5 * f0)
    ref = X[np.argmin(np.abs(f - f0))]
    col = []
    for lo, hi in zip(E3[:-1], E3[1:]):
        m = mid & (f >= lo) & (f < hi)
        col.append(10 * np.log10(np.median(X[m]) / ref + 1e-30) if m.sum() > 4 else np.nan)
    return dict(lvl=lvl, rms=rms, rate=np.array(rate), corr=np.array(corr), colour=np.array(col),
                shared=shared)


def turb_report(voice, prog):
    rec, ours = [], []
    for key, p in recordings(voice):
        x, sr = load(p)
        r = turbulence(x, sr, key)
        if r is None:
            continue
        y, sr2 = render(prog, key, 4.5)
        rec.append(r)
        ours.append(turbulence(y, sr2, key))
    for fld, lab in (("lvl", "level dB"), ("rms", "wobble dB rms"), ("rate", "wobble rate Hz"), ("corr", "corr with h1")):
        for name, rows in (("recorded", rec), ("ours", ours)):
            print("  %-15s %-9s " % (lab, name) + " ".join("%6.2f" % v for v in table(rows, fld, 6)))
    print("  shared:         tone dB, Hz | breath dB, Hz, corr w/ tone | pitch cents, corr w/ tone")
    for name, rows in (("recorded", rec), ("ours", ours)):
        print("  %-15s " % name + " ".join("%6.2f" % v for v in table(rows, "shared", 7)))
    cen = np.sqrt(E3[:-1] * E3[1:])
    sel = [i for i, c in enumerate(cen) if 300 < c < 16000][::2]
    print("  breath colour (midway, dB re h1) at " + " ".join("%6d" % cen[i] for i in sel))
    for name, rows in (("recorded", rec), ("ours", ours)):
        m = table(rows, "colour", len(cen))
        print("  %-36s" % name + " ".join("%6.1f" % m[i] for i in sel))


CEN = np.sqrt(E3[:-1] * E3[1:])


PUSH = ("bellows_push_gain", "bellows_push_rise_s", "bellows_push_dbs", "bellows_push_tilt",
        "bellows_push_tilt_per_octave")
PUSH_T = (0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5)


def push_shape(x, sr, key):
    """A note's onset against its steady level (0.6-1.0 s after it speaks):
    the level, dB, at PUSH_T; and how much brighter it is at its loudest in the
    first 0.4 s -- h3-h8's power over h1's, dB re the same at 0.8 s."""
    w = int(0.01 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
    a = int(np.flatnonzero(e > e.max() * 0.03)[0])
    st = np.median(e[a + int(0.6 * sr):a + int(1.0 * sr)])
    lv = np.array([20 * np.log10(e[a + int(t * sr)] / st + 1e-9) for t in PUSH_T])
    pk = int(np.argmax(e[a:a + int(0.4 * sr)]))
    f0 = 440.0 * 2 ** ((key - 69) / 12.0 + TONIC_CENTS / 1200.0)
    win = int(0.04 * sr)
    fr = np.fft.rfftfreq(win * 4, 1.0 / sr)

    def tilt(i):
        X = np.abs(np.fft.rfft(x[i:i + win] * np.hanning(win), win * 4))
        hs = [X[np.abs(fr - k * f0) < 0.2 * f0].max() for k in range(1, 9)]
        return 10 * np.log10(sum(h * h for h in hs[2:]) / hs[0] ** 2)
    return lv, tilt(a + pk) - tilt(a + int(0.8 * sr))


SPEECH_W = ((0.0, 0.03), (0.03, 0.06), (0.06, 0.12))


def onset_db(x, sr):
    """The note's level in SPEECH_W after it starts (first within 26 dB of
    its peak), dB re its steady level 0.8-1.2 s in."""
    a = int(np.flatnonzero(np.abs(x) > 0.05 * np.abs(x).max())[0])
    st = 10 * np.log10(np.mean(x[a + int(0.8 * sr):a + int(1.2 * sr)] ** 2) + 1e-20)
    return np.array([10 * np.log10(np.mean(x[a + int(p * sr):a + int(q * sr)] ** 2) + 1e-20) - st
                     for p, q in SPEECH_W])


def fit_speech(voice, prog, cls):
    """--fit=speech: how fast a note speaks -- attack_time (s) plus
    speech_cycles of the fundamental (FreeReedProperties) -- by a grid against
    each key's level over its first 120 ms (SPEECH_W, re its steady level),
    with the push fitted as it stands. The rms over keys and windows."""
    refs = [(key, onset_db(*load(p))) for key, p in recordings(voice)]
    best = None
    for at in (0.008, 0.015, 0.025, 0.035, 0.05):
        for sc in (0.0, 3.0, 6.0, 10.0):
            cls.attack_time, cls.speech_cycles = at, sc
            d = np.array([onset_db(*render(prog, key, 1.6)) - r for key, r in refs])
            e = float(np.sqrt(np.mean(d ** 2)))
            print("  attack_time %.3f speech_cycles %4.1f: %.2f dB  (by window %s)" % (
                at, sc, e, " ".join("%+.1f" % v for v in np.median(d, 0))), flush=True)
            if best is None or e < best[0]:
                best = (e, at, sc)
    print("    attack_time = %.3f\n    speech_cycles = %.1f   (%.2f dB)" % (best[1], best[2], best[0]))


TOP_E = (500, 1000, 2000, 3000, 4000, 6000, 8000, 11000)


def top_bands(x, sr, f0, t0=0.4, t1=1.3):
    """The HARMONICS' share of the note's energy in TOP_E's bands, dB, over
    t0-t1 s after it speaks -- by absolute frequency, so a bass note's h50-h120
    are read where a ladder to h12 stops at 0.8 kHz."""
    a = speaks(x, sr)
    seg = x[a + int(t0 * sr):a + int(t1 * sr)]
    N = 1 << 18
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    h = np.zeros_like(f, bool)
    for m in range(1, int(0.45 * sr / f0)):
        h |= np.abs(f - m * f0) < 0.12 * f0
    tot = X.sum()
    return np.array([10 * np.log10(X[(f >= lo) & (f < hi) & h].sum() / tot + 1e-30)
                     for lo, hi in zip(TOP_E[:-1], TOP_E[1:])])


def fit_top(voice, prog, cls, knobs, maxfev=80):
    """--fit=top:KNOB,...: those knobs against every note's top_bands (rms of
    recorded - ours over notes and bands). The bandoneon's bass is bright to
    8 kHz where its treble is not (Ben: "the low notes need some more
    harmonics ... a reed brightness"): reed_spread and its slope an octave."""
    from scipy.optimize import minimize
    tc = 2 ** (TONIC_CENTS / 1200.0)
    refs = [(key, top_bands(*load(p), 440.0 * 2 ** ((key - 69) / 12.0) * tc)) for key, p in recordings(voice)]
    x0 = np.array([float(getk(cls, k)) for k in knobs])
    lin = np.array([k.endswith("_per_octave") or k.endswith("_db") for k in knobs])
    best = [1e9, x0]

    def val(z):
        return np.where(lin, x0 + 0.05 * z, x0 * np.exp(z))

    def f(z):
        v = val(z)
        if any(k in BOUNDS and not BOUNDS[k][0] <= q <= BOUNDS[k][1] for k, q in zip(knobs, v)):
            return 1e3
        for k, q in zip(knobs, v):
            setk(cls, k, float(q))
        d = np.array([r - top_bands(*render(prog, key, 1.6), 440.0 * 2 ** ((key - 69) / 12.0) * tc)
                      for key, r in refs])
        e = float(np.sqrt(np.mean(d ** 2)))
        if e < best[0]:
            best[:] = [e, v]
            print("  %.2f dB  %s   by note %s" % (e, " ".join("%s=%.4g" % kv for kv in zip(knobs, v)),
                  " ".join("%d:%+.0f" % (k, m) for (k, _), m in zip(refs, d.mean(1)))), flush=True)
        return e
    minimize(f, np.zeros(len(knobs)), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": np.vstack([np.zeros(len(knobs)), 0.5 * np.eye(len(knobs))]),
                      "xatol": 0.02, "fatol": 0.02})
    for k, q in zip(knobs, best[1]):
        setk(cls, k, float(q))
        print("    %s = %.4g" % (k, q))


BLOOM_H = (0, 1, 2, 3, 4, 6, 8)        # 0: the whole note


def rise_times(x, sr, f0):
    """Each of BLOOM_H's time (s) to come within 6 and within 1 dB of its
    steady level (0.8-1.2 s in), from the note's start; NaN for a harmonic
    30 dB under the strongest (too weak to time)."""
    from scipy.signal import butter, sosfiltfilt, hilbert
    a = int(np.flatnonzero(np.abs(x) > 0.02 * np.abs(x).max())[0])
    out, lv = [], []
    for h in BLOOM_H:
        if h * f0 > 0.4 * sr:
            out.append((np.nan, np.nan)); lv.append(-200.0)
            continue
        y = x if h == 0 else sosfiltfilt(butter(2, [h * f0 * 0.96, h * f0 * 1.04], btype="band", fs=sr, output="sos"), x)
        e = np.abs(hilbert(y))
        w = int(0.01 * sr)
        e = np.convolve(e, np.ones(w) / w, "same")
        st = np.median(e[a + int(0.8 * sr):a + int(1.2 * sr)])
        lv.append(20 * np.log10(st + 1e-20))
        out.append(tuple(np.flatnonzero(e[a:] > st * 10 ** (-db / 20.0))[0] / sr for db in (6.0, 1.0)))
    out = np.array(out, float)
    out[np.array(lv) < max(lv) - 30.0] = np.nan
    return out


def fit_bloom(voice, prog, cls, maxfev=60):
    """--fit=bloom: how a note speaks, harmonic by harmonic -- attack_time,
    speech_cycles, speech_harmonic_exp and its slope an octave
    (speech_harmonic_exp_per_octave) -- against each key's BLOOM_H rise times
    (rise_times; 0 the whole note, counted twice), the error the rms of
    log2(ours / recorded), times floored at 5 ms. The per-harmonic times
    scatter note to note, and Nelder-Mead settles anywhere near 1.06-1.14
    octaves: the bandoneon's values were read off C2, F2 and C3 by hand and
    this scored them (the bass 1.30 -> 1.01). A bandoneon's bass reed has its fundamental at once and its
    upper harmonics 4-6 times later; its treble all together (Ben: "a much
    softer attack ... more like a pressure swell")."""
    from scipy.optimize import minimize
    import warnings
    warnings.simplefilter("ignore")
    tc = 2 ** (TONIC_CENTS / 1200.0)
    refs = [(key, rise_times(*load(p), 440.0 * 2 ** ((key - 69) / 12.0) * tc)) for key, p in recordings(voice)]
    K = ("attack_time", "speech_cycles", "speech_harmonic_exp", "speech_harmonic_exp_per_octave")
    x0 = np.array([float(getattr(cls, k)) for k in K])
    lin = np.array([False, False, True, True])
    best = [1e9, x0]

    def val(z):
        return np.where(lin, x0 + 0.3 * z, x0 * np.exp(z))

    def f(z):
        v = val(z)
        for k, q in zip(K, v):
            setattr(cls, k, float(q))
        d = []
        for key, r in refs:
            y, sr = render(prog, key, 1.6)
            o = rise_times(y, sr, 440.0 * 2 ** ((key - 69) / 12.0) * tc)
            ok = np.isfinite(r) & np.isfinite(o)
            dd = np.log2(np.maximum(o, 0.005) / np.maximum(r, 0.005))
            d.extend(dd[ok])
            d.extend(dd[0][ok[0]])      # the whole note twice: what the ear calls the attack
        e = float(np.sqrt(np.mean(np.square(d))))
        if e < best[0]:
            best[:] = [e, v]
            print("  %.3f octaves  %s" % (e, " ".join("%s=%.4g" % kv for kv in zip(K, v))), flush=True)
        return e
    minimize(f, np.zeros(len(K)), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": np.vstack([np.zeros(len(K)), 0.5 * np.eye(len(K))]),
                      "xatol": 0.02, "fatol": 0.005})
    for k, q in zip(K, best[1]):
        print("    %s = %.4g" % (k, q))


def fit_push(voice, prog, cls, maxfev=80, hold=()):
    """--fit=push: the bellows' push (tonelib.bellows_push_weight) -- its
    gain, rise, decay and tilt with its slope up the keyboard -- against each
    key's onset: its level at PUSH_T re its steady level, and how much
    brighter it is at its peak (push_shape). The error: the level's rms, key
    by key, and the brightening's TREND -- its line against octave, at A4 and
    its slope -- not key by key: a musette's harmonics beat 12-19 dB, so one
    40 ms window at the peak scatters 5-7 dB even on this model, which has no
    randomness in it. --hold=NAME,... keeps those knobs where the class has
    them (the bandoneon's decay: free, a slow sag carried the push's extra
    brightness into the steady tone the spectrum is fitted on)."""
    from scipy.optimize import minimize
    import warnings
    warnings.simplefilter("ignore")
    PUSH = tuple(k for k in globals()["PUSH"] if k not in hold)
    refs = [(key, push_shape(*load(p), key)) for key, p in recordings(voice)]
    x0 = np.array([float(getattr(cls, k)) for k in PUSH])
    lin = np.array([k.startswith("bellows_push_tilt") for k in PUSH])
    best = [1e9, x0]

    def val(z):
        return np.where(lin, x0 + 0.3 * z, x0 * np.exp(z))

    def f(z):
        v = val(z)
        for k, q in zip(PUSH, v):
            setattr(cls, k, float(q))
        el, ob_ = [], []
        for key, (lv, bt) in refs:
            y, sr = render(prog, key, 1.6)
            ol, ob = push_shape(y, sr, key)
            el.extend(ol - lv)
            ob_.append(ob)
        oc = np.array([(k - 69) / 12.0 for k, _ in refs])
        rb = np.polyfit(oc, [b for _, (_, b) in refs], 1)
        obf = np.polyfit(oc, ob_, 1)
        eb = [obf[1] - rb[1], obf[0] - rb[0]]       # at A4, and an octave's change
        e = float(np.sqrt(np.mean(np.square(el)) + 0.25 * np.mean(np.square(eb))))
        if e < best[0]:
            best[:] = [e, v]
            print("  %5.2f (level %.2f dB, brightening %.2f dB)  %s" % (
                e, np.sqrt(np.mean(np.square(el))), np.sqrt(np.mean(np.square(eb))),
                " ".join("%s=%.4g" % (k[13:], q) for k, q in zip(PUSH, v))), flush=True)
        return e
    minimize(f, np.zeros(len(PUSH)), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": np.vstack([np.zeros(len(PUSH)), 0.4 * np.eye(len(PUSH))]),
                      "xatol": 0.02, "fatol": 0.02})
    for k, q in zip(PUSH, best[1]):
        print("    %s = %.4g" % (k, q))


def fit_breath(voice, prog, cls, passes=4, step=2):
    """--fit=breath: breath_noise_db, band by band, toward the recordings'
    breath colour (the spectrum midway between harmonics, dB re h1, mean over
    the notes): each pass adds recorded - ours to every band both measure;
    a band no note measures (under the lowest fundamental) takes its
    neighbour's. Every STEP-th note."""
    refs = []
    for key, p in recordings(voice)[::step]:
        x, sr = load(p)
        r = turbulence(x, sr, key)
        if r is not None:
            refs.append((key, r))
    rec = table([r for _, r in refs], "colour", len(CEN))
    keep = [i for i, c in enumerate(CEN) if 150 < c < 18000]
    if not cls.breath_noise_db:
        cls.breath_noise_db = tuple((int(round(CEN[i])), 0.0) for i in keep)
    tab = dict(cls.breath_noise_db)
    for n in range(passes + 1):
        ours = table([turbulence(*render(prog, key, 2.4), key) for key, _ in refs], "colour", len(CEN))
        d = rec - ours
        ok = [i for i in keep if np.isfinite(d[i])]
        print("  pass %d: breath colour rec - ours, rms %.1f dB" % (n, np.sqrt(np.mean(d[ok] ** 2))), flush=True)
        if n == passes:
            break
        for i in keep:
            j = i if np.isfinite(d[i]) else min(ok, key=lambda q: abs(q - i))
            hz = int(round(CEN[i]))
            tab[hz] = tab.get(hz, 0.0) + float(d[j])
        cls.breath_noise_db = tuple((hz, round(db, 1)) for hz, db in sorted(tab.items()))
    print("    breath_noise_db = %s" % (cls.breath_noise_db,))
    print("  " + "  ".join("%d %+.0f/%+.0f" % (CEN[i], rec[i], ours[i]) for i in keep[::2]))


SKIRT = ("wind_skirt_db", "wind_skirt_harmonic_db", "wind_skirt_hz", "wind_skirt_rel")


def spectra(x, sr, key, nh):
    """--fit=tables' measurement, over the note's window (T0-T1, or what a short
    note has): each harmonic's peak to NH, and the breath by third-octave band
    -- the median between the harmonics, and UNDER the fundamental too (a high
    whistle's breath is mostly there, where the gaps never look) -- all dB re
    the fundamental's peak."""
    i = speaks(x, sr)
    seg = x[i + int(T0 * sr): i + int(T1 * sr)]
    seg = seg - seg.mean()
    f0 = f0_near(seg, sr, key)
    N = 1 << 18
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    h = []
    for m in range(1, nh + 1):
        b = (f > m * f0 * 0.97) & (f < m * f0 * 1.03)
        h.append(X[b].max() if b.any() and m * f0 < 0.45 * sr else np.nan)
    h = np.array(h)
    ph = (f / f0) % 1.0
    gap = (((ph > 0.3) & (ph < 0.7)) | (f < 0.7 * f0)) & (f > 100)
    col = []
    for lo, hi in zip(E3[:-1], E3[1:]):
        m = gap & (f >= lo) & (f < hi) & (f < 0.45 * sr)
        col.append(10 * np.log10(np.median(X[m]) / h[0] + 1e-30) if m.sum() > 4 else np.nan)
    return 10 * np.log10(h / h[0] + 1e-30), np.array(col)


def fit_tables(voice, prog, cls, argv, passes=3):
    """--fit=tables [--keys=LO-HI] [--match=TEXT] [--low]: the series and the
    breath together, note by note at full length, as TABLES -- mode_gains (to
    max_harmonic) and breath_noise_db -- each pass adding recorded - ours (the
    notes' median) to every harmonic and band; --nh=N to hN, the table grown
    (max_harmonic must let it sound). --keys and --match take a part
    of the notes (one player's, one register's); --low fits that part into
    mode_gains_low / breath_noise_low_db instead (register_low_hz sends those
    notes there). --breath fits the breath table alone, the series left to
    --fit=body (a short take's two pitches cannot tell a formant from a
    series)."""
    breath_only = "--breath" in argv
    keys = next((a.split("=")[1] for a in argv if a.startswith("--keys=")), None)
    match = next((a.split("=")[1] for a in argv if a.startswith("--match=")), None)
    low = "--low" in argv
    picked = []
    for key, p in recordings(voice):
        if keys and not int(keys.split("-")[0]) <= key <= int(keys.split("-")[1]):
            continue
        if match and match not in os.path.basename(p):
            continue
        picked.append((key, p))
    nh = int(next((a.split("=")[1] for a in argv if a.startswith("--nh=")), cls.max_harmonic))
    import warnings
    warnings.simplefilter("ignore")
    rec = [spectra(*load(p), key, nh) for key, p in picked]
    lens = [len(load(p)[0]) / load(p)[1] for _, p in picked]
    R_h, R_c = np.nanmedian([r[0] for r in rec], 0), np.nanmedian([r[1] for r in rec], 0)
    gname, bname = ("mode_gains_low", "breath_noise_low_db") if low else ("mode_gains", "breath_noise_db")
    if getattr(cls, gname) is None and not breath_only:
        setattr(cls, gname, tuple(cls.mode_gains))
    if not getattr(cls, bname):
        setattr(cls, bname, tuple(cls.breath_noise_db))
    print("  %d notes: %s" % (len(picked), " ".join(os.path.basename(p)[:-4] for _, p in picked)))
    for n in range(passes + 1):
        ours = [spectra(*render(prog, key, max(L, T1 + 0.5)), key, nh) for (key, _), L in zip(picked, lens)]
        O_h, O_c = np.nanmedian([o[0] for o in ours], 0), np.nanmedian([o[1] for o in ours], 0)
        dh, dc = R_h - O_h, R_c - O_c
        tab = dict(getattr(cls, bname))
        bands = [i for i, c in enumerate(CEN) if int(round(c)) in tab]
        ok = [i for i in bands if np.isfinite(dc[i])]
        print("  pass %d: series rec - ours rms %.1f dB (h2-h%d), breath %.1f dB (%d bands)"
              % (n, np.sqrt(np.nanmean(dh[1:] ** 2)), nh, np.sqrt(np.mean(dc[ok] ** 2)), len(ok)), flush=True)
        if n == passes:
            break
        if not breath_only:
            g = list(getattr(cls, gname))
            g += [g[-1]] * (nh - len(g))         # a longer series starts level with its last
            for m in range(1, nh):
                if np.isfinite(dh[m]):
                    g[m] = g[m] * 10 ** (dh[m] / 20.0)
            setattr(cls, gname, tuple(g))
        for i in bands:
            j = i if np.isfinite(dc[i]) else min(ok, key=lambda q: abs(q - i))
            hz = int(round(CEN[i]))
            tab[hz] += float(dc[j])
        setattr(cls, bname, tuple((hz, round(db, 1)) for hz, db in sorted(tab.items())))
    if not breath_only:
        print("    %s = (%s)" % (gname, ", ".join("%.5f" % v for v in getattr(cls, gname))))
    print("    %s = %s" % (bname, getattr(cls, bname)))
    print("  series rec/ours " + " ".join("%+.0f/%+.0f" % (r, o) for r, o in zip(R_h, O_h)))
    print("  breath rec/ours " + " ".join("%d %+.0f/%+.0f" % (CEN[i], R_c[i], O_c[i]) for i in bands[::2]))


def harm_bands(x, sr, key):
    """Each harmonic's level by WHERE IT SOUNDS: third-octave bands (CEN), the
    harmonics in each pooled, dB re the note's harmonic power -- the window
    T0-T1. A body's or a bore's resonance stays put while the harmonics slide
    through it, so it is read in Hz, not by harmonic number."""
    i = speaks(x, sr)
    seg = x[i + int(T0 * sr): i + int(T1 * sr)]
    seg = seg - seg.mean()
    f0 = f0_near(seg, sr, key)
    N = 1 << 18
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    hz, p = [], []
    m = 1
    while m * f0 < min(16000.0, 0.45 * sr):
        b = (f > m * f0 * 0.98) & (f < m * f0 * 1.02)
        hz.append(m * f0); p.append(X[b].max())
        m += 1
    hz, p = np.array(hz), np.array(p)
    db = 10 * np.log10(p / p.sum() + 1e-30)
    out = np.full(len(CEN), np.nan)
    for k, c in enumerate(CEN):
        w = np.abs(np.log2(hz / c)) <= 1 / 6.0
        if w.any():
            out[k] = 10 * np.log10(np.mean(10 ** (db[w] / 10)))
    return out


def fit_body(voice, prog, cls, passes=4):
    """--fit=body: FormantBody.body_trim_db, by absolute frequency, toward the
    recordings' harmonics pooled by where they sound (harm_bands; the notes'
    median), each pass adding half of recorded - ours (its median removed:
    colour, not level) to every band both measure."""
    import warnings
    warnings.simplefilter("ignore")
    picked = recordings(voice)
    R = np.nanmedian([harm_bands(*load(p), key) for key, p in picked], 0)
    trim = dict((int(round(c)), v) for c, v in (cls.body_trim_db or ()))
    for n in range(passes + 1):
        O = np.nanmedian([harm_bands(*render(prog, key, T1 + 0.5), key) for key, _ in picked], 0)
        d = R - O
        ok = np.isfinite(d)
        d = d - np.nanmedian(d)
        print("  pass %d: harmonics by band, rec - ours, rms %.2f dB over %d bands"
              % (n, np.sqrt(np.nanmean(d[ok] ** 2)), ok.sum()), flush=True)
        print("    " + " ".join("%d:%+.1f" % (CEN[k], d[k]) for k in range(len(CEN)) if ok[k]))
        if n == passes:
            break
        for k in np.flatnonzero(ok):
            c = int(round(CEN[k]))
            trim[c] = trim.get(c, 0.0) + 0.5 * float(d[k])
        cls.body_trim_db = tuple((c, round(v, 1)) for c, v in sorted(trim.items()))
    print("    body_trim_db = %s" % (cls.body_trim_db,))


def fit_skirt(voice, prog, cls, step=3, maxfev=80):
    """--fit=skirt: the harmonics' turbulence -- the skirt's level, its rise
    with harmonic number and its width -- against the recordings' wobble (dB
    rms, h1-h6) and its rate (log2 of the ratio, weighted 3: an octave off in
    rate costs as much as 3 dB of depth). Mean over every STEP-th note."""
    from scipy.optimize import minimize
    refs = []
    for key, p in recordings(voice)[::step]:
        x, sr = load(p)
        r = turbulence(x, sr, key)
        if r is not None:
            refs.append((key, r))
    R = [r for _, r in refs]
    rms_r, rate_r = table(R, "rms", 6), table(R, "rate", 6)
    add = np.array([k.endswith("_db") for k in SKIRT])
    x0 = np.array([float(getattr(cls, k) or 0.0) for k in SKIRT])
    best = [1e9, x0]

    def f(z):
        v = np.where(add, x0 + 6.0 * z, np.exp(z) * x0)
        for k, q in zip(SKIRT, v):
            setattr(cls, k, float(q))
        O = [turbulence(*render(prog, key, 4.5), key) for key, _ in refs]
        a = table(O, "rms", 6) - rms_r
        b = 3.0 * np.log2(table(O, "rate", 6) / rate_r)
        e = float(np.sqrt(np.mean(np.concatenate([a, b]) ** 2)))
        if e < best[0]:
            best[:] = [e, v]
            print("  %5.2f  depth %s  rate %s  %s" % (e, " ".join("%+.1f" % q for q in a),
                  " ".join("%+.1f" % q for q in b / 3.0), " ".join("%s=%.4g" % kv for kv in zip(SKIRT, v))), flush=True)
        return e
    n = len(SKIRT)
    simplex = np.vstack([np.zeros(n)] + [0.5 * np.eye(n)[i] for i in range(n)])
    minimize(f, np.zeros(n), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02})
    for k, q in zip(SKIRT, best[1]):
        setattr(cls, k, float(q))
        print("    %s = %.4g" % (k, q))


WOBBLE = ("breath_wobble_db", "breath_wobble_hz", "breath_noise_wobble_db", "breath_noise_wobble_hz")


def fit_wobble(voice, prog, cls, step=3, maxfev=60):
    """--fit=wobble: the player's breath -- the tone's shared level wobble and
    the breath noise's own, each a depth and a corner -- against the
    recordings' shared wobble (h1-h4 together), the breath's wobble, and each
    harmonic's (h1-h6, so the flutter stays fitted): depths in dB, rates as
    3 log2 of the ratio. The share (their correlation) is set, not fitted."""
    from scipy.optimize import minimize
    refs = []
    for key, p in recordings(voice)[::step]:
        x, sr = load(p)
        r = turbulence(x, sr, key)
        if r is not None:
            refs.append((key, r))
    R = [r for _, r in refs]
    sh_r, rms_r = table(R, "shared", 7), table(R, "rms", 6)
    x0 = np.array([max(float(getattr(cls, k)), 0.5) for k in WOBBLE])
    best = [1e9, x0]

    def f(z):
        v = np.exp(z) * x0
        for k, q in zip(WOBBLE, v):
            setattr(cls, k, float(q))
        O = [turbulence(*render(prog, key, 4.5), key) for key, _ in refs]
        sh, rms = table(O, "shared", 7), table(O, "rms", 6)
        e = np.concatenate([[sh[0] - sh_r[0], sh[2] - sh_r[2]],
                            3.0 * np.log2([sh[1] / sh_r[1], sh[3] / sh_r[3]]), rms - rms_r])
        err = float(np.sqrt(np.mean(e ** 2)))
        if err < best[0]:
            best[:] = [err, v]
            print("  %5.2f  shared %.2f/%.2f dB %.1f/%.1f Hz  breath %.2f/%.2f dB %.1f/%.1f Hz  h %s  %s"
                  % (err, sh[0], sh_r[0], sh[1], sh_r[1], sh[2], sh_r[2], sh[3], sh_r[3],
                     " ".join("%+.1f" % q for q in rms - rms_r),
                     " ".join("%s=%.4g" % kv for kv in zip(WOBBLE, v))), flush=True)
        return err
    n = len(WOBBLE)
    simplex = np.vstack([np.zeros(n)] + [0.4 * np.eye(n)[i] for i in range(n)])
    minimize(f, np.zeros(n), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": simplex, "xatol": 0.02, "fatol": 0.02})
    for k, q in zip(WOBBLE, best[1]):
        setattr(cls, k, float(q))
        print("    %s = %.4g" % (k, q))


def top(voice, prog, nh=64):
    """THE LADDER BY ABSOLUTE FREQUENCY, to 20 kHz: recorded minus ours for
    every harmonic of every note (standing within 60 dB), the median in each
    third octave, pooled and by register. The fit's ladder stops at h12, so a
    body's top (the harmonica's above 8 kHz) is invisible to it -- and the
    renderer's listening path (air, directivity, room) is itself 7-10 dB down
    at 10 kHz, which a voice's body must make up. A gap the same in every
    register is the body's; one that changes sign is the instruments'."""
    global NH
    NH = nh
    B = 2 ** np.arange(np.log2(300), np.log2(20000), 1 / 3.0)
    acc = {g: [[] for _ in B] for g in range(4)}
    for key, p in recordings(voice):
        x, sr = load(p)
        r = analyse(x, sr, key)
        y, sr2 = render(prog, key)
        o = analyse(y, sr2, key)
        g = next(i for i, (lo, hi) in enumerate(REGISTERS) if lo <= key < hi)
        for h in range(1, min(len(r["ladder"]), len(o["ladder"]))):
            if r["ladder"][h] < -60:
                continue
            i = int(np.searchsorted(B, (h + 1) * r["f0"])) - 1
            if 0 <= i < len(B):
                for gg in (g, 3):
                    acc[gg][i].append(r["ladder"][h] - o["ladder"][h])
    print("  band Hz   pooled       low          mid          high      (recorded - ours, dB, n)")
    for i, b in enumerate(B):
        print("  %6d " % (b * 2 ** (1 / 6.0)) + " ".join(
            ("%+6.1f(%3d)  " % (np.median(acc[g][i]), len(acc[g][i]))) if acc[g][i] else "     -       "
            for g in (3, 0, 1, 2)))


# THE RENDERER'S LISTENING PATH (air, directivity, the room), measured by
# rendering a flat series at E5: dB at Hz. The scatter fit reads the model's
# own harmonic levels rather than rendering 30 notes a step, so it adds this.
PATH_HZ = (0, 652, 1305, 2611, 3917, 5223, 6529, 7835, 9141, 10447, 11753, 13059, 15671, 18283, 22050)
PATH_DB = (0, 0, -1.2, -2.1, -2.9, -3.8, -5.0, -6.3, -7.9, -9.8, -11.9, -14.4, -20.9, -35.7, -60)


def rough(ladder):
    """How jagged a ladder is: the sd of its steps, h2-h12, dB."""
    l = np.asarray(ladder[1:12])
    return float(np.std(np.diff(l[np.isfinite(l)])))


def fit_scatter(voice, prog, cls, nh=24):
    """EACH REED ITS OWN LADDER (FreeReedProperties.reed_scatter): fit the
    scatter's depth and its slope an octave to each register's roughness
    (rough(), the mean over its notes) and its deepest hole h2-h12 (0.3 the
    weight), reading the model's harmonic levels plus the listening path."""
    from scipy.optimize import minimize
    rec = []
    for key, p in recordings(voice):
        x, sr = load(p)
        global NH
        NH = nh
        r = analyse(x, sr, key)
        rec.append((key, r["ladder"][:nh], r["f0"]))

    def ours():
        rows = []
        for key, _, f0 in rec:
            q = cls(f0)
            v = np.array([q.harmonic_volume(h) for h in range(1, nh + 1)])
            f = f0 * np.arange(1, nh + 1)
            l = 20 * np.log10(v / v[0] + 1e-9) + np.interp(f, PATH_HZ, PATH_DB) - np.interp(f0, PATH_HZ, PATH_DB)
            l[f > 0.45 * 44100] = np.nan
            rows.append((key, l))
        return rows

    def summary(rows):
        out = []
        for lo, hi in REGISTERS:
            rs = [l for k, l in rows if lo <= k < hi]
            out.append((np.mean([rough(l) for l in rs]), np.mean([np.nanmin(l[1:12]) for l in rs])))
        return np.array(out)

    R = summary([(k, l) for k, l, _ in rec])

    def err(v):
        cls.reed_scatter, cls.reed_scatter_per_octave = float(v[0]), float(v[1])
        d = summary(ours()) - R
        return float(np.sum(d[:, 0] ** 2) + 0.3 * np.sum(d[:, 1] ** 2))

    best = min((minimize(err, np.array(x0), method="Nelder-Mead") for x0 in ([1.0, 0.0], [2.0, -0.5], [0.5, 0.3])),
               key=lambda r: r.fun)
    err(best.x)
    O = summary(ours())
    for (lo, hi), r, o in zip(REGISTERS, R, O):
        print("  keys %3d-%3d  rough %.1f (recorded %.1f)  deepest %.1f (%.1f)" % (lo, hi - 1, o[0], r[0], o[1], r[1]))
    print("    reed_scatter = %.4g\n    reed_scatter_per_octave = %.4g" % tuple(best.x))


def main(argv):
    spec = next((a.split("=", 1)[1] for a in argv if a.startswith("--inharm=")), None)
    if spec:
        return inharm(spec) or 0
    voice = next((a.split("=")[1] for a in argv if a.startswith("--voice=")), "recorder")
    global T0, T1, TONIC_CENTS, CC1, CCS
    T0 = VOICE_OPTS.get(voice, {}).get("t0", T0)
    T1 = VOICE_OPTS.get(voice, {}).get("t1", T1)
    TONIC_CENTS = VOICE_OPTS.get(voice, {}).get("tonic_cents", 0.0)
    CC1 = VOICE_OPTS.get(voice, {}).get("cc1")
    CCS = VOICE_OPTS.get(voice, {}).get("ccs", ())
    prog, cls = use_class(voice)
    fitarg = next((a for a in argv if a.startswith("--fit")), None)
    if fitarg == "--fit=breath":
        fit_breath(voice, prog, cls)
        fitarg = None
    elif fitarg == "--fit=wobble":
        fit_wobble(voice, prog, cls)
        return 0
    elif fitarg == "--fit=scatter":
        fit_scatter(voice, prog, cls)
        return 0
    elif fitarg and fitarg.startswith("--fit=top:"):
        fit_top(voice, prog, cls, fitarg.split(":", 1)[1].split(","))
        return 0
    elif fitarg == "--fit=bloom":
        fit_bloom(voice, prog, cls)
        return 0
    elif fitarg == "--fit=speech":
        fit_speech(voice, prog, cls)
        return 0
    elif fitarg == "--fit=push":
        hold = next((a.split("=", 1)[1].split(",") for a in argv if a.startswith("--hold=")), ())
        fit_push(voice, prog, cls, hold=tuple(hold))
        return 0
    elif fitarg == "--fit=body":
        fit_body(voice, prog, cls)
        return 0
    elif fitarg == "--fit=tables":
        fit_tables(voice, prog, cls, argv)
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
    if "--top" in argv:
        return top(voice, prog) or 0
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--ab=")), None)
    if out:
        ks = next((a.split("=", 1)[1] for a in argv if a.startswith("--ab-keys=")), None)
        return ab(voice, prog, out, keys={int(k) for k in ks.split(",")} if ks else None) or 0
    report(voice, prog)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
