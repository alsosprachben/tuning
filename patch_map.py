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


def program_trim(program, drum=False):
    """The linear factor on a note's channel volume for its program -- or for
    its variation (VARIATION_TRIM_DB), where it has one."""
    v = getattr(program, "variation", 0)
    if not drum and v and ((int(program) & 0x7F), v) in VARIATION_TRIM_DB:
        db = VARIATION_TRIM_DB[(int(program) & 0x7F, v)]
    else:
        db = KIT_TRIM_DB if drum else PROGRAM_TRIM_DB.get(int(program) & 0x7F, 0.0)
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
        _attrs = dict(messenger=dict(_B.messenger, **{k: v for k, v in _pan.items() if k != "key_pan_spread"}))
        if "key_pan_spread" in _pan:
            _attrs["key_pan_spread"] = _pan["key_pan_spread"]
        VARIATIONS[(_p, _b)] = type("Sc88_%d_%d" % (_p, _b), (_B,), _attrs)
        VARIATION_NAMES[(_p, _b)] = _nm
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
    (126, 1): 52, (126, 5): 56,                                  # Laughing, Footstep
    (127, 1): 73,                                                # Machinegun
}
for _pv, _k in SFX_VARIATIONS.items():
    VARIATIONS[_pv] = melodic_sfx(_k)
    # ...AT THE KIT'S LEVEL: the class is levelled as the SFX set's key, and
    # its program's trim was set for that program's own voice (120's fret
    # noise +34 dB over the kit's, 124's telephone -25)
    VARIATION_TRIM_DB.setdefault(_pv, KIT_TRIM_DB)

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
# semitones, dB), ...)}
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
    base = property_class_for_note(spec[0], note)
    db = float(spec[2])
    if not db:
        return base
    k = (base, db)
    if k not in _LAYER_CLASSES:
        _LAYER_CLASSES[k] = type("%s_layer%+g" % (base.__name__, db), (base,),
                                 {"initial_gain": base.initial_gain * 10.0 ** (db / 20.0)})
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
    (18, 8): ("Rotary Org.", ("set", 18, dict(default_stops=0b111111111, leslie_fast=True))),
    (18, 16): ("RotaryOrg.S", ("set", 18, dict(leslie_fast=False))),
    (18, 24): ("RotaryOrg.F", ("set", 18, dict(leslie_fast=True, default_stops=0b111111111))),
    (19, 16): ("ChurchOrg.3", ("set", 19, dict(default_stops=0b10010011))),     # 8' 4' 16' mixture
    (19, 24): ("Organ Flute", ("set", 19, dict(default_stops=(1 << 6) | (1 << 14)))),                # flute 8' 4'
    (19, 32): ("Trem.Flute", ("set", 19, dict(default_stops=(1 << 6) | (1 << 14) | (1 << 13)))),    # ...tremulant
    (24, 16): ("Nylon Gt.o", ("layer", ((24, 0, 0.0), (24, 12, -6.0)))),
    (24, 24): ("VeloHarmnix", ("layer", ((24, 0, 0.0, 0, 95), (31, 0, 0.0, 96, 127)))),
    (25, 9): ("Nylon+Steel", ("layer", ((24, 0, -2.0), (25, 0, -2.0)))),
    (31, 16): ("Ac.Gt.Harm.", ("alias", 31)),
    (48, 9): ("Orchestra 2", ("layer", ((48, 0, 0.0), (60, 0, -8.0)))),
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
    (123, 3): ("Bird 2", ("kit", 78, 56)),
    (124, 7): ("Scratch 2", ("var", (124, 4))),
    (126, 6): ("Applause 2", ("kit", 58, 56)),
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


for (_p, _b), (_nm, _how) in SC88_CHEAP.items():
    VARIATION_NAMES[(_p, _b)] = _nm
    if _how[0] == "layer":
        LAYERED[(_p, _b)] = _how[1]
        VARIATIONS[(_p, _b)] = routed_variation(_how[1][0][0], "sc88_%d_%d" % (_p, _b))
    else:
        VARIATIONS[(_p, _b)], _tr = _sc88_class(_how, "sc88_%d_%d" % (_p, _b))
        VARIATION_TRIM_DB.setdefault((_p, _b), _tr)

# THE VARIATIONS' LEVELS, MEASURED: each GS variation GeneralUser GS has a
# preset for, levelled to it as the programs are (examples/sfx_levels.py
# --var-trim: velocities 64 and 100, K level re a piano C4) -- over the
# defaults set above (a variation's capital's trim, or the SFX set's)
VARIATION_TRIM_FIT = {(0, 8): 0.0, (0, 16): 0.2, (1, 8): 8.2, (2, 1): -1.3, (2, 2): -2.8, (2, 8): 1.9, (3, 8): 7.3, (4, 8): 0.6, (4, 16): -7.4, (4, 24): -4.5, (5, 8): -2.4, (5, 16): -5.3, (6, 8): -11.9, (6, 16): -10.9, (6, 24): -12.5, (11, 8): 2.3, (12, 8): 2.9, (14, 8): -2.6, (14, 9): -1.9, (15, 1): 4.2, (16, 1): -7.4, (16, 8): -4.4, (16, 9): -6.0, (16, 16): -5.5, (16, 17): -5.7, (16, 18): -9.6, (16, 32): -10.1, (16, 33): -7.7, (16, 40): -6.9, (17, 1): -2.4, (17, 8): -2.0, (17, 32): -2.7, (18, 8): -10.1, (18, 16): -7.9, (18, 24): -10.1, (19, 8): -2.6, (19, 16): -3.8, (19, 24): 5.4, (19, 32): 5.2, (21, 8): -12.2, (24, 8): 7.9, (24, 16): 8.3, (24, 24): 9.6, (25, 8): -0.9, (25, 9): -0.4, (25, 16): 3.5, (26, 8): 12.8, (27, 8): 3.7, (28, 8): 5.1, (30, 8): 6.6, (31, 8): -12.7, (31, 16): 13.2, (35, 4): 9.2, (38, 1): -4.9, (38, 8): -4.6, (38, 9): -2.9, (38, 10): 5.4, (38, 16): 4.0, (39, 1): -4.2, (39, 2): -2.6, (39, 3): 3.0, (39, 8): -2.3, (39, 9): -1.3, (39, 16): -0.9, (39, 17): -5.5, (39, 18): -2.7, (39, 19): -3.3, (48, 8): 2.2, (48, 9): 0.9, (48, 11): -0.4, (48, 16): 2.1, (48, 24): 4.2, (49, 10): 2.6, (50, 1): 10.0, (50, 8): 5.0, (52, 8): 3.5, (54, 8): 2.1, (55, 10): -15.9, (55, 16): 16.3, (60, 16): 6.4, (61, 8): 3.1, (62, 1): 8.4, (62, 8): 3.2, (62, 9): 11.0, (62, 16): 7.4, (63, 8): 5.2, (63, 16): 8.5, (63, 17): 7.6, (80, 1): -2.3, (80, 2): 9.0, (80, 3): 11.9, (80, 4): 0.3, (80, 5): 8.5, (80, 6): 5.5, (80, 8): 8.0, (81, 1): -5.4, (81, 2): -2.0, (81, 3): 3.1, (81, 4): -1.0, (81, 5): 1.1, (81, 6): -2.8, (81, 7): -0.5, (81, 8): 4.0, (81, 16): 4.1, (82, 1): 8.8, (82, 2): 9.9, (84, 8): 0.1, (86, 1): 1.2, (87, 1): 6.5, (87, 2): 3.5, (88, 1): 14.7, (89, 1): 2.2, (89, 2): 2.6, (89, 3): 2.9, (89, 4): 4.5, (90, 1): 7.8, (91, 1): 8.0, (93, 1): 5.8, (93, 2): 5.4, (95, 1): 5.1, (95, 8): 5.9, (95, 9): 4.2, (95, 10): 12.8, (96, 1): 1.3, (96, 2): 15.9, (96, 8): -0.9, (97, 1): 5.5, (97, 2): 7.7, (97, 8): 10.9, (98, 1): 8.1, (98, 2): 4.0, (98, 3): -0.9, (98, 4): 3.8, (98, 5): -6.0, (98, 6): 3.5, (98, 7): 3.9, (98, 8): 3.9, (98, 9): 4.6, (98, 16): 3.0, (98, 17): 3.6, (98, 18): 0.1, (98, 19): 9.3, (99, 1): 6.2, (99, 2): 5.6, (99, 3): 4.6, (99, 4): 2.8, (99, 5): 8.3, (99, 6): 5.2, (101, 1): 3.8, (101, 2): 8.1, (102, 1): -3.3, (102, 2): 6.7, (102, 3): -1.2, (102, 4): -1.2, (102, 5): 1.8, (102, 6): -2.5, (103, 1): 5.6, (104, 1): 12.6, (104, 2): 17.0, (107, 8): 0.7, (115, 8): -13.2, (116, 8): 0.5, (117, 1): 5.8, (117, 8): -1.8, (117, 9): 5.5, (118, 8): 1.2, (118, 9): 0.0, (119, 1): -1.7, (119, 8): -0.2, (119, 9): 2.5, (119, 16): -2.8, (119, 17): -2.1, (119, 24): 1.2, (119, 25): 2.1, (120, 1): -5.4, (120, 2): -5.3, (120, 3): 1.0, (120, 4): 1.0, (120, 6): 32.8, (121, 1): -9.6, (122, 1): 16.4, (122, 2): -0.7, (122, 3): 11.8, (122, 4): 19.8, (122, 5): 3.4, (123, 1): -10.8, (123, 2): -6.9, (124, 1): 13.3, (124, 2): -7.4, (124, 3): -10.3, (124, 4): -8.0, (124, 5): -2.0, (124, 7): -6.4, (125, 1): 3.1, (125, 2): -8.3, (125, 3): -1.4, (125, 4): -4.3, (125, 5): 1.1, (125, 6): -6.7, (125, 7): 2.0, (125, 8): -2.4, (125, 9): 0.8, (126, 1): -2.4, (126, 2): -8.0, (126, 3): -1.1, (126, 4): -3.4, (126, 5): -0.9, (126, 6): 14.3, (127, 1): 4.7, (127, 2): 8.3, (127, 3): 4.2}
VARIATION_TRIM_DB.update(VARIATION_TRIM_FIT)
