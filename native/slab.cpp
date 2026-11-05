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

extern "C" int nv_tcache_slur_fade(void *h, int program, int note, double *out);
extern "C" const NoteClass *nv_tcache_note_class(void *h, int program, int note);
extern "C" int nv_tcache_glide(void *h, int program, int src, int tgt, int cc5, double *out);
extern "C" const OrganSpec *nv_tcache_organ(void *h, int program);
extern "C" const NoteClass *nv_tcache_class(void *h, int program);
extern "C" double nv_tcache_trim(void *h, int program);
extern "C" double nv_cab_gain(const NoteClass *k, double hz);
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

extern "C" double nv_damper_contact(int p, int key, int top);

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
    float headroom = 1.0f;
    double headroom_d = 1.0;
    // A SECTION'S ENTRIES ARE REDRAWN AT EVERY PRESS (live.Slab._rng)
    PyRandom scat_rng;

    explicit Slab(long capacity) : cap(capacity)
    {
        pyr_seed(&scat_rng, 0x5CA7);
        owner.assign(cap, -1);
        f8.assign(NF8, std::vector<double>(cap, 0.0));
        f4.assign(NF4, std::vector<float>(cap, 0.0f));
        f4n.assign(NF4N, std::vector<float>(cap, 0.0f));
        i8.assign(NI8, std::vector<long long>(cap, IDLE));
        i4.assign(NI4, std::vector<int32_t>(cap, 0));
        // live.Slab's rest: no gate, bend row or Moog filter row (-1); unit
        // gains, harmonic ratio and vibrato scale; the vibrato at 5.5 Hz
        for (int c : {I4_gr, I4_br, I4_fx})
            i4[c].assign(cap, -1);
        f4[F4_cbw].assign(cap, 100000.0f);      // the wash's width: blockrender.RAND_GRAN, never 0
        sw.assign(cap, 1.0f);
        aL0.assign(cap, 0.0f); aR0.assign(cap, 0.0f); sg.assign(cap, 1.0f); sre.assign(cap, 1.0f);
        hrel.assign(cap, 1.0f); vbase.assign(cap, 0.0f); vsc.assign(cap, 1.0f);
        vrbase.assign(cap, 1.0f * 5.5f);
        dk.assign(cap, -1); slot_ch.assign(cap, -1);
        dg.assign(cap, 0.0f);
        aLp.assign(cap, 0.0f); aRp.assign(cap, 0.0f);
        tr_on.assign(cap, 0); tr_dep.assign(cap, 0.0f); tr_aL.assign(cap, 0.0f); tr_aR.assign(cap, 0.0f);
        cv_on.assign(cap, 0); cv_aL.assign(cap, 0.0f); cv_aR.assign(cap, 0.0f);
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
               const double *aL64 = nullptr, const double *aR64 = nullptr)
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
        if (!std::isnan(tsend) && ch >= 0)
            swv = tsend;
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
        return stamp(f8p, f4p, i8p, i4p, T.hrel.data(), T.P, key, n0, vel_scale, T.dur, T.oneshot, NAN, ch,
                     T.sof.empty() ? nullptr : T.sof.data(), T.rof.empty() ? nullptr : T.rof.data(),
                     std::isnan(scat) ? T.scatter_ms : scat, rate);
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
        const double *t1 = pan_tab[clamp(cc)], *t0 = pan_tab[clamp(was)];
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
            mo_uL[s] *= r[q]; mo_uR[s] *= r[q];
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
            f4[F4_aL][s] = (float)((double)ls_aL[s] * g);
            f4[F4_aR][s] = (float)((double)ls_aR[s] * g);
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

    void moog_alloc()
    {
        FT.assign(MOOG_FT_ROWS * FT_W, 0.0f);
        KN.assign(MOOG_KN_ROWS * 2 * KN_W, 0.0f);
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
        if (kn)
            set_knobs(r, kn, false);
        return r;
    }

    // Slab.set_knobs: the knobs' new values the END of the next block (ramp),
    // or both ends
    void set_knobs(int r, const double *kn, bool ramp)
    {
        for (int j = 0; j < KN_W; j++) {
            KN[(2 * r + 1) * KN_W + j] = (float)kn[j];
            if (!ramp)
                KN[2 * r * KN_W + j] = (float)kn[j];
        }
    }

    // Slab.knobs_advance's knob rows: a block's end the next one's start
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
    void moog_retimbre(const std::vector<long> &idx, const MoogLayer *L, double rate, const Retune *retune = nullptr)
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
            std::vector<float> *bases[3] = {side ? &ls_aR : &ls_aL, side ? &tr_aR : &tr_aL, side ? &cv_aR : &cv_aL};
            const std::vector<char> *arm[3] = {&ls_on, &tr_on, &cv_on};
            for (size_t i = 0; i < n; i++) {
                long s = idx[i];
                double nw = (double)uo[s] * w[i];
                float old = a0[s];
                bool z = old == 0.0f;
                float q = (float)(z ? 1.0 : nw / (double)old);
                for (int b = 0; b < 3; b++) {
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
            if ((double)n > tail) {
                std::vector<long> freed;
                for (long s : r.first) {
                    i8[0][s] = IDLE;
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
                            // 4 the pitch wheel (a, -8192..8191)
    int ch, a, b;
};

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
    std::map<Key, long long> tex_on;    // a held texture's key: the sample it may stop (live.tex_on)
    std::vector<Ev> events;
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
    };
    std::vector<Patch> patches;
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
    // channel's CC94, the band rows of each (part, position) from the siren
    // rows' pool, and each rank's data for a position, worked out at its
    // first press (live prepares it off the audio thread)
    std::vector<double> scan;
    std::map<int, int> cc94;
    std::map<std::tuple<int, int>, std::vector<int>> scan_row;
    std::deque<int> siren_free = [] {
        std::deque<int> d;
        for (int r = 33; r < 65; r++)       // (WIND_ROWS + 1 ...)
            d.push_back(r);
        return d;
    }();
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
        auto it = cc94.find(ch);
        if ((p.scanner & 2) && it != cc94.end()) {
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
        if (pi >= 0 && patches[pi].amp > 0.0)
            amp_dirty.insert(patches[pi].pid);
    }

    long long amp_ahead() const { return patches[cur].amp > 0.0 && !patches[cur].drums ? LIVE_AMP_LOOKAHEAD * cur_blk : 0; }

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
        std::vector<const std::vector<long> *> groups;
        size_t nslots = 0;
        for (auto &kv : S.live) {
            const Key &k = kv.first;
            if (std::get<0>(k) != apid || std::get<3>(k) == AMPK || std::get<3>(k) >= AMP_OLD0)
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
        if (p.amp_ref != 0.0) {
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
            jd.ref = p.amp_ref * chan_gain(ch) * (pow(10.0, level_db / 20.0) * swell) * S.headroom_d;
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
        if (pi >= 0 && patches[pi].cab)     // through the speaker, as the notes were (cabinet.gain)
            for (long q = 0; q < n; q++)
                a[q] *= nv_cab_gain(patches[pi].cab, f[q]);
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
        return LIVE_AMP_HOLD && pi >= 0 && !patches[pi].drums && patches[pi].amp > 0.0;
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
        p.amp = k ? k->amp_drive : 0.0;
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
    int cur = 0, transpose = 0;
    bool cur_reg = true;                            // the patch in use has the register

    int patch_for(int ch, int note) const
    {
        for (int i = (int)patches.size() - 1; i >= 0; i--) {
            const Patch &p = patches[i];
            if ((p.channel < 0 || p.channel == ch) && !((p.excl >> ch) & 1u) && p.lo <= note && note <= p.hi)
                return i;
        }
        return -1;
    }

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
    void tone_wheel(int ch, int v)
    {
        for (size_t pi = 0; pi < patches.size(); pi++) {
            const Patch &p = patches[pi];
            if (!(p.channel < 0 || p.channel == ch))
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
        // (_slur_cut: no native voice cuts the note it leaves -- slur_cuts_release)
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
        last_on[ch] = note;
        strike(ch, note, vel, n0, slur);
        glide_from = -1;
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
        let_go(ch, note, n0);
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
        if (patches[cur].organ) {           // a registered organ: its ranks drawn
            organ_strike(*T, ch, note, n0);
            return;
        }
        double scale = pow(10.0, level_db / 20.0) * swell * chan_gain(ch);
        if (patches[cur].touch)             // touch: the press over the template's (a voice without it: its own level)
            scale *= pow(vel / 127.0, 2.0) / std::max(pow(T->vel / 127.0, 2.0), 1e-9);
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
        if (!S.stamp_t(*T, key, n0, scale, ch, rate))
            return;                         // the slab full: this note does not sound
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
        }
        if (T->min_hold)
            tex_on[key] = n0 + T->min_hold; // a held texture: the least it plays
        if (!T->rel.empty())
            held_rel[Key(pid, ch, note, 0)] = std::make_pair(T, scale);     // its key-up rows, at the key-up
        long lj = S.live_find(key);
        std::vector<long> slots = lj >= 0 ? S.live[lj].second : std::vector<long>();
        if (cpan[ch] != 64 && !slots.empty())
            S.repan(slots, cpan[ch], 64, rate, true);
        if (soft[ch] && !slots.empty())
            S.soft_strings(slots, soft_drop, soft_top);
        double gl[3];                       // PORTAMENTO, stamped (live._glide)
        if (glide_from >= 0 && !slots.empty()
            && nv_tcache_glide(cache, program, glide_from + transpose, sn, porta_time[ch], gl))
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
        sound_stamp_note(patches[cur], ch, sn, slots);     // the channel's CC71-78 (live._sound_stamp)
        {                                   // a note struck under a bend, or the wheel up, joins them
            double sva, svr;
            snd_vib(patches[cur], ch, slots, &sva, &svr);
            double b = bend[ch], v2 = vib_mod[ch] + sva, r2 = (1.0 + mod_rate * vib_modw[ch]) * svr;
            if (b != 1.0 || v2 != 0.0 || r2 != 1.0)
                retune_v(slots, n0, b != 1.0, b, v2 != 0.0, v2, r2 != 1.0, r2);
        }
        if (reg_on && cur_reg && reg_note[note] && !lslots[0].empty())
            reg_strike(ch, note, n0, *T, lslots[0]);
        if (patches[cur].moog && !slots.empty())
            for (int ly = 0; ly < 2; ly++)          // each Messenger its own pedal
                if (!lslots[ly].empty())
                    mf104(patches[cur], ch, note, *T, key, lslots[ly], scale, n0, bend[ch], ly);
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
                if (S.live_find(c.first) >= 0 && !S.oneshot.count(c.first))
                    S.release(c.first, off + c.second);
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
        int kind;                           // 0 the stops, 1 a patch change
        std::vector<std::string> names;
        std::shared_ptr<Swap> swap;
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
        const MoogLayer *base = layer ? p.moog_b : p.moog;
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
                S.moog_retimbre(mo, L, rate, &rt);
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

    void sound_cc(int ch, int cc, int v, long long n0)
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
        if (patches[cur].leslie && !S.les.empty())    // onto the rotors, at their rates now
            S.leslie_arm(S.last_slots, R.f4[24].data(), R.f4[2].data(), R.lflip.empty() ? nullptr : R.lflip.data(),
                         n0, rotor_horn.rate, rotor_drum.rate, nullptr, lobe_of_t(R));
        if (patches[cur].scanner)                     // the scanner's selector, last (_scan_stamp)
            scan_stamp(R, ch, note, ri, n0, scale, std::vector<long>(S.last_slots));
    }

    // live._note_on's organ path: every rank drawn, in the stops' order (a
    // pipe organ has no touch: a key is open or shut)
    void organ_strike(const nv::live::Template &T, int ch, int note, long long n0)
    {
        note_touch[std::make_pair(ch, note)] = 1.0;
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
                         nullptr, 0.0, 0.0, J.cof.data()))
                continue;
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
                if (patch_for(d.first, d.second) != pi)
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
                mono_cut(ch, note, n0);
                mono_cur[ch] = back.first;
                glide_from = porta_on[ch] ? note : -1;
                last_on[ch] = back.first;
                strike(ch, back.first, back.second, n0, true);     // back to a key still held: a slur too
                glide_from = -1;
                return;
            }
            mono_cur[ch] = -1;                      // last key up: an ordinary release
        }
        int pi = patch_for(ch, note);
        Use u(*this, pi < 0 ? cur : pi);
        auto sq = sost.find(ch);
        if ((pedal_holds(ch, note) || (sq != sost.end() && sq->second.count(note))) && damper_pedal) {
            pedalled.insert(std::make_pair(ch, note));
            return;
        }
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
        if (patches[cur].amp > 0.0 && (kt == key_tone.end() || kt->second == patches[cur].cache) && !amp_holds(cur))
            S.release(Key(pid, -1, -1, AMPK), n0);  // the products end with their chord (a note of this tone's)
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
        // (a held texture lets go no sooner than its gate)
        long long at = n0;
        auto tx = tex_on.find(Key(pid, ch, note, -1));
        if (tx != tex_on.end()) {
            at = std::max(n0, tx->second);
            tex_on.erase(tx);
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
                     R.cof.empty() ? nullptr : R.cof.data()))
            return;
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
        return p.wheel_vib && !(p.amp > 0.0) && !(p.organ && p.organ->n_order) && !(p.wtrem > 0.0) && !p.clav
               && !p.leslie && !p.wheel_swell;
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
        double st = range_of(ch) * (double)wheel[ch] / 8192.0 + coarse[ch] + fine[ch] / 100.0 + 0.0 + 0.0 / 100.0;
        double ratio = pow(2.0, st / 12.0);
        double prev = bend[ch];
        if (ratio == prev)
            return;
        bend[ch] = ratio;
        if (leslie_on(ch))
            return;                         // (a rotor part's wheel is its half-moon: nothing bends)
        retune(sounding(ch), n0, ratio / prev);
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
            return;                                 // MTS: a gm2 part's
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
        if (l == 3 || l == 4 || !rpn_step_of(l, &step, &lo, &hi))
            return;                                 // (MTS's: a gm2 part's)
        double cur = l == 0 ? range_of(ch) : l == 1 ? fine[ch] : l == 2 ? coarse[ch]
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
        down.clear();
        pedalled.clear();
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
        for (auto &cv : RESET_CC)
            control(ch, cv[0], cv[1], n0);
        aftertouch(ch, 0);
        rpn_none[ch] = false;
        rpn_msb[ch] = rpn_lsb[ch] = 127;
        pw_armed[ch] = true;
    }

    // channel aftertouch: every key sounding on the channel (live's
    // _press_groups: the slab's keys in order, one tilt)
    void aftertouch(int ch, int v)
    {
        pressure[ch] = v / 127.0;
        press(sounding(ch), pressure[ch]);
    }

    void control(int ch, int cc, int v, long long n0)
    {
        if (cc == 94) {
            cc94[ch] = v;                           // the scanner's selector (_scan_stamp)
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
        } else if (cc == 1 && hammond_on(ch)) {
            // A HAMMOND'S MOD WHEEL, OR AN AMPLIFIED VOICE'S (live's
            // wheel_roles): with a valve, its drive (LIVE_DRIVE_STEPS over
            // the range) -- a guitar amp's own gain knob; else its swell pedal --
            // CC11's squared law on the part, the notes sounding rescaled,
            // floored at -80 dB
            for (const Patch &p : patches) {
                if (!(p.leslie || p.wheel_swell || p.amp > 0.0) || !(p.channel < 0 || p.channel == ch))
                    continue;
                if (p.amp > 0.0) {
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
        } else if (cc == 1 && wheel_trem_on(ch)) {
            wheel_tremolo(ch, v);
        } else if (cc == 1 && organ_on(ch)) {
            // AN ORGAN'S MOD WHEEL IS ITS CRESCENDO PEDAL (live's 'crescendo' role)
            for (size_t pi = 0; pi < patches.size(); pi++)
                if (patches[pi].organ && patches[pi].organ->n_order && (patches[pi].channel < 0 || patches[pi].channel == ch))
                    crescendo((int)pi, v, n0);
        } else if (cc == 1 && detune_wheel) {
            static const int steps[3] = {0, 64, 127};       // live.DETUNE_STEPS: min(), the first of a tie
            int best = steps[0];
            for (int st : steps)
                if (abs(st - v) < abs(best - v))
                    best = st;
            speed = best;
        }
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
        if (cc == 1)                            // A CLAVINET's TONE ROCKERS (live's 'tone' role)
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
        if (cc == 1 && !key_tone.empty()) {     // ...and the tones held from before a program change
            n0_wheel = n0;
            tone_wheel(ch, v);
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
        long nact = (long)gidx.size();
        if (nact > D.n)
            D.make(std::max(nact, 2 * D.n), D.size);
        long mg = (blk % 128 == 0 && blk / 128 <= 64) ? 128 : blk;     // moog_grid
        long kb0 = (long)(n0 / mg);
        gnon.resize(S.cap);
        gnoff.resize(S.cap);
        for (long q = 0; q < S.cap; q++) {
            gnon[q] = (long)S.i8[0][q];
            gnoff[q] = (long)S.i8[1][q];
        }
        void *vb = gp.vb;
        bool damp = false;
        for (long q : gidx)
            damp = damp || S.dk[q] >= 0;
        if (damp && gp.vbd && gp.vds) {
            vb = gp.vbd;
            ((nv_vdamp_fn)gp.vds)(S.dk.data(), S.dg.data(), DM.data(), DMO.data(), DMB.data(), DMN.data());
        }
        const std::vector<float> *F4 = S.f4.data(), *F4N = S.f4n.data();
        int counts[2] = {0, 0};
        auto t0 = std::chrono::steady_clock::now();
        while (true) {
            int r = ((nv_vblock_fn)vb)(
                (long)n0, (int)blk, 1, (int)S.cap, S.f8[0].data(), S.f8[1].data(), S.f8[2].data(), F4[0].data(),
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
        bool g = hi >= 0 && gp.vb && !gpu_off && act >= gp.gpu_min && frames == blk && n0 % frames == 0;
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
                S.aLp = S.f4[0];            // knobs_advance
                S.aRp = S.f4[1];
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
            ~Advance() { S.aLp = S.f4[0]; S.aRp = S.f4[1]; S.knobs_advance(); }
        } advance{S};
        long hi = -1;
        for (long q = 0; q < S.cap; q++)
            if (S.busy[q])
                hi = q;
        if (hi < 0)
            return;
        hi += 1;
        // THE GPU (live.GpuRenderer), when given one and the block has rows
        // enough for it (gpu_min); the CPU below otherwise
        long act = 0;
        for (long q = 0; q < hi; q++)
            act += S.busy[q] != 0;
        on_gpu = gp.vb && !gpu_off && act >= gp.gpu_min && frames == blk && n0 % frames == 0;
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
        std::vector<long> xr, keep, dm;
        for (long q = 0; q < hi; q++)
            (S.dk[q] >= 0 && sd ? dm : fast(q) ? xr : keep).push_back(q);
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
                // synth_voice_damp: synth_voice's arguments, then the tracks
                ((nv_damp_fn)fn)(VOICE_ARGS, dkr.data(), dgr.data(), DM.data(), DMO.data(), DMB.data(), DMN.data());
            } else {
                ((nv_voice_fn)fn)(VOICE_ARGS);
            }
        };
        if (!dm.empty()) {
            call(sv, keep.data(), (long)keep.size(), false, false);
            call(sx, xr.data(), (long)xr.size(), false, false);
            call(sd, dm.data(), (long)dm.size(), false, true);
        } else if (!xr.empty()) {
            call(sv, keep.data(), (long)keep.size(), false, false);
            call(sx, xr.data(), (long)xr.size(), false, false);
        } else {
            call(sv, nullptr, hi, true, false);
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
        bool uniform = true;
        for (int c = 1; c < 256 && uniform; c++)
            uniform = S.send[c] == S.send[0];
        bool snd = room && room_on && !uniform;
        oSL.assign(frames, 0.0f);
        oSR.assign(frames, 0.0f);
        render(n0, frames, L, R, snd ? oSL.data() : nullptr, snd ? oSR.data() : nullptr, sv, sx, sd, blk,
               master_gain);
        if (room && room_on) {
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
            oWL.resize(frames);
            oWR.resize(frames);
            room->process(sl, sr, oWL.data(), oWR.data());
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
                S.mo_uL[q] = S.mo_uR[q] = 0.0f;
            }
            shed_mo.emplace_back(n + 2 * cur_blk, qm);     // (live sets blockrender.BLK to its block)
        }
        return k;
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
        if (!(o[1] > 0.95 * budget_ms))
            return 0;
        long k = shed(n, 0.1);
        if (k) {
            partials_shed += k;
            ms_n = 0;
        }
        return k;
    }

    // live's callback for one block: its events, the sweep, the reap
    void block(long long n0, long long blk)
    {
        cur_blk = blk;
        if (!wind_st.empty() || !wind_spent.empty())    // the organs' chests, before the block's events (live's callback)
            wind_block(n0, blk);
        if (!amp_retired.empty())
            amp_retire(n0);
        std::vector<Ev> evs;
        evs.swap(events);
        for (const Ev &e : evs) {
            if (e.type == 0)
                note_on(e.ch, e.a, e.b, n0);
            else if (e.type == 1)
                note_off(e.ch, e.a, n0);
            else if (e.type == 3)
                aftertouch(e.ch, e.a);
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
        if (!amp_dirty.empty() || amp_has_out || !amp_fine_results.empty() || amp_async || !amp_chg.empty()
            || !S.rel_log.empty())
            amp_pump(n0);                       // the valve (live's _amp_pump)
        std::vector<Key> sw;
        for (auto &kv : S.live) {
            std::pair<int, int> ck((int)std::get<1>(kv.first), (int)std::get<2>(kv.first));
            auto sq = sost.find(ck.first);
            if (!down.count(ck) && !pedalled.count(ck) && !S.oneshot.count(kv.first)
                && !(sq != sost.end() && sq->second.count(ck.second)) && std::get<3>(kv.first) != AMPK
                && std::get<3>(kv.first) < AMP_OLD0 && std::get<3>(kv.first) > MFK0)
                sw.push_back(kv.first);         // (not a valve's products, an old tone's, a repeat's: not a note)
        }
        for (auto &k : sw)
            S.release(k, n0);
        damp_block(n0, blk);
        if (!mf_groups.empty())
            mf104_reap();
        S.reap(n0, blk);
        if (!scan_row.empty())                  // the scanners' band rows (live's _scanner_block)
            scanner_block(n0, blk);
        tremolo_block(n0);                      // (live's swing, after the reap)
        leslie_block(n0, blk);                  // ...then the rotors'
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
void nv_part_program(void *h, int program)
{
    nv::slab::Part *P = (nv::slab::Part *)h;
    P->patches[0].program = program;
    P->program = program;
    nv::slab::Part::organ_start(P->patches[0], nv_tcache_organ(P->patches[0].cache, program));
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
    if (!drums)
        nv::slab::Part::organ_start(p, nv_tcache_organ(cache, program));
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
    nv::slab::Part::Patch &p = ((nv::slab::Part *)h)->patches[i];
    p.channel = channel;
    p.excl = excl;
    p.lo = lo;
    p.hi = hi;
    p.transpose = transpose;
}

void nv_part_free(void *h) { delete (nv::slab::Part *)h; }

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

// the kernel library's Moog row functions (synthkernel.c moog_pitch_cells,
// moog_shape_rows), as the caller has it loaded
void nv_part_moog_kernel(void *h, void *pcells, void *srows)
{
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

// THE PANEL'S: a global set between blocks -- 0 headroom (dB), 1 the
// pressure's lift (dB), 2 the limiter's knee, 3 the wheel's range, 4 the mod
// range (cents), 5 the GPU on (1) or off, 6 the room's tail on or off
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
