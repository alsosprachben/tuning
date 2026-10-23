"""GS 111.8 Pungi, fitted to the melody pipe of Nick Mariette's snake charmers
in Bhaktapur (Wikimedia Commons, CC BY 2.5; ~/Documents/refs/commons/pungi/,
sources.md) -- a street, measured only, never sent.

THE CROWD SITS UNDER 700 HZ, so the melody (~440-650 Hz, over a 174 Hz
drone) is tracked by its upper harmonics: per 60 ms frame (20 ms hop), the
f0 in 430-800 Hz whose h2-h7 under 4 kHz stand highest over the midpoints
between them. Runs of the better 60% of frames holding within 35 cents for
0.25 s or more are its held notes (32, A4-D#5). Each note's ladder, h1-h12,
over its middle (30 ms off each end), dB re h2 (h1 has the crowd under it).

Ours: each note at its nearest key for its own length, read the same way;
mode_gains moves by the notes' median miss, harmonic by harmonic.

    python3 examples/pungi_fit.py           # the ladder, take and ours
    python3 examples/pungi_fit.py --fit     # mode_gains, 3 passes
    python3 examples/pungi_fit.py --drone   # the drone pipe's, h1-h8
"""
import glob
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "examples")]
from drum_fit import read  # noqa: E402

TAKE = os.path.expanduser("~/Documents/refs/commons/pungi/*.ogg")
NH = 12


def load():
    with tempfile.TemporaryDirectory() as d:
        w = os.path.join(d, "t.wav")
        subprocess.run(["sox", glob.glob(TAKE)[0], "-e", "floating-point", "-b", "32", "-c", "1", w],
                       check=True)
        x, sr = read(w)
    return x.reshape(len(x), -1).mean(1), sr


def notes(x, sr):
    """[(start, end, f0)] of the held notes."""
    win, hop = int(0.06 * sr), int(0.02 * sr)
    N = 1 << 15
    f = np.fft.rfftfreq(N, 1 / sr)
    w = np.hanning(win)
    cands = np.arange(430, 800, 1.0)
    F, Q = [], []
    for s0 in range(0, len(x) - win, hop):
        Y = np.log(np.abs(np.fft.rfft(x[s0:s0 + win] * w, N)) ** 2 + 1e-20)

        def at(hz):
            i = int(round(hz / f[1]))
            return Y[max(0, i - 2):i + 3].max()
        sc = [np.mean([at(c * h) for h in range(2, 8) if c * h < 4000])
              - np.mean([at(c * (h + 0.5)) for h in range(2, 7)]) for c in cands]
        k = int(np.argmax(sc))
        F.append(cands[k])
        Q.append(sc[k])
    F, Q = np.array(F), np.array(Q)
    good = Q > np.percentile(Q, 40)
    out, i = [], 0
    while i < len(F):
        if not good[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(F) and good[j + 1] and abs(1200 * np.log2(F[j + 1] / np.median(F[i:j + 1]))) < 35:
            j += 1
        if (j - i + 1) * 0.02 >= 0.25:
            out.append((i * 0.02, (j + 1) * 0.02, float(np.median(F[i:j + 1]))))
        i = j + 1
    return out


def ladder(s, sr, f0):
    N = 1 << 17
    Y = 20 * np.log10(np.abs(np.fft.rfft(s * np.hanning(len(s)), N)) + 1e-12)
    f = np.fft.rfftfreq(N, 1 / sr)
    lad = np.array([Y[(f > h * f0 * 0.985) & (f < h * f0 * 1.015)].max() for h in range(1, NH + 1)])
    return lad - lad[1]


def ours(f0, secs):
    import wind_fit as W
    prog, cls = W.use_class("pungi")
    key = int(round(69 + 12 * np.log2(f0 / 440.0)))
    y, sr = W.render(prog, key, secs + 0.1)
    k = int(np.flatnonzero(np.abs(y) > 0.1 * np.abs(y).max())[0])
    return y[k:], sr, 440.0 * 2 ** ((key - 69) / 12.0)


def compare(ns, x, sr):
    R, O = [], []
    for a, b, f0 in ns:
        R.append(ladder(x[int((a + 0.03) * sr):int((b - 0.03) * sr)], sr, f0))
        y, s2, fk = ours(f0, b - a)
        O.append(ladder(y[int(0.03 * s2):int((b - a - 0.03) * s2)], s2, fk))
    return np.median(R, 0), np.median(O, 0)


# THE DRONE PIPE (--drone): its long-term ladder over the whole take, h1-h8
# re h1 (past h8 the melody's harmonics land on its own; h2 stands only 2 dB
# over the street, so it is the least sure)
DRONE_HZ = 173.61
DRONE_LADDER = (0.0, -9.0, -9.0, -17.0, -15.0, -13.0, -13.0, -19.0)


def drone_fit(passes=3):
    import patch_map
    import tonelib
    import wind_fit as W
    D = tonelib.PungiDroneProperties
    patch_map.PROGRAM_CLASS[111] = D
    want = np.array(DRONE_LADDER)
    for n in range(passes + 1):
        y, sr = W.render(111, 53, 2.0)
        k = int(np.flatnonzero(np.abs(y) > 0.1 * np.abs(y).max())[0])
        s = y[k + int(0.3 * sr):k + int(1.8 * sr)]
        N = 1 << 18
        Y = 20 * np.log10(np.abs(np.fft.rfft(s * np.hanning(len(s)), N)) + 1e-12)
        f = np.fft.rfftfreq(N, 1 / sr)
        f0 = 440.0 * 2 ** ((53 - 69) / 12.0)
        got = np.array([Y[(f > h * f0 * 0.985) & (f < h * f0 * 1.015)].max() for h in range(1, 9)])
        got -= got[0]
        d = want - got
        print("  drone pass %d: rms %.1f dB  take %s  ours %s" % (
            n, np.sqrt(np.mean(d[1:] ** 2)), " ".join("%+.0f" % v for v in want),
            " ".join("%+.0f" % v for v in got)), flush=True)
        if n == passes:
            break
        g = list(D.mode_gains)
        for h in range(1, 8):
            g[h] *= 10 ** (d[h] / 20.0)
        for h in range(8, len(g)):
            g[h] *= 10 ** (d[7] / 20.0)
        D.mode_gains = tuple(round(v, 5) for v in g)
    print("    PungiDroneProperties.mode_gains = %s" % (D.mode_gains,))


def main(argv):
    import tonelib
    if "--drone" in argv:
        return drone_fit()
    C = tonelib.PungiProperties
    x, sr = load()
    ns = notes(x, sr)
    print("  %d held notes, %.0f-%.0f Hz" % (len(ns), min(n[2] for n in ns), max(n[2] for n in ns)))
    passes = 3 if "--fit" in argv else 0
    for n in range(passes + 1):
        R, O = compare(ns, x, sr)
        d = R - O
        print("  pass %d: rms %.1f dB (h1-h%d)\n    take %s\n    ours %s" % (
            n, np.sqrt(np.mean(d ** 2)), NH, " ".join("%+.0f" % v for v in R),
            " ".join("%+.0f" % v for v in O)), flush=True)
        if n == passes:
            break
        g = list(C.mode_gains)
        for h in range(NH):
            if h == 1:
                continue        # the reference: re h2, it is the table's anchor in the other
            # (each table is re h2: h1 moves by its own miss less h2's, which is 0)
            g[h] *= 10 ** (d[h] / 20.0)
        # the series beyond h12 follows h12's correction
        for h in range(NH, len(g)):
            g[h] *= 10 ** (d[NH - 1] / 20.0)
        top = g[0]
        C.mode_gains = tuple(round(v / top, 5) for v in g)
    if passes:
        print("    mode_gains = %s" % (C.mode_gains,))


if __name__ == "__main__":
    main(sys.argv[1:])
