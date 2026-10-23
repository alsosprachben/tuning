"""GS 123.4 Kitty and 123.5 Growl beside their recordings (both CC0;
sources.md): a meow of peridactyloptrix's, then ours; qubodup's longest growl
burst, then ours -- each pair at one peak, 0.6 s apart. Writes
OUT/kitty_ab.wav and OUT/growl_ab.wav.

    python3 examples/kitty_growl_ab.py OUT
"""
import glob
import os
import subprocess
import sys
import tempfile

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B          # noqa: E402
from drum_fit import read        # noqa: E402

R = os.path.expanduser("~/Documents/refs/freesound")
# (name, bank, the take, its excerpt s, our note's length s)
PAIRS = (("kitty", 4, "cat/214759_*.wav", (5.65, 6.45), 0.9),
         ("growl", 5, "growl/122183_*.flac", (7.95, 8.90), 1.0))


def take(pat, a, b):
    with tempfile.TemporaryDirectory() as d:
        w = os.path.join(d, "t.wav")
        subprocess.run(["sox", sorted(glob.glob(os.path.join(R, pat)))[0], "-e", "floating-point",
                        "-b", "32", "-c", "1", "-r", str(B.SR), w], check=True)
        x, sr = read(w)
    x = x.reshape(len(x), -1).mean(1)
    return x[int(a * sr):int(b * sr)]


def ours(bank, secs):
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    m.tracks.append(t)
    for msg in (mido.Message("control_change", channel=0, control=0, value=bank),
                mido.Message("program_change", channel=0, program=123),
                mido.Message("note_on", channel=0, note=60, velocity=100),
                mido.Message("note_off", channel=0, note=60, velocity=0, time=int(secs * 960))):
        t.append(msg)
    L, Rr = B.render(m)[:2]
    y = 0.5 * (np.asarray(L, float) + np.asarray(Rr, float))
    a = int(np.flatnonzero(np.abs(y) > 0.01 * np.abs(y).max())[0])
    return y[a:]


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    for name, bank, pat, (a, b), secs in PAIRS:
        x = take(pat, a, b)
        y = ours(bank, secs)
        z = np.concatenate([x * 0.5 / np.abs(x).max(), np.zeros(int(0.6 * B.SR)), y * 0.5 / np.abs(y).max()])
        f = os.path.join(out, name + "_ab.wav")
        B.write_wav(f, z, z)
        print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
