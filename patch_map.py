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
    MutedTrumpetProperties,
    TromboneProperties,
    HornProperties,
    brass_section,
    WoodPercussionProperties,
    SquareSynthProperties,
    SawtoothSynthProperties,
    GrandPianoProperties,
    HarpsichordProperties, HarpsiRossProperties,
    PluckedStringProperties,
    OrchestraHitProperties,
    NylonGuitarProperties,
    ElectricGuitarProperties,
    JazzGuitarProperties,
    MutedGuitarProperties,
    OverdrivenGuitarProperties,
    DistortionGuitarProperties,
    GuitarHarmonicsProperties,
    GuitarFretNoiseProperties,
    FingeredBassProperties,
    PickedBassProperties,
    FretlessBassProperties,
    SlapBassProperties,
    PoppedBassProperties,
    HammeredDulcimerProperties,
    CrotaleProperties,
    AgogoProperties,
    MembraneDrumProperties,
    TomTomProperties,
    ApplauseProperties,
    BassTromboneProperties,
    BassClarinetProperties,
    AltoFluteProperties,
    BassFluteProperties,
    VesselFluteProperties,
    OcarinaProperties,
    BlownBottleProperties,
    MalletProperties,
    BowedStringProperties,
    SlowBowedStringProperties,
    ViolinProperties,
    ViolaProperties,
    CelloProperties,
    ContrabassProperties,
    slow_bow,
    FlueOrganProperties,
    ReedOrganProperties,
    DrawbarOrganProperties,
    PercussiveOrganProperties,
    RockOrganProperties,
    BrassProperties,
    CylindricalBrassProperties,
    TrumpetProperties,
    ConicalBrassProperties,
    StoppedPipeProperties,
    CylindricalReedProperties,
    OpenPipeProperties,
    ConicalReedProperties,
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
    SoloViolinProperties,)

# 0-based GM program -> property class. Grouped by the 16 GM families of 8.
PROGRAM_CLASS = {}


def _fill(lo, hi, cls):
    for p in range(lo, hi + 1):
        PROGRAM_CLASS[p] = cls


# 0-7    Piano                         -> struck inharmonic strings
_fill(0, 7, GrandPianoProperties)
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
# 16-18 are a HAMMOND, not a pipe organ: one instrument, three registrations.
# They had all been pointed at FlueOrganProperties, which gets the speech, the
# harmonic slope and the tuning of the drawbars wrong, all for the same reason
# -- a tonewheel is not a pipe.
_fill(16, 16, DrawbarOrganProperties)
_fill(17, 17, PercussiveOrganProperties)
_fill(18, 18, RockOrganProperties)
_fill(19, 19, FlueOrganProperties)
_fill(20, 23, ReedOrganProperties)
# 24-31  Guitar                        -> plucked strings
_fill(24, 31, PluckedStringProperties)
# 24 alone is MEASURED (Iowa's guitar is a nylon classical; see
# NylonGuitarProperties). 25-31 keep the body-less family base deliberately: a
# steel-string is a measurably different instrument -- brighter, with plain
# steel trebles where the nylon's are its darkest strings -- and 26-31 are
# electrics, whose colour is an amplifier's, not a box's. A fit for one
# instrument should not silently redefine an unmeasured one (the trap the
# saxophone hit when it inherited the oboe's).
PROGRAM_CLASS[15] = HammeredDulcimerProperties   # STRUCK, not plucked
PROGRAM_CLASS[24] = NylonGuitarProperties
# 27 is the first electric to get its own class, now that there is an amplifier
# and a speaker to give it: see ElectricGuitarProperties and cabinet.py. The
# rest stay on the base ON PURPOSE. 25 is an ACOUSTIC steel-string -- a
# different instrument from both its neighbours, and unmeasured. 29 and 30 are
# this voice with the gain turned up and 26/28 are a pickup position and a
# damping, so they are cheap once 27 has been judged by ear; cheap is not the
# same as done, and handing them a class before then is exactly the trap the
# saxophone hit.
PROGRAM_CLASS[26] = JazzGuitarProperties
PROGRAM_CLASS[27] = ElectricGuitarProperties
PROGRAM_CLASS[28] = MutedGuitarProperties
PROGRAM_CLASS[29] = OverdrivenGuitarProperties
PROGRAM_CLASS[30] = DistortionGuitarProperties
PROGRAM_CLASS[31] = GuitarHarmonicsProperties
# 32-39  Bass                          -> plucked strings
_fill(32, 39, PluckedStringProperties)
# 33-37 are the ELECTRIC basses, and they are the guitar's physics on a longer
# string: two combs, a magnet, and a cabinet built to reach 41 Hz rather than
# to bite. 33/34 differ only in the right hand (finger vs plectrum), 35 in the
# termination (wood, not fret wire), 36/37 in the collision a slap makes.
#
# 32 IS NOT ONE OF THEM. "Acoustic Bass" is an upright -- a large wooden box
# with its own radiating body, which is the one thing a solid-body deliberately
# has not got. Giving it a pickup and a speaker cabinet would be the saxophone
# trap again, and it is unmeasured.
#
# 38-39 are SYNTH basses: they have no string, no pickup and no cabinet, and
# nothing here would be modelling them, only flattering them.
PROGRAM_CLASS[33] = FingeredBassProperties
PROGRAM_CLASS[34] = PickedBassProperties
PROGRAM_CLASS[35] = FretlessBassProperties
PROGRAM_CLASS[36] = SlapBassProperties
PROGRAM_CLASS[37] = PoppedBassProperties
# 40-47  Strings / orchestral
_fill(40, 44, BowedStringProperties)   # violin, viola, cello, contrabass, tremolo
PROGRAM_CLASS[45] = PluckedStringProperties  # pizzicato strings
PROGRAM_CLASS[40] = ViolinProperties         # each instrument now has its own body
PROGRAM_CLASS[41] = ViolaProperties
PROGRAM_CLASS[42] = CelloProperties
PROGRAM_CLASS[43] = ContrabassProperties
PROGRAM_CLASS[46] = PluckedStringProperties  # orchestral harp
PROGRAM_CLASS[47] = TimpaniProperties         # tuned membrane over a bowl, not a bar
# 48-55  Ensemble (strings, choir, voices, orchestra hit)
_fill(48, 55, BowedStringProperties)
PROGRAM_CLASS[49] = SlowBowedStringProperties  # String Ensemble 2: darker section
# 52-54 are PEOPLE, not strings. A voice is a glottal buzz through a tract whose
# fixed formants are what make a vowel a vowel; the bowed-string bucket got the
# "sustained, not percussive" part right and the identifying part wrong. 1950
# notes across the collection, and it is the actual choral writing -- a full SATB
# CANON.MID, satb196, dimin, bwv196, djchp210.
PROGRAM_CLASS[52] = ChoirAahsProperties      # open "ah"
PROGRAM_CLASS[53] = VoiceOohsProperties      # rounded "oo": F1/F2 drop hard
PROGRAM_CLASS[54] = SynthVoiceProperties     # an "eh", steadier than people are
PROGRAM_CLASS[55] = OrchestraHitProperties   # Orchestra Hit: the whole band, one chord,
                                             # short. Was falling through to a SUSTAINED
                                             # bowed string, which is its exact opposite.
# 56-63  Brass, split by bore profile: cylindrical (bright) vs conical (dark)
_fill(56, 63, BrassProperties)              # default (brass section, synth brass)
PROGRAM_CLASS[56] = TrumpetProperties        # fitted to the Iowa trumpet, 3 registers
PROGRAM_CLASS[57] = CylindricalBrassProperties   # Trombone: cylindrical, bright
PROGRAM_CLASS[59] = MutedTrumpetProperties   # Muted Trumpet
PROGRAM_CLASS[58] = ConicalBrassProperties     # Tuba: conical, dark
PROGRAM_CLASS[60] = ConicalBrassProperties     # French Horn: conical, dark
# 64-71  Reed (saxes, oboe, english horn, bassoon, clarinet). The reed ORGAN's
# timbre, but not its drawbars: registerable makes CC11 a stop word, and a
# clarinet has no stops to draw. See CylindricalReedProperties.
_fill(64, 71, ConicalReedProperties)      # saxes and double reeds: CONICAL = open
PROGRAM_CLASS[71] = ClarinetProperties   # the one cylindrical stopped bore
PROGRAM_CLASS[70] = BassoonProperties    # formant an octave and a half below the oboe's
for _p in (64, 65, 66, 67):
    PROGRAM_CLASS[_p] = SaxophoneProperties
# 72-79  Pipe (piccolo, flute, recorder, pan flute, bottle, shakuhachi, whistle, ocarina)
_fill(72, 79, StoppedPipeProperties)
# ...but they are three different bodies, not one. The OPEN pipes have the full
# harmonic series; a PAN PIPE is closed at the bottom and really is odd-only; and
# an ocarina or a bottle is a HELMHOLTZ RESONATOR with no series at all.
#
# 79 used to keep the stopped voice because the Bach files in this collection
# write program 79 for organ flue ranks -- 7714 notes across 15 files. That is
# now deliberately NOT honoured. BE A SUPERSET OF GENERAL MIDI: if a file
# orchestrates an organ out of wind patches, let it, because whoever made it
# chose those patches knowing how they sound on real GM gear. An ocarina is a
# soft pure tone, which is exactly why it reads as a flue rank -- so giving them
# a real ocarina serves that intent better than lending them our organ.
for _p in (72, 73, 74, 77, 78):
    PROGRAM_CLASS[_p] = OpenPipeProperties
# Same Helmholtz body, different EDGE: an ocarina has a fipple and sings, a
# bottle has none and is mostly breath. See the two classes.
PROGRAM_CLASS[76] = BlownBottleProperties
PROGRAM_CLASS[79] = OcarinaProperties
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
PROGRAM_CLASS[110] = SoloViolinProperties  # fiddle -- ONE player, unlike 40-43
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
# 112-119 AND 123-126 WERE ALL STRUCK BARS, and most of them are not. Each of
# these already had a voice in this file, fitted for the drum kit on channel
# 10 and reachable from a melodic channel like any other -- 115 Woodblock was
# pointed at one long ago and its neighbours were left behind. They keep the
# percussion classes' one_shot: a struck drum or bell ignores the stick being
# lifted, so note length is the file's opinion and not the instrument's.
PROGRAM_CLASS[112] = CrotaleProperties          # small tuned bells
PROGRAM_CLASS[113] = AgogoProperties            # the class is named for it
PROGRAM_CLASS[116] = MembraneDrumProperties     # a big drum, not a bar
PROGRAM_CLASS[117] = TomTomProperties           # likewise, and pitched
PROGRAM_CLASS[126] = ApplauseProperties         # noise, not a mallet
# STILL BARS, and each for a reason. 114 Steel Drums is a tuned pan -- a shaped
# metal dome with tuned areas, which nothing here models. 118 Synth Drum has no
# physical referent. 119 Reverse Cymbal needs a BACKWARDS envelope and there is
# no mechanism for one. 123-125 (bird, telephone, helicopter) want voices of
# their own, as 120 fret noise did.
# 120 is GUITAR FRET NOISE, and a struck bar is the wrong thing entirely: a
# mallet voice has fixed modes and a decay where this has a swept fundamental
# and a duration set by the hand. See GuitarFretNoiseProperties -- it is a
# pitched scrape (slide speed / winding pitch), not a hiss, which is also why
# it is not built on its neighbours at 121-122.
PROGRAM_CLASS[120] = GuitarFretNoiseProperties
PROGRAM_CLASS[121] = BreathNoiseProperties   # bwx27c, 339 notes
PROGRAM_CLASS[122] = SeashoreProperties      # rigormrt "Water"
PROGRAM_CLASS[127] = GunshotProperties       # A-Team "Gun Shot"


def property_class_for_program(program):
    """Return the property class for a 0-based GM program number."""
    return PROGRAM_CLASS.get(program & 0x7F, PluckedStringProperties)


# An ENSEMBLE patch is not one instrument, so a single note of it should be
# played by whichever instrument actually plays that note -- basses at the
# bottom, violins at the top -- each with its own body. Same shape as
# percussion_map.percussion_for_note, which has always picked a voice class per
# note rather than per program.
#
# The boundaries are where the sections hand over in ordinary scoring, not where
# the instruments' ranges end (they overlap heavily): below C2 is bass
# territory, C2-B2 is cello, C3-B3 is where violas sit, C4 and up is violins.
BOWED_SPLIT = ((36, ContrabassProperties),      # below C2
               (48, CelloProperties),           # C2 - B2
               (60, ViolaProperties),           # C3 - B3
               (128, ViolinProperties))         # C4 and up

# A brass section is scored the same way a string one is -- tuba at the bottom,
# then trombones, horns, trumpets on top -- and the instruments' bodies differ
# more than the strings' do (trumpet's bell cuts at 1600 Hz, a trombone's at
# 230). Same handover-in-scoring boundaries rather than range limits.
# NO FRENCH HORN. GM 61 is the pop/big-band brass stab -- trumpets and
# trombones -- and horns are an orchestral colour with their own program at 60.
# Putting one in the middle of the section also put a HOLE there, and measurement
# says that is the horn being right rather than wrong: at the same register
# (C4-B4) the Iowa horn's spectral centroid is 492 Hz against the Iowa
# trombone's 891, so a real horn is 45% darker than a real trombone. Correct for
# a horn, wrong for the middle of a brass section.
BRASS_SPLIT = ((40, ConicalBrassProperties),       # below E2: tuba weight
               (60, TromboneProperties),        # E2 - B3
               (128, TrumpetProperties))        # C4 and up
BRASS_ENSEMBLE = {61}

# Programs that are a whole section rather than a named instrument.
BOWED_ENSEMBLE = {44, 48, 50, 51}
BOWED_ENSEMBLE_SLOW = {49}


# A SOLO patch is a family too, and below a certain note it is a DIFFERENT
# INSTRUMENT. General MIDI gives one "Clarinet" and one "Trombone", but a
# clarinet part written below sounding D3 is a BASS clarinet part -- a Bb
# clarinet cannot play those notes at all -- and a trombone part below E2 is a
# bass trombone's. The old model answered by extrapolating the small instrument
# into a register it does not have, which is exactly the register a composer
# reaches for the big one.
#
# Same machinery as BOWED_SPLIT, and the same standard of evidence: each low
# voice here is fitted to its OWN Iowa recording, not guessed from its sibling.
#
# COVERAGE IS OF THE KEYBOARD, NOT OF THE COLLECTION. It is tempting to size
# this table by how many notes the 168-file corpus actually writes below each
# instrument's bottom -- which says clarinet 240, trombone 59, flute ZERO. That
# is the wrong question now that live.py exists: a player can select any patch
# and play the whole keyboard, so every program has to be right over its whole
# range whether or not a file in the collection happens to go there. A corpus is
# a sample; an instrument is a promise.
# Boundaries are the low instrument's REAL bottom sounding note, so the switch
# happens exactly where the small instrument runs out. That makes it a hard
# change of instrument mid-keyboard rather than a crossfade -- which is what an
# orchestrator gets too, and it is audible on a line that crosses it.
SOLO_SPLIT = {
    # --- bowed strings. BOWED_SPLIT already does this for the ENSEMBLES; the
    # solo patches never did, so a violin patch below its open G string was a
    # violin model extrapolated under the instrument.
    40: ((36, ContrabassProperties),     # Violin, bottom G3
         (48, CelloProperties),
         (55, ViolaProperties),
         (128, ViolinProperties)),
    41: ((36, ContrabassProperties),     # Viola, bottom C3
         (48, CelloProperties),
         (128, ViolaProperties)),
    42: ((36, ContrabassProperties),     # Cello, bottom C2
         (128, CelloProperties)),
    # --- brass. Same reasoning as BRASS_SPLIT, applied to the solo patches.
    56: ((40, ConicalBrassProperties),      # Trumpet, bottom E3
         (52, TromboneProperties),
         (128, TrumpetProperties)),
    60: ((34, ConicalBrassProperties),      # French horn, bottom Bb1
         (128, HornProperties)),
    # --- a tenor trombone with an F attachment reaches C2, and parts are
    # routinely written there, so the tenor keeps everything down to C2 even
    # though Iowa only recorded it to E2. Four semitones of extrapolation on a
    # fitted model beats changing instrument where a player would not.
    57: ((36, BassTromboneProperties),
         (128, TromboneProperties)),
    # --- below sounding D3 a Bb clarinet has no notes at all. The collection
    # writes down to MIDI 24, two octaves under it.
    71: ((50, BassClarinetProperties),
         (128, ClarinetProperties)),
    # --- a piccolo cannot play below D5, and below that it is simply a FLUTE.
    # The boundary is the PICCOLO's own bottom, not the flute's -- the whole
    # point of the rule is that each instrument keeps the notes it can play, and
    # writing the flute's B3 here made 72 and 73 the same mapping, which left
    # program 72 with no meaning of its own. The flute's cascade continues
    # underneath, so a low piccolo part descends piccolo -> flute -> alto ->
    # bass rather than jumping straight to a bass flute two octaves down.
    #
    # (The piccolo and the concert flute still share OpenPipeProperties, so
    # above D5 this changes nothing audible today. It changes what the routing
    # MEANS, and it is what a fitted PiccoloProperties would hang from -- Iowa
    # has no piccolo, so there is nothing to fit yet.)
    72: ((55, BassFluteProperties),
         (59, AltoFluteProperties),
         (74, OpenPipeProperties),       # below D5: a flute, not a piccolo
         (128, OpenPipeProperties)),     # D5 and up: the piccolo's own range
    73: ((55, BassFluteProperties),      # Flute, bottom B3 (C4 without a B foot)
         (59, AltoFluteProperties),
         (128, OpenPipeProperties)),
}


def property_class_for_note(program, note):
    """The voice class for one NOTE of one program.

    Identical to property_class_for_program except where a program is really a
    FAMILY: the bowed and brass ensembles, which pick the instrument whose
    register the note is in, and the solo winds and brass whose bottom octave
    belongs to a bigger instrument entirely (SOLO_SPLIT).
    """
    prog = program & 0x7F
    if prog in BRASS_ENSEMBLE:
        for hi, cls in BRASS_SPLIT:
            if note < hi:
                return brass_section(cls)
    if prog in BOWED_ENSEMBLE or prog in BOWED_ENSEMBLE_SLOW:
        for hi, cls in BOWED_SPLIT:
            if note < hi:
                return slow_bow(cls) if prog in BOWED_ENSEMBLE_SLOW else cls
    split = SOLO_SPLIT.get(prog)
    if split is not None:
        for hi, cls in split:
            if note < hi:
                return cls
    return property_class_for_program(prog)

# Each brass instrument has its own comfortable register and its own bore, so
# they cannot share one class: doing so boosted the trombone 3 dB through its
# whole range (trumpet's centre) and the horn 2 dB through its (tuba's centre).
PROGRAM_CLASS[57] = TromboneProperties     # Trombone
PROGRAM_CLASS[60] = HornProperties         # French Horn
PROGRAM_CLASS[61] = TromboneProperties     # Brass Section: routed per note, see BRASS_SPLIT

# WHICH HARPSICHORD. The GM program says "harpsichord" and stops there, but the
# family is wide -- HarpsichordProperties is fitted to a 1970s Zuckermann kit
# (VCSL's English set), the bright nasal end, and HarpsiRossProperties to John
# Sankey's own instrument, which has a strong fundamental and rings 36% longer.
# Neither is more correct; they are different harpsichords, and which one a file
# wants is not something a program number can say.
#
# TUNING_HARPSI=ross selects the other. Deliberately an env switch rather than a
# stop: a stop is a register of ONE instrument, the same strings plucked by a
# different row of jacks, and swapping the whole instrument is not that.
import os as _os
_HARPSI = {'ross': HarpsiRossProperties, 'zuckermann': HarpsichordProperties}
_want = _os.environ.get('TUNING_HARPSI', '').strip().lower()
if _want:
    _cls = _HARPSI.get(_want)
    if _cls is None:
        raise SystemExit("TUNING_HARPSI=%r; have %s" % (_want, ", ".join(sorted(_HARPSI))))
    PROGRAM_CLASS[6] = PROGRAM_CLASS[7] = _cls
