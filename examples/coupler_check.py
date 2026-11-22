"""The divider organ's COUPLER SWITCHES (tonelib.couple_divider, COUPLER_CC 87)
through the file renderer: 60's Organ 1 (Flute 8', its 4' coupler on) holding
C4 while the switches change -- the 4' coupler off, then 8' Off with the 4'
(the 4' alone), then 16' -- each stretch's level at C4 (the 8'), C5 (the 4')
and C3 (the 16'), dB.

    python3 examples/coupler_check.py [--wav=PATH]
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TUNING_REFLECT", "0")

STEPS = ((0.5, None, "as the preset (4' on)"), (2.5, 0, "couplers off"), (4.5, 1 | 4, "8' Off + 4'"),
         (6.5, 2, "16' only"), (8.5, 2 | 4 | 8, "16' + 4' + 2'"))


def midi():
    import mido
    m = mido.MidiFile(type=0, ticks_per_beat=480); t = mido.MidiTrack(); m.tracks.append(t)
    ev = [(0.0, mido.Message('control_change', channel=0, control=0, value=16)),
          (0.0, mido.Message('program_change', channel=0, program=16)),
          (0.3, mido.Message('note_on', channel=0, note=60, velocity=100)),
          (10.5, mido.Message('note_off', channel=0, note=60, velocity=0))]
    for at, v, _ in STEPS:
        if v is not None:
            ev.append((at, mido.Message('control_change', channel=0, control=87, value=v)))
    now = 0
    for at, msg in sorted(ev, key=lambda e: e[0]):
        tk = int(round(at * 960)); msg.time = tk - now; now = tk; t.append(msg)
    return m


def main(argv):
    import blockrender as B
    L, R = B.render(midi())[:2]
    x = 0.5 * (np.asarray(L, float) + np.asarray(R, float)); sr = B.SR
    for at, v, lab in STEPS:
        s = x[int((at + 0.8) * sr):int((at + 1.8) * sr)]
        S = np.abs(np.fft.rfft(s * np.hanning(len(s)))); f = np.fft.rfftfreq(len(s), 1 / sr)
        lv = lambda hz: 20 * np.log10(S[(f > hz * 0.98) & (f < hz * 1.02)].max() + 1e-12)
        print("%-22s C3 %6.1f  C4 %6.1f  C5 %6.1f  C6 %6.1f" % (lab, lv(130.8), lv(261.6), lv(523.3), lv(1046.5)))


if __name__ == "__main__":
    main(sys.argv)
