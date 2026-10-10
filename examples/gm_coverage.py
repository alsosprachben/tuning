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
 2:(2,"a CP-70: short strings so 12x the bass stretch, no soundboard, a piezo on the bridge. Derived, no reference"),
 3:(3,"the measured upright (GM 1) with the tuner's hand off: unisons 8-20 cents, CC1 the wheel. The upright is fitted; the detune is judged from beat rates, not measured"),
 4:(2,"Rhodes. Built on two papers' high-speed-camera measurements, but NO audio fitted"),
 5:(2,"Wurlitzer. Same machinery, 1/d pickup; no audio fitted"),
 6:(4,"VCSL recordings"),
 7:(2,"its own voice: struck at the anvil, magnetic pickups whose fraction climbs with pitch. No reference"),
 8:(2,"struck steel plate, felt hammer"),
 9:(4,"Iowa orchestra bells"),
 10:(2,"plucked steel comb tooth. Its docstring claims a cantilever; its numbers are a free-free bar"),
 11:(4,"Iowa vibraphone. The motor tremolo that gives it its name is NOT modelled"),
 12:(4,"Iowa marimba"),
 13:(4,"Iowa xylophone"),
 14:(4,"VSCO 2 CE's chimes (CC0), C4 G4 C5 F5: a free-free tube's modes, the note an octave under the fourth -- plus the hum a third above it and a mode a sixth below, rising with pitch; the upper modes compressing as the tube shortens; each mode's own ring, the hum outlasting the rest. Renders read back on the fitted lines. Ben, by ear: sounds great"),
 15:(2,"struck steel courses; the stiffness is estimated"),
 16:(3,"tonewheel + Leslie, worked over extensively by ear"),
 17:(3,"tonewheel, percussive tap"),
 18:(3,"tonewheel, overdriven"),
 19:(3,"flue pipes; registration built on Geer and judged by ear. The wind is fitted to Pitea's recorded pipes -- the jet's turbulence as noise skirts, the reeds' attack rush -- but the pipes' tone is not, so it stays a 3. A shared wind per division (sag under a chord) and a Tremulant stop, off by default until judged by ear"),
 20:(2,"a French harmonium: free reeds, four registers split bass/treble, celeste, Expression/Percussion/Tremolo on CC43/44"),
 21:(2,"AccordionProperties: musette, the reed banks deliberately offset ~16 cents"),
 22:(2,"HarmonicaProperties: one free reed inside a cupped-hand formant pair"),
 23:(2,"TangoAccordionProperties: the same box tuned DRY (~3 cents), which is what a bandoneon is"),
 24:(4,"Iowa classical guitar, six strings measured sul A/B/D/E/G"),
 25:(2,"the measured classical's body with a steel string on it: less damping, a pick, 35% more stretch"),
 26:(3,"electric family: pluck comb x pickup comb, amp and cabinet; judged by ear"),
 27:(3,"as 26 -- the reference voice of the family"),
 28:(3,"as 26, palm mute"),
 29:(3,"as 26, driven harder"),
 30:(3,"as 26, driven hardest"),
 31:(3,"as 26, touched harmonics"),
 32:(4,"Iowa double bass pizzicato, 83 notes: the decay rising with the note, the stretch, the pluck's colour, and a pluck point that rises up each string as the finger shortens it (0.23 of the open string, measured), moved by CC74 from the bridge to the middle. Ben, by ear: so much better"),
 33:(3,"electric bass family, cabinet and amp; judged by ear"),
 34:(3,"as 33, pick"),
 35:(3,"as 33, fretless -- loses its top rather than starting without it"),
 36:(3,"as 33, slap"),
 37:(3,"as 33, pop"),
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
 52:(3,"vocal tract and formants; Ben's ear on the consonant balance"),
 53:(3,"as 52"),
 54:(3,"two saws on the Messenger, then the class's own sung tract after it. The Messenger is measured; the formant body is theory"),
 55:(2,"its own class, theory"),
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
 75:(2,"a CLOSED tube (odd harmonics, already right) that had no breath at all -- StoppedPipe ships sustain_jitter 0, so it rendered as an organ's Gedackt"),
 76:(2,"its own class, theory"),
 77:(2,"a knife-edge notch and the breathiest voice in the family; meri/kari belong on a controller and are not modelled"),
 78:(2,"CATEGORY CORRECTION: a human whistle is a Helmholtz resonator, not a pipe -- one resonance tuned by the tongue, and nearly a sine (h2 -33 dB)"),
 79:(4,"VCSL typical and small ocarinas (CC0), 21 sustains (examples/wind_fit.py): near-pure (h2 -44), its breath, flutter, shared wobble (2.4 dB) and pitch wander (5.6 cents) fitted, a soft chiff. Ben: sounds great"),
 80:(4,"a Messenger patch: a square with the SUB's square an octave under -- the weight a square lead has on a Moog and not on a chip"),
 81:(4,"a Messenger patch: the sawtooth lead as a Moog player sets it"),
 82:(4,"a Messenger patch: the calliope, a steam whistle -- two triangles an octave apart, the ladder wide open. The GM name misleads; the patch does not"),
 83:(4,"a Messenger patch: the NOISE oscillator through the same ladder as the saw, so the breath chuffs as the contour snaps open"),
 84:(3,"two saws on the Messenger and THEN the valve the electric guitars use -- the hardware's order. The Messenger is measured; the amp is the guitars' own model"),
 85:(3,"two saws and a slow breath on the Messenger, sung through the class's open /a/ after it. The Messenger is measured; the formants are theory"),
 86:(4,"a Messenger patch: OSC 2 FREQ fully up, a tempered fifth -- where the knob's travel ends"),
 87:(4,"a Messenger patch: OSC 2 on 16', the bass and the lead from one key, more resonance and a shorter contour for the punch"),
 104:(2,"its own class; sympathetic strings and jawari, but the responder set is ASSERTED -- no recording"),
 105:(2,"steel over a DRUMHEAD: a membrane is light and damped, so it cannot radiate below 380 Hz and it empties the string fast. Thin, quick and bright are one fact"),
 106:(2,"the same head, plus a SAWARI buzz modelled as the sitar models its jawari, and a wide bachi that fills its own comb notch"),
 107:(2,"long slack silk over a light WOODEN box: the banjo's opposite in every way. Movable bridges mean uniform, very low inharmonicity across the compass"),
 108:(2,"a plucked CANTILEVER, 1 : 6.267 : 17.55 -- not the mallet base's struck bar. The Rhodes tine's ratios, undamped, so the overtones ping above the note"),
 109:(3,"the DRONES: two tenors and a bass at a FIXED 220/220.4/110 Hz whatever the melody does, which no other voice here can do. They belong to the PART -- sounding once across a played phrase, not restarting per note -- and CC1 corks them one at a time, 0 to 3, because a piper corks rather than turns down. Not touch sensitive: a bag holds one pressure, so CC7/CC11 are the whole dynamic"),
 110:(4,"the measured violin, given solo treatment"),
 111:(2,"a CONE, so the even harmonics the chanter's class suppressed come back -- a shawm is an oboe's geometry, not a bagpipe's"),
 112:(4,"Iowa crotales, 25 pitches"),
 113:(4,"VSCO-2 CE (CC0) agogo bells 2 and 3, played as a melodic instrument: the high bell above note 82, the low below, each fitted stroke carrying its band colour with the note. Ben: sounds good"),
 114:(4,"built from the instrument's design, then corrected against Freesound 742254"),
 115:(4,"Iowa woodblocks"),
 116:(4,"VSCO-2 CE (CC0) giant drum struck with sticks, as a taiko with bachi: 28 measured modes as ratios to the played note, its colour moving with it (PlayedAtPitchMixin). Fitted on the first 250 ms with the strike dying as a stick's does -- the takes' late energy is their room. Ben: sounds great"),
 117:(4,"DRSKit's two toms, measured, by register: the floor tom under G2, the rack tom from G2 up. A melodic tom part is a set of drums, not one drum retuned"),
 118:(4,"a Messenger patch: the drum machine's tom as an analog synth makes it -- the MOD section's F ENV on OSC 2's pitch (measured: linear, +-5 octaves)"),
 119:(4,"the fitted crash (Iowa's modes, refitted to DRSKit) PLAYED BACKWARDS, literally: every partial emitted time-reversed -- each decay a growth at its own rate, each phase mirrored so the modes arrive together as they set out, the strike's wash a swell before the arrival. Against the forward crash flipped, 0.4 dB rms in every band (examples/reverse_check.py). It was one shared swell over the modes; Ben: sounds great"),
 120:(3,"its own class -- slide, squeak and position shift; reworked against Ben's ear"),
 121:(2,"its own class, theory"),
 122:(2,"its own class, theory"),
 123:(2,"a CHIRP: a nearly pure tone whose pitch RISES (tension_bend negative, where the synth drum's is positive), repeated four times -- 999 Hz climbing to a written 1047"),
 124:(2,"a BELL struck 21 times a second by a clapper alternating between two gongs. The thing in the room, not the 440+480 Hz ringback the exchange sends the caller"),
 125:(2,"the BLADE PASSING FREQUENCY: a sawtooth at 16.3 Hz with partials every 16.3 up to 1 kHz. The only voice whose fundamental is below hearing -- the series above it IS the sound"),
 126:(2,"its own class, theory"),
 127:(2,"an N-wave whose length the key sets (its spectrum peaks on the key), the tail the room, standing back at 127's distance. Published measurements, no recording"),
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
 91:(3,"two saws and a swell on the Messenger, then the class's three vocal formants (its /O/). The Messenger is measured; the formants are theory"),
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
 35:(4,"DRSKit's kick (DrumGizmo, CC-BY 4.0), 29 strokes on its two close mics: eleven measured modes, damped like a pillowed kick (head modes 40-130 dB/s, fitted by BAND so two modes 7% apart are not each read twice), a stroke-scaled glide of 150-350 cents, the beater's click. Two semitones under 36, at 39.4 Hz. Ben, by ear: sounds deeper"),
 36:(4,"as 35, at the recorded kick's own 44.4 Hz"),
 37:(4,"DRSKit's cross-stick, fitted as the measured snare struck on the rim: its head under the stick, the rim's click at 1.05 and 1.93 kHz, wires that die faster. Level by ear, 3 dB under the snare (the recorded 20.6 left it buried under the kick)"),
 38:(4,"DRSKit's snare (29 strokes, top and bottom mics): the head at 196 Hz with a tom's modes, choked in 50 ms; the wires a buzz of jittered noise in third-octave bands, fitted on band, onset balance and flatness (a chord of sines at the right band levels was not a snare; neither was a comb in phase -- \"pew pew\"). Needed the renderer's onsets to start on their own sample. Ben, by ear: sounds so much better"),
 39:(2,"its own class, theory"),
 40:(2,"a DRUM MACHINE's snare, not the acoustic one retuned: a short noise burst over a body that DROPS (tension_bend), and no wires at all"),
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
 65:(2,"a TIMBALE: a METAL shell with no bottom head, ringing to 3900 Hz where the head reaches 1116 and holding it three times longer than wood. Sticks"), 66:(2,"as 65, lower"),
 67:(4,"VSCO-2 CE (CC0) agogo bell 2 (1228 Hz), fitted: measured modes, per-stroke scatter from the takes"),
 68:(4,"VSCO-2 CE (CC0) agogo bell 3 (696 Hz), as 67"),
 69:(4,"VSCO-2 CE (CC0) cabasa as SHAPED NOISE: measured, a twist is noise (its grain is its own spectrum with random phases), so the recording's third-octave spectrum as noise rows under the fitted swell, shake and 0.33 s settle -- colour within 0.3 dB, envelope 3.0. The impact burst before it clicked where the takes do not. Ben: sounds great"),
 70:(4,"VSCO-2 CE (CC0) maracas as SHAPED NOISE, fitted to the SINGLE strokes (two of the five files are two strokes, one three): the recording's spectrum as noise rows, a swell, the shake, a 0.29 s settle falling 40 dB -- colour within 0.8 dB but for the gourd's 2.3 kHz cliff, envelope 3.2. A little seed-click grain above 4 kHz is the recording's and not ours. Ben: sounds great"),
 71:(3,"NO REFERENCE, and it says so. Ben on the first version: the whistles were noise driven"),
 72:(3,"as 71, longer"),
 73:(4,"Iowa guiro, both directions -- four rounds of measuring the right thing in the wrong window"),
 74:(4,"as 73, the long scrape"),
 75:(4,"Iowa claves, three pairs"),
 76:(4,"Iowa woodblocks, four sizes"),
 77:(4,"as 76, the low block"),
 78:(2,"its own FRICTION voice: sawtooth drive, axisymmetric modes only, mode-locked, glides up into pitch"),
 79:(2,"as 78, lower and gliding the other way. No reference -- Iowa has no friction drum"),
 80:(4,"Iowa triangles, 6\" and 8\""),
 81:(4,"as 80, undamped"),
 84:(4,"the measured crotales, cascaded -- 22 of them over 30 units"),
 85:(4,"Iowa castanets"),
 86:(2,"a SURDO: two feet across, its shell resonating at 52 Hz under a 66 Hz head. Muted -- a hand laid flat straight after the beater"),
 87:(2,"as 86, open, and it rings nearly four times as long"),
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
    L.append("the crashes hit hard.\n")
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
# replaces (examples/drumset_check.py). No reference audio exists for any of
# them. Ben's ear has had its turn on what he heard -- all of Brush, and the
# one Electronic note thememat plays -- which is 3; the rest stay at 2.
KIT_RATED = {
    24: {
        36: (2, "a synth tom tuned down to a kick: the same downward sweep, narrower and faster"),
        38: (2, "the Simmons snare: the drum machine's snare with its body let loose -- it sweeps as the toms do"),
        40: (2, "an acoustic snare behind a GATE: the room tail holds, then stops dead at 0.30 s"),
        41: (2, "GM 118's synth tom at the Standard tom's pitch, given a drum's ring (0.85-0.95 s to silence) in place of its melodic one"),
        43: (2, "as 41"), 45: (2, "as 41"), 47: (2, "as 41"), 48: (2, "as 41"), 50: (2, "as 41"),
        52: (4, "GM 119's reverse cymbal: the fitted crash played backwards, arriving on the written note-off"),
    },
    40: {
        38: (3, "a brush TAPPED: the wires land over 5-18 ms, and an area contact darkens the head's high modes. Ben's ear, brush_demo (2026-09-23): good"),
        39: (3, "a brush slapped FLAT: louder, and it lies on the head and chokes it. As 38"),
        40: (3, "a brush SWEPT: no strike -- friction drives the head's modes as noise bands, swelling in over 120 ms. As 38"),
    },
}


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
    L.append(class_tree_md())
    open(out, 'w').write("\n".join(L) + "\n")
    print("  wrote %s" % out)
    print("  %s" % "  ".join("%d:%d" % (k, hist[k]) for k in range(5)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
