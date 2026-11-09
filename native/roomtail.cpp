// roomtail.cpp -- roomtail.py's late field, drawn natively: the diffuse tail
// (build_ir) and the room's low modes (modal_ir) from a room's spec
// (roomtail.tail_spec: what does not depend on the stage) and the stage's
// directivity per octave (band_q: live._room_band_q, the rig's), bit for bit
// as live.room_irs draws them -- numpy's legacy RandomState (MT19937 seeded
// as mt19937_seed, its polar gauss), numpy's pocketfft (pocketfft.c), its
// pairwise sums in 8192-element buffers, libm where roomtail.py now uses
// native's libm wrappers. A device's tail (the plate, the delays) is not here.
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <vector>

#include "pycompat.h"

extern "C" int nv_pocket_rfft(const double *x, int n, double *out);
extern "C" int nv_pocket_irfft(const double *c, int n, double *out);
extern "C" void nv_cabs_n(long n, const double *z, double *out);

namespace {

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

// np.sum / np.mean's sum of a contiguous float64 array: each of the
// reduction's 8192-element buffers its pairwise sum, in turn
double npsum(const double *a, long n)
{
    double r = 0.0;
    for (long i = 0; i < n; i += 8192)
        r += pairwise(a + i, std::min(8192L, n - i));
    return r;
}

const double OCTAVES[9] = {63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0};

// roomtail.tail_spec's layout
enum { S_N, S_KIND, S_VOLUME, S_R, S_T0, S_MFP, S_FS, S_C, S_LX, S_LY, S_LZ, S_LIS, S_SRC = S_LIS + 3,
       S_OCT = S_SRC + 3, S_LEN = S_OCT + 27 };

// numpy's legacy RandomState(seed): mt19937_seed, legacy_double, legacy_gauss
struct Legacy {
    PyRandom r;
    explicit Legacy(uint32_t seed)
    {
        pyr_init_genrand(&r, seed);
        r.has_gauss = 0;
        r.gauss_next = 0.0;
    }
    double uniform() { return pyr_random(&r); }
    double gauss()
    {
        if (r.has_gauss) {
            double t = r.gauss_next;
            r.has_gauss = 0;
            r.gauss_next = 0.0;
            return t;
        }
        double x1, x2, r2;
        do {
            x1 = 2.0 * uniform() - 1.0;
            x2 = 2.0 * uniform() - 1.0;
            r2 = x1 * x1 + x2 * x2;
        } while (r2 >= 1.0 || r2 == 0.0);
        double f = sqrt(-2.0 * log(r2) / r2);
        r.gauss_next = f * x1;
        r.has_gauss = 1;
        return f * x2;
    }
};

// decay_and_level's reverberant ratio at octave i: 16 pi r^2 / (Q R)
double ratio_at(const double *sp, int i, double qf)
{
    const double r = sp[S_R], R = sp[S_OCT + 3 * i + 1];
    return 16.0 * M_PI * r * r / ((qf < 1e-3 ? 1e-3 : qf) * R);
}

// band_q.get(f, q) if band_q else q (NaN: not measured)
double q_at(const double *bq, int has, int i, double q)
{
    return has && !std::isnan(bq[i]) ? bq[i] : q;
}

std::vector<double> rfft(const std::vector<double> &x, long n)
{
    std::vector<double> in(x.begin(), x.end());
    in.resize(n, 0.0);                          // (numpy pads to n)
    std::vector<double> out(2 * (n / 2 + 1));
    nv_pocket_rfft(in.data(), (int)n, out.data());
    return out;
}

std::vector<double> irfft(const std::vector<double> &c, long n)
{
    std::vector<double> out(n);
    nv_pocket_irfft(c.data(), (int)n, out.data());
    return out;
}

}  // namespace

// build_ir(props, sr, q=2.0, seed, channels=2, band_q): its n samples, two
// channels interleaved
static std::vector<double> build_ir(const double *sp, const double *bq, int has_bq, int sr, int seed)
{
    const double q = 2.0, c = 343.0, volume = sp[S_VOLUME], r = sp[S_R], t0 = sp[S_T0], mfp = sp[S_MFP];
    const double fs_hz = sp[S_FS];
    double t60[9], ratio[9], t60_max = 0.0;
    for (int i = 0; i < 9; i++) {
        t60[i] = sp[S_OCT + 3 * i];
        ratio[i] = ratio_at(sp, i, q_at(bq, has_bq, i, q));
        t60_max = i == 0 ? t60[i] : std::max(t60_max, t60[i]);
    }
    const double onset = sqrt(volume) / 1000.0;
    const long n = (long)((onset + t60_max * 1.2) * sr);
    std::vector<double> t(n), order(n), gate(n), p_arr(n), amp(n);
    const double rc = r / c, K = 4.0 * M_PI * pow(c, 3.0);
    for (long i = 0; i < n; i++) {
        t[i] = (double)i / (double)sr;
        const double tau = t[i] + rc;
        order[i] = c * tau / mfp;
        gate[i] = t[i] >= t0 ? 1.0 : 0.0;
        const double lam = K * tau * tau / volume;
        p_arr[i] = std::min(std::max(lam / (double)sr, 0.0), 1.0);
        amp[i] = sqrt(1.0 / std::max(p_arr[i], 1e-12));
    }
    Legacy rng((uint32_t)seed);
    const long nb = n / 2 + 1;
    std::vector<double> freqs(nb);
    const double val = 1.0 / ((double)n * (1.0 / (double)sr));
    for (long k = 0; k < nb; k++)
        freqs[k] = (double)k * val;
    std::vector<double> ir(2 * n, 0.0);
    for (int ci = 0; ci < 2; ci++) {
        std::vector<double> noise(n), sparse(n);
        for (long i = 0; i < n; i++)
            noise[i] = rng.gauss();
        const std::vector<double> spec = rfft(noise, n);
        std::vector<double> u(n);
        for (long i = 0; i < n; i++)
            u[i] = rng.uniform();
        for (long i = 0; i < n; i++) {
            const double g = rng.gauss();
            const double sg = g > 0.0 ? 1.0 : g < 0.0 ? -1.0 : g;      // (np.sign)
            sparse[i] = u[i] < p_arr[i] ? amp[i] * sg : 0.0;
            if (order[i] < 2.0)
                sparse[i] = 0.0;                // (first order is geometric)
        }
        const std::vector<double> sspec = rfft(sparse, n);
        std::vector<double> acc(n, 0.0), sq(n);
        for (int b = 0; b < 9; b++) {
            const double fc = OCTAVES[b];
            const double lo = fc / sqrt(2.0);
            double hi = fc * sqrt(2.0);
            if (lo >= sr / 2.0)
                continue;
            hi = hi <= sr / 2.0 ? hi : sr / 2.0;
            std::vector<double> ms(2 * nb, 0.0), mss(2 * nb, 0.0);
            bool any = false;
            for (long k = 0; k < nb; k++)
                if (freqs[k] >= lo && freqs[k] < hi) {
                    ms[2 * k] = spec[2 * k];
                    ms[2 * k + 1] = spec[2 * k + 1];
                    mss[2 * k] = sspec[2 * k];
                    mss[2 * k + 1] = sspec[2 * k + 1];
                    any = true;
                }
            if (!any)
                continue;
            std::vector<double> band = irfft(ms, n), spar = irfft(mss, n);
            for (long i = 0; i < n; i++)
                sq[i] = band[i] * band[i];
            const double mb = npsum(sq.data(), n) / (double)n;
            const double db = sqrt(std::max(mb, 1e-30));
            for (long i = 0; i < n; i++)
                band[i] /= db;
            for (long i = 0; i < n; i++)
                sq[i] = spar[i] * spar[i];
            const double msp = npsum(sq.data(), n) / (double)n;
            if (msp > 0.0) {
                const double dsp = sqrt(msp);
                for (long i = 0; i < n; i++)
                    spar[i] = spar[i] / dsp;
            }
            const double base = 1.0 - sp[S_OCT + 3 * b + 2], tm = t60[b] < 1e-3 ? 1e-3 : t60[b];
            for (long i = 0; i < n; i++) {
                const double ss = order[i] < 2.0 ? 0.0 : pow(base, order[i]);
                double v = sqrt(1.0 - ss) * band[i] + sqrt(ss) * spar[i];
                v *= gate[i] * exp(-6.907755 * t[i] / tm);
                band[i] = v;
            }
            const double share = (hi - lo) / (sr / 2.0);
            for (long i = 0; i < n; i++)
                sq[i] = band[i] * band[i];
            const double e = npsum(sq.data(), n);
            if (e > 0.0 && share > 0.0) {
                const double g = sqrt(ratio[b] * share / e);
                for (long i = 0; i < n; i++)
                    acc[i] += band[i] * g;
            }
        }
        for (long i = 0; i < n; i++)
            ir[2 * i + ci] = acc[i];
    }
    if (fs_hz > 25.0) {
        // zero-padded to 2n, the high-pass a linear filter (numpy's complex
        // product with the mask as complex: (a h - b 0, a 0 + b h))
        const long n2 = 2 * n, nb2 = n2 / 2 + 1;
        const double v2 = 1.0 / ((double)n2 * (1.0 / (double)sr)), fd = fs_hz > 1e-6 ? fs_hz : 1e-6;
        for (int ci = 0; ci < 2; ci++) {
            std::vector<double> col(n);
            for (long i = 0; i < n; i++)
                col[i] = ir[2 * i + ci];
            std::vector<double> s = rfft(col, n2);
            for (long k = 0; k < nb2; k++) {
                const double f2 = (double)k * v2;
                const double h = std::min(std::max((f2 - fs_hz) / fd, 0.0), 1.0);
                const double a = s[2 * k], b = s[2 * k + 1];
                s[2 * k] = a * h - b * 0.0;
                s[2 * k + 1] = a * 0.0 + b * h;
            }
            std::vector<double> y = irfft(s, n2);
            for (long i = 0; i < n; i++)
                ir[2 * i + ci] = y[i];
        }
    }
    return ir;
}

// ...into a malloc'd *out (the caller frees it); n, or -1
extern "C" long nv_room_tail_ir(const double *sp, const double *bq, int has_bq, int sr, int seed, double **out)
{
    if ((int)sp[S_N] != S_LEN)
        return -1;
    std::vector<double> ir = build_ir(sp, bq, has_bq, sr, seed);
    *out = (double *)malloc(sizeof(double) * ir.size());
    memcpy(*out, ir.data(), sizeof(double) * ir.size());
    return (long)ir.size() / 2;
}

// modal_ir(props, sr, channels=2, q_low): its n samples, two channels
// interleaved, into a malloc'd *out; n (1: no modes, a zero row), -1. *nmodes
// how many; live uses them only where there are some and Schroeder is over 25 Hz
extern "C" long nv_room_tail_modes(const double *sp, const double *bq, int has_bq, int sr, double **out, int *nmodes)
{
    if ((int)sp[S_N] != S_LEN)
        return -1;
    const double lx = sp[S_LX], ly = sp[S_LY], lz = sp[S_LZ], fs = sp[S_FS], c = sp[S_C];
    const double lis[3] = {sp[S_LIS], sp[S_LIS + 1], sp[S_LIS + 2]};
    const double src[3] = {sp[S_SRC], sp[S_SRC + 1], sp[S_SRC + 2]};
    const double fmax = std::min(2.0 * fs, sr / 2.0);
    auto t60_at = [&](double f) {
        int best = 0;
        double bd = 0.0;
        for (int i = 0; i < 9; i++) {
            const double d = fabs(log(std::max(f, 1e-3) / OCTAVES[i]));
            if (i == 0 || d < bd) {
                bd = d;
                best = i;
            }
        }
        return sp[S_OCT + 3 * best];
    };
    auto nmax = [&](double L) { return (long)(2.0 * fmax * L / c) + 1; };
    struct Mode {
        double f, a, t60;
    };
    std::vector<Mode> modes;
    const double Ls[3] = {lx, ly, lz};
    for (long nx = 0; nx <= nmax(lx); nx++)
        for (long ny = 0; ny <= nmax(ly); ny++)
            for (long nz = 0; nz <= nmax(lz); nz++) {
                if (nx == 0 && ny == 0 && nz == 0)
                    continue;
                const double f = 0.5 * c * sqrt(pow(nx / lx, 2.0) + pow(ny / ly, 2.0) + pow(nz / lz, 2.0));
                if (f > fmax || f < 1.0)
                    continue;
                double a = 1.0;
                const long ns[3] = {nx, ny, nz};
                for (int d = 0; d < 3; d++)
                    a *= cos(ns[d] * M_PI * src[d] / Ls[d]) * cos(ns[d] * M_PI * lis[d] / Ls[d]);
                if (fabs(a) < 1e-4)
                    continue;
                a *= std::min(1.0, std::max(0.0, (2.0 * fs - f) / std::max(fs, 1e-6)));
                if (fabs(a) < 1e-4)
                    continue;
                modes.push_back(Mode{f, a, t60_at(f)});
            }
    *nmodes = (int)modes.size();
    if (modes.empty()) {
        *out = (double *)calloc(2, sizeof(double));
        return 1;
    }
    double longest = modes[0].t60;
    for (const Mode &m : modes)
        longest = std::max(longest, m.t60);
    const long n = (long)(std::min(longest * 1.2, 8.0) * sr);
    std::vector<double> t(n), ir(2 * n, 0.0), env(n);
    for (long i = 0; i < n; i++)
        t[i] = (double)i / (double)sr;
    for (const Mode &m : modes) {
        const double tm = m.t60 < 1e-3 ? 1e-3 : m.t60, w = 2.0 * M_PI * m.f;
        for (long i = 0; i < n; i++)
            env[i] = m.a * exp(-6.907755 * t[i] / tm);
        for (int ci = 0; ci < 2; ci++)
            for (long i = 0; i < n; i++)
                ir[2 * i + ci] += env[i] * cos(w * t[i]);
    }
    // ...its level: the reverberant ratio at the lowest octave, at the stage's
    // directivity there, against the mean |H|^2 below twice Schroeder
    const double q_low = q_at(bq, has_bq, 0, 1.0);
    const double target = ratio_at(sp, 0, q_low);
    const long nb = n / 2 + 1;
    const double val = 1.0 / ((double)n * (1.0 / (double)sr));
    std::vector<std::vector<double>> S(2);
    for (int ci = 0; ci < 2; ci++) {
        std::vector<double> col(n);
        for (long i = 0; i < n; i++)
            col[i] = ir[2 * i + ci];
        S[ci] = rfft(col, n);
    }
    std::vector<double> p2;                     // (spec[band, :]: row by row, its two channels)
    for (long k = 0; k < nb; k++)
        if ((double)k * val <= 2.0 * fs)
            for (int ci = 0; ci < 2; ci++) {
                double z[2] = {S[ci][2 * k], S[ci][2 * k + 1]}, m;
                nv_cabs_n(1, z, &m);
                p2.push_back(m * m);
            }
    if (!p2.empty()) {
        const double power = npsum(p2.data(), (long)p2.size()) / (double)p2.size();
        if (power > 0.0) {
            const double g = sqrt(target / power);
            for (long i = 0; i < 2 * n; i++)
                ir[i] = ir[i] * g;
        }
    }
    *out = (double *)malloc(sizeof(double) * 2 * n);
    memcpy(*out, ir.data(), sizeof(double) * 2 * n);
    return n;
}

// ---- A DEVICE IN THE ROOM'S PLACE (roomtail.device_ir: the plate, the delays) ----
extern "C" void *nv_npy_new(unsigned long long seed);
extern "C" double nv_npy_next(void *g);
extern "C" void nv_npy_free(void *g);

namespace {
// scipy's sosfilt over x in place, from the state z (sections x 2)
void sosfilt(const double *sos, int ns, std::vector<double> &z, double *x, long n)
{
    for (long i = 0; i < n; i++) {
        double x_cur = x[i];
        for (int s = 0; s < ns; s++) {
            const double *c = sos + 6 * s;
            const double x_new = c[0] * x_cur + z[2 * s];
            z[2 * s] = c[1] * x_cur - c[4] * x_new + z[2 * s + 1];
            z[2 * s + 1] = c[2] * x_cur - c[5] * x_new;
            x_cur = x_new;
        }
        x[i] = x_cur;
    }
}

// scipy's sosfiltfilt (padtype 'odd', padlen 3 ntaps; its zi from sosfilt_zi)
std::vector<double> sosfiltfilt(const double *sos, const double *zi, int ns, const std::vector<double> &x)
{
    int z2 = 0, z5 = 0;
    for (int s = 0; s < ns; s++) {
        z2 += sos[6 * s + 2] == 0.0;
        z5 += sos[6 * s + 5] == 0.0;
    }
    const long ntaps = 2 * ns + 1 - std::min(z2, z5), edge = 3 * ntaps, n = (long)x.size();
    std::vector<double> e(n + 2 * edge);
    for (long i = 0; i < edge; i++)
        e[i] = 2.0 * x[0] - x[edge - i];
    for (long i = 0; i < n; i++)
        e[edge + i] = x[i];
    for (long j = 0; j < edge; j++)
        e[edge + n + j] = 2.0 * x[n - 1] - x[n - 2 - j];
    std::vector<double> z(2 * ns);
    for (int k = 0; k < 2 * ns; k++)
        z[k] = zi[k] * e[0];
    sosfilt(sos, ns, z, e.data(), (long)e.size());
    std::reverse(e.begin(), e.end());
    for (int k = 0; k < 2 * ns; k++)
        z[k] = zi[k] * e[0];
    sosfilt(sos, ns, z, e.data(), (long)e.size());
    std::reverse(e.begin(), e.end());
    return std::vector<double>(e.begin() + edge, e.begin() + edge + n);
}

// a filter in device_spec: sections, their coefficients, their zi -- past it
const double *filt(const double *p, int *ns, const double **sos, const double **zi)
{
    *ns = (int)p[0];
    *sos = p + 1;
    *zi = p + 1 + 6 * *ns;
    return p + 1 + 8 * *ns;
}

// _octave_energy: the mean of the two channels' sum's energy through each band-pass
double octave_energy(const std::vector<double> &ir, const double *eb)
{
    const long n = (long)ir.size() / 2;
    std::vector<double> x(n);
    for (long i = 0; i < n; i++)
        x[i] = 0.0 + ir[2 * i] + ir[2 * i + 1];
    const int nb = (int)eb[0];
    const double *p = eb + 1;
    std::vector<double> e;
    for (int b = 0; b < nb; b++) {
        int ns;
        const double *sos, *zi;
        p = filt(p, &ns, &sos, &zi);
        std::vector<double> y = sosfiltfilt(sos, zi, ns, x);
        for (double &v : y)
            v = v * v;
        e.push_back(npsum(y.data(), (long)y.size()));
    }
    double s = 0.0;
    for (double v : e)
        s += v;
    return s / (double)e.size();
}
}  // namespace

// roomtail.device_ir(kind, the room's build_ir, sr, 1.0, None, 0) as
// live.room_irs draws it: the plate (kind 1) or the echo (2 'delay', 3
// 'pan_delay') at the room tail's octave energy; n, -1
extern "C" long nv_room_tail_device(const double *sp, const double *dv, const double *bq, int has_bq, int sr,
                                    double **out)
{
    if ((int)sp[S_N] != S_LEN)
        return -1;
    const int kind = (int)sp[S_KIND];
    if (kind < 1 || kind > 3)
        return -1;
    const std::vector<double> room = build_ir(sp, bq, has_bq, sr, 0);
    const double *pb = dv + 2;                  // (the plate's bands)
    const double *eb = pb + 1;                  // (...past them: the energy's)
    for (int b = 0; b < (int)pb[0]; b++) {
        int ns;
        const double *sos, *zi;
        eb = filt(eb + 1, &ns, &sos, &zi);
    }
    std::vector<double> ir;
    if (kind == 1) {                            // plate_ir(sr, PLATE_T500, 2, 0)
        const long n = (long)dv[1];
        std::vector<double> t(n), x(n);
        for (long i = 0; i < n; i++)
            t[i] = (double)i / (double)sr;
        ir.assign(2 * n, 0.0);
        void *g = nv_npy_new(0 + 140);
        const double *p = pb + 1;
        for (int b = 0; b < (int)pb[0]; b++) {
            const double t60 = p[0];
            int ns;
            const double *sos, *zi;
            p = filt(p + 1, &ns, &sos, &zi);
            for (int c = 0; c < 2; c++) {
                for (long i = 0; i < n; i++)
                    x[i] = nv_npy_next(g);
                std::vector<double> y = sosfiltfilt(sos, zi, ns, x);
                for (long i = 0; i < n; i++)
                    ir[2 * i + c] += y[i] * pow(10.0, -3.0 * t[i] / t60);
            }
        }
        nv_npy_free(g);
        const long k = std::max(1L, (long)(0.0005 * sr));
        const double step = 1.0 / (double)(k - 1);
        for (long i = 0; i < k; i++) {
            const double w = i == k - 1 ? 1.0 : (double)i * step + 0.0;
            ir[2 * i] *= w;
            ir[2 * i + 1] *= w;
        }
    } else {                                    // echo_ir(sr, fb, pan, 2)
        const double fb = kind == 2 ? 40.0 : 32.0;
        const double g = std::min(0.95, std::max(0.0, fb / 127.0));
        const double a = exp(-2.0 * M_PI * 5000.0 / sr);
        const long d = (long)nearbyint(0.100 * sr);
        const long reps = g > 0.0 ? std::max(1L, (long)ceil(log(1e-3) / log(g))) : 1;
        const long n = (reps + 1) * d + 256;
        ir.assign(2 * n, 0.0);
        std::vector<double> tap(256, 0.0);
        tap[0] = 1.0;
        for (long k = 1; k <= reps; k++) {
            double Z = 0.0;                     // (lfilter([1 - a], [1, -a]): transposed, from rest)
            const double b0 = 1.0 - a, b1 = 0.0, a1 = -a;
            for (int i = 0; i < 256; i++) {
                const double xi = tap[i];
                const double y = Z + b0 * xi;
                Z = xi * b1 - y * a1;
                tap[i] = y;
            }
            const double amp = pow(g, (double)(k - 1));
            for (int i = 0; i < 256; i++) {
                const long r = k * d + i;
                if (kind == 3)
                    ir[2 * r + (k - 1) % 2] += tap[i] * amp * sqrt(2.0);
                else {
                    ir[2 * r] += tap[i] * amp;
                    ir[2 * r + 1] += tap[i] * amp;
                }
            }
        }
    }
    const double er = octave_energy(room, eb), ed = octave_energy(ir, eb);
    const double s = sqrt(er / std::max(ed, 1e-30));
    for (double &v : ir)
        v = v * s;
    *out = (double *)malloc(sizeof(double) * ir.size());
    memcpy(*out, ir.data(), sizeof(double) * ir.size());
    return (long)ir.size() / 2;
}

extern "C" void nv_room_tail_free(double *p) { free(p); }
