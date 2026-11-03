// tubeamp.cpp -- THE VALVE STAGE (tubeamp.py) on a finished table, as
// blockrender's _prep_amplifier runs it: each amplified channel cut at every
// note boundary, each segment's sounding partials merged by frequency
// (combine), synthesised, driven through the valve's curve, its distortion
// residual windowed and transformed, its peaks taken as partials and
// scaled to the residual's power (emit), appended after the table, each a
// copy of the loudest row it came from (segment).
//
// SHARED WITH THE PYTHON: the signal's synthesis (nv_amp_synth), the
// Blackman-Harris window (nv_amp_window) and the real FFT (nv_rfft) are
// the ones tubeamp.py itself calls, so its numerics are these, on every
// machine; the rest is ported, bit for bit, with libm's pow, hypot and
// atan2 where the Python takes native's.

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <map>
#include <mutex>
#include <thread>
#include <vector>

#include "nv.h"

namespace {

// tubeamp.py's constants
const double EXPONENT = 1.5, BIAS = 1.0, IMBALANCE = 0.06, CEILING = 6.0, KNEE = 3.0, MIN_HZ = 20.0;
const double WINDOW_S = 1.0;
const int OVERSAMPLE = 2, KEEP_PEAKS = 400, KEEP_PARTIALS = 96;
const double PEAK_FLOOR = 1e-3;

// the FFT's twiddles for n, cached: w[k] = exp(-2 pi i k / n), k < n/2
std::mutex tw_mu;
std::map<long, std::vector<double>> tw_cache;

const std::vector<double> &twiddles(long n)
{
    std::lock_guard<std::mutex> g(tw_mu);
    auto it = tw_cache.find(n);
    if (it != tw_cache.end())
        return it->second;
    std::vector<double> &w = tw_cache[n];
    w.resize(n);
    for (long k = 0; k < n / 2; k++) {
        double a = (2.0 * M_PI * (double)k) / (double)n;
        w[2 * k] = cos(a);
        w[2 * k + 1] = -sin(a);
    }
    return w;
}

// numpy's pairwise sum (DOUBLE_pairwise_sum, PW_BLOCKSIZE 128), stride 1
double pairwise(const double *a, long n)
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
    return pairwise(a, n2) + pairwise(a + n2, n - n2);
}

// np.sum / np.add.reduce of a contiguous float64 array: the identity, then the pairwise sum
double npsum(const double *a, long n) { return 0.0 + pairwise(a, n); }

// tubeamp.curve's half: a 3/2-law triode with a floor and a ceiling
double half(double g, double bi, double imax)
{
    double v = bi + g;
    double i = pow(v > 0.0 ? v : 0.0, EXPONENT);       // np.maximum(bi + g, 0.0) ** EXPONENT
    double u = i / imax;
    return imax * u / pow(1.0 + pow(u, KNEE), 1.0 / KNEE);
}

struct Valve {
    double a, b, imax, q;
    explicit Valve(double imbalance)
    {
        a = BIAS * (1.0 + imbalance);
        b = BIAS * (1.0 - imbalance);
        imax = CEILING * pow(BIAS, EXPONENT);
        q = half(0.0, a, imax) - half(0.0, b, imax);
    }
    double curve(double v) const { return (half(v, a, imax) - half(-v, b, imax)) - q; }
    // small_signal: d(curve)/dv at the operating point
    double small_signal() const
    {
        double h = 1e-5;
        return (curve(h) - curve(-h)) / (2.0 * h);
    }
};

struct Partial {
    double hz, amp, ph;
};

}  // namespace

extern "C" {

// sum A cos(2 pi F t + P) over the partials, t = i / fs (np.arange(n) / fs):
// tubeamp._synth_loop's, each sample built by the same operations in the
// same partial order, on every core
void nv_amp_synth(const double *a, const double *f, const double *p, long np_, long n, double fs, double *x)
{
    for (long i = 0; i < n; i++)
        x[i] = 0.0;
    const long CH = 8192;
    long nchunk = (n + CH - 1) / CH;
    unsigned nt = std::thread::hardware_concurrency();
    if (nt < 1)
        nt = 1;
    if ((long)nt > nchunk)
        nt = (unsigned)nchunk;
    auto job = [&](unsigned w) {
        for (long c = w; c < nchunk; c += nt) {
            long s = c * CH, e = std::min(n, s + CH);
            for (long q = 0; q < np_; q++) {
                double A = a[q], P = p[q], W = 2.0 * M_PI * f[q];
                for (long i = s; i < e; i++)
                    x[i] += A * cos(W * ((double)i / fs) + P);
            }
        }
    };
    std::vector<std::thread> th;
    for (unsigned w = 1; w < nt; w++)
        th.emplace_back(job, w);
    job(0);
    for (auto &t : th)
        t.join();
}

// tubeamp._window_of: the 4-term Blackman-Harris over n
void nv_amp_window(long n, double *w)
{
    for (long i = 0; i < n; i++) {
        double k = (2.0 * M_PI * (double)i) / (double)n;
        w[i] = 0.35875 - 0.48829 * cos(k) + 0.14128 * cos(2.0 * k) - 0.01168 * cos(3.0 * k);
    }
}

// THE FFT: an iterative radix-2 transform in place (re, im; n a power of
// two) with libm's twiddles -- the Python's own (native.xrfft, xfft), so
// both are this, on every machine
static void fft_core(std::vector<double> &re, std::vector<double> &im, long n)
{
    const std::vector<double> &w = twiddles(n);
    int bits = 0;
    while ((1L << bits) < n)
        bits++;
    for (long i = 0; i < n; i++) {
        long r = 0;
        for (int b = 0; b < bits; b++)
            if (i & (1L << b))
                r |= 1L << (bits - 1 - b);
        if (r > i) {
            std::swap(re[i], re[r]);
            std::swap(im[i], im[r]);
        }
    }
    for (long len = 2; len <= n; len <<= 1) {
        long half_ = len >> 1, step = n / len;
        for (long s = 0; s < n; s += len)
            for (long j = 0; j < half_; j++) {
                double wr = w[2 * j * step], wi = w[2 * j * step + 1];
                long u = s + j, v = u + half_;
                double tr = re[v] * wr - im[v] * wi, ti = re[v] * wi + im[v] * wr;
                re[v] = re[u] - tr;
                im[v] = im[u] - ti;
                re[u] = re[u] + tr;
                im[u] = im[u] + ti;
            }
    }
}

// The real FFT of x: out[2k], out[2k+1] bin k's real and imaginary parts,
// k <= n/2 -- np.fft.rfft's layout, unnormalised
int nv_rfft(const double *x, long n, double *out)
{
    if (n < 2 || (n & (n - 1)))
        return -1;
    std::vector<double> re(x, x + n), im(n, 0.0);
    fft_core(re, im, n);
    for (long k = 0; k <= n / 2; k++) {
        out[2 * k] = re[k];
        out[2 * k + 1] = im[k];
    }
    return 0;
}

// ...and the complex FFT of z (interleaved), np.fft.fft's, unnormalised
int nv_cfft(const double *z, long n, double *out)
{
    if (n < 2 || (n & (n - 1)))
        return -1;
    std::vector<double> re(n), im(n);
    for (long i = 0; i < n; i++) {
        re[i] = z[2 * i];
        im[i] = z[2 * i + 1];
    }
    fft_core(re, im, n);
    for (long k = 0; k < n; k++) {
        out[2 * k] = re[k];
        out[2 * k + 1] = im[k];
    }
    return 0;
}

}  // extern "C"

namespace {

// tubeamp.emit: the distortion partials of these, driven at drive (against
// the signal's own peak: no reference), the valve at imbalance
std::vector<Partial> emit(const std::vector<double> &f, const std::vector<double> &a, const std::vector<double> &p,
                          double sr, double drive, double imbalance)
{
    std::vector<Partial> out;
    if (f.size() < 2)
        return out;
    long n0 = (long)nearbyint(WINDOW_S * sr);
    double lg = log((double)(n0 > 1 ? n0 : 1)) / log(2.0);
    long e2 = (long)ceil(lg);
    long n = 1L << (e2 > 8 ? e2 : 8);
    n *= OVERSAMPLE;
    double fs = sr * (double)OVERSAMPLE;
    std::vector<double> x(n);
    nv_amp_synth(a.data(), f.data(), p.data(), (long)f.size(), n, fs, x.data());
    double pk = 0.0;
    for (long i = 0; i < n; i++)
        pk = std::max(pk, fabs(x[i]));                  // np.abs(x).max()
    if (pk <= 0.0)
        return out;
    double unit = drive * BIAS / pk;
    for (long i = 0; i < n; i++)
        x[i] *= unit;
    Valve V(imbalance);
    double g = V.small_signal();
    std::vector<double> r(n);
    for (long i = 0; i < n; i++)
        r[i] = V.curve(x[i]) - g * x[i];
    double mean = npsum(r.data(), n) / (double)n;
    for (long i = 0; i < n; i++)
        r[i] -= mean;
    std::vector<double> w(n), rw(n);
    nv_amp_window(n, w.data());
    for (long i = 0; i < n; i++)
        rw[i] = r[i] * w[i];
    std::vector<double> R(2 * (n / 2 + 1)), X0(2 * (n / 2 + 1));
    nv_rfft(rw.data(), n, R.data());
    double df = fs / (double)n;
    long lim = (long)(std::min(sr * 0.5, fs * 0.5) / df);
    if (lim < 8)
        return out;
    std::vector<double> e(lim);
    for (long k = 0; k < lim; k++) {
        double m = hypot(R[2 * k], R[2 * k + 1]);
        e[k] = m * m;                                   // np.abs(R) ** 2 (a square)
    }
    nv_rfft(r.data(), n, X0.data());
    std::vector<double> e0(lim > 1 ? lim - 1 : 0);
    for (long k = 1; k < lim; k++) {
        double m = hypot(X0[2 * k], X0[2 * k + 1]);
        e0[k - 1] = m * m;
    }
    double power = (2.0 * npsum(e0.data(), (long)e0.size())) / ((double)n * (double)n);
    // the peaks: local maxima, over floor^2 of the strongest, the strongest keep
    std::vector<long> loc;
    for (long k = 1; k < lim - 1; k++)
        if (e[k] > e[k - 1] && e[k] >= e[k + 1])
            loc.push_back(k);
    if (loc.empty())
        return out;
    double emax = e[loc[0]];
    for (long k : loc)
        emax = std::max(emax, e[k]);
    double thr = emax * pow(PEAK_FLOOR, 2.0);
    std::vector<long> kept;
    for (long k : loc)
        if (e[k] > thr)
            kept.push_back(k);
    loc.swap(kept);
    if (loc.empty())
        return out;
    if ((long)loc.size() > KEEP_PEAKS) {
        std::vector<long> idx(loc.size());
        for (size_t i = 0; i < idx.size(); i++)
            idx[i] = (long)i;
        std::stable_sort(idx.begin(), idx.end(), [&](long u, long v) { return -e[loc[u]] < -e[loc[v]]; });
        std::vector<long> top;
        for (int i = 0; i < KEEP_PEAKS; i++)
            top.push_back(loc[idx[i]]);
        std::sort(top.begin(), top.end());
        loc.swap(top);
    }
    // every bin to its nearest peak (the lower on a tie), in bin order
    long L = (long)loc.size();
    std::vector<std::vector<long>> bins(L);
    for (long k = 0; k < lim; k++) {
        long j = (long)(std::lower_bound(loc.begin(), loc.end(), k) - loc.begin());
        long jl = std::min(std::max(j - 1, 0L), L - 1), jr = std::min(std::max(j, 0L), L - 1);
        long own = std::labs(loc[jl] - k) <= std::labs(loc[jr] - k) ? jl : jr;
        bins[own].push_back(k);
    }
    std::vector<double> eb;
    for (long c = 0; c < L; c++) {
        eb.resize(bins[c].size());
        for (size_t q = 0; q < bins[c].size(); q++)
            eb[q] = e[bins[c][q]];
        double tote = npsum(eb.data(), (long)eb.size());
        if (tote <= 0.0)
            continue;
        long km = loc[c];
        double gc;
        if (0 < km && km < lim - 1) {
            double y[3];
            for (int d = -1; d <= 1; d++)
                y[d + 1] = 0.5 * log(std::max(e[km + d], 1e-300));
            double den = y[0] - 2.0 * y[1] + y[2];
            gc = (double)km + (den != 0.0 ? std::max(-0.5, std::min(0.5, 0.5 * (y[0] - y[2]) / den)) : 0.0);
        } else {
            gc = (double)km;
        }
        double hz = gc * df;
        if (hz < MIN_HZ || hz >= sr * 0.5)
            continue;
        double ph = atan2(R[2 * km + 1], R[2 * km]) - 2.0 * M_PI * (gc - (double)km) * (double)(n - 1) / (2.0 * (double)n);
        out.push_back(Partial{hz, sqrt(tote), ph});
    }
    double have = 0.0;
    for (const Partial &q : out)
        have += q.amp * q.amp;
    have *= 0.5;
    double sc = have > 0.0 ? sqrt(power / have) / (g * unit) : 0.0;
    for (Partial &q : out)
        q.amp *= sc;
    return out;
}

}  // namespace

extern "C" {

// THE AMPLIFIER over a table: rows (NCOLS each, *Pp of them, realloc'd), the
// channels (chans[k] at drives[k], in _AMP_CH's order); each channel's
// direct rows cut at every onset and end, each segment's products appended
// (after every channel's), a damper's dk/dg copied with them. Returns the
// products made.
long long nv_amp_expand(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                        const double *drives, double sr)
{
    enum { cOM = 0, cP0 = 1, cP0R = 2, cAL = 3, cAR = 4, cAM = 5, cMCH = 6, cDR = 10, cNF = 11, cNON = 12,
           cNOFF = 13, cDELL = 37, cDELR = 38, cFX = 43, cMK = 44 };
    const long long n = *Pp;
    double *rows = *rowsp;
    auto at = [&](long long i, int c) { return rows[(size_t)NCOLS * i + c]; };
    std::vector<double> extra;
    std::vector<long long> src_of;
    for (int k = 0; k < nch; k++) {
        double drive = drives[k];
        if (drive <= 0.0)
            continue;
        std::vector<long long> rs;
        for (long long i = 0; i < n; i++)
            if ((long long)at(i, cMCH) == chans[k] && at(i, cDR) > 0.5)
                rs.push_back(i);
        if (rs.size() < 2)
            continue;
        std::vector<double> edges;
        for (long long i : rs) {
            edges.push_back(at(i, cNON));
            edges.push_back(at(i, cNOFF));
        }
        std::sort(edges.begin(), edges.end());
        edges.erase(std::unique(edges.begin(), edges.end()), edges.end());
        for (size_t s = 0; s + 1 < edges.size(); s++) {
            double a = edges[s], b = edges[s + 1];
            if (b - a < sr * 0.01)
                continue;
            std::vector<long long> live;
            for (long long i : rs)
                if (at(i, cNON) <= a + 1e-6 && at(i, cNOFF) >= b - 1e-6)
                    live.push_back(i);
            if (live.size() < 2)
                continue;
            // combine: partials sharing a frequency (to 0.01 Hz) as one complex amplitude
            std::vector<long long> key(live.size());
            std::vector<double> fs(live.size()), zr(live.size()), zi(live.size());
            for (size_t q = 0; q < live.size(); q++) {
                double om = at(live[q], cOM);
                fs[q] = om * sr / (2.0 * M_PI);
                double ps = at(live[q], cP0) + om * a;
                double am = at(live[q], cAM);
                key[q] = (long long)nearbyint(fs[q] / 0.01);
                double c = cos(ps), si = sin(ps);
                zr[q] = am * c;
                zi[q] = am * si;
            }
            std::vector<long long> uk(key);
            std::sort(uk.begin(), uk.end());
            uk.erase(std::unique(uk.begin(), uk.end()), uk.end());
            size_t nu = uk.size();
            std::vector<double> ar(nu, 0.0), ai(nu, 0.0), fsum(nu, 0.0), cnt(nu, 0.0);
            for (size_t q = 0; q < live.size(); q++) {
                size_t u = (size_t)(std::lower_bound(uk.begin(), uk.end(), key[q]) - uk.begin());
                ar[u] += zr[q];
                ai[u] += zi[q];
                fsum[u] += fs[q];
                cnt[u] += 1.0;
            }
            std::vector<double> F(nu), A(nu), Ph(nu);
            for (size_t u = 0; u < nu; u++) {
                F[u] = fsum[u] / cnt[u];
                A[u] = hypot(ar[u], ai[u]);
                Ph[u] = atan2(ai[u], ar[u]);
            }
            if (nu < 2)
                continue;
            if ((long)nu > KEEP_PARTIALS) {
                std::vector<size_t> idx(nu);
                for (size_t q = 0; q < nu; q++)
                    idx[q] = q;
                std::stable_sort(idx.begin(), idx.end(), [&](size_t u, size_t v) { return -A[u] < -A[v]; });
                std::vector<double> F2, A2, P2;
                for (int q = 0; q < KEEP_PARTIALS; q++) {
                    F2.push_back(F[idx[q]]);
                    A2.push_back(A[idx[q]]);
                    P2.push_back(Ph[idx[q]]);
                }
                F.swap(F2);
                A.swap(A2);
                Ph.swap(P2);
            }
            long long src = live[0];
            for (long long i : live)
                if (at(i, cAM) > at(src, cAM))
                    src = i;
            std::vector<Partial> got = emit(F, A, Ph, sr, drive, IMBALANCE);
            for (const Partial &q : got) {
                size_t o = extra.size();
                extra.insert(extra.end(), rows + (size_t)NCOLS * src, rows + (size_t)NCOLS * (src + 1));
                double *e = extra.data() + o;
                double w = 2.0 * M_PI * q.hz / sr;
                e[cOM] = w;
                e[cNF] = q.hz;
                e[cNON] = (double)(long long)a;
                e[cNOFF] = (double)(long long)b;
                e[cP0] = q.ph - w * a;
                e[cP0R] = q.ph - w * a - w * (at(src, cDELR) - at(src, cDELL));
                e[cFX] = -1.0;
                e[cMK] = 0.0;
                double sc = q.amp / std::max(at(src, cAM), 1e-12);
                e[cAL] = at(src, cAL) * sc;
                e[cAR] = at(src, cAR) * sc;
                e[cAM] = q.amp;
                src_of.push_back(src);
            }
        }
    }
    long long m = (long long)src_of.size();
    if (m) {
        rows = (double *)realloc(*rowsp, sizeof(double) * NCOLS * (size_t)(n + m));
        memcpy(rows + (size_t)NCOLS * n, extra.data(), sizeof(double) * extra.size());
        *rowsp = rows;
        if (dm[0]) {
            int32_t *dk = (int32_t *)realloc(dm[0], sizeof(int32_t) * (size_t)(n + m));
            float *dg = (float *)realloc(dm[1], sizeof(float) * (size_t)(n + m));
            for (long long q = 0; q < m; q++) {
                dk[n + q] = dk[src_of[q]];
                dg[n + q] = dg[src_of[q]];
            }
            dm[0] = dk;
            dm[1] = dg;
        }
        *Pp = n + m;
    }
    return m;
}

}  // extern "C"
