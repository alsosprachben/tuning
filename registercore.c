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
 * Built without -ffast-math or fused multiply-adds, so the order of operations
 * is the source's; the glide's integral alone is vectorised (integral_batch).
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

/* THE GLIDE'S INTEGRAL FOR MANY PAIRS AT ONCE. Every near pair of a call
 * integrates over the same times with the same glide phase ph[k] (the
 * driver's); a pair differs only by its offset dw = W_i - W_m and its decay
 * difference da = a_m - b_i. So the loop runs over the times outside and the
 * pairs inside, in real arithmetic, where gcc vectorises it -- exp, expm1,
 * sin and cos from glibc's vector library (libmvec), 8 pairs a step on
 * AVX-512. Each step is exact for a linear exponent, as before:
 *     exp(g_{k-1}) (e^x - 1) / (x / dt),   x = g_k - g_{k-1}
 * with numpy's complex expm1 (e^x - 1 = expm1(xr) cos xi - 2 sin^2(xi/2)
 * + i e^xr sin xi), and exp(g_{k-1}) dt where |x| is too small. Not
 * bit-identical to the scalar loop it replaces (the vector routines differ
 * in the last bits); checked by tolerance like the rest of the core. */
#pragma omp declare simd notinbranch
extern double exp(double);
#pragma omp declare simd notinbranch
extern double expm1(double);
#pragma omp declare simd notinbranch
extern double sin(double);
#pragma omp declare simd notinbranch
extern double cos(double);

static void integral_batch(const double *tt, const double *ph, int nt, double ca, int np,
                           const double *dw, const double *da, double *sre, double *sim)
{
    double *gr = malloc(np * sizeof(double)), *gi = malloc(np * sizeof(double));
    double tp = tt[0] < ca ? tt[0] : ca;
    for (int p = 0; p < np; p++) {
        gi[p] = dw[p] * tp + ph[0];
        gr[p] = da[p] * tp;
        sre[p] = 0.0;
        sim[p] = 0.0;
    }
    for (int k = 1; k < nt; k++) {
        double t = tt[k] < ca ? tt[k] : ca;
        double dt = t - tp;
        double phk = ph[k];
        if (dt > 0) {
#pragma omp simd
            for (int p = 0; p < np; p++) {
                double nr = da[p] * t, ni = dw[p] * t + phk;
                double xr = nr - gr[p], xi = ni - gi[p];
                double e = exp(gr[p]);
                double er = e * cos(gi[p]), ei = e * sin(gi[p]);
                double h = sin(0.5 * xi);
                double mr = expm1(xr) * cos(xi) - 2.0 * h * h;
                double mi = exp(xr) * sin(xi);
                double xx = xr * xr + xi * xi;
                /* (e^x - 1) dt / x, and its limit dt where x is too small */
                double big = xx > 1e-18;
                double inv = big ? dt / (big ? xx : 1.0) : 0.0;
                double qr = big ? (mr * xr + mi * xi) * inv : dt;
                double qi = big ? (mi * xr - mr * xi) * inv : 0.0;
                sre[p] += er * qr - ei * qi;
                sim[p] += er * qi + ei * qr;
                gr[p] = nr;
                gi[p] = ni;
            }
        }
        tp = t;
    }
    free(gr);
    free(gi);
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
    /* the pairs the glide matters for: near, and able to reach `need` */
    int *near = malloc((n > 0 ? n : 1) * sizeof(int));
    int nn = 0;
    for (int i = 0; i < n; i++) {
        double complex D0 = (I * Wi * (1.0 + gs) - bi[i]) - (I * Wm[i] - am[i]);
        freep[i] = -c[i] / D0;
        double width = fabs(Wi * gs) + fabs(am[i] - bi[i]) + 1.0;
        if (fabs(Wi - Wm[i]) < NEAR * width && cabs(freep[i]) >= need)
            near[nn++] = i;
    }
    if (nn) {
        double *grid, *half, *pg, *ph;
        int ng = glide_grid(ca, tau, &grid);
        /* the grid and its midpoints, in order (sorted, as numpy sorts them) */
        int nh = 2 * ng - 1;
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
        double *dw = malloc(nn * sizeof(double)), *da = malloc(nn * sizeof(double));
        double *hr = malloc(nn * sizeof(double)), *hi = malloc(nn * sizeof(double));
        double *qr = malloc(nn * sizeof(double)), *qi = malloc(nn * sizeof(double));
        for (int q = 0; q < nn; q++) {
            dw[q] = Wi - Wm[near[q]];
            da[q] = am[near[q]] - bi[near[q]];
        }
        integral_batch(half, ph, nh, ca, nn, dw, da, hr, hi);
        integral_batch(grid, pg, ng, ca, nn, dw, da, qr, qi);
        double th = glide_phase(Wi, tb, tau, cut, ca);
        for (int q = 0; q < nn; q++) {
            int i = near[q];
            double complex y = c[i] * (4.0 * (hr[q] + I * hi[q]) - (qr[q] + I * qi[q])) / 3.0;
            freep[i] = y - forced[i] * cexp(I * th + (I * (Wi - Wm[i]) + (am[i] - bi[i])) * ca);
        }
        free(grid); free(half); free(pg); free(ph);
        free(dw); free(da); free(hr); free(hi); free(qr); free(qi);
    }
    free(near);
}

/* ------------------------------------------------------------------ a strike */

/* register.Channel._strikes' loop over one strike's driver partials, row by
 * row and stage by stage as the Python walks them: the free modes in reach
 * (fi, sorted by W), their bridge weight (Strings.coupling), the coincident
 * pairs' raised decay (coincident), the response (free_part), and from it
 * the free part's kick (add) and what the forced part holds at the driver's
 * damper (xfer), both per mode, over M modes. The forced rows come back in
 * the order the Python makes them: (row, decay, value re the driver) in
 * f_r/f_beta/f_val, up to cap; the count is returned (more than cap: call
 * again with room, add and xfer zeroed). last_noff, last_re: the noff and
 * re of the last row over the floor, -1 if none. */
int strike_drive(int R, const double *aM, const double *om, const double *non, const double *p0,
                 const double *delL, const double *noff, const double *re_, const double *tbav,
                 const double *tau, const double *tcut, const double *aft, const double *sus,
                 const double *logr, const double *logrA, const long *choir,
                 int nf, const long *fi, const double *W, const double *alpha, const double *w,
                 const long *bridge, const long *mkey, const long *choir_bridges, double cross,
                 long keybridge, long partner, double partner_k,
                 double kappa, double floor_, double split, double sr, double b,
                 double complex *add, double complex *xfer,
                 int cap, int *f_r, double *f_beta, double complex *f_val,
                 double *last_noff, double *last_re)
{
    int nfo = 0;
    *last_noff = -1.0;
    *last_re = -1.0;
    double *fW = malloc((nf > 0 ? nf : 1) * sizeof(double));
    for (int k = 0; k < nf; k++)
        fW[k] = W[fi[k]];
    /* scratch, as large as a reach can be */
    double *wj = malloc((nf > 0 ? nf : 1) * sizeof(double));
    double *bj = malloc((nf > 0 ? nf : 1) * sizeof(double));
    double *Wj = malloc((nf > 0 ? nf : 1) * sizeof(double));
    double *aj = malloc((nf > 0 ? nf : 1) * sizeof(double));
    char *close = malloc((nf > 0 ? nf : 1));
    double complex *cj = malloc((nf > 0 ? nf : 1) * sizeof(double complex));
    double complex *fr = malloc((nf > 0 ? nf : 1) * sizeof(double complex));
    double complex *fo = malloc((nf > 0 ? nf : 1) * sizeof(double complex));
    double need = floor_ * split;
    for (int r = 0; r < R; r++) {
        double a_i = aM[r];
        if (a_i < floor_)
            continue;
        double om_i = om[r], Wi = om_i * sr, n_i = non[r];
        double theta = om_i * n_i + p0[r] + om_i * delL[r];
        double n_off = noff[r];
        *last_noff = n_off;
        *last_re = re_[r];
        double tb = tbav[r], ta = tau[r], cu = tcut[r];
        /* register.stages */
        double sw[3], sb[3];
        int ns = 0;
        if ((1.0 - sus[r]) * (1.0 - aft[r]) > 0) { sw[ns] = (1.0 - sus[r]) * (1.0 - aft[r]); sb[ns++] = logr[r]; }
        if ((1.0 - sus[r]) * aft[r] > 0) { sw[ns] = (1.0 - sus[r]) * aft[r]; sb[ns++] = logrA[r]; }
        if (sus[r] > 0) { sw[ns] = sus[r]; sb[ns++] = 0.0; }
        for (int s = 0; s < ns; s++) {
            double wgt = sw[s], beta = sb[s];
            double cmax = kappa * a_i * wgt;
            if (cmax <= 0)
                continue;
            double reach = cmax / (floor_ * split);
            /* np.searchsorted, side left */
            int lo = 0, hi = nf;
            { int a = 0, z = nf; double v = Wi - reach;
              while (a < z) { int m = (a + z) / 2; if (fW[m] < v) a = m + 1; else z = m; } lo = a; }
            { int a = 0, z = nf; double v = Wi + reach;
              while (a < z) { int m = (a + z) / 2; if (fW[m] < v) a = m + 1; else z = m; } hi = a; }
            if (hi <= lo)
                continue;
            int n = hi - lo;
            long kb = choir[r] >= 0 ? choir_bridges[choir[r]] : keybridge;
            for (int q = 0; q < n; q++) {
                long j = fi[lo + q];
                double x = w[j];
                if (kb >= 0)
                    x = x * (bridge[j] == kb ? 1.0 : cross);
                if (partner >= 0)
                    x = x * (mkey[j] == partner ? partner_k : 1.0);
                wj[q] = x;
                Wj[q] = W[j];
                aj[q] = alpha[j];
                /* register.coincident (ROWS_OVER 1) */
                double cw = kappa * wgt * x;
                double complex D = (I * Wi - beta) - (I * W[j] - alpha[j]);
                double thr = cw / 1.0;
                close[q] = cabs(D) < thr;
                bj[q] = close[q] ? (beta > alpha[j] ? beta : alpha[j]) + thr : beta;
                cj[q] = cmax * x;
            }
            free_part(n, cj, Wi, bj, Wj, aj, tb, ta, cu, need, fr, fo);
            double tq = (n_off - n_i) / sr;
            double gq = glide_phase(Wi, tb, ta, cu, tq);
            double complex F = 0.0;
            for (int q = 0; q < n; q++) {
                long j = fi[lo + q];
                add[j] += fr[q] * cexp(I * (theta - Wj[q] * n_i / sr) + aj[q] * (n_i - b) / sr);
                if (!close[q])
                    F += fo[q];
            }
            if (cabs(F) > need) {
                if (nfo < cap) { f_r[nfo] = r; f_beta[nfo] = beta; f_val[nfo] = F / a_i; }
                nfo++;
            }
            for (int q = 0; q < n; q++) {
                if (close[q] && cabs(fo[q]) > need) {
                    if (nfo < cap) { f_r[nfo] = r; f_beta[nfo] = bj[q]; f_val[nfo] = fo[q] / a_i; }
                    nfo++;
                }
            }
            for (int q = 0; q < n; q++) {
                long j = fi[lo + q];
                xfer[j] += fo[q] * cexp(I * (theta + Wi * tq + gq - Wj[q] * n_off / sr) - bj[q] * tq);
            }
        }
    }
    free(fW); free(wj); free(bj); free(Wj); free(aj); free(close); free(cj); free(fr); free(fo);
    return nfo;
}

/* ------------------------------------------------------------------ the felt */

/* register.Channel._dcum: the felt's damping done by sample n[i] (nepers at
 * key[i]'s fundamental), for each of n queries. Each key's breakpoints
 * bk[], rates and cumulative damping D[] are a slice of the flat arrays,
 * off[key]..off[key + 1] (an empty slice: never damped). The same
 * arithmetic, in the same order, as the numpy: bit-identical. */
void dcum(int n, const long *key, const double *t, const long *off, const double *bk,
          const double *rate, const double *D, double sr, double *out)
{
    for (int q = 0; q < n; q++) {
        long k = key[q];
        long a = off[k], z = off[k + 1];
        if (z <= a) {
            out[q] = 0.0;
            continue;
        }
        /* np.searchsorted(bk, t, 'right') - 1 */
        long lo = a, hi = z;
        while (lo < hi) {
            long m = (lo + hi) / 2;
            if (bk[m] <= t[q]) lo = m + 1; else hi = m;
        }
        long i = lo - 1;
        out[q] = i >= a ? D[i] + rate[i] * (t[q] - bk[i]) / sr : 0.0;
    }
}

/* ------------------------------------------------------------------ free rows */

/* register.Channel._update's loop over the modes whose row has drifted (go):
 * each closes the row it had (closed at b, unless closed earlier), and,
 * where it is still over the floor and its string is free, opens a new one
 * -- its values written straight into the row store's columns, at row
 * index n onward. Python's math.atan2, math.log and abs(complex) are the
 * same libm calls (atan2, log, hypot), the arithmetic in the same order, no
 * fused multiply-adds: bit-identical. Returns the rows written; the store
 * must have room for ngo more (the caller grows it first).
 *
 * Per mode (M of them): Az (complex), am (alpha), dw (the felt's weight, or
 * NULL), W, f, hl, hr, dl, dr, px, string, key; state: rrow (its open row
 * or -1), has, r_b, r_nfloor, r_closed, Rz (complex), rref, r_lr.
 * Per go mode k: go[k], free_now[k], drate[k] (or NULL).
 * Per row (the store): om p0 p0R aL aR aM nf non fa logr delL delR px pl,
 * mode key b n_floor closed seq src. open_ids: the open rows, appended. */
int free_rows(int ngo, const long *go, const char *free_now, const double *drate,
              const double complex *Az, const double *am, const double *dw, const double *W,
              const double *f, const double *hl, const double *hr, const double *dl, const double *dr,
              const double *px, const long *string, const long *key,
              long *rrow, char *has, double *r_b, double *r_nfloor, double *r_closed,
              double complex *Rz, double *rref, double *r_lr,
              double floor_, double b, double sr, double blk, long src,
              long n, long *seq,
              double *c_om, double *c_p0, double *c_p0R, double *c_aL, double *c_aR, double *c_aM,
              double *c_nf, double *c_non, double *c_fa, double *c_logr, double *c_delL,
              double *c_delR, double *c_px, long *c_pl, long *c_mode, long *c_key, double *c_b,
              double *c_nfloor, double *c_closed, long *c_seq, long *c_src,
              long *open_ids, long nopen)
{
    long n0 = n;
    for (int k = 0; k < ngo; k++) {
        long i = go[k];
        long rec = rrow[i];
        if (rec >= 0 && c_closed[rec] > b) {      /* (None is +inf: always over b) */
            c_closed[rec] = b;
            r_closed[i] = b;
        }
        rrow[i] = -1;
        has[i] = 0;
        double complex z = Az[i];
        double az = cabs(z);
        if (az < floor_ || !free_now[k])
            continue;
        double lr = am[i] + (dw ? dw[i] * drate[k] : 0.0);
        double n_floor = b + sr * log(az / floor_) / (lr > 1e-9 ? lr : 1e-9);
        double om = W[i] / sr;
        double ph = atan2(cimag(z), creal(z));
        c_om[n] = om;
        c_p0[n] = ph - om * dl[i];
        c_p0R[n] = ph - om * dr[i];
        c_aL[n] = az * hl[i];
        c_aR[n] = az * hr[i];
        c_aM[n] = az;
        c_nf[n] = f[i];
        c_non[n] = b;
        c_fa[n] = blk;
        c_logr[n] = lr;
        c_delL[n] = dl[i];
        c_delR[n] = dr[i];
        c_px[n] = px[i];
        c_pl[n] = string[i];
        c_mode[n] = i;
        c_key[n] = key[i];
        c_b[n] = b;
        c_nfloor[n] = n_floor;
        c_closed[n] = 1.0 / 0.0;
        c_seq[n] = (*seq)++;
        c_src[n] = src;
        open_ids[nopen++] = n;
        rrow[i] = n;
        has[i] = 1;
        r_b[i] = b;
        r_nfloor[i] = n_floor;
        r_closed[i] = 1.0 / 0.0;
        Rz[i] = z;
        rref[i] = b;
        r_lr[i] = lr;
        n++;
    }
    return (int)(n - n0);
}
