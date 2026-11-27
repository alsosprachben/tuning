"""THE HELP: every topic the native interface's ? shows (nui/help.h reads
ui/help.json, written from this by examples/help_json.py -- the credits'
terms filled from ui/credits.json there). Each topic: a title, an intro, and
its terms -- [term, what it says] pairs, or a string alone as a heading.
HELP_TOC: the contents, (group, [topic keys]) in the order shown.

Until 2026-11-25 this lived in the web interface's ui/help.js (deprecated
with it); the words were carried over unchanged."""

HELP = {
    'basics': {'title': 'Using the screen',
     'intro': 'The front panel along the top always shows the selected part. The card keys under it choose the card '
              'below. Every card has a ? beside its name, and so do the regions inside it.',
     'terms': ['Touching the controls',
               ['Drag', 'Up or right turns a knob, fader or field up; down or left turns it down.'],
               ['Fine',
                'Rest a second finger anywhere off the controls while you drag: the control moves ten times finer.'],
               ['Detent',
                'A named position (a centre, 0 dB, triangle, saw or square on a wave knob) holds the value for a moment '
                'as you drag past it.'],
               ['Double-tap', "Puts the control back to the patch's own value (or its default)."],
               ['Long-press', 'Opens a sheet to type the exact value.'],
               ['Orange', "A control drawn in orange (redder than the display's amber) has been changed from the patch."],
               'The card keys',
               ['PARTS',
                'Every part: its key range, level, pan, transpose, channel, mute and solo; layer, split and remove '
                'parts.'],
               ['LIBRARY', 'Every patch, by family or by search: tap one to play it on the selected part.'],
               ['SYNTH',
                "The selected part's synth knobs, laid out after the Moog Messenger's panel. Only for the synth "
                'programs.'],
               ['STOPS', "The selected part's organ: its stops or drawbars, and a tonewheel organ's drive."],
               ['PIANO', 'The pedals, the dampers on the strings, and a key used as the sustain pedal.'],
               ['DRUMS', 'The drum kits and their sounds as pads to play; the user sets.'],
               ['AMP', "The selected part's speaker, its pickups, its valve's drive, and a rotary speaker's rotors."],
               ['EFFECTS', 'The insertion effect, and the reverb, chorus, delay and EQ every part shares.'],
               ['MATRIX', 'What the wheels, aftertouch and two controllers move on the selected part.'],
               ['TUNING', "The tuning every part plays in, and the Indian voices' raga tuning."],
               ['CONTROL',
                "Controls on the screen for what the keyboard lacks, routes that rewrite the keyboard's own, the "
                'metronome and the GS reset.'],
               ['SCENES', 'Presets and scenes to save and bring back.'],
               ['FILES', 'MIDI files on this machine: play one live, or render it to a WAV.'],
               ['SETUP', 'MIDI inputs, the Messenger, the sound settings for every part, and the room.']]},
    'display': {'title': 'The display',
     'intro': 'The selected part, how hard the engine is working, and the levels.',
     'terms': [['PART', "The selected part's number. ◀ PART and PART ▶ choose another."],
               ['Name line',
                'The program number (a variation after the dot), its family, and the channel it listens on. ALL CH means '
                'every channel.'],
               ['CPU',
                "How much of each audio block's time the engine spends making sound, on average. GPU+CPU when the "
                'graphics chip is helping. Near 100% the sound may break up.'],
               ['VOICES', 'How many voices are sounding now.'],
               ['BUILDING',
                'The engine is building the sounds for a new patch or tuning; the number is how far along it is. A patch '
                'plays when its build is done.'],
               ['UNDERRUNS', 'How many times the sound dropped out because a block was late.'],
               ['RT DROPPED',
                'The engine gave up its real-time priority after a block ran away. Restart nvlive to get it back.'],
               'The seven fields',
               ['',
                'Tap a field to choose it, then drag it or turn the dial. Double-tap puts it back; long-press to type '
                'the value.'],
               ['LEVEL', "The part's level in dB."],
               ['PAN', 'Left to right: L64 to C (the centre) to R63.'],
               ['REVERB', 'How much of the part goes to the reverb, 0 to 127.'],
               ['CHORUS', 'How much goes to the chorus, 0 to 127.'],
               ['DELAY', 'How much goes to the delay, 0 to 127.'],
               ['KEY', 'Transpose, in semitones (up to two octaves either way).'],
               ['CH', 'The MIDI channel the part listens to; ALL is every channel.'],
               'The meters',
               ['Two long bars', "The output's left and right peaks. Red within 1 dB of the top."],
               ['1 to 16', "Each MIDI channel's level."]]},
    'panel': {'title': 'The panel keys and the dial',
     'intro': 'These act on the selected part.',
     'terms': [['◀ PART / PART ▶', 'Select the part before or after.'],
               ['MUTE', 'Silences the selected part (lit while muted). Tap again to hear it.'],
               ['SOLO', 'Only the soloed parts sound (lit while soloed). Tap again to take it out of the solo.'],
               ['PANIC',
                'All notes off: every sounding note on every part is let go and fades as if its key were lifted, and '
                'notes left stuck with no key are cleared. Use it when a note hangs. Sounds and settings are not '
                'changed.'],
               ['The dial',
                'Turns the field chosen on the display, a step each 15 degrees. The word under it names the field.']]},
    'parts': {'title': 'Parts',
     'intro': 'A part is one sound with its own keys, channel and level. Several parts can share the keyboard: layered '
              '(the same keys) or split (different keys).',
     'terms': ['The keyboard',
               ['Bars under the keys',
                "Each part's key range. The selected part is lit; a muted or silenced part is dim."],
               ['Tap a bar', 'Selects that part.'],
               ["Drag a bar's end", "Moves that end of the part's range, key by key."],
               'The buttons',
               ['LAYER',
                'Adds a copy of the selected part, with the same keys and channel. Choose another patch for it in the '
                'Library to play two sounds at once.'],
               ['SPLIT',
                "Cuts the selected part's keys in two at the middle. The upper half becomes a new part; choose its sound "
                'in the Library.'],
               ['REMOVE', 'Takes the selected part away and lets its notes go. The first part cannot be removed.'],
               "Each part's strip",
               ['Name', 'Tap to select the part.'],
               ['level', "The part's level, −30 to +10 dB. Double-tap for 0 dB."],
               ['pan', 'Left to right. Double-tap for the centre.'],
               ['KEY', 'Transpose in semitones. Double-tap for none.'],
               ['CH', 'The channel it listens to; ALL is every channel.'],
               ['MUTE / SOLO', 'As the panel keys, for this part.'],
               ['VEL / FIXED',
                "VEL: how hard you play sets how loud. FIXED: every key sounds the same, as an organ's keys do."]]},
    'library': {'title': 'Library',
     'intro': 'Every patch, to play on the selected part.',
     'terms': [['Families (left)',
                "★ Favourites, All, the sixteen General MIDI families, Drum kits, and the MT-32's and CM-64's own "
                'tones.'],
               ['Standards (under the search)',
                "ALL, or a standard: GM1, GM2, GS1 (the SC-55's), GS2 (SC-88), GS3 (SC-88 Pro), GS4 (SC-8850), or CVT1 "
                "(Clavitone's own). A standard shows every patch a file written for it can select: GM2 includes GM1's, "
                "and each GS map includes GM1's and the maps before it. A tile says the standards it belongs to: the "
                'earliest of each, so a tone GM 2 took from the SC-55 says GM2 GS1.'],
               ['Search',
                "Type words: a patch shows if its number, name or family has them all. The screen's own keys come up: "
                'CLEAR empties it, ⌫ takes a letter back, DONE puts the keys away.'],
               ['A tile',
                "Tap to play that patch on the selected part. The lit tile is the part's patch now; one blinking is "
                'still being built.'],
               ['Number', 'The program number, a variation after the dot; KIT and a number for a drum kit.'],
               ['★', 'Keeps the patch in Favourites (saved beside the session).']]},
    'synth': {'title': 'Synth',
     'intro': "The selected part's synth, laid out after the Moog Messenger's front panel, then the delay. Each section "
              "has its own ?. Long-press a knob for its exact value and the Messenger's name for it.",
     'terms': [['LAYER A / LAYER B', 'A patch made of two synths: which one the knobs show.'],
               ['N CHANGED · BACK TO THE PATCH',
                'How many controls you have changed; tap to put them all back. AS THE PATCH when none are.'],
               ['CONTROLS TEST', 'Opens a page of every kind of control, to try them.'],
               ['Orange', "Changed from the patch. Double-tap a knob, or a switch's name, to put it back."],
               ['IN A MIDI FILE',
                "CC86 at 64 or more puts a channel in Messenger mode: from there on it reads the Moog Messenger's own CC "
                "chart, so a file (or a sequencer) sets these knobs with the Messenger's numbers -- CC19 the cutoff, "
                'CC21 the resonance, and so on, the fine half of a knob 32 above it -- and a real Messenger on that '
                'channel follows the same file. Those numbers stop meaning what General MIDI says (CC10 is the '
                "Messenger's TUNE, not pan); volume, sustain, the reverb send and the mod wheel keep theirs. Below 64 it "
                'is General MIDI again; a GM System On or GS Reset turns it off. A program change keeps the mode and '
                "puts the knobs back to the new voice's own. In a file each note plays the knobs as they are when it "
                'starts; played live, turning one moves the notes sounding too.']]},
    'synth:LFO 1': {'title': 'LFO 1',
     'intro': 'A slow oscillator that moves one thing up and down by itself.',
     'terms': [['LFO 1 rate', 'How fast it moves.'],
               ['Waveshape',
                'The shape of the movement: tri (smooth up and down), saw, ramp, square (jumps between two values).'],
               ['LFO 1 depth', 'How far it moves.'],
               ['Destination',
                "What it moves: cutoff (the filter), osc 2 freq (oscillator 2's pitch), osc 1 wave, sub wave (their "
                'shapes).'],
               ['KB reset', 'On: each new key starts the LFO from the beginning.']]},
    'synth:Left hand': {'title': 'Left hand',
     'intro': 'The controls by the wheels: glide, and what the mod wheel brings in through LFO 2. Turn the mod wheel up '
              'to hear it.',
     'terms': [['Glide', "How long a note takes to slide to the next one's pitch. 0 is no glide."],
               ['LFO 2 rate', 'How fast LFO 2 moves.'],
               ['Pitch', 'On: the mod wheel brings LFO 2 onto the pitch (vibrato).'],
               ['Cutoff', 'On: onto the filter (wah).'],
               ['Amp', 'On: onto the level (tremolo).']]},
    'synth:Oscillators': {'title': 'Oscillators',
     'intro': 'The two oscillators, 1 and 2, and the sub oscillator an octave under oscillator 1.',
     'terms': [['Octave', "The oscillator's octave, in organ feet: 32′ is lowest, 4′ highest."],
               ['Tune', 'Fine tuning.'],
               ['Sub wave', "The sub oscillator's shape, sweeping smoothly from triangle to square to a narrow pulse."],
               ['Waveshape',
                "The oscillator's shape, sweeping smoothly: fold, triangle, saw, square, pulse. The ticks mark triangle, "
                'saw and square; the little screen shows the wave.'],
               ['Osc 2 freq',
                "Oscillator 2's pitch against oscillator 1: in tune at the centre, or a chosen interval for fatter or "
                'harmonised sounds.'],
               ['Mod amount', 'How much the mod destination is moved.'],
               ['Sync 1→2',
                'On: oscillator 2 restarts with every cycle of oscillator 1, for a hard, tearing tone as osc 2 freq '
                'moves.'],
               ['Mod destination',
                "1→2 FM: oscillator 1 bends oscillator 2's pitch at audio speed (bell and metal tones). F env→osc 2 "
                'freq, F env→osc 2 wave, F env→sub wave: the filter envelope moves that instead.']]},
    'synth:Mixer': {'title': 'Mixer',
     'intro': 'How much of each source goes into the filter.',
     'terms': [['Osc 1', "Oscillator 1's level."],
               ['Sub osc', "The sub oscillator's level."],
               ['Osc 2', "Oscillator 2's level."],
               ['Noise', 'White noise, for breath and percussion.']]},
    'synth:Filter': {'title': 'Filter',
     'intro': 'The filter shapes the brightness of the sound.',
     'terms': [['Cutoff', 'Where the filter starts to cut: low is dark, high is bright.'],
               ['EG amount', 'How far the filter envelope opens the filter on each note.'],
               ['Resonance', 'A peak at the cutoff; turned high, it rings and whistles.'],
               ['KB tracking',
                'off: the cutoff is the same on every key. 1:1: it rises with the key, so high notes stay as bright as '
                'low ones.'],
               ['Mode',
                '4P LP: a steep low-pass (after the classic Moog ladder). 2P LP: a gentler low-pass. BP: band-pass, only '
                'the middle. HP: high-pass, only the top.'],
               ['Res bass', 'Puts back the bass that resonance takes away.']]},
    'synth:Envelopes': {'title': 'Envelopes',
     'intro': 'How each note moves over time: the filter envelope (top row) opens the filter, the amplifier envelope '
              '(second row) shapes the level.',
     'terms': [['Attack', 'How long the note takes to rise when the key goes down.'],
               ['Decay', 'How long it takes to fall to the sustain level.'],
               ['Sustain', 'The level held while the key stays down.'],
               ['Release', 'How long it takes to die away after the key comes up.'],
               ['Multi-trig', 'On: every key restarts the envelopes, even when played legato.'],
               ['F env vel', 'On: playing harder opens the filter envelope further.'],
               ['A env vel', 'Whether playing harder is louder: voice (as the patch has it), off or on.'],
               ['F env loop / A env loop', 'On: the envelope repeats while the key is held, as a rhythmic pulse.']]},
    'synth:Delay': {'title': 'Delay',
     'intro': 'An analog-style echo after the synth.',
     'terms': [['On', 'Turns the echo on.'],
               ['Range', 'short or long echo times.'],
               ['Time', 'The time between echoes.'],
               ['Feedback', 'How many echoes: more feedback, more repeats.'],
               ['Mix', 'How loud the echoes are against the dry sound.'],
               ['LFO rate / LFO amount', 'A slow wobble of the echo time, for a chorus-like or tape-like sway.']]},
    'stops': {'title': 'Stops',
     'intro': "The selected part's organ. A pipe organ shows its stops by division; a tonewheel organ shows its drawbars "
              'and percussion. A part that is not an organ shows organs to put on it.',
     'terms': [['A stop', 'Tap to draw it (lit) or put it in. Taps land at once, however fast.'],
               ['16′, 8′, 4′…',
                'The pitch in organ feet: 8′ sounds as written, 16′ an octave lower, 4′ an octave higher; 2-2/3′ and '
                '1-3/5′ add the twelfth and the seventeenth.'],
               ['Perc 3rd / Perc 2nd',
                "A tonewheel organ's percussion: a short ping on the third or second harmonic as each key goes down, "
                'voiced two ways, L102 and B3.'],
               ['N of M drawn', 'How many stops are drawn.'],
               ['The line below', 'Touch a stop for what it is.']]},
    'drive': {'title': 'Valve (drive)',
     'intro': "The valve amplifier's drive, in front of the speaker (or an organ's rotary speaker): a guitar's, a "
              "bass's, an organ's. On the AMP card for every amplified voice; an organ's on its Stops card too, where "
              'the mod wheel is the swell pedal.',
     'terms': [['Drive',
                '0 is clean; 1 the edge of breakup; turned past it, it growls and clips. Its distortion is mostly the '
                'notes mixing, so a chord thickens where one note barely would. Two knobs: DRIVE, the drive set (the '
                "patch's own, or turned), and WITH THE WHEEL, what plays: the mod wheel scales the drive, up to four "
                "times the patch's own. Both reach that far (at least 3)."],
               ['AS THE PATCH (n)', "The knob is at the patch's own drive, n."],
               ["BACK TO THE PATCH'S n",
                "You have turned it; tap to put the patch's own back. Double-tapping the knob does the same."]]},
    'rotary': {'title': 'Rotary',
     'intro': 'How the rotating speaker is heard. Organs stand their cabinet in the room; the Rotary insertion effect '
              'records it with two mics. Either can be switched, part by part, and the part keeps it through program '
              'changes.',
     'terms': [['IN THE ROOM',
                'The cabinet heard where it stands: its horn and drum turning toward you and away, the room around it.'],
               ['TWO MICS',
                'The cabinet as a studio records it: a mic either side, one to each speaker, each hearing the rotors '
                'from its own angle. Wide.'],
               ['SPREAD',
                'How far apart the two mics stand round the cabinet, in degrees. Double-tap for the default, the Rotary '
                "effect's own (136°)."],
               ['CC82',
                "A file or a keyboard knob sets it too, on the part's channel: 0 the cabinet in the room, 1 to 127 two "
                "mics, the value × 180/127 degrees apart (96 is 136°, the Rotary effect's own scale). A note hears the "
                'setting it starts under.']]},
    'couplers': {'title': 'Couplers',
     'intro': "A 60's organ's coupler switches, on the left of its console: each makes the voices it takes sound again "
              "at another octave, on the manual it belongs to. The upper's take its six 8' voices (Flute, Diapason, "
              "String, Oboe, Trumpet, Kinura); the lower's every voice but its Quint. A Solo tab raises the coupled "
              'pitches with their voice.',
     'terms': [["16'", "Upper to Upper 16': each voice an octave lower as well."],
               ["4'", "Upper to Upper 4', Lower to Lower 4': each voice an octave higher as well."],
               ["2'", "Upper to Upper 2': each voice two octaves higher as well."],
               ["8' OFF", "The coupled voices' own pitch silenced, their couplers' kept: with 4', a voice at 4' alone."],
               ['CC87',
                "A file or a keyboard sets them too, on the part's channel, a bit a switch: 1 8' Off, 2 16', 4 4', 8 2' "
                "(add them up). A program change puts back the preset's."]]},
    'spectra': {'title': 'Cone rotor',
     'intro': "A 60's organ's turning speaker, after the Wurlitzer Spectra-Tone: two small speakers back to back on one "
              'rotor inside the console. Their beams sweep past you, so the higher a note the more swells it makes each '
              'turn, with a slight wobble of pitch. Choose it under Speaker for the part: SPECTRA-TONE sends the manual '
              'through the rotor, ST CHORUS through the rotor and the console speakers together.',
     'terms': [['CATHEDRAL', 'The rocker down: the rotor turning slowly, about one turn in two seconds.'],
               ['THEATER',
                'The rocker up: the rotor turning fast, about three turns a second. It climbs there over several seconds '
                'and drops back to Cathedral in about one.'],
               ['CC80',
                "A file or a keyboard sets it too, on the part's channel: below 64 Cathedral, 64 and over Theater."]]},
    'amp': {'title': 'Amp',
     'intro': "What the selected part's voice plays through, as it is modelled: a guitar's, a bass's or a clav's "
              "pickups, its valve amplifier, the speaker it drives, and an organ's rotary speaker. An acoustic voice has "
              'none of these: it is heard as it is.',
     'terms': [['PICKUP',
                "Which of the instrument's pickups it plays on, on a switch drawn after the instrument's own: a 5-way "
                "blade (after the Fender Stratocaster's and the Ibanez's), two volume knobs (after the Fender Jazz "
                "Bass's), two rockers (after the Hohner Clavinet's). Under it, the string with its coils where they sit, "
                'the ones heard lit.'],
               ['VALVE',
                "The amplifier's triode stage and its drive: clean at 0, the edge of breakup at 1, a clip past it. DRIVE "
                'is the drive set; WITH THE WHEEL beside it is what plays, the mod wheel scaling it (up to four times '
                "the patch's own). AS THE PATCH puts the patch's back."],
               ['SPEAKER',
                "The cabinet: the voice's own, or another it can play through. The line under the buttons says what that "
                'speaker is.'],
               ['ROTARY',
                "An organ's rotating speaker, after the Leslie 122: its speed (STOP, SLOW, FAST -- the half-moon, CC80) "
                'and how it is heard (IN THE ROOM, or TWO MICS round it). Shown when the organ plays through one.'],
               ['Kept',
                'The part keeps its valve, speaker and how its rotary speaker is heard through program changes, and in '
                'the session.']]},
    'pickup': {'title': 'Pickup',
     'intro': "The pickups the part's instrument plays on, on the AMP card. A pickup hears the string at the point where "
              'it sits: near the bridge it hears the upper harmonics strongly and the fundamental weakly (bright, thin), '
              'toward the neck the reverse (round, full). Two coils together add their combs -- and where they hear the '
              'string in opposite phase, cancel, which is the in-between positions\' hollow "quack". Choose a position, '
              "part by part; the session keeps it, and a program change puts the part back on its new voice's own.",
     'terms': [['Three single coils',
                'After the Fender Stratocaster: its 5-way blade, numbered as a Strat player numbers it: 1 the bridge '
                'pickup, 2 bridge and middle, 3 the middle, 4 middle and neck, 5 the neck.'],
               ['Two humbuckers',
                'After the Ibanez RG2820: its 5-way blade, numbered as Ibanez numbers it: 1 the neck humbucker, 2 its '
                'two coils in parallel, 3 both humbuckers, 4 the two inside coils, 5 the bridge humbucker. Overdriven '
                'and Distortion Guitar play the bridge; Jazz Guitar the neck.'],
               ['Two-coil bass',
                'After the Fender Jazz Bass. No switch: its two volume knobs, neck and bridge. Tap one to turn it fully '
                'up or off (one always stays up). Both up is the full sound; the bridge alone the growl, the neck alone '
                'the thump.'],
               ['Keyboard, two pickups',
                'After the Hohner Clavinet D6: its two rocker switches, A/B and C/D. A C the centre pickup alone (warm), '
                'B C the bridge pickup (thin), B D both in phase (full), A D both against each other (hollow: the '
                'fundamental cancelled -- the funk sound).'],
               ['Level',
                'A bridge pickup is wound hotter, as a real one is, to make up for the string moving less there; '
                'parallel coils load each other, which lifts their resonance. The levels follow from that, as on the '
                'instrument.'],
               ['CC85',
                "A file or a keyboard chooses it too, on the part's channel, at once (the next notes). A program change "
                "puts it back to the voice's own, so a file sends it after the program change, as it would a volume: "
                "bank select, program change, then CC83 and CC85. 0 the voice's own, 1 neck, 2 the second position "
                '(three single coils: neck and middle; two humbuckers: the neck one in parallel), 3 middle, 4 the fourth '
                '(three single coils: middle and bridge; two humbuckers: the inside coils), 5 bridge, 6 neck and bridge '
                "(both), 7 the clav's both in anti-phase. One the instrument does not have leaves it its own."]]},
    'cabinet': {'title': 'Speaker (cabinet)',
     'intro': "The speaker the part's voice plays through, on the AMP card. Every amplified voice has one of its own: "
              "the guitars and basses their amps' cabinets, the tine electric piano its suitcase, the reed electric "
              "piano the speakers in its lid, the organs a rotary speaker or their console's own speaker. Choose "
              "another, part by part; the session keeps it, and a program change puts the part back on its new voice's "
              'own.',
     'terms': [["PATCH'S OWN · name",
                "The patch's own speaker, named. Tap another to play through it; the line under the buttons says what "
                'that speaker is.'],
               ['DIRECT',
                "No speaker: the amplifier's output straight to the desk, as a direct box takes it. Brighter and harder, "
                'with nothing rounding the top.'],
               ['ROTARY',
                "A tonewheel organ's rotating speaker, after the Leslie 122: its horn and drum turning. Only an organ "
                "offers it. Its speed and how it is heard are on the AMP card's ROTARY."],
               ['SPINET', "A tonewheel organ's own speaker, after a Hammond spinet's: no rotors, a single 12-inch cone."],
               ['Level',
                "A rotary speaker coming or going keeps the organ's level: the rotors' path is quieter than a fixed "
                "speaker's, and that is put back."],
               ['CC83',
                "A file or a keyboard chooses it too, on the part's channel, at once (the next notes). A program change "
                "puts it back to the voice's own, so a file sends it after the program change, as it would a volume: "
                "bank select, program change, then CC83 and CC85. 0 the voice's own (OWN), 1 DIRECT, 2 ROTARY (after the "
                "Leslie 122), 3 SPINET (after a Hammond spinet's speaker), 4 1x12 (a guitar combo), 5 4x12 (closed), 6 "
                "2x12 CLEAN (after the Roland JC-120), 7 BASS 4x10, 8 SUITCASE (a tine piano's), 9 LID PAIR (a reed "
                "piano's lid speakers), 10 CONE ROTOR (after the Wurlitzer Spectra-Tone), 11 ROTOR CHORUS (its chorus, a "
                "60's organ's manuals). One the voice does not offer leaves it its own."]]},
    'piano': {'title': 'Piano',
     'intro': "The selected part's pedals. They show what the keyboard, a file or this screen last sent, and act on the "
              "part's channel.",
     'terms': [['Pedals', 'Soft, sostenuto and sustain, as on a grand piano.'],
               ['Dampers', "Where each key's damper sits on its strings."],
               ['Pedal key', 'A key on the keyboard that works as the sustain pedal.']]},
    'piano:pedals': {'title': 'Pedals',
     'intro': 'Tap a pedal to press it; tap again to let it up.',
     'terms': [['SOFT', 'Una corda: the hammers strike fewer strings, softer and darker.'],
               ['SOSTENUTO',
                'Holds up the dampers of only the keys that are down as it goes down; keys played after it are damped as '
                'usual.'],
               ['SUSTAIN',
                'Drag the fader through its travel. Between up and down the dampers rest lightly on the strings (half '
                'pedal).'],
               ['DOWN / HALF / UP', 'Sets the sustain pedal straight to down, halfway or up.']]},
    'piano:dampers': {'title': 'Dampers',
     'intro': "Each key's damper as the sustain pedal leaves it.",
     'terms': [['Lifted', 'Off the string: it rings on.'],
               ['Resting lightly', 'Half pedal: loud notes are cut back, the quiet sound rings on.'],
               ['On the strings', 'Damped: the note stops when its key comes up.'],
               ['The line below',
                'The pedal values where the dampers leave the strings, by register. The bass dampers are heavier and '
                'leave later. The top keys have no dampers.']]},
    'piano:key': {'title': 'Pedal key',
     'intro': 'For a keyboard with no pedal: a key held down works as the sustain pedal.',
     'terms': [['Held', 'Holding the key lifts the dampers.'],
               ['Pushed into',
                'Pressing harder into the held key (aftertouch) lowers the dampers back onto the strings, for '
                'half-pedalling.'],
               ['REMOVE', 'That key plays as a note again.'],
               ['LEARN A KEY', 'Tap it, then press the key you want. Tap again to stop waiting.'],
               ['Sympathetic strings', "With them on, the first part's undamped strings ring with what is played."]]},
    'drums': {'title': 'Drums',
     'intro': "The selected part's drum kit as pads, grouped by kind, across the whole card: a drum machine's "
              'buttons. The kits, and what each sound is, are on the KITS card.',
     'terms': [['A pad',
                'Strikes its sound, as hard as VEL says: by position, higher up the pad is harder. Several fingers '
                'can play at once. Pads light as the keyboard, a file or the sequencer plays them.'],
               ['The strip (right)',
                'Drag along it to scroll the pads without striking one. A finger drawn up or down the pads scrolls '
                'them too, but the pad it landed on sounds first.'],
               ['VEL', 'How hard a touch plays the pads: as Setup says, or their own way. See Touch.'],
               ['KITS \u25b8', 'The KITS card: choose a kit, see what each sound is, build a user set.'],
               ['The key', "Each pad's key name."]]},
    'kits': {'title': 'Kits',
     'intro': "The drum library: the kits, the keys of the selected part's kit, and what each key is.",
     'terms': [['Kits (left)', 'Tap a kit to put it on the selected part.'],
               ['Keys (middle)', "The kit's keys: note, MIDI number and name. Tap one to hear it and read about it."],
               ['The key (right)', 'What the sound is, and the kit it borrows from when it does.'],
               ['User Set 1 / 2',
                'Kits you build yourself: each key takes its sound from any key of any kit, with its own pitch, '
                'level and pan. Choose a key, then its sound.'],
               ['DRUMS \u25b8', 'Back to the pads.']]},
    'seq': {'title': 'Seq',
     'intro': "A Euclidean sequencer: each lane strikes one drum on HITS of its STEPS, spread as evenly as they "
              "can be. Four hits in sixteen steps is the beat; three in eight is the tresillo; five in eight, seven in "
              "sixteen and many other rhythms from around the world come out the same way. Each lane has its own "
              "length, so lanes of 16, 12 and 7 steps drift against each other and meet again.",
     'terms': [['PLAY / STOP',
                'Runs the lanes on the drum part: the selected part if it is a drum kit, else the first that is. It '
                'keeps running while you use the other cards.'],
               ['TEMPO', "Beats a minute. It is the metronome's tempo too: change either and both follow, and the "
                         "metronome clicks on the sequencer's beats while it runs."],
               ['SWING', "50% is straight. Higher delays every second step, to 66% (a triplet feel) and up to 75%."],
               ['STEPS A BEAT', 'How many steps make a beat: 4 for sixteenths, 3 for triplets, 2 for eighths.'],
               ['DRUM', 'The sound a lane strikes. Tap it to choose one from the kit, or none to rest the lane.'],
               ['STEPS AS STRUCK',
                "The lane's steps: lit where it strikes, the beats' steps a shade lighter, the step playing now framed. "
                'Drag sideways along them to rotate the pattern.'],
               ['STEPS / HITS', "The lane's length (1 to 32) and how many of its steps strike."],
               ['ROTATE', 'Starts the pattern later by this many steps: the same rhythm, from another place in it.'],
               ['VEL', 'How hard the lane strikes, 1 to 127.'],
               ['NUDGE',
                "Moves the lane's notes off its steps, by part of a step: minus is ahead of the beat (pushing), plus "
                'behind it (laid back). The lit steps are drawn where the notes fall.'],
               ['DRIFT',
                'Runs the lane a little faster (plus) or slower (minus) than the tempo, up to 5%, so it slides '
                "against the other lanes, as in Steve Reich's phase pieces: give two lanes the same drum and pattern "
                'and drift one by 0.5%. Set it back to 0 and the lane stays where it has slid; SYNC puts it back on '
                'the beat.'],
               ['ACCENT', 'Every nth hit of the lane 20 harder (/2: every other one). A dash: none.'],
               ['SYNC', 'Puts every lane back on the beat at the next step, wherever drift has taken it.'],
               ['PATTERN / TIMING',
                "On the iPad and phone: which of the lane's numbers show, its pattern's (STEPS, HITS, ROTATE) or its "
                "timing's (NUDGE, DRIFT, ACCENT). VEL shows on both."],
               ['MUTE (M)', 'Silences the lane, keeping its pattern.'],
               ['Kept', 'The lanes, tempo and swing are kept in the session. It starts stopped.'],
               ['SAVE MIDI',
                'Writes the pattern as a MIDI file: BARS bars of BEATS A BAR beats, every lane from the start, with '
                "the tempo, the kit, and a user set's settings. It goes in the Sequences folder, on the FILES card, "
                'to play, render or take into another program. Swing, NUDGE and ACCENT are written as they play; '
                'a drifting lane is written as it drifts.']]},
    'keys': {'title': 'Keys',
     'intro': "A keyboard to touch, playing the selected part: for trying a sound, or showing it, without a keyboard "
              'plugged in.',
     'terms': [['A key', 'Plays while it is held, as hard as VEL says: by position, nearer its front edge is harder. '
                         'Every finger plays its own key, so chords work. A held key is lit brighter the harder it was '
                         'struck.'],
               ['VEL', 'How hard a touch plays the keys: as Setup says, or their own way. See Touch.'],
               ['\u25c0 OCTAVE / OCTAVE \u25b6', 'Moves the keyboard down or up an octave. Its range is shown between them.'],
               ['SUSTAIN', "The part's sustain pedal: lit, what the keys play rings on. Leaving the card lets it go."],
               ['How many keys', 'Four octaves on a computer, three on the iPad, two on the phone.'],
               ['A finger drawn along a held key',
                "Chosen under VEL. GLISSANDO: each key it crosses plays in turn. BEND: drawn sideways it bends the "
                "part's pitch, a key's width a semitone, up to the bend range on the Setup card; the latest finger "
                'bends, and lifting it lets the pitch back. AFTERTOUCH: drawn toward the front edge it presses the key '
                'harder (the channel\'s aftertouch, the deepest finger\'s), for the sounds that answer it.']]},
    'su:touch': {'title': 'Touch',
     'intro': 'How hard a finger plays the Keys card and the Drums pads. People like it different ways, so there is a '
              'choice. Setup sets it for both; either card can keep its own instead, from its VEL. Kept in the session.',
     'terms': [['FIXED', 'Every note plays at one velocity, VELOCITY (1 to 127), wherever it is touched.'],
               ['POSITION', "Where the finger lands: a key's front edge and a pad's top play hardest."],
               ['SOFT END / HARD END', 'The velocities at the two ends. Drag up or down to change them; hold to type one.'],
               ['SOFT / LINEAR / HARD',
                'The curve between them. SOFT keeps most of the touch quiet and saves the loud notes for the hard end; '
                'HARD plays loud sooner; LINEAR is even.'],
               ['REVERSE', 'Swaps the ends: the back of a key, or the foot of a pad, plays hardest.'],
               ['TRY', 'Touch the strip to see the velocity a touch there would play: its foot is the hard end.'],
               ['AS SETUP', "On a card's VEL: the card plays as Setup says. FIXED or POSITION there gives the card its "
                            'own.']]},
    'drums:user': {'title': "A user set's key",
     'intro': 'Where the chosen key gets its sound, and how it plays it.',
     'terms': [['ITS SOUND FROM', 'The sets (left): choose the kit to take the sound from. The keys (right): tap the '
                                  'sound you want. It plays once and the key keeps it.'],
               ['PITCH', 'Up or down from the sound as recorded, in semitones (GS: the play note).'],
               ['LEVEL', "The key's own level, 0 to 127. A dash: the kit's own."],
               ['PAN', 'Left to right; "random" moves each hit somewhere new. A dash: the kit\'s own.'],
               ['MUTE', 'Lit, the key does not play (GS: Rx note on, off).'],
               ['Drag or hold', 'Drag a value up or down; hold it to type one. The key plays when you let go.'],
               ['Kept', 'User sets are kept in the session, as a GS module keeps them.']]},
    'effects': {'title': 'Effects',
     'intro': 'The insertion effect (one effect, for the parts you put on it), and the system effects every part sends '
              'to.',
     'terms': [['Insertion effect', 'Its type and knobs, and its sends.'],
               ['Reverb / Chorus / Delay / EQ',
                'The system effects, on the right. Each part sends to them with its REVERB, CHORUS and DELAY fields.'],
               ['The notes below', 'Touch a type or knob for what that effect is.']]},
    'fx:ins': {'title': 'Insertion effect',
     'intro': 'One effect at a time, used by the parts put on it: a distortion, a rotary speaker, a phaser and so on.',
     'terms': [['THIS PART ON IT', 'Puts the selected part through the effect (lit) or takes it off.'],
               ['On it: channels…', 'Which channels go through it now. If it cannot play live, the reason is shown.'],
               ['The families', 'Groups of types: tap one to see its types.'],
               ['A type', 'Tap to use it. 00 Thru is no effect.'],
               ['The knobs', "The type's settings, in the values its manual prints."]]},
    'fx:sends': {'title': 'Sends from it',
     'intro': "How much of the insertion effect's output also goes on to the system effects.",
     'terms': [['to Reverb / to Chorus / to Delay', '0 to 127.']]},
    'fx:rev': {'title': 'Reverb',
     'intro': 'The room or hall every part sends to with its REVERB field (CC91).',
     'terms': [['Room 1 … Pan Delay', 'The reverb type. Delay and Pan Delay are echoes.'],
               ['Level', 'How loud the reverb is.'],
               ['Time', 'How long it rings.'],
               ['Feedback', 'For the echo types: how many repeats.'],
               ['No GS reverb set',
                'Until a file or this card sets one, the reverb is the room chosen on the Setup card.']]},
    'fx:cho': {'title': 'Chorus',
     'intro': 'The shimmer every part sends to with its CHORUS field (CC93).',
     'terms': [['Chorus 1 … Short Delay FB',
                'The chorus type; Flanger and the short delays are stronger, jet-like or doubling sounds.'],
               ['Pre-LPF', 'Cuts the highs going in, 0 (none) to 7.'],
               ['Level', 'How loud the chorus is.'],
               ['Feedback', 'How much is fed back, for a stronger, ringing sweep.'],
               ['Delay', 'Its delay time.'],
               ['Rate', 'How fast it sweeps.'],
               ['Depth', 'How far it sweeps.']]},
    'fx:dly': {'title': 'Delay',
     'intro': 'The echo every part sends to with its DELAY field (CC94).',
     'terms': [['Delay 1 … Pan Repeat',
                'The delay type: plain echoes, echoes panned left and right, an echo into the reverb.'],
               ['Pre-LPF', 'Cuts the highs going in, 0 (none) to 7.'],
               ['Time', "The centre echo's time."],
               ['Ratio L / Ratio R', "The left and right echoes' times, as a share of the centre's."],
               ['Level C / L / R', "Each echo's level."],
               ['Level', "The delay's overall level."],
               ['Feedback', 'How many repeats.']]},
    'fx:eq': {'title': 'EQ',
     'intro': 'Bass and treble for the whole mix.',
     'terms': [['Low', "The bass control's frequency: 200 or 400 Hz."],
               ['Low gain', 'Bass up or down, ±12 dB.'],
               ['High', "The treble control's frequency: 3 or 6 kHz."],
               ['High gain', 'Treble up or down, ±12 dB.']]},
    'matrix': {'title': 'Matrix',
     'intro': "What each controller moves on the selected part's channel. A row is a controller; a column is what it "
              'moves; the knob is how far, at full travel.',
     'terms': ['The rows (sources)',
               ['Mod wheel / Pitch bend', "The keyboard's wheels."],
               ['Channel aftertouch', 'Pressing into a held key (the whole keyboard).'],
               ['Poly aftertouch', 'Pressing into each key on its own, where the keyboard sends it.'],
               ['CC1 / CC2', 'Any two knobs or pedals you choose. Tap "is CCn" to type the controller number.'],
               ['LEARN', 'Tap, then move the knob or pedal you want for CC1 or CC2.'],
               'The columns (destinations)',
               ['Pitch / Cutoff / Amplitude', 'Bend the pitch, open the filter, change the level directly.'],
               ['LFO 1 / LFO 2: Rate, Pitch, Filter, Amp',
                'The two vibrato LFOs: their speed, and how much they move pitch (vibrato), filter (wah) and level '
                '(tremolo).'],
               'The knobs',
               ['Lit', 'Changed from the power-on setting. Double-tap a knob to put it back.'],
               ['A lit row name', 'That controller moves something.'],
               ["Set by a file's GM2 messages", 'Settings a file made with GM2 messages: shown, not changed here.']]},
    'tuning': {'title': 'Tuning',
     'intro': "The tuning every part plays in. Tap one and every part's sounds are built again in it (the display shows "
              'BUILDING); notes already sounding keep the old tuning.',
     'terms': [['Concert pitch, A=440',
                'Modern pitch. gm2 is the default: equal temperament at A=440, and a file can retune it with its own '
                'tuning messages.'],
               ['Baroque pitch, A=415', 'Half a step lower, with the old temperaments.'],
               ['Pure octaves: pipes', 'Tunings with unstretched octaves, for the pipe organ.'],
               ['Indian, every part', 'Every part in a raga tuning.'],
               ['Other systems', 'The rest.'],
               ['Lit / blinking', 'Lit is playing now; blinking is being built.']]},
    'tn:shape': {'title': "The tuning's shape",
     'intro': 'How the chosen tuning differs from equal temperament.',
     'terms': [['C4 to B4',
                'Each note of the middle octave, in cents (hundredths of a semitone) above or below equal temperament.'],
               ['A0 to C8',
                'How far each octave is stretched wider than a pure 2:1, across the keyboard, as a piano tuner '
                'stretches.'],
               ['A4 = n Hz', 'The pitch of the A above middle C.']]},
    'tn:east': {'title': 'Eastern tuning',
     'intro': "The tuning the Indian instruments' parts play (sitar, shehnai and the rest), while the other parts keep "
              'the tuning above.',
     'terms': [['Off', 'The Indian instruments play the tuning above.'],
               ['A system', 'The raga tuning system to use.'],
               ['No raga / a raga', "The raga, which sets each note's exact tuning."],
               ['Sa', 'The key of Sa, the tonic.']]},
    'control': {'title': 'Control',
     'intro': "Controls on the screen for what the keyboard lacks, and routes that change what the keyboard's own "
              'controls do.',
     'terms': [['On-screen controls', 'Pedals, wheels and switches to play from the screen.'],
               ['Routes', "The keyboard's controls rewritten before the engine hears them."]]},
    'ct:strip': {'title': 'On-screen controls',
     'intro': 'Each sends straight to the engine on its channel.',
     'terms': [['A fader', 'A continuous control. Pitch bend and aftertouch spring back when you let go.'],
               ['A switch', 'Tap down, tap up (a sustain pedal, for one).'],
               ['A selector', "The tonewheel organ's vibrato and chorus: off, V1–V3, C1–C3."],
               ['every channel / channel n', 'Where it sends.'],
               ['REMOVE', 'Takes the control off the screen.'],
               ['+ ADD A CONTROL',
                "Choose a control to add, on the selected part's channel. A lit choice is already there."]]},
    'ct:routes': {'title': 'Routes',
     'intro': 'Each rewrites a control from the keyboard before the engine hears it, such as a key as the sustain pedal, '
              'or one knob as another.',
     'terms': [["A route's line", 'What it takes and what it becomes.'],
               ['REMOVE', 'Takes the route away: that control reaches the engine as it is.']]},
    'ct:new': {'title': 'A new route',
     'intro': 'Choose where it comes from, what it becomes and how, then ADD THE ROUTE.',
     'terms': ['FROM',
               ['A KEY (LEARN)', 'Tap, then press the key on the keyboard.'],
               ['A CONTROLLER (LEARN)', 'Tap, then move the knob, slider or pedal.'],
               ['WHEEL UP / DOWN / EITHER', 'The pitch wheel pushed up, pulled down, or either way.'],
               ['AFTERTOUCH', 'Pressing into held keys.'],
               'TO',
               ['The controls', 'What it becomes.'],
               'HOW',
               ['KEEP THE ORIGINAL TOO', 'The original still does its own job as well.'],
               ['LATCH (PRESS ON, PRESS OFF)', 'For a switch: one press turns it on, the next off.'],
               ['PUSH INTO IT TO DAMP', 'For a key as the sustain: pressing into it lowers the dampers.'],
               ['EVERY CHANNEL / CHANNEL n', "Every part, or only the selected part's channel."],
               ['ADD THE ROUTE', 'Adds it. The line beside it says what it will do.']]},
    'scenes': {'title': 'Scenes',
     'intro': 'Save the setup and bring it back. Presets and scenes are kept beside the session.',
     'terms': [['Presets', 'The whole setup.'],
               ['Scenes', "Only each channel's control settings."],
               ['Metronome, GS reset', 'On the Control card.']]},
    'sc:presets': {'title': 'Presets',
     'intro': 'The whole setup: the parts and their patches, the routes, the tuning and the effects.',
     'terms': [['A preset', 'Tap to choose it; its buttons come up. Tap again to put them away.'],
               ['LOAD', 'Brings that setup back.'],
               ['SAVE OVER', 'Saves the setup now in its place.'],
               ['DELETE', 'Takes it away.'],
               ['AS MIDI',
                'Writes what a MIDI file can say of it as a one-bar MIDI file, setups/NAME.mid in the music folder (the '
                'Files card): a GS Reset, the scene, then each part on a channel -- its bank, program, speaker (CC83), '
                "pickup (CC85), an organ's drawn stops, a synth's whole panel (CC86's Messenger mode, then the "
                "Messenger's own CCs), level and pan. Paste it at the top of a song so the song plays on this setup. A "
                "part's key range, transpose, tuner and knobs have no MIDI word: the preset keeps them, and the file "
                "names each part's keys in a text event."],
               ['SAVE THIS SETUP AS…', "Name a new preset on the screen's keys and save the setup now."]]},
    'sc:scenes': {'title': 'Scenes',
     'intro': "Each channel's control settings (levels, pans, sends, pedals), without changing the sounds.",
     'terms': [['A scene', 'Tap to choose it; its buttons come up.'],
               ['RECALL', 'Sets the controls as the scene has them.'],
               ['SAVE OVER', 'Saves the controls now in its place.'],
               ['DELETE', 'Takes it away.'],
               ['SAVE THE CONTROLS AS…', 'Name a new scene and save the controls now.']]},
    'sc:metro': {'title': 'Metronome',
     'intro': 'A click from a recorded metronome.',
     'terms': [['ON', 'Starts and stops it.'],
               ['Tempo', "Beats a minute, 30 to 300. The sequencer's tempo too (the SEQ card): change either and both "
                         'follow.'],
               ['Bell every', 'A bell on the first of every n beats, or none.'],
               ['Level', 'How loud, in dB.']]},
    'sc:gs': {'title': 'GS reset',
     'intro': "As a sequencer's GS Reset.",
     'terms': [['GS RESET',
                'Tap twice within 3 seconds: every part goes back to program 000, and the controllers, effects and '
                'receive settings to power-on.']]},
    'setup': {'title': 'Setup',
     'intro': 'The rig: inputs, the sound settings for every part, the room. The line at the top is the sample rate and '
              'the block size, the time the engine has for each block of sound.',
     'terms': [['Quitting',
                'There is no quit button. On a computer, close the window or press Ctrl+Q (Cmd+Q on a Mac): the engine '
                'saves the session and stops. On the iPhone and iPad, leave the app as any other.']]},
    'su:midi': {'title': 'MIDI in',
     'intro': 'Every MIDI device plugged in. Several can be on at once; their notes are merged. The choice is kept in '
              'the session.',
     'terms': [['A device', 'Tap to turn it on or off.'],
               ['reading', 'On and being read.'],
               ['wanted, not open', 'On, but it could not be opened (unplugged, or another program has it).'],
               ['off', 'Not read.']]},
    'su:module': {'title': 'Play as a module',
     'intro': 'For a sequencer or a DAW playing whole songs into Clavitone over MIDI, as into a Sound Canvas or an '
              'MT-32: each of the 16 channels its own part, and the input read as that module reads it. Your own parts '
              'are set aside meanwhile, and the session keeps them; OFF puts them back exactly.',
     'terms': [['OFF: MY PARTS', 'The input plays your own parts, as always.'],
               ['AUTO',
                'Starts as GS and follows what the input sends: a GS Reset plays it as GS, GM System On as GM, MT-32 '
                'messages as an MT-32. The button shows what it is playing as.'],
               ['GM', 'A General MIDI module: bank selects ignored.'],
               ['GS: OURS … GS: SC-8850', 'A Sound Canvas, bank numbers in that map.'],
               ['GS: INIT CM-64',
                "A Sound Canvas after its Init CM-64: the MT-32's sounds on parts 1 to 9, its drums on 10, the CM-32P's "
                "on 11 to 16, pans mirrored; the input's MT-32 messages ignored."],
               ['MT-32',
                "A real MT-32: parts on channels 2 to 9 and drums on 10, the input's MT-32 messages followed (which "
                'sound each program is, custom sounds by name, levels, pans, reverb). What it did with them is listed '
                'below the buttons.'],
               ['CM-64', "The same, with the CM-32P's parts on 11 to 16."],
               ['MT-32 velocity', "The Files card's MT-32 VELOCITY switch applies here too."]]},
    'su:msgr': {'title': 'The Messenger',
     'intro': 'The Moog Messenger, when one is plugged in.',
     'terms': [['On …', 'Which MIDI input it is on.'],
               ['READ ITS KNOBS',
                "On: turning the Messenger's own knobs turns the same knobs on the Synth card. On by itself when a "
                'Messenger is the MIDI input -- by its name, or, behind a USB MIDI interface, by its answer when asked '
                'who it is; switched off here, it stays off until the next start. Off, its knobs are read as General '
                "MIDI's: its SUB WAVE knob (CC71) turns a sound controller, not the sub wave."],
               ['FIRMWARE BEFORE 1.0.7',
                'Turn on if its firmware is older than 1.0.7, which sent the cutoff knob differently.']]},
    'su:sound': {'title': 'Sound',
     'intro': 'Settings every part plays through.',
     'terms': [['Master', 'The overall output level.'],
               ['Headroom',
                'How much every note is turned down before the mix, so that big chords stay under the limiter.'],
               ['Limiter knee', 'Where the output limiter starts to hold the level back: lower is gentler and earlier.'],
               ['Bend range', 'How far the pitch wheel bends, in semitones.'],
               ['Mod depth', "How deep the mod wheel's vibrato is at full wheel, in cents."],
               ['Mod rate', 'How much faster the vibrato goes at full wheel.'],
               ['Aftertouch', 'How much louder (and brighter) a held note gets as you press into it, at full pressure.'],
               ['Stand-in',
                'A note whose sound is not built yet waits while it is built, usually a few milliseconds. Past this time '
                "it plays the nearest built key's sound, tuned to its own pitch, and the display shows STAND-IN in red. "
                'OFF: it always waits for its own.'],
               ['THE GPU', 'On: the graphics chip helps render the sound, for more voices.'],
               ["THE ROOM'S TAIL", "On: the room's reverb tail."],
               ['The room', 'The room the instruments play in, when a file or the Effects card has not set a GS reverb.'],
               ['Program changes read as',
                "Which Sound Canvas a file's program and bank numbers are read for: ours, or the SC-55, SC-88, SC-88Pro "
                "or SC-8850's own map."]]},
    'su:rubato': {'title': 'Borrowed time',
     'intro': 'With rubato on (the default), when a block of sound is late, the sound already playing is held on and the '
              'time is borrowed instead of dropping out. It is given back where no note falls.',
     'terms': [['BORROW TIME WHEN LATE',
                'On: rubato, as above. Off: a late block drops out as a click. Kept in the session.'],
               ['Callbacks that waited', 'How many times time was borrowed.'],
               ['Time held, ever', 'All the time borrowed since the start.'],
               ['Owed now', 'Time borrowed and not yet given back.'],
               ['Time returned', 'Time given back, and in how many cuts.'],
               ['Held by the partials ringing on', 'Time covered by holding the sound that was playing.']]},
    'files': {'title': 'Files',
     'intro': 'A MIDI file on this machine, played live through the engine or rendered offline to a WAV.',
     'terms': [['Folders', 'Find the file.'],
               ['The file', 'What it is, the mode to read it in, and playing or rendering it.']]},
    'fl:browse': {'title': 'Folders',
     'intro': 'The folders and MIDI files (.mid, .midi, .kar) on this machine. It opens where you were last.',
     'terms': [['▲ UP', 'The folder above.'],
               ['MUSIC', 'Your Music folder.'],
               ['▸ A folder', 'Opens it.'],
               ['A file', 'Chooses it: what it is shows on the right.']]},
    'fl:file': {'title': 'The file',
     'intro': 'Its length, the channels it plays, how many program changes it makes, and the mode it asks for.',
     'terms': [['The file check',
                'Problems in the file that would sound like a wrong instrument: two programs at the start where only the '
                'last counts, two instruments on one channel, a pitched part on the drum channel, two tracks fighting '
                "over one channel's volume, a volume so low it is silence, notes out of the instrument's range. Tap to "
                'open the list.'],
               ['Worth trying', 'A mode that suits the file better than the one chosen, and why.']]},
    'fl:mode': {'title': 'Mode',
     'intro': 'Which module the file was written for. It decides what its program and bank numbers mean, so the same '
              'file can sound quite different.',
     'terms': [['AUTO',
                'What the file says: a GS Reset reads it as GS, GM System On as GM, MT-32 messages as MT-32. A file that '
                "says nothing plays as GS in the Setup card's standard. The button shows what it found."],
               ['GM', 'A General MIDI module: bank selects are ignored, every program plays its plain sound.'],
               ['GS: OURS', "Sound Canvas files, bank numbers in our own library's numbering."],
               ['GS: SC-55 … SC-8850',
                'Sound Canvas files, bank numbers as that module laid them out (a file that names its own map with CC32 '
                'keeps it).'],
               ['GS: INIT CM-64',
                "Files for the MT-32 or CM-64, as a Sound Canvas plays them after its Init CM-64 (Roland's name for its "
                "MT-32 setting): parts 1 to 9 the MT-32's sounds, 10 its drums, 11 to 16 the CM-32P's, every pan "
                "mirrored. The file's own MT-32 messages are ignored, as a Sound Canvas ignores them, and channel 1 "
                'plays a piano.'],
               ['MT-32',
                'As a real MT-32 plays the file: its parts on channels 2 to 9 and the drums on 10 (channel 1 and 11 to '
                "16 silent unless the file moves them), and the file's MT-32 messages followed: which sound each program "
                "number selects, key shift, fine tune, bend range, each part's level and pan, the drums' levels and "
                'pans, master volume and tune, the reverb. A custom sound the file builds plays as our voice nearest its '
                'name. What it cannot follow is listed under the modes. AUTO chooses this for a file that sends MT-32 '
                'messages.'],
               ['CM-64',
                "As a real CM-64 plays it: the same as the MT-32, with the CM-64's CM-32P parts on channels 11 to 16 and "
                'its sound effects on drum keys 76 to 108.'],
               ['ORCHESTRA BY NAMES',
                'For an orchestral file of the MT-32 years that names its parts on its tracks (Flutes, Horns, Timpani…): '
                'each part plays the instrument its name says, whatever program number it sends, and parts that shared a '
                'channel get one each, or share one only where they never play the same note at once. Suggested above '
                'the modes when a file looks like one. The parts it found are listed under the modes.']]},
    'fl:vel': {'title': 'MT-32 velocity',
     'intro': 'An MT-32 spans about 30 dB from its softest note to its loudest; our instruments span far more. Files '
              'written for one come out far too dynamic unless their velocities are compressed to match. The switch '
              "shows only in the MT-32's modes (AUTO's when it finds an MT-32 file); a GS or GM file always plays its "
              'velocities as written.',
     'terms': [['ON',
                'In GS: INIT CM-64, MT-32, CM-64 and ORCHESTRA BY NAMES, each velocity v plays as 3/4 v + 32 (set as '
                "each part's velocity sense, so the Parts card shows it). Leave it on for MT-32 files."],
               ['OFF', "The file's velocities as written."]]},
    'fl:play': {'title': 'Play live',
     'intro': 'The file plays through the engine in real time, as a sequencer drives a Sound Canvas.',
     'terms': [['PLAY LIVE',
                'Takes the parts over: one part per channel (16), every key, channel 10 the drums. Then it builds the '
                'sounds the file asks for, so its notes do not fall on a build, sends a reset, and plays.'],
               ['STOP',
                'Stops it: the notes let go, every pedal up. The parts stay as the file left them; load a preset (Scenes '
                'card) to have yours back.'],
               ['The bar', 'How far through the file it is.']]},
    'fl:render': {'title': 'Render offline',
     'intro': 'The file rendered to a WAV in ~/Music/renders, named after it, which then plays here.',
     'terms': [['RENDER AS HEARD',
                'The live engine renders it, on the CPU: your tuning, room and effects, the parts as PLAY LIVE sets '
                'them. Saved as NAME.heard.wav.'],
               ['RENDER BEST QUALITY',
                "The file renderer, streamed on the GPU, then the room's tail: the full renderer, not the live engine's "
                'shortcuts. Saved as NAME.best.wav. It checks first: what it cannot render yet, it says, and offers the '
                'as-heard render instead.'],
               ['STOP THE RENDER', 'Stops it.'],
               ['While playing',
                'A render shares the processors with the engine you are playing, so it can cause dropouts. One that '
                'would need more memory than is free beside the engine is stopped rather than slowing the machine '
                'down.']]},
    'how:file': {'title': 'Play or render a MIDI file',
     'intro': 'Hear a file through the engine, or make a WAV of it.',
     'steps': ['Open the Files card and find the file in the folders on the left.',
               'Tap it. The right side says how long it is and which mode it asks for.',
               'Leave the mode on AUTO, or choose the module it was written for.',
               "PLAY LIVE plays it now (the parts become the file's), or RENDER AS HEARD / RENDER BEST QUALITY make a "
               'WAV.'],
     'see': ['fl:mode', 'fl:play', 'fl:render']},
    'how:layer': {'title': 'Play two sounds at once',
     'intro': 'Layer a second part on the same keys, such as strings under a piano.',
     'steps': ['Open the Parts card and select the part to layer on.',
               'Tap LAYER. A copy of the part is added with the same keys and channel.',
               'Select the new part: tap its name in its strip, or PART ▶.',
               'Open the Library and tap the second sound.',
               "Balance the two with each strip's level fader."],
     'see': ['parts', 'library', 'how:split']},
    'how:split': {'title': 'Split the keyboard',
     'intro': 'A different sound under each hand, such as a bass on the left and a piano on the right.',
     'steps': ['Open the Parts card and select the part to split.',
               'Tap SPLIT. Its keys are cut at the middle; the upper half becomes a new part.',
               'Select the new part and choose its sound in the Library.',
               "To move the split point, drag the ends of the two parts' bars under the keyboard."],
     'see': ['parts', 'how:layer']},
    'how:keyboard': {'title': 'Play from a keyboard',
     'intro': 'Choose which MIDI devices are read.',
     'steps': ['Plug the keyboard in.',
               'Open the Setup card. It is listed under MIDI in.',
               'Tap it until it says "reading". Several can be on at once.'],
     'see': ['su:midi']},
    'how:pedal': {'title': 'Use a key as the sustain pedal',
     'intro': 'For a keyboard with no pedal: one key held down lifts the dampers.',
     'steps': ['Open the Piano card.',
               'Tap LEARN A KEY, then press the key to use (a low one you will not play).',
               'Hold the key: the dampers lift and notes ring on. Press into it harder to bring the dampers down again '
               '(half pedal).',
               'To play it as a note again, tap REMOVE beside it.'],
     'see': ['piano:key', 'piano:pedals', 'ct:new']},
    'how:organ': {'title': 'Register the organ',
     'intro': "Choose an organ's stops or drawbars.",
     'steps': ["Put an organ on a part: the Library's Organ family, or the organs the Stops card offers when the part is "
               'not one.',
               'Open the Stops card and tap stops to draw them. Start with one and add.',
               'On a tonewheel organ, the Drive knob below sets the overdrive, and the mod wheel is the swell pedal.'],
     'see': ['stops', 'drive']},
    'how:save': {'title': 'Save a setup and bring it back',
     'intro': 'A preset keeps the whole setup: the parts, their sounds, the routes, the tuning and the effects.',
     'steps': ['Open the Scenes card.',
               "Tap SAVE THIS SETUP AS…, type a name on the screen's keys, and tap Save.",
               'Later, tap the preset in the list and tap LOAD.',
               'To keep only the levels, pans, sends and pedals, use SAVE THE CONTROLS AS… (a scene) instead.'],
     'see': ['sc:presets', 'sc:scenes']},
    'how:tuning': {'title': 'Change the tuning',
     'intro': 'Every part plays in the chosen tuning.',
     'steps': ['Open the Tuning card.',
               'Tap a tuning. The display shows BUILDING while the sounds are made again in it.',
               'Play when BUILDING has gone. Notes already sounding keep the old tuning.'],
     'see': ['tuning', 'tn:shape', 'tn:east']},
    'how:stuck': {'title': 'A note will not stop',
     'intro': 'A note can hang if its key-up was lost, for example when a cable is pulled mid-note.',
     'steps': ['Tap PANIC on the front panel. Every sounding note is let go, as if its key were lifted.',
               "If a sustain is stuck down instead, check the Piano card's pedals: tap UP."],
     'see': ['panel', 'piano:pedals']},
    'how:breakup': {'title': 'The sound breaks up or clicks',
     'intro': 'The engine has a fixed time for each block of sound; when a block is late, the sound drops out.',
     'steps': ['Watch CPU on the display. Near 100%, the engine is out of time.',
               'UNDERRUNS counts the dropouts.',
               'Turn THE GPU on (Setup card) to let the graphics chip help.',
               'Fewer parts, or fewer notes held under the sustain pedal, take less time.',
               'Started with --rubato, a late block borrows time instead of dropping out (Setup card, Borrowed time).'],
     'see': ['display', 'su:sound', 'su:rubato']},
    'how:quit': {'title': 'Quit',
     'intro': 'The session is saved as you go, and once more as the engine stops.',
     'steps': ['On a computer: close the window, or press Ctrl+Q (Cmd+Q on a Mac). Full screen, Ctrl+Q is the way '
               'out. Started from a terminal, Ctrl-C there stops it too.',
               'On the iPhone and iPad: leave the app as you leave any other. There is no quit button; the session '
               'is already saved.'],
     'see': ['setup']},
    'credits': {'title': 'Credits',
     'intro': 'No recordings are included in Clavitone. Its instruments are models, and many of them were fitted to '
              'recordings that musicians, sound recordists, libraries and researchers shared. These are those sources, '
              'by kind of instrument, each with its licence and the voices it shaped. Our thanks to all of them; the CC '
              'BY and CC BY-SA licences ask that they be named, and the CC0 and public domain sources are named with '
              'gratitude. Last come the references: the books, papers, standards, patents and service documents the '
              'models were built from, each with what it shaped. All product names, trademarks and registered trademarks '
              'are the property of their respective owners, who are in no way associated or affiliated with Clavitone. '
              'They are used solely to identify the instruments whose sounds were studied in building our models, and '
              'the named sounds of the MIDI standards a file asks for.',
     'terms': []},
}

HELP_TOC = [['Start here', ['basics']],
 ['How to…',
  ['how:keyboard',
   'how:file',
   'how:layer',
   'how:split',
   'how:pedal',
   'how:organ',
   'how:save',
   'how:tuning',
   'how:stuck',
   'how:breakup',
   'how:quit']],
 ['Front panel', ['display', 'panel']],
 ['Parts', ['parts']],
 ['Scenes', ['scenes', 'sc:presets', 'sc:scenes']],
 ['Library', ['library']],
 ['Synth',
  ['synth',
   'synth:LFO 1',
   'synth:Left hand',
   'synth:Oscillators',
   'synth:Mixer',
   'synth:Filter',
   'synth:Envelopes',
   'synth:Delay']],
 ['Stops', ['stops', 'drive', 'rotary']],
 ['Amp', ['amp', 'pickup', 'drive', 'cabinet', 'rotary', 'spectra', 'couplers']],
 ['Piano', ['piano', 'piano:pedals', 'piano:dampers', 'piano:key']],
 ['Drums', ['drums']],
 ['Kits', ['kits', 'drums:user']],
 ['Seq', ['seq']],
 ['Keys', ['keys']],
 ['Effects', ['effects', 'fx:ins', 'fx:sends', 'fx:rev', 'fx:cho', 'fx:dly', 'fx:eq']],
 ['Matrix', ['matrix']],
 ['Tuning', ['tuning', 'tn:shape', 'tn:east']],
 ['Control', ['control', 'ct:strip', 'ct:routes', 'ct:new', 'sc:metro', 'sc:gs']],
 ['Files', ['files', 'fl:browse', 'fl:file', 'fl:mode', 'fl:vel', 'fl:play', 'fl:render']],
 ['Setup', ['setup', 'su:midi', 'su:module', 'su:msgr', 'su:touch', 'su:sound', 'su:rubato']],
 ['About', ['credits']]]

# THE FILES CARD's AUDIO PLAYER (2026-11-26)
HELP['fl:audio'] = {
    'title': 'Player',
    'intro': 'An audio file -- MP3, WAV or FLAC, your renders among them -- chosen on the left plays here, '
             'beside what you play, through the same output.',
    'terms': [
        ['PLAY / PAUSE', 'Plays the file from where it is, or holds it there.'],
        ['STOP', 'Stops it and goes back to the start.'],
        ['The bar', 'Where it is in the file. Drag along it and let go to play from there.'],
        ['LEVEL', "The file's level beside the keyboard's, -30 to +6 dB; 0 dB as the file is."],
        ['PLAY IT', 'Under a finished render: chooses that render here, ready to play.'],
    ],
}
for _g in HELP_TOC:
    if _g[0] == 'Files' and 'fl:audio' not in _g[1]:
        _g[1].insert(_g[1].index('fl:render') + 1 if 'fl:render' in _g[1] else len(_g[1]), 'fl:audio')
