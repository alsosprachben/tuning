#!/usr/bin/env python3
"""Does the modelled steelpan couple like a real one?

    python3 examples/steelpan_check.py [outdir]

Renders isolated strikes and runs the SAME analysis that was run on a real pan
(Freesound 742254, CC0, 28 min, 48 kHz/24-bit mono -- 408 strikes with over a
second of clearance, of which 40 were analysed and 26 are dominated by a single
note). The recording's numbers are quoted here because the audio is not in the
repo; see sources.md for how they were obtained.

WHAT IS BEING CHECKED IS THE COUPLING, not the note. A steelpan's own modes are
tuned 1:2:3 by the maker and that was confirmed to two cents. What this script
measures is the OTHER 23% -- the energy that is not a harmonic of the note
struck, because it belongs to neighbouring note areas answering through the
shared steel.
"""
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mido
import numpy as np

import blockrender as B

SR = 44100.0
PROGRAM = 114
STRIKES = (60, 64, 67, 72, 55, 59)
# TEN SECONDS, because this voice rings for six and a half. At three, every
# strike after the first sat inside the previous ones' ring -- which is
# non-harmonic relative to the new note by definition -- and the control with
# the coupling switched OFF measured 100% non-harmonic, which is what a broken
# measurement looks like. The recording's own clean strikes were chosen the
# same way: 1.5 s before and 2 s after, on a pan whose previous note had
# already decayed.
GAP = 10.0

# MEASURED on the real pan: non-harmonic energy, folded into one octave and
# energy-weighted. This is the target.
REAL = {"m2": 0.0, "M2": 27.0, "m3": 0.0, "M3": 2.0, "P4": 5.0, "TT": 0.0,
        "P5": 20.0, "m6": 7.0, "M6": 0.0, "m7": 31.0, "M7": 0.0}
REAL_SHARE = 23.0              # % of peak energy that is not harmonic
NAMES = ("unison", "m2", "M2", "m3", "M3", "P4", "TT", "P5", "m6", "M6", "m7", "M7")


def render(outdir):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    m = mido.MidiFile(ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(60), time=0))
    tr.append(mido.Message('program_change', program=PROGRAM, channel=0, time=0))
    for i, n in enumerate(STRIKES):
        tr.append(mido.Message('note_on', note=n, velocity=105, channel=0,
                               time=0 if i == 0 else int(480 * GAP)))
        tr.append(mido.Message('note_off', note=n, velocity=0, channel=0, time=240))
    mid = os.path.join(outdir, 'steelpan-strikes.mid')
    m.save(mid)
    out = mid[:-4] + '.wav'
    env = dict(os.environ)
    env.setdefault('TUNING_ROOM', 'chamber')
    env.setdefault('TUNING_MASTER_DB', '-12')
    r = subprocess.run([sys.executable, os.path.join(root, 'blockrender.py'),
                        mid, out, 'even'], env=env, cwd=root,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:]); raise SystemExit(1)
    for l in r.stdout.splitlines():
        if 'sympathetic' in l:
            print("  " + l.strip())
    return out


def peaks(y, sr, top=25):
    y = y * np.hanning(len(y))
    N = 1 << 19
    X = np.abs(np.fft.rfft(y, N)); f = np.arange(len(X)) * sr / N
    m = (f > 60) & (f < 7000); X = X[m]; f = f[m]
    idx = [i for i in range(2, len(X) - 2) if X[i] > X[i - 1] and X[i] >= X[i + 1]]
    idx.sort(key=lambda i: -X[i])
    out = []
    for i in idx:
        if any(abs(f[i] - g) < 10 for g, _ in out):
            continue
        out.append((float(f[i]), float(X[i])))
        if len(out) >= top:
            break
    return out


def main(argv):
    outdir = argv[1] if len(argv) > 1 else '.'
    os.makedirs(outdir, exist_ok=True)
    wav = render(outdir)
    import wave
    w = wave.open(wav); sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype='<i4').astype(float) / 2147483648.0
    x = x.reshape(-1, 2).mean(axis=1)

    # ASK THE RENDERER WHAT THE NOTE IS, do not assume A440. This is a Bach
    # renderer and its default reference is BAROQUE pitch, A=415 -- so note 60
    # sounds at 246.76 Hz and not 261.63. Assuming the modern pitch put every
    # partial a semitone away from where the analysis looked for it, and the
    # control with the coupling switched OFF duly reported 100% non-harmonic.
    FREQ = B.tuning_table('even')
    hist = np.zeros(12); shares = []
    for k, note in enumerate(STRIKES):
        f0 = FREQ[note]
        a = int((k * GAP + 0.05) * sr); b = a + int(0.60 * sr)
        if b > len(x):
            break
        P = peaks(x[a:b], sr)
        if not P:
            continue
        a1 = max([v for g, v in P if abs(g / f0 - 1) < 0.025] + [0.0])
        if a1 <= 0:
            continue
        tot = sum(v * v for _, v in P)
        non = 0.0
        for g, v in P:
            r = g / f0
            if r < 0.3 or r > 4.2:
                continue
            if abs(r - round(r)) < 0.03 and round(r) >= 1:
                continue                      # a harmonic of the note struck
            non += v * v
            hist[int(round(12 * math.log2(r))) % 12] += v * v
        shares.append(100.0 * non / max(tot, 1e-30))
        print("    strike %d (%s): %5.1f%% non-harmonic"
              % (k + 1, note, shares[-1]))

    print()
    print("  NON-HARMONIC SHARE of peak energy -- the coupling itself")
    print("    modelled %.0f%%      real pan %.0f%%" % (np.median(shares), REAL_SHARE))
    print()
    print("  WHERE IT LANDS, folded into one octave and energy-weighted")
    h = 100.0 * hist / max(hist.sum(), 1e-30)
    print("    interval   modelled   real pan")
    for i in range(1, 12):
        if h[i] < 1.0 and REAL.get(NAMES[i], 0) < 1.0:
            continue
        print("      %-6s    %5.1f%%     %5.1f%%" % (NAMES[i], h[i], REAL.get(NAMES[i], 0.0)))
    print()
    print("  A pan's note areas run round the instrument in the CYCLE OF FIFTHS,")
    print("  so one step of body distance is a fifth or a fourth and TWO steps is")
    print("  a major second. That is why P5, P4 and M2 carry the coupling and a")
    print("  semitone carries almost none: a semitone is FIVE steps away across")
    print("  the steel, however close it sounds.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
