// slab.cpp -- the native engine's LIVE SLAB: live.Slab's core, and a live
// part on it (live.Part: any native voice -- it began as the piano's).
//
// The slab is live's partial table: a fixed capacity of slots, each a row of
// the kernel's columns, the free ones in a queue. A press stamps its key's
// template into free slots (Slab.stamp_cols): the template's columns, each
// partial's onset moved to the press with its phase moved to match, its end
// left open (IDLE) until the key comes up, its level scaled by the velocity
// and the headroom. A key-up releases them (Slab.release: noff at the key-up,
// plus its own delay); once a release has rung out, reap frees the slots.
// Bit for bit live.Slab's columns (numpy's float32 arithmetic, its pairwise
// mean), checked by examples/slab_check.py.
//
// Not here yet (refused by the caller): a section's onset scatter, a
// contact's, grain's or stroke's offsets, a catch's own end, the taps, the
// Moog's rows, Leslie, filters and the damper tracks.

#include <algorithm>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <climits>
#include <chrono>
#include <cmath>
#include <complex>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <functional>
#include <map>
#include <memory>
#include <tuple>
#include <set>
#include <utility>
#include <vector>

#include "live.h"
#include "nv.h"
#include "pycompat.h"          // a section's entries: random.Random
#include "gsdisplay.h"         // the Sound Canvas's display

extern "C" int nv_tcache_slur_fade(void *h, int program, int note, double *out);
extern "C" const NoteClass *nv_tcache_note_class(void *h, int program, int note);
extern "C" int nv_tcache_glide(void *h, int program, int src, int tgt, int cc5, double *out, double moog_tau);

// numpy.interp at one x (tone.c's np_interp)
static double sl_interp(double x, const double *xp, const double *fp, int n)
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
    if (std::isnan(r)) {
        r = slope * (x - xp[j + 1]) + fp[j + 1];
        if (std::isnan(r) && fp[j] == fp[j + 1])
            r = fp[j];
    }
    return r;
}

// moog.knob_glide_tau: GLIDE's lag in cents, seconds (0: none)
static double moog_glide_tau(double v)
{
    static const double CC[9] = {0.0, 16.0, 32.0, 48.0, 64.0, 80.0, 96.0, 112.0, 127.0};
    static const double TAU[9] = {0.0021, 0.0045, 0.0110, 0.027, 0.062, 0.146, 0.355, 1.02, 5.03};
    double gv[9], gl[9];
    for (int i = 0; i < 9; i++) {
        gv[i] = CC[i] / 127.0;
        gl[i] = log(TAU[i]);
    }
    v = v < 1.0 ? v : 1.0;
    v = v > 0.0 ? v : 0.0;
    if (v <= 0.0)
        return 0.0;
    return exp(sl_interp(v, gv, gl, 9));
}

// moog.knob_lfo2_rate: LFO 2 RATE, Hz
static double moog_lfo2_rate(double v)
{
    static const double CC[9] = {0.0, 16.0, 32.0, 48.0, 64.0, 80.0, 96.0, 112.0, 127.0};
    static const double HZ[9] = {0.023, 0.042, 0.20, 0.643, 1.50, 2.94, 5.08, 8.0, 11.72};
    double lv[9], ll[9];
    for (int i = 0; i < 9; i++) {
        lv[i] = CC[i] / 127.0;
        ll[i] = log(HZ[i]);
    }
    v = v < 1.0 ? v : 1.0;
    v = v > 0.0 ? v : 0.0;
    return exp(sl_interp(v, lv, ll, 9));
}

// moog.lfo2_on / lfo2_mods: whether LFO 2 goes anywhere; at phase x under
// the wheel w, (the pitch ratio, the cutoff's factor, the level's gain)
static bool moog_lfo2_on(const double *pn)
{
    return pn[NV_MK_LFO2_PITCH] != 0.0 || pn[NV_MK_LFO2_CUT] != 0.0 || pn[NV_MK_LFO2_AMP] != 0.0;
}
static void moog_lfo2_mods(const double *pn, double w, double x, double *pr, double *cf, double *ag)
{
    x = x - floor(x);                       // (Python's x % 1.0, x >= 0)
    const double tri = 1.0 - 4.0 * fabs(x - 0.5), d = w * w;
    *pr = pn[NV_MK_LFO2_PITCH] != 0.0 ? pow(2.0, 684.0 * d * tri / 1200.0) : 1.0;
    *cf = pn[NV_MK_LFO2_CUT] != 0.0 ? pow(2.0, 4.6 * d * tri) : 1.0;
    *ag = pn[NV_MK_LFO2_AMP] != 0.0 ? 1.0 - pow(w, 1.55) * (1.0 - tri) * 0.5 : 1.0;
}

// moog.a_vel_gain: A ENV VEL on, the amplitude at velocity vel re 127's
static double moog_a_vel_gain(int vel)
{
    static const double V[8] = {1.0, 10.0, 25.0, 40.0, 60.0, 80.0, 100.0, 127.0};
    static const double DB[8] = {-80.0, -44.5, -15.1, -10.7, -6.9, -4.3, -2.2, 0.0};
    return pow(10.0, sl_interp((double)vel, V, DB, 8) / 20.0);
}
extern "C" const OrganSpec *nv_tcache_organ(void *h, int program);
extern "C" const NoteClass *nv_tcache_class(void *h, int program);
extern "C" const NoteClass *nv_tcache_key_class(void *h, int program, int key);
extern "C" double nv_tcache_trim(void *h, int program);
extern "C" double nv_cab_gain(const NoteClass *k, double hz);
extern "C" void *nv_livebus_new(const double *fc, double sr, int frames, void *cn, void *cp, void *cf);
extern "C" void nv_livebus_process(void *h, const float *L, const float *R, double gain, float *oL, float *oR);
extern "C" void nv_livebus_free(void *h);
extern "C" const nv::live::Template *nv_tcache_at(void *h, long i, long *n);
extern "C" long nv_amp_live_t(const double *f, const double *a, const double *p, long n, double sr, double drive,
                              double window_s, int oversample, int keep, double **out, unsigned threads,
                              double reference, double imbalance);
extern "C" void nv_leslie_lobe_of(double f, int horn, const double *L, double *fl, double *sh);
extern "C" void nv_leslie_params(long n, const double *nf, const char *flip, const double *L, char *horn, float *fl,
                                 float *sh, double *nrm);
extern "C" void nv_scan_prep(const double *X, long n, const float *nf, const float *aL, const float *aR,
                             const long long *non, const float *rdl, int depth, int chorus, double sr, int *band,
                             double *dry, double *sc, long *ns, long **src, double **mm, double **cc);
extern "C" void nv_scan_bc(const double *X, double t0, double t1, int depth, int band, int chorus, double sr,
                           double *c);
extern "C" double nv_tcache_freq(void *h, int note);
extern "C" int nv_tcache_gm2(void *h);
extern "C" int nv_tuning_excl(const uint8_t *d, int n, int *iv, double *dv, double *hz);
extern "C" int nv_tuning_table(const char *name, int ref_note, double ref_hz, double *out, int *have);
extern "C" int nv_tcache_get_raga(void *h, double *sw, int *nsw);
extern "C" double nv_meend_cents(double nc, const double *sw, int nsw, double range_c, double pull, double strength);

extern "C" double nv_damper_contact(int p, int key, int top);

// tapkernel.c (live.py's, built with libnative under its own flags): the
// insertion effect's copies written into the scratch rows
extern "C" int tap_expand(int ncol, void **colp, const int *colsz, int nsrc, const int64_t *src, const int32_t *set,
                          double *om, double *p0, double *p0R, int64_t *non, int64_t *noff, float *nf, float *aL,
                          float *aR, float *vd, float *vr, float *vp, float *vdl, float *delL, float *delR,
                          int32_t *fx, int32_t *gr, int32_t *br, const int32_t *ts, const double *eq,
                          const int32_t *eqo, const int32_t *nmid, const double *dry, const double *al0,
                          const double *ar0, const int64_t *tD, const double *tg, const double *tfc,
                          const double *tr, const double *thz, const double *tal1, const double *tar1,
                          const double *tdl, const double *tvd, const double *tvr, const double *tph,
                          const float *re, double floor, int64_t n0, int64_t n1, double beta, double sr,
                          int64_t idle, int64_t dst0, int cap, int identity, int moog_w, int64_t ucap,
                          int64_t *units);

extern "C" {
// livereg.cpp: register.LiveChannel
void *nv_lreg_new(const StringMode *modes, int M, double sr, double kappa, double knock, double fall, double fl,
                  int top, double beta);
int nv_lreg_strike(void *h, long long sid, int key, double at, int R, const double *cols, const long *slot,
                   const int *free_keys, int nfree);
int nv_lreg_release(void *h, long long sid, double at, const int *free_keys, int nfree);
void nv_lreg_damp(void *h, const int *keys, int n);
int nv_lreg_felt(void *h, double at, const int *keys, const double *rates, int n);
int nv_lreg_answer(void *h, long *idx, double *z, double *floor_);
void nv_lreg_forced(void *h, long *slot, double *wgt, double *beta, double *val);
void nv_lreg_free(void *h);
int nv_cl_launch(void *h, int slot, const void *D, long dn, const void *C, long cn, const void *S, long sn, int nd,
                 long long n0, int frames, int send, int mg);
int nv_cl_collect(void *h, int slot, float *out);
int nv_cl_samples(void *h, const void *D, long dn, const void *C, long cn, const void *S, long sn, int nd,
                  long long n0, int frames, int send, int mg, float *out);
}

// numpy's pairwise sum of float64 (DOUBLE_pairwise_sum, PW_BLOCKSIZE 128),
// and np.sum's 8192-element buffers each summed in turn -- tubeamp.cpp's own
static double pairwise_d(const double *a, long n)
{
    if (n < 8) {
        double r = 0.0;
        for (long i = 0; i < n; i++)
            r += a[i];
        return r;
    }
    if (n <= 128) {
        double r[8];
        for (int j = 0; j < 8; j++)
            r[j] = a[j];
        long i = 8;
        for (; i < n - (n % 8); i += 8)
            for (int j = 0; j < 8; j++)
                r[j] += a[i + j];
        double res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        for (; i < n; i++)
            res += a[i];
        return res;
    }
    long n2 = n / 2;
    n2 -= n2 % 8;
    return pairwise_d(a, n2) + pairwise_d(a + n2, n - n2);
}

static double npsum(const double *a, long n)
{
    double r = 0.0;
    for (long i = 0; i < n; i += 8192)
        r += pairwise_d(a + i, std::min(8192L, n - i));
    return r;
}

namespace nv {
namespace slab {

static const long long IDLE = 1LL << 62;        // live.IDLE

// live's column groups, in live.py's order
static const char *F8[] = {"om", "p0", "p0R", "fmw", "fmp", "fmpR"};
static const char *F4[] = {"aL", "aR", "nf", "fa", "re", "ch", "logr", "logrA", "aft", "sus", "cv", "cc", "crl",
                           "sj", "csc", "cbw", "tbav", "tau", "tcut", "vd", "vr", "vp", "delL", "delR", "az", "rdl",
                           "nfr"};
static const char *F4N[] = {"gb", "gt", "gc", "vdl"};
static const char *I8[] = {"non", "noff"};
static const char *I4[] = {"gr", "cr", "br", "pl", "fx", "mk"};
enum { NF8 = 6, NF4 = 27, NF4N = 4, NI8 = 2, NI4 = 6 };
enum { F4_aL = 0, F4_aR = 1, F4_nf = 2, F4_fa = 3, F4_re = 4, F4_ch = 5, F4_logr = 6, F4_logrA = 7, F4_aft = 8, F4_sus = 9, F4_cbw = 15, F4_vd = 19, F4_vr = 20, F4_delL = 22, F4_delR = 23, F4_rdl = 25 };
enum { F8_om = 0, F8_p0 = 1, F8_p0R = 2, F8_fmw = 3, F8_fmp = 4, F8_fmpR = 5 };
enum { F4_nfr = 26 };
enum { I4_gr = 0, I4_cr = 1, I4_br = 2, I4_fx = 4, I4_mk = 5 };

// numpy's pairwise sum of a float32 array (its float accumulator), as np.mean takes it
extern "C" void nv_log_n(long n, const double *x, double *out);   // exactmath.c: libm's log
extern "C" const NoteClass *nv_tcache_class_key(void *h, int program, int key);

// tonelib._apow: libm's pow, its square at 2 (numpy's ** 2.0)
static double apow(double x, double y) { return y == 2.0 ? x * x : pow(x, y); }

// tonelib.pluck_shape: the comb at the pluck point moved by CC74 over the
// comb where it was (pluck_point_moved), each partial's index read off its
// frequency under the note's stretch (the nearest in log, the first of equals)
static void pluck_shape(const NoteClass *k, const double *nf, long n, double d, double *out)
{
    double f0 = nf[0];
    for (long i = 1; i < n; i++)
        if (nf[i] < f0)
            f0 = nf[i];
    f0 = f0 > 1e-9 ? f0 : 1e-9;                 // max(nf.min(), 1e-9)
    double p0 = k->sh_sp;
    if (k->sh_nopen > 0 && k->sh_popen != 0.0) {    // (stopped_pluck_point: cls(f0)'s)
        double nn = 69.0 + 12.0 * log((f0 > 1.0 ? f0 : 1.0) / 440.0) / log(2.0);
        int any = 0;
        double o = 0.0, lo = k->sh_open[0];
        for (int i = 0; i < k->sh_nopen; i++) {
            if (k->sh_open[i] <= nn + 0.5 && (!any || k->sh_open[i] > o)) {
                o = k->sh_open[i];
                any = 1;
            }
            if (k->sh_open[i] < lo)
                lo = k->sh_open[i];
        }
        if (!any)
            o = lo;
        double p = fmod(k->sh_popen * pow(2.0, (nn - o) / 12.0), 1.0);
        double q = 1.0 - p;
        p = q < p ? q : p;                      // min(p, 1 - p)
        p0 = 0.02 > p ? 0.02 : p;               // max(0.02, ...)
    }
    double p1;                                  // pluck_point_moved
    if (d >= 0.0) {
        double b = 0.06 < p0 ? 0.06 : p0;       // min(PLUCK_BRIGHT, p)
        p1 = p0 * pow(b / p0, d);
    } else {
        p1 = p0 * pow(0.5 / p0, -d);
    }
    int mh = k->sh_mh;
    std::vector<double> r(mh), lr(mh), x(n), lx(n);
    for (int j = 0; j < mh; j++) {
        double hm = (double)(j + 1);
        r[j] = hm * (1.0 + 0.5 * (hm * hm - 1.0) * k->sh_B);
    }
    for (long i = 0; i < n; i++)
        x[i] = nf[i] / f0;
    nv_log_n(mh, r.data(), lr.data());
    nv_log_n(n, x.data(), lx.data());
    double dp = k->sh_sd;
    for (long i = 0; i < n; i++) {
        int best = 0;
        double bd = fabs(lx[i] - lr[0]);
        for (int j = 1; j < mh; j++) {
            double dd = fabs(lx[i] - lr[j]);
            if (dd < bd) {
                bd = dd;
                best = j;
            }
        }
        double m = (double)(best + 1);
        double c1 = (1.0 - dp) + dp * fabs(sin(m * M_PI * p1));
        double c0 = (1.0 - dp) + dp * fabs(sin(m * M_PI * p0));
        out[i] = c1 / (c0 > 1e-3 ? c0 : 1e-3);
    }
}

// tonelib._two_pole: |H| of a two-pole low-pass at x = f/fc, quality q
static double two_pole(double x, double q)
{
    double a = 1.0 - x * x, b = x / q;
    return 1.0 / sqrt(a * a + b * b);
}

// tonelib.sound_shape: a per-partial gain for brightness (bright: granted)
// and resonance (res: granted), not yet normalised
static void sound_shape(const NoteClass *k, const double *nf, long n, double db, double dr, bool bright,
                        bool res, double *g)
{
    for (long i = 0; i < n; i++)
        g[i] = 1.0;
    if (!n)
        return;
    if (db != 0.0 && bright) {
        double et = k->sh_et, corner = k->sh_corner;
        if (k->sh_pluck) {
            std::vector<double> ps(n);
            pluck_shape(k, nf, n, db, ps.data());
            for (long i = 0; i < n; i++)
                g[i] *= ps[i];
        } else if (et != 0.0) {
            double kk = et * (12.0 * db) / 6.0206;
            double mn = nf[0];
            for (long i = 1; i < n; i++)
                if (nf[i] < mn)
                    mn = nf[i];
            mn = mn > 1e-9 ? mn : 1e-9;
            for (long i = 0; i < n; i++)
                g[i] *= apow(nf[i] / mn, kk);
        } else if (corner != 0.0) {
            double order = k->sh_order, c2 = corner * pow(4.0, db);
            for (long i = 0; i < n; i++)
                g[i] *= (1.0 + apow(nf[i] / corner, order)) / (1.0 + apow(nf[i] / c2, order));
        }
    }
    if (dr != 0.0 && res) {
        double mq = k->sh_mq, corner = k->sh_corner;
        if (mq != 0.0 && k->sh_mhz != 0.0) {
            double hz = k->sh_mhz, boost = pow(10.0, k->sh_mdb / 20.0) - 1.0, q2 = mq * pow(4.0, dr);
            for (long i = 0; i < n; i++) {
                double r = nf[i] / hz, u = r - 1.0 / r;
                double a = q2 * u, b = mq * u;
                g[i] *= ((1.0 + boost / (1.0 + a * a)) / (1.0 + boost / (1.0 + b * b)));
            }
        } else if (corner != 0.0) {
            double c = corner * ((db != 0.0 && bright && k->sh_et == 0.0) ? pow(4.0, db) : 1.0);
            double q0 = pow(0.5, 0.5), q1 = q0 * pow(4.0, dr);
            for (long i = 0; i < n; i++) {
                double x = nf[i] / c;
                g[i] *= two_pole(x, q1) / two_pole(x, q0);
            }
        }
    }
}

// tonelib.normalise_power: g scaled so amp g carries amp's power
static void normalise_power(const double *amp, long n, double *g)
{
    std::vector<double> a2(n), b2(n);
    for (long i = 0; i < n; i++) {
        a2[i] = amp[i] * amp[i];
        double b = amp[i] * g[i];
        b2[i] = b * b;
    }
    double p0 = npsum(a2.data(), n), p1 = npsum(b2.data(), n);
    double f = (p1 > 0.0 && p0 > 0.0) ? pow(p0 / p1, 0.5) : 1.0;
    for (long i = 0; i < n; i++)
        g[i] *= f;
}

extern "C" void nv_sound_shape(const NoteClass *k, const double *nf, long n, double db, double dr, int bright,
                               int res, double *g)
{
    sound_shape(k, nf, n, db, dr, bright != 0, res != 0, g);
}

extern "C" void nv_normalise_power(const double *amp, long n, double *g) { normalise_power(amp, n, g); }

static float pairwise(const float *a, long n)
{
    if (n < 8) {
        float res = 0.0f;
        for (long i = 0; i < n; i++)
            res += a[i];
        return res;
    }
    if (n <= 128) {
        float r[8];
        for (int k = 0; k < 8; k++)
            r[k] = a[k];
        long i;
        for (i = 8; i < n - (n % 8); i += 8)
            for (int k = 0; k < 8; k++)
                r[k] += a[i + k];
        float res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        for (; i < n; i++)
            res += a[i];
        return res;
    }
    long n2 = n / 2;
    n2 -= n2 % 8;
    return pairwise(a, n2) + pairwise(a + n2, n - n2);
}

// ...and of a float64 array (np.sum's)
static double pairwise_d(const double *a, long n)
{
    if (n < 8) {
        double res = 0.0;
        for (long i = 0; i < n; i++)
            res += a[i];
        return res;
    }
    if (n <= 128) {
        double r[8];
        for (int k = 0; k < 8; k++)
            r[k] = a[k];
        long i;
        for (i = 8; i < n - (n % 8); i += 8)
            for (int k = 0; k < 8; k++)
                r[k] += a[i + k];
        double res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        for (; i < n; i++)
            res += a[i];
        return res;
    }
    long n2 = n / 2;
    n2 -= n2 % 8;
    return pairwise_d(a, n2) + pairwise_d(a + n2, n - n2);
}

typedef std::tuple<long long, long long, long long, long long> Key;    // (part, channel, note, layer)

// THE SLOTS, ONCE EACH, as numpy's x[idx] op= y takes them: a held one-shot's
// key still lists slots reaped and stamped again by a later note (live's
// Slab.live keeps them too), so a channel's slots can name one twice -- and
// a step applied twice is not live's (the fader, the pan's shadow, a bend)
static std::vector<long> once(const std::vector<long> &slots)
{
    std::vector<long> u(slots);
    std::sort(u.begin(), u.end());
    u.erase(std::unique(u.begin(), u.end()), u.end());
    return u;
}

// a row set's Leslie lobes worked out ahead (a template's, a scanner copy's,
// the valve's products': live's leslie_params memo), NULL none
struct LobePre {
    const char *horn = nullptr;
    const float *fl = nullptr, *sh = nullptr;
    const double *nrm = nullptr;
};

struct Slab {
    long cap;
    // THE TAPS' SCRATCH ROWS (live.Slab.tcap: tapkernel.c): past the slots,
    // in every kernel column (f8, f4, f4n, i8, i4, sw, aLp, aRp, dk, dg),
    // rewritten every block from the partials that carry a tap set and
    // rendered as rows -- never handed out, never busy, never reaped
    long tcap;
    std::vector<int32_t> tp;                // each slot's tap set (its channel's), -1 none
    std::vector<long long> tpx;             // ...and its longest tap: the slot is held that much longer
    long tap_m = 0;                         // scratch rows written for this block
    // ...their cost at most, in units (TAP_MOOG_COST; the budget governor's),
    // and this block's
    static const int TAP_MOOG_COST = 3;
    long long tap_ucap = 0, tap_cap = 0, tap_u = 0;
    bool tap_on = false;                    // a tap table stands (live's tap_tab is not None)
    std::vector<std::vector<double>> f8;
    std::vector<std::vector<float>> f4, f4n;
    std::vector<std::vector<long long>> i8;
    std::vector<std::vector<int32_t>> i4;
    std::vector<float> sw, aL0, aR0, sg, sre, hrel, vbase, vrbase, vsc;
    // THE TREMOLO (live.Slab.tremolo_arm / tremolo_swing): a slot armed, its
    // depth, its own baseline (captured once) and its stereo sign
    std::vector<char> tr_on;
    std::vector<float> tr_dep, tr_aL, tr_aR, tr_st;
    // a Clavinet's tone rockers (live's cv_*): the rows they have taken, and
    // each one's level unfiltered, which every move recomputes from
    std::vector<char> cv_on;
    std::vector<float> cv_aL, cv_aR;
    // THE MOVING FILTER (live.Slab.fl_*: Live._filter_block): a slot under
    // one, its effect channel, the level it would have unfiltered (a fifth
    // baseline, kept up as the others are); how many are armed (fl_on.any(),
    // a slot's flag kept until it is stamped again)
    std::vector<char> fl_on;
    std::vector<int32_t> fl_ch;
    std::vector<float> fl_aL, fl_aR;
    long fl_n = 0;
    // ...a MOOG ROW's |H| this block (live's _fl_mo: its level is its
    // panel's), on its level for the render only (moog_filter_apply), and
    // the panel's level kept to put back after (moog_filter_restore)
    std::vector<long> flm_s;
    std::vector<float> flm_l, flm_r, flm_aL, flm_aR;
    std::vector<float> hs_dep;                  // a harmonium's Tremolo stop: its depth and rate (live's)
    std::vector<double> hs_hz;
    // THE LESLIE (live.Slab.leslie_arm / leslie_swing): a slot on a rotor,
    // which (horn, else the drum), its lobe's floor, sharpness and one over
    // its mean, its angle off the cabinet, its own baseline; two mics' angle
    // apart (a Rotary's Separate: 0 here)
    std::vector<char> ls_on, ls_horn;
    std::vector<float> ls_am, ls_sharp, ls_norm, ls_ph, ls_sep, ls_aL, ls_aR;
    std::vector<double> les;                    // the Leslie's constants (leslie.cpp's L_*)
    double rate_ = 48000.0;                     // (live.Slab.rate: retune's clock)
    std::vector<int32_t> dk, slot_ch;
    std::vector<int32_t> fx_chs;            // each slot's tone-effect channel (live's fx_ch), -1 none
    // A PART'S BUS (live.Slab.bus_fill): its rows after the taps' in the
    // scratch rows, the originals hidden from the main render this block
    long bus_m = 0;
    std::vector<long> bus_hide;
    std::set<int> bus_chans;                // (tap_fill leaves their copies to the bus)
    std::vector<float> dg;                 // a damped row's weight (damper.weight)
    std::vector<float> aLp, aRp;            // pressure's columns: none on a piano, still the kernel's
    std::vector<char> busy;
    std::deque<long> free;
    // the keys sounding and their slots, in the order first stamped (a
    // Python dict: a key released and stamped again goes to the end) --
    // the order a pedal's release takes them in, so the free queue's order
    std::vector<std::pair<Key, std::vector<long>>> live;
    std::map<Key, int> oneshot;
    std::vector<std::pair<std::vector<long>, long long>> retiring;
    std::vector<long> last_slots;
    std::vector<long> *collect = nullptr;   // the slots stamp places go here too (the held notes)
    // live.Slab.rel_log: each release since the pump read it (key, n, slots)
    std::vector<std::tuple<Key, long long, std::vector<long>>> rel_log;
    // each slot's key, by id (live.Slab.owner): a slot freed while its key
    // is still held leaves that key's list
    std::vector<long long> owner;
    std::map<Key, long long> key_id;
    std::vector<Key> id_key;
    double send[256];
    // ...A VOICE'S OWN DISTANCE (live's send_said, odd_until): the channels
    // that have sent a CC91 -- a template's own send applies on any other --
    // and the sample until which the send bus must run for a slot standing
    // at a distance its channel's send does not say
    std::set<long long> send_said;
    long long odd_until = 0;
    float headroom = 1.0f;
    double headroom_d = 1.0;
    // THE GS EQ (live.Slab.eq): its shelves (lo Hz, hi Hz, lo dB, hi dB) on
    // the notes stamped while it is on, but on the channels in eq_off
    bool eq_on = false;
    double eq_lo_f = 200.0, eq_hi_f = 3000.0, eq_lo_g = 0.0, eq_hi_g = 0.0;
    unsigned eq_off = 0;
    // A SECTION'S ENTRIES ARE REDRAWN AT EVERY PRESS (live.Slab._rng)
    PyRandom scat_rng;

    explicit Slab(long capacity, long tap_capacity = -1) : cap(capacity)
    {
        tcap = tap_capacity < 0 ? 4 * capacity : tap_capacity;
        tp.assign(cap, -1);
        tpx.assign(cap, 0);
        tap_ucap = tap_cap = (long long)tcap * TAP_MOOG_COST;
        const long full = cap + tcap;           // (the kernel's columns: the slots, then the scratch rows)
        pyr_seed(&scat_rng, 0x5CA7);
        owner.assign(cap, -1);
        f8.assign(NF8, std::vector<double>(full, 0.0));
        f4.assign(NF4, std::vector<float>(full, 0.0f));
        f4n.assign(NF4N, std::vector<float>(full, 0.0f));
        i8.assign(NI8, std::vector<long long>(full, IDLE));
        i4.assign(NI4, std::vector<int32_t>(full, 0));
        // live.Slab's rest: no gate, bend row or Moog filter row (-1); unit
        // gains, harmonic ratio and vibrato scale; the vibrato at 5.5 Hz
        for (int c : {I4_gr, I4_br, I4_fx})
            i4[c].assign(full, -1);
        f4[F4_cbw].assign(full, 100000.0f);     // the wash's width: blockrender.RAND_GRAN, never 0
        sw.assign(full, 1.0f);
        aL0.assign(cap, 0.0f); aR0.assign(cap, 0.0f); sg.assign(cap, 1.0f); sre.assign(cap, 1.0f);
        hrel.assign(cap, 1.0f); vbase.assign(cap, 0.0f); vsc.assign(cap, 1.0f);
        vrbase.assign(cap, 1.0f * 5.5f);
        dk.assign(full, -1); slot_ch.assign(cap, -1); fx_chs.assign(cap, -1);
        dg.assign(full, 0.0f);
        aLp.assign(full, 0.0f); aRp.assign(full, 0.0f);
        tr_on.assign(cap, 0); tr_dep.assign(cap, 0.0f); tr_aL.assign(cap, 0.0f); tr_aR.assign(cap, 0.0f);
        cv_on.assign(cap, 0); cv_aL.assign(cap, 0.0f); cv_aR.assign(cap, 0.0f);
        fl_on.assign(cap, 0); fl_ch.assign(cap, 0); fl_aL.assign(cap, 0.0f); fl_aR.assign(cap, 0.0f);
        fl_n = 0;
        moog_alloc();
        tr_st.assign(cap, 1.0f);
        hs_dep.assign(cap, 0.0f); hs_hz.assign(cap, 0.0);
        ls_on.assign(cap, 0); ls_horn.assign(cap, 0); ls_am.assign(cap, 0.0f); ls_sharp.assign(cap, 1.0f);
        ls_norm.assign(cap, 1.0f); ls_ph.assign(cap, 0.0f); ls_sep.assign(cap, 0.0f); ls_aL.assign(cap, 0.0f);
        ls_aR.assign(cap, 0.0f);
        busy.assign(cap, 0);
        for (long i = 0; i < cap; i++)
            free.push_back(i);
        for (int c = 0; c < 256; c++)
            send[c] = 1.0;
    }

    // Slab.stamp_cols for a template with none of the offsets (scatter,
    // contact, grain) but a stroked note's (sof: each row where its stroke
    // falls) and a row's own end (rof: from its onset, where >= 0): t_* the
    // template's columns (n rows), key, n0, vel_scale, hrel, dur, oneshot,
    // the template's send (NAN: none), sof and rof (NULL: none). False if
    // the slab is full.
    bool stamp(const double *const *tf8, const float *const *tf4, const long long *const *ti8,
               const int32_t *const *ti4, const float *threl, long n, Key key, long long n0, double vel_scale,
               long long dur, bool one, double tsend, long long ch, const long long *sof = nullptr,
               const long long *rof = nullptr, double scat = 0.0, double rate = 0.0, const long long *cof = nullptr,
               const double *aL64 = nullptr, const double *aR64 = nullptr, const long long *gof = nullptr)
    {
        if (n == 0)
            return true;
        if ((long)free.size() < n)
            return false;
        // each player's entry, drawn for this press (t["pl"]: the row's player)
        std::vector<double> offs;
        if (scat != 0.0) {
            int mp = 0;
            for (long q = 0; q < n; q++)
                mp = std::max(mp, (int)ti4[3][q]);
            offs.resize(mp + 1);
            for (int p = 0; p <= mp; p++)
                offs[p] = pyr_random(&scat_rng) * scat * 0.001 * rate;
        }
        std::vector<long> idx(n);
        for (long q = 0; q < n; q++) {
            idx[q] = free.front();
            free.pop_front();
        }
        for (long q = 0; q < n; q++) {
            long s = idx[q];
            busy[s] = 1;
            dk[s] = -1;
            tp[s] = -1;                         // (a fresh slot carries no taps)
            fx_chs[s] = -1;
            for (int c = 0; c < NF4; c++)
                f4[c][s] = tf4[c][q];
            for (int c = 0; c < NI4; c++)
                i4[c][s] = ti4[c][q];
            for (int c = 0; c < NF4N; c++)
                f4n[c][s] = 0.0f;
            i4[I4_gr][s] = -1;
            i4[I4_br][s] = -1;
            i4[I4_cr][s] = 0;
            f8[F8_om][s] = tf8[F8_om][q];
            f8[F8_fmw][s] = 0.0;
            long long rd = (long long)tf4[F4_rdl][q];        // rdl.astype(int64): toward zero
            long long newnon = offs.empty() ? n0 + rd : (long long)((double)n0 + offs[ti4[3][q]]) + rd;
            if (cof)                            // a Hammond drawbar speaks when its contact closes
                newnon += cof[q];
            if (gof)                            // ...a grain lands where it falls in the note
                newnon += gof[q];
            if (sof)
                newnon += sof[q];
            double sh = tf8[F8_om][q] * (double)(ti8[0][q] - newnon);
            f8[F8_p0][s] = tf8[F8_p0][q] + sh;
            f8[F8_p0R][s] = tf8[F8_p0R][q] + sh;
            i8[0][s] = newnon;
            i8[1][s] = one ? n0 + dur + rd : IDLE;
            if (rof && rof[q] >= 0)
                i8[1][s] = newnon + rof[q];
            if (aL64) {                         // (levels in float64: a scanner's copy, numpy's product)
                f4[F4_aL][s] = (float)(vel_scale != 1.0 ? aL64[q] * vel_scale : aL64[q]);
                f4[F4_aR][s] = (float)(vel_scale != 1.0 ? aR64[q] * vel_scale : aR64[q]);
            } else if (vel_scale != 1.0) {
                f4[F4_aL][s] = tf4[F4_aL][q] * (float)vel_scale;
                f4[F4_aR][s] = tf4[F4_aR][q] * (float)vel_scale;
            }
            if (headroom_d != 1.0) {
                f4[F4_aL][s] *= headroom;
                f4[F4_aR][s] *= headroom;
            }
            // the GS EQ (live.Slab.stamp_cols: blockrender.gs_eq_gain at the
            // row's nominal frequency, the gain in float64, libm's pow)
            if (eq_on && ch >= 0 && ch < 16 && !((eq_off >> ch) & 1u)) {
                const double fq = (double)tf4[F4_nf][q];
                double x = fq / eq_lo_f, y = fq / eq_hi_f;
                x = x * x;
                y = y * y;
                const double g = pow(10.0, (eq_lo_g / (1.0 + x) + eq_hi_g * y / (1.0 + y)) / 20.0);
                f4[F4_aL][s] = (float)((double)f4[F4_aL][s] * g);
                f4[F4_aR][s] = (float)((double)f4[F4_aR][s] * g);
            }
            aL0[s] = f4[F4_aL][s];
            aR0[s] = f4[F4_aR][s];
            sg[s] = 1.0f;
            sre[s] = 1.0f;
            hrel[s] = threl[q];
            slot_ch[s] = (int32_t)ch;
            vbase[s] = tf4[F4_vd][q];
            vrbase[s] = tf4[F4_vr][q];
            tr_on[s] = 0;                       // (unarmed until its tremolo is)
            cv_on[s] = 0;                       // (...and off the rockers)
            fl_n -= fl_on[s];
            fl_on[s] = 0;                       // (...and no filter)
            hs_dep[s] = 0.0f;
            ls_on[s] = 0;                       // (...and off the rotors until armed)
        }
        // the vibrato's scale: vd over its mean (np.mean: float32, pairwise)
        std::vector<float> vd(n);
        for (long q = 0; q < n; q++)
            vd[q] = tf4[F4_vd][q];
        float mv = (float)((double)pairwise(vd.data(), n) / (double)n);     // (np.mean: over the count in float64)
        for (long q = 0; q < n; q++)
            vsc[idx[q]] = (double)mv > 1e-12 ? vd[q] / mv : 1.0f;
        double swv = (ch >= 0 && ch < 256) ? send[ch] : 1.0;
        if (!std::isnan(tsend) && ch >= 0 && !send_said.count(ch)) {
            if (tsend != swv) {
                // a one-shot's partials are gone a little past its noff (3 s
                // is more than any release); a held note's end is not known,
                // so the bus stays on
                long long rdm = 0;
                for (long q = 0; q < n; q++)
                    rdm = q == 0 ? (long long)tf4[F4_rdl][q] : std::max(rdm, (long long)tf4[F4_rdl][q]);
                odd_until = std::max(odd_until, one ? (long long)(n0 + dur + rdm + 3.0 * rate) : (1LL << 62));
            }
            swv = tsend;
        }
        for (long q = 0; q < n; q++)
            sw[idx[q]] = (float)swv;
        if (one) {
            long long m = 0;
            retiring.push_back(std::make_pair(idx, n0 + dur));
            (void)m;
            oneshot[key] = 1;
        }
        std::vector<long> &lv = live_of(key);
        lv.insert(lv.end(), idx.begin(), idx.end());
        own(key, idx);
        for (long s : idx)
            i4[I4_fx][s] = -1;                  // _moog_stamp: not a Moog note
        if (collect)
            collect->insert(collect->end(), idx.begin(), idx.end());
        last_slots = idx;
        return true;
    }

    // live.Slab.retime: a note not yet begun, begun d samples later -- its
    // onset, its end where it has one, its retiring time; its phases stay
    void retime(const std::vector<long> &idx, long long d)
    {
        std::set<long> in(idx.begin(), idx.end());
        for (long s : idx) {
            i8[0][s] += d;
            if (i8[1][s] != IDLE)
                i8[1][s] += d;
        }
        for (auto &r : retiring)
            for (long s : r.first)
                if (in.count(s)) {
                    r.second += d;
                    break;
                }
    }

    // stamp_cols with a cached template (its own columns, hrel, dur)
    bool stamp_t(const nv::live::Template &T, Key key, long long n0, double vel_scale, long long ch, double rate,
                 double scat = NAN)
    {
        const double *f8p[6];
        const float *f4p[27];
        const long long *i8p[2];
        const int32_t *i4p[6];
        for (int c = 0; c < 6; c++)
            f8p[c] = T.f8[c].data();
        for (int c = 0; c < 27; c++)
            f4p[c] = T.f4[c].data();
        for (int c = 0; c < 2; c++)
            i8p[c] = T.i8[c].data();
        for (int c = 0; c < 6; c++)
            i4p[c] = T.i4[c].data();
        return stamp(f8p, f4p, i8p, i4p, T.hrel.data(), T.P, key, n0, vel_scale, T.dur, T.oneshot, T.send, ch,
                     T.sof.empty() ? nullptr : T.sof.data(), T.rof.empty() ? nullptr : T.rof.data(),
                     std::isnan(scat) ? T.scatter_ms : scat, rate, nullptr, nullptr, nullptr,
                     T.gof.size() == (size_t)T.P ? T.gof.data() : nullptr);
    }

    // THE PAN TABLE (live.pan_table: CC10 -> left and right shadow alpha, half
    // the interaural delay) and the head's beta, from the caller
    double pan_tab[128][3];
    double pan_beta = 0.0;

    // Slab.repan: CC10 was -> cc on these slots; the head shadow's ratio at
    // each partial's frequency (float32), and with itd the ears' delays and
    // the phases that follow them
    void repan(const std::vector<long> &slots, int cc, int was, double rate, bool itd)
    {
        if (slots.empty() || cc == was)
            return;
        auto clamp = [](int v) { return v < 0 ? 0 : (v > 127 ? 127 : v); };
        repan_rows(slots, pan_tab[clamp(cc)], pan_tab[clamp(was)], rate, itd);
    }

    // ...from row t0 to row t1 (alpha left, alpha right, half itd): a CC's,
    // or a place of its own (live.pan_at's: a 3D type's)
    void repan_rows(const std::vector<long> &slots, const double *t1, const double *t0, double rate, bool itd)
    {
        if (slots.empty())
            return;
        double b2 = pan_beta * pan_beta;
        const std::vector<long> u = once(slots);
        for (long sidx : u) {
            double om = 2.0 * M_PI * (double)f4[2][sidx];
            auto shelf = [&](double al) { double x = al * om; return sqrt(x * x + b2); };
            float rl = (float)(shelf(t1[0]) / shelf(t0[0]));
            float rr = (float)(shelf(t1[1]) / shelf(t0[1]));
            aL0[sidx] *= rl; aR0[sidx] *= rr;
            f4[F4_aL][sidx] *= rl; f4[F4_aR][sidx] *= rr;
            tr_aL[sidx] *= rl; tr_aR[sidx] *= rr;   // (the tremolo's baseline with it)
            ls_aL[sidx] *= rl; ls_aR[sidx] *= rr;   // (...and the Leslie's)
            cv_aL[sidx] *= rl; cv_aR[sidx] *= rr;   // (...and the rockers')
            fl_aL[sidx] *= rl; fl_aR[sidx] *= rr;   // (...and the filter's)
        }
        if (itd) {
            float dl = (float)((t1[2] - t0[2]) * rate);
            for (long sidx : u) {
                f4[F4_delL][sidx] += dl;
                f4[F4_delR][sidx] -= dl;
                f8[F8_p0][sidx] -= f8[F8_om][sidx] * (double)dl;
                f8[F8_p0R][sidx] += f8[F8_om][sidx] * (double)dl;
            }
        }
    }

    // Slab.clav_tone: the rockers on these rows, from their unfiltered level
    // (taken the first time), never from what is there -- tonelib.
    // clav_tone_gain in float32, as numpy has it on the float32 columns
    void clav_tone(int setting, const std::vector<long> &slots)
    {
        static const float tone[5][3] = {{1200.0f, 2.0f, 0.0f}, {3000.0f, 2.0f, 0.0f}, {0.0f, 0.0f, 0.0f},
                                         {400.0f, 2.0f, 1.0f}, {900.0f, 2.0f, 1.0f}};
        if (slots.empty())
            return;
        for (long s : slots)
            if (!cv_on[s]) {
                cv_aL[s] = f4[F4_aL][s];
                cv_aR[s] = f4[F4_aR][s];
            }
        for (long s : slots)
            cv_on[s] = 1;
        const float *t = tone[((setting % 5) + 5) % 5];
        for (long s : slots) {
            float g = 1.0f;
            if (t[0] > 0.0f) {
                float y = f4[F4_nf][s] / t[0];
                float x = y * y;                // (numpy's ** 2.0: its square)
                g = t[2] != 0.0f ? x / (1.0f + x) : 1.0f / (1.0f + x);
            }
            f4[F4_aL][s] = cv_aL[s] * g;
            f4[F4_aR][s] = cv_aR[s] * g;
        }
    }

    // live.Slab.filter_arm: these partials under channel ch's moving filter,
    // their levels now what it filters every block from here on
    void filter_arm(const std::vector<long> &slots, int ch)
    {
        for (long s : slots) {
            fl_aL[s] = f4[F4_aL][s];
            fl_aR[s] = f4[F4_aR][s];
            fl_ch[s] = ch;
            fl_n += !fl_on[s];
            fl_on[s] = 1;
        }
    }

    // live.Slab.filter_swing: channel ch's |H| this block at each of its
    // partials' frequency (H(f), float32; HR(f) the right ear's), on the
    // level a swing left this block where one ran (the tremolo's, the
    // rotors'), else on its own -- a Moog row's for the render only
    template <class Fn, class FnR>
    void filter_swing(int ch, double rate, Fn H, FnR HR)
    {
        const double k = rate / (2.0 * M_PI);
        for (long s = 0; s < cap; s++) {
            if (!fl_on[s] || !busy[s] || fl_ch[s] != ch)
                continue;
            const double f = f8[F8_om][s] * k;
            const float hl = (float)H(f), hr = (float)HR(f);
            if (i4[I4_fx][s] >= 0) {
                flm_s.push_back(s);
                flm_l.push_back(hl);
                flm_r.push_back(hr);
                continue;
            }
            if (tr_on[s] || ls_on[s]) {
                f4[F4_aL][s] *= hl;
                f4[F4_aR][s] *= hr;
            } else {
                f4[F4_aL][s] = fl_aL[s] * hl;
                f4[F4_aR][s] = fl_aR[s] * hr;
            }
        }
    }
    template <class Fn>
    void filter_swing(int ch, double rate, Fn H) { filter_swing(ch, rate, H, H); }

    // live.Slab.moog_filter_apply / moog_filter_restore
    void moog_filter_apply()
    {
        flm_aL.resize(flm_s.size());
        flm_aR.resize(flm_s.size());
        for (size_t q = 0; q < flm_s.size(); q++) {
            const long s = flm_s[q];
            flm_aL[q] = f4[F4_aL][s];
            flm_aR[q] = f4[F4_aR][s];
            f4[F4_aL][s] *= flm_l[q];
            f4[F4_aR][s] *= flm_r[q];
        }
    }
    void moog_filter_restore()
    {
        for (size_t q = 0; q < flm_s.size(); q++) {
            f4[F4_aL][flm_s[q]] = flm_aL[q];
            f4[F4_aR][flm_s[q]] = flm_aR[q];
        }
        flm_s.clear(); flm_l.clear(); flm_r.clear(); flm_aL.clear(); flm_aR.clear();
    }

    // Slab.soft_strings: una corda, the `drop` highest of the instrument's `top` strings
    void soft_strings(const std::vector<long> &slots, int drop, int top)
    {
        if (slots.empty() || drop <= 0 || top <= 0)
            return;
        for (long sidx : slots)
            if (i4[3][sidx] > top - drop) {
                aL0[sidx] = 0.0f; aR0[sidx] = 0.0f;
                f4[F4_aL][sidx] = 0.0f; f4[F4_aR][sidx] = 0.0f;
                tr_aL[sidx] = 0.0f; tr_aR[sidx] = 0.0f;
                ls_aL[sidx] = 0.0f; ls_aR[sidx] = 0.0f;
                cv_aL[sidx] = 0.0f; cv_aR[sidx] = 0.0f;
            }
    }

    // Slab.channel_gain: the fader moved under these slots, by a ratio (float32)
    void channel_gain(const std::vector<long> &slots, double ratio)
    {
        if (slots.empty())
            return;
        float r = (float)ratio;
        if ((double)r == 1.0)
            return;
        for (long sidx : once(slots)) {
            aL0[sidx] *= r; aR0[sidx] *= r;
            f4[F4_aL][sidx] *= r; f4[F4_aR][sidx] *= r;
            tr_aL[sidx] *= r; tr_aR[sidx] *= r;     // (the tremolo's own baseline with it)
            ls_aL[sidx] *= r; ls_aR[sidx] *= r;     // (...and the Leslie's)
            cv_aL[sidx] *= r; cv_aR[sidx] *= r;     // (...and the rockers')
            fl_aL[sidx] *= r; fl_aR[sidx] *= r;     // (...and the filter's)
            mo_uL[sidx] *= r; mo_uR[sidx] *= r;     // (...and a Moog's panel weights' base)
        }
    }

    // channel_gain with a ratio a slot (a harmonium's Expression: each
    // partial its own), float32 each
    void channel_gain_each(const std::vector<long> &slots, const std::vector<float> &r)
    {
        for (size_t q = 0; q < slots.size(); q++) {
            long s = slots[q];
            aL0[s] *= r[q]; aR0[s] *= r[q];
            f4[F4_aL][s] *= r[q]; f4[F4_aR][s] *= r[q];
            tr_aL[s] *= r[q]; tr_aR[s] *= r[q];
            ls_aL[s] *= r[q]; ls_aR[s] *= r[q];
            cv_aL[s] *= r[q]; cv_aR[s] *= r[q];
            fl_aL[s] *= r[q]; fl_aR[s] *= r[q];
            mo_uL[s] *= r[q]; mo_uR[s] *= r[q];
        }
    }

    // live.Slab.ear_gain: a gain on each ear of these slots, every baseline
    // with it (as channel_gain's): a parallel type's branch at its pan
    void ear_gain(const std::vector<long> &slots, double gl, double gr)
    {
        if (slots.empty() || (gl == 1.0 && gr == 1.0))
            return;
        const float l = (float)gl, r = (float)gr;
        for (long s : once(slots)) {
            aL0[s] *= l; f4[F4_aL][s] *= l; tr_aL[s] *= l; ls_aL[s] *= l; cv_aL[s] *= l; fl_aL[s] *= l;
            mo_uL[s] *= l;
            aR0[s] *= r; f4[F4_aR][s] *= r; tr_aR[s] *= r; ls_aR[s] *= r; cv_aR[s] *= r; fl_aR[s] *= r;
            mo_uR[s] *= r;
        }
    }

    // live.Slab.tremolo_arm: these slots swung, each's baseline captured
    // once (a slot already armed keeps its own)
    void tremolo_arm(const std::vector<long> &slots, double depth, bool stereo)
    {
        std::vector<char> fresh(slots.size());
        for (size_t q = 0; q < slots.size(); q++)
            fresh[q] = !tr_on[slots[q]];
        for (size_t q = 0; q < slots.size(); q++)
            if (fresh[q]) {
                tr_aL[slots[q]] = f4[F4_aL][slots[q]];
                tr_aR[slots[q]] = f4[F4_aR][slots[q]];
            }
        for (long s : slots) {
            tr_on[s] = 1;
            tr_dep[s] = (float)depth;
            tr_st[s] = stereo ? -1.0f : 1.0f;
        }
    }

    // live.Slab.tremolo_swing: every armed slot's level where the modulator is
    // (wheel false: no wheel tremolo here, its swing 0); a Tremolo stop's
    // slots then at their own rate, from the same clock n
    void tremolo_swing(bool wheel, double phase, long long n, double rt)
    {
        float c0 = wheel ? (float)cos(phase) : 0.0f;
        for (long s = 0; s < cap; s++) {
            if (!tr_on[s] || !busy[s])
                continue;
            float c = c0 * tr_dep[s];
            f4[F4_aL][s] = tr_aL[s] * (1.0f + c);
            f4[F4_aR][s] = tr_aR[s] * (1.0f + c * tr_st[s]);
            if (hs_dep[s] > 0.0f) {
                float g = 1.0f + (float)cos(2.0 * M_PI * hs_hz[s] * (double)n / rt) * hs_dep[s];
                f4[F4_aL][s] *= g;
                f4[F4_aR][s] *= g;
            }
        }
    }

    // live.Slab.stop_tremolo_arm: a harmonium's Tremolo stop on these slots,
    // on tremolo_arm's baselines (a slot the wheel has not armed: depth 0)
    void stop_tremolo_arm(const std::vector<long> &slots, double depth, double hz)
    {
        std::vector<char> fresh(slots.size());
        for (size_t q = 0; q < slots.size(); q++)
            fresh[q] = !tr_on[slots[q]];
        for (size_t q = 0; q < slots.size(); q++)
            if (fresh[q]) {
                long s = slots[q];
                tr_aL[s] = f4[F4_aL][s];
                tr_aR[s] = f4[F4_aR][s];
                tr_dep[s] = 0.0f;
                tr_st[s] = 1.0f;
            }
        for (long s : slots) {
            tr_on[s] = 1;
            hs_dep[s] = (float)depth;
            hs_hz[s] = hz;
        }
    }

    // live.Slab.retune for a vibrato: each slot's depth to vbase + vd x vsc
    // and its rate to vrbase x vrs, the phase put back so neither the
    // carrier nor the vibrato's accrued phase steps (om unchanged)
    void retune_vib(const std::vector<long> &slots, long long n, double vd, double vrs)
    {
        double tn = (double)n / rate_;
        for (long q : slots) {
            double om0 = f8[F8_om][q];
            double vd0 = (double)f4[F4_vd][q];
            double vr0 = std::max((double)f4[F4_vr][q], 1e-6);
            double vp = (double)f4[21][q];
            double ton = (double)i8[0][q] / rate_;
            auto extra = [&](double om, double d, double r, double ph) {
                double w2 = 2.0 * M_PI * r;
                double swing = cos(w2 * ton + ph) - cos(w2 * tn + ph);
                return (om * rate_ / (2.0 * M_PI)) * d / r * swing;
            };
            double vr1 = std::max((double)vrbase[q] * vrs, 1e-6);
            double vp1 = vp + 2.0 * M_PI * (vr0 - vr1) * tn;
            double before = extra(om0, vd0, vr0, vp);
            double vd1 = (double)vbase[q] + vd * (double)vsc[q];
            double after = extra(om0, vd1, vr1, vp1);
            double step = (om0 - om0) * (double)n - (after - before);
            f8[F8_p0][q] += step;
            f8[F8_p0R][q] += step;
            f4[F4_vd][q] = (float)vd1;
            f4[F4_vr][q] = (float)vr1;
            f4[21][q] = (float)vp1;
        }
    }

    // live.Slab.leslie_params: each partial's rotor (the horn over the
    // crossover, flipped for a crossover copy), its lobe's floor and
    // sharpness, the lobe's mean (libm's cos and pow; numpy's mean)
    void leslie_params(long n, const double *nf, const char *flip, std::vector<char> &horn, std::vector<float> &fl,
                       std::vector<float> &sh, std::vector<double> &nrm) const
    {
        horn.resize(n); fl.resize(n); sh.resize(n); nrm.resize(n);
        nv_leslie_params(n, nf, flip, les.data(), horn.data(), fl.data(), sh.data(), nrm.data());
    }

    // live.Slab._doppler_to: the rotor rows' Doppler, from FAST_HZ's unit to
    // the rotors' rates (the horns', then the drum's)
    void doppler_to(const std::vector<long> &idx, long long n, double horn_rate, double drum_rate)
    {
        const double *L = les.data();
        for (int h = 1; h >= 0; h--) {
            std::vector<long> sub;
            for (long s : idx)
                if ((bool)ls_horn[s] == (bool)h)
                    sub.push_back(s);
            if (sub.empty())
                continue;
            double ref = h ? L[4] : L[4] * fabs(L[5]);
            double vrs = std::max(h ? horn_rate : drum_rate, 1e-4) / ref;
            retune_vib(sub, n, vrs - 1.0, vrs);
        }
    }

    // live.Slab.leslie_arm: these slots on the rotors -- their lobe, their
    // place off the cabinet (az), their baseline; their Doppler a unit at
    // FAST_HZ, then at the rotors' rates
    void leslie_arm(const std::vector<long> &slots, const float *az, const float *nf32, const char *flip, long long n,
                    double horn_rate, double drum_rate, const double *nf64 = nullptr, LobePre pre = LobePre())
    {
        if (slots.empty())
            return;
        const double *L = les.data();
        long m = (long)slots.size();
        std::vector<char> horn;
        std::vector<float> fl, sh;
        std::vector<double> nrm, nf(m);
        if (pre.horn) {                 // (worked out ahead: live's memo)
            horn.assign(pre.horn, pre.horn + m);
            fl.assign(pre.fl, pre.fl + m);
            sh.assign(pre.sh, pre.sh + m);
            nrm.assign(pre.nrm, pre.nrm + m);
        } else {
            for (long q = 0; q < m; q++)
                nf[q] = nf64 ? nf64[q] : (double)nf32[q];  // (a scanner's copy: its float64 pitch)
            leslie_params(m, nf.data(), flip, horn, fl, sh, nrm);
        }
        for (long q = 0; q < m; q++) {
            long s = slots[q];
            ls_on[s] = 1;
            ls_sep[s] = 0.0f;
            ls_ph[s] = az[q];
            ls_horn[s] = horn[q];
            ls_am[s] = fl[q];
            ls_sharp[s] = sh[q];
            ls_norm[s] = (float)nrm[q];
            ls_aL[s] = f4[F4_aL][s];
            ls_aR[s] = f4[F4_aR][s];
            double ref = horn[q] ? L[4] : L[4] * fabs(L[5]);
            double rad = horn[q] ? L[1] : L[2];
            vrbase[s] = (float)ref;
            vbase[s] = (float)(2.0 * M_PI * rad * ref / L[6]);
            vsc[s] = vbase[s];
        }
        doppler_to(slots, n, horn_rate, drum_rate);
    }

    // live.Slab.leslie_swing: every rotor slot's level where its rotor has got to
    void leslie_swing(double horn_angle, double drum_angle)
    {
        for (long s = 0; s < cap; s++) {
            if (!ls_on[s] || !busy[s])
                continue;
            double ang = ls_horn[s] ? horn_angle : drum_angle;
            float fl = ls_am[s];
            double c = 0.5 * (1.0 + cos(ang - (double)ls_ph[s]));
            double g = (double)fl + (double)(1.0f - fl) * pow(c, (double)(0.5f * ls_sharp[s]));
            g /= (double)ls_norm[s];
            double gl = g, gr = g;
            if (ls_sep[s] != 0.0f) {
                // THE RECORDED ROTARY's two mics (Separate): each ear its own,
                // half the spacing either side -- its own swing
                const double hs = (double)(0.5f * ls_sep[s]), d = ang - (double)ls_ph[s];
                const double ex = (double)(0.5f * ls_sharp[s]);
                const double cl = 0.5 * (1.0 + cos(d + hs)), cr = 0.5 * (1.0 + cos(d - hs));
                gl = ((double)fl + (double)(1.0f - fl) * pow(cl, ex)) / (double)ls_norm[s];
                gr = ((double)fl + (double)(1.0f - fl) * pow(cr, ex)) / (double)ls_norm[s];
            }
            f4[F4_aL][s] = (float)((double)ls_aL[s] * gl);
            f4[F4_aR][s] = (float)((double)ls_aR[s] * gr);
        }
    }

    // live.Slab.leslie_doppler: the rotor slots' Doppler to the rotors' rates
    void leslie_doppler(long long n, double horn_rate, double drum_rate)
    {
        std::vector<long> idx;
        for (long s = 0; s < cap; s++)
            if (ls_on[s] && busy[s])
                idx.push_back(s);
        if (!idx.empty())
            doppler_to(idx, n, horn_rate, drum_rate);
    }

    // live.Slab.stamp_amp: the valve's products (Hz, amplitude, phase at
    // `at`) placed from n0, each a copy of the sounding slot src but its
    // pitch, level (on src's own panning, from its baseline) and phase -- its
    // fader, room send and channel left as the slot had them. Empty if the
    // slab is full.
    std::vector<long> stamp_amp(const Key &key, long src, const double *f, const double *a, const double *p, long n,
                                long long n0, double rt, long long at)
    {
        std::vector<long> idx;
        if (n == 0 || (long)free.size() < n)
            return idx;
        for (long q = 0; q < n; q++) {
            idx.push_back(free.front());
            free.pop_front();
        }
        double ref = 0.5 * ((double)aL0[src] + (double)aR0[src]);
        for (long q = 0; q < n; q++) {
            long s = idx[q];
            busy[s] = 1;
            dk[s] = -1;
            tp[s] = -1;                         // (a fresh slot carries no taps)
            fx_chs[s] = -1;
            slot_ch[s] = slot_ch[src];          // its parent's part (not the slot's last note's)
            fl_n -= fl_on[s];
            fl_on[s] = 0;                       // (...and no filter)
            ls_on[s] = 0;
            cv_on[s] = 0;
            tr_on[s] = 0;
            hs_dep[s] = 0.0f;
            for (int c = 0; c < NF4; c++)
                f4[c][s] = f4[c][src];
            for (int c = 0; c < NF4N; c++)
                f4n[c][s] = f4n[c][src];
            for (int c = 0; c < NI4; c++)
                i4[c][s] = i4[c][src];
            i4[I4_fx][s] = -1;
            i4[5][s] = 0;                           // mk
            i4[I4_gr][s] = -1;
            i4[I4_br][s] = -1;
            i4[I4_cr][s] = 0;
            double om = 2.0 * M_PI * f[q] / rt;
            f8[F8_om][s] = om;
            f4[F4_nf][s] = (float)f[q];
            f8[F8_p0][s] = p[q] - om * (double)at;
            f8[F8_p0R][s] = f8[F8_p0][s] - om * ((double)f4[F4_delR][src] - (double)f4[F4_delL][src]);
            i8[0][s] = n0;
            i8[1][s] = IDLE;
            f4[F4_rdl][s] = 0.0f;
            double g = a[q] / std::max(ref, 1e-30);
            f4[F4_aL][s] = (float)((double)aL0[src] * g);
            f4[F4_aR][s] = (float)((double)aR0[src] * g);
            aL0[s] = f4[F4_aL][s];
            aR0[s] = f4[F4_aR][s];
            hrel[s] = 1.0f;
            vbase[s] = 0.0f;
            vrbase[s] = 0.0f;
            vsc[s] = 1.0f;
        }
        std::vector<long> &lv = live_of(key);
        lv.insert(lv.end(), idx.begin(), idx.end());
        own(key, idx);
        last_slots = idx;
        return idx;
    }

    bool any_leslie() const
    {
        for (long s = 0; s < cap; s++)
            if (ls_on[s])
                return true;
        return false;
    }

    bool any_tremolo() const
    {
        for (long s = 0; s < cap; s++)
            if (tr_on[s])
                return true;
        return false;
    }

    long live_find(const Key &key) const
    {
        for (size_t i = 0; i < live.size(); i++)
            if (live[i].first == key)
                return (long)i;
        return -1;
    }

    std::vector<long> &live_of(const Key &key)
    {
        long i = live_find(key);
        if (i < 0) {
            live.push_back(std::make_pair(key, std::vector<long>()));
            return live.back().second;
        }
        return live[i].second;
    }

    std::map<Key, std::pair<std::vector<long>, long long>> last_release;   // live.Slab.last_release

    void release(Key key, long long n)
    {
        long li = live_find(key);
        if (li < 0)
            return;
        std::vector<long> idx = live[li].second;
        live.erase(live.begin() + li);
        if (idx.empty()) {
            oneshot.erase(key);             // (a one-shot rung out under the key: disown)
            return;
        }
        auto o = oneshot.find(key);
        if (o != oneshot.end()) {
            oneshot.erase(o);
            return;
        }
        rel_log.push_back(std::make_tuple(key, n, idx));
        if (std::get<3>(key) == -1)
            last_release[key] = std::make_pair(idx, n);     // (a played note's: for a slur to cut, Live._slur_cut)
        for (long s : idx) {
            long long v = n + (long long)f4[F4_rdl][s];
            if (v < i8[1][s])
                i8[1][s] = v;
        }
        retiring.push_back(std::make_pair(idx, n));
        for (long s : idx)                  // the Moog rows' key-up (their pitch and shape rows')
            if (i4[I4_fx][s] >= 0 && (double)n < mp_toff[i4[I4_fx][s]])
                mp_toff[i4[I4_fx][s]] = (double)n;
    }

    // live.Slab.retime_off: a released note's end, d samples later
    void retime_off(const std::vector<long> &idx, long long d)
    {
        std::set<long> in(idx.begin(), idx.end());
        for (long s : idx)
            if (i8[1][s] != IDLE)
                i8[1][s] += d;
        for (auto &r : retiring)
            for (long s : r.first)
                if (in.count(s)) {
                    r.second += d;
                    break;
                }
    }

    // live.Slab._own: the slots idx are key's
    void own(const Key &key, const std::vector<long> &idx)
    {
        auto it = key_id.find(key);
        long long k;
        if (it == key_id.end()) {
            k = (long long)id_key.size();
            key_id[key] = k;
            id_key.push_back(key);
        } else {
            k = it->second;
        }
        for (long s : idx)
            owner[s] = k;
    }

    // live.Slab._disown: freed slots out of a key still held, its list's
    // order kept
    void disown(const std::vector<long> &idx)
    {
        std::vector<long long> ks;
        for (long s : idx)
            if (owner[s] >= 0)
                ks.push_back(owner[s]);
        std::set<long> gone(idx.begin(), idx.end());
        for (long s : idx)
            owner[s] = -1;
        std::sort(ks.begin(), ks.end());
        ks.erase(std::unique(ks.begin(), ks.end()), ks.end());
        for (long long k : ks) {
            long li = live_find(id_key[k]);
            if (li < 0 || live[li].second.empty())
                continue;
            std::vector<long> &lst = live[li].second;
            std::vector<long> kept;
            for (long s : lst)
                if (!gone.count(s))
                    kept.push_back(s);
            if (kept.size() != lst.size())
                lst.swap(kept);
        }
    }

    // Slab.reap: slots whose release has rung out, freed
    // THE MOOG's ROWS (live.Slab's): a note's filter row (FT, from a pool),
    // its part's knob row (KN, two ends a block), its mod section's pitch
    // (MP*) and shape (MK*, MPK) rows, its OSC 2 slots' FM source; and a
    // Moog slot's own baseline (mo_*): its level at unit weight (the
    // template is knob-neutral), and what the panel makes of it now
    static const int MOOG_FT_ROWS = 1024, MOOG_KN_ROWS = 256, MOOG_MP_CAP = 65, MOOG_MK_GRID = 5,
                     MOOG_MK_CAP = MOOG_MK_GRID * 3 * 64 * 2, FT_W = 30, KN_W = 9, SHAPE_W = 25, SHAPE_K = 64;
    std::vector<float> FT, KN, MPR, MPK;
    std::vector<int32_t> MPI, MKI;
    std::vector<double> MPC;
    std::deque<int> ft_free;
    std::vector<int> ft_cnt, ft_layer;
    std::vector<double> mp_a0, mp_toff, mp_acc, mp_P, ms_par;
    std::vector<char> mp_on, ms_on;
    std::vector<long long> ms_next, ms_nj;
    std::map<int, std::pair<std::vector<long>, std::vector<long>>> fm_map;
    std::vector<float> mo_uL, mo_uR, mo_w;
    std::vector<double> mo_ph, mo_r;
    std::map<std::tuple<long long, long long, int>, int> kn_of;     // (pid, ch, layer) -> its knob row
    // ...each row's knobs as its panel has them, and LFO 2 on them (live's
    // kn_base, kn_cf, kn_ag: the cutoff's factor, the level's gain)
    std::vector<double> kn_base;
    // ...and each NOTE's row of the kernel's Moog extensions (live's MX,
    // mx_on, mx_vel, mx_age: moog.mx_row)
    static const int MX_W = 6;
    std::vector<float> MX;
    std::vector<char> mx_on;
    std::vector<int> mx_vel;
    std::vector<double> mx_age, mx_l0a, mx_l0f;
    std::vector<char> kn_has;
    std::vector<double> kn_cf;
    std::vector<float> kn_ag;
    std::vector<long> l2_s;
    std::vector<float> l2_aL, l2_aR;

    void moog_alloc()
    {
        FT.assign(MOOG_FT_ROWS * FT_W, 0.0f);
        KN.assign(MOOG_KN_ROWS * 2 * KN_W, 0.0f);
        kn_base.assign(MOOG_KN_ROWS * KN_W, 0.0);
        MX.assign(MOOG_FT_ROWS * MX_W, 0.0f);
        mx_on.assign(MOOG_FT_ROWS, 0);
        mx_vel.assign(MOOG_FT_ROWS, 127);
        mx_age.assign(MOOG_FT_ROWS, 0.0);
        mx_l0a.assign(MOOG_FT_ROWS, 0.0);
        mx_l0f.assign(MOOG_FT_ROWS, 0.0);
        kn_has.assign(MOOG_KN_ROWS, 0);
        kn_cf.assign(MOOG_KN_ROWS, 1.0);
        kn_ag.assign(MOOG_KN_ROWS, 1.0f);
        MPI.assign(MOOG_FT_ROWS * 3, 0);
        MKI.assign(MOOG_FT_ROWS * 7, 0);
        MPC.assign(MOOG_FT_ROWS * MOOG_MP_CAP, 0.0);
        MPR.assign(MOOG_FT_ROWS * MOOG_MP_CAP, 1.0f);
        MPK.assign((size_t)MOOG_FT_ROWS * MOOG_MK_CAP, 0.0f);
        for (int r = 0; r < MOOG_FT_ROWS; r++) {
            MPI[3 * r + 2] = 1;
            MKI[7 * r + 2] = 1;
            MKI[7 * r + 4] = MKI[7 * r + 5] = MKI[7 * r + 6] = -1;
            ft_free.push_back(r);
        }
        ft_cnt.assign(MOOG_FT_ROWS, 0);
        ft_layer.assign(MOOG_FT_ROWS, 0);
        mp_a0.assign(MOOG_FT_ROWS, 0.0);
        mp_toff.assign(MOOG_FT_ROWS, INFINITY);
        mp_acc.assign(MOOG_FT_ROWS, 0.0);
        mp_P.assign(MOOG_FT_ROWS * 9, 0.0);
        ms_par.assign(MOOG_FT_ROWS * SHAPE_W, 0.0);
        mp_on.assign(MOOG_FT_ROWS, 0);
        ms_on.assign(MOOG_FT_ROWS, 0);
        ms_next.assign(MOOG_FT_ROWS, -1);
        ms_nj.assign(MOOG_FT_ROWS, 0);
        mo_uL.assign(cap, 0.0f); mo_uR.assign(cap, 0.0f); mo_w.assign(cap, 0.0f);
        mo_ph.assign(cap, 0.0); mo_r.assign(cap, 1.0);
    }

    // Slab.knob_row: the KN row of a (part, channel[, layer]), made on first
    // use from the knobs it is stamped with; the mapping starts again when full
    int knob_row(const std::tuple<long long, long long, int> &pk, const double *kn)
    {
        auto it = kn_of.find(pk);
        if (it != kn_of.end())
            return it->second;
        if ((int)kn_of.size() >= MOOG_KN_ROWS)
            kn_of.clear();
        int r = (int)kn_of.size();
        kn_of[pk] = r;
        kn_cf[r] = 1.0;
        kn_ag[r] = 1.0f;
        if (kn)
            set_knobs(r, kn, false);
        return r;
    }

    // Slab.set_knobs: the knobs' new values the END of the next block (ramp),
    // or both ends
    void set_knobs(int r, const double *kn, bool ramp)
    {
        double k0[KN_W];
        std::copy(kn, kn + KN_W, k0);       // (kn may be this row's own base)
        std::copy(k0, k0 + KN_W, kn_base.begin() + (size_t)r * KN_W);
        kn_has[r] = 1;
        for (int j = 0; j < KN_W; j++) {
            const float v = j == 0 && kn_cf[r] != 1.0 ? (float)(k0[0] * kn_cf[r]) : (float)k0[j];
            KN[(2 * r + 1) * KN_W + j] = v;
            if (!ramp)
                KN[2 * r * KN_W + j] = v;
        }
    }

    // live.Slab.lfo2_amp_apply: LFO 2's level on the Moog rows of the parts
    // it swings, for the render only (lfo2_amp_restore after it)
    void lfo2_amp_apply()
    {
        l2_s.clear(); l2_aL.clear(); l2_aR.clear();
        bool any = false;
        for (float g : kn_ag)
            any = any || g != 1.0f;
        if (!any)
            return;
        for (long q = 0; q < cap; q++) {
            if (!busy[q] || i4[I4_fx][q] < 0)
                continue;
            const long kr = (long)FT[(size_t)i4[I4_fx][q] * FT_W + 9];
            const float g = kn_ag[kr];
            if (g == 1.0f)
                continue;
            l2_s.push_back(q);
            l2_aL.push_back(f4[F4_aL][q]);
            l2_aR.push_back(f4[F4_aR][q]);
            f4[F4_aL][q] *= g;
            f4[F4_aR][q] *= g;
        }
    }
    void lfo2_amp_restore()
    {
        for (size_t i = 0; i < l2_s.size(); i++) {
            f4[F4_aL][l2_s[i]] = l2_aL[i];
            f4[F4_aR][l2_s[i]] = l2_aR[i];
        }
        l2_s.clear(); l2_aL.clear(); l2_aR.clear();
    }

    // Slab.unison_voice: ONE VOICE OF A UNISON on these freshly stamped Moog
    // slots -- its detune (the frequency, anchored at the onset), its phase
    // (k x its offset on an oscillator's harmonic k), its level and place (into
    // the panel weights' base too; its place on the direct sound alone), its
    // drift (the vibrato columns). uv: nv_moog_unison's 9
    void unison_voice(const std::vector<long> &idx, const double *uv)
    {
        const double ratio = uv[0], g = uv[1], uph = uv[2], gl = uv[3], gr = uv[4];
        if (idx.empty())
            return;
        if (ratio != 1.0)
            for (long s : idx) {
                double om0 = f8[F8_om][s], om1 = om0 * ratio;
                double non = (double)i8[0][s] + (double)f4[F4_nfr][s];
                f8[F8_p0][s] -= (om1 - om0) * (non + (double)f4[F4_delL][s]);
                f8[F8_p0R][s] -= (om1 - om0) * (non + (double)f4[F4_delR][s]);
                f8[F8_om][s] = om1;
            }
        for (long s : idx) {
            const int osc = i4[I4_mk][s] / 4096;
            const bool tone = osc == 1 || osc == 2 || osc == 3;
            if (uph != 0.0 && tone) {
                const double dph = 2.0 * M_PI * uph * (double)(i4[I4_mk][s] % 4096);
                f8[F8_p0][s] += dph;
                f8[F8_p0R][s] += dph;
            }
            const bool dr = f4[F4_rdl][s] == 0.0f;
            const float fl = (float)(dr ? g * gl : g), fr = (float)(dr ? g * gr : g);
            mo_uL[s] *= fl; aL0[s] *= fl; f4[F4_aL][s] *= fl; aLp[s] *= fl;
            mo_uR[s] *= fr; aR0[s] *= fr; f4[F4_aR][s] *= fr; aRp[s] *= fr;
            if (uv[5] != 0.0 && tone) {
                f4[F4_vd][s] = (float)uv[6];
                f4[F4_vr][s] = (float)uv[7];
                f4[21][s] = (float)uv[8];         // (vp)
            }
        }
    }
    // Slab.silence_slots: these slots' level zeroed, at their weights' base too
    void silence_slots(const std::vector<long> &idx)
    {
        for (long s : idx) {
            mo_uL[s] = aL0[s] = f4[F4_aL][s] = aLp[s] = 0.0f;
            mo_uR[s] = aR0[s] = f4[F4_aR][s] = aRp[s] = 0.0f;
        }
    }

    // Slab.mx_write: FT row r's note row of the kernel's Moog extensions
    // (moog.mx_row) from the panel pn and the note's velocity and age
    void mx_write(int r, const double *pn)
    {
        const double v[MX_W] = {mx_age[r], pn[NV_MK_F_LOOP] != 0.0 ? 1.0 : 0.0, pn[NV_MK_A_LOOP] != 0.0 ? 1.0 : 0.0,
                                pn[NV_MK_F_VEL] != 0.0 ? pow((double)mx_vel[r] / 127.0, 0.8) - 1.0 : 0.0,
                                mx_l0a[r], mx_l0f[r]};
        bool on = false;
        for (int j = 0; j < MX_W; j++) {
            MX[(size_t)r * MX_W + j] = (float)v[j];
            on = on || v[j] != 0.0;
        }
        mx_on[r] = on;
    }

    // moog.held_level: a held contour's level tt s in, as the kernel draws it
    static double held_level(double tt, double A, double D, double S, double l0, bool loop, double R)
    {
        const double T = 1.03, K = 3.5361166995615263, U = 0.055;
        A = std::max(A, 1e-6);
        D = std::max(D, 1e-6);
        R = std::max(R, 1e-6);
        if (tt < 0.0)
            return 0.0;
        if (loop) {
            const double Td = 3.37 * D * 0.25;
            const double h = held_level(A + Td, A, D, S, 0.0, false, 0.0);
            tt = fmod(tt, A + Td + R * 0.25 * log((h + U) / U));
            if (tt >= A + Td)
                return std::max(0.0, (h + U) * exp(-(tt - A - Td) / (R * 0.25)) - U);
            l0 = 0.0;
        }
        const double ta = A / K;
        double A1;
        if (l0 > 0.0) {
            A1 = l0 >= 1.0 ? 0.0 : ta * log((T - l0) / (T - 1.0));
            if (tt < A1)
                return T - (T - l0) * exp(-tt / ta);
        } else {
            A1 = A;
            if (tt < A)
                return T * (1.0 - exp(-tt / ta));
        }
        return std::max(0.0, S + (1.0 - S) * exp(-(tt - A1) / (D * 0.25)));
    }
    // Slab.contour_at: FT row r's note's amp (or filter) contour, held, t s in
    double contour_at(int r, double t, bool amp) const
    {
        const int kr = (int)FT[(size_t)r * FT_W + 9];
        const int o = amp ? 4 : 1;
        const double S = (double)KN[(size_t)(2 * kr + 1) * KN_W + (amp ? 4 : 3)];
        return held_level(t, (double)FT[(size_t)r * FT_W + o], (double)FT[(size_t)r * FT_W + o + 1], S,
                          amp ? mx_l0a[r] : mx_l0f[r], MX[(size_t)r * MX_W + (amp ? 2 : 1)] != 0.0f,
                          (double)FT[(size_t)r * FT_W + o + 2]);
    }

    // Slab.knobs_advance's knob rows: a block's end the next one's start
    // ...and the Moog partials' levels: each slot's now where the next
    // block's ramp starts (the slots alone: live's view, not the scratch rows)
    void levels_advance()
    {
        std::copy(f4[F4_aL].begin(), f4[F4_aL].begin() + cap, aLp.begin());
        std::copy(f4[F4_aR].begin(), f4[F4_aR].begin() + cap, aRp.begin());
    }

    void knobs_advance()
    {
        for (int r = 0; r < MOOG_KN_ROWS; r++)
            for (int j = 0; j < KN_W; j++)
                KN[2 * r * KN_W + j] = KN[(2 * r + 1) * KN_W + j];
    }

    // moog.ft_row: a note's fixed row -- its key's tracking, the contours'
    // times, the mode, its knob row, its key, the valve's flag, the flags,
    // and 1 -> 2 FM's index and modulator (fm_coeffs, against phi1: OSC 1's
    // fundamental's phase -- arg c_1 unless given -- in libm's arithmetic)
    static void ft_row(const MoogLayer *L, double f0, int krow, bool pre, int flags, bool has_phi1, double phi1,
                       float *out)
    {
        double row[30];
        row[0] = pow(f0 / L->kb_ref_hz, L->kb_track);
        for (int j = 1; j <= 8; j++)
            row[j] = L->ft[j];
        row[9] = (double)krow;
        row[10] = f0;
        row[11] = pre ? 1.0 : 0.0;
        double fi = L->fm_index;
        row[12] = (double)((flags & ~16) | (fi != 0.0 ? 16 : 0));
        row[13] = fi;
        double p1 = has_phi1 ? phi1 : atan2(L->c1[0][1], L->c1[0][0]);
        for (int j = 1; j <= 8; j++) {
            double re = 0.0, im = 0.0;
            if (fi != 0.0) {
                double a = 2.0 * hypot(L->c1[j - 1][0], L->c1[j - 1][1]) / (double)j;
                double x = atan2(L->c1[j - 1][1], L->c1[j - 1][0]) - (double)j * p1;
                re = a * cos(x);
                im = a * sin(x);
            }
            row[12 + 2 * j] = re;
            row[13 + 2 * j] = im;
        }
        for (int j = 0; j < 30; j++)
            out[j] = (float)row[j];
    }

    // moog.weights: what the panel makes of each knob-neutral partial
    // (mk = osc 4096 + k, nf its nominal Hz): its weight, phase and ratio
    static void weights(const MoogLayer *L, const std::vector<long> &idx, const int32_t *mk, const float *nf,
                        double fmax, double *w, double *ph, double *rt)
    {
        double r1 = L->t * L->foot1, r2 = L->t * L->foot2 * L->o2f;
        double sa = L->self_amp;
        for (size_t i = 0; i < idx.size(); i++) {
            long s = idx[i];
            int osc = mk[s] / 4096, k = mk[s] % 4096;
            double f = (double)nf[s];
            w[i] = 0.0;
            ph[i] = 0.0;
            rt[i] = 1.0;
            if (osc == 4) {                     // the noise bands: level only, in hertz
                int kk = std::min(std::max(k, 1), L->n_noise) - 1;
                w[i] = f > fmax ? 0.0 : L->noise_amp[kk] * L->lvl[3];
            } else if (osc == 5) {              // the ladder's own sine, at its cutoff
                double fs = L->self_cut * pow(f / L->kb_ref_hz, L->kb_track) * L->self_eg;
                rt[i] = fs / f;
                w[i] = fs > fmax ? 0.0 : sa;
            } else if (osc >= 1 && osc <= 3) {
                int n = osc == 3 ? 32 : 64;
                const double (*c)[2] = osc == 1 ? L->c1 : osc == 2 ? L->c2 : L->cs;
                double r = osc == 2 ? r2 : r1;
                bool moving = (L->shape_on >> osc) & 1;     // FT_SHAPE: the shape rows carry it
                int kk = std::min(std::max(k, 1), n) - 1;
                double cr = moving ? 1.0 : c[kk][0], ci = moving ? 0.0 : c[kk][1];
                rt[i] = r;
                w[i] = 2.0 * hypot(cr, ci) * L->lvl[osc - 1];
                ph[i] = atan2(ci, cr);
                if (!(osc == 2 && L->pitch_on) && f * r > fmax)
                    w[i] = 0.0;
            }
        }
    }

    // Slab.moog_retimbre: the panel on these Moog slots -- weight, phase
    // (within 90 degrees of the last: a crossing a sign), frequency -- each
    // against what was applied before, the swings' baselines moved with it.
    // At a stamp (no retune) the frequency is the onset's own anchor,
    // fraction and all; under a sounding note it moves through retune (each
    // slot's ratio), which keeps the phase continuous
    using Retune = std::function<void(const std::vector<long> &, const std::vector<double> &)>;
    void moog_retimbre(const std::vector<long> &idx, const MoogLayer *L, double rate, const Retune *retune = nullptr,
                       long long lock_n = -1)
    {
        size_t n = idx.size();
        if (!n)
            return;
        std::vector<double> w(n), ph(n), rt(n);
        double fmax = 0.5 * rate < L->fmax_hz ? 0.5 * rate : L->fmax_hz;    // min(FMAX_HZ, 0.5 rate)
        weights(L, idx, i4[I4_mk].data(), f4[F4_nf].data(), fmax, w.data(), ph.data(), rt.data());
        // an amplifier after the ladder hears it at its sustain (FT slot 11)
        for (size_t i = 0; i < n; i++) {
            long s = idx[i];
            int r = i4[I4_fx][s];
            if (r >= 0 && FT[r * FT_W + 11] > 0.5f && i4[I4_mk][s] / 4096 != 5) {
                double f0 = (double)FT[r * FT_W + 10], f = (double)f4[F4_nf][s] * rt[i];
                double fcs = L->self_cut * pow(f0 / L->kb_ref_hz, L->kb_track) * L->self_eg;
                w[i] *= nv_moog_ladder_gain(L, f, fcs > 1.0 ? fcs : 1.0, L->kn[1], (int)L->ft[7],
                                            L->ft[8] != 0.0);
            }
        }
        bool any = false;
        for (size_t i = 0; i < n; i++)
            any = any || fabs(rt[i] / mo_r[idx[i]] - 1.0) > 1e-12;
        if (any && retune) {
            std::vector<double> sc(n);
            for (size_t i = 0; i < n; i++)
                sc[i] = rt[i] / mo_r[idx[i]];
            (*retune)(idx, sc);
        } else if (any)
            for (size_t i = 0; i < n; i++) {
                long s = idx[i];
                double sc = rt[i] / mo_r[s];
                double om0 = f8[F8_om][s], om1 = om0 * sc;
                double non = (double)i8[0][s] + (double)f4[F4_nfr][s];
                f8[F8_p0][s] -= (om1 - om0) * (non + (double)f4[F4_delL][s]);
                f8[F8_p0R][s] -= (om1 - om0) * (non + (double)f4[F4_delR][s]);
                f8[F8_om][s] = om1;
            }
        for (size_t i = 0; i < n; i++)
            mo_r[idx[i]] = rt[i];
        for (size_t i = 0; i < n; i++) {        // a harmonic through zero changes sign, not phase
            long s = idx[i];
            double x = ph[i] - mo_ph[s];
            double d = atan2(sin(x), cos(x));
            if (fabs(d) > 0.5 * M_PI) {
                ph[i] = ph[i] - M_PI * (d > 0.0 ? 1.0 : d < 0.0 ? -1.0 : 0.0);
                w[i] = -w[i];
            }
            double dph = ph[i] - mo_ph[s];
            f8[F8_p0][s] += dph;
            f8[F8_p0R][s] += dph;
            mo_ph[s] = ph[i];
        }
        // aftertouch rides on aL0: the note's current factor over it (np.median)
        std::vector<float> rat;
        for (long s : idx)
            if (aL0[s] > 0.0f)
                rat.push_back(f4[F4_aL][s] / aL0[s]);
        float f = 1.0f;
        if (!rat.empty()) {
            std::sort(rat.begin(), rat.end());
            size_t m = rat.size();
            f = m % 2 ? rat[m / 2] : (float)((double)(float)(rat[m / 2 - 1] + rat[m / 2]) / 2.0);
        }
        // ...and the swings' own baselines move with it (by the ratio; a row
        // that was silent set where its swing is armed)
        for (int side = 0; side < 2; side++) {
            std::vector<float> &uo = side ? mo_uR : mo_uL;
            std::vector<float> &a0 = side ? aR0 : aL0;
            std::vector<float> *bases[4] = {side ? &ls_aR : &ls_aL, side ? &tr_aR : &tr_aL, side ? &cv_aR : &cv_aL,
                                            side ? &fl_aR : &fl_aL};
            const std::vector<char> *arm[4] = {&ls_on, &tr_on, &cv_on, &fl_on};
            for (size_t i = 0; i < n; i++) {
                long s = idx[i];
                double nw = (double)uo[s] * w[i];
                float old = a0[s];
                bool z = old == 0.0f;
                float q = (float)(z ? 1.0 : nw / (double)old);
                for (int b = 0; b < 4; b++) {
                    (*bases[b])[s] *= q;
                    if (z && (*arm[b])[s])
                        (*bases[b])[s] = (float)(nw * (double)f);
                }
            }
        }
        for (size_t i = 0; i < n; i++) {
            long s = idx[i];
            aL0[s] = (float)((double)mo_uL[s] * w[i]);
            aR0[s] = (float)((double)mo_uR[s] * w[i]);
            f4[F4_aL][s] = aL0[s] * f;
            f4[F4_aR][s] = aR0[s] * f;
            mo_w[s] = (float)w[i];
        }
        if (lock_n >= 0 && L->pn[NV_MK_SYNC] != 0.0)
            sync_lock(idx, lock_n);
    }

    // Slab._moog_sync_lock: SYNC under a held note -- each OSC 2 harmonic k
    // put at k times its own OSC 1 fundamental's phase plus the synced
    // wave's, per ear and per room image (the same note row and delays)
    void sync_lock(const std::vector<long> &idx, long long n)
    {
        std::vector<long> f1;
        for (long s : idx)
            if (i4[I4_mk][s] == 4096 + 1)
                f1.push_back(s);
        for (long i : idx) {
            if (i4[I4_mk][i] / 4096 != 2)
                continue;
            long j = -1;
            for (long q : f1)
                if (i4[I4_fx][q] == i4[I4_fx][i] && f4[F4_delL][q] == f4[F4_delL][i]
                    && f4[F4_delR][q] == f4[F4_delR][i])
                    j = q;                  // (the last, as a dict built in order keeps)
            if (j < 0)
                continue;
            const int k = i4[I4_mk][i] % 4096;
            for (int col = 0; col < 2; col++) {
                std::vector<double> &p0 = col ? f8[F8_p0R] : f8[F8_p0];
                double th1 = p0[j] + f8[F8_om][j] * (double)n - mo_ph[j];
                double want = k * th1 + mo_ph[i];
                double have = p0[i] + f8[F8_om][i] * (double)n;
                double d = want - have;
                p0[i] += d - 2.0 * M_PI * floor(d / (2.0 * M_PI) + 0.5);
            }
        }
    }

    // the FT rows these slots read, each once (np.unique's: ascending)
    std::vector<int> rows_of(const std::vector<long> &idx) const
    {
        std::set<int> u;
        for (long s : idx)
            if (i4[I4_fx][s] >= 0)
                u.insert(i4[I4_fx][s]);
        return std::vector<int>(u.begin(), u.end());
    }

    // Slab.moog_rows: the filter rows these slots read rebuilt from a changed
    // panel (the contours' times, the mode, key tracking); the release span
    // follows
    void moog_rows(const std::vector<long> &idx, const MoogLayer *L, double rate)
    {
        for (int r : rows_of(idx)) {
            float *row = &FT[r * FT_W];
            float nrow[30];
            ft_row(L, (double)row[10], (int)row[9], row[11] > 0.5f, (int)row[12], false, 0.0, nrow);
            for (int j = 0; j < 30; j++)
                row[j] = nrow[j];
            mx_write(r, L->pn);
        }
        double span = L->rel_span * rate;
        float re = (float)(span > 1.0 ? span : 1.0);
        for (long s : idx)
            f4[F4_re][s] = re;
    }

    // Slab.moog_pitch: what moves OSC 2's pitch changed -- the rows carry on
    // from where they are with the new law; turned off, a note keeps the
    // phase it gathered (its amounts to zero)
    void moog_pitch(const std::vector<long> &idx, const MoogLayer *L)
    {
        for (int r : rows_of(idx)) {
            if (L->pitch_on) {
                if (!mp_on[r]) {
                    mp_on[r] = 1;
                    mp_acc[r] = 0.0;
                    FT[r * FT_W + 12] = (float)((int)FT[r * FT_W + 12] | 1);
                }
                for (int j = 0; j < 9; j++)
                    mp_P[r * 9 + j] = L->pitch_p[j];
            } else if (mp_on[r]) {
                mp_P[r * 9 + 0] = 0.0;
                mp_P[r * 9 + 5] = 0.0;
            }
        }
    }

    // Slab.moog_shape: which shapes move, or how, changed -- the rows' flags
    // and parameters follow; the slots whose representation switched (a
    // moving shape's carry 2 x level, a still one's the coefficient)
    std::vector<long> moog_shape(const std::vector<long> &idx, const MoogLayer *L)
    {
        int sf = L->shape_on;
        std::vector<long> sw;
        for (int r : rows_of(idx)) {
            int old = (int)FT[r * FT_W + 12];
            if ((old & 14) != sf)
                for (long s : idx) {
                    if (i4[I4_fx][s] != r)
                        continue;
                    int osc = i4[I4_mk][s] / 4096;
                    int bit = osc >= 1 && osc <= 3 ? 1 << osc : 0;      // FT_SHAPE
                    if (((bit & old) != 0) != ((bit & sf) != 0))
                        sw.push_back(s);
                }
            FT[r * FT_W + 12] = (float)((old & 1) | sf);
            ms_on[r] = sf != 0;
            ms_next[r] = -1;                // new knobs: no grid point carried over
            if (sf)
                for (int j = 0; j < SHAPE_W; j++)
                    ms_par[r * SHAPE_W + j] = L->shape_par[j];
        }
        return sw;
    }

    // Slab.moog_fm: 1 -> 2 FM for the note on row r -- its row's modulator
    // against the phase OSC 1's fundamental carries, and which OSC 1 slot
    // each OSC 2 slot reads its angle from (same note, same room image)
    void moog_fm(int r, const std::vector<long> &idx, const MoogLayer *L)
    {
        if (L->fm_index == 0.0) {
            fm_map.erase(r);
            FT[r * FT_W + 12] = (float)((int)FT[r * FT_W + 12] & ~16);
            return;
        }
        std::vector<long> f1, o2;
        for (long s : idx) {
            if (i4[I4_fx][s] != r)
                continue;
            if (i4[I4_mk][s] == 1 * 4096 + 1)
                f1.push_back(s);
            if (i4[I4_mk][s] / 4096 == 2)
                o2.push_back(s);
        }
        if (f1.empty() || o2.empty())
            return;
        float *row = &FT[r * FT_W];
        float nrow[30];
        ft_row(L, (double)row[10], (int)row[9], row[11] > 0.5f, (int)row[12], true, mo_ph[f1[0]], nrow);
        for (int j = 0; j < 30; j++)
            row[j] = nrow[j];
        auto key = [&](long s) {            // (round(delL, 2), round(delR, 2))
            return std::make_pair((long long)nearbyint((double)f4[F4_delL][s] * 100.0),
                                  (long long)nearbyint((double)f4[F4_delR][s] * 100.0));
        };
        std::map<std::pair<long long, long long>, long> fund;
        for (long s : f1)
            fund[key(s)] = s;               // (a later one of the same key wins: a dict's)
        std::vector<long> dst, src;
        for (long s : o2) {
            auto it = fund.find(key(s));
            if (it != fund.end()) {
                dst.push_back(s);
                src.push_back(it->second);
            }
        }
        fm_map[r] = std::make_pair(dst, src);
    }

    // Slab._moog_stamp: a Moog note -- its filter row, its part's knob row,
    // the panel applied to its knob-neutral partials (T.i4's fx: its Moog
    // rows); a full row pool leaves it unfiltered
    void moog_stamp(const nv::live::Template &T, long long pid, long long ch, int layer, const MoogLayer *L,
                    double rate)
    {
        const std::vector<long> &idx = last_slots;
        if (!T.moog || !L || (long)T.i4[I4_fx].size() != (long)idx.size())
            return;
        std::vector<long> mine;
        for (size_t q = 0; q < idx.size(); q++)
            if (T.i4[I4_fx][q] >= 0)
                mine.push_back(idx[q]);
        if (mine.empty() || ft_free.empty())
            return;
        int r = ft_free.front();
        ft_free.pop_front();
        ft_layer[r] = layer;
        int krow = knob_row(std::make_tuple(pid, ch, layer), L->kn);
        int sf = L->shape_on;
        ft_row(L, T.ft_f0, krow, T.ft_pre, (L->pitch_on ? 1 : 0) | sf, false, 0.0, &FT[r * FT_W]);
        ms_on[r] = sf != 0;
        ms_next[r] = -1;
        if (sf)
            for (int j = 0; j < SHAPE_W; j++)
                ms_par[r * SHAPE_W + j] = L->shape_par[j];
        mx_vel[r] = 127;
        mx_age[r] = 0.0;
        mx_l0a[r] = mx_l0f[r] = 0.0;
        mx_write(r, L->pn);
        for (long s : mine)
            i4[I4_fx][s] = r;
        ft_cnt[r] = (int)mine.size();
        // the note's key, for its pitch rows: its direct sound's onset
        long long a0 = 0;
        bool got = false;
        for (long s : idx)
            if (f4[F4_rdl][s] == 0.0f && (!got || i8[0][s] < a0)) {
                a0 = i8[0][s];
                got = true;
            }
        if (!got)
            for (long s : idx)
                if (!got || i8[0][s] < a0) {
                    a0 = i8[0][s];
                    got = true;
                }
        mp_a0[r] = (double)a0;
        mp_toff[r] = INFINITY;
        mp_acc[r] = 0.0;
        mp_on[r] = L->pitch_on != 0;
        if (L->pitch_on)
            for (int j = 0; j < 9; j++)
                mp_P[r * 9 + j] = L->pitch_p[j];
        std::vector<long> mo;
        for (long s : idx)
            if (i4[I4_mk][s] > 0)
                mo.push_back(s);
        if (!mo.empty()) {
            for (long s : mo) {
                mo_uL[s] = aL0[s];
                mo_uR[s] = aR0[s];
                mo_w[s] = 1.0f;
                mo_ph[s] = 0.0;
                mo_r[s] = 1.0;
            }
            moog_retimbre(mo, L, rate);
        }
        moog_fm(r, idx, L);
        double span = L->rel_span * rate;
        float re = (float)(span > 1.0 ? span : 1.0);
        for (long s : idx) {
            f4[F4_re][s] = re;
            aLp[s] = f4[F4_aL][s];
            aRp[s] = f4[F4_aR][s];
        }
    }

    // Slab.moog_fm_block: OSC 1's frequency and phase anchors onto the OSC 2
    // slots it modulates, this block
    void moog_fm_block()
    {
        for (auto &kv : fm_map)
            for (size_t q = 0; q < kv.second.first.size(); q++) {
                long d = kv.second.first[q], s = kv.second.second[q];
                f8[F8_fmw][d] = f8[F8_om][s];
                f8[F8_fmp][d] = f8[F8_p0][s];
                f8[F8_fmpR][d] = f8[F8_p0R][s];
            }
    }

    // Slab.moog_pitch_block: this block's pitch rows for every note that has
    // them -- the grid points from n0 on, one cell integral apart
    // (synthkernel.c moog_pitch_cells)
    void moog_pitch_block(long long n0, long long frames, double rate, void *pcells_)
    {
        auto pcells = (void (*)(int, const double *, const double *, const double *, const double *, double, int,
                                double *, double *))pcells_;
        std::vector<int> on;
        for (int r = 0; r < MOOG_FT_ROWS; r++)
            if (mp_on[r])
                on.push_back(r);
        if (on.empty() || !pcells)
            return;
        long long mg = (frames % 128 == 0 && frames / 128 <= 64) ? 128 : frames;
        long long j0 = n0 / mg, nj = frames / mg + 1;
        int m_ = (int)on.size();
        std::vector<double> C(m_), g(m_), a0(m_), toff(m_), P(9 * m_), dc(m_), rr(m_);
        for (int q = 0; q < m_; q++) {
            C[q] = mp_acc[on[q]];
            a0[q] = mp_a0[on[q]];
            toff[q] = mp_toff[on[q]];
            for (int j = 0; j < 9; j++)
                P[9 * q + j] = mp_P[on[q] * 9 + j];
        }
        for (long long m = 0; m < nj; m++) {
            double gg = (double)((j0 + m) * mg);
            for (int q = 0; q < m_; q++) {
                MPC[on[q] * MOOG_MP_CAP + m] = C[q];
                g[q] = gg;
            }
            pcells(m_, g.data(), a0.data(), toff.data(), P.data(), rate, (int)mg, dc.data(), rr.data());
            for (int q = 0; q < m_; q++) {
                if (m < nj - 1)
                    C[q] = C[q] + dc[q];
                MPR[on[q] * MOOG_MP_CAP + m] = (float)rr[q];
            }
        }
        for (int q = 0; q < m_; q++) {
            int r = on[q];
            MPI[r * 3] = r * MOOG_MP_CAP;
            MPI[r * 3 + 1] = (int32_t)j0;
            MPI[r * 3 + 2] = (int32_t)nj;
            mp_acc[r] = C[q];               // this block's end the next one's start
        }
    }

    // Slab.moog_shape_block: this block's shape rows for every note whose
    // shape moves (synthkernel.c moog_shape_rows); a block's first grid
    // point the last one's last, for a note whose knobs have not moved
    void moog_shape_block(long long n0, long long frames, double rate, void *srows_)
    {
        auto srows = (void (*)(int, const double *, const double *, const double *, const long *, const int *, int,
                               double, int, const long *, const int *, const int *, float *))srows_;
        std::vector<int> on;
        for (int r = 0; r < MOOG_FT_ROWS; r++)
            if (ms_on[r])
                on.push_back(r);
        if (on.empty() || !srows)
            return;
        long long mg = (frames % 128 == 0 && frames / 128 <= 64) ? 128 : frames;
        int nj = (int)std::min(frames / mg + 1, (long long)MOOG_MK_GRID);
        long long j0 = n0 / mg;
        int st = 3 * SHAPE_K * 2;
        static const int FT_SHAPE[4] = {0, 2, 4, 8};
        std::vector<int> fresh, cont;
        for (int r : on)
            (ms_next[r] != n0 ? fresh : cont).push_back(r);
        auto offs_of = [&](int r, int *o) {
            int fl = (int)ms_par[r * SHAPE_W + 0];
            for (int i = 0; i < 3; i++)
                o[i] = (fl & FT_SHAPE[i + 1]) ? i * SHAPE_K * 2 : -1;
        };
        auto run = [&](const std::vector<int> &rs, long long jj0, int nnj, long add) {
            int m = (int)rs.size();
            std::vector<double> par(m * SHAPE_W), a0(m), toff(m);
            std::vector<long> j0s(m), base(m);
            std::vector<int> njs(m), stride(m), offs(3 * m);
            for (int q = 0; q < m; q++) {
                int r = rs[q];
                for (int j = 0; j < SHAPE_W; j++)
                    par[q * SHAPE_W + j] = ms_par[r * SHAPE_W + j];
                a0[q] = mp_a0[r];
                toff[q] = mp_toff[r];
                j0s[q] = (long)jj0;
                njs[q] = nnj;
                base[q] = (long)r * MOOG_MK_CAP + add;
                stride[q] = st;
                offs_of(r, &offs[3 * q]);
            }
            srows(m, par.data(), a0.data(), toff.data(), j0s.data(), njs.data(), (int)mg, rate, SHAPE_K, base.data(),
                  stride.data(), offs.data(), MPK.data());
        };
        for (int r : cont) {
            long last = (long)r * MOOG_MK_CAP + (ms_nj[r] - 1) * st, first = (long)r * MOOG_MK_CAP;
            for (int j = 0; j < st; j++)
                MPK[first + j] = MPK[last + j];
        }
        if (!cont.empty())
            run(cont, j0 + 1, nj - 1, st);
        if (!fresh.empty())
            run(fresh, j0, nj, 0);
        for (int r : on) {
            ms_next[r] = n0 + frames;
            ms_nj[r] = nj;
            int o[3];
            offs_of(r, o);
            MKI[r * 7] = r * MOOG_MK_CAP;
            MKI[r * 7 + 1] = (int32_t)j0;
            MKI[r * 7 + 2] = nj;
            MKI[r * 7 + 3] = st;
            for (int i = 0; i < 3; i++)
                MKI[r * 7 + 4 + i] = o[i];
        }
    }

    void reap(long long n, long long blk)
    {
        std::vector<std::pair<std::vector<long>, long long>> keep;
        for (auto &r : retiring) {
            float mx = 0.0f;
            bool first = true;
            for (long s : r.first) {
                float d = f4[F4_delL][s] > f4[F4_delR][s] ? f4[F4_delL][s] : f4[F4_delR][s];
                float v = (f4[F4_re][s] + f4[F4_rdl][s]) + d;
                if (first || v > mx) {
                    mx = v;
                    first = false;
                }
            }
            double tail = (double)r.second + (double)mx + (double)blk + 1.0;
            if (tap_on) {                       // its taps' copies ring that much on
                long long tx = 0;
                for (size_t q = 0; q < r.first.size(); q++)
                    tx = q == 0 ? tpx[r.first[q]] : std::max(tx, tpx[r.first[q]]);
                tail += (double)tx;
            }
            if ((double)n > tail) {
                std::vector<long> freed;
                for (long s : r.first) {
                    i8[0][s] = IDLE;
                    tp[s] = -1;
                    if (busy[s]) {
                        busy[s] = 0;
                        free.push_back(s);
                        freed.push_back(s);
                    }
                }
                if (!freed.empty())
                    disown(freed);
                // the Moog rows these slots held, returned with the last of them
                std::map<int, int> cnt;
                for (long s : freed)
                    if (i4[I4_fx][s] >= 0)
                        cnt[i4[I4_fx][s]]++;
                if (!cnt.empty()) {
                    for (auto &c : cnt) {
                        int q = c.first;
                        ft_cnt[q] -= c.second;
                        if (ft_cnt[q] <= 0) {
                            ft_cnt[q] = 0;
                            mp_on[q] = 0;
                            ms_on[q] = 0;
                            fm_map.erase(q);
                            ft_free.push_back(q);
                        }
                    }
                    for (long s : freed) {
                        i4[I4_fx][s] = -1;
                        f8[F8_fmw][s] = 0.0;
                    }
                }
            } else {
                keep.push_back(r);
            }
        }
        retiring.swap(keep);
    }
};

// ---------------------------------------------------------------------------
// A PART, LIVE: live.Live's events for one part on its slab -- what
// _one_core, _note_on and _note_off do, block by block as live's callback
// runs them: the block's events at its start, then the sweep (a key neither
// down nor held released), then the reap. Not here yet: CC71-78 but on an
// organ part (the harmonium's attack and release). MONO MODE (CC126/127),
// THE RPNs (bend range, fine and coarse tuning, the mod range), CC120,
// CC121, CC123, the channel-mode messages and SOSTENUTO as live's. THE PITCH
// WHEEL (live._repitch: GM's 2-semitone range) and THE MOD WHEEL by the
// voice's role (live.wheel_roles: drive, swell, crescendo, tremolo, the
// rockers, a honky-tonk's detune, else vibrato).
// PRESSURE (channel aftertouch, live's Slab.press) as a level: a piano's
// effort_tilt is 0, so its partials are not tilted, only lifted by press_db
// at full pressure. THE DAMPERS IN BETWEEN (live._damp_block), when given damper.py's
// numbers (nv_part_damper): a pedalled key in the band is taken down by its
// level through a damper track the kernel reads (synth_voice_damp). THE REGISTER (live's _reg_*), when given
// one (nv_part_register): its worker's jobs answered in step -- each as it is
// sent, as a worker that kept up would, so a reply is placed at the first
// pump after its job (live's own worker answers a few blocks later, as it
// can: the same rows, later).

// THE LATE ROOM (live.RoomTail): the diffuse tail and the room's modes, each
// stereo, fed the send -- through convolver.c (live's Convolver, its library
// loaded by the caller: conv_new, conv_process, conv_free). Each impulse
// response split at one block: its first block's taps on the audio thread,
// the rest on a thread of its own a block behind -- exact, since the rest
// starts a block late by definition.
typedef void *(*conv_new_fn)(const float *ir, int len, int B, int M);
typedef void (*conv_proc_fn)(void *c, const float *x, float *out);
typedef void (*conv_free_fn)(void *c);

struct Room {
    static const int SEGMENT_BLOCKS = 16;           // live.Convolver.SEGMENT_BLOCKS
    conv_new_fn cnew;
    conv_proc_fn cproc;
    conv_free_fn cfree;
    int B, nconv = 0;
    void *head[4] = {}, *body[4] = {};
    std::vector<float> inp[4], res[4], out[4], tmp;
    std::thread worker;
    std::mutex mu;
    std::condition_variable cv;
    bool go = false, done = true, stop = false;

    // ir: n samples of 2 channels interleaved; mir the modes' (m 0: none)
    Room(void *cn, void *cp, void *cf, const float *ir, long n, const float *mir, long m, int frames)
        : cnew((conv_new_fn)cn), cproc((conv_proc_fn)cp), cfree((conv_free_fn)cf), B(frames)
    {
        std::vector<std::vector<float>> irs;
        for (int c = 0; c < 2; c++) {
            irs.emplace_back(n);
            for (long k = 0; k < n; k++)
                irs.back()[k] = ir[2 * k + c];
        }
        for (int c = 0; m > 0 && c < 2; c++) {
            irs.emplace_back(m);
            for (long k = 0; k < m; k++)
                irs.back()[k] = mir[2 * k + c];
        }
        nconv = (int)irs.size();
        for (int i = 0; i < nconv; i++) {
            const std::vector<float> &h = irs[i];
            long hb = std::min((long)h.size(), (long)B);
            head[i] = cnew(h.data(), (int)hb, B, SEGMENT_BLOCKS);
            body[i] = (long)h.size() > B ? cnew(h.data() + B, (int)(h.size() - B), B, SEGMENT_BLOCKS) : nullptr;
            inp[i].assign(B, 0.0f);
            res[i].assign(B, 0.0f);
            out[i].assign(B, 0.0f);
        }
        tmp.assign(B, 0.0f);
        worker = std::thread([this] { work(); });
    }

    ~Room()
    {
        {
            std::unique_lock<std::mutex> lk(mu);
            cv.wait(lk, [&] { return done; });
            stop = true;
            go = true;
        }
        cv.notify_all();
        worker.join();
        for (int i = 0; i < nconv; i++) {
            if (head[i]) cfree(head[i]);
            if (body[i]) cfree(body[i]);
        }
    }

    void work()
    {
        std::unique_lock<std::mutex> lk(mu);
        while (true) {
            cv.wait(lk, [&] { return go; });
            go = false;
            if (stop)
                return;
            lk.unlock();
            for (int i = 0; i < nconv; i++)
                if (body[i])
                    cproc(body[i], inp[i].data(), res[i].data());
            lk.lock();
            done = true;
            cv.notify_all();
        }
    }

    // RoomTail.process: the room's (wl, wr) for a block of the send
    void process(const float *sL, const float *sR, float *wl, float *wr)
    {
        {
            std::unique_lock<std::mutex> lk(mu);
            cv.wait(lk, [&] { return done; });     // last block's body: ready, normally long since
            done = false;
        }
        const float *xs[4] = {sL, sR, sL, sR};
        for (int i = 0; i < nconv; i++) {
            cproc(head[i], xs[i], tmp.data());
            for (int k = 0; k < B; k++)
                out[i][k] = tmp[k] + res[i][k];
        }
        for (int i = 0; i < nconv; i++)
            memcpy(inp[i].data(), xs[i], sizeof(float) * B);
        {
            std::lock_guard<std::mutex> lk(mu);
            go = true;
        }
        cv.notify_all();
        for (int k = 0; k < B; k++) {
            wl[k] = nconv == 4 ? out[0][k] + out[2][k] : out[0][k];
            wr[k] = nconv == 4 ? out[1][k] + out[3][k] : out[1][k];
        }
    }
};

struct Ev {
    int type;               // 0 note-on, 1 note-off, 2 control change, 3 channel aftertouch (a),
                            // 4 the pitch wheel (a, -8192..8191), 6 an exclusive (a: its bytes' place),
                            // 7 a key's polytouch (a the key, b the value)
    int ch, a, b;
};

// THE SIREN's ROTOR (siren.py, as live steps it): kind 1 the fire siren's
// (its motor; FIRE), 2 the Helmholtz double siren's (its air; HELMHOLTZ) --
// du/dt = a p (W sqrt(p) - u) - b u, the chest's air after the key's
struct SirenModel {
    double a, b, uk, n, air_tau;
};
static const SirenModel SIREN_FIRE = {0.723, 0.0908, 0.452, 3.8, 0.0};
static const SirenModel SIREN_HELM = {1.50, 0.17, 0.0, 0.0, 0.04};
static const double SIREN_FLOOR_DB = 60.0, SIREN_U_LOW = 0.12;
struct SirenRot {
    int kind = 1;
    double u = 0.0, air = 0.0;
    SirenRot() {}
    explicit SirenRot(int k) : kind(k) {}
    const SirenModel &m() const { return kind == 1 ? SIREN_FIRE : SIREN_HELM; }
};
static double siren_target(double p, const SirenModel &m, double k)
{
    return m.a * p * ((m.a + m.b) / m.a) * sqrt(std::max(p, 0.0)) / k;     // (a p W sqrt(p) / k: w_top)
}
static double siren_step(double u, double p, double dt, const SirenModel &m)
{
    const double k = m.a * p + m.b;
    if (k <= 0.0)
        return u;
    const double t = siren_target(p, m, k);
    return t + (u - t) * exp(-k * dt);
}
static double siren_mean(double u, double p, double dt, const SirenModel &m)
{
    const double k = m.a * p + m.b;
    if (k <= 0.0 || dt <= 0.0)
        return u;
    const double t = siren_target(p, m, k);
    return t + (u - t) * (1.0 - exp(-k * dt)) / (k * dt);
}
static double siren_air(double air, double p, double dt, const SirenModel &m)
{
    if (m.air_tau <= 0.0)
        return p;
    return p + (air - p) * exp(-dt / m.air_tau);
}
static double siren_level(const SirenRot &r)
{
    if (r.kind == 1) {                  // fire_level: self-pumped, 1 at full speed
        const SirenModel &m = SIREN_FIRE;
        if (r.u <= 0.0)
            return 0.0;
        const double x = pow(r.u / m.uk, m.n), x1 = pow(1.0 / m.uk, m.n);
        return sqrt((x / (1.0 + x)) / (x1 / (1.0 + x1)));
    }
    // blown_level: the jet's speed, the disc chopping it once it turns
    return sqrt(std::max(r.air, 0.0)) * (r.u * r.u / (r.u * r.u + SIREN_U_LOW * SIREN_U_LOW));
}
// Rotor.block: dt seconds at drive p -- the mean speed over it, the levels at its ends
static double siren_rot_block(SirenRot &r, double p, double dt, double *l0, double *l1)
{
    *l0 = siren_level(r);
    const double mr = siren_mean(r.u, p, dt, r.m());
    r.u = siren_step(r.u, p, dt, r.m());
    r.air = siren_air(r.air, p, dt, r.m());
    *l1 = siren_level(r);
    return mr;
}
// Rotor.coast: dt seconds with no air (between two presses)
static void siren_coast(SirenRot &r, double dt)
{
    r.u *= exp(-r.m().b * dt);
    r.air = siren_air(r.air, 0.0, dt, r.m());
}
// the crank (CC1): the upper chest's angle, and its phase as samples of the note's own time
static double siren_crank_angle(int cc1)
{
    return M_PI / 12.0 * std::max(0, std::min(127, cc1)) / 127.0;
}
static double siren_crank_samples(double theta, double f_rev, double sr)
{
    return theta * sr / (2.0 * M_PI * f_rev);
}

struct Part {
    Slab S;
    void *cache;
    long long pid;
    double level_db = 0.0, swell = 1.0, rate, retrigger;
    int nbuckets, speed, damper_pedal, soft_drop, soft_top;
    int vol[16], expr[16], cpan[16], pedal_v[16];
    bool soft[16];
    double cgain[16];
    bool cgain_set[16];
    std::set<std::pair<int, int>> down, pedalled;
    // A PALM-MUTED OPEN STRING RINGING ON past its key (live's open_ring):
    // (part id, channel, key) -> (its string, the sample it stops at the latest)
    std::map<std::tuple<long long, int, int>, std::pair<int, long long>> open_ring;
    std::map<Key, long long> tex_on;    // a held texture's key: the sample it may stop (live.tex_on)
    // ...AND ITS GRAINS (live.tex_gen, in the order struck): the key, its
    // template, the next grain's sample, the press's scale; one generator
    // (live._tex_rng; one part here) and the grains' own keys (_tex_n)
    struct TexGen {
        Key key;
        const nv::live::Template *T;
        double nxt, scale;
    };
    std::vector<TexGen> tex_gen;
    PyRandom tex_rng;
    long long tex_n = 0;
    static const long long GRAIN0 = 1LL << 32;     // a grain's layer: GRAIN0 + its number (("grain", n))
    // A HELD ROLL (live.roll_gen, in the order struck): its key, template,
    // its steps (percussion_map.RollSteps: their generator seeded by the key
    // and the press's sample, the stroke counted, the next stroke's s), the
    // press's sample and scale, the key-up's s from the press (NAN: held),
    // its hits' own keys (("roll", n)) counted
    struct RollGen {
        Key key;
        const nv::live::Template *T;
        PyRandom r;
        long long k = 0;
        double t = 0.0;
        long long at = 0;
        double scale = 1.0, close = NAN;
        long long n = 0;
    };
    std::vector<RollGen> roll_gen;
    static const long long ROLL0 = 2LL << 32;      // a roll's hit's layer: ROLL0 + its number

    // the next stroke's hits [(s, level)] (RollSteps.next), and the step on
    static std::vector<std::pair<double, double>> roll_next(RollGen &g)
    {
        const std::vector<double> &p = g.T->roll_par;
        std::vector<std::pair<double, double>> out;
        if (g.T->roll_kind == 4) {
            const double rate = p[0], bounce_s = p[2], bounce_db = p[3], hand_db = p[4], jit = p[5], sc = p[6];
            const int bounces = (int)p[1];
            const double base = g.k == 0 ? p[9] : p[8] + (g.k % 2 ? -hand_db : 0.0);
            for (int b = 0; b < bounces; b++) {
                double tb = g.t + b * bounce_s * (1.0 + pyr_uniform(&g.r, -0.15, 0.15));
                out.push_back({tb, pow(10.0, (base - bounce_db * b + pyr_uniform(&g.r, -sc, sc)) / 40.0)});
            }
            g.k++;
            g.t = (double)g.k / rate + pyr_uniform(&g.r, -jit, jit) / rate;
        } else {
            const double rate = p[0], swell_s = p[1], lo = p[2], hi = p[3], sc = p[4], fp = p[5], fs = p[6], fd = p[7];
            const double db = lo + (hi - lo) * std::min(1.0, g.t / swell_s) + pyr_uniform(&g.r, -sc, sc);
            out.push_back({g.t, pow(10.0, db / 40.0)});
            if (pyr_uniform(&g.r, 0.0, 1.0) < fp)
                out.push_back({g.t + fs, pow(10.0, (db + fd) / 40.0)});
            g.k++;
            g.t = g.t + 1.0 / rate;
        }
        return out;
    }

    // ...and the closing stroke's (RollSteps.close), the key up at s from the press
    static std::vector<std::pair<double, double>> roll_close(RollGen &g, double at)
    {
        const std::vector<double> &p = g.T->roll_par;
        std::vector<std::pair<double, double>> out;
        if (g.T->roll_kind == 4)
            for (int b = 0; b < 2; b++) {
                double tb = at + b * p[2] * (1.0 + pyr_uniform(&g.r, -0.15, 0.15));
                out.push_back({tb, pow(10.0, (p[10] - p[3] * b + pyr_uniform(&g.r, -p[6], p[6])) / 40.0)});
            }
        else
            out.push_back({at, pow(10.0, p[9] / 40.0)});
        return out;
    }
    std::vector<Ev> events;
    std::vector<std::vector<uint8_t>> sx;           // the exclusives the events name (type 6)
    std::map<std::pair<int, int>, int> key_vel;     // (ch, note) -> the strike's velocity
    double pressure[16] = {};                       // channel aftertouch, 0..1
    // THE PITCH WHEEL (live._repitch): each channel's raw wheel and the ratio
    // last applied to its notes; the range, GM's 2 semitones (no RPN 0 here)
    int wheel[16] = {};
    double bend[16] = {1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0};
    double bend_range = 2.0;                        // live.bend_range, the session's
    // THE RPNs (live's _rpn_data, _rpn_step; tonelib's arithmetic): the one
    // selected (an NRPN selected: none), and what the channel's are set to --
    // its bend range (-1: live's bend_range), fine and coarse tuning, the
    // fine tuning's last MSB, the mod wheel's range (cents; -1: live's)
    int rpn_msb[16], rpn_lsb[16];
    bool rpn_none[16] = {};
    int nrpn_msb[16], nrpn_lsb[16];             // the NRPN selected (live's nrpn; 127 none)
    // THE SOUND CONTROLLERS (live's snd): each channel's CC71-78 as its
    // offset d (sound_offset; 0 none), cc - 71 -- read where a part answers
    // them (OrganSpec.snd_mask: the harmonium's attack and release)
    double snd_d[16][8] = {};
    double brange[16], fine[16] = {}, coarse[16] = {}, modrange[16];
    int fine_msb[16];
    double mod_cents = 35.0;                        // live.mod_cents (the session's)
    double mod_rate = 0.25;                         // live.mod_rate: the wheel's +25% rate at full
    std::map<Key, std::vector<char>> sym_at;        // live.sym_at: a note's fixed open strings' rows, off the wheel
    std::map<Key, std::pair<double, std::vector<char>>> meend_at;   // live.meend_at: (its ratio, its strings' mask)
    // THE TUNINGS THE EXCLUSIVES SET (live._sysex): each channel's scale/octave
    // table (live.sota) and the ratio last applied to each pitch class
    // (sota_at); master fine (cents) and coarse (semitones); the gm2 store
    // (mts.TuningStore: its tables, each channel's selection) and the ratio
    // last applied to each key (mts_at: part, channel, sounding key)
    std::map<int, std::array<double, 12>> sota;
    std::map<std::pair<int, int>, double> sota_at;
    double master_fine = 0.0, master_coarse = 0.0;
    // ...and the master volume (live.master_vol) with its ramp: where it has
    // got to, the target its step was fixed for (NaN none), the step
    double master_vol = 1.0, mv_now = 1.0, mv_target = NAN, mv_step = 0.0;
    std::vector<float> mv_g;
    std::map<std::pair<int, int>, std::vector<double>> mts_tab;
    std::map<int, std::pair<int, int>> mts_sel;
    std::map<std::tuple<long long, int, int>, double> mts_at;
    int mts_ref_note = -1;                          // the tuners' reference (--a, --c), -1 none
    double mts_ref_hz = 0.0;
    double vib_mod[16] = {}, vib_modw[16] = {};     // live.mod, live.modw: the wheel's depth, its fraction
    // SOSTENUTO (CC66): the keys down when it went down, held (live.sost)
    std::map<int, std::set<int>> sost;
    // MONO MODE (CC126; live.mono): one voice a channel -- its held keys in
    // press order (note, velocity) and the one sounding (-1 none)
    bool mono[16] = {};
    // PORTAMENTO (live's porta_on, porta_time, porta_src, last_on): CC65,
    // CC5, a pending CC84's source key (-1 none), the channel's last note-on;
    // and where the press being struck glides from (_glide_from, -1 none)
    bool porta_on[16] = {};
    int porta_time[16] = {};
    int porta_src[16] = {-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1};
    int last_on[16] = {-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1};
    int glide_from = -1;
    int moog_src = -1;                      // ...and the last key, for a Moog's GLIDE knob (live._moog_src)
    std::vector<std::pair<int, int>> mono_stack[16];
    int mono_cur[16] = {-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1};
    // THE MOD WHEEL on a honky-tonk (live's 'detune' role): which pre-warmed
    // detune new notes take, the nearest of DETUNE_STEPS (a piano's wheel
    // does nothing else: a hammered string takes no vibrato)
    bool detune_wheel = false;
    double press_db = 8.0;                          // tonelib.PRESS_DB (live.press_db)
    // A DRUM PART (live.Patch(program, True)): its program the drum set, and
    // each key's exclusive class (two words a key: native.kits' choke)
    bool drums = false;
    int program = 0;
    std::vector<unsigned long long> choke;
    // THE PART'S PATCHES (live's Parts on one slab): each its templates and
    // settings, the channel it listens on (-1 every one, less those in excl:
    // bits), its keys lo..hi and transpose; a note takes the last added that
    // claims it. Patch 0 is the part as nv_part_new made it; the members above
    // are the patch in use (Use), patch 0's between notes
    struct Patch {
        void *cache;
        long long pid;
        double level_db;
        int nbuckets, speed, damper_pedal, soft_drop, soft_top;
        bool drums, reg;
        int program;
        std::vector<unsigned long long> choke;
        int channel;
        unsigned excl;
        int lo, hi, transpose;
        // ...muted (live's part.muted: it claims no key), or gone (a part
        // taken away: its notes let go, its place kept so no index moves)
        bool muted = false, gone = false, hidden = false;     // (hidden: the metronome's, no key reaches it)
        int fixed_touch = -1;                   // FIXED TOUCH (live's part.fixed_touch): -1 the patch's way, 1 on, 0 off
        // A REGISTERED ORGAN (live's part.organ): its table, its stops drawn
        // (a rank each), the crescendo's place (part.cres)
        const OrganSpec *organ = nullptr;
        std::vector<char> drawn = {};
        double cres = 0.0;
        // A HAMMOND'S (live.Patch): on the rotors (leslie), the wheel its
        // swell pedal (wheel_swell), its valve's drive (amp_drive)
        bool leslie = false, wheel_swell = false;
        // ...ITS TOUCH (live's Patch.touch_sensitive): whether velocity sets
        // the level -- not on an accordion, whose key only opens a valve
        bool touch = true;
        // ...ITS WHEEL TREMOLO (live's Patch.tremolo_*): what a full wheel
        // asks for, its rate, a stereo pan -- an organ's from its table
        double wtrem = 0.0, wtrem_hz = 0.0;
        bool wtrem_stereo = false;
        double amp = 0.0;
        // ...ITS VOICE's, and the panel's drive knob (live's Part.drive: <0 the
        // voice's); amp is the one in use
        double amp0 = 0.0, drive = -1.0;
        // ...against a fixed peak (amp_reference by the program's trim, 0 the
        // chord's own), through a pair this unbalanced (amp_imbalance)
        double amp_ref = 0.0, amp_imb = 0.06;
        const NoteClass *cab = nullptr;     // its speaker (cab_set), which the templates went through
        int scanner = 0;            // NoteClass.scanner: 0 none, else 1 +2 the switch +4 x depth +16 chorus
        bool clav = false;          // a Clavinet's panel (clav_panel): CC1 its tone rockers
        bool wheel_vib = false;     // its wheel can be a vibrato (wheel_vibrato)
        const MoogLayer *moog = nullptr;    // a Moog's panel (its class's, layer A): Live._moog_panel_for
        const MoogLayer *moog_b = nullptr;  // ...a layered one's second Messenger (moog.layers_of)
        int snd = 0;                // the CC71-78 its voice answers (NoteClass.snd_mask, SOUND_CC's order)
        // ...A PUNGI's DRONE (live's Patch.drone_note_patch): its own
        // variation's templates (nvlive's), their buckets and rotor speed
        void *dcache = nullptr;
        int dnb = 1, dspeed = -1;
        // ...A MOOG's KNOBS, the part's own over its patch's (live's
        // Part.synth, layer A: NV_MK_* -> value), and the panel they and any
        // glide make (built: null while there are none); and whether it reads
        // a Messenger's CC chart (Part.cc_map)
        std::map<int, double> syn;
        std::shared_ptr<MoogLayer> mb;
        std::map<int, double> syn_b;            // ...a layered voice's second Messenger's own (live's synth_b)
        std::shared_ptr<MoogLayer> mb_b;
        std::map<int, double> syn_kept[2];      // (a session's knobs the engine refused: kept, saved back, not heard)
        bool msgr = false;
    };
    std::vector<Patch> patches;
    // THE MODULE's INSERTION EFFECT (live.efx: efxchain.cpp's), its export
    // tables given by nvlive (nv_part_efx); NULL none -- and whether its
    // refusal has been said
    void *efx = nullptr;
    const double *efx_x = nullptr;      // (its export tables: the tremolo's waves)
    // ...ITS COPIES AS REFERENCED TAPS (live.EFX_TAPS: _tap_tables, _tap_arm,
    // Slab.tap_fill): one tap set an effect channel (the module's parts, the
    // tones' own), flattened for tapkernel.c's tap_expand -- rebuilt when
    // the effect, its parts, the tones' channels or a part's pan move; a
    // slot carries its channel's set (S.tp) and its copies are written each
    // block from it as it stands
    struct TapTab {
        std::vector<int32_t> ts, eqo, nmid;
        std::vector<double> eq, dry, al0, ar0, g, fc, r, hz, al1, ar1, dl, vd, vr, ph;
        std::vector<int64_t> D, dmax;
    };
    std::unique_ptr<TapTab> tap_tab;
    std::map<int, int> tap_sid;             // an effect channel's tap set
    std::vector<long long> tap_key;
    bool tap_keyed = false;
    std::vector<void *> tap_colp;           // (tap_expand's generic columns: every kernel column it does not name)
    std::vector<int> tap_colsz;
    long tap_shed = 0;                      // blocks the governor cut the copies on
    // ...each part's notes on it (live.efx_notes: start, end -- inf while
    // held -- velocity, key), what an auto wah's Sens hears; and each part's
    // moving filter over the timeline (nv_efx_live_filter), kept by its rev
    struct EfxNote {
        double s0, s1;
        int vel, note;
    };
    std::map<int, std::vector<EfxNote>> efx_notes;
    struct ModFlt {
        long rev = -1;
        int n = 0;
        double head[4] = {0.0, 0.0, 0.0, 0.0};
        std::vector<double> seg;
    };
    std::map<int, ModFlt> mflt;
    bool efx_said = false;
    // A TONE's OWN EFFECT CHANNEL (live._tone_fx): ch + TONE_SEG x (1 + the
    // tone's place among the channel's tones that brought one, mod 255) --
    // what the tone brings (an insertion effect, a plunger, a mouth) on it;
    // here its moving filter: the plunger's (flt_k 3) or the mouth's (4) --
    // the wheel's and the hand's last moves (live keeps three), and the
    // mouth's wander (efxfilter.MouthWander: its generator, the next draw's
    // time, where it is headed, where it is, when last asked)
    static const int TONE_SEG = 1 << 8;
    static const int VIRT = 1 << 16;        // (gsefx.VIRT: ch + VIRT a parallel type's branch B)
    struct ToneFx {
        int ch = 0;
        const NoteClass *k = nullptr;
        int kind = 0;                       // flt_k: 3 the plunger, 4 the mouth; 0 no filter of its own
        std::vector<std::pair<double, int>> wheel, at;
        void *g = nullptr;
        double next_t = 0.0, t = 0.0;
        int target = -1;
        bool have_cur = false;
        double cur[3] = {0.0, 0.0, 0.0};
        void *ex = nullptr;                 // its own insertion effect (efxchain.cpp's EfxLive), NULL none
    };
    std::map<int, ToneFx> tone_fx;
    std::map<int, std::vector<void *>> tone_seg;
    bool at_seen[16] = {}, wheel_seen[16] = {};     // (live's pressure, wheel_at: a channel's, once moved)
    int wheel_v[16] = {};
    // (channel, CC) -> a wheel job's last value (live's job_at: tonelib.WHEEL_CC),
    // as its own CC or the wheel's route set it
    std::map<std::pair<int, int>, int> job_at;
    int job_get(int ch, int cc) const
    {
        auto it = job_at.find(std::make_pair(ch, cc));
        return it == job_at.end() ? 0 : it->second;
    }
    // THE CABINET (live's rotor_horn, rotor_drum: LiveRotor): one Leslie in
    // the room, every rotor part turning with it, from chorale; the half-moon's
    // position (STOP, CHORALE, TREMOLO) and each channel's wheel armed
    struct LRotor {
        double up = 0.0, down = 0.0, ratio = 1.0, rate = 0.0, target = 0.0, angle = 0.0;
        double advance(double dt)
        {
            double tau = target > rate ? up : down;
            rate += (target - rate) * (1.0 - exp(-dt / tau));
            angle += 2.0 * M_PI * rate * ratio * dt;
            if (angle > 1e6)
                angle = fmod(angle, 2.0 * M_PI);
            return angle;
        }
    } rotor_horn, rotor_drum;
    int half_moon = 1;
    std::map<int, bool> pw_armed;
    double ls_rate = -1.0;

    void leslie_start(const std::vector<double> &L)
    {
        S.les = L;
        rotor_horn.up = L[12]; rotor_horn.down = L[13]; rotor_horn.ratio = 1.0;
        rotor_drum.up = L[14]; rotor_drum.down = L[15]; rotor_drum.ratio = L[5];
        rotor_horn.rate = rotor_horn.target = rotor_drum.rate = rotor_drum.target = L[3];
    }

    bool leslie_on(int ch) const
    {
        for (const Patch &p : patches)
            if (p.leslie && (p.channel < 0 || p.channel == ch))
                return true;
        return false;
    }

    // live._half_moon: a flick of the wheel steps the rotors' speed, firing on
    // the edge and re-armed near the centre (PW_FIRE, PW_REARM)
    void half_moon_step(int ch, int pitch)
    {
        const double ladder[3] = {0.0, S.les[3], S.les[4]};
        double f = pitch / 8192.0;
        auto it = pw_armed.find(ch);
        bool armed = it == pw_armed.end() ? true : it->second;
        if (armed && fabs(f) >= 0.50) {
            pw_armed[ch] = false;
            int i = std::max(0, std::min(2, half_moon + (f > 0.0 ? 1 : -1)));
            if (i != half_moon) {
                half_moon = i;
                rotor_horn.target = ladder[i];
                rotor_drum.target = ladder[i];
            }
        } else if (!armed && fabs(f) <= 0.20) {
            pw_armed[ch] = true;
        }
    }

    // live's callback: the rotors a block on, every rotor slot's swing, and
    // its Doppler where the horn's rate has moved
    // THE SCANNER (live._scan_*): its tables (the export's SCAN), each
    // channel's CC81, the band rows of each (part, position) from the siren
    // rows' pool, and each rank's data for a position, worked out at its
    // first press (live prepares it off the audio thread)
    std::vector<double> scan;
    std::map<int, int> cc_scan;
    std::map<std::tuple<int, int>, std::vector<int>> scan_row;
    std::deque<int> siren_free = [] {
        std::deque<int> d;
        for (int r = 33; r < 65; r++)       // (WIND_ROWS + 1 ...)
            d.push_back(r);
        return d;
    }();
    // THE SIRENS (live's siren_st, siren_mem, siren_retire): (pid, ch, note)
    // the sounding note's rotor and rows, in the order struck (a dict's); a
    // rotor let go remembered with the sample it was, still turning; rows of a
    // note just ended waiting for its fade -- and a siren's air beside the
    // channel's pressure: each key's polytouch, the channel's CC2
    typedef std::tuple<long long, int, int> SKey;
    struct SirenSt {
        SirenRot rot;
        std::vector<int> rows;
        bool down = true, ends = false;
        long long drive_end = 0;
        double pv = 1.0, acc[2] = {0.0, 0.0}, frev = 0.0, dl = 0.0;
    };
    std::vector<std::pair<SKey, SirenSt>> siren_st;
    std::map<SKey, std::pair<SirenRot, long long>> siren_mem;
    std::vector<std::pair<long long, std::vector<int>>> siren_retire;
    std::map<std::pair<int, int>, double> ppress;
    double cc2v[16] = {};
    std::vector<std::pair<SKey, SirenSt>>::iterator siren_find(const SKey &k)
    {
        return std::find_if(siren_st.begin(), siren_st.end(), [&](const std::pair<SKey, SirenSt> &x) {
            return x.first == k;
        });
    }
    bool siren_of(long long p, int ch, int note) { return siren_find(SKey(p, ch, note)) != siren_st.end(); }
    struct ScanPrep {
        std::vector<int> band;
        std::vector<double> dry, sc;
        std::vector<long> src;
        std::vector<double> mm, cc;
        std::vector<char> lhorn;            // tier B's copies' lobes (a rotary voice's), worked out with them
        std::vector<float> lfl, lsh;
        std::vector<double> lnrm;
    };
    std::map<std::tuple<const void *, int, int>, ScanPrep> scan_g;
    long long cur_blk = 128;
    // ...WORKED OUT OFF THE AUDIO THREAD when playing (scan_async: live's
    // builder, _scan_prefetch): every warmed rank for each position in play,
    // a press whose rank is not ready yet playing dry, its rank queued
    bool scan_async = false, scan_stop = false;
    std::thread scan_thread;
    std::mutex scan_mu;
    std::condition_variable scan_cv;
    std::deque<std::tuple<const nv::live::Template *, int, int>> scan_jobs;

    ScanPrep make_prep(const nv::live::Template &R, int dep, int cho) const
    {
        ScanPrep g;
        long n = R.P;
        g.band.resize(n);
        g.dry.resize(2 * n);
        g.sc.resize(2 * n);
        long ns = 0, *src = nullptr;
        double *mm = nullptr, *cc = nullptr;
        nv_scan_prep(scan.data(), n, R.f4[2].data(), R.f4[0].data(), R.f4[1].data(), R.i8[0].data(), R.f4[25].data(),
                     dep, cho, rate, g.band.data(), g.dry.data(), g.sc.data(), &ns, &src, &mm, &cc);
        g.src.assign(src, src + ns);
        g.mm.assign(mm, mm + ns);
        g.cc.assign(cc, cc + 2 * ns);
        free(src); free(mm); free(cc);
        if (!S.les.empty() && !R.lhorn.empty() && ns) {
            std::vector<double> nf(ns);
            std::vector<char> fl(ns);
            for (long j = 0; j < ns; j++) {
                nf[j] = (double)R.f4[F4_nf][g.src[j]] + scan[0] * g.mm[j];
                fl[j] = R.lflip.empty() ? 0 : R.lflip[g.src[j]];
            }
            g.lhorn.resize(ns); g.lfl.resize(ns); g.lsh.resize(ns); g.lnrm.resize(ns);
            nv_leslie_params(ns, nf.data(), fl.data(), S.les.data(), g.lhorn.data(), g.lfl.data(), g.lsh.data(),
                             g.lnrm.data());
        }
        return g;
    }

    void scan_worker()
    {
        for (;;) {
            std::tuple<const nv::live::Template *, int, int> j;
            {
                std::unique_lock<std::mutex> lk(scan_mu);
                scan_cv.wait(lk, [&] { return scan_stop || !scan_jobs.empty(); });
                if (scan_stop)
                    return;
                j = scan_jobs.front();
                scan_jobs.pop_front();
                if (scan_g.count(std::make_tuple((const void *)std::get<0>(j), std::get<1>(j), std::get<2>(j))))
                    continue;
            }
            ScanPrep g = make_prep(*std::get<0>(j), std::get<1>(j), std::get<2>(j));
            std::lock_guard<std::mutex> lk(scan_mu);
            scan_g[std::make_tuple((const void *)std::get<0>(j), std::get<1>(j), std::get<2>(j))] = std::move(g);
        }
    }

    // every warmed rank of every scanner part, for this position, queued (the worker's lock held by the caller)
    void scan_prefetch_locked(int dep, int cho)
    {
        for (const Patch &p : patches) {
            if (!p.scanner || p.drums)
                continue;
            long n = 0;
            nv_tcache_at(p.cache, -1, &n);
            for (long i = 0; i < n; i++) {
                const nv::live::Template *T = nv_tcache_at(p.cache, i, nullptr);
                for (const nv::live::Template &R : T->ranks)
                    if (R.P)
                        scan_jobs.push_back(std::make_tuple(&R, dep, cho));
            }
        }
    }

    void start_scan_worker()
    {
        if (scan_async || scan.empty())
            return;
        scan_async = true;
        {
            std::lock_guard<std::mutex> lk(scan_mu);
            for (const Patch &p : patches) {        // each voice's own position
                int dep = (p.scanner >> 2) & 3;
                if (p.scanner && dep)
                    scan_prefetch_locked(dep, (p.scanner >> 4) & 1);
            }
        }
        scan_thread = std::thread([this] { scan_worker(); });
        scan_cv.notify_all();
    }

    static LobePre lobe_of_t(const nv::live::Template &R)
    {
        LobePre p;
        if (!R.lhorn.empty()) {
            p.horn = R.lhorn.data();
            p.fl = R.lfl.data();
            p.sh = R.lsh.data();
            p.nrm = R.lnrm.data();
        }
        return p;
    }

    // live._scan_setting: the part's position on this channel, (depth, chorus); depth 0 off
    std::pair<int, int> scan_setting(const Patch &p, int ch) const
    {
        int depth = (p.scanner >> 2) & 3, cho = (p.scanner >> 4) & 1;
        auto it = cc_scan.find(ch);
        if ((p.scanner & 2) && it != cc_scan.end()) {
            static const int start[7] = {0, 18, 37, 55, 73, 91, 110};
            int pos = 0;
            for (int q = 0; q < 7; q++)
                if (it->second >= start[q])
                    pos = q;
            depth = pos == 0 ? 0 : (pos - 1) % 3 + 1;
            cho = pos >= 4;
        }
        return std::make_pair(depth, cho);
    }

    // live._scanner_block: every scanner's band rows, this block
    void scanner_block(long long n0, long long frames)
    {
        for (auto &kv : scan_row) {
            int dep = std::get<0>(kv.first), cho = std::get<1>(kv.first);
            for (int b = 0; b < 6; b++) {
                int row = kv.second[b];
                double c[2];
                nv_scan_bc(scan.data(), (double)n0 / rate, (double)(n0 + frames) / rate, dep, b, cho, rate, c);
                BRt[row] = (float)(1.0 + (c[1] - c[0]) / (double)frames);
                BCt[row] = c[0];
                BLt[2 * row] = BLt[2 * row + 1] = 1.0f;
            }
        }
    }

    // live._scan_stamp: the selector on a rank just stamped (slots dry): on
    // vibrato its slots on their band rows at the scanned path's gain; on
    // chorus the dry share, and a copy the scanned; tier B's copies after
    void scan_stamp(const nv::live::Template &R, int ch, int note, int ri, long long n0, double scale,
                    const std::vector<long> &dry_slots)
    {
        const Patch &p = patches[cur];
        std::pair<int, int> st = scan_setting(p, ch);
        if (!st.first || dry_slots.empty() || scan.empty())
            return;
        int dep = st.first, cho = st.second;
        // its band rows (_scan_rows), from the pool
        auto rk = std::make_tuple(dep, cho);
        if (!scan_row.count(rk)) {
            if (siren_free.size() < 6)
                return;
            std::vector<int> rws;
            for (int b = 0; b < 6; b++) {
                rws.push_back(siren_free.front());
                siren_free.pop_front();
            }
            scan_row[rk] = rws;
            scanner_block(n0, cur_blk);
        }
        const std::vector<int> &rows = scan_row[rk];
        auto gk = std::make_tuple((const void *)&R, dep, cho);
        const ScanPrep *gp = nullptr;
        if (scan_async) {
            // (off this thread: not ready, the press plays dry and its rank is queued)
            std::lock_guard<std::mutex> lk(scan_mu);
            auto it = scan_g.find(gk);
            if (it == scan_g.end()) {
                scan_jobs.push_front(std::make_tuple(&R, dep, cho));
                scan_cv.notify_all();
                return;
            }
            gp = &it->second;
        } else {
            auto it = scan_g.find(gk);
            if (it == scan_g.end())
                it = scan_g.emplace(gk, make_prep(R, dep, cho)).first;
            gp = &it->second;
        }
        const ScanPrep &g = *gp;
        auto put = [&](const std::vector<long> &slots, const std::vector<double> &gain, bool br) {
            std::vector<float> r(slots.size());
            for (size_t q = 0; q < slots.size(); q++)
                r[q] = (float)hypot(gain[2 * q], gain[2 * q + 1]);
            S.channel_gain_each(slots, r);
            for (size_t q = 0; q < slots.size(); q++) {
                long s = slots[q];
                double a = atan2(gain[2 * q + 1], gain[2 * q]);
                S.f8[F8_p0][s] += a;
                S.f8[F8_p0R][s] += a;
                if (br)
                    S.i4[I4_br][s] = rows[g.band[q]];
            }
        };
        auto sidestamp = [&]() {
            long ns = (long)g.src.size();
            if (!ns)
                return;
            // each copy: the rank's row, its pitch moved m scan steps, its level and phase by its gain
            std::vector<double> f8c[6], aL64(ns), aR64(ns);
            std::vector<float> f4c[27], hr(ns);
            std::vector<long long> i8c[2], cofc;
            std::vector<int32_t> i4c[6];
            std::vector<char> lfl;
            for (int c = 0; c < 6; c++) f8c[c].resize(ns);
            for (int c = 0; c < 27; c++) f4c[c].resize(ns);
            for (int c = 0; c < 2; c++) i8c[c].resize(ns);
            for (int c = 0; c < 6; c++) i4c[c].resize(ns);
            std::vector<double> dwx(ns), nf64(ns);
            for (long j = 0; j < ns; j++) {
                long q = g.src[j];
                for (int c = 0; c < 6; c++) f8c[c][j] = R.f8[c][q];
                for (int c = 0; c < 27; c++) f4c[c][j] = R.f4[c][q];
                for (int c = 0; c < 2; c++) i8c[c][j] = R.i8[c][q];
                for (int c = 0; c < 6; c++) i4c[c][j] = R.i4[c][q];
                double m = g.mm[j], cr = g.cc[2 * j], ci = g.cc[2 * j + 1];
                double om1 = R.f8[F8_om][q] + 2.0 * M_PI * scan[0] / rate * m;
                dwx[j] = om1 - R.f8[F8_om][q];
                f8c[F8_om][j] = om1;
                nf64[j] = (double)R.f4[F4_nf][q] + scan[0] * m;
                f4c[F4_nf][j] = (float)nf64[j];
                double gm = hypot(cr, ci), an = atan2(ci, cr);
                aL64[j] = (double)R.f4[F4_aL][q] * gm;
                aR64[j] = (double)R.f4[F4_aR][q] * gm;
                f8c[F8_p0][j] = R.f8[F8_p0][q] + an;
                f8c[F8_p0R][j] = R.f8[F8_p0R][q] + an;
                hr[j] = R.hrel[q];
                if (!R.cof.empty()) cofc.push_back(R.cof[q]);
                lfl.push_back(R.lflip.empty() ? 0 : R.lflip[q]);
            }
            const double *f8p[6]; const float *f4p[27]; const long long *i8p[2]; const int32_t *i4p[6];
            for (int c = 0; c < 6; c++) f8p[c] = f8c[c].data();
            for (int c = 0; c < 27; c++) f4p[c] = f4c[c].data();
            for (int c = 0; c < 2; c++) i8p[c] = i8c[c].data();
            for (int c = 0; c < 6; c++) i4p[c] = i4c[c].data();
            Key sk(pid, ch, note, SCANSIDE0 + (rank_layer(patches[cur].organ, ri) - RANK0));
            if (!S.stamp(f8p, f4p, i8p, i4p, hr.data(), ns, sk, n0, scale, 0, false, NAN, ch, nullptr, nullptr, 0.0,
                         0.0, cofc.empty() ? nullptr : cofc.data(), aL64.data(), aR64.data())) {
                dropped++;
                return;
            }
            std::vector<long> ss = S.last_slots;
            for (long j = 0; j < ns; j++) {
                long s = ss[j];
                S.i4[I4_br][s] = rows[g.band[g.src[j]]];
                double turn = dwx[j] * (double)(S.i8[0][s] - i8c[0][j]);
                S.f8[F8_p0][s] += turn;
                S.f8[F8_p0R][s] += turn;
            }
            if (p.leslie && !S.les.empty()) {
                std::vector<float> az(ns), nf32(ns);
                for (long j = 0; j < ns; j++) {
                    az[j] = f4c[24][j];
                    nf32[j] = f4c[F4_nf][j];
                }
                LobePre lp;
                if (!g.lhorn.empty()) {
                    lp.horn = g.lhorn.data(); lp.fl = g.lfl.data(); lp.sh = g.lsh.data(); lp.nrm = g.lnrm.data();
                }
                S.leslie_arm(ss, az.data(), nf32.data(), lfl.data(), n0, rotor_horn.rate, rotor_drum.rate,
                             nf64.data(), lp);
            }
        };
        if (!cho) {
            put(dry_slots, g.sc, true);
            sidestamp();
            return;
        }
        put(dry_slots, g.dry, false);
        const double *f8p[6]; const float *f4p[27]; const long long *i8p[2]; const int32_t *i4p[6];
        for (int c = 0; c < 6; c++) f8p[c] = R.f8[c].data();
        for (int c = 0; c < 27; c++) f4p[c] = R.f4[c].data();
        for (int c = 0; c < 2; c++) i8p[c] = R.i8[c].data();
        for (int c = 0; c < 6; c++) i4p[c] = R.i4[c].data();
        Key ck(pid, ch, note, SCAN0 + (rank_layer(patches[cur].organ, ri) - RANK0));
        if (!S.stamp(f8p, f4p, i8p, i4p, R.hrel.data(), R.P, ck, n0, scale, 0, false, NAN, ch,
                     R.sof.empty() ? nullptr : R.sof.data(), R.rof.empty() ? nullptr : R.rof.data(), 0.0, 0.0,
                     R.cof.empty() ? nullptr : R.cof.data())) {
            dropped++;
            return;
        }
        std::vector<long> cs = S.last_slots;
        if (p.leslie && !S.les.empty())
            S.leslie_arm(cs, R.f4[24].data(), R.f4[2].data(), R.lflip.empty() ? nullptr : R.lflip.data(), n0,
                         rotor_horn.rate, rotor_drum.rate, nullptr, lobe_of_t(R));
        put(cs, g.sc, true);
        sidestamp();
    }

    // THE VALVE, LIVE (live._amp_*): a part with one is stale whenever its
    // chord changes (amp_dirty); the pump snapshots the chord's direct sound
    // at its level now and asks for its products -- a fast pass and the
    // file's fine one -- and places what comes back, the fine over the fast,
    // each crossing over the last, a result for a chord already gone
    // dropped. In step (the checks: examples/ampsync.py) both passes answer
    // as the job is posted and land at the next pump; playing (amp_async),
    // on a worker of their own.
    struct AmpOut {
        long long pid = 0;
        long src = 0;
        std::vector<double> prod;           // (Hz, amplitude, phase) each
        long long when = 0, jid = 0;
        std::vector<char> lhorn;            // its products' lobes, worked out with them (on the rotors)
        std::vector<float> lfl, lsh;
        std::vector<double> lnrm;
    };

    // the products' lobes, where the part is on the rotors (live's leslie_arm for them)
    void amp_lobes(AmpOut &o) const
    {
        long n = (long)o.prod.size() / 3;
        if (S.les.empty() || !n)
            return;
        std::vector<double> nf(n);
        for (long q = 0; q < n; q++)
            nf[q] = o.prod[3 * q];
        o.lhorn.resize(n); o.lfl.resize(n); o.lsh.resize(n); o.lnrm.resize(n);
        nv_leslie_params(n, nf.data(), nullptr, S.les.data(), o.lhorn.data(), o.lfl.data(), o.lsh.data(),
                         o.lnrm.data());
    }
    std::map<long long, int> drive_step;
    bool wheel_reset = false;               // a reset's CC1 = 0: only the roles whose rest is 0
    std::map<long long, int> clav_step;     // live's: a part's rockers, once its wheel has moved
    std::set<long long> amp_dirty;
    std::map<long long, long long> amp_jid, amp_start, amp_fine_placed;
    bool amp_busy = false, amp_has_out = false;
    AmpOut amp_out;
    std::deque<AmpOut> amp_fine_results;
    // the worker (amp_async)
    bool amp_async = false, amp_stop = false;
    std::thread amp_thread, amp_fine_thread;
    std::mutex amp_mu;
    std::condition_variable amp_cv, amp_fine_cv;
    std::deque<AmpOut> amp_jobs, amp_ready_fast, amp_ready_fine;
    struct AmpJob {
        std::vector<double> f, a, p;
        double drive = 0.0, ref = 0.0, imb = 0.06;
    };
    std::map<long long, AmpJob> amp_jobdata;    // jid -> its parents
    // the fine pass's waiting chords, the newest of each part (live's
    // amp_fine_pending: an older one of the same part is passed over)
    std::map<long long, std::pair<AmpOut, AmpJob>> amp_fine_pending;

    static const int LIVE_DRIVE_STEPS = 8;
    int LIVE_AMP_LOOKAHEAD = 3;             // (live's; the checks set it)
    // live.LIVE_AMP_HOLD: a valve part's note waits for its products
    bool LIVE_AMP_HOLD = true;
    double LIVE_AMP_HOLD_S = 0.060;
    // live._amp_change: a chord's change (a note's onset, or its release)
    // no result covers yet
    struct Chg {
        bool on;
        int ch, note;
        std::vector<long> idx;
        long long T;
        double xf;
        long long jid0, sh;
    };
    std::map<long long, std::vector<Chg>> amp_chg;
    // live.amp_jobT: where each job's products take over (has, at, crossover)
    struct Cross {
        bool has;
        long long at;
        double xf;
        Cross() : has(false), at(0), xf(0.0) {}
    };
    std::map<long long, std::map<long long, Cross>> amp_jobT;
    Cross amp_end;                          // live._amp_end
    std::map<std::tuple<long long, int, int>, long long> amp_shifted;
    // the worker's synthesis threads: a share of the cores, the rest left to
    // the audio thread and the GPU's driver (every core made them miss)
    unsigned AMP_THREADS = 2;

    int patch_of_pid(long long id) const
    {
        for (size_t i = 0; i < patches.size(); i++)
            if (patches[i].pid == id)
                return (int)i;
        return -1;
    }

    void amp_touch(int pi)
    {
        if (pi >= 0 && valved(pi))
            amp_dirty.insert(patches[pi].pid);
    }

    long long amp_ahead() { return !patches[cur].drums && valved(cur) ? LIVE_AMP_LOOKAHEAD * cur_blk : 0; }

    // a part on a valve: its voice's own (amp_drive), or its insertion
    // effect's OD stage (live._efx_od)
    bool valved(int pi) { return patches[pi].amp > 0.0 || efx_od(pi) != nullptr; }

    // live._efx_od: the chain with an OD stage this part plays through, or
    // NULL -- its channel's, or (a part on every channel) the first of the
    // effect's channels it is sounding on, else the first of them; or, the
    // part on none of them, its TONE's own (Rock Piano's Overdrive)
    const double *efx_od(int pi)
    {
        const Patch &p = patches[pi];
        const NoteClass *k = p.drums ? nullptr : nv_tcache_class(p.cache, p.program);
        if (k && k->efx_raw && !(p.channel >= 0 && efx && nv_efx_live_on(efx, p.channel))) {
            for (auto &kv : tone_fx)            // (its chain: the tone's, where a note of it has built it)
                if (kv.second.k == k && kv.second.ex) {
                    const double *fc = efx_for(kv.first);
                    return fc && fc[1] != 0.0 ? fc : nullptr;
                }
            return nullptr;
        }
        if (!efx || !nv_efx_live_parts(efx))
            return nullptr;
        std::vector<int> chs;
        if (p.channel >= 0) {
            chs.push_back(p.channel);
        } else {
            std::set<int> on;
            for (auto &kv : S.live) {
                const int c = (int)std::get<1>(kv.first);
                if (std::get<0>(kv.first) == p.pid && c >= 0 && c < 16 && nv_efx_live_on(efx, c))
                    on.insert(c);
            }
            if (on.empty())
                for (int c = 0; c < 16; c++)
                    if (nv_efx_live_on(efx, c))
                        on.insert(c);
            chs.assign(on.begin(), on.end());
        }
        for (int c : chs) {
            const double *fc = efx_for(c);
            if (fc && fc[1] != 0.0)
                return fc;
        }
        return nullptr;
    }

    // the type's speaker (the export's cabinets: guitar12, bass410), as
    // nvrender builds them -- NULL under TUNING_CABINET=0
    std::vector<char> fx_cabbuf[2];
    const NoteClass *fx_cab_k[2] = {nullptr, nullptr};
    const NoteClass *efx_cab(double which)
    {
        const int w = (int)which - 1;
        if (w < 0 || w > 1 || !efx_x)
            return nullptr;
        const char *cb = getenv("TUNING_CABINET");
        if (cb && !strcmp(cb, "0"))
            return nullptr;
        if (!fx_cab_k[w]) {
            const double *C = efx_x + 132 + NV_EFX_NAT * (size_t)efx_x[131] + 30 + 33 * w;
            fx_cabbuf[w].assign(sizeof(NoteClass), 0);
            NoteClass *nc = (NoteClass *)fx_cabbuf[w].data();
            nc->cab_set = (int)C[0];
            nc->n_cab_fm = (int)C[1];
            nc->n_cab_afm = (int)C[2];
            nc->cab_floor = C[3];
            for (int r = 0; r < 4; r++)
                for (int x = 0; x < 3; x++) {
                    nc->cab_fm[r][x] = C[4 + 3 * r + x];
                    nc->cab_afm[r][x] = C[16 + 3 * r + x];
                }
            nc->cab_corner = C[28]; nc->cab_order = C[29]; nc->cab_cut = C[30]; nc->cab_bell = C[31];
            nc->cab_ref = C[32];
            fx_cab_k[w] = nc;
        }
        return fx_cab_k[w];
    }

    // live._amp_snapshot: the chord's direct partials at their level now
    bool amp_snapshot(long long apid, long long n0, AmpOut &job, AmpJob &jd)
    {
        int pi = patch_of_pid(apid);
        Key key(apid, -1, -1, AMPK);
        if (pi < 0) {
            amp_off(key, n0);
            return false;
        }
        const Patch &p = patches[pi];
        auto st = drive_step.find(apid);
        double drive = st == drive_step.end() ? p.amp : p.amp * 4.0 * st->second / (double)LIVE_DRIVE_STEPS;
        // THE INSERTION EFFECT's OD: its gain already in the notes' level
        // (efx_direct); the valve the voice's own, or -- a voice with none --
        // one at its edge (gsefx.PEDAL_AMP_DRIVE), measured against the
        // Strat's level (0.2289 x the program's trim); either reference
        // carries the type's Level
        const double *od = efx_od(pi);
        double ref_e = 0.0;
        if (od) {
            if (drive <= 0.0) {
                drive = efx_x[132 + NV_EFX_NAT * (size_t)efx_x[131] + 6];
                ref_e = 0.2289 * nv_tcache_trim(p.cache, p.program);
            } else {
                ref_e = p.amp_ref;
            }
            if (ref_e != 0.0)
                ref_e *= od[0];
        }
        std::vector<const std::vector<long> *> groups;
        size_t nslots = 0;
        // (a parallel type's branch B is in the chord where B has an OD of its own)
        const double *odb = od && od[208] != 0.0 && efx ? nv_efx_live_rec_b(efx) : nullptr;
        const bool b_od = odb && odb[1] != 0.0;
        for (auto &kv : S.live) {
            const Key &k = kv.first;
            if (std::get<0>(k) != apid || std::get<3>(k) == AMPK
                || (std::get<3>(k) >= AMP_OLD0 && !(b_od && std::get<3>(k) >= EFXB0)))
                continue;                   // (not a valve's products, the old tones' among them)
            auto t = key_tone.find(Key(std::get<0>(k), std::get<1>(k), std::get<2>(k), 0));
            if (t != key_tone.end() && t->second != p.cache)
                continue;                   // this tone's notes only
            groups.push_back(&kv.second);
            nslots += kv.second.size();
        }
        if (drive <= 0.0 || nslots < 2) {
            amp_off(key, n0);
            return false;
        }
        // each note's direct sound, its own shortest path (live's: the stage
        // places a key by its pitch, so one minimum for the chord left out
        // every note more than 2 samples later than the earliest)
        std::vector<long> idx;
        for (const std::vector<long> *g : groups) {
            double mn = 0.0;
            for (size_t q = 0; q < g->size(); q++) {
                double dl = (double)S.f4[F4_delL][(*g)[q]] + (double)S.f4[F4_delR][(*g)[q]];
                if (q == 0 || dl < mn)
                    mn = dl;
            }
            for (long s : *g)
                if ((double)S.f4[F4_delL][s] + (double)S.f4[F4_delR][s] <= mn + 2.0)
                    idx.push_back(s);
        }
        if (idx.size() < 2) {
            amp_off(key, n0);
            return false;
        }
        std::vector<long> ok;
        std::vector<double> f, aM, ph;
        for (long s : idx) {
            double om = S.f8[F8_om][s];
            double fq = om * rate / (2.0 * M_PI);
            double a = 0.5 * ((double)S.aL0[s] + (double)S.aR0[s]);
            double t = std::max(0.0, (double)n0 - (double)S.i8[0][s]) / rate;
            double sl = (double)S.f4[F4_sus][s], af = (double)S.f4[F4_aft][s];
            double dc = sl + (1.0 - sl) * ((1.0 - af) * exp(-t * (double)S.f4[F4_logr][s])
                                           + af * exp(-t * (double)S.f4[F4_logrA][s]));
            double rx = ((double)n0 - (double)S.i8[1][s]) / std::max((double)S.f4[F4_re][s], 1.0);
            rx = rx < 0.0 ? 0.0 : (rx > 1.0 ? 1.0 : rx);
            a = a * dc * (1.0 - rx * rx * (3.0 - 2.0 * rx));
            double pp = S.f8[F8_p0][s] + om * (double)n0;
            if (fq > 20.0 && a > 0.0) {
                ok.push_back(s);
                f.push_back(fq);
                aM.push_back(a);
                ph.push_back(pp);
            }
        }
        if (ok.size() < 2) {
            amp_off(key, n0);
            return false;
        }
        size_t best = 0;
        long long first = S.i8[0][ok[0]];
        for (size_t q = 0; q < ok.size(); q++) {
            if (aM[q] > aM[best])
                best = q;
            first = std::min(first, S.i8[0][ok[q]]);
        }
        amp_start[apid] = first;
        job.pid = apid;
        job.src = ok[best];
        job.when = n0;
        jd.f = f;
        jd.a = aM;
        jd.p = ph;
        jd.drive = drive;
        jd.imb = p.amp_imb;
        jd.ref = 0.0;
        const double aref = od ? ref_e : p.amp_ref;
        if (aref != 0.0) {
            // THE FADERS SET THE LEVEL, NOT THE DRIVE: the channel's, the
            // part's and the headroom in the reference too (the part's
            // channel, or its first sounding key's)
            int ch = p.channel;
            if (ch < 0) {
                ch = 0;
                for (auto &kv : S.live)
                    if (std::get<0>(kv.first) == apid && std::get<1>(kv.first) >= 0 && std::get<1>(kv.first) < 256) {
                        ch = (int)std::get<1>(kv.first);
                        break;
                    }
            }
            jd.ref = aref * chan_gain(ch) * (pow(10.0, level_db / 20.0) * swell) * S.headroom_d;
        }
        return true;
    }

    // one pass: the fast (live's 0.25 s, 150 products, no oversampling) or the fine (valvefine's)
    static void amp_pass(const AmpJob &jd, double sr, bool fine, std::vector<double> &prod, unsigned threads = 0)
    {
        double *out = nullptr;
        long n = nv_amp_live_t(jd.f.data(), jd.a.data(), jd.p.data(), (long)jd.f.size(), sr, jd.drive,
                               fine ? 1.0 : 0.25, 1, fine ? 400 : 150, &out, threads, jd.ref, jd.imb);
        prod.assign(out, out + 3 * n);
        free(out);
    }

    // live._amp_off: the products under key end -- at `at` over xf (a
    // change's; amp_end where a snapshot ends them), else now as they are;
    // those not begun by then never sound. What was there.
    std::vector<long> amp_off(const Key &key, long long n0, bool has_at = false, long long at = 0,
                              bool has_xf = false, double xfv = 0.0)
    {
        if (!has_at && amp_end.has) {
            has_at = true;
            at = amp_end.at;
            has_xf = true;
            xfv = amp_end.xf;
        }
        if (!has_at)
            at = n0;
        long li = S.live_find(key);
        std::vector<long> old = li >= 0 ? S.live[li].second : std::vector<long>();
        for (long s : old) {
            if (has_xf)
                S.f4[F4_re][s] = (float)xfv;
            if (S.i8[0][s] >= at)
                S.f4[F4_re][s] = 1.0f;
        }
        S.release(key, at);
        return old;
    }

    // live._amp_place: what came back, the products before it crossing out
    // -- at their chord's change (cross), or now
    void amp_place(long long n0, const AmpOut &o, const Cross &cross = Cross())
    {
        Key key(o.pid, -1, -1, AMPK);
        float xf = (float)(long long)(0.020 * rate);
        long long at = n0;
        double xin = (double)xf;
        if (cross.has && cross.at >= n0) {
            at = cross.at;
            xin = cross.xf;
        }
        std::vector<long> old = amp_off(key, n0, true, at, true, xin);
        if (o.prod.empty() || !S.busy[o.src])
            return;
        int pi = patch_of_pid(o.pid);
        const OrganSpec *cog = pi >= 0 ? patches[pi].organ : nullptr;
        bool held = false;
        for (auto &kv : S.live) {
            const Key &k = kv.first;
            long long l = std::get<3>(k);
            if (std::get<0>(k) != o.pid)
                continue;
            if (l == -1) {
                held = true;
                break;
            }
            // ...or a rank of THIS organ's, by its stop's name (live's `k[3] in
            // ranks`): a rank struck on another organ, before a program
            // change, is one of this one's only where they share a name
            if (rank_of(cog, l) >= 0)
                held = true;
            if (held)
                break;
        }
        if (!held)
            return;                         // never after their notes
        long n = (long)o.prod.size() / 3;
        std::vector<double> f(n), a(n), p(n);
        for (long q = 0; q < n; q++) {
            f[q] = o.prod[3 * q];
            a[q] = o.prod[3 * q + 1];
            p[q] = o.prod[3 * q + 2];
        }
        const double *odp = pi >= 0 ? efx_od(pi) : nullptr;
        const NoteClass *pcab = pi >= 0 ? patches[pi].cab : nullptr;
        if (odp) {
            // the type's speaker where the voice has none, and its EQ -- AFTER
            // the valve, so on its products too (gsefx.eq_gain)
            if (!pcab)
                pcab = efx_cab(odp[2]);
            if (odp[6] != 0.0)
                for (long q = 0; q < n; q++)
                    a[q] *= nv_efx_eq_gain(odp, f[q]);
        }
        if (pcab)                           // through the speaker, as the notes were (cabinet.gain)
            for (long q = 0; q < n; q++)
                a[q] *= nv_cab_gain(pcab, f[q]);
        auto as = amp_start.find(o.pid);
        long long start = cross.has ? at : std::max(n0, as == amp_start.end() ? n0 : as->second);
        std::vector<long> slots = S.stamp_amp(key, o.src, f.data(), a.data(), p.data(), n, start, rate, o.when);
        if (!slots.empty() && (cross.has || (!old.empty() && start <= n0)))
            for (long s : slots)
                S.f4[F4_fa][s] = cross.has ? (float)xin : xf;
        if (!slots.empty() && S.ls_on[o.src] && !S.les.empty()) {
            std::vector<float> az(n, S.ls_ph[o.src]);
            LobePre lp;
            if ((long)o.lhorn.size() == n) {
                lp.horn = o.lhorn.data(); lp.fl = o.lfl.data(); lp.sh = o.lsh.data(); lp.nrm = o.lnrm.data();
            }
            S.leslie_arm(slots, az.data(), nullptr, nullptr, n0, rotor_horn.rate, rotor_drum.rate, f.data(), lp);
        }
    }

    void amp_worker()
    {
        for (;;) {
            AmpOut j;
            AmpJob jd;
            {
                std::unique_lock<std::mutex> lk(amp_mu);
                amp_cv.wait(lk, [&] { return amp_stop || !amp_jobs.empty(); });
                if (amp_stop)
                    return;
                j = amp_jobs.front();
                amp_jobs.pop_front();
                jd = amp_jobdata[j.jid];
            }
            AmpOut fast = j;
            amp_pass(jd, rate, false, fast.prod, AMP_THREADS);
            amp_lobes(fast);
            std::lock_guard<std::mutex> lk(amp_mu);
            amp_ready_fast.push_back(fast);
            amp_jobdata.erase(j.jid);
            amp_fine_pending[j.pid] = std::make_pair(j, jd);
            amp_fine_cv.notify_all();
        }
    }

    // THE FINE PASS ON A THREAD OF ITS OWN (live's _amp_fine_worker): on the
    // fast pass's, the next chord's fast pass waited behind this one's 30-70
    // ms, so a note played soon after another change -- a key let go, a
    // second note -- sounded clean until it landed (Ben, live)
    void amp_fine_worker()
    {
        for (;;) {
            AmpOut j;
            AmpJob jd;
            {
                std::unique_lock<std::mutex> lk(amp_mu);
                amp_fine_cv.wait(lk, [&] { return amp_stop || !amp_fine_pending.empty(); });
                if (amp_stop)
                    return;
                auto it = amp_fine_pending.begin();
                for (auto q = amp_fine_pending.begin(); q != amp_fine_pending.end(); ++q)
                    if (q->second.first.jid > it->second.first.jid)
                        it = q;                     // (the newest chord any part waits on)
                j = it->second.first;
                jd = it->second.second;
                amp_fine_pending.erase(it);
            }
            AmpOut fine = j;
            amp_pass(jd, rate, true, fine.prod, AMP_THREADS);
            amp_lobes(fine);
            std::lock_guard<std::mutex> lk(amp_mu);
            amp_ready_fine.push_back(fine);
        }
    }

    void start_amp_worker()
    {
        if (amp_async)
            return;
        amp_async = true;
        amp_thread = std::thread([this] { amp_worker(); });
        amp_fine_thread = std::thread([this] { amp_fine_worker(); });
    }

    // live._amp_pump
    void amp_pump(long long n0)
    {
        if (amp_async) {                    // (the worker's answers so far)
            std::lock_guard<std::mutex> lk(amp_mu);
            while (!amp_ready_fast.empty()) {
                amp_out = amp_ready_fast.front();       // (the newest stands, as live's one amp_out)
                amp_ready_fast.pop_front();
                amp_has_out = true;
            }
            while (!amp_ready_fine.empty()) {
                if (amp_jid[amp_ready_fine.front().pid] == amp_ready_fine.front().jid)
                    amp_fine_results.push_back(amp_ready_fine.front());
                amp_ready_fine.pop_front();
            }
        }
        amp_released();
        if (amp_has_out) {
            AmpOut o = amp_out;
            amp_has_out = false;
            amp_busy = false;
            auto fp = amp_fine_placed.find(o.pid);
            if (amp_jid[o.pid] == o.jid && !(fp != amp_fine_placed.end() && fp->second == o.jid)) {
                amp_place(n0, o, amp_cross(o.pid, o.jid));
            }
        }
        while (!amp_fine_results.empty()) {
            AmpOut o = amp_fine_results.front();
            amp_fine_results.pop_front();
            if (amp_jid[o.pid] == o.jid) {
                amp_fine_placed[o.pid] = o.jid;
                amp_place(n0, o, amp_cross(o.pid, o.jid));
            }
        }
        if (!amp_dirty.empty() && !amp_busy) {
            long long apid = *amp_dirty.begin();
            amp_dirty.erase(amp_dirty.begin());
            AmpOut job;
            AmpJob jd;
            // (where it ends the products, if it does: at the changes it reads)
            long long nxt = amp_jid[apid] + 1;
            const Chg *e0 = nullptr;
            auto ch0 = amp_chg.find(apid);
            if (ch0 != amp_chg.end())
                for (const Chg &e : ch0->second)
                    if (e.jid0 < nxt && (!e0 || e.T < e0->T))
                        e0 = &e;
            amp_end = Cross();
            if (e0 && e0->T >= n0) {
                amp_end.has = true;
                amp_end.at = e0->T;
                amp_end.xf = e0->xf;
            }
            bool got = amp_snapshot(apid, n0, job, jd);
            amp_end = Cross();
            if (got) {
                job.jid = ++amp_jid[apid];
                amp_busy = true;
                if (amp_async) {
                    std::lock_guard<std::mutex> lk(amp_mu);
                    amp_jobdata[job.jid] = jd;
                    amp_jobs.push_back(job);
                    amp_cv.notify_all();
                } else {                    // in step: both passes now, placed at the next pump
                    amp_out = job;
                    amp_pass(jd, rate, false, amp_out.prod);
                    amp_has_out = true;
                    AmpOut fine = job;
                    amp_pass(jd, rate, true, fine.prod);
                    amp_fine_results.push_back(fine);
                }
            } else {
                amp_jid[apid] += 1;         // nothing to distort now
                amp_cross(apid, amp_jid[apid]);     // ...so nothing to wait for
            }
        }
        if (!amp_chg.empty())
            amp_hold_step(n0);
    }

    // live._amp_holds: a part whose chord changes wait for its valve
    bool amp_holds(int pi) const
    {
        return LIVE_AMP_HOLD && pi >= 0 && !patches[pi].drums && const_cast<Part *>(this)->valved(pi);
    }

    // live._amp_change: the chord changes at T -- a note's onset or its
    // release, crossing over its loudest row's attack or release
    void amp_change(long long apid, bool on, int ch, int note, const std::vector<long> &idx, long long T,
                    const float *col)
    {
        long src = idx[0];
        double best = 0.0;
        for (size_t q = 0; q < idx.size(); q++) {
            double v = (double)S.aL0[idx[q]] + (double)S.aR0[idx[q]];
            if (q == 0 || v > best) {
                best = v;
                src = idx[q];
            }
        }
        auto j = amp_jid.find(apid);
        amp_chg[apid].push_back(Chg{on, ch, note, idx, T, std::max(1.0, (double)col[src]),
                                    j == amp_jid.end() ? 0 : j->second, 0});
    }

    // live._amp_released: the slab's releases since the last pump -- a valve
    // part's note let go (its key, the pedal, a steal) is a change
    void amp_released()
    {
        if (S.rel_log.empty())
            return;
        std::vector<std::tuple<Key, long long, std::vector<long>>> log;
        log.swap(S.rel_log);
        for (auto &r : log) {
            const Key &k = std::get<0>(r);
            long long l = std::get<3>(k);
            if (l == AMPK || l >= AMP_OLD0)
                continue;
            int pi = patch_of_pid(std::get<0>(k));
            if (!amp_holds(pi))
                continue;
            auto kt = key_tone.find(Key(std::get<0>(k), std::get<1>(k), std::get<2>(k), 0));
            if (kt != key_tone.end() && kt->second != patches[pi].cache)
                continue;
            amp_change(std::get<0>(k), false, (int)std::get<1>(k), (int)std::get<2>(k), std::get<2>(r),
                       std::get<1>(r), S.f4[F4_re].data());
        }
    }

    // live._amp_held: how far this key's note was held back
    long long amp_held(long long apid, int ch, int note) const
    {
        auto h = amp_chg.find(apid);
        if (h != amp_chg.end())
            for (auto e = h->second.rbegin(); e != h->second.rend(); ++e)
                if (e->on && e->ch == ch && e->note == note)
                    return e->sh;
        auto s = amp_shifted.find(std::make_tuple(apid, ch, note));
        return s == amp_shifted.end() ? 0 : s->second;
    }

    void amp_play(long long apid, const std::vector<Chg> &ents)
    {
        for (const Chg &e : ents)
            if (e.on && e.sh)
                amp_shifted[std::make_tuple(apid, e.ch, e.note)] = e.sh;
    }

    // live._amp_cross: where job jid's products take over -- the earliest
    // change it covers -- once per job
    Cross amp_cross(long long apid, long long jid)
    {
        std::map<long long, Cross> &jt = amp_jobT[apid];
        auto f = jt.find(jid);
        if (f != jt.end())
            return f->second;
        for (auto j = jt.begin(); j != jt.end();)
            j = j->first < jid ? jt.erase(j) : std::next(j);
        Cross got;
        auto h = amp_chg.find(apid);
        if (h != amp_chg.end()) {
            std::vector<Chg> cov, keep;
            for (Chg &e : h->second)
                (e.jid0 < jid ? cov : keep).push_back(e);
            if (!cov.empty()) {
                const Chg *e0 = &cov[0];
                for (const Chg &e : cov)
                    if (e.T < e0->T)
                        e0 = &e;
                got.has = true;
                got.at = e0->T;
                got.xf = e0->xf;
                amp_play(apid, cov);
                if (keep.empty())
                    amp_chg.erase(h);
                else
                    h->second = keep;
            }
        }
        jt[jid] = got;
        return got;
    }

    // live._amp_hold_step: changes due within this block that no result
    // covers yet, a block later -- the part's together
    void amp_hold_step(long long n0)
    {
        long long blk = cur_blk;
        long long cap = (long long)(LIVE_AMP_HOLD_S * rate);
        for (auto h = amp_chg.begin(); h != amp_chg.end();) {
            std::vector<Chg> &chg = h->second;
            // a note let go before it began (its key up, the pedal up, its
            // tone changed): its onset has nothing to wait for; one cut and
            // reaped, gone
            int pi = patch_of_pid(h->first);
            std::vector<Chg> keep, gone;
            for (Chg &e : chg) {
                if (!e.on) {
                    keep.push_back(e);
                    continue;
                }
                bool ok = pi >= 0;
                for (long s : e.idx)
                    ok = ok && S.busy[s];
                if (ok) {
                    auto kt = key_tone.find(Key(h->first, e.ch, e.note, 0));
                    ok = kt == key_tone.end() || kt->second == patches[pi].cache;
                }
                if (ok) {
                    bool in = false;
                    for (auto &kv : S.live) {
                        if (std::get<0>(kv.first) != h->first || std::get<3>(kv.first) == AMPK)
                            continue;
                        for (long s : kv.second)
                            if (s == e.idx[0]) {
                                in = true;
                                break;
                            }
                        if (in)
                            break;
                    }
                    ok = in;
                }
                (ok ? keep : gone).push_back(e);
            }
            amp_play(h->first, gone);
            chg = keep;
            if (chg.empty()) {
                h = amp_chg.erase(h);
                continue;
            }
            long long on = chg[0].T, most = 0;
            for (Chg &e : chg) {
                on = std::min(on, e.T);
                most = std::max(most, e.sh);
            }
            if (on >= n0 + blk) {
                ++h;
                continue;
            }
            long long d = n0 + blk - on;
            if (most + d > cap) {
                amp_play(h->first, chg);
                h = amp_chg.erase(h);       // waited long enough: as they are
                continue;
            }
            for (Chg &e : chg) {
                if (e.on)
                    S.retime(e.idx, d);
                else
                    S.retime_off(e.idx, d);
                e.T += d;
                e.sh += d;
            }
            ++h;
        }
    }

    void leslie_block(long long n0, long long blk)
    {
        if (S.les.empty() || !S.any_leslie())
            return;
        double dt = (double)blk / rate;
        double ah = rotor_horn.advance(dt);
        double ad = rotor_drum.advance(dt);
        S.leslie_swing(ah, ad);
        if (fabs(rotor_horn.rate - ls_rate) > 0.05) {
            S.leslie_doppler(n0, rotor_horn.rate, rotor_drum.rate);
            ls_rate = rotor_horn.rate;
        }
    }
    // the organ's registration as live's Part starts it: its default stops,
    // or the crescendo's first where it has none
    static void organ_start(Patch &p, const OrganSpec *og)
    {
        const NoteClass *k = p.drums ? nullptr : nv_tcache_class(p.cache, p.program);
        p.leslie = k && k->leslie;
        p.wheel_swell = k && k->wheel_swell;
        p.touch = p.drums || !k || k->touch_sensitive;
        p.wtrem = og ? og->wheel_trem : (k ? k->trem_depth : 0.0);
        p.wtrem_hz = og ? og->wtrem_hz : (k ? k->trem_hz : 0.0);
        p.wtrem_stereo = og ? og->wtrem_stereo != 0 : (k && k->trem_stereo);
        p.amp0 = k ? k->amp_drive : 0.0;
        p.amp = p.drive >= 0.0 ? p.drive : p.amp0;
        p.amp_ref = k && k->amp_reference != 0.0 ? k->amp_reference * nv_tcache_trim(p.cache, p.program) : 0.0;
        p.amp_imb = k ? k->amp_imbalance : 0.06;
        p.cab = k && k->cab_set ? k : nullptr;
        p.scanner = k ? k->scanner : 0;
        p.clav = !p.drums && k && k->clav_panel;
        p.wheel_vib = !p.drums && k && k->wheel_vibrato;
        p.moog = !p.drums && k && k->init.kind == 6 && k->moog.n_layer >= 1 ? &k->moog.L[0] : nullptr;
        p.moog_b = p.moog && k->moog.n_layer >= 2 ? &k->moog.L[1] : nullptr;
        p.snd = !p.drums && k ? k->snd_mask : 0;
        p.organ = og;
        if (!og)
            return;
        p.drawn.assign(og->n_rank, 0);
        bool any = false;
        for (int i = 0; i < og->n_rank; i++)
            if ((og->default_stops >> i) & 1) {
                p.drawn[i] = 1;
                any = true;
            }
        if (!any && og->n_order)
            p.drawn[og->order[0]] = 1;
    }
    // each organ key's touch at its press (live.note_touch)
    std::map<std::pair<int, int>, double> note_touch;
    // a harpsichord's key down: the template it was stamped from, for its jacks' clicks (live's held_tmpl)
    std::map<Key, std::pair<const nv::live::Template *, const OrganSpec *>> held_jacks;   // ...and its organ
    std::map<Key, std::pair<const nv::live::Template *, double>> held_rel;  // live's held_tmpl: its key-up rows, its scale
    static const long long KEYUP_REL = 4999;    // the key-up's one-shot ((pid, ch, note, "keyup"))
    // THE CHEST'S WIND (live.wind_st, _wind_row, _wind_block): a part's, made
    // at its first rank drawn -- numpy's generator seeded by the part, the
    // pressure's state, a slab row a family of its ranks (from wind_next, to
    // WIND_ROWS), each rank's row (0 none) and each row's accrued phase
    struct WindSt {
        void *g = nullptr;
        const OrganSpec *og = nullptr;
        double w1 = 0, w2 = 0, s1 = 0, s2 = 0, d1 = 0, r1 = 0, te = 0, tph = 0;
        bool was_on = false;
        std::vector<std::pair<std::pair<double, double>, int>> rows;
        std::map<int, double> acc;
        int rank_row[32] = {0};
    };
    std::map<long long, WindSt> wind_st;
    std::vector<long long> wind_order;          // the parts' wind, in the order made
    int wind_next = 1;
    // ...and an old chest's rows (live's wind_spent, wind_free): spent until
    // no slot rides them, then free again, at rest
    std::vector<int> wind_spent;
    std::deque<int> wind_free;
    static const int WIND_ROWS = 32;
    static const long long RANK0 = 1000;        // a rank's slots: layer RANK0 + its stop name's id (rank_layer)
    static const long long SCAN0 = 2000;        // ...its scanner's copy (("scan", rank))
    static const long long SCANSIDE0 = 3000;    // ...and tier B's copies (("scanside", rank))
    static const long long AMPK = 4000;         // the valve's products ((pid, -1, -1, "amp"))
    static const long long KEYUP0 = 5000;       // a jack's key-up click ((pid, ch, note, "keyup:" + rank))
    static const long long DRONEK = 6000;       // a drone's layer ((pid, ch, -1 - i, "drone"))
    // THE DRONES (live's drone_count, drone_quiet): how many the wheel leaves
    // uncorked (absent: all), and when the chanter went quiet (its channel,
    // the sample, the hold: part_break_s)
    std::map<long long, int> drone_count;
    struct DroneQuiet {
        int ch;
        long long when, hold;
    };
    std::map<long long, DroneQuiet> drone_quiet;
    long misses = 0;                            // templates not warmed when asked (live.misses)

    const NoteClass *drone_class() const
    {
        const NoteClass *k = nv_tcache_class(patches[cur].cache, patches[cur].program);
        return (k && k->drone_wheel && !patches[cur].drums) ? k : nullptr;
    }

    // THE PUNGI's DRONE (live._drone_note): one note of the part, the
    // wheel's choice (drone_sel: its step), held across the line -- the old
    // one let go and the new stamped on the other of two keys where the
    // wheel has moved (dnote_at: the note sounding, dnote_k its key)
    std::map<long long, int> drone_sel, dnote_at, dnote_k;
    const NoteClass *dnote_class() const
    {
        const NoteClass *k = patches[cur].drums ? nullptr : nv_tcache_class(patches[cur].cache, patches[cur].program);
        return (k && k->n_dchoice) ? k : nullptr;
    }
    void drone_note(int ch, long long n0)
    {
        const NoteClass *k = dnote_class();
        const Patch &p = patches[cur];
        if (!k || !p.dcache)
            return;
        auto st = drone_sel.find(pid);
        int note = st != drone_sel.end() ? k->dchoice[st->second] : k->dchoice_def;
        auto ki = dnote_k.find(pid);
        int kk = ki != dnote_k.end() ? ki->second : -200;
        Key curk(pid, ch, kk, DRONEK);
        if (S.live_find(curk) >= 0) {
            auto at = dnote_at.find(pid);
            if (at != dnote_at.end() && at->second == note)
                return;
            S.release(curk, n0);
            kk = -401 - kk;                 // -200 <-> -201
        }
        int b = (int)(100 * p.dnb / 128.0);
        const nv::live::Template *T = nv_tcache_lookup(p.dcache, note, b < p.dnb - 1 ? b : p.dnb - 1, p.dspeed);
        if (!T) {
            misses++;
            return;
        }
        if (!S.stamp_t(*T, Key(pid, ch, kk, DRONEK), n0, (pow(10.0, level_db / 20.0) * swell) * chan_gain(ch), ch,
                       rate)) {
            dropped++;
            return;
        }
        dnote_at[pid] = note;
        dnote_k[pid] = kk;
    }

    // live._chanting: a chanter note sounding (the drones do not count themselves)
    bool chanting(int ch) const
    {
        for (auto &kv : S.live)
            if (std::get<0>(kv.first) == pid && std::get<1>(kv.first) == ch && std::get<3>(kv.first) != DRONEK)
                return true;
        return false;
    }

    // the partial nearest ref (Hz) of a template, as live finds a fundamental
    // (numpy on the float32 column: |log(max(nf, 1e-6) / ref)|, float32)
    static double nearest_nf(const nv::live::Template *T, double ref)
    {
        const std::vector<float> &nf = T->f4[2];
        long best = 0;
        float bv = INFINITY;
        for (long r = 0; r < T->P; r++) {
            float x = fabsf(logf(std::max(nf[r], 1e-6f) / (float)ref));
            if (x < bv) {
                bv = x;
                best = r;
            }
        }
        return (double)nf[best];
    }

    // live._tonic_hz: the tonic off its own template, times the channel's tuning
    double tonic_hz(const NoteClass *k, int ch)
    {
        int n = k->scale_n ? k->scale_tonic : -1;
        if (n < 0 || n > 127)
            return 0.0;
        const nv::live::Template *T = nv_tcache_lookup(patches[cur].cache, n, bucket(100), speed);
        if (!T || !T->P)
            return 0.0;
        double F = nv_tcache_freq(patches[cur].cache, n);
        double ref = F > 0.0 ? F : (double)*std::min_element(T->f4[2].begin(), T->f4[2].begin() + T->P);
        return nearest_nf(T, ref) * key_ratio(patches[cur], ch, n);
    }

    // live._drones: the uncorked drones up, the rest corked
    void drones(int ch, long long n0)
    {
        const NoteClass *k = drone_class();
        if (!k)
            return;
        auto dc = drone_count.find(pid);
        int want = dc != drone_count.end() ? dc->second : k->n_dratio;
        double tonic = tonic_hz(k, ch);
        if (tonic <= 0.0)
            return;
        for (int i = 0; i < k->n_dratio; i++) {
            double hz = tonic * k->drone_ratio[i];
            Key key(pid, ch, -1 - i, DRONEK);
            bool on = S.live_find(key) >= 0;
            if (i < want && !on) {
                int note = i < k->n_drone ? k->drone_note[i] : (int)nearbyint(69.0 + 12.0 * log2(hz / 440.0));
                if (note < 21 || note > 108)        // (MELODIC_RANGE)
                    continue;
                const nv::live::Template *T = nv_tcache_lookup(patches[cur].cache, note, bucket(100), speed);
                if (!T) {
                    misses++;
                    continue;
                }
                double g = k->drone_gain[i];
                if (!S.stamp_t(*T, key, n0, g * (pow(10.0, level_db / 20.0) * swell) * chan_gain(ch), ch, rate)) {
                    dropped++;
                    continue;
                }
                long li = S.live_find(key);
                double Fd = nv_tcache_freq(patches[cur].cache, note);
                double ref = Fd > 0.0 ? Fd : (double)*std::min_element(T->f4[2].begin(), T->f4[2].begin() + T->P);
                double f0 = nearest_nf(T, ref);
                if (li >= 0 && f0 > 0.0 && fabs(hz / f0 - 1.0) > 1e-9)
                    retune(S.live[li].second, n0, hz / f0);
            } else if (i >= want && on) {
                S.release(key, n0);
            }
        }
    }

    // live._drone_reap: the bag let down once the chanter has been quiet part_break_s
    void drone_reap(long long n0)
    {
        for (auto it = drone_quiet.begin(); it != drone_quiet.end();) {
            if (n0 - it->second.when < it->second.hold) {
                ++it;
                continue;
            }
            long long qp = it->first;
            it = drone_quiet.erase(it);
            std::vector<Key> ks;
            for (auto &kv : S.live)
                if (std::get<0>(kv.first) == qp && std::get<3>(kv.first) == DRONEK)
                    ks.push_back(kv.first);
            for (auto &kk : ks)
                S.release(kk, n0);
        }
    }
    int cur = 0, transpose = 0;
    bool cur_reg = true;                            // the patch in use has the register

    // does patch i take channel ch's key note (live's Part.matches)
    bool claims(int i, int ch, int note) const
    {
        const Patch &p = patches[i];
        return !p.muted && !p.gone && !p.hidden && (p.channel < 0 || p.channel == ch) && !((p.excl >> ch) & 1u)
               && p.lo <= note && note <= p.hi;
    }

    // the patch a note goes to: the one a layer's loop is on (force_pi), else
    // the last added that claims it
    int force_pi = -1;
    int patch_for(int ch, int note) const
    {
        if (force_pi >= 0)
            return force_pi;
        for (int i = (int)patches.size() - 1; i >= 0; i--)
            if (claims(i, ch, note))
                return i;
        return -1;
    }

    // EVERY PATCH THE KEY REACHES, in order (live's `for part in parts: if
    // part.matches`): a layer each -- and a Force puts the note on one of them
    std::vector<int> claimers(int ch, int note) const
    {
        std::vector<int> out;
        for (int i = 0; i < (int)patches.size(); i++)
            if (claims(i, ch, note))
                out.push_back(i);
        return out;
    }
    struct Force {
        Part &P;
        int was;
        Force(Part &P_, int i) : P(P_), was(P_.force_pi) { P.force_pi = i; }
        ~Force() { P.force_pi = was; }
    };

    void use(int i)
    {
        if (i == cur)
            return;
        if (cur == 0 && !patches.empty())
            patches[0].speed = speed;               // (the wheel's detune step, the piano's)
        const Patch &p = patches[i];
        cache = p.cache; pid = p.pid; level_db = p.level_db; nbuckets = p.nbuckets; speed = p.speed;
        damper_pedal = p.damper_pedal; soft_drop = p.soft_drop; soft_top = p.soft_top;
        drums = p.drums; program = p.program; cur_reg = p.reg; transpose = p.transpose;
        choke_p = &p.choke;
        cur = i;
    }

    // the patch a note takes, in use for a scope; the one before put back
    struct Use {
        Part &P;
        int was;
        Use(Part &P_, int i) : P(P_), was(P_.cur) { P.use(i); }
        ~Use() { P.use(was); }
    };
    const std::vector<unsigned long long> *choke_p = &choke;
    // LEGATO (live._legato_on): each channel's last onset group -- when it
    // began, its keys, its last key up, whether it was a slur -- a note
    // struck within CHORD_WINDOW_S of it a member, else slurred where one of
    // its keys is still down or the last went up within LEGATO_GAP_S
    struct Group {
        long long on = 0;
        std::set<std::pair<int, int>> keys;
        bool has_off = false;
        long long off = 0;
        bool slur = false;
    };
    std::map<int, Group> onset_group;
    double legato_gap_s = 0.015, chord_window_s = 0.030;    // live.LEGATO_GAP_S, CHORD_WINDOW_S

    Part(long cap) : S(cap)
    {
        pyr_seed(&tex_rng, 0x7E47);             // (live's _tex_rng)
        for (int t = 0; t < DAMP_TRACKS; t++) {
            free_tracks.push_back(t);
            DMO[t] = 2 * t;
        }
        for (int c = 0; c < 16; c++) {
            rpn_msb[c] = rpn_lsb[c] = 127;
            brange[c] = modrange[c] = -1.0;
            fine_msb[c] = 64;
        }
        for (int c = 0; c < 16; c++) {
            vol[c] = 100; expr[c] = 127; cpan[c] = 64; pedal_v[c] = 0;     // GM's power-on
            soft[c] = false; cgain[c] = 1.0; cgain_set[c] = false;
            stopword[c][0] = stopword[c][1] = stopword[c][2] = -1;
            nrpn_msb[c] = nrpn_lsb[c] = 127;
        }
    }

    int bucket(int vel) const
    {
        int b = (int)(vel * nbuckets / 128.0);
        return b < nbuckets - 1 ? b : nbuckets - 1;
    }

    double chan_gain(int ch) const { return pow((vol[ch] / 127.0) * (expr[ch] / 127.0), 2.0); }

    bool pedal_holds(int ch, int note) const
    {
        int v = pedal_v[ch];
        return v > 0 && nv_damper_contact(v, note, 128) < 1.0;
    }

    std::vector<long> sounding(int ch) const
    {
        std::vector<long> out;
        for (auto &kv : S.live)
            if (std::get<1>(kv.first) == ch)
                out.insert(out.end(), kv.second.begin(), kv.second.end());
        return out;
    }

    // live._sounding(ch, pids={ppid}, tone=...): ONE TONE's NOTES (key_tone) --
    // the part's current one takes the keys no note struck; an OLD one only its own
    std::vector<long> sounding_tone(int ch, long long ppid, const void *tone, bool old) const
    {
        std::vector<long> out;
        for (auto &kv : S.live) {
            const Key &k = kv.first;
            if (std::get<1>(k) != ch || std::get<0>(k) != ppid)
                continue;
            auto t = key_tone.find(Key(std::get<0>(k), std::get<1>(k), std::get<2>(k), 0));
            if (!(t != key_tone.end() ? t->second == tone : !old))
                continue;
            out.insert(out.end(), kv.second.begin(), kv.second.end());
        }
        return out;
    }

    // live._tone_wheel: THE MOD WHEEL ON NOTES HELD THROUGH A PROGRAM CHANGE --
    // each old tone's own tremolo (its voice's wheel role), on its own notes
    long long n0_wheel = 0;                 // (the block's, for tone_wheel's retune)
    void tone_wheel(int ch, int v, int jobs, bool routed)
    {
        for (size_t pi = 0; pi < patches.size(); pi++) {
            const Patch &p = patches[pi];
            if (!(p.channel < 0 || p.channel == ch))
                continue;
            int pj = jobs;
            if (routed)                             // (the route: a part's held tones take only the jobs its voice has)
                pj &= (p.wtrem > 0.0 ? 1 : 0) | (p.clav ? 2 : 0);
            if (!pj)
                continue;
            std::vector<const void *> olds;
            for (auto &kv : S.live) {
                const Key &k = kv.first;
                if (std::get<0>(k) != p.pid || std::get<1>(k) != ch)
                    continue;
                auto t = key_tone.find(Key(std::get<0>(k), std::get<1>(k), std::get<2>(k), 0));
                if (t != key_tone.end() && t->second != p.cache
                    && std::find(olds.begin(), olds.end(), t->second) == olds.end())
                    olds.push_back(t->second);
            }
            for (const void *tone : olds) {
                auto tp = tone_prog.find(tone);
                if (tp == tone_prog.end() || tp->second.second)
                    continue;                           // (a drum set's: no wheel)
                const NoteClass *k = nv_tcache_class((void *)tone, tp->second.first);
                const OrganSpec *og = nv_tcache_organ((void *)tone, tp->second.first);
                double dep = og ? og->wheel_trem : (k ? k->trem_depth : 0.0);
                bool st = og ? og->wtrem_stereo != 0 : (k && k->trem_stereo);
                bool clv = k && k->clav_panel;
                // (its wheel a vibrato where nothing else of that voice wants it: live.wheel_roles)
                bool vib = k && k->wheel_vibrato && !(k->amp_drive > 0.0) && !(og && og->n_order) && !(dep > 0.0)
                           && !clv && !k->leslie && !k->wheel_swell;
                dep = (pj & 1) ? dep : 0.0;
                clv = clv && (pj & 2);
                vib = vib && (pj & 4);
                if (dep <= 0.0 && !clv && !vib)
                    continue;
                std::vector<long> sl = sounding_tone(ch, p.pid, tone, true);
                if (sl.empty())
                    continue;
                if (dep > 0.0)
                    S.tremolo_arm(sl, v / 127.0 * dep, st);
                if (clv)
                    S.clav_tone((int)nearbyint(v / 127.0 * 4.0), sl);
                if (vib) {
                    double w = v / 127.0, cents = modrange[ch] >= 0.0 ? modrange[ch] : mod_cents;
                    retune_v(sl, n0_wheel, false, 1.0, true, pow(2.0, cents * w / 1200.0) - 1.0, true,
                             1.0 + mod_rate * w);
                }
            }
        }
    }

    // live._slur_cut: the notes a slurred one follows stop in the legato
    // time (max(retrigger fade, legato_attack_s)) -- a key still down before
    // it is let go, one let go this very block before its release has played
    void slur_cut(const std::set<std::pair<int, int>> &keys, long long n0)
    {
        for (auto &kn : keys)
            for (size_t pi = 0; pi < patches.size(); pi++) {
                const Patch &p = patches[pi];
                const NoteClass *pc = p.drums ? nullptr : nv_tcache_class_key(p.cache, p.program, kn.second + transpose);
                if (!pc || !pc->slur_cuts_release)
                    continue;
                float shrt = (float)(std::max(retrigger, pc->legato_set ? pc->legato_attack_s : 0.0) * rate);
                Key key(p.pid, kn.first, kn.second, -1);
                std::vector<long> idx;
                long li = S.live_find(key);
                if (li >= 0 && !S.live[li].second.empty())
                    idx = S.live[li].second;
                else {
                    auto lr = S.last_release.find(key);
                    if (lr == S.last_release.end() || lr->second.second < n0)
                        continue;
                    idx = lr->second.first;
                }
                for (long q : idx)
                    if (shrt < S.f4[F4_re][q])
                        S.f4[F4_re][q] = shrt;
            }
    }

    // a key down (live's note-on, before its parts): the key held, and in
    // MONO the voice handed over -- the note sounding cut, the new key on top
    // of the held stack
    bool legato_on(int ch, int note, long long n0)
    {
        auto it = onset_group.find(ch);
        if (it != onset_group.end() && (double)(n0 - it->second.on) <= chord_window_s * rate) {
            it->second.keys.insert(std::make_pair(ch, note));     // a chord member: the chord's answer
            return it->second.slur;
        }
        bool slur = false;
        if (it != onset_group.end()) {
            for (auto &k : it->second.keys)
                if (down.count(k))
                    slur = true;
            if (it->second.has_off && (double)(n0 - it->second.off) <= legato_gap_s * rate)
                slur = true;
        }
        if (slur)
            slur_cut(it->second.keys, n0);  // (live._slur_cut: a voice that says so stops the note it leaves)
        Group g;
        g.on = n0;
        g.keys.insert(std::make_pair(ch, note));
        g.slur = slur;
        onset_group[ch] = g;
        return slur;
    }

    void legato_off(int ch, int note, long long n0)
    {
        auto it = onset_group.find(ch);
        if (it != onset_group.end() && it->second.keys.count(std::make_pair(ch, note))) {
            Group &g = it->second;
            g.off = g.has_off ? std::max(g.off, n0) : n0;
            g.has_off = true;
        }
    }

    // THE UILLEANN CHANTER's CUT, live (live._cut_on, _cut_go, _cut_off):
    // the key opens a flick cut_semi above, held cut_s, and the written note
    // arrives from it by slur -- the chanter never stops. Live cannot know a
    // note's length, so every note is cut; a key let go in its flick ends there
    struct Cut {
        long long pid;
        int ch, cnote, note, vel;
        long long due;
    };
    std::vector<Cut> cutting;
    void cut_on(int ch, int note, int vel, long long n0, bool slur)
    {
        int pi = patch_for(ch, note);
        if (!open_ring.empty() && pi >= 0)
            open_ring_stop(pi, ch, note, n0);       // (a string an open one rings on: it stops)
        const NoteClass *k = nullptr;
        long long ppid = 0;
        if (pi >= 0) {
            const Patch &p = patches[pi];
            k = p.drums ? nullptr : nv_tcache_class(p.cache, p.program);
            ppid = p.pid;
        }
        const int cs = k ? k->cut_semi : 0;
        if (!cs || note + cs < 0 || note + cs > 127) {
            strike(ch, note, vel, n0, slur);
            return;
        }
        strike(ch, note + cs, vel, n0, slur);
        Cut c{ppid, ch, note + cs, note, vel, n0 + (long long)nearbyint(k->cut_s * rate)};
        auto it = std::find_if(cutting.begin(), cutting.end(),
                               [&](const Cut &x) { return x.pid == c.pid && x.ch == c.ch && x.cnote == c.cnote; });
        if (it != cutting.end())
            *it = c;                        // (a dict's key keeps its place)
        else
            cutting.push_back(c);
    }
    void cut_release(long long ppid, int ch, int cnote, long long n0)
    {
        std::vector<Key> ks;
        for (auto &kv : S.live)
            if (std::get<0>(kv.first) == ppid && std::get<1>(kv.first) == ch && std::get<2>(kv.first) == cnote)
                ks.push_back(kv.first);
        for (const Key &k : ks)
            S.release(k, n0);
    }
    // the flicks whose time is up give way to their notes, by slur
    void cut_go(long long n0)
    {
        std::vector<Cut> all = cutting;
        for (const Cut &c : all) {
            if (c.due > n0)
                continue;
            cutting.erase(std::find_if(cutting.begin(), cutting.end(), [&](const Cut &x) {
                return x.pid == c.pid && x.ch == c.ch && x.cnote == c.cnote;
            }));
            bool here = false;
            for (const Patch &p : patches)
                here = here || p.pid == c.pid;
            if (!here)
                continue;
            strike(c.ch, c.note, c.vel, n0, true);
            cut_release(c.pid, c.ch, c.cnote, n0);
        }
    }
    // a key up while its flick still sounds: the flick ends, and there is no
    // note to let go (true when that was so)
    // live._open_string: the patch's key as a palm-muted open string's -- its
    // string (-1: not one that rings on), and whether the key is that string's open pitch
    int open_string(int pi, int note, bool *open) const
    {
        *open = false;
        if (pi < 0)
            return -1;
        const Patch &p = patches[pi];
        const int sn = note + p.transpose;
        const NoteClass *k = p.drums || sn < 0 || sn > 127 ? nullptr : key_class(p, sn);
        if (!k || k->osr_n <= 0 || k->one_shot)
            return -1;
        int s = -1;
        for (int i = 0; i < k->osr_n; i++)          // (np.searchsorted, side right, less 1)
            if (k->osr_open[i] <= (double)sn)
                s = i;
        for (int i = 0; i < k->osr_n; i++)
            *open = *open || k->osr_open[i] == (double)sn;
        return s;
    }
    // live._open_ring_hold: a key up on a palm-muted open string -- held on
    // until that string sounds again or its cap after the onset; true where so
    bool open_ring_hold(int pi, int ch, int note)
    {
        bool open = false;
        const int s = open_string(pi, note, &open);
        if (s < 0 || !open)
            return false;
        const long long id = patches[pi].pid;
        long long on = LLONG_MAX;
        for (auto &kv : S.live)
            if (std::get<0>(kv.first) == id && std::get<1>(kv.first) == ch && std::get<2>(kv.first) == note)
                for (long q : kv.second)
                    on = std::min(on, (long long)S.i8[0][q]);
        if (on == LLONG_MAX)
            return false;
        const NoteClass *k = key_class(patches[pi], note + patches[pi].transpose);
        open_ring[std::make_tuple(id, ch, note)] = std::make_pair(s, on + (long long)nearbyint(k->osr_cap * rate));
        return true;
    }
    void open_ring_release(const std::tuple<long long, int, int> &rk, long long n0, bool fade)
    {
        const float fd = (float)(retrigger * rate);
        std::vector<Key> ks;
        for (auto &kv : S.live)
            if (std::get<0>(kv.first) == std::get<0>(rk) && std::get<1>(kv.first) == std::get<1>(rk)
                && std::get<2>(kv.first) == std::get<2>(rk))
                ks.push_back(kv.first);
        for (const Key &k : ks) {
            long li = S.live_find(k);
            if (fade && li >= 0)
                for (long q : S.live[li].second)
                    if (fd < S.f4[F4_re][q])
                        S.f4[F4_re][q] = fd;
            S.release(k, n0);
        }
    }
    // live._open_ring_stop: a note on a string an open one rings on stops it now, in the steal fade
    void open_ring_stop(int pi, int ch, int note, long long n0)
    {
        bool open = false;
        const int s = open_string(pi, note, &open);
        if (s < 0)
            return;
        const long long id = patches[pi].pid;
        std::vector<std::tuple<long long, int, int>> gone;
        for (auto &kv : open_ring)
            if (std::get<0>(kv.first) == id && std::get<1>(kv.first) == ch && kv.second.first == s)
                gone.push_back(kv.first);
        for (auto &rk : gone) {
            open_ring.erase(rk);
            open_ring_release(rk, n0, true);
        }
    }
    // live._open_ring_tick: those whose cap has come let go, their own release
    void open_ring_tick(long long n0)
    {
        std::vector<std::tuple<long long, int, int>> gone;
        for (auto &kv : open_ring)
            if (kv.second.second <= n0)
                gone.push_back(kv.first);
        for (auto &rk : gone) {
            open_ring.erase(rk);
            open_ring_release(rk, n0, false);
        }
    }

    bool cut_off(int ch, int note, long long n0)
    {
        int pi = patch_for(ch, note);
        if (pi < 0 || cutting.empty())
            return false;
        const long long ppid = patches[pi].pid;
        bool hit = false;
        for (size_t i = 0; i < cutting.size();) {
            if (cutting[i].pid == ppid && cutting[i].ch == ch && cutting[i].note == note) {
                Cut c = cutting[i];
                cutting.erase(cutting.begin() + i);
                cut_release(c.pid, c.ch, c.cnote, n0);
                hit = true;
            } else {
                i++;
            }
        }
        return hit;
    }

    void note_on(int ch, int note, int vel, long long n0)
    {
        bool slur = legato_on(ch, note, n0);
        down.insert(std::make_pair(ch, note));
        pedalled.erase(std::make_pair(ch, note));
        if (mono[ch]) {
            std::vector<std::pair<int, int>> &st = mono_stack[ch];
            std::vector<std::pair<int, int>> keep;
            for (auto &x : st)
                if (x.first != note)
                    keep.push_back(x);
            keep.push_back(std::make_pair(note, vel));
            st.swap(keep);
            int prev = mono_cur[ch];
            if (prev >= 0 && prev != note) {
                legato_take(ch, prev);
                mono_cut(ch, prev, n0);
                slur = true;                    // a handoff is a slur (_MONO_SLUR)
            }
            mono_cur[ch] = note;
        }
        // WHERE IT GLIDES FROM: a pending CC84, spent, else under CC65 the
        // last note to have started
        int src = porta_src[ch];
        porta_src[ch] = -1;
        if (src < 0 && porta_on[ch])
            src = last_on[ch];
        glide_from = src != note ? src : -1;
        // A MOOG'S GLIDE needs no switch: with its knob up every note glides
        // from the last one on the channel, detached or not
        moog_src = last_on[ch] != note ? last_on[ch] : -1;
        last_on[ch] = note;
        std::vector<int> cl = claimers(ch, note);
        if (cl.size() <= 1)
            cut_on(ch, note, vel, n0, slur);
        else
            for (int i : cl) {
                Force f(*this, i);
                cut_on(ch, note, vel, n0, slur);
            }
        glide_from = moog_src = -1;
        legato_age.clear();
    }

    // live._legato_take: a mono handoff from `note` -- where each Moog part's
    // contours have got to (its note's onset and age, per layer), for the note
    // taking over, which carries on from there where MULTI-TRIG is off
    std::map<std::pair<long long, int>, int> legato_age;
    void legato_take(int ch, int note)
    {
        legato_age.clear();
        for (auto &kv : S.live) {
            if (std::get<1>(kv.first) != ch || std::get<2>(kv.first) != note || kv.second.empty())
                continue;
            for (long i : kv.second) {
                const int r = S.i4[I4_fx][i];
                if (r >= 0)
                    legato_age.emplace(std::make_pair((long long)std::get<0>(kv.first), S.ft_layer[r]), r);
            }
        }
    }

    // the chain channel ch hears now (live._efx_for), NULL where none
    const double *efx_chain(int ch, int *st, const char **why)
    {
        const double *fc = nv_efx_live_chain(efx, ch, st, why);
        return fc;
    }

    // THE MODULE's MOVING FILTERS on a chain (live._filter_for): a
    // flanger's comb (a chorus device with feedback), a tremolo or auto pan
    static bool efx_moves(const double *fc)
    {
        return fc[50] != 0.0 || (fc[14] != 0.0 && fc[18] != 0.0) || fc[55] != 0.0;
    }

    // THE INSERTION EFFECT on a note just stamped (live._efx_note, its
    // _efx_direct): its level, its EQ at each partial's frequency, the chorus's
    // dry share -- a gain a slot on every baseline (channel_gain); then its
    // moving filters arm the rows
    // ...a tone's own chain (its effect channel's), as efx_chain takes it
    const double *tone_chain(const ToneFx &tf, int *st, const char **why, bool virt = false)
    {
        const double *fc = tf.ex ? nv_efx_live_chain(tf.ex, tf.ch + (virt ? VIRT : 0), st, why) : nullptr;
        return fc;
    }

    const double *efx_note(int ch, int note, int vel, long long n0, const std::vector<long> &slots, int *ecp)
    {
        // THE MODULE's, where the part is on it; else THE TONE's OWN on its
        // effect channel (live._tone_fx) -- and the tone's plunger or mouth
        // arms its rows there either way, after the level
        int st = -1;
        const char *why = "";
        const double *fc = efx ? efx_chain(ch, &st, &why) : nullptr;
        const int fxc = tone_fx_of(ch, n0);
        if (fxc >= 0)
            for (long s : slots)
                S.fx_chs[s] = fxc;
        int ec = ch;
        if (st != 0 && st != -3 && fxc >= 0 && tone_fx[fxc].ex) {
            fc = tone_chain(tone_fx[fxc], &st, &why);
            ec = fxc;
        }
        if (st == -3 && !efx_said) {
            fprintf(stderr, "nvlive: refused: the insertion effect's %s -- played without it\n", why);
            efx_said = true;
        }
        if (fxc >= 0 && (ec != fxc || !fc) && tone_fx[fxc].kind)
            S.filter_arm(slots, fxc);
        *ecp = ec;
        if (!fc)
            return nullptr;
        efx_direct(fc, ec, note, vel, n0, slots, ec == fxc && tone_fx[fxc].kind, cpan[ch]);
        return fc;
    }

    // ---- THE COPIES AS TAPS (live._tap_list, _tap_tables, _tap_arm) ----
    // live._side_cc: an output's side as a CC10 on the +-30 degree stage --
    // the record's codes: 0 'l', 1 'r', 2 'c', 100 + v a pan (v), 300/301
    // the 3D Delay's -60/+60 degrees
    static int side_cc(int code)
    {
        if (code == 0)
            return 0;
        if (code == 1)
            return 127;
        if (code >= 100 && code < 300)
            return code - 100;
        if (code == 300 || code == 301)
            return pan_cc(std::max(-1.0, std::min(1.0, (code == 300 ? -60.0 : 60.0) / 30.0)));
        return 64;                          // (T.GM_DEFAULT_PAN)
    }
    static int pan_cc(double x)             // (a pan -1..1, as _side_cc rounds it)
    {
        return (int)nearbyint(64 + 63 * std::max(-1.0, std::min(1.0, x)));
    }
    struct Tap {
        long long D;
        double g, fc, r, hz;
        int cc;                             // its side's CC10
        double vd, vr, ph;                  // its LFO (vd < 0: none)
    };
    // the chain's copies, partial-independent (live._tap_list): the delay's
    // taps and their repeats (gsdelay's law, REPEAT_FLOOR), the chorus's
    // voices (chorus.gs_copies', EFX_CF_PASSES 1) where it is no comb
    std::vector<Tap> tap_list(const double *fc) const
    {
        std::vector<Tap> out;
        const double REPEAT_FLOOR = pow(10.0, -60.0 / 20.0);
        const double *Dv = fc[34] == 1.0 ? fc + 35 : fc[34] == 2.0 ? fc + 96 : nullptr;
        if (fc[34] == 3.0) {
            // a KEYBOARD MULTI's (gsefx._keyboard_multi, as prepare unrolls it):
            // every path through its ring modulator, pitch shifter and delay a
            // tap at the centre -- its ratio, and the modulator's Hz times it
            const double fm = fc[161], rd = fc[162], rw = fc[163], pd = fc[164], pw = fc[165], ra = fc[166];
            const double base = fc[167];
            std::vector<std::pair<double, double>> reps = {{0.0, 1.0}};
            if (fc[160] != 0.0) {
                const double t = fc[38], dfb = fc[36];
                for (int q = 0; q < 64; q++) {
                    double l = fc[35] * pow(dfb, (double)q);
                    if (l < 1e-3)
                        break;
                    reps.push_back(std::make_pair((q + 1) * t, l));
                }
            }
            const double rm[3][2] = {{rd, 0.0}, {0.5 * rw, fm}, {0.5 * rw, -fm}};
            const double ps[2][2] = {{pd, 1.0}, {pw, ra}};
            for (const auto &a : rm)
                for (const auto &b : ps)
                    for (const auto &rp : reps) {
                        if (a[1] == 0.0 && b[1] == 1.0 && rp.first == 0.0)
                            continue;               // (the part itself)
                        const double l = a[0] * b[0] * rp.second / base;
                        if (l > 1e-4 && fabs(l) >= REPEAT_FLOOR)
                            out.push_back(Tap{(long long)nearbyint(rp.first * rate), l, 0.0, b[1], a[1] * b[1],
                                              side_cc(2), -1.0, 0.0, 0.0});
                    }
        }
        if (Dv) {
            const bool cross = fc[34] == 2.0 && fc[121] != 0.0;
            const double *mod = fc[34] == 2.0 && fc[122] != 0.0 ? fc + 122 : nullptr;
            const double level = Dv[0], fb = Dv[1], lpf = Dv[2];
            const int ntap = (int)Dv[4];
            for (int t = 0; t < ntap; t++) {
                const double *T = Dv + 5 + 5 * t;
                const double tau = T[0], lv = T[1], period = T[3], shift = T[4];
                const int side = (int)T[2];
                for (int k = 0; k < 64; k++) {              // (gsdelay.MAX_REPEATS)
                    if (k && fb == 0.0)
                        break;
                    const double g = level * lv * (k ? pow(fb, (double)k) : 1.0);
                    if (fabs(g) < REPEAT_FLOOR)
                        break;
                    const int sd = cross && (k % 2) && side <= 1 ? 1 - side : side;
                    Tap tp{(long long)nearbyint((tau + k * period) * rate), g, lpf, pow(shift, (double)(k + 1)), 0.0,
                           side_cc(sd), -1.0, 0.0, 0.0};
                    if (mod) {
                        const double mr = mod[0], mswing = mod[1], mph = mod[2];
                        tp.vd = std::min(0.5, 2.0 * M_PI * mr * mswing);
                        tp.vr = mr;
                        tp.ph = sd == 1 ? mph : 0.0;
                    }
                    out.push_back(tp);
                }
            }
        }
        if (fc[14] != 0.0 && fc[18] == 0.0) {
            const double a = fc[20], sh = fc[21] >= 0.0 ? fc[21] : a * a / (1.0 + a * a);
            if (sh > 0.0) {
                const double tau = fc[15], crate = fc[16], cvd = fc[17], fb = fc[18], lpf = fc[19];
                const double fb2 = pow(fb, 2.0);
                const double passes = fb2 < 1.0 ? (1.0 - pow(fb2, 16.0)) / (1.0 - fb2) : 16.0;   // (GS_MAX_PASSES)
                // its voices (side CC10, LFO phase, extra delay s, depth factor): the
                // Hexa Chorus's six, the 3D Chorus's two, else left and right at its phase
                std::vector<std::array<double, 4>> taps;
                if (fc[87] == 1.0) {
                    const double pd = fc[88] / 20.0, dd = fc[89], dv = (fc[90] - 0x40) / 20.0;
                    for (int k = 0; k < 6; k++)
                        taps.push_back({(double)pan_cc(pd * (2.0 * k / 5.0 - 1.0)), 2.0 * M_PI * k / 6.0,
                                        0.5 * dd * (k / 5.0 - 0.5) / 1000.0,
                                        std::max(0.0, 1.0 + dv * (k / 5.0 - 0.5))});
                } else if (fc[87] == 2.0) {
                    taps.push_back({(double)pan_cc(-60.0 / 30.0), 0.0, 0.0, 1.0});
                    taps.push_back({(double)pan_cc(60.0 / 30.0), M_PI, 0.0, 1.0});
                } else {
                    taps.push_back({0.0, 0.0, 0.0, 1.0});
                    taps.push_back({127.0, fc[31], 0.0, 1.0});
                }
                const double wet = pow(sh / (double)taps.size() / passes, 0.5);
                for (const auto &tv : taps) {
                    const int k = 1;
                    const double g = wet * pow(fb, (double)(k - 1));
                    if (fabs(g) < 0.02 * 0.5)               // (chorus.FLOOR)
                        continue;
                    out.push_back(Tap{(long long)nearbyint((k * tau + tv[2]) * rate), g, lpf, 1.0, 0.0, (int)tv[0],
                                      std::min(0.5, k * cvd * tv[3]), crate, tv[1]});
                }
            }
        }
        return out;
    }

    // live._efx_chans, sorted: the module's parts on it and the tones' own
    // effect channels -- and a parallel type's branch B of each (c + VIRT)
    std::vector<int> efx_chans()
    {
        std::set<int> c;
        if (efx) {
            int pl[64];
            int n = nv_efx_live_part_list(efx, pl, 64);
            for (int i = 0; i < n && i < 64; i++)
                c.insert(pl[i]);
        }
        for (const auto &kv : tone_fx)
            c.insert(kv.first);
        std::vector<int> base(c.begin(), c.end());
        for (int b : base) {
            const double *ex = efx_for(b);
            if (ex && ex[208] != 0.0)
                c.insert(b + VIRT);
        }
        return std::vector<int>(c.begin(), c.end());
    }
    // ...the chain channel c hears (live._efx_for): its tone's own, or the
    // module's -- a virtual channel (c + VIRT) the branch B of its part's
    const double *efx_for(int c)
    {
        int st = -1;
        const char *why = "";
        const int base = c % VIRT;
        if (base >= TONE_SEG) {
            auto it = tone_fx.find(base);
            return it != tone_fx.end() ? tone_chain(it->second, &st, &why, c >= VIRT) : nullptr;
        }
        return efx ? efx_chain(c, &st, &why) : nullptr;
    }

    // live._tap_tables: the tap sets, one an effect channel, flattened --
    // rebuilt when the effect, its parts, the tones' channels or a part's
    // pan has moved; loudest first in each set, so a capped block keeps the
    // loudest
    void tap_tables()
    {
        std::vector<int> chans = efx_chans();
        std::set<int> pcs;
        for (int c : chans)
            pcs.insert(c % TONE_SEG);
        std::vector<long long> key{efx ? nv_efx_live_rev(efx) : -1, (long long)chans.size()};
        key.insert(key.end(), chans.begin(), chans.end());
        for (int pc : pcs)
            key.push_back(pc < 16 ? cpan[pc] : 64);
        if (tap_keyed && key == tap_key)
            return;
        tap_keyed = true;
        tap_key = key;
        auto clamp = [](int v) { return v < 0 ? 0 : v > 127 ? 127 : v; };
        const int NS = std::max(1, (int)chans.size());
        tap_sid.clear();
        for (size_t i = 0; i < chans.size(); i++)
            tap_sid[chans[i]] = (int)i;
        std::unique_ptr<TapTab> t(new TapTab);
        t->ts.assign(NS + 1, 0);
        t->eqo.assign(NS, -1);
        t->nmid.assign(NS, 0);
        t->dry.assign(NS, 1.0);
        t->al0.assign(NS, 0.0);
        t->ar0.assign(NS, 0.0);
        t->dmax.assign(NS, 0);
        int n = 0;
        for (int i = 0; i < NS; i++) {
            t->ts[i] = n;
            const double *fc = i < (int)chans.size() ? efx_for(chans[i]) : nullptr;
            if (!fc)
                continue;
            const int pc = chans[i] % TONE_SEG;
            const double *p0 = S.pan_tab[clamp(pc < 16 ? cpan[pc] : 64)];
            t->al0[i] = p0[0];
            t->ar0[i] = p0[1];
            if (fc[14] != 0.0 && fc[18] == 0.0) {
                const double a = fc[20], sh = fc[21] >= 0.0 ? fc[21] : a * a / (1.0 + a * a);
                t->dry[i] = pow(1.0 - sh, 0.5);
            }
            if (fc[6] != 0.0) {
                // (lo, hi, their corners, then each mid (Hz, Q, dB), "or" as live's)
                std::vector<std::array<double, 3>> mids{{fc[8], fc[9], fc[10]}};
                for (int j = 0; j < (int)fc[62]; j++)
                    mids.push_back({fc[63 + 3 * j], fc[64 + 3 * j], fc[65 + 3 * j]});
                t->eqo[i] = (int)t->eq.size();
                t->nmid[i] = (int)mids.size();
                t->eq.insert(t->eq.end(), {fc[7], fc[11], fc[60] != 0.0 ? fc[60] : 400.0, fc[61] != 0.0 ? fc[61] : 4000.0});
                for (const auto &m : mids)
                    t->eq.insert(t->eq.end(), {m[0] != 0.0 ? m[0] : 0.0, m[1] != 0.0 ? m[1] : 1.0, m[2] != 0.0 ? m[2] : 0.0});
            }
            std::vector<Tap> taps = tap_list(fc);
            std::stable_sort(taps.begin(), taps.end(), [](const Tap &x, const Tap &y) { return -fabs(x.g) < -fabs(y.g); });
            for (const Tap &tp : taps) {
                const double *p1 = S.pan_tab[clamp(tp.cc)];
                t->D.push_back(tp.D);
                t->g.push_back(tp.g);
                t->fc.push_back(tp.fc);
                t->r.push_back(tp.r);
                t->hz.push_back(tp.hz);
                t->al1.push_back(p1[0]);
                t->ar1.push_back(p1[1]);
                t->dl.push_back((p1[2] - p0[2]) * rate);
                t->vd.push_back(tp.vd);
                t->vr.push_back(tp.vr);
                t->ph.push_back(tp.ph);
                t->dmax[i] = std::max(t->dmax[i], (int64_t)tp.D);
                n++;
            }
        }
        t->ts[NS] = n;
        if (!n) {
            tap_tab.reset();
            S.tap_on = false;
            return;
        }
        if (t->eq.empty())
            t->eq.push_back(0.0);
        tap_tab = std::move(t);
        S.tap_on = true;
    }

    // live._tap_arm: these slots on channel ec's tap set, if it has taps
    void tap_arm(int ec, const std::vector<long> &slots)
    {
        auto it = tap_sid.find(ec);
        if (!tap_tab || it == tap_sid.end() || tap_tab->ts[it->second + 1] <= tap_tab->ts[it->second])
            return;
        for (long s : slots) {
            S.tp[s] = it->second;
            S.tpx[s] = tap_tab->dmax[it->second];
        }
    }

    // Slab.tap_fill: every partial with a tap set written once a tap into
    // the scratch rows, from the partial as it now stands (tap_expand) --
    // tap_m the rows the renderers add; rows left from a busier block idle
    // a slot on this block's bus (its channel, or its tone's effect channel)
    bool on_bus(long q) const
    {
        return !S.bus_chans.empty() && (S.bus_chans.count(S.slot_ch[q]) || S.bus_chans.count(S.fx_chs[q]));
    }

    // tapkernel's columns (every kernel column but those it writes itself)
    void tap_cols()
    {
        if (!tap_colp.empty())
            return;
        auto add = [&](void *p, int sz) {
            tap_colp.push_back(p);
            tap_colsz.push_back(sz);
        };
        for (int c : {F8_fmw, F8_fmp, F8_fmpR})
            add(S.f8[c].data(), 8);
        for (int c = 0; c < NF4; c++)
            if (c != F4_aL && c != F4_aR && c != F4_nf && c != F4_vd && c != F4_vr && c != 21
                && c != F4_delL && c != F4_delR)
                add(S.f4[c].data(), 4);
        for (int c = 0; c < 3; c++)
            add(S.f4n[c].data(), 4);
        for (int c : {(int)I4_cr, 3, (int)I4_mk})
            add(S.i4[c].data(), 4);
        add(S.sw.data(), 4);
        add(S.aLp.data(), 4);
        add(S.aRp.data(), 4);
        add(S.dk.data(), 4);
        add(S.dg.data(), 4);
    }

    // tap_expand over src's slots and their sets (tab's), into the scratch rows
    // from dst0 (cap of them): how many rows it wrote
    long expand(const std::vector<int64_t> &src, const std::vector<int32_t> &set, const TapTab &T, long dst0,
                long cap, double floor, long long n0, long long frames, int identity, long long ucap,
                int64_t *units)
    {
        tap_cols();
        return tap_expand((int)tap_colp.size(), tap_colp.data(), tap_colsz.data(), (int)src.size(), src.data(),
                          set.data(), S.f8[F8_om].data(), S.f8[F8_p0].data(), S.f8[F8_p0R].data(),
                          (int64_t *)S.i8[0].data(), (int64_t *)S.i8[1].data(), S.f4[F4_nf].data(),
                          S.f4[F4_aL].data(), S.f4[F4_aR].data(), S.f4[F4_vd].data(), S.f4[F4_vr].data(),
                          S.f4[21].data(), S.f4n[3].data(), S.f4[F4_delL].data(), S.f4[F4_delR].data(),
                          S.i4[I4_fx].data(), S.i4[I4_gr].data(), S.i4[I4_br].data(), T.ts.data(), T.eq.data(),
                          T.eqo.data(), T.nmid.data(), T.dry.data(), T.al0.data(), T.ar0.data(), T.D.data(),
                          T.g.data(), T.fc.data(), T.r.data(), T.hz.data(), T.al1.data(), T.ar1.data(),
                          T.dl.data(), T.vd.data(), T.vr.data(), T.ph.data(), S.f4[F4_re].data(), floor, n0,
                          n0 + frames, S.pan_beta, rate, IDLE, dst0, (int)cap, identity, Slab::TAP_MOOG_COST,
                          ucap, units);
    }

    // ---- A PART'S OWN BUS (live._bus_owner, _bus_block, Slab.bus_fill) ----
    void *bus_cn = nullptr, *bus_cp = nullptr, *bus_cf = nullptr;     // (convolver.c's: the reverbs')
    void *busp = nullptr, *busps = nullptr;     // the mix's processor, the send's (made at its first use)
    std::vector<double> bus_key;
    const double *bus_fc = nullptr;
    // live._bus_owner: the bus this block -- the effect's parts when its type
    // has one, else a tone's own with notes sounding on its effect channel
    const double *bus_owner(std::set<int> &chans)
    {
        chans.clear();
        if (efx && nv_efx_live_parts(efx)) {
            int pl[64];
            int n = std::min(64, nv_efx_live_part_list(efx, pl, 64));
            std::sort(pl, pl + n);
            for (int i = 0; i < n; i++) {
                const double *fc = efx_for(pl[i]);
                if (fc) {
                    if (fc[25] == 0.0)
                        return nullptr;
                    chans.insert(pl, pl + n);
                    return fc;
                }
            }
        }
        for (auto &kv : tone_fx) {
            const double *fc = efx_for(kv.first);
            if (!fc || fc[25] == 0.0)
                continue;
            for (long q = 0; q < S.cap; q++)
                if (S.busy[q] && S.fx_chs[q] == kv.first) {
                    chans.insert(kv.first);
                    return fc;
                }
        }
        return nullptr;
    }

    // live._bus_block: the processor rebuilt only when the setting changes,
    // the bus parts' partials (and their valve's products) into the rows
    void bus_block(long long n0, long long frames)
    {
        std::set<int> chans;
        const double *fc = bus_owner(chans);
        std::vector<double> key;
        if (fc) {
            key.assign(fc + 25, fc + 34);
            if (fc[25] == 6.0)
                key.insert(key.end(), fc + 176, fc + 203);
            key.push_back((double)frames);
        }
        if (key != bus_key) {
            if (busp)
                nv_livebus_free(busp);
            if (busps)
                nv_livebus_free(busps);
            busp = busps = nullptr;
            if (fc)
                busp = nv_livebus_new(fc, rate, (int)frames, bus_cn, bus_cp, bus_cf);
            bus_key = key;
        }
        bus_fc = busp ? fc : nullptr;
        if (!busp) {
            bus_fill(std::set<int>(), n0, frames, std::vector<long>());
            return;
        }
        std::vector<long> extra;                // the bus parts' valve products (no channel of their own)
        std::set<int> parts;                    // (gsefx.part_of: a mix channel's part)
        for (int c : chans)
            parts.insert((c % (1 << 16)) % TONE_SEG);
        for (const Patch &p : patches)
            if (p.channel < 0 || parts.count(p.channel)) {
                long j = S.live_find(Key(p.pid, -1, -1, AMPK));
                if (j >= 0)
                    extra.insert(extra.end(), S.live[j].second.begin(), S.live[j].second.end());
            }
        bus_fill(chans, n0, frames, extra);
    }

    // live.Slab.bus_fill: an identity copy of each bus partial (no delay,
    // unit gain, its own place) after the taps' rows, then their own copies
    void bus_fill(const std::set<int> &chans, long long n0, long long frames, const std::vector<long> &extra)
    {
        const long prev = S.bus_m;
        S.bus_m = 0;
        S.bus_hide.clear();
        if (!chans.empty()) {
            std::vector<char> m(S.cap, 0);
            for (long q = 0; q < S.cap; q++)
                m[q] = S.busy[q] && (chans.count(S.slot_ch[q]) || chans.count(S.fx_chs[q]));
            for (long e : extra)
                if (e >= 0 && e < S.cap)
                    m[e] = S.busy[e] != 0;
            std::vector<int64_t> src;
            for (long q = 0; q < S.cap; q++)
                if (m[q])
                    src.push_back(q);
            if (!src.empty()) {
                static TapTab ID;
                if (ID.ts.empty()) {
                    ID.ts = {0, 1}; ID.eq = {0.0}; ID.eqo = {-1}; ID.nmid = {0}; ID.dry = {1.0};
                    ID.al0 = {1.0}; ID.ar0 = {1.0}; ID.D = {0}; ID.g = {1.0}; ID.fc = {0.0}; ID.r = {1.0};
                    ID.hz = {0.0}; ID.al1 = {1.0}; ID.ar1 = {1.0}; ID.dl = {0.0}; ID.vd = {-1.0}; ID.vr = {0.0};
                    ID.ph = {0.0};
                }
                int64_t units = 0;
                const long d0 = S.cap + S.tap_m;
                std::vector<int32_t> zero(src.size(), 0);
                S.bus_m = expand(src, zero, ID, d0, S.tcap - S.tap_m, 0.0, n0, frames, 1, (long long)1 << 62,
                                 &units);
                S.bus_hide.assign(src.begin(), src.end());
                // THE BUS PARTS' COPIES (the effect's delays, chorus, shifters), after them
                if (tap_tab) {
                    std::vector<int64_t> ts;
                    std::vector<int32_t> tset;
                    for (long q = 0; q < S.cap; q++)
                        if (S.tp[q] >= 0 && (chans.count(S.slot_ch[q]) || chans.count(S.fx_chs[q]))) {
                            ts.push_back(q);
                            tset.push_back(S.tp[q]);
                        }
                    if (!ts.empty())
                        S.bus_m += expand(ts, tset, *tap_tab, d0 + S.bus_m, S.tcap - S.tap_m - S.bus_m,
                                          pow(10.0, -60.0 / 20.0), n0, frames, 0, S.tap_cap, &units);
                }
            }
        }
        if (S.bus_m < prev)
            for (long q = S.cap + S.tap_m + S.bus_m; q < S.cap + S.tap_m + prev; q++)
                S.i8[0][q] = IDLE;
    }

    void tap_fill(long long n0, long long frames)
    {
        long m = 0;
        int64_t units = 0;
        if (tap_tab) {
            std::vector<int64_t> src;
            std::vector<int32_t> set;
            for (long q = 0; q < S.cap; q++)
                if (S.tp[q] >= 0 && !on_bus(q)) {
                    src.push_back(q);
                    set.push_back(S.tp[q]);
                }
            if (!src.empty()) {
                tap_cols();
                const TapTab &T = *tap_tab;
                m = tap_expand((int)tap_colp.size(), tap_colp.data(), tap_colsz.data(), (int)src.size(), src.data(),
                               set.data(), S.f8[F8_om].data(), S.f8[F8_p0].data(), S.f8[F8_p0R].data(),
                               (int64_t *)S.i8[0].data(), (int64_t *)S.i8[1].data(), S.f4[F4_nf].data(),
                               S.f4[F4_aL].data(), S.f4[F4_aR].data(), S.f4[F4_vd].data(), S.f4[F4_vr].data(),
                               S.f4[21].data(), S.f4n[3].data(), S.f4[F4_delL].data(), S.f4[F4_delR].data(),
                               S.i4[I4_fx].data(), S.i4[I4_gr].data(), S.i4[I4_br].data(), T.ts.data(), T.eq.data(),
                               T.eqo.data(), T.nmid.data(), T.dry.data(), T.al0.data(), T.ar0.data(), T.D.data(),
                               T.g.data(), T.fc.data(), T.r.data(), T.hz.data(), T.al1.data(), T.ar1.data(),
                               T.dl.data(), T.vd.data(), T.vr.data(), T.ph.data(), S.f4[F4_re].data(),
                               pow(10.0, -60.0 / 20.0), n0, n0 + frames, S.pan_beta, rate, IDLE, S.cap,
                               (int)S.tcap, 0, Slab::TAP_MOOG_COST, S.tap_cap, &units);
            }
        }
        S.tap_u = m ? units : 0;
        for (long q = S.cap + m; q < S.cap + S.tap_m; q++)
            S.i8[0][q] = IDLE;
        S.tap_m = m;
    }

    // live's callback, after the moving filters and the Moog's under them:
    // the tap sets as they stand, then this block's copies
    void tap_block(long long n0, long long frames)
    {
        if ((efx && nv_efx_live_parts(efx)) || !tone_fx.empty() || S.tap_m) {
            tap_tables();
            bus_owner(S.bus_chans);
            tap_fill(n0, frames);
        }
    }

    // live._efx_direct: a chain's level, its compressor, its OD stage's
    // gain, its speaker, its EQ at each partial's frequency, the chorus's
    // dry share -- a gain a slot on every baseline (channel_gain)
    void efx_gain(const double *fc, const std::vector<long> &slots)
    {
        const bool cf = fc[14] != 0.0 && fc[18] == 0.0;     // (a chorus's copies, not a flanger's comb)
        double sh = 0.0;
        if (cf) {
            const double a = fc[20];
            sh = fc[21] >= 0.0 ? fc[21] : a * a / (1.0 + a * a);
        }
        std::vector<float> g(slots.size());
        const NoteClass *fcab = fc[2] != 0.0 && !patches[cur].cab ? efx_cab(fc[2]) : nullptr;
        for (size_t q = 0; q < slots.size(); q++) {
            const double f = S.f8[F8_om][slots[q]] * rate / (2.0 * M_PI);
            double x = fc[0];
            if (fc[3] != 0.0)
                x = x * fc[4];                  // ITS COMPRESSOR's makeup, before the OD
            if (fc[1] != 0.0)
                x = x * fc[1];                  // ITS OD STAGE's GAIN, in front of the valve
            if (fcab)
                x = x * nv_cab_gain(fcab, f);   // ...and the type's speaker, on a voice with none
            if (fc[6] != 0.0)
                x = x * nv_efx_eq_gain(fc, f);
            if (cf)
                x = x * pow(1.0 - sh, 0.5);
            g[q] = (float)x;
        }
        S.channel_gain_each(slots, g);
        if (fc[3] != 0.0) {
            // ITS COMPRESSOR (a multi's Cmp stage), as the file has it: its
            // sustain the decay slowed, its attack the onset's rise (float32)
            const float cs = (float)fc[3], ca = (float)(fc[5] * rate);
            for (long s : slots) {
                S.f4[F4_logr][s] = S.f4[F4_logr][s] * cs;
                S.f4[F4_logrA][s] = S.f4[F4_logrA][s] * cs;
                if (fc[5] > 0.0)
                    S.f4[F4_fa][s] = std::max(S.f4[F4_fa][s], ca);
            }
        }
    }

    // live._efx_direct and the rest of _efx_note on a chain: its level, its
    // EQ at each partial's frequency, the chorus's dry share -- a gain a slot
    // on every baseline (channel_gain); the note for an auto wah's Sens; its
    // moving filters (or the tone's own) arming the rows on channel ec
    void efx_direct(const double *fc, int ec, int note, int vel, long long n0, const std::vector<long> &slots,
                    bool own, int cp)
    {
        efx_gain(fc, slots);
        efx_notes[ec].push_back(EfxNote{(double)n0 / rate, INFINITY, vel, note});
        if (fc[22] != 0.0 && has_p3d)
            efx_place3d(fc, slots, cp, n0);
        if (fc[140] != 0.0)
            efx_rotary_arm(fc, slots, note, n0);
        if (efx_moves(fc) || own)
            S.filter_arm(slots, ec);
    }

    // A PARALLEL TYPE's BRANCH B (live._efx_branch; gsefx.PARALLEL_TYPES),
    // live as the file has it: the note again, struck with it, on the part's
    // virtual channel (ec + VIRT) -- so the filter, the rotor, the taps take
    // it as a part of its own, its chain branch B's -- at B's level, OD and
    // speaker; each branch at its own pan; let go with the note (mf104_reap)
    static const long long EFXB0 = 1LL << 48;       // its layer: EFXB0 + n0 (("efxB_%d", n0))
    void efx_branch(const double *fc, int ec, int ch, int note, const nv::live::Template &T, const Key &key,
                    const std::vector<long> &slots, double scale, long long n0, double b, int cp)
    {
        const int vch = ec + VIRT;
        const double *fb = efx_for(vch);
        if (!fb || slots.empty())
            return;
        long long on = 0;
        for (size_t i = 0; i < slots.size(); i++) {
            long long o = (long long)((double)S.i8[0][slots[i]] - (double)S.f4[F4_rdl][slots[i]]);
            on = i == 0 ? o : std::min(on, o);
        }
        Key kb(std::get<0>(key), ch, note, EFXB0 + n0);
        if (!S.stamp_t(T, kb, on, scale, ch, rate, 0.0)) {
            dropped++;
            return;
        }
        std::vector<long> sb = S.last_slots;
        for (long q : sb)
            S.slot_ch[q] = vch;
        if (cp != 64)
            S.repan(sb, cp, 64, rate, true);
        efx_gain(fb, sb);
        S.ear_gain(slots, fc[210], fc[211]);
        S.ear_gain(sb, fc[212], fc[213]);
        if (b != 0.0 && b != 1.0)
            retune(sb, n0, b);
        if (fb[140] != 0.0)
            efx_rotary_arm(fb, sb, note, n0);
        if (efx_moves(fb))
            S.filter_arm(sb, vch);
        tap_tables();
        tap_arm(vch, sb);
        long direct = slots[0];
        for (long q : slots)
            if (S.f4[F4_rdl][q] == 0.0f) {
                direct = q;
                break;
            }
        mf_groups.push_back(MfGroup{key, direct, {std::make_pair(kb, 0LL)}});
    }

    // live.pan_at: (alpha left, alpha right, half itd) for a source at angle
    // (radians, + right) -- tonelib's hrtf_at(0, angle=) on the stopped pipe's
    // head (Woodworth), the shadow's alpha as pan_table has each CC10's
    double p3d[4] = {0.0, 0.0, 0.0, 0.0};
    bool has_p3d = false;
    void pan_at(double angle, double *out) const
    {
        const double z = p3d[0], hr = p3d[2], c = p3d[3];
        double x = 0.0, y = p3d[1];
        const double th = angle;
        if (th != 0.0) {
            const double x1 = x * cos(th) + y * sin(th), y1 = -x * sin(th) + y * cos(th);
            x = x1;
            y = y1;
        }
        const double distance = std::max(sqrt(pow(x, 2.0) + y * y + z * z), hr);
        const double base_delay = distance / c;
        const double cos_to_right = x / distance;
        auto woodworth = [&](double ct, double *inc, double *del) {
            const double theta = acos(std::max(-1.0, std::min(1.0, ct)));
            const double offset = theta <= M_PI / 2.0 ? -cos(theta) : (theta - M_PI / 2.0);
            *inc = theta;
            *del = base_delay + offset * hr / c;
        };
        double li, ld, ri, rd;
        woodworth(-cos_to_right, &li, &ld);
        woodworth(cos_to_right, &ri, &rd);
        const double amin = 0.1, tmin = 150.0 * M_PI / 180.0;
        out[0] = 1.0 + amin / 2.0 + (1.0 - amin / 2.0) * cos(li * M_PI / tmin);
        out[1] = 1.0 + amin / 2.0 + (1.0 - amin / 2.0) * cos(ri * M_PI / tmin);
        out[2] = (ld - rd) / 2.0;
    }

    // Python's float % (a floor modulo: the divisor's sign)
    static double py_fmod(double a, double b)
    {
        double m = fmod(a, b);
        if (m != 0.0) {
            if ((b < 0.0) != (m < 0.0))
                m += b;
        } else {
            m = copysign(0.0, b);
        }
        return m;
    }

    // live._efx_place3d: the part at the type's azimuth (r[23], degrees), 3D
    // Auto's turning at r[24] turns a second, each note where its onset finds
    // it -- a repan from the channel's pan to the place
    void efx_place3d(const double *fc, const std::vector<long> &slots, int cp, long long n0)
    {
        const double az = fc[23], turn = fc[24];
        const double t = (double)n0 / rate;
        const double ang = (py_fmod(az + 360.0 * turn * t + 180.0, 360.0) - 180.0) * (M_PI / 180.0);
        double row[3];
        pan_at(ang, row);
        S.repan_rows(slots, row, S.pan_tab[std::max(0, std::min(127, cp))], rate, true);
    }

    // live._efx_rotary_arm: a Rotary type's part on the rotors -- each partial
    // leaving at its own angle (default_rng(note * 7919 + n).uniform(0, 2 pi):
    // PCG64), the drum and horn at their levels (r[149], r[150]), the two mics
    // at Separate (r[152])
    void efx_rotary_arm(const double *fc, const std::vector<long> &slots, int note, long long n0)
    {
        efx_rotary_sync();
        if (slots.empty())
            return;
        const long m = (long)slots.size();
        void *g = nv_npy_new((unsigned long long)((long long)note * 7919 + m));
        std::vector<float> az(m), nf(m), lv(m);
        for (long q = 0; q < m; q++)
            az[q] = (float)(0.0 + (2.0 * M_PI - 0.0) * nv_npy_uniform(g));
        nv_npy_free(g);
        for (long q = 0; q < m; q++)
            nf[q] = S.f4[F4_nf][slots[q]];
        S.leslie_arm(slots, az.data(), nf.data(), nullptr, n0, rotor_horn.rate, rotor_drum.rate);
        for (long q = 0; q < m; q++)
            lv[q] = (float)(S.ls_horn[slots[q]] ? fc[150] : fc[149]);
        S.channel_gain_each(slots, lv);
        for (long q = 0; q < m; q++)
            S.ls_sep[slots[q]] = (float)fc[152];
    }

    // live._efx_rotary_sync: the rotors at the Rotary type's speeds -- slow or
    // fast as its Speed stands (r[151]) -- and its spin times; back to the
    // organ's when it goes. Once a revision of the effect, as live keys it
    long rot_rev = -2;
    int rot_has = -1;
    bool rot_saved = false;
    double rot_dflt[4] = {0.0, 0.0, 0.0, 0.0};
    void efx_rotary_sync()
    {
        const double *rt = nullptr;
        for (int c : efx_chans()) {
            const double *ex = efx_for(c);
            if (ex && ex[140] != 0.0) {
                rt = ex;
                break;
            }
        }
        const long rev = efx ? nv_efx_live_rev(efx) : -1;
        if (rev == rot_rev && (rt != nullptr) == (rot_has == 1))
            return;
        rot_rev = rev;
        rot_has = rt != nullptr;
        if (!rot_saved) {
            rot_dflt[0] = rotor_horn.up; rot_dflt[1] = rotor_horn.down;
            rot_dflt[2] = rotor_drum.up; rot_dflt[3] = rotor_drum.down;
            rot_saved = true;
        }
        if (!rt) {
            rotor_horn.up = rot_dflt[0]; rotor_horn.down = rot_dflt[1];
            rotor_drum.up = rot_dflt[2]; rotor_drum.down = rot_dflt[3];
            return;
        }
        const bool fast = rt[151] != 0.0;
        const double hz = fast ? rt[144] : rt[143];
        const double dz = fast ? rt[142] : rt[141];
        rotor_horn.target = hz;
        rotor_drum.target = dz / std::max(fabs(rotor_drum.ratio), 1e-9);
        rotor_horn.up = rt[147]; rotor_horn.down = rt[148];
        rotor_drum.up = rt[145]; rotor_drum.down = rt[146];
    }

    // efxfilter.response type 4, a comb: |(1 - pa) + pa z / (1 - pb z)|, z =
    // exp(-2 pi i f ctrl) (native.xcexp's) -- numpy's complex division
    // (Smith's), the absolute libm's hypot (native.xabs)
    static double comb_h(double f, double ctrl, double pa, double pb)
    {
        const double th = -2.0 * M_PI * f * ctrl;
        const double zr = cos(th), zi = sin(th);
        const double nr = pa * zr, ni = pa * zi;
        const double dr = 1.0 - pb * zr, di = 0.0 - pb * zi;
        double qr, qi;
        if (fabs(dr) >= fabs(di)) {
            const double rat = di / dr, scl = 1.0 / (dr + di * rat);
            qr = (nr + ni * rat) * scl;
            qi = (ni - nr * rat) * scl;
        } else {
            const double rat = dr / di, scl = 1.0 / (di + dr * rat);
            qr = (nr * rat + ni) * scl;
            qi = (ni * rat - nr) * scl;
        }
        return hypot((1.0 - pa) + qr, qi);
    }

    // live._mono_cut: the voice taken -- this note stopped now over the
    // steal-fade, pedal or no pedal (its key has not come up)
    void mono_cut(int ch, int note, long long n0)
    {
        float fade = (float)(retrigger * rate);
        for (auto &kv : S.live)
            if (std::get<1>(kv.first) == ch && std::get<2>(kv.first) == note)
                for (long q : kv.second)
                    if (fade < S.f4[F4_re][q])
                        S.f4[F4_re][q] = fade;
        pedalled.erase(std::make_pair(ch, note));
        std::vector<int> cl = claimers(ch, note);
        if (cl.size() <= 1)
            let_go(ch, note, n0);
        else
            for (int i : cl) {
                Force f(*this, i);
                let_go(ch, note, n0);
            }
    }

    // the part's note (live._note_on): stamped, panned, softened, pressed,
    // bent, its strings struck
    void strike(int ch, int note, int vel, long long n0, bool slur = false)
    {
        int pi = 0 <= note && note <= 127 ? patch_for(ch, note) : -1;
        if (!amp_holds(pi)) {
            strike_now(ch, note, vel, n0, slur);
            return;
        }
        long long apid = patches[pi].pid;
        amp_shifted.erase(std::make_tuple(apid, ch, note));
        std::vector<long> got;
        S.collect = &got;
        strike_now(ch, note, vel, n0, slur);
        S.collect = nullptr;
        bool moog = false;                  // (a Moog's rows keep onsets of their own: never held)
        for (long s : got)
            moog = moog || S.i4[I4_fx][s] >= 0;
        if (!got.empty() && !moog) {
            long long T = S.i8[0][got[0]];
            for (long s : got)
                T = std::min(T, S.i8[0][s]);
            amp_change(apid, true, ch, note, got, T, S.f4[F4_fa].data());
        }
    }

    void strike_now(int ch, int note, int vel, long long n0, bool slur = false)
    {
        key_vel[std::make_pair(ch, note)] = vel;
        if (note < 0 || note > 127)
            return;
        int pi = patch_for(ch, note);
        if (pi < 0)
            return;                         // no part listens there
        Use u(*this, pi);
        key_tone[Key(pid, ch, note, 0)] = patches[cur].cache;   // (live.key_tone: the tone it was struck on)
        tone_prog[patches[cur].cache] = std::make_pair(patches[cur].program, (int)patches[cur].drums);
        int sn = note + transpose;          // the key the patch plays (live's snote)
        if (sn < 0 || sn > 127)
            return;
        n0 += amp_ahead();                  // a part with a valve plays its notes late (LIVE_AMP_LOOKAHEAD)
        const nv::live::Template *T = nv_tcache_lookup(cache, sn, bucket(vel), speed);
        if (!T)
            return;                         // a miss: live warms it off the audio thread
        amp_touch(cur);                     // (its chord changed: the valve's products are stale)
        {
            const NoteClass *skc = nv_tcache_key_class(patches[cur].cache, patches[cur].program, sn);
            if (skc && skc->siren)          // A SIREN's key: its rotor (live._siren_on)
                siren_on(ch, note, vel, n0, skc->siren, sn);
        }
        // FIXED TOUCH (live.Part.touch_fixed): the part's switch, else the
        // patch's way -- on, a touch-sensitive voice plays at velocity 127's
        // level (its timbre still the bucket's); off, a voice that has no
        // touch follows velocity (live's note_touch, its key's level)
        const Patch &pc = patches[cur];
        const bool fixt = pc.fixed_touch < 0 ? !pc.touch : pc.fixed_touch != 0;
        const double tf = (pc.touch || fixt) ? 1.0 : pow(vel / 127.0, 2.0);
        if (patches[cur].organ) {           // a registered organ: its ranks drawn
            organ_strike(*T, ch, note, vel, n0, tf);
            return;
        }
        double scale = pow(10.0, level_db / 20.0) * swell * chan_gain(ch);
        if (patches[cur].touch)             // touch: the press over the template's (a voice without it: its own level)
            scale *= pow((fixt ? 127 : vel) / 127.0, 2.0) / std::max(pow(T->vel / 127.0, 2.0), 1e-9);
        else
            scale *= tf;
        if (patches[cur].touch && patches[cur].moog) {
            // A MOOG'S A ENV VEL, where the panel sets it: off, the level fixed
            // (velocity 127's); on, the Messenger's own law (moog.a_vel_gain)
            double pn[NV_MK_N];
            moog_pn(patches[cur], true, pn);
            if (pn[NV_MK_A_VEL] >= 0.0) {
                scale = pow(10.0, level_db / 20.0) * swell * chan_gain(ch) / std::max(pow(T->vel / 127.0, 2.0), 1e-9);
                if (pn[NV_MK_A_VEL] >= 0.5)
                    scale *= moog_a_vel_gain(fixt ? 127 : vel);
            }
        }
        Key key(pid, ch, note, -1);
        long li = S.live_find(key);
        if (damper_pedal && li >= 0 && !S.live[li].second.empty() && !S.oneshot.count(key)) {
            // a restrike: the string under the hammer stops in a steal-fade,
            // and its forced register rows (REG_FORCED) with it
            float fade = (float)(retrigger * rate);
            for (const Key &k : {key, Key(pid, ch, note, REG_FORCED)}) {
                long lk = S.live_find(k);
                if (lk < 0 || S.live[lk].second.empty())
                    continue;
                for (long sidx : S.live[lk].second)
                    if (fade < S.f4[F4_re][sidx])
                        S.f4[F4_re][sidx] = fade;
                S.release(k, n0);
            }
        }
        if (T->roll_kind) {
            // A HELD ROLL: struck as it goes, from the press (roll_tick)
            RollGen g;
            g.key = Key(pid, ch, note, -1);
            g.T = T;
            pyr_seed(&g.r, (long long)T->roll_key * 7919LL + n0);
            g.at = n0;
            g.scale = scale;
            auto it = std::find_if(roll_gen.begin(), roll_gen.end(), [&](const RollGen &x) { return x.key == g.key; });
            if (it != roll_gen.end())
                *it = g;                    // (a dict's key keeps its place)
            else
                roll_gen.push_back(g);
            return;
        }
        if (!S.stamp_t(*T, key, n0, scale, ch, rate)) {
            dropped++;
            return;                         // the slab full: this note does not sound
        }
        {
            auto si = siren_find(SKey(pid, ch, note));      // a siren's slots on its rotor's row
            if (si != siren_st.end() && !si->second.rows.empty())
                for (long s : S.last_slots)
                    S.i4[I4_br][s] = si->second.rows[0];
        }
        std::vector<long> lslots[2] = {S.last_slots, {}};    // each layer's (live's _lslots)
        if (T->moog) {                      // a Moog note: its rows, the panel on it (Slab._moog_stamp)
            MoogLayer La;
            S.moog_stamp(*T, pid, ch, 0, moog_panel(patches[cur], ch, La), rate);
            // A LAYERED MOOG (moog.layers_of): the same knob-neutral template
            // again for its second Messenger, under the same key -- so all
            // below, and the key-up, act on both -- each stamp's rows reading
            // its own panel; at layer A's onset, no scatter of its own (the
            // file has the two together)
            if (patches[cur].moog_b) {
                double lo = INFINITY;
                for (long s : S.last_slots)
                    lo = std::min(lo, (double)S.i8[0][s] - (double)S.f4[F4_rdl][s]);
                if (S.stamp_t(*T, key, (long long)lo, scale, ch, rate, 0.0)) {
                    lslots[1] = S.last_slots;
                    S.moog_stamp(*T, pid, ch, 1, moog_panel(patches[cur], ch, La, 1), rate);
                } else
                    dropped++;
            }
            // THE UNISON (moog.unison: a supersaw): each layer's stamp again for
            // every voice past the first, under the same key, each its own
            // detune, phase, level, place and drift (Slab.unison_voice); the
            // first stamp is the centre voice's (live's _uvs, _mid)
            double uv[9 * 16];
            int umid = 0;
            const int nu = nv_moog_unison(patches[cur].moog, T->ft_f0, uv, &umid);
            if (nu > 1) {
                double lo = INFINITY;
                for (long s : lslots[0])
                    lo = std::min(lo, (double)S.i8[0][s] - (double)S.f4[F4_rdl][s]);
                for (int ly = 0; ly < 2; ly++) {
                    if (ly == 1 && !patches[cur].moog_b)
                        continue;
                    S.unison_voice(lslots[ly], uv + 9 * umid);
                    for (int u = 0; u < nu; u++) {
                        if (u == umid)
                            continue;
                        if (!S.stamp_t(*T, key, (long long)lo, scale, ch, rate, 0.0)) {
                            dropped++;
                            continue;
                        }
                        S.moog_stamp(*T, pid, ch, ly, moog_panel(patches[cur], ch, La, ly), rate);
                        std::vector<long> us = S.last_slots;
                        S.unison_voice(us, uv + 9 * u);
                        std::vector<long> quiet;
                        for (long s : us) {
                            const int o = S.i4[I4_mk][s] / 4096;
                            if (o == 4 || o == 5)
                                quiet.push_back(s);
                        }
                        S.silence_slots(quiet);
                        lslots[ly].insert(lslots[ly].end(), us.begin(), us.end());
                    }
                }
            }
        }
        if (T->min_hold) {
            tex_on[key] = n0 + T->min_hold; // a held texture: the least it plays
            if (!T->gpool.empty() && T->grate > 0.0) {
                // its grains, from the press, for as long as it is held (tex_tick)
                double nx = (double)n0 + tex_expo(T->grate) * rate;
                auto it = std::find_if(tex_gen.begin(), tex_gen.end(), [&](const TexGen &g) { return g.key == key; });
                if (it != tex_gen.end())
                    *it = TexGen{key, T, nx, scale};        // (a dict's key keeps its place)
                else
                    tex_gen.push_back(TexGen{key, T, nx, scale});
            }
        }
        if (!T->rel.empty())
            held_rel[Key(pid, ch, note, 0)] = std::make_pair(T, scale);     // its key-up rows, at the key-up
        long lj = S.live_find(key);
        std::vector<long> slots = lj >= 0 ? S.live[lj].second : std::vector<long>();
        if (cpan[ch] != 64 && !slots.empty())
            S.repan(slots, cpan[ch], 64, rate, true);
        const double *efx_fc = nullptr;     // the insertion effect, the module's or the tone's (live._efx_note)
        int efx_ec = ch;
        if (!slots.empty() && !patches[cur].drums)
            efx_fc = efx_note(ch, note, vel, n0, slots, &efx_ec);
        if (soft[ch] && !slots.empty())
            S.soft_strings(slots, soft_drop, soft_top);
        double gl[3];                       // PORTAMENTO, stamped (live._glide)
        double mtau = 0.0;                  // (a Moog with its GLIDE knob up: the knob's, from the last key)
        if (!slots.empty() && (glide_from >= 0 || moog_src >= 0) && patches[cur].moog) {
            double pn[NV_MK_N];
            moog_pn(patches[cur], true, pn);
            mtau = moog_glide_tau(pn[NV_MK_GLIDE]);
        }
        const int gsrc = mtau > 0.0 ? moog_src : glide_from;
        if (gsrc >= 0 && !slots.empty()
            && nv_tcache_glide(cache, program, gsrc + transpose, sn, porta_time[ch], gl, mtau))
            for (long q : slots) {
                S.f4n[0][q] = (float)gl[0];
                S.f4n[1][q] = (float)gl[1];
                S.f4n[2][q] = (float)gl[2];
            }
        if (slur && !slots.empty()) {
            slur_push(ch, sn, n0, *T);
            slur_stamp(sn, *T);
        } else if (!slots.empty() && std::find(T->push.begin(), T->push.end(), 1) != T->push.end()) {
            push_t0[ch] = n0;               // A NOTE FROM SILENCE IS A PUSH OF THE BELLOWS: when it began
        }
        if (drums && !choke_p->empty()) {
            // THE CHOKE, live (Live._note_on): the strike in an exclusive
            // class is a note-off written into whatever of it is ringing
            const unsigned long long *m = &(*choke_p)[2 * (128 * program + sn)];
            if (m[0] | m[1]) {
                std::vector<Key> hit;
                for (auto &kv : S.live) {
                    int k = (int)std::get<2>(kv.first), ks = k + transpose;
                    if (std::get<0>(kv.first) == pid && k != note && ks >= 0 && ks < 128
                        && ((m[ks >> 6] >> (ks & 63)) & 1ULL))
                        hit.push_back(kv.first);
                }
                for (const Key &k : hit) {
                    S.oneshot.erase(k);
                    S.release(k, n0);
                }
            }
        }
        auto cs = clav_step.find(pid);      // a note struck with the rockers down joins them
        if (cs != clav_step.end())
            S.clav_tone(cs->second, slots);
        auto td = trem_depth.find(pid);     // the wheel's tremolo, the wheel already up
        if (td != trem_depth.end() && td->second > 0.0)
            S.tremolo_arm(slots, td->second, patches[cur].wtrem_stereo);
        if (pressure[ch] != 0.0)
            press(slots, pressure[ch]);
        if (drone_class()) {                // THE DRONES: up with the chanter (live._drones)
            drone_quiet.erase(pid);
            drones(ch, n0);
        } else if (dnote_class()) {         // ...the pungi's (live._drone_note)
            drone_quiet.erase(pid);
            drone_note(ch, n0);
        }
        sound_stamp_note(patches[cur], ch, sn, slots);     // the channel's CC71-78 (live._sound_stamp)
        double b_left = 1.0;                // (the bend left to apply: a parallel type's branch B takes it)
        {                                   // a note struck under a bend, or the wheel up, joins them
            double sva, svr;
            snd_vib(patches[cur], ch, slots, &sva, &svr);
            double b = bend[ch] * (key_ratio(patches[cur], ch, note) * 1.0);   // (the key's tuning: _key_ratio)
            double v2 = vib_mod[ch] + sva, r2 = (1.0 + mod_rate * vib_modw[ch]) * svr;
            if (nv_tcache_gm2(patches[cur].cache))
                mts_at[std::make_tuple(pid, ch, note + transpose)] = mts_ratio(patches[cur], ch, note);
            // ...OR A MEEND'S, for a voice that locks its bend to the tuning's swaras
            double mr;
            bool has_mr = meend_ratio(patches[cur], ch, note, &mr);
            if (has_mr) {
                b = b / bend[ch] * mr;
                meend_at[key] = std::make_pair(mr, T->sym);
            }
            if (patches[cur].moog) {        // ...AND A MOOG'S LFO 2 WHERE IT HAS THE PITCH (lfo2_tick)
                auto lp = lfo2_pr.find(pid);
                b *= lp != lfo2_pr.end() ? lp->second : 1.0;
            }
            messenger_pitch(patches[cur], ch, note);     // A MESSENGER PLAYING IT, on the same pitch
            // THE OPEN STRINGS ARE NOT ON THE WHEEL (live._fixed_sym): their
            // rows take the note's tuning but not the pull, now or later
            // ...AND THE RING ROWS (a banjo's other strings and head): never on the wheel
            const NoteClass *kc = key_class(patches[cur], sn);
            std::vector<char> sm(slots.size(), 0);
            bool any = false;
            if (kc && (kc->sym_kind == 1 || kc->sym_kind == 3) && T->sym.size() == slots.size())
                for (size_t q = 0; q < slots.size(); q++)
                    sm[q] = sm[q] || T->sym[q];
            if (T->ring.size() == slots.size())
                for (size_t q = 0; q < slots.size(); q++)
                    sm[q] = sm[q] || T->ring[q];
            for (char m : sm)
                any = any || m;
            {
                if (any) {
                    sym_at[key] = sm;
                    // _wheel_share: the bend over the channel's tuning without the wheel
                    double st0 = range_of(ch) * 0.0 / 8192.0 + coarse[ch] + fine[ch] / 100.0 + master_coarse
                                 + master_fine / 100.0;
                    double rest = pow(2.0, st0 / 12.0);
                    double share = rest > 0 ? (has_mr ? mr : bend[ch]) / rest : 1.0;
                    double bs = b / share;
                    for (int sel = 1; sel >= 0; sel--) {
                        double r_ = sel ? bs : b;
                        std::vector<long> ix;
                        for (size_t q = 0; q < slots.size(); q++)
                            if ((sm[q] != 0) == (sel != 0))
                                ix.push_back(slots[q]);
                        if (r_ != 1.0 && !ix.empty())
                            retune(ix, n0, r_);
                    }
                    b = 1.0;            // applied; the vibrato below, on every row
                }
            }
            if (b != 1.0 || v2 != 0.0 || r2 != 1.0)
                retune_v(slots, n0, b != 1.0, b, v2 != 0.0, v2, r2 != 1.0, r2);
            b_left = b;
        }
        if (reg_on && cur_reg && reg_note[note] && !lslots[0].empty())
            reg_strike(ch, note, n0, *T, lslots[0]);
        if (patches[cur].moog && !slots.empty()) {
            // ITS VELOCITY, for F ENV VEL (moog.mx_row): each of its rows' notes
            std::set<int> rs;
            for (long s : slots)
                if (S.i4[I4_fx][s] >= 0)
                    rs.insert(S.i4[I4_fx][s]);
            for (int r : rs) {
                S.mx_vel[r] = vel;
                double pn[NV_MK_N];
                moog_pn(patches[cur], true, pn, S.ft_layer[r]);
                // ...AND A LEGATO HANDOFF WITH MULTI-TRIG OFF: its contours
                // carry on from the note it took over (legato_take)
                // -- or, MULTI-TRIG on, start again charged from where its
                // contours had got to (held_level)
                auto lg = legato_age.find(std::make_pair((long long)pid, S.ft_layer[r]));
                if (lg != legato_age.end()) {
                    const int ro = lg->second;
                    const double t = (S.mp_a0[r] - S.mp_a0[ro]) / rate + S.mx_age[ro];
                    if (pn[NV_MK_MULTITRIG] == 0.0) {
                        S.mx_age[r] = t;
                        S.mx_l0a[r] = S.mx_l0a[ro];
                        S.mx_l0f[r] = S.mx_l0f[ro];
                    } else {
                        S.mx_l0a[r] = S.contour_at(ro, t, true);
                        S.mx_l0f[r] = S.contour_at(ro, t, false);
                    }
                }
                S.mx_write(r, pn);
            }
        }
        if (patches[cur].moog && !slots.empty())
            for (int ly = 0; ly < 2; ly++)          // each Messenger its own pedal
                if (!lslots[ly].empty())
                    mf104(patches[cur], ch, note, *T, key, lslots[ly], scale, n0, bend[ch], ly);
        if (efx_fc) {                           // ITS COPIES: the slots on the channel's tap set (live._tap_arm)
            tap_tables();
            tap_arm(efx_ec, slots);
            if (efx_fc[208] != 0.0)             // ...and a parallel type's branch B (live._efx_branch)
                efx_branch(efx_fc, efx_ec, ch, note, *T, key, slots, scale, n0, b_left, cpan[ch]);
        }
    }

    // THE MF-104M, LIVE (live._mf104; mf104.py): a Moog part whose panel has
    // the pedal on stamps each repeat as its own key at the note's onset +
    // k tau -- a future onset, silence until it arrives -- carrying only the
    // partials whose repeat clears the floor, each at its own gain (k trips
    // through the line's filter), as the file's expand. A copy keeps the
    // note's vibrato, delayed, or takes the pedal LFO's in its place; it is
    // released at the note's release plus its own delay (mf104_reap), never
    // by the sweep, which would cut it off before it had sounded
    static const long long MFK0 = -(1LL << 20);     // a repeat's layer: MFK0 - (n0 64 + layer 32 + k)
    struct MfGroup {
        Key key;
        long direct;
        std::vector<std::pair<Key, long long>> group;
    };
    std::vector<MfGroup> mf_groups;

    // mf104.bessel_i: I_n(x) by its series, summed as Python's sum() sums floats
    static double mf_bessel_i(int n, double x)
    {
        double t[12];
        for (int m = 0; m < 12; m++) {
            long long a = 1, b = 1;
            for (int q = 2; q <= m; q++)
                a *= q;
            for (int q = 2; q <= m + n; q++)
                b *= q;
            t[m] = pow(x / 2.0, (double)(2 * m + n)) / (double)(a * b);
        }
        return pysum(t, 12);
    }

    // the template's rows where m (live's {c: v[m]}): every per-row column
    static nv::live::Template sub_template(const nv::live::Template &T, const std::vector<char> &m)
    {
        nv::live::Template o;
        long P = T.P;
        auto cut = [&](auto &dst, const auto &src) {
            dst.clear();
            if ((long)src.size() != P)
                return;
            for (long q = 0; q < P; q++)
                if (m[q])
                    dst.push_back(src[q]);
        };
        for (int c = 0; c < 6; c++) cut(o.f8[c], T.f8[c]);
        for (int c = 0; c < 27; c++) cut(o.f4[c], T.f4[c]);
        for (int c = 0; c < 4; c++) cut(o.f4n[c], T.f4n[c]);
        for (int c = 0; c < 2; c++) cut(o.i8[c], T.i8[c]);
        for (int c = 0; c < 6; c++) cut(o.i4[c], T.i4[c]);
        cut(o.hrel, T.hrel); cut(o.fa_at, T.fa_at); cut(o.rof, T.rof); cut(o.sof, T.sof); cut(o.cof, T.cof);
        cut(o.lflip, T.lflip); cut(o.lhorn, T.lhorn); cut(o.lfl, T.lfl); cut(o.lsh, T.lsh); cut(o.lnrm, T.lnrm);
        cut(o.push, T.push);
        long n = 0;
        for (long q = 0; q < P; q++)
            n += m[q] != 0;
        o.P = n;
        o.dur = T.dur; o.vel = T.vel; o.oneshot = T.oneshot; o.min_hold = T.min_hold;
        o.moog = T.moog; o.ft_f0 = T.ft_f0; o.ft_pre = T.ft_pre;
        o.scatter_ms = 0.0;
        return o;
    }

    void mf104(const Patch &p, int ch, int note, const nv::live::Template &T, const Key &key,
               const std::vector<long> &slots, double scale, long long n0, double b, int layer)
    {
        MoogLayer La;
        const MoogLayer *L = moog_panel(p, ch, La, layer);
        if (!L || !L->mf_on)
            return;
        const double time = L->mf[0], fc = L->mf[1], fb = L->mf[2], wet = L->mf[3], dry = L->mf[4],
                     lrate = L->mf[5], amount = L->mf[6];
        size_t n = slots.size();
        if ((long)n != T.P)
            return;
        // each partial's sounding frequency, the bend taken back out as the
        // file's rows have it; the line's filter at it; only what sounds
        std::vector<double> f(n), h(n), rel(n);
        std::vector<char> snd(n);
        double top = 0.0, fmin = 0.0;
        bool anys = false;
        long long on = 0;
        for (size_t i = 0; i < n; i++) {
            long s = slots[i];
            f[i] = S.f8[F8_om][s] * rate / (2.0 * M_PI) / (b != 0.0 ? b : 1.0);
            double x = fabs(f[i]) / fc;
            h[i] = pow(1.0 + x * x, -L->mf_poles / 2.0);
            float aL = fabsf(S.f4[F4_aL][s]), aR = fabsf(S.f4[F4_aR][s]);
            snd[i] = (aL + aR) > 0.0f;
            rel[i] = (double)std::max(aL, aR);
            top = i == 0 ? rel[i] : std::max(top, rel[i]);
            if (snd[i]) {
                fmin = anys ? std::min(fmin, f[i]) : f[i];
                anys = true;
            }
            double o = (double)S.i8[0][s] - (double)S.f4[F4_rdl][s];
            long long oi = (long long)o;
            on = i == 0 ? oi : std::min(on, oi);
        }
        if (top > 0.0)
            for (size_t i = 0; i < n; i++)
                rel[i] = rel[i] / top;
        // mf104.delay_samples, mf104.repeats at the lowest that sounds
        double mean = time * mf_bessel_i(0, amount * log(2.0));
        long long g0 = (long long)L->mf_grid;
        long long d0 = std::max(g0, (long long)nearbyint(mean * rate / L->mf_grid) * g0);
        double xm = fabs(fmin) / fc, hm = pow(1.0 + xm * xm, -L->mf_poles / 2.0);
        std::vector<std::pair<Key, long long>> group;
        const double tpi = 2.0 * M_PI;
        for (int k = 1; k <= (int)L->mf_max; k++) {
            if (wet * pow(fb, (double)(k - 1)) * pow(hm, (double)k) < L->mf_floor)
                break;
            long long d = (long long)k * d0;
            std::vector<double> g(n);
            std::vector<char> m(n);
            bool any = false;
            for (size_t i = 0; i < n; i++) {
                g[i] = wet * pow(fb, (double)(k - 1)) * pow(h[i], (double)k);
                m[i] = g[i] * rel[i] >= L->mf_floor && snd[i];
                any = any || m[i];
            }
            if (!any)
                break;
            nv::live::Template sub = sub_template(T, m);
            Key ck(std::get<0>(key), ch, note, MFK0 - (n0 * 64 + layer * 32 + k));
            if (!S.stamp_t(sub, ck, on + d, scale, ch, rate, 0.0)) {
                dropped++;
                break;
            }
            S.moog_stamp(sub, std::get<0>(key), ch, layer, L, rate);
            std::vector<long> cs = S.last_slots;
            if (cpan[ch] != 64)
                S.repan(cs, cpan[ch], 64, rate, true);
            std::vector<float> gm;
            for (size_t i = 0; i < n; i++)
                if (m[i])
                    gm.push_back((float)g[i]);
            S.channel_gain_each(cs, gm);
            if (amount > 0.0) {             // the line's wobble, in place of the note's (mf104.lfo_vibrato)
                double w = tpi * lrate, tau = (double)d0 / rate, sre = 0.0, sim = 0.0;
                for (int j = 0; j < k; j++) {
                    sre = sre + cos(w * (double)j * tau);
                    sim = sim + -sin(w * (double)j * tau);
                }
                double dlt = time * 2.0 * mf_bessel_i(1, amount * log(2.0)) * hypot(sre, sim);
                double th = atan2(sim, sre);
                for (long q : cs) {
                    double fq = S.f8[F8_om][q] * rate / (2.0 * M_PI);
                    double t_on = (double)S.i8[0][q] / rate;
                    S.f4[F4_vd][q] = (float)(w * dlt);
                    S.f4[F4_vr][q] = (float)lrate;
                    S.f4[21][q] = (float)(th - M_PI / 2.0);      // vp
                    S.f4n[3][q] = 0.0f;                  // vdl
                    double dp = -2.0 * M_PI * fq * dlt * sin(w * t_on + th);
                    S.f8[F8_p0][q] += dp;
                    S.f8[F8_p0R][q] += dp;
                    S.vbase[q] = S.f4[F4_vd][q];
                    S.vrbase[q] = S.f4[F4_vr][q];
                }
            } else {                        // the note's own vibrato, delayed
                // (numpy 1.26's value-based casting: a Python float on a
                // float32 column stays float32, rounded to it; a Python int
                // too while it fits a uint16 -- past 65535 the product is
                // float64, and so is the rest)
                for (long q : cs) {
                    float x = (float)tpi * S.f4[F4_vr][q];
                    if (d <= 65535) {
                        x = x * (float)d;
                        x = x / (float)rate;
                        S.f4[21][q] = S.f4[21][q] - x;
                    } else {
                        S.f4[21][q] = (float)((double)S.f4[21][q] - (double)x * (double)d / rate);
                    }
                }
            }
            if (b != 1.0)
                retune(cs, n0, b);
            group.emplace_back(ck, d);
        }
        if (!group.empty()) {
            S.channel_gain(slots, dry);
            long direct = slots[0];
            for (long s : slots)
                if (S.f4[F4_rdl][s] == 0.0f) {
                    direct = s;
                    break;
                }
            mf_groups.push_back(MfGroup{key, direct, group});
        }
    }

    // live._mf104_reap: each repeat ends where its note ended, its own delay later
    void mf104_reap()
    {
        std::vector<MfGroup> keep;
        for (MfGroup &g : mf_groups) {
            if (S.live_find(g.key) >= 0) {
                keep.push_back(g);
                continue;
            }
            long long off = S.i8[1][g.direct];
            for (auto &c : g.group)
                if (S.live_find(c.first) >= 0 && !S.oneshot.count(c.first)) {
                    S.release(c.first, off + c.second);
                    if (std::get<3>(c.first) >= EFXB0)
                        amp_dirty.insert(std::get<0>(c.first));     // (branch B going: the valve's chord changed)
                }
        }
        mf_groups.swap(keep);
    }

    long dropped = 0;                           // ranks the slab had no room for (live.dropped)
    // A HARMONIUM'S (live's): the Expression's bellows each key's ranks were
    // stamped at (xnote), each channel's stop word as sent (CC43-45; -1 not
    // yet), each part's wheel tremolo depth (trem_depth)
    std::map<Key, double> xnote;
    int stopword[16][3];
    std::map<long long, double> trem_depth;

    // live._h8: a key's 8-foot pitch against its template's lowest partial
    double h8(int note)
    {
        int tgt = note + transpose;
        double F = nv_tcache_freq(cache, tgt);
        const nv::live::Template *t = (tgt >= 0 && tgt < 128) ? nv_tcache_lookup(cache, tgt, bucket(100), speed)
                                                               : nullptr;
        if (t && t->P && F > 0.0) {
            float mn = t->f4[2][0];
            for (long q = 1; q < t->P; q++)
                mn = std::min(mn, t->f4[2][q]);
            return (double)mn / F;
        }
        const OrganSpec *og = patches[cur].organ;
        double m = 1e300;
        for (int r = 0; r < og->n_rank; r++) {
            const OrganRank &rk = og->rank[r];
            if (rk.n_ratio && !rk.compound && rk.lo <= tgt && tgt <= rk.hi)
                m = std::min(m, rk.ratio[0]);
        }
        return m < 1e300 ? m : 1.0;
    }

    // live._harmonium_stamp: the effect stops on the slots just stamped --
    // the Expression's bellows (each partial by harmonium_expression_gain),
    // the Percussion's hammer, the Tremolo
    void harmonium_stamp(const nv::live::Template &T, const nv::live::Template &R, int ch, int note, int ri,
                         const Key &key)
    {
        const std::vector<long> sl = S.last_slots;
        if (sl.empty() || (long)sl.size() != R.P)
            return;
        const OrganSpec *og = patches[cur].organ;
        const std::vector<char> &dr = patches[cur].drawn;
        sound_stamp(og, ch, sl);            // CC73/72 first: the hammer is a min over the attack
        if (og->expr_rank >= 0 && dr[og->expr_rank]) {
            double e = expr[ch] / 127.0, h8_ = h8(note);
            std::vector<float> g(sl.size());
            for (size_t q = 0; q < sl.size(); q++) {
                double h = (double)R.hrel[q] * h8_;
                g[q] = (float)pow(h > 1.0 ? h : 1.0, og->expr_tilt * (e - 1.0));
            }
            S.channel_gain_each(sl, g);
            xnote[key] = e;
        }
        if (og->perc_rank >= 0 && dr[og->perc_rank] && og->rank[ri].perc) {
            double dur = T.dur ? T.dur / rate : 1.0;
            float fa = (float)(std::max(1e-4, std::min(og->perc_attack_s, og->afm * dur)) * rate);
            for (long s : sl)
                if (fa < S.f4[F4_fa][s])
                    S.f4[F4_fa][s] = fa;
        }
        if (og->htrem_rank >= 0 && dr[og->htrem_rank] && og->htrem_depth > 0.0)
            S.stop_tremolo_arm(sl, og->htrem_depth, og->htrem_hz);   // (at the stop's own rate)
    }

    // live's CC11 on a harmonium: the Expression's bellows moved under the
    // notes stamped with it drawn -- each by the law's ratio between the two
    void harmonium_bellows(int ch, int v)
    {
        double e = v / 127.0;
        std::vector<Key> gone;
        for (auto &kv : xnote) {
            long li = S.live_find(kv.first);
            if (li < 0 || S.live[li].second.empty()) {
                gone.push_back(kv.first);
                continue;
            }
            if (std::get<1>(kv.first) != ch || kv.second == e)
                continue;
            int pi = -1;
            for (size_t q = 0; q < patches.size(); q++)
                if (patches[q].pid == std::get<0>(kv.first))
                    pi = (int)q;
            if (pi < 0 || !patches[pi].organ)
                continue;
            Use u(*this, pi);
            const std::vector<long> &sl = S.live[li].second;
            double h8_ = h8((int)std::get<2>(kv.first)), tilt = patches[cur].organ->expr_tilt;
            std::vector<float> g(sl.size());
            for (size_t q = 0; q < sl.size(); q++) {
                double h = (double)S.hrel[sl[q]] * h8_;
                h = h > 1.0 ? h : 1.0;
                g[q] = (float)(pow(h, tilt * (e - 1.0)) / pow(h, tilt * (kv.second - 1.0)));
            }
            S.channel_gain_each(sl, g);
            kv.second = e;
        }
        for (auto &k : gone)
            xnote.erase(k);
    }

    // live's CC43-45 on a harmonium: its stop word, a controller each seven
    // stops, the default's bytes where none has come yet
    void harmonium_word(int ch, int cc, int v, long long n0)
    {
        stopword[ch][cc - 43] = v;
        for (size_t pi = 0; pi < patches.size(); pi++) {
            const OrganSpec *og = patches[pi].organ;
            if (!og || og->wccs[0] != 43 || !(patches[pi].channel < 0 || patches[pi].channel == ch))
                continue;
            long long word = 0;
            for (int i = 0; i < og->n_wccs && i < 3; i++)
                word |= (long long)(stopword[ch][i] >= 0 ? stopword[ch][i] : (og->default_stops >> (7 * i)) & 0x7F)
                        << (7 * i);
            std::vector<char> want(og->n_rank, 0);
            for (int i = 0; i < og->n_rank; i++)
                want[i] = (word >> i) & 1;
            set_stops((int)pi, want, n0);
        }
    }

    // live's CC1 on a voice with a tremolo (its 'tremolo' role): the depth, on
    // the notes the part has sounding
    void wheel_tremolo(int ch, int v)
    {
        for (size_t pi = 0; pi < patches.size(); pi++) {
            const Patch &p = patches[pi];
            if (p.wtrem <= 0.0 || !(p.channel < 0 || p.channel == ch))
                continue;
            double d = (v / 127.0) * p.wtrem;
            trem_depth[patches[pi].pid] = d;
            S.tremolo_arm(sounding_tone(ch, p.pid, p.cache, false), d, p.wtrem_stereo);   // (this tone's notes)
        }
    }

    // live's swing each block: the wheel's at one rate (the first part's with
    // a wheel tremolo), a Tremolo stop's slots at their own
    void tremolo_block(long long n0)
    {
        if (!S.any_tremolo())
            return;
        double hz = 0.0;
        for (const Patch &p : patches)
            if (p.wtrem > 0.0) {
                hz = p.wtrem_hz;
                break;
            }
        // (a Tremolo stop's slots at their own rate: tremolo_swing)
        S.tremolo_swing(hz > 0.0, hz > 0.0 ? 2.0 * M_PI * hz * n0 / rate : 0.0, n0, rate);
    }
    // the panel's stops for the next block: each the whole registration, as
    // drawn when it was posted with the one stop toggled (livetui's
    // request_stops) -- so a stop word in the same block is put back, as live's
    // ...and a patch change's (Swap): ONE QUEUE, done in the order posted, as
    // live's posted commands are -- each stop request the registration by its
    // stops' NAMES (livetui's request_stops: live.set_stops takes those of
    // the patch then in use, a change of program between them its own)
    struct Swap;
    struct Post {
        int kind;                           // 0 the stops, 1 a patch change, 2 a Moog's knob (set_synth), 4 a drive knob
        std::vector<std::string> names;
        std::shared_ptr<Swap> swap;
        long long pid = 0;
        int knob = 0;
        double old = 0.0;
        int layer = 0;                      // (a Moog's knob: 1 its second Messenger, live's 'b')
        int pi = -1;                        // (3: a knob set once the patches before it are in -- a preset's)
        double value = 0.0;
    };
    std::vector<Post> posts;

    // A PATCH CHANGE (live._swap_patch, posted: after the block's events):
    // the patch re-pointed at another tone -- its templates (cache), its
    // program and the part's constants for it -- keeping its pid, so notes
    // already sounding keep the templates they were struck with
    // A VOICE'S STRINGS for the register: a bank and its constants
    // (nv_part_register's), as a program change hands a new one over
    struct Bank {
        std::vector<StringMode> modes;
        double kappa = 0, knock = 0, fall = 0, fl = 0, beta = 0, rel = 0;
        int top = 128, pedals = 1;
        std::vector<int> note;              // the keys whose classes answer (128)
        std::vector<long> cbr;              // a harpsichord's choirs (empty: none)
        double cross = 1.0;
        std::vector<int> buffs;
        const NoteClass *keyed = nullptr;   // a dulcimer's bridges by key, partners, knock (NoteClass.reg_keyed)
    };
    struct Swap {
        int pi;
        void *cache;
        int program, drums, nbuckets, speed, damper_pedal, soft_drop, soft_top, detune_wheel;
        std::vector<unsigned long long> choke;
        std::vector<int> reg_note;          // the new tone's keys that answer the register (empty: as they were)
        std::shared_ptr<Bank> bank;         // ...ITS OWN STRINGS where they are another voice's (null: the same)
    };

    std::map<Key, const void *> key_tone;           // (pid, ch, note, 0) -> the cache it was struck on
    std::map<const void *, std::pair<int, int>> tone_prog;     // a cache -> its (program, drums)
    // A RANK's KEY IS ITS STOP's NAME (live's k[3]): its layer RANK0 + the
    // name's id, interned here (an organ's rank index is not one across a
    // program change -- the Hammond's '1' and the church organ's 'reed 8'
    // can share one)
    std::vector<std::string> stop_names;
    std::map<std::string, int> stop_id;
    long long rank_layer(const OrganSpec *og, int ri)
    {
        const char *nm = og->rank[ri].key;
        auto it = stop_id.find(nm);
        if (it != stop_id.end())
            return RANK0 + it->second;
        int id = (int)stop_names.size();
        stop_names.push_back(nm);
        stop_id[nm] = id;
        return RANK0 + id;
    }
    bool is_rank(long long l) const { return l >= RANK0 && l < RANK0 + (long long)stop_names.size(); }
    // live's k[3] for a rank key: its stop's name ("" none)
    const char *rank_name(const Key &k) const
    {
        long long l = std::get<3>(k);
        return is_rank(l) ? stop_names[l - RANK0].c_str() : "";
    }
    // the rank of og a layer is (by its stop's name), -1 none
    int rank_of(const OrganSpec *og, long long l)
    {
        if (!og || !is_rank(l))
            return -1;
        for (int j = 0; j < og->n_rank; j++)
            if (stop_names[l - RANK0] == og->rank[j].key)
                return j;
        return -1;
    }
    // the old tones' valves (live.amp_retired): retired key -> (pid, old cache), a dict's order
    std::vector<std::pair<Key, std::pair<long long, const void *>>> amp_retired;
    static const long long AMP_OLD0 = 1LL << 40;    // ...their layer: AMP_OLD0 + the swap's sample

    void swap_patch(const Swap &w, long long n0)
    {
        if (w.pi < 0 || w.pi >= (int)patches.size())
            return;
        Patch &p = patches[w.pi];
        long long ppid = p.pid;
        // THE OLD TONE's VALVE GOES WITH THE OLD TONE's NOTES: its products
        // under a key of their own, let go when the last of them is
        Key ak(ppid, -1, -1, AMPK);
        long li = S.live_find(ak);
        if (w.cache != p.cache && li >= 0 && !S.live[li].second.empty()) {
            Key rk(ppid, -1, -1, AMP_OLD0 + n0);
            std::vector<long> sl = S.live[li].second;
            S.live.erase(S.live.begin() + li);
            S.live.push_back(std::make_pair(rk, sl));
            S.own(rk, sl);
            auto o = S.oneshot.find(ak);
            if (o != S.oneshot.end()) {
                int v = o->second;
                S.oneshot.erase(o);
                S.oneshot[rk] = v;
            }
            amp_retired.push_back(std::make_pair(rk, std::make_pair(ppid, (const void *)p.cache)));
        }
        // ANOTHER ORGAN, ANOTHER CHEST (live's): the old one let go -- its
        // notes keep the wind they had, its rows freed once they end
        auto ws = wind_st.find(ppid);
        if (ws != wind_st.end()) {
            const OrganSpec *nog = w.drums ? nullptr : nv_tcache_organ(w.cache, w.program);
            if ((nog && nog->wind ? nog : nullptr) != ws->second.og) {
                for (auto &x : ws->second.rows)
                    wind_spent.push_back(x.second);
                if (ws->second.g)
                    nv_npy_free(ws->second.g);
                wind_st.erase(ws);
                wind_order.erase(std::remove(wind_order.begin(), wind_order.end(), ppid), wind_order.end());
            }
        }
        // ...AND OTHER STRINGS, ITS OWN FREE ONES (live._reg_forget): its free
        // rows end at their release, its state and what is queued for it go,
        // and the worker takes the new voice's bank
        if (w.bank && reg_on && w.pi == 0)
            reg_forget(w.bank, n0);
        if (w.program != p.program || w.cache != p.cache) {
            p.syn.clear();                      // A NEW PROGRAM IS A NEW PATCH: its knobs its own (Part.set_patch)
            p.mb.reset();
            p.syn_b.clear();
            p.mb_b.reset();
            p.syn_kept[0].clear();
            p.syn_kept[1].clear();
            p.drive = -1.0;                     // (an organ's drive knob too)
        }
        // THE SAME ORGAN BUILT AGAIN (a room switched to, a tuner changed: the
        // patch made anew, the voice the same -- its organ's tables the same)
        // KEEPS ITS REGISTRATION (live's set_patch)
        const OrganSpec *og_new = w.drums ? nullptr : nv_tcache_organ(w.cache, w.program);
        const bool keep_reg = og_new && og_new == p.organ && w.program == p.program && !p.drums && !w.drums
                              && (int)p.drawn.size() == og_new->n_rank;
        std::vector<char> kept = keep_reg ? p.drawn : std::vector<char>();
        p.cache = w.cache;
        p.program = w.program;
        p.drums = w.drums != 0;
        p.nbuckets = w.nbuckets;
        p.speed = w.speed;
        p.damper_pedal = w.damper_pedal;
        p.soft_drop = w.soft_drop;
        p.soft_top = w.soft_top;
        p.cres = 0.0;
        if (!w.choke.empty())
            p.choke = w.choke;
        p.organ = nullptr;
        p.drawn.clear();
        if (!p.drums)
            organ_start(p, nv_tcache_organ(p.cache, p.program));
            moog_sync_build(p);
        if (keep_reg)
            p.drawn = kept;
        if (w.pi == 0) {
            detune_wheel = w.detune_wheel != 0;
            if (!w.reg_note.empty())
                for (int k = 0; k < 128; k++)
                    reg_note[k] = w.reg_note[k] != 0;
        }
        if (w.pi == cur) {                      // (the patch in use: its working copy again, as use() loads it)
            cache = p.cache; nbuckets = p.nbuckets; speed = p.speed; damper_pedal = p.damper_pedal;
            soft_drop = p.soft_drop; soft_top = p.soft_top; drums = p.drums; program = p.program;
        }
        choke_p = &patches[cur].choke;
        // ...and everything keyed to the old voice: its wheel's drive step and tremolo
        drive_step.erase(ppid);
        trem_depth.erase(ppid);
        clav_step.erase(ppid);
        amp_dirty.erase(ppid);
        messenger_sync(p);                  // A MOOG PROGRAM SETS THE MESSENGER to it (queued)
        Use u(*this, w.pi);
        amp_touch(w.pi);
    }

    // live._amp_retire: an old tone's valve ends when the last of its notes has been let go
    void amp_retire(long long n0)
    {
        for (size_t i = 0; i < amp_retired.size();) {
            const Key &rk = amp_retired[i].first;
            long long ppid = amp_retired[i].second.first;
            const void *old = amp_retired[i].second.second;
            if (S.live_find(rk) < 0) {
                amp_retired.erase(amp_retired.begin() + i);
                continue;
            }
            bool any = false;
            for (auto &kv : S.live) {
                const Key &k = kv.first;
                if (std::get<0>(k) == ppid && std::get<1>(k) >= 0) {
                    auto t = key_tone.find(Key(std::get<0>(k), std::get<1>(k), std::get<2>(k), 0));
                    if (t != key_tone.end() && t->second == old) {
                        any = true;
                        break;
                    }
                }
            }
            if (!any) {
                S.release(rk, n0);
                amp_retired.erase(amp_retired.begin() + i);
                continue;
            }
            i++;
        }
    }

    // the panel's posts (live.post's set_stops and _swap_patch), after the block's events
    void run_posts(long long n0)
    {
        std::vector<Post> ps;
        ps.swap(posts);
        for (auto &q : ps) {
            if (q.kind == 1) {
                swap_patch(*q.swap, n0);
                continue;
            }
            if (q.kind == 2) {
                synth_post(q, n0);
                continue;
            }
            if (q.kind == 4) {                  // (a session's drive knob, after its swap)
                if (q.pi >= 0 && q.pi < (int)patches.size()) {
                    Patch &p = patches[q.pi];
                    p.drive = q.value < 0.0 ? -1.0 : q.value;
                    p.amp = p.drive >= 0.0 ? p.drive : p.amp0;
                    amp_dirty.insert(p.pid);
                }
                continue;
            }
            if (q.kind == 3) {                  // (a session's or preset's knob, after its swap)
                if (q.pi >= 0 && q.pi < (int)patches.size() && !set_synth(patches[q.pi], q.knob, q.value, q.layer)
                    && moog_spec(patches[q.pi], q.layer))
                    patches[q.pi].syn_kept[q.layer & 1][q.knob] = q.value;     // (refused: kept as written)
                continue;
            }
            const OrganSpec *og = patches[0].organ;
            if (!og)
                continue;
            // its names, of this organ's (none: its first in the crescendo, set_stops')
            std::vector<char> want(og->n_rank, 0);
            for (int ri = 0; ri < og->n_rank; ri++)
                for (auto &nm : q.names)
                    if (nm == og->rank[ri].key)
                        want[ri] = 1;
            set_stops(0, want, n0);
        }
    }

    // tonelib.GS_SOUND_NRPN: the CC an NRPN is, -1 none
    static int gs_sound_nrpn(int m, int l)
    {
        if (m != 1)
            return -1;
        switch (l) {
        case 0x08: return 76;
        case 0x09: return 77;
        case 0x0A: return 78;
        case 0x20: return 74;
        case 0x21: return 71;
        case 0x63: return 73;
        case 0x64: return 75;
        case 0x66: return 72;
        }
        return -1;
    }

    // live._sound_cc: one CC71-78 on channel ch. The release moves on the
    // notes whose key is still down (a release already running would jump);
    // the attack and decay are onset facts, for the next note
    // the class a part plays at a key (live's part.patch._voice_class), none on drums
    // mts.TuningStore.table: a bank and program's 128 Hz -- loaded, a
    // built-in tuner's (bank 0), else equal temperament
    std::vector<double> &mts_table(int b, int p)
    {
        auto key = std::make_pair(b, p);
        auto it = mts_tab.find(key);
        if (it != mts_tab.end())
            return it->second;
        static const char *BUILTIN[] = {"even", "hybrid", "hybridharm", "hybrid440", "hybridharm440", "stretch",
                                        "werckmeister", "sankey", "meantone", "well", "pyth", "just", "linear",
                                        "linear5", "linearwell", "bechstein", "spiral", "semi", "path", "dynamic"};
        std::vector<double> t(128);
        bool built = false;
        if (b == 0 && p >= 0 && p < (int)(sizeof BUILTIN / sizeof BUILTIN[0])) {
            double F[128];
            int have[128], all = 1;
            if (nv_tuning_table(BUILTIN[p], mts_ref_note, mts_ref_hz, F, have) == 0) {
                for (int k = 0; k < 128; k++)
                    all = all && have[k];
                if (all) {
                    t.assign(F, F + 128);
                    built = true;
                }
            }
        }
        if (!built)
            for (int k = 0; k < 128; k++)
                t[k] = 440.0 * pow(2.0, (k - 69) / 12.0);
        return mts_tab[key] = t;
    }

    std::pair<int, int> mts_selection(int ch) const
    {
        auto it = mts_sel.find(ch);
        return it == mts_sel.end() ? std::make_pair(0, 0) : it->second;
    }

    // live._sota_ratio: this channel's scale/octave factor for one written key
    double sota_ratio(int ch, int note) const
    {
        auto it = sota.find(ch);
        return it == sota.end() ? 1.0 : pow(2.0, it->second[((note % 12) + 12) % 12] / 1200.0);
    }

    // live._mts_ratio: the gm2 store's correction for one written key (the
    // selected table over the part's own, at the key it sounds)
    double mts_ratio(const Patch &p, int ch, int note)
    {
        if (p.drums || !nv_tcache_gm2(p.cache))
            return 1.0;
        int key = note + p.transpose;
        if (key < 0 || key >= 128)
            return 1.0;
        double base = nv_tcache_freq(p.cache, key);
        if (base == 0.0)
            return 1.0;
        auto s_ = mts_selection(ch);
        return mts_table(s_.first, s_.second)[key] / base;
    }

    // live._key_ratio: everything that tunes one key
    double key_ratio(const Patch &p, int ch, int note) { return sota_ratio(ch, note) * mts_ratio(p, ch, note); }

    // live._resota: this channel's sounding notes onto its table, each pitch
    // class against the ratio last applied to it
    void resota(int ch, long long n0)
    {
        bool moved = false;
        for (int pc = 0; pc < 12; pc++) {
            double want = sota_ratio(ch, pc);
            auto it = sota_at.find(std::make_pair(ch, pc));
            double was = it == sota_at.end() ? 1.0 : it->second;
            if (want == was)
                continue;
            sota_at[std::make_pair(ch, pc)] = want;
            std::vector<long> sl;
            for (auto &kv : S.live)
                if (std::get<1>(kv.first) == ch && ((std::get<2>(kv.first) % 12) + 12) % 12 == pc)
                    sl.insert(sl.end(), kv.second.begin(), kv.second.end());
            if (!sl.empty()) {
                retune(sl, n0, want / was);
                moved = true;
            }
        }
        if (moved)
            for (size_t pi = 0; pi < patches.size(); pi++)
                if (patches[pi].channel < 0 || patches[pi].channel == ch)
                    amp_touch((int)pi);
    }

    // live._remts: a gm2 part's sounding notes onto the tuning now in force
    // (the keys named, else every key sounding), each against what it had
    void remts(int ch, const std::vector<int> *keys, long long n0)
    {
        for (size_t pi = 0; pi < patches.size(); pi++) {
            const Patch &p = patches[pi];
            if (!(p.channel < 0 || p.channel == ch) || !nv_tcache_gm2(p.cache))
                continue;
            bool moved = false;
            std::set<int> pk;
            if (keys)
                pk.insert(keys->begin(), keys->end());
            else
                for (auto &kv : S.live)
                    if (std::get<0>(kv.first) == p.pid && std::get<1>(kv.first) == ch && std::get<2>(kv.first) >= 0)
                        pk.insert((int)std::get<2>(kv.first) + p.transpose);
            for (int key : pk) {
                int w = key - p.transpose;
                double want = mts_ratio(p, ch, w);
                auto mk = std::make_tuple(p.pid, ch, key);
                auto it = mts_at.find(mk);
                double was = it == mts_at.end() ? 1.0 : it->second;
                if (fabs(want - was) < 1e-15)
                    continue;
                std::vector<long> sl;
                for (auto &kv : S.live)
                    if (std::get<0>(kv.first) == p.pid && std::get<1>(kv.first) == ch && std::get<2>(kv.first) == w)
                        sl.insert(sl.end(), kv.second.begin(), kv.second.end());
                if (!sl.empty()) {
                    retune(sl, n0, want / was);
                    moved = true;
                }
                mts_at[mk] = want;
            }
            if (moved)
                amp_touch((int)pi);
        }
    }

    // live._sysex, its tunings: GM 2's scale/octave (each channel named, re-
    // tuned), MTS (the store loaded; a real-time single-note change moves the
    // keys it names on every channel playing from that program), the master
    // (fine and coarse: every channel re-pitched; the volume: nvlive refuses
    // it under full)
    // THE SOUND CANVAS'S DISPLAY (gsdisplay.Display): the text and dot pages
    // a GS file writes to the module's LCD, for the panel (nv_part_display);
    // the sound untouched. Written on the audio thread, read on the panel's
    // under a sequence count (odd: being written)
    struct GsDisplay {
        uint8_t mem[5][128] = {};
        int steps = 6;                      // the display time, 0.48 s a step
        char text[33] = {};
        double text_at = -1.0, page_at = -1.0;
        int page = 0;
    } gsd;
    std::atomic<unsigned> gsd_seq{0};
    static double gsd_now()
    {
        return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
    }
    gsd::Display gsd_live;                  // (the audio thread's; gsd its snapshot for the panel)
    // gsdisplay.parse and Display.apply (gsdisplay.h): true where it was one
    // of the display's; its state then published for the panel
    bool gs_display(const std::vector<uint8_t> &d)
    {
        if (!gsd_live.apply(d.data(), d.size(), gsd_now()))
            return false;
        gsd_seq.fetch_add(1);
        memcpy(gsd.mem, gsd_live.mem, sizeof gsd.mem);
        gsd.steps = gsd_live.steps;
        snprintf(gsd.text, sizeof gsd.text, "%s", gsd_live.text.c_str());
        gsd.text_at = gsd_live.text_at;
        gsd.page_at = gsd_live.page_at;
        gsd.page = gsd_live.page;
        gsd_seq.fetch_add(1);
        return true;
    }

    void sysex(const std::vector<uint8_t> &d, long long n0)
    {
        if (gs_display(d))
            return;
        // THE INSERTION EFFECT (gsefx.parse, live._sysex): its type, a
        // parameter, a send, a controller, or a part's assign
        {
            int ek, ea, eb;
            if (efx && nv_efx_parse(d.data(), (int)d.size(), &ek, &ea, &eb)) {
                if (ek == 5)
                    ea = ea % 16;               // (a part's channel: this port's)
                nv_efx_live_apply(efx, (double)n0 / rate, ek, ea, eb);
                return;
            }
        }
        int iv[4] = {0, 0, 0, 0};
        double dv[12], hz[128];
        int tk = nv_tuning_excl(d.data(), (int)d.size(), iv, dv, hz);
        if (tk == 4) {
            for (int c = 0; c < 16; c++)
                if (iv[0] & (1 << c)) {
                    std::array<double, 12> &t = sota[c];
                    for (int i = 0; i < 12; i++)
                        t[i] = dv[i];
                    resota(c, n0);
                }
        } else if (tk == 2) {
            std::vector<double> cur = mts_table(iv[0], iv[1]);
            std::vector<int> named;
            for (int k = 0; k < 128; k++)
                if (!std::isnan(hz[k])) {
                    cur[k] = hz[k];
                    named.push_back(k);
                }
            mts_tab[std::make_pair(iv[0], iv[1])] = cur;
            if (iv[2])
                for (int c = 0; c < 16; c++)
                    if (mts_selection(c) == std::make_pair(iv[0], iv[1]))
                        remts(c, &named, n0);
        } else if (tk == 1 && iv[0] == 1) {
            master_vol = dv[0];
        } else if (tk == 1 && iv[0] != 1) {
            (iv[0] == 2 ? master_fine : master_coarse) = dv[0];
            for (int c = 0; c < 16; c++)
                repitch(c, n0);
        } else if (tk == 0) {
            // GM SYSTEM ON (gm_on_level: 09 01, 09 03) OR GS RESET (parse_gs_reset)
            size_t n = d.size();
            bool gm = n >= 4 && d[0] == 0x7E && d[2] == 0x09 && (d[3] == 0x01 || d[3] == 0x03);
            bool gs = n >= 8 && d[0] == 0x41 && d[2] == 0x42 && d[3] == 0x12
                      && ((d[4] == 0x40 && d[5] == 0x00 && d[6] == 0x7F && d[7] == 0x00)
                          || (d[4] == 0x00 && d[5] == 0x00 && d[6] == 0x7F));
            if (gm || gs)
                power_on(n0);
        }
    }

    // live._sysex's reset: everything let go; the device's state, then each
    // channel's, back to power-on (the master tuning first, so each channel's
    // re-pitch lands on it); every part asked for program 0 (reset_asked)
    bool reset_asked = false;
    void power_on(long long n0)
    {
        panic(n0);
        if (efx)                                // the insertion effect Thru, every part off it
            nv_efx_live_apply(efx, (double)n0 / rate, 0, 0, 0);
        for (int c = 0; c < 256; c++)
            S.send[c] = 1.0;                    // every channel at the nominal distance
        master_fine = master_coarse = 0.0;
        master_vol = 1.0;
        for (int c = 0; c < 16; c++) {
            mono[c] = false;
            mono_stack[c].clear();
            mono_cur[c] = -1;
            modrange[c] = -1.0;
            for (int i = 0; i < 8; i++)
                snd_d[c][i] = 0.0;
            nrpn_msb[c] = nrpn_lsb[c] = 127;
        }
        mts_sel.clear();                        // (the store keeps its tables)
        for (int c = 0; c < 16; c++) {
            reset_controllers(c, n0);
            jobs_power_on(c, n0);
            vol[c] = 100;
            expr[c] = 127;
            control(c, 10, 64, n0);
            brange[c] = -1.0;                   // (live's bend_range, the session's, is not a file's)
            coarse[c] = 0.0;
            fine[c] = 0.0;
            repitch(c, n0);
            sota.erase(c);                      // ...and its scale: cleared, then re-applied
            resota(c, n0);
        }
        for (int c = 0; c < 16; c++) {
            cgain[c] = 1.0;
            cgain_set[c] = false;
        }
        reset_asked = true;
    }

    // live._meend_part: a part whose program's class meends (bend_detents)
    bool meend_part(const Patch &p) const
    {
        const NoteClass *k = p.drums ? nullptr : nv_tcache_class(p.cache, p.program);
        return k && k->meend;
    }

    // live._meend_ratio: this note's pitch ratio under the wheel, as a meend
    // -- the swaras above it (the raga's, else every key of the part's
    // table), Sa the raga's or the class's, over the channel's RPN 0 range or
    // the class's; false for a voice without detents
    bool meend_ratio(const Patch &p, int ch, int note, double *out) const
    {
        int n = note + p.transpose;
        const NoteClass *pc = key_class(p, n);
        if (!pc || !pc->meend)
            return false;
        int sa, rn = 0;
        double rsw[12];
        std::vector<double> sw;
        int rsa = nv_tcache_get_raga(p.cache, rsw, &rn);       // (its tuner a raga's: the part's patch's)
        if (rsa >= 0) {
            sa = rsa;
            sw.assign(rsw, rsw + rn);
        } else {
            sa = pc->meend_tonic;
            for (int k = 0; k < 12; k++)
                sw.push_back(1200.0 * log2(nv_tcache_freq(p.cache, sa + k) / nv_tcache_freq(p.cache, sa)));
        }
        if (!(n >= 0 && n < 128 && sa >= 0 && sa < 128))
            return false;
        double Fn = nv_tcache_freq(p.cache, n), Fs = nv_tcache_freq(p.cache, sa);
        if (Fn <= 0.0 || Fs <= 0.0)
            return false;
        double rng = brange[ch] >= 0.0 ? brange[ch] : pc->meend_range;
        double pull = 100.0 * rng * (double)wheel[ch] / 8192.0;
        double rest = pow(2.0, (rng * 0.0 / 8192.0 + coarse[ch] + fine[ch] / 100.0 + master_coarse
                                + master_fine / 100.0) / 12.0);
        *out = rest * pow(2.0, nv_meend_cents(1200.0 * log2(Fn / Fs), sw.data(), (int)sw.size(), 100.0 * rng, pull,
                                              pc->meend_strength) / 1200.0);
        return true;
    }

    // live._meend_retune: each sounding meend note (of these parts) to its own
    // ratio -- its played rows; the strings keep their pitch
    void meend_retune(int ch, const std::set<long long> &pids, long long n0)
    {
        for (auto &kv : S.live) {
            const Key &k = kv.first;
            if (!pids.count(std::get<0>(k)) || std::get<1>(k) != ch || std::get<3>(k) != -1 || kv.second.empty())
                continue;
            auto got = meend_at.find(k);
            if (got == meend_at.end())
                continue;
            const Patch *pp = nullptr;
            for (const Patch &p : patches)
                if (p.pid == std::get<0>(k))
                    pp = &p;
            double r;
            if (!pp || !meend_ratio(*pp, ch, (int)std::get<2>(k), &r) || r == got->second.first)
                continue;
            std::vector<long> idx = kv.second;
            auto sa = sym_at.find(k);
            std::vector<char> sym = sa != sym_at.end() ? sa->second : got->second.second;
            if (!sym.empty() && sym.size() == idx.size()) {
                std::vector<long> kept;
                for (size_t q = 0; q < idx.size(); q++)
                    if (!sym[q])
                        kept.push_back(idx[q]);
                idx.swap(kept);
            }
            if (!idx.empty())
                retune(idx, n0, r / got->second.first);
            got->second = std::make_pair(r, sym);
        }
    }

    const NoteClass *key_class(const Patch &p, int key) const
    {
        return p.drums ? nullptr : nv_tcache_class_key(p.cache, p.program, key);
    }

    // live._sound_stamp: at note-on, what the channel's CC71-78 ask of this
    // key's voice -- the times (attack, release, decay) and the vibrato's
    // delay, onset facts; the brightness/resonance gain, power kept, baked
    // into aL0 and recorded in sg (a Moog's rows its panel's: none here)
    void sound_stamp_note(const Patch &p, int ch, int key, const std::vector<long> &slots)
    {
        const NoteClass *k = key_class(p, key);
        if (!k || slots.empty())
            return;
        const double *d = snd_d[ch];
        auto has = [&](int i) { return ((k->snd_mask >> i) & 1) && d[i] != 0.0; };
        bool any = false;
        for (int i = 0; i < 8; i++)
            any = any || has(i);
        if (!any)
            return;
        std::vector<long> idx;
        for (long s : slots)
            if (S.i4[I4_fx][s] < 0)
                idx.push_back(s);
        if (idx.empty())
            return;
        if (has(2)) {                       // attack: sound_time_scale
            float f = (float)pow(4.0, d[2]);
            for (long s : idx)
                S.f4[F4_fa][s] *= f;
        }
        if (has(1)) {                       // release
            float r = (float)pow(4.0, d[1]);
            for (long s : idx) {
                S.f4[F4_re][s] *= r;
                S.sre[s] = r;
            }
        }
        if (has(4)) {                       // decay
            float kk = (float)(1.0 / pow(4.0, d[4]));
            for (long s : idx) {
                S.f4[F4_logr][s] *= kk;
                S.f4[F4_logrA][s] *= kk;
            }
        }
        if (has(7)) {                       // the vibrato's delay: sound_vib_delay
            float vd = (float)((d[7] > 0.0 ? d[7] : 0.0) * 1.0);
            for (long s : idx)
                S.f4n[3][s] = vd;
        }
        if (has(3) || has(0)) {             // brightness, resonance
            long n = (long)idx.size();
            std::vector<double> nf(n), amp(n), g(n);
            for (long i = 0; i < n; i++) {
                nf[i] = (double)S.f4[F4_nf][idx[i]];
                amp[i] = (double)S.aL0[idx[i]];
            }
            sound_shape(k, nf.data(), n, has(3) ? d[3] : 0.0, has(0) ? d[0] : 0.0, (k->snd_mask >> 3) & 1,
                        k->snd_mask & 1, g.data());
            normalise_power(amp.data(), n, g.data());
            for (long i = 0; i < n; i++) {
                long s = idx[i];
                float gf = (float)g[i];
                S.f4[F4_aL][s] *= gf;
                S.f4[F4_aR][s] *= gf;
                S.aL0[s] *= gf;
                S.aR0[s] *= gf;
                S.sg[s] = gf;
            }
        }
    }

    // live._reshape_sound: CC74/71 on a channel's sounding notes, each
    // against its un-shaped baseline (aL0 over sg), as new over old -- not a
    // plucked string's (plucked where it was plucked: the next note's)
    void reshape_sound(int ch)
    {
        const double *d = snd_d[ch];
        for (const Patch &p : patches) {
            if (p.drums || !(p.channel < 0 || p.channel == ch))
                continue;
            for (auto &kv : S.live) {
                const Key &kk = kv.first;
                if (std::get<0>(kk) != p.pid || std::get<1>(kk) != ch || std::get<2>(kk) < 0 || kv.second.empty())
                    continue;
                std::vector<long> idx;
                for (long s : kv.second)
                    if (S.i4[I4_fx][s] < 0)
                        idx.push_back(s);
                if (idx.empty())
                    continue;
                const NoteClass *k = key_class(p, (int)std::get<2>(kk) + transpose);
                if (!k || k->sh_pluck)
                    continue;
                auto has = [&](int i) { return ((k->snd_mask >> i) & 1) && d[i] != 0.0; };
                long n = (long)idx.size();
                std::vector<double> nf(n), base(n), g(n);
                for (long i = 0; i < n; i++) {
                    nf[i] = (double)S.f4[F4_nf][idx[i]];
                    base[i] = (double)(S.aL0[idx[i]] / std::max(S.sg[idx[i]], 1e-12f));
                }
                sound_shape(k, nf.data(), n, has(3) ? d[3] : 0.0, has(0) ? d[0] : 0.0, (k->snd_mask >> 3) & 1,
                            k->snd_mask & 1, g.data());
                normalise_power(base.data(), n, g.data());
                for (long i = 0; i < n; i++) {
                    long s = idx[i];
                    float gf = (float)g[i];
                    float r = gf / std::max(S.sg[s], 1e-12f);
                    S.f4[F4_aL][s] *= r;
                    S.f4[F4_aR][s] *= r;
                    S.aL0[s] *= r;
                    S.aR0[s] *= r;
                    S.sg[s] = gf;
                }
            }
        }
    }

    // live._moog_panel_for (layer A): the part's panel with its channel's
    // GM sound controllers on it (moog.apply_gm) -- those its voice answers
    // at middle C (_snd_for at 60 - transpose); null if not a Moog
    const MoogLayer *moog_panel(const Patch &p, int ch, MoogLayer &out, int layer = 0) const
    {
        const MoogLayer *base = layer ? (p.mb_b ? p.mb_b.get() : p.moog_b) : (p.mb ? p.mb.get() : p.moog);
        if (!base)
            return nullptr;
        const NoteClass *k = ch >= 0 ? key_class(p, 60) : nullptr;
        if (!k)
            return base;
        double d[8];
        bool any = false;
        for (int i = 0; i < 8; i++) {
            d[i] = ((k->snd_mask >> i) & 1) ? snd_d[ch][i] : 0.0;
            any = any || d[i] != 0.0;
        }
        if (!any)
            return base;
        nv_moog_apply(base, d, &out);
        return &out;
    }

    // live._moog_refresh: a Moog part's panel changed -- its knob rows ramp
    // to the new values over the next block, its sounding notes' filter rows
    // are rebuilt and their partials re-weighed; per channel (only_ch, or
    // every one), each with its own sound controllers
    void moog_refresh(const Patch &p, long long n0, int only_ch = -2)
    {
        // BY CHANNEL AND LAYER: a layered voice's two Messengers each with
        // its own panel, its slots told apart by their row's layer
        std::vector<std::pair<std::pair<long long, int>, std::vector<long>>> by_ch;
        auto at = [&](long long ch, int lay) -> std::vector<long> & {
            for (auto &b : by_ch)
                if (b.first == std::make_pair(ch, lay))
                    return b.second;
            by_ch.emplace_back(std::make_pair(ch, lay), std::vector<long>());
            return by_ch.back().second;
        };
        for (auto &kv : S.live)
            if (std::get<0>(kv.first) == p.pid && !kv.second.empty()
                && (only_ch == -2 || std::get<1>(kv.first) == only_ch))
                for (long s : kv.second) {
                    int r = S.i4[I4_fx][s];
                    at(std::get<1>(kv.first), r >= 0 ? S.ft_layer[r] : 0).push_back(s);
                }
        for (auto &kk : S.kn_of)
            if (std::get<0>(kk.first) == p.pid && (only_ch == -2 || std::get<1>(kk.first) == only_ch))
                at(std::get<1>(kk.first), std::get<2>(kk.first));
        Slab::Retune rt = [&](const std::vector<long> &idx, const std::vector<double> &sc) {
            for (size_t i = 0; i < idx.size(); i++)
                retune(std::vector<long>(1, idx[i]), n0, sc[i]);
        };
        for (auto &b : by_ch) {
            long long ch = b.first.first;
            int lay = b.first.second;
            MoogLayer La;
            const MoogLayer *L = moog_panel(p, (int)ch, La, lay);
            if (!L)
                continue;
            S.set_knobs(S.knob_row(std::make_tuple(p.pid, ch, lay), L->kn), L->kn, true);
            std::vector<long> idx;
            for (long s : b.second)
                if (S.i4[I4_fx][s] >= 0)
                    idx.push_back(s);
            if (idx.empty())
                continue;
            S.moog_rows(idx, L, rate);
            S.moog_pitch(idx, L);
            std::vector<long> sw = S.moog_shape(idx, L);
            std::vector<long> mo;
            for (long s : idx)
                if (S.i4[I4_mk][s] > 0)
                    mo.push_back(s);
            if (!mo.empty())
                S.moog_retimbre(mo, L, rate, &rt, n0);
            for (long s : sw) {             // a representation switched: no ramp across it
                S.aLp[s] = S.f4[F4_aL][s];
                S.aRp[s] = S.f4[F4_aR][s];
            }
            for (int r : S.rows_of(idx))
                S.moog_fm(r, idx, L);
        }
        // an amplifier after the ladder (the charang) distorts what the
        // filter passed: its products recomputed from the new levels
        if (p.amp > 0.0)
            amp_dirty.insert(p.pid);
    }

    void sound_cc(int ch, int cc, double v, long long n0)
    {
        double d = (v - 64.0) / 64.0;
        snd_d[ch][cc - 71] = d;
        sound_cc_notes(ch, cc, d, n0);
        // attack, decay, vib_delay are onset facts, for the next note --
        // except on a Moog, where CC71-75 are its panel's knobs and move as
        // knobs do
        if (cc <= 75)
            for (const Patch &p : patches)
                if (p.moog && !p.drums && (p.channel < 0 || p.channel == ch))
                    moog_refresh(p, n0, ch);
    }

    void sound_cc_notes(int ch, int cc, double d, long long n0)
    {
        if (cc == 71 || cc == 74) {         // brightness, resonance: on the notes sounding
            reshape_sound(ch);
            return;
        }
        if (cc == 76 || cc == 77) {
            // THE VIBRATO's RATE AND DEPTH (live: _vib_apply on each part
            // whose voice answers this one), with the wheel's, written once
            for (const Patch &p : patches)
                if (!p.drums && (p.channel < 0 || p.channel == ch) && (p.snd >> (cc - 71)) & 1)
                    vib_apply(p, ch, n0);
            return;
        }
        if (cc != 72)
            return;
        for (const Patch &p : patches) {
            // the release on the notes whose key is still down (live's, a
            // voice with no ranks: each key's own grant)
            if (p.organ || p.drums || !(p.channel < 0 || p.channel == ch))
                continue;
            for (auto &kv : S.live) {
                if (std::get<0>(kv.first) != p.pid || std::get<1>(kv.first) != ch || kv.second.empty())
                    continue;
                const NoteClass *k = key_class(p, (int)std::get<2>(kv.first) + transpose);
                float nw = k && ((k->snd_mask >> 1) & 1) && d != 0.0 ? (float)pow(4.0, d) : 1.0f;
                for (long s : kv.second) {
                    if (S.i8[1][s] != IDLE || S.i4[I4_fx][s] >= 0)
                        continue;
                    S.f4[F4_re][s] *= nw / std::max(S.sre[s], 1e-12f);
                    S.sre[s] = nw;
                }
            }
        }
        for (size_t pi = 0; pi < patches.size(); pi++) {
            const OrganSpec *og = patches[pi].organ;
            if (!og || !(patches[pi].channel < 0 || patches[pi].channel == ch))
                continue;
            float nw = (og->snd_mask & 2) && d != 0.0 ? (float)pow(4.0, d) : 1.0f;
            for (auto &kv : S.live) {
                if (std::get<0>(kv.first) != patches[pi].pid || std::get<1>(kv.first) != ch)
                    continue;
                for (long s : kv.second) {
                    if (S.i8[1][s] != IDLE || S.i4[4][s] >= 0)
                        continue;
                    S.f4[F4_re][s] *= nw / std::max(S.sre[s], 1e-12f);
                    S.sre[s] = nw;
                }
            }
        }
    }

    // live._sound_stamp on a part's slots: the times its channel asks of them
    void sound_stamp(const OrganSpec *og, int ch, const std::vector<long> &sl)
    {
        const double *d = snd_d[ch];
        bool at = (og->snd_mask & 1) && d[2] != 0.0, rl = (og->snd_mask & 2) && d[1] != 0.0,
             dc = (og->snd_mask & 4) && d[4] != 0.0;
        if (!(at || rl || dc))
            return;
        float fa = at ? (float)pow(4.0, d[2]) : 1.0f, r = rl ? (float)pow(4.0, d[1]) : 1.0f,
              k = dc ? (float)(1.0 / pow(4.0, d[4])) : 1.0f;
        for (long s : sl) {
            if (S.i4[4][s] >= 0)                // (a Moog's CC71-75 are its panel)
                continue;
            if (at)
                S.f4[F4_fa][s] *= fa;
            if (rl) {
                S.f4[F4_re][s] *= r;
                S.sre[s] = r;
            }
            if (dc) {
                S.f4[F4_logr][s] *= k;
                S.f4[F4_logrA][s] *= k;
            }
        }
    }

    // whether a harmonium (a stop word on CC43) is a part here
    bool harmonium_on() const
    {
        for (const Patch &p : patches)
            if (p.organ && p.organ->wccs[0] == 43)
                return true;
        return false;
    }

    // whether a Hammond part (on a rotor, or its wheel a swell) listens on channel ch
    bool hammond_on(int ch) const
    {
        for (const Patch &p : patches)
            if ((p.leslie || p.wheel_swell || p.amp > 0.0) && (p.channel < 0 || p.channel == ch))
                return true;
        return false;
    }

    // whether a part with a wheel tremolo listens on channel ch
    bool wheel_trem_on(int ch) const
    {
        for (const Patch &p : patches)
            if (p.wtrem > 0.0 && (p.channel < 0 || p.channel == ch))
                return true;
        return false;
    }

    // whether an organ part listens on channel ch
    bool organ_on(int ch) const
    {
        for (const Patch &p : patches)
            if (p.organ && p.organ->n_order && (p.channel < 0 || p.channel == ch))
                return true;
        return false;
    }

    // live._wind_row: the slab row rank ri of this organ part rides (0: none),
    // the part's chest made at its first rank
    int wind_row(int ri)
    {
        const OrganSpec *og = patches[cur].organ;
        auto it = wind_st.find(pid);
        if (it == wind_st.end()) {
            WindSt &st = wind_st[pid];
            wind_order.push_back(pid);
            st.og = og;
            st.g = nv_npy_new(0x5EED + (unsigned long long)pid);
            for (int r = 0; r < og->n_rank; r++) {
                if (!og->rank[r].n_ratio)
                    continue;
                std::pair<double, double> ab(og->fam_a[r], og->fam_b[r]);
                int row = 0;
                for (auto &x : st.rows)
                    if (x.first == ab)
                        row = x.second;
                if (!row) {
                    if (!wind_free.empty()) {           // a row an old chest gave back
                        row = wind_free.front();
                        wind_free.pop_front();
                    } else if (wind_next > WIND_ROWS) {
                        continue;
                    } else {
                        row = wind_next++;
                    }
                    st.rows.push_back(std::make_pair(ab, row));
                    st.acc[row] = 0.0;
                }
                st.rank_row[r] = row;
            }
            it = wind_st.find(pid);
        }
        return it->second.rank_row[ri];
    }

    // live._draw: rank ri of the key's template stamped -- at the part's gain,
    // the channel's, and the key's touch -- on its chest's row
    void draw_rank(const nv::live::Template &T, int ch, int note, int ri, long long n0)
    {
        if (ri >= (int)T.ranks.size() || !T.ranks[ri].P)
            return;
        const nv::live::Template &R = T.ranks[ri];
        Key key(pid, ch, note, rank_layer(patches[cur].organ, ri));
        auto nt = note_touch.find(std::make_pair(ch, note));
        double scale = pow(10.0, level_db / 20.0) * swell * chan_gain(ch) * (nt != note_touch.end() ? nt->second : 1.0);
        const double *f8p[6];
        const float *f4p[27];
        const long long *i8p[2];
        const int32_t *i4p[6];
        for (int c = 0; c < 6; c++)
            f8p[c] = R.f8[c].data();
        for (int c = 0; c < 27; c++)
            f4p[c] = R.f4[c].data();
        for (int c = 0; c < 2; c++)
            i8p[c] = R.i8[c].data();
        for (int c = 0; c < 6; c++)
            i4p[c] = R.i4[c].data();
        if (!S.stamp(f8p, f4p, i8p, i4p, R.hrel.data(), R.P, key, n0, scale, 0, false, NAN, ch,
                     R.sof.empty() ? nullptr : R.sof.data(), R.rof.empty() ? nullptr : R.rof.data(), 0.0, 0.0,
                     R.cof.empty() ? nullptr : R.cof.data())) {
            dropped++;
            return;
        }
        const OrganSpec *og = patches[cur].organ;
        if (og->wccs[0] == 43)              // a harmonium's effect stops (_harmonium_stamp)
            harmonium_stamp(T, R, ch, note, ri, key);
        auto td = trem_depth.find(pid);     // the wheel's tremolo, the wheel already up
        if (td != trem_depth.end() && td->second > 0.0)
            S.tremolo_arm(S.last_slots, td->second, og->wtrem_stereo);
        if (og->wind) {
            int wr = wind_row(ri);
            if (wr > 0)
                for (long s : S.last_slots)
                    S.i4[I4_br][s] = wr;
        }
        {
            auto si = siren_find(SKey(pid, ch, note));      // each row of holes turns with its own disc
            if (si != siren_st.end() && !si->second.rows.empty()) {
                int rw = (og->siren_up >> ri) & 1 ? si->second.rows.back() : si->second.rows[0];
                for (long s : S.last_slots)
                    S.i4[I4_br][s] = rw;
            }
        }
        if (patches[cur].leslie && !S.les.empty())    // onto the rotors, at their rates now
            S.leslie_arm(S.last_slots, R.f4[24].data(), R.f4[2].data(), R.lflip.empty() ? nullptr : R.lflip.data(),
                         n0, rotor_horn.rate, rotor_drum.rate, nullptr, lobe_of_t(R));
        if (patches[cur].scanner)                     // the scanner's selector, last (_scan_stamp)
            scan_stamp(R, ch, note, ri, n0, scale, std::vector<long>(S.last_slots));
    }

    // live._note_on's organ path: every rank drawn, in the stops' order (a
    // pipe organ has no touch: a key is open or shut)
    void organ_strike(const nv::live::Template &T, int ch, int note, int vel, long long n0, double tf = 1.0)
    {
        note_touch[std::make_pair(ch, note)] = tf;
        const std::vector<char> &dr = patches[cur].drawn;
        for (int ri = 0; ri < (int)dr.size(); ri++)
            if (dr[ri])
                draw_rank(T, ch, note, ri, n0);
        if (!T.jacks.empty())
            held_jacks[Key(pid, ch, note, 0)] = std::make_pair(&T, patches[cur].organ);   // its jacks' clicks, at the key-up
        // ...AND A HARPSICHORD'S KEY LIFTS EVERY CHOIR'S DAMPER: the strings
        // its drawn stops pluck drive the rest through the bridge, its own
        // key's undrawn choirs among them -- the pluck's rows only (the
        // quill's catch ends at the slip), in the stops' order
        const OrganSpec *og = patches[cur].organ;
        if (reg_on && cur_reg && reg_note[note] && og->n_choir) {
            std::vector<long> sl;
            std::map<long, long> sc;
            std::set<int> pk;
            for (int ri = 0; ri < og->n_rank; ri++) {
                if (!dr[ri] || og->rank_choir[ri] < 0)
                    continue;
                long li = S.live_find(Key(pid, ch, note, rank_layer(og, ri)));
                if (li < 0)
                    continue;
                for (long s : S.live[li].second)
                    if (S.i8[1][s] == IDLE && !sc.count(s)) {
                        sc[s] = og->rank_choir[ri];
                        sl.push_back(s);
                        pk.insert(og->rank_choir[ri]);
                    }
            }
            if (!sc.empty()) {
                std::vector<int> pv(pk.begin(), pk.end());
                reg_strike(ch, note, n0, T, sl, &pv, &sc);
            }
        }
        // ...AND ITS EFFECT, the module's or the tone's own (live's organ path:
        // Bit Hit's Lo-Fi on an orchestra hit's sections), on every drawn rank,
        // in the stops' order -- then its copies (_tap_arm)
        std::vector<long> rs;
        for (int ri = 0; ri < (int)dr.size(); ri++) {
            if (!dr[ri])
                continue;
            long li = S.live_find(Key(pid, ch, note, rank_layer(og, ri)));
            if (li >= 0)
                rs.insert(rs.end(), S.live[li].second.begin(), S.live[li].second.end());
        }
        if (!rs.empty()) {
            int ec = ch;
            if (efx_note(ch, note, vel, n0, rs, &ec)) {
                tap_tables();
                tap_arm(ec, rs);
            }
        }
    }

    // live._key_up_jacks: a harpsichord's jacks falling back -- one click a
    // stop that sounded on this key, at the note's own level, a one-shot
    void key_up_jacks(int ch, int note, long long n0, const std::set<std::string> &sounded)
    {
        auto it = held_jacks.find(Key(pid, ch, note, 0));
        if (it == held_jacks.end())
            return;
        const nv::live::Template &T = *it->second.first;
        const OrganSpec *jog = it->second.second;
        held_jacks.erase(it);
        auto nt = note_touch.find(std::make_pair(ch, note));
        double scale = pow(10.0, level_db / 20.0) * swell * chan_gain(ch) * (nt != note_touch.end() ? nt->second : 1.0);
        for (size_t q = 0; q < T.jacks.size(); q++) {
            int ri = T.jack_rank[q];
            if (!jog || ri >= jog->n_rank || !sounded.count(jog->rank[ri].key))
                continue;                   // (a stop that sounded on this key, by its name)
            long long jl = rank_layer(jog, ri) - RANK0;
            const nv::live::Template &J = T.jacks[q];
            const double *f8p[6];
            const float *f4p[27];
            const long long *i8p[2];
            const int32_t *i4p[6];
            for (int c = 0; c < 6; c++)
                f8p[c] = J.f8[c].data();
            for (int c = 0; c < 27; c++)
                f4p[c] = J.f4[c].data();
            for (int c = 0; c < 2; c++)
                i8p[c] = J.i8[c].data();
            for (int c = 0; c < 6; c++)
                i4p[c] = J.i4[c].data();
            Key key(pid, ch, note, KEYUP0 + jl);
            if (!S.stamp(f8p, f4p, i8p, i4p, J.hrel.data(), J.P, key, n0, scale, J.dur, true, NAN, ch, nullptr,
                         nullptr, 0.0, 0.0, J.cof.data())) {
                dropped++;
                continue;
            }
            std::vector<long> got = S.last_slots;
            long li = S.live_find(key);
            if (li >= 0)
                S.live.erase(S.live.begin() + li);      // it retires on its own; never released
            if (cpan[ch] != 64)
                S.repan(got, cpan[ch], 64, rate, true);
        }
    }

    // live.set_stops: draw and retire ranks to match want, on every key
    // already down (each drawn at velocity 127's template), in the stops' order
    void set_stops(int pi, std::vector<char> want, long long n0)
    {
        Use u(*this, pi);
        const OrganSpec *og = patches[cur].organ;
        bool any = false;
        for (char w : want)
            any = any || w;
        if (!any && og->n_order)
            want[og->order[0]] = 1;
        std::vector<char> &dr = patches[cur].drawn;
        for (int ri = 0; ri < og->n_rank; ri++) {
            if (!want[ri] || dr[ri])
                continue;
            for (auto &d : down) {
                if (!claims(pi, d.first, d.second))
                    continue;
                int sn = d.second + transpose;
                if (sn < 0 || sn > 127)
                    continue;
                const nv::live::Template *T = nv_tcache_lookup(cache, sn, bucket(127), speed);
                if (T)
                    draw_rank(*T, d.first, d.second, ri, n0);
            }
        }
        for (int ri = 0; ri < og->n_rank; ri++) {
            if (!dr[ri] || want[ri])
                continue;
            std::vector<Key> ks;
            long long rl = rank_layer(og, ri);
            for (auto &kv : S.live)         // (by its stop's name, as live keys it: one an old organ stamped too)
                if (std::get<0>(kv.first) == pid && std::get<3>(kv.first) == rl)
                    ks.push_back(kv.first);
            for (auto &k : ks)
                S.release(k, n0);
        }
        dr = want;
        amp_touch(pi);                      // a drawbar is a parent: the valve's products are stale
    }

    // live._crescendo: the mod wheel adds stops in the organ's own order
    void crescendo(int pi, int v, long long n0)
    {
        Patch &p = patches[pi];
        const OrganSpec *og = p.organ;
        p.cres = v / 127.0;
        int n = (int)(p.cres * og->n_order + 1e-9);
        std::vector<char> want(og->n_rank, 0);
        for (int q = 0; q < std::max(1, n) && q < og->n_order; q++)
            want[og->order[q]] = 1;
        set_stops(pi, want, n0);
    }

    // live._wind_block: every organ part's chest, one block on -- its demand
    // from its ranks sounding, the pressure (wind.Wind.blocks for one block),
    // a row a family: this block's ratio, the phase accrued, the level at its edges
    void wind_block(long long n0, long long frames)
    {
        (void)n0;
        // AN OLD CHEST's ROWS, FREE AGAIN once no note rides them: at rest
        for (size_t i = 0; i < wind_spent.size();) {
            int row = wind_spent[i];
            bool rides = false;
            for (long q = 0; q < S.cap && !rides; q++)
                rides = S.busy[q] && S.i4[I4_br][q] == row;
            if (rides) {
                i++;
                continue;
            }
            wind_spent.erase(wind_spent.begin() + i);
            BRt[row] = 1.0f;
            BCt[row] = 0.0;
            BLt[2 * row] = 1.0f;
            BLt[2 * row + 1] = 1.0f;
            wind_free.push_back(row);
        }
        for (size_t pi = 0; pi < patches.size(); pi++) {
            auto it = wind_st.find(patches[pi].pid);
            if (it == wind_st.end())
                continue;
            WindSt &st = it->second;
            const OrganSpec *og = st.og;
            int tp = patches[pi].transpose;
            double dem = 0.0;
            for (auto &kv : S.live) {
                if (std::get<0>(kv.first) != patches[pi].pid)
                    continue;
                // ...A RANK BY ITS STOP's NAME (live's `k[3] in ratios`): one
                // stamped by another organ, before a program change, draws on
                // this chest where it shares a name with one of its ranks
                long long ri = rank_of(og, std::get<3>(kv.first));
                if (ri < 0 || ri >= og->n_rank || !og->rank[ri].n_ratio || !st.rank_row[ri])
                    continue;
                const OrganRank &rk = og->rank[ri];
                double f = 440.0 * pow(2.0, (std::get<2>(kv.first) + tp - 69) / 12.0);
                double d[8];
                for (int q = 0; q < rk.n_ratio; q++)
                    d[q] = pow(std::max(f * rk.ratio[q], 8.0) / og->unit_hz, og->draw_exp);
                dem += pysum(d, rk.n_ratio);
            }
            bool on = og->trem_rank >= 0 && patches[pi].drawn[og->trem_rank];
            // the pressure, SUB 8 points across this block
            double w0 = st.w2;
            if (og->wander_rms > 0.0) {
                double z = nv_npy_next(st.g);
                st.w1 = og->wa * st.w1 + (1.0 - og->wa) * z;
                st.w2 = og->wa * st.w2 + (1.0 - og->wa) * st.w1;
            }
            auto dev = [&]() {
                double d = st.s1 - (og->has_ra ? og->reg_restore * st.r1 : 0.0);
                return og->sag_max > 0.0 ? og->sag_max * tanh(d / og->sag_max) : d;
            };
            double s0 = dev();
            if (og->sag_per_unit > 0.0) {
                double sn = og->c1 * st.s1 + og->c2 * st.s2 + og->g * st.d1;
                st.s2 = st.s1;
                st.s1 = sn;
                st.d1 = dem * og->sag_per_unit;
                if (og->has_ra)
                    st.r1 = og->ra * st.r1 + (1.0 - og->ra) * st.s1;
            }
            double sv1 = dev();
            if (on && !st.was_on && st.te < 1e-4)
                st.tph = 0.0;
            st.was_on = on;
            double tgt = on ? 1.0 : 0.0, e0 = st.te;
            st.te = tgt + (st.te - tgt) * og->tdecay;
            if (!on && st.te < 1e-6)
                st.te = 0.0;
            bool tr = e0 > 0.0 || st.te > 0.0;
            double p[9];
            for (int j = 0; j <= 8; j++) {
                double fr = j / 8.0;
                double wv = (w0 + (st.w2 - w0) * fr) * (og->wgain * og->wander_rms);
                double sv = s0 + (sv1 - s0) * fr;
                double tv = 0.0;
                if (tr) {
                    double ev = e0 + (st.te - e0) * fr;
                    tv = og->trem_depth * ev * sin(2.0 * M_PI * (st.tph + og->trem_hz * og->blk_s * fr));
                }
                p[j] = 1.0 + wv - sv + tv;
            }
            st.tph = fmod(st.tph + og->trem_hz * og->blk_s, 1.0);
            for (auto &x : st.rows) {
                double a = x.first.first, b = x.first.second;
                int row = x.second;
                double sum = pow(p[0], a);
                for (int j = 1; j < 8; j++)
                    sum = sum + pow(p[j], a);
                BRt[row] = (float)(sum / 8.0);
                BCt[row] = st.acc[row];
                BLt[2 * row] = (float)pow(p[0], b);
                BLt[2 * row + 1] = (float)pow(p[8], b);
                st.acc[row] += ((double)BRt[row] - 1.0) * frames;
            }
        }
    }

    // A SLURRED NOTE MAKES NO PUSH OF ITS OWN -- the bellows is already
    // moving -- but TAKES OVER the one under way, where it stands (live's
    // _slur_stamp, first: the template's push rows, a note from silence's,
    // by the push's rise and their own fall since it began, their fade the
    // legato attack's; none under way, silent)
    std::map<int, long long> push_t0;       // channel -> sample its bellows' push began
    void slur_push(int ch, int note, long long n0, const nv::live::Template &T)
    {
        const std::vector<long> &sl = S.last_slots;
        if (T.push.empty() || sl.size() != T.push.size()
            || std::find(T.push.begin(), T.push.end(), 1) == T.push.end())
            return;
        auto it = push_t0.find(ch);
        bool on = it != push_t0.end() && n0 > it->second;
        double dt = on ? (double)(n0 - it->second) / rate : 0.0, rise = 0.1;
        float sfa = (float)(0.005 * rate);
        if (on) {
            const NoteClass *k = nv_tcache_note_class(cache, program, note);
            if (k)
                rise = std::max(k->push_rise_s, 1e-4);
            double sf[3];
            if (nv_tcache_slur_fade(cache, program, note, sf))
                sfa = (float)(std::max(1e-4, sf[0]) * rate);
        }
        for (size_t q = 0; q < sl.size(); q++) {
            if (!T.push[q])
                continue;
            long s = sl[q];
            float env = 0.0f;
            if (on) {
                env = (float)(std::min(1.0, dt / rise) * exp(-(double)S.f4[F4_logr][s] * dt));
                S.f4[F4_fa][s] = std::min(S.f4[F4_fa][s], sfa);
            }
            S.f4[F4_aL][s] *= env;
            S.f4[F4_aR][s] *= env;
            S.ls_aL[s] *= env;              // (a rig's cached level, which would put them back)
            S.ls_aR[s] *= env;
        }
    }

    // live._slur_stamp: the slots just stamped given the voice's legato
    // attack -- the rows whose fade is the attack's (fa_at), their fade and
    // chiff no longer than its, under the note's caps
    void slur_stamp(int note, const nv::live::Template &T)
    {
        double sf[3];
        if (!nv_tcache_slur_fade(cache, program, note, sf))
            return;
        const std::vector<long> &sl = S.last_slots;
        if ((long)sl.size() != (long)T.fa_at.size())
            return;
        double dur = T.dur ? T.dur / rate : 1.0;
        float fa = (float)(std::max(1e-4, std::min(sf[0], sf[2] * dur)) * rate);
        float chf = (float)(std::max(1e-4, std::min(sf[1], 0.45 * dur)) * rate);
        for (size_t q = 0; q < sl.size(); q++) {
            if (!T.fa_at[q])
                continue;
            long s = sl[q];
            if (fa < S.f4[F4_fa][s])
                S.f4[F4_fa][s] = fa;
            if (chf < S.f4[F4_ch][s])
                S.f4[F4_ch][s] = chf;
        }
    }

    // a key up (live's note-off): in MONO, the sounding key's voice back to
    // the last key still held (struck again), or nothing if the voice had
    // gone on already; then, as ever, the damper or the release
    void note_off(int ch, int note, long long n0)
    {
        down.erase(std::make_pair(ch, note));
        legato_off(ch, note, n0);
        if (mono[ch]) {
            std::vector<std::pair<int, int>> &st = mono_stack[ch];
            for (size_t i = 0; i < st.size();)
                if (st[i].first == note)
                    st.erase(st.begin() + i);
                else
                    i++;
            if (mono_cur[ch] != note)
                return;                             // already handed over: nothing sounds for it
            if (!st.empty()) {
                std::pair<int, int> back = st.back();
                legato_take(ch, note);
                mono_cut(ch, note, n0);
                mono_cur[ch] = back.first;
                glide_from = porta_on[ch] ? note : -1;
                moog_src = note;
                last_on[ch] = back.first;
                std::vector<int> cl = claimers(ch, back.first);
                if (cl.size() <= 1)
                    strike(ch, back.first, back.second, n0, true);     // back to a key still held: a slur too
                else
                    for (int i : cl) {
                        Force f(*this, i);
                        strike(ch, back.first, back.second, n0, true);
                    }
                glide_from = moog_src = -1;
                legato_age.clear();
                return;
            }
            mono_cur[ch] = -1;                      // last key up: an ordinary release
        }
        std::vector<int> cl = claimers(ch, note);
        if (cl.size() > 1) {                        // A LAYER EACH (live's loop): its flick, its pedal, its release
            bool held = false;
            for (int i : cl) {
                Force f(*this, i);
                if (cut_off(ch, note, n0))
                    continue;
                Use u(*this, i);
                auto sq = sost.find(ch);
                if ((pedal_holds(ch, note) || (sq != sost.end() && sq->second.count(note))) && damper_pedal) {
                    held = true;
                    continue;
                }
                if (open_ring_hold(i, ch, note))
                    continue;                       // an open string: the palm, not the key, stops it
                let_go(ch, note, n0);
            }
            if (held)
                pedalled.insert(std::make_pair(ch, note));
            return;
        }
        if (cut_off(ch, note, n0))
            return;                                 // let go in its flick: the note never came
        int pi = patch_for(ch, note);
        Use u(*this, pi < 0 ? cur : pi);
        auto sq = sost.find(ch);
        if ((pedal_holds(ch, note) || (sq != sost.end() && sq->second.count(note))) && damper_pedal) {
            pedalled.insert(std::make_pair(ch, note));
            return;
        }
        if (open_ring_hold(pi < 0 ? cur : pi, ch, note))
            return;                                 // an open string: the palm, not the key, stops it
        let_go(ch, note, n0);
    }

    // the part's note let go (live._note_off): released, its forced register
    // rows with it, and its damper told
    void let_go(int ch, int note, long long n0)
    {
        int pi = patch_for(ch, note);
        Use u(*this, pi < 0 ? cur : pi);
        n0 += amp_ahead();                  // (a part with a valve: late, as its notes began)
        n0 += amp_held(pid, ch, note);      // (...and held, as long as it was played)
        amp_touch(cur);
        auto kt = key_tone.find(Key(pid, ch, note, 0));
        if (valved(cur) && (kt == key_tone.end() || kt->second == patches[cur].cache) && !amp_holds(cur))
            S.release(Key(pid, -1, -1, AMPK), n0);  // the products end with their chord (a note of this tone's)
        {                                   // the auto wah's envelope lets go: ch's, and ch's tones'
            std::vector<int> ecs{ch};
            for (const auto &kv : tone_fx)
                if (kv.second.ch == ch)
                    ecs.push_back(kv.first);
            for (int c : ecs) {
                auto en = efx_notes.find(c);
                if (en != efx_notes.end())
                    for (EfxNote &e : en->second)
                        if (e.note == note && std::isinf(e.s1))
                            e.s1 = (double)n0 / rate;
            }
        }
        {
            // A SIREN's KEY-UP ENDS ITS DRIVE, not its sound: the fire siren
            // coasts (no sooner than its GS length), the double siren's air
            // runs out -- and siren_block lets the note go when it has
            auto si = siren_find(SKey(pid, ch, note));
            if (si != siren_st.end() && si->second.down) {
                si->second.down = false;
                long long at = n0;
                auto tx = tex_on.find(Key(pid, ch, note, -1));
                if (tx != tex_on.end()) {
                    at = std::max(n0, tx->second);
                    tex_on.erase(tx);
                }
                si->second.ends = true;
                si->second.drive_end = at;
                Key k(pid, ch, note, -1);
                tex_gen.erase(std::remove_if(tex_gen.begin(), tex_gen.end(),
                                             [&](const TexGen &g) { return g.key == k; }),
                              tex_gen.end());
                return;
            }
        }
        if (drone_class() || dnote_class()) {   // a chanter's key: the drones wait part_break_s (_drone_reap)
            const NoteClass *dk = drone_class() ? drone_class() : dnote_class();
            S.release(Key(pid, ch, note, -1), n0);
            if (!chanting(ch))
                drone_quiet[pid] = DroneQuiet{ch, n0, (long long)(dk->part_break_s * rate)};
            return;
        }
        if (patches[cur].organ) {           // an organ's key: each of its ranks
            std::vector<Key> ks;
            std::set<std::string> sounded;
            for (auto &kv : S.live)
                if (std::get<0>(kv.first) == pid && std::get<1>(kv.first) == ch && std::get<2>(kv.first) == note) {
                    ks.push_back(kv.first);
                    sounded.insert(rank_name(kv.first));
                }
            for (auto &k : ks)
                S.release(k, n0);
            key_up_jacks(ch, note, n0, sounded);
            if (reg_on && cur_reg && reg_note[note] && patches[cur].organ->n_choir)
                reg_damper(ch, n0, note, false);        // every choir's damper falls
            return;
        }
        {                                   // a held roll closes at the key-up (no sooner than its least span)
            Key k(pid, ch, note, -1);
            for (RollGen &g : roll_gen)
                if (g.key == k && std::isnan(g.close))
                    g.close = std::max((double)(n0 - g.at) / rate,
                                       g.T->roll_par[g.T->roll_kind == 4 ? 7 : 8]);
        }
        // (a held texture lets go no sooner than its gate)
        long long at = n0;
        auto tx = tex_on.find(Key(pid, ch, note, -1));
        if (tx != tex_on.end()) {
            at = std::max(n0, tx->second);
            tex_on.erase(tx);
        }
        {                                   // ...and strikes no more grains
            Key k(pid, ch, note, -1);
            tex_gen.erase(std::remove_if(tex_gen.begin(), tex_gen.end(), [&](const TexGen &g) { return g.key == k; }),
                          tex_gen.end());
        }
        S.release(Key(pid, ch, note, -1), at);
        key_up_event(ch, note, n0);
        if (reg_on && cur_reg) {
            S.release(Key(pid, ch, note, REG_FORCED), n0);
            reg_damper(ch, n0, note, false);
        }
    }

    // live._key_up_event: the mechanism letting go (release_click_*) -- the
    // template's key-up rows stamped now, a one-shot at the note's own level
    void key_up_event(int ch, int note, long long n0)
    {
        auto it = held_rel.find(Key(pid, ch, note, 0));
        if (it == held_rel.end())
            return;
        const nv::live::Template &T = *it->second.first;
        double scale = it->second.second;
        held_rel.erase(it);
        if (T.rel.empty() || !T.rel[0].P)
            return;
        const nv::live::Template &R = T.rel[0];
        const double *f8p[6];
        const float *f4p[27];
        const long long *i8p[2];
        const int32_t *i4p[6];
        for (int c = 0; c < 6; c++)
            f8p[c] = R.f8[c].data();
        for (int c = 0; c < 27; c++)
            f4p[c] = R.f4[c].data();
        for (int c = 0; c < 2; c++)
            i8p[c] = R.i8[c].data();
        for (int c = 0; c < 6; c++)
            i4p[c] = R.i4[c].data();
        Key key(pid, ch, note, KEYUP_REL);
        if (!S.stamp(f8p, f4p, i8p, i4p, R.hrel.data(), R.P, key, n0, scale, R.dur, true, NAN, ch,
                     R.sof.empty() ? nullptr : R.sof.data(), R.rof.empty() ? nullptr : R.rof.data(), 0.0, 0.0,
                     R.cof.empty() ? nullptr : R.cof.data())) {
            dropped++;
            return;
        }
        std::vector<long> got = S.last_slots;
        long li = S.live_find(key);
        if (li >= 0)
            S.live.erase(S.live.begin() + li);      // it retires on its own; never released
        if (cpan[ch] != 64)
            S.repan(got, cpan[ch], 64, rate, true);
    }

    // live.Slab.press at tilt 0: each slot from its baseline (aL0, aR0),
    // the shape normalised by the left baseline's power, times
    // 10^(press_db * p / 20)
    void press(const std::vector<long> &slots, double p)
    {
        if (slots.empty())
            return;
        long n = (long)slots.size();
        std::vector<double> b2(n);
        for (long q = 0; q < n; q++) {
            double b = (double)S.aL0[slots[q]];
            b2[q] = b * b;
        }
        double sh = 1.0;                    // hrel ** (0 * p)
        double p2 = pairwise_d(b2.data(), n);
        if (p2 > 0.0)                       // (base * shape) ** 2 is base * base again
            sh = sh * pow(p2 / (pairwise_d(b2.data(), n) + 1e-30), 0.5);
        sh = sh * pow(10.0, press_db * p / 20.0);
        for (long s : slots) {
            S.f4[F4_aL][s] = (float)((double)S.aL0[s] * sh);
            S.f4[F4_aR][s] = (float)((double)S.aR0[s] * sh);
            if (S.tr_on[s]) {                   // (a tremolo's baselines with it)
                S.tr_aL[s] = S.f4[F4_aL][s];
                S.tr_aR[s] = S.f4[F4_aR][s];
            }
        }
    }

    // live.Slab.retune for a pitch (om_scale; the vibrato's depth and rate
    // as they are): om scaled, and the phase anchored where it is now -- the
    // vibrato's accumulated swing included, which moves with om (a piano's
    // depth is 0, so that term is too)
    void retune(const std::vector<long> &slots, long long n, double scale)
    {
        retune_v(slots, n, true, scale, false, 0.0, false, 0.0);
    }

    // live.Slab.retune: a sounding partial's pitch (scale), its vibrato's
    // depth (vd: over each player's own, by vsc) and rate (vrs: of its own,
    // the LFO's phase rotated to carry on) -- without a click: the phase now
    // worked out, the change made, the difference put back into p0
    void retune_v(const std::vector<long> &slots, long long n, bool has_s, double scale, bool has_vd, double vd,
                  bool has_vrs, double vrs)
    {
        if (slots.empty())
            return;
        double tn = (double)n / rate;
        for (long q : once(slots)) {
            double om0 = S.f8[F8_om][q], vd0 = (double)S.f4[F4_vd][q];
            double vr0 = std::max((double)S.f4[F4_vr][q], 1e-6), vp = (double)S.f4[21][q];   // vp
            double ton = (double)S.i8[0][q] / rate;
            auto extra = [&](double om, double d, double r, double ph) {
                double w2 = 2.0 * M_PI * r;
                double swing = cos(w2 * ton + ph) - cos(w2 * tn + ph);
                return (om * rate / (2.0 * M_PI)) * d / r * swing;
            };
            double vr1 = has_vrs ? std::max((double)S.vrbase[q] * vrs, 1e-6) : vr0;
            double vp1 = has_vrs ? vp + 2.0 * M_PI * (vr0 - vr1) * tn : vp;
            double before = extra(om0, vd0, vr0, vp);
            double om1 = has_s ? om0 * scale : om0;
            double vd1 = has_vd ? (double)S.vbase[q] + vd * (double)S.vsc[q] : vd0;
            double after = extra(om1, vd1, vr1, vp1);
            double step = (om0 - om1) * (double)n - (after - before);
            // A SLOT ON A WIND ROW carries om x BC of the wind's accrued phase
            // as well (the kernel adds it), so a new om moves that term too
            if (has_s && S.i4[I4_br][q] >= 0)
                step -= (om1 - om0) * BCt[S.i4[I4_br][q]];
            S.f8[F8_p0][q] += step;
            S.f8[F8_p0R][q] += step;
            if (has_s)
                S.f8[F8_om][q] = om1;
            if (has_vd)
                S.f4[F4_vd][q] = (float)vd1;
            if (has_vrs) {
                S.f4[F4_vr][q] = (float)vr1;
                S.f4[21][q] = (float)vp1;
            }
        }
    }

    // live.wheel_roles' 'vibrato': a part whose wheel nothing else wants
    bool vib_role(const Patch &p) const
    {
        const NoteClass *k = p.drums ? nullptr : nv_tcache_class(p.cache, p.program);
        return p.wheel_vib && !(p.amp > 0.0) && !(p.organ && (p.organ->n_order || p.organ->siren_up))
               && !(p.wtrem > 0.0) && !p.clav
               && !p.leslie && !p.wheel_swell && !(k && k->drone_wheel) && !(k && k->flt_set == 2 && k->flt_k == 4)
               && !(k && k->n_dchoice) && !lfo2_role(p);
    }

    // live.wheel_roles' 'lfo2': a Moog whose LFO 2 goes somewhere, its
    // wheel LFO 2's depth
    bool lfo2_role(const Patch &p) const
    {
        if (p.drums || !p.moog)
            return false;
        double pn[NV_MK_N];
        moog_pn(p, true, pn);
        return moog_lfo2_on(pn);
    }

    // LFO 2 (live's lfo2_ph, lfo2_w, lfo2_pr): each Moog part's phase, the
    // wheel last sent it, the pitch its sounding notes were last moved to
    std::map<long long, double> lfo2_ph, lfo2_w, lfo2_pr;

    // live._lfo2_tick: one block of every Moog part's LFO 2 at the block's
    // end -- the cutoff on its knob rows, the level for the render, the pitch
    // its sounding notes are moved to
    void lfo2_tick(long long n0, long frames)
    {
        for (const Patch &p : patches) {
            if (p.drums || !p.moog)
                continue;
            const long long id = p.pid;
            double pn[NV_MK_N];
            moog_pn(p, true, pn);
            auto ph = lfo2_ph.find(id);
            double x = (ph != lfo2_ph.end() ? ph->second : 0.0) + moog_lfo2_rate(pn[NV_MK_LFO2_RATE]) * frames / rate;
            x -= floor(x);
            lfo2_ph[id] = x;
            auto wi = lfo2_w.find(id);
            const double w = moog_lfo2_on(pn) && wi != lfo2_w.end() ? wi->second : 0.0;
            double pr, cf, ag;
            moog_lfo2_mods(pn, w, x, &pr, &cf, &ag);
            auto pi = lfo2_pr.find(id);
            const double prev = pi != lfo2_pr.end() ? pi->second : 1.0;
            if (pr != prev) {
                lfo2_pr[id] = pr;
                std::vector<long> sl;
                for (auto &kv : S.live)
                    if (std::get<0>(kv.first) == id)
                        sl.insert(sl.end(), kv.second.begin(), kv.second.end());
                retune(sl, n0, pr / prev);
            }
            for (auto &kk : S.kn_of) {
                const int r = kk.second;
                if (std::get<0>(kk.first) != id || !S.kn_has[r] || (S.kn_cf[r] == cf && S.kn_ag[r] == (float)ag))
                    continue;
                S.kn_cf[r] = cf;
                S.kn_ag[r] = (float)ag;
                S.set_knobs(r, &S.kn_base[(size_t)r * Slab::KN_W], true);
            }
        }
    }

    // live._snd_vib: (depth to add, rate factor) the part's CC77/76 ask of
    // these slots -- tonelib.sound_vib_depth_add (up to SOUND_VIB_DEPTH_CENTS
    // upward; downward toward none, by their own depth's mean, numpy's
    // float32 mean) and sound_vib_rate (SOUND_VIB_RATE_RANGE ** d)
    void snd_vib(const Patch &p, int ch, const std::vector<long> &slots, double *add, double *rt) const
    {
        *add = 0.0;
        *rt = 1.0;
        if (slots.empty() || p.drums)
            return;
        double dd = snd_d[ch][6], dr = snd_d[ch][5];
        if ((p.snd >> 6) & 1 && dd != 0.0) {
            if (dd >= 0.0) {
                *add = dd * (pow(2.0, 30.0 / 1200.0) - 1.0);
            } else {
                std::vector<float> vb(slots.size());
                for (size_t q = 0; q < slots.size(); q++)
                    vb[q] = S.vbase[slots[q]];
                // (np.mean: the float32 sum over the count in float64, back to float32 -- numpy 1.26's)
                float m = (float)((double)pairwise(vb.data(), (long)vb.size()) / (double)vb.size());
                *add = dd * (double)m;
            }
        }
        if ((p.snd >> 5) & 1 && dr != 0.0)
            *rt = pow(2.0, dr);
    }

    // live._vib_apply: the wheel's depth and rate and CC76/77's, summed,
    // on one part's sounding slots (retune sets them absolutely: once)
    void vib_apply(const Patch &p, int ch, long long n0)
    {
        std::vector<long> sl = sounding_tone(ch, p.pid, p.cache, false);
        if (sl.empty())
            return;
        double add, rt;
        snd_vib(p, ch, sl, &add, &rt);
        double v = vib_mod[ch] + add, w = vib_modw[ch];
        retune_v(sl, n0, false, 1.0, true, v, true, (1.0 + mod_rate * w) * rt);
    }

    double range_of(int ch) const { return brange[ch] >= 0.0 ? brange[ch] : bend_range; }

    // live._repitch: the channel's ratio (tonelib.channel_pitch_ratio: the
    // wheel over its range, the coarse and fine tuning; no master tuning
    // here), its notes moved by the change
    void repitch(int ch, long long n0)
    {
        double st = range_of(ch) * (double)wheel[ch] / 8192.0 + coarse[ch] + fine[ch] / 100.0 + master_coarse
                    + master_fine / 100.0;
        double ratio = pow(2.0, st / 12.0);
        double prev = bend[ch];
        // A MEEND MOVES EACH NOTE BY ITS OWN SWARAS: its parts retuned key by
        // key and kept out of the channel's ratio
        std::set<long long> mee;
        for (const Patch &p : patches)
            if ((p.channel < 0 || p.channel == ch) && meend_part(p))
                mee.insert(p.pid);
        if (!mee.empty())
            meend_retune(ch, mee, n0);
        if (ratio == prev)
            return;
        bend[ch] = ratio;
        messenger_rebend(ch);
        if (leslie_on(ch))
            return;                         // (a rotor part's wheel is its half-moon: nothing bends)
        // ...AND A FIXED OPEN STRING STAYS AT ITS PITCH (live._fixed_sym_slots)
        std::set<long> fx;
        for (auto &kv : S.live) {
            if (std::get<1>(kv.first) != ch || kv.second.empty() || mee.count(std::get<0>(kv.first)))
                continue;
            auto it = sym_at.find(kv.first);
            if (it != sym_at.end() && it->second.size() == kv.second.size())
                for (size_t q = 0; q < kv.second.size(); q++)
                    if (it->second[q])
                        fx.insert(kv.second[q]);
        }
        std::vector<long> sl;
        for (auto &kv : S.live)
            if (std::get<1>(kv.first) == ch && !mee.count(std::get<0>(kv.first)))
                sl.insert(sl.end(), kv.second.begin(), kv.second.end());
        if (!fx.empty()) {
            std::vector<long> kept;
            for (long s : sl)
                if (!fx.count(s))
                    kept.push_back(s);
            sl.swap(kept);
        }
        retune(sl, n0, ratio / prev);
        // ...AND THE VALVE'S PRODUCTS WITH THEIR PARENTS (live._repitch_amp):
        // each a sum of multiples of theirs, so one ratio moves them exactly
        std::vector<long> amps;
        for (const Patch &p : patches)
            if (p.channel < 0 || p.channel == ch) {
                long li = S.live_find(Key(p.pid, -1, -1, AMPK));
                if (li >= 0)
                    amps.insert(amps.end(), S.live[li].second.begin(), S.live[li].second.end());
            }
        for (auto &ar : amp_retired)                // ...the old tones' valves too
            for (const Patch &p : patches)
                if (ar.second.first == p.pid && (p.channel < 0 || p.channel == ch)) {
                    long li = S.live_find(ar.first);
                    if (li >= 0)
                        amps.insert(amps.end(), S.live[li].second.begin(), S.live[li].second.end());
                    break;
                }
        if (!amps.empty() && ratio / prev != 1.0)
            retune(amps, n0, ratio / prev);
    }

    void pitchwheel(int ch, int v, long long n0)
    {
        wheel[ch] = v;
        if (leslie_on(ch) && !S.les.empty())   // on a rotor part the wheel is the half-moon
            half_moon_step(ch, v);
        repitch(ch, n0);
    }

    // tonelib.RPN_STEP: (step, lo, hi) for (0, 0) .. (0, 5)
    static bool rpn_step_of(int lsb, double *step, double *lo, double *hi)
    {
        static const double T[6][3] = {{0.01, 0.0, 127.99},
                                       {100.0 / 8192.0, -100.0, 100.0 * 8191.0 / 8192.0},
                                       {1.0, -64.0, 63.0},
                                       {1.0, 0.0, 127.0},
                                       {1.0, 0.0, 127.0},
                                       {100.0 / 128.0, 0.0, 127.0 * 100.0 + 127.0 * 100.0 / 128.0}};
        if (lsb < 0 || lsb > 5)
            return false;
        *step = T[lsb][0];
        *lo = T[lsb][1];
        *hi = T[lsb][2];
        return true;
    }

    // live._rpn_data: CC6/CC38 into the RPN selected; the pitch ones re-pitch
    // the channel; MTS's (0/3, 0/4) only a gm2 part acts on, none here; MPE's
    // configuration (0/6) is not read here
    void rpn_data(int ch, int cc, int v, long long n0)
    {
        if (rpn_none[ch])
            return;                                 // an NRPN (GS's sound ones: not here)
        int m = rpn_msb[ch], l = rpn_lsb[ch];
        if (m != 0 || l > 5)
            return;                                 // null, or not one read
        if (l == 0) {
            brange[ch] = cc == 6 ? (double)v : (double)(long)range_of(ch) + v / 100.0;     // rpn_bend_range
        } else if (l == 1) {
            if (cc == 6)
                fine_msb[ch] = v;                   // rpn_fine
            int lsb = cc == 38 ? v : 0;
            fine[ch] = (double)(((fine_msb[ch] << 7) | lsb) - 8192) / 8192.0 * 100.0;
        } else if (l == 2) {
            if (cc != 6)
                return;
            coarse[ch] = (double)(v - 64);          // rpn_coarse
        } else if (l == 5) {
            double cur = modrange[ch] >= 0.0 ? modrange[ch] : mod_cents;
            modrange[ch] = cc == 6 ? (double)v * 100.0 : (double)(long)floor(cur / 100.0) * 100.0 + v * (100.0 / 128.0);
            if (vib_modw[ch] > 0.0)             // a wheel already up follows its new range (sent again)
                control(ch, 1, (int)nearbyint(vib_modw[ch] * 127.0), n0);
            return;
        } else {
            if (cc != 6)
                return;                             // (rpn_tuning_program, _bank: the data entry MSB)
            auto s_ = mts_selection(ch);
            (l == 3 ? s_.second : s_.first) = v;
            mts_sel[ch] = s_;
            remts(ch, nullptr, n0);                 // ("This change takes effect immediately")
            return;
        }
        repitch(ch, n0);
    }

    // live._rpn_step: CC96 (up) / CC97, the selected RPN one unit of its finest byte
    void rpn_step(int ch, bool up, long long n0)
    {
        if (rpn_none[ch] || rpn_msb[ch] != 0)
            return;
        int l = rpn_lsb[ch];
        double step, lo, hi;
        if (!rpn_step_of(l, &step, &lo, &hi))
            return;
        double cur = l == 0 ? range_of(ch) : l == 1 ? fine[ch] : l == 2 ? coarse[ch]
                     : l == 3 ? (double)mts_selection(ch).second : l == 4 ? (double)mts_selection(ch).first
                     : (modrange[ch] >= 0.0 ? modrange[ch] : mod_cents);
        double v = cur + (up ? step : -step);
        v = std::max(lo, v);                        // min(hi, max(lo, v)): Python keeps the first of equals
        v = std::min(hi, v);
        if (l == 2)
            v = (double)(long)nearbyint(v);
        if (l == 0) {
            brange[ch] = v;
        } else if (l == 1) {
            fine[ch] = v;
            long code = (long)nearbyint(v / 100.0 * 8192.0) + 8192;       // rpn_fine_msb
            fine_msb[ch] = (int)(std::max(0L, std::min(16383L, code)) >> 7);
        } else if (l == 2) {
            coarse[ch] = v;
        } else if (l == 3 || l == 4) {
            auto s_ = mts_selection(ch);
            (l == 3 ? s_.second : s_.first) = (int)v;
            mts_sel[ch] = s_;
            remts(ch, nullptr, n0);
            return;
        } else {
            modrange[ch] = v;
            if (vib_modw[ch] > 0.0)
                control(ch, 1, (int)nearbyint(vib_modw[ch] * 127.0), n0);
            return;
        }
        repitch(ch, n0);
    }

    // PANIC (live.panic, _all_off): every key let go over its own release,
    // what no key holds ended the same way (an orphan: busy, no key, not yet
    // ending -- noff at n0 plus its release delay), the keys and the pedal's
    // holds forgotten
    bool room_on = true;                            // the panel's: the tail on or off
    void panic(long long n0)
    {
        std::vector<Key> keys;
        for (auto &kv : S.live)
            keys.push_back(kv.first);
        for (const Key &k : keys) {
            S.oneshot.erase(k);
            S.release(k, n0);
        }
        std::vector<char> held(S.cap, 0);
        for (auto &kv : S.live)
            for (long q : kv.second)
                held[q] = 1;
        std::vector<long> orphan;
        for (long q = 0; q < S.cap; q++)
            if (S.busy[q] && !held[q] && S.i8[1][q] == IDLE)
                orphan.push_back(q);
        for (long q : orphan)
            S.i8[1][q] = std::min(S.i8[1][q], n0 + (long long)S.f4[F4_rdl][q]);
        if (!orphan.empty())
            S.retiring.push_back(std::make_pair(orphan, n0));
        for (long q : orphan)                   // (a Moog row's key-up is its pitch row's: live's)
            if (S.i4[I4_fx][q] >= 0 && (double)n0 < S.mp_toff[S.i4[I4_fx][q]])
                S.mp_toff[S.i4[I4_fx][q]] = (double)n0;
        down.clear();
        roll_gen.clear();                       // (a held roll strikes no more)
        pedalled.clear();
        cutting.clear();
        open_ring.clear();
    }

    // CC120, ALL SOUND OFF (live's): the channel stopped now, pedal or no
    // pedal -- every key on it over the steal-fade, its keys, pedals and
    // sostenuto cleared, and its register killed (_reg_channel, kill)
    void all_sound_off(int ch, long long n0)
    {
        for (size_t pi = 0; pi < patches.size(); pi++)    // (the valve's products: their parents go)
            if (patches[pi].channel < 0 || patches[pi].channel == ch)
                amp_touch((int)pi);
        for (auto it = down.begin(); it != down.end();)
            it = it->first == ch ? down.erase(it) : std::next(it);
        for (auto it = pedalled.begin(); it != pedalled.end();)
            it = it->first == ch ? pedalled.erase(it) : std::next(it);
        for (auto it = open_ring.begin(); it != open_ring.end();)
            it = std::get<1>(it->first) == ch ? open_ring.erase(it) : std::next(it);
        sost.erase(ch);
        pedal_v[ch] = 0;
        float fade = (float)(retrigger * rate);
        std::vector<Key> keys;
        for (auto &kv : S.live)
            if (std::get<1>(kv.first) == ch)
                keys.push_back(kv.first);
        for (const Key &k : keys) {
            long li = S.live_find(k);
            if (li >= 0)
                for (long q : S.live[li].second)
                    if (fade < S.f4[F4_re][q])
                        S.f4[F4_re][q] = fade;
            S.oneshot.erase(k);
            S.release(k, n0);
        }
        if (!reg_on)
            return;
        for (RegSt &st : reg) {
            if (st.ch != ch)
                continue;
            if (st.ready) {
                std::vector<long> on;
                for (long m = 0; m < (long)st.slot_of.size(); m++)
                    if (st.slot_of[m] >= 0)
                        on.push_back(m);
                reg_close(st, on, n0, retrigger * rate);
            }
            for (size_t i = 0; i < reg_strike_of.size();)
                if (reg_strike_of[i].first.first == ch)
                    reg_strike_of.erase(reg_strike_of.begin() + i);
                else
                    i++;
            Job j;
            j.kind = 2;
            j.ch = ch;
            for (int k = 21; k < 109; k++)
                j.keys.push_back(k);
            send_job(std::move(j));
        }
    }

    // CC123, ALL NOTES OFF (live's): the keys come up -- a note under a held
    // damper or the sostenuto rings on (pedalled), a one-shot on its own decay
    void all_notes_off(int ch, long long n0)
    {
        for (size_t pi = 0; pi < patches.size(); pi++)
            if (patches[pi].channel < 0 || patches[pi].channel == ch)
                amp_touch((int)pi);
        for (auto it = down.begin(); it != down.end();)
            it = it->first == ch ? down.erase(it) : std::next(it);
        auto sq = sost.find(ch);
        std::vector<Key> keys;
        for (auto &kv : S.live)
            if (std::get<1>(kv.first) == ch)
                keys.push_back(kv.first);
        for (const Key &k : keys) {
            if (S.oneshot.count(k) && S.oneshot[k])
                continue;
            int nt = (int)std::get<2>(k);
            if (pedal_holds(ch, nt) || (sq != sost.end() && sq->second.count(nt))) {
                pedalled.insert(std::make_pair(ch, nt));
                continue;
            }
            S.release(k, n0);
        }
    }

    // live._reset_controllers (CC121): the wheel to centre, then CC1, CC11,
    // CC64, CC65, CC66, CC67 as live sends them, pressure off, no RPN
    // selected -- not the volume, pan, program or the tuning RPNs' values
    void reset_controllers(int ch, long long n0)
    {
        wheel[ch] = 0;
        porta_src[ch] = -1;                 // a pending CC84 goes too
        repitch(ch, n0);
        static const int RESET_CC[6][2] = {{1, 0}, {11, 127}, {64, 0}, {65, 0}, {66, 0}, {67, 0}};
        for (auto &cv : RESET_CC) {
            wheel_reset = cv[0] == 1;
            control(ch, cv[0], cv[1], n0);
        }
        wheel_reset = false;
        aftertouch(ch, 0, n0);
        rpn_none[ch] = false;
        rpn_msb[ch] = rpn_lsb[ch] = 127;
        pw_armed[ch] = true;
    }

    // live._jobs_power_on: a GM SYSTEM ON or GS RESET's power-on for the
    // wheel's jobs (their own CCs, tonelib.WHEEL_CC -- CC121 leaves them, GM 2
    // 3.5.2): the swell open (its notes rescaled), the valve its own drive, the
    // rockers, the detune and the drones the voice's own; the registration left
    // as it is
    void jobs_power_on(int ch, long long n0)
    {
        for (auto it = job_at.begin(); it != job_at.end();)
            it = it->first.first == ch ? job_at.erase(it) : std::next(it);
        if (hammond_on(ch))
            for (const Patch &p : patches) {
                if (!(p.leslie || p.wheel_swell || p.amp > 0.0) || !(p.channel < 0 || p.channel == ch))
                    continue;
                if (p.wheel_swell && (!(p.amp > 0.0) || p.leslie) && swell != 1.0) {
                    const double was = swell;
                    swell = 1.0;
                    S.channel_gain(sounding_tone(ch, p.pid, p.cache, false), 1.0 / was);
                }
                break;
            }
        for (const Patch &p : patches) {
            if (!(p.channel < 0 || p.channel == ch))
                continue;
            if (p.amp > 0.0 && drive_step.erase(p.pid))
                amp_dirty.insert(p.pid);
            if (p.clav)
                clav_step.erase(p.pid);
        }
        if (detune_wheel)
            for (const Patch &p : patches)
                if (p.cache == cache) {
                    speed = p.speed;
                    break;
                }
        for (int pi = 0; pi < (int)patches.size(); pi++) {
            if (!(patches[pi].channel < 0 || patches[pi].channel == ch))
                continue;
            Use u(*this, pi);
            if (drone_class() && drone_count.erase(pid) && chanting(ch))
                drones(ch, n0);
            if (dnote_class() && drone_sel.erase(pid) && chanting(ch))
                drone_note(ch, n0);
        }
    }

    // channel aftertouch: every key sounding on the channel (live's
    // _press_groups: the slab's keys in order, one tilt) -- and a plunger's
    // hand (live._tone_ctl)
    void aftertouch(int ch, int v, long long n0)
    {
        pressure[ch] = v / 127.0;
        at_seen[ch] = true;
        tone_ctl(ch, false, n0, v);
        press(pressed(ch, -1), pressure[ch]);
    }

    // a key's polytouch: its slots (live's _press_groups(ch, note)) -- and a
    // siren's air (ppress)
    void polytouch(int ch, int note, int v)
    {
        ppress[std::make_pair(ch, note)] = v / 127.0;
        press(pressed(ch, note), v / 127.0);
    }

    // the slots a pressure reaches: the channel's (a key's, note >= 0), a
    // siren's none -- its pressure is its air (live's _press_groups)
    std::vector<long> pressed(int ch, int note) const
    {
        if (siren_st.empty() && note < 0)
            return sounding(ch);
        std::vector<long> out;
        for (auto &kv : S.live)
            if (std::get<1>(kv.first) == ch && (note < 0 || std::get<2>(kv.first) == note)
                && std::none_of(siren_st.begin(), siren_st.end(), [&](const std::pair<SKey, SirenSt> &x) {
                       return x.first == SKey(std::get<0>(kv.first), ch, (int)std::get<2>(kv.first));
                   }))
                out.insert(out.end(), kv.second.begin(), kv.second.end());
        return out;
    }

    // ---- the sirens (siren.py; live's _siren_on, _siren_end, _siren_block) ----
    // a siren key goes down: its rotor -- the one still turning under this key
    // if it was let go and is coasting, else at rest -- and its rows; a note
    // still sounding on the key let go here (the disc is one disc)
    void siren_on(int ch, int note, int vel, long long n0, int kind, int sn)
    {
        SKey k(pid, ch, note);
        SirenRot rot;
        bool have = false;
        auto it = siren_find(k);
        if (it != siren_st.end()) {
            SirenSt old = it->second;
            siren_st.erase(it);
            rot = old.rot;
            have = true;
            siren_end(k, old, n0);
        } else {
            auto m = siren_mem.find(k);
            if (m != siren_mem.end()) {
                rot = m->second.first;
                have = true;
                siren_coast(rot, (double)std::max(0LL, n0 - m->second.second) / rate);
                siren_mem.erase(m);
            }
        }
        if (!have)
            rot = SirenRot(kind);
        const OrganSpec *og = patches[cur].organ;
        size_t nrow = og && og->siren_up ? 2 : 1;
        SirenSt st;
        st.rot = rot;
        if (siren_free.size() >= nrow)
            for (size_t q = 0; q < nrow; q++) {
                st.rows.push_back(siren_free.front());
                siren_free.pop_front();
            }
        double f = 440.0 * pow(2.0, (sn - 69) / 12.0);
        st.pv = std::max(vel / 127.0, 1e-3);
        st.frev = f / 12.0;
        if (nrow == 2) {
            st.dl = siren_crank_samples(siren_crank_angle(job_get(ch, NV_CC_CRANK)), st.frev, rate);
            st.acc[1] = st.dl;
        }
        for (int r : st.rows) {
            BRt[r] = 1.0f;
            BCt[r] = 0.0;
            BLt[2 * r] = BLt[2 * r + 1] = 0.0f;
        }
        siren_st.push_back(std::make_pair(k, st));
    }

    // a siren note let go: its slots fade on their own release, its rows
    // freed once they have (siren_retire), its rotor remembered
    void siren_end(const SKey &k, const SirenSt &st, long long n0)
    {
        std::vector<Key> ks;
        for (auto &kv : S.live)
            if (std::get<0>(kv.first) == std::get<0>(k) && std::get<1>(kv.first) == std::get<1>(k)
                && std::get<2>(kv.first) == std::get<2>(k))
                ks.push_back(kv.first);
        for (auto &q : ks)
            S.release(q, n0);
        if (!st.rows.empty())
            siren_retire.push_back(std::make_pair(n0 + (long long)(0.5 * rate), st.rows));
        siren_mem[k] = std::make_pair(st.rot, n0);
    }

    // every sounding siren's rotor one callback on: its rows for this block
    // (the same model, the same steps, as nvrender's)
    void siren_block(long long n0, long long frames)
    {
        const double dt = (double)frames / rate;
        while (!siren_retire.empty() && siren_retire[0].first <= n0) {
            for (int r : siren_retire[0].second)
                siren_free.push_back(r);
            siren_retire.erase(siren_retire.begin());
        }
        std::vector<SKey> ks;
        for (auto &x : siren_st)
            ks.push_back(x.first);
        for (const SKey &k : ks) {
            auto it = siren_find(k);
            if (it == siren_st.end())
                continue;
            const int ch = std::get<1>(k), note = std::get<2>(k);
            bool held = false;
            for (auto &kv : S.live)
                held = held || (std::get<0>(kv.first) == std::get<0>(k) && std::get<1>(kv.first) == ch
                                && std::get<2>(kv.first) == note);
            if (!held) {                    // its slots taken from it (a reset, a panic): let it go
                SirenSt st = it->second;
                siren_st.erase(it);
                siren_end(k, st, n0);
                continue;
            }
            SirenSt &st = it->second;
            const bool drive = st.down || (st.ends && n0 < st.drive_end);
            double p;
            if (!drive) {
                p = 0.0;
            } else if (st.rot.kind == 1) {
                p = 1.0;
            } else {
                auto pp = ppress.find(std::make_pair(ch, note));
                p = std::max(std::max(st.pv, pressure[ch]),
                             std::max(pp != ppress.end() ? pp->second : 0.0, cc2v[ch]));
            }
            double l0, l1;
            const double r = siren_rot_block(st.rot, p, dt, &l0, &l1);
            if (st.rot.kind != 1) {
                const double g = 1.0 / sqrt(st.pv);   // the velocity's gain is the onset's level
                l0 *= g;
                l1 *= g;
            }
            if (!st.rows.empty()) {
                const int lo = st.rows[0];
                BRt[lo] = (float)r;
                BCt[lo] = st.acc[0];
                BLt[2 * lo] = (float)l0;
                BLt[2 * lo + 1] = (float)l1;
                st.acc[0] += ((double)BRt[lo] - 1.0) * frames;
                if (st.rows.size() > 1) {
                    const int up = st.rows[1];
                    const double dl = siren_crank_samples(siren_crank_angle(job_get(ch, NV_CC_CRANK)), st.frev, rate);
                    BRt[up] = (float)(r + (dl - st.dl) / frames);
                    BCt[up] = st.acc[1];
                    BLt[2 * up] = (float)l0;
                    BLt[2 * up + 1] = (float)l1;
                    st.acc[1] += ((double)BRt[up] - 1.0) * frames;
                    st.dl = dl;
                }
            }
            if (!drive) {
                const bool done = st.rot.kind == 1 ? siren_level(st.rot) <= pow(10.0, -SIREN_FLOOR_DB / 20.0)
                                                   : st.rot.air <= 1e-3 * st.pv;
                if (done) {
                    SirenSt cp = st;
                    siren_st.erase(it);
                    siren_end(k, cp, n0 + frames);
                }
            }
        }
    }

    // live._tone_ctl: the wheel or the hand reaching ch's tones' filters, the
    // last three moves kept (a glide needs two)
    void tone_ctl(int ch, bool wheel_, long long n0, int v)
    {
        const double t = (double)n0 / rate;
        for (auto &kv : tone_fx) {
            ToneFx &tf = kv.second;
            if (tf.ch != ch || !tf.kind)
                continue;
            auto &l = wheel_ ? tf.wheel : tf.at;
            l.push_back(std::make_pair(t, v));
            if (l.size() > 3)
                l.erase(l.begin(), l.end() - 3);
        }
    }

    // live._tone_fx: the effect channel of the tone the part plays now on
    // ch (a melodic tone that brings one), made the first time
    int tone_fx_of(int ch, long long n0)
    {
        const Patch &p = patches[cur];
        const NoteClass *k = p.drums ? nullptr : nv_tcache_class(p.cache, p.program);
        if (!k || !(k->efx_raw || k->flt_set == 2))
            return -1;
        std::vector<void *> &lst = tone_seg[ch];
        long ix = (long)(std::find(lst.begin(), lst.end(), p.cache) - lst.begin());
        if (ix == (long)lst.size())
            lst.push_back(p.cache);
        const int fxc = ch % TONE_SEG + TONE_SEG * (1 + (int)(ix % (TONE_SEG - 1)));
        if (!tone_fx.count(fxc)) {
            ToneFx tf;
            tf.ch = ch;
            tf.k = k;
            tf.kind = k->flt_set == 2 ? k->flt_k : 0;       // (the plunger, the mouth; a tone's effect's own: P2b)
            const double t = (double)n0 / rate;     // (the hand and the wheel where they already are)
            if (at_seen[ch])
                tf.at.push_back(std::make_pair(t, (int)nearbyint(pressure[ch] * 127.0)));
            auto jm = job_at.find(std::make_pair(ch, (int)NV_CC_MOUTH));     // (the mouth's own CC)
            if (jm != job_at.end())
                tf.wheel.push_back(std::make_pair(t, jm->second));
            if (tf.kind == 4)
                tf.g = nv_npy_new((unsigned long long)(fxc + k->mouth_seed));
            if (k->efx_raw && efx_x) {          // ITS OWN EFFECT: its setting, the part on it, at 0 (tone_events)
                tf.ex = nv_efx_live_new(efx_x, rate);
                nv_efx_live_apply(tf.ex, 0.0, 1, k->efx_raw_ty[0], k->efx_raw_ty[1]);
                for (int q = 1; q <= 20; q++)
                    if (k->efx_raw_p[q] >= 0)
                        nv_efx_live_apply(tf.ex, 0.0, 2, q, k->efx_raw_p[q]);
                nv_efx_live_apply(tf.ex, 0.0, 5, ch, 1);
            }
            tone_fx[fxc] = std::move(tf);
        }
        return fxc;
    }

    // a stepped control from 0 at time 0 (efxfilter.steps over [0.0] + its
    // times, [0.0] + its values: sorted moves), at t, gliding
    static double steps_at(std::vector<std::pair<double, int>> ev, double glide, double t)
    {
        std::sort(ev.begin(), ev.end());
        std::vector<double> ts{0.0}, vs{0.0};
        for (auto &e : ev) {
            ts.push_back(e.first);
            vs.push_back((double)e.second);
        }
        long i = (long)(std::upper_bound(ts.begin(), ts.end(), t) - ts.begin()) - 1;
        i = i < 0 ? 0 : (i > (long)ts.size() - 1 ? (long)ts.size() - 1 : i);
        if (glide <= 0.0 || vs.size() < 2)
            return vs[i];
        double prev = vs[i > 0 ? i - 1 : 0];
        double dt = t - ts[i];
        double kk = exp(-(dt > 0.0 ? dt : 0.0) / glide);
        return vs[i] + (prev - vs[i]) * (i > 0 ? kk : 0.0);
    }

    // gsefx.filter_setup's control at t for part c (its settings M): the
    // vowels' three centres gliding (efxfilter.steps), else one value -- a
    // sweep's LFO on the absolute clock (an auto wah's Sens adding the
    // part's loudness, note_envelope), a flanger's line (stepped), a pedal
    void efx_control(const ModFlt &M, int c, double t, double *ctl, double *F)
    {
        const double *sg = M.seg.data();
        long i = 0;
        while (i < M.n && sg[8 * i] <= t)
            i++;
        i = i - 1 < 0 ? 0 : (i - 1 > M.n - 1 ? M.n - 1 : i - 1);
        const double *s = sg + 8 * i;
        if (sg[2] == 3.0) {
            static const double VOWEL_F[5][3] = {{730, 1090, 2440}, {270, 2290, 3010},
                                                 {300, 870, 2240}, {530, 1840, 2480}, {570, 840, 2410}};
            const double glide = sg[4];
            for (int fk = 0; fk < 3; fk++) {
                const double vi = VOWEL_F[(int)s[3]][fk];
                if (glide <= 0.0 || M.n < 2) {
                    F[fk] = vi;
                } else {
                    const double prev = VOWEL_F[(int)sg[8 * (i > 0 ? i - 1 : 0) + 3]][fk];
                    const double kk = exp(-std::max(t - s[0], 0.0) / glide);
                    F[fk] = vi + (prev - vi) * (i > 0 ? kk : 0.0);
                }
            }
            return;
        }
        const double *k = s + 2;
        if (k[0] == 1.0) {
            const double lf = sin(2.0 * M_PI * k[3] * t);
            if (std::isnan(k[4])) {             // a phaser: about its Manual
                *ctl = k[1] * pow(2.0, k[2] * lf);
            } else {                            // an auto wah: up (or down) from it
                double oc = k[2] * 0.5 * (1.0 + lf);
                bool sens = false;
                for (int q = 0; q < M.n; q++)
                    sens = sens || (sg[8 * q + 2] == 1.0 && sg[8 * q + 7] != 0.0);
                if (k[5] != 0.0 && sens)        // ...and by the part's loudness
                    oc = oc + k[5] * note_env(c, t);
                *ctl = k[1] * pow(2.0, (k[4] != 0.0 ? 1.0 : -1.0) * oc);
            }
        } else if (k[0] == 2.0) {               // a flanger's line, stepped or not
            const double held = std::isnan(k[4]) ? t : floor(t * k[4]) / k[4];
            *ctl = k[1] + k[2] * 0.5 * (1.0 + sin(2.0 * M_PI * k[3] * held));
        } else {
            *ctl = s[1];                        // a wah's pedal
        }
    }

    // gsefx.note_envelope at t: the part's notes on the effect, each one's
    // level (its velocity, attacked, held, released), the loudest
    double note_env(int c, double t)
    {
        const double ATT = 0.005, HOLD = 0.4, REL = 0.06;      // (WAH_ENV_*)
        double out = 0.0;
        auto it = efx_notes.find(c % VIRT);     // (branch B hears its part's notes)
        if (it == efx_notes.end())
            return out;
        for (const EfxNote &e : it->second) {
            const double s = e.s0, en = e.s1, a = e.vel / 127.0;
            if (!(s <= t) || !(t < en + 8.0 * REL))
                continue;
            const double u = t - s;
            double lv;
            if (t <= en)
                lv = a * std::min(1.0, u / ATT) * exp(-u / HOLD);
            else
                lv = a * exp(-(en - s) / HOLD) * exp(-std::max(t - en, 0.0) / REL);
            out = std::max(out, lv);
        }
        return out;
    }

    // efxfilter.response for the module's filter types: 1 the phaser (N
    // all-passes at the corner: native.xatan, xcexp, xabs), 2 and 3 a
    // resonant low or band pass, 4 a comb, 5 the vowels' three formants
    static double flt_h(int ty, double f, double ctrl, const double *F, double pa, double pb, double pc)
    {
        if (ty == 1) {
            const double th = -2.0 * pc * atan(f / (ctrl > 1.0 ? ctrl : 1.0));
            const double zr = cos(th), zi = sin(th);
            const double nr = pa * zr, ni = pa * zi;
            const double dr = 1.0 - pb * zr, di = 0.0 - pb * zi;
            double qr, qi;
            if (fabs(dr) >= fabs(di)) {
                const double rat = di / dr, scl = 1.0 / (dr + di * rat);
                qr = (nr + ni * rat) * scl;
                qi = (ni - nr * rat) * scl;
            } else {
                const double rat = dr / di, scl = 1.0 / (di + dr * rat);
                qr = (nr * rat + ni) * scl;
                qi = (ni * rat - nr) * scl;
            }
            return hypot((1.0 - pa) + qr, qi);
        }
        if (ty == 2 || ty == 3) {
            const double x = f / (ctrl > 1.0 ? ctrl : 1.0);
            const double q = pa > 0.1 ? pa : 0.1;
            const double a = 1.0 - x * x, b = x / q;
            const double den = sqrt(a * a + b * b);
            const double w = ty == 2 ? 1.0 / den : (x / q) / den;
            return (1.0 - pb) + pb * w;
        }
        if (ty == 4)
            return comb_h(f, ctrl, pa, pb);
        if (ty == 5) {
            static const double BW[3] = {80.0, 110.0, 160.0}, AM[3] = {1.0, 0.7, 0.5};
            double h = pa;
            for (int fk = 0; fk < 3; fk++) {
                const double u = (f - F[fk]) / (0.5 * BW[fk]);
                h = h + AM[fk] / (1.0 + u * u);
            }
            return h * pb;
        }
        return 1.0;
    }

    // Live._filter_block, the module's: on each part on the effect, its
    // flanger's comb (the delay swung, the right ear half a turn on) and its
    // tremolo or auto pan (1 + m w(t), w Roland's wave, gsefx.WAVES; a pan's
    // right ear 1 - m w(t)), multiplied in that order
    // A CHAIN's MOVING FILTERS at t (live._filter_for's comps, _filter_block's
    // |H|): its filter over its timeline (h, the part pc on it; key c its
    // channel's: its notes, its cache), its comb, its tremolo -- ear by ear
    struct Comps {
        bool comb = false, trem = false;
        int fty = 0;
        double fpa = 0.0, fpb = 0.0, fpc = 0.0, fctl = 0.0, FV[3] = {0.0, 0.0, 0.0};
        double tl = 0.0, tr = 0.0, mix = 0.0, fb = 0.0, gl = 1.0, gr = 1.0;
        double h(double f, bool right, double x = 1.0) const     // (x: a tone's own filter, first)
        {
            if (fty)
                x = x * flt_h(fty, f, fctl, FV, fpa, fpb, fpc);
            if (comb)
                x = x * comb_h(f, right ? tr : tl, mix, fb);
            if (trem)
                x = x * (right ? gr : gl);
            return x;
        }
    };
    void chain_comps(void *h, int pc, int c, const double *fc, double t, Comps &o)
    {
        const bool comb = fc[14] != 0.0 && fc[18] != 0.0, trem = fc[55] != 0.0;
        o.comb = comb;
        o.trem = trem;
            // ITS MOVING FILTER (gsefx.filter_setup's control at t): the
            // settings over the timeline, the one in force at t
            int fty = 0;
            double fpa = 0.0, fpb = 0.0, fpc = 0.0, fctl = 0.0, FV[3] = {0.0, 0.0, 0.0};
            if (fc[50] != 0.0) {
                ModFlt &M = mflt[c];
                const long rv = nv_efx_live_rev(h);
                if (M.rev != rv) {
                    M.seg.assign(8 * 256, 0.0);
                    M.n = nv_efx_live_filter(h, pc, M.head, M.seg.data(), 256);
                    M.rev = rv;
                }
                if (M.n)
                    fty = M.seg[2] == 3.0 ? 5 : (int)M.head[0];     // (the vowels: VOWEL's, type 5)
                fpa = M.head[1]; fpb = M.head[2]; fpc = M.head[3];
                if (M.n)
                    efx_control(M, c, t, &fctl, FV);
            }
            double tl = 0.0, tr = 0.0, mix = 0.0, fb = 0.0, gl = 1.0, gr = 1.0;
            if (comb) {
                const double rt = fc[16];
                const double swing = fc[17] / (2.0 * M_PI * (rt > 1e-6 ? rt : 1e-6));
                tl = fc[15] + swing * sin(2.0 * M_PI * rt * t);
                tr = fc[15] + swing * sin(2.0 * M_PI * rt * t + M_PI);
                const double a = fc[20];
                mix = fc[21] >= 0.0 ? fc[21] : a * a / (1.0 + a * a);
                fb = fc[18];
            }
            if (trem) {
                static const double SINE[4] = {1.0, 1.0, 1.0, 0.0};
                const double *wv = SINE;
                if (fc[55] == 1.0)          // (Roland's wave; the Tremolo Chorus's the sine)
                    wv = efx_x + 132 + NV_EFX_NAT * (size_t)efx_x[131] + 30 + 66 + 1024 + 128 + 19 * (int)fc[59];
                const double rt = fc[56], m = fc[57];
                double w = 0.0;
                for (int q = 0; q < (int)wv[0]; q++)
                    w = w + wv[2 + 3 * q] * cos(wv[1 + 3 * q] * 2.0 * M_PI * rt * t + wv[3 + 3 * q]);
                gl = 1.0 + m * w;
                gr = fc[58] != 0.0 ? 1.0 - m * w : 1.0 + m * w;
            }
            o.fty = fty; o.fpa = fpa; o.fpb = fpb; o.fpc = fpc; o.fctl = fctl;
            o.FV[0] = FV[0]; o.FV[1] = FV[1]; o.FV[2] = FV[2];
            o.tl = tl; o.tr = tr; o.mix = mix; o.fb = fb; o.gl = gl; o.gr = gr;
    }

    void efx_filter_block(double t)
    {
        for (int c = 0; c < TONE_SEG; c++) {
            if (!nv_efx_live_on(efx, c))
                continue;
            int st = -1;
            const char *why = "";
            const double *fc = efx_chain(c, &st, &why);
            if (!fc || !efx_moves(fc))
                continue;
            Comps o;
            chain_comps(efx, c, c, fc, t, o);
            S.filter_swing(c, rate, [&](double f) { return o.h(f, false); }, [&](double f) { return o.h(f, true); });
        }
        for (int c = 0; c < TONE_SEG; c++) {    // ...and each part's branch B (a parallel type's)
            if (!nv_efx_live_on(efx, c))
                continue;
            int st = -1;
            const char *why = "";
            const double *fc = efx_chain(c + VIRT, &st, &why);
            if (!fc || !efx_moves(fc))
                continue;
            Comps o;
            chain_comps(efx, c + VIRT, c + VIRT, fc, t, o);
            S.filter_swing(c + VIRT, rate, [&](double f) { return o.h(f, false); },
                           [&](double f) { return o.h(f, true); });
        }
    }

    // Live._filter_block, the tones' own: each tone's filter at the block's
    // middle, |H| on its rows -- the plunger's corner (efxfilter.plunger, the
    // hand's last moves), the mouth's three centres (the wheel's vowel once it
    // has moved, else the wander: efxfilter.mouth_live)
    void filter_block(long long n0, long long frames)
    {
        if ((tone_fx.empty() && !(efx && nv_efx_live_parts(efx))) || S.fl_n == 0)
            return;
        const double t = ((double)n0 + 0.5 * (double)frames) / rate;
        if (efx)
            efx_filter_block(t);
        tone_filter_block(t);
        for (auto &kv : efx_notes) {        // the notes an auto wah no longer hears
            std::vector<EfxNote> &l = kv.second;
            if (!l.empty() && l[0].s1 < t - 4.0) {
                std::vector<EfxNote> keep;
                for (const EfxNote &e : l)
                    if (e.s1 >= t - 4.0)
                        keep.push_back(e);
                l.swap(keep);
            }
        }
    }

    void tone_filter_block(double t)
    {
        for (auto &kv : tone_fx) {
            ToneFx &tf = kv.second;
            const NoteClass *k = tf.k;
            // ITS OWN EFFECT's (live._filter_for: none where the part is on
            // the module's -- the module's takes the tone's place)
            Comps o;
            bool chain = false;
            if (tf.ex && !(efx && nv_efx_live_on(efx, tf.ch))) {
                int st = -1;
                const char *why = "";
                const double *fc = tone_chain(tf, &st, &why);
                if (fc && efx_moves(fc)) {
                    chain_comps(tf.ex, tf.ch, kv.first, fc, t, o);
                    chain = true;
                }
            }
            if (!tf.kind && !chain)
                continue;
            if (!tf.kind) {
                S.filter_swing(kv.first, rate, [&](double f) { return o.h(f, false); },
                               [&](double f) { return o.h(f, true); });
                continue;
            }
            const double pa = k->flt_p[0], pb = k->flt_p[1];
            if (tf.kind == 3) {
                const double *c = k->flt_c;
                double st = steps_at(tf.at, c[4], t);
                double x = st < 0.0 ? 0.0 : (st > 127.0 ? 127.0 : st);
                double u = 2.0 * x / 127.0 - 1.0;
                double g = c[3] * u + (1.0 - c[3]) * pow(u, 3.0);
                const double ctrl = c[1] * pow(g < 0.0 ? c[0] / c[1] : c[2] / c[1], fabs(g));
                const double q = pa > 0.1 ? pa : 0.1;
                auto own = [&](double f) {      // (efxfilter.response, type 2)
                    double xx = f / (ctrl > 1.0 ? ctrl : 1.0);
                    double a = 1.0 - xx * xx, b = xx / q;
                    double w = 1.0 / sqrt(a * a + b * b);
                    return (1.0 - pb) + pb * w;
                };
                S.filter_swing(kv.first, rate, [&](double f) { return chain ? o.h(f, false, own(f)) : own(f); },
                               [&](double f) { return chain ? o.h(f, true, own(f)) : own(f); });
                continue;
            }
            const int nm = k->n_mouth;
            double F[3];
            if (!tf.wheel.empty()) {
                // the wheel's vowel (efxfilter.mouth_wheel): the states closed
                // to open along it, between two the centres interpolated
                double pos = steps_at(tf.wheel, k->mouth_glide, t);
                double x = pos < 0.0 ? 0.0 : (pos > 127.0 ? 127.0 : pos);
                double u = x / 127.0 * (double)(nm - 1);
                long j = (long)floor(u);
                j = j < nm - 2 ? j : nm - 2;
                double w = u - (double)j;
                for (int fk = 0; fk < 3; fk++)
                    F[fk] = k->mouth_wst[j][fk] * (1.0 - w) + k->mouth_wst[j + 1][fk] * w;
            } else {
                // the wander (efxfilter.MouthWander): a state drawn by its
                // share, held a log-normal dwell, glided to from where it was
                while (tf.next_t <= t) {
                    const double r = nv_npy_uniform(tf.g);
                    int i = 0;
                    while (i < nm && k->mouth_cdf[i] <= r)
                        i++;
                    tf.target = i < nm ? i : nm - 1;
                    tf.next_t += k->mouth_dw[0] * exp(k->mouth_dw[1] * nv_npy_next(tf.g));
                }
                const double *tg = k->mouth_st[tf.target];
                if (!tf.have_cur || k->mouth_glide <= 0.0) {
                    for (int fk = 0; fk < 3; fk++)
                        tf.cur[fk] = tg[fk];
                    tf.have_cur = true;
                } else {
                    double kk = exp(-(t - tf.t > 0.0 ? t - tf.t : 0.0) / k->mouth_glide);
                    for (int fk = 0; fk < 3; fk++)
                        tf.cur[fk] = tg[fk] + (tf.cur[fk] - tg[fk]) * kk;
                }
                tf.t = t;
                for (int fk = 0; fk < 3; fk++)
                    F[fk] = tf.cur[fk];
            }
            auto own = [&](double f) {          // (efxfilter.response, type 5: VOWEL)
                static const double BW[3] = {80.0, 110.0, 160.0}, AM[3] = {1.0, 0.7, 0.5};
                double h = pa;
                for (int fk = 0; fk < 3; fk++) {
                    double u = (f - F[fk]) / (0.5 * BW[fk]);
                    h = h + AM[fk] / (1.0 + u * u);
                }
                return h * pb;
            };
            S.filter_swing(kv.first, rate, [&](double f) { return chain ? o.h(f, false, own(f)) : own(f); },
                           [&](double f) { return chain ? o.h(f, true, own(f)) : own(f); });
        }
    }

    // ---- the Moog's knobs (live's set_synth, _moog_tick, _messenger_cc)
    // A KNOB TURNS, IT DOES NOT JUMP: what the notes play glides toward what
    // was asked, MOOG_GLIDE_PER_BLOCK a block, the waveshapes, levels and
    // pitches (MOOG_GLIDES); the octave is a switch and jumps
    static constexpr double MOOG_GLIDE_PER_BLOCK = 0.01;
    static bool moog_glides(int k)
    {
        return k == NV_MK_OSC1_WAVE || k == NV_MK_OSC2_WAVE || k == NV_MK_SUB_WAVE || k == NV_MK_OSC1_LEVEL
               || k == NV_MK_OSC2_LEVEL || k == NV_MK_SUB_LEVEL || k == NV_MK_NOISE_LEVEL
               || k == NV_MK_OSC2_FREQ || k == NV_MK_TUNE || k == NV_MK_MOD_AMOUNT;
    }
    // (part pid, layer) -> {knob: where it has got to}, in the order they
    // began (live.moog_glide: (pid, 'b') a layered voice's second Messenger)
    std::vector<std::pair<std::pair<long long, int>, std::map<int, double>>> moog_glide;
    bool msgr_all = false;                  // --messenger: every part reads the chart
    bool msgr_pre107 = false;               // ...a Messenger on firmware before 1.0.7 (moog.messenger_chart)
    bool msgr_said = false;
    std::map<std::pair<int, int>, int> msg_msb;     // (channel, CC) -> a knob's coarse half
    static const MoogLayer *moog_spec(const Patch &p, int layer) { return layer ? p.moog_b : p.moog; }
    // the part's panel on a layer (moog.panel_of: its patch's, its own knobs
    // over it), and where a knob still glides, where it has got to
    void moog_pn(const Patch &p, bool glide, double *pn, int layer = 0) const
    {
        const MoogLayer *m = moog_spec(p, layer);
        memcpy(pn, m->pn, sizeof m->pn);
        for (auto &kv : layer ? p.syn_b : p.syn)
            pn[kv.first] = kv.second;
        if (glide)
            for (auto &g : moog_glide)
                if (g.first == std::make_pair(p.pid, layer))
                    for (auto &kv : g.second)
                        pn[kv.first] = kv.second;
    }
    // the panel its notes read again (_moog_panel_for's knobs), each layer
    // A SYNCED Messenger plays its panel as live builds it (moog.weights'
    // C coefficients), not the export's file-render spectrum: after a patch
    // is set up (organ_start), its layers built again
    void moog_sync_build(Patch &p)
    {
        if (p.moog && (p.moog->pn[NV_MK_SYNC] != 0.0 || (p.moog_b && p.moog_b->pn[NV_MK_SYNC] != 0.0)))
            moog_rebuild(p);
    }
    void moog_rebuild(Patch &p)
    {
        for (int layer = 0; layer < 2; layer++) {
            const MoogLayer *m = moog_spec(p, layer);
            std::shared_ptr<MoogLayer> &mb = layer ? p.mb_b : p.mb;
            bool gl = false;
            for (auto &g : moog_glide)
                gl = gl || g.first == std::make_pair(p.pid, layer);
            if (!m || ((layer ? p.syn_b : p.syn).empty() && !gl && m->pn[NV_MK_SYNC] == 0.0)) {
                mb.reset();
                continue;
            }
            double pn[NV_MK_N];
            moog_pn(p, true, pn, layer);
            auto b = std::make_shared<MoogLayer>();
            if (nv_moog_build(pn, m, b.get()) == 0)
                mb = b;
        }
    }
    Patch *patch_pid(long long id)
    {
        for (Patch &p : patches)
            if (p.pid == id)
                return &p;
        return nullptr;
    }
    // live.set_synth (from the hardware, or the panel; layer 1 a layered
    // voice's second Messenger, ours alone): the part has the new value at
    // once, so the next press steps from it; after the block's events
    // (live.post) the notes sounding are told where they glide FROM and
    // refreshed. Refused here: SYNC (its spectrum), and a turn that would
    // move a pitch or shape under the MF-104M -- said, and left
    bool set_synth(Patch &p, int knob, double value, int layer = 0)
    {
        const MoogLayer *m = moog_spec(p, layer);
        if (!m)
            return false;
        double pn[NV_MK_N];
        moog_pn(p, false, pn, layer);
        const double old = pn[knob];
        std::map<int, double> &syn = layer ? p.syn_b : p.syn;
        std::map<int, double> was = syn;
        syn[knob] = value;
        double tr[NV_MK_N];
        moog_pn(p, true, tr, layer);
        MoogLayer probe;
        if (nv_moog_build(tr, m, &probe) != 0) {
            syn.swap(was);
            if (!msgr_said)
                fprintf(stderr, "nvlive: refused: the Messenger's %s live -- the knob left as it was\n",
                        "pitch or shape under the MF-104M");
            msgr_said = true;
            return false;
        }
        moog_rebuild(p);
        Post q{2, {}, nullptr};
        q.pid = p.pid;
        q.knob = knob;
        q.old = old;
        q.layer = layer;
        posts.push_back(std::move(q));
        return true;
    }
    void synth_post(const Post &q, long long n0)
    {
        Patch *p = patch_pid(q.pid);
        if (!p || !p->moog)
            return;
        bool sounding = false;
        for (auto &kv : S.live)
            sounding = sounding || std::get<0>(kv.first) == q.pid;
        if (moog_glides(q.knob) && sounding) {
            const std::pair<long long, int> gk(q.pid, q.layer);
            auto it = std::find_if(moog_glide.begin(), moog_glide.end(),
                                   [&](const std::pair<std::pair<long long, int>, std::map<int, double>> &g) {
                                       return g.first == gk;
                                   });
            if (it == moog_glide.end()) {
                moog_glide.emplace_back(gk, std::map<int, double>());
                it = moog_glide.end() - 1;
            }
            it->second.emplace(q.knob, q.old);      // (setdefault: the first turn's start)
            moog_rebuild(*p);
        }
        moog_refresh(*p, n0);
    }
    // live._moog_tick: one block of every gliding knob
    void moog_tick(long long n0)
    {
        std::vector<std::pair<long long, int>> ids;
        for (auto &g : moog_glide)
            ids.push_back(g.first);
        for (const auto &id : ids) {
            auto it = std::find_if(moog_glide.begin(), moog_glide.end(),
                                   [&](const std::pair<std::pair<long long, int>, std::map<int, double>> &g) {
                                       return g.first == id;
                                   });
            Patch *p = patch_pid(id.first);
            if (!p || !moog_spec(*p, id.second)) {
                moog_glide.erase(it);
                continue;
            }
            double base[NV_MK_N];
            moog_pn(*p, false, base, id.second);
            std::map<int, double> &now = it->second;
            for (auto k = now.begin(); k != now.end();) {
                double d = base[k->first] - k->second;
                if (fabs(d) <= MOOG_GLIDE_PER_BLOCK) {
                    k = now.erase(k);
                } else {
                    k->second += d > 0 ? MOOG_GLIDE_PER_BLOCK : -MOOG_GLIDE_PER_BLOCK;
                    ++k;
                }
            }
            if (now.empty())
                moog_glide.erase(it);
            moog_rebuild(*p);
            moog_refresh(*p, n0);
        }
    }
    // moog.messenger_value: a Messenger CC's value as the panel knob's
    // (kind 0 '14', 1 'tune', 2 '7', 3 'foot', 4 'track', 5 'mode', 6 'onoff')
    static double msgr_value(int kind, int msb, int lsb)
    {
        switch (kind) {
        case 0: return lsb >= 0 ? ((msb << 7) | lsb) / 16383.0 : msb / 127.0;
        case 1: return msgr_value(0, msb, lsb) + 28.3 / (2.0 * 7.0 * 100.0);
        case 2: return msb / 127.0;
        case 3: { static const int F[4] = {32, 16, 8, 4}; return F[std::min(3, msb / 32)]; }
        case 4: return msb < 64 ? 0.0 : 1.0;
        case 5: return std::min(3, msb / 32);
        }
        return msb >= 64 ? 1.0 : 0.0;
    }
    // moog.MESSENGER_CC (its manual's Appendix A; MESSENGER_CC_PRE107 before
    // 1.0.7: SUB WAVE on CC11, 14-bit): CC -> (knob, kind), knob -2 one the
    // simulator does not model (taken all the same), -1 not the chart's
    void msgr_chart(int cc, int *knob, int *kind) const
    {
        struct E { int cc, knob, kind; };
        static const E C[] = {
            {9, NV_MK_OSC1_WAVE, 0}, {14, NV_MK_OSC2_WAVE, 0}, {10, NV_MK_TUNE, 1}, {12, NV_MK_OSC2_FREQ, 0},
            {15, NV_MK_OSC1_LEVEL, 0}, {16, NV_MK_OSC2_LEVEL, 0}, {17, NV_MK_SUB_LEVEL, 0},
            {8, NV_MK_NOISE_LEVEL, 0}, {19, NV_MK_CUTOFF, 0}, {21, NV_MK_RESONANCE, 0},
            {22, NV_MK_EG_AMOUNT, 0}, {23, NV_MK_F_ATTACK, 0}, {24, NV_MK_F_DECAY, 0}, {25, NV_MK_F_SUSTAIN, 0},
            {26, NV_MK_F_RELEASE, 0}, {28, NV_MK_A_ATTACK, 0}, {29, NV_MK_A_DECAY, 0}, {30, NV_MK_A_SUSTAIN, 0},
            {31, NV_MK_A_RELEASE, 0}, {71, NV_MK_SUB_WAVE, 2}, {75, NV_MK_OSC1_OCTAVE, 3},
            {76, NV_MK_OSC2_OCTAVE, 3}, {78, NV_MK_KB_TRACK, 4}, {79, NV_MK_RES_BASS, 6}, {109, NV_MK_MODE, 5},
            {13, NV_MK_MOD_AMOUNT, 0}, {72, NV_MK_MOD_DEST, 5}, {77, NV_MK_SYNC, 6}, {3, NV_MK_LFO1_RATE, 0},
            {4, NV_MK_LFO1_DEPTH, 0}, {83, NV_MK_LFO1_SHAPE, 5}, {85, NV_MK_LFO1_DEST, 5},
            {93, NV_MK_LFO1_RESET, 6}, {5, NV_MK_GLIDE, 0}, {81, NV_MK_A_VEL, 6},
            {27, NV_MK_LFO2_RATE, 0}, {116, NV_MK_LFO2_PITCH, 6}, {117, NV_MK_LFO2_CUT, 6},
            {118, NV_MK_LFO2_AMP, 6}, {112, NV_MK_F_LOOP, 6}, {113, NV_MK_A_LOOP, 6}, {80, NV_MK_F_VEL, 6},
            {114, NV_MK_MULTITRIG, 6},
            {2, -2, 0}, {18, -2, 0}, {20, -2, 0}, {73, -2, 0}, {89, -2, 0},
            {102, -2, 0}, {107, -2, 0}, {108, -2, 0},
        };
        *knob = -1;
        *kind = 0;
        if (msgr_pre107 && cc == 71)
            return;
        if (msgr_pre107 && cc == 11) {
            *knob = NV_MK_SUB_WAVE;
            return;
        }
        for (const E &e : C)
            if (e.cc == cc) {
                *knob = e.knob;
                *kind = e.kind;
                return;
            }
    }
    // ---- A MESSENGER TO SET (live.open_messenger's queue): what is sent,
    // through msgr_send (nvlive's: its thread writes it, the audio thread
    // never waits); the pitch-bend range it is set to; the note each of its
    // channels plays (messenger_note, in the order they began)
    void (*msgr_send)(void *, const uint8_t *, int) = nullptr;
    void *msgr_ctx = nullptr;
    double msgr_bend = 2.0;
    std::vector<std::pair<int, std::tuple<long long, int, int>>> msgr_note;
    void msgr_put(int a, int b, int c)
    {
        const uint8_t m[3] = {(uint8_t)a, (uint8_t)b, (uint8_t)c};
        msgr_send(msgr_ctx, m, 3);
    }
    // moog.messenger_cc_value: a knob's value as the Messenger's CC, *lo -1
    // where it has no fine half
    static int msgr_cc_value(int kind, double v, int *lo)
    {
        *lo = -1;
        auto clip = [](double x) { double y = x < 1.0 ? x : 1.0; return y > 0.0 ? y : 0.0; };
        switch (kind) {
        case 0: {
            int x = (int)nearbyint(clip(v) * 16383);
            *lo = x & 0x7F;
            return x >> 7;
        }
        case 1: return msgr_cc_value(0, v - 28.3 / (2.0 * 7.0 * 100.0), lo);
        case 2: return (int)nearbyint(clip(v) * 127);
        case 3: { int f = (int)v; return (f == 32 ? 0 : f == 16 ? 1 : f == 8 ? 2 : 3) * 32 + 16; }
        case 4: return v < 0.5 ? 32 : 96;
        case 5: return (int)v * 32 + 16;
        }
        return v != 0.0 ? 127 : 0;
    }
    // live.messenger_sync: a Moog part's panel (its patch's, its own knobs
    // over it) as the chart's CCs on its channel, coarse halves first, in
    // the chart's order -- or just one knob (knob >= 0)
    void messenger_sync(const Patch &p, int knob = -1)
    {
        if (!msgr_send || p.drums || !p.moog)
            return;
        double pn[NV_MK_N];
        moog_pn(p, false, pn);
        const int ch = p.channel >= 0 ? p.channel : 0;
        for (int cc = 0; cc < 128; cc++) {
            int k, kind, lo;
            msgr_chart(cc, &k, &kind);
            if (k < 0 || (knob >= 0 && k != knob))
                continue;
            if (k == NV_MK_A_VEL && pn[k] < 0.0)
                continue;                   // (the voice's own touch: the hardware's switch left as it is)
            msgr_put(0xB0 | ch, cc, msgr_cc_value(kind, pn[k], &lo));
            if (lo >= 0)
                msgr_put(0xB0 | ch, cc + 32, lo);
        }
    }
    // live.messenger_pitch: the Messenger's note bent from the equal-tempered
    // A440 key it plays to where this part's tuner, the key's tuning and the
    // wheel put it (its range msgr_bend); its newest note owns the channel
    void messenger_pitch(const Patch &p, int ch, int note)
    {
        if (!msgr_send || p.drums || !p.moog)
            return;
        const int sn = note + p.transpose;
        if (sn < 0 || sn > 127 || note < 0 || note > 127)
            return;
        double b = bend[ch] * (key_ratio(p, ch, note) * 1.0);
        double ours = nv_tcache_freq(p.cache, sn) * b;
        double et = 440.0 * pow(2.0, (note - 69) / 12.0);
        double cents = 1200.0 * log2(ours / et);
        int val = (int)nearbyint(cents / (100.0 * msgr_bend) * 8192);
        const int mch = p.channel >= 0 ? p.channel : 0;
        auto it = std::find_if(msgr_note.begin(), msgr_note.end(),
                               [&](const std::pair<int, std::tuple<long long, int, int>> &x) { return x.first == mch; });
        if (it != msgr_note.end())
            it->second = std::make_tuple(p.pid, ch, note);  // (a dict's key keeps its place)
        else
            msgr_note.emplace_back(mch, std::make_tuple(p.pid, ch, note));
        val = std::max(-8192, std::min(8191, val)) + 8192;
        msgr_put(0xE0 | mch, val & 0x7F, val >> 7);
    }
    // live._messenger_rebend: the wheel moved on a channel -- its Messenger note follows
    void messenger_rebend(int ch)
    {
        if (!msgr_send)
            return;
        std::vector<std::pair<int, std::tuple<long long, int, int>>> ns = msgr_note;
        for (auto &x : ns)
            if (std::get<1>(x.second) == ch)
                if (Patch *p = patch_pid(std::get<0>(x.second)))
                    messenger_pitch(*p, ch, std::get<2>(x.second));
    }

    // live._messenger_cc: a CC on a channel where a part reads the
    // Messenger's chart -- that part's knob turned (a part that is not a Moog:
    // the knobs with a GM sound controller, moog.MESSENGER_GM, turn that) --
    // or false, the message General MIDI's
    bool messenger_cc(int ch, int cc, int v, long long n0)
    {
        std::vector<int> mine;
        bool hears = false, gm = false;
        for (size_t i = 0; i < patches.size(); i++) {
            const Patch &p = patches[i];
            if (!(p.msgr || msgr_all) || !(p.channel < 0 || p.channel == ch))
                continue;
            hears = true;
            if (!p.drums && p.moog)
                mine.push_back((int)i);
            else
                gm = true;
        }
        if (!hears)
            return false;
        if (cc == 73) {
            // HOLD holds both contours at sustain after the key goes up: the
            // sustain pedal, which on a synth holds the gate
            control(ch, 64, v >= 64 ? 127 : 0, n0);
            return true;
        }
        int knob, kind;
        double val;
        int hi = cc - 32, hk, hkind;
        if (cc >= 32) {
            msgr_chart(hi, &hk, &hkind);
        } else {
            hk = -1;
            hkind = 0;
        }
        if (hk >= 0 && (hkind == 0 || hkind == 1)) {     // the fine half of a knob
            auto m = msg_msb.find(std::make_pair(ch, hi));
            if (m == msg_msb.end())
                return true;
            knob = hk;
            val = msgr_value(hkind, m->second, v);
        } else {
            msgr_chart(cc, &knob, &kind);
            if (knob == -1)
                return false;                       // CC1, 7, 11, 64, 74 ...: GM's
            if (knob == -2)
                return true;                        // the panel's, not modelled yet
            if (kind == 0 || kind == 1)
                msg_msb[std::make_pair(ch, cc)] = v;
            val = msgr_value(kind, v, -1);
        }
        for (int i : mine)
            set_synth(patches[i], knob, val);
        int gcc = knob == NV_MK_CUTOFF ? 74 : knob == NV_MK_RESONANCE ? 71 : knob == NV_MK_A_ATTACK ? 73
                  : knob == NV_MK_A_DECAY ? 75 : knob == NV_MK_A_RELEASE ? 72 : knob == NV_MK_LFO1_RATE ? 76
                  : knob == NV_MK_LFO1_DEPTH ? 77 : -1;
        if (gm && gcc >= 0) {
            double g = 127.0 * val;                 // (max(0, min(127, 127 v)), Python's)
            g = g < 127.0 ? g : 127.0;
            sound_cc(ch, gcc, g > 0.0 ? g : 0.0, n0);
        }
        return true;
    }

    void control(int ch, int cc, int v, long long n0)
    {
        if (messenger_cc(ch, cc, v, n0))
            return;                                 // a Messenger's panel, on a part that reads its chart
        // THE WHEEL's JOBS ON CCs OF THEIR OWN (tonelib.WHEEL_CC): CC1 is GM's
        // modulation, and the wheel a default ROUTE to each part's other
        // jobs (live._wheel_route) -- not a reset's CC1 = 0 (GM 2 3.5.2)
        const bool wr = cc == 1 && !wheel_reset;
        if (cc == NV_CC_CRANK || cc == NV_CC_MOUTH)
            job_at[std::make_pair(ch, cc)] = v;     // (their CCs' own: live's job_at)
        if (wr)
            for (const Patch &p : patches) {
                if (!(p.channel < 0 || p.channel == ch))
                    continue;
                const NoteClass *k = p.drums ? nullptr : nv_tcache_class(p.cache, p.program);
                if (p.organ && p.organ->siren_up)
                    job_at[std::make_pair(ch, (int)NV_CC_CRANK)] = v;     // (the crank, routed)
                if (k && k->flt_set == 2 && k->flt_k == 4)
                    job_at[std::make_pair(ch, (int)NV_CC_MOUTH)] = v;     // (the mouth, routed)
            }
        if (cc == NV_CC_LESLIE) {
            // THE ROTOR's SPEED (CC80): the file's zones (leslie.zone), the
            // rotors aimed there as the half-moon aims them
            bool les = false;
            for (const Patch &p : patches)
                les = les || (p.leslie && (p.channel < 0 || p.channel == ch));
            if (les) {
                const double ladder[3] = {0.0, S.les[3], S.les[4]};
                half_moon = v < 42 ? 0 : v < 85 ? 1 : 2;
                rotor_horn.target = ladder[half_moon];
                rotor_drum.target = ladder[half_moon];
            }
        }
        if (cc == NV_CC_SCANNER) {
            cc_scan[ch] = v;                           // the scanner's selector (_scan_stamp)
            if (scan_async)                         // ...its new position prepared (_scan_prefetch)
                for (const Patch &p : patches)
                    if (p.scanner && (p.channel < 0 || p.channel == ch)) {
                        std::pair<int, int> st = scan_setting(p, ch);
                        if (st.first) {
                            std::lock_guard<std::mutex> lk(scan_mu);
                            scan_prefetch_locked(st.first, st.second);
                            scan_cv.notify_all();
                        }
                        break;
                    }
        }
        if (cc == 7 || cc == 11) {
            (cc == 7 ? vol : expr)[ch] = v;
            double g = chan_gain(ch), was = cgain_set[ch] ? cgain[ch] : 1.0;
            if (g != was) {
                cgain[ch] = g;
                cgain_set[ch] = true;
                S.channel_gain(sounding(ch), g / std::max(was, 1e-9));
            }
            if (cc == 11 && !xnote.empty())         // a harmonium's bellows: its Expression
                harmonium_bellows(ch, v);
        } else if (cc >= 43 && cc <= 45 && harmonium_on()) {
            harmonium_word(ch, cc, v, n0);
        } else if (cc == 10) {
            int was = cpan[ch];
            if (v != was) {
                cpan[ch] = v;
                S.repan(sounding(ch), v, was, rate, false);
            }
        } else if (cc == 64) {
            int was_v = pedal_v[ch];
            pedal_v[ch] = v;
            reg_felt(ch, n0);
            if (v < was_v) {
                std::set<std::pair<int, int>> gone;
                for (auto &k : pedalled)
                    if (k.first == ch && !down.count(k) && !pedal_holds(ch, k.second))
                        gone.insert(k);
                std::vector<Key> rel;
                for (auto &kv : S.live)
                    if (gone.count(std::make_pair((int)std::get<1>(kv.first), (int)std::get<2>(kv.first))))
                        rel.push_back(kv.first);
                for (auto &k : rel)
                    S.release(k, n0);
                for (auto &k : gone)
                    pedalled.erase(k);
                if (reg_on)                         // _reg_channel: the pedal came up
                    for (size_t i = 0; i < reg.size(); i++)
                        if (reg[i].ch == ch)
                            reg_damper(ch, n0, -1, true);
            }
        } else if (cc == 91) {
            // a DISTANCE (live's): CC91 over GM's 40 times the room's nominal
            // one, on the notes sounding too
            double d = v / 40.0;
            S.send[ch] = d;
            S.send_said.insert(ch);
            for (long q : sounding(ch))
                S.sw[q] = (float)d;
        } else if (cc == 67) {
            soft[ch] = v >= 64;
        } else if (cc == 5) {
            porta_time[ch] = v;
        } else if (cc == 65) {
            porta_on[ch] = v >= 64;
        } else if (cc == 84) {
            porta_src[ch] = v;              // the next note-on's source, once
        } else if (cc == 66) {
            // SOSTENUTO: a snapshot of the keys down as it goes down; up, the
            // ones it held let go where nothing else holds them
            bool dn = v >= 64, was = sost.count(ch) > 0;
            if (dn && !was) {
                std::set<int> &h = sost[ch];
                for (auto &d : down)
                    if (d.first == ch)
                        h.insert(d.second);
            } else if (!dn && was) {
                std::set<int> gone = sost[ch];
                sost.erase(ch);
                std::vector<Key> rel;
                for (auto &kv : S.live) {
                    int c2 = (int)std::get<1>(kv.first), nt = (int)std::get<2>(kv.first);
                    if (c2 == ch && gone.count(nt) && !down.count(std::make_pair(c2, nt)) && !pedal_holds(ch, nt))
                        rel.push_back(kv.first);
                }
                for (auto &k : rel)
                    S.release(k, n0);
                for (int nt : gone)
                    pedalled.erase(std::make_pair(ch, nt));
                if (reg_on)                         // _reg_channel
                    for (size_t i = 0; i < reg.size(); i++)
                        if (reg[i].ch == ch)
                            reg_damper(ch, n0, -1, true);
            }
        } else if (cc == 98 || cc == 99) {
            rpn_none[ch] = true;                    // NRPN select: no RPN takes the data
            (cc == 99 ? nrpn_msb : nrpn_lsb)[ch] = v;
        } else if (cc == 101 || cc == 100) {
            if (rpn_none[ch]) {
                rpn_none[ch] = false;
                rpn_msb[ch] = rpn_lsb[ch] = 127;
            }
            nrpn_msb[ch] = nrpn_lsb[ch] = 127;      // (live's nrpn None)
            (cc == 101 ? rpn_msb : rpn_lsb)[ch] = v;
        } else if (cc == 6 || cc == 38) {
            int gs = rpn_none[ch] ? gs_sound_nrpn(nrpn_msb[ch], nrpn_lsb[ch]) : -1;
            if (gs >= 0) {                          // GS's sound NRPNs: CC71-78's older address
                if (cc == 6)
                    sound_cc(ch, gs, v, n0);
            } else
                rpn_data(ch, cc, v, n0);
        } else if (cc >= 71 && cc <= 78) {
            sound_cc(ch, cc, v, n0);
        } else if (cc == 96 || cc == 97) {
            rpn_step(ch, cc == 96, n0);
        } else if (cc == 121) {
            reset_controllers(ch, n0);
        } else if (cc == 120) {
            all_sound_off(ch, n0);
        } else if (cc == 123) {
            all_notes_off(ch, n0);
        } else if (cc >= 124 && cc <= 127) {
            // CHANNEL MODE, as live sends it: all four are All Notes Off, MONO
            // and POLY All Sound Off first; MONO (126) one voice on the
            // channel, POLY (127) as many as it plays
            if (cc >= 126)
                all_sound_off(ch, n0);
            all_notes_off(ch, n0);
            mono_stack[ch].clear();
            mono_cur[ch] = -1;
            if (cc == 126)
                mono[ch] = true;
            else if (cc == 127)
                mono[ch] = false;
        } else if ((cc == NV_CC_DRIVE || wr) && hammond_on(ch)) {
            // A HAMMOND'S MOD WHEEL, OR AN AMPLIFIED VOICE'S (live's
            // wheel_roles): with a valve, its drive (LIVE_DRIVE_STEPS over
            // the range) -- a guitar amp's own gain knob; else its swell pedal --
            // CC11's squared law on the part, the notes sounding rescaled,
            // floored at -80 dB
            for (const Patch &p : patches) {
                if (!(p.leslie || p.wheel_swell || p.amp > 0.0) || !(p.channel < 0 || p.channel == ch))
                    continue;
                if (cc == NV_CC_DRIVE && !(p.amp > 0.0))
                    continue;                       // (CC12 the drive's: the swell is the wheel's route alone)
                // A TONEWHEEL ORGAN's WHEEL IS ITS SWELL, its drive or not: the
                // drive CC12's and the panel's knob (live's wheel_roles, _wheel_route)
                if (p.amp > 0.0 && !(cc == 1 && p.leslie && p.wheel_swell)) {
                    int step = (int)nearbyint(v / 127.0 * LIVE_DRIVE_STEPS);
                    auto it = drive_step.find(p.pid);
                    if (it == drive_step.end() || it->second != step) {
                        drive_step[p.pid] = step;
                        amp_dirty.insert(p.pid);
                    }
                } else if (p.wheel_swell) {
                    double sw = std::max(pow(v / 127.0, 2.0), 1e-4), was = swell;
                    swell = sw;
                    if (sw != was)
                        S.channel_gain(sounding_tone(ch, p.pid, p.cache, false), sw / was);
                }
                break;
            }
        } else if ((cc == NV_CC_TREMOLO || wr) && wheel_trem_on(ch)) {
            wheel_tremolo(ch, v);
        } else if ((cc == NV_CC_CRESCENDO || wr) && organ_on(ch)) {
            // AN ORGAN'S MOD WHEEL IS ITS CRESCENDO PEDAL (live's 'crescendo' role)
            // (not the double siren's: its wheel is the crank and nothing else)
            for (size_t pi = 0; pi < patches.size(); pi++)
                if (patches[pi].organ && patches[pi].organ->n_order && !patches[pi].organ->siren_up
                    && (patches[pi].channel < 0 || patches[pi].channel == ch))
                    crescendo((int)pi, v, n0);
        } else if ((cc == NV_CC_DETUNE || wr) && detune_wheel) {
            static const int steps[3] = {0, 64, 127};       // live.DETUNE_STEPS: min(), the first of a tie
            int best = steps[0];
            for (int st : steps)
                if (abs(st - v) < abs(best - v))
                    best = st;
            speed = best;
        }
        if (cc == 2)
            cc2v[ch] = v / 127.0;               // breath: a siren's air (siren_block)
        if (cc == 1) {                          // the wheel's last (live's wheel_at)
            wheel_seen[ch] = true;
            wheel_v[ch] = v;
        }
        if (cc == NV_CC_MOUTH || wr) {          // THE MOUTH (its 'mouth' job: CC19, or the wheel's route)
            bool mouth = false;
            for (const Patch &p : patches) {
                const NoteClass *k = p.drums ? nullptr : nv_tcache_class(p.cache, p.program);
                mouth = mouth || ((p.channel < 0 || p.channel == ch) && k && k->flt_set == 2 && k->flt_k == 4);
            }
            if (mouth)
                tone_ctl(ch, true, n0, v);
        }
        if (cc == 1)                            // LFO 2's depth (live's 'lfo2' role)
            for (const Patch &p : patches)
                if ((p.channel < 0 || p.channel == ch) && lfo2_role(p))
                    lfo2_w[p.pid] = v / 127.0;
        if (cc == 1) {                          // THE MOD WHEEL IS VIBRATO (live's 'vibrato' role)
            bool any = false;
            for (const Patch &p : patches)
                any = any || (vib_role(p) && (p.channel < 0 || p.channel == ch));
            if (any) {
                double w = v / 127.0;
                double cents = modrange[ch] >= 0.0 ? modrange[ch] : mod_cents;
                vib_mod[ch] = pow(2.0, cents * w / 1200.0) - 1.0;
                vib_modw[ch] = w;
                for (const Patch &p : patches)
                    if (vib_role(p) && (p.channel < 0 || p.channel == ch))
                        vib_apply(p, ch, n0);
            }
        }
        if (cc == NV_CC_DRONES || wr)           // THE DRONES (live's 'drones' job: CC18, or the wheel's route)
            for (int pi = 0; pi < (int)patches.size(); pi++) {
                if (!(patches[pi].channel < 0 || patches[pi].channel == ch))
                    continue;
                Use u(*this, pi);
                const NoteClass *k = drone_class();
                if (!k)
                    continue;
                int nd = k->n_dratio;
                int n = std::max(0, std::min(nd, (int)nearbyint(v / 127.0 * nd)));
                auto it = drone_count.find(pid);
                if (it == drone_count.end() || it->second != n) {
                    drone_count[pid] = n;
                    if (chanting(ch))
                        drones(ch, n0);
                }
            }
        if (cc == NV_CC_DRONES || wr)           // THE PUNGI's DRONE NOTE (live's 'drone note': CC18, or the route)
            for (int pi = 0; pi < (int)patches.size(); pi++) {
                if (!(patches[pi].channel < 0 || patches[pi].channel == ch))
                    continue;
                Use u(*this, pi);
                const NoteClass *k = dnote_class();
                if (!k)
                    continue;
                const int ns = k->n_dchoice, st = std::min(ns - 1, v * ns / 128);   // (even steps over the choices)
                auto it = drone_sel.find(pid);
                if (it == drone_sel.end() || it->second != st) {
                    drone_sel[pid] = st;
                    if (chanting(ch))
                        drone_note(ch, n0);
                }
            }
        if (cc == NV_CC_TONE || wr)             // A CLAVINET's TONE ROCKERS (live's 'tone' job: CC70, or the route)
            for (const Patch &p : patches) {
                if (!p.clav || !(p.channel < 0 || p.channel == ch))
                    continue;
                int step = (int)nearbyint(v / 127.0 * 4.0);
                auto it = clav_step.find(p.pid);
                if (it == clav_step.end() || it->second != step) {
                    clav_step[p.pid] = step;
                    S.clav_tone(step, sounding_tone(ch, p.pid, p.cache, false));
                }
            }
        if (!key_tone.empty() && (cc == 1 || cc == NV_CC_TREMOLO || cc == NV_CC_TONE)) {
            // ...and the tones held from before a program change (live's
            // _tone_wheel): CC1 their vibrato; CC92 and CC70 their tremolo and
            // rockers -- or the wheel's route, on the parts that have the job
            n0_wheel = n0;
            if (cc == 1)
                tone_wheel(ch, v, 4, false);
            if (cc == NV_CC_TREMOLO)
                tone_wheel(ch, v, 1, false);
            if (cc == NV_CC_TONE)
                tone_wheel(ch, v, 2, false);
            if (wr)
                tone_wheel(ch, v, 1 | 2, true);
        }
    }

    // THE DAMPERS IN BETWEEN (live._damp_block, _damp_open, _damp_mark;
    // damper.py): a pedalled note whose key's contact is in the band takes a
    // TRACK -- its damping so far at the block's two edges, DM -- its rows
    // marked with it (the slab's dk, and dg their weight). A track stays with
    // its note while any row of it sounds. Track numbers are handed out in
    // `pedalled`'s order, which is not live's (a Python set's): the same
    // tracks under other numbers, the same sound.
    static const int DAMP_TRACKS = 256;     // live.DAMP_TRACKS
    bool dmp_on = false;
    double dmp_full = 0.0, dmp_res = 0.0, dmp_knee = 0.0, dmp_beta = 0.0, dmp_ln = 0.0;
    struct DTrack {
        int t;
        double dc, f0, non, lr, lra, af, su, vdb;
        std::set<Key> keys;
        std::vector<long> slots;            // sorted (np.union1d)
    };
    std::vector<std::pair<std::pair<int, int>, DTrack>> dtracks;   // live's damp_tracks, in its order
    std::vector<int> free_tracks;
    std::vector<float> DM = std::vector<float>(2 * DAMP_TRACKS, 0.0f);
    std::vector<long> DMO = std::vector<long>(DAMP_TRACKS, 0), DMB = std::vector<long>(DAMP_TRACKS, 0),
                      DMN = std::vector<long>(DAMP_TRACKS, 2);

    long dtrack_find(int ch, int note) const
    {
        for (size_t i = 0; i < dtracks.size(); i++)
            if (dtracks[i].first == std::make_pair(ch, note))
                return (long)i;
        return -1;
    }

    void damp_block(long long n0, long long frames)
    {
        if (!dmp_on)
            return;
        bool any = !dtracks.empty();
        for (int c = 0; c < 16 && !any; c++)
            any = pedal_v[c] > 0 && pedal_v[c] < 127;
        if (!any)
            return;
        double dt = frames / rate;
        for (const auto &cn : pedalled) {
            int ch = cn.first, note = cn.second;
            double c = nv_damper_contact(pedal_v[ch], note, 128);
            std::vector<Key> ks;
            for (auto &kv : S.live)
                if (std::get<1>(kv.first) == ch && std::get<2>(kv.first) == note)
                    ks.push_back(kv.first);
            for (const Key &k : ks) {
                long i = dtrack_find(ch, note);
                if (i < 0) {
                    if (!(0.0 < c && c < 1.0) || free_tracks.empty())
                        continue;
                    i = damp_open(ch, note);
                    if (i < 0)
                        continue;
                }
                if (!dtracks[i].second.keys.count(k))
                    damp_mark(dtracks[i].second, k);
            }
        }
        for (size_t i = 0; i < dtracks.size();) {
            DTrack &st = dtracks[i].second;
            std::vector<long> alive;
            for (long q : st.slots)
                if (S.busy[q] && S.dk[q] == st.t)
                    alive.push_back(q);
            if (alive.empty()) {
                free_tracks.push_back(st.t);
                dtracks.erase(dtracks.begin() + i);
                continue;
            }
            st.slots = alive;
            int ch = dtracks[i].first.first, note = dtracks[i].first.second;
            double c = pedalled.count(dtracks[i].first) ? nv_damper_contact(pedal_v[ch], note, 128) : 0.0;
            double d0 = st.dc;
            if (0.0 < c && c < 1.0) {
                double x = std::max(((double)n0 - st.non) / rate, 0.0);
                double dc = st.su + (1.0 - st.su) * ((1.0 - st.af) * exp(-st.lr * x) + st.af * exp(-st.lra * x));
                double lvl = st.vdb + 20.0 * log10(dc >= 1e-12 ? dc : 1e-12) - d0;
                double thr = -dmp_knee * c / (1.0 - c);         // damper.threshold_db
                double r = dmp_full * c;                        // damper.rate_db_s
                st.dc = d0 + (lvl > thr ? r : r * dmp_res) * dt;
            }
            DM[2 * st.t] = (float)d0;
            DM[2 * st.t + 1] = (float)st.dc;
            i++;
        }
    }

    // a track for this pressed-and-pedalled key: its level model from its
    // fundamental's decay and the strike's velocity (live._damp_open)
    long damp_open(int ch, int note)
    {
        std::vector<long> rows;
        std::vector<Key> ks;
        for (auto &kv : S.live)
            if (std::get<1>(kv.first) == ch && std::get<2>(kv.first) == note) {
                ks.push_back(kv.first);
                rows.insert(rows.end(), kv.second.begin(), kv.second.end());
            }
        if (rows.empty())
            return -1;
        double f0 = 440.0 * pow(2.0, (note - 69) / 12.0);
        long j = rows[0];
        double best = 0.0;
        for (size_t q = 0; q < rows.size(); q++) {
            double nf = (double)S.f4[F4_nf][rows[q]];
            double d = fabs(log((nf >= 1e-3 ? nf : 1e-3) / f0));
            if (q == 0 || d < best) {
                best = d;
                j = rows[q];
            }
        }
        DTrack st;
        st.t = free_tracks.back();
        free_tracks.pop_back();
        st.dc = 0.0;
        st.f0 = f0;
        st.non = (double)S.i8[0][j];
        st.lr = S.f4[F4_logr][j];
        st.lra = S.f4[F4_logrA][j];
        st.af = S.f4[F4_aft][j];
        st.su = S.f4[F4_sus][j];
        auto kv = key_vel.find(std::make_pair(ch, note));
        int vel = kv == key_vel.end() ? 100 : kv->second;
        st.vdb = 40.0 * log10((vel > 1 ? vel : 1) / 127.0);
        DM[2 * st.t] = DM[2 * st.t + 1] = 0.0f;
        dtracks.emplace_back(std::make_pair(ch, note), st);
        long i = (long)dtracks.size() - 1;
        for (const Key &k : ks)
            damp_mark(dtracks[i].second, k);
        return i;
    }

    // this slab key's rows onto the track: its index, each row's weight
    void damp_mark(DTrack &st, const Key &k)
    {
        st.keys.insert(k);
        long li = S.live_find(k);
        if (li < 0 || S.live[li].second.empty())
            return;
        for (long q : S.live[li].second) {
            S.dk[q] = st.t;
            double x = std::max((double)S.f4[F4_nf][q], 1e-6) / std::max(st.f0, 1e-6);
            S.dg[q] = (float)(dmp_ln * pow(x, dmp_beta));     // damper.weight
            st.slots.insert(std::lower_bound(st.slots.begin(), st.slots.end(), q), q);
        }
        st.slots.erase(std::unique(st.slots.begin(), st.slots.end()), st.slots.end());
    }

    // THE FREE-STRING REGISTER, LIVE (live._reg_strike, _reg_damper, _reg_felt,
    // _reg_channel, _reg_pump, _reg_place, _reg_close): one register channel
    // per MIDI channel (register.LiveChannel, livereg.cpp), its free rows the
    // register's own slots, one per string mode, retired once -- at its
    // damper or under the floor; its forced rows on their note's key (layer
    // REG_FORCED), going when it does.
    typedef std::complex<double> cplx;
    static const long long REG_KEY = -2, REG_FORCED = -3;      // live's "reg" and REG_FORCED layers
    static const long REG_PLACE_MAX = 256;
    bool reg_on = false;
    std::vector<StringMode> rmodes;
    // (the audio thread's copy above, the worker's in wk -- each changed on
    // its own thread, as live's worker builds its own: Bank)
    Bank wk;                                // the worker's
    std::shared_ptr<Bank> staged_bank;      // the next swap's (nv_part_swap_bank)
    bool reg_forgetting = false;            // live.reg_forgetting: the old strings' answers still coming
    double r_kappa = 0, r_knock = 0, r_fall = 0, r_fl = 0, r_beta = 0, r_rel = 0, r_full = 0, r_resid = 0,
           r_ln = 0, r_blk = 128;
    int r_top = 128, r_pedals = 1;
    bool reg_note[128];
    struct RegSt {
        int ch;
        bool ready = false;
        double row_f8[NF8], row_f4[NF4];
        int32_t row_i4[NI4];
        std::vector<long> slot_of;
        std::vector<double> n_floor, krate, dw;
        bool has_krate = false;
        std::map<int, double> krate_key;
    };
    std::vector<RegSt> reg;                         // by channel, as made (live's self.reg)
    struct Pend {
        int ch;
        long long sid;
        int note;
        long long at;
        std::vector<long> slots;
        bool has_plucked = false;                   // a harpsichord's: the choirs it plucked,
        std::vector<int> plucked;
        std::map<long, long> slot_choir;            // ...and each slot's choir
    };
    // a harpsichord's choirs, for its register (Strings.choir_bridges, cross, buffs)
    std::vector<long> r_cbr;
    double r_cross = 1.0;
    std::vector<int> r_buffs;
    std::vector<Pend> reg_pend;
    struct Reply {
        int kind;                                   // 0 'free', 1 'forced', 2 'forgot'
        int ch, note;
        std::vector<long> modes;
        std::vector<cplx> z;
        double at, floor;
        std::vector<long> f_slot;
        std::vector<double> f_wgt, f_beta;
        std::vector<cplx> f_val;
    };
    std::deque<Reply> reg_out;
    std::vector<std::pair<std::pair<int, int>, long long>> reg_strike_of;      // (ch, note) -> sid, a dict's order
    std::vector<std::pair<long long, std::vector<long>>> reg_retire;          // n0 -> slots closed, a dict's order
    long long reg_sid = 0;
    bool reg_live = false, reg_more = false;
    long reg_budget = 0, reg_dropped = 0;

    // THE WORKER'S JOBS (live's reg_jobs: 'strike', 'release', 'damp',
    // 'felt'), each answered onto a queue of Replies by run_job -- at once,
    // into reg_out, when the register runs in step (the checks: live's
    // worker as regsync answers it); or on a worker thread of its own
    // (reg_async, nvlive: live's worker process, off the audio thread), its
    // answers taken up at the next pump after they are ready
    struct Job {
        int kind;                                   // 0 strike, 1 release, 2 damp, 3 felt, 4 forget
        std::shared_ptr<Bank> bank;                 // ...the new strings (forget)
        int ch, note = -1, R = 0;
        long long sid = 0;
        double at = 0.0;
        std::vector<double> cols, rates;
        std::vector<long> d;
        std::vector<int> keys;
        bool has_plucked = false;
        std::vector<int> plucked;
        std::vector<long> choir;                    // each row's (empty: none)
    };
    std::map<int, void *> lcs;                      // channel -> its register (the worker's chans)
    bool reg_async = false;
    std::thread reg_thread;
    std::mutex reg_mu;
    std::condition_variable reg_cv;
    std::deque<Job> reg_jobs;
    std::deque<Reply> reg_done;
    std::atomic<long> reg_ndone{0};
    bool reg_stop = false;

    ~Part()
    {
        if (amp_thread.joinable()) {
            {
                std::lock_guard<std::mutex> lk(amp_mu);
                amp_stop = true;
            }
            amp_cv.notify_all();
            amp_fine_cv.notify_all();
            amp_thread.join();
            if (amp_fine_thread.joinable())
                amp_fine_thread.join();
        }
        if (scan_thread.joinable()) {
            {
                std::lock_guard<std::mutex> lk(scan_mu);
                scan_stop = true;
            }
            scan_cv.notify_all();
            scan_thread.join();
        }
        if (reg_thread.joinable()) {
            {
                std::lock_guard<std::mutex> lk(reg_mu);
                reg_stop = true;
            }
            reg_cv.notify_all();
            reg_thread.join();
        }
        for (auto &kv : lcs)
            nv_lreg_free(kv.second);
    }

    void *lc_of(int ch)
    {
        auto it = lcs.find(ch);
        if (it != lcs.end())
            return it->second;
        void *h = nv_lreg_new(wk.modes.data(), (int)wk.modes.size(), rate, wk.kappa, wk.knock, wk.fall, wk.fl, wk.top,
                              wk.beta);
        if (!wk.cbr.empty())
            nv_lreg_choirs(h, (int)wk.cbr.size(), wk.cbr.data(), wk.cross, (int)wk.buffs.size() / 2, wk.buffs.data());
        if (wk.keyed && wk.keyed->reg_keyed) {
            const NoteClass *k = wk.keyed;
            nv_lreg_keys(h, k->reg_kb, k->reg_cross, k->reg_partner, k->reg_partner_k, k->reg_ktilt, k->reg_nkp,
                         k->reg_kp_x, k->reg_kp_db);
        }
        lcs[ch] = h;
        return h;
    }

    // a 'free' answer (the job's at sample `at`) onto out -- always, or only
    // with modes in it; returns the strike's forced rows
    int answer(int ch, void *lc, int n, double at, bool always, std::deque<Reply> &out)
    {
        Reply r;
        r.kind = 0;
        r.ch = ch;
        r.note = -1;
        r.at = at;
        r.modes.resize(n);
        std::vector<double> zz(2 * (size_t)n + 2);
        double fl;
        int nf = nv_lreg_answer(lc, r.modes.data(), zz.data(), &fl);
        r.z.resize(n);
        for (int q = 0; q < n; q++)
            r.z[q] = cplx(zz[2 * q], zz[2 * q + 1]);
        r.floor = fl;
        if (always || n)
            out.push_back(std::move(r));
        return nf;
    }

    void run_job(const Job &j, std::deque<Reply> &out)
    {
        if (j.kind == 4) {
            // a part's strings gone with its voice (live's worker 'forget'):
            // its channels, and the new voice's bank in their place
            for (auto &kv : lcs)
                nv_lreg_free(kv.second);
            lcs.clear();
            if (j.bank)
                wk = *j.bank;
            Reply r;
            r.kind = 2;
            r.ch = -1;
            r.note = -1;
            r.at = j.at;
            r.floor = 0.0;
            out.push_back(std::move(r));
            return;
        }
        void *lc = lc_of(j.ch);
        if (j.kind == 0) {
            int n = j.has_plucked || !j.choir.empty()
                        ? nv_lreg_pluck(lc, j.sid, j.note, j.at, j.R, j.cols.data(), j.d.data(), j.keys.data(),
                                        (int)j.keys.size(), j.plucked.data(),
                                        j.has_plucked ? (int)j.plucked.size() : -1,
                                        j.choir.empty() ? nullptr : j.choir.data())
                        : nv_lreg_strike(lc, j.sid, j.note, j.at, j.R, j.cols.data(), j.d.data(), j.keys.data(),
                                         (int)j.keys.size());
            int nf = answer(j.ch, lc, n, j.at, true, out);
            if (nf) {
                Reply r;
                r.kind = 1;
                r.ch = j.ch;
                r.note = j.note;
                r.at = j.at;
                r.f_slot.resize(nf); r.f_wgt.resize(nf); r.f_beta.resize(nf);
                std::vector<double> v(2 * (size_t)nf);
                nv_lreg_forced(lc, r.f_slot.data(), r.f_wgt.data(), r.f_beta.data(), v.data());
                for (int q = 0; q < nf; q++)
                    r.f_val.push_back(cplx(v[2 * q], v[2 * q + 1]));
                out.push_back(std::move(r));
            }
        } else if (j.kind == 1) {
            answer(j.ch, lc, nv_lreg_release(lc, j.sid, j.at, j.keys.data(), (int)j.keys.size()), j.at, true, out);
        } else if (j.kind == 2) {
            nv_lreg_damp(lc, j.keys.data(), (int)j.keys.size());
        } else {
            answer(j.ch, lc, nv_lreg_felt(lc, j.at, j.keys.data(), j.rates.data(), (int)j.keys.size()), j.at, false,
                   out);
        }
    }

    void send_job(Job &&j)
    {
        if (!reg_async) {
            run_job(j, reg_out);
            return;
        }
        {
            std::lock_guard<std::mutex> lk(reg_mu);
            reg_jobs.push_back(std::move(j));
        }
        reg_cv.notify_one();
    }

    void reg_worker()
    {
        std::unique_lock<std::mutex> lk(reg_mu);
        while (true) {
            reg_cv.wait(lk, [&] { return reg_stop || !reg_jobs.empty(); });
            if (reg_stop)
                return;
            Job j = std::move(reg_jobs.front());
            reg_jobs.pop_front();
            lk.unlock();
            std::deque<Reply> out;
            run_job(j, out);
            lk.lock();
            for (Reply &r : out)
                reg_done.push_back(std::move(r));
            reg_ndone = (long)reg_done.size();
        }
    }

    void start_reg_worker()
    {
        if (reg_async)
            return;
        reg_async = true;
        reg_thread = std::thread([this] { reg_worker(); });
    }

    // the worker's answers so far, onto reg_out (the audio thread)
    void reg_collect()
    {
        if (!reg_async || reg_ndone.load() == 0)
            return;
        std::lock_guard<std::mutex> lk(reg_mu);
        for (Reply &r : reg_done)
            reg_out.push_back(std::move(r));
        reg_done.clear();
        reg_ndone = 0;
    }

    RegSt *reg_of(int ch)
    {
        for (RegSt &st : reg)
            if (st.ch == ch)
                return &st;
        return nullptr;
    }

    long strike_of_find(int ch, int note) const
    {
        for (size_t i = 0; i < reg_strike_of.size(); i++)
            if (reg_strike_of[i].first == std::make_pair(ch, note))
                return (long)i;
        return -1;
    }

    // _reg_free: the keys whose strings are free on this channel, now (sorted)
    std::vector<int> reg_free(int ch) const
    {
        std::set<int> keys;
        if (r_pedals && pedal_v[ch] > 0) {
            std::vector<int> held;
            for (int k = 21; k < 109; k++)
                if (nv_damper_contact(pedal_v[ch], k, r_top) < 1.0)
                    held.push_back(k);
            if (held.size() == 88)
                return held;
            keys.insert(held.begin(), held.end());
        }
        for (auto &d : down)
            if (d.first == ch)
                keys.insert(d.second);
        auto sq = sost.find(ch);
        if (r_pedals && sq != sost.end())
            keys.insert(sq->second.begin(), sq->second.end());
        for (int k = r_top; k < 109; k++)
            keys.insert(k);
        return std::vector<int>(keys.begin(), keys.end());
    }

    void reg_strike(int ch, int note, long long n0, const nv::live::Template &T, const std::vector<long> &slots,
                    const std::vector<int> *plucked = nullptr, const std::map<long, long> *slot_choir = nullptr)
    {
        if (!reg_of(ch)) {
            RegSt st;
            st.ch = ch;
            for (int c = 0; c < NF8; c++) st.row_f8[c] = T.f8[c][0];
            for (int c = 0; c < NF4; c++) st.row_f4[c] = T.f4[c][0];
            for (int c = 0; c < NI4; c++) st.row_i4[c] = T.i4[c][0];
            reg.push_back(st);
        }
        reg_sid += 1;
        long i = strike_of_find(ch, note);
        if (i >= 0)
            reg_strike_of[i].second = reg_sid;
        else
            reg_strike_of.push_back(std::make_pair(std::make_pair(ch, note), reg_sid));
        Pend pd{ch, reg_sid, note, n0, slots};
        if (plucked) {
            pd.has_plucked = true;
            pd.plucked = *plucked;
        }
        if (slot_choir)
            pd.slot_choir = *slot_choir;
        reg_pend.push_back(std::move(pd));
    }

    void reg_forget(const std::shared_ptr<Bank> &b, long long n0)
    {
        for (RegSt &st : reg)
            if (st.ready) {
                std::vector<long> ms;
                for (long m = 0; m < (long)st.slot_of.size(); m++)
                    if (st.slot_of[m] >= 0)
                        ms.push_back(m);
                reg_close(st, ms, n0, r_rel);
            }
        reg.clear();
        reg_strike_of.clear();
        reg_pend.clear();
        reg_out.clear();
        reg_forgetting = true;
        // the audio thread's copy: the new voice's
        rmodes = b->modes;
        r_kappa = b->kappa; r_knock = b->knock; r_fall = b->fall; r_fl = b->fl; r_beta = b->beta;
        r_rel = b->rel; r_top = b->top; r_pedals = b->pedals;
        if (b->note.size() == 128)
            for (int k = 0; k < 128; k++)
                reg_note[k] = b->note[k] != 0;
        r_cbr = b->cbr; r_cross = b->cross; r_buffs = b->buffs;
        Job j;
        j.kind = 4;
        j.at = (double)n0;
        j.bank = b;
        send_job(std::move(j));
    }

    void reg_close(RegSt &st, const std::vector<long> &modes, long long n0, double re_)
    {
        if (modes.empty())
            return;
        std::vector<long> sl;
        for (long m : modes) {
            long s = st.slot_of[m];
            st.slot_of[m] = -1;
            if (S.busy[s])
                sl.push_back(s);
        }
        if (sl.empty())
            return;
        for (long s : sl) {
            S.i8[1][s] = n0;
            S.f4[F4_re][s] = (float)re_;
        }
        for (auto &e : reg_retire)
            if (e.first == n0) {
                e.second.insert(e.second.end(), sl.begin(), sl.end());
                return;
            }
        reg_retire.push_back(std::make_pair(n0, sl));
    }

    void reg_damper(int ch, long long n0, int released, bool pedal_up)
    {
        RegSt *st = reg_of(ch);
        if (!st)
            return;
        std::vector<int> fv = reg_free(ch);
        std::set<int> free(fv.begin(), fv.end());
        if (released >= 0 && !free.count(released)) {
            long i = strike_of_find(ch, released);
            if (i >= 0) {
                long long sid = reg_strike_of[i].second;
                reg_strike_of.erase(reg_strike_of.begin() + i);
                Job j;
                j.kind = 1; j.ch = ch; j.sid = sid; j.at = (double)n0; j.keys = fv;
                send_job(std::move(j));
            }
        }
        if (pedal_up) {
            std::vector<std::pair<std::pair<int, int>, long long>> was = reg_strike_of;
            for (auto &e : was) {
                if (e.first.first != ch || free.count(e.first.second))
                    continue;
                reg_strike_of.erase(reg_strike_of.begin() + strike_of_find(e.first.first, e.first.second));
                Job j;
                j.kind = 1; j.ch = ch; j.sid = e.second; j.at = (double)n0; j.keys = fv;
                send_job(std::move(j));
            }
        }
        if (st->ready) {
            std::vector<long> dead;
            for (long m = 0; m < (long)rmodes.size(); m++)
                if (!free.count((int)rmodes[m].key) && st->slot_of[m] >= 0)
                    dead.push_back(m);
            reg_close(*st, dead, n0, r_rel);
        }
        Job j;
        j.kind = 2;
        j.ch = ch;
        for (int k = 21; k < 109; k++)
            if (!free.count(k))
                j.keys.push_back(k);
        send_job(std::move(j));
    }

    void reg_felt(int ch, long long n0)
    {
        if (!reg_on)
            return;
        int v = pedal_v[ch];
        for (RegSt &st : reg) {
            if (st.ch != ch || !st.ready || !r_pedals)
                continue;
            std::vector<int> keys;
            std::vector<double> rates;
            for (int k = 21; k < 109; k++) {
                double c = nv_damper_contact(v, k, r_top);
                double r = (0.0 < c && c < 1.0) ? r_full * c * r_resid * r_ln : 0.0;
                auto it = st.krate_key.find(k);
                if (r != (it == st.krate_key.end() ? 0.0 : it->second)) {
                    st.krate_key[k] = r;
                    keys.push_back(k);
                    rates.push_back(r);
                }
            }
            if (keys.empty())
                continue;
            if (!st.has_krate) {
                st.has_krate = true;
                st.krate.assign(rmodes.size(), 0.0);
                for (const StringMode &q : rmodes) {
                    double f0 = 440.0 * pow(2.0, ((double)q.key - 69.0) / 12.0);
                    st.dw.push_back(pow((q.f >= 1e-6 ? q.f : 1e-6) / f0, r_beta));
                }
            }
            for (size_t q = 0; q < keys.size(); q++)
                for (size_t m = 0; m < rmodes.size(); m++)
                    if (rmodes[m].key == keys[q])
                        st.krate[m] = rates[q] * st.dw[m];
            Job j;
            j.kind = 3; j.ch = st.ch; j.at = (double)n0; j.keys = keys; j.rates = rates;
            send_job(std::move(j));
        }
    }

    void reg_pump(long long n0)
    {
        for (RegSt &st : reg) {
            if (!st.ready) {
                st.slot_of.assign(rmodes.size(), -1);
                st.n_floor.assign(rmodes.size(), 0.0);
                st.ready = true;
                reg_felt(st.ch, n0);            // a pedal already in the band
            }
        }
        // this block's strikes: their stamped direct rows, read now, and the keys free now
        std::vector<Pend> pend;
        pend.swap(reg_pend);
        for (const Pend &p : pend) {
            std::vector<long> idx;
            for (long s : p.slots)
                if (S.busy[s])
                    idx.push_back(s);
            if (idx.empty())
                continue;
            double mn = 0.0;
            std::vector<double> dl(idx.size());
            for (size_t q = 0; q < idx.size(); q++) {
                dl[q] = (double)S.f4[F4_delL][idx[q]] + (double)S.f4[F4_delR][idx[q]];
                if (q == 0 || dl[q] < mn)
                    mn = dl[q];
            }
            std::vector<long> d;
            for (size_t q = 0; q < idx.size(); q++)
                if (dl[q] <= mn + 2.0)
                    d.push_back(idx[q]);
            int R = (int)d.size();
            // drv's columns, livereg.cpp's order: om p0 delL aM non logr logrA aft sus tbav tau tcut
            std::vector<double> cols(12 * (size_t)R);
            static const int f4c[] = {6, 7, 8, 9, 16, 17, 18};      // logr logrA aft sus tbav tau tcut
            for (int r = 0; r < R; r++) {
                long s = d[r];
                cols[0 * R + r] = S.f8[F8_om][s];
                cols[1 * R + r] = S.f8[F8_p0][s];
                cols[2 * R + r] = (double)S.f4[F4_delL][s];
                cols[3 * R + r] = 0.5 * ((double)S.aL0[s] + (double)S.aR0[s]);
                cols[4 * R + r] = (double)S.i8[0][s];
                for (int c = 0; c < 7; c++)
                    cols[(5 + c) * R + r] = (double)S.f4[f4c[c]][s];
            }
            Job j;
            j.kind = 0; j.ch = p.ch; j.sid = p.sid; j.note = p.note; j.at = (double)p.at; j.R = R;
            j.has_plucked = p.has_plucked;
            j.plucked = p.plucked;
            if (!p.slot_choir.empty())              // each row's choir: the bridge it drives through
                for (long s : d) {
                    auto it = p.slot_choir.find(s);
                    j.choir.push_back(it == p.slot_choir.end() ? 0 : it->second);
                }
            j.cols.swap(cols);
            j.d.swap(d);
            j.keys = reg_free(p.ch);
            send_job(std::move(j));
        }
        reg_collect();
        // what the worker handed back: until a block's worth is placed
        reg_more = false;
        reg_budget = REG_PLACE_MAX;
        while (!reg_out.empty() && !reg_more) {
            Reply r = std::move(reg_out.front());
            reg_out.pop_front();
            reg_place(n0, r);
        }
        // rows fallen under the floor: ended
        if (reg_live) {
            bool live_ = false;
            for (RegSt &st : reg) {
                if (!st.ready)
                    continue;
                bool on = false;
                std::vector<long> done;
                for (size_t m = 0; m < st.slot_of.size(); m++)
                    if (st.slot_of[m] >= 0) {
                        on = true;
                        if (st.n_floor[m] <= (double)n0)
                            done.push_back((long)m);
                    }
                if (on) {
                    reg_close(st, done, n0, (double)r_blk);
                    for (long x : st.slot_of)
                        if (x >= 0) {
                            live_ = true;
                            break;
                        }
                }
            }
            reg_live = live_;
        }
        for (auto &e : reg_retire)
            S.retiring.push_back(std::make_pair(e.second, e.first));
        reg_retire.clear();
    }

    void reg_place(long long n0, Reply &job)
    {
        if (job.kind == 2) {
            reg_forgetting = false;             // its old answers all in
            return;
        }
        if (reg_forgetting)
            return;                             // an answer from the strings it had
        RegSt *stp = reg_of(job.ch);
        if (!stp || !stp->ready)
            return;
        RegSt &st = *stp;
        if (job.kind == 0) {
            // ONLY STRINGS STILL FREE NOW
            if (!job.modes.empty()) {
                std::vector<int> fv = reg_free(job.ch);
                std::set<int> free(fv.begin(), fv.end());
                std::vector<long> m2;
                std::vector<cplx> z2;
                for (size_t q = 0; q < job.modes.size(); q++)
                    if (free.count((int)rmodes[job.modes[q]].key)) {
                        m2.push_back(job.modes[q]);
                        z2.push_back(job.z[q]);
                    }
                job.modes.swap(m2);
                job.z.swap(z2);
            }
            if (job.modes.empty())
                return;
            long nb = std::max(reg_budget, 1L);
            if ((long)job.modes.size() > nb) {
                // A BLOCK'S WORTH AT A TIME: the rest waits a block
                Reply rest = job;
                rest.modes.assign(job.modes.begin() + nb, job.modes.end());
                rest.z.assign(job.z.begin() + nb, job.z.end());
                reg_out.push_front(std::move(rest));
                job.modes.resize(nb);
                job.z.resize(nb);
                reg_more = true;
            }
            reg_budget -= (long)job.modes.size();
            if (reg_budget <= 0)
                reg_more = true;
            std::vector<long> old;
            for (long m : job.modes)
                if (st.slot_of[m] >= 0)
                    old.push_back(m);
            reg_close(st, old, n0, (double)r_blk);
            // each mode's rate: its own, and the felt's in the band
            double dt = (double)n0 - job.at;
            dt = 0.0 > dt ? 0.0 : dt;                               // Python's max(n0 - at, 0.0)
            std::vector<long> modes;
            std::vector<cplx> zz;
            std::vector<double> lr;
            for (size_t q = 0; q < job.modes.size(); q++) {
                long m = job.modes[q];
                double l = st.has_krate ? rmodes[m].alpha + st.krate[m] : rmodes[m].alpha;
                double g = exp(-l * dt / rate);
                cplx a(job.z[q].real() * g - job.z[q].imag() * 0.0, job.z[q].real() * 0.0 + job.z[q].imag() * g);
                if (hypot(a.real(), a.imag()) >= job.floor) {
                    modes.push_back(m);
                    zz.push_back(a);
                    lr.push_back(l);
                }
            }
            long n = (long)modes.size();
            if (!n)
                return;
            // the rows: the template's first, with the mode's own pitch, level, ears and decay
            std::vector<std::vector<double>> tf8(NF8, std::vector<double>(n));
            std::vector<std::vector<float>> tf4(NF4, std::vector<float>(n));
            std::vector<std::vector<long long>> ti8(NI8, std::vector<long long>(n, n0));
            std::vector<std::vector<int32_t>> ti4(NI4, std::vector<int32_t>(n));
            std::vector<float> hr(n, 1.0f);
            double hd = S.headroom_d > 1e-12 ? S.headroom_d : 1e-12;
            static const int zero4[] = {7, 8, 9, 10, 13, 12, 14, 15, 16, 18, 19, 24};   // logrA aft sus cv sj crl csc cbw tbav tcut vd az
            for (long q = 0; q < n; q++) {
                long m = modes[q];
                const StringMode &M_ = rmodes[m];
                for (int c = 0; c < NF8; c++) tf8[c][q] = st.row_f8[c];
                for (int c = 0; c < NF4; c++) tf4[c][q] = (float)st.row_f4[c];
                for (int c = 0; c < NI4; c++) ti4[c][q] = st.row_i4[c];
                double om = (2.0 * M_PI * M_.f) / rate;
                double ph = atan2(zz[q].imag(), zz[q].real());
                double mag = hypot(zz[q].real(), zz[q].imag()) / hd;
                tf8[F8_om][q] = om;
                tf8[F8_p0][q] = ph - om * M_.dl;
                tf8[F8_p0R][q] = ph - om * M_.dr;
                tf4[F4_aL][q] = (float)(mag * M_.hl);
                tf4[F4_aR][q] = (float)(mag * M_.hr);
                tf4[F4_nf][q] = (float)M_.f;
                tf4[26][q] = (float)M_.f;                           // nfr
                tf4[3][q] = (float)r_blk;                           // fa
                tf4[6][q] = (float)lr[q];                           // logr
                tf4[F4_delL][q] = (float)M_.dl;
                tf4[F4_delR][q] = (float)M_.dr;
                tf4[F4_rdl][q] = 0.0f;
                for (int c : zero4)
                    tf4[c][q] = 0.0f;
                ti4[3][q] = (int32_t)M_.string;                     // pl
                ti4[I4_fx][q] = -1;
                ti4[5][q] = 0;                                      // mk
            }
            const double *f8p[NF8];
            const float *f4p[NF4];
            const long long *i8p[NI8];
            const int32_t *i4p[NI4];
            for (int c = 0; c < NF8; c++) f8p[c] = tf8[c].data();
            for (int c = 0; c < NF4; c++) f4p[c] = tf4[c].data();
            for (int c = 0; c < NI8; c++) i8p[c] = ti8[c].data();
            for (int c = 0; c < NI4; c++) i4p[c] = ti4[c].data();
            Key key(pid, job.ch, REG_KEY, REG_KEY);
            if (!S.stamp(f8p, f4p, i8p, i4p, hr.data(), n, key, n0, 1.0, 0, false, NAN, job.ch)) {
                reg_dropped += n;
                return;
            }
            std::vector<long> got = S.last_slots;
            long li = S.live_find(key);
            if (li >= 0)
                S.live.erase(S.live.begin() + li);         // the register keeps its own slots
            if (cpan[job.ch] != 64)
                S.repan(got, cpan[job.ch], 64, rate, true);
            for (long q = 0; q < n; q++) {
                long m = modes[q];
                st.slot_of[m] = got[q];
                double a = hypot(zz[q].real(), zz[q].imag()) / job.floor;
                st.n_floor[m] = (double)n0 + rate * log(a >= 1.0 ? a : 1.0) / (lr[q] >= 1e-9 ? lr[q] : 1e-9);
            }
            reg_live = true;
            return;
        }
        // 'forced': its note still sounding -- and still ITS note
        double win = 0.05 * rate;
        std::vector<long> sl;
        std::vector<double> wgt, beta;
        std::vector<cplx> F;
        for (size_t q = 0; q < job.f_slot.size(); q++) {
            long s = job.f_slot[q];
            double age = (double)(S.i8[0][s]) - job.at;                // float(non - at)
            double d = age - (double)S.f4[F4_rdl][s];
            if (S.busy[s] && S.i8[1][s] >= n0 && 0.0 <= d && d <= win) {
                sl.push_back(s);
                wgt.push_back(job.f_wgt[q]);
                beta.push_back(job.f_beta[q]);
                F.push_back(job.f_val[q]);
            }
        }
        if (sl.empty())
            return;
        reg_budget -= (long)sl.size();
        if (reg_budget <= 0)
            reg_more = true;
        long n = (long)sl.size();
        std::vector<std::vector<double>> tf8(NF8, std::vector<double>(n));
        std::vector<std::vector<float>> tf4(NF4, std::vector<float>(n));
        std::vector<std::vector<long long>> ti8(NI8, std::vector<long long>(n, n0));
        std::vector<std::vector<int32_t>> ti4(NI4, std::vector<int32_t>(n));
        std::vector<float> hr(n, 1.0f);
        double hd = S.headroom_d > 1e-12 ? S.headroom_d : 1e-12;
        for (long q = 0; q < n; q++) {
            long s = sl[q];
            for (int c = 0; c < NF8; c++) tf8[c][q] = S.f8[c][s];
            for (int c = 0; c < NF4; c++) tf4[c][q] = S.f4[c][s];
            for (int c = 0; c < NI4; c++) ti4[c][q] = S.i4[c][s];
            double a0 = (double)n0 - (double)S.i8[0][s];
            double age = (a0 >= 0.0 ? a0 : 0.0) / rate;
            double g = hypot(F[q].real(), F[q].imag()) * wgt[q] * exp(-beta[q] * age) / hd;
            double om = S.f8[F8_om][s];
            double ph = atan2(F[q].imag(), F[q].real())
                        + glide_phase(om * rate, (double)S.f4[16][s], (double)S.f4[17][s], (double)S.f4[18][s], age);
            tf4[F4_aL][q] = (float)((double)S.aL0[s] * g);
            tf4[F4_aR][q] = (float)((double)S.aR0[s] * g);
            tf8[F8_p0][q] = S.f8[F8_p0][s] + ph;
            tf8[F8_p0R][q] = S.f8[F8_p0R][s] + ph;
            tf4[3][q] = (float)r_blk;                                   // fa
            tf4[6][q] = (float)beta[q];                                 // logr
            tf4[7][q] = 0.0f;                                           // logrA
            tf4[8][q] = 0.0f;                                           // aft
            tf4[9][q] = beta[q] > 0 ? 0.0f : 1.0f;                      // sus
            tf4[16][q] = 0.0f;                                          // tbav
            tf4[F4_rdl][q] = 0.0f;
        }
        const double *f8p[NF8];
        const float *f4p[NF4];
        const long long *i8p[NI8];
        const int32_t *i4p[NI4];
        for (int c = 0; c < NF8; c++) f8p[c] = tf8[c].data();
        for (int c = 0; c < NF4; c++) f4p[c] = tf4[c].data();
        for (int c = 0; c < NI8; c++) i8p[c] = ti8[c].data();
        for (int c = 0; c < NI4; c++) i4p[c] = ti4[c].data();
        if (!S.stamp(f8p, f4p, i8p, i4p, hr.data(), n, Key(pid, job.ch, job.note, REG_FORCED), n0, 1.0, 0, false,
                     NAN, job.ch))
            reg_dropped += n;
    }

    // register._glide_phase_x
    static double glide_phase(double Wi, double tb, double tau, double cut, double t)
    {
        double ct = cut < 0 ? -cut * 1048576.0 : cut;
        double e = exp(-(!(ct < t) ? t : ct) / tau);
        if (cut >= 0)
            return Wi * tb * tau * (1.0 - e);
        double acc = 0.0, term = 1.0, ek = 1.0;
        for (int k = 1; k < 41; k++) {
            term = term * tb / k;
            ek = ek * e;
            acc = acc + term * (1.0 - ek) / k;
        }
        return Wi * tau * acc;
    }

    // LIVE'S SIDE TABLES (live.Slab's, at rest: a piano never moves them)
    // and its render over the slab (Renderer.render, one thread): every slot
    // from 0 past the last busy one through synth_voice, the fast bursts
    // apart through synth_voice_xdec (synth_partials' _xdec_rows), and the
    // rows on a damper track after them through synth_voice_damp (sd)
    std::vector<float> G = std::vector<float>(1, 1.0f), Sx = std::vector<float>(1, 1.0f);
    std::vector<float> BRt = std::vector<float>(65, 1.0f), BLt = std::vector<float>(130, 1.0f);
    std::vector<double> BCt = std::vector<double>(65, 0.0);
    // (the Moog's tables: the slab's -- live.Slab's FT, KN and the mod rows)
    std::vector<float> &FT = S.FT, &KN = S.KN;
    std::vector<int32_t> &MPI = S.MPI, &MKI = S.MKI;
    std::vector<double> &MPC = S.MPC;
    std::vector<float> &MPR = S.MPR, &MPK = S.MPK;
    void *moog_pcells = nullptr, *moog_srows = nullptr;     // synthkernel.c's moog_pitch_cells, moog_shape_rows
    float sh[4] = {0.06f, 1.6f, 3.5f, 1500.0f};
    double xdec_nepers = 2.302585;

    void init_tables() {}                   // (the slab's own: Slab.moog_alloc)

    // THE GPU'S BLOCK (live.GpuRenderer._render_now, gpurender.BlockTables):
    // the setup on the CPU, voice_block over every busy slot (through the
    // damper's build, its tracks handed over first, when one of them is on a
    // track), into page-aligned tables that grow when a block asks for more
    // cells or sidebands -- then the samples: the OpenCL GPU (gpu.cpp) or
    // the C reference (voice_samples)
    struct Table {
        void *p = nullptr;
        long n = 0, size = 0;           // records, and each one's bytes
        ~Table() { free(p); }
        // gpurender.aligned_zeros: n records, whole pages and whole records
        void make(long want, long sz)
        {
            long a = 4096, b = sz;
            while (b) {
                long t = a % b;
                a = b;
                b = t;
            }
            long per = 4096 / a;                    // lcm(4096, sz) / sz
            long m = std::max((std::max(want, 1L) + per - 1) / per * per, per);
            free(p);
            p = aligned_alloc(4096, (size_t)(m * sz));
            memset(p, 0, (size_t)(m * sz));
            n = m;
            size = sz;
        }
        long bytes() const { return n * size; }
    };
    struct GpuSide {
        void *vb = nullptr, *vbd = nullptr, *vds = nullptr, *vs = nullptr, *cl = nullptr;
        // the Moog extensions' build (gpurender's ensure_gpu_moogx_lib): its
        // voice_block, voice_damp_set and voice_moogx_set
        void *vbm = nullptr, *vmd = nullptr, *vmm = nullptr;
        long gpu_min = 1000;
        int nthr = 4;
        Table D, C, SB;
        Table D2, C2, SB2;              // the pipeline's second set (its blocks take turns)
    } gp;
    // PIPELINED (live.GpuRenderer, TUNING_GPU_PIPELINE): every block a block
    // late, so the CPU builds block n+1's tables while the GPU renders block
    // n -- the block started (rendered on the CPU and held, or launched on
    // the GPU in its turn's tables) and the one started before it finished
    bool pipeline = false;
    int turn = 0;
    void *smx = nullptr;                // synth_voice_moogx (nv_part_moogx; NULL: none)
    struct GpuPend {
        int kind = 0;                   // 0 none (the first block), 1 done on the CPU, 2 on the GPU
        int slot = 0;
        bool snd = false;
        std::vector<float> L, R, SL, SR;
    } gpend;
    bool on_gpu = false;                // did the last block go to the GPU
    bool gpu_off = false;               // the panel's: the CPU for every block
    bool gpu_failed_said = false;
    double ms_setup = 0.0, ms_samples = 0.0;    // its two halves (live's GpuRenderer.ms_*)
    std::vector<long> gidx, gnon, gnoff;
    std::vector<float> gout;

    bool render_gpu(long long n0, long frames, float *L, float *R, float *SL, float *SR, long long blk)
    {
        long mg = 0;
        long nact = setup_gpu(n0, blk, gp.D, gp.C, gp.SB, SL != nullptr, mg);
        auto t1 = std::chrono::steady_clock::now();
        struct Ms {
            double &out;
            std::chrono::steady_clock::time_point t;
            ~Ms() { out = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t).count(); }
        } ms{ms_samples, t1};
        if (gp.cl) {
            gout.resize(4 * frames);
            if (nv_cl_samples(gp.cl, gp.D.p, gp.D.bytes(), gp.C.p, gp.C.bytes(), gp.SB.p, gp.SB.bytes(), (int)nact,
                              n0, (int)frames, SL ? 1 : 0, (int)mg, gout.data()) != 0)
                return false;
            for (long k = 0; k < frames; k++) {
                L[k] = gout[k];
                R[k] = gout[frames + k];
                if (SL) {
                    SL[k] = gout[2 * frames + k];
                    SR[k] = gout[3 * frames + k];
                }
            }
        } else {
            ((nv_vsamples_fn)gp.vs)((long)n0, (int)blk, (int)nact, gp.D.p, gp.C.p, gp.SB.p, L, R, SL, SR);
        }
        return true;
    }

    // the GPU block's setup (voice_block over every busy slot) into the
    // tables D, C, SB, grown as it asks; the busy slots' count, and *mg the
    // Moog's grid. ms_setup its time
    long setup_gpu(long long n0, long long blk, Table &D, Table &C, Table &SB, bool snd, long &mgo)
    {
        if (!D.size) {                      // (a second set made as the first: an empty table is no buffer)
            D.make(gp.D.n, gp.D.size);
            C.make(gp.C.n, gp.C.size);
            SB.make(gp.SB.n, gp.SB.size);
        }
        gidx.clear();
        for (long q = 0; q < S.cap; q++)
            if (S.busy[q])
                gidx.push_back(q);
        for (long q = S.cap; q < S.cap + S.tap_m; q++)
            gidx.push_back(q);              // (...and the taps' scratch rows)
        long nact = (long)gidx.size();
        if (nact > D.n)
            D.make(std::max(nact, 2 * D.n), D.size);
        long mg = (blk % 128 == 0 && blk / 128 <= 64) ? 128 : blk;     // moog_grid
        long kb0 = (long)(n0 / mg);
        gnon.resize(S.cap + S.tap_m);
        gnoff.resize(S.cap + S.tap_m);
        for (long q = 0; q < S.cap + S.tap_m; q++) {
            gnon[q] = (long)S.i8[0][q];
            gnoff[q] = (long)S.i8[1][q];
        }
        void *vb = gp.vb;
        bool damp = false, mx = false;
        for (long q : gidx) {
            damp = damp || S.dk[q] >= 0;
            mx = mx || (S.i4[I4_fx][q] >= 0 && S.mx_on[S.i4[I4_fx][q]]);
        }
        if (mx && gp.vbm && gp.vmd && gp.vmm) {
            // ...AND A TABLE WITH MOOG NOTE ROWS through the extensions' build
            vb = gp.vbm;
            ((void (*)(const float *))gp.vmm)(S.MX.data());
            if (damp)
                ((nv_vdamp_fn)gp.vmd)(S.dk.data(), S.dg.data(), DM.data(), DMO.data(), DMB.data(), DMN.data());
            else
                ((nv_vdamp_fn)gp.vmd)(nullptr, nullptr, nullptr, nullptr, nullptr, nullptr);
        } else if (damp && gp.vbd && gp.vds) {
            vb = gp.vbd;
            ((nv_vdamp_fn)gp.vds)(S.dk.data(), S.dg.data(), DM.data(), DMO.data(), DMB.data(), DMN.data());
        }
        const std::vector<float> *F4 = S.f4.data(), *F4N = S.f4n.data();
        int counts[2] = {0, 0};
        auto t0 = std::chrono::steady_clock::now();
        while (true) {
            int r = ((nv_vblock_fn)vb)(
                (long)n0, (int)blk, 1, (int)(S.cap + S.tap_m), S.f8[0].data(), S.f8[1].data(), S.f8[2].data(), F4[0].data(),
                F4[1].data(), F4[2].data(), gnon.data(), gnoff.data(), F4[3].data(), F4[4].data(), F4[5].data(),
                F4[6].data(), F4[7].data(), F4[8].data(), F4[9].data(), F4[10].data(), F4[11].data(),
                F4[12].data(), F4[13].data(), F4[14].data(), F4[15].data(), F4[16].data(), F4[17].data(),
                F4[18].data(), F4N[0].data(), F4N[1].data(), F4N[2].data(), F4[19].data(), F4[20].data(),
                F4[21].data(), F4N[3].data(), F4[22].data(), F4[23].data(), S.i4[0].data(), S.i4[1].data(),
                G.data(), Sx.data(), S.i4[2].data(), BRt.data(), BCt.data(), BLt.data(), S.i4[4].data(), FT.data(),
                KN.data(), 2, kb0, S.aLp.data(), S.aRp.data(), S.i4[5].data(), MPI.data(), MPC.data(), MPR.data(),
                MKI.data(), MPK.data(), S.f8[3].data(), S.f8[4].data(), S.f8[5].data(), sh[0], sh[1], sh[2], sh[3],
                nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, 0, nullptr, nullptr, nullptr, nullptr,
                nullptr, nullptr, 0, S.sw.data(), snd ? 1 : 0, gidx.data(), (int)nact, D.p, C.p,
                (int)C.n, SB.p, (int)SB.n, gp.nthr, counts, 1);
            if (r == 0)
                break;
            if (counts[0] > C.n)
                C.make(2L * counts[0], C.size);
            if (counts[1] > SB.n)
                SB.make(2L * counts[1], SB.size);
        }
        ms_setup = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        mgo = mg;
        return nact;
    }

    // THE PIPELINE'S BLOCK (GpuRenderer.render, _start, _finish): this one
    // started, the one before finished into L, R (SL, SR)
    void render(long long n0, long frames, float *L, float *R, float *SL, float *SR, void *sv, void *sx, void *sd,
                long long blk, double master_gain)
    {
        // THE MOOG ROWS under a moving filter (live's moog_filter_apply before
        // the render, _restore in its finally): their |H| for this render, the
        // panel's level back after it -- after knobs_advance has carried the
        // filtered end into aLp
        struct MoogFlt {
            Slab &S;
            ~MoogFlt() { S.moog_filter_restore(); }
        } moog_flt{S};
        S.moog_filter_apply();
        tap_block(n0, frames);                  // the insertion effect's copies (live's tap_fill)
        bus_block(n0, frames);                  // ...and a part's own bus (live's _bus_block)
        // LFO 2's level on the Moog rows, for this render (live's lfo2_amp_apply,
        // _restore in its finally, before the filter's)
        struct Lfo2Amp {
            Slab &S;
            ~Lfo2Amp() { S.lfo2_amp_restore(); }
        } lfo2_amp{S};
        S.lfo2_amp_apply();
        // the Moog's mod rows for this block, and its FM's anchors (Renderer.render's first)
        S.moog_pitch_block(n0, frames, rate, moog_pcells);
        S.moog_shape_block(n0, frames, rate, moog_srows);
        S.moog_fm_block();
        if (!pipeline || !gp.cl) {
            render_now(n0, frames, L, R, SL, SR, sv, sx, sd, blk, master_gain);
            shed_tick(n0 + frames);
            return;
        }
        GpuPend cur;
        cur.snd = SL != nullptr;
        long hi = -1, act = 0;
        for (long q = 0; q < S.cap; q++)
            if (S.busy[q]) {
                hi = q;
                act++;
            }
        bool g = hi >= 0 && gp.vb && !gpu_off && act >= gp.gpu_min && frames == blk && n0 % frames == 0 && !busp;
        if (g) {
            // set up in this turn's tables and launched, not waited for
            Table &D = turn ? gp.D2 : gp.D, &C = turn ? gp.C2 : gp.C, &SB = turn ? gp.SB2 : gp.SB;
            long mg = 0;
            long nact = setup_gpu(n0, blk, D, C, SB, cur.snd, mg);
            if (nv_cl_launch(gp.cl, turn, D.p, D.bytes(), C.p, C.bytes(), SB.p, SB.bytes(), (int)nact, n0,
                             (int)frames, cur.snd ? 1 : 0, (int)mg) == 0) {
                cur.kind = 2;
                cur.slot = turn;
                turn ^= 1;
                S.levels_advance();         // knobs_advance
                S.knobs_advance();
            } else {
                if (!gpu_failed_said) {     // (said once: a failed launch renders on the CPU, and costs it)
                    fprintf(stderr, "nvlive: a GPU launch failed (%ld slots): this block on the CPU\n", act);
                    gpu_failed_said = true;
                }
                g = false;
            }
        }
        if (!g) {
            // the CPU's, rendered now and held
            cur.kind = 1;
            cur.L.assign(frames, 0.0f);
            cur.R.assign(frames, 0.0f);
            if (cur.snd) {
                cur.SL.assign(frames, 0.0f);
                cur.SR.assign(frames, 0.0f);
            }
            render_now(n0, frames, cur.L.data(), cur.R.data(), cur.snd ? cur.SL.data() : nullptr,
                       cur.snd ? cur.SR.data() : nullptr, sv, sx, sd, blk, master_gain);
        }
        on_gpu = g;
        GpuPend prev = std::move(gpend);
        gpend = std::move(cur);
        // ...and the one before it, finished
        for (long k = 0; k < frames; k++) {
            L[k] = R[k] = 0.0f;
            if (SL)
                SL[k] = SR[k] = 0.0f;
        }
        if (prev.kind == 1) {
            for (long k = 0; k < frames; k++) {
                L[k] = prev.L[k];
                R[k] = prev.R[k];
                if (SL && prev.snd) {
                    SL[k] = prev.SL[k];
                    SR[k] = prev.SR[k];
                }
            }
        } else if (prev.kind == 2) {
            auto t1 = std::chrono::steady_clock::now();
            gout.resize(4 * frames);
            if (nv_cl_collect(gp.cl, prev.slot, gout.data()) == 0) {
                float gn = (float)master_gain;
                for (long k = 0; k < frames; k++) {
                    L[k] = gout[k] * gn;
                    R[k] = gout[frames + k] * gn;
                    L[k] = L[k] < -1.0f ? -1.0f : (L[k] > 1.0f ? 1.0f : L[k]);
                    R[k] = R[k] < -1.0f ? -1.0f : (R[k] > 1.0f ? 1.0f : R[k]);
                    if (SL && prev.snd) {
                        SL[k] = gout[2 * frames + k] * gn;
                        SR[k] = gout[3 * frames + k] * gn;
                    }
                }
            }
            ms_samples = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t1).count();
        }
        shed_tick(n0 + frames);
    }

    void render_now(long long n0, long frames, float *L, float *R, float *SL, float *SR, void *sv, void *sx,
                    void *sd, long long blk, double master_gain)
    {
        for (long k = 0; k < frames; k++) {
            L[k] = 0.0f;
            R[k] = 0.0f;
            if (SL) {
                SL[k] = 0.0f;
                SR[k] = 0.0f;
            }
        }
        // ...and after it, knobs_advance: each slot's level now is where the
        // next block's ramp starts (aLp, aRp)
        struct Advance {
            Slab &S;
            ~Advance() { S.levels_advance(); S.knobs_advance(); }
        } advance{S};
        long hi = -1;
        for (long q = 0; q < S.cap; q++)
            if (S.busy[q])
                hi = q;
        if (hi < 0 && !busp)
            return;                         // (nothing sounding, no bus to run on: silence)
        hi += 1;
        // THE GPU (live.GpuRenderer), when given one and the block has rows
        // enough for it (gpu_min); the CPU below otherwise -- and a block with
        // a bus on the CPU (its rows on the GPU: not yet here)
        long act = 0;
        for (long q = 0; q < hi; q++)
            act += S.busy[q] != 0;
        on_gpu = gp.vb && !gpu_off && act >= gp.gpu_min && frames == blk && n0 % frames == 0 && !busp;
        // A PART'S OWN BUS: its partials rendered apart from their copies in
        // the scratch rows, so the originals sit this block out
        std::vector<long long> bus_saved;
        if (busp) {
            bus_saved.resize(S.bus_hide.size());
            for (size_t q = 0; q < S.bus_hide.size(); q++) {
                bus_saved[q] = S.i8[0][S.bus_hide[q]];
                S.i8[0][S.bus_hide[q]] = IDLE;
            }
        }
        if (on_gpu && !render_gpu(n0, frames, L, R, SL, SR, blk))
            on_gpu = false;
        if (!on_gpu) {
        long kb0 = (long)(n0 / blk);                        // moog_grid(128) = 128
        long chunk = blk * std::max(1L, (long)(rate / blk));
        auto fast = [&](long q) {
            float lr = S.f4[6][q];
            return S.f4[9][q] <= 0 && S.f4[8][q] <= 0 && (float)(lr * (float)blk) > (float)(xdec_nepers * rate)
                   && S.i4[0][q] < 0 && S.i4[2][q] < 0 && S.dk[q] < 0 && S.i4[4][q] < 0;
        };
        // ONLY THE BUSY SLOTS (as the GPU's setup packs them): an idle one
        // adds nothing (the kernel adds its rows in order, a row out of its
        // window skipped), but gathering it costs ~40 columns -- and after a
        // thick passage a few voices can sit high on the slab: a coupled
        // harpsichord's chord, 16-64 slots near the top, gathered 40,000 deep,
        // ran 10-25 ms a block on the CPU
        // THE MOOG ROWS WHOSE NOTE HAS A ROW OF THE EXTENSIONS (synth_partials'
        // moogx_rows) through synth_voice_moogx, last
        auto mxq = [&](long q) { return smx && S.i4[I4_fx][q] >= 0 && S.mx_on[S.i4[I4_fx][q]]; };
        std::vector<long> xr, keep, dm, mxr;
        for (long q = 0; q < hi; q++)
            if (S.busy[q])
                (mxq(q) ? mxr : S.dk[q] >= 0 && sd ? dm : fast(q) ? xr : keep).push_back(q);
#define VOICE_ARGS L, R, (long)n0, frames, (int)blk, 1, (int)n, gd(S.f8[0], 0), gd(S.f8[1], 1), gd(S.f8[2], 2), \
    gf(F4[0]), gf(F4[1]), gf(F4[2]), gl(S.i8[0], 0), gl(S.i8[1], 1), gf(F4[3]), gf(F4[4]), gf(F4[5]), gf(F4[6]), \
    gf(F4[7]), gf(F4[8]), gf(F4[9]), gf(F4[10]), gf(F4[11]), gf(F4[12]), gf(F4[13]), gf(F4[14]), gf(F4[15]), \
    gf(F4[16]), gf(F4[17]), gf(F4[18]), gf(F4N[0]), gf(F4N[1]), gf(F4N[2]), gf(F4[19]), gf(F4[20]), gf(F4[21]), \
    gf(F4N[3]), gf(F4[22]), gf(F4[23]), gi(S.i4[0]), gi(S.i4[1]), G.data(), Sx.data(), gi(S.i4[2]), BRt.data(), \
    BCt.data(), BLt.data(), gi(S.i4[4]), FT.data(), KN.data(), 2, kb0, gf(S.aLp), gf(S.aRp), gi(S.i4[5]), \
    MPI.data(), MPC.data(), MPR.data(), MKI.data(), MPK.data(), gd(S.f8[3], 3), gd(S.f8[4], 4), gd(S.f8[5], 5), \
    sh[0], sh[1], sh[2], sh[3], chunk, SL ? gf(S.sw) : nullptr, SL, SR
        auto call = [&](void *fn, const long *rows, long n, bool whole, bool damp) {
            if (!n)
                return;
            // columns gathered (a set of rows), or the slab's own (the whole range)
            std::vector<double> d[6];
            std::vector<float> f[32];
            std::vector<long> l[2];
            std::vector<int> i[6];
            auto gd = [&](const std::vector<double> &c, int k) {
                if (whole) return c.data();
                d[k].resize(n); for (long q = 0; q < n; q++) d[k][q] = c[rows[q]]; return (const double *)d[k].data();
            };
            int fk = 0;
            auto gf = [&](const std::vector<float> &c) {
                if (whole) return c.data();
                std::vector<float> &v = f[fk++];
                v.resize(n); for (long q = 0; q < n; q++) v[q] = c[rows[q]]; return (const float *)v.data();
            };
            auto gl = [&](const std::vector<long long> &c, int k) {
                l[k].resize(n); for (long q = 0; q < n; q++) l[k][q] = (long)c[whole ? q : rows[q]];
                return (const long *)l[k].data();
            };
            int ik = 0;
            auto gi = [&](const std::vector<int32_t> &c) {
                if (whole) return (const int *)c.data();
                std::vector<int> &v = i[ik++];
                v.resize(n); for (long q = 0; q < n; q++) v[q] = c[rows[q]]; return (const int *)v.data();
            };
            const std::vector<float> *F4 = S.f4.data(), *F4N = S.f4n.data();
            if (damp) {
                std::vector<int> &dkr = i[ik++];
                dkr.resize(n); for (long q = 0; q < n; q++) dkr[q] = S.dk[rows[q]];
                std::vector<float> &dgr = f[fk++];
                dgr.resize(n); for (long q = 0; q < n; q++) dgr[q] = S.dg[rows[q]];
                if (fn == smx)          // synth_voice_moogx: synth_voice_damp's, then the note rows
                    ((nv_moogx_fn)fn)(VOICE_ARGS, dkr.data(), dgr.data(), DM.data(), DMO.data(), DMB.data(),
                                      DMN.data(), S.MX.data());
                // synth_voice_damp: synth_voice's arguments, then the tracks
                else
                    ((nv_damp_fn)fn)(VOICE_ARGS, dkr.data(), dgr.data(), DM.data(), DMO.data(), DMB.data(), DMN.data());
            } else {
                ((nv_voice_fn)fn)(VOICE_ARGS);
            }
        };
        if (!mxr.empty()) {
            call(sv, keep.data(), (long)keep.size(), false, false);
            call(sx, xr.data(), (long)xr.size(), false, false);
            call(sd, dm.data(), (long)dm.size(), false, true);
            call(smx, mxr.data(), (long)mxr.size(), false, true);
        } else if (!dm.empty()) {
            call(sv, keep.data(), (long)keep.size(), false, false);
            call(sx, xr.data(), (long)xr.size(), false, false);
            call(sd, dm.data(), (long)dm.size(), false, true);
        } else if (!xr.empty()) {
            call(sv, keep.data(), (long)keep.size(), false, false);
            call(sx, xr.data(), (long)xr.size(), false, false);
        } else if (2 * (long)keep.size() < hi) {
            call(sv, keep.data(), (long)keep.size(), false, false);    // (sparse: the busy ones gathered)
        } else {
            call(sv, nullptr, hi, true, false);
        }
        if (S.tap_m) {                      // the taps' scratch rows (Slab.tap_fill), after
            std::vector<long> xr2, keep2, dm2, mx2;
            for (long q = S.cap; q < S.cap + S.tap_m; q++)
                (mxq(q) ? mx2 : S.dk[q] >= 0 && sd ? dm2 : fast(q) ? xr2 : keep2).push_back(q);
            if (!mx2.empty()) {
                call(sv, keep2.data(), (long)keep2.size(), false, false);
                call(sx, xr2.data(), (long)xr2.size(), false, false);
                call(sd, dm2.data(), (long)dm2.size(), false, true);
                call(smx, mx2.data(), (long)mx2.size(), false, true);
            } else if (!dm2.empty()) {
                call(sv, keep2.data(), (long)keep2.size(), false, false);
                call(sx, xr2.data(), (long)xr2.size(), false, false);
                call(sd, dm2.data(), (long)dm2.size(), false, true);
            } else {
                call(sv, keep2.data(), (long)keep2.size(), false, false);
                call(sx, xr2.data(), (long)xr2.size(), false, false);
            }
        }
        if (busp) {
            for (size_t q = 0; q < S.bus_hide.size(); q++)
                S.i8[0][S.bus_hide[q]] = bus_saved[q];
            // the bus rows apart, through the processor, added back
            std::vector<float> BL(frames, 0.0f), BR(frames, 0.0f), BSL(frames, 0.0f), BSR(frames, 0.0f);
            if (S.bus_m) {
                float *L0 = L, *R0 = R, *SL0 = SL, *SR0 = SR;
                L = BL.data();
                R = BR.data();
                SL = SL0 ? BSL.data() : nullptr;
                SR = SL0 ? BSR.data() : nullptr;
                std::vector<long> xr3, keep3, dm3, mx3;
                const long c1 = S.cap + S.tap_m;
                for (long q = c1; q < c1 + S.bus_m; q++)
                    (mxq(q) ? mx3 : S.dk[q] >= 0 && sd ? dm3 : fast(q) ? xr3 : keep3).push_back(q);
                call(sv, keep3.data(), (long)keep3.size(), false, false);
                call(sx, xr3.data(), (long)xr3.size(), false, false);
                if (!dm3.empty())
                    call(sd, dm3.data(), (long)dm3.size(), false, true);
                call(smx, mx3.data(), (long)mx3.size(), false, true);
                L = L0;
                R = R0;
                SL = SL0;
                SR = SR0;
            }
            std::vector<float> oL(frames), oR(frames);
            nv_livebus_process(busp, BL.data(), BR.data(), master_gain, oL.data(), oR.data());
            for (long k = 0; k < frames; k++) {
                L[k] = L[k] + oL[k];
                R[k] = R[k] + oR[k];
            }
            if (SL) {                       // (the send: through a processor of its own, the effect's output heard)
                if (!busps)
                    busps = nv_livebus_new(bus_fc, rate, (int)frames, bus_cn, bus_cp, bus_cf);
                if (busps) {
                    nv_livebus_process(busps, BSL.data(), BSR.data(), master_gain, oL.data(), oR.data());
                    for (long k = 0; k < frames; k++) {
                        SL[k] = SL[k] + oL[k];
                        SR[k] = SR[k] + oR[k];
                    }
                }
            }
        }
#undef VOICE_ARGS
        }
        // the master gain (float32, as numpy multiplies by a Python float) and
        // the clip; the room's send scaled, not clipped
        float g = (float)master_gain;
        for (long k = 0; k < frames; k++) {
            L[k] *= g;
            R[k] *= g;
            L[k] = L[k] < -1.0f ? -1.0f : (L[k] > 1.0f ? 1.0f : L[k]);
            R[k] = R[k] < -1.0f ? -1.0f : (R[k] > 1.0f ? 1.0f : R[k]);
            if (SL) {
                SL[k] *= g;
                SR[k] *= g;
            }
        }
    }

    // AFTER THE RENDER (live's callback): the master volume (live's Master
    // Volume, 1.0: no ramp), the room on the send -- the kernel's second
    // output when the channels' CC91s differ, else the dry mix times their
    // one distance -- and the soft limiter's knee
    std::unique_ptr<Room> room;
    // A ROOM SWITCHED TO (live._room_install): the old tail crossfaded out
    // over room_xf_n blocks (ROOM_XFADE_S), the new one in; the old freed off
    // the audio thread (room_trash: the builder's, live's _room_trash)
    std::unique_ptr<Room> room_prev;
    int room_xf = 0, room_xf_n = 1;
    std::vector<std::unique_ptr<Room>> room_trash;
    std::mutex room_mu;                             // (room_trash: the audio thread's and the builder's)
    void room_install(Room *r, long long frames)
    {
        std::lock_guard<std::mutex> lk(room_mu);
        if (room_prev)
            room_trash.push_back(std::move(room_prev));
        room_prev = std::move(room);
        room.reset(r);
        room_xf_n = std::max(1, (int)(0.15 * rate / (double)frames));
        room_xf = room_xf_n;
    }
    double thresh = 0.70;                           // live.thresh
    std::vector<float> oSL, oSR, oA, oB, oWL, oWR;

    // Live.limit: a soft knee above thresh (libm's tanhf, as live's now)
    void limit(float *x, long n) const
    {
        float t = (float)thresh, k = (float)(1.0 - thresh);
        for (long i = 0; i < n; i++) {
            float a = fabsf(x[i]);
            if (a > t)
                x[i] = (x[i] > 0.0f ? 1.0f : -1.0f) * (t + k * tanhf((a - t) / k));
        }
    }

    void output(long long n0, long frames, float *L, float *R, void *sv, void *sx, void *sd, long long blk,
                double master_gain)
    {
        bool uniform = n0 >= S.odd_until;      // (a voice standing apart: the bus runs)
        for (int c = 1; c < 256 && uniform; c++)
            uniform = S.send[c] == S.send[0];
        const bool any_room = (room || room_prev) && room_on;
        bool snd = any_room && !uniform;
        oSL.assign(frames, 0.0f);
        oSR.assign(frames, 0.0f);
        render(n0, frames, L, R, snd ? oSL.data() : nullptr, snd ? oSR.data() : nullptr, sv, sx, sd, blk,
               master_gain);
        // THE MASTER VOLUME (live.master_gain): at its value, or ramping to it
        double want = master_vol, now = mv_now;
        if (want == now) {
            float w = (float)want;
            if (want != 1.0)
                for (long k = 0; k < frames; k++) {
                    L[k] = L[k] * w;
                    R[k] = R[k] * w;
                }
            if (snd)                                // (the send takes exactly this)
                for (long k = 0; k < frames; k++) {
                    oSL[k] = oSL[k] * w;
                    oSR[k] = oSR[k] * w;
                }
        } else {
            if (!(want == mv_target)) {             // the step fixed when the target changes
                mv_target = want;
                long ramp = std::max(1L, (long)(0.005 * rate));        // blockrender.MASTER_RAMP_S
                mv_step = (want - now) / (double)ramp;
            }
            mv_g.resize(frames);
            double gk = now;
            for (long k = 0; k < frames; k++) {
                gk = now + mv_step * (double)(k + 1);
                gk = mv_step > 0 ? std::min(gk, want) : std::max(gk, want);
                mv_g[k] = (float)gk;
            }
            mv_now = gk;
            for (long k = 0; k < frames; k++) {
                L[k] = L[k] * mv_g[k];
                R[k] = R[k] * mv_g[k];
                if (snd) {
                    oSL[k] = oSL[k] * mv_g[k];
                    oSR[k] = oSR[k] * mv_g[k];
                }
            }
        }
        if (any_room) {
            const float *sl = L, *sr = R;
            if (snd) {
                sl = oSL.data();                    // (times the master volume's 1.0)
                sr = oSR.data();
            } else if (S.send[0] != 1.0) {
                float u = (float)S.send[0];
                oA.resize(frames);
                oB.resize(frames);
                for (long k = 0; k < frames; k++) {
                    oA[k] = L[k] * u;
                    oB[k] = R[k] * u;
                }
                sl = oA.data();
                sr = oB.data();
            }
            // live._room_add: the new tail, faded in while a switch's
            // crossfade runs, and the old one faded out -- float32 as numpy's
            oWL.assign(frames, 0.0f);
            oWR.assign(frames, 0.0f);
            oA.resize(frames);
            oB.resize(frames);
            const float xf = (float)room_xf, xn = (float)room_xf_n;
            if (room) {
                room->process(sl, sr, oA.data(), oB.data());
                if (room_xf > 0)
                    for (long k = 0; k < frames; k++) {
                        const float g = 1.0f - (xf - (float)k / (float)frames) / xn;
                        oA[k] = oA[k] * g;
                        oB[k] = oB[k] * g;
                    }
                for (long k = 0; k < frames; k++) {
                    oWL[k] = oWL[k] + oA[k];
                    oWR[k] = oWR[k] + oB[k];
                }
            }
            if (room_prev) {
                room_prev->process(sl, sr, oA.data(), oB.data());
                for (long k = 0; k < frames; k++) {
                    const float g = (xf - (float)k / (float)frames) / xn;
                    oWL[k] = oWL[k] + oA[k] * g;
                    oWR[k] = oWR[k] + oB[k] * g;
                }
                if (--room_xf <= 0) {
                    std::lock_guard<std::mutex> lk(room_mu);
                    room_trash.push_back(std::move(room_prev));
                }
            } else if (room_xf > 0) {
                room_xf--;
            }
            for (long k = 0; k < frames; k++) {
                L[k] = L[k] + oWL[k];
                R[k] = R[k] + oWR[k];
            }
        }
        limit(L, frames);
        limit(R, frames);
    }

    // THE BUDGET GOVERNOR (live's callback, after its render; Slab.shed):
    // each block's time against its slot, the last four kept; when their
    // median-ish (the second smallest) is over 95% of the slot -- so one
    // chord's strike is not a reason -- the highest tenth of the partials
    // still sounding end over SHED_FADE: the top of each note's spectrum
    // first, where its partials are quietest and the rest mask them. A shed
    // slot keeps its key and is reaped with its note; only its sound stops.
    // Ties in frequency (a note and its forced register rows share one) go
    // by slot, where numpy's argpartition picks as it partitions.
    static constexpr double SHED_FADE = 0.005;
    double ms_hist[4];
    int ms_n = 0;
    long partials_shed = 0;

    long shed(long long n, double frac)
    {
        std::vector<long> idx;
        for (long q = 0; q < S.cap; q++) {
            long long off = S.i8[1][q];
            if (S.busy[q] && S.i8[0][q] <= n && (off == IDLE || off > n))
                idx.push_back(q);
        }
        long k = (long)(frac * (double)idx.size());
        if (k < 1)
            return 0;
        const std::vector<float> &nf = S.f4[F4_nf];
        std::partial_sort(idx.begin(), idx.begin() + k, idx.end(), [&](long a, long b) {
            return nf[a] > nf[b] || (nf[a] == nf[b] && a < b);
        });
        float fade = (float)(SHED_FADE * rate);
        std::vector<long> qm;
        for (long i = 0; i < k; i++) {
            long q = idx[i];
            if (S.i4[I4_fx][q] >= 0) {
                qm.push_back(q);
                continue;
            }
            S.i8[1][q] = std::min(S.i8[1][q], n);
            S.f4[F4_re][q] = std::min(S.f4[F4_re][q], fade);
        }
        if (!qm.empty()) {
            // A MOOG ROW's envelope is its note's (the FT row), not its own,
            // so it is faded by its level -- every baseline to zero, so no
            // panel or aftertouch brings it back, the kernel ramping it down
            // over the next block -- and out of the render once that has
            // (shed_tick)
            std::sort(qm.begin(), qm.end());
            for (long q : qm) {
                S.aL0[q] = S.aR0[q] = 0.0f;
                S.f4[F4_aL][q] = S.f4[F4_aR][q] = 0.0f;
                S.tr_aL[q] = S.tr_aR[q] = 0.0f;
                S.ls_aL[q] = S.ls_aR[q] = 0.0f;
                S.cv_aL[q] = S.cv_aR[q] = 0.0f;
                S.fl_aL[q] = S.fl_aR[q] = 0.0f;
                S.mo_uL[q] = S.mo_uR[q] = 0.0f;
            }
            shed_mo.emplace_back(n + 2 * cur_blk, qm);     // (live sets blockrender.BLK to its block)
        }
        return k;
    }

    // THE METRONOME (live's set_metronome, _metro_tick): Standard's click (33)
    // on every beat and its bell (34, which strikes the click with it) every
    // ring beats, from a drum patch of its own that claims no key (hidden),
    // struck here at each beat's own sample; starting again begins on beat
    // one, a new tempo keeps the next beat and spaces the rest
    int metro_pi = -1, metro_ring = 0;
    double metro_bpm = 0.0, metro_next = 0.0;
    bool metro_has = false;                     // (metro_next is None: the next block's start, beat one)
    long metro_beat = 0;
    void metronome(int pi, double bpm, int ring)
    {
        if (pi >= 0)
            metro_pi = pi;
        const bool was = metro_bpm > 0.0;
        metro_ring = std::max(0, ring);
        metro_bpm = std::max(0.0, bpm);
        if (metro_bpm > 0.0 && !was) {
            metro_has = false;
            metro_beat = 0;
        }
    }
    void metro_tick(long long n0, long long frames)
    {
        const double period = rate * 60.0 / metro_bpm;
        if (!metro_has || metro_next < (double)n0 - period) {
            metro_next = (double)n0;
            metro_beat = 0;
            metro_has = true;
        }
        const long long end = n0 + frames;
        while (metro_next < (double)end) {
            const long long at = (long long)nearbyint(metro_next);
            const bool bell = metro_ring > 0 && metro_beat % metro_ring == 0;
            {
                Force f(*this, metro_pi);           // (live's _note_on on its own part)
                cut_on(9, bell ? 34 : 33, 100, at, false);
            }
            metro_next += period;
            metro_beat++;
        }
    }

    // live.Slab.shed_tick: the shed Moog rows whose fade has run, out of the
    // render (their slots go with their notes, as every shed slot)
    std::vector<std::pair<long long, std::vector<long>>> shed_mo;
    void shed_tick(long long n)
    {
        if (shed_mo.empty() || shed_mo[0].first > n)
            return;
        std::vector<std::pair<long long, std::vector<long>>> keep;
        for (auto &e : shed_mo) {
            if (e.first > n) {
                keep.push_back(e);
                continue;
            }
            for (long q : e.second)
                if (S.busy[q])
                    S.i8[0][q] = IDLE;
        }
        shed_mo.swap(keep);
    }

    // a block took ms of budget_ms; the next starts at n
    long govern(double ms, double budget_ms, long long n)
    {
        // THE INSERTION EFFECT's COPIES ARE THE LOAD THAT CAN GIVE (live's
        // callback): over 85% of the slot, the next block writes 30% less of
        // them, counted by cost; back an eighth at a time once four blocks
        // running are under 70%
        if (S.tap_m || S.tap_cap < S.tap_ucap) {
            bool calm = ms < 0.7 * budget_ms;
            for (int i = 0; i < ms_n; i++)
                calm = calm && ms_hist[i] < 0.7 * budget_ms;
            if (ms > 0.85 * budget_ms && S.tap_m) {
                S.tap_cap = (long long)((double)std::min(S.tap_cap, S.tap_u) * 0.7);
                tap_shed++;
            } else if (calm && S.tap_cap < S.tap_ucap) {
                S.tap_cap = std::min(S.tap_ucap, S.tap_cap + std::max(256LL, S.tap_cap / 8));
            }
        }
        if (ms_n == 4) {
            for (int i = 0; i < 3; i++)
                ms_hist[i] = ms_hist[i + 1];
            ms_hist[3] = ms;
        } else {
            ms_hist[ms_n++] = ms;
        }
        if (ms_n < 4)
            return 0;
        double o[4] = {ms_hist[0], ms_hist[1], ms_hist[2], ms_hist[3]};
        std::sort(o, o + 4);
        if (S.tap_m || !(o[1] > 0.95 * budget_ms))     // (...the notes' own partials only with no copies left)
            return 0;
        long k = shed(n, 0.1);
        if (k) {
            partials_shed += k;
            ms_n = 0;
        }
        return k;
    }

    // live's callback for one block: its events, the sweep, the reap
    // random.expovariate, randrange (CPython 3.12's: getrandbits' top bits, rejected past n)
    double tex_expo(double lambd) { return -log(1.0 - pyr_random(&tex_rng)) / lambd; }
    long tex_below(long n)
    {
        int k = 0;
        while ((1L << k) <= n)
            k++;
        uint32_t r = pyr_genrand(&tex_rng) >> (32 - k);
        while ((long)r >= n)
            r = pyr_genrand(&tex_rng) >> (32 - k);
        return (long)r;
    }

    // live._tex_tick: a held texture's grains past its template -- a drop from
    // its pool at each Poisson instant in this block, at its own sample, under
    // a key of its own: a one-shot that decays on its own rows' ends
    // A HELD ROLL's strokes falling in this block (live._roll_tick): each hit
    // the template's one hit at its own sample, its level the step's over the
    // template's, squared; past the key-up, the closing stroke, and it is done
    void roll_tick(long long n0, long long blk)
    {
        const long long end = n0 + blk;
        for (size_t i = 0; i < roll_gen.size();) {
            RollGen &g = roll_gen[i];
            const nv::live::Template &hit = g.T->roll_hit[0];
            auto strike = [&](const std::vector<std::pair<double, double>> &hs) {
                for (const auto &h : hs) {
                    g.n++;
                    Key k(std::get<0>(g.key), std::get<1>(g.key), std::get<2>(g.key), ROLL0 + g.n);
                    if (!S.stamp_t(hit, k, g.at + (long long)nearbyint(h.first * rate),
                                   g.scale * pow(h.second / g.T->roll_lv0, 2.0), std::get<1>(g.key), rate))
                        dropped++;
                }
            };
            while ((double)g.at + g.t * rate < (double)end && (std::isnan(g.close) || g.t < g.close))
                strike(roll_next(g));
            if (!std::isnan(g.close) && (double)g.at + g.close * rate < (double)end) {
                strike(roll_close(g, g.close));
                roll_gen.erase(roll_gen.begin() + i);
                continue;
            }
            i++;
        }
    }

    void tex_tick(long long n0, long long blk)
    {
        const long long end = n0 + blk;
        for (TexGen &g : tex_gen) {
            while (g.nxt < (double)end) {
                const nv::live::Template &sub = g.T->gpool[tex_below((long)g.T->gpool.size())];
                tex_n++;
                Key k(std::get<0>(g.key), std::get<1>(g.key), std::get<2>(g.key), GRAIN0 + tex_n);
                if (!S.stamp_t(sub, k, std::max((long long)g.nxt, n0), g.scale, std::get<1>(g.key), rate))
                    dropped++;
                g.nxt += tex_expo(g.T->grate) * rate;
            }
        }
    }

    void block(long long n0, long long blk)
    {
        cur_blk = blk;
        if (!wind_st.empty() || !wind_spent.empty())    // the organs' chests, before the block's events (live's callback)
            wind_block(n0, blk);
        if (!cutting.empty())
            cut_go(n0);                         // the flicks due give way to their notes (live._cut_go)
        if (!amp_retired.empty())
            amp_retire(n0);
        std::vector<Ev> evs;
        evs.swap(events);
        std::vector<std::vector<uint8_t>> sxs;
        sxs.swap(sx);
        for (const Ev &e : evs) {
            // (a part on the insertion effect: a controller that is one of
            // its sources -- CC1-95, aftertouch, the bend -- its value, first:
            // live._efx_control)
            if (efx && e.type >= 2 && e.type <= 4 && nv_efx_live_on(efx, e.ch)) {
                if (e.type == 2 && e.a >= 1 && e.a <= 95)
                    nv_efx_live_source(efx, (double)n0 / rate, e.a, e.b);
                else if (e.type == 3)
                    nv_efx_live_source(efx, (double)n0 / rate, 96, e.a);        // (gsefx.SRC_CAF)
                else if (e.type == 4)
                    nv_efx_live_source(efx, (double)n0 / rate, 97, (e.a + 8192) >> 7);  // (gsefx.SRC_BEND)
            }
            if (e.type == 6) {
                if (e.a >= 0 && e.a < (int)sxs.size())
                    sysex(sxs[e.a], n0);
            } else if (e.type == 0)
                note_on(e.ch, e.a, e.b, n0);
            else if (e.type == 1)
                note_off(e.ch, e.a, n0);
            else if (e.type == 3)
                aftertouch(e.ch, e.a, n0);
            else if (e.type == 7)
                polytouch(e.ch, e.a, e.b);
            else if (e.type == 4)
                pitchwheel(e.ch, e.a, n0);
            else
                control(e.ch, e.a, e.b, n0);
        }
        if (!posts.empty())                     // the panel's posts, in their order (live.post's)
            run_posts(n0);
        if (reg_on && (!reg_pend.empty() || !reg_out.empty() || reg_live || !reg_retire.empty()
                       || reg_ndone.load() > 0))
            reg_pump(n0);
        if (!tex_gen.empty())
            tex_tick(n0, blk);                  // a held texture's grains (live's _tex_tick)
        if (!roll_gen.empty())
            roll_tick(n0, blk);                 // a held roll's strokes (live's _roll_tick)
        if (metro_bpm > 0.0 && metro_pi >= 0)
            metro_tick(n0, blk);                // the metronome's beats (live's _metro_tick)
        if (!moog_glide.empty())
            moog_tick(n0);                      // the Moog's knobs gliding (live's _moog_tick)
        if (!open_ring.empty())
            open_ring_tick(n0);                 // the open strings' caps (live's _open_ring_tick)
        lfo2_tick(n0, blk);                     // each Moog part's LFO 2 (live's _lfo2_tick)
        if (!amp_dirty.empty() || amp_has_out || !amp_fine_results.empty() || amp_async || !amp_chg.empty()
            || !S.rel_log.empty())
            amp_pump(n0);                       // the valve (live's _amp_pump)
        std::vector<Key> sw;
        for (auto &kv : S.live) {
            std::pair<int, int> ck((int)std::get<1>(kv.first), (int)std::get<2>(kv.first));
            auto sq = sost.find(ck.first);
            if (!down.count(ck) && !pedalled.count(ck) && !S.oneshot.count(kv.first)
                && !(sq != sost.end() && sq->second.count(ck.second)) && std::get<3>(kv.first) != AMPK
                && std::get<3>(kv.first) != DRONEK
                && std::get<3>(kv.first) < AMP_OLD0 && std::get<3>(kv.first) > MFK0
                && !siren_of(std::get<0>(kv.first), ck.first, ck.second)
                && !open_ring.count(std::make_tuple((long long)std::get<0>(kv.first), ck.first, ck.second))
                && std::none_of(cutting.begin(), cutting.end(), [&](const Cut &c) {
                       return c.pid == std::get<0>(kv.first) && c.ch == ck.first && c.cnote == ck.second;
                   }))
                sw.push_back(kv.first);         // (not a valve's products, an old tone's, a repeat's, a flick: not a note)
        }
        for (auto &k : sw)
            S.release(k, n0);
        if (!drone_quiet.empty())
            drone_reap(n0);                     // the bag let down (live's _drone_reap, after the sweep)
        damp_block(n0, blk);
        if (!mf_groups.empty())
            mf104_reap();
        if (!siren_st.empty() || !siren_retire.empty())
            siren_block(n0, blk);               // the sirens' rotors (live's _siren_block, before the reap)
        S.reap(n0, blk);
        if (!scan_row.empty())                  // the scanners' band rows (live's _scanner_block)
            scanner_block(n0, blk);
        tremolo_block(n0);                      // (live's swing, after the reap)
        leslie_block(n0, blk);                  // ...then the rotors'
        if ((efx && nv_efx_live_parts(efx)) || !tone_fx.empty() || S.tap_m)
            efx_rotary_sync();                  // (the Rotary type's rotors: live._efx_rotary_sync)
        filter_block(n0, blk);                  // ...then the moving filters, on the levels they left
    }
};

// THE ROUTES (live.Route, and Live.on_midi's pass over them): one hardware
// control made to drive another, ahead of the part. A message is (type, ch,
// a, b): 0 note-on (a key, b velocity), 1 note-off, 2 control change (a
// number, b value), 3 channel aftertouch (a), 4 the pitch wheel (a,
// -8192..8191). A source is a CC, the wheel's up, down or both halves,
// channel pressure, or a key; a destination one of live.CONTROLS -- a CC,
// or BEND, PRESSURE, MONO -- and the transform follows from the two:
//   the wheel onto a switch    held while pushed: down past PW_FIRE of its
//                              half, up under PW_REARM
//   a CC onto a switch         64 and above is down
//   anything onto a CC         its travel scaled 0-127
//   a CC onto the wheel        0-127 onto -8192..8191, centred at 64
//   a key onto a switch        held while down, or each press toggles (latch);
//                              held as the sustain pedal, its channel's
//                              aftertouch while it is down is 127 - pressure
//   a key onto anything else   its velocity while held, and on release the
//                              value the control had before
// A route REPLACES its source unless it keeps it; the messages that pass are
// what the last value of each control is kept from (live.seen), which a key
// puts back when it comes up.
enum { DST_BEND = -1, DST_PRESSURE = -2, DST_MONO = -3 };
enum { SRC_CC = 0, SRC_BEND = 1, SRC_PRESSURE = 2, SRC_NOTE = 3 };
enum { K_SWITCH = 0, K_CONT = 1, K_BEND = 2, K_PRESSURE = 3 };
static const double PW_FIRE = 0.50, PW_REARM = 0.20;    // live's

struct Msg {
    int type, ch, a, b;
};

// live.CONTROLS: (key, kind, default); a key not here is no destination
static bool control_spec(int key, int *kind, int *dflt)
{
    static const int T[][3] = {{64, K_SWITCH, 0}, {66, K_SWITCH, 0}, {67, K_SWITCH, 0}, {65, K_SWITCH, 0},
                               {DST_MONO, K_SWITCH, 0}, {1, K_CONT, 0}, {11, K_CONT, 127}, {7, K_CONT, 100},
                               {10, K_CONT, 64}, {5, K_CONT, 0}, {93, K_CONT, 0}, {94, K_CONT, 0},
                               {74, K_CONT, 64}, {71, K_CONT, 64}, {73, K_CONT, 64}, {75, K_CONT, 64},
                               {72, K_CONT, 64}, {76, K_CONT, 64}, {77, K_CONT, 64}, {78, K_CONT, 64},
                               {DST_BEND, K_BEND, 0}, {DST_PRESSURE, K_PRESSURE, 0}};
    for (auto &r : T)
        if (r[0] == key) {
            *kind = r[1];
            *dflt = r[2];
            return true;
        }
    return false;
}

// live.control_message: the message one catalogue control sends at value
static Msg control_message(int key, long value, int ch)
{
    auto clamp = [](long v, long lo, long hi) { return v < lo ? lo : v > hi ? hi : v; };
    if (key == DST_BEND)
        return Msg{4, ch, (int)clamp(value, -8192, 8191), 0};
    if (key == DST_PRESSURE)
        return Msg{3, ch, (int)clamp(value, 0, 127), 0};
    if (key == DST_MONO)
        return value >= 64 ? Msg{2, ch, 126, 1} : Msg{2, ch, 127, 0};
    return Msg{2, ch, key, (int)clamp(value, 0, 127)};
}

static long pyround(double x) { return (long)nearbyint(x); }    // round(): to even

struct Route {
    int src, arg, dst;          // arg: the CC, the key, or the wheel's half (0 up, 1 down, 2 both)
    bool keep = false, latch = false, press = true;
    int channel = -1;           // -1 every channel
    bool down[16] = {}, held[16] = {};
    std::map<int, int> prior;   // channel -> the value before the key went down

    static bool is_on(const Msg &m) { return m.type == 0 && m.b > 0; }

    bool pressing(int ch) const
    {
        return press && !latch && dst == 64 && held[ch];
    }

    bool matches(const Msg &m) const
    {
        if (channel >= 0 && m.ch != channel)
            return false;
        if (src == SRC_CC)
            return m.type == 2 && m.a == arg;
        if (src == SRC_BEND)
            return m.type == 4;
        if (src == SRC_PRESSURE)
            return m.type == 3;
        if (m.type == 3)
            return pressing(m.ch);
        if ((m.type != 0 && m.type != 1) || m.a != arg)
            return false;
        // a release only if this route took the press
        return is_on(m) || held[m.ch];
    }

    double level(const Msg &m) const
    {
        if (src == SRC_BEND) {
            int p = m.a;
            if (arg == 0)
                return std::max(0, p) / 8191.0;
            if (arg == 1)
                return std::max(0, -p) / 8192.0;
            return abs(p) / 8192.0;
        }
        return (m.type == 3 ? m.a : m.b) / 127.0;
    }

    void rewrite(const Msg &m, const std::map<std::pair<int, int>, int> &seen, std::vector<Msg> &out)
    {
        int kind, dflt;
        if (!control_spec(dst, &kind, &dflt))
            return;
        int ch = m.ch;
        if (src == SRC_NOTE) {
            key(m, ch, kind, dflt, seen, out);
            return;
        }
        double x = level(m);
        if (kind == K_SWITCH) {
            bool was = down[ch], now;
            if (src == SRC_BEND)
                now = !was ? x >= PW_FIRE : x > PW_REARM;
            else
                now = x >= 64.0 / 127.0;
            if (now == was)
                return;                         // a pedal is sent on a change, not a stream
            down[ch] = now;
            out.push_back(control_message(dst, now ? 127 : 0, ch));
            return;
        }
        if (kind == K_BEND) {
            if (src == SRC_BEND) {
                out.push_back(control_message(DST_BEND, m.a, ch));
                return;
            }
            // each half on its own scale: 64 centre, 0 full down, 127 full up
            double v = x * 127.0;
            double p = v >= 64.0 ? (v - 64.0) / 63.0 * 8191.0 : (v - 64.0) / 64.0 * 8192.0;
            out.push_back(control_message(DST_BEND, pyround(p), ch));
            return;
        }
        out.push_back(control_message(dst, pyround(x * 127.0), ch));
    }

    void key(const Msg &m, int ch, int kind, int dflt, const std::map<std::pair<int, int>, int> &seen,
             std::vector<Msg> &out)
    {
        if (m.type == 3) {
            // pushed into while held: the dampers lowered (Route.press)
            out.push_back(control_message(dst, 127 - m.a, ch));
            return;
        }
        bool on = is_on(m);
        held[ch] = on;
        if (kind == K_SWITCH) {
            bool was = down[ch], now;
            if (latch) {
                if (!on)
                    return;
                now = !was;
            } else {
                now = on;
                if (now == was)
                    return;
            }
            down[ch] = now;
            out.push_back(control_message(dst, now ? 127 : 0, ch));
            return;
        }
        if (on) {
            if (!prior.count(ch)) {
                auto it = seen.find(std::make_pair(ch, dst));
                prior[ch] = it != seen.end() ? it->second : dflt;
            }
            int v = m.b;
            out.push_back(control_message(dst, kind == K_BEND ? pyround(v / 127.0 * 8191) : v, ch));
            return;
        }
        auto it = prior.find(ch);
        if (it == prior.end())
            return;
        int pv = it->second;
        prior.erase(it);
        out.push_back(control_message(dst, pv, ch));
    }
};

struct Router {
    std::vector<Route> routes;
    std::map<std::pair<int, int>, int> seen;    // (channel, control) -> its last value (live.seen)

    // Live.on_midi's pass: the messages msg becomes, each then seen
    std::vector<Msg> feed(const Msg &msg)
    {
        std::vector<Msg> out;
        bool consumed = false;
        for (Route &r : routes)
            if (r.matches(msg)) {
                r.rewrite(msg, seen, out);
                consumed = consumed || !r.keep;
            }
        std::vector<Msg> msgs;
        if (!consumed)
            msgs.push_back(msg);
        msgs.insert(msgs.end(), out.begin(), out.end());
        for (const Msg &m : msgs)
            see(m);
        return msgs;
    }

    // Live._see: the last value of each control on each channel; CC121 forgets
    // the ones it resets
    void see(const Msg &m)
    {
        int kind, dflt;
        if (m.type == 2) {
            if (m.a == 121) {
                for (int k : {1, 11, 64, 65, 66, 67, (int)DST_BEND, (int)DST_PRESSURE})
                    seen.erase(std::make_pair(m.ch, k));
            } else if (control_spec(m.a, &kind, &dflt)) {
                seen[std::make_pair(m.ch, m.a)] = m.b;
            }
        } else if (m.type == 4) {
            seen[std::make_pair(m.ch, (int)DST_BEND)] = m.a;
        } else if (m.type == 3) {
            seen[std::make_pair(m.ch, (int)DST_PRESSURE)] = m.a;
        }
    }
};

}  // namespace slab
}  // namespace nv

extern "C" {

// A part on its own slab: the template cache (nv_tcache_new, warmed),
// its part id, level, buckets, wheel step (-1 none), dampers, una corda
// (strings dropped, of the top), the rate, the steal-fade, the slab's
// capacity and headroom, the pan table (128 x 3) and the head's beta
void *nv_part_new(void *cache, long long pid, double level_db, int nbuckets, int speed, int damper_pedal,
                int soft_drop, int soft_top, double rate, double retrigger, long cap, double headroom,
                const double *pan_tab, double pan_beta)
{
    nv::slab::Part *P = new nv::slab::Part(cap);
    P->cache = cache; P->pid = pid; P->level_db = level_db; P->nbuckets = nbuckets; P->speed = speed;
    P->damper_pedal = damper_pedal; P->soft_drop = soft_drop; P->soft_top = soft_top;
    P->rate = rate; P->retrigger = retrigger;
    P->patches.push_back(nv::slab::Part::Patch{cache, pid, level_db, nbuckets, speed, damper_pedal, soft_drop,
                                                 soft_top, false, true, 0, {}, -1, 0u, 0, 127, 0});
    P->choke_p = &P->patches[0].choke;
    P->S.headroom_d = headroom;
    P->S.headroom = (float)headroom;
    memcpy(P->S.pan_tab, pan_tab, sizeof P->S.pan_tab);
    P->S.pan_beta = pan_beta;
    P->init_tables();
    return P;
}

// AN ORGAN'S STOP drawn or put in (livetui's toggle_stop: live.set_stops
// with the rank toggled) -- posted: done in the next block after its events,
// as live runs what its panel posts
void nv_part_toggle_stop(void *h, int rank, long long n0)
{
    (void)n0;
    nv::slab::Part *P = (nv::slab::Part *)h;
    nv::slab::Part::Patch &p = P->patches[0];
    if (!p.organ || rank < 0 || rank >= p.organ->n_rank)
        return;
    std::vector<char> want = p.drawn;   // (the registration now, as the panel sees it)
    want[rank] = !want[rank];
    nv::slab::Part::Post q{0, {}, nullptr};
    for (int ri = 0; ri < p.organ->n_rank; ri++)
        if (want[ri])
            q.names.push_back(p.organ->rank[ri].key);
    P->posts.push_back(std::move(q));   // (done in the next block, after its events: live.post)
}

// EACH CHANNEL's STATE a scene keeps (live.scene_from's, read from the
// engine): out[13 c + 0..7] its CC71-78 offsets (0 none), +8 its bend range
// (-1 live's), +9 fine (cents), +10 coarse (semitones), +11 its mod range
// (cents; -1 live's), +12 mono (1). Read on the audio thread (a post)
void nv_part_chanstate(void *h, double *out)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    for (int c = 0; c < 16; c++) {
        double *o = out + 13 * c;
        for (int i = 0; i < 8; i++)
            o[i] = P->snd_d[c][i];
        o[8] = P->brange[c];
        o[9] = P->fine[c];
        o[10] = P->coarse[c];
        o[11] = P->modrange[c];
        o[12] = P->mono[c] ? 1.0 : 0.0;
    }
}

// THE METRONOME (live.set_metronome): patch pi its own drum part (claiming no
// key from now: hidden; -1 the one it has), the tempo (0 stops it), the ring
void nv_part_metronome(void *h, int pi, double bpm, int ring)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (pi >= 0 && pi < (int)P->patches.size())
        P->patches[pi].hidden = true;
    P->metronome(pi, bpm, ring);
}

// A MOOG PART's KNOBS (livetui's synth pane), patch pi's on layer (0 A, 1 a
// layered voice's B): pn[NV_MK_N] its patch's with its own over them, own[k]
// 1 where it has its own. Its layers (0: not a Moog). The audio thread's
int nv_part_synth_get(void *h, int pi, int layer, double *pn, char *own)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (pi < 0 || pi >= (int)P->patches.size() || !P->patches[pi].moog)
        return 0;
    const nv::slab::Part::Patch &p = P->patches[pi];
    const int n = p.moog_b ? 2 : 1;
    if (layer >= n)
        layer = 0;
    P->moog_pn(p, false, pn, layer);
    const std::map<int, double> &syn = layer ? p.syn_b : p.syn;
    for (int k = 0; k < NV_MK_N; k++)
        own[k] = syn.count(k) ? 1 : 0;
    for (auto &kv : p.syn_kept[layer & 1]) {   // (2: the part's, refused here -- not heard natively)
        pn[kv.first] = kv.second;
        own[kv.first] = 2;
    }
    return n;
}

// ...one turned (live.set_synth from the panel: sent to a Messenger too, on
// layer A), 1 done, 0 refused
int nv_part_synth_set(void *h, int pi, int layer, int knob, double v)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (pi < 0 || pi >= (int)P->patches.size() || knob < 0 || knob >= NV_MK_N)
        return 0;
    nv::slab::Part::Patch &p = P->patches[pi];
    if (!P->set_synth(p, knob, v, layer))
        return 0;
    p.syn_kept[layer & 1].erase(knob);
    if (!layer)
        P->messenger_sync(p, knob);
    return 1;
}

// ...one set after what is already queued (a session's or preset's knobs,
// behind the swap that brings their program in)
void nv_part_synth_set_later(void *h, int pi, int layer, int knob, double v)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (knob < 0 || knob >= NV_MK_N)
        return;
    nv::slab::Part::Post q{3, {}, nullptr};
    q.pi = pi;
    q.layer = layer;
    q.knob = knob;
    q.value = v;
    P->posts.push_back(std::move(q));
}

// ...its whole panel sent to a Messenger (livetui.synth_send): 1 sent, 0 none to set
int nv_part_synth_send(void *h, int pi)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (!P->msgr_send || pi < 0 || pi >= (int)P->patches.size() || !P->patches[pi].moog)
        return 0;
    P->messenger_sync(P->patches[pi]);
    return 1;
}

// ...one put back to the patch's (livetui.synth_reset: turned to the patch's
// value, gliding there, and no longer the part's own)
void nv_part_synth_forget(void *h, int pi, int layer, int knob)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (pi < 0 || pi >= (int)P->patches.size() || knob < 0 || knob >= NV_MK_N)
        return;
    nv::slab::Part::Patch &p = P->patches[pi];
    const MoogLayer *m = layer ? p.moog_b : p.moog;
    if (!m)
        return;
    p.syn_kept[layer & 1].erase(knob);
    if (P->set_synth(p, knob, m->pn[knob], layer)) {
        (layer ? p.syn_b : p.syn).erase(knob);
        P->moog_rebuild(p);
        if (!layer)
            P->messenger_sync(p, knob);
    }
}

// AN ORGAN's DRIVE KNOB (live.set_drive): its valve stage's drive, <0 the
// voice's own (amp_drive); the stage rebuilt at the next block
void nv_part_drive(void *h, int pi, double v)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (pi < 0 || pi >= (int)P->patches.size())
        return;
    nv::slab::Part::Patch &p = P->patches[pi];
    p.drive = v < 0.0 ? -1.0 : v;
    p.amp = p.drive >= 0.0 ? p.drive : p.amp0;
    P->amp_dirty.insert(p.pid);
}

// ...one set after what is already queued (a session's, behind the swap
// that brings its program in)
void nv_part_drive_later(void *h, int pi, double v)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    nv::slab::Part::Post q{4, {}, nullptr};
    q.pi = pi;
    q.value = v;
    P->posts.push_back(std::move(q));
}

// ...and what it is: out[0] the drive in use, [1] the voice's, [2] the
// knob's (<0 none); 1 for a tonewheel organ's (a Leslie's), 0 else
int nv_part_drive_get(void *h, int pi, double *out)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (pi < 0 || pi >= (int)P->patches.size())
        return 0;
    const nv::slab::Part::Patch &p = P->patches[pi];
    out[0] = p.amp;
    out[1] = p.amp0;
    out[2] = p.drive;
    return p.leslie && !p.drums ? 1 : 0;
}

// A PATCH's FIXED TOUCH (live's part.fixed_touch: -1 its own way, 1 on, 0
// off) -- kept across its program changes, as the part's switch is -- and
// whether its patch has touch of its own (live's patch.touch_sensitive)
void nv_part_patch_touch(void *h, int pi, int fixed)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (pi >= 0 && pi < (int)P->patches.size())
        P->patches[pi].fixed_touch = fixed < 0 ? -1 : fixed != 0;
}
int nv_part_patch_touch_sensitive(void *h, int pi)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    return pi >= 0 && pi < (int)P->patches.size() && P->patches[pi].touch ? 1 : 0;
}

// A CHANNEL's SWITCHES as the engine has them (livetui.switch_on: the lamp
// says what a CC121 or a reset did too): out[0] sustain, [1] sostenuto,
// [2] soft, [3] portamento, [4] mono
void nv_part_switches(void *h, int ch, int *out)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    ch &= 15;
    out[0] = P->pedal_v[ch] > 0;
    out[1] = P->sost.count(ch) ? 1 : 0;
    out[2] = P->soft[ch] ? 1 : 0;
    out[3] = P->porta_on[ch] ? 1 : 0;
    out[4] = P->mono[ch] ? 1 : 0;
}

// THE WHOLE REGISTRATION at once (a session's: want[rank] 1 drawn): one post,
// so stops set together are not each toggled from the same registration
void nv_part_set_drawn(void *h, const char *want, int n)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    nv::slab::Part::Patch &p = P->patches[0];
    if (!p.organ)
        return;
    nv::slab::Part::Post q{0, {}, nullptr};
    for (int ri = 0; ri < p.organ->n_rank && ri < n; ri++)
        if (want[ri])
            q.names.push_back(p.organ->rank[ri].key);
    P->posts.push_back(std::move(q));   // (done in the next block, after its events: live.post)
}

// ...BY NAME, for the organ the part will have when it is done (a preset's,
// sent with its swap: the names matched to that organ's ranks then)
void nv_part_set_drawn_names(void *h, const char *const *names, int n)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    nv::slab::Part::Post q{0, {}, nullptr};
    for (int i = 0; i < n; i++)
        q.names.push_back(names[i]);
    P->posts.push_back(std::move(q));   // (done in the next block, after its events: live.post)
}

// the organ's stops drawn (out[rank] 1), the count; 0 for no organ
int nv_part_drawn(void *h, char *out, int cap)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    const nv::slab::Part::Patch &p = P->patches[0];
    if (!p.organ)
        return 0;
    int n = std::min((int)p.drawn.size(), cap);
    for (int i = 0; i < n; i++)
        out[i] = p.drawn[i];
    return n;
}

// The part's PROGRAM, a melodic one's: the class its slurs and glides read
// a patch's pungi drone: its own variation's templates (live's
// Patch.drone_note_patch), their buckets and rotor speed; NULL none
void nv_part_drone_patch(void *h, int pi, void *cache, int nbuckets, int speed)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (pi < 0 || pi >= (int)P->patches.size())
        return;
    P->patches[pi].dcache = cache;
    P->patches[pi].dnb = nbuckets > 0 ? nbuckets : 1;
    P->patches[pi].dspeed = speed;
}

void nv_part_program(void *h, int program)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    P->patches[0].program = program;
    P->program = program;
    nv::slab::Part::organ_start(P->patches[0], nv_tcache_organ(P->patches[0].cache, program));
    P->moog_sync_build(P->patches[0]);
}

// The part a DRUM PART (live.Patch(program, True)): program its drum set,
// choke[2 * (128 * program + key) + w] each key's exclusive class (native.kits')
void nv_part_drums(void *h, int program, const unsigned long long *choke)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    nv::slab::Part::Patch &p = P->patches[0];
    p.drums = true;
    p.reg = false;
    p.program = program;
    p.choke.assign(choke, choke + 2 * 16384);
    P->drums = true;
    P->program = program;
    P->cur_reg = false;
    P->choke_p = &p.choke;
}

// ANOTHER PATCH on the part (live's Parts beside it): its template cache,
// part id, level, buckets, wheel step, dampers, una corda; a drum set's
// (drums: program its set, choke its exclusive classes, as nv_part_drums)
// or not; the channel it listens on (-1 every one, less excl's bits), its
// keys lo..hi, transposed. Added last, it takes the notes it claims. Its index
int nv_part_add_patch(void *h, void *cache, long long pid, double level_db, int nbuckets, int speed, int damper_pedal,
                    int soft_drop, int soft_top, int drums, int program, const unsigned long long *choke, int channel,
                    unsigned excl, int lo, int hi, int transpose)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    nv::slab::Part::Patch p{cache, pid, level_db, nbuckets, speed, damper_pedal, soft_drop, soft_top, drums != 0,
                             false, program, {}, channel, excl, lo, hi, transpose};
    if (drums && choke)
        p.choke.assign(choke, choke + 2 * 16384);
    if (!drums) {
        nv::slab::Part::organ_start(p, nv_tcache_organ(cache, program));
        P->moog_sync_build(p);
    }
    P->patches.push_back(std::move(p));
    P->choke_p = &P->patches[P->cur].choke;          // (the vector may have moved)
    return (int)P->patches.size() - 1;
}

// A PATCH CHANGE posted (live._swap_patch, done after the next block's
// events): patch pi on cache (warmed: the program's templates), its
// program, a drum set or not, its buckets, wheel step, dampers, una corda,
// the honky-tonk's detune wheel, a drum set's exclusive classes (NULL: as
// they were), and which keys answer the register (NULL: as they were)
// ...its strings, where the new voice's are another's (live._reg_forget):
// staged for the next nv_part_swap -- the bank (M modes, as nv_strings makes
// it), kappa, knock, fall, floor, the felt's BETA, its release (samples),
// damper_top, whether it has dampers, which keys answer (128), its choirs
// (nchoir bridges, their cross coupling, nbuff (buffed, plain) pairs; 0 none)
void nv_part_swap_bank(void *h, const StringMode *modes, int M, const double *k6, int top, int pedals, const int *note,
                     int nchoir, const long *cbr, double cross, int nbuff, const int *buffs)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    auto b = std::make_shared<nv::slab::Part::Bank>();
    b->modes.assign(modes, modes + M);
    b->kappa = k6[0]; b->knock = k6[1]; b->fall = k6[2]; b->fl = k6[3]; b->beta = k6[4]; b->rel = k6[5];
    b->top = top; b->pedals = pedals;
    b->note.assign(note, note + 128);
    if (nchoir > 0) {
        b->cbr.assign(cbr, cbr + nchoir);
        b->cross = cross;
        b->buffs.assign(buffs, buffs + 2 * nbuff);
    }
    P->staged_bank = b;
}

void nv_part_swap(void *h, int pi, void *cache, int program, int drums, int nbuckets, int speed, int damper_pedal,
                int soft_drop, int soft_top, int detune_wheel, const unsigned long long *choke, const int *reg_note)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    nv::slab::Part::Swap w{pi, cache, program, drums, nbuckets, speed, damper_pedal, soft_drop, soft_top,
                            detune_wheel, {}, {}, P->staged_bank};
    P->staged_bank.reset();
    if (choke)
        w.choke.assign(choke, choke + 2 * 16384);
    if (reg_note)
        w.reg_note.assign(reg_note, reg_note + 128);
    P->posts.push_back(nv::slab::Part::Post{1, {}, std::make_shared<nv::slab::Part::Swap>(std::move(w))});
}

// a patch's channel (-1 every one, less excl's bits), keys and transpose
void nv_part_patch_range(void *h, int i, int channel, unsigned excl, int lo, int hi, int transpose)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    nv::slab::Part::Patch &p = P->patches[i];
    p.channel = channel;
    p.excl = excl;
    p.lo = lo;
    p.hi = hi;
    p.transpose = transpose;
    if (P->cur == i)                        // (the patch in use: the part's copy too)
        P->transpose = transpose;
}

// A PATCH's LEVEL AND MUTE (live's part.level_db, part.muted), read as a
// note is struck: what already sounds keeps its own
void nv_part_patch_level(void *h, int i, double level_db, int muted)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (i < 0 || i >= (int)P->patches.size())
        return;
    P->patches[i].level_db = level_db;
    P->patches[i].muted = muted != 0;
    if (P->cur == i)
        P->level_db = level_db;
}

// A PATCH TAKEN AWAY (live.set_parts: a part no longer in the set): it
// claims no key from now, and its notes are let go at n0 (live's go, a
// block after the swap) -- its place kept, so no other patch's index moves
void nv_part_patch_gone(void *h, int i, long long n0)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (i <= 0 || i >= (int)P->patches.size() || P->patches[i].gone)
        return;                             // (patch 0 is the part itself: never taken)
    P->patches[i].gone = true;
    const long long pid = P->patches[i].pid;
    std::vector<nv::slab::Key> ks;
    for (auto &kv : P->S.live)
        if (std::get<0>(kv.first) == pid)
            ks.push_back(kv.first);
    for (auto &k : ks) {
        P->S.oneshot.erase(k);
        P->S.release(k, n0);
    }
}

void nv_part_free(void *h)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (P->efx)
        nv_efx_live_free(P->efx);
    delete P;
}

// THE MODULE's INSERTION EFFECT for this engine: the export's tables (K_EFX)
// at the render's rate
void nv_part_efx(void *h, const double *X, double SR)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (!P->efx)
        P->efx = nv_efx_live_new(X, SR);
    P->efx_x = X;
}

// THE MODULE's INSERTION EFFECT as a panel shows it (nv_efx_live_state;
// the audio thread's), and its revision: -1 where the export has none
int nv_part_efx_state(void *h, int *o, int cap, const char **why)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (!P->efx)
        return -1;
    int n = nv_efx_live_state(P->efx, o, cap, why);
    return n;
}

// live.pan_at's head for a 3D type's place (the export's LP3D)
void nv_part_place3d(void *h, const double *q)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    memcpy(P->p3d, q, sizeof P->p3d);
    P->has_p3d = true;
}

// convolver.c's calls for the part's bus (a reverb type's: live's Convolver)
void nv_part_conv(void *h, void *cn, void *cp, void *cf)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    P->bus_cn = cn;
    P->bus_cp = cp;
    P->bus_cf = cf;
}

long nv_part_efx_rev(void *h)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    return P->efx ? nv_efx_live_rev(P->efx) : -1;
}

// The part's free strings (live's register): its string bank (M modes, as
// nv_strings makes it), register.LiveChannel's constants (kappa, knock,
// fall, floor, damper_top, the felt's BETA), the class's dampers and release
// (samples), damper.py's FULL_DB_S, RESIDUAL, LN10_20, the block, and which
// keys' classes answer (live._reg_voice, 128 flags)
void nv_part_register(void *h, const StringMode *modes, int M, double kappa, double knock, double fall, double fl,
                    int top, double beta, int pedals, double rel, double full_db_s, double residual, double ln10_20,
                    long long blk, const int *reg_note)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    P->reg_on = true;
    P->rmodes.assign(modes, modes + M);
    P->wk.modes = P->rmodes;                // (the worker's copy)
    P->wk.kappa = kappa; P->wk.knock = knock; P->wk.fall = fall; P->wk.fl = fl; P->wk.top = top; P->wk.beta = beta;
    P->r_kappa = kappa; P->r_knock = knock; P->r_fall = fall; P->r_fl = fl; P->r_top = top; P->r_beta = beta;
    P->r_pedals = pedals; P->r_rel = rel; P->r_full = full_db_s; P->r_resid = residual; P->r_ln = ln10_20;
    P->r_blk = (double)blk;
    for (int k = 0; k < 128; k++)
        P->reg_note[k] = reg_note[k] != 0;
}

// a bank's bridges by key, partners and knock (a dulcimer's: its class's
// reg_keyed), for its register -- or, after nv_part_swap_bank, the staged bank's
void nv_part_reg_keys(void *h, const NoteClass *k)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    P->wk.keyed = k;
}

void nv_part_swap_bank_keys(void *h, const NoteClass *k)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (P->staged_bank)
        P->staged_bank->keyed = k;
}

// a harpsichord's choirs, for its register (Strings.choir_bridges, cross, buffs)
void nv_part_reg_choirs(void *h, int nchoir, const long *bridges, double cross, int nbuff, const int *buffs)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    P->r_cbr.assign(bridges, bridges + nchoir);
    P->r_cross = cross;
    P->r_buffs.assign(buffs, buffs + 2 * nbuff);
    P->wk.cbr = P->r_cbr;                   // (the worker's copy)
    P->wk.cross = cross;
    P->wk.buffs = P->r_buffs;
}

// the chests' rows (live's wind_next, wind_spent, wind_free, each chest's rows):
// out[0] wind_next, then the spent rows, -1, the free ones, -1, each chest's
// rows (pid, n, rows...), to cap; the count written
int nv_part_wind_info(void *h, long long *out, int cap)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    std::vector<long long> v;
    v.push_back(P->wind_next);
    for (int r : P->wind_spent)
        v.push_back(r);
    v.push_back(-1);
    for (int r : P->wind_free)
        v.push_back(r);
    v.push_back(-1);
    for (auto &kv : P->wind_st) {
        v.push_back(kv.first);
        v.push_back((long long)kv.second.rows.size());
        for (auto &x : kv.second.rows)
            v.push_back(x.second);
    }
    int n = std::min((int)v.size(), cap);
    for (int i = 0; i < n; i++)
        out[i] = v[i];
    return n;
}

// the slab's live keys in their order (live's dict's): (pid, ch, note, layer) each, and
// a rank's stop name (live's k[3]) into names, '\n' after each; the count
int nv_part_live_keys(void *h, long long *out, int cap, char *names, int ncap)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    int n = 0, w = 0;
    for (auto &kv : P->S.live) {
        if (n >= cap)
            break;
        const nv::slab::Key &k = kv.first;
        out[4 * n] = std::get<0>(k); out[4 * n + 1] = std::get<1>(k);
        out[4 * n + 2] = std::get<2>(k); out[4 * n + 3] = std::get<3>(k);
        const char *nm = P->rank_name(k);
        for (const char *c = nm; *c && w < ncap - 2; c++)
            names[w++] = *c;
        names[w++] = '\n';
        n++;
    }
    names[w] = 0;
    return n;
}

// the first chest's state (live's wind.Wind: w1 w2 s1 s2 d1 r1 te tph); 0 for no chest
int nv_part_wind_state(void *h, double *out)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    if (P->wind_st.empty())
        return 0;
    const auto &st = P->wind_st.begin()->second;
    double v[8] = {st.w1, st.w2, st.s1, st.s2, st.d1, st.r1, st.te, st.tph};
    memcpy(out, v, sizeof v);
    return 1;
}

// the bend rows' tables (live's Slab.BR, BC, BL: the wind's and the sirens'), n rows of each
int nv_part_bend_rows(void *h, float *br, double *bc, float *bl, int n)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    int m = std::min(n, (int)P->BRt.size());
    for (int r = 0; r < m; r++) {
        br[r] = P->BRt[r];
        bc[r] = P->BCt[r];
        bl[2 * r] = P->BLt[2 * r];
        bl[2 * r + 1] = P->BLt[2 * r + 1];
    }
    return m;
}

// the register's rows dropped for a full slab, and whether any are placed
long nv_part_reg_dropped(void *h) { return ((nv::slab::Part *)h)->reg_dropped; }

// an event for the next block: 0 note-on (a key, b velocity), 1 note-off, 2 control (a cc, b value)
void nv_part_event(void *h, int type, int ch, int a, int b)
{
    ((nv::slab::Part *)h)->events.push_back(nv::slab::Ev{type, ch, a, b});
}

// an exclusive (the bytes between F0 and F7), the next of the block's events
void nv_part_sysex(void *h, const uint8_t *d, int n)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    P->events.push_back(nv::slab::Ev{6, -1, (int)P->sx.size(), 0});
    P->sx.push_back(std::vector<uint8_t>(d, d + n));
}

// a reset heard since last asked (every part to program 0): 1, and forgotten
int nv_part_take_reset(void *h)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    bool r = P->reset_asked;
    P->reset_asked = false;
    return r ? 1 : 0;
}

// the tuners' reference for the gm2 store's built-in tables (--a: 69, --c: 60), note -1 none
void nv_part_mts_ref(void *h, int note, double hz)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    P->mts_ref_note = note;
    P->mts_ref_hz = hz;
}

void nv_part_block(void *h, long long n0, long long blk) { ((nv::slab::Part *)h)->block(n0, blk); }

// the Moog's tables for a check: 0 FT, 1 KN (floats, n of them; how many there are)
long nv_part_moog_table(void *h, int which, float *out, long n)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    const std::vector<float> &v = which == 0 ? P->S.FT : P->S.KN;
    for (long i = 0; i < n && i < (long)v.size(); i++)
        out[i] = v[i];
    return (long)v.size();
}

// THE LIVE SLOTS' COLUMNS, for a check: each sounding slot's f8, f4, f4n, i8
// and i4 (NF8 + NF4 + NF4N + NI8 + NI4 numbers, slab.cpp's names' order),
// up to cap slots; how many there are
long nv_part_slots_dump(void *h, double *out, long cap)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    const auto &S = P->S;
    const int W = nv::slab::NF8 + nv::slab::NF4 + nv::slab::NF4N + nv::slab::NI8 + nv::slab::NI4;
    long n = 0;
    for (const auto &kv : S.live)
        for (long sl : kv.second) {
            if (n < cap) {
                double *o = out + (size_t)W * n;
                int c = 0;
                for (int q = 0; q < nv::slab::NF8; q++) o[c++] = S.f8[q][sl];
                for (int q = 0; q < nv::slab::NF4; q++) o[c++] = S.f4[q][sl];
                for (int q = 0; q < nv::slab::NF4N; q++) o[c++] = S.f4n[q][sl];
                for (int q = 0; q < nv::slab::NI8; q++) o[c++] = (double)S.i8[q][sl];
                for (int q = 0; q < nv::slab::NI4; q++) o[c++] = (double)S.i4[q][sl];
            }
            n++;
        }
    return n;
}

// the kernel library's Moog row functions (synthkernel.c moog_pitch_cells,
// moog_shape_rows), as the caller has it loaded
void nv_part_moog_kernel(void *h, void *pcells, void *srows, void *crows)
{
    nv_moog_coeff(crows);           // (a synced OSC 2's coefficients: nv_moog_build's)
    ((nv::slab::Part *)h)->moog_pcells = pcells;
    ((nv::slab::Part *)h)->moog_srows = srows;
}

// Renderer.render's block: L, R (and with SL the room's send pair) over
// [n0, n0 + frames), through synth_voice (sv), synth_voice_xdec (sx) and
// synth_voice_damp (sd; NULL: no row is drawn by a damper track)
void nv_part_render(void *h, long long n0, long frames, float *L, float *R, float *SL, float *SR, void *sv, void *sx,
                  void *sd, long long blk, double master_gain)
{
    ((nv::slab::Part *)h)->render(n0, frames, L, R, SL, SR, sv, sx, sd, blk, master_gain);
}

// THE ROUTES (live.Route, Live.on_midi): a router, its routes added in
// order, each (source kind, its CC/half/key, destination, keep, channel -1
// all, latch, press)
void *nv_rt_new() { return new nv::slab::Router(); }

void nv_rt_add(void *h, int src, int arg, int dst, int keep, int channel, int latch, int press)
{
    nv::slab::Route r;
    r.src = src; r.arg = arg; r.dst = dst; r.keep = keep != 0; r.channel = channel; r.latch = latch != 0;
    r.press = press != 0;
    ((nv::slab::Router *)h)->routes.push_back(r);
}

// one message in (type, ch, a, b); up to cap out, 4 ints each; how many
int nv_rt_feed(void *h, int type, int ch, int a, int b, int *out, int cap)
{
    std::vector<nv::slab::Msg> got = ((nv::slab::Router *)h)->feed(nv::slab::Msg{type, ch, a, b});
    int n = 0;
    for (const nv::slab::Msg &m : got)
        if (n < cap) {
            out[4 * n] = m.type; out[4 * n + 1] = m.ch; out[4 * n + 2] = m.a; out[4 * n + 3] = m.b;
            n++;
        }
    return n;
}

void nv_rt_free(void *h) { delete (nv::slab::Router *)h; }

// the panel's: how many routes, route i's seven (nv_rt_add's), route i gone
int nv_rt_count(void *h) { return (int)((nv::slab::Router *)h)->routes.size(); }

void nv_rt_get(void *h, int i, int *out)
{
    const nv::slab::Route &r = ((nv::slab::Router *)h)->routes[i];
    int v[7] = {r.src, r.arg, r.dst, r.keep, r.channel, r.latch, r.press};
    memcpy(out, v, sizeof v);
}

void nv_rt_del(void *h, int i)
{
    auto &rs = ((nv::slab::Router *)h)->routes;
    if (i >= 0 && i < (int)rs.size())
        rs.erase(rs.begin() + i);
}

// the damper tracks' values (DM: 2 x 256 floats)
void nv_part_dm(void *h, float *out)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    memcpy(out, P->DM.data(), sizeof(float) * P->DM.size());
}

// THE GPU (live.GpuRenderer): voice_block from the GPU's build (vb), its
// damper build's voice_block and voice_damp_set (vbd, vds), voice_samples
// (vs, the C reference) and voice_sizes (vz); cl an OpenCL GPU (nv_cl_new),
// NULL to run the samples through voice_samples; a block of gpu_min busy
// slots or more goes to it, its setup on nthr threads
// THE SOUND CANVAS'S DISPLAY (gsdisplay.Display.showing): what it shows now --
// the text (33 bytes, "" none) and how long it has shown, the page's 16 x 16
// dots (rows[16 r + c], 0/1; *page 0 none); its display time, s. 1 read, 0
// none to show
int nv_part_display(void *h, char *text, double *text_age, int *page, unsigned char *rows)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    nv::slab::Part::GsDisplay g;
    for (int tries = 0; tries < 100; tries++) {
        unsigned s0 = P->gsd_seq.load();
        if (s0 & 1)
            continue;
        g = P->gsd;
        if (P->gsd_seq.load() == s0)
            break;
    }
    const double now = nv::slab::Part::gsd_now(), hold = g.steps * 0.48;
    text[0] = 0;
    *page = 0;
    *text_age = 0.0;
    if (g.text_at >= 0.0 && now - g.text_at < hold && g.text[0]) {
        memcpy(text, g.text, 33);
        *text_age = now - g.text_at;
    }
    if (g.page && g.page_at >= 0.0 && now - g.page_at < hold) {
        *page = g.page;
        const uint8_t *m = g.mem[(g.page + 1) / 2 - 1] + (g.page % 2 ? 0 : 0x40);
        for (int r = 0; r < 16; r++)
            for (int c = 0; c < 16; c++) {
                const int s = c / 5;
                const uint8_t b = m[16 * s + r];
                rows[16 * r + c] = s < 3 ? (b & (0x10 >> (c % 5))) != 0 : (b & 0x10) != 0;
            }
    }
    return text[0] || *page;
}

// THE MOOG EXTENSIONS' KERNELS (blockrender.ensure_moogx_lib, ensure_gpu_moogx_lib):
// synth_voice_moogx (smx), and the GPU build's voice_block, voice_damp_set and
// voice_moogx_set (vbm, vmd, vmm; NULL: none)
void nv_part_moogx(void *h, void *smx, void *vbm, void *vmd, void *vmm)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    P->smx = smx;
    P->gp.vbm = vbm;
    P->gp.vmd = vmd;
    P->gp.vmm = vmm;
}

void nv_part_gpu(void *h, void *vb, void *vbd, void *vds, void *vs, void *vz, void *cl, long gpu_min, int nthr)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    auto &g = P->gp;
    g.vb = vb; g.vbd = vbd; g.vds = vds; g.vs = vs; g.cl = cl; g.gpu_min = gpu_min; g.nthr = nthr;
    int sz[3];
    ((nv_vsizes_fn)vz)(sz);
    g.D.make(1024, sz[0]);
    g.C.make(1024, sz[1]);
    g.SB.make(1 << 14, sz[2]);
}

// THE PIPELINE (live's TUNING_GPU_PIPELINE): on, every block a block late --
// the CPU's setup of the next while the GPU renders this one (an OpenCL GPU's)
void nv_part_pipeline(void *h, int on) { ((nv::slab::Part *)h)->pipeline = on != 0; }

// The register's jobs on a worker thread of the part's own, off the audio
// thread (live's worker process): answers placed at the pump after they are
// ready, not in step -- for playing, not for the checks
void nv_part_reg_async(void *h) { ((nv::slab::Part *)h)->start_reg_worker(); }

// Slab.shed: the highest frac of the partials sounding at n end over 5 ms; how many
// the scanner's constants and circuit tables (scanner.cpp's: the export's SCAN)
void nv_part_scan(void *h, const double *X, long n)
{
    ((nv::slab::Part *)h)->scan.assign(X, X + n);
}

// the valve's passes off the audio thread (nvlive playing: live's workers)
void nv_part_amp_async(void *h) { ((nv::slab::Part *)h)->start_amp_worker(); }

// live.LIVE_AMP_LOOKAHEAD and LIVE_AMP_HOLD, as the checks set them
void nv_part_amp_ahead(void *h, int blocks, int hold)
{
    ((nv::slab::Part *)h)->LIVE_AMP_LOOKAHEAD = blocks;
    ((nv::slab::Part *)h)->LIVE_AMP_HOLD = hold != 0;
}

// the scanner's data off the audio thread (nvlive playing: live's builder)
void nv_part_scan_async(void *h) { ((nv::slab::Part *)h)->start_scan_worker(); }

// the Leslie's constants (leslie.cpp's L_*): the part's rotors, on chorale
void nv_part_leslie(void *h, const double *L, int n)
{
    ((nv::slab::Part *)h)->leslie_start(std::vector<double>(L, L + n));
}

long nv_part_shed(void *h, long long n, double frac) { return ((nv::slab::Part *)h)->shed(n, frac); }

// The governor: a block took ms against its budget_ms, the next starts at n;
// returns the partials it shed now
long nv_part_govern(void *h, double ms, double budget_ms, long long n)
{
    return ((nv::slab::Part *)h)->govern(ms, budget_ms, n);
}

long nv_part_partials_shed(void *h) { return ((nv::slab::Part *)h)->partials_shed; }

// the notes (and grains, layers, ranks) the slab had no room for: --slots too small
long nv_part_dropped(void *h) { return ((nv::slab::Part *)h)->dropped; }

// THE PANEL'S: a global set between blocks -- 0 headroom (dB), 1 the
// pressure's lift (dB), 2 the limiter's knee, 3 the wheel's range, 4 the mod
// range (cents), 5 the GPU on (1) or off, 6 the room's tail on or off
// A MESSENGER TO SET: send(ctx, bytes, n) takes what is sent (NULL none),
// its pitch-bend range; then every Moog part set to its panel (the start)
void nv_part_messenger(void *h, void (*send)(void *, const uint8_t *, int), void *ctx, double bend)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    P->msgr_send = send;
    P->msgr_ctx = ctx;
    P->msgr_bend = bend;
    for (const auto &p : P->patches)
        P->messenger_sync(p);
}

void nv_part_set(void *h, int what, double v)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    switch (what) {
    case 0:
        P->S.headroom_d = pow(10.0, -v / 20.0);
        P->S.headroom = (float)P->S.headroom_d;
        break;
    case 1: P->press_db = v; break;
    case 2: P->thresh = v; break;
    case 3: P->bend_range = v; break;
    case 4: P->mod_cents = v; break;
    case 5: P->gpu_off = v < 0.5; break;
    case 6: P->room_on = v >= 0.5; break;
    case 7: P->mod_rate = v; break;
    case 8: P->msgr_all = v >= 0.5; break;
    case 9: P->msgr_pre107 = v >= 0.5; break;
    }
}

// what the panel shows: 0 busy slots, 1 keys sounding, 2 partials shed, 3
// register rows dropped, 4 the GPU took the last block, 5 its setup ms, 6
// its samples ms, 7 channel 1's pedal, 8 sostenuto down on it, 9 mono on it,
// 10 damper tracks, 11 a room, 12 the GPU on, 13 the tail on, 14 the bend
// on channel 1 (cents)
void nv_part_stats(void *h, double *out)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    long busy = 0;
    for (long q = 0; q < P->S.cap; q++)
        busy += P->S.busy[q] != 0;
    out[0] = (double)busy;
    out[1] = (double)P->S.live.size();
    out[2] = (double)P->partials_shed;
    out[3] = (double)P->reg_dropped;
    out[4] = P->on_gpu;
    out[5] = P->ms_setup;
    out[6] = P->ms_samples;
    out[7] = P->pedal_v[0];
    out[8] = P->sost.count(0) ? 1.0 : 0.0;
    out[9] = P->mono[0];
    out[10] = (double)P->dtracks.size();
    out[11] = P->room ? 1.0 : 0.0;
    out[12] = P->gp.vb && !P->gpu_off;
    out[13] = P->room_on;
    out[14] = 1200.0 * log2(P->bend[0]);
}

// live.panic, at n0
void nv_part_panic(void *h, long long n0) { ((nv::slab::Part *)h)->panic(n0); }

// did the last block render on the GPU
int nv_part_on_gpu(void *h) { return ((nv::slab::Part *)h)->on_gpu; }

// ...and its two halves, ms: the setup (voice_block), the samples
void nv_part_gpu_ms(void *h, double *out)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    out[0] = P->ms_setup;
    out[1] = P->ms_samples;
}

// The late room (live.RoomTail) through convolver.c's conv_new, conv_process
// and conv_free: ir n stereo samples interleaved, mir the modes' (m 0: none)
void nv_part_room(void *h, void *cn, void *cp, void *cf, const float *ir, long n, const float *mir, long m, int frames)
{
    ((nv::slab::Part *)h)->room.reset(new nv::slab::Room(cn, cp, cf, ir, n, mir, m, frames));
}

// A ROOM's TAIL made (off the audio thread: its convolvers and their thread),
// NULL none; installed on the audio thread between two blocks (nv_part_room_set:
// live._room_install's crossfade), the old freed later off it (nv_part_room_reap)
void *nv_room_new(void *cn, void *cp, void *cf, const float *ir, long n, const float *mir, long m, int frames)
{
    return n > 0 ? new nv::slab::Room(cn, cp, cf, ir, n, mir, m, frames) : nullptr;
}

void nv_part_room_set(void *h, void *room, long long frames)
{
    ((nv::slab::Part *)h)->room_install((nv::slab::Room *)room, frames);
}

void nv_part_room_reap(void *h)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    std::vector<std::unique_ptr<nv::slab::Room>> gone;
    {
        std::lock_guard<std::mutex> lk(P->room_mu);
        gone.swap(P->room_trash);
    }
}

// the soft limiter's knee (live.thresh), the pitch wheel's range (live.bend_range)
// and the mod wheel's (live.mod_cents)
void nv_part_post(void *h, double thresh, double bend_range, double mod_cents)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    P->thresh = thresh;
    P->bend_range = bend_range;
    P->mod_cents = mod_cents;
}

// live's callback after its events and step: the render, the room, the limiter
void nv_part_output(void *h, long long n0, long frames, float *L, float *R, void *sv, void *sx, void *sd,
                  long long blk, double master_gain)
{
    ((nv::slab::Part *)h)->output(n0, frames, L, R, sv, sx, sd, blk, master_gain);
}

// The mod wheel picks a honky-tonk's detune (live's 'detune' role)
void nv_part_detune_wheel(void *h, int on) { ((nv::slab::Part *)h)->detune_wheel = on != 0; }

// THE GS EQ onto the slab (live._gs_eq): on, its shelves, the channels off
void nv_part_gs_eq(void *h, int on, double lo_f, double hi_f, double lo_g, double hi_g, unsigned off)
{
    nv::slab::Slab &S = ((nv::slab::Part *)h)->S;
    S.eq_on = on != 0;
    S.eq_lo_f = lo_f;
    S.eq_hi_f = hi_f;
    S.eq_lo_g = lo_g;
    S.eq_hi_g = hi_g;
    S.eq_off = off;
}

// Pressure's level at full aftertouch, dB (live.press_db)
void nv_part_press_db(void *h, double db) { ((nv::slab::Part *)h)->press_db = db; }

// The dampers in between (live._damp_block): damper.py's FULL_DB_S,
// RESIDUAL, KNEE_DB, BETA and LN10_20
void nv_part_damper(void *h, double full_db_s, double residual, double knee_db, double beta, double ln10_20)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    P->dmp_on = true;
    P->dmp_full = full_db_s; P->dmp_res = residual; P->dmp_knee = knee_db; P->dmp_beta = beta; P->dmp_ln = ln10_20;
}

// the part's slab, for nv_slab_col and nv_slab_free_list
void *nv_part_slab(void *h) { return &((nv::slab::Part *)h)->S; }


void *nv_slab_new(long capacity, double headroom)
{
    nv::slab::Slab *S = new nv::slab::Slab(capacity);
    S->headroom_d = headroom;
    S->headroom = (float)headroom;
    return S;
}

void nv_slab_free(void *h) { delete (nv::slab::Slab *)h; }

// a template's columns by group (live's COLS_F8, COLS_F4, COLS_I8, COLS_I4
// order), its hrel; key (part, channel, note, layer); send NAN for none
int nv_slab_stamp(void *h, double *const *tf8, float *const *tf4, long long *const *ti8, int32_t *const *ti4,
                  const float *threl, long n, long long part, long long ch, long long note, long long layer,
                  long long n0, double vel_scale, long long dur, int one, double tsend)
{
    nv::slab::Slab *S = (nv::slab::Slab *)h;
    return S->stamp(tf8, tf4, ti8, ti4, threl, n, nv::slab::Key(part, ch, note, layer), n0, vel_scale, dur, one != 0,
                    tsend, ch);
}

void nv_slab_release(void *h, long long part, long long ch, long long note, long long layer, long long n)
{
    ((nv::slab::Slab *)h)->release(nv::slab::Key(part, ch, note, layer), n);
}

void nv_slab_reap(void *h, long long n, long long blk) { ((nv::slab::Slab *)h)->reap(n, blk); }

// a column's values over the capacity: group 0 F8, 1 F4, 2 F4_NOTE, 3 I8, 4 I4;
// 5 the bookkeeping (index: sw aL0 aR0 sg sre hrel vbase vrbase vsc), 6 dk/slot_ch/busy,
// 7 aLp/aRp, 8 dg (index 3)
void nv_slab_col(void *h, int group, int index, void *out)
{
    nv::slab::Slab *S = (nv::slab::Slab *)h;
    long n = S->cap;
    switch (group) {
    case 0: memcpy(out, S->f8[index].data(), sizeof(double) * n); break;
    case 1: memcpy(out, S->f4[index].data(), sizeof(float) * n); break;
    case 2: memcpy(out, S->f4n[index].data(), sizeof(float) * n); break;
    case 3: memcpy(out, S->i8[index].data(), sizeof(long long) * n); break;
    case 4: memcpy(out, S->i4[index].data(), sizeof(int32_t) * n); break;
    case 5: {
        std::vector<float> *v[] = {&S->sw, &S->aL0, &S->aR0, &S->sg, &S->sre, &S->hrel, &S->vbase, &S->vrbase,
                                   &S->vsc};
        memcpy(out, v[index]->data(), sizeof(float) * n);
        break;
    }
    case 8:
        memcpy(out, S->dg.data(), sizeof(float) * n);
        break;
    case 10: {                          // the Leslie's: ls_on, ls_horn (as float), ls_am, ls_sharp, ls_norm, ls_ph, ls_aL, ls_aR
        if (index <= 1)
            for (long i = 0; i < n; i++)
                ((float *)out)[i] = (index == 0 ? S->ls_on : S->ls_horn)[i];
        else
            memcpy(out, (index == 2 ? S->ls_am : index == 3 ? S->ls_sharp : index == 4 ? S->ls_norm
                         : index == 5 ? S->ls_ph : index == 6 ? S->ls_aL : S->ls_aR).data(), sizeof(float) * n);
        break;
    }
    case 9: {                           // the tremolo's: tr_dep, tr_aL, tr_aR, tr_st, tr_on, hs_dep
        if (index == 4)
            for (long i = 0; i < n; i++)
                ((float *)out)[i] = S->tr_on[i];
        else if (index == 5)
            memcpy(out, S->hs_dep.data(), sizeof(float) * n);
        else
            memcpy(out, (index == 0 ? S->tr_dep : index == 1 ? S->tr_aL : index == 2 ? S->tr_aR : S->tr_st).data(),
                   sizeof(float) * n);
        break;
    }
    case 7:
        memcpy(out, (index == 0 ? S->aLp : S->aRp).data(), sizeof(float) * n);
        break;
    case 6: {
        if (index == 0)
            memcpy(out, S->dk.data(), sizeof(int32_t) * n);
        else if (index == 1)
            memcpy(out, S->slot_ch.data(), sizeof(int32_t) * n);
        else
            for (long i = 0; i < n; i++)
                ((int32_t *)out)[i] = S->busy[i];
        break;
    }
    }
}

// the free queue, in order: its length (out up to cap)
long nv_slab_free_list(void *h, long *out, long cap)
{
    nv::slab::Slab *S = (nv::slab::Slab *)h;
    long n = 0;
    for (long s : S->free)
        if (n < cap)
            out[n++] = s;
    return (long)S->free.size();
}

}  // extern "C"
