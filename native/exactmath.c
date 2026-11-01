/* exactmath.c -- array math as libm does it, one element at a time.
 *
 * numpy's float64 exp, log, power and complex abs over arrays are its own
 * SIMD routines (SVML on AVX-512): they differ from libm in the last bit on
 * a fifth of their values here, and differently again on another machine
 * (ARM, Apple). Python code that wants the same bits everywhere -- and a C
 * port that can match it -- calls these instead: glibc's exp, pow and hypot
 * (CPython's abs of a complex), element by element. Built with the rest of
 * native/ (no builtins, no vectorisation of libm calls). */

void nv_exp_n(long n, const double *x, double *out)
{
    for (long i = 0; i < n; i++)
        out[i] = exp(x[i]);
}

/* x ** y elementwise; sx, sy: 0 for a scalar (the one value), 1 an array */
void nv_pow_n(long n, const double *x, int sx, const double *y, int sy, double *out)
{
    for (long i = 0; i < n; i++)
        out[i] = pow(x[sx ? i : 0], y[sy ? i : 0]);
}

/* abs of complex values (interleaved re, im) */
void nv_cabs_n(long n, const double *z, double *out)
{
    for (long i = 0; i < n; i++)
        out[i] = hypot(z[2 * i], z[2 * i + 1]);
}
