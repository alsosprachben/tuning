#!/usr/bin/env python3
"""A sitar meend at three lock strengths, for the ear.

    python3 examples/meend_demo.py [out.wav] [--eastern=raga:just5/yaman@c#]

Ga (Sa on C#: F4) struck, then the wheel pulls slowly up across tivra Ma, Pa
and Dha -- 7 semitones of pull, the sitar's range -- holds, and comes back,
three times: meend_strength 0 (a plain bend), 0.6 (the class's dwell) and
0.9 (nearly stepped). tonelib.meend_cents is the curve; the raga's swaras are
the detents (ragas.py), here Yaman's.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def gesture(note=65):
    import mido
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=104, time=0))
    t.append(mido.Message("note_on", channel=0, note=note, velocity=100, time=0))
    steps = 80
    # 0.4 s still, 2.0 s up, 0.8 s held, 1.2 s down
    curve = [0] * 8 + [int(8191 * k / 40) for k in range(41)] + [8191] * 16 + \
            [int(8191 * (1 - k / 24)) for k in range(25)]
    for k, v in enumerate(curve):
        t.append(mido.Message("pitchwheel", channel=0, pitch=max(-8192, min(8191, v)), time=0 if k == 0 else 48))
    t.append(mido.Message("note_off", channel=0, note=note, velocity=0, time=480))
    return m


def main(argv):
    import wave
    import blockrender as B
    import tonelib as T
    out = next((a for a in argv[1:] if not a.startswith("--")), "meend_demo.wav")
    east = next((a.split("=", 1)[1] for a in argv if a.startswith("--eastern=")), "raga:just5/yaman@c#")
    keep = T.SitarProperties.meend_strength
    parts = []
    try:
        for st in (0.0, 0.6, 0.9):
            T.SitarProperties.meend_strength = st
            B.EASTERN = east
            L, R = B.render(gesture())[:2]
            B.EASTERN = None
            x = 0.5 * (np.asarray(L) + np.asarray(R))
            parts += [x, np.zeros(int(0.6 * B.SR))]
            print("  strength %.1f: %.1f s" % (st, len(x) / B.SR))
    finally:
        T.SitarProperties.meend_strength = keep
        B.EASTERN = None
    z = np.concatenate(parts)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(B.SR)
    w.writeframes((z * 32767).astype("<i2").tobytes()); w.close()
    print("  ->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
