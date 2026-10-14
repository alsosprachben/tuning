#!/usr/bin/env python3
"""Fit the gunshot (GM 127) to a 9 mm at 15 m: the blast's noise beside the
N-wave. sources.md "Sound effects".

    python3 -I examples/gunshot_fit.py measure     the shots, and ours
    python3 -I examples/gunshot_fit.py fit         the blast's noise rows (writes tonelib.py)
    python3 -I examples/gunshot_fit.py ab OUT.wav [--hall]  the shots, then ours (dry, or in the hall)

THE TAKES (CC0, Freesound): johanwestling's 9 mm pistol at 15 m on a range
(377789, five shots, Sony PCM-M10) -- the distance the class stands at; and
his close shots of three guns (377786), a 0.1-0.4 ms crack peaking at 2-4
kHz, read beside it, not fitted.

WHAT THE 15 m SHOTS HOLD, their first 6 ms: a peak in the 125-250 Hz octave
(the N-wave the class builds for G3, A-Team's key, peaks there too) falling
only ~3 dB an octave above it -- -20 dB at 16 kHz, where an N-wave alone
falls ~6 -- and the shot still -4 dB at 5-20 ms where the N-wave alone is
-16. The tail past 20 ms is the range's echo, and in the class the room's:
not fitted.
"""
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import upright_fit as U

FS = os.path.expanduser("~/Documents/refs/freesound/gunshot")
SHOT15 = os.path.join(FS, "377789__johanwestling__gun_9mm_15m_in_front_m10.wav")
OCT = (63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
THIRDS = tuple(int(round(c * 2 ** (k / 3.0))) for c in (50, 100, 200, 400, 800, 1600, 3200, 6400, 12800)
               for k in (0, 1, 2) if c * 2 ** (k / 3.0) < 18000)
KEY = 55


def load(p):
    from scipy.io import wavfile
    import warnings
    warnings.simplefilter("ignore")
    sr, x = wavfile.read(p)
    x = x.astype(np.float64)
    x = x.mean(1) if x.ndim > 1 else x
    return x / np.abs(x).max(), sr


def onsets(x, sr):
    from scipy.signal import find_peaks
    w = int(0.002 * sr)
    c = np.concatenate(([0.0], np.cumsum(x * x)))
    e = np.sqrt((c[w:] - c[:-w]) / w)
    pk, _ = find_peaks(e, height=0.2, distance=int(0.5 * sr))
    out = []
    for q in pk:
        a0 = max(0, q - int(0.05 * sr))
        s = x[a0:q + w]
        out.append(a0 + int(np.flatnonzero(np.abs(s) > 0.3 * np.abs(s).max())[0]))
    return out


def reading(x, sr, a):
    """(the first 20 ms by octave, dB re the loudest -- the blast and its
    boom; the 5-20 ms window, dB re the first 5)."""
    seg = x[a:a + int(0.02 * sr)]
    X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 14)) ** 2
    f = np.fft.rfftfreq(1 << 14, 1.0 / sr)
    o = np.array([10 * np.log10(X[(f >= c / np.sqrt(2)) & (f < c * np.sqrt(2))].sum() + 1e-20) for c in OCT])
    w0 = 10 * np.log10(np.mean(x[a:a + int(0.005 * sr)] ** 2) + 1e-20)
    w1 = 10 * np.log10(np.mean(x[a + int(0.005 * sr):a + int(0.02 * sr)] ** 2) + 1e-20)
    return o - o.max(), w1 - w0


def target():
    x, sr = load(SHOT15)
    rs = [reading(x, sr, a) for a in onsets(x, sr)]
    return np.mean([r[0] for r in rs], 0), float(np.mean([r[1] for r in rs]))


def ours():
    y, sr = U.render(127, KEY, 100, 1.0)
    a = int(np.flatnonzero(np.abs(y) > 0.3 * np.abs(y).max())[0])
    return reading(y, sr, a)


def measure():
    R, w = target()
    print("  9 mm at 15 m: octaves %s  5-20 ms %+.1f dB" % (" ".join("%+4.0f" % v for v in R), w))
    O, wo = ours()
    print("  ours (G3):    octaves %s  5-20 ms %+.1f dB" % (" ".join("%+4.0f" % v for v in O), wo))


def fit(passes=12):
    """strike_noise_db (third-octave rows, dB re the note's gain) by octave
    toward the shots' first 6 ms, and strike_noise_dbs toward their 5-20 ms
    level; written into tonelib.py."""
    import tonelib as T
    cls = T.GunshotProperties
    R, w = target()
    nb = np.full(len(OCT), -40.0)
    cls.strike_noise_dbs = 600.0
    cls.strike_noise_fade_s = 0.0002
    cls.strike_noise_octave_db = 0.0
    cls.strike_noise_len_s = 0.3

    def band(c):
        return int(np.argmin([abs(np.log2(c / o)) for o in OCT]))
    best = None
    for it in range(passes + 1):
        cls.strike_noise_db = tuple((c, round(float(nb[band(c)]), 1)) for c in THIRDS)
        O, wo = ours()
        d = R - O
        e = float(np.sqrt(np.mean(d ** 2) + 0.5 * (w - wo) ** 2))
        print("  pass %d: shot - ours by octave %s (rms %.1f); 5-20 ms %+.1f against %+.1f; dB/s %.0f; error %.2f" % (
            it, " ".join("%+.0f" % v for v in d), np.sqrt(np.mean(d ** 2)), wo, w, cls.strike_noise_dbs, e), flush=True)
        if best is None or e < best[0]:
            best = (e, cls.strike_noise_db, cls.strike_noise_dbs)
        if it == passes:
            break
        nb += 0.7 * d
        # a slower fall holds the 5-20 ms window up
        cls.strike_noise_dbs = float(np.clip(cls.strike_noise_dbs * 10 ** (-(w - wo) / 40.0), 50.0, 5000.0))
    cls.strike_noise_db, cls.strike_noise_dbs = best[1], best[2]
    print("  best: error %.2f" % best[0])
    path = os.path.join(os.path.dirname(HERE), "tonelib.py")
    src = open(path).read()
    a = src.index("class GunshotProperties(")
    b = src.index("\nclass ", a + 10)
    body = src[a:b].rstrip("\n")
    i = body.index("\n    def pulse_length(")
    add = ("    strike_noise_db = %s\n    strike_noise_dbs = %.1f\n    strike_noise_fade_s = 0.0002\n"
           "    strike_noise_octave_db = 0.0\n    strike_noise_len_s = 0.3\n" % (cls.strike_noise_db, cls.strike_noise_dbs))
    for k in ("strike_noise_db", "strike_noise_dbs", "strike_noise_fade_s", "strike_noise_octave_db", "strike_noise_len_s"):
        body = re.sub(r"^    %s = .*\n" % k, "", body, flags=re.M)
        i = body.index("\n    def pulse_length(")
    body = body[:i + 1] + add + body[i + 1:]
    open(path, "w").write(src[:a] + body + "\n" + src[b:])
    print("  written")


def hall_shot(secs=2.5):
    """Ours at G3 rendered as the corpus is -- the hall, roomtail, at the
    class's own distance (gunshot_distance_ab.render): a shot is mostly its
    room. (mono, sr)"""
    import subprocess
    import tempfile
    import mido
    import gunshot_distance_ab as G
    d = tempfile.mkdtemp(prefix="gunshot_fit_")
    m = mido.MidiFile(ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=10, program=127, time=0))
    t.append(mido.Message("note_on", channel=10, note=KEY, velocity=120, time=10))
    t.append(mido.Message("note_off", channel=10, note=KEY, time=120))
    t.append(mido.Message("note_off", channel=10, note=KEY, time=int(secs * 960)))
    mid = os.path.join(d, "shot.mid")
    m.save(mid)
    wav = G.render(mid, os.path.join(d, "shot.wav"))
    y, sr = load(wav)
    return y, sr


def ab(out, hall=False):
    """Each of three shots at 15 m (its range echo kept), then ours -- dry,
    or (hall) in the hall as the corpus renders it."""
    import harpsi_ab as A
    from roomtail import write_wav
    gap = np.zeros(int(0.5 * A.SR))
    A.NOTE_S = 2.5 if hall else 1.2
    x, sr = load(SHOT15)
    if hall:
        y, sr2 = hall_shot()
        a2 = int(np.flatnonzero(np.abs(y) > 0.3 * np.abs(y).max())[0])
        y = y[max(0, a2 - int(0.02 * sr2)):]
    else:
        y, sr2 = U.render(127, KEY, 100, 1.0)
    parts = []
    for a in onsets(x, sr)[:3]:
        parts += [A.fit_note(x[max(0, a - int(0.02 * sr)):a + int(A.NOTE_S * sr)], sr), gap]
        parts += [A.fit_note(y, sr2), gap, gap]
    z = np.concatenate(parts)
    write_wav(out, np.stack([z, z], 1), A.SR)


def main(argv):
    if argv[1:2] == ["measure"]:
        measure()
    elif argv[1:2] == ["fit"]:
        fit()
    elif argv[1:2] == ["ab"]:
        ab(argv[2], hall="--hall" in argv)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
