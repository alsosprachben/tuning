#!/usr/bin/env python3
"""The nylon guitar's decay, before and after (examples/nylon_decay_fit.py).

    python3 examples/nylon_ab.py [--root=TREE] [--tag=NAME] [OUTDIR]   # default ~/Downloads/nylon_ab

GM 24, dry but for the chamber: a Tarrega-ish arpeggio in E minor, then five
single notes held four seconds each (E2 E3 B3 E4 B4), each one's decay read
off the render (dB/s over 0.3-2.5 s) and printed. --root renders from another
tree, for the A/B.
"""
import os
import subprocess
import sys

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPB = 480
HELD = [40, 52, 59, 64, 71]
# E minor arpeggios, p-i-m-a over a bass, eighth notes: (bass, upper three)
ARP = [(40, (55, 59, 64)), (40, (55, 59, 64)), (45, (57, 60, 64)), (47, (54, 59, 63)),
       (40, (55, 59, 64)), (43, (55, 59, 62)), (47, (54, 57, 63)), (40, (52, 55, 59))]


def build(path):
    m = mido.MidiFile(type=1, ticks_per_beat=TPB)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=int(60e6 / 76), time=0))
    tr.append(mido.Message("program_change", channel=0, program=24, time=0))
    ev, t, e8 = [], 0, TPB // 2
    for bass, up in ARP:
        ev += [(t, 1, bass, 82), (t + 8 * e8 - 20, 0, bass, 0)]
        for k, n in enumerate(up + (up[1],) + up[::-1][1:] + (up[1],)):   # 7 upper eighths
            at = t + (k + 1) * e8
            ev += [(at, 1, n, 70), (at + 3 * e8, 0, n, 0)]
        t += 8 * e8
    t += 4 * TPB
    held_at = []
    for n in HELD:
        held_at.append(t)
        ev += [(t, 1, n, 85), (t + int(4.0 * 76 / 60 * TPB), 0, n, 0)]
        t += int(5.0 * 76 / 60 * TPB)
    now = 0
    for at, on, n, v in sorted(ev, key=lambda e: (e[0], e[1])):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=v, time=at - now)); now = at
    tr.append(mido.MetaMessage("end_of_track", time=TPB * 4))
    m.save(path)
    return [a * 60.0 / (76 * TPB) for a in held_at]


def decays(wav, starts):
    from scipy.io import wavfile
    sr, x = wavfile.read(wav)
    x = x.astype(float).mean(1) if x.ndim > 1 else x.astype(float)
    w = int(0.02 * sr)
    out = []
    for s in starts:
        a, b = int((s + 0.3) * sr), int((s + 2.5) * sr)
        seg = x[a:b]
        e = 10 * np.log10(np.convolve(seg * seg, np.ones(w) / w, "valid") + 1e-20)
        tt = np.arange(len(e)) / sr
        out.append(-np.polyfit(tt, e, 1)[0])
    return out


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.expanduser("~/Downloads/nylon_ab")
    root = next((a.split("=", 1)[1] for a in argv if a.startswith("--root=")), HERE)
    tag = next((a.split("=", 1)[1] for a in argv if a.startswith("--tag=")), "after")
    os.makedirs(out, exist_ok=True)
    P = lambda f: os.path.join(out, tag + f)                 # noqa: E731
    starts = build(P(".mid"))
    env = dict(os.environ, TUNING_REFLECT="0")
    subprocess.check_call([sys.executable, os.path.join(root, "blockrender.py"), P(".mid"), P(".dry.wav"),
                           "hybrid"], env=env, cwd=root)
    print("  %s held decay dB/s (E2 E3 B3 E4 B4): %s" % (tag, "  ".join("%.1f" % d for d in decays(P(".dry.wav"), starts))))
    subprocess.check_call(["sox", P(".dry.wav"), P(".norm.wav"), "reverb", "60", "50", "100", "100", "0", "-6",
                           "gain", "-n", "-1"])
    subprocess.check_call(["lame", "-b", "256", "--quiet", P(".norm.wav"), P(".mp3")])
    for f in (".dry.wav", ".norm.wav"):
        os.remove(P(f))
    print("  -> " + P(".mp3"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
