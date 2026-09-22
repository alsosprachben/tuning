#!/usr/bin/env python3
"""GM 62 and 63, Synth Brass: a sawtooth through a RESONANT filter.

    python3 examples/synthbrass.py [outdir]
    python3 examples/synthbrass.py --check

Both sat on BrassProperties, the abstract acoustic brass base -- which carries a
bore, a register centre, an effort tilt and the intonation tendencies of a
played horn. A synthesiser has none of those. The same category error the synth
leads had with the organ pipe, in the family next door.

WHAT GENERAL MIDI ACTUALLY SPECIFIES: nothing about construction. GM Level 1 is
a name list plus behavioural requirements -- 24 voices, channel 10 percussion,
controller response. It gives program 62 the name "Synth Brass 1" and stops. The
only grounding is the Roland SC-55, the reference implementation GM was
co-developed against and which every file in the wild was written for, where 62
is the bright hard stab and 63 the softer slower one.

What GM does say, weakly, is taxonomic: 56-63 is the BRASS family, so these two
are classified as brass substitutes rather than as synth voices, which get their
own families at 80-87 and 88-95.

THE FILTER IS THE PATCH. One or two saws, a resonant low-pass, and an envelope
on the FILTER rather than the amplitude. Two halves, and the first version here
had only one of them:

  the ENVELOPE needed no machinery -- a low-pass closing is upper partials dying
  faster than lower ones, which is harmonic_decay_db, and a front that blooms
  and settles is decay_db against sustain_level.

  the FILTER ITSELF was missing, and that was the real gap. Without the resonant
  peak these two were a bare 1/n saw: spectrally IDENTICAL to each other,
  differing only in an envelope. The bite is the resonance, and a peak is what
  FormantBody makes -- the same thing a real horn's bell does, measured at about
  19 dB above the fundamental on the Iowa trumpet.
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

VOICES = [(56, "trumpet (real)"), (62, "synth brass 1"), (63, "synth brass 2")]


def passage(program):
    """Stabs then a held chord: a synth brass patch is a section stab."""
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=100, time=0))
    for n, b in ((67, .5), (67, .5), (70, .5), (72, 1), (70, .5), (67, 1.5)):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=104, time=0))
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=int(480 * b)))
    for i, n in enumerate((55, 62, 67, 70)):
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=100,
                               time=240 if i == 0 else 0))
    tr.append(mido.Message("note_off", channel=0, note=55, velocity=0, time=480 * 4))
    for n in (62, 67, 70):
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=0))
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return m


def check():
    print("\nthe spectrum at C4, dB relative to the fundamental:\n")
    ks = (1, 2, 3, 4, 6, 8, 12, 16)
    print("  %-16s %s" % ("", " ".join("%6d" % k for k in ks)))
    for gm, lab in VOICES:
        q = P.property_class_for_note(gm, 60)(261.63, 0.0, 1.0, 1.0)
        v = [q.harmonic_volume(k) for k in ks]
        r = v[0] or 1e-12
        print("  %-16s %s" % (lab, " ".join(
            "%6.1f" % (20 * math.log10(max(x, 1e-12) / r)) for x in v)))
    print("\n  A real trumpet's peak is its BELL. The two synth patches' peaks are")
    print("  their filter cutoffs, an octave apart, which is what makes 63 the")
    print("  soft one -- and what makes them differ in spectrum and not only in")
    print("  envelope, which was the whole problem with the first version.\n")

    print("the filter ENVELOPE: decay rate per harmonic, dB/s.")
    print("A low-pass closing means the top of the series falls fastest.\n")
    print("  %-16s %s" % ("", " ".join("%7s" % ("h%d" % k) for k in (1, 2, 4, 8, 16, 32))))
    for gm, lab in VOICES:
        q = P.property_class_for_note(gm, 60)(261.63, 0.0, 1.0, 1.0)
        print("  %-16s %s" % (lab, " ".join(
            "%7.1f" % q.harmonic_decay(k) for k in (1, 2, 4, 8, 16, 32))))

    print("\nand the two oscillators -- a KNOB, not a spread:\n")
    for gm, lab in ((62, "synth brass 1"), (63, "synth brass 2")):
        c = P.property_class_for_note(gm, 60)
        q = c(261.63, 0.0, 1.0, 1.0)
        for g, _, ratio, _, _ in q.unison_voices(261.63, 1, 0.0):
            print("  %-16s second oscillator %+5.1f cents at gain %.2f, attack %.0f ms"
                  % (lab, c.detune_cents, g, 1000 * c.attack_time))
    print("  (the same offset on every note, every time -- unlike a piano's")
    print("   unisons, which are random per note, or a section, random per player)")
    return 0


def main(argv):
    if "--check" in argv:
        return check()
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    for gm, lab in VOICES:
        mid = os.path.join(outdir, "sb%d.mid" % gm)
        out = os.path.join(outdir, "sb%d.wav" % gm)
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
        print("  %2d %-16s %5.1fs -> %s" % (gm, lab, time.time() - t0, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
