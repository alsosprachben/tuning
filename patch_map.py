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
    TaikoProperties,
    MelodicAgogoHighProperties,
    MelodicAgogoLowProperties,
    AcousticBassProperties,
    SteelGuitarProperties,
    BrightPianoProperties,
    ClavinetProperties,
    ElectricGrandProperties,
    HonkyTonkProperties,
    UprightPianoProperties,
    RhodesProperties,
    WurlitzerProperties,
    MutedTrumpetProperties,
    TromboneProperties,
    HornProperties,
    brass_section,
    WoodPercussionProperties,
    SquareSynthProperties, MoogSawLead, MoogSquareLead, MoogCalliopeLead, MoogChiffLead,
    MoogCharangLead, MoogVoiceLead, MoogFifthsLead, MoogBassLead,
    MoogSynthBass1, MoogSynthBass2, MoogSynthBrass1, MoogSynthBrass2,
    MoogSynthStrings1, MoogSynthStrings2, MoogWarmPad, MoogPolysynthPad,
    MoogHaloPad, MoogSweepPad, MoogSoundtrackPad,
    MoogAtmosphereFX, MoogGoblinsFX, MoogSciFiFX,
    MoogBrightnessFX, MoogChoirPad, MoogBowedPad, MoogSynthVoice,
    MoogMetallicPad, MoogCrystalFX, MoogSynthDrum, MoogRainFX, MoogEchoesFX,
    MoogNewAgePad,
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
    TelephoneRingProperties,
    HelicopterProperties,
    BirdTweetProperties,
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
    FloorTomProperties,
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
PROGRAM_CLASS[1] = UprightPianoProperties  # the upright, measured: a small board's brightness
# ...and 3 (Honky-tonk) is the same piano with the tuner's hand off. The grand
# already models a unison as one string at pitch and two mistuned around it; a
# honky-tonk just widens that range from under 2 cents to 8-20.
PROGRAM_CLASS[3] = HonkyTonkProperties     # the upright, badly tuned
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
PROGRAM_CLASS[80] = MoogSquareLead               # Lead 1 (square): a Moog, moog.py
PROGRAM_CLASS[81] = MoogSawLead                  # Lead 2 (sawtooth): a Moog, moog.py
PROGRAM_CLASS[82] = MoogCalliopeLead             # Lead 3 (calliope): triangles
PROGRAM_CLASS[83] = MoogChiffLead                # Lead 4 (chiff): a breath on the front
PROGRAM_CLASS[84] = MoogCharangLead              # Lead 5 (charang): the ladder, then the valve
PROGRAM_CLASS[85] = MoogVoiceLead                # Lead 6 (voice): the ladder, then formants
PROGRAM_CLASS[86] = MoogFifthsLead               # Lead 7 (fifths): OSC 2 FREQ +7
PROGRAM_CLASS[87] = MoogBassLead                 # Lead 8 (bass+lead): OSC 2 at 16'
# TUNING_MOOG=0 puts the additive leads back -- not a setting to play through,
# the A/B that shows what the Moog is for, as TUNING_CABINET=0 is the amp's.
if __import__('os').environ.get('TUNING_MOOG', '1') == '0':
    PROGRAM_CLASS[80] = SquareSynthProperties
    PROGRAM_CLASS[81] = SawtoothSynthProperties
    PROGRAM_CLASS[82] = TriangleSynthProperties
    PROGRAM_CLASS[83] = ChiffLeadProperties
    PROGRAM_CLASS[84] = CharangLeadProperties
    PROGRAM_CLASS[85] = VoiceLeadProperties
    PROGRAM_CLASS[86] = FifthsLeadProperties
    PROGRAM_CLASS[87] = BassLeadProperties
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
# ...and its drones' notes, the first class each note names (the tenors share one)
DRONE_NOTES = {109: {}}
for _dn, _dc in BagpipeProperties.drone_classes:
    DRONE_NOTES[109].setdefault(_dn, _dc)
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
PROGRAM_CLASS[116] = TaikoProperties            # a big barrel drum, measured (VSCO-2 CE)
PROGRAM_CLASS[117] = TomTomProperties           # likewise, and pitched
PROGRAM_CLASS[114] = SteelPanProperties          # tuned 1:2:3, not a bar
# The two CATEGORY ERRORS in this family, both on the generic mallet base.
# 118 is an electronic drum -- an oscillator with a downward pitch sweep, which
# is tension_bend and needed nothing new. 119 is a cymbal played BACKWARDS,
# which needed the attack to be allowed past 45% of the note; see
# SynthProperties.attack_fraction_max.
PROGRAM_CLASS[118] = SynthDrumProperties        # an 808 tom, not a bar
PROGRAM_CLASS[119] = ReverseCymbalProperties    # the measured crash, reversed
# THE LAST THREE CATEGORY ERRORS, and all three turned out to be instruments.
# 124 is a bell struck twenty times a second -- the thing in the room, not the
# ringback tone the exchange sends the caller. 125 is the blade passing
# frequency, a sawtooth at about 16 Hz, which is the only voice here whose
# fundamental is below hearing. 123 is a nearly pure tone whose pitch sweeps,
# repeated, which is tension_bend used rising where the synth drum uses it
# falling. See tonelib for each.
PROGRAM_CLASS[123] = BirdTweetProperties        # a chirp, and then three more
PROGRAM_CLASS[124] = TelephoneRingProperties    # gongs and a clapper, not a tone
PROGRAM_CLASS[125] = HelicopterProperties       # a sawtooth four octaves down
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


# THE BANK'S BALANCE, BY PROGRAM: dB on a pitched note's channel volume,
# measured against GeneralUser GS (the nearest witness to Roland's GS set on
# this machine) by examples/sfx_levels.py --all --trim: each program and a
# piano C4 alone at velocity 64 and at 100, K-weighted, the loudest 150 ms; the
# two (GU - ours) differences averaged (Ben). Its own table, not the classes'
# initial_gain: a class can serve several programs, a drum kit's notes, or an
# organ's ranks, and the balance is the program's. KIT_TRIM_DB the same for
# the drum kit as a whole (its notes' balance among themselves is
# kit_levels.py's). Empty = each class's own level.
PROGRAM_TRIM_DB = {1: 8.2, 2: 1.9, 3: 9.6, 4: -2.0, 5: -5.3, 6: -10.9, 7: -2.8, 8: -1.4, 9: -2.1, 10: 8.8, 11: 2.3, 12: 2.9, 13: 1.5, 14: 1.8, 15: 3.6, 16: -7.3, 17: -2.8, 18: -6.2, 19: 1.8, 20: 6.8, 21: -10.0, 22: 0.0, 23: -1.2, 24: 9.8, 25: 0.8, 26: 7.3, 27: 5.8, 28: 14.9, 29: 10.5, 30: 6.7, 31: 13.2, 32: 4.2, 33: 3.6, 34: 3.5, 35: 7.5, 36: -2.2, 37: -4.6, 38: 3.5, 39: -3.5, 40: 8.0, 41: 3.1, 42: 7.3, 43: 9.0, 44: -0.8, 45: -15.5, 46: 4.3, 47: -2.0, 48: 2.1, 49: 6.4, 50: 6.4, 51: -0.2, 52: 4.1, 53: 4.3, 54: 0.6, 55: -12.0, 56: 3.4, 57: 3.1, 58: 3.2, 59: 13.6, 60: 7.3, 61: 3.5, 62: 8.3, 63: 9.1, 64: 5.1, 65: 4.7, 66: 6.8, 67: 2.7, 68: 8.0, 69: 4.1, 70: 5.3, 71: 4.8, 72: 10.6, 73: 8.3, 74: 6.5, 75: 8.3, 76: 8.2, 77: 8.7, 78: 11.6, 79: 12.3, 80: 4.4, 81: -0.5, 82: 8.0, 83: 7.1, 84: 0.8, 85: 3.8, 86: 3.7, 87: 5.3, 88: 10.5, 89: 3.6, 90: 7.5, 91: 3.3, 92: 2.9, 93: 5.4, 94: 4.5, 95: 3.1, 96: 2.1, 97: 5.5, 98: 3.9, 99: 6.2, 100: 5.3, 101: 3.9, 102: -1.2, 103: 3.6, 104: 15.9, 105: 10.8, 106: 1.6, 107: 11.1, 108: 13.1, 109: 4.8, 110: 9.7, 111: 5.5, 112: 18.4, 113: -14.8, 114: -7.7, 115: 1.1, 116: 3.5, 117: 3.7, 118: -4.1, 119: -9.7, 120: 32.8, 121: -8.4, 122: 4.0, 123: -11.0, 124: -25.8, 125: 9.8, 126: 11.6, 127: 11.0}
KIT_TRIM_DB = -1.7


# A SOUND CANVAS FILE'S BALANCE, on top of the bank's: the trims above match
# GeneralUser GS, but a GS file was balanced by ear against a Roland module,
# whose programs sit differently against each other. Only where that has
# been heard: Tokei (Konami, SC-88Pro) had every electric guitar 3-6 dB
# quiet -- the side and lead parts on their own valves as well as the EFX
# ones, so the program's level and not the effect -- and Ben chose +3 from
# +0/+3/+4.5/+6 on the whole mix (4.5 too much). Its electric bass under
# them the same +3 (Ben, by ear on the same mix), finger and pick. Every
# variation of the program with it. A GM file keeps GeneralUser's balance.
GS_TRIM_DB = {29: 3.0, 30: 3.0, 33: 3.0, 34: 3.0}
# ...and its drum kit: Tokei's kick, hats and snare quiet against the band
# (Ben: "the whole kit could be 3dB higher"), every kit, every key
GS_DRUM_TRIM_DB = 3.0


def program_trim(program, drum=False, gs=False):
    """The linear factor on a note's channel volume for its program -- or for
    its variation (VARIATION_TRIM_DB), where it has one -- and, in a file
    that speaks GS, GS_TRIM_DB's on top."""
    v = getattr(program, "variation", 0)
    if not drum and v and ((int(program) & 0x7F), v) in VARIATION_TRIM_DB:
        db = VARIATION_TRIM_DB[(int(program) & 0x7F, v)]
    else:
        db = KIT_TRIM_DB if drum else PROGRAM_TRIM_DB.get(int(program) & 0x7F, 0.0)
    if gs:
        db += GS_DRUM_TRIM_DB if drum else GS_TRIM_DB.get(int(program) & 0x7F, 0.0)
    return 10.0 ** (db / 20.0) if db else 1.0


class VariationProgram(int):
    """A program number in a BANK: GS's variation tones (CC0 = the variation,
    the SC-55's "Variation" table), carried as DrumProgram carries a drum set.
    An int, so everything that reads a note's program keeps working; the class
    lookups read `.variation` and take the variation's class where VARIATIONS
    has one. Made only for a variation that exists -- any other bank plays the
    capital tone, as a Sound Canvas does."""

    def __new__(cls, program, variation):
        o = int.__new__(cls, int(program))
        o.variation = int(variation)
        return o

    def __repr__(self):
        return "VariationProgram(%d, %d)" % (int(self), self.variation)


def property_class_for_program(program):
    """Return the property class for a 0-based GM program number -- its
    variation's, where it carries one (VariationProgram)."""
    v = getattr(program, "variation", 0)
    if v:
        got = VARIATIONS.get((int(program) & 0x7F, v))
        if got is not None:
            # a ROUTED variation (a function of the note): its middle register
            return got if isinstance(got, type) else got(60)
    return PROGRAM_CLASS.get(program & 0x7F, PluckedStringProperties)


# BANK VARIATIONS: {(program, variation): class}. EMPTY, and on purpose. The
# corpus selects none -- 39 of its 42 CC0 messages are 0 and the other three
# are XG's drum bank on channel 10 -- so a variation built now could not be
# heard in anything that asks for it. Each one goes here when a file or a
# player wants it, as a subclass of its capital program. Until then every
# variation falls back to the capital tone, which is what a Sound Canvas does
# with one it lacks.
VARIATIONS = {}
# ...each one's level against GeneralUser GS's own tone (dB, as
# PROGRAM_TRIM_DB); without one, its capital's trim
VARIATION_TRIM_DB = {}
# GS's names (SC-55 owner's manual p.68, the Variation table), 0-based
# programs: what the panel and the coverage table call a variation, built or
# not. Bank 127 is the CM-64/MT-32 map (p.69), not listed here.
VARIATION_NAMES = {
    (4, 8): "Detuned EP 1", (5, 8): "Detuned EP 2", (6, 8): "Coupled Hps.",
    (14, 8): "Church Bell", (16, 8): "Detuned Or. 1", (17, 8): "Detuned Or. 2",
    (19, 8): "Church Org. 2", (21, 8): "Accordion It", (24, 8): "Ukulele",
    (25, 8): "12-str. Gt", (25, 16): "Mandolin", (26, 8): "Hawaiian Gt.",
    (27, 8): "Chorus Gt.", (28, 8): "Funk Gt.", (30, 8): "Feedback Gt.",
    (31, 8): "Gt. Feedback", (38, 8): "Synth Bass 3", (39, 8): "Synth Bass 4",
    (48, 8): "Orchestra", (50, 8): "Syn. Strings3", (61, 8): "Brass 2",
    (62, 8): "Synth Brass3", (63, 8): "Synth Brass4", (107, 8): "Taisho Koto",
    (115, 8): "Castanets", (116, 8): "Concert BD", (117, 8): "Melo. Tom 2",
    (118, 8): "808 Tom",
    (120, 1): "Gt. Cut Noise", (120, 2): "String Slap", (121, 1): "Fl. Key Click",
    (122, 1): "Rain", (122, 2): "Thunder", (122, 3): "Wind", (122, 4): "Stream",
    (122, 5): "Bubble", (123, 1): "Dog", (123, 2): "Horse",
    (124, 1): "Telephone 2", (124, 2): "Door Creaking", (124, 3): "Door",
    (124, 4): "Scratch", (124, 5): "Windchime",
    (125, 1): "Car-Engine", (125, 2): "Car-Stop", (125, 3): "Car-Pass",
    (125, 4): "Car-Crash", (125, 5): "Siren", (125, 6): "Train", (125, 7): "Jetplane",
    (125, 8): "Starship", (125, 9): "Burst Noise",
    (126, 1): "Laughing", (126, 2): "Screaming", (126, 3): "Punch",
    (126, 4): "Heart Beat", (126, 5): "Footstep",
    (127, 1): "Machinegun", (127, 2): "Lasergun", (127, 3): "Explosion",
}


def variation_class(program, variation):
    """The class for `program` in bank `variation`, or the capital tone's."""
    return (VARIATIONS.get((program & 0x7F, variation))
            or property_class_for_program(program))


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
    # --- a melodic tom part is a set of toms, and under ~100 Hz the drum is a
    # FLOOR tom: DRSKit's sits at 81 Hz and rings ~2.5 s on its own modes (1 :
    # 1.631 : 2.012 ...), its rack tom at 122 Hz and under one second. Split
    # at G2, 98 Hz, the two drums' recorded pitches' geometric mean. There is
    # no smaller tom to measure, so the rack tom carries the rest.
    117: ((43, FloorTomProperties),
          (128, TomTomProperties)),
    # --- an agogo is TWO bells, and a melodic agogo part is played across
    # them: VSCO-2 CE's low bell rings at 696 Hz, its high one at 1228 (kit
    # notes 68 and 67, measured). Split at A#5, 932 Hz, near their geometric
    # mean (924).
    113: ((82, MelodicAgogoLowProperties),
          (128, MelodicAgogoHighProperties)),
}


def property_class_for_note(program, note):
    """The voice class for one NOTE of one program.

    Identical to property_class_for_program except where a program is really a
    FAMILY: the bowed and brass ensembles, which pick the instrument whose
    register the note is in, and the solo winds and brass whose bottom octave
    belongs to a bigger instrument entirely (SOLO_SPLIT).
    A VARIATION (VariationProgram) is its own class, ahead of every router.
    """
    if getattr(program, "layer", None) is not None:
        return layer_class(program, note)
    v = getattr(program, "variation", 0)
    if v and (int(program) & 0x7F, v) in VARIATIONS:
        got = VARIATIONS[(int(program) & 0x7F, v)]
        # a ROUTED variation is a function of the note (an ensemble's, whose
        # register picks the instrument): the variation wraps the router
        return got if isinstance(got, type) else got(note)
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
    # A BAGPIPE'S DRONES are notes of their own (tonelib BagpipeDroneProperties):
    # the notes they sound as are those voices, wherever they come from --
    # blockrender's drone notes, live's drone templates, or a drone an arranger
    # wrote into the part
    dn = DRONE_NOTES.get(prog)
    if dn and note in dn:
        return dn[note]
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

# THE SUBTRACTIVE BANK ON THE MOOG: the synth programs a two-oscillator synth
# through a ladder actually makes, as the leads (80-87) are. The additive
# classes above stay as their bases and as the A/B: TUNING_MOOG=0 keeps them.
# Only what no Moog makes stays additive: 88, a bell OVER a pad, two sounds in
# one note. Formants are not a reason -- a choir or a synth voice is the Moog
# sung through them, as GM 85 is; nor is metal, once FM makes it (93, 98); nor
# an echo, once Moog's own MF-104M delay makes it (96, 102: mf104.py). See
# tonelib, below the leads.
if __import__('os').environ.get('TUNING_MOOG', '1') != '0':
    PROGRAM_CLASS[38] = MoogSynthBass1           # saw over a 16' saw, low ladder
    PROGRAM_CLASS[39] = MoogSynthBass2           # square and SUB, resonant
    PROGRAM_CLASS[62] = MoogSynthBrass1          # the blat: a 60 ms filter attack
    PROGRAM_CLASS[63] = MoogSynthBrass2          # slower, darker, wider apart
    PROGRAM_CLASS[50] = MoogSynthStrings1        # two saws 7 c apart: no chorus
    PROGRAM_CLASS[51] = MoogSynthStrings2        # slower, darker, 11 c
    # GS's bank-8 variations of them (tonelib: starting panels, voiced on
    # Ben's Messenger)
    from tonelib import MoogSynthBass3, MoogSynthBass4, MoogSynthStrings3, \
        MoogSynthBrass3, MoogSynthBrass4
    VARIATIONS[(38, 8)] = MoogSynthBass3
    VARIATIONS[(39, 8)] = MoogSynthBass4
    VARIATIONS[(50, 8)] = MoogSynthStrings3
    VARIATIONS[(62, 8)] = MoogSynthBrass3
    VARIATIONS[(63, 8)] = MoogSynthBrass4
    # GS 124.1 "Telephone 2": the electronic tone ringer, a small synth
    from tonelib import MoogTelephone2
    VARIATIONS[(124, 1)] = MoogTelephone2
    # THE SC-88 MAP'S SYNTH TONES: each its capital's panel with what makes the
    # tone changed (sc88_synth.py), a panel to start from and edit
    import tonelib as _tl
    from sc88_synth import SC88_SYNTH
    for (_p, _b), (_nm, _base, _pan) in SC88_SYNTH.items():
        _B = getattr(_tl, _base)
        _pan = dict(_pan)
        # a panel's own class attributes, not knobs: the key's pan spread,
        # and the insertion effect the tone carries (a Juno's chorus)
        _cls_keys = ("key_pan_spread", "insertion_efx")
        _attrs = dict(messenger=dict(_B.messenger, **{k: v for k, v in _pan.items() if k not in _cls_keys}))
        for _k in _cls_keys:
            if _k in _pan:
                _attrs[_k] = _pan[_k]
        VARIATIONS[(_p, _b)] = type("Sc88_%d_%d" % (_p, _b), (_B,), _attrs)
        VARIATION_NAMES[(_p, _b)] = _nm
    from sc88_synth import SYNTH_TRIM_DB
    VARIATION_TRIM_DB.update(SYNTH_TRIM_DB)
    # ...and the other maps' own synth tones, under their map's key (map_bank)
    from sc88_synth import MAP_SYNTH
    for (_m, _p, _b), (_nm, _base, _pan) in MAP_SYNTH.items():
        _B = getattr(_tl, _base)
        VARIATIONS[(_p, 128 * _m + _b)] = type("Map%d_%d_%d" % (_m, _p, _b), (_B,),
                                               dict(messenger=dict(_B.messenger, **_pan)))
        VARIATION_NAMES[(_p, 128 * _m + _b)] = _nm
    PROGRAM_CLASS[89] = MoogWarmPad              # a low ladder, a slow swell
    PROGRAM_CLASS[90] = MoogPolysynthPad         # open, and a front to play on
    PROGRAM_CLASS[94] = MoogHaloPad              # squares, and NOISE for the air
    PROGRAM_CLASS[95] = MoogSweepPad             # LFO 1 on the cutoff: up AND down
    PROGRAM_CLASS[97] = MoogSoundtrackPad        # the longest swell, a slow drift
    PROGRAM_CLASS[99] = MoogAtmosphereFX         # a saw and the NOISE oscillator
    PROGRAM_CLASS[101] = MoogGoblinsFX           # two wobbles: the voice, and OSC 2
    PROGRAM_CLASS[103] = MoogSciFiFX             # PWM squares, a resonant contour
    PROGRAM_CLASS[100] = MoogBrightnessFX        # a hard front on an open ladder
    PROGRAM_CLASS[91] = MoogChoirPad             # the ladder, then the /O/ tract
    PROGRAM_CLASS[54] = MoogSynthVoice           # the ladder, then the sung tract
    PROGRAM_CLASS[92] = MoogBowedPad             # band pass, resonant, slow
    PROGRAM_CLASS[93] = MoogMetallicPad          # FM, carrier 2.06 x the key: beats
    PROGRAM_CLASS[98] = MoogCrystalFX            # FM bell, carrier 2 sqrt(2), anchored
    PROGRAM_CLASS[118] = MoogSynthDrum           # F ENV -> OSC 2 FREQ: the tom's sweep
    PROGRAM_CLASS[96] = MoogRainFX               # FM droplets through the MF-104M
    PROGRAM_CLASS[102] = MoogEchoesFX            # a saw pluck through the MF-104M
    PROGRAM_CLASS[88] = MoogNewAgePad            # LAYERED: a pad (A), an FM bell over it (B)

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


# THE SFX SET, PLAYED FROM THE KEYBOARD. GS's sound-effect variations (bank
# 1-8 under programs 120-127) are the SFX set's own sounds on a melodic part:
# the same tone, its key choosing the pitch, with C4 (key 60) at the pitch the
# kit plays it (SC-55 p.71's convention for the set's sounds). So each one is
# the kit key's fitted class with everything the kit gives it -- its ring, its
# level and its GS gate (percussion_map._with_ring) -- and its written note
# moved onto the kit's pitch by sounding_octaves, which both renderers apply
# to f0 before anything is built from it -- and then the whole sound moved
# with the key (transposed_from_hz). A held texture keeps sounding while held,
# as on the kit.
_MELODIC_SFX = {}


def melodic_sfx(key, kit=56):
    """The SFX set's key `key` as a melodic voice, C4 at its kit pitch."""
    import percussion_map as _PM
    from math import log2
    if (key, kit) not in _MELODIC_SFX:
        if key in _PM.KITS.get(kit, {}):
            name, cls, freq = _PM.KITS[kit][key]
            rc = _PM._with_ring(cls, key, kit)
        else:
            # Standard's own (and any set's note it takes from Standard)
            name, cls, freq = _PM.PERCUSSION[key]
            rc = _PM._with_ring(cls, key)
        so = float(getattr(rc, "sounding_octaves", 0.0))
        # ...AND TRANSPOSED WHOLE: built at the kit's pitch, every frequency it
        # emits -- its noise bands and grains, which are in Hz, with its
        # harmonics -- moved by the key's interval (blockrender's _XP), as GS
        # transposes the sample. Its gate and decays stay in seconds.
        # ...and its STROKES (percussion_map.rasp_strokes): the key whose
        # table they are, which blockrender expands a melodic note by
        attrs = {"sounding_octaves": so + log2(freq / SFX_C4_HZ),
                 "transposed_from_hz": freq * 2.0 ** so,
                 "sfx_strokes_of": (kit, key)}
        _MELODIC_SFX[(key, kit)] = type("%s_sfx%d" % (cls.__name__, key), (rc,), attrs)
    return _MELODIC_SFX[(key, kit)]


SFX_C4_HZ = 440.0 * 2.0 ** (-9 / 12.0)      # key 60 at A440 equal temperament

# GS bank on program -> the SFX set's key (SC-55 p.68 against p.71)
SFX_VARIATIONS = {
    (120, 1): 48, (120, 2): 50,                                  # Gt Cut Noise, String Slap
    (121, 1): 51,                                                # Fl.KeyClick
    (122, 1): 79, (122, 2): 80, (122, 3): 81, (122, 4): 83,      # Rain, Thunder, Wind, Stream
    (124, 2): 59, (124, 3): 60, (124, 4): 61, (124, 5): 62,      # DoorCreaking, Door, Scratch, Windchime
    (125, 1): 63, (125, 2): 64, (125, 3): 65, (125, 4): 66,      # Car-Engine, Car-Stop, Car-Pass, Car-Crash
    (125, 6): 68, (125, 7): 69, (125, 8): 71,                    # Train, Jetplane, Starship
    (126, 2): 53, (126, 3): 54, (126, 4): 55,                    # Screaming, Punch, Heart Beat
    (127, 2): 74, (127, 3): 75,                                  # Lasergun, Explosion
    # ...and those played as STROKES (percussion_map.KIT_STROKES): a pattern,
    # a voice's pulses, a train, a cascade -- expanded for a melodic note too
    (122, 5): 84,                                                # Bubble
    (123, 1): 76, (123, 2): 77,                                  # Dog, Horse-Gallop
    (123, 4): 85, (123, 5): 87,                                  # Kitty, Growl (past the set: the SC-88's keys)
    (126, 1): 52, (126, 5): 56,                                  # Laughing, Footstep
    (127, 1): 73,                                                # Machinegun
}
for _pv, _k in SFX_VARIATIONS.items():
    VARIATIONS[_pv] = melodic_sfx(_k)
    # ...AT THE KIT'S LEVEL: the class is levelled as the SFX set's key, and
    # its program's trim was set for that program's own voice (120's fret
    # noise +34 dB over the kit's, 124's telephone -25)
    VARIATION_TRIM_DB.setdefault(_pv, KIT_TRIM_DB)


def _morse_tone():
    """GS 125.10 "Calculating" (SC-88 Pro and SC-8850 maps, among the machines
    after the Starship): the Morse keyboard (percussion_map.MORSE_KIT) played
    from the keys -- each note its own character, at its own pitch."""
    import percussion_map as _PM
    base = melodic_sfx(60, kit=_PM.MORSE_KIT)
    return type("RfxMorseKeyboard", (base,), {"sfx_strokes_of": (_PM.MORSE_KIT, None)})


VARIATIONS[(125, 10)] = _morse_tone()
VARIATION_TRIM_DB.setdefault((125, 10), KIT_TRIM_DB)


# GS BANK 127: THE MT-32 SET (SC-55 p.69) -- the MT-32's 128 tones on the
# GS programs, for files written for one (a Sound Canvas in its MT-32 map).
# Each its nearest voice here: a GM program (its router and all, at that
# program's own level), or for a drum the MT-32 played from the keyboard,
# the fitted kit key (melodic_sfx, set 0). Synth tones the MT-32 made its own
# (Fantasy, Doctor Solo, Bellsinger) take the GM synth program nearest in
# kind. (mt32mux still maps an MT-32 FILE by its track names: this is for a
# file that selects bank 127 itself.)
MT32_SET = (
    ("Acou Piano 1", 0), ("Acou Piano 2", 1), ("Acou Piano 3", 1), ("Elec Piano 1", 4),
    ("Elec Piano 2", 5), ("Elec Piano 3", 4), ("Elec Piano 4", 5), ("Honkytonk", 3),
    ("Elec Org 1", 16), ("Elec Org 2", 17), ("Elec Org 3", 18), ("Elec Org 4", 16),
    ("Pipe Org 1", 19), ("Pipe Org 2", 19), ("Pipe Org 3", 20), ("Accordion", 21),
    ("Harpsi 1", 6), ("Harpsi 2", 6), ("Harpsi 3", 6), ("Clavi 1", 7),
    ("Clavi 2", 7), ("Clavi 3", 7), ("Celesta 1", 8), ("Celesta 2", 8),
    ("Syn Brass 1", 62), ("Syn Brass 2", 63), ("Syn Brass 3", 62), ("Syn Brass 4", 63),
    ("Syn Bass 1", 38), ("Syn Bass 2", 39), ("Syn Bass 3", 38), ("Syn Bass 4", 39),
    ("Fantasy", 88), ("Harmo Pan", 89), ("Chorale", 52), ("Glasses", 98),
    ("Soundtrack", 97), ("Atmosphere", 99), ("Warm Bell", 14), ("Funny Vox", 54),
    ("Echo Bell", 102), ("Ice Rain", 96), ("Oboe 2001", 68), ("Echo Pan", 75),
    ("Doctor Solo", 81), ("School Daze", 14), ("Bellsinger", 85), ("Square Wave", 80),
    ("Str Sect 1", 48), ("Str Sect 2", 48), ("Str Sect 3", 49), ("Pizzicato", 45),
    ("Violin 1", 40), ("Violin 2", 40), ("Cello 1", 42), ("Cello 2", 42),
    ("Contrabass", 43), ("Harp 1", 46), ("Harp 2", 46), ("Guitar 1", 24),
    ("Guitar 2", 25), ("Elec Gtr 1", 26), ("Elec Gtr 2", 27), ("Sitar", 104),
    ("Acou Bass 1", 32), ("Acou Bass 2", 32), ("Elec Bass 1", 33), ("Elec Bass 2", 34),
    ("Slap Bass 1", 36), ("Slap Bass 2", 37), ("Fretless 1", 35), ("Fretless 2", 35),
    ("Flute 1", 73), ("Flute 2", 73), ("Piccolo 1", 72), ("Piccolo 2", 72),
    ("Recorder", 74), ("Pan Pipes", 75), ("Sax 1", 64), ("Sax 2", 65),
    ("Sax 3", 66), ("Sax 4", 67), ("Clarinet 1", 71), ("Clarinet 2", 71),
    ("Oboe", 68), ("Engl Horn", 69), ("Bassoon", 70), ("Harmonica", 22),
    ("Trumpet 1", 56), ("Trumpet 2", 56), ("Trombone 1", 57), ("Trombone 2", 57),
    ("Fr Horn 1", 60), ("Fr Horn 2", 60), ("Tuba", 58), ("Brs Sect 1", 61),
    ("Brs Sect 2", 61), ("Vibe 1", 11), ("Vibe 2", 11), ("Syn Mallet", 12),
    ("Windbell", 112), ("Glock", 9), ("Tube Bell", 14), ("Xylophone", 13),
    ("Marimba", 12), ("Koto", 107), ("Sho", 20), ("Shakuhachi", 77),
    ("Whistle 1", 78), ("Whistle 2", 78), ("Bottleblow", 76), ("Breathpipe", 76),
    ("Timpani", 47), ("Melodic Tom", 117), ("Deep Snare", ("kit", 38)), ("Elec Perc 1", 118),
    ("Elec Perc 2", 118), ("Taiko", 116), ("Taiko Rim", 116), ("Cymbal", ("kit", 49)),
    ("Castanets", ("kit", 85)), ("Triangle", ("kit", 81)), ("Orche Hit", 55), ("Telephone", 124),
    ("Bird Tweet", 123), ("One Note Jam", 28), ("Water Bell", 98), ("Jungle Tune", 108),
)
assert len(MT32_SET) == 128


def aliased_variation(program):
    """VARIATIONS entry: another program's voice, note by note (its router)."""
    def pick(note, _p=program):
        return property_class_for_note(_p, note)
    return pick


for _i, (_nm, _to) in enumerate(MT32_SET):
    VARIATION_NAMES[(_i, 127)] = _nm
    if isinstance(_to, tuple):
        VARIATIONS[(_i, 127)] = melodic_sfx(_to[1], kit=0)
        VARIATION_TRIM_DB[(_i, 127)] = KIT_TRIM_DB
    else:
        VARIATIONS[(_i, 127)] = aliased_variation(_to)
        VARIATION_TRIM_DB[(_i, 127)] = PROGRAM_TRIM_DB.get(_to, 0.0)

# GS 125.9 "Burst Noise": a hiss and low bursts, fitted to GeneralUser's own
# (tonelib.SfxBurstNoiseProperties); at the SFX set's level until levelled
from tonelib import SfxBurstNoiseProperties as _SBN
VARIATIONS[(125, 9)] = _SBN
VARIATION_TRIM_DB.setdefault((125, 9), KIT_TRIM_DB)

# GS 125.5 "Siren": Helmholtz's double siren (tonelib.HelmholtzSirenProperties,
# siren.py) -- the key's pitch the 12-rows' at full air, the rows its stops.
# At the SFX set's level until levelled against GeneralUser's own.
from tonelib import HelmholtzSirenProperties as _HSP
VARIATIONS[(125, 5)] = _HSP
VARIATION_TRIM_DB.setdefault((125, 5), KIT_TRIM_DB)

# GS 19.8 "Church Org. 2": the church organ's principal chorus to the fourth
# harmonic, 8' 4' 2 2/3' 2' (tonelib.ChurchOrgan2Properties); its level the
# capital's trim, the extra ranks' own loudness on top, as on the instrument
from tonelib import ChurchOrgan2Properties as _CO2
VARIATIONS[(19, 8)] = _CO2

# GS 6.8 "Coupled Hps.": the harpsichord's 8' and 4' (tonelib.CoupledHarpsichordProperties)
from tonelib import CoupledHarpsichordProperties as _CHP
VARIATIONS[(6, 8)] = _CHP

# GS 21.8 "Accordion It": the musette, M- M M+ (tonelib.AccordionItalianProperties)
from tonelib import AccordionItalianProperties as _AIP
VARIATIONS[(21, 8)] = _AIP

# GS 4.8 / 5.8 / 16.8 / 17.8: the program's own voice as a detuned pair
# (tonelib.Detuned*Properties, chorus._pair)
from tonelib import (DetunedEP1Properties as _DE1, DetunedEP2Properties as _DE2,
                     DetunedOrgan1Properties as _DO1, DetunedOrgan2Properties as _DO2)
VARIATIONS[(4, 8)] = _DE1
VARIATIONS[(5, 8)] = _DE2
VARIATIONS[(16, 8)] = _DO1
VARIATIONS[(17, 8)] = _DO2

# GS 27.8 / 28.8: the Strat through a chorus pedal; the Strat on position 4,
# clean (tonelib.ChorusGuitarProperties, FunkGuitarProperties)
from tonelib import ChorusGuitarProperties as _CGP, FunkGuitarProperties as _FGP
VARIATIONS[(27, 8)] = _CGP
VARIATIONS[(28, 8)] = _FGP

# GS 115.8 / 116.8 / 117.8 / 118.8: kit voices played from the keyboard, as the
# SFX variations are (melodic_sfx: the kit's ring, gate, level and strokes,
# C4 at its kit pitch, transposed whole) -- a tom set's MIDDLE tom, as a
# sampler maps one tom across the keys
for _pv, (_k, _kit) in {(115, 8): (85, 0),       # Castanets (Standard)
                        (116, 8): (36, 48),      # Concert BD 1 (Orchestra set)
                        (117, 8): (47, 24),      # Elec Mid Tom 1: the Simmons (Electronic set)
                        (118, 8): (47, 25),      # 808 Mid Tom 1 (808 set)
                        }.items():
    VARIATIONS[_pv] = melodic_sfx(_k, _kit)
    VARIATION_TRIM_DB.setdefault(_pv, KIT_TRIM_DB)

# A VARIATION OF A ROUTED PROGRAM keeps the routing: the entry is a function of
# the note, each register's class with the variation's attributes on it
_ROUTED_CLASSES = {}


def routed_variation(program, name, **attrs):
    """VARIATIONS entry: program's own router, each class it picks given attrs."""
    def pick(note, _p=program, _n=name, _a=attrs):
        base = property_class_for_note(_p, note)
        k = (base, _n)
        if k not in _ROUTED_CLASSES:
            _ROUTED_CLASSES[k] = type("%s_%s" % (base.__name__, _n), (base,), dict(_a))
        return _ROUTED_CLASSES[k]
    return pick


# GS 61.8 "Brass 2": the brass section's own router, every register a detuned
# pair (chorus._pair), +-4 cents half left and right -- MuseScore's 61.8, its
# section twice, +-4, panned apart: the brass made wider
VARIATIONS[(61, 8)] = routed_variation(61, "brass2", detuned_pair=(-4.0, 4.0))

# A LAYERED VARIATION: one key, two (or more) voices -- each routed by its
# own program at its own transposition and level. blockrender expands such a
# note into one event per layer before anything else sees it (so live's
# templates, built through it, carry every layer), each event's program a
# LayerProgram naming its layer. {(program, variation): ((routing program,
# semitones, dB), ...)}; a routing program may be ("kit", key, set), a kit's
# key, or ("set", program, {attrs}), a program's voice with settings (layer_class)
LAYERED = {}


class LayerProgram(int):
    """The program (its int value, for every channel-level lookup) of one
    LAYER of a layered variation."""
    def __new__(cls, program, variation, layer):
        o = int.__new__(cls, int(program)); o.variation = int(variation); o.layer = int(layer)
        return o

    def __repr__(self):
        return "LayerProgram(%d, %d, %d)" % (int(self), self.variation, self.layer)


_LAYER_CLASSES = {}


def layer_class(program, note):
    """The class of one layer of a layered variation at (its own) note."""
    spec = LAYERED[(int(program) & 0x7F, program.variation)][program.layer]
    # a layer is a program's voice, ("kit", key, set): a kit's key played from
    # the keyboard (melodic_sfx), C4 at its kit pitch, ("set", program,
    # {attrs}): the program's voice with those settings, as a "set" tone, or
    # ("class", cls): a voice class itself
    src, attrs = spec[0], {}
    if isinstance(src, tuple) and src[0] == "set":
        src, attrs = src[1], dict(src[2])
    # ...or ("class", cls): a voice no program routes to (St.Gamelan's gangsa pair)
    if isinstance(src, tuple) and src[0] == "class":
        base = src[1]
    else:
        base = (melodic_sfx(src[1], kit=src[2]) if isinstance(src, tuple)
                else property_class_for_note(src, note))
    db = float(spec[2])
    if not db and not attrs:
        return base
    k = (base, db, tuple(sorted(attrs.items())))
    if k not in _LAYER_CLASSES:
        _LAYER_CLASSES[k] = type("%s_layer%+g" % (base.__name__, db), (base,),
                                 dict(attrs, initial_gain=base.initial_gain * 10.0 ** (db / 20.0)))
    return _LAYER_CLASSES[k]


def layers_of(program):
    """((LayerProgram, semitones), ...) for a layered variation, else None."""
    v = getattr(program, "variation", 0)
    spec = LAYERED.get((int(program) & 0x7F, v)) if v and getattr(program, "layer", None) is None else None
    if not spec:
        return None
    # (a spec's optional 4th and 5th fields: the velocities it sounds at)
    return tuple((LayerProgram(program, v, i), int(s[1]),
                  int(s[3]) if len(s) > 3 else 0, int(s[4]) if len(s) > 4 else 127)
                 for i, s in enumerate(spec))


# GS 48.8 "Orchestra": the strings, and a brass section an octave above them,
# softer -- what both GM sets build (GeneralUser's and MuseScore's 48.8 are
# their strings with their brass section 8va layered over them). Each layer
# its own router: the bowed section by register, the brass by its.
LAYERED[(48, 8)] = ((48, 0, 0.0), (61, 12, -10.0))
VARIATIONS[(48, 8)] = routed_variation(48, "orchestra")

# GS 14.8 "Church Bell": a church bell, measured (tonelib.ChurchBellProperties)
from tonelib import ChurchBellProperties as _CBP
VARIATIONS[(14, 8)] = _CBP

# GS 26.8 "Hawaiian Gt.": the lap steel (tonelib.HawaiianGuitarProperties)
from tonelib import HawaiianGuitarProperties as _HGP
VARIATIONS[(26, 8)] = _HGP

# GS 25.8 "12-str. Gt": the steel-string's courses doubled (tonelib.TwelveStringProperties)
from tonelib import TwelveStringProperties as _TSP
VARIATIONS[(25, 8)] = _TSP

# GS 30.8 "Feedback Gt.", 31.8 "Gt. Feedback": a guitar held into feedback
# (tonelib.Feedback): the distortion guitar blooming, the clean loop itself
from tonelib import FeedbackGuitarProperties as _FGP, GuitarFeedbackProperties as _GFP
VARIATIONS[(30, 8)] = _FGP
VARIATIONS[(31, 8)] = _GFP

# GS 24.8 "Ukulele": Ben's own, recorded for it (tonelib.UkuleleProperties)
from tonelib import UkuleleProperties as _UKP
VARIATIONS[(24, 8)] = _UKP

# GS 107.8 "Taisho Koto": a course of a string and three an octave over it
from tonelib import TaishoKotoProperties as _TKP
VARIATIONS[(107, 8)] = _TKP
# ...and its drone string, alone on a bank of its own (the fit renders it there;
# blockrender's struck drone plays it through the class)
from tonelib import TaishoDroneProperties as _TDP
VARIATIONS[(107, 9)] = _TDP

# GS 25.16 "Mandolin": unison courses of steel strings (tonelib.MandolinProperties)
from tonelib import MandolinProperties as _MDP
VARIATIONS[(25, 16)] = _MDP


# THE SC-88 MAP'S CHEAP TONES (Roland's SC-88Pro owner's manual, its
# instrument list; examples/gs_maps.py, gs_inventory.md): the ones that are
# one of our voices under another number, or a setting of one -- wide (the
# keys across the stereo field), dark, an octave or a second voice layered, a
# velocity switch, a drum reversed, an organ's registration. Each at its
# capital's level (or its own voice's), until levelled against GeneralUser's.
#   ("alias", program)            that program's voice, note by note
#   ("var", (program, bank))      that variation's voice
#   ("kit", key, set)             the set's key played from the keyboard
#   ("rev", key, set)             ...and played backwards (the reverse cymbal's)
#   ("set", program, {attrs})     the program's voice with these settings
#   ("layer", ((program, semitones, dB[, vel lo, vel hi]), ...))
WIDE = 0.5                       # key_pan_spread: +-0.5 of the field 30 keys from middle C


def palm_mute(s):
    """GM 30's strings under a palm mute of strength s: 0 its own, 1 GM 28's
    fitted mute (IDMT-SMT-Guitar, a clean DI guitar) -- decay rates taken
    geometrically between the two, the pick and the palm's low-pass linearly.
    A driven chug's length also depends on how hard the palm rests, which is
    the player's: examples/rock_rhythm_ab.py renders a part at any s."""
    from tonelib import DistortionGuitarProperties as _D, MutedGuitarProperties as _M
    out = {}
    for k in ('decay_db', 'harmonic_decay_db', 'decay_register_slope', 'strike_depth',
              'tonal_dampening'):
        a, b = float(getattr(_D, k)), float(getattr(_M, k))
        v = a * (b / a) ** s if k in ('decay_db', 'harmonic_decay_db') else a + s * (b - a)
        out[k] = float('%.4g' % v)
    return out


SC88_CHEAP = {
    (0, 8): ("Piano 1w", ("set", 0, dict(key_pan_spread=WIDE))),
    # "d": A SOFTER, WORN HAMMER (Ben: "the hammer is beaten up... the attack
    # starts darker due to the hammer difference"), not a duller piano: the
    # felt's contact low-pass at 0.6x -- fewer upper partials excited at the
    # strike, every string then ringing by its own law
    (0, 16): ("Piano 1d", ("set", 0, dict(hammer_corner_hz=0.6 * 3542.03))),
    (1, 8): ("Piano 2w", ("set", 1, dict(key_pan_spread=WIDE))),
    (2, 1): ("EG+Rhodes 1", ("layer", ((2, 0, 0.0), (4, 0, -6.0)))),
    (2, 2): ("EG+Rhodes 2", ("layer", ((2, 0, -3.0), (4, 0, 0.0)))),
    (2, 8): ("Piano 3w", ("set", 2, dict(key_pan_spread=WIDE))),
    (3, 8): ("Old Upright", ("alias", 1)),
    (4, 16): ("FM+SA EP", ("layer", ((4, 0, 0.0), (5, 0, -4.0)))),
    (4, 24): ("60'sE.Piano", ("alias", 5)),
    (5, 16): ("St.FM EP", ("set", 5, dict(key_pan_spread=WIDE))),
    (6, 16): ("Harpsi.w", ("set", 6, dict(key_pan_spread=WIDE))),
    (6, 24): ("Harpsi.o", ("layer", ((6, 0, 0.0), (6, 12, -6.0)))),
    (11, 8): ("Vib.w", ("set", 11, dict(key_pan_spread=WIDE))),
    (12, 8): ("Marimba w", ("set", 12, dict(key_pan_spread=WIDE))),
    (14, 9): ("Carillon", ("var", (14, 8))),
    (15, 1): ("Santur 2", ("set", 15, dict(detuned_pair=(-6.0, 6.0)))),
    (16, 1): ("Organ 101", ("set", 16, dict(default_stops=0b101101))),          # 16' 8' 4' 2'
    (16, 9): ("Organ 109", ("set", 16, dict(default_stops=0b111100))),          # 8' 4' 2 2/3' 2'
    (16, 16): ("60'sOrgan 1", ("set", 16, dict(default_stops=0b100001100))),    # 8' 4' 1'
    (16, 17): ("60'sOrgan 2", ("set", 16, dict(default_stops=0b100101100))),    # 8' 4' 2' 1'
    (16, 18): ("60'sOrgan 3", ("set", 16, dict(default_stops=0b111111100))),    # 8' and every one over it
    (16, 32): ("Organ 4", ("set", 16, dict(default_stops=0b111111111))),        # all nine
    (16, 33): ("Even Bar", ("set", 16, dict(default_stops=0b100101101))),       # the even ones: 16' 8' 4' 2' 1'
    (16, 40): ("Organ Bass", ("set", 16, dict(default_stops=0b101))),           # 16' 8'
    (17, 1): ("Organ 201", ("set", 17, dict(default_stops=0b1000000000111))),   # 888, the B3's 2nd percussion
    (17, 32): ("Organ 5", ("set", 17, dict(default_stops=0b100100000111))),     # 888 and 1', 3rd percussion
    # Rotary Org. is the switchable one -- Roland has RotaryOrg.S and .F for
    # the fixed speeds -- so it starts slow and the wheel (CC1) takes it fast
    (18, 8): ("Rotary Org.", ("set", 18, dict(default_stops=0b111111111, leslie_fast=False))),
    (18, 16): ("RotaryOrg.S", ("set", 18, dict(leslie_fast=False))),
    (18, 24): ("RotaryOrg.F", ("set", 18, dict(leslie_fast=True, default_stops=0b111111111))),
    (19, 16): ("ChurchOrg.3", ("set", 19, dict(default_stops=0b10010011))),     # 8' 4' 16' mixture
    (19, 24): ("Organ Flute", ("set", 19, dict(default_stops=(1 << 6) | (1 << 14)))),                # flute 8' 4'
    (19, 32): ("Trem.Flute", ("set", 19, dict(default_stops=(1 << 6) | (1 << 14) | (1 << 13)))),    # ...tremulant
    (24, 16): ("Nylon Gt.o", ("layer", ((24, 0, 0.0), (24, 12, -6.0)))),
    (24, 24): ("VeloHarmnix", ("layer", ((24, 0, 0.0, 0, 95), (31, 0, 0.0, 96, 127)))),
    (25, 9): ("Nylon+Steel", ("layer", ((24, 0, -2.0), (25, 0, -2.0)))),
    (31, 16): ("Ac.Gt.Harm.", ("alias", 31)),
    # THE SC-88Pro's ":" TONES ARE LEGATO-ENABLED (owner's manual, "Concerning
    # legato-enabled sounds"): a note played over a held one sounds without
    # its attack. Ours slur what overlaps on every voice that declares a
    # legato attack (blockrender's legato pass, tonelib.slur_attack), so where
    # the colon is the only difference the tone is the voice as it is
    (72, 1): ("Piccolo :", ("alias", 72)),
    # ...and the strings' two, legato as ours are: Bright Str: the body's
    # roll-off opened (bore_corner_hz 3 -> 4.5 kHz: a colour, power-
    # preserving); ChamberStr: a chamber orchestra's section, fewer players
    # (2 voices against 7, a narrower desk) -- each chosen by Ben on Tokei's
    # strings (examples/tone_ab.py; 3, 4.5, 6 kHz; 7, 3, 2 players)
    (48, 1): ("Bright Str:", ("set", 48, dict(bore_corner_hz=4500.0))),
    (48, 2): ("ChamberStr:", ("set", 48, dict(section_players=2, section_width_m=0.8))),
    # SOLO SPIC.: one violin, its bow thrown onto the string and off it -- a
    # quick bite (12 ms, no bowed speech), 40 ms on the string whatever the
    # key holds (one_shot, gate_time), then the string's brief ring (0.12 s:
    # a stopped high note, damped by the finger) -- chosen by Ben on Tokei's
    # clock tick (F#6 every half second) in its hall, over 50 ms / 0.18 s
    (45, 16): ("Solo Spic.", ("set", 40, dict(section_players=1, one_shot=True, gate_time=0.04,
                                              release_valve_time=0.12, attack_time=0.012,
                                              speech_cycles=0.0))),
    # PICKED BASS 2: the picked bass with its amp pushed into a mild growl --
    # Roland gives only its 2 voices; read by Ben as the driven one, the Ozzy
    # rhythm section's (Bob Daisley's picked bass under Crazy Train's guitars),
    # drive 1.0 chosen on Tokei's bass (0.28 its own, 1.0, 2.0)
    (34, 1): ("Picked Bass2", ("set", 34, dict(amp_drive=1.0))),
    # DIST. GT2 : the distortion guitar, legato-enabled -- a guitar's legato
    # is the fretting hand: a note over a held one is hammered or pulled off,
    # its string ringing on from the last pick (blockrender hammer_legato),
    # and the note it leaves stops (one string, one pitch)
    (30, 1): ("Dist. Gt2 :", ("set", 30, dict(hammer_legato=True, slur_cuts_release=True))),
    # MORE DRIVE: GM 29's own voice. Tokei plays it through GTR Multi 2's
    # overdrive at 30 (x1.72 on the valve, gsefx.od_gain), and that product
    # Ben heard as right -- Crazy Train's crunch, a little less smashed; a
    # hotter voice under the same EFX would be more smashed than that
    (29, 3): ("More Drive", ("alias", 29)),
    # ROCK RHYTHM: the distortion guitar palm-muted, at 0.3 of GM 28's mute --
    # a distorted palm-muted open G (Freesound 12042, CC0) swells 150 ms and
    # sags ~11 dB/s, a light palm (0.2-0.35); Ben chose 0.3 by ear on Tokei's
    # rhythm part (0, 0.3, 1 rendered by examples/rock_rhythm_ab.py)
    (30, 24): ("Rock Rhythm", ("set", 30, palm_mute(0.3))),
    # ROCK RHYTHM 2: the same guitar under GM 28's whole fitted palm mute (1.0)
    # -- Ben chose it from 0, 0.3, 0.6 and 1 on Tokei's three Rock Rhythm 2
    # parts (tracks 21, 30, 31 at 3:28; examples/tone_ab.py)
    (30, 25): ("Rock Rhythm2", ("set", 30, palm_mute(1.0))),
    # MUTED DIS.GT: the distortion guitar under the whole palm mute -- Rock
    # Rhythm2's tone, as Ben chose it (SENSATIO, 2)
    (28, 1): ("Muted Dis.Gt", ("var", (30, 25))),
    # BRASS FALL: the brass section, its notes falling off -- held 0.15 s,
    # then a run down the valved lattice, 9 semitones over 0.45 s, half-valved,
    # fading 30 dB (tonelib fall_cents; a gliss down, not a sweep -- Ben):
    # within the 0.6 s Sorcerian holds its one chord (Sorcerian, 3)
    (61, 16): ("Brass Fall", ("set", 61, dict(fall_cents=900.0))),
    # BIG SHOT: the gunshot made bigger -- its noise held twice as long and its
    # slower tail louder and longer (-6 dB at 60 dB/s -> -3 dB at 30) (storm_pro, 2)
    (127, 5): ("Big Shot", ("set", 127, dict(strike_noise_len_s=2.0, strike_noise_tail=(-3.0, 30.0)))),
    # --- THE SC-88 MAP'S SETTINGS, the rest of them (not in our GS files):
    # each a reading of its name on the voice it is a setting of, through
    # the voice's own physical controls -- tonal_dampening (how fast the top
    # dies: down is harder, brighter), the valve's drive, the attack (x4 at
    # +1), a mute's decay, layers -- for Ben's ear, as tier 2's were
    # (the fitted electric pianos' brightness is the tine's swing past the
    # pickup, pickup_deflection; a vibraphone's its bar's mode levels, which a
    # harder mallet lifts: tonal_dampening moves neither)
    (4, 25): ("Hard Rhodes", ("set", 4, dict(pickup_deflection=1.12))),
    (4, 26): ("MellwRhodes", ("set", 4, dict(pickup_deflection=0.45))),
    (5, 24): ("Hard FM EP", ("set", 5, dict(pickup_deflection=1.46))),
    (11, 1): ("Hard Vibe", ("set", 11, dict(bar_modes=((1, 1.0), (4, 0.75), (10, 0.25))))),
    # the concert cimbalom: a bigger dulcimer, longer ringing, harder hammers
    (15, 8): ("Cimbalom", ("set", 15, dict(decay_db=4.5, tonal_dampening=0.65))),
    (22, 1): ("Harmonica 2", ("set", 22, dict(reed_edge=0.0128))),
    (24, 32): ("Nylon Gt.2", ("set", 24, dict(tonal_dampening=0.8))),
    # the requinto: a small, higher guitar -- brighter, shorter ringing
    (24, 40): ("Lequint Gt.", ("set", 24, dict(tonal_dampening=0.75, decay_db=7.0))),
    (25, 32): ("Steel Gt.2", ("set", 25, dict(tonal_dampening=0.6))),
    (26, 1): ("Mellow Gt.", ("set", 26, dict(tonal_dampening=2.6))),
    (28, 16): ("Funk Gt.2", ("var", (28, 8))),
    # dazed: the distortion guitar wobbling against itself, a detuned pair
    (30, 2): ("DazedGuitar", ("set", 30, dict(detuned_pair=(-12.0, 12.0)))),
    (30, 9): ("FeedbackGt2", ("var", (30, 8))),
    (30, 16): ("PowerGuitar", ("set", 30, dict(amp_drive=28.9))),
    (30, 17): ("Power Gt.2", ("layer", ((30, 0, 0.0), (30, -12, -6.0)))),
    (30, 18): ("5th Dist.", ("layer", ((30, 0, 0.0), (30, 7, -2.0)))),
    (33, 1): ("FingeredBs2", ("set", 33, dict(tonal_dampening=2.9))),
    # a Jazz bass on its bridge pickup alone: brighter, its own comb
    (33, 2): ("Jazz Bass", ("set", 33, dict(pickup_points=(0.098,), tonal_dampening=2.0))),
    (34, 8): ("MutePickBs.", ("set", 34, dict(decay_db=20.0, tonal_dampening=2.4))),
    # Mr. Smooth: the soul fretless Ben heard in Fretless Bs2
    (35, 5): ("Mr.Smooth", ("set", 35, dict(lowpass_hz=455.7, lowpass_order=3.605, tonal_dampening=2.315))),
    (36, 8): ("Reso Slap", ("set", 36, dict(tonal_dampening=1.4))),
    (40, 8): ("Slow Violin", ("set", 40, dict(sound_bias={"attack": 1.0}))),
    (44, 8): ("SlowTremolo", ("set", 44, dict(sound_bias={"attack": 1.0}))),
    # suspense: tremolo bowed near the bridge, sul ponticello -- glassy, bright
    (44, 9): ("SuspenseStr", ("set", 44, dict(tonal_dampening=0.9))),
    # tremolo orchestra: Orchestra's layering (48.8) on the tremolo strings
    (48, 10): ("TremoloOrch", ("layer", ((44, 0, 0.0), (61, 12, -10.0)))),
    (49, 8): ("Legato Str.", ("set", 48, dict(sound_bias={"attack": 0.5}))),
    (52, 32): ("ChoirAahs 2", ("set", 52, dict(section_players=12))),
    # Philly: a soul string stab with the hit -- strings one-shot, gated
    # 150 ms, 3 dB under the hit at their own trim
    (55, 9): ("Philly Hit", ("layer", ((55, 0, 0.0),
                                        (("set", 48, dict(one_shot=True, gate_time=0.15)), 0, 11.1)))),
    (105, 1): ("Muted Banjo", ("set", 105, dict(decay_db=30.0, tonal_dampening=1.2))),
    # Tsugaru: the shamisen's heavier school, a thicker neck struck harder
    (106, 1): ("Tsugaru", ("set", 106, dict(tonal_dampening=0.35, decay_db=3.0))),
    (111, 1): ("Shanai 2", ("set", 111, dict(sound_bias={"vib_depth": 0.5}))),
    # cheese organ: a thin combo organ, 8' 4' 2' 1 3/5' 1'
    (16, 24): ("CheeseOrgan", ("set", 16, dict(default_stops=0b101101100))),
    (48, 9): ("Orchestra 2", ("layer", ((48, 0, 0.0), (60, 0, -8.0)))),
    # IMPACT HIT: the orchestra hit made heavier -- our timpani two octaves
    # under it and the Orchestra set's Concert BD 1, 18 semitones down (the hits
    # sit E4-B5, so the drum near its own pitch at C4) -- no Impact Hit in any GM
    # set here to fit; voiced for Ben's ear: "needs bass drum, too", the
    # timpani "could be louder" (-6 -> 0 dB); and on top a BRASS STAB -- the
    # brass section struck sforzando and let go, one-shot, gated to 120 ms, at
    # the hit's own pitch (D5-B5), -3 dB ("the piccolo is not a hit. It
    # sustains"). EACH AT ITS OWN TRIM: a layered tone's notes all take the
    # capital's (55's -12 dB), so each layer's dB carries its own trim less
    # that -- the timpani's -2 (+10), the kit's -1.7 (+10.3), the brass
    # section's +3.5 (+15.5); written as 0 dB they sat 10-16 dB under the
    # hit, "didn't really hear much timpani" (Sorcerian, 87)
    (55, 8): ("Impact Hit", ("layer", ((55, 0, 0.0), (47, -24, 10.0), (("kit", 36, 48), -18, 10.3),
                                       (("set", 61, dict(one_shot=True, gate_time=0.12)), 0, 12.5)))),
    # BAM HIT: the hit made PUNCHY where Impact Hit is heavy -- the brass stab
    # at the hit's own level and the Concert BD under it, no timpani boom; each
    # at its own trim as Impact Hit's (the hits sit G5-A5: the drum 20 down to
    # its pitch at C4) (SENSATIO, 32)
    (55, 19): ("Bam Hit", ("layer", ((55, 0, 0.0), (("kit", 36, 48), -20, 10.3),
                                     (("set", 61, dict(one_shot=True, gate_time=0.12)), 0, 15.5)))),
    (48, 11): ("Choir Str.", ("layer", ((48, 0, 0.0), (52, 0, -4.0)))),
    (48, 16): ("St.Strings", ("set", 48, dict(key_pan_spread=WIDE))),
    (48, 24): ("VeloStrings", ("layer", ((49, 0, 0.0, 0, 90), (48, 0, 0.0, 91, 127)))),
    (49, 10): ("St.SlowStr.", ("set", 49, dict(key_pan_spread=WIDE))),
    (52, 8): ("St.Choir", ("set", 52, dict(key_pan_spread=WIDE))),
    (55, 10): ("Double Hit", ("layer", ((55, 0, 0.0), (55, 12, -6.0)))),
    (60, 16): ("Horn Orch", ("set", 60, dict(detuned_pair=(-5.0, 5.0)))),
    (62, 16): ("OctaveBrass", ("layer", ((62, 0, 0.0), (62, 12, -6.0)))),
    (63, 16): ("VeloBrass 1", ("layer", ((63, 0, 0.0, 0, 90), (62, 0, 0.0, 91, 127)))),
    (63, 17): ("VeloBrass 2", ("layer", ((63, 0, 0.0, 0, 90), (61, 0, 0.0, 91, 127)))),
    (98, 3): ("Round Glock", ("alias", 9)),
    (98, 5): ("GlocknChime", ("layer", ((9, 0, 0.0), (14, 0, -6.0)))),
    (98, 18): ("Bell Harp", ("layer", ((46, 0, 0.0), (9, 12, -8.0)))),
    (98, 19): ("Gamelimba", ("layer", ((108, 0, 0.0), (98, 0, -6.0)))),
    (99, 2): ("Nylon Harp", ("layer", ((24, 0, -2.0), (46, 0, -3.0)))),
    (99, 3): ("Harpvox", ("layer", ((46, 0, 0.0), (54, 0, -6.0)))),
    (99, 5): ("NylonRhodes", ("layer", ((24, 0, -2.0), (4, 0, -3.0)))),
    (102, 3): ("Echo Pan 2", ("set", 102, dict(key_pan_spread=WIDE))),
    (102, 4): ("Big Panner", ("set", 102, dict(key_pan_spread=0.8))),
    (102, 5): ("Reso Panner", ("set", 102, dict(key_pan_spread=0.8, sound_bias={"resonance": 0.5}))),
    (104, 1): ("Sitar 2", ("set", 104, dict(tonal_dampening=0.4125))),                     # brighter: less rolloff
    (104, 2): ("DetuneSitar", ("set", 104, dict(detuned_pair=(-8.0, 8.0)))),
    (117, 1): ("Real Tom", ("kit", 45, 0)),
    (117, 9): ("Rock Tom", ("kit", 45, 16)),
    (118, 9): ("Elec Perc", ("kit", 45, 24)),
    (119, 1): ("ReverseCym2", ("rev", 57, 0)),
    (119, 8): ("Rev.Snare 1", ("rev", 38, 0)),
    (119, 9): ("Rev.Snare 2", ("rev", 40, 0)),
    (119, 16): ("Rev.Kick 1", ("rev", 36, 0)),
    (119, 17): ("Rev.ConBD", ("rev", 36, 48)),
    (119, 24): ("Rev.Tom 1", ("rev", 45, 0)),
    (119, 25): ("Rev.Tom 2", ("rev", 48, 0)),
    (120, 3): ("Gt.CutNz. 2", ("var", (120, 1))),
    (120, 4): ("Dist.CutNz.", ("var", (120, 1))),
    (120, 6): ("Pick Scrape", ("alias", 120)),
    # BASS SLIDE: GM 120's fingertip on a BASS string. The squeak is hand speed
    # over winding pitch (tonelib.GuitarFretNoiseProperties), and a round-wound
    # bass's outer wrap is ~0.6 mm to a guitar's ~0.35: the band down by that,
    # 1700 -> 990 Hz, and its floor, 650 -> 380. No recording found (rated 2)
    (120, 5): ("Bass Slide", ("set", 120, dict(formants=((990.0, 1170.0, 1.0),), bore_corner_hz=2040.0,
                                               bell_cutoff_hz=380.0))),
    (123, 3): ("Bird 2", ("kit", 78, 56)),
    (124, 7): ("Scratch 2", ("var", (124, 4))),
    (126, 6): ("Applause 2", ("kit", 58, 56)),
    # --- THE SC-88Pro MAP'S SETTINGS OF OUR VOICES THAT OUR GS FILES PLAY
    # (examples/gs_maps.py; the notes each file gives the tone in brackets) --
    # DANCE PIANO: the bright piano with a harder hammer, across the field
    # (sysex_01, 912)
    (1, 16): ("Dance Piano", ("set", 1, dict(hammer_corner_hz=1.6 * 189.3, key_pan_spread=WIDE))),
    # SLOW STRINGS 2: the slow section's bow slower still, and darker for it
    # -- its registers' attack 1.1 -> 1.8 s, their dampening 1.75-1.85 -> 2.1
    # (SENSATIO, 454)
    (49, 1): ("SlowStrings2", ("set", 49, dict(attack_time=1.8, tonal_dampening=2.1))),
    # WARM STRINGS: the slow section with the body's roll-off lower, 3 -> 2.2
    # kHz (River 9, SENSATIO 20)
    (49, 9): ("Warm Strings", ("set", 49, dict(bore_corner_hz=2200.0))),
    # MELTED / MELLO CHOIR: the choir darker, its upper partials damped faster
    # (tonal_dampening 1.45 -> 1.9; its bore corner lowered read BRIGHTER, the
    # colour being power-preserving) (River, 48)
    (52, 9): ("Melted Choir", ("set", 52, dict(tonal_dampening=1.9))),
    # CHORUS LAHS: a pop backing group's "lah" -- four singers, not seven, and
    # the syllable's quicker onset (SENSATIO, 903)
    (52, 24): ("Chorus Lahs", ("set", 52, dict(section_players=4, chiff_min_valve_time=0.025,
                                               chiff_max_valve_time=0.05))),
    # VOICE DAHS: the oohs' voices on /a/ (vowels.VOWELS), the plosive's quick
    # onset (SuwaFF, 169)
    (53, 8): ("Voice Dahs", ("set", 53, dict(formants=__import__("vowels").VOWELS["a"],
                                             chiff_min_valve_time=0.015, chiff_max_valve_time=0.03))),
    # WIDE FRENCH HORNS: the horns across the field (sysex_01, 140)
    (60, 3): ("Wide FreHrns", ("set", 60, dict(key_pan_spread=WIDE))),
    # FLUTE 2 : the flute, legato-enabled (the colon, as Piccolo :) (SENSATIO, 4)
    (73, 1): ("Flute 2 :", ("alias", 73)),
    # JC CLEAN GT.: the clean guitar through Roland's JC-120 -- a clean
    # solid-state amplifier (no valve: amp_drive 0) and its closed-back 2x12
    # (cabinet.JazzChorus212); the chorus is the Sound Canvas's own send
    # (storm_pro, 3557, through its Distortion)
    (27, 4): ("JC Clean Gt.", ("set", 27, dict(amp_drive=0.0, cabinet="jc120"))),
    # FRETLESS BS2: ANOTHER FRETLESS -- GM 35's top refitted to mrforfs' (CC0,
    # sources.md): a Harley Benton five-string, flatwounds, direct, both
    # pickups (examples/egtr_fit.py's envelope on fretless_open_both, 5 open
    # strings: miss 4.59 -> 1.94 dB): darker than FaireDesVagues' Jazz, the
    # low-pass 645 -> 456 Hz. Ben, on SENSATIO's three parts: "like what is
    # used in soul music" (SENSATIO, 1055)
    (35, 1): ("Fretless Bs2", ("set", 35, dict(lowpass_hz=455.7, lowpass_order=3.605,
                                               tonal_dampening=2.315))),
    # FRETLESSBS3, FRETLESSBS4: THE SAME BASS ON ONE COIL -- mrforfs' neck and
    # bridge takes (examples/fretless_pickup_fit.py: the low harmonics and the
    # top together). Neck: the coil at 0.189, rounder (ladder 10.3 -> 7.2,
    # envelope 3.2 -> 2.7 dB against Bs2's top); bridge: at 0.073, a wider
    # coil, the fundamental down and h5-h7 up (9.4 -> 5.1, 2.2 -> 1.5). One
    # coil reads less than two: trimmed to GM 35's level (+5.8, +9.5 dB)
    (35, 2): ("FretlessBs3", ("set", 35, dict(pickup_points=(0.1893,), pickup_width=0.006505,
                                              tonal_dampening=2.556, lowpass_hz=462.4,
                                              lowpass_order=3.224))),
    (35, 3): ("FretlessBs4", ("set", 35, dict(pickup_points=(0.07274,), pickup_width=0.03394,
                                              tonal_dampening=2.309, lowpass_hz=735.6,
                                              lowpass_order=3.673))),
    # FLT TRAVELSO: THE TRAVERSO, the baroque wooden flute -- GM 73 refitted as
    # a difference, Alex Murray's late-1700s Goulding flute (Bach's Sarabande,
    # BWV 1013; Commons, CC BY-SA 2.0; sources.md) against the Iowa takes GM 73
    # is fitted to, frame by frame where the pitch holds (examples/
    # traverso_fit.py: miss 17.3 -> 4.35 dB): far purer, h2 some 20 dB under
    # the modern flute's at D4. The bore corner under the lowest note is a
    # slope, not a roll-off. Ben, on its part: sounds great (sysex_01, 274)
    # THE BRASS'S DYNAMICS: Iowa's pp, ff and vibrato runs against the mf
    # takes GM's voices are fitted to, each note against itself
    # (examples/brass_dyn_fit.py): above a knee the dynamic's change runs in
    # dB per kHz to a cap (tonelib, blare_db_per_khz). Bright Tp. takes the
    # trombone's ff law: Iowa's trumpet ff is its mf (+0.3 dB, +0.6 dB/kHz)
    (56, 1): ("Trumpet 2", ("set", 56, dict(blare_db_per_khz=-0.9, blare_knee_hz=192, blare_cap_db=15.2,
                                           exp_vibrato_cents=5.4, solo_vibrato_hz=4.83))),
    (56, 24): ("Bright Tp.", ("set", 56, dict(blare_db_per_khz=7.7, blare_knee_hz=754, blare_cap_db=25.9))),
    (56, 25): ("Warm Tp.", ("set", 56, dict(blare_db_per_khz=-6.6, blare_knee_hz=160, blare_cap_db=34.8))),
    (57, 1): ("Trombone 2", ("set", 57, dict(blare_db_per_khz=7.7, blare_knee_hz=754, blare_cap_db=25.9))),
    (58, 1): ("Tuba 2", ("set", 58, dict(blare_db_per_khz=30.1, blare_knee_hz=116, blare_cap_db=24.7))),
    (60, 1): ("Fr.Horn 2", ("set", 60, dict(blare_db_per_khz=-14.0, blare_knee_hz=162, blare_cap_db=10.3))),
    (60, 8): ("Fr.HornSolo", ("set", 60, dict(blare_db_per_khz=9.9, blare_knee_hz=588, blare_cap_db=29.1))),
    (73, 3): ("Flt Travelso", ("set", 73, dict(tonal_dampening=1.513, bore_corner_hz=104.3,
                                               even_harmonic_db=-8.253))),
}
_SC88_DONE = {}


def _sc88_class(how, tag):
    kind = how[0]
    if kind == "alias":
        return aliased_variation(how[1]), PROGRAM_TRIM_DB.get(how[1], 0.0)
    if kind == "var":
        return VARIATIONS[how[1]], VARIATION_TRIM_DB.get(how[1], PROGRAM_TRIM_DB.get(how[1][0], 0.0))
    if kind in ("kit", "rev"):
        c = melodic_sfx(how[1], kit=how[2])
        if kind == "rev":
            # PLAYED BACKWARDS as the reverse cymbal is (blockrender: each
            # partial's decay a growth, arriving on the note-off)
            c = type("%s_rev" % c.__name__, (c,), dict(played_backwards=True, one_shot=False,
                                                     held_texture=False))
        return c, KIT_TRIM_DB
    if kind == "set":
        return routed_variation(how[1], tag, **how[2]), PROGRAM_TRIM_DB.get(how[1], 0.0)
    raise ValueError(kind)


import tonelib as _TL
# THE SC-8850 MAP'S SETTINGS, the GM 2 sound set's (patch_map.gm2_bank finds a
# GM 2 tone by name, and these are the SC-8850's own, in slots no earlier map
# used): each a reading of its name on the voice it is a setting of, through
# the voice's own physical controls, as SC88_CHEAP's are -- for Ben's ear
SC8850_CHEAP = {
    # the harmonium pumped breathily: its reeds' breath noise up 8 dB
    (20, 16): ("Puff Organ", ("set", 20, dict(breath_noise_db=tuple(
        (h, d + 8.0) for h, d in _TL.ReedOrganFreeProperties.breath_noise_db)))),
    # the steel-string's body sounding more: its resonances half again
    (25, 33): ("Steel + Body", ("set", 25, dict(body_trim_db=tuple(
        (h, 1.5 * d) for h, d in _TL.SteelGuitarProperties.body_trim_db)))),
    # the Strat's middle pickup, ~100 mm from the bridge (the neck's 160)
    (27, 23): ("Mid Tone GTR", ("set", 27, dict(pickup_points=(0.155,)))),
    # a jazz guitar's comping, the hand half on the strings
    (28, 24): ("Jazz Man", ("set", 26, palm_mute(0.5))),
    # a pinch harmonic: the thumb catching the string, its harmonic two
    # octaves up squealing over the note
    (29, 4): ("Guitar Pinch", ("layer", ((29, 0, -6.0), (29, 24, -3.0)))),
    # the rhythm guitar between Rock Rhythm's light palm (0.3) and Rock
    # Rhythm 2's whole mute
    (30, 26): ("Dist Rtm GTR", ("set", 30, palm_mute(0.6))),
    # fingered, with the slap's thumb under it
    (33, 7): ("Finger Slap", ("layer", ((33, 0, 0.0), (36, 0, -6.0)))),
    # a 1960s pop session's strings: fewer players, close and bright
    (48, 40): ("60s Strings", ("set", 48, dict(section_players=4, section_width_m=1.2,
                                               bore_corner_hz=4500.0))),
    # darker than Warm Tp. (-6.6 dB per kHz): -10 dB per kHz from 160 Hz
    (56, 3): ("Dark Trumpet", ("set", 56, dict(blare_db_per_khz=-10.0, blare_knee_hz=160,
                                               blare_cap_db=34.8))),
    # the trombone's ff law, as Trombone 2's
    (57, 4): ("Bright Tb", ("var", (57, 1))),
    # THE PLUNGER: the open trumpet with a rubber cup over its bell, the hand
    # on the channel's aftertouch -- sealed at rest, pressure opening it, the
    # doo-wah (efxfilter.plunger). GM 59 is the harmon, stem out (measured);
    # Ben's choice of mute and control for the second
    (59, 2): ("MuteTrumpet2", ("set", 56, dict(plunger=True))),
    # GM 2's last (2026-10-26). Roland's "Legend" is a vintage Rhodes -- ours,
    # fitted to one (GM 4); and the same through the module's PHASER, which the
    # tone carries (insertion_efx: gsefx.tone_state) where a file sets none
    (5, 10): ("EP Legend", ("set", 4, {})),
    (5, 32): ("EP Phase", ("set", 4, dict(insertion_efx=((0x01, 0x20), {})))),
    # the hit's ranks (OrchestraHitProperties.stop_ranks: bass 0, tenor 1,
    # horn 2, string 3, tpt 4, wind 5, picc 6): the low ones alone; the bright
    # ones alone (the Eurodance stab); and a SIXTH chord -- the hit is a root
    # and fifth, so itself a major sixth up adds the sixth and the third
    (55, 1): ("Bass Hit", ("set", 55, dict(default_stops=0b0001011))),
    (55, 2): ("6th Hit", ("layer", ((55, 0, 0.0), (55, 9, -3.0)))),
    (55, 3): ("Euro Hit", ("set", 55, dict(default_stops=0b1011100))),
    # the Chinese hammered dulcimer: ours (Kemp's, fitted), struck nearer the
    # bridge with bamboo beaters -- brighter, its brass strings ringing longer
    (46, 24): ("Yang Qin", ("set", 15, dict(strike_point=1.0 / 8, tonal_dampening=0.6))),
    # the choir humming, lips closed: a nasal murmur -- one low formant, the
    # mouth's others nearly gone, the closure's low-pass
    (53, 40): ("Humming", ("set", 53, dict(formants=((250.0, 120.0, 1.0), (2200.0, 300.0, 0.06),
                                                     (2700.0, 400.0, 0.04)), bore_corner_hz=1500.0))),
    # a saw lead through the module's stereo delay, which the tone carries
    (87, 7): ("Delayed Lead", ("set", 81, dict(insertion_efx=((0x01, 0x50), {})))),
}

for _cheap, _tag in ((SC88_CHEAP, "sc88"), (SC8850_CHEAP, "sc8850")):
    for (_p, _b), (_nm, _how) in _cheap.items():
        VARIATION_NAMES[(_p, _b)] = _nm
        if _how[0] == "layer":
            LAYERED[(_p, _b)] = _how[1]
            VARIATIONS[(_p, _b)] = routed_variation(_how[1][0][0], "%s_%d_%d" % (_tag, _p, _b))
        else:
            VARIATIONS[(_p, _b)], _tr = _sc88_class(_how, "%s_%d_%d" % (_tag, _p, _b))
            VARIATION_TRIM_DB.setdefault((_p, _b), _tr)

# BIWA STROKE: the satsuma biwa (tonelib.BiwaProperties), fitted to Hugh de
# Ferranti's (PARADISEC HDF1-SB33; CC BY-NC-SA 4.0 data: sources.md) -- at the
# shamisen's trim, the instrument it starts from, not GM 120's fret noise
from tonelib import BiwaProperties
VARIATIONS[(120, 12)] = BiwaProperties
VARIATION_NAMES[(120, 12)] = "Biwa Stroke"
VARIATION_TRIM_DB[(120, 12)] = PROGRAM_TRIM_DB.get(106, 0.0)

# PHONO NOISE: a record's crackle and hiss as a voice (tonelib.PhonoNoiseProperties),
# at the applause's trim, whose machinery it is
from tonelib import PhonoNoiseProperties
VARIATIONS[(124, 10)] = PhonoNoiseProperties
VARIATION_NAMES[(124, 10)] = "Phono Noise"
VARIATION_TRIM_DB[(124, 10)] = PROGRAM_TRIM_DB.get(126, 0.0)

# KANOON: the kanun (tonelib.KanunProperties), fitted to Baris Bozkurt's
# isolated notes (Freesound 211133, CC0) -- at the koto's trim, the zither it
# starts from
from tonelib import KanunProperties
VARIATIONS[(107, 16)] = KanunProperties
VARIATION_NAMES[(107, 16)] = "Kanoon"
VARIATION_TRIM_DB[(107, 16)] = PROGRAM_TRIM_DB.get(107, 0.0)

# RAMA CYMBAL: the Balinese ceng-ceng (tonelib.CengCengProperties), fitted to
# the UNT gamelan's open strikes (Freesound pack 12954, CC0), at the kit's trim
from tonelib import CengCengProperties
VARIATIONS[(112, 16)] = CengCengProperties
VARIATION_NAMES[(112, 16)] = "RAMA Cymbal"
VARIATION_TRIM_DB[(112, 16)] = KIT_TRIM_DB

# THE MELLOTRON (tonelib.MellotronMixin): a program's own router, each class
# it picks on tape -- the run-out, no touch, each key's own tuning, one
# capstan's wow -- with the tape's colour as settings
def mellotron_variation(program, name, **attrs):
    import tonelib as _T

    def pick(note, _p=program, _n=name, _a=attrs):
        base = property_class_for_note(_p, note)
        k = (base, _n)
        if k not in _ROUTED_CLASSES:
            _ROUTED_CLASSES[k] = type("%s_%s" % (base.__name__, _n), (_T.MellotronMixin, base), dict(_a))
        return _ROUTED_CLASSES[k]
    return pick


# THE TAPE'S COLOUR, fitted on menegass' Mellotron violins (Freesound 6815,
# CC0; examples/mellotron_fit.py, 12 notes C4-B4: miss 4.98 -> 2.08 dB):
# brighter than our violins to ~5 kHz -- their body's resonance 2.3 -> 3.5
# kHz, its floor gone -- then cut steeply, a low-pass at 2.6 kHz, order 6.4,
# the copies of copies the tapes were
TAPE_CUT = dict(lowpass_hz=2635.0, lowpass_order=6.392)
# TRON STRINGS: the "3 Violins" tape -- the string section, three players, the
# violins' body and the tape's cut (sysex_01, 4352)
VARIATIONS[(50, 24)] = mellotron_variation(48, "tron", section_players=3, formant_floor=0.005,
                                          formants=((3475.0, 1671.0, 0.55),), **TAPE_CUT)
VARIATION_NAMES[(50, 24)] = "Tron Strings"
# ...at its capital's level (the synth strings, GM 50): three players and the
# tape's cut came out 6.5 dB under it (examples/variation_demo.py)
VARIATION_TRIM_DB[(50, 24)] = PROGRAM_TRIM_DB.get(48, 0.0) + 6.5
# TRON FLUTE: the flute tape -- our flute under the tape's cut (its own notes in
# that pack too short to fit: 0.135 s) (sysex_01, 274)
VARIATIONS[(73, 16)] = mellotron_variation(73, "tron", **TAPE_CUT)
VARIATION_NAMES[(73, 16)] = "Tron Flute"
VARIATION_TRIM_DB[(73, 16)] = PROGRAM_TRIM_DB.get(73, 0.0)

# ALTOSAX EXP. (the SC-88's "Hyper Alto"): the alto played out, fitted as a
# difference from GM 65 to Iowa's vibrato ff takes (tonelib.AltoSaxExpProperties,
# examples/sax_exp_fit.py) -- its own vibrato, the ladder a little brighter
from tonelib import AltoSaxExpProperties
VARIATIONS[(65, 8)] = AltoSaxExpProperties
VARIATION_NAMES[(65, 8)] = "AltoSax Exp."

# BS CLARINET: the bass clarinet over its whole compass (tonelib.BassClarinetProperties,
# Iowa's mf runs; its effort law from the pp and ff, examples/bsclar_fit.py) --
# under GM 71 it plays only the notes below D3
VARIATIONS[(71, 8)] = BassClarinetProperties
VARIATION_NAMES[(71, 8)] = "Bs Clarinet"
# GENDER: the gamelan's metallophone, fitted to UNT's Balinese gangsa
# (tonelib.GenderProperties, examples/gender_fit.py; cpolcyn's pack, CC0) --
# at the celesta's trim, the bar whose gain it starts from
from tonelib import GenderProperties
VARIATIONS[(112, 9)] = GenderProperties
VARIATION_NAMES[(112, 9)] = "Gender"
VARIATION_TRIM_DB[(112, 9)] = PROGRAM_TRIM_DB.get(8, 0.0)

# GAMELAN GONG: the gong ageng, fitted to the same gamelan's big gong
# (tonelib.GamelanGongProperties, examples/gender_fit.py --gong)
from tonelib import GamelanGongProperties
VARIATIONS[(112, 10)] = GamelanGongProperties
VARIATION_NAMES[(112, 10)] = "GamelanGong"
VARIATION_TRIM_DB[(112, 10)] = PROGRAM_TRIM_DB.get(8, 0.0)

# OUD: the Arabic lute (tonelib.OudProperties, examples/pluck_fit.py --voice=oud)
from tonelib import OudProperties
VARIATIONS[(105, 24)] = OudProperties
VARIATION_NAMES[(105, 24)] = "Oud"
VARIATION_TRIM_DB[(105, 24)] = PROGRAM_TRIM_DB.get(24, 0.0)

# LOG DRUM: a slit drum, fitted to VSCO 2's (CC0; tonelib.LogDrumProperties,
# examples/logdrum_fit.py)
from tonelib import LogDrumProperties
VARIATIONS[(12, 24)] = LogDrumProperties
VARIATION_NAMES[(12, 24)] = "Log Drum"
VARIATION_TRIM_DB[(12, 24)] = PROGRAM_TRIM_DB.get(12, 0.0)

# RABAB: the Afghan rubab on the banjo's drumhead (tonelib.RababProperties,
# examples/rabab_fit.py)
from tonelib import RababProperties
VARIATIONS[(105, 8)] = RababProperties
VARIATION_NAMES[(105, 8)] = "Rabab"
VARIATION_TRIM_DB[(105, 8)] = PROGRAM_TRIM_DB.get(105, 0.0)

# GOPICHANT: the ektara, its scoop (tonelib.GopichantProperties,
# examples/pluck_fit.py --voice=gopichant)
from tonelib import GopichantProperties
VARIATIONS[(105, 16)] = GopichantProperties
VARIATION_NAMES[(105, 16)] = "Gopichant"
VARIATION_TRIM_DB[(105, 16)] = PROGRAM_TRIM_DB.get(105, 0.0)

# FLUGEL HORN: the trumpet's source on a conical bore (tonelib.FlugelhornProperties,
# examples/flugel_fit.py)
from tonelib import FlugelhornProperties
VARIATIONS[(56, 8)] = FlugelhornProperties
VARIATION_NAMES[(56, 8)] = "Flugel Horn"
VARIATION_TRIM_DB[(56, 8)] = PROGRAM_TRIM_DB.get(56, 0.0)

# KAWALA: an end-blown cane flute, fitted to its family (the kaval, the ney;
# tonelib.KawalaProperties, examples/wind_fit.py --voice=kawala)
from tonelib import KawalaProperties
VARIATIONS[(75, 8)] = KawalaProperties
VARIATION_NAMES[(75, 8)] = "Kawala"
VARIATION_TRIM_DB[(75, 8)] = PROGRAM_TRIM_DB.get(75, 0.0)

# ATARIGANE: the festival hand gong, an educated guess on the bonang's measured
# bronze (tonelib.AtariganeProperties)
from tonelib import AtariganeProperties
VARIATIONS[(113, 8)] = AtariganeProperties
VARIATION_NAMES[(113, 8)] = "Atarigane"
VARIATION_TRIM_DB[(113, 8)] = PROGRAM_TRIM_DB.get(113, 0.0)

# TAMBOURA: the tanpura, fitted to sankalp's drone takes (CC BY 4.0;
# tonelib.TambouraProperties, examples/tanpura_fit.py)
from tonelib import TambouraProperties
VARIATIONS[(104, 16)] = TambouraProperties
VARIATION_NAMES[(104, 16)] = "Tamboura"
VARIATION_TRIM_DB[(104, 16)] = PROGRAM_TRIM_DB.get(104, 0.0)

# TAMBRA: the same tanpura with its jawari set another way, fitted to its
# other take (tonelib.TambraProperties, examples/tanpura_fit.py --take=1)
from tonelib import TambraProperties
VARIATIONS[(104, 8)] = TambraProperties
VARIATION_NAMES[(104, 8)] = "Tambra"
VARIATION_TRIM_DB[(104, 8)] = PROGRAM_TRIM_DB.get(104, 0.0)

# PUNGI: the snake charmer's pipe, fitted to a Bhaktapur street (CC BY 2.5;
# tonelib.PungiProperties, examples/pungi_fit.py)
from tonelib import PungiProperties
VARIATIONS[(111, 8)] = PungiProperties
VARIATION_NAMES[(111, 8)] = "Pungi"
VARIATION_TRIM_DB[(111, 8)] = PROGRAM_TRIM_DB.get(111, 0.0)
# ...and its drone pipe, alone on a bank of its own (live builds the drone's
# templates there, as the taishogoto's drone string; 111.9 is no SC-88 tone)
from tonelib import PungiDroneProperties
VARIATIONS[(111, 9)] = PungiDroneProperties

# HICHIRIKI: gagaku's double reed, fitted to gaijinbuzz's shrine take (CC0;
# tonelib.HichirikiProperties, examples/wind_fit.py --voice=hichiriki)
from tonelib import HichirikiProperties
VARIATIONS[(111, 16)] = HichirikiProperties
VARIATION_NAMES[(111, 16)] = "Hichiriki"
VARIATION_TRIM_DB[(111, 16)] = PROGRAM_TRIM_DB.get(111, 0.0)

# BARAFON: the balafon, fitted to marini24's (CC BY 4.0; tonelib.BalafonProperties,
# examples/balafon_fit.py) -- at its capital's level, the marimba's (the
# celesta's trim, whose gain it starts from, left its short bars 23 dB under)
from tonelib import BalafonProperties
VARIATIONS[(12, 16)] = BalafonProperties
VARIATION_NAMES[(12, 16)] = "Barafon"
VARIATION_TRIM_DB[(12, 16)] = PROGRAM_TRIM_DB.get(8, 0.0) + 23.2
# BARAFON 2: the same balafon played softer, and drier (tonelib.BalafonSoftProperties)
from tonelib import BalafonSoftProperties
VARIATIONS[(12, 17)] = BalafonSoftProperties
VARIATION_NAMES[(12, 17)] = "Barafon 2"
VARIATION_TRIM_DB[(12, 17)] = PROGRAM_TRIM_DB.get(8, 0.0) + 23.2

# BONANG: the Javanese kettle gongs, fitted to Casa da Musica's (CC BY 3.0;
# tonelib.BonangProperties, examples/gender_fit.py --bonang)
from tonelib import BonangProperties
VARIATIONS[(112, 8)] = BonangProperties
VARIATION_NAMES[(112, 8)] = "Bonang"
VARIATION_TRIM_DB[(112, 8)] = PROGRAM_TRIM_DB.get(8, 0.0)

# ST.GAMELAN: the gamelan in stereo -- the Balinese gangsa as it is played, a
# PAIR beating 26 cents apart, its two instruments left and right
# (tonelib.GangsaPairProperties), and the bonang an octave over it, softer,
# as the panerus doubles the melody
from tonelib import GangsaPairProperties
LAYERED[(112, 11)] = ((("class", GangsaPairProperties), 0, 0.0), (("class", BonangProperties), 12, -6.0))
VARIATIONS[(112, 11)] = GangsaPairProperties
VARIATION_NAMES[(112, 11)] = "St.Gamelan"
VARIATION_TRIM_DB[(112, 11)] = PROGRAM_TRIM_DB.get(8, 0.0)

# BREATHYTNR.: the tenor played airy -- fitted on GM 66 to cemorse100's "soft,
# airy" C5 (CC0; examples/breathy_fit.py): the ladder darker (h2 -18 dB where
# ours is -8; miss 9.8 -> 2.3 dB) and the air through the reed, a breath table
# through the renderer (1.45 dB by band; 635 Hz is the fundamental's skirt and
# does not move); and under it the wet reed's CRACKLE (tonelib.ReedCrackleProperties)
# ...and it SPEAKS SOFTLY (Ben: "The breath itself should probably fade in"):
# the take's tone 18 dB under its level at the start, -8 at 50 ms, there by
# ~100 ms; its breath 8 dB under at once and creeping up over ~0.4 s. A SLUR
# speaks at once (Ben: "might want to have different logic for legato"): the
# tone takes the sax's legato attack (slur_attack, 12 ms) and so does the
# breath (breath_noise_slur) -- the air never stopped. ITS BREATH IS A LOW
# REGISTER'S: 5 dB more an octave down from the take's C5, 5 less up -- assumed
# (Ben's -5; rockwehrmann's CC0 alto subtones are all at its bottom, D-flat3-D3,
# 6-12 dB breathier than the same horn straight, and no airy sax was found
# recorded at more than one register)
BREATHY_TENOR = dict(attack_time=0.12, breath_noise_fade_s=0.1, breath_noise_slur=True,
                     breath_noise_octave_db=-5.0, breath_noise_ref_hz=528.2,
                     tonal_dampening=2.047, formant_floor=0.999, breath_noise_db=(
    (160, -13.0), (202, -13.0), (255, -13.0), (321, -13.0), (400, -13.0), (504, -38.0), (635, -58.9),
    (800, 27.4), (1008, 30.2), (1270, 33.4), (1600, 32.9), (2016, 40.3), (2540, 38.3), (3200, 29.8),
    (4032, 28.0), (5080, 24.4), (6400, 13.2), (8063, 12.5), (10159, 9.4), (12800, -4.4)))
BREATHY_CRACKLE_DB = -8.0       # 2 dB under the clicks' 99th percentile match at 2-4 kHz (Ben: "a little too loud")
from tonelib import ReedCrackleProperties
LAYERED[(66, 8)] = ((("set", 66, BREATHY_TENOR), 0, 0.0), (("class", ReedCrackleProperties), 0, BREATHY_CRACKLE_DB))
VARIATIONS[(66, 8)] = routed_variation(66, "breathy", **BREATHY_TENOR)
VARIATION_NAMES[(66, 8)] = "BreathyTnr."
VARIATION_TRIM_DB[(66, 8)] = PROGRAM_TRIM_DB.get(66, 0.0)
VARIATION_TRIM_DB[(35, 2)] = PROGRAM_TRIM_DB.get(35, 0.0) + 5.8
VARIATION_TRIM_DB[(35, 3)] = PROGRAM_TRIM_DB.get(35, 0.0) + 9.5

# THE MAP SWITCH: BANK SELECT LSB (CC32) picks a Sound Canvas's map, as an
# SC-88 does -- 1 the SC-55 map (the SC-55mkII's, as a later module has it),
# 2 the SC-88's, 3 the SC-88Pro's, 4 the SC-8850's -- latched with CC0 until the next program
# change. 0, or none, is OURS: the SC-55's own tones, and the later maps'
# where the SC-55 had none. A map names its tones (gs_map_names.MAP_NAMES,
# from the SC-88Pro manual); under a map:
#   - a number it has no tone at plays the capital, as a Sound Canvas does
#   - a number where it holds ANOTHER TONE than ours (MAP_OTHER) plays its own,
#     kept under the key 128 x map + bank (VARIATIONS, VARIATION_NAMES and the
#     trims are all keyed so), or the capital until that is built
#   - anywhere else it plays ours: the same tone, perhaps renamed ("Syn.Bass
#     3", "Acid Bass")
from gs_map_names import MAP_NAMES
MAP_LABELS = {1: "SC-55", 2: "SC-88", 3: "SC-88Pro", 4: "SC-8850"}
MAP_OTHER = {
    1: {(3, 8), (4, 16), (5, 16), (62, 16), (63, 16)},
    2: {(4, 8), (39, 8)},
    3: {(0, 16), (3, 8), (4, 8), (39, 8), (16, 8), (16, 9), (16, 32), (17, 1), (17, 32),
        (60, 16), (62, 8), (63, 8), (63, 17)},
    # the SC-8850 keeps the SC-88Pro's, and makes its two "w" pianos uprights
    # and pop pianos
    4: {(0, 8), (0, 16), (1, 8), (3, 8), (4, 8), (39, 8), (16, 8), (16, 9), (16, 32), (17, 1),
        (17, 32), (60, 16), (62, 8), (63, 8), (63, 17)},
}


def map_bank(program, bank, gsmap):
    """The variation key a program change selects: `bank` (CC0) under the map
    `gsmap` (CC32). 0 is the capital tone."""
    if not bank or gsmap not in MAP_NAMES:
        return bank
    p = int(program) & 0x7F
    if (p, bank) not in MAP_NAMES[gsmap]:
        return 0
    if (p, bank) in MAP_OTHER[gsmap]:
        # its own, or ANOTHER MAP'S tone of the same name (the SC-88Pro keeps
        # the SC-88's "Beef FM Bass" at 39.8), else the capital
        name = _map_norm(MAP_NAMES[gsmap][(p, bank)])
        for m in [gsmap] + sorted(MAP_NAMES):
            own = 128 * m + bank
            if (p, own) in VARIATIONS and _map_norm(MAP_NAMES[m].get((p, bank), "")) == name:
                return own
        return 0
    return bank


def _map_norm(name):
    return "".join(ch for ch in name.lower() if ch.isalnum())


# THE SC-8850 MAP'S OWN SYNTH TONES (sc88_synth.SC8850_SYNTH): under their
# own bank, or the SC-8850 map's key where an earlier map used the slot
from sc88_synth import SC8850_SYNTH
for (_p, _b), (_nm, _base, _pan) in SC8850_SYNTH.items():
    _B = getattr(_TL, _base)
    _k = 128 * 4 + _b if (_p, _b) in MAP_OTHER.get(4, ()) else _b
    VARIATIONS[(_p, _k)] = type("Sc8850_%d_%d" % (_p, _b), (_B,), dict(messenger=dict(_B.messenger, **_pan)))
    VARIATION_NAMES[(_p, _k)] = _nm


# GENERAL MIDI 2's variations (bank select MSB 121, the LSB picking): GM 2
# numbers them its own way -- its Piano 1w is LSB 1, the Sound Canvas's bank
# 8 -- but every one IS a Sound Canvas tone under its own name (gm2_names,
# from the SC-8850 manual's GM 2 list). So a GM 2 LSB is read as the tone of
# that name: the SC-8850 map's, else an earlier map's, through map_bank as a
# file's CC32 would select it. Not built: the capital, as a Sound Canvas does.
from gm2_names import GM2_NAMES
_GM2_BANK = {}


def gm2_bank(program, lsb):
    """The variation key GM 2's (program, LSB) selects; 0 the capital."""
    p, lsb = int(program) & 0x7F, int(lsb)
    if not lsb or (p, lsb) not in GM2_NAMES:
        return 0
    if (p, lsb) not in _GM2_BANK:
        name, key = _map_norm(GM2_NAMES[(p, lsb)]), 0
        for m in (4, 3, 2, 1):
            hit = [b for (pp, b), nm in MAP_NAMES[m].items() if pp == p and _map_norm(nm) == name]
            if hit:
                key = map_bank(p, hit[0], m)
                if key and (p, key) in VARIATIONS:
                    break                   # built: else an earlier map's, else the capital
                key = 0
        _GM2_BANK[(p, lsb)] = key
    return _GM2_BANK[(p, lsb)]


def bank_select(v):
    """(CC0, CC32) that select the variation key v (map_bank's inverse)."""
    return v & 0x7F, v >> 7


# ...THE MAPS' OWN TONES that are settings or layers of ours (the synth ones
# are Moog panels, sc88_synth.MAP_SYNTH): {(map, program, bank): (name, how)},
# `how` as SC88_CHEAP's
MAP_TONES = {
    (1, 3, 8): ("HonkyTonk w", ("set", 3, {"key_pan_spread": 0.5})),
    # "v": velocity-switched -- read here as the tine's bell an octave up
    # coming in on a hard hit
    (1, 4, 16): ("E.Piano 1v", ("layer", ((4, 0, 0.0), (4, 12, -9.0, 100, 127)))),
    (1, 5, 16): ("E.Piano 2v", ("layer", ((5, 0, 0.0), (5, 12, -9.0, 100, 127)))),
    (2, 4, 8): ("St.Soft EP", ("set", 4, {"key_pan_spread": 0.5,
                                          "sound_bias": {"brightness": -0.35}})),
    # THE SC-88Pro MAP'S OWN under numbers the SC-88 used (the SC-8850 keeps
    # them, and GM 2 names them): readings of their names, for Ben's ear.
    # A European concert grand, warmer than ours: the hammer's corner at 0.8x
    (3, 0, 16): ("European Pf", ("set", 0, {"hammer_corner_hz": 0.8 * 3542.03})),
    # the honky-tonk's two extra strings further out: 14-30 cents, not 8-20
    (3, 3, 8): ("Honky-tonk 2", ("set", 3, {"string_detune_range": (14.0, 30.0)})),
    # the Leslie's TREMOLO, its fast speed (Leslie names them chorale and tremolo)
    (3, 16, 8): ("Trem. Organ", ("set", 16, {"leslie_fast": True})),
    # the 1970s rock organ: 888 through a driven amp (Jon Lord's)
    (3, 16, 32): ("70's E.Organ", ("set", 16, {"default_stops": 0b111, "amp_drive": 1.5})),
    # 888 and the B3's third-harmonic percussion: Jimmy Smith's setting
    (3, 17, 32): ("Perc. Organ", ("set", 17, {"default_stops": 0b100000000111})),
}
for (_m, _p, _b), (_nm, _how) in MAP_TONES.items():
    _k = (_p, 128 * _m + _b)
    VARIATION_NAMES[_k] = _nm
    if _how[0] == "layer":
        LAYERED[_k] = _how[1]
        VARIATIONS[_k] = routed_variation(_how[1][0][0], "map%d_%d_%d" % (_m, _p, _b))
    else:
        VARIATIONS[_k], _tr = _sc88_class(_how, "map%d_%d_%d" % (_m, _p, _b))
        VARIATION_TRIM_DB.setdefault(_k, _tr)

# THE VARIATIONS' LEVELS, MEASURED: each GS variation GeneralUser GS has a
# preset for, levelled to it as the programs are (examples/sfx_levels.py
# --var-trim: velocities 64 and 100, K level re a piano C4) -- over the
# defaults set above (a variation's capital's trim, or the SFX set's)
VARIATION_TRIM_FIT = {(0, 8): 0.0, (0, 16): 0.2, (1, 8): 8.2, (2, 1): -1.3, (2, 2): -2.8, (2, 8): 1.9, (3, 8): 7.3, (3, 136): 9.6, (4, 8): 0.6, (4, 16): -7.4, (4, 24): -4.5, (4, 144): -2.1, (4, 264): -2.0, (5, 8): -2.4, (5, 16): -5.3, (5, 144): -5.6, (6, 8): -11.9, (6, 16): -10.9, (6, 24): -12.5, (11, 8): 2.3, (12, 8): 2.9, (14, 8): -2.6, (14, 9): -1.9, (15, 1): 4.2, (16, 1): -7.4, (16, 8): -4.4, (16, 9): -6.0, (16, 16): -5.5, (16, 17): -5.7, (16, 18): -9.6, (16, 32): -10.1, (16, 33): -7.7, (16, 40): -6.9, (17, 1): -2.4, (17, 8): -2.0, (17, 32): -2.7, (18, 8): -10.1, (18, 16): -7.9, (18, 24): -10.1, (19, 8): -2.6, (19, 16): -3.8, (19, 24): 5.4, (19, 32): 5.2, (21, 8): -12.2, (24, 8): 7.9, (24, 16): 8.3, (24, 24): 9.6, (25, 8): -0.9, (25, 9): -0.4, (25, 16): 3.5, (26, 8): 12.8, (27, 8): 3.7, (28, 8): 5.1, (30, 8): 6.6, (31, 8): -12.7, (31, 16): 13.2, (34, 1): 3.7, (35, 4): 9.2, (38, 1): -4.9, (38, 8): -4.6, (38, 9): -2.9, (38, 10): 5.4, (38, 16): 4.0, (39, 1): -4.2, (39, 2): -2.6, (39, 3): 3.0, (39, 8): -2.3, (39, 9): -1.3, (39, 16): -0.9, (39, 17): -5.5, (39, 18): -2.7, (39, 19): -3.3, (39, 264): -3.9, (45, 16): 16.1, (48, 1): 2.5, (48, 2): 7.4, (48, 8): 2.2, (48, 9): 0.9, (48, 11): -0.4, (48, 16): 2.1, (48, 24): 4.2, (49, 10): 2.6, (50, 1): 10.0, (50, 8): 5.0, (52, 8): 3.5, (54, 8): 2.1, (55, 10): -15.9, (55, 16): 16.3, (60, 16): 6.4, (61, 8): 3.1, (62, 1): 8.4, (62, 8): 3.2, (62, 9): 11.0, (62, 16): 7.4, (62, 144): 9.0, (63, 8): 5.2, (63, 16): 8.5, (63, 17): 7.6, (63, 144): 8.5, (80, 1): -2.3, (80, 2): 9.0, (80, 3): 11.9, (80, 4): 0.3, (80, 5): 8.5, (80, 6): 5.5, (80, 8): 8.0, (81, 1): -5.4, (81, 2): -2.0, (81, 3): 3.1, (81, 4): -1.0, (81, 5): 1.1, (81, 6): -2.8, (81, 7): -0.5, (81, 8): 4.0, (81, 16): 4.1, (82, 1): 8.8, (82, 2): 9.9, (84, 8): 0.1, (86, 1): 1.2, (87, 1): 6.5, (87, 2): 3.5, (88, 1): 14.7, (89, 1): 2.2, (89, 2): 2.6, (89, 3): 2.9, (89, 4): 4.5, (90, 1): 7.8, (91, 1): 8.0, (93, 1): 5.8, (93, 2): 5.4, (95, 1): 5.1, (95, 8): 5.9, (95, 9): 4.2, (95, 10): 12.8, (96, 1): 1.3, (96, 2): 15.9, (96, 8): -0.9, (97, 1): 5.5, (97, 2): 7.7, (97, 8): 10.9, (98, 1): 8.1, (98, 2): 12.8, (98, 3): -0.9, (98, 4): 3.8, (98, 5): -6.0, (98, 6): 3.5, (98, 7): 3.9, (98, 8): 3.9, (98, 9): 4.6, (98, 16): 3.0, (98, 17): 3.6, (98, 18): 0.1, (98, 19): 9.3, (99, 1): 6.2, (99, 2): 5.6, (99, 3): 4.6, (99, 4): 2.8, (99, 5): 8.3, (99, 6): 5.2, (101, 1): 3.8, (101, 2): 8.1, (102, 1): -3.3, (102, 2): 6.7, (102, 3): -1.2, (102, 4): -1.2, (102, 5): 1.8, (102, 6): -2.5, (103, 1): 5.6, (104, 1): 12.6, (104, 2): 17.0, (107, 8): 0.7, (115, 8): -13.2, (116, 8): 0.5, (117, 1): 5.8, (117, 8): -1.8, (117, 9): 5.5, (118, 8): 1.2, (118, 9): 0.0, (119, 1): -1.7, (119, 8): -0.2, (119, 9): 2.5, (119, 16): -2.8, (119, 17): -2.1, (119, 24): 1.2, (119, 25): 2.1, (120, 1): -5.4, (120, 2): -5.3, (120, 3): 1.0, (120, 4): 1.0, (120, 6): 32.8, (121, 1): -9.6, (122, 1): 16.4, (122, 2): -0.7, (122, 3): 11.8, (122, 4): 19.8, (122, 5): 3.4, (123, 1): -10.8, (123, 2): -6.9, (124, 1): 13.3, (124, 2): -7.4, (124, 3): -10.3, (124, 4): -8.0, (124, 5): -2.0, (124, 7): -6.4, (125, 1): 3.1, (125, 2): -8.3, (125, 3): -1.4, (125, 4): -4.3, (125, 5): 1.1, (125, 6): -6.7, (125, 7): 2.0, (125, 8): -2.4, (125, 9): 0.8, (126, 1): -2.4, (126, 2): -8.0, (126, 3): -1.1, (126, 4): -3.4, (126, 5): -0.9, (126, 6): 14.3, (127, 1): 4.7, (127, 2): 8.3, (127, 3): 4.2}
VARIATION_TRIM_DB.update(VARIATION_TRIM_FIT)

# ...AND BY EAR, where there is no witness: dB added over the above (so a
# re-run of --var-trim keeps them). GeneralUser has no preset for these, and
# each was put where its capital sits -- which the SC-88Pro does not.
#   98.2 Soft Crystal: at Crystal's level it stood out of Tokei against the
#        SC-88Pro recording, where it all but disappears -- too far, Ben
#        judged, for the arrangement. Its panel made soft (sc88_synth) and
#        set 5.3 dB under Crystal by ear (Ben, 2026-10-20)
#   48.1 Bright Str, 48.2 ChamberStr: at the level Ben chose them at on
#        Tokei's strings -- the chamber section 5.3 dB under the full one,
#        which is the power of 2 players against 7
VARIATION_TRIM_EAR = {(98, 2): -5.3, (48, 1): -0.4, (48, 2): -5.3}
for _k, _db in VARIATION_TRIM_EAR.items():
    VARIATION_TRIM_DB[_k] = VARIATION_TRIM_DB.get(_k, PROGRAM_TRIM_DB.get(_k[0], 0.0)) + _db
