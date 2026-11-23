"""GS 105.8 Rabab's colour, fitted to the only open rubab found: the solo
that opens belamalta10's "3 continents" (Freesound 513846, CC0: GarageBand's
rubab loop, before the pandeiro and talking drum come in at 2.0 s;
~/Documents/refs/freesound/rubab/, sources.md).

Its seven notes (232-277 Hz, 0.12-0.4 s each, cut by the next) are read
from 20 ms after each onset to 10 ms before the next: each harmonic's peak,
dB re the note's strongest, pooled into third-octave bands by where it
sounds. Ours, each note at its pitch and length, read the same way;
body_trim_db moves by the bands' median miss.

    python3 examples/rabab_fit.py            # the bands, take and ours
    python3 examples/rabab_fit.py --fit      # body_trim_db, 4 passes
    python3 examples/rabab_fit.py --ab=DIR   # the solo, then ours on its notes
"""
import glob
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
from drum_fit import read  # noqa: E402

TAKE = os.path.expanduser("~/Documents/refs/freesound/rubab/513846__*.wav")
SOLO_END = 2.0
# THE OPEN TAKE (since 2026-11-23, licences.md L6: the GarageBand loop's CC0
# was not its uploader's to give): RABAB_REF=ermlick -- Rich Ermlick playing
# the Afghan rubab alone, 6 min 14 s ("Rich Ermlick plays the Afghan
# Ru'bab", YouTube o-_CUFyHZ98, CC BY as its uploader marks it; AAC 129
# kb/s, sound to ~15 kHz; ~/Documents/refs/rabab_ermlick), the whole solo read
REF = os.environ.get("RABAB_REF", "loop")
if REF == "ermlick":
    TAKE = os.path.expanduser("~/Documents/refs/rabab_ermlick/ermlick_rubab.m4a")
    SOLO_END = 374.0
CEN = 2 ** np.arange(np.log2(160), np.log2(6000), 1 / 3.0)


def load():
    with tempfile.TemporaryDirectory() as d:
        w = os.path.join(d, "t.wav")
        if TAKE.endswith(".m4a"):
            subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-i", TAKE, "-ac", "1", "-c:a", "pcm_f32le", w],
                           check=True)
        else:
            subprocess.run(["sox", glob.glob(TAKE)[0], "-e", "floating-point", "-b", "32", "-c", "1", w],
                           check=True)
        x, sr = read(w)
    return x.reshape(len(x), -1).mean(1), sr


def notes(x, sr):
    """[(start s, end s, f0)] in the solo: onsets by an 8 dB rise in 25 ms,
    the pitch by harmonic score."""
    seg = x[:int((SOLO_END + 0.05) * sr)]
    hop = int(0.005 * sr)
    e = 10 * np.log10(np.convolve(seg ** 2, np.ones(hop) / hop, "same")[::hop] + 1e-12)
    ons = []
    for i in range(4, len(e) - 4):
        if e[i + 2] - e[i - 3] > 8 and e[i + 2] > e.max() - 35 and (not ons or i - ons[-1] > 30):
            ons.append(i)
    ons = [i * 0.005 for i in ons]
    out = []
    N = 1 << 17
    f = np.fft.rfftfreq(N, 1 / sr)
    for a, b in zip(ons, ons[1:] + [SOLO_END]):
        s = x[int((a + 0.02) * sr):int((b - 0.01) * sr)]
        L = np.log(np.abs(np.fft.rfft(s * np.hanning(len(s)), N)) ** 2 + 1e-20)

        def at(hz):
            i = int(round(hz / f[1]))
            w = max(2, int(0.006 * hz / f[1]))
            return L[max(0, i - w):i + w + 1].max()
        f0 = max((np.mean([at(c * h) for h in range(1, 9)]) - np.mean([at(c * (h + 0.5)) for h in range(1, 9)]), c)
                 for c in np.arange(120, 900, 0.25))[1]
        out.append((a, b, float(f0)))
    return out


def bands(s, sr, f0):
    """Third-octave bands (CEN): the harmonics in each, their peaks' mean in
    dB, re the note's strongest harmonic."""
    N = 1 << 17
    f = np.fft.rfftfreq(N, 1 / sr)
    Y = 20 * np.log10(np.abs(np.fft.rfft(s * np.hanning(len(s)), N)) + 1e-12)
    hz, lv = [], []
    h = 1
    while h * f0 < 6000:
        hz.append(h * f0)
        lv.append(Y[(f > h * f0 * 0.985) & (f < h * f0 * 1.015)].max())
        h += 1
    hz, lv = np.array(hz), np.array(lv) - max(lv)
    out = np.full(len(CEN), np.nan)
    for i, c in enumerate(CEN):
        m = np.abs(np.log2(hz / c)) <= 1 / 6.0
        if m.any():
            out[i] = 10 * np.log10(np.mean(10 ** (lv[m] / 10.0)))
    return out


def ours(f0, secs):
    import pluck_fit as P
    P.PROG, P.CLS, P.BANK = 105, "RababProperties", 8
    y, sr = P.render(f0, secs + 0.2)
    k = int(np.flatnonzero(np.abs(y) > 0.05 * np.abs(y).max())[0])
    return y[k:], sr


def compare():
    x, sr = load()
    R, O = [], []
    ns = notes(x, sr)
    if REF == "ermlick":
        # (inside the pitch search, not on its edge: a misread; every 4th note)
        ns = [n for n in ns if 125.0 < n[2] < 880.0][::int(os.environ.get("RABAB_STEP", "4"))]
    for a, b, f0 in ns:
        R.append(bands(x[int((a + 0.02) * sr):int((b - 0.01) * sr)], sr, f0))
        y, s2 = ours(f0, b - a)
        O.append(bands(y[int(0.02 * s2):int((b - a - 0.01) * s2)], s2, f0))
    return np.nanmedian(R, 0), np.nanmedian(O, 0)


def decays(s, sr, f0, nh=6, t0=0.03):
    """Harmonics 1-NH's fall, dB/s: a line through each one's 10 ms band
    envelope from T0 to 30 ms before the segment's end (the next pluck)."""
    from scipy.signal import butter, sosfiltfilt
    w = int(0.01 * sr)
    out = []
    for h in range(1, nh + 1):
        fh = h * f0
        if fh * 1.08 > 0.45 * sr:
            out.append(np.nan)
            continue
        y = sosfiltfilt(butter(2, [fh * 0.95, fh * 1.05], btype="band", fs=sr, output="sos"), s)
        e = 20 * np.log10(np.sqrt(np.convolve(y * y, np.ones(w) / w, "same")) + 1e-12)
        a, b = int(t0 * sr), len(e) - int(0.03 * sr)
        if b - a < int(0.25 * sr) or e[a:b].max() < e.max() - 40:
            out.append(np.nan)
            continue
        t = np.arange(a, b, w) / sr
        out.append(-float(np.polyfit(t, e[a:b:w], 1)[0]))
    return np.array(out)


def decay_compare(min_len=0.6, step=3):
    """The take's notes of MIN_LEN or more, each harmonic's fall, against
    ours at the note's pitch and length: the medians, and ours over the take's."""
    x, sr = load()
    ns = [n for n in notes(x, sr) if n[1] - n[0] >= min_len and 125.0 < n[2] < 880.0][::step]
    R, O = [], []
    for a, b, f0 in ns:
        R.append(decays(x[int(a * sr):int((b - 0.01) * sr)], sr, f0))
        y, s2 = ours(f0, b - a)
        O.append(decays(y[:int((b - a - 0.01) * s2)], s2, f0))
    R, O = np.array(R), np.array(O)
    print("  %d notes of %.1f s or more: h1-h6 dB/s, take | ours | ours/take" % (len(ns), min_len))
    print("    " + " ".join("%5.1f" % v for v in np.nanmedian(R, 0)) + "  |  "
          + " ".join("%5.1f" % v for v in np.nanmedian(O, 0)) + "  |  "
          + " ".join("%4.2f" % v for v in np.nanmedian(O / R, 0)))
    return R, O


def ab(out):
    """OUT/rabab_ab.wav: the take's solo, then ours playing its seven notes
    at their times and pitches, each held until the next begins (its
    note-off then: the take's player stops each string before the next
    pluck), its release left to ring, at one peak."""
    import blockrender as B
    x, sr = load()
    end = SOLO_END if REF != "ermlick" else 25.0         # (Ermlick's: his first 25 s)
    ns = [n for n in notes(x, sr) if n[1] <= end and 125.0 < n[2] < 880.0]
    t0 = ns[0][0] - 0.05
    rec = x[int(t0 * sr):int(end * sr)]
    z = np.zeros(len(rec) + int(0.6 * sr))
    import pluck_fit as P
    P.PROG, P.CLS, P.BANK = 105, "RababProperties", 8
    for a, b, f0 in ns:
        y, s2 = P.render(f0, b - a)
        y = y[int(np.flatnonzero(np.abs(y) > 0.05 * np.abs(y).max())[0]):]
        k = int((a - t0) * sr)
        n = min(len(y), len(z) - k)
        z[k:k + n] += y[:n]
    rec = rec * 0.5 / np.abs(rec).max()
    z = z * 0.5 / np.abs(z).max()
    w = np.concatenate([rec, np.zeros(int(0.8 * sr)), z])
    f = os.path.join(out, "rabab_ab.wav")
    B.write_wav(f, w, w)
    print("  " + f)


def main(argv):
    if "--decay" in argv:
        decay_compare()
        return 0
    ab_out = next((a[5:] for a in argv if a.startswith("--ab=")), None)
    if ab_out:
        return ab(ab_out)
    passes = 4 if "--fit" in argv else 0
    import tonelib
    C = tonelib.RababProperties
    for n in range(passes + 1):
        R, O = compare()
        d = R - O
        ok = np.isfinite(d)
        print("  pass %d: rms %.1f dB over %d bands\n    take %s\n    ours %s" % (
            n, np.sqrt(np.mean(d[ok] ** 2)), ok.sum(),
            " ".join("%d:%+.0f" % (c, v) for c, v in zip(CEN, R) if np.isfinite(v)),
            " ".join("%d:%+.0f" % (c, v) for c, v in zip(CEN, O) if np.isfinite(v))), flush=True)
        if n == passes:
            break
        tab = dict(getattr(C, "body_trim_db", ()) or ())
        keys = [int(round(c)) for c in CEN]
        if sorted(tab) != keys:
            tab = {k: 0.0 for k in keys}
        have = [i for i in range(len(CEN)) if ok[i]]
        for i, k in enumerate(keys):
            j = i if ok[i] else min(have, key=lambda q: abs(q - i))
            tab[k] = round(float(np.clip(tab[k] + d[j], -40, 30)), 1)
        C.body_trim_db = tuple(sorted(tab.items()))
    if passes:
        print("    body_trim_db = %s" % (C.body_trim_db,))


if __name__ == "__main__":
    main(sys.argv[1:])
