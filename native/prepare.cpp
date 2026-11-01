// prepare.cpp -- the native engine's TABLE: blockrender.prepare's result for
// a piano song -- its notes and register (nv_play_full), how long the render
// runs (the music, then on to where the last partial falls under RING_FLOOR,
// at most RING_MAX past it: _prep_ring_length / ring_last) and the room's
// power per band (room_q, from the tallies the notes carried).

#include <cmath>

#include "nv.h"

extern "C" {

long long nv_play_full(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr,
                       PyRandom *rs, double **rowsp, double *qacc, double *azimuth, const int *kind,
                       double scale, double full_db_s, double residual, double beta, long long blk,
                       long long *nnote);

// blockrender.ring_last over rows (NCOLS each, EMIT_COLS): the last sample any
// sounds above floor_, 0 if none does
static long long ring_last(const double *rows, long long n, double floor_, double sr)
{
    enum { om, p0, p0R, aL, aR, aM, mch, px, pz, az, dr, nf, non, noff, fa, re, ch, logr, logrA, aft, sus };
    enum { delL = 37, delR = 38 };
    double best = -INFINITY;
    for (long long i = 0; i < n; i++) {
        const double *r = rows + NCOLS * i;
        double a1 = fabs(r[aL]), a2 = fabs(r[aR]);
        double a = a2 > a1 ? a2 : a1;                   /* np.maximum */
        double sl = r[sus], af = r[aft];
        double t = 0.0;
        double cs[2] = {(1.0 - sl) * (1.0 - af) * a, (1.0 - sl) * af * a};
        double ls[2] = {r[logr], r[logrA]};
        for (int s = 0; s < 2; s++) {
            double c = cs[s], lr = ls[s];
            int loud = c > floor_;
            double tt = lr > 0.0 ? log((loud ? c : 1.0) / floor_) / lr : INFINITY;
            double v = loud ? tt : 0.0;
            t = v > t ? v : t;                          /* np.maximum (no NaN here) */
        }
        if (sl * a > floor_)
            t = INFINITY;
        double stop = r[noff] + r[re];
        double x = r[non] + t * sr;
        double out = x < stop ? x : stop;               /* np.minimum */
        if (!(a > floor_))
            out = 0.0;
        double d = r[delR] > r[delL] ? r[delR] : r[delL];
        out += d;
        if (i == 0 || out > best)
            best = out;
    }
    return n ? (long long)ceil(best) : 0;
}

// THE TABLE for a piano song: its rows (nv_play_full) into *rowsp, and
// out[]: N (the render's samples), nblk, P (rows), the notes' rows, then
// room_q's nine (band Hz, Q, energy). total: the song's length (s);
// ring_floor, ring_max: blockrender's RING_FLOOR and RING_MAX. Returns P, or
// < 0 as nv_play_full.
long long nv_prepare(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr,
                     PyRandom *rs, double **rowsp, double *qacc, double *azimuth, const int *kind, double scale,
                     double full_db_s, double residual, double beta, long long blk, double total, double ring_floor,
                     double ring_max, double *out)
{
    long long nnote = 0;
    long long P = nv_play_full(song, K, tmpl, br, nbr, rs, rowsp, qacc, azimuth, kind, scale, full_db_s, residual,
                               beta, blk, &nnote);
    if (P < 0)
        return P;
    const double sr = tmpl->sr;
    long long srl = (long long)sr;
    long long N = (long long)(total * sr) + srl;
    long long nblk = N / blk + 2;
    long long rl = ring_last(*rowsp, P, ring_floor, sr);
    long long cap = (long long)((total + ring_max) * sr);
    rl = rl + blk < cap ? rl + blk : cap;               /* min(rl + BLK, int((total + RING_MAX) * SR)) */
    if (rl > N)
        N = rl;
    out[0] = (double)N;
    out[1] = (double)nblk;
    out[2] = (double)P;
    out[3] = (double)nnote;                             /* where the notes' rows end (sym_rows) */
    for (int i = 0; i < 9; i++) {
        double d = qacc[2 * i], r = qacc[2 * i + 1];
        out[4 + 3 * i] = tmpl->room_bands[i];
        out[4 + 3 * i + 1] = r > 0.0 ? d / r : 1.0;
        out[4 + 3 * i + 2] = d;
    }
    return P;
}

}  // extern "C"
