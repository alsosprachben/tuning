/* efxrev.c -- THE GS INSERTION EFFECT's REVERBS (efxbus.Reverb, GateReverb):
 * their impulse responses and the convolution that runs a part through them,
 * here once for both efxbus (which calls these) and nvrender -- scipy's
 * fftconvolve and numpy's SIMD pow and exp are not libm's, so the two could
 * only agree to the bit on code they share. Included by tone.c after
 * npyrandom.c (its PCG64 and ziggurat) and pocketfft.c (its real FFT). */

/* numpy's SeedSequence over entropy words (_coerce_to_uint32_array of a list:
 * each element's 32-bit words, least first, one word for 0), then PCG64 */
static void efx_pcg_seed(NpyPCG64 *r, const uint32_t *ent, int nent)
{
    const uint32_t INIT_A = 0x43b0d7e5u, MULT_A = 0x931e8875u, INIT_B = 0x8b51f9ddu, MULT_B = 0x58f38dedu;
    const uint32_t MIX_MULT_L = 0xca01f9ddu, MIX_MULT_R = 0x4973f715u;
    uint32_t pool[4], hc = INIT_A;
#define HASHMIX(v) ({ uint32_t _v = (v); _v ^= hc; hc *= MULT_A; _v *= hc; _v ^= _v >> 16; _v; })
#define MIX(x, y) ({ uint32_t _r = MIX_MULT_L * (x) - MIX_MULT_R * (y); _r ^= _r >> 16; _r; })
    for (int i = 0; i < 4; i++)
        pool[i] = HASHMIX(i < nent ? ent[i] : 0u);
    for (int s = 0; s < 4; s++)
        for (int d = 0; d < 4; d++)
            if (s != d)
                pool[d] = MIX(pool[d], HASHMIX(pool[s]));
    for (int s = 4; s < nent; s++)
        for (int d = 0; d < 4; d++)
            pool[d] = MIX(pool[d], HASHMIX(ent[s]));
#undef HASHMIX
#undef MIX
    uint32_t st[8], hb = INIT_B;
    for (int i = 0; i < 8; i++) {
        uint32_t v = pool[i % 4];
        v ^= hb;
        hb *= MULT_B;
        v *= hb;
        v ^= v >> 16;
        st[i] = v;
    }
    uint64_t v4[4];
    for (int i = 0; i < 4; i++)
        v4[i] = (uint64_t)st[2 * i] | ((uint64_t)st[2 * i + 1] << 32);
    __uint128_t s = (((__uint128_t)v4[0]) << 64) | v4[1];
    __uint128_t inc = (((__uint128_t)v4[2]) << 64) | v4[3];
    r->state = 0;
    r->inc = (inc << 1) | 1u;
    pcg_step(r);
    r->state += s;
    pcg_step(r);
}

static int efx_words(unsigned long long x, uint32_t *w)
{
    int n = 0;
    do {
        w[n++] = (uint32_t)(x & 0xFFFFFFFFu);
        x >>= 32;
    } while (x && n < 2);
    return n;
}

/* efxbus.noise: n samples from absolute sample n0 (normal, or uniform 0..1),
 * in chunks of 8192 (NOISE_CHUNK), each chunk default_rng([seed, chunk]) */
void nv_efx_noise(long long n0, long long n, unsigned long long seed, int uniform, double *out)
{
    const long long C = 8192;
    if (n <= 0)
        return;
    long long k0 = n0 / C, k1 = (n0 + n - 1) / C;
    double *c = (double *)malloc(sizeof(double) * C);
    for (long long k = k0; k <= k1; k++) {
        uint32_t ent[4];
        int ne = efx_words(seed, ent);
        ne += efx_words((unsigned long long)k, ent + ne);
        NpyPCG64 r;
        efx_pcg_seed(&r, ent, ne);
        for (long long i = 0; i < C; i++)
            c[i] = uniform ? pcg_next_double(&r) : npy_standard_normal(&r);
        long long a = n0 > k * C ? n0 : k * C, b = n0 + n < (k + 1) * C ? n0 + n : (k + 1) * C;
        for (long long i = a; i < b; i++)
            out[i - n0] = c[i - k * C];
    }
    free(c);
}

/* scipy's lfilter([1 - a], [1, -a], x), from rest */
static void efx_pole(double *x, long long n, double a)
{
    double z = 0.0, b0 = 1.0 - a;
    for (long long i = 0; i < n; i++) {
        double y = z + b0 * x[i];
        z = x[i] * 0.0 - y * -a;
        x[i] = y;
    }
}

static void efx_unit(double *x, long long n)
{
    double s = 0.0;
    for (long long i = 0; i < n; i++)
        s = s + x[i] * x[i];
    double d = sqrt(s) + 1e-12;
    for (long long i = 0; i < n; i++)
        x[i] = x[i] / d;
}

/* GATE REVERB's response (efxbus.GateReverb): a noise burst Gate Time long
 * -- Norm flat-decaying, Reverse rising, Sweep1 right to left, Sweep2 left
 * to right -- its close 2 ms, low-passed at 7 kHz, its energy whole, after
 * the pre-delay. Each ear's into hL, hR (cap each); returns the length. */
long long nv_efx_gate_ir(double sr, int gtype, double pre_ms, double gate_ms, double *hL, double *hR, long long cap)
{
    long long n = (long long)nearbyint(gate_ms / 1000.0 * sr);
    n = n > 8 ? n : 8;
    long long pre = (long long)nearbyint(pre_ms / 1000.0 * sr);
    if (pre + n > cap)
        return -(pre + n);
    double *env = (double *)malloc(sizeof(double) * n), *x = (double *)malloc(sizeof(double) * n);
    for (long long i = 0; i < n; i++) {
        double u = (double)i / (double)n;
        env[i] = gtype == 1 ? pow(u + 0.05, 1.5) : exp(-0.7 * u);
    }
    long long f = (long long)(0.002 * sr);
    f = f > 2 ? f : 2;
    f = f < n ? f : n;
    for (long long j = 0; j < f; j++)            /* the gate's close: 1 to 0 over f */
        env[n - f + j] *= 1.0 - (double)j / (double)(f - 1);
    const double a = exp(-2.0 * M_PI * 7000.0 / sr);
    for (int ear = 0; ear < 2; ear++) {
        double *h = ear ? hR : hL;
        nv_efx_noise(0, n, 77 + ear, 0, x);
        efx_pole(x, n, a);
        for (long long i = 0; i < n; i++) {
            double u = (double)i / (double)n;
            double th = 0.5 * M_PI * (gtype == 3 ? u : 1.0 - u);
            double side = gtype == 2 || gtype == 3 ? (ear ? sin(th) : cos(th)) : 1.0;
            x[i] = x[i] * env[i] * side;
        }
        efx_unit(x, n);
        for (long long i = 0; i < pre; i++)
            h[i] = 0.0;
        for (long long i = 0; i < n; i++)
            h[pre + i] = x[i];
    }
    free(env);
    free(x);
    return pre + n;
}

/* THE REVERB type's response (efxbus.Reverb): a decaying noise per ear --
 * RT60 0.1 s x 50^(Time/127) x the type's own, Room2 sparse, Stage1 a slower
 * late tail, Stage2 its early reflections -- its highs damped toward HF
 * Damp as it decays (0 or NaN: 20 kHz), its energy whole, after the
 * pre-delay. Each ear's into hL, hR (cap each); returns the length, or minus
 * it where cap is short. */
long long nv_efx_reverb_ir(double sr, int rtype, double pre_ms, int time, double damp_hz, double *hL, double *hR,
                           long long cap)
{
    static const double RT[6] = {0.4, 0.4, 0.7, 0.7, 1.0, 1.2}, DENSE[6] = {1.0, 0.04, 1.0, 1.0, 1.0, 1.0},
                        LATE[6] = {0.0, 0.0, 1.6, 0.0, 0.0, 0.0};
    static const int EARLYT[6] = {0, 0, 0, 1, 0, 0};
    static const double EARLY[6][3] = {{0.011, 0.9, 0.3}, {0.019, -0.7, 0.8}, {0.027, 0.6, 0.1},
                                       {0.041, -0.5, 0.6}, {0.053, 0.45, 0.95}, {0.071, -0.35, 0.4}};
    int ty = rtype >= 0 && rtype < 6 ? rtype : 0;
    int tm = time < 0 ? 0 : time > 127 ? 127 : time;
    double rt = 0.1 * pow(50.0, tm / 127.0) * RT[ty];
    double len = 1.2 * rt < 8.0 ? 1.2 * rt : 8.0;
    long long n = (long long)(len * sr) + 8;
    long long pre = (long long)nearbyint(pre_ms / 1000.0 * sr);
    if (pre + n > cap)
        return -(pre + n);
    if (!(damp_hz > 0.0))
        damp_hz = 20000.0;
    double *env = (double *)malloc(sizeof(double) * n), *k = (double *)malloc(sizeof(double) * n),
           *x = (double *)malloc(sizeof(double) * n), *y = (double *)malloc(sizeof(double) * n),
           *u = (double *)malloc(sizeof(double) * n);
    for (long long i = 0; i < n; i++) {
        double t = (double)i / sr;
        double e = pow(10.0, -3.0 * t / rt);
        if (LATE[ty] > 0.0) {                       /* a slower tail after 80 ms */
            double l = 0.25 * pow(10.0, -3.0 * t / (LATE[ty] * rt));
            e = l > e ? l : e;
        }
        double b = t / 0.004;                       /* the first reflections' build */
        env[i] = e * (b < 1.0 ? b : 1.0);
        k[i] = 1.0 - exp(-t / (rt / 3.0));          /* how far the highs have died */
    }
    const double a = exp(-2.0 * M_PI * damp_hz / sr);
    for (int ear = 0; ear < 2; ear++) {
        double *h = ear ? hR : hL;
        nv_efx_noise(0, n, 91 + ear, 0, x);
        if (DENSE[ty] < 1.0) {                      /* sparse: a few reflections */
            nv_efx_noise(0, n, 93 + ear, 1, u);
            double sd = sqrt(DENSE[ty]);
            for (long long i = 0; i < n; i++)
                x[i] = u[i] < DENSE[ty] ? x[i] / sd : 0.0;
        }
        for (long long i = 0; i < n; i++)
            y[i] = x[i];
        efx_pole(y, n, a);
        for (long long i = 0; i < n; i++)
            x[i] = ((1.0 - k[i]) * x[i] + k[i] * y[i]) * env[i];
        if (EARLYT[ty])
            for (int q = 0; q < 6; q++) {
                long long at = (long long)(EARLY[q][0] * sr);
                if (at < n)
                    x[at] += EARLY[q][1] * 30.0 * (ear ? EARLY[q][2] : 1.0 - EARLY[q][2]) * sqrt(sr / 44100.0);
            }
        efx_unit(x, n);
        for (long long i = 0; i < pre; i++)
            h[i] = 0.0;
        for (long long i = 0; i < n; i++)
            h[pre + i] = x[i];
    }
    free(env); free(k); free(x); free(y); free(u);
    return pre + n;
}

/* THE CONVOLUTION a bus runs (GateReverb.process): out[j] = (x * h)[k + j]
 * for j < m, x the history and the window (nx), h the response (nh) -- by
 * overlap-add, numpy's pocketfft at a power of two at least twice h. 0, or
 * -1 where it could not plan. */
int nv_efx_conv(const double *x, long long nx, const double *h, long long nh, long long k, long long m, double *out)
{
    long long N = 1;
    while (N < 2 * nh)
        N <<= 1;
    long long B = N - nh + 1;
    rfft_plan plan = make_rfft_plan((size_t)N);
    if (!plan)
        return -1;
    double *H = (double *)calloc((size_t)N, sizeof(double)), *X = (double *)malloc(sizeof(double) * N);
    for (long long i = 0; i < nh; i++)
        H[i] = h[i];
    int fail = rfft_forward(plan, H, 1.0) != 0;
    for (long long j = 0; j < m; j++)
        out[j] = 0.0;
    for (long long b0 = 0; b0 < nx && !fail; b0 += B) {
        /* only the blocks that reach [k, k + m): block b0 makes b0 .. b0 + B + nh - 2 */
        if (b0 + B + nh - 2 < k || b0 >= k + m)
            continue;
        long long nb = nx - b0 < B ? nx - b0 : B;
        for (long long i = 0; i < N; i++)
            X[i] = i < nb ? x[b0 + i] : 0.0;
        fail = rfft_forward(plan, X, 1.0) != 0;
        /* (the halfcomplex product: r0, then (re, im) pairs, r_{N/2} last) */
        X[0] = X[0] * H[0];
        for (long long q = 1; q + 1 < N; q += 2) {
            double xr = X[q], xi = X[q + 1], hr = H[q], hi = H[q + 1];
            X[q] = xr * hr - xi * hi;
            X[q + 1] = xr * hi + xi * hr;
        }
        X[N - 1] = X[N - 1] * H[N - 1];
        fail = fail || rfft_backward(plan, X, 1.0 / (double)N) != 0;
        long long lo = k - b0 > 0 ? k - b0 : 0, hi = k + m - b0 < N ? k + m - b0 : N;
        for (long long i = lo; i < hi; i++)
            out[b0 + i - k] += X[i];
    }
    free(H);
    free(X);
    destroy_rfft_plan(plan);
    return fail ? -1 : 0;
}
