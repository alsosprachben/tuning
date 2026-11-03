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
static void seed_sequence(uint64_t seed, uint64_t *out4)
{
    const uint32_t INIT_A = 0x43b0d7e5u, MULT_A = 0x931e8875u, INIT_B = 0x8b51f9ddu, MULT_B = 0x58f38dedu;
    const uint32_t MIX_MULT_L = 0xca01f9ddu, MIX_MULT_R = 0x4973f715u;
    uint32_t ent[2];
    int nent = 0;
    do {                                        /* _coerce_to_uint32_array: 32-bit words, least first */
        ent[nent++] = (uint32_t)(seed & 0xFFFFFFFFu);
        seed >>= 32;
    } while (seed && nent < 2);
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
