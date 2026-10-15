#!/usr/bin/env python3
"""The church organ's principal chorus (GM 19) against the Pitea organ's pipes.

    python3 examples/pitea_fit.py                     measure: each rank against its stop
    python3 examples/pitea_fit.py --fit=body          FlueOrganProperties.body_trim_db
    python3 examples/pitea_fit.py --fit=tone          the series: tonal/octave dampening, ceiling
    python3 examples/pitea_fit.py --ab=OUT.wav        Pitea's Principal 8 then ours, key by key

THE REFERENCE (sources.md "Pipe organ"): Lars Palo's Pitea School of Music set,
CC BY-SA 2.5 -- the Gronlund organ's every pipe, one file a key, numbered by
MIDI note and tuned equal at A440 (checked: C2 65.40 Hz, A4 439.96). Our
ranks against its HV (Huvudverk) stops of the same footage:

  principal 8     HVPrincipal8      the foundation -- GM 19 draws it alone
  octave 4        HVOktava4
  super octave 2  HVOktava2

MEASURED THE SAME WAY ON BOTH SIDES, over the pipe's steady sound (1.0-3.0 s
after it speaks; the two microphones' spectra averaged as powers):
  LADDER  each harmonic, dB re the fundamental, to h32
  BANDS   the harmonics pooled by third-octave of where they sound, re the
          pipe's harmonic power -- the voicing and the room together
"""
import glob
import os
import subprocess
import sys
import tempfile

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ.setdefault("TUNING_REFLECT", "0")
import blockrender as B  # noqa: E402
import tonelib as T  # noqa: E402

PITEA = os.path.expanduser("~/Documents/refs/organ/pitea")
RANKS = {"principal 8": "HVPrincipal8", "octave 4": "HVOktava4", "super octave 2": "HVOktava2"}
# The console's other stops, each against a Pitea stop of its kind
# (examples/pitea_stops.py). Pitea's Mixtur is IV ranks to our III, its
# composition not in the set.
MORE_STOPS = {
    "flute 8":     ("POSGedakt8",    "Positiv Gedakt 8, stopped"),
    "bourdon 16":  ("HVGedPommer16", "Huvudverk Gedackt Pommer 16, stopped"),
    "quint 2-2/3": ("POSKvinta223",  "Positiv Kvinta 2 2/3"),
    "mixture III": ("HVMixtur",      "Huvudverk Mixtur IV"),
    "reed 8":      ("POSCromorne8",  "Positiv Cromorne 8"),
    "reed 16":     ("Basson16",      "Basson 16 (the extended set's second organ)"),
    "reed 4":      ("SVClarion4",    "Svallverk Clarion 4"),
    "trumpet 8":   ("HVTrumpet8",    "Huvudverk Trumpet 8"),
    # the recorded ranks added on bits 14-24 (tonelib, "THE RECORDED RANKS")
    "koppelflute 4":    ("POSKoppelflojt4", "Positiv Koppelflöjt 4"),
    "waldflute 2":      ("POSValdflojt2",   "Positiv Valdflöjt 2"),
    "nazard 2-2/3":     ("Nazard",          "Nazard 2 2/3"),
    "tierce 1-3/5":     ("Tierce",          "Tierce 1 3/5"),
    "subbass 16":       ("PEDSubbas16",     "Pedal Subbas 16"),
    "contrabassoon 32": ("Kontrabasun32",   "Pedal Kontrabasun 32"),
    "gamba 8":          ("SVGamba8",        "Svallverk Gamba 8"),
    "celeste 8":        ("SVVoixCeleste8",  "Svallverk Voix celeste 8"),
    "oboe 8":           ("SVOboe8",         "Svallverk Oboe 8"),
    "vox humana 8":     ("VoixHumaine8",    "Voix humaine 8 (the extended set's second organ)"),
    "trompette 8":      ("SVTrHarm8",       "Svallverk Trompette harmonique 8"),
}
FOLDER = dict(RANKS, **{k: v[0] for k, v in MORE_STOPS.items()})
NH = 32
T0, T1 = 1.0, 3.0
CEN = 2 ** np.arange(np.log2(50), np.log2(13000), 1 / 3.0)
STEP = 4                      # every STEP-th key


def read(path):
    with tempfile.TemporaryDirectory() as d:
        w = os.path.join(d, "t.wav")
        subprocess.run(["sox", path, "-e", "floating-point", "-b", "32", w], check=True,
                       stderr=subprocess.DEVNULL)
        from scipy.io import wavfile
        sr, x = wavfile.read(w)
    x = x.astype(np.float64)
    return (x if x.ndim == 2 else x[:, None]), sr


def spectrum(x, sr):
    """Power spectrum of the steady part, the channels averaged as powers."""
    s = x[int(T0 * sr):int(T1 * sr)]
    N = 1 << 18
    P = np.mean([np.abs(np.fft.rfft(c * np.hanning(len(c)), N)) ** 2 for c in s.T], 0)
    return P, np.fft.rfftfreq(N, 1.0 / sr)


def measure(x, sr, f0):
    P, f = spectrum(x, sr)
    b = (f > f0 / 1.04) & (f < f0 * 1.04)
    f0 = f[b][np.argmax(P[b])]
    hz, h = [], []
    m = 1
    while m * f0 < min(13000.0, 0.45 * sr):
        w = (f > m * f0 * 0.985) & (f < m * f0 * 1.015)
        hz.append(m * f0); h.append(P[w].max())
        m += 1
    hz, h = np.array(hz), np.array(h)
    lad = 10 * np.log10(h[:NH] / h[0] + 1e-30)
    lad = np.concatenate([lad, np.full(NH - len(lad), np.nan)])
    db = 10 * np.log10(h / h.sum() + 1e-30)
    bands = np.full(len(CEN), np.nan)
    for k, c in enumerate(CEN):
        sel = np.abs(np.log2(hz / c)) <= 1 / 6.0
        if sel.any():
            bands[k] = 10 * np.log10(np.mean(10 ** (db[sel] / 10)))
    return lad, bands, f0


def pipes(rank):
    out = []
    for p in sorted(glob.glob(os.path.join(PITEA, FOLDER[rank], "[0-9][0-9][0-9]-*.wav"))):
        out.append((int(os.path.basename(p)[:3]), p))
    return out[::STEP]


def render(rank, key, secs=3.5):
    cls = T.FlueOrganProperties
    names = [r[0] for r in cls.stop_ranks]
    keep = cls.default_stops
    cls.default_stops = 1 << names.index(rank)
    try:
        m = mido.MidiFile(type=1, ticks_per_beat=480)
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.Message("program_change", channel=0, program=19, time=0))
        t.append(mido.Message("note_on", channel=0, note=key, velocity=100, time=0))
        t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(secs * 960)))
        L, R = B.render(m)[:2]
    finally:
        cls.default_stops = keep
    x = np.stack([np.asarray(L, np.float64), np.asarray(R, np.float64)], 1)
    a = int(np.flatnonzero(np.abs(x[:, 0]) > np.abs(x[:, 0]).max() * 0.01)[0])
    return x[a:], B.SR


def both(rank):
    rec, ours = [], []
    ratio = dict((r[0], r[1]) for r in T.FlueOrganProperties.stop_ranks)[rank]
    for key, p in pipes(rank):
        x, sr = read(p)
        a = int(np.flatnonzero(np.abs(x[:, 0]) > np.abs(x[:, 0]).max() * 0.01)[0])
        f0 = 440.0 * 2 ** ((key - 69) / 12.0) * ratio
        r = measure(x[a:], sr, f0)
        y, s2 = render(rank, key)
        rec.append((key, r)); ours.append((key, measure(y, s2, f0)))
    return rec, ours


def report(argv):
    for rank in RANKS:
        rec, ours = both(rank)
        print("  == %s (%s), %d pipes" % (rank, FOLDER[rank], len(rec)))
        for lo, hi in ((24, 48), (48, 72), (72, 100)):
            R = [r[0] for k, r in rec if lo <= k < hi]
            O = [o[0] for k, o in ours if lo <= k < hi]
            if not R:
                continue
            R, O = np.nanmedian(R, 0), np.nanmedian(O, 0)
            print("  keys %d-%d  rec  %s" % (lo, hi - 1, " ".join("%5.1f" % v for v in R)))
            print("             ours %s" % " ".join("%5.1f" % v for v in O))
        d = np.nanmedian([r[1] for _, r in rec], 0) - np.nanmedian([o[1] for _, o in ours], 0)
        d -= np.nanmedian(d)
        print("  bands rec-ours " + " ".join("%d:%+.1f" % (c, v) for c, v in zip(CEN, d) if np.isfinite(v)))


TONE = ("tonal_dampening", "bore_corner_hz", "bore_order", "octave_dampening")


def fit_tone(maxfev=80):
    """--fit=tone: the flue's series -- its tilt (tonal_dampening), a corner by
    absolute frequency and its steepness (bore_corner_hz, bore_order: the
    mouth's cut-off), and the register's darkening (octave_dampening) --
    against every rank's ladder, h2-h16, pipe by pipe (dB, rms)."""
    from scipy.optimize import minimize
    import warnings
    warnings.simplefilter("ignore")
    cls = T.FlueOrganProperties
    refs = []
    for rank in RANKS:
        ratio = dict((r[0], r[1]) for r in cls.stop_ranks)[rank]
        for key, p in pipes(rank)[::2]:
            x, sr = read(p)
            a = int(np.flatnonzero(np.abs(x[:, 0]) > np.abs(x[:, 0]).max() * 0.01)[0])
            f0 = 440.0 * 2 ** ((key - 69) / 12.0) * ratio
            refs.append((rank, key, f0, measure(x[a:], sr, f0)[0]))
    x0 = np.array([1.2, 2500.0, 3.0, float(cls.octave_dampening)])
    best = [1e9, x0]

    def val(z):
        return np.array([x0[0] * np.exp(z[0]), x0[1] * np.exp(z[1]), x0[2] * np.exp(z[2]),
                         max(0.0, x0[3] + 0.2 * z[3])])

    def f(z):
        v = val(z)
        for k, q in zip(TONE, v):
            setattr(cls, k, float(q))
        err = []
        for rank, key, f0, R in refs:
            y, s2 = render(rank, key)
            O = measure(y, s2, f0)[0]
            ok = np.isfinite(R) & np.isfinite(O)
            ok[0] = False
            err.extend((O - R)[ok])
        e = float(np.sqrt(np.mean(np.square(err))))
        if e < best[0]:
            best[:] = [e, v]
            print("  %5.2f dB  %s" % (e, " ".join("%s=%.4g" % kv for kv in zip(TONE, v))), flush=True)
        return e
    minimize(f, np.zeros(4), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": np.vstack([np.zeros(4), 0.4 * np.eye(4)]),
                      "xatol": 0.02, "fatol": 0.05})
    for k, q in zip(TONE, best[1]):
        print("    %s = %.4g" % (k, q))


def fit_tables(passes=3, rank="principal 8"):
    """--fit=tables: the flue's series as MEASURED TABLES, h1-h32, at three
    anchor pitches (SynthProperties.mode_gains_points): the rank's pipes on
    keys to B2, C3-B4 and from C5, each group's median ladder at its keys'
    geometric-mean pitch, blended along log frequency between -- each pass
    adding recorded - ours to every harmonic. A power law and a corner could
    not (the bass ladder falls as -4.15 (log2 n)^2 dB), and two registers
    could not either: the 4' and 2' are brightest over the middle keys."""
    import warnings
    warnings.simplefilter("ignore")
    fl = T.FlueOrganProperties
    row = next(r for r in fl.stop_ranks if r[0] == rank)
    cls = row[3] if len(row) > 3 and row[3] is not None else fl
    cls.bore_corner_hz = 0.0
    edges = ((0, 47), (48, 71), (72, 127))
    groups = [[] for _ in edges]
    for key, p in pipes(rank):
        if not 36 <= key <= 96:          # the manual's compass (the Positiv's run lower)
            continue
        gi = next(i for i, (a0, a1) in enumerate(edges) if a0 <= key <= a1)
        x, sr = read(p)
        a = int(np.flatnonzero(np.abs(x[:, 0]) > np.abs(x[:, 0]).max() * 0.01)[0])
        f0 = 440.0 * 2 ** ((key - 69) / 12.0) * row[1]
        groups[gi].append((key, f0, measure(x[a:], sr, f0)[0]))
    # A RANK'S OWN COMPASS: a pedal rank (the Subbas to F4, the Kontrabasun to
    # F4) has no treble group -- its anchors are the registers it reaches
    groups = [g for g in groups if g]
    R = [np.nanmedian([r for _, _, r in g], 0) for g in groups]
    # anchored at the RANK's pitch, where the renderer reads them (mode_gains_at)
    anchors = [float(np.exp(np.mean([np.log(f0) for _, f0, _ in g]))) for g in groups]
    tabs = []
    for r in R:
        t = np.where(np.isfinite(r), r, np.nanmin(r))
        tabs.append([float(10 ** (v / 20.0)) for v in t])
    cls.mode_gains_low = None
    cls.max_harmonic = NH
    for n in range(passes + 1):
        cls.mode_gains_points = tuple((f, tuple(t)) for f, t in zip(anchors, tabs))
        cls.mode_gains = tuple(tabs[-1])
        msg = []
        for gi, g in enumerate(groups):
            O = np.nanmedian([measure(*render(rank, k), f0)[0] for k, f0, _ in g], 0)
            d = R[gi] - O
            ok = np.isfinite(d)
            msg.append("%.2f" % np.sqrt(np.mean(d[ok][1:] ** 2)))
            if n < passes:
                for m in range(1, NH):
                    if ok[m]:
                        tabs[gi][m] *= 10 ** (d[m] / 20.0)
        print("  %s pass %d: ladder rec - ours rms, h2-h%d, bass/middle/treble: %s dB"
              % (rank, n, NH, " / ".join(msg)), flush=True)
    print("    %s.mode_gains_points = (" % cls.__name__)
    for f, t in cls.mode_gains_points:
        print("        (%.1f, (%s))," % (f, ", ".join("%.5f" % v for v in t)))
    print("    )")


# PITEA'S HALL, near enough, for ours in an A/B: the set's samples carry the
# school's organ hall (its release falls ~70 dB/s after a few dB in the first
# 60 ms), and ours renders with early reflections only -- dry against wet.
# Matched on the Principal 8's release samples at C3, C4 and C5
PITEA_HALL = "reverb 45 50 60 100 5 -4"


def ab(out, rank="principal 8", keys=(36, 43, 48, 55, 60, 67, 72, 79, 84)):
    """--ab=OUT.wav: the rank's Pitea pipe, then ours, key by key, level-matched
    over the steady part; the left channel each. Ours through PITEA_HALL,
    and its note released, so the release is heard against the hall's too."""
    import wave
    from scipy.signal import resample_poly
    SR = 44100
    parts = []
    gap = np.zeros(int(0.35 * SR))
    allp = {int(os.path.basename(p)[:3]): p for p in
            glob.glob(os.path.join(PITEA, FOLDER[rank], "[0-9][0-9][0-9]-*.wav"))}
    for k in keys:
        if k not in allp:
            continue
        x, sr = read(allp[k])
        x = x[:, 0]
        if sr != SR:
            x = resample_poly(x, SR, sr)
        a = int(np.flatnonzero(np.abs(x) > np.abs(x).max() * 0.01)[0])
        x = x[max(0, a - int(0.02 * SR)):]
        y, s2 = render(rank, k, secs=min(3.0, len(x) / SR - 1.0))
        y = y[:, 0]
        if s2 != SR:
            y = resample_poly(y, SR, s2)
        with tempfile.TemporaryDirectory() as d:
            from scipy.io import wavfile
            wavfile.write(os.path.join(d, "a.wav"), SR, (y / max(np.abs(y).max(), 1e-9) * 0.5).astype(np.float32))
            subprocess.run(["sox", os.path.join(d, "a.wav"), "-e", "floating-point", "-b", "32",
                            os.path.join(d, "b.wav")] + PITEA_HALL.split(), check=True, stderr=subprocess.DEVNULL)
            y = wavfile.read(os.path.join(d, "b.wav"))[1].astype(np.float64)
            y = y.mean(1) if y.ndim == 2 else y
        y = y[:len(x)]
        s0, s1 = int(T0 * SR), int(T1 * SR)
        y *= np.sqrt(np.mean(x[s0:s1] ** 2) / max(np.mean(y[s0:s1] ** 2), 1e-30))
        parts += [x, gap, y, gap, gap]
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


if __name__ == "__main__":
    _ab = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--ab=")), None)
    if _ab:
        ab(_ab)
    elif "--fit=tables" in sys.argv:
        for _r in ([a.split("=", 1)[1] for a in sys.argv if a.startswith("--stop=")] or RANKS):
            fit_tables(rank=_r)
    elif "--fit=tone" in sys.argv:
        fit_tone()
    else:
        report(sys.argv)
