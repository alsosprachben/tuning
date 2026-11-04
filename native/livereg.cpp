// livereg.cpp -- the native engine's LIVE REGISTER: register.LiveChannel for
// a piano (one row of strings) or a harpsichord (its choirs, their bridges
// and the buff: no courses or key bridges), bit for
// bit with the Python, whose arithmetic is libm's and spelled out (register
// _xexp, _xabs, _xcexp, _xcmul, _xcmulr, _xcsum) and whose free part is
// registercore.c's -- which this calls, the same code under the same flags.
//
// A channel: its string bank (native/strings.c's modes) and the class's
// register constants. Jobs in, as live's worker takes them: a strike (its
// key, the sample it fell at, its stamped direct rows, the keys free), a
// release (a strike's damper fell: its forced part handed to the free
// modes), a damp (these keys' strings at rest), the felt (the pedal in the
// band: these keys' extra rates). A strike, release or felt answers with the
// modes whose stamped row drifted and their state at the job's sample; a
// strike with its forced rows too.

#include <algorithm>
#include <cmath>
#include <complex>
#include <map>
#include <set>
#include <vector>

#include "nv.h"

extern "C" {
// registercore.c, linked in as its own object (complex arrays as double pairs)
void free_part(int n, const void *c, double Wi, const double *bi, const double *Wm, const double *am, double tb,
               double tau, double cut, double need, void *freep, void *forced);
}

namespace nv {
namespace reg {
// register.cpp's: CPython's hash((a, b)) of two ints, numpy's knock phases
long long py_tuple_hash2(long long a, long long b);
std::vector<double> knock_phase(long long seed, int n);
}  // namespace reg

namespace lreg {

typedef std::complex<double> cplx;
static const double SPLIT = 1e-2;                    // register.SPLIT
static const double ROWS_OVER = 1.0;                 // register.ROWS_OVER
static const double TBEND_CUT_SCALE = 1048576.0;     // register.TBEND_CUT_SCALE
static const long long KNOCK_SALT = 0x4C495645;      // register.LIVE_KNOCK_SALT
static const double TAU = 2.0 * M_PI;

static double pymax(double a, double b) { return b > a ? b : a; }
// np.maximum(x, y) of two non-NaN values: x where x >= y
static double npmax(double x, double y) { return x >= y ? x : y; }

// _xcexp: exp(re) * (cos im, sin im)
static cplx xcexp(double re, double im)
{
    double e = exp(re);
    return cplx(e * cos(im), e * sin(im));
}

// _xcmul: the four products and two sums, each rounded
static cplx xcmul(cplx a, cplx b)
{
    return cplx(a.real() * b.real() - a.imag() * b.imag(), a.real() * b.imag() + a.imag() * b.real());
}

// _xcmulr: z * r, r promoted to (r, 0)
static cplx xcmulr(cplx z, double r)
{
    return cplx(z.real() * r - z.imag() * 0.0, z.real() * 0.0 + z.imag() * r);
}

static double xabs(cplx z) { return hypot(z.real(), z.imag()); }

static bool nonzero(cplx z) { return z.real() != 0.0 || z.imag() != 0.0; }

// CPython 3.12's complex / float: the float promoted, _Py_c_quot
static cplx py_quot_real(cplx a, double br)
{
    const double bi = 0.0;
    double ratio = bi / br;
    double denom = br + bi * ratio;
    return cplx((a.real() + a.imag() * ratio) / denom, (a.imag() - a.real() * ratio) / denom);
}

// numpy's pairwise sum of a contiguous float64 array (np.sum)
static double pairwise(const double *a, long n)
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
    return pairwise(a, n2) + pairwise(a + n2, n - n2);
}

// _glide_phase_x: one row's glide at one time
static double glide_phase(double Wi, double tb, double tau, double cut, double t)
{
    double ct = cut < 0 ? -cut * TBEND_CUT_SCALE : cut;
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

// a strike's direct rows, column by column (_reg_pump's drv)
enum { D_om, D_p0, D_delL, D_aM, D_non, D_logr, D_logrA, D_aft, D_sus, D_tbav, D_tau, D_tcut, ND };

struct Keep {
    std::vector<int> j;
    std::vector<cplx> fo;
    double Wi;
    std::vector<double> bj;
    double theta, n_i, tb, ta, cu;
};

struct Forced {
    long slot;
    double wgt, beta;
    cplx val;
};

struct Channel {
    int M = 0;
    double sr, kappa, knock, fall, fl;
    int top;
    std::vector<long> key, string;
    std::vector<double> f, alpha, w, W, dw;
    // the choirs (Strings.choir_bridges, cross, buffs): each mode's bridge
    std::vector<long> choir_bridges = std::vector<long>(1, 0), bridge;
    double cross = 1.0;
    std::vector<std::pair<int, int>> buffs;     // (buffed, plain)
    std::map<int, std::vector<int>> keyidx;
    std::vector<cplx> Az, Rz;
    std::vector<double> nref, rref, krate, Rk;
    std::vector<char> stamped;
    std::map<long long, std::vector<Keep>> held;
    double loud = 0.0;
    // the last job's answer
    std::vector<long> idx;
    std::vector<cplx> z;
    std::vector<Forced> forced;

    double floor_() const { return fl * pymax(loud, 1e-30); }

    std::vector<char> mask(const int *keys, int n, int except) const
    {
        std::vector<char> m(M, 0);
        for (int q = 0; q < n; q++) {
            if (keys[q] == except)
                continue;
            auto it = keyidx.find(keys[q]);
            if (it != keyidx.end())
                for (int i : it->second)
                    m[i] = 1;
        }
        return m;
    }

    // Az carried to `at` and the kick added, where the kick is
    void carry(const std::vector<cplx> &add, double at, std::vector<char> &touched)
    {
        touched.assign(M, 0);
        for (int i = 0; i < M; i++) {
            if (!nonzero(add[i]))
                continue;
            touched[i] = 1;
            double g = exp(-(alpha[i] + krate[i]) * npmax(at - nref[i], 0.0) / sr);
            cplx a = xcmulr(Az[i], g);
            Az[i] = cplx(a.real() + add[i].real(), a.imag() + add[i].imag());
            nref[i] = at;
        }
    }

    // _settle: the touched modes whose stamped row has drifted (all, forced)
    void settle(const std::vector<char> &touched, double at, bool force)
    {
        idx.clear();
        z.clear();
        double floor = floor_();
        for (int i = 0; i < M; i++) {
            if (!touched[i])
                continue;
            cplx tz = Az[i];
            cplx rz = 0.0;
            if (stamped[i])
                rz = xcmulr(Rz[i], exp(-(alpha[i] + Rk[i]) * npmax(at - rref[i], 0.0) / sr));
            bool go = xabs(cplx(tz.real() - rz.real(), tz.imag() - rz.imag())) > SPLIT * npmax(xabs(tz), floor);
            if (!(go || force))
                continue;
            idx.push_back(i);
            z.push_back(tz);
        }
        for (size_t q = 0; q < idx.size(); q++) {
            long i = idx[q];
            Rz[i] = z[q]; rref[i] = at; Rk[i] = krate[i];
            stamped[i] = xabs(z[q]) >= floor;
        }
    }

    void strike(long long sid, int k, double at, int R, const double *const *drv, const long *slot,
                const int *free_keys, int nfree, const int *plucked = nullptr, int nplucked = -1,
                const long *rchoir = nullptr)
    {
        forced.clear();
        std::vector<char> free = mask(free_keys, nfree, k);
        auto in_plucked = [&](long c) {
            for (int q = 0; q < nplucked; q++)
                if (plucked[q] == c)
                    return true;
            return false;
        };
        if (nplucked >= 0) {
            // its own key's choirs but the plucked ones, while it is held
            bool held = false;
            for (int q = 0; q < nfree; q++)
                held = held || free_keys[q] == k;
            auto it = keyidx.find(k);
            if (held && it != keyidx.end())
                for (int i : it->second)
                    if (!in_plucked(string[i] / 16))
                        free[i] = 1;
        }
        if (!buffs.empty()) {               // a buff's string, or its plain one (Strings.free_choirs)
            std::vector<char> okc(choir_bridges.size(), 1);
            for (auto &bp : buffs) {
                if (nplucked >= 0 && in_plucked(bp.first))
                    okc[bp.second] = 0;
                else
                    okc[bp.first] = 0;
            }
            for (int i = 0; i < M; i++)
                if (!okc[string[i] / 16])
                    free[i] = 0;
        }
        double mx = 0.0;
        for (int r = 0; r < R; r++)
            if (r == 0 || drv[D_aM][r] > mx)
                mx = drv[D_aM][r];
        if (R)
            loud = pymax(loud, mx);
        double floor = floor_();
        std::vector<cplx> add(M, 0.0);
        std::vector<Keep> keep;
        std::vector<int> fi;
        for (int i = 0; i < M; i++)
            if (free[i])
                fi.push_back(i);
        std::vector<double> fW(fi.size());
        for (size_t q = 0; q < fi.size(); q++)
            fW[q] = W[fi[q]];
        if (!fi.empty() && kappa > 0) {
            for (int r = 0; r < R; r++) {
                double a_i = drv[D_aM][r];
                if (a_i < floor)
                    continue;
                double om_i = drv[D_om][r], Wi = om_i * sr;
                double n_i = drv[D_non][r];
                double theta = om_i * n_i + drv[D_p0][r] + om_i * drv[D_delL][r];
                double tb = drv[D_tbav][r], ta = drv[D_tau][r], cu = drv[D_tcut][r];
                double aft = drv[D_aft][r], sus = drv[D_sus][r];
                // register.stages
                double sw[3], sb[3];
                int ns = 0;
                if ((1.0 - sus) * (1.0 - aft) > 0) { sw[ns] = (1.0 - sus) * (1.0 - aft); sb[ns++] = drv[D_logr][r]; }
                if ((1.0 - sus) * aft > 0) { sw[ns] = (1.0 - sus) * aft; sb[ns++] = drv[D_logrA][r]; }
                if (sus > 0) { sw[ns] = sus; sb[ns++] = 0.0; }
                for (int s = 0; s < ns; s++) {
                    double wgt = sw[s], beta = sb[s];
                    double cmax = kappa * a_i * wgt;
                    if (cmax <= 0)
                        continue;
                    double reach = cmax / (floor * SPLIT);
                    long lo = std::lower_bound(fW.begin(), fW.end(), Wi - reach) - fW.begin();
                    long hi = std::lower_bound(fW.begin(), fW.end(), Wi + reach) - fW.begin();
                    if (hi <= lo)
                        continue;
                    long n = hi - lo;
                    Keep kp;
                    kp.j.assign(fi.begin() + lo, fi.begin() + hi);
                    std::vector<double> Wm(n), am(n), bj(n);
                    std::vector<char> close(n);
                    std::vector<cplx> c(n), fr(n), fo(n);
                    double kw = kappa * wgt;
                    for (long q = 0; q < n; q++) {
                        int j = kp.j[q];
                        Wm[q] = W[j]; am[q] = alpha[j];
                        double wj = w[j];                             // Strings.coupling: the board's...
                        if (rchoir)                                   // ...across bridges at cross
                            wj = wj * (bridge[j] == choir_bridges[rchoir[r]] ? 1.0 : cross);
                        double thr = kw * wj / ROWS_OVER;             // _coincident_x
                        close[q] = xabs(cplx(am[q] - beta, Wi - Wm[q])) < thr;
                        bj[q] = close[q] ? npmax(beta, am[q]) + thr : beta;
                        c[q] = cplx(cmax * wj, 0.0);
                    }
                    free_part((int)n, c.data(), Wi, bj.data(), Wm.data(), am.data(), tb, ta, cu, floor * SPLIT,
                              fr.data(), fo.data());
                    std::vector<double> sre, sim;
                    for (long q = 0; q < n; q++) {
                        cplx e = xcexp(am[q] * (n_i - at) / sr, theta - Wm[q] * n_i / sr);
                        cplx m = xcmul(fr[q], e);
                        int j = kp.j[q];
                        add[j] = cplx(add[j].real() + m.real(), add[j].imag() + m.imag());
                        if (!close[q]) {
                            sre.push_back(fo[q].real());
                            sim.push_back(fo[q].imag());
                        }
                    }
                    // as Channel.strike: a coincident pair's forced part its own row
                    cplx F = sre.empty() ? cplx(0.0, 0.0)
                                         : cplx(pairwise(sre.data(), (long)sre.size()),
                                                pairwise(sim.data(), (long)sim.size()));
                    if (xabs(F) > floor * SPLIT)
                        forced.push_back(Forced{slot[r], wgt, beta, py_quot_real(F, a_i)});
                    for (long q = 0; q < n; q++)
                        if (close[q] && xabs(fo[q]) > floor * SPLIT)
                            forced.push_back(Forced{slot[r], wgt, bj[q], py_quot_real(fo[q], a_i)});
                    kp.fo = fo;
                    kp.Wi = Wi;
                    kp.bj = bj;
                    kp.theta = theta; kp.n_i = n_i; kp.tb = tb; kp.ta = ta; kp.cu = cu;
                    keep.push_back(std::move(kp));
                }
            }
        }
        // THE KNOCK: every free string kicked, falling `fall` dB a semitone
        if (knock > 0 && !fi.empty()) {
            double ka = knock * (R ? mx : 0.0);
            std::vector<double> ph = nv::reg::knock_phase(nv::reg::py_tuple_hash2(KNOCK_SALT, sid), (int)fi.size());
            for (size_t q = 0; q < fi.size(); q++) {
                int i = fi[q];
                double dk = (double)std::labs(key[i] - k);
                double amp = ka * w[i] * pow(10.0, -fall * dk / 20.0);
                cplx m = xcmulr(xcexp(0.0, ph[q]), amp);
                add[i] = cplx(add[i].real() + m.real(), add[i].imag() + m.imag());
            }
        }
        held[sid] = std::move(keep);
        std::vector<char> touched;
        carry(add, at, touched);
        settle(touched, at, false);
    }

    void release(long long sid, double at, const int *free_keys, int nfree)
    {
        forced.clear();
        idx.clear();
        z.clear();
        auto it = held.find(sid);
        if (it == held.end())
            return;
        std::vector<Keep> keep = std::move(it->second);
        held.erase(it);
        if (keep.empty())
            return;
        std::vector<char> free = mask(free_keys, nfree, -1);
        std::vector<cplx> add(M, 0.0);
        for (const Keep &kp : keep) {
            double tq = (at - kp.n_i) / sr;
            double gq = glide_phase(kp.Wi, kp.tb, kp.ta, kp.cu, tq);
            double th = kp.theta + kp.Wi * tq + gq;
            for (size_t q = 0; q < kp.j.size(); q++) {
                int j = kp.j[q];
                cplx m = xcmul(kp.fo[q], xcexp(-(kp.bj[q] * tq), th - W[j] * at / sr));
                add[j] = cplx(add[j].real() + m.real(), add[j].imag() + m.imag());
            }
        }
        for (int i = 0; i < M; i++)
            if (!free[i])
                add[i] = 0.0;
        std::vector<char> touched;
        carry(add, at, touched);
        settle(touched, at, false);
    }

    void damp(const int *keys, int n)
    {
        std::vector<char> m = mask(keys, n, -1);
        for (int i = 0; i < M; i++)
            if (m[i]) {
                Az[i] = 0.0; Rz[i] = 0.0; stamped[i] = 0;
            }
    }

    void felt(double at, const int *keys, const double *rates, int n)
    {
        forced.clear();
        std::vector<double> nw = krate;
        for (int q = 0; q < n; q++) {
            auto it = keyidx.find(keys[q]);
            if (it != keyidx.end())
                for (int i : it->second)
                    nw[i] = rates[q] * dw[i];
        }
        std::vector<char> touched(M, 0);
        for (int i = 0; i < M; i++) {
            if (nw[i] == krate[i] || !nonzero(Az[i]))
                continue;
            Az[i] = xcmulr(Az[i], exp(-(alpha[i] + krate[i]) * npmax(at - nref[i], 0.0) / sr));
            nref[i] = at;
            touched[i] = 1;
        }
        krate = nw;
        settle(touched, at, true);
    }
};

}  // namespace lreg
}  // namespace nv

extern "C" {

// A live register channel: its string bank (modes, M of them, as nv_strings
// sorts them) and the class's constants (kappa = register_gain * scale,
// knock = register_knock_gain * scale, fall, the floor, damper_top, the
// felt's BETA).
void *nv_lreg_new(const StringMode *modes, int M, double sr, double kappa, double knock, double fall, double fl,
                  int top, double beta)
{
    using namespace nv::lreg;
    Channel *C = new Channel();
    C->M = M; C->sr = sr; C->kappa = kappa; C->knock = knock; C->fall = fall; C->fl = fl; C->top = top;
    for (int i = 0; i < M; i++) {
        const StringMode &q = modes[i];
        C->key.push_back((long)q.key); C->string.push_back((long)q.string);
        C->f.push_back(q.f); C->alpha.push_back(q.alpha); C->w.push_back(q.w);
        C->W.push_back(TAU * q.f);
        C->keyidx[(int)q.key].push_back(i);
        // the felt's weight: (max(f, 1e-6) / the key's f0) ** BETA
        double f0 = 440.0 * pow(2.0, ((double)q.key - 69.0) / 12.0);
        C->dw.push_back(pow(npmax(q.f, 1e-6) / f0, beta));
    }
    C->bridge.assign(M, 0);
    C->Az.assign(M, 0.0); C->Rz.assign(M, 0.0);
    C->nref.assign(M, 0.0); C->rref.assign(M, 0.0);
    C->krate.assign(M, 0.0); C->Rk.assign(M, 0.0);
    C->stamped.assign(M, 0);
    return C;
}

// A strike: its id, key, sample, and R direct rows (cols: ND columns of R,
// in drv's order om p0 delL aM non logr logrA aft sus tbav tau tcut; slot
// each row's slot), with these keys' strings free. The answer: nv_lreg_answer.
int nv_lreg_strike(void *h, long long sid, int key, double at, int R, const double *cols, const long *slot,
                   const int *free_keys, int nfree)
{
    using namespace nv::lreg;
    Channel *C = (Channel *)h;
    const double *drv[ND];
    for (int c = 0; c < ND; c++)
        drv[c] = cols + (long)c * R;
    C->strike(sid, key, at, R, drv, slot, free_keys, nfree);
    return (int)C->idx.size();
}

// ...a pluck: the choirs it plucked (nplucked < 0: None) and each row's choir (NULL: none)
int nv_lreg_pluck(void *h, long long sid, int key, double at, int R, const double *cols, const long *slot,
                  const int *free_keys, int nfree, const int *plucked, int nplucked, const long *rchoir)
{
    using namespace nv::lreg;
    Channel *C = (Channel *)h;
    const double *drv[ND];
    for (int c = 0; c < ND; c++)
        drv[c] = cols + (long)c * R;
    C->strike(sid, key, at, R, drv, slot, free_keys, nfree, plucked, nplucked, rchoir);
    return (int)C->idx.size();
}

// A harpsichord's choirs (register.Strings'): each choir's bridge, the
// coupling across bridges, and the buffs (buffed, plain) pairs
void nv_lreg_choirs(void *h, int nchoir, const long *bridges, double cross, int nbuff, const int *buffs)
{
    nv::lreg::Channel *C = (nv::lreg::Channel *)h;
    C->choir_bridges.assign(bridges, bridges + nchoir);
    C->cross = cross;
    C->buffs.clear();
    for (int q = 0; q < nbuff; q++)
        C->buffs.push_back(std::make_pair(buffs[2 * q], buffs[2 * q + 1]));
    C->bridge.assign(C->M, 0);
    for (int i = 0; i < C->M; i++)
        C->bridge[i] = C->choir_bridges[C->string[i] / 16];
}

int nv_lreg_release(void *h, long long sid, double at, const int *free_keys, int nfree)
{
    nv::lreg::Channel *C = (nv::lreg::Channel *)h;
    C->release(sid, at, free_keys, nfree);
    return (int)C->idx.size();
}

void nv_lreg_damp(void *h, const int *keys, int n) { ((nv::lreg::Channel *)h)->damp(keys, n); }

int nv_lreg_felt(void *h, double at, const int *keys, const double *rates, int n)
{
    nv::lreg::Channel *C = (nv::lreg::Channel *)h;
    C->felt(at, keys, rates, n);
    return (int)C->idx.size();
}

// The last job's answer: its modes and their state (complex as pairs), the
// floor it was made at; returns the forced rows' count.
int nv_lreg_answer(void *h, long *idx, double *z, double *floor_)
{
    nv::lreg::Channel *C = (nv::lreg::Channel *)h;
    for (size_t q = 0; q < C->idx.size(); q++) {
        idx[q] = C->idx[q];
        z[2 * q] = C->z[q].real();
        z[2 * q + 1] = C->z[q].imag();
    }
    *floor_ = C->floor_();
    return (int)C->forced.size();
}

// The last strike's forced rows: (slot, weight, decay, value re the driver)
void nv_lreg_forced(void *h, long *slot, double *wgt, double *beta, double *val)
{
    nv::lreg::Channel *C = (nv::lreg::Channel *)h;
    for (size_t q = 0; q < C->forced.size(); q++) {
        const nv::lreg::Forced &f = C->forced[q];
        slot[q] = f.slot; wgt[q] = f.wgt; beta[q] = f.beta;
        val[2 * q] = f.val.real(); val[2 * q + 1] = f.val.imag();
    }
}

void nv_lreg_free(void *h) { delete (nv::lreg::Channel *)h; }

}  // extern "C"
