"""GS 56.8 Flugel Horn, fitted to Chris Cook's "Dusty Flugelhorn" (Pianobook;
~/Documents/refs/flugelhorn_pianobook, sources.md -- measure only): a Yamaha
6310z, every note E3-A#5 at one soft dynamic, each 7 s with 0.5 s of silence
before it. The file names are the sounding pitch (measured: within 11 cents);
the pack's Decent Sampler preset maps them an octave higher.

THE TRUMPET'S MODEL, ITS COLOUR REFITTED: a flugelhorn is a trumpet player on
a conical, wider bore -- the same mouthpiece and the same source, the bell and
the bore darker. So FlugelhornProperties keeps TrumpetProperties and fits the
five knobs that make its colour: bell_cutoff_hz, bell_order, bore_corner_hz,
tonal_dampening, octave_dampening.

THE TAKES ARE SOFT, OUR TRUMPET IS MF: fitted plain, the soft dynamic's
darkness went into the flugelhorn's colour -- ours then 40-60 dB darker than
our trumpet where one player's flugelhorn and trumpet (Wikimedia Commons, the
same tune; --commons) differ by a few dB. So ours is read through the
trumpet's own SOFT LAW while fitting (56.25 Warm Tp.: Iowa's trumpet pp
against its mf, blare -6.6 dB/kHz over 160 Hz to 34.8), and the class keeps
the flugelhorn's colour at our mf.

Each note's ladder, h1-h16 dB re the strongest, over its steady part (0.4-2.0
s after it speaks); ours at the same key, velocity 80, read the same way.
Fitted on every third note (all registers), scored on all.

    python3 examples/flugel_fit.py            # the ladders, takes and ours
    python3 examples/flugel_fit.py --fit      # the five knobs
    python3 examples/flugel_fit.py --commons  # the check: flugelhorn - trumpet,
                                              # one player's pair against ours
    python3 examples/flugel_fit.py --fit=commons  # the knobs to that pair instead
"""
import glob
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
from drum_fit import read  # noqa: E402

D = os.path.expanduser("~/Documents/refs/flugelhorn_pianobook/unz/Dusty Flugelhorn/Dusty Flugelhorn Samples")
NAMES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
NH = 16
T0, T1 = 0.4, 2.0
VEL = 80
FLOOR = -50.0
CLS = "FlugelhornProperties"
KNOBS = ("bell_cutoff_hz", "bell_order", "bore_corner_hz", "tonal_dampening", "octave_dampening")


def speaks(x, sr):
    return int(np.flatnonzero(np.abs(x) > 0.1 * np.abs(x).max())[0])


def ladder(x, sr, f0):
    a = speaks(x, sr)
    s = x[a + int(T0 * sr):a + int(T1 * sr)]
    N = 1 << 18
    Y = 20 * np.log10(np.abs(np.fft.rfft(s * np.hanning(len(s)), N)) + 1e-12)
    f = np.fft.rfftfreq(N, 1 / sr)
    lad = np.array([Y[(f > h * f0 * 0.985) & (f < h * f0 * 1.015)].max() for h in range(1, NH + 1)])
    return lad - lad.max()


def takes():
    out = []
    for p in sorted(glob.glob(os.path.join(D, "*.wav"))):
        m = re.search(r"Flg p ([A-G]#?)(\d)\.wav", p)
        key = NAMES[m.group(1)] + 12 * (int(m.group(2)) + 1)
        x, sr = read(p)
        x = x.reshape(len(x), -1).mean(1)
        out.append((key, ladder(x, sr, 440.0 * 2 ** ((key - 69) / 12.0))))
    return sorted(out)


SOFT_LAW = dict(blare_db_per_khz=-6.6, blare_knee_hz=160.0, blare_cap_db=34.8)


def ours(key, soft=True):
    """Our 56.8 at the key, velocity VEL, selected as a file selects it --
    bank 8, then program 56 (overriding PROGRAM_CLASS[56] reached nothing:
    the trumpet's program resolves its class another way)."""
    import mido
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("control_change", channel=0, control=0, value=8, time=0))
    t.append(mido.Message("program_change", channel=0, program=56, time=0))
    t.append(mido.Message("note_on", channel=0, note=key, velocity=VEL, time=0))
    t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int((T1 + 0.4) * 960)))
    import tonelib
    C = getattr(tonelib, CLS)
    keep = {k: C.__dict__.get(k) for k in SOFT_LAW}
    if soft:
        for k, v in SOFT_LAW.items():
            setattr(C, k, v)
    try:
        L, R = B.render(m)[:2]
    finally:
        for k, v in keep.items():
            if v is None:
                if k in C.__dict__:
                    delattr(C, k)
            else:
                setattr(C, k, v)
    y = 0.5 * (np.asarray(L, float) + np.asarray(R, float))
    return ladder(y, B.SR, 440.0 * 2 ** ((key - 69) / 12.0))


def score(T, show=False):
    e = []
    for key, R in T:
        O = ours(key)
        m = R > FLOOR
        d = (O - R)[m]
        e.append(d)
        if show:
            print("  %d  rec %s\n      ours %s" % (key, " ".join("%+4.0f" % v for v in R),
                                                 " ".join("%+4.0f" % v for v in O)))
    e = np.concatenate(e)
    return float(np.sqrt(np.mean(e ** 2)))


def fit(T, maxfev=120):
    import tonelib
    from scipy.optimize import minimize
    C = getattr(tonelib, CLS)
    x0 = np.array([getattr(C, k) for k in KNOBS], float)
    sub = T[::3]
    best = [1e9, x0]

    def f(u):
        v = x0.copy()
        v[0] = x0[0] * np.exp(u[0])
        v[1] = max(0.5, x0[1] * np.exp(u[1]))
        v[2] = x0[2] * np.exp(u[2])
        v[3] = max(0.05, x0[3] * np.exp(u[3]))
        v[4] = x0[4] + u[4]
        for k, val in zip(KNOBS, v):
            setattr(C, k, float(val))
        s = score(sub)
        if s < best[0]:
            best[:] = [s, v.copy()]
            print("  %.2f dB  " % s + " ".join("%s=%.4g" % (k, val) for k, val in zip(KNOBS, v)), flush=True)
        return s
    minimize(f, np.zeros(len(KNOBS)), method="Nelder-Mead",
             options=dict(maxfev=maxfev, initial_simplex=np.vstack([np.zeros(len(KNOBS)), 0.4 * np.eye(len(KNOBS))])))
    for k, val in zip(KNOBS, best[1]):
        setattr(C, k, float(val))
    print("  all notes: %.2f dB rms" % score(T))
    for k in KNOBS:
        print("    %s = %.4g" % (k, getattr(C, k)))


CEN = 2 ** np.arange(np.log2(160), np.log2(8000), 1 / 3.0)


def commons(fit_it=False):
    """One player's flugelhorn and trumpet, the same tune (Wikimedia Commons,
    CC BY-SA 4.0, local only): their long-term spectra by third octave, each
    re its median, flugelhorn - trumpet; ours the same over C4-D#5 (the
    tune's register), 56.8 - 56.0 at our mf."""
    import subprocess
    import tempfile
    import mido
    import blockrender as B
    R = os.path.expanduser("~/Documents/refs/commons/flugelhorn")

    def load(fn):
        with tempfile.TemporaryDirectory() as d:
            w = os.path.join(d, "t.wav")
            subprocess.run(["sox", os.path.join(R, fn), "-e", "floating-point", "-b", "32", "-c", "1", w],
                           check=True)
            x, sr = read(w)
        return x.reshape(len(x), -1).mean(1), sr

    def bands(x, sr):
        N = 1 << 15
        acc = np.zeros(N // 2 + 1)
        w = np.hanning(N)
        for s0 in range(0, len(x) - N, N // 2):
            acc += np.abs(np.fft.rfft(x[s0:s0 + N] * w)) ** 2
        f = np.fft.rfftfreq(N, 1 / sr)
        b = np.array([10 * np.log10(acc[(f > c * 2 ** (-1 / 6.0)) & (f < c * 2 ** (1 / 6.0))].sum() + 1e-20)
                      for c in CEN])
        return b - np.median(b)

    def render(bank):
        m = mido.MidiFile(type=1, ticks_per_beat=480)
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.Message("control_change", channel=0, control=0, value=bank, time=0))
        t.append(mido.Message("program_change", channel=0, program=56, time=0))
        for k in range(60, 76, 2):
            t.append(mido.Message("note_on", channel=0, note=k, velocity=90, time=0))
            t.append(mido.Message("note_off", channel=0, note=k, velocity=0, time=480))
        L, Rr = B.render(m)[:2]
        return 0.5 * (np.asarray(L, float) + np.asarray(Rr, float)), B.SR
    rec = bands(*load("Short_flugelhorn_excerpt.ogg")) - bands(*load("Trumpet_excerpt_for_comparison.ogg"))
    trumpet = bands(*render(0))
    if fit_it:
        # THE SAME FIVE KNOBS, to the pair's difference from our trumpet --
        # the other reading of what a flugelhorn is (one player, one dynamic,
        # both horns), where the Pianobook horn is one soft instrument
        import tonelib
        from scipy.optimize import minimize
        C = getattr(tonelib, CLS)
        x0 = np.array([getattr(C, k) for k in KNOBS], float)
        best = [1e9, x0]

        def f(u):
            v = x0.copy()
            v[0] = x0[0] * np.exp(u[0])
            v[1] = max(0.5, x0[1] * np.exp(u[1]))
            v[2] = x0[2] * np.exp(u[2])
            v[3] = max(0.05, x0[3] * np.exp(u[3]))
            v[4] = x0[4] + u[4]
            for k, val in zip(KNOBS, v):
                setattr(C, k, float(val))
            e = float(np.sqrt(np.mean((rec - (bands(*render(8)) - trumpet)) ** 2)))
            if e < best[0]:
                best[:] = [e, v.copy()]
                print("  %.2f dB  " % e + " ".join("%s=%.4g" % (k, val) for k, val in zip(KNOBS, v)), flush=True)
            return e
        minimize(f, np.zeros(len(KNOBS)), method="Nelder-Mead",
                 options=dict(maxfev=80, initial_simplex=np.vstack([np.zeros(len(KNOBS)),
                                                                    0.4 * np.eye(len(KNOBS))])))
        for k, val in zip(KNOBS, best[1]):
            setattr(C, k, float(val))
        for k in KNOBS:
            print("    %s = %.4g" % (k, getattr(C, k)))
    oo = bands(*render(8)) - trumpet
    print("  flugelhorn - trumpet by third octave (each re its median):")
    print("  band " + " ".join("%5.0f" % c for c in CEN))
    print("  pair " + " ".join("%+5.0f" % v for v in rec))
    print("  ours " + " ".join("%+5.0f" % v for v in oo))
    print("  rms miss %.1f dB" % np.sqrt(np.mean((rec - oo) ** 2)))


def main(argv):
    if "--commons" in argv:
        return commons()
    if "--fit=commons" in argv:
        return commons(fit_it=True)
    T = takes()
    if "--fit" in argv:
        fit(T)
    else:
        print("  %.2f dB rms over h1-h%d, %d notes" % (score(T, show=True), NH, len(T)))


if __name__ == "__main__":
    main(sys.argv[1:])
