/* pycompat.h -- Python's arithmetic where C's differs, for bit-identical ports.
 *
 * THE RANDOM STREAMS: CPython's random.Random is MT19937, seeded from an int
 * by init_by_array over the int's 32-bit words (low first); random() is
 * 53 bits from two outputs; uniform(a, b) is a + (b - a) * random(). A voice
 * that draws from a seeded Random (unison_voices' beat scatter, the solo
 * vibrato) draws the same numbers here.
 *
 * sum() OF FLOATS is CPython 3.12's compensated (Neumaier) sum: the first
 * item, then each added with its compensation, the compensation added at the
 * end. x ** y is libm pow; max/min keep the first of equals; round() of a
 * float is round-half-even (rint in the default rounding mode).
 */
#ifndef PYCOMPAT_H
#define PYCOMPAT_H

#include <math.h>
#include <stdint.h>

typedef struct {
    uint32_t mt[624];
    int i;
} PyRandom;

static void pyr_init_genrand(PyRandom *r, uint32_t s)
{
    r->mt[0] = s;
    for (int i = 1; i < 624; i++)
        r->mt[i] = (uint32_t)(1812433253u * (r->mt[i - 1] ^ (r->mt[i - 1] >> 30)) + (uint32_t)i);
    r->i = 624;
}

static void pyr_init_by_array(PyRandom *r, const uint32_t *key, int klen)
{
    pyr_init_genrand(r, 19650218u);
    int i = 1, j = 0;
    for (int k = (624 > klen ? 624 : klen); k; k--) {
        r->mt[i] = (r->mt[i] ^ ((r->mt[i - 1] ^ (r->mt[i - 1] >> 30)) * 1664525u)) + key[j] + (uint32_t)j;
        i++; j++;
        if (i >= 624) { r->mt[0] = r->mt[623]; i = 1; }
        if (j >= klen) j = 0;
    }
    for (int k = 623; k; k--) {
        r->mt[i] = (r->mt[i] ^ ((r->mt[i - 1] ^ (r->mt[i - 1] >> 30)) * 1566083941u)) - (uint32_t)i;
        i++;
        if (i >= 624) { r->mt[0] = r->mt[623]; i = 1; }
    }
    r->mt[0] = 0x80000000u;
    r->i = 624;
}

/* random.Random(n) for an int n: its magnitude's 32-bit words, low first */
static void pyr_seed(PyRandom *r, long long n)
{
    uint64_t a = n < 0 ? (uint64_t)(-n) : (uint64_t)n;
    uint32_t key[2];
    int klen = 0;
    do {
        key[klen++] = (uint32_t)(a & 0xffffffffu);
        a >>= 32;
    } while (a);
    pyr_init_by_array(r, key, klen);
}

static uint32_t pyr_genrand(PyRandom *r)
{
    static const uint32_t mag01[2] = {0x0u, 0x9908b0dfu};
    uint32_t y;
    if (r->i >= 624) {
        int kk;
        for (kk = 0; kk < 624 - 397; kk++) {
            y = (r->mt[kk] & 0x80000000u) | (r->mt[kk + 1] & 0x7fffffffu);
            r->mt[kk] = r->mt[kk + 397] ^ (y >> 1) ^ mag01[y & 1u];
        }
        for (; kk < 623; kk++) {
            y = (r->mt[kk] & 0x80000000u) | (r->mt[kk + 1] & 0x7fffffffu);
            r->mt[kk] = r->mt[kk + (397 - 624)] ^ (y >> 1) ^ mag01[y & 1u];
        }
        y = (r->mt[623] & 0x80000000u) | (r->mt[0] & 0x7fffffffu);
        r->mt[623] = r->mt[396] ^ (y >> 1) ^ mag01[y & 1u];
        r->i = 0;
    }
    y = r->mt[r->i++];
    y ^= (y >> 11);
    y ^= (y << 7) & 0x9d2c5680u;
    y ^= (y << 15) & 0xefc60000u;
    y ^= (y >> 18);
    return y;
}

static double pyr_random(PyRandom *r)
{
    uint32_t a = pyr_genrand(r) >> 5, b = pyr_genrand(r) >> 6;
    return (a * 67108864.0 + b) * (1.0 / 9007199254740992.0);
}

static double pyr_uniform(PyRandom *r, double a, double b)
{
    return a + (b - a) * pyr_random(r);
}

/* sum() of n floats, as CPython 3.12+ adds them */
static double pysum(const double *x, int n)
{
    if (n <= 0)
        return 0.0;
    double f = x[0], c = 0.0;
    for (int i = 1; i < n; i++) {
        double t = f + x[i];
        if (fabs(f) >= fabs(x[i]))
            c += (f - t) + x[i];
        else
            c += (x[i] - t) + f;
        f = t;
    }
    if (c != 0.0 && isfinite(c))
        f += c;
    return f;
}

#endif
