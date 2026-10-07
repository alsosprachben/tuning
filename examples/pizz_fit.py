#!/usr/bin/env python3
"""Fit the pizzicato voices to Iowa's recordings: the decay law and the pluck.

    python3 examples/pizz_fit.py [REFS]

REFS (default ~/Documents/refs/pizz) holds violin/ viola/ cello/ bass/ as
examples/pizz_split.py writes them. Each note is measured by
examples/pizz_measure.py, and two laws are fitted per instrument:

THE DECAY, D(m, f0) = (decay_db + harmonic_decay_db * m) * (f0 / 415)^slope,
tonelib's own law in its own convention (D is half the measured amplitude
dB/s; voicefit.cmd_decay). Least squares on log D over every partial of every
note that supports a slope, with a soft-L1 loss so one bad partial cannot
steer it -- not voicefit's two-step median, which fits the slope on D(m=1)
alone and leaves the upper partials to chance.

THE PLUCK POINT, which MOVES. A player plucks a roughly fixed distance from
the bridge, near the end of the fingerboard. Stopping the string shortens it,
so that distance is a larger FRACTION of what sounds: beta = beta_open *
2^(k/12), k semitones above the open string. Past the middle it folds -- a
pluck at 1 - beta excites the same comb as at beta -- so the measured point
rises up each string, peaks near 0.5 and falls back. The cello's C string,
measured: 0.30 open, 0.41 a fourth up, 0.48 at the octave, 0.03 at the
octave and a sixth, against 0.30 * 2^(k/12) folded. One beta_open per
instrument is fitted over every string, each note on the string it was
recorded on; the voices then assume the lowest string that reaches a note
(first position), which is where a pizzicato part mostly lives.
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

from pizz_measure import measure  # noqa: E402

REF_HZ = 415.0
OPEN = {"violin": {"G": 55, "D": 62, "A": 69, "E": 76},
        "viola": {"C": 48, "G": 55, "D": 62, "A": 69},
        "cello": {"C": 36, "G": 43, "D": 50, "A": 57},
        "bass": {"E": 28, "A": 33, "D": 38, "G": 43}}


def fold(b):
    b = np.mod(b, 1.0)
    return np.minimum(b, 1.0 - b)


def fit_decay(rows):
    from scipy.optimize import least_squares
    pts = [(m, r['f0'], d / 2.0) for r in rows for m, d in r['D'] if d > 0]
    m = np.array([p[0] for p in pts], float)
    f = np.array([p[1] for p in pts], float)
    D = np.array([p[2] for p in pts], float)

    def res(p):
        a, b, s = p
        return np.log(np.maximum(a + b * m, 1e-6)) + s * np.log(f / REF_HZ) - np.log(D)
    r = least_squares(res, [20.0, 8.0, 1.0], bounds=([0.0, 0.0, -1.0], [500.0, 200.0, 3.0]),
                      loss='soft_l1', f_scale=0.3)
    a, b, s = r.x
    fit = (a + b * m) * (f / REF_HZ) ** s
    return a, b, s, len(pts), float(np.median(np.abs(np.log(fit / D))))


def fit_pluck(rows, inst, rmin=0.55):
    pts = [(OPEN[inst][r['string'][3:]], r['note'], r['beta'][0]) for r in rows
           if r['beta'] and r['beta'][1] >= rmin and r['string'][3:] in OPEN[inst]
           and r['note'] >= OPEN[inst][r['string'][3:]]]
    k = np.array([n - o for o, n, _ in pts], float)
    meas = np.array([b for _, _, b in pts])
    best = None
    for b0 in np.arange(0.05, 0.45, 0.0025):
        err = np.median(np.abs(fold(b0 * 2 ** (k / 12.0)) - meas))
        if best is None or err < best[1]:
            best = (b0, err)
    # and the null model: one fixed point for every note
    err, fixed = min((np.median(np.abs(b - meas)), b) for b in np.arange(0.05, 0.5, 0.0025))
    return best[0], best[1], fixed, err, len(pts)


BODY = None
TS = (0.05, 0.1, 0.2, 0.3, 0.5, 0.8)


def fundamental_env(path):
    """(f0, dB under its peak at TS) of a note's fundamental band."""
    from voicefit import analytic_env, mono, note_of
    x, sr = mono(path)
    n = note_of(path)
    f0 = 440.0 * 2 ** ((n - 69) / 12.0)
    e = analytic_env(x, sr, f0 * 0.85, f0 * 1.15)
    w = int(0.02 * sr)
    e = np.sqrt(np.convolve(e * e, np.ones(w) / w, 'same'))
    pk = int(np.argmax(e))
    return f0, np.array([20 * np.log10(e[pk + int(t * sr)] / e[pk] + 1e-12)
                         if pk + int(t * sr) < len(e) else np.nan for t in TS])


def fit_envelope(paths, hd_ratio):
    """THE DOUBLE DECAY. A plucked string's motion across the soundboard
    couples hard into the body and dies fast; along it, it carries on -- the
    piano's aftersound, which the kernel already makes: amplitude
    (1 - af) 10^(-D t/10) + af 10^(-r D t/10). Fitted to every note's
    fundamental at TS: D(m=1) = (decay_db + harmonic_decay_db) (f0/415)^slope,
    the two split as the per-partial fit split them (hd_ratio), with af and r.
    Points under -60 dB are left out -- the files are edited to digital
    silence between notes, and a note runs into it."""
    from scipy.optimize import least_squares
    obs = [fundamental_env(p) for p in paths]
    t = np.array(TS)

    def model(p, f0):
        k, s, af, r = p
        D = k * (f0 / REF_HZ) ** s
        a = (1 - af) * 10 ** (-D * t / 10) + af * 10 ** (-r * D * t / 10)
        return 20 * np.log10(np.maximum(a, 1e-9))

    def res(p):
        out = []
        for f0, L in obs:
            ok = np.isfinite(L) & (L > -60)
            out.extend((model(p, f0) - L)[ok])
        return np.array(out)
    r = least_squares(res, [60.0, 1.0, 0.1, 0.2], bounds=([1, -1, 0, 0.02], [800, 3, 0.6, 1.0]),
                      loss='soft_l1', f_scale=3.0)
    k, s, af, rr = r.x
    single = least_squares(lambda p: res([p[0], p[1], 0.0, 1.0]), [60.0, 1.0],
                           bounds=([1, -1], [800, 3]), loss='soft_l1', f_scale=3.0)
    return (k / (1 + hd_ratio), k * hd_ratio / (1 + hd_ratio), s, af, rr,
            float(np.median(np.abs(res(r.x)))), float(np.median(np.abs(res([*single.x, 0.0, 1.0])))))


def ladder_of(cls, f0, nm=10, vel=80):
    """The class's own partial levels at f0, dB under the first, over the
    measurement's window (5-65 ms after the peak: each partial's decay to the
    window's middle taken off). Checked against renders: partials 2-7 within
    1-3 dB of what pizz_measure reads off the rendered note."""
    pr = cls(f0, 0.0, (vel / 127.0) ** 2, 1.0)
    a = np.array([abs(pr.harmonic_volume(m)) * pr.radiation_gain(m * f0) for m in range(1, nm + 1)])
    D = np.array([(pr.decay_db + pr.harmonic_decay_db * m) * pr.decay_register_factor
                  for m in range(1, nm + 1)])
    db = 20 * np.log10(np.maximum(a, 1e-12) / max(a[0], 1e-12)) - 2 * 0.035 * (D - D[0])
    return db


def pluck_profile(rows, base, b0s=np.arange(0.08, 0.401, 0.02)):
    """THE PLUCK POINT, from the ladders rather than the comb. A per-note comb
    fit cannot read the violin's or viola's (their notes are short and high:
    it swung from 0.05 to 0.36 with which notes were trusted), so the open-
    string point is scanned here and, at each value, the colour -- tilt, its
    register term, the notch's depth -- re-fitted around it, and the ladders
    of every note scored. A sharp minimum says the data knows the point; a
    flat profile says it does not, and the geometry should stand."""
    out = []
    for b0 in b0s:
        cls = type("Fit", (base,), dict(pluck_open=float(b0)))
        (e, td, od, sd), _ = fit_tilt(rows, cls, coarse=True)
        out.append((float(b0), e, td, od, sd))
    return out


def fit_tilt(rows, base, coarse=False):
    """tonal_dampening, octave_dampening and strike_depth: the pluck ladder's
    slope, how the slope moves with register, and how deep the finger's notch
    is -- against every note's ladder, partials 2-10 where the recording is
    within 60 dB of its fundamental."""
    import tonelib as T
    obs = [(r['f0'], np.asarray(r['ladder'][:10])) for r in rows if len(r['ladder']) >= 10]
    best = None
    tds = np.arange(0.8, 3.61, 0.2) if coarse else np.arange(0.4, 4.01, 0.1)
    ods = np.arange(-1.0, 0.81, 0.2) if coarse else np.arange(-1.0, 0.81, 0.1)
    for td in tds:
        for od in ods:
            for sd in (0.0, 0.2, 0.35, 0.5, 0.7):
                cls = type("Fit", (base,), dict(tonal_dampening=td, octave_dampening=od,
                                                strike_depth=sd))
                errs = []
                for f0, L in obs:
                    M = ladder_of(cls, f0)
                    ok = L[1:] > -60
                    errs.extend(np.abs(M[1:] - L[1:])[ok])
                e = float(np.median(errs))
                if best is None or e < best[0]:
                    best = (e, td, od, sd)
    cur = []
    for f0, L in obs:
        M = ladder_of(base, f0)
        ok = L[1:] > -60
        cur.extend(np.abs(M[1:] - L[1:])[ok])
    return best, float(np.median(cur))


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    refs = pos[0] if pos else os.path.expanduser("~/Documents/refs/pizz")
    for inst in ("violin", "viola", "cello", "bass"):
        rows = [r for r in (measure(p) for p in sorted(glob.glob(os.path.join(refs, inst, "*.wav")))) if r]
        a, b, s, n, err = fit_decay(rows)
        b0, e0, fixed, efix, npl = fit_pluck(rows, inst)
        c0, ce0, cfixed, cefix, cn = fit_pluck(rows, inst, 0.7)
        t30 = [r['t30'] for r in rows if r['t30']]
        print("%-6s decay_db %6.2f  harmonic_decay_db %6.2f  decay_register_slope %5.3f"
              "  (%d partials, median |log err| %.2f)" % (inst, a, b, s, n, err))
        print("       pluck: beta_open %.3f, rising along the string (median miss %.3f)"
              " -- against one fixed %.3f (miss %.3f); %d notes" % (b0, e0, fixed, efix, npl))
        if "--pluck" in argv and inst in ("violin", "viola"):
            import tonelib as T
            base = T.pizzicato({"violin": T.ViolinProperties, "viola": T.ViolaProperties}[inst])
            for b0, e, td, od, sd in pluck_profile(rows, base):
                print("       pluck_open %.2f: ladder miss %.2f dB  (tilt %.1f, %+.1f, notch %.2f)"
                      % (b0, e, td, od, sd))
        if "--envelope" in argv:
            ps = sorted(glob.glob(os.path.join(refs, inst, "*.wav")))
            dd, hh, ss, af, rr, e2, e1 = fit_envelope(ps, b / a)
            print("       double decay: decay_db %.2f  harmonic_decay_db %.2f  slope %.3f  "
                  "slow share %.3f at %.2f of the rate  (median miss %.1f dB; one stage %.1f)"
                  % (dd, hh, ss, af, rr, e2, e1))
        if "--tilt" in argv:
            import tonelib as T
            base = (T.AcousticBassProperties if inst == "gm32" else
                    T.pizzicato({"violin": T.ViolinProperties, "viola": T.ViolaProperties,
                                 "cello": T.CelloProperties, "bass": T.ContrabassProperties}[inst]))
            (e, td, od, sd), e0 = fit_tilt(rows, base)
            print("       tilt: tonal_dampening %.2f  octave_dampening %+.2f  strike_depth %.2f"
                  "  (median ladder miss %.1f dB, from %.1f as it stands)" % (td, od, sd, e, e0))
        print("       ...on the clearest combs (r >= 0.7): beta_open %.3f (miss %.3f)"
              " against fixed %.3f (miss %.3f); %d notes" % (c0, ce0, cfixed, cefix, cn))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
