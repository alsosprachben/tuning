#!/usr/bin/env python3
"""GM 38 and 39, Synth Bass: an oscillator under a resonant low-pass.

    python3 examples/synthbass.py [outdir]
    python3 examples/synthbass.py --check

Both fell through to PluckedStringProperties -- the GENERIC plucked string,
which has no `formants` attribute at all -- so a synth bass was a bare string
series with no body, no filter and nothing synthetic about it. The third family
caught by that same hole, after the pizzicato section and the harp.

THE FILTER ENVELOPE IS THE PLUCK. On a bass it is the whole gesture: the
amplitude holds while the FILTER shuts, which is why a synth bass note has a
bright attack and a round body without getting quieter. Measured, the
fundamental decays at 3.7 dB/s and the eighth harmonic at 26.

ONE OSCILLATOR, NO DETUNE -- the opposite of the synth brass, and deliberate.
Two oscillators a few cents apart beat at a rate proportional to frequency: at
C3 that is a shimmer, at E1 it is 0.2 Hz -- a slow wobble in and out of phase
across a whole bar, which down there reads as the part being out of tune rather
than as thickness. Real synth basses are voiced tight for that reason, and where
they use a second oscillator it is an OCTAVE down, which does not beat.

GM 39 IS A SQUARE, which is an exact distinction rather than a tuned one: a
square IS the odd harmonics at 1/n, so its evens are absent by definition and it
is audibly a different instrument from its neighbour rather than the same one
brighter.

AND NEITHER IS TUNED ONTO THE ELECTRIC BASSES. GM 33-37 are modelled
instruments here, so resemblance would be redundancy -- the lesson GM 62/63
taught the hard way, where a synth brass was tuned until it sat 1.7 dB from the
modelled horn and that was recorded as a success.
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

VOICES = [(33, "bass finger (model)"), (38, "synth bass 1 (saw)"),
          (39, "synth bass 2 (square)")]


def passage(program):
    """A bass line, because that is what these are for."""
    m = mido.MidiFile(type=1, ticks_per_beat=480)
    tr = mido.MidiTrack(); m.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))
    tr.append(mido.Message("control_change", channel=0, control=7, value=100, time=0))
    line = [(28, .5), (28, .5), (35, .5), (28, .5), (31, .5), (28, .5), (33, .5), (31, .5),
            (26, .5), (26, .5), (33, .5), (26, .5), (29, .5), (33, .5), (28, 1.5)]
    for n, b in line:
        tr.append(mido.Message("note_on", channel=0, note=n, velocity=102, time=0))
        tr.append(mido.Message("note_off", channel=0, note=n, velocity=0, time=int(480 * b)))
    tr.append(mido.MetaMessage("end_of_track", time=960))
    return m


def check():
    f0 = 41.2
    odd = (1, 3, 5, 7, 9, 11, 13, 15)
    print("\nat E1, the ODD harmonics -- the ones a square also has, so the")
    print("comparison is fair. A square's evens are absent by definition and")
    print("putting them in this table would inflate every difference.\n")
    print("  %-24s %s" % ("", " ".join("%6d" % k for k in odd)))
    rows = {}
    for gm, lab in VOICES:
        q = P.property_class_for_note(gm, 28)(f0, 0.0, 1.0, 1.0)
        v = [q.harmonic_volume(k) for k in odd]
        r = v[0] or 1e-12
        rows[gm] = [20 * math.log10(max(x, 1e-12) / r) for x in v]
        print("  %-24s %s" % (lab, " ".join("%6.1f" % x for x in rows[gm])))
    print()
    for a, b, lab in ((38, 33, "synth bass 1 vs electric"), (39, 33, "synth bass 2 vs electric"),
                      (38, 39, "synth bass 1 vs synth bass 2")):
        print("  %-32s worst %5.1f dB" % (lab, max(abs(x - y) for x, y in zip(rows[a], rows[b]))))

    print("\nand separately, the exact distinction:")
    q = P.property_class_for_note(39, 28)(f0, 0.0, 1.0, 1.0)
    print("  GM 39's evens h2, h4, h6: %s" % ", ".join(
        "%.0f dB" % (20 * math.log10(max(q.harmonic_volume(k), 1e-12) / q.harmonic_volume(1)))
        for k in (2, 4, 6)))

    print("\nthe filter shutting while the amplitude holds (dB/s):\n")
    print("  %-24s %s" % ("", " ".join("%7s" % ("h%d" % k) for k in (1, 2, 4, 8, 16))))
    for gm, lab in VOICES:
        q = P.property_class_for_note(gm, 28)(f0, 0.0, 1.0, 1.0)
        print("  %-24s %s" % (lab, " ".join("%7.1f" % q.harmonic_decay(k)
                                            for k in (1, 2, 4, 8, 16))))

    print("\nand why there is no detune down here:\n")
    for midi, lab in ((28, "E1"), (40, "E2"), (60, "C4")):
        f = 440.0 * 2.0 ** ((midi - 69) / 12.0)
        print("  %-4s a 6-cent detune would beat at %5.2f Hz" % (lab, f * (2 ** (6 / 1200.) - 1)))
    print("  (at E1 that is a wobble lasting most of a bar -- out of tune, not thick)")
    return 0


def main(argv):
    if "--check" in argv:
        return check()
    outdir = argv[1] if len(argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    for gm, lab in VOICES:
        mid = os.path.join(outdir, "bs%d.mid" % gm)
        out = os.path.join(outdir, "bs%d.wav" % gm)
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
        print("  %2d %-24s %5.1fs -> %s" % (gm, lab, time.time() - t0, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
