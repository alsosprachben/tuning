"""The High and Low Hoo (GS Hip-Hop / Dance 78-79; tonelib.HooProperties,
percussion_gs.STROKES) beside the take they were read from: Reitanna's HOO
(Freesound 343968, CC0) twice, then ours -- High, Low, High, Low -- on the
native Dance set, in the studio. Writes OUT/hoo_ab.wav.

    python3 examples/hoo_demo.py OUT
"""
import os
import subprocess
import sys
import tempfile

import mido
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

TAKE = os.path.expanduser("~/Documents/refs/hoo/raw/343968__reitanna__hoo-ha-hee-ha.wav")
ROOM = "studio"


def ours():
    import blockrender as B
    import tonelib
    tonelib.set_room(ROOM)
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    t.append(mido.Message("sysex", data=[0x41, 0x10, 0x42, 0x12, 0x40, 0x00, 0x7F, 0x00, 0x41], time=0))
    t.append(mido.Message("program_change", channel=9, program=26, time=0))
    for i, k in enumerate((78, 79, 78, 79)):
        t.append(mido.Message("note_on", channel=9, note=k, velocity=110, time=0 if i == 0 else 720))
        t.append(mido.Message("note_off", channel=9, note=k, velocity=0, time=240))
    L, R = B.render(m)[:2]
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "dry.wav"), os.path.join(d, "wet.wav")
        B.write_wav(a, np.asarray(L, float), np.asarray(R, float))
        subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), a, b], check=True,
                       stdout=subprocess.DEVNULL, env=dict(os.environ, TUNING_ROOM=ROOM))
        sr, w = wavfile.read(b)
    w = w.astype(np.float64)
    return w.mean(1) if w.ndim > 1 else w, sr


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    y, sr = ours()
    sr0, x = wavfile.read(TAKE)
    x = x.astype(np.float64)
    x = x[int(0.04 * sr0):int(0.42 * sr0)]
    if sr0 != sr:
        x = resample_poly(x, sr, sr0)
    x *= np.abs(y).max() / np.abs(x).max()
    gap = np.zeros(int(0.6 * sr))
    z = np.concatenate([x, gap, x, gap, np.zeros(int(0.5 * sr)), y])
    z *= 0.5 / np.abs(z).max()
    f = os.path.join(out, "hoo_ab.wav")
    wavfile.write(f, sr, (z * 32767).astype(np.int16))
    print("  " + f + "  (the take's HOO twice, then ours: High, Low, High, Low)")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
