  wrote /home/ben/repos/tuning/coverage.md
  0:0  1:45  2:36  3:18  4:29
examples/gm_coverage.py`, which reads the class column out of `patch_map`
so it cannot drift; the ratings live in that script and can be argued with.

| | meaning |
|---|---|
| **0** | nothing |
| **1** | general class |
| **2** | specific, theory |
| **3** | specific, theory + ear |
| **4** | specific, reference audio |

4 means the voice was fitted against a RECORDING of the instrument, or
against a family law measured on its close relatives. Published measurements
that are not audio -- the Rhodes' high-speed-camera papers -- are better than
theory but cannot contradict the model the way a recording can, so those
voices sit at 2 and say so.

## Where it stands

| rating | patches | share |
|---|---|---|
| 0 nothing | 0 | 0% |
| 1 general class | 45 | 35% |
| 2 specific, theory | 36 | 28% |
| 3 specific, theory + ear | 18 | 14% |
| 4 specific, reference audio | 29 | 23% |

**5 patches are played by a voice of the wrong physical kind** (marked CATEGORY ERROR below): 118 Synth Drum, 119 Reverse Cymbal, 123 Bird Tweet, 124 Telephone Ring, 125 Helicopter.

## Channel 10: the percussion note map

51 notes, 35 to 87. Iowa's percussion pages carry cymbals, crotales and
hand percussion and **no drum kit at all** -- no snare, no bass drum, no
toms, which is 9630 of that collection's 12781 percussion notes. This table
splits almost exactly along that line.

| rating | notes | share |
|---|---|---|
| 1 general class | 10 | 20% |
| 2 specific, theory | 17 | 33% |
| 3 specific, theory + ear | 5 | 10% |
| 4 specific, reference audio | 19 | 37% |

| # | note | class | | notes |
|---|---|---|---|---|
| 35 | Acoustic Bass Drum | `KickDrum` | **3** | no reference -- Iowa has no drum kit. Analytic membrane, pitch tuned by ear |
| 36 | Bass Drum 1 | `KickDrum` | **3** | as 35, tuned higher |
| 37 | Side Stick | `SideStick` | **2** | its own class, theory |
| 38 | Acoustic Snare | `SnareDrum` | **3** | NO REFERENCE, and it says so. Analytic Bessel modes plus the snare wires; ear |
| 39 | Hand Clap | `HandClap` | **2** | its own class, theory |
| 40 | Electric Snare | `SnareDrum` | **1** | the acoustic snare at a different pitch; an electric snare is a different instrument |
| 41 | Low Floor Tom | `FloorTom` | **2** | floor tom, analytic membrane |
| 42 | Closed Hi-Hat | `ClosedHiHat` | **4** | Iowa hi-hat, five takes |
| 43 | High Floor Tom | `FloorTom` | **2** | as 41, higher |
| 44 | Pedal Hi-Hat | `PedalHiHat` | **4** | Iowa hi-hat, foot-close take |
| 45 | Low Tom | `TomTom` | **2** | tom, analytic membrane |
| 46 | Open Hi-Hat | `OpenHiHat` | **4** | Iowa hi-hat, open |
| 47 | Low-Mid Tom | `TomTom` | **2** | as 45, higher |
| 48 | Hi-Mid Tom | `HighTom` | **2** | high tom, analytic membrane |
| 49 | Crash Cymbal 1 | `CrashCymbal1` | **4** | Iowa 17" suspended crash, stick on the bow |
| 50 | High Tom | `HighTom` | **2** | as 48, higher |
| 51 | Ride Cymbal 1 | `RideCymbal` | **4** | Iowa 21" ride, bow |
| 52 | Chinese Cymbal | `ChineseCymbal` | **4** | Iowa chinese, 16/19/20" |
| 53 | Ride Bell | `RideBell` | **4** | Iowa ride bell -- the ping is mode 8.1, not the fundamental |
| 54 | Tambourine | `NoiseDrum` | **2** | generic noise body, but its own rattle: 14 jingles. Iowa HAS tambourines; they were not taken |
| 55 | Splash Cymbal | `SplashCymbal` | **4** | Iowa splash |
| 56 | Cowbell | `Cowbell` | **2** | its own class, theory |
| 57 | Crash Cymbal 2 | `CrashCymbal2` | **4** | Iowa 20" and 13" suspended crash |
| 58 | Vibraslap | `NoiseDrum` | **2** | generic noise body with its own rattle |
| 59 | Ride Cymbal 2 | `CrashRide` | **4** | GM wants two rides and Iowa has one; this is that measurement on a larger plate |
| 60 | Hi Bongo | `MembraneDrum` | **1** | one MembraneDrum serves eleven notes, 60-66 and 78-79 and 86-87, differing only in pitch |
| 61 | Low Bongo | `MembraneDrum` | **1** | as 60 |
| 62 | Mute Hi Conga | `MembraneDrum` | **1** | as 60 |
| 63 | Open Hi Conga | `MembraneDrum` | **1** | as 60 |
| 64 | Low Conga | `MembraneDrum` | **1** | as 60 |
| 65 | High Timbale | `MembraneDrum` | **1** | as 60 |
| 66 | Low Timbale | `MembraneDrum` | **1** | as 60 |
| 67 | High Agogo | `Agogo` | **2** | its own class, theory |
| 68 | Low Agogo | `Agogo` | **2** | as 67, lower |
| 69 | Cabasa | `Cabasa` | **2** | its own class -- a shaken rattle, theory |
| 70 | Maracas | `Rattle` | **2** | its own class -- a shaken rattle, theory |
| 71 | Short Whistle | `Whistle` | **3** | NO REFERENCE, and it says so. Ben on the first version: the whistles were noise driven |
| 72 | Long Whistle | `Whistle` | **3** | as 71, longer |
| 73 | Short Guiro | `Guiro` | **4** | Iowa guiro, both directions -- four rounds of measuring the right thing in the wrong window |
| 74 | Long Guiro | `Guiro` | **4** | as 73, the long scrape |
| 75 | Claves | `Claves` | **4** | Iowa claves, three pairs |
| 76 | Hi Wood Block | `WoodBlockHi` | **4** | Iowa woodblocks, four sizes |
| 77 | Low Wood Block | `WoodBlockLo` | **4** | as 76, the low block |
| 78 | Mute Cuica | `MuteCuica` | **2** | its own FRICTION voice: sawtooth drive, axisymmetric modes only, mode-locked, glides up into pitch |
| 79 | Open Cuica | `Cuica` | **2** | as 78, lower and gliding the other way. No reference -- Iowa has no friction drum |
| 80 | Mute Triangle | `Triangle` | **4** | Iowa triangles, 6" and 8" |
| 81 | Open Triangle | `Triangle` | **4** | as 80, undamped |
| 84 | Belltree | `Crotale` | **4** | the measured crotales, cascaded -- 22 of them over 30 units |
| 85 | Castanets | `Castanets` | **4** | Iowa castanets |
| 86 | Mute Surdo | `MembraneDrum` | **1** | MembraneDrum again; a surdo is a different drum from a bongo |
| 87 | Open Surdo | `MembraneDrum` | **1** | as 86 |

## 0-7 Piano

| # | patch | class | | notes |
|---|---|---|---|---|
| 0 | Acoustic Grand Piano | `GrandPiano` | **4** | Iowa samples; Steinway B inharmonicity fit, soundboard and stretch measured |
| 1 | Bright Acoustic Piano | `BrightPiano` | **2** | the grand voiced HARD: shorter hammer contact, felt that spreads half as much. Tells most at pp |
| 2 | Electric Grand Piano | `ElectricGrand` | **2** | a CP-70: short strings so 12x the bass stretch, no soundboard, a piezo on the bridge. Derived, no reference |
| 3 | Honky-tonk Piano | `HonkyTonk` | **2** | the grand with the tuner's hand off: the unison range widened from under 2 cents to 8-20, CC1 scales it |
| 4 | Electric Piano 1 | `Rhodes` | **2** | Rhodes. Built on two papers' high-speed-camera measurements, but NO audio fitted |
| 5 | Electric Piano 2 | `Wurlitzer` | **2** | Wurlitzer. Same machinery, 1/d pickup; no audio fitted |
| 6 | Harpsichord | `Harpsichord` | **4** | VCSL recordings |
| 7 | Clavinet | `Clavinet` | **2** | its own voice: struck at the anvil, magnetic pickups whose fraction climbs with pitch. No reference |

## 8-15 Chromatic Percussion

| # | patch | class | | notes |
|---|---|---|---|---|
| 8 | Celesta | `Celesta` | **2** | struck steel plate, felt hammer |
| 9 | Glockenspiel | `Glockenspiel` | **4** | Iowa orchestra bells |
| 10 | Music Box | `MusicBox` | **2** | plucked steel comb tooth. Its docstring claims a cantilever; its numbers are a free-free bar |
| 11 | Vibraphone | `Vibraphone` | **4** | Iowa vibraphone. The motor tremolo that gives it its name is NOT modelled |
| 12 | Marimba | `Marimba` | **4** | Iowa marimba |
| 13 | Xylophone | `Xylophone` | **4** | Iowa xylophone |
| 14 | Tubular Bells | `TubularBell` | **2** | tubes at 2:3:4:5 |
| 15 | Dulcimer | `HammeredDulcimer` | **2** | struck steel courses; the stiffness is estimated |

## 16-23 Organ

| # | patch | class | | notes |
|---|---|---|---|---|
| 16 | Drawbar Organ | `DrawbarOrgan` | **3** | tonewheel + Leslie, worked over extensively by ear |
| 17 | Percussive Organ | `PercussiveOrgan` | **3** | tonewheel, percussive tap |
| 18 | Rock Organ | `RockOrgan` | **3** | tonewheel, overdriven |
| 19 | Church Organ | `FlueOrgan` | **3** | flue pipes; registration built on Geer and judged by ear |
| 20 | Reed Organ | `ReedOrganFree` | **2** | FreeReedProperties: a tongue through a slot, no resonator -- not the pipe organ reed RANK all four used to be |
| 21 | Accordion | `Accordion` | **2** | AccordionProperties: musette, the reed banks deliberately offset ~16 cents |
| 22 | Harmonica | `Harmonica` | **2** | HarmonicaProperties: one free reed inside a cupped-hand formant pair |
| 23 | Tango Accordion | `TangoAccordion` | **2** | TangoAccordionProperties: the same box tuned DRY (~3 cents), which is what a bandoneon is |

## 24-31 Guitar

| # | patch | class | | notes |
|---|---|---|---|---|
| 24 | Acoustic Guitar (nylon) | `NylonGuitar` | **4** | Iowa classical guitar, six strings measured sul A/B/D/E/G |
| 25 | Acoustic Guitar (steel) | `SteelGuitar` | **2** | the measured classical's body with a steel string on it: less damping, a pick, 35% more stretch |
| 26 | Electric Guitar (jazz) | `JazzGuitar` | **3** | electric family: pluck comb x pickup comb, amp and cabinet; judged by ear |
| 27 | Electric Guitar (clean) | `ElectricGuitar` | **3** | as 26 -- the reference voice of the family |
| 28 | Electric Guitar (muted) | `MutedGuitar` | **3** | as 26, palm mute |
| 29 | Overdriven Guitar | `OverdrivenGuitar` | **3** | as 26, driven harder |
| 30 | Distortion Guitar | `DistortionGuitar` | **3** | as 26, driven hardest |
| 31 | Guitar Harmonics | `GuitarHarmonics` | **3** | as 26, touched harmonics |

## 32-39 Bass

| # | patch | class | | notes |
|---|---|---|---|---|
| 32 | Acoustic Bass | `AcousticBass` | **2** | the upright PLUCKED: GM 43's measured body with a plucked base, comb at the quarter point |
| 33 | Electric Bass (finger) | `FingeredBass` | **3** | electric bass family, cabinet and amp; judged by ear |
| 34 | Electric Bass (pick) | `PickedBass` | **3** | as 33, pick |
| 35 | Fretless Bass | `FretlessBass` | **3** | as 33, fretless -- loses its top rather than starting without it |
| 36 | Slap Bass 1 | `SlapBass` | **3** | as 33, slap |
| 37 | Slap Bass 2 | `PoppedBass` | **3** | as 33, pop |
| 38 | Synth Bass 1 | `PluckedString` | **1** | falls through to the generic plucked string |
| 39 | Synth Bass 2 | `PluckedString` | **1** | as 38 |

## 40-47 Strings

| # | patch | class | | notes |
|---|---|---|---|---|
| 40 | Violin | `Violin` | **4** | Iowa violin |
| 41 | Viola | `Viola` | **4** | Iowa viola, fitted across registers |
| 42 | Cello | `Cello` | **4** | Iowa cello |
| 43 | Contrabass | `Contrabass` | **4** | Iowa double bass |
| 44 | Tremolo Strings | `BowedString` | **2** | tremolo_bow(): the articulation applied to whichever body the register picks -- amplitude modulation, per-player rate and phase |
| 45 | Pizzicato Strings | `PizzicatoStrings` | **2** | pizzicato(): the MEASURED body of whichever instrument the register picks, plucked -- and the ring scales with register, 2.35 s at E1 to 0.42 at E5 |
| 46 | Orchestral Harp | `Harp` | **2** | Harp: plucked in toward the middle (the comb nulls at h2.6, which is why it is mellow) and anchored into the board, so it rings |
| 47 | Timpani | `Timpani` | **2** | analytic: the Bessel zeros of a clamped circular membrane. No recording exists in the set |

## 48-55 Ensemble

| # | patch | class | | notes |
|---|---|---|---|---|
| 48 | String Ensemble 1 | `BowedString` | **1** | the generic bowed string |
| 49 | String Ensemble 2 | `SlowBowedString` | **2** | its own slow-bowed class |
| 50 | Synth Strings 1 | `BowedString` | **1** | the generic bowed string |
| 51 | Synth Strings 2 | `BowedString` | **1** | as 50 |
| 52 | Choir Aahs | `ChoirAahs` | **3** | vocal tract and formants; Ben's ear on the consonant balance |
| 53 | Voice Oohs | `VoiceOohs` | **3** | as 52 |
| 54 | Synth Choir | `SynthVoice` | **2** | its own class, theory |
| 55 | Orchestra Hit | `OrchestraHit` | **2** | its own class, theory |

## 56-63 Brass

| # | patch | class | | notes |
|---|---|---|---|---|
| 56 | Trumpet | `Trumpet` | **4** | Iowa trumpet, three registers |
| 57 | Trombone | `Trombone` | **4** | Iowa tenor and bass trombone, refitted across registers |
| 58 | Tuba | `ConicalBrass` | **4** | Iowa tuba |
| 59 | Muted Trumpet | `MutedTrumpet` | **2** | its own class; the mute is theory |
| 60 | French Horn | `Horn` | **4** | Iowa horn, re-measured across four registers and pp/mf/ff |
| 61 | Brass Section | `Trombone` | **1** | the trombone stands in for the whole section |
| 62 | Synth Brass 1 | `Brass` | **1** | the generic brass base |
| 63 | Synth Brass 2 | `Brass` | **1** | as 62 |

## 64-71 Reed

| # | patch | class | | notes |
|---|---|---|---|---|
| 64 | Soprano Sax | `Saxophone` | **4** | Iowa soprano sax |
| 65 | Alto Sax | `Saxophone` | **4** | Iowa alto sax |
| 66 | Tenor Sax | `Saxophone` | **4** | the sax law, measured on soprano and alto and transposed |
| 67 | Baritone Sax | `Saxophone` | **4** | as 66 |
| 68 | Oboe | `ConicalReed` | **4** | Iowa oboe |
| 69 | English Horn | `ConicalReed` | **4** | the conical reed law measured on the oboe; its close relative |
| 70 | Bassoon | `Bassoon` | **4** | Iowa bassoon |
| 71 | Clarinet | `Clarinet` | **4** | Iowa clarinet family -- Bb, Eb and bass, to find one register law |

## 72-79 Pipe

| # | patch | class | | notes |
|---|---|---|---|---|
| 72 | Piccolo | `OpenPipe` | **4** | the flute law, measured across bass, alto and concert flute |
| 73 | Flute | `OpenPipe` | **4** | Iowa flute (nonvib -- vibrato smears the harmonics) |
| 74 | Recorder | `OpenPipe` | **1** | the generic open pipe |
| 75 | Pan Flute | `StoppedPipe` | **1** | the generic stopped pipe |
| 76 | Blown Bottle | `BlownBottle` | **2** | its own class, theory |
| 77 | Shakuhachi | `OpenPipe` | **1** | the generic open pipe; a shakuhachi's breath and pitch bend are not modelled |
| 78 | Whistle | `OpenPipe` | **1** | the generic open pipe |
| 79 | Ocarina | `Ocarina` | **2** | its own class -- a vessel flute, theory |

## 80-87 Synth Lead

| # | patch | class | | notes |
|---|---|---|---|---|
| 80 | Lead 1 (square) | `SquareSynth` | **2** | its own class, theory |
| 81 | Lead 2 (sawtooth) | `SawtoothSynth` | **2** | its own class, theory |
| 82 | Lead 3 (calliope) | `SynthLead` | **1** | one SynthLeadProperties serves 82-87 |
| 83 | Lead 4 (chiff) | `SynthLead` | **1** | as 82 |
| 84 | Lead 5 (charang) | `SynthLead` | **1** | as 82 |
| 85 | Lead 6 (voice) | `SynthLead` | **1** | as 82 |
| 86 | Lead 7 (fifths) | `SynthLead` | **1** | as 82 |
| 87 | Lead 8 (bass+lead) | `SynthLead` | **1** | as 82 |

## 88-95 Synth Pad

| # | patch | class | | notes |
|---|---|---|---|---|
| 88 | Pad 1 (new age) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 89 | Pad 2 (warm) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 90 | Pad 3 (polysynth) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 91 | Pad 4 (choir) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 92 | Pad 5 (bowed) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 93 | Pad 6 (metallic) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 94 | Pad 7 (halo) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 95 | Pad 8 (sweep) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |

## 96-103 Synth Effects

| # | patch | class | | notes |
|---|---|---|---|---|
| 96 | FX 1 (rain) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 97 | FX 2 (soundtrack) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 98 | FX 3 (crystal) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 99 | FX 4 (atmosphere) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 100 | FX 5 (brightness) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 101 | FX 6 (goblins) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 102 | FX 7 (echoes) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |
| 103 | FX 8 (sci-fi) | `BowedString` | **1** | one BowedStringProperties serves all sixteen pads and FX |

## 104-111 Ethnic

| # | patch | class | | notes |
|---|---|---|---|---|
| 104 | Sitar | `Sitar` | **2** | its own class; sympathetic strings and jawari, but the responder set is ASSERTED -- no recording |
| 105 | Banjo | `PluckedString` | **1** | the generic plucked string; a banjo's membrane head is a real resonator |
| 106 | Shamisen | `PluckedString` | **1** | the generic plucked string |
| 107 | Koto | `PluckedString` | **1** | the generic plucked string |
| 108 | Kalimba | `Mallet` | **1** | the generic mallet base; a kalimba is a plucked cantilever tine |
| 109 | Bag pipe | `ReedPipe` | **1** | one ReedPipeProperties for the bagpipe and the shanai |
| 110 | Fiddle | `SoloViolin` | **4** | the measured violin, given solo treatment |
| 111 | Shanai | `ReedPipe` | **1** | as 109 |

## 112-119 Percussive

| # | patch | class | | notes |
|---|---|---|---|---|
| 112 | Tinkle Bell | `Crotale` | **4** | Iowa crotales, 25 pitches |
| 113 | Agogo | `Agogo` | **2** | its own class, theory |
| 114 | Steel Drums | `SteelPan` | **4** | built from the instrument's design, then corrected against Freesound 742254 |
| 115 | Woodblock | `WoodPercussion` | **4** | Iowa woodblocks |
| 116 | Taiko Drum | `MembraneDrum` | **2** | the membrane drum class |
| 117 | Melodic Tom | `TomTom` | **2** | the tom class |
| 118 | Synth Drum | `Mallet` | **1** | the generic mallet base. CATEGORY ERROR |
| 119 | Reverse Cymbal | `Mallet` | **1** | the generic mallet base. CATEGORY ERROR: this needs a BACKWARDS envelope |

## 120-127 Sound Effects

| # | patch | class | | notes |
|---|---|---|---|---|
| 120 | Guitar Fret Noise | `GuitarFretNoise` | **3** | its own class -- slide, squeak and position shift; reworked against Ben's ear |
| 121 | Breath Noise | `BreathNoise` | **2** | its own class, theory |
| 122 | Seashore | `Seashore` | **2** | its own class, theory |
| 123 | Bird Tweet | `Mallet` | **1** | the generic mallet base. CATEGORY ERROR |
| 124 | Telephone Ring | `Mallet` | **1** | the generic mallet base. CATEGORY ERROR: US ringback is 440+480 Hz gated |
| 125 | Helicopter | `Mallet` | **1** | the generic mallet base. CATEGORY ERROR |
| 126 | Applause | `Applause` | **2** | its own class, theory |
| 127 | Gunshot | `Gunshot` | **2** | its own class, theory |

