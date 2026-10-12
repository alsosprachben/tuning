#!/usr/bin/env python3
"""A pipe's SPEECH and its RELEASE, against the Pitea organ's (GM 19).

    python3 examples/pitea_speech.py [--rank="principal 8"]

THE ATTACK, from each pipe's sample (examples/pitea_fit.py has the set): over
its first 400 ms, in 10 ms frames, four courses each dB re its own steady level
(1.5-2.5 s): the fundamental, h2-h4, h5 and up (each harmonic's own line), and
the BREATH -- the spectrum between the partials (their lines and their widths
taken out), 300 Hz-8 kHz.

THE RELEASE, from the set's release samples (rel00450: what the pipe does
after a 450 ms note, the key lifting at the sample's start): the same four
courses over 600 ms, dB re the release's first 20 ms.

Ours the same: the rank alone (pitea_fit.render), held 3 s for the attack; held
450 ms and released for the release, read from the note-off.
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
import pitea_fit as P  # noqa: E402
import tonelib as T  # noqa: E402

HOP, WIN = 0.01, 0.04
KEYS = (36, 48, 60, 72, 84)


def courses(x, sr, f0, a, secs, ref=None):
    """[fund, low, high, breath] dB courses from sample a over secs."""
    x = x.mean(1) if x.ndim == 2 else x
    W = int(WIN * sr)
    N = 1 << 14
    fr = np.fft.rfftfreq(N, 1.0 / sr)
    win = np.hanning(W)
    hm = np.zeros(len(fr), bool)
    lines = {}
    for m in range(1, 64):
        if m * f0 > 0.45 * sr:
            break
        b = np.abs(fr - m * f0) < max(0.25 * f0, 3 * sr / W)
        lines[m] = b
        hm |= b
    gap = (~hm) & (fr > 300) & (fr < 8000)
    out = []
    for i in range(int(secs / HOP)):
        s = x[a + int(i * HOP * sr): a + int(i * HOP * sr) + W]
        if len(s) < W:
            break
        P2 = np.abs(np.fft.rfft(s * win, N)) ** 2
        f1 = P2[lines[1]].max()
        lo = sum(P2[lines[m]].max() for m in (2, 3, 4) if m in lines)
        hi = sum(P2[lines[m]].max() for m in lines if m >= 5)
        br = np.median(P2[gap]) if gap.any() else 1e-30
        out.append([f1, lo, hi, br])
    c = 10 * np.log10(np.array(out) + 1e-30)
    if ref is None:
        ref = c[-1]
    return c - ref


def steady(x, sr, f0, a):
    c = courses(x, sr, f0, a + int(1.5 * sr), 1.0, ref=np.zeros(4))
    return np.median(c, 0)


def onset(x):
    m = x.mean(1) if x.ndim == 2 else x
    return int(np.flatnonzero(np.abs(m) > np.abs(m).max() * 0.003)[0])


def main(argv):
    rank = next((a.split("=", 1)[1] for a in argv if a.startswith("--rank=")), "principal 8")
    ratio = dict((r[0], r[1]) for r in T.FlueOrganProperties.stop_ranks)[rank]
    folder = os.path.join(P.PITEA, P.FOLDER[rank])
    T_ATT = (0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.2, 0.3)
    T_REL = (0.0, 0.03, 0.06, 0.1, 0.15, 0.2, 0.3, 0.45)
    names = ("fund", "h2-4", "h5+", "breath")
    for key in KEYS:
        p = glob.glob(os.path.join(folder, "%03d-*.wav" % key))
        r = glob.glob(os.path.join(folder, "rel00450", "%03d-*.wav" % key))
        if not p:
            continue
        f0 = 440.0 * 2 ** ((key - 69) / 12.0) * ratio
        x, sr = P.read(p[0])
        a = onset(x)
        st = steady(x, sr, f0, a)
        rc = courses(x, sr, f0, a, 0.4, ref=st)
        y, s2 = P.render(rank, key, 3.0)
        b = 0
        sto = steady(y, s2, f0, b)
        oc = courses(y, s2, f0, b, 0.4, ref=sto)
        print("  == key %d, %.0f Hz: ATTACK, dB re steady at %s ms" % (key, f0, " ".join("%d" % (t * 1000) for t in T_ATT)))
        for j, n in enumerate(names):
            print("    %-6s rec  %s" % (n, " ".join("%+6.1f" % rc[int(t / HOP), j] for t in T_ATT)))
            print("    %-6s ours %s" % ("", " ".join("%+6.1f" % oc[int(t / HOP), j] for t in T_ATT)))
        print("    breath at steady re the fundamental: rec %+.1f, ours %+.1f dB" % (st[3] - st[0], sto[3] - sto[0]))
        if r:
            xr, srr = P.read(r[0])
            rr = courses(xr, srr, f0, 0, 0.6)
            rr = rr - rr[:2].mean(0)
            yo, s3 = P.render(rank, key, 0.45)
            off = int(0.45 * s3)
            ro = courses(yo, s3, f0, off, 0.6)
            ro = ro - ro[:2].mean(0)
            print("    RELEASE, dB re its first 20 ms at %s ms" % " ".join("%d" % (t * 1000) for t in T_REL))
            for j, n in enumerate(names):
                print("    %-6s rec  %s" % (n, " ".join("%+6.1f" % rr[min(int(t / HOP), len(rr) - 1), j] for t in T_REL)))
                print("    %-6s ours %s" % ("", " ".join("%+6.1f" % ro[min(int(t / HOP), len(ro) - 1), j] for t in T_REL)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
