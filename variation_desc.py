"""WHAT EACH GS VARIATION CHANGES, in a few words: the picker's description
beside the GS name (livetui.pick_patch), so a musician scanning or searching
the list sees how "Piano 1d" differs from Piano 1 without playing it (Ben:
"the program selector as descriptive as possible"). Each says what differs
from the capital tone above it, in the instrument's own terms -- the stops,
the layer, the setting -- not GS's name again.
"""

VARIATION_DESC = {
    (107, 9): "the taish\u014d koto's drone strings",
    (111, 9): "the pungi's drone pipe",
    (120, 5): "a finger sliding down a bass string",
    (53, 24): 'women singing "lah" and "lan"',
    (39, 22): "Moog: square + triangle 8vb + sub",
    (45, 1): "cellos and basses, plucked",
    (55, 12): "orchestra hit, doubled 8vb, with a cymbal",
    (120, 9): "pizzicato strings, snapped on the board",
    (120, 29): "distortion guitar's pick scrape, up",
    (120, 30): "distortion guitar's pick scrape, down",
    (120, 31): "distortion guitar's pick scrape, backwards",
    # the voices of their own (ethnic, sound effects, the Mellotron): what each is
    (12, 16): "West African balafon: buzzing wooden bars",
    (12, 17): "the balafon played softly: less buzz",
    (12, 24): "slit log drum: two wooden tongues",
    (14, 10): "church bell, its hum doubled an octave down",
    (15, 16): "kanun: the Arabic plucked zither",
    (15, 17): "kanun, brighter",
    (25, 17): "mandolin, brighter, picked near the bridge",
    (25, 18): "mandolin, tremolo-picked",
    (50, 24): "Mellotron: the tape of three violins",
    (56, 8): "flugelhorn: a mellow, conical trumpet",
    (65, 8): "alto sax played out, with vibrato",
    (66, 8): "tenor sax, soft and airy, the reed crackling",
    (71, 8): "bass clarinet, over its whole range",
    (72, 8): "nay: the end-blown Arabic flute",
    (72, 9): "nay, with a tremolo of the breath",
    (73, 16): "Mellotron: the flute tape",
    (75, 8): "kawala: the Egyptian end-blown flute",
    (104, 8): "tanpura, its bridge set for another buzz",
    (104, 16): "tanpura: the Indian drone lute",
    (105, 8): "Afghan rubab: gut strings on goatskin",
    (105, 16): "ektara: one plucked string, its pitch bent",
    (105, 24): "oud: the Arabic fretless lute",
    (105, 32): "pipa: the Chinese pear-shaped lute",
    (107, 16): "kanun: triple courses on a wooden box",
    (108, 9): "bodhr\u00e1n: the Irish frame drum",
    (108, 10): "bodhr\u00e1n, the hand pressed into the skin",
    (109, 8): "didgeridoo: a lip drone, its vowels moving",
    (109, 9): "uilleann pipes: the chanter over its drone",
    (109, 10): "uilleann pipes",
    (109, 11): "uilleann pipes, a grace note on each note",
    (111, 8): "pungi: the snake charmer's reed pipe",
    (111, 16): "hichiriki: the double reed of gagaku",
    (112, 8): "bonang: Javanese kettle gongs",
    (112, 9): "gend\u00e9r: the gamelan's bronze metallophone",
    (112, 10): "gong ageng: the gamelan's great gong",
    (112, 11): "a gamelan in stereo: metallophones and gongs",
    (112, 16): "ceng-ceng: Balinese clashing cymbals",
    (113, 8): "atarigane: the Japanese festival hand gong",
    (118, 13): "the 606's tom, through a valve, on every key",
    (120, 12): "satsuma biwa: the Japanese lute, struck",
    (120, 13): "satsuma biwa, tremolo-picked",
    (122, 16): "pink noise: equal power in every octave",
    (123, 4): "a cat's meow",
    (123, 5): "a dog's growl",
    (124, 10): "a record's surface: hiss, rumble and clicks",
    (125, 10): "Morse code: a letter on each key",
    (125, 12): "a gas burner's roar",
    # pianos and keys
    (0, 8): "wide: keys spread in stereo",
    (0, 16): "dark: worn hammers, soft attack",
    (1, 8): "wide: keys spread in stereo",
    (2, 1): "CP-80 + Rhodes underneath",
    (2, 2): "Rhodes + CP-80 underneath",
    (2, 8): "wide: keys spread in stereo",
    (3, 8): "the bright upright (= 001)",
    (4, 8): "Rhodes as a detuned pair, ±4 c",
    (4, 16): "Rhodes + Wurlitzer layered",
    (4, 24): "the Wurlitzer (= 005)",
    (5, 8): "Wurlitzer as a detuned pair, ±4 c",
    (5, 16): "wide: keys spread in stereo",
    (6, 8): "8' and 4' coupled",
    (6, 16): "wide: keys spread in stereo",
    (6, 24): "octave layer above, -6 dB",
    (11, 8): "wide: keys spread in stereo",
    (12, 8): "wide: keys spread in stereo",
    (14, 8): "a church bell",
    (14, 9): "the church bell (= 014.8)",
    (15, 1): "courses detuned ±6 c",
    # organs: the drawbars (footages) or stops drawn
    (16, 1): "drawbars 16 8 4 2",
    (16, 8): "scanner chorus C3",
    (16, 9): "drawbars 8 4 2-2/3 2",
    # the divider organ (tonelib.DividerOrganProperties): its tabs and couplers
    (16, 16): "Wurlitzer console: Flute 8' and its octave",
    (16, 17): "Wurlitzer console: Flute 8', 4' and 2'",
    (16, 18): "Wurlitzer: Flute, Diapason, Quint, octaves",
    (16, 40): "Wurlitzer pedals: Bourdon 16' and Flute 8'",
    (16, 41): "after the Wurlitzer 4500's lower manual: Melodia and Trombone",
    (16, 32): "all nine drawbars",
    (16, 33): "even drawbars: 16 8 4 2 1",
    (17, 1): "16 5-1/3 8, perc 2nd",
    (17, 8): "scanner chorus C3",
    (17, 32): "16 5-1/3 8 1, perc 3rd",
    (18, 8): "all drawbars, Leslie slow, wheel to fast",
    (18, 16): "Leslie slow",
    (18, 24): "all drawbars, Leslie fast",
    (19, 8): "principal chorus to 15th",
    (19, 16): "principals 16 8 4, mixture",
    (19, 24): "flutes 8 4",
    (19, 32): "flutes 8 4, tremulant",
    (21, 8): "Italian musette: 3 wet reeds",
    # guitars
    (24, 8): "concert ukulele",
    (24, 16): "octave layer above, -6 dB",
    (24, 24): "nylon; harmonics when hit hard",
    (25, 8): "12-string guitar: octave courses",
    (25, 9): "nylon + steel layered",
    (25, 16): "4 unison courses, small body",
    (26, 8): "lap steel, slide",
    (27, 8): "Strat into a chorus pedal",
    (28, 8): "Strat, pickup position 4",
    (30, 8): "held notes swell to feedback",
    (29, 3): "overdriven guitar, more crunch",
    (34, 1): "amp pushed to a mild growl",
    (45, 16): "one violin, bounced bow: a short tick",
    (48, 1): "brighter section (legato)",
    (48, 2): "a chamber orchestra's strings, legato",
    (72, 1): "legato: a held note slurs into the next",
    (30, 1): "legato: overlapping notes hammer on",
    (30, 24): "light palm mute, for chugs",
    (31, 8): "the feedback alone, clean amp",
    (31, 16): "acoustic harmonics (= 031)",
    # synths (bank 8)
    (38, 8): "acid: resonant, squelchy",
    (39, 8): "a resonant peak held high",
    (50, 8): "brighter, quicker swell",
    (62, 8): "punchier, pair 6 c apart",
    (63, 8): "squares: hollower, slower",
    # ensembles
    (48, 8): "strings + brass an octave up",
    (48, 9): "strings + horns, -8 dB",
    (48, 11): "strings + choir aahs",
    (48, 16): "wide: keys spread in stereo",
    (48, 24): "slow strings soft, fast hard",
    (49, 10): "wide: keys spread in stereo",
    (52, 8): "wide: keys spread in stereo",
    (55, 10): "octave layer above, -6 dB",
    (60, 16): "horns detuned ±5 c",
    (61, 8): "section detuned ±4 c",
    (62, 16): "octave layer above, -6 dB",
    (63, 16): "soft brass; Synth Brass 1 hard",
    (63, 17): "soft brass; brass section hard",
    # bells, harps, pans
    (98, 3): "the glockenspiel (= 009)",
    (98, 5): "glockenspiel + tubular bells",
    (98, 18): "harp + glock an octave up",
    (98, 19): "kalimba + crystal",
    (99, 2): "nylon guitar + harp",
    (99, 3): "harp + synth voice",
    (99, 5): "nylon guitar + Rhodes",
    (102, 3): "wide: keys spread in stereo",
    (102, 4): "keys spread wider",
    (102, 5): "spread wider, resonant",
    (104, 1): "duller, damped strings",
    (104, 2): "detuned pair ±8 c",
    (107, 8): "keyed zither (a soprano)",
    # percussion
    (115, 8): "castanets, by pitch",
    (116, 8): "the orchestra set's drum, by pitch",
    (117, 1): "Standard set's tom, by pitch",
    (117, 8): "electronic tom (Simmons)",
    (117, 9): "Room set's tom, by pitch",
    (118, 8): "the 808's mid tom",
    (118, 9): "Simmons tom (Electronic set)",
    (119, 1): "Standard's crash 2, backwards",
    (119, 8): "Standard's snare, backwards",
    (119, 9): "Standard's snare 2, backwards",
    (119, 16): "Standard's kick, backwards",
    (119, 17): "the orchestra set's BD, backwards",
    (119, 24): "Standard's low tom, backwards",
    (119, 25): "Standard's high tom, backwards",
    # sound effects (the SFX set's keys, played by pitch)
    (120, 1): "a muted strum on steel strings",
    (120, 2): "a hand slapping upright strings",
    (120, 3): "cut noise (= 120.1)",
    (120, 4): "cut noise (= 120.1)",
    (120, 6): "fret noise (= 120)",
    (121, 1): "a sax key struck, not blown",
    (122, 1): "rain",
    (122, 2): "a strike: rumble under 250 Hz",
    (122, 3): "a howl at 1 kHz on a rumble",
    (122, 4): "a brook's hiss and trickle",
    (122, 5): "bubbles rising, eleven a second",
    (123, 1): "a bark as a throat",
    (123, 2): "horseshoe clicks, galloping",
    (123, 3): "the SFX set's birds",
    (124, 1): "electronic tone ringer",
    (124, 2): "a hinge's stick-slip",
    (124, 3): "a wooden door slammed",
    (124, 4): "record scratch",
    (124, 5): "metal tubes struck",
    (124, 7): "scratch (= 124.4)",
    (125, 1): "a car engine idling",
    (125, 2): "a handbrake skid",
    (125, 3): "tyres on a wet road",
    (125, 4): "a crash with glass",
    (125, 5): "Helmholtz double siren",
    (125, 6): "a freight train",
    (125, 7): "a jet's roar",
    (125, 8): "a spaceship's hum",
    (125, 9): "a hiss and low bursts",
    (126, 1): "\"ho ho ho\"",
    (126, 2): "a girl's scream",
    (126, 3): "a fist on a body",
    (126, 4): "a heartbeat",
    (126, 5): "a hard shoe on stone",
    (126, 6): "the SFX set's applause",
    (127, 1): "the set's shot every 69 ms",
    (127, 2): "a square swept down",
    (127, 3): "a dynamite blast",
    # the SC-88 map's synth tones (sc88_synth.py: panels on the Moog)
    (35, 4): "Moog: soft saw, glide",
    (38, 1): "Moog: saw + sub, round",
    (38, 9): "Moog: resonant, sliding",
    (38, 10): "Moog: square, resonant pluck",
    (38, 16): "Moog: the 101's resonant saw",
    (39, 1): "Moog: pulse + sub",
    (39, 2): "Moog: two saws, octave",
    (39, 3): "Moog: short sequencer pluck",
    (39, 9): "Moog: oscillator sync",
    (39, 16): "Moog: rubbery, slight glide",
    (39, 17): "Moog: pulse + sub, as the 101",
    (39, 18): "Moog: resonant saw, as the 101",
    (39, 19): "Moog: triangle + sub, soft",
    (50, 1): "Moog: wider pair, slower swell",
    (54, 8): "Moog: voice, wave moving",
    (55, 16): "Moog: lo-fi square + saw hit",
    (62, 1): "Moog: quicker blat, wider pair",
    (62, 9): "Moog: brass, resonant quack",
    (80, 1): "Moog: plain square",
    (80, 2): "Moog: hollow, triangle below",
    (80, 3): "Moog: FM triangles, mellow",
    (80, 4): "Moog: OSC 2 pitch vibrato",
    (80, 5): "Moog: glide, resonant",
    (80, 6): "Moog: narrow pulse + sub",
    (80, 8): "Moog: near sine",
    (81, 1): "Moog: plain saw",
    (81, 2): "Moog: saw + narrow pulse",
    (81, 3): "Moog: filter sweep, glide",
    (81, 4): "Moog: wide detune + sub",
    (81, 5): "Moog: velocity opens filter",
    (81, 6): "Moog: squares, 2 octaves",
    (81, 7): "Moog: saw + noise, snappy",
    (81, 8): "Moog: OSC 2 pitch vibrato",
    (81, 16): "Moog: sync, resonant",
    (82, 1): "Moog: breathy triangle",
    (82, 2): "Moog: pan-pipe triangle",
    (84, 8): "Moog: two saws, driven",
    (86, 1): "Moog: fifths + sub",
    (87, 1): "Moog: saw + square below",
    (87, 2): "Moog: square + sub, plucky",
    (88, 1): "Moog: pad + MF-104 echo",
    (89, 1): "Moog: thicker, + sub",
    (89, 2): "Moog: brassy swell",
    (89, 3): "Moog: rotary filter wobble",
    (89, 4): "Moog: darker, slower",
    (90, 1): "Moog: 80s poly, plucked filter",
    (91, 1): "Moog: choir pad + echo",
    (93, 1): "Moog: decaying tines",
    (93, 2): "Moog: keys panned, slow wobble",
    (95, 1): "Moog: slow sweep",
    (95, 8): "Moog: OSC 2 converging",
    (95, 9): "Moog: wave swimming",
    (95, 10): "Moog: 2 octaves up + echo",
    (96, 1): "Moog: droplets on the octave",
    (96, 2): "Moog: short resonant wood",
    (96, 8): "Moog: clavi pluck pad",
    (97, 1): "Moog: darker soundtrack",
    (97, 2): "Moog: brighter + echo",
    (97, 8): "Moog: two saws, rave stab",
    (98, 1): "Moog: FM mallet",
    (98, 2): "Moog: soft FM, darker",
    (98, 4): "Moog: bright FM glock",
    (98, 6): "Moog: FM bells, long",
    (98, 7): "Moog: FM bells, inharmonic",
    (98, 8): "Moog: FM bells, vibrato",
    (98, 9): "Moog: hard FM bells",
    (98, 16): "Moog: bells + sustain",
    (98, 17): "Moog: bells + air",
    (99, 1): "Moog: darker atmosphere",
    (99, 4): "Moog: square, long release",
    (99, 6): "Moog: slow pad + echo",
    (101, 1): "Moog: faster goblins",
    (101, 2): "Moog: theremin-like glide",
    (102, 1): "Moog: FM bell echoes",
    (102, 2): "Moog: pan flute echoes",
    (102, 6): "Moog: FM piano echoes",
    (103, 1): "Moog: resonant sci-fi",
}

# THE CAPITAL TONES ON THE MOOG, said the same way: a GM name ("Pad 2 (warm)")
# says what a tone is for, not that it is a Moog panel or what the panel does
CAPITAL_DESC = {
    38: "Moog: saw over a 16' saw, round",
    39: "Moog: square + sub, resonant",
    50: "Moog: two saws 7 c apart, swell",
    51: "Moog: slower, darker, 11 c",
    54: "Moog: two saws, sung \"eh\"",
    62: "Moog: saw pair, filter blat",
    63: "Moog: softer, darker, slower",
    80: "Moog: square + sub",
    81: "Moog: two saws, ladder",
    82: "Moog: triangles, open whistle",
    83: "Moog: saw + breath noise",
    84: "Moog: two saws into a valve amp",
    85: "Moog: saws, sung \"ah\"",
    86: "Moog: parallel fifths",
    87: "Moog: lead + octave below",
    88: "Moog: glass bell over a pad",
    89: "Moog: two saws, low, slow swell",
    90: "Moog: open, quick, plucky",
    91: "Moog: saws through \"oh\"",
    92: "Moog: band-pass, bowed glass",
    93: "Moog: FM metal, swelling",
    94: "Moog: squares + air noise",
    95: "Moog: LFO sweeps the filter",
    96: "Moog: FM droplets + echo",
    97: "Moog: widest pair, slow drift",
    98: "Moog: FM bell, struck",
    99: "Moog: saw + breath noise",
    100: "Moog: hard front, open filter",
    101: "Moog: dark, two wobbles",
    102: "Moog: plucky saws + echo",
    103: "Moog: squares, PWM, resonant",
    118: "Moog: pitch-swept triangle tom",
}

# THE REST OF THE CAPITALS: the instrument each is, and what is characteristic
# of it here -- the model, the default registration, how it is played
CAPITAL_DESC.update({
    0: "Steinway model B concert grand",
    1: "an upright piano",
    2: "Yamaha CP-80: strings + piezo",
    3: "the upright, unisons 8-20 c apart",
    4: "Fender Rhodes Mark I (1977)",
    5: "Wurlitzer 200A: reed in a slot",
    6: "English and Flemish harpsichords, 8'",
    7: "Hohner Clavinet D6",
    8: "felt on steel plates",
    9: "steel bars, struck",
    10: "a plucked steel comb",
    11: "aluminium bars; the wheel its motor",
    12: "rosewood bars, dark",
    13: "rosewood bars, bright",
    14: "brass tubes, struck",
    15: "hammered dulcimer",
    16: "Hammond: 16 5-1/3 8, its own speaker",
    17: "Hammond: 888 8, perc 3rd, Leslie slow",
    18: "Hammond: 16 5-1/3 8 1, Leslie fast",
    19: "Grönlund organ: principal 8'",
    20: "harmonium: an 8' and a sharp 4'",
    21: "Hohner on musette: wet reeds",
    22: "Hohner, cupped hands",
    23: "1930 ELA bandoneon: octave reeds",
    24: "classical guitar, nylon strings",
    25: "steel-string flat-top, on a mic",
    26: "Ibanez RG2820, neck humbucker",
    27: "Stratocaster neck pickup, clean",
    28: "Ibanez, palm-muted",
    29: "Ibanez bridge humbucker, crunch",
    30: "Ibanez RG2820, bridge humbucker",
    31: "harmonics: a string touched at a node",
    32: "double bass, plucked",
    33: "Fender Jazz Bass, fingers",
    34: "Fender Jazz Bass, a pick",
    35: "fretless bass",
    36: "slap bass: the thumb",
    37: "slap bass: the popped string",
    40: "a violin section",
    41: "a viola section",
    42: "a cello section",
    43: "a double bass section",
    44: "the section's bow shaking, 11 Hz",
    45: "string sections, plucked",
    46: "concert harp, plucked mid-string",
    47: "five kettledrums",
    48: "four sections by register",
    49: "the section swelling in, slow bow",
    52: "a choir singing \"ah\"",
    53: "voices singing \"oo\"",
    55: "the Fairlight-era stab",
    56: "Bb trumpet",
    57: "tenor and bass trombones",
    58: "tuba",
    59: "trumpet in a Harmon mute",
    60: "French horn",
    61: "trumpets, trombones, tuba by register",
    64: "soprano sax",
    65: "alto sax",
    66: "tenor sax",
    67: "baritone sax",
    68: "oboe",
    69: "cor anglais: the alto oboe",
    70: "bassoon",
    71: "clarinets: Bb, Eb and bass",
    72: "piccolo",
    73: "concert flute, no vibrato",
    74: "baroque recorders",
    75: "closed pipes, breathy",
    76: "air across a bottle's neck",
    77: "breath and edge",
    78: "a person whistling",
    79: "ocarina: a vessel flute",
    104: "jawari + sympathetic strings",
    105: "five strings on a head",
    106: "silk strings, sawari buzz",
    107: "Vietnamese đàn tranh zither",
    108: "plucked metal tines",
    109: "chanter + drones",
    110: "one violin, solo",
    111: "shehnai: a conical double reed",
    112: "crotales: tuned discs",
    113: "two cone bells",
    114: "Caribbean steel pan",
    115: "woodblocks",
    116: "big barrel drum, sticks",
    117: "floor and rack tom by register",
    119: "crash played backwards",
    120: "fingertip on a wound string",
    121: "breath, no note",
    122: "ocean drum: beads on a drumhead",
    123: "falling chirps (sparrows)",
    124: "bell struck 20 times a second",
    125: "blade passes and wash",
    126: "three audiences clapping",
    127: "a pistol shot",
})


# THE MAPS' OWN TONES (patch_map.map_bank: key 128 x map + bank)
VARIATION_DESC.update({
    (3, 128 + 8): "wide: keys spread in stereo",
    (4, 128 + 16): "bell an octave up on hard hits",
    (5, 128 + 16): "bell an octave up on hard hits",
    (62, 128 + 16): "Moog: slow filter swell, wide",
    (63, 128 + 16): "Moog: slower, darker, vibrato",
    (4, 256 + 8): "wide and softer Rhodes",
    (39, 256 + 8): "Moog: FM triangles + sub",
})

# AND WHAT A VOICE IS MODELLED ON, where that is one instrument a word can
# name (examples/gm_coverage.py has the measurements): the pickers show it
# after the GM name -- "Electric Piano 1 (Rhodes)". Display only; GM itself
# stays the GM names (voice_ab.py makes file names of them).
MODELLED = {0: "Steinway", 2: "CP-80", 4: "Rhodes", 5: "Wurlitzer", 7: "Clavinet",
            16: "Hammond", 17: "Hammond", 18: "Hammond", 19: "Gr\u00f6nlund",
            26: "Ibanez", 27: "Stratocaster", 28: "Ibanez", 29: "Ibanez", 30: "Ibanez",
            80: "Moog", 81: "Moog", 107: "\u0110\u00e0n Tranh"}


def patch_desc(program, variation=0):
    """A patch's few words for the pickers (the TUI's, and ui/about.json's
    "desc" for the touch and native ones): a variation's own, else for a
    capital what it is modelled on."""
    if variation:
        return VARIATION_DESC.get((program, variation)) or derived().get((program, variation))
    return CAPITAL_DESC.get(program) or MODELLED.get(program)


# THE DRUM SETS (their programs on a drum part), in a few words each
KIT_DESC = {
    0: "acoustic kit: maple drums, brass cymbals", 1: "acoustic kit, a second set of drums",
    2: "acoustic kit, a third set of drums", 8: "acoustic kit in a live room", 9: "hip-hop kit: sampled breaks",
    10: "jungle kit: fast breakbeat drums", 11: "techno kit: machine drums", 12: "the room kit, panned wide",
    13: "house kit: 909-style drums", 16: "rock kit, gated and big", 24: "Simmons electronic drums",
    25: "the TR-808 drum machine", 26: "dance kit: machine and sampled drums", 27: "the CR-78 rhythm box",
    28: "the TR-606 drum machine", 29: "the TR-707 drum machine", 30: "the TR-909 drum machine",
    32: "jazz kit: small drums, ride cymbals", 33: "the jazz kit, panned wide", 40: "jazz kit with brushes",
    41: "brushes, a second set", 42: "brushes, panned wide", 48: "orchestral percussion: timpani and drums",
    49: "world percussion", 50: "kicks and snares across the keys", 51: "more kicks and snares",
    52: "Asian percussion", 53: "cymbals and claps", 54: "Balinese gamelan percussion",
    55: "Javanese gamelan percussion", 56: "sound effects", 57: "rhythmic effects",
    58: "rhythmic effects, a second set", 59: "rhythmic effects, a third set", 60: "sound effects, a second set",
    61: "voices: shouts and syllables", 62: "cymbals and claps, a second set", 64: "your own set, the first",
    65: "your own set, the second", 127: "the MT-32's drums",
}


def kit_desc(kit):
    return KIT_DESC.get(kit)


# ---- THE REST, DERIVED: every map tone's few words read from what it is
# made of (patch_map's cheap tones, sc88_synth's panels, the MT-32 and
# CM-32P sets), so no patch the engine lists is without them. A hand-written
# line above (VARIATION_DESC) wins over these; these over nothing. Each says
# what the sound is, in a musician's words -- never where it came from.

def _gm_name(p):
    import patches
    return patches.patches.get(p, "program %d" % p)


def _base_words(p, b=0):
    """the source tone's own few words, or its GM name"""
    return (VARIATION_DESC.get((p, b)) if b else None) or CAPITAL_DESC.get(p) or _gm_name(p)


def _drum_name(key, kit=0):
    import percussion_map as PM
    k = PM.KITS.get(kit, {}).get(key) or PM.PERCUSSION.get(key)
    return k[0] if k else "key %d" % key


def _kit_name(kit):
    import percussion_map as PM
    return PM.DRUM_SETS.get(kit, "set %d" % kit)


def _efx_name(e):
    import gsefx
    return gsefx.TYPES.get(tuple(e[0]), "an effect") if e else "an effect"


# (a Moog panel in words: moog.PANEL's units, sc88_synth's notes)
def _wave(v):
    if v < 0.2:
        return "folded"
    if v < 0.42:
        return "triangle"
    if v < 0.59:
        return "saw"
    if v < 0.76:
        return "square"
    return "pulse"


_PLURAL = {"triangle": "triangles", "saw": "saws", "square": "squares", "pulse": "pulses", "folded": "folded waves"}
_INTERVALS = {1: "a semitone", 2: "a tone", 3: "a minor third", 4: "a third", 5: "a fourth", 6: "a tritone",
              7: "a fifth", 8: "a minor sixth", 9: "a sixth", 10: "a seventh", 11: "a major seventh",
              12: "an octave", 14: "a ninth", 15: "a tenth", 16: "a tenth", 17: "an eleventh",
              18: "a sharp 11th", 19: "a twelfth", 21: "a thirteenth", 24: "two octaves"}


def panel_words(k, engine="Moog", extra=()):
    """a whole Messenger panel (knob name -> position) said in a few words"""
    g = lambda n, d=0.0: float(k.get(n, d))
    parts = []
    l1, l2 = g("osc1_level", 0.8), g("osc2_level", 0.0)
    w1, w2 = _wave(g("osc1_wave", 0.5)), _wave(g("osc2_wave", 0.5))
    o1, o2 = int(k.get("osc1_octave", 8)), int(k.get("osc2_octave", 8))
    cents = (g("osc2_freq", 0.5) - 0.5) * 1400.0
    semis = round(cents / 100.0) + 12 * round(__import__("math").log2(o1 / o2)) if o1 and o2 else 0
    if l1 > 0.1 and l2 > 0.1:
        if semis == 0 and abs(cents) < 60:
            s = ("two %s" % _PLURAL[w1]) if w1 == w2 else "%s + %s" % (w1, w2)
            if abs(cents) >= 3:
                s += " %d c apart" % round(abs(cents))
        else:
            iv = _INTERVALS.get(abs(semis), "%d semitones" % abs(semis))
            s = ("two %s %s apart" % (_PLURAL[w1], iv)) if w1 == w2 else \
                "%s + %s %s %s" % (w1, w2, iv, "under" if semis < 0 else "over")
        parts.append(s)
    elif l2 > 0.1:
        parts.append(w2)
    else:
        parts.append(w1)
    if k.get("sync"):
        parts[-1] += ", synced"
    if g("sub_level") > 0.15:
        parts[-1] += " + sub"
    if g("noise_level") > 0.25:
        parts.append("noise")
    hz = 7.9 * 2.0 ** (11.38 * g("cutoff", 0.6))
    mode = int(k.get("mode", 0))
    if mode == 2:
        parts.append("band-pass")
    elif mode == 3:
        parts.append("high-pass")
    elif hz < 450:
        parts.append("dark")
    elif hz > 3000:
        parts.append("bright")
    r = g("resonance")
    if r >= 0.8:
        parts.append("self-oscillating")
    elif r >= 0.4:
        parts.append("resonant")
    eg = g("eg_amount", 0.5) - 0.5
    if g("a_attack") >= 0.38:
        parts.append("slow swell")
    elif g("a_attack") >= 0.15:
        parts.append("soft attack")
    elif g("a_sustain", 1.0) < 0.3:
        parts.append("plucked")
    elif eg > 0.15 and g("f_decay", 0.5) < 0.25 and g("f_sustain", 1.0) < 0.6:
        parts.append("filter pluck")
    if g("a_release") >= 0.49:
        parts.append("long release")
    lfo = g("lfo1_depth", 0.5) - 0.5
    if abs(lfo) > 0.08:
        parts.append({0: "filter wobble", 1: "vibrato", 2: "wave sweep"}.get(int(k.get("lfo1_dest", 0)), "LFO"))
    if g("glide") > 0.05:
        parts.append("glide")
    # (an effect it plays through, before the lesser words that may be dropped)
    parts[1:1] = list(extra)
    head = engine + ": "
    return head + _fit_words(parts, CAP - len(head))


def _synth_engine(nm, pan):
    """which synth a map tone's panel is voiced as, by its GS name (gm_coverage's rules)"""
    import sc88_synth as S
    if nm.startswith(("MG", "WowMG")):
        return "Minimoog", S.MINIMOOG
    if nm in ("OB Brass", "OB Square", "OB Saw 1", "OB Saw 2", "OB Saw Lead"):
        return "Oberheim", S.OBERHEIM
    if nm.startswith("JUNO") and pan.get("insertion_efx") in (S.JUNO_CHORUS1, S.JUNO_CHORUS2):
        return "Juno-6", S.JUNO
    if nm in ("TB303 Bass 2", "Kicked TB303", "TB303 Saw Bs", "Rubber303 Bs", "Reso 303 Bs", "303 Sqr Bs",
              "TB303 DistBs", "TB Lead", "Acid Guitar1", "Acid Guitar2"):
        return "TB-303", S.TB303
    if nm in ("Syn.Bass101", "Reso SHBass", "SH101Bass 1", "SH101Bass 2", "SH101 Bass 3", "SH-101 Saw"):
        return "SH-101", S.SH101
    if nm in ("SH-5 Brass", "SH-5 Bs.Lead"):
        return "SH-5", S.SH5
    if nm in ("CS Bass", "CS Saw", "CS Saw Lead"):
        return "Yamaha CS", S.CS
    if nm in ("D-50 Saw", "D-50 Fat Saw", "D-50 Organ"):
        return "D-50", S.D50
    if nm.startswith(("JP", "JPMG")):
        return "Jupiter-8", S.JUPITER
    return "Moog", {}


def _synth_tones():
    """{(program, bank): (GS name, base class name, panel changes)} -- every map's synth tones"""
    import sc88_synth as S
    out = dict(S.SC88_SYNTH)
    out.update({(p, 128 * m + b): t for (m, p, b), t in S.MAP_SYNTH.items()})
    import patch_map as P
    for (p, b), e in S.SC8850_SYNTH.items():
        k = (p, 128 * 4 + b) if (p, b) in P.MAP_OTHER.get(4, ()) else (p, b)
        out.setdefault(k, tuple(e[:3]))
    return out


def _synth_desc(nm, base, pan, _efx=None):
    import tonelib as T
    engine, eng = _synth_engine(nm, pan)
    k = dict(getattr(getattr(T, base, None), "messenger", None) or {})
    k.update(eng)
    k.update({a: v for a, v in pan.items() if isinstance(v, (int, float))})
    extra = ["chorus"] if engine == "Juno-6" else \
        [_efx_name(pan["insertion_efx"]).lower()] if "insertion_efx" in pan else []
    s = panel_words(k, engine, extra)
    if pan.get("unison") or pan.get("supersaw"):
        s = s.replace(engine + ":", engine + ": supersaw,")
    return s


# (a setting changed on a voice, in words: its direction against the voice's own)
def _setting_words(src, attrs, nm=""):
    import patch_map as P
    cls = P.PROGRAM_CLASS.get(src)
    own = lambda a: getattr(cls, a, None) if cls else None
    out = []
    for a, v in attrs.items():
        o = own(a)
        more = (o is not None and isinstance(v, (int, float)) and isinstance(o, (int, float)) and v > o)
        if a == "key_pan_spread":
            out.append("wide stereo")
        elif a == "hammer_corner_hz":
            out.append("harder hammers" if more else "worn hammers")
        elif a == "tonal_dampening":
            out.append("muted" if more else "ringing")
        elif a == "section_players":
            out.append("a solo player" if v == 1 else "two players" if v == 2 else "a section of %d" % v)
        elif a == "sound_bias":
            for bk, bv in v.items():
                w_ = {"attack": "slow attack" if bv > 0 else "quick attack",
                      "brightness": "brighter" if bv > 0 else "darker",
                      "vib_depth": "more vibrato" if bv > 0 else "less vibrato",
                      "vib_rate": "faster vibrato" if bv > 0 else "slower vibrato"}.get(bk)
                if w_:
                    out.append(w_)
        elif a == "amp_drive":
            out.append("clean" if v <= 0.5 else "overdriven" if v < 10 else "distorted")
        elif a == "insertion_efx":
            out.append(_efx_name(v).lower())
        elif a == "detuned_pair":
            out.append("detuned pair ±%g c" % abs(v[1]))
        elif a in ("blare_db_per_khz", "bore_corner_hz", "lowpass_hz", "bell_cutoff_hz"):
            out.append("brighter" if more else "darker")
        elif a == "leslie_fast":
            out.append("Leslie fast" if v else "Leslie slow")
        elif a == "leslie":
            out.append("tremolo")
        elif a in ("one_shot", "gate_time", "speech_cycles", "release_valve_time"):
            out.append("short, detached")
        elif a == "attack_time":
            out.append("slow attack" if more else "quick attack")
        elif a == "cabinet":
            if v:
                out.append({"guitar412": "4x12 cabinet", "guitar12": "1x12 cabinet", "jc120": "JC-120 amp",
                            "bass410": "4x10 bass cabinet", "leslie": "Leslie", "hammond": "Hammond speaker",
                            "direct": "direct", "rhodes": "suitcase speaker"}.get(v, str(v)))
        elif a == "voice_part":
            out.append({"boy": "boys' voices"}.get(v, v))
        elif a == "voice_crossover_hz":
            if "Fem" in nm:
                out.append("women's voices")
            elif "Mal" in nm:
                out.append("men's voices")
        elif a in ("hammer_legato", "slur_cuts_release"):
            out.append("legato")
        elif a == "pickup_deflection":
            out.append("harder, more bark" if more else "mellower")
        elif a in ("chiff_volume", "strike_noise_slope", "strike_noise_len_s", "strike_noise_tail"):
            out.append("sharper attack")
        elif a == "bar_modes":
            out.append("harder mallets")
        elif a in ("noise_gate", "open_string_ring"):
            out.append("gated")
        elif a in ("reed_edge",):
            out.append("brighter reeds" if more else "softer reeds")
        elif a in ("even_harmonic_db",):
            out.append("hollower")
        elif a in ("body_trim_db",):
            out.append("more body")
        elif a in ("tremolo_pick_up_db", "tremolo_pick_jitter"):
            out.append("tremolo-picked")
        elif a == "initial_gain":
            pass
        elif a == "pickup_points":
            pts = list(v) if isinstance(v, (tuple, list)) else [v]
            if len(pts) > 1:
                out.append("two pickups")
            else:
                out.append("bridge pickup" if pts[0] < 0.11 else "neck pickup" if pts[0] > 0.18 else "middle pickup")
        elif a == "clav_pickup":
            out.append("%s pickup" % v)
        elif a in ("strike_point", "pickup_width"):
            out.append("other pickup" if a != "strike_point" else "picked near the bridge")
        elif a == "fall_cents":
            out.append("a fall off the note")
        elif a in ("rip_cents", "rip_s"):
            out.append("a rip up to the note")
        elif a in ("mute_resonance_hz", "mute_response", "plunger"):
            out.append("muted")
        elif a in ("decay_db", "harmonic_decay_db"):
            out.append("muted" if more else "longer ring")
        elif a == "tremolo_pick_hz":
            out.append("tremolo-picked")
        elif a == "formants":
            import re as _re
            m_ = _re.search(r"(Lah|Luh|Lan|Aah|Uuh|Wah|Woh|Ooh|Dah|Dat|Bap|Dow|Thum|Scat|Hum)", nm)
            out.append('sung "%s"' % m_.group(1).lower() if m_ else "another vowel")
        elif a in ("chiff_min_valve_time", "chiff_max_valve_time"):
            out.append("crisper onset")
        elif a == "breath_noise_db":
            out.append("breathy")
        elif a == "section_width_m" or a == "section_spread_cents":
            out.append("wider section")
        elif a == "string_detune_range":
            out.append("more out of tune")
        elif a in ("exp_vibrato_cents", "solo_vibrato_hz"):
            out.append("more vibrato")
        elif a == "default_stops":
            ranks = [r[0] for r in (getattr(cls, "stop_ranks", None) or [])]
            on = [r for i, r in enumerate(ranks) if (v >> i) & 1]
            if src in (16, 17, 18) and len(ranks) >= 9:
                # (a tonewheel registration as players write it: the nine drawbars, 8 out, 0 in)
                d = "".join("8" if (v >> i) & 1 else "0" for i in range(9))
                w = "drawbars %s %s %s" % (d[:3], d[3:6], d[6:])
                perc = [r.split(" B3")[0].split(" L102")[0] for r in on[9:] if r.startswith("perc")]
                out.append(w + (", " + perc[0] if perc else ""))
            elif on:
                out.append(", ".join(on[:2]) + (" +%d stops" % (len(on) - 2) if len(on) > 2 else ""))
            else:
                out.append("other stops")
    if "ringing" in out and "longer ring" in out:
        out.remove("longer ring")
    seen, words = set(), []
    for w in out:
        if w not in seen:
            seen.add(w)
            words.append(w)
    return words


CAP = 44        # (a patch's words: one line of the display, two of a Library button)


def _fit_words(ws, cap=CAP):
    """phrases joined, the last ones dropped until the line fits"""
    ws = list(ws)
    while len(ws) > 1 and len(", ".join(ws)) > cap:
        ws.pop()
    return ", ".join(ws)


def _short_base(p):
    """a voice named shortly: what it is modelled on, else its GM name"""
    m = MODELLED.get(p)
    if m and m != "Moog":
        return {"Gr\u00f6nlund": "Gr\u00f6nlund organ"}.get(m, m)
    n = _gm_name(p)
    return _SHORT.get(n, n)


def _cheap_desc(p, b, how, nm=""):
    kind = how[0]
    if kind == "alias":
        return "%s (= %03d)" % (_base_words(how[1]), how[1])
    if kind == "var":
        return "%s (= %03d.%d)" % (_base_words(*how[1]), how[1][0], how[1][1])
    if kind in ("kit", "rev"):
        n = _drum_name(how[1], how[2])
        if kind == "rev" and not n.lower().startswith("rev"):
            n += ", backwards"
        return n + " on every key"
    if kind == "menu":
        return "%d drums, one on each key from C2" % len(how[1])
    if kind == "set":
        src = how[1]
        words = _setting_words(src, how[2], nm) or ["a variation"]
        head = _short_base(src)
        return _fit_words([head] + words)
    # a layer
    names = []
    for l in how[1]:
        src = l[0]
        if isinstance(src, tuple) and src[0] == "kit":
            n = _drum_name(src[1], src[2])
        elif isinstance(src, tuple) and src[0] == "set":
            n = _short_base(src[1])
            w_ = _setting_words(src[1], src[2], nm)
            if w_:
                n += " (%s)" % w_[0]
        elif isinstance(src, int):
            n = _gm_name(src)
        elif isinstance(src, tuple) and src[0] == "class":
            src = src[1]
            nm_ = getattr(src, "__name__", str(src)).replace("Properties", "")
            n = _CLASS_WORDS.get(nm_.lower(), nm_.lower())
        else:
            nm_ = getattr(src, "__name__", str(src)).replace("Properties", "").lower()
            n = _CLASS_WORDS.get(nm_, nm_)
        n = _SHORT.get(n, n)
        if len(l) > 1 and l[1]:
            n += {12: " 8va", -12: " 8vb", 24: " 15ma", -24: " 15mb"}.get(l[1], " %+d" % l[1])
        if len(l) > 3:
            n += " (hard hits)"
        names.append(n)
    first = names[0]
    out_ = [first] + [("doubled" + n[len(first):]) if n.startswith(first + " ") else n for n in names[1:]]
    s_ = " + ".join(out_).replace(" + doubled", ", doubled")
    if len(s_) > CAP and len(out_) > 3:     # (a big stack: its first voices, and how many more)
        s_ = " + ".join(out_[:2]) + " + %d more" % (len(out_) - 2)
    if len(s_) > CAP:           # (long GM names: their bracketed words dropped)
        import re as _re
        s_ = _re.sub(r" \([^)]*\)", "", s_)
    return s_


# (layers' voices named shortly)
_SHORT = {"Brass Section": "brass", "String Ensemble 1": "strings", "String Ensemble 2": "slow strings",
          "French Horn": "horn", "Orchestra Hit": "orchestra hit", "Tremolo Strings": "tremolo strings",
          "Pizzicato Strings": "pizzicato strings", "Synth Strings 1": "synth strings",
          "Synth Strings 2": "synth strings 2", "Acoustic Grand Piano": "piano", "Bright Acoustic Piano": "upright",
          "Electric Piano 1": "Rhodes", "Electric Piano 2": "Wurlitzer", "Drawbar Organ": "drawbar organ",
          "Percussive Organ": "percussive organ", "Choir Aahs": "choir", "Voice Oohs": "voices",
          "Alto Sax": "alto", "Tenor Sax": "tenor", "Baritone Sax": "baritone", "Trombone": "trombone",
          "Trumpet": "trumpet", "Tuba": "tuba", "Flute": "flute", "Oboe": "oboe", "Clarinet": "clarinet",
          "Bassoon": "bassoon", "Timpani": "timpani", "Guitar harmonics": "harmonics",
          "Overdriven Guitar": "overdriven guitar", "Distortion Guitar": "distortion guitar",
          "Electric Bass (finger)": "finger bass", "Electric Bass (pick)": "picked bass",
          "Acoustic Bass": "double bass", "Acoustic Guitar (steel)": "steel-string guitar",
          "Acoustic Guitar (nylon)": "nylon guitar", "Electric Guitar (jazz)": "jazz guitar",
          "Electric Guitar (clean)": "clean guitar", "Electric Guitar (muted)": "muted guitar",
          "Slap Bass 1": "slap bass", "Slap Bass 2": "slap bass, popped", "Fretless Bass": "fretless bass",
          "Church Organ": "church organ", "Reed Organ": "harmonium", "Orchestral Harp": "harp",
          "Synth Bass 1": "synth bass", "Synth Bass 2": "synth bass 2", "Tango Accordion": "bandoneon"}

_CLASS_WORDS = {"tambra": "tanpura", "tamboura": "tanpura", "oud": "oud", "pipa": "pipa", "kanun": "kanun"}

_DERIVED = None


def derived():
    """{(program, bank): words} for every map tone, MT-32 and CM-32P tone"""
    global _DERIVED
    if _DERIVED is not None:
        return _DERIVED
    import patch_map as P
    out = {}
    tones = list(P.SC88_CHEAP.items()) + list(getattr(P, "SC8850_CHEAP", {}).items())
    tones += [((p, 128 * m + b), v) for (m, p, b), v in getattr(P, "MAP_TONES", {}).items()]
    for (p, b), (nm, how) in tones:
        try:
            out[(p, b)] = _cheap_desc(p, b, how, nm)
        except Exception as e:      # (a tone the rules cannot read: said by hand above)
            out[(p, b)] = None
    for (p, b), (nm, layers) in getattr(P, "_SYN_LAYERED", {}).items():
        out.setdefault((p, b), _cheap_desc(p, b, ("layer", layers)))
    for (p, b), (nm, base, pan) in _synth_tones().items():
        out[(p, b)] = _synth_desc(nm, base, pan)
    for i, (nm, src) in enumerate(P.MT32_SET):
        if isinstance(src, tuple):
            out[(i, 127)] = "our %s, on every key" % _drum_name(src[1])
        else:
            out[(i, 127)] = "our %s (= %03d)" % (_gm_name(src), src)
    for i, (nm, src) in enumerate(P.CM32P_SET):
        out[(i, 126)] = "our %s (= %s)" % (_gm_name(src[0]), "%03d" % src[0] if not src[1] else "%03d.%d" % tuple(src))
    _DERIVED = out
    return out

