/* nv.h -- the native engine's shared types: what a voice is as numbers
 * (VoiceSnap; VoiceInit, a class's constants for its constructor; VoiceNote,
 * what the note setup reads of it besides), a note's tone inputs (ToneIn),
 * CPython's random stream (PyRandom) -- for the C core (voice.c, tone.c)
 * and the C++ engine (engine.cpp) alike. Field order is native.py's ctypes'.
 */
#ifndef NV_H
#define NV_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NCOLS 50                /* blockrender.EMIT_COLS */
#define NV_TOO_SMALL (-2000000000)      /* nv_play: the row store was too small */

typedef struct {
    uint32_t mt[624];
    int i;
    int has_gauss;          /* random.gauss's cached second value (gauss_next) */
    double gauss_next;
} PyRandom;

typedef struct {
    /* the series (SynthProperties.series_volume) */
    double gain;
    int max_harmonic;
    int odd_only;
    int even_db_set;                /* even_harmonic_db is not None */
    double even_harmonic_db;
    double strike_point, strike_depth;
    int strike_fills;               /* strike_fills_with_force */
    double strike_fill_fraction, attack_volume, attack_dampening;
    double frequency_x, octave_position;
    /* the decay */
    double decay_db, harmonic_decay_db, harmonic_decay_dampening, decay_register_factor;
    /* the grand's hammer and board */
    double hammer_corner_hz, hammer_open_lo, hammer_open_slope, hammer_register_slope, hammer_order;
    double board_body_gain, board_body_hz, board_body_width, board_high_hz, board_high_order, board_low_hz;
    /* its strings */
    double string_gain[2], string_break_hz[2], string_crossfade_semitones;
    int soft_pedal_strings, soft_pedal_down;
    int n_detune;
    double note_detune_cents[4];
    int unison_beat_scatter;
    double unison_beat_hz[2];
    long long unison_key;
    double aftersound_level[3], aftersound_decay_ratio;
    /* chiff, bloom, vibrato */
    int chiff_span_set;
    double chiff_harmonic_span, chiff_harmonic_power;
    double bloom_seconds, bloom_center_hz, bloom_octaves, bloom_shape;
    double exp_vibrato_cents, solo_vibrato_spread, solo_vibrato_hz;
    long long section_salt;
    /* where it is heard */
    double radiation_distance, position_x, position_z, hrtf_beta;
    double room[10];                /* roomcore.c's R: directivity, speed, air */
    double ahz[6], alpha[36], scat[36];     /* ...its octave bands and surfaces */
    /* the phantom partials (the wound bass's sum-tones) */
    double phantom_coupling, phantom_register_power, phantom_ref_hz, phantom_note_max_hz, phantom_gain_floor;
    int phantom_max_order;
    /* the board (soundboard_gain): 0 the grand's, 1 the upright's, 2 the electric grand's bridge */
    int board_kind;
    double board_low_order, bridge_gain, bridge_corner_hz, bridge_order, bridge_force_power;
    /* WHOSE METHODS THE VOICE HAS: 0 the grand's (its hammer and board, its
       strings, its aftersound -- above); 1 a kit drum's (KitDrumProperties:
       its measured modes, its stick's click, its two-stage decay -- below),
       on SynthProperties' series volume and unison */
    int kind;
    double unison_gain;
    int n_unison;
    double unison_detune[8];
    /* KitDrumProperties: DRUM_MODES (ratio, dB under the first, amplitude dB/s);
       the click's CLICK_DB bands of click_per_band partials from CLICK_HZ0 */
    int n_modes;
    double modes[128][3];
    int n_click, click_per_band;
    double click_db[32];
    double click_hz0, click_cal_db, click_scatter, click_dbs, click_stroke_slope, stroke_ref_db;
    double slow_share, slow_dbs, slow_max_hz;       /* slow_max_hz 0: None */
    /* NoisyPercussionMixin: the partials' and the chiff's roll-off above
       hf_corner_hz, and the band trim ((Hz, dB), log-interpolated) */
    int noisy;
    double hf_corner_hz, hf_order;
    /* SampledBreak: nothing sounds at or above the sampler's moved Nyquist
       (0: no sampler) */
    double nyquist;
    int n_trim;
    double trim[32][2];
    /* AcousticSnareProperties: the head's two rates, the shell's remainder on
       the head modes alone, each partial's jitter (the wires', the head's);
       SideStickProperties: the rim's modes from rim_from (0 none) and rate */
    int snare;
    double fund_dbs, head_dbs, wire_jitter, head_jitter;
    int rim_from;
    double rim_dbs;
    /* kind 2 (a measured mode set on SynthProperties: modes[i] = (ratio,
       linear gain, -)): a key's decay retargeted (percussion_map's _nNN
       classes: the decay scaled so its first mode's is decay_target) */
    /* MeasuredStrokeProperties: the modes' ring (ring_scale), each mode's
       level scattered stroke by stroke (mode_scatter_db); which of the two
       jitters is the note's sustain_jitter (1 the head's, a snare's; 2 the
       rest's, a measured stroke's) */
    int measured;
    double ring_scale, mode_scatter_db;
    int jit_sus;
    int jit_from;       /* partial_jitter: the rest's from this harmonic (0: past the modes) */
    int tamb;           /* TambourineProperties: every jingle mode scattered alike, unclamped */
    int retarget;
    double decay_target;
    /* ...its modes: (ratio, linear gain); mm_harm, a gain table on the
       harmonic series (mode_ratios None: partial m at m) */
    int mm_harm;
    int n_mm;
    double mm_ratio[400], mm_gain[400];         /* (a TR-606 hat: 400) */
    /* CymbalProperties: decay by octaves from the ring's peak (ring_peak_hz
       0: SynthProperties'), the aftersound's share and rate */
    int cymbal;
    double ring_peak_hz, ring_decay_below, ring_decay_above, ring_decay_floor;
    double aftersound_fraction, aftersound_dbs, aftersound_ratio;
    /* the bloom's late copy: its gain (the stroke's, bloom_gain_slope), only
       in its band (bloom_banded), its swell, scatter and own fall */
    double bloom_gain;
    int bloom_banded;
    double bloom_swell, bloom_scatter, bloom_decay_dbs;
    /* SynthProperties' bore (bore_gain: a roll-off from bore_corner_hz, a
       bell's high-pass from bell_cutoff_hz), renormalised to the series'
       power (_bore_norm: the note's, the constructor's); a samba whistle's
       pea (SambaWhistleProperties: its comb as unison voices, its vibrato) */
    double bore_corner_hz, bore_order, bell_cutoff_hz, bell_order, bore_norm;
    /* BLARE (SynthProperties._blare): dB per kHz over blare_knee_hz, held at
       +-blare_cap_db, through the bore; renormalised to the bored series'
       power (_blare_norm). 0 dB per kHz: none */
    double blare_db_per_khz, blare_knee_hz, blare_cap_db, blare_norm;
    int pea;
    double pea_vibrato_cents, pea_vibrato_hz;
    /* TunedBarProperties: only the bar's own modes sound (bar_modes: the
       series' index, its gain) */
    int n_bar;
    int bar_n[16];
    double bar_g[16];
    /* ModeDecays: each mode's own decay (x decay_register_factor);
       TR808Properties: each mode's aftersound (share, its dB/s; aftersound_
       partial) and where it starts (mode_phase, radians) */
    int n_md, n_ma, n_mp;
    double mode_decays[400], mode_after[400][2], mode_phases[400];
    /* SfxThroatProperties: a pulse's tilt (dB at 4 kHz over 1 kHz), its
       mouth (the formants scaled) and its vowel moved toward DRUM_MODES_B
       (n_mb of (ratio, dB)) -- the note's, set after the voice is built;
       its breath (chiff_volume: breath_volume, tilted) */
    int throat, n_mb;
    double stroke_tilt_db, formant_scale, formant_morph, breath_volume;
    double mb[128][2];
    /* kind 4, A HARMONIC VOICE (a guitar: SynthProperties' series and the
       pluck's comb, comb[h], tonelib._pluck_comb's), its body a FormantBody
       (fbody): the floor, the formants and antiformants (centre Hz, width Hz,
       amplitude or depth), the body trim ((Hz, dB), log-interpolated) */
    int fbody, n_fm, n_afm, n_bt;
    double formant_floor, fm[16][3], afm[8][3], bt[32][2];
    double comb[257];
    /* A SECTION (SectionMixin, on a kind 4 voice: the bowed strings): sect_n
       players, each a few cents off its neighbours (unison_voices), with a
       vibrato of its own (voice_vibrato, sect_vib) and its own entry
       (section_onset, the extras' capped at sect_ofm of the note); seated
       (sect_seats) sect_dx[i] metres from the voice's place
       (section_position_x) */
    int sect_n, sect_vib, sect_seats;
    double sect_spread_cents, sect_vib_cents, sect_vib_hz[2], sect_onset_ms, sect_ofm, sect_dx[16];
    /* AN ORGAN PIPE'S REGISTER (a kind 2 mode set by pitch: mode_gains_at):
       measured tables at anchor pitches (n_pts of pts_hz, pts_g, n_ptg
       gains each), blended in dB along log frequency; or a low register's
       table (low_set: mode_gains_low, low_g) blended in under register_low_hz.
       mm_gain the note's (mode_gains_here) */
    int n_pts, n_ptg, low_set, n_low, pts_n[8];
    double pts_hz[8], pts_g[8][64], low_g[64], low_hz[2], pipe_g[64];
    int n_pipe;
    /* A FREE REED (FreeReedProperties' flow spectrum, on a kind 4 voice: the
       accordions', the harmonica's): its geometry (gate, edge, spread over
       reed_points gate positions, the leak), the gate's and spread's laws by
       octave, the harmonics' scatter and its law (the harmonica's); the
       note's series (reed_s, n_reed of them: native/reed.cpp's); the reed
       banks (an accordion's unison: each's gain, cents and their law by
       octave, its ratio) */
    int reed, reed_points, n_reed, n_bank;
    double reed_gate, reed_edge, reed_spread, reed_direct, reed_gate_oct, reed_spread_oct, reed_scatter,
        reed_scatter_oct;
    double reed_s[1025];                /* (a bandoneon's low key: 12 kHz of harmonics) */
    double bank_g[4], bank_cents[4], bank_oct[4], bank_ratio[4];
    /* ITS UPPER HARMONICS SPEAK LATE (speech_harmonic_exp: harmonic m's attack
       m^-exp of the note's, the exponent's law by octave from 415 Hz, never
       past 0, counted to sh_cap; 0 none) */
    double sh_exp, sh_exp_oct;
    int sh_cap;
    /* A PLAYED REED'S WIND SKIRT (wind_skirt_always: the harmonica's): a noise
       band on each of its first sk_max partials, sk_db under it rising
       sk_hdb a harmonic octave, as wide as the wider of sk_hz and sk_rel of
       its frequency; no images */
    int skirt, sk_max;
    double sk_db, sk_hdb, sk_hz, sk_rel;
    /* AN ELECTRIC PIANO (kind 5: ElectricPianoProperties): its pickup's curve
       (ep_kind 1 the Rhodes', 2 the Wurlitzer's slot; ep_p its parameters),
       the swing (pickup_deflection, its register slope, velocity power and
       ceiling; swing_damping), the fit (pickup_harmonics, _layer_terms,
       _max_hz, _floor_db), level_swing_share; the tonebar (its pitch law,
       modes, gains and decay) -- and the note's: its swing (ep_a0), its
       layers (n_lay: each a mode at ep_r, its term's power ep_n and weight
       ep_w; the tonebar's modes after them, at ep_r too) */
    int ep_kind, ep_harm, ep_terms, n_tb, n_lay;
    double ep_p[5], ep_defl, ep_defl_slope, ep_defl_power, ep_defl_max, ep_rho, ep_max_hz, ep_floor_db, ep_share;
    double tb_coeff, tb_power, tb_decay, tb_ratio[8], tb_g[8];
    double ep_a0, ep_r[408], ep_n[400], ep_w[400];
    /* AN ELECTRIC GUITAR'S STRING AND MAGNET (elec, on a kind 4 voice:
       ElectricGuitarProperties): the pick's comb (at eg_sp, notched eg_depth
       at every force: a plectrum), the coils (n_pk at pk_q0, each its sign
       pk_sign, wound pk_turns, pk_width wide, read as velocity pk_vel, loaded
       by a two-pole at pk_res_hz of Q pk_qf; a dark string's low-pass lp_hz
       of lp_order: pickup_gain), and the open strings a note is fretted from
       (n_os of os_hz, to fret_max) -- the note's pick and coils pk_sp, pk_q;
       A TOUCHED HARMONIC's (GuitarHarmonicsProperties): the touches a
       player chooses among (n_touch of touches; 0: the class's touch0), the
       note's touch, and the killed modes' leak (leak_set: touch_leak_db not
       None) at leak_db, dying leak_dbs */
    int elec, n_pk, pk_vel, n_os;
    double eg_sp, eg_depth, pk_q0[4], pk_sign[4], pk_turns, pk_width, pk_res_hz, pk_qf, lp_hz, lp_order, os_hz[8],
        fret_max, pk_sp, pk_q[4];
    int n_touch, touches[4], touch0, touch, leak_set;
    double leak_db, leak_dbs;
    /* A PIPE'S MODE LOCK (mode_lock_*: a played pipe's, a reed's, a brass
       instrument's): each harmonic above the first starting sharp by
       ml_spread x/(1+x), x = (m/ml_knee)^2, pulled into lock over ml_time
       (the partial's tension-bend triple) */
    double ml_spread, ml_knee, ml_time;
    /* A MUTE IN THE BELL (MutedTrumpetProperties.bore_gain): muted minus
       open, n_mute (Hz, dB) log-interpolated, held flat past its ends */
    int n_mute;
    double mute[24][2];
    /* A CHIME'S TUBE (TubularBellProperties): n_tube modes, each (ratio, its
       slope, dB, its slope) a line in the note's octaves from tube_ref_hz,
       held at -0.6 and 0.85 (_tube_oct); their decays are mode_decays */
    int n_tube;
    double tube_ref_hz, tube[32][4];
    /* A COMB TOOTH'S OCTAVE BELOW (MusicBoxProperties.mode_gains_here): mode
       7 sounds on a key random.Random(key 7919 + 10) chooses -- its draw
       under or_share, an octave under the key not below or_lowest_hz -- at
       a level drawn between or_db; the note's (or_g) set by nv_voice_init */
    int or_set;
    double or_share, or_db[2], or_lowest_hz, or_g;
    /* A DULCIMER'S COURSE (HammeredDulcimerProperties): its other dul_n
       strings, each beating dul_beat Hz (a draw by key, string and
       harmonic) at unison_gain, ringing as the harmonic does; each mode's
       decay by its own frequency (dhz_set: 0.5 (decay_db + dhz_db
       (f/1000)^dhz_pow)) */
    int dul_n, dhz_set;
    double dul_beat[2], dhz_db, dhz_pow;
    /* EACH PARTIAL ITS OWN PHASE (partial_phase_spread: pps of a turn, from
       ToneIn.pps_seed's random.Random), a course's unisons its phase
       (unison_shares_phase) */
    double pps;
    int ushare;
    /* A STROKE's TILT ON MEASURED MODES (mode_stroke_tilt: the timpani's):
       dB per octave of mode ratio per dB of stroke, about mst_ref */
    double mst, mst_ref;
    /* A CLAVINET (ClavinetProperties.__init__, on the electric path): its
       coil a fraction of the note's speaking length (ref_m (ref_hz/f0)^pow),
       at bridge_m or between c0 and c1 by key, capped at qmax; sel 0
       centre, 1 bridge, 2 both, 3 both in anti-phase. Its key-up's modes
       (release_click_modes): the thumps, falling tdb a semitone over key
       46, then the string's harmonics kh at ka -- the note's in vk_* */
    int clav, cl_sel, cl_nt, cl_nk;
    double cl_ref_m, cl_ref_hz, cl_pow, cl_bridge, cl_c0, cl_c1, cl_qmax, cl_tdb;
    double cl_thump[8], cl_kh[8], cl_ka[8];
    int vk_n;
    double vk_hz[16], vk_amp[16];
    /* AN ORCHESTRA HIT's SECTION (OrchestraHitProperties.unison_voices): its
       players a few cents each way (hit_cents, hit_n of them) at hit_gain */
    int hit_n;
    double hit_cents[8], hit_gain;
    /* A TWO-STAGE DECAY (PromptDecay): every partial under pd_max_hz falls
       at pd_dbs at first, pd_share of it ringing on at the law; 0 none */
    double pd_max_hz, pd_dbs, pd_share;
    /* PLAYED AT PITCH (PlayedAtPitchMixin._band_trim): the trim read at
       pap_hz (RECORDED_HZ) x each of its first pap_n modes' ratio; 0 none */
    double pap_hz;
    int pap_n;
    /* A STRUCK VOICE REPEATED (tap_kind 1 a bird's chirps, 2 a telephone's
       clapper): its taps (s), each voice's gain, a stroke's offset sd and
       level range (dB, the clapper's), each mode's gong (A 0, B 1), whether
       a stroke past the note's end is dropped; the cap on an entry is sect_ofm */
    int tap_kind, n_tap, n_gong, tap_drop;
    double tap_t[192], tap_gain, tap_jit, tap_ldb;
    int gong[16];
    /* A MEASURED SERIES (HelicopterProperties.harmonic_volume): gain x
       hvt[h - 1], nothing past n_hvt; 0 none */
    int n_hvt;
    double hvt[512];
    /* THE WASH WHERE THE BODY IS (GuitarFretNoiseProperties.chiff_harmonic_gain:
       the body's gain at the harmonic x the roll-off, in place of the chiff's) */
    int chiff_bore;
    /* A FIXED VIBRATO of its own (the skid's, starship's, scream's
       voice_vibrato): its depth's cents (x 1.4142) and rate; fv_set 0 none */
    int fv_set;
    double fv_cents, fv_hz;
    /* A PICK (Plectrum): every partial over pick_hz pick_slope_db an octave
       louder (to pick_boost_max_db), the extra falling at pick_dbs, the rest
       ringing on; a doubled course crossed pick_stagger s apart (0 none) */
    int pick_set;
    double pick_hz, pick_slope_db, pick_boost_max_db, pick_dbs, pick_stagger;
    /* ITS COURSES' PARTNERS (unison_voices): crs_kind 1 a unison partner on
       every harmonic (the mandolin's), 2 the 12-string's -- an octave partner
       on the even harmonics under crs_split, a unison one from it */
    int crs_kind;
    double crs_split, crs_oct_gain, crs_oct_cents, crs_uni_gain, crs_uni_cents;
    /* A CHURCH BELL's decay (ChurchBellProperties.harmonic_decay): each tube
       mode's mode_decays / 2, by church_slope an octave from tube_ref_hz */
    int church;
    double church_slope;
    /* FEEDBACK (Feedback): the loop's harmonic (fb_fixed, else the one
       nearest fb_band_hz), its series (fbs: multiple, gain) late copies
       fb_delay s after the pluck, swelling over fb_swell s, sinking fb_dbs */
    int fb_set, fb_fixed, n_fbs;
    double fb_band_hz, fb_delay, fb_swell, fb_gain, fb_dbs, fbs[8][2];
    /* A STRING'S WANDER (the ukulele's voice_vibrato): each voice's depth up
       to sw_cents, rate in sw_hz, phase drawn by the key; sw_set 0 none */
    int sw_set;
    double sw_cents, sw_hz[2];
} VoiceSnap;

/* AN ORGAN PIPE (a class an organ's ranks draw on: the host, a borrowed
   spectrum, a named pipe): its voice's constructor and template, and what
   its speech, chiff, ceiling and push are */
typedef struct OrganPipe OrganPipe;
/* AN ORGAN RANK (one of stop_ranks): its footage (or a mixture's), level,
   spectrum and pipe (OrganPipe indices, -1: the host's), its key range, its
   place in the case (rank_spatial), a mixture's compositions by pitch, and
   its speech class's release, band by band, at every key */
typedef struct {
    int n_ratio, compound;
    double ratio[8], gain;
    int spec, pipe, lo, hi;
    double sp_off, sp_split;
    int n_comp, comp_n[64];
    double comp_hz[64], comp_r[64][8];
    double rel_band[128][3];
    /* a reed organ's: the rank's own mistuning at every key (rank_detune_cents,
       0 none), and whether the Percussion stop strikes it (percussion_ranks) */
    double detune[128];
    int perc;
    /* A HAMMOND'S: when this drawbar's contact closes at every key
       (contact_offset_s), its name's length (the leak's seed), whether it is
       nothing until its channel draws it (rank_only_when_drawn: a percussion
       tap), and whether the leak skips it (a rank with a class of its own) */
    double contact[128];
    int keylen, only_drawn, no_leak;
    /* A HARPSICHORD'S: the choir it plucks (rank_choirs, a buffed string as
       its string: choir_of), its wire's stiffness at every key against choir
       A's (choir_stiffness), and whether its partials scatter (choir_beat_hz:
       not on choir A) -- each (choir, key, partial)'s own Hz, choir_partial_hz */
    double stiff[128];
    char choir[16];
    int beat;
    char key[64];           /* its stop's name (a jack's click's phase is drawn by it) */
} OrganRank;

typedef struct {
    double tonal_dampening, octave_dampening;
    int octave_modulo;
    double octave_width, seat_x, decay_register_slope;
    double pitch_jitter_cents, timing_jitter_seconds;
    double tension_bend, tension_bend_max, tension_bend_ref_hz, tension_bend_slope;
    int inharmonicity_dynamic;
    double inharmonicity_coefficient, ia, ib, ic, id, ie;   /* a + b x + c x^2 + d/x + e/x^2 */
    double effort, effort_tilt, effort_tilt_up;
    int effort_tilt_up_set;
    int even_db_set;
    double even_harmonic_db, even_harmonic_db_per_octave;
    int touch_sensitive, fixed_touch;
    double initial_gain, octave_gain, projection_db;
    double register_effort_db, register_tilt_db, register_center_hz, register_half_octaves;
    double listener_distance, head_radius, position_z, sound_speed;
    double max_partial_hz;          /* 0: none */
    double bloom_seconds, bloom_slope, bloom_stretch_max;
    double detune_lo, detune_hi;    /* string_detune_range (the honky-tonk's scaled) */
    int key_jitter;                 /* the grand's per-key pitch error (GrandPianoProperties) */
    int soft_pedal_down;
    /* the B law: 0 the polynomial; 1 the upright's (k f^p, wound under
       break_hz, plain over); 2 the electric grand's (the polynomial times
       (long/short)^4 of its strings) */
    int b_law;
    double wound_k, wound_p, plain_k, plain_p, break_hz;
    double scale_constant_hz_m, reference_string_max_m, case_string_max_m;
    /* the upright's (UprightPianoProperties.__init__): the hammer's contact
       from the velocity, and the level across the keyboard (Hz, dB) */
    int upright, n_level;
    double attack_time, hammer_soft_s, hammer_hard_s;
    double level_hz[32], level_db[32];
    /* 0 a grand's constructor (the key's strings and pitch error, the B law
       above); 1 a kit drum's (SynthProperties' alone: B the class's own);
       2 a measured mode set's (SynthProperties' alone too: the clap); 3 a
       harmonic series' on SynthProperties (a shaker's) */
    int kind;
    double bloom_gain, bloom_gain_slope;
    /* the stroke's chiff and jitter (chiff_volume, sustain_jitter scaled by
       attack_volume ** strike_noise_slope), and the volume trimmed back on
       the square law ((velocity, dB), ascending: strike_volume_trim_db) */
    double chiff_volume, sustain_jitter, strike_noise_slope;
    int n_vtrim;
    double vtrim_v[16], vtrim_db[16];
    /* the strike's wobble: a unison voice strike_wobble_hz off, its gain the stroke's */
    double strike_wobble_hz, strike_wobble_gain, strike_wobble_slope;
    /* [RND] (tonelib.RandomStrike): each strike varied by its own stream's
       four draws -- level dB, effort dB, cents, seconds late -- in
       rnd_draws, the note's (its sds the class's, the caller draws) */
    int rnd;
    double rnd_level_db, rnd_effort_db, rnd_cents, rnd_timing_s;
    double rnd_draws[4];
    /* b_law 3 (a kind 4 voice's: SteelGuitarProperties' inharmonicity_law),
       B = law_k f^law_p */
    double law_k, law_p;
    /* b_law 4 (HammeredDulcimerProperties'): bb_B under the bass bridge's
       bb_hz, law_k f^law_p over it */
    double bb_hz, bb_B;
    /* A BANK OF COURSES (course_keys: the dulcimer's): the register's
       strings only at the keys with course[key] set, has_course; else all */
    int has_course;
    unsigned char course[128];
    /* A STOPPED STRING's PLUCK (stopped_pluck_point: the pizzicato's, the
       upright's): the open strings' keys, the open-string point -- the
       note's strike point from them; n_open 0: the template's */
    int n_open;
    double open_st[8], pluck_open;
    /* A SUNG VOICE's BODY (tonelib._VocalBody): the class's own vowel (vb_fm,
       n_vb) and the draw between a male and a female tract -- the note's
       formants _sung_formants' at sung_hz (its part's tessitura: the median
       key of its channel), or a declared part's (part_set: its tract ratio
       and singer's-formant cluster); vbody 0 none */
    int vbody, n_vb;
    double vb_fm[16][3];
    double vb_tract, vb_sigma, vb_mb, vb_xhz, vb_xoct, vb_ftop, vb_sfhz;
    int part_set;
    double part_ratio, part_cluster, sung_hz;
} VoiceInit;

struct OrganPipe {
    VoiceInit init;
    VoiceSnap tmpl;
    int attack_set, release_set, chiff_width_set, sh_cap, rank_is_pipe, rank_speech, truncate;
    double attack_time, release_valve_time, chiff_max_valve_time, speech_cycles, chiff_width, chiff_width_cycles;
    double chiff_volume, chiff_cycle, sustain_level, speech_harmonic_exp, speech_harmonic_exp_per_octave;
    double pipe_ceiling_hz;
    /* the bellows' push (bellows_push_*): its gain, rise, fall and settle,
       its band (band_set: centre harmonic, octaves) or tilt, its register */
    int push_band_set, n_push_reg;
    double push_gain, push_rise_s, push_dbs, push_settle_db, push_tilt, push_tilt_oct, push_band[2];
    double push_reg[8][2];
    /* THE QUILL'S CATCH (HarpsiBase.pre_pluck_s): how long it holds the
       string by pitch (n_pp of pp_hz, pp_s, log-interpolated), the partials
       moving meanwhile (pp_partials) at pp_db, the slip's snap pp_snap_s */
    int n_pp, pp_partials;
    double pp_hz[8], pp_s[8], pp_db, pp_snap_s;
};

/* A REGISTERED ORGAN: its pipes (pipe[0] the host's own), its ranks, the
   case's spiral (rank_position_x), the pipes' scale (pipe_radius), the mode
   lock (mode_lock_*), and whether each rank speaks at its own pitch */
typedef struct OrganSpec {
    int n_pipe, n_rank, spiral, own_pitch;
    OrganPipe pipe[24];
    OrganRank rank[32];
    double spiral_m, spiral_phase, drift_m, spatial_default[2];
    double pipe_scale_divisor, sound_speed, mode_lock_spread, mode_lock_knee, mode_lock_time;
    /* ITS REGISTRATION (registration_blocks): the stop word's controllers
       (wccs; the first 11 for an organ whose CC7 is its swell: swells), its
       default, the crescendo's order (rank indices), the swell's law
       (floor, power, hf_max, hf_ref); its family (organ_family's id) */
    int n_wccs, wccs[4], default_stops, n_order, order[32], swells, family;
    double swell_law[4];
    /* ITS CHEST'S WIND (wind.py, its constants as the Python's Wind made
       them for the export's block): a pipe organ's (wind), its scale (wsc),
       the Tremulant's rank (-1 none) and the class's depth; the wander, the
       sag and the regulator (has_ra), the Tremulant's beat; the pipes' draw;
       each rank's family's pitch and level exponents */
    int wind, trem_rank, has_ra;
    double wsc, trem_class_depth, wander_rms, wa, wgain, ra, reg_restore, sag_max, sag_per_unit, c1, c2, g;
    double trem_hz, trem_depth, tdecay, unit_hz, draw_exp, blk_s;
    double fam_a[32], fam_b[32];
    /* A REED ORGAN'S EFFECT STOPS (the harmonium's): its Expression,
       Percussion and Tremolo stops' ranks (-1 none), the Expression's tilt,
       the hammer's attack and the attack's share of the note (attack_fraction_max) */
    int expr_rank, perc_rank, htrem_rank;
    double expr_tilt, perc_attack_s, afm;
    int pipe_radius;        /* each pipe's own aperture (pipe_radius); 0: the class's (a reed organ's) */
    double wheel_trem;      /* the wheel's tremolo depth (tremolo_depth), 0 none */
    /* live's tremolos: the wheel's rate and stereo (tremolo_hz, tremolo_stereo),
       the Tremolo stop's depth and rate (stop_tremolo_depth, stop_tremolo_hz) */
    double wtrem_hz, htrem_depth, htrem_hz;
    int wtrem_stereo;
    double wtrem_scatter;   /* a section's (tremolo_scatter), 0 none */
    /* the sound controllers it answers (tonelib.sound_controls_of): bit 0
       attack (CC73), 1 release (CC72), 2 decay (CC75) */
    int snd_mask;
    /* A TONEWHEEL'S CONTACTS (tonelib.TonewheelProperties): each drawbar's
       bounce, a noise burst a band (contact_noise_db: Hz, dB under its
       drawbar's fundamental) falling at contact_noise_dbs; the other drawbars'
       wheels leaking through each drawn contact (drawbar_leak_db, leak 0
       none); each partial its own phase (partial_phase_spread, 0 none) */
    int n_cn, leak;
    double cn_hz[16], cn_db[16], cn_dbs, leak_db, phase_spread;
    int contact_on;         /* its contacts close at their own instants (contact_spread_s): live's t["cof"] */
    double beat_lo, beat_hi;    /* a harpsichord's choirs' partials' scatter (choir_beat_hz), Hz */
    /* ITS CHOIRS (string_choirs: n_choir 0 none), as the register's string
       bank has them: each its pipe (the class its strings are, -1 the
       host's), footage, bridge (choir_bridge), the name its partials scatter
       by (a buffed choir's plain one: choir_bname, choir_beat 0 none), its
       cents and wire at every key (choir_cents, choir_stiffness); the
       bridges' cross coupling, the buffs (buffed, plain), each rank's choir */
    int n_choir, choir_pipe[8], choir_bridge[8], choir_beat[8], n_buff, buff[8][2], rank_choir[32];
    double choir_ratio[8], cross, choir_cents[8][128], choir_stiff[8][128];
    char choir_bname[8][16];
} OrganSpec;

/* what the note setup reads of the voice besides its VoiceSnap */
typedef struct {
    double pitch_jitter, attack_jitter, pan_angle;
    double left_incidence, right_incidence, left_hrtf_delay, right_hrtf_delay;
    double inharmonicity_coefficient, B;    /* the class's scaled; and the law's at the note */
    double tension_bend, attack_time;
    double chiff_volume, sustain_jitter;    /* the note's: the stroke's (strike_noise_slope) */
} VoiceNote;

typedef struct {
    /* the note */
    double f0, B, gain, non, noff, fade, rel, chiff, cv, cc, crl, sjit, csc;
    double li, ri, sustain_level;
    double gr, cr;
    double sr;
    /* the emitter's state for the note */
    double jitter_scale, nyq_om;
    int transposed, reflect;
    double dl, dr, pos_x0, pos_x_props, pos_z, channel;
    double cbw0, cbw1, tb[3], gl[3], sv[2], sound_vib_depth_cents, vibrato_delay;
    double br, fx, mk, fm_omega, fm_phase;
    /* the head, for each image's ears (hrtf_at) */
    double listener_distance, head_radius, pan_angle;
    double room_bands[9];
    /* each partial its own jitter (jitter_by_partial: nv_partial_jitter);
       each its strike's sign, pi * a random bit * sps (strike_phase_spread) */
    int pjit;
    double sps;
    double dur;         /* the note's length, s: the bloom's swell is held within it */
    int ssc;            /* each mode's level scattered (stroke_scatter: random.gauss) */
    /* a tape played backwards (played_backwards): every row reversed, from
       the strike at rev_n0 to its arrival at rev_arr (_Emitter.reverse) */
    int rev;
    double rev_n0, rev_arr;
    /* the room's walls (nv_images' planes) and its order: a section's
       players' images, each from its own desk */
    double planes[6];
    int order;
    /* the partial's radiating aperture (an organ pipe's: pipe_radius), when
       has_radius; else the class's directivity_radius */
    double radius;
    int has_radius;
    long long pps_seed;     /* the note's partials' phases (VoiceSnap.pps): random.Random(pps_seed) */
    /* ITS DISTANCE as a multiple of its voice's own (_src_dist: its
       channel's CC91 over GM's 40; 0 or 1 where it stands): the source moved
       out along its ray, its images from there */
    double dist;
    long long cls;          /* its class (the NoteClass), keying _refl_norm's memo as type(props) does */
    double hammer_on;       /* a hammer-on's seconds since the pick (em.hammer_on), 0 none */
    double gs_eq[4];        /* the file's GS EQ on its part (gs_eq_gain), [0] 0 none */
    /* A FILE'S INSERTION EFFECT's compressor (gsefx.chain's comp): its decay
       factor, its makeup and its attack (s); [0] 0 none */
    double fx_comp[3];
} ToneIn;

/* A MOOG MESSENGER's panel as a note reads it (moog.py; native.moog_spec):
   its knobs worked out at the class -- the waveshapes' coefficients, the
   filter's fixed row, the knob row -- so a note has only its key to add */
typedef struct {
    double t, foot1, foot2, o2f;            /* TUNE's ratio, the OCTAVE switches, OSC 2 FREQ's ratio */
    double lvl[4];                          /* OSC 1, OSC 2, SUB, NOISE levels */
    double c1[64][2], c2[64][2], cs[32][2]; /* c_k of OSC 1, OSC 2 and the SUB (osc_spectrum, sub_spectrum) */
    int n_noise;                            /* the noise bank (NOISE_HZ, NOISE_AMP) */
    double noise_hz[32], noise_amp[32];
    /* the ladder's own sine (self_amp, self_hz): its level, CUTOFF's corner,
       2^(the contour's sustained octaves), KB TRACKING */
    double self_amp, self_cut, self_eg, kb_track;
    double fm_index, fm_r1, fm_ph;          /* 1 -> 2 FM: its index, OSC 1's ratio, its fundamental's phase */
    double ft[30];                          /* moog.ft_row (slots 0, 9 and 10 the note's) */
    double kn[9];                           /* moog.kn_row */
    double rel_span;                        /* release_span, s */
    double fmax_hz, kb_ref_hz, noise_bw;    /* FMAX_HZ, KB_REF_HZ, NOISE_BW */
    /* THE MOD SECTION: OSC 2's pitch moving (pitch_params, 9) and the shapes
       moving (shape_flags' bits, shape_params, 25) -- 0 none; their rows the
       renderer's (synthkernel.c moog_pitch_cells, moog_shape_rows) */
    int pitch_on, shape_on;
    double pitch_p[9], shape_par[25];
    /* GM's SOUND CONTROLLERS on its knobs (moog.apply_gm): CUTOFF, RESONANCE,
       AMP ATTACK, RELEASE, DECAY as the panel has them, each one's span
       (GM_SOUND's order), and the laws that read them -- knob_tau's table
       (_EG_V, _EG_LOG), _ATK_TO_1, knob_cutoff's CUT_LO_HZ and CUT_OCT,
       knob_k's K_MAX and RES_PER_UNIT, self_amp's SELF_FROM and SELF_AMP,
       EG_UNDER */
    double knob[5], span[5], eg_v[11], eg_log[11];
    double atk_to_1, cut_lo, cut_oct, k_max, res_per_unit, self_from, self_amp_max, eg_under;
    int body;                               /* through the voice's formant body (moog_body: bore x norm) */
    /* A VALVE AFTER THE LADDER (amp_drive): the partials carry the ladder at
       its sustain (sustain_gain, ladder_gain_1's modes: BP_GAIN, BP_CORNER,
       HP_GAIN, HP_CORNER, HP_LEAK) */
    int pre;
    double bp_gain, bp_corner, hp_gain, hp_corner, hp_leak;
    /* THE MF-104M after it (mf104.settings; mf_on 0 none): TIME (s), the
       line's filter corner, FEEDBACK, wet, dry, LFO RATE, AMOUNT -- and
       mf104's GRID, MAX_REPEATS, REPEAT_FLOOR, FILTER_POLES */
    int mf_on;
    double mf[7], mf_grid, mf_max, mf_floor, mf_poles;
    /* THE UNISON (moog.unison, the class's moog_unison; u_n 1 none): its
       voices, the outermost's detune, a side voice's level, each one's
       drift (cents, its rate's range Hz) and the stereo width -- each note
       draws its voices from its key (moog.unison's seed). SYNC needs none of
       its own: OSC 2 is on OSC 1's harmonics (foot2 = foot1, o2f 1), its
       coefficients the synced spectrum's (moog.sync_spectrum) */
    int u_n;
    double u_cents, u_mix, u_dc, u_dhz[2], u_width;
} MoogLayer;

typedef struct {
    int n_layer;                            /* 1, or 2 a layered voice (moog.layers_of) */
    MoogLayer L[2];
} MoogSpec;

/* tone.c: a Moog layer's panel with GM's sound controllers on it (d: CC71-78's
   offsets, the class's own among them): the knob row, the amp contour's
   times, the ladder's own sine and the release, from the knobs they move */
void nv_moog_apply(const MoogLayer *in, const double *d, MoogLayer *out);

/* tone.c: a Moog layer's partials (blockrender._note_moog): its rows, the
   note's filter row fx and its release (samples) on them */
void nv_set_moog_neutral(int on);
double nv_moog_ladder_gain(const MoogLayer *L, double f, double fc, double k, int mode, int rb);
int nv_moog_neutral(void);
int nv_moog_neutral_tone(const VoiceSnap *v, const ToneIn *t0, const MoogLayer *L, double fx, double mre, int nimg,
                         const int *nsurf, const int *surf, const double *img, const double *mir, double *rows,
                         int cap, double *qacc, double *azimuth);
int nv_moog_tone(const VoiceSnap *v, const ToneIn *t, const MoogLayer *L, double fx, double mre, int nimg,
                 const int *nsurf, const int *surf, const double *img, const double *mir, double *rows, int cap,
                 double *qacc, double *azimuth);

/* the voice's gain scaled after it is built (props.gain *= k), what was
   read from it made again (the bore's norm) */
void nv_voice_regain(const VoiceInit *c, VoiceSnap *s, double k);
void nv_voice_init(const VoiceInit *c, const VoiceSnap *tmpl, double frequency, double channel_pan,
                   double attack_volume, double channel_volume, double effort, PyRandom *rs,
                   VoiceSnap *s, VoiceNote *o);
int nv_tone_rs(const VoiceSnap *v, const ToneIn *t,
               int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
               double *rows, int cap, double *transverse, int *ntrans, double *qacc, double *azimuth,
               PyRandom *rs, double *sjit_last);
int nv_shake(const VoiceSnap *v, const ToneIn *t, int nb, const double *hz, const double *db, int k,
             double held, double shake_min_s, double shake_frac, double shake_xfade_s, double rise_s,
             double settle_db, double settle_s, double pos_x, double *rows, int cap, double *qacc,
             double *azimuth);
int nv_strike_bal(const VoiceSnap *v, const ToneIn *t, int nb, const double *hz, const double *db,
                  double reg, double bdb, double scal, double slr, double sfade, double slen, double bon,
                  double pos_x, double bgl, double bgr, double *rows, int cap, double *qacc, double *azimuth);
int nv_layer(const VoiceSnap *v, const ToneIn *t, int nb, const double *hz, const double *db, double reg,
             double fade, double slr, double len, double pos_x, double *rows, int cap, double *qacc, double *azimuth);
int nv_pulse(const VoiceSnap *v, const ToneIn *t, double f0, double blk, double lo_ms, double hi_ms, double peak,
             double fmax, double taper, double pos_x, int nimg, const int *nsurf, const int *surf, const double *img,
             const double *mir, double *rows, int cap, double *qacc, double *azimuth);
int nv_events(const VoiceSnap *v, const ToneIn *t, int ne, const double (*ev)[4], int k, double ramp,
              double pos_x, double *rows, int cap, double *qacc, double *azimuth);
int nv_palm(const VoiceSnap *v, const ToneIn *t, double hz, double db, double plr, double bon, double slen,
            double sfade, double gl, double gr, double pos_x, double *rows, int cap, double *qacc, double *azimuth);
int nv_grains(const VoiceSnap *v, const ToneIn *t, int ng, const double (*g)[9], long long seed, double settle,
              double pos_x, double *rows, int cap, double *qacc, double *azimuth);
int nv_breath(const VoiceSnap *v, const ToneIn *t, int nb, const double *hz, const double *db, int k, double fade,
              double pos_x, double *rows, int cap, double *qacc, double *azimuth);
int nv_tone(const VoiceSnap *v, const ToneIn *t,
            int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
            double *rows, int cap, double *transverse, int *ntrans, double *qacc, double *azimuth);
int nv_strike(const VoiceSnap *v, const ToneIn *t, int nb, const double *hz, const double *db,
              double reg, double bdb, double scal, double slr, double sfade, double slen, double bon,
              double pos_x, double *rows, int cap, double *qacc, double *azimuth);
int nv_phantom(const VoiceSnap *v, const ToneIn *t, const double *trans, int ntrans,
               int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
               double *rows, int cap, double *qacc, double *azimuth);
/* tone.c: the other strings (blockrender._note_ring) -- n rows at hz
   (tuned), db, dps; those on f0's own modes (within skip) left out; phases
   from rr; dr 0.9 direct, 0.1 an image */
int nv_ring(const VoiceSnap *v, const ToneIn *t, double f0, int n, const double *hz, const double *db,
            const double *dps, double skip, int nown, const double *own_r, PyRandom *rr, int nimg,
            const int *nsurf, const int *surf, const double *img, const double *mir, double *rows, int cap,
            double *qacc, double *azimuth);
int nv_leak(const VoiceSnap *v, const ToneIn *t, double Bs, PyRandom *lr, int nimg, const int *nsurf,
            const int *surf, const double *img, const double *mir, double *rows, int cap, double *qacc,
            double *azimuth);

// What a voice class is to a note's setup: the constructor's constants and
// the class's VoiceSnap, the attack/release/chiff laws, the tension bend and
// the hammer's knock (strike_noise_db). "_set" flags carry Python's None.
typedef struct NoteClass {
    VoiceInit init;
    VoiceSnap tmpl;
    double chiff_max_valve_time;
    int release_valve_set;
    double release_valve_time;
    double speech_cycles;
    int legato_set;
    double legato_attack_s;
    double attack_fraction_max;
    int release_fraction_set;
    double release_fraction_max;
    int slur_cuts_release;
    int chiff_width_set;
    double chiff_width, chiff_width_cycles;
    double chiff_volume, chiff_cycle, chiff_release, sustain_jitter;
    double cbw0, cbw1;                  // chiff_bandwidth or RAND_GRAN, chiff_bandwidth_hz or 0
    double tension_bend_power;
    int tension_bend_slurs;
    double tension_settle_time, tension_settle_cutoff;
    int tension_log;
    double tbend_cut_scale;
    double sustain_level;
    int reflection_order;
    int n_strike;                       // the knock's bands (0: none)
    double strike_hz[32], strike_db[32];
    double strike_noise_dbs;
    int strike_span_set;
    double strike_span_lo, strike_span_hi;
    double strike_octave_db;            // strike_noise_octave_db, else strike_noise_slope
    double strike_fade_s, strike_len_s, strike_at_s, strike_cal_db;
    // the room it plays in (WALLS' signed planes, its reflection order), its
    // dampers, its strings' detune range and whether CC1 scales it (detune_wheel)
    double room_planes[6];
    int room_order, damper_pedal;
    double detune_lo, detune_hi;
    int detune_wheel;
    // its free-string register (register.Channel): register_gain and
    // register_knock_gain (times the render's scale), the knock's fall a
    // semitone, damper_top, the floor (floor_of), the release (s)
    double reg_gain, reg_knock, reg_fall;
    int damper_top;
    double reg_floor, reg_release;
    // ...BY KEY (a dulcimer's, reg_keyed): each key's bridge (key_bridge;
    // -1 none), the coupling across them (cross_bridge_coupling), each key's
    // partner past the treble bridge (bridge_partner, -1 none) at
    // reg_partner_k; the knock by its measured profile (reg_nkp (semitones,
    // dB) from the struck key) and its tilt by each mode's frequency
    int reg_keyed;
    int reg_kb[128], reg_partner[128];
    double reg_cross, reg_partner_k, reg_ktilt;
    int reg_nkp;
    double reg_kp_x[64], reg_kp_db[64];
    // a one-shot (a kit drum): its note held to at least one_shot_hold past
    // its onset, the key-up ignored (ONE_SHOT_MIN_S)
    int one_shot;
    double one_shot_hold;
    // each partial its own jitter (jitter_by_partial), its strike's sign
    // spread (strike_phase_spread): the tone's (a snare's wires)
    int pjit;
    double sps;
    int ssc;            // each mode's level scattered by stroke (stroke_scatter)
    // a GATED one-shot (gate_time > 0): its note ends gate_time past its
    // onset, the key-up ignored (held_texture: no earlier than the key-up)
    double gate_time;
    int held_texture;
    // A SHAKE AS SHAPED NOISE (shake_noise: ShakenNoiseProperties), in place
    // of the tone: noise_bands, noise_rows a band, the shake held for
    // shake_frac of the key (shake_min_s at least), swelling in over rise_s,
    // then the settle falling settle_db over settle_s, crossfaded over
    // shake_xfade_s; noise_rel the rows' width
    int shake, n_nb, noise_rows;
    double nb_hz[32], nb_db[32];
    double shake_min_s, shake_frac, shake_xfade_s, rise_s, settle_db, settle_s, noise_rel;
    // the strike fired strike_flam times (n_flam > 1: an ensemble clap), each
    // within flam_s and flam_db under the loudest
    int n_flam;
    double flam_s, flam_db;
    double flam_rate;       // a crowd (strike_flam_rate): bursts a second through the note, 0 none
    // A FEW PEOPLE (strike_flam_people): how many, their lowest and highest
    // claps a second, the jitter, the dB spread; their palms' ring
    // (strike_flam_people_peak: lowest and highest Hz, dB, Q), pk_set 0 none
    int people_n, pk_set;
    double people_lo, people_hi, people_jit, people_db, pk_lo, pk_hi, pk_db, pk_q;
    // TIMED NOISE BANDS (noise_events: Hz, dB, start s, end s), noise_rows a
    // band, ramped nev_ramp_s; their width -noise_rel (in nb's noise_rel)
    int n_nev;
    double nev[64][4], nev_ramp_s;
    // ...or a machine's (strike_flam_times: each burst's offset s, dB, and
    // place in the balance -- the cos/sin of its angle -- where ft_bal)
    int n_ft, ft_bal;
    double ft_t[64], ft_db[64], ft_c[64];
    // MORE STRUCK THINGS THAN ONE (strike_noise_layers): each its table, rise
    // s, dB/s and length s, from the note's onset
    int n_layer;
    int lay_n[32];
    double lay_hz[32][32], lay_db[32][32], lay_rise[32], lay_dbs[32], lay_len[32];
    int played_backwards;               // a tape played backwards: every row reversed (ToneIn.rev)
    // THE BREATH (breath_noise_db, as breath_noise_at gives it: no low
    // register, no octave law): its bands (Hz, dB), bn_rows noise rows a
    // band, held for the note and swelling in over bn_fade_s
    int n_bn, bn_rows;
    // ...in the low register its own table, blended in by band under
    // register_low_hz in dB (breath_noise_low_db: bn_low, NaN where it has
    // none; bn_low_set none at all)
    int bn_low_set;
    double bn_low[64], bn_low_hz[2];
    double bn_fade_s;
    double bn_hz[64], bn_db[64];
    int bendable;                       // pitch_bendable: a wheel moves it (blockrender's bend row)
    // CC71-78 AS IT ANSWERS THEM (sound_controls_of: bits in SOUND_CC's
    // order, 71 first), its own starting point (sound_bias, d each), and
    // tonelib's laws: time x/ snd_time_range, vibrato rate x/ snd_rate_range,
    // its delay to snd_delay_s
    int snd_mask;
    double snd_bias[8], snd_time_range, snd_rate_range, snd_delay_s;
    // ITS GLIDE (glide_mechanism: 0 none, 1 a hand's, 2 a circuit's, 3 a
    // valve's), its reach in semitones (NaN: any), and tonelib's portamento
    // laws (porta_semitone_time's ends, _PORTA_D_SEMI, PORTA_SETTLE_TAUS)
    int glide_mech;
    double glide_reach, porta_fast, porta_slow, porta_d_semi, porta_settle;
    // A REGISTERED ORGAN (registerable): its ranks and their pipes, NULL none
    // (the caller's pointer, set after the class is made or loaded)
    const struct OrganSpec *organ;
    // A HAMMOND'S CABINET AND AMPLIFIER: its rotating speaker (leslie: 0
    // none, 1 starting on chorale, 2 on tremolo -- leslie_fast), its scanner
    // (0 none, else 1, +2 a selector CC94 sets -- scanner_switch -- +4 x
    // its own depth 1-3, +16 its own on chorus), its valve stage's drive
    // (amp_drive, 0 none) -- against a fixed peak (amp_reference, 0 the
    // segment's own; the channel's fader taken back out), its pair's
    // imbalance (amp_imbalance)
    int leslie, scanner;
    double amp_drive, amp_reference, amp_imbalance;
    int wheel_swell;                    // the mod wheel its expression pedal (live's 'swell' role)
    // A PLAYER'S BELLOWS (bellows_push_*, a standalone voice's: the
    // accordions'): a note from silence pushes, a slur carries the push on
    // (blockrender._push_finish) -- its gain, rise, fall, settle, tilt and
    // its law by octave; 0 gain none
    double push_gain, push_rise_s, push_dbs, push_settle_db, push_tilt, push_tilt_oct;
    // THE PLAYER'S BREATH (breath_wobble_db...: a harmonica's): its notes on
    // its channel's breath rows (breath: the tone's level or pitch wobbles;
    // its breath noise its own row where that wobbles too), and the rows'
    // laws -- wobble dB, Hz; the noise's dB, Hz, share; the pitch's cents,
    // Hz, share (nv_breath_rows' p)
    int breath;
    double breath_p[8];
    // ITS TREMOLO (tremolo_depth: a voice's, not an organ's): its rate and
    // depth (the channel's first CC1 its share of it, or all of it where the
    // stroke is the tone: trem_intrinsic), stereo, a section's scatter
    double trem_hz, trem_depth, trem_scatter;
    int trem_stereo, trem_intrinsic;
    int touch_sensitive;            // velocity sets its level (a key that only opens a valve does not)
    // ITS SPEAKER CABINET (cabinet.py, a voice's cabinet): FormantBody's
    // response -- its floor, formants and antiformants (Hz, bandwidth, amp or
    // depth), its top corner and order, its low cutoff and order -- over its
    // own level at 1 kHz (cab_ref); cab_set 0 none
    int cab_set, n_cab_fm, n_cab_afm;
    double cab_floor, cab_fm[4][3], cab_afm[4][3], cab_corner, cab_order, cab_cut, cab_bell, cab_ref;
    // THE KEY-UP'S CLICK (release_click_db: n_click 0 none): the jack's
    // fixed modes (Hz, amplitude) at click_db, decaying click_dec dB/s for
    // click_s; on an organ with choirs (click_jacks), one a drawn stop's jack
    int n_click, click_jacks;
    double click_db, click_hz[16], click_amp[16], click_dec, click_s;
    int pre_pluck;          // a quill's catch (pre_pluck_s): live's catch rows end at the slip (rof)
    // A MOOG (moog.py; VoiceSnap.kind 6): each layer's panel as its note
    // reads it (native.moog_spec), n_layer 0 none
    MoogSpec moog;
    int brass;              // the horn's intonation (brass_fingering): 1 a trumpet's, 2 a tuba's; 0 none
    int bn_slur;            // on a slur the breath takes the legato attack (breath_noise_slur: slur_attack)
    // a MELODIC one-shot's hold (blockrender.one_shot_ring): until its last
    // partial is os_floor_db under its loudest, one_shot_hold to os_max_s
    double os_floor_db, os_max_s;
    // A SLOWER TAIL under the strike (strike_noise_tail): its bursts again,
    // tail_db under, falling tail_dbs; tail_set 0 none
    int tail_set;
    double tail_db, tail_dbs;
    // A CLAVINET's PANEL (clav_panel): its tone rockers by the part's first
    // CC1 (_prep_clav_rockers)
    int clav_panel;
    // ITS MOD WHEEL CAN BE A VIBRATO (wheel_vibrato: not a hammer's, a
    // mallet's, a stick's or a noise's -- live's 'vibrato' role)
    int wheel_vibrato;
    // THE SOUND CONTROLLERS' SHAPING (tonelib.sound_shape, CC74 and CC71):
    // brightness as effort (sh_et), a corner moved (sh_corner, sh_order), or
    // -- sh_pluck -- the pluck point (pluck_shape: the class's strike point
    // sh_sp, or a stopped string's from sh_open/sh_popen; sh_sd its depth,
    // sh_B, sh_mh its series); resonance a mute's (sh_mq, sh_mhz, sh_mdb) or
    // the corner's
    double sh_et, sh_corner, sh_order, sh_sp, sh_sd, sh_B, sh_mq, sh_mhz, sh_mdb, sh_popen;
    int sh_pluck, sh_mh, sh_nopen;
    double sh_open[8];
    // ITS ENTRY SCATTER, LIVE (t["scatter_ms"]: the class's section_onset_ms,
    // a section's or not -- a Moog's players come in apart too)
    double scatter_ms;
    // A STRUCK, PITCHED LAYER (struck_layer: an orchestra hit's timpani): the
    // class whose modes it is (sl: its NoteClass, the export's sl_idx), its
    // level (dB re the note's gain), rise (s) and fall (dB/s), the range its
    // pitch is moved into by octaves (Hz), how many modes (sl_nm); sl_on 0 none
    int sl_on, sl_idx, sl_nm;
    double sl_db, sl_rise, sl_dbs, sl_lo, sl_hi;
    const struct NoteClass *sl;
    // ITS CHORUS's COMB (chorus.offsets_for: chorus_cents, else the default), cents
    int n_cho;
    double cho_cents[8];
    // ITS SYMPATHETIC STRINGS, BY CONTACT (sympathetic.expand): sym_kind 1 a
    // fixed set (sym_pitch the strings' keys, sym_d each one's drive,
    // sym_cents its own tuning), 2 the body's neighbours (sym_pitch the
    // offsets, sym_d their drives, strongest first); sym_floor and sym_top
    // the set's floor and count; sym_nobend: a meend leaves them (bend_detents)
    int sym_kind, sym_n, sym_top, sym_nobend;
    double sym_floor;
    int sym_pitch[32];
    double sym_d[32], sym_cents[32];
    // THE OTHER STRINGS (ring_db): ring_n rows, each its Hz (12-TET at A440,
    // the note's table moves it), dB and dB/s; one on the note's own modes
    // within ring_skip is the plucked string itself
    int ring_n;
    double ring_hz[48], ring_db[48], ring_dps[48], ring_skip;
    int ring_nown;                  // the note's own modes' ratios (mode_ratios, or 1 and 2)
    double ring_own[16];
    int indian;                     // tuning_family 'indian': the secondary tuning's table (FREQ_E)
    // ...BY COINCIDENCE (sym_kind 3, a fixed set: sym_pitch the strings'
    // offsets from sym_tonic -- Sa's, under a raga -- sym_d each one's level,
    // 10^(dB/20)): sym_g the gain, sym_wmin the pluck's spread (Hz)
    int sym_tonic;
    double sym_g, sym_wmin;
    int meend;                      // bend_detents: a wheel on its channel meends (_MEEND_CH)
    // ...its range (bend_range_semitones, else GM's), how much each swara
    // holds (meend_strength), its Sa without a raga (sympathetic_tonic)
    double meend_range, meend_strength;
    int meend_tonic;
    double key_pan_spread;          // a wide voice (GS's "w" tones): its keys' seats, +-this 30 keys from middle C
    // GRAINS (grains): each row lo Hz, hi Hz, a second (negative: a clock),
    // dB, its scatter dB, dB/s, a glide's rise (0 none) and time, a cluster's sines
    int n_grain;
    double grain[8][9];
    // A PULSE (pulse: the gunshot's N-wave) in place of the series: its
    // length's range (ms), its spectrum's peak x T (N_WAVE_PEAK), band and taper
    int pulse;
    double pulse_lo_ms, pulse_hi_ms, pulse_peak, pulse_fmax, pulse_taper;
    double sounding_oct;    // a melodic note's sounding octaves (sounding_octaves), 0 none
    double xf;              // a sound transposed whole (transposed_from_hz): built at this pitch, 0 none
    // ...ITS KIT KEY'S STROKES (sfx_strokes_of): the program whose kit has it
    // (-1 none) and the key (-1: the note's own)
    int sfx_prog, sfx_key;
    // ITS OWN SCALE (scale_cents): offsets from the tonic note and their cents; scale_n 0 none
    int scale_n, scale_tonic;
    int scale_off[32];
    double scale_c[32];
    // A STRIKE-IN SET BY THE HAND (strike_in_s): the attack, soft to hard; si_set 0 none
    int si_set;
    double si0, si1;
    // ITS DRONES (drone_classes): each one's note and class (K's index), in
    // the order the wheel corks them; the gap that ends a phrase (part_break_s)
    int n_drone;
    int drone_note[4], drone_k[4];
    double part_break_s;
    // ...LIVE's (Patch.drone_wheel, drone_ratios, drone_gain): the wheel corks
    // them, each sounding at the tonic x its ratio, at its gain
    int drone_wheel, n_dratio;
    double drone_ratio[4], drone_gain[4];
    // ...and A DISTANCE OF ITS OWN (reverb_distance: where its part sends no CC91)
    int rd_set;
    double reverb_dist;
    // ...and THE FRETTING HAND (hammer_legato): a slurred note hammered on
    int hammer;
    // A FALL (fall_cents: held fall_at_s, then down the lattice over fall_s,
    // fading fall_fade_db) and A RIP (rip_cents: up the lattice into the note
    // over rip_s from rip_start_db under), each smeared; 0 cents none
    double fall_cents, fall_at_s, fall_s, fall_fade_db, fall_smear;
    double rip_cents, rip_s, rip_start_db, rip_smear;
    // ITS OWN CHORUS where the part sends no CC93: a pedal (chorus_send, its
    // comb cho_cents) or a detuned pair (detuned_pair: cents down, up)
    double cho_send;
    int pair_set;
    double pair_lo, pair_hi;
    // TREMOLO PICKING (tremolo_pick_hz, 0 none): the up strokes tp_up_db,
    // each stroke's time scattered tp_jit of a period
    double tp_hz, tp_up_db, tp_jit;
    // A SIREN'S ROTOR (siren_rotor): 1 the fire siren's (its motor), 0 none
    int siren;
    // ITS OWN INSERTION EFFECT (insertion_efx: gsefx.chain of its tone_state):
    // its output level, its OD stage's gain (0 none), its EQ (low dB, mid Hz,
    // Q, mid dB, high dB; efx_eq_set 0 none) and its reverb send (0-127)
    int efx_set, efx_eq_set;
    double efx_level, efx_od, efx_eq[5], efx_rev;
    // ...ITS CHORUS DEVICE (its 'cf': chorus.gs_copies), efx_cf 0 none: tau,
    // rate, vd, fb, lpf (0 none), share, taps, the head's beta; each output's
    // place (l, r, c: left and right incidence, left and right delay in
    // samples); each tap's output (0 l, 1 r, 2 c), phase, extra delay, depth
    int efx_cf;
    double cf_p[40];
    // ...ITS DELAY (its 'dly': gsdelay.expand), efx_dly 0 none: level, fb,
    // lpf (0 none), tc, taps; each tap's tau, level, output (0 l, 1 r, 2 c),
    // period -- and the outputs' places (efx_place: the head's beta, then l,
    // r, c's left and right incidence, left and right delay in samples)
    int efx_dly;
    double dly_p[24], efx_place[13];
    // ...ITS TREMOLO (an Auto Pan's 'trem': rate, depth, stereo, scatter), efx_trem 0 none
    int efx_trem;
    double trem_cfg[4];
    // ...ITS MOVING FILTER (efxfilter: a Phaser's or wah's), flt_set 0 none:
    // its type, control kind (1 a sweep, 2 a held pedal), parameters (pa, pb,
    // pc) and control's (Manual Hz, octaves, rate, up: NaN a phaser's, 1 up, 0
    // down; sens)
    int flt_set, flt_ty, flt_k;
    double flt_p[3], flt_c[5];
    // ...ITS BUS (efxbus.Bus), efx_bus 0 none: 1 Lo-Fi (step, quantum, pre
    // and post filters' a, 0 none), 2 a compressor (threshold dB, ratio,
    // attack and release k, makeup); bus_p[10], [11] its dry and wet
    int efx_bus;
    double bus_p[12];
} NoteClass;

// A note, as its file and channel give it, and the emitter's state for it.
typedef struct {
    double f0, pan, vel, chan_vol, effort, on, off, nx;
    int has_nx, mcut, slurred, slur_out;
    double detune_lo, detune_hi;        // string_detune_range, the honky-tonk's wheel applied
    int soft_pedal_down, fixed_touch;
    double sr, retrigger_fade, channel, br, nyq_om;
    double sv[2], sound_vib_depth_cents, vibrato_delay, gl[3];
    double fx, mk, fm_omega, fm_phase;
    double room_bands[9];
    int reflect, no_reflections;        // the emitter's REFLECT, and no_reflections before the note
    // for nv_song_play: the note's key in its file, and its key-up
    long long ch;
    int note, damper_pedal;
    double key_off;
    // the room's walls (WALLS' order, signed planes) and its reflection order
    double planes[6];
    int order;
    int from_song;                      // nv_song_play: its pitch and level from the song too...
    int song_index;                     // ...as its note there (the song's notes, in order)
    double seat;                        // a seat in the instrument (a kit's drum): its pan there, 0 none
    double held;                        // how long its key was held, s (a shake's share of it)
    double rnd_draws[4];                // an [RND] voice's strike (VoiceInit.rnd_draws)
    // a throat's pulse (SfxThroatProperties): its tilt, mouth and vowel's
    // morph -- NaN, the class's own
    double stroke_tilt, stroke_mouth, stroke_morph;
    // CC73 and CC72 (the sound controls the class answers): the attack's and
    // the release's time scale, 0 none
    double snd_at, snd_rt;
    // AN ORGAN'S RANKS, as its registration leaves them for this note: each
    // rank's gate row, when it speaks (NaN: never drawn for it -- gated
    // shut, at the note's onset), whether it is drawn only after the key
    // lifted (skip: it does not speak), or pushed in before the key-up
    // (rel1: its release a sample); and the organ's swell row
    double rank_gr[32], rank_sp[32];
    int rank_skip[32], rank_rel1[32];
    double organ_cr;
    double rank_br[32];     // each rank's bend row: its chest's wind (wrow_of), as it stands at that rank
    double carry_radius;    // the emitter's radius from the note before (an organ's last pipe), NaN none
    // a reed organ's at its onset: the Expression stop's bellows (CC11 / 127,
    // NaN: not drawn), and the Percussion stop drawn
    double organ_hx;
    int organ_perc;
    // THE BREATH'S OWN ROW (bbr_set: the player's breath noise wobbling on
    // its own, bbrow_of's second); else the note's
    int bbr_set;
    double bbr;
    int rank_drawn_off[32]; // each rank drawn at the key-up (its jack clicks: release_click_db)
    // A MOOG's knobs as GM's sound controllers turn them (moog.apply_gm):
    // CC71-78's offsets at its onset, the class's own; snd_moog 0 none
    int snd_moog;
    double snd_d[8];
    // A SUNG VOICE (_VocalBody): its part's tessitura (Hz, 0: its own pitch)
    // and the voice part its channel declares (part 0 none, else 1 + its
    // index in nv_voice_body's table)
    double sung_hz;
    int part;
    double dist;            // its distance multiple (_src_dist: CC91 / 40, or its step at the onset); 0: 1
    double gliss_lv;        // a valved gliss's step: its level (_GLISS), 0: none
    // ITS OTHER STRINGS (ring_db), ring_on: each one's Hz in the note's
    // table (ring_f, the class's order); fbr the channel's fader row, -1 none
    int ring_on;
    double ring_f[48], fbr;
    void *sym_drv;          // where its voice goes, the driver of its channel's strings (_SYM_CH), NULL not
    double blk;             // the render's block (BLK): a pulse's lead is two of them
    double xp;              // ...the key's interval it is moved by (_XP), 0: 1
    // A HAMMER-ON (hammer_legato): hammered over the file's slur, a mono or
    // gliss slur besides (its attack the legato's again), the seconds since
    // the channel's last pick
    int hammered, reslur;
    double hammer_on;
    // A SIREN's (_SIREN_AT): sounding until its rotor's end, siren_set 0 none
    int siren_set;
    double siren_end;
    // ITS PRESSURE (_pressure_of: its polytouch, else its channel's aftertouch), 0..1
    double press;
    // THE FILE'S GS EQ on its part (gs_eq_gain): low and high corners, gains (dB); [0] 0 none
    double gs_eq[4];
    // ITS PART ON THE FILE'S INSERTION EFFECT at its onset (nvrender's
    // chains): fx_set 1 a chain (its level, OD gain, 0 none, compressor), 2
    // the part on it with no chain built (the tone's own not played), 0 not
    int fx_set;
    double fx_level, fx_od, fx_comp[3];
} NoteIn;

/* tone.c: an organ note's ranks (_note_stops for a registered organ), its
   pushes after them; fin: the ears, delays and pipe radius the last rank
   leaves the emitter (li, ri, dl, dr, radius; radius NaN: none), and how
   many of its rows, the last, are the push */
/* blockrender's _RNORM: the reflections' normalisation memo, emptied at a
   render's start (each _prepare its own) */
void nv_refl_memo_reset(void);
/* live.cpp: chorus.expand's send path -- each channel (chans, in its first
   note's order) at its send (0..1), its comb (ncents[q] cents of
   cents[8 q ...]): a copy of each of its rows per comb tooth, detuned,
   delayed and swept, the dry share taken out of the rows -- or, kinds[q] 1,
   a detuned pair (chorus._pair: cents[8 q] down, cents[8 q + 1] up). The
   copies made. */
void nv_gsd_place_reset(void);
void nv_gsd_place(int side, double f, const double *pl, double *out);
long long nv_chorus_expand(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                           const double *sends, const int *ncents, const double *cents, const int *kinds,
                           const double *gsp, double sr);
int nv_struck(const VoiceSnap *v, const ToneIn *t, const VoiceSnap *ls, int nm, double ft, const double *hv,
              double hmax, double db, double rise, double dbs, long long seed, int nimg, const int *nsurf,
              const int *surf, const double *img, const double *mir, double *rows, int cap, double *qacc,
              double *azimuth);
int nv_organ_tone(const OrganSpec *og, const VoiceSnap *host, const ToneIn *t, const NoteIn *n, PyRandom *rs, int note,
                  int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
                  double *rows, int cap, double *qacc, double *azimuth, double *fin);


// What the note's setup worked out, beside its rows.
typedef struct {
    int n_knock, n_tone, n_phantom;
    double non, noff, fade, rel, chiff, jitter_scale;
    double dl, dr, li, ri, pos_x, pos_z, B;
    double cv, cc, crl, sjit, csc;
    double tb[3], cbw[2];
    double radius;          /* the emitter's radius after the note (an organ's last pipe), NaN none */
    int n_push;             /* the tone's last rows that are its push (_PUSH_ROWS) */
    double f0;              /* the note's pitch (a standalone push's, nv_play) */
    /* its key-up's click, its last rows (n_click; _REL_ROWS): each jack's
       rows (jack_n), its rank (-1: one click, no jack) and offset (s) */
    int n_click, n_jack, jack_n[32], jack_rank[32];
    double jack_off[32];
    /* a Moog's layers' filter rows (moog.ft_row), slot 9 the layer's index:
       the caller's knob row goes there */
    int n_ft, lay_rows[2];          /* (each layer's rows, in order) */
    double ft[2][30], kn[2][9];     /* ...and their knob rows (moog.kn_row, the knobs turned) */
    int ring0, ring1;               /* its other strings' rows (_RING), from the note's first */
    int grain0, grain1;             /* its grains' rows (_GRAIN_ROWS: live keeps their own onsets) */
} NoteOut;

// tone.c: the key-up's click (nv_click, blockrender._note_release_click)
int nv_click(const VoiceSnap *v, const ToneIn *t, const NoteClass *K, const NoteIn *n, double noff, int nimg,
             const int *nsurf, const int *surf, const double *img, const double *mir, double *rows, int cap,
             double *qacc, double *azimuth, NoteOut *out);

int nv_note(const NoteClass *K, const NoteIn *n, PyRandom *rs,
            int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
            double *rows, int cap, double *qacc, double *azimuth, NoteOut *out);
int nv_song_play(void *song, const NoteClass *K, NoteIn *n, PyRandom *rs,
                 int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
                 double *rows, int cap, double *qacc, double *azimuth, NoteOut *out, int *band);
int nv_play(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr, PyRandom *rs,
            double *rows, long long cap, double *qacc, double *azimuth, long long *nrows, int *played,
            long long *row0, int *bands, double *offs);

/* strings.c: one mode of the register's string bank */
typedef struct {
    long long key, string, harm;
    double f, alpha, w, hl, hr, dl, dr, px;
} StringMode;

/* tone.c: a section's player i's ears at its desk (section_seats) */
void nv_section_seat(const VoiceSnap *v, const ToneIn *t, int i, double *out);

/* npyrandom.c: numpy's default_rng(seed).standard_normal, draw by draw */
void *nv_npy_new(unsigned long long seed);
double nv_npy_next(void *g);
void nv_npy_free(void *g);

/* room.cpp: a source's image sources in the room (SynthProperties.image_sources) */
int nv_images(const double *planes, int order, double sx, double sy, double sz, int cap,
              int *nsurf, int *surf, double *img, double *mir);

/* channel.cpp's Song: a file's channels, as a note asks of them */
double nv_song_note_off(void *s, long long ch, int note, double on, double off, int damper_pedal, int mcut,
                        double retrigger_fade, int *band);
int nv_song_soft_at(void *s, long long ch, double t);
int nv_song_next_same(void *s, long long ch, int note, double on, double *out);
int nv_song_pitch_level(void *s, int index, int effort_tilt, double *out);
/* ...an 'indian' class's at the secondary tuning (indian 1: FREQ_E's) */
int nv_song_pitch_level_k(void *s, int index, int effort_tilt, int indian, double *out);
/* ...a class's sounding octaves into a melodic note's pitch (after its meend) */
int nv_song_pitch_level_ks(void *s, int index, int effort_tilt, int indian, double so, double *out);
/* ...the note's class's own pitch: its sounding octaves and its scale */
int nv_song_pitch_level_kc(void *s, int index, int effort_tilt, const NoteClass *K, double *out);
/* THE DRONES (_prep_phrase_spans, _DRONE_PC): once, the song's notes given
   the drones of each channel's drone class; 0, or -1 refused */
int nv_song_drones(void *s, const NoteClass *const *K);
/* THE SECONDARY TUNING (FREQ_E; NULL none) and the raga in force (raga_on:
   T.raga_spec set; sa its Sa's note, -1 none; sw its swaras' cents); and a
   note's table: the secondary's for an 'indian' class, else the channel's */
void nv_song_eastern(void *s, const double *freq_e, int raga_on, int sa, const double *sw, int nsw);
int nv_song_raga_sa(void *s);          /* T.raga_sa_note, -1 none */
int nv_song_has_eastern(void *s);       /* a secondary tuning (FREQ_E) */
int nv_song_raga_sw(void *s, double *sw);   /* T.raga_spec's swaras' cents (sw[12]), their count; -1 none */
/* _MEEND_AT: a note's meend -- its ratio at Note On (f0's) and its row (-1 none);
   and song note i's row, 1 if it meends */
void nv_song_meend(void *s, long long ch, int note, double on, double r0, double row);
int nv_song_meend_row(void *s, int i, double *row);
void nv_song_note_table(void *s, long long ch, double t, int indian, double *out);
/* THE DRIVER OF A CHANNEL's STRINGS (sympathetic._coupling's: _SYM_CH's
   props, its first note's voice): a VoiceSnap's room, once a mix channel,
   NULL after; read back (NULL none); and all forgotten (a play again) */
void *nv_song_sym_driver(void *s, long long mix, int size);
const void *nv_song_sym_get(void *s, long long mix);
void nv_song_sym_reset(void *s);
/* voice.c: sympathetic._coupling by coincidence -- how loudly rsp rings, a
   fraction of its own level, when drv is struck (g the gain, wmin the
   pluck's spread) */
double nv_sym_coupling(const VoiceSnap *drv, const VoiceSnap *rsp, double g, double wmin);
void nv_song_kits(void *s, const double *f0, const double *seat);
void nv_song_chokes(void *s, const unsigned long long *choke);
void nv_song_legato(void *s, long long ch, int note, int k);
void nv_song_note_stroke(void *s, int i, double ratio, int inner);
void nv_song_strokes(void *s, const int *kind, const double *par);
/* ...and a melodic SFX note's, its class's kit key's (K: the classes) */
void nv_song_strokes_k(void *s, const NoteClass *const *K, const int *kind, const double *par);
/* a note's stroke pitch (stroke_pitch: a bell tree's bar, a gallop's hoof), 1 none */
double nv_song_note_ratio(void *s, int i);
int nv_song_slur(void *s, int i, int *out);
int nv_song_snd_any(void *s, long long ch);
long long nv_song_mix(void *s, int i);
int nv_song_snd_moves(void *s, long long ch);
/* render.cpp: THE MOOG's columns of a table with one (its filter rows FT,
   knob rows KN): fx mk (int32), fmw fmp fmpR */
typedef struct {
    const float *FT, *KN;
    const int *fx, *mk;
    const double *fm[3];
    long knk, kb0;                          /* KN's entries a row, from grid point kb0 */
    const int *MPI, *MKI;                   /* its pitch rows and shape rows, NULL none */
    const double *MPC;
    const float *MPR, *MPK;
} MoogCols;
int nv_song_moog_n(void *s);
int nv_song_moog_ft(void *s, int i, double *out);
void nv_song_moog_add(void *s, long long ch, const double *ft, const double *kn, const MoogLayer *L, double a0,
                      double toff, double end);
int nv_song_moog_rows(void *s, int i, const MoogLayer **L, double *a0t);
void nv_song_add_mf104(void *s, long long r0, long long r1, const MoogLayer *L);
int nv_song_mf104(void *s, int i, long long *r0, long long *r1, const MoogLayer **L);
int nv_song_moog_tables(void *s, float *ft, float *kn, int *nkn, long *knk, long *kb0);
void nv_song_moog_add_moving(void *s, long long ch, const double *ft, const MoogLayer *L, const void *cls,
                             int layer, const double *bias, int mask, double sr, double a0, double toff, double end);
int nv_song_choke(void *s, long long ch, int note, double on, double *out);
/* a note's class: K[128 * program + key], a drum set's K[16384 + 128 * program + key] */
#define NV_K_DRUMS 16384
/* ...a variation's (bank select): K[NV_K_VAR + 128 * slot + key] */
#define NV_K_DRONE (2 * NV_K_DRUMS)
/* ...a drone's class (a bagpipe's: drone_classes): K[NV_K_DRONE + its index], 256 of them */
#define NV_K_VAR (NV_K_DRONE + 256)
// A DRUM KEY'S GESTURE ROW (native.kits' spar, native.SPAR): its strokes'
// numbers from the row's start (up to NV_SPAR - 4: a pattern's 32 strokes),
// and in its last four the keys a strike on it also sounds -- how many, then
// up to three
#define NV_SPAR 136
void nv_song_cc(void *s, long long ch, double t, int cc, int v);
/* a sung part's (blockrender._prep_choir_parts): a channel's tessitura, the
   median of its keys, in Hz (0: no notes); the part its track declares
   (1 + nv_voice_body's index, 0 none) */
/* slab.cpp: tonelib.sound_shape (a per-partial gain for brightness db and
   resonance dr on class k, bright/res: granted) and normalise_power (g
   scaled so amp g carries amp's power) -- live's and the file's alike */
void nv_sound_shape(const NoteClass *k, const double *nf, long n, double db, double dr, int bright, int res,
                    double *g);
void nv_normalise_power(const double *amp, long n, double *g);
/* mono mode's flags on song note i (_MONO_CUT, _MONO_SLUR); and read back */
void nv_song_note_mono(void *s, int i, int mcut, int mslur);
int nv_song_mono(void *s, int i, int *mcut, int *mslur);
/* the valved glisses walked (_prep_gliss): the song's notes rewritten, once;
   and a note's step (level, smear, the step it arrives from or -1, the step's
   time), 0 not one */
void nv_song_gliss(void *s, const NoteClass *const *K);
void nv_song_slot_organs(void *s, int n, const OrganSpec *const *so);
void nv_song_play_mark(void *s);
void nv_song_siren(void *s, long long ch, int note, double on, double row, double end);
void nv_song_efx_part(void *s, long long part, double on, double dist);
void nv_song_pressure_events(void *s, long long ch, int key, int n, const double *t, const int *v);
double nv_song_pressure(void *s, long long ch, int note, double on, double off);
int nv_song_efx_dist(void *s, long long part, double on, double *dist);
void nv_song_gs_eq(void *s, const double *eq, int noff, const int *off);
void nv_song_gs_delay(void *s, const double *dev, const double *place);
void nv_song_dedit(void *s, int n, const int *iv, const double *t);
int nv_song_dst(void *s, long long ch, int key, double on, int *v);
const double *nv_song_gs_delay_of(void *s, const double **place);
int nv_song_gs_eq_of(void *s, long long part, double *eq);
int nv_song_siren_of(void *s, int i, double *out);
int nv_song_gliss_note(void *s, int i, double *out);
double nv_song_tess(void *s, long long ch);
void nv_song_set_part(void *s, long long ch, int part);
int nv_song_part(void *s, long long ch);
/* voice.c: tonelib.voice_body over a track's name -- 1 + the part's index in
   VOICE_BODIES' table (native.py hands it over: nv_voice_bodies_set), 0
   none; nv_voice_part its ratio and cluster */
int nv_voice_bodies_set(int n, const char *names, const double *ratio, const double *cluster, int nn);
int nv_voice_body(const char *name);
int nv_voice_part(int part, double *ratio, double *cluster);
void nv_song_note(void *s, long long ch, int note, double on, double off, int vel, double v7, double v11,
                  double pan, double trim, int prog, int drum);
int nv_song_n_notes(void *s);
/* BANK SELECT: the entries (each one's layers: slot, semitones, velocities;
   nls[e] of them, entry 0 none), their trims, GS's table [map][program][msb]
   and GM 2's [program][lsb]; the last note's bank (the reader's bsel) made
   its variation's notes (0: no table); a note's class index in K, and its
   tone on its part (_TONE_SEGS) */
void nv_song_vars(void *s, int nent, const int *nls, const int *ls, const double *trim, const int *gs, const int *gm2);
int nv_song_note_bank(void *s, int bsel);
int nv_song_kidx(void *s, int i);
int nv_song_tone(void *s, int i);
void nv_song_snd(void *s, long long ch, double t, int cc, int v);
void nv_song_sound(void *s, long long ch, double t, double *d);
int nv_song_glide(void *s, int i, int *cc5);
void nv_song_organ(void *s, long long ch, const OrganSpec *spec, const OrganSpec *const *prog_organ);
int nv_song_n_organs(void *s);
int nv_song_organ_tremolo(void *s);
void nv_song_add_push_rows(void *s, long long a, long long b);
void nv_song_add_rel_jack(void *s, long long a, long long b, int rank, double jo);
int nv_song_n_rel_jacks(void *s, double *out, int cap);
void nv_song_add_rel_rows(void *s, long long a, long long b);
int nv_song_n_rel_rows(void *s, long long *out, int cap);
int nv_song_n_push_rows(void *s, long long *ab, int cap);
double nv_song_note_trim(void *s, int i);
int nv_song_n_grows(void *s);
int nv_song_organ_wind_rows(void *s, int row0);
int nv_song_organ_rows(void *s, long nblk, int blk, double sr, double tau, float *G, float *S, double *sh);
void nv_song_organ_wind(void *s, long nblk, int blk, double sr, const float *G, float *BR, double *BC, float *BL);
int nv_song_organ_note(void *s, int i, int family, NoteIn *n);
int nv_song_stroked(void *s, int i);
void nv_song_add_stroke_rows(void *s, long long a, long long b);
/* each note's grains' rows (_GRAIN_ROWS), [first, end); n pairs into ab (NULL: count) */
void nv_song_add_grain_rows(void *s, long long a, long long b);
int nv_song_n_grain_rows(void *s, long long *ab, int cap);
int nv_song_n_stroke_rows(void *s, long long *ab, int cap);
int nv_song_htrem(void *s, int i);
void nv_song_add_htrem_rows(void *s, long long a, long long b);
int nv_song_n_htrem_rows(void *s, long long *ab, int cap);
int nv_song_organ_tremolos(void *s, int which, int *ch, double *cfg, int cap);
void nv_song_add_leslie(void *s, long long ch, int kind);
void nv_song_add_trem(void *s, long long ch, const double *cfg);
void nv_song_add_cab(void *s, long long ch, const NoteClass *k);
int nv_song_cabs(void *s, long long *ch, const NoteClass **k, int cap);
void nv_cabinet_pass(void *song, double *rows, long long P);
void nv_song_add_clav(void *s, long long ch, int setting);
int nv_song_clavs(void *s, long long *ch, int *setting, int cap);
void nv_clav_pass(void *song, double *rows, long long P);
int nv_song_trems(void *s, long long *ch, double *cfg, int cap);
void nv_song_add_amp(void *s, long long ch, double drive, int rotor, double reference, double imbalance,
                     double lv0);
void nv_song_amp_steps(void *s, long long ch);
int nv_song_amp_steps_of(void *s, int k, double *base, const double **starts, const double **levels);
// A FILE'S INSERTION EFFECT (nvrender's chains, NV_FXN doubles each): the
// chains, each note's (-1 its part not on the effect, -2 on it, no chain),
// which notes are their mix channel's first through a chain, the cabinets
// a chain names (guitar12, bass410; null none)
enum { NV_FXN = 24 };
void nv_song_fx(void *s, int nchain, const double *chains, int nnote, const int *note_fx, const unsigned char *first,
                const NoteClass *cab0, const NoteClass *cab1);
int nv_song_note_fx(void *s, int i, const double **chain);
int nv_song_note_fx_first(void *s, int i);
const NoteClass *nv_song_fx_cab(void *s, int which);
// ...and a mix channel's level steps over the file (its amp's reference: tubeamp.segment's 'steps')
void nv_song_fx_steps(void *s, long long ch, int n, const double *starts, const double *levels);
void nv_song_amp_cfg(void *s, int k, double *reference, double *imbalance);
double nv_song_amp(void *s, int k, long long *ch, int *rotor);
int nv_song_leslie(void *s, int k, long long *ch);
int nv_song_ccs(void *s, long long ch, int cc, double *t, int *v, int cap);
void nv_song_get_note(void *s, int i, long long *ch, int *iv, double *dv);
void nv_song_note_voice(void *s, int i, double *out);
int nv_song_first_cc(void *s, long long ch, int cc, int *v);
int nv_song_sost(void *s, long long ch, int note, double on, double *out);
void nv_song_table(void *s, long long ch, double t, double *out);
double nv_song_total(void *s);
int nv_song_ped_spans(void *s, long long ch, double *out, int cap);
int nv_song_pedal_values(void *s, long long ch, double *t, int *v, int cap);
double nv_damper_contact(int p, int key, int top);
double nv_stage_angle(double p);
double nv_harmonic_volume(const VoiceSnap *v, int harmonic);
void nv_partial_decay(const VoiceSnap *v, double f0, int m, double *out);
int nv_lreg_pluck(void *h, long long sid, int key, double at, int R, const double *cols, const long *slot,
                  const int *free_keys, int nfree, const int *plucked, int nplucked, const long *rchoir);
void nv_lreg_choirs(void *h, int nchoir, const long *bridges, double cross, int nbuff, const int *buffs);
void nv_lreg_keys(void *h, const int *kb, double cross, const int *partner, double partner_k, double ktilt,
                  int nkp, const double *kp_x, const double *kp_db);
int nv_strings_og(const VoiceInit *c0, const VoiceSnap *tmpl, const OrganSpec *og, const double *table, double pan,
                  double chan_vol, double sr, StringMode *out, StringMode *tmp, int cap);
int nv_strings(const VoiceInit *c0, const VoiceSnap *tmpl, const double *table, double pan, double chan_vol,
               double sr, StringMode *out, StringMode *tmp, int cap);

#ifdef __cplusplus
}
#endif

#endif
