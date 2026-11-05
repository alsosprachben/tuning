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
#include <map>
#include <vector>

#include "nv.h"
#include "pycompat.h"

extern "C" {

long long nv_play_full(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr,
                       PyRandom *rs, double **rowsp, double *qacc, double *azimuth, const int *kind,
                       double scale, double full_db_s, double residual, double beta, long long blk,
                       long long *nnote, int *played_out, long long *row0_out, int *bands, double *offs,
                       int with_register, long long *nsym);

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

// mf104.bessel_i: I_n(x) by its series, summed as Python's sum() sums floats
static double mf_bessel_i(int n, double x)
{
    double t[12];
    for (int m = 0; m < 12; m++) {
        double f = 1.0;                 /* factorial(m) * factorial(m + n), exact */
        long long a = 1, b = 1;
        for (int q = 2; q <= m; q++)
            a *= q;
        for (int q = 2; q <= m + n; q++)
            b *= q;
        f = (double)(a * b);
        t[m] = pow(x / 2.0, (double)(2 * m + n)) / f;
    }
    return pysum(t, 12);
}

// mf104.delay_samples: the line's mean delay, whole grid points
static long long mf_delay(const MoogLayer *L, double sr)
{
    double mean = L->mf[0] * mf_bessel_i(0, L->mf[6] * log(2.0));
    long long g = (long long)L->mf_grid;
    long long d = (long long)nearbyint(mean * sr / L->mf_grid) * g;
    return d > g ? d : g;
}

// THE MF-104M's REPEATS (blockrender._prep_delays, mf104.expand): each pedal
// note's rows copied k delays late while the repeat stays over REPEAT_FLOOR
// of the note's loudest -- the line's filter at the partial's own pitch, the
// note's vibrato carried or the line's LFO as one, the FM's anchor moved --
// appended after the table, its dry rows then scaled by the pedal's dry. The
// rows as the table holds them (kind: 1 float32, 2 int32). Returns the
// latest sample a repeat may sound to (0 none), or -1 a note whose rows
// have damper tracks (the C's do not copy them).
static long long mf104_expand(void *song, double **rowsp, long long *Pp, const int *kind, double sr)
{
    enum { cOM = 0, cP0 = 1, cP0R = 2, cAL = 3, cAR = 4, cAM = 5, cNON = 12, cNOFF = 13, cRE = 15, cVD = 33, cVR = 34,
           cVP = 35, cVDL = 36, cFMW = 46, cNFR = 47, cFMP = 48, cFMPR = 49 };
    int nm = nv_song_mf104(song, -1, nullptr, nullptr, nullptr);
    if (nm <= 0)
        return 0;
    auto cast = [&](double *r) {
        for (int c = 0; c < NCOLS; c++)
            if (kind[c] == 1)
                r[c] = (double)(float)r[c];
            else if (kind[c] == 2)
                r[c] = (double)(int32_t)r[c];
    };
    const double TPI = 2.0 * M_PI;
    std::vector<double> extra;
    long long last = 0;
    for (int q = 0; q < nm; q++) {
        long long i0, i1;
        const MoogLayer *L;
        nv_song_mf104(song, q, &i0, &i1, &L);
        double *rows = *rowsp;
        std::vector<double> lv;
        double top = 0.0;
        for (long long i = i0; i < i1; i++) {
            double l = std::max(fabs(rows[NCOLS * i + cAL]), fabs(rows[NCOLS * i + cAR]));
            lv.push_back(l);
            top = i == i0 ? l : std::max(top, l);       /* max(lv) */
        }
        const double time = L->mf[0], fc = L->mf[1], fb = L->mf[2], wet = L->mf[3], dry = L->mf[4],
                     rate = L->mf[5], amount = L->mf[6];
        const long long d0 = mf_delay(L, sr);
        for (long long i = i0; i < i1; i++) {
            const double *row = *rowsp + NCOLS * i;
            double om = row[cOM];
            double rel = top > 0.0 ? lv[i - i0] / top : 0.0;
            /* mf104.repeats at the partial's own pitch */
            double fhz = om * sr / (2.0 * M_PI);
            double x = fabs(fhz) / fc;
            double h = pow(1.0 + x * x, -L->mf_poles / 2.0);
            for (int k = 1; k <= (int)L->mf_max; k++) {
                double g = wet * pow(fb, (double)(k - 1)) * pow(h, (double)k);
                if (g * rel < L->mf_floor)
                    break;
                long long d = (long long)k * d0;
                std::vector<double> c(row, row + NCOLS);
                c[cNON] = row[cNON] + (double)d;
                c[cNOFF] = row[cNOFF] + (double)d;
                c[cNFR] = c[cNON] - floor(c[cNON]);
                c[cP0] = row[cP0] - om * (double)d;
                c[cP0R] = row[cP0R] - om * (double)d;
                if (row[cFMW] != 0.0) {
                    c[cFMP] = row[cFMP] - row[cFMW] * (double)d;
                    c[cFMPR] = row[cFMPR] - row[cFMW] * (double)d;
                }
                if (row[cVD] != 0.0)            /* the note's own vibrato, delayed */
                    c[cVP] = row[cVP] - TPI * row[cVR] * (double)d / sr;
                if (amount > 0.0) {             /* ...or the line's (mf104.lfo_vibrato), in its place */
                    double w = 2.0 * M_PI * rate;
                    double tau = (double)d0 / sr;
                    double sre = 0.0, sim = 0.0;
                    for (int j = 0; j < k; j++) {
                        sre = sre + cos(w * (double)j * tau);
                        sim = sim + -sin(w * (double)j * tau);
                    }
                    double dlt = time * 2.0 * mf_bessel_i(1, amount * log(2.0)) * hypot(sre, sim);
                    double th = atan2(sim, sre);
                    double f = om * sr / (2.0 * M_PI);
                    double t_on = c[cNON] / sr;
                    c[cVD] = w * dlt;
                    c[cVR] = rate;
                    c[cVP] = th - M_PI / 2.0;
                    c[cVDL] = 0.0;
                    double dp = -2.0 * M_PI * f * dlt * sin(w * t_on + th);
                    c[cP0] = c[cP0] + dp;
                    c[cP0R] = c[cP0R] + dp;
                }
                c[cAL] = row[cAL] * g;
                c[cAR] = row[cAR] * g;
                c[cAM] = row[cAM] * g;
                cast(c.data());
                extra.insert(extra.end(), c.begin(), c.end());
                long long e = (long long)c[cNOFF] + (long long)ceil(row[cRE]);
                last = std::max(last, e);
            }
            double *rw = *rowsp + NCOLS * i;
            for (int cc : {cAL, cAR, cAM})
                rw[cc] = rw[cc] * dry;
            cast(rw);
        }
    }
    long long m = (long long)extra.size() / NCOLS;
    if (m) {
        double *nr = (double *)realloc(*rowsp, sizeof(double) * NCOLS * (size_t)(*Pp + m));
        if (!nr)
            return -2;
        memcpy(nr + NCOLS * (size_t)*Pp, extra.data(), sizeof(double) * extra.size());
        *rowsp = nr;
        *Pp += m;
    }
    return last;
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
    nv_song_gliss(song, K);                 // the valved glisses walked (_prep_gliss), before the notes are counted
    long long nnote = 0, nsym = 0;
    int nn = nv_song_n_notes(song);
    std::vector<int> played(nn), bands(nn);
    std::vector<long long> row0(nn);
    std::vector<double> offs(nn);
    long long P = nv_play_full(song, K, tmpl, br, nbr, rs, rowsp, qacc, azimuth, kind, scale, full_db_s, residual,
                               beta, blk, &nnote, played.data(), row0.data(), bands.data(), offs.data(),
                               with_register, &nsym);
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
    // A REED ORGAN'S TREMOLO STOP'S ROWS (_HT_ROWS): each note struck with it
    // drawn, from its first row to the next note's
    for (int j = 0; j < nn; j++)
        if (nv_song_htrem(song, played[j])) {
            long long r1 = j + 1 < nn ? row0[j + 1] : nnote;
            nv_song_add_htrem_rows(song, row0[j], r1);
        }
    // THE VALVE AMPLIFIERS (_AMP_CH) and THE ROTATING SPEAKERS (_LESLIE_CH):
    // each channel as its first note through one is played
    for (int j = 0; j < nn; j++) {
        long long ch;
        int iv[4];
        double dv[2];
        nv_song_get_note(song, played[j], &ch, iv, dv);
        const NoteClass *k = (iv[2] < 0 || iv[2] > 127) ? nullptr : K[(iv[3] ? NV_K_DRUMS : 0) + 128 * iv[2] + iv[0]];
        const long long part = ch;
        ch = nv_song_mix(song, played[j]);              // (each tone its own: TONE_SEG)
        if (k && k->amp_drive != 0.0) {
            // (_note_amp_drive: the reference times the note's fader, chan_vol)
            double ref = 0.0, pl[6];
            if (k->amp_reference != 0.0 && nv_song_pitch_level(song, played[j], k->init.effort_tilt != 0.0, pl))
                ref = k->amp_reference * pl[3];
            nv_song_add_amp(song, ch, k->amp_drive, k->leslie != 0, ref, k->amp_imbalance);
        }
        if (k && k->leslie)
            nv_song_add_leslie(song, ch, k->leslie);
        if (k && k->cab_set)                            // (_CAB_CH: the channel's, set once)
            nv_song_add_cab(song, ch, k);
        if (k && k->clav_panel) {                       // (_CLAV_CH: the part's first CC1, the rockers swept)
            int v;
            if (nv_song_first_cc(song, part, 1, &v)) {
                int set = (int)nearbyint(v / 127.0 * 4.0);      // (round: half to even)
                if (set != 2)                           // (CLAV_FLAT: all four up, nothing)
                    nv_song_add_clav(song, ch, set);
            }
        }
        if (k && !k->organ && k->trem_depth > 0.0) {    // (_note_tremolo: the channel's, set once)
            int v;
            double dep = k->trem_intrinsic ? k->trem_depth
                                           : k->trem_depth * (nv_song_first_cc(song, part, 1, &v) ? v / 127.0 : 0.0);
            if (dep > 0.0) {
                double cfg[4] = {k->trem_hz, dep, (double)k->trem_stereo, k->trem_scatter};
                nv_song_add_trem(song, ch, cfg);
            }
        }
    }
    out[40] = 0.0;
    out[41] = 0.0;
    const double sr = tmpl->sr;
    long long srl = (long long)sr;
    long long N = (long long)(total * sr) + srl;
    long long nblk = N / blk + 2;
    // THE MF-104M's REPEATS, before the length (_prep_delays): the render
    // grows to hold the last one's release (nblk stays: the kernel clamps)
    for (int j = 0; j < nn; j++)                        // (a pedal note's damper track: Python's)
        if (bands[j]) {
            long long r0 = row0[j], r1 = j + 1 < nn ? row0[j + 1] : nnote;
            long long a, b;
            const MoogLayer *L;
            for (int q = 0; nv_song_mf104(song, q, &a, &b, &L); q++)
                if (a < r1 && b > r0)
                    return -(1 + played[j]);
        }
    long long mlast = mf104_expand(song, rowsp, &P, kind, sr);
    if (mlast < -1)
        return NV_TOO_SMALL;
    if (mlast > 0 && mlast + srl / 2 > N)
        N = mlast + srl / 2;
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
    out[42] = (double)(nnote + nsym);                   /* ...and the sympathetic strings' */
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

// cabinet.Cabinet.gain: FormantBody.bore_gain at hz (no less than 1e-6 Hz)
// over the cabinet's level at its reference
static double cab_gain(const NoteClass *k, double hz);

// cabinet.gain at hz, for live's valve products
extern "C" double nv_cab_gain(const NoteClass *k, double hz)
{
    return cab_gain(k, hz);
}

static double cab_gain(const NoteClass *k, double hz)
{
    hz = hz > 1e-6 ? hz : 1e-6;
    double g = k->cab_floor;
    for (int i = 0; i < k->n_cab_fm; i++) {
        double d = (hz - k->cab_fm[i][0]) / (k->cab_fm[i][1] * 0.5);
        g += k->cab_fm[i][2] / (1.0 + d * d);
    }
    for (int i = 0; i < k->n_cab_afm; i++) {
        double d = (hz - k->cab_afm[i][0]) / (k->cab_afm[i][1] * 0.5);
        g *= 1.0 - k->cab_afm[i][2] / (1.0 + d * d);
    }
    g /= 1.0 + pow(hz / k->cab_corner, k->cab_order);
    if (k->cab_cut != 0.0) {
        double x = pow(hz / k->cab_cut, k->cab_bell);
        g *= x / (1.0 + x);
    }
    return g / k->cab_ref;
}

// THE SPEAKER CABINETS (blockrender._prep_cabinet, cabinet.expand): every row
// on a cabinet's channel (the song's: nv_song_cabs) through its response at
// the row's frequency -- the file's after the amplifier, before the rotors;
// a live template's as it is built (the speaker is linear: each note through
// it, summed, is the sum through it)
// THE CLAVINET's TONE ROCKERS (_prep_clav_rockers, tonelib.clav_tone_gain):
// every row on the channel through the rocker's filter at its frequency --
// CLAV_TONE's (corner, order, high-pass), darkest to brightest
extern "C" void nv_clav_pass(void *song, double *rows, long long P)
{
    enum { cAL = 3, cAR = 4, cAM = 5, cMCH = 6, cNF = 11 };     // (EMIT_COLS)
    static const double tone[5][3] = {{1200.0, 2.0, 0.0}, {3000.0, 2.0, 0.0}, {0.0, 0.0, 0.0},
                                      {400.0, 2.0, 1.0}, {900.0, 2.0, 1.0}};
    int nc = nv_song_clavs(song, nullptr, nullptr, 0);
    if (!nc)
        return;
    std::vector<long long> cch(nc);
    std::vector<int> cset(nc);
    nv_song_clavs(song, cch.data(), cset.data(), nc);
    std::map<long long, int> clav;
    for (int k = 0; k < nc; k++)
        clav[cch[k]] = cset[k];
    for (long long r = 0; r < P; r++) {
        double *row = rows + (size_t)NCOLS * r;
        auto it = clav.find((long long)row[cMCH]);
        if (it == clav.end())
            continue;
        const double *t = tone[((it->second % 5) + 5) % 5];
        if (t[0] <= 0.0)
            continue;
        double y = row[cNF] / t[0];
        double x = t[1] == 2.0 ? y * y : pow(y, t[1]);  // (numpy's x ** 2.0 is its square)
        double g = t[2] != 0.0 ? x / (1.0 + x) : 1.0 / (1.0 + x);
        row[cAL] *= g;
        row[cAR] *= g;
        row[cAM] *= g;
    }
}

extern "C" void nv_cabinet_pass(void *song, double *rows, long long P)
{
    enum { cAL = 3, cAR = 4, cAM = 5, cMCH = 6, cNF = 11 };     // (EMIT_COLS)
    int nc = nv_song_cabs(song, nullptr, nullptr, 0);
    if (!nc)
        return;
    std::vector<long long> cch(nc);
    std::vector<const NoteClass *> cks(nc);
    nv_song_cabs(song, cch.data(), cks.data(), nc);
    std::map<long long, const NoteClass *> cab;
    for (int k = 0; k < nc; k++)
        cab[cch[k]] = cks[k];
    for (long long r = 0; r < P; r++) {
        double *row = rows + (size_t)NCOLS * r;
        auto it = cab.find((long long)row[cMCH]);
        if (it == cab.end())
            continue;
        double g = cab_gain(it->second, row[cNF]);
        row[cAL] *= g;
        row[cAR] *= g;
        row[cAM] *= g;
    }
}
