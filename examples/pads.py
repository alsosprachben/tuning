#!/usr/bin/env python3
"""GM 88-95, the pads: eight mechanisms, not eight tweaks.

    python3 examples/pads.py [outdir]
    python3 examples/pads.py --check

All eight were one BowedStringProperties. Together with the effects at 96-103
that was sixteen programs on a single voice, and the largest gap in the bank.

WHAT MAKES A PAD A PAD is the swell -- a long attack, a filter that opens with
it, a sustain that holds -- and everything here has that. What separates the
eight is that General MIDI's own names point at eight different MECHANISMS, and
each class gets one the others do not have:

  88 new age    partials slightly STRETCHED: glassy, a shimmer
  89 warm       a low cutoff and a wide chorus, and deliberately nothing else
  90 polysynth  the only one with a front fast enough to play chords in time
  91 choir      VOCAL FORMANTS, from vowels.py's own table
  92 bowed      the longest swell in the family, over a high narrow body
  93 metallic   INHARMONIC, eighteen times the stretch of the glassy pad --
                the one distinction here that is physics and not filtering
  94 halo       ODD HARMONICS ONLY: hollow, with an airy formant above
  95 sweep      the filter sweep itself, an order of magnitude deeper

A STRETCHED SERIES MUST BE SHORTER THAN A HARMONIC ONE, which is not obvious
and cost a correction here. The law is 1 + 0.5*(h^2-1)*B, growing with the
SQUARE of the partial index, so the metallic pad at forty partials put its
fortieth at 238 x f0 -- 78 kHz on an E4, partials the renderer would carry to
the edge of the band and throw away. Capped at fourteen, which is about what a
struck plate actually has.
"""
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import mido

import patch_map as P

PADS = [(88, "new age"), (89, "warm"), (90, "polysynth"), (91, "choir"),
        (92, "bowed"), (93, "metallic"), (94, "halo"), (95, "sweep")]


def passage(program):
    """Held chords: a pad's swell and its chorus are the whole sound."""
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=600000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=100, time=0))
    for chord in ((52, 59, 64, 68), (50, 57, 62, 69), (48, 55, 60, 67)):
        for n in chord:
            tr.append(mido.Message("note_on", channel=0, note=n, velocity=92, time=0))
        tr.append(mido.Message("note_off", channel=0, note=chord[0], velocity=0,
                               time=480 * 5))
        for n in chord[1:]:
            tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return m


def check():
    print("\neach pad and the mechanism it does not share:\n")
    print("  GM  name        attack   odd     B          formants  h16 decay  partials")
    for gm, lab in PADS:
        c = P.property_class_for_note(gm, 64)
        q = c(329.63, 0.0, 1.0, 1.0)
        print("  %2d  %-11s %5.0f ms  %-6s %-10.5g %-9d %5.0f dB/s  %d"
              % (gm, lab, 1000 * c.attack_time, c.odd_only,
                 c.inharmonicity_coefficient, len(c.formants),
                 q.harmonic_decay(16), c.max_harmonic))

    print("\nthe two INHARMONIC pads, by the code's own law")
    print("(stretch = 1 + 0.5*(h^2-1)*B, so it grows with the SQUARE of h):\n")
    for gm, lab in ((88, "new age"), (93, "metallic")):
        c = P.property_class_for_note(gm, 64)
        B = c.inharmonicity_coefficient
        print("  GM %2d %-9s B = %-9.5g capped at %d partials" % (gm, lab, B, c.max_harmonic))
        for h in (4, 8, c.max_harmonic):
            st = 1.0 + 0.5 * (h * h - 1) * B
            print("     h%-3d -> %6.2f x f0 (%+7.1f cents) = %7.0f Hz at E4"
                  % (h, h * st, 1200 * math.log2(st), 329.63 * h * st))
    print("\n  (uncapped at forty partials the metallic pad's h40 sat at 78 kHz)")

    print("\nthe spectrum at E4, dB re the fundamental:\n")
    ks = (1, 2, 3, 4, 6, 8, 12)
    print("  %-14s %s" % ("", " ".join("%6d" % k for k in ks)))
    for gm, lab in PADS:
        q = P.property_class_for_note(gm, 64)(329.63, 0.0, 1.0, 1.0)
        v = [q.harmonic_volume(k) for k in ks]
        r = v[0] or 1e-12
        print("  %2d %-11s %s" % (gm, lab, " ".join(
            "%6.1f" % (20 * math.log10(max(x, 1e-12) / r)) for x in v)))
    print("\n  (GM 94's even harmonics are ABSENT, not quiet -- odd-only is a")
    print("   definition, not a filter)")
    return 0


def main(argv):
    if "--check" in argv:
        return check()
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    for gm, lab in PADS:
        mid = os.path.join(outdir, "pad%d.mid" % gm)
        out = os.path.join(outdir, "pad%d.wav" % gm)
        passage(gm).save(mid)
        env = dict(os.environ)
        env.setdefault("TUNING_ROOM", "chamber")
        env.setdefault("TUNING_MASTER_DB", "-12")
        t0 = time.time()
        r = subprocess.run([sys.executable, os.path.join(ROOT, "blockrender.py"),
                            mid, out, "even"], env=env, cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-2000:]); print(r.stderr[-2000:]); return 1
        print("  %2d %-12s %5.1fs -> %s" % (gm, lab, time.time() - t0, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
