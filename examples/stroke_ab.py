#!/usr/bin/env python3
"""A struck voice against its recording, by ear: each recorded stroke, then
ours at the velocity whose level sits as far under our loudest as that stroke
sits under the recording's loudest.

    python3 examples/stroke_ab.py SET OUT.wav
    python3 examples/stroke_ab.py SET --bands

--bands prints, instead of writing the pairs, each octave band's level
ours minus the recording's in three windows -- the attack (0-30 ms), the
body (30-150) and the tail (150-500) -- every stroke levelled on its whole
energy, then averaged over the strokes: where ours is brighter or darker,
and when.

SET is one of SETS below. Ours is rendered dry, as the fits render it (no
reflections, master -14 dB); one gain for the whole file, matching the two
loudest, so the dynamics are each side's own. The recordings keep their
room: what is heard between a pair beyond the drum is that.

TWO SECONDS INTO A FILE, not at its start. A partial's noise is drawn from
a hash of floor(n * f * gran / SR), n counted from the FILE's first sample
and nothing of the partial in it: near n = 0 partials share indices along
t * f = const, and their noise is one noise, drawn as 1/f arcs -- a "pew"
over the first 10-30 ms that no stroke two seconds in has. A fit's render
(crash_fit.render) starts at 0; a song's drums do not.
"""
import glob
import os
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

os.environ.setdefault("TUNING_REFLECT", "0")
os.environ.setdefault("TUNING_MASTER_DB", "-14")

import crash_fit as C  # noqa: E402
from drum_fit import read  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs")
SETS = {
    # GM 40, Snare Drum 2: VCSL Modern 1, wires on, one take of each layer
    "snare2": (40, sorted(glob.glob(os.path.join(REFS, "vcsl/snare/Snare2_HitSN_v*_rr1_Mid.wav")))),
    "timbale_hi": (65, sorted(glob.glob(os.path.join(REFS, "freesound/timbales/hits/high_*.wav")))[:6]),
    "timbale_lo": (66, sorted(glob.glob(os.path.join(REFS, "freesound/timbales/hits/low_*.wav")))[:6]),
    "surdo_open": (87, sorted(glob.glob(os.path.join(REFS, "freesound/surdo/hits/open_*.wav")))),
    "surdo_mute": (86, sorted(glob.glob(os.path.join(REFS, "freesound/surdo/hits/mute_*.wav")))),
}
SECS = 1.0


def mono(chs):
    return np.sqrt(0.5) * (chs[0] + chs[1]) if len(chs) > 1 else chs[0]


def cut(x, sr):
    on = C.onset([x], sr)
    return x[max(0, on - int(0.01 * sr)):on + int(SECS * sr)]


def render_late(note, vel, secs, lead=2.0):
    import mido
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("note_on", channel=9, note=note, velocity=vel, time=int(lead * 960)))
    tr.append(mido.Message("note_off", channel=9, note=note, velocity=0, time=int(secs * 960)))
    L, R = B.render(m)[:2]
    k = int((lead - 0.05) * B.SR)
    return [np.asarray(L, np.float64)[k:], np.asarray(R, np.float64)[k:]], B.SR


BANDS = (63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
WINS = ((0.0, 0.03), (0.03, 0.15), (0.15, 0.5))


def bands(x, sr):
    """dB per octave band per window, levelled on the stroke's whole energy."""
    on = C.onset([x], sr)
    out = np.zeros((len(BANDS), len(WINS)))
    tot = np.sum(x[on:on + int(0.5 * sr)] ** 2) + 1e-30
    for j, (a, b) in enumerate(WINS):
        seg = x[on + int(a * sr):on + int(b * sr)]
        X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 15)) ** 2
        f = np.fft.rfftfreq(1 << 15, 1.0 / sr)
        sc = np.sum(seg ** 2) / (np.sum(X) + 1e-30)
        for i, c in enumerate(BANDS):
            out[i, j] = 10 * np.log10(sc * X[(f >= c / 2 ** 0.5) & (f < c * 2 ** 0.5)].sum() / tot + 1e-30)
    return out


def main(argv):
    note, files = SETS[argv[1]]
    out = argv[2]
    rec = []
    for p in files:
        a, sr = read(p)
        chs = [a[:, 0], a[:, 1]] if a.ndim > 1 else [a]
        rec.append((C.level(chs, sr), cut(mono(chs), sr)))
    top = max(l for l, _ in rec)
    cache = {}
    ours = []
    for l, _ in rec:
        v = C.model_velocity(note, l - top, cache)
        chs, sr2 = render_late(note, v, SECS + 0.1)
        if sr2 != sr:
            # the take's own rate (the surdo's is 48 kHz)
            from math import gcd
            from scipy.signal import resample_poly
            g = gcd(sr, sr2)
            chs = [resample_poly(c, sr // g, sr2 // g) for c in chs]
            sr2 = sr
        ours.append((v, C.level(chs, sr2), cut(mono(chs), sr2)))
        print("  stroke %+5.1f dB -> velocity %d" % (l - top, v))
    if out == "--bands":
        d = np.mean([bands(o, sr) - bands(r, sr) for (_, r), (_, _, o) in zip(rec, ours)], 0)
        print("  ours minus recorded, dB   " + "  ".join("%3.0f-%-3.0f ms" % (1000 * a, 1000 * b) for a, b in WINS))
        for c, row in zip(BANDS, d):
            print("  %6d Hz            " % c + "  ".join("%+9.1f " % v for v in row))
        return 0
    g = 10 ** ((top - max(o[1] for o in ours)) / 20.0)
    gap = np.zeros(int(0.35 * sr))
    z = np.concatenate(sum(([r, gap, o * g, gap, gap] for (_, r), (_, _, o) in zip(rec, ours)), []))
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes((z * 32767).astype("<i2").tobytes())
    w.close()
    print("%s: %d pairs, recording then ours -> %s" % (argv[1], len(rec), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
