#!/usr/bin/env python3
"""How complete is each of the 128 GM patches? Writes coverage.md.

    python3 examples/gm_coverage.py [outfile]

THE CLASS COLUMN IS READ FROM THE CODE, so it cannot drift: it asks
patch_map the same question blockrender asks. The RATING is a judgement and
lives in RATED below, where it can be argued with.

The scale, and how each rung was decided:

  0  nothing -- no voice at all. (Nothing scores 0: every program resolves
     to something. That is not the same as every program being served.)
  1  a general class -- this patch is played by a shared base, or by another
     instrument's voice standing in for it. Some stand-ins are reasonable
     (an Electric Grand is a string piano) and some are category errors
     (a Telephone Ring is not a mallet). The note says which.
  2  a specific class built from theory -- the instrument has its own voice,
     derived from how it works, with nothing heard or measured against it.
  3  ...and calibrated by ear -- Ben listened and the numbers moved.
  4  ...and fitted against a RECORDING of the instrument, or against the
     family law measured on its close relatives (the sax law is measured on
     soprano and alto; the flute law across bass, alto and concert).

WHAT COUNTS AS A RECORDING, since that is the line that matters: audio of the
instrument that was analysed and fitted against. Published measurements of an
instrument -- the Rhodes' high-speed camera papers, say -- are better than
theory but are NOT audio, so those voices sit at 2 with a note. The point of
the scale is to show where the model has been contradicted by reality, and only
a recording can do that.

A SYNTHESIZER IS AN INSTRUMENT TOO. The synth programs are Moog Messenger
patches, and the Messenger engine is fitted against Ben's Messenger recorded
(examples/messenger_fit.py) -- so a patch that is the Messenger alone is a 4,
and one with a part the Messenger has not got is a 3.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import patch_map

GM = """Acoustic Grand Piano,Bright Acoustic Piano,Electric Grand Piano,Honky-tonk Piano,
Electric Piano 1,Electric Piano 2,Harpsichord,Clavinet,Celesta,Glockenspiel,Music Box,
Vibraphone,Marimba,Xylophone,Tubular Bells,Dulcimer,Drawbar Organ,Percussive Organ,
Rock Organ,Church Organ,Reed Organ,Accordion,Harmonica,Tango Accordion,
Acoustic Guitar (nylon),Acoustic Guitar (steel),Electric Guitar (jazz),
Electric Guitar (clean),Electric Guitar (muted),Overdriven Guitar,Distortion Guitar,
Guitar Harmonics,Acoustic Bass,Electric Bass (finger),Electric Bass (pick),
Fretless Bass,Slap Bass 1,Slap Bass 2,Synth Bass 1,Synth Bass 2,Violin,Viola,Cello,
Contrabass,Tremolo Strings,Pizzicato Strings,Orchestral Harp,Timpani,String Ensemble 1,
String Ensemble 2,Synth Strings 1,Synth Strings 2,Choir Aahs,Voice Oohs,Synth Choir,
Orchestra Hit,Trumpet,Trombone,Tuba,Muted Trumpet,French Horn,Brass Section,
Synth Brass 1,Synth Brass 2,Soprano Sax,Alto Sax,Tenor Sax,Baritone Sax,Oboe,
English Horn,Bassoon,Clarinet,Piccolo,Flute,Recorder,Pan Flute,Blown Bottle,
Shakuhachi,Whistle,Ocarina,Lead 1 (square),Lead 2 (sawtooth),Lead 3 (calliope),
Lead 4 (chiff),Lead 5 (charang),Lead 6 (voice),Lead 7 (fifths),Lead 8 (bass+lead),
Pad 1 (new age),Pad 2 (warm),Pad 3 (polysynth),Pad 4 (choir),Pad 5 (bowed),
Pad 6 (metallic),Pad 7 (halo),Pad 8 (sweep),FX 1 (rain),FX 2 (soundtrack),
FX 3 (crystal),FX 4 (atmosphere),FX 5 (brightness),FX 6 (goblins),FX 7 (echoes),
FX 8 (sci-fi),Sitar,Banjo,Shamisen,Koto,Kalimba,Bag pipe,Fiddle,Shanai,Tinkle Bell,
Agogo,Steel Drums,Woodblock,Taiko Drum,Melodic Tom,Synth Drum,Reverse Cymbal,
Guitar Fret Noise,Breath Noise,Seashore,Bird Tweet,Telephone Ring,Helicopter,
Applause,Gunshot""".replace("\n", "").split(",")

# program: (rating, note). The note earns the rating or explains the gap.
RATED = {
 0:(4,"FITTED TO A STEINWAY B (VCSL, CC0; examples/upright_fit.py --ref=steinway) -- the model whose published law it had: inharmonicity by partial peaks (the real bass ~3x stiffer), spectrum and board, decay with its late tail, a 2 ms hammer, the strike's thump and noise (a pluck without them, Ben), unisons beating slowly and irregularly as the B's do (one ratio made a phaser). Levels held: VCSL's are normalized. The undamped strings ring sympathetically (the free-string register)"),
 1:(4,"an UPRIGHT, measured (VSCO-2 CE, Ivy Audio's): inharmonicity by partial peaks (short wound bass 4-9x the grand's, the scale break at C#3-F3), spectrum, decay with its late tail and register levels fitted per key (examples/upright_fit.py), a hammer contact shortening with force. A small board's brightness, which GM's name asks for; the grand voiced hard is kept as a voicing. Ben: very close, then great once the attack's knee went in"),
 2:(4,"a CP-70, FITTED TO PIANOBOOK'S \"DAVID'S CP70\" (Conner Sawchuk; 31 keys, 4-7 layers at their recorded levels, measured only; examples/upright_fit.py --ref=cp70): the short strings' 1/L^4 stiffness, derived, held (F1's B 12.6e-4 recorded, 12.0 derived); no soundboard, a piezo on the bridge; the decay fitted -- a fundamental that sings over fast upper partials (8.6 -> 6.8 dB); the hammers' brightness swinging far with velocity, dark soft and bright hard (13.4 -> 10.3 dB); the register's level (4.3 -> 3.5). The rest is one instrument's key-by-key variation. Ben: sounds great"),
 3:(3,"the measured upright (GM 1) with the tuner's hand off: unisons 8-20 cents, CC1 the wheel. The upright is fitted; the detune is judged from beat rates, not measured"),
 4:(4,"FITTED TO LEARMAN'S 1977 MARK I off the harp connector (jRhodes3d, CC BY-NC, measured only; examples/rhodes_fit.py), on what his EQ cancels -- the growl a harder layer adds, the hard attack's first 50 ms, the bark's fade, the decay (a tine sings 3-4x longer than we had it), the bass h1 BUILDING for seconds (F1 peaks 3.9 s in): the paper's own pickup (DAFx-17), a point tip over the magnet's frustum face on an arc, so a wide bass swing spikes each half cycle; each harmonic a sum of decaying layers, the swing's power series, at its true phase. Then voiced by ear: a forte that buzzes in the bass, mf untouched, and the buzz dying away faster than the tone (a wide swing damps faster); the register level even across the keyboard, as Gwazda's Wurlitzer measures (it had run 43 dB C2-C7 riding the swing). Ben, live: good and distinct from the Wurlitzer"),
 5:(4,"FITTED TO GWAZDA'S BALTIWURLI, a 200A (measured only; examples/wurli_fit.py), DI and speaker sets, the takes the recording's clipper spared: the reed swings through a SLOT in the plate (Pfeifle & Muenster, DAFx-17), a square-edged bump, not the one-sided 1/d first read (ladder h2-h32 14.6 -> 10.8 dB rms) -- centred it loses the fundamental; each harmonic's envelope a signed sum of exponentials, so a wide bass swing buzzes to h32 against the edges and its fundamental builds back as the swing decays (the lingering low attack, Ben); each layer at its true phase in the wave (in phase, a flat top came out lopsided); the reed's decay by register (log-rate 0.35); the action's thump from the Mech set, at the pack's own mix; the register level to the DI's own (6.2 -> 2.1 dB rms). Not modelled: a fixed ring near 387 Hz from E5 up. Ben: better on the low buzz; kept; live, good and distinct from the Rhodes"),
 6:(4,"FITTED TO VCSL'S HARPSICHORDS (CC0; examples/harpsi_fit.py): the English Normal and Lute sets and the Flemish High and Low, each stop measured as its difference from the 8' on one instrument, so the room drops out. A STRING BANK, like the piano: every choir on a key is present, each slightly apart in cents, stiffness and partial tuning, and the stops (the CC11 word, rated below) choose which the jacks pluck; a key lifts every damper, so the undrawn choirs ring through the bridge. The quill plucks at fixed force, so the comb never fills and there are no dynamics. The ladder and body over the whole band, partials to 16 kHz, the decay by band (log-rate error 0.96 -> 0.65), random partial phases (in phase they swept like a phaser, Ben), and the quill's catch before it slips (3.5-6 ms, measured). Ben: sounds great"),
 7:(4,"FITTED TO A HOHNER D6 (Aalto's companion page to Gabrielli, Valimaki & Bilbao, ICMC 2011: Bb2, E4, F#5, each twice, measured only; examples/clav_fit.py) on the DAFx-12 pickup paper's geometry -- a 67.8 cm string at 161 Hz where the estimate had 0.26 m, the bridge pickup at 4 cm and the centre one 18.5-6.5 cm from the termination, the four switch settings (centre, bridge, both, anti-phase) -- the takes on the CENTRE pickup (6.7 dB rms, against 7.6 for the bridge); the ladder darkening up the keyboard (F#5's h2 25 dB down where the estimate had it level), a string that sings (Bb2 2-3 dB/s, not the estimate's 17), B 3.5e-5 measured (not 1.1e-4); and the KEY-UP, measured: a thump at the mechanism's fixed Hz plus the string let go at its own 2nd-4th harmonics, 35 dB under the strike and gone in ~30 ms -- live as well, stamped at the key-up. Three notes: the compass past them is the length law's. Ben: sounds good"),
 8:(4,"FITTED TO MACSAT-RD'S CELESTA (Freesound, CC0; twelve notes A4-G#5; examples/steelbar_fit.py): a fundamental all but alone, EXACT harmonics 2x-7x decaying with it (the glow under a held chord), and the plate's own free-bar modes, 2.76x and 5.42x, 43-47 dB down and dying ten times faster -- the class had the plate's modes alone, no harmonics; each mode's own level and decay, the levels calibrated through the renderer. Touch kept (a keyboard action); the felt's 2 ms landing validated against the takes' first 5 ms. One octave measured, so the register is weakly held. Ben: a perfect fit"),
 9:(4,"Iowa orchestra bells; rings out to -80 dB (~40 s), where an 8 s hold had cut it at -15. Ben: sounds good"),
 10:(4,"FITTED TO TWO BOXES (Freesound, CC0: folkman's in D, 16 teeth, and rbnuser's 13; examples/steelbar_fit.py): the tooth a CANTILEVER (its ~6x and 17.6x), not the free bar the class had, with exact harmonics; each mode's level and decay, the decay doubling up the comb, the level rising 8.6 dB an octave (both boxes agree); THE PIN'S SNAP -- broadband, as loud as the fundamental above 3 kHz for 5 ms, then the comb's buzz to 60 ms (a slower strike-noise tail); the tooth an octave below ringing on some keys (4 of 14 measured), only where that tooth exists. No touch live: the pins pluck. Not modelled: the neighbouring teeth's ring (up to -34 dB). Ben: perfect"),
 11:(4,"Iowa vibraphone. The motor is the mod wheel: a mono tremolo, 5 Hz, half the level at a full wheel -- asserted, not fitted, and one depth for every partial where the tubes swing mostly the fundamental. A damper (0.5 s at key-up, the GM sets' median) and the damper pedal on CC64. Ben: sounds good"),
 12:(4,"Iowa marimba"),
 13:(4,"Iowa xylophone"),
 14:(4,"VSCO 2 CE's chimes (CC0), C4 G4 C5 F5: a free-free tube's modes, the note an octave under the fourth -- plus the hum a third above it and a mode a sixth below, rising with pitch; the upper modes compressing as the tube shortens; each mode's own ring, the hum outlasting the rest. Renders read back on the fitted lines. Ben, by ear: sounds great"),
 15:(4,"FITTED TO KEVIN KEMP'S 17/16 DULCIMER (Pianobook \"Lite Hammered Dulcimer\", measured only; examples/dulcimer_fit.py), 33 notes D3-F6: the stiffness by bridge (the bass courses 3e-5, the treble stepping to 1.6e-4 and rising), no fixed strike notch (a hand's hammer lands anywhere), the decay by the partial's Hz in every register, the ladder and body read at the partials' own peaks, each partial's course beating at its own rate (all in step had been a phaser), and the box knocked by every stroke (140-510 Hz, gone in a tenth of a second). A BANK OF STRINGS and no dampers: every course free, driven through two bridges, the treble string's other length ringing a fifth away, the stroke's kick ringing the strings below the note and not those above (register.py). Ben: sounds perfect"),
 16:(4,"hammondman's tonewheel organ through a Leslie, two packs (freesound 18844, 15120, CC0): the recordings' drawbar settings DERIVED from their spectra (examples/drawbar_fit.py) and the model's drawbars, gains and foldback validated on them to 3.5 dB rms -- 23 notes slow, 17 fast; the Leslie measured: the bass rotor directional from 160 Hz (it barely swung), the cabinet's response (a dip at 400-640 Hz, the horn's 1.5 kHz peak), a two-rotor crossover (partials near 800 Hz from both: the shimmer), the horn's throw and lobe refitted (6.9 -> 4.7 dB); and the wheels -- the KEY CLICK as the contacts make it (each drawbar's at its own instant over 15 ms, at the wheel's running phase, a bounce of noise; within ~1 dB of the takes' burst), their own harmonics 8-17 dB purer, the takes' leakage at the unpulled drawbars (-48 dB). Ben: drawbar and Leslie sound great; the click sounds good"),
 17:(4,"tonewheel, percussive tap. The drawbars, Leslie and cabinet are GM 16's, measured; the tap a rank of its own, the B3's third harmonic (Real Rotor Organ: its decay ~100 dB/s, its level its maker's mix), the drawbars sustaining under it. Ben: B3 as the default, level is good"),
 18:(4,"as 16, the rok pack's fast rotor and its drawbars (00 8876 034) measured; and its overdrive, from the energy off the drawbars' harmonics: only to the edge of breakup (drive 1.53 -> 0.92, the recording's 41 dB under the drawbars). Ben: sounds great"),
 19:(4,"FITTED TO PITEA'S PIPES (Lars Palo's set of the Gronlund organ, CC BY-SA 2.5; examples/pitea_fit.py): the Principal 8, Octave 4 and Super Octave 2 each their own measured series, h1-h32 at three anchor pitches, within 0.9 dB rms; the pipe's SPEECH fitted register by register -- 24 of its own periods, the upper harmonics first, h2-h4 overshooting ~+6 dB mid-keyboard, the release as long as the speech, and each pipe's release its own, an upper band ringing on past the fundamental on some (the release's squeak, fitted to the spread across 33 pipes) -- and the wind before it (the jet's turbulence, the reeds' attack rush). Pitea's fundamentals swing 15 dB key to key with its hall's modes; the tables keep the median and leave the room out. A shared wind per division, on by default -- a chord breathes as it enters and lifts, every pipe on the chest hearing it -- and a Tremulant. Every other stop is rated in the stops map. Ben: sounds great"),
 20:(4,"donyaquick's harmonium (freesound 330410, CC0), all 32 keys G2-D5 held 7-12 s (examples/wind_fit.py --voice=reedorgan): it plays an 8' and a 4' -- its evens beat, each key's 4' 0.4-12 cents sharp (rank_detune) -- so ours is measured at 8'+4'; the foundation reed fitted far brighter (gate 0.52 -> 1.07), the 4' voiced as it and at twice the level, the series within 2.5 dB rms, the partials' odd/even cents the take's; the reed's hiss between the harmonics. The French registers re-anchored on it. Ben: sounds great"),
 21:(4,"hammondman's Hohner on musette (freesound pack 18842, CC0), 15 keys A3-E6 (examples/wind_fit.py --voice=accordion): the musette's detune measured -- 16.0 cents at A4, as asserted, narrowing 3.3 an octave -- and no 16'; the reed bright and HOLLOW (odd harmonics strong, evens 4.8 dB down), the box's colour by absolute frequency (FormantBody), the reeds' hiss; and the BELLOWS' PUSH on a note from silence -- a +10 dB swell at 0.1 s, brightening the bass far more than the treble, every partial settling together -- carried over a slur where it stands. Ben: sounds great"),
 22:(4,"VCSL Hohner Special 20s and Super 64 (CC0), 30 sustains (examples/wind_fit.py): the reed's flow and the tongue's own sine, the cupped hands and a broad top fitted by absolute frequency to 17 kHz, each reed its own jagged ladder (the takes' roughness and holes), breath, flutter and wobble. Ben: very close, sounding real; the lowest and highest notes slightly off"),
 23:(4,"FITTED TO A 1930 ELA BANDONEON (Joerg Bleymehl's bandoneon_v2 SoundFont, twelve notes C2-F6, measured only; examples/wind_fit.py --voice=bandoneon): the second reed an OCTAVE ABOVE, quiet (-13.5 dB) and ~2.5 cents off -- the class had a 16' under the note, so GM 23 sounded an octave low -- and no wet unison; a bright reed, brightest in the bass and ringing there to 8 kHz and past (harmonics by Hz, to 12 kHz, where 32 had ended C2 at 2.1); the box, hardly radiating the bass fundamentals; the reeds' hiss and the bass reeds' buzz; a push a fifth of the musette's; the big bass reeds BLOOMING, their upper harmonics after the note (Ben: 'a pressure swell'). The SoundFont is peak-normalised: the level across the keyboard held. Ben: sounds great"),
 24:(4,"Iowa classical guitar, six strings measured sul A/B/D/E/G; its DECAY fitted at last (examples/nylon_decay_fit.py: the runs split at their onsets, each note named by its own pitch, 26 takes read) -- a held note had fallen 2-3 dB/s, twenty seconds to silence; now ~8 dB/s at E2 to ~20 at B4, faster on the upper partials. Ben, A/B (examples/nylon_ab.py): fit is good"),
 25:(4,"NYU's GuitarSet (CC BY 4.0), a steel-string acoustic on a microphone: 493 notes that sound alone in its 360 takes. The string measured (examples/egtr_fit.py --string=steel: decay 10-30 dB/s rising with the note, the stretch 1-2.4e-4 -- the derivation had 1.7e-3), the classical's borrowed body refitted to it by absolute frequency (examples/steel_fit.py: less mid honk, 3-6 kHz presence; 3.3 -> 1.2 dB). Ben: good"),
 26:(4,"Fraunhofer IDMT-SMT-Guitar (CC BY-NC-ND, measured only), DI, the RG2820's neck humbucker (examples/egtr_fit.py): the family's string measured on 306 notes (decay 5-30 dB/s, rising with the harmonic and up the neck; stretch 4e-4 at E2 to 1e-4 at E4), each note fretted where a player puts it so the pick and coil combs climb the neck, the pick, notch, tilt and the coil's load fitted (ladder 8.95 -> 5.40 dB); amp and cabinet after, unchanged"),
 27:(4,"as 26, on the Stratocaster's neck single coil (the voice moved there from the middle one): ladder 5.33 -> 4.23 dB, the coil's load 5.0 kHz. Ben, DI A/B: very, very close"),
 28:(4,"as 26, the palm mute MEASURED (IDMT-SMT-Guitar dataset 2: three guitars, five muted notes at the fifth fret of every string, each against the same note open): the decay 3.6-5.5 x the open string, steeply more up the neck (h1 ~36 dB/s at A2, ~120 at A4), and a partial low-pass at onset (equal to h4, then h5/h6 8-17 dB under the open note) -- onset ladder 13.5 -> 5.6 dB. Ben, DI A/B: close"),
 29:(4,"as 30 (the same bridge humbucker), driven less hard"),
 30:(4,"as 26, on the RG2820's bridge humbucker: ladder 6.25 -> 3.40 dB, the coil's load 4.8 kHz; the amplifier after it unchanged. Ben, DI A/B: very, very close"),
 31:(4,"as 26, natural harmonics MEASURED (dataset 2: 90 harmonics over frets 12, 7, 5, 4 and 9 on three guitars): each note takes a touch (2-5) near the nut its coil can hear; the pick, notch, tilt and coil fitted (onset ladder 15.2 -> 8.7 dB); the finger's width damping the upper partials so the note grows purer as it sustains (sustained ladder 19.4 -> 10.5 dB), the fundamental at its measured rate and faster up the neck; and the PLUCK -- the modes the finger kills sounding at their own pitches for ~100 ms, with the pick's click fitted between the partials. Ben, DI A/B: sounds great"),
 32:(4,"Iowa double bass pizzicato, 83 notes: the decay rising with the note, the stretch, the pluck's colour, and a pluck point that rises up each string as the finger shortens it (0.23 of the open string, measured), moved by CC74 from the bridge to the middle. Ben, by ear: so much better"),
 33:(4,"Fraunhofer IDMT-SMT-Bass (CC BY-NC-ND, measured only), DI, three basses on both coils (examples/egtr_fit.py): the string measured (decay 3-25 dB/s, stretch 1.3e-4), fretted, the Jazz pickups and their load (4.9 kHz, shared by every hand), the finger's pluck fitted (ladder 7.68 -> 4.79 dB), and the player's damp measured as its release (0.39 s, where GM sets gave 0.08). Ben: very, very close; the release sounds good"),
 34:(4,"as 33, the pick: ladder 5.56 -> 4.30 dB, its damp 0.36 s"),
 35:(4,"two fretless basses on Freesound (FaireDesVagues' stopped notes, CC BY 3.0; mrforfs' flatwound open strings, CC0): its decay law measured -- the upper partials do NOT go faster than a fretted bass's (the old 4x was a guess) -- and a LOW-PASS at 644 Hz, ~24 dB/oct, where both fall 10-18 dB under a fretted bass (examples/egtr_fit.py --envelope=35; 9.55 -> 1.19 dB). Ben: perfect"),
 36:(4,"as 33, the slap thumb: ladder 10.2 -> 7.9 dB (the rest the string slapping the frets, not modelled), its damp 0.37 s"),
 37:(4,"as 33, the slap pluck: ladder 10.8 -> 6.3 dB, its damp 0.40 s"),
 38:(4,"a Messenger patch: a saw over OSC 2 on 16' (an octave, since a detune beats in the bass), the ladder low and a little resonant"),
 39:(4,"a Messenger patch: a square over the SUB's square, the resonance up and the contour snappier -- hollow and edged where 38 is round"),
 40:(4,"Iowa violin"),
 41:(4,"Iowa viola, fitted across registers"),
 42:(4,"Iowa cello"),
 43:(4,"Iowa double bass"),
 44:(4,"tremolo_bow() on whichever body the register picks, fitted to VSCO 2 CE's violin, viola and cello section tremolos (70 notes): the stroke 11.3 Hz, the players' rates +/-8%, 0.50 depth a player -- what the section sums to, read the same way off the render. CC1 the vibrato, as on Roland's SC-55, whose Tremolo Str is a recording of the stroke. Ben, by ear"),
 45:(4,"Iowa pizzicato for all four instruments, 341 notes: each one's decay, stretch and pluck colour, on the measured bodies. The violin's and viola's decay is two-stage, fast then a faint slow tail (approved by ear). The cello's and bass's pluck points are measured; the violin's and viola's are the fingerboard's end, which Iowa cannot resolve. CC74 moves the pluck from the bridge (127) to the middle of the string (0)"),
 46:(4,"VSCO 2 CE's harp (CC0), 23 plucks E1-F7: plucked at the middle of the string (0.48, measured -- the even partials thinned), the decay rising with the note from 3 dB/s in the bass to 50 at the top, the stretch, a low end the board cannot radiate. CC74 moves the pluck toward the soundboard (pres de la table). Ben, by ear: sounds great"),
 47:(4,"VSCO 2 CE's timpani (CC0), five drums at three stroke layers: the kettle-loaded modes 1 : 1.488 : 1.963 : 2.456 : 2.809, their levels, a stroke that tilts them (a pp timpano nearly a sine, an ff one ringing), and each mode's own decay -- the (2,1) and (3,1) outlast the principal, so the colour shifts as it rings. Renders read back within 0.1 dB at mf. Ben, by ear: sounds great"),
 48:(4,"four MEASURED bodies (Iowa violin/viola/cello/bass) routed per register, each in a section -- and the section itself fitted to VSCO 2 CE's sustained violin, viola and cello sections (75 notes): +/-15 cents of vibrato a player, where 5 left the beating as a slow drift (examples/sect_fit.py). Ben, by ear: sounds great"),
 49:(4,"slow_bow() on the same measured section: the entry a soft section swells in with, read off VSCO 2 CE's soft layers (rise 420-1400 ms, median 660; 1.1 s of attack), where it had taken 170 -- the pad Roland's SlowStr is. Ben, by ear: sounds great"),
 50:(4,"a Messenger patch: the string machine without its chorus -- two saws seven cents apart, the ladder half open, amp and filter swelling together"),
 51:(4,"a Messenger patch: slower and darker than 50, the pair eleven cents apart so it beats faster"),
 52:(4,"FITTED TO VOCALSET'S LONG TONES (CC BY 4.0, measured only; examples/choir_fit.py): 20 conservatory singers, each by the voice type their readme names, every frame's harmonics -- the vibrato sweeps them across the tract. The old \"ah\" was 10 dB short at F2 and 20-30 dB short at 2.4-3.4 kHz, the singer's formant, and so it was against all four GM sets' choirs; weighted rms 11.1 -> 3.2 dB. A woman's whole cluster is weaker (not only the top formant), and a declared countertenor keeps a tenth of it (one singer: an estimate). The section from Dagstuhl ChoirSet's larynx microphones: each singer 14-22 cents off the note, vibrato +/-12 at 4.4-5.5 Hz. The air between the harmonics (51-77 dB under them, in the tract's shape; the room 15-25 dB under that), and EFFORT: +0.23 dB/octave brighter per dB louder, from 109 messa di voce notes. Not modelled: each singer's slow drift (8.5 cents rms under 1 Hz, independent between singers) and the harmonics' level swing under vibrato (under 1 dB at a choir's depth). Ben: sounds great, the wider section even better; the breath and effort, great"),
 53:(4,"as 52, on \"u\": 11.7 -> 3.2 dB; its F3 is a woman's strongest peak up there, which is why the cluster rule covers every formant above F2"),
 54:(4,"two saws on the Messenger, then the class's own sung tract after it -- now the MEASURED sung /E/ (VocalSet, vowels.MEASURED), four formants and the singer's cluster, the tract's measured floor and mouth (it had the spoken three, and a 4 kHz mouth that hid the cluster: 2.4-3.6 kHz +13 dB). Both halves measured. Ben, A/B (examples/synthvoice_ab.py): sounds great"),
 55:(4,"FITTED TO WHAT GM PLAYS (examples/orchhit_fit.py): the patch is the Fairlight-era SAMPLE, one recorded orchestral stab, so the GM sets' own hits are the instrument (FluidR3/MuseScore, GeneralUser GS, TimGM6mb; measured only). A root and its FIFTH (horns re-voiced onto it, winds onto the twelfth), flat across the octaves, a quarter of it noise, short (-20 dB at ~0.3 s; it rang 1.4 s) -- and the PERCUSSION: 55-74% of their power is under 400 Hz, the impact and then the chord's root three and four octaves down, so a TIMPANI on the root (our fitted kettle's own modes, a new pitched layer) and a cymbal above. A/B'd against FluidR3's own hit. Ben: sounds great now"),
 56:(4,"Iowa trumpet, three registers"),
 57:(4,"Iowa tenor and bass trombone, refitted across registers"),
 58:(4,"Iowa tuba"),
 59:(4,"the Iowa trumpet through a MEASURED harmon mute, stem out: VSCO 2 CE's trumpet open and muted at the same pitches, each partial's level muted minus open read as the mute's response. Ben, by ear: sounds fine"),
 60:(4,"Iowa horn, re-measured across four registers and pp/mf/ff"),
 61:(3,"brass_section over three MEASURED bodies (Iowa trumpet/trombone/tuba), five players each, crossfaded across the range handovers -- the hard break moved the spectrum 13.2 dB in one semitone and now moves 2.7"),
 62:(4,"a Messenger patch: the brass stab -- the ladder nearly shut and a filter contour that opens three octaves in 60 ms and falls back: the blat"),
 63:(4,"a Messenger patch: the soft brass -- wider, darker, slower to open, so softer is darker too"),
 64:(4,"Iowa soprano sax"),
 65:(4,"Iowa alto sax"),
 66:(4,"the sax law, measured on soprano and alto and transposed"),
 67:(4,"as 66"),
 68:(4,"Iowa oboe"),
 69:(4,"the conical reed law measured on the oboe; its close relative"),
 70:(4,"Iowa bassoon"),
 71:(4,"Iowa clarinet family -- Bb, Eb and bass, to find one register law"),
 72:(4,"the flute law, measured across bass, alto and concert flute"),
 73:(4,"Iowa flute (nonvib -- vibrato smears the harmonics)"),
 74:(4,"VCSL baroque soprano, alto and tenor recorders (CC0), 38 sustains (examples/wind_fit.py): harmonic to 0.3 cents, odd-dominant (h2 -33, h3 -24), its breath a hiss of its own colour, each harmonic fluttering on its own and the whole tone and pitch wavering with the breath; attack and release fitted. Ben: sounds great"),
 75:(4,"Freesound pan pipes (mrshoes CC BY 3.0, j008b and PanPiper5 CC0), 35 notes (examples/wind_fit.py --fit=tables): closed but not odd-only -- the evens 14 dB under the odds; harmonic, not the stopped rank's stretch; quiet breath (-64 to -70 dB) of its own colour; the bass pipe's D3 its own low-register tables, breathier and rich to h48. Ben: sounds good"),
 76:(4,"Freesound blown bottles, 18 notes (examples/wind_fit.py): near-pure, a measured series and breath, the breath wavering slowly. Ben: sounds good"),
 77:(4,"Freesound shakuhachi (UncleSigmund CC BY 3.0, gonzooka CC0), 49 notes (examples/wind_fit.py --fit=tables): two tones by register -- the low breathy and buzzy to h40, the high near-pure -- each harmonic fluttering on its own and a 2.5 dB shared waver (a locked 8 dB swell was a fog horn); meri/kari not modelled. Ben: sounds good"),
 78:(4,"CATEGORY CORRECTION: a human whistle is a Helmholtz resonator, not a pipe. Freesound whistling (nbild, oscarboyle CC0), 9 notes (examples/wind_fit.py --fit=tables): h2 -43, h3 -57, its breath measured under the tone as well as between the harmonics. Ben: sounds good"),
 79:(4,"VCSL typical and small ocarinas (CC0), 21 sustains (examples/wind_fit.py): near-pure (h2 -44), its breath, flutter, shared wobble (2.4 dB) and pitch wander (5.6 cents) fitted, a soft chiff. Ben: sounds great"),
 80:(4,"a Messenger patch: a square with the SUB's square an octave under -- the weight a square lead has on a Moog and not on a chip"),
 81:(4,"a Messenger patch: the sawtooth lead as a Moog player sets it"),
 82:(4,"a Messenger patch: the calliope, a steam whistle -- two triangles an octave apart, the ladder wide open. The GM name misleads; the patch does not"),
 83:(4,"a Messenger patch: the NOISE oscillator through the same ladder as the saw, so the breath chuffs as the contour snaps open"),
 84:(3,"two saws on the Messenger and THEN the valve the electric guitars use -- the hardware's order. The Messenger is measured; the amp is the guitars' own model"),
 85:(4,"two saws and a slow breath on the Messenger, sung through the class's open /a/ after it -- now the MEASURED sung /a/ (VocalSet, vowels.py), with the tract's measured mouth; the Messenger and the vowel both measured. Ben, A/B (examples/synthvoice_ab.py): sounds great"),
 86:(4,"a Messenger patch: OSC 2 FREQ fully up, a tempered fifth -- where the knob's travel ends"),
 87:(4,"a Messenger patch: OSC 2 on 16', the bass and the lead from one key, more resonance and a shorter contour for the punch"),
 104:(4,"Freesound sitars: a Ma string struck four times (CC0) and chinpen's D4 strokes (CC BY 3.0) (examples/pluck_fit.py): the decay law and its register slope on both; the gourd by absolute frequency, the jawari as the body falling away under a buzz that is there at once and rises quickly (a short banded late copy), each partial its own phase, a 1.5 ms onset -- all on the Ma take, chinpen's sitar having no growing buzz. Its sympathetic strings tuned on Sa; Indian intonation as a secondary tuning (ragas.py: just, Pythagorean, equal, Bel's Todi, 27 ragas measured from Saraga) and a meend that locks the wheel to the raga's swaras. Ben: sounds great"),
 105:(4,"the Windsor banjo SoundFont's open-string plucks (public domain; examples/pluck_fit.py --voice=banjo): decay law and register slope, the head's colour by absolute frequency (it radiates down to 100 Hz, not the 380 asserted), the head's own brief modes 190-1480 Hz for the hollow knock, the other open-G strings ringing in sympathy ~36 dB under; a note-off damps it in 0.35 s (the short GM sets'; Roland publishes none). Ben: sounds great"),
 106:(3,"RTB45's Ueno festival take (freesound 195521, CC BY 4.0), its 14 plucks that ring alone, 0.3-0.7 s (examples/pluck_fit.py --voice=shamisen): no comb notch (the bachi fills it), silk's near-harmonic series (it had the banjo's steel), bright to 13.6 kHz, the bachi's knock a two-stage decay, its colour by absolute frequency; the other open strings kicked through the skin in niagari on C#3, the sawari string loudest, unmoved by the wheel. One string at two pitches, the ring past 0.7 s and the sawari's buzz unmeasured. Ben: sounds good"),
 107:(4,"VCSL Dan Tranh (CC0), its nearest recorded cousin (examples/koto_fit.py): decay laws, pluck point, the box's low cut (450 Hz measured), the tsume's strike; the other twelve strings ringing in sympathy at the measured level and decays, in hirajoshi, tuned through the tuner. Silk inharmonicity kept. Ben: sounds fine"),
 108:(4,"VCSL kalimba (CC0, examples/kalimba_fit.py): measured tine modes 1 : 2 : 6.4, the other tines ringing sympathetically at their own pitches and decays, the thumb's strike. Ben: great"),
 109:(4,"Freesound IowaSpaceWizard chanter, its nine notes, and the drones (CC0) with iainmccurdy's (CC BY 4.0) (examples/wind_fit.py --voice=bagpipe): the chanter a CONE (it sat on the organ's stopped pipe, evens 100 dB down), its colour by absolute frequency, its measured scale (Low G -228, the D 18 sharp), reed noise climbing the chanter, each harmonic its own phase and flutter, a 32 ms attack with no reed-organ rush; the drones their OWN voices -- tenor, tenor, bass, CC1 corking them -- split from the mixture by pitch (the bass's evens are not weak), a struck-in swell set by velocity; a slur ends the note it leaves. Ben: perfect"),
 110:(4,"the measured violin, given solo treatment"),
 111:(3,"by PROXY: cdrk's Turkish zurna (freesound 18661, CC BY 4.0; no open shehnai recording), G4 and E5 (examples/wind_fit.py --voice=shanai, examples/shanai_ab.py): a cone seeded from the fitted chanter, its colour by absolute frequency, its reed hiss between the harmonics, a tongued 16 ms onset. Checked against the GM sets' shehnai samples (examples/gm_samples.py 111), which agree on the weak fundamental and not on the zurna's fading upper one, so that was left out. Ben: sounds good"),
 112:(4,"Iowa crotales, 25 pitches"),
 113:(4,"VSCO-2 CE (CC0) agogo bells 2 and 3, played as a melodic instrument: the high bell above note 82, the low below, each fitted stroke carrying its band colour with the note. Ben: sounds good"),
 114:(4,"built from the instrument's design, then corrected against Freesound 742254"),
 115:(4,"Iowa woodblocks"),
 116:(4,"VSCO-2 CE (CC0) giant drum struck with sticks, as a taiko with bachi: 28 measured modes as ratios to the played note, its colour moving with it (PlayedAtPitchMixin). Fitted on the first 250 ms with the strike dying as a stick's does -- the takes' late energy is their room. Ben: sounds great"),
 117:(4,"DRSKit's two toms, measured, by register: the floor tom under G2, the rack tom from G2 up. A melodic tom part is a set of drums, not one drum retuned"),
 118:(4,"a Messenger patch: the drum machine's tom as an analog synth makes it -- the MOD section's F ENV on OSC 2's pitch (measured: linear, +-5 octaves)"),
 119:(4,"the fitted crash (Iowa's modes, refitted to DRSKit) PLAYED BACKWARDS, literally: every partial emitted time-reversed -- each decay a growth at its own rate, each phase mirrored so the modes arrive together as they set out, the strike's wash a swell before the arrival. Against the forward crash flipped, 0.4 dB rms in every band (examples/reverse_check.py). It was one shared swell over the modes; Ben: sounds great"),
 120:(3,"its own class -- slide, squeak and position shift; reworked against Ben's ear"),
 121:(4,"FITTED TO TWO TAKES OF BREATHING (Freesound, CC0; examples/breath_fit.py): a breath has no pitch, so no series -- it had been 64 partials at the key dithered into noise, its colour following the key, brightest at 16 kHz -- but a noise table of the breaths' own colour from 250 Hz up (under it the takes are the breath on the microphone), held for the note and swelling in. Roland's tone here is 'Fl. Keyclick' (SC-55 p.67); this follows GM's name. Ben: good"),
 122:(3,"BY PROXY: VCSL's ocean drum (CC0, examples/seashore_fit.py), the instrument that imitates the surf, not the sea: a hiss of its measured colour on its slow irregular swell, and the beads' ticks above 8 kHz one by one. Ben: sounds great"),
 123:(4,"FITTED TO THREE BIRDS (Freesound, CC0; examples/bird_fit.py): the chirp FALLS -- house sparrows' cheeps drop ~900-1300 cents in 100-140 ms, a white-crowned sparrow's trill notes 150-600 cents, 68-120 ms apart -- where the class had it rising a major third; four chirps at the trill's spacing, each gone before the next, nearly pure (h2 -30 dB, h3 -40). GS has one Bird tone (SC-55 p.68). Ben: sounds fine"),
 124:(4,"FITTED TO BELL TELEPHONES (Freesound, CC0; examples/phone_fit.py): TRP's two gongs struck one at a time, a Stromberg-Carlson and a Western Electric ringing -- the Bell System's pair in all three, 437 cents apart (the class had them 9), each a dome's modes with its own decay, levels to the ringing phones within ~1 dB; one clapper striking each gong 20 times a second (the ringing current), the other between, LOOSELY -- each stroke its own offset (~5 ms), phase and level, where a grid locked the dings (Ben); ringing on ~24 dB/s after the burst. Ben: sounds good"),
 125:(4,"FITTED TO THREE PASSES (Freesound, CC0; examples/heli_fit.py): the blade passes' harmonics from 80 Hz to ~5 kHz (300 of them) with the rotor's wash under them as noise rows, together within 0.7 dB rms an octave, and the chop 11.0 dB against the passes' 11.2 -- a bare saw had put its energy under 40 Hz, nothing past 1 kHz, a 35 dB chop. The note picks the rotor (four octaves down). Ben: sounds good"),
 126:(4,"FITTED TO THREE AUDIENCES (Freesound, CC0; examples/applause_fit.py): CLAPS, the hand clap's own noise burst (GM 39's, fitted) fired ~274 times a second through the note at levels within 13 dB -- every octave 125 Hz-16 kHz within 1 dB, the 5 ms level's swing 3.3 dB sd as theirs (a wash's 0.8). Damped-sine grains were tried and pinged ('seashore drips'). Heard in the hall against crisper and wider-spread variants: the fitted kept (Ben)"),
 127:(4,"an N-wave whose length the key sets, standing back at 127's distance with the room its tail; and FITTED (examples/gunshot_fit.py) to a 9 mm at 15 m (Freesound, CC0): the blast's own noise beside the N-wave, which alone fell ~6 dB an octave where the shot falls ~3 -- every octave of the first 20 ms within 1 dB but 125 Hz, the 5-20 ms boom -3.5 dB against -3.8. Heard in the hall. Ben: sounds good"),
}
for p in range(88, 104):
    RATED[p] = (1, "one BowedStringProperties serves all sixteen pads and FX")
# ...and 88-95 no longer do. GM's own names point at eight MECHANISMS, and each
# class has one the others do not; see tonelib.SynthPadProperties. 96-103 are
# still the shared voice.
RATED.update({
 88:(4,"TWO Messengers on one key (a layered voice): a pad of two saws under a low ladder and an FM bell over it. Ben: \"sounds amazing\""),
 89:(4,"a Messenger patch: two saws under a low ladder, a slow swell and a long release -- the pad you put underneath something"),
 90:(4,"a Messenger patch: open, a quick front and a contour that settles, so chords articulate a rhythm"),
 91:(4,"two saws and a swell on the Messenger, then the class's three vocal formants (its /O/) -- now /O/ on the measured /o/'s widths, levels and singer's cluster, widened x1.5 for a section (VocalSet, vowels.py), with the tract's measured mouth; the Messenger and the vowel both measured. Ben, A/B (examples/synthvoice_ab.py): sounds great"),
 92:(4,"a Messenger patch: bowed glass as a resonance excited slowly -- the ladder in BAND PASS (measured: 7.6 dB under the low-passes), tracking the key"),
 93:(4,"a Messenger patch: 1 -> 2 FM, the carrier a few cents off a whole ratio, so the sidebands land in pairs. The FM index is measured to 0.65, where this sits"),
 94:(4,"a Messenger patch: two squares six cents apart and a little of the NOISE oscillator through the same ladder -- the air the name means"),
 95:(4,"a Messenger patch: the sweep BOTH ways -- LFO 1 a slow triangle on the resonant cutoff, the rising half the additive pad could not make"),
 96:(3,"the crystal's FM bell (98) short and bright, through the MF-104M on SHORT. The Messenger is measured; the pedal is modelled, not recorded"),
 97:(4,"a Messenger patch: the longest swell and the widest pair (fourteen cents), a slower, shallower LFO on the cutoff -- width and drift"),
 98:(4,"a Messenger patch: an FM bell -- the carrier 2 sqrt(2) x the key, a strong partial ON the key and inharmonic ones over it"),
 99:(4,"a Messenger patch: a saw and the NOISE oscillator through the same ladder, so the breath is filtered with the tone and swells with it"),
 100:(4,"a Messenger patch: the hard front on an open ladder -- plain subtractive"),
 101:(4,"a Messenger patch: dark and wobbling -- the class's deep slow vibrato, and LFO 1 drifting OSC 2 alone, so the two slide against each other"),
 102:(3,"\"Echo Drops\": a plucky pair of saws on the Messenger through the MF-104M. The Messenger is measured; the pedal is modelled, not recorded"),
 103:(4,"a Messenger patch: two squares, LFO 1 working OSC 1's waveshape (pulse-width modulation) and a deep resonant contour"),
})

# ---- channel 10, the percussion note map --------------------------------
# Iowa's percussion pages carry cymbals, crotales and hand percussion -- and NO
# DRUM KIT AT ALL: no snare, no bass drum, no toms, which is 9630 of the
# collection's 12781 percussion notes. DrumGizmo's DRSKit (CC-BY 4.0) fills
# the kick, the snare, the toms, and the crashes struck the way a kit drummer
# strikes them; the classes that have no reference say so themselves.
PERC_RATED = {
 27:(3,"GS's High Q, the SFX set's 39 (SfxHighQ): the 808 engine's resonator snapped down 5 octaves, fitted to GeneralUser GS's own sample's track -- stepped: the renderer holds a pitch a 11.6 ms block, and the sweep falls 4.5 octaves in 45 ms"),
 28:(4,"GS's Slap, the SFX set's 40: a palm slap, fitted to Freesound slaps (CC0, examples/perc_fit.py sfx_slap)"),
 29:(4,"GS's Scratch Push, the SFX set's 41: a turntable's groove (Freesound, CC0), its colour bending up a fifth"),
 30:(4,"GS's Scratch Pull, the SFX set's 42: the groove bending down from a fifth"),
 31:(4,"GS's Sticks, the SFX set's 43: two drumsticks clicked (Freesound, CC0; perc_fit sfx_sticks)"),
 32:(3,"GS's Square Click, the SFX set's 44: the 808 engine's click alone, fitted to GeneralUser GS's sample (examples/sfx808_fit.py) -- a synth sound, its sample the reference"),
 33:(4,"GS's Metronome Click, the SFX set's 45: Ben's own Wittner, recorded through his A6 (perc_fit sfx_metronome), as the SFX set's 45"),
 34:(4,"GS's Metronome Bell, the SFX set's 46: Ben's own Wittner's bell, with 33's tick struck under it (percussion_map.KIT_LAYER), as the SFX set's 46"),
 35:(4,"DRSKit's kick (DrumGizmo, CC-BY 4.0), 29 strokes on its two close mics: eleven measured modes, damped like a pillowed kick (head modes 40-130 dB/s, fitted by BAND so two modes 7% apart are not each read twice), a stroke-scaled glide of 150-350 cents, the beater's click. Two semitones under 36, at 39.4 Hz. Ben, by ear: sounds deeper"),
 36:(4,"as 35, at the recorded kick's own 44.4 Hz"),
 37:(4,"DRSKit's cross-stick, fitted as the measured snare struck on the rim: its head under the stick, the rim's click at 1.05 and 1.93 kHz, wires that die faster. Level by ear, 3 dB under the snare (the recorded 20.6 left it buried under the kick)"),
 38:(4,"DRSKit's snare (29 strokes, top and bottom mics): the head at 196 Hz with a tom's modes, choked in 50 ms; the wires a buzz of jittered noise in third-octave bands, fitted on band, onset balance and flatness (a chord of sines at the right band levels was not a snare; neither was a comb in phase -- \"pew pew\"). Needed the renderer's onsets to start on their own sample. Ben, by ear: sounds so much better"),
 39:(4,"VCSL claps (CC0, examples/clap_fit.py): an ensemble -- seven hands flammed over 65 ms, each a fitted noise burst. Ben: sounds great"),
 40:(4,"Roland's SNARE DRUM 2 (SC-55 p.70), a second acoustic snare: VCSL's Modern 1 (CC0), wires on, ten hits over 30 dB on a stereo pair (examples/snare_fit.py --vcsl). Its own head -- lowest mode 192.5 Hz, the loudest 435 -- and stick burst; 8.3 -> 6.9 dB. 2.5 dB under 38, where three GM sets keep theirs. The drum machine's snare is the Electronic set's"),
 41:(4,"DRSKit's floor tom, 30 strokes on its close mic: modes 1 : 1.631 : 2.012 : 2.349 : 2.971, a long ring (the fundamental 13 dB/s, about 2.5 s), a two-stage decay, the stick's click, a glide that grows with the stroke. Ben, by ear"),
 42:(4,"REFIT TO A KIT DRUMMER'S: DrumGizmo DRSKit's closed hats (24 strokes, CC-BY, measured only; examples/crash_fit.py --hats) on the plate measured on Iowa's -- a short bright tick, nearly all strike, 7.75 -> 4.91 dB over the grid; Iowa's were a percussionist's, darker, a stand's thump under them. Set by its SIZZLE (4-16 kHz re the snare) where GeneralUser GS has its hat. Ben: \"The new hats sound much better\""),
 43:(4,"as 41, higher"),
 44:(4,"Iowa hi-hat, foot-close take (DRSKit has no pedal take) -- its stand's thump under 2 kHz cut to the refitted closed hat's share, set by its sizzle where GeneralUser GS has its pedal hat. Ben: \"The new hats sound much better\""),
 45:(4,"DRSKit's rack tom, 27 strokes on its close mic: modes 1 : 1.477 : 1.755 : 2.259, the stick's click 30-60 dB under the fundamental to 6 kHz, a glide that grows with the stroke. Ben, by ear"),
 46:(4,"REFIT TO A KIT DRUMMER'S: DRSKit's open hats (18 strokes; examples/crash_fit.py --hats), 5.84 -> 3.37 dB; set by its sizzle where GeneralUser GS has it -- 13.5 dB up: the quiet hat Ben had heard all along. Ben: \"The new hats sound much better\""),
 47:(4,"as 45, higher"),
 48:(4,"as 45, higher"),
 49:(4,"Iowa 17\" suspended crash for the modes, refitted to DRSKit's left crash hit HARD with the stick's shank (11 strokes over 37 dB): the cascade's swell of 2-8 kHz after the strike, scattered (in order it glided), growing with the stroke; a slow ring at its own 8.5 dB/s; the shank's thud. Ben, by ear: sounds great"),
 50:(4,"as 45, higher"),
 51:(4,"Iowa 21\" ride, bow"),
 52:(4,"Iowa chinese, 16/19/20\""),
 53:(4,"Iowa ride bell -- the ping is mode 8.1, not the fundamental"),
 54:(4,"Iowa's tambourines, fitted: 77 measured jingle modes in four clusters, the hand's slap on the head, and each stroke catching the jingles differently (alike, a run of strokes rang metallic)"),
 55:(4,"Iowa splash"),
 56:(4,"VSCO-2 CE (CC0) cowbell, fitted: 28 measured modes each at its own rate, clean; the strike dense and noisy from 400 Hz, its attack contrast matched. Ben: better than the first fit, which was jittery and modal"),
 57:(4,"Iowa 18\" suspended crash for the modes, refitted to DRSKit's right crash hit hard (12 shank strokes), as 49. Ben, by ear: sounds good"),
 58:(4,"VSCO-2 CE (CC0) vibraslap: the rod's swing at 27.4 Hz striking both sides, the far one dropping out as the swing dies (the roll slowing, 55 strikes a second to 27); the pins' clatter as strike noise, within 1 dB of the takes from 900 Hz up. Score 2.34 (was 2.72). Ben: sounds great now"),
 59:(4,"GM wants two rides and Iowa has one; this is that measurement on a larger plate"),
 60:(4,"VSCO-2 CE (CC0) high bongo (161 Hz), fitted: measured modes ringing clean, the slap a dense noisy strike, strokes varying as the takes do"),
 61:(4,"as 60, the low bongo (142 Hz)"), 62:(4,"VSCO-2 CE (CC0) quinto tapped: the high conga muted"), 63:(4,"VSCO-2 CE (CC0) quinto open (216 Hz), 13 measured modes -- one left out, the glide smeared into a peak that beat at 16 Hz"), 64:(4,"VSCO-2 CE (CC0) conga, the middle of its three (164 Hz), open at three dynamics"),
 65:(4,"hello_flowers' timbales (freesound 41196, CC0), the high drum's ten free strokes cut from 50 hits (examples/freesound_slice.py): 46 measured modes ringing to 3.8 kHz, 224 Hz; fitted to 5.1 dB. The strike dense, jittered and SCATTERED in its bands (click_scatter): on an even grid its partials beat in a sweep -- Ben: \"a phaser in the initial attack\""), 66:(4,"as 65, the low drum's nine (186 Hz, 33 modes), fitted to 6.3 dB"),
 67:(4,"VSCO-2 CE (CC0) agogo bell 2 (1228 Hz), fitted: measured modes, per-stroke scatter from the takes"),
 68:(4,"VSCO-2 CE (CC0) agogo bell 3 (696 Hz), as 67"),
 69:(4,"VSCO-2 CE (CC0) cabasa as SHAPED NOISE: measured, a twist is noise (its grain is its own spectrum with random phases), so the recording's third-octave spectrum as noise rows under the fitted swell, shake and 0.33 s settle -- colour within 0.3 dB, envelope 3.0. The impact burst before it clicked where the takes do not. Ben: sounds great"),
 70:(4,"VSCO-2 CE (CC0) maracas as SHAPED NOISE, fitted to the SINGLE strokes (two of the five files are two strokes, one three): the recording's spectrum as noise rows, a swell, the shake, a 0.29 s settle falling 40 dB -- colour within 0.8 dB but for the gourd's 2.3 kHz cliff, envelope 3.2. A little seed-click grain above 4 kHz is the recording's and not ours. Ben: sounds great"),
 71:(4,"VCSL ball whistle, short blast (CC0, examples/whistle_fit.py): one tone at 2.7 kHz, the pea swinging it 144 cents at 40 Hz and chopping it, a 0.19 s blast; the air above the tone only. Ben: sounds good"),
 72:(4,"as 71, the long blast (0.89 s, 80 cents at 30 Hz)"),
 73:(4,"Iowa guiro, both directions, fitted (examples/perc_fit.py guiro): 44 ridges over 0.19 s, each ringing 16 ms (the hand deadens it) as shaped strike noise, the scrape's level swelling to the flick as the takes' (PERCUSSION_RASP_SHAPE); dry, the takes' echo and rumble left to the room. Score 3.9 (was 10.7). Ben: sounds great"),
 74:(4,"as 73, the long scrape"),
 75:(4,"Iowa claves, three pairs"),
 76:(4,"Iowa woodblocks, four sizes"),
 77:(4,"as 76, the low block"),
 78:(4,"reinsamba's cuica (freesound pack 1339, CC-BY), the high takes: a squeak WHOOPING UP ~700 cents into ~790 Hz in 0.15 s, its own measured spectrum (h2 -23, h3 -21 dB), a one-shot gesture as every GM set plays it"),
 79:(4,"the FRICTION drum, on reinsamba's 13 close, dry takes (freesound pack 1339, CC-BY): rubbed UP into ~355 Hz from ~305, a 0.15 s gesture (gated: a one-tick note sounds), nearly a sine (h2 -14, h3 -27 dB) -- read first off a stairwell's takes, which had smeared it bright; at the GM sets' level against the snare"),
 80:(4,"Iowa triangles, 6\" and 8\""),
 81:(4,"as 80, undamped"),
 84:(4,"the measured crotales, cascaded -- 22 of them over 30 units"),
 85:(4,"Iowa castanets"),
 86:(4,"as 87, the hand: the takes' muted strokes ring as the open ones for 0.2 s, then fall 25-30 dB in 40-60 ms (read in the head's own band) -- the open drum gated; the softer strike fitted, 2.1 dB"),
 87:(4,"plotzki's samba surdo (freesound 36127, CC0), its open strokes: 21 modes from 66.7 Hz (a 40-49 Hz hump left out), fitted to 0.4 s -- the take's other drum rings past it -- 8.4 -> 3.2 dB"),
}

FAMILY = [(0,"Piano"),(8,"Chromatic Percussion"),(16,"Organ"),(24,"Guitar"),(32,"Bass"),
          (40,"Strings"),(48,"Ensemble"),(56,"Brass"),(64,"Reed"),(72,"Pipe"),
          (80,"Synth Lead"),(88,"Synth Pad"),(96,"Synth Effects"),(104,"Ethnic"),
          (112,"Percussive"),(120,"Sound Effects")]
LEVEL = {0:"nothing", 1:"general class", 2:"specific, theory",
         3:"specific, theory + ear", 4:"specific, validated against a target"}


def _class_name(p):
    """What program p actually renders as -- asked of the ROUTER, not the map.

    This column used to read `patch_map.property_class_for_program`, which is
    the no-note FALLBACK. Several programs are a FAMILY and are routed per note:
    the bowed and pizzicato ensembles, the brass section, and the solo winds
    whose bottom octave is a different instrument. For all of those the fallback
    is one member of the family, so the doc reported GM 61 as `Trombone` and
    called it a 1 -- "the trombone stands in for the whole section" -- when the
    code had routed it to trumpet, trombone and tuba sections for some time.

    The same mistake GM 32 and GM 44 both punished in the renderer, made here in
    the thing that is supposed to report on it. Ask the router.
    """
    # Probe every band a split can carve: BOWED_SPLIT breaks at 36/48/60 and
    # BRASS_SPLIT at 40/60, so sampling only low/middle/high missed the viola
    # and the trombone and reported a four-way split as a two-way one.
    names = []
    for c in (patch_map.property_class_for_note(p, n)
              for n in (30, 38, 44, 54, 64, 84)):
        n = c.__name__.replace("Properties", "")
        # A blended or sectioned class is named for what it is made of.
        for suffix in ("Section", "Tremolo", "Pizz"):
            n = n.replace(suffix, "")
        # a crossfade sits between two, named AToB -- split only there: a
        # bare "To" also starts TomTom and ends HonkyTonk, and splitting on
        # it named GM 117 " by register" and GM 3 "Honky"
        n = re.split(r"(?<=[a-z])To(?=[A-Z])", n)[0]
        if n and n not in names:
            names.append(n)
    if len(names) == 1:
        return names[0]
    return "/".join(names) + " by register"


def percussion_table():
    """Channel 10. A separate specification from the 128 programs, and the place
    where the reference corpus divides most sharply."""
    import percussion_map as PM
    L = ["## Channel 10: the percussion note map\n"]
    ph = {k: 0 for k in range(5)}
    for n in PERC_RATED:
        ph[PERC_RATED[n][0]] += 1
    tot = len(PERC_RATED)
    L.append("%d notes: GM's 35 to 81, GS's 25 and 82-87, and the SC-88 Pro's kicks and snares on 0-16"
             % tot)
    L.append("and 97-122. Iowa's percussion pages carry cymbals, crotales and")
    L.append("hand percussion and **no drum kit at all** -- no snare, no bass drum, no")
    L.append("toms, which is 9630 of that collection's 12781 percussion notes. DrumGizmo's")
    L.append("DRSKit (CC-BY 4.0), a recorded kit, fills the kick, the snare, the toms and")
    L.append("the crashes hit hard; VSCO-2 CE and VCSL (CC0) the hand percussion, the")
    L.append("claps, the whistles and the second snare; Freesound takes the timbales, the")
    L.append("surdo (CC0) and the cuica (reinsamba, CC-BY).\n")
    L.append("| rating | notes | share |")
    L.append("|---|---|---|")
    for k in range(5):
        if ph[k]:
            L.append("| %d %s | %d | %d%% |" % (k, LEVEL[k], ph[k], round(100 * ph[k] / tot)))
    L.append("")
    L.append("| # | note | class | | notes |")
    L.append("|---|---|---|---|---|")
    for n in sorted(PERC_RATED):
        name, cls = PM.PERCUSSION[n][0], PM.PERCUSSION[n][1].__name__
        r, note = PERC_RATED[n]
        L.append("| %d | %s | `%s` | **%d** | %s |"
                 % (n, name, cls.replace("Properties", ""), r, note))
    L.append("")
    return "\n".join(L)


# ---- drum sets: the program on a drum channel ----------------------------------
# Only the notes a set CHANGES; every other note is Standard's, rated above. The
# contents are the SC-55 owner's manual's drum set table (p.70-71); the sounds
# are theory, and their level and length are matched to the Standard note each
# replaces (examples/drumset_check.py). No reference audio exists for most of
# them. Ben's ear has had its turn on what he heard -- all of Brush, and the
# one Electronic note thememat plays -- which is 3; the rest stay at 2. The
# Electronic set is a SIMMONS SDS-V on its own engine (simmons.py), its
# patches fitted to a real Simmons's hits chosen by GeneralUser's (two levels,
# examples/elkit_fit.py), and Ben has heard it: 4. The TR-808 the same way
# on its own engine (tr808.py), fitted to Michael Fischer's recordings of a
# real 808 (examples/tr808_fit.py; scores: dB rms over a time x third-octave
# grid plus the hit's band balance), and heard: 4. The Orchestra set too: its
# concert drums and clashes fitted to VCSL (examples/orch_fit.py), the rest
# Standard's fitted voices moved, and heard: 4. Brush too, fitted to Swirly
# Drums (examples/snare_fit.py --brush, brush_fit.py), and heard: 4. Room and
# Power: Standard's fitted drums in a live room of their own, its size fitted to
# GeneralUser's (examples/roomset_fit.py), and heard: 4. SFX: built in
# batches, its unbuilt keys silent (KIT_ONLY); what is built, heard: 4.
_808 = ("THE ROLAND TR-808, AS AN ENGINE (tr808.py: its two kinds of circuit as partials -- "
        "bridged-T resonators, and six square oscillators through band-passes -- every "
        "instrument a patch of knobs, read off the service notes' schematic where it fixes "
        "them). FITTED BY TWO LEVELS to Michael Fischer's recordings of one 808 (every knob "
        "at five positions): the GM set whose sample IS an 808 picks the setting, the patch "
        "fits that hit (examples/tr808_fit.py). Balanced within itself as GeneralUser's "
        "(examples/elkit_balance.py --kit=25). Ben: sounds incredible")
KIT_RATED = {
    24: {
        36: (4, "THE SIMMONS SDS-V, AS AN ENGINE (simmons.py: the circuit as partials, every drum a patch of knobs, as the synths are Messenger patches): its bass drum module FITTED BY TWO LEVELS -- GeneralUser GS's Elec BD picks the closest of tarane468's real Simmons hits (Freesound, CC0; hit 30), and the patch is fitted to that hit at its pitch, 28 Hz (examples/elkit_fit.py --select, --fit=skick --real). The bend falls evenly in pitch (the kernel's log sweep). Ben: sounds great -- the vintage sound is the point"),
        38: (4, "the SDS-V's snare module on the same engine: one oscillator near 450 Hz under its noise, fitted to the real Simmons snare GeneralUser's is closest to (hit 36), score 7.6 -- its decay within a few ms of the hit's. The two-tone snare fitted to GeneralUser itself stays in the code (ElectronicSnareProperties)"),
        40: (4, "an acoustic snare behind a GATE, fitted to GeneralUser GS (examples/elkit_fit.py --fit=gated, and its envelope to the gate within 3.8 dB rms): a loud room falling into a 0.40 s gate, tuned to 290 Hz. Ben: good"),
        41: (4, "the SDS-V's tom modules: one patch, each tom its own TONE and DECAY, the bend following the strike and the noise filter darkening with it; fitted to the real Simmons's NOISY toms GeneralUser's are closest to (hits 31, 35), each tom at GeneralUser's tuning, ringing out ungated as a Simmons does. The kit balanced within itself as GeneralUser's (examples/elkit_balance.py). Ben: sounds great"),
        43: (4, "as 41"), 45: (4, "as 41"), 47: (4, "as 41"), 48: (4, "as 41"), 50: (4, "as 41"),
        52: (4, "GM 119's reverse cymbal: the fitted crash played backwards, arriving on the written note-off"),
    },
    25: {
        36: (4, _808 + ". The BASS DRUM: one network at 49.6 Hz, its first cycle at 4x (the time "
             "constant halved while the trigger lasts), the pitch sighing 0.5 oct onto it; its "
             "spectrum within 1-3 dB of the hit's to 8 kHz. Score 4.5 (BD0050)"),
        37: (4, "the RIM SHOT: two networks into the SWING VCA (a transistor conducting on one "
             "polarity: their harmonics and intermodulation, each product decaying as the "
             "networks' mix changes), out through Q63's resonant high-pass (590 Hz, Q 2.9). "
             "Score 15.2 -- the rectifier's sharp 3-12 kHz edge is short"),
        38: (4, "the SNARE: two networks near an octave apart and SNAPPY, high-passed noise on "
             "its own envelope. Score 5.2 (SD7575)"),
        41: (4, "the LOW TOM: diodes D80/D81 conduct with the ring, so the pitch falls as it "
             "decays and their harmonics die faster; pink noise at 154-402 Hz on its own "
             "envelope (the schematic's RCs). Score 5.0 (LT75)"),
        43: (4, "as 41, played 2.8 semitones higher -- the SC-55's sixth tom where FluidR3 "
             "plays it, past the TUNING knob's reach"),
        45: (4, "the MID TOM, its own circuit: noise 219-482 Hz. Score 5.3 (MT50)"),
        47: (4, "as 45, 2 semitones higher (as 43)"),
        48: (4, "the HI TOM, its own circuit: noise 268-723 Hz. Score 6.7 (HT75)"),
        50: (4, "as 48, 3.5 semitones higher (as 43)"),
        42: (4, "the CLOSED HAT: the six oscillators (this 808's, read off its cymbal: 345.5, "
             "486.2, 558.5, 630.6, 823.9, 852.0 Hz -- pulses, not squares) through the high "
             "band, a short VCA and a high-pass. Score 5.8"),
        44: (4, "as 42 (the SC-55's pedal hat is the 808's CHH)"),
        46: (4, "the OPEN HAT: the same band, a longer VCA, choked by 42/44. Score 8.3 (OH75)"),
        49: (4, "the CYMBAL: the six through three bands at the circuit's centres (Werner's "
             "cymbal paper), each its own decay -- the kernel's two-stage decay per partial. "
             "Score 7.1 (CY7500)"),
        56: (4, "the COWBELL: two of the six through a band-pass, an abrupt drop into a tail. "
             "Score 10.7"),
        62: (4, "the HIGH CONGA: the tom circuit with a capacitor switched out -- higher, no "
             "noise. Score 9.3 (HC50)"),
        63: (4, "the MID CONGA. Score 2.8 (MC25)"),
        64: (4, "the LOW CONGA. Score 2.9 (LC25)"),
        70: (4, "the MARACAS: white noise through Q68's 1 kHz RC and 10.6 kHz Sallen-Key (Q 2.3), "
             "a gate that swells, holds and cuts. Score 10.0"),
        75: (4, "the CLAVES: one network at 2.42 kHz. Score 13.4"),
    },
    32: {
        36: (4, "JAZZ KICK 1: the ~71 Hz drum of soneproject's kit in a jazz bar (Freesound 25895, CC0): "
             "its modes measured, its strike fitted (examples/perc_fit.py jazz_kick1, 8.4 -> 7.9 dB; the takes "
             "a Zoom H1 out in the room, so the score is the room's as much as the drum's). Ben: the Jazz set sounds great"),
        35: (4, "JAZZ KICK 2: the kit's ~47 Hz tuning: its modes measured, the Standard kick's strike (fitted "
             "whole to the room-laden takes, the click ran to +53 dB and the trims to +31/-25)"),
        38: (4, "JAZZ SNARE 1: the kit's bright snare, 251 Hz on top, the wires ~15 dB under the body: "
             "modes, strike and noise fitted (7.2 -> 4.3 dB)"),
        40: (4, "JAZZ SNARE 2: the same snare darker, 174 Hz on top: its modes measured, Snare 1's strike with "
             "the wires 7.5 dB lower (the takes' difference). Also the SC-88 Pro's Standard key 106"),
    },
    27: {
        36: (4, "CR-78 KICK 1: a bridged-T at 59 Hz, fitted to Bjornmossa's real CR-78 (CC BY; "
             "examples/cr78_fit.py). Score 4.3. Ben: sounds good"),
        35: (4, "CR-78 KICK 2: the kick, its first cycles' third harmonic (~178 Hz) up. Score 14.2"),
        37: (4, "CR-78 RIM SHOT: a ring at 1.43 kHz, gone in 5 ms (his 'clave_2'). Score 16.0"),
        38: (4, "CR-78 SNARE 1: a bridged-T at 307 Hz and its noise above 3.9 kHz. Score 11.7"),
        40: (4, "CR-78 SNARE 2: a second take, its noise lower. Score 11.9"),
        41: (4, "the CR-78's one tom (176 Hz) six semitones down: its six toms are it at six "
             "pitches, two apart"),
        43: (4, "as 47, four semitones down"), 45: (4, "as 47, two semitones down"),
        47: (4, "CR-78 TOM: a bridged-T at 176.6 Hz, its pitch falling as it rings. Score 11.4"),
        48: (4, "as 47, two semitones up"), 50: (4, "as 47, four semitones up"),
        42: (4, "CR-78 CLOSED HAT: noise in a band at ~6-8 kHz, short, the trigger's thump "
             "under it. Score 13.3"),
        46: (4, "CR-78 OPEN HAT: the same, held. Score 16.1"),
        54: (4, "CR-78 TAMBOURINE: noise in a band at ~6 kHz, its jingle's ripple. Score 18.4"),
        60: (4, "CR-78 HIGH BONGO: a bridged-T at 601 Hz (wikter's CC0 take). Score 7.8"),
        61: (4, "CR-78 LOW BONGO: at 408 Hz. Score 7.3"),
        70: (4, "CR-78 MARACAS: a gated burst of high noise, ~30 ms. Score 18.9"),
        74: (4, "CR-78 GUIRO: a ratchet of 28 noise bursts 17.8 ms apart (click_bursts, the "
             "take's), every third 2 dB down; the set's own stroke, not Standard's scrape "
             "(percussion_map.rasp_strokes). Score 26.6"),
        75: (4, "CR-78 CLAVES: a bridged-T at 2.56 kHz. Score 10.9"),
        80: (4, "CR-78 METALLIC BEAT 1: two tones (~610, ~840 Hz), short. Score 14.7"),
        81: (4, "CR-78 METALLIC BEAT 2: a bright ping, noise in a band at ~5 kHz. Score 18.5"),
        39: (4, "the 707's clap"), 44: (4, "the 606's closed hat"), 49: (4, "the 808's cymbal"),
        51: (4, "the 606's cymbal"), 57: (4, "the 909's crash"),
        62: (4, "the 808's high conga"), 63: (4, "the 808's mid conga"), 64: (4, "the 808's low conga"),
    },
    28: {
        36: (4, "606 KICK:a bridged-T at 57.7 Hz (Ed Vargo's real 606; examples/tr606_fit.py). "
             "Score 7.3. Ben: sounds great"),
        38: (4, "606 SNARE 1: a bridged-T at 207 Hz and its snappy noise. Score 8.1"),
        40: (4, "606 SNARE 2: the snare ACCENTED (bdu's CC0 take). Score 9.1"),
        41: (4, "606 LOW TOM: a bridged-T whose pitch falls as it rings (diodes). Score 9.1"),
        43: (4, "as 41, 1.75 semitones up (the 606's two toms over six keys, evenly)"),
        45: (4, "as 41, 3.5 semitones up"), 47: (4, "as 48, 1.75 semitones down"),
        48: (4, "606 HIGH TOM. Score 10.2"), 50: (4, "as 48, 1.75 semitones up"),
        42: (4, "606 CLOSED HAT: six square oscillators (read off its cymbal: 203.2, 211.2, "
             "222.1, 251.2, 333.1, 351.9 Hz) through a high band, a short VCA; the trigger's "
             "thump under 250 Hz. Score 11.8"),
        44: (4, "as 42"),
        46: (4, "606 OPEN HAT: the same band, a longer VCA. Score 10.6"),
        51: (4, "606 CYMBAL (Roland's 'Ride'): the oscillators through three bands, each its "
             "own VCA, and a tail ringing on (after_db), scored on its 50 ms envelope too (Ben: "
             "'more ring to it than ours'): within 2 dB of the take from 0.25 s to 0.9"),
        39: (4, "the 707's clap"), 49: (4, "the 808's cymbal"), 57: (4, "the 909's crash"),
        62: (4, "the 808's high conga"), 63: (4, "the 808's mid conga"), 64: (4, "the 808's low conga"),
    },
    29: {
        36: (4, "707 KICK 1: the ROM's kick swept from ~300 Hz onto 55 (zero crossings: a 20 ms "
             "frame cannot read 55 Hz), held, then its VCA closing at 58 ms (gate_ms); its "
             "beater's click a band at 0.8-1.4 kHz. Fitted to hyperreal's 707 take: score 12.3. "
             "Ben: sounds great"),
        35: (4, "707 KICK 2: the same drum, its click softer, gated at 55 ms. Score 14.3"),
        37: (4, "707 RIM SHOT: a ring at 897 Hz and two more, gated. Score 17.4"),
        38: (4, "707 SNARE 1: a 161 Hz shell, its modes at x1.73 and x2.31, its wires' noise, "
             "gated. Score 11.2"),
        40: (4, "707 SNARE 2: the wires louder. Score 10.8"),
        39: (4, "707 HAND CLAP: four bursts at the take's 0, 10, 20, 31 ms (click_bursts: a "
             "machine's flam, the same every note) and a tail. Score 14.5"),
        41: (4, "707 LOW TOM 2: a membrane gliding down from ~140 Hz to ~100, its modes beside "
             "it. Score 9.7"),
        43: (4, "as 41, two semitones up (the 707 has three toms; the six evenly spaced)"),
        45: (4, "707 MID TOM 2. Score 8.2"), 47: (4, "as 45, two semitones up"),
        48: (4, "707 HI TOM 2. Score 9.9"), 50: (4, "as 48, two semitones up"),
        42: (4, "707 CLOSED HAT: a real hat in ROM, so OUR closed hat fitted to it "
             "(examples/rom_cymbal_fit.py), the ROM's grit on top: 4.58 -> 1.67 dB"),
        44: (4, "as 42"),
        46: (4, "707 OPEN HAT: our open hat fitted to the ROM's: 2.29 -> 1.99 dB"),
        49: (4, "the 909's crash, as Roland's set has it"), 51: (4, "the 909's ride"),
        56: (4, "the 808's cowbell"), 70: (4, "the 808's maracas"),
    },
    30: {
        36: (4, "909 KICK 1: a VCO swept in Hz (a current into an integrator: tr808.py's linear "
             "sweep) from 5.6x down onto 49.8 Hz, tau 30.5 ms, its ATTACK click beside it; TUNE, "
             "ATTACK, DECAY full. Fitted to Jason Baker's real 909 (BTAAADA): score 8.7. Ben: "
             "sounds great"),
        35: (4, "909 KICK 2: the panel's middle, no attack (BT7A0D7). Score 8.0"),
        37: (4, "909 RIM: a short ring and its click (RIM127). Score 16.3"),
        38: (4, "909 SNARE 1: two swept oscillators 1.44 apart over SNAPPY's noise; ST0T3S3, the "
             "take GeneralUser GS's own sample is. Score 9.6"),
        40: (4, "909 SNARE 2: TUNE, TONE, SNAPPY full (STATASA, GeneralUser's other). Score 11.6"),
        41: (4, "909 LOW TOM 2: a swept VCO and a second at 2/3 of it (LT3D7). Score 9.2"),
        43: (4, "909 LOW TOM 1: TUNE full (LTAD7). Score 9.4"),
        45: (4, "909 MID TOM 2 (MT3D7). Score 10.7"), 47: (4, "909 MID TOM 1 (MTAD7). Score 10.2"),
        48: (4, "909 HI TOM 2 (HT3D7). Score 6.8"), 50: (4, "909 HI TOM 1 (HTAD7). Score 6.4"),
        46: (4, "909 OPEN HAT: a real hat in the 909's ROM, so OUR open hat fitted to it "
             "(examples/rom_cymbal_fit.py: crash_fit's grid, HHOD4), the ROM's 6-bit grit a "
             "noise layer on top: 4.60 -> 1.75 dB"),
        49: (4, "909 CRASH: our crash (modes, the hard hit's swell) fitted to the 909's ROM take "
             "(CSHD4), its grit on top: 3.08 -> 2.58 dB. Ben: the samples 'sound almost real'; "
             "ours 'a little more open-ended because we aren't a sample, but that is fine'"),
        51: (4, "909 RIDE: our ride fitted to the ROM's (RIDED4): 6.11 -> 1.74 dB"),
        42: (4, "the 707's closed hat, as Roland's set borrows it"), 44: (4, "as 42"),
        56: (4, "the 808's cowbell, as Roland's set borrows it"),
        70: (4, "the 808's maracas"), 75: (4, "the 808's claves"),
    },
    8: {
        41: (4, "ROOM LOW TOM 2: Standard's floor tom in a small LIVE ROOM of its own (tonelib.LiveRoom: ~3.5 x 3.9 x 2.8 m, hard walls, reflections to the third order, the drum 1.5 m away facing the listener), fitted (examples/roomset_fit.py) to what GeneralUser GS's Room toms carry over its Standard toms: early reflections +4.5 dB against +5.4, top +3.0 against +2.2. The hall's drum moved further back gave +1 dB, aimed at the back wall 6-7 dB darker: the live room's hard walls make it roomier AND brighter. Ben: sounds great"),
        43: (4, "as 41"), 45: (4, "ROOM MID TOM 2: Standard's rack tom in the live room (as 41)"),
        47: (4, "as 45"), 48: (4, "ROOM HI TOM 2: Standard's high tom in the live room (as 41)"), 50: (4, "as 48"),
    },
    16: {
        36: (4, "MONDO KICK: Standard's kick in the Room set's live room (tonelib.LiveRoom). GeneralUser GS's Power kick is another drum besides -- tuned higher, undamped; ours keeps Standard's, which Ben heard"),
        38: (4, "GATED SD: the Electronic set's gated snare, as the manual names it, set against Standard's snare as GeneralUser's Power snare sits against its own"),
        **{n: (4, "the Room set's tom (as program 8)") for n in (41, 43, 45, 47, 48, 50)},
    },
    56: {
        47: (3, "GM 120's fret noise (not fitted: its slide, squeak and shift reworked by Ben's ear), a one-shot gated as GeneralUser GS's sample lasts (0.3 s)"),
        58: (4, "the Orchestra set's applause, gated 3.7 s as GeneralUser GS's"),
        70: (4, "GM 125's helicopter (fitted), a one-shot gated 3.75 s, its key's note a rotor as the program's is (a written C4 at 16.3 Hz; it had buzzed at 261.6)"),
        72: (4, "GM 127's gunshot (fitted)"),
        78: (4, "GM 123's bird (fitted), a one-shot gated 0.4 s"),
        79: (4, "RAIN fitted to a Freesound recording (CC0, examples/weather_fit.py): the hiss band by band (1.7 dB rms) and the DROPS as clicks -- each a cluster of sines across 500 Hz-16 kHz at one instant (grains' ninth field), +16 dB over the hiss against the recording's +19, every octave lifted as its drops lift it. Ben: \"the rain is good enough drops\""),
        80: (4, "THUNDER fitted to a Freesound strike (CC0): its rumble under 250 Hz exact to 2 kHz, the cracks low grains; gated 1 s as GeneralUser GS's"),
        81: (4, "WIND fitted to a Freesound howl (CC0): the 1 kHz howl over its rumble, 0.2 dB rms; one gust a key (a drum channel has no swell rows)"),
        82: (3, "GM 122's seashore, a one-shot gated 2.3 s -- by proxy, fitted to an ocean drum, not the sea"),
        83: (4, "STREAM fitted to a Freesound brook (CC0): its hiss (0.2 dB rms), its drops a short ring at 2 kHz under clicks to 16 kHz -- the ring kept short (Ben: \"a bit too bouncy ball\")"),
        84: (4, "BUBBLES set from a Freesound recording's own events (CC0): 11 a second at 300 Hz-1.2 kHz, each rising from 0.88 of its pitch (grains' glide), dying at 220 dB/s -- run as the bell tree's cascade, 22 rising (percussion_map.KIT_STROKES), as Ben approved it"),
        63: (4, "CAR ENGINE fitted to a Freesound idle (CC0, examples/weather_fit.py): its firing at 47.4 Hz and harmonics as partials, each standing out of the engine's noise as the recording's (h1-h6 within 2 dB; those barely over the noise held at their measured heights), the noise's colour 1.6 dB rms"),
        64: (4, "CAR SKID fitted to a Freesound handbrake turn (CC0): a squeal near 1.4 kHz over the tyre's roar (2.6 dB rms), never steady -- three near pitches beating under a slow swing, as the recording hops 53 cents rms"),
        65: (4, "CAR PASS fitted to a Freesound pass on a wet road (CC0): the tyres' noise (2.2 dB rms) swelling and falling, the engine one tone 18-21 dB over it (the recording's 16-20) falling 140 to 108 Hz through the pass -- GeneralUser GS's fast Doppler, an exponential in pitch, the noise riding it"),
        66: (4, "CAR CRASH fitted to a Freesound crash with glass (CC0): its noise (0.2 dB rms) with glass clicks and metal rings as grains, holding 1.3 s and falling away over 0.6 s as the recording does"),
        67: (4, "SIREN from a Freesound fire engine (CC0): its measured series (a rotor's pulses) on a ROTOR (siren.py) fitted to the whole recorded gesture, 33 cents rms -- wound up while held (1.23 s), coasting after (11 s a factor e) and fading as it slows (its own fan: 1.1 dB rms); pressed again while it coasts it starts from the speed it has. Live steps the same model a callback at a time"),
        68: (4, "TRAIN fitted to a Freesound freight train (CC0): rumble and the wheels' clacks (clusters), 0.2 dB rms; levelled to the jet, timidity playing GeneralUser GS's train as silence"),
        69: (4, "JETPLANE fitted to a Freesound jet (CC0): its roar (0.0 dB rms), swelling in"),
        39: (3, "HIGH Q: as Standard's 27"),
        40: (4, "SLAP: a palm slap, fitted to Freesound slaps (CC0, examples/perc_fit.py sfx_slap): 4.8 dB"),
        41: (4, "SCRATCH PUSH: a turntable's groove (Freesound, CC0; examples/weather_fit.py: 1.4 dB) sped up from still -- its colour rising a fifth (tension_log)"),
        42: (4, "SCRATCH PULL: the groove dragged back, its colour falling from a fifth"),
        43: (4, "STICKS: hickory sticks clicked (Freesound, CC0): their modes near 4 kHz, the strike fitted (perc_fit): 5.0 dB"),
        44: (3, "SQUARE CLICK: as Standard's 32"),
        45: (4, "METRONOME CLICK: Ben's own Wittner at its slowest, the bell off, 35 ticks recorded close through his A6 (perc_fit sfx_metronome): a wooden knock at 0.7-1 kHz, its octaves within 2.7 dB of the ticks; its ring held to theirs with his room measured and put on ours (metronome_room.py), the knock's lines read slow under the room. Its tick no longer swings with where in the block it falls (the kernel's short chiff and cross-edge knee). Ben: sounds great"),
        46: (4, "METRONOME BELL: Ben's own Wittner's bell, 8 strikes, two left to ring (perc_fit sfx_bell): 8.97 kHz under 13.5 and 18.7 kHz gone in a second, over its own low modes 2.05 and 5.1 kHz ringing 2.5-5 dB/s; each upper mode a DOUBLET, beating 2.3-11 Hz as his rings do (Ben: the wobble). The bell alone -- its tick is the click key's, struck with it (KIT_LAYER: GeneralUser's bell is its click under 4 kHz too) -- and levelled over that tick as his take has it, +11.3 dB at 4-16 kHz (elkit_balance.TIED). Ben: sounds great"),
        48: (4, "GUITAR CUTTING NOISE (DOWN): a muted strum on steel strings (Freesound, CC0), the strings' scrape at 0.14-3 kHz: 5.9 dB. A nylon guitar's take had been its body's thump -- a tom (Ben)"),
        49: (4, "GUITAR CUTTING NOISE (UP): a hollowbody's bright muted strum (Freesound, CC0): 8.0 dB"),
        50: (3, "STRING SLAP OF DOUBLE BASS: a hand slapping an upright's strings (Freesound, CC0), judged from 31 Hz: 9.7 dB -- the take's three onsets (the rattle) one strike here"),
        51: (4, "KEY CLICK: a woodwind key struck, not blown -- a saxophone's (Freesound, CC0; no CC0 flute key clicks exist): 5.9 dB"),
        59: (4, "DOOR CREAKING: a hinge's stick-slip as a pulse train slowing 285 to 130 Hz (GeneralUser GS's gesture) over the hinge's noise, fitted to a Freesound cupboard door (CC0): 1.6 dB"),
        60: (4, "DOOR: a wooden door slammed (Freesound, CC0): the slab, the latch, the frame (perc_fit): 6.5 dB"),
        61: (4, "SCRATCH: the Scratch Pull, as GeneralUser GS plays it"),
        62: (3, "WINDCHIME: a metal chime tube struck, ringing out (Freesound, CC0): 13.0 dB -- one tube where GS's is a shaken set"),
        73: (4, "MACHINEGUN: the set's gun shot (72) fired every 69 ms, 0.69 s of them, as a Freesound M16A1 burst measures (CC0) -- an impact train in the set's own stroke table (percussion_map.KIT_STROKES)"),
        74: (3, "LASERGUN: a square wave swept down from 12x its note with a 0.1 s time constant, held and cut, as a Freesound blaster (CC0) measures. GeneralUser GS's is no reference (its envelope dies in 1 ms by the SF2; timidity plays a whine)"),
        75: (4, "EXPLOSION: a dynamite blast (Freesound, CC0; weather_fit: 0.4 dB), at once, held 0.6 s, dying over the next second as GeneralUser GS's does"),
        52: (4, "LAUGHING: a \"ho ho ho\" (Ben's call; a woman's laugh never read as one) -- a throat pulsed as a Freesound Santa says it (CC0): four arcing \"ho\"s and a long falling \"hooo\", each glottal pulse ringing his /o/'s formants (LPC: 500, 850 Hz, 2.5, 2.9, 5.7 kHz; examples/throat_fit.py), so the pitch slides through a fixed vowel. 2.1 s where GeneralUser GS's laugh is 0.9"),
        53: (4, "SCREAMING: a girl's scream (Freesound, CC0), its harmonics at her own levels (h2 -5 dB, h3 -12) over a breath 60 dB under, sliding up a fourth into 1.24 kHz as GeneralUser GS's does (weather_fit HARMCOL: colour 0.0 dB at the harmonics)"),
        54: (4, "PUNCH: a fist on a body (Freesound, CC0) as a 16 ms burst of shaped noise, its colour fitted (2.6 dB) -- as a body's modes it rang half a second"),
        55: (3, "HEART BEAT: not a recording -- the heart's own waveform, a textbook ECG beat's Fourier series, 1 Hz harmonics at the FFT's gains and phases (examples/ecg_heart.py: rendered, correlation 1.000) -- and over it the BLOOD FLOW as a Doppler hears it, noise filling to a top that follows an artery's velocity (3 kHz at peak; systole, the dicrotic notch, diastole's run-off). Ben: \"sounds great\""),
        56: (4, "FOOTSTEPS1: a hard shoe on stone (Freesound, CC0): the heel as shaped noise (colour 1.0 dB) and, 70 ms on, the sole 8 dB under, as the recorded steps pair"),
        57: (4, "FOOTSTEPS2: as 56, a semitone up, as GeneralUser GS has its pair"),
        76: (4, "DOG: a bark as a throat (examples/throat_fit.py): pulses at the six Freesound dogs' near-level contour (CC0; ~540 Hz, up 0.8 semitone, down 1.5), rough (6% jitter, 2 dB shimmer, breath), bright first then darkening ~9 dB at 4-8 kHz as the barks do, ringing their formants (LPC: 560 Hz, 1.35, 2.4, 3.5, 5.4 kHz) levelled to their bands"),
        77: (3, "HORSE-GALLOP: horseshoe clicks (Ben's call) in GeneralUser GS's five-fall gallop -- a free bar's modes from 1.9 kHz gone in ~60 ms over a bright strike, set, not fitted (no recording has a shoe's click alone). Levelled to the footsteps: GeneralUser's swells in over 5 s, 20 dB down"),
        71: (3, "STARSHIP: no recording exists, so GeneralUser GS's patch as it means it (examples/starship_ref.py, from its SF2 generators -- timidity plays it as a 4409 Hz whine): a resonant hiss at 3.8 kHz (4.1 dB rms) and a buzz warbling 581 cents at 10.9 Hz. Not modelled: the noise loop's 7 Hz repetition. Levelled to the jet"),
        85: (4, "KITTY (past the set, GS 123.4): a cat's meow as a throat (examples/throat_fit.py cat): peridactyloptrix's five meows (Freesound 214759, CC0), one 0.75 s syllable at 640 Hz, clean, near level then falling ~a semitone; LPC formants (on its harmonics, floored wide) with its fundamental and 4.5-5 kHz added, balanced to the meows (0.0 dB in every band). Ben: 'Kitty sounds good'"),
        87: (3, "GROWL (on the SC-88's key 87, GS 123.5): a dog's growl as a throat (throat_fit.py growl): qubodup's (Freesound 122183, CC0), one 0.75 s expression at ~130 Hz, its roughness measured (4.5% jitter: 35% voiced, the take's 39%), its MOUTH opening and closing (formants scaled per pulse, new: fitted to the jaw's path, 300-1000 over 80-300 Hz, 0.9 dB rms), its LIFE a level contour (new: up in 30 ms, a sagging body, a 0.15 s release), balanced to the bursts (0.0 dB). Ben: 'good enough' -- a player's pitch bend gives it its character"),
    },
    48: {
        27: (4, "Standard's closed hi-hat, moved: the set's hats are EXC1 with 42/44/46 -- six keys, one pair of cymbals (percussion_map.KIT_CHOKE)"),
        28: (4, "Standard's pedal hi-hat, moved (as 27)"),
        29: (4, "Standard's open hi-hat, moved (as 27)"),
        30: (4, "Standard's ride, moved"),
        35: (4, "CONCERT BD 2: the concert bass drum of 36 (ConcertBassDrum), the softer hit GeneralUser GS's picks"),
        36: (4, "CONCERT BD 1, FITTED BY TWO LEVELS (examples/orch_fit.py): GeneralUser GS's Orchestra bass drum picks VCSL's \"Bass Drum 1\" (CC0), and the drum is fitted to its hit -- 73 modes read settled to -45 dB AND early to 3 kHz (a big head's upper modes are gone before a kick's are read), per-octave trims and rates: 10.7 dB. Balanced as GeneralUser's set (examples/elkit_balance.py --kit=48). Ben: sounds good"),
        38: (4, "CONCERT SD: VCSL's legacy concert snare drum1 (CC0), the drum GeneralUser GS's and FluidR3's both pick: its own head (195 Hz, a flat field of modes to 12x) and stick burst, Snare Drum 2's head and wires, its bands trimmed (examples/snare_fit.py --concert): 6.9 dB"),
        39: (4, "Standard's castanets (85), moved"),
        40: (4, "as 38"),
        **{n: (4, "TIMPANI, chromatically F2-F3 (each key's MIDI pitch is its drum's: FluidR3's 41 rings at 87.3 Hz): GM 47's timpani, fitted to VSCO 2's") for n in range(41, 54)},
        57: (4, "CONCERT CYMBAL 2: a CLASHED pair, VCSL's \"Clash Cymbals 2\" (CC0, the pair both GM sets pick), on the kit crash fitted to its hits (examples/crash_fit.py --orch): 6.1 dB -- a clash's top dies far faster than a suspended crash's"),
        59: (4, "CONCERT CYMBAL 1: VCSL's \"Clash Cymbals 1\", as 57: 5.2 dB"),
        88: (4, "GM 126's applause (fitted to three Freesound halls) as a drum note: a one-shot, gated at 1.4 s as GeneralUser GS's sample lasts"),
    },
    40: {
        38: (4, "a brush TAPPED, MEASURED on Karoryfer's Swirly Drums (CC0), a kit played with brushes: its center hits, the articulation GeneralUser GS's and FluidR3's taps both pick -- the head's 25 modes from 191.8 Hz and the brush's burst read off top and bottom microphones, Snare Drum 2's wires refitted to them (examples/snare_fit.py --brush=tap): 6.2 dB. 11.3 dB under Standard's snare, as GeneralUser keeps its tap"),
        39: (4, "a brush SLAPPED down and left on the head: Swirly Drums' DIG (\"leaves the brush on the head, which mutes the sound\"), both GM sets' pick -- its own modes from 171.6 Hz, the lowest choked most (snare_fit.py --brush=slap): 7.6 dB"),
        40: (4, "a brush SWEPT, fitted on two levels (examples/brush_fit.py): its texture to Swirly Drums' fastest plain stir -- friction noise as a band table over the head's noise-driven modes, the wires' sizzle to 12.7 kHz -- and its swish to GeneralUser GS's (one gesture, gone by ~0.8 s): 7.5 dB. Ben: \"the swirl seems to need more harmonics or high-end\" -- refitted from a darker skin take"),
    },
}



def _cm32l_rated():
    """THE CM-64/32L SET (127), rated as it is built (percussion_map._cm32l):
    each key its source's rating and note -- the MT-32's drums Standard's (40
    the Electronic set's snare), its effects the SFX set's, 24 keys down."""
    import percussion_map as PM
    out = {}
    for n, (src_kit, src) in PM.CM32L_DRUMS.items():
        r, note = (KIT_RATED[src_kit][src] if src_kit else PERC_RATED[src])
        where = ("the Electronic set's %d" % src) if src_kit else ("Standard's %d" % src)
        out[n] = (r, "%s -- the MT-32's, as %s: %s" % (PM.KITS[127][n][0].upper(), where, note))
    for n in PM.KITS[127]:
        if n >= 76:
            r, note = KIT_RATED[56][n - PM.CM32L_SFX]
            out[n] = (r, "the CM-32L's, as the SFX set's %d: %s" % (n - PM.CM32L_SFX, note))
    return out


KIT_RATED[127] = _cm32l_rated()

def _gs_sets_rated():
    """THE SETS THAT REARRANGE OUR VOICES (percussion_gs): each key its source's
    rating -- at most 2 where the voice is the nearest we have (APPROX) --
    a class its program's or variation's; a name with no voice yet, unrated."""
    import percussion_gs as _G
    cls_rating = {'TaikoProperties': (lambda: RATED[116][0]), 'AtariganeProperties': (lambda: VAR_RATED[(113, 8)][0]),
                  'CengCengProperties': (lambda: VAR_RATED[(112, 16)][0]),
                  'GamelanGongProperties': (lambda: VAR_RATED[(112, 10)][0]),
                  # the Hip-Hop drums (tonelib.SampledBreak): what the names mean --
                  # a break through a 12-bit sampler at its Nyquist, played slower.
                  # Ben, on examples/hiphop_demo.py: "Sounds great."
                  'HipHopKick1Properties': (lambda: 4), 'HipHopKick2Properties': (lambda: 4),
                  'RapSnareProperties': (lambda: 4), 'HipHopSnare2Properties': (lambda: 4),
                  # the Techno drums (tonelib.TechnoKick1Properties ...): the 909s
                  # driven once through our own valve (tr808.drive on tubeamp.curve).
                  # Ben, on examples/techno_demo.py: "It actually sounds really cool."
                  'TechnoKick1Properties': (lambda: 4), 'TechnoKick2Properties': (lambda: 4),
                  'TechnoSnare1Properties': (lambda: 4), 'TechnoSnare2Properties': (lambda: 4),
                  # ...and the SC-8850's Techno set's machines so driven (the fitted
                  # 808 kick and 606 snare). Ben, on examples/techno_ab_demo.py:
                  # "The driven 808 and 606 sound good"
                  'TechnoTR808KickProperties': (lambda: 4), 'TechnoTR606SnareProperties': (lambda: 4),
                  # the SC-8850's dance-era drums, ours through what each name
                  # implies (examples/rfx_demo.py s8850dance; Ben: "Level the
                  # snares", no verdict of their own)
                  **{_c: (lambda: 3) for _c in (
                      'JungleRimProperties', 'JungleCrashProperties', 'JungleShakerProperties',
                      'LoFiSnare1Properties', 'LoFiSnare2Properties', 'LoFiRimProperties',
                      'HipHopClapsProperties', 'RnBClapsProperties', 'CompClaps2Properties',
                      'TR909ClapProperties', 'FatKickProperties')},
                  # the SC-8850's Jazz set's own, fitted to soneproject's jazz-bar kit
                  # (CC0; perc_fit.py jazz_tom_low/high, crash_fit.py --jazz), heard in
                  # examples/roomjazz_demo.py
                  **{_c: (lambda: 4) for _c in (
                      'JazzTomLowProperties', 'JazzTomHighProperties', 'JazzCrashProperties',
                      'JazzRideProperties', 'JazzRideBellProperties')},
                  # the Room set's own (Standard's in the live room) and the L/R sets'
                  # left foot (the beater off centre, a membrane's modes): theory,
                  # heard in examples/roomjazz_demo.py
                  **{_c: (lambda: 3) for _c in (
                      'RoomSnareProperties', 'RoomSnare2Properties', 'RoomClosedHatProperties',
                      'RoomOpenHatProperties', 'RoomCrashProperties', 'RoomRideProperties',
                      'RoomRideBellProperties', 'MondoKickProperties', 'LeftKickProperties',
                      'LeftRoomKickProperties', 'LeftJazzKickProperties', 'LeftJazzKick2Properties')},
                  # the SC-8850's Gamelan sets: UNT's own gamelan where it was recorded (the
                  # gangsa's bars, the gongs, the ceng-ceng) -- and the kendang fitted to
                  # Java's, the jublag's and jegogan's padded mallets, the kettles, the
                  # kempur and the kopyak built from their kin; examples/gamelan_demo.py
                  **{_c: (lambda: 4) for _c in ('GamelanPemadeProperties', 'GamelanPenyacahProperties')},
                  **{_c: (lambda: 3) for _c in (
                      'KendangWadonProperties', 'KendangLanangProperties', 'KendangBebaronganProperties',
                      'KendangPelegonganProperties', 'KelontukProperties', 'KelontukMuteProperties',
                      'KelontukSideProperties', 'GamelanJublagProperties', 'GamelanJegoganProperties',
                      'ReyongProperties', 'KajarProperties', 'KempurProperties', 'KopyakProperties')},
                  # Rock Snare Dry: Standard's snare, gated (APPROX)
                  'AcousticSnareProperties': (lambda: PERC_RATED[38][0]),
                  # the Jungle drums (tonelib.JungleBreak: breaks sped up; Kick 2 the
                  # 808's sub). Ben, on examples/jungle_demo.py: "sound good"
                  'JungleKick1Properties': (lambda: 4), 'JungleKick2Properties': (lambda: 4),
                  'JungleSnare1Properties': (lambda: 4), 'JungleSnare2Properties': (lambda: 4),
                  'JungleHiHatProperties': (lambda: 4),
                  # the native Dance set's own (2026-10-25): the Hoo a throat
                  # pulsed as a CC0 shout (Ben: "Hoo sounds good"); Small Club
                  # twelve people, each their own tempo, place and ringing
                  # cupped hands (Ben: "The claps sound much better now. Sounds
                  # good"); the Comp Kick the 909 through our valve gently
                  # (heard in examples/dance_demo.py, no verdict of its own)
                  'HooProperties': (lambda: 4), 'SmallClubProperties': (lambda: 4),
                  'TR909CompKickProperties': (lambda: 3),
                  # Cymbal & Claps' strokes: the half-open hats, the ride's
                  # zones, the brushed and the choked crashes -- each a
                  # difference fitted to DRSKit's strokes, applied to ours (Ben,
                  # on examples/cymclaps_demo.py: "cymclaps all sound good")
                  'OpenHiHatProperties': (lambda: 4), 'RideCymbalProperties': (lambda: 4),
                  'RideEdgeProperties': (lambda: 4), 'BrushCrashProperties': (lambda: 4),
                  'CrashCymbal1Properties': (lambda: 4), 'CrashCymbal2Properties': (lambda: 4),
                  # THE RHYTHM FX SETS' VOICES AND EFFECTS, THE ASIA AND ETHNIC
                  # SETS' REST (2026-10-25), on the page's scale: a 4 where a
                  # recording of the instrument is its target, a 3 where it is
                  # built from how the instrument works and Ben's ear passed it
                  # (examples/rfx_demo.py a-d, gong, asia1, asia2, ethnic: "All
                  # sound good", "Sonar sounds good", "Missile sounds good", "Call
                  # the morse good", "The voices and kakegoe sound good", "The
                  # gongs sound good", "sounds good to me", "Both sound good")
                  **{_c: (lambda: 3) for _c in (
                      'RfxTechnoThipProperties', 'RfxPopDropProperties', 'RfxSynDropsProperties',
                      'RfxPipeProperties', 'RfxDistortionKickProperties', 'RfxSubMarineProperties',
                      'RfxNoiseAttackProperties', 'RfxBounceProperties', 'RfxDistortionKnockProperties',
                      'RfxMissileProperties', 'RfxMorseProperties', 'RfxSwishProperties',
                      'RfxVelocityNoiseProperties', 'RfxSparkProperties', 'RfxSpaceBirdsProperties',
                      'RfxSpaceWormsProperties', 'RfxTapeStopProperties', 'RfxTapeStop2Properties',
                      'RfxSquareToneProperties', 'RfxSawSweepProperties', 'SfxFretSlideProperties',
                      'SfxGrowlProperties', 'RfxAliasProperties', 'RfxWoodySlapProperties',
                      'RfxIceBlockProperties', 'RfxMetallicPercProperties', 'RfxModulatedBellProperties',
                      'RfxDigitalTambourineProperties', 'RfxStereoClapProperties', 'SfxSlapProperties',
                      'RfxVoiceTahProperties', 'RfxVoiceTahRevProperties', 'RfxVoiceOuProperties',
                      'RfxVoiceAuProperties', 'RfxVoiceWheyProperties', 'RfxFrogProperties',
                      'RfxDoubyProperties', 'RfxDoubyRevProperties', 'RfxBaertProperties',
                      'RfxKakegoeProperties', 'RfxKakegoeRevProperties', 'RfxBurstTProperties',
                      'RfxBurstDProperties', 'RfxHissThProperties',
                      'RfxHuYinLuoProperties', 'RfxPaiBanProperties', 'RfxOhkawaProperties',
                      'RfxKotsuzumiLowProperties', 'RfxKotsuzumiHighProperties', 'RfxTaikoRimProperties',
                      'RfxBukProperties', 'RfxGengariProperties', 'RfxJangguKunProperties',
                      'RfxJangguCheProperties', 'RfxJingProperties', 'RfxSagatProperties',
                      'RfxBendirProperties', 'RfxUduLongProperties', 'RfxUduShortProperties',
                      'RfxUduSlapProperties', 'RfxTalkingDrumProperties', 'RfxBendTalkingDrumProperties',
                      'RfxDjembeProperties', 'RfxDjembeRimProperties', 'RfxCongaSlideProperties',
                      'RfxPandieroOpenProperties', 'RfxPandieroMuteProperties', 'RfxTamborimProperties')},
                  **{_c: (lambda: 4) for _c in (
                      'RfxVoiceOneProperties', 'RfxVoiceOneRevProperties', 'RfxVoiceTwoProperties',
                      'RfxVoiceTwoRevProperties', 'RfxVoiceThreeProperties', 'RfxVoiceThreeRevProperties',
                      'RfxDaluoProperties', 'RfxXiaoluoProperties', 'RfxNaoboProperties', 'RfxBanguProperties',
                      'RfxGenderKeyProperties', 'BonangProperties', 'GamelanGongProperties',
                      'RfxTablaTunProperties', 'RfxTablaNaProperties', 'RfxTablaTeProperties',
                      'RfxTablaGeProperties', 'RfxTablaGeHiProperties', 'RfxReqDumProperties',
                      'RfxReqTikProperties', 'RfxJingleBellProperties', 'TambourineProperties',
                      # the Brush set's hats and toms: DRSKit's whisker strokes
                      # against its sticks (examples/stroke_diff_fit.py)
                      'BrushClosedHatProperties', 'BrushOpenHatProperties', 'BrushTomHighProperties',
                      'BrushTomMidProperties', 'BrushTomLowProperties', 'BrushSwishProperties',
                      'BrushSwishMidProperties',
                      # ours reused in the SFX set's additions
                      'PhonoNoiseProperties', 'TelephoneRingProperties', 'SfxExplosionProperties',
                      'GunshotProperties', 'SfxBassSlapProperties', 'SfxBirdsProperties')},
                  # the SFX set's additions built from their names, passed by ear
                  # (examples/rfx_demo.py sfx, Ben: "They all sound great"); the
                  # biwa on our shamisen and the bang the orchestra hit APPROX
                  **{_c: (lambda: 3) for _c in (
                      'RfxMC500BeepProperties', 'RfxGuitarWahProperties', 'RfxStrumProperties',
                      'RfxBiwaFxProperties', 'RfxTapeRewindProperties', 'RfxPickScrapeProperties',
                      'RfxApplauseWaveProperties', 'OrchestraHitProperties')}}
    for which, keys in _G.SETS.items():
        k = _G.SET_KIT[which]
        # ...a set that EXTENDS one built elsewhere keeps that one's ratings
        KIT_RATED[k] = KIT_RATED.get(k, {}) if k in getattr(_G, 'SET_EXTEND', ()) else {}
        for key, name in keys.items():
            spec = _G.VOICE.get(name)
            if spec is None:
                continue
            approx = len(spec) > 3 and spec[3] == _G.APPROX
            if spec[0] in ('c', 'nc'):
                r = cls_rating[spec[1]]()
                note = "%s, the %s at %.0f Hz" % (name, spec[1].replace("Properties", ""), spec[2])
            else:
                src = (KIT_RATED.get(spec[1], {}).get(spec[2]) if spec[1] else None) or PERC_RATED.get(spec[2])
                r = src[0]
                note = "%s: %s%s" % (name, ("set %d's key %d" % spec[1:3]) if spec[1] else "Standard's key %d" % spec[2],
                                     ", played backwards" if spec[0] == 'r' else
                                     ", each strike varied ([RND]: level, brightness, pitch, a few ms; "
                                     "tonelib.RandomStrike). Ben, on examples/standard3_demo.py: pass 2 (these amounts) was good"
                                     if spec[0] == 'n' else "")
            if approx:
                r, note = min(r, 2), note + " -- the nearest we have, not the sound"
            KIT_RATED[k][key] = (r, note)


# THE SC-88 MAP'S TR-808/909 (percussion_map.SC88_TR808_909): the TR-808 set's
# ratings, and the 909's kick and snare on 35 and 40
KIT_RATED[2 * 128 + 25] = dict(KIT_RATED[25])
KIT_RATED[2 * 128 + 25][35] = (KIT_RATED[30][36][0], "the 909's kick (its set's 36), as the SC-88 map has it")
KIT_RATED[2 * 128 + 25][40] = (KIT_RATED[30][38][0], "the 909's snare 1 (its set's 38)")


# GS'S OWN KEYS PAST GM'S (SC-55 p.70), as Standard plays them
PERC_RATED[25] = (4, "the SNARE ROLL, held: the Standard snare at 13.5 strokes a second, each pressed into a "
                     "buzz of six bounces (~82 a second), the hands alternating, the first stroke and the last "
                     "accented -- MEASURED on two CC0 rolls (lucianodato's, annannienann's; "
                     "percussion_map.PERCUSSION_ROLL). Ben: roll sounds great")
PERC_RATED[26] = (4, "the FINGER SNAP, one hand's clap: the hand clap's strike fired once, fitted to the "
                     "crisp CC0 snaps (four strikes from two takes, their first 25 ms; a third take's series "
                     "tires and was left out; examples/snap_fit.py): a hump at 2-5 kHz, falling ~7400 dB/s. "
                     "Ben: \"Snaps sound great now. Just needed to fit the good ones.\"")
PERC_RATED[82] = (4, "the SHAKER as shaped noise, fitted to Camo's shaker in VSCO 2 CE (eight single shakes, CC0; "
                     "examples/perc_fit.py shaker, 10.4 -> 2.6 dB): one fixed shake of 32 ms and its decay, 3.6 dB "
                     "off the takes' envelope, colour within 0.5 dB 224 Hz-11 kHz, level with the maracas. "
                     "Ben: sounds perfect now")


def _sc88pro_extra_rated():
    """THE SC-88 PRO'S STANDARD KEYS PAST GM'S (percussion_map.SC88PRO_EXTRA_KEYS):
    each the drum it borrows, at that drum's rating."""
    import percussion_map as _PM
    for key, (name, kit, src) in _PM.SC88PRO_EXTRA_KEYS.items():
        r = (KIT_RATED.get(kit, {}).get(src) if kit else None) or PERC_RATED.get(src)
        if r is None:
            continue        # a set rated later (percussion_gs): rated again after it
        PERC_RATED[key] = (r[0], "SC-88 Pro's %s: %s" % (name, ("set %d's key %d" % (kit, src)) if kit
                                                         else "Standard's key %d" % src))


_sc88pro_extra_rated()

# THE SOUND CANVAS'S DRUM SETS, every map (SC-8850 owner's manual, p.187,
# "Drum Set List"): (PC, SC-8850 map, SC-88Pro map, SC-88 map, SC-55 map),
# None where that map has no set at that program. The goal (2026-10-23):
# every one built (Ben: "let's work on coveraging all of the drum sets")
GS_DRUM_SETS = (
    (1, "STANDARD 1", "STANDARD 1", "STANDARD 1", "STANDARD"),
    (2, "STANDARD 2", "STANDARD 2", "STANDARD 2", None),
    (3, "STANDARD L/R", "STANDARD 3", None, None),
    (9, "ROOM", "ROOM", "ROOM", "ROOM"),
    (10, "HIP HOP", "HIP HOP", None, None),
    (11, "JUNGLE", "JUNGLE", None, None),
    (12, "TECHNO", "TECHNO", None, None),
    (13, "ROOM L/R", None, None, None),
    (14, "HOUSE", None, None, None),
    (17, "POWER", "POWER", "POWER", "POWER"),
    (25, "ELECTRONIC", "ELECTRONIC", "ELECTRONIC", "ELECTRONIC"),
    (26, "TR-808", "TR-808", "TR-808/909", "TR-808"),
    (27, "DANCE", "DANCE", "DANCE", None),
    (28, "CR-78", "CR-78", None, None),
    (29, "TR-606", "TR-606", None, None),
    (30, "TR-707", "TR-707", None, None),
    (31, "TR-909", "TR-909", None, None),
    (33, "JAZZ", "JAZZ", "JAZZ", "JAZZ"),
    (34, "JAZZ L/R", None, None, None),
    (41, "BRUSH", "BRUSH", "BRUSH", "BRUSH"),
    (42, "BRUSH 2", None, None, None),
    (43, "BRUSH 2 L/R", None, None, None),
    (49, "ORCHESTRA", "ORCHESTRA", "ORCHESTRA", "ORCHESTRA"),
    (50, "ETHNIC", "ETHNIC", "ETHNIC", None),
    (51, "KICK & SNARE", "KICK & SNARE", "KICK & SNARE", None),
    (52, "KICK & SNARE 2", None, None, None),
    (53, "ASIA", "ASIA", None, None),
    (54, "CYMBAL&CLAPS", "CYMBAL&CLAPS", None, None),
    (55, "GAMELAN 1", None, None, None),
    (56, "GAMELAN 2", None, None, None),
    (57, "SFX", "SFX", "SFX", "SFX"),
    (58, "RHYTHM FX", "RHYTHM FX", "RHYTHM FX", None),
    (59, "RHYTHM FX 2", "RHYTHM FX 2", None, None),
    (60, "RHYTHM FX 3", None, None, None),
    (61, "SFX 2", None, None, None),
    (62, "VOICE", None, None, None),
    (63, "CYM&CLAPS 2", None, None, None),
    (128, None, None, None, "CM-64/32L"),
)
# sets that ARE Standard by design here (the SC-55 map's Jazz: Standard's
# notes; its kick and snare a shade apart, not built)
STANDARD_BY_DESIGN = {33}


# ROLAND'S OWN KEYS FOR EACH SET (the SC-88 Pro owner's manual's drum set
# lists, parsed by examples/gs_drumsets.py): {(map, PC): {key: name}}, a key
# that sounds and is not "same as Standard 1". A set is BUILT only where every
# one of them is ours; else PARTIAL -- silent where the set stands alone,
# Standard's drum where it stands on Standard. The native sets are the
# SC-8850's (percussion_sc8850): where it revised or added a set, its own list
# (DRUMSET8850_TSV; in a set that stands alone a "same as Standard 1" key is
# Standard 1's sound, and its own)
DRUMSET_TSV = os.path.expanduser("~/Documents/refs/roland/sc88pro_drumsets.tsv")
DRUMSET8850_TSV = os.path.expanduser("~/Documents/refs/roland/sc8850_drumsets.tsv")
_OWN = None
_SAME = ("\u2190", "<-", "<\u2013")


def roland_own_keys(pc, lsb=0):
    global _OWN
    if _OWN is None:
        _OWN = {}
        if os.path.exists(DRUMSET_TSV):
            for line in open(DRUMSET_TSV).read().split("\n")[1:]:
                f = line.split("\t")
                if len(f) < 5:
                    continue
                mp, p_, _sn, key, name = f[:5]
                if name.startswith("-") or name in _SAME or name == "":
                    continue
                _OWN.setdefault((mp, int(p_)), {})[int(key)] = name
        if os.path.exists(DRUMSET8850_TSV):
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from sc8850_sets import ALONE
            rows = [l.split("\t") for l in open(DRUMSET8850_TSV).read().strip().split("\n")[1:]]
            std = {int(f[2]): f[3] for f in rows if f[0] == "1"}
            for p_, _sn, key, name, _fl, pro in rows:
                p_, key = int(p_), int(key)
                if pro == "1":
                    continue                    # the SC-88 Pro's set, unchanged
                if name in _SAME and p_ in ALONE:
                    name = std.get(key, "---")
                if name.startswith("-") or name in _SAME or name == "":
                    continue
                _OWN.setdefault(("sc8850", p_), {})[key] = name
    if lsb == 0 and ("sc8850", pc) in _OWN:
        return _OWN[("sc8850", pc)]
    mp = {0: "native", 1: "sc55", 2: "sc88", 3: "native"}[lsb]
    return _OWN.get((mp, pc)) or (_OWN.get(("native", pc)) if lsb else None)


def _set_status(pc, lsb=0):
    """(status, keys rated, median rating) for the set at program pc (1-based),
    in the map CC32 = lsb names (0 the native; 1 SC-55, 2 SC-88, 3 SC-88Pro)
    where that map has a set of its own there (percussion_map._map_set)."""
    import percussion_map as PM
    k = pc - 1
    if lsb and 128 * lsb + k in PM.KITS:
        k = 128 * lsb + k
    if k == 0:
        rated = [r for r, _ in PERC_RATED.values()]
        return "built: the note map above", len(rated), sorted(rated)[len(rated) // 2]
    if k in PM.KITS:
        # ...not counting the keys below a set that only carry a sound's second
        # voice (percussion_gs.LAYER: a word's consonant, Slappy's slap)
        hidden = {h for ks in PM.KIT_LAYER.get(k, {}).values() for h in ks}
        rated = [r for key, (r, _) in KIT_RATED.get(k, {}).items() if key not in hidden]
        med = sorted(rated)[len(rated) // 2] if rated else None
        mine = [n for n in PM.KITS[k] if n not in hidden]
        own = roland_own_keys(pc, lsb)
        if own:
            # ...a key Roland names for a different sample of the same drum
            # (Room's "Hand Clap") is covered where our voice for that name IS
            # Standard's on that key and the set plays Standard's there
            import percussion_gs as _G
            def _covered(key, name):
                sp = _G.VOICE.get(name)
                return (k not in PM.KIT_ONLY and sp is not None and sp[0] == 'k' and sp[1] == 0
                        and sp[2] == key)
            missing = [key for key, name in own.items() if key not in PM.KITS[k] and not _covered(key, name)]
            if missing:
                how = "silent" if k in PM.KIT_ONLY else "Standard's drum"
                return ("partial: %d of %d keys (%d %s)" % (len(own) - len(missing), len(own),
                                                            len(missing), how), len(rated), med)
        return "built: %d keys of its own" % len(mine), len(rated), med
    if pc in STANDARD_BY_DESIGN:
        return "Standard, by design", 0, None
    return "not built: plays Standard", 0, None


DRUM_MAPS = ((1, "SC-8850"), (2, "SC-88Pro"), (3, "SC-88"), (4, "SC-55"))
DRUM_LSB = {1: 0, 2: 3, 3: 2, 4: 1}


def drum_set_totals():
    """{map name: [sets built, sets]} -- a map's set by another name than the
    native's is its own: built only where that map's set is (the SC-88's
    TR-808/909 on 26)."""
    import percussion_map as PM
    tot = {}
    for row in GS_DRUM_SETS:
        for col, nm in DRUM_MAPS:
            if row[col]:
                own = row[col] not in (row[1], row[2])
                st = (_set_status(row[0], DRUM_LSB[col])[0]
                      if not own or 128 * DRUM_LSB[col] + row[0] - 1 in PM.KITS else "not built")
                t = tot.setdefault(nm, [0, 0])
                t[1] += 1
                t[0] += st.startswith("built") or st.startswith("Standard, by")
    return tot


def summary_md(hist, wrong):
    """THE NUMBERS FIRST (Ben: summaries before details): GM 1's programs and
    percussion keys, GM 2's sound set and drum sets, each Sound Canvas map's
    tones and drum sets -- every one counted from the tables below."""
    import percussion_map as PM
    L = ["## Summary\n"]
    gmk = [n for n in range(35, 82)]
    built = [PERC_RATED[n][0] for n in gmk if n in PERC_RATED]
    L.append("| set | of | built | | 4 | 3 | 2 | 1 | 0 |")
    L.append("|---|---|---|---|---|---|---|---|---|")

    def row(name, n, rs):
        h = {k: rs.count(k) for k in range(5)}
        b = sum(r is not None for r in rs)
        L.append("| %s | %d | %d | %d%% | %s |" % (name, n, b, round(100 * b / n) if n else 0,
                                                   " | ".join(str(h[k]) for k in (4, 3, 2, 1, 0))))
    row("GM 1 programs", 128, [k for k in range(5) for _ in range(hist[k])])
    row("GM 1 percussion keys (35-81)", len(gmk), built)
    g = gm2()
    if g is not None:
        row("GM 2 tones (MSB 121)", len(g), [r for *_x, r in g])
    kr = []
    for k in GM2_KITS:
        st, n, med = _set_status(k + 1)
        # GM 2's sets ask less than Roland's own (its Brush differs from
        # Standard by the brushes on 38-40): a set of ours there counts, partial
        # by the Sound Canvas's lists or not
        kr.append(med if st.startswith("built") or st.startswith("partial") else None)
    row("GM 2 drum sets", len(GM2_KITS), kr)
    sc = sound_canvas()
    tot = drum_set_totals()
    dmap = {"SC-55": "SC-55", "SC-55mkII": "SC-55", "SC-88": "SC-88", "SC-88Pro": "SC-88Pro",
            "SC-8850": "SC-8850"}
    if sc is not None:
        for name, n, nb, other, h in sc[0]:
            row("%s tones" % name, n, [r for r in (4, 3, 2, 1, 0) for _ in range(h[r])] + [None] * (n - nb))
            d = tot.get(dmap[name])
            if d and name != "SC-55mkII":
                L.append("| %s drum sets | %d | %d | %d%% | | | | | |"
                         % (dmap[name], d[1], d[0], round(100 * d[0] / d[1])))
    L.append("")
    L.append("A drum set is counted by the program that selects it on a drum channel, in that map; "
             "a GM 2 drum set's rating is its set's median key rating. The SC-55mkII has the SC-55's sets.\n")
    L.append(wrong + "\n")
    return "\n".join(L)


def drum_set_table():
    """The drum sets, by the program that selects them."""
    import percussion_map as PM
    L = ["## Drum sets: the program on a drum channel\n"]
    L.append("The program on a drum channel is the drum SET, and a set changes only")
    L.append("some notes -- every blank in Roland's table is \"same as Standard\". The")
    L.append("Sound Canvas's sets on every map (SC-8850 owner's manual p.187): the")
    L.append("SC-55 map has 10 (and the CM-64/32L at 128), the SC-88 map 14, the")
    L.append("SC-88Pro map 25, the SC-8850 map 37. A set not built here plays")
    L.append("Standard. THE GOAL: every one built.\n")
    maps, LSB = DRUM_MAPS, DRUM_LSB
    L.append("| PC | SC-8850 | SC-88Pro | SC-88 | SC-55 | here | keys rated | median |")
    L.append("|---|---|---|---|---|---|---|---|")
    for row in GS_DRUM_SETS:
        st, n, med = _set_status(row[0])
        if st.startswith("not"):
            # a map's own set built where the native's is not (the SC-88's Dance)
            for col, nm in maps:
                k = 128 * LSB[col] + row[0] - 1
                if LSB[col] and row[col] and k in PM.KITS:
                    mst, n, med = _set_status(row[0], LSB[col])
                    st = "%s (the %s map's); native not built" % (mst, nm)
                    break
        L.append("| %d | %s | %s | %s | %s | %s | %s | %s |" % (
            row[0], *(c or "--" for c in row[1:]), ("**%s**" % st) if "not built" in st else st,
            n or "", ("**%d**" % med) if med is not None else ""))
    L.append("")
    for k in sorted(KIT_RATED):
        L.append("### %d %s\n" % (k, PM.DRUM_SETS[k]))
        L.append("| # | note | class | | notes |")
        L.append("|---|---|---|---|---|")
        for n in sorted(KIT_RATED[k]):
            name, cls = PM.KITS[k][n][0], PM.KITS[k][n][1].__name__
            r, note = KIT_RATED[k][n]
            L.append("| %d | %s | `%s` | **%d** | %s |"
                     % (n, name, cls.replace("Properties", ""), r, note))
        L.append("")
    return "\n".join(L)


# ---- stops: the registers WITHIN a program ---------------------------------------
# A program's rating is its default registration's. A registerable program has
# other stops, and each is its own claim -- the harmonium take plays two of its
# nine reeds, Pitea's principals measured three of the console's fourteen. So
# each is rated here on the same scale, by the stop's name as the class's
# stop_ranks spells it (read from the code, checked against it: a stop renamed
# or added without a rating fails the build). CONTROLS are the rest of the
# console -- the Leslie's speeds, the accordion's banks -- that are not stops.
# Each entry: (programs, what the panel is, {stop: (rating, note)},
#              [(control, rating, note)]).
STOP_RATED = [
 ((6,), "the harpsichord's registers (CC11 stop word)", {
    "8":       (4, "the lower 8': VCSL's English harpsichord over the whole band -- ladder, body, decay as m^0.6, partials to 16 kHz, the quill's catch before it slips -- and a string among three: the key's other choirs answer through the bridge (register.py), each its own cents and wire"),
    "8-upper": (4, "the Harpsimachord (Pianobook, a Kirckman copy), its Upper against its Lower: within +-3 dB at every harmonic, so plucked where the lower 8' is (0.115; the Flemish pair's ratio, 0.083, was 13.1 dB rms off, now 3.1) and dying 1.12x as fast (11 keys). Plucks ~3 ms after the lower 8' (asserted: no coupled recording)"),
    "4":       (4, "the Harpsimachord's Lower+4 against its Lower, the 4' read on the 8''s even harmonics against the odd ones beside them: plucked at 0.21 (twice the 8''s fraction), darker, dying faster (2.89 -> 1.62 dB rms); level 0.57 from the takes' totals (+0.9 dB), not the ladder's 1.05 -- Ben, A/B: \"Levelled sounds more natural\". Its own bridge (half the coupling, asserted)"),
    "lute":    (4, "the Harpsimachord's Buff against its Lower (VCSL's English Lute before it): a gentler buff, the treble 6-10 dB down at h3-h12 and the bass untouched (7.18 -> 2.20 dB rms), dying 1.62x as fast as the 8' (early partials); its tail is the other 8' answering, 5.7 cents off (VCSL's 5.8), through the register VCSL's tail fitted; the pad damps choir A's string whichever jack plucks it. Ben, A/B: \"After lute sounds more natural\""),
  }, []),
 ((16, 17, 18), "the tonewheel's nine drawbars", {
    "8":     (4, "pulled in both of hammondman's packs; drawbar_fit.py derives the settings (tonewheel 00 7880 000, rok 00 8876 034) and the model explains every note to 3.0-3.9 dB rms"),
    "4":     (4, "as 8: both packs, 3.4-3.6 dB"),
    "2-2/3": (4, "as 8: both packs, 2.9-4.1 dB -- the tempered twelfth"),
    "2":     (4, "the rok pack, 3.6 dB"),
    "1-1/3": (4, "the rok pack, 4.0 dB"),
    "1":     (4, "the rok pack, 3.1 dB, with the foldback above the 91st wheel"),
    "16":    (4, "the L102 (Pianobook, a spinet sampled dry, every drawbar alone; l102_fit.py): +2.2 dB over the 8' on the same wheel -- one frequency, so speaker and mic divide out -- 1.00 -> 1.30. Ben, A/B: \"the after sounds more natural\""),
    "5-1/3": (4, "the L102, as 16: -1.1 dB under the 8' on its wheel, which the asserted 0.85 had (0.87)"),
    "1-3/5": (4, "the L102, as 16: level with the 2' and 1.3 dB over the 1-1/3' on their wheels (0.52 -> 0.59); its wheel the tempered seventeenth, read 11.4 cents sharp"),
    "perc 3rd L102": (4, "the L102's third-harmonic tap, recorded alone on the fast decay: 90 dB/s, -6.6 dB against the 8' on the same wheel (its rise with pitch, +4.5 dB/octave, is the spinet's circuit: left flat)"),
    "perc 2nd L102": (4, "the L102's second, as its third: 90 dB/s, -14.4 dB"),
    "perc 3rd B3":   (4, "Real Rotor Organ's (a 1957 B3 through its Leslie): ~100 dB/s, +1.4 dB over its 5-1/3' by its maker's own mix (the files read hot, normalised) -- GM 17's"),
    "perc 2nd B3":   (4, "Real Rotor Organ's second, as its third: +6.3 dB over its 8'"),
  }, [
    ("Leslie slow (chorale)", 4, "the tonewheel pack: the bass rotor's lobe from 160 Hz, the cabinet's response, the crossover's shimmer"),
    ("Leslie fast (tremolo)", 4, "the rok pack: the horn's throw and lobe refitted, 6.9 -> 4.7 dB"),
    ("key click and leakage", 4, "every drawbar's contact at its own instant over 15 ms, the bounce's noise, the unpulled wheels at -48 dB: within ~1 dB of the takes"),
    ("percussion (GM 17)", 3, "the four tap stops (perc 3rd/2nd, L102/B3), each a rank decaying on its own, fitted; NOT modelled, the B3's own behaviour: its single trigger (keyed only from every key up), its 1' cancel while on, its normal-volume duck of the drawbars"),
    ("overdrive (GM 18)", 4, "the rok pack's energy off the drawbars' harmonics: to the edge of breakup, drive 0.92"),
    ("scanner vibrato/chorus (CC94: off, V1-V3, C1-C3)", 3, "the late B-3's circuit SOLVED (scanner.py; Werner, Dunkel & Germain, DAFx-16, its Table 1): the LC ladder's 19 taps by AC nodal analysis -- lowpass, dispersion, standing-wave ripple, the tapered early taps -- and on chorus the bottom rail's 0.71 of the signal undelayed under the scanned ~0.3 (Rc 22 k; the service manual's 'part of the signal across the line, the rest across a resistor in series'); the scanner's crossfade over its 16 plates at 6.87 Hz, one motor for every key: a delay row per band, each partial's mean gain, and the crossfade's own motion as sidebands within 40 dB of their partial and 60 of its note (Ben, A/B: 'Tier B sounds better'). Live = file to 0.15 dB. No recording of a B-3's scanner to fit against"),
  ]),
 ((19,), "the church organ's console (28-bit stop word, CC11 | CC43<<7 | CC44<<14 | CC45<<21)", {
    "principal 8":    (4, "Pitea's HV Principal 8: its own series at three anchor pitches, its speech and overshoot fitted register by register, its wind. Ben: sounds great"),
    "octave 4":       (4, "Pitea's HV Oktava 4: its own series, brighter over the middle keys than the 8' at the same pitch; the speech the 8''s law at its pitch"),
    "super octave 2": (4, "Pitea's HV Oktava 2: its own series, near-pure in the treble (h2 33 dB down)"),
    "quint 2-2/3":    (4, "Pitea's Positiv Kvinta 2 2/3: its own series at its pitch, its speech the principal's law at its own pitch (its overshoot on its own harmonics, not the key's)"),
    "quint 5-1/3":    (4, "FITTED ON BORROWED PIPES (examples/pitea_newranks.py --hold-level): Pitea has no 5 1/3 (its pedal mixture's quint is the plein-jeu's 2 2/3), so its series is the Kvinta 2 2/3's pipes an octave down, which sound its pitch, from C3 -- h2-h10 6-10 dB under the principal series it had borrowed, a quint that FUSES into the chorus; its level held where the console had it. Ben, A/B: blends better"),
    "principal 16":   (4, "FITTED ON BORROWED PIPES (examples/pitea_newranks.py --hold-level): Pitea has no open 16' on a manual, so its series is the Principal 8's pipes an octave down and, under C3, the pedal Oktava 8's (open, down to C1) -- within ~2-3 dB of the 8''s series it had read at its pitch, and its bottom octave now measured; its level held. Ben, A/B: approved"),
    "flute 8":        (4, "Pitea's Positiv Gedakt 8 (examples/pitea_stops.py): its own series at three anchor pitches, read at the rank's pitch (h3 12-20 dB down, the evens 30-50); its speech fitted (24 of its own periods, no overshoot -- it had taken the principal's); its wind fitted before. Level held"),
    "bourdon 16":     (4, "Pitea's Huvudverk Gedackt Pommer 16, as the flute 8: its series, its speech (12 periods, the upper harmonics a little ahead)"),
    "mixture III":    (4, "Pitea's Huvudverk Mixtur IV, its harmonics read key by key: the composition breaking back at every C (1 1/3 1 2/3, then 2 1 1/3 1, 2 2/3 2 1 1/3, 4 2 2/3 2 -- the IV's lowest three), each pipe the principal's measured series at its own pitch; within 2-5 dB of the IV's three, its fourth rank absent"),
    "reed 8":         (4, "Pitea's Positiv Cromorne 8: its series -- the evens there, which the odd-only reed had not -- its speech (12 periods, no overshoot), its wind and attack rush fitted before. Heard as BuxWV 140's fugue reed"),
    "reed 16":        (4, "the extended set's Basson 16, as reed 8. Heard as BuxWV 161's Posaune"),
    "reed 4":         (4, "Pitea's Svallverk Clarion 4, as reed 8: bright to h7, speaking slowly (18 periods over an 80 ms valve)"),
    "trumpet 8":      (4, "Pitea's Huvudverk Trumpet 8, as reed 8: its own series in place of the orchestral trumpet's, which a forced stiffness had cut off above 2.6 kHz; speech 18 periods. Trimmed by ear in BuxWV 161"),
    "tremulant":      (2, "no pipes: a valve pulsing the division's wind. Off by default until judged by ear"),
    "koppelflute 4":    (4, "Pitea's Positiv Koppelflöjt 4 (bit 14): its own series at its anchor pitches, its speech and its level by Pitea's own balance, fitted to its pipes (examples/pitea_newranks.py). Ben, examples/organ_newstops_demo.py: they sound incredible"),
    "waldflute 2":      (4, "Pitea's Positiv Valdflöjt 2 (bit 15): its own series at its anchor pitches, its speech and its level by Pitea's own balance, fitted to its pipes (examples/pitea_newranks.py). Ben, examples/organ_newstops_demo.py: they sound incredible"),
    "nazard 2-2/3":     (4, "Pitea's Nazard (bit 16): the flute twelfth, the Sesquialtera's fifth: its own series at its anchor pitches, its speech and its level by Pitea's own balance, fitted to its pipes (examples/pitea_newranks.py). Ben, examples/organ_newstops_demo.py: they sound incredible"),
    "tierce 1-3/5":     (4, "Pitea's Tierce (bit 17), tuned near pure as recorded: its own series at its anchor pitches, its speech and its level by Pitea's own balance, fitted to its pipes (examples/pitea_newranks.py). Ben, examples/organ_newstops_demo.py: they sound incredible"),
    "subbass 16":       (4, "Pitea's pedal Subbas 16 (bit 18); its speech the least fitted (9 dB: a wide stopped bass builds slowly): its own series at its anchor pitches, its speech and its level by Pitea's own balance, fitted to its pipes (examples/pitea_newranks.py). Ben, examples/organ_newstops_demo.py: they sound incredible"),
    "contrabassoon 32": (4, "Pitea's pedal Kontrabasun 32 (bit 19), the reed an octave under the 16'. Ben: insane: its own series at its anchor pitches, its speech and its level by Pitea's own balance, fitted to its pipes (examples/pitea_newranks.py). Ben, examples/organ_newstops_demo.py: they sound incredible"),
    "gamba 8":          (4, "Pitea's swell Gamba 8 (bit 20) at Pitea's own soft level (-19 dB re the Principal 8); speech 8 dB off (a string's slow build): its own series at its anchor pitches, its speech and its level by Pitea's own balance, fitted to its pipes (examples/pitea_newranks.py). Ben, examples/organ_newstops_demo.py: they sound incredible"),
    "celeste 8":        (4, "Pitea's swell Voix celeste 8 (bit 21), +17.9 cents measured against its Gamba, from C3; drawn with it, it beats: its own series at its anchor pitches, its speech and its level by Pitea's own balance, fitted to its pipes (examples/pitea_newranks.py). Ben, examples/organ_newstops_demo.py: they sound incredible"),
    "oboe 8":           (4, "Pitea's swell Oboe 8 (bit 22): its own series at its anchor pitches, its speech and its level by Pitea's own balance, fitted to its pipes (examples/pitea_newranks.py). Ben, examples/organ_newstops_demo.py: they sound incredible"),
    "vox humana 8":     (4, "the Voix humaine 8 of the extended set's second organ (bit 23), the Grönlund having none: its own series at its anchor pitches, its speech and its level by Pitea's own balance, fitted to its pipes (examples/pitea_newranks.py). Ben, examples/organ_newstops_demo.py: they sound incredible"),
    "trompette 8":      (4, "Pitea's swell Trompette harmonique 8 (bit 24): its own series at its anchor pitches, its speech and its level by Pitea's own balance, fitted to its pipes (examples/pitea_newranks.py). Ben, examples/organ_newstops_demo.py: they sound incredible"),
  }, [
    ("pipe speech and release", 4, "fitted on the Principal 8 by register; every flue rank takes the law at its own pitch"),
    ("shared wind (the chest)", 3, "every pipe on the chest hears the others' demand: a chord dips the pressure as it enters and surges it as it lifts, a reservoir ringing at 4 Hz and a regulator restoring it -- the form the physics' (Pykett, Carlsson 2002, the Rodgers wind patent), the size Ben's ear's (flexibility 1 of off/1/2.5/8: a five-note chord takes ~2 cents from a held note). No recording of one organ's coupling was fitted: it varies organ to organ. On by default"),
    ("the key's groove", 2, "not modelled: the stops on a key share its channel, so a release drains faster with more drawn, and the pipes go flat as it drains (Pitea's reeds 35-68 cents at C3-C4)"),
  ]),
 ((20,), "the harmonium's registers (CC43/44/45 stop word: bass | treble at E4/F4)", {
    "cor anglais 1": (4, "the bass 8' foundation: donyaquick's harmonium, 32 keys, the series within 2.5 dB rms"),
    "flute 1":       (4, "the treble 8' foundation, as cor anglais 1"),
    "clairon 3":     (4, "the bass 4': its series and speech the Debain's Clairon recorded alone (as bourdon 2), its level and its cents (each key 0.4-12 sharp of its octave) donyaquick's 8'+4' take's -- where the 8'+4' had fitted its brightness only as a sum: against that take the evens h2-h8 now within 2.1 dB (were 5.0), h10-h12 5-9 dB dark (the Debain's cut)"),
    "fifre 3":       (4, "the treble 4', as clairon 3 (the Debain's Fifre, its top thirteen keys broken: those carry the keys below)"),
    "bourdon 2":     (4, "the bass 16': the Debain's Bourdon (Silvestre's set), its difference from the Debain's foundation key by key carried onto ours as tables at three anchors (the takes are low-passed and denoised: each read over its live band), its slow speech (36 cycles) and its level by the set's balance (examples/debain_registers.py). Ben, examples/harmonium_registers_demo.py: they sound great"),
    "clarinette 2":  (4, "the treble 16': the Debain's Clarinette, HOLLOW at last (h3 over h2: the cavity the flow model could not make), as bourdon 2. Ben, examples/harmonium_registers_demo.py: they sound great"),
    "basson 4":      (4, "the bass 8' solo: the Debain's Basson, as bourdon 2. Ben, examples/harmonium_registers_demo.py: they sound great"),
    "hautbois 4":    (4, "the treble 8' solo: the Debain's Hautbois, as bourdon 2. Ben, examples/harmonium_registers_demo.py: they sound great"),
    "celeste":       (4, "the Debain's Voix celeste 16: TWO ROWS beating on their own, 10.5-18.6 cents apart key by key (median 15.4; every harmonic's swing at m times one rate), its series as bourdon 2. Ben, examples/harmonium_registers_demo.py: they sound great"),
    "expression":    (2, "the reservoir shut, the feet the wind: brightness with pressure, asserted"),
    "percussion":    (2, "a hammer on the front 8' reeds at key-down, asserted"),
    "tremolo":       (4, "the Debain's Tremolo (its Musette with the flutter on): a level swing at 9.52 Hz, depth 0.25, ours on the Musette reading the same; it flutters every reed drawn, the Debain's only its one row. Ben, examples/harmonium_registers_demo.py: they sound great"),
    "violoncelle":   (4, "the Debain's Violoncelle 8', bass (bit 12): added from its takes, as bourdon 2. Ben, examples/harmonium_registers_demo.py: they sound great"),
    "sourdine":      (4, "the Debain's Sourdine 8', bass (bit 13), the muted stop 10.3 dB under the foundation: added, as bourdon 2. Ben, examples/harmonium_registers_demo.py: they sound great"),
    "musette":       (4, "the Debain's Musette 16', treble (bit 14): added, as bourdon 2. Ben, examples/harmonium_registers_demo.py: they sound great"),
  }, []),
 ((21, 23), "the accordion's reed banks (no stops: GM gives each box its own program)", {}, [
    ("musette (GM 21)", 4, "two 8' banks, the wet one 16.0 cents at A4 narrowing 3.3 an octave, no 16': measured on hammondman's Hohner"),
    ("bellows push (GM 21)", 4, "the swell from silence, carried over a slur: measured on the same take"),
    ("bandoneon (GM 23)", 4, "two reeds a tone, the second an OCTAVE ABOVE at -13.5 dB and ~2.5 cents, no wet unison: measured on Bleymehl's 1930 ELA (the 16' it had sounded GM 23 an octave low)"),
  ]),
 ((55,), "the orchestra hit's sections (CC11, all seven drawn by default)", {
    "bass":   (4, "the tuba's conical brass two octaves down: a measured voice, its level in the hit FITTED to the GM sets' hits with the rest (examples/orchhit_fit.py)"),
    "tenor":  (4, "the trombone an octave down, as bass"),
    "horn":   (4, "the horn on the FIFTH (x1.5), re-voiced for the fifth the GM hits carry; as bass"),
    "string": (4, "the bowed strings marcato, as bass"),
    "tpt":    (4, "the trumpet an octave up, as bass"),
    "wind":   (4, "flutes and oboes as a stopped pipe on the TWELFTH (x3), re-voiced with the horns; as bass"),
    "picc":   (4, "the piccolo two octaves up, as bass"),
  }, []),
]


def stops():
    """[(programs, panel, [(bit, stop, rating, note)], controls)], the stop names
    read from each program's class and checked against STOP_RATED."""
    out = []
    for progs, panel, rated, controls in STOP_RATED:
        cls = patch_map.property_class_for_note(progs[0], 60)
        names = [r[0] for r in getattr(cls, "stop_ranks", None) or []] if rated else []
        missing = [n for n in names if n not in rated]
        extra = [n for n in rated if n not in names]
        if missing or extra:
            raise SystemExit("STOP_RATED for GM %s (%s) does not match its stop_ranks: unrated %s, unknown %s"
                             % (progs[0], cls.__name__, missing, extra))
        rows = [(i, n) + rated[n] for i, n in enumerate(names)]
        out.append((progs, panel, rows, controls))
    return out


# THE GS VARIATIONS (CC0 = bank, SC-55 p.68): each one built is its own claim,
# rated here as a program is. Every key of patch_map.VARIATIONS must be rated
# and nothing else may be -- checked when the page is built, as STOP_RATED is.
VAR_RATED = {
    (107, 16): (4, "the KANUN (tonelib.KanunProperties): courses of three strings over a wooden box, FITTED to Baris Bozkurt's isolated notes (Freesound 211133, CC0; examples/pluck_fit.py --voice=kanun, 28 notes): its inharmonicity measured (B 7.9e-5, 13x the koto's -- Ben: 'looser ... like a guitar'), its decay set on the whole note's level curve, its body within ~3 dB 250 Hz-13 kHz. Ben: 'Sounds great now'"),
    (112, 16): (4, "the Balinese CENG-CENG (tonelib.CengCengProperties): a plate from the crash FITTED to the UNT gamelan Bwana Kumala's single ringing strikes (Freesound pack 12954, CC0; examples/rama_fit.py: multi-strike files rejected, 4.8 dB on the grid), with each strike's chatter of the stand's plates (14-17 sub-hits in 120 ms) as strike_flam bursts at +10 dB by Ben's ear"),
    (124, 10): (4, "a RECORD'S SURFACE as a voice (tonelib.PhonoNoiseProperties), FITTED to nervousneal's blank groove (a 1961 MGM test pressing, Freesound 586430, CC0; examples/phono_fit.py): the hiss flat 300 Hz-12 kHz with its rumble (not brown: RIAA flattens it), clicks 34/s over 12 dB against the take's 36.7, their level spread and bright spectrum the take's, one timeline for the record with each click randomly placed in the balance (Ben) and 11.5% recurring a revolution on. Not modelled: the hiss's L/R anti-correlation, clicks of opposite polarity. Ben: 'Sounds great now'"),
    (120, 12): (4, "the SATSUMA BIWA (tonelib.BiwaProperties): a wooden-bodied lute from the shamisen's struck-silk numbers, FITTED to Hugh de Ferranti's satsuma biwa (PARADISEC HDF1-SB33, CC BY-NC-SA 4.0 data: the fitted numbers derive from it; sources.md): 44 strokes, the decay fast and flat across the harmonics, the body 500 Hz-5 kHz (the cassette's ends not the instrument's). Ben: 'Sounds great'"),
    (50, 24): (4, "the MELLOTRON's '3 Violins' tape (tonelib.MellotronMixin): the string section, three players, its colour FITTED to menegass' Mellotron violin notes (Freesound 6815, CC0; examples/mellotron_fit.py, 12 notes C4-B4: miss 4.98 -> 2.08 dB) -- brighter to ~5 kHz, then cut steeply; the transport from the M400's mechanism (8 s run-out, no touch, each key its own tuning, one capstan's wow); at its capital's level. Ben: 'Sounds incredible'"),
    (73, 16): (3, "the MELLOTRON's flute tape (tonelib.MellotronMixin): our flute under the tape's cut fitted on its violins (the flute notes found were 0.135 s, too short to fit), the capstan's wow in place of a vibrato of its own. Ben: 'Sounds incredible'"),
    (56, 1): (4, "Iowa's vibrato trumpet against its straight mf takes, note for note (examples/brass_dyn_fit.py): its vibrato, 4.83 Hz at +-5.4 cents (mf 1.5), and the ladder's top a little darker (blare -0.9 dB/kHz; miss 4.85 -> 1.73 dB). Ben: 'It sounds good'"),
    (56, 24): (4, "the brass's ff law, as the trombone's (blare +7.7 dB/kHz over 754 Hz, held at 25.9 dB): Iowa's trumpet ff is its mf, +0.3 dB and +0.6 dB/kHz (examples/brass_dyn_fit.py). Ben: 'It sounds good'"),
    (56, 8): (4, "the flugelhorn: our trumpet's source on a conical bore, its five colour knobs (bell cutoff and order, bore corner, roll-off, register law) refitted to Chris Cook's 'Dusty Flugelhorn' (Pianobook, a Yamaha 6310z, E3-A#5 at one soft dynamic; examples/flugel_fit.py): 21.2 -> 4.7 dB rms over 31 notes, ours read through the trumpet's own soft law while fitting (Warm Tp., Iowa's pp against its mf) so the class is the flugelhorn at mf; its attack the takes' (9-18 ms). A lower bell (1.2 kHz), the cone's faster roll-off. One player's Commons flugelhorn/trumpet pair read a lighter horn (--fit=commons); Ben chose this one by ear. At the trumpet's level. Ben: 'sounds more properly like a Flugelhorn'"),
    (56, 25): (4, "Iowa's trumpet pp against its mf, note for note (examples/brass_dyn_fit.py): blare -6.6 dB/kHz over 160 Hz to 34.8 dB (miss 16.77 -> 2.66 dB). Ben: 'It sounds good'"),
    (57, 1): (4, "Iowa's tenor trombone ff against its mf, note for note (examples/brass_dyn_fit.py): blare +7.7 dB/kHz over 754 Hz to 25.9 dB, the same line in all three registers (miss 8.23 -> 0.88 dB). Ben: 'It sounds good'"),
    (58, 1): (4, "Iowa's tuba ff against its mf, note for note (examples/brass_dyn_fit.py): blare +30.1 dB/kHz over 116 Hz to 24.7 dB (miss 13.01 -> 1.26 dB). Ben: 'It sounds good'"),
    (60, 1): (4, "Iowa's horn pp against its mf (examples/brass_dyn_fit.py): blare -14.0 dB/kHz over 162 Hz, held at 10.3 dB -- a weak fit (miss 4.05 -> 3.63 dB): the pp runs' top is hiss. Ben: 'It sounds good'"),
    (60, 8): (4, "Iowa's horn ff against its mf, note for note (examples/brass_dyn_fit.py): blare +9.9 dB/kHz over 588 Hz to 29.1 dB (miss 13.26 -> 2.18 dB). Ben: 'It sounds good'"),
    (35, 2): (4, "the fretless on its NECK coil alone, fitted to mrforfs' neck-pickup takes (CC0) on the low harmonics and the top together (examples/fretless_pickup_fit.py): the coil at 0.189 of the scale, ladder miss 7.2 dB and envelope 2.7 (10.3 and 3.2 with Fretless Bs2's top); trimmed +5.8 dB to GM 35's level. Ben: 'They all sound great'"),
    (35, 3): (4, "the fretless on its BRIDGE coil alone, fitted to mrforfs' bridge-pickup takes (CC0) on the low harmonics and the top together (examples/fretless_pickup_fit.py): the coil at 0.073, wider, the fundamental 7 dB down and h5-h7 up as the takes show, ladder miss 5.1 dB and envelope 1.5 (9.4 and 2.2 with Fretless Bs2's top); trimmed +9.5 dB to GM 35's level. Ben: 'They all sound great'"),
    (112, 8): (4, "the Javanese kettle gongs, fitted to Casa da Musica's bonang barung and panerus (CC BY 3.0; examples/gender_fit.py --bonang): 33 kettles 338-1382 Hz, the kettle's partner at 1.55 (-22 dB), a quiet octave, a broad mode near 3, a 7 s ring with no register law; the mallet's own strike (--mallet: a burst between the modes, 0.6-0.9 kHz, 945 dB/s; 3.9 dB by band over the first 15 ms). Ben: the tone good, 'what it is missing is the sound of the reaction of the mallet itself' -> 'Sounds good now'"),
    (112, 11): (2, "the gamelan in stereo, BY ITS NAME: no recording of Roland's tone and neither GS SoundFont has one (both hold only 112.0), and no GS file here uses it. Composed of fitted voices: the Balinese gangsa as played, a pair 26 cents apart left and right (GangsaPairProperties), and the bonang an octave over it at -6 dB, as the panerus doubles the melody. Ben: 'It sounds good, but I don't know what it is supposed to sound like'"),
    (112, 9): (4, "the gamelan's metallophone, fitted to UNT's Balinese gangsa (cpolcyn, CC0; examples/gender_fit.py): a free bar 1 : 2.70 : 5.27, the third mode carrying the strike under ~4 kHz (the panggul's roll-off, steep), the fundamental ringing (D 1.87 at 415 Hz), 42 keys; the Balinese pair (26 cents, GangsaPairProperties) taken off against Casa da Musica's Javanese gender, which has none. Ben: 'I hear it less tuned, but not too bright' -> 'Sounds good'"),
    (112, 10): (4, "the gong ageng, fitted to UNT's big gong (CC0; examples/gender_fit.py --gong): 69.3 Hz, the octave pair 2.00/2.08 at -1 dB, the beat 0.61 Hz at 2.2 dB p-p (recorded 1.4-2.4), the felt's onset 0.18 s (0.10-0.16), 3.0 dB/s (2.9-3.1); shorter up the register by the same gamelan's kempli (slope 0.73). Ben: 'Sounds good'"),
    (66, 8): (4, "the tenor played airy, fitted on GM 66 to cemorse100's 'soft, airy' C5 (CC0; examples/breathy_fit.py): the ladder darker (9.8 -> 2.3 dB), a breath table through the renderer (1.45 dB by band); the wet reed's CRACKLE as a layer (ReedCrackleProperties: exponential levels, fitted between the harmonics, shaped by the bore -- nothing under ~1 kHz; drawn as true exponentials by the kernel's synth_voice_xdec); a soft onset (tone 0.12 s, breath 0.1 s, as the take's); a slur carries tone and breath (breath_noise_slur); the breath -5 dB an octave up from C5 (ASSUMED, Ben's: no airy sax recorded at more than one register). Ben, through ten rounds: 'Sounds good'"),
    (120, 5): (2, "GM 120's fingertip on a BASS string: the squeak is hand speed over winding pitch, and a bass's outer wrap (~0.6 mm) is a guitar's (~0.35) coarser, so its band 1700 -> 990 Hz and its floor 650 -> 380 (half its energy under 950 Hz against GM 120's 1550). No recording found: Freesound held only a time-stretched effect, IDMT's bass set no slide takes"),
    (12, 16): (4, "the West African balafon, fitted to marini24's 17 strikes (CC BY 4.0; examples/balafon_fit.py): undercut wooden bars whose tuning falls up the keys (the second mode 4.1x at 236 Hz to 2.9x from ~700 Hz, the third 9x to a floor of 7), their levels by the key (a big bar rings its upper modes, a small one not), short and shorter up (35 dB/s at 236 Hz, 230 at 1.5 kHz), and the gourds' membranes BUZZING between the partials, fitted through the renderer (0.48 dB by band). Ben: 'Sounds great'"),
    (105, 16): (4, "the ektara of Bengal's Bauls, fitted to Rajobrata's Shantiniketan ektara (Pianobook, 'The Ektara': C3-A3, three strokes, three round-robins, plain and bent; measure only). THE SCOOP from the 45 bent takes: 236 cents under 30-50 ms in, 15 by 0.15 s, deeper the harder (151-276), an exponential in pitch (0.04 s), every pluck. The string from the plain takes (examples/pluck_fit.py --voice=gopichant): nearly harmonic (B 1e-5, the banjo's 8e-5 had stretched the top out of place -- the high notes' missing top Ben heard), plucked a third along (the banjo's 0.12 notched 3-4 kHz on G3-A3), its decay 7 dB/s rms, its colour to 13 kHz 0.7 dB rms. At the banjo's level. Ben: 'Sounds good'"),
    (105, 8): (3, "the Afghan rubab on the banjo's drumhead, gut on goatskin, fitted thinly: the only open rubab found is the 2 s solo opening belamalta10's '3 continents' (Freesound 513846, CC0 as uploaded -- GarageBand's loop, so measure only; examples/rabab_fit.py). Its seven notes give the colour (the fundamental weak, h2-h7 15-30 dB over it, the top falling from 2.5 kHz; 0.8 dB rms over 12 bands), the decay (24 dB/s, the banjo's 19) and the STOP: the plectrum damps each string before the next pluck (1.3-4.4 dB in the 20-35 ms before it, then ~100 dB/s; Ben heard it), so the note-off stops it. The sympathetic strings ASSUMED (the oud's contact model, eight on C's natural scale). At the banjo's level. Ben: 'Sounds good'"),
    (12, 24): (4, "a slit drum, fitted to VSCO 2's log drum (CC0; examples/logdrum_fit.py): two tongues, 108 and 155 Hz, three strokes each. The TONGUE -- its fundamental, its 2nd and 3rd (13-27 dB under on the big tongue, 31-45 on the small) -- and the LOG's own modes at 183, 505 and 660 Hz, fixed in Hz whatever key, the 183 a thump and a ring; the mallet's KNOCK between the modes (strike noise, band by band, 0.3 dB; falling 397 dB/s, the small tongue's ~20 dB under); harder strokes brighter (0.4 dB an octave per dB). 6.2 dB rms over 46 cells. At the marimba's level. Ben: 'Sounds great'"),
    (111, 8): (3, "the snake charmer's pungi, its melody pipe fitted to Nick Mariette's snake charmers in Bhaktapur (Wikimedia Commons, CC BY 2.5; examples/pungi_fit.py): a street, so its 32 held notes A4-D#5 tracked by their harmonics over the crowd -- bright and buzzy, h2-h5 within 4 dB, h4 the strongest, a series table on the shanai's reed (0.0 dB rms h1-h12); the hiss assumed (the hichiriki's: between the harmonics the take is the street). THE DRONE PIPE, a note of the part held under each phrase, its series from the take's drone (0.0 dB h2-h8, 2.4 dB over the melody's h2); THE WHEEL CHOOSES ITS NOTE (Ben), C3-B3 in twelve steps, F3 with none -- files read the first CC1, live follows the wheel. At the shanai's level. Ben: 'Sounds great'"),
    (111, 9): (3, "(internal: the pungi's drone pipe alone, the bank live sounds its drone from -- its series from the Bhaktapur take's long-term spectrum, 0.0 dB rms h2-h8 through the renderer; not an SC-88 tone)"),
    (75, 8): (3, "the Egyptian kawala, an EDUCATED GUESS (Ben: 'make educated guesses for the last two'): no kawala under an open licence, so fitted to its end-blown family -- EKVelika's Balkan kaval and aliaref's Turkish ney (both CC0; examples/freesound_slice.py pipes kawala, 22 held notes G#3-E5) -- on the shakuhachi, its series and breath as one table each (wind_fit.py --voice=kawala --fit=tables --nh=16: 0.7 and 0.9 dB rms): the octave over the fundamental (+4 dB), a breath ~30 dB under it. At the pan flute's level."),
    (113, 8): (2, "the festival hand gong, an EDUCATED GUESS (Ben's word): no recording found, so the bonang's MEASURED bronze kettle (its partner at 1.55, octave, mode near 3, mallet burst) with what differs reasoned -- a hard deer-horn mallet (the upper modes 12-18 dB up, a mode near 4.2), a small thick hand-held gong (~1.5 s ring, not 7), the horn's click brighter and quicker. At the agogo's level; examples/atarigane_demo.py plays a festival figure at C6."),
    (111, 16): (4, "gagaku's double reed, fitted to gaijinbuzz's shrine wedding (Freesound 680565, CC0; examples/wind_fit.py --voice=hichiriki), the only open recording found: nine held notes D5-E5 over the sho. The whole series, the fundamental the strongest (a table to h24 over the shanai's reed: 34.2 -> 0.0 dB rms; the hiss 0.5 dB, the shrine's floor under the fundamental left out). THE ENBAI: a phrase's first note lipped up from 230 cents under (the take's 145-290), ~0.15 s in log frequency, no slur repeating it (tension_bend_slurs, new). At the shanai's level. Ben: 'Sounds great'"),
    (104, 8): (3, "Roland's other tanpura (one voice to the Tamboura's two; no manual says more, no recording of either tone here): ours is the same tanpura with its jawari SET ANOTHER WAY, fitted to sankalp's take 1 (CC BY 4.0; examples/tanpura_fit.py --take=1 --cls=TambraProperties), whose cells differ from take 2's by 9-13 dB -- the brighter setting, the top over 5 kHz ~13 dB up, the swirl centred at 5.4 kHz and stronger; 10.1 dB rms over 250 cells (4-5 plucks a string). At the sitar's level. Ben: 'Sounds good'"),
    (104, 16): (4, "the tanpura, fitted to sankalp's drone takes (Freesound pack 9571, CC BY 4.0; examples/tanpura_fit.py): no string rings alone in them, so each is read through the partials that are its alone -- Pa's odd harmonics, the low Sa's 1st, 5th, 7th, 11th ... -- from each pluck to its next, ~14 plucks a string. The jawari's SWIRL as a burst in its band (bloom_decay_dbs, new): ~1.5-4.5 kHz rising 10-20 dB to a peak 0.3-0.85 s in and falling at 21 dB/s, a fundamental 15-20 dB under it, the decay's register slope from the two strings' own rates (9.6 and 6.0 dB/s); 9.6 dB rms over 241 cells (one take: the two disagree by 9-13 dB, two settings of the thread). The sitar's jawari model without its taraf; at the sitar's level. Ben: 'Sounds great'"),
    (105, 24): (4, "the Arabic oud, fitted to Andy R. Jordan's notes (Commons, CC BY-SA 3.0) and hammondman's (Freesound, CC0; examples/pluck_fit.py --voice=oud): a plain plucked string struck near its end (the risha), the kanun's structure where the nylon guitar was 30-60 dB short up top, its bowl as a third-octave trim (5.6 -> 2.5 dB rms), its decay from hammondman's long notes; its DOUBLE COURSES measured from each harmonic's beating (examples/course_sympathy.py: 4-9 cents, the second string ~6 dB under), and its other open courses KICKED through the bridge (contact, the Arab tuning C2 F2 A2 D3 G3 C4: the A and D courses 26-42 dB under the note, the D ~12 cents sharp, the outer four under -45). Ben: 'Sounds good'"),
    (12, 17): (2, "the same balafon played SOFTER and so drier (Ben's choice): its buzz 12 dB under (a membrane rattles only when driven hard), the upper modes 4 and 8 dB under (a soft mallet's longer contact) -- ASSUMED, one effort recorded. Ben: 'Sounds good'"),
    (71, 8): (4, "the bass clarinet over its whole compass (tonelib.BassClarinetProperties, fitted to Iowa's mf runs; GM 71 plays it only below D3), its effort law fitted on Iowa's pp and ff matched note for note (examples/bsclar_fit.py): 0.97 dB of tilt per dB from pp to mf, 0.41 above (effort_tilt_up); G3's centroid pp 209 Hz against Iowa's 202. Ben: 'Sounds great'"),
    (65, 8): (4, "the alto PLAYED OUT, fitted as a difference from GM 65 to Iowa's AltoSax.Vib.ff (examples/sax_exp_fit.py; 32 notes matched by pitch against the NoVib.mf takes GM 65 is fitted to): its own vibrato, 4.85 Hz at +-8.1 cents where the mf takes play straight (rendered 4.98 Hz, 8.9 cents), the ladder 1-2 dB up above h3 (miss 1.34 -> 0.66 dB). Ben: 'Sounds good'"),
    (25, 8): (3, "the steel-string with its courses DOUBLED, read off John Magner's Fender 12-string (Pianobook), its harmonics resolved into doublets: below B3 an octave string on the even harmonics, as loud as the main at its own pitch (the open low strings' 2nd ~10 dB over a single string's), 8 cents off (6-14 measured); B3 up a unison partner at 0.9, 5.5 cents off (2.6-9). Levels the robust numbers only: the Fender is a different guitar from the steel-string's fit. STRUCK BY A PICK (tonelib.Plectrum; examples/plectrum_fit.py): the scrape as noise of its own -- the take's attack as bright on E2 as on A4, which brighter partials cannot be -- at the note's level to 7 kHz, gone at 400 dB/s (fitted on the 4-16 kHz envelope over 70 ms, after a fit on 15 ms shares took a long quiet scrape Ben heard as harsh), the course crossed 28 ms apart. Ben: 'Sounds good'"),
    (25, 16): (3, "unison COURSES of steel strings, measured from each harmonic's beating (examples/course_sympathy.py --voice=mandolin: 5.5 cents, the partner 0.45), its decay fitted to the Eclectic Mandolin's takes (examples/pluck_fit.py --voice=mandolin: 14.35 dB/s, steeply by register), and PICKED (tonelib.Plectrum): the scrape at the note's level to 5.5 kHz gone at 700 dB/s, the top partials struck 12 dB an octave over 1.5 kHz and gone at 400 dB/s (the take's top falls 24-42 dB by 0.1 s), the course crossed 14 ms apart. The take is re-amped dark, so its colour is not a target: fitted on flatness and how fast the top falls. Its other open courses KICKED through the bridge (contact, tuned a fourth low, D3 A3 E4 B4): the D course at its own harmonics 29-44 dB under 10 of 13 notes, the A seldom, the E and B hardly. Ben: 'Sounds good'"),
    (26, 8): (4, "a LAP STEEL fitted to David Long's (Pianobook, Lapsteel Articulations; examples/pluck_fit.py --voice=lapsteel): its six open strings -- the sustain (decay fit 17.4 -> 10.2 dB/s rms, the low harmonics 2-6 dB/s), the tone rolled back on its pickup (resonance 500 Hz, Q 0.5; lapsteel_tone.py), and its OTHER OPEN STRINGS answering through the bridge, each as tuned on that instrument, harmonic by harmonic where it lies near the note's (the E2 string's 2nd under an E3 at -14 dB, the take's -13, beating 1.7 Hz off) -- what Ben heard as 'more inharmonicity, especially lower'. Ben: 'Sounds great'"),
    (14, 8): (4, "St. Kathrin's church bell, Gelting (Pianobook, Zoom H5): its 19 modes fitted window by window to their level at the strike and decay -- the strike note an octave under the nominal (649.6 Hz), the flat hum (0.438) and the 1.125 ringing seconds, the superquint a doublet 3 Hz apart, the clang 4.2-13.7 gone in a second; within ~6 dB of the recording, mode by mode against the nominal, to 2.5 s (its noise beyond). Ben: \"Sounds amazing\""),
    (48, 8): (3, "a LAYERED variation (patch_map.LAYERED): the strings by register (cello, viola, violin) and the brass section's own router an octave above at -10 dB -- both GM sets' 48.8 is their strings with their brass 8va; the layer's level by Ben's ear of -4/-10/-16"),
    (61, 8): (3, "the brass section's router (tuba, trombones, trumpets by register), every register a detuned pair, +-4 cents half left and right -- MuseScore's 61.8, its section twice, panned apart; the spread asserted"),
    (27, 8): (3, "the Stratocaster into a chorus pedal (the swept bucket-brigade chorus CC93 makes), on at half by default -- GeneralUser's 27.8 is its clean guitar with a copy 7 cents up; the pedal's settings asserted"),
    (28, 8): (3, "the Stratocaster on position 4: neck (0.247) and middle (0.157) pickups in parallel -- their combs summed, the mean of two coils, the resonance up by sqrt 2 with the halved inductance -- through a cleaner amp (drive 0.3). The physics of the wiring; not fitted to a recording of one"),
    (4, 8): (3, "the Rhodes as a detuned pair (chorus._pair): the note 4 cents down and half left, a copy 4 up and half right, by level, the copy 7 ms behind -- MuseScore's 4.8 (its sample twice, +-4); the spread the GM sets', asserted"),
    (5, 8): (3, "the Wurlitzer as a detuned pair, as 4.8"),
    (16, 8): (3, "the drawbar organ on its SCANNER CHORUS, C3 (the stops table's scanner row): what GS's two detuned copies stand in for on an organ that cannot be detuned"),
    (17, 8): (3, "the percussive organ on its scanner chorus, C3, as 16.8"),
    (21, 8): (3, "the musette: GM 21's accordion with a third middle reed, M-16 / M / M+16 -- the wet reed's tuning measured on the Hohner, mirrored flat (asserted). Both GM sets' 21.8 is their accordion made wetter; no recording of a three-reed musette here (juskiddink's Paolo Soprani take is a dry register). Ben's pick of three"),
    (6, 8): (4, "the harpsichord's 8' and 4' together, both fitted stops (the stops table): what both GM sets' 6.8 plays, their harpsichord with a layer an octave up; Ben's pick of four (8'+8', 8'+4', 8'+8'+4'), the upper 8' left to draw for the full coupler"),
    (19, 8): (4, "the church organ's principal chorus to the fourth harmonic -- 8', 4', the principal quint 2 2/3', 2' -- every rank Pitea's recorded pipe (the stops table); clear and bright, short of the mixture (Ben's registration). GeneralUser's 19.8 is its organ an octave up, MuseScore's its organ coupled at 16': neither a plenum"),
    (38, 8): (3, "the ACID bass on the Moog (tonelib.MoogSynthBass3): one saw into a resonant ladder nearly shut, the contour snapping open to a low sustain, RES BASS on -- GeneralUser names it Acid Bass; a starting panel, the model checked against Ben's Messenger (re-measured on its new firmware: the cutoff law moved 4.5 octaves, convert_v5), at its capital's level. Ben: 'The synths sound great'"),
    (39, 8): (3, "the talking bass on the Moog (MoogSynthBass4): both GS sets' takes hold a peak h17-23 10-16 dB over its neighbours -- a square and the SUB through a resonant ladder left open, the cutoff tracking the key. Ben: 'great'"),
    (50, 8): (3, "the brighter, quicker string machine on the Moog (MoogSynthStrings3): two saws nine cents apart, the ladder further open with a touch of resonance, the swell a third of 50's. Ben: 'great'"),
    (62, 8): (3, "62's blat punchier on the Moog (MoogSynthBrass3): the pair six cents apart, the contour opening faster and further, a little resonance on its edge. Ben: 'great'"),
    (63, 8): (3, "63's soft brass on squares (MoogSynthBrass4): hollower, fourteen cents apart, slower to open. Ben: 'great'"),
    (124, 1): (3, "an ELECTRONIC TONE RINGER on the Moog (MoogTelephone2), fitted to GeneralUser GS's own (examples/telephone2_fit.py): OSC 2 a saw through a band pass for the piezo, LFO 1 a square switching it up a fifth at 14.6 Hz -- 1824/2736 Hz at C4, the upper 6.4 dB under (GU's 9.8), 8.6 dB rms over each tone's harmonics; sounds 2.8 octaves over where written. Ben: 'sound great'"),
    (125, 9): (3, "a hiss and LOW BURSTS (SfxBurstNoiseProperties), the weather's machinery fitted to GeneralUser GS's own (examples/weather_fit.py burst): the colour within ~1 dB from 320 Hz to 8 kHz, 100-400 Hz bursts ~1.6 a second at C4, transposed whole by the key. Ben: 'sound great'"),
    (107, 8): (4, "the TAISHOGOTO, fitted to Arthur Chanson's soprano (Pianobook; examples/pluck_fit.py --voice=taisho): each key a course, a low string and three an octave up a few cents apart; the small box barely radiating the low fundamental (its corner 600 Hz: E5's 3rd 11 dB over its 1st); decay on h1-h6; the 12-string's plectrum; THE PICK'S SWEEP across the course timed on all 81 takes (half together, half the trio 15-50 ms late); its open G2 DRONE a stop on the wheel (low: ringing in sympathy; high: struck with every stroke, TaishoDroneProperties fitted to its 24 strokes). Ben: 'The fit is otherwise great', 'Sounds great'"),
    (107, 9): (3, "(internal: the taishogoto's drone string alone, the bank its struck stop renders from -- 98 Hz, its own fundamental all but silent, decay 3.4 dB/s rms over 24 strokes, colour within ~10 dB 300 Hz-10 kHz)"),
    (30, 8): (3, "the distortion guitar HELD INTO FEEDBACK (tonelib.Feedback, examples/feedback_fit.py): a second after the pluck the partial nearest the loop's band (~800 Hz; 600-1100 on the Feedbacker's '69 Strat into a Super Reverb) swells in and holds while the rest dies, the amp distorting it with the note -- GeneralUser's 30.8 has no bloom; ours follows the real thing. Ben: 'They sound great'"),
    (31, 8): (4, "FEEDBACK ITSELF on a clean amp (GuitarFeedbackProperties), fitted to the Gretsch's clean G4 (Pianobook, OMS-1): the fundamental 21 dB over the pluck a second in (the take's 23), its odd harmonics -20/-18/-23 dB as the amp saturates (-25/-16/-21), sinking slowly while held -- as GeneralUser's 31.8 swells. Ben: 'They sound great'"),
    (24, 8): (4, "BEN'S OWN UKULELE, a Luna, concert size (G C E A, re-entrant, A440), recorded by him through his A6 for it (ukulele_ben/; examples/pluck_fit.py --voice=ukulele): its 52 chromatic notes staged; its strings' stiffness measured (B 2.7e-4, the nylon guitar's was 5x); its fast dark decay (the fundamental 15-45 dB/s); its box (a resonance at 800 Hz, a hollow at 1 kHz; 2.9 dB rms to 5 kHz); the finger's flesh a soft noise burst (the attacks' flatness matched); and ITS PITCH WANDERING 9 cents over a second after the strike's glide, a soft string under a fretting finger (Ben: 'more than the guitar model'). Its first 15 ms ~5-8 dB brighter over 2 kHz than his (a fingertip rounding the pluck, not modelled). Ben: 'Perfect. Sounds great'"),
    (125, 5): (3, "HELMHOLTZ'S DOUBLE SIREN (siren.py): two discs on one axle -- lower rows 8/10/12/18, upper 9/12/15/16, each row a stop (CC43/44) -- driven by AIR (velocity, aftertouch, CC2): its rotor's inertia measured on the fire siren and the VCSL siren whistle, singing only while blown and coasting silent after (the wail on a re-press); the mod wheel is the crank, the upper chest's angle, cancelling the 12-rows' fundamental at the top. Its tone is the fire siren's measured series: no recording of the instrument itself"),
}
# THE SFX VARIATIONS are the SFX set's keys played from the keyboard
# (patch_map.SFX_VARIATIONS, checked by examples/sfx_variations.py: at C4 each
# is its key's spectrum within the noise floor), so each carries its key's
# rating and note -- read from KIT_RATED, so the two cannot drift
# ...and the kit voices played from the keyboard the same way (115.8-118.8),
# each its key's rating, Standard's from PERC_RATED
KIT_VARIATIONS = {(115, 8): (0, 85), (116, 8): (48, 36), (117, 8): (24, 47), (118, 8): (25, 47)}


def _kit_var_rated():
    for (p, v), (kit, key) in KIT_VARIATIONS.items():
        r, note = PERC_RATED[key] if kit == 0 else KIT_RATED[kit][key]
        VAR_RATED[(p, v)] = (r, "set %d's key %d played from the keyboard (patch_map.melodic_sfx), "
                                "C4 at its kit pitch, transposed whole -- at C4 its key's spectrum "
                                "within 0.05-0.33 dB: %s" % (kit, key, note))


def _sfx_var_rated():
    for (p, v), key in patch_map.SFX_VARIATIONS.items():
        r, note = KIT_RATED[56][key]
        VAR_RATED[(p, v)] = (r, "the SFX set's key %d played from the keyboard, C4 at its "
                                "kit pitch (its gate, ring and level the kit's): %s" % (key, note))
    # ...and 125.10 "Calculating" (SC-88 Pro, SC-8850): the Morse keyboard
    # (percussion_map.MORSE_KIT), each key its character. Ben: "Call the
    # morse good"
    VAR_RATED[(125, 10)] = (3, "MORSE across the keyboard: each key a character of ITU-R M.1677-1 "
                               "(A-Z, 1-0, its punctuation, from middle C), sent once at 20 words a "
                               "minute on a sidetone at the key's pitch (percussion_map.MORSE_KIT; "
                               "Rhythm FX 2's 90 sends CALC). Ben: \"Call the morse good\"")


def _mt32_var_rated():
    """BANK 127, the MT-32 set: each tone its target's rating, read from
    RATED / PERC_RATED, so they cannot drift."""
    names = GM
    for i, (nm, to) in enumerate(patch_map.MT32_SET):
        if isinstance(to, tuple):
            r, note = PERC_RATED[to[1]]
            VAR_RATED[(i, 127)] = (r, "Standard's key %d played from the keyboard" % to[1])
        else:
            r = RATED[to][0]
            VAR_RATED[(i, 127)] = (r, "GM %d %s" % (to, names[to]))


# GM 2's settings-and-layers tones (patch_map.SC8850_CHEAP and MAP_TONES' map
# 3), heard as a group in examples/gm2_tones_demo.py
_GM2_HEARD_KEYS = [(0, 3 * 128 + 16), (3, 3 * 128 + 8), (16, 3 * 128 + 8), (16, 3 * 128 + 32),
                   (17, 3 * 128 + 32), (20, 16), (25, 33), (27, 23), (28, 24), (29, 4), (30, 26),
                   (33, 7), (48, 40), (56, 3), (57, 4)]
GM2_HEARD = {k: 'Ben, on examples/gm2_tones_demo.py: "sound good"' for k in _GM2_HEARD_KEYS}
# the plunger: no recording to fit, voiced by ear over three takes
# (examples/plunger_demo.py) -- the curve centre-weighted at Ben's suggestion
GM2_HEARD[(59, 2)] = ('the plunger, aftertouch opening it (no recording; voiced by ear). '
                      'Ben, on examples/plunger_demo.py: "fine for now"')
# GM 2's last 21 (2026-10-26), heard together in examples/gm2_last_demo.py
_GM2_LAST = 'Ben, on examples/gm2_last_demo.py: "Sounds great"'
GM2_HEARD.update({k: _GM2_LAST for k in ((5, 10), (5, 32), (46, 24), (53, 40), (55, 1), (55, 2), (55, 3), (87, 7))})


def _sc88_var_rated():
    """THE SC-88 MAP'S CHEAP TONES (patch_map.SC88_CHEAP): each its source
    voice's rating -- the program it aliases or sets, its layers' lowest, the
    kit key it plays -- and what was done to it."""
    names = GM
    tones = [((p, b), how, "SC-88 map: ") for (p, b), (nm, how) in patch_map.SC88_CHEAP.items()]
    tones += [((p, b), how, "SC-8850 map: ") for (p, b), (nm, how) in
              getattr(patch_map, "SC8850_CHEAP", {}).items()]
    tones += [((p, 128 * m + b), how, "%s map's own: " % patch_map.MAP_LABELS[m])
              for (m, p, b), (nm, how) in getattr(patch_map, "MAP_TONES", {}).items()]
    for (p, b), how, whose in tones:
        kind = how[0]
        if kind == "alias":
            r, note = RATED[how[1]][0], "GM %d %s's voice" % (how[1], names[how[1]])
        elif kind == "var":
            r, note = VAR_RATED[how[1]][0], "%d.%d's voice" % how[1]
        elif kind in ("kit", "rev"):
            kr = PERC_RATED[how[1]] if how[2] == 0 else KIT_RATED[how[2]].get(how[1], PERC_RATED.get(how[1]))
            r = kr[0]
            note = "set %d's key %d from the keyboard%s" % (how[2], how[1], ", played backwards" if kind == "rev" else "")
        elif kind == "set":
            r = RATED[how[1]][0]
            note = "GM %d %s with %s" % (how[1], names[how[1]], ", ".join(
                "%s=%s" % (k, ("%#x" % v) if k == "default_stops" else v) for k, v in how[2].items()))
        else:
            # a layer is a GM program, ("kit", key, set) or ("set", program, {attrs})
            def _lr(src):
                if isinstance(src, tuple) and src[0] == "kit":
                    kr = KIT_RATED.get(src[2], {}).get(src[1]) or PERC_RATED.get(src[1])
                    return kr[0], "set %d's key %d" % (src[2], src[1])
                if isinstance(src, tuple) and src[0] == "set":
                    return RATED[src[1]][0], "GM %d with %s" % (src[1], ", ".join(
                        "%s=%s" % kv for kv in src[2].items()))
                return RATED[src][0], "GM %d" % src
            r = min(_lr(l[0])[0] for l in how[1])
            note = "layered: " + " + ".join("%s%s%s%s" % (_lr(l[0])[1], (" %+d st" % l[1]) if l[1] else "",
                                                       (" %+.0f dB" % l[2]) if l[2] else "",
                                                       (" vel %d-%d" % (l[3], l[4])) if len(l) > 3 else "")
                                            for l in how[1])
        if (p, b) in GM2_HEARD:
            note += ". " + GM2_HEARD[(p, b)]
        VAR_RATED[(p, b)] = (r, whose + note)
    # ...AND ITS SYNTH TONES (sc88_synth.SC88_SYNTH): Moog panels, a 3 as the
    # bank-8 synths are -- the engine is fitted to Ben's Messenger, the panel
    # is voiced from what the tone is, not fitted to a recording of it
    try:
        from sc88_synth import SC88_SYNTH, MAP_SYNTH
    except ImportError:
        SC88_SYNTH, MAP_SYNTH = {}, {}
    SC88_SYNTH = {**SC88_SYNTH, **{(p, 128 * m + b): t for (m, p, b), t in MAP_SYNTH.items()}}
    for (p, b), (nm, base, pan) in SC88_SYNTH.items():
        if (p, b) in patch_map.VARIATIONS:
            VAR_RATED[(p, b)] = (3, "SC-88 map: a Moog panel, %s's with %s changed (sc88_synth.py); "
                                    "voiced from what the tone is, the engine fitted to Ben's Messenger"
                                 % (base.replace("Moog", "the "), ", ".join(sorted(pan))))
            if nm.startswith(("MG", "WowMG")):
                VAR_RATED[(p, b)] = (3, "SC-88 map: the Minimoog fitted to a Model D's held bass (sc88_synth."
                                        "MINIMOOG, examples/minimoog_fit.py: Garzul's, CC0, C1 and C4, 3 dB "
                                        "rms rendered), with %s changed. Ben, on examples/mg_demo.py: \"They sound "
                                        "great\"" % (", ".join(
                                            sorted(k for k in pan if pan[k] != __import__("sc88_synth").MINIMOOG.get(k)))
                                            or "nothing"))
            if nm in ("OB Brass", "OB Square", "OB Saw 1", "OB Saw 2", "OB Saw Lead"):
                VAR_RATED[(p, b)] = (3, "SC-88 map: the Oberheim fitted to an OB-8's held chords (sc88_synth."
                                        "OBERHEIM, examples/obx_fit.py: Analogist's jungle pad, CC0, ten "
                                        "four-note chords, 3.2 dB rms rendered), with %s changed" % ", ".join(
                                            sorted(k for k in pan if pan[k] != __import__("sc88_synth").OBERHEIM.get(k))))
            if nm.startswith("JUNO") and "JUNO" in __import__("sc88_synth").__dict__ and \
                    pan.get("insertion_efx") in (__import__("sc88_synth").JUNO_CHORUS1, __import__("sc88_synth").JUNO_CHORUS2):
                VAR_RATED[(p, b)] = (3, "SC-88 map: the Juno fitted to a Juno-6's notes (sc88_synth.JUNO, "
                                        "examples/juno_fit.py: Modular Samples, CC0, the PW Pluck C2-C6 over its "
                                        "whole pluck), its chorus the tone's own Stereo Chorus, with %s changed"
                                     % ", ".join(sorted(k for k in pan if pan[k] != __import__("sc88_synth").JUNO.get(k))))
            if nm in ("TB303 Bass 2", "Kicked TB303", "TB303 Saw Bs", "Rubber303 Bs", "Reso 303 Bs", "303 Sqr Bs",
                      "TB303 DistBs", "TB Lead", "Acid Guitar1", "Acid Guitar2"):
                VAR_RATED[(p, b)] = (3, "SC-88 map: the TB-303 fitted to a TB-303's note (sc88_synth.TB303, "
                                        "examples/tb303_fit.py: DJMini's, CC0, its resonant peak through the pluck "
                                        "0.07 octave rms rendered; the held tone 4.1 dB, the diode ladder's broader "
                                        "peak left), with %s changed" % (", ".join(
                                            sorted(k for k in pan if pan[k] != __import__("sc88_synth").TB303.get(k)))
                                            or "nothing"))
            if nm in ("Syn.Bass101", "Reso SHBass", "SH101Bass 1", "SH101Bass 2", "SH101 Bass 3", "SH-101 Saw"):
                VAR_RATED[(p, b)] = (3, "SC-88 map: the SH-101 as the Juno-6's fitted voice without its chorus "
                                        "(sc88_synth.SH101: the same IR3109 and VCO section; no clean SH-101 note "
                                        "exists under CC0 -- the refs are a bassline with its knobs moving and "
                                        "resonance sweeps), one VCO, with %s changed" % ", ".join(
                                            sorted(k for k in pan if pan[k] != __import__("sc88_synth").SH101.get(k))))
            if nm in ("SH-5 Brass", "SH-5 Bs.Lead"):
                VAR_RATED[(p, b)] = (3, "SC-88 map: the SH-5 READ, not fitted, from xanthorp's sample-and-hold "
                                        "patterns (sc88_synth.SH5, examples/sh5_fit.py: each step a note at its "
                                        "own cutoff, 9 dB rms -- no held SH-5 note under CC0), with %s changed"
                                     % ", ".join(sorted(k for k in pan if pan[k] != __import__("sc88_synth").SH5.get(k))))
            if nm in ("CS Bass", "CS Saw", "CS Saw Lead"):
                VAR_RATED[(p, b)] = (3, "SC-88 map: the CS fitted to a Yamaha CS-30L's bass (sc88_synth.CS, "
                                        "examples/cs_fit.py: Modular Samples, CC0; 5.0 dB on the harmonics, 0.31 "
                                        "octave on the contour; the 2-pole by design, the takes agreeing), with %s "
                                        "changed" % ", ".join(sorted(k for k in pan if pan[k] != __import__("sc88_synth").CS.get(k))))
            if nm.startswith(("JP", "JPMG")):
                VAR_RATED[(p, b)] = (3, "SC-88 map: the JUPITER-8 fitted on the record (sc88_synth.JUPITER, "
                                        "examples/sepways_fit.py), one pass, with %s changed. Ben, on "
                                        'examples/jp8_demo.py: "Sounds great"' % ", ".join(
                                            sorted(k for k in pan if pan[k] != __import__("sc88_synth").JUPITER.get(k))))
    # ...and the SC-8850 map's (sc88_synth.SC8850_SYNTH), GM 2's last, under
    # their own bank or the SC-8850 map's key
    try:
        from sc88_synth import SC8850_SYNTH
    except ImportError:
        SC8850_SYNTH = {}
    for (p, b), (nm, base, pan) in SC8850_SYNTH.items():
        k = (p, 128 * 4 + b) if (p, b) in patch_map.MAP_OTHER.get(4, ()) else (p, b)
        if k in patch_map.VARIATIONS:
            VAR_RATED[k] = (3, "SC-8850 map: a Moog panel, %s's with %s changed (sc88_synth.py); "
                               "voiced from what the tone is, the engine fitted to Ben's Messenger. %s"
                            % (base.replace("Moog", "the "), ", ".join(sorted(pan)), _GM2_LAST))


def variations():
    if not any(k in VAR_RATED for k in patch_map.SFX_VARIATIONS):
        _sfx_var_rated()
        _kit_var_rated()
        _mt32_var_rated()
        _sc88_var_rated()
    """[(program, bank, GS name, class or None, rating or None, note)], every
    variation GS names; one not built plays its capital tone."""
    built = set(patch_map.VARIATIONS)
    unrated = sorted(built - set(VAR_RATED))
    unknown = sorted(set(VAR_RATED) - built)
    if unrated or unknown:
        raise SystemExit("VAR_RATED does not match patch_map.VARIATIONS: unrated %s, unknown %s"
                         % (unrated, unknown))
    out = []
    for (p, v), name in sorted(patch_map.VARIATION_NAMES.items()):
        if v >= 127:
            continue                       # the MT-32 set (mt32_md); the maps' own (sound_canvas_md)
        if (p, v) in built:
            cls = patch_map.property_class_for_program(patch_map.VariationProgram(p, v))
            r, note = VAR_RATED[(p, v)]
            out.append((p, v, name, cls.__name__, r, note))
        else:
            out.append((p, v, name, None, None, "not built: plays %d %s" % (p, GM[p])))
    return out


def variations_md():
    rows = variations()
    sc88 = set(getattr(patch_map, "SC88_CHEAP", {})) | set(getattr(patch_map, "SC8850_CHEAP", {}))
    r55 = [r for r in rows if (r[0], r[1]) not in sc88]
    nb = sum(1 for r in r55 if r[3])
    L = ["## Variations: the GS banks (CC0)\n",
         "A GS bank select (CC0 = bank, then the program) picks a variation tone",
         "under a program (SC-55 owner's manual p.68). %d of the SC-55's %d are built," % (nb, len(r55)),
         "and %d of the SC-88 map's (Roland's SC-88Pro manual; gs_inventory.md);" % len(sc88),
         "one not built plays its capital tone, as a Sound Canvas does.\n",
         "| program.bank | map | GS name | class | | notes |",
         "|---|---|---|---|---|---|"]
    for p, v, name, cls, r, note in rows:
        L.append("| %d.%d | %s | %s | %s | %s | %s |"
                 % (p, v, "SC-88" if (p, v) in sc88 else "SC-55", name,
                    "`%s`" % cls.replace("Properties", "") if cls else "--",
                    "**%d**" % r if r is not None else "", note))
    L.append("")
    return "\n".join(L)


def mt32_md():
    variations()
    L = ["## Bank 127: the MT-32 set\n",
         "GS's bank 127 is the MT-32's 128 tones on the GS programs (SC-55 owner's",
         "manual p.69), for a file that selects it. Each plays its nearest voice",
         "here (patch_map.MT32_SET) at that voice's level, rated as that voice.\n",
         "| program.127 | MT-32 tone | plays | |",
         "|---|---|---|---|"]
    for i, (nm, to) in enumerate(patch_map.MT32_SET):
        r, note = VAR_RATED[(i, 127)]
        L.append("| %d.127 | %s | %s | **%d** |" % (i, nm, note, r))
    L.append("")
    return "\n".join(L)


# THE SOUND CANVAS MAPS (examples/gs_maps.py: the SC-88Pro owner's manual's
# instrument list, its Native, SC-88 and SC-55mkII maps side by side, and the
# original SC-55's p.68 list, which VARIATION_NAMES follows): each map's tones
# against what we have built, rated as the GM table and the variations are.
# A later map can put ANOTHER TONE under a number we built (the SC-88's 4.8 is
# "St.Soft EP", not our detuned pair): those are not counted as built. A name
# that differs only in its spelling ("Syn.Bass 3", "Acid Bass") is the same
# tone, renamed.
SC_COL_MAP = {"sc55": 1, "sc88": 2, "native": 3, "sc8850": 4}
SC_OTHER = {col: patch_map.MAP_OTHER[m] for col, m in SC_COL_MAP.items()}
SC_MAPS = (("sc55o", "SC-55"), ("sc55", "SC-55mkII"), ("sc88", "SC-88"), ("native", "SC-88Pro"),
           ("sc8850", "SC-8850"))


def map_rating(col, k):
    """WHAT A MAP PLAYS for (program, bank) (patch_map.map_bank, as a file's
    CC32 selects it): its own tone's rating, ours, or None -- not built, the
    capital plays."""
    if k[1] == 0:
        return RATED[k[0]][0]
    v = patch_map.map_bank(k[0], k[1], SC_COL_MAP.get(col, 0))
    if not v or (k[0], v) not in patch_map.VARIATIONS or (k[0], v) not in VAR_RATED:
        return None
    return VAR_RATED[(k[0], v)][0]


GM2_TSV = os.path.expanduser("~/Documents/refs/roland/gm2_instruments.tsv")
# GM 2's drum sets (SC-8850 owner's manual p.215): its program -> ours
GM2_KITS = {0: "Standard", 8: "Room", 16: "Power", 24: "Electronic", 25: "Analog (TR-808)",
            32: "Jazz", 40: "Brush", 48: "Orchestra", 56: "SFX"}


def gm2():
    """GM 2's sound set (examples/gm2_list.py): [(program, LSB, name, the
    Sound Canvas tone it is -- (map column, bank) -- and its rating or None)].
    Every GM 2 tone is a Sound Canvas tone under its own name: matched by
    program and name on the SC-8850's list, then the earlier maps'."""
    import csv
    import re
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gs_maps
    if not (os.path.exists(GM2_TSV) and os.path.exists(gs_maps.TSV8850)):
        return None
    variations()
    norm = lambda t: re.sub(r"[\s.\-]", "", t).lower()
    by = {}
    for r in list(csv.reader(open(gs_maps.TSV8850), delimiter="\t"))[1:]:
        for i, col in ((2, "sc8850"), (3, "native"), (4, "sc88"), (5, "sc55")):
            by.setdefault((int(r[0]), norm(r[i])), (col, int(r[1])))
    out = []
    for p, b, nm in list(csv.reader(open(GM2_TSV), delimiter="\t"))[1:]:
        p, b = int(p), int(b)
        hit = by.get((p, norm(nm)))
        # what the renderer plays for it (patch_map.gm2_bank), rated as that is
        v = patch_map.gm2_bank(p, b) if b else 0
        r = RATED[p][0] if not b else (VAR_RATED[(p, v)][0] if v and (p, v) in VAR_RATED else None)
        out.append((p, b, nm, hit, r))
    return out


def sound_canvas():
    """([(map name, tones, built, other tone, {rating: n})],
    [(family, [(built, tones) per map])], the SC-88 map's missing [(p, b, name, kind)])
    -- None if the manual's list has not been parsed (gs_maps.py parse)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gs_maps
    if not os.path.exists(gs_maps.TSV):
        return None
    variations()                                     # fills VAR_RATED
    R = gs_maps.load()
    later = set(getattr(patch_map, "SC88_CHEAP", {})) | set(getattr(patch_map, "SC8850_CHEAP", {}))
    try:
        from sc88_synth import SC88_SYNTH
        later |= set(SC88_SYNTH)
    except ImportError:
        pass
    tones = {"sc55o": [(p, 0) for p in range(128)] +
             [k for k in patch_map.VARIATION_NAMES if k[1] < 127 and k not in later]}
    for col in ("sc55", "sc88", "native"):
        tones[col] = [(r["program"], r["bank"]) for r in R
                      if r[col] not in ("-----", "", "+ -----")]
    # the SC-8850's, from its own list (which sets the other three beside it)
    if os.path.exists(gs_maps.TSV8850):
        import csv
        tones["sc8850"] = [(int(r[0]), int(r[1])) for r in
                           list(csv.reader(open(gs_maps.TSV8850), delimiter="\t"))[1:]
                           if r[2] not in ("-----", "", "+ -----")]
    else:
        tones["sc8850"] = []

    rating = map_rating
    maps, fams = [], []
    for col, name in SC_MAPS:
        rs = [rating(col, k) for k in tones[col]]
        hist = {r: rs.count(r) for r in range(5)}
        other = sum(1 for k in tones[col] if k in SC_OTHER.get(col, ()) and rating(col, k) is None)
        maps.append((name, len(rs), sum(r is not None for r in rs), other, hist))
    for start, fam in FAMILY:
        row = []
        for col, _ in SC_MAPS:
            ks = [k for k in tones[col] if start <= k[0] < start + 8]
            row.append((sum(rating(col, k) is not None for k in ks), len(ks)))
        fams.append((fam, row))
    miss = sorted((r["program"], r["bank"], r["sc88"], gs_maps.KIND.get((r["program"], r["bank"]), "?"))
                  for r in R if r["sc88"] not in ("-----", "", "+ -----")
                  and rating("sc88", (r["program"], r["bank"])) is None)
    return maps, fams, miss


SC_KINDS = (("synth", "a Moog panel, voiced by ear"),
            ("refit", "an articulation of one we have, wanting a fit to a reference"),
            ("new", "an instrument we have not modelled, wanting references"),
            ("other", "a different tone under a number we built"))


def gm2_md():
    """GM 2's sound set: how it is read, and what is still to build."""
    g = gm2()
    if g is None:
        return ""
    todo = [(p, b, nm) for p, b, nm, _h, r in g if r is None]
    L = ["## General MIDI 2: the sound set (MSB 121)\n",
         "GM 2's 256 tones (SC-8850 owner's manual, \"GM 2 Instrument List\"; examples/gm2_list.py).",
         "GM 2 numbers its variations its own way -- its Piano 1w is LSB 1, the Sound Canvas's",
         "bank 8 -- but every one is a Sound Canvas tone under its own name, so a GM 2 LSB plays",
         "the tone of that name (patch_map.gm2_bank: the SC-8850 map's, else an earlier map's),",
         "rated as that tone is; one not built plays the capital. GM 2's nine drum sets are the",
         "Sound Canvas's (Standard, Room, Power, Electronic, Analog = TR-808, Jazz, Brush,",
         "Orchestra, SFX), all built.\n",
         "**Still to build (%d):** %s.\n" % (len(todo), ", ".join("%d.%d %s" % t for t in todo))]
    return "\n".join(L) + "\n"


def sound_canvas_md():
    sc = sound_canvas()
    if sc is None:
        return ""
    maps, fams, miss = sc
    L = ["## Sound Canvas: the GS maps\n",
         "Each Sound Canvas's map of tones (the SC-55's own owner's manual p.68; the SC-55mkII,",
         "SC-88 and SC-88Pro maps from the SC-88Pro manual's list), against ours. A tone is built",
         "when we play it, as a program or a variation, and rated as the tables above rate it.",
         "A later map can put another tone under a number we built; that one is not counted.",
         "The maps' totals are in the Summary at the top; still to build: " + ", ".join(
             "%s %d%s" % (name, n - nb, (" (%d another tone)" % other) if other else "")
             for name, n, nb, other, h in maps) + ".\n"]
    own = sorted((v >> 7, p, v & 0x7F, nm) for (p, v), nm in patch_map.VARIATION_NAMES.items()
                 if v >> 7 in patch_map.MAP_LABELS and (p, v) in patch_map.VARIATIONS)
    if own:
        L += ["", "A file selects a map with bank select LSB (CC32: 1 SC-55, 2 SC-88, 3 SC-88Pro, 4 SC-8850; "
              "none, ours). Where a map holds another tone under a number, it is built as its own: "
              + ", ".join("%s %d.%d %s (%s)" % (patch_map.MAP_LABELS[m], p, b, nm,
                                                  VAR_RATED[(p, 128 * m + b)][0])
                          for m, p, b, nm in own) + "."]
    L += ["", "### By family: built of each map's tones\n",
          "| family | " + " | ".join(nm for _, nm in SC_MAPS) + " |",
          "|---|" + "---|" * len(SC_MAPS)]
    for fam, row in fams:
        L.append("| %s | %s |" % (fam, " | ".join("%d/%d" % x for x in row)))
    L += ["", "### The SC-88 map's %d still to build, by what they take\n" % len(miss)]
    for k, what in SC_KINDS:
        rs = [m for m in miss if (m[3] if (m[0], m[1]) not in SC_OTHER["sc88"] else "other") == k]
        if rs:
            L.append("**%s** (%d: %s): %s\n" % (k, len(rs), what,
                                               ", ".join("%d.%d %s" % (p, b, nm) for p, b, nm, _ in rs)))
    return "\n".join(L) + "\n"


# THE SOUND CANVAS'S EFFECTS, rated on the voices' own scale (Ben): 4
# validated against a target -- a recording of the device, or the hardware's
# output of a file judged against ours by ear; 3 validated semantically by ear
# (not necessarily Roland's mechanism); 2 specific, from theory (Roland's
# tables, our models); 1 a stand-in; 0 not built (the sound passes dry).
# THE REVERB IS NOT A DEVICE TO EMULATE: on a Sound Canvas it is the module's
# way of giving the music a space, as a SoundFont player's is, and our
# physical rooms are how we do that job -- the question is whether the space
# the arranger asked for is the space we give.
EFFECTS_RATED = [
    ("Reverb (system)", 3, "the macro picks one of our physical rooms by what it is for, small to large as "
     "Roland's run: Room 1-3 studio, chamber, a larger chamber; Hall 1 our concert hall, Hall 2 a grand one "
     "(Musikverein-scale); Plate an EMT 140 plate and Delay / Panning Delay a 100 ms echo, on the studio's "
     "walls (roomtail.device_ir) -- heard in examples/gs_reverb_demo.py (Ben: those all sound good). Its level "
     "and time scale the tail; CC91 a distance. Tokei was validated in the chamber under Hall 1 (now our hall: "
     "Ben chose the studio for it). Character, Pre-LPF, pre-delay and a per-drum reverb send not yet"),
    ("Controller matrix (GS 40 2x, GM2 09 0s)", 3, "ctrlmatrix.py: GS's six sources (mod, bend, both "
     "aftertouches, the assignable CC1/CC2) and GM2's (channel and poly pressure, any CC) into amplitude (the "
     "fader's rows; an organ's gates), pitch (the bend row), cutoff (brightness at onset), LFO pitch depth (a "
     "sine on the bend row, so a held note's aftertouch vibrato moves), LFO amplitude depth (sidebands on rows "
     "of their own) and LFO rate -- measured in examples/ctrlmatrix_demo.py (Ben: phase 1 sounds good). The "
     "mod wheel's own vibrato (GS's 47-cent default) held out of files (TUNING_MOD_VIBRATO), LFO filter depth "
     "and live not yet"),
    ("Chorus (system)", 3, "chorus.gs_copies: Roland's eight macros, a line swept by one LFO, "
     "read at two outputs in opposite phase, fed back; laws GM 2's (rate, depth, feedback), the "
     "delay's chosen (0.2 ms a step); the wet share held as CC93's. To reverb / to delay, "
     "per-drum chorus sends, not yet"),
    ("Delay (system)", 3, "gsdelay.py: Roland's three taps, time table, ten macros, feedback "
     "through the center; CC94 (in a GS file) and the drum keys' sends; level laws chosen "
     "(linear over 127). Delay to reverb not yet a send of its own"),
    ("EQ (system)", 2, "the SC-88's two shelves at 200/400 Hz and 3/6 kHz, per part on/off, "
     "first-order (the order chosen)"),
]
EFX_TYPES = ("Stereo-EQ", "Spectrum", "Enhancer", "Humanizer", "Overdrive", "Distortion",
             "Phaser", "Auto Wah", "Rotary", "Stereo Flanger", "Step Flanger", "Tremolo",
             "Auto Pan", "Compressor", "Limiter", "Hexa Chorus", "Tremolo Chorus",
             "Stereo Chorus", "Space D", "3D Chorus", "Stereo Delay", "Mod Delay",
             "3 Tap Delay", "4 Tap Delay", "Tm Ctrl Delay", "Reverb", "Gate Reverb",
             "3D Delay", "2 Pitch Shifter", "Fb P.Shifter", "3D Auto", "3D Manual",
             "Lo-Fi 1", "Lo-Fi 2", "OD -> Chorus", "OD -> Flanger", "OD -> Delay",
             "DS -> Chorus", "DS -> Flanger", "DS -> Delay", "EH -> Chorus", "EH -> Flanger",
             "EH -> Delay", "Cho -> Delay", "FL -> Delay", "Cho -> Flanger", "Rotary Multi",
             "GTR Multi 1", "GTR Multi 2", "GTR Multi 3", "Clean Gt Multi 1",
             "Clean Gt Multi 2", "Bass Multi", "Rhodes Multi", "Keyboard Multi",
             "Cho / Delay", "FL / Delay", "Cho / Flanger", "OD1 / OD2", "OD / Rotary",
             "OD / Phaser", "OD / AutoWah", "PH / Rotary", "PH / AutoWah")


# THE INSERTION TYPES BUILT (gsefx.BUILT), each on our models: the OD a gain
# stage in front of the voice's valve (gsefx.od_gain), its makeup and the
# Level after it, the EQ after the valve on its products too
EFX_RATED = {
    "Overdrive": (3, "the OD a gain stage in front of the part's valve (tubeamp, its gains multiplying), its output makeup, the 1x12 cabinet; low/high gains after it. Amp Type (Small/BltIn/2-/3-Stack) one speaker for all; heard in the OD -> Chorus/Flanger/Delay demos (Ben, 2026-10-21: those sound great)"),
    "Distortion": (3, "as Overdrive, with more gain; heard on storm_pro (kathie, SC-88Pro), its part 8 clean electric guitar at Drive 70 (Ben: sounds good)"),
    "GTR Multi 1": (3, "compressor (decay slowed, its Attack the onset's rise), OD and amp, chorus/flanger (chorus.gs_copies), its delay (gsdelay); every type at Roland's own defaults (gs_efx_params); heard in its demo, +20.6 dB over the dry guitar at the defaults (Ben, 2026-10-22: sounds good; louder, but not crazy loud)"),
    "GTR Multi 2": (4, "compressor, OD and amp, 3-band EQ after the valve, chorus/flanger -- VALIDATED against Tokei on the SC-88Pro for the settings it uses (Ben: Crazy Train's crunch, a little less smashed; the makeup lowered by ear); Amp Type and the compressor's Attack not yet built"),
    "GTR Multi 3": (4, "as GTR Multi 1, with its wah (efxfilter: a resonant LPF/BPF at its pedal, where the file moves it); heard on our guitar riff (Ben: \"Those all sound great\"); SENSATIO's six overdriven guitars through it, the wah on CC16 (the file's control source), once port B's exclusive reached their parts (Ben, 2026-10-23: \"sounds incredible. The effects are insane in it\")"),
    "Stereo-EQ": (3, "two shelves at their own corners and two peaking mids (gsefx.eq_gain), every partial; heard on sysex_01 (Ben: \"These all sound great\")"),
    "Space D": (3, "chorus.gs_copies, two outputs half a turn apart, pre-delay and rate from Roland's tables, Balance the share; heard on SENSATIO"),
    "Stereo Chorus": (3, "as Space D, its Phase and pre-filter (the LPF; its HPF not built); heard in its demo (Ben, 2026-10-21: these all sound great)"),
    "Hexa Chorus": (3, "six voices spread in delay, depth and pan by its Dev parameters (0.5 ms a Pre Dly Dev step, chosen); heard in its demo (Ben, 2026-10-21: these all sound great)"),
    "Tremolo Chorus": (3, "the chorus and the tremolo pass (half depth, chosen); heard in its demo (Ben, 2026-10-21: these all sound great)"),
    "3D Chorus": (3, "the chorus's outputs at 60 degrees, past the speakers; heard in its demo (Ben, 2026-10-21: these all sound great)"),
    "Stereo Delay": (3, "gsdelay: left and right taps each looping at its own period, feedback (cross for ping-pong), phase inversion, HF damping; heard on our riff (Ben: \"They sound great\")"),
    "Mod Delay": (3, "the Stereo Delay with its modulation as the repeats' vibrato; heard on our riff"),
    "3 Tap Delay": (3, "centre, left and right taps, the centre's loop; heard on our riff"),
    "4 Tap Delay": (3, "four taps spread left to right (chosen); heard on our riff"),
    "Tm Ctrl Delay": (3, "one tap at its time, placed by its pan (its time's glide under control not built); heard on our riff"),
    "3D Delay": (3, "centre tap and two at 60 degrees; heard on our riff"),
    "Rotary": (3, "our Leslie at the type's rotor speeds, switched by Speed, Accl through our measured spin-ups, the rotors' levels -- RECORDED as Roland's is: two mics round the cabinet (Separate, 0-180 degrees), each to its speaker with its own swing and Doppler; heard on our Rhodes riff, mono and then with its two mics (Ben: \"Those sound awesome\", \"Sounds great\")"),
    "Rotary Multi": (3, "the Rotary with its OD (the valve) and EQ before the rotors; heard in its demo (Ben, 2026-10-21: those sound awesome)"),
    "Tremolo": (3, "the tremolo pass, Roland's five waves as Fourier series, the depth dipping the level; heard on our riff"),
    "Auto Pan": (3, "the same across the ears; heard on our riff"),
    "Stereo Flanger": (3, "the chorus device with a flanger's swing, Roland's pre-delay and feedback, its outputs apart by its Phase; heard on our riff (Ben: \"sound great\")"),
    "3D Manual": (3, "the part at the type's Azimuth, past the speakers and behind (tonelib pan_angle); heard on our riff (Ben: \"sound great\")"),
    "3D Auto": (3, "the same, turning at its Speed; each note where its onset finds it; heard on our riff (Ben: \"sound great\")"),
    "2 Pitch Shifter": (3, "two shifted voices as gsdelay taps (Coarse, Fine, delay, pan, L.Bal); heard on our riff (Ben: \"sound great\")"),
    "Fb P.Shifter": (3, "a shifted tap whose repeats shift again round the loop; heard on our riff (Ben: \"sound great\")"),
    "OD -> Chorus": (3, "the valve's gain stage and guitar cabinet, then the chorus (gs_copies); heard on our riff (Ben: \"sound great\")"),
    "OD -> Flanger": (3, "the same with the flanger; heard on our riff (Ben: \"sound great\")"),
    "OD -> Delay": (3, "the same with a gsdelay tap; its dry and effect by Bal; heard on our riff (Ben: \"sound great\")"),
    "DS -> Chorus": (3, "as OD -> Chorus with the distortion's gain; heard on our riff (Ben: \"sound great\")"),
    "DS -> Flanger": (3, "as OD -> Flanger with the distortion's gain; heard on our riff (Ben: \"sound great\")"),
    "DS -> Delay": (3, "as OD -> Delay with the distortion's gain; heard on our riff (Ben: \"sound great\")"),
    "Cho -> Delay": (3, "the chorus and a delay tap (our passes run the delay first); heard on our riff (Ben: \"sound great\")"),
    "FL -> Delay": (3, "the flanger and a delay tap; heard on our riff (Ben: \"sound great\")"),
    "Clean Gt Multi 1": (3, "compressor, EQ, chorus/flanger and delay, as the guitar multis'; heard on our riff (Ben: \"sound great\")"),
    "Bass Multi": (3, "compressor, OD, EQ, chorus/flanger, the 4x10 bass cabinet; heard on our riff (Ben: \"sound great\")"),
    "Phaser": (3, "efxfilter: four all-passes at the swept corner, its resonance and mix, on every partial (the lobe kernel's filter_grid); heard on our riff"),
    "Auto Wah": (3, "efxfilter: a resonant LPF/BPF swept up (or down) from its Manual by its LFO, and opened by its Sens (the part's notes' envelope); heard on our riff and a Clav (Ben: \"sounds great\")"),
    "Step Flanger": (3, "efxfilter: the flanger's comb, its line swept in steps; heard on our riff"),
    "Humanizer": (3, "efxfilter: three formants of its vowel (a/i/u/e/o), gliding at its Accel; its drive the valve's gain stage; heard on a Moog lead"),
    "Lo-Fi 1": (3, "efxbus, the part's own bus: held to a lower rate, quantised to fewer bits (Type 1-9, chosen), its pre and post low-passes; heard on an EP and sysex_01 (Ben: \"sounds great\")"),
    "Compressor": (3, "efxbus: a level-following gain at the output's scale, 10-40 dB down at 8:1, attack 1-50 ms (chosen); heard on our guitar riff"),
    "Limiter": (3, "efxbus: the compressor at its Threshold and Ratio, Release 10 ms-1 s (chosen); heard on our guitar riff"),
    "Enhancer": (3, "efxbus: what lies above 2 kHz saturated, its harmonics mixed back by Mix; heard on an EP"),
    "Lo-Fi 2": (3, "efxbus: its rate and bits, a filter after, and noises heard through silence -- a radio's detune and static, white/pink, a record's crackle (33/45/78 rpm), mains hum; heard on an EP (Ben: \"sounds great\")"),
    "Gate Reverb": (3, "efxbus: a noise burst Gate Time long convolved with the part -- Norm, Reverse, the two Sweeps; heard on Melodic Tom"),
    "Reverb": (3, "efxbus: a decaying noise response per ear, its highs dying to HF Damp, six types by density, tail and early reflections (chosen); heard on an EP"),
    "Spectrum": (3, "eight fixed peaking bands at the manual's frequencies, each partial's gain at its own; heard on a piano"),
    "EH -> Chorus": (3, "the chorus's copies, then the Enhancer on the part's bus (after them: the other way about); heard on an EP (Ben: \"sounds great\")"),
    "EH -> Flanger": (3, "the flanger, then the Enhancer's bus; heard on a guitar"),
    "EH -> Delay": (3, "a delay tap, then the Enhancer's bus; heard on an EP"),
    "Cho -> Flanger": (3, "the chorus's copies, then a moving comb (efxfilter) on every row, the copies' too: in its order; heard on strings"),
    "Clean Gt Multi 2": (3, "an auto wah (efxfilter), the EQ, chorus/flanger and its delay; heard on a guitar"),
    "Rhodes Multi": (3, "Enhancer (the bus), phaser (efxfilter), chorus/flanger, tremolo/pan; heard on an EP"),
    "Keyboard Multi": (3, "ring modulator (each partial's f +- Hz sidebands as gsdelay taps), EQ, pitch shifter, phaser, delay -- the series unrolled into a tap per path; heard on an EP"),
    "Cho / Delay": (3, "TWO BRANCHES: the part's rows the chorus's, a copy on its virtual channel the delay's, each at its own Level and Pan (a gain across the ears; the chorus's copies keep its +-30 degree outputs); heard (Ben: \"They all sound great\")"),
    "FL / Delay": (3, "the flanger's branch and the delay's, in parallel; heard (Ben: \"They all sound great\")"),
    "Cho / Flanger": (3, "the chorus's branch and the flanger's, in parallel; heard (Ben: \"They all sound great\")"),
    "OD1 / OD2": (3, "two OD branches, each the valve's gain stage and cabinet at its own drive, level and pan; heard (Ben: \"They all sound great\")"),
    "OD / Rotary": (3, "an OD branch beside a Leslie branch (the voice's own valve in both); heard (Ben: \"They all sound great\")"),
    "OD / Phaser": (3, "an OD branch beside a phaser branch (efxfilter); heard (Ben: \"They all sound great\")"),
    "OD / AutoWah": (3, "an OD branch beside an auto wah branch, its Sens the part's notes; heard (Ben: \"They all sound great\")"),
    "PH / Rotary": (3, "a phaser branch beside a Leslie branch; heard (Ben: \"They all sound great\")"),
    "PH / AutoWah": (3, "a phaser branch beside an auto wah branch; heard (Ben: \"They all sound great\")"),
}


def effects_md():
    L = ["## Effects: the Sound Canvas's\n",
         "Rated on the voices' scale: 4 validated against a target (a recording of the device, or "
         "the hardware's output of a file judged against ours by ear), 3 validated semantically "
         "by ear, 2 from theory (Roland's tables, our models), 1 a stand-in, 0 not built (the "
         "sound passes dry). The reverb is the module's way of giving the music a space, and our "
         "physical rooms are how we do that job: it is rated on whether the space is the one the "
         "arranger asked for. The plan maps each insertion type onto the physical "
         "model we have where one exists (Rotary the Leslie, Overdrive/Distortion the valve "
         "amp and cabinet, the choruses chorus.py, the 3D types our room and head).\n",
         "| effect | | notes |", "|---|---|---|"]
    for nm, r, note in EFFECTS_RATED:
        L.append("| %s | **%d** | %s |" % (nm, r, note))
    L += ["", "### Insertion effects (EFX, the SC-88Pro's 64 types)\n",
          "Read per note at its onset (the files automate the level, the mix, the sends); "
          "a part assigned to a type not built plays dry.\n",
          "| type | | notes |", "|---|---|---|"]
    for n in EFX_TYPES:
        if n in EFX_RATED:
            L.append("| %s | **%d** | %s |" % (n, EFX_RATED[n][0], EFX_RATED[n][1]))
    L += ["", "Not built yet: %s." % ", ".join(n for n in EFX_TYPES if n not in EFX_RATED), ""]
    return "\n".join(L) + "\n"


# THE GS SYSEX MAP: Roland's addresses (VE-GS Pro MIDI Implementation; the
# SC-88Pro owner's manual for the insertion effects) against what the file
# renderer reads. Yes: read and applied; Partial: read, with the limit said;
# No: not read. Kept by hand from the map, as the ratings above are.
import gsefx as _GSX_C
_BUILT_EFX = _GSX_C.BUILT    # the insertion types built, counted where they are

SYSEX_ROWS = [
    ("System", [
        ("40 00 7F, 00 00 7F", "GS Reset, System Mode Set", "Yes",
         "back to power-on: banks, programs, controllers, tunings, effects, drum edits, the part settings below"),
        ("40 00 00-05", "Master tune, volume, key shift", "Yes", "the file's timeline; live too"),
        ("40 00 06", "Master pan", "No", ""),
    ]),
    ("Reverb, chorus, delay, EQ (40 01, 40 02)", [
        ("40 01 30", "Reverb macro", "Partial", "the arranger's space onto one of our rooms (Room 1 the studio, Hall 2 the church); read before the first note"),
        ("40 01 33-34", "Reverb level, time", "Partial", "onto the room's tail; before the first note"),
        ("40 01 31-32, 35, 37", "Reverb character, pre-LPF, feedback, pre-delay", "No", ""),
        ("40 01 38-3E", "Chorus macro and parameters", "Partial", "the GS chorus device; before the first note"),
        ("40 01 3F-40", "Chorus send to reverb, delay", "No", "parsed, not used"),
        ("40 01 50-59", "Delay macro and parameters", "Partial", "the GS delay; before the first note"),
        ("40 01 5A", "Delay send to reverb", "No", "parsed, not used"),
        ("40 02 00-03", "Master EQ, low and high", "Partial", "each partial at its frequency; before the first note"),
    ]),
    ("Insertion effect (40 03)", [
        ("40 03 00-01", "Type", "Yes" if len(_BUILT_EFX) >= 64 else "Partial", "%d of 64 built: the filters and EQs, the drives and guitar/bass/keyboard multis, the choruses and flangers, the delays, Rotary, Tremolo, Auto Pan, the 3D types, the pitch shifters, the moving filters (efxfilter), a part's own bus (Lo-Fi, the dynamics, Enhancer, the reverbs: efxbus), the series pairs and the parallel ones (branch B on a virtual channel); Thru plays dry" % len(_BUILT_EFX)),
        ("40 03 03-16", "Parameters 1-20", "Partial", "each type at Roland's own defaults (the data table) until the file sends one; drive and level follow the song, the EQ and chorus/flanger settings are the part's first note's; Amp Type not read"),
        ("40 03 17, 19", "Send to reverb, delay", "Yes", "per note"),
        ("40 03 18", "Send to chorus", "No", "parsed, not used"),
        ("40 03 1B-1E", "Control sources and depths", "Yes", "CC1-95, aftertouch or bend onto each type's + and # parameter, Roland's law (setting + controller x depth of the range); a file's at each note's onset, live's at once; the live panel learns the knob"),
        ("40 4x 22", "Part assign", "Yes", "ports A and B"),
    ]),
    ("Part (40 1x)", [
        ("40 1x 00", "Tone number", "Yes", "as CC0 and program change"),
        ("40 1x 02-12", "Rx channel and switches", "No", ""),
        ("40 1x 13", "Mono/poly", "Yes", "as CC126/127"),
        ("40 1x 14", "Assign mode", "No", ""),
        ("40 1x 15", "Use for rhythm part", "Yes", ""),
        ("40 1x 16", "Pitch key shift", "Partial", "as RPN 2: replaces the file's own rather than adding to it"),
        ("40 1x 17-18", "Pitch offset fine (Hz)", "No", ""),
        ("40 1x 19, 1C, 2C", "Part level, pan, delay send", "Yes", "as CC7, CC10 (random as centre), CC94"),
        ("40 1x 1A-1B", "Velocity sense depth, offset", "Yes", "at each note-on"),
        ("40 1x 1D-1E", "Keyboard range", "Yes", "notes outside it do not sound"),
        ("40 1x 1F-20", "CC1/CC2 controller numbers", "No", ""),
        ("40 1x 21-22", "Chorus, reverb send", "Yes", "as CC93, CC91 -- each note's onset finds its own (the sends follow the song)"),
        ("40 1x 23-24", "Rx bank select", "No", ""),
        ("40 1x 2A", "Pitch fine tune", "Yes", "as RPN 1"),
        ("40 1x 30-37", "Tone Modify 1-8", "Yes", "as the sound controllers CC71-78 (= the NRPNs)"),
        ("40 1x 40-4B", "Scale tuning", "Yes", "through the scale/octave tuning"),
        ("40 2x 04", "Mod LFO1 pitch depth", "Yes", "as RPN 5, the mod wheel's vibrato depth"),
        ("40 2x 10", "Bend pitch control", "Yes", "as RPN 0, the bend range"),
        ("40 2x (the rest)", "Mod, bend, aftertouch, CC1/CC2 onto TVF, TVA, LFOs", "No", "a Sound Canvas's own circuits, which our voices are not built from"),
        ("40 4x 00-01", "Tone map number", "No", "the map comes from CC32"),
        ("40 4x 20", "EQ switch", "Partial", "before the first note"),
    ]),
    ("Drum setup (41) and drum NRPNs", [
        ("41 m1 / NRPN 18", "Play note, pitch", "Yes", ""),
        ("41 m2 / NRPN 1A", "Level", "Yes", ""),
        ("41 m4 / NRPN 1C", "Pan", "Yes", "a seat inside the kit, turned by the part's pan"),
        ("41 m8", "Rx note on", "Yes", ""),
        ("41 m9 / NRPN 1F", "Delay send", "Yes", ""),
        ("41 m3", "Assign group", "No", "parsed, not used; the kits' own choke groups apply"),
        ("41 m5-m6 / NRPN 1D-1E", "Reverb, chorus send", "No", "parsed, not used"),
        ("41 m7", "Rx note off", "No", "parsed, not used"),
    ]),
    ("User sets, display, dumps", [
        ("21 d1, d2, d4, d8, dB, dC", "User drum set: note, level, pan, Rx note on, source set and note", "Yes", ""),
        ("21 (the rest)", "User drum set: group, sends, Rx note off, source map", "No", ""),
        ("20, 22-27", "User tones, user EFX, user patches", "No", ""),
        ("45 ...", "Display text and pages", "No", "not sound"),
        ("bulk dumps", "48, 49, ...", "No", ""),
    ]),
]


def sysex_md():
    n = {k: 0 for k in ("Yes", "Partial", "No")}
    L = ["## Roland GS SysEx: the address map\n",
         "What the file renderer reads of Roland's GS map (VE-GS Pro MIDI Implementation; "
         "the SC-88Pro manual for the insertion effects). **Yes** read and applied; "
         "**Partial** read, with its limit; **No** not read. Live reads the part parameters, "
         "the rhythm part, the master settings and the reset, on port A.\n"]
    for blk, rows in SYSEX_ROWS:
        L += ["### %s\n" % blk, "| address | parameter | | notes |", "|---|---|---|---|"]
        for a, p, st, note in rows:
            n[st] += 1
            L.append("| `%s` | %s | **%s** | %s |" % (a, p, st, note))
        L.append("")
    L.insert(2, "%d rows: %d read, %d partly, %d not.\n" % (sum(n.values()), n["Yes"], n["Partial"], n["No"]))
    return "\n".join(L) + "\n"


def stops_md():
    L = ["## Stops: the registers within a program\n",
         "A program's rating is its default registration's. Each stop of a",
         "registerable program is its own claim, rated on the same scale; the",
         "names are the code's (`stop_ranks`), and the bit is the stop word's.",
         "Controls are the rest of the console that are not stops.\n"]
    for progs, panel, rows, controls in stops():
        L.append("### %s -- %s\n" % (", ".join("%d %s" % (p, GM[p]) for p in progs), panel))
        L.append("| bit | stop | | notes |")
        L.append("|---|---|---|---|")
        for i, n, r, note in rows:
            L.append("| %d | %s | **%d** | %s |" % (i, n, r, note))
        for n, r, note in controls:
            L.append("| -- | %s | **%d** | %s |" % (n, r, note))
        L.append("")
    return "\n".join(L)


# THE CLASS TREE. Every class a program or a drum note is routed to, hung
# under its PHYSICAL base -- the first base that is itself a voice class
# (tonelib's convention: a class sits below what it physically is, struck or
# plucked or blown; mixins such as NoisyPercussionMixin add a behaviour and are
# listed beside the name, not as a branch). Asked of the router at every note,
# as _class_name is, so a split family shows each of its members.

def _primary_base(c):
    import tonelib
    for b in c.__bases__:
        if isinstance(b, type) and issubclass(b, tonelib.SynthProperties):
            return b
    return None


def _mixins(c):
    import tonelib
    return [b.__name__ for b in c.__bases__
            if isinstance(b, type) and not issubclass(b, tonelib.SynthProperties) and b is not object]


def class_users():
    """{class: [(kind, number, name, rating)]}, kind 'gm', 'perc' or 'kit<k>'."""
    import percussion_map as PM
    users = {}
    for p in range(128):
        seen = []
        for n in range(128):
            c = patch_map.property_class_for_note(p, n)
            if c not in seen:
                seen.append(c)
        for c in seen:
            users.setdefault(c, []).append(("gm", p, GM[p], RATED[p][0]))
    for n in sorted(PERC_RATED):
        users.setdefault(PM.PERCUSSION[n][1], []).append(("perc", n, PM.PERCUSSION[n][0], PERC_RATED[n][0]))
    for k in sorted(KIT_RATED):
        for n in sorted(KIT_RATED[k]):
            users.setdefault(PM.KITS[k][n][1], []).append(("kit%d" % k, n, PM.KITS[k][n][0], KIT_RATED[k][n][0]))
    return users


def class_tree():
    """[(class, users, children)] from the roots down, children by name."""
    users = class_users()
    kids = {}
    nodes = set()
    for c in users:
        while c is not None and c not in nodes:
            nodes.add(c)
            b = _primary_base(c)
            kids.setdefault(b, []).append(c)
            c = b

    def grow(c):
        return (c, users.get(c, []), [grow(k) for k in sorted(kids.get(c, []), key=lambda k: k.__name__)])
    return [grow(r) for r in sorted(kids.get(None, []), key=lambda k: k.__name__)]


def short(c):
    return c.__name__.replace("Properties", "") or c.__name__


def class_tree_md():
    tree = class_tree()
    n = [0]
    L = ["## The class tree\n",
         "Every voice class a program or a drum note is routed to, under its physical",
         "base (the first base that is itself a voice class; mixins in brackets). After",
         "each: the GM programs (`GM n`), percussion notes (`n`) and drum-set notes",
         "(`set k n`) that use it, with their ratings.\n"]

    def walk(node, depth):
        c, us, ch = node
        n[0] += 1
        mx = _mixins(c)
        tags = ", ".join(("GM %d %s" % (num, name) if kind == "gm" else
                          "%d %s" % (num, name) if kind == "perc" else
                          "set %s %d %s" % (kind[3:], num, name)) + " (%d)" % r
                         for kind, num, name, r in us)
        L.append("%s- `%s`%s%s" % ("  " * depth, short(c), " [%s]" % ", ".join(mx) if mx else "",
                                  " -- " + tags if tags else ""))
        for k in ch:
            walk(k, depth + 1)
    for r in tree:
        walk(r, 0)
    L.insert(1, "%d classes.\n" % n[0])
    L.append("")
    return "\n".join(L)


def main(argv):
    _gs_sets_rated()            # after VAR_RATED, whose classes it rates by
    _sc88pro_extra_rated()      # ...and Standard's keys that borrow from those sets
    _sc88pro_extra_rated()      # ...and the Standard keys that borrow from those sets
    out = argv[1] if len(argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'coverage.md')
    fams = dict(FAMILY)
    L = []
    L.append("# GM coverage\n")
    L.append("How complete each of the 128 GM patches is. Generated by")
    L.append("`examples/gm_coverage.py`, which reads the class column out of `patch_map`")
    L.append("so it cannot drift; the ratings live in that script and can be argued with.\n")
    L.append("| | meaning |")
    L.append("|---|---|")
    for k in range(5):
        L.append("| **%d** | %s |" % (k, LEVEL[k]))
    L.append("")
    L.append("__SUMMARY__")
    L.append("3 means validated SEMANTICALLY BY EAR: it does what the instrument does, judged")
    L.append("by listening, whether or not by the same mechanism. 4 means validated against a")
    L.append("TARGET -- a recording of the instrument is one (fitted against it, or against a")
    L.append("family law measured on its close relatives); the hardware's own output of a")
    L.append("file is another (a Sound Canvas playing it, judged against ours by ear). Published measurements")
    L.append("that are not audio -- the Rhodes' high-speed-camera papers -- are better than")
    L.append("theory but cannot contradict the model the way a recording can, so those")
    L.append("voices sit at 2 and say so.\n")
    L.append("FOR A SYNTH PROGRAM THE INSTRUMENT IS A SYNTHESIZER. The 32 synth programs --")
    L.append("basses, strings, brass, leads, pads, effects and the synth drum -- are")
    L.append("patches on a Moog Messenger, and the Messenger")
    L.append("engine in `moog.py` is fitted against Ben's own Messenger, recorded through a")
    L.append("mixer and back (`examples/messenger_fit.py`): every knob law -- cutoff,")
    L.append("resonance, the contours and sustain, waveshape and sub wave, FM index, LFO 1")
    L.append("and MOD depths, the filter modes, the mixer, the noise and the output stage.")
    L.append("Whole notes, attack to release, agree within 0.6-2 dB rms on 28 of 32")
    L.append("programs. That is a recording of the instrument, so a pure Messenger patch")
    L.append("is a 4; one with a part no Messenger has (the vocal formants after it, the")
    L.append("guitars' valve, the MF-104M pedal, which is modelled and not recorded) is a 3.")
    L.append("And the reference runs the other way too: a patch's knobs are the hardware's,")
    L.append("so it plays on the Messenger itself.\n")
    hist = {k: 0 for k in range(5)}
    for p in range(128):
        hist[RATED[p][0]] += 1
    cat = [p for p in range(128) if "CATEGORY ERROR" in RATED[p][1]]
    if cat:
        wrong = ("**%d patches are played by a voice of the wrong physical kind** "
                 "(marked CATEGORY ERROR below): %s." % (len(cat), ", ".join("%d %s" % (p, GM[p]) for p in cat)))
    else:
        # It read "0 patches ... : ." once the list emptied, which is the kind of
        # sentence that only ever gets written when the count cannot reach zero.
        wrong = ("**No patch is played by a voice of the wrong physical kind.** "
                 "The last three to be were 123 Bird Tweet, 124 Telephone Ring "
                 "and 125 Helicopter, which are not recordings of the world but "
                 "a chirp, a struck bell and a blade passing frequency.")
    L[L.index("__SUMMARY__")] = summary_md(hist, wrong)
    L.append(percussion_table())
    L.append(drum_set_table())
    for start, name in FAMILY:
        L.append("## %d-%d %s\n" % (start, start + 7, name))
        L.append("| # | patch | class | | notes |")
        L.append("|---|---|---|---|---|")
        for p in range(start, start + 8):
            cls = _class_name(p)
            r, note = RATED[p]
            L.append("| %d | %s | `%s` | **%d** | %s |"
                     % (p, GM[p], cls.replace("Properties", ""), r, note))
        L.append("")
    L.append(stops_md())
    L.append(variations_md())
    L.append(mt32_md())
    L.append(gm2_md())
    L.append(sound_canvas_md())
    L.append(effects_md())
    L.append(sysex_md())
    L.append(class_tree_md())
    open(out, 'w').write("\n".join(L) + "\n")
    print("  wrote %s" % out)
    print("  %s" % "  ".join("%d:%d" % (k, hist[k]) for k in range(5)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
