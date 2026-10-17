"""General MIDI percussion key map (channel 10).

On GM channel 10 the note number selects a drum, not a pitch. Each note
maps to (drum name, physical-model bucket, base frequency in Hz). The base
frequency sets where the struck modes sit; the bucket sets the timbre
(membrane / noise / metal). Broad first: three buckets cover the kit, with
per-drum base frequencies. Splitting buckets into distinct kick/snare/hat
models is the realism step.

`percussion_for_note(note, kit=0)` returns (name, property_class,
base_frequency, pan) or None if the note is unmapped (silent). `kit` is the
drum set, chosen by program change on the drum channel: see KITS.
"""

import tonelib as _T
from tonelib import (
    MembraneDrumProperties,
    BongoProperties,
    CongaProperties,
    TimbaleProperties,
    TimbaleHighProperties,
    TimbaleLowProperties,
    SurdoProperties,
    SurdoOpenProperties,
    SurdoMuteProperties,
    ElectricSnareProperties,
    SnareDrum2Properties,
    CuicaProperties,
    MuteCuicaProperties,
    TomTomProperties,
    FloorTomProperties,
    HighTomProperties,
    KickDrumProperties,
    NoiseDrumProperties,
    MetalPercussionProperties,
    SnareDrumProperties,
    AcousticSnareProperties,
    CymbalProperties,
    RideBellProperties,
    CrashCymbal1Properties,
    CrashCymbal2Properties,
    SplashCymbalProperties,
    ChineseCymbalProperties,
    RideCymbalProperties,
    CrashRideProperties,
    SideStickProperties,
    TambourineProperties,
    CowbellStrokeProperties,
    AgogoHighProperties,
    AgogoLowProperties,
    CongaMuteProperties,
    CongaOpenProperties,
    CongaLowProperties,
    BongoHighProperties,
    BongoLowProperties,
    HandClapProperties,
    WoodPercussionProperties,
    RattleProperties,
    MaracasProperties,
    VibraslapProperties,
    CabasaProperties,
    SambaWhistleProperties, ShortWhistleProperties, LongWhistleProperties,
    ClavesProperties,
    WoodBlockHiProperties,
    WoodBlockLoProperties,
    CastanetsProperties,
    TriangleProperties,
    CrotaleProperties,
    AgogoProperties,
    CowbellProperties,
    ClosedHiHatProperties,
    PedalHiHatProperties,
    OpenHiHatProperties,
    GuiroProperties,
    SynthDrumProperties,
    ElectronicTomProperties,
    SimmonsSnareProperties,
    ReverseCymbalProperties,
    ElectronicKickProperties,
    ConcertBassDrumProperties,
    SfxFretSlideProperties,
    SfxHelicopterProperties,
    SfxBirdsProperties,
    SfxSeashoreProperties,
    SfxRainProperties,
    SfxThunderProperties,
    SfxWindProperties,
    SfxStreamProperties,
    SfxBubbleProperties,
    SfxEngineProperties,
    SfxTrainProperties,
    SfxJetProperties,
    SfxCrashProperties,
    SfxSirenProperties,
    SfxCarPassProperties,
    SfxSkidProperties,
    SfxStarshipProperties,
    GunshotProperties,
    RoomTomProperties,
    RoomFloorTomProperties,
    RoomHighTomProperties,
    MondoKickProperties,
    ConcertCymbal1Properties,
    ConcertCymbal2Properties,
    ConcertSnareProperties,
    OrchestraApplauseProperties,
    TimpaniProperties,
    TR808KickProperties,
    TR808SnareProperties,
    TR808TomProperties,
    TR808MidTomProperties,
    TR808HiTomProperties,
    TR808CongaProperties,
    TR808MidCongaProperties,
    TR808HiCongaProperties,
    TR808RimShotProperties,
    TR808ClavesProperties,
    TR808MaracasProperties,
    TR808CowbellProperties,
    TR808ClosedHatProperties,
    TR808OpenHatProperties,
    TR808CymbalProperties,
    ElectronicSnareProperties,
    GatedSnareProperties,
    BrushTapProperties,
    BrushSlapProperties,
    BrushSwirlProperties,
)

M = MembraneDrumProperties      # a head with no shell worth modelling
# ...and the four that DO have one. These nine notes were all M: nine notes,
# four instruments. They share a circular head and its Bessel modes and very
# little else -- what separates a bongo from a surdo is the SHELL, and what
# separates a timbale from a conga is what the shell is made of. See
# tonelib.ShelledDrumProperties.
BO = BongoProperties            # tiny, tight, fingers: almost no shell at all
CO = CongaProperties            # a tall wooden cavity, and it is most of the sound
TI = TimbaleProperties          # a METAL shell, one head, sticks: it rings
SU = SurdoProperties            # two feet across, slack, a padded beater
TF = FloorTomProperties         # two heads over a closed shell: see TomTomProperties
TR = TomTomProperties
TH = HighTomProperties
K = KickDrumProperties          # bass drum: tight low thump
N = NoiseDrumProperties
T = MetalPercussionProperties   # pitched metal/wood (cowbell, agogo, block, ...)
S = SnareDrumProperties
C = CymbalProperties            # the family; the four kit plates below are measured
R = RideBellProperties          # the ride's bell: pitch THROUGH the wash
W = WoodPercussionProperties    # claves, woodblocks: a dry tock, gone at once
P = CrotaleProperties           # tuned discs: the only PLATE here, 1 : 2.08 : 3.41
G = GuiroProperties             # struck wood, but the noisiest of it

# GM note -> (name, bucket, base Hz). Standard GM drum map, notes 35-81.
PERCUSSION = {
    # DRSKit's kick settles at 44.4 Hz (KickDrumProperties); 35, the
    # "acoustic" bass drum, the deeper of the two, the same 2 semitones under
    35: ("Acoustic Bass Drum", K, 39.4),
    36: ("Bass Drum 1",        K, 44.4),
    37: ("Side Stick",      SideStickProperties, 195.1),
    # DRSKit's snare head, 196 Hz on every stroke (AcousticSnareProperties)
    38: ("Acoustic Snare",     AcousticSnareProperties, 195.1),
    39: ("Hand Clap",          HandClapProperties, 310.4),
    # Roland's "Snare Drum 2" (SC-55 p.70): VCSL's Modern 1, lowest mode 192.5 Hz
    40: ("Snare Drum 2",       SnareDrum2Properties, 192.5),
    41: ("Low Floor Tom",      TF, 87.0),
    42: ("Closed Hi-Hat",   ClosedHiHatProperties, 248.4),
    43: ("High Floor Tom",     TF, 98.0),
    44: ("Pedal Hi-Hat",    PedalHiHatProperties, 248.4),
    45: ("Low Tom",            TR, 110.0),
    46: ("Open Hi-Hat",     OpenHiHatProperties, 248.4),
    47: ("Low-Mid Tom",        TR, 130.0),
    48: ("Hi-Mid Tom",         TH, 150.0),
    49: ("Crash Cymbal 1",     CrashCymbal1Properties, 288.3),
    50: ("High Tom",           TH, 175.0),
    51: ("Ride Cymbal 1",     RideCymbalProperties, 147.5),
    52: ("Chinese Cymbal",     ChineseCymbalProperties, 181.9),
    # MEASURED: Iowa 21ride.stick.bell. 345 Hz is the LOWEST mode; the ping a
    # drummer hears is the strongest one, at ratio 8.1 = 2795 Hz. It was 660.
    53: ("Ride Bell",         R, 147.5),
    54: ("Tambourine",         TambourineProperties, 1000.0),
    55: ("Splash Cymbal",      SplashCymbalProperties, 143.3),
    56: ("Cowbell",            CowbellStrokeProperties, 466.0),
    57: ("Crash Cymbal 2",     CrashCymbal2Properties, 333.7),
    58: ("Vibraslap",          VibraslapProperties, 300.0),
    # GM wants two RIDES here, not two articulations of one: 51 and 59 are
    # different plates and 53 is the bell of whichever carries it. Iowa has one
    # ride, so this is its 20" plate -- the biggest and lowest in the set -- and
    # so a crash-ride rather than a second dark ride. See CrashRideProperties.
    59: ("Ride Cymbal 2",     CrashRideProperties, 151.7),
    60: ("Hi Bongo",           BongoHighProperties, 161.0),
    61: ("Low Bongo",          BongoLowProperties, 142.0),
    62: ("Mute Hi Conga",      CongaMuteProperties, 209.0),
    63: ("Open Hi Conga",      CongaOpenProperties, 216.0),
    64: ("Low Conga",          CongaLowProperties, 164.0),
    # hello_flowers' pair (freesound 41196): the free strokes' lowest modes
    65: ("High Timbale",       TimbaleHighProperties, 224.1),
    66: ("Low Timbale",        TimbaleLowProperties, 186.4),
    67: ("High Agogo",         AgogoHighProperties, 1228.0),
    68: ("Low Agogo",          AgogoLowProperties, 696.0),
    69: ("Cabasa",             CabasaProperties, 482.5),
    70: ("Maracas",            MaracasProperties, 386.0),
    # ROLAND NAMES THE PITCH, not just the length. GM calls 71 and 72 "Short
    # Whistle" and "Long Whistle" and says nothing more, so the reading everyone
    # implements is the SC-55's -- the same argument SlowBowedStringProperties
    # makes about GM 48 and 49. In Roland's own GS drum map these are:
    #
    #     71  Short Hi Whistle
    #     72  Long Lo Whistle
    #
    # so short-is-higher is not an inference, it is the reference stating it,
    # and "Hi"/"Lo" as a named pair wants a clear interval rather than a few
    # cents. A fourth: 694.9 against 520 puts the resonances at 3207 and 2400 Hz.
    #
    # The physics agrees under either reading of the names. A shorter chamber
    # resonates higher directly; and a short sharp stab is blown HARDER, while a
    # pressure-driven resonator goes sharp under pressure -- the same mechanism
    # as the attack sweep in SambaWhistleProperties, where the tone rises into place
    # as the jet establishes.
    71: ("Short Whistle",      ShortWhistleProperties, 587.2),   # its tone at 2723 Hz (VCSL's ball whistle)
    72: ("Long Whistle",       LongWhistleProperties, 575.6),   # its tone at 2659 Hz
    # MEASURED: the Iowa guiro body rings at 1175 Hz, not 520-560 -- and it is a
    # STRUCK WOODEN BODY, not noise. Spectral flatness on one ridge is 0.0044
    # (away) and 0.0056 (toward), against a clave's 0.0002 and a woodblock's
    # 0.0000, where white noise is 1.0. It was on NoiseDrumProperties, which
    # builds a dense inharmonic stack to approximate a hiss, so every ridge
    # arrived as a burst of static instead of a tock. A guiro is a notched gourd
    # and the stick catching a notch excites the body: much closer to a small
    # woodblock struck very fast than to a rattle.
    # 1099 Hz is the lowest mode present in BOTH Iowa takes, measured from the
    # free tail. (744 came from a scrape-spectrum measurement that was reading
    # the ridge-rate comb; 1175 before that was a single mis-picked peak.)
    73: ("Short Guiro",        G, 1099.0),
    74: ("Long Guiro",         G, 1099.0),
    # MEASURED (Iowa hand percussion, mf). Claves ring at 908, 993 and 1216 Hz
    # across the three pairs; 990 is the middle one.
    75: ("Claves",             ClavesProperties, 700.0),
    # The four Iowa woodblocks give f1 x size = 7700 Hz-inches almost exactly
    # (10" 778, 8.5" 853, 6.5" 1234, 5.5" 1406), so HI is the small block and
    # LOW the large one. They were 760 and 620, which is the large block twice.
    76: ("Hi Wood Block",      WoodBlockHiProperties, 687.7),
    77: ("Low Wood Block",     WoodBlockLoProperties, 777.9),
    # A CUICA IS NOT STRUCK, and this was M -- the generic struck membrane it
    # shares with the bongos. It is a FRICTION drum: a stick tied to the inside
    # centre of the head, stroked with a damp cloth, driving the membrane with a
    # sawtooth. Driven at the centre only the axisymmetric modes can speak, and
    # the drive mode-locks them into a harmonic tone. See CuicaProperties.
    # The mute is the finger pressed on the head: tighter, higher, and gliding
    # UP into the note where the open one falls away from it.
    # reinsamba's cuica (freesound pack 1339): where each register's strokes arrive
    78: ("Mute Cuica",         MuteCuicaProperties, 790.0),
    79: ("Open Cuica",         CuicaProperties, 355.0),
    # MEASURED: the Iowa 6" triangle sounds 1927 Hz and the 8" 1497 -- a
    # triangle is a bent BAR and rings far higher than 1000. Its upper modes
    # come out at 2.0, 3.2, 4.2 and 5.3 x f1, dense and inharmonic as a bent bar
    # should be.
    80: ("Mute Triangle",      TriangleProperties, 711.6),
    81: ("Open Triangle",      TriangleProperties, 711.6),
    # GM 85 was simply missing. Iowa's two castanet pairs sound 1247 and 1323 Hz.
    85: ("Castanets",          CastanetsProperties, 268.2),
    # ...and so was 84. A belltree is a stack of small tuned DISCS, which is a
    # crotale in a different mounting -- MEASURED across Iowa's chromatic set,
    # see CrotaleProperties. 1055 Hz is its C6, the bottom of that set.
    84: ("Belltree",           P, 1055.0),
    # 86 and 87 were unmapped too. A surdo is the big Brazilian bass drum that
    # carries a samba -- a large membrane, deeper than a floor tom, and the
    # muted stroke is the same head with a hand on it.
    # plotzki's (freesound 36127): its strokes settle at 66.7 Hz
    86: ("Mute Surdo",         SurdoMuteProperties, 66.7),
    87: ("Open Surdo",         SurdoOpenProperties, 66.7),
}

GM_PERCUSSION_CHANNEL = 9  # 0-based; GM drum channel is "10" one-based

# Default stereo placement of each kit piece (drummer's perspective:
# -1 = full left, 0 = center, +1 = full right), so a centered percussion
# channel still spreads the kit across the image instead of stacking every
# drum at one point. A channel pan (CC10) is added on top to rotate the
# whole kit. Kick and snare sit near center; hats to the left, ride/toms
# fanning to the right, crashes to the sides.
import os as _os

DEFAULT_PAN = {
    35: 0.0, 36: 0.0,                    # bass drums: center
    37: -0.12, 38: -0.12, 40: -0.12,     # snare / stick: just left of center
    39: -0.12,                           # hand clap
    42: -0.45, 44: -0.45, 46: -0.45,     # hi-hats: left
    41: 0.5, 43: 0.4, 45: 0.2, 47: 0.0, 48: -0.2, 50: -0.35,  # toms: low->high, R->L
    49: -0.6, 55: -0.4, 52: -0.7,        # crash 1 / splash / china: left
    57: 0.6,                             # crash 2: right
    51: 0.5, 53: 0.5, 59: 0.5,           # ride / ride bell: right
    54: 0.3,                             # tambourine
    56: 0.0,                             # cowbell: center
    60: 0.35, 61: 0.35, 62: 0.4, 63: 0.4, 64: 0.45,  # bongos/congas: right
    65: 0.3, 66: 0.3,                    # timbales
    67: 0.4, 68: 0.4,                    # agogo
    69: 0.55, 70: -0.55,                 # cabasa / maracas: opposite sides
    75: -0.3, 76: -0.3, 77: -0.35,       # claves / woodblocks: left
}



def kit_pan(note):
    """This drum's place in the stereo image, before the channel's CC10.

    FROM WHICH SIDE OF THE KIT. DEFAULT_PAN is the drummer's view (hi-hat
    left, ride right), which is how most records are mixed. A GS module adds
    CC10 to "each Instrument's pan setting" (Roland, VE-GS Pro MIDI
    Implementation) -- so a pan move on a drum channel lands relative to where
    the module put each drum, and modules did not agree on which side.

    Ben's qkbttl02 shows which his card used. The hi-hat section pans the kit
    to 24, then sweeps it back to 64 across the bar that ends it, and he heard
    the hi-hats START LEFT AND SWEEP TO THE RIGHT -- the climax of the piece.
    With the hi-hat left of centre (this table) that sweep goes from hard left
    to left and never crosses; with it RIGHT of centre it goes from a little
    left to clearly right, which is what he wrote for. That is an audience-side
    kit, and TUNING_KIT_VIEW=audience mirrors the whole kit for such a file.
    """
    p = DEFAULT_PAN.get(note, 0.0)
    return -p if _os.environ.get('TUNING_KIT_VIEW', 'drummer') == 'audience' else p

# ---- DRUM SETS ---------------------------------------------------------------
#
# The drum set is the PROGRAM on the drum channel -- "The Drum Set number
# corresponds to the program number" (SC-55 owner's manual p.21). The SC-55 has
# ten, and its drum set table (p.70-71) says what each changes: a set lists
# only the notes that differ, and every blank is "Same as the percussion sound
# of Standard". Numbered 0-based here, as the bytes are; the manual counts from
# 1, so its "25:Electronic Set" is program 24.
#
# Jazz (32) shares Standard's column on the SC-55, so it IS Standard there.
DRUM_SETS = {0: "Standard", 8: "Room", 16: "Power", 24: "Electronic",
             25: "TR-808", 32: "Jazz", 40: "Brush", 48: "Orchestra",
             56: "SFX", 127: "CM-64/32L"}

# THE SETS THAT ARE BUILT: {program: {note: (name, class, base Hz)}}, holding
# only the notes that differ. A set named above but not here plays Standard,
# as it always has; a program that is no set at all does too. The manual does
# not say what the SC-55 does with a number that is not a set, so nothing is
# guessed: 1, 20, 29, 30, 35, 47, 49 and 60 -- all sent to channel 10 by files
# in the corpus -- play Standard, which is what they did before sets existed.
#
# ELECTRONIC, p.70. A Simmons-era kit: the six toms are synth toms, which
# SynthDrumProperties (GM 118) already is; the reverse cymbal is GM 119. Only
# the kick and the two snares needed new classes. The toms keep Standard's
# pitches, so a fill written for one kit lands in the same places on the other.
KITS = {
    24: {
        36: ("Elec BD",          ElectronicKickProperties, 28.3),    # a real Simmons's (elkit_fit.py)
        38: ("Elec SD",          SimmonsSnareProperties, 453.5),    # a real Simmons's (elkit_fit.py)
        40: ("Gated SD",         GatedSnareProperties, 290.0),    # its body as GeneralUser GS's (elkit_fit.py)
        41: ("Elec Low Tom 2", _T.simmons_voice(ElectronicTomProperties, "ElectronicTom41",
                                    tone_hz=42.8, decay_s=1.005), 42.8),
        43: ("Elec Low Tom 1", _T.simmons_voice(ElectronicTomProperties, "ElectronicTom43",
                                    tone_hz=45.8, decay_s=0.925), 45.8),
        45: ("Elec Mid Tom 2", _T.simmons_voice(ElectronicTomProperties, "ElectronicTom45",
                                    tone_hz=53.4, decay_s=0.864), 53.4),
        47: ("Elec Mid Tom 1", _T.simmons_voice(ElectronicTomProperties, "ElectronicTom47",
                                    tone_hz=65.4, decay_s=0.784), 65.4),
        48: ("Elec Hi Tom 2", _T.simmons_voice(ElectronicTomProperties, "ElectronicTom48",
                                    tone_hz=69.9, decay_s=0.703), 69.9),
        50: ("Elec Hi Tom 1", _T.simmons_voice(ElectronicTomProperties, "ElectronicTom50",
                                    tone_hz=75.4, decay_s=0.623), 75.4),
        52: ("Reverse Cymbal",   ReverseCymbalProperties, 181.9),
    },
    # TR-808, p.70: Roland's own drum machine, every note a patch on tr808.py
    # FITTED to a real 808 (Michael Fischer's recordings; examples/tr808_fit.py).
    # The six toms are the machine's three tom circuits at two tunings each:
    # 41, 45, 48 at their fitted hits' own pitches, 43, 47, 50 where FluidR3
    # plays them (Fischer's recordings repitched 2-3.5 semitones up, past the
    # TUNING knob's reach -- a fill's six steps). The clap (39) is not in
    # Roland's set and stays Standard's.
    25: {
        36: ("808 Bass Drum",    TR808KickProperties, TR808KickProperties.tr808_base_hz),
        37: ("808 Rim Shot",     TR808RimShotProperties, TR808RimShotProperties.tr808_base_hz),
        38: ("808 Snare Drum",   TR808SnareProperties, TR808SnareProperties.tr808_base_hz),
        41: ("808 Low Tom 2",    TR808TomProperties, TR808TomProperties.tr808_base_hz),
        42: ("808 CHH",          TR808ClosedHatProperties, TR808ClosedHatProperties.tr808_base_hz),
        43: ("808 Low Tom 1",    TR808TomProperties, 116.0),
        44: ("808 CHH",          TR808ClosedHatProperties, TR808ClosedHatProperties.tr808_base_hz),
        45: ("808 Mid Tom 2",    TR808MidTomProperties, TR808MidTomProperties.tr808_base_hz),
        46: ("808 OHH",          TR808OpenHatProperties, TR808OpenHatProperties.tr808_base_hz),
        47: ("808 Mid Tom 1",    TR808MidTomProperties, 172.0),
        48: ("808 Hi Tom 2",     TR808HiTomProperties, TR808HiTomProperties.tr808_base_hz),
        49: ("808 Cymbal",       TR808CymbalProperties, TR808CymbalProperties.tr808_base_hz),
        50: ("808 Hi Tom 1",     TR808HiTomProperties, 260.0),
        56: ("808 Cowbell",      TR808CowbellProperties, TR808CowbellProperties.tr808_base_hz),
        62: ("808 High Conga",   TR808HiCongaProperties, TR808HiCongaProperties.tr808_base_hz),
        63: ("808 Mid Conga",    TR808MidCongaProperties, TR808MidCongaProperties.tr808_base_hz),
        64: ("808 Low Conga",    TR808CongaProperties, TR808CongaProperties.tr808_base_hz),
        70: ("808 Maracas",      TR808MaracasProperties, TR808MaracasProperties.tr808_base_hz),
        75: ("808 Claves",       TR808ClavesProperties, TR808ClavesProperties.tr808_base_hz),
    },
    # ORCHESTRA, p.70: Roland's concert percussion. The hi-hats move to 27-29
    # (EXC1 with 42/44/46: KIT_CHOKE) and a ride to 30; two concert bass
    # drums, a concert snare on both snare keys, Standard's castanets on 39;
    # the TIMPANI chromatically F to f, 41-53 -- F2-F3, so each key's MIDI
    # pitch IS its drum's (FluidR3's 41 rings at 87.3 Hz) -- our fitted GM 47;
    # two concert cymbals; applause. Fitted where VCSL has the instrument
    # (examples/orch_fit.py: GeneralUser GS's sample picks the hit).
    48: {
        27: ("Closed Hi-Hat",    ClosedHiHatProperties, 248.4),
        28: ("Pedal Hi-Hat",     PedalHiHatProperties, 248.4),
        29: ("Open Hi-Hat",      OpenHiHatProperties, 248.4),
        30: ("Ride Cymbal",      RideCymbalProperties, 147.5),
        35: ("Concert BD 2",     ConcertBassDrumProperties, 37.7),
        36: ("Concert BD 1",     ConcertBassDrumProperties, 37.7),
        38: ("Concert SD",       ConcertSnareProperties, 195.1),
        39: ("Castanets",        CastanetsProperties, 268.2),
        40: ("Concert SD",       ConcertSnareProperties, 195.1),
        **{n: ("Timpani " + nm, TimpaniProperties, 440.0 * 2 ** ((n - 69) / 12.0))
           for n, nm in zip(range(41, 54), ("F", "F#", "G", "G#", "A", "A#", "B",
                                            "c", "c#", "d", "d#", "e", "f"))},
        57: ("Concert Cymbal 2", ConcertCymbal2Properties, 333.7),
        59: ("Concert Cymbal 1", ConcertCymbal1Properties, 288.3),
        88: ("Applause",         OrchestraApplauseProperties, 440.0),
    },
    # ROOM, p.70: the six toms, "Room Low Tom 2" to "Room Hi Tom 1" -- Standard's
    # toms placed further back (tonelib.FartherBack), at Standard's pitches.
    8: {
        41: ("Room Low Tom 2",   RoomFloorTomProperties, 87.0),
        43: ("Room Low Tom 1",   RoomFloorTomProperties, 98.0),
        45: ("Room Mid Tom 2",   RoomTomProperties, 110.0),
        47: ("Room Mid Tom 1",   RoomTomProperties, 130.0),
        48: ("Room Hi Tom 2",    RoomHighTomProperties, 150.0),
        50: ("Room Hi Tom 1",    RoomHighTomProperties, 175.0),
    },
    # POWER, p.70: Room's toms, the "MONDO Kick" and the "Gated SD" -- the
    # Electronic set's gated snare (its 40), as the manual names it.
    16: {
        36: ("MONDO Kick",       MondoKickProperties, 44.4),
        38: ("Gated SD",         GatedSnareProperties, 290.0),
        41: ("Room Low Tom 2",   RoomFloorTomProperties, 87.0),
        43: ("Room Low Tom 1",   RoomFloorTomProperties, 98.0),
        45: ("Room Mid Tom 2",   RoomTomProperties, 110.0),
        47: ("Room Mid Tom 1",   RoomTomProperties, 130.0),
        48: ("Room Hi Tom 2",    RoomHighTomProperties, 150.0),
        50: ("Room Hi Tom 1",    RoomHighTomProperties, 175.0),
    },
    # SFX, p.71: 46 sound effects on keys 39-84 and NO drums (KIT_ONLY). Built
    # in batches; the keys a GM sound-effect program already covers first,
    # played at the key it was fitted at (C4; birds at E7, the gunshot at G3).
    56: {
        47: ("Guitar sliding finger", SfxFretSlideProperties, 261.63),
        58: ("Applause",         OrchestraApplauseProperties, 440.0),
        70: ("Helicopter",       SfxHelicopterProperties, 261.63),
        72: ("Gun Shot",         GunshotProperties, 196.0),
        78: ("Birds",            SfxBirdsProperties, 2637.02),
        82: ("Sea Shore",        SfxSeashoreProperties, 261.63),
        79: ("Rain",             SfxRainProperties, 261.63),
        80: ("Thunder",          SfxThunderProperties, 261.63),
        81: ("Wind",             SfxWindProperties, 261.63),
        83: ("Stream",           SfxStreamProperties, 261.63),
        84: ("Bubble",           SfxBubbleProperties, 261.63),
        63: ("Car-Engine",       SfxEngineProperties, 47.42),
        66: ("Car-Crash",        SfxCrashProperties, 261.63),
        68: ("Train",            SfxTrainProperties, 261.63),
        69: ("Jetplane",         SfxJetProperties, 261.63),
        64: ("Car-Skid",         SfxSkidProperties, 1375.0),
        65: ("Car-Pass",         SfxCarPassProperties, 108.0),
        67: ("Siren",            SfxSirenProperties, 738.0),
        71: ("Starship",         SfxStarshipProperties, 2315.0),
    },
    # BRUSH, p.70: the SC-55's jazz set, since its Jazz (32) is Standard. Three
    # notes, all strokes of a brush on the snare, at the snare's own pitch.
    40: {
        38: ("Brush Tap",        BrushTapProperties, 191.8),
        39: ("Brush Slap",       BrushSlapProperties, 171.6),
        40: ("Brush Swirl",      BrushSwirlProperties, 260.0),
    },
}

# A set's own notes do NOT take Standard's per-note ring and level: those were
# measured for the acoustic instrument on that key, and would force a chinese
# cymbal's ring onto a reverse cymbal that must not decay while it swells. A
# built set may give its own here, {program: {note: value}}.
#
# ELECTRONIC'S RINGS: GM 118's decay is a melodic voice's, 1.4 s to -40 dB, which
# is four times a tom and turns a fill into a drone. A Simmons tom is long for a
# drum and short for a note; its kick is a thump with a tail.
# FITTED (examples/elkit_fit.py --target=GeneralUser): the toms shorten up the
# kit; each tuned so the pitch a render reads where it fades (the sweep
# still settling there) is where GeneralUser's reads: ~0.9x its end -- (48 between its neighbours:
# GeneralUser's 47 and 48 both end at 79 Hz).
KIT_RING = {24: {}, 25: {}, 48: {}, 56: {}}     # the Simmons voices' DECAY is their patch's (simmons.py)
# ...AND THEIR GATES: the Electronic toms stop dead where the pad's amplifier
# closes. GeneralUser GS's decay as ours do and then fall 30 dB in under 50 ms
# from about -32 dB -- at 0.70, 0.55 and 0.35 s on 41, 45 and 50 (the rest
# between) -- where ours rang on to -40 at 0.77, 0.64 and 0.46 s and past
# (examples/elkit_fit.py). The note's length, as GatedSnareProperties.gate_time
# is, closing over the class's release_valve_time.
# The Electronic snare too: GeneralUser's stops at 0.31 s, -32 dB.
KIT_GATE = {24: {}, 25: {}, 48: {88: 1.4},
            # the SFX set's held voices, as long as GeneralUser GS's samples ring
            56: {47: 0.3, 58: 3.7, 70: 3.75, 78: 0.4, 82: 2.3,
                 79: 2.75, 80: 1.0, 81: 1.6, 83: 2.75, 84: 0.4,
                 63: 0.64, 66: 1.3, 68: 2.25, 69: 1.81,
                 64: 0.45, 65: 0.75, 67: 1.5, 71: 1.5}}     # the Simmons voices are not gated: their bodies decay (elkit_fit.py --real)
# BRUSH is balanced against its own tap instead: a slap does not replace a
# hand clap nor a swirl an electric snare, whatever key they share. Its tap
# sits 11.3 dB under Standard's snare, where GeneralUser GS keeps its brush
# tap under its own; the slap and swirl against the tap as GeneralUser has
# them (examples/elkit_balance.py --kit=40). It had been judgement (a slap
# ~3 dB over, a swirl ~5.5 under), before the brushes were fitted to
# Swirly Drums' recordings.
#
# ...and its LEVELS, matched to the Standard note each replaces (loudness over
# the first 150 ms, examples/drumset_check.py). A set is a different
# instrument, not a louder one: a file balanced its drums against its band
# with velocities, and swapping the kit must not undo that. (36 and 38 moved
# with Standard's kick and snare when those were rebalanced, -7 and +5 dB.)
# ELECTRONIC'S, 2026-10-15: the snare on the Standard snare (drumset_check.py),
# and every other note where GeneralUser GS sits against ITS snare, K-weighted
# (examples/elkit_balance.py). Each note on its own key's Standard note had
# left the kick 1.2 dB and the toms 4-12 dB under (Ben: "Our kick seems
# quieter").
KIT_LEVEL = {24: {36: 1.697, 38: 0.823, 40: 0.790, 41: 0.945, 43: 0.990, 45: 0.984, 47: 0.992, 48: 0.988, 50: 0.967},
             25: {36: 2.445, 37: 0.298, 38: 0.479, 41: 1.649, 42: 0.151, 43: 1.790, 44: 0.139, 45: 2.023, 46: 0.195, 47: 2.163, 48: 2.523, 49: 0.319, 50: 2.807, 56: 1.763, 62: 2.439, 63: 2.470, 64: 1.675, 70: 0.550, 75: 8.462},
             48: {27: 2.703, 28: 2.143, 29: 0.757, 30: 0.290, 35: 0.092, 36: 0.151, 38: 1.778, 39: 0.514, 40: 1.778, 41: 0.627, 42: 0.631, 43: 0.639, 44: 0.623, 45: 0.621, 46: 0.620, 47: 0.610, 48: 0.612, 49: 0.629, 50: 0.614, 51: 0.625, 52: 0.644, 53: 0.633, 57: 0.551, 59: 0.558, 88: 1.683},
             8: {41: 1.026, 43: 1.013, 45: 1.019, 47: 0.936, 48: 1.453, 50: 1.110},
             16: {36: 0.906, 38: 1.175, 41: 1.043, 43: 1.032, 45: 1.040, 47: 0.944, 48: 1.470, 50: 1.129},
             56: {47: 59.315, 58: 0.137, 63: 0.063, 64: 8.793, 65: 1.407, 66: 1.285, 67: 0.474, 68: 0.785, 69: 0.381, 70: 0.575, 71: 1.119, 72: 3.108, 78: 0.326, 79: 0.025, 80: 1.587, 81: 0.569, 82: 0.111, 83: 0.034, 84: 5.146},
             40: {38: 0.490, 39: 0.570, 40: 0.011}}


class DrumProgram(int):
    """A program number that is a DRUM SET: the channel it was sent on was a
    drum channel when the note began.

    An int, so everything that reads a note's program keeps working; the file
    renderer's note tuple keeps its shape (registrate.py unpacks it), and the
    mono, gliss and rasp passes that rebuild notes carry it without knowing.
    Channel 10 is one from power-on; GM 2's CC0 = 120 makes any channel one,
    and 121 makes it melodic again.
    """
    __slots__ = ()

    def __repr__(self):
        return "DrumProgram(%d)" % int(self)


def is_drum(program):
    return isinstance(program, DrumProgram)


def kit_for_program(program):
    """The drum set a drum-channel program plays: itself if built, else 0."""
    return program if program in KITS else 0


def drum_set_name(program):
    """What the SC-55 calls this program on a drum channel, and whether it
    sounds as itself here."""
    name = DRUM_SETS.get(program)
    if name is None:
        return "%d (Standard)" % program
    if program and program not in KITS and name != "Jazz":
        return "%s (plays Standard)" % name
    return name


# SETS WITHOUT A KIT UNDER THEM: the SFX set (SC-55 p.71) is its effects and
# nothing else, so a key it does not define (or not yet) is silent, not
# Standard's drum on that key -- "Guitar cutting noise" must not be a tom.
KIT_ONLY = {56}


def percussion_for_note(note, kit=0):
    """Return (name, property_class, base_frequency, default_pan) for a GM
    drum note in drum set `kit`, or None if unmapped."""
    own = KITS.get(kit, {}).get(note)
    if own is not None:
        name, cls, freq = own
        return name, _with_ring(cls, note, kit), freq, kit_pan(note)
    if kit in KIT_ONLY:
        return None
    entry = PERCUSSION.get(note)
    if entry is None:
        return None
    name, cls, freq = entry
    return name, _with_ring(cls, note), freq, kit_pan(note)

# How long each instrument actually SOUNDS, in seconds to inaudibility (-60 dB).
#
# Ring time cannot be a property of the class: NoiseDrumProperties covers both a
# closed hi-hat (0.12 s) and an open one (0.70 s), MetalPercussion covers a
# cowbell (0.4 s) and an open triangle (1.5 s). Sharing one decay across a family
# left 37 of these 47 notes ringing more than three times too long -- the cowbell
# and the agogo for nearly eleven seconds -- so every stroke overlapped the next
# and time-keeping parts accumulated into sustained pitched drones.
#
# These are the instruments' own ring times, and the engines set each drum's
# decay from them at note construction.
PERCUSSION_RING = {
    # The kick, the toms, the snare and its side stick (35-38, 41-50) carry their
    # measured rings in their classes (tonelib.KitDrumProperties), mode by
    # mode: a single ring time here would rescale all of them by the first
    # mode's.
    39: 0.100,
    # ONE PLATE, THREE DAMPINGS. These are no longer three separately measured
    # decays: the hats share a mode set and a loss curve, and the ring is the
    # uniform part of the contact damping -- how hard the articulation holds the
    # plate. Fitted against each take's own envelope with everything else held:
    #
    #     closed   1.38 s      pedal   2.65 s      open   0.71 s
    #
    # These are long because the plate's TOP now dies with the strike (see
    # ring_decay_above): what rings for seconds is a middle that is already
    # 25 dB down by 100 ms, not an audible hat hanging over the next beat.
    #
    # The open hat's is FAR below the foot splash's own ~10.9 s T60, and
    # deliberately: Iowa's only long hi-hat take is a splash -- hats opened and
    # left free -- where GM 46 is a stick on hats still loosely together, which
    # damp each other. Same kind of cap as the triangle, and for the same
    # reason: the measurement is of a different gesture.
    #
    # The three used to be 0.35 / 0.21 / 2.00, measured on three different mode
    # sets. The spread mattered more than the values: at 150-400 ms the three
    # rendered 49 dB apart where the recordings sit within 6.8, which is what
    # Ben heard as "the hi-hat tonality seems to differ too much between the 3
    # modes."
    42: 1.38, 44: 2.11, 46: 0.23,
    # MEASURED rings, fitted with each plate's mode set against its recording.
    49: 0.61, 51: 0.50, 52: 0.62,
    # MEASURED: -10 dB at 0.17 s, -20 at 0.69, -40 at 2.69 -> T60 near 4 s.
    53: 0.34, 55: 0.41,
    # (56, 60-68 carry their measured rings in their classes:
    #  tonelib.MeasuredStrokeProperties, fitted by examples/perc_fit.py)
    57: 1.69, 58: 0.098, 59: 0.48,
    # (69, 70: shaped noise now, tonelib.ShakenNoiseProperties -- no impacts to ring)
    # (71, 72: blown, not struck -- a held blast of their own length,
    #  tonelib.ShortWhistleProperties / LongWhistleProperties, no ring)
    # A GUIRO IS HELD IN THE HAND, and the hand damps the gourd -- which is also
    # fairly closed. Measured on the Iowa guiro, the envelope after the last
    # ridge falls 10 dB in 3-5 ms and 20 dB in 15-21 ms, against a woodblock's
    # 26 and 50 ms and a clave's 53 and 62. It is the SHORTEST wooden sound in
    # the kit, not a middling one.
    #
    # This matters more here than anywhere else because the ridges are 13 ms
    # apart: any ring that outlives that spacing stacks nine strokes into a held
    # tone at the body pitch. At 0.035 the tail still reached -40 dB only after
    # 49 ms, four ridges later.
    #
    # (0.012 and below overflow db_ratio in tonelib -- 60/ring becomes a decay
    # rate that 10**(db/10) cannot represent. 0.020 is comfortably clear of it.)
    73: 0.020, 74: 0.020, 75: 0.184, 76: 0.026,
    77: 0.115,
    # the cuicas HOLD and then stop: a stroke of the stick is gated
    # (tonelib.CuicaProperties.gate_time), and under the gate the GM sets
    # sit within 1-7 dB of their peak (78 to 0.1 s, 79 to 0.15-0.2) -- so a
    # long ring, the gate doing the ending
    78: 1.0, 79: 2.0,
    # A TRIANGLE RINGS FOR A VERY LONG TIME, and 0.60/1.50 was not close.
    # Measured T60 on the Iowa triangles: 12.8 s on the 8" and 30.0 s on the 6".
    # Held to 6.0 and 2.0 rather than the measured figures: the open triangle is
    # the longest ring in the kit by a wide margin either way, and a 30 s tail
    # on a note that repeats is a slab full of partials that never release.
    80: 2.10, 81: 4.357,
    # castanets are a dry clack; a belltree rings like the crotale it is
    85: 0.163, 84: 8.00,
    # a surdo rings long open and is stopped dead by the hand
}


COMPOSITE_SLOWDOWN = 1.85    # measured across the kit; see _with_ring

# Per-note level trim, as a multiplier on the family's gain.
#
# Level cannot be a property of the class either, for the same reason ring time
# could not: NoiseDrumProperties carries both the hi-hats and the guiro, and
# quietening the hats buried the guiro 16 dB under the kick. A scraped note is
# also intrinsically quiet in this model -- its energy is spread over a train of
# 35 ms ridges rather than concentrated in one hit -- so it needs the trim even
# before the hats are touched.
PERCUSSION_LEVEL = {
    # THE TRIANGLE IS AN ORCHESTRAL COLOUR, NOT A LEAD. Ben, on Jupiter, at its
    # fitted gain: "very loud, overwhelms the whole orchestra", and again after a
    # channel-volume bug of mine was fixed, "piercingly loud". Measured, the
    # triangle stem alone was +7.9 dB on every other instrument in the movement
    # combined.
    #
    # The Iowa hand-percussion session says the opposite -- there the 8" triangle
    # is +10.3 dB on the claves -- but those are close-mic'd single instruments,
    # the player's ear rather than row H. Ben: "A triangle sounds loud when you
    # are playing it, but it doesn't overpower an orchestra. Something like a
    # guiro, and other latin percussion, is recorded in a smaller band, so it has
    # a higher relative loudness, which is correct." The ensemble is part of what
    # the instrument is, and that is the thing a close mic cannot tell us. So the
    # latin and hand percussion keep their recorded prominence; this does not.
    #
    # 16.2 dB, which is where his ear put it once the roll was actually audible.
    # A Jupiter roll is 154 strokes at velocity 125 with a 4.4 s ring, so it
    # accumulates about 20 dB over a single stroke no matter what this says --
    # that part is real and belongs to the score, not to the gain.
    73: 5.0, 74: 5.0,        # guiro: energy spread across the ridges
    # ...and the rattles for the same reason: a shake is now a burst of impacts,
    # each ringing 10-12 ms instead of one 250 ms hit, so the energy is spread
    # across dozens of them. The whistles moved from the drum family to the pipe
    # family, which changes their level too; each is trimmed back to exactly
    # where it sat before, so this commit changes what they ARE and not the mix.
    54: 1.1874, # tambourine +1.6 dB
    69: 2.1697, # cabasa +28.9 dB
    70: 2.6794, # maracas +30.3 dB
    71: 87.7984,  # whistle short, held at its old level (fitted to VCSL's ball whistle: -4.28 dB without)
    72: 82.4220, # whistle long, held at its old level (-8.77 dB without)
    # The open hat sat 9.4 dB above the closed one. An open hat IS louder -- more
    # metal is free to move -- but not by that much; on a kit it is a few dB, and
    # at nine the closed strokes vanish between the open ones.
    # ...and both hats then sat too close to the crash -- the open one only 1.6 dB
    # under it. A crash is the loudest thing a kit does; hats live well below it,
    # nearer the ride. Both dropped 5 dB, keeping the 3.5 dB open/closed gap.
    42: 0.87,                # closed
    44: 0.87,                # pedal, to match
    46: 0.47,                # open
    # The crash family then stood ~10 dB over everything else that is made of
    # metal. A crash IS the loudest cymbal, but at that distance it stops being
    # an accent within the kit and becomes an interruption of it.
    49: 0.56, 57: 0.56,      # crash 1 and 2: -5 dB
    52: 0.5513, 55: 0.56,      # china and splash, to match
    # The kick's own class sits at 1/1.05, flagged as near a per-tone ceiling --
    # but that is a limit on the CLASS gain, and the trim is applied on top, so
    # the headroom question is simply whether the rendered tone stays clean.
    # Measured below: it does.
    # ...and +0.94 dB more with the ported cavity: the same energy now sits in
    # two resonances instead of one Bessel cluster, so the same class gain is
    # slightly quieter. The class itself is at its ceiling, and the trim is
    # where the headroom note above says this belongs.
    # ...and then 7 dB down (2026-10-08), with the snare 5 up: the kick sat
    # 11.5 dB over the snare (K-weighted, velocity 100) where FluidR3,
    # GeneralUser GS and MuseScore General all put it within 3 dB of it --
    # and they agree on the kick to 2.5 dB (examples/kit_levels.py). Ben, on
    # a bossa nova: "the bass drum seems rather loud compared to the rest".
    35: 0.7964, 36: 0.7964,      # bass drum
    84: 0.483,       # bell tree -6.3 dB: 22 bars share the gesture
    37: 1.0000,   # held against the wash-floor fix
    55: 0.5533,   # held against the wash-floor fix
    81: 0.1260,   # open triangle -16.2 dB -- see the note above
    80: 0.1472,   # mute triangle -16.2 dB -- see the note above

}
_RING_CLASSES = {}


def _with_ring(cls, note, kit=0):
    """A per-note subclass whose fundamental decays over the instrument's own
    ring time, keeping the family's relative rolloff across the harmonics.

    Specialising the CLASS rather than mutating the instance is what makes this
    work in both engines: the partials are built inside the tone's constructor
    from properties that do not exist yet when the note is created, so there is
    no moment at which an instance could be adjusted in time.
    """
    gate = None
    if kit:
        ring = KIT_RING.get(kit, {}).get(note)
        trim = KIT_LEVEL.get(kit, {}).get(note)
        gate = KIT_GATE.get(kit, {}).get(note)
    else:
        ring = PERCUSSION_RING.get(note)
        trim = PERCUSSION_LEVEL.get(note)
    if not ring and not trim and not gate:
        return cls
    key = (cls.__name__, note, kit)
    if key not in _RING_CLASSES:
        target = 60.0 / ((ring or 1.0) * COMPOSITE_SLOWDOWN)
        # The audible ring is the whole sound dying away, not the fundamental
        # alone: the upper partials decay faster, so total energy falls sooner
        # than harmonic 1 does. Solving for harmonic_decay(1) = 60/ring made
        # every drum about 0.55x its intended length when measured on the
        # envelope. COMPOSITE_SLOWDOWN corrects for that, and is itself measured.

        def harmonic_decay(self, harmonic, _cls=cls, _t=target):
            base = _cls.harmonic_decay(self, harmonic)
            first = _cls.harmonic_decay(self, 1)
            return base * (_t / first) if first > 0 else _t

        attrs = {}
        if ring: attrs["harmonic_decay"] = harmonic_decay
        if trim: attrs["initial_gain"] = cls.initial_gain * trim
        if gate: attrs["gate_time"] = gate
        _RING_CLASSES[key] = type("%s_n%d%s" % (cls.__name__, note,
                                               "_k%d" % kit if kit else ""),
                                  (cls,), attrs)
    return _RING_CLASSES[key]

# GM EXCLUSIVE CLASSES. Some percussion is mutually exclusive on one physical
# instrument: closing the hi-hat pedal damps the cymbals, so a closed or pedal
# stroke cuts off a ringing open hat. The same is true of the two whistles, the
# two guiros, the two cuicas and the two triangles -- each pair is one object
# that cannot make both sounds at once.
#
# Without this the open hat rings on underneath every closed stroke, which is
# audible as soon as the open hat is given any real sustain: the pattern turns
# into a wash instead of alternating open and shut.
PERCUSSION_CHOKE = [
    {42, 44, 46},        # hi-hat: closed / pedal / open
    {71, 72},            # short / long whistle
    {73, 74},            # short / long guiro
    {78, 79},            # mute / open cuica
    {80, 81},            # mute / open triangle
    # mute / open surdo: Roland's EXC6 (SC-55 manual p.70, the drum set table,
    # with the five above as EXC1-5). How a drum part stops a ringing surdo:
    # an 86 after an 87 is the hand landing on the open head -- Ben, on the
    # Freesound take: "the surdo_open original recording seems to have a hand
    # muting it"
    {86, 87},
]

_CHOKE_OF = {}
for _grp in PERCUSSION_CHOKE:
    for _n in _grp:
        _CHOKE_OF[_n] = _grp


# A SET'S OWN EXCLUSIVE CLASSES, where it moves an instrument to other keys:
# the Orchestra set's hi-hats at 27-29 are EXC1 (SC-55 p.70) -- the same class
# as 42/44/46, one pair of cymbals on six keys.
KIT_CHOKE = {48: [{27, 28, 29, 42, 44, 46}]}


def choke_group(note, kit=0):
    """The notes a strike on this one stops, in this drum set."""
    for grp in KIT_CHOKE.get(kit, ()):
        if note in grp:
            return grp
    return _CHOKE_OF.get(note)


# SCRAPED instruments. A guiro is not struck -- a stick is dragged across a
# ridged gourd, and what you hear is the individual ridges going past. As one
# broadband hit with a decay it is just a "shh"; the rasp IS the train of
# impacts, and the ear reads the ridge rate as the character of the stroke.
#
# So a guiro note expands into its ridges, and PERCUSSION_RING gives the ring of
# ONE ridge (35 ms) rather than of the whole gesture.
# The ridges are CARVED INTO THE GOURD, so both strokes cross the same number of
# them -- a short guiro is the same scrape done faster, not a shorter one. Giving
# the short stroke fewer ridges made it a different instrument rather than a
# quicker gesture, and lost the rising ridge-rate that is what actually
# distinguishes the two.
# MEASURED (Iowa guiro.away and guiro.toward, mf): 9 ridges over 0.11 s, a
# median gap of 13 ms, and a body that rings at 1175 Hz.
#
# THE SPACING IS THE INSTRUMENT AND THE DURATION IS THE GESTURE. The ridges are
# carved at a fixed pitch along the gourd, so a longer scrape crosses MORE of
# them at the same rate -- it does not cross the same seventeen more slowly.
# This table held the count fixed at 17 and stretched the time, which made the
# short guiro 8 ms per ridge (nearly twice too fast) and the long one 26 ms
# (twice too slow). Both are 13 ms now.
PERCUSSION_RASP = {
    # MEASURED (Iowa guiro.away and guiro.toward, mf): 27 and 33 ridges over
    # 126 and 151 ms -- a median gap of 4.2 and 4.5 ms, so about 230 ridges per
    # SECOND. A guiro is a fast dense rasp, not a clatter.
    #
    # This was 9 ridges at 13.8 ms, a third of the real density, and that is why
    # it did not sound like anything in particular: the ear hears a scrape as a
    # RATE, and at 72 ridges per second it is a stutter rather than a rip. An
    # earlier count found 13 ms by peak-picking a 64-sample envelope at a high
    # threshold, which sees every third ridge; a 2 ms impact envelope finds them
    # all.
    #
    # The spacing is the instrument and the duration is the gesture, so a long
    # scrape crosses proportionally more of them at the same rate.
    73: (0.13, 30),      # short guiro: one quick rip, as Iowa recorded it
    74: (0.42, 98),      # long guiro: the same 4.3 ms spacing, further along
}


# SHAKEN instruments. A rattle is not one hit either, and it is not a scrape:
# it is a BURST OF MANY SMALL IMPACTS -- seeds against a gourd, ball chain against
# a cylinder, jingles against their pins -- densest just after the shake and
# thinning as the contents settle. Modelled as one broadband hit with a decay it
# is a "chh" with a pitch, which is what these three were: NoiseDrumProperties on
# a tuned base of 600 to 680 Hz. A rattle has no pitch at all.
#
# The difference from a guiro is that a guiro's ridges are CARVED, so its train
# is regular and speeds up as the hand does. A rattle's contents are loose: the
# gaps grow as the burst dies, and the impacts land where they land.
#
# (span seconds, impacts[, fall[, settle s, settle dB[, accent s, accent dB]]]). PERCUSSION_RING then gives the ring of ONE impact,
# exactly as it gives the ring of one guiro ridge.
#
# NO REFERENCE. Iowa has no rattle of any kind, so the counts and spans below are
# physics and judgement, not measurement -- the same footing as the membranes.
# What is not judgement is the STRUCTURE: a burst of impacts rather than a single
# pitched stroke, which is the part that was wrong.
def _settling_rattle(note, on, span, n, fall, settle_s, settle_db, accent_s=0.0, accent_db=0.0, rise_s=0.0,
                     thin=3.0):
    """A shake that SETTLES: (start, end, level, pitch) impacts.

    VSCO's maraca strokes peak and then die away smoothly over 0.25-0.4 s,
    30-40 dB, the seeds settling, with a bump where a few hit again. The
    burst below stopped dead when its last impact rang out -- 60 dB in 20
    ms (Ben: "It seems to be suddenly dying out ... need to diminish in volume
    as it shakes"). So: the shake itself, n impacts over span falling by
    `fall` as before, then the settle -- impacts thinning (their rate halving
    every third of settle_s) and falling settle_db over settle_s.

    AND AT RANDOM. The burst's timing and pitch came from a hash of the
    impact's index, so every maraca note was the same pattern of clicks at
    near-even spacing: a buzz, and the same buzz each time (the tambourine's
    lesson, inside one note). Here every impact time is a Poisson draw and
    every impact its own level (+-3 dB) and pitch scale, seeded by the note
    and its time, so the render is still deterministic.

    THE HAND STOPS. A recorded stroke opens with a spike -- the seeds thrown
    against the gourd together as the hand reverses -- and the body follows
    5-10 dB under it; a uniform burst had no such contrast (Ben, comparing:
    "the timing difference"). accent_s is how long that first throw lasts,
    accent_db how far the rest of the shake sits under it.

    ...BUT THAT SPIKE WAS A SECOND STROKE'S. Two of VSCO's five maraca files
    are two strokes (peaks 85-100 ms apart) and one is three quick hits; the
    single strokes do not open with a spike at all -- they SWELL, 35-75 ms,
    as the seeds get going (Ben heard it first: "a two stroke and a single
    stroke"). rise_s is that swell, a linear ramp of the impacts' level.

    NOT EVERY RATTLE THINS. A maraca's seeds come to rest one by one, so its
    impacts thin (their rate halving `thin` times over the settle, 3); a
    cabasa's beads stay on the ridges and keep scraping as the hand slows --
    its settle is a smooth fade, and thinned three times it broke into lone
    clicks with silence between, 60-70 dB jumps (perc_fit's crackle).
    """
    import math
    import random
    rng = random.Random(note * 1000003 + int(round(on * 1e4)))
    rate0 = n / span
    tau = settle_s / thin / math.log(2.0) if thin > 0 else float("inf")
    out = []
    t = 0.0
    while True:
        r = rate0 if t < span else rate0 * math.exp(-(t - span) / tau)
        t += rng.expovariate(r)
        if t >= span + settle_s:
            break
        if t < span:
            level = (1.0 - fall * t / span) ** 1.4
        else:
            level = (1.0 - fall) ** 1.4 * 10.0 ** (-settle_db * (t - span) / settle_s / 20.0)
        if t >= accent_s:
            level *= 10.0 ** (-accent_db / 20.0)
        if rise_s > 0.0 and t < rise_s:
            level *= t / rise_s
        level *= 10.0 ** (rng.uniform(-3.0, 3.0) / 20.0)
        pitch = 2.0 ** (rng.uniform(-0.31, 0.31))
        out.append((on + t, on + t + 0.9 / r, level, pitch))
    return out or [(on, on + span, 1.0)]


# A VIBRASLAP IS PERIODIC. VSCO's four takes (vibraslap1-4) clatter at a steady
# 55 Hz envelope -- the rod swings at ~27 Hz and the pins strike its box on
# each half -- for 2.4-3.5 s, falling only 7-9 dB over the first 1.5, and the
# length is the instrument's, not the note's: it is struck once and left. So
# not a rattle burst scaled to the gesture, but a train of impacts at the rod's
# rate: (rate Hz, seconds, dB fallen over them, timing jitter as a fraction of
# a period, level scatter dB, and how far the first impact -- the ball's
# strike that sets it going -- stands above). Fitted (examples/perc_fit.py
# vibraslap, 31.3 -> 2.6 dB): each strike rings 0.1 s (PERCUSSION_RING), so
# they overlap into a steady clatter, as smooth as the takes (+-0.35 dB); the
# early impacts' ring carries the attack, and the first stands only 0.55 over.
PERCUSSION_TRAIN = {
    58: (55.0, 2.58, 10.7, 0.08, 0.35, 0.55),
}


def _impact_train(note, on, rate, secs, fall_db, jit, scatter_db, strike_db=0.0):
    """(start, end, level, pitch) for a PERCUSSION_TRAIN note: impacts at a
    steady rate, each its own time (within jit of a period), level and
    pitch, seeded by the note and its time."""
    import random
    rng = random.Random(note * 1000003 + int(round(on * 1e4)))
    out = []
    n = int(rate * secs)
    for k in range(n):
        t = (k + rng.uniform(-jit, jit)) / rate
        level = 10.0 ** ((-fall_db * t / secs + rng.uniform(-scatter_db, scatter_db)
                          + (strike_db if k == 0 else 0.0)) / 20.0)
        out.append((on + max(0.0, t), on + max(0.0, t) + 0.9 / rate, level, 2.0 ** rng.uniform(-0.1, 0.1)))
    return out


PERCUSSION_RATTLE = {
    # (69 and 70, the cabasa and maracas, were here: a settling burst of
    #  impacts, fitted to VSCO's takes. Measured for grain, those takes are
    #  noise, not clicks -- tonelib.ShakenNoiseProperties, whose shake is an
    #  envelope; _settling_rattle stays for whatever does click)
    # (58, the vibraslap, was here: 80 impacts over 1.1 s, a guess. Measured,
    #  it is a periodic train -- see PERCUSSION_TRAIN)
}


# SWEPT instruments. A bell tree is not struck at all: a rod is drawn across
# twenty-odd graduated bars and every one of them rings on, so a single note is a
# GLISSANDO. Roland reads it the same way -- in the GS map note 84 is Belltree,
# and one hit there is a full gliss of the instrument, not one bar.
#
# It differs from a rattle in the one way that matters: a rattle's impacts are
# all the same pitch and thin out as the contents settle, while a bell tree's
# climb (or fall) through the bars and every bar keeps sounding. So these strokes
# carry a PITCH RATIO as well as a time and a level.
#
# (span seconds, bars, semitones swept). PERCUSSION_RING then gives the ring of
# ONE bar, which is seconds -- they are little bells.
#
# NO REFERENCE, and one free choice: the sweep runs upward here, low bars to
# high, which is the commoner notated gesture. Reversing it is the sign of the
# span. Nothing else about the instrument depends on the direction.
PERCUSSION_CASCADE = {
    84: (0.70, 22, 30.0),    # bell tree: 22 bars over 0.7 s, two and a half octaves
}


def rasp_strokes(note, on, off, rng=None):
    """[(on, off, level)] for one scraped note, or None if it is not scraped.

    THE STROKE IS NOT EVEN, and both of the ways it is uneven are MEASURED off
    the Iowa guiro rather than asserted. Ben, who was taught to play one: "I was
    taught to speed up as I swipe, by flicking to the side."

    Pooled across guiro.away and guiro.toward, by position through the stroke:

        position   gap / median   level
         0.0-0.2       1.227      0.348
         0.2-0.4       1.077      0.398
         0.4-0.6       0.998      0.442
         0.6-0.8       0.985      0.605
         0.8-1.0       1.132      0.505

    The hand ACCELERATES and the stroke GETS LOUDER as it goes, then both ease
    over the last fifth as the flick lifts away. The coefficients below are set
    to reproduce those five buckets rather than a least-squares line through
    them: a line fitted across the whole stroke is pulled flat by the lift at
    the end, and understates the acceleration by two thirds.

    This used to say "a scrape starts hard, eases through the middle and lifts
    at the end" and implement the level exactly backwards. The ridges are carved
    at a regular spacing and only the hand varies, so the residual timing jitter
    stays small -- at +-9% it read as sloppy rather than human.
    """
    cascade = PERCUSSION_CASCADE.get(note)
    if cascade is not None:
        span, n, semis = cascade
        if off > on:
            span = max(span, (off - on) * 0.6)
        out = []
        for k in range(n):
            frac = k / float(n - 1) if n > 1 else 0.0
            # the hand eases through the sweep rather than running at one rate
            t = on + span * (frac ** 0.85)
            jitter = ((k * 2654435761) % 1000 / 1000.0 - 0.5) * 0.35 * (span / max(n, 1))
            level = 0.55 + 0.45 * (1.0 - abs(frac - 0.45) / 0.55) ** 2
            ratio = 2.0 ** (semis * frac / 12.0)
            out.append((max(on, t + jitter), t + span / n, level, ratio))
        return out

    train = PERCUSSION_TRAIN.get(note)
    if train is not None:
        return _impact_train(note, on, *train)

    rattle = PERCUSSION_RATTLE.get(note)
    if rattle is not None:
        span, n = rattle[:2]
        # how far the impacts fall across the burst: 0.75 unless the entry
        # says (the maracas, measured, hold up longer -- see their entry)
        fall = rattle[2] if len(rattle) > 2 else 0.75
        # The RATE is the instrument and the duration is the gesture -- the same
        # argument the guiro table makes about carved ridges. A longer shake is
        # more impacts at the same rate, not the same few spread thinner.
        if off > on:
            # ...AND A SHORTER ONE IS FEWER. The floor used to be max(span, ...),
            # so a note briefer than the gesture was stretched UP to a full shake.
            # That doubles a written-out roll: Holst's Jupiter writes its
            # tambourine as 436 separate notes 0.062 s apart, and each became a
            # 0.237 s, 14-impact shake -- 96% of them outlasting the next note,
            # so about 3.8 shakes sounded at once. The player is already shaking;
            # the score is telling us the RATE, and we were adding our own on top.
            #
            # Symmetric now, which is what the rate-is-the-instrument argument
            # actually implies: n scales with the gesture either way and the
            # impact rate is unchanged. Normal notation does not move -- a
            # quarter note at 120 gives want 0.25 s against the tambourine's
            # intrinsic 0.237 -- and `max(2, ...)` keeps a very short note
            # rattling rather than turning into a single click.
            want = (off - on) * 0.5
            n = max(2, min(400, int(round(n * want / span))))
            span = want
        if n < 2:
            return [(on, on + span, 1.0)]
        if len(rattle) > 3:
            return _settling_rattle(note, on, span, n, fall, *rattle[3:])
        # Gaps OPEN as the burst dies -- the contents are loose and settling,
        # which is the opposite of the guiro's carved ridges closing up as the
        # hand accelerates. Level falls with them.
        w = [1.0 + 1.9 * (k / float(n - 1)) for k in range(n)]
        scale = span / sum(w)
        out = []
        t = on
        for k in range(n):
            frac = k / float(n - 1)
            jitter = ((k * 2654435761) % 1000 / 1000.0 - 0.5) * 0.55
            level = (1.0 - fall * frac) ** 1.4
            step = w[k] * scale
            # NO TWO IMPACTS ALIKE. Every seed struck the same note before, forty
            # times a shake, and a repeated identical spectrum is a pitch however
            # flat any one window looks. Real contents hit different parts of the
            # body with different force, so each stroke gets its own pitch scale --
            # the bell tree's per-stroke mechanism, scattered instead of swept.
            pitch = 2.0 ** ((((k * 40503) % 977) / 977.0 - 0.5) * 0.62)
            out.append((max(on, t + step * jitter), t + step * 0.9, level, pitch))
            t += step
        return out

    spec = PERCUSSION_RASP.get(note)
    if spec is None:
        return None
    dur, n = spec
    span = max(dur, (off - on) * 0.5) if off > on else dur
    if n < 2:
        return [(on, on + span, 1.0)]

    # Gap WEIGHTS through the stroke: narrowing as the hand speeds up, then
    # opening again over the last fifth as it lifts. Normalised so the ridges
    # fill exactly `span` however the shape is tuned.
    w = []
    for k in range(n - 1):
        frac = k / float(n - 1)
        g = 1.260 - 0.330 * frac
        if frac > 0.80:
            g += 0.62 * (frac - 0.80) / 0.20
        w.append(g)
    scale = span / sum(w)

    out = []
    t = on
    for k in range(n):
        frac = k / float(n - 1)
        jitter = ((k * 2654435761) % 1000 / 1000.0 - 0.5) * 0.05
        level = (0.318 + 0.400 * frac) / 0.638
        if frac > 0.80:
            level *= 1.0 - 0.30 * (frac - 0.80) / 0.20
        step = (w[k] if k < n - 1 else w[-1]) * scale
        out.append((t + step * jitter, t + step * 0.9, level))
        t += step
    return out
