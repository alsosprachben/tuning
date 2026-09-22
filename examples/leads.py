#!/usr/bin/env python3
"""GM 80-87, the synth leads: the one family that can be EXACT.

    python3 examples/leads.py [outdir]
    python3 examples/leads.py --check

Everywhere else in this bank the model approximates a physical object and a
recording can contradict it. A sawtooth is not an approximation of anything: it
IS the harmonic series at 1/n, a square IS the odd harmonics at 1/n, a triangle
IS the odd harmonics at 1/n^2. There is no object to measure and nothing a
recording could correct, so an additive engine renders these exactly -- the one
family where this renderer has an advantage over sampling rather than a
handicap.

What General MIDI does NOT specify is everything that turns a waveform into a
lead rather than a buzz: the resonant low-pass, its envelope, the vibrato, the
doubling. GM names eight leads and defines none of them, so the reading here is
the Roland SC-55's, which is what the files in the wild were written for. Those
choices are judgement and say so.

  80 square     odd harmonics at 1/n            exact
  81 sawtooth   every harmonic at 1/n           exact
  82 calliope   odd harmonics at 1/n^2 -- a TRIANGLE, which is why it is the
                soft one. The GM name misleads: a real calliope is a steam
                whistle organ and this patch is nothing like one.
  83 chiff      a saw with a breath on the front -- the organ's own chiff
  84 charang    a saw through the valve the electric guitars use
  85 voice      an oscillator behind vocal formants (an open /a/)
  86 fifths     the waveform and its fifth, +700 cents, exactly
  87 bass+lead  the waveform and an octave below, exactly

A lead's filter envelope is not new machinery: a low-pass sweeping shut is the
upper partials dying faster than the lower ones, which is harmonic_decay_db.
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

LEADS = [(80, "square"), (81, "sawtooth"), (82, "calliope"), (83, "chiff"),
         (84, "charang"), (85, "voice"), (86, "fifths"), (87, "bass+lead")]


def passage(program):
    """A lead line -- these are melody patches, so a melody."""
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=480000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=100, time=0))
    line = [(72, 1), (74, .5), (75, .5), (77, 1), (74, 1),
            (70, 1), (72, .5), (74, .5), (75, 2),
            (67, 1), (70, .5), (72, .5), (74, 1), (72, 1), (70, 3)]
    for n, b in line:
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=100, time=0))
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0,
                               time=int(480 * b)))
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return m


def check():
    print("\nEXACT, checked against the closed form rather than a recording.")
    print("The tolerance is floating point, not decibels:\n")
    for gm, law, nm in ((81, lambda n: 1.0 / n, "sawtooth"),
                        (80, lambda n: 1.0 / n if n % 2 else 0.0, "square"),
                        (82, lambda n: 1.0 / (n * n) if n % 2 else 0.0, "triangle")):
        q = P.property_class_for_program(gm)(261.63, 0.0, 1.0, 1.0)
        v1 = q.harmonic_volume(1)
        worst = max(abs(q.harmonic_volume(n) / v1 - law(n) / law(1))
                    for n in range(1, 33))
        print("  GM %2d %-9s worst deviation over 32 partials: %.1e" % (gm, nm, worst))

    print("\nthe first eight partials, dB re the fundamental:\n")
    print("  GM  lead        %s" % " ".join("%6d" % k for k in range(1, 9)))
    for gm, lab in LEADS:
        q = P.property_class_for_program(gm)(261.63, 0.0, 1.0, 1.0)
        v = [q.harmonic_volume(k) for k in range(1, 9)]
        ref = v[0] or 1e-12
        print("  %2d  %-10s %s" % (gm, lab, " ".join(
            "%6.1f" % (20 * math.log10(max(x, 1e-12) / ref)) for x in v)))
    print("  (a square and a triangle have NO even harmonics; that is the")
    print("   definition, not a roll-off, so those columns are empty by construction)")

    print("\nthe two fixed-interval leads, at A4 = 440 Hz:\n")
    for gm, lab in ((86, "fifths"), (87, "bass+lead")):
        q = P.property_class_for_program(gm)(440.0, 0.0, 1.0, 1.0)
        for g, _, ratio, _, _ in q.unison_voices(440.0, 1, 0.0):
            f = 440.0 * (1.0 + ratio)
            print("  GM %2d %-10s second voice %7.2f Hz  %+8.1f cents  gain %.2f"
                  % (gm, lab, f, 1200 * math.log2(f / 440.0), g))
    print("  (+700.0 is the TEMPERED fifth. A GM oscillator is offset in")
    print("   semitones, so it tracks the tuning in force; just would be +702.0)")

    print("\nand what makes each of the six not-a-plain-waveform leads differ:\n")
    print("  GM  lead        chiff  drive  formants  extra voice")
    for gm, lab in LEADS:
        c = P.property_class_for_program(gm)
        q = c(261.63, 0.0, 1.0, 1.0)
        ex = q.unison_voices(261.63, 1, 0.0)
        print("  %2d  %-10s %5.2f  %5.2f  %8s  %s"
              % (gm, lab, getattr(c, "chiff_volume", 0.0),
                 getattr(c, "amp_drive", 0.0),
                 len(getattr(c, "formants", ())) or "-",
                 ("%.4f x" % (1.0 + ex[0][2])) if ex else "-"))
    return 0


def main(argv):
    if "--check" in argv:
        return check()
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    for gm, lab in LEADS:
        mid = os.path.join(outdir, "lead%d.mid" % gm)
        out = os.path.join(outdir, "lead%d.wav" % gm)
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
        print("  %2d %-11s %5.1fs -> %s" % (gm, lab, time.time() - t0, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
