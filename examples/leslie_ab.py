#!/usr/bin/env python3
"""The Leslie against a recording of one: hammondman's "Rok organ" notes
(freesound pack 15120, CC0; sources.md "Organs and free reeds"), a tonewheel
organ through a rotary cabinet, each recorded then ours on GM 18 (Rock Organ:
fast rotor, amp pushed) at the same key -- the rotor's swing and rate, which do
not depend on the drawbars (the take's are not given).

    python3 examples/leslie_ab.py OUT.wav
"""
import glob
import os
import sys
import wave

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
import blockrender as B  # noqa: E402
import voicefit as V  # noqa: E402

SRC = os.path.expanduser("~/Documents/refs/freesound/tonewheel/hammondman_rok")
NAMES = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
SR = 44100


def main(out):
    from scipy.signal import resample_poly
    parts = []
    gap = np.zeros(int(0.35 * SR))
    for nm in ("g2", "c3", "f3", "c4", "e4", "g4", "a5"):
        p = glob.glob(os.path.join(SRC, "*__%s.wav" % nm))[0]
        x, sr = V.mono(p)
        x = resample_poly(x.astype(np.float64), SR, sr)
        key = NAMES[nm[0]] + 12 * (int(nm[1]) + 1)
        m = mido.MidiFile(type=1, ticks_per_beat=480)
        t = mido.MidiTrack()
        m.tracks.append(t)
        t.append(mido.Message("program_change", channel=0, program=18, time=0))
        t.append(mido.Message("note_on", channel=0, note=key, velocity=100, time=0))
        t.append(mido.Message("note_off", channel=0, note=key, velocity=0, time=int(len(x) / SR * 960)))
        L, R = B.render(m)[:2]
        y = np.asarray(L, np.float64)                  # one mic, as the take
        if B.SR != SR:
            y = resample_poly(y, SR, B.SR)
        y = y[np.flatnonzero(np.abs(y) > np.abs(y).max() * 0.02)[0]:][:len(x) + int(0.3 * SR)]
        y *= np.sqrt(np.mean(x ** 2) / max(np.mean(y[:len(x)] ** 2), 1e-30))
        parts += [x, gap, y, gap, gap]
        print("  %s key %d" % (nm, key))
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()


if __name__ == "__main__":
    main(sys.argv[1])
