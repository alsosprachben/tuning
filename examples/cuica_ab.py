#!/usr/bin/env python3
"""The cuicas (GM 78, 79) by ear, against the recording they were fitted to.

    python3 examples/cuica_ab.py OUT.wav

  1  the low drum (79): three of reinsamba's strokes (take 6) and three of
     ours, alternating -- recorded, ours, recorded, ours ...
  2  the high squeak (78): the same, from take 2
  3  reinsamba's take 5, 2.5 s: a phrase of the low drum, rubbed back and
     forth
  4  ours in a samba figure, 78 and 79 in sixteenths at 100 bpm, two bars

reinsamba's "Cuica" pack (freesound 1339, CC-BY; ~/Documents/refs/sources.md),
close and dry. Ours dry, master -14 dB, two seconds into its file (see
examples/stroke_ab.py: a note at a file's first sample draws its noise along
1/f arcs). Each stroke levelled on its loudest 150 ms.
"""
import glob
import os
import sys
import wave

import mido
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)
os.environ.setdefault("TUNING_REFLECT", "0")
os.environ.setdefault("TUNING_MASTER_DB", "-14")

import crash_fit as C  # noqa: E402
from drum_fit import read  # noqa: E402

SR = 44100
REFS = os.path.expanduser("~/Documents/refs/freesound/cuica/reinsamba")
# (take, stroke onsets in s), each stroke cut 0.35 s long
LOW = (6, (0.53, 1.08, 2.15))
HIGH = (2, (0.65, 1.35, 2.02))
PHRASE = (5, 0.0, 2.5)
LEAD = 2.0


def take(n):
    a, sr = read(glob.glob(os.path.join(REFS, "*__reinsamba__cuica-%d.wav" % n))[0])
    assert sr == SR
    return a.sum(1)


def strokes(n, ts, secs=0.35):
    x = take(n)
    return [x[int((t - 0.03) * SR):int((t - 0.03 + secs) * SR)] for t in ts]


def ours(events, secs):
    import blockrender as B
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack()
    m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=600000, time=0))
    last = 0
    for t, n in sorted(events):
        tk = int((t + LEAD) * 800)
        tr.append(mido.Message("note_on", channel=9, note=n, velocity=100, time=tk - last))
        tr.append(mido.Message("note_off", channel=9, note=n, velocity=0, time=10))
        last = tk + 10
    tr.append(mido.Message("note_off", channel=9, note=79, velocity=0, time=int(secs * 800)))
    L, R = B.render(m)[:2]
    assert B.SR == SR
    x = np.asarray(L, np.float64) + np.asarray(R, np.float64)
    return x[int((LEAD - 0.03) * SR):int((LEAD - 0.03 + secs) * SR)]


def lvl(x):
    return C.level([x], SR)


def main(argv):
    out = argv[1]
    gap = np.zeros(int(0.25 * SR))
    z = []
    top = None
    for (n, ts), note in ((LOW, 79), (HIGH, 78)):
        rec = strokes(n, ts)
        mine = ours([(0.0, note)], 0.35)
        top = top if top is not None else lvl(rec[0])
        for r in rec:
            z += [r * 10 ** ((top - lvl(r)) / 20), gap, mine * 10 ** ((top - lvl(mine)) / 20), gap, gap]
        z.append(gap)
    n, t0, t1 = PHRASE
    ph = take(n)[int(t0 * SR):int(t1 * SR)]
    z += [ph * 10 ** ((top - lvl(ph)) / 20), gap, gap]
    sixteenth = 0.15
    pat = [78, 79, 79, 78, 0, 79, 78, 79] * 4
    fig = ours([(i * sixteenth, k) for i, k in enumerate(pat) if k], len(pat) * sixteenth + 0.5)
    z.append(fig * 10 ** ((top - lvl(fig)) / 20))
    z = np.concatenate(z)
    z *= 0.5 / np.abs(z).max()
    w = wave.open(out, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((z * 32767).astype("<i2").tobytes())
    w.close()
    print("->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
