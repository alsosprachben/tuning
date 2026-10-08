#!/usr/bin/env python3
"""Fit the harp (GM 46) to VSCO 2 CE's: the decay, the pluck point, the colour.

    python3 examples/harp_fit.py [REFS] [--envelope] [--tilt] [--profile]

REFS (default ~/Documents/refs/harp/raw) holds Versilian's 23 plucks,
KSHarp_<note>_<dyn>.wav, E1 to F7 (CC0; ~/Documents/refs/sources.md). Each
note is measured by examples/pizz_measure.py, and fitted with
examples/pizz_fit.py's own laws, so the harp and the pizzicato are held to
the same yardstick:

  decay      D(m, f0) = (decay_db + harmonic_decay_db m) (f0/415)^slope over
             every partial of every note (tonelib's convention: half the
             measured amplitude dB/s)
  --envelope the same with a second, slow stage, to every note's fundamental
  pluck      the comb's point, per note. A harp string is never stopped, so
             there is no stopped_pluck_point here: one fixed point, the
             median of the notes whose comb reads clearly
  --profile  the point scanned, the colour refitted at each: does the
             LADDER agree with the comb?
  --tilt     tonal_dampening, octave_dampening and strike_depth, at the
             fitted point, against every note's ladder
  --model    the class as it stands, rendered dry at every recorded pitch
             (velocity 80, 12 s held) into REFS/../model, and measured by the
             same code beside the recording
"""
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "examples"))
sys.path.insert(0, HERE)

from pizz_measure import measure, report  # noqa: E402
import pizz_fit  # noqa: E402
from pizz_fit import fit_decay, fit_envelope, fit_tilt  # noqa: E402

# A harp note rings for seconds, not the pizzicato's half second: the
# envelope is read out to 3 s, and the notch can be as deep as a centre
# pluck makes it -- the even partials sit 15-25 dB under their neighbours.
pizz_fit.TS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.5, 3.0)
SDS = (0.0, 0.35, 0.5, 0.7, 0.8, 0.9, 0.95)


def fit_point(rows, rmin=0.7):
    b = [r['beta'][0] for r in rows if r['beta'] and r['beta'][1] >= rmin]
    return float(np.median(b)), len(b), b


def main(argv):
    import tonelib as T
    pos = [a for a in argv[1:] if not a.startswith("--")]
    refs = pos[0] if pos else os.path.expanduser("~/Documents/refs/harp/raw")
    paths = sorted(glob.glob(os.path.join(refs, "*.wav")))
    rows = [r for r in (measure(p) for p in paths) if r]
    report(rows, "harp")
    a, b, s, n, err = fit_decay(rows)
    print("decay_db %.2f  harmonic_decay_db %.2f  decay_register_slope %.3f"
          "  (%d partials, median |log err| %.2f)" % (a, b, s, n, err))
    bp, nb, bs = fit_point(rows)
    bp = 0.48 if "--at48" in argv else bp
    print("pluck point %.3f, median of %d notes with r >= 0.7 (%s)"
          % (bp, nb, " ".join("%.2f" % x for x in sorted(bs))))
    if "--model" in argv:
        os.environ.setdefault("TUNING_REFLECT", "0")
        os.environ.setdefault("TUNING_MASTER_DB", "-14")
        import blockrender as B
        import patch_map as PM
        from pizz_model_notes import NAMES, one
        from roomtail import write_wav
        out = os.path.join(os.path.dirname(os.path.normpath(refs)), "model")
        os.makedirs(out, exist_ok=True)
        for r in rows:
            n = r['note']
            write_wav(os.path.join(out, "%s%d.model.wav" % (NAMES[n % 12], n // 12 - 1)),
                      one(PM.BOWED_SPLIT, 46, n, secs=12.0), B.SR)
        report([m for m in (measure(p) for p in sorted(glob.glob(os.path.join(out, "*.wav")))) if m],
               "model")
    if "--envelope" in argv:
        dd, hh, ss, af, rr, e2, e1 = fit_envelope(paths, b / a)
        print("double decay: decay_db %.2f  harmonic_decay_db %.2f  slope %.3f  slow share %.3f"
              " at %.2f of the rate  (median miss %.1f dB; one stage %.1f)"
              % (dd, hh, ss, af, rr, e2, e1))
    base = type("Fit", (T.HarpProperties,), dict(strike_point=bp))
    if "--profile" in argv:
        for p in (0.30, 0.38, 0.44, 0.47, 0.49, 0.50):
            cls = type("Fit", (T.HarpProperties,), dict(strike_point=float(p)))
            (e, td, od, sd), _ = fit_tilt(rows, cls, coarse=True, sds=SDS)
            print("  strike_point %.2f: ladder miss %.2f dB  (tilt %.1f, %+.1f, notch %.2f)"
                  % (p, e, td, od, sd))
    if "--body" in argv:
        # THE LOW END. The soundboard cannot radiate the lowest strings'
        # fundamentals: under ~90 Hz the recording's sits 15-40 dB below its
        # own upper partials. The class's high-pass (bell_cutoff_hz, its
        # order) scanned, the colour refitted at each.
        for bc in (90.0, 130.0, 180.0, 250.0):
            for bo in (2.0, 4.0):
                cls = type("Fit", (base,), dict(bell_cutoff_hz=bc, bell_order=bo))
                (e, td, od, sd), _ = fit_tilt(rows, cls, coarse=True, sds=SDS)
                print("  bell_cutoff_hz %5.0f order %.0f: ladder miss %.2f dB  (tilt %.1f, %+.1f, notch %.2f)"
                      % (bc, bo, e, td, od, sd))
    if "--tilt" in argv:
        (e, td, od, sd), e0 = fit_tilt(rows, base, sds=SDS)
        print("tilt: tonal_dampening %.2f  octave_dampening %+.2f  strike_depth %.2f"
              "  (median ladder miss %.1f dB, from %.1f as it stands)" % (td, od, sd, e, e0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
