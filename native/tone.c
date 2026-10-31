/* tone.c -- a note's tone in C: blockrender._note_stops' path for a voice
 * with one stop (not an organ) and none of its extras, through
 * _Emitter.emit_partial (the direct row, the room's images), writing the
 * note's rows in EMIT_COLS' order -- bit for bit the Python's (checked row by
 * row: examples/native_check.py --tone).
 *
 * For each harmonic m: the string's partial (string_partial), its level
 * (harmonic_volume) and decay (partial_decay), what radiates toward the
 * listener (radiation_gain) and each ear's shadow (hrtf_gain), its chiff
 * weight and vibrato; the row; then each unison string's (unison_voices,
 * unison_partial) at the same level times its gain. Each row is followed by
 * its images (roomcore.c's reflection_terms over the note's image sources,
 * each image's ears by hrtf_at). The room's power tallies (_QACC) are
 * carried in and out, so their sums add in the same order as Python's.
 */
#include <stddef.h>
#include "voice.c"

#define NCOLS 50

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

/* SynthProperties.hrtf_at(x, z, y): (left inc, right inc, left delay, right delay) */
static void hrtf_at(const VoiceSnap *v, const ToneIn *t, double position_x, double position_z,
                    double position_y, double *out)
{
    double z = position_z, y = position_y;
    double th = t->pan_angle;
    if (th != 0.0) {
        double px = position_x * cos(th) + y * sin(th);
        double py = -position_x * sin(th) + y * cos(th);
        position_x = px;
        y = py;
    }
    double dist = sqrt(pow(position_x, 2.0) + y * y + z * z);
    double distance = t->head_radius > dist ? t->head_radius : dist;      /* max(d, head) */
    double c = v->room[4];
    double base_delay = distance / c;
    double cos_to_right = position_x / distance;
    for (int ear = 0; ear < 2; ear++) {
        double ct = ear == 0 ? -cos_to_right : cos_to_right;
        double m = ct < 1.0 ? ct : 1.0;
        m = m > -1.0 ? m : -1.0;
        double theta = acos(m);
        double offset = theta <= PI / 2 ? -cos(theta) : (theta - PI / 2);
        out[ear] = theta;
        out[2 + ear] = base_delay + offset * t->head_radius / c;
    }
}

typedef struct {
    double *rows;
    int n, cap;
} Rows;

static double *row_new(Rows *R)
{
    if (R->n >= R->cap)
        return NULL;
    return R->rows + NCOLS * (R->n++);
}

/* _Emitter.emit_partial for a direct partial of this note (no reverse, no
 * fold, no hammer-on, no compressor, no GS EQ, the source at its own
 * distance), and its images. Returns 0 if the row store is full. */
static int emit(const VoiceSnap *v, const ToneIn *t, Rows *R, double *qacc, double *azimuth,
                const double *terms, int nterms,
                double om, double ampL, double ampR, double ampM, double nomf, double non, double noff,
                double fa, double re, double ch, double logr, double logrA, double aft, double sus,
                double cv, double cc, double crl, double sj, double csc, double gr, double cr, double ph0,
                double player, const double *VB, double pos_x)
{
    om = om * t->jitter_scale;
    if (t->transposed && om >= t->nyq_om)
        return 1;
    double dl = t->dl, dr = t->dr, px = pos_x, pz = t->pos_z;
    double am0 = ampM;
    double rd = v->room[0];
    *azimuth = atan2(px, rd > 1e-6 ? rd : 1e-6);
    double cbw = t->cbw1 > 0.0 ? t->cbw1 / (1e-6 > nomf ? 1e-6 : nomf) : t->cbw0;
    double vd0 = VB[0];
    if (t->sv[0] > 0.0)
        vd0 = vd0 + t->sv[0] * (pow(2.0, t->sound_vib_depth_cents / 1200.0) - 1.0);
    else if (t->sv[0] < 0.0)
        vd0 = vd0 * (1.0 + t->sv[0]);
    double *r = row_new(R);
    if (!r)
        return 0;
    double row[NCOLS] = {
        om, -om * (non + dl) + ph0, -om * (non + dr) + ph0, ampL, ampR, ampM, t->channel,
        px, pz, *azimuth, 1.0,
        nomf, non, noff, fa, re, ch, logr, logrA, aft, sus, cv, cc, crl, sj, csc, cbw,
        t->tb[0], t->tb[1], t->tb[2], t->gl[0], t->gl[1], t->gl[2],
        vd0, VB[1] * t->sv[1], VB[2], t->vibrato_delay, dl, dr,
        gr, cr, t->br, player, t->fx, t->mk, 0.0,
        t->fm_omega, non - floor(non),
        t->fm_omega != 0.0 ? -t->fm_omega * (non + dl) + t->fm_phase : 0.0,
        t->fm_omega != 0.0 ? -t->fm_omega * (non + dr) + t->fm_phase : 0.0};
    for (int k = 0; k < NCOLS; k++)
        r[k] = row[k];
    /* the room's power: at the band nearest in log frequency (directivity Q 1:
       directivity_radius <= 0, which native.py requires) */
    if (ampM > 0.0) {
        double lf = nomf > 1e-6 ? nomf : 1e-6;
        int bi = 0;
        double bd = fabs(log(lf / t->room_bands[0]));
        for (int i = 1; i < 9; i++) {
            double d = fabs(log(lf / t->room_bands[i]));
            if (d < bd) {
                bi = i;
                bd = d;
            }
        }
        double q = 1.0;
        double e = am0 * am0;
        qacc[2 * bi] += e;
        qacc[2 * bi + 1] += e / (q > 1e-6 ? q : 1e-6);
    }
    if (!t->reflect)
        return 1;
    double direct_az = *azimuth;
    double omi = om / t->jitter_scale * t->jitter_scale;
    int skip = t->transposed && omi >= t->nyq_om;
    double sr = t->sr;
    for (int k = 0; k < nterms; k++) {
        const double *T_ = terms + 9 * k;   /* rg, rdelay, ix, iy, iz, rli, rri, rld, rrd */
        double ix = T_[2], iy = T_[3], iz = T_[4];
        *azimuth = atan2(ix, iy > 1e-6 ? iy : 1e-6);
        double gm = ampM * T_[0];
        double image_delay = (double)((long long)(non + T_[1] * sr) - (long long)non);
        if (skip)
            continue;
        double gl_ = gm * nv_hrtf_gain(v, nomf, T_[5]), gr_ = gm * nv_hrtf_gain(v, nomf, T_[6]);
        double ni = non + T_[1] * sr, fi = noff + T_[1] * sr;
        double dli = T_[7] * sr, dri = T_[8] * sr;
        double *q = row_new(R);
        if (!q)
            return 0;
        double irow[NCOLS] = {
            omi, -omi * (ni + dli) + ph0, -omi * (ni + dri) + ph0, gl_, gr_, gm, t->channel,
            ix, iz, *azimuth, 0.0,
            nomf, ni, fi, fa, re, ch, logr, logrA, aft, sus, cv, cc, crl, sj, csc, cbw,
            t->tb[0], t->tb[1], t->tb[2], t->gl[0], t->gl[1], t->gl[2],
            vd0, VB[1] * t->sv[1], VB[2], t->vibrato_delay, dli, dri,
            gr, cr, t->br, player, t->fx, t->mk, image_delay,
            t->fm_omega, ni - floor(ni),
            t->fm_omega != 0.0 ? -t->fm_omega * (ni + dli) + t->fm_phase : 0.0,
            t->fm_omega != 0.0 ? -t->fm_omega * (ni + dri) + t->fm_phase : 0.0};
        for (int c = 0; c < NCOLS; c++)
            q[c] = irow[c];
    }
    *azimuth = direct_az;
    return 1;
}

/* The room's terms for this note's direct sound at frequency f: roomcore's
 * reflection_terms over the images, then each image's ears and the delay
 * past the stage (emit_partial's _terms). terms: 9 a kept image. */
static int note_terms(const VoiceSnap *v, const ToneIn *t, double f, double px, double pz,
                      int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
                      double *terms)
{
    int keep[64];
    double g[64], dly[64];
    if (nimg > 64)
        return -1;
    double sx = px * 1.0, sy = v->room[0] * 1.0, sz = pz * 1.0;
    double stage = sqrt(px * px + pow(t->listener_distance, 2.0) + pz * pz);
    int k = reflection_terms(v->room, v->ahz, v->alpha, v->scat,
                             f, sx, sy, sz, 0.0, 0, nimg, nsurf, surf, img, mir, keep, g, dly);
    for (int i = 0; i < k; i++) {
        const double *im = img + 3 * keep[i];
        double e[4];
        hrtf_at(v, t, im[0], im[2], im[1], e);
        double sh = (sqrt(pow(im[0], 2.0) + pow(im[1], 2.0) + pow(im[2], 2.0)) - stage) / v->room[4];
        double *T_ = terms + 9 * i;
        T_[0] = g[i]; T_[1] = dly[i]; T_[2] = im[0]; T_[3] = im[1]; T_[4] = im[2];
        T_[5] = e[0]; T_[6] = e[1]; T_[7] = e[2] - sh; T_[8] = e[3] - sh;
    }
    return k;
}

/* blockrender._note_stops for a one-stop voice (rp is the voice, no organ,
 * rank, choir, wind, bloom, feedback, pre-pluck, section or phase spread):
 * the note's rows into rows (cap of them, NCOLS each), each harmonic's (hf,
 * hv, dB/s) into transverse; qacc[18] carried; *azimuth the emitter's after.
 * Returns the rows written, -1 if the store was too small. */
int nv_tone(const VoiceSnap *v, const ToneIn *t,
            int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
            double *rows, int cap, double *transverse, int *ntrans, double *qacc, double *azimuth)
{
    Rows R = {rows, 0, cap};
    double terms_main[9 * 64], terms_u[9 * 64];
    double sr = t->sr;
    double VB0[3] = {0.0, 5.5, 0.0};
    double pos_x = t->pos_x0;
    *ntrans = 0;
    for (int m = 1; m < v->max_harmonic + 1; m++) {
        double hh[2];
        if (!nv_string_partial(v, t->f0, 1.0, m, t->B, hh))
            break;
        double h = hh[0], hf = hh[1];
        if (hf > sr / 2)
            break;
        double hv = nv_harmonic_volume(v, m);
        if (hv == 0.0)
            continue;
        double pd[4];
        nv_partial_decay(v, t->f0, m, pd);          /* dbps, logr, aftL, logrA */
        double gM = hv * t->gain * nv_radiation_gain(v, hf, 0.0, 0);
        double gL = gM * nv_hrtf_gain(v, hf, t->li), gR = gM * nv_hrtf_gain(v, hf, t->ri);
        double cvp = t->cv * nv_chiff_harmonic_gain(v, h);
        double VB[3];
        if (!nv_voice_vibrato(v, t->f0, 0, VB)) {
            VB[0] = VB0[0]; VB[1] = VB0[1]; VB[2] = VB0[2];
        }
        double non_m = t->non + 0.0;
        double mph = 0.0;
        int nt_ = 0;
        if (t->reflect) {
            nt_ = note_terms(v, t, hf, pos_x, t->pos_z, nimg, nsurf, surf, img, mir, terms_main);
            if (nt_ < 0)
                return -1;
        }
        if (!emit(v, t, &R, qacc, azimuth, terms_main, nt_, 2 * PI * hf / sr, gL, gR, gM, hf, non_m, t->noff,
                  t->fade, t->rel, t->chiff, pd[1], pd[3], pd[2], t->sustain_level, cvp, t->cc, t->crl, t->sjit,
                  t->csc, t->gr, t->cr, mph, 0.0, VB, pos_x))
            return -1;
        transverse[3 * *ntrans] = hf;
        transverse[3 * *ntrans + 1] = hv;
        transverse[3 * *ntrans + 2] = pd[0];
        (*ntrans)++;
        double uv[20];
        int nu = nv_unison_voices(v, t->f0, m, pd[0], uv);
        for (int ui = 0; ui < nu; ui++) {
            double gm = uv[5 * ui], off_hz = uv[5 * ui + 1], dr = uv[5 * ui + 2], ud = uv[5 * ui + 3];
            double uph = uv[5 * ui + 4];
            if (!nv_voice_vibrato(v, t->f0, ui + 1, VB)) {
                VB[0] = VB0[0]; VB[1] = VB0[1]; VB[2] = VB0[2];
            }
            double up[2];
            nv_unison_partial(hf, off_hz, dr, ud, up);
            double uf = up[0], ulr = up[1];
            if (uf <= 0 || uf > sr / 2)
                continue;
            double ugL = gL * gm, ugR = gR * gm;
            double non_u = t->non + 0.0;
            int ntu = 0;
            if (t->reflect) {
                ntu = note_terms(v, t, uf, pos_x, t->pos_z, nimg, nsurf, surf, img, mir, terms_u);
                if (ntu < 0)
                    return -1;
            }
            if (!emit(v, t, &R, qacc, azimuth, terms_u, ntu, 2 * PI * uf / sr, ugL, ugR, gM * gm, uf, non_u,
                      t->noff, t->fade, t->rel, t->chiff, ulr, pd[3], pd[2], t->sustain_level, cvp, t->cc,
                      t->crl, t->sjit, t->csc, t->gr, t->cr, 2 * PI * uph + 0.0, (double)(ui + 1), VB, pos_x))
                return -1;
        }
        pos_x = t->pos_x_props;     /* em.pos_x = the voice's position, after each harmonic */
    }
    return R.n;
}

/* blockrender._note_strike_noise for a single burst at the onset (no flams,
 * no crowd, no recorded clicks, no tail, no layers): each band of the
 * voice's strike_noise_db (hz[], db[]) a noise row (the caller sets the
 * noise width in t->cbw0/1 and no room images, t->reflect 0), its level the
 * band's with the register's tilt (reg) and the calibration (scal), decaying
 * at slr from bon for slen samples. qacc and *azimuth as nv_tone's. Returns
 * the rows written, -1 if the store was too small. */
int nv_strike(const VoiceSnap *v, const ToneIn *t, int nb, const double *hz, const double *db,
              double reg, double bdb, double scal, double slr, double sfade, double slen, double bon,
              double pos_x, double *rows, int cap, double *qacc, double *azimuth)
{
    Rows R = {rows, 0, cap};
    double VB[3] = {0.0, 5.5, 0.0};
    double sr = t->sr;
    for (int i = 0; i < nb; i++) {
        double hf = hz[i];
        if (hf >= 0.45 * sr)
            continue;
        double gM = v->gain * pow(10.0, (db[i] + reg + bdb + scal) / 20.0);
        if (!emit(v, t, &R, qacc, azimuth, NULL, 0, 2 * PI * hf / sr,
                  gM * nv_hrtf_gain(v, hf, t->li) * 1.0, gM * nv_hrtf_gain(v, hf, t->ri) * 1.0, gM, hf,
                  bon, bon + slen, sfade, 0.01 * sr, t->chiff, slr, 0.0, 0.0, 0.0, 0.0, t->cc, t->crl,
                  0.0, t->csc, -1.0, 0.0, 0.0, 0.0, VB, pos_x))
            return -1;
    }
    return R.n;
}
