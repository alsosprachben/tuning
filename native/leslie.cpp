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
    {
        up = horn ? L[L_HORN_UP] : L[L_DRUM_UP];
        down = horn ? L[L_HORN_DOWN] : L[L_DRUM_DOWN];
        ratio = horn ? 1.0 : L[L_DRUM_RATIO];
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
long long nv_leslie_expand(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                           const int *nreq, const double *req, double sr, const double *L, void **lobe,
                           long long **flips, long long *nflips)
{
    if (lobe && L[L_LOBE] == 0.0)
        return -1;
    const int cOM = 0, cAL = 3, cAR = 4, cAM = 5, cMCH = 6, cAZ = 9, cNF = 11, cNON = 12, cVD = 33, cVR = 34,
              cVP = 35;
    std::map<long long, int> rank;
    std::vector<Rotor> rotors;
    {
        long q = 0;
        for (int k = 0; k < nch; k++) {
            std::vector<std::pair<double, double>> rq;
            for (int j = 0; j < nreq[k]; j++, q++)
                rq.push_back(std::make_pair(req[2 * q], req[2 * q + 1]));
            rank[chans[k]] = k;
            rotors.emplace_back(true, rq, L);
            rotors.emplace_back(false, rq, L);
        }
    }
    const long long n = *Pp;
    double *rows = *rowsp;
    std::vector<double> extra;
    std::vector<long long> src;
    struct Lobe {
        long long row;
        int rot;
        double az, f;
        bool horn;
    };
    std::vector<Lobe> lobes;
    // rotate: a row on a rotor -- its Doppler from the rotor at its onset
    auto rotate = [&](double *r, bool horn) {
        const Rotor &ro = rotors[2 * rank[(long long)r[cMCH]] + (horn ? 0 : 1)];
        double t_on = r[cNON] / sr, rate, angle;
        ro.at(t_on, &rate, &angle);
        if (!horn) {
            rate *= fabs(ro.ratio);
            angle *= ro.ratio;
        }
        double radius = horn ? L[L_HORN_RADIUS] : L[L_DRUM_RADIUS];
        double fm = 2.0 * M_PI * radius * rate / L[L_C];
        double ph = angle - 2.0 * M_PI * rate * t_on - r[cAZ];
        r[cVD] = fm;
        r[cVR] = rate;
        r[cVP] = atan2(sin(ph), cos(ph));
        if (rate < 0.05)
            r[cVD] = 0.0;
    };
    for (long long i = 0; i < n; i++) {
        double *r = rows + (size_t)NCOLS * i;
        auto it = rank.find((long long)r[cMCH]);
        if (it == rank.end())
            continue;
        double f = r[cNF];
        if (f <= 0.0)
            continue;
        bool horn = f >= L[L_XOVER_HZ];
        double cg = cabinet_gain(f, L);
        double x4 = pow((f > 1e-9 ? f : 1e-9) / L[L_XOVER_HZ], 4.0);
        double wh = sqrt(x4 / (1.0 + x4)), wd = sqrt(1.0 / (1.0 + x4));
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
        rotate(r, horn);
        lobes.push_back(Lobe{i, 2 * it->second + (horn ? 0 : 1), r[cAZ], f, horn});
        if (!twin.empty()) {
            long long pos = (long long)src.size();
            rotate(twin.data(), !horn);
            extra.insert(extra.end(), twin.begin(), twin.end());
            src.push_back(i);
            lobes.push_back(Lobe{n + pos, 2 * it->second + (horn ? 1 : 0), twin[cAZ], f, !horn});
        }
    }
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
    // lobe_params: the floor and sharpness (float32), the mean over 256
    // points of the lobe (libm's cos and pow; numpy's mean) as float32, one
    // over it in float32
    double cc[256];
    for (int k = 0; k < 256; k++) {
        double th = (double)k * (2.0 * M_PI / 256.0);
        cc[k] = 0.5 * (1.0 + cos(th));
    }
    double g[256];
    for (const Lobe &b : lobes) {
        double fl_, sh_;
        lobe_of(b.f, b.horn, L, &fl_, &sh_);
        float fl = (float)fl_, sh = (float)sh_;
        float hs = 0.5f * sh, om = 1.0f - fl;
        for (int k = 0; k < 256; k++)
            g[k] = (double)fl + (double)om * pow(cc[k], (double)hs);
        float nrm = (float)((0.0 + pairwise(g, 256)) / 256.0);
        lsr[b.row] = b.rot;
        lph[b.row] = (float)b.az;
        lfl[b.row] = fl;
        lsh[b.row] = hs;
        lnm[b.row] = 1.0f / nrm;
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

// angle_table: each rotor's angle (wrapped to a turn, float32) at every grid
// point of an n_samples render -- 2 a channel, the horn then the drum (which
// turns the other way) -- into LANG (2 * nch * lgn); lgn = n_samples / g + 2,
// g the kernel's grid (rotor_grid). Returns lgn.
long nv_leslie_angles(int nch, const int *nreq, const double *req, long n_samples, double sr, int blk,
                      const double *L, float *LANG)
{
    long gg = (blk % 128 == 0 && blk / 128 <= 64) ? 128 : blk;
    long lgn = n_samples / gg + 2;
    if (!LANG)
        return lgn;
    long q = 0;
    for (int k = 0; k < nch; k++) {
        std::vector<std::pair<double, double>> rq;
        for (int j = 0; j < nreq[k]; j++, q++)
            rq.push_back(std::make_pair(req[2 * q], req[2 * q + 1]));
        for (int h = 0; h < 2; h++) {
            Rotor ro(h == 0, rq, L);
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
