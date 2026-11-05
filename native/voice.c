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
    double f = v->frequency_x * pow(2.0, v->octave_position) * nv_mode_ratio(v, harmonic);
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
        if (!(1 <= harmonic && harmonic <= v->n_mm))
            return 0.0;
        double g = v->gain * v->mm_gain[harmonic - 1];
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
        if (harmonic % 2 == 0 && v->even_db_set)
            r *= pow(10.0, v->even_harmonic_db / 20.0);
        return r;
    }
    if (v->kind == 4 || v->kind == 6 || v->kind == 2) {     /* SynthProperties': the pluck's comb (a Moog's body's norm; a pipe's with no table) */
        double r = v->gain / pow((double)harmonic, v->attack_dampening) * (harmonic <= 256 ? v->comb[harmonic] : 0.0);
        if (harmonic % 2 == 0 && v->even_db_set)
            r *= pow(10.0, v->even_harmonic_db / 20.0);
        return r;
    }
    if (v->kind == 3)                           /* the pluck comb at plucked_harmonic 0: whole */
        return v->gain / pow((double)harmonic, v->attack_dampening) * (harmonic % 1000000 ? 1.0 : 0.0);
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
        return v->bridge_gain * slope / (1.0 + pow(fn / v->bridge_corner_hz, v->bridge_order));
    }
    double body = 1.0 + v->board_body_gain * exp(
        -(pow(log(fn / v->board_body_hz), 2.0)) / (2.0 * pow(v->board_body_width, 2.0)));
    double high = 1.0 / (1.0 + pow(fn / v->board_high_hz, v->board_high_order));
    double low = 1.0 / (1.0 + pow(v->board_low_hz / fn, v->board_kind == 1 ? v->board_low_order : 2.0));
    return body * high * low;
}

static double harmonic_volume(const VoiceSnap *v, int harmonic);

/* the voice's harmonic_volume -- a throat's tilted and its vowel moved --
   and SampledBreak's: nothing at or above its Nyquist */
double nv_harmonic_volume(const VoiceSnap *v, int harmonic)
{
    double s = harmonic_volume(v, harmonic);
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

/* GrandPianoProperties.harmonic_volume, on SynthProperties' (no bore) */
static double harmonic_volume(const VoiceSnap *v, int harmonic)
{
    double s = nv_series_volume(v, harmonic);
    if (s == 0.0)
        return 0.0;
    if (v->kind != 0) {                         /* SynthProperties': its bore, if it has one */
        if (v->bore_corner_hz != 0.0)
            s = s * bore_gain(v, v->frequency_x * pow(2.0, v->octave_position) * nv_mode_ratio(v, harmonic))
                * v->bore_norm;
        if (v->noisy)                           /* ...and the noise's roll-off and trim */
            return s * hf_rolloff(v, nv_mode_ratio(v, harmonic)) * band_trim(v, harmonic);
        return s;
    }
    double fn = v->frequency_x * pow(2.0, v->octave_position) * harmonic;
    double fc = (v->hammer_corner_hz * (v->hammer_open_lo + v->hammer_open_slope * v->attack_volume)
                 * pow(2.0, v->hammer_register_slope * v->octave_position));
    return s / (1.0 + pow(fn / fc, v->hammer_order)) * soundboard_gain(v, fn);
}

/* SynthProperties.harmonic_decay by where the mode sits; CymbalProperties'
 * by octaves from the ring's peak */
static double mode_decay(const VoiceSnap *v, int harmonic)
{
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

double nv_harmonic_decay(const VoiceSnap *v, int harmonic)
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
    double h = (double)harmonic;                /* mode_ratios None */
    double base = v->decay_db + v->harmonic_decay_db * h * pow(h, v->harmonic_decay_dampening);
    base = base * v->decay_register_factor;
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

int nv_unison_voices(const VoiceSnap *v, double frequency, int harmonic, double harmonic_decay, double *out)
{
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
        for (int i = 0; i < v->n_unison; i++) {
            out[5 * i + 0] = v->unison_gain; out[5 * i + 1] = v->unison_detune[i]; out[5 * i + 2] = 0.0;
            out[5 * i + 3] = harmonic_decay; out[5 * i + 4] = 0.0;
        }
        return v->n_unison;
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
    double g = v->noisy                         /* NoisyPercussionMixin: the wash rolled off too */
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

int nv_voice_vibrato(const VoiceSnap *v, double frequency, int index, double *out)
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
    if (v->n_ma) {                              /* TR808Properties.aftersound_partial */
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
}

void nv_voice_regain(const VoiceInit *c, VoiceSnap *s, double k)
{
    s->gain *= k;
    if (s->bore_corner_hz != 0.0)
        bore_norm(c, s);
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
    if (s->kind == 4 && s->elec) {              /* an electric guitar: its fret (ElectricGuitarProperties.__init__) */
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
            double length = s->cl_ref_m * pow(s->cl_ref_hz / f0, s->cl_pow);
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
        else if (c->b_law == 4)         /* the dulcimer's: its bass bridge's own, the steel's law over it */
            o->B = frequency < c->bb_hz ? c->bb_B : c->law_k * pow(frequency, c->law_p);
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
