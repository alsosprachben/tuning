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
#include "nv.h"
#include "pycompat.h"
#include "../roomcore.c"        /* air_db, directivity_gain: the room's, shared */


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

/* THE VOICE'S CONSTRUCTOR (SynthProperties.__init__ and
 * GrandPianoProperties.__init__): the class's constants, the note's
 * (frequency, pan, velocity, channel volume, effort), and the global random
 * stream in and out. What the base class draws from that stream (pitch and
 * attack jitter) is drawn here in its order, so the stream after a note is
 * the Python's. Branches the four native piano classes never take (a chiff
 * scaled by force, the bloom's gain, a strike wobble, a velocity trim table,
 * no HRTF) are refused by native.py, not ported. */


static double pymin(double a, double b) { return b < a ? b : a; }
static double pymax(double a, double b) { return b > a ? b : a; }

/* tonelib.stage_angle */
static double stage_angle(double p)
{
    return asin(0.5 * tan(pymax(-1.0, pymin(1.0, p)) * PI / 4.0));
}

/* SynthProperties.register_effort_at */
static double register_effort_at(const VoiceInit *c, double frequency)
{
    if (c->register_effort_db == 0.0 && c->register_tilt_db == 0.0)
        return 0.0;
    double octaves = log(frequency / c->register_center_hz) / log(2.0);
    double span = c->register_half_octaves;
    double x = pymin(1.0, fabs(octaves) / span);
    double tilt = c->register_tilt_db * pymax(-span, pymin(span, octaves));
    return c->register_effort_db * (x * x) + tilt;
}

/* SynthProperties.hrtf_at(position_x) at the voice's own height and distance */
static void voice_hrtf_at(const VoiceInit *c, double th, double position_x, double *out)
{
    double z = c->position_z, y = c->listener_distance;
    if (th != 0.0) {
        double px = position_x * cos(th) + y * sin(th);
        double py = -position_x * sin(th) + y * cos(th);
        position_x = px;
        y = py;
    }
    double distance = pymax(sqrt(pow(position_x, 2.0) + y * y + z * z), c->head_radius);
    double base_delay = distance / c->sound_speed;
    double cos_to_right = position_x / distance;
    for (int ear = 0; ear < 2; ear++) {
        double theta = acos(pymax(-1.0, pymin(1.0, ear == 0 ? -cos_to_right : cos_to_right)));
        double offset = theta <= PI / 2 ? -cos(theta) : (theta - PI / 2);
        out[ear] = theta;
        out[2 + ear] = base_delay + offset * c->head_radius / c->sound_speed;
    }
}

/* tmpl: the class's VoiceSnap (its constants; every per-note field is
 * rewritten here). rs: the global stream (Python's random.getstate()), or
 * NULL to draw from a scratch one -- the attack jitter is then not the
 * Python's, and nothing in the VoiceSnap depends on it. */
void nv_voice_init(const VoiceInit *c, const VoiceSnap *tmpl, double frequency, double channel_pan,
                   double attack_volume, double channel_volume, double effort, PyRandom *rs,
                   VoiceSnap *s, VoiceNote *o)
{
    PyRandom scratch;
    if (!rs) {
        pyr_seed(&scratch, 0);
        rs = &scratch;
    }
    *s = *tmpl;
    double eff = effort != 0.0 ? effort : c->effort;
    s->attack_volume = attack_volume;
    if (c->bloom_seconds > 0.0 && c->bloom_slope != 0.0) {
        double av = pow(pymax(attack_volume, 1e-3), -fabs(c->bloom_slope));
        s->bloom_seconds = c->bloom_seconds * pymin(av, c->bloom_stretch_max);
    } else {
        s->bloom_seconds = c->bloom_seconds;
    }
    s->frequency_x = 415.0;
    double op = log(frequency / s->frequency_x) / log(2.0);
    s->octave_position = op;
    if (c->max_partial_hz != 0.0 && frequency != 0.0) {
        int mh = (int)(c->max_partial_hz / frequency);
        s->max_harmonic = mh > 1 ? mh : 1;
    }
    s->decay_register_factor = pow(2.0, c->decay_register_slope * op);
    o->pitch_jitter = c->pitch_jitter_cents != 0.0
        ? pow(2.0, pyr_uniform(rs, -c->pitch_jitter_cents, c->pitch_jitter_cents) / 1200.0) - 1.0 : 0.0;
    o->attack_jitter = c->timing_jitter_seconds != 0.0 ? pyr_uniform(rs, 0.0, c->timing_jitter_seconds) : 0.0;
    o->tension_bend = c->tension_bend;
    if (c->tension_bend != 0.0) {
        double tbs = c->tension_bend > 0.0 ? 1.0 : -1.0;
        o->tension_bend = tbs * pymin(c->tension_bend_max, fabs(c->tension_bend)
                                      * pow(c->tension_bend_ref_hz / frequency, c->tension_bend_slope));
    }
    o->inharmonicity_coefficient = c->inharmonicity_coefficient;
    if (c->inharmonicity_dynamic)
        o->inharmonicity_coefficient *= (1.0 + fabs(op));
    s->attack_dampening = c->octave_modulo ? c->tonal_dampening + floor(op) * c->octave_dampening
                                           : c->tonal_dampening + op * c->octave_dampening;
    if (c->effort_tilt != 0.0 && eff != 0.0) {
        double tilt = c->effort_tilt;
        if (eff > 0 && c->effort_tilt_up_set)
            tilt = c->effort_tilt_up;
        s->attack_dampening -= (tilt * eff) / 6.0206;
    }
    s->even_db_set = c->even_db_set;
    s->even_harmonic_db = c->even_db_set ? c->even_harmonic_db : 0.0;
    if (c->even_db_set && c->even_harmonic_db_per_octave != 0.0)
        s->even_harmonic_db = c->even_harmonic_db + c->even_harmonic_db_per_octave * op;
    double touch = (c->touch_sensitive || !c->fixed_touch) ? attack_volume : 1.0;
    s->gain = (c->initial_gain * pow(10.0, c->octave_gain * op / 20.0)
               * pow(10.0, (register_effort_at(c, s->frequency_x * pow(2.0, op)) + c->projection_db) / 20.0)
               * touch * channel_volume);
    /* place() */
    o->pan_angle = stage_angle(channel_pan);
    s->position_x = op * c->octave_width + c->seat_x;
    s->position_z = c->position_z;
    s->hrtf_beta = 2.0 * c->sound_speed / c->head_radius;
    double e[4];
    voice_hrtf_at(c, o->pan_angle, s->position_x, e);
    o->left_incidence = e[0]; o->right_incidence = e[1];
    o->left_hrtf_delay = e[2]; o->right_hrtf_delay = e[3];
    /* GrandPianoProperties: the key's own strings and pitch error */
    int midi = (int)rint(69.0 + 12.0 * log(frequency / 440.0) / log(2.0));
    PyRandom r;
    pyr_seed(&r, midi);
    s->unison_key = midi;
    s->n_detune = 2;
    s->note_detune_cents[0] = -pyr_uniform(&r, c->detune_lo, c->detune_hi);
    s->note_detune_cents[1] = pyr_uniform(&r, c->detune_lo, c->detune_hi);
    s->note_detune_cents[2] = s->note_detune_cents[3] = 0.0;
    if (c->key_jitter && c->pitch_jitter_cents != 0.0)
        o->pitch_jitter = pow(2.0, pyr_uniform(&r, -c->pitch_jitter_cents, c->pitch_jitter_cents) / 1200.0) - 1.0;
    s->soft_pedal_down = c->soft_pedal_down;
    o->attack_time = c->attack_time;
    if (c->upright) {
        o->attack_time = c->hammer_soft_s + (c->hammer_hard_s - c->hammer_soft_s) * attack_volume;
        int n = c->n_level;
        if (n) {
            double f = frequency, db = 0.0;
            if (f <= c->level_hz[0])
                db = c->level_db[0];
            else if (f >= c->level_hz[n - 1])
                db = c->level_db[n - 1];
            else
                for (int i = 0; i + 1 < n; i++)
                    if (f < c->level_hz[i + 1]) {
                        double f0 = c->level_hz[i], d0 = c->level_db[i], f1 = c->level_hz[i + 1];
                        db = d0 + (c->level_db[i + 1] - d0) * log(f / f0) / log(f1 / f0);
                        break;
                    }
            s->gain *= pow(10.0, db / 20.0);
        }
    }
    /* blockrender: the law's B at the note (inharmonicity_coefficient_for_frequency) */
    double x = frequency;
    if (c->b_law == 1) {
        o->B = frequency < c->break_hz ? c->wound_k * pow(x, c->wound_p) : c->plain_k * pow(x, c->plain_p);
    } else {
        o->B = c->ia + c->ib * x + c->ic * x * x + (c->id / x) + (c->ie / (x * x));
        if (c->b_law == 2) {
            double f = pymax(x, 1e-6);
            double long_ = pymin(c->scale_constant_hz_m / f, c->reference_string_max_m);
            double short_ = pymin(c->scale_constant_hz_m / f, c->case_string_max_m);
            o->B = o->B * pow(long_ / short_, 4.0);
        }
    }
}
