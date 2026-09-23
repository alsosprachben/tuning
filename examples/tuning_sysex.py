#!/usr/bin/env python3
"""Put a temperament INTO a MIDI file, as GM2 Scale/Octave Tuning Adjust.

This renderer has twenty temperaments in midilib.tuner_registry and no way to
tell anything else about them. John Sankey's bwv847.mid shows what people do
instead: one pitch class per MIDI channel, one static pitch bend on each, twelve
numbers smuggled through a control that was meant for a gesture. It works, it
costs twelve channels, and no other instrument knows what it means.

GM2 has a message for exactly this. F0 7E <dev> 08 09 ... carries twelve cent
offsets, one per pitch class, for a set of channels -- a temperament, said
plainly, that any GM2 device will honour.

WHAT IT CAN AND CANNOT CARRY. Twelve cents-per-pitch-class is a TEMPERAMENT and
nothing more. It cannot express:

  - a stretched octave (the piano's, which tracks inharmonicity up the compass),
    because every C is forced to the same offset;
  - a tuning that changes with register at all, which is most of what this
    repo's `hybrid` family does;
  - a dynamic tuner, which retunes per chord.

So this is a downgrade for internal use and a portability win for export. The
table below says which of the registry's tuners survive the trip exactly and
which are approximated by their middle octave.

    python3 examples/tuning_sysex.py --list
    python3 examples/tuning_sysex.py --tuner meantone in.mid out.mid
"""
import argparse
import os
import sys

import mido

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import blockrender as B                                      # noqa: E402

REF = 69            # A4: the pitch class offsets are measured against this
OCTAVE = 60         # the octave sampled when a tuner is register-dependent


def cents_of(tuner, base=OCTAVE):
    """Twelve cent offsets against equal temperament, from a registry tuner."""
    freq = B.tuning_table(tuner)
    even = B.tuning_table('even')
    out = []
    for pc in range(12):
        n = base + pc
        out.append(1200.0 * (0.0 if freq[n] == even[n]
                             else __import__('math').log2(freq[n] / even[n])))
    # Anchor on A, so the table is a temperament and not also a pitch shift.
    a = out[(REF - base) % 12]
    return [c - a for c in out]


def stretch_of(tuner):
    """How much this tuner varies BETWEEN octaves -- what the sysex cannot say.

    The spread of one pitch class across the compass. Zero means the tuner is
    a pure temperament and the export is exact.
    """
    import math
    freq = B.tuning_table(tuner)
    even = B.tuning_table('even')
    worst = 0.0
    for pc in range(12):
        vals = []
        for base in (36, 48, 60, 72, 84):
            n = base + pc
            if n in freq and n in even and freq[n] > 0 and even[n] > 0:
                vals.append(1200.0 * math.log2(freq[n] / even[n]))
        if len(vals) > 1:
            worst = max(worst, max(vals) - min(vals))
    return worst


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--tuner', default='meantone')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--one-byte', action='store_true')
    ap.add_argument('infile', nargs='?')
    ap.add_argument('outfile', nargs='?')
    a = ap.parse_args(argv[1:])

    if a.list:
        import midilib
        print("  tuner          spread across the compass   exact as a sysex?")
        for name in sorted(midilib.tuner_registry):
            try:
                s = stretch_of(name)
            except Exception as e:
                print("   %-14s (%s)" % (name, type(e).__name__))
                continue
            print("   %-14s %8.2f cents               %s"
                  % (name, s, "yes" if s < 0.05 else "no, approximated at C4"))
        return 0

    cents = cents_of(a.tuner)
    msg = B.sota_message(cents, two_byte=not a.one_byte)
    print("  %s -> %s" % (a.tuner,
                          " ".join("%+.2f" % c for c in cents)))
    spread = stretch_of(a.tuner)
    if spread >= 0.05:
        print("  NOTE: this tuner varies %.2f cents between octaves, which a"
              % spread)
        print("        scale/octave table cannot carry. Sampled at C4.")
    if not a.infile:
        print("  (no input file; nothing written)")
        return 0
    m = mido.MidiFile(a.infile)
    m.tracks[0].insert(0, mido.Message('sysex', data=msg, time=0))
    m.save(a.outfile or a.infile)
    print("  wrote %s with the tuning in its header" % (a.outfile or a.infile))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
