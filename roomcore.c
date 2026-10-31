/* roomcore.c -- the room's reflections, in C (tonelib.SynthProperties).
 *
 * reflection_terms, operation for operation: for each image source (found
 * by image_sources, in Python), its gain against the direct sound -- the
 * instrument's directivity toward where the ray left (a piston, 2 J1(x)/x),
 * what each surface kept (absorption and scattering, interpolated over
 * octave bands), the longer path's spreading and the air's absorption (ISO
 * 9613-1) -- and its extra delay; kept where it is over the floor and
 * inside the fusion limit. Python's float arithmetic and math functions are
 * these libm calls in this order (x ** y is pow, max/min keep the first of
 * equals, sum() is CPython's compensated sum), built without fused multiply-adds or
 * -ffast-math: bit-identical, so the table is checked by identity.
 *
 * THE ROOM, as numbers (tonelib._room_pack):
 *   R[0] radiation_distance   R[1] directivity_radius  R[2] directivity_floor
 *   R[3] directivity_axis_deg R[4] sound_speed         R[5] reflection_floor_db
 *   R[6] reflection_fusion_s  R[7] air_temperature_c   R[8] air_pressure_kpa
 *   R[9] air_humidity_pct
 *   AHZ[6]: the octave bands (_ALPHA_HZ); ALPHA[6*6], SCAT[6*6]: per surface
 *   (left right back front floor ceiling, WALLS' order), per band.
 */
#include <math.h>

#define PI 3.141592653589793

static double air_db(const double *R, double frequency)
{
    double T = R[7] + 273.15;
    double T0 = 293.15, T01 = 273.16;
    double pa = R[8] / 101.325;
    double psat = pow(10.0, -6.8346 * pow(T01 / T, 1.261) + 4.6151);
    double h = R[9] * psat / pa;
    double frO = pa * (24.0 + 4.04e4 * h * (0.02 + h) / (0.391 + h));
    double frN = pa * pow(T / T0, -0.5) * (9.0 + 280.0 * h
                                           * exp(-4.170 * (pow(T / T0, -1.0 / 3.0) - 1.0)));
    double f2 = frequency * frequency;
    return 8.686 * f2 * (
        1.84e-11 / pa * pow(T / T0, 0.5)
        + pow(T / T0, -2.5) * (0.01275 * exp(-2239.1 / T) / (frO + f2 / frO)
                               + 0.1068 * exp(-3352.0 / T) / (frN + f2 / frN)));
}

static double octave_interp(const double *AHZ, const double *table, double frequency)
{
    double f = AHZ[0] > frequency ? AHZ[0] : frequency;         /* max(frequency, lo) */
    f = AHZ[5] < f ? AHZ[5] : f;                                  /* min(f, hi) */
    for (int i = 0; i < 5; i++) {
        double lo = AHZ[i], hi = AHZ[i + 1];
        if (f <= hi) {
            double t = (log(f) - log(lo)) / (log(hi) - log(lo));
            return table[i] + t * (table[i + 1] - table[i]);
        }
    }
    return table[5];
}

static double surface_reflection(const double *AHZ, const double *ALPHA, const double *SCAT,
                                 int s, double frequency)
{
    double alpha = octave_interp(AHZ, ALPHA + 6 * s, frequency);
    double scat = octave_interp(AHZ, SCAT + 6 * s, frequency);
    double a = 1.0 - alpha, b = 1.0 - scat;
    return sqrt(a > 0.0 ? a : 0.0) * sqrt(b > 0.0 ? b : 0.0);   /* max(0.0, x) */
}

/* sum() of three floats as CPython 3.12+ adds them: from the first, then
 * Neumaier's compensated summation, the compensation added at the end */
static double pysum3(double x0, double x1, double x2)
{
    double f = x0, c = 0.0, xs[2] = {x1, x2};
    for (int i = 0; i < 2; i++) {
        double x = xs[i], t = f + x;
        if (fabs(f) >= fabs(x))
            c += (f - t) + x;
        else
            c += (x - t) + f;
        f = t;
    }
    if (c != 0.0 && isfinite(c))
        f += c;
    return f;
}

static double bessel_j1(double x)
{
    if (x < 3.0) {
        double t = x / 3.0;
        double t2 = t * t;
        return x * (0.5 + t2 * (-0.56249985 + t2 * (0.21093573 + t2 * (
            -0.03954289 + t2 * (0.00443319 + t2 * (-0.00031761 + t2 * 0.00001109))))));
    }
    double t = 3.0 / x;
    double f1 = (0.79788456 + t * (0.00000156 + t * (0.01659667 + t * (0.00017105 + t * (
        -0.00249511 + t * (0.00113653 + t * -0.00020033))))));
    double th = (x - 2.35619449 + t * (0.12499612 + t * (0.00005650 + t * (-0.00637879 + t * (
        0.00074348 + t * (0.00079824 + t * -0.00029166))))));
    return f1 * cos(th) / sqrt(x);
}

static double off_axis_angle(const double *R, double x, double z)
{
    double d = R[0];
    double psi = R[3] * PI / 180.0;
    double norm = sqrt(x * x + d * d + z * z);
    if (norm == 0.0)
        norm = 1.0;                                               /* `or 1.0` */
    double c = (-x * sin(psi) + d * cos(psi)) / norm;
    c = c < 1.0 ? c : 1.0;                                        /* min(1.0, c) */
    c = c > -1.0 ? c : -1.0;                                      /* max(-1.0, .) */
    return acos(c);
}

static double directivity_gain(const double *R, double frequency, double x, double z, double radius,
                               int has_radius)
{
    double a = has_radius ? radius : R[1];
    if (a <= 0.0)
        return 1.0;
    double theta = off_axis_angle(R, x, z);
    double xx = fabs(2.0 * PI * frequency / R[4] * a * sin(theta));
    if (xx < 1e-6)
        return 1.0;
    double v = fabs(2.0 * bessel_j1(xx) / xx);
    return R[2] > v ? R[2] : v;                                    /* max(v, floor) */
}

/* tonelib.reflection_terms over the n images image_sources found: nsurf[k]
 * surfaces each, their indices in surf[] (concatenated), the image at
 * img[3k..3k+2], the mirrored listener at mir[3k..3k+2]. Writes, for the
 * kept images in order, their index (keep), gain and delay; returns how
 * many. radius: has_radius 0 is None (the class's own). */
int reflection_terms(const double *R, const double *AHZ, const double *ALPHA, const double *SCAT,
                     double frequency, double sx, double sy, double sz, double radius, int has_radius,
                     int n, const int *nsurf, const int *surf, const double *img, const double *mir,
                     int *keep, double *gain, double *delay)
{
    double direct = sqrt(sx * sx + sy * sy + sz * sz);
    if (direct == 0.0)
        direct = 1e-9;
    double direct_dir = directivity_gain(R, frequency, sx, sz, radius, has_radius);
    if (direct_dir == 0.0)
        direct_dir = 1e-9;
    double air = air_db(R, frequency);
    double floor_ = pow(10.0, R[5] / 20.0);
    int out = 0, si = 0;
    for (int k = 0; k < n; k++) {
        const double *im = img + 3 * k, *mr = mir + 3 * k;
        double path = sqrt(pysum3(im[0] * im[0], im[1] * im[1], im[2] * im[2]));
        if (path == 0.0)
            path = 1e-9;
        double dm = sqrt(pysum3(pow(mr[0] - sx, 2.0), pow(mr[1] - sy, 2.0), pow(mr[2] - sz, 2.0)));
        if (dm == 0.0)
            dm = 1e-9;
        double scale = direct / dm;
        double ax = (mr[0] - sx) * scale;
        double az = (mr[2] - sz) * scale;
        double depart = directivity_gain(R, frequency, ax, az, radius, has_radius);
        double kept = 1.0;
        for (int q = 0; q < nsurf[k]; q++)
            kept *= surface_reflection(AHZ, ALPHA, SCAT, surf[si + q], frequency);
        si += nsurf[k];
        double g = ((direct / path)
                    * kept
                    * (depart / direct_dir)
                    * pow(10.0, -(air * (path - direct)) / 20.0));
        if (g < floor_)
            continue;
        double dl = (path - direct) / R[4];
        if (R[6] != 0.0 && dl > R[6])
            continue;
        keep[out] = k;
        gain[out] = g;
        delay[out] = dl;
        out++;
    }
    return out;
}
