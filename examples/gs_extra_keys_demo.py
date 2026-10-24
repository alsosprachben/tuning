"""GS's Snare Roll (key 25) and Shaker (key 82) beside the recordings they
were built from: three of Camo's shakes (VSCO 2 CE, CC0), three of ours; then
lucianodato's snare roll (Freesound 265179, CC0), ours held as long; then the
two in a groove -- the shaker's sixteenths, a roll into each phrase's
downbeat. Writes OUT/gs_extra_keys.wav.

    python3 examples/gs_extra_keys_demo.py OUT
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import tr909_demo as D       # noqa: E402
from drum_fit import read    # noqa: E402

D.TEMPO = 120.0
SHAKES = os.path.expanduser("~/Documents/refs/vsco2/VSCO 1 Percussion/varWood/Camo's Shaker")
ROLL = os.path.expanduser("~/Documents/refs/snare_roll/lucianodato_roll.wav")


def mono(chs):
    return np.asarray(chs[0], float) + np.asarray(chs[1], float)


def ours(note, secs, vel=100):
    mf = D._mid([], secs + 1.0, program=0)
    import mido
    tr = mf.tracks[0]
    tr.insert(-1, mido.Message("note_on", channel=9, note=note, velocity=vel, time=0))
    tr.insert(-1, mido.Message("note_off", channel=9, note=note, velocity=0, time=int(secs * 960)))
    return mono(B.render(mf)[:2])


def rms_match(x, ref):
    return x * np.sqrt(np.mean(ref ** 2) / max(np.mean(x ** 2), 1e-20))


def groove():
    ev = []
    for bar in range(4):
        b0 = bar * 4
        for k in range(16):
            ev.append((b0 + k / 4.0, 82, 100 if k % 4 == 0 else (80 if k % 2 == 0 else 62)))
        ev.append((b0, 36, 110))
        ev.append((b0 + 2, 36, 100))
        ev.append((b0 + 1, 38, 100))
        if bar % 2:
            ev.append((b0 + 3, 25, 84))       # the roll, held into the downbeat
        else:
            ev.append((b0 + 3, 38, 100))
    ev.append((16, 49, 110))
    ev.append((16, 36, 112))
    mf = D._mid(ev, 18, program=0)
    import mido
    # the roll's note held a beat (D._mid holds every note 120 ticks)
    tr = mf.tracks[0]
    t, out = 0, []
    for m in tr:
        t += m.time
        out.append([t, m])
    for x in out:
        if x[1].type == "note_on" and x[1].note == 25 and x[1].velocity == 0:
            x[0] += 480 - 120
    out.sort(key=lambda x: x[0])
    tr.clear()
    last = 0
    for at, m in out:
        tr.append(m.copy(time=at - last))
        last = at
    return mono(B.render(mf)[:2])


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    sr = B.SR
    gap = np.zeros(int(0.35 * sr))
    seq = []
    takes = [read(os.path.join(SHAKES, "shake%d.wav" % k)) for k in (1, 3, 6)]
    takes = [a.sum(1) for a, _sr in takes]
    our = ours(82, 0.3)
    our = our[:int(0.4 * sr)]
    for t in takes:
        seq += [rms_match(t, takes[0]), gap]
    seq.append(gap)
    for _ in range(3):
        seq += [rms_match(our, takes[0]), gap]
    seq += [gap, gap]
    a, _sr = read(ROLL)
    roll = a.sum(1)
    seq += [roll, gap]
    r = ours(25, len(roll) / sr)[:len(roll) + int(0.3 * sr)]
    seq += [rms_match(r, roll), gap, gap]
    g = groove()
    seq.append(rms_match(g, roll) * 0.7)
    y = np.concatenate(seq)
    y *= 10 ** (-1 / 20.0) / np.abs(y).max()
    f = os.path.join(out, "gs_extra_keys.wav")
    B.write_wav(f, y, y)
    print("  " + f)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
