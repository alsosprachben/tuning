#!/usr/bin/env python3
"""The nylon guitar's DECAY (GM 24), fitted to Iowa's classical guitar.

    python3 -I examples/nylon_decay_fit.py [OUTDIR]     # default ~/Documents/refs/iowa_guitar_notes

NylonGuitarProperties was fitted to Iowa Guitar.mf for its spectrum and its
body, never its decay: decay_db sat at 0, and a held note fell 2-3 dB/s --
twenty seconds to 60 dB (Ben: "a very long sustain ... still decaying, just
very slowly").

Iowa's guitar takes are RUNS, one string's notes in a file. Each is split at
its onsets (attack_audit.split_run) and every note NAMED BY ITS OWN PITCH
(voicefit.detect_f0 over its first second), not by its place in the run: a
missed or extra onset had shifted a whole run a semitone. The string is kept
in the name, so a note played on two strings is two takes, not one written
over the other. Then voicefit.py decay fits decay_db, harmonic_decay_db and
decay_register_slope on them -- the same tool and law the class's decay is
read by.
"""
import glob
import os
import subprocess
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
import attack_audit as A  # noqa: E402
import voicefit as V  # noqa: E402

REFS = os.path.expanduser("~/Documents/refs")
NAMES = "C C# D D# E F F# G G# A A# B".split()


def split_all(out):
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "*.wav")):
        os.remove(old)
    n = 0
    for path in sorted(glob.glob(os.path.join(REFS, "gtr_sul*.aiff"))):
        string = os.path.basename(path).split(".")[0].replace("gtr_", "").replace("_", "")
        x, sr = A.mono(path)
        ons = A.split_run(x, sr, 99)
        for j, o in enumerate(ons):
            end = ons[j + 1] if j + 1 < len(ons) else len(x)
            seg = x[o:end]
            if len(seg) < int(0.8 * sr):
                continue                      # too short to read a decay from
            f0 = V.detect_f0(seg[int(0.05 * sr):int(1.0 * sr)], sr, 70.0, 1200.0)
            if not f0 or not np.isfinite(f0) or f0 <= 0:
                continue
            k = int(round(69 + 12 * np.log2(f0 / 440.0)))
            name = "%s%d.%s.%d.wav" % (NAMES[k % 12], k // 12 - 1, string, j)
            w = wave.open(os.path.join(out, name), "wb")
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes((np.clip(seg / max(np.abs(seg).max(), 1e-9) * 0.9, -1, 1)
                           * 32767).astype("<i2").tobytes())
            w.close()
            n += 1
    return n


def main(argv):
    out = argv[1] if len(argv) > 1 else os.path.join(REFS, "iowa_guitar_notes")
    print("  %d notes split into %s" % (split_all(out), out), flush=True)
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "voicefit.py"), "decay", out])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
