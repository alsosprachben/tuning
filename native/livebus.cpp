// livebus.cpp -- A PART'S OWN BUS, live (live.LiveBus): efxbus's processors
// block by block, each one's state carried from block to block -- the hold's
// place on the absolute sample clock, every filter's memory, the envelope --
// so a stream of blocks is the one signal efxbus's own windows make; the
// reverbs (Reverb, Gate Reverb) through live's block convolver (convolver.c,
// float32), as LiveBus has them; dry against effect by the type's Balance, in
// float32 as numpy has the mix. The arithmetic is nvrender's whole-file
// bus_process, the state lifted out of it.
#include <algorithm>
#include <cmath>
#include <cstring>
#include <vector>

extern "C" {
long long nv_efx_gate_ir(double sr, int gtype, double pre_ms, double gate_ms, double *hL, double *hR, long long cap);
long long nv_efx_reverb_ir(double sr, int rtype, double pre_ms, int time, double damp_hz, double *hL, double *hR,
                           long long cap);
void nv_npy_noise(long long n0, long n, unsigned long long seed, int normal, double *out);
}

namespace {

typedef void *(*conv_new_fn)(const float *ir, int len, int B, int M);
typedef void (*conv_proc_fn)(void *c, const float *x, float *out);
typedef void (*conv_free_fn)(void *c);

// scipy's lfilter (transposed direct form II), its memory z carried
struct Filt {
    double b[4] = {0, 0, 0, 0}, a[4] = {1, 0, 0, 0};
    int nb = 0;                             // 0: none
    double z[2][3] = {{0, 0, 0}, {0, 0, 0}};
    void set(const double *bb, const double *aa, int n)
    {
        nb = n;
        for (int i = 0; i < n; i++) {
            b[i] = bb[i];
            a[i] = aa[i];
        }
    }
    void one_pole(double hz, double sr)     // (efxbus.lowpass: 0 none)
    {
        if (hz == 0.0)
            return;
        const double e = exp(-2.0 * M_PI * hz / sr);
        const double bb[2] = {1.0 - e, 0.0}, aa[2] = {1.0, -e};
        set(bb, aa, 2);
    }
    void run(double *x, long n, int ear)
    {
        if (!nb)
            return;
        double *zz = z[ear];
        for (long i = 0; i < n; i++) {
            const double xn = x[i], yn = zz[0] + b[0] * xn;
            for (int m = 0; m < nb - 2; m++)
                zz[m] = zz[m + 1] + xn * b[m + 1] - yn * a[m + 1];
            zz[nb - 2] = xn * b[nb - 1] - yn * a[nb - 1];
            x[i] = yn;
        }
    }
};

// efxbus.OnePole (Lo-Fi 1's pre and post, the Enhancer's): lfilter([1 - a],
// [1, -a]) as efxbus calls it, 0 none
struct Pole {
    double a = 0.0, z[2] = {0.0, 0.0};
    void run(double *x, long n, int ear)
    {
        if (a == 0.0)
            return;
        double zz = z[ear];
        const double b0 = 1.0 - a;
        for (long i = 0; i < n; i++) {
            const double yv = zz + b0 * x[i];
            zz = x[i] * 0.0 - yv * -a;
            x[i] = yv;
        }
        z[ear] = zz;
    }
};

// efxbus.LoFi's hold and bits on the absolute sample clock (n: samples so
// far), held[]: the grid point before this block's first
struct Hold {
    double step = 1.0, q = 1.0;
    double held[2] = {0.0, 0.0};
    void run(const double *x, double *y, long n, long long n0, int ear, bool f32)
    {
        long long last = -1;
        for (long i = 0; i < n; i++) {
            const double k = floor((double)(n0 + i) / step);
            const long long first = (long long)ceil(k * step) - n0;
            double v = first >= 0 ? x[first] : held[ear];
            if (f32)                        // (LoFi2 hands it float32, and takes float32 back)
                v = (double)(float)v;
            y[i] = nearbyint(v / q) * q;
            if (f32)
                y[i] = (double)(float)y[i];
            if (i == n - 1)
                last = first;
        }
        if (n && last >= 0)
            held[ear] = x[last];
    }
};

struct Bus {
    int kind = 0;                           // 1 Lo-Fi, 2 a compressor, 3 Reverb, 4 Gate Reverb, 5 Enhancer, 6 Lo-Fi 2
    double p[40] = {};
    double q2[27] = {};                     // Lo-Fi 2's record
    double sr = 48000.0, dry = 0.0, wet = 1.0;
    int frames = 128;
    long long n = 0;                        // samples processed
    // Lo-Fi 1
    Pole pre, post;
    Hold hold;
    // the compressor
    double env = 0.0;
    // the Enhancer
    Pole hp;
    // Lo-Fi 2
    Filt radio_band, radio_static, pink, wp_lpf, click, disc_lpf, hum_lpf, post2;
    // the reverbs
    void *conv[2] = {nullptr, nullptr};
    conv_proc_fn cproc = nullptr;
    conv_free_fn cfree = nullptr;
    std::vector<float> m32, c0, c1;

    void process_raw(const float *L, const float *R, float gain, float *yL, float *yR);
};

void Bus::process_raw(const float *Lf, const float *Rf, float g, float *yL, float *yR)
{
    const long N = frames;
    std::vector<double> x[2] = {std::vector<double>(N), std::vector<double>(N)};
    for (long i = 0; i < N; i++) {          // (L * g: float32, as numpy has it)
        x[0][i] = (double)(Lf[i] * g);
        x[1][i] = (double)(Rf[i] * g);
    }
    float *ys[2] = {yL, yR};
    if (kind == 1) {                        // LO-FI 1: the pre filter, the hold, the bits, the post filter
        for (int ear = 0; ear < 2; ear++) {
            pre.run(x[ear].data(), N, ear);
            std::vector<double> y(N);
            hold.run(x[ear].data(), y.data(), N, n, ear, false);
            post.run(y.data(), N, ear);
            for (long i = 0; i < N; i++)
                ys[ear][i] = (float)y[i];
        }
    } else if (kind == 2) {                 // the compressor (and the Limiter): the envelope, its gain
        const double t = p[0], rr = p[1], ka = p[2], kr = p[3], mk = p[4];
        for (long i = 0; i < N; i++) {
            const double a = fabs(x[0][i]), b = fabs(x[1][i]);
            const double v = b > a ? b : a;     // (np.maximum)
            const double kk = v > env ? ka : kr;
            env = kk * env + (1.0 - kk) * v;
            const double db = 20.0 * log10(env > 1e-9 ? env : 1e-9);
            const double over = db - t > 0.0 ? db - t : 0.0;
            const double gg = pow(10.0, -over * (1.0 - 1.0 / rr) / 20.0) * mk;
            yL[i] = (float)(x[0][i] * gg);
            yR[i] = (float)(x[1][i] * gg);
        }
    } else if (kind == 5) {                 // THE ENHANCER: the top above the corner, saturated, mixed back
        const double drive = p[1], mix = p[2];
        for (int ear = 0; ear < 2; ear++) {
            std::vector<double> lp(x[ear]);
            hp.run(lp.data(), N, ear);
            for (long i = 0; i < N; i++) {
                const double hi = x[ear][i] - lp[i];
                const double sat = tanh(drive * hi) / drive;
                ys[ear][i] = (float)(x[ear][i] + mix * sat);
            }
        }
    } else if (kind == 6) {                 // LO-FI 2
        static const int BITS2[6] = {12, 10, 8, 7, 6, 5};
        static const double HUM[6][2] = {{1, 1.0}, {2, 0.5}, {3, 0.35}, {4, 0.15}, {5, 0.2}, {7, 0.1}};
        static const double DISC[4][3] = {{6.0, 33.3 / 60.0, 0.15}, {10.0, 45.0 / 60.0, 0.2},
                                          {20.0, 78.0 / 60.0, 0.5}, {14.0, 0.0, 0.1}};
        const double *q = q2;
        const double full = pow(10.0, -40.0 / 20.0), det = q[2] / 127.0;
        const double radio_amp = full * q[3] / 127.0 * det, wp_amp = full * q[6] / 127.0;
        const double disc_amp = full * q[9] / 127.0, hum_amp = full * q[12] / 127.0;
        const long long n0 = n;
        auto noises = [&](int ear, std::vector<double> &y) {
            const unsigned long long seed = 1000ULL * (unsigned long long)(ear + 1);
            std::vector<double> w(N);
            y.assign(N, 0.0);
            if (radio_amp != 0.0) {
                nv_npy_noise(n0, N, seed + 1, 1, w.data());
                radio_static.run(w.data(), N, ear);
                for (long i = 0; i < N; i++)
                    y[i] += radio_amp * w[i] * 4.5;
            }
            if (wp_amp != 0.0) {
                nv_npy_noise(n0, N, seed + 2, 1, w.data());
                if (pink.nb) {
                    pink.run(w.data(), N, ear);
                    for (long i = 0; i < N; i++)
                        w[i] = w[i] * 11.0;
                }
                wp_lpf.run(w.data(), N, ear);
                for (long i = 0; i < N; i++)
                    y[i] += wp_amp * w[i];
            }
            if (disc_amp != 0.0) {
                const double *dc = DISC[std::max(0, std::min(3, (int)q[7]))];
                const double rate = dc[0], rev = dc[1], hiss = dc[2];
                std::vector<double> u(N), s(N), h(N);
                nv_npy_noise(n0, N, seed + 3, 0, u.data());
                nv_npy_noise(n0, N, seed + 4, 1, s.data());
                nv_npy_noise(n0, N, seed + 5, 1, h.data());
                for (long i = 0; i < N; i++) {
                    const double sg = s[i] > 0.0 ? 1.0 : s[i] < 0.0 ? -1.0 : s[i];        // (np.sign)
                    w[i] = u[i] < rate / sr ? sg * (0.3 + 2.0 * (u[i] * sr / rate)) : 0.0;
                    if (rev != 0.0) {                   // (the tick once a revolution)
                        const double ix = (double)(n0 + i);
                        w[i] = w[i] + (floor(ix * rev / sr) != floor((ix - 1.0) * rev / sr) ? 2.5 : 0.0);
                    }
                }
                click.run(w.data(), N, ear);
                for (long i = 0; i < N; i++)
                    w[i] = 1.5 * w[i] + hiss * h[i];
                disc_lpf.run(w.data(), N, ear);
                for (long i = 0; i < N; i++)
                    y[i] += disc_amp * w[i];
            }
            if (hum_amp != 0.0) {
                const double hz = q[10] != 0.0 ? 60.0 : 50.0;
                for (long i = 0; i < N; i++) {
                    const double t = (double)(n0 + i) / sr;
                    double hv = 0.0;
                    for (const auto &hh : HUM)
                        hv += hh[1] * sin(2.0 * M_PI * hh[0] * hz * t);
                    w[i] = hv;
                }
                hum_lpf.run(w.data(), N, ear);
                for (long i = 0; i < N; i++)
                    y[i] += hum_amp * w[i];
            }
        };
        if (radio_band.nb) {                // THE RADIO OFF ITS STATION: an AM set's band, fading, wandering
            for (int ear = 0; ear < 2; ear++) {
                radio_band.run(x[ear].data(), N, ear);
                for (long i = 0; i < N; i++) {
                    const double t = (double)(n0 + i) / sr;
                    const double fade = (1.0 - 0.8 * det) * (1.0 + 0.3 * det * sin(2.0 * M_PI * 0.37 * t)
                                                             * sin(2.0 * M_PI * 0.11 * t + 1.0));
                    x[ear][i] = x[ear][i] * fade;
                }
            }
        }
        std::vector<double> y[2] = {std::vector<double>(N), std::vector<double>(N)};
        for (int ear = 0; ear < 2; ear++) {
            std::vector<double> xf(N);
            for (long i = 0; i < N; i++)
                xf[i] = (double)(float)x[ear][i];   // (handed to LoFi as float32)
            hold.run(xf.data(), y[ear].data(), N, n0, ear, true);
        }
        (void)BITS2;
        std::vector<double> z;
        if (q[13] != 0.0) {
            for (int ear = 0; ear < 2; ear++) {
                noises(ear, z);
                for (long i = 0; i < N; i++)
                    y[ear][i] = y[ear][i] + z[i];
            }
        } else {
            const double th = (std::max(0, std::min(127, (int)q[14])) - 64) / 63.0 * 0.25 * M_PI + 0.25 * M_PI;
            const double pl = cos(th), pr = sin(th);
            noises(0, z);
            for (long i = 0; i < N; i++) {
                const double m = 0.5 * (y[0][i] + y[1][i]) + z[i];
                y[0][i] = m * pl * sqrt(2.0);
                y[1][i] = m * pr * sqrt(2.0);
            }
        }
        for (int ear = 0; ear < 2; ear++) {
            post2.run(y[ear].data(), N, ear);
            for (long i = 0; i < N; i++)
                ys[ear][i] = (float)y[ear][i];
        }
    }
    n += N;
}

}  // namespace

extern "C" {

// a bus from the chain's record (efxchain.cpp's: fc[25] its kind, fc[26..30]
// its processor, fc[32..33] dry and effect, fc[176..] Lo-Fi 2's), the rate,
// the block, and convolver.c's calls (the reverbs')
void *nv_livebus_new(const double *fc, double sr, int frames, void *cn, void *cp, void *cf)
{
    Bus *b = new Bus;
    b->kind = (int)fc[25];
    for (int i = 0; i < 5; i++)
        b->p[i] = fc[26 + i];
    b->sr = sr;
    b->frames = frames;
    b->dry = fc[32];
    b->wet = fc[33];
    if (b->kind == 1) {
        b->hold.step = b->p[0];
        b->hold.q = b->p[1];
        b->pre.a = b->p[2];
        b->post.a = b->p[3];
    } else if (b->kind == 5) {
        b->hp.a = b->p[0];
    } else if (b->kind == 6) {
        static const double RATE2[6] = {16000, 11025, 8000, 6000, 5000, 4000};
        static const int BITS2[6] = {12, 10, 8, 7, 6, 5};
        static const double PB[4] = {0.049922035, -0.095993537, 0.050612699, -0.004408786};
        static const double PA[4] = {1.0, -2.494956002, 2.017265875, -0.522189400};
        for (int i = 0; i < 27; i++)
            b->q2[i] = fc[176 + i];
        const double *q = b->q2;
        const int k = std::max(0, std::min(5, (int)q[0]));
        b->hold.step = sr / RATE2[k];
        b->hold.q = pow(2.0, -(double)(BITS2[k] - 1));
        if ((int)q[1])
            b->post2.set(q + 15, q + 18, 3);
        if ((int)q[2]) {
            b->radio_band.set(q + 21, q + 24, 3);
            b->radio_static.set(q + 21, q + 24, 3);
        }
        if (q[4] != 0.0)
            b->pink.set(PB, PA, 4);
        b->wp_lpf.one_pole(q[5], sr);
        const double cb[2] = {1.0, 0.0}, ca[2] = {1.0, -exp(-1.0 / (0.0003 * sr))};
        b->click.set(cb, ca, 2);
        b->disc_lpf.one_pole(q[8], sr);
        b->hum_lpf.one_pole(q[11], sr);
    } else if (b->kind == 3 || b->kind == 4) {
        const long long cap = (long long)(10.0 * sr) + 64;
        std::vector<double> hL(cap), hR(cap);
        const long long nh = b->kind == 3
            ? nv_efx_reverb_ir(sr, (int)b->p[0], b->p[1], (int)b->p[2], b->p[3], hL.data(), hR.data(), cap)
            : nv_efx_gate_ir(sr, (int)b->p[0], b->p[1], b->p[2], hL.data(), hR.data(), cap);
        if (nh <= 0 || !cn || !cp || !cf) {
            delete b;
            return nullptr;
        }
        const double *hs[2] = {hL.data(), hR.data()};
        for (int ear = 0; ear < 2; ear++) {
            std::vector<float> h32(nh);
            for (long long i = 0; i < nh; i++)
                h32[i] = (float)hs[ear][i];
            b->conv[ear] = ((conv_new_fn)cn)(h32.data(), (int)nh, frames, 16);    // (Convolver.SEGMENT_BLOCKS)
        }
        b->cproc = (conv_proc_fn)cp;
        b->cfree = (conv_free_fn)cf;
        b->m32.assign(frames, 0.0f);
        b->c0.assign(frames, 0.0f);
        b->c1.assign(frames, 0.0f);
    } else if (b->kind != 2) {
        delete b;
        return nullptr;
    }
    return b;
}

// live.LiveBus._run: one block (frames) of the bus parts' sum through the
// processor at the output's scale (gain: the master gain), its output taken
// back down, dry against effect -- into oL, oR
void nv_livebus_process(void *h, const float *L, const float *R, double gain, float *oL, float *oR)
{
    Bus *b = (Bus *)h;
    const long N = b->frames;
    const float dry = (float)b->dry, wet = (float)b->wet;
    std::vector<float> yL(N), yR(N);
    if (b->kind == 3 || b->kind == 4) {     // (the reverbs: the mono sum through each ear's response)
        for (long i = 0; i < N; i++)
            b->m32[i] = 0.5f * (L[i] + R[i]);
        b->cproc(b->conv[0], b->m32.data(), b->c0.data());
        b->cproc(b->conv[1], b->m32.data(), b->c1.data());
        for (long i = 0; i < N; i++) {
            yL[i] = b->c0[i];
            yR[i] = b->c1[i];
        }
    } else {
        const float g = (float)std::max(gain, 1e-12);
        b->process_raw(L, R, g, yL.data(), yR.data());
        for (long i = 0; i < N; i++) {
            yL[i] = yL[i] / g;
            yR[i] = yR[i] / g;
        }
    }
    for (long i = 0; i < N; i++) {
        oL[i] = dry * L[i] + wet * yL[i];
        oR[i] = dry * R[i] + wet * yR[i];
    }
}

// A FILE's BUS, STREAMED (nvrender --stream): its processor (kind, p in
// NoteClass.bus_p's layout: p[0..4], Lo-Fi 2's record from p[5]) on windows of
// the part's signal at the output's scale, its state carried -- the raw output
// (bus_process's y), any length a call; NULL for the reverbs
void *nv_livebus_raw_new(int kind, const double *p, double sr)
{
    std::vector<double> fc(203, 0.0);
    fc[25] = kind;
    for (int i = 0; i < 5; i++)
        fc[26 + i] = p[i];
    if (kind == 6)
        for (int i = 0; i < 27; i++)
            fc[176 + i] = p[5 + i];
    fc[33] = 1.0;
    return nv_livebus_new(fc.data(), sr, 1, nullptr, nullptr, nullptr);
}
void nv_livebus_raw(void *h, const float *x0, const float *x1, long n, float *y0, float *y1)
{
    Bus *b = (Bus *)h;
    b->frames = (int)n;
    b->process_raw(x0, x1, 1.0f, y0, y1);
}

void nv_livebus_free(void *h)
{
    Bus *b = (Bus *)h;
    if (!b)
        return;
    for (int ear = 0; ear < 2; ear++)
        if (b->conv[ear] && b->cfree)
            b->cfree(b->conv[ear]);
    delete b;
}

}  // extern "C"
