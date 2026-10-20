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
 42:(4,"Iowa hi-hat, five takes"),
 43:(4,"as 41, higher"),
 44:(4,"Iowa hi-hat, foot-close take"),
 45:(4,"DRSKit's rack tom, 27 strokes on its close mic: modes 1 : 1.477 : 1.755 : 2.259, the stick's click 30-60 dB under the fundamental to 6 kHz, a glide that grows with the stroke. Ben, by ear"),
 46:(4,"Iowa hi-hat, open"),
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
 58:(4,"VSCO-2 CE (CC0) vibraslap: the beads in the box a periodic train at 55 Hz falling over 2.6 s, each impact soft-onset, the colour matched in third octaves. Ben: a lot better than expected"),
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
 73:(4,"Iowa guiro, both directions -- four rounds of measuring the right thing in the wrong window"),
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
         3:"specific, theory + ear", 4:"specific, reference audio"}


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
    L.append("%d notes, 35 to 87. Iowa's percussion pages carry cymbals, crotales and"
             % tot)
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

def drum_set_table():
    """The drum sets, by the program that selects them."""
    import percussion_map as PM
    L = ["## Drum sets: the program on a drum channel\n"]
    L.append("The program on a drum channel is the drum SET (SC-55 owner's manual")
    L.append("p.21), and a set changes only some notes -- every blank in the manual's")
    L.append("table is \"same as Standard\". The SC-55 has ten; a set not built here")
    L.append("plays Standard, as does any program that is not a set.\n")
    L.append("| program | set | built |")
    L.append("|---|---|---|")
    for k in sorted(PM.DRUM_SETS):
        built = ("the note map above" if k == 0 else "yes" if k in PM.KITS else
                 "= Standard on the SC-55" if PM.DRUM_SETS[k] in ("Standard", "Jazz")
                 else "no -- plays Standard")
        L.append("| %d | %s | %s |" % (k, PM.DRUM_SETS[k], built))
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
    (25, 8): (3, "the steel-string with its courses DOUBLED, read off John Magner's Fender 12-string (Pianobook), its harmonics resolved into doublets: below B3 an octave string on the even harmonics, as loud as the main at its own pitch (the open low strings' 2nd ~10 dB over a single string's), 8 cents off (6-14 measured); B3 up a unison partner at 0.9, 5.5 cents off (2.6-9). Levels the robust numbers only: the Fender is a different guitar from the steel-string's fit. STRUCK BY A PICK (tonelib.Plectrum; examples/plectrum_fit.py): the scrape as noise of its own -- the take's attack as bright on E2 as on A4, which brighter partials cannot be -- at the note's level to 7 kHz, gone at 400 dB/s (fitted on the 4-16 kHz envelope over 70 ms, after a fit on 15 ms shares took a long quiet scrape Ben heard as harsh), the course crossed 28 ms apart. Ben: 'Sounds good'"),
    (25, 16): (3, "unison COURSES of steel strings (0.9, 5.5 cents off, as the 12-string's top), its decay fitted to the Eclectic Mandolin's takes (examples/pluck_fit.py --voice=mandolin: 14.35 dB/s, steeply by register), and PICKED (tonelib.Plectrum): the scrape at the note's level to 5.5 kHz gone at 700 dB/s, the top partials struck 12 dB an octave over 1.5 kHz and gone at 400 dB/s (the take's top falls 24-42 dB by 0.1 s), the course crossed 14 ms apart. The take is re-amped dark, so its colour is not a target: fitted on flatness and how fast the top falls. Ben: 'Sounds good'"),
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


def _sc88_var_rated():
    """THE SC-88 MAP'S CHEAP TONES (patch_map.SC88_CHEAP): each its source
    voice's rating -- the program it aliases or sets, its layers' lowest, the
    kit key it plays -- and what was done to it."""
    names = GM
    for (p, b), (nm, how) in patch_map.SC88_CHEAP.items():
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
            r = min(RATED[l[0]][0] for l in how[1])
            note = "layered: " + " + ".join("GM %d%s%s%s" % (l[0], (" %+d st" % l[1]) if l[1] else "",
                                                          (" %+.0f dB" % l[2]) if l[2] else "",
                                                          (" vel %d-%d" % (l[3], l[4])) if len(l) > 3 else "")
                                            for l in how[1])
        VAR_RATED[(p, b)] = (r, "SC-88 map: " + note)
    # ...AND ITS SYNTH TONES (sc88_synth.SC88_SYNTH): Moog panels, a 3 as the
    # bank-8 synths are -- the engine is fitted to Ben's Messenger, the panel
    # is voiced from what the tone is, not fitted to a recording of it
    try:
        from sc88_synth import SC88_SYNTH
    except ImportError:
        SC88_SYNTH = {}
    for (p, b), (nm, base, pan) in SC88_SYNTH.items():
        if (p, b) in patch_map.VARIATIONS:
            VAR_RATED[(p, b)] = (3, "SC-88 map: a Moog panel, %s's with %s changed (sc88_synth.py); "
                                    "voiced from what the tone is, the engine fitted to Ben's Messenger"
                                 % (base.replace("Moog", "the "), ", ".join(sorted(pan))))


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
        if v == 127:
            continue                       # the MT-32 set: its own table (mt32_md)
        if (p, v) in built:
            cls = patch_map.property_class_for_program(patch_map.VariationProgram(p, v))
            r, note = VAR_RATED[(p, v)]
            out.append((p, v, name, cls.__name__, r, note))
        else:
            out.append((p, v, name, None, None, "not built: plays %d %s" % (p, GM[p])))
    return out


def variations_md():
    rows = variations()
    sc88 = set(getattr(patch_map, "SC88_CHEAP", {}))
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
SC_OTHER = {
    "sc55": {(3, 8), (4, 16), (5, 16), (62, 16), (63, 16)},
    "sc88": {(4, 8), (39, 8)},
    "native": {(0, 16), (3, 8), (4, 8), (39, 8), (16, 8), (16, 9), (16, 32), (17, 1), (17, 32),
               (60, 16), (62, 8), (63, 8), (63, 17)},
}
SC_MAPS = (("sc55o", "SC-55"), ("sc55", "SC-55mkII"), ("sc88", "SC-88"), ("native", "SC-88Pro"))


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
    later = set(getattr(patch_map, "SC88_CHEAP", {}))
    try:
        from sc88_synth import SC88_SYNTH
        later |= set(SC88_SYNTH)
    except ImportError:
        pass
    tones = {"sc55o": [(p, 0) for p in range(128)] +
             [k for k in patch_map.VARIATION_NAMES if k[1] != 127 and k not in later]}
    for col in ("sc55", "sc88", "native"):
        tones[col] = [(r["program"], r["bank"]) for r in R
                      if r[col] not in ("-----", "", "+ -----")]

    def rating(col, k):
        if k[1] == 0:
            return RATED[k[0]][0]
        if k in SC_OTHER.get(col, ()) or k not in patch_map.VARIATIONS or k not in VAR_RATED:
            return None
        return VAR_RATED[k][0]
    maps, fams = [], []
    for col, name in SC_MAPS:
        rs = [rating(col, k) for k in tones[col]]
        hist = {r: rs.count(r) for r in range(5)}
        other = sum(1 for k in tones[col] if k in SC_OTHER.get(col, ()))
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


def sound_canvas_md():
    sc = sound_canvas()
    if sc is None:
        return ""
    maps, fams, miss = sc
    L = ["## Sound Canvas: the GS maps\n",
         "Each Sound Canvas's map of tones (the SC-55's own owner's manual p.68; the SC-55mkII,",
         "SC-88 and SC-88Pro maps from the SC-88Pro manual's list), against ours. A tone is built",
         "when we play it, as a program or a variation, and rated as the tables above rate it.",
         "A later map can put another tone under a number we built; that one is not counted.\n",
         "| map | tones | built | | 4 | 3 | 2 | 1 | 0 | to do |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, n, nb, other, h in maps:
        L.append("| %s | %d | %d | %d%% | %s | %d%s |"
                 % (name, n, nb, round(100 * nb / n), " | ".join(str(h[r]) for r in (4, 3, 2, 1, 0)),
                    n - nb, (" (%d another tone)" % other) if other else ""))
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
    L.append("4 means the voice was fitted against a RECORDING of the instrument, or")
    L.append("against a family law measured on its close relatives. Published measurements")
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
    L.append("## Where it stands\n")
    L.append("| rating | patches | share |")
    L.append("|---|---|---|")
    for k in range(5):
        L.append("| %d %s | %d | %d%% |" % (k, LEVEL[k], hist[k], round(100 * hist[k] / 128)))
    L.append("")
    cat = [p for p in range(128) if "CATEGORY ERROR" in RATED[p][1]]
    if cat:
        L.append("**%d patches are played by a voice of the wrong physical kind** "
                 "(marked CATEGORY ERROR below): %s.\n"
                 % (len(cat), ", ".join("%d %s" % (p, GM[p]) for p in cat)))
    else:
        # It read "0 patches ... : ." once the list emptied, which is the kind of
        # sentence that only ever gets written when the count cannot reach zero.
        L.append("**No patch is played by a voice of the wrong physical kind.** "
                 "The last three to be were 123 Bird Tweet, 124 Telephone Ring "
                 "and 125 Helicopter, which are not recordings of the world but "
                 "a chirp, a struck bell and a blade passing frequency.\n")
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
    L.append(sound_canvas_md())
    L.append(class_tree_md())
    open(out, 'w').write("\n".join(L) + "\n")
    print("  wrote %s" % out)
    print("  %s" % "  ".join("%d:%d" % (k, hist[k]) for k in range(5)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
