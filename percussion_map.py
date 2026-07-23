"""General MIDI percussion key map (channel 10).

On GM channel 10 the note number selects a drum, not a pitch. Each note
maps to (drum name, physical-model bucket, base frequency in Hz). The base
frequency sets where the struck modes sit; the bucket sets the timbre
(membrane / noise / metal). Broad first: three buckets cover the kit, with
per-drum base frequencies. Splitting buckets into distinct kick/snare/hat
models is the realism step.

`percussion_for_note(note)` returns (name, property_class, base_frequency)
or None if the note is unmapped (silent).
"""

from tonelib import (
    MembraneDrumProperties,
    NoiseDrumProperties,
    MetalPercussionProperties,
    SnareDrumProperties,
    CymbalProperties,
)

M = MembraneDrumProperties
N = NoiseDrumProperties
T = MetalPercussionProperties   # pitched metal/wood (cowbell, agogo, block, ...)
S = SnareDrumProperties
C = CymbalProperties            # crash/ride/splash/china: broadband wash

# GM note -> (name, bucket, base Hz). Standard GM drum map, notes 35-81.
PERCUSSION = {
    35: ("Acoustic Bass Drum", M, 55.0),
    36: ("Bass Drum 1",        M, 62.0),
    37: ("Side Stick",         S, 340.0),
    38: ("Acoustic Snare",     S, 260.0),
    39: ("Hand Clap",          N, 260.0),
    40: ("Electric Snare",     S, 275.0),
    41: ("Low Floor Tom",      M, 87.0),
    42: ("Closed Hi-Hat",      N, 400.0),
    43: ("High Floor Tom",     M, 98.0),
    44: ("Pedal Hi-Hat",       N, 360.0),
    45: ("Low Tom",            M, 110.0),
    46: ("Open Hi-Hat",        N, 380.0),
    47: ("Low-Mid Tom",        M, 130.0),
    48: ("Hi-Mid Tom",         M, 150.0),
    49: ("Crash Cymbal 1",     C, 520.0),
    50: ("High Tom",           M, 175.0),
    51: ("Ride Cymbal 1",      C, 560.0),
    52: ("Chinese Cymbal",     C, 480.0),
    53: ("Ride Bell",          T, 660.0),
    54: ("Tambourine",         N, 600.0),
    55: ("Splash Cymbal",      C, 620.0),
    56: ("Cowbell",            T, 540.0),
    57: ("Crash Cymbal 2",     C, 500.0),
    58: ("Vibraslap",          N, 300.0),
    59: ("Ride Cymbal 2",      C, 580.0),
    60: ("Hi Bongo",           M, 260.0),
    61: ("Low Bongo",          M, 200.0),
    62: ("Mute Hi Conga",      M, 230.0),
    63: ("Open Hi Conga",      M, 210.0),
    64: ("Low Conga",          M, 160.0),
    65: ("High Timbale",       M, 270.0),
    66: ("Low Timbale",        M, 220.0),
    67: ("High Agogo",         T, 700.0),
    68: ("Low Agogo",          T, 560.0),
    69: ("Cabasa",             N, 640.0),
    70: ("Maracas",            N, 680.0),
    71: ("Short Whistle",      N, 900.0),
    72: ("Long Whistle",       N, 880.0),
    73: ("Short Guiro",        N, 560.0),
    74: ("Long Guiro",         N, 520.0),
    75: ("Claves",             T, 800.0),
    76: ("Hi Wood Block",      T, 760.0),
    77: ("Low Wood Block",     T, 620.0),
    78: ("Mute Cuica",         M, 340.0),
    79: ("Open Cuica",         M, 300.0),
    80: ("Mute Triangle",      T, 1040.0),
    81: ("Open Triangle",      T, 1000.0),
}

GM_PERCUSSION_CHANNEL = 9  # 0-based; GM drum channel is "10" one-based

# Default stereo placement of each kit piece (drummer's perspective:
# -1 = full left, 0 = center, +1 = full right), so a centered percussion
# channel still spreads the kit across the image instead of stacking every
# drum at one point. A channel pan (CC10) is added on top to rotate the
# whole kit. Kick and snare sit near center; hats to the left, ride/toms
# fanning to the right, crashes to the sides.
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


def percussion_for_note(note):
    """Return (name, property_class, base_frequency, default_pan) for a GM
    drum note, or None if unmapped."""
    entry = PERCUSSION.get(note)
    if entry is None:
        return None
    name, cls, freq = entry
    return name, cls, freq, DEFAULT_PAN.get(note, 0.0)
