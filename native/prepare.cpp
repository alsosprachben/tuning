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

extern "C" long long nv_play_own_end(int j, long long dflt);
extern "C" const void *nv_play_get_sink(void);
extern "C" void nv_stream_refuse(const char *why);
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

// ...for the streaming render, note by note (a maximum: the whole table's
// is the greatest of its notes')
extern "C" long long nv_ring_last(const double *rows, long long n, double floor_, double sr)
{
    return ring_last(rows, n, floor_, sr);
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

extern "C" int nv_song_moog_dup(void *s, int fx, long long d);     // (channel.cpp: a repeat's own filter row)

// THE MF-104M's REPEATS (blockrender._prep_delays, mf104.expand): each pedal
// note's rows copied k delays late while the repeat stays over REPEAT_FLOOR
// of the note's loudest -- the line's filter at the partial's own pitch, the
// note's vibrato carried or the line's LFO as one, the FM's anchor moved --
// appended after the table, its dry rows then scaled by the pedal's dry. The
// rows as the table holds them (kind: 1 float32, 2 int32). Returns the
// latest sample a repeat may sound to (0 none), or -1 a note whose rows
// have damper tracks (the C's do not copy them).
// ONE LAYER's repeats (rows [i0, i1) of rows, in the table's numbering, cast):
// appended to extra, its dry rows scaled in place; the latest sample in last
static void mf_layer(void *song, const MoogLayer *L, double *rows, long long i0, long long i1, const int *kind,
                     double sr, std::vector<double> &extra, long long &last)
{
    enum { cOM = 0, cP0 = 1, cP0R = 2, cAL = 3, cAR = 4, cAM = 5, cNON = 12, cNOFF = 13, cRE = 15, cVD = 33, cVR = 34,
           cVP = 35, cVDL = 36, cFX = 43, cFMW = 46, cNFR = 47, cFMP = 48, cFMPR = 49 };
    auto cast = [&](double *r) {
        for (int c = 0; c < NCOLS; c++)
            if (kind[c] == 1)
                r[c] = (double)(float)r[c];
            else if (kind[c] == 2)
                r[c] = (double)(int32_t)r[c];
    };
    const double TPI = 2.0 * M_PI;
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
        const double *row = rows + NCOLS * i;
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
            if ((int)row[cFX] >= 0) {       /* a note whose pitch or shape rows move: its own row, D later */
                int nf = nv_song_moog_dup(song, (int)row[cFX], d);
                if (nf >= 0)
                    c[cFX] = (double)nf;
            }
            cast(c.data());
            extra.insert(extra.end(), c.begin(), c.end());
            long long e = (long long)c[cNOFF] + (long long)ceil(row[cRE]);
            last = std::max(last, e);
        }
        double *rw = rows + NCOLS * i;
        for (int cc : {cAL, cAR, cAM})
            rw[cc] = rw[cc] * dry;
        cast(rw);
    }
}

static long long mf104_expand(void *song, double **rowsp, long long *Pp, const int *kind, double sr)
{
    int nm = nv_song_mf104(song, -1, nullptr, nullptr, nullptr);
    if (nm <= 0)
        return 0;
    std::vector<double> extra;
    long long last = 0;
    for (int q = 0; q < nm; q++) {
        long long i0, i1;
        const MoogLayer *L;
        nv_song_mf104(song, q, &i0, &i1, &L);
        mf_layer(song, L, *rowsp, i0, i1, kind, sr, extra, last);
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

// A STREAM's MF-104M: each note's layers as it lands (rows [i0, i1) at R, cast,
// in the table's numbering) -- its dry rows scaled in place, its repeats into
// *out (malloc'd, NCOLS each; NULL none), the latest sample in *last. The
// layers registered as the play goes (nv_song_add_mf104), walked in order.
struct MfCursor {
    void *song;
    const int *kind;
    double sr;
    int next = 0;
};
extern "C" void *nv_mf104_new(void *song, const int *kind, double sr)
{
    MfCursor *c = new MfCursor;
    c->song = song;
    c->kind = kind;
    c->sr = sr;
    return c;
}
extern "C" long nv_mf104_note(void *h, double *R, long long i0, long long i1, double **out, long long *last)
{
    MfCursor &c = *(MfCursor *)h;
    std::vector<double> ex;
    long long l = 0, a, b;
    const MoogLayer *L;
    while (nv_song_mf104(c.song, c.next, &a, &b, &L) && a < i1) {
        if (a >= i0 && b <= i1)
            mf_layer(c.song, L, R - NCOLS * i0, a, b, c.kind, c.sr, ex, l);
        c.next++;
    }
    *last = l;
    *out = nullptr;
    if (ex.empty())
        return 0;
    *out = (double *)malloc(sizeof(double) * ex.size());
    memcpy(*out, ex.data(), sizeof(double) * ex.size());
    return (long)(ex.size() / NCOLS);
}
extern "C" void nv_mf104_free(void *h) { delete (MfCursor *)h; }

// THE GS DELAY's REPEATS (blockrender._prep_delays, gsdelay.expand), after
// the MF-104M's: each delayed note's rows (row0[j] to the next note's, a
// tone's own insertion effect's 'dly'), each tap's repeats a period apart
// while over REPEAT_FLOOR of the note's loudest partial -- its line's filter
// on the first, placed at the tap's output (nv_gsd_place), the note's
// vibrato and FM carried -- appended as the table holds them. Returns the
// latest sample a repeat may sound to (0 none), -2 out of memory.
struct GsdCtx {
    const NoteClass *const *K = nullptr;
    void *song = nullptr;
    const int *kind = nullptr;
    double sr = 0.0;
    const double *gdev = nullptr, *gplace = nullptr;
    std::map<long long, std::pair<std::vector<double>, std::vector<int>>> c94;
};
// ONE NOTE's repeats (j its place in the play, ni the song's note): its rows
// [n0, i1all) at R (cast), its own to iown -- appended to extra, the latest
// sample a repeat may sound to in last; probe: 1 where it has any, none made
static int gsd_note(GsdCtx &X, int j, int ni, const double *R, long long n0, long long iown, long long i1all,
                    std::vector<double> &extra, long long &last, bool probe = false)
{
    (void)j;
    const NoteClass *const *K = X.K;
    void *song = X.song;
    const int *kind = X.kind;
    const double sr = X.sr;
    const double *gdev = X.gdev, *gplace = X.gplace;
    auto &c94 = X.c94;
    enum { cOM = 0, cP0 = 1, cP0R = 2, cAL = 3, cAR = 4, cAM = 5, cNF = 11, cNON = 12, cNOFF = 13, cRE = 15, cVD = 33,
           cVR = 34, cVP = 35, cDL = 37, cDR = 38, cFMW = 46, cNFR = 47, cFMP = 48, cFMPR = 49 };
    const double FLOOR = pow(10.0, -60.0 / 20.0), TPI = 2.0 * M_PI;
    auto cast = [&](double *r) {
        for (int c = 0; c < NCOLS; c++)
            if (kind[c] == 1)
                r[c] = (double)(float)r[c];
            else if (kind[c] == 2)
                r[c] = (double)(int32_t)r[c];
    };
    {
        long long ch;
        int iv[4];
        double dv[2];
        nv_song_get_note(song, ni, &ch, iv, dv);
        const NoteClass *k = (iv[2] < 0 || (iv[2] > 127 && !iv[3])) ? nullptr : K[nv_song_kidx(song, ni)];
        const NoteClass *kk = K[nv_song_kidx(song, ni)];
        const double *D = nullptr, *place = nullptr, *pans = nullptr;
        double send = 1.0;
        int tw = 4;                         // (a tap's doubles: time, level, output, period[, shift])
        bool cross = false;                 // (ping-pong: each odd repeat from the other side)
        const double *mod = nullptr;        // (a Mod Delay's LFO: rate, swing, the right's phase)
        const double *fc = nullptr;
        std::vector<double> km;             // (a Keyboard Multi's taps, unrolled)
        const int fx = nv_song_note_fx(song, ni, &fc);
        if (fx == -1 && k && k->efx_set && k->efx_dly && !iv[3] && !nv_moog_neutral()) {
            D = k->dly_p;                   // (a tone's own insertion delay, in the GS delay's place)
            place = k->efx_place;
        } else if (fx >= 0 && fc[34] == 3.0) {
            // ...a KEYBOARD MULTI's (gsefx._keyboard_multi): every path through
            // its ring modulator (dry, either sideband at half), pitch shifter
            // (dry, shifted) and delay (direct, each repeat) one tap of (delay,
            // level, the centre, period, ratio, Hz) against the all-dry path,
            // feedback none (the repeats are taps)
            const double fm = fc[161], rd = fc[162], rw = fc[163], pd = fc[164], pw = fc[165], ra = fc[166];
            const double base = fc[167];
            std::vector<std::pair<double, double>> reps = {{0.0, 1.0}};
            if (fc[160] != 0.0) {
                const double t = fc[38], dfb = fc[36];
                for (int q = 0; q < 64; q++) {
                    double l = fc[35] * pow(dfb, (double)q);
                    if (l < 1e-3)
                        break;
                    reps.push_back(std::make_pair((q + 1) * t, l));
                }
            }
            const double rm[3][2] = {{rd, 0.0}, {0.5 * rw, fm}, {0.5 * rw, -fm}};
            const double ps[2][2] = {{pd, 1.0}, {pw, ra}};
            km.assign(5, 0.0);
            km[0] = 1.0;
            km[3] = std::max(1e-3, reps.back().first);
            for (const auto &a : rm)
                for (const auto &b : ps)
                    for (const auto &rp : reps) {
                        if (a[1] == 0.0 && b[1] == 1.0 && rp.first == 0.0)
                            continue;       // (the part itself)
                        double l = a[0] * b[0] * rp.second / base;
                        if (l > 1e-4) {
                            const double tp[6] = {rp.first, l, 2.0, rp.first, b[1], a[1] * b[1]};
                            km.insert(km.end(), tp, tp + 6);
                        }
                    }
            km[4] = (double)((km.size() - 5) / 6);
            D = km.data();
            place = nv_song_fx_place_of(song, &pans);
            tw = 6;
        } else if (fx >= 0 && fc[34] != 0.0) {
            // ...the file's chain's own delay (a pitch shifter's, a delay
            // type's: its wide form at fc + 96, a cross-feedback beside it),
            // sent whole in the GS delay's place: its taps 5 each, a shift with them
            D = fc[34] == 2.0 ? fc + 96 : fc + 35;
            cross = fc[34] == 2.0 && fc[121] != 0.0;
            mod = fc[34] == 2.0 && fc[122] != 0.0 ? fc + 122 : nullptr;
            place = nv_song_fx_place_of(song, &pans);
            tw = 5;
        } else if (fx >= 0) {
            // ...the file's chain: its own send to the GS delay (40 03 19)
            send = fc[13] / 127.0;
            if (gdev && send > 0.0) {
                D = gdev;
                place = gplace;
            }
        } else if (gdev && !(fx == -1 && kk && kk->efx_set && !iv[3] && !nv_moog_neutral())) {
            // ...else the file's GS delay, at the part's CC94 at the onset
            // (_gsd_send: the last at or before it), a drum key's level 127
            auto it = c94.find(ch);
            if (it == c94.end()) {
                int n = nv_song_ccs(song, ch, 94, nullptr, nullptr, 0);
                std::vector<double> tt(n > 0 ? n : 0);
                std::vector<int> vv(n > 0 ? n : 0);
                if (n > 0)
                    nv_song_ccs(song, ch, 94, tt.data(), vv.data(), n);
                it = c94.emplace(ch, std::make_pair(tt, vv)).first;
            }
            int v = 0;
            for (size_t q = 0; q < it->second.first.size(); q++) {
                if (it->second.first[q] > dv[0] + 1e-9)
                    break;
                v = it->second.second[q];
            }
            int ed[9];          // (a drum key's own delay level: _dst's, else 127)
            int dlv = iv[3] && (nv_song_dst(song, ch, iv[0], dv[0], ed) & 32) ? ed[5] : 127;
            send = v / 127.0 * (iv[3] ? dlv / 127.0 : 1.0);
            if (send > 0.0) {
                D = gdev;
                place = gplace;
            }
        }
        // ...A PARALLEL TYPE's COPY (branch B's rows, after the note's own:
        // _par_close): B's own delay, else the GS delay the note was sent to
        // (not A's own), its repeats after the note's
        const double *D2 = nullptr, *place2 = nullptr, *pans2 = nullptr, *mod2 = nullptr;
        double send2 = 1.0;
        int tw2 = 4;
        bool cross2 = false;
        if (fx >= 0 && fc[208] != 0.0 && iown < i1all) {
            const double *fb_ = fc - NV_FXN;       // (branch B's record: before A's)
            if (fb_[34] != 0.0) {
                D2 = fb_[34] == 2.0 ? fb_ + 96 : fb_ + 35;
                cross2 = fb_[34] == 2.0 && fb_[121] != 0.0;
                mod2 = fb_[34] == 2.0 && fb_[122] != 0.0 ? fb_ + 122 : nullptr;
                place2 = nv_song_fx_place_of(song, &pans2);
                tw2 = 5;
            } else if (fc[34] == 0.0 && D && D == gdev) {
                D2 = gdev;
                place2 = gplace;
                send2 = send;
            }
        }
        if (probe && (D || D2))
            return 1;
        for (int seg = 0; seg < 2; seg++) {
        if (seg == 1) {
            D = D2;
            place = place2;
            pans = pans2;
            send = send2;
            tw = tw2;
            cross = cross2;
            mod = mod2;
        }
        long long i0 = seg ? iown : n0, i1 = seg ? i1all : iown;
        if (!D || i1 <= i0)
            continue;
        const double level = D[0], fb = D[1], lpf = D[2], tc = D[3];
        const int ntap = (int)D[4];
        (void)tc;
        const double *rows = R - NCOLS * n0;     // (the table's numbering: rows[NCOLS * i])
        std::vector<double> lv;
        double top = 0.0;
        for (long long i = i0; i < i1; i++) {
            double l = std::max(fabs(rows[NCOLS * i + cAL]), fabs(rows[NCOLS * i + cAR]));
            lv.push_back(l);
            top = i == i0 ? l : std::max(top, l);       /* max(lv) */
        }
        for (long long i = i0; i < i1; i++) {
            const double *row = rows + NCOLS * i;
            double om = row[cOM];
            double f = om * sr / TPI;
            double rel = top > 0.0 ? lv[i - i0] / top : 0.0;
            double lg = lpf != 0.0 ? 1.0 / sqrt(1.0 + pow(f / lpf, 2.0)) : 1.0;     /* (lpf_gain) */
            double g0 = send * level * lg;
            if (g0 <= 0.0)
                continue;
            for (int t = 0; t < ntap; t++) {
                const double tau = D[5 + tw * t], tl = D[6 + tw * t], period = D[8 + tw * t];
                const double shr = tw > 4 ? D[9 + tw * t] : 1.0;
                const int side = (int)D[7 + tw * t];
                for (int q = 0; q < 64; q++) {
                    double g = g0 * tl * (q ? pow(fb, (double)q) : 1.0);
                    if (fabs(g) * rel < FLOOR || (q && fb == 0.0))
                        break;
                    long long d = (long long)nearbyint((tau + q * period) * sr);
                    // (a pitch shifter's: each repeat by its ratio once more, k + 1 times)
                    double sh = tw > 4 ? pow(shr, (double)(q + 1)) : 1.0;
                    // ...and a RING MODULATOR's (a Keyboard Multi's) by Hz besides:
                    // the copy at f * ratio + Hz, a lower sideband below 0 Hz
                    // folded back up, its phase turned
                    const double add = tw > 5 ? D[10 + tw * t] : 0.0;
                    bool flip = false;
                    if (tw > 5) {
                        if (f * sh + add == 0.0)
                            continue;
                        flip = f * sh + add < 0.0;
                        sh = fabs(f * sh + add) / f;
                    }
                    double pl[4];
                    const int sd = cross && (q % 2) && side <= 1 ? 1 - side : side;     // ('l' <-> 'r')
                    if (sd >= 300) {            // (a 3D type's side past the speakers: its angle)
                        const double *A5 = pans + NV_EFX_PANS_TO_DEG + 5 * (sd - 300);
                        nv_gsd_place4k(A5[0], f * sh, place[0], A5 + 1, pl);
                    } else if (sd >= 100) {     // (a tap at a pan between the outputs)
                        nv_gsd_place4(sd, f * sh, place[0], pans + 4 * (sd - 100), pl);
                    } else {
                        nv_gsd_place(sd, f * sh, place, pl);
                    }
                    std::vector<double> c(row, row + NCOLS);
                    c[cNON] = row[cNON] + (double)d;
                    c[cNOFF] = row[cNOFF] + (double)d;
                    c[cNFR] = c[cNON] - floor(c[cNON]);
                    c[cDL] = pl[2];
                    c[cDR] = pl[3];
                    const double om2 = om * sh;     // (a shifter's repeat at its own pitch)
                    if (sh != 1.0) {
                        c[cOM] = om2;
                        c[cNF] = row[cNF] * sh;
                    }
                    c[cP0] = -om2 * (c[cNON] + pl[2]) + (row[cP0] + om * (row[cNON] + row[cDL]));
                    c[cP0R] = -om2 * (c[cNON] + pl[3]) + (row[cP0R] + om * (row[cNON] + row[cDR]));
                    if (tw > 5) {
                        // the modulator's own phase where the copy starts (on
                        // the file's clock), and a folded sideband's turn
                        const double mp = TPI * add * c[cNON] / sr;
                        for (int w = 0; w < 2; w++) {
                            const int pk = w ? cP0R : cP0;
                            const double dd = pl[2 + w];
                            double ph0 = c[pk] + om2 * (c[cNON] + dd) + mp;
                            if (flip)
                                ph0 = M_PI - ph0;
                            c[pk] = -om2 * (c[cNON] + dd) + ph0;
                        }
                    }
                    if (row[cFMW] != 0.0) {
                        c[cFMP] = row[cFMP] - row[cFMW] * (double)d;
                        c[cFMPR] = row[cFMPR] - row[cFMW] * (double)d;
                    }
                    if (row[cVD] != 0.0)        /* the note's own vibrato, delayed */
                        c[cVP] = row[cVP] - TPI * row[cVR] * (double)d / sr;
                    double m = fabs(row[cAM]);
                    c[cAL] = m * g * pl[0];
                    c[cAR] = m * g * pl[1];
                    c[cAM] = row[cAM] * g;
                    if (mod) {
                        // AN INSERTION DELAY's MODULATION (Mod Delay): the line's
                        // LFO on the copy, free-running, the right output's at
                        // its phase (a ping-pong's: the side it answers from)
                        c[cVD] = std::min(0.5, 2.0 * M_PI * mod[0] * mod[1]);
                        c[cVR] = mod[0];
                        double x = TPI * mod[0] * c[cNON] / sr + (sd == 1 ? mod[2] : 0.0);
                        double md = fmod(x, TPI);           // (Python's %: the divisor's sign)
                        if (md != 0.0) {
                            if ((TPI < 0.0) != (md < 0.0))
                                md += TPI;
                        } else {
                            md = copysign(0.0, TPI);
                        }
                        c[cVP] = md;
                    }
                    cast(c.data());
                    extra.insert(extra.end(), c.begin(), c.end());
                    long long e = (long long)c[cNOFF] + (long long)ceil(row[cRE]);
                    last = std::max(last, e);
                }
            }
        }
        }
    }
    return 0;
}

static long long gsd_expand(const NoteClass *const *K, void *song, const int *played, const long long *row0, int nn,
                            long long nnote, double **rowsp, long long *Pp, const int *kind, double sr,
                            bool probe = false)    // (probe: 1 at the first note with a delay, no rows touched)
{
    GsdCtx X;
    X.K = K;
    X.song = song;
    X.kind = kind;
    X.sr = sr;
    X.gdev = nv_song_gs_delay_of(song, &X.gplace);     // (a GS file's: _GS_DLY)
    std::vector<double> extra;
    long long last = 0;
    for (int j = 0; j < nn; j++) {
        const long long i1all = j + 1 < nn ? row0[j + 1] : nnote, iown = nv_play_own_end(j, i1all);
        if (gsd_note(X, j, played[j], *rowsp + NCOLS * row0[j], row0[j], iown, i1all, extra, last, probe))
            return 1;
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

// A STREAM's DELAYS: gsd_note for one note at a time -- its repeats into *out
// (malloc'd, NCOLS each; NULL none), the latest sample in *last
extern "C" void *nv_gsd_new(const NoteClass *const *K, void *song, const int *kind, double sr)
{
    GsdCtx *X = new GsdCtx;
    X->K = K;
    X->song = song;
    X->kind = kind;
    X->sr = sr;
    X->gdev = nv_song_gs_delay_of(song, &X->gplace);
    return X;
}
extern "C" long nv_gsd_note(void *h, int j, int ni, const double *R, long long i0, long long iown, long long i1,
                            double **out, long long *last)
{
    std::vector<double> ex;
    long long l = 0;
    gsd_note(*(GsdCtx *)h, j, ni, R, i0, iown, i1, ex, l);
    *last = l;
    *out = nullptr;
    if (ex.empty())
        return 0;
    *out = (double *)malloc(sizeof(double) * ex.size());
    memcpy(*out, ex.data(), sizeof(double) * ex.size());
    return (long)(ex.size() / NCOLS);
}
extern "C" void nv_gsd_free(void *h) { delete (GsdCtx *)h; }

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

// A NOTE's TRACK (damper.track, _damp_close): from its own rows (nr of them,
// rows its first) -- the one nearest its key's fundamental -- its pedal's
// values, its key-up to where its damper lands; b0, f0 and dc into T. The
// whole render's loop and a stream's (nv_damp_track) alike.
static bool damp_track(void *song, int i, const double *rows, long long nr, double land, double SR, long long blk,
                       long long nblk, double full_db_s, double residual, double knee_db, Track &T)
{
    enum { C_nf = 11, C_non = 12, C_logr = 17, C_logrA = 18, C_aft = 19, C_sus = 20, C_gr = 39 };
    if (nr <= 0)
        return false;
    long long ch;
    int iv[4];
    double dv[2];
    nv_song_get_note(song, i, &ch, iv, dv);
    int key = iv[0], vel = iv[1];
    double on = dv[0], off = dv[1];
    double f0 = 440.0 * pow(2.0, (key - 69) / 12.0);
    long long jb = 0;
    double best = 0.0;
    for (long long r = 0; r < nr; r++) {
        double nf = rows[NCOLS * r + C_nf];
        double v = fabs(log((nf > 1e-3 ? nf : 1e-3) / f0));     /* np.maximum, then |log| */
        if (r == 0 || v < best) {
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

    T.b0 = b0;
    T.f0 = f0;
    T.dc.assign(dc.begin(), dc.end());
    return true;
}

// PASS A's NOTES, kept for its replay: each played note's index, whether
// it meets the half-pedal's band, where its damper lands
static std::vector<int> g_sn_i, g_sn_band;
static std::vector<double> g_sn_land;
extern "C" int nv_stream_note(int j, int *i, int *band, double *land)
{
    if (j < 0 || j >= (int)g_sn_i.size())
        return 0;
    *i = g_sn_i[j];
    *band = g_sn_band[j];
    *land = g_sn_land[j];
    return 1;
}
// ...a stream's track for note i: its own rows; b0, f0, dc (cap floats) out;
// dc's length returned (0 none, -(length) cap too small)
extern "C" long nv_damp_track(void *song, int i, const double *rows, long long nr, double land, double SR,
                              long long blk, long long nblk, double full_db_s, double residual, double knee_db,
                              long long *b0, double *f0, float *dc, long cap)
{
    Track T;
    if (!damp_track(song, i, rows, nr, land, SR, blk, nblk, full_db_s, residual, knee_db, T))
        return 0;
    if ((long)T.dc.size() > cap)
        return -(long)T.dc.size();
    *b0 = T.b0;
    *f0 = T.f0;
    std::copy(T.dc.begin(), T.dc.end(), dc);
    return (long)T.dc.size();
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
    if (nv_song_drones(song, K) < 0)        // ...and the drones (_DRONE_PC), after them
        return -3;
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
    const bool stream = nv_play_get_sink() != nullptr;  // (a stream's play: no table here)
    // THE STROKES' ROWS (stroke_rows): each gesture's stroke's, from its
    // first row to the next note's
    // (a stream's: none -- its strokes are notes, these ranges live's templates' alone)
    for (int j = 0; j < nn && !stream; j++)
        if (nv_song_stroked(song, played[j])) {
            long long r1 = j + 1 < nn ? row0[j + 1] : nnote;
            if (r1 > row0[j])
                nv_song_add_stroke_rows(song, row0[j], r1);
        }
    // A REED ORGAN'S TREMOLO STOP'S ROWS (_HT_ROWS): each note struck with it
    // drawn, from its first row to the next note's
    for (int j = 0; j < nn; j++)
        if (nv_song_htrem(song, played[j])) {
            long long r1 = nv_play_own_end(j, j + 1 < nn ? row0[j + 1] : nnote);     // (its own rows)
            nv_song_add_htrem_rows(song, row0[j], r1, played[j]);
        }
    // THE VALVE AMPLIFIERS (_AMP_CH) and THE ROTATING SPEAKERS (_LESLIE_CH):
    // each channel as its first note through one is played
    for (int j = 0; j < nn; j++) {
        long long ch;
        int iv[4];
        double dv[2];
        nv_song_get_note(song, played[j], &ch, iv, dv);
        const NoteClass *k = (iv[2] < 0 || (iv[2] > 127 && !iv[3])) ? nullptr : K[nv_song_kidx(song, played[j])];
        const long long part = ch;
        ch = nv_song_mix(song, played[j]);              // (each tone its own: TONE_SEG)
        // (a tone's own insertion effect, melodic, where the file puts its
        // part on none -- else the file's chain its onset finds: its level
        // and OD in the note's level; the mix channel's first chain note its
        // amp, its level's steps and its cabinet: _note_insertion_efx)
        const double *fc = nullptr;
        const int fx = nv_song_note_fx(song, played[j], &fc);
        const bool efx = fx == -1 && k && k->efx_set && !iv[3] && !nv_moog_neutral();     // (live's template: none, live's own)
        const bool ffirst = fx >= 0 && nv_song_note_fx_first(song, played[j]);
        const double flv = fx >= 0 ? fc[0] : 1.0, fod = fx >= 0 ? fc[1] : 0.0;
        if (k && (k->amp_drive != 0.0 || (efx && k->efx_od != 0.0) || (ffirst && fod != 0.0))) {
            // (_note_amp_drive: the reference times the note's fader, chan_vol;
            // _note_insertion_efx: an OD stage the valve where the voice has
            // none, at PEDAL_AMP_DRIVE, its reference the voice's or the
            // Strat's, and the effect's level after the valve in it: 'steps')
            const bool own = k->amp_drive != 0.0;
            double r0 = own ? k->amp_reference : (k->amp_reference != 0.0 ? k->amp_reference : 0.2289);
            double ref = 0.0, pl[6];
            if (r0 != 0.0 && nv_song_pitch_level_k(song, played[j], k->init.effort_tilt != 0.0, k->indian, pl)) {
                double cv = pl[3], eg = 1.0;
                if (k->organ && k->organ->swells)   // (an organ's CC7 its swell: the note at 1, trimmed)
                    cv = 1.0 * nv_song_note_trim(song, played[j]);
                if (efx) {
                    cv *= k->efx_level;
                    eg = k->efx_od != 0.0 ? k->efx_od : 1.0;
                    cv *= eg;
                } else if (fx >= 0) {
                    cv *= flv;
                    eg = fod != 0.0 ? fod : 1.0;
                    cv *= eg;
                }
                ref = r0 * cv / eg;
                if (efx)
                    ref = ref / (k->efx_level > 1e-12 ? k->efx_level : 1e-12) * k->efx_level;
            }
            nv_song_add_amp(song, ch, own ? k->amp_drive : 1.0, k->leslie != 0, ref, k->amp_imbalance,
                            efx ? k->efx_level : fx >= 0 ? flv : 1.0);
        }
        if (ffirst) {
            nv_song_amp_steps(song, ch);                // (its reference follows the file's level: 'steps')
            if (fc[2] != 0.0 && nv_song_fx_cab(song, (int)fc[2]))
                nv_song_add_cab(song, ch, nv_song_fx_cab(song, (int)fc[2]));     // (its cabinet, ahead of the voice's)
        }
        if (ffirst && fc[208] != 0.0) {
            // A PARALLEL TYPE's BRANCH B on the part's virtual channel: where B
            // drives, a valve at PEDAL_AMP_DRIVE, its reference the voice's (or
            // the Strat's) times the part's level before the effect (_cv0),
            // following B's level steps; B's cabinet
            const double *fb_ = fc - NV_FXN;
            const long long vc = ch + 65536;
            // (...the voice's own valve where it has one -- its drive and
            // imbalance, its reference its own, none without -- else B's)
            const bool vown = k && k->amp_drive != 0.0;
            double pl[6];
            if ((vown || fb_[1] != 0.0) && k
                && nv_song_pitch_level_k(song, played[j], k->init.effort_tilt != 0.0, k->indian, pl)) {
                double cv = pl[3];
                if (k->organ && k->organ->swells)
                    cv = 1.0 * nv_song_note_trim(song, played[j]);
                const double eg = fod != 0.0 ? fod : 1.0;
                cv *= flv;
                cv *= eg;
                const double cv0 = cv / std::max(flv * eg, 1e-12);
                const double r0 = vown ? k->amp_reference : (k->amp_reference != 0.0 ? k->amp_reference : 0.2289);
                const double ref = r0 * cv0;
                nv_song_add_amp(song, vc, vown ? k->amp_drive : 1.0, 0, r0 != 0.0 ? ref : 0.0,
                                vown ? k->amp_imbalance : nv_amp_default_imbalance(), fb_[0]);
                if (r0 != 0.0)
                    nv_song_amp_steps_base(song, vc, ref);
            }
            if (fb_[2] != 0.0 && nv_song_fx_cab(song, (int)fb_[2]))
                nv_song_add_cab(song, vc, nv_song_fx_cab(song, (int)fb_[2]));
            else if (k && k->cab_set)
                nv_song_add_cab(song, vc, k);           // (...else the voice's own)
        }
        if (k && k->leslie)
            nv_song_add_leslie(song, ch, k->leslie);
        if (k && k->cab_set)                            // (_CAB_CH: the channel's, set once)
            nv_song_add_cab(song, ch, k);
        if (k && k->clav_panel) {                       // (_CLAV_CH: the part's first CC70, the rockers swept)
            int v;
            if (nv_song_first_cc(song, part, NV_CC_TONE, &v)) {
                int set = (int)nearbyint(v / 127.0 * 4.0);      // (round: half to even)
                if (set != 2)                           // (CLAV_FLAT: all four up, nothing)
                    nv_song_add_clav(song, ch, set);
            }
        }
        if (efx && k->efx_trem)                         // (an insertion effect's tremolo, ahead of the voice's)
            nv_song_add_trem(song, ch, k->trem_cfg);
        if (k && !k->organ && k->trem_depth > 0.0) {    // (_note_tremolo: the channel's, set once)
            int v;
            double dep = k->trem_intrinsic ? k->trem_depth
                                           : k->trem_depth * (nv_song_first_cc(song, part, NV_CC_TREMOLO, &v) ? v / 127.0 : 0.0);
            if (dep > 0.0) {
                double cfg[4] = {k->trem_hz, dep, (double)k->trem_stereo, k->trem_scatter};
                nv_song_add_trem(song, ch, cfg);
            }
        }
        if (fx >= 0 && fc[208] != 0.0) {
            // A PARALLEL TYPE's NOTE CLOSED (_par_close): the part's tremolo
            // and rockers its virtual channel's too, where it has none yet
            const long long vc = part + 65536;
            const int nt_ = nv_song_trems(song, nullptr, nullptr, 0);
            std::vector<long long> tc(nt_ > 0 ? nt_ : 1);
            std::vector<double> tg(4 * (nt_ > 0 ? nt_ : 1));
            nv_song_trems(song, tc.data(), tg.data(), nt_);
            for (int q = 0; q < nt_; q++)
                if (tc[q] == part) {
                    nv_song_add_trem(song, vc, tg.data() + 4 * q);
                    break;
                }
            const int nc_ = nv_song_clavs(song, nullptr, nullptr, 0);
            std::vector<long long> cc_(nc_ > 0 ? nc_ : 1);
            std::vector<int> cs_(nc_ > 0 ? nc_ : 1);
            nv_song_clavs(song, cc_.data(), cs_.data(), nc_);
            for (int q = 0; q < nc_; q++)
                if (cc_[q] == part) {
                    nv_song_add_clav(song, vc, cs_[q]);
                    break;
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
    if (stream) {
        // the passes that read the table: refused where they would act
        // (the MF-104M's repeats the stream's own, note by note: nv_mf104_note)
        // (an insertion effect's work the passes', each refusing its own; the
        // delays' repeats the stream's own, note by note: nv_gsd_note)
        g_sn_i.assign(played.begin(), played.begin() + nn);     // (pass A's notes, for its replay's tracks)
        g_sn_band.assign(bands.begin(), bands.begin() + nn);
        g_sn_land.assign(offs.begin(), offs.begin() + nn);
        out[0] = (double)N;                 // (the ring's end: the stream's own scan)
        out[1] = (double)nblk;
        out[2] = (double)P;
        out[3] = (double)nnote;
        out[42] = (double)nnote;
        out[40] = out[41] = 0.0;            // (no damper tracks)
        for (int i = 0; i < 6; i++)
            dm[i] = nullptr;
        for (int i = 0; i < 9; i++) {       // the room's bands, from the play's tallies
            double d = qacc[2 * i], r = qacc[2 * i + 1];
            out[4 + 3 * i] = tmpl->room_bands[i];
            out[4 + 3 * i + 1] = r > 0.0 ? d / r : 1.0;
            out[4 + 3 * i + 2] = d;
        }
        return P;
    }
    long long mlast = mf104_expand(song, rowsp, &P, kind, sr);
    if (mlast < -1)
        return NV_TOO_SMALL;
    if (mlast > 0 && mlast + srl / 2 > N)
        N = mlast + srl / 2;
    long long glast = gsd_expand(K, song, played.data(), row0.data(), nn, nnote, rowsp, &P, kind, sr);
    if (glast < -1)
        return NV_TOO_SMALL;
    if (glast > 0 && glast + srl / 2 > N)
        N = glast + srl / 2;
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
        long long r0 = row0[j], r1 = nv_play_own_end(j, j + 1 < nn ? row0[j + 1] : nnote);
        if (r1 <= r0)
            continue;
        Track T;
        if (!damp_track(song, i, rows + NCOLS * r0, r1 - r0, offs[j], SR, blk, nblk, full_db_s, residual, knee_db, T))
            continue;
        T.r0 = r0; T.r1 = r1;
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
