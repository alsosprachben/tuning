#!/usr/bin/env python3
"""A closed-back 4x12, fitted: cabinet.Guitar412 from measured impulse responses.

    python3 -I examples/cab412_fit.py IR.wav [IR.wav ...]

The IRs are jesterdyne's "Brutal BG412S (V30+DV77)" pack (Freesound pack
34071, CC0; measured only): a 2004 Behringer BG412S, plywood, closed back,
Celestion Vintage 30s, an SM57 close on the cone -- "Even" (616702), "Balls"
(616705) and "Brutal" (616704). Their responses agree within 1-2 dB; the fit
is to their mean in dB at sixth-octave points 50 Hz-8 kHz, 0 dB at 1 kHz.

THE SHAPE IT FINDS (and why each part is there): a box resonance whose peak
is the low-mid, not the sub (an SM57 close on a 4x12 rolls the deep lows off
-- the low E's fundamental is 9 dB under 125 Hz); a broad hollow at 1.5 kHz,
the V30's; presence at 2.5 kHz; a notch near 3 kHz; and a top reaching higher
than the open-backed 12"'s. The pack is "mix ready" by its author's word,
so a shaping EQ may be in it: Ben's ear is the check.

Run with python3 -I: the IRs are downloads, read as data.
"""
import sys

import numpy as np
from scipy.io import wavfile
from scipy.optimize import least_squares

F = 1000.0 * 2.0 ** (np.arange(-26, 19) / 6.0)        # 50 Hz .. 8 kHz, sixth octaves


def response(path):
    sr, x = wavfile.read(path)
    x = x.astype(np.float64)
    if x.ndim > 1:
        x = x.mean(1)
    n = 1 << 17
    db = 20.0 * np.log10(np.abs(np.fft.rfft(x, n)) + 1e-12)
    f = np.fft.rfftfreq(n, 1.0 / sr)

    def band(fc):
        m = (f >= fc * 2 ** (-1 / 12)) & (f < fc * 2 ** (1 / 12))
        return 10.0 * np.log10(np.mean(10.0 ** (db[m] / 10.0)))
    out = np.array([band(fc) for fc in F])
    return out - band(1000.0)


def model(p, f):
    """FormantBody's bore_gain with this shape, in dB re 1 kHz."""
    (fl, bl, al, fp, bp, ap, fh, bh, dh, fn, bn, dn, floor, corner, order, cut, cord) = p

    def g(hz):
        v = floor + al / (1 + ((hz - fl) / (bl / 2)) ** 2) + ap / (1 + ((hz - fp) / (bp / 2)) ** 2)
        v *= 1 - dh / (1 + ((hz - fh) / (bh / 2)) ** 2)
        v *= 1 - dn / (1 + ((hz - fn) / (bn / 2)) ** 2)
        v /= 1 + (hz / corner) ** order
        x = (hz / cut) ** cord
        return v * x / (1 + x)
    return 20.0 * np.log10(g(f) / g(1000.0))


NAMES = ("low peak Hz", "low peak bw", "low peak amp", "presence Hz", "presence bw", "presence amp",
         "hollow Hz", "hollow bw", "hollow depth", "notch Hz", "notch bw", "notch depth",
         "floor", "top corner", "top order", "low cutoff", "low order")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    target = np.mean([response(p) for p in argv[1:]], axis=0)
    p0 = [150, 200, 0.6, 2250, 800, 0.6, 1500, 400, 0.5, 3200, 600, 0.4, 0.55, 6000, 6, 120, 2]
    # (presence below the notch, so the two do not cancel into one)
    # ...AND THE HOLLOWS BROAD: a cabinet's gain is applied at each partial's
    # own frequency, so a notch narrower than the sixth octaves it is fitted
    # over would sink a partial that lands in it by 25 dB (a mic position's
    # comb, not the box) -- at least 400 Hz wide, at most 0.7 deep
    lo = [80, 40, 0.0, 1900, 300, 0.0, 1000, 400, 0.0, 2900, 400, 0.0, 0.1, 3000, 1, 40, 1]
    hi = [300, 600, 3.0, 2600, 2500, 3.0, 2200, 1500, 0.7, 3700, 1500, 0.7, 2.0, 9000, 16, 300, 6]
    fit = least_squares(lambda p: model(p, F) - target, p0, bounds=(lo, hi))
    err = model(fit.x, F) - target
    print("  rms %.2f dB, max %.2f dB over %d points (50 Hz-8 kHz)" % (np.sqrt(np.mean(err ** 2)), np.abs(err).max(), len(F)))
    for nm, v in zip(NAMES, fit.x):
        print("  %-14s %10.4g" % (nm, v))
    print("  Hz    " + " ".join("%6.0f" % f for f in F[::3]))
    print("  meas  " + " ".join("%+6.1f" % v for v in target[::3]))
    print("  fit   " + " ".join("%+6.1f" % v for v in model(fit.x, F)[::3]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
