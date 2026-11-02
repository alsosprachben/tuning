// prepare.cpp -- the native engine's TABLE: blockrender.prepare's result for
// a piano song -- its notes and register (nv_play_full), how long the render
// runs (the music, then on to where the last partial falls under RING_FLOOR,
// at most RING_MAX past it: _prep_ring_length / ring_last) and the room's
// power per band (room_q, from the tallies the notes carried), and a
// half-pedalled channel's damper tracks (blockrender._damp_close,
// damper.track, damper.onto_tracks): each released note that meets the band,
// its felt block by block from key-up to landing, onto its rows.

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <vector>

#include "nv.h"

extern "C" {

long long nv_play_full(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr,
                       PyRandom *rs, double **rowsp, double *qacc, double *azimuth, const int *kind,
                       double scale, double full_db_s, double residual, double beta, long long blk,
                       long long *nnote, int *played_out, long long *row0_out, int *bands, double *offs,
                       int with_register);

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

struct Track {
    long long r0, r1, b0;
    double f0;
    std::vector<float> dc;
};

// damper.threshold_db / rate_db_s
static double threshold_db(double c, double knee)
{
    if (c <= 0.0)
        return INFINITY;
    if (c >= 1.0)
        return -INFINITY;
    return -knee * c / (1.0 - c);
}

// THE TABLE for a piano song: its rows (nv_play_full) into *rowsp, and
// out[] (48): N (the render's samples), nblk, P (rows), the notes' rows,
// room_q's nine (band Hz, Q, energy) from out[4]; out[40], out[41] the damper
// tracks used and DM's length (0: none), their arrays in dm[] (malloc'd:
// dk, dg, DM, DMO, DMB, DMN). total: the song's length (s);
// ring_floor, ring_max: blockrender's RING_FLOOR and RING_MAX. Returns P, or
// < 0 as nv_play_full.
long long nv_prepare(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr,
                     PyRandom *rs, double **rowsp, double *qacc, double *azimuth, const int *kind, double scale,
                     double full_db_s, double residual, double beta, long long blk, double total, double ring_floor,
                     double ring_max, double *out, double knee_db, double ln10_20, double xdec_nepers, double SR,
                     void **dm, int with_register)
{
    long long nnote = 0;
    int nn = nv_song_n_notes(song);
    std::vector<int> played(nn), bands(nn);
    std::vector<long long> row0(nn);
    std::vector<double> offs(nn);
    long long P = nv_play_full(song, K, tmpl, br, nbr, rs, rowsp, qacc, azimuth, kind, scale, full_db_s, residual,
                               beta, blk, &nnote, played.data(), row0.data(), bands.data(), offs.data(),
                               with_register);
    if (P < 0)
        return P;
    // THE STROKES' ROWS (stroke_rows): each gesture's stroke's, from its
    // first row to the next note's
    for (int j = 0; j < nn; j++)
        if (nv_song_stroked(song, played[j])) {
            long long r1 = j + 1 < nn ? row0[j + 1] : nnote;
            if (r1 > row0[j])
                nv_song_add_stroke_rows(song, row0[j], r1);
        }
    out[40] = 0.0;
    out[41] = 0.0;
    const double sr = tmpl->sr;
    long long srl = (long long)sr;
    long long N = (long long)(total * sr) + srl;
    long long nblk = N / blk + 2;
    (void)SR;
    long long rl = ring_last(*rowsp, P, ring_floor, sr);
    long long cap = (long long)((total + ring_max) * sr);
    rl = rl + blk < cap ? rl + blk : cap;               /* min(rl + BLK, int((total + RING_MAX) * SR)) */
    if (rl > N)
        N = rl;
    out[0] = (double)N;
    out[1] = (double)nblk;
    out[2] = (double)P;
    out[3] = (double)nnote;                             /* where the notes' rows end (sym_rows) */
    // THE HALF-PEDAL'S TRACKS (_damp_close, damper.track): each note whose
    // key-up meets the band, from its rows' fundamental and its pedal
    const double *rows = *rowsp;
    enum { C_nf = 11, C_non = 12, C_logr = 17, C_logrA = 18, C_aft = 19, C_sus = 20, C_gr = 39 };
    std::vector<Track> tracks;
    for (int j = 0; j < nn; j++) {
        if (!bands[j])
            continue;
        int i = played[j];
        long long ch;
        int iv[4];
        double dv[2];
        nv_song_get_note(song, i, &ch, iv, dv);
        long long r0 = row0[j], r1 = j + 1 < nn ? row0[j + 1] : nnote;
        if (r1 <= r0)
            continue;
        int key = iv[0], vel = iv[1];
        double on = dv[0], off = dv[1], land = offs[j];
        double f0 = 440.0 * pow(2.0, (key - 69) / 12.0);
        long long jb = r0;
        double best = 0.0;
        for (long long r = r0; r < r1; r++) {
            double nf = rows[NCOLS * r + C_nf];
            double v = fabs(log((nf > 1e-3 ? nf : 1e-3) / f0));     /* np.maximum, then |log| */
            if (r == r0 || v < best) {
                best = v;
                jb = r;
            }
        }
        const double *R = rows + NCOLS * jb;
        double lr = R[C_logr], lra = R[C_logrA], af = R[C_aft], su = R[C_sus];
        double vdb = 40.0 * log10((vel > 1 ? vel : 1) / 127.0);
        long long b0 = (long long)(off * SR) / blk;
        long long b1 = (long long)ceil(land * SR / blk);
        if (nblk < b1)
            b1 = nblk;
        int npv = nv_song_pedal_values(song, ch, nullptr, nullptr, 0);
        std::vector<double> pt(npv);
        std::vector<int> pv(npv);
        nv_song_pedal_values(song, ch, pt.data(), pv.data(), npv);
        auto pedal_at = [&](double t) {
            int q = (int)(std::upper_bound(pt.begin(), pt.end(), t) - pt.begin()) - 1;
            return q >= 0 ? pv[q] : 0;
        };
        auto lvl = [&](double tt) {
            double x = tt - on;
            x = 0.0 > x ? 0.0 : x;
            double dc = su + (1.0 - su) * ((1.0 - af) * exp(-lr * x) + af * exp(-lra * x));
            return vdb + 20.0 * log10(1e-12 > dc ? 1e-12 : dc);
        };
        long long ne = b1 - b0 + 1;
        std::vector<double> edges(ne > 0 ? ne : 0), dc(edges.size(), 0.0);
        for (long long q = 0; q < ne; q++)
            edges[q] = (double)((b0 + q) * blk) / SR;
        double acc = 0.0;
        for (long long q = 0; q + 1 < ne; q++) {
            double c = nv_damper_contact(pedal_at(edges[q]), key, 128);
            if (c >= 1.0) {
                for (long long z = q; z < ne; z++)
                    dc[z] = acc;
                break;
            }
            if (c > 0.0) {
                bool over = lvl(edges[q]) - acc > threshold_db(c, knee_db);
                double r_ = full_db_s * c;
                acc += (over ? r_ : r_ * residual) * (edges[q + 1] - edges[q]);
            }
            dc[q + 1] = acc;
        }
        Track T;
        T.r0 = r0; T.r1 = r1; T.b0 = b0; T.f0 = f0;
        T.dc.assign(dc.begin(), dc.end());
        tracks.push_back(T);
    }
    // ...ONTO THE ROWS (onto_tracks): a note's own rows take its track, but a
    // burst no damper can reach (fast_rows); the register's take none
    if (!tracks.empty()) {
        std::vector<int> t_of(P, -1);
        std::vector<char> usedt(tracks.size(), 0);
        for (long long r = 0; r < nnote; r++) {
            const double *R = rows + NCOLS * r;
            // fast_rows, on prepare's final columns (FINAL_DTYPES: logr, sus, aft float32;
            // numpy 1.26 takes a Python scalar at the array's type, so in float32)
            float lr32 = (float)R[C_logr];
            bool fast = (float)R[C_sus] <= 0 && (float)R[C_aft] <= 0
                        && (float)(lr32 * (float)blk) > (float)(xdec_nepers * SR) && R[C_gr] < 0;
            if (fast)
                continue;
            long long lo = 0, hi = (long long)tracks.size();
            while (lo < hi) {                       /* searchsorted(r0, r, 'right') - 1 */
                long long mid = (lo + hi) / 2;
                if (tracks[mid].r0 <= r)
                    lo = mid + 1;
                else
                    hi = mid;
            }
            long long t = lo - 1;
            if (t >= 0 && r < tracks[t].r1) {
                t_of[r] = (int)t;
                usedt[t] = 1;
            }
        }
        std::vector<int> loc(tracks.size(), -1);
        std::vector<long long> used;
        for (size_t t = 0; t < tracks.size(); t++)
            if (usedt[t]) {
                loc[t] = (int)used.size();
                used.push_back((long long)t);
            }
        if (!used.empty()) {
            int32_t *dk = (int32_t *)malloc(sizeof(int32_t) * (P > 0 ? P : 1));
            float *dg = (float *)malloc(sizeof(float) * (P > 0 ? P : 1));
            for (long long r = 0; r < P; r++) {
                dk[r] = -1;
                dg[r] = 0.0f;
                if (r < nnote && t_of[r] >= 0) {
                    const Track &T = tracks[t_of[r]];
                    double nf = (double)(float)rows[NCOLS * r + C_nf];     /* prepare's nf: float32 */
                    double x = (nf > 1e-6 ? nf : 1e-6) / (T.f0 > 1e-6 ? T.f0 : 1e-6);
                    dk[r] = loc[t_of[r]];
                    dg[r] = (float)(ln10_20 * pow(x, beta));
                }
            }
            long long ndm = 0;
            for (long long u : used)
                ndm += (long long)tracks[u].dc.size();
            float *DM = (float *)malloc(sizeof(float) * (ndm > 0 ? ndm : 1));
            int64_t *DMO = (int64_t *)malloc(sizeof(int64_t) * used.size());
            int64_t *DMB = (int64_t *)malloc(sizeof(int64_t) * used.size());
            int64_t *DMN = (int64_t *)malloc(sizeof(int64_t) * used.size());
            long long o = 0;
            for (size_t q = 0; q < used.size(); q++) {
                const Track &T = tracks[used[q]];
                memcpy(DM + o, T.dc.data(), sizeof(float) * T.dc.size());
                DMO[q] = o;
                DMB[q] = T.b0;
                DMN[q] = (int64_t)T.dc.size();
                o += (long long)T.dc.size();
            }
            dm[0] = dk; dm[1] = dg; dm[2] = DM; dm[3] = DMO; dm[4] = DMB; dm[5] = DMN;
            out[40] = (double)used.size();      /* the tracks used, and DM's length */
            out[41] = (double)(ndm > 0 ? ndm : 1);
            if (!ndm)
                out[41] = 0.0;
        }
    }
    for (int i = 0; i < 9; i++) {
        double d = qacc[2 * i], r = qacc[2 * i + 1];
        out[4 + 3 * i] = tmpl->room_bands[i];
        out[4 + 3 * i + 1] = r > 0.0 ? d / r : 1.0;
        out[4 + 3 * i + 2] = d;
    }
    return P;
}

}  // extern "C"
