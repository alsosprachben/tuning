"""THE INTERFACES' WORDS for what is not a patch: each insertion effect, the
system effects, the organs' stops, the speakers and pickups -- one line each,
saying what the thing is and does, in a musician's words. Written into
ui/about.json by examples/gm_coverage.py --about, beside variation_desc's
patch lines. How each was modelled, and from what, stays in coverage.md
(the credits, ui/credits.json, name the sources); never here.
"""

# THE INSERTION EFFECTS (GS EFX), by gsefx.TYPES's names
EFX_ABOUT = {
    "Thru": "no effect: the part as it is",
    "Stereo-EQ": "two shelves and two mid bands, to shape the tone",
    "Spectrum": "eight fixed bands, a graphic equaliser",
    "Enhancer": "adds brightness: the highs saturated and mixed back",
    "Humanizer": "a talking filter: the formants of a vowel",
    "Overdrive": "a valve pushed into soft clipping, through a 1x12",
    "Distortion": "overdrive with more gain: hard clipping",
    "Phaser": "a sweeping notch, the classic swirl",
    "Auto Wah": "a resonant filter swept by an LFO and by playing",
    "Rotary": "a rotary speaker: horn and drum spinning",
    "Stereo Flanger": "a short swept delay with feedback: a jet sweep",
    "Step Flanger": "a flanger that moves in steps",
    "Tremolo": "the level pulsing",
    "Auto Pan": "the sound moving between the speakers",
    "Compressor": "evens out the level: loud notes held down",
    "Limiter": "holds the peaks under a ceiling",
    "Hexa Chorus": "six chorus voices spread in delay, depth and pan",
    "Tremolo Chorus": "a chorus with the level pulsing",
    "Stereo Chorus": "a chorus on two sides, a wide shimmer",
    "Space D": "a multi-tap chorus, wide and smooth",
    "3D Chorus": "a chorus placed beyond the speakers",
    "Stereo Delay": "echoes left and right, ping-pong if you like",
    "Mod Delay": "echoes with a gentle vibrato",
    "3 Tap Delay": "three echoes: centre, left and right",
    "4 Tap Delay": "four echoes spread across the field",
    "Tm Ctrl Delay": "one echo whose time you can move",
    "Reverb": "a room's reverberation, on this part alone",
    "Gate Reverb": "a short, cut-off reverb: the 80s drum sound",
    "3D Delay": "echoes placed beyond the speakers",
    "2 Pitch Shifter": "two shifted copies: harmonies or detune",
    "Fb P.Shifter": "a shifted echo that climbs as it repeats",
    "3D Auto": "the sound circling around the listener",
    "3D Manual": "the sound placed anywhere around the listener",
    "Lo-Fi 1": "fewer bits and a lower rate: gritty",
    "Lo-Fi 2": "lo-fi with a radio's or a record's noises",
    "OD -> Chorus": "overdrive, then chorus",
    "OD -> Flanger": "overdrive, then flanger",
    "OD -> Delay": "overdrive, then echoes",
    "DS -> Chorus": "distortion, then chorus",
    "DS -> Flanger": "distortion, then flanger",
    "DS -> Delay": "distortion, then echoes",
    "EH -> Chorus": "enhancer, then chorus",
    "EH -> Flanger": "enhancer, then flanger",
    "EH -> Delay": "enhancer, then echoes",
    "Cho -> Delay": "chorus, then echoes",
    "FL -> Delay": "flanger, then echoes",
    "Cho -> Flanger": "chorus, then flanger",
    "Rotary Multi": "overdrive and EQ into a Leslie",
    "GTR Multi 1": "compressor, overdrive, chorus and delay for guitar",
    "GTR Multi 2": "compressor, overdrive and EQ, chorus, for guitar",
    "GTR Multi 3": "compressor, overdrive and wah, for guitar",
    "Clean Gt Multi 1": "compressor, EQ, chorus and delay, clean guitar",
    "Clean Gt Multi 2": "auto wah, EQ, chorus and delay, clean guitar",
    "Bass Multi": "compressor, overdrive, EQ and chorus, for bass",
    "Rhodes Multi": "enhancer, phaser, chorus and tremolo, for keys",
    "Keyboard Multi": "ring modulator, EQ, pitch shift, phaser, delay",
    "Cho / Delay": "chorus and echoes side by side",
    "FL / Delay": "flanger and echoes side by side",
    "Cho / Flanger": "chorus and flanger side by side",
    "OD1 / OD2": "two overdrives side by side",
    "OD / Rotary": "overdrive beside a Leslie",
    "OD / Phaser": "overdrive beside a phaser",
    "OD / AutoWah": "overdrive beside an auto wah",
    "PH / Rotary": "phaser beside a Leslie",
    "PH / AutoWah": "phaser beside an auto wah",
}

# THE SYSTEM EFFECTS every part sends to, and the controller matrix
EFFECTS_ABOUT = {
    "Reverb (system)": "the room every part sends to (CC91)",
    "Chorus (system)": "a shared chorus every part sends to (CC93)",
    "Delay (system)": "shared echoes every part sends to (CC94)",
    "EQ (system)": "low and high shelves on the whole mix",
    "Controller matrix": "what the wheels, aftertouch and two CCs move",
}

# AN ORGAN's REGISTERS: each card's heading line, by program
STOPS_PANEL = {
    6: "the harpsichord's registers",
    16: "the tonewheel organ's nine drawbars",
    17: "the tonewheel organ's nine drawbars",
    18: "the tonewheel organ's nine drawbars",
    19: "the church organ's stops",
    20: "the harmonium's registers, bass and treble",
    21: "the accordion's reed banks: each its own program",
    23: "the bandoneon's reeds: each its own program",
    55: "the orchestra hit's sections",
}

# ...and each stop, by its name on the card
STOP_ABOUT = {
    # the tonewheel's drawbars: each a pitch above (or below) the key
    "16": "the sub-octave: an octave below the key",
    "5-1/3": "a fifth above the key, under the 8'",
    "8": "the key's own pitch",
    "4": "an octave above",
    "2-2/3": "an octave and a fifth above",
    "2": "two octaves above",
    "1-3/5": "two octaves and a third above",
    "1-1/3": "two octaves and a fifth above",
    "1": "three octaves above",
    "perc 2nd B3": "a click of the octave above on each new chord, as a B3",
    "perc 3rd B3": "a click of the twelfth on each new chord, as a B3",
    "perc 2nd L102": "a click of the octave above, as a spinet",
    "perc 3rd L102": "a click of the twelfth, as a spinet",
    # the church organ
    "principal 8": "the organ's main voice: open metal pipes",
    "principal 16": "the main voice an octave down",
    "octave 4": "the principal an octave up",
    "super octave 2": "the principal two octaves up",
    "quint 2-2/3": "a fifth above the octave: brightens the chorus",
    "quint 5-1/3": "a fifth under the 8': deepens the bass",
    "mixture III": "three high ranks at once: the chorus's crown",
    "flute 8": "a stopped flute: round and soft",
    "koppelflute 4": "a flute an octave up, half stopped",
    "waldflute 2": "a bright open flute two octaves up",
    "bourdon 16": "a stopped flute an octave down",
    "subbass 16": "the pedal's deep stopped flute",
    "gamba 8": "a narrow string-toned pipe",
    "celeste 8": "a string tuned a little sharp: it beats with the gamba",
    "nazard 2-2/3": "a flute a twelfth up: a reedy colour with the 8'",
    "tierce 1-3/5": "a flute two octaves and a third up",
    "reed 8": "a chorus reed at pitch",
    "reed 16": "a reed an octave down",
    "reed 4": "a reed an octave up",
    "trumpet 8": "a bright trumpet reed",
    "trompette 8": "a French trumpet reed: brassy",
    "oboe 8": "a thin, nasal reed",
    "vox humana 8": "a short reed meant to sound like a voice",
    "contrabassoon 32": "the deepest reed: two octaves down",
    "tremulant": "the wind shaken: a gentle vibrato on every stop",
    # the harmonium
    "basson 4": "bass reeds an octave up",
    "bourdon 2": "bass reeds, soft and round",
    "celeste": "a second rank tuned sharp: it beats",
    "clairon 3": "bass reeds two octaves up",
    "clarinette 2": "bass reeds with a clarinet's hollow tone",
    "cor anglais 1": "the bass's main reed at pitch",
    "expression": "the bellows played by the feet: the swell follows",
    "fifre 3": "treble reeds two octaves up",
    "flute 1": "the treble's main reed at pitch",
    "hautbois 4": "treble reeds an octave up, nasal",
    "musette": "a treble rank tuned off: the accordion's wobble",
    "percussion": "a hammer on the reed: a quicker start",
    "sourdine": "a softer, damped rank",
    "tremolo": "the wind pulsed",
    "violoncelle": "a treble rank with a string's edge",
    # the orchestra hit
    "bass": "the low strings and brass", "tenor": "the tenor strings", "horn": "the horns",
    "string": "the violins", "tpt": "the trumpets", "wind": "the woodwinds", "picc": "the piccolo",
    # the harpsichord
    "8'": "the main row of strings at pitch",
    "8-upper": "the second 8' row, plucked nearer the end: brighter",
    "lute": "the 8' muted by felt: a lute's dry pluck",
}
# (the harpsichord names its 4' and 8' plainly: said for the instrument, not the tonewheel)
HARPSICHORD_STOP = {"4": "a row of strings an octave up", "8": "the main row of strings at pitch",
                    "8-upper": STOP_ABOUT["8-upper"], "lute": STOP_ABOUT["lute"]}

# THE SPEAKERS the Amp card offers (patch_map.CAB_CHOICES' names)
CAB_ABOUT = {
    None: "the voice's own speaker",
    "direct": "no speaker: the amplifier straight to the desk",
    "leslie": "after the Leslie 122: horn and drum rotors spinning",
    "hammond": "after a Hammond spinet's speaker: a single 12-inch cone",
    "guitar12": "open-backed 1x12 guitar combo",
    "guitar412": "closed-back 4x12 guitar cabinet",
    "jc120": "after the Roland JC-120: a clean 2x12 combo",
    "bass410": "sealed 4x10 bass cabinet",
    "rhodes": "after the Rhodes suitcase: four 12-inch speakers",
    "wurlitzer": "after the Wurlitzer 200's two lid speakers",
    "spectra": "after the Wurlitzer Spectra-Tone: two small speakers back to back, turning on one rotor",
    "spectra_chorus": "after the Spectra-Tone's Chorus: the turning speakers and the console's together",
}

# what the interfaces must not show: how a sound was made, or from whose recording
PROVENANCE = ("VCSL", "VSCO", "Iowa", "Freesound", "Pianobook", "IDMT", "CC0", "CC BY", "fitted", "Fitted",
              "measured", "Measured", ".py", "Ben", " -- ", "derived", "Derived", "recording")


def plain(text):
    """a text with its provenance sentences taken out (a pickup's or a
    speaker's own words, which say both what it is and how it was made)"""
    import re
    out = [s for s in re.split(r"(?<=\.)\s+", text) if not has_provenance(s)]
    return " ".join(out).strip()


def has_provenance(text):
    import re
    return any((re.search(r"\b%s\b" % m, text) if m.isalpha() else m in text) for m in PROVENANCE)


# THE TUNINGS the Tuning card offers (their engine keys): a name, and a line
TUNERS = {
    "hybrid440": ("Hybrid, A=440", "our hybrid temperament at concert pitch"),
    "hybrid": ("Hybrid, A=415", "the hybrid temperament at baroque pitch"),
    "hybridharm": ("Hybrid, pure octaves", "pure 2:1 octaves: right for organ pipes, A=415"),
    "hybridharm440": ("Hybrid, pure octaves, 440", "pure 2:1 octaves at concert pitch"),
    "hybridmean": ("Hybrid mean", "the hybrid's chains joined by a mean third: no wolf"),
    "hybridmeanpiano": ("Hybrid mean, piano", "hybrid mean on a piano's stretched octaves, A=440"),
    "stretchedhelmholtz": ("Stretched Helmholtz", "two pure-fifth chains joined by stretched octaves"),
    "gm2": ("GM2 standard", "the default: equal at A=440, or a file's own"),
    "even": ("Equal", "equal temperament, A=440"),
    "stretch": ("Stretched fifths", "pure fifths; the comma goes into the octaves"),
    "werckmeister": ("Werckmeister III", "a baroque well temperament, A=415"),
    "sankey": ("Sankey", "a Scarlatti tuning found by consonance, A=415"),
    "meantone": ("Meantone", "quarter-comma meantone, A=415"),
    "just": ("Just", "pure ratios from the tonic"),
    "pyth": ("Pythagorean", "pure fifths"),
    "well": ("Well", "a circulating well temperament"),
    "linear": ("Linear", "linear in cents"),
    "linear5": ("Linear, five fifths", "linear over five fifths"),
    "linearwell": ("Linear well", "a linear well temperament"),
    "bechstein": ("Bechstein", "a Bechstein grand's tuning"),
    "spiral": ("Spiral of fifths", "the spiral of fifths, unclosed"),
    "semi": ("Semitones", "semitone-based"),
    "dynamic": ("Dynamic", "solved once over the keyboard"),
    "path": ("Path", "follows a written path of notes"),
    "raga:et@c#": ("Raga, equal", "Indian, Sa on C#: equal, nearest sung Hindustani"),
    "raga:just5@c#": ("Raga, just", "Indian, Sa on C#: 5-limit just intonation"),
    "raga:pythagorean@c#": ("Raga, Pythagorean", "Indian, Sa on C#: Pythagorean"),
    "raga:bel_todi/todi@c#": ("Raga Todi", "Indian, Sa on C#: Todi as sung, near Pythagorean"),
}

# THE EASTERN TUNINGS' systems (the Tuning card's buttons): a name each; the
# measured ragas ("sung_yaman_kalyan") by their raga's name
EASTERN = {"bel_todi": "Todi", "et": "Equal", "just5": "Just", "pythagorean": "Pythagorean"}


def eastern_name(key):
    if key in EASTERN:
        return EASTERN[key]
    if key.startswith("sung_"):
        return key[len("sung_"):].replace("_", " ").title()
    return key.replace("_", " ")


# THE ROOMS (Setup's): their names as a person says them
def room_name(key):
    return key.replace("_", " ")
