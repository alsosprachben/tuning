#!/usr/bin/env python3
"""Fit the hand clap (GM percussion 39) to VCSL's ensemble claps (CC0;
~/Documents/refs/vcsl/claps/Clap_rr1-6, sources.md).

    clap_fit.py              measure: recorded against ours
    clap_fit.py --fit        the strike's colour, third octave by third octave
    clap_fit.py --level      the level a fit is held at (velocity 100, loudest 150 ms)
    clap_fit.py --ab=OUT.wav the six takes, then six of ours

AN ENSEMBLE CLAP IS SEVERAL HANDS NOT QUITE TOGETHER: 5-9 sub-claps over
50-60 ms, each within 13 dB of the loudest, each dying in a few ms (the tail
after the last 240-800 dB/s); the colour a broad hump at 1-2 kHz, 15 dB down
at 400 Hz and 10 by 10-13 kHz. Modelled as the hammer's strike rows
(tonelib strike_noise_db) fired strike_flam times (blockrender) -- not the
52 noise-washed modes it was, centred at 5.5 kHz.
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import voicefit as V

REFS = os.path.expanduser("~/Documents/refs/vcsl/claps")
NOTE = 39
E3 = 2 ** np.arange(np.log2(45), np.log2(16000), 1 / 3.0)
CEN = np.sqrt(E3[:-1] * E3[1:])


def takes():
    return sorted(glob.glob(os.path.join(REFS, "Clap_rr*.wav")))


def load(p):
    x, sr = V.mono(p)
    return x.astype(np.float64), sr


def render(n=6, gap=1.0, vel=100):
    """N claps GAP seconds apart (each its own flam: the draw is the note's)."""
    import mido
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    for i in range(n):
        t.append(mido.Message("note_on", channel=9, note=NOTE, velocity=vel, time=0 if i == 0 else int(gap * 960) - 48))
        t.append(mido.Message("note_off", channel=9, note=NOTE, velocity=0, time=48))
    L, R = B.render(m)[:2]
    y = 0.5 * (np.asarray(L, np.float64) + np.asarray(R, np.float64))
    return [y[int(i * gap * B.SR):int((i + 1) * gap * B.SR)] for i in range(n)], B.SR


def measure(x, sr):
    """The clap: its sub-claps (count, spread ms), the tail's fall after the
    last (dB/s), and the colour of its first 100 ms (third octaves, dB re the
    strongest)."""
    w = int(0.0007 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, "same"))
    db = 20 * np.log10(e / e.max() + 1e-9)
    on = int(np.flatnonzero(db > -25)[0])
    seg = db[on:on + int(0.08 * sr)]
    g = int(0.0025 * sr)
    b = [k for k in range(1, len(seg) - 1) if seg[k] > -14 and seg[k] == seg[max(0, k - g):k + g].max()]
    last = on + b[-1]
    t = db[last:]
    a6 = np.flatnonzero(t < db[last] - 6)
    a30 = np.flatnonzero(t < db[last] - 30)
    dps = 24.0 / ((a30[0] - a6[0]) / sr) if len(a6) and len(a30) else np.nan
    y = x[on:on + int(0.1 * sr)]
    N = 1 << 15
    X = np.abs(np.fft.rfft(y, N)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    c = np.array([X[(f >= lo) & (f < hi)].sum() for lo, hi in zip(E3[:-1], E3[1:])])
    c = 10 * np.log10(c / c.max() + 1e-12)
    return dict(n=len(b), spread=(b[-1] - b[0]) / sr * 1000, tail=dps, colour=c)


def level(x, sr):
    c = np.concatenate(([0.0], np.cumsum(x * x)))
    n = int(0.15 * sr)
    return 10 * np.log10((c[n:] - c[:-n]).max() / n + 1e-30)


def report():
    R = [measure(*load(p)) for p in takes()]
    hits, sr = render()
    O = [measure(y, sr) for y in hits]
    for name, rows in (("recorded", R), ("ours", O)):
        print("  %-9s sub-claps %.1f over %.0f ms, tail %.0f dB/s" % (
            name, np.mean([r["n"] for r in rows]), np.mean([r["spread"] for r in rows]),
            np.nanmedian([r["tail"] for r in rows])))
    sel = [i for i, c in enumerate(CEN) if c > 100][::2]
    print("  colour at " + " ".join("%6d" % CEN[i] for i in sel))
    for name, rows in (("recorded", R), ("ours", O)):
        m = np.mean([r["colour"] for r in rows], 0)
        print("  %-9s " % name + " ".join("%6.1f" % m[i] for i in sel))
    print("  level at velocity 100: %.2f dB" % np.mean([level(y, sr) for y in hits]))


TARGET = -44.48        # the clap it replaced, velocity 100, loudest 150 ms


def fit(passes=4):
    """--fit: strike_noise_db band by band toward the recordings' colour (mean
    over the six takes; ours over six hits, each its own flam), then the whole
    table shifted to hold the level. Written into tonelib.py."""
    import re
    import tonelib
    cls = tonelib.HandClapProperties
    rec = np.mean([measure(*load(p))["colour"] for p in takes()], 0)
    keep = {int(hz): i for i, c in enumerate(CEN) for hz, _ in cls.strike_noise_db if abs(c / hz - 1) < 0.02}
    for n in range(passes + 1):
        hits, sr = render()
        ours = np.mean([measure(y, sr)["colour"] for y in hits], 0)
        lv = np.mean([level(y, sr) for y in hits])
        d = {hz: rec[i] - ours[i] for hz, i in keep.items()}
        print("  pass %d: colour rms %.1f dB, level %.2f dB (target %.2f)" % (
            n, np.sqrt(np.mean([v * v for v in d.values()])), lv, TARGET), flush=True)
        if n == passes:
            break
        cls.strike_noise_db = tuple((hz, round(db + d.get(hz, 0.0) + (TARGET - lv), 1))
                                    for hz, db in cls.strike_noise_db)
    path = os.path.join(HERE, "tonelib.py")
    body = open(path).read()
    i = body.index("class HandClapProperties(")
    j = body.index("\nclass ", i + 10)
    blk = re.sub(r"(?m)^    strike_noise_db = \(.*\)$", lambda _: "    strike_noise_db = %s" % (cls.strike_noise_db,),
                 body[i:j])
    open(path, "w").write(body[:i] + blk + body[j:])
    print("    strike_noise_db = %s" % (cls.strike_noise_db,))


def ab(out):
    """--ab=OUT.wav: the six takes, a pause, then six of ours (each its own
    flam), matched in level."""
    import wave
    from scipy.signal import resample_poly
    R = []
    for p in takes():
        x, sr = load(p)
        on = int(np.flatnonzero(np.abs(x) > np.abs(x).max() * 0.05)[0])
        R.append(x[max(0, on - int(0.01 * sr)):on + int(0.5 * sr)])
    hits, sr2 = render()
    O = []
    for y in hits:
        on = int(np.flatnonzero(np.abs(y) > np.abs(y).max() * 0.05)[0])
        y = y[max(0, on - int(0.01 * sr2)):on + int(0.5 * sr2)]
        O.append(resample_poly(y, sr, sr2) if sr2 != sr else y)
    lr = np.mean([level(r, sr) for r in R]); lo = np.mean([level(o, sr) for o in O])
    O = [o * 10 ** ((lr - lo) / 20) for o in O]
    gap, pause = np.zeros(int(0.25 * sr)), np.zeros(int(1.0 * sr))
    z = np.concatenate(sum(([r, gap] for r in R), []) + [pause] + sum(([o, gap] for o in O), []))
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


def main(argv):
    out = next((a.split("=", 1)[1] for a in argv if a.startswith("--ab=")), None)
    if out:
        return ab(out) or 0
    if "--fit" in argv:
        fit()
        return 0
    if "--level" in argv:
        hits, sr = render()
        print("  level %.2f dB" % np.mean([level(y, sr) for y in hits]))
        return 0
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
