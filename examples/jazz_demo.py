"""The Jazz set (drum program 32) in a swing groove: the ride's swung eighths,
the hi-hat's foot on 2 and 4, Jazz Kick 1 feathered on the quarters, Jazz
Snare 1 comping with ghost notes, Jazz Snare 2 on the accents, a Jazz Kick 2
"bomb" ending each phrase. Writes OUT/jazz_groove.wav (and _room.wav), and
each Jazz drum beside the Standard one it replaces as OUT/jazz_voices.wav.

    python3 examples/jazz_demo.py OUT
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]

import blockrender as B      # noqa: E402
import tr909_demo as D       # noqa: E402

D.TEMPO = 140.0
SWING = 2.0 / 3.0            # the second eighth of a beat, a triplet late


def groove():
    ev = []
    for bar in range(8):
        b0 = bar * 4
        for k in range(4):
            ev.append((b0 + k, 51, 92 if k % 2 else 84))             # ride on the beat
            if k % 2:
                ev.append((b0 + k + SWING, 51, 70))                   # ...and the skip
                ev.append((b0 + k, 44, 70))                           # hat foot on 2 and 4
            ev.append((b0 + k, 36, 46))                               # the kick feathered
        for k, v in ((1 + SWING, 34), (2 + SWING, 40), (3 + SWING, 30)):
            ev.append((b0 + k, 38, v))                                # ghost notes
        if bar % 2:
            ev.append((b0 + 2 + SWING, 40, 104))                      # an accent on the and of 3
            ev.append((b0 + 3 + SWING, 35, 112))                      # ...and the bomb
        else:
            ev.append((b0 + 1, 38, 90))
            ev.append((b0 + 3 + SWING, 38, 96))
    ev.append((32, 35, 110))
    ev.append((32, 51, 100))
    return D._mid(ev, 36, program=32)


def voices():
    ev = []
    for i, (prog, note) in enumerate(((32, 36), (0, 36), (32, 35), (0, 35), (32, 38), (0, 38),
                                      (32, 40), (0, 40))):
        ev.append((prog, 1.5 * i, note))
    out = []
    for prog, beat, note in ev:
        out.append(B.render(D._mid([(0.0, note, 100)], 3, program=prog))[:2])
    return out


def main(argv):
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    L, R = B.render(groove())[:2]
    L, R = np.asarray(L, float), np.asarray(R, float)
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "jazz_groove.wav")
    B.write_wav(f, L * g, R * g)
    subprocess.run([sys.executable, os.path.join(HERE, "roomtail.py"), f,
                    os.path.splitext(f)[0] + "_room.wav"], check=True, stdout=subprocess.DEVNULL)
    print("  " + f)
    parts = []
    for l, r in voices():
        l, r = np.asarray(l, float), np.asarray(r, float)
        n = int(1.6 * B.SR)
        l, r = np.pad(l[:n], (0, max(0, n - len(l)))), np.pad(r[:n], (0, max(0, n - len(r))))
        parts.append((l, r))
    L = np.concatenate([p[0] for p in parts]); R = np.concatenate([p[1] for p in parts])
    g = 10 ** (-1 / 20.0) / max(np.abs(L).max(), np.abs(R).max())
    f = os.path.join(out, "jazz_voices.wav")
    B.write_wav(f, L * g, R * g)
    print("  " + f + "  (Jazz Kick 1, Standard 36, Jazz Kick 2, Standard 35, Jazz Snare 1, "
          "Standard 38, Jazz Snare 2, Standard 40)")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
