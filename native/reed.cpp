// reed.cpp -- A FREE REED'S FLOW SPECTRUM (tonelib.FreeReedProperties.
// _reed_series): the tongue's swing a sinusoid, the air through the slot
// while it is clear (a smoothstep crossing reed_edge wide, plus the leak
// reed_direct), its spectrum's power averaged over reed_points gate positions
// across +- reed_spread, each harmonic's magnitude over the fundamental's.
// tonelib.py calls this itself (native.reed_series), so the two renderers'
// reeds are one arithmetic: the shared FFT (tubeamp.cpp's nv_rfft), libm's
// sin and hypot, numpy's linspace.

#include <cmath>
#include <cstdlib>
#include <map>
#include <mutex>
#include <tuple>
#include <vector>

extern "C" int nv_rfft(const double *x, long n, double *out);
extern "C" void *nv_npy_new(unsigned long long seed);
extern "C" double nv_npy_next(void *g);
extern "C" void nv_npy_free(void *g);

extern "C" {

// The series for one geometry: out[0..top] (top = min(max_harmonic, 4096)),
// harmonic k's magnitude over the fundamental's; returns top + 1
int nv_reed_series(double gate, double edge, double spread, int points, int max_harmonic, double direct, double *out)
{
    const long n = 1L << 13;
    std::vector<double> u(n), a(n), R(2 * (n / 2 + 1)), power(n / 2 + 1, 0.0);
    for (long i = 0; i < n; i++)
        u[i] = sin(2.0 * M_PI * ((double)i / (double)n));
    // the gates: np.linspace(gate - spread, gate + spread, points), its last exactly the stop
    std::vector<double> gates;
    if (spread > 0.0 && points > 1) {
        double start = gate - spread, stop = gate + spread, step = (stop - start) / (double)(points - 1);
        for (int k = 0; k < points; k++)
            gates.push_back((double)k * step + start);
        gates.back() = stop;
    } else {
        gates.push_back(gate);
    }
    double ed = edge > 1e-6 ? edge : 1e-6;
    for (double g0 : gates) {
        for (long i = 0; i < n; i++) {
            double x = (u[i] - g0) / ed + 0.5;
            x = x < 0.0 ? 0.0 : (x > 1.0 ? 1.0 : x);
            a[i] = u[i] * (x * x * (3.0 - 2.0 * x)) + direct * u[i];
        }
        nv_rfft(a.data(), n, R.data());
        for (long k = 0; k <= n / 2; k++) {
            double m = hypot(R[2 * k], R[2 * k + 1]) / (double)n;
            power[k] += m * m;
        }
    }
    long len = n / 2 + 1;
    int top = (int)(max_harmonic < len - 1 ? max_harmonic : len - 1);
    double ng = (double)gates.size();
    double m1 = sqrt(power[1] / ng);
    double ref = m1 > 0 ? m1 : 1.0;
    for (int k = 0; k <= top; k++)
        out[k] = sqrt(power[k] / ng) / ref;
    return top + 1;
}

// THE PLAYER'S BREATH on a channel (blockrender._prep_breath and
// _prep_breath_rows): slow noises (one pole at each corner, numpy's
// default_rng(seed)'s normals) for the tone's level, the breath noise's
// (partly the tone's) and the pitch (partly the tone's) -- p: wobble dB and
// Hz, the noise's dB, Hz and share, the pitch's cents, Hz and share -- as two
// rows: the pitch's ratio a block and its phase (br, bc: nblk) with the
// tone's level at the block edges (tl: nblk + 1), and the noise's level (nl)
void nv_breath_rows(unsigned long long seed, long nblk, int blk, double sr, const double *p, float *br, double *bc,
                    float *tl, float *nl)
{
    void *g = nv_npy_new(seed);
    auto wander = [&](double fc, std::vector<double> &y) {
        double a = exp(-2.0 * M_PI * fc * blk / sr);
        double b = sqrt(1.0 - a * a);
        std::vector<double> z(nblk + 1);
        for (long i = 0; i <= nblk; i++)
            z[i] = nv_npy_next(g);
        y.assign(nblk + 1, 0.0);
        y[0] = z[0];
        for (long i = 1; i <= nblk; i++)
            y[i] = a * y[i - 1] + b * z[i];
    };
    std::vector<double> tz, w2, w3;
    wander(p[1], tz);
    wander(p[3], w2);
    double sh = p[4], ps = p[7];
    double cn = sqrt(1.0 - sh * sh > 0.0 ? 1.0 - sh * sh : 0.0), cp = sqrt(1.0 - ps * ps > 0.0 ? 1.0 - ps * ps : 0.0);
    std::vector<double> nz(nblk + 1);
    for (long i = 0; i <= nblk; i++)
        nz[i] = sh * tz[i] + cn * w2[i];
    wander(p[6], w3);
    std::vector<double> pz(nblk + 1);
    for (long i = 0; i <= nblk; i++)
        pz[i] = ps * tz[i] + cp * w3[i];
    nv_npy_free(g);
    for (long i = 0; i <= nblk; i++) {
        tl[i] = (float)pow(10.0, p[0] * tz[i] / 20.0);
        nl[i] = (float)pow(10.0, p[2] * nz[i] / 20.0);
    }
    double c = 0.0;
    for (long i = 0; i < nblk; i++) {
        double pzb = 0.5 * (pz[i] + pz[i + 1]);
        br[i] = (float)pow(2.0, p[5] * pzb / 1200.0);
        bc[i] = c;
        c += ((double)br[i] - 1.0) * (double)blk;
    }
}

// ...each geometry once (a key's every velocity, every template): the series
// into out, its length returned
int nv_reed_series_cached(double gate, double edge, double spread, int points, int max_harmonic, double direct,
                          double *out)
{
    static std::mutex mu;
    static std::map<std::tuple<double, double, double, int, int, double>, std::vector<double>> got;
    auto key = std::make_tuple(gate, edge, spread, points, max_harmonic, direct);
    {
        std::lock_guard<std::mutex> lk(mu);
        auto it = got.find(key);
        if (it != got.end()) {
            std::copy(it->second.begin(), it->second.end(), out);
            return (int)it->second.size();
        }
    }
    int n = nv_reed_series(gate, edge, spread, points, max_harmonic, direct, out);
    std::lock_guard<std::mutex> lk(mu);
    got[key] = std::vector<double>(out, out + n);
    return n;
}

}  // extern "C"
