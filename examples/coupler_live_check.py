"""The divider organ's COUPLER SWITCHES through live.Live (no device): 60's
Organ 1 holding C4 while CC87 (tonelib.COUPLER_CC) changes them, as
examples/coupler_check.py does the file -- each stretch's level at C3 (16'),
C4 (8'), C5 (4') and C6 (2'), dB.

    python3 examples/coupler_live_check.py
"""
import os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
from coupler_check import STEPS


def main(argv):
    os.environ["TUNING_NATIVE_TONE"] = "off"
    import mido
    import blockrender as B
    B.set_sample_rate(48000)
    B.BLK = 128
    import live as L
    part = L.Part(L.patch_for(16, False, "hybrid440", variation=16))
    lv = L.Live(program=16, rate=48000, frames=128, capacity=65536, verbose=False, threads=1, gpu=False,
                tuner="hybrid440", parts=[part])
    lv.parts[0].patch.warm()
    import patchsync
    patchsync.sync(lv)
    lv.slab.shed = lambda n, frac: 0
    M = mido.Message
    ev = [(0.3, M("note_on", channel=0, note=60, velocity=100))]
    ev += [(at, M("control_change", channel=0, control=87, value=v)) for at, v, _ in STEPS if v is not None]
    ev.sort(key=lambda e: e[0])
    out, e = [], 0
    for b in range(int(10.5 * 48000) // 128):
        while e < len(ev) and int(ev[e][0] * 48000) // 128 <= b:
            lv.on_midi(ev[e][1]); e += 1
        out.append(np.frombuffer(lv.callback(None, 128, None, 0)[0], np.float32).reshape(-1, 2))
    if lv.cb_exceptions:
        print("live's callback raised: %s" % lv.last_error)
        return 1
    x = np.concatenate(out).astype(float).mean(axis=1); sr = 48000
    for at, v, lab in STEPS:
        s = x[int((at + 0.8) * sr):int((at + 1.8) * sr)]
        S = np.abs(np.fft.rfft(s * np.hanning(len(s)))); f = np.fft.rfftfreq(len(s), 1 / sr)
        lv_ = lambda hz: 20 * np.log10(S[(f > hz * 0.98) & (f < hz * 1.02)].max() + 1e-12)
        print("%-22s C3 %6.1f  C4 %6.1f  C5 %6.1f  C6 %6.1f" % (lab, lv_(130.8), lv_(261.6), lv_(523.3), lv_(1046.5)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
