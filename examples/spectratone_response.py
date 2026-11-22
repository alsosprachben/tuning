"""The Spectra-Tone's rotor path against the console speakers, by frequency.

Ben's takes (2026-11-21, one mic, one gain): each partial of Flute 8 through
the rotor (st_warm, the slow half: the organ warm, levels averaged over whole
turns) less the same partial dry (st_dry C3-C6, st_gaps C7: Spectra-Tone off,
the console speakers). The divider's tab tables already hold the console
speakers, so this difference is what the rotor path does on top of them.

    python3 examples/spectratone_response.py      -> RESPONSE_DB points
"""
import os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spectratone_fit as F

ROT = ("st_warm.wav", 113.0, 226.0, (2, 3, 4, 5, 6, 7))
DRY = (("st_dry.wav", 0.0, None, (3, 4, 5, 6)), ("st_gaps.wav", 0.0, 20.0, (7,)))


def levels(name, lo, hi, notes, harmonics=8, floor_db=-75.0):
    x, sr = F.load(name)
    segs = F.segments(x, sr, notes, lo, hi)
    out = {}
    for o, (t0, t1) in segs.items():
        xs = x[int(t0 * sr):int(t1 * sr)]
        for h in range(1, harmonics + 1):
            f = F.C[o] * h
            if f > 9000:
                break
            z = F.env_db(F.band(xs, sr, f), sr)[20:-20]
            lv = 20 * np.log10(np.mean(10 ** (z / 20)) + 1e-12)      # the mean amplitude over the hold
            if lv > floor_db:
                out[(o, h)] = (f, lv)
    return out


def main(argv):
    rot = levels(*ROT)
    dry = {}
    for d in DRY:
        dry.update(levels(*d))
    rows = sorted((rot[k][0], rot[k][1] - dry[k][1]) for k in rot if k in dry)
    for f, d in rows:
        print("%7.1f Hz  rotor - dry %+6.1f dB" % (f, d))
    # one point per third of an octave, the median of the partials in it, re the median overall
    ref = float(np.median([d for _, d in rows]))
    pts = []
    edges = 2.0 ** (np.arange(np.log2(100), np.log2(9000), 1 / 3.0))
    for a in edges:
        b = a * 2 ** (1 / 3.0)
        ds = [d for f, d in rows if a <= f < b]
        if len(ds) >= 1:
            pts.append((round(float(np.sqrt(a * b)), 0), round(float(np.median(ds) - ref), 1)))
    print("level re the console (median) %+.1f dB" % ref)
    print("RESPONSE_DB =", tuple(pts))


if __name__ == "__main__":
    main(sys.argv)
