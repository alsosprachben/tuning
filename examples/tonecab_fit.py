#!/usr/bin/env python3
"""A Hammond's own speaker, fitted: the cabinet a tonewheel plays through
without a Leslie (cabinet.HammondSpinet), from the L102's takes.

    python3 examples/tonecab_fit.py measure      the residual, by frequency (cached)
    python3 examples/tonecab_fit.py fit          the cabinet's shape, fitted to it

Peter Corbett's Hammond L102 (Pianobook; ~/Documents/refs/hammond_l102,
sources.md): a 1960s spinet sampled through its OWN speaker, close-miked,
no Leslie, every upper drawbar alone (l102_fit.py). No openly licensed
recording of a tone cabinet (a PR-40's or HR-40's) was found, so this is
the one Hammond speaker heard without rotors: a spinet's, and named so.

THE RESIDUAL IS THE SPEAKER. A drawbar's level in a take is its gain times
its wheel's output times the speaker and the mic at its frequency. Ours,
each drawbar rendered alone with no Leslie (drawbar_fit.render), is its gain
times its wheel's output -- the gains already fitted to these very takes'
same-wheel ratios (l102_fit.py) -- so take minus ours, at every drawbar and
key, leaves the speaker and the mic, by absolute frequency: as the Leslie's
CABINET_DB was found (the drawbar fit's residual on one curve). A constant
offset (the mic's gain) is taken out at 1 kHz.

THE RESIDUAL IS THE SPEAKER ONLY ABOVE 300 Hz. There the drawbars agree
(each within 2-4 dB of the others at a frequency): the hollow near 800 Hz,
the lift at 1.2-1.8 kHz, the fall over 2.5 kHz. Below it the residual climbs
to +30 dB at 87 Hz -- no speaker does that: the spinet's own generator taper
and its swell's loudness compensation (bass boost at a part-closed pedal)
are in it, and the takes cannot part them from the cone. So (Ben,
2026-11-19) the measurement sets the shape over 300 Hz-4 kHz, and THEORY
carries it below: a paper 12" in a console's open back -- its cone's free-air
resonance near 80 Hz, no box peak (an open back has no box to resonate), a
2nd-order roll-off under it -- and flat between that and the measured band,
as the Leslie's CABINET_DB is held flat under 253 Hz. Above 4 kHz the
fitted top corner carries on: a paper cone with no tweeter.

The fit is cab412_fit's shape (FormantBody's bore gain: a low peak, a
presence, a hollow, a notch, a top corner, a low cutoff), the low peak and
cutoff held at theory's, the rest to the residual's median in sixth octaves
over the measured band.
"""
F_LO, F_HI = 300.0, 4500.0                       # where the residual is the speaker
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "examples"))
import l102_fit as LF  # noqa: E402
import tonelib as T  # noqa: E402
import cab412_fit as CF  # noqa: E402

CACHE = os.path.join(os.path.expanduser("~/Documents/refs/hammond_l102"), "tonecab_residual.json")
F = 1000.0 * 2.0 ** (np.arange(-22, 15) / 6.0)       # 79 Hz .. 5 kHz, sixth octaves


def measure():
    rows = []
    for bar in range(len(LF.BARS)):
        for key in LF.KEYS:
            f = 440.0 * 2 ** ((key + 12 - 69) / 12.0) * T.TonewheelProperties.stop_ranks[bar][1]
            if f > LF.FMAX:
                continue
            a, b = LF.rec_level(bar, key), LF.our_level(bar, key)
            if np.isfinite(a) and np.isfinite(b):
                rows.append((float(f), float(a - b), bar, key))
                print("  bar %d key %d  %7.1f Hz  %+6.1f dB" % (bar, key, f, a - b), flush=True)
    with open(CACHE, "w") as fh:
        json.dump(rows, fh)
    return rows


def target(rows):
    f = np.array([r[0] for r in rows])
    d = np.array([r[1] for r in rows])
    out, keep = [], []
    for fc in F:
        m = (f >= fc * 2 ** (-1 / 12)) & (f < fc * 2 ** (1 / 12))
        if m.sum() >= 2:
            out.append(np.median(d[m]))
            keep.append(fc)
    out, keep = np.array(out), np.array(keep)
    ref = np.interp(np.log(1000.0), np.log(keep), out)
    return keep, out - ref


def fit(rows):
    from scipy.optimize import least_squares
    fs, tgt = target(rows)
    m = (fs >= F_LO) & (fs <= F_HI)
    fs, tgt = fs[m], tgt[m]
    # (the peaks and hollows broad: the gain lands on each partial at its
    # own frequency, and a narrow one is the mic's comb, not the cone --
    # cab412_fit's rule)
    # (theory's below 300 Hz: no box peak -- an open back -- and the cone's
    # resonance at 80 Hz, 2nd order; held, not fitted)
    p0 = [150, 200, 0.0, 1500, 1200, 0.4, 800, 500, 0.3, 3500, 800, 0.2, 0.7, 5000, 4, 80, 2]
    lo = [149.9, 199.9, 0.0, 900, 600, 0.0, 400, 400, 0.0, 2600, 400, 0.0, 0.1, 2500, 1, 79.99, 1.999]
    hi = [150.1, 200.1, 1e-6, 2400, 3000, 3.0, 1000, 1500, 0.7, 4500, 1500, 0.7, 2.0, 9000, 12, 80.01, 2.001]
    res = least_squares(lambda p: CF.model(p, fs) - tgt, p0, bounds=(lo, hi))
    err = CF.model(res.x, fs) - tgt
    print("  rms %.2f dB, max %.2f dB over %d points (%.0f Hz-%.0f Hz)"
          % (np.sqrt(np.mean(err ** 2)), np.abs(err).max(), len(fs), fs[0], fs[-1]))
    for nm, v in zip(CF.NAMES, res.x):
        print("  %-14s %10.4g" % (nm, v))
    print("  Hz    " + " ".join("%6.0f" % f for f in fs[::2]))
    print("  meas  " + " ".join("%+6.1f" % v for v in tgt[::2]))
    print("  fit   " + " ".join("%+6.1f" % v for v in CF.model(res.x, fs)[::2]))
    ex = np.array([40.0, 60.0, 80.0, 120.0, 200.0, 300.0, 4000.0, 6000.0, 8000.0])
    print("  whole: " + " ".join("%.0f Hz %+.1f" % (f, v) for f, v in zip(ex, CF.model(res.x, ex))))
    return res.x


def main(argv):
    if len(argv) < 2 or argv[1] not in ("measure", "fit"):
        print(__doc__)
        return 2
    if argv[1] == "measure" or not os.path.exists(CACHE):
        rows = measure()
    else:
        with open(CACHE) as fh:
            rows = json.load(fh)
    if argv[1] == "fit":
        fit(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
