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
    ("GM1", False, "Live: the bagpipe's drones (live's own held drone voices: drone_wheel, drone_ratios; templates "
                   "built corked) -- nvlive refuses the bagpipe"),
    ("GM1", False, "Files: two-port files (PortedMidi, meta 21) in the reader"),
    ("GM1", False, "Files: NRPNs and MPE in the reader"),
    ("GM1", True, "Files: a class's own distance and gestures -- reverb_distance, its own chorus pedal "
                  "(chorus_send) and detuned pair (detuned_pair: chorus._pair), falls and rips on the valved "
                  "lattice (fall_cents, rip_cents: Song::gliss)"),
    ("GM1", True, "Files: tremolo picking (tremolo_pick_hz: 25.18 MandolinTrem, 27.25, 34.4, 115.16, the "
                  "biwa's): its strokes in Song::gliss, seeded as the Python's"),
    ("GM1", False, "Files: the uilleann pipes' cut (cut_semitones: 109.11 -- _CUT_OF's legato and occurrence)"),
    ("GM2", True, "Registered variations in files (GS's organs, harpsichords and hits, the MT-32 set's): a "
                  "variation's organ as a program's (Song::porg, nvrender's organ pass, the fader's swell by the "
                  "note's class); a layered one's organ still Python's"),
    ("GM2", False, "Files: layered registered variations (55.2 6th Hit, 6.24 Harpsi.o) -- a layer's organ: its "
                   "registration the layer class's, its chest's wind the variation's program class's"),
    ("GM2", False, "Files: per-mode sympathetic strings (sympathetic_per_mode: 26.8 Pedal Steel; 107.8 Taisho "
                   "Koto's, with its drone stops and sweep)"),
    ("GM2", False, "Files: a channel's moving filter (efxfilter: 59.2's plunger, a didgeridoo's mouth)"),
    ("GM2", True, "Files: the church bells (14.8-14.10: a tube's measured modes, 19 of them, a decay of their "
                  "own) and the feedback guitars (30.8, 31.8: the loop's partial and series as late copies)"),
    ("GM2", True, "Brass variations' blare (blare_db_per_khz: dB per kHz over a knee, renormalised) and the "
                  "SC-88's hammer-on (hammer_legato: the fretting hand, its strings and guitars)"),
    ("GM1", False, "Files: a sung part's text, vocalise and declared parts (TUNING_LYRIC_LANG, TUNING_VOCALISE, "
                   "TUNING_VOICE_PARTS)"),
    ("GM1", False, "Files: organs -- two on a channel, an organ beside a variation, swell laws of their own"),
    ("GM2", True, "Bank select in files (CC0/CC32): GM2's banks (120 drums, 121 melodic) and GS's variations, "
                  "layered ones too (nvrender; nvlive refuses a bank)"),
    ("GM2", False, "Bank select in nvlive: a file's banks (live._program's variation)"),
    ("GM2", False, "nvlive: a variation as a patch (Patch(program, drums, tuner, variation)); the picker's GM2 bank"),
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
    ("SC-55", False, "The GS map (CC32 / TONE MAP-0) and kit_in_map in the reader and nvlive"),
    ("SC-55", False, "GS's effects natively (gsefx: insertion EFX, the GS delay, chorus) -- the corpus has no "
                     "GS files, so each needs GS test files"),
    ("SC-55", False, "Files: GS's other exclusives -- part parameters (parse_gs_part), drum setup and the user "
                     "sets, the rhythm part's assignment, TONE MAP-0 (the reader refuses them, -4)"),
    ("SC-55", True, "Melodic SFX (patch_map.melodic_sfx): a kit's sound on a keyboard part, transposed whole "
                    "(transposed_from_hz: _XP), its kit key's strokes (sfx_strokes_of), the weather voices "
                    "(a measured mode set under the noise's roll-off, its breath beside it)"),
    ("SC-55", True, "SFX voices with a fixed vibrato of their own (skid, starship, scream: VoiceSnap.fv_*)"),
    ("SC-55", True, "The heartbeat: its ECG's mode phases, its blood flow's timed noise bands (noise_events)"),
    ("SC-55", True, "A drum's sounding octaves (the SFX sets' helicopter: its key a rotor, under its kit pitch)"),
    ("SC-55", False, "The siren's rotor (siren_rotor: its rows and live's siren block) -- GM 2's 125.5, the SFX "
                     "set's 67"),
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

    def kit_keys(prog, only=None):
        kit = PM.kit_for_program(prog)
        keys = [k for k in range(128) if PM.percussion_for_note(k, kit) and (only is None or k in only)]
        nat = [k for k in keys if prog < 128 and native_cls(kc[128 * prog + k])]
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
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
