#!/usr/bin/env python3
"""The organ's wind, by ear: one excerpt three ways, at one gain.

    python3 examples/organ_wind_ab.py SCORE.mid [SECONDS] [outdir]

Renders the first SECONDS (default 60) of an organ score through
examples/organ.py's recipe (church, hybrid, -12 dB) with the wind off
(TUNING_WIND=0), on (1) and four times as strong (4) -- the last only to teach
the ear what to listen for in the second (Ben's practice) -- and writes them
as MP3s at one common gain, so their levels compare. Default outdir
~/Downloads/organ_wind.
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))


def main(argv):
    from bitident import excerpt
    score = argv[1]
    secs = float(argv[2]) if len(argv) > 2 else 60.0
    out = argv[3] if len(argv) > 3 else os.path.expanduser("~/Downloads/organ_wind")
    os.makedirs(out, exist_ok=True)
    base = os.path.splitext(os.path.basename(score))[0]
    d = tempfile.mkdtemp(prefix="organwind_")
    mid = os.path.join(d, "%s_%ds.mid" % (base, secs))
    excerpt(score, secs).save(mid)
    wavs = {}
    for w in ("0", "1", "4"):
        od = os.path.join(d, "w" + w)
        env = dict(os.environ, TUNING_WIND=w)
        subprocess.run([sys.executable, os.path.join(HERE, "examples", "organ.py"), mid, od],
                       env=env, check=True, stdout=subprocess.DEVNULL)
        got = [f for f in os.listdir(od) if f.endswith(".wav") and "dry" not in f and "send" not in f]
        wavs[w] = os.path.join(od, sorted(got, key=len)[-1])
    peak = 0.0
    for p in wavs.values():
        s = subprocess.run(["sox", p, "-n", "stat"], capture_output=True, text=True).stderr
        peak = max(peak, float([l for l in s.splitlines() if l.startswith("Maximum amplitude")][0].split()[-1]),
                   abs(float([l for l in s.splitlines() if l.startswith("Minimum amplitude")][0].split()[-1])))
    gain = -1.0 - 20 * np.log10(peak)
    names = {"0": "1_no_wind", "1": "2_wind", "4": "3_wind_x4"}
    for w, p in wavs.items():
        mp3 = os.path.join(out, "%s_%s.mp3" % (base, names[w]))
        tmp = os.path.join(d, "g.wav")
        subprocess.run(["sox", p, "-b", "24", tmp, "gain", "%.2f" % gain], check=True)
        subprocess.run(["lame", "-b", "320", "--quiet", tmp, mp3], check=True)
        print("  -> %s" % mp3)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
