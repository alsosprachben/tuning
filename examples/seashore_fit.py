#!/usr/bin/env python3
"""Fit the seashore (GM 122) to VCSL's ocean drum (CC0;
~/Documents/refs/vcsl/oceandrum, three sustained takes, sources.md).

    seashore_fit.py              measure: recorded against ours
    seashore_fit.py --fit        the colour (band by band), the swell, the level
    seashore_fit.py --ab=OUT.wav a take, then ours

AN OCEAN DRUM IS THE ORCHESTRA'S SEA: beads rolled across a drumhead as the
frame is tilted. Measured, it is NOT the dark surf the class asserted: a
continuous hiss peaking at 1.3-2.6 kHz, 20-30 dB down under 300 Hz, rolling
off above 4 kHz; swelling irregularly, a swell every 0.4-2 s (about 1.1 s),
the level moving 6-10 dB; the hiss smooth under 4 kHz (kurtosis ~3) and the
top octave impulsive (9-10 in two takes): the beads' ticks, one by one.

So it is the breath's noise table (breath_noise_db, held for the note, three
rows a band) on the breath's own slow swell (breath_noise_wobble_db, per
channel, ramped at block edges), the ticks as grains on the same swell -- and
no partials.
"""
import glob
import math
import os
import sys

import numpy as np
from scipy.signal import butter, sosfiltfilt

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import voicefit as V

REFS = os.path.expanduser("~/Documents/refs/vcsl/oceandrum")
PROG = 122
KEY = 60
E3 = 2 ** np.arange(np.log2(45), np.log2(16000), 1 / 3.0)
CEN = np.sqrt(E3[:-1] * E3[1:])
HOLD = 20.0


def takes():
    return sorted(glob.glob(os.path.join(REFS, "*.wav")))


def load(p):
    x, sr = V.mono(p)
    return x.astype(np.float64), sr


def active(x, sr):
    """The held part: where the 50 ms envelope is within 30 dB of its peak,
    less a second at each end (the swell in and the ebb out)."""
    w = int(0.05 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
    on = np.flatnonzero(e > e.max() * 10 ** (-30 / 20))
    return x[on[0] + sr:on[-1] - sr]


OCT = ((2000, 4000), (4000, 8000), (8000, 16000))


def clicks(x, sr):
    """How impulsive each top octave is: the kurtosis of the band, its 100 ms
    rms divided out (the swell is not a click). Noise reads 3; the beads'
    ticks lift 8-16 kHz to 9-10 in two takes of three (3.7 in the third)."""
    out = []
    for lo, hi in OCT:
        y = sosfiltfilt(butter(4, [lo, hi], btype="band", fs=sr, output="sos"), x)
        w = int(0.1 * sr)
        z = y / (np.sqrt(np.convolve(y * y, np.ones(w) / w, "same")) + 1e-12)
        out.append(float(np.mean(z ** 4) / np.mean(z ** 2) ** 2))
    return out


def measure(x, sr):
    """Colour (long-term third octaves, dB re the strongest), the swell (the
    50 ms envelope's dB rms after a 3 s running mean, and its median
    modulation rate, Hz), the clicks (kurtosis 2-4, 4-8, 8-16 kHz), and the
    level (dB rms)."""
    x = active(x, sr)
    kurt = clicks(x[:int(30 * sr)], sr)
    N = 1 << 16
    X = np.zeros(N // 2 + 1)
    for a in range(0, len(x) - N, N // 2):
        X += np.abs(np.fft.rfft(x[a:a + N] * np.hanning(N))) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    c = np.array([X[(f >= lo) & (f < hi)].sum() for lo, hi in zip(E3[:-1], E3[1:])])
    c = 10 * np.log10(c / c.max() + 1e-12)
    hop = int(0.01 * sr)
    w = int(0.05 * sr)
    e = 20 * np.log10(np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))[::hop] + 1e-12)
    k = 300
    d = (e - np.convolve(e, np.ones(k) / k, "same"))[k:-k]
    P = np.abs(np.fft.rfft(d * np.hanning(len(d)))) ** 2
    fr = np.fft.rfftfreq(len(d), 0.01)
    cs = np.cumsum(P[1:])
    rate = fr[1:][np.searchsorted(cs, cs[-1] / 2)]
    return dict(colour=c, swell=float(d.std()), rate=float(rate), clicks=kurt,
                level=float(10 * np.log10(np.mean(x * x) + 1e-30)))


def render(secs=HOLD, key=KEY):
    import mido
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=PROG, time=0))
    t.append(mido.Message("note_on", channel=0, note=key, velocity=100, time=0))
    t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(secs * 960)))
    L, R = B.render(m)[:2]
    return 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64)), B.SR


def report():
    R = [measure(*load(p)) for p in takes()]
    O = measure(*render())
    sel = [i for i, c in enumerate(CEN) if 60 < c < 14000][::2]
    print("  colour at " + " ".join("%6d" % CEN[i] for i in sel))
    print("  recorded  " + " ".join("%6.1f" % v for v in np.mean([r["colour"] for r in R], 0)[sel]))
    print("  ours      " + " ".join("%6.1f" % v for v in O["colour"][sel]))
    print("  swell: recorded %.2f dB at %.2f Hz, ours %.2f dB at %.2f Hz; level ours %.2f dB" % (
        np.mean([r["swell"] for r in R]), np.median([r["rate"] for r in R]), O["swell"], O["rate"], O["level"]))
    print("  clicks (kurtosis 2-4, 4-8, 8-16 kHz): recorded %s, ours %s" % (
        " ".join("%.2f" % v for v in np.mean([r["clicks"] for r in R], 0)), " ".join("%.2f" % v for v in O["clicks"])))


TARGET = None


def fit(passes=6):
    """The colour band by band (the median over the takes of recorded - ours
    added to breath_noise_db), the swell's depth and corner scaled toward the
    recordings' each pass, the ticks' level moved toward the recordings'
    8-16 kHz kurtosis (6 dB a factor e), and the table shifted to hold the old
    level. The ticks and the top of the table share the band: they are fitted
    together, or the table gives the top away to the ticks."""
    import tonelib
    cls = tonelib.SeashoreProperties
    R = [measure(*load(p)) for p in takes()]
    rc = np.mean([r["colour"] for r in R], 0)
    rs, rr = np.mean([r["swell"] for r in R]), np.median([r["rate"] for r in R])
    rk = np.mean([r["clicks"][-1] for r in R])
    for n in range(passes + 1):
        O = measure(*render())
        d = rc - O["colour"]
        keep = {hz: i for i, c in enumerate(CEN) for hz, _ in cls.breath_noise_db if abs(c / hz - 1) < 0.02}
        print("  pass %d: colour rms %.1f dB; swell %.2f dB at %.2f Hz (rec %.2f at %.2f); clicks %.2f (rec %.2f);"
              " level %.2f (hold %.2f)"
              % (n, np.sqrt(np.mean([d[i] ** 2 for i in keep.values()])), O["swell"], O["rate"], rs, rr,
                 O["clicks"][-1], rk, O["level"], TARGET), flush=True)
        if n == passes:
            break
        cls.breath_noise_db = tuple((hz, round(db + float(d[keep[hz]]) + (TARGET - O["level"]), 1))
                                    for hz, db in cls.breath_noise_db)
        cls.breath_noise_wobble_db *= rs / max(O["swell"], 1e-3)
        cls.breath_noise_wobble_hz *= rr / max(O["rate"], 1e-3)
        dk = 6.0 * math.log(rk / O["clicks"][-1])
        cls.grains = tuple((lo, hi, r, round(db + dk + (TARGET - O["level"]), 1), sc, dps)
                           for lo, hi, r, db, sc, dps in cls.grains)
    print("    grains = %s" % (cls.grains,))
    print("    breath_noise_db = %s" % (cls.breath_noise_db,))
    print("    breath_noise_wobble_db = %.4g" % cls.breath_noise_wobble_db)
    print("    breath_noise_wobble_hz = %.4g" % cls.breath_noise_wobble_hz)


def ab(out):
    import wave
    from scipy.signal import resample_poly
    x, sr = load(takes()[0])
    x = active(x, sr)[:int(12 * sr)]
    y, sr2 = render(14.0)
    y = active(y, sr2)[:int(12 * sr2)]
    if sr2 != sr:
        y = resample_poly(y, sr, sr2)
    y = y * np.sqrt(np.mean(x ** 2) / np.mean(y ** 2))
    ramp = np.linspace(0, 1, int(0.5 * sr))
    for z in (x, y):
        z[:len(ramp)] *= ramp
        z[-len(ramp):] *= ramp[::-1]
    z = np.concatenate([x, np.zeros(int(1.0 * sr)), y])
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


def main(argv):
    global TARGET
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--ab=")), None)
    if out:
        return ab(out) or 0
    if "--fit" in argv:
        TARGET = float(next((a.split("=")[1] for a in argv if a.startswith("--hold=")), "nan"))
        fit()
        return 0
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
