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
#include <stdlib.h>
#include <string.h>
#include "nv.h"
#include "pycompat.h"
#include "../roomcore.c"        /* air_db, directivity_gain: the room's, shared */


/* tonelib.db_ratio */
static double db_ratio(double db)
{
    double x = 3000.0 < db ? 3000.0 : db;      /* min(db, 3000.0) */
    return pow(10.0, x / 10.0);
}

/* KitDrumProperties._click: the band and frequency of partial `harmonic`
 * if it is one of the stick's, else 0 */
static int drum_click(const VoiceSnap *v, int harmonic, int *band, double *hz)
{
    int j = harmonic - v->n_modes - 1;
    if (j < 0)
        return 0;
    int b = j / v->click_per_band, k = j % v->click_per_band;
    if (b >= v->n_click)
        return 0;
    double x;
    if (v->click_scatter != 0.0) {
        /* anywhere in the band, by a hash of (band, partial) */
        unsigned long long hv = ((unsigned long long)(b * 1000003LL + k * 7919LL + 12345LL) * 2654435761ULL)
                                % 4294967296ULL;
        double h = (double)hv / 4294967296.0;
        x = (h - 0.5) * v->click_scatter
            + (1.0 - v->click_scatter) * ((k + 0.5) / v->click_per_band - 0.5);
    } else {
        x = (k + 0.5) / v->click_per_band - 0.5
            + 0.3 * (fmod((b * 7 + k * 13) * 0.6180339887, 1.0) - 0.5) / v->click_per_band;
    }
    *band = b;
    *hz = v->click_hz0 * pow(2.0, (b + x) / 3.0);
    return 1;
}

/* NoisyPercussionMixin._hf_rolloff at ratio h */
static double hf_rolloff(const VoiceSnap *v, double h)
{
    double fn = v->frequency_x * pow(2.0, v->octave_position) * h;
    return 1.0 / (1.0 + pow(fn / v->hf_corner_hz, v->hf_order));
}

double nv_mode_ratio(const VoiceSnap *v, int m);

/* NoisyPercussionMixin._band_trim */
static double band_trim(const VoiceSnap *v, int harmonic)
{
    if (!v->n_trim)
        return 1.0;
    double f = v->pap_hz != 0.0 && harmonic <= v->pap_n
                   ? v->pap_hz * nv_mode_ratio(v, harmonic)      /* PlayedAtPitchMixin: the recorded pitch's */
                   : v->frequency_x * pow(2.0, v->octave_position) * nv_mode_ratio(v, harmonic);
    int n = v->n_trim;
    double db = 0.0;
    if (f <= v->trim[0][0])
        db = v->trim[0][1];
    else if (f >= v->trim[n - 1][0])
        db = v->trim[n - 1][1];
    else
        for (int i = 0; i + 1 < n; i++)
            if (f < v->trim[i + 1][0]) {
                double f0 = v->trim[i][0], d0 = v->trim[i][1], f1 = v->trim[i + 1][0], d1 = v->trim[i + 1][1];
                db = d0 + (d1 - d0) * log(f / f0) / log(f1 / f0);
                break;
            }
    return pow(10.0, db / 20.0);
}

/* AcousticSnareProperties.partial_jitter (the head's, the wires'),
 * MeasuredStrokeProperties' (the modes', the rest's) */
double nv_partial_jitter(const VoiceSnap *v, int harmonic)
{
    int from = v->jit_from ? v->jit_from : v->n_modes + 1;     /* CuicaProperties: rough_from */
    return harmonic >= from ? v->wire_jitter : v->head_jitter;
}

/* MeasuredStrokeProperties.stroke_scatter_db: the weaker modes' spread,
 * held under the strongest */
double nv_stroke_scatter_db(const VoiceSnap *v, int harmonic)
{
    if (v->tamb)                                /* TambourineProperties: the jingles' alike */
        return harmonic <= v->n_modes ? v->mode_scatter_db : 0.0;
    double g = harmonic <= v->n_modes ? v->modes[harmonic - 1][1] : 0.0;
    if (harmonic > v->n_modes || g > -6.0)
        return 0.0;
    double c = -g / 2.5;
    return c < v->mode_scatter_db ? c : v->mode_scatter_db;
}

/* SynthProperties._blend_db: a and b blended w of the way from b to a, in dB */
static double blend_db(double a, double b, double w)
{
    if (w <= 0.0)
        return b;
    if (w >= 1.0)
        return a;
    return pow(a > 1e-12 ? a : 1e-12, w) * pow(b > 1e-12 ? b : 1e-12, 1.0 - w);
}

/* SynthProperties.mode_gains_at: an organ pipe's table for a sound at f --
   its anchors' tables blended along log frequency, or its low register's
   blended in; into out (64), the count returned */
int nv_mode_gains_at(const VoiceSnap *v, double f, double *out)
{
    if (v->n_pts) {
        int last = v->n_pts - 1;
        if (f <= v->pts_hz[0] || f >= v->pts_hz[last]) {
            int i = f <= v->pts_hz[0] ? 0 : last;
            for (int h = 0; h < v->pts_n[i]; h++)
                out[h] = v->pts_g[i][h];
            return v->pts_n[i];
        }
        for (int i = 0; i < last; i++) {
            double fa = v->pts_hz[i], fb = v->pts_hz[i + 1];
            if (f <= fb) {
                double w = log(fb / f) / log(fb / fa);
                int n = v->pts_n[i] > v->pts_n[i + 1] ? v->pts_n[i] : v->pts_n[i + 1];
                for (int h = 0; h < n; h++) {
                    double x = v->pts_g[i][h], y = v->pts_g[i + 1][h];
                    out[h] = (x != 0.0 || y != 0.0) ? blend_db(x, y, w) : 0.0;
                }
                return n;
            }
        }
    }
    if (!v->low_set) {
        for (int h = 0; h < v->n_pipe; h++)
            out[h] = v->pipe_g[h];
        return v->n_pipe;
    }
    double lo = v->low_hz[0], hi = v->low_hz[1], w;
    if (f <= lo)
        w = 1.0;
    else if (f >= hi)
        w = 0.0;
    else
        w = log(hi / f) / log(hi / lo);
    int n = v->n_pipe > v->n_low ? v->n_pipe : v->n_low;
    for (int h = 0; h < n; h++) {
        double l = h < v->n_low ? v->low_g[h] : 0.0, x = h < v->n_pipe ? v->pipe_g[h] : 0.0;
        out[h] = (l != 0.0 || x != 0.0) ? blend_db(l, x, w) : 0.0;
    }
    return n;
}

/* ElectricPianoProperties._deflection: the swing at the strike, as velocity
   (attack_volume's root) to its power, wider down the keyboard, capped */
static double ep_deflection(const VoiceSnap *v)
{
    double av = v->attack_volume > 1e-4 ? v->attack_volume : 1e-4;
    double a = v->ep_defl * pow(2.0, v->ep_defl_slope * v->octave_position) * pow(sqrt(av), v->ep_defl_power);
    return a < v->ep_defl_max ? a : v->ep_defl_max;
}

/* ElectricPianoProperties._level_law: the level following velocity, not its square */
static double ep_level_law(const VoiceSnap *v)
{
    double av = v->attack_volume > 1e-4 ? v->attack_volume : 1e-4;
    if (v->ep_defl_power == 1.0)
        return 1.0 / av;
    double fr = v->ep_defl * pow(2.0, v->ep_defl_slope * v->octave_position);
    double d = ep_deflection(v);
    double undo = sqrt(av) * fr / (d > 1e-9 ? d : 1e-9);
    return pow(undo, 1.0 - v->ep_share) / av;
}

/* TubularBellProperties._tube_oct: the note's octaves from tube_ref_hz, held */
static double tube_oct(const VoiceSnap *v)
{
    double f = v->frequency_x * pow(2.0, v->octave_position);
    double x = log(f / v->tube_ref_hz) / log(2.0);
    double lo = x < 0.85 ? x : 0.85;
    return lo > -0.6 ? lo : -0.6;
}

double nv_mode_ratio(const VoiceSnap *v, int m)
{
    if (v->kind == 2 && v->n_tube)              /* TubularBellProperties.mode_ratio: a line in octaves */
        return 1 <= m && m <= v->n_tube ? v->tube[m - 1][0] + v->tube[m - 1][1] * tube_oct(v) : 0.0;
    if (v->kind == 5)                           /* SynthProperties.mode_ratio: the note's layers, the tonebar's */
        return 1 <= m && m <= v->n_lay + v->n_tb ? v->ep_r[m - 1] : 0.0;
    if (v->kind == 2 && v->mr_law == 1) {       /* BalafonProperties.mode_ratio: the upper modes by octave */
        if (m == 1)
            return 1.0;
        if (2 <= m && m <= 3) {
            double oc = log(v->frequency_x * pow(2.0, v->octave_position) / v->mr_ref) / log(2.0);
            double x = v->mr_a[m - 2] + v->mr_b[m - 2] * oc;
            return x > v->mr_lo[m - 2] ? x : v->mr_lo[m - 2];     /* max(lo, a + b oc) */
        }
        return 0.0;
    }
    if (v->kind == 2 && v->mr_law == 2) {       /* LogDrumProperties.mode_ratio: the body's modes in Hz */
        if (1 <= m && m <= 3)
            return (double)m;
        if (4 <= m && m <= 6)
            return v->mr_body[m - 4] / (v->frequency_x * pow(2.0, v->octave_position));
        if (m == 7)
            return v->mr_body[0] / (v->frequency_x * pow(2.0, v->octave_position));
        return 0.0;
    }
    if (v->kind == 2 && v->mm_harm)             /* SynthProperties.mode_ratio: mode_ratios None */
        return (double)m;
    if (v->kind == 2)                           /* SynthProperties.mode_ratio: mode_ratios */
        return 1 <= m && m <= v->n_mm ? v->mm_ratio[m - 1] : 0.0;
    if (v->kind == 1) {                         /* KitDrumProperties.mode_ratio */
        if (1 <= m && m <= v->n_modes) {
            double r = v->modes[m - 1][0];
            if (v->throat) {                    /* SfxThroatProperties': the vowel moved, the mouth */
                if (v->formant_morph != 0.0 && v->n_mb)
                    r *= pow(v->mb[m - 1][0] / v->modes[m - 1][0], v->formant_morph);
                if (v->formant_scale != 1.0)
                    return r * v->formant_scale;
            }
            return r;
        }
        int b;
        double hz;
        return drum_click(v, m, &b, &hz) ? hz / (v->frequency_x * pow(2.0, v->octave_position)) : 0.0;
    }
    return (double)m;                           /* mode_ratios None */
}

/* SynthProperties.pickup_gain: what the coils read of string mode h (of a
   touched harmonic's string, its touch under the note) */
/* SynthProperties.series_volume's LOW PASS where a voice has no pickup (a
   Mellotron's tape: lowpass_hz, lowpass_order x 6 dB/octave above it): the
   divisor at string mode sm's frequency */
static double lp_div(const VoiceSnap *v, int sm)
{
    double f = v->frequency_x * pow(2.0, v->octave_position) * sm / (v->touch ? v->touch : 1);
    return pow(1.0 + pow(f / v->lp_hz, 2.0 * v->lp_order), 0.5);
}

static double eg_pickup_gain(const VoiceSnap *v, int h)
{
    double t[4];
    for (int i = 0; i < v->n_pk; i++)
        t[i] = v->pk_sign[i] * sin(h * PI * v->pk_q[i]);
    double g = fabs(pysum(t, v->n_pk));
    if (v->pk_turns != 1.0)
        g *= v->pk_turns;
    if (v->pk_width != 0.0) {
        double x = h * PI * v->pk_width;
        if (x > 1e-9)
            g *= fabs(sin(x) / x);
    }
    if (v->pk_vel)
        g *= h;
    double f = v->frequency_x * pow(2.0, v->octave_position) * h / (v->touch ? v->touch : 1);
    if (v->pk_res_hz != 0.0) {                  /* _two_pole, the coil's load */
        double x = f / v->pk_res_hz;
        g *= 1.0 / sqrt(pow(1.0 - x * x, 2.0) + pow(x / v->pk_qf, 2.0));
    }
    if (v->lp_hz != 0.0)
        g /= pow(1.0 + pow(f / v->lp_hz, 2.0 * v->lp_order), 0.5);
    return g;
}

double nv_series_volume(const VoiceSnap *v, int harmonic)
{
    if (v->n_hvt) {                             /* SynthProperties: mode_gains, a played pipe's measured series */
        if (v->max_harmonic && harmonic > v->max_harmonic)
            return 0.0;
        return (1 <= harmonic && harmonic <= v->n_hvt) ? v->gain * v->hvt[harmonic - 1] : 0.0;
    }
    if (v->kind == 5) {                         /* ElectricPianoProperties: a layer's weight, the tonebar's */
        if (harmonic < 1 || harmonic > v->n_lay + v->n_tb)
            return 0.0;
        double x = harmonic > v->n_lay ? v->tb_g[harmonic - v->n_lay - 1] * ep_deflection(v)
                                       : fabs(v->ep_w[harmonic - 1]);
        return v->gain * x * ep_level_law(v);
    }
    if (v->kind == 2 && v->n_tube) {            /* TubularBellProperties: each mode's level, a line in octaves */
        if (harmonic < 1 || harmonic > v->n_tube)
            return 0.0;
        return v->gain * pow(10.0, (v->tube[harmonic - 1][2] + v->tube[harmonic - 1][3] * tube_oct(v)) / 20.0);
    }
    if (v->kind == 2 && v->n_bar) {             /* TunedBarProperties: the bar's own modes */
        for (int i = 0; i < v->n_bar; i++)
            if (harmonic == v->bar_n[i])
                return v->gain * v->bar_g[i];
        return 0.0;
    }
    if (v->kind == 2 && (v->n_mm || v->or_set)) {   /* SynthProperties: a measured mode set (none: its series) */
        if (v->max_harmonic && harmonic > v->max_harmonic)
            return 0.0;
        if (v->or_set && harmonic == 7)         /* MusicBoxProperties: its key's octave below */
            return v->gain * v->or_g;
        double g;
        if (v->mm_pts) {                        /* mode_gains_here: the register's tables at the note's pitch */
            double here[64];
            int n = nv_mode_gains_at(v, v->frequency_x * pow(2.0, v->octave_position), here);
            if (!(1 <= harmonic && harmonic <= n))
                return 0.0;
            g = v->gain * here[harmonic - 1];
        } else {
            if (!(1 <= harmonic && harmonic <= v->n_mm))
                return 0.0;
            g = v->gain * v->mm_gain[harmonic - 1];
        }
        if (v->mst != 0.0) {                    /* a stroke's tilt: harder, toward the top */
            double av = v->attack_volume > 1e-6 ? v->attack_volume : 1e-6;    /* max(attack_volume, 1e-6) */
            double sdb = 20.0 * log(av) / log(10.0);
            if (!(sdb > -40.0))
                sdb = -40.0;                    /* max(-40, ...) */
            g *= pow(10.0, v->mst * log(nv_mode_ratio(v, harmonic)) / log(2.0) * (sdb - v->mst_ref) / 20.0);
        }
        return g;
    }
    if (v->kind == 1) {                         /* KitDrumProperties.series_volume */
        if (1 <= harmonic && harmonic <= v->n_modes)
            return v->gain * pow(10.0, v->modes[harmonic - 1][1] / 20.0);
        int b;
        double hz;
        if (!drum_click(v, harmonic, &b, &hz))
            return 0.0;
        /* _stroke_db: the stroke's dB against the drum's reference */
        double av = v->attack_volume > 1e-6 ? v->attack_volume : 1e-6;
        double sd = 20.0 * log(av) / log(10.0);
        sd = (sd > -40.0 ? sd : -40.0) - v->stroke_ref_db;
        double db = v->click_db[b] + v->click_cal_db + v->click_stroke_slope * sd;
        return v->gain * pow(10.0, db / 20.0) / pow((double)v->click_per_band, 0.5);
    }
    if (v->max_harmonic && harmonic > v->max_harmonic)
        return 0.0;
    if (harmonic % 2 == 0 && !v->even_db_set && v->odd_only)
        return 0.0;
    if (v->kind == 4 && v->reed) {              /* FreeReedProperties: the flow spectrum */
        if (harmonic >= v->n_reed)
            return 0.0;
        double r = v->gain * v->reed_s[harmonic];
        if (harmonic % 2 == 0 && v->even_db_set)
            r *= pow(10.0, v->even_harmonic_db / 20.0);
        double q = v->reed_scatter + v->reed_scatter_oct * v->octave_position;
        if (v->reed_scatter != 0.0 && q > 0.0 && harmonic > 1) {
            /* each key's harmonics scattered, Random(k 7919 + h 104729 + 17).expovariate(1) */
            long long k = (long long)nearbyint(12.0 * v->octave_position);
            PyRandom R;
            pyr_seed(&R, k * 7919 + (long long)harmonic * 104729 + 17);
            double e = -log(1.0 - pyr_random(&R)) / 1.0;
            r *= sqrt(pow(e, q) / tgamma(1.0 + q));
        }
        return r;
    }
    if (v->kind == 4 && v->elec && v->fc_tab) {     /* FretContact.series_volume: the baked stroke, the coils */
        if ((v->max_harmonic && harmonic > v->max_harmonic) || harmonic > v->n_fc)
            return 0.0;
        double r = v->gain * v->fc_amp[harmonic - 1];
        r *= eg_pickup_gain(v, harmonic);
        if (harmonic % 2 == 0 && v->even_db_set)
            r *= pow(10.0, v->even_harmonic_db / 20.0);
        return r;
    }
    if (v->kind == 4 && v->elec) {              /* ElectricGuitarProperties: the pick's comb, the coils */
        /* (a touched harmonic's partial m is string mode m times the touch) */
        int sm = v->touch ? harmonic * v->touch : harmonic;
        if (v->touch && v->max_harmonic && sm > v->max_harmonic)
            return 0.0;
        double comb = (1.0 - v->eg_depth) + v->eg_depth * fabs(sin(sm * PI * v->pk_sp));
        double r = v->gain / pow((double)sm, v->attack_dampening) * comb;
        r *= eg_pickup_gain(v, sm);
        if (harmonic % 2 == 0 && v->even_db_set)
            r *= pow(10.0, v->even_harmonic_db / 20.0);
        return r;
    }
    if (v->kind == 4 && v->strike_point != 0.0) {   /* a quill's strike comb (no fill: a plectrum) */
        double comb = (1.0 - v->strike_depth) + v->strike_depth * fabs(sin(harmonic * PI * v->strike_point));
        double r = v->gain / pow((double)harmonic, v->attack_dampening) * comb;
        if (v->lp_hz != 0.0 && !v->elec)
            r /= lp_div(v, harmonic);
        if (harmonic % 2 == 0 && v->even_db_set)
            r *= pow(10.0, v->even_harmonic_db / 20.0);
        return r;
    }
    if (v->kind == 4 || v->kind == 6 || v->kind == 2) {     /* SynthProperties': the pluck's comb (a Moog's body's norm; a pipe's with no table) */
        double r = v->gain / pow((double)harmonic, v->attack_dampening) * (harmonic <= 256 ? v->comb[harmonic] : 0.0);
        if (v->lp_hz != 0.0 && !v->elec)
            r /= lp_div(v, harmonic);
        if (harmonic % 2 == 0 && v->even_db_set)
            r *= pow(10.0, v->even_harmonic_db / 20.0);
        return r;
    }
    if (v->kind == 3) {                         /* the pluck comb at plucked_harmonic 0: whole */
        double r = v->gain / pow((double)harmonic, v->attack_dampening) * (harmonic % 1000000 ? 1.0 : 0.0);
        if (v->lp_hz != 0.0 && !v->elec)
            r /= lp_div(v, harmonic);
        return r;
    }
    int sm = harmonic;                          /* harmonic_touch 0 */
    double depth = v->strike_depth;
    if (v->strike_fills)
        depth *= (1.0 - v->strike_fill_fraction * v->attack_volume);
    double comb = (1.0 - depth) + depth * fabs(sin(sm * PI * v->strike_point));
    double r = v->gain / pow((double)sm, v->attack_dampening) * comb;
    if (v->lp_hz != 0.0 && !v->elec)
        r /= lp_div(v, sm);
    if (harmonic % 2 == 0 && v->even_db_set)
        r *= pow(10.0, v->even_harmonic_db / 20.0);
    return r;
}

/* a (Hz, dB) table at f, log-interpolated, held flat past its ends
   (FormantBody._body_trim) */
static double db_table(const double (*pts)[2], int n, double f)
{
    double db = 0.0;
    if (f <= pts[0][0])
        db = pts[0][1];
    else if (f >= pts[n - 1][0])
        db = pts[n - 1][1];
    else
        for (int i = 0; i + 1 < n; i++)
            if (f < pts[i + 1][0]) {
                double f0 = pts[i][0], d0 = pts[i][1], f1 = pts[i + 1][0], d1 = pts[i + 1][1];
                db = d0 + (d1 - d0) * log(f / f0) / log(f1 / f0);
                break;
            }
    return pow(10.0, db / 20.0);
}

/* SynthProperties.bore_gain; FormantBody's (fbody): the floor, each
   resonance and antiresonance, the mouth's roll-off, the bell, the trim */
static double bore_gain(const VoiceSnap *v, double partial_hz)
{
    if (v->fbody) {
        double g = v->formant_floor;
        for (int i = 0; i < v->n_fm; i++) {
            double d = (partial_hz - v->fm[i][0]) / (v->fm[i][1] * 0.5);
            g += v->fm[i][2] / (1.0 + d * d);
        }
        for (int i = 0; i < v->n_afm; i++) {
            double d = (partial_hz - v->afm[i][0]) / (v->afm[i][1] * 0.5);
            g *= 1.0 - v->afm[i][2] / (1.0 + d * d);
        }
        g /= 1.0 + pow(partial_hz / v->bore_corner_hz, v->bore_order);
        if (v->bell_cutoff_hz != 0.0) {
            double x = pow(partial_hz / v->bell_cutoff_hz, v->bell_order);
            g *= x / (1.0 + x);
        }
        if (v->n_bt)
            g *= db_table(v->bt, v->n_bt, partial_hz);
        return g;
    }
    double g = 1.0;
    if (v->bore_corner_hz != 0.0)
        g /= 1.0 + pow(partial_hz / v->bore_corner_hz, v->bore_order);
    if (v->bell_cutoff_hz != 0.0) {
        double x = pow(partial_hz / v->bell_cutoff_hz, v->bell_order);
        g *= x / (1.0 + x);
    }
    if (v->n_mute && partial_hz > 0.0) {
        /* the mute's response (MutedTrumpetProperties.bore_gain) */
        const double (*t)[2] = v->mute;
        int n = v->n_mute;
        double x = log(partial_hz), db = 0.0;
        if (partial_hz <= t[0][0])
            db = t[0][1];
        else if (partial_hz >= t[n - 1][0])
            db = t[n - 1][1];
        else
            for (int i = 0; i + 1 < n; i++)
                if (partial_hz <= t[i + 1][0]) {
                    double f0 = t[i][0], d0 = t[i][1], f1 = t[i + 1][0], d1 = t[i + 1][1];
                    db = d0 + (d1 - d0) * (x - log(f0)) / (log(f1) - log(f0));
                    break;
                }
        g *= pow(10.0, db / 20.0);
    }
    return g;
}

/* GrandPianoProperties.soundboard_gain */
/* soundboard_gain: the grand's board (board_kind 0); the upright's, its low
 * roll-off of its own order (1); the electric grand's bridge and piezo (2) */
static double soundboard_gain(const VoiceSnap *v, double fn)
{
    if (v->board_kind == 2) {
        double slope = 1.0;
        if (v->bridge_force_power != 0.0) {
            double f0 = v->frequency_x * pow(2.0, v->octave_position);
            double r = fn / (f0 > 1e-9 ? f0 : 1e-9);
            slope = pow(1.0 > r ? 1.0 : r, v->bridge_force_power);     /* max(r, 1.0) */
        }
        double g = v->bridge_gain * slope / (1.0 + pow(fn / v->bridge_corner_hz, v->bridge_order));
        if (v->bridge_peak_db != 0.0)           /* the piezo's resonance */
            g = g * (1.0 + (pow(10.0, v->bridge_peak_db / 20.0) - 1.0) * exp(
                -(pow(log(fn / v->bridge_peak_hz), 2.0)) / (2.0 * pow(v->bridge_peak_width, 2.0))));
        return g;
    }
    double body = 1.0 + v->board_body_gain * exp(
        -(pow(log(fn / v->board_body_hz), 2.0)) / (2.0 * pow(v->board_body_width, 2.0)));
    double high = 1.0 / (1.0 + pow(fn / v->board_high_hz, v->board_high_order));
    double low = 1.0 / (1.0 + pow(v->board_low_hz / fn,
                                  (v->board_kind == 1 || v->board_low_order > 0.0) ? v->board_low_order : 2.0));
    double g = body * high * low;
    if (v->board_kind == 0 && v->lid_db != 0.0)       /* the open lid */
        g = g * (1.0 + (pow(10.0, v->lid_db / 20.0) - 1.0) / (1.0 + pow(v->lid_hz / fn, v->lid_order)));
    return g;
}

/* Plectrum._pick_db: the pick's boost on partial m, dB (0 under pick_hz) */
static double pick_db(const VoiceSnap *v, int m)
{
    double f = v->frequency_x * pow(2.0, v->octave_position) * m;
    if (f <= v->pick_hz)
        return 0.0;
    double b = v->pick_slope_db * log2(f / v->pick_hz);
    return b < v->pick_boost_max_db ? b : v->pick_boost_max_db;   /* (min(max, b)) */
}

static double harmonic_volume(const VoiceSnap *v, int harmonic);

/* the voice's harmonic_volume -- a throat's tilted and its vowel moved --
   and SampledBreak's: nothing at or above its Nyquist */
double nv_harmonic_volume_base(const VoiceSnap *v, int harmonic)
{
    double s = harmonic_volume(v, harmonic);
    if (v->pick_set) {                          /* Plectrum: the pick's boost over pick_hz */
        double b = pick_db(v, harmonic);
        if (b > 0.0)
            s = s * pow(10.0, b / 20.0);
    }
    if (v->throat && harmonic <= v->n_modes) {
        /* SfxThroatProperties': the vowel's levels moved, the pulse tilted */
        if (v->formant_morph != 0.0 && s != 0.0 && v->n_mb)
            s *= pow(10.0, v->formant_morph * (v->mb[harmonic - 1][1] - v->modes[harmonic - 1][1]) / 20.0);
        if (v->stroke_tilt_db != 0.0 && s != 0.0) {
            double hz = 1000.0 * v->modes[harmonic - 1][0];
            if (hz > 1000.0)
                s *= pow(10.0, 0.5 * v->stroke_tilt_db * log(hz / 1000.0) / log(2.0) / 20.0);
        }
    }
    if (v->nyquist != 0.0 && !(v->frequency_x * pow(2.0, v->octave_position) * nv_mode_ratio(v, harmonic) < v->nyquist))
        return 0.0;
    return s;
}

/* ...THE TAISHOGOTO'S LOW STRING DARKER (TaishoKotoProperties.harmonic_volume:
   its harmonics falling crs_ltilt dB an octave more than the trio's) */
double nv_harmonic_volume(const VoiceSnap *v, int harmonic)
{
    double s = nv_harmonic_volume_base(v, harmonic);
    if (v->crs_ltilt != 0.0 && harmonic > 1)
        s = s * pow(10.0, -v->crs_ltilt * log2((double)harmonic) / 20.0);
    return s;
}

/* SynthProperties._blare: a dynamic's change above the knee, dB per kHz, capped */
static double blare(const VoiceSnap *v, double hz)
{
    double x = hz - v->blare_knee_hz;           /* (Python's max and min: the first unless the second is past it) */
    double d = v->blare_db_per_khz * (x > 0.0 ? x : 0.0) / 1000.0;
    double c = d < v->blare_cap_db ? d : v->blare_cap_db;
    d = c > -v->blare_cap_db ? c : -v->blare_cap_db;
    return pow(10.0, d / 20.0);
}

/* hammer.string_of's impedance sqrt(T mu): L = C/f to the case's longest, the
   wound bass's higher tension, mu from f = sqrt(T/mu) / 2L */
static double string_z(double f0, double scale_c, double lmax)
{
    double L = (lmax < scale_c / f0 ? lmax : scale_c / f0);
    double T = f0 < 110.0 ? 1100.0 : 750.0;
    double c = 2.0 * L * f0;
    double mu = T / (c * c);
    return sqrt(T * mu);
}

/* ElectricGrandProperties._wound_weight: 0 above the break or with no term */
static double wound_weight(const VoiceSnap *v, int harmonic)
{
    double f0 = v->frequency_x * pow(2.0, v->octave_position);
    if (v->board_kind != 2 || v->wound_below_hz <= 0.0 || f0 >= v->wound_below_hz)
        return 0.0;
    double fn = f0 * harmonic;
    return 1.0 / (1.0 + pow(v->wound_corner_hz / fn, 2.0));
}

/* GrandPianoProperties.harmonic_volume, on SynthProperties' (no bore) */
static double harmonic_volume(const VoiceSnap *v, int harmonic)
{
    if (v->n_hvt && !v->hvt_bore)               /* a measured series: the table, nothing past it */
        return harmonic <= v->n_hvt ? v->gain * v->hvt[harmonic - 1] : 0.0;
    double s = nv_series_volume(v, harmonic);
    if (s == 0.0)
        return 0.0;
    if (v->kind != 0) {                         /* SynthProperties': its bore, if it has one */
        if (v->bore_corner_hz != 0.0) {
            s = s * bore_gain(v, v->frequency_x * pow(2.0, v->octave_position) * nv_mode_ratio(v, harmonic))
                * v->bore_norm;
            if (v->blare_db_per_khz != 0.0)     /* ...and its blare, renormalised */
                s *= blare(v, v->frequency_x * pow(2.0, v->octave_position) * nv_mode_ratio(v, harmonic))
                     * v->blare_norm;
        }
        if (v->noisy)                           /* ...and the noise's roll-off and trim */
            return s * hf_rolloff(v, nv_mode_ratio(v, harmonic)) * band_trim(v, harmonic);
        return s;
    }
    double fn = v->frequency_x * pow(2.0, v->octave_position) * harmonic;
    double r;
    if (v->hammer_model) {                      /* GrandPianoProperties': the simulated hammer's share */
        r = s * (harmonic - 1 < v->hm_n ? v->hm_g[harmonic - 1] : 0.0) * soundboard_gain(v, fn);
    } else {
        double av = v->hammer_open_power == 1.0 ? v->attack_volume : pow(v->attack_volume, v->hammer_open_power);
        double fc = (v->hammer_corner_hz * (v->hammer_open_lo + v->hammer_open_slope * av)
                     * pow(2.0, v->hammer_register_slope * v->octave_position));
        r = s / (1.0 + pow(fn / fc, v->hammer_order)) * soundboard_gain(v, fn);
    }
    double w = wound_weight(v, harmonic);       /* ElectricGrandProperties': the wound strings' zing */
    return w != 0.0 ? r * pow(10.0, v->wound_zing_db * v->attack_volume * w / 20.0) : r;
}

/* SynthProperties.harmonic_decay by where the mode sits; CymbalProperties'
 * by octaves from the ring's peak */
static double mode_decay(const VoiceSnap *v, int harmonic)
{
    if (v->church && 1 <= harmonic && harmonic <= v->n_md) {   /* ChurchBellProperties: half, by its slope */
        double f = v->frequency_x * pow(2.0, v->octave_position);
        return v->mode_decays[harmonic - 1] / 2.0 * pow(2.0, v->church_slope * log(f / v->tube_ref_hz) / log(2.0));
    }
    if (v->n_md && 1 <= harmonic && harmonic <= v->n_md)   /* ModeDecays */
        return v->mode_decays[harmonic - 1] * v->decay_register_factor;
    if (v->cymbal && v->ring_peak_hz > 0.0) {
        double f = v->frequency_x * pow(2.0, v->octave_position) * nv_mode_ratio(v, harmonic);
        if (f > 0.0) {
            double o = log(f / v->ring_peak_hz) / log(2.0);
            double k = o < 0.0 ? v->ring_decay_below : v->ring_decay_above;
            return (v->ring_decay_floor + k * o * o) * v->decay_register_factor;
        }
    }
    double h = nv_mode_ratio(v, harmonic);
    return (v->decay_db + v->harmonic_decay_db * h * pow(h, v->harmonic_decay_dampening)) * v->decay_register_factor;
}

static double harmonic_decay_(const VoiceSnap *v, int harmonic);
static double sp_decay(const VoiceSnap *v, int harmonic);
static double pymin(double a, double b);
static double pymax(double a, double b);

double nv_harmonic_decay(const VoiceSnap *v, int harmonic)
{
    double base = harmonic_decay_(v, harmonic);
    if (v->pick_set && pick_db(v, harmonic) > 0.0)  /* Plectrum: the boost's fast fall */
        return v->pick_dbs > base ? v->pick_dbs : base;
    return base;
}

/* the voice's own decay, under a pick's */
static double harmonic_decay_(const VoiceSnap *v, int harmonic)
{
    if (v->dhz_set) {                           /* HammeredDulcimerProperties: by the mode's own frequency */
        double f = v->frequency_x * pow(2.0, v->octave_position) * harmonic;
        return 0.5 * (v->decay_db + v->dhz_db * pow(f / 1000.0, v->dhz_pow));
    }
    if (v->kind == 5) {                         /* ElectricPianoProperties: n D for the term A^n; the tonebar's tick */
        if (harmonic > v->n_lay)
            return v->tb_decay;
        return v->harmonic_decay_db * v->ep_n[harmonic - 1] * v->decay_register_factor;
    }
    if (v->kind == 2) {                         /* a mode set's, a key's retargeted */
        double base = mode_decay(v, harmonic);
        if (!v->retarget)
            return base;
        double first = mode_decay(v, 1);
        return first > 0 ? base * (v->decay_target / first) : v->decay_target;
    }
    if (v->kind == 1 && v->measured && 1 <= harmonic && harmonic <= v->n_modes)
        return 0.5 * v->ring_scale * v->modes[harmonic - 1][2];  /* MeasuredStrokeProperties' ring */
    if (v->kind == 1 && v->rim_from && v->rim_from <= harmonic && harmonic <= v->n_modes)
        return 0.5 * v->rim_dbs;                /* SideStickProperties: the rim's */
    if (v->kind == 1 && v->snare) {             /* AcousticSnareProperties: the head's two rates */
        if (harmonic == 1)
            return 0.5 * v->fund_dbs;
        if (2 <= harmonic && harmonic <= v->n_modes)
            return 0.5 * v->head_dbs;
    }
    if (v->kind == 1) {                         /* KitDrumProperties: half the amplitude dB/s */
        if (1 <= harmonic && harmonic <= v->n_modes)
            return 0.5 * v->modes[harmonic - 1][2];
        int b;
        double hz;
        return drum_click(v, harmonic, &b, &hz) ? 0.5 * v->click_dbs : 0.0;
    }
    if (v->kind == 0 && v->decay_by_hz) {       /* GrandPianoProperties': by the partial's frequency */
        double f0 = v->frequency_x * pow(2.0, v->octave_position);
        double f = f0 * harmonic * pow(1.0 + v->dz_B * harmonic * harmonic, 0.5);
        double board = v->decay_board_db * v->dz_zr / (1.0 + pow(v->decay_board_hz / f, 2.0));
        if (v->decay_treble_power != 0.0 && f0 > 440.0)  /* the treble's thinner wire */
            board = board * pow(f0 / 440.0, v->decay_treble_power);
        if (v->decay_board_top_hz != 0.0)       /* the board letting go above its band */
            board = board / (1.0 + pow(f / v->decay_board_top_hz, 2.0));
        double d = v->decay_b1 + v->decay_b3 * pow(f / 1000.0, 2.0) + board;
        double w = wound_weight(v, harmonic);   /* ElectricGrandProperties': the wound top's faster fall */
        if (w != 0.0)
            return d + (v->wound_decay_by_force ? v->wound_decay_db * v->attack_volume : v->wound_decay_db) * w;
        return d;
    }
    if (v->sw_on) {                             /* SawariContact: the free silk's fall */
        double f = (double)harmonic * v->sw_f0;
        return 10.0 * (v->sw_sigma0 + v->sw_sigma2 * f * f) / log(10.0);
    }
    if (v->kind == 4 && v->elec && v->sp_decay) {    /* ElectricBassProperties: the string's physics */
        double slow = sp_decay(v, harmonic);
        if (v->fc_tab && harmonic <= v->n_fc && v->fc_share[harmonic - 1] < 1.0)
            return pymax(v->fc_fast[harmonic - 1], slow);   /* FretContact: the contact's fall */
        return slow;
    }
    double h = (double)harmonic;                /* mode_ratios None */
    double base = v->decay_db + v->harmonic_decay_db * h * pow(h, v->harmonic_decay_dampening);
    base = base * v->decay_register_factor;
    if (v->kind == 0) {                         /* ElectricGrandProperties': the wound top's faster fall */
        double w = wound_weight(v, harmonic);
        if (w != 0.0)
            return base + (v->wound_decay_by_force ? v->wound_decay_db * v->attack_volume : v->wound_decay_db) * w;
    }
    if (v->pd_max_hz != 0.0) {                  /* PromptDecay: the prompt fall under its corner */
        double f = v->frequency_x * pow(2.0, v->octave_position) * harmonic;
        if (f < v->pd_max_hz)
            return v->pd_dbs > base ? v->pd_dbs : base;     /* (max(base, prompt_dbs)) */
    }
    return base;
}

/* PromptDecay's ring: the law without the prompt fall */
static double prompt_ring(const VoiceSnap *v, int harmonic)
{
    double h = (double)harmonic;
    return (v->decay_db + v->harmonic_decay_db * h * pow(h, v->harmonic_decay_dampening)) * v->decay_register_factor;
}

/* tonelib._voice_partials: (Hz, amplitude) of the voice's first 24 modes
   (or its last), those that sound under 20 kHz */
static int sym_partials(const VoiceSnap *v, double *f, double *a)
{
    double f0 = v->frequency_x * pow(2.0, v->octave_position);
    int top = v->max_harmonic && v->max_harmonic < 24 ? v->max_harmonic : 24, n = 0;
    for (int h = 1; h <= top; h++) {
        double x = nv_harmonic_volume(v, h);
        if (x <= 0.0)
            continue;
        double fh = f0 * nv_mode_ratio(v, h);
        if (fh <= 0.0 || fh > 20000.0)
            continue;
        f[n] = fh;
        a[n] = x;
        n++;
    }
    return n;
}

double nv_sym_coupling(const VoiceSnap *drv, const VoiceSnap *rsp, double g, double wmin)
{
    if (g <= 0.0)
        return 0.0;
    double df[24], da[24], rf[24], ra[24];
    int nd = sym_partials(drv, df, da), nr = sym_partials(rsp, rf, ra);
    if (!nd || !nr)
        return 0.0;
    double ref = da[0];
    for (int i = 1; i < nd; i++)
        if (da[i] > ref)
            ref = da[i];
    if (ref == 0.0)
        ref = 1.0;
    double pa[24];
    int np = 0;
    for (int j = 1; j <= nr; j++) {
        /* _mode_bandwidth at the mode's PLACE among the partials (j): the
           ring, where the voice tells it from its prompt fall */
        double r = rsp->pd_max_hz != 0.0 ? prompt_ring(rsp, j) : nv_harmonic_decay(rsp, j);
        r = r > 1e-6 ? r : 1e-6;
        double tau = 8.685889638 / r;
        double bw = 1.0 / (2.0 * M_PI * tau);
        bw = wmin > bw ? wmin : bw;
        double d = 0.0;
        for (int i = 0; i < nd; i++) {
            double x = (df[i] - rf[j - 1]) / (bw > 1e-9 ? bw : 1e-9);
            d += (da[i] / ref) / (1.0 + x * x);
        }
        if (d > 0.0)
            pa[np++] = ra[j - 1] * g * d;
    }
    if (!np)
        return 0.0;
    double sq[24];
    for (int i = 0; i < nr; i++)
        sq[i] = ra[i] * ra[i];
    double nat = pysum(sq, nr);
    if (nat <= 0.0)
        return 0.0;
    for (int i = 0; i < np; i++)
        sq[i] = pa[i] * pa[i];
    return sqrt(pysum(sq, np) / nat);
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
    if (v->kind == 4 && v->aftersound_fraction > 0.0) {     /* PizzicatoStringsProperties': a slow share */
        out[0] = v->aftersound_fraction;
        out[1] = decay_rate * v->aftersound_ratio;
        return;
    }
    if (v->kind == 3 || v->kind == 4 || v->kind == 5) {     /* SynthProperties: one stage */
        out[0] = 0.0;
        out[1] = decay_rate;
        return;
    }
    if (v->kind == 2) {                         /* SynthProperties: one stage; CymbalProperties' */
        if (!v->cymbal || v->aftersound_fraction <= 0.0) {
            out[0] = 0.0;
            out[1] = decay_rate;
        } else if (v->aftersound_dbs > 0.0) {
            double s = 0.5 * v->aftersound_dbs;
            out[0] = v->aftersound_fraction;
            out[1] = s < decay_rate ? s : decay_rate;
        } else {
            out[0] = v->aftersound_fraction;
            out[1] = decay_rate * v->aftersound_ratio;
        }
        return;
    }
    if (v->kind == 1 && v->snare) {             /* AcousticSnareProperties: the shell's, on the head */
        double lo = v->fund_dbs < v->head_dbs ? v->fund_dbs : v->head_dbs;    /* min(fund, head) */
        if (v->slow_share <= 0.0 || decay_rate < 0.5 * lo - 1e-9) {
            out[0] = 0.0;
            out[1] = decay_rate;
        } else {
            double s = 0.5 * v->slow_dbs;
            out[0] = v->slow_share;
            out[1] = s < decay_rate ? s : decay_rate;
        }
        return;
    }
    if (v->kind == 1) {                         /* KitDrumProperties: the click has no remainder */
        if (v->slow_share <= 0.0 || decay_rate >= 0.5 * v->click_dbs) {
            out[0] = 0.0;
            out[1] = decay_rate;
        } else {
            double s = 0.5 * v->slow_dbs;
            out[0] = v->slow_share;
            out[1] = s < decay_rate ? s : decay_rate;
        }
        return;
    }
    double b1 = string_blend(v, frequency, v->string_break_hz[0]);
    double b2 = string_blend(v, frequency, v->string_break_hz[1]);
    double level = v->aftersound_level[0] + (v->aftersound_level[1] - v->aftersound_level[0]) * b1;
    level += (v->aftersound_level[2] - level) * b2;
    out[0] = level;
    out[1] = decay_rate * v->aftersound_decay_ratio;
}

/* GrandPianoProperties.unison_voices: [(gain, offset Hz, ratio, decay, phase)]
 * in out[5k..5k+4]; returns how many */
/* round(69 + 12 log2(f/440)): the note a section's seeds key on */
static long long section_midi(double frequency)
{
    return (long long)rint(69 + 12 * log(frequency / 440.0) / log(2.0));
}

/* sum() of floats as Python's (3.12: Neumaier's compensated sum) */
static double py_fsum(const double *x, int n)
{
    double r = 0.0, c = 0.0;
    for (int i = 0; i < n; i++) {
        double t = r + x[i];
        if (fabs(r) >= fabs(x[i]))
            c += (r - t) + x[i];
        else
            c += (x[i] - t) + r;
        r = t;
    }
    if (c != 0.0 && isfinite(c))
        r += c;
    return r;
}

/* tonelib.section_onset: how late player index is, in seconds */
double nv_section_onset(long long salt, long long midi, int index, double width_ms)
{
    if (width_ms == 0.0)
        return 0.0;
    uint64_t x = (uint64_t)(salt & 0xFFFFFFFFLL) * 0x9E3779B1ULL;
    x = x + ((uint64_t)midi << 20) + (uint64_t)(long long)index;
    x = x + 0x9E3779B97F4A7C15ULL;
    x ^= x >> 30; x = x * 0xBF58476D1CE4E5B9ULL;
    x ^= x >> 27; x = x * 0x94D049BB133111EBULL;
    x ^= x >> 31;
    return ((double)x / 18446744073709551616.0) * (width_ms / 1000.0);
}

/* TelephoneRingProperties._stroke: stroke i's offset (s), level and phase
 * (cycles), fixed by the pitch -- random.Random(round(f x 16) x 7919 + i x
 * 104729 + 124): gauss, uniform, random, in that order */
static void tap_stroke(const VoiceSnap *v, double frequency, int i, double *o)
{
    PyRandom r;
    pyr_seed(&r, (long long)nearbyint(frequency * 16.0) * 7919 + (long long)i * 104729 + 124);
    o[0] = pyr_gauss(&r, 0.0, v->tap_jit);
    o[1] = pow(10.0, -pyr_uniform(&r, 0.0, v->tap_ldb) / 20.0);
    o[2] = pyr_random(&r);
}

/* section_onsets_at for a struck voice repeated: [0] and each tap -- the
 * clapper's moved by its stroke's offset, never before 1 ms. Returns how many */
int nv_tap_onsets(const VoiceSnap *v, double frequency, double *ons)
{
    ons[0] = 0.0;
    for (int i = 0; i < v->n_tap; i++) {
        if (v->tap_kind == 2) {
            double o[3];
            tap_stroke(v, frequency, i, o);
            double x = v->tap_t[i] + o[0];
            ons[i + 1] = x > 0.001 ? x : 0.001;
        } else {
            ons[i + 1] = v->tap_t[i];
        }
    }
    return v->n_tap + 1;
}

int nv_unison_voices(const VoiceSnap *v, double frequency, int harmonic, double harmonic_decay, double *out)
{
    if (v->tap_kind) {                          /* BirdTweet's chirps, TelephoneRing's strokes */
        int g = (1 <= harmonic && harmonic <= v->n_gong) ? v->gong[harmonic - 1] : 0;
        for (int i = 0; i < v->n_tap; i++) {
            double gm = v->tap_gain, ph = 0.0;
            if (v->tap_kind == 2) {             /* stroke i+1 rings gong (i+1) % 2, its own level and phase */
                double o[3];
                tap_stroke(v, frequency, i, o);
                gm = ((i + 1) % 2 == g) ? v->tap_gain * o[1] : 0.0;
                ph = o[2];
            }
            out[5 * i] = gm; out[5 * i + 1] = 0.0; out[5 * i + 2] = 0.0;
            out[5 * i + 3] = harmonic_decay; out[5 * i + 4] = ph;
        }
        return v->n_tap;
    }
    if (v->hit_n) {                             /* OrchestraHitProperties: the section, cents in the ratio slot */
        for (int i = 0; i < v->hit_n; i++) {
            out[5 * i] = v->hit_gain; out[5 * i + 1] = 0.0;
            out[5 * i + 2] = pow(2.0, v->hit_cents[i] / 1200.0) - 1.0;
            out[5 * i + 3] = harmonic_decay; out[5 * i + 4] = 0.0;
        }
        return v->hit_n;
    }
    if (v->dul_n) {                             /* HammeredDulcimerProperties: the course's other strings */
        long long key = (long long)nearbyint(69 + 12 * log2(frequency / 440.0));
        for (int i = 0; i < v->dul_n; i++) {
            PyRandom r;
            pyr_seed(&r, key * 7919 + (long long)i * 104729 + harmonic);
            double off = pyr_uniform(&r, v->dul_beat[0], v->dul_beat[1]) * (pyr_random(&r) < 0.5 ? 1.0 : -1.0);
            out[5 * i] = v->unison_gain; out[5 * i + 1] = off; out[5 * i + 2] = 0.0;
            out[5 * i + 3] = harmonic_decay; out[5 * i + 4] = 0.0;
        }
        return v->dul_n;
    }
    if (v->sect_n > 1) {                        /* SectionMixin: the other players */
        int n = v->sect_n;
        long long midi = section_midi(frequency);
        PyRandom r;
        pyr_seed(&r, 0x5EC0 + midi + v->section_salt * 65537);
        double cents[16];
        for (int i = 0; i < n - 1; i++)
            cents[i] = pyr_uniform(&r, -v->sect_spread_cents, v->sect_spread_cents);
        double mean = py_fsum(cents, n - 1) / (double)(n - 1);
        for (int i = 0; i < n - 1; i++)
            cents[i] = cents[i] - mean * (double)(n - 1) / (double)n;
        for (int i = 0; i < n - 1; i++) {
            out[5 * i + 0] = 1.0; out[5 * i + 1] = 0.0;
            out[5 * i + 2] = pow(2.0, cents[i] / 1200.0) - 1.0;
            out[5 * i + 3] = harmonic_decay;
            out[5 * i + 4] = pyr_random(&r);
        }
        return n - 1;
    }
    if (v->pea) {                               /* SambaWhistleProperties: the pea's comb, +-k */
        int n = 0;
        for (int k = 0; k < v->n_unison; k++) {
            double g = v->unison_gain / (double)(k + 1);
            for (int sg = 0; sg < 2; sg++, n++) {
                out[5 * n + 0] = g; out[5 * n + 1] = sg ? -v->unison_detune[k] : v->unison_detune[k];
                out[5 * n + 2] = 0.0; out[5 * n + 3] = harmonic_decay; out[5 * n + 4] = 0.0;
            }
        }
        return n;
    }
    if (v->n_bank) {                            /* AccordionProperties: its reed banks */
        double octv = log((frequency > 1e-9 ? frequency : 1e-9) / 440.0) / log(2.0);
        int n = 0;
        for (int i = 0; i < v->n_bank; i++) {
            if (v->bank_g[i] <= 0.0)
                continue;
            double cents = v->bank_cents[i] + v->bank_oct[i] * octv;
            double det = pow(2.0, cents / 1200.0) - 1.0;
            out[5 * n + 0] = v->bank_g[i]; out[5 * n + 1] = 0.0;
            out[5 * n + 2] = v->bank_ratio[i] * (1.0 + det) - 1.0;
            out[5 * n + 3] = harmonic_decay; out[5 * n + 4] = 0.0;
            n++;
        }
        return n;
    }
    if (v->kind != 0) {                         /* SynthProperties': a voice per detune */
        int n = v->n_unison;
        for (int i = 0; i < v->n_unison; i++) {
            out[5 * i + 0] = v->unison_gain; out[5 * i + 1] = v->unison_detune[i]; out[5 * i + 2] = 0.0;
            out[5 * i + 3] = harmonic_decay; out[5 * i + 4] = 0.0;
        }
        /* ...and a course's partner (the mandolin's, the 12-string's) */
        double ug = 0.0, uc = 0.0;
        int add = 0;
        if (v->crs_kind == 1) {
            ug = v->crs_uni_gain; uc = v->crs_uni_cents; add = 1;
        } else if (v->crs_kind == 2) {
            double midi = 69 + 12 * log2((frequency > 1e-6 ? frequency : 1e-6) / 440.0);
            if (midi >= v->crs_split - 0.5) {
                ug = v->crs_uni_gain; uc = v->crs_uni_cents; add = 1;
            } else if (harmonic % 2 == 0) {
                double hm = nv_harmonic_volume(v, harmonic);
                if (hm > 0.0) {
                    double g = v->crs_oct_gain * nv_harmonic_volume(v, harmonic / 2) / hm;
                    ug = g < 30.0 ? g : 30.0; uc = v->crs_oct_cents; add = 1;
                }
            }
        }
        if (add) {
            out[5 * n + 0] = ug; out[5 * n + 1] = 0.0; out[5 * n + 2] = pow(2.0, uc / 1200.0) - 1.0;
            out[5 * n + 3] = harmonic_decay; out[5 * n + 4] = 0.0;
            n++;
        }
        if (v->crs_kind == 5 && harmonic % 2 == 0) {
            /* THE TAISHOGOTO's TRIO (TaishoKotoProperties.unison_voices): the
               trio's k-th harmonics on the string's 2k-th, each a third of
               the sum's power */
            double hm = nv_harmonic_volume(v, harmonic);
            if (hm > 0.0) {             /* (at the string's own spectrum: without the low string's tilt) */
                double g = v->crs_oct_gain * nv_harmonic_volume_base(v, harmonic / 2) / hm;
                g = (g < 30.0 ? g : 30.0) / pow((double)v->crs_ntrio, 0.5);
                for (int q = 0; q < v->crs_ntrio; q++) {
                    out[5 * n + 0] = g; out[5 * n + 1] = 0.0;
                    out[5 * n + 2] = pow(2.0, v->crs_trio[q] / 1200.0) - 1.0;
                    out[5 * n + 3] = harmonic_decay; out[5 * n + 4] = 0.0;
                    n++;
                }
            }
        }
        if (v->crs_kind == 3 || v->crs_kind == 4) {
            /* THE KANUN's COURSE (KanunProperties.unison_voices): the key's two
               strings, one sharp, one flat; the OUD's (OudProperties'): one
               partner either side -- each from random.Random(seed + key) */
            const int midi = (int)nearbyint(69 + 12 * log((double)frequency / 440.0) / log(2));
            PyRandom rng;
            pyr_seed(&rng, (long long)v->crs_seed + midi);
            double cs[2];
            int nc = 1;
            if (v->crs_kind == 3) {
                cs[0] = pyr_uniform(&rng, v->crs_lo, v->crs_hi);
                cs[1] = -pyr_uniform(&rng, v->crs_lo, v->crs_hi);
                nc = 2;
            } else {
                const double c = pyr_uniform(&rng, v->crs_lo, v->crs_hi);
                cs[0] = c * (pyr_random(&rng) < 0.5 ? 1.0 : -1.0);
            }
            for (int q = 0; q < nc; q++) {
                out[5 * n + 0] = v->crs_kind == 3 ? 1.0 : v->crs_uni_gain;
                out[5 * n + 1] = 0.0;
                out[5 * n + 2] = pow(2.0, cs[q] / 1200.0) - 1.0;
                out[5 * n + 3] = harmonic_decay;
                out[5 * n + 4] = 0.0;
                n++;
            }
        }
        return n;
    }
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

static double chiff_harmonic_gain(const VoiceSnap *v, double harmonic)
{
    if (!v->chiff_span_set)
        return 1.0;
    double x = (harmonic - 1.0) / v->chiff_harmonic_span;
    if (x <= 0.0)
        return 1.0;
    return 1.0 / (1.0 + pow(x, v->chiff_harmonic_power));
}

double nv_chiff_harmonic_gain(const VoiceSnap *v, double harmonic)
{
    double g = v->chiff_bore                    /* the fret noise's: the body's gain x the roll-off */
        ? bore_gain(v, v->frequency_x * pow(2.0, v->octave_position) * harmonic) * hf_rolloff(v, harmonic)
        : v->noisy                              /* NoisyPercussionMixin: the wash rolled off too */
        ? chiff_harmonic_gain(v, harmonic) * hf_rolloff(v, harmonic) : chiff_harmonic_gain(v, harmonic);
    if (v->nyquist != 0.0 && !(v->frequency_x * pow(2.0, v->octave_position) * harmonic < v->nyquist))
        return 0.0;                             /* SampledBreak's Nyquist */
    return g;
}

double nv_bloom_delay_for(const VoiceSnap *v, double frequency)
{
    if (v->bloom_seconds <= 0.0 || frequency <= 0.0)
        return 0.0;
    double d = fabs(log(frequency / v->bloom_center_hz) / log(2.0) / v->bloom_octaves);
    return v->bloom_seconds * exp(-0.5 * pow(d, v->bloom_shape));
}

/* SynthProperties.bloom_gain_for: the late copy's gain at this partial */
double nv_bloom_gain_for(const VoiceSnap *v, double frequency)
{
    if (!v->bloom_banded || v->bloom_seconds <= 0.0)
        return v->bloom_gain;
    return v->bloom_gain * nv_bloom_delay_for(v, frequency) / v->bloom_seconds;
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

static int voice_vibrato_base(const VoiceSnap *v, double frequency, int index, double *out);

/* SynthProperties.voice_vibrato, and a MELLOTRON's over it (MellotronMixin):
   the voice's own where it has depth, else the capstan's wow */
int nv_voice_vibrato(const VoiceSnap *v, double frequency, int index, double *out)
{
    const int got = voice_vibrato_base(v, frequency, index, out);
    if (v->wow_set && !(got && out[0] != 0.0)) {
        out[0] = pow(2.0, v->wow_cents / 1200.0) - 1.0;
        out[1] = v->wow_hz;
        out[2] = 0.0;
        return 1;
    }
    return got;
}

static int voice_vibrato_base(const VoiceSnap *v, double frequency, int index, double *out)
{
    if (v->sect_vib) {                          /* SectionMixin: each player's own */
        if (v->sect_vib_cents == 0.0)
            return 0;
        long long midi = section_midi(frequency);
        PyRandom r;
        pyr_seed(&r, 0x71B0 + midi * 64 + index + v->section_salt * 8191);
        out[0] = (pow(2.0, v->sect_vib_cents / 1200.0) - 1.0) * pyr_uniform(&r, 0.7, 1.0);
        out[1] = pyr_uniform(&r, v->sect_vib_hz[0], v->sect_vib_hz[1]);
        out[2] = pyr_uniform(&r, 0.0, 6.283185307179586);
        return 1;
    }
    if (v->sw_set) {                            /* UkuleleProperties: each string's wander, drawn by the key */
        long long midi = (long long)nearbyint(69 + 12 * log(frequency / 440.0) / log(2.0));
        PyRandom r;
        pyr_seed(&r, 0x0CE + midi * 64 + index);
        out[0] = (pow(2.0, v->sw_cents / 1200.0) - 1.0) * pyr_uniform(&r, 0.3, 1.0);
        out[1] = pyr_uniform(&r, v->sw_hz[0], v->sw_hz[1]);
        out[2] = pyr_uniform(&r, 0.0, 6.283185307179586);
        return 1;
    }
    if (v->fv_set) {                            /* a fixed vibrato of its own (the skid's, the scream's) */
        out[0] = pow(2.0, v->fv_cents * 1.4142 / 1200.0) - 1.0;
        out[1] = v->fv_hz;
        out[2] = 0.0;
        return 1;
    }
    if (v->pea) {                               /* SambaWhistleProperties: the pea's flutter */
        out[0] = pow(2.0, v->pea_vibrato_cents * 1.4142 / 1200.0) - 1.0;
        out[1] = v->pea_vibrato_hz;
        out[2] = 0.0;
        return 1;
    }
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
    double stretch = B > 0 ? (v->stretch_exact ? sqrt((1.0 + B * h * h) / (1.0 + B))
                                              : (1.0 + 0.5 * (h * h - 1.0) * B)) : 1.0;
    out[0] = h;
    out[1] = f0 * h * stretch;
    if (v->partial_cents_scatter != 0.0 && m > 1) {   /* off the law by its own cents (tonelib.partial_hash) */
        int k = (int)rint(69.0 + 12.0 * log(f0 / 440.0) / log(2.0));
        uint32_t hh = ((uint32_t)k * 2654435761u) ^ ((uint32_t)m * 40503u);
        hh = hh * 2246822519u + 3266489917u;
        hh ^= hh >> 15;
        hh = hh * 668265263u + 374761393u;
        hh ^= hh >> 13;
        double u = hh / 4294967296.0;
        out[1] *= pow(2.0, (2.0 * u - 1.0) * v->partial_cents_scatter / 1200.0);
    }
    return 1;
}

/* blockrender.partial_decay: (dB/s, log rate, aftersound's share, its log rate) */
void nv_partial_decay(const VoiceSnap *v, double f0, int m, double *out)
{
    double dbps = nv_harmonic_decay(v, m);
    double logr = dbps > 0 ? log(db_ratio(dbps)) : 0.0;
    double a[2];
    if (v->sw_on) {                             /* SawariContact.aftersound_partial: the share the strip feeds */
        a[0] = 0.0;
        a[1] = dbps;
        if (m <= v->n_sw && v->sw_share[m - 1] > 0.0) {
            a[0] = v->sw_share[m - 1];
            a[1] = v->sw_slow[m - 1];
        }
    } else if (v->fc_tab) {                     /* FretContact.aftersound_partial: the string's own ring */
        a[0] = 0.0;
        a[1] = dbps;
        if (m <= v->n_fc && v->fc_share[m - 1] < 1.0) {
            a[0] = v->fc_share[m - 1];
            a[1] = sp_decay(v, m);
        }
    } else if (v->pick_set) {                   /* Plectrum.aftersound_partial: what rings on under the boost */
        double b = pick_db(v, m);
        a[0] = b > 0.0 ? pow(10.0, -b / 20.0) : 0.0;
        a[1] = b > 0.0 ? harmonic_decay_(v, m) : dbps;
    } else if (v->n_ma) {                       /* TR808Properties.aftersound_partial */
        a[0] = 0.0;
        a[1] = dbps;
        if (1 <= m && m <= v->n_ma && v->mode_after[m - 1][0] > 0.0) {
            a[0] = v->mode_after[m - 1][0];
            a[1] = v->mode_after[m - 1][1] * v->decay_register_factor;
        }
    } else if (v->pd_max_hz != 0.0) {           /* PromptDecay.aftersound_partial: the ring under the fall */
        a[0] = 0.0;
        a[1] = dbps;
        if (v->pd_share > 0.0 && f0 * m < v->pd_max_hz) {
            a[0] = v->pd_share;
            a[1] = prompt_ring(v, m);
        }
    } else if (v->kind == 1 && v->slow_max_hz != 0.0 && f0 * nv_mode_ratio(v, m) > v->slow_max_hz) {
        a[0] = 0.0;                             /* aftersound_partial: no remainder up here */
        a[1] = dbps;
    } else {
        nv_aftersound(v, f0, dbps, a);
    }
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

/* ElectricBassProperties._string_of: the string a note is played on (the
   highest open string at or under it, else the first) and its stopped length */
static void sp_string(const VoiceSnap *v, double f0, int *kk, double *oo, double *ls)
{
    int k = -1;
    for (int q = 0; q < v->n_os; q++)
        if (v->os_hz[q] <= f0 * 1.0001 && (k < 0 || v->os_hz[q] > v->os_hz[k]))
            k = q;
    if (k < 0)
        k = 0;
    double o = v->os_hz[k];
    double sc = pymin(pymax(1.0, f0 / o), pow(2.0, v->fret_max / 12.0));
    *kk = k;
    *oo = o;
    *ls = v->sp_scale / sc;
}

/* ElectricBassProperties._string_mu_t: its gauge (m), mass per length, tension */
static void sp_mu_t(const VoiceSnap *v, int k, double o, double *d, double *mu, double *t)
{
    *d = v->sp_gauge[k] * 0.0254;
    *mu = v->sp_mass * 7850.0 * PI * *d * *d / 4.0;
    *t = *mu * pow(2.0 * v->sp_scale * o, 2.0);
}

/* ElectricBassProperties.harmonic_decay: the string's air, visco- and
   thermo-elastic losses, the bearings' 4 W G a reflection, the mounting */
static double sp_decay(const VoiceSnap *v, int harmonic)
{
    double f0 = v->frequency_x * pow(2.0, v->octave_position);
    int k;
    double o, ls, d, mu, t;
    sp_string(v, f0, &k, &o, &ls);
    sp_mu_t(v, k, o, &d, &mu, &t);
    double dc = v->sp_core[k] * 0.0254;
    double rc = dc / 2.0;
    double rw = (d - dc) / 4.0;
    double d_air = (PI / 2.0) * ((1.0 + 2.0 / PI) * 2.0 * rw + 2.0 * rc);
    double ei = 2.0e11 * PI * pow(rc, 4.0) / 4.0;
    double nu = (double)harmonic * f0;
    double eta = 1.8e-5, rho = 1.2;
    double r = 2.0 * PI * eta + 2.0 * PI * d_air * sqrt(PI * eta * rho * nu);
    double iq = r / (2.0 * PI * mu * nu) + 4.0 * pow(PI, 2.0) * mu * ei * v->sp_wind * pow(nu, 2.0) / pow(t, 2.0)
                + v->sp_qte;
    double x = 1.0 - ls / v->sp_scale;
    double g = v->sp_g * (v->sp_body + (1.0 - v->sp_body) * pow(pymax(1.0 - x / v->sp_joint, 0.0), v->sp_fall));
    g *= pow(nu / 100.0, -v->sp_fexp);
    double bear = g != 0.0 ? -10.0 * log(pymax(1.0 - 4.0 * sqrt(t * mu) * g, 1e-9)) / log(10.0) * 2.0 * f0 : 0.0;
    double dbs = (20.0 / log(10.0)) * PI * nu * iq + v->sp_mount + bear;
    return 0.5 * dbs;
}

/* tonelib.FretContact's tables (nv_fret_contact_set) */
static double *FC_DATA, FC_KEY0, FC_VELS[16];
static int fc_nt, fc_nk, fc_nv, fc_nm;

int nv_fret_contact_set(int nt, int nk, int nv, int nm, double key0, const double *vels, const double *data)
{
    if (nt < 1 || nk < 1 || nv < 2 || nv > 16 || nm < 1 || nm > 64)
        return 0;
    size_t n = (size_t)nt * nk * nv * nm * 3;
    double *d = (double *)malloc(n * sizeof(double));
    if (!d)
        return 0;
    memcpy(d, data, n * sizeof(double));
    free(FC_DATA);
    FC_DATA = d;
    FC_KEY0 = key0;
    memcpy(FC_VELS, vels, nv * sizeof(double));
    fc_nt = nt; fc_nk = nk; fc_nv = nv; fc_nm = nm;
    return 1;
}

/* tonelib.fret_contact_modes: the note's modes, linear in the key and in the
   stroke (sqrt attack_volume), each held at the table's ends */
static void fc_modes(VoiceSnap *s, double frequency, double attack_volume)
{
    int t = s->fc_tab - 1;
    if (!FC_DATA || t < 0 || t >= fc_nt) {
        /* (no table handed over -- an export without its FCON: the string
           plays as its plain pluck, never silent) */
        s->fc_tab = 0;
        s->n_fc = 0;
        return;
    }
    double key = 69.0 + 12.0 * log(frequency / 440.0) / log(2.0);
    double kf = pymin(pymax(key - FC_KEY0, 0.0), (double)(fc_nk - 1));
    int i = (int)kf;
    int i1 = i + 1 < fc_nk - 1 ? i + 1 : fc_nk - 1;
    double wk = kf - i;
    double vv = pymin(pymax(sqrt(pymax(attack_volume, 0.0)), FC_VELS[0]), FC_VELS[fc_nv - 1]);
    int j = 0;
    while (j + 2 < fc_nv && vv > FC_VELS[j + 1])
        j++;
    double wv = (vv - FC_VELS[j]) / (FC_VELS[j + 1] - FC_VELS[j]);
#define FCV(ii, jj, mm, qq) FC_DATA[((((size_t)t * fc_nk + (ii)) * fc_nv + (jj)) * fc_nm + (mm)) * 3 + (qq)]
    for (int m = 0; m < fc_nm; m++) {
        double out[3];
        for (int q = 0; q < 3; q++) {
            double a = FCV(i, j, m, q) + (FCV(i, j + 1, m, q) - FCV(i, j, m, q)) * wv;
            double b = FCV(i1, j, m, q) + (FCV(i1, j + 1, m, q) - FCV(i1, j, m, q)) * wv;
            out[q] = a + (b - a) * wk;
        }
        s->fc_amp[m] = out[0];
        s->fc_share[m] = out[1];
        s->fc_fast[m] = out[2];
    }
#undef FCV
    s->n_fc = fc_nm;
}

/* tonelib.SawariContact's table (nv_sawari_set): [key][mode][share, fast, slow] */
static double *SW_DATA, SW_KEY0;
static int sw_nk, sw_nm;

int nv_sawari_set(int nk, int nm, double key0, const double *data)
{
    if (nk < 1 || nm < 1 || nm > 96)
        return 0;
    size_t n = (size_t)nk * nm * 3;
    double *d = (double *)malloc(n * sizeof(double));
    if (!d)
        return 0;
    memcpy(d, data, n * sizeof(double));
    free(SW_DATA);
    SW_DATA = d;
    SW_KEY0 = key0;
    sw_nk = nk; sw_nm = nm;
    return 1;
}

/* tonelib.sawari_modes: the note's (share, slow), linear in the key between
   rows (a mode one row lacks taken from the other), held at the ends */
static void sw_modes(VoiceSnap *s, double frequency)
{
    s->sw_f0 = frequency;
    if (!SW_DATA) {                             /* (no table: the free silk alone) */
        s->n_sw = 0;
        return;
    }
    double key = 69.0 + 12.0 * log(frequency / 440.0) / log(2.0);
    double kf = pymin(pymax(key - SW_KEY0, 0.0), (double)(sw_nk - 1));
    int i = (int)kf;
    int i1 = i + 1 < sw_nk - 1 ? i + 1 : sw_nk - 1;
    double wk = kf - i;
#define SWV(ii, mm, qq) SW_DATA[(((size_t)(ii)) * sw_nm + (mm)) * 3 + (qq)]
    for (int m = 0; m < sw_nm; m++) {
        if (SWV(i, m, 1) <= 0.0 || SWV(i1, m, 1) <= 0.0) {
            int c = SWV(i, m, 1) > 0.0 ? i : i1;
            s->sw_share[m] = SWV(c, m, 0);
            s->sw_slow[m] = SWV(c, m, 2);
        } else {
            s->sw_share[m] = SWV(i, m, 0) + (SWV(i1, m, 0) - SWV(i, m, 0)) * wk;
            s->sw_slow[m] = SWV(i, m, 2) + (SWV(i1, m, 2) - SWV(i, m, 2)) * wk;
        }
    }
#undef SWV
    s->n_sw = sw_nm;
}

/* ElectricBassProperties.inharmonicity_coefficient_for_frequency: from its core */
static double sp_b(const VoiceSnap *v, double frequency)
{
    int k;
    double o, ls, d, mu, t;
    sp_string(v, frequency, &k, &o, &ls);
    sp_mu_t(v, k, o, &d, &mu, &t);
    double dc = v->sp_core[k] * 0.0254;
    return pow(PI, 3.0) * 2.0e11 * pow(dc, 4.0) / (64.0 * t * pow(ls, 2.0));
}

int nv_reed_series_cached(double gate, double edge, double spread, int points, int max_harmonic, double direct,
                          double *out);
int nv_ep_layers_cached(int kind, const double *p, double a0, double rho, double f0, double op, int harmonics,
                        int terms, double max_hz, double floor_db, int control, double *out, int cap);

/* tonelib.stage_angle */
static double stage_angle(double p)
{
    return asin(0.5 * tan(pymax(-1.0, pymin(1.0, p)) * PI / 4.0));
}

double nv_stage_angle(double p) { return stage_angle(p); }

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
/* tonelib.VOICE_BODIES and VOICE_CLUSTER (each part's tract against the
   mean singer's, its singer's-formant cluster) and _NOT_A_VOICE, as
   native.py hands them over from tonelib (nv_voice_bodies_set) */
#define VB_MAX 64
static char VB_NAME[VB_MAX][32], NOT_A_VOICE[VB_MAX][32];
static double VB_RATIO[VB_MAX], VB_CLUSTER[VB_MAX];
static int vb_n, nav_n, vb_ready;

/* names: n parts' then nn not-a-voice strings, each NUL-terminated, back to back */
int nv_voice_bodies_set(int n, const char *names, const double *ratio, const double *cluster, int nn)
{
    if (n > VB_MAX || nn > VB_MAX)
        return 0;
    const char *p = names;
    for (int i = 0; i < n + nn; i++) {
        size_t l = strlen(p);
        if (l >= 32)
            return 0;
        memcpy(i < n ? VB_NAME[i] : NOT_A_VOICE[i - n], p, l + 1);
        p += l + 1;
    }
    for (int i = 0; i < n; i++) {
        VB_RATIO[i] = ratio[i];
        VB_CLUSTER[i] = cluster[i];
    }
    vb_n = n;
    nav_n = nn;
    vb_ready = 1;
    return 1;
}

/* tonelib.voice_body: the longest part named by a word of the track's
   lowercased name, unless it names something that is not a voice */
int nv_voice_body(const char *name)
{
    if (!name || !*name || !vb_ready)
        return 0;
    char low[512];
    size_t n = strlen(name);
    if (n >= sizeof low)
        n = sizeof low - 1;
    for (size_t i = 0; i < n; i++) {
        unsigned char ch = (unsigned char)name[i];
        low[i] = (char)((ch >= 'A' && ch <= 'Z') || (ch >= 0xC0 && ch <= 0xDE && ch != 0xD7) ? ch + 32 : ch);
    }
    low[n] = 0;
    for (int b = 0; b < nav_n; b++)
        if (strstr(low, NOT_A_VOICE[b]))
            return 0;
    int hit = -1;
    size_t hlen = 0;
    int m = vb_n;
    for (size_t i = 0; i < n;) {
        if (low[i] < 'a' || low[i] > 'z') {
            i++;
            continue;
        }
        size_t j = i;
        while (j < n && low[j] >= 'a' && low[j] <= 'z')
            j++;
        for (int k = 0; k < m; k++)
            if (strlen(VB_NAME[k]) == j - i && !strncmp(VB_NAME[k], low + i, j - i) && (hit < 0 || j - i > hlen)) {
                hit = k;
                hlen = j - i;
            }
        i = j;
    }
    return hit + 1;
}

int nv_voice_part(int part, double *ratio, double *cluster)
{
    if (part < 1 || part > vb_n)
        return 0;
    *ratio = VB_RATIO[part - 1];
    *cluster = VB_CLUSTER[part - 1];
    return 1;
}

/* _VocalBody._formant_tune: F1 raised onto a fundamental above it, below F2 */
static void formant_tune(double (*out)[3], int n, double f)
{
    if (!n || f <= out[0][0])
        return;
    double c = out[0][0], bw = out[0][1];
    double ceiling = n > 1 ? out[1][0] * 0.8 : f;
    double nw = pymin(f, ceiling);
    if (nw > c) {
        out[0][0] = nw;
        out[0][1] = bw * pow(nw / c, 0.5);
    }
}

/* _VocalBody._sung_formants: the class's vowel on this note's body -- a
   declared part's tract, or the draw between a man's and a woman's by its
   part's tessitura (seeded on its key), broadened where both sing */
static void sung_formants(const VoiceInit *c, double frequency, VoiceSnap *s)
{
    int n = c->n_vb;
    double out[16][3];
    s->n_fm = n;
    if (!n || c->vb_tract == 0.0) {
        for (int i = 0; i < n; i++)
            for (int j = 0; j < 3; j++)
                s->fm[i][j] = c->vb_fm[i][j];
        return;
    }
    double f0 = c->sung_hz != 0.0 ? c->sung_hz : frequency;
    if (c->part_set) {
        double ratio = c->part_ratio, cl = c->part_cluster;
        for (int i = 0; i < n; i++) {
            double ce = c->vb_fm[i][0], bw = c->vb_fm[i][1], amp = c->vb_fm[i][2];
            double a = amp * ((ratio > 1.0 && i >= 2 && ce * ratio >= c->vb_sfhz) ? c->vb_ftop : 1.0)
                       * (i >= 2 ? cl : 1.0);
            out[i][0] = ce * ratio;
            out[i][1] = bw * ratio;
            out[i][2] = a;
        }
        formant_tune(out, n, f0 != 0.0 ? f0 : 1.0);
    } else {
        double f = f0 != 0.0 ? f0 : 1.0;
        long long midi = (long long)nearbyint(69 + 12 * log(f / 440.0) / log(2));
        double x = (log(f / c->vb_xhz) / log(2)) / c->vb_xoct;
        double w = 1.0 / (1.0 + exp(-pymax(-40.0, pymin(40.0, x))));
        double half = pow(c->vb_tract, 0.5);
        double ratio = pow(half, 2.0 * w - 1.0);
        PyRandom r;
        pyr_seed(&r, 0x5117 + midi * 2654435761LL);
        ratio *= exp(pyr_gauss(&r, 0.0, c->vb_sigma));
        double blend = 1.0 + c->vb_mb * 4.0 * w * (1.0 - w);
        for (int i = 0; i < n; i++) {
            double ce = c->vb_fm[i][0], bw = c->vb_fm[i][1], a = c->vb_fm[i][2];
            if (i >= 2 && ce * ratio >= c->vb_sfhz)
                a *= (1.0 - w) + w * c->vb_ftop;
            out[i][0] = ce * ratio;
            out[i][1] = bw * ratio * blend;
            out[i][2] = a;
        }
        formant_tune(out, n, f);
    }
    for (int i = 0; i < n; i++)
        for (int j = 0; j < 3; j++)
            s->fm[i][j] = out[i][j];
}

/* _bore_norm: the series' power at the voice's own tonal dampening,
   unfiltered, over the bore's -- at the gain the voice has now (the
   Python's is read lazily, at the first harmonic) */
static void bore_norm(const VoiceInit *c, VoiceSnap *s)
{
    double f0 = s->frequency_x * pow(2.0, s->octave_position), ref = 0.0, shaped = 0.0;
    int top = s->max_harmonic ? s->max_harmonic : 64;
    for (int h = 1; h <= top; h++) {
        double a = nv_series_volume(s, h);
        if (a == 0.0)
            continue;
        double r = a * pow((double)h, s->attack_dampening - c->tonal_dampening);
        ref += r * r;
        double g = a * bore_gain(s, f0 * h);
        shaped += g * g;
    }
    s->bore_norm = shaped > 0.0 ? pow(ref / shaped, 0.5) : 1.0;
    if (s->blare_db_per_khz != 0.0) {
        /* _blare_norm: the bored series' power over the blared */
        ref = shaped = 0.0;
        for (int h = 1; h <= top; h++) {
            double a = nv_series_volume(s, h);
            if (a == 0.0)
                continue;
            double hz = f0 * nv_mode_ratio(s, h);
            a *= bore_gain(s, hz);
            ref += a * a;
            double g = a * blare(s, hz);
            shaped += g * g;
        }
        s->blare_norm = shaped > 0.0 ? pow(ref / shaped, 0.5) : 1.0;
    }
}

void nv_voice_regain(const VoiceInit *c, VoiceSnap *s, double k)
{
    s->gain *= k;
    if (s->bore_corner_hz != 0.0)
        bore_norm(c, s);
}

/* A NOTE TURNED TO AN ANGLE after it is built (a GS 3D type's: props.pan_angle,
   props.place()): its ears' incidences and delays from there */
void nv_voice_turn(const VoiceInit *c, const VoiceSnap *s, VoiceNote *o, double angle)
{
    double e[4];
    o->pan_angle = angle;
    voice_hrtf_at(c, angle, s->position_x, e);
    o->left_incidence = e[0]; o->right_incidence = e[1];
    o->left_hrtf_delay = e[2]; o->right_hrtf_delay = e[3];
}


/* ---- THE SIMULATED HAMMER (hammer.py; GrandPianoProperties._hammer_gain) ----
   Every step and sum as the Python takes them, so a note's partials are the
   same numbers here as there. */
#include <pthread.h>

static const int HM_LEVELS[17] = {1, 9, 17, 25, 33, 41, 49, 57, 65, 73, 81, 89, 97, 105, 113, 121, 127};

/* hammer.contact: the felt's force each step of 1/(44100*8) s, first touch to
   lift-off (or 25 ms); *dt_out its step. Returns its length; F malloc'd. */
static int hm_contact(double f0, double v0, double mass, double K, double p, double beta, double L, double Z,
                      double alpha, double tau, double core_x, double core_K, double **F_out, double *dt_out)
{
    const double core_p = 3.5;
    double dt = 1.0 / (44100 * 8);
    double kdec = exp(-dt / tau);
    double mem = 0.0;
    double c = 2.0 * L * f0;
    int M = (int)rint(L / (c * dt));
    if (M < 8) M = 8;
    int i0 = (int)rint(beta * M);
    if (i0 > M - 2) i0 = M - 2;
    if (i0 < 1) i0 = 1;
    double *r = calloc((size_t)M, sizeof(double)), *l = calloc((size_t)M, sizeof(double));
    int nmax = (int)(0.025 / dt);
    double *F = malloc((size_t)nmax * sizeof(double));
    int nf = 0, touched = 0;
    double ys = 0.0, yh = 0.0, vh = v0;
    for (int n = 0; n < nmax; n++) {
        double x = yh - ys;
        double up = x > 0.0 ? pow(x, p) : 0.0;
        mem = mem * kdec + up * (1.0 - kdec);
        double f = x > 0.0 ? K * (up - alpha * mem) : 0.0;
        if (core_x > 0.0 && x > core_x)
            f += core_K * pow(x - core_x, core_p);
        if (f < 0.0)
            f = 0.0;
        if (f > 0.0)
            touched = 1;
        else if (touched)
            break;
        F[nf++] = f;
        double inj = f / (2.0 * Z);
        double vs = r[i0 - 1] + l[i0 + 1] + inj;
        ys += vs * dt;
        vh -= f / mass * dt;
        yh += vh * dt;
        double rl = r[M - 1], ll0 = l[0];
        memmove(r + 1, r, (size_t)(M - 1) * sizeof(double));
        r[0] = -ll0;
        memmove(l, l + 1, (size_t)(M - 1) * sizeof(double));
        l[M - 1] = -rl;
        r[i0] += inj;
        l[i0] += inj;
    }
    free(r);
    free(l);
    *F_out = F;
    *dt_out = dt;
    return nf;
}

/* hammer.level_gains' cache: one per (nominal key, level), the felt it was made
   with, its longest spectrum */
typedef struct { double fn; int j, n; double key[13]; double *g, *ph; } HmEntry;
static HmEntry *hm_cache;
static int hm_ncache, hm_capcache;
static pthread_mutex_t hm_lock = PTHREAD_MUTEX_INITIALIZER;

static const double *hm_level_gains_ph(double fn, int j, int nharm, const double key[13], const double **ph_out);

static const double *hm_level_gains(double fn, int j, int nharm, const double key[13])
{
    return hm_level_gains_ph(fn, j, nharm, key, NULL);
}

static const double *hm_level_gains_ph(double fn, int j, int nharm, const double key[13], const double **ph_out)
{
    /* key: beta, mass, K, p, v_lo, v_hi, scale, lmax, alpha, tau, core_x, core_K, (unused 0) */
    pthread_mutex_lock(&hm_lock);
    for (int i = 0; i < hm_ncache; i++) {
        HmEntry *e = &hm_cache[i];
        if (e->fn == fn && e->j == j && e->n >= nharm && !memcmp(e->key, key, sizeof(e->key))) {
            if (ph_out)
                *ph_out = e->ph;
            pthread_mutex_unlock(&hm_lock);
            return e->g;
        }
    }
    pthread_mutex_unlock(&hm_lock);
    double scale = key[6], lmax = key[7];
    double L = lmax < scale / fn ? lmax : scale / fn;
    double T = fn < 110.0 ? 1100.0 : 750.0;
    double c = 2.0 * L * fn, mu = T / (c * c), Z = sqrt(T * mu);
    double v0 = key[4] * pow(key[5] / key[4], (HM_LEVELS[j] - 1) / 126.0);
    double *F, dt;
    int nf = hm_contact(fn, v0, key[1], key[2], key[3], key[0], L, Z, key[8], key[9], key[10], key[11], &F, &dt);
    double tot = 0.0;
    for (int i = 0; i < nf; i++)
        tot += F[i];
    double *g = malloc((size_t)nharm * sizeof(double));
    double *ph = malloc((size_t)nharm * sizeof(double));
    for (int h = 1; h <= nharm; h++) {
        double w = 2.0 * PI * fn * h * dt;
        double cw = cos(w), sw = sin(w), cc = 1.0, ss = 0.0, re = 0.0, im = 0.0;
        for (int i = 0; i < nf; i++) {
            re += F[i] * cc;
            im += F[i] * ss;
            double c2 = cc * cw - ss * sw;
            ss = ss * cw + cc * sw;
            cc = c2;
        }
        g[h - 1] = tot > 0.0 ? sqrt(re * re + im * im) / tot : 0.0;
        ph[h - 1] = -atan2(im, re);              /* hammer.phases: arg F(f) */
    }
    free(F);
    pthread_mutex_lock(&hm_lock);
    if (hm_ncache == hm_capcache) {
        hm_capcache = hm_capcache ? 2 * hm_capcache : 256;
        hm_cache = realloc(hm_cache, (size_t)hm_capcache * sizeof(HmEntry));
    }
    HmEntry *e = &hm_cache[hm_ncache++];
    e->fn = fn; e->j = j; e->n = nharm; e->g = g; e->ph = ph;
    if (ph_out)
        *ph_out = ph;
    memcpy(e->key, key, sizeof(e->key));
    pthread_mutex_unlock(&hm_lock);
    return g;
}

/* the felt's key (hm_level_gains') for the key at nominal pitch fn */
static void hm_key(const VoiceSnap *s, double fn, double key[13])
{
    double octs = log(fn / 440.0) / log(2.0);
    double u = log(fn / 27.5) / log(4186.0 / 27.5);
    u = u < 0.0 ? 0.0 : u;
    u = 1.0 < u ? 1.0 : u;
    double mass = (s->hm_mass_lo_g + (s->hm_mass_hi_g - s->hm_mass_lo_g) * u) * 1e-3;
    double p = s->hm_p_lo + (s->hm_p_hi - s->hm_p_lo) * u;
    double K = pow(10.0, s->hm_logk + s->hm_logk_slope * octs + s->hm_logk_curve * octs * octs);
    double core_mm = s->hm_core_mm;
    if (s->hm_core_edge_mm != 0.0) {
        double d = log(fn / s->hm_wear_center_hz) / log(2.0) / s->hm_wear_octaves;
        double w = exp(-0.5 * d * d);
        core_mm = s->hm_core_edge_mm + (s->hm_core_mm - s->hm_core_edge_mm) * w;
    }
    double k2[13] = {s->strike_point, mass, K, p, s->hm_speed_lo, s->hm_speed_hi, s->dz_scale, s->dz_lmax,
                     s->hm_alpha, pow(10.0, s->hm_log_tau), core_mm * 1e-3, pow(10.0, s->hm_core_logk), 0.0};
    memcpy(key, k2, sizeof(k2));
}

/* THE WHOLE PIANO'S TABLE AHEAD OF THE NOTES: every key A0-C8 at every level,
   to a partial count that covers a tuning half a semitone flat -- what a live
   host calls once the voice is loaded (off the audio thread), so no note-on
   waits on a simulation. Returns how many it made. */
int nv_hammer_warm(const VoiceSnap *tmpl)
{
    if (!tmpl->hammer_model)
        return 0;
    int made = 0;
    for (int k = 21; k <= 108; k++) {
        double fn = 440.0 * pow(2.0, (k - 69) / 12.0);
        double key[13];
        hm_key(tmpl, fn, key);
        int n = tmpl->hm_max_partial_hz != 0.0 ? (int)(tmpl->hm_max_partial_hz / (fn * 0.97)) + 1 : 64;
        if (n < 64) n = 64;
        if (n > 400) n = 400;
        for (int j = 0; j < 17; j++) {
            hm_level_gains(fn, j, n, key);
            made++;
        }
    }
    return made;
}

/* GrandPianoProperties._hammer_gain, for the whole note: s->hm_g[0..hm_n) */
static void hm_note(VoiceSnap *s)
{
    double f0 = s->frequency_x * pow(2.0, s->octave_position);
    /* hammer.nominal_f0 and _hammer_felt: the felt at the key's nominal pitch */
    int k = (int)rint(69.0 + 12.0 * log(f0 / 440.0) / log(2.0));
    double fn = 440.0 * pow(2.0, (k - 69) / 12.0);
    double key[13];
    hm_key(s, fn, key);
    int vel = (int)rint(127.0 * pow(s->attack_volume, 0.5));
    int n = s->max_harmonic ? s->max_harmonic : 64;
    if (s->hm_max_partial_hz != 0.0) {
        int m = (int)(s->hm_max_partial_hz / f0);
        n = m > n ? m : n;
    }
    if (n > 400)
        n = 400;
    /* hammer.gains: the two nearest levels, blended in dB */
    int v = vel < 1 ? 1 : (vel > 127 ? 127 : vel);
    int j = 0;
    while (j + 1 < 16 && HM_LEVELS[j + 1] <= v)
        j++;
    int va = HM_LEVELS[j], vb = HM_LEVELS[j + 1];
    const double *ga = hm_level_gains(fn, j, n, key);
    if (v == va) {
        for (int h = 0; h < n; h++) s->hm_g[h] = ga[h];
    } else {
        const double *gb = hm_level_gains(fn, j + 1, n, key);
        if (v == vb) {
            for (int h = 0; h < n; h++) s->hm_g[h] = gb[h];
        } else {
            double t = (double)(v - va) / (double)(vb - va);
            for (int h = 0; h < n; h++) {
                double a = ga[h] < 1e-30 ? 1e-30 : ga[h], b = gb[h] < 1e-30 ? 1e-30 : gb[h];
                s->hm_g[h] = exp((1.0 - t) * log(a) + t * log(b));
            }
        }
    }
    s->hm_n = n;
    if (s->hm_phase) {                          /* hammer.phases: the levels' phases, blended the shorter way */
        int np = n < 400 ? n : 400;
        const double *pa, *pb;
        hm_level_gains_ph(fn, j, n, key, &pa);
        if (v == va) {
            for (int h = 0; h < np; h++) s->mode_phases[h] = pa[h];
        } else {
            hm_level_gains_ph(fn, j + 1, n, key, &pb);
            if (v == vb) {
                for (int h = 0; h < np; h++) s->mode_phases[h] = pb[h];
            } else {
                double t = (double)(v - va) / (double)(vb - va);
                for (int h = 0; h < np; h++)
                    s->mode_phases[h] = pa[h] + t * remainder(pb[h] - pa[h], 2.0 * PI);
            }
        }
        s->n_mp = np;
    }
    /* THE NOTE'S LOUDNESS AS THE LOW-PASS HAMMER GAVE IT (its tilt, 64 harmonics) */
    double av = s->hammer_open_power == 1.0 ? s->attack_volume : pow(s->attack_volume, s->hammer_open_power);
    double fc = (s->hammer_corner_hz * (s->hammer_open_lo + s->hammer_open_slope * av)
                 * pow(2.0, s->hammer_register_slope * s->octave_position));
    double dt_ = s->hm_tonal - s->hm_level_tilt;
    double e_old = 0.0, e_new = 0.0;
    for (int h = 1; h <= n; h++) {
        double base = nv_series_volume(s, h);
        if (base == 0.0)
            continue;
        double fh = f0 * h;
        double bb = pow(base * soundboard_gain(s, fh), 2.0);
        e_new += bb * pow(s->hm_g[h - 1], 2.0);
        if (h <= s->hm_level_harmonics)
            e_old += bb * pow((double)h, 2.0 * dt_) / pow(1.0 + pow(fh / fc, s->hammer_order), 2.0);
    }
    double kk = e_new > 0.0 ? pow(e_old / e_new, 0.5) : 1.0;
    if (s->hm_n_pts) {                          /* the register's level (hammer_level_points) */
        double lf = log(f0), db = 0.0;
        if (lf <= log(s->hm_pts_hz[0]))
            db = s->hm_pts_db[0];
        else if (lf >= log(s->hm_pts_hz[s->hm_n_pts - 1]))
            db = s->hm_pts_db[s->hm_n_pts - 1];
        else
            for (int i = 0; i + 1 < s->hm_n_pts; i++) {
                double fa = s->hm_pts_hz[i], da = s->hm_pts_db[i], fb = s->hm_pts_hz[i + 1];
                if (f0 <= fb) {
                    db = da + (s->hm_pts_db[i + 1] - da) * (lf - log(fa)) / (log(fb) - log(fa));
                    break;
                }
            }
        kk *= pow(10.0, db / 20.0);
    }
    if (s->hm_vp_n) {                           /* the strings' growth with force (hammer_vel_power_points) */
        double lf = log(f0), ep = 0.0;
        if (lf <= log(s->hm_vp_hz[0]))
            ep = s->hm_vp_p[0];
        else if (lf >= log(s->hm_vp_hz[s->hm_vp_n - 1]))
            ep = s->hm_vp_p[s->hm_vp_n - 1];
        else
            for (int i = 0; i + 1 < s->hm_vp_n; i++) {
                double fa = s->hm_vp_hz[i], ea = s->hm_vp_p[i], fb = s->hm_vp_hz[i + 1];
                if (f0 <= fb) {
                    ep = ea + (s->hm_vp_p[i + 1] - ea) * (lf - log(fa)) / (log(fb) - log(fa));
                    break;
                }
            }
        if (ep != 0.0)
            kk *= pow(s->attack_volume > 1e-6 ? s->attack_volume : 1e-6, 0.5 * ep);
    }
    if (s->hm_bass_level_db != 0.0 && f0 < s->hm_bass_level_top_hz) {
        double uu = log(s->hm_bass_level_top_hz / f0) / log(s->hm_bass_level_top_hz / 27.5);
        kk *= pow(10.0, s->hm_bass_level_db * (1.0 < uu ? 1.0 : uu) / 20.0);
    }
    for (int h = 0; h < n; h++)
        s->hm_g[h] = s->hm_g[h] * kk;
}

/* a piano's inharmonicity_coefficient_for_frequency at x, by its law */
static double law_B(const VoiceInit *c, double x)
{
    if (c->b_law == 1)
        return x < c->break_hz ? c->wound_k * pow(x, c->wound_p) : c->plain_k * pow(x, c->plain_p);
    double B = c->ia + c->ib * x + c->ic * x * x + (c->id / x) + (c->ie / (x * x));
    if (c->b_law == 2) {
        double f = pymax(x, 1e-6);
        double long_ = pymin(c->scale_constant_hz_m / f, c->reference_string_max_m);
        double short_ = pymin(c->scale_constant_hz_m / f, c->case_string_max_m);
        B = B * pow(long_ / short_, 4.0);
    }
    return B;
}

void nv_voice_init(const VoiceInit *c, const VoiceSnap *tmpl, double frequency, double channel_pan,
                   double attack_volume, double channel_volume, double effort, PyRandom *rs,
                   VoiceSnap *s, VoiceNote *o)
{
    PyRandom scratch;
    if (!rs) {
        pyr_seed(&scratch, 0);
        rs = &scratch;
    }
    if (c->rnd) {                       /* RandomStrike.__init__: the strike's level and effort */
        attack_volume = attack_volume * pow(10.0, c->rnd_draws[0] / 20.0);
        effort = effort + c->rnd_draws[1];
    }
    *s = *tmpl;
    if (c->vbody)                       /* a sung voice: the note's own body (before the bore's norm) */
        sung_formants(c, frequency, s);
    double eff = effort != 0.0 ? effort : c->effort;
    s->attack_volume = attack_volume;
    if (c->bloom_seconds > 0.0 && c->bloom_slope != 0.0) {
        double av = pow(pymax(attack_volume, 1e-3), -fabs(c->bloom_slope));
        s->bloom_seconds = c->bloom_seconds * pymin(av, c->bloom_stretch_max);
    } else {
        s->bloom_seconds = c->bloom_seconds;
    }
    s->bloom_gain = c->bloom_gain;
    if (c->bloom_gain > 0.0 && c->bloom_gain_slope != 0.0)
        s->bloom_gain = c->bloom_gain * pow(pymax(attack_volume, 1e-3), c->bloom_gain_slope);
    if (c->strike_wobble_hz > 0.0 && c->strike_wobble_gain > 0.0) {
        s->n_unison = 1;
        s->unison_detune[0] = c->strike_wobble_hz;
        s->unison_gain = c->strike_wobble_gain * pow(pymax(attack_volume, 1e-3), c->strike_wobble_slope);
    }
    s->frequency_x = 415.0;
    double op = log(frequency / s->frequency_x) / log(2.0);
    s->octave_position = op;
    if (c->max_partial_hz != 0.0 && frequency != 0.0) {
        int mh = (int)(c->max_partial_hz / frequency);
        s->max_harmonic = mh > 1 ? mh : 1;
    }
    s->decay_register_factor = pow(2.0, c->decay_register_slope * op);
    if (s->kind == 4 && c->n_open > 0 && c->pluck_open != 0.0) {
        /* stopped_pluck_point: a fixed distance from the bridge, a growing
           fraction of what sounds, on the highest open string at or below */
        double n = 69.0 + 12.0 * log(pymax(frequency, 1.0) / 440.0) / log(2.0);
        int any = 0;
        double o = 0.0, lo = c->open_st[0];
        for (int i = 0; i < c->n_open; i++) {
            if (c->open_st[i] <= n + 0.5 && (!any || c->open_st[i] > o)) {
                o = c->open_st[i];
                any = 1;
            }
            if (c->open_st[i] < lo)
                lo = c->open_st[i];
        }
        if (!any)
            o = lo;
        double p = fmod(c->pluck_open * pow(2.0, (n - o) / 12.0), 1.0);
        s->strike_point = pymax(0.02, pymin(p, 1.0 - p));
    }
    if (s->kind == 4 && s->reed) {              /* a free reed: this key's flow spectrum (_reed_series) */
        double gate = s->reed_gate + s->reed_gate_oct * op;
        if (s->reed_gate_oct != 0.0)
            gate = pymin(gate, 1.08);
        double spread = s->reed_spread;
        if (s->reed_spread_oct != 0.0)
            spread = pymax(0.01, spread + s->reed_spread_oct * op);
        if (s->max_harmonic > 1024)
            s->max_harmonic = 1024;             /* (never, at 12 kHz over A0) */
        s->n_reed = nv_reed_series_cached(gate, s->reed_edge, spread, s->reed_points, s->max_harmonic, s->reed_direct,
                                          s->reed_s);
        for (int q = s->n_reed; q < 1025; q++)
            s->reed_s[q] = 0.0;                 /* (none past this key's) */
    }
    if (s->sw_on)                               /* SawariContact.__init__: the note's modes from its table */
        sw_modes(s, frequency);
    if (s->kind == 4 && s->elec) {              /* an electric guitar: its fret (ElectricGuitarProperties.__init__) */
        if (s->fc_tab)                          /* FretContact.__init__: the note's modes from its table */
            fc_modes(s, frequency, s->attack_volume);
        s->pk_sp = s->eg_sp;
        for (int q = 0; q < s->n_pk; q++)
            s->pk_q[q] = s->pk_q0[q];
        s->touch = s->touch0;
        if (s->n_touch) {
            /* A TOUCHED HARMONIC (GuitarHarmonicsProperties.__init__): of the
               touches putting the string within 4 frets of the nut (else
               all), the one the coils and the pick reach best */
            double fr[4], hd[4];
            int near = 0;
            for (int i = 0; i < s->n_touch; i++) {
                int n = s->touches[i];
                double fs = (double)frequency / n, o = 0.0;
                int under = 0;
                for (int q = 0; q < s->n_os; q++)
                    if (s->os_hz[q] <= fs * 1.0001 && (!under || s->os_hz[q] > o)) {
                        o = s->os_hz[q];
                        under = 1;
                    }
                fr[i] = under ? 12.0 * log(fs / o) / log(2.0) : 99.0;
                double sc = pow(2.0, fr[i] / 12.0), t[4];
                for (int q = 0; q < s->n_pk; q++)
                    t[q] = sin(n * PI * pymin(s->pk_q0[q] * sc, 0.5));
                hd[i] = fabs(pysum(t, s->n_pk)) * fabs(sin(n * PI * pymin(s->eg_sp * sc, 0.5)));
                if (fr[i] <= 4.0)
                    near = 1;
            }
            int best = -1;
            for (int i = 0; i < s->n_touch; i++) {
                if (near && !(fr[i] <= 4.0))
                    continue;
                if (best < 0 || hd[i] > hd[best] || (hd[i] == hd[best] && -s->touches[i] > -s->touches[best]))
                    best = i;
            }
            s->touch = s->touches[best];
        }
        if (s->n_os) {
            /* the highest open string at or under the note (the STRING's
               pitch: a touched harmonic sounds its touch above it), else the
               lowest: the pick and the coils a larger share of the shorter string */
            double f0 = frequency / (s->touch ? s->touch : 1), o = 0.0, lo = s->os_hz[0];
            int under = 0;
            for (int q = 0; q < s->n_os; q++) {
                if (s->os_hz[q] <= f0 * 1.0001 && (!under || s->os_hz[q] > o)) {
                    o = s->os_hz[q];
                    under = 1;
                }
                if (s->os_hz[q] < lo)
                    lo = s->os_hz[q];
            }
            if (!under)
                o = lo;
            double sc = pymin(pymax(1.0, f0 / o), pow(2.0, s->fret_max / 12.0));
            for (int q = 0; q < s->n_pk; q++)
                s->pk_q[q] = pymin(s->pk_q0[q] * sc, 0.5);
            s->pk_sp = pymin(s->eg_sp * sc, 0.5);
        }
        if (s->clav) {
            /* ClavinetProperties.__init__: the coil on the note's speaking
               length, and the key-up's modes */
            double f0 = frequency;
            double length = s->cl_ref_m * pow(s->cl_ref_hz / f0, f0 >= s->cl_ref_hz ? s->cl_pow : s->cl_pow_lo);
            double key = 69.0 + 12.0 * log(f0 / 440.0) / log(2.0);
            double dc = s->cl_c0 + (s->cl_c1 - s->cl_c0) * pymin(1.0, pymax(0.0, (key - 29.0) / 59.0));
            double qb = pymin(s->cl_bridge / pymax(length, 1e-6), s->cl_qmax);
            double qc = pymin(dc / pymax(length, 1e-6), s->cl_qmax);
            if (s->cl_sel == 0 || s->cl_sel == 1) {
                s->n_pk = 1;
                s->pk_q[0] = s->cl_sel == 0 ? qc : qb;
                s->pk_sign[0] = 1.0;
            } else {
                s->n_pk = 2;
                s->pk_q[0] = qc;
                s->pk_q[1] = qb;
                s->pk_sign[0] = 1.0;
                s->pk_sign[1] = s->cl_sel == 3 ? -1.0 : 1.0;
            }
            double mech = pow(10.0, -s->cl_tdb * pymax(0.0, key - 46.0) / 20.0);
            s->vk_n = 0;
            for (int i = 0; i < s->cl_nt; i++) {
                s->vk_hz[s->vk_n] = s->cl_thump[i];
                s->vk_amp[s->vk_n++] = mech;
            }
            for (int i = 0; i < s->cl_nk; i++) {
                s->vk_hz[s->vk_n] = s->cl_kh[i] * f0;
                s->vk_amp[s->vk_n++] = s->cl_ka[i];
            }
        }
        s->strike_point = s->pk_sp;
    }
    if (s->kind == 5) {                         /* an electric piano: this note's layers (ElectricPianoProperties.__init__) */
        double lay[4 * 400], f0 = s->frequency_x * pow(2.0, op);
        s->ep_a0 = ep_deflection(s);
        int n = nv_ep_layers_cached(s->ep_kind, s->ep_p, s->ep_a0, s->ep_rho, f0, op, s->ep_harm, s->ep_terms,
                                    s->ep_max_hz, s->ep_floor_db, 0, lay, 400);
        s->n_lay = n < 400 ? n : 400;
        double tb = s->tb_coeff * pow(frequency, s->tb_power);
        for (int q = 0; q < s->n_lay; q++) {
            s->ep_r[q] = lay[4 * q];
            s->ep_n[q] = lay[4 * q + 1];
            s->ep_w[q] = lay[4 * q + 2];
            s->mode_phases[q] = lay[4 * q + 3] + (lay[4 * q + 2] < 0.0 ? PI : 0.0);    /* mode_phase */
        }
        for (int q = 0; q < s->n_tb; q++) {
            s->ep_r[s->n_lay + q] = tb * s->tb_ratio[q] / frequency;
            s->mode_phases[s->n_lay + q] = 0.0;
        }
        for (int q = s->n_lay + s->n_tb; q < 408; q++)
            s->ep_r[q] = 0.0;
        for (int q = s->n_lay; q < 400; q++)
            s->ep_n[q] = s->ep_w[q] = 0.0;
        for (int q = s->n_lay + s->n_tb; q < 400; q++)
            s->mode_phases[q] = 0.0;
        s->n_mp = s->n_lay + s->n_tb;
        s->max_harmonic = s->n_lay + s->n_tb;
    }
    if (s->kind == 2 && (s->n_pts || s->low_set))  /* an organ pipe: its register's table (mode_gains_here) */
        s->n_mm = nv_mode_gains_at(s, s->frequency_x * pow(2.0, s->octave_position), s->mm_gain);
    if (s->kind == 4 && s->hvt_bore)            /* a blown reed's table, at its register (mode_gains_here) */
        s->n_hvt = nv_mode_gains_at(s, s->frequency_x * pow(2.0, s->octave_position), s->hvt);
    o->pitch_jitter = c->pitch_jitter_cents != 0.0
        ? pow(2.0, pyr_uniform(rs, -c->pitch_jitter_cents, c->pitch_jitter_cents) / 1200.0) - 1.0 : 0.0;
    o->attack_jitter = c->timing_jitter_seconds != 0.0 ? pyr_uniform(rs, 0.0, c->timing_jitter_seconds) : 0.0;
    if (c->tape_key_cents != 0.0) {
        /* A MELLOTRON's STRIP (MellotronMixin.__init__): each key's own
           tuning, random.Random(0x7A9E0 + the key), over the note's draw */
        const int km = (int)nearbyint(69 + 12 * log(frequency / 440.0) / log(2));
        PyRandom tr;
        pyr_seed(&tr, 0x7A9E0 + (long long)km);
        o->pitch_jitter = pow(2.0, pyr_uniform(&tr, -c->tape_key_cents, c->tape_key_cents) / 1200.0) - 1.0;
    }
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
    if (c->n_vtrim) {
        /* the volume back on the square law, at the velocity it came from (_np_interp) */
        double x = 127.0 * pow(pymax(attack_volume, 0.0), 0.5), d;
        int n = c->n_vtrim;
        if (x <= c->vtrim_v[0]) {
            d = c->vtrim_db[0];
        } else {
            d = c->vtrim_db[n - 1];
            for (int i = 0; i + 1 < n; i++)
                if (x <= c->vtrim_v[i + 1]) {
                    double x0 = c->vtrim_v[i], y0 = c->vtrim_db[i], x1 = c->vtrim_v[i + 1], y1 = c->vtrim_db[i + 1];
                    d = y0 + (y1 - y0) * (x - x0) / (x1 - x0);
                    break;
                }
        }
        s->gain *= pow(10.0, d / 20.0);
    }
    if (s->bore_corner_hz != 0.0)
        bore_norm(c, s);
    if (s->or_set) {
        /* MusicBoxProperties.mode_gains_here: its key's octave below */
        double f = s->frequency_x * pow(2.0, s->octave_position);
        long long key = (long long)nearbyint(69 + 12 * log(f / 440.0) / log(2.0));
        PyRandom r;
        pyr_seed(&r, key * 7919 + 10);
        double draw = pyr_random(&r), lev = pyr_uniform(&r, s->or_db[0], s->or_db[1]);
        int on = f / 2.0 >= s->or_lowest_hz * pow(2.0, -0.5 / 12.0) && draw < s->or_share;
        s->or_g = on ? pow(10.0, lev / 20.0) : 0.0;
    }
    /* place() */
    o->pan_angle = stage_angle(channel_pan);
    s->position_x = op * c->octave_width + c->seat_x;
    s->position_z = c->position_z;
    s->hrtf_beta = 2.0 * c->sound_speed / c->head_radius;
    double e[4];
    voice_hrtf_at(c, o->pan_angle, s->position_x, e);
    o->left_incidence = e[0]; o->right_incidence = e[1];
    o->left_hrtf_delay = e[2]; o->right_hrtf_delay = e[3];
    o->attack_time = c->attack_time;
    o->chiff_volume = c->chiff_volume;
    o->sustain_jitter = c->sustain_jitter;
    if (c->strike_noise_slope != 0.0 && c->chiff_volume != 0.0) {
        /* the stroke's force: the strike's noise, and the ring's jitter with it */
        double av = pow(pymax(attack_volume, 1e-3), c->strike_noise_slope);
        o->chiff_volume = c->chiff_volume * av;
        o->sustain_jitter = c->sustain_jitter * av;
    }
    if (s->jit_sus == 1)                        /* partial_jitter's sustain_jitter, the note's */
        s->head_jitter = o->sustain_jitter;
    else if (s->jit_sus == 2)
        s->wire_jitter = o->sustain_jitter;
    if (c->kind != 0) {
        /* a kit drum, a mode set: SynthProperties' constructor and no more;
           its B the class's coefficient (no law: inharmonicity_dynamic off) */
        o->B = o->inharmonicity_coefficient;
        if (c->b_law == 3)              /* the steel's law (inharmonicity_coefficient_for_frequency) */
            o->B = c->law_k * pow(frequency, c->law_p);
        else if (c->b_law == 4) {       /* the dulcimer's: its bass bridge's own, the steel's law over it */
            o->B = frequency < c->bb_hz ? c->bb_B : c->law_k * pow(frequency, c->law_p);
            if (frequency < c->bb_hz && c->n_btab) {   /* ...its bass bridge by course (bass_bridge_table) */
                double key = 69.0 + 12.0 * log(frequency / 440.0) / log(2.0);
                int n = c->n_btab;
                if (key <= c->btab_key[0])
                    o->B = c->btab_B[0];
                else {
                    o->B = c->btab_B[n - 1];
                    for (int i = 0; i + 1 < n; i++)
                        if (key <= c->btab_key[i + 1]) {
                            o->B = c->btab_B[i] + (c->btab_B[i + 1] - c->btab_B[i]) * (key - c->btab_key[i])
                                   / (c->btab_key[i + 1] - c->btab_key[i]);
                            break;
                        }
                }
            }
        }
        else if (c->b_law == 6)         /* a bass string's, from its core (ElectricBassProperties) */
            o->B = sp_b(s, frequency);
        else if (c->b_law == 5) {       /* the Clavinet's published table, linear in the key */
            double key = 69.0 + 12.0 * log(frequency / 440.0) / log(2.0);
            int n = c->n_btab;
            if (key <= c->btab_key[0])
                o->B = c->btab_B[0];
            else {
                o->B = c->btab_B[n - 1];
                for (int i = 0; i + 1 < n; i++)
                    if (key <= c->btab_key[i + 1]) {
                        o->B = c->btab_B[i] + (c->btab_B[i + 1] - c->btab_B[i]) * (key - c->btab_key[i])
                               / (c->btab_key[i + 1] - c->btab_key[i]);
                        break;
                    }
            }
        }
        if (c->rnd) {                   /* ...and RandomStrike's: its pitch and lateness */
            o->pitch_jitter = (1.0 + o->pitch_jitter) * pow(2.0, c->rnd_draws[2] / 1200.0) - 1.0;
            o->attack_jitter = o->attack_jitter + c->rnd_draws[3];
        }
        return;
    }
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
    if (s->decay_by_hz) {
        /* GrandPianoProperties.harmonic_decay's B and impedance ratio, at the
           note's frequency as Python rebuilds it (frequency_x * 2 ** op) */
        double f0 = s->frequency_x * pow(2.0, s->octave_position);
        s->dz_B = law_B(c, f0);
        s->dz_zr = string_z(440.0, s->dz_scale, s->dz_lmax) / string_z(f0, s->dz_scale, s->dz_lmax);
    }
    /* blockrender: the law's B at the note (inharmonicity_coefficient_for_frequency) */
    o->B = law_B(c, frequency);
    if (s->sp_curve_set) {                      /* GrandPianoProperties.strike_curve: the key's strike point */
        int midi = (int)rint(69.0 + 12.0 * log(frequency / 440.0) / log(2.0));
        double oo = (midi - 69) / 12.0;
        double sp = 1.0 / (s->sp_curve[0] + s->sp_curve[1] * oo + s->sp_curve[2] * oo * oo);
        s->strike_point = 0.5 < sp ? 0.5 : (0.02 > sp ? 0.02 : sp);
    }
    if (s->hammer_model)
        hm_note(s);
}
