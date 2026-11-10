// register.cpp -- the native engine's FREE-STRING REGISTER: register.Channel
// for a piano (one row of strings) or a harpsichord (its choirs, their
// bridges and the buff: no courses or key bridges),
// bit for bit with the Python whose array math is libm's (register._xexp,
// _xpow, _xabs) and whose heavy loops are registercore.c's -- which this
// calls, the same code under the same flags.
//
// A channel: its string bank (native/strings.c's modes), the class's register
// constants, the pedal (a switch's spans, or a half-pedalled channel's spans
// and felt per key). Fed each strike (its key, onset, key-up, velocity and
// its direct rows as the table holds them), then finished: block by block,
// the strikes kick the free strings (strike_drive), dampers hand over
// (bridges), the felt moves, every mode's state is carried and a row written
// where it drifted (free_rows). Its rows come out as register.expand puts
// them: the free and bridge rows by seq, then the forced rows.

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <complex>
#include <cstring>
#include <limits>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "pycompat.h"

extern "C" {
// registercore.c, linked in as its own object (register._load_core's flags) (complex arrays as double pairs)
int strike_drive(int R, const double *aM, const double *om, const double *non, const double *p0,
                 const double *delL, const double *noff, const double *re_, const double *tbav,
                 const double *tau, const double *tcut, const double *aft, const double *sus,
                 const double *logr, const double *logrA, const long *choir,
                 int nf, const long *fi, const double *W, const double *alpha, const double *w,
                 const long *bridge, const long *mkey, const long *choir_bridges, double cross,
                 long keybridge, long partner, double partner_k,
                 double kappa, double floor_, double split, double sr, double b,
                 void *add, void *xfer, int cap, int *f_r, double *f_beta, void *f_val,
                 double *last_noff, double *last_re);
void dcum(int n, const long *key, const double *t, const long *off, const double *bk, const double *rate,
          const double *D, double sr, double *out);
int free_rows(int ngo, const long *go, const char *free_now, const double *drate,
              const void *Az, const double *am, const double *dw, const double *W,
              const double *f, const double *hl, const double *hr, const double *dl, const double *dr,
              const double *px, const long *string, const long *key,
              long *rrow, char *has, double *r_b, double *r_nfloor, double *r_closed,
              void *Rz, double *rref, double *r_lr,
              double floor_, double b, double sr, double blk, long src,
              long n, long *seq,
              double *c_om, double *c_p0, double *c_p0R, double *c_aL, double *c_aR, double *c_aM,
              double *c_nf, double *c_non, double *c_fa, double *c_logr, double *c_delL,
              double *c_delR, double *c_px, long *c_pl, long *c_mode, long *c_key, double *c_b,
              double *c_nfloor, double *c_closed, long *c_seq, long *c_src,
              long *open_ids, long nopen);
}

namespace nv {
namespace reg {

typedef std::complex<double> cplx;
static const double INF = std::numeric_limits<double>::infinity();
static const double SPLIT = 1e-2;               // register.SPLIT
static const double TAU = 2.0 * M_PI;           // register.TAU (2.0 * math.pi)

// blockrender.EMIT_COLS, the rows' layout in and out
enum {
    C_om, C_p0, C_p0R, C_aL, C_aR, C_aM, C_mch, C_px, C_pz, C_az, C_dr, C_nf, C_non, C_noff, C_fa, C_re, C_ch,
    C_logr, C_logrA, C_aft, C_sus, C_cv, C_cc, C_crl, C_sj, C_csc, C_cbw, C_tbav, C_tau, C_tcut, C_gb, C_gt,
    C_gc, C_vd, C_vr, C_vp, C_vdl, C_delL, C_delR, C_gr, C_cr, C_br, C_pl, C_fx, C_mk, C_rdl, C_fmw, C_nfr,
    C_fmp, C_fmpR, NC
};

static double pymin(double a, double b) { return b < a ? b : a; }
static double pymax(double a, double b) { return b > a ? b : a; }

// Python's float floor division, x // y (CPython float_floor_div)
static double pyfloordiv(double vx, double wx)
{
    double mod = fmod(vx, wx);
    double div = (vx - mod) / wx;
    if (mod != 0.0) {
        if ((wx < 0) != (mod < 0))
            div -= 1.0;
    }
    double fd;
    if (div != 0.0) {
        fd = floor(div);
        if (div - fd > 0.5)
            fd += 1.0;
    } else {
        fd = copysign(0.0, vx / wx);
    }
    return fd;
}

// numpy's complex * real, the real promoted to complex (x + 0j)
static cplx cmul_r(cplx z, double r)
{
    return cplx(z.real() * r - z.imag() * 0.0, z.real() * 0.0 + z.imag() * r);
}

// numpy's real * complex, the real promoted
static cplx rmul_c(double r, cplx z)
{
    return cplx(r * z.real() - 0.0 * z.imag(), r * z.imag() + 0.0 * z.real());
}

// CPython's hash((a, b)) of two ints (3.8+'s xxHash-style tuple hash)
long long py_tuple_hash2(long long a, long long b)        // (livereg.cpp's too)
{
    const uint64_t P1 = 11400714785074694791ULL, P2 = 14029467366897019727ULL, P5 = 2870177450012600261ULL;
    auto ih = [](long long v) -> uint64_t {        // hash(int) for |v| < 2**61 - 1
        long long h = v == -1 ? -2 : v;
        return (uint64_t)h;
    };
    uint64_t acc = P5;
    for (long long v : {a, b}) {
        acc += ih(v) * P2;
        acc = (acc << 31) | (acc >> 33);
        acc *= P1;
    }
    acc += 2ULL ^ (P5 ^ 3527539ULL);
    if (acc == (uint64_t)-1)
        return 1546275796;
    return (long long)acc;
}

// numpy's RandomState(seed).uniform(0, TAU, n): MT19937 by init_genrand
/* numpy.interp at one x (tone.c's np_interp) */
double np_interp(double x, const double *xp, const double *fp, int n)
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

std::vector<double> knock_phase(long long seed, int n)      // (livereg.cpp's too)
{
    PyRandom r;
    uint32_t s = (uint32_t)(seed & 0x7fffffff);
    r.mt[0] = s;
    for (int i = 1; i < 624; i++)
        r.mt[i] = (uint32_t)(1812433253u * (r.mt[i - 1] ^ (r.mt[i - 1] >> 30)) + (uint32_t)i);
    r.i = 624;
    std::vector<double> out(n);
    for (int i = 0; i < n; i++) {
        uint32_t a = pyr_genrand(&r) >> 5, b = pyr_genrand(&r) >> 6;
        out[i] = 0.0 + TAU * ((a * 67108864.0 + b) * (1.0 / 9007199254740992.0));
    }
    return out;
}

typedef std::pair<double, double> Span;

static std::vector<Span> merge_spans(std::vector<Span> s)
{
    std::sort(s.begin(), s.end());
    std::vector<Span> out;
    for (const Span &x : s) {
        if (!out.empty() && x.first <= out.back().second)
            out.back().second = pymax(out.back().second, x.second);
        else
            out.push_back(x);
    }
    return out;
}

struct Forced {
    double row[NC];
    long long seq;
};

struct Bridge {
    std::vector<long long> seqs;
    std::vector<int> cand;
    std::vector<cplx> vals;
    double n0, re0;
    long long pb;
};

struct Strike {
    int key;
    std::vector<std::vector<double>> drv;   // [column][row], the direct rows
    bool has_plucked = false;               // the choirs it plucked (None: every string of the key)
    std::vector<int> plucked;
    std::vector<long> choir;                // each direct row's choir (empty: none)
};

struct Channel {
    long long ch;
    double sr;
    long long blk;
    // the bank
    int M = 0;
    std::vector<long> key, string;
    std::vector<double> f, alpha, w, hl, hr, dl, dr, px, W;
    std::map<int, std::vector<int>> keyidx;      // in the bank's key order
    // the choirs (Strings.choir_bridges, cross, buffs): each mode's bridge
    std::vector<long> choir_bridges = std::vector<long>(1, 0), bridge;
    double cross = 1.0;
    std::vector<std::pair<int, int>> buffs;     // (buffed, plain)
    // ...or by key (Strings.keybridge: a dulcimer's two bridges, over the
    // bank's keys), each key's partner (bridge_partner) at partner_k, the
    // knock's measured profile (semitones, dB) and its tilt
    std::map<int, long> kbridge;
    std::vector<long> partner = std::vector<long>(128, -1);
    double partner_k = 1.0, ktilt = 0.0;
    std::vector<double> kp_x, kp_db;
    // the class
    double kappa, knock, fall, fl, rel;
    int top;
    // the pedal: a switch's spans (samples), or per key (half-pedal)
    bool per_key = false;
    std::vector<Span> pedal;
    std::map<int, std::vector<Span>> pedal_key;
    std::map<int, std::vector<Span>> holds;
    // the felt (half-pedal)
    bool damping = false;
    std::vector<double> dw;
    std::vector<long> d_off;
    std::vector<double> d_bk, d_rate, d_D;
    std::map<int, std::vector<double>> d_bk_of, d_rate_of;
    std::map<long long, std::set<int>> pevents;
    // the state
    std::vector<cplx> Az, Rz;
    std::vector<double> nref, rref, r_b, r_nfloor, r_closed, r_lr;
    std::vector<long> rrow;
    std::vector<char> has;
    // the store
    long n = 0;
    std::vector<double> c_om, c_p0, c_p0R, c_aL, c_aR, c_aM, c_nf, c_non, c_noff, c_fa, c_re, c_logr, c_delL,
        c_delR, c_px, c_b, c_nfloor, c_closed;
    std::vector<long> c_pl, c_mode, c_key, c_seq, c_src, c_kind;
    std::vector<Strike> strikes;
    std::map<long long, std::vector<int>> groups;
    std::map<long long, std::vector<cplx>> pending;
    std::vector<Bridge> bridges;
    std::vector<long> open;
    std::vector<Forced> out;
    std::vector<long> out_rows;
    long seq = 0, fseq = 0;
    double loud = 0.0;
    bool have_tpl = false;
    double tpl[NC];
    double T = 0.0;
    long nsrc = 0;

    void room(long more)
    {
        long cap = (long)c_om.size();
        if (n + more <= cap)
            return;
        long nw = std::max(2 * cap, n + more);
        for (auto *v : {&c_om, &c_p0, &c_p0R, &c_aL, &c_aR, &c_aM, &c_nf, &c_non, &c_noff, &c_fa, &c_re, &c_logr,
                        &c_delL, &c_delR, &c_px, &c_b, &c_nfloor, &c_closed})
            v->resize(nw, 0.0);
        for (auto *v : {&c_pl, &c_mode, &c_key, &c_seq, &c_src, &c_kind})
            v->resize(nw, 0);
    }

    double floor_() const { return fl * pymax(loud, 1e-30); }

    // each key's free spans merged, made on first ask (register.Channel's
    // `spans`): a strike on the key adds a hold and clears its entry
    mutable std::map<int, std::vector<Span>> sp_cache;

    const std::vector<Span> &span_list(int k) const
    {
        auto it = sp_cache.find(k);
        if (it != sp_cache.end())
            return it->second;
        std::vector<Span> all;
        if (k >= top) {
            all.push_back(Span(0.0, INF));
            return sp_cache[k] = all;
        }
        if (per_key) {
            auto p = pedal_key.find(k);
            if (p != pedal_key.end())
                all = p->second;
        } else {
            all = pedal;
        }
        auto h = holds.find(k);
        if (h != holds.end())
            all.insert(all.end(), h->second.begin(), h->second.end());
        return sp_cache[k] = merge_spans(all);
    }

    // span_end: the end of the free span holding sample n, or NaN for none
    double span_end(int k, double t) const
    {
        for (const Span &s : span_list(k)) {
            if (s.first <= t && t < s.second)
                return s.second;
            if (s.first > t)
                break;
        }
        return NAN;
    }

    std::vector<double> dcum_of(const std::vector<int> &modes, const std::vector<double> &t) const
    {
        std::vector<double> o(modes.size());
        std::vector<long> k8(modes.size());
        for (size_t i = 0; i < modes.size(); i++)
            k8[i] = key[modes[i]];
        dcum((int)modes.size(), k8.data(), t.data(), d_off.data(), d_bk.data(), d_rate.data(), d_D.data(), sr,
             o.data());
        return o;
    }

    // _dgain: exp(-felt) on modes from n0 to n1 (1 where nothing damps)
    std::vector<double> dgain(const std::vector<int> &modes, const std::vector<double> &n0,
                              const std::vector<double> &n1) const
    {
        std::vector<double> g(modes.size(), 1.0);
        if (!damping || modes.empty())
            return g;
        std::vector<double> a = dcum_of(modes, n1), b = dcum_of(modes, n0);
        for (size_t i = 0; i < modes.size(); i++)
            g[i] = exp(-dw[modes[i]] * (a[i] - b[i]));
        return g;
    }

    double drate(int k, double t) const
    {
        auto it = d_bk_of.find(k);
        if (it == d_bk_of.end())
            return 0.0;
        const std::vector<double> &bk = it->second;
        int i = (int)(std::upper_bound(bk.begin(), bk.end(), t) - bk.begin()) - 1;
        return i >= 0 ? d_rate_of.at(k)[i] : 0.0;
    }

    long src_ix() { return nsrc++; }   // a row's source: not handed out

    long write(int i, cplx z, double non, double fa, double noff, double re_, int kind, long long sq, double lr,
               bool lr_set)
    {
        room(1);
        long r = n++;
        double om = W[i] / sr;
        double ph = atan2(z.imag(), z.real());
        double az = hypot(z.real(), z.imag());
        c_om[r] = om; c_p0[r] = ph - om * dl[i]; c_p0R[r] = ph - om * dr[i];
        c_aL[r] = az * hl[i]; c_aR[r] = az * hr[i]; c_aM[r] = az;
        c_nf[r] = f[i]; c_non[r] = non; c_noff[r] = noff; c_fa[r] = fa; c_re[r] = re_;
        c_logr[r] = lr_set ? lr : alpha[i];
        c_delL[r] = dl[i]; c_delR[r] = dr[i]; c_px[r] = px[i];
        c_pl[r] = string[i]; c_mode[r] = i; c_key[r] = key[i]; c_kind[r] = kind; c_src[r] = src_ix();
        c_seq[r] = sq;
        return r;
    }

    void forced(const Strike &st, int r, double beta, cplx F)
    {
        Forced x;
        for (int c = 0; c < NC; c++)
            x.row[c] = st.drv[c][r];
        double g = hypot(F.real(), F.imag());
        double ph = atan2(F.imag(), F.real());
        x.row[C_aL] *= g; x.row[C_aR] *= g; x.row[C_aM] *= g;
        x.row[C_p0] += ph; x.row[C_p0R] += ph;
        x.row[C_logr] = beta; x.row[C_logrA] = 0.0; x.row[C_aft] = 0.0; x.row[C_sus] = beta != 0.0 ? 0.0 : 1.0;
        x.seq = fseq++;
        out.push_back(x);
    }

    void strike(int k, double on, double held, const double *rows, int nr, const int *plucked = nullptr,
                int nplucked = -1, const long *rchoir = nullptr)
    {
        // rows: nr rows of NC columns (EMIT_COLS), the note's rows as the table holds them;
        // plucked: the choirs it plucked (nplucked < 0: None); rchoir: each row's choir
        Strike st;
        st.key = k;
        st.drv.assign(NC, {});
        st.has_plucked = nplucked >= 0;
        if (st.has_plucked)
            st.plucked.assign(plucked, plucked + nplucked);
        for (int r = 0; r < nr; r++)
            if (rows[NC * r + C_dr] > 0.5) {
                for (int c = 0; c < NC; c++)
                    st.drv[c].push_back(rows[NC * r + c]);
                if (rchoir)
                    st.choir.push_back(rchoir[r]);
            }
        // ITS OWN KEY'S FREE CHOIRS ARE FREE FROM ITS BLOCK (a pluck's: the
        // block its partials start in)
        double n_on = on * sr;
        if (st.has_plucked && !st.drv[0].empty()) {
            double mn = st.drv[C_non][0];
            for (double v : st.drv[C_non])
                mn = pymin(mn, v);
            n_on = pymin(n_on, (double)((long long)pyfloordiv(mn, (double)blk) * blk));
        }
        holds[k].push_back(Span(n_on, held * sr));
        sp_cache.erase(k);
        if (st.drv[0].empty())
            return;
        int si = (int)strikes.size();
        double mn = st.drv[C_non][0];
        for (double v : st.drv[C_non])
            mn = pymin(mn, v);                      // np.min
        long long b = (long long)pyfloordiv(mn, (double)blk) * blk;     // int(min // blk) * blk
        strikes.push_back(st);
        groups[b].push_back(si);
        if (!have_tpl) {
            for (int c = 0; c < NC; c++)
                tpl[c] = strikes[si].drv[c][0];
            have_tpl = true;
        }
    }

    double next_event_d() const
    {
        double e = INF;
        if (!groups.empty())
            e = pymin(e, (double)groups.begin()->first);
        if (!pending.empty())
            e = pymin(e, (double)pending.begin()->first);
        if (!pevents.empty())
            e = pymin(e, (double)pevents.begin()->first);
        if (T != INF)
            e = pymin(e, pyfloordiv(T, (double)blk) * (double)blk);    // float(int(T // blk) * blk)
        return e;
    }

    // register.Channel.pending_min: the next event, an open row's onset, a
    // waiting bridge's -- no row still to come starts before it
    double pending_min() const
    {
        double e = next_event_d();
        for (long r : open)
            e = pymin(e, c_non[r]);
        for (const Bridge &br : bridges)
            e = pymin(e, br.n0);
        return e;
    }

    void update(const std::vector<char> &m, long long bl, const std::vector<cplx> &add, const std::vector<char> *force)
    {
        double b = (double)bl;
        std::vector<int> idx;
        for (int i = 0; i < M; i++)
            if (m[i])
                idx.push_back(i);
        if (idx.empty())
            return;
        for (int i : idx)
            if (Az[i] != cplx(0.0, 0.0)) {
                double e = span_end((int)key[i], nref[i]);
                if (std::isnan(e))
                    e = nref[i];
                if (e <= b) {
                    Az[i] = 0.0;
                    nref[i] = b;
                }
            }
        std::vector<double> n0(idx.size()), n1(idx.size(), b);
        for (size_t q = 0; q < idx.size(); q++)
            n0[q] = nref[idx[q]];
        std::vector<double> g = dgain(idx, n0, n1);
        for (size_t q = 0; q < idx.size(); q++) {
            int i = idx[q];
            double e = exp(-alpha[i] * pymax(b - nref[i], 0.0) / sr);
            cplx z = cmul_r(Az[i], e);
            if (damping)
                z = cmul_r(z, g[q]);
            else
                z = cplx(z.real() * 1.0 - z.imag() * 0.0, z.real() * 0.0 + z.imag() * 1.0);
            Az[i] = z + add[i];
            nref[i] = b;
        }
        double floor = floor_();
        std::vector<int> go;
        for (size_t q = 0; q < idx.size(); q++) {
            int i = idx[q];
            cplx tz = Az[i], rz(0.0, 0.0);
            if (has[i]) {
                double end = span_end((int)key[i], r_b[i]);
                if (std::isnan(end))
                    end = r_b[i];
                double mn = pymin(pymin(r_nfloor[i], end), r_closed[i]);
                if (mn > b)
                    rz = cmul_r(Rz[i], exp(-r_lr[i] * pymax(b - rref[i], 0.0) / sr));
                else
                    rz = cplx(0.0, 0.0);
            }
            double mag = pymax(hypot(tz.real(), tz.imag()), floor);
            cplx d = tz - rz;
            bool g_ = hypot(d.real(), d.imag()) > SPLIT * mag;
            if (force && (*force)[i] && has[i])
                g_ = true;
            if (g_)
                go.push_back(i);
        }
        if (go.empty())
            return;
        std::vector<char> free_now(go.size());
        std::vector<double> drt(go.size());
        for (size_t q = 0; q < go.size(); q++) {
            free_now[q] = !std::isnan(span_end((int)key[go[q]], b));
            if (damping)
                drt[q] = drate((int)key[go[q]], b);
        }
        room((long)go.size());
        std::vector<long> go8(go.begin(), go.end());
        std::vector<long> opn(open.size() + go.size());
        std::copy(open.begin(), open.end(), opn.begin());
        long sq = seq;
        int got = free_rows((int)go8.size(), go8.data(), free_now.data(), damping ? drt.data() : nullptr,
                            Az.data(), alpha.data(), damping ? dw.data() : nullptr, W.data(), f.data(), hl.data(),
                            hr.data(), dl.data(), dr.data(), px.data(), string.data(), key.data(), rrow.data(),
                            has.data(), r_b.data(), r_nfloor.data(), r_closed.data(), Rz.data(), rref.data(),
                            r_lr.data(), floor, b, sr, (double)blk, src_ix(), n, &sq, c_om.data(), c_p0.data(),
                            c_p0R.data(), c_aL.data(), c_aR.data(), c_aM.data(), c_nf.data(), c_non.data(),
                            c_fa.data(), c_logr.data(), c_delL.data(), c_delR.data(), c_px.data(), c_pl.data(),
                            c_mode.data(), c_key.data(), c_b.data(), c_nfloor.data(), c_closed.data(), c_seq.data(),
                            c_src.data(), opn.data(), (long)open.size());
        n += got;
        seq = sq;
        opn.resize(open.size() + got);
        open.swap(opn);
    }

    void strikes_at(long long bl, const std::vector<int> &sis)
    {
        double b = (double)bl;
        std::vector<cplx> add(M, cplx(0.0, 0.0));
        for (int si : sis) {
            const Strike &st = strikes[si];
            const std::vector<std::vector<double>> &drv = st.drv;
            int R = (int)drv[0].size();
            double mx = std::fabs(drv[C_aM][0]);
            for (int r = 1; r < R; r++)
                if (std::fabs(drv[C_aM][r]) > mx)
                    mx = std::fabs(drv[C_aM][r]);
            loud = pymax(loud, mx);
            double floor = floor_();
            std::vector<long> fi;
            std::vector<char> free(M, 0);
            // (Strings.free_choirs: a buffed choir while its stop is drawn, else its plain one)
            std::vector<char> okc(choir_bridges.size(), 1);
            auto in_plucked = [&](long c) {
                return std::find(st.plucked.begin(), st.plucked.end(), (int)c) != st.plucked.end();
            };
            for (auto &bp : buffs) {
                if (st.has_plucked && in_plucked(bp.first))
                    okc[bp.second] = 0;
                else
                    okc[bp.first] = 0;
            }
            for (auto &ki : keyidx) {
                if (ki.first != st.key) {
                    if (!std::isnan(span_end(ki.first, b)))
                        for (int i : ki.second)
                            if (okc[string[i] / 16])
                                free[i] = 1;
                } else if (st.has_plucked && !std::isnan(span_end(ki.first, b))) {
                    // its own key: every choir but the plucked ones
                    for (int i : ki.second)
                        if (okc[string[i] / 16] && !in_plucked(string[i] / 16))
                            free[i] = 1;
                }
            }
            for (int i = 0; i < M; i++)
                if (free[i])
                    fi.push_back(i);
            if (fi.empty())
                continue;
            std::vector<cplx> xfer(M, cplx(0.0, 0.0));
            // strike_drive
            std::vector<long> choir(R, -1);
            if (!st.choir.empty())
                choir = st.choir;
            int cap = 4 * 3 * std::max(R, 1);
            // the struck key's bridge (a dulcimer's, over the bank's keys) and its partner
            auto kbi = kbridge.find(st.key);
            long kb = kbi != kbridge.end() ? kbi->second : -1;
            long pk = (st.key >= 0 && st.key < 128) ? partner[st.key] : -1;
            std::vector<cplx> add_s, xfer_s, f_val;
            std::vector<int> f_r;
            std::vector<double> f_beta;
            double lo = 0.0, lr = 0.0;
            int nfo;
            for (;;) {
                add_s.assign(M, cplx(0.0, 0.0));
                xfer_s.assign(M, cplx(0.0, 0.0));
                f_r.assign(cap, 0); f_beta.assign(cap, 0.0); f_val.assign(cap, cplx(0.0, 0.0));
                nfo = strike_drive(R, drv[C_aM].data(), drv[C_om].data(), drv[C_non].data(), drv[C_p0].data(),
                                   drv[C_delL].data(), drv[C_noff].data(), drv[C_re].data(), drv[C_tbav].data(),
                                   drv[C_tau].data(), drv[C_tcut].data(), drv[C_aft].data(), drv[C_sus].data(),
                                   drv[C_logr].data(), drv[C_logrA].data(), choir.data(), (int)fi.size(), fi.data(),
                                   W.data(), alpha.data(), w.data(), bridge.data(), key.data(), choir_bridges.data(),
                                   cross, kb, pk, partner_k, kappa, floor, SPLIT, sr, b, add_s.data(), xfer_s.data(), cap,
                                   f_r.data(), f_beta.data(), f_val.data(), &lo, &lr);
                if (nfo <= cap)
                    break;
                cap = nfo;
            }
            for (int i = 0; i < M; i++) {
                add[i] += add_s[i];
                xfer[i] += xfer_s[i];
            }
            for (int q = 0; q < nfo; q++)
                forced(st, f_r[q], f_beta[q], f_val[q]);
            bool have_off = lo >= 0;
            // THE KNOCK: every free string kicked, falling `fall` dB a semitone
            if (knock > 0) {
                double mxa = drv[C_aM][0];
                for (int r = 1; r < R; r++)
                    if (drv[C_aM][r] > mxa)
                        mxa = drv[C_aM][r];
                double ka = knock * mxa;
                std::vector<double> ph = knock_phase(py_tuple_hash2(ch, si), (int)fi.size());
                for (size_t q = 0; q < fi.size(); q++) {
                    int i = (int)fi[q];
                    // (Strings.coupling: across bridges, onto the struck string's partner)
                    double cw = w[i];
                    if (kb >= 0)
                        cw = cw * (bridge[i] == kb ? 1.0 : cross);
                    if (pk >= 0)
                        cw = cw * (key[i] == pk ? partner_k : 1.0);
                    // (Strings.knock_shape: the fall a semitone, or the measured profile; the tilt)
                    double g;
                    if (!kp_x.empty())
                        g = pow(10.0, np_interp((double)(key[i] - st.key), kp_x.data(), kp_db.data(),
                                                (int)kp_x.size()) / 20.0);
                    else
                        g = pow(10.0, -fall * (double)std::labs(key[i] - st.key) / 20.0);
                    if (ktilt != 0.0)
                        g = g * pow(f[i] / 1000.0, -ktilt);
                    double amp = ka * cw * g;
                    double r0 = exp(0.0);              // numpy's exp(1j * p): (cos p, sin p)
                    cplx e(r0 * cos(ph[q]), r0 * sin(ph[q]));
                    add[i] += rmul_c(amp, e);
                }
            }
            bool any = false;
            for (int i = 0; i < M; i++)
                if (xfer[i] != cplx(0.0, 0.0))
                    any = true;
            if (have_off && any) {
                double n_off = lo, re_off = lr;
                long long pb = (long long)std::ceil((n_off + re_off) / (double)blk) * blk;
                Bridge br;
                for (int i = 0; i < M; i++)
                    if (hypot(xfer[i].real(), xfer[i].imag()) >= floor) {
                        br.cand.push_back(i);
                        br.vals.push_back(xfer[i]);
                        br.seqs.push_back(seq++);
                    }
                if (!br.cand.empty()) {
                    br.n0 = n_off; br.re0 = re_off; br.pb = pb;
                    bridges.push_back(br);
                }
                std::vector<int> all(M);
                std::vector<double> a0(M, n_off), a1(M, (double)pb);
                for (int i = 0; i < M; i++)
                    all[i] = i;
                std::vector<double> g = dgain(all, a0, a1);
                std::vector<cplx> tr(M);
                for (int i = 0; i < M; i++) {
                    cplx z = cmul_r(xfer[i], exp(-alpha[i] * ((double)pb - n_off) / sr));
                    tr[i] = damping ? cmul_r(z, g[i]) : cplx(z.real() * 1.0 - z.imag() * 0.0,
                                                               z.real() * 0.0 + z.imag() * 1.0);
                }
                auto it = pending.find(pb);
                if (it == pending.end())
                    pending[pb] = tr;
                else
                    for (int i = 0; i < M; i++)
                        it->second[i] += tr[i];
            }
        }
        std::vector<char> m(M);
        for (int i = 0; i < M; i++)
            m[i] = add[i] != cplx(0.0, 0.0);
        update(m, bl, add, nullptr);
    }

    void decide_bridges(double Tn)
    {
        std::vector<Bridge> keep;
        for (Bridge &br : bridges) {
            if (br.n0 >= Tn) {
                keep.push_back(br);
                continue;
            }
            for (size_t q = 0; q < br.cand.size(); q++) {
                int i = br.cand[q];
                if (std::isnan(span_end((int)key[i], br.n0)))
                    continue;
                out_rows.push_back(write(i, br.vals[q], br.n0, pymax(br.re0, 1.0), (double)br.pb, (double)blk, 1,
                                         br.seqs[q], 0.0, false));
            }
        }
        bridges.swap(keep);
    }

    void settle_rows()
    {
        double e = next_event_d();
        std::vector<long> keep;
        for (long r : open) {
            double end = span_end((int)c_key[r], c_b[r]);
            bool exact = !std::isnan(end) && end < T;
            double closed = c_closed[r], nfl = c_nfloor[r];
            double x = pymin(pymin(nfl, closed), exact ? end : INF);
            if (x <= e || T == INF) {
                if (std::isnan(end))
                    end = c_b[r];
                double noff, re_;
                if (end <= nfl) {
                    noff = end; re_ = rel;
                } else {
                    noff = nfl; re_ = (double)blk;
                }
                if (closed != INF && noff > closed) {
                    noff = closed; re_ = (double)blk;
                }
                c_noff[r] = pymin(noff, 9e15);
                c_re[r] = re_;
                out_rows.push_back(r);
            } else {
                keep.push_back(r);
            }
        }
        open.swap(keep);
    }

    void advance(double Tn)
    {
        T = Tn;
        for (;;) {
            bool hg = false, hp = false, he = false;
            long long gb = 0, pb = 0, eb = 0;
            for (auto &g : groups)
                if ((double)(g.first + blk) <= Tn) {
                    gb = g.first; hg = true;
                    break;
                }
            for (auto &p : pending)
                if ((double)p.first <= Tn) {
                    pb = p.first; hp = true;
                    break;
                }
            for (auto &p : pevents)
                if ((double)(p.first + blk) <= Tn) {
                    eb = p.first; he = true;
                    break;
                }
            if (!hg && !hp && !he)
                break;
            if (he && (!hg || eb < gb) && (!hp || eb < pb)) {
                std::set<int> keys = pevents[eb];
                pevents.erase(eb);
                std::vector<char> mk(M, 0);
                bool anyk = false;
                for (int i = 0; i < M; i++)
                    if (keys.count((int)key[i]) && Az[i] != cplx(0.0, 0.0)) {
                        mk[i] = 1;
                        anyk = true;
                    }
                if (anyk)
                    update(mk, eb, std::vector<cplx>(M, cplx(0.0, 0.0)), &mk);
                continue;
            }
            if (hp && (!hg || pb <= gb)) {
                std::vector<cplx> add = pending[pb];
                pending.erase(pb);
                std::vector<char> m(M);
                for (int i = 0; i < M; i++)
                    m[i] = add[i] != cplx(0.0, 0.0);
                update(m, pb, add, nullptr);
            } else {
                std::vector<int> sis = groups[gb];
                groups.erase(gb);
                strikes_at(gb, sis);
            }
        }
        decide_bridges(Tn);
        settle_rows();
    }
};

}  // namespace reg
}  // namespace nv

extern "C" {

// A register channel: its string bank (modes, M of them, as nv_strings
// sorts them), the class's constants (kappa = register_gain * scale, knock =
// register_knock_gain * scale, fall, the floor, the release in samples,
// damper_top), and its pedal: a switch's spans (seconds, nped pairs), or
// with per_key set, half-pedalled spans and felt added by nv_reg_key_pedal.
void *nv_reg_new(long long ch, const StringMode *modes, int M, double kappa, double knock, double fall,
                 double fl, double rel, int top, double sr, long long blk, const double *ped, int nped, int per_key)
{
    using namespace nv::reg;
    Channel *C = new Channel();
    C->ch = ch; C->sr = sr; C->blk = blk; C->M = M;
    C->kappa = kappa; C->knock = knock; C->fall = fall; C->fl = fl; C->rel = rel; C->top = top;
    C->per_key = per_key != 0;
    for (int i = 0; i < M; i++) {
        const StringMode &q = modes[i];
        C->key.push_back((long)q.key); C->string.push_back((long)q.string);
        C->f.push_back(q.f); C->alpha.push_back(q.alpha); C->w.push_back(q.w);
        C->hl.push_back(q.hl); C->hr.push_back(q.hr); C->dl.push_back(q.dl); C->dr.push_back(q.dr);
        C->px.push_back(q.px); C->W.push_back(TAU * q.f);
        C->keyidx[(int)q.key].push_back(i);
    }
    for (int i = 0; i < nped; i++)
        C->pedal.push_back(Span(ped[2 * i] * sr, ped[2 * i + 1] * sr));
    C->Az.assign(M, 0.0); C->Rz.assign(M, 0.0);
    C->nref.assign(M, 0.0); C->rref.assign(M, 0.0);
    C->r_b.assign(M, 0.0); C->r_nfloor.assign(M, 0.0); C->r_closed.assign(M, INF);
    C->r_lr = C->alpha;
    C->rrow.assign(M, -1); C->has.assign(M, 0);
    C->bridge.assign(M, 0);
    C->room(1024);
    return C;
}

// A harpsichord's choirs (register.Strings'): each choir's bridge, the
// coupling across bridges, and the buffs (buffed, plain) pairs
void nv_reg_choirs(void *h, int nchoir, const long *bridges, double cross, int nbuff, const int *buffs)
{
    nv::reg::Channel *C = (nv::reg::Channel *)h;
    C->choir_bridges.assign(bridges, bridges + nchoir);
    C->cross = cross;
    C->buffs.clear();
    for (int q = 0; q < nbuff; q++)
        C->buffs.push_back(std::make_pair(buffs[2 * q], buffs[2 * q + 1]));
    for (int i = 0; i < C->M; i++)
        C->bridge[i] = C->choir_bridges[C->string[i] / 16];
}

// ...or a bank's bridges BY KEY (register.Strings.keybridge: kb[key], -1
// none, over the bank's keys), the coupling across them, each key's partner
// (-1 none) at partner_k, and the knock's measured profile (nkp (semitones,
// dB)) and tilt
void nv_reg_keys(void *h, const int *kb, double cross, const int *partner, double partner_k, double ktilt,
                 int nkp, const double *kp_x, const double *kp_db)
{
    nv::reg::Channel *C = (nv::reg::Channel *)h;
    C->cross = cross;
    C->kbridge.clear();
    bool any = false;
    for (auto &ki : C->keyidx)
        if (ki.first >= 0 && ki.first < 128 && kb[ki.first] >= 0) {
            C->kbridge[ki.first] = kb[ki.first];
            any = true;
        }
    if (any)
        for (int i = 0; i < C->M; i++)
            C->bridge[i] = C->kbridge.count((int)C->key[i]) ? C->kbridge[(int)C->key[i]] : 0;
    for (int q = 0; q < 128; q++)
        C->partner[q] = partner[q];
    C->partner_k = partner_k;
    C->ktilt = ktilt;
    C->kp_x.assign(kp_x, kp_x + nkp);
    C->kp_db.assign(kp_db, kp_db + nkp);
}

// A half-pedalled channel's key: its free spans (seconds) and its felt (each
// pedal move in samples, the residual rate from it); dw the felt's weight
// per mode, given once (nkey < 0 to finish: the felt's tables are built).
void nv_reg_key_pedal(void *h, int key, const double *spans, int nspans, const double *bk, const double *rate,
                      int nrate, const double *dw)
{
    using namespace nv::reg;
    Channel *C = (Channel *)h;
    std::vector<Span> sp;
    for (int i = 0; i < nspans; i++)
        sp.push_back(Span(spans[2 * i] * C->sr, spans[2 * i + 1] * C->sr));
    C->pedal_key[key] = sp;
    C->sp_cache.erase(key);
    if (dw && C->dw.empty())
        C->dw.assign(dw, dw + C->M);
    bool anyr = false;
    for (int i = 0; i < nrate; i++)
        if (rate[i] != 0.0)
            anyr = true;
    if (nrate && anyr) {
        C->damping = true;
        C->d_bk_of[key] = std::vector<double>(bk, bk + nrate);
        C->d_rate_of[key] = std::vector<double>(rate, rate + nrate);
        for (int i = 0; i < nrate; i++)
            if (i == 0 || rate[i] != rate[i - 1]) {
                long long b = (long long)std::ceil(bk[i] / (double)C->blk) * C->blk;
                C->pevents[b].insert(key);
            }
    }
}

// the felt's flat tables for dcum, once every key is in (D: the damping done
// by each move, the cumulative sum the Python takes)
void nv_reg_felt_done(void *h)
{
    using namespace nv::reg;
    Channel *C = (Channel *)h;
    if (!C->damping)
        return;
    C->d_off.assign(130, 0);
    for (int k = 0; k < 129; k++) {
        auto it = C->d_bk_of.find(k);
        C->d_off[k + 1] = C->d_off[k] + (it != C->d_bk_of.end() ? (long)it->second.size() : 0);
        if (it != C->d_bk_of.end()) {
            const std::vector<double> &bk = it->second, &rate = C->d_rate_of[k];
            C->d_bk.insert(C->d_bk.end(), bk.begin(), bk.end());
            C->d_rate.insert(C->d_rate.end(), rate.begin(), rate.end());
            // D = concatenate(([0], cumsum(rate[:-1] * diff(bk) / sr)))
            double acc = 0.0;
            C->d_D.push_back(0.0);
            for (size_t i = 0; i + 1 < bk.size(); i++) {
                acc = acc + rate[i] * (bk[i + 1] - bk[i]) / C->sr;
                C->d_D.push_back(acc);
            }
        }
    }
}

void nv_reg_strike(void *h, int key, double on, double held, const double *rows, int nr)
{
    ((nv::reg::Channel *)h)->strike(key, on, held, rows, nr);
}

// ...a pluck: the choirs it plucked (nplucked < 0: None) and each row's choir
void nv_reg_pluck(void *h, int key, double on, double held, const double *rows, int nr, const int *plucked,
                  int nplucked, const long *rchoir)
{
    ((nv::reg::Channel *)h)->strike(key, on, held, rows, nr, plucked, nplucked, rchoir);
}

void nv_reg_finish(void *h) { ((nv::reg::Channel *)h)->advance(nv::reg::INF); }

// The rows, as register.expand appends them: the free and bridge rows by
// seq, then the forced rows by theirs; NC columns each (EMIT_COLS) into out
// (cap rows). Returns the rows, or -(rows) if cap is too small.
long nv_reg_take(void *h, double *out, long cap)
{
    using namespace nv::reg;
    Channel *C = (Channel *)h;
    std::vector<long> ids = C->out_rows;
    std::stable_sort(ids.begin(), ids.end(), [&](long a, long b) { return C->c_seq[a] < C->c_seq[b]; });
    std::vector<Forced> fo = C->out;
    std::stable_sort(fo.begin(), fo.end(), [](const Forced &a, const Forced &b) { return a.seq < b.seq; });
    long n = (long)ids.size() + (long)fo.size();
    if (n > cap)
        return -n;
    for (size_t q = 0; q < ids.size(); q++) {
        long r = ids[q];
        double *o = out + NC * q;
        for (int c = 0; c < NC; c++)
            o[c] = C->tpl[c];
        // the constants (Channel._CONST)
        o[C_logrA] = 0.0; o[C_aft] = 0.0; o[C_sus] = 0.0; o[C_cv] = 0.0; o[C_sj] = 0.0; o[C_crl] = 0.0;
        o[C_csc] = 0.0; o[C_cbw] = 0.0; o[C_tbav] = 0.0; o[C_tcut] = 0.0; o[C_gb] = 0.0; o[C_gc] = 0.0;
        o[C_vd] = 0.0; o[C_vdl] = 0.0; o[C_br] = -1; o[C_gr] = -1; o[C_cr] = 0; o[C_fx] = -1; o[C_mk] = 0;
        o[C_rdl] = 0.0; o[C_fmw] = 0.0; o[C_fmp] = 0.0; o[C_fmpR] = 0.0; o[C_dr] = 1.0;
        // the row's own (_Rows.ROW, and nfr its nf)
        o[C_om] = C->c_om[r]; o[C_p0] = C->c_p0[r]; o[C_p0R] = C->c_p0R[r]; o[C_aL] = C->c_aL[r];
        o[C_aR] = C->c_aR[r]; o[C_aM] = C->c_aM[r]; o[C_nf] = C->c_nf[r]; o[C_non] = C->c_non[r];
        o[C_noff] = C->c_noff[r]; o[C_fa] = C->c_fa[r]; o[C_re] = C->c_re[r]; o[C_logr] = C->c_logr[r];
        o[C_delL] = C->c_delL[r]; o[C_delR] = C->c_delR[r]; o[C_px] = C->c_px[r]; o[C_pl] = (double)C->c_pl[r];
        o[C_nfr] = C->c_nf[r];
    }
    for (size_t q = 0; q < fo.size(); q++)
        memcpy(out + NC * (ids.size() + q), fo[q].row, sizeof fo[q].row);
    return n;
}

void nv_reg_free(void *h) { delete (nv::reg::Channel *)h; }

// A STREAM's (register.Channel.advance / pending_min / take): the channel
// worked to T; the horizon; and the rows final so far, each with its (phase,
// seq) -- 0 and its seq a free or bridge row, 1 and its fseq a forced one --
// handed out ONCE (unlike nv_reg_take): -(rows) if cap is too small, nothing taken
void nv_reg_advance(void *h, double T) { ((nv::reg::Channel *)h)->advance(T); }

double nv_reg_pending_min(void *h) { return ((nv::reg::Channel *)h)->pending_min(); }

long nv_reg_take_ready(void *h, double *out, long cap, long long *phase, long long *seq)
{
    using namespace nv::reg;
    Channel *C = (Channel *)h;
    long n = nv_reg_take(h, out, cap);
    if (n < 0)
        return n;
    std::vector<long> ids = C->out_rows;
    std::stable_sort(ids.begin(), ids.end(), [&](long a, long b) { return C->c_seq[a] < C->c_seq[b]; });
    std::vector<Forced> fo = C->out;
    std::stable_sort(fo.begin(), fo.end(), [](const Forced &a, const Forced &b) { return a.seq < b.seq; });
    for (size_t q = 0; q < ids.size(); q++) {
        phase[q] = 0;
        seq[q] = C->c_seq[ids[q]];
    }
    for (size_t q = 0; q < fo.size(); q++) {
        phase[ids.size() + q] = 1;
        seq[ids.size() + q] = fo[q].seq;
    }
    C->out_rows.clear();
    C->out.clear();
    return n;
}

// A STREAM's SAFE HORIZON for a channel (streamrender._register's): a pluck's
// hold starts at its partials' block, up to a block before its onset, so a
// stream advances to floor(T / blk) * blk - blk; INF as it is
double reg_safe(void *h, double T)
{
    if (T == nv::reg::INF)
        return T;
    const double b = (double)((nv::reg::Channel *)h)->blk;
    return nv::reg::pyfloordiv(T, b) * b - b;
}

// a channel's copy, as it stands (TUNING_NV_REG_INC's twin)
void *nv_reg_copy(void *h) { return new nv::reg::Channel(*(nv::reg::Channel *)h); }

void nv_buf_free(void *p) { free(p); }

}  // extern "C"

// THE FIRST STORE'S GUESS, rows a note (TUNING_NV_ROWS_PER_NOTE sets it: a
// gate's small one plays every file again), and this thread's last play's
// growth (nv_play_growth: the first store and the rows it needed, 0 none)
static const long long ROWS_PER_NOTE = 1024;
static thread_local long long g_cap0 = 0, g_need = 0;

extern "C" {

// how far this thread's last nv_play_full grew its store: the first store's
// rows and the rows the song needed (0: it fit)
void nv_play_growth(long long *cap0, long long *need)
{
    *cap0 = g_cap0;
    *need = g_need;
}

// A SONG PLAYED, WITH ITS REGISTER: nv_play's note rows, cast as the table
// stores them (kind[c]: 0 float64, 1 float32, 2 int32 -- blockrender's
// _COL_F4 and _COL_I4), then each channel's free strings (register.Channel,
// one per channel and class, made at its first note: its string bank at
// that note's tuning, pan and volume; its pedal, a switch's spans or a
// half-pedalled channel's spans and felt per key) fed every strike (the
// note's rows, its key-up or the sostenuto's hold) and their rows appended,
// channel by channel, cast the same way. scale: the render's register
// scale; full_db_s, residual, beta: damper.py's felt. The rows in *rowsp
// (malloc'd: nv_buf_free), grown as they need. Returns the rows, or < 0 as
// nv_play (a note that is not the engine's), -1e9 if memory ran out.
extern "C" void nv_play_set_kind(const int *kind);
extern "C" void nv_play_set_sink(const void *s);
extern "C" const void *nv_play_get_sink(void);
extern "C" void nv_stream_refuse(const char *why);
// A STREAM's replay (nv_play_replay): the state its first play began from, and the store that fit
static PyRandom g_rp_rs;
static double g_rp_q[18], g_rp_az;
static long long g_rp_cap = 0;
// TUNING_NV_SINK_TEST's sink: every note's rows appended to a table of its own
namespace {
struct Collect {
    double *rows = nullptr;
    long long n = 0, cap = 0;
    bool fail = false;
    static void note(void *c_, const double *at, long long i0, long long i1, double)
    {
        Collect &c = *(Collect *)c_;
        if (c.fail || i0 != c.n) {          // (rows handed out of order: the hook is wrong)
            c.fail = true;
            return;
        }
        if (i1 > c.cap) {
            long long nc = std::max(i1, 2 * c.cap + 1024);
            double *g = (double *)realloc(c.rows, sizeof(double) * nv::reg::NC * nc);
            if (!g) {
                c.fail = true;
                return;
            }
            c.rows = g;
            c.cap = nc;
        }
        memcpy(c.rows + nv::reg::NC * i0, at, sizeof(double) * nv::reg::NC * (i1 - i0));
        c.n = i1;
    }
};
struct SinkDesc {
    void *ctx;
    void (*note)(void *, const double *, long long, long long, double);
};
}  // namespace
extern "C" long long nv_play_own_end(int j, long long dflt);

// THE REGISTER's FEED (nv_play_full's, lifted so a stream drives it too): a
// note's strike or pluck on its channel, the channel made at its first note;
// the whole render loops it over its table, a stream's sink note by note
struct RegFeed {
    void *song = nullptr;
    const NoteClass *const *K = nullptr;
    const NoteIn *tmpl = nullptr;
    double sr = 0.0, total = 0.0, beta = 0.0, full_db_s = 0.0, residual = 0.0, scale = 0.0, LN10_20 = 0.0;
    long long blk = 0;
    int with_register = 0, nn = 0;
    std::vector<long long> order;                    // the channels, as made
    std::map<long long, std::pair<void *, const NoteClass *>> chans;
    std::map<long long, std::vector<int>> tones;
    std::vector<long long> sym_order;
    std::map<long long, const NoteClass *> sym_k;
    bool inc = false;
    std::map<long long, void *> twin;
    std::map<long long, std::vector<double>> trows;
    std::map<long long, std::vector<std::pair<long long, long long>>> tkey;
    const double *rb = nullptr;                     // (the note's rows: row r at rb + NC (r - roff))
    long long roff = 0;
    const double *RB(long long r) const { return rb + nv::reg::NC * (r - roff); }

    void init(void *song_, const NoteClass *const *K_, const NoteIn *tmpl_, double beta_, double full_db_s_,
              double residual_, double scale_, long long blk_, int with_register_)
    {
        song = song_; K = K_; tmpl = tmpl_; beta = beta_; full_db_s = full_db_s_; residual = residual_;
        scale = scale_; blk = blk_; with_register = with_register_;
        sr = tmpl->sr; total = nv_song_total(song); LN10_20 = log(10.0) / 20.0;
        nn = nv_song_n_notes(song);
        const char *incv = getenv("TUNING_NV_REG_INC");
        inc = incv && *incv && strcmp(incv, "0") != 0;
    }
    void reset()
    {
        for (auto &kv : chans)
            nv_reg_free(kv.second.first);
        for (auto &kv : twin)
            nv_reg_free(kv.second);
        order.clear(); chans.clear(); tones.clear(); sym_order.clear(); sym_k.clear();
        twin.clear(); trows.clear(); tkey.clear();
    }
    void twin_take(long long rk)
    {
        using namespace nv::reg;
        void *t = twin[rk];
        long need = -nv_reg_take(t, nullptr, 0);
        if (need <= 0)
            return;
        std::vector<double> o((size_t)NC * need);
        std::vector<long long> ph(need), sq(need);
        nv_reg_take_ready(t, o.data(), need, ph.data(), sq.data());
        trows[rk].insert(trows[rk].end(), o.begin(), o.end());
        for (long q = 0; q < need; q++)
            tkey[rk].push_back(std::make_pair(ph[q], sq[q]));
    }
    // note j (the song's note i): its own rows r0..r1
    long long note(int j, int i, const double *rb_, long long roff_, long long r0, long long r1)
    {
        using namespace nv::reg;
        rb = rb_;
        roff = roff_;
    long long ch;
    int iv[4];
    double dv[2];
    nv_song_get_note(song, i, &ch, iv, dv);
    if (inc)                            // (a stream's horizon: this note's onset, int(on * SR))
        for (long long rk : order) {
            nv_reg_advance(twin[rk], reg_safe(twin[rk], (double)(long long)(dv[0] * sr)));
            twin_take(rk);
        }
    std::vector<int> &tl = tones[ch];
    const int tk = nv_song_tone(song, i);
    size_t ti = std::find(tl.begin(), tl.end(), tk) - tl.begin();
    if (ti == tl.size())
        tl.push_back(tk);
    long long mix = ch + (ti ? 256LL * (long long)(ti % 256) : 0LL);
    const NoteClass *k = K[nv_song_kidx(song, i)];
    if (k->sym_kind && !sym_k.count(mix)) {
        sym_k[mix] = k;
        sym_order.push_back(mix);
    }
    if (!with_register || !(k->reg_gain != 0.0 || k->reg_knock != 0.0))
        return 0;           // (blockrender.REGISTER off: live's templates)
    long long rk = mix;
    while (chans.count(rk) && chans[rk].second != k)
        rk += 100000;
    if (!chans.count(rk)) {
        double pl[6];
        nv_song_pitch_level_k(song, i, k->init.effort_tilt != 0.0, k->indian, pl);
        double tab[128];
        nv_song_note_table(song, ch, dv[0], k->indian, tab);
        VoiceInit c = k->init;
        double det = 1.0;
        int c1;
        if (k->detune_wheel && nv_song_first_cc(song, ch, 1, &c1))
            det = c1 / 64.0;
        c.detune_lo = k->detune_lo * det;
        c.detune_hi = k->detune_hi * det;
        c.fixed_touch = tmpl->fixed_touch;
        std::vector<StringMode> modes(88 * 4 * 130), tmp(88 * 4 * 130);
        const OrganSpec *cog = k->organ && k->organ->n_choir ? k->organ : nullptr;   // (a harpsichord's choirs)
        int M = nv_strings_og(&c, &k->tmpl, cog, tab, pl[2], pl[3], sr, modes.data(), tmp.data(),
                              (int)modes.size());
        if (M < 0)
            return -1000000000LL;
        int npv = nv_song_pedal_values(song, ch, nullptr, nullptr, 0);
        bool half = k->damper_pedal && npv > 0;
        std::vector<double> ped;
        if (k->damper_pedal && !half) {
            int np = nv_song_ped_spans(song, ch, nullptr, 0);
            ped.resize(2 * np + 2);
            nv_song_ped_spans(song, ch, ped.data(), np);
            ped.resize(2 * np);
        }
        void *h = nv_reg_new(rk, modes.data(), M, k->reg_gain * scale, k->reg_knock * scale, k->reg_fall,
                             k->reg_floor, k->reg_release * sr, k->damper_top, sr, blk, ped.data(),
                             (int)ped.size() / 2, half);
        if (cog) {
            std::vector<long> cbr(cog->choir_bridge, cog->choir_bridge + cog->n_choir);
            nv_reg_choirs(h, cog->n_choir, cbr.data(), cog->cross, cog->n_buff, &cog->buff[0][0]);
        }
        if (k->reg_keyed)               // (a dulcimer's bridges, partners and knock)
            nv_reg_keys(h, k->reg_kb, k->reg_cross, k->reg_partner, k->reg_partner_k, k->reg_ktilt,
                        k->reg_nkp, k->reg_kp_x, k->reg_kp_db);
        if (half) {
            std::vector<double> pt(npv);
            std::vector<int> pv(npv);
            nv_song_pedal_values(song, ch, pt.data(), pv.data(), npv);
            // the felt's weight per mode: (max(f, 1e-6) / the key's f0) ** BETA
            std::vector<double> dw(M);
            for (int q = 0; q < M; q++) {
                double f0 = 440.0 * pow(2.0, ((double)modes[q].key - 69.0) / 12.0);
                dw[q] = pow(pymax(modes[q].f, 1e-6) / f0, beta);
            }
            std::set<int> bank;
            for (int q = 0; q < M; q++)
                bank.insert((int)modes[q].key);
            for (int key = 0; key < 128; key++) {
                // _pedal_spans_of: free while the key's contact is under 1
                std::vector<double> sp;
                bool on = false;
                double a = 0.0;
                for (int q = 0; q < npv; q++) {
                    bool fr = nv_damper_contact(pv[q], key, k->damper_top) < 1.0;
                    if (fr && !on) {
                        a = pt[q];
                        on = true;
                    } else if (!fr && on) {
                        sp.push_back(a);
                        sp.push_back(pt[q]);
                        on = false;
                    }
                }
                if (on) {
                    sp.push_back(a);
                    sp.push_back(pymax(total, a));
                }
                // _pedal_damping_of: the residual felt under the band, per move
                std::vector<double> bk, rate;
                if (bank.count(key)) {
                    bool anyr = false;
                    for (int q = 0; q < npv; q++) {
                        double cn = nv_damper_contact(pv[q], key, k->damper_top);
                        double r_ = cn < 1.0 ? full_db_s * cn * residual * LN10_20 : 0.0;
                        rate.push_back(r_);
                        bk.push_back(pt[q] * sr);
                        if (r_ != 0.0)
                            anyr = true;
                    }
                    if (!anyr) {
                        bk.clear();
                        rate.clear();
                    }
                }
                nv_reg_key_pedal(h, key, sp.data(), (int)sp.size() / 2, bk.data(), rate.data(), (int)rate.size(),
                                 dw.data());
            }
            nv_reg_felt_done(h);
        }
        chans[rk] = std::make_pair(h, k);
        order.push_back(rk);
        if (inc)
            twin[rk] = nv_reg_copy(h);
    }
    double held = dv[1], so;
    if (nv_song_sost(song, ch, iv[0], dv[0], &so))
        held = pymax(dv[1], so);
    if (k->organ && k->organ->n_choir) {
        // A PLUCK (blockrender's register_open plucked, grc): the ranks
        // drawn at the key-down, each on its choir's string; only their
        // rows drive the bridge
        const OrganSpec *og = k->organ;
        NoteIn on_;
        memset(&on_, 0, sizeof on_);
        on_.on = dv[0]; on_.key_off = dv[1]; on_.br = -1.0;
        if (!nv_song_organ_note(song, i, og->family, &on_))
            return -1000000000LL;
        std::vector<int> pk;
        std::map<long, long> grc;
        for (int ri = 0; ri < og->n_rank; ri++)
            if (!std::isnan(on_.rank_sp[ri]) && on_.rank_sp[ri] == dv[0]) {
                if (og->rank_choir[ri] < 0)
                    return -1000000000LL;
                pk.push_back(og->rank_choir[ri]);
                grc[(long)on_.rank_gr[ri]] = og->rank_choir[ri];
            }
        std::sort(pk.begin(), pk.end());
        pk.erase(std::unique(pk.begin(), pk.end()), pk.end());
        std::vector<double> kept;
        std::vector<long> rch;
        for (long long r = r0; r < r1; r++) {
            auto it = grc.find((long)RB(r)[C_gr]);
            if (it == grc.end())
                continue;
            kept.insert(kept.end(), RB(r), RB(r) + NC);
            rch.push_back(it->second);
        }
        nv_reg_pluck(chans[rk].first, iv[0], dv[0], held, kept.data(), (int)rch.size(), pk.data(), (int)pk.size(),
                     rch.data());
        if (inc)
            nv_reg_pluck(twin[rk], iv[0], dv[0], held, kept.data(), (int)rch.size(), pk.data(), (int)pk.size(),
                         rch.data());
    } else {
        nv_reg_strike(chans[rk].first, iv[0], dv[0], held, RB(r0), (int)(r1 - r0));
        if (inc)
            nv_reg_strike(twin[rk], iv[0], dv[0], held, RB(r0), (int)(r1 - r0));
    }
        return 0;
    }
};

// A STREAM's REGISTER SINK (nvrender's): a channel's ready rows (its place
// in `order`, each row's phase and seq) and the horizon after each note
struct RegSinkDesc {
    void *ctx;
    void (*rows)(void *ctx, int rank, const double *rows, const long long *phase, const long long *seq, long n);
    void (*horizon)(void *ctx, double h);
};
static const RegSinkDesc *g_reg_sink = nullptr;
extern "C" void nv_play_set_reg_sink(const void *s) { g_reg_sink = (const RegSinkDesc *)s; }
// the feed's settings, kept from a stream's scan for its replay
static double g_rp_beta, g_rp_full, g_rp_resid, g_rp_scale;
static int g_rp_reg = 0;

// A STREAM's SINK, WRAPPED: each note's rows cast and fed, every channel
// advanced to the next onset (int(on * SR): streamrender's), its final rows
// handed on, the horizon with them; then the note's rows to the stream
struct RegSink {
    const SinkDesc *ext = nullptr;
    RegFeed F;
    const int *played = nullptr, *kind = nullptr;
    int j = 0;
    long long fail = 0;
    std::vector<double> buf;
    static void note(void *c_, const double *at, long long i0, long long i1, double next_on)
    {
        using namespace nv::reg;
        RegSink &w = *(RegSink *)c_;
        int j = w.j++;
        if (!w.fail) {
            w.buf.assign(at, at + NC * (i1 - i0));
            for (long long r = 0; r < i1 - i0; r++)
                for (int c = 0; c < NC; c++)
                    if (w.kind[c] == 1)
                        w.buf[NC * r + c] = (double)(float)w.buf[NC * r + c];
                    else if (w.kind[c] == 2)
                        w.buf[NC * r + c] = (double)(int32_t)w.buf[NC * r + c];
            long long rc = w.F.note(j, w.played[j], w.buf.data(), i0, i0, nv_play_own_end(j, i1));
            if (rc < 0)
                w.fail = rc;
        }
        if (!w.fail) {
            const double T = std::isnan(next_on) ? INF : (double)(long long)(next_on * w.F.sr);
            double hz = T;
            for (size_t q = 0; q < w.F.order.size(); q++) {
                void *h = w.F.chans[w.F.order[q]].first;
                nv_reg_advance(h, reg_safe(h, T));      // (streamrender._register's safe horizon)
                long need = -nv_reg_take(h, nullptr, 0);
                if (need > 0) {
                    std::vector<double> o((size_t)NC * need);
                    std::vector<long long> ph(need), sq(need);
                    nv_reg_take_ready(h, o.data(), need, ph.data(), sq.data());
                    for (long r = 0; r < need; r++)
                        for (int c = 0; c < NC; c++)
                            if (w.kind[c] == 1)
                                o[NC * r + c] = (double)(float)o[NC * r + c];
                            else if (w.kind[c] == 2)
                                o[NC * r + c] = (double)(int32_t)o[NC * r + c];
                    g_reg_sink->rows(g_reg_sink->ctx, (int)q, o.data(), ph.data(), sq.data(), need);
                }
                hz = pymin(hz, nv_reg_pending_min(h));
            }
            g_reg_sink->horizon(g_reg_sink->ctx, hz);
        }
        w.ext->note(w.ext->ctx, at, i0, i1, next_on);
    }
};

long long nv_play_full(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr,
                       PyRandom *rs, double **rowsp, double *qacc, double *azimuth, const int *kind,
                       double scale, double full_db_s, double residual, double beta, long long blk,
                       long long *nnote, int *played_out, long long *row0_out, int *bands, double *offs,
                       int with_register, long long *nsym)
{
    using namespace nv::reg;
    NoteIn tb_ = *tmpl;
    tb_.blk = (double)blk;                  // (the render's block: a pulse's lead)
    tmpl = &tb_;
    int nn = nv_song_n_notes(song);
    std::vector<int> played(nn);
    std::vector<long long> row0(nn);
    std::vector<int> band_(nn);
    std::vector<double> off_(nn);
    long long nr = 0;
    // THE STORE, grown until the notes fit: each try from the same stream and tallies
    PyRandom rs0 = *rs;
    double q0[18], az0 = *azimuth;
    memcpy(q0, qacc, sizeof q0);
    const char *rpn = getenv("TUNING_NV_ROWS_PER_NOTE");
    long long cap = (rpn && atoll(rpn) > 0 ? atoll(rpn) : ROWS_PER_NOTE) * (long long)(nn > 0 ? nn : 1);
    g_cap0 = cap;
    g_need = 0;
    double *rows = nullptr;
    int got;
    // TUNING_NV_SINK_TEST=1: the notes through the sink, the store one note's
    // (ROWS_PER_NOTE x 64 to begin), the table rebuilt from what it was handed
    const char *stv = getenv("TUNING_NV_SINK_TEST");
    bool sink_test = stv && *stv && strcmp(stv, "0") != 0;
    if (sink_test) {
        cap = (rpn && atoll(rpn) > 0 ? atoll(rpn) : ROWS_PER_NOTE) * 64LL;
        g_cap0 = cap;
    }
    Collect col;
    SinkDesc sd{&col, &Collect::note};
    const void *ext = nv_play_get_sink();   // (a stream's: kept across the sink test's own)
    if (ext) {
        sink_test = false;
        cap = (rpn && atoll(rpn) > 0 ? atoll(rpn) : ROWS_PER_NOTE) * 64LL;    // (its store: a note's)
        g_cap0 = cap;
    }
    RegSink rsk;                            // (a stream's sink, its register fed as it goes)
    SinkDesc rsd{&rsk, &RegSink::note};
    const bool reg_stream = ext && g_reg_sink && with_register;
    if (reg_stream) {
        rsk.ext = (const SinkDesc *)ext;
        rsk.kind = kind;
        rsk.F.init(song, K, tmpl, beta, full_db_s, residual, scale, blk, with_register);
        g_rp_beta = beta; g_rp_full = full_db_s; g_rp_resid = residual; g_rp_scale = scale; g_rp_reg = with_register;
    }
    for (;;) {
        free(rows);
        rows = (double *)malloc(sizeof(double) * NC * cap);
        if (!rows)
            return -1000000000LL;
        *rs = rs0;
        memcpy(qacc, q0, sizeof q0);
        *azimuth = az0;
        free(col.rows);
        col = Collect();
        nv_play_set_kind(kind);             // (a parallel type's copies, cast as the table)
        if (reg_stream) {                   // (each try from the start: its channels anew)
            rsk.F.reset();
            rsk.j = 0;
            rsk.fail = 0;
            rsk.played = played.data();
        }
        nv_play_set_sink(sink_test ? (const void *)&sd : reg_stream ? (const void *)&rsd : ext);
        got = nv_play(song, K, tmpl, br, nbr, rs, rows, cap, qacc, azimuth, &nr, played.data(), row0.data(),
                      band_.data(), off_.data());
        nv_play_set_sink(ext);
        nv_play_set_kind(nullptr);
        if (got != NV_TOO_SMALL)
            break;
        cap *= 2;
    }
    if (sink_test) {
        free(rows);
        if (col.fail || (got >= 0 && col.n != nr)) {
            fprintf(stderr, "nv_play_full: the sink test's rows came out wrong (%lld of %lld)\n", col.n, nr);
            free(col.rows);
            return -1000000000LL;
        }
        rows = col.rows ? col.rows : (double *)malloc(sizeof(double) * NC);
        col.rows = nullptr;
    }
    if (cap != g_cap0 && got >= 0)
        g_need = nr;                        // (it grew: the rows the song needed)
    if (sink_test)
        cap = col.cap > 0 ? col.cap : 1;    // (the table's room, not the store's: the strings come after)
    *rowsp = rows;
    if (got < 0)
        return got;
    if (nnote)
        *nnote = nr;
    if (played_out)
        for (int j = 0; j < nn; j++) {
            played_out[j] = played[j];
            row0_out[j] = row0[j];
            bands[j] = band_[j];
            offs[j] = off_[j];
        }
    if (ext) {
        // A STREAM: every note's rows went to its sink, so nothing below has a
        // table to read. The strings that would need one are refused.
        for (int j = 0; j < nn; j++) {
            const NoteClass *k = K[nv_song_kidx(song, played[j])];
            if (with_register && (k->reg_gain != 0.0 || k->reg_knock != 0.0) && !reg_stream)
                nv_stream_refuse("the register's strings");
            if (k->sym_kind)
                nv_stream_refuse("sympathetic strings");
        }
        if (rsk.fail)
            return rsk.fail;
        g_rp_rs = rs0;                      // (the replay's start, and the store that fit)
        memcpy(g_rp_q, q0, sizeof g_rp_q);
        g_rp_az = az0;
        g_rp_cap = cap;
        if (nsym)
            *nsym = 0;
        return nr;
    }
    auto cast = [&](double *r) {
        for (int c = 0; c < NC; c++)
            if (kind[c] == 1)
                r[c] = (double)(float)r[c];
            else if (kind[c] == 2)
                r[c] = (double)(int32_t)r[c];
    };
    for (long long r = 0; r < nr; r++)
        cast(rows + NC * r);
    const double sr = tmpl->sr, total = nv_song_total(song);
    const double LN10_20 = log(10.0) / 20.0;
    RegFeed F_;
    F_.init(song, K, tmpl, beta, full_db_s, residual, scale, blk, with_register);
    for (int j = 0; j < nn; j++) {
        long long rc_ = F_.note(j, played[j], rows, 0, row0[j], nv_play_own_end(j, j + 1 < nn ? row0[j + 1] : nr));
        if (rc_ < 0)
            return rc_;
    }
    auto &order = F_.order;
    auto &chans = F_.chans;
    auto &sym_order = F_.sym_order;
    auto &sym_k = F_.sym_k;
    auto &twin = F_.twin;
    auto &trows = F_.trows;
    auto &tkey = F_.tkey;
    const bool inc = F_.inc;
    auto twin_take = [&](long long rk) { F_.twin_take(rk); };
    long long n = nr;
    // sympathetic.expand, before the register's: each channel's strikes (its
    // rows by onset, 64 samples a bin; not a late copy's or a ring row's),
    // each answered by its responders -- the strike's rows at the
    // responder's pitch (the table's, at the strike), at its drive
    {
        std::vector<double> extra;
        std::map<std::pair<long long, int>, std::vector<double>> sym_cache;    // (channel, key): responders()
        for (long long ch : sym_order) {
            const NoteClass *k = sym_k[ch];
            std::vector<long long> grp_key;
            std::map<long long, std::vector<long long>> grp;
            for (long long r = 0; r < nr; r++) {
                const double *x = rows + NC * r;
                if ((long long)x[C_mch] != ch)
                    continue;
                double d2 = nearbyint(x[C_dr] * 100.0) / 100.0;     // (np.round(dr, 2))
                if (d2 == 0.75 || d2 == 0.25 || d2 == 0.9 || d2 == 0.1)
                    continue;
                long long g = (long long)nearbyint(x[C_non] / 64.0);
                if (!grp.count(g))
                    grp_key.push_back(g);
                grp[g].push_back(r);
            }
            const bool fixed = k->sym_kind == 1 || k->sym_kind == 3, ring_law = k->sym_kind == 1;
            for (long long g : grp_key) {
                const std::vector<long long> &ix = grp[g];
                double nmin = rows[NC * ix[0] + C_non], f0 = rows[NC * ix[0] + C_nf];
                for (long long r : ix) {
                    nmin = pymin(nmin, rows[NC * r + C_non]);
                    f0 = pymin(f0, rows[NC * r + C_nf]);
                }
                double tab[128];
                nv_song_note_table(song, ch, nmin / sr, k->indian, tab);   // (_F_SYM)
                // _nearest_key: the table's key nearest f0 in cents (the first of equals)
                int drv = -1;
                double bd = 0.0;
                for (int q = 0; q < 128; q++) {
                    if (!(tab[q] > 0.0))
                        continue;
                    double d = fabs(log2(pymax(tab[q], 1e-9) / pymax(f0, 1e-9)));
                    if (drv < 0 || d < bd) {
                        drv = q;
                        bd = d;
                    }
                }
                // responders(): the strings the strike is not on, over the floor,
                // strongest first (stable), the first sym_top
                std::vector<int> rs_s;
                std::vector<double> rs_d, rs_c;
                if (k->sym_kind == 3) {
                    // BY COINCIDENCE (responders, a fixed set): each string the
                    // strike is not on, at the table's pitch (its own cents),
                    // as loud as _coupling says, over the floor
                    const VoiceSnap *dv_ = (const VoiceSnap *)nv_song_sym_get(song, ch);
                    int ra = nv_song_raga_sa(song);
                    int tonic = k->indian && ra >= 0 ? ra : k->sym_tonic;
                    auto sc = sym_cache.find(std::make_pair(ch, drv));
                    if (sc == sym_cache.end()) {
                        std::vector<double> dd(k->sym_n, -1.0);
                        for (int q = 0; q < k->sym_n && dv_; q++) {
                            int pitch = tonic + k->sym_pitch[q], s = pitch - drv;
                            if (s == 0)
                                continue;
                            double rf = pitch >= 0 && pitch < 128 && tab[pitch] > 0.0 ? tab[pitch]
                                                                                       : f0 * pow(2.0, s / 12.0);
                            rf *= pow(2.0, k->sym_cents[q] / 1200.0);
                            VoiceInit rc = k->init;
                            rc.fixed_touch = tmpl->fixed_touch;
                            VoiceSnap rv;
                            VoiceNote ro;
                            nv_voice_init(&rc, &k->tmpl, rf, 0.0, 1.0, 1.0, 0.0, nullptr, &rv, &ro);
                            dd[q] = nv_sym_coupling(dv_, &rv, k->sym_g, k->sym_wmin) * k->sym_d[q];
                        }
                        sc = sym_cache.emplace(std::make_pair(ch, drv), dd).first;
                    }
                    for (int q = 0; q < k->sym_n; q++) {
                        int s = tonic + k->sym_pitch[q] - drv;
                        if (s == 0 || !(sc->second[q] >= k->sym_floor))
                            continue;
                        rs_s.push_back(s);
                        rs_d.push_back(sc->second[q]);
                        rs_c.push_back(k->sym_cents[q]);
                    }
                }
                for (int q = 0; q < (k->sym_kind == 3 ? 0 : k->sym_n); q++) {
                    int s = k->sym_kind == 1 ? k->sym_pitch[q] - drv : k->sym_pitch[q];
                    if (k->sym_kind == 1 && (s == 0 || !(k->sym_d[q] >= k->sym_floor)))
                        continue;
                    rs_s.push_back(s);
                    rs_d.push_back(k->sym_d[q]);
                    rs_c.push_back(k->sym_cents[q]);
                }
                std::vector<int> ordr(rs_s.size());
                for (size_t q = 0; q < ordr.size(); q++)
                    ordr[q] = (int)q;
                if (k->sym_kind == 1 || k->sym_kind == 3) {
                    std::stable_sort(ordr.begin(), ordr.end(), [&](int a, int b) { return -rs_d[a] < -rs_d[b]; });
                    if ((int)ordr.size() > k->sym_top)
                        ordr.resize(k->sym_top);
                }
                auto in_tab = [&](int key) { return key >= 0 && key < 128 && tab[key] > 0.0; };
                for (int q : ordr) {
                    int semis = rs_s[q];
                    double drive = rs_d[q];
                    double tune = rs_c[q] != 0.0 ? pow(2.0, rs_c[q] / 1200.0) : 1.0;
                    double ratio;
                    if (fixed && drv >= 0 && in_tab(drv + semis) && f0 > 0)
                        ratio = tab[drv + semis] / f0;
                    else if (drv >= 0 && in_tab(drv + semis) && tab[drv] > 0)
                        ratio = tab[drv + semis] / tab[drv];
                    else
                        ratio = pow(2.0, semis / 12.0);
                    ratio *= tune;
                    for (long long i : ix) {
                        const double *x = rows + NC * i;
                        if (!(x[C_nf] * ratio < sr * 0.5))
                            continue;
                        size_t o = extra.size();
                        extra.insert(extra.end(), x, x + NC);
                        double *e = extra.data() + o;
                        e[C_om] = x[C_om] * ratio;
                        e[C_nf] = x[C_nf] * ratio;
                        e[C_p0] = x[C_p0] * ratio;
                        e[C_p0R] = x[C_p0R] * ratio;
                        if (fixed || k->sym_nobend)
                            e[C_br] = -1;
                        if (ring_law && e[C_aft] > 0.0) {
                            e[C_logr] = e[C_logrA];
                            e[C_aft] = 0.0;
                        }
                        e[C_aL] = x[C_aL] * drive;
                        e[C_aR] = x[C_aR] * drive;
                        e[C_aM] = x[C_aM] * drive;
                        cast(e);
                    }
                }
            }
        }
        long long m = (long long)(extra.size() / NC);
        if (m) {
            if (n + m > cap) {
                cap = n + m;
                double *grown = (double *)realloc(rows, sizeof(double) * NC * cap);
                if (!grown)
                    return -1000000000LL;
                rows = grown;
                *rowsp = rows;
            }
            memcpy(rows + NC * n, extra.data(), sizeof(double) * extra.size());
            n += m;
        }
        if (nsym)
            *nsym = m;
    }
    if (inc) {
        long bad = 0, all = 0;
        for (long long rk : order) {
            void *h = chans[rk].first;
            nv_reg_finish(twin[rk]);
            twin_take(rk);
            nv_reg_free(twin[rk]);
            nv_reg_finish(h);               // (the whole render's: finish is advance(INF), again harmless)
            long need = -nv_reg_take(h, nullptr, 0);
            std::vector<double> w((size_t)NC * (need > 0 ? need : 0));
            if (need > 0)
                nv_reg_take(h, w.data(), need);
            std::vector<long> ix(tkey[rk].size());
            for (size_t q = 0; q < ix.size(); q++)
                ix[q] = (long)q;
            std::stable_sort(ix.begin(), ix.end(), [&](long a, long b) { return tkey[rk][a] < tkey[rk][b]; });
            long n_ = (long)ix.size(), first = -1;
            if (n_ != (need > 0 ? need : 0))
                first = 0;
            for (long q = 0; first < 0 && q < n_; q++)
                if (memcmp(&trows[rk][(size_t)NC * ix[q]], &w[(size_t)NC * q], sizeof(double) * NC) != 0)
                    first = q;
            all += need > 0 ? need : 0;
            if (first >= 0) {
                bad++;
                fprintf(stderr, "reg inc: channel %lld: DIFFERS (%ld rows taken as it went, %ld whole; first at %ld)\n",
                        rk, n_, need, first);
            }
        }
        fprintf(stderr, "reg inc: %zu channel(s), %ld rows: %s\n", order.size(), all,
                bad ? "DIFFER" : "identical taken as it went");
    }
    for (long long rk : order) {
        void *h = chans[rk].first;
        nv_reg_finish(h);
        long need = -nv_reg_take(h, nullptr, 0);         // its rows (the store's room asked first)
        if (n + need > cap) {
            cap = n + need;
            double *grown = (double *)realloc(rows, sizeof(double) * NC * cap);
            if (!grown)
                return -1000000000LL;
            rows = grown;
            *rowsp = rows;
        }
        long got2 = nv_reg_take(h, rows + NC * n, (long)(cap - n));
        nv_reg_free(h);
        for (long q = 0; q < got2; q++)
            cast(rows + NC * (n + q));
        n += got2;
    }
    return n;
}

// A STREAM's RENDER PASS: the notes played again, from the state the last
// nv_play_full (a stream's) began at, into the sink set now -- the same rows,
// in the same order. Returns the rows, or < 0 as nv_play.
long long nv_play_replay(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr,
                         PyRandom *rs, double *qacc, double *azimuth, const int *kind, long long blk)
{
    NoteIn tb_ = *tmpl;
    tb_.blk = (double)blk;
    int nn = nv_song_n_notes(song);
    std::vector<int> played(nn);
    std::vector<long long> row0(nn);
    std::vector<int> band_(nn);
    std::vector<double> off_(nn);
    double *rows = (double *)malloc(sizeof(double) * nv::reg::NC * (g_rp_cap > 0 ? g_rp_cap : 1));
    if (!rows)
        return -1000000000LL;
    *rs = g_rp_rs;
    memcpy(qacc, g_rp_q, sizeof g_rp_q);
    *azimuth = g_rp_az;
    long long nr = 0;
    const void *ext = nv_play_get_sink();
    RegSink rsk;
    SinkDesc rsd{&rsk, &RegSink::note};
    if (ext && g_reg_sink && g_rp_reg) {
        rsk.ext = (const SinkDesc *)ext;
        rsk.kind = kind;
        rsk.played = played.data();
        rsk.F.init(song, K, &tb_, g_rp_beta, g_rp_full, g_rp_resid, g_rp_scale, blk, g_rp_reg);
        nv_play_set_sink(&rsd);
    }
    nv_play_set_kind(kind);
    int got = nv_play(song, K, &tb_, br, nbr, rs, rows, g_rp_cap, qacc, azimuth, &nr, played.data(), row0.data(),
                      band_.data(), off_.data());
    nv_play_set_kind(nullptr);
    nv_play_set_sink(ext);
    if (got >= 0 && rsk.fail)
        got = (int)rsk.fail;
    free(rows);
    return got < 0 ? got : nr;
}

}  // extern "C"
