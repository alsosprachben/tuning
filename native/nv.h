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
    double comb[129];
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
} ToneIn;

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
int nv_leak(const VoiceSnap *v, const ToneIn *t, double Bs, PyRandom *lr, int nimg, const int *nsurf,
            const int *surf, const double *img, const double *mir, double *rows, int cap, double *qacc,
            double *azimuth);

// What a voice class is to a note's setup: the constructor's constants and
// the class's VoiceSnap, the attack/release/chiff laws, the tension bend and
// the hammer's knock (strike_noise_db). "_set" flags carry Python's None.
typedef struct {
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
} NoteIn;

/* tone.c: an organ note's ranks (_note_stops for a registered organ), its
   pushes after them; fin: the ears, delays and pipe radius the last rank
   leaves the emitter (li, ri, dl, dr, radius; radius NaN: none), and how
   many of its rows, the last, are the push */
int nv_organ_tone(const OrganSpec *og, const VoiceSnap *host, const ToneIn *t, const NoteIn *n, int note,
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
void nv_song_kits(void *s, const double *f0, const double *seat);
void nv_song_chokes(void *s, const unsigned long long *choke);
void nv_song_legato(void *s, long long ch, int note, int k);
void nv_song_note_stroke(void *s, int i, double ratio, int inner);
void nv_song_strokes(void *s, const int *kind, const double *par);
int nv_song_slur(void *s, int i, int *out);
int nv_song_choke(void *s, long long ch, int note, double on, double *out);
/* a note's class: K[128 * program + key], a drum set's K[16384 + 128 * program + key] */
#define NV_K_DRUMS 16384
// A DRUM KEY'S GESTURE ROW (native.kits' spar, native.SPAR): its strokes'
// numbers from the row's start (up to NV_SPAR - 4: a pattern's 32 strokes),
// and in its last four the keys a strike on it also sounds -- how many, then
// up to three
#define NV_SPAR 136
void nv_song_cc(void *s, long long ch, double t, int cc, int v);
void nv_song_note(void *s, long long ch, int note, double on, double off, int vel, double v7, double v11,
                  double pan, double trim, int prog, int drum);
int nv_song_n_notes(void *s);
void nv_song_snd(void *s, long long ch, double t, int cc, int v);
void nv_song_sound(void *s, long long ch, double t, double *d);
int nv_song_glide(void *s, int i, int *cc5);
void nv_song_organ(void *s, long long ch, const OrganSpec *spec, const OrganSpec *const *prog_organ);
int nv_song_n_organs(void *s);
int nv_song_organ_tremolo(void *s);
void nv_song_add_push_rows(void *s, long long a, long long b);
int nv_song_n_push_rows(void *s, long long *ab, int cap);
double nv_song_note_trim(void *s, int i);
int nv_song_n_grows(void *s);
int nv_song_organ_wind_rows(void *s, int row0);
int nv_song_organ_rows(void *s, long nblk, int blk, double sr, double tau, float *G, float *S, double *sh);
void nv_song_organ_wind(void *s, long nblk, int blk, double sr, const float *G, float *BR, double *BC, float *BL);
int nv_song_organ_note(void *s, int i, int family, NoteIn *n);
int nv_song_stroked(void *s, int i);
void nv_song_add_stroke_rows(void *s, long long a, long long b);
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
int nv_song_trems(void *s, long long *ch, double *cfg, int cap);
void nv_song_add_amp(void *s, long long ch, double drive, int rotor, double reference, double imbalance);
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
int nv_strings(const VoiceInit *c0, const VoiceSnap *tmpl, const double *table, double pan, double chan_vol,
               double sr, StringMode *out, StringMode *tmp, int cap);

#ifdef __cplusplus
}
#endif

#endif
