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
    AcousticBassProperties,
    SteelGuitarProperties,
    BrightPianoProperties,
    ClavinetProperties,
    ElectricGrandProperties,
    HonkyTonkProperties,
    RhodesProperties,
    WurlitzerProperties,
    MutedTrumpetProperties,
    TromboneProperties,
    HornProperties,
    brass_section,
    WoodPercussionProperties,
    SquareSynthProperties,
    SawtoothSynthProperties,
    TriangleSynthProperties,
    ChiffLeadProperties,
    CharangLeadProperties,
    VoiceLeadProperties,
    FifthsLeadProperties,
    BassLeadProperties,
    SynthBrass1Properties,
    SynthBass1Properties,
    SynthStrings1Properties,
    NewAgePadProperties,
    RainFXProperties,
    BanjoProperties,
    ReverseCymbalProperties,
    SynthDrumProperties,
    ShamisenProperties,
    KotoProperties,
    KalimbaProperties,
    BagpipeProperties,
    ShanaiProperties,
    SoundtrackFXProperties,
    CrystalFXProperties,
    AtmosphereFXProperties,
    BrightnessFXProperties,
    GoblinsFXProperties,
    EchoesFXProperties,
    SciFiFXProperties,
    WarmPadProperties,
    PolysynthPadProperties,
    ChoirPadProperties,
    BowedPadProperties,
    MetallicPadProperties,
    HaloPadProperties,
    SweepPadProperties,
    SynthStrings2Properties,
    SynthBass2Properties,
    SynthBrass2Properties,
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
    SteelPanProperties,
    SitarProperties,
    BassTromboneProperties,
    BassClarinetProperties,
    AltoFluteProperties,
    BassFluteProperties,
    VesselFluteProperties,
    OcarinaProperties,
    BlownBottleProperties,
    RecorderProperties,
    PanFluteProperties,
    ShakuhachiProperties,
    WhistleProperties,
    MalletProperties,
    BowedStringProperties,
    SlowBowedStringProperties,
    ViolinProperties,
    ViolaProperties,
    CelloProperties,
    ContrabassProperties,
    tremolo_bow,
    pizzicato,
    brass_blend,
    PizzicatoStringsProperties,
    HarpProperties,
    slow_bow,
    FlueOrganProperties,
    ReedOrganProperties,
    ReedOrganFreeProperties,
    AccordionProperties,
    TangoAccordionProperties,
    HarmonicaProperties,
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
# ...and 1 (Bright Acoustic) is the same piano voiced HARD: a shorter hammer
# contact time, and felt that spreads about half as much under force so the
# strike comb keeps its notch. GM names no instrument, and its own Wide/Dark
# variations say brightness is a timbral axis rather than another piano.
PROGRAM_CLASS[1] = BrightPianoProperties   # the grand, voiced hard
# ...and 3 (Honky-tonk) is the same piano with the tuner's hand off. The grand
# already models a unison as one string at pitch and two mistuned around it; a
# honky-tonk just widens that range from under 2 cents to 8-20.
PROGRAM_CLASS[3] = HonkyTonkProperties     # the grand, badly tuned
# ...and 2 (Electric Grand) is a Yamaha CP-70: a real grand action and real
# strings, but with NO SOUNDBOARD and a piezo under the bridge, and short enough
# that its bass strings are a twelfth as stiff-tuned again as a concert grand's.
PROGRAM_CLASS[2] = ElectricGrandProperties  # short strings, no board, bridge piezo
# ...and 7 (Clavi) is not a harpsichord: a clavinet is a STRUCK steel string
# trapped against an anvil by a rubber tangent and read by MAGNETS, where the
# harpsichord voice it borrowed is plucked, wooden and carries no pickup at all.
# The tangent is the string's termination, so the strike comb rises instead of
# notching -- that is the buzz. See ClavinetProperties.
PROGRAM_CLASS[7] = ClavinetProperties     # struck string, anvil, magnetic pickup
# ...and 4 (Electric Piano 1) is not a piano at all. A Rhodes is a struck steel
# TINE read by a magnetic pickup: no strings, no soundboard, no unison trios,
# so none of the piano's stretch or beating. Measured, the tine vibrates as a
# pure sine and every harmonic is made by the pickup. See ElectricPianoProperties.
PROGRAM_CLASS[4] = RhodesProperties       # tine + bell-curve magnetic pickup
# ...and 5 (Electric Piano 2) is a Wurlitzer: a free steel REED read by an
# electrostatic pickup, where capacitance goes as 1/d. A pole rather than a bell
# curve, so its harmonics fall off geometrically instead of off a cliff -- bark
# rather than bell -- and it has no tonebar at all.
PROGRAM_CLASS[5] = WurlitzerProperties    # reed + 1/d electrostatic pickup
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
# 20-23 are FREE reeds, and were rendering as a pipe organ's reed RANK -- a
# beating reed with a resonator, which is what ReedOrganProperties is (and it
# stays that, being the base of the clarinets and ReedPipeProperties). A free
# reed swings through a slot with no resonator at all, so it has no odd-only
# selection and no high break-back. See tonelib.FreeReedProperties.
_fill(20, 23, ReedOrganFreeProperties)
PROGRAM_CLASS[21] = AccordionProperties        # musette: banks tuned apart
PROGRAM_CLASS[22] = HarmonicaProperties        # one reed and two cupped hands
PROGRAM_CLASS[23] = TangoAccordionProperties   # a bandoneon is tuned DRY
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
# 25 Acoustic Guitar (steel) fell through to the generic plucked string, which
# has NO BODY -- formants None, bore_corner_hz 0 -- so it rendered as a bare
# string beside the one guitar in the set with a measured one. It inherits that
# body and changes the string, the pick and how much top the box passes.
PROGRAM_CLASS[25] = SteelGuitarProperties  # steel strings on the measured body
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
# trap again.
#
# AND ITS BODY IS NOT UNMEASURED AFTER ALL, which is what changed: GM 43
# Contrabass is the SAME INSTRUMENT, fitted against the Iowa double bass across
# three registers. Arco and pizzicato differ by excitation, not by box. So 32
# takes that measured body with a PLUCKED base under it -- copied rather than
# inherited, because ContrabassProperties is bowed and subclassing it would
# claim a plucked instrument is a driven one. See AcousticBassProperties.
PROGRAM_CLASS[32] = AcousticBassProperties   # the measured upright, pizzicato
#
# 38-39 are SYNTH basses: they have no string, no pickup and no cabinet, and
# nothing here would be modelling them, only flattering them.
PROGRAM_CLASS[33] = FingeredBassProperties
PROGRAM_CLASS[34] = PickedBassProperties
PROGRAM_CLASS[35] = FretlessBassProperties
PROGRAM_CLASS[36] = SlapBassProperties
PROGRAM_CLASS[37] = PoppedBassProperties
# 38 and 39 are SYNTHESISERS and had been falling through to the generic plucked
# string -- which has no `formants` attribute at all, so they were a bare string
# series with no body and no filter. An oscillator under a resonant low-pass,
# and deliberately not tuned onto the electric basses above: those are modelled
# instruments here, so resemblance would be redundancy.
PROGRAM_CLASS[38] = SynthBass1Properties   # saw, low cutoff: the round one
PROGRAM_CLASS[39] = SynthBass2Properties   # square, higher and more resonant
# 40-47  Strings / orchestral
_fill(40, 44, BowedStringProperties)   # violin, viola, cello, contrabass, tremolo
# 44 is an ARTICULATION, not an instrument, and it rides on whichever body the
# register picks -- a low tremolo is a CELLO section bowing tremolo. So it is
# applied in property_class_for_note below, beside the slow bow of GM 49, and
# NOT as a PROGRAM_CLASS entry: 44 is in BOWED_ENSEMBLE, so the per-note router
# would override any class set here (and did, silently, until it was measured).
# 45 and 46 were BOTH the generic plucked string, which has no `formants`
# attribute at all -- so a pizzicato section and a harp were being rendered with
# no body whatsoever. 45 wears the measured violin body and plucks; 46 is its
# own instrument.
# Routed per register in property_class_for_note, as 44 is; this is the
# fallback for anything that asks for the program without a note.
PROGRAM_CLASS[45] = PizzicatoStringsProperties
PROGRAM_CLASS[40] = ViolinProperties         # each instrument now has its own body
PROGRAM_CLASS[41] = ViolaProperties
PROGRAM_CLASS[42] = CelloProperties
PROGRAM_CLASS[43] = ContrabassProperties
PROGRAM_CLASS[46] = HarpProperties            # plucked near the middle, and it rings
PROGRAM_CLASS[47] = TimpaniProperties         # tuned membrane over a bowl, not a bar
# 48-55  Ensemble (strings, choir, voices, orchestra hit)
_fill(48, 55, BowedStringProperties)
PROGRAM_CLASS[49] = SlowBowedStringProperties  # String Ensemble 2: darker section
PROGRAM_CLASS[50] = SynthStrings1Properties   # a string MACHINE: chorus, not section
PROGRAM_CLASS[51] = SynthStrings2Properties   # ...slower swell, wider chorus
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
# 72-79 differ in the three things that decide what a flue instrument sounds
# like: whether the tube is OPEN or CLOSED, how the jet is aimed, and how much
# of the breath misses the edge entirely. Four of them had none of that.
PROGRAM_CLASS[74] = RecorderProperties     # a fipple DUCT: a fixed jet, so pure
PROGRAM_CLASS[75] = PanFluteProperties     # closed tube (odd), and mostly breath
PROGRAM_CLASS[76] = BlownBottleProperties
PROGRAM_CLASS[77] = ShakuhachiProperties   # a knife-edge notch; breathiest of all
# A HUMAN whistle is a Helmholtz resonator, not a pipe -- one resonance tuned by
# the tongue, which is why whistling has no registers and is nearly a sine. It
# belongs with the ocarina and the bottle, where GM already put it.
PROGRAM_CLASS[78] = WhistleProperties
PROGRAM_CLASS[79] = OcarinaProperties
# 80-87  Synth Lead                    -> bright sustained pipe, but no drawbars:
# a synth lead has no stops to draw, and registerable would make CC11 a stop word
# instead of the expression GM says it is. See SynthLeadProperties.
_fill(80, 87, SynthLeadProperties)
# ...except the two that name an actual waveform. An additive engine can BE a
# saw or a square exactly (1/n over all harmonics, or over the odd ones), so
# routing them to an organ pipe threw away the one thing they specify.
# 80-87 are the one family in the bank whose targets are SPECIFICATIONS rather
# than instruments: a sawtooth IS the series at 1/n and a square IS the odd
# harmonics at 1/n, so an additive engine renders them exactly. What General
# MIDI does not specify is anything that makes a waveform a lead rather than a
# buzz, so the readings below are the Roland SC-55's, which is what the files in
# the wild were written for. See tonelib, above TriangleSynthProperties.
PROGRAM_CLASS[80] = SquareSynthProperties        # Lead 1 (square): odd, 1/n
PROGRAM_CLASS[81] = SawtoothSynthProperties      # Lead 2 (sawtooth): all, 1/n
PROGRAM_CLASS[82] = TriangleSynthProperties      # Lead 3 (calliope): odd, 1/n^2
PROGRAM_CLASS[83] = ChiffLeadProperties          # Lead 4 (chiff): a breath on the front
PROGRAM_CLASS[84] = CharangLeadProperties        # Lead 5 (charang): through the valve
PROGRAM_CLASS[85] = VoiceLeadProperties          # Lead 6 (voice): vocal formants
PROGRAM_CLASS[86] = FifthsLeadProperties         # Lead 7 (fifths): +700 cents
PROGRAM_CLASS[87] = BassLeadProperties           # Lead 8 (bass+lead): an octave below
# 88-95  Synth Pad                     -> soft sustained
# 88-95 were one BowedStringProperties -- together with 96-103 that was sixteen
# programs on a single voice, the largest gap in the bank. GM's own names point
# at eight different MECHANISMS, not eight tweaks to one sound, and each class
# below gets one the others do not have. See tonelib.SynthPadProperties.
_fill(88, 95, BowedStringProperties)
PROGRAM_CLASS[88] = NewAgePadProperties     # glassy: partials slightly stretched
PROGRAM_CLASS[89] = WarmPadProperties       # low cutoff, wide chorus, nothing else
PROGRAM_CLASS[90] = PolysynthPadProperties  # bright, and fast enough to play
PROGRAM_CLASS[91] = ChoirPadProperties      # vocal formants, from vowels.py
PROGRAM_CLASS[92] = BowedPadProperties      # bowed glass: the longest swell
PROGRAM_CLASS[93] = MetallicPadProperties   # INHARMONIC -- what metal means
PROGRAM_CLASS[94] = HaloPadProperties       # odd harmonics only: hollow, airy
PROGRAM_CLASS[95] = SweepPadProperties      # the filter sweep IS the patch
# 96-103 Synth FX                      -> sustained
# 96-103 were the LAST block of eight on one voice. Most of these are pads with
# one unusual property pushed to the front, so they are built on the pads -- and
# each gets a mechanism the others do not. See tonelib.SynthEffectProperties,
# and note that the echo is the section's own per-player entry offsets, evenly
# spaced instead of drawn.
_fill(96, 103, BowedStringProperties)
PROGRAM_CLASS[96] = RainFXProperties         # stretched AND echoing: droplets
PROGRAM_CLASS[97] = SoundtrackFXProperties   # the widest chorus and longest swell
PROGRAM_CLASS[98] = CrystalFXProperties      # the most inharmonic voice in the bank
PROGRAM_CLASS[99] = AtmosphereFXProperties   # BREATH -- sustain_jitter, as a pan pipe
PROGRAM_CLASS[100] = BrightnessFXProperties  # the hardest front and nothing rolled off
PROGRAM_CLASS[101] = GoblinsFXProperties     # a deep slow WOBBLE, and dark with it
PROGRAM_CLASS[102] = EchoesFXProperties      # the delay line itself
PROGRAM_CLASS[103] = SciFiFXProperties       # odd harmonics AND a deep sweep
# 104-111 Ethnic (sitar, banjo, shamisen, koto, kalimba, bagpipe, fiddle, shanai)
_fill(104, 107, PluckedStringProperties)  # sitar, banjo, shamisen, koto
# 104 has SYMPATHETIC STRINGS, which is the whole instrument: thirteen tuned
# strings under the frets that nobody plays. See SitarProperties. 105-107 stay
# on the base -- a banjo is a membrane rather than a soundboard and a koto has
# movable bridges, and neither is measured.
PROGRAM_CLASS[104] = SitarProperties
# 105-108 were the generic plucked string and the generic mallet; 109 and 111
# shared one reed pipe. Each is a different MECHANISM: a string over a drumhead
# (105, 106), a long silk string over a wooden box (107), a plucked cantilever
# (108), a fixed-pitch DRONE (109), and a conical double reed (111).
PROGRAM_CLASS[105] = BanjoProperties      # steel over a head: thin low, fast decay
PROGRAM_CLASS[106] = ShamisenProperties   # the same head, plus a sawari buzz
PROGRAM_CLASS[107] = KotoProperties       # long slack silk over a light wooden box
PROGRAM_CLASS[108] = KalimbaProperties    # a CANTILEVER: 1 : 6.267 : 17.55
PROGRAM_CLASS[109] = BagpipeProperties    # the drones, at a pitch the melody cannot move
PROGRAM_CLASS[111] = ShanaiProperties     # a cone, so the evens come back
# 108, 109 and 111 are set above and were being overwritten HERE -- the same
# shape as GM 32, where PROGRAM_CLASS[32] sat above a _fill that clobbered it:
# the class existed, was correct, and was never reached. Caught by asking
# property_class_for_note what it returns rather than trusting the assignment.
PROGRAM_CLASS[110] = SoloViolinProperties  # fiddle -- ONE player, unlike 40-43
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
PROGRAM_CLASS[114] = SteelPanProperties          # tuned 1:2:3, not a bar
# The two CATEGORY ERRORS in this family, both on the generic mallet base.
# 118 is an electronic drum -- an oscillator with a downward pitch sweep, which
# is tension_bend and needed nothing new. 119 is a cymbal played BACKWARDS,
# which needed the attack to be allowed past 45% of the note; see
# SynthProperties.attack_fraction_max.
PROGRAM_CLASS[118] = SynthDrumProperties        # an 808 tom, not a bar
PROGRAM_CLASS[119] = ReverseCymbalProperties    # the measured crash, reversed
PROGRAM_CLASS[126] = ApplauseProperties         # noise, not a mallet
# STILL BARS, and each for a reason. 118 Synth Drum has no physical referent.
# 119 Reverse Cymbal needs a BACKWARDS envelope and there is no mechanism for
# one. 123-125 (bird, telephone, helicopter) want voices of their own, as 120
# fret noise did.
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

# HOW WIDE THE HANDOVER IS. A trumpet plays F#3 to D6 and a trombone E2 to F5,
# so they overlap by two octaves and a section on a unison line has both of them
# on it -- the hard split at a single note was not modelling a section at all.
# Measured, one semitone across the old C4 boundary moved the spectrum 13.2 dB
# on average and 23.2 at the sixth harmonic, where a semitone inside one
# instrument moves it 1.5 to 5.6.
#
# Six semitones, twice the piano's string_crossfade_semitones, because the real
# overlap here is two octaves rather than a voicing detail -- but not wider,
# because a blend spread across the whole overlap would leave no note sounding
# like either instrument, and the point of the split is that a trumpet and a
# trombone are different.
BRASS_CROSSFADE_SEMITONES = 6.0


def _brass_body(note):
    """The brass body for one note: one instrument, or a blend across a break."""
    half = BRASS_CROSSFADE_SEMITONES / 2.0
    prev = None
    for hi, cls in BRASS_SPLIT:
        if note < hi:
            # `hi` is the note the NEXT instrument starts at, and `prev` the one
            # this one took over from. Blend on whichever break is close.
            if prev is not None and note < prev[0] + half:
                t = 0.5 + (note - prev[0]) / (2.0 * half)
                return brass_blend(prev[1], cls, t)
            nxt = next((c for h, c in BRASS_SPLIT if h > hi), None)
            if nxt is not None and note >= hi - half:
                t = (note - (hi - half)) / (2.0 * half)
                return brass_blend(cls, nxt, t)
            return cls
        prev = (hi, cls)
    return BRASS_SPLIT[-1][1]



# Programs that are a whole section rather than a named instrument.
# 50 and 51 are NOT bowed and are no longer here. They were, so they routed per
# register to the four measured string bodies and rendered IDENTICALLY to GM 48
# -- three programs, one voice. A string machine has one oscillator per key and
# a chorus; see tonelib.SynthStringsProperties.
BOWED_ENSEMBLE = {44, 48}
BOWED_ENSEMBLE_SLOW = {49}
# A PIZZICATO SECTION IS SCORED THE SAME WAY A BOWED ONE IS, so it splits at the
# same notes -- but it is NOT bowed, and putting 45 in BOWED_ENSEMBLE would give
# it a bow. It takes the same BOWED_SPLIT boundaries through its own transform,
# which lends the plucked class that instrument's body rather than the reverse.
PIZZ_ENSEMBLE = {45}


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
        return brass_section(_brass_body(note))
    if prog in PIZZ_ENSEMBLE:
        for hi, cls in BOWED_SPLIT:
            if note < hi:
                return pizzicato(cls)
    if prog in BOWED_ENSEMBLE or prog in BOWED_ENSEMBLE_SLOW:
        for hi, cls in BOWED_SPLIT:
            if note < hi:
                if prog in BOWED_ENSEMBLE_SLOW:
                    return slow_bow(cls)
                # GM 44 is the same section bowing tremolo: the articulation
                # rides on the body the register chose. See tonelib.tremolo_bow.
                if prog == 44:
                    return tremolo_bow(cls)
                return cls
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
# 62 and 63 are SYNTHESISER patches, not brass. They had been on the acoustic
# brass base, which carries a bore, a register centre and the intonation
# tendencies of a played horn -- the same category error the synth leads had
# with the organ pipe. A synth brass is a sawtooth through a filter envelope,
# and the two programs differ in that envelope. See tonelib.SynthBrassProperties.
PROGRAM_CLASS[62] = SynthBrass1Properties  # the bright stab: fast, deep sweep
PROGRAM_CLASS[63] = SynthBrass2Properties  # the soft pad: slower, shallower

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
