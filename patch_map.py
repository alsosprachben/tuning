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
    TromboneProperties,
    BrassSectionProperties,
    HornProperties,
    WoodPercussionProperties,
    SquareSynthProperties,
    SawtoothSynthProperties,
    Steinway,
    HarpsichordProperties,
    PluckedStringProperties,
    MalletProperties,
    BowedStringProperties,
    BowedStringSecondProperties,
    FlueOrganProperties,
    ReedOrganProperties,
    BrassProperties,
    BrightBrassProperties,
    TrumpetProperties,
    DarkBrassProperties,
    BlownPipeProperties,
    OrchestralReedProperties,
    OrchestralFluteProperties,
    DoubleReedProperties,
    ClarinetProperties,
    BassoonProperties,
    SaxophoneProperties,
    SynthLeadProperties,
    ReedPipeProperties,
    TimpaniProperties,
    GlockenspielProperties,
    CelestaProperties,
    MusicBoxProperties,
    VibraphoneProperties,
    MarimbaProperties,
    XylophoneProperties,
    TubularBellProperties,
    ChoirAahsProperties,
    VoiceOohsProperties,
    SynthVoiceProperties,
    BreathNoiseProperties,
    SeashoreProperties,
    GunshotProperties,
)

# 0-based GM program -> property class. Grouped by the 16 GM families of 8.
PROGRAM_CLASS = {}


def _fill(lo, hi, cls):
    for p in range(lo, hi + 1):
        PROGRAM_CLASS[p] = cls


# 0-7    Piano                         -> struck inharmonic strings
_fill(0, 7, Steinway)
# ...except the harpsichords (6 = Harpsichord, 7 = Clavi): PLUCKED, and registered
# (choirs as stops via CC11), not struck. GM files that mean a harpsichord get one.
_fill(6, 7, HarpsichordProperties)
# 8-15   Chromatic Percussion          -> struck bars/bells
# 8-15  Chromatic percussion. These are NOT one instrument: what separates them
# is whether the bar is undercut, and to what interval. See StruckBarProperties.
_fill(8, 15, MalletProperties)
PROGRAM_CLASS[8]  = CelestaProperties       # steel plate, felt hammer
PROGRAM_CLASS[9]  = GlockenspielProperties  # steel bar, not undercut: 2.756
PROGRAM_CLASS[10] = MusicBoxProperties      # plucked steel comb tooth
PROGRAM_CLASS[11] = VibraphoneProperties    # aluminium, undercut 4:1
PROGRAM_CLASS[12] = MarimbaProperties       # rosewood, undercut 4:1
PROGRAM_CLASS[13] = XylophoneProperties     # rosewood, undercut 3:1
PROGRAM_CLASS[14] = TubularBellProperties   # tubes, 2:3:4:5
PROGRAM_CLASS[15] = PluckedStringProperties # dulcimer: struck STRINGS, not a bar
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
PROGRAM_CLASS[47] = TimpaniProperties         # tuned membrane over a bowl, not a bar
# 48-55  Ensemble (strings, choir, voices, orchestra hit)
_fill(48, 55, BowedStringProperties)
PROGRAM_CLASS[49] = BowedStringSecondProperties  # String Ensemble 2: darker section
# 52-54 are PEOPLE, not strings. A voice is a glottal buzz through a tract whose
# fixed formants are what make a vowel a vowel; the bowed-string bucket got the
# "sustained, not percussive" part right and the identifying part wrong. 1950
# notes across the collection, and it is the actual choral writing -- a full SATB
# CANON.MID, satb196, dimin, bwv196, djchp210.
PROGRAM_CLASS[52] = ChoirAahsProperties      # open "ah"
PROGRAM_CLASS[53] = VoiceOohsProperties      # rounded "oo": F1/F2 drop hard
PROGRAM_CLASS[54] = SynthVoiceProperties     # an "eh", steadier than people are
# 56-63  Brass, split by bore profile: cylindrical (bright) vs conical (dark)
_fill(56, 63, BrassProperties)              # default (brass section, synth brass)
PROGRAM_CLASS[56] = TrumpetProperties        # fitted to the Iowa trumpet, 3 registers
PROGRAM_CLASS[57] = BrightBrassProperties   # Trombone: cylindrical, bright
PROGRAM_CLASS[59] = TrumpetProperties        # Muted Trumpet (mute not modelled)
PROGRAM_CLASS[58] = DarkBrassProperties     # Tuba: conical, dark
PROGRAM_CLASS[60] = DarkBrassProperties     # French Horn: conical, dark
# 64-71  Reed (saxes, oboe, english horn, bassoon, clarinet). The reed ORGAN's
# timbre, but not its drawbars: registerable makes CC11 a stop word, and a
# clarinet has no stops to draw. See OrchestralReedProperties.
_fill(64, 71, DoubleReedProperties)      # saxes and double reeds: CONICAL = open
PROGRAM_CLASS[71] = ClarinetProperties   # the one cylindrical stopped bore
PROGRAM_CLASS[70] = BassoonProperties    # formant an octave and a half below the oboe's
for _p in (64, 65, 66, 67):
    PROGRAM_CLASS[_p] = SaxophoneProperties
# 72-79  Pipe (piccolo, flute, recorder, pan flute, bottle, shakuhachi, whistle, ocarina)
_fill(72, 79, BlownPipeProperties)
# ...but the OPEN pipes among them have the full harmonic series, not the odd-only
# one a stopped organ rank wants. 75 (pan flute) and 79 (ocarina) keep the stopped
# voice: a pan pipe IS closed at the bottom, and 79 is how our organ pipeline
# writes flue ranks -- 26735 notes across the Bach corpus depend on it.
for _p in (72, 73, 74, 77, 78):
    PROGRAM_CLASS[_p] = OrchestralFluteProperties
# 80-87  Synth Lead                    -> bright sustained pipe, but no drawbars:
# a synth lead has no stops to draw, and registerable would make CC11 a stop word
# instead of the expression GM says it is. See SynthLeadProperties.
_fill(80, 87, SynthLeadProperties)
# ...except the two that name an actual waveform. An additive engine can BE a
# saw or a square exactly (1/n over all harmonics, or over the odd ones), so
# routing them to an organ pipe threw away the one thing they specify.
PROGRAM_CLASS[80] = SquareSynthProperties        # Lead 1 (square)
PROGRAM_CLASS[81] = SawtoothSynthProperties      # Lead 2 (sawtooth)
# 88-95  Synth Pad                     -> soft sustained
_fill(88, 95, BowedStringProperties)
# 96-103 Synth FX                      -> sustained
_fill(96, 103, BowedStringProperties)
# 104-111 Ethnic (sitar, banjo, shamisen, koto, kalimba, bagpipe, fiddle, shanai)
_fill(104, 107, PluckedStringProperties)  # sitar, banjo, shamisen, koto
PROGRAM_CLASS[108] = MalletProperties      # kalimba
PROGRAM_CLASS[109] = ReedPipeProperties    # bagpipe: a reed and a pipe, no console
PROGRAM_CLASS[110] = BowedStringProperties # fiddle
PROGRAM_CLASS[111] = ReedPipeProperties    # shanai: likewise
# 112-119 Percussive (tinkle bell, agogo, steel drums, woodblock, taiko, melodic tom, synth drum, reverse cymbal)
_fill(112, 119, MalletProperties)
# 115 Woodblock is a TIME-KEEPING voice even on a melodic channel -- a game cue
# plays its samba pattern on five pitches. As a pitched mallet bar it rang for
# 15 seconds a stroke and turned the rhythm into a drone.
PROGRAM_CLASS[115] = WoodPercussionProperties
# 120-127 Sound effects (fret noise, breath, seashore, bird, phone, helicopter, applause, gunshot).
# These are bands of NOISE, and routing them to a struck bar rang a gunshot as a
# tuned bell. The three the collection actually uses now have voices; the rest
# keep the mallet fallback until there is a file to hear them in.
_fill(120, 127, MalletProperties)
PROGRAM_CLASS[121] = BreathNoiseProperties   # bwx27c, 339 notes
PROGRAM_CLASS[122] = SeashoreProperties      # rigormrt "Water"
PROGRAM_CLASS[127] = GunshotProperties       # A-Team "Gun Shot"


def property_class_for_program(program):
    """Return the property class for a 0-based GM program number."""
    return PROGRAM_CLASS.get(program & 0x7F, PluckedStringProperties)

# Each brass instrument has its own comfortable register and its own bore, so
# they cannot share one class: doing so boosted the trombone 3 dB through its
# whole range (trumpet's centre) and the horn 2 dB through its (tuba's centre).
PROGRAM_CLASS[57] = TromboneProperties     # Trombone
PROGRAM_CLASS[60] = HornProperties         # French Horn
PROGRAM_CLASS[61] = BrassSectionProperties  # Brass Section: five players, tenor-ish weight
