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
# variation of the program with it. Dracula X's Tougi (SC-88) the same for
# the nylon: its Main gt already at CC7 120, velocity 126, and still quiet;
# Ben chose +6 from +3/+6 (against GeneralUser the nylon is within ~2 dB --
# Roland's guitars sit hotter in its band). A GM file keeps GeneralUser's
# balance.
GS_TRIM_DB = {24: 6.0, 29: 3.0, 30: 3.0, 33: 3.0, 34: 3.0}
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
# ...25.17 "Mandolin 2": brighter, picked nearer the bridge; 25.18
# "MandolinTrem": tremolo-picked, as the mandolin is played (tonelib
# tremolo_pick_hz: 12 strokes a second)
VARIATIONS[(25, 17)] = type("Mandolin2Properties", (_MDP,), dict(tonal_dampening=_MDP.tonal_dampening * 0.8))
VARIATION_NAMES[(25, 17)] = "Mandolin 2"
VARIATIONS[(25, 18)] = type("MandolinTremProperties", (_MDP,), dict(tremolo_pick_hz=12.0))
VARIATION_NAMES[(25, 18)] = "MandolinTrem"
VARIATION_TRIM_DB[(25, 17)] = VARIATION_TRIM_DB[(25, 18)] = PROGRAM_TRIM_DB.get(25, 0.0)
# ...and the tones that are a voice no program routes to (2026-10-26):
# the NAY (72.8; the Arabic end-blown reed flute: our kawala, its cousin)
# and with a tremolo of the breath; the ZITHER (15.16-17: the kanun, a
# zither, plucked; its second brighter); CHURCH BELL 2 (14.10: the church
# bell with its hum an octave under, louder)
from tonelib import KawalaProperties as _KWL, KanunProperties as _KNN
VARIATIONS[(72, 8)] = _KWL
VARIATION_NAMES[(72, 8)] = "Nay"
VARIATIONS[(72, 9)] = type("NayTremoloProperties", (_KWL,), dict(sound_bias={"vib_depth": 0.9, "vib_rate": 0.3}))
VARIATION_NAMES[(72, 9)] = "Nay Tremolo"
VARIATIONS[(15, 16)] = _KNN
VARIATION_NAMES[(15, 16)] = "Zither 1"
VARIATIONS[(15, 17)] = type("Zither2Properties", (_KNN,), dict(tonal_dampening=_KNN.tonal_dampening * 0.75))
VARIATION_NAMES[(15, 17)] = "Zither 2"
LAYERED[(14, 10)] = ((("class", _CBP), 0, 0.0), (("class", _CBP), -12, -6.0))
VARIATIONS[(14, 10)] = _CBP
VARIATION_NAMES[(14, 10)] = "Church Bell2"
# PINK NOISE (122.16): the breath's noise voice (tonelib.BreathNoiseProperties)
# with every third-octave band level -- pink, equal power per band -- and
# held still; a BURNER (125.12): a gas burner's roar, the low bands up, falling
# 4 dB a third-octave band above 250 Hz, flickering 3 dB at 7 Hz
from tonelib import BreathNoiseProperties as _BNP
_PINK_BANDS = tuple(_h for _h, _d in _BNP.breath_noise_db)
VARIATIONS[(122, 16)] = type("PinkNoiseProperties", (_BNP,), dict(
    breath_noise_db=tuple((_h, -25.0) for _h in _PINK_BANDS), breath_noise_wobble_db=0.0))
VARIATION_NAMES[(122, 16)] = "Pink Noise"
VARIATIONS[(125, 12)] = type("BurnerProperties", (_BNP,), dict(
    breath_noise_db=tuple((_h, -18.0 - max(0.0, 4.0 * 3.0 * __import__("math").log2(_h / 250.0))) for _h in _PINK_BANDS),
    breath_noise_wobble_db=3.0, breath_noise_wobble_hz=7.0))
VARIATION_NAMES[(125, 12)] = "Burner"
# BIWA TREMOLO (120.13): the biwa (120.12) tremolo-picked, ten strokes a second
VARIATIONS[(120, 13)] = type("BiwaTremoloProperties", (__import__("tonelib").BiwaProperties,), dict(
    tremolo_pick_hz=10.0, tremolo_pick_up_db=-2.0, tremolo_pick_jitter=0.08))
VARIATION_NAMES[(120, 13)] = "Biwa Tremolo"
for _k, _src in (((122, 16), 121), ((125, 12), 121), ((120, 13), 106)):
    VARIATION_TRIM_DB[_k] = PROGRAM_TRIM_DB.get(_src, 0.0)
# 606 DIST.TOM (118.13): the 606 set's tom through the valve, driven
VARIATIONS[(118, 13)] = type("Tr606DistTomProperties", (melodic_sfx(45, kit=28),), dict(amp_drive=2.0))
VARIATION_NAMES[(118, 13)] = "606 Dist.Tom"
VARIATION_TRIM_DB[(118, 13)] = KIT_TRIM_DB
# the UILLEANN PIPES (109.9-11: tonelib, measured on a practice set): the
# set, its "normal" (the same voice: Roland's names do not say what parts
# them), and ornamented -- a CUT on every note, a flick a fourth above
from tonelib import UilleannPipeProperties as _UIL
VARIATIONS[(109, 9)] = _UIL
VARIATION_NAMES[(109, 9)] = "Uillean Pipe"
VARIATIONS[(109, 10)] = _UIL
VARIATION_NAMES[(109, 10)] = "UillnPipe Nm"
VARIATIONS[(109, 11)] = type("UilleannPipeOrnamentedProperties", (_UIL,), dict(cut_semitones=5))
VARIATION_NAMES[(109, 11)] = "UillnPipe Or"
for _k in ((109, 9), (109, 10), (109, 11)):
    VARIATION_TRIM_DB[_k] = PROGRAM_TRIM_DB.get(109, 0.0)
# the DIDGERIDOO (109.8: tonelib, fitted to two CC0 takes, examples/didg_fit.py)
from tonelib import DidgeridooProperties as _DDG
VARIATIONS[(109, 8)] = _DDG
VARIATION_NAMES[(109, 8)] = "Didgeridoo"
VARIATION_TRIM_DB[(109, 8)] = PROGRAM_TRIM_DB.get(58, 0.0)
# the BODHRAN, open and with the hand pressed in (108.9-10: tonelib, fitted
# to Teh_Bucket's strokes, examples/perc_fit.py bodhran)
from tonelib import BodhranProperties as _BDH, BodhranMuteProperties as _BDM
VARIATIONS[(108, 9)] = _BDH
VARIATION_NAMES[(108, 9)] = "Bodhran"
VARIATIONS[(108, 10)] = _BDM
VARIATION_NAMES[(108, 10)] = "Bodhran Mute"
VARIATION_TRIM_DB[(108, 9)] = VARIATION_TRIM_DB[(108, 10)] = PROGRAM_TRIM_DB.get(116, 0.0)
for _k, _src in (((72, 8), 75), ((72, 9), 75), ((15, 16), 15), ((15, 17), 15), ((14, 10), 14)):
    VARIATION_TRIM_DB[_k] = PROGRAM_TRIM_DB.get(_src, 0.0)


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
    # Rhythm2's tone, as Ben chose it (SENSATIO, 2) -- and THROUGH A GATE, as
    # a chugging rhythm rig is (efxbus.NoiseGate; Ben: the gated chug "needs
    # to sound like a string section bowing"): its body held by the
    # compression in front, its stop the gate's, 6 ms (examples/chug_demo.py)
    # ...ITS OPEN STRINGS RINGING ON under the palm between chugs (standard
    # tuning's six, up to 2 s; blockrender open_string_ring) -- what the gate cuts
    # -- into a closed-back 4x12 (cabinet.Guitar412), the rhythm rig's stack
    (28, 1): ("Muted Dis.Gt", ("set", 30, dict(palm_mute(1.0), noise_gate=dict(
        keyed=True, hold_s=0.008, close_s=0.006, sustain_db=-24.0, ratio=6.0, makeup_db=13.0),
        open_string_ring=((40, 45, 50, 55, 59, 64), 2.0), cabinet="guitar412"))),
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
    # MUTE PICK BASS: the palm on the strings, and the BASSIST'S STOP -- a key-up
    # damped by the hands at once (release 0.05 s, chosen), not the picked
    # bass's fitted 0.355 s lift-off ring: in a stop-start riff the bass stops
    # with the band (examples/chug_demo.py)
    (34, 8): ("MutePickBs.", ("set", 34, dict(decay_db=20.0, tonal_dampening=2.4,
                                              release_valve_time=0.05))),
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
    # --- THE SC-88 PRO's OTHER ENSEMBLES (2026-10-26) -------------------------
    # the cellos alone, a section; the strings an octave apart, doubled
    (48, 3): ("Cello sect.", ("set", 42, dict(section_players=6, section_spread_cents=6.0, section_width_m=2.0))),
    (48, 32): ("Oct Strings1", ("layer", ((48, 0, 0.0), (48, 12, -4.0)))),
    (48, 33): ("Oct Strings2", ("layer", ((48, 0, 0.0), (48, -12, -4.0)))),
    # the horns with the strings, under them
    (48, 12): ("Strings+Horn", ("layer", ((48, 0, 0.0), (60, 0, -6.0)))),
    # a church choir: the choir darker and wider, the space doing the rest
    (52, 10): ("Church Choir", ("set", 52, dict(key_pan_spread=WIDE, tonal_dampening=1.7, section_players=12))),
    # breathed: "hah" -- the choir's breath up, its onset aspirated
    (52, 16): ("Choir Hahs", ("set", 52, dict(breath_noise_db=tuple(
        (h, d + 8.0) for h, d in __import__("tonelib").ChoirAahsProperties.breath_noise_db),
        chiff_min_valve_time=0.04, chiff_max_valve_time=0.08))),
    # the men's aah (the sex rule pinned male: crossover far above the
    # range) with the strings under it
    (52, 33): ("Male Aah+Str", ("layer", ((("set", 52, dict(voice_crossover_hz=20000.0)), 0, 0.0),
                                          (48, 0, -5.0)))),
    # HITS: the orchestra hit with what each name adds -- a drum's crack, a
    # shock (the hit swept down: an octave under, short), the valve, a
    # sampler's bits, an organ, rave octaves, a string stab, a stack
    (55, 11): ("Perc. Hit", ("layer", ((55, 0, 0.0), (("kit", 38, 48), -12, 4.0)))),
    (55, 12): ("Shock Wave", ("layer", ((55, 0, 0.0), (55, -12, -3.0), (("kit", 57, 48), -12, 2.0)))),
    (55, 17): ("Techno Hit", ("layer", ((55, 0, 0.0), (("kit", 36, 30), -24, 4.0)))),
    (55, 18): ("Dist. Hit", ("set", 55, dict(insertion_efx=((0x01, 0x11), {})))),
    (55, 20): ("Bit Hit", ("set", 55, dict(insertion_efx=((0x01, 0x72), {})))),
    (55, 21): ("Bim Hit", ("layer", ((55, 0, 0.0), (55, 7, -4.0)))),
    (55, 22): ("Technorg Hit", ("layer", ((55, 0, -2.0), (("set", 16, dict(one_shot=True, gate_time=0.15)), 0, 0.0)))),
    (55, 23): ("Rave Hit", ("layer", ((55, 0, 0.0), (55, 12, -4.0), (55, -12, -4.0)))),
    (55, 24): ("Strings Hit", ("set", 48, dict(one_shot=True, gate_time=0.18, sound_bias={"attack": -1.0}))),
    (55, 25): ("Stack Hit", ("layer", ((55, 0, 0.0), (55, 12, -5.0), (55, 19, -8.0)))),
    # --- THE SC-88 PRO's OTHER BRASS (2026-10-26) ----------------------------
    # the trumpet a little darker than the capital; trumpets in fourths; a
    # synth trumpet (the synth brass panel)
    (56, 2): ("Trumpet", ("set", 56, dict(blare_db_per_khz=2.0, blare_knee_hz=400, blare_cap_db=20.0))),
    (56, 16): ("4th Trumpets", ("layer", ((56, 0, 0.0), (56, 5, -2.0)))),
    (56, 32): ("Syn. Trumpet", ("alias", 62)),
    # two trombones a few cents apart; the bass trombone, darker and lower
    (57, 2): ("Twin bones", ("set", 57, dict(detuned_pair=(-6.0, 6.0)))),
    (57, 8): ("Bs. Trombone", ("set", 57, dict(blare_db_per_khz=-4.0, blare_knee_hz=150, blare_cap_db=30.0,
                                               tonal_dampening=1.0))),
    # muted horns: the muted brass in the horns' octave
    (59, 8): ("Muted Horns", ("layer", ((59, -12, 0.0),))),
    # horns with the strings; two horns apart; a horn ripping up into the note
    # (the fall's mirror, a fifth below it, tonelib rip_cents)
    (60, 2): ("Horn + Orche", ("layer", ((60, 0, 0.0), (48, 0, -6.0)))),
    (60, 9): ("Dual Horns", ("set", 60, dict(detuned_pair=(-8.0, 8.0)))),
    (60, 24): ("F.Horn Rip", ("set", 60, dict(rip_cents=700.0, rip_s=0.15))),
    # the section: fortissimo (the blare up), its trombones alone, a third
    # voicing, sforzando (a hard stab over the section held soft), a trumpet's
    # fall, octaves, with the saxes
    (61, 1): ("Brass ff", ("set", 61, dict(blare_db_per_khz=9.0, blare_knee_hz=700, blare_cap_db=28.0))),
    (61, 2): ("Bones Sect.", ("set", 57, dict(detuned_pair=(-7.0, 7.0), key_pan_spread=WIDE))),
    (61, 9): ("Brass 3", ("set", 61, dict(blare_db_per_khz=4.0, blare_knee_hz=500, blare_cap_db=22.0))),
    (61, 10): ("Brass sfz", ("layer", ((("set", 61, dict(one_shot=True, gate_time=0.15)), 0, 4.0), (61, 0, -6.0)))),
    (61, 17): ("Trumpet Fall", ("set", 56, dict(fall_cents=900.0))),
    (61, 24): ("Octave Brass", ("layer", ((61, 0, 0.0), (61, 12, -6.0)))),
    (61, 25): ("Brass + Reed", ("layer", ((61, 0, 0.0), (65, 0, -4.0)))),
    # --- THE SC-88 PRO's OTHER ORGANS (2026-10-26): drawbars (bit 0 16',
    # 1 5 1/3', 2 8', 3 4', 4 2 2/3', 5 2', 6 1 3/5', 7 1 1/3', 8 1'; 11 the
    # third-harmonic percussion, 12 the second), the church organ's ranks,
    # the reeds' settings -------------------------------------------------
    (16, 19): ("Farf Organ", ("set", 16, dict(default_stops=0b100101100, amp_drive=0.8))),   # a combo organ, thin and edged
    (16, 27): ("Hybrid Organ", ("layer", ((16, 0, 0.0), (89, 0, -8.0)))),                    # the drawbars over a warm pad
    (16, 29): ("Digi Church", ("set", 19, dict(default_stops=0b10010011))),                  # a church organ, 8' 4' 16' mixture
    (16, 48): ("5th Organ", ("layer", ((16, 0, 0.0), (16, 7, -4.0)))),
    (17, 2): ("E.Organ 16+2", ("set", 17, dict(default_stops=0b100001))),                    # 16' and 2'
    (17, 9): ("Octave Organ", ("layer", ((17, 0, 0.0), (17, 12, -6.0)))),
    (18, 17): ("Rock Organ 1", ("set", 18, dict(default_stops=0b111111111, amp_drive=1.5))),
    (18, 18): ("Rock Organ 2", ("set", 18, dict(default_stops=0b100000111, amp_drive=2.0, leslie_fast=True))),
    # a theatre organ: the tibia (flute 8), the vox humana, the celeste, the
    # koppelflute 4, and the tremulant that makes it one
    (19, 33): ("Theater Org.", ("set", 19, dict(default_stops=(1 << 6) | (1 << 23) | (1 << 21) | (1 << 14) | (1 << 13)))),
    # the reed organ's wind louder in it
    (20, 8): ("Wind Organ", ("set", 20, dict(breath_noise_db=tuple(
        (h, d + 8.0) for h, d in __import__("tonelib").ReedOrganFreeProperties.breath_noise_db)))),
    # accordions: through the distortion; chorused; harder (brighter, the
    # reeds' edge up) and softer (darker)
    (21, 9): ("Dist. Accord", ("set", 21, dict(insertion_efx=((0x01, 0x11), {})))),
    (21, 16): ("Cho. Accord", ("set", 21, dict(insertion_efx=((0x01, 0x42), {})))),
    (21, 24): ("Hard Accord", ("set", 21, dict(tonal_dampening=1.5, reed_edge=0.0045))),
    (21, 25): ("Soft Accord", ("set", 21, dict(tonal_dampening=2.6))),
    # bandoneons: two reeds a few cents apart; the octave reed louder
    (23, 8): ("Bandoneon 2", ("set", 23, dict(detuned_pair=(-5.0, 5.0)))),
    (23, 16): ("Bandoneon 3", ("layer", ((23, 0, 0.0), (23, 12, -3.0)))),
    # --- THE SC-88 PRO's OTHER KEYBOARDS (2026-10-26) -----------------------
    (0, 24): ("Piano + Str.", ("layer", ((0, 0, 0.0), (48, 0, -6.0)))),
    # the Rhodes through the chorus, softly (the tine's swing small), and
    # through the distortion
    (4, 9): ("Cho. E.Piano", ("set", 4, dict(insertion_efx=((0x01, 0x42), {})))),
    (4, 10): ("SilentRhodes", ("set", 4, dict(pickup_deflection=0.35))),
    (4, 17): ("Dist E.Piano", ("set", 4, dict(insertion_efx=((0x01, 0x11), {})))),
    # the harpsichord's other registers (bit 0 8', 1 the upper 8', 2 4', 3
    # the lute): 8' and 4'
    (6, 1): ("Harpsichord2", ("set", 6, dict(default_stops=0b101))),
    # the clavinet: compressed, through the auto-wah (its resonance), an
    # octave doubling
    (7, 8): ("Comp Clav.", ("set", 7, dict(insertion_efx=((0x01, 0x30), {})))),
    (7, 16): ("Reso Clav.", ("set", 7, dict(insertion_efx=((0x01, 0x21), {})))),
    (7, 24): ("Clav.o", ("layer", ((7, 0, 0.0), (7, 12, -6.0)))),
    # --- THE SC-88 PRO's OTHER GUITARS (2026-10-26): the Strat (GM 27, its
    # neck pickup at 0.247 of the string), a Telecaster's pickups (TC: the
    # slanted bridge pickup ~0.065, the neck ~0.21), a Les Paul's
    # humbuckers (LP: the overdrive's pair at the bridge) -------------------
    (27, 1): ("Clean Half", ("set", 27, dict(pickup_points=(0.247, 0.155)))),          # neck and middle
    (27, 2): ("Open Hard 1", ("set", 27, dict(strike_point=0.12))),
    (27, 3): ("Open Hard 2", ("set", 27, dict(strike_point=0.11, pickup_points=(0.09,)))),
    (27, 9): ("JC Chorus Gt", ("set", 27, dict(amp_drive=0.0, cabinet="jc120", insertion_efx=((0x01, 0x42), {})))),
    (27, 16): ("TC FrontPick", ("set", 27, dict(pickup_points=(0.21,)))),
    (27, 17): ("TC Rear Pick", ("set", 27, dict(pickup_points=(0.065,)))),
    (27, 18): ("TC Clean ff", ("set", 27, dict(pickup_points=(0.065,), strike_point=0.11))),
    (27, 19): ("TC Clean 2:", ("set", 27, dict(pickup_points=(0.065,), hammer_legato=True, slur_cuts_release=True))),
    (28, 2): ("TC Muted Gt.", ("set", 28, dict(pickup_points=(0.065,)))),
    (29, 1): ("Overdrive 2", ("set", 29, dict(amp_drive=6.0))),
    (29, 2): ("Overdrive 3", ("set", 29, dict(amp_drive=3.0, pickup_points=(0.21, 0.24)))),
    (29, 8): ("LP OverDrvGt", ("set", 29, dict(pickup_points=(0.049, 0.077), amp_drive=5.0))),
    (29, 9): ("LP OverDrv:", ("set", 29, dict(pickup_points=(0.049, 0.077), amp_drive=5.0, hammer_legato=True,
                                              slur_cuts_release=True))),
    (30, 3): ("Distortion:", ("set", 30, dict(hammer_legato=True, slur_cuts_release=True))),
    (30, 4): ("Dist.Fast", ("set", 30, dict(attack_time=0.0008, strike_point=0.12))),
    (31, 9): ("Gt.Feedback2", ("var", (30, 9))),
    # harmonics on the bass: the guitar's harmonics an octave down
    (31, 24): ("E.Bass Harm.", ("layer", ((31, -12, 0.0),))),
    # --- THE SC-88 PRO's OTHER ACOUSTICS (2026-10-26) -----------------------
    (8, 1): ("Pop Celesta", ("layer", ((8, 0, 0.0), (8, 12, -8.0)))),
    (11, 9): ("Vibraphones", ("set", 11, dict(detuned_pair=(-4.0, 4.0), key_pan_spread=WIDE))),
    (15, 24): ("Dulcimer", ("alias", 15)),
    # basses: a rockabilly slap on the upright (struck at its end), a wilder
    # one, an open hi-hat on every note (Roland's), the Jazz bass on both
    # pickups, driven for rock, chorused, its harmonics over it; the pick
    # harder, darker; the fretless with the upright; slap and pop, two slaps
    (32, 1): ("Rockabilly", ("set", 32, dict(strike_point=0.08, tonal_dampening=1.2))),
    (32, 8): ("Wild A.Bass", ("set", 32, dict(tonal_dampening=0.9))),
    (32, 16): ("Bass + OHH", ("layer", ((32, 0, 0.0), (("kit", 46, 0), 0, -8.0)))),
    (33, 3): ("Jazz Bass 2", ("set", 33, dict(pickup_points=(0.098, 0.2)))),
    (33, 4): ("Rock Bass", ("set", 33, dict(amp_drive=1.0))),
    (33, 8): ("ChorusJazzBs", ("set", 33, dict(pickup_points=(0.098,), insertion_efx=((0x01, 0x42), {})))),
    (33, 16): ("F.Bass/Harm.", ("layer", ((33, 0, 0.0), (31, 12, -10.0)))),
    (34, 2): ("Picked Bass3", ("set", 34, dict(amp_drive=2.0))),
    (34, 3): ("Picked Bass4", ("set", 34, dict(tonal_dampening=3.0))),
    (34, 16): ("P.Bass/Harm.", ("layer", ((34, 0, 0.0), (31, 12, -10.0)))),
    (35, 8): ("Wood+FlessBs", ("layer", ((35, 0, 0.0), (32, 0, -4.0)))),
    (36, 1): ("Slap Pop", ("layer", ((36, 0, 0.0), (37, 0, -3.0)))),
    (36, 9): ("Unison Slap", ("set", 36, dict(detuned_pair=(-6.0, 6.0)))),
    # strings' attack sharper, legato-enabled (the colon)
    (40, 1): ("Violin Atk:", ("set", 40, dict(sound_bias={"attack": -1.0}, hammer_legato=True))),
    (41, 1): ("Viola Atk.:", ("set", 41, dict(sound_bias={"attack": -1.0}, hammer_legato=True))),
    (42, 1): ("Cello Atk.:", ("set", 42, dict(sound_bias={"attack": -1.0}, hammer_legato=True))),
    # pizzicato: the cellos and basses (an octave and two under), a chamber
    # group, in stereo, one player
    (45, 1): ("Vcs&Cbs Pizz", ("layer", ((45, -12, 0.0), (45, -24, -4.0)))),
    (45, 2): ("Chamber Pizz", ("set", 45, dict(section_players=2))),
    (45, 3): ("St.Pizzicato", ("set", 45, dict(key_pan_spread=WIDE))),
    (45, 8): ("Solo Pizz.", ("set", 45, dict(section_players=1))),
    # reeds: the soprano and the oboe with more vibrato; the alto growled (the
    # breath through a driven reed); with a trumpet; the tenor brighter, wide;
    # the baritone brighter; reeds and winds together
    (64, 8): ("Soprano Exp.", ("set", 64, dict(sound_bias={"vib_depth": 0.6}))),
    (65, 9): ("Grow Sax", ("set", 65, dict(amp_drive=1.5))),
    (65, 16): ("AltoSax + Tp", ("layer", ((65, 0, 0.0), (56, 0, -4.0)))),
    (66, 1): ("Tenor Sax", ("set", 66, dict(sound_bias={"brightness": 0.3}))),
    (66, 9): ("St.Tenor Sax", ("set", 66, dict(key_pan_spread=WIDE))),
    (67, 1): ("Bari. Sax", ("set", 67, dict(sound_bias={"brightness": 0.3}))),
    (68, 8): ("Oboe Exp.", ("set", 68, dict(sound_bias={"vib_depth": 0.6}))),
    (68, 16): ("Multi Reed", ("layer", ((68, 0, 0.0), (71, 0, -3.0), (70, -12, -6.0)))),
    (71, 16): ("Multi Wind", ("layer", ((73, 12, 0.0), (68, 0, -3.0), (71, 0, -3.0)))),
    # pipes: the dizi (the flute, breathier and brighter: its membrane's buzz
    # is not modelled), the flute with more vibrato, with the violin; the
    # zampona (the pan flute, breathier; then its chiff harder); the
    # shakuhachi legato-enabled; the whistle's second
    (72, 16): ("Di", ("set", 73, dict(sound_bias={"brightness": 0.4, "attack": -0.5}))),
    (73, 2): ("Flute Exp.", ("set", 73, dict(sound_bias={"vib_depth": 0.6}))),
    (73, 8): ("Flute + Vln", ("layer", ((73, 0, 0.0), (40, 0, -4.0)))),
    (75, 16): ("Zampona", ("set", 75, dict(sound_bias={"brightness": -0.3}))),
    (75, 17): ("Zampona Atk", ("set", 75, dict(sound_bias={"brightness": -0.3, "attack": -1.0}))),
    (77, 1): ("Shakuhachi:", ("alias", 77)),
    (78, 1): ("Whistle 2", ("set", 78, dict(sound_bias={"vib_depth": 0.5}))),
    # --- THE SC-88 PRO's ETHNIC TONES (2026-10-26) ---------------------------
    # the sitar's third: its jawari brighter still, a narrower course
    (104, 3): ("Sitar 3", ("set", 104, dict(tonal_dampening=0.33, detuned_pair=(-4.0, 4.0)))),
    # the SAN XIAN, the shamisen's Chinese parent: a snakeskin head, no
    # sawari, plucked nearer the end -- the shamisen brighter, drier
    (105, 9): ("San Xian", ("set", 106, dict(strike_point=0.12, tonal_dampening=0.8))),
    # the GU ZHENG: the koto's Chinese parent, steel-wound strings ringing
    # longer and brighter
    (107, 1): ("Gu Zheng", ("set", 107, dict(tonal_dampening=0.55, decay_db=6.0))),
    # an octave harp: the koto doubled an octave up
    (107, 24): ("Oct Harp", ("layer", ((107, 0, 0.0), (107, 12, -6.0)))),
    # the SANZA, the mbira: the kalimba with its bottle-cap rattle (a short
    # noise on each pluck: the kit's cabasa, quiet)
    (108, 8): ("Sanza", ("layer", ((108, 0, 0.0), (("kit", 69, 0), 0, -18.0)))),
    # the ER HU: two silk strings bowed over a python-skin drum, its sound
    # nasal and vocal, its vibrato wide -- the violin, brighter, the vibrato
    # deeper; the GAO HU, its higher cousin, brighter still
    (110, 8): ("Er Hu", ("set", 40, dict(sound_bias={"brightness": 0.35, "vib_depth": 0.7}))),
    (110, 9): ("Gao Hu", ("set", 40, dict(sound_bias={"brightness": 0.55, "vib_depth": 0.6}))),
    # the MIZMAR (the Arab shawm, outdoors) and the SUONA (China's, with its
    # metal bell): the shanai louder in its upper partials; the suona's
    # second with its vibrato wider
    (111, 24): ("Mizmar", ("set", 111, dict(sound_bias={"brightness": 0.35}))),
    (111, 32): ("Suona 1", ("set", 111, dict(sound_bias={"brightness": 0.5}))),
    (111, 33): ("Suona 2", ("set", 111, dict(sound_bias={"brightness": 0.5, "vib_depth": 0.6}))),
    # --- THE SC-88 PRO's PERCUSSIVE TONES (2026-10-26): its drums from the
    # keyboard, each our kit's voice for it (melodic_sfx), the kit named
    (112, 12): ("Jang-Gu", ("kit", 67, 52)),                 # the Asia set's jang-gu, its che stroke
    (113, 16): ("Tambourine", ("kit", 54, 0)),
    # an island mallet: the steel drum and the marimba under it
    (114, 1): ("Island Mlt", ("layer", ((114, 0, 0.0), (12, 0, -6.0)))),
    # the ANGKLUNG: tuned bamboo tubes rattled in their frame -- the woodblock
    # shaken at 11 strokes a second (tremolo picking); its rhythm tone struck
    (115, 16): ("Angklung", ("set", 115, dict(tremolo_pick_hz=11.0, tremolo_pick_up_db=-1.0, tremolo_pick_jitter=0.12))),
    (115, 17): ("Angkl Rhythm", ("alias", 115)),
    (115, 24): ("Finger Snaps", ("kit", 26, 1)),
    (115, 32): ("909 HandClap", ("kit", 39, 13)),
    (116, 1): ("Small Taiko", ("kit", 52, 52)),
    (116, 16): ("Jungle BD", ("kit", 36, 10)),
    (116, 17): ("Techno BD", ("kit", 36, 11)),
    (116, 18): ("Bounce", ("kit", 82, 58)),
    (117, 16): ("Rash SD", ("kit", 38, 9)),                  # a trashy snare: the lo-fi one
    (117, 17): ("House SD", ("kit", 38, 13)),
    (117, 18): ("Jungle SD", ("kit", 40, 10)),
    (117, 19): ("909 SD", ("kit", 38, 30)),
    (118, 11): ("606 Tom", ("kit", 45, 28)),
    (118, 12): ("909 Tom", ("kit", 45, 30)),
    (119, 2): ("Reverse Cym3", ("kit", 73, 62)),             # the room crash, reversed
    # --- THE SC-88 PRO's SFX (2026-10-26): its sounds from the SFX sets (56,
    # 60, 61), from the keyboard
    (120, 8): ("Gt. FX Menu", ("menu", (("kit", 23, 56), ("kit", 24, 56), ("kit", 25, 56), ("kit", 26, 56), ("kit", 27, 56), ("kit", 28, 56), ("kit", 33, 56), ("kit", 34, 56), ("kit", 35, 56), ("kit", 36, 56), ("kit", 47, 56), ("kit", 48, 56), ("kit", 49, 56),))),     # a menu: slide, wah, slap, strokes, the biwa, cutting noises
    # Bartok's pizzicato: the string snapped back on the fingerboard -- the
    # pizzicato with the double bass's slap on it
    (120, 9): ("Bartok Pizz.", ("layer", ((45, 0, 0.0), (("kit", 50, 56), 0, -4.0)))),
    (120, 10): ("Guitar Slap", ("kit", 25, 56)),
    (120, 11): ("Chord Stroke", ("kit", 26, 56)),
    (122, 6): ("Wind 2", ("kit", 81, 60)),
    (124, 8): ("ScratchKey", ("kit", 61, 56)),
    (124, 9): ("TapeRewind", ("kit", 30, 56)),
    (125, 11): ("Perc. Bang", ("kit", 96, 56)),
    (126, 7): ("Small Club", ("kit", 88, 9)),
    (126, 8): ("ApplauseWave", ("kit", 93, 56)),
    (126, 16): ("Voice One", ("kit", 59, 61)),
    (126, 17): ("Voice Two", ("kit", 60, 61)),
    (126, 18): ("Voice Three", ("kit", 61, 61)),
    (126, 19): ("Voice Tah", ("kit", 62, 61)),
    (126, 20): ("Voice Whey", ("kit", 75, 58)),
    (127, 4): ("Eruption", ("kit", 94, 56)),
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
    if kind == "menu":
        return kit_menu(how[1], tag), KIT_TRIM_DB
    raise ValueError(kind)


def kit_menu(entries, tag):
    """A MENU TONE (the SC-8850's Kick Menu, SD Menu, Crash Menu...): a different
    drum on each key, as a drum set has -- entries ((kind, key, kit), ...) laid
    on consecutive keys from C2, repeating up the keyboard, each sounding at its
    own kit pitch whatever the key (its sounding_octaves offset by the key's
    distance from C4, where melodic_sfx puts the kit pitch). A function of the
    note, as a routed variation is."""
    cache = {}

    def at(note):
        i = (int(note) - 36) % len(entries)
        if (i, note) not in cache:
            base, _tr = _sc88_class(entries[i], tag)
            cache[(i, note)] = type("%s_menu%d" % (base.__name__, note), (base,), dict(
                sounding_octaves=float(getattr(base, "sounding_octaves", 0.0)) - (int(note) - 60) / 12.0))
        return cache[(i, note)]
    return at


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

    # --- THE SC-8850's OTHER ACOUSTICS (2026-10-26) -------------------------
    (10, 1): ("Music Box 2", ("set", 10, dict(detuned_pair=(-5.0, 5.0)))),
    (10, 8): ("St.Music Box", ("set", 10, dict(key_pan_spread=WIDE))),
    (13, 8): ("Xylophone w", ("set", 13, dict(key_pan_spread=WIDE))),
    (14, 16): ("Tubularbellw", ("set", 14, dict(key_pan_spread=WIDE))),
    (15, 2): ("Santur 3", ("set", 15, dict(detuned_pair=(-9.0, 9.0), strike_point=1.0 / 9))),
    (32, 9): ("Atk A.Bass", ("set", 32, dict(strike_point=0.08))),
    (33, 5): ("Heart Bass", ("set", 33, dict(tonal_dampening=3.2))),
    (33, 6): ("AttackFinger", ("set", 33, dict(strike_point=0.08))),
    # double-picked: the picked bass tremolo-picked, eight strokes a second
    (34, 4): ("Double Pick", ("set", 34, dict(tremolo_pick_hz=8.0))),
    (37, 1): ("Slap Bass 3", ("set", 37, dict(tonal_dampening=1.6))),
    (44, 2): ("Trem Str.St.", ("set", 44, dict(key_pan_spread=WIDE))),
    (44, 10): ("SuspenseStr2", ("set", 44, dict(tonal_dampening=0.75, key_pan_spread=WIDE))),
    (45, 17): ("StringsSpic.", ("set", 48, dict(one_shot=True, gate_time=0.05, release_valve_time=0.12,
                                                attack_time=0.012, speech_cycles=0.0))),
    # the harp with the strings, wide; an Irish harp (brighter, ringing
    # longer); the yang qin again, struck nearer its end and doubled
    (46, 1): ("Harp&Strings", ("layer", ((46, 0, 0.0), (48, 0, -6.0)))),
    (46, 2): ("Harp St.", ("set", 46, dict(key_pan_spread=WIDE))),
    (46, 8): ("Uillean Harp", ("set", 46, dict(tonal_dampening=0.7))),
    (46, 25): ("Yang Qin 2", ("set", 15, dict(strike_point=1.0 / 9, tonal_dampening=0.55, detuned_pair=(-5.0, 5.0)))),
    (65, 17): ("Sax Section", ("layer", ((65, 0, 0.0), (66, 0, -3.0), (67, -12, -6.0)))),
    (67, 8): ("Bari & Tenor", ("layer", ((67, 0, 0.0), (66, 12, -4.0)))),
    (71, 17): ("Quad Wind", ("layer", ((73, 12, 0.0), (68, 0, -3.0), (71, 0, -3.0), (70, -12, -6.0)))),
    (73, 9): ("Pipe & Reed", ("layer", ((73, 0, 0.0), (68, 0, -4.0)))),
    # the bansuri: the flute darker and breathier
    (73, 17): ("Indian Flute", ("set", 73, dict(sound_bias={"brightness": -0.4, "vib_depth": 0.4}))),
    # the TIN WHISTLE: the recorder's fipple, brighter; plain; ornamented
    # (a quicker vibrato for its cuts and rolls)
    (75, 24): ("Tin Whistle", ("set", 74, dict(sound_bias={"brightness": 0.3}))),
    (75, 25): ("TinWhtsle Nm", ("alias", 74)),
    (75, 26): ("TinWhtsle Or", ("set", 74, dict(sound_bias={"brightness": 0.3, "vib_depth": 0.5, "vib_rate": 0.4}))),

    # --- THE SC-8850's ETHNIC TONES (2026-10-26) -----------------------------
    # the sitar's fourth: darker, its jawari softened
    (104, 5): ("Sitar 4", ("set", 104, dict(tonal_dampening=0.55))),

    # --- THE SC-8850's PERCUSSIVE TONES (2026-10-26) ---------------------------
    # the BALI sets' gamelan (54), each instrument from the keyboard
    (112, 13): ("Jegogan", ("kit", 50, 54)),
    (112, 14): ("Jublag", ("kit", 55, 54)),
    (112, 15): ("Pemade", ("kit", 67, 54)),
    (112, 17): ("Kajar", ("kit", 48, 54)),
    (112, 18): ("Kelontuk", ("kit", 40, 54)),
    (112, 19): ("Kelontuk Mt", ("kit", 41, 54)),
    (112, 20): ("Kelontuk Sid", ("kit", 42, 54)),
    (112, 21): ("Kopyak Op", ("kit", 46, 54)),
    (112, 22): ("Kopyak Mt", ("kit", 47, 54)),
    (112, 23): ("Ceng Ceng", ("kit", 45, 54)),
    (112, 24): ("Reyoung", ("kit", 77, 54)),
    (112, 25): ("Kempur", ("kit", 49, 54)),
    (116, 24): ("KendangWadon", ("kit", 36, 54)),
    (116, 25): ("Bebarongan", ("kit", 38, 54)),
    (116, 26): ("Pelegongan", ("kit", 39, 54)),
    # the Asia set's dholak; the jungle set's crash, kick roll and snare roll
    (116, 27): ("Dholak 1", ("kit", 89, 52)),
    (116, 28): ("Dholak 2", ("kit", 90, 52)),
    (112, 32): ("Jngl Crash", ("kit", 49, 10)),
    (116, 32): ("Jngl BD Roll", ("kit", 89, 10)),
    (117, 24): ("Jngl SD Roll", ("kit", 90, 10)),
    (116, 9): ("ConcertBD Mt", ("kit", 48, 51)),
    # the toms of the room, jazz and brush sets
    (117, 2): ("Real Tom 2", ("kit", 45, 8)),
    (117, 3): ("Jazz Tom", ("kit", 45, 32)),
    (117, 4): ("Brush Tom", ("kit", 45, 40)),
    (119, 3): ("Reverse Cym4", ("kit", 74, 62)),             # the jazz crash, reversed
    (119, 26): ("Rev.Tom 3", ("rev", 50, 0)),
    (119, 27): ("Rev.Tom 4", ("rev", 41, 0)),
    # THE MENUS: a different drum on each key, from C2 up (kit_menu) -- the
    # Kick & Snare sets' kicks and snares (50, 51), the cymbal and clap set's
    # (62), the reverse sets' (57-59), sorted by kind
    (116, 40): ("Kick Menu 1", ("menu", (("kit", 38, 50), ("kit", 39, 50), ("kit", 40, 50), ("kit", 41, 50), ("kit", 42, 50), ("kit", 43, 50), ("kit", 44, 50), ("kit", 45, 50), ("kit", 46, 50), ("kit", 47, 50), ("kit", 48, 50), ("kit", 49, 50), ("kit", 50, 50), ("kit", 51, 50), ("kit", 52, 50), ("kit", 53, 50),))),        # acoustic: standard, soft, jazz, concert, room, power
    (116, 41): ("Kick Menu 2", ("menu", (("kit", 25, 50), ("kit", 26, 50), ("kit", 27, 50), ("kit", 28, 50), ("kit", 29, 50), ("kit", 30, 50), ("kit", 31, 50), ("kit", 54, 50), ("kit", 55, 50), ("kit", 56, 50), ("kit", 57, 50), ("kit", 58, 50),))),        # the machines: CR-78, 606, 707, 808, 909, electric
    (116, 42): ("Kick Menu 3", ("menu", (("kit", 32, 50), ("kit", 33, 50), ("kit", 34, 50), ("kit", 35, 50), ("kit", 36, 50), ("kit", 37, 50), ("kit", 59, 50), ("kit", 55, 51), ("kit", 56, 51),))),        # hip-hop, jungle, techno, dance, fat
    (116, 43): ("Kick Menu 4", ("menu", (("kit", 42, 51), ("kit", 43, 51), ("kit", 44, 51), ("kit", 45, 51), ("kit", 46, 51), ("kit", 47, 51), ("kit", 48, 51), ("kit", 49, 51), ("kit", 50, 51), ("kit", 51, 51), ("kit", 52, 51), ("kit", 53, 51), ("kit", 54, 51),))),        # brush, jazz, concert mute, room, jungle, the roll
    (117, 40): ("SD Menu 1", ("menu", (("kit", 60, 50), ("kit", 61, 50), ("kit", 62, 50), ("kit", 63, 50), ("kit", 64, 50), ("kit", 65, 50), ("kit", 66, 50), ("kit", 67, 50), ("kit", 68, 50), ("kit", 69, 50), ("kit", 70, 50), ("kit", 71, 50), ("kit", 72, 50),))),          # acoustic: standard, tight, concert, jazz, room, power, gated
    (117, 41): ("SD Menu 2", ("menu", (("kit", 73, 50), ("kit", 74, 50), ("kit", 75, 50), ("kit", 76, 50), ("kit", 77, 50), ("kit", 78, 50), ("kit", 79, 50), ("kit", 80, 50), ("kit", 81, 50), ("kit", 82, 50), ("kit", 83, 50),))),          # dance, disco, electric, house, 808, 909
    (117, 42): ("SD Menu 3", ("menu", (("kit", 84, 50), ("kit", 85, 50), ("kit", 86, 50), ("kit", 87, 50), ("kit", 88, 50), ("kit", 89, 50), ("kit", 90, 50), ("kit", 91, 50),))),          # brush: taps, slaps, swirls
    (117, 43): ("SD Menu 4", ("menu", (("kit", 70, 51), ("kit", 71, 51), ("kit", 72, 51), ("kit", 73, 51), ("kit", 74, 51), ("kit", 75, 51), ("kit", 76, 51), ("kit", 77, 51), ("kit", 78, 51), ("kit", 79, 51), ("kit", 80, 51), ("kit", 81, 51), ("kit", 82, 51), ("kit", 83, 51),))),          # lo-fi, hip-hop, 606, techno, house, rock, jungle
    (117, 44): ("SD Menu 5", ("menu", (("kit", 92, 50), ("kit", 93, 50), ("kit", 94, 50), ("kit", 95, 50), ("kit", 96, 50), ("kit", 97, 50), ("kit", 98, 50), ("kit", 99, 50),))),          # standard, rap, hip-hop, jungle, techno
    (112, 40): ("Crash Menu", ("menu", (("kit", 58, 62), ("kit", 59, 62), ("kit", 60, 62), ("kit", 61, 62), ("kit", 62, 62), ("kit", 63, 62), ("kit", 64, 62), ("kit", 65, 62), ("kit", 66, 62), ("kit", 67, 62), ("kit", 68, 62), ("kit", 69, 62), ("kit", 70, 62), ("kit", 71, 62), ("kit", 76, 62), ("kit", 87, 62), ("kit", 88, 62),))),         # crashes, mutes, splash, china
    (112, 41): ("RideCym Menu", ("menu", (("kit", 81, 62), ("kit", 82, 62), ("kit", 83, 62), ("kit", 84, 62), ("kit", 85, 62), ("kit", 86, 62),))),
    (112, 42): ("RideBellMenu", ("menu", (("kit", 77, 62), ("kit", 78, 62), ("kit", 79, 62), ("kit", 80, 62),))),
    (115, 40): ("HandClapMenu", ("menu", (("kit", 89, 62), ("kit", 90, 62), ("kit", 91, 62), ("kit", 92, 62), ("kit", 93, 62), ("kit", 94, 62), ("kit", 95, 62), ("kit", 96, 62),))),
    (119, 40): ("Rev.SD Menu1", ("menu", (("kit", 56, 59), ("kit", 57, 59), ("kit", 58, 59), ("kit", 59, 59), ("kit", 60, 59), ("kit", 61, 59), ("kit", 62, 59), ("kit", 63, 59),))),       # standard, room, jazz, brush, reversed
    (119, 41): ("Rev.SD Menu2", ("menu", (("kit", 64, 59), ("kit", 65, 59), ("kit", 66, 59), ("kit", 67, 59), ("kit", 68, 59), ("kit", 69, 59), ("kit", 70, 59), ("kit", 71, 59), ("kit", 72, 59), ("kit", 73, 59), ("kit", 74, 59), ("kit", 75, 59), ("kit", 76, 59), ("kit", 77, 59), ("kit", 78, 59),))),       # lo-fi, hip-hop, house, jungle, 606, techno, dance, rock, rims
    (119, 42): ("Rev.SD Menu3", ("menu", (("kit", 41, 58), ("kit", 42, 58), ("kit", 43, 58), ("kit", 44, 58), ("kit", 45, 58), ("kit", 46, 58), ("kit", 47, 58), ("kit", 48, 58), ("kit", 49, 58), ("kit", 50, 58), ("kit", 51, 58), ("kit", 40, 57), ("kit", 41, 57), ("kit", 42, 57), ("kit", 43, 57), ("kit", 44, 57), ("kit", 45, 57),))),       # the machines' and the dance sets', reversed
    (119, 43): ("Rev.BD Menu1", ("menu", (("kit", 39, 59), ("kit", 40, 59), ("kit", 41, 59), ("kit", 42, 59), ("kit", 43, 59), ("kit", 44, 59), ("kit", 45, 59), ("kit", 46, 59),))),       # standard, room, jazz, brush
    (119, 44): ("Rev.BD Menu2", ("menu", (("kit", 47, 59), ("kit", 48, 59), ("kit", 49, 59), ("kit", 50, 59), ("kit", 51, 59), ("kit", 52, 59), ("kit", 53, 59), ("kit", 54, 59), ("kit", 55, 59),))),       # hip-hop, jungle, 808, 909, fat, dance
    (119, 45): ("Rev.BD Menu3", ("menu", (("kit", 36, 58), ("kit", 37, 58), ("kit", 38, 58), ("kit", 39, 58), ("kit", 40, 58), ("kit", 36, 57), ("kit", 37, 57), ("kit", 38, 57), ("kit", 39, 57),))),       # 707, 909, hip-hop, jungle, techno, concert, power, electric
    (119, 46): ("Rev.ClapMenu", ("menu", (("kit", 88, 59), ("kit", 89, 59), ("kit", 90, 59), ("kit", 91, 59), ("kit", 92, 59), ("kit", 95, 59),))),

    # --- THE SC-8850's SFX (2026-10-26): the SFX 2 set's (60) and the voice
    # set's (61) sounds from the keyboard; the guitar and breath menus
    (120, 16): ("A.Bs.Nz Menu", ("menu", (("kit", 31, 60), ("kit", 32, 60), ("kit", 33, 60), ("kit", 37, 56), ("kit", 50, 56),))),
    (120, 17): ("D.Gt.Nz Menu", ("menu", (("kit", 35, 56), ("kit", 36, 56), ("kit", 34, 60), ("kit", 24, 56),))),
    (120, 18): ("E.Gt.NzMenu1", ("menu", (("kit", 48, 56), ("kit", 49, 56), ("kit", 33, 56), ("kit", 34, 56), ("kit", 47, 56),))),
    (120, 19): ("E.Gt.NzMenu2", ("menu", (("kit", 39, 60), ("kit", 40, 60), ("kit", 41, 60), ("kit", 42, 60), ("kit", 43, 60),))),
    (120, 20): ("G.StrokeMenu", ("menu", (("kit", 26, 56), ("kit", 27, 56), ("kit", 39, 60), ("kit", 40, 60), ("kit", 41, 60), ("kit", 42, 60), ("kit", 43, 60),))),
    (120, 21): ("Gt.SlideMenu", ("menu", (("kit", 35, 60), ("kit", 36, 60), ("kit", 37, 60), ("kit", 38, 60), ("kit", 23, 56), ("kit", 47, 56),))),
    (120, 22): ("A.Bs.Mute Nz", ("kit", 31, 60)),
    (120, 23): ("A.Bs.TouchNz", ("kit", 32, 60)),
    (120, 24): ("A.Bs.AtackNz", ("kit", 33, 60)),
    # the Telecaster's cutting noises: the SFX set's, up and down, open and muted
    (120, 25): ("TC Up Nz", ("kit", 49, 56)),
    (120, 26): ("TC DownMt.Nz", ("kit", 34, 56)),
    (120, 27): ("TC UpMt.Nz", ("kit", 33, 56)),
    (120, 28): ("TC Down Nz", ("kit", 48, 56)),
    (120, 29): ("DstGT.Up Nz", ("kit", 35, 56)),
    (120, 30): ("DstGT.DwnNz1", ("kit", 36, 56)),
    (120, 31): ("DstGT.DwnNz2", ("rev", 25, 59)),          # the reverse set's down noise, the right way round
    (120, 32): ("DstGT.MuteNz", ("kit", 34, 60)),
    (120, 34): ("Gt.StrokeNz5", ("kit", 43, 60)),
    (120, 35): ("StlGt.SldNz1", ("kit", 35, 60)),
    (120, 36): ("StlGt.SldNz2", ("kit", 36, 60)),
    (120, 37): ("StlGt.SldNz3", ("kit", 37, 60)),
    (120, 38): ("StlGt.SldNz4", ("kit", 38, 60)),
    (120, 39): ("Gt.StrokeNz1", ("kit", 39, 60)),
    (120, 40): ("Gt.StrokeNz2", ("kit", 40, 60)),
    (120, 41): ("Gt.StrokeNz3", ("kit", 41, 60)),
    (120, 42): ("Gt.StrokeNz4", ("kit", 42, 60)),
    (121, 2): ("Brth Nz Menu", ("menu", (("kit", 54, 61), ("kit", 55, 61), ("kit", 56, 61), ("kit", 57, 61), ("kit", 58, 61),))),
    (121, 3): ("Fl.Breath 1", ("kit", 54, 61)),
    (121, 4): ("Fl.Breath 2", ("kit", 55, 61)),
    (121, 5): ("Fl.Breath 3", ("kit", 56, 61)),
    (121, 6): ("Vox Breath 1", ("kit", 57, 61)),
    (121, 7): ("Vox Breath 2", ("kit", 58, 61)),
    # the brass noises: only their reverses are in a set (59) -- played
    # backwards, they are the right way round
    (121, 8): ("Trombone Nz", ("rev", 37, 59)),
    (121, 9): ("Trumpet Nz", ("rev", 38, 59)),
    (122, 7): ("Cricket", ("kit", 78, 60)),
    (123, 6): ("Growl 2", ("kit", 79, 60)),                  # the SFX 2 set's bear
    (123, 7): ("Fancy Animal", ("kit", 77, 60)),
    (123, 8): ("Seal", ("kit", 76, 60)),
    (124, 12): ("Scratch 3", ("kit", 82, 60)),
    (124, 13): ("Scratch 4", ("kit", 83, 60)),
    (124, 14): ("Scratch 5", ("kit", 84, 60)),
    (124, 15): ("Scratch 6", ("kit", 85, 60)),
    (124, 16): ("Scratch 7", ("kit", 86, 60)),
    (125, 13): ("Glass & Glam", ("kit", 58, 60)),           # the glass stir
    (125, 14): ("Ice Ring", ("kit", 59, 60)),
    (125, 15): ("Over Blow", ("kit", 68, 60)),
    (125, 16): ("Crack Bottle", ("kit", 60, 60)),
    (125, 17): ("Pour Bottle", ("kit", 61, 60)),
    (125, 18): ("Soda", ("kit", 62, 60)),
    (125, 19): ("Open CD Tray", ("kit", 44, 60)),
    (125, 20): ("Audio Switch", ("kit", 45, 60)),
    (125, 21): ("Key Typing", ("menu", (("kit", 46, 60), ("kit", 47, 60), ("kit", 48, 60), ("kit", 49, 60), ("kit", 50, 60), ("kit", 51, 60),))),     # a key each: the six typings
    (125, 22): ("SL 1", ("kit", 66, 60)),
    (125, 23): ("SL 2", ("kit", 67, 60)),
    (125, 24): ("Car Engine 2", ("kit", 63, 60)),
    (125, 25): ("Car Horn", ("kit", 64, 60)),
    (125, 26): ("Boeeeen", ("kit", 57, 60)),
    (125, 27): ("R.Crossing", ("kit", 65, 60)),
    (125, 28): ("Compresser", ("kit", 73, 60)),
    (125, 29): ("Sword Boom!", ("kit", 69, 60)),
    (125, 30): ("Sword Cross", ("kit", 70, 60)),
    (125, 31): ("Stab! 1", ("kit", 54, 60)),
    (125, 32): ("Stab! 2", ("kit", 55, 60)),
    (126, 9): ("BabyLaughing", ("kit", 52, 60)),
    (126, 22): ("Voice Kikit", ("kit", 64, 61)),
    (126, 23): ("Voice ComeOn", ("kit", 63, 61)),
    (126, 24): ("Voice Aou", ("kit", 65, 61)),
    (126, 25): ("Voice Oou", ("kit", 66, 61)),
    (126, 26): ("Voice Hie", ("kit", 70, 61)),
    (127, 6): ("Explosion 2", ("kit", 75, 60)),

    # --- THE SC-8850's OTHER GUITARS (2026-10-26) ---------------------------
    (25, 10): ("Atk Steel Gt", ("set", 25, dict(tonal_dampening=0.55))),
    (27, 5): ("Atk CleanGt.", ("set", 27, dict(strike_point=0.11))),
    (27, 20): ("LP Rear Pick", ("set", 27, dict(pickup_points=(0.049, 0.077)))),
    (27, 21): ("LP Rear 2", ("set", 27, dict(pickup_points=(0.049, 0.077), amp_drive=1.2))),
    (27, 22): ("LP RearAtack", ("set", 27, dict(pickup_points=(0.049, 0.077), strike_point=0.11))),
    # the zhongruan: the moon-bodied Chinese lute, picked -- the steel guitar
    # mellower, and tremolo-picked as it often is
    (27, 24): ("Chung Ruan", ("set", 25, dict(tonal_dampening=1.0))),
    (27, 25): ("Chung Ruan 2", ("set", 25, dict(tonal_dampening=1.0, tremolo_pick_hz=10.0))),
    (29, 5): ("Attack Drive", ("set", 29, dict(strike_point=0.12))),
    (29, 10): ("LP Half Drv", ("set", 29, dict(pickup_points=(0.049, 0.077), amp_drive=2.5))),
    (29, 11): ("LP Half Drv2", ("set", 29, dict(pickup_points=(0.21, 0.24), amp_drive=2.5))),
    (29, 12): ("LP Chorus", ("set", 29, dict(pickup_points=(0.049, 0.077), amp_drive=2.5, insertion_efx=((0x01, 0x42), {})))),
    (30, 5): ("Attack Dist", ("set", 30, dict(strike_point=0.12))),

    # --- THE SC-8850's OTHER KEYBOARDS (2026-10-26) -------------------------
    # the upright as GS 0.1 names it; the grand with a softer hammer (its
    # felt's contact low-pass at 0.75, Piano 1d's at 0.6), and wide
    (0, 1): ("UprightPiano", ("alias", 1)),
    (0, 2): ("Mild Piano", ("set", 0, dict(hammer_corner_hz=0.75 * 3542.03))),
    (0, 9): ("Mild Piano w", ("set", 0, dict(hammer_corner_hz=0.75 * 3542.03, key_pan_spread=WIDE))),
    # the piano with the strings, the choir, the oohs
    (0, 25): ("Piano + Str2", ("layer", ((0, 0, 0.0), (48, 0, -3.0)))),
    (0, 26): ("Piano+Choir1", ("layer", ((0, 0, 0.0), (52, 0, -6.0)))),
    (0, 27): ("Piano+Choir2", ("layer", ((0, 0, 0.0), (53, 0, -5.0)))),
    # the upright played pop (a harder hammer: its corner up) and rock (harder
    # still, through the overdrive), and wide
    (1, 1): ("Pop Piano", ("set", 1, dict(hammer_corner_hz=1.6 * 189.3))),
    (1, 2): ("Rock Piano", ("set", 1, dict(hammer_corner_hz=2.2 * 189.3, insertion_efx=((0x01, 0x10), {})))),
    (1, 9): ("Rock Piano w", ("set", 1, dict(hammer_corner_hz=2.2 * 189.3, key_pan_spread=WIDE,
                                             insertion_efx=((0x01, 0x10), {})))),
    # the Wurlitzer harder, and two a few cents apart
    (5, 1): ("E.Piano 3", ("set", 5, dict(pickup_deflection=1.2))),
    (5, 9): ("Detuned EP 3", ("set", 5, dict(detuned_pair=(-8.0, 8.0)))),
    # the harpsichord's two 8's
    (6, 2): ("Harpsichord3", ("set", 6, dict(default_stops=0b11))),
    # the clavinet: its bridge pickup; the attack harder (the strike's noise
    # and the hammer's chiff up), harder again; through the phaser
    (7, 1): ("Clav. 2", ("set", 7, dict(clav_pickup="bridge"))),
    (7, 2): ("Atk Clav.1", ("set", 7, dict(chiff_volume=1.0, strike_noise_slope=2.0))),
    (7, 3): ("Atk Clav.2", ("set", 7, dict(chiff_volume=1.4, strike_noise_slope=2.6, clav_pickup="bridge"))),
    (7, 17): ("Phase Clav", ("set", 7, dict(insertion_efx=((0x01, 0x20), {})))),

    # --- THE SC-8850's OTHER ORGANS (2026-10-26) ----------------------------
    # FULL ORGANS: nine full registrations, from the foundations up to all
    # nine, each a player's different full sound
    (16, 2): ("Ful Organ 1", ("set", 16, dict(default_stops=0b000001111))),     # 16' 5 1/3' 8' 4'
    (16, 3): ("Ful Organ 2", ("set", 16, dict(default_stops=0b000111111))),     # ...and 2 2/3' 2'
    (16, 4): ("Ful Organ 3", ("set", 16, dict(default_stops=0b110101111))),     # 16 5 8 4 2, 1 1/3' 1'
    (16, 5): ("Ful Organ 4", ("set", 16, dict(default_stops=0b101111101))),     # 16' 8' 4' 2 2/3' 2' 1 3/5' 1'
    (16, 6): ("Ful Organ 5", ("set", 16, dict(default_stops=0b111111101))),     # all but 5 1/3'
    (16, 7): ("Ful Organ 6", ("set", 16, dict(default_stops=0b011111111))),     # all but 1'
    (16, 10): ("Ful Organ 7", ("set", 16, dict(default_stops=0b111100111))),    # 888 and the top three
    (16, 11): ("Ful Organ 8", ("set", 16, dict(default_stops=0b111111011))),    # all but 8'
    (16, 12): ("Ful Organ 9", ("set", 16, dict(default_stops=0b111111111, amp_drive=1.0))),   # all nine, driven
    # an FM organ (sines: 16' 8' 4')
    (16, 31): ("FM Organ", ("set", 16, dict(default_stops=0b001101))),
    # JAZZ: 888 with the third-harmonic percussion, then 888 and 4', 16' 8'
    # alone, all three of the upper, the second harmonic's percussion
    (17, 3): ("Jazz Organ 2", ("set", 17, dict(default_stops=0b100000000111))),
    (17, 4): ("Jazz Organ 3", ("set", 17, dict(default_stops=0b100000001111))),
    (17, 5): ("Jazz Organ 4", ("set", 17, dict(default_stops=0b100000000101))),
    (17, 6): ("Jazz Organ 5", ("set", 17, dict(default_stops=0b100111000111))),
    (17, 7): ("Jazz Organ 6", ("set", 17, dict(default_stops=0b1000000000111))),
    # PERCUSSIVE: the percussion on other registrations
    (17, 33): ("Perc.Organ 2", ("set", 17, dict(default_stops=0b100000000101))),
    (17, 34): ("Perc.Organ 3", ("set", 17, dict(default_stops=0b1000000101100))),
    (17, 35): ("Perc.Organ 4", ("set", 17, dict(default_stops=0b100100101101))),
    # the BLUES HARP: the harmonica cupped and pushed (its reeds' edge up,
    # darker) and its second, supplementary take brighter
    (22, 8): ("B.Harp Basic", ("set", 22, dict(reed_edge=0.0115, tonal_dampening=2.3))),
    (22, 9): ("B.Harp Suppl", ("set", 22, dict(reed_edge=0.0135, tonal_dampening=1.8))),

    # --- THE SC-8850's OTHER BRASS (2026-10-26) -----------------------------
    # the trumpet with its breath (GM 121's) under it; warmer than Warm Tp.;
    # two trumpets apart
    (56, 4): ("Trumpet & Nz", ("layer", ((56, 0, 0.0), (121, 0, -14.0)))),
    (56, 26): ("Warm Tp.2", ("set", 56, dict(blare_db_per_khz=-9.0, blare_knee_hz=150, blare_cap_db=36.0))),
    (56, 27): ("Twin Tp.", ("set", 56, dict(detuned_pair=(-6.0, 6.0)))),
    # trombones with a tuba under them; the euphonium, a tenor tuba (the
    # conical bore, an octave up, brighter)
    (57, 3): ("Bones & Tuba", ("layer", ((57, 0, 0.0), (58, -12, -4.0)))),
    (57, 16): ("Euphonium", ("set", 58, dict(blare_db_per_khz=6.0, blare_knee_hz=300, blare_cap_db=22.0))),
    (58, 8): ("Tuba + Horn", ("layer", ((58, 0, 0.0), (60, 12, -6.0)))),
    # MUTES: GM 59 is the harmon (its nasal 2.5 kHz); a CUP mute is mellower,
    # its peak lower and the top cut; a STRAIGHT mute between them
    (59, 1): ("Cup Mute Tp", ("set", 59, dict(mute_resonance_hz=1200.0, mute_resonance_db=4.0, mute_resonance_q=1.0,
                                              mute_response=tuple((h, d - (6.0 if h >= 2000 else 0.0))
                                                                  for h, d in _TL.MutedTrumpetProperties.mute_response)))),
    (59, 3): ("MuteTrumpet3", ("set", 59, dict(mute_resonance_hz=1800.0, mute_resonance_db=8.0, mute_resonance_q=1.6))),
    # the section: ff in stereo; four sections' worth (trumpets over,
    # trombones, tuba under), two voicings; a second sforzando; fat pop brass
    # (the trumpets and an alto under it), with reeds; orchestral brass (horns,
    # trombones, tuba; then the trumpets over), each in stereo too
    (61, 3): ("St. Brass ff", ("set", 61, dict(blare_db_per_khz=9.0, blare_knee_hz=700, blare_cap_db=28.0,
                                                key_pan_spread=WIDE))),
    (61, 4): ("Quad Brass1", ("layer", ((61, 0, 0.0), (56, 12, -6.0), (57, 0, -4.0), (58, -12, -8.0)))),
    (61, 5): ("Quad Brass2", ("layer", ((61, 0, 0.0), (56, 0, -3.0), (60, 0, -5.0), (58, -12, -9.0)))),
    (61, 12): ("Brass sfz 2", ("layer", ((("set", 61, dict(one_shot=True, gate_time=0.1)), 0, 6.0), (61, 0, -9.0)))),
    (61, 14): ("FatPop Brass", ("layer", ((61, 0, 0.0), (56, 0, -4.0), (65, 0, -8.0)))),
    (61, 26): ("Fat + Reed", ("layer", ((61, 0, 0.0), (65, 0, -2.0), (66, -12, -6.0)))),
    (61, 32): ("Orch Brass", ("layer", ((60, 0, 0.0), (57, 0, -3.0), (58, -12, -8.0)))),
    (61, 33): ("Orch Brass 2", ("layer", ((60, 0, 0.0), (57, 0, -3.0), (58, -12, -8.0), (56, 12, -6.0)))),
    (61, 35): ("St.FatPopBrs", ("layer", ((("set", 61, dict(key_pan_spread=WIDE)), 0, 0.0), (("set", 56, dict(key_pan_spread=WIDE)), 0, -4.0), (("set", 65, dict(key_pan_spread=WIDE)), 0, -8.0)))),
    (61, 36): ("St.Orch Brs", ("layer", ((("set", 60, dict(key_pan_spread=WIDE)), 0, 0.0), (("set", 57, dict(key_pan_spread=WIDE)), 0, -3.0), (("set", 58, dict(key_pan_spread=WIDE)), -12, -8.0)))),
    (61, 37): ("St.Orch Brs2", ("layer", ((("set", 60, dict(key_pan_spread=WIDE)), 0, 0.0), (("set", 57, dict(key_pan_spread=WIDE)), 0, -3.0), (("set", 58, dict(key_pan_spread=WIDE)), -12, -8.0), (("set", 56, dict(key_pan_spread=WIDE)), 12, -6.0)))),
    (61, 38): ("St.Orch Brs3", ("layer", ((("set", 60, dict(key_pan_spread=WIDE)), 0, 0.0), (("set", 57, dict(key_pan_spread=WIDE)), 0, -2.0), (("set", 58, dict(key_pan_spread=WIDE)), -12, -6.0), (("set", 56, dict(key_pan_spread=WIDE)), 12, -4.0)))),

    # --- THE SC-8850's OTHER ENSEMBLES (2026-10-26) --------------------------
    # strings brighter (Bright Str's corner further up), mild (darker), four
    # sections' worth (many players, wide), stereo ones further apart, and
    # the double basses alone
    (48, 4): ("Bright Str.2", ("set", 48, dict(bore_corner_hz=5500.0))),
    (48, 5): ("Bright Str.3", ("set", 48, dict(bore_corner_hz=6500.0, tonal_dampening=0.9))),
    (48, 6): ("Quad Strings", ("set", 48, dict(section_players=14, key_pan_spread=WIDE))),
    (48, 7): ("Mild Strings", ("set", 48, dict(bore_corner_hz=2600.0))),
    (48, 17): ("St.Strings 2", ("set", 48, dict(key_pan_spread=0.75))),
    (48, 18): ("St.Strings 3", ("set", 48, dict(key_pan_spread=1.0, section_players=10))),
    (48, 34): ("ContraBsSect", ("set", 43, dict(section_players=4, section_spread_cents=6.0))),
    # strings with: the flute over them; the choir, more of it, then most
    (48, 13): ("Str.+Flute", ("layer", ((48, 0, 0.0), (73, 12, -8.0)))),
    (48, 14): ("Choir Str.2", ("layer", ((48, 0, 0.0), (52, 0, -2.0)))),
    (48, 15): ("Choir Str.3", ("layer", ((48, 0, -2.0), (52, 0, 0.0)))),
    # orchestras: the strings with the brass a fifth under its octave (Orch
    # 3), with the woodwinds (Orch 4)
    (48, 19): ("Orchestra 3", ("layer", ((48, 0, 0.0), (61, 0, -8.0), (60, 0, -10.0)))),
    (48, 20): ("Orchestra 4", ("layer", ((48, 0, 0.0), (61, 12, -10.0), (71, 12, -10.0)))),
    # slow strings: darker; stereo wider; with the choir, twice
    (49, 2): ("SlowStrings3", ("set", 49, dict(bore_corner_hz=2600.0))),
    (49, 11): ("St.Slow Str2", ("set", 49, dict(key_pan_spread=0.75))),
    (49, 12): ("S.Str+Choir", ("layer", ((49, 0, 0.0), (52, 0, -4.0)))),
    (49, 13): ("S.Str+Choir2", ("layer", ((49, 0, -2.0), (52, 0, 0.0)))),
    # boys' choirs: a TREBLE's body (tonelib.VOICE_BODIES 'boy': a shorter
    # tract, formants 1.20x -- not a woman's, as the Lacrimosa's --parts=treble
    # sings it), the tone declaring the part a file would; fewer, brighter;
    # stereo; then a rich choir
    (52, 11): ("Boys Choir 1", ("set", 52, dict(voice_part='boy', section_players=8, bore_corner_hz=13500.0))),
    (52, 12): ("Boys Choir 2", ("set", 52, dict(voice_part='boy', section_players=6, bore_corner_hz=14000.0,
                                                tonal_dampening=1.3))),
    (52, 13): ("St.BoysChoir", ("set", 52, dict(voice_part='boy', section_players=8, key_pan_spread=WIDE))),
    (52, 14): ("Rich Choir", ("set", 52, dict(section_players=14, key_pan_spread=WIDE, tonal_dampening=1.35))),
    # oohs: a chorus (more), the voice's second, the chorus's
    (53, 1): ("Chorus Oohs", ("set", 53, dict(section_players=10))),
    (53, 2): ("Voice Oohs 2", ("set", 53, dict(tonal_dampening=1.3))),
    (53, 3): ("Chorus Oohs2", ("set", 53, dict(section_players=10, key_pan_spread=WIDE))),
    # chords on one key: the oohs as a major seventh, as a suspended fourth
    (53, 4): ("OohsCodeMaj7", ("layer", ((53, 0, 0.0), (53, 4, -2.0), (53, 7, -2.0), (53, 11, -3.0)))),
    (53, 5): ("OohsCodeSus4", ("layer", ((53, 0, 0.0), (53, 5, -2.0), (53, 7, -2.0)))),
    # scat: the voice's plosive syllables, quick and short -- "dat" and "bap"
    # cut off, "dow" open, "thum" a hum
    (53, 6): ("Jazz Scat", ("set", 53, dict(formants=__import__("vowels").VOWELS["a"], section_players=1,
                                            chiff_min_valve_time=0.012, chiff_max_valve_time=0.025))),
    (53, 9): ("JzVoice Dat", ("set", 53, dict(formants=__import__("vowels").VOWELS["a"], section_players=1,
                                              one_shot=True, gate_time=0.14, chiff_min_valve_time=0.01,
                                              chiff_max_valve_time=0.02))),
    (53, 10): ("JzVoice Bap", ("set", 53, dict(formants=__import__("vowels").VOWELS["a"], section_players=1,
                                               one_shot=True, gate_time=0.13, chiff_min_valve_time=0.008,
                                               chiff_max_valve_time=0.018))),
    (53, 11): ("JzVoice Dow", ("set", 53, dict(formants=__import__("vowels").VOWELS["o"], section_players=1,
                                               chiff_min_valve_time=0.012, chiff_max_valve_time=0.025))),
    (53, 12): ("JzVoice Thum", ("set", 53, dict(formants=__import__("vowels").VOWELS["V"], section_players=1,
                                                bore_corner_hz=1800.0, chiff_min_valve_time=0.02,
                                                chiff_max_valve_time=0.04))),
    # THE SYLLABLES (a woman's voice and her chorus, then a man's): lah, luh,
    # lan on their vowels, aah, uuh, wah, woh, ooh -- the liquid's or glide's
    # slower onset; the sex rule pinned. A vowel that moves (lan's n, wah's
    # u-a) is held on its main vowel: a note's formants do not move here
    (53, 16): ("VoiceLah Fem", ("set", 53, dict(formants=__import__("vowels").VOWELS["a"], voice_crossover_hz=20.0,
                                                section_players=1, chiff_min_valve_time=0.03, chiff_max_valve_time=0.05))),
    (53, 17): ("ChorusLahFem", ("set", 53, dict(formants=__import__("vowels").VOWELS["a"], voice_crossover_hz=20.0,
                                                section_players=8, chiff_min_valve_time=0.03, chiff_max_valve_time=0.05))),
    (53, 18): ("VoiceLuh Fem", ("set", 53, dict(formants=__import__("vowels").VOWELS["V"], voice_crossover_hz=20.0,
                                                section_players=1, chiff_min_valve_time=0.03, chiff_max_valve_time=0.05))),
    (53, 19): ("ChorusLuhFem", ("set", 53, dict(formants=__import__("vowels").VOWELS["V"], voice_crossover_hz=20.0,
                                                section_players=8, chiff_min_valve_time=0.03, chiff_max_valve_time=0.05))),
    (53, 20): ("VoiceLan Fem", ("set", 53, dict(formants=__import__("vowels").VOWELS["A"], voice_crossover_hz=20.0,
                                                section_players=1, chiff_min_valve_time=0.03, chiff_max_valve_time=0.05))),
    (53, 21): ("ChorusLanFem", ("set", 53, dict(formants=__import__("vowels").VOWELS["A"], voice_crossover_hz=20.0,
                                                section_players=8, chiff_min_valve_time=0.03, chiff_max_valve_time=0.05))),
    (53, 22): ("VoiceAah Fem", ("set", 53, dict(formants=__import__("vowels").VOWELS["a"], voice_crossover_hz=20.0,
                                                section_players=1))),
    (53, 23): ("VoiceUuh Fem", ("set", 53, dict(formants=__import__("vowels").VOWELS["u"], voice_crossover_hz=20.0,
                                                section_players=1))),
    (53, 24): ("Fem Lah&Lan", ("layer", ((("set", 53, dict(formants=__import__("vowels").VOWELS["a"],
                                                           voice_crossover_hz=20.0, section_players=1)), 0, 0.0),
                                         (("set", 53, dict(formants=__import__("vowels").VOWELS["A"],
                                                           voice_crossover_hz=20.0, section_players=1)), 0, -2.0)))),
    (53, 32): ("VoiceWah Mal", ("set", 53, dict(formants=__import__("vowels").VOWELS["a"], voice_crossover_hz=20000.0,
                                                section_players=1, chiff_min_valve_time=0.05, chiff_max_valve_time=0.08))),
    (53, 33): ("ChorusWahMal", ("set", 53, dict(formants=__import__("vowels").VOWELS["a"], voice_crossover_hz=20000.0,
                                                section_players=8, chiff_min_valve_time=0.05, chiff_max_valve_time=0.08))),
    (53, 34): ("VoiceWoh Mal", ("set", 53, dict(formants=__import__("vowels").VOWELS["o"], voice_crossover_hz=20000.0,
                                                section_players=1, chiff_min_valve_time=0.05, chiff_max_valve_time=0.08))),
    (53, 35): ("ChorusWohMal", ("set", 53, dict(formants=__import__("vowels").VOWELS["o"], voice_crossover_hz=20000.0,
                                                section_players=8, chiff_min_valve_time=0.05, chiff_max_valve_time=0.08))),
    (53, 36): ("VoiceAah Mal", ("set", 53, dict(formants=__import__("vowels").VOWELS["a"], voice_crossover_hz=20000.0,
                                                section_players=1))),
    (53, 37): ("VoiceOoh Mal", ("set", 53, dict(voice_crossover_hz=20000.0, section_players=1))),
    # hits SFX 2 names too: its bounce, drill, thrill, industry and clap
    # hits, as there (percussion_gs: the bounce, the machine gun's burst, the
    # orchestra hit a whole step down, the car crash, the percussion bang)
    (55, 13): ("Bounce Hit", ("layer", ((55, 0, -4.0), (("kit", 56, 60), 0, 0.0)))),
    (55, 14): ("Drill Hit", ("layer", ((55, 0, -4.0), (("kit", 72, 60), 0, 0.0)))),
    (55, 15): ("Thrill Hit", ("layer", ((55, -2, 0.0), (55, 10, -6.0)))),
    (55, 26): ("Industry Hit", ("layer", ((55, 0, -2.0), (("kit", 71, 60), 0, 0.0)))),
    (55, 27): ("Clap Hit", ("layer", ((55, 0, 0.0), (("kit", 39, 0), 0, 2.0)))),
}

for _cheap, _tag in ((SC88_CHEAP, "sc88"), (SC8850_CHEAP, "sc8850")):
    for (_p, _b), (_nm, _how) in _cheap.items():
        VARIATION_NAMES[(_p, _b)] = _nm
        if _how[0] == "layer":
            LAYERED[(_p, _b)] = _how[1]
            # (a first layer with settings -- ("set", program, {...}) -- is that
            # program's voice with them, as BreathyTnr.'s is)
            _l0 = _how[1][0][0]
            VARIATIONS[(_p, _b)] = (routed_variation(_l0[1], "%s_%d_%d" % (_tag, _p, _b), **_l0[2])
                                    if isinstance(_l0, tuple) and _l0[0] == "set"
                                    else routed_variation(_l0, "%s_%d_%d" % (_tag, _p, _b)))
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

# THE SYNTH PROGRAMS' LAYERED TONES (2026-10-26; Ben: "build the layered
# tones"): an acoustic voice of ours under a synth panel's, or two of ours --
# each name's two halves, the second layer's level under the first's.
# Starting points for the ear, as the synth tables' are; the angklung (no
# voice of its own here) is the marimba's struck bamboo.
from tonelib import TambraProperties as _TMB
_SYN_LAYERED = {
    # strings and brass sections with their synth twins
    (50, 17): ("Hybrid Str.", ((48, 0, 0.0), (50, 0, -4.0))),
    (51, 5): ("Hybrid Str.2", ((48, 0, 0.0), (51, 0, -3.0))),
    (62, 10): ("OrchSynBrass", ((61, 0, 0.0), (62, 0, -3.0))),
    (62, 17): ("Hybrid Brass", ((62, 0, 0.0), (61, 0, -2.0))),
    # struck and blown things over pads: bamboo (the marimba) on the choir pad,
    # the steel pan on the bowed glass and the metal pad, a blown bottle
    # stacked on the bowed pad, the angklung on the rain pad
    (91, 7): ("Bamboo Hit", ((12, 0, 0.0), (91, 0, -6.0))),
    (92, 4): ("Steel Glass", ((114, 0, 0.0), (92, 0, -6.0))),
    (92, 5): ("Bottle Stack", ((76, 0, 0.0), (76, 12, -6.0), (92, 0, -8.0))),
    (93, 3): ("Steel Pad", ((93, 0, 0.0), (114, 0, -4.0))),
    (96, 3): ("Anklung Pad", ((12, 12, 0.0), (96, 0, -6.0))),
    # a shaker over the rain pad
    (96, 4): ("Rattle Pad", ((96, 0, 0.0), (("kit", 82, 9), 0, -6.0))),
    # keyboards over the warm pad: the Rhodes, the CP-70 (electric grand),
    # the piano with the atmosphere's noise
    (96, 9): ("EP Pad", ((4, 0, 0.0), (89, 0, -8.0))),
    (96, 11): ("CP Pad", ((2, 0, 0.0), (89, 0, -8.0))),
    (99, 9): ("Noise Piano", ((0, 0, 0.0), (99, 0, -10.0))),
    # the tambura's drone under a pad and an atmosphere
    (96, 10): ("Tambra Pad", ((("class", _TMB), 0, 0.0), (89, 0, -6.0))),
    (99, 11): ("Tambra Atmos", ((("class", _TMB), 0, 0.0), (99, 0, -6.0))),
    # pizzicato with a bell on it; an organ with a bell
    (98, 22): ("Pizz Bell", ((45, 0, 0.0), (98, 0, -6.0))),
    (100, 8): ("Org Bell", ((16, 0, 0.0), (98, 0, -4.0))),
    # a choir struck as the orchestra hit is: the hit's punch, the choir
    (100, 4): ("Choir Stab", ((55, 0, 0.0), (52, 0, -2.0))),
    # water poured (the bubbles, rising) under the crystal's sparkle; a drill
    # (SFX 2's) over the goblins
    (101, 26): ("Pour Magic", ((("kit", 61, 60), 0, 0.0), (98, 12, -6.0))),
    (101, 27): ("DancingDrill", ((("kit", 72, 60), 0, 0.0), (101, 0, -6.0))),
    # the sitar over the tambura's drone (SC-8850); the oud with strings, the
    # kanun with a choir (SC-88 Pro)
    (104, 4): ("Sitar/Drone", ((104, 0, 0.0), (("class", TambouraProperties), 0, -8.0))),
    (105, 28): ("Oud+Strings", ((("class", _TL.OudProperties), 0, 0.0), (48, 0, -6.0))),
    (107, 19): ("Kanoon+Choir", ((("class", _TL.KanunProperties), 0, 0.0), (52, 0, -8.0))),
    # the PI PA: a pear-shaped lute, frets high, plucked with nails near the
    # bridge -- the oud, brighter, nearer the bridge, its courses single
    (105, 32): ("Pi Pa", ((("class", type("PipaProperties", (_TL.OudProperties,), dict(
        strike_point=0.07, tonal_dampening=0.4, course_partner_gain=0.0))), 0, 0.0),)),
}
for (_p, _b), (_nm, _ly) in _SYN_LAYERED.items():
    LAYERED[(_p, _b)] = _ly
    _s0 = _ly[0][0]
    VARIATIONS[(_p, _b)] = (_s0[1] if isinstance(_s0, tuple) and _s0[0] == "class" else
                            melodic_sfx(_s0[1], kit=_s0[2]) if isinstance(_s0, tuple) else
                            property_class_for_program(_s0))
    VARIATION_NAMES[(_p, _b)] = _nm
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
for (_p, _b), _e in SC8850_SYNTH.items():
    _nm, _base, _pan = _e[:3]
    _B = getattr(_TL, _base)
    _k = 128 * 4 + _b if (_p, _b) in MAP_OTHER.get(4, ()) else _b
    # (a panel's class attributes out of its knobs, as SC88_SYNTH's: the
    # insertion effect the tone carries, the key's pan spread)
    _ck = ("key_pan_spread", "insertion_efx")
    VARIATIONS[(_p, _k)] = type("Sc8850_%d_%d" % (_p, _b), (_B,),
                                dict(messenger=dict(_B.messenger, **{k: v for k, v in _pan.items() if k not in _ck}),
                                     **{k: _pan[k] for k in _ck if k in _pan},
                                     **(_e[3] if len(_e) > 3 else {})))
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
    # the SC-88 Pro's Synth Horn where ours is Horn Orch: the synth brass
    (3, 60, 16): ("Synth Horn", ("alias", 62)),
    # the SC-88 Pro's Organ. o where ours is Organ 109: the organ and its octave
    (3, 16, 9): ("Organ. o", ("layer", ((16, 0, 0.0), (16, 12, -6.0)))),
    # ...and its Jazz Organ where ours is Organ 201: 888 and the third-
    # harmonic percussion, Jimmy Smith's
    (3, 17, 1): ("Jazz Organ", ("set", 17, {"default_stops": 0b100000000111})),
    # the SC-8850's wide upright and wide pop piano where ours are Piano 1w / 2w
    (4, 0, 8): ("Upright P w", ("set", 1, {"key_pan_spread": WIDE})),
    (4, 1, 8): ("Pop Piano w", ("set", 1, {"hammer_corner_hz": 1.6 * 189.3, "key_pan_spread": WIDE})),
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
VARIATION_TRIM_FIT = {(0, 1): 8.4, (0, 2): 0.1, (0, 8): 0.0, (0, 9): 0.1, (0, 16): 0.2, (0, 24): 0.3, (0, 25): 0.3, (0, 26): -0.6, (0, 27): -2.3, (0, 520): 8.4, (1, 1): 6.1, (1, 2): -3.6, (1, 8): 8.2, (1, 9): -3.6, (1, 520): 6.1, (2, 1): -1.3, (2, 2): -2.8, (2, 8): 1.9, (3, 8): 7.3, (3, 136): 9.6, (4, 8): 0.6, (4, 9): -1.8, (4, 10): 7.4, (4, 16): -7.4, (4, 17): -20.3, (4, 24): -4.5, (4, 144): -2.1, (4, 264): -2.0, (5, 1): -6.5, (5, 8): -2.4, (5, 9): -5.6, (5, 16): -5.3, (5, 32): 4.1, (5, 144): -5.6, (6, 1): -11.8, (6, 2): -12.4, (6, 8): -11.9, (6, 16): -10.9, (6, 24): -12.5, (6, 32): 0.0, (7, 1): -1.1, (7, 2): -2.8, (7, 3): -1.1, (7, 8): -1.1, (7, 16): 9.4, (7, 17): 4.4, (7, 24): -5.0, (7, 32): -0.6, (7, 36): -2.6, (7, 37): -27.0, (7, 38): 5.0, (8, 1): -2.1, (10, 1): 8.2, (10, 8): 8.6, (11, 8): 2.3, (11, 9): 2.2, (12, 8): 2.9, (13, 8): 1.4, (14, 8): -2.6, (14, 9): -1.9, (14, 10): -5.0, (14, 16): 1.4, (15, 1): 4.2, (15, 2): 4.3, (15, 16): -2.3, (15, 17): -4.4, (15, 24): 3.6, (16, 1): -7.4, (16, 2): -7.7, (16, 3): -8.7, (16, 4): -10.7, (16, 5): -10.4, (16, 6): -12.1, (16, 7): -12.0, (16, 8): -4.4, (16, 9): -6.0, (16, 10): -12.0, (16, 11): -17.1, (16, 12): -14.4, (16, 16): -5.5, (16, 17): -5.7, (16, 18): -9.6, (16, 19): -6.7, (16, 25): -2.1, (16, 26): -3.5, (16, 27): -7.0, (16, 28): -1.5, (16, 29): -5.2, (16, 30): -1.4, (16, 31): -7.3, (16, 32): -10.1, (16, 33): -7.7, (16, 40): -6.9, (16, 48): -8.1, (16, 393): -5.6, (17, 1): -2.4, (17, 2): -0.4, (17, 3): -2.4, (17, 4): -2.8, (17, 5): -1.9, (17, 6): -6.9, (17, 7): -2.4, (17, 8): -2.0, (17, 9): -3.1, (17, 32): -2.7, (17, 33): -1.9, (17, 34): -1.3, (17, 35): -3.3, (17, 385): -2.4, (18, 8): -10.1, (18, 16): -7.9, (18, 17): -10.0, (18, 18): -6.0, (18, 24): -10.1, (19, 8): -2.6, (19, 16): -3.8, (19, 24): 5.4, (19, 32): 5.2, (19, 33): 4.8, (20, 8): 6.8, (21, 8): -12.2, (21, 9): -19.8, (21, 16): -9.2, (21, 24): -10.0, (21, 25): -10.0, (22, 8): 0.3, (22, 9): 0.4, (23, 8): -1.2, (23, 16): -3.8, (24, 8): 7.9, (24, 16): 8.3, (24, 24): 9.6, (25, 8): -0.9, (25, 9): -0.4, (25, 10): -1.0, (25, 16): 3.5, (25, 17): -2.9, (25, 18): -3.8, (26, 8): 12.8, (27, 1): 1.1, (27, 2): 6.8, (27, 3): 8.2, (27, 5): 7.2, (27, 8): 3.7, (27, 9): 7.6, (27, 16): 5.6, (27, 17): 7.6, (27, 18): 8.8, (27, 19): 7.6, (27, 20): 2.0, (27, 21): 2.1, (27, 22): 3.2, (27, 24): 4.8, (27, 25): 0.7, (28, 2): 17.7, (28, 8): 5.1, (29, 1): 10.6, (29, 2): 5.6, (29, 5): 11.2, (29, 8): 10.5, (29, 9): 10.5, (29, 10): 10.3, (29, 11): 4.4, (29, 12): 12.0, (30, 3): 6.7, (30, 4): 7.1, (30, 5): 7.1, (30, 8): 6.6, (31, 8): -12.7, (31, 9): 6.9, (31, 16): 13.2, (31, 24): 12.5, (32, 1): 4.1, (32, 8): 4.0, (32, 9): 4.2, (32, 16): 3.1, (33, 3): 3.8, (33, 4): 3.7, (33, 5): 7.5, (33, 6): 4.5, (33, 8): 12.0, (33, 16): 3.1, (34, 1): 3.7, (34, 2): 4.3, (34, 3): 11.9, (34, 4): 0.3, (34, 16): 3.0, (35, 4): 9.2, (35, 8): 3.4, (36, 1): -7.1, (36, 9): -2.2, (37, 1): -9.0, (37, 8): 4.6, (38, 1): -5.6, (38, 2): -5.6, (38, 5): 4.8, (38, 8): -4.6, (38, 9): -2.9, (38, 10): 5.4, (38, 11): 11.7, (38, 12): 11.8, (38, 13): 11.4, (38, 14): 13.6, (38, 15): 10.0, (38, 16): 7.9, (38, 17): 7.4, (38, 18): -8.1, (38, 21): 10.8, (38, 22): 1.6, (38, 23): 5.4, (38, 24): 14.8, (38, 32): 8.8, (38, 33): 0.3, (38, 34): 20.2, (38, 35): 7.2, (38, 36): 5.2, (38, 40): -17.1, (38, 41): -20.0, (38, 42): -16.9, (38, 43): 6.4, (38, 44): 11.2, (39, 1): -4.2, (39, 2): -2.6, (39, 3): 3.0, (39, 5): -0.7, (39, 8): -2.3, (39, 9): -1.3, (39, 10): -0.7, (39, 11): 4.1, (39, 12): 1.7, (39, 13): -1.0, (39, 14): 1.9, (39, 15): -3.7, (39, 16): -0.9, (39, 17): -1.8, (39, 18): 1.7, (39, 19): -3.3, (39, 20): 0.8, (39, 22): -2.2, (39, 23): -0.9, (39, 24): -3.8, (39, 26): -0.1, (39, 28): -2.3, (39, 30): -5.1, (39, 31): -7.3, (39, 32): -16.4, (39, 33): 7.3, (39, 34): -1.9, (39, 35): -1.0, (39, 36): -1.7, (39, 37): 0.9, (39, 38): -20.7, (39, 39): -0.6, (39, 40): -24.3, (39, 41): 0.6, (39, 42): -2.7, (39, 264): -3.9, (40, 1): 9.2, (41, 1): 1.6, (42, 1): 7.7, (44, 2): -0.6, (44, 10): -4.8, (45, 1): -14.9, (45, 2): -1.3, (45, 3): -3.3, (45, 8): -3.4, (45, 16): 16.1, (45, 17): 5.0, (46, 1): 2.9, (46, 2): 4.3, (46, 8): 2.6, (46, 16): 4.4, (46, 25): 7.4, (46, 26): 4.4, (48, 1): 2.5, (48, 2): 7.4, (48, 3): 2.7, (48, 4): 1.7, (48, 5): -1.0, (48, 6): 0.0, (48, 7): 2.3, (48, 8): 2.2, (48, 9): 0.9, (48, 11): -0.4, (48, 12): 5.2, (48, 13): 5.9, (48, 14): 0.2, (48, 15): -0.5, (48, 16): 2.1, (48, 17): 0.4, (48, 18): 0.1, (48, 19): 0.7, (48, 20): 2.0, (48, 24): 4.2, (48, 32): 0.6, (48, 33): 1.1, (48, 34): 4.3, (49, 2): 0.6, (49, 10): 2.6, (49, 11): 2.8, (49, 12): 5.5, (49, 13): 1.5, (50, 1): 10.0, (50, 2): 9.0, (50, 4): 6.8, (50, 8): 5.0, (50, 9): 6.3, (50, 10): 7.4, (50, 11): 5.1, (50, 12): 6.4, (50, 16): 6.5, (50, 17): 3.5, (50, 25): 6.3, (51, 1): -0.3, (51, 2): 5.7, (51, 3): 4.9, (51, 4): -0.2, (51, 5): -1.9, (51, 6): -18.1, (51, 7): -3.6, (51, 8): -0.9, (51, 9): 0.1, (51, 10): -1.3, (52, 8): 3.5, (52, 10): 2.5, (52, 11): 3.1, (52, 12): 4.2, (52, 13): 3.0, (52, 14): -0.7, (52, 16): 4.5, (52, 33): 2.0, (53, 1): 4.3, (53, 2): 2.4, (53, 3): 1.1, (53, 4): 0.6, (53, 5): 1.6, (53, 6): 15.7, (53, 9): 15.7, (53, 10): 15.7, (53, 11): 15.7, (53, 12): 15.7, (53, 16): 15.7, (53, 17): 3.1, (53, 18): 15.7, (53, 19): 4.8, (53, 20): 15.7, (53, 21): 4.4, (53, 22): 15.7, (53, 23): 15.7, (53, 24): 11.2, (53, 32): 15.7, (53, 33): 4.2, (53, 34): 15.7, (53, 35): 1.7, (53, 36): 15.7, (53, 37): 15.7, (54, 1): -0.1, (54, 2): 8.1, (54, 8): 2.1, (54, 9): 14.3, (54, 10): 5.6, (54, 16): 6.9, (54, 17): 0.6, (54, 18): 1.4, (55, 10): -15.9, (55, 11): -12.1, (55, 12): -17.1, (55, 13): -10.9, (55, 14): -10.7, (55, 15): -15.6, (55, 16): 16.3, (55, 17): -12.2, (55, 18): -32.1, (55, 20): -11.1, (55, 21): -15.8, (55, 22): -9.1, (55, 23): -18.8, (55, 24): 7.4, (55, 25): -17.9, (55, 26): -11.6, (55, 27): -12.1, (56, 2): 3.3, (56, 4): 3.4, (56, 16): -0.0, (56, 26): 3.5, (56, 27): 3.4, (56, 32): 3.3, (57, 2): 3.3, (57, 3): 0.4, (57, 8): 1.2, (57, 16): 3.9, (58, 8): -0.0, (59, 1): 13.7, (59, 3): 13.6, (59, 8): 13.3, (60, 2): 4.9, (60, 9): 6.3, (60, 16): 6.4, (60, 24): 7.3, (60, 400): 7.2, (61, 1): 3.8, (61, 2): 2.6, (61, 3): 4.0, (61, 4): -1.6, (61, 5): -0.3, (61, 8): 3.1, (61, 9): 4.4, (61, 10): 1.8, (61, 12): 1.4, (61, 14): 0.7, (61, 17): 5.4, (61, 24): 3.8, (61, 25): 2.0, (61, 26): 0.5, (61, 32): -0.7, (61, 33): -1.8, (61, 35): 2.0, (61, 36): -0.6, (61, 37): -1.8, (61, 38): -2.7, (62, 1): 8.4, (62, 2): 10.9, (62, 3): 11.2, (62, 4): 8.1, (62, 8): 3.2, (62, 9): 11.0, (62, 10): 5.9, (62, 16): 7.4, (62, 17): 6.7, (62, 18): 10.7, (62, 19): 21.0, (62, 144): 9.0, (63, 2): 14.0, (63, 3): 8.4, (63, 4): 11.2, (63, 5): 8.2, (63, 6): 11.3, (63, 8): 5.2, (63, 10): 10.1, (63, 11): -13.8, (63, 12): 12.3, (63, 16): 8.5, (63, 17): 7.6, (63, 144): 8.5, (63, 401): 8.8, (64, 8): 5.1, (65, 9): 5.6, (65, 16): 1.7, (65, 17): -1.1, (66, 1): 6.8, (66, 9): 6.8, (67, 1): 2.7, (67, 8): -0.3, (68, 8): 8.0, (68, 16): 2.5, (71, 16): -0.9, (71, 17): -2.5, (72, 8): 11.0, (72, 9): 11.0, (72, 16): 10.6, (73, 2): 8.3, (73, 8): 3.9, (73, 9): 4.2, (73, 17): 8.3, (75, 16): 8.3, (75, 17): 8.3, (75, 24): 7.4, (75, 25): 7.4, (75, 26): 7.4, (77, 1): 8.7, (78, 1): 11.6, (80, 1): -2.3, (80, 2): 9.0, (80, 3): 11.9, (80, 4): 0.3, (80, 5): 8.5, (80, 6): 5.5, (80, 7): 1.9, (80, 8): 8.0, (80, 9): 12.1, (80, 11): 7.1, (80, 19): 3.2, (80, 20): -12.1, (80, 21): -15.2, (80, 22): 4.5, (80, 23): 2.5, (80, 24): 2.8, (80, 28): 6.8, (80, 29): 3.0, (80, 30): -6.7, (80, 31): 3.3, (80, 32): 10.6, (80, 33): 5.4, (80, 34): 6.7, (80, 35): 9.1, (81, 1): -5.4, (81, 2): -2.0, (81, 3): 3.1, (81, 4): -1.0, (81, 5): 1.1, (81, 6): -2.8, (81, 7): -0.5, (81, 8): 4.0, (81, 9): 2.7, (81, 10): -2.5, (81, 11): -6.2, (81, 12): -5.9, (81, 13): -7.8, (81, 14): 2.6, (81, 15): -4.4, (81, 16): 4.1, (81, 17): 0.6, (81, 18): 2.2, (81, 28): 2.0, (81, 29): 3.7, (81, 30): -2.4, (81, 33): -0.9, (81, 35): 1.5, (81, 40): 12.1, (81, 41): 14.6, (81, 42): 7.4, (81, 43): -0.3, (81, 44): 2.0, (81, 45): 7.3, (81, 47): 3.8, (82, 1): 8.8, (82, 2): 9.9, (82, 8): 8.9, (82, 9): 8.8, (83, 1): 5.7, (83, 2): 0.1, (83, 3): -2.0, (83, 4): 2.4, (83, 5): 9.2, (83, 6): 2.2, (83, 7): 3.4, (83, 8): 10.0, (83, 9): 5.2, (83, 10): -2.2, (84, 2): 0.9, (84, 3): -3.0, (84, 4): -2.7, (84, 5): -6.7, (84, 6): -3.7, (84, 8): 0.1, (84, 9): 2.8, (84, 10): -8.1, (84, 11): -0.4, (84, 12): 1.3, (84, 16): 5.3, (84, 17): -0.4, (84, 18): -3.8, (84, 19): 3.6, (84, 20): -11.7, (84, 21): -0.3, (84, 22): -0.6, (84, 24): 1.1, (84, 25): 1.4, (84, 26): 2.2, (85, 1): 3.9, (85, 8): 3.7, (85, 9): 3.8, (85, 10): 3.9, (86, 1): 1.2, (86, 2): 3.5, (86, 3): 6.3, (86, 4): 0.1, (86, 5): 1.2, (86, 6): 3.3, (86, 8): 3.7, (87, 1): 6.5, (87, 2): 3.5, (87, 6): 8.7, (88, 1): 14.7, (88, 2): 10.5, (88, 4): 12.6, (88, 5): 14.7, (88, 6): 9.7, (88, 7): 15.3, (89, 1): 2.2, (89, 2): 2.6, (89, 3): 2.9, (89, 4): 4.5, (89, 6): 4.6, (89, 8): 7.8, (89, 9): 5.9, (89, 10): 7.2, (89, 11): 3.0, (89, 12): -2.4, (89, 13): 4.9, (90, 1): 7.8, (90, 2): 7.8, (90, 3): 7.4, (90, 4): 9.1, (90, 9): 9.9, (90, 10): 14.6, (90, 11): 14.4, (90, 12): 4.3, (90, 13): 8.3, (90, 14): 9.7, (90, 15): 10.1, (90, 16): 7.5, (90, 17): 8.1, (90, 24): 9.8, (91, 1): 8.0, (91, 2): 5.0, (91, 4): 1.9, (91, 5): 11.0, (91, 6): 4.0, (91, 7): 2.7, (91, 8): 3.1, (91, 9): 8.1, (91, 10): 6.1, (91, 11): 8.7, (91, 12): 6.7, (92, 1): 8.5, (92, 3): 12.0, (92, 4): -8.3, (92, 5): 5.7, (93, 1): 5.8, (93, 2): 5.4, (93, 3): -4.2, (93, 4): 7.1, (93, 5): 5.7, (94, 1): 10.7, (94, 2): 10.2, (94, 8): 10.2, (94, 9): 11.0, (94, 10): 8.7, (94, 11): 4.2, (94, 12): 11.4, (95, 1): 5.1, (95, 2): -1.7, (95, 3): 7.2, (95, 4): 5.0, (95, 8): 5.9, (95, 9): 4.2, (95, 10): 12.8, (95, 11): 6.0, (95, 12): 1.0, (95, 13): 7.9, (95, 14): 7.5, (95, 15): 4.0, (96, 1): 1.3, (96, 2): 15.9, (96, 3): 2.5, (96, 4): 1.0, (96, 5): 0.8, (96, 6): -3.9, (96, 7): 1.7, (96, 8): -0.9, (96, 9): 1.7, (96, 10): 11.1, (96, 11): -0.5, (97, 1): 5.5, (97, 2): 7.7, (97, 3): 5.5, (97, 4): 5.2, (97, 5): 5.6, (97, 8): 10.9, (98, 1): 8.1, (98, 2): 12.8, (98, 3): -0.9, (98, 4): 3.8, (98, 5): -6.0, (98, 6): 3.5, (98, 7): 3.9, (98, 8): 3.9, (98, 9): 4.6, (98, 10): 3.9, (98, 11): 5.1, (98, 12): 3.4, (98, 13): 3.9, (98, 16): 3.0, (98, 17): 3.6, (98, 18): 0.1, (98, 19): 9.3, (98, 20): 11.7, (98, 21): 1.9, (98, 22): -13.1, (98, 23): 4.9, (99, 1): 6.2, (99, 2): 5.6, (99, 3): 4.6, (99, 4): 2.8, (99, 5): 8.3, (99, 6): 5.2, (99, 7): 6.2, (99, 8): 2.5, (99, 9): 4.7, (99, 10): 5.1, (99, 11): 12.1, (100, 1): 9.5, (100, 3): 5.3, (100, 4): -12.6, (100, 5): 4.4, (100, 6): 8.5, (100, 7): 6.0, (100, 8): -3.4, (101, 1): 3.8, (101, 2): 8.1, (101, 3): 9.7, (101, 4): 4.4, (101, 5): 3.6, (101, 6): 3.6, (101, 7): 3.7, (101, 8): 5.8, (101, 9): 6.1, (101, 10): 3.8, (101, 11): 5.1, (101, 12): 4.9, (101, 13): 6.6, (101, 14): 6.1, (101, 15): 2.2, (101, 16): 9.1, (101, 17): 9.3, (101, 18): 6.8, (101, 19): 5.8, (101, 20): 5.0, (101, 21): 6.7, (101, 22): 4.2, (101, 23): 1.7, (101, 24): 2.4, (101, 25): 4.7, (101, 26): 4.4, (101, 27): 8.9, (101, 28): -15.6, (101, 29): 6.7, (101, 30): 5.1, (101, 31): 5.4, (101, 32): 7.4, (102, 1): -3.3, (102, 2): 6.7, (102, 3): -1.2, (102, 4): -1.2, (102, 5): 1.8, (102, 6): -2.5, (102, 7): -2.3, (102, 8): 3.4, (102, 9): 2.1, (102, 10): 2.1, (102, 11): 2.2, (103, 1): 5.6, (103, 2): 3.0, (103, 3): 4.9, (103, 4): 13.5, (103, 5): 4.8, (103, 6): 4.3, (103, 9): -4.4, (103, 10): 4.9, (103, 11): 6.1, (103, 16): 6.8, (103, 17): 5.9, (103, 18): 4.6, (103, 19): 4.5, (104, 1): 12.6, (104, 2): 17.0, (104, 3): 11.0, (104, 4): 15.1, (104, 5): 15.9, (105, 9): 11.8, (105, 28): 6.6, (105, 32): 8.1, (106, 8): 4.5, (107, 1): 8.5, (107, 8): 0.7, (107, 19): 1.4, (107, 24): 8.5, (108, 8): 11.3, (108, 9): 5.8, (108, 10): 6.9, (109, 8): 3.2, (109, 9): 11.5, (109, 10): 11.5, (109, 11): 12.0, (110, 8): 7.9, (110, 9): 9.1, (111, 24): 5.5, (111, 32): 5.5, (111, 33): 5.5, (112, 12): -1.5, (112, 13): -1.6, (112, 14): -1.6, (112, 15): -1.5, (112, 17): -1.7, (112, 18): -1.7, (112, 19): -1.5, (112, 20): -1.6, (112, 21): -1.2, (112, 22): -1.7, (112, 23): -1.3, (112, 24): -1.7, (112, 25): -1.7, (112, 32): -1.7, (112, 40): -1.2, (112, 41): -1.8, (112, 42): -1.8, (113, 16): -1.3, (114, 1): -8.6, (115, 8): -13.2, (115, 16): -1.2, (115, 17): 1.1, (115, 24): -1.5, (115, 32): -1.7, (115, 40): -1.8, (116, 1): -1.7, (116, 8): 0.5, (116, 9): -1.7, (116, 16): -0.9, (116, 17): -1.7, (116, 18): -1.7, (116, 24): -1.7, (116, 25): -1.7, (116, 26): -1.7, (116, 27): -1.7, (116, 28): -1.7, (116, 32): -0.5, (116, 40): -1.7, (116, 41): -1.7, (116, 42): -2.7, (116, 43): -1.7, (117, 1): 5.8, (117, 2): -1.7, (117, 3): -1.7, (117, 4): -1.5, (117, 8): -1.8, (117, 9): 5.5, (117, 16): -2.0, (117, 17): -1.7, (117, 18): -0.3, (117, 19): -1.7, (117, 24): 0.1, (117, 40): -1.6, (117, 41): -1.7, (117, 42): -1.7, (117, 43): -2.3, (117, 44): -1.6, (118, 8): 1.2, (118, 9): 0.0, (118, 11): -1.7, (118, 12): -1.7, (118, 13): 1.4, (119, 1): -1.7, (119, 2): -1.3, (119, 3): -1.0, (119, 8): -0.2, (119, 9): 2.5, (119, 16): -2.8, (119, 17): -2.1, (119, 24): 1.2, (119, 25): 2.1, (119, 26): -2.0, (119, 27): -2.3, (119, 40): -1.6, (119, 41): -3.2, (119, 42): -1.6, (119, 43): -1.7, (119, 44): -2.6, (119, 45): -1.7, (119, 46): -1.8, (120, 1): -5.4, (120, 2): -5.3, (120, 3): 1.0, (120, 4): 1.0, (120, 6): 32.8, (120, 8): -1.6, (120, 9): -15.6, (120, 10): -1.7, (120, 11): -1.5, (120, 13): -5.4, (120, 16): -1.7, (120, 17): -1.7, (120, 18): -1.8, (120, 19): -1.5, (120, 20): -1.5, (120, 21): -1.7, (120, 22): -1.7, (120, 23): -1.7, (120, 24): -1.6, (120, 25): -1.7, (120, 26): -1.8, (120, 27): -1.7, (120, 28): -1.8, (120, 29): -1.7, (120, 30): -1.8, (120, 31): -1.8, (120, 32): -1.7, (120, 34): -1.7, (120, 35): -1.7, (120, 36): -1.6, (120, 37): -1.7, (120, 38): -1.5, (120, 39): -1.5, (120, 40): -1.5, (120, 41): -1.8, (120, 42): -1.7, (121, 1): -9.6, (121, 2): -1.5, (121, 3): -1.5, (121, 4): -1.8, (121, 5): -1.7, (121, 6): -1.3, (121, 7): -1.7, (121, 8): -1.8, (121, 9): -1.8, (122, 1): 16.4, (122, 2): -0.7, (122, 3): 11.8, (122, 4): 19.8, (122, 5): 3.4, (122, 6): -1.9, (122, 7): -2.0, (122, 16): 5.4, (123, 1): -10.8, (123, 2): -6.9, (123, 6): -1.7, (123, 7): -1.5, (123, 8): -1.7, (124, 1): 13.3, (124, 2): -7.4, (124, 3): -10.3, (124, 4): -8.0, (124, 5): -2.0, (124, 7): -6.4, (124, 8): -1.6, (124, 9): -1.7, (124, 11): 23.9, (124, 12): -1.0, (124, 13): -1.8, (124, 14): -1.5, (124, 15): -1.8, (124, 16): -1.5, (125, 1): 3.1, (125, 2): -8.3, (125, 3): -1.4, (125, 4): -4.3, (125, 5): 1.1, (125, 6): -6.7, (125, 7): 2.0, (125, 8): -2.4, (125, 9): 0.8, (125, 11): -8.9, (125, 12): -12.0, (125, 13): -1.7, (125, 14): -0.0, (125, 15): -1.7, (125, 16): -1.2, (125, 17): -0.2, (125, 18): -1.1, (125, 19): -1.2, (125, 20): -1.6, (125, 21): -1.7, (125, 22): -1.5, (125, 23): -1.8, (125, 24): -1.7, (125, 25): -1.6, (125, 26): -1.7, (125, 27): -1.8, (125, 28): -1.7, (125, 29): -1.5, (125, 30): -1.9, (125, 31): -8.9, (125, 32): -10.1, (126, 1): -2.4, (126, 2): -8.0, (126, 3): -1.1, (126, 4): -3.4, (126, 5): -0.9, (126, 6): 14.3, (126, 7): -2.2, (126, 8): -1.7, (126, 9): -1.5, (126, 16): -1.4, (126, 17): -1.5, (126, 18): -1.6, (126, 19): -1.3, (126, 20): -1.7, (126, 22): -1.6, (126, 23): -1.7, (126, 24): -1.6, (126, 25): -1.6, (126, 26): -1.7, (127, 1): 4.7, (127, 2): 8.3, (127, 3): 4.2, (127, 4): -1.7, (127, 6): -1.4}
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
