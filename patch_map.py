"""General MIDI program -> physical-model routing.

Broad first: every one of the 128 GM programs routes to one of a small set
of physical-model property classes, so any GM file renders with a
family-appropriate timbre instead of falling through to a default pluck.
Realism comes later by splitting these buckets into per-instrument classes
and editing this table -- the dispatch stays data-driven.

`property_class_for_program(program)` takes a 0-based GM program number
(0 = Acoustic Grand Piano) and returns a tonelib property class.
"""

from tonelib import (
    Steinway,
    PluckedStringProperties,
    MalletProperties,
    BowedStringProperties,
    FlueOrganProperties,
    ReedOrganProperties,
    BrassProperties,
    BlownPipeProperties,
)

# 0-based GM program -> property class. Grouped by the 16 GM families of 8.
PROGRAM_CLASS = {}


def _fill(lo, hi, cls):
    for p in range(lo, hi + 1):
        PROGRAM_CLASS[p] = cls


# 0-7    Piano                         -> struck inharmonic strings
_fill(0, 7, Steinway)
# 8-15   Chromatic Percussion          -> struck bars/bells
_fill(8, 15, MalletProperties)
# 16-23  Organ                         -> flue pipes; reeds/accordion from 20
_fill(16, 19, FlueOrganProperties)
_fill(20, 23, ReedOrganProperties)
# 24-31  Guitar                        -> plucked strings
_fill(24, 31, PluckedStringProperties)
# 32-39  Bass                          -> plucked strings
_fill(32, 39, PluckedStringProperties)
# 40-47  Strings / orchestral
_fill(40, 44, BowedStringProperties)   # violin, viola, cello, contrabass, tremolo
PROGRAM_CLASS[45] = PluckedStringProperties  # pizzicato strings
PROGRAM_CLASS[46] = PluckedStringProperties  # orchestral harp
PROGRAM_CLASS[47] = MalletProperties         # timpani (pitched membrane; mallet for now)
# 48-55  Ensemble (strings, choir, voices, orchestra hit)
_fill(48, 55, BowedStringProperties)
# 56-63  Brass
_fill(56, 63, BrassProperties)
# 64-71  Reed (saxes, oboe, english horn, bassoon, clarinet)
_fill(64, 71, ReedOrganProperties)
# 72-79  Pipe (piccolo, flute, recorder, pan flute, bottle, shakuhachi, whistle, ocarina)
_fill(72, 79, BlownPipeProperties)
# 80-87  Synth Lead                    -> bright sustained pipe
_fill(80, 87, FlueOrganProperties)
# 88-95  Synth Pad                     -> soft sustained
_fill(88, 95, BowedStringProperties)
# 96-103 Synth FX                      -> sustained
_fill(96, 103, BowedStringProperties)
# 104-111 Ethnic (sitar, banjo, shamisen, koto, kalimba, bagpipe, fiddle, shanai)
_fill(104, 107, PluckedStringProperties)  # sitar, banjo, shamisen, koto
PROGRAM_CLASS[108] = MalletProperties      # kalimba
PROGRAM_CLASS[109] = ReedOrganProperties   # bagpipe
PROGRAM_CLASS[110] = BowedStringProperties # fiddle
PROGRAM_CLASS[111] = ReedOrganProperties   # shanai
# 112-119 Percussive (tinkle bell, agogo, steel drums, woodblock, taiko, melodic tom, synth drum, reverse cymbal)
_fill(112, 119, MalletProperties)
# 120-127 Sound effects (fret noise, breath, seashore, bird, phone, helicopter, applause, gunshot)
_fill(120, 127, MalletProperties)


def property_class_for_program(program):
    """Return the property class for a 0-based GM program number."""
    return PROGRAM_CLASS.get(program & 0x7F, PluckedStringProperties)
