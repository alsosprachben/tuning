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
    ('native', 57): {  # SFX: EXTENDING the set built in percussion_map -- the SC-88 Pro's
        # additions below and above the SC-55's 39-84
        21: 'MC-500 Beep 1', 22: 'MC-500 Beep 2', 23: 'Guitar Slide', 24: 'Guitar Wah', 25: 'Guitar Slap',
        26: 'Chord Stroke Down', 27: 'Chord Stroke Up', 28: 'Biwa FX', 29: 'Phonograph Noise',
        30: 'Tape Rewind', 31: 'Scratch Push 2', 32: 'Scratch Pull 2', 33: 'Cutting Noise 2 Up',
        34: 'Cutting Noise 2 Down', 35: 'Distortion Guitar Cutting Noise Up',
        36: 'Distortion Guitar Cutting Noise Down', 37: 'Bass Slide', 38: 'Pick Scrape', 86: 'Bird 2', 88: 'Applause2',
        89: 'Telephone 1', 90: 'Telephone 2', 91: 'Small Club 1', 92: 'Small Club 2', 93: 'Applause Wave',
        94: 'Eruption', 95: 'Big Shot', 96: 'Percussion Bang'},
    ('native', 41): {  # BRUSH: EXTENDING the set built in percussion_map -- its brushed
        # toms and hats, the Jazz set's kicks, the ride's zones, the applause
        35: 'Jazz Kick 2', 36: 'Jazz Kick 1', 41: 'Brush Low Tom 2', 42: 'Brush Closed Hi-Hat',
        43: 'Brush Low Tom 1', 45: 'Brush Mid Tom 2', 46: 'Brush Open Hi-Hat', 47: 'Brush Mid Tom 1',
        48: 'Brush High Tom 2', 49: 'Brush Crash Cymbal', 50: 'Brush High Tom 1', 51: 'Ride Cymbal Inner',
        59: 'Ride Cymbal Edge', 88: 'Applause'},
    # THE MACHINE AND KIT SETS' KEYS FROM OTHER SETS (Roland's lists): each
    # EXTENDING the set built in percussion_map -- the CR-78's sounds on the
    # 606 and 808, the Kick 2s, the Hoos and Small Club, the ride's zones
    # (its hats the SC-88's "Hi-hat 3" -- the Room set's, Power being Standard's
    # in a big room, its toms already the Room toms)
    ('native', 17): {35: 'Power Kick 2', 40: 'Power Snare 2', 42: 'Closed Hi-hat3 C', 46: 'Open Hi-hat3'},
    # ROOM (its toms percussion_map's): its own kick and snare -- Standard's in
    # the live room (tonelib.MondoKickProperties, RoomSnareProperties)
    ('native', 9): {35: 'Room Kick 2', 36: 'Room Kick 1', 38: 'Room Snare 1', 40: 'Room Snare 2'},
    ('native', 25): {35: 'Electric Kick 2', 42: 'Closed Hi-Hat 2', 46: 'Open Hi-Hat 2', 88: 'Small Club 1'},
    ('native', 26): {35: 'TR-808 Kick 2', 40: 'TR-808 Snare 2', 51: 'TR-606 Ride Cymbal', 54: 'CR-78 Tambourine', 57: 'TR-909 Crash Cymbal', 60: 'CR-78 High Bongo', 61: 'CR-78 Low Bongo', 74: 'CR-78 Guiro', 78: 'High Hoo', 79: 'Low Hoo', 88: 'Small Club 1'},
    ('native', 28): {56: 'CR-78 Cowbell', 59: 'Ride Cymbal Edge', 78: 'High Hoo', 79: 'Low Hoo', 88: 'Small Club 1'},
    ('native', 29): {35: 'CR-78 Kick 2', 37: 'CR-78 Rim Shot', 54: 'CR-78 Tambourine', 56: 'CR-78 Cowbell', 59: 'Ride Cymbal Edge', 60: 'CR-78 High Bongo', 61: 'CR-78 Low Bongo', 70: 'CR-78 Maracas', 74: 'CR-78 Guiro', 75: 'CR-78 Claves', 78: 'High Hoo', 79: 'Low Hoo', 80: 'CR-78 Metalic Beat 1', 81: 'CR-78 Metalic Beat 2', 88: 'Small Club 1'},
    ('native', 30): {59: 'Ride Cymbal Edge', 78: 'High Hoo', 79: 'Low Hoo', 88: 'Small Club 1'},
    ('native', 31): {59: 'Ride Cymbal Edge', 74: 'CR-78 Guiro', 78: 'High Hoo', 79: 'Low Hoo'},
    ('native', 33): {39: 'Hand Clap2', 42: 'Closed Hi-Hat 2', 46: 'Open Hi-Hat 2', 51: 'Ride Cymbal Inner', 59: 'Ride Cymbal Edge', 88: 'Applause'},
    ('native', 53): {  # ASIA: EXTENDING the set Tokei plays (its gongs and crash,
        # percussion_map.KITS[52]); its Chinese opera gongs, the kakegoe -- first,
        # as other sets play its keys backwards
        25: 'Gamelan Gong 1', 26: 'Gamelan Gong 2', 27: 'Gamelan Gong 3', 28: 'Gamelan Gong 4', 29: 'Gamelan Gong 5', 30: 'Gamelan Gong 6', 31: 'Gamelan Gong 7', 32: 'Gamelan Gong 8', 33: 'Gamelan Gong 9', 34: 'Gamelan Gong 10',
        35: 'Gender 1', 36: 'Gender 2', 37: 'Gender 3', 38: 'Gender 4', 39: 'Gender 5', 40: 'Bonang 1', 41: 'Bonang 2', 42: 'Bonang 3', 43: 'Bonang 4', 44: 'Bonang 5',
        45: 'Rama Cymbal Low', 46: 'Rama Cymbal High', 47: 'Sagat Open', 48: 'Sagat Closed',
        50: 'Wadaiko', 51: 'Wadaiko Rim', 52: 'Small Taiko', 53: 'Shimedaiko', 54: 'Atarigane',
        55: 'Hyoushigi', 56: 'Ohkawa', 57: 'High Kotsuzumi', 58: 'Low Kotsuzumi',
        59: 'Yyoo Dude', 60: 'Buk', 61: 'Buk Rim', 62: 'Gengari p', 63: 'Gengari Mute Low', 64: 'Gengari f',
        65: 'Gengari Mute High', 66: 'Gengari Samll', 67: 'Jang-Gu Che', 68: 'Jang-Gu Kun', 69: 'Jang-Gu Rim',
        70: 'Jing p', 71: 'Jing f', 72: 'Jing Mute', 80: 'Shou Luo', 81: 'Bend Gong', 82: 'Hu Yin Luo Low', 83: 'Hu Yin Luo Mid',
        84: 'Hu Yin Luo Mid 2', 85: 'Hu Yin Luo High', 86: 'Hu Yin Luo High 2', 87: 'Nao Bo',
        88: 'Xiao Bo', 77: 'Ban Gu', 76: 'Pai Ban', 78: 'Tang Gu', 79: 'Tang Gu Mute',
    },
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
SET_KIT = {('native', 9): 8, ('native', 2): 1, ('native', 3): 2, ('native', 27): 26, ('native', 10): 9, ('native', 11): 10, ('native', 12): 11, ('native', 50): 49, ('native', 51): 50, ('native', 58): 57, ('native', 59): 58, ('native', 54): 53, ('native', 53): 52, ('native', 57): 56, ('native', 41): 40, ('native', 17): 16, ('native', 25): 24, ('native', 26): 25, ('native', 28): 27, ('native', 29): 28, ('native', 30): 29, ('native', 31): 30, ('native', 33): 32,
           ('sc88', 27): 2 * 128 + 26}
SET_NAME = {1: "Standard 2", 2: "Standard 3", 9: "Hip-Hop", 10: "Jungle", 11: "Techno", 49: "Ethnic", 50: "Kick & Snare", 57: "Rhythm FX", 58: "Rhythm FX 2", 53: "Cymbal & Claps", 52: "Asia", 56: "SFX", 26: "Dance", 2 * 128 + 26: "Dance"}
SET_ALONE = {49, 50, 52, 53, 57, 58}
# ...and the sets that EXTEND a kit built elsewhere rather than replace it
SET_EXTEND = {8, 40, 52, 56, 16, 24, 25, 27, 28, 29, 30, 32}

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
    # the Room set's own: Standard's in the live room (tonelib.RoomClosedHatProperties ...)
    'Room Closed Hi-Hat': ('c', 'RoomClosedHatProperties', 248.4), 'Room Closed Hi-Hat 3': ('c', 'RoomClosedHatProperties', 248.4),
    'Room Open Hi-Hat': ('c', 'RoomOpenHatProperties', 248.4), 'Room Open Hi-Hat 3': ('c', 'RoomOpenHatProperties', 248.4),
    'Room Crash Cymbal': ('c', 'RoomCrashProperties', 288.3), 'Room Ride Cymbal': ('c', 'RoomRideProperties', 147.5),
    'Room Ride Bell': ('c', 'RoomRideBellProperties', 147.5),
    # the Jazz set's own: soneproject's jazz-bar kit (tonelib.JazzTomLowProperties ...)
    'Jazz Low Tom 2': ('c', 'JazzTomLowProperties', 90.0), 'Jazz Low Tom 1': ('c', 'JazzTomLowProperties', 101.0),
    'Jazz Mid Tom 2': ('c', 'JazzTomHighProperties', 144.0), 'Jazz Mid Tom 1': ('c', 'JazzTomHighProperties', 162.0),
    'Jazz High Tom 2': ('c', 'JazzTomHighProperties', 182.0), 'Jazz High Tom 1': ('c', 'JazzTomHighProperties', 204.0),
    'Jazz Crash Cymbal': ('c', 'JazzCrashProperties', 288.3), 'Jazz Ride Cymbal': ('c', 'JazzRideProperties', 147.5),
    'JAZZ Ride Cymbal': ('c', 'JazzRideProperties', 147.5), 'Jazz Ride Bell': ('c', 'JazzRideBellProperties', 147.5),
    # Standard L/R's names for Standard's (each strike varied there: [RND])
    'Standard Kick 1': ('k', 0, 36), 'Standard Kick 2': ('k', 0, 35), 'Standard Snare 1': ('k', 0, 38),
    'Standard Snare 2': ('k', 0, 40), 'Low Tom 2': ('k', 0, 41), 'Low Tom 1': ('k', 0, 43), 'Mid Tom 2': ('k', 0, 45),
    'Mid Tom 1': ('k', 0, 47), 'High Tom 2': ('k', 0, 48), 'High Tom 1': ('k', 0, 50),
    # the L/R sets' left foot (a double pedal's second beater: tonelib.LeftKickProperties ...)
    '[L] Standard Kick 1': ('c', 'LeftKickProperties', 44.4), '[L] Standard Kick 2': ('c', 'LeftKickProperties', 39.4),
    '[L] Room Kick 1': ('c', 'LeftRoomKickProperties', 44.4), '[L] Room Kick 2': ('c', 'LeftRoomKickProperties', 39.4),
    '[L] Jazz Kick 1': ('c', 'LeftJazzKickProperties', 70.0), '[L] Jazz Kick 2': ('c', 'LeftJazzKick2Properties', 46.0),
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
    # the SC-88 map's own names (its Power, Jazz and SFX sets)
    'Closed Hi-hat3 C': ('c', 'RoomClosedHatProperties', 248.4), 'Open Hi-hat3': ('c', 'RoomOpenHatProperties', 248.4),
    'Hand Clap2': ('k', 0, 39, APPROX), 'Applause2': ('k', 0, 88),
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
    'Room Kick 1': ('c', 'MondoKickProperties', 44.4), 'Room Kick 2': ('c', 'MondoKickProperties', 39.4),
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
    'Room Snare 1': ('c', 'RoomSnareProperties', 195.1), 'Room Snare 2': ('c', 'RoomSnare2Properties', 192.5),
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
    'Dholak 1': ('c', 'DholakBassProperties', 107.0), 'Dholak 2': ('c', 'DholakTrebleProperties', 790.0),
    # THE BRUSH KIT'S KICK (Brush 2, Brush 2 L/R, Kick & Snare 2): the jazz
    # kit's bass drum, which a brush player plays -- its own feathered stroke
    # unrecorded; its left foot the jazz kick's second beater
    'Brush Kick 1': ('k', 32, 36, APPROX), 'Brush Kick 2': ('k', 32, 35, APPROX),
    '[L] Brush Kick 1': ('c', 'LeftJazzKickProperties', 70.0, APPROX),
    '[L] Brush Kick 2': ('c', 'LeftJazzKick2Properties', 46.0, APPROX),
    # the concert bass drum, the hand on its head (its exclusive class is the
    # open drum's): cut at GATE
    'Concert BD 1 Mute': ('c', 'ConcertBassDrumProperties', 37.7),
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
    'Reverse Hi Q': ('r', 0, 27), 'Reverse Bendir': ('r', 49, 54),
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
    # Rhythm FX 3's (SC-8850): each kit's own kick, snare, rim, tom, hat and clap
    # backwards, from where it is built (Brush's snares and toms by what Brush
    # has: its tap and swirl, its high, mid and low tom)
    'Reverse Standard Kick 2': ('r', 0, 35), 'Reverse Standard Kick 1': ('r', 0, 36),
    'Reverse Room Kick 2': ('r', 8, 35), 'Reverse Room Kick 1': ('r', 8, 36),
    'Reverse Jazz Kick 2': ('r', 32, 35), 'Reverse Jazz Kick 1': ('r', 32, 36),
    'Reverse Brush Kick 2': ('r', 41, 35), 'Reverse Brush Kick 1': ('r', 41, 36),
    'Reverse HipHop Kick 2': ('r', 9, 35), 'Reverse HipHop Kick 1': ('r', 9, 36),
    'Reverse Jungle Kick 1': ('r', 10, 36), 'Reverse TR-808 Kick': ('r', 25, 36),
    'Reverse TR-909 Kick 2': ('r', 30, 35), 'Reverse Fat Kick': ('r', 26, 35),
    'Reverse Dance Kick': ('r', 26, 36),
    'Reverse Standard Snare 1': ('r', 0, 38), 'Reverse Standard Snare 2': ('r', 0, 40),
    'Reverse Room Snare 1': ('r', 8, 38), 'Reverse Room Snare 2': ('r', 8, 40),
    'Reverse Jazz Snare 1': ('r', 32, 38), 'Reverse Jazz Snare 2': ('r', 32, 40),
    'Reverse Brush Snare 1': ('r', 40, 38, APPROX), 'Reverse Brush Snare 2': ('r', 40, 40, APPROX),
    'Reverse Lo-Fi Snare 1': ('r', 9, 38), 'Reverse Lo-Fi Snare 2': ('r', 9, 40),
    'Reverse HipHop Snare 1': ('r', 10, 38), 'Reverse HipHop Snare 2': ('r', 9, 40),
    'Reverse House Snare 1': ('r', 30, 38, APPROX), 'Reverse Jungle Snare': ('r', 10, 40),
    'Reverse 606 Snare 2': ('r', 28, 40), 'Reverse Techno Snare': ('r', 10, 93),
    'Reverse Dance Snare': ('r', 26, 38), 'Reverse Rock Snare Dry': ('r', 10, 95),
    'Reverse Lo-Fi Snare Rim': ('r', 9, 90), 'Reverse 909 Snare Rim': ('r', 30, 37),
    'Reverse Jungle Snare Rim': ('r', 10, 37), 'Reverse Dance Snare Rim': ('r', 26, 37),
    'Reverse House Snare Rim': ('r', 30, 37, APPROX),
    'Reverse Brush Tom 1': ('r', 40, 50, APPROX), 'Reverse Brush Tom 2': ('r', 40, 47, APPROX),
    'Reverse Brush Tom 3': ('r', 40, 43, APPROX), 'Reverse 606 Tom': ('r', 28, 47, APPROX),
    'Reverse Jungle Crash Cymbal': ('r', 10, 49),
    'Reverse Standard Closed Hi-Hat': ('r', 0, 42), 'Reverse Room Closed Hi-Hat': ('r', 9, 42),
    'Reverse Jazz Closed Hi-Hat': ('r', 32, 42), 'Reverse Brush Closed Hi-Hat': ('r', 40, 42),
    'Reverse 707 Claps': ('r', 29, 39), 'Reverse 909 Claps': ('r', 11, 39),
    'Reverse R&B Claps 1': ('r', 10, 39), 'Reverse HipHop Claps': ('r', 9, 91),
    'Reverse Comp Claps 2': ('r', 26, 39), 'Reverse Shaker 2': ('r', 9, 82),
    'Reverse Jungle Shaker': ('r', 10, 82),
    # THE CHINESE OPERA GONGS (tonelib.RfxDaluo, RfxHuYinLuo, RfxXiaoluo):
    # the tiger gongs in three sizes (a "2" a second gong a little higher), the
    # reverse the middle one's
    'Shou Luo': ('c', 'RfxXiaoluoProperties', 660.6),
    'Bend Gong': ('c', 'RfxDaluoProperties', 179.3),
    'Hu Yin Luo Low': ('c', 'RfxHuYinLuoProperties', 250.0),
    'Hu Yin Luo Mid': ('c', 'RfxHuYinLuoProperties', 340.0),
    'Hu Yin Luo Mid 2': ('c', 'RfxHuYinLuoProperties', 360.0),
    'Hu Yin Luo High': ('c', 'RfxHuYinLuoProperties', 470.0),
    'Hu Yin Luo High 2': ('c', 'RfxHuYinLuoProperties', 500.0),
    'Reverse Hu Yin Luo': ('r', 52, 83),
    # ...the machine sets' borrowed keys: our CR-78's (its cowbell the 808's,
    # ours having none), the 808's kick 2 its kick, the ride's zones
    # Cymbal & Claps' mid ride, Jazz's applause the Orchestra set's
    'TR-808 Kick 2': ('k', 25, 36, APPROX), 'Power Kick 2': ('k', 16, 36, APPROX),
    'CR-78 Tambourine': ('k', 27, 54), 'CR-78 Rim Shot': ('k', 27, 37), 'CR-78 Maracas': ('k', 27, 70),
    'CR-78 Claves': ('k', 27, 75), 'CR-78 Metalic Beat 1': ('k', 27, 80), 'CR-78 Metalic Beat 2': ('k', 27, 81),
    'CR-78 Cowbell': ('k', 25, 56, APPROX), 'Tambourine 2': ('k', 0, 54, APPROX),
    'Ride Cymbal Edge': ('c', 'RideEdgeProperties', 147.5), 'Ride Cymbal Inner': ('c', 'RideCymbalProperties', 147.5),
    'Applause': ('k', 48, 88),
    # THE SC-8850's DANCE-ERA DRUMS (tonelib: ours through the sampler each name
    # implies, driven, or cut; the machines' from their own sets)
    'LoFi Snare 1': ('c', 'LoFiSnare1Properties', 195.1), 'LoFi Snare 2': ('c', 'LoFiSnare2Properties', 165.0),
    'LoFi Snare Rim': ('c', 'LoFiRimProperties', 195.1), 'TR-707 Claps': ('k', 29, 39),
    'Hip-Hop Claps': ('c', 'HipHopClapsProperties', 310.4), 'Shaker 2': ('n', 0, 82),
    'HipHop Snare 1': ('c', 'RapSnareProperties', 173.8, APPROX),
    'Hip-Hop Snare 1': ('c', 'RapSnareProperties', 173.8, APPROX),
    'HipHop Snare 2': ('c', 'HipHopSnare2Properties', 131.0), 'R&B Claps': ('c', 'RnBClapsProperties', 310.4),
    'Jungle Snare': ('c', 'JungleSnare1Properties', 245.8, APPROX),
    'Jungle Snare Rim': ('c', 'JungleRimProperties', 195.1), 'Jungle Crash': ('c', 'JungleCrashProperties', 288.3),
    'Jungle Crash Cymbal': ('c', 'JungleCrashProperties', 288.3),
    'Jungle Shaker': ('c', 'JungleShakerProperties', 386.0),
    'Jungle Kick Roll': ('c', 'JungleKick1Properties', 52.8), 'Jungle Snare Roll': ('c', 'JungleSnare1Properties', 245.8),
    'TR-606 Snare 2': ('k', 28, 40), 'TR-606 Low Tom 2': ('k', 28, 41), 'TR-606 Low Tom 1': ('k', 28, 43),
    'TR-606 Mid Tom 2': ('k', 28, 45), 'TR-606 Mid Tom 1': ('k', 28, 47), 'TR-606 High Tom 2': ('k', 28, 48),
    'TR-606 High Tom 1': ('k', 28, 50), 'Techno Snare': ('c', 'TechnoSnare1Properties', 119.9, APPROX),
    # the SC-8850's Techno set's machine drums, driven (its name says distorted)
    'Techno TR-808 Kick': ('c', 'TechnoTR808KickProperties', 49.6),
    'Techno TR-606 Snare 2': ('c', 'TechnoTR606SnareProperties', 203.9),
    'Rock Snare Dry': ('c', 'AcousticSnareProperties', 195.1, APPROX),
    'Rock SD Dry': ('c', 'AcousticSnareProperties', 195.1, APPROX),
    'TR-909 Snare Rim': ('k', 30, 37), 'Dance Rim Shot': ('k', 30, 37), 'TR-909 Ride Cymbal': ('k', 30, 51),
    'TR-909 Claps': ('c', 'TR909ClapProperties', 1000.0), 'House Snare 1': ('k', 30, 38),
    'House Snare 2': ('k', 30, 40), 'House Snare Rim': ('k', 30, 37), 'Fat Kick': ('c', 'FatKickProperties', 42.0),
    'Comp Claps 2': ('c', 'CompClaps2Properties', 310.4),
    # THE SC-88 PRO SFX SET'S ADDITIONS (tonelib.Rfx*: ours where we have the
    # sound -- the fret slide, the cutting noises (their second takes and the
    # distorted ones ours: the guitar's amp is a channel's), the record, the
    # telephone, the crowd, the explosion and the gunshot lower, the orchestra
    # hit -- the rest guesses from the names)
    'MC-500 Beep 1': ('c', 'RfxMC500BeepProperties', 2093.0),
    'MC-500 Beep 2': ('c', 'RfxMC500BeepProperties', 1046.5),
    'Guitar Wah': ('c', 'RfxGuitarWahProperties', 261.63),
    'Guitar Slap': ('c', 'SfxBassSlapProperties', 523.25, APPROX),
    'Chord Stroke Down': ('c', 'RfxStrumProperties', 82.41),
    'Chord Stroke Up': ('c', 'RfxStrumProperties', 82.41),
    'Biwa FX': ('c', 'RfxBiwaFxProperties', 196.0, APPROX),
    'Phonograph Noise': ('c', 'PhonoNoiseProperties', 261.63),
    'Tape Rewind': ('c', 'RfxTapeRewindProperties', 2500.0),
    'Cutting Noise 2 Up': ('k', 56, 49, APPROX), 'Cutting Noise 2 Down': ('k', 56, 48, APPROX),
    'Distortion Guitar Cutting Noise Up': ('k', 56, 49, APPROX),
    'Distortion Guitar Cutting Noise Down': ('k', 56, 48, APPROX),
    'Bass Slide': ('c', 'SfxFretSlideProperties', 130.81, APPROX),
    'Pick Scrape': ('c', 'RfxPickScrapeProperties', 261.63),
    'Bird 2': ('c', 'SfxBirdsProperties', 3322.4, APPROX),
    'Telephone 1': ('c', 'TelephoneRingProperties', 523.25),
    'Telephone 2': ('c', 'RfxSquareToneProperties', 1000.0),
    'Small Club 2': ('c', 'SmallClubProperties', 440.0),
    'Applause Wave': ('c', 'RfxApplauseWaveProperties', 440.0),
    'Eruption': ('c', 'SfxExplosionProperties', 130.81),
    'Big Shot': ('c', 'GunshotProperties', 98.0),
    'Percussion Bang': ('c', 'OrchestraHitProperties', 261.63, APPROX),
    # THE BRUSH SET'S BRUSHED STROKES (tonelib.Brush*: DRSKit's whiskers against
    # its sticks, applied to Standard's), at Standard's pitches
    'Brush High Tom 1': ('c', 'BrushTomHighProperties', 175.0),
    'Brush High Tom 2': ('c', 'BrushTomHighProperties', 150.0),
    'Brush Mid Tom 1': ('c', 'BrushTomMidProperties', 130.0),
    'Brush Mid Tom 2': ('c', 'BrushTomMidProperties', 110.0),
    'Brush Low Tom 1': ('c', 'BrushTomLowProperties', 98.0),
    'Brush Low Tom 2': ('c', 'BrushTomLowProperties', 87.0),
    'Brush swish high': ('c', 'BrushSwishProperties', 1000.0),
    'Brush swish mid': ('c', 'BrushSwishMidProperties', 1000.0),
    'Brush swish low': ('c', 'BrushSwishProperties', 1000.0),
    'Brush Closed Hi-Hat': ('c', 'BrushClosedHatProperties', 248.4),
    'Brush Open Hi-Hat': ('c', 'BrushOpenHatProperties', 248.4),
    # ...and the opera's cymbals and its small drum (the dataset's naobo and
    # bangu; the small cymbals the pair a fifth up)
    'Nao Bo': ('c', 'RfxNaoboProperties', 181.9),
    'Xiao Bo': ('c', 'RfxNaoboProperties', 272.5),
    'Ban Gu': ('c', 'RfxBanguProperties', 1926.0),
    # the clapper and the hall drum: no recordings -- a hardwood clack, and
    # our taiko a mid-sized barrel drum (110 Hz), its mute hand-damped (GATE)
    'Pai Ban': ('c', 'RfxPaiBanProperties', 1100.0),
    # THE JAPANESE DRUMS (tonelib.RfxOhkawa, RfxKotsuzumi*, RfxTaikoRim: how
    # they are made and played); the small taiko ours higher
    'Ohkawa': ('c', 'RfxOhkawaProperties', 1600.0),
    'High Kotsuzumi': ('c', 'RfxKotsuzumiHighProperties', 600.0),
    'Low Kotsuzumi': ('c', 'RfxKotsuzumiLowProperties', 260.0),
    'Wadaiko Rim': ('c', 'RfxTaikoRimProperties', 1200.0),
    # THE KOREAN (tonelib.RfxBuk, RfxGengari, RfxJanggu*, RfxJing: guesses from
    # how they are made and played; "Samll" as Roland prints it). A rim the
    # taiko rim's click; the gengari's mutes choked (GATE), a semitone either
    # way, its small one a fourth up; the jing's mute hand-damped
    # THE JAVANESE AND THE THAI: the gamelan's fitted voices (GS 112.8-10) at
    # SLENDRO's pitches -- five near-equal steps an octave (240 cents): the ten
    # gongs from the Ethnic set's 65.4 Hz up two octaves, the gender from
    # middle C, the bonang's kettles an octave over it; the ceng-ceng a fourth
    # apart; the sagat open, and closed (GATE)
    # THE ETHNIC SET'S REST (tonelib.Rfx*: VCSL's takes where it has them, the
    # rest how they are played); a jingle our tambourine (LAYER)
    'Jingle Bell': ('c', 'RfxJingleBellProperties', 2540.0),
    'Req Dum': ('c', 'RfxReqDumProperties', 144.0),
    'Req Tik': ('c', 'RfxReqTikProperties', 728.0),
    'Bendir': ('c', 'RfxBendirProperties', 90.0),
    'Udo Short': ('c', 'RfxUduShortProperties', 180.0),
    'Udo Long': ('c', 'RfxUduLongProperties', 120.0),
    'Udo Slap': ('c', 'RfxUduSlapProperties', 600.0),
    'Talking Drum': ('c', 'RfxTalkingDrumProperties', 220.0),
    'Bend Talking Drum': ('c', 'RfxBendTalkingDrumProperties', 220.0),
    'Djembe': ('c', 'RfxDjembeProperties', 330.0),
    'Djembe Rim': ('c', 'RfxDjembeRimProperties', 700.0),
    'Conga Slide': ('c', 'RfxCongaSlideProperties', 330.0),
    'Open Pandiero': ('c', 'RfxPandieroOpenProperties', 150.0),
    'Mute Pandiero': ('c', 'RfxPandieroMuteProperties', 180.0),
    'Tamborim': ('c', 'RfxTamborimProperties', 620.0),
    # THE TABLA (tonelib.RfxTabla*, from mmiron's CC0 bols)
    'Tabla Te': ('c', 'RfxTablaTeProperties', 125.0),
    'Tabla Na': ('c', 'RfxTablaNaProperties', 837.0),
    'Tabla Tun': ('c', 'RfxTablaTunProperties', 314.0),
    'Tabla Ge': ('c', 'RfxTablaGeProperties', 97.0),
    'Tabla Ge Hi': ('c', 'RfxTablaGeHiProperties', 174.0),
    'Buk': ('c', 'RfxBukProperties', 100.0),
    'Buk Rim': ('c', 'RfxTaikoRimProperties', 1300.0),
    'Gengari p': ('c', 'RfxGengariProperties', 1100.0),
    'Gengari f': ('c', 'RfxGengariProperties', 1100.0),
    'Gengari Mute Low': ('c', 'RfxGengariProperties', 1038.0),
    'Gengari Mute High': ('c', 'RfxGengariProperties', 1165.0),
    'Gengari Samll': ('c', 'RfxGengariProperties', 1468.0),
    'Jang-Gu Che': ('c', 'RfxJangguCheProperties', 480.0),
    'Jang-Gu Kun': ('c', 'RfxJangguKunProperties', 130.0),
    'Jang-Gu Rim': ('c', 'RfxTaikoRimProperties', 1500.0),
    'Jing p': ('c', 'RfxJingProperties', 110.0),
    'Jing f': ('c', 'RfxJingProperties', 110.0),
    'Jing Mute': ('c', 'RfxJingProperties', 110.0),
    'Rama Cymbal Low': ('c', 'CengCengProperties', 440.0),
    'Rama Cymbal High': ('c', 'CengCengProperties', 587.3),
    'Sagat Open': ('c', 'RfxSagatProperties', 2400.0),
    'Sagat Closed': ('c', 'RfxSagatProperties', 2400.0),
    'Small Taiko': ('c', 'TaikoProperties', 120.0, APPROX),
    'Shimedaiko': ('c', 'TaikoProperties', 330.0, APPROX),
    'Tang Gu': ('c', 'TaikoProperties', 110.0, APPROX),
    'Tang Gu Mute': ('c', 'TaikoProperties', 110.0, APPROX),
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
    # THEIR VOICES (tonelib.RfxVoice* and friends: throats, their gestures and
    # consonants STROKES and LAYER); reversed, the gesture mirrored
    'Voice One': ('c', 'RfxVoiceOneProperties', 1000.0),
    'Reverse Voice One': ('c', 'RfxVoiceOneRevProperties', 1000.0),
    'Voice Two': ('c', 'RfxVoiceTwoProperties', 1000.0),
    'Reverse Voice Two': ('c', 'RfxVoiceTwoRevProperties', 1000.0),
    'Voice Three': ('c', 'RfxVoiceThreeProperties', 1000.0),
    'Reverse Voice Three': ('c', 'RfxVoiceThreeRevProperties', 1000.0),
    'Voice Tah': ('c', 'RfxVoiceTahProperties', 1000.0),
    'Reverse Voice Tah': ('c', 'RfxVoiceTahRevProperties', 1000.0),
    'Voice Ou': ('c', 'RfxVoiceOuProperties', 1000.0),
    'Voice Au': ('c', 'RfxVoiceAuProperties', 1000.0),
    'Voice Whey': ('c', 'RfxVoiceWheyProperties', 1000.0),
    'Frog Voice': ('c', 'RfxFrogProperties', 1000.0),
    'Douby': ('c', 'RfxDoubyProperties', 1000.0),
    'Reverse Douby': ('c', 'RfxDoubyRevProperties', 1000.0),
    'Baert High': ('c', 'RfxBaertProperties', 1000.0),
    'Baert Low': ('c', 'RfxBaertProperties', 1000.0),
    # THE KAKEGOE backwards: "Yyoo" is the call (the SC-8850's "Reverse
    # Yyooh"; "Dude" who calls -- Ben), and its forward on the Asia set, beside
    # the kotsuzumi, makes it a noh drummer's long "yo-o"
    'Reverse Yyoo Dude': ('c', 'RfxKakegoeRevProperties', 1000.0),
    'Yyoo Dude': ('c', 'RfxKakegoeProperties', 1000.0),
    **{'Gamelan Gong %d' % (_i + 1): ('c', 'GamelanGongProperties', round(65.4 * 2 ** (_i / 5.0), 2))
   for _i in range(10)},
    **{'Gender %d' % (_i + 1): ('c', 'RfxGenderKeyProperties', round(261.63 * 2 ** (_i / 5.0), 2)) for _i in range(5)},
    **{'Bonang %d' % (_i + 1): ('c', 'BonangProperties', round(523.25 * 2 ** (_i / 5.0), 2)) for _i in range(5)},
    # ...and the keys below the set that carry their consonants and Yo Dude's
    # second word
    'consonant t': ('c', 'RfxBurstTProperties', 1000.0),
    'consonant d': ('c', 'RfxBurstDProperties', 1000.0),
    'consonant th': ('c', 'RfxHissThProperties', 1000.0),

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
    # ...and each kit's own (Cym&Claps 2, SC-8850): Standard 1's, Room's,
    # Jazz's, Brush's crash, choked
    'Standard 1 Mute Crash Cymbal': ('c', 'CrashCymbal1Properties', 288.3),
    'Room Mute Crash Cymbal': ('c', 'RoomCrashProperties', 288.3),
    'Jazz Mute Crash Cymbal': ('c', 'JazzCrashProperties', 288.3),
    'Brush Mute Crash Cymbal': ('c', 'BrushCrashProperties', 288.3),
    'Reverse Crash Cymbal 1': ('r', 0, 49), 'Reverse Crash Cymbal 2': ('r', 0, 57),
    # Cym&Claps 2's: the kits' own cymbals and hats, by kit, forward and back
    'Standard 1 Crash Cymbal': ('k', 0, 49), 'Reverse Standard 1 Crash Cymbal': ('r', 0, 49),
    'Reverse Room Crash Cymbal': ('r', 8, 49), 'Reverse Jazz Crash Cymbal': ('r', 32, 49),
    'Reverse Brush Crash Cymbal': ('r', 40, 49),
    'Standard 1 Closed Hi-Hat': ('k', 0, 42), 'Jazz Closed Hi-Hat': ('k', 32, 42),
    'Standard 1 Open Hi-Hat': ('k', 0, 46), 'Jazz Open Hi-Hat': ('k', 32, 46),
    'Standard Ride Bell': ('k', 0, 53), 'Standard Ride Cymbal': ('k', 0, 51),
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
    # THE STRUM: an open E's six strings 12 ms apart, down low to high, up the
    # reverse, each a little softer
    'Chord Stroke Down': {"pattern": tuple((0.012 * i, -0.6 * i, st, 1.5) for i, st in enumerate((0, 7, 12, 16, 19, 24)))},
    'Chord Stroke Up': {"pattern": tuple((0.012 * i, -0.6 * i, st, 1.5) for i, st in enumerate((24, 19, 16, 12, 7, 0)))},
    # TAPE REWIND: twenty chirps in 1.2 s, closing up and rising an octave
    'Tape Rewind': {"pattern": tuple((round(1.2 * (i / 20.0) ** 0.8, 3), -4.0 * (i % 2), round(12.0 * i / 19, 2))
                                     for i in range(20))},
    # TELEPHONE 2: an electronic trill, two tones a minor third apart at 20 a
    # second, for 0.8 s
    'Telephone 2': {"pattern": tuple((0.025 * i, 0.0, 3.0 * (i % 2), 0.025) for i in range(32))},
    # THE JUNGLE ROLLS: the kick and the snare rolled as Standard's snare roll
    # (percussion_map.PERCUSSION_ROLL[25]) is, while the key is held
    'Jungle Kick Roll': {"roll": (13.5, 6, 0.009, 3.0, 1.5, 0.08, 2.0, 0.3, -14.0, -4.0, 0.0)},
    'Jungle Snare Roll': {"roll": (13.5, 6, 0.009, 3.0, 1.5, 0.08, 2.0, 0.3, -14.0, -4.0, 0.0)},
    'Bounce': {"pattern": _BOUNCE},
    'Reverse Bounce': {"pattern": _REV_BOUNCE},
}
STROKES['Hoo'] = STROKES['High Hoo']


# THE VOICES' GESTURES: a word's syllable (where it starts, after its
# consonant), its pitch (semitones re f0), its life (dB) and its vowel's
# motion (0..1 toward the throat's DRUM_MODES_B), as contours; a consonant's
# key struck at its moment (a pattern, LAYER); reversed, all mirrored
def _vo(f0, dur, pitch, level, morph=None, ts=0.0, jitter=0.02, shimmer=1.0, syllables=None, mouth=None):
    return {"voiced": (syllables or ((ts, 0.0, 0.0),), f0, pitch, dur, 0.01, 0.0, jitter, shimmer, None, mouth,
                       level, morph)}


def _mirror(pts, length):
    return tuple(sorted((round(length - t, 4), v) for t, v in pts)) if pts else pts


def _vo_rev(f0, dur, pitch, level, morph=None, ts=0.0, total=None, mouth=None, **kw):
    total = total if total is not None else ts + dur
    return _vo(f0, dur, _mirror(pitch, dur), _mirror(level, dur), _mirror(morph, dur),
               ts=round(total - (ts + dur), 4), mouth=_mirror(mouth, dur), **kw)


_ONE = dict(f0=130.0, dur=0.32, pitch=((0.0, 0.5), (0.32, -1.5)),
            level=((0.0, -14.0), (0.04, 0.0), (0.22, -2.0), (0.32, -22.0)),
            morph=((0.0, 0.0), (0.12, 0.0), (0.3, 1.0)))
_TWO = dict(f0=130.0, dur=0.38, ts=0.04, pitch=((0.0, 0.5), (0.38, -2.0)),
            level=((0.0, -10.0), (0.03, 0.0), (0.25, -3.0), (0.38, -24.0)),
            morph=((0.0, 0.0), (0.1, 0.0), (0.36, 1.0)))
_THREE = dict(f0=130.0, dur=0.42, ts=0.09, pitch=((0.0, 0.0), (0.42, -2.0)),
              level=((0.0, -16.0), (0.05, 0.0), (0.3, -3.0), (0.42, -24.0)),
              morph=((0.0, 0.0), (0.08, 0.2), (0.25, 1.0)))
_TAH = dict(f0=140.0, dur=0.22, ts=0.035, pitch=((0.0, 0.5), (0.22, -1.0)),
            level=((0.0, -8.0), (0.02, 0.0), (0.12, -3.0), (0.22, -26.0)))
_DOUBY = dict(f0=150.0, dur=0.32, ts=0.02, pitch=((0.0, 0.0), (0.12, 0.0), (0.15, 2.0), (0.32, 1.0)),
              level=((0.0, -10.0), (0.02, 0.0), (0.1, -2.0), (0.13, -30.0), (0.15, -30.0), (0.17, 0.0),
                     (0.28, -3.0), (0.32, -26.0)),
              morph=((0.0, 0.0), (0.13, 0.0), (0.14, 1.0)))
# THE KAKEGOE, as it is described: the y into o in 0.1 s; from ~165 Hz up five
# semitones over 0.45 s and held; swelling to its loudest at 0.8 s, cut short
# at 1.05 into the stroke; a steady pressed voice (1.5% jitter)
_YO = dict(f0=165.0, dur=1.05, pitch=((0.0, 0.0), (0.45, 5.0), (1.05, 5.3)),
           level=((0.0, -16.0), (0.06, -4.0), (0.45, -2.0), (0.8, 0.0), (0.97, -3.0), (1.05, -30.0)),
           morph=((0.0, 0.0), (0.1, 1.0)), jitter=0.015)
STROKES.update({
    'Voice One': _vo(**_ONE), 'Reverse Voice One': _vo_rev(**_ONE),
    'Voice Two': _vo(**_TWO), 'Reverse Voice Two': _vo_rev(**_TWO),
    'Voice Three': _vo(**_THREE), 'Reverse Voice Three': _vo_rev(**_THREE),
    'Voice Tah': _vo(**_TAH), 'Reverse Voice Tah': _vo_rev(**_TAH),
    'Voice Ou': _vo(150.0, 0.35, ((0.0, 0.0), (0.35, -2.0)),
                    ((0.0, -18.0), (0.04, 0.0), (0.22, -3.0), (0.35, -26.0)), ((0.0, 0.0), (0.12, 0.0), (0.3, 1.0))),
    'Voice Au': _vo(150.0, 0.4, ((0.0, 1.0), (0.4, -2.0)),
                    ((0.0, -18.0), (0.04, 0.0), (0.25, -3.0), (0.4, -26.0)), ((0.0, 0.0), (0.15, 0.0), (0.35, 1.0))),
    'Voice Whey': _vo(160.0, 0.5, ((0.0, -2.0), (0.15, 3.0), (0.35, 4.0), (0.5, -1.0)),
                      ((0.0, -18.0), (0.06, -2.0), (0.2, 0.0), (0.38, -3.0), (0.5, -26.0)), ((0.0, 0.0), (0.12, 1.0))),
    # the croak: two rough pulses' worth, the second higher
    'Frog Voice': _vo(70.0, 0.1, ((0.0, 0.0), (0.1, -1.0)), ((0.0, -12.0), (0.02, 0.0), (0.08, -4.0), (0.1, -30.0)),
                      jitter=0.06, shimmer=2.0, syllables=((0.0, 0.0, 0.0), (0.17, -2.0, 2.0))),
    'Douby': _vo(**_DOUBY), 'Reverse Douby': _vo_rev(**_DOUBY),
    'Baert High': _vo(220.0, 0.3, ((0.0, 1.0), (0.3, -1.0)), ((0.0, -10.0), (0.02, 0.0), (0.2, -3.0), (0.3, -26.0)),
                      ((0.0, 0.0), (0.12, 0.0), (0.26, 1.0)), ts=0.015),
    'Baert Low': _vo(110.0, 0.3, ((0.0, 1.0), (0.3, -1.0)), ((0.0, -10.0), (0.02, 0.0), (0.2, -3.0), (0.3, -26.0)),
                     ((0.0, 0.0), (0.12, 0.0), (0.26, 1.0)), ts=0.015),
    'Yyoo Dude': _vo(**_YO), 'Reverse Yyoo Dude': _vo_rev(**_YO),
})
# THE VOICE SET'S WORDS (f0 Hz, length s, pitch semitones, level dB, the
# vowel's motion), each after its consonant (ts)
_COMEON = dict(f0=150.0, dur=0.45, ts=0.05, pitch=((0.0, 1.0), (0.15, 2.0), (0.45, -2.0)),
               level=((0.0, -14.0), (0.04, 0.0), (0.3, -3.0), (0.45, -26.0)), morph=((0.0, 0.0), (0.18, 0.1), (0.35, 1.0)))
_AOU = dict(f0=160.0, dur=0.6, pitch=((0.0, 0.0), (0.3, 2.0), (0.6, -2.0)),
            level=((0.0, -16.0), (0.05, 0.0), (0.45, -3.0), (0.6, -26.0)), morph=((0.0, 0.0), (0.2, 0.3), (0.5, 1.0)))
_OOU = dict(f0=150.0, dur=0.65, pitch=((0.0, 0.0), (0.3, 1.0), (0.65, -2.0)),
            level=((0.0, -16.0), (0.05, 0.0), (0.5, -3.0), (0.65, -26.0)), morph=((0.0, 0.0), (0.25, 0.0), (0.55, 1.0)))
_HIE = dict(f0=200.0, dur=0.4, ts=0.06, pitch=((0.0, 1.0), (0.4, -2.0)),
            level=((0.0, -10.0), (0.03, 0.0), (0.25, -3.0), (0.4, -26.0)), morph=((0.0, 0.0), (0.1, 0.0), (0.3, 1.0)))
_HIE2 = dict(_HIE, f0=260.0, dur=0.3, pitch=((0.0, 2.0), (0.3, -1.0)),
             level=((0.0, -10.0), (0.03, 0.0), (0.18, -3.0), (0.3, -26.0)), morph=((0.0, 0.0), (0.08, 0.0), (0.24, 1.0)))
_OOUE = dict(f0=180.0, dur=0.5, pitch=((0.0, 0.0), (0.25, 2.0), (0.5, 3.0)),
             level=((0.0, -16.0), (0.05, 0.0), (0.4, -2.0), (0.5, -26.0)), morph=((0.0, 0.0), (0.2, 0.0), (0.4, 1.0)))
# KIKIT: "ki" and "kit", each after its k, a t to close
_KIKIT = dict(f0=220.0, dur=0.12, pitch=((0.0, 0.0), (0.12, -1.0)), level=((0.0, -8.0), (0.02, 0.0), (0.09, -2.0), (0.12, -30.0)),
              syllables=((0.03, 0.0, 0.0), (0.2, 1.0, 1.0)), ts=0.03)
# the baby's giggle: six "ha"s high and falling, quieter as they go
_BABY = dict(f0=380.0, dur=0.08, pitch=((0.0, 1.0), (0.08, -1.0)), level=((0.0, -12.0), (0.015, 0.0), (0.06, -4.0), (0.08, -30.0)),
             syllables=tuple((round(0.12 * i, 3), -0.6 * i, -1.2 * i) for i in range(6)), jitter=0.03)
def _rev_syl(g, total):
    """A word of several syllables, reversed: each syllable's start mirrored
    (its end becomes its start), latest first."""
    return dict(g, syllables=tuple(sorted((round(total - (t + g['dur']), 4), p, l) for t, p, l in g['syllables'])))


_LAN = dict(f0=330.0, dur=0.75, pitch=((0.0, -0.3), (0.1, 0.0), (0.75, 0.0)),
            level=((0.0, -14.0), (0.08, 0.0), (0.6, -2.0), (0.75, -26.0)), morph=((0.0, 0.0), (0.45, 0.0), (0.65, 1.0)),
            jitter=0.01)
STROKES.update({
    'Voice ComeOn': _vo(**_COMEON), 'Reverse Voice Come On': _vo_rev(**_COMEON),
    'Voice Kikit': _vo(**_KIKIT), 'Reverse Voice Kikit': _vo_rev(**_rev_syl(_KIKIT, 0.36), total=0.36),
    'Voice Aou': _vo(**_AOU), 'Reverse Voice Aou': _vo_rev(**_AOU),
    'Voice Oou': _vo(**_OOU), 'Reverse Voice Oou': _vo_rev(**_OOU),
    'Voice Hie': _vo(**_HIE), 'Reverse Voice Hie 2': _vo_rev(**_HIE2),
    'Reverse Ooue!': _vo_rev(**_OOUE),
    'Baby Laughing': _vo(**_BABY), 'Reverse Baby Laughing': _vo_rev(**_rev_syl(_BABY, 0.68), total=0.68),
    'Jazz Voice Thum': _vo(140.0, 0.3, ((0.0, 0.0), (0.3, -1.0)), ((0.0, -10.0), (0.03, 0.0), (0.2, -4.0), (0.3, -28.0)),
                           ((0.0, 0.0), (0.12, 0.0), (0.25, 1.0)), ts=0.05),
    'Jazz Voice Bap': _vo(150.0, 0.16, ((0.0, 0.5), (0.16, 0.0)), ((0.0, -6.0), (0.02, 0.0), (0.13, -2.0), (0.16, -30.0)), ts=0.015),
    'Jazz Voice Dat': _vo(160.0, 0.16, ((0.0, 0.5), (0.16, 0.0)), ((0.0, -6.0), (0.02, 0.0), (0.13, -2.0), (0.16, -30.0)), ts=0.015),
    'Jazz Voice Dow': _vo(150.0, 0.35, ((0.0, 0.5), (0.35, -2.0)), ((0.0, -6.0), (0.02, 0.0), (0.25, -3.0), (0.35, -28.0)),
                          ((0.0, 0.0), (0.1, 0.0), (0.3, 1.0)), ts=0.015),
    'Japanese Female Voice Lah': _vo(330.0, 0.7, ((0.0, -0.3), (0.1, 0.0), (0.7, 0.0)),
                                     ((0.0, -20.0), (0.08, 0.0), (0.55, -2.0), (0.7, -26.0)), ((0.0, 0.0), (0.08, 1.0)),
                                     jitter=0.01),
    'Japanese Female Voice Lan': _vo(**_LAN), 'Reverse Japanese Female Voice Lan': _vo_rev(**_LAN),
    'Japanese Male Voice Wah': _vo(147.0, 0.6, ((0.0, -0.3), (0.1, 0.0), (0.6, 0.0)),
                                   ((0.0, -18.0), (0.06, 0.0), (0.45, -2.0), (0.6, -26.0)), ((0.0, 0.0), (0.1, 1.0)),
                                   jitter=0.012),
    'Japanese Male Voice Woh': _vo(147.0, 0.6, ((0.0, -0.3), (0.1, 0.0), (0.6, 0.0)),
                                   ((0.0, -18.0), (0.06, 0.0), (0.45, -2.0), (0.6, -26.0)), ((0.0, 0.0), (0.1, 1.0)),
                                   jitter=0.012),
})


# THE CONSONANTS: each a key below the set, struck at its moment in the word
# (a pattern of one stroke, or two), reversed at its mirror
def _at(*ts, db=-4.0):
    return {"pattern": tuple((round(t, 4), db, 0.0) for t in ts)}


_CONS = {   # name: (consonant, its times)
    'Voice Two': ('t', (0.0,)), 'Reverse Voice Two': ('t', (0.42,)),
    'Voice Three': ('th', (0.0,)), 'Reverse Voice Three': ('th', (0.41,)),
    'Voice Tah': ('t', (0.0,)), 'Reverse Voice Tah': ('t', (0.225,)),
    'Douby': ('d', (0.0, 0.15)), 'Reverse Douby': ('d', (0.19, 0.34)),
    'Baert High': ('d', (0.0,)), 'Baert Low': ('d', (0.0,)),
}
_HIDDEN = iter(range(1, 21))
_VOICE_LAYER = {}
for _w, (_c, _ts) in _CONS.items():
    _k = next(_HIDDEN)
    _nm = '%s (%s)' % (_w, _c)
    VOICE[_nm] = VOICE['consonant %s' % _c]
    STROKES[_nm] = _at(*_ts)
    _VOICE_LAYER[_w] = _VOICE_LAYER.get(_w, ()) + ((_k, _nm),)

# THE VOICE SET'S (SC-8850, 62): its words on the throat (tonelib.Rfx*Voice*,
# Rfx Scat, Jp), voiced from what each says -- no recording; Ben's ear to
# judge -- with their consonants, its breaths, its oohs and their chords
VOICE.update({
    'consonant k': ('c', 'RfxBurstKProperties', 1000.0), 'consonant p': ('c', 'RfxBurstPProperties', 1000.0),
    'consonant h': ('c', 'RfxBreathHProperties', 1000.0), 'consonant b': ('c', 'RfxBurstDProperties', 1000.0),
    'Voice ComeOn': ('c', 'RfxVoiceComeOnProperties', 1000.0),
    'Reverse Voice Come On': ('c', 'RfxVoiceComeOnProperties', 1000.0),
    'Voice Kikit': ('c', 'RfxVoiceKikitProperties', 1000.0),
    'Reverse Voice Kikit': ('c', 'RfxVoiceKikitProperties', 1000.0),
    'Voice Aou': ('c', 'RfxVoiceAouProperties', 1000.0), 'Reverse Voice Aou': ('c', 'RfxVoiceAouProperties', 1000.0),
    'Voice Oou': ('c', 'RfxVoiceOouProperties', 1000.0), 'Reverse Voice Oou': ('c', 'RfxVoiceOouProperties', 1000.0),
    'Voice Hie': ('c', 'RfxVoiceHieProperties', 1000.0),
    'Reverse Voice Hie 2': ('c', 'RfxVoiceHieProperties', 1000.0),
    'Reverse Ooue!': ('c', 'RfxVoiceOoueProperties', 1000.0),
    'Baby Laughing': ('c', 'RfxBabyLaughProperties', 1000.0),
    'Reverse Baby Laughing': ('c', 'RfxBabyLaughProperties', 1000.0),
    'Jazz Voice Thum': ('c', 'RfxScatThumProperties', 1000.0), 'Jazz Voice Bap': ('c', 'RfxScatAhProperties', 1000.0),
    'Jazz Voice Dat': ('c', 'RfxScatAhProperties', 1000.0), 'Jazz Voice Dow': ('c', 'RfxScatDowProperties', 1000.0),
    'Japanese Female Voice Lah': ('c', 'RfxJpLahProperties', 1000.0),
    'Japanese Female Voice Lan': ('c', 'RfxJpLanProperties', 1000.0),
    'Reverse Japanese Female Voice Lan': ('c', 'RfxJpLanProperties', 1000.0),
    'Japanese Male Voice Wah': ('c', 'RfxJpWahProperties', 1000.0),
    'Japanese Male Voice Woh': ('c', 'RfxJpWohProperties', 1000.0),
    # the SFX set's own
    'Punch': ('k', 56, 54), 'Screaming': ('k', 56, 53), 'Laughing': ('k', 56, 52),
    # BREATHS: GM 121's breath at a pitch (its noise's centre) and a length
    # (GATE): a flute's higher and shorter, a voice's lower; reversed, drawn
    # in -- a woman's brighter than a man's
    'Flute Breath 1': ('c', 'RfxFluteBreath1Properties', 1000.0), 'Flute Breath 2': ('c', 'RfxFluteBreath2Properties', 1000.0),
    'Flute Breath 3': ('c', 'RfxFluteBreath3Properties', 1000.0),
    'Voice Breath 1': ('c', 'RfxVoiceBreath1Properties', 1000.0), 'Voice Breath 2': ('c', 'RfxVoiceBreath2Properties', 1000.0),
    'Reverse Breath Slow': ('c', 'RfxRevBreathProperties', 1000.0),
    'Reverse Breath Short': ('c', 'RfxRevBreathShortProperties', 1000.0),
    'Reverse Breath Strong': ('c', 'RfxRevBreathStrongProperties', 1000.0),
    "Reverse Woman's Breath": ('c', 'RfxRevWomanBreathProperties', 1000.0),
    "Reverse Man's Breath": ('c', 'RfxRevManBreathProperties', 1000.0),
    # OOHS: GM 53's fitted choir "oo", one voice at F4; the chords that voice
    # stacked (Maj7 A on C4, B on F4; Sus4 A on C4, B on D4)
    'Voice Oohs 2': ('c', 'VoiceOohsDrumProperties', 349.23),
    'Voice Oohs Chord Maj7 A': ('c', 'VoiceOohsDrumProperties', 261.63),
    'Voice Oohs Chord Maj7 B': ('c', 'VoiceOohsDrumProperties', 349.23),
    'Voice Oohs Chord Sus4 A': ('c', 'VoiceOohsDrumProperties', 261.63),
    'Voice Oohs Chord Sus4 B': ('c', 'VoiceOohsDrumProperties', 293.66),
})
_CHORDS = {'Voice Oohs Chord Maj7 A': (329.63, 392.0, 493.88), 'Voice Oohs Chord Maj7 B': (440.0, 523.25, 659.26),
           'Voice Oohs Chord Sus4 A': (349.23, 392.0), 'Voice Oohs Chord Sus4 B': (392.0, 440.0)}
_HIDDEN2 = iter(range(97, 128))       # the Voice set's own: its keys end at 96
for _w, _hz in _CHORDS.items():
    for _f in _hz:
        _k = next(_HIDDEN2)
        _nm = 'Oohs %.2f Hz' % _f
        VOICE[_nm] = ('c', 'VoiceOohsDrumProperties', _f)
        _VOICE_LAYER[_w] = _VOICE_LAYER.get(_w, ()) + ((_k, _nm),)
# ...and its words' consonants, each at its moment (reversed, at its mirror)
_CONS2 = {   # word: ((consonant, its times), ...)
    'Voice ComeOn': (('k', (0.0,)),), 'Reverse Voice Come On': (('k', (0.475,)),),
    'Voice Kikit': (('k', (0.0, 0.17)), ('t', (0.33,))), 'Reverse Voice Kikit': (('t', (0.0,)), ('k', (0.16, 0.33))),
    'Voice Hie': (('h', (0.0,)),), 'Reverse Voice Hie 2': (('h', (0.32,)),),
    'Jazz Voice Thum': (('th', (0.0,)),), 'Jazz Voice Bap': (('b', (0.0,)), ('p', (0.18,))),
    'Jazz Voice Dat': (('d', (0.0,)), ('t', (0.18,))), 'Jazz Voice Dow': (('d', (0.0,)),),
}
for _w, _cs in _CONS2.items():
    for _c, _ts in _cs:
        _k = next(_HIDDEN2)
        _nm = '%s (%s)' % (_w, _c)
        VOICE[_nm] = VOICE['consonant %s' % _c]
        STROKES[_nm] = _at(*_ts)
        _VOICE_LAYER[_w] = _VOICE_LAYER.get(_w, ()) + ((_k, _nm),)

# ...AND ITS LENGTH, a one-shot's (percussion_map.KIT_GATE): Small Club's the
# takes' main burst, ~2.5 s; a choked crash's the hand's, 0.15 s
GATE = {'Rock Snare Dry': 0.25, 'Rock SD Dry': 0.25, 'MC-500 Beep 1': 0.04, 'MC-500 Beep 2': 0.04, 'Guitar Wah': 0.25, 'Biwa FX': 1.2,
        'Phonograph Noise': 2.0, 'Pick Scrape': 0.8, 'Telephone 1': 1.5, 'Small Club 2': 2.5,
        'Applause Wave': 3.0, 'Eruption': 2.5, 'Sagat Closed': 0.07, 'Gengari Mute Low': 0.12, 'Gengari Mute High': 0.12, 'Jing Mute': 0.35, 'Tang Gu Mute': 0.12, 'Alias': 0.9, 'Swish': 0.35, 'Velocity Noise FX': 0.4, 'Missile': 1.0, 'Tape Stop 1': 1.0, 'Tape Stop 2': 0.6,
        'Guitar Slide': 0.3, 'Small Club 1': 2.5, 'Mute Crash Cymbal 1': 0.15, 'Mute Crash Cymbal 2': 0.15,
        'Standard 1 Mute Crash Cymbal': 0.15, 'Room Mute Crash Cymbal': 0.15, 'Jazz Mute Crash Cymbal': 0.15,
        'Brush Mute Crash Cymbal': 0.15, 'Concert BD 1 Mute': 0.25,
        # the Voice set's breaths and oohs: their lengths
        'Flute Breath 1': 0.32, 'Flute Breath 2': 0.47, 'Flute Breath 3': 0.24, 'Voice Breath 1': 0.57,
        'Voice Breath 2': 0.77, 'Reverse Breath Slow': 0.95, 'Reverse Breath Short': 0.33, 'Reverse Breath Strong': 0.66,
        "Reverse Woman's Breath": 0.58, "Reverse Man's Breath": 0.58, 'Voice Oohs 2': 1.2,
        **{_n: 1.2 for _n in ('Voice Oohs Chord Maj7 A', 'Voice Oohs Chord Maj7 B', 'Voice Oohs Chord Sus4 A',
                              'Voice Oohs Chord Sus4 B')},
        **{'Oohs %.2f Hz' % _f: 1.2 for _hz in _CHORDS.values() for _f in _hz},
        # (the reversed words: FORWARD pulses, the gesture mirrored -- each
        # pulse reversed in its own period, Rhythm FX 2's way, read as noise:
        # periodicity 0.3-0.6 against 0.9; Ben, "just noise")
        }

# ...AND ITS RING (percussion_map.KIT_RING, PERCUSSION_RING's sense): the
# half-open hats', fitted to DRSKit's semi-open hat against its open one
# (examples/halfhat_fit.py) -- 2 halfway (in log) to the open hat
RING = {'Half-Open Hi-Hat 1': 0.0721, 'Half-Open Hi-Hat 2': 0.1344}
# ...the opera cymbals', fitted (examples/asia_fit.py naobo), the small pair shorter
RING['Nao Bo'] = 0.56
RING['Xiao Bo'] = 0.62
# ...the ride's zones Standard's ride's (PERCUSSION_RING[51])
RING.update({'Ride Cymbal %s %s' % (h, z): 0.5 for h in ('Low', 'Mid', 'High') for z in ('Inner', 'Edge')})
RING.update({'Ride Cymbal Edge': 0.5, 'Ride Cymbal Inner': 0.5})
# ...the brushed hats Standard's hats' (PERCUSSION_RING 42, 46)
RING.update({'Brush Closed Hi-Hat': 1.38, 'Brush Open Hi-Hat': 0.23})
# ...AND ITS LEVEL TRIM (percussion_map.KIT_LEVEL): the half-open hats the open
# hat's (PERCUSSION_LEVEL[46])
LEVEL = {'Half-Open Hi-Hat 1': 0.47, 'Half-Open Hi-Hat 2': 0.47}
# ...the crashes played by class (choked, brushed) Standard's crashes' ring and
# trim (PERCUSSION_RING/LEVEL 49, 57), the brushed one 9 dB under
RING.update({'Mute Crash Cymbal 1': 0.61, 'Mute Crash Cymbal 2': 1.69, 'Brush Crash Cymbal': 0.61})
# ...the SFX set's voices borrowed whole its trims (KIT_LEVEL[56] 47, 71)
LEVEL.update({'Guitar Slide': 59.315})
LEVEL.update({'Brush Closed Hi-Hat': 0.87, 'Brush Open Hi-Hat': 0.47})
# ...and Standard's voices borrowed whole theirs (PERCUSSION_LEVEL 28, 54)
LEVEL.update({'Slappy (slap)': 0.0771, 'Digital Tambourine': 1.1874})

# THE GAMELAN SETS (the SC-8850's Gamelan 1 and 2, kits 54 and 55): a Balinese
# gong kebyar. GAMELAN 1 in the UNT gamelan's own PELOG SELISIR -- its pemade's
# five tones (examples/gender_fit.py's survey: 457.6, 569.6, 600.2, 659.8,
# 830.4 Hz; steps 380, 90, 164, 397, 168 cents, each octave a register up or
# down); GAMELAN 2 the same instruments EQUAL-TEMPERED, each tone the nearest
# semitone (A#, C#, D, E, G#), to play beside Western parts (Ben). The ranges
# a kebyar's: the jegogan two octaves under the pemade, the jublag one, the
# penyacah the pemade's low register, the reyong's twelve from its second tone.
SELISIR = (457.6, 569.6, 600.2, 659.8, 830.4)


def _selisir(i, et=False):
    hz = SELISIR[i % 5] * 2.0 ** (i // 5)
    if et:
        import math
        hz = 440.0 * 2.0 ** (round(12.0 * math.log2(hz / 440.0)) / 12.0)
    return round(hz, 2)


def _et(hz):
    import math
    return round(440.0 * 2.0 ** (round(12.0 * math.log2(hz / 440.0)) / 12.0), 2)


# (instrument, class, the scale's steps from the pemade's 457.6 Hz)
GAMELAN_KEYS = (('Jegogan', 'GamelanJegoganProperties', range(-11, -6)),
                ('Jublag', 'GamelanJublagProperties', range(-6, -1)),
                ('Penyacah', 'GamelanPenyacahProperties', range(-1, 6)),
                ('Pemade', 'GamelanPemadeProperties', range(-1, 9)),
                ('Reyong', 'ReyongProperties', range(0, 12)))
for _inst, _cls, _steps in GAMELAN_KEYS:
    for _n, _i in enumerate(_steps):
        VOICE['%s %d' % (_inst, _n + 1)] = ('c', _cls, _selisir(_i))
        VOICE['%s %d ET' % (_inst, _n + 1)] = ('c', _cls, _selisir(_i, True))
# its drums at their takes' pitches; its gongs at UNT's (the wadon 58.0 Hz, the
# lanang 69.3: its gong takes hold the pair), the kempur an octave over the
# wadon, the kajar on the pemade's tone; the cymbals as the ceng-ceng
for _n, _c, _hz in (('Gamelan Gong Wadon', 'GamelanGongProperties', 58.0),
                    ('Gamelan Gong Lanang', 'GamelanGongProperties', 69.3),
                    ('Kempur', 'KempurProperties', 116.0), ('Kajar', 'KajarProperties', 457.6)):
    VOICE[_n] = ('c', _c, _hz)
    VOICE[_n + ' ET'] = ('c', _c, _et(_hz))
VOICE.update({
    'Kendang Wadon': ('c', 'KendangWadonProperties', 93.0), 'Kendang Lanang': ('c', 'KendangLanangProperties', 205.0),
    'Bebarongan': ('c', 'KendangBebaronganProperties', 196.0),
    'Pelegongan': ('c', 'KendangPelegonganProperties', 186.0),
    'Kelontuk': ('c', 'KelontukProperties', 290.0), 'Kelontuk Mute': ('c', 'KelontukMuteProperties', 478.0),
    'Kelontuk Side': ('c', 'KelontukSideProperties', 406.0),
    'Ceng-Ceng': ('c', 'CengCengProperties', 440.0),
    'Kopyak Open': ('c', 'KopyakProperties', 300.0), 'Kopyak Mute': ('c', 'KopyakProperties', 300.0)})
GATE.update({'Kajar': 0.15, 'Kajar ET': 0.15, 'Kopyak Mute': 0.08})
# ...their exclusive classes ([EXC1] the kelontuk's three, [EXC2] the kopyak's two)
SET_CHOKE = {54: [{40, 41, 42}, {46, 47}], 55: [{40, 41, 42}, {46, 47}]}


# STANDARD'S OWN DRUM ELSEWHERE: these class voices wear Standard's ring and
# level for the key named (percussion_map._build_gs_sets), their LEVEL a trim
# on it -- the Room set's (Standard's in the live room) and the left foot's
STANDARD_OF = {'Room Kick 1': 36, 'Room Kick 2': 35, 'Room Snare 1': 38, 'Room Snare 2': 40,
               'Room Closed Hi-Hat': 42, 'Room Closed Hi-Hat 3': 42, 'Room Open Hi-Hat': 46,
               'Room Open Hi-Hat 3': 46, 'Room Crash Cymbal': 49, 'Room Ride Cymbal': 51, 'Room Ride Bell': 53,
               'Closed Hi-hat3 C': 42, 'Open Hi-hat3': 46, '[L] Standard Kick 1': 36, '[L] Standard Kick 2': 35, '[L] Room Kick 1': 36, '[L] Room Kick 2': 35}


# THE CLASS VOICES LEVELLED to the kit (examples/gs_levels.py)
LEVEL.update({'High Hoo': 43.9236, 'Low Hoo': 70.5532, 'Hoo': 42.9539, 'Yyoo Dude': 87.9449, 'Reverse Yyoo Dude': 490.848, 'Voice One': 95.1735, 'Reverse Voice One': 241.4161, 'Voice Two': 94.8676, 'Reverse Voice Two': 233.8809, 'Voice Three': 102.6541, 'Reverse Voice Three': 206.488, 'Voice Tah': 130.6951, 'Reverse Voice Tah': 280.3505, 'Voice Ou': 102.0971, 'Voice Au': 103.6908, 'Voice Whey': 74.2745, 'Frog Voice': 80.4819, 'Douby': 114.649, 'Reverse Douby': 247.8117, 'Baert High': 81.688, 'Baert Low': 122.9863, 'Techno Thip': 4.281, 'Pop Drop': 2.4134, 'Syn. Drops': 3.594, 'Pipe': 1.4294, 'Noise Attack': 0.5112, 'Bounce': 2.2248, 'Reverse Bounce': 2.2902, 'Distortion Knock': 5.3581, 'Swish': 4.1329, 'Velocity Noise FX': 3.5333, 'Spark': 3.0143, 'Space Birds': 2.961, 'Tape Stop 1': 4.6273, 'Tape Stop 2': 6.1098, 'Emergency !': 3.7488, 'Calculating...': 4.5691, 'Saw LFO Saw': 3.0384, 'Woody Slap': 1.5678, 'Ice Block': 2.2633, 'Modulated Bell': 0.5649, 'Alias': 3.6555, 'Stereo Noise Clap': 1.6868, 'Flying Monster': 6.0009, 'Bend Gong': 0.595, 'Hu Yin Luo Low': 0.4998, 'Hu Yin Luo Mid': 0.5653, 'Hu Yin Luo Mid 2': 0.5636, 'Hu Yin Luo High': 0.6186, 'Hu Yin Luo High 2': 0.6435, 'Pai Ban': 1.7533, 'Tang Gu Mute': 1.4555, 'Low Kotsuzumi': 1.4294, 'Wadaiko Rim': 2.1837, 'Small Taiko': 1.5138, 'Buk Rim': 1.9684, 'Gengari p': 0.5949, 'Jang-Gu Rim': 2.083, 'Jing p': 0.2654, 'Jing f': 0.5315, 'Jing Mute': 0.5315, 'Gamelan Gong 1': 0.4601, 'Gamelan Gong 2': 0.4982, 'Gamelan Gong 3': 0.5458, 'Gamelan Gong 4': 0.5881, 'Gamelan Gong 5': 0.6136, 'Gamelan Gong 6': 0.6423, 'Gamelan Gong 7': 0.667, 'Gamelan Gong 8': 0.6863, 'Gamelan Gong 9': 0.6697, 'Gamelan Gong 10': 0.6878, 'Bonang 1': 0.4947, 'Bonang 2': 0.5771, 'Bonang 3': 0.6025, 'Bonang 4': 0.6666, 'Bonang 5': 0.53, 'Bendir': 0.5921, 'Udo Short': 1.9571, 'Udo Slap': 1.5506, 'Talking Drum': 1.483, 'Mute Pandiero': 2.0032, 'Tamborim': 1.5554, 'Tabla Te': 1.6667, 'Tabla Ge': 0.604, 'MC-500 Beep 1': 3.9281, 'MC-500 Beep 2': 3.1058, 'Guitar Wah': 2.0689, 'Biwa FX': 2.5052, 'Phonograph Noise': 7.212, 'Tape Rewind': 3.3312, 'Bass Slide': 49.3266, 'Pick Scrape': 2.0225, 'Bird 2': 0.6743, 'Telephone 1': 0.0748, 'Telephone 2': 3.0982, 'Eruption': 1.6774, 'Big Shot': 4.2851, 'LoFi Snare 2': 0.3231, 'LoFi Snare Rim': 1.5021, 'Hip-Hop Claps': 2.4116, 'HipHop Snare 1': 0.3376, 'HipHop Snare 2': 0.2828, 'R&B Claps': 1.8039, 'Jungle Snare': 0.3995, 'Jungle Snare Rim': 1.658, 'Jungle Crash': 0.8649, 'Jungle Shaker': 1.8687, 'Jungle Snare Roll': 0.3528, 'Techno Snare': 1.5174, 'TR-909 Claps': 1.6031, 'Comp Claps 2': 1.4772, 'Hip-Hop Kick 1': 0.5382, 'Hip-Hop Kick 2': 0.6671, 'Rap Snare': 0.3376, 'Hip-Hop Snare 2': 0.2787, 'Jungle Kick 1': 0.6524, 'Jungle Kick 2': 0.5588, 'Jungle Snare 1': 0.3995, 'Jungle Snare 2': 0.3782, 'Jungle Hi-Hat': 3.0645, 'Techno Snare 1': 1.5017, 'Techno TR-808 Kick': 0.6877, 'Techno TR-606 Snare 2': 0.5233, 'Jazz Mid Tom 1': 1.4206, 'Room Kick 1': 0.3214, 'Room Kick 2': 0.3308, 'Room Snare 1': 0.3542, 'Room Snare 2': 0.3215, 'Room Closed Hi-Hat 3': 0.3422, 'Room Open Hi-Hat 3': 0.3215, 'Room Crash Cymbal': 0.3906, 'Room Ride Cymbal': 0.4399, 'Room Ride Bell': 0.4445, 'Kendang Wadon': 2.9287, 'Kendang Lanang': 1.9952, 'Bebarongan': 3.7648, 'Pelegongan': 0.1544, 'Kelontuk': 2.3579, 'Kelontuk Mute': 11.8211, 'Kelontuk Side': 7.4748, 'Gamelan Gong Wadon': 0.4344, 'Gamelan Gong Wadon ET': 0.4344, 'Gamelan Gong Lanang': 0.4749, 'Gamelan Gong Lanang ET': 0.4749, 'Kempur': 0.6143, 'Kempur ET': 0.6143, 'Kajar': 0.4795, 'Kajar ET': 0.4795, 'Kopyak Open': 0.5287, 'Reyong 1': 0.5185, 'Reyong 1 ET': 0.5185, 'Reyong 2': 0.5185, 'Reyong 2 ET': 0.5185, 'Reyong 3': 0.5185, 'Reyong 3 ET': 0.5185, 'Reyong 4': 0.5185, 'Reyong 4 ET': 0.5185, 'Reyong 5': 0.5185, 'Reyong 5 ET': 0.5185, 'Reyong 6': 0.5185, 'Reyong 6 ET': 0.5185, 'Reyong 7': 0.5185, 'Reyong 7 ET': 0.5185, 'Reyong 8': 0.5185, 'Reyong 8 ET': 0.5185, 'Reyong 9': 0.5185, 'Reyong 9 ET': 0.5185, 'Reyong 10': 0.5185, 'Reyong 10 ET': 0.5185, 'Reyong 11': 0.5185, 'Reyong 11 ET': 0.5185, 'Reyong 12': 0.5185, 'Reyong 12 ET': 0.5185, 'Kopyak Mute': 0.5287})
# ...the SC-88 map's names for the Room hats, at the Room hats' levels
LEVEL['Closed Hi-hat3 C'] = LEVEL['Room Closed Hi-Hat 3']
LEVEL['Open Hi-hat3'] = LEVEL['Room Open Hi-Hat 3']

# ...a word's consonant at its word's trim: they were balanced together
for _w, (_c, _ts) in _CONS.items():
    if _w in LEVEL:
        LEVEL['%s (%s)' % (_w, _c)] = LEVEL[_w]

# A SOUND OF TWO VOICES (percussion_map._build_gs_sets): its second voice, on
# a key below the set's own, struck with it
LAYER = {'Slappy': ((16, 'Slappy (slap)'),)}
LAYER.update(_VOICE_LAYER)      # the voices' consonants (above)
# ...the Brush set's toms' swish (tonelib.BrushSwishProperties), on keys below
# the set's, its level fitted (examples/stroke_diff_fit.py --swish)
LAYER.update({'Brush High Tom 1': ((1, 'Brush swish high'),), 'Brush High Tom 2': ((2, 'Brush swish high'),),
              'Brush Mid Tom 1': ((3, 'Brush swish mid'),), 'Brush Mid Tom 2': ((4, 'Brush swish mid'),),
              'Brush Low Tom 1': ((5, 'Brush swish low'),), 'Brush Low Tom 2': ((6, 'Brush swish low'),)})
LEVEL.update({'Brush swish high': 0.0562, 'Brush swish mid': 0.0891, 'Brush swish low': 0.0447})
# ...the riq's and the pandeiro's jingles (our tambourine, on keys below the
# Ethnic set's: it has none under 25), 9 dB under the head
LAYER.update({'Req Dum': ((20, 'Req jingles'),), 'Req Tik': ((21, 'Req jingles'),),
              'Open Pandiero': ((22, 'Pandiero jingles'),), 'Mute Pandiero': ((23, 'Pandiero jingles'),)})
VOICE['Req jingles'] = VOICE['Pandiero jingles'] = ('c', 'TambourineProperties', 1000.0)
LEVEL.update({'Req jingles': round(1.1874 * 10 ** (-9 / 20.0), 4), 'Pandiero jingles': round(1.1874 * 10 ** (-9 / 20.0), 4)})
# ...a REVERSED voice's pulses each gated to its period (1/f0): a pulse turned
# round must land somewhere, and ungated a one-shot runs on to its ring
GATE.update({'Reverse Voice One': round(1 / _ONE['f0'], 4), 'Reverse Voice Two': round(1 / _TWO['f0'], 4),
             'Reverse Voice Three': round(1 / _THREE['f0'], 4), 'Reverse Voice Tah': round(1 / _TAH['f0'], 4),
             'Reverse Douby': round(1 / _DOUBY['f0'], 4), 'Reverse Yyoo Dude':
             round(1 / (_YO['f0'] * 2 ** (5 / 12.0)), 4)})
LEVEL.update({'Mute Crash Cymbal 1': 0.56, 'Mute Crash Cymbal 2': 0.56,
              'Brush Crash Cymbal': round(0.56 * 10 ** (-9 / 20.0), 4)})
# ...the kits' choked crashes their kit's crash's ring and trim (Room's and
# Brush's KIT_RING/LEVEL 49; Jazz's crash plays at its class's own level)
RING.update({'Standard 1 Mute Crash Cymbal': 0.61, 'Room Mute Crash Cymbal': 0.61,
             'Jazz Mute Crash Cymbal': 0.61, 'Brush Mute Crash Cymbal': 0.61})
LEVEL.update({'Concert BD 1 Mute': 0.151})          # the open drum's trim (Orchestra's 36)
LEVEL.update({'Dholak 1': 3.5487, 'Dholak 2': 4.9493})   # to the kit's drum target (examples/gs_levels.py)
# the Voice set's words, breaths and oohs, to the voices' target (examples/gs_levels.py)
LEVEL.update({'Voice ComeOn': 89.9813, 'Reverse Voice Come On': 92.801, 'Voice Kikit': 93.8224, 'Reverse Voice Kikit': 97.3389, 'Voice Aou': 83.9786, 'Reverse Voice Aou': 82.1472, 'Voice Oou': 100.8626, 'Reverse Voice Oou': 92.9273, 'Voice Hie': 82.9223, 'Reverse Voice Hie 2': 68.8167, 'Reverse Ooue!': 79.7716, 'Baby Laughing': 77.4072, 'Reverse Baby Laughing': 81.3076, 'Jazz Voice Thum': 102.1189, 'Jazz Voice Bap': 98.1927, 'Jazz Voice Dat': 107.5652, 'Jazz Voice Dow': 104.1424, 'Japanese Female Voice Lah': 67.8286, 'Japanese Female Voice Lan': 66.616, 'Reverse Japanese Female Voice Lan': 61.8973, 'Japanese Male Voice Wah': 93.7862, 'Japanese Male Voice Woh': 97.8748, 'Flute Breath 1': 58.3598, 'Flute Breath 2': 40.304, 'Flute Breath 3': 65.7982, 'Voice Breath 1': 44.4818, 'Voice Breath 2': 41.0972, 'Reverse Breath Slow': 32.4014, 'Reverse Breath Short': 28.6213, 'Reverse Breath Strong': 18.1199, "Reverse Woman's Breath": 32.4493, "Reverse Man's Breath": 27.8928, 'Voice Oohs 2': 1.6137, 'Voice Oohs Chord Maj7 B': 0.618})
LEVEL.update({'Standard 1 Mute Crash Cymbal': 0.56, 'Room Mute Crash Cymbal': 0.218736,
              'Brush Mute Crash Cymbal': 0.1987})

# Every name the SC-88 Pro's sets use has a voice here (2026-10-25); a few
# are the nearest we have (APPROX), and Standard's Voice One-Three (17-19)
# stay silent: its keys play no voiced strokes.


# THE SC-8850's VERSIONS OF THE SETS, OURS (percussion_sc8850, written from its
# manual by examples/sc8850_sets.py): its revised sets extending the native
# kits, its added programs native kits of their own; an [RND] name our voice
# each strike varied
import percussion_sc8850 as _S8850   # noqa: E402
SETS.update(_S8850.SETS)
SET_KIT.update(_S8850.SET_KIT)
SET_NAME.update(_S8850.SET_NAME)
SET_ALONE |= _S8850.SET_ALONE
SET_EXTEND |= _S8850.SET_EXTEND
SET_BASE = dict(_S8850.SET_BASE)
SET_SILENCE = set(_S8850.SET_SILENCE)
for _n, _spec in _S8850.RND.items():
    VOICE.setdefault(_n, _spec)
