/* registercore.c -- the free-string register's arithmetic, in C (register.py).
 *
 * register.py's free_part, operation for operation: the free and forced
 * response of a driver partial (W_i, b_i per pair) on a set of free modes
 * (W_m, a_m), with the tension glide integrated where it matters. In numpy
 * the work was a few thousand complex exponentials per call, buried under
 * the per-call cost of building and masking small arrays; here it is a loop.
 * Not bit-identical to numpy (whose float64 exp is its own SIMD routine): the
 * register is checked against the Python path by tolerance
 * (examples/regclose.py), everything else stays table-identical.
 *
 * Built without -ffast-math, so the order of operations is the source's.
 */
#include <complex.h>
#include <math.h>
#include <stdlib.h>

#define NEAR 30.0                 /* register.NEAR */
#define STEP 0.02                 /* register.STEP */
#define TBEND_CUT_SCALE 1048576.0 /* register.TBEND_CUT_SCALE */

static double cut_time(double cut)
{
    return cut < 0 ? -cut * TBEND_CUT_SCALE : cut;
}

/* register.glide_phase for one time */
static double glide_phase(double Wi, double tb, double tau, double cut, double t)
{
    double ct = cut_time(cut);
    double tm = t < ct ? t : ct;
    if (cut < 0) {
        double e = exp(-tm / tau);
        double acc = 0.0, term = 1.0, ek = 1.0;
        for (int k = 1; k <= 40; k++) {
            term = term * tb / k;
            ek = ek * e;
            acc = acc + term * (1.0 - ek) / k;
        }
        return Wi * tau * acc;
    }
    return Wi * tb * tau * (1.0 - exp(-tm / tau));
}

static double glide_start(double tb, double cut)
{
    return cut < 0 ? expm1(tb) : tb;
}

/* numpy's complex expm1 (npymath nc_expm1) */
static double complex cexpm1(double complex z)
{
    double x = creal(z), y = cimag(z);
    double a = sin(y / 2.0);
    return (expm1(x) * cos(y) - 2.0 * a * a) + I * (exp(x) * sin(y));
}

/* register._glide_grid: times 0..cut; returns the count, *out malloc'd */
static int glide_grid(double cut, double tau, double **out)
{
    int cap = 64, n = 1;
    double *t = malloc(cap * sizeof(double));
    t[0] = 0.0;
    while (t[n - 1] < cut) {
        double nx = t[n - 1] + 0.5 * STEP * exp(t[n - 1] / (2.0 * tau));
        if (nx > cut)
            nx = cut;
        if (n == cap) {
            cap *= 2;
            t = realloc(t, cap * sizeof(double));
        }
        t[n++] = nx;
    }
    *out = t;
    return n;
}

/* free_part's integral for one pair over times tt[0..nt), clipped at the
 * cut, with ph[k] the glide's phase at tt[k] (the driver's: the same for
 * every pair, so computed once a call) */
static double complex integral(const double *tt, const double *ph, int nt, double ca, double wi,
                               double wm, double a_, double b_)
{
    double complex s = 0.0;
    double tp = tt[0] < ca ? tt[0] : ca;
    double complex gp = I * ((wi - wm) * tp + ph[0]) + (a_ - b_) * tp;
    for (int k = 1; k < nt; k++) {
        double t = tt[k] < ca ? tt[k] : ca;
        double complex g = I * ((wi - wm) * t + ph[k]) + (a_ - b_) * t;
        double dt = t - tp;
        double complex sl = (g - gp) / (dt > 0 ? dt : 1.0);
        double complex x = sl * dt;
        if (cabs(x) > 1e-9)
            s += cexp(gp) * cexpm1(x) / sl;
        else
            s += cexp(gp) * dt;
        tp = t;
        gp = g;
    }
    return s;
}

/* register.free_part for n pairs sharing one driver: c[i] complex, Wi, tb,
 * tau, cut scalars (one driver partial), bi/Wm/am per pair. Writes free[i]
 * and forced[i]. */
void free_part(int n, const double complex *c, double Wi, const double *bi, const double *Wm,
               const double *am, double tb, double tau, double cut, double need,
               double complex *freep, double complex *forced)
{
    for (int i = 0; i < n; i++) {
        double complex D = (I * Wi - bi[i]) - (I * Wm[i] - am[i]);
        forced[i] = c[i] / D;
        freep[i] = -forced[i];
    }
    if (tb == 0.0)
        return;
    double gs = glide_start(tb, cut);
    double ca = cut_time(cut);
    double *grid = NULL, *half = NULL, *pg = NULL, *ph = NULL;
    int ng = 0, nh = 0;
    for (int i = 0; i < n; i++) {
        double complex D0 = (I * Wi * (1.0 + gs) - bi[i]) - (I * Wm[i] - am[i]);
        freep[i] = -c[i] / D0;
        double width = fabs(Wi * gs) + fabs(am[i] - bi[i]) + 1.0;
        if (!(fabs(Wi - Wm[i]) < NEAR * width) || !(cabs(freep[i]) >= need))
            continue;
        if (grid == NULL) {
            ng = glide_grid(ca, tau, &grid);
            /* the grid and its midpoints, in order (sorted, as numpy sorts them) */
            nh = 2 * ng - 1;
            half = malloc(nh * sizeof(double));
            for (int k = 0; k < ng; k++) {
                half[2 * k] = grid[k];
                if (k + 1 < ng)
                    half[2 * k + 1] = 0.5 * (grid[k + 1] + grid[k]);
            }
            /* the glide's phase at each time, clipped at the cut as the
               integral clips its times */
            pg = malloc(ng * sizeof(double));
            ph = malloc(nh * sizeof(double));
            for (int k = 0; k < ng; k++)
                pg[k] = glide_phase(Wi, tb, tau, cut, grid[k] < ca ? grid[k] : ca);
            for (int k = 0; k < nh; k++)
                ph[k] = glide_phase(Wi, tb, tau, cut, half[k] < ca ? half[k] : ca);
        }
        double complex y = c[i] * (4.0 * integral(half, ph, nh, ca, Wi, Wm[i], am[i], bi[i])
                                   - integral(grid, pg, ng, ca, Wi, Wm[i], am[i], bi[i])) / 3.0;
        double th = glide_phase(Wi, tb, tau, cut, ca);
        freep[i] = y - forced[i] * cexp(I * th + (I * (Wi - Wm[i]) + (am[i] - bi[i])) * ca);
    }
    free(grid);
    free(half);
    free(pg);
    free(ph);
}
