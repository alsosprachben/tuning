#!/usr/bin/env python3
"""The native port's task list: what of each standard the C engine plays.

    python3 examples/native_coverage.py [OUT.md]      (default: native.md)

Written from the engine itself (native.note_class over patch_map's and
percussion_map's classes), so it cannot drift: a tone is NATIVE when every
key of it, A0 to C8 (a drum set: every key it defines), is a class the
engine plays in a file render. The order is Ben's (2026-11-04): General
MIDI 1, then GM 2, then the Sound Canvas maps -- SC-55, SC-88, SC-88 Pro,
SC-8850 -- each stage only what the one before it did not already bring.
The infrastructure a stage needs, and the live side, are kept by hand in
TASKS below.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

# THE WORK THAT IS NOT A TONE: what a stage needs before its tones can be
# reached, and live's side. (stage, done, text); kept by hand.
TASKS = [
    ("GM1", True, "Program changes in nvlive: a builder thread, MIDI program change, the panel's picker"),
    ("GM1", False, "nvlive's panel at livetui's (a switch is not a control: each a panel control and a library "
                   "call) -- done: the patch picker and its variations, globals, routes, stops, the insertion "
                   "effect (x), parts (layers, splits, channel, range, transpose, level, mute, fixed touch), the "
                   "tuner, the synth (Moog, Messenger) pane and M, scenes, presets and the shared session, mod "
                   "rate, the metronome, the standard, the devices (--port), mouse and touch, the Eastern tuning "
                   "(E: system, raga and Sa, the Indian voices' parts built again in it, in presets and the "
                   "session; native vs live identical switched mid-phrase); open: threads"),
    ("GM2", True, "Restore c2111e6's six tones, lost when be5a996 was committed from an older tree: 12.16 "
                  "Barafon, 12.17 Barafon 2, 12.24 Log drum, 66.8 BreathyTnr., 28.1 MutedDis.Gt, 125.10 Calculating "
                  "-- and with them sympathy per mode (26.8 Pedal Steel, 107.8 Taisho Koto whole). Replayed onto "
                  "today's tree: every stage whole again, each tone Python vs native in files and live, the corpus "
                  "167/167"),
    ("GM1", True, "Live: the synth variations nvlive greyed as not native -- a Moog's SYNC (13: Sync Bass, P5 "
                  "Sync Lead, Wire Lead...) and unison (16: JP SuperSaw, Super Poly, the JP-8000 stacks...): "
                  "moog.weights' synced spectrum the kernel's C, the shape rows' sweep, the lock under a held "
                  "note; each unison voice a stamp of its own. Native vs live identical on P5 Sync Lead, a lead's "
                  "SYNC turned live, Sync Bass and JP SuperSaw on the GPU path, Super Poly, JP8000 Clav., "
                  "DualSyncLead. The page's tone counts are the files'; a live count beside them is to come"),
    ("SC-88", True, "Live: what c2111e6's tones played in files only -- 28.1 MutedDis.Gt's open strings ringing "
                    "on (held past the key until the string sounds again or its cap: live._open_ring_*, both "
                    "engines) and 125.10 Calculating's Morse strokes (a melodic note's borrowed strokes: the "
                    "sets' tables and the class table, nv_song_strokes_k, as nvrender's) -- native vs live "
                    "identical, 125.10 no longer refused"),
    ("GM1", True, "Live: the Messenger's performance controls, measured on Ben's unit (messenger_perf.py) -- GLIDE "
                  "(a lag in cents, detached notes too), HOLD, A and F ENV VEL, LFO 2 (rate, pitch, cutoff, amp, "
                  "the wheel its depth), F and A ENV LOOP, MULTI-TRIG (carry on, or recharge from where it was); "
                  "the loops, F ENV VEL and the contours' age and start level in a kernel entry of their own "
                  "(synth_voice_moogx), Python and native alike"),
    ("GM1", True, "Live: the room switched while playing (live.set_room): every room in the export (LROOMS), "
                  "its tail drawn natively at the stage's directivity (native/roomtail.cpp, bit for bit "
                  "roomtail.py's), the templates built again in it, the tail crossfaded"),
    ("GM1", True, "nvlive's host as a library (nv_host_*: the export, the builder, parts, programs, the room, "
                   "rebuilding, tuning, the devices) beside nv_part_*, for a GUI; nvlive its terminal client "
                   "-- 2a-2f done (host_check: the library against live.py); 2g, the picker, the globals and "
                   "panic, in its checks -- all of it: host_api_check 0 failed, 2g's picker, globals and panic among them"),
    ("GM1", True, "Live: the Moog (knob-neutral templates and the slab's moog.weights; CC71-75 its knobs; "
                  "a layered voice; the MF-104M) -- not yet a unison or SYNC live"),
    ("GM1", True, "Live: the Moog Messenger both ways (live._messenger_cc, messenger_sync/_pitch): its chart "
                  "turns a part's knobs (the panel rebuilt in C from the export's MTAB, the knob's glide; both "
                  "firmwares), the panel and each note's bend sent back (--messenger-out: the panel heard on the "
                  "Messenger itself; its notes' bends not yet tried there) -- not SYNC's knob"),
    ("GM1", True, "Live: check the fiddle, tinkle bell, melodic tom, reverse cymbal and breath noise against live.Live"),
    ("GM1", True, "Live: a drum set identical to live.Live beyond the kick and toms (the Standard set's every key, "
                  "nvlive end to end)"),
    ("GM1", False, "Files: GS's controller-matrix cutoff on a Moog (_CMXEV) -- nvrender's reader refuses it"),
    ("GM1", True, "Files: an organ after another tone on its channel (its tremolo keyed by its mix channel)"),
    ("GM1", True, "Moog: an MF-104M on a note whose pitch or shapes move -- each repeat its own filter row, its "
                  "pitch and shape rows its delay later (_prep_delays' _mf_dup; nv_song_moog_dup); nvrender vs "
                  "blockrender identical on Heaven II's shape LFO and three tones bent under their echoes (no "
                  "MF-104M tone moves its pitch rows yet)"),
    ("GM1", True, "Files: grains (_note_grains: the ocean drum's beads, rain, a stream, bubbles that glide, "
                  "clusters) -- GM 122, the SFX sets' grain keys"),
    ("GM1", True, "Live: the grain source -- a note's grains at their own onsets (gof), a held texture's pool "
                  "struck while the key is down (gpool, _tex_tick)"),
    ("GM1", True, "Files: numpy 1.26.4's pocketfft vendored (native/pocketfft.c), tonelib.pulse_series calling it"),
    ("GM1", True, "GM 127 Gunshot in files: a pulse voice (kind 7), the N-wave with its images, its blast's tail, "
                  "a class's own distance (reverb_distance: _src_dist, the send bus)"),
    ("GM1", True, "Live: a voice's own distance (live's template send, send_said, odd_until) -- the gunshot "
                  "in nvlive"),
    ("GM1", True, "GM 123 Bird Tweet and 124 Telephone, files and live: a struck voice repeated (tap_voice: the "
                  "chirps, the clapper's strokes each its own onset, level and phase; unison_drop_late)"),
    ("GM1", True, "GM 125 Helicopter, files and live: a played pipe with a measured series (VoiceSnap.hvt) and a "
                  "melodic note's sounding octaves in the engine's pitch"),
    ("GM1", True, "GM 120 Guitar Fret Noise, files and live: a noisy harmonic voice (the mixin's roll-off on a "
                  "formant body, its wash weighted by the body: VoiceSnap.chiff_bore)"),
    ("GM1", True, "GM 109 Bagpipe in files: the chanter (a played pipe, its own scale: scale_cents), the drones "
                  "as notes of the part (phrases, the CC1 corking, each its own class: Ev.kover, K's drone "
                  "region), a strike-in by the hand, a pipe's phase spread and mode lock"),
    ("GM1", True, "Live: the bagpipe's drones (live's own held drone voices: drone_wheel, drone_ratios; templates "
                  "built corked)"),
    ("GM1", True, "Files: two-port files (PortedMidi, meta 21) in the reader: channel + 16 x port, port B's "
                  "part exclusives as port A reads them, the legato over the merged stream"),
    ("GM1", True, "Files: GS's drum instrument NRPNs (GS_DRUM_NRPN: a key's pitch, level, pan, delay level; "
                  "reset by a GS or GM reset and a drum program change)"),
    ("GM1", False, "Files: MPE in the reader"),
    ("GM1", True, "Files: a class's own distance and gestures -- reverb_distance, its own chorus pedal "
                  "(chorus_send) and detuned pair (detuned_pair: chorus._pair), falls and rips on the valved "
                  "lattice (fall_cents, rip_cents: Song::gliss)"),
    ("GM1", True, "Files: tremolo picking (tremolo_pick_hz: 25.18 MandolinTrem, 27.25, 34.4, 115.16, the "
                  "biwa's): its strokes in Song::gliss, seeded as the Python's"),
    ("GM1", True, "Files: the uilleann pipes' cut (cut_semitones: 109.11, Song::gliss -- the flick takes the "
                  "written note's legato, _CUT_OF) and the pungi's wheel-chosen drone (111.8, Song::drones)"),
    ("GM1", True, "Live: the uilleann's cut (Live._cut_on: the flick, its key spared by the sweep) and the "
                  "pungi's drone (Live._drone_note, its own variation's templates: VDRN) -- their templates "
                  "without them (NO_CUT, NO_PART_DRONES)"),
    ("GM2", True, "Registered variations in files (GS's organs, harpsichords and hits, the MT-32 set's): a "
                  "variation's organ as a program's (Song::porg, nvrender's organ pass, the fader's swell by the "
                  "note's class); a layered one's organ still Python's"),
    ("GM2", True, "Files: layered registered variations (55.2 6th Hit, 6.24 Harpsi.o) -- a layer's organ: its "
                  "registration the layer class's, its chest's wind the variation's program class's (nvrender "
                  "vs blockrender identical on both)"),
    ("GM2", True, "Files: per-mode sympathetic strings (sympathetic_per_mode: 26.8 Pedal Steel; 107.8 Taisho "
                   "Koto's, with its drone stops and sweep) -- done with c2111e6's restore"),
    ("GM2", True, "Files: a didgeridoo's mouth (efxfilter.mouth: VOWEL's rows, its seeded wander -- "
                  "numpy's choice and dwell, scipy's glide -- or the part's wheel)"),
    ("GM2", True, "Files: the church bells (14.8-14.10: a tube's measured modes, 19 of them, a decay of their "
                  "own) and the feedback guitars (30.8, 31.8: the loop's partial and series as late copies)"),
    ("GM2", True, "Brass variations' blare (blare_db_per_khz: dB per kHz over a knee, renormalised) and the "
                  "SC-88's hammer-on (hammer_legato: the fretting hand, its strings and guitars)"),
    ("GM1", False, "Files: a sung part's text, vocalise and declared parts (TUNING_LYRIC_LANG, TUNING_VOCALISE, "
                   "TUNING_VOICE_PARTS)"),
    ("GM1", False, "Files: organs -- two on a channel, an organ beside a variation, swell laws of their own"),
    ("GM2", True, "Bank select in files (CC0/CC32): GM2's banks (120 drums, 121 melodic) and GS's variations, "
                  "layered ones too (nvrender; nvlive refuses a bank)"),
    ("GM2", True, "Bank select in nvlive: CC0 and CC32 latched until a program change reads them (GS's in a map, "
                  "GM 2's by MSB 121), a variation as a patch (its templates, classes, trim and live record: "
                  "VLIV), the picker's variations under each program (VNAM)"),
    ("GM2", True, "nvlive: a Moog variation under a capital that is no Moog's organ (its level: live's), a "
                  "layered variation's other layers -- native vs live identical (a harpsichord's, a clavinet's, "
                  "the drawbar organ's, a hit's, a trumpet's, a harp's, a phone's Moog; strings, choirs, brass "
                  "and hit stacks, an organ's and a map's own)"),
    ("GM2", True, "Live: the maps' own drum sets (MKIT read, MKNM their names; kit_in_map at a program change and "
                  "in the picker): a set's template selects it as a file does, CC32 then the program (live.py's "
                  "had raised on program 281 and played nothing); a GS Reset's program 0 asked where it falls "
                  "among a block's events, not after the program change that follows it -- native vs live "
                  "identical across the maps' sets"),
    ("SC-55", True, "The Sound Canvas display: a file's text and 16x16 dot pages (model 45: gsdisplay.py, "
                    "native/gsdisplay.h) shown in both panels' SC display box, and written beside a render as "
                    "OUT.display.txt (blockrender and nvrender, byte for byte)"),
    ("GM1", True, "The export memory-mapped in the host (MAP_PRIVATE): nvlive's peak 1.26 -> 0.72 GB, its "
                  "output identical"),
    ("GM2", True, "nvlive: the Moog variations (VLIV), plain and layered, a tone's own Auto Pan -- live "
                  "templates without the tone's effect (MOOG_NEUTRAL); a unison's and SYNC's refused"),
    ("GM2", True, "Tuning, files: the secondary (eastern) tuning, the meend, master fine/coarse tuning, "
                  "scale/octave tuning (GM 2's and GS's), MTS under gm2"),
    ("GM2", True, "Tuning, live: the secondary tuning (nvlive --eastern), a raga tuner's Sa and swaras, the meend"),
    ("GM2", True, "Tuning, live: the exclusives in nvlive -- master tuning, scale/octave tuning, MTS (a "
                  "real-time change and a select moving sounding keys), GM System On and GS Reset (live._sysex)"),
    ("GM2", True, "Master volume, files and live (blockrender's _mvol, live's master_gain ramp)"),
    ("GM2", True, "Files: a variation that meends (a sitar's, 63.127, 104.1/4/5) -- 104.4 Sitar/Drone's, a "
                  "layered one, had been refused: its note's meend read as Python's, before its layers part (the "
                  "variation's class), every layer riding it; nvrender vs blockrender identical on all four"),
    ("GM2", True, "Every GM 2 drum set's keys native (the last, the SFX set's Phonograph Noise: its record's "
                  "clicks, strike_flam_record), nvrender and nvlive"),
    ("SC-55", True, "The drum keys the maps' sets lacked: the tam-tams (Ethnic 45, 46, 48; both Asia sets' 73-75; "
                    "Rhythm FX's Reverse Gong: a cymbal's ModeDecays, its stroke tilt, its restrike folded) and "
                    "Rhythm FX's Alias (an aliasing sweep a harmonic a row), nvrender and nvlive"),
    ("MT-32", True, "An mt32mux file (a part a patch stamped before each note): its stamped channels' CC7 a "
                    "snapshot, not a fader (bend.cpp, STAMPED_SHARE)"),
    ("MT-32", False, "nvrender over mt32mux's own renders (Holst's planets: examples/mars.py ...), checked against "
                     "blockrender"),
    ("MT-32", True, "nvlive: the MT-32 set as a patch (bank 127): by bank select, and the picker's (its 128 "
                    "tones marked MT-32) -- native vs live identical"),
    ("CM-64", True, "The CM-32P (the CM-64's PCM half: the U-110's tones on channels 11-16): its 64 tones on bank "
                    "126 as the Sound Canvas's SC-55 map plays them (each a GS tone, under the CM-32P's name: CM-32P "
                    "OM pp.7-8, SC-8850 OM p.186); --map cm64 (TUNING_CM64) the CM-64 sound map's parts before a "
                    "file (SC-88Pro OM p.114), pans mirrored, its exclusives ignored; the pickers' CM-32P -- nvrender "
                    "identical on the CM-64 map's file, nvlive identical following a file's CM-32P tones"),
    ("GM1", True, "Live: the wheel's jobs on their own CCs (tonelib.WHEEL_CC: crescendo 4, swell 11, drive 12, "
                  "detune 13, drones 18, mouth 19, crank 20, tone 70, the rotor 80, the scanner 81, tremolo 92), "
                  "CC1 the vibrato and the wheel a route to each part's other jobs; an organ's wheel its swell, its "
                  "drive CC12's and the panel's knob (Part.drive: a default per organ, kept in presets and the "
                  "session) -- files and live native vs Python identical on the wheel's test files, every panel "
                  "control answered"),
    ("GM1", True, "nvlive and livetui: a MIDI input selector (I, or the header): several devices open at once, "
                  "merged; the session keeps them by device name, shared by both"),
    ("GM1", True, "Files: user drum sets (a key the set does not receive skipped), an organ beside a variation on "
                  "its channel (its registered organ off the shared fader) -- nvrender identical"),
    ("GM1", True, "Live: a voice's own chorus in native's templates -- the detuned pairs (Detuned EP 1 and 2, the "
                  "Detuned Organs, Vibraphones, Dual Horns...) and Chorus Gt.'s pedal had played as the plain "
                  "voice; the honky-tonk's detune and the bagpipe's corked drones in the templates on their own "
                  "CCs -- native vs live identical"),
    ("CM-64", True, "The CM-32L's sound effects on the rhythm part (keys 76-108) in nvlive -- native vs live "
                    "identical"),
    ("SC-55", True, "Files: a drum set read in a map (kit_in_map) where the map has none of its own"),
    ("SC-55", True, "The maps' own drum sets (percussion_map.KITS past 127) in files: their keys' classes and "
                    "tables (MKIT), a drum program past 127; a drum part on the insertion effect"),
    ("SC-55", True, "A tone's own insertion effect (insertion_efx) in files, all 58 of the maps' tones: its "
                    "level, OD stage (the part's valve), cabinet, EQ and sends; its chorus device (chorus.gs_copies) "
                    "and delay (gsdelay.expand, gsd_place's memo shared); an Auto Pan's tremolo; a Phaser's or "
                    "wah's moving filter (efxfilter on the lobe kernel); a bus (efxbus: Lo-Fi, a compressor -- "
                    "its rows rendered apart, before the post)"),
    ("GM2", True, "Files: a note's pressure (channel aftertouch, polytouch: _pressure_of) -- the reader had "
                  "dropped them -- and the plunger's moving filter on the channel's aftertouch (59.2)"),
    ("SC-55", True, "A FILE's GS setup (gs_setup): the reverb macro's room (an export per room), its level, "
                    "time and a delay's feedback in the sidecar; the GS EQ on each part that has it on (gs_eq_gain)"),
    ("SC-55", True, "A FILE's GS chorus and delay: CC93 through its chorus device (chorus.gs_device), CC94 into "
                    "its delay (gsdelay.device), each note's send at its onset"),
    ("SC-55", True, "A FILE's insertion effect (gsefx: 40 03, a part's 4p 22): each note's chain at its onset -- "
                    "Overdrive, Distortion, the guitar and bass multis (compressor, OD into the valve, cabinet, EQ, "
                    "chorus or flanger with its mix following the file); its level's steps in the amp's reference; "
                    "its sends; its effect controllers (40 03 1B-1E: a source's values moving + and #)"),
    ("SC-55", True, "A FILE's insertion effect, more types: 3D Manual and Auto (each note's angle), the "
                    "Compressor, Reverb and Gate Reverb buses (a part's, over its spans; the reverbs' responses and "
                    "convolution native/efxrev.c's, which efxbus shares), the pitch shifters, GTR Multi 3's wah, "
                    "Space D, a multi's own delay"),
    ("SC-55", True, "A FILE's insertion effect's other types: the chorus family, tremolo and auto pan, the six "
                    "delay types (the Mod Delay's LFO), the phasers, auto wahs, Step Flanger and Humanizer, "
                    "Lo-Fi 1 and 2 (numpy's noises), Limiter, Enhancer, Stereo-EQ, Spectrum, the multis (Rotary "
                    "Multi, Keyboard Multi's ring modulator), Rotary (its mics), the twelve series pairs and the "
                    "nine parallel pairs (branch B on the part's virtual channel); a controller on a choice"),
    ("SC-55", True, "Strokes fold as a gong's re-strikes do (fold_restrike): a roll's, a rasp's, a laugh's plain "
                    "strokes sound one strike's rows at a time, files and Python alike"),
    ("SC-55", False, "The chorus types' pre-filter high pass (Pre Filter 2): Python builds none -- a model to choose"),
    ("SC-55", True, "Live: a tone's own moving filter in nvlive -- the plunger (59.2, aftertouch) and the "
                    "didgeridoo's mouth (109.8, its wander or the wheel's vowel) on the tone's effect channel "
                    "(live._tone_fx), |H| each block on the rows' unfiltered level (Slab.filter_arm/swing)"),
    ("SC-55", True, "Live: the module's moving filters in nvlive -- Phaser, Auto Wah (its Sens from the part's "
                    "notes), the wahs' pedal, Step Flanger, Humanizer (gsefx.filter_setup over live's own EFX "
                    "timeline, compacted as _efx_event does), a flanger's feedback comb, Tremolo and Auto Pan "
                    "(Roland's waves; the Tremolo Chorus's): |H| each block on P2a's path, both ears; the "
                    "responses and controls on libm in Python too (native.xatan/xcexp/xabs/xpow/xexp)"),
    ("SC-55", True, "Live: the rest of the insertion effect in nvlive -- the chain builder shared "
                     "(native/efxchain.cpp), its state and each note's direct gain, the moving filters, a Moog's "
                     "rows under a moving filter, a tone's own insertion effect (an organ's too), the copies as "
                     "taps, the rotor (Separate's two mics) and the 3D place, the drive and cabinet and an OD's "
                     "valve, the compressor, a part's bus (Lo-Fi 1/2, compressor, limiter, enhancer, gate, "
                     "reverb), a parallel type's branch B (a second stamp on the part's virtual channel, "
                     "released with its note), a Keyboard Multi's copies (its taps unrolled as prepare's)"),
    ("SC-55", True, "Files: a streaming (windowed) nvrender for whole songs (--stream) -- it held the table whole "
                     "in float64, and a Sound Canvas song's is past memory (SHIRO's 6.4 min: 21.8M rows, ~8.7 GB). "
                     "Done, in checks to bank: the scan and replay, order keys, each pass at its horizon, windows; "
                     "the GS delay's and an MF-104's repeats, the chorus device, a part's bus (its reverbs at the "
                     "FFT block's lag), the tremolo, the scanner; two order bugs found on the way (the GS delay's "
                     "place memo, a pluck's hold a block early -- Python's stream had it too). Streamed equals "
                     "whole on 167 of 167 corpus windows and 64 of 66 GS files (2 refused: a variation no native voice "
                     "plays). OPEN: SHIRO full length was killed at the 3.5 GB cap within seconds -- tables "
                     "still held for the whole song (to measure, then bound). Open (rendered whole): a controller "
                     "matrix's tremolo, a tremolo stop beside a channel tremolo, a scanner on a register's or an "
                     "amplifier's channel, a chorus share rising on an amplifier's channel, a clavinet's rockers, "
                     "a moving filter -- committed (be5a996); only SHIRO at full length still meets the cap"),
    ("SC-55", True, "Files and live: every SC-88Pro insertion type measured on its own file "
                    "(examples/gs_efx_files.py, efx_coverage.py: Python vs native, stream vs whole, live vs "
                    "live.Live) -- only 8 of the 65 occur in a real song. Python vs native 63 of 65 identical "
                    "(2 refused by design), streamed equals whole on 63 (50 streamed, 13 rendered whole), "
                    "live 65 of 65"),
    ("SC-55", True, "Live: a HELD ROLL struck as it goes (percussion_map.RollSteps, live._roll_tick): every roll "
                    "key -- Standard's and Ethnic's hand rolls, the Jungle sets' machine rolls -- sustains while "
                    "held and closes on the key-up, as in files; a template its first hit (ROLL_FIRST), at its "
                    "strongest 4096 rows; its velocity its level. 117:24 Jngl SD Roll live (it was refused, its "
                    "probe past 2.5 GB; the Jungle keys' half-second roll had not fitted the slab). Native vs "
                    "live identical, drum keys and the keyboard's"),
    ("SC-55", True, "Files: the Jungle rolls a sampler's (Ben's A/B): a steady 23 a second, swelling -12 to -3 dB "
                    "over 2 s, +-1 dB, one in ten flammed, the closing hit accented -- measured on three takes "
                    "(~/Documents/refs/jungle_roll); Standard's and Ethnic's keep the hand roll"),
    ("SC-55", True, "Files: the rhythm part's assignment (40 1p 15); the controller matrix (40 2p, GM2 09) where "
                    "it moves nothing"),
    ("SC-55", True, "Files: a controller matrix that moves (ctrlmatrix): its cutoff and LFO rate in the sound "
                    "controls, its amplitude in the level and fader, its pitch and vibrato on the pitch stream, its "
                    "tremolo's rows; a variation that meends; a layered variation's registered layers"),
    ("SC-55", False, "Files: GS's other exclusives -- part parameters, TONE MAP-0, drum setup's levels, pans, "
                     "sends and Rx note on, and the USER DRUM SETS (e6199b7: a key another set's, its own pitch, "
                     "level, pan and receive switch -- nvrender identical) read; what is left: drum setup's "
                     "exclusive group and Rx note off, read but used by neither engine (Python's too)"),
    ("SC-55", True, "Melodic SFX (patch_map.melodic_sfx): a kit's sound on a keyboard part, transposed whole "
                    "(transposed_from_hz: _XP), its kit key's strokes (sfx_strokes_of), the weather voices "
                    "(a measured mode set under the noise's roll-off, its breath beside it)"),
    ("SC-55", True, "SFX voices with a fixed vibrato of their own (skid, starship, scream: VoiceSnap.fv_*)"),
    ("SC-55", True, "The heartbeat: its ECG's mode phases, its blood flow's timed noise bands (noise_events)"),
    ("SC-55", True, "A drum's sounding octaves (the SFX sets' helicopter: its key a rotor, under its kit pitch)"),
    ("SC-55", True, "Files: the fire siren's rotor (siren.py: its motor and coast, carried key to key, a row a "
                    "note under the channel's fader) -- the SFX set's 67, the CM-32L's 91"),
    ("SC-55", True, "The Helmholtz siren (GM 2's 125.5: its air from velocity and pressure, its upper disc on "
                     "the crank) in files; live's siren block in nvlive -- done (269553e: its air, the crank's upper disc)"),
    ("GM1", True, "examples/struct_check.py: each ctypes mirror's field offsets against the C struct's (a "
                  "reordered field of the same size passed the size check silently)"),
    ("SC-55", True, "Melodic hits: a hand drum's or a kit's detail on a melodic voice (strike_phase_spread, "
                     "stroke_scatter, jitter_by_partial, bloom_seconds, played_backwards, strike_noise_layers, "
                     "one_shot and gate_time off a kit) -- dholak, kelontuk, reversed pieces, cymbal tones -- every tone that needs one native (coverage whole); each detail still gated to the voices that use it"),
    ("SC-55", True, "Crowds: a few people clapping (strike_flam_people, their palms ringing: "
                    "strike_flam_people_peak) -- Small Club, the applause wave; GM 2's Electronic and TR-808 sets"),
    ("SC-55", True, "A recorded flam (strike_flam_record) and a crackle's exponential levels (strike_flam_exp_db, "
                     "with a gate): phono noise -- every drum set whole"),
    ("SC-88", True, "Variations that change a native family's methods (the SC-88 maps' brass, strings, guitars, "
                     "flutes and cymbal menus: a subclass the engine's owner checks refuse) -- each family's "
                     "overrides ported -- every variation native in files (coverage whole)"),
    ("SC-88", True, "Brass detail: mode_lock_spread and directivity_radius off an organ (16 brass variations) -- every brass variation native in files"),
    ("SC-88", True, "Electric pianos with mode phases (mode_phase: the Detuned EPs, a Wurlitzer variation) -- every EP variation native in files"),
    ("SC-88", True, "Guitars: feedback (feedback_harmonic), open strings ringing (open_string_ring), sections "
                     "(chorus guitar, biwa tremolo, the gangsa pair) -- every guitar variation native in files (open strings: files only, live has none)"),
    ("SC-88", True, "The SFX families: siren, starship, laser, scream, heartbeat, Morse, machine gun, engine, "
                     "car pass, skid, door creak, birds, fret slide (noise_events, pulse, ring_db, sweeps) -- every SFX tone native in files (the Morse keyboard's strokes: files only)"),
    ("SC-88", True, "Dulcimer and accordion variations (course_keys, unison_shares_phase; speech_harmonic_exp) -- every variation native in files"),
    # A SUPERSET OF THE SOUND CANVAS (Ben, 2026-11-09): every GS message an SC-8850 receives doing
    # what Roland's does (or more) in files and live, and every front-panel control a TUI one --
    # Python first (the oracle), then native
    ("SC-55", False, "Sound Canvas superset, files: the GS messages the reader ignores -- a part's RX. CHANNEL "
                     "(another channel's notes: Roland's own layering), its Rx switches (pitch bend, volume, "
                     "program change... off), ASSIGN MODE (a repeated note's retrigger), the CC1/CC2 "
                     "CONTROLLER NUMBERS its matrix reads, MASTER PAN, VOICE RESERVE (accepted: we have more), "
                     "the display's text and 16x16 dot pages (45 xx) -- read and kept (the reader no longer "
                     "refuses them), the display written beside a render (OUT.display.txt, nvrender's the same, "
                     "line for line); open: the file renders honouring RX CHANNEL, the Rx switches, ASSIGN MODE "
                     "and master pan (live does since 00ec34d)"),
    ("SC-55", False, "Sound Canvas superset, live: what a sequencer sends that live ignores and a file render "
                     "honours -- done (both engines, native vs live identical, each message counted and its effect "
                     "measured): the system reverb, chorus and delay (macros and parameters), the GS EQ, a GS "
                     "reset's sends, RX CHANNEL, the Rx switches, master pan; open: drum setup and the user drum "
                     "sets live, the controller matrix live, ASSIGN MODE's modes (stored only)"),
    ("SC-55", False, "Sound Canvas superset, the controllers -- done: the Rx switches live (a message a part "
                     "does not receive dropped, both engines, 00ec34d), the wheel's jobs on CCs of their own; "
                     "open: the CC1/CC2 controller numbers (stored, not yet read by anything) and the controller "
                     "matrix live, into the CC-route design (a controller, a destination, a depth)"),
    ("SC-8850", False, "Sound Canvas superset, the panel (livetui, then nvlive) -- done: per-part pan, reverb, "
                       "chorus and delay sends as part columns; the system effects page (G: the reverb's type, "
                       "level, time and delay feedback, the chorus's and delay's types and parameters, the EQ -- "
                       "each move a GS message, so a reset puts it back); the display (both TUIs' SC display box); "
                       "the map in the picker (the standard); open: velocity sense as a column (the engine first), "
                       "per-part level meters (the 16 bars), a GS Reset key, solo beside mute, user tones and drum "
                       "sets edited and stored"),
]

# MT-32 and CM-64 between GM 2 and the Sound Canvas, in the hardware's own
# order: the MT-32's 128 tones (GS bank 127, patch_map.MT32_SET) and its
# rhythm part's keys (the CM-32L set's own drums, 35-75); the CM-64's CM-32L
# adds the set's sound effects (CM32L_SFX), its CM-32P half (PCM) a task
# A TONE's OWN INSERTION EFFECT, LIVE (kept by hand, as TASKS): what of a
# tone's own effect (its class's insertion_efx, gsefx.chain of it) nvlive plays
# as live.py does -- each feature of the chain with where its port stands, the
# tone's state the worst of its features' ("yes" where it has only what is
# done: level, EQ, the moving filters, a flanger's comb, tremolo and pan)
LIVE_EFX = (
    ("bus", "yes", "the part's bus (Lo-Fi, compressor, gate, reverb)"),
    ("par", "not yet", "a parallel type's branch B"),
    ("kbm", "not yet", "the Keyboard Multi's copies"),
    ("comp", "not yet", "a multi's compressor (Python's live plays none either)"),
    ("rotary", "yes", "the rotor"),
    ("pos3d", "yes", "the 3D place"),
    ("od", "yes", "the drive and cabinet"),
    ("copies", "yes", "the copies (taps)"),
)
_LIVE_RANK = {"yes": 0, "checks pending": 1, "not yet": 2}


def tone_effect_live(fx):
    """(the type's name, its live state, what stands in its way) for a tone's
    own effect (insertion_efx); ("", "none", "") without one"""
    if not fx:
        return "", "none", ""
    import gsefx as G
    ch = G.chain(G.tone_state(*fx)) or {}
    name = ch.get("name") or ""
    has = lambda k: ch.get(k) not in (None, False, 0, {}, [], ())
    feats = set()
    if has("bus") or has("bus_mix"):
        feats.add("bus")
    if has("par"):
        feats.add("par")
    if name == "Keyboard Multi":
        feats.add("kbm")
    if has("comp"):
        feats.add("comp")
    for k in ("rotary", "pos3d"):
        if has(k):
            feats.add(k)
    if has("od_gain") or has("cabinet"):
        feats.add("od")
    if (has("cf") and not ch["cf"][0].get("fb")) or has("dly"):
        feats.add("copies")
    state, why = "yes", []
    for f, st, what in LIVE_EFX:
        if f in feats:
            why.append(what)
            if _LIVE_RANK[st] > _LIVE_RANK[state]:
                state = st
    return name, state, "; ".join(why)


# LIVE (nvlive): what the native player offers and plays, read from the
# player itself -- a host opened on a live export (native_export.py --live),
# its patch list (nv_host_patches: every program, set and variation, each
# native or not, as its picker greys them). A tone the list leaves out that
# bank select still reaches (as live's resolve_patch) is "bank select"; the
# maps' own drum sets are reached so (kit_in_map). Beside each stage, the
# live checks that hold it to Python's live, every sample (nvlive_check.py;
# kept by hand, as TASKS): what was played, identical.
LIVE_CHECKS = {
    "GM1": "piano (CPU and GPU), organ, program switching, a Moog's SYNC (P5 Sync Lead), unison "
           "(JP SuperSaw), its LFO 2, loops and multi-trigger; Standard's Snare Roll held and tapped",
    "GM2": "c2111e6's restored GM 2 tones; MutedDis.Gt's open strings; layered variations; Moog "
           "variations under other capitals; the Eastern tuning switched on a sitar",
    "MT-32": "six MT-32 tones by bank select (CC0 127), a phrase each",
    "CM-64": "the CM-32L set's sound effects, keys 76-108",
    "SC-88": "c2111e6's restored SC-88 tones; the maps' own drum sets",
    "SC-88 Pro": "Calculating (the Morse keyboard)",
    "SC-8850": "Jngl SD Roll held and tapped from the keyboard; the Jungle rolls on their drum keys",
}


def live_patches(nvx):
    """nvlive's patch list from the export NVX: [dict(program, variation,
    drums, native, name)] -- a host opened in a process of its own (it holds
    the export and is never freed), capped as every heavy job"""
    import json
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "patches.json")
        subprocess.check_call(["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=3500M",
                               "-p", "MemorySwapMax=0", sys.executable, os.path.abspath(__file__),
                               "--patches", nvx, out], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(out) as f:
            return json.load(f)


def _patches_child(nvx, out):
    import ctypes
    import json
    import native as N

    class Patch(ctypes.Structure):
        _fields_ = [("program", ctypes.c_int), ("variation", ctypes.c_int), ("drums", ctypes.c_int),
                    ("native", ctypes.c_int), ("pick", ctypes.c_int), ("name", ctypes.c_char * 64)]
    d = N.lib()
    vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    d.nv_host_open_args.restype = vp
    d.nv_host_open_args.argtypes = [ci, ctypes.POINTER(cp), cp, ci]
    d.nv_host_patches.argtypes = [vp, vp, ci]
    av = [b"nvlive", os.fsencode(nvx), b"--program=0", b"--cpu", b"--no-pipeline", b"--no-register",
          b"--no-governor"]
    err = ctypes.create_string_buffer(256)
    h = d.nv_host_open_args(len(av), (cp * len(av))(*av), err, 256)
    if not h:
        raise SystemExit("native_coverage: the host refused %s: %s" % (nvx, err.value.decode()))
    n = d.nv_host_patches(h, None, 0)
    pt = (Patch * n)()
    d.nv_host_patches(h, pt, n)
    with open(out, "w") as f:
        json.dump([dict(program=x.program, variation=x.variation, drums=x.drums, native=x.native,
                        name=x.name.decode("utf-8", "replace")) for x in pt], f)
    os._exit(0)                 # (the host's threads run on: not joined)


STAGES = (("GM1", None), ("GM2", 'gm2'), ("MT-32", 'mt32'), ("CM-64", 'cm64'), ("SC-55", 1), ("SC-88", 2),
          ("SC-88 Pro", 3), ("SC-8850", 4))


def main(argv):
    # --json DIR: the coverage page's data besides (stages, tones, kits, tasks .json)
    jdir = None
    if "--json" in argv:
        i = argv.index("--json")
        jdir = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) > 3 and argv[1] == "--patches":
        return _patches_child(argv[2], argv[3])
    # --live NVX: the live table besides, from nvlive's own patch list
    lp = None
    if "--live" in argv:
        i = argv.index("--live")
        lp = live_patches(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    out = argv[1] if len(argv) > 1 else os.path.join(HERE, "native.md")
    import native as N
    import patch_map as P
    import percussion_map as PM
    import blockrender as B
    import livetui as LT

    def native_cls(c):
        return isinstance(c, type) and N.note_class(c) is not None

    def program_native(p):
        return all(native_cls(B.property_class_for_note(p, k)) for k in range(21, 109))

    # a variation: native where bank select reaches it -- every key A0 to C8
    # of each of its slots (a layered one's layers) a class the engine plays
    # (native.variation_tables, as native_export writes them)
    vslots, ventries = N.variation_tables()[:2]
    vnat = {(e[0], e[1]): all(all(vslots[s][3][k] is not None for k in range(21, 109)) for s, _, _, _ in e[2])
            for e in ventries[1:]}

    # each tone's own effect (insertion_efx): a variation's from its slots'
    # classes (the first with one), a program's from its class at middle C
    vfx = {}
    for e in ventries[1:]:
        for sl, _, _, _ in e[2]:
            c = vslots[sl][3][60]
            fx = getattr(c, "insertion_efx", None) if c is not None else None
            if fx:
                vfx[(e[0], e[1])] = fx
                break

    def tone_fx(p, key):
        if key:
            return vfx.get((p, key))
        c = B.property_class_for_note(p, 60)
        return getattr(c, "insertion_efx", None) if isinstance(c, type) else None

    def variation_native(p, key):
        return vnat.get((p, key), program_native(p)) if key else program_native(p)

    kc = N.kits()[0]
    # ...and the maps' own sets (native.map_kits: past 127, their own tables)
    mk_ids, mkc = N.map_kits()[:2]

    def kit_keys(prog, only=None):
        kit = PM.kit_for_program(prog)
        keys = [k for k in range(128) if PM.percussion_for_note(k, kit) and (only is None or k in only)]
        if prog < 128:
            nat = [k for k in keys if native_cls(kc[128 * prog + k])]
        else:
            j = mk_ids.index(prog) if prog in mk_ids else -1
            nat = [k for k in keys if j >= 0 and native_cls(mkc[128 * j + k])]
        return keys, nat

    lines = ["# The native port: what remains", "",
             "What of each standard the C engine (native/) plays in a file render, bit for bit",
             "against blockrender. Generated by `examples/native_coverage.py` from the engine",
             "itself, so it cannot drift: a tone is native when every key of it, A0 to C8, is a",
             "class the engine plays (a drum set: every key it defines). The order is the plan's:",
             "General MIDI 1, then GM 2, the MT-32 and CM-64, then the Sound Canvas maps, each stage only what the one",
             "before it did not already bring. The work that is not a tone, and live's side, are",
             "kept by hand in the script's TASKS.", ""]
    summary = []
    # ...live's: each tone as nvlive's list has it ("picker": offered and
    # native; "bank select": not listed, reached by CC0; "refused"; "no")
    lsum = []
    if lp is not None:
        from native_export import LIVE_REFUSED
        lprog = {(x["program"], bool(x["drums"])): bool(x["native"]) for x in lp if not x["variation"]}
        lvar = {(x["program"], x["variation"]): bool(x["native"]) for x in lp if x["variation"]}

    def tone_live(p, key):
        if (p, key) in LIVE_REFUSED:
            return "refused"
        if not key:
            return "picker" if lprog.get((p, False)) else "no"
        if (p, key) in lvar:
            return "picker" if lvar[(p, key)] else "no"
        return "bank select" if variation_native(p, key) else "no"

    def kit_live(s, nk, nn):
        if nn < nk:
            return "no"
        return ("picker" if lprog.get((s, True)) else "no") if s < 128 else "bank select"
    js = dict(stages=[], tones=[], kits=[], tasks=[dict(stage=s, done=bool(d), task=t) for s, d, t in TASKS])
    seen = set()            # (program, variation key) a stage before has listed
    body = []
    for stage, src in STAGES:
        if src is None:
            tones = [(p, 0, LT.GM[p]) for p in range(128)]
            kits = [0]
        elif src == 'gm2':
            tones = sorted({(p, P.gm2_bank(p, l), P.GM2_NAMES[(p, l)]) for (p, l) in P.GM2_NAMES if l
                            and P.gm2_bank(p, l)})
            kits = [0, 8, 16, 24, 25, 32, 40, 48, 56]
        elif src == 'mt32':
            tones = [(p, 127, P.VARIATION_NAMES[(p, 127)]) for p in range(128)]
            kits = [(127, "MT-32 rhythm part", set(PM.CM32L_DRUMS))]
        elif src == 'cm64':
            # the CM-32P's 64 (bank 126: the Sound Canvas's SC-55 map of it)
            tones = [(p, 126, P.VARIATION_NAMES[(p, 126)]) for p in range(len(P.CM32P_SET))]
            kits = [(127, "CM-32L sound effects", set(PM.KITS[127]) - set(PM.CM32L_DRUMS))]
        else:
            tones = sorted({(p, P.map_bank(p, b, src), P.MAP_NAMES[src][(p, b)]) for (p, b) in P.MAP_NAMES[src]
                            if b and P.map_bank(p, b, src)})
            kits = sorted({PM.kit_in_map(s, src) for s in PM.DRUM_SETS if s < 128})
        new = [t for t in tones if (t[0], t[1]) not in seen]
        seen |= {(t[0], t[1]) for t in tones}
        kits = [k for k in kits if isinstance(k, tuple) or ('kit', k) not in seen]
        seen |= {('kit', k[0] if isinstance(k, tuple) else k) for k in kits}
        nat = [t for t in new if variation_native(t[0], t[1])]
        rest = [t for t in new if t not in nat]
        ks = [(k[0], k[1]) + tuple(map(len, kit_keys(k[0], k[2]))) if isinstance(k, tuple) else
              (k, PM.drum_set_name(k if k < 128 else k % 128)) + tuple(map(len, kit_keys(k))) for k in kits]
        kfull = sum(1 for k in ks if k[2] == k[3])
        summary.append("| %s | %d of %d | %d of %d |" % (stage, len(nat), len(new), kfull, len(ks)))
        js['stages'].append(dict(stage=stage, order=len(js['stages']), tones_native=len(nat), tones_total=len(new),
                                 kits_whole=kfull, kits_total=len(ks)))
        if lp is not None:
            _tl = [tone_live(p, key) for p, key, _ in new]
            _kl = [kit_live(s, nk, nn) for s, _, nk, nn in ks]
            _out = ["%s %s (%s)" % ("%d" % p if src is None else "%d.%d" % (p, key if key >= 126 else key % 128),
                                    name, st) for (p, key, name), st in zip(new, _tl) if st in ("no", "refused")]
            _out += ["drum set %s %s" % (s, name) for (s, name, _, _), st in zip(ks, _kl) if st == "no"]
            js.setdefault('live', []).append(dict(
                stage=stage, order=len(js['live']), tones_total=len(new),
                tones_live=sum(st in ("picker", "bank select") for st in _tl),
                tones_picker=_tl.count("picker"), tones_bank=_tl.count("bank select"),
                kits_total=len(ks), kits_live=sum(st != "no" for st in _kl),
                not_live="; ".join(_out), checked=LIVE_CHECKS.get(stage, "")))
            lsum.append("| %s | %d of %d (%d by bank select only) | %d of %d | %s |" % (
                stage, js['live'][-1]['tones_live'], len(new), _tl.count("bank select"),
                js['live'][-1]['kits_live'], len(ks), _out and "; ".join(_out) or "--"))
        for i, (p, key, name) in enumerate(new):
            _to = P.MT32_SET[p][1] if src == 'mt32' else P.CM32P_SET[p][1][0] if src == 'cm64' else p
            _fxn, _fxs, _fxw = tone_effect_live(tone_fx(p, key) if src != 'mt32' else None)
            js['tones'].append(dict(stage=stage, program=p, variation=key,
                                    tone=str(p) if src is None else "%d.%d" % (p, key if key >= 126 else key % 128),
                                    name=name, family=LT.FAMILIES[14 if isinstance(_to, tuple) else _to // 8],
                                    native=(p, key, name) in nat, own_effect=_fxn, effect_live=_fxs,
                                    effect_note=_fxw))
            if lp is not None:
                js['tones'][-1]['live'] = _tl[i]
        for j, (s, name, nk, nn) in enumerate(ks):
            js['kits'].append(dict(stage=stage, set=s, name=name, keys=nk, native_keys=nn))
            if lp is not None:
                js['kits'][-1]['live'] = _kl[j]
        body += ["## %s" % stage, ""]
        stasks = [t for t in TASKS if t[0] == stage]
        if stasks:
            body += ["What it needs first, and live's side:", ""]
            body += ["- [%s] %s" % ("x" if done else " ", text) for _, done, text in stasks]
            body.append("")
        body += ["Tones: %d of %d native%s." % (len(nat), len(new),
                                                "" if src is None else " (new at this stage)"), ""]
        fam = {}
        for p, key, name in rest:
            # (the MT-32's by the voice it plays here: its GM program's family, a kit key's percussion)
            _to = P.MT32_SET[p][1] if src == 'mt32' else P.CM32P_SET[p][1][0] if src == 'cm64' else p
            fam.setdefault(14 if isinstance(_to, tuple) else _to // 8, []).append((p, key, name))
        for f in sorted(fam):
            items = ", ".join(("%d %s" % (p, name)) if src is None else ("%d.%d %s" % (p, key if key >= 126 else key % 128, name))
                              for p, key, name in fam[f])
            body.append("- [ ] **%s** -- %s" % (LT.FAMILIES[f], items))
        body.append("")
        body += ["Drum sets: %d of %d with every key native%s." % (kfull, len(ks), "" if src is None else
                                                                   " (new at this stage)"), ""]
        for s, name, nk, nn in ks:
            if nn < nk:
                body.append("- [ ] %d %s -- %d of %d keys native" % (s, name, nn, nk))
        body.append("")
    lines += ["| stage | tones native | drum sets whole |", "|---|---|---|"] + summary + [""]
    if lsum:
        lines += ["Live (nvlive, from its own patch list):", "",
                  "| stage | tones live | drum sets live | not live |", "|---|---|---|---|"] + lsum + [""]
    lines += body
    with open(out, "w") as f:
        f.write("\n".join(lines))
    print("native coverage -> %s" % out)
    if jdir:
        import json
        os.makedirs(jdir, exist_ok=True)
        for k, v in js.items():
            with open(os.path.join(jdir, k + ".json"), "w") as f:
                json.dump(v, f, indent=0)
        print("...and its page's data -> %s" % jdir)
    print("\n".join(summary))
    if lsum:
        print("live:\n" + "\n".join(lsum))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
