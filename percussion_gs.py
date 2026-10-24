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
SET_KIT = {('native', 2): 1, ('native', 3): 2, ('native', 10): 9, ('native', 12): 11, ('native', 50): 49, ('native', 51): 50, ('native', 58): 57,
           ('sc88', 27): 2 * 128 + 26}
SET_NAME = {1: "Standard 2", 2: "Standard 3", 9: "Hip-Hop", 11: "Techno", 49: "Ethnic", 50: "Kick & Snare", 57: "Rhythm FX", 2 * 128 + 26: "Dance"}
SET_ALONE = {49, 50, 57}

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
    'High Hoo': None, 'Low Hoo': None, 'Small Club 1': None,
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
    'Techno Kick 2': ('c', 'TechnoKick2Properties', 49.6), 'Jungle Kick 1': ('k', 0, 36, APPROX),
    'Jungle Kick 2': ('k', 0, 35, APPROX),
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
    'Hip-Hop Snare 2': ('c', 'HipHopSnare2Properties', 131.0), 'Jungle Snare 1': ('k', 0, 38, APPROX),
    'Jungle Snare 2': ('k', 0, 40, APPROX), 'Techno Snare 1': ('c', 'TechnoSnare1Properties', 119.9),
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
}
# not built yet: Finger Snap, Jingle Bell, Wadaiko Rim, Ohkawa, the Kotsuzumi,
# Ban Gu, Bend Gong, the udu, Bendir, Req, the tabla, the talking drums,
# Djembe, Conga Slide, Pandiero, Tamborim, High/Low Hoo, Reverse Bendir, and
# Rhythm FX's synth effects (Techno Thip ... Flying Monster)
