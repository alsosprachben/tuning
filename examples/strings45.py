#!/usr/bin/env python3
"""GM 44, 45, 46: tremolo strings, pizzicato strings, and the orchestral harp.

    python3 examples/strings45.py [outdir]
    python3 examples/strings45.py --check

All three sat at coverage 1. Two of them -- pizzicato and harp -- were the
GENERIC plucked string, which has no `formants` attribute at all, so they were
rendering with no body whatsoever: a bare string series and a bore roll-off,
nothing of a violin or a harp about either. The third, tremolo strings, was the
generic bowed string, which meant GM 44 and GM 40 rendered identically: the
articulation simply was not there.

  44  the same violin section, bowing rapid unmeasured strokes. Amplitude
      modulation, one sideband pair per partial -- and a PER-PLAYER rate and
      phase, because fourteen players do not count strokes together.
  45  a section plucking, wearing the measured violin body, plucked over the
      end of the fingerboard and damped fast.
  46  plucked with finger flesh in toward the middle of the string, which is
      the darkest place there is, and anchored straight into the soundboard so
      it rings for seconds.
"""
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import mido

VOICES = [(40, "Violin (measured)"), (44, "Tremolo strings"),
          (45, "Pizzicato strings"), (46, "Orchestral harp")]


def passage(program, arpeggio=False):
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=600000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=100, time=0))
    # A rising figure, then a held chord. The chord is where a tremolo shows
    # itself and where a harp's ring does.
    for n in (55, 59, 62, 67, 71, 74):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=92, time=0))
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=360))
    for i, n in enumerate((55, 62, 67, 71)):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=88,
                               time=240 if i == 0 else 0))
    tr.append(mido.Message("note_off", channel=0, note=55, velocity=0, time=480 * 8))
    for n in (62, 67, 71):
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return m


def render(gm, outdir):
    mid = os.path.join(outdir, "str%d.mid" % gm)
    out = os.path.join(outdir, "str%d.wav" % gm)
    passage(gm).save(mid)
    env = dict(os.environ)
    env.setdefault("TUNING_ROOM", "chamber")
    env.setdefault("TUNING_MASTER_DB", "-12")
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "blockrender.py"),
                        mid, out, "even"], env=env, cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:]); return None
    return out, time.time() - t0


def check():
    import patch_map as P
    import tonelib as T
    print("\nthese three had no body. What they have now:\n")
    for gm, lab in VOICES:
        c = P.property_class_for_program(gm)
        print("  %2d %-20s %-26s formants %s"
              % (gm, lab, c.__name__.replace("Properties", ""),
                 getattr(c, "formants", "(NONE -- no body)")))

    print("\nthe pluck point decides the colour (first comb null at 1/p):\n")
    for gm, lab in ((45, "Pizzicato"), (46, "Harp")):
        c = P.property_class_for_program(gm)
        print("  %-12s plucked at %.2f of the length -> first null at h%.1f"
              % (lab, c.strike_point, 1.0 / c.strike_point))

    print("\nhow long a note lasts, which is most of what separates them:\n")
    for gm, lab in ((45, "Pizzicato"), (46, "Harp"), (24, "Nylon guitar")):
        c = P.property_class_for_program(gm)
        print("  %-14s decay %4.2f dB/s, upper partials +%.2f"
              % (lab, c.decay_db, c.harmonic_decay_db))

    print("\nand the tremolo's stroke against the same section's vibrato:\n")
    c = P.property_class_for_program(44)
    print("  tremolo %.1f Hz, depth %.2f, per-player scatter +/-%.0f%%"
          % (c.tremolo_hz, c.tremolo_depth, 100 * c.tremolo_scatter))
    print("  vibrato %.1f-%.1f Hz -- the two must not be confusable, and are not"
          % c.section_vibrato_hz)
    return 0


def main(argv):
    if "--check" in argv:
        return check()
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    for gm, lab in VOICES:
        got = render(gm, outdir)
        if got is None:
            return 1
        print("  %2d %-20s %5.1fs -> %s" % (gm, lab, got[1], got[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
