# GS maps: what we have, and what the later ones would take

From Roland's SC-88Pro owner's manual (its instrument list, every tone in its Native,
SC-88 and SC-55 maps side by side; examples/gs_maps.py). The SC-55 map of a later
module is the SC-55mkII's, a few dozen tones more than the original SC-55's we built.

| map | tones | built | to do |
|---|---|---|---|
| SC-55 map (mkII) | 226 | 188 | 38 |
| SC-88 map | 409 | 188 | 221 |
| SC-88Pro map | 765 | 188 | 577 |

## The SC-88 map's 221 missing tones, by what they take

| kind | count | what it takes |
|---|---|---|
| alias | 6 | one of our voices, under another number |
| derived | 53 | a setting of one of ours (wide, dark, octave, layered, velocity, reversed) |
| organ | 16 | a registration of our organs (drawbars, stops, the Leslie) |
| synth | 77 | a Moog panel, voiced by ear |
| refit | 49 | an articulation of one we have, wanting a fit to a reference |
| new | 20 | an instrument we have not modelled, wanting references |

### alias

3.8 Old Upright (mkII), 4.24 60'sE.Piano (mkII), 98.3 Round Glock, 117.1 Real Tom, 117.9 Rock Tom, 118.9 Elec Perc (mkII)

### derived

0.8 Piano 1w (mkII), 0.16 Piano 1d (mkII), 1.8 Piano 2w (mkII), 2.1 EG+Rhodes 1, 2.2 EG+Rhodes 2, 2.8 Piano 3w (mkII), 4.16 FM+SA EP (mkII), 5.16 St.FM EP (mkII), 6.16 Harpsi.w (mkII), 6.24 Harpsi.o (mkII), 11.8 Vib.w (mkII), 12.8 Marimba w (mkII), 14.9 Carillon (mkII), 15.1 Santur 2, 24.16 Nylon Gt.o (mkII), 24.24 VeloHarmnix, 25.9 Nylon+Steel, 31.16 Ac.Gt.Harm., 48.9 Orchestra 2, 48.11 Choir Str., 48.16 St.Strings, 48.24 VeloStrings, 49.10 St.SlowStr., 52.8 St.Choir, 55.10 Double Hit, 60.16 Horn Orch, 62.16 OctaveBrass (mkII), 63.16 VeloBrass 1 (mkII), 63.17 VeloBrass 2, 98.5 GlocknChime, 98.18 Bell Harp, 98.19 Gamelimba, 99.2 Nylon Harp, 99.3 Harpvox, 99.5 NylonRhodes, 102.3 Echo Pan 2, 102.4 Big Panner, 102.5 Reso Panner, 104.1 Sitar 2 (mkII), 104.2 DetuneSitar, 119.1 ReverseCym2, 119.8 Rev.Snare 1, 119.9 Rev.Snare 2, 119.16 Rev.Kick 1, 119.17 Rev.ConBD, 119.24 Rev.Tom 1, 119.25 Rev.Tom 2, 120.3 Gt.CutNz. 2, 120.4 Dist.CutNz., 120.6 Pick Scrape, 123.3 Bird 2 (mkII), 124.7 Scratch 2, 126.6 Applause 2

### organ

16.1 Organ 101, 16.9 Organ 109, 16.16 60'sOrgan 1 (mkII), 16.17 60'sOrgan 2, 16.18 60'sOrgan 3, 16.32 Organ 4 (mkII), 16.33 Even Bar, 16.40 Organ Bass, 17.1 Organ 201, 17.32 Organ 5 (mkII), 18.8 Rotary Org., 18.16 RotaryOrg.S, 18.24 RotaryOrg.F, 19.16 ChurchOrg.3 (mkII), 19.24 Organ Flute, 19.32 Trem.Flute

### synth

35.4 SynFretless, 38.1 Syn.Bass101 (mkII), 38.9 TB303 Bass, 38.10 Tekno Bass, 38.16 Reso SHBass, 39.1 Syn.Bass201, 39.2 ModularBass, 39.3 Seq Bass, 39.9 X Wire Bass, 39.16 Rubber Bass (mkII), 39.17 SH101Bass 1, 39.18 SH101Bass 2, 39.19 Smooth Bass, 50.1 OB Strings, 54.8 Syn.Voice, 55.16 Lo Fi Rave, 62.1 Poly Brass, 62.9 Quack Brass, 80.1 Square (mkII), 80.2 Hollow Mini, 80.3 Mellow FM, 80.4 CC Solo, 80.5 Shmoog, 80.6 LM Square, 80.8 Sine Wave (mkII), 81.1 Saw (mkII), 81.2 Pulse Saw, 81.3 Feline GR, 81.4 Big Lead, 81.5 Velo Lead, 81.6 GR-300, 81.7 LA Saw, 81.8 Doctor Solo (mkII), 81.16 Waspy Synth, 82.1 Vent Synth, 82.2 PurePanLead, 84.8 Dist.Lead, 86.1 Big Fives, 87.1 Big & Raw, 87.2 Fat & Perky, 88.1 Fantasia 2, 89.1 Thick Pad, 89.2 Horn Pad, 89.3 RotaryStrng, 89.4 Soft Pad, 90.1 80'sPolySyn, 91.1 Heaven II, 93.1 Tine Pad, 93.2 Panner Pad, 95.1 Polar Pad, 95.8 Converge, 95.9 Shwimmer, 95.10 CelestialPd, 96.1 Harmo Rain, 96.2 AfricanWood, 96.8 Clavi Pad, 97.1 Ancestral, 97.2 Prologue, 97.8 Rave, 98.1 Syn Mallet (mkII), 98.2 SoftCrystal, 98.4 Loud Glock, 98.6 Clear Bells, 98.7 X'mas Bell, 98.8 Vibra Bells, 98.9 Digi Bells, 98.16 ChoralBells, 98.17 Air Bells, 99.1 Warm Atmos, 99.4 HollowRels., 99.6 Ambient Pad, 101.1 Goblinson, 101.2 50's Sci-Fi, 102.1 Echo Bell (mkII), 102.2 Echo Pan (mkII), 102.6 Water Piano, 103.1 StarTheme 2

### refit

4.25 Hard Rhodes, 4.26 MellwRhodes, 5.24 Hard FM EP, 11.1 Hard Vibe, 15.8 Cimbalom, 22.1 Harmonica 2, 24.32 Nylon Gt.2 (mkII), 24.40 Lequint Gt., 25.32 Steel Gt.2, 26.1 Mellow Gt., 28.1 MutedDis.Gt, 28.16 Funk Gt.2 (mkII), 30.1 Dist. Gt2, 30.2 DazedGuitar, 33.1 FingeredBs2, 33.2 Jazz Bass, 34.8 MutePickBs., 35.1 FretlessBs2, 35.2 FretlessBs3, 35.3 FretlessBs4, 35.5 Mr.Smooth, 36.8 Reso Slap, 40.8 Slow Violin (mkII), 44.8 SlowTremolo, 44.9 SuspenseStr, 48.1 Strings 2, 48.10 TremoloOrch, 49.1 Slow Str. 2, 49.8 Legato Str., 49.9 WarmStrings, 52.9 Mello Choir, 52.32 ChoirAahs 2 (mkII), 55.8 Impact Hit, 55.9 Philly Hit, 56.1 Trumpet 2, 56.24 Bright Tp., 56.25 Warm Tp., 57.1 Trombone 2 (mkII), 58.1 Tuba 2, 60.1 Fr.Horn 2 (mkII), 60.8 Fr.HornSolo, 61.16 Brass Fall, 63.1 Soft Brass, 65.8 Hyper Alto, 66.8 BreathyTnr., 105.1 Muted Banjo, 106.1 Tsugaru, 111.1 Shanai 2, 120.5 Bass Slide

### new

16.24 CheeseOrgan, 56.8 Flugel Horn, 71.8 Bs Clarinet, 75.8 Kawala, 104.8 Tambra, 104.16 Tamboura, 105.8 Rabab, 105.16 Gopichant, 105.24 Oud, 107.16 Kanoon, 111.8 Pungi, 111.16 Hichiriki, 112.8 Bonang, 112.9 Gender, 112.10 GamelanGong, 112.11 St.Gamelan, 112.16 RAMA Cymbal, 113.8 Atarigane, 123.4 Kitty, 123.5 Growl

## Drum sets

| map | sets | we have | to do |
|---|---|---|---|
| SC-55 map | 10 | 10 | -- |
| SC-88 map | 14 | 8 of them (Standard 1, Room, Power, Electronic, Jazz, Brush, Orchestra, SFX; our TR-808 without the 909's sounds) | Standard 2, TR-808/909, Dance, Ethnic, Kick & Snare, Rhythm FX |
| SC-88Pro map | 25 | as above | and Standard 3 (each hit varied in timbre and timing), Hip Hop, Jungle, Techno, CR-78, TR-606, TR-707, TR-909, Asia, Cymbal & Claps, Rhythm FX 2 |
