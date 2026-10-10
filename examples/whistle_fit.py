#!/usr/bin/env python3
"""Fit the samba (pea) whistles (GM percussion 71 short, 72 long) to VCSL's
ball whistle (CC0; ~/Documents/refs/vcsl/ballwhistle, Long and Short, sources.md).

    whistle_fit.py            measure: recorded against ours
    whistle_fit.py --ab=OUT   the recorded blasts, then ours

A PEA WHISTLE IS A TONE THE PEA CHOPS: the jet over a cavity sounds one note
(2.7 kHz here, nearly pure -- h2 30 dB down) and the cork pea, spun by the
air in the chamber, swings it in level and in pitch many times a second.
Measured: the level moving 6 dB rms at ~110 Hz, the pitch 80 cents rms at
~30 Hz, the air between the harmonics only 55 dB under the tone.
"""
import glob
import os
import sys

import numpy as np
from scipy.signal import hilbert, butter, sosfiltfilt

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import voicefit as V

REFS = os.path.expanduser("~/Documents/refs/vcsl/ballwhistle")
NOTES = {"Long": 72, "Short": 71}


def held(x, sr):
    w = int(0.01 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
    on = np.flatnonzero(e > e.max() * 0.1)
    return x[on[0] + int(0.03 * sr):on[-1] - int(0.03 * sr)], (on[-1] - on[0]) / sr


def measure(x, sr):
    """The tone's pitch and ladder, its level and pitch modulation (rms and
    the strongest rate, 5-300 Hz, after a 40 ms running mean), and the air
    between h1 and h2 (median, dB re the tone's peak)."""
    seg, dur = held(x, sr)
    n = min(len(seg), 1 << 17)
    N = 1 << 17
    X = np.abs(np.fft.rfft(seg[:n] * np.hanning(n), N))
    f = np.fft.rfftfreq(N, 1.0 / sr)
    k = int(np.argmax(X * (f > 500)))
    f0 = f[k]
    lad = [20 * np.log10(X[(f > m * f0 * 0.95) & (f < m * f0 * 1.05)].max() / X[k]) for m in (2, 3)]
    bp = sosfiltfilt(butter(4, [f0 * 0.8, f0 * 1.2], btype="band", fs=sr, output="sos"), seg)
    a = hilbert(bp)
    edb = 20 * np.log10(np.abs(a) + 1e-9)
    inst = np.clip(np.diff(np.unwrap(np.angle(a))) * sr / (2 * np.pi), f0 * 0.5, f0 * 2)
    cents = 1200 * np.log2(inst / f0)
    w = int(0.04 * sr)

    def mod(c):
        c = (c - np.convolve(c, np.ones(w) / w, "same"))[w:-w]
        P = np.abs(np.fft.rfft(c * np.hanning(len(c)))) ** 2
        fr = np.fft.rfftfreq(len(c), 1.0 / sr)
        s = (fr > 5) & (fr < 300)
        return float(c.std()), float(fr[s][np.argmax(P[s])])
    am, amr = mod(edb)
    fm, fmr = mod(cents)
    # The pitch the ear hears: the median instantaneous frequency (the
    # spectrum's tallest peak can be one of the pea's sidebands)
    f0 = float(np.median(inst))
    mid = (f > f0 * 1.2) & (f < f0 * 1.8)
    return dict(dur=dur, f0=f0, h2=lad[0], h3=lad[1], am=am, amr=amr, fm=fm, fmr=fmr,
                air=float(20 * np.log10(np.median(X[mid]) / X[k])))


def render(note, secs=1.0):
    import mido
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("note_on", channel=9, note=note, velocity=100, time=0))
    t.append(mido.Message("note_off", channel=9, note=note, velocity=0, time=int(secs * 960)))
    L, R = B.render(m)[:2]
    return 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64)), B.SR


FMT = ("%-6s %-9s dur %.2fs  f0 %5.0f Hz  h2 %+4.0f h3 %+4.0f dB  AM %4.1f dB at %3.0f Hz  "
       "FM %4.0f c at %3.0f Hz  air %+4.0f dB")


def report():
    for p in sorted(glob.glob(os.path.join(REFS, "*.wav"))):
        kind = "Long" if "Long" in p else "Short"
        x, sr = V.mono(p)
        r = measure(x.astype(np.float64), sr)
        y, sr2 = render(NOTES[kind], 1.0 if kind == "Long" else 0.3)
        o = measure(y, sr2)
        for name, d in (("recorded", r), ("ours", o)):
            print(FMT % (kind, name, d["dur"], d["f0"], d["h2"], d["h3"], d["am"], d["amr"], d["fm"], d["fmr"], d["air"]))


def ab(out):
    """--ab=OUT.wav: the recorded short and long blasts, then ours, each
    pair matched in level."""
    import wave
    from scipy.signal import resample_poly
    parts, sr = [], 44100
    for kind in ("Short", "Long"):
        p = glob.glob(os.path.join(REFS, "*%s*.wav" % kind))[0]
        x, sr = V.mono(p)
        x = x.astype(np.float64)
        y, sr2 = render(NOTES[kind], 0.1)
        if sr2 != sr:
            y = resample_poly(y, sr, sr2)
        y = y[:int(1.2 * sr)] * np.sqrt(np.mean(held(x, sr)[0] ** 2) / np.mean(held(y, sr)[0] ** 2))
        gap = np.zeros(int(0.4 * sr))
        parts += [x[:int(1.2 * sr)], gap, y, gap, gap]
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


def main(argv):
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--ab=")), None)
    if out:
        return ab(out) or 0
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
