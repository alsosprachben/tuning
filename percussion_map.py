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
    KickDrumProperties,
    NoiseDrumProperties,
    MetalPercussionProperties,
    SnareDrumProperties,
    CymbalProperties,
    RideBellProperties,
    WoodPercussionProperties,
    CrotaleProperties,
    GuiroProperties,
)

M = MembraneDrumProperties      # pitched membranes: toms, congas, timbales
K = KickDrumProperties          # bass drum: tight low thump
N = NoiseDrumProperties
T = MetalPercussionProperties   # pitched metal/wood (cowbell, agogo, block, ...)
S = SnareDrumProperties
C = CymbalProperties            # crash/ride/splash/china: broadband wash
R = RideBellProperties          # the ride's bell: pitch THROUGH the wash
W = WoodPercussionProperties    # claves, woodblocks: a dry tock, gone at once
P = CrotaleProperties           # tuned discs: the only PLATE here, 1 : 2.08 : 3.41
G = GuiroProperties             # struck wood, but the noisiest of it

# GM note -> (name, bucket, base Hz). Standard GM drum map, notes 35-81.
PERCUSSION = {
    35: ("Acoustic Bass Drum", K, 55.0),
    36: ("Bass Drum 1",        K, 62.0),
    37: ("Side Stick",         S, 340.0),
    38: ("Acoustic Snare",     S, 260.0),
    39: ("Hand Clap",          N, 260.0),
    40: ("Electric Snare",     S, 275.0),
    41: ("Low Floor Tom",      M, 87.0),
    42: ("Closed Hi-Hat",      N, 780.0),
    43: ("High Floor Tom",     M, 98.0),
    44: ("Pedal Hi-Hat",       N, 700.0),
    45: ("Low Tom",            M, 110.0),
    46: ("Open Hi-Hat",        N, 720.0),
    47: ("Low-Mid Tom",        M, 130.0),
    48: ("Hi-Mid Tom",         M, 150.0),
    49: ("Crash Cymbal 1",     C, 520.0),
    50: ("High Tom",           M, 175.0),
    51: ("Ride Cymbal 1",      C, 560.0),
    52: ("Chinese Cymbal",     C, 480.0),
    53: ("Ride Bell",          R, 660.0),
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
    # MEASURED: the Iowa guiro body rings at 1175 Hz, not 520-560 -- and it is a
    # STRUCK WOODEN BODY, not noise. Spectral flatness on one ridge is 0.0044
    # (away) and 0.0056 (toward), against a clave's 0.0002 and a woodblock's
    # 0.0000, where white noise is 1.0. It was on NoiseDrumProperties, which
    # builds a dense inharmonic stack to approximate a hiss, so every ridge
    # arrived as a burst of static instead of a tock. A guiro is a notched gourd
    # and the stick catching a notch excites the body: much closer to a small
    # woodblock struck very fast than to a rattle.
    # 744 Hz is the LOWEST measured mode, which is what mode_ratios[0] means.
    # (1175 was an earlier peak-pick that landed on a different mode.)
    73: ("Short Guiro",        G, 744.0),
    74: ("Long Guiro",         G, 744.0),
    # MEASURED (Iowa hand percussion, mf). Claves ring at 908, 993 and 1216 Hz
    # across the three pairs; 990 is the middle one.
    75: ("Claves",             W, 990.0),
    # The four Iowa woodblocks give f1 x size = 7700 Hz-inches almost exactly
    # (10" 778, 8.5" 853, 6.5" 1234, 5.5" 1406), so HI is the small block and
    # LOW the large one. They were 760 and 620, which is the large block twice.
    76: ("Hi Wood Block",      W, 1400.0),
    77: ("Low Wood Block",     W, 780.0),
    78: ("Mute Cuica",         M, 340.0),
    79: ("Open Cuica",         M, 300.0),
    # MEASURED: the Iowa 6" triangle sounds 1927 Hz and the 8" 1497 -- a
    # triangle is a bent BAR and rings far higher than 1000. Its upper modes
    # come out at 2.0, 3.2, 4.2 and 5.3 x f1, dense and inharmonic as a bent bar
    # should be.
    80: ("Mute Triangle",      T, 1900.0),
    81: ("Open Triangle",      T, 1500.0),
    # GM 85 was simply missing. Iowa's two castanet pairs sound 1247 and 1323 Hz.
    85: ("Castanets",          W, 1290.0),
    # ...and so was 84. A belltree is a stack of small tuned DISCS, which is a
    # crotale in a different mounting -- MEASURED across Iowa's chromatic set,
    # see CrotaleProperties. 1055 Hz is its C6, the bottom of that set.
    84: ("Belltree",           P, 1055.0),
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
    return name, _with_ring(cls, note), freq, DEFAULT_PAN.get(note, 0.0)

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
    35: 0.40, 36: 0.35, 37: 0.15, 38: 0.35, 39: 0.30, 40: 0.30, 41: 0.60,
    42: 0.12, 43: 0.60, 44: 0.10, 45: 0.55, 46: 1.60, 47: 0.50, 48: 0.45,
    49: 4.00, 50: 0.40, 51: 2.50, 52: 3.00, 53: 1.20, 54: 0.50, 55: 2.00,
    56: 0.40, 57: 4.00, 58: 0.50, 59: 2.50, 60: 0.30, 61: 0.35, 62: 0.20,
    63: 0.35, 64: 0.40, 65: 0.30, 66: 0.35, 67: 0.25, 68: 0.30, 69: 0.25,
    70: 0.25, 71: 0.60, 72: 0.80,
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
    73: 0.020, 74: 0.020, 75: 0.20, 76: 0.15,
    77: 0.18, 78: 0.30, 79: 0.50,
    # A TRIANGLE RINGS FOR A VERY LONG TIME, and 0.60/1.50 was not close.
    # Measured T60 on the Iowa triangles: 12.8 s on the 8" and 30.0 s on the 6".
    # Held to 6.0 and 2.0 rather than the measured figures: the open triangle is
    # the longest ring in the kit by a wide margin either way, and a 30 s tail
    # on a note that repeats is a slab full of partials that never release.
    80: 2.00, 81: 6.00,
    # castanets are a dry clack; a belltree rings like the crotale it is
    85: 0.25, 84: 8.00,
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
    73: 5.0, 74: 5.0,        # guiro: energy spread across the ridges
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
    52: 0.56, 55: 0.56,      # china and splash, to match
    # The kick's own class sits at 1/1.05, flagged as near a per-tone ceiling --
    # but that is a limit on the CLASS gain, and the trim is applied on top, so
    # the headroom question is simply whether the rendered tone stays clean.
    # Measured below: it does.
    35: 1.6, 36: 1.6,        # bass drum: +4 dB
}
_RING_CLASSES = {}


def _with_ring(cls, note):
    """A per-note subclass whose fundamental decays over the instrument's own
    ring time, keeping the family's relative rolloff across the harmonics.

    Specialising the CLASS rather than mutating the instance is what makes this
    work in both engines: the partials are built inside the tone's constructor
    from properties that do not exist yet when the note is created, so there is
    no moment at which an instance could be adjusted in time.
    """
    ring = PERCUSSION_RING.get(note)
    trim = PERCUSSION_LEVEL.get(note)
    if not ring and not trim:
        return cls
    key = (cls.__name__, note)
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
        _RING_CLASSES[key] = type("%s_n%d" % (cls.__name__, note), (cls,), attrs)
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
]

_CHOKE_OF = {}
for _grp in PERCUSSION_CHOKE:
    for _n in _grp:
        _CHOKE_OF[_n] = _grp


def choke_group(note):
    """The set of notes this one silences (and is silenced by), or None."""
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


def rasp_strokes(note, on, off, rng=None):
    """[(on, off, level)] for one scraped note, or None if it is not scraped.

    The stroke is not even in LEVEL: a scrape starts hard, eases through the
    middle and lifts at the end. The ridges themselves are, though -- they are
    carved at a regular spacing, and only the hand varies -- so the timing
    jitter is small. At +-9% it read as sloppy rather than human.
    """
    spec = PERCUSSION_RASP.get(note)
    if spec is None:
        return None
    dur, n = spec
    span = max(dur, (off - on) * 0.5) if off > on else dur
    out = []
    for i in range(n):
        frac = i / float(n - 1) if n > 1 else 0.0
        jitter = ((i * 2654435761) % 1000 / 1000.0 - 0.5) * 0.05   # deterministic, +-2.5%
        t = on + span * (frac + jitter / n)
        # hard at the start, easing, with a slight lift at the very end
        level = 0.55 + 0.45 * (1.0 - frac) ** 0.7
        if i == n - 1:
            level *= 0.7
        out.append((t, t + span / n * 0.9, level))
    return out

