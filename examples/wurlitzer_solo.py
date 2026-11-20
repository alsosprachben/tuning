#!/usr/bin/env python3
"""BEN'S WURLITZER'S SOLO AND ACCENT TABS, MEASURED: each upper tab's level with every
Solo and the Accent off (his take 1) and on (take 2) -- the same sequence, nothing
else moved between them -- on its own harmonics (the garage's floor and hum under the
quiet ones would hold a plain RMS up), key by key: C3, C4, C5, told apart by C3's odd
harmonics, which no C4 or C5 has. The boosts tonelib.DividerOrganProperties.level_stops
holds (the median of the three keys).

    python3 examples/wurlitzer_solo.py [REFDIR]
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wurlitzer_survey as WS  # noqa: E402

KEYS = {"C3": 130.81 * 0.983, "C4": 261.63 * 0.983, "C5": 523.25 * 0.983}   # (the organ ~30 cents flat)
# take 1's windows (the tabs alone, in take 2's order; take 2's are WS.TABS')
OFF = {"Tibia 16'": (8.5, 15), "Bass Clarinet 16'": (17, 24), "Trombone 16'": (26, 33), "Flute 8'": (36, 42),
       "Diapason 8'": (45, 52), "String 8'": (55, 61), "Clarinet 8'": (63, 70), "Oboe 8'": (72, 80),
       "Trumpet 8'": (81, 88), "Kinura 8'": (90, 97), "Quint 5-1/3'": (97.5, 105), "Clarinet 4'": (107, 114)}


def _spec(x, s, e):
    seg = x[int((s + 0.3) * WS.SR):int((e - 0.12) * WS.SR)]
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1 << 18)) ** 2
    return sp, np.fft.rfftfreq(1 << 18, 1 / WS.SR)


def _peaks(sp, fr, f0, hs):
    t = 0.0
    for h in hs:
        if f0 * h > 7000:
            break
        m = (fr > f0 * h * 0.99) & (fr < f0 * h * 1.01)
        t += sp[m].max()
    return 10 * np.log10(t + 1e-20)


def keyed(x, a, b, fac):
    """Each note in (a, b) s: its key and its level (dB, harmonics 1-24 to 7 kHz)."""
    out = {}
    for s, e in WS.runs(x, a, b):
        sp, fr = _spec(x, s, e)
        tot = _peaks(sp, fr, KEYS["C3"] * fac, range(1, 25))
        k = "C5"
        for kk in ("C3", "C4"):
            if _peaks(sp, fr, KEYS[kk] * fac, (1, 3, 5, 7)) > tot - 15:
                k = kk
                break
        out.setdefault(k, round(_peaks(sp, fr, KEYS[k] * fac, range(1, 25)), 1))
    return out


def main():
    ref = sys.argv[1] if len(sys.argv) > 1 else WS.REF
    x1, x2 = WS.load("1", ref), WS.load("2", ref)
    on = {n: (w, f) for n, _t, w, f, m in WS.TABS if m == "upper"}
    for n, (a, b) in OFF.items():
        w, fac = on[n]
        d1, d2 = keyed(x1, a, b, fac), keyed(x2, *w, fac)
        bo = {k: round(d2[k] - d1[k], 1) for k in d1 if k in d2}
        print("%-18s off %s  on %s  boost %s  median %s" % (
            n, d1, d2, bo, round(float(np.median(list(bo.values()))), 1) if bo else "-"))


if __name__ == "__main__":
    main()
