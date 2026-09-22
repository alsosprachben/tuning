#!/usr/bin/env python3
"""GM 61 Brass Section: three measured bodies, and the seam between them.

    python3 examples/brass61.py [outdir]
    python3 examples/brass61.py --check

GM 61 was already better than the coverage doc said -- it routes per register
into trumpet, trombone and tuba SECTIONS of five, and has since brass_section()
was written. The doc reported it as `Trombone`, rated 1, "the trombone stands in
for the whole section", because it asked `property_class_for_program` -- the
no-note fallback -- instead of the router. Fixed there too.

What was genuinely wrong is that it handed over at a SINGLE NOTE. Measured, one
semitone across the C4 break moved the spectrum 13.2 dB on average and 23.2 at
the sixth harmonic, where a semitone inside one instrument moves it 1.5 to 5.6:
a seam two to three times the natural variation.

And the reason is not a tuning detail. A trumpet plays F#3 to D6 and a trombone
E2 to F5 -- they overlap by two octaves, and a section on a unison line at C4
has both of them on it. Handing over at a point was not modelling a section.

--check walks the handover and prints the step at every semitone, which is the
measurement the crossfade was fitted against.
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


def stabs():
    """A section line that crosses BOTH handovers, then a held chord.

    Short hard notes, because GM 61 is the big-band stab and that is where an
    ensemble's entry scatter and its blend are audible.
    """
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=61, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=100, time=0))
    for n in (72, 67, 63, 60, 57, 55, 52, 48, 45, 43, 40, 36, 33):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=104, time=0))
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=360))
    for i, n in enumerate((40, 52, 59, 64)):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=100,
                               time=240 if i == 0 else 0))
    tr.append(mido.Message("note_off", channel=0, note=40, velocity=0, time=480 * 4))
    for n in (52, 59, 64):
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return m


def check():
    print("\nwhat GM 61 actually renders as -- asked of the ROUTER, since the")
    print("program-level class is only the no-note fallback:\n")
    for lo, hi, lab in ((21, 36, "bottom"), (37, 42, "E2 handover"),
                        (43, 56, "middle"), (57, 62, "C4 handover"),
                        (63, 96, "top")):
        seen = []
        for n in range(lo, hi + 1):
            nm = P.property_class_for_note(61, n).__name__.replace("SectionProperties", "")
            if nm not in seen:
                seen.append(nm)
        print("  %-14s %s" % (lab, ", ".join(seen)))

    print("\nthe body moving across the C4 handover:\n")
    print("  note  class                         bell Hz   bore Hz")
    for n in range(56, 64):
        c = P.property_class_for_note(61, n)
        print("  %3d   %-28s %7.0f  %8.0f"
              % (n, c.__name__.replace("SectionProperties", ""),
                 c.bell_cutoff_hz, c.bore_corner_hz))

    print("\nA FREQUENCY BLENDS IN THE LOG DOMAIN. Halfway between a conical")
    print("390 Hz bell and a trumpet's 1600 is the geometric mean, not the")
    print("arithmetic one -- 790 Hz, not 995:\n")
    import tonelib as T
    mid = T.brass_blend(T.ConicalBrassProperties, T.TrumpetProperties, 0.5)
    print("  blended bell cutoff %.0f Hz   (geometric %.0f, linear %.0f)"
          % (mid.bell_cutoff_hz, (390.0 * 1600.0) ** 0.5, 0.5 * (390.0 + 1600.0)))
    return 0


def main(argv):
    if "--check" in argv:
        return check()
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    mid = os.path.join(outdir, "brass61.mid")
    out = os.path.join(outdir, "brass61.wav")
    stabs().save(mid)
    env = dict(os.environ)
    env.setdefault("TUNING_ROOM", "chamber")
    env.setdefault("TUNING_MASTER_DB", "-12")
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "blockrender.py"),
                        mid, out, "even"], env=env, cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:]); return 1
    print("  61 Brass Section  %5.1fs -> %s  (crosses both handovers)"
          % (time.time() - t0, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
