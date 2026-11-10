#include <array>
// scanner.cpp -- THE HAMMOND SCANNER (scanner.py) for a file render: each
// scanned channel's band rows (rows: the moving delay as a bend row a band,
// on the motor's clock from 0), and the pass over the finished table
// (expand): each partial of the channel not on a row of its own put on its
// band's row with the scanned path's gain (vibrato), or kept at the
// circuit's dry share with a copy on the row (chorus), and tier B's
// sideband copies. The circuit's tables are the Python's (scanner.table_d,
// solved there with LAPACK), from the export; everything after them is
// scanner.py's arithmetic -- each complex product written out, libm's cos,
// sin, log, hypot and atan2, the shared FFT (tubeamp.cpp), numpy's pairwise
// means and its interp -- bit for bit.

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <map>
#include <vector>

#include "nv.h"

extern "C" int nv_cfft(const double *z, long n, double *out);

namespace {

// the export's SCAN section: constants, then the two tables (vibrato, chorus)
enum { S_HZ, S_SIDEBANDS, S_SIDE_DB, S_FLOOR_DB, S_MAX_SIDE, S_BAND0, S_TAPS0 = S_BAND0 + 6,
       S_PLATES0 = S_TAPS0 + 27, S_NTAB = S_PLATES0 + 16 };

struct Tab {
    long n = 0;
    std::vector<double> fg, lg, rm, rp, mag, ph;     // mag, ph: n x 19
};

struct Scan {
    double hz, side_db, floor_db;
    int sidebands, max_side;
    double band_hz[6];
    int taps[3][9], plates[16];
    Tab tab[2];
    std::map<int, std::vector<double>> dcache;        // band_delays, by (depth, band, chorus)
};

// np.interp(x, xp, fp) for one x (xp increasing, fp strided by st)
double interp(double x, const double *xp, const double *fp, long n, long st)
{
    if (x > xp[n - 1])
        return fp[(n - 1) * st];
    if (x < xp[0])
        return fp[0];
    long j = (long)(std::upper_bound(xp, xp + n, x) - xp) - 1;
    if (j == n - 1 || xp[j] == x)
        return fp[j * st];
    double slope = (fp[(j + 1) * st] - fp[j * st]) / (xp[j + 1] - xp[j]);
    return slope * (x - xp[j]) + fp[j * st];
}

// numpy's pairwise sum (stride 1) and mean
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
double npmean(const double *a, long n) { return (0.0 + pairwise(a, n)) / (double)n; }

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

// band_delays: the delays (s) of terminals t1..t9 at the band's centre
const std::vector<double> &band_delays(Scan &S, int depth, int band, int chorus)
{
    int key = (depth * 8 + band) * 2 + chorus;
    auto it = S.dcache.find(key);
    if (it != S.dcache.end())
        return it->second;
    const Tab &T = S.tab[chorus];
    double f = S.band_hz[band];
    double lf = log(std::max(f, T.fg[0]));
    std::vector<double> &d = S.dcache[key];
    for (int j = 0; j < 9; j++) {
        int k = S.taps[depth - 1][j] - 1;
        d.push_back(-interp(lf, T.lg.data(), T.ph.data() + k, T.n, 19) / (2.0 * M_PI * f));
    }
    return d;
}

// crossfade at theta: the two plates (a, b) and the first's share's complement eta
void crossfade(const Scan &S, double theta, int *a, int *b, double *eta)
{
    double p = npmod(theta / (2.0 * M_PI), 1.0) * 16.0;
    long i = (long)floor(p);
    *eta = p - (double)i;
    *a = S.plates[((i % 16) + 16) % 16];
    *b = S.plates[(((i + 1) % 16) + 16) % 16];
}

double delay(Scan &S, double theta, int depth, int band, int chorus)
{
    const std::vector<double> &d = band_delays(S, depth, band, chorus);
    int a, b;
    double eta;
    crossfade(S, theta, &a, &b, &eta);
    return (1.0 - eta) * d[a] + eta * d[b];
}

double mean_delay(Scan &S, int depth, int band, int chorus)
{
    double v[512];
    for (int k = 0; k < 512; k++)
        v[k] = delay(S, (double)k * 2.0 * M_PI / 512.0, depth, band, chorus);
    return npmean(v, 512);
}

int band_of(const Scan &S, double f)
{
    int n = 0;
    for (int i = 0; i < 5; i++)
        if (sqrt(S.band_hz[i] * S.band_hz[i + 1]) < f)
            n++;
    return n;
}

Scan load(const double *X)
{
    Scan S;
    S.hz = X[S_HZ];
    S.sidebands = (int)X[S_SIDEBANDS];
    S.side_db = X[S_SIDE_DB];
    S.floor_db = X[S_FLOOR_DB];
    S.max_side = (int)X[S_MAX_SIDE];
    for (int i = 0; i < 6; i++)
        S.band_hz[i] = X[S_BAND0 + i];
    for (int d = 0; d < 3; d++)
        for (int j = 0; j < 9; j++)
            S.taps[d][j] = (int)X[S_TAPS0 + 9 * d + j];
    for (int i = 0; i < 16; i++)
        S.plates[i] = (int)X[S_PLATES0 + i];
    const double *p = X + S_NTAB;
    for (int c = 0; c < 2; c++) {
        Tab &T = S.tab[c];
        T.n = (long)*p++;
        for (std::vector<double> *v : {&T.fg, &T.lg, &T.rm, &T.rp}) {
            v->assign(p, p + T.n);
            p += T.n;
        }
        T.mag.assign(p, p + 19 * T.n);
        p += 19 * T.n;
        T.ph.assign(p, p + 19 * T.n);
        p += 19 * T.n;
    }
    return S;
}

// a partial's rail-relative tap responses at f (re, im: 19 each)
void rel_at(const Scan &S, double f, int chorus, double *re, double *im)
{
    const Tab &T = S.tab[chorus];
    double lf = log(std::max(f, T.fg[0]));
    for (int k = 0; k < 19; k++) {
        double m = interp(lf, T.lg.data(), T.mag.data() + k, T.n, 19);
        double ph = interp(lf, T.lg.data(), T.ph.data() + k, T.n, 19);
        re[k] = m * cos(ph);
        im[k] = m * sin(ph);
    }
}

// the angles of a revolution (_TH) and their crossfade
struct Rev {
    double th[256], eta[256];
    int a[256], b[256];
};

// the scanned path of a partial at f over a revolution (Pr, Pi), and w
void scanned(Scan &S, const Rev &R, double f, int depth, int band, int chorus, double *Pr, double *Pi, double *w)
{
    double rr[19], ri[19];
    rel_at(S, f, chorus, rr, ri);
    *w = 2.0 * M_PI * f;
    for (int j = 0; j < 256; j++) {
        double tau = delay(S, R.th[j], depth, band, chorus);
        int ta = S.taps[depth - 1][R.a[j]] - 1, tb = S.taps[depth - 1][R.b[j]] - 1;
        double Sr = (1.0 - R.eta[j]) * rr[ta] + R.eta[j] * rr[tb];
        double Si = (1.0 - R.eta[j]) * ri[ta] + R.eta[j] * ri[tb];
        double x = *w * tau, c = cos(x), s = sin(x);
        Pr[j] = Sr * c - Si * s;
        Pi[j] = Sr * s + Si * c;
    }
}

// gains for one partial at f: its band, the dry share (dre, dim: 0 on
// vibrato), the scanned path's mean turned back by the row's mean delay
void gains_one(Scan &S, const Rev &R, double f, int depth, int chorus, std::map<int, double> &mdl, int *band,
               double *dre, double *dim, double *sre, double *sim)
{
    double Pr[256], Pi[256];
    *band = band_of(S, f);
    *dre = *dim = 0.0;
    if (chorus) {
        const Tab &T = S.tab[1];
        double lf = log(std::max(f, T.fg[0]));
        double m = interp(lf, T.lg.data(), T.rm.data(), T.n, 1);
        double p = interp(lf, T.lg.data(), T.rp.data(), T.n, 1);
        *dre = m * cos(p);
        *dim = m * sin(p);
    }
    if (!mdl.count(*band))
        mdl[*band] = mean_delay(S, depth, *band, chorus);
    double w;
    scanned(S, R, f, depth, *band, chorus, Pr, Pi, &w);
    double c0r = npmean(Pr, 256), c0i = npmean(Pi, 256);
    double x = (-w) * mdl[*band], cm = cos(x), sm = sin(x);
    *sre = c0r * cm - c0i * sm;
    *sim = c0r * sm + c0i * cm;
}

// tier B for one partial at f (its level amp, its note's loudest nmax):
// each kept component's m and complex gain, strongest first (sidebands)
void sides_one(Scan &S, const Rev &R, double f, int depth, int band, int chorus, double md, double amp, double nmax,
               std::vector<double> &mm, std::vector<double> &cr, std::vector<double> &ci)
{
    double Pr[256], Pi[256], z[512], F[512], Cr[256], Ci[256], mag[256];
    const double kside = pow(10.0, -S.side_db / 20.0), kfloor = pow(10.0, -S.floor_db / 20.0);
    double w;
    scanned(S, R, f, depth, band, chorus, Pr, Pi, &w);
    for (int j = 0; j < 256; j++) {
        z[2 * j] = Pr[j];
        z[2 * j + 1] = Pi[j];
    }
    nv_cfft(z, 256, F);
    double x = (-w) * md, cm = cos(x), sm = sin(x);
    double mx = 0.0;
    for (int j = 0; j < 256; j++) {
        double Fr = F[2 * j] / 256.0, Fi = F[2 * j + 1] / 256.0;
        Cr[j] = Fr * cm - Fi * sm;
        Ci[j] = Fr * sm + Fi * cm;
        mag[j] = hypot(Cr[j], Ci[j]);
        mx = j ? std::max(mx, mag[j]) : mag[j];
    }
    std::vector<int> keep;
    for (int j = 0; j < 256; j++) {
        int m = j < 128 ? j : j - 256;          // fftfreq
        if (mag[j] > mx * kside && m != 0 && amp * mag[j] >= nmax * kfloor)
            keep.push_back(j);
    }
    std::stable_sort(keep.begin(), keep.end(), [&](int u, int v) { return -mag[u] < -mag[v]; });
    if ((int)keep.size() > S.max_side)
        keep.resize(S.max_side);
    for (int j : keep) {
        mm.push_back((double)(j < 128 ? j : j - 256));
        cr.push_back(Cr[j]);
        ci.push_back(Ci[j]);
    }
}

// the tables, loaded once per export
std::map<const double *, Scan> loaded;

Scan &scan_of(const double *X)
{
    auto it = loaded.find(X);
    if (it == loaded.end())
        it = loaded.emplace(X, load(X)).first;
    return it->second;
}

Rev make_rev(const Scan &S)
{
    Rev R;
    for (int j = 0; j < 256; j++) {
        R.th[j] = (double)j * 2.0 * M_PI / 256.0;
        crossfade(S, R.th[j], &R.a[j], &R.b[j], &R.eta[j]);
    }
    return R;
}

}  // namespace

extern "C" {

// LIVE'S SCANNER, one rank's data for one position (live._scan_prep): its
// partials' bands, dry and scanned gains (dry, sc: re, im each), and tier B's
// copies (their source rows, m and complex gain: *ns of them, malloc'd) -- the
// note's loudest its rows' by onset less room delay (note_peaks)
void nv_scan_prep(const double *X, long n, const float *nf, const float *aL, const float *aR, const long long *non,
                  const float *rdl, int depth, int chorus, double sr, int *band, double *dry, double *sc, long *ns,
                  long **src, double **mm, double **cc)
{
    Scan &S = scan_of(X);
    Rev R = make_rev(S);
    std::map<int, double> mdl;
    for (long q = 0; q < n; q++)
        gains_one(S, R, (double)nf[q], depth, chorus, mdl, &band[q], &dry[2 * q], &dry[2 * q + 1], &sc[2 * q],
                  &sc[2 * q + 1]);
    std::vector<long> so;
    std::vector<double> mo, co;
    if (S.sidebands && sr) {
        std::vector<double> amp(n), key(n);
        std::map<double, double> top;
        for (long q = 0; q < n; q++) {
            amp[q] = std::max(fabs((double)aL[q]), fabs((double)aR[q]));
            key[q] = (double)non[q] - (double)rdl[q];
            auto it = top.find(key[q]);
            if (it == top.end() || amp[q] > it->second)
                top[key[q]] = amp[q];
        }
        for (long q = 0; q < n; q++) {
            std::vector<double> m1, r1, i1;
            sides_one(S, R, (double)nf[q], depth, band[q], chorus, mdl[band[q]], amp[q], top[key[q]], m1, r1, i1);
            for (size_t j = 0; j < m1.size(); j++) {
                so.push_back(q);
                mo.push_back(m1[j]);
                co.push_back(r1[j]);
                co.push_back(i1[j]);
            }
        }
    }
    *ns = (long)so.size();
    *src = (long *)malloc(sizeof(long) * (so.size() + 1));
    *mm = (double *)malloc(sizeof(double) * (mo.size() + 1));
    *cc = (double *)malloc(sizeof(double) * (co.size() + 1));
    std::copy(so.begin(), so.end(), *src);
    std::copy(mo.begin(), mo.end(), *mm);
    std::copy(co.begin(), co.end(), *cc);
}

// THE SCANNER, ONE ROW (nv_scan_expand's body, a stream's): r on its band (no
// chorus) or its dry share (chorus); its copies into cp -- the scanned copy
// (chorus: *nch 1) then tier B's (*nsd, strongest first) -- from the row as it
// was; nmax its note's loudest (note_peaks); row0 the channel's band rows
void *nv_scan_new(const double *X)
{
    struct H {
        Scan *S;
        Rev R;
        std::map<std::array<int, 3>, double> mdl;
    };
    H *h = new H;
    h->S = &scan_of(X);
    h->R = make_rev(*h->S);
    return h;
}
void nv_scan_row(void *hv, double *r, int depth, int chorus, int row0, double nmax, double sr, double *cp, int *nch,
                 int *nsd)
{
    enum { cOM = 0, cP0 = 1, cP0R = 2, cAL = 3, cAR = 4, cAM = 5, cNF = 11, cBR = 41 };
    struct H {
        Scan *S;
        Rev R;
        std::map<std::array<int, 3>, double> mdl;
    };
    H &h = *(H *)hv;
    Scan &S = *h.S;
    const Rev &R = h.R;
    std::vector<double> Pr(256), Pi(256);
    const double f = r[cNF];
    const int band = band_of(S, f);
    double dre = 0.0, dim = 0.0;
    if (chorus) {
        const Tab &T = S.tab[1];
        double lf = log(std::max(f, T.fg[0]));
        double m = interp(lf, T.lg.data(), T.rm.data(), T.n, 1);
        double p = interp(lf, T.lg.data(), T.rp.data(), T.n, 1);
        dre = m * cos(p);
        dim = m * sin(p);
    }
    const std::array<int, 3> mk = {depth, band, chorus};
    if (!h.mdl.count(mk))
        h.mdl[mk] = mean_delay(S, depth, band, chorus);
    const double mdl = h.mdl[mk];
    double w;
    scanned(S, R, f, depth, band, chorus, Pr.data(), Pi.data(), &w);
    double c0r = npmean(Pr.data(), 256), c0i = npmean(Pi.data(), 256);
    double x = (-w) * mdl, cm = cos(x), sm = sin(x);
    const double sre = c0r * cm - c0i * sm, sim = c0r * sm + c0i * cm;
    std::vector<double> side;
    if (S.sidebands && sr) {
        const double amp = std::max(fabs(r[cAL]), fabs(r[cAR]));
        const double kside = pow(10.0, -S.side_db / 20.0), kfloor = pow(10.0, -S.floor_db / 20.0);
        std::vector<double> z(512), F(512), Cr(256), Ci(256), mag(256);
        double w2;
        scanned(S, R, f, depth, band, chorus, Pr.data(), Pi.data(), &w2);
        for (int j = 0; j < 256; j++) {
            z[2 * j] = Pr[j];
            z[2 * j + 1] = Pi[j];
        }
        nv_cfft(z.data(), 256, F.data());
        double x2 = (-w2) * mdl, cm2 = cos(x2), sm2 = sin(x2);
        double mx = 0.0;
        for (int j = 0; j < 256; j++) {
            double Fr = F[2 * j] / 256.0, Fi = F[2 * j + 1] / 256.0;
            Cr[j] = Fr * cm2 - Fi * sm2;
            Ci[j] = Fr * sm2 + Fi * cm2;
            mag[j] = hypot(Cr[j], Ci[j]);
            mx = j ? std::max(mx, mag[j]) : mag[j];
        }
        std::vector<int> keep;
        for (int j = 0; j < 256; j++) {
            int m = j < 128 ? j : j - 256;
            if (mag[j] > mx * kside && m != 0 && amp * mag[j] >= nmax * kfloor)
                keep.push_back(j);
        }
        std::stable_sort(keep.begin(), keep.end(), [&](int u, int v) { return -mag[u] < -mag[v]; });
        if ((int)keep.size() > S.max_side)
            keep.resize(S.max_side);
        for (int j : keep) {
            double mm = (double)(j < 128 ? j : j - 256);
            size_t o = side.size();
            side.insert(side.end(), r, r + NCOLS);
            double *e = side.data() + o;
            e[cOM] = e[cOM] + 2.0 * M_PI * S.hz / sr * mm;
            e[cNF] = e[cNF] + S.hz * mm;
            double g = hypot(Cr[j], Ci[j]), ang = atan2(Ci[j], Cr[j]);
            for (int c : {cAL, cAR, cAM})
                e[c] = e[c] * g;
            e[cP0] = e[cP0] + ang;
            e[cP0R] = e[cP0R] + ang;
            e[cBR] = (double)(row0 + band);
        }
    }
    const double gs = hypot(sre, sim), as = atan2(sim, sre);
    *nch = 0;
    if (!chorus) {
        for (int c : {cAL, cAR, cAM})
            r[c] = r[c] * gs;
        r[cP0] = r[cP0] + as;
        r[cP0R] = r[cP0R] + as;
        r[cBR] = (double)(row0 + band);
    } else {
        double *e = cp;
        memcpy(e, r, sizeof(double) * NCOLS);
        for (int c : {cAL, cAR, cAM})
            e[c] = e[c] * gs;
        e[cP0] = e[cP0] + as;
        e[cP0R] = e[cP0R] + as;
        e[cBR] = (double)(row0 + band);
        double gd = hypot(dre, dim), ad = atan2(dim, dre);
        for (int c : {cAL, cAR, cAM})
            r[c] = r[c] * gd;
        r[cP0] = r[cP0] + ad;
        r[cP0R] = r[cP0R] + ad;
        *nch = 1;
    }
    memcpy(cp + (size_t)NCOLS * *nch, side.data(), sizeof(double) * side.size());
    *nsd = (int)(side.size() / NCOLS);
}

// a band row's BC at two times (scanner.band_bc: live's _scanner_block)
void nv_scan_bc(const double *X, double t0, double t1, int depth, int band, int chorus, double sr, double *c)
{
    Scan &S = scan_of(X);
    double md = mean_delay(S, depth, band, chorus);
    for (int k = 0; k < 2; k++) {
        double th = 2.0 * M_PI * S.hz * (k ? t1 : t0);
        c[k] = -(delay(S, th, depth, band, chorus) - md) * sr;
    }
}

// THE SCANNER'S ROWS (scanner.rows) for a render nblk blocks long: a row per
// band -- BR (float32) and BC -- into br[6 * nblk], bc[6 * nblk]
void nv_scan_rows(const double *X, long nblk, int blk, double sr, int depth, int chorus, float *br, double *bc)
{
    Scan S = load(X);
    std::vector<double> b(nblk + 1);
    for (int band = 0; band < 6; band++) {
        double md = mean_delay(S, depth, band, chorus);
        for (long k = 0; k <= nblk; k++) {
            double t = (double)(k * (long)blk) / sr;
            double th = 2.0 * M_PI * S.hz * t;
            b[k] = -(delay(S, th, depth, band, chorus) - md) * sr;
        }
        for (long k = 0; k < nblk; k++) {
            br[band * nblk + k] = (float)(1.0 + (b[k + 1] - b[k]) / (double)blk);
            bc[band * nblk + k] = b[k];
        }
    }
}

// THE SCANNER over a table (scanner.expand): rows (NCOLS each, *Pp of them,
// realloc'd), the channels (chans[k]: its band rows from row0s[k], depth,
// chorus), in _SCAN_CH's order; a damper's dk/dg copied with any copy.
// Returns the copies made.
long long nv_scan_expand(const double *X, double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                         const int *row0s, const int *depths, const int *choruses, double sr)
{
    enum { cOM = 0, cP0 = 1, cP0R = 2, cAL = 3, cAR = 4, cAM = 5, cMCH = 6, cNF = 11, cNON = 12, cBR = 41,
           cRDL = 45 };
    Scan S = load(X);
    Rev R;
    for (int j = 0; j < 256; j++) {
        R.th[j] = (double)j * 2.0 * M_PI / 256.0;
        crossfade(S, R.th[j], &R.a[j], &R.b[j], &R.eta[j]);
    }
    const long long n = *Pp;
    std::vector<long long> mch(n), brc(n);
    for (long long i = 0; i < n; i++) {
        mch[i] = (long long)(*rowsp)[(size_t)NCOLS * i + cMCH];
        brc[i] = (long long)(*rowsp)[(size_t)NCOLS * i + cBR];
    }
    long long made = 0;
    for (int k = 0; k < nch; k++) {
        std::vector<long long> sel;
        for (long long i = 0; i < n; i++)
            if (mch[i] == chans[k] && brc[i] < 0)
                sel.push_back(i);
        if (sel.empty())
            continue;
        const int depth = depths[k], chorus = choruses[k];
        double *rows = *rowsp;
        size_t ns = sel.size();
        auto at = [&](size_t q, int c) { return rows[(size_t)NCOLS * sel[q] + c]; };
        // gains: each partial's band, the dry share (the rail's) and the scanned path's mean
        std::vector<int> band(ns);
        std::vector<double> dre(ns, 0.0), dim(ns, 0.0), sre(ns), sim(ns);
        std::vector<double> Pr(256), Pi(256);
        std::map<int, double> mdl;
        for (size_t q = 0; q < ns; q++) {
            double f = at(q, cNF);
            band[q] = band_of(S, f);
            if (chorus) {
                const Tab &T = S.tab[1];
                double lf = log(std::max(f, T.fg[0]));
                double m = interp(lf, T.lg.data(), T.rm.data(), T.n, 1);
                double p = interp(lf, T.lg.data(), T.rp.data(), T.n, 1);
                dre[q] = m * cos(p);
                dim[q] = m * sin(p);
            }
            if (!mdl.count(band[q]))
                mdl[band[q]] = mean_delay(S, depth, band[q], chorus);
            double w;
            scanned(S, R, f, depth, band[q], chorus, Pr.data(), Pi.data(), &w);
            double c0r = npmean(Pr.data(), 256), c0i = npmean(Pi.data(), 256);
            double x = (-w) * mdl[band[q]], cm = cos(x), sm = sin(x);
            sre[q] = c0r * cm - c0i * sm;
            sim[q] = c0r * sm + c0i * cm;
        }
        // tier B's copies (_side_copies), from the rows as they were
        std::vector<double> side;
        if (S.sidebands && sr) {
            // note_peaks: each row's level, its note's loudest (by onset less its delay)
            std::vector<double> amp(ns), key(ns), nmax(ns);
            for (size_t q = 0; q < ns; q++) {
                amp[q] = std::max(fabs(at(q, cAL)), fabs(at(q, cAR)));
                key[q] = at(q, cNON) - at(q, cRDL);
            }
            std::map<double, double> top;
            for (size_t q = 0; q < ns; q++) {
                auto it = top.find(key[q]);
                if (it == top.end() || amp[q] > it->second)
                    top[key[q]] = amp[q];
            }
            for (size_t q = 0; q < ns; q++)
                nmax[q] = top[key[q]];
            const double kside = pow(10.0, -S.side_db / 20.0), kfloor = pow(10.0, -S.floor_db / 20.0);
            std::vector<double> z(512), F(512), Cr(256), Ci(256), mag(256);
            for (size_t q = 0; q < ns; q++) {
                double f = at(q, cNF), w;
                scanned(S, R, f, depth, band[q], chorus, Pr.data(), Pi.data(), &w);
                for (int j = 0; j < 256; j++) {
                    z[2 * j] = Pr[j];
                    z[2 * j + 1] = Pi[j];
                }
                nv_cfft(z.data(), 256, F.data());
                double x = (-w) * mdl[band[q]], cm = cos(x), sm = sin(x);
                double mx = 0.0;
                for (int j = 0; j < 256; j++) {
                    double Fr = F[2 * j] / 256.0, Fi = F[2 * j + 1] / 256.0;
                    Cr[j] = Fr * cm - Fi * sm;
                    Ci[j] = Fr * sm + Fi * cm;
                    mag[j] = hypot(Cr[j], Ci[j]);
                    mx = j ? std::max(mx, mag[j]) : mag[j];
                }
                std::vector<int> keep;
                for (int j = 0; j < 256; j++) {
                    int m = j < 128 ? j : j - 256;          // fftfreq
                    if (mag[j] > mx * kside && m != 0 && amp[q] * mag[j] >= nmax[q] * kfloor)
                        keep.push_back(j);
                }
                std::stable_sort(keep.begin(), keep.end(), [&](int u, int v) { return -mag[u] < -mag[v]; });
                if ((int)keep.size() > S.max_side)
                    keep.resize(S.max_side);
                for (int j : keep) {
                    double mm = (double)(j < 128 ? j : j - 256);
                    size_t o = side.size();
                    side.insert(side.end(), rows + (size_t)NCOLS * sel[q], rows + (size_t)NCOLS * (sel[q] + 1));
                    double *e = side.data() + o;
                    e[cOM] = e[cOM] + 2.0 * M_PI * S.hz / sr * mm;
                    e[cNF] = e[cNF] + S.hz * mm;
                    double g = hypot(Cr[j], Ci[j]), ang = atan2(Ci[j], Cr[j]);
                    for (int c : {cAL, cAR, cAM})
                        e[c] = e[c] * g;
                    e[cP0] = e[cP0] + ang;
                    e[cP0R] = e[cP0R] + ang;
                    e[cBR] = (double)(row0s[k] + band[q]);
                }
            }
        }
        // the rows themselves: on vibrato the scanned path on the band row;
        // on chorus the dry share, and a copy the scanned
        std::vector<double> copies;
        for (size_t q = 0; q < ns; q++) {
            double *r = rows + (size_t)NCOLS * sel[q];
            double gs = hypot(sre[q], sim[q]), as = atan2(sim[q], sre[q]);
            if (!chorus) {
                for (int c : {cAL, cAR, cAM})
                    r[c] = r[c] * gs;
                r[cP0] = r[cP0] + as;
                r[cP0R] = r[cP0R] + as;
                r[cBR] = (double)(row0s[k] + band[q]);
                continue;
            }
            size_t o = copies.size();
            copies.insert(copies.end(), r, r + NCOLS);
            double *e = copies.data() + o;
            for (int c : {cAL, cAR, cAM})
                e[c] = e[c] * gs;
            e[cP0] = e[cP0] + as;
            e[cP0R] = e[cP0R] + as;
            e[cBR] = (double)(row0s[k] + band[q]);
            double gd = hypot(dre[q], dim[q]), ad = atan2(dim[q], dre[q]);
            for (int c : {cAL, cAR, cAM})
                r[c] = r[c] * gd;
            r[cP0] = r[cP0] + ad;
            r[cP0R] = r[cP0R] + ad;
        }
        copies.insert(copies.end(), side.begin(), side.end());
        long long m = (long long)(copies.size() / NCOLS);
        if (!m)
            continue;
        long long P0 = *Pp;
        rows = (double *)realloc(*rowsp, sizeof(double) * NCOLS * (size_t)(P0 + m));
        memcpy(rows + (size_t)NCOLS * P0, copies.data(), sizeof(double) * copies.size());
        *rowsp = rows;
        if (dm[0]) {
            // (no damper rides an organ: the tracks' rows carried as none)
            int32_t *dk = (int32_t *)realloc(dm[0], sizeof(int32_t) * (size_t)(P0 + m));
            float *dg = (float *)realloc(dm[1], sizeof(float) * (size_t)(P0 + m));
            for (long long q = 0; q < m; q++) {
                dk[P0 + q] = -1;
                dg[P0 + q] = 0.0f;
            }
            dm[0] = dk;
            dm[1] = dg;
        }
        *Pp = P0 + m;
        made += m;
    }
    return made;
}

}  // extern "C"
