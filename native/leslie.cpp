// leslie.cpp -- THE ROTATING SPEAKER (leslie.py) on a finished table, as
// blockrender's _prep_rotating_speaker runs it with the kernel's lobe
// (KERNEL_LOBE, SIDEBANDS): every row of a Leslie channel through the
// cabinet's colour and the crossover (a copy for the other rotor's share
// where it is within XOVER_FLOOR), its Doppler in the vibrato columns from
// its rotor's rate and angle at its onset; each rotor row's lobe columns
// (lsr, lph, lfl, lsh, lnm: lobe_columns), and each rotor's angle on the
// kernel's grid (angle_table: LANG). The rotors as leslie.Rotor integrates
// them from the half-moon's requests. Bit for bit leslie.py's -- its lobe's
// mean with libm's cos and pow (lobe_params) and numpy's pairwise sum.
//
// The constants are leslie.py's, from the export (L_* below); the beams'
// own (beam's 700 Hz, drum_beam's 0.06 and 9.0) are written here as there.

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <array>
#include <cstring>
#include <map>
#include <vector>

#include "nv.h"

namespace {

enum { L_XOVER_HZ, L_HORN_RADIUS, L_DRUM_RADIUS, L_SLOW, L_FAST, L_DRUM_RATIO, L_C, L_XOVER_FLOOR, L_HORN_FLOOR,
       L_HORN_SHARP, L_DRUM_DEPTH, L_DRUM_REF, L_HORN_UP, L_HORN_DOWN, L_DRUM_UP, L_DRUM_DOWN, L_LOBE, L_NCAB,
       L_CAB };

const double TWO_PI = 2.0 * M_PI;

// leslie.Rotor: one rotor's angle over time, integrated in 10 ms steps
struct Rotor {
    double up, down, ratio, step = 0.01;
    std::vector<double> rate, angle;

    Rotor(bool horn, std::vector<std::pair<double, double>> req, const double *L)
        : Rotor(horn ? L[L_HORN_UP] : L[L_DRUM_UP], horn ? L[L_HORN_DOWN] : L[L_DRUM_DOWN],
                horn ? 1.0 : L[L_DRUM_RATIO], req, L)
    {
    }

    // an insertion Rotary's (gsefx.rotary_setup): its own spin times, its
    // drum asked its own speed (ratio -1: only turning the other way)
    Rotor(double up_, double down_, double ratio_, std::vector<std::pair<double, double>> req, const double *L)
    {
        up = up_;
        down = down_;
        ratio = ratio_;
        angle.push_back(0.0);
        std::sort(req.begin(), req.end());
        if (req.empty())
            req.push_back(std::make_pair(0.0, L[L_FAST]));
        double end = std::max(req.back().first, 0.0) + 30.0;
        double want = req[0].second, r = want, a = 0.0, t = 0.0;
        size_t i = 0;
        rate.push_back(r);
        while (t < end) {
            while (i < req.size() && req[i].first <= t) {
                want = req[i].second;
                i++;
            }
            double tau = want > r ? up : down;
            r += (want - r) * (1.0 - exp(-step / tau));
            a += 2.0 * M_PI * r * step;
            t += step;
            rate.push_back(r);
            angle.push_back(a);
        }
    }

    // at: (rate, angle), linear between the steps
    void at(double t, double *rt, double *ang) const
    {
        double k = t / step;
        long long i = (long long)k;
        if (i < 0) {
            *rt = rate[0];
            *ang = angle[0];
            return;
        }
        if (i >= (long long)rate.size() - 1) {
            *rt = rate.back();
            *ang = angle.back();
            return;
        }
        double f = k - (double)i;
        *rt = rate[i] + (rate[i + 1] - rate[i]) * f;
        *ang = angle[i] + (angle[i + 1] - angle[i]) * f;
    }

    // angles: np.interp over the steps (k = arange * step), past the end on at the last rate
    double angle_at(double t, const std::vector<double> &k) const
    {
        size_t n = k.size();
        if (t > k[n - 1])
            return angle[n - 1] + 2.0 * M_PI * rate[n - 1] * (t - k[n - 1]);
        if (t < k[0])
            return angle[0];
        size_t j = (size_t)(std::upper_bound(k.begin(), k.end(), t) - k.begin()) - 1;
        if (j == n - 1 || k[j] == t)
            return angle[j];
        double slope = (angle[j + 1] - angle[j]) / (k[j + 1] - k[j]);
        return slope * (t - k[j]) + angle[j];
    }
};

// np.mod(a, b) for b > 0 (npy_divmod's remainder)
double npmod(double a, double b)
{
    double m = fmod(a, b);
    if (m != 0.0) {
        if ((b < 0) != (m < 0))
            m += b;
    } else {
        m = copysign(0.0, b);
    }
    return m;
}

// AN INSERTION ROTARY's channel record (gsefx.rotary_setup), GSW wide: 1,
// the horn's spin up and down, the drum's, the drum's and horn's levels,
// Separate given (1) and its angle, the drum's requests (after the horn's
// in req); 0 a Leslie's
const int GSW = 10;
const double MIC_SHARE = 0.70710678118654752440;      // (leslie.MIC_SHARE: 0.5 ** 0.5)

}  // namespace
extern "C" void nv_gsd_place(int side, double f, const double *pl, double *out);
namespace {

// leslie._to_mic: row v as one microphone of a recorded Rotary hears it, at
// azimuth az to the rotors, arriving from its speaker (side 0 left, 1 right:
// the GS outputs' places) -- its ear gains and delays the speaker's, its
// phase the line's
void to_mic(double *v, int side, double az, const double *place, double f)
{
    const int cOM = 0, cP0 = 1, cP0R = 2, cAL = 3, cAR = 4, cAM = 5, cAZ = 9, cNON = 12, cDELL = 37, cDELR = 38;
    double pl[4];
    nv_gsd_place(side, f, place, pl);
    double om = v[cOM], non = v[cNON];
    double m = fabs(v[cAM]) * MIC_SHARE;
    v[cP0] = -om * (non + pl[2]) + (v[cP0] + om * (non + v[cDELL]));
    v[cP0R] = -om * (non + pl[3]) + (v[cP0R] + om * (non + v[cDELR]));
    v[cDELL] = pl[2];
    v[cDELR] = pl[3];
    v[cAL] = m * pl[0];
    v[cAR] = m * pl[1];
    v[cAM] = v[cAM] * MIC_SHARE;
    v[cAZ] = az;
}

// the rotors of channel k (horn, drum), its requests from req at *q on
long make_rotors(int k, const int *nreq, const double *req, long q, const double *gs, const double *L,
                 std::vector<Rotor> &out)
{
    std::vector<std::pair<double, double>> rq;
    for (int j = 0; j < nreq[k]; j++, q++)
        rq.push_back(std::make_pair(req[2 * q], req[2 * q + 1]));
    const double *G = gs ? gs + GSW * k : nullptr;
    if (!G || G[0] == 0.0) {
        out.emplace_back(true, rq, L);
        out.emplace_back(false, rq, L);
        return q;
    }
    std::vector<std::pair<double, double>> rd;
    for (int j = 0; j < (int)G[9]; j++, q++)
        rd.push_back(std::make_pair(req[2 * q], req[2 * q + 1]));
    out.emplace_back(G[1], G[2], 1.0, rq, L);
    out.emplace_back(G[3], G[4], -1.0, rd, L);
    return q;
}

// leslie.cabinet_gain
double cabinet_gain(double f, const double *L)
{
    int n = (int)L[L_NCAB];
    const double *p = L + L_CAB;
    double db = 0.0;
    if (f <= p[0])
        db = p[1];
    else if (f >= p[2 * (n - 1)])
        db = p[2 * (n - 1) + 1];
    else
        for (int i = 0; i + 1 < n; i++) {
            double f0 = p[2 * i], d0 = p[2 * i + 1], f1 = p[2 * i + 2], d1 = p[2 * i + 3];
            if (f <= f1) {
                db = d0 + (d1 - d0) * log(f / f0) / log(f1 / f0);
                break;
            }
        }
    return pow(10.0, db / 20.0);
}

// leslie.beam: (floor, sharpness)
void beam(double f, double floor_, double ref, double sharpness, double *fl, double *sharp)
{
    double x = pow(f / ref, 2.0);
    *sharp = 0.6 + sharpness * x / (1.0 + x);
    *fl = 1.0 - (1.0 - floor_) * x / (1.0 + x);
}

// leslie.beam (the horn's) or drum_beam
void lobe_of(double f, bool horn, const double *L, double *fl, double *sh)
{
    if (horn) {
        beam(f, L[L_HORN_FLOOR], 700.0, L[L_HORN_SHARP], fl, sh);
        return;
    }
    double f0, s0;
    beam(f, 0.06, L[L_DRUM_REF], 9.0, &f0, &s0);
    *fl = 1.0 - (1.0 - f0) * L[L_DRUM_DEPTH];
    double h = s0 * 0.5;
    *sh = h > 0.5 ? h : 0.5;
}

// numpy's pairwise sum (DOUBLE_pairwise_sum, PW_BLOCKSIZE 128)
double pairwise(const double *a, long n)
{
    if (n < 8) {
        double r = 0.0;
        for (long i = 0; i < n; i++)
            r += a[i];
        return r;
    }
    if (n <= 128) {
        double r[8];
        for (int j = 0; j < 8; j++)
            r[j] = a[j];
        long i = 8;
        for (; i < n - (n % 8); i += 8)
            for (int j = 0; j < 8; j++)
                r[j] += a[i + j];
        double res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        for (; i < n; i++)
            res += a[i];
        return res;
    }
    long n2 = n / 2;
    n2 -= n2 % 8;
    return pairwise(a, n2) + pairwise(a + n2, n - n2);
}

}  // namespace

extern "C" {

// THE LESLIE over a table: rows (NCOLS each, *Pp of them, realloc'd), the
// channels (chans[k], each with nreq[k] requests (seconds, Hz) from req0[k])
// in leslie's order -- expand's rotor index -- and L its constants; a
// damper's dk/dg copied with any copy. The lobe columns for every row after
// it (malloc'd: lsr int32, lph lfl lsh lnm float32) in *lobe[0..4] -- or,
// lobe NULL, none: live's template (SIDEBANDS off: the swing is live's). The
// crossover's copies' rows into *flips (malloc'd, *nflips of them) where
// flips is given (live's leslie_flip). Returns the copies made, or -1 where
// the export's leslie does not render by the kernel's lobe.
long long nv_leslie_expand_gs(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                              const int *nreq, const double *req, double sr, const double *L, void **lobe,
                              long long **flips, long long *nflips, const double *gs, const double *place);

long long nv_leslie_expand(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                           const int *nreq, const double *req, double sr, const double *L, void **lobe,
                           long long **flips, long long *nflips)
{
    return nv_leslie_expand_gs(rowsp, Pp, dm, nch, chans, nreq, req, sr, L, lobe, flips, nflips, nullptr,
                               nullptr);
}

// ...with each channel's insertion Rotary (gs: GSW a channel, NULL none) and
// the GS outputs' places (a recorded Rotary's microphones: K_GSPLACE's)
// THE LESLIE's ROWS, one at a time (nv_leslie_expand_gs's, a stream's): its
// rotors made once from the channels' requests
struct LeslieSet {
    std::map<long long, int> rank;
    std::vector<Rotor> rotors;
    double sr;
    const double *L, *gs, *place;
};
void *nv_leslie_new(int nch, const long long *chans, const int *nreq, const double *req, double sr, const double *L,
                    const double *gs, const double *place)
{
    LeslieSet *h = new LeslieSet;
    long q = 0;
    for (int k = 0; k < nch; k++) {
        h->rank[chans[k]] = k;
        q = make_rotors(k, nreq, req, q, gs, L, h->rotors);
    }
    h->sr = sr;
    h->L = L;
    h->gs = gs;
    h->place = place;
    return h;
}
void nv_leslie_free(void *h) { delete (LeslieSet *)h; }

// a lobe's columns (lobe_params): its rotor, azimuth (float32), floor and
// sharpness (float32), one over its mean over 256 points (libm's cos and
// pow; numpy's mean) -- into o[5]
static void lobe_cols(int rot, double az, double f, bool horn, const double *L, float *o)
{
    double cc[256], g[256];
    for (int k = 0; k < 256; k++) {
        double th = (double)k * (2.0 * M_PI / 256.0);
        cc[k] = 0.5 * (1.0 + cos(th));
    }
    double fl_, sh_;
    lobe_of(f, horn, L, &fl_, &sh_);
    float fl = (float)fl_, sh = (float)sh_;
    float hs = 0.5f * sh, om = 1.0f - fl;
    for (int k = 0; k < 256; k++)
        g[k] = (double)fl + (double)om * pow(cc[k], (double)hs);
    float nrm = (float)((0.0 + pairwise(g, 256)) / 256.0);
    o[0] = (float)rot;
    o[1] = (float)az;
    o[2] = fl;
    o[3] = hs;
    o[4] = 1.0f / nrm;
}

// ONE ROW (NCOLS) through the Leslie: on a rotor's channel and sounding (f
// > 0), its level its cabinet's and crossover's, rotated, *on set and its
// lobe in lob[0..4]; its copies (its twin, mic B's: up to 3, in the order
// the whole table appends them) into cp (NCOLS each), their lobes after
// its in lob; the copies returned. Off a rotor: untouched, *on 0.
int nv_leslie_row(void *hv, double *r, double *cp, float *lob, int *on)
{
    LeslieSet &h = *(LeslieSet *)hv;
    const double *L = h.L, *gs = h.gs, *place = h.place;
    const double sr = h.sr;
    const int cOM = 0, cAL = 3, cAR = 4, cAM = 5, cMCH = 6, cAZ = 9, cDIR = 10, cNF = 11, cNON = 12, cVD = 33,
              cVR = 34, cVP = 35;
    (void)cOM;
    *on = 0;
    auto rotate = [&](double *x, bool horn) {
        const Rotor &ro = h.rotors[2 * h.rank[(long long)x[cMCH]] + (horn ? 0 : 1)];
        double t_on = x[cNON] / sr, rate, angle;
        ro.at(t_on, &rate, &angle);
        if (!horn) {
            rate *= fabs(ro.ratio);
            angle *= ro.ratio;
        }
        double radius = horn ? L[L_HORN_RADIUS] : L[L_DRUM_RADIUS];
        double fm = 2.0 * M_PI * radius * rate / L[L_C];
        double ph = angle - 2.0 * M_PI * rate * t_on - x[cAZ];
        x[cVD] = fm;
        x[cVR] = rate;
        x[cVP] = atan2(sin(ph), cos(ph));
        if (rate < 0.05)
            x[cVD] = 0.0;
    };
    auto it = h.rank.find((long long)r[cMCH]);
    if (it == h.rank.end())
        return 0;
    double f = r[cNF];
    if (f <= 0.0)
        return 0;
    *on = 1;
    bool horn = f >= L[L_XOVER_HZ];
    double cg = cabinet_gain(f, L);
    double x4 = pow((f > 1e-9 ? f : 1e-9) / L[L_XOVER_HZ], 4.0);
    double wh = sqrt(x4 / (1.0 + x4)), wd = sqrt(1.0 / (1.0 + x4));
    // an insertion Rotary's own balance of the rotors (its Hi/Low Level)
    const double *G = gs && gs[GSW * it->second] != 0.0 ? gs + GSW * it->second : nullptr;
    if (G) {
        wh = wh * G[6];
        wd = wd * G[5];
    }
    double wp = horn ? wh : wd, ws = horn ? wd : wh;
    if (ws < L[L_XOVER_FLOOR]) {
        wp = 1.0;
        ws = 0.0;
    }
    std::vector<double> twin;
    if (ws > 0.0) {
        twin.assign(r, r + NCOLS);
        for (int c : {cAL, cAR, cAM})
            twin[c] = r[c] * cg * ws;
    }
    for (int c : {cAL, cAR, cAM})
        r[c] = r[c] * cg * wp;
    // A RECORDED ROTARY (its Separate): the direct sound as two
    // microphones round the cabinet hear it -- mic A to the left, mic B
    // to the right, Separate apart -- each its own swing and Doppler
    std::vector<double> rB, twinB;
    if (G && G[7] != 0.0 && place && r[cDIR] > 0.5) {
        double az0 = r[cAZ], sep = G[8];
        rB.assign(r, r + NCOLS);
        to_mic(rB.data(), 1, az0 + 0.5 * sep, place, f);
        to_mic(r, 0, az0 - 0.5 * sep, place, f);
        if (!twin.empty()) {
            twinB = twin;
            to_mic(twinB.data(), 1, az0 + 0.5 * sep, place, f);
            to_mic(twin.data(), 0, az0 - 0.5 * sep, place, f);
        }
    }
    rotate(r, horn);
    lobe_cols(2 * it->second + (horn ? 0 : 1), r[cAZ], f, horn, L, lob);
    int nc = 0;
    if (!twin.empty()) {
        rotate(twin.data(), !horn);
        memcpy(cp + (size_t)NCOLS * nc, twin.data(), sizeof(double) * NCOLS);
        nc++;
        lobe_cols(2 * it->second + (horn ? 1 : 0), twin[cAZ], f, !horn, L, lob + 5 * nc);
    }
    // ...and mic B's: the row's, then its twin's, after them
    for (int b = 0; b < 2; b++) {
        std::vector<double> &vb = b ? twinB : rB;
        if (vb.empty())
            continue;
        bool hb = b ? !horn : horn;
        rotate(vb.data(), hb);
        memcpy(cp + (size_t)NCOLS * nc, vb.data(), sizeof(double) * NCOLS);
        nc++;
        lobe_cols(2 * it->second + (hb ? 0 : 1), vb[cAZ], f, hb, L, lob + 5 * nc);
    }
    return nc;
}

long long nv_leslie_expand_gs(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                              const int *nreq, const double *req, double sr, const double *L, void **lobe,
                              long long **flips, long long *nflips, const double *gs, const double *place)
{
    if (lobe && L[L_LOBE] == 0.0)
        return -1;
    void *h = nv_leslie_new(nch, chans, nreq, req, sr, L, gs, place);
    const long long n = *Pp;
    double *rows = *rowsp;
    std::vector<double> extra;
    std::vector<long long> src;
    std::vector<std::pair<long long, std::array<float, 5>>> lobes;     // (row, its lobe's columns)
    double cp[3 * NCOLS];
    float lob[4 * 5];
    for (long long i = 0; i < n; i++) {
        int on;
        int nc = nv_leslie_row(h, rows + (size_t)NCOLS * i, cp, lob, &on);
        if (!on)
            continue;
        std::array<float, 5> a;
        std::copy(lob, lob + 5, a.begin());
        lobes.push_back(std::make_pair(i, a));
        for (int q = 0; q < nc; q++) {
            long long pos = (long long)src.size();
            extra.insert(extra.end(), cp + (size_t)NCOLS * q, cp + (size_t)NCOLS * (q + 1));
            src.push_back(i);
            std::copy(lob + 5 * (q + 1), lob + 5 * (q + 2), a.begin());
            lobes.push_back(std::make_pair(n + pos, a));
        }
    }
    nv_leslie_free(h);
    long long m = (long long)src.size();
    if (m) {
        rows = (double *)realloc(*rowsp, sizeof(double) * NCOLS * (size_t)(n + m));
        memcpy(rows + (size_t)NCOLS * n, extra.data(), sizeof(double) * extra.size());
        *rowsp = rows;
        if (dm[0]) {
            int32_t *dk = (int32_t *)realloc(dm[0], sizeof(int32_t) * (size_t)(n + m));
            float *dg = (float *)realloc(dm[1], sizeof(float) * (size_t)(n + m));
            for (long long q = 0; q < m; q++) {
                dk[n + q] = dk[src[q]];
                dg[n + q] = dg[src[q]];
            }
            dm[0] = dk;
            dm[1] = dg;
        }
    }
    const long long P = n + m;
    *Pp = P;
    if (flips) {
        *flips = (long long *)malloc(sizeof(long long) * (size_t)(m ? m : 1));
        for (long long q = 0; q < m; q++)
            (*flips)[q] = n + q;
        *nflips = m;
    }
    if (!lobe)
        return m;
    // lobe_columns: every row on no rotor (-1, 0, 1, 0, 1), then the rotor rows'
    int32_t *lsr = (int32_t *)malloc(sizeof(int32_t) * (size_t)(P ? P : 1));
    float *lph = (float *)malloc(sizeof(float) * (size_t)(P ? P : 1));
    float *lfl = (float *)malloc(sizeof(float) * (size_t)(P ? P : 1));
    float *lsh = (float *)malloc(sizeof(float) * (size_t)(P ? P : 1));
    float *lnm = (float *)malloc(sizeof(float) * (size_t)(P ? P : 1));
    for (long long q = 0; q < P; q++) {
        lsr[q] = -1;
        lph[q] = 0.0f;
        lfl[q] = 1.0f;
        lsh[q] = 0.0f;
        lnm[q] = 1.0f;
    }
    for (const auto &b : lobes) {
        lsr[b.first] = (int32_t)b.second[0];
        lph[b.first] = b.second[1];
        lfl[b.first] = b.second[2];
        lsh[b.first] = b.second[3];
        lnm[b.first] = b.second[4];
    }
    lobe[0] = lsr;
    lobe[1] = lph;
    lobe[2] = lfl;
    lobe[3] = lsh;
    lobe[4] = lnm;
    return m;
}

// a partial at f's lobe on the horn (else the drum): (floor, sharpness),
// leslie.beam / drum_beam's -- live's slab reads it (Slab.leslie_params)
void nv_leslie_lobe_of(double f, int horn, const double *L, double *fl, double *sh)
{
    lobe_of(f, horn != 0, L, fl, sh);
}

// live.Slab.leslie_params for n partials at nf (flip: a crossover copy's
// rotor flipped, NULL none): each's rotor (horn), its lobe's floor and
// sharpness (float32), the lobe's mean (libm's cos and pow; numpy's mean)
void nv_leslie_params(long n, const double *nf, const char *flip, const double *L, char *horn, float *fl, float *sh,
                      double *nrm)
{
    double cc[256], g[256];
    for (int k = 0; k < 256; k++)
        cc[k] = 0.5 * (1.0 + cos((double)k * (2.0 * M_PI / 256.0)));
    for (long j = 0; j < n; j++) {
        double f = nf[j];
        horn[j] = (f >= L[L_XOVER_HZ]) ^ (flip && flip[j]);
        double a, b;
        lobe_of(f, horn[j] != 0, L, &a, &b);
        fl[j] = (float)a;
        sh[j] = (float)b;
        float hs = 0.5f * sh[j], om = 1.0f - fl[j];
        for (int k = 0; k < 256; k++)
            g[k] = (double)fl[j] + (double)om * pow(cc[k], (double)hs);
        nrm[j] = (0.0 + pairwise(g, 256)) / 256.0;
    }
}

// angle_table: each rotor's angle (wrapped to a turn, float32) at every grid
// point of an n_samples render -- 2 a channel, the horn then the drum (which
// turns the other way) -- into LANG (2 * nch * lgn); lgn = n_samples / g + 2,
// g the kernel's grid (rotor_grid). Returns lgn.
long nv_leslie_angles_gs(int nch, const int *nreq, const double *req, long n_samples, double sr, int blk,
                         const double *L, float *LANG, const double *gs);

long nv_leslie_angles(int nch, const int *nreq, const double *req, long n_samples, double sr, int blk,
                      const double *L, float *LANG)
{
    return nv_leslie_angles_gs(nch, nreq, req, n_samples, sr, blk, L, LANG, nullptr);
}

// ...with each channel's insertion Rotary (gs: GSW a channel, NULL none)
long nv_leslie_angles_gs(int nch, const int *nreq, const double *req, long n_samples, double sr, int blk,
                         const double *L, float *LANG, const double *gs)
{
    long gg = (blk % 128 == 0 && blk / 128 <= 64) ? 128 : blk;
    long lgn = n_samples / gg + 2;
    if (!LANG)
        return lgn;
    long q = 0;
    for (int k = 0; k < nch; k++) {
        std::vector<Rotor> rs;
        q = make_rotors(k, nreq, req, q, gs, L, rs);
        for (int h = 0; h < 2; h++) {
            const Rotor &ro = rs[h];
            std::vector<double> kk(ro.angle.size());
            for (size_t i = 0; i < kk.size(); i++)
                kk[i] = (double)i * ro.step;
            float *out = LANG + (size_t)(2 * k + h) * lgn;
            for (long i = 0; i < lgn; i++) {
                double t = (double)i * ((double)gg / sr);
                double a = ro.angle_at(t, kk);
                if (h == 1)
                    a = ro.ratio * a;
                out[i] = (float)npmod(a, TWO_PI);
            }
        }
    }
    return lgn;
}

}  // extern "C"
