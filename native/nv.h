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
} VoiceSnap;

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
    double dur;
    int ssc;            /* each mode's level scattered (stroke_scatter: random.gauss) */         /* the note's length, s: the bloom's swell is held within it */
    /* a tape played backwards (played_backwards): every row reversed, from
       the strike at rev_n0 to its arrival at rev_arr (_Emitter.reverse) */
    int rev;
    double rev_n0, rev_arr;
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
    double bn_fade_s;
    double bn_hz[64], bn_db[64];
    int bendable;                       // pitch_bendable: a wheel moves it (blockrender's bend row)
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
} NoteIn;

// What the note's setup worked out, beside its rows.
typedef struct {
    int n_knock, n_tone, n_phantom;
    double non, noff, fade, rel, chiff, jitter_scale;
    double dl, dr, li, ri, pos_x, pos_z, B;
    double cv, cc, crl, sjit, csc;
    double tb[3], cbw[2];
} NoteOut;

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
int nv_song_stroked(void *s, int i);
void nv_song_add_stroke_rows(void *s, long long a, long long b);
int nv_song_n_stroke_rows(void *s, long long *ab, int cap);
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
