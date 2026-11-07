/* npyrandom.c -- numpy's default_rng(seed).standard_normal in C, draw for draw.
 *
 * The organ's wind (wind.py) draws its wander from it, and nvrender must make
 * the same numbers: numpy's SeedSequence (its hashmix and mix over a pool of
 * four words) seeding a PCG64 (the 128-bit LCG, XSL-RR output), and numpy's
 * random_standard_normal -- a ziggurat on numpy's own tables
 * (native/npyrandom.h, read out of the installed numpy by
 * examples/npyrandom_tables.py). Checked against numpy, draw by draw
 * (native.npy_normals).
 */
#include <math.h>
#include <stdint.h>
#include "npyrandom.h"

typedef struct {
    __uint128_t state, inc;
} NpyPCG64;

static const __uint128_t PCG_MULT = (((__uint128_t)0x2360ED051FC65DA4ULL) << 64) | 0x4385DF649FCCF645ULL;

static void pcg_step(NpyPCG64 *r)
{
    r->state = r->state * PCG_MULT + r->inc;
}

static uint64_t pcg_next64(NpyPCG64 *r)
{
    pcg_step(r);
    uint64_t hi = (uint64_t)(r->state >> 64), lo = (uint64_t)r->state;
    unsigned rot = (unsigned)(r->state >> 122);
    uint64_t x = hi ^ lo;
    return (x >> rot) | (x << ((-rot) & 63));
}

static double pcg_next_double(NpyPCG64 *r)
{
    return (double)(pcg_next64(r) >> 11) * (1.0 / 9007199254740992.0);
}

/* numpy's SeedSequence(seed).generate_state(4, uint64), a small seed */
/* SeedSequence(seeds): each seed's 32-bit words, least first, one after
   another (_coerce_to_uint32_array of an int, or of a list of them) */
static void seed_sequence_n(const uint64_t *seeds, int ns, uint64_t *out4)
{
    const uint32_t INIT_A = 0x43b0d7e5u, MULT_A = 0x931e8875u, INIT_B = 0x8b51f9ddu, MULT_B = 0x58f38dedu;
    const uint32_t MIX_MULT_L = 0xca01f9ddu, MIX_MULT_R = 0x4973f715u;
    uint32_t ent[16];
    int nent = 0;
    for (int q = 0; q < ns && q < 8; q++) {
        uint64_t seed = seeds[q];
        do {
            ent[nent++] = (uint32_t)(seed & 0xFFFFFFFFu);
            seed >>= 32;
        } while (seed);
    }
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
    uint32_t st[8];
    uint32_t hb = INIT_B;
    for (int i = 0; i < 8; i++) {
        uint32_t v = pool[i % 4];
        v ^= hb;
        hb *= MULT_B;
        v *= hb;
        v ^= v >> 16;
        st[i] = v;
    }
    for (int i = 0; i < 4; i++)
        out4[i] = (uint64_t)st[2 * i] | ((uint64_t)st[2 * i + 1] << 32);
}

static void seed_sequence(uint64_t seed, uint64_t *out4)
{
    seed_sequence_n(&seed, 1, out4);
}

/* PCG64(SeedSequence(seeds)) */
static void npy_pcg64_seed_n(NpyPCG64 *r, const uint64_t *seeds, int ns)
{
    uint64_t v[4];
    seed_sequence_n(seeds, ns, v);
    __uint128_t s = (((__uint128_t)v[0]) << 64) | v[1];
    __uint128_t inc = (((__uint128_t)v[2]) << 64) | v[3];
    r->state = 0;
    r->inc = (inc << 1) | 1u;
    pcg_step(r);
    r->state += s;
    pcg_step(r);
}

/* PCG64(SeedSequence(seed)) */
static void npy_pcg64_seed(NpyPCG64 *r, uint64_t seed)
{
    uint64_t v[4];
    seed_sequence(seed, v);
    __uint128_t s = (((__uint128_t)v[0]) << 64) | v[1];
    __uint128_t inc = (((__uint128_t)v[2]) << 64) | v[3];
    r->state = 0;
    r->inc = (inc << 1) | 1u;
    pcg_step(r);
    r->state += s;
    pcg_step(r);
}

/* numpy's random_standard_normal (the ziggurat) */
static double npy_standard_normal(NpyPCG64 *r)
{
    const double ZIG_R = 3.6541528853610087963519472518, ZIG_INV_R = 0.27366123732975827203338247596;
    for (;;) {
        uint64_t rr = pcg_next64(r);
        int idx = (int)(rr & 0xff);
        rr >>= 8;
        int sign = (int)(rr & 0x1);
        uint64_t rabs = (rr >> 1) & 0x000fffffffffffffULL;
        double x = (double)rabs * NPY_WI[idx];
        if (sign & 0x1)
            x = -x;
        if (rabs < NPY_KI[idx])
            return x;
        if (idx == 0) {
            for (;;) {
                double xx = -ZIG_INV_R * log1p(-pcg_next_double(r));
                double yy = -log1p(-pcg_next_double(r));
                if (yy + yy > xx * xx)
                    return ((rabs >> 8) & 0x1) ? -(ZIG_R + xx) : ZIG_R + xx;
            }
        } else {
            if (((NPY_FI[idx - 1] - NPY_FI[idx]) * pcg_next_double(r) + NPY_FI[idx]) < exp(-0.5 * x * x))
                return x;
        }
    }
}

/* default_rng(seed).standard_normal(n), into out */
void nv_npy_normals(unsigned long long seed, long n, double *out)
{
    NpyPCG64 r;
    npy_pcg64_seed(&r, seed);
    for (long i = 0; i < n; i++)
        out[i] = npy_standard_normal(&r);
}

/* a generator kept between calls (live's Wind: one normal a block), as a handle */
void *nv_npy_new(unsigned long long seed)
{
    NpyPCG64 *r = (NpyPCG64 *)malloc(sizeof(NpyPCG64));
    if (r)
        npy_pcg64_seed(r, seed);
    return r;
}

double nv_npy_next(void *g) { return npy_standard_normal((NpyPCG64 *)g); }

void nv_npy_free(void *g) { free(g); }

/* efxbus.noise: n samples from absolute sample n0, each chunk (8192) of
   them default_rng([seed, chunk]) -- its standard_normal (uniform 0: its
   random) -- so windows draw what the whole does */
void nv_npy_noise(long long n0, long n, unsigned long long seed, int normal, double *out)
{
    const long long CH = 8192;
    if (n <= 0)
        return;
    long long k0 = n0 / CH, k1 = (n0 + n - 1) / CH;
    for (long long k = k0; k <= k1; k++) {
        NpyPCG64 r;
        const uint64_t sd[2] = {(uint64_t)seed, (uint64_t)k};
        npy_pcg64_seed_n(&r, sd, 2);
        long long a = n0 > k * CH ? n0 : k * CH, b = n0 + n < (k + 1) * CH ? n0 + n : (k + 1) * CH;
        for (long long i = k * CH; i < b; i++) {
            double x = normal ? npy_standard_normal(&r) : pcg_next_double(&r);
            if (i >= a)
                out[i - n0] = x;
        }
    }
}
