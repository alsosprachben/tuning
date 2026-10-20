#!/usr/bin/env python3
"""Fit a plucked voice to single-pluck takes: the sitar (GM 104) to Freesound's sitar
takes, the banjo (GM 105) to the Windsor SoundFont's plucks, the shamisen (GM 106) to
a live festival take's isolated plucks (sources.md "Ethnic programs").

    python3 examples/pluck_fit.py --voice=sitar|banjo [...]   (sitar if omitted)

    python3 examples/pluck_fit.py --stage            cut the takes into one pluck a file
    python3 examples/pluck_fit.py                    measure: recorded against ours
    python3 examples/pluck_fit.py --fit=decay        decay_db, harmonic_decay_db, the register slope
    python3 examples/pluck_fit.py --fit=body         body_trim_db, by absolute frequency
    python3 examples/pluck_fit.py --fit=jawari       the buzz's growth: a banded late copy (bloom)
    python3 examples/pluck_fit.py --fit=prompt       the low partials' prompt fall (two-stage decay)
    python3 examples/pluck_fit.py --ab=OUT.wav       recorded, then ours, pluck by pluck
    (--take=ma fits to one take only)

THE NOTES. Two strings, two players:
  ma       the main string's Ma, struck once and left to ring ~10 s, four times
           (freesound 42192, CC0): 169 Hz
  chinpen  one note struck thirteen times, 0.8-5 s apart (42268, CC BY 3.0):
           292 Hz; the strokes with 2.5 s and more to the next are taken
Each is staged under ~/Documents/refs/freesound/staged/sitar/ as
<label>_<n>.wav with its measured f0 in the name (f0_<Hz>), and ours is
rendered at THAT pitch, by a secondary tuning whose Sa is it (a sitar's
wheel is a meend, not a bend), so a gourd's colour lines up where it sounds.

MEASURED THE SAME WAY ON BOTH SIDES, per pluck:
  DECAY   each harmonic's level in 0.2 s frames every 0.1 s, its slope (dB/s)
          from 0.3 s to 5 s while within 45 dB of its peak
  LADDER  each harmonic at 0.15 s and at 2 s, dB re the fundamental at 0.15 s
  BANDS   at 0.1-0.3 s, the harmonics pooled by third-octave of where they
          sound, re the note's harmonic power (the body's colour)
"""
import glob
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ.setdefault("TUNING_REFLECT", "0")

REFS = os.path.expanduser("~/Documents/refs/freesound")
STAGED = os.path.join(REFS, "staged", "sitar")
PROG = 104
CLS = "SitarProperties"
# voice: (program, class, staged folder)
VOICES = {"sitar": (104, "SitarProperties", "sitar"), "banjo": (105, "BanjoProperties", "banjo"),
          "shamisen": (106, "ShamisenProperties", "shamisen"),
          # GS 26.8 Hawaiian Gt. on David Long's hollow-body lap steel (Pianobook,
          # Lapsteel Articulations; sources.md): its open strings, one pluck a file
          "lapsteel": (26, "HawaiianGuitarProperties", "lapsteel"),
          # GS 25.16 Mandolin on Joshua Meltzer's (Pianobook, Eclectic Mandolin),
          # carved from its monolith: its medium layer's long takes
          "mandolin": (25, "MandolinProperties", "mandolin"),
          # GS 107.8 Taisho Koto on Arthur Chanson's soprano taishogoto
          # (Pianobook, Taishogoto): its condenser takes, the middle velocity
          "taisho": (107, "TaishoKotoProperties", "taisho"),
          # ...and its open G2 drone string, its own takes (Drone_Mic_*); rendered
          # on its class through the drone's own program slot (DRONE_PROG)
          "taishodrone": (107, "TaishoDroneProperties", "taishodrone"),
          # GS 24.8 Ukulele on Ben's own (ukulele_ben/, recorded 2026-10-19)
          "ukulele": (24, "UkuleleProperties", "ukulele")}
# the GS bank a voice is (a variation): CC0 before its program change
BANKS = {"lapsteel": 8, "mandolin": 16, "taisho": 8, "taishodrone": 9, "ukulele": 8}
BANK = 0
NH = 24
HOP, WIN = 0.1, 0.2
# THE DECAY'S WINDOW: from T_DECAY to T_END s after the pluck. A live take's
# plucks (the shamisen's) ring 0.3-0.7 s before the next, so they are read in
# short frames over their first 0.3 s (VOICE_OPTS); a sitar's ring for seconds
T_DECAY, T_END = 0.3, 5.0
# ...and the prompt fall's (--fit=prompt): its bands read over P_SECS, from
# PROMPT_X0 (the shamisen's knock is on every partial, so from 6 kHz)
P_SECS = 0.6
PROMPT_X0 = (15.0, 0.3, 1200.0)
# ...and the render's TUNER: None the renderer's own. A voice with tuned open
# strings ringing in sympathy (the shamisen's) is rendered where the take's
# instrument was tuned -- its strings follow the table, so a pluck bent to the
# take's pitch off an A440 table would sit up to 45 cents off its own strings
TUNER = None
VOICE_OPTS = {"mandolin": dict(T_END=3.0),
              # (16 harmonics: its high notes, 929 Hz, have no 24th under Nyquist)
              "taisho": dict(T_END=4.0, NH=16),
              "taishodrone": dict(T_END=6.0),
              # its notes damped ~3 s in: read to 2.4 s
              "ukulele": dict(T_END=2.4, NH=16),
              "lapsteel": dict(T_END=8.0,
                               # the take's own tuning: E3, its open string, at
                               # 164.54 Hz, so a pluck and the strings answering
                               # it share one table (bent to the take's pitch,
                               # the played note left the open strings behind)
                               TUNER="hybrid440:443.92"),
              "shamisen": dict(HOP=0.02, WIN=0.06, T_DECAY=0.05, T_END=0.3,
                               P_SECS=0.3, PROMPT_X0=(30.0, 0.15, 6000.0),
                               # C#3, its sympathetic_tonic, at the bass string's 142.2 Hz
                               TUNER="hybrid:454.81")}
CEN = 2 ** np.arange(np.log2(160), np.log2(13000), 1 / 3.0)


def read(path):
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "t.wav")
        subprocess.run(["sox", path, "-c", "1", "-b", "16", wav], check=True)
        import wave
        w = wave.open(wav)
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32768.0
    return x, sr


def onsets(x, sr, top_db=35.0, min_gap=0.3):
    w = int(0.01 * sr)
    en = 10 * np.log10(np.convolve(x * x, np.ones(w) / w, "same") + 1e-12)[::w]
    ons = [i for i in range(5, len(en)) if en[i] - en[i - 5] > 10 and en[i] > en.max() - top_db]
    out = []
    for i in ons:
        if not out or i - out[-1] > min_gap / 0.01:
            out.append(i)
    return [i * 0.01 for i in out]


def f0_of(seg, sr, lo, hi):
    N = 1 << 19
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    b = (f > lo) & (f < hi)
    k = np.flatnonzero(b)[np.argmax(X[b])]
    y0, y1, y2 = np.log(X[k - 1:k + 2] + 1e-30)
    d = y0 - 2 * y1 + y2
    return f[k] + (0.5 * (y0 - y2) / d if d else 0.0) * (f[1] - f[0])


# label: (file under REFS, f0 search Hz, min seconds to the next pluck)
TAKES = {"ma": ("sitar/42192__*.flac", (150, 190), 5.0),
         "chinpen": ("sitar/42268__*.wav", (270, 310), 2.5)}


def stage_files(label, pat, lo=60.0, hi=1500.0, skip=(), div=1):
    """A pack's single notes, one pluck a file (the lap steel's open strings):
    each staged as it is, its f0 measured over its first second's harmonics."""
    import shutil
    os.makedirs(STAGED, exist_ok=True)
    for f in glob.glob(os.path.join(STAGED, "*.wav")):
        os.remove(f)
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8,
             "A": 9, "A#": 10, "B": 11}
    for n, p in enumerate(p for p in sorted(glob.glob(pat)) if not any(s in p for s in skip)):
        x, sr = read(p)
        a = int(np.flatnonzero(np.abs(x) > 0.1 * np.abs(x).max())[0])
        # THE NAME AN OCTAVE HIGH (as the pack labels it: E5.wav sounds E4,
        # its h2 the strongest line): the pitch refined near the name's, less
        # an octave -- the strongest peak alone read h2 on four of seven
        # (searched, not matched at the start: the taishogoto's are Mic_E5_2_1)
        m = re.search(r"([A-G]#?)(-?\d)", os.path.basename(p))
        if m:
            nom = 440.0 * 2 ** ((names[m.group(1)] + 12 * (int(m.group(2)) + 1) - 69 - 12) / 12.0)
            f0 = f0_of(x[a + int(0.1 * sr):a + int(1.1 * sr)], sr, nom * 0.97, nom * 1.03)
        else:
            # (div: read on the harmonic that number up -- the drone's own
            # fundamental is all but silent, its 4th the strongest)
            f0 = f0_of(x[a + int(0.1 * sr):a + int(1.1 * sr)], sr, lo * div, hi * div) / div
        name = "%s_%d_f0_%.2f.wav" % (label, n, f0)
        shutil.copy(p, os.path.join(STAGED, name))
        print("  %s -> %s" % (os.path.basename(p), name))


# the carved mandolin takes (wav/NN.wav, names.txt) with their pitch read by
# a harmonic sum (their file numbers are not note order): the medium layer's,
# 2.4 s and longer, across the range
MANDOLIN = ((57, 149.2), (55, 166.7), (53, 186.4), (52, 197.8), (50, 219.2), (48, 247.8),
            (58, 260.6), (47, 278.2), (45, 312.4), (44, 331.1), (42, 372.8), (40, 423.4),
            (37, 496.4))


def stage_mandolin():
    import shutil
    os.makedirs(STAGED, exist_ok=True)
    for f in glob.glob(os.path.join(STAGED, "*.wav")):
        os.remove(f)
    d = os.path.expanduser("~/Documents/refs/mandolin_eclectic/wav")
    for n, (i, f0) in enumerate(MANDOLIN):
        x, sr = read(os.path.join(d, "%02d.wav" % i))
        a = int(np.flatnonzero(np.abs(x) > 0.1 * np.abs(x).max())[0])
        f0 = f0_of(x[a + int(0.1 * sr):a + int(1.1 * sr)], sr, f0 * 0.98, f0 * 1.02)
        name = "medium_%d_f0_%.2f.wav" % (n, f0)
        shutil.copy(os.path.join(d, "%02d.wav" % i), os.path.join(STAGED, name))
        print("  %02d.wav -> %s" % (i, name))


# BEN'S UKULELE (sources.md, ukulele_ben/): its chromatic take, each string
# open to the 12th fret at mf, G (re-entrant, G4) then C, E, A
UKE_TAKE = os.path.expanduser("~/Documents/refs/ukulele_ben/03_chromatic_mf.wav")
UKE_NOTES = [s + k for s in (67, 60, 64, 69) for k in range(13)]


def stage_ukulele():
    """THE CHROMATIC TAKE, CUT: every onset (a 10 dB rise, over -50 dB) that
    rings 0.8 s or more, its pitch YIN's median over 0.05-0.9 s where periodic,
    kept within 0.4 semitone of a note in the uke's range -- a repeat of the
    note just kept REPLACING it (Ben flubbed one on the G string and played
    it again), one an octave over the next fret halved (YIN's octave slip), a
    segment with no stable pitch (a damp, a knock) skipped. Each cut from
    20 ms before its onset to its end."""
    from scipy.io import wavfile
    sys.path.insert(0, os.path.join(HERE, "examples"))
    from freesound_slice import onsets as fs_onsets, track
    os.makedirs(STAGED, exist_ok=True)
    for f in glob.glob(os.path.join(STAGED, "*.wav")):
        os.remove(f)
    sr, x = wavfile.read(UKE_TAKE)
    y = x[:, 0].astype(np.float64) / 32768.0
    on = fs_onsets(y, sr, rise_db=10.0, top_db=-50.0, gap=0.3) + [len(y)]
    got = []
    for a, b in zip(on[:-1], on[1:]):
        if b - a < 0.8 * sr:
            continue
        T = [t for t in track(y[a + int(0.05 * sr):a + int(0.9 * sr)], sr, 200, 1200) if t[1] < 0.2]
        if len(T) < 10:
            continue
        f0 = float(np.median([t[0] for t in T]))
        m = 69 + 12 * np.log2(f0 / 440.0)
        prev = got[-1][3] if got else None
        # ...AN OCTAVE HIGH where the next fret is an octave under it (YIN
        # read F#4's 2nd as its pitch, twice): halved
        if prev is not None and abs(m - 12 - (prev + 1)) < 0.5 and abs(m - (prev + 1)) >= 0.5:
            f0, m = f0 / 2.0, m - 12
        n = int(round(m))
        if abs(m - n) > 0.4 or not 59 <= n <= 82:
            continue
        if prev is not None and n == prev:
            got[-1] = (a, b, f0, n)                 # the note again: the second try
        else:
            got.append((a, b, f0, n))
    for n, (a, b, f0, note) in enumerate(got):
        seg = y[max(0, a - int(0.02 * sr)):b]
        name = "uke_%d_f0_%.2f.wav" % (n, f0)
        wavfile.write(os.path.join(STAGED, name), sr, (seg * 32767).astype(np.int16))
    have = sorted(n for _, _, _, n in got)
    print("  %d notes staged (of %d played): %s" % (len(got), len(UKE_NOTES), have))


def stage_live(label="ueno", pat="shamisen/195521__*.wav", min_next=0.3):
    """THE SHAMISEN'S PLUCKS, out of RTB45's live festival take (freesound
    195521, CC BY 4.0; sources.md "Ethnic programs"): every onset (a 12 dB
    rise in 10 ms, over -40 dB) that rings MIN_NEXT s or more before the next,
    whose first 0.3 s is pitched (YIN periodic in 60% of frames) and steady
    (pitch sd under 30 cents) -- fourteen in four minutes, twelve of them the
    open bass string at 142 Hz, the one with the sawari. Each cut from 20 ms
    before its onset to 20 ms before the next."""
    from scipy.io import wavfile
    sys.path.insert(0, os.path.join(HERE, "examples"))
    from freesound_slice import onsets as fs_onsets, track
    os.makedirs(STAGED, exist_ok=True)
    for f in glob.glob(os.path.join(STAGED, "*.wav")):
        os.remove(f)
    x, sr = read(glob.glob(os.path.join(REFS, pat))[0])
    on = fs_onsets(x, sr, rise_db=12.0, top_db=-40.0, gap=0.08) + [len(x)]
    n = 0
    for i, j in zip(on[:-1], on[1:]):
        if j - i < min_next * sr:
            continue
        T = track(x[i:j], sr, 100, 1500)
        if len(T) < 12:
            continue
        t = T[3:30]
        f = float(np.median(t[:, 0]))
        if (t[:, 1] < 0.2).mean() <= 0.6 or np.std(1200 * np.log2(t[:, 0] / f)) >= 30:
            continue
        seg = x[max(0, i - int(0.02 * sr)):j - int(0.02 * sr)]
        # THE TRACKER'S MEDIAN, not a spectral peak: over 0.3 s the peak's
        # bins are 4 Hz wide and it scattered 132-148 Hz around a steady 142
        name = "%s_%d_f0_%.2f.wav" % (label, n, f)
        wavfile.write(os.path.join(STAGED, name), sr,
                      (seg / max(np.abs(seg).max(), 1e-9) * 0.9 * 32767).astype(np.int16))
        print("  %-28s %.2f s" % (name, len(seg) / sr))
        n += 1


def stage():
    from scipy.io import wavfile
    os.makedirs(STAGED, exist_ok=True)
    for f in glob.glob(os.path.join(STAGED, "*.wav")):
        os.remove(f)
    for label, (pat, (lo, hi), min_next) in TAKES.items():
        src = glob.glob(os.path.join(REFS, pat))[0]
        x, sr = read(src)
        ons = onsets(x, sr) + [len(x) / sr]
        n = 0
        for a, b in zip(ons[:-1], ons[1:]):
            if b - a < min_next:
                continue
            seg = x[max(0, int((a - 0.02) * sr)):int((b - 0.05) * sr)]
            f0 = f0_of(seg[int(0.1 * sr):int(1.0 * sr)], sr, lo, hi)
            name = "%s_%d_f0_%.2f.wav" % (label, n, f0)
            wavfile.write(os.path.join(STAGED, name), sr,
                          (seg / max(np.abs(seg).max(), 1e-9) * 0.9 * 32767).astype(np.int16))
            print("  %-28s %.2f s" % (name, len(seg) / sr))
            n += 1


def plucks():
    """[(f0, path, take label)] of the staged plucks."""
    out = []
    for p in sorted(glob.glob(os.path.join(STAGED, "*.wav"))):
        m = re.search(r"([a-z]+)_\d+_f0_([0-9.]+)\.wav$", p)
        out.append((float(m.group(2)), p, m.group(1)))
    return out


def render(f0, secs):
    """Ours at f0 exactly. An Indian voice by the TUNING (a sitar's wheel is a
    meend, which locks to swaras): a secondary equal tuning whose Sa is this
    pluck's pitch, the note played on Sa. Any other by a static bend from the
    nearest note (2 semitones' range): a tuning, which every voice honours."""
    import mido
    import blockrender as B
    import tonelib as T
    indian = getattr(getattr(T, CLS), "tuning_family", None) == "indian"
    names = ("c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b")
    # THE TABLE THE RENDER USES, the renderer's own default where no TUNER:
    # bending from A440's equal steps put every note under hybrid440 ~1% flat
    # of its target (E3 162.8 Hz asked 164.5) -- harmless to decays and
    # levels, wrong for anything placed by frequency (a lap steel's strings)
    tab = B.tuning_table(TUNER or "hybrid440")
    near = min(tab, key=lambda n: abs(np.log2(tab[n] / f0)))
    note = 60 + near % 12 if indian else near
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    if BANK:
        t.append(mido.Message("control_change", channel=0, control=0, value=BANK, time=0))
    t.append(mido.Message("program_change", channel=0, program=PROG, time=0))
    if not indian:
        cents = 1200 * np.log2(f0 / tab[near])
        t.append(mido.Message("pitchwheel", channel=0, pitch=int(round(cents / 200.0 * 8191)), time=0))
    t.append(mido.Message("note_on", channel=0, note=note, velocity=100, time=0))
    t.append(mido.Message("note_off", channel=0, note=note, velocity=0, time=int(secs * 960)))
    B.EASTERN = "raga:et@%s:%.4f" % (names[near % 12], f0) if indian else None
    try:
        L, R = (B.render(m, TUNER) if TUNER else B.render(m))[:2]
    finally:
        B.EASTERN = None
    return 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64)), B.SR


def measure(x, sr, f0):
    """(decay dB/s h1-NH, ladder at 0.15 s, ladder at 2 s, bands) for one pluck."""
    w = int(0.005 * sr)
    e = np.convolve(x * x, np.ones(w) / w, "same")
    a = int(np.flatnonzero(e > e.max() * 0.01)[0])
    W = int(WIN * sr)
    win = np.hanning(W)
    Nf = 1 << 15
    fs = np.fft.rfftfreq(Nf, 1.0 / sr)
    L = []
    for j in range(int(T_END / HOP)):
        s = x[a + int(j * HOP * sr): a + int(j * HOP * sr) + W]
        if len(s) < W:
            break
        X = np.abs(np.fft.rfft(s * win, Nf))
        L.append([20 * np.log10(X[np.abs(fs - k * f0) < 4 + 0.01 * k * f0].max() + 1e-9)
                  for k in range(1, NH + 1)])
    L = np.array(L)
    tt = np.arange(len(L)) * HOP + WIN / 2
    rate = []
    for k in range(NH):
        y = L[:, k]
        ok = (tt > T_DECAY) & (y > y.max() - 45)
        rate.append(-np.polyfit(tt[ok], y[ok], 1)[0] if ok.sum() > 5 else np.nan)
    ref = L[0, 0]
    j2 = min(len(L) - 1, int(round((2.0 - WIN / 2) / HOP)))
    # the body's colour: harmonics to 13 kHz, 0.1-0.3 s
    s = x[a + int(0.1 * sr): a + int(0.3 * sr)]
    N = 1 << 17
    X = np.abs(np.fft.rfft(s * np.hanning(len(s)), N)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    hz, p = [], []
    m = 1
    while m * f0 < min(13000.0, 0.45 * sr):
        b = (f > m * f0 * 0.98) & (f < m * f0 * 1.02)
        hz.append(m * f0)
        p.append(X[b].max())
        m += 1
    hz, p = np.array(hz), np.array(p)
    db = 10 * np.log10(p / p.sum() + 1e-30)
    bands = np.full(len(CEN), np.nan)
    for k, c in enumerate(CEN):
        sel = np.abs(np.log2(hz / c)) <= 1 / 6.0
        if sel.any():
            bands[k] = 10 * np.log10(np.mean(10 ** (db[sel] / 10)))
    return np.array(rate), L[0] - ref, L[j2] - ref, bands


def both(step=1):
    rec, ours = [], []
    for f0, p, lab in plucks()[::step]:
        x, sr = read(p)
        rec.append((lab, f0, measure(x, sr, f0)))
        y, s2 = render(f0, 6.0)
        ours.append((lab, f0, measure(y, s2, f0)))
    return rec, ours


def fit_bright():
    """--fit=bright: tonal_dampening and the low-pass corner (bore_corner_hz,
    bore_order) on the 0.15 s ladder, h2-h12 where the take holds the
    harmonic 20 dB or more over its 2 s floor (the taishogoto's top is in its
    floor within a second), by grid."""
    import tonelib as T
    C = getattr(T, CLS)
    recs = []
    for f0, p, lab in plucks():
        x, sr = read(p)
        recs.append((f0, measure(x, sr, f0)))

    def err():
        e = []
        for f0, m in recs:
            y, s2 = render(f0, 1.0)
            o = measure(y, s2, f0)
            floor = np.nanmin(m[2])
            for k in range(1, min(12, NH)):
                if m[1][k] > floor + 20.0:
                    e.append((m[1][k] - o[1][k]) ** 2)
        return float(np.sqrt(np.mean(e)))
    best = None
    if hasattr(C, "low_string_tilt_db"):
        # A COURSE (the taishogoto's): the trio's level and the low string's
        # own tilt, the overall top as it stands
        # ...and the BODY'S LOW CORNER (bell_cutoff_hz, bell_order): a small
        # box radiates the low string's fundamental weakly -- E5's 3rd stands
        # 11 dB over its 1st
        C.low_string_tilt_db = 0.0
        if "--top" in sys.argv:
            # the top again, with the body's corner in place (bell_cutoff_hz)
            for td in (0.97, 0.85, 0.7):
                for bc in (2500.0, 5000.0, 9000.0):
                    C.tonal_dampening, C.bore_corner_hz = td, bc
                    e = err()
                    print("  tonal_dampening %.2f corner %5.0f Hz -> %.2f dB" % (td, bc, e), flush=True)
                    if best is None or e < best[0]:
                        best = (e, td, bc)
            print("    tonal_dampening = %s\n    bore_corner_hz = %s   (%.2f dB)" % (best[1], best[2], best[0]))
            return
        for og in (1.0, 2.0):
            for bc in (300.0, 600.0, 900.0, 1300.0):
                for bo in (1.0, 2.5):
                    C.octave_partner_gain, C.bell_cutoff_hz, C.bell_order = og, bc, bo
                    e = err()
                    print("  trio %.1f body corner %5.0f Hz order %.1f -> %.2f dB" % (og, bc, bo, e), flush=True)
                    if best is None or e < best[0]:
                        best = (e, og, bc, bo)
        print("    octave_partner_gain = %s\n    bell_cutoff_hz = %s\n    bell_order = %s   (%.2f dB)"
              % (best[1], best[2], best[3], best[0]))
        return
    tds, bcs, bos = ((0.97, 0.9, 0.8, 0.7), (1500.0, 2500.0, 3500.0), (1.4, 2.5))
    if "--wide" in sys.argv:
        # brighter and gentler (the ukulele's top held to its 12th harmonic)
        tds, bcs, bos = ((0.7, 0.5, 0.35), (3500.0, 6000.0, 10000.0), (0.7, 1.4))
    for td in tds:
        for bc in bcs:
            for bo in bos:
                C.tonal_dampening, C.bore_corner_hz, C.bore_order = td, bc, bo
                e = err()
                print("  tonal_dampening %.2f corner %5.0f Hz order %.1f -> %.2f dB" % (td, bc, bo, e), flush=True)
                if best is None or e < best[0]:
                    best = (e, td, bc, bo)
    print("    tonal_dampening = %s\n    bore_corner_hz = %s\n    bore_order = %s   (%.2f dB)"
          % (best[1], best[2], best[3], best[0]))


def report():
    rec, ours = both()

    def key(lab, f0):
        return (lab, int(round(12 * np.log2(f0 / 440.0))))
    for k in sorted({key(l, f) for l, f, _ in rec}, key=lambda q: (q[0], q[1])):
        sel = [i for i, (l, f, _) in enumerate(rec) if key(l, f) == k]
        f0 = np.median([rec[i][1] for i in sel])
        print("  == %s (%.1f Hz, %d plucks), h1-h16" % (k[0], f0, len(sel)))
        for name, kk in (("decay dB/s", 0), ("ladder 0.15 s", 1), ("ladder 2 s", 2)):
            R = np.nanmedian([rec[i][2][kk] for i in sel], 0)
            O = np.nanmedian([ours[i][2][kk] for i in sel], 0)
            print("  %-14s rec  %s" % (name, " ".join("%5.1f" % v for v in R[:16])))
            print("  %-14s ours %s" % ("", " ".join("%5.1f" % v for v in O[:16])))
    R = np.nanmedian([m[3] for _, _, m in rec], 0)
    O = np.nanmedian([m[3] for _, _, m in ours], 0)
    d = R - O
    print("  bands rec-ours " + " ".join("%d:%+.1f" % (c, v) for c, v in zip(CEN, d) if np.isfinite(v)))


DECAY = ("decay_db", "harmonic_decay_db", "decay_register_slope")


def fit_decay(maxfev=60):
    """--fit=decay: the string's decay law -- its rate, its rise with harmonic
    number and its register slope -- against each take's measured decay of
    h1-h12 (dB/s, the plucks' median), at each take's own pitch: two pitches,
    so the slope is fitted on the two. Nelder-Mead, the rates' rms."""
    from scipy.optimize import minimize
    import tonelib as T
    cls = getattr(T, CLS)
    groups = {}
    for f0, p, lab in plucks():
        if TAKE and lab != TAKE:
            continue
        x, sr = read(p)
        # by take AND pitch: a take of four strings is four pitches
        groups.setdefault((lab, int(round(12 * np.log2(f0 / 440.0)))), []).append((f0, measure(x, sr, f0)[0]))
    targets = [(float(np.median([f for f, _ in v])), np.nanmedian([r for _, r in v], 0)[:12])
               for v in groups.values()]
    x0 = np.array([float(getattr(cls, k)) for k in DECAY])
    best = [1e9, x0]

    def f(z):
        v = np.array([x0[0] * np.exp(z[0]), x0[1] * np.exp(z[1]), z[2]])
        for k, q in zip(DECAY, v):
            setattr(cls, k, float(q))
        err = []
        for f0, R in targets:
            y, sr = render(f0, 4.0)
            O = measure(y, sr, f0)[0][:12]
            ok = np.isfinite(R) & np.isfinite(O)
            err.extend((O - R)[ok])
        e = float(np.sqrt(np.mean(np.square(err))))
        if e < best[0]:
            best[:] = [e, v]
            print("  %5.2f dB/s  %s" % (e, " ".join("%s=%.4g" % kv for kv in zip(DECAY, v))), flush=True)
        return e
    minimize(f, np.zeros(3), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": np.vstack([np.zeros(3), np.diag([0.4, 0.5, 0.4])]),
                      "xatol": 0.02, "fatol": 0.05})
    for k, q in zip(DECAY, best[1]):
        print("    %s = %.4g" % (k, q))


def fit_body(passes=4):
    """--fit=body: FormantBody.body_trim_db by absolute frequency -- every
    harmonic of every pluck at 0.1-0.3 s pooled by third-octave of where it
    sounds (both takes), each pass adding half of recorded - ours, the median
    removed (colour, not level), as steel_fit.py --body does."""
    import tonelib as T
    cls = getattr(T, CLS)
    ps = [q for q in plucks() if not TAKE or q[2] == TAKE]
    R = np.nanmedian([measure(*read(p), f0)[3] for f0, p, _ in ps], 0)
    trim = dict((int(round(c)), v) for c, v in (cls.body_trim_db or ()))
    for n in range(passes + 1):
        O = np.nanmedian([measure(*render(f0, 1.0), f0)[3] for f0, _, _ in ps[::2]], 0)
        d = R - O
        ok = np.isfinite(d)
        d = d - np.nanmedian(d)
        print("  pass %d: rms %.2f dB  %s" % (n, np.sqrt(np.nanmean(d[ok] ** 2)),
              " ".join("%d:%+.1f" % (CEN[k], d[k]) for k in np.flatnonzero(ok))), flush=True)
        if n == passes:
            break
        for k in np.flatnonzero(ok):
            if CEN[k] > TOP_HZ:
                continue        # over the top a take's noise, not its harmonics
            c = int(round(CEN[k]))
            trim[c] = max(-24.0, min(24.0, trim.get(c, 0.0) + 0.5 * float(d[k])))
        cls.body_trim_db = tuple((c, round(v, 1)) for c, v in sorted(trim.items()))
    print("    body_trim_db = %s" % (cls.body_trim_db,))


def ab(out, secs=5.0):
    """--ab=OUT.wav: each take's plucks (the Ma string's four, three of
    chinpen's strokes), recorded then ours at its pitch, level-matched over
    the first second."""
    import wave
    from scipy.signal import resample_poly
    parts, sr = [], 44100
    ps = plucks()
    labs = []
    for q in ps:
        if q[2] not in labs:
            labs.append(q[2])
    # the sitar's Ma plucks first, then up to four of every take -- or, from a
    # live take of short plucks (the shamisen's), the longest at each pitch
    # and then the longest of the rest, to six
    labs.sort(key=lambda l: (l != "ma", l))
    if T_END < 1.0:
        pick = []
        for l in labs:
            rs = sorted([r for r in ps if r[2] == l], key=lambda r: -len(read(r[1])[0]))
            by = {}
            for r in rs:
                by.setdefault(int(round(12 * np.log2(r[0] / 440.0))), r)
            first = list(by.values())
            pick += first + [r for r in rs if r not in first][:max(0, 6 - len(first))]
    else:
        pick = [q for l in labs for q in [r for r in ps if r[2] == l][:4]]
    for f0, p, lab in pick:
        x, sr = read(p)
        x = x[:int(secs * sr)]
        y, s2 = render(f0, min(secs, len(x) / sr))
        w = int(0.005 * s2)
        e = np.convolve(y * y, np.ones(w) / w, "same")
        y = y[max(0, int(np.flatnonzero(e > e.max() * 0.01)[0]) - int(0.02 * s2)):]
        if s2 != sr:
            y = resample_poly(y, sr, s2)
        y = y[:len(x)]
        g = np.sqrt(np.mean(x[:sr] ** 2) / max(np.mean(y[:sr] ** 2), 1e-30))
        gap = np.zeros(int(0.4 * sr))
        parts += [x, gap, y * g, gap, gap]
        print("  %s %.1f Hz" % (os.path.basename(p), f0))
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


JBANDS = ((1500, 3000), (3000, 6000), (6000, 12000))
JAWARI = ("bloom_seconds", "bloom_center_hz", "bloom_octaves", "bloom_gain", "bloom_scatter")


def band_course(x, sr, secs=1.5, hop=0.05):
    """Each of JBANDS' level every HOP s for SECS from the pluck, dB re the
    band under 1 kHz at the same time: the buzz's growth, as a shape."""
    from scipy.signal import butter, sosfilt
    w = int(0.005 * sr)
    e = np.convolve(x * x, np.ones(w) / w, "same")
    a = int(np.flatnonzero(e > e.max() * 0.01)[0])
    seg = x[a:a + int((secs + hop) * sr)]
    lo = sosfilt(butter(4, 1000, "lp", fs=sr, output="sos"), seg)
    h = int(hop * sr)
    out = []
    for f1, f2 in JBANDS:
        b = sosfilt(butter(4, [f1, f2], "bp", fs=sr, output="sos"), seg)
        out.append([10 * np.log10(np.mean(b[i:i + h] ** 2) / max(np.mean(lo[i:i + h] ** 2), 1e-30))
                    for i in range(0, int(secs * sr), h)])
    return np.array(out)


def fit_jawari(maxfev=70):
    """--fit=jawari: the buzz's growth as a late copy of the upper partials
    (SynthProperties' bloom, banded): its delay, the band's centre and width,
    the copy's gain and the arrivals' scatter, against each take's high bands
    over the first 1.5 s re the band under 1 kHz (band_course), the plucks'
    median, both takes."""
    from scipy.optimize import minimize
    import tonelib as T
    cls = getattr(T, CLS)
    cls.bloom_banded = True
    cls.bloom_swell = 1.0
    groups = {}
    for f0, p, lab in plucks():
        if TAKE and lab != TAKE:
            continue
        groups.setdefault(lab, []).append((f0, band_course(*read(p))))
    targets = [(float(np.median([f for f, _ in v])), np.median([c for _, c in v], 0)) for v in groups.values()]
    x0 = np.array([0.20, 3500.0, 1.2, 3.0, 0.5])
    best = [1e9, x0]

    def val(z):
        return np.array([x0[0] * np.exp(z[0]), x0[1] * np.exp(z[1]), x0[2] * np.exp(z[2]),
                         x0[3] * np.exp(z[3]), min(1.0, max(0.0, x0[4] + z[4]))])

    def f(z):
        v = val(z)
        for k, q in zip(JAWARI, v):
            setattr(cls, k, float(q))
        err = []
        for f0, R in targets:
            O = band_course(*render(f0, 1.8))
            err.extend((O - R).ravel())
        e = float(np.sqrt(np.mean(np.square(err))))
        if e < best[0]:
            best[:] = [e, v]
            print("  %5.2f dB  %s" % (e, " ".join("%s=%.4g" % kv for kv in zip(JAWARI, v))), flush=True)
        return e
    minimize(f, np.zeros(5), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": np.vstack([np.zeros(5), np.diag([0.5, 0.4, 0.4, 0.6, 0.3])]),
                      "xatol": 0.02, "fatol": 0.05})
    for k, q in zip(JAWARI, best[1]):
        print("    %s = %.4g" % (k, q))


PBANDS = ((0, 1000), (1500, 3000), (3000, 6000), (6000, 12000))
PROMPT = ("prompt_dbs", "aftersound_share", "prompt_max_hz")


def early_course(x, sr, secs=None, hop=0.02):
    """Each of PBANDS' level every HOP s for SECS from the pluck, each re its
    own mean: the SHAPE of each band's first half-second, its level apart."""
    from scipy.signal import butter, sosfilt
    secs = secs or P_SECS
    w = int(0.002 * sr)
    e = np.convolve(x * x, np.ones(w) / w, "same")
    a = int(np.flatnonzero(e > e.max() * 0.01)[0])
    seg = x[a:a + int((secs + hop) * sr)]
    h = int(hop * sr)
    out = []
    for f1, f2 in PBANDS:
        y = (sosfilt(butter(4, f2, "lp", fs=sr, output="sos"), seg) if f1 == 0
             else sosfilt(butter(4, [f1, f2], "bp", fs=sr, output="sos"), seg))
        v = np.array([10 * np.log10(np.mean(y[i:i + h] ** 2) + 1e-20) for i in range(0, int(secs * sr), h)])
        out.append(v - v.mean())
    return np.array(out)


def fit_prompt(maxfev=50):
    """--fit=prompt: the low partials' two-stage decay -- a prompt rate under
    a frequency, a share of it remaining at the law's own rate -- against the
    take's bands' first 0.6 s, each band's shape (early_course)."""
    from scipy.optimize import minimize
    import tonelib as T
    cls = getattr(T, CLS)
    g = [(f0, early_course(*read(p))) for f0, p, lab in plucks() if not TAKE or lab == TAKE]
    f0 = float(np.median([f for f, _ in g]))
    R = np.median([c for _, c in g], 0)
    x0 = np.array(PROMPT_X0)
    best = [1e9, x0]

    def val(z):
        return np.array([x0[0] * np.exp(z[0]), min(0.95, max(0.01, x0[1] + z[1])), x0[2] * np.exp(z[2])])

    def f(z):
        v = val(z)
        for k, q in zip(PROMPT, v):
            setattr(cls, k, float(q))
        O = early_course(*render(f0, 1.0))
        e = float(np.sqrt(np.mean((O - R) ** 2)))
        if e < best[0]:
            best[:] = [e, v]
            print("  %5.2f dB  %s" % (e, " ".join("%s=%.4g" % kv for kv in zip(PROMPT, v))), flush=True)
        return e
    minimize(f, np.zeros(3), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": np.vstack([np.zeros(3), np.diag([0.6, 0.25, 0.5])]),
                      "xatol": 0.02, "fatol": 0.03})
    for k, q in zip(PROMPT, best[1]):
        print("    %s = %.4g" % (k, q))


QUICK = ("bloom_seconds", "bloom_gain", "bloom_center_hz", "bloom_octaves")


def fit_quick(maxfev=50):
    """--fit=quick: the buzz's QUICK rise -- a short late copy of the upper
    partials, little scattered -- against every band's first 0.6 s
    (early_course), the prompt fall in place."""
    from scipy.optimize import minimize
    import tonelib as T
    cls = getattr(T, CLS)
    cls.bloom_banded = True
    cls.bloom_swell = 0.5
    cls.bloom_scatter = 0.2
    g = [(f0, early_course(*read(p))) for f0, p, lab in plucks() if not TAKE or lab == TAKE]
    f0 = float(np.median([f for f, _ in g]))
    R = np.median([c for _, c in g], 0)
    x0 = np.array([0.05, 1.0, 5000.0, 1.5])
    best = [1e9, x0]

    def f(z):
        v = x0 * np.exp(z)
        for k, q in zip(QUICK, v):
            setattr(cls, k, float(q))
        O = early_course(*render(f0, 1.0))
        e = float(np.sqrt(np.mean((O - R) ** 2)))
        if e < best[0]:
            best[:] = [e, v]
            print("  %5.2f dB  %s" % (e, " ".join("%s=%.4g" % kv for kv in zip(QUICK, v))), flush=True)
        return e
    minimize(f, np.zeros(4), method="Nelder-Mead",
             options={"maxfev": maxfev, "initial_simplex": np.vstack([np.zeros(4), np.diag([0.5, 0.7, 0.4, 0.4])]),
                      "xatol": 0.02, "fatol": 0.03})
    for k, q in zip(QUICK, best[1]):
        print("    %s = %.4g" % (k, q))


TAKE = None     # --take=ma: fit to one take's plucks only
TOP_HZ = 11500.0   # the body fit's last band: above it one pluck's noise, not harmonics


def main(argv):
    global TAKE, PROG, CLS, STAGED, BANK
    TAKE = next((a.split("=", 1)[1] for a in argv if a.startswith("--take=")), None)
    voice = next((a.split("=", 1)[1] for a in argv if a.startswith("--voice=")), "sitar")
    PROG, CLS, folder = VOICES[voice]
    STAGED = os.path.join(REFS, "staged", folder)
    globals().update(VOICE_OPTS.get(voice, {}))
    BANK = BANKS.get(voice, 0)
    if "--stage" in argv:
        if voice == "lapsteel":
            stage_files("open", os.path.expanduser("~/Documents/refs/lapsteel/x/samples/open/*.wav"))
        elif voice == "mandolin":
            stage_mandolin()
        elif voice == "ukulele":
            stage_ukulele()
        elif voice == "taishodrone":
            stage_files("drone", os.path.expanduser(
                "~/Documents/refs/taishogoto/x/Taishogoto/Taishogoto Samples/Drone_Mic_*.wav"), 94.0, 102.0, div=4)
        elif voice == "taisho":
            # named by the trio, an octave over the low string (stage_files)
            stage_files("mic", os.path.expanduser(
                "~/Documents/refs/taishogoto/x/Taishogoto/Taishogoto Samples/Mic_*_2_1.wav"),
                # G4 left out: its low string is 29 dB under the trio (the open
                # string, no key down?), so its fundamental is not the note's
                skip=("Mic_G4_",))
        else:
            stage_live() if voice == "shamisen" else stage()
        return 0
    if "--fit=decay" in argv:
        # --nh=N: the decay read on h1-hN only (a take whose upper harmonics
        # sink into its floor in a second reads them as 0 dB/s)
        globals()["NH"] = int(next((a.split("=")[1] for a in argv if a.startswith("--nh=")), NH))
        fit_decay()
        return 0
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--ab=")), None)
    if out:
        ab(out)
        return 0
    if "--fit=quick" in argv:
        fit_quick()
        return 0
    if "--fit=prompt" in argv:
        fit_prompt()
        return 0
    if "--fit=jawari" in argv:
        fit_jawari()
        return 0
    if "--fit=body" in argv:
        fit_body()
        return 0
    if "--fit=bright" in argv:
        fit_bright()
        return 0
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
