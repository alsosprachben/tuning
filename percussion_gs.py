"""The Sound Canvas's drum sets that are rearrangements of voices we have:
each set's keys as Roland's manual lists them (SC-88 Pro owner's manual,
"Native Drum set" and "SC-88 Drum set": examples/gs_drumsets.py parses them),
and for each name Roland uses the voice here that IS that sound -- a key of a
set we built, played as it is or BACKWARDS, or a class at a pitch -- or none
yet. Imported by percussion_map, which builds the sets from it (_build).

A name with no voice of ours is left out of its set: where the set stands on
Standard (Roland's blanks are "same as Standard 1") Standard's voice plays
there, and where it stands alone (KIT_ONLY) the key is silent, not Standard's
drum on a key that means something else. APPROX marks a voice that is the
nearest we have rather than the sound (rated 2 in coverage).
"""

# (map, PC): {key: Roland's name} -- '---' no sound; a key not listed is
# "same as Standard 1"
SETS = {
    ('native', 2): {  # STANDARD 2
        26: 'Finger Snap', 35: 'Standard 2 Kick 2', 36: 'Standard 2 Kick 1',
        38: 'Standard 2 Snare 1', 39: 'Hand Clap', 40: 'Standard 2 Snare 2', 42: 'Closed Hi-Hat',
        44: 'Pedal Hi-Hat', 46: 'Open Hi-Hat', 84: 'Bar Chimes', 89: '---', 90: '---', 91: '---',
        92: '---', 93: '---', 94: '---', 95: '---', 96: '---',
    },
    ('native', 3): {  # STANDARD 3: Standard's kit, [RND] -- each strike varied
        35: 'Standard 3 Kick 2', 36: '[RND] Kick', 38: '[RND] Snare', 39: '[RND] Hand Clap',
        40: 'Standard 3 Snare 2', 42: '[RND] Closed Hi-Hat', 44: '[RND] Pedal Hi-Hat',
        46: '[RND] Open Hi-Hat', 49: '[RND] Crash Cymbal', 51: '[RND] Ride Cymbal 1',
        53: '[RND] Ride Bell 1', 59: '[RND] Ride Cymbal 2', 89: '---', 90: '---', 91: '---',
        92: '---', 93: '---', 94: '---', 95: '---', 96: '---',
    },
    ('native', 10): {  # HIP-HOP
        29: 'Scratch Push 2', 30: 'Scratch Pull 2', 35: 'Hip-Hop Kick 2', 36: 'Hip-Hop Kick 1',
        37: 'TR-808 Rim Shot', 38: 'Rap Snare', 40: 'Hip-Hop Snare 2', 41: 'TR-909 Low Tom 2',
        42: 'Room Closed Hi-Hat', 43: 'TR-909 Low Tom 1', 44: 'Pedal Hi-Hat', 45: 'TR-909 Mid Tom 2',
        46: 'Room Open Hi-Hat', 47: 'TR-909 Mid Tom 1', 48: 'TR-909 High Tom 2', 49: 'TR-909 Crash Cymbal',
        50: 'TR-909 High Tom 1', 52: 'Reverse Cymbal', 54: 'Shake Tambourine', 56: 'TR-808 Cowbell',
        70: 'TR-808 Maracas', 74: 'CR-78 Guiro', 75: 'TR-808 Claves', 78: 'High Hoo', 79: 'Low Hoo',
        80: 'Mute Triangle', 81: 'Open Triangle', 82: 'TR-626 Shaker', 88: 'Small Club 1',
        89: '---', 90: '---', 91: '---', 92: '---', 93: '---', 94: '---', 95: '---', 96: '---',
    },
    ('native', 12): {  # TECHNO
        29: 'Scratch Push 2', 30: 'Scratch Pull 2', 35: 'Techno Kick 2', 36: 'Techno Kick 1',
        37: 'TR-808 Rim Shot', 38: 'Techno Snare 1', 39: 'TR-707 Hand Clap', 40: 'Techno Snare 2',
        41: 'TR-808 Low Tom 2', 42: 'TR-707 Closed Hi-Hat', 43: 'TR-808 Low Tom 1',
        44: 'CR-78 Closed Hi-Hat', 45: 'TR-808 Mid Tom 2', 46: 'TR-909 Open Hi-Hat',
        47: 'TR-808 Mid Tom 1', 48: 'TR-808 High Tom 2', 49: 'TR-909 Crash Cymbal',
        50: 'TR-808 High Tom 1', 52: 'Reverse Cymbal', 54: 'Shake Tambourine', 56: 'TR-808 Cowbell',
        57: 'TR-909 Crash Cymbal', 60: 'CR-78 High Bongo', 61: 'CR-78 Low Bongo',
        62: 'TR-808 High Conga', 63: 'TR-808 Mute Conga', 64: 'TR-808 Low Conga',
        70: 'TR-808 Maracas', 74: 'CR-78 Guiro', 75: 'TR-808 Claves', 78: 'High Hoo', 79: 'Low Hoo',
        80: 'Mute Triangle', 81: 'Open Triangle', 82: 'TR-626 Shaker',
        89: '---', 90: '---', 91: '---', 92: '---', 93: '---', 94: '---', 95: '---', 96: '---',
    },
    ('native', 11): {  # JUNGLE
        29: 'Scratch Push 2', 30: 'Scratch Pull 2', 35: 'Jungle Kick 2', 36: 'Jungle Kick 1',
        38: 'Jungle Snare 1', 39: 'Hand Clap 2', 40: 'Jungle Snare 2', 41: 'TR-909 Low Tom 2',
        42: 'TR-606 Closed Hi-Hat', 43: 'TR-909 Low Tom 1', 44: 'Jungle Hi-Hat', 45: 'TR-909 Mid Tom 2',
        46: 'TR-606 Open Hi-Hat', 47: 'TR-909 Mid Tom 1', 48: 'TR-909 High Tom 2',
        49: 'TR-808 Crash Cymbal', 50: 'TR-909 High Tom 1', 52: 'Reverse Cymbal',
        54: 'Shake Tambourine', 56: 'TR-808 Cowbell', 70: 'TR-808 Maracas', 74: 'CR-78 Guiro',
        75: 'TR-808 Claves', 78: 'High Hoo', 79: 'Low Hoo', 80: 'Mute Triangle', 81: 'Open Triangle',
        82: 'TR-626 Shaker', 88: 'Small Club 1',
        89: '---', 90: '---', 91: '---', 92: '---', 93: '---', 94: '---', 95: '---', 96: '---',
    },
    ('native', 50): {  # ETHNIC
        25: 'Finger Snap', 26: 'Tambourine', 27: 'Castanets', 28: 'Crash Cymbal 1',
        29: 'Snare Roll', 30: 'Concert SD', 31: 'Concert Cymbal', 32: 'Concert BD 1',
        33: 'Jingle Bell', 34: 'Bell Tree', 35: 'Bar Chimes', 36: 'Wadaiko', 37: 'Wadaiko Rim',
        38: 'Shime Taiko', 39: 'Atarigane', 40: 'Hyoushigi', 41: 'Ohkawa', 42: 'High Kotsuzumi',
        43: 'Low Kotsuzumi', 44: 'Ban Gu', 45: 'Big Gong', 46: 'Small Gong', 47: 'Bend Gong',
        48: 'Thai Gong', 49: 'Rama Cymbal', 50: 'Gamelan Gong', 51: 'Udo Short', 52: 'Udo Long',
        53: 'Udo Slap', 54: 'Bendir', 55: 'Req Dum', 56: 'Req Tik', 57: 'Tabla Te', 58: 'Tabla Na',
        59: 'Tabla Tun', 60: 'Tabla Ge', 61: 'Tabla Ge Hi', 62: 'Talking Drum',
        63: 'Bend Talking Drum', 64: 'Caxixi', 65: 'Djembe', 66: 'Djembe Rim', 67: 'Timbales Low',
        68: 'Timbales Paila', 69: 'Timbales High', 70: 'Cowbell', 71: 'High Bongo',
        72: 'Low Bongo', 73: 'Mute High Conga', 74: 'Open High Conga', 75: 'Mute Low Conga',
        76: 'Conga Slap', 77: 'Open Low Conga', 78: 'Conga Slide', 79: 'Mute Pandiero',
        80: 'Open Pandiero', 81: 'Open Surdo', 82: 'Mute Surdo', 83: 'Tamborim', 84: 'High Agogo',
        85: 'Low Agogo', 86: 'Shaker', 87: 'High Whistle', 88: 'Low Whistle', 89: 'Mute Cuica',
        90: 'Open Cuica', 91: 'Mute Triangle', 92: 'Open Triangle', 93: 'Short Guiro',
        94: 'Long Guiro', 95: 'Cabasa Up', 96: 'Cabasa Down', 97: 'Claves', 98: 'High Wood Block',
        99: 'Low Wood Block',
    },
    ('native', 51): {  # KICK & SNARE
        25: 'CR-78 Kick 1', 26: 'CR-78 Kick 2', 27: 'TR-606 Kick', 28: 'TR-707 Kick',
        29: 'TR-808 Kick 1', 30: 'TR-909 Kick 1', 31: 'TR-909 Kick 2', 32: 'Hip-Hop Kick 2',
        33: 'Hip-Hop Kick 1', 34: 'Jungle Kick 2', 35: 'Jungle Kick 1', 36: 'Techno Kick 2',
        37: 'Techno KicK 1', 38: 'Standard 1 Kick 2', 39: 'Standard 1 Kick 1',
        40: 'Standard 1 Kick 1', 41: 'Standard 1 Kick 2', 42: 'Standard 2 Kick 1',
        43: 'Standard 2 Kick 2', 44: 'Kick Drum1', 45: 'Kick Drum 2', 46: 'Soft Kick',
        47: 'Jazz Kick 1', 48: 'Jazz Kick 2', 49: 'Concert BD 1', 50: 'Room Kick 1',
        51: 'Room Kick 2', 52: 'Power Kick1', 53: 'Power Kick2', 54: 'Electric Kick 2',
        55: 'Electric Kick 1', 56: 'Electric Kick', 57: 'TR-808 Kick', 58: 'TR-909 Kick',
        59: 'Dance Kick', 60: 'Standard 1 Snare 1', 61: 'Standard 1 Snare 2',
        62: 'Standard 2 Snare 1', 63: 'Standard 2 Snare 2', 64: 'Tight Snare', 65: 'Concert Snare',
        66: 'Jazz Snare 1', 67: 'Jazz Snare 2', 68: 'Room Snare 1', 69: 'Room Snare 2',
        70: 'Power Snare 1', 71: 'Power Snare 2', 72: 'Gated Snare', 73: 'Dance Snare 1',
        74: 'Dance Snare 2', 75: 'Disco Snare', 76: 'Electric Snare 2', 77: 'House Snare',
        78: 'Electric Snare 1', 79: 'Electric Snare 3', 80: 'TR-808 Snare 1', 81: 'TR-808 Snare 2',
        82: 'TR-909 Snare 1', 83: 'TR-909 Snare 2', 84: 'Brush Tap 1', 85: 'Brush Tap 2',
        86: 'Brush Slap 1', 87: 'Brush Slap 2', 88: 'Brush Slap 3', 89: 'Brush Swirl 1',
        90: 'Brush Swirl 2', 91: 'Brush Long Swirl', 92: 'Standard 1 Snare 1',
        93: 'Standard 1 Snare 2', 94: 'Standard 1 Snare 3', 95: 'Rap Snare', 96: 'Hip-Hop Snare 2',
        97: 'Jungle Snare 1', 98: 'Jungle Snare 2', 99: 'Techno Snare 1',
    },
    ('native', 58): {  # RHYTHM FX
        21: '---', 22: '---', 23: '---', 24: '---', 25: '---', 26: '---', 27: '---', 28: '---',
        29: '---', 30: '---', 31: '---', 32: '---', 33: '---', 34: '---', 35: '---',
        36: 'Reverse Kick 1', 37: 'Reverse Concert Bass Drum', 38: 'Reverse Power Kick1',
        39: 'Reverse Electric Kick 1', 40: 'Reverse Snare 1', 41: 'Reverse Snare 2',
        42: 'Reverse Standard 1 Snare 1', 43: 'Reverse Tight Snare', 44: 'Reverse Dance Snare',
        45: 'Reverse 808 Snare', 46: 'Reverse Tom 1', 47: 'Reverse Tom 2', 48: 'Reverse Sticks',
        49: 'Reverse Slap', 50: 'Reverse Cymbal 1', 51: 'Reverse Cymbal 2',
        52: 'Reverse Open Hi-Hat', 53: 'Reverse Ride Cymbal', 54: 'Reverse CR-78 Open Hi-Hat',
        55: 'Reverse Closed Hi-Hat', 56: 'Reverse Gong', 57: 'Reverse Bell Tree',
        58: 'Reverse Guiro', 59: 'Reverse Bendir', 60: 'Reverse Gun Shot', 61: 'Reverse Scratch',
        62: 'Reverse Laser Gun', 63: 'Key Click', 64: 'Techno Thip', 65: 'Pop Drop',
        66: 'Woody Slap', 67: 'Distortion Kick', 68: 'Syn. Drops', 69: 'Reverse Hi Q', 70: 'Pipe',
        71: 'Ice Block', 72: 'Digital Tambourine', 73: 'Alias', 74: 'Modulated Bell', 75: 'Spark',
        76: 'Metallic Percussion', 77: 'Velocity Noise FX', 78: 'Stereo Noise Clap', 79: 'Swish',
        80: 'Slappy', 81: 'Voice Ou', 82: 'Voice Au', 83: 'Hoo', 84: 'Tape Stop 1',
        85: 'Tape Stop 2', 86: 'Missile', 87: 'Space Birds', 88: 'Flying Monster', 89: '---',
        90: '---', 91: '---', 92: '---', 93: '---', 94: '---', 95: '---', 96: '---',
    },
    ('native', 27): {  # DANCE: the Electronic set's toms, the machines' hats
        26: 'Finger Snap 2', 29: 'Scratch Push 2', 30: 'Scratch Pull 2', 35: 'TR-909 Comp Kick',
        36: 'Electric Kick 2', 38: 'House Snare', 40: 'Dance Snare 2', 41: 'Electric Low Tom 2',
        42: 'CR-78 Closed Hi-Hat', 43: 'Electric Low Tom 1', 44: 'TR-808 Closed Hi-Hat 2',
        45: 'Electric Mid Tom 2', 46: 'CR-78 Open Hi-Hat', 47: 'Electric Mid Tom 1',
        48: 'Electric High Tom 2', 49: 'TR-808 Crash Cymbal', 50: 'Electric High Tom 1',
        51: 'TR-606 Ride Cymbal', 52: 'Reverse Cymbal', 54: 'Shake Tambourine', 56: 'TR-808 Cowbell',
        78: 'High Hoo', 79: 'Low Hoo', 80: 'Mute Triangle', 81: 'Open Triangle', 82: 'TR-626 Shaker',
        88: 'Small Club 1', 89: '---', 90: '---', 91: '---', 92: '---', 93: '---', 94: '---',
        95: '---', 96: '---',
    },
    ('native', 59): {  # RHYTHM FX 2: the machines' and the breaks' drums backwards, then
        # voices and synth effects ("Frog Vpoce", "Reverse bounce" as printed: fixed)
        21: '---', 22: '---', 23: '---', 24: '---', 25: '---', 26: '---', 27: '---', 28: '---',
        29: '---', 30: '---', 31: '---', 32: '---', 33: '---', 34: '---', 35: '---',
        36: 'Reverse TR-707 Kick 1', 37: 'Reverse TR-909 Kick 1', 38: 'Reverse Hip-Hop Kick 1',
        39: 'Reverse Jungle Kick 2', 40: 'Reverse Techno Kick 2', 41: 'Reverse TR-606 Snare 2',
        42: 'Reverse CR-78 Snare 1', 43: 'Reverse CR-78 Snare 2', 44: 'Reverse Jungle Snare 2',
        45: 'Reverse Techno Snare 2', 46: 'Reverse TR-707 Snare', 47: 'Reverse TR-606 Snare 1',
        48: 'Reverse TR-909 Snare 1', 49: 'Reverse Hip-Hop Snare 2', 50: 'Reverse Jungle Snare 1',
        51: 'Reverse House Snare', 52: 'Reverse Closed Hi-Hat',
        53: 'Reverse TR-606 Closed Hi-Hat', 54: 'Reverse TR-707 Closed Hi-Hat',
        55: 'Reverse TR-808 Closed Hi-Hat', 56: 'Reverse Jungle Hi-Hat',
        57: 'Reverse Tambourine 2', 58: 'Reverse Shake Tambourine',
        59: 'Reverse TR-808 Open Hi-Hat', 60: 'Reverse TR-707 Open Hi-Hat',
        61: 'Reverse Open Hi-Hat', 62: 'Reverse TR-606 Open Hi-Hat', 63: 'Reverse Hu Yin Luo',
        64: 'Reverse TR-707 Crash Cymbal', 65: 'Voice One', 66: 'Reverse Voice One',
        67: 'Voice Two', 68: 'Reverse Voice Two', 69: 'Voice Three', 70: 'Reverse Voice Three',
        71: 'Voice Tah', 72: 'Reverse Voice Tah', 73: 'Voice Ou', 74: 'Voice Au',
        75: 'Voice Whey', 76: 'Frog Voice', 77: 'Reverse Yyoo Dude', 78: 'Douby',
        79: 'Reverse Douby', 80: 'Baert High', 81: 'Baert Low', 82: 'Bounce',
        83: 'Reverse Bounce', 84: 'Distortion Knock', 85: 'Guitar Slide', 86: 'Sub Marine',
        87: 'Noise Attack', 88: 'Space Worms', 89: 'Emergency !', 90: 'Calculating...',
        91: 'Saw LFO Saw', 92: '---', 93: '---', 94: '---', 95: '---', 96: '---',
    },
    ('native', 54): {  # CYMBAL & CLAPS: every map's hats, cymbals and claps (the [55]/[88]
        # keys an older map's take of the same sound: our one voice, or a varied strike)
        32: 'Reverse Open Hi-Hat', 33: 'Reverse Closed Hi-Hat 1', 34: 'Reverse Closed Hi-Hat 2',
        35: 'Jungle Hi-Hat', 36: 'Closed Hi-Hat', 37: 'Closed Hi-Hat 2', 38: 'Closed Hi-Hat 3',
        39: 'Closed Hi-Hat 4', 40: 'Closed Hi-Hat', 41: 'TR-707 Closed Hi-Hat',
        42: 'TR-606 Closed Hi-Hat', 43: 'TR-808 Closed Hi-Hat', 44: 'TR-808 Closed Hi-Hat',
        45: 'CR-78 Closed Hi-Hat', 46: 'Pedal Hi-Hat', 47: 'Pedal Hi-Hat', 48: 'Pedal Hi-Hat',
        49: 'Half-Open Hi-Hat 1', 50: 'Half-Open Hi-Hat 2', 51: 'Open Hi Hat',
        52: 'Open Hi-Hat 2', 53: 'Open Hi-Hat 3', 54: 'Open Hi-Hat 2', 55: 'TR-909 Open Hi-Hat',
        56: 'TR-707 Open Hi-Hat', 57: 'TR-606 Open Hi-Hat', 58: 'TR-808 Open Hi-Hat',
        59: 'TR-808 Open Hi-Hat', 60: 'CR-78 Open Hi-Hat', 61: 'Crash Cymbal 1',
        62: 'Crash Cymbal 2', 63: 'Crash Cymbal 3', 64: 'Brush Crash Cymbal',
        65: 'Hard Crash Cymbal', 66: 'TR-909 Crash Cymbal', 67: 'TR-808 Crash Cymbal',
        68: 'Mute Crash Cymbal 1', 69: 'Mute Crash Cymbal 2', 70: 'Reverse Crash Cymbal 1',
        71: 'Reverse Crash Cymbal 2', 72: 'Reverse Crash Cymbal 3',
        73: 'Reverse TR-909 Crash Cymbal', 74: 'Splash Cymbal', 75: 'Splash Cymbal',
        76: 'Ride Bell', 77: 'Brush Ride Bell', 78: 'Ride Cymbal 1', 79: 'Ride Cymbal 2',
        80: 'Brush Ride Cymbal', 81: 'Ride Cymbal Low Inner', 82: 'Ride Cymbal Mid Inner',
        83: 'Ride Cymbal High Inner', 84: 'Ride Cymbal Low Edge', 85: 'Ride Cymbal Mid Edge',
        86: 'Ride Cymbal High Edge', 87: 'TR-606 Ride Cymbal', 88: 'TR-808 Ride Cymbal',
        89: 'Chinese Cymbal', 90: 'Chinese Cymbal 2', 91: 'Hand Clap', 92: 'Hand Clap 2',
        93: 'Hand Clap', 94: 'Hand Clap', 95: 'Hand Clap 2', 96: 'TR-707 Hand Clap',
    },
    ('sc88', 27): {  # DANCE
        29: 'Scratch Push2', 30: 'Scratch Pull2', 35: 'Dance Kick', 36: 'Electric Kick 2',
        38: 'Dance Snare 1', 40: 'Dance Snare 2', 41: 'Electric Low Tom2', 42: 'CR-78 CHH',
        43: 'Electric Low Tom1', 44: '808 CHH', 45: 'Electric Mid Tom2', 46: 'CR-78 OHH',
        47: 'Electric Mid Tom1', 48: 'Electric High Tom2', 50: 'Electric High Tom1',
        52: 'Reverse Cymbal', 78: 'High Hoo', 79: 'Low Hoo', 80: 'Electric Mute Triangle',
        81: 'Electric Open Triangle', 88: '---', 89: '---', 90: '---', 91: '---', 92: '---',
        93: '---', 94: '---', 95: '---', 96: '---', 97: '---', 98: '---', 99: '---',
    },
}

# where each set is kept (percussion_map.KITS): the native ones at their
# program, the SC-88 map's own at 128 x 2 + program (_map_set); and whether
# it stands alone
SET_KIT = {('native', 2): 1, ('native', 3): 2, ('native', 27): 26, ('native', 10): 9, ('native', 11): 10, ('native', 12): 11, ('native', 50): 49, ('native', 51): 50, ('native', 58): 57, ('native', 59): 58, ('native', 54): 53,
           ('sc88', 27): 2 * 128 + 26}
SET_NAME = {1: "Standard 2", 2: "Standard 3", 9: "Hip-Hop", 10: "Jungle", 11: "Techno", 49: "Ethnic", 50: "Kick & Snare", 57: "Rhythm FX", 58: "Rhythm FX 2", 53: "Cymbal & Claps", 26: "Dance", 2 * 128 + 26: "Dance"}
SET_ALONE = {49, 50, 53, 57, 58}

APPROX = 'approx'

# Roland's name -> ('k', set, key[, APPROX]) a voice of ours; ('r', set, key)
# that voice backwards; ('n', set, key) that voice, each strike varied ([RND]); ('c', class name, Hz[, APPROX]) a class at a pitch;
# None: not built yet
VOICE = {
    # kicks
    'Standard 1 Kick 1': ('k', 0, 36), 'Standard 1 Kick 2': ('k', 0, 35),
    # Hip-Hop's machines, from their own sets: the 909's toms and crash, the
    # 808's rim, cowbell, maracas and claves, the CR-78's guiro
    'TR-909 Low Tom 2': ('k', 30, 41), 'TR-909 Low Tom 1': ('k', 30, 43),
    'TR-909 Mid Tom 2': ('k', 30, 45), 'TR-909 Mid Tom 1': ('k', 30, 47),
    'TR-909 High Tom 2': ('k', 30, 48), 'TR-909 High Tom 1': ('k', 30, 50),
    'TR-909 Crash Cymbal': ('k', 30, 49), 'TR-808 Rim Shot': ('k', 25, 37),
    'TR-808 Cowbell': ('k', 25, 56), 'TR-808 Maracas': ('k', 25, 70), 'TR-808 Claves': ('k', 25, 75),
    'CR-78 Guiro': ('k', 27, 74),
    # ...and the nearest we have for its own: the Room set's hats are Standard's
    # here; a second take of a scratch, a shaken tambourine, the 626's shaker
    'Room Closed Hi-Hat': ('k', 0, 42, APPROX), 'Room Open Hi-Hat': ('k', 0, 46, APPROX),
    'Scratch Push 2': ('k', 0, 29, APPROX), 'Scratch Pull 2': ('k', 0, 30, APPROX),
    'Shake Tambourine': ('k', 0, 54, APPROX), 'TR-626 Shaker': ('k', 0, 82, APPROX),
    'High Hoo': ('c', 'HooProperties', 1000.0), 'Low Hoo': ('c', 'HooProperties', 1000.0),
    'Small Club 1': ('c', 'SmallClubProperties', 440.0),
    # the native Dance set's: one snap of ours (Standard's 26); the 909 kick
    # through our valve gently, as a compressor holds it; the Electronic
    # set's toms by their Pro names; the 808 set's own hat (its key 42 IS
    # "TR-808 Closed Hi-Hat 2"); the 606's ride
    'Finger Snap': ('k', 0, 26), 'Finger Snap 2': ('k', 0, 26),
    'TR-909 Comp Kick': ('c', 'TR909CompKickProperties', 49.8),
    'Electric Low Tom 2': ('k', 24, 41), 'Electric Low Tom 1': ('k', 24, 43),
    'Electric Mid Tom 2': ('k', 24, 45), 'Electric Mid Tom 1': ('k', 24, 47),
    'Electric High Tom 2': ('k', 24, 48), 'Electric High Tom 1': ('k', 24, 50),
    'CR-78 Open Hi-Hat': ('k', 27, 46), 'TR-808 Closed Hi-Hat 2': ('k', 25, 42),
    'TR-606 Ride Cymbal': ('k', 28, 51),
    # the Techno set's: the driven 909s (tonelib.TechnoKick1Properties ...), and
    # its machines from their own sets
    'Techno Kick 1': ('c', 'TechnoKick1Properties', 44.4),
    'TR-707 Hand Clap': ('k', 29, 39), 'TR-707 Closed Hi-Hat': ('k', 29, 42),
    'CR-78 Closed Hi-Hat': ('k', 27, 42), 'TR-909 Open Hi-Hat': ('k', 30, 46),
    'TR-808 Low Tom 2': ('k', 25, 41), 'TR-808 Low Tom 1': ('k', 25, 43),
    'TR-808 Mid Tom 2': ('k', 25, 45), 'TR-808 Mid Tom 1': ('k', 25, 47),
    'TR-808 High Tom 2': ('k', 25, 48), 'TR-808 High Tom 1': ('k', 25, 50),
    'CR-78 High Bongo': ('k', 27, 60), 'CR-78 Low Bongo': ('k', 27, 61),
    'TR-808 High Conga': ('k', 25, 62), 'TR-808 Mute Conga': ('k', 25, 63),
    'TR-808 Low Conga': ('k', 25, 64),
    'Techno Snare 2': ('c', 'TechnoSnare2Properties', 233.8),
    # the Jungle set's (tonelib.JungleBreak: breaks sped up), and its others
    'Jungle Hi-Hat': ('c', 'JungleHiHatProperties', 312.9),
    'Hand Clap 2': ('k', 0, 39, APPROX), 'TR-606 Closed Hi-Hat': ('k', 28, 42),
    'TR-606 Open Hi-Hat': ('k', 28, 46), 'TR-808 Crash Cymbal': ('k', 25, 49),
    'Standard 3 Kick 2': ('k', 0, 35, APPROX), 'Standard 3 Snare 2': ('k', 0, 40, APPROX),
    # Standard 3's [RND] voices: Standard's own, each strike varied (tonelib.RandomStrike)
    '[RND] Kick': ('n', 0, 36), '[RND] Snare': ('n', 0, 38), '[RND] Hand Clap': ('n', 0, 39),
    '[RND] Closed Hi-Hat': ('n', 0, 42), '[RND] Pedal Hi-Hat': ('n', 0, 44),
    '[RND] Open Hi-Hat': ('n', 0, 46), '[RND] Crash Cymbal': ('n', 0, 49),
    '[RND] Ride Cymbal 1': ('n', 0, 51), '[RND] Ride Bell 1': ('n', 0, 53),
    '[RND] Ride Cymbal 2': ('n', 0, 59),
    'Standard 2 Kick 1': ('k', 0, 36, APPROX), 'Standard 2 Kick 2': ('k', 0, 35, APPROX),
    'Kick Drum1': ('k', 0, 36), 'Kick Drum 2': ('k', 0, 35), 'Soft Kick': ('k', 0, 35, APPROX),
    'Jazz Kick 1': ('k', 32, 36), 'Jazz Kick 2': ('k', 32, 35), 'Concert BD 1': ('k', 48, 36),
    'Room Kick 1': ('k', 0, 36, APPROX), 'Room Kick 2': ('k', 0, 35, APPROX),
    'Power Kick1': ('k', 16, 36), 'Power Kick2': ('k', 16, 36, APPROX),
    'Electric Kick 1': ('k', 24, 36), 'Electric Kick 2': ('k', 24, 36, APPROX), 'Electric Kick': ('k', 24, 36),
    'TR-808 Kick 1': ('k', 25, 36), 'TR-808 Kick': ('k', 25, 36),
    'TR-909 Kick 1': ('k', 30, 36), 'TR-909 Kick': ('k', 30, 36), 'TR-909 Kick 2': ('k', 30, 35),
    'TR-606 Kick': ('k', 28, 36), 'TR-707 Kick': ('k', 29, 36),
    'CR-78 Kick 1': ('k', 27, 36), 'CR-78 Kick 2': ('k', 27, 35),
    'Dance Kick': ('k', 30, 36, APPROX), 'Hip-Hop Kick 1': ('c', 'HipHopKick1Properties', 37.3),
    'Hip-Hop Kick 2': ('c', 'HipHopKick2Properties', 55.6), 'Techno KicK 1': ('c', 'TechnoKick1Properties', 44.4),
    'Techno Kick 2': ('c', 'TechnoKick2Properties', 49.6), 'Jungle Kick 1': ('c', 'JungleKick1Properties', 52.8),
    'Jungle Kick 2': ('c', 'JungleKick2Properties', 41.7),
    # snares
    'Standard 1 Snare 1': ('k', 0, 38), 'Standard 1 Snare 2': ('k', 0, 40), 'Standard 1 Snare 3': ('k', 0, 38),
    'Standard 2 Snare 1': ('k', 0, 38, APPROX), 'Standard 2 Snare 2': ('k', 0, 40, APPROX),
    'Tight Snare': ('k', 0, 40), 'Concert Snare': ('k', 48, 38), 'Concert SD': ('k', 48, 38),
    'Jazz Snare 1': ('k', 32, 38), 'Jazz Snare 2': ('k', 32, 40),
    'Room Snare 1': ('k', 0, 38, APPROX), 'Room Snare 2': ('k', 0, 40, APPROX),
    'Power Snare 1': ('k', 16, 38), 'Power Snare 2': ('k', 16, 38, APPROX), 'Gated Snare': ('k', 16, 38),
    'Electric Snare 1': ('k', 24, 38), 'Electric Snare 2': ('k', 24, 40), 'Electric Snare 3': ('k', 24, 38, APPROX),
    'TR-808 Snare 1': ('k', 25, 38), 'TR-808 Snare 2': ('k', 25, 38, APPROX),
    'TR-909 Snare 1': ('k', 30, 38), 'TR-909 Snare 2': ('k', 30, 40),
    'Dance Snare 1': ('k', 30, 38, APPROX), 'Dance Snare 2': ('k', 30, 40, APPROX),
    'Disco Snare': ('k', 30, 40, APPROX), 'House Snare': ('k', 30, 38, APPROX), 'Rap Snare': ('c', 'RapSnareProperties', 173.8),
    'Hip-Hop Snare 2': ('c', 'HipHopSnare2Properties', 131.0), 'Jungle Snare 1': ('c', 'JungleSnare1Properties', 245.8),
    'Jungle Snare 2': ('c', 'JungleSnare2Properties', 220.2), 'Techno Snare 1': ('c', 'TechnoSnare1Properties', 119.9),
    'Brush Tap 1': ('k', 40, 38), 'Brush Tap 2': ('k', 40, 38), 'Brush Slap 1': ('k', 40, 39),
    'Brush Slap 2': ('k', 40, 39), 'Brush Slap 3': ('k', 40, 39), 'Brush Swirl 1': ('k', 40, 40),
    'Brush Swirl 2': ('k', 40, 40), 'Brush Long Swirl': ('k', 40, 40), 'Snare Roll': ('k', 0, 25),
    # kit and hand percussion on other keys
    'Hand Clap': ('k', 0, 39), 'Closed Hi-Hat': ('k', 0, 42), 'Pedal Hi-Hat': ('k', 0, 44),
    'Open Hi-Hat': ('k', 0, 46), 'Crash Cymbal 1': ('k', 0, 49), 'Concert Cymbal': ('k', 48, 59),
    'Tambourine': ('k', 0, 54), 'Castanets': ('k', 0, 85), 'Bell Tree': ('k', 0, 84),
    'Bar Chimes': ('k', 56, 62, APPROX), 'Cowbell': ('k', 0, 56), 'High Bongo': ('k', 0, 60),
    'Low Bongo': ('k', 0, 61), 'Mute High Conga': ('k', 0, 62), 'Open High Conga': ('k', 0, 63),
    'Mute Low Conga': ('k', 0, 64, APPROX), 'Open Low Conga': ('k', 0, 64), 'Conga Slap': ('k', 0, 62, APPROX),
    'Timbales High': ('k', 0, 65), 'Timbales Low': ('k', 0, 66), 'Timbales Paila': ('k', 0, 65, APPROX),
    'High Agogo': ('k', 0, 67), 'Low Agogo': ('k', 0, 68), 'Cabasa Up': ('k', 0, 69), 'Cabasa Down': ('k', 0, 69),
    'Caxixi': ('k', 0, 70, APPROX), 'High Whistle': ('k', 0, 71), 'Low Whistle': ('k', 0, 72),
    'Short Guiro': ('k', 0, 73), 'Long Guiro': ('k', 0, 74), 'Claves': ('k', 0, 75),
    'High Wood Block': ('k', 0, 76), 'Low Wood Block': ('k', 0, 77), 'Mute Cuica': ('k', 0, 78),
    'Open Cuica': ('k', 0, 79), 'Mute Triangle': ('k', 0, 80), 'Open Triangle': ('k', 0, 81),
    'Shaker': ('k', 0, 82), 'Mute Surdo': ('k', 0, 86), 'Open Surdo': ('k', 0, 87),
    '808 CHH': ('k', 25, 42), 'CR-78 CHH': ('k', 27, 42), 'CR-78 OHH': ('k', 27, 46),
    'Electric Low Tom2': ('k', 24, 41), 'Electric Low Tom1': ('k', 24, 43), 'Electric Mid Tom2': ('k', 24, 45),
    'Electric Mid Tom1': ('k', 24, 47), 'Electric High Tom2': ('k', 24, 48), 'Electric High Tom1': ('k', 24, 50),
    'Electric Mute Triangle': ('k', 0, 80, APPROX), 'Electric Open Triangle': ('k', 0, 81, APPROX),
    'Scratch Push2': ('k', 0, 29, APPROX), 'Scratch Pull2': ('k', 0, 30, APPROX),
    'Reverse Cymbal': ('k', 24, 52), 'Key Click': ('k', 56, 51),
    # the world's
    'Wadaiko': ('c', 'TaikoProperties', 65.9), 'Shime Taiko': ('c', 'TaikoProperties', 330.0, APPROX),
    'Atarigane': ('c', 'AtariganeProperties', 1318.5), 'Big Gong': ('k', 52, 74), 'Small Gong': ('k', 52, 75),
    'Thai Gong': ('k', 52, 73, APPROX), 'Rama Cymbal': ('c', 'CengCengProperties', 440.0),
    'Gamelan Gong': ('c', 'GamelanGongProperties', 65.4), 'Hyoushigi': ('k', 0, 75, APPROX),
    # backwards (blockrender._reverse_partial): the voice swelling to its hit
    'Reverse Kick 1': ('r', 0, 36), 'Reverse Concert Bass Drum': ('r', 48, 36),
    'Reverse Power Kick1': ('r', 16, 36), 'Reverse Electric Kick 1': ('r', 24, 36),
    'Reverse Snare 1': ('r', 0, 38), 'Reverse Snare 2': ('r', 0, 40), 'Reverse Standard 1 Snare 1': ('r', 0, 38),
    'Reverse Tight Snare': ('r', 0, 40), 'Reverse Dance Snare': ('r', 30, 38), 'Reverse 808 Snare': ('r', 25, 38),
    'Reverse Tom 1': ('r', 0, 48), 'Reverse Tom 2': ('r', 0, 45), 'Reverse Sticks': ('r', 0, 31),
    'Reverse Slap': ('r', 0, 28), 'Reverse Cymbal 1': ('r', 0, 49), 'Reverse Cymbal 2': ('r', 0, 57),
    'Reverse Open Hi-Hat': ('r', 0, 46), 'Reverse Ride Cymbal': ('r', 0, 51),
    'Reverse CR-78 Open Hi-Hat': ('r', 27, 46), 'Reverse Closed Hi-Hat': ('r', 0, 42),
    'Reverse Gong': ('r', 52, 74), 'Reverse Bell Tree': ('r', 0, 84), 'Reverse Guiro': ('r', 0, 74),
    'Reverse Gun Shot': ('r', 56, 72), 'Reverse Scratch': ('r', 56, 61), 'Reverse Laser Gun': ('r', 56, 74),
    'Reverse Hi Q': ('r', 0, 27),
    # Rhythm FX 2's: the drum machines' and the breaks' from their own sets
    # (the 707's crash is the 909's in our 707 set; Tambourine 2 Standard's)
    'Reverse TR-707 Kick 1': ('r', 29, 36), 'Reverse TR-909 Kick 1': ('r', 30, 36),
    'Reverse Hip-Hop Kick 1': ('r', 9, 36), 'Reverse Jungle Kick 2': ('r', 10, 35),
    'Reverse Techno Kick 2': ('r', 11, 35), 'Reverse TR-606 Snare 2': ('r', 28, 40),
    'Reverse CR-78 Snare 1': ('r', 27, 38), 'Reverse CR-78 Snare 2': ('r', 27, 40),
    'Reverse Jungle Snare 2': ('r', 10, 40), 'Reverse Techno Snare 2': ('r', 11, 40),
    'Reverse TR-707 Snare': ('r', 29, 38), 'Reverse TR-606 Snare 1': ('r', 28, 38),
    'Reverse TR-909 Snare 1': ('r', 30, 38), 'Reverse Hip-Hop Snare 2': ('r', 9, 40),
    'Reverse Jungle Snare 1': ('r', 10, 38), 'Reverse House Snare': ('r', 30, 38, APPROX),
    'Reverse TR-606 Closed Hi-Hat': ('r', 28, 42), 'Reverse TR-707 Closed Hi-Hat': ('r', 29, 42),
    'Reverse TR-808 Closed Hi-Hat': ('r', 25, 42), 'Reverse Jungle Hi-Hat': ('r', 10, 44),
    'Reverse Tambourine 2': ('r', 0, 54, APPROX), 'Reverse Shake Tambourine': ('r', 0, 54, APPROX),
    'Reverse TR-808 Open Hi-Hat': ('r', 25, 46), 'Reverse TR-707 Open Hi-Hat': ('r', 29, 46),
    'Reverse TR-606 Open Hi-Hat': ('r', 28, 46), 'Reverse TR-707 Crash Cymbal': ('r', 29, 49, APPROX),
    'Reverse Hu Yin Luo': None,
    # THE RHYTHM FX SETS' SYNTH HITS (tonelib.Rfx*: guesses from the names, on
    # the TR-808 engine) -- and Rhythm FX's Hoo, the Dance set's High Hoo
    'Techno Thip': ('c', 'RfxTechnoThipProperties', 1800.0),
    'Pop Drop': ('c', 'RfxPopDropProperties', 900.0),
    'Syn. Drops': ('c', 'RfxSynDropsProperties', 1500.0),
    'Pipe': ('c', 'RfxPipeProperties', 330.0),
    'Distortion Kick': ('c', 'RfxDistortionKickProperties', 49.8),
    'Sub Marine': ('c', 'RfxSubMarineProperties', 1200.0),
    'Noise Attack': ('c', 'RfxNoiseAttackProperties', 1000.0),
    'Bounce': ('c', 'RfxBounceProperties', 600.0),
    'Reverse Bounce': ('c', 'RfxBounceProperties', 600.0),
    'Distortion Knock': ('c', 'RfxDistortionKnockProperties', 2421.8),
    'Hoo': ('c', 'HooProperties', 1000.0),
    # ...AND THEIR SWEPT AND MOVING EFFECTS (tonelib.Rfx*, the weather and
    # laser machinery; the guitar's slide and the starship the SFX set's)
    'Swish': ('c', 'RfxSwishProperties', 261.63),
    'Velocity Noise FX': ('c', 'RfxVelocityNoiseProperties', 261.63),
    'Spark': ('c', 'RfxSparkProperties', 310.4),
    'Missile': ('c', 'RfxMissileProperties', 600.0),
    'Space Birds': ('c', 'RfxSpaceBirdsProperties', 2600.0),
    'Space Worms': ('c', 'RfxSpaceWormsProperties', 400.0),
    'Tape Stop 1': ('c', 'RfxTapeStopProperties', 30.0),
    'Tape Stop 2': ('c', 'RfxTapeStop2Properties', 30.0),
    'Emergency !': ('c', 'RfxSquareToneProperties', 960.0),
    'Calculating...': ('c', 'RfxMorseProperties', 700.0),
    'Saw LFO Saw': ('c', 'RfxSawSweepProperties', 220.0),
    'Guitar Slide': ('c', 'SfxFretSlideProperties', 261.63),
    # ...AND THEIR STRUCK AND PROCESSED OBJECTS (tonelib.Rfx*); Slappy a guess:
    # the SFX set's slap and its slapback echoes (STROKES)
    'Woody Slap': ('c', 'RfxWoodySlapProperties', 420.0),
    'Ice Block': ('c', 'RfxIceBlockProperties', 1800.0),
    'Metallic Percussion': ('c', 'RfxMetallicPercProperties', 700.0),
    'Modulated Bell': ('c', 'RfxModulatedBellProperties', 880.0),
    'Digital Tambourine': ('c', 'RfxDigitalTambourineProperties', 1000.0),
    'Alias': ('c', 'RfxAliasProperties', 300.0),
    'Stereo Noise Clap': ('c', 'RfxStereoClapProperties', 1000.0),
    # SLAPPY: a SNARE -- the SC-8850 files it last in its sets' bank of
    # snares (97-127, after House Snare 2 and Voice Tah), from the SC-88's
    # own sounds, two voices: a tight dance snare (the 909's) and a hand's
    # slap on it (LAYER) -- house's and new jack's "slappy" snare
    'Slappy': ('k', 30, 38),
    'Slappy (slap)': ('c', 'SfxSlapProperties', 335.0),
    # a monster flying past: the SFX set's growl, low (STROKES)
    'Flying Monster': ('c', 'SfxGrowlProperties', 1000.0),
    # Cymbal & Claps': a second take of a hat or a clap our voice each strike
    # varied; the old maps' takes our one voice; the 808's ride its cymbal
    'Reverse Closed Hi-Hat 1': ('r', 0, 42), 'Reverse Closed Hi-Hat 2': ('r', 0, 44, APPROX),
    'Closed Hi-Hat 2': ('n', 0, 42), 'Closed Hi-Hat 3': ('k', 0, 42, APPROX),
    'Closed Hi-Hat 4': ('k', 0, 42, APPROX), 'TR-808 Closed Hi-Hat': ('k', 25, 42),
    'Open Hi Hat': ('k', 0, 46), 'Open Hi-Hat 2': ('n', 0, 46), 'Open Hi-Hat 3': ('k', 0, 46, APPROX),
    'TR-707 Open Hi-Hat': ('k', 29, 46), 'TR-808 Open Hi-Hat': ('k', 25, 46),
    'Crash Cymbal 2': ('k', 0, 57), 'Crash Cymbal 3': ('k', 0, 57, APPROX),
    'Hard Crash Cymbal': ('k', 0, 49, APPROX),
    # a crash CHOKED -- the hand on the plate (its exclusive class is the
    # crash's): the crash, cut at GATE
    'Mute Crash Cymbal 1': ('c', 'CrashCymbal1Properties', 288.3),
    'Mute Crash Cymbal 2': ('c', 'CrashCymbal2Properties', 333.7),
    'Reverse Crash Cymbal 1': ('r', 0, 49), 'Reverse Crash Cymbal 2': ('r', 0, 57),
    'Reverse Crash Cymbal 3': ('r', 0, 57, APPROX), 'Reverse TR-909 Crash Cymbal': ('r', 30, 49),
    'Splash Cymbal': ('k', 0, 55), 'Ride Bell': ('k', 0, 53), 'Brush Ride Bell': ('k', 0, 53, APPROX),
    'Ride Cymbal 1': ('k', 0, 51), 'Ride Cymbal 2': ('k', 0, 59), 'Brush Ride Cymbal': ('k', 0, 51, APPROX),
    'TR-808 Ride Cymbal': ('k', 25, 49, APPROX), 'Chinese Cymbal': ('k', 0, 52),
    'Chinese Cymbal 2': ('k', 0, 52, APPROX),
    # HALF-OPEN: the open hat's plate rung shorter (RING, examples/halfhat_fit.py)
    'Half-Open Hi-Hat 1': ('c', 'OpenHiHatProperties', 248.4),
    'Half-Open Hi-Hat 2': ('c', 'OpenHiHatProperties', 248.4),
    'Brush Crash Cymbal': ('c', 'BrushCrashProperties', 288.3),
    # THE RIDE'S ZONES: inner the tip on the bow (our ride, Iowa's), edge the
    # shank on the edge (tonelib.RideEdgeProperties); low, mid and high three
    # rides a minor third apart (Roland's names only: the sizes a guess)
    'Ride Cymbal Low Inner': ('c', 'RideCymbalProperties', 124.0),
    'Ride Cymbal Mid Inner': ('c', 'RideCymbalProperties', 147.5),
    'Ride Cymbal High Inner': ('c', 'RideCymbalProperties', 175.4),
    'Ride Cymbal Low Edge': ('c', 'RideEdgeProperties', 124.0),
    'Ride Cymbal Mid Edge': ('c', 'RideEdgeProperties', 147.5),
    'Ride Cymbal High Edge': ('c', 'RideEdgeProperties', 175.4),
}
# A CLASS VOICE'S GESTURE, where it has one (percussion_map.KIT_STROKES, in
# each set it plays in): Roland's name -> {table: entry}.
# THE HOO, Reitanna's (Freesound 343968, CC0; examples/throat_fit.py hoo):
# ~480 Hz, level for 0.12 s, then falling an octave by 0.23 s; up within
# 20 ms, its loudest at the turn, gone with the fall; 2% jitter, a dB of
# shimmer (a shout, not a clean voice). The LOW HOO a bigger throat: a fifth
# down, its formants x0.85 (the pair a guess: Roland's names only)
_HOO_PITCH = ((0.0, -2.1), (0.01, 0.0), (0.1, 0.2), (0.12, -0.4), (0.15, -1.9), (0.17, -6.1),
              (0.19, -9.1), (0.21, -11.0), (0.23, -12.7))
_HOO_LEVEL = ((0.0, -12.0), (0.02, -2.0), (0.1, -1.0), (0.12, 0.0), (0.16, -4.0), (0.2, -8.0), (0.23, -20.0))
# THE BOUNCE: a ball settling -- each gap 0.75 of the last from 0.3 s, each
# bounce 2 dB under the one before; REVERSE BOUNCE the same mirrored in time
_BOUNCE = [(0.0, 0.0, 0.0)]
for _i in range(1, 10):
    _BOUNCE.append((_BOUNCE[-1][0] + 0.3 * 0.75 ** (_i - 1), -2.0 * _i, 0.0))
_BOUNCE = tuple((round(t, 4), d, st) for t, d, st in _BOUNCE)
_REV_BOUNCE = tuple(sorted((round(_BOUNCE[-1][0] - t, 4), d, st) for t, d, st in _BOUNCE))
# INTERNATIONAL MORSE CODE (ITU-R M.1677-1): its letters, figures and
# punctuation, in its order; a dash three dots, a dot between a character's
# elements, three between characters, seven between words; the speed in
# words a minute of "PARIS" (50 dots a word: 20 wpm a 60 ms dot)
MORSE_DOT_S = 0.06
MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.", "G": "--.", "H": "....",
    "I": "..", "J": ".---", "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---", "P": ".--.",
    "Q": "--.-", "R": ".-.", "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "1": ".----", "2": "..---", "3": "...--", "4": "....-", "5": ".....", "6": "-....", "7": "--...",
    "8": "---..", "9": "----.", "0": "-----",
    ".": ".-.-.-", ",": "--..--", ":": "---...", "?": "..--..", "'": ".----.", "-": "-....-",
    "/": "-..-.", "(": "-.--.", ")": "-.--.-", '"': ".-..-.", "=": "-...-", "+": ".-.-.",
    "x": "-..-", "@": ".--.-.",
}
MORSE_CHARS = tuple(MORSE)        # the keyboard's order: x is the multiplication sign


def morse_pattern(text, dot=MORSE_DOT_S):
    """A pattern's strokes (s, dB, semitones, length s) sending TEXT."""
    out, t = [], 0.0
    for w, word in enumerate(text.split()):
        if w:
            t += 7 * dot
        for c, ch in enumerate(word):
            if c:
                t += 3 * dot
            for e, sym in enumerate(MORSE[ch]):
                if e:
                    t += dot
                n = 1 if sym == "." else 3
                out.append((round(t, 4), 0.0, 0.0, round(n * dot, 4)))
                t += n * dot
    return tuple(out)


_morse = morse_pattern


STROKES = {
    'High Hoo': {"voiced": (((0.0, 0.0, 0.0),), 480.0, _HOO_PITCH, 0.23, 0.01, 0.0, 0.02, 1.0, None,
                            ((0.0, 1.0),), _HOO_LEVEL)},
    'Low Hoo': {"voiced": (((0.0, 0.0, 0.0),), 320.0, _HOO_PITCH, 0.23, 0.01, 0.0, 0.02, 1.0, None,
                           ((0.0, 0.85),), _HOO_LEVEL)},
    # THE SONAR PING and its RETURN: the echo off the target 0.7 s on, 14 dB
    # down, 10 cents low (moving away)
    'Sub Marine': {"pattern": ((0.0, 0.0, 0.0), (0.7, -14.0, -0.1))},
    # THE FLOCK: seven chirps at their own times and pitches over 0.8 s
    'Space Birds': {"pattern": ((0.0, 0.0, 0.0), (0.09, -4.0, 3.0), (0.21, -2.0, -2.0), (0.33, -6.0, 5.0),
                                (0.47, -3.0, 1.0), (0.6, -8.0, 7.0), (0.74, -5.0, -1.0))},
    # THE WRIGGLE: six blurps wiggling up and down, 90 ms apart
    'Space Worms': {"pattern": ((0.0, 0.0, 0.0), (0.09, -2.0, 3.0), (0.18, -1.0, -2.0), (0.27, -3.0, 4.0),
                                (0.36, -4.0, -1.0), (0.45, -6.0, 2.0))},
    # NEE-NAW: the two-tone a fourth apart, 0.35 s each, three times
    'Emergency !': {"pattern": tuple((0.35 * i, 0.0, 0.0 if i % 2 == 0 else -5.0) for i in range(6))},
    # CALCULATING: Morse, "CALC" at 20 words a minute on a 700 Hz sidetone
    # (Ben; percussion_map.morse_pattern -- the tone 125.10 the keyboard's)
    'Calculating...': {"pattern": _morse("CALC")},
    # THE LFO: the sweep eight times a second for a second
    'Saw LFO Saw': {"pattern": tuple((0.125 * i, 0.0, 0.0) for i in range(8))},
    # THE FLYING MONSTER: the growl (the SFX set's, KIT_STROKES[56] 86) low at
    # 85 Hz and long, passing -- swelling in and away, its jaw working twice a
    # second, its pitch falling 3 semitones as it goes by (Doppler)
    'Flying Monster': {"voiced": (((0.0, 0.0, 0.0),), 85.0, ((0.0, 1.0), (0.75, 0.0), (1.5, -2.0)),
                                  1.5, 0.03, 0.0, 0.045, 2.0, None,
                                  ((0.0, 0.8), (0.25, 1.1), (0.5, 0.8), (0.75, 1.1), (1.0, 0.8),
                                   (1.25, 1.05), (1.5, 0.7)),
                                  ((0.0, -24.0), (0.45, 0.0), (1.0, -2.0), (1.5, -26.0)))},
    'Bounce': {"pattern": _BOUNCE},
    'Reverse Bounce': {"pattern": _REV_BOUNCE},
}
STROKES['Hoo'] = STROKES['High Hoo']

# ...AND ITS LENGTH, a one-shot's (percussion_map.KIT_GATE): Small Club's the
# takes' main burst, ~2.5 s; a choked crash's the hand's, 0.15 s
GATE = {'Alias': 0.9, 'Swish': 0.35, 'Velocity Noise FX': 0.4, 'Missile': 1.0, 'Tape Stop 1': 1.0, 'Tape Stop 2': 0.6,
        'Guitar Slide': 0.3, 'Small Club 1': 2.5, 'Mute Crash Cymbal 1': 0.15, 'Mute Crash Cymbal 2': 0.15}

# ...AND ITS RING (percussion_map.KIT_RING, PERCUSSION_RING's sense): the
# half-open hats', fitted to DRSKit's semi-open hat against its open one
# (examples/halfhat_fit.py) -- 2 halfway (in log) to the open hat
RING = {'Half-Open Hi-Hat 1': 0.0721, 'Half-Open Hi-Hat 2': 0.1344}
# ...the ride's zones Standard's ride's (PERCUSSION_RING[51])
RING.update({'Ride Cymbal %s %s' % (h, z): 0.5 for h in ('Low', 'Mid', 'High') for z in ('Inner', 'Edge')})
# ...AND ITS LEVEL TRIM (percussion_map.KIT_LEVEL): the half-open hats the open
# hat's (PERCUSSION_LEVEL[46])
LEVEL = {'Half-Open Hi-Hat 1': 0.47, 'Half-Open Hi-Hat 2': 0.47}
# ...the crashes played by class (choked, brushed) Standard's crashes' ring and
# trim (PERCUSSION_RING/LEVEL 49, 57), the brushed one 9 dB under
RING.update({'Mute Crash Cymbal 1': 0.61, 'Mute Crash Cymbal 2': 1.69, 'Brush Crash Cymbal': 0.61})
# ...the SFX set's voices borrowed whole its trims (KIT_LEVEL[56] 47, 71)
LEVEL.update({'Guitar Slide': 59.315})
# ...and Standard's voices borrowed whole theirs (PERCUSSION_LEVEL 28, 54)
LEVEL.update({'Slappy (slap)': 0.0771, 'Digital Tambourine': 1.1874})

# A SOUND OF TWO VOICES (percussion_map._build_gs_sets): its second voice, on
# a key below the set's own, struck with it
LAYER = {'Slappy': ((16, 'Slappy (slap)'),)}
LEVEL.update({'Mute Crash Cymbal 1': 0.56, 'Mute Crash Cymbal 2': 0.56,
              'Brush Crash Cymbal': round(0.56 * 10 ** (-9 / 20.0), 4)})

# not built yet: Jingle Bell, Wadaiko Rim, Ohkawa, the Kotsuzumi,
# Ban Gu, Bend Gong, the udu, Bendir, Req, the tabla, the talking drums,
# Djembe, Conga Slide, Pandiero, Tamborim, High/Low Hoo, Reverse Bendir, and
# Rhythm FX's synth effects (Techno Thip ... Flying Monster)
