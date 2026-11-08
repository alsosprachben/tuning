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
    ("GM1", True, "Live: the Moog (knob-neutral templates and the slab's moog.weights; CC71-75 its knobs; "
                  "a layered voice; the MF-104M) -- not yet a unison or SYNC live"),
    ("GM1", True, "Live: check the fiddle, tinkle bell, melodic tom, reverse cymbal and breath noise against live.Live"),
    ("GM1", True, "Live: a drum set identical to live.Live beyond the kick and toms (the Standard set's every key, "
                  "nvlive end to end)"),
    ("GM1", False, "Files: GS's controller-matrix cutoff on a Moog (_CMXEV) -- nvrender's reader refuses it"),
    ("GM1", True, "Files: an organ after another tone on its channel (its tremolo keyed by its mix channel)"),
    ("GM1", False, "Moog: an MF-104M on a note whose pitch or shapes move (SYNC and a unison: native in files)"),
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
    ("GM2", False, "Files: layered registered variations (55.2 6th Hit, 6.24 Harpsi.o) -- a layer's organ: its "
                   "registration the layer class's, its chest's wind the variation's program class's"),
    ("GM2", False, "Files: per-mode sympathetic strings (sympathetic_per_mode: 26.8 Pedal Steel; 107.8 Taisho "
                   "Koto's, with its drone stops and sweep)"),
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
    ("GM2", False, "nvlive: a Moog variation under a capital that is no Moog's organ (its level: live's), a "
                   "layered variation's other layers, the maps' own drum sets"),
    ("GM2", True, "nvlive: the Moog variations (VLIV), plain and layered, a tone's own Auto Pan -- live "
                  "templates without the tone's effect (MOOG_NEUTRAL); a unison's and SYNC's refused"),
    ("GM2", True, "Tuning, files: the secondary (eastern) tuning, the meend, master fine/coarse tuning, "
                  "scale/octave tuning (GM 2's and GS's), MTS under gm2"),
    ("GM2", True, "Tuning, live: the secondary tuning (nvlive --eastern), a raga tuner's Sa and swaras, the meend"),
    ("GM2", True, "Tuning, live: the exclusives in nvlive -- master tuning, scale/octave tuning, MTS (a "
                  "real-time change and a select moving sounding keys), GM System On and GS Reset (live._sysex)"),
    ("GM2", True, "Master volume, files and live (blockrender's _mvol, live's master_gain ramp)"),
    ("GM2", False, "Files: a variation that meends (a sitar's, 63.127, 104.1/4/5)"),
    ("GM2", False, "Files: a GM 2 drum set the engine lacks keys of (3 of 8 sets)"),
    ("MT-32", True, "An mt32mux file (a part a patch stamped before each note): its stamped channels' CC7 a "
                    "snapshot, not a fader (bend.cpp, STAMPED_SHARE)"),
    ("MT-32", False, "nvrender over mt32mux's own renders (Holst's planets: examples/mars.py ...), checked against "
                     "blockrender"),
    ("MT-32", False, "nvlive: the MT-32 set as a patch (bank 127) -- live's bank select first"),
    ("CM-64", False, "The CM-32P (the CM-64's PCM half: the U-110's tones on channels 11-16) -- Python has none yet"),
    ("CM-64", False, "The CM-32L's sound effects on the rhythm part (keys 76-108) in nvlive"),
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
    ("SC-55", False, "Live: the rest of the insertion effect in nvlive -- the chain builder shared "
                     "(native/efxchain.cpp), its state and each note's direct gain, the moving filters done; "
                     "a Moog's rows under a moving filter, a tone's own insertion effect done; the copies "
                     "as taps (tapkernel.c), a drive or cabinet, a part's bus (Lo-Fi), branch B, the rotor "
                     "and 3D place, an OD's valve"),
    ("SC-55", False, "Files: a streaming (windowed) nvrender for whole songs -- it holds the table whole in float64, "
                     "and a Sound Canvas song's is past memory (SHIRO's 6.4 min: 21.8M rows, ~8.7 GB; killed at the "
                     "3.5 GB cap) where Python streams (streamrender); every native check so far a 20 s excerpt. "
                     "Next after main's gate"),
    ("SC-55", False, "Live: 117:24 Jngl SD Roll refused (LIVE_REFUSED: its velocity probe's table past 2.5 GB) "
                     "-- a re-attack within a row, a gain track like the damper's, would shrink it"),
    ("SC-55", True, "Files: the rhythm part's assignment (40 1p 15); the controller matrix (40 2p, GM2 09) where "
                    "it moves nothing"),
    ("SC-55", True, "Files: a controller matrix that moves (ctrlmatrix): its cutoff and LFO rate in the sound "
                    "controls, its amplitude in the level and fader, its pitch and vibrato on the pitch stream, its "
                    "tremolo's rows; a variation that meends; a layered variation's registered layers"),
    ("SC-55", False, "Files: GS's other exclusives -- part parameters (parse_gs_part), drum setup and the user "
                     "sets, TONE MAP-0 (the reader refuses them, -4)"),
    ("SC-55", True, "Melodic SFX (patch_map.melodic_sfx): a kit's sound on a keyboard part, transposed whole "
                    "(transposed_from_hz: _XP), its kit key's strokes (sfx_strokes_of), the weather voices "
                    "(a measured mode set under the noise's roll-off, its breath beside it)"),
    ("SC-55", True, "SFX voices with a fixed vibrato of their own (skid, starship, scream: VoiceSnap.fv_*)"),
    ("SC-55", True, "The heartbeat: its ECG's mode phases, its blood flow's timed noise bands (noise_events)"),
    ("SC-55", True, "A drum's sounding octaves (the SFX sets' helicopter: its key a rotor, under its kit pitch)"),
    ("SC-55", True, "Files: the fire siren's rotor (siren.py: its motor and coast, carried key to key, a row a "
                    "note under the channel's fader) -- the SFX set's 67, the CM-32L's 91"),
    ("SC-55", False, "The Helmholtz siren (GM 2's 125.5: its air from velocity and pressure, its upper disc on "
                     "the crank) in files; live's siren block in nvlive"),
    ("GM1", True, "examples/struct_check.py: each ctypes mirror's field offsets against the C struct's (a "
                  "reordered field of the same size passed the size check silently)"),
    ("SC-55", False, "Melodic hits: a hand drum's or a kit's detail on a melodic voice (strike_phase_spread, "
                     "stroke_scatter, jitter_by_partial, bloom_seconds, played_backwards, strike_noise_layers, "
                     "one_shot and gate_time off a kit) -- dholak, kelontuk, reversed pieces, cymbal tones"),
    ("SC-55", True, "Crowds: a few people clapping (strike_flam_people, their palms ringing: "
                    "strike_flam_people_peak) -- Small Club, the applause wave; GM 2's Electronic and TR-808 sets"),
    ("SC-55", False, "A recorded flam (strike_flam_record) and a crackle's exponential levels (strike_flam_exp_db, "
                     "with a gate): phono noise"),
    ("SC-88", False, "Variations that change a native family's methods (the SC-88 maps' brass, strings, guitars, "
                     "flutes and cymbal menus: a subclass the engine's owner checks refuse) -- each family's "
                     "overrides ported"),
    ("SC-88", False, "Brass detail: mode_lock_spread and directivity_radius off an organ (16 brass variations)"),
    ("SC-88", False, "Electric pianos with mode phases (mode_phase: the Detuned EPs, a Wurlitzer variation)"),
    ("SC-88", False, "Guitars: feedback (feedback_harmonic), open strings ringing (open_string_ring), sections "
                     "(chorus guitar, biwa tremolo, the gangsa pair)"),
    ("SC-88", False, "The SFX families: siren, starship, laser, scream, heartbeat, Morse, machine gun, engine, "
                     "car pass, skid, door creak, birds, fret slide (noise_events, pulse, ring_db, sweeps)"),
    ("SC-88", False, "Dulcimer and accordion variations (course_keys, unison_shares_phase; speech_harmonic_exp)"),
]

# MT-32 and CM-64 between GM 2 and the Sound Canvas, in the hardware's own
# order: the MT-32's 128 tones (GS bank 127, patch_map.MT32_SET) and its
# rhythm part's keys (the CM-32L set's own drums, 35-75); the CM-64's CM-32L
# adds the set's sound effects (CM32L_SFX), its CM-32P half (PCM) a task
STAGES = (("GM1", None), ("GM2", 'gm2'), ("MT-32", 'mt32'), ("CM-64", 'cm64'), ("SC-55", 1), ("SC-88", 2),
          ("SC-88 Pro", 3), ("SC-8850", 4))


def main(argv):
    # --json DIR: the coverage page's data besides (stages, tones, kits, tasks .json)
    jdir = None
    if "--json" in argv:
        i = argv.index("--json")
        jdir = argv[i + 1]
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
            tones = []
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
        for p, key, name in new:
            _to = P.MT32_SET[p][1] if src == 'mt32' else p
            js['tones'].append(dict(stage=stage, program=p, variation=key,
                                    tone=str(p) if src is None else "%d.%d" % (p, key if key == 127 else key % 128),
                                    name=name, family=LT.FAMILIES[14 if isinstance(_to, tuple) else _to // 8],
                                    native=(p, key, name) in nat))
        for s, name, nk, nn in ks:
            js['kits'].append(dict(stage=stage, set=s, name=name, keys=nk, native_keys=nn))
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
            _to = P.MT32_SET[p][1] if src == 'mt32' else p
            fam.setdefault(14 if isinstance(_to, tuple) else _to // 8, []).append((p, key, name))
        for f in sorted(fam):
            items = ", ".join(("%d %s" % (p, name)) if src is None else ("%d.%d %s" % (p, key if key == 127 else key % 128, name))
                              for p, key, name in fam[f])
            body.append("- [ ] **%s** -- %s" % (LT.FAMILIES[f], items))
        body.append("")
        body += ["Drum sets: %d of %d with every key native%s." % (kfull, len(ks), "" if src is None else
                                                                   " (new at this stage)"), ""]
        for s, name, nk, nn in ks:
            if nn < nk:
                body.append("- [ ] %d %s -- %d of %d keys native" % (s, name, nn, nk))
        body.append("")
    lines += ["| stage | tones native | drum sets whole |", "|---|---|---|"] + summary + [""] + body
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
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
