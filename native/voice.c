/* voice.c -- a note's voice in C: the per-partial physics the note loop asks
 * of its Python voice (tonelib.SynthProperties and its classes), and the
 * string's partials (blockrender.string_partial / partial_decay /
 * unison_partial), operation for operation, so a port is bit-identical and
 * checked by identity (examples/native_check.py).
 *
 * THE VOICE AS NUMBERS (VoiceSnap): what these methods read of one note's
 * Python voice object, filled by native.py's snapshot(). A voice using a
 * feature not ported yet (mode tables, a bore, pickups, harmonic touch, a
 * plucked comb) is not supported: native.py says so and Python plays it.
 *
 * First voice: the grand piano (GrandPianoProperties) -- its hammer and
 * soundboard on SynthProperties' series, its unison strings, its
 * aftersound; and the shared ones every voice uses (decay, radiation,
 * chiff, bloom, vibrato, the head's shadow).
 */
#include "pycompat.h"
#include "../roomcore.c"        /* air_db, directivity_gain: the room's, shared */

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
} VoiceSnap;

/* tonelib.db_ratio */
static double db_ratio(double db)
{
    double x = 3000.0 < db ? 3000.0 : db;      /* min(db, 3000.0) */
    return pow(10.0, x / 10.0);
}

double nv_mode_ratio(const VoiceSnap *v, int m)
{
    (void)v;
    return (double)m;                           /* mode_ratios None */
}

double nv_series_volume(const VoiceSnap *v, int harmonic)
{
    if (v->max_harmonic && harmonic > v->max_harmonic)
        return 0.0;
    if (harmonic % 2 == 0 && !v->even_db_set && v->odd_only)
        return 0.0;
    int sm = harmonic;                          /* harmonic_touch 0 */
    double depth = v->strike_depth;
    if (v->strike_fills)
        depth *= (1.0 - v->strike_fill_fraction * v->attack_volume);
    double comb = (1.0 - depth) + depth * fabs(sin(sm * PI * v->strike_point));
    double r = v->gain / pow((double)sm, v->attack_dampening) * comb;
    if (harmonic % 2 == 0 && v->even_db_set)
        r *= pow(10.0, v->even_harmonic_db / 20.0);
    return r;
}

/* GrandPianoProperties.soundboard_gain */
static double soundboard_gain(const VoiceSnap *v, double fn)
{
    double body = 1.0 + v->board_body_gain * exp(
        -(pow(log(fn / v->board_body_hz), 2.0)) / (2.0 * pow(v->board_body_width, 2.0)));
    double high = 1.0 / (1.0 + pow(fn / v->board_high_hz, v->board_high_order));
    double low = 1.0 / (1.0 + pow(v->board_low_hz / fn, 2.0));
    return body * high * low;
}

/* GrandPianoProperties.harmonic_volume, on SynthProperties' (no bore) */
double nv_harmonic_volume(const VoiceSnap *v, int harmonic)
{
    double s = nv_series_volume(v, harmonic);
    if (s == 0.0)
        return 0.0;
    double fn = v->frequency_x * pow(2.0, v->octave_position) * harmonic;
    double fc = (v->hammer_corner_hz * (v->hammer_open_lo + v->hammer_open_slope * v->attack_volume)
                 * pow(2.0, v->hammer_register_slope * v->octave_position));
    return s / (1.0 + pow(fn / fc, v->hammer_order)) * soundboard_gain(v, fn);
}

double nv_harmonic_decay(const VoiceSnap *v, int harmonic)
{
    double h = (double)harmonic;                /* mode_ratios None */
    double base = v->decay_db + v->harmonic_decay_db * h * pow(h, v->harmonic_decay_dampening);
    return base * v->decay_register_factor;
}

/* GrandPianoProperties._string_blend */
static double string_blend(const VoiceSnap *v, double frequency, double break_hz)
{
    double half = v->string_crossfade_semitones / 2.0;
    double lo = break_hz * pow(2.0, -half / 12.0);
    double hi = break_hz * pow(2.0, half / 12.0);
    if (frequency <= lo)
        return 0.0;
    if (frequency >= hi)
        return 1.0;
    double t = (log(frequency) - log(lo)) / (log(hi) - log(lo));
    return t * t * (3.0 - 2.0 * t);
}

/* GrandPianoProperties.aftersound: (level, its decay rate) */
void nv_aftersound(const VoiceSnap *v, double frequency, double decay_rate, double *out)
{
    double b1 = string_blend(v, frequency, v->string_break_hz[0]);
    double b2 = string_blend(v, frequency, v->string_break_hz[1]);
    double level = v->aftersound_level[0] + (v->aftersound_level[1] - v->aftersound_level[0]) * b1;
    level += (v->aftersound_level[2] - level) * b2;
    out[0] = level;
    out[1] = decay_rate * v->aftersound_decay_ratio;
}

/* GrandPianoProperties.unison_voices: [(gain, offset Hz, ratio, decay, phase)]
 * in out[5k..5k+4]; returns how many */
int nv_unison_voices(const VoiceSnap *v, double frequency, int harmonic, double harmonic_decay, double *out)
{
    double gains[2] = {v->string_gain[0] * string_blend(v, frequency, v->string_break_hz[0]),
                       v->string_gain[1] * string_blend(v, frequency, v->string_break_hz[1])};
    int ng = 2;
    if (v->soft_pedal_down && v->soft_pedal_strings) {
        ng = ng - v->soft_pedal_strings;
        if (ng < 0)
            ng = 0;
    }
    if (ng > v->n_detune)
        ng = v->n_detune;
    int n = 0;
    for (int i = 0; i < ng; i++) {
        double g = gains[i];
        if (g < 1e-3)
            continue;
        double ratio = pow(2.0, v->note_detune_cents[i] / 1200.0) - 1.0;
        if (v->unison_beat_scatter) {
            PyRandom r;
            pyr_seed(&r, v->unison_key * 7919 + (long long)i * 104729 + harmonic);
            double off = pyr_uniform(&r, v->unison_beat_hz[0], v->unison_beat_hz[1])
                         * (pyr_random(&r) < 0.5 ? 1.0 : -1.0);
            out[5 * n + 0] = g; out[5 * n + 1] = off; out[5 * n + 2] = 0.0;
            out[5 * n + 3] = harmonic_decay; out[5 * n + 4] = 0.0;
            n++;
            continue;
        }
        out[5 * n + 0] = g; out[5 * n + 1] = 0.0; out[5 * n + 2] = ratio;
        out[5 * n + 3] = harmonic_decay; out[5 * n + 4] = 0.0;
        n++;
    }
    return n;
}

/* SynthProperties.radiation_gain at the voice's own position */
double nv_radiation_gain(const VoiceSnap *v, double frequency, double radius, int has_radius)
{
    double db = air_db(v->room, frequency) * v->radiation_distance;
    return directivity_gain(v->room, frequency, v->position_x, v->position_z, radius, has_radius)
           * pow(10.0, -db / 20.0);
}

/* SynthProperties.hrtf_gain: Brown-Duda's head shadow */
double nv_hrtf_gain(const VoiceSnap *v, double frequency, double incidence)
{
    double alpha_min = 0.1;
    double theta_min = 150.0 * PI / 180.0;
    double alpha = 1.0 + alpha_min / 2.0 + (1.0 - alpha_min / 2.0) * cos(incidence * PI / theta_min);
    double omega = 2.0 * PI * frequency;
    return sqrt(pow(alpha * omega, 2.0) + pow(v->hrtf_beta, 2.0)) / sqrt(pow(omega, 2.0) + pow(v->hrtf_beta, 2.0));
}

double nv_chiff_harmonic_gain(const VoiceSnap *v, double harmonic)
{
    if (!v->chiff_span_set)
        return 1.0;
    double x = (harmonic - 1.0) / v->chiff_harmonic_span;
    if (x <= 0.0)
        return 1.0;
    return 1.0 / (1.0 + pow(x, v->chiff_harmonic_power));
}

double nv_bloom_delay_for(const VoiceSnap *v, double frequency)
{
    if (v->bloom_seconds <= 0.0 || frequency <= 0.0)
        return 0.0;
    double d = fabs(log(frequency / v->bloom_center_hz) / log(2.0) / v->bloom_octaves);
    return v->bloom_seconds * exp(-0.5 * pow(d, v->bloom_shape));
}

/* SynthProperties._solo_vibrato / voice_vibrato: (depth, rate, phase) in
 * out; 0 for None */
static int solo_vibrato(const VoiceSnap *v, double frequency, int index, double *out)
{
    if (v->solo_vibrato_spread == 0.0)
        return 0;
    long long midi = (long long)rint(69 + 12 * log(frequency / 440.0) / log(2.0));
    PyRandom r;
    pyr_seed(&r, 0x5010 + midi * 64 + index + v->section_salt * 8191);
    double spread = v->solo_vibrato_spread;
    out[0] = 0.0;
    out[1] = v->solo_vibrato_hz * (1.0 + pyr_uniform(&r, -spread, spread));
    out[2] = pyr_uniform(&r, 0.0, 6.283185307179586);
    return 1;
}

int nv_voice_vibrato(const VoiceSnap *v, double frequency, int index, double *out)
{
    if (v->exp_vibrato_cents != 0.0) {
        double got[3];
        double rate, phase;
        if (solo_vibrato(v, frequency, index, got)) {
            rate = got[1];
            phase = got[2];
        } else {
            rate = v->solo_vibrato_hz;
            phase = 0.0;
        }
        out[0] = pow(2.0, v->exp_vibrato_cents / 1200.0) - 1.0;
        out[1] = rate;
        out[2] = phase;
        return 1;
    }
    return solo_vibrato(v, frequency, index, out);
}

/* blockrender.string_partial: (h, Hz) in out; 0 past the voice's last mode */
int nv_string_partial(const VoiceSnap *v, double f0, double ratio, int m, double B, double *out)
{
    double mr = nv_mode_ratio(v, m);
    if (mr <= 0.0)
        return 0;
    double h = ratio * mr;
    double stretch = B > 0 ? (1.0 + 0.5 * (h * h - 1.0) * B) : 1.0;
    out[0] = h;
    out[1] = f0 * h * stretch;
    return 1;
}

/* blockrender.partial_decay: (dB/s, log rate, aftersound's share, its log rate) */
void nv_partial_decay(const VoiceSnap *v, double f0, int m, double *out)
{
    double dbps = nv_harmonic_decay(v, m);
    double logr = dbps > 0 ? log(db_ratio(dbps)) : 0.0;
    double a[2];
    nv_aftersound(v, f0, dbps, a);
    out[0] = dbps;
    out[1] = logr;
    out[2] = a[0];
    out[3] = a[1] > 0 ? log(db_ratio(a[1])) : 0.0;
}

/* blockrender.unison_partial: (Hz, log rate) */
void nv_unison_partial(double hf, double off_hz, double dr, double ud, double *out)
{
    out[0] = hf * (1.0 + dr) + off_hz;
    out[1] = ud > 0 ? log(db_ratio(ud)) : 0.0;
}

/* random.Random(seed): its first n random() draws (the check's) */
void nv_random_check(long long seed, int n, double *out)
{
    PyRandom r;
    pyr_seed(&r, seed);
    for (int i = 0; i < n; i++)
        out[i] = pyr_random(&r);
}
