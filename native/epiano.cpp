// epiano.cpp -- AN ELECTRIC PIANO'S PICKUP LAYERS (tonelib.
// ElectricPianoProperties._pickup_layers): the tine's (the reed's) swing a
// sinusoid decaying as A0 x, x = e^{-Dt} (a wide swing faster: swing_damping),
// read through the pickup's flux curve -- the Rhodes' point tip over its
// magnet's frustum on an arc, the Wurlitzer's slot -- and each harmonic's
// signed level along that decay fitted, greedily, as a sum of terms x^n.
// tonelib.py calls this itself (native.ep_layers), so the two renderers'
// electric pianos are one arithmetic: libm, plain sums, a Householder solve
// of the fit's least squares (in place of numpy's lstsq on the normal
// equations, which is LAPACK's and the machine's).

#include <algorithm>
#include <cmath>
#include <map>
#include <mutex>
#include <set>
#include <vector>

namespace {

// the pickup's flux at u (units of the field's width); kind 1 the Rhodes
// (p: offset, gap, side, side depth, tine arc; op the key's octave), kind 2
// the Wurlitzer (p: offset, slot p, slot q); control: flux = u
struct Flux {
    int kind, control;
    const double *p;
    double op;
    // the Rhodes' face: its profile, sampled (RhodesProperties._face)
    std::vector<double> fx, fh;
    double fdx = 0.0, r = 0.0, g = 0.0, norm = 1.0;

    Flux(int kind_, const double *p_, double op_, int control_) : kind(kind_), control(control_), p(p_), op(op_)
    {
        if (kind != 1 || control)
            return;
        double sd = std::max(p[2], 0.05), e = 1.0 + sd, depth = std::max(p[3], 0.0);
        const int n = 241;
        double step = (2.0 * e) / (double)(n - 1);
        for (int i = 0; i < n; i++) {
            double x = i == n - 1 ? e : (double)i * step + -e;      // np.linspace(-e, e, 241)
            double t = (fabs(x) - 1.0) / sd;
            t = t < 0.0 ? 0.0 : (t > 1.0 ? 1.0 : t);
            fx.push_back(x);
            fh.push_back(-depth * t);
        }
        fdx = fx[1] - fx[0];
        r = std::max(p[4], 2.0) * pow(2.0, -0.5 * op);
        g = std::max(p[1], 0.02);
        norm = field(0.0, g);
    }
    // the face's charge sheet's B_z at (X, Z) (RhodesProperties._field)
    double field(double X, double Z) const
    {
        double s = 0.0;
        for (size_t i = 0; i < fx.size(); i++) {
            double dz = Z - fh[i], dx = X - fx[i];
            double v = dx * dx + dz * dz;
            s += dz / (v * sqrt(v));
        }
        return s * fdx;
    }
    double operator()(double u) const
    {
        if (control)
            return u;
        if (kind == 2)
            return pow(1.0 + pow(fabs(u), p[1]), -p[2]);
        double d = u - p[0], lim = 0.999 * r;
        d = d < -lim ? -lim : (d > lim ? lim : d);
        double z = g + r - sqrt(r * r - d * d);
        return field(u, z) / norm;
    }
};

// min ||P w - b||^2 + lam ||w||^2 for P m x J: Householder on [P; sqrt(lam) I]
void solve_ls(const std::vector<double> &P, const std::vector<double> &b, int m, int J, double lam, double *w)
{
    int M = m + J;
    std::vector<double> A((size_t)M * J, 0.0), y(M, 0.0);
    for (int i = 0; i < m; i++) {
        for (int j = 0; j < J; j++)
            A[(size_t)i * J + j] = P[(size_t)i * J + j];
        y[i] = b[i];
    }
    double sl = sqrt(lam);
    for (int j = 0; j < J; j++)
        A[(size_t)(m + j) * J + j] = sl;
    for (int j = 0; j < J; j++) {
        double nrm = 0.0;
        for (int i = j; i < M; i++)
            nrm += A[(size_t)i * J + j] * A[(size_t)i * J + j];
        nrm = sqrt(nrm);
        if (nrm == 0.0)
            continue;
        double a0 = A[(size_t)j * J + j], alpha = a0 > 0.0 ? -nrm : nrm;
        std::vector<double> v(M, 0.0);
        v[j] = a0 - alpha;
        for (int i = j + 1; i < M; i++)
            v[i] = A[(size_t)i * J + j];
        double vv = 0.0;
        for (int i = j; i < M; i++)
            vv += v[i] * v[i];
        if (vv == 0.0)
            continue;
        for (int c = j; c < J; c++) {
            double s = 0.0;
            for (int i = j; i < M; i++)
                s += v[i] * A[(size_t)i * J + c];
            s = 2.0 * s / vv;
            for (int i = j; i < M; i++)
                A[(size_t)i * J + c] -= s * v[i];
        }
        double s = 0.0;
        for (int i = j; i < M; i++)
            s += v[i] * y[i];
        s = 2.0 * s / vv;
        for (int i = j; i < M; i++)
            y[i] -= s * v[i];
    }
    for (int j = J - 1; j >= 0; j--) {
        double s = y[j];
        for (int c = j + 1; c < J; c++)
            s -= A[(size_t)j * J + c] * w[c];
        double d = A[(size_t)j * J + j];
        w[j] = d != 0.0 ? s / d : 0.0;
    }
}

}  // namespace

extern "C" {

// The layers for one note: out[4 q..4 q + 3] = (k, n, w, phase), harmonic k's
// envelope the sum of its w x^n, its phase in the wave (the coil's -dPhi/dt,
// as cos(k theta + phase)); returns how many (at most cap). p: the flux's
// parameters (Flux); a0 the swing at the strike, rho the wide swing's extra
// damping; f0 the key's pitch and op its octave (the Rhodes' arc); harmonics,
// terms, max_hz, floor_db: pickup_harmonics, pickup_layer_terms,
// pickup_max_hz (0 none) and pickup_floor_db
int nv_ep_layers(int kind, const double *p, double a0, double rho, double f0, double op, int harmonics, int terms,
                 double max_hz, double floor_db, int control, double *out, int cap)
{
    Flux flux(kind, p, op, control);
    const int nx = 64, nt = 256;
    // the swing as it decays, sampled geometrically in time from the strike:
    // x = exp(-[0, geomspace(1e-4, 7, 63)])
    double xs[nx];
    xs[0] = 1.0;
    {
        double l0 = log10(1e-4), l1 = log10(7.0), st = (l1 - l0) / 62.0;
        for (int i = 0; i < 63; i++) {
            double t = i == 0 ? 1e-4 : (i == 62 ? 7.0 : pow(10.0, (double)i * st + l0));
            xs[i + 1] = exp(-t);
        }
    }
    std::vector<double> th(nt), sn(nt);
    for (int j = 0; j < nt; j++) {
        th[j] = 2.0 * M_PI * (double)j / (double)nt;
        sn[j] = sin(th[j]);
    }
    std::vector<double> F((size_t)nx * nt);
    for (int i = 0; i < nx; i++) {
        double sw = a0 * xs[i] / sqrt(1.0 + rho * a0 * a0 * (1.0 - xs[i] * xs[i]));
        for (int j = 0; j < nt; j++)
            F[(size_t)i * nt + j] = flux(p[0] + sw * sn[j]);
    }
    int kmax = harmonics;
    if (max_hz != 0.0)
        kmax = std::max(1, std::min(kmax, (int)(max_hz / f0)));
    const int J = terms;
    std::vector<double> pin(nx, 1.0);
    pin[0] = 30.0;
    struct Lay { int k; double n, w, ph; };
    std::vector<Lay> layers;
    std::vector<double> cr(nx), ci(nx), sgn(nx), cs(nt), sk(nt);
    for (int k = 1; k <= kmax; k++) {
        for (int j = 0; j < nt; j++) {
            cs[j] = cos((double)k * th[j]);
            sk[j] = sin((double)k * th[j]);
        }
        for (int i = 0; i < nx; i++) {
            double re = 0.0, im = 0.0;
            for (int j = 0; j < nt; j++) {
                re += F[(size_t)i * nt + j] * cs[j];
                im -= F[(size_t)i * nt + j] * sk[j];
            }
            cr[i] = re / nt * 2.0;
            ci[i] = im / nt * 2.0;
        }
        double rr = cr[0], ri = ci[0];
        if (!(hypot(rr, ri) > 1e-15)) {
            int best = 0;
            for (int i = 1; i < nx; i++)
                if (hypot(cr[i], ci[i]) > hypot(cr[best], ci[best]))
                    best = i;
            rr = cr[best];
            ri = ci[best];
        }
        double ra = std::max(hypot(rr, ri), 1e-30);
        for (int i = 0; i < nx; i++)
            sgn[i] = (cr[i] * rr + ci[i] * ri) / ra;            // Re(c conj(ref)) / |ref|
        // which powers: the series' own (k, k+2...), slower and faster ones
        std::set<double> cset;
        for (int j = 0; j < J; j++)
            cset.insert((double)(k + 2 * j));
        for (int i = 1; i < 6; i++)
            cset.insert(std::max(1.0, (double)k / pow(2.0, i)));
        for (int i = 1; i < 4; i++)
            cset.insert((double)k * pow(2.0, i));
        std::vector<double> cands(cset.begin(), cset.end()), chosen, w;
        std::vector<double> b(nx);
        for (int i = 0; i < nx; i++)
            b[i] = sgn[i] * pin[i];
        for (int it = 0; it < J; it++) {
            double br = 0.0, bn = 0.0;
            bool have = false;
            std::vector<double> bw;
            for (double n : cands) {
                if (std::find(chosen.begin(), chosen.end(), n) != chosen.end())
                    continue;
                std::vector<double> ns(chosen);
                ns.push_back(n);
                int m = (int)ns.size();
                std::vector<double> P((size_t)nx * m), ww(m);
                for (int i = 0; i < nx; i++)
                    for (int c = 0; c < m; c++)
                        P[(size_t)i * m + c] = pow(xs[i], ns[c]) * pin[i];
                solve_ls(P, b, nx, m, 1e-9, ww.data());
                double r = 0.0;
                for (int i = 0; i < nx; i++) {
                    double s = 0.0;
                    for (int c = 0; c < m; c++)
                        s += P[(size_t)i * m + c] * ww[c];
                    r += (s - b[i]) * (s - b[i]);
                }
                if (!have || r < br) {
                    have = true;
                    br = r;
                    bn = n;
                    bw = ww;
                }
            }
            if (!have)
                break;
            chosen.push_back(bn);
            w = bw;
        }
        double ph = atan2(rr, -ri);                             // angle(1j ref)
        std::vector<int> ord(chosen.size());
        for (size_t q = 0; q < ord.size(); q++)
            ord[q] = (int)q;
        std::sort(ord.begin(), ord.end(), [&](int a, int b2) { return chosen[a] < chosen[b2]; });
        for (int q : ord)
            layers.push_back({k, chosen[q], (double)k * w[q], ph});
    }
    // the floor drops a HARMONIC, never one of its layers
    std::map<int, double> lev;
    for (const Lay &q : layers)
        lev[q.k] += q.w;
    double top = 0.0;
    for (auto &kv : lev)
        top = std::max(top, fabs(kv.second));
    if (top == 0.0)
        top = 1.0;
    double floor = top * pow(10.0, floor_db / 20.0);
    int n = 0;
    for (const Lay &q : layers)
        if (fabs(lev[q.k]) >= floor) {
            if (n < cap) {
                out[4 * n] = q.k;
                out[4 * n + 1] = q.n;
                out[4 * n + 2] = q.w;
                out[4 * n + 3] = q.ph;
            }
            n++;
        }
    return n;
}

// ...each note's once (a key's every template, every velocity bucket): the
// layers into out, how many returned
int nv_ep_layers_cached(int kind, const double *p, double a0, double rho, double f0, double op, int harmonics,
                        int terms, double max_hz, double floor_db, int control, double *out, int cap)
{
    static std::mutex mu;
    static std::map<std::vector<double>, std::vector<double>> got;
    int np = kind == 1 ? 5 : 3;
    std::vector<double> key(p, p + np);
    key.insert(key.end(), {(double)kind, a0, rho, f0, op, (double)harmonics, (double)terms, max_hz, floor_db,
                           (double)control});
    {
        std::lock_guard<std::mutex> lk(mu);
        auto it = got.find(key);
        if (it != got.end()) {
            int n = (int)it->second.size() / 4;
            std::copy(it->second.begin(), it->second.begin() + 4 * std::min(n, cap), out);
            return n;
        }
    }
    std::vector<double> buf(4 * 512);
    int n = nv_ep_layers(kind, p, a0, rho, f0, op, harmonics, terms, max_hz, floor_db, control, buf.data(), 512);
    n = std::min(n, 512);
    std::lock_guard<std::mutex> lk(mu);
    got[key] = std::vector<double>(buf.begin(), buf.begin() + 4 * n);
    std::copy(buf.begin(), buf.begin() + 4 * std::min(n, cap), out);
    return n;
}

}  // extern "C"
