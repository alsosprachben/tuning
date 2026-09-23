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

AND --mts, WHICH CARRIES ALL OF THEM. The MIDI Tuning Standard's Bulk Tuning
Dump is 128 KEYS at 100/16384 of a cent, and every tuner here is already a
fixed 128-key table -- `dynamic` included -- so every one survives, stretched
octaves and all, and it carries ABSOLUTE pitch: `hybrid` arrives at A415
rather than being re-anchored on A like the scale/octave export. The file then
selects it on each channel with RPN 0/4 and 0/3. It is honoured by the `gm2`
tuner, which is the one that lets a file own its tuning (see mts.py).

    python3 examples/tuning_sysex.py --list
    python3 examples/tuning_sysex.py --tuner meantone in.mid out.mid
    python3 examples/tuning_sysex.py --mts --tuner stretch in.mid out.mid
    python3 blockrender.py out.mid out.wav gm2
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


def mts_error_of(tuner):
    """(worst cents on the keys a dump can hold, [keys it cannot]).

    Measured, not asserted: the table goes through the encoder and the parser
    and comes back. The keys it cannot hold are outside the word's range --
    below MIDI note 0's 8.18 Hz or above just under 13.3 kHz -- which in
    practice is the sub-audio bottom of an A415 tuner and `dynamic`'s top five.
    """
    import math
    import numpy as np
    import mts
    t = mts.builtin_table(tuner)
    if t is None:
        return None, []
    back = mts.parse_mts(mts.bulk_dump_message(t, 0, tuner))[4]
    lo, hi = mts.word_to_hz(0, 0, 0), mts.word_to_hz(127, 127, 126)
    inr = (t >= lo) & (t <= hi)
    err = float(np.abs(1200.0 * np.log2(back[inr] / t[inr])).max())
    return err, [int(k) for k in np.nonzero(~inr)[0]]


def with_mts(infile, outfile, tuner, program=127, bank=0):
    """Write `infile` with `tuner` carried as an MTS dump and selected.

    Program 127 of bank 0 by default: clear of the built-ins, which occupy the
    bottom of bank 0 and only ever grow upward. Every channel but 10 selects
    it, since percussion is not a temperament.
    """
    import mts
    table = B.tuning_table(tuner)
    head = [mido.Message('sysex', data=mts.bulk_dump_message(
        table, program, tuner, bank=bank if bank else None), time=0)]
    for ch in range(16):
        if ch == 9:
            continue
        for cc, v in ((101, 0), (100, 4), (6, bank), (101, 0), (100, 3), (6, program)):
            head.append(mido.Message('control_change', channel=ch, control=cc,
                                     value=v, time=0))
    m = mido.MidiFile(infile)
    for i, msg in enumerate(head):
        m.tracks[0].insert(i, msg)
    m.save(outfile)
    return len(head)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--tuner', default='meantone')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--one-byte', action='store_true')
    ap.add_argument('--mts', action='store_true',
                    help='carry the whole 128-key table as an MTS bulk dump')
    ap.add_argument('--program', type=int, default=127)
    ap.add_argument('infile', nargs='?')
    ap.add_argument('outfile', nargs='?')
    a = ap.parse_args(argv[1:])

    if a.list:
        import midilib
        print("  tuner          spread across   as scale/octave        as MTS dump")
        print("                 the compass")
        for name in sorted(midilib.tuner_registry):
            try:
                s = stretch_of(name)
                e, out = mts_error_of(name)
            except Exception as ex:
                print("   %-14s (%s)" % (name, type(ex).__name__))
                continue
            so = "exact" if s < 0.05 else "approximated at C4"
            mt = ("could not build" if e is None else
                  "%.4f c%s" % (e, "" if not out else
                                ", keys %s out of range" % out))
            print("   %-14s %8.2f cents   %-22s %s" % (name, s, so, mt))
        return 0

    if a.mts:
        if not a.infile:
            e, out = mts_error_of(a.tuner)
            print("  %s as an MTS dump: worst %.4f cents%s" % (
                a.tuner, e, "" if not out else "; keys %s out of range" % out))
            print("  (no input file; nothing written)")
            return 0
        n = with_mts(a.infile, a.outfile or a.infile, a.tuner, a.program)
        print("  wrote %s: %s as MTS program %d, selected on 15 channels "
              "(%d messages). Render it with the gm2 tuner."
              % (a.outfile or a.infile, a.tuner, a.program, n))
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
