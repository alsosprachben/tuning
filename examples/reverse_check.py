#!/usr/bin/env python3
"""Is GM 119 the crash played backwards? Render the crash forward (the same
class, played_backwards off), flip the waveform, and set it against the
reversed render, band by band, in windows counted back from the arrival.

    python3 examples/reverse_check.py [SECONDS]

Dry (TUNING_REFLECT=0), velocity 100, one note of SECONDS (3).
"""
import os
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ.setdefault("TUNING_REFLECT", "0")
os.environ.setdefault("TUNING_MASTER_DB", "-14")

import blockrender as B  # noqa: E402
import tonelib as T  # noqa: E402

BANDS = ((200, 1000), (1000, 4000), (4000, 16000))
WINDOWS = ((-3.0, -2.0), (-2.0, -1.0), (-1.0, -0.5), (-0.5, -0.25), (-0.25, -0.1), (-0.1, -0.05),
           (-0.05, -0.02), (-0.02, 0.0))


def render(secs, back):
    T.ReverseCymbalProperties.played_backwards = back
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("program_change", channel=0, program=119, time=0))
    t.append(mido.Message("note_on", channel=0, note=60, velocity=100, time=0))
    t.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=int(secs * 960)))
    L, R = B.render(m)[:2]
    return np.asarray(L, np.float64) + np.asarray(R, np.float64)


def main(argv):
    from scipy.signal import butter, sosfiltfilt
    secs = float(argv[1]) if len(argv) > 1 else 3.0
    sr = B.SR
    fw = render(secs, False)
    on = int(np.flatnonzero(np.abs(fw) > 1e-4 * np.abs(fw).max())[0])
    flipped = fw[on:on + int(secs * sr)][::-1]
    end = int(secs * sr)
    ours = render(secs, True)[end - int(secs * sr):end]
    print("windows (s before the arrival): " + " ".join("%5.2f" % -a for a, _ in WINDOWS))
    rms = []
    for lo, hi in BANDS:
        sos = butter(4, [lo, hi], btype="band", fs=sr, output="sos")
        a, b = sosfiltfilt(sos, flipped), sosfiltfilt(sos, ours)

        def win(y):
            n = len(y)
            return np.array([10 * np.log10(np.mean(y[n + int(w0 * sr):n + int(w1 * sr)] ** 2) + 1e-30)
                             for w0, w1 in WINDOWS if -w0 <= secs])
        ea, eb = win(a), win(b)
        top = ea.max()
        print("%5d-%-5d flipped " % (lo, hi) + " ".join("%5.1f" % v for v in ea - top))
        print("%11s ours    " % "" + " ".join("%5.1f" % v for v in eb - top))
        rms.append(np.sqrt(np.mean((ea - eb) ** 2)))
    print("rms difference by band: " + "  ".join("%.2f dB" % r for r in rms))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
