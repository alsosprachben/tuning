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

typedef struct {
    uint32_t mt[624];
    int i;
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
} VoiceInit;

/* what the note setup reads of the voice besides its VoiceSnap */
typedef struct {
    double pitch_jitter, attack_jitter, pan_angle;
    double left_incidence, right_incidence, left_hrtf_delay, right_hrtf_delay;
    double inharmonicity_coefficient, B;    /* the class's scaled; and the law's at the note */
    double tension_bend, attack_time;
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
} ToneIn;

void nv_voice_init(const VoiceInit *c, const VoiceSnap *tmpl, double frequency, double channel_pan,
                   double attack_volume, double channel_volume, double effort, PyRandom *rs,
                   VoiceSnap *s, VoiceNote *o);
int nv_tone(const VoiceSnap *v, const ToneIn *t,
            int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
            double *rows, int cap, double *transverse, int *ntrans, double *qacc, double *azimuth);
int nv_strike(const VoiceSnap *v, const ToneIn *t, int nb, const double *hz, const double *db,
              double reg, double bdb, double scal, double slr, double sfade, double slen, double bon,
              double pos_x, double *rows, int cap, double *qacc, double *azimuth);
int nv_phantom(const VoiceSnap *v, const ToneIn *t, const double *trans, int ntrans,
               int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
               double *rows, int cap, double *qacc, double *azimuth);

/* room.cpp: a source's image sources in the room (SynthProperties.image_sources) */
int nv_images(const double *planes, int order, double sx, double sy, double sz, int cap,
              int *nsurf, int *surf, double *img, double *mir);

/* channel.cpp's Song: a file's channels, as a note asks of them */
double nv_song_note_off(void *s, long long ch, int note, double on, double off, int damper_pedal, int mcut,
                        double retrigger_fade, int *band);
int nv_song_soft_at(void *s, long long ch, double t);
int nv_song_next_same(void *s, long long ch, int note, double on, double *out);

#ifdef __cplusplus
}
#endif

#endif
