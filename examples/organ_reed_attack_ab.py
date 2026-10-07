#!/usr/bin/env python3
"""The reeds' attack rush, by ear: BWV 659's cantus on a solo reed 8'.

    python3 examples/organ_reed_attack_ab.py [SCORE.mid] [SECONDS] [outdir]

The cantus of Nun komm, der Heiden Heiland on the console's reed 8 alone (bit
8), the accompaniment on a flute 8 and the pedal on bourdon 16 + flute 8, as
examples/organ_tremulant_ab.py registers it, no Tremulant. Three renders
through examples/organ.py's recipe, the wind on in all three:

  1  TUNING_WIND_ATTACK=0   the turbulence and the chest, no rush
  2  the rush as fitted to Pitea (tonelib: wind_attack_db)
  3  TUNING_WIND=4          all of the wind, rush included, four times over --
                            only to teach the ear what to listen for in 2

as MP3s at one common gain. Default 75 s into ~/Downloads/organ_wind.
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
import organ_tremulant_ab as TA                         # noqa: E402

REED8 = 1 << 8
PARTS = {"Cantus Firmus": (0, REED8), "Accomp 8": (1, TA.FLUTE8),
         "Ped 8": (2, TA.BOURDON16 | TA.FLUTE8)}
TAKES = (("1_no_rush", {"TUNING_WIND": "1", "TUNING_WIND_ATTACK": "0"}),
         ("2_rush", {"TUNING_WIND": "1"}),
         ("3_wind_x4", {"TUNING_WIND": "4"}))


def main(argv):
    from bitident import excerpt
    score = argv[1] if len(argv) > 1 else os.path.expanduser("~/Downloads/midi/bwv659.mid")
    secs = float(argv[2]) if len(argv) > 2 else 75.0
    out = argv[3] if len(argv) > 3 else os.path.expanduser("~/Downloads/organ_wind")
    os.makedirs(out, exist_ok=True)
    d = tempfile.mkdtemp(prefix="organreed_")
    reg = os.path.join(d, "bwv659_reed.mid")
    TA.register(score, reg, False, PARTS)
    mid = reg[:-4] + "_%ds.mid" % secs
    excerpt(reg, secs).save(mid)
    wavs = {}
    for name, env in TAKES:
        od = os.path.join(d, name)
        subprocess.run([sys.executable, os.path.join(HERE, "examples", "organ.py"), mid, od],
                       env=dict(os.environ, **env), check=True, stdout=subprocess.DEVNULL)
        got = [f for f in os.listdir(od) if f.endswith(".wav") and "dry" not in f and "send" not in f]
        wavs[name] = os.path.join(od, sorted(got, key=len)[-1])
    peak = 0.0
    for p in wavs.values():
        s = subprocess.run(["sox", p, "-n", "stat"], capture_output=True, text=True).stderr
        for k in ("Maximum amplitude", "Minimum amplitude"):
            peak = max(peak, abs(float([l for l in s.splitlines() if l.startswith(k)][0].split()[-1])))
    gain = -1.0 - 20 * np.log10(peak)
    for name, p in wavs.items():
        mp3 = os.path.join(out, "bwv659_reed_%s.mp3" % name)
        tmp = os.path.join(d, "g.wav")
        subprocess.run(["sox", p, "-b", "24", tmp, "gain", "%.2f" % gain], check=True)
        subprocess.run(["lame", "-b", "320", "--quiet", tmp, mp3], check=True)
        print("  -> %s" % mp3)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
