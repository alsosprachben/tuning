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
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <pthread.h>
#include "voice.c"
#include "strings.c"      /* the register's string bank */
#include "exactmath.c"    /* array math as libm does it */



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

/* SynthProperties.section_seats()[i]: player i's ears at its desk */
void nv_section_seat(const VoiceSnap *v, const ToneIn *t, int i, double *out)
{
    hrtf_at(v, t, t->pos_x_props + v->sect_dx[i], t->pos_z, t->listener_distance, out);
}

/* SynthProperties.sphere_mean_directivity: <D^2> over the sphere for a
   piston of radius a (180 polar steps, sin-weighted) -- kept, as the
   class's _Q_CACHE keeps it, under (round(a, 5), round(f, 1), round(floor,
   3)) for the whole process: a radius rounding to one already asked takes
   that one's value */
static pthread_mutex_t q_lock = PTHREAD_MUTEX_INITIALIZER;
static struct { char key[96]; double v; } *q_tab = NULL;
static size_t q_n = 0, q_cap = 0;

static double sphere_mean(const VoiceSnap *v, double f, double a)
{
    if (a <= 0.0)
        return 1.0;
    char key[96];
    snprintf(key, sizeof key, "%.5f|%.1f|%.3f", a, f, v->room[2]);
    pthread_mutex_lock(&q_lock);
    size_t h = 5381;
    for (const char *c = key; *c; c++)
        h = h * 33 + (unsigned char)*c;
    if (q_cap) {
        for (size_t i = h & (q_cap - 1);; i = (i + 1) & (q_cap - 1)) {
            if (!q_tab[i].key[0])
                break;
            if (!strcmp(q_tab[i].key, key)) {
                double got = q_tab[i].v;
                pthread_mutex_unlock(&q_lock);
                return got;
            }
        }
    }
    double k = 2.0 * PI * f / v->room[4];
    int n = 180;
    double total = 0.0, weight = 0.0;
    for (int i = 0; i < n; i++) {
        double theta = (i + 0.5) * PI / n;
        double s = sin(theta);
        double x = fabs(k * a * s);
        double d;
        if (x < 1e-6)
            d = 1.0;
        else {
            d = fabs(2.0 * bessel_j1(x) / x);
            d = v->room[2] > d ? v->room[2] : d;
        }
        total += d * d * s;
        weight += s;
    }
    double got = weight != 0.0 ? total / weight : 1.0;
    if (2 * (q_n + 1) > q_cap) {                /* grow: rehash into twice the table */
        size_t nc = q_cap ? 2 * q_cap : 1024;
        void *old = q_tab;
        size_t oc = q_cap;
        q_tab = calloc(nc, sizeof *q_tab);
        q_cap = nc;
        for (size_t j = 0; j < oc; j++) {
            char *ok = ((char *)old) + j * sizeof *q_tab;
            if (!ok[0])
                continue;
            size_t hh = 5381;
            for (const char *c = ok; *c; c++)
                hh = hh * 33 + (unsigned char)*c;
            size_t i = hh & (q_cap - 1);
            while (q_tab[i].key[0])
                i = (i + 1) & (q_cap - 1);
            memcpy(&q_tab[i], ok, sizeof *q_tab);
        }
        free(old);
    }
    size_t i = h & (q_cap - 1);
    while (q_tab[i].key[0])
        i = (i + 1) & (q_cap - 1);
    strcpy(q_tab[i].key, key);
    q_tab[i].v = got;
    q_n++;
    pthread_mutex_unlock(&q_lock);
    return got;
}

/* the cache's value for (f, a), at this floor and speed of sound (Python's
   sphere_mean_directivity in the engine's modes: one cache for both) */
double nv_sphere_mean(double f, double a, double floor_, double sound_speed)
{
    VoiceSnap v;
    v.room[2] = floor_;
    v.room[4] = sound_speed;
    return sphere_mean(&v, f, a);
}

/* SynthProperties.directivity_factor(f, px, pz, radius): Q */
static double directivity_factor(const VoiceSnap *v, double f, double px, double pz, double radius)
{
    double mean = sphere_mean(v, f, radius);
    if (mean <= 0.0)
        return 1.0;
    double d = directivity_gain(v->room, f, px, pz, radius, 1);
    return (d * d) / mean;
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

/* _Emitter.emit_partial for a direct partial of this note (no fold, no
 * compressor, no GS EQ, the source at its own distance), and
 * its images. Returns 0 if the row store is full. */
/* blockrender's _refl_norm: sqrt(E(1) / E(d)), E = 1 + the images'
 * energy against the direct sound, for this voice at f moved out by d --
 * the images worked out where the source stands (kept for the last place) */
/* ...MEMOISED AS THE PYTHON's: keyed by f rounded to 0.1 Hz (round(f, 1)),
 * the place, the radius, d and the class, its value the first f's of the key;
 * emptied at PREP_MEMO_MAX entries */
typedef struct {
    long long cls;
    double rf, px, pz, rad, d, val;
    int hr, used;
} RnEntry;
#define RN_CAP (1 << 17)
#define RN_MAX 50000                /* blockrender.PREP_MEMO_MAX */
static RnEntry *rn_tab;
static int rn_n;
static pthread_mutex_t rn_mu = PTHREAD_MUTEX_INITIALIZER;

void nv_refl_memo_reset(void)
{
    pthread_mutex_lock(&rn_mu);
    if (rn_tab)
        memset(rn_tab, 0, sizeof(RnEntry) * RN_CAP);
    rn_n = 0;
    pthread_mutex_unlock(&rn_mu);
}

static double refl_norm_raw(const VoiceSnap *v, const ToneIn *t, double f, double px, double pz, double d);

static double refl_norm(const VoiceSnap *v, const ToneIn *t, double f, double px, double pz, double d)
{
    char b[64];
    snprintf(b, sizeof b, "%.1f", f);
    double rf = strtod(b, NULL);
    double rad = t->has_radius ? t->radius : 0.0;
    unsigned long long h = 1469598103934665603ULL;
    double ks[5] = {rf, px, pz, rad, d};
    for (int i = 0; i < 5; i++) {
        unsigned long long x;
        memcpy(&x, &ks[i], 8);
        h = (h ^ x) * 1099511628211ULL;
    }
    h = (h ^ (unsigned long long)t->cls) * 1099511628211ULL;
    pthread_mutex_lock(&rn_mu);
    if (!rn_tab)
        rn_tab = (RnEntry *)calloc(RN_CAP, sizeof(RnEntry));
    unsigned long i = (unsigned long)(h & (RN_CAP - 1));
    while (rn_tab[i].used) {
        RnEntry *e = &rn_tab[i];
        if (e->cls == t->cls && e->rf == rf && e->px == px && e->pz == pz && e->rad == rad && e->hr == t->has_radius
            && e->d == d) {
            double v_ = e->val;
            pthread_mutex_unlock(&rn_mu);
            return v_;
        }
        i = (i + 1) & (RN_CAP - 1);
    }
    pthread_mutex_unlock(&rn_mu);
    double g = refl_norm_raw(v, t, f, px, pz, d);
    pthread_mutex_lock(&rn_mu);
    if (rn_n >= RN_MAX) {                   /* if len(_RNORM) >= PREP_MEMO_MAX: _RNORM.clear() */
        memset(rn_tab, 0, sizeof(RnEntry) * RN_CAP);
        rn_n = 0;
        i = (unsigned long)(h & (RN_CAP - 1));
    }
    while (rn_tab[i].used)
        i = (i + 1) & (RN_CAP - 1);
    RnEntry e = {t->cls, rf, px, pz, rad, d, g, t->has_radius, 1};
    rn_tab[i] = e;
    rn_n++;
    pthread_mutex_unlock(&rn_mu);
    return g;
}

static double refl_norm_raw(const VoiceSnap *v, const ToneIn *t, double f, double px, double pz, double d)
{
    static _Thread_local double lp[4] = {NAN, NAN, NAN, NAN};
    static _Thread_local int ln[2], lns[2][64], ls[2][64 * 8];
    static _Thread_local double li[2][64 * 3], lm[2][64 * 3];
    if (!(lp[0] == px && lp[1] == pz && lp[2] == d && lp[3] == v->room[0])) {
        for (int q = 0; q < 2; q++) {
            double m = q ? d : 1.0;
            ln[q] = nv_images(t->planes, t->order, px * m, v->room[0] * m, pz * m, 64, lns[q], ls[q], li[q], lm[q]);
            if (ln[q] < 0)
                ln[q] = 0;
        }
        lp[0] = px; lp[1] = pz; lp[2] = d; lp[3] = v->room[0];
    }
    double e[2];
    for (int q = 0; q < 2; q++) {
        double m = q ? d : 1.0;
        int keep[64];
        double g[64], dly[64], sq[64];
        int k = reflection_terms(v->room, v->ahz, v->alpha, v->scat, f, px * m, v->room[0] * m, pz * m, t->radius,
                                 t->has_radius, ln[q], lns[q], ls[q], li[q], lm[q], keep, g, dly);
        for (int j = 0; j < k; j++)
            sq[j] = g[j] * g[j];
        e[q] = 1.0 + pysum(sq, k);
    }
    return sqrt(e[0] / e[1]);
}

static int emit_fwd(const VoiceSnap *v, const ToneIn *t, Rows *R, double *qacc, double *azimuth,
                const double *terms, int nterms,
                double om, double ampL, double ampR, double ampM, double nomf, double non, double noff,
                double fa, double re, double ch, double logr, double logrA, double aft, double sus,
                double cv, double cc, double crl, double sj, double csc, double gr, double cr, double ph0,
                double player, const double *VB, double pos_x, int late)
{
    om = om * t->jitter_scale;
    if (t->transposed && om >= t->nyq_om)
        return 1;
    double dl = t->dl, dr = t->dr, px = pos_x, pz = t->pos_z;
    double am0 = ampM;
    double dm = t->dist > 0.0 ? t->dist : 1.0;
    if (dm != 1.0) {
        /* FURTHER AWAY, THE SAME BALANCE (emit_partial's _src_dist): its
           top end across the extra air, and the direct and its early images
           held to the energy they had at the voice's own distance */
        double r0 = sqrt(px * px + pow(v->room[0], 2.0) + pz * pz);
        double ga = pow(10.0, -air_db(v->room, nomf) * (dm - 1.0) * r0 / 20.0);
        if (t->reflect)
            ga *= refl_norm(v, t, nomf, px, pz, dm);
        ampL *= ga; ampR *= ga; ampM *= ga;
    }
    if (t->hammer_on > 0.0) {
        /* A HAMMER-ON / PULL-OFF (hammer_legato): the partial where its own
           decay has got to since the pick (logr, then the aftersound's
           logrA), less what the fretting finger costs (HAMMER_LOSS_DB) */
        double hg = ((1.0 - aft) * exp(-logr * t->hammer_on) + aft * exp(-logrA * t->hammer_on))
                    * pow(10.0, -3.0 / 20.0);
        ampL *= hg; ampR *= hg; ampM *= hg;
    }
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
        px, pz, *azimuth, late == 2 ? 0.9 : late ? 0.75 : 1.0,
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
        /* (no radius of its own: the class's directivity_radius, room[1]) */
        double q = t->has_radius ? directivity_factor(v, t->room_bands[bi], px, pz, t->radius)
                   : v->room[1] > 0.0 ? directivity_factor(v, t->room_bands[bi], px, pz, v->room[1]) : 1.0;
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
            ix, iz, *azimuth, late == 2 ? 0.1 : late ? 0.25 : 0.0,
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

/* ...AND A TAPE PLAYED BACKWARDS (t->rev: _Emitter._reverse_partial): the
 * partial of the forward note, time-reversed -- each of its decays a growth
 * at its own rate, begun REV_FLOOR under its end (or at the onset, faded
 * in), ending where the forward one began, mirrored about the arrival; its
 * phase mirrored; the attack's chiff a swell of noise just before the
 * arrival (no images). Each row a forward one, with its images. */
static int emit(const VoiceSnap *v, const ToneIn *t, Rows *R, double *qacc, double *azimuth,
                const double *terms, int nterms,
                double om, double ampL, double ampR, double ampM, double nomf, double non, double noff,
                double fa, double re, double ch, double logr, double logrA, double aft, double sus,
                double cv, double cc, double crl, double sj, double csc, double gr, double cr, double ph0,
                double player, const double *VB, double pos_x, int late)
{
    if (!t->rev)
        return emit_fwd(v, t, R, qacc, azimuth, terms, nterms, om, ampL, ampR, ampM, nomf, non, noff, fa, re,
                        ch, logr, logrA, aft, sus, cv, cc, crl, sj, csc, gr, cr, ph0, player, VB, pos_x, late);
    const double SR = t->sr, n0 = t->rev_n0, arr = t->rev_arr;
    double end = arr - (non - n0);
    if (end <= n0)
        return 1;
    double out = pymax(fa, 0.001 * SR);        /* the forward fade-in, now the cut-off */
    out = pymin(out, 0.5 * (end - n0));
    const double w3[3] = {(1.0 - sus) * (1.0 - aft), (1.0 - sus) * aft, sus};
    const double lr3[3] = {logr, logrA, 0.0};
    for (int i = 0; i < 3; i++) {
        double w = w3[i], lr = lr3[i];
        if (w <= 0.0)
            continue;
        double span = lr > 0.0 ? log(1e5) / lr * SR : end - n0;
        double start = pymax(n0, end - span);
        double g = w * exp(-lr * (end - start) / SR);
        double fin = start <= n0 ? 0.01 * SR : 0.001 * SR;
        double o_ = pymin(out, pymax(1.0, end - start));
        if (!emit_fwd(v, t, R, qacc, azimuth, terms, nterms, om, ampL * g, ampR * g, ampM * g, nomf, start,
                      pymax(start + 1.0, end - o_), fin, o_, 1.0, -lr, 0.0, 0.0, 0.0, cv, cc, 0.0, sj, csc, gr, cr,
                      -ph0 - om * t->jitter_scale * (end - start), player, VB, pos_x, late))
            return 0;
    }
    double jp = cv * csc * 0.25;                /* the hump's peak, r(1-r) at r = 1/2 */
    if (jp > 0.0 && ch > 0.0) {
        ToneIn th = *t;
        th.cbw0 = -pymax(fabs(t->cbw0), 1e-3);
        th.cbw1 = 0.0;
        double start = pymax(n0, end - ch);
        double pk = end - ch / 3.0;             /* the forward hump peaks a third in */
        double g = jp * (1.0 - sus) * (1.0 - aft) * exp(-logr * (ch / 3.0) / SR);
        if (!emit_fwd(v, &th, R, qacc, azimuth, NULL, 0, om, ampL * g, ampR * g, ampM * g, nomf, start,
                      pymax(start + 1.0, pk), pymax(1.0, pk - start), pymax(1.0, end - pk), ch, 0.0, 0.0, 0.0,
                      1.0, 0.0, cc, crl, 0.0, csc, gr, cr, -ph0 - om * t->jitter_scale * (end - start), player, VB,
                      pos_x, late))
            return 0;
    }
    return 1;
}

/* The room's terms for this note's direct sound at frequency f: roomcore's
 * reflection_terms over the images, then each image's ears and the delay
 * past the stage (emit_partial's _terms). terms: 9 a kept image. */
/* a note's distance multiple (_src_dist), 1 where it stands */
static double dist_of(const ToneIn *t) { return t->dist > 0.0 ? t->dist : 1.0; }

static int note_terms(const VoiceSnap *v, const ToneIn *t, double f, double px, double pz,
                      int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
                      double *terms)
{
    int keep[64];
    double g[64], dly[64];
    if (nimg > 64)
        return -1;
    double dm = dist_of(t);
    double sx = px * dm, sy = v->room[0] * dm, sz = pz * dm;
    double stage = sqrt(px * px + pow(t->listener_distance, 2.0) + pz * pz);
    int k = reflection_terms(v->room, v->ahz, v->alpha, v->scat,
                             f, sx, sy, sz, t->radius, t->has_radius, nimg, nsurf, surf, img, mir, keep, g, dly);
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
int nv_tone_rs(const VoiceSnap *v, const ToneIn *t,
               int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
               double *rows, int cap, double *transverse, int *ntrans, double *qacc, double *azimuth,
               PyRandom *rs, double *sjit_last);

int nv_tone(const VoiceSnap *v, const ToneIn *t,
            int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
            double *rows, int cap, double *transverse, int *ntrans, double *qacc, double *azimuth)
{
    return nv_tone_rs(v, t, nimg, nsurf, surf, img, mir, rows, cap, transverse, ntrans, qacc, azimuth,
                      NULL, NULL);
}

/* nv_tone, drawing each partial's strike sign from rs (the global random
 * stream: random.getrandbits(1), where strike_phase_spread asks; -2 without
 * one), and *sjit_last the jitter of the last partial emitted (the note's
 * nt.sjit after it) */
int nv_tone_rs(const VoiceSnap *v, const ToneIn *t,
               int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
               double *rows, int cap, double *transverse, int *ntrans, double *qacc, double *azimuth,
               PyRandom *rs, double *sjit_last)
{
    if ((t->sps > 0.0 || t->ssc) && !rs)
        return -2;
    Rows R = {rows, 0, cap};
    double terms_main[9 * 64], terms_u[9 * 64];
    double sr = t->sr;
    double VB0[3] = {0.0, 5.5, 0.0};
    /* A SECTION'S PLAYERS (SectionMixin): each one's entry (section_onsets_at)
       and, seated, each one's ears (section_seats: hrtf_at of its desk), the
       note's own the first player's */
    int ns = v->sect_n > 1 ? v->sect_n : 0;
    int ons_set = ns && v->sect_onset_ms != 0.0;
    double ons[16], seat[16][4];
    ToneIn tl, tu;
    if (ons_set)
        for (int i = 0; i < ns; i++)
            ons[i] = nv_section_onset(v->section_salt, section_midi(t->f0), i, v->sect_onset_ms);
    /* ...OR A STRUCK VOICE'S REPEATS (the bird's chirps, the clapper's strokes):
       each its own onset, capped at sect_ofm of the note */
    static _Thread_local double tons[200];
    int nons = v->tap_kind ? nv_tap_onsets(v, t->f0, tons) : 0;
    if (v->pick_set && v->pick_stagger > 0.0) {  /* a doubled course crossed (Plectrum.section_onsets_at) */
        tons[0] = 0.0;
        tons[1] = v->pick_stagger;
        nons = 2;
    }
    if (ns && v->sect_seats) {
        for (int i = 0; i < ns; i++)
            nv_section_seat(v, t, i, seat[i]);
        tl = *t;
        tl.li = seat[0][0]; tl.ri = seat[0][1];
        tl.dl = seat[0][2] * sr; tl.dr = seat[0][3] * sr;
        t = &tl;
    }
    /* ...and each player's images, from its own desk (the note's are the
       first player's place: the voice's) */
    static _Thread_local int pn_img[16], p_nsurf[16][64], p_surf[16][64 * 8];
    static _Thread_local double p_img[16][64 * 3], p_mir[16][64 * 3];
    if (ns && v->sect_seats && t->reflect) {
        if (t->order > 8)
            return -2;
        for (int i = 1; i < ns; i++) {
            pn_img[i] = nv_images(t->planes, t->order, (t->pos_x_props + v->sect_dx[i]) * dist_of(t),
                                  v->room[0] * dist_of(t), t->pos_z * dist_of(t), 64, p_nsurf[i], p_surf[i], p_img[i], p_mir[i]);
            if (pn_img[i] < 0)
                return -2;              /* more than 64 images: not the C's */
        }
    }
    double pos_x = t->pos_x0;
    *ntrans = 0;
    const ToneIn *const t_note = t;
    ToneIn tml;
    /* each partial its own phase (partial_phase_spread): the note's own stream */
    PyRandom prng;
    if (v->pps > 0.0)
        pyr_seed(&prng, t->pps_seed);
    for (int m = 1; m < v->max_harmonic + 1; m++) {
        const ToneIn *t = t_note;
        double hh[2];
        if (!nv_string_partial(v, t->f0, 1.0, m, t->B, hh))
            break;
        double h = hh[0], hf = hh[1];
        if (hf > sr / 2)
            break;
        double hv = nv_harmonic_volume(v, m);
        if (hv == 0.0)
            continue;
        /* A PIPE'S MODES START SHARP (mode_lock_offset_for): this partial's
           tension-bend triple the lock's, where it has one */
        if (v->ml_spread > 0.0 && m > 1) {
            double x = pow((double)m / v->ml_knee, 2.0);
            double mlo = v->ml_spread * (x / (1.0 + x));
            if (mlo != 0.0) {
                tml = *t_note;
                tml.tb[0] = mlo; tml.tb[1] = v->ml_time; tml.tb[2] = v->ml_time * 6.0;
                t = &tml;
            }
        }
        double pd[4];
        nv_partial_decay(v, t->f0, m, pd);          /* dbps, logr, aftL, logrA */
        double gM = hv * t->gain * nv_radiation_gain(v, hf, 0.0, 0);
        double gL = gM * nv_hrtf_gain(v, hf, t->li), gR = gM * nv_hrtf_gain(v, hf, t->ri);
        double cvp = t->cv * nv_chiff_harmonic_gain(v, h);
        double VB[3];
        if (!nv_voice_vibrato(v, t->f0, 0, VB)) {
            VB[0] = VB0[0]; VB[1] = VB0[1]; VB[2] = VB0[2];
        }
        double sj = t->pjit ? nv_partial_jitter(v, m) : t->sjit;
        if (sjit_last)
            *sjit_last = sj;
        double non_m = t->non + (ons_set ? pymin(ons[0], 0.25 * t->dur) * sr : 0.0);
        double mph = 0.0;
        if (t->sps > 0.0)                           /* where the stick landed against its nodes */
            mph = PI * (double)(pyr_genrand(rs) >> 31) * t->sps;
        if (v->n_mp)                                /* a mode's own phase (mode_phase) */
            mph += (1 <= m && m <= v->n_mp) ? v->mode_phases[m - 1] : 0.0;
        if (v->pps > 0.0)                           /* ...and its own, drawn (partial_phase_spread) */
            mph += 2.0 * PI * v->pps * pyr_random(&prng);
        double mph_course = mph;
        if (t->ssc) {                               /* how hard this stroke caught the mode */
            double ssd = nv_stroke_scatter_db(v, m);
            if (ssd > 0.0) {
                if (!rs)
                    return -2;
                double sk = pow(10.0, pyr_gauss(rs, 0.0, ssd) / 20.0);
                gL *= sk;
                gR *= sk;
                gM *= sk;
            }
        }
        int nt_ = 0;
        if (t->reflect) {
            nt_ = note_terms(v, t, hf, pos_x, t->pos_z, nimg, nsurf, surf, img, mir, terms_main);
            if (nt_ < 0)
                return -1;
        }
        /* ...its upper harmonics late (speech_harmonic_exp), counted to sh_cap */
        double pfade = t->fade;
        double she = v->sh_exp;
        if (v->sh_exp_oct != 0.0)
            she = pymin(0.0, she + v->sh_exp_oct * log2(pymax(t->f0, 1.0) / 415.0));
        if (she != 0.0 && m > 1)
            pfade = pymax(1.0, t->fade * pow((double)(v->sh_cap ? (m < v->sh_cap ? m : v->sh_cap) : m), -she));
        if (!emit(v, t, &R, qacc, azimuth, terms_main, nt_, 2 * PI * hf / sr, gL, gR, gM, hf, non_m, t->noff,
                  pfade, t->rel, t->chiff, pd[1], pd[3], pd[2], t->sustain_level, cvp, t->cc, t->crl, sj,
                  t->csc, t->gr, t->cr, mph, 0.0, VB, pos_x, 0))
            return -1;
        /* A PLAYED REED'S WIND (wind_skirt_always): a noise band on the
           partial, as it is, no images */
        if (v->skirt && m <= v->sk_max) {
            double wg = pow(10.0, (v->sk_db + v->sk_hdb * log2((double)m)) / 20.0) * 1.0;
            ToneIn ts = *t;
            ts.cbw0 = -pymax(v->sk_hz / hf, v->sk_rel);
            ts.cbw1 = 0.0;
            ts.reflect = 0;
            if (!emit(v, &ts, &R, qacc, azimuth, NULL, 0, 2 * PI * hf / sr, gL * wg, gR * wg, gM * wg, hf, non_m,
                      t->noff, pfade, t->rel, t->chiff, pd[1], pd[3], pd[2], t->sustain_level, 0.0, t->cc, t->crl,
                      0.0, t->csc, t->gr, t->cr, 0.0, 0.0, VB, pos_x, 0))
                return -1;
        }
        /* THE LATE ARRIVAL (bloom_gain): a quieter copy of the partial, its
           arrival bloom_delay_for later (scattered from the global stream:
           bloom_scatter), swelling in over bloom_swell of it, held within the
           note; falling at bloom_decay_dbs where the voice sets one */
        double pdelay = nv_bloom_delay_for(v, hf) * sr;
        if (pdelay > 0.0 && v->bloom_gain > 0.0) {
            double bg = nv_bloom_gain_for(v, hf);
            double sc = v->bloom_scatter, pdl = pdelay;
            if (sc > 0.0) {
                if (!rs)
                    return -2;
                pdl = pdelay * (1.0 - sc + 2.0 * sc * pyr_random(rs));
            }
            double bfade = pymax(1e-4, pymin(v->bloom_swell * pdl / sr, 0.45 * t->dur)) * sr;
            int ok;
            if (v->bloom_decay_dbs > 0.0) {
                double blr = log(db_ratio(v->bloom_decay_dbs));
                ok = emit(v, t, &R, qacc, azimuth, terms_main, nt_, 2 * PI * hf / sr, gL * bg, gR * bg, gM * bg, hf,
                          non_m + pdl, t->noff, bfade, t->rel, t->chiff, blr, blr, 0.0, 0.0, cvp, t->cc, t->crl, sj,
                          t->csc, t->gr, t->cr, 0.0, 0.0, VB, pos_x, 1);
            } else {
                ok = emit(v, t, &R, qacc, azimuth, terms_main, nt_, 2 * PI * hf / sr, gL * bg, gR * bg, gM * bg, hf,
                          non_m + pdl, t->noff, bfade, t->rel, t->chiff, pd[1], pd[3], pd[2], t->sustain_level, cvp,
                          t->cc, t->crl, sj, t->csc, t->gr, t->cr, 0.0, 0.0, VB, pos_x, 1);
            }
            if (!ok)
                return -1;
        }
        /* FEEDBACK (Feedback): the loop's partial and its own series, a late
           copy swelling in at the loop's onset and held, sinking at its own
           rate, at the fundamental's pluck level */
        if (v->fb_set) {
            int fbk = v->fb_fixed;
            if (!fbk) {                         /* (the harmonic nearest the loop's band: the first of equals) */
                double best = 0.0;
                for (int k = 1; k < 33; k++) {
                    double d = fabs(log2(k * t->f0 / v->fb_band_hz));
                    if (k == 1 || d < best) {
                        best = d;
                        fbk = k;
                    }
                }
            }
            double fbs = 0.0;
            if (m % fbk == 0)
                for (int i = 0; i < v->n_fbs; i++)
                    if ((int)v->fbs[i][0] == m / fbk) {
                        fbs = v->fbs[i][1];     /* (dict(): the last of a multiple's) */
                    }
            double fon = non_m + v->fb_delay * sr;
            if (m % fbk == 0 && fbs > 0.0 && fon < t->noff && hv > 0.0) {
                double fs = v->fb_gain * fbs * nv_harmonic_volume(v, 1) / hv;
                double flr = v->fb_dbs > 0.0 ? log(db_ratio(v->fb_dbs)) : 0.0;
                if (!emit(v, t, &R, qacc, azimuth, terms_main, nt_, 2 * PI * hf / sr, gL * fs, gR * fs, gM * fs, hf, fon,
                          t->noff, pymax(1e-4, v->fb_swell) * sr, t->rel, t->chiff, flr, flr, 0.0, 0.0, cvp, t->cc,
                          t->crl, sj, t->csc, t->gr, t->cr, 0.0, 0.0, VB, pos_x, 1))
                    return -1;
            }
        }
        transverse[3 * *ntrans] = hf;
        transverse[3 * *ntrans + 1] = hv;
        transverse[3 * *ntrans + 2] = pd[0];
        (*ntrans)++;
        static _Thread_local double uv[5 * 200];
        int nu = nv_unison_voices(v, t->f0, m, pd[0], uv);
        for (int ui = 0; ui < nu; ui++) {
            double gm = uv[5 * ui], off_hz = uv[5 * ui + 1], dr = uv[5 * ui + 2], ud = uv[5 * ui + 3];
            double uph = uv[5 * ui + 4];
            /* A STRIKE THE NOTE DOES NOT REACH, OR THAT MISSES THIS MODE, IS NOT
               EMITTED (unison_drop_late: the telephone's) */
            if (v->tap_drop && (gm <= 0.0 || (nons && ui + 1 < nons && tons[ui + 1] >= v->sect_ofm * t->dur)))
                continue;
            if (!nv_voice_vibrato(v, t->f0, ui + 1, VB)) {
                VB[0] = VB0[0]; VB[1] = VB0[1]; VB[2] = VB0[2];
            }
            double up[2];
            nv_unison_partial(hf, off_hz, dr, ud, up);
            double uf = up[0], ulr = up[1];
            if (uf <= 0 || uf > sr / 2)
                continue;
            double ugL = gL * gm, ugR = gR * gm;
            const ToneIn *tp = t;
            double upos = pos_x;
            if (ns && v->sect_seats && ui + 1 < ns) {
                /* this player's chair, its shadow read at the nominal harmonic */
                upos = t->pos_x_props + v->sect_dx[ui + 1];
                ugL = gM * gm * nv_hrtf_gain(v, hf, seat[ui + 1][0]);
                ugR = gM * gm * nv_hrtf_gain(v, hf, seat[ui + 1][1]);
                tu = *t;
                tu.dl = seat[ui + 1][2] * sr; tu.dr = seat[ui + 1][3] * sr;
                tp = &tu;
            }
            double non_u = t->non + ((ons_set && ui + 1 < ns) ? pymin(ons[ui + 1], v->sect_ofm * t->dur) * sr
                                     : (nons && ui + 1 < nons) ? pymin(tons[ui + 1], v->sect_ofm * t->dur) * sr : 0.0);
            int ntu = 0;
            if (t->reflect) {
                ntu = (ns && v->sect_seats && ui + 1 < ns)
                      ? note_terms(v, tp, uf, upos, t->pos_z, pn_img[ui + 1], p_nsurf[ui + 1], p_surf[ui + 1],
                                   p_img[ui + 1], p_mir[ui + 1], terms_u)
                      : note_terms(v, tp, uf, upos, t->pos_z, nimg, nsurf, surf, img, mir, terms_u);
                if (ntu < 0)
                    return -1;
            }
            if (!emit(v, tp, &R, qacc, azimuth, terms_u, ntu, 2 * PI * uf / sr, ugL, ugR, gM * gm, uf, non_u,
                      t->noff, pfade, t->rel, t->chiff, ulr, pd[3], pd[2], t->sustain_level, cvp, t->cc,
                      t->crl, sj, t->csc, t->gr, t->cr,
                      2 * PI * uph + (v->ushare ? mph_course : v->pps > 0.0 ? 2.0 * PI * v->pps * pyr_random(&prng) : 0.0),
                      (double)(ui + 1), VB, upos, 0))
                return -1;
        }
        pos_x = t->pos_x_props;     /* em.pos_x = the voice's position, after each harmonic */
    }
    return R.n;
}

/* blockrender._note_shake_noise: the shake's noise bands (hz[], db[] of nb),
 * k rows a band spread across it, each twice -- the shake, swelling in over
 * rise_s and held for its share of the key (held s), then the settle,
 * falling settle_db over settle_s, crossfaded; the caller sets the noise
 * width (t->cbw0) and no images (t->reflect 0). qacc and *azimuth as
 * nv_tone's. Returns the rows written, -1 if the store was too small. */
int nv_shake(const VoiceSnap *v, const ToneIn *t, int nb, const double *hz, const double *db, int k,
             double held, double shake_min_s, double shake_frac, double shake_xfade_s, double rise_s,
             double settle_db, double settle_s, double pos_x, double *rows, int cap, double *qacc,
             double *azimuth)
{
    Rows R = {rows, 0, cap};
    double VB[3] = {0.0, 5.5, 0.0};
    double sr = t->sr;
    double shk = pymax(shake_min_s, held * shake_frac);
    double xf = pymin(shake_xfade_s, 0.5 * shk);
    double rise = pymax(1e-4, pymin(rise_s, shk - xf)) * sr;
    double slr = log(10.0) / 20.0 * settle_db / settle_s;
    double sgain = exp(slr * xf);
    double son = t->non + (shk - xf) * sr;
    for (int b = 0; b < nb; b++)
        for (int j = 0; j < k; j++) {
            double hf = hz[b] * pow(2.0, (j - 0.5 * (k - 1)) / (3.0 * k));
            double d = db[b] - 10.0 * log10((double)k);
            if (hf >= 0.45 * sr)
                continue;
            double gM = v->gain * pow(10.0, d / 20.0) * nv_radiation_gain(v, hf, 0.0, 0);
            double gl = nv_hrtf_gain(v, hf, t->li), gr = nv_hrtf_gain(v, hf, t->ri);
            double om = 2 * PI * hf / sr;
            if (!emit(v, t, &R, qacc, azimuth, NULL, 0, om, gM * gl, gM * gr, gM, hf, t->non,
                      t->non + (shk - 0.5 * xf) * sr, rise, xf * sr, t->chiff, 0.0, 0.0, 0.0, 1.0, 0.0, t->cc,
                      t->crl, 0.0, t->csc, -1.0, 0.0, 0.0, 0.0, VB, pos_x, 0))
                return -1;
            double g2 = gM * sgain;
            if (!emit(v, t, &R, qacc, azimuth, NULL, 0, om, g2 * gl, g2 * gr, g2, hf, son,
                      son + (xf + 4.0 * settle_s) * sr, xf * sr, 0.02 * sr, t->chiff, slr, 0.0, 0.0, 0.0, 0.0,
                      t->cc, t->crl, 0.0, t->csc, -1.0, 0.0, 0.0, 0.0, VB, pos_x, 0))
                return -1;
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
int nv_strike_bal(const VoiceSnap *v, const ToneIn *t, int nb, const double *hz, const double *db,
                  double reg, double bdb, double scal, double slr, double sfade, double slen, double bon,
                  double pos_x, double bgl, double bgr, double *rows, int cap, double *qacc, double *azimuth);

/* numpy.interp at one x (compiled_base.c's arr_interp: a search, then the
 * slope's line from the point below; an exact point its own value) */
static double np_interp(double x, const double *xp, const double *fp, int n)
{
    if (x < xp[0])
        return fp[0];
    if (x > xp[n - 1])
        return fp[n - 1];
    int j = 0;
    while (j + 1 < n && xp[j + 1] <= x)
        j++;
    if (j == n - 1 || xp[j] == x)
        return fp[j];
    double slope = (fp[j + 1] - fp[j]) / (xp[j + 1] - xp[j]);
    double r = slope * (x - xp[j]) + fp[j];
    if (isnan(r)) {
        r = slope * (x - xp[j + 1]) + fp[j + 1];
        if (isnan(r) && fp[j] == fp[j + 1])
            r = fp[j];
    }
    return r;
}

static double clip01(double v) { return pymax(0.0, pymin(1.0, v)); }

/* moog.knob_tau: a contour knob's time constant */
static double knob_tau(const MoogLayer *L, double v)
{
    return exp(np_interp(clip01(v), L->eg_v, L->eg_log, 11));
}

void nv_moog_apply(const MoogLayer *in, const double *d, MoogLayer *out)
{
    *out = *in;
    /* GM_SOUND's order: brightness, resonance, attack, release, decay */
    static const int cc[5] = {3, 0, 2, 1, 4};
    double k[5];
    int moved[5];
    for (int i = 0; i < 5; i++) {
        k[i] = in->knob[i];
        moved[i] = d[cc[i]] != 0.0;
        if (moved[i])
            k[i] = pymax(0.0, pymin(1.0, k[i] + d[cc[i]] * in->span[i]));
        out->knob[i] = k[i];
    }
    if (moved[0]) {                             /* knob_cutoff: the knob row's, the sine's */
        double c = in->cut_lo * pow(2.0, in->cut_oct * clip01(k[0]));
        out->kn[0] = c;
        out->self_cut = c;
    }
    if (moved[1]) {                             /* knob_k, self_amp */
        out->kn[1] = pymin(in->k_max, in->res_per_unit * clip01(k[1]));
        out->self_amp = in->self_amp_max * pow(pymax(0.0, (k[1] - in->self_from) / (1.0 - in->self_from)), 2.0);
    }
    if (moved[2])                               /* knob_attack */
        out->ft[4] = knob_tau(in, k[2]) * in->atk_to_1;
    if (moved[3]) {                             /* knob_time, release_span */
        double tau = knob_tau(in, k[3]);
        out->ft[6] = 4.0 * tau;
        out->rel_span = tau * (log((1.0 + in->eg_under) / in->eg_under) + 1.0);
    }
    if (moved[4])
        out->ft[5] = 4.0 * knob_tau(in, k[4]);
}

/* moog.ladder_gain_1: the ladder's |H| at f, corner fc, feedback k, mode
 * (0 4-pole, 1 2-pole, 2 band-pass, 3 high-pass), RES BASS rb */
static double moog_ladder_gain(const MoogLayer *L, double f, double fc, double k, int mode, int rb)
{
    double x = f / (fc * (mode == 2 ? L->bp_corner : mode == 3 ? L->hp_corner : 1.0));
    double re4 = 1.0 - 6.0 * x * x + pow(x, 4.0), im4 = 4.0 * x - 4.0 * pow(x, 3.0);
    double den = sqrt((re4 + k) * (re4 + k) + im4 * im4), num;
    if (mode == 0)
        num = 1.0;
    else if (mode == 1)
        num = 1.0 + x * x;
    else if (mode == 2)
        num = L->bp_gain * 4.0 * x * x;
    else {
        double nr = pow(x, 4.0) - x * x, ni = -2.0 * pow(x, 3.0);
        double dr = re4 + k;
        double d2 = dr * dr + im4 * im4;
        double hr = L->hp_gain * (nr * dr + ni * im4) / d2 + L->hp_leak;
        double hi = L->hp_gain * (ni * dr - nr * im4) / d2;
        return sqrt(hr * hr + hi * hi);
    }
    double h = num / den;
    if (rb && (mode == 0 || mode == 1))
        h = h * (1.0 + k);
    return h;
}

/* moog.ladder_gain_1, for the live slab (a valve after the ladder: sustain_gain) */
double nv_moog_ladder_gain(const MoogLayer *L, double f, double fc, double k, int mode, int rb)
{
    return moog_ladder_gain(L, f, fc, k, mode, rb);
}

/* (moog_ladder_gain, for the checks) */
double nv_moog_ladder(const MoogLayer *L, double f, double fc, double k, int mode, int rb)
{
    return moog_ladder_gain(L, f, fc, k, mode, rb);
}

/* A MOOG LAYER's partials (blockrender._note_moog, one layer, no unison):
 * moog.partials in its order -- the noise bands, the ladder's own sine,
 * OSC 1, OSC 2, the SUB -- each at its true pitch, but its head, radiation
 * and room read at its harmonic's NOMINAL frequency (where live's
 * knob-neutral templates read them); every one tagged with the note's
 * filter row fx and its key (osc 4096 + k), OSC 2's with 1 -> 2 FM's
 * modulator. A noise band is noise (a negative wash bandwidth) and has no
 * images. The envelope columns are neutral (a 1-sample fade, the panel's
 * release mre): the kernel's contours are the envelope. */
static int moog_emit(const VoiceSnap *v, const ToneIn *t0, const MoogLayer *L, double fx, double mre, int nimg,
                     const int *nsurf, const int *surf, const double *img, const double *mir, double *rows, int cap,
                     double *qacc, double *azimuth, int np, const int *po, const int *pk, const double *phf,
                     const double *pa, const double *pph, int neutral, int nu, const double *uv, int umid);

/* A LIVE TEMPLATE's MOOG (blockrender's MOOG_NEUTRAL): set by the live
 * template builder around its one-note render, on its own thread */
static _Thread_local int moog_neutral_on = 0;
void nv_set_moog_neutral(int on) { moog_neutral_on = on; }
int nv_moog_neutral(void) { return moog_neutral_on; }

/* blockrender._note_moog under MOOG_NEUTRAL: every harmonic at unit weight,
 * phase 0, its NOMINAL frequency -- OSC 1 and 2 on the key, the SUB an
 * octave under, over Nyquist too -- then the noise bands, then the
 * ladder's own sine at the key: the live slab weighs them (moog.weights) */
int nv_moog_neutral_tone(const VoiceSnap *v, const ToneIn *t0, const MoogLayer *L, double fx, double mre, int nimg,
                         const int *nsurf, const int *surf, const double *img, const double *mir, double *rows,
                         int cap, double *qacc, double *azimuth)
{
    static _Thread_local int po[64 + 64 + 32 + 32 + 1], pk[64 + 64 + 32 + 32 + 1];
    static _Thread_local double phf[64 + 64 + 32 + 32 + 1], pa[64 + 64 + 32 + 32 + 1], pph[64 + 64 + 32 + 32 + 1];
    const double f0 = t0->f0;
    int np = 0;
    for (int o = 1; o <= 3; o++) {
        double fn = o == 3 ? f0 * 0.5 : f0;
        int nh = o == 3 ? 32 : 64;
        for (int k = 1; k <= nh; k++) {
            po[np] = o; pk[np] = k; phf[np] = fn * k; pa[np] = 1.0; pph[np++] = 0.0;
        }
    }
    for (int k = 0; k < L->n_noise; k++) {
        po[np] = 4; pk[np] = k + 1; phf[np] = L->noise_hz[k]; pa[np] = 1.0; pph[np++] = 0.0;
    }
    po[np] = 5; pk[np] = 1; phf[np] = f0; pa[np] = 1.0; pph[np++] = 0.0;
    static const double UV1[9] = {1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0};
    return moog_emit(v, t0, L, fx, mre, nimg, nsurf, surf, img, mir, rows, cap, qacc, azimuth, np, po, pk, phf, pa,
                     pph, 1, 1, UV1, 0);
}

int nv_moog_tone(const VoiceSnap *v, const ToneIn *t0, const MoogLayer *L, double fx, double mre, int nimg,
                 const int *nsurf, const int *surf, const double *img, const double *mir, double *rows, int cap,
                 double *qacc, double *azimuth)
{
    const double f0 = t0->f0, sr = t0->sr;
    const double fmax = pymin(L->fmax_hz, sr / 2.0);
    /* moog.partials: (osc, harmonic, Hz, amplitude, phase) */
    static _Thread_local int po[32 + 1 + 64 + 64 + 32], pk[32 + 1 + 64 + 64 + 32];
    static _Thread_local double phf[32 + 1 + 64 + 64 + 32], pa[32 + 1 + 64 + 64 + 32], pph[32 + 1 + 64 + 64 + 32];
    int np = 0;
    double f1 = f0 * L->t * L->foot1;
    double f2 = f0 * L->t * L->foot2 * L->o2f;
    if (L->lvl[3] > 0.0)
        for (int k = 0; k < L->n_noise; k++)
            if (L->noise_hz[k] <= fmax) {
                po[np] = 4; pk[np] = k + 1; phf[np] = L->noise_hz[k]; pa[np] = L->noise_amp[k] * L->lvl[3];
                pph[np++] = 0.0;
            }
    if (L->self_amp > 0.0) {
        double fs = L->self_cut * pow(f0 / L->kb_ref_hz, L->kb_track) * L->self_eg;
        if (fs <= fmax) {
            po[np] = 5; pk[np] = 1; phf[np] = fs; pa[np] = L->self_amp; pph[np++] = 0.0;
        }
    }
    for (int o = 1; o <= 3; o++) {
        double f = o == 1 ? f1 : o == 2 ? f2 : f1 * 0.5;
        double lvl = L->lvl[o - 1];
        const double (*c)[2] = o == 1 ? L->c1 : o == 2 ? L->c2 : L->cs;
        int nh = o == 3 ? 32 : 64;
        /* ITS SHAPE MOVES (FT_SHAPE): the kernel multiplies in the shape rows'
           coefficient, so the partial carries only 2 x level */
        int moving = (L->shape_on >> o) & 1;
        if (lvl <= 0.0 || f <= 0.0)
            continue;
        double q = py_floordiv(fmax, f);
        int n = q < (double)nh ? (int)q : nh;
        if (o == 2 && L->pitch_on)
            n = 64;                         /* its pitch moves: every harmonic */
        if (n < 1)
            continue;
        for (int k = 1; k <= n; k++) {
            double cr = moving ? 1.0 : c[k - 1][0], ci = moving ? 0.0 : c[k - 1][1];
            double a = 2.0 * hypot(cr, ci) * lvl;
            if (a > 1e-9) {
                po[np] = o; pk[np] = k; phf[np] = f * k; pa[np] = a; pph[np++] = atan2(ci, cr);
            }
        }
    }
    /* moog.unison: the note's voices, seeded on its key -- (ratio, gain,
       phase in cycles, left, right, has drift, drift depth, rate, phase) */
    static const double UV1[9] = {1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0};
    static _Thread_local double uv[9 * 16];
    int nu = L->u_n > 1 && L->u_n <= 16 ? L->u_n : 1, umid = 0;
    if (nu > 1) {
        PyRandom r;
        pyr_seed(&r, 0x5A75 + (long long)nearbyint(f0 * 100.0));
        static const double SS[7] = {-1.0, -0.5716, -0.1774, 0.0, 0.1810, 0.5650, 0.9767};
        double sp[16], g[16], gg[16];
        for (int i = 0; i < nu; i++)
            sp[i] = nu == 7 ? SS[i] : -1.0 + 2.0 * i / (nu - 1);
        int smid = 0;
        for (int i = 1; i < nu; i++)
            if (fabs(sp[i]) < fabs(sp[smid]))
                smid = i;
        for (int i = 0; i < nu; i++) {
            g[i] = i == smid ? 1.0 : L->u_mix;
            gg[i] = g[i] * g[i];
        }
        double norm = pow(pysum(gg, nu), -0.5);
        for (int i = 0; i < nu; i++) {
            double *w = uv + 9 * i;
            w[0] = pow(2.0, sp[i] * L->u_cents / 1200.0);
            double pan = pymax(-1.0, pymin(1.0, sp[i] * L->u_width));
            double a = (pan + 1.0) * PI / 4.0;
            w[5] = L->u_dc != 0.0;
            if (w[5]) {
                w[6] = (pow(2.0, L->u_dc / 1200.0) - 1.0) * pyr_uniform(&r, 0.6, 1.0);
                w[7] = pyr_uniform(&r, L->u_dhz[0], L->u_dhz[1]);
                w[8] = pyr_uniform(&r, 0.0, 2.0 * PI);
            } else {
                w[6] = w[7] = w[8] = 0.0;
            }
            w[1] = g[i] * norm;
            w[2] = pyr_random(&r);
            w[3] = cos(a) * pow(2.0, 0.5);
            w[4] = sin(a) * pow(2.0, 0.5);
        }
        for (int i = 1; i < nu; i++)        /* blockrender's: the voice nearest unison */
            if (fabs(uv[9 * i] - 1.0) < fabs(uv[9 * umid] - 1.0))
                umid = i;
    }
    return moog_emit(v, t0, L, fx, mre, nimg, nsurf, surf, img, mir, rows, cap, qacc, azimuth, np, po, pk, phf, pa,
                     pph, 0, nu, nu > 1 ? uv : UV1, umid);
}

/* the partials of a Moog note as blockrender._note_moog emits them: (osc,
 * harmonic, Hz, amplitude, phase) each, at the key's own harmonic for the
 * head, radiation and body; a valve after the ladder (not a live
 * template's: neutral) hears it at its sustain */
static int moog_emit(const VoiceSnap *v, const ToneIn *t0, const MoogLayer *L, double fx, double mre, int nimg,
                     const int *nsurf, const int *surf, const double *img, const double *mir, double *rows, int cap,
                     double *qacc, double *azimuth, int np, const int *po, const int *pk, const double *phf,
                     const double *pa, const double *pph, int neutral, int nu, const double *uv, int umid)
{
    Rows R = {rows, 0, cap};
    const double f0 = t0->f0, sr = t0->sr;
    /* the note's vibrato (none: the kernel's neutral one), OSC 1 as the FM's modulator */
    double VB[3];
    if (!nv_voice_vibrato(v, f0, 0, VB)) {
        VB[0] = 0.0; VB[1] = 5.5; VB[2] = 0.0;
    }
    double fm1 = L->fm_index != 0.0 ? 2.0 * PI * f0 * L->fm_r1 / sr : 0.0;
    double terms[9 * 64];
    double VB0[3] = {VB[0], VB[1], VB[2]};
    for (int i = 0; i < np; i++) {
        int o = po[i], k = pk[i];
        double hf = phf[i];
        ToneIn t = *t0;
        t.fx = fx;
        t.mk = (double)(o * 4096 + k);
        t.fm_omega = o == 2 ? fm1 : 0.0;
        t.fm_phase = o == 2 ? (L->fm_index != 0.0 ? L->fm_ph : 0.0) : 0.0;
        int nz = o == 4;
        if (nz) {
            t.cbw0 = -L->noise_bw;
            t.cbw1 = 0.0;
            t.reflect = 0;
        }
        double hn = (o == 1 || o == 2) ? f0 * k : o == 3 ? f0 * 0.5 * k : o == 5 ? f0 : hf;
        double gM = v->gain * pa[i] * nv_radiation_gain(v, hn, 0.0, 0);
        if (L->body)                            /* through its formant body (moog_body) */
            gM *= bore_gain(v, hn) * v->bore_norm;
        if (L->pre && !neutral && o != 5) {     /* a valve after it: the ladder at its sustain (sustain_gain) */
            double fcs = L->self_cut * pow(f0 / L->kb_ref_hz, L->kb_track) * L->self_eg;
            gM *= moog_ladder_gain(L, hf, pymax(fcs, 1.0), L->kn[1], (int)L->ft[7], L->ft[8] != 0.0);
        }
        double hL = nv_hrtf_gain(v, hn, t.li), hR = nv_hrtf_gain(v, hn, t.ri);
        double cv = nz ? 0.0 : t.cv * nv_chiff_harmonic_gain(v, k);
        int nt_ = 0;
        if (t.reflect) {
            nt_ = note_terms(v, &t, hn, t.pos_x0, t.pos_z, nimg, nsurf, surf, img, mir, terms);
            if (nt_ < 0)
                return -1;
        }
        /* each voice of a unison (one, none): its detune, level, phase (k x
           its offset on an oscillator's harmonic k), place and drift; noise
           and the ladder's own sine the centre voice's alone */
        for (int u = 0; u < nu; u++) {
            const double *w = uv + 9 * u;
            if (u != umid && (o == 4 || o == 5))
                continue;
            if (nu > 1) {
                VB[0] = w[5] != 0.0 ? w[6] : VB0[0];
                VB[1] = w[5] != 0.0 ? w[7] : VB0[1];
                VB[2] = w[5] != 0.0 ? w[8] : VB0[2];
            }
            double off = (o >= 1 && o <= 3) ? 2.0 * PI * w[2] * k : 0.0;
            double gu = gM * w[1];
            if (!emit(v, &t, &R, qacc, azimuth, terms, nt_, 2.0 * PI * hf * w[0] / sr, gu * w[3] * hL,
                      gu * w[4] * hR, gu, hn, t.non, t.noff, 1.0, mre, t.chiff, 0.0, 0.0, 0.0, 1.0, cv, t.cc, t.crl,
                      t.sjit, t.csc, -1.0, 0.0, pph[i] + off, 0.0, VB, t.pos_x0, 0))
                return -1;
        }
    }
    return R.n;
}

/* blockrender._note_struck_layer's rows: another instrument's modes (ls,
 * its voice at ft) struck with the note -- each at its level against the
 * loudest (hv[], hmax), the note's gain times db, rising over rise s and
 * falling dbs dB/s for 1.5 s, its phase from random.Random(seed), with the
 * room's images. Returns the rows written: -1 the store too small, -2 more
 * images than the C's. */
int nv_struck(const VoiceSnap *v, const ToneIn *t, const VoiceSnap *ls, int nm, double ft, const double *hv,
              double hmax, double db, double rise, double dbs, long long seed, int nimg, const int *nsurf,
              const int *surf, const double *img, const double *mir, double *rows, int cap, double *qacc,
              double *azimuth)
{
    Rows R = {rows, 0, cap};
    double VB[3] = {0.0, 5.5, 0.0}, terms[9 * 64];
    const double sr = t->sr;
    double slr = log(10.0) / 20.0 * dbs;
    PyRandom r;
    pyr_seed(&r, seed);
    for (int m = 1; m <= nm; m++) {
        double h = hv[m - 1], hf = ft * nv_mode_ratio(ls, m);
        if (h <= 0.0 || hf >= 0.45 * sr)
            continue;
        double gM = v->gain * pow(10.0, db / 20.0) * h / hmax;
        int nt_ = 0;
        if (t->reflect) {
            nt_ = note_terms(v, t, hf, t->pos_x0, t->pos_z, nimg, nsurf, surf, img, mir, terms);
            if (nt_ < 0)
                return -2;
        }
        if (!emit(v, t, &R, qacc, azimuth, terms, nt_, 2 * PI * hf / sr, gM * nv_hrtf_gain(v, hf, t->li),
                  gM * nv_hrtf_gain(v, hf, t->ri), gM, hf, t->non, t->non + 1.5 * sr, pymax(1.0, rise * sr),
                  t->rel, 0.0, slr, 0.0, 0.0, 0.0, 0.0, t->cc, t->crl, 0.0, t->csc, -1.0, 0.0,
                  pyr_random(&r) * 2.0 * PI, 0.0, VB, t->pos_x0, 0))
            return -1;
    }
    return R.n;
}

int nv_strike(const VoiceSnap *v, const ToneIn *t, int nb, const double *hz, const double *db,
              double reg, double bdb, double scal, double slr, double sfade, double slen, double bon,
              double pos_x, double *rows, int cap, double *qacc, double *azimuth)
{
    return nv_strike_bal(v, t, nb, hz, db, reg, bdb, scal, slr, sfade, slen, bon, pos_x, 1.0, 1.0, rows, cap,
                         qacc, azimuth);
}

/* nv_strike, the burst at its place in the balance (bgl, bgr: a machine's
 * stereo clap's sqrt 2 cos, sin of its angle; 1 and 1 centred) */
int nv_strike_bal(const VoiceSnap *v, const ToneIn *t, int nb, const double *hz, const double *db,
                  double reg, double bdb, double scal, double slr, double sfade, double slen, double bon,
                  double pos_x, double bgl, double bgr, double *rows, int cap, double *qacc, double *azimuth)
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
                  gM * nv_hrtf_gain(v, hf, t->li) * bgl, gM * nv_hrtf_gain(v, hf, t->ri) * bgr, gM, hf,
                  bon, bon + slen, sfade, 0.01 * sr, t->chiff, slr, 0.0, 0.0, 0.0, 0.0, t->cc, t->crl,
                  0.0, t->csc, -1.0, 0.0, 0.0, 0.0, VB, pos_x, 0))
            return -1;
    }
    return R.n;
}

/* blockrender._note_strike_noise's LAYERS (strike_noise_layers): one
 * layer's table (hz[], db[] of nb) as noise rows from the note's onset, its
 * level with the register's tilt (reg), rising over fade, falling at slr for
 * len samples; the caller sets the noise width and no images. qacc and
 * *azimuth as nv_tone's. Returns the rows written, -1 if the store was too small. */
int nv_layer(const VoiceSnap *v, const ToneIn *t, int nb, const double *hz, const double *db, double reg,
             double fade, double slr, double len, double pos_x, double *rows, int cap, double *qacc, double *azimuth)
{
    Rows R = {rows, 0, cap};
    double VB[3] = {0.0, 5.5, 0.0};
    double sr = t->sr;
    for (int i = 0; i < nb; i++) {
        double hf = hz[i];
        if (hf >= 0.45 * sr)
            continue;
        double gM = v->gain * pow(10.0, (db[i] + reg) / 20.0);
        if (!emit(v, t, &R, qacc, azimuth, NULL, 0, 2 * PI * hf / sr, gM * nv_hrtf_gain(v, hf, t->li),
                  gM * nv_hrtf_gain(v, hf, t->ri), gM, hf, t->non, t->non + len, fade, 0.01 * sr, t->chiff, slr,
                  0.0, 0.0, 0.0, 0.0, t->cc, t->crl, 0.0, t->csc, -1.0, 0.0, 0.0, 0.0, VB, pos_x, 0))
            return -1;
    }
    return R.n;
}

/* blockrender._note_breath_noise: the voice's own noise (breath_noise_db),
 * held for the note -- each band k noise rows spread across it, sharing its
 * level -- swelling in over fade, released with the note; no images, the
 * emitter as the knock leaves it. Returns the rows written, -1 if the store
 * was too small. */
int nv_breath(const VoiceSnap *v, const ToneIn *t, int nb, const double *hz, const double *db, int k, double fade,
              double pos_x, double *rows, int cap, double *qacc, double *azimuth)
{
    Rows R = {rows, 0, cap};
    double VB[3] = {0.0, 5.5, 0.0};
    double sr = t->sr;
    for (int i = 0; i < nb; i++)
        for (int j = 0; j < k; j++) {
            double hf = hz[i] * pow(2.0, ((double)j - 0.5 * (k - 1)) / (3.0 * k));
            double d = db[i] - 10.0 * log10((double)k);
            if (hf >= 0.45 * sr)
                continue;
            double gM = v->gain * pow(10.0, d / 20.0);
            if (!emit(v, t, &R, qacc, azimuth, NULL, 0, 2 * PI * hf / sr, gM * nv_hrtf_gain(v, hf, t->li),
                      gM * nv_hrtf_gain(v, hf, t->ri), gM, hf, t->non, t->noff, fade, t->rel, t->chiff, 0.0,
                      0.0, 0.0, 1.0, 0.0, t->cc, t->crl, 0.0, t->csc, -1.0, 0.0, 0.0, 0.0, VB, pos_x, 0))
                return -1;
        }
    return R.n;
}

/* blockrender._note_noise_events: TIMED NOISE BANDS -- each (Hz, dB, start
 * s, end s) a band sounding over its own span of the note, k rows across it
 * sharing its level, ramped in and out over ramp samples, through the
 * radiation and the ears; no images, the emitter as the knock leaves it */
int nv_events(const VoiceSnap *v, const ToneIn *t, int ne, const double (*ev)[4], int k, double ramp,
              double pos_x, double *rows, int cap, double *qacc, double *azimuth)
{
    Rows R = {rows, 0, cap};
    double VB[3] = {0.0, 5.5, 0.0};
    double sr = t->sr;
    for (int e = 0; e < ne; e++)
        for (int j = 0; j < k; j++) {
            double hf = ev[e][0] * pow(2.0, ((double)j - 0.5 * (k - 1)) / (3.0 * k));
            if (hf >= 0.45 * sr)
                continue;
            double gM = v->gain * pow(10.0, (ev[e][1] - 10.0 * log10((double)k)) / 20.0) * nv_radiation_gain(v, hf, 0.0, 0);
            double gl = nv_hrtf_gain(v, hf, t->li), gr = nv_hrtf_gain(v, hf, t->ri);
            if (!emit(v, t, &R, qacc, azimuth, NULL, 0, 2 * PI * hf / sr, gM * gl, gM * gr, gM, hf,
                      t->non + ev[e][2] * sr, t->non + ev[e][3] * sr, ramp, ramp, t->chiff, 0.0, 0.0, 0.0, 1.0, 0.0,
                      t->cc, t->crl, 0.0, t->csc, -1.0, 0.0, 0.0, 0.0, VB, pos_x, 0))
                return -1;
        }
    return R.n;
}

/* _note_strike_noise's PALMS RINGING (strike_flam_people_peak): one decaying
 * sine at the person's pitch, at db (the caller's sum, as the Python adds
 * it), dying at plr, through the burst's balance -- with the burst, no images */
int nv_palm(const VoiceSnap *v, const ToneIn *t, double hz, double db, double plr, double bon, double slen,
            double sfade, double gl, double gr, double pos_x, double *rows, int cap, double *qacc, double *azimuth)
{
    Rows R = {rows, 0, cap};
    double VB[3] = {0.0, 5.5, 0.0};
    double sr = t->sr;
    double gM = v->gain * pow(10.0, db / 20.0);
    if (!emit(v, t, &R, qacc, azimuth, NULL, 0, 2 * PI * hz / sr, gM * nv_hrtf_gain(v, hz, t->li) * gl,
              gM * nv_hrtf_gain(v, hz, t->ri) * gr, gM, hz, bon, bon + slen, sfade, 0.01 * sr, t->chiff, plr, 0.0,
              0.0, 0.0, 0.0, t->cc, t->crl, 0.0, t->csc, -1.0, 0.0, 0.0, 0.0, VB, pos_x, 0))
        return -1;
    return R.n;
}

/* tonelib.pulse_series' cache (_PULSE_CACHE): keyed by T, t0 and the period
 * rounded to 7 places (Python's round), fmax and taper; the first series
 * made for a key is every later one's */
typedef struct {
    double k[5];
    int n;
    double *s;
} PulseMemo;
static PulseMemo pulse_memo[256];
static int pulse_nmemo = 0;
static pthread_mutex_t pulse_mu = PTHREAD_MUTEX_INITIALIZER;

static double round7(double x)
{
    char b[64];
    snprintf(b, sizeof b, "%.7f", x);
    return strtod(b, NULL);
}

int nv_pulse_series(double T, double t0, double period, double fmax, double taper, double *out, int cap);

static const double *pulse_series_memo(double T, double t0, double period, double fmax, double taper, int *n)
{
    double k[5] = {round7(T), round7(t0), round7(period), fmax, taper};
    pthread_mutex_lock(&pulse_mu);
    for (int i = 0; i < pulse_nmemo; i++)
        if (!memcmp(pulse_memo[i].k, k, sizeof k)) {
            *n = pulse_memo[i].n;
            const double *s = pulse_memo[i].s;
            pthread_mutex_unlock(&pulse_mu);
            return s;
        }
    int cap = (int)nearbyint(4 * fmax * period) / 2 + 2;
    double *s = (double *)malloc(sizeof(double) * 3 * (size_t)cap);
    int m = s ? nv_pulse_series(T, t0, period, fmax, taper, s, cap) : -1;
    if (m < 0 || m > cap || pulse_nmemo >= 256) {
        free(s);
        pthread_mutex_unlock(&pulse_mu);
        return NULL;
    }
    memcpy(pulse_memo[pulse_nmemo].k, k, sizeof k);
    pulse_memo[pulse_nmemo].n = m;
    pulse_memo[pulse_nmemo].s = s;
    pulse_nmemo++;
    pthread_mutex_unlock(&pulse_mu);
    *n = m;
    return s;
}

/* blockrender._note_pulse: A PRESSURE PULSE (the gunshot's N-wave) -- one
 * period of its Fourier series, every partial under one gate, opened two
 * blocks before the pulse (or at the render's start, the pulse NON into the
 * series) and shut a block after it, the period long enough that the next
 * pulse falls after it has shut; its length from the key (pulse_length: the
 * spectrum's peak on f0, within its range); each partial the voice's gain x
 * its amplitude x the radiation, its phase the series', with its room
 * images. Returns the rows written, -1 if the store was too small or the
 * series could not be made. */
int nv_pulse(const VoiceSnap *v, const ToneIn *t, double f0, double blk, double lo_ms, double hi_ms, double peak,
             double fmax, double taper, double pos_x, int nimg, const int *nsurf, const int *surf, const double *img,
             const double *mir, double *rows, int cap, double *qacc, double *azimuth)
{
    Rows R = {rows, 0, cap};
    double terms[9 * 64];
    double VB[3] = {0.0, 5.5, 0.0};
    double SR = t->sr;
    double T = pymin(hi_ms, pymax(lo_ms, 1000.0 * peak / pymax(f0, 1.0))) / 1000.0;
    double lead = 2.0 * blk, rel = 0.002 * SR;
    double gate = lead + T * SR + blk;
    double per = (gate + rel + blk + 0.002 * SR) / SR;
    double pnon = pymax(0.0, t->non - lead);
    double t0 = t->non >= lead ? lead : t->non;
    int ns = 0;
    const double *s = pulse_series_memo(T, t0 / SR, per, fmax, taper, &ns);
    if (!s)
        return -1;
    for (int i = 0; i < ns; i++) {
        double hf = s[3 * i], amp = s[3 * i + 1], ph = s[3 * i + 2];
        double gM = v->gain * amp * nv_radiation_gain(v, hf, 0.0, 0);
        int nt_ = 0;
        if (t->reflect) {
            nt_ = note_terms(v, t, hf, t->pos_x_props, t->pos_z, nimg, nsurf, surf, img, mir, terms);
            if (nt_ < 0)
                return -1;
        }
        if (!emit(v, t, &R, qacc, azimuth, terms, nt_, 2 * PI * hf / SR, gM * nv_hrtf_gain(v, hf, t->li),
                  gM * nv_hrtf_gain(v, hf, t->ri), gM, hf, pnon, pnon + gate, 1.0, rel, t->chiff, 0.0, 0.0, 0.0,
                  1.0, 0.0, t->cc, t->crl, 0.0, t->csc, -1.0, 0.0, ph, 0.0, VB, pos_x, 0))
            return -1;
    }
    return R.n;
}

/* blockrender._note_grains: sparse damped sines at Poisson instants (rate a
 * second; negative, a clock: one every -1/rate s from the onset, each 7%
 * rms off it) through the held note, each its own pitch across the band and
 * level under its row's dB by up to its scatter, a millisecond's rise, dying
 * at its dB/s -- or a CLUSTER (n sines at one instant, each its pitch, at
 * 1/sqrt(n)) -- a glide from rise x its pitch where the row has one; drawn
 * from the note (seed), no images. The caller sets the row, the noise width
 * and the emitter. Returns the rows written, -1 if the store was too small. */
static double pyr_expovariate(PyRandom *r, double lambd) { return -log(1.0 - pyr_random(r)) / lambd; }

int nv_grains(const VoiceSnap *v, const ToneIn *t, int ng, const double (*g)[9], long long seed, double settle,
              double pos_x, double *rows, int cap, double *qacc, double *azimuth)
{
    Rows R = {rows, 0, cap};
    double VB[3] = {0.0, 5.5, 0.0};
    double sr = t->sr;
    PyRandom rg;
    pyr_seed(&rg, seed);
    double hf = 0.0;
    for (int r = 0; r < ng; r++) {
        double lo = g[r][0], hi = g[r][1], rate = g[r][2], db = g[r][3], dsc = g[r][4], dps = g[r][5];
        ToneIn tg = *t;
        if (g[r][6] > 0.0) {                /* a bubble's ring rising as it nears the surface */
            tg.gl[0] = 1.0 / g[r][6] - 1.0;
            tg.gl[1] = g[r][7];
            tg.gl[2] = g[r][7] * settle;
        }
        double per = rate < 0.0 ? -1.0 / rate : 0.0;
        double tt = per != 0.0 ? t->non : t->non + pyr_expovariate(&rg, rate) * sr;
        double glr = log(10.0) / 20.0 * dps;
        int ncl = g[r][8] > 0.0 ? (int)g[r][8] : 1;
        double gcl = 1.0 / sqrt((double)ncl);
        while (tt < t->noff) {
            double gM0;
            if (ncl == 1) {
                hf = lo * pow(hi / lo, pyr_random(&rg));         /* (the draws in their order: pitch, then level) */
                gM0 = v->gain * pow(10.0, (db - pyr_uniform(&rg, 0.0, dsc)) / 20.0);
            } else {
                gM0 = v->gain * pow(10.0, (db - pyr_uniform(&rg, 0.0, dsc)) / 20.0) * gcl;
            }
            for (int k = 0; k < ncl; k++) {
                if (ncl > 1)
                    hf = lo * pow(hi / lo, pyr_random(&rg));
                double gM = gM0;
                if (hf < 0.45 * sr) {
                    double ph0 = pyr_random(&rg) * 2.0 * PI;
                    if (!emit(v, &tg, &R, qacc, azimuth, NULL, 0, 2 * PI * hf / sr, gM * nv_hrtf_gain(v, hf, t->li),
                              gM * nv_hrtf_gain(v, hf, t->ri), gM, hf, tt, tt + 0.1 * sr, 8.0, 0.005 * sr, t->chiff,
                              glr, 0.0, 0.0, 0.0, 0.0, t->cc, t->crl, 0.0, t->csc, -1.0, 0.0, ph0, 0.0, VB, pos_x, 0))
                        return -1;
                }
            }
            tt += (per != 0.0 ? pymax(0.2 * per, pyr_gauss(&rg, per, 0.07 * per)) : pyr_expovariate(&rg, rate)) * sr;
        }
    }
    return R.n;
}

/* blockrender._note_phantoms: the wound bass's phantom partials -- f_i + f_j
 * of the note's transverse partials (trans: ntrans of (hz, raw gain, dB/s),
 * nv_tone's), gain coupling v_i v_j (twice for i != j) times the radiation,
 * decay d_i + d_j; centred, no HRTF gain; with their room images. The
 * emitter as the tone leaves it (player 0, no vibrato, the voice's own
 * place). qacc and *azimuth as nv_tone's. Returns the rows written, -1 if
 * the store was too small. */
int nv_phantom(const VoiceSnap *v, const ToneIn *t, const double *trans, int ntrans,
               int nimg, const int *nsurf, const int *surf, const double *img, const double *mir,
               double *rows, int cap, double *qacc, double *azimuth)
{
    Rows R = {rows, 0, cap};
    double terms[9 * 64];
    double VB[3] = {0.0, 5.5, 0.0};
    double sr = t->sr;
    double coupling = v->phantom_coupling;
    double power = v->phantom_register_power;
    if (power > 0.0)
        coupling *= pow(v->phantom_ref_hz / t->f0, power);
    if (!(coupling > 0.0 && t->f0 <= v->phantom_note_max_hz && ntrans > 0))
        return 0;
    int np = ntrans < v->phantom_max_order ? ntrans : v->phantom_max_order;
    if (np <= 0)
        return 0;
    double vmax = trans[1];
    for (int i = 1; i < np; i++)
        if (trans[3 * i + 1] > vmax)
            vmax = trans[3 * i + 1];
    double floor_ = v->phantom_gain_floor * vmax;
    for (int a = 0; a < np; a++) {
        double fa = trans[3 * a], va = trans[3 * a + 1], da = trans[3 * a + 2];
        for (int b = a; b < np; b++) {
            double fb = trans[3 * b], vb = trans[3 * b + 1], db_ = trans[3 * b + 2];
            double fph = fa + fb;
            if (fph >= sr / 2)
                break;
            double g = coupling * va * vb * (a == b ? 1.0 : 2.0) * nv_radiation_gain(v, fph, 0.0, 0);
            if (g < floor_)
                continue;
            double dph = da + db_;
            double lrp = dph > 0 ? log(db_ratio(dph)) : 0.0;
            double af[2];
            nv_aftersound(v, t->f0, dph, af);
            double lrAp = af[1] > 0 ? log(db_ratio(af[1])) : 0.0;
            int nt_ = 0;
            if (t->reflect) {
                nt_ = note_terms(v, t, fph, t->pos_x_props, t->pos_z, nimg, nsurf, surf, img, mir, terms);
                if (nt_ < 0)
                    return -1;
            }
            if (!emit(v, t, &R, qacc, azimuth, terms, nt_, 2 * PI * fph / sr, g, g, g, fph, t->non, t->noff,
                      t->fade, t->rel, t->chiff, lrp, lrAp, af[0], t->sustain_level, 0.0, 0.0, 0.0, 0.0, t->csc,
                      -1.0, 0.0, 0.0, 0.0, VB, t->pos_x_props, 0))
                return -1;
        }
    }
    return R.n;
}

/* blockrender's A TOUCHED STRING'S OTHER MODES (touch_leak_db): the modes
 * the touch kills (k not a multiple of it, to 48) at k/n of the note --
 * stretched by Bs, the string's B -- each as the string would have it
 * untouched (SynthProperties.touch_leak_modes: the pick's comb, the tilt,
 * the coils), dying at leak_dbs; with their room images, their phases from
 * lr (the note's own stream). qacc and *azimuth as nv_tone's. Returns the
 * rows written, -1 if the store was too small. */
int nv_ring(const VoiceSnap *v, const ToneIn *t, double f0, int n, const double *hz, const double *db,
            const double *dps, double skip, int nown, const double *own_r, PyRandom *rr, int nimg,
            const int *nsurf, const int *surf, const double *img, const double *mir, double *rows, int cap,
            double *qacc, double *azimuth)
{
    Rows R = {rows, 0, cap};
    double terms[9 * 64];
    double VB[3] = {0.0, 5.5, 0.0};
    double sr = t->sr;
    double own[17];                 /* f0 at each of the note's own mode ratios, and 2 f0 */
    for (int j = 0; j < nown; j++)
        own[j] = f0 * own_r[j];
    own[nown] = 2.0 * f0;
    for (int q = 0; q < n; q++) {
        double hf = hz[q];
        if (hf >= 0.45 * sr)
            continue;
        int on_own = 0;
        for (int j = 0; j <= nown; j++)
            if (fabs(hf / own[j] - 1.0) < skip)
                on_own = 1;
        if (on_own)
            continue;
        double gM = v->gain * pow(10.0, db[q] / 20.0);
        int nt_ = 0;
        if (t->reflect) {
            nt_ = note_terms(v, t, hf, t->pos_x_props, t->pos_z, nimg, nsurf, surf, img, mir, terms);
            if (nt_ < 0)
                return -1;
        }
        double ph0 = pyr_random(rr) * 2.0 * PI;
        if (!emit(v, t, &R, qacc, azimuth, terms, nt_, 2 * PI * hf / sr, gM * nv_hrtf_gain(v, hf, t->li),
                  gM * nv_hrtf_gain(v, hf, t->ri), gM, hf, t->non, pymax(t->noff, t->non + 4.0 * sr), t->fade,
                  t->rel, t->chiff, log(10.0) / 20.0 * dps[q], 0.0, 0.0, 0.0, 0.0, t->cc, t->crl, 0.0, t->csc,
                  -1.0, 0.0, ph0, 0.0, VB, t->pos_x_props, 2))
            return -1;
    }
    return R.n;
}

int nv_leak(const VoiceSnap *v, const ToneIn *t, double Bs, PyRandom *lr, int nimg, const int *nsurf,
            const int *surf, const double *img, const double *mir, double *rows, int cap, double *qacc,
            double *azimuth)
{
    Rows R = {rows, 0, cap};
    double terms[9 * 64];
    double VB[3] = {0.0, 5.5, 0.0};
    double sr = t->sr;
    int n = v->touch;
    if (n < 2 || !v->leak_set)
        return 0;
    double fs = t->f0 / n;
    double lk = pow(10.0, v->leak_db / 20.0);
    double llr = log(10.0) / 20.0 * v->leak_dbs;
    for (int k = 1; k <= 48; k++) {
        if (k % n == 0)
            continue;
        double comb = v->pk_sp != 0.0 ? (1.0 - v->eg_depth) + v->eg_depth * fabs(sin(k * PI * v->pk_sp)) : 1.0;
        double a = v->gain / pow((double)k, v->attack_dampening) * comb;
        if (v->n_pk)
            a *= eg_pickup_gain(v, k);
        a = a * lk;
        double hf = fs * k * (Bs > 0 ? 1.0 + 0.5 * ((double)(k * k) - 1.0) * Bs : 1.0);
        if (hf >= 0.45 * sr)
            continue;
        double gM = a * nv_radiation_gain(v, hf, 0.0, 0);
        int nt_ = 0;
        if (t->reflect) {
            nt_ = note_terms(v, t, hf, t->pos_x_props, t->pos_z, nimg, nsurf, surf, img, mir, terms);
            if (nt_ < 0)
                return -1;
        }
        double ph0 = pyr_random(lr) * 2.0 * PI;
        if (!emit(v, t, &R, qacc, azimuth, terms, nt_, 2 * PI * hf / sr, gM * nv_hrtf_gain(v, hf, t->li),
                  gM * nv_hrtf_gain(v, hf, t->ri), gM, hf, t->non, pymax(t->noff, t->non + 0.5 * sr), t->fade,
                  t->rel, t->chiff, llr, 0.0, 0.0, 0.0, 0.0, t->cc, t->crl, 0.0, t->csc, -1.0, 0.0, ph0, 0.0, VB,
                  t->pos_x_props, 0))
            return -1;
    }
    return R.n;
}

#include "organ.c"     /* a registered organ's note */

/* blockrender._note_release_click: THE KEY-UP'S CLICK -- the jack's fixed
 * modes (K's click_hz, click_amp) at note-off (noff, samples), riding the
 * note's gain (the last stop's, as _note_stops returns it), each above its floor; on
 * an organ with choirs (click_jacks) one click a stop drawn at the key-up,
 * at its jack's offset (the rank's contact) and its own phase
 * (Random(crc32("rank|key|click"))); with their room images. The jacks'
 * rows into out. Returns the rows written, -1 if the store was too small. */
int nv_click(const VoiceSnap *v, const ToneIn *t, const NoteClass *K, const NoteIn *n, double noff, int nimg,
             const int *nsurf, const int *surf, const double *img, const double *mir, double *rows, int cap,
             double *qacc, double *azimuth, NoteOut *out)
{
    Rows R = {rows, 0, cap};
    double terms[9 * 64];
    double VB[3] = {0.0, 5.5, 0.0};
    const OrganSpec *og = K->organ;
    /* (_note_stops' gain: the last stop's -- an organ's last rank's, else the one stop's) */
    double sr = t->sr, gain = og && og->n_rank ? og->rank[og->n_rank - 1].gain : 1.0;
    double cg = gain * pow(10.0, K->click_db / 20.0);
    double cdec = log(db_ratio(K->click_dec));
    int nj = 0, jr[32];
    if (og && K->click_jacks) {
        for (int ri = 0; ri < og->n_rank && nj < 32; ri++)
            if (n->rank_drawn_off[ri])
                jr[nj++] = ri;
    } else {
        jr[nj++] = -1;
    }
    for (int j = 0; j < nj; j++) {
        int j0 = R.n;
        double jo = jr[j] >= 0 ? og->rank[jr[j]].contact[n->note] : 0.0;
        double ph = 0.0;
        if (jr[j] >= 0) {
            char b[96];
            int nb = snprintf(b, sizeof b, "%s|%d|click", og->rank[jr[j]].key, n->note);
            PyRandom g;
            pyr_seed(&g, (long long)organ_crc32(b, (size_t)nb));
            ph = pyr_random(&g) * 2.0 * PI;
        }
        /* (a Clavinet's: the note's own, its __init__'s -- VoiceSnap.vk_*) */
        int nk = v->vk_n ? v->vk_n : K->n_click;
        for (int q = 0; q < nk; q++) {
            double chz = v->vk_n ? v->vk_hz[q] : K->click_hz[q];
            if (chz >= sr / 2)
                continue;
            double a = cg * (v->vk_n ? v->vk_amp[q] : K->click_amp[q]) * nv_radiation_gain(v, chz, 0.0, 0);
            if (a < 3e-3 * gain)
                continue;
            double non = noff + jo * sr;
            int nt_ = 0;
            if (t->reflect) {
                nt_ = note_terms(v, t, chz, t->pos_x_props, t->pos_z, nimg, nsurf, surf, img, mir, terms);
                if (nt_ < 0)
                    return -1;
            }
            if (!emit(v, t, &R, qacc, azimuth, terms, nt_, 2 * PI * chz / sr, a * nv_hrtf_gain(v, chz, t->li),
                      a * nv_hrtf_gain(v, chz, t->ri), a, chz, non, non + K->click_s * sr, pymax(1e-4, 0.0005) * sr,
                      pymax(1e-4, 0.002) * sr, t->chiff, cdec, cdec, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, t->csc, -1.0, 0.0,
                      ph, 0.0, VB, t->pos_x_props, 0))
                return -1;
        }
        out->jack_n[out->n_jack] = R.n - j0;
        out->jack_rank[out->n_jack] = jr[j];
        out->jack_off[out->n_jack] = jo;
        out->n_jack++;
    }
    out->n_click = R.n;
    return R.n;
}
#include "npyrandom.c" /* numpy's normal stream (the organ's wind) */
#include "pocketfft.c" /* numpy's rfft (the gunshot's N-wave: nv_pulse_series) */
