// tuner.cpp -- the tuners: blockrender.tuning_table(name) with no Python.
//
// A tuner here is a 128-key table, which is all the renderers ever ask of
// one: midilib.set_tuner's name -- a registry name, then optionally @KEY and
// :A4 (`hybrid@D:466`), or Indian intonation, raga:<system>[/<raga>]@<Sa>
// [:<Sa Hz>] -- and every key's frequency as tunelib's class gives it, at
// tunelib.set_reference's pitch when one is in force (or name~Hz: A4 there). What each class starts
// from is the data in tunertables.h (examples/tuner_tables.py writes it from
// the Python); what it does with it is here, operation for operation:
//
//   the twelve-tone tuners  (TwelveTuner) C from A over the ratio for A4,
//                           each key C times its interval, an octave out
//                           (2 * stretch) at a time
//   the path tuners         (PathTuner) the generator's table rescaled so A4
//                           lands on A; on pure octaves (HybridHarmonic: one
//                           octave from C4, repeated by 2:1); the mean-third
//                           chains (HybridMean); a key outside the table by
//                           pure octaves from the nearest one; @KEY (in_key:
//                           moved, A4 kept) and :A4 (at_pitch) on these only
//   the procedure tuners    (PleyelTuner) the procedure's table, the fork's
//                           key at A times its share (or the reference)
//   `dynamic`               its search's table, as it comes (the search reads
//                           no reference, so neither does this)
//   ragas                   (ragas.table) Sa at its key in the octave from
//                           middle C, each key Sa times its swara's cents
//
// Bit for bit blockrender.tuning_table's (examples/tuner_check.py): libm's
// pow, log and sqrt where Python calls them, its order of operations.

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>

#include "tunertables.h"

namespace nv {
namespace tuner {

typedef std::map<int, double> Table;

static int key_of(const std::string &k)
{
    static const char *K[] = {"c", "c#", "db", "d", "d#", "eb", "e", "f", "f#", "gb", "g", "g#", "ab", "a",
                              "a#", "bb", "b"};
    static const int V[] = {0, 1, 1, 2, 3, 3, 4, 5, 6, 6, 7, 8, 8, 9, 10, 10, 11};
    for (int i = 0; i < 17; i++)
        if (k == K[i])
            return V[i];
    return -1;
}

// Python's float(s): the whole string a number (spaces around allowed), else false
static bool pyfloat(const std::string &s, double *v)
{
    const char *p = s.c_str();
    char *end;
    *v = strtod(p, &end);
    if (end == p)
        return false;
    while (*end == ' ' || *end == '\t')
        end++;
    return *end == 0;
}

struct Ref {
    bool on;
    int note;
    double hz;
};

// TwelveTuner.note2Ratio
static double twelve_ratio(const Twelve &t, int note)
{
    double oa = 1.0;
    while (note < 0 || note > 11) {
        if (note < 0) {
            note += 12;
            oa /= (2 * t.stretch);
        } else {
            note -= 12;
            oa *= (2 * t.stretch);
        }
    }
    return t.iv[note] * oa;
}

static const Gen *gen_of(const char *name)
{
    for (const Gen &g : GEN)
        if (!strcmp(g.name, name))
            return &g;
    return nullptr;
}

// TWO CHAINS ON A PIANO's OCTAVES (tunelib.ChainsPianoTuner, path.py's
// HybridMeanNotes made general): Note.rel_tune's arithmetic, operation for
// operation -- fifths 3:2, octaves on the lower note's 2nd partial by the
// fitted grand's coefficient (steinway_inharmonicity_coefficient_func)
static double grand_coeff(double x)
{
    const double a = 5.22964e-6, b = 1.21012e-6, c = 8.3666e-10, d = -0.007927, e = 0.429601;
    return a + b * x + c * x * x + (d / x) + (e / (x * x));
}
static double ratio2(double coeff) { return 2.0 * (1.0 + 0.5 * 3.0 * coeff); }    // (inharmonicity_coefficient_ratio(2, c))
// A CLASS's OWN STRINGS (tunelib.chain_law_token: b<law>[x]=<numbers>):
// voice.c law_B's arithmetic -- 0 the polynomial (floor 27.5 Hz), 1 a
// two-part power law, 2 the polynomial times (long/short)^4; x the stiff
// string's 2nd partial exactly. law -1: path.py's fitted grand, first order
struct ChainLaw {
    int law = -1;
    bool exact = false;
    double p[8] = {};
    double B(double x) const
    {
        if (law < 0)
            return grand_coeff(x);
        if (law == 1)
            return x < p[4] ? p[0] * pow(x, p[1]) : p[2] * pow(x, p[3]);
        const double xl = x < 27.5 ? 27.5 : x;
        double y = p[0] + p[1] * xl + p[2] * xl * xl + (p[3] / xl) + (p[4] / (xl * xl));
        if (law == 2) {
            const double f = x > 1e-6 ? x : 1e-6;
            const double long_ = std::min(p[5] / f, p[6]), short_ = std::min(p[5] / f, p[7]);
            y = y * pow(long_ / short_, 4.0);
        }
        return y;
    }
    double ratio(double coeff) const
    {
        return exact ? 2.0 * sqrt((1.0 + 4.0 * coeff) / (1.0 + coeff)) : ratio2(coeff);
    }
};
// a law token taken apart; false if it is not one
static bool chain_law(const std::string &tok, ChainLaw *L)
{
    const size_t eq = tok.find('=');
    if (eq == std::string::npos || eq < 2 || tok[0] != 'b' || tok[1] < '0' || tok[1] > '2')
        return false;
    const std::string head = tok.substr(0, eq);
    if (head.size() > 3 || (head.size() == 3 && head[2] != 'x'))
        return false;
    L->law = tok[1] - '0';
    L->exact = head.size() == 3;
    std::string rest = tok.substr(eq + 1);
    int n = 0;
    size_t a = 0;
    while (a <= rest.size() && n < 8) {
        const size_t b = rest.find(',', a);
        const std::string t = rest.substr(a, b == std::string::npos ? std::string::npos : b - a);
        if (!pyfloat(t, &L->p[n]))
            return false;
        n++;
        if (b == std::string::npos)
            break;
        a = b + 1;
    }
    return n == (L->law == 2 ? 8 : 5) && rest.find(',', 0) != std::string::npos;
}
struct ChainGen {
    double f[150];
    bool set[150];
    ChainLaw L;
    // Note.rel_tune: child from parent by n/d (along the inharmonicity: an octave)
    void tune(int child, int parent, int n, int d, bool inh = false)
    {
        double base = f[parent] * (double)n / (double)d, v;
        if (!inh)
            v = f[parent] * (double)n / (double)d;
        else if (n >= d)
            v = base * (L.ratio(L.B(f[parent])) / 2.0);
        else
            v = base / (L.ratio(L.B(base)) / 2.0);
        f[child] = v;
        set[child] = true;
    }
};
// tunelib._chain_shift: a route's generator moved -6..5 semitones for start s
static int chain_shift(int s) { return s < 6 ? s : s - 12; }

// tunelib._chain_gen: the generator's table (keys it tuned), before the
// reference, for a route (0 fifth, 1 fourth, 2 octaves) from start s; the
// bridge by `ratio` (pure_ratio: the fourth route's 5/4 as HybridNotes writes it)
static Table chain_gen(int route, int s, double ratio, bool pure_ratio, const ChainLaw &law = ChainLaw())
{
    ChainGen g;
    g.L = law;
    for (int n = 0; n < 150; n++) {
        g.f[n] = 0.0;
        g.set[n] = false;
    }
    auto at = [&](int n, double f) {
        g.f[n] = f;
        g.set[n] = true;
    };
    auto fill = [&]() {                                 // (HybridMeanNotes.init_octaves: up, then down)
        for (int n = 12; n <= 127; n++)
            if (!g.set[n] && n - 12 >= 0 && g.set[n - 12])
                g.tune(n, n - 12, 2, 1, true);
        for (int n = 127; n >= 12; n--)
            if (!g.set[n] && g.set[n + 12])
                g.tune(n, n + 12, 1, 2, true);
    };
    if (route == 0) {                                   // HybridMeanNotes: chain one from C3
        const int d = chain_shift(s), n0 = 48 + d;
        at(n0, 440.0 * pow(2.0, (3 + d) / 12.0) / 4.0);
        for (int k = 0; k < 5; k++)
            g.tune(n0 + 7 * (k + 1), n0 + 7 * k, 3, 2);
        at(n0 + 18, g.f[n0 + 14] * ratio);              // (the bridge: position 2 up a third)
        g.tune(n0 + 25, n0 + 18, 3, 2);                 // (a fifth up, two stretched octaves down)
        g.tune(n0 + 13, n0 + 25, 1, 2, true);
        g.tune(n0 + 1, n0 + 13, 1, 2, true);
        for (int k = 0; k < 4; k++)
            g.tune(n0 + 1 + 7 * (k + 1), n0 + 1 + 7 * k, 3, 2);
        fill();
    } else if (route == 2) {                            // StretchedHelmholtzNotes: chain two from C#3
        const int d = chain_shift(s), cs = 49 + d;
        at(cs, 440.0 * pow(2.0, (-20 + d) / 12.0));
        g.tune(cs - 7, cs, 2, 3);
        int c = cs;
        for (int k = 0; k < 5; k++, c += 7)
            g.tune(c + 7, c, 3, 2);
        for (int k = 0; k < 3; k++, c -= 12)
            g.tune(c - 12, c, 1, 2, true);
        for (int k = 0; k < 5; k++, c += 7)
            g.tune(c + 7, c, 3, 2);
        fill();
    } else {                                            // HybridNotes: around the bridge's C4
        const int d = chain_shift((s + 2) % 12), C = 60 + d;
        at(C, 440.0 * pow(2.0, (3 + d) / 12.0) / 2.0);
        g.tune(C - 7, C, 2, 3);                         // F3, B-flat2
        g.tune(C - 14, C - 7, 2, 3);
        g.tune(C + 7, C, 3, 2);                         // G4, D5, A5
        g.tune(C + 14, C + 7, 3, 2);
        g.tune(C + 21, C + 14, 3, 2);
        g.tune(C + 12, C, 2, 1, true);
        g.tune(C - 12, C, 1, 2, true);
        g.tune(C + 5, C - 7, 2, 1, true);               // F4, F5
        g.tune(C + 17, C + 5, 2, 1, true);
        g.tune(C - 2, C - 14, 2, 1, true);              // B-flat3, B-flat4
        g.tune(C + 10, C - 2, 2, 1, true);
        g.tune(C - 5, C + 7, 1, 2, true);               // G3, G5
        g.tune(C + 19, C + 7, 2, 1, true);
        g.tune(C + 2, C + 14, 1, 2, true);              // D4, D3
        g.tune(C - 10, C + 2, 1, 2, true);
        g.tune(C + 9, C + 21, 1, 2, true);              // A4, A3
        g.tune(C - 3, C + 9, 1, 2, true);
        if (pure_ratio)                                 // the bridge E4
            g.tune(C + 4, C, 5, 4);
        else
            at(C + 4, g.f[C] * ratio);
        g.tune(C - 8, C + 4, 1, 2, true);               // E3
        g.tune(C - 13, C - 8, 3, 4);                    // B2, a pure fourth down
        g.tune(C - 6, C - 13, 3, 2);                    // F#3, C#4, G#4, D#5
        g.tune(C + 1, C - 6, 3, 2);
        g.tune(C + 8, C + 1, 3, 2);
        g.tune(C + 15, C + 8, 3, 2);
        g.tune(C + 16, C + 4, 2, 1, true);              // E5
        g.tune(C - 1, C - 13, 2, 1, true);              // B3, B4
        g.tune(C + 11, C - 1, 2, 1, true);
        g.tune(C + 6, C - 6, 2, 1, true);               // F#4, F#5
        g.tune(C + 18, C + 6, 2, 1, true);
        g.tune(C + 13, C + 1, 2, 1, true);              // C#5, C#3
        g.tune(C - 11, C + 1, 1, 2, true);
        g.tune(C + 20, C + 8, 2, 1, true);              // G#5, G#3
        g.tune(C - 4, C + 8, 1, 2, true);
        g.tune(C + 3, C + 15, 1, 2, true);              // D#4, D#3
        g.tune(C - 9, C + 3, 1, 2, true);
        static const int LOW[12] = {47, 46, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57};    // (init_octaves_low)
        for (int n : LOW) {
            g.tune(n + d - 12, n + d, 1, 2, true);
            g.tune(n + d - 24, n + d - 12, 1, 2, true);
        }
        g.tune(57 + d - 36, 57 + d - 24, 1, 2, true);
        static const int HIGH[12] = {70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81};    // (init_octaves_high)
        for (int n : HIGH) {
            g.tune(n + d + 12, n + d, 2, 1, true);
            g.tune(n + d + 24, n + d + 12, 2, 1, true);
        }
        for (int n : {70, 71, 72})
            g.tune(n + d + 36, n + d + 24, 2, 1, true);
    }
    Table t;
    for (int n = 0; n < 150; n++)
        if (g.set[n] && g.f[n] != 0.0)
            t[n] = g.f[n];
    return t;
}

// tunelib.chain_bridge: chains/<spec>'s bridge in cents -- a name (helm,
// pure, mid, mean, pyth) or a number from the schismatic third to the
// Pythagorean; false otherwise
static bool chain_bridge(const std::string &spec, double *X)
{
    double P = 1200.0 * (log(1.5) / log(2.0));
    if (spec == "helm")
        *X = 6000.0 - 8.0 * P;
    else if (spec == "mid")
        *X = (3600.0 - 4.0 * P) / 2.0;
    else if (spec == "pure")
        *X = 1200.0 * (log(1.25) / log(2.0));
    else if (spec == "mean")
        *X = 1200.0 * (log(sqrt(1.25 * 81.0 / 64.0)) / log(2.0));
    else if (spec == "pyth")
        *X = 1200.0 * (log(81.0 / 64.0) / log(2.0));
    else {
        if (!pyfloat(spec, X))
            return false;
        double lo = 6000.0 - 8.0 * P, hi = 4.0 * P - 2400.0;
        if (!(lo - 1e-6 <= *X && *X <= hi + 1e-6))
            return false;
    }
    return true;
}

// PathTuner._build_table at A (NAN: none); X the bridge of the two chains
// (kind 2: NAN hybridmean's mean third, else ChainsTuner's)
static Table path_table(const PathT &p, double A, const Ref &ref, double Xc = NAN)
{
    Table t;
    if (p.kind == 2) {
        // HybridMeanTuner: two chains of pure fifths, bridged D-F# by the mean third (ChainsTuner: by X)
        double P = 1200.0 * (log(1.5) / log(2.0));
        double X = std::isnan(Xc) ? 1200.0 * (log(sqrt(1.25 * 81.0 / 64.0)) / log(2.0)) : Xc;
        double c[12];
        static const int CH1[6] = {0, 7, 2, 9, 4, 11};
        for (int i = 0; i < 6; i++)
            c[CH1[i]] = fmod(i * P, 1200.0);
        c[6] = fmod(c[2] + X, 1200.0);
        c[1] = fmod(c[6] + P, 1200.0);
        static const int CH2[4] = {8, 3, 10, 5};
        for (int i = 1; i <= 4; i++)
            c[CH2[i - 1]] = fmod(c[1] + i * P, 1200.0);
        int rn = ref.on ? ref.note : 69;
        double rh = ref.on ? ref.hz : (std::isnan(A) || A == 0.0 ? 440.0 : A);
        int q = rn / 12, m = rn % 12;               // (ref notes are 60 and 69: no negatives)
        double base = rh / pow(2.0, (c[m] + 1200.0 * q) / 1200.0);
        for (int n = 0; n < 128; n++)
            t[n] = base * pow(2.0, (c[n % 12] + 1200.0 * (n / 12)) / 1200.0);
        return t;
    }
    if (p.kind == 3) {
        // a procedure's table (PleyelTuner._build_table): scaled so the fork's
        // key sounds the reference, else A times the fork's share
        for (const Fixed &x : FIXED)
            if (!strcmp(x.name, p.name))
                for (int n = 0; n < 128; n++)
                    if (!std::isnan(x.f[n]))
                        t[n] = x.f[n];
        int rn = 0;
        double rh = 0.0;
        for (const Fixed &x : FIXED)
            if (!strcmp(x.name, p.name)) {
                rn = ref.on ? ref.note : x.fork_note;
                rh = ref.on ? ref.hz : A * x.fork_share;
            }
        auto it = t.find(rn);
        if (it != t.end() && it->second != 0.0) {
            double s = rh / it->second;
            for (auto &kv : t)
                kv.second = kv.second * s;
        }
        return t;
    }
    const Gen *g = gen_of(p.gen);
    for (int n = 0; g && n < 150; n++)
        if (!std::isnan(g->f[n]) && g->f[n] != 0.0)
            t[n] = g->f[n];
    bool ron = ref.on || !std::isnan(A);
    int rn = ref.on ? ref.note : 69;
    double rh = ref.on ? ref.hz : A;
    auto it = t.find(rn);
    if (ron && it != t.end() && it->second != 0.0) {
        double s = rh / it->second;
        for (auto &kv : t)
            kv.second = kv.second * s;
    }
    if (p.kind != 1)
        return t;
    // HybridHarmonicTuner: the octave from C4, repeated by pure 2:1
    if (!t.count(60))
        return t;
    double r[12];
    for (int i = 0; i < 12; i++) {
        if (!t.count(60 + i))
            return t;
        r[i] = t[60 + i] / t[60];
    }
    double c4 = t[60];
    Table h;
    for (int n = 0; n < 128; n++) {
        int d = n - 60, pc = ((d % 12) + 12) % 12;
        int k = (d - pc) / 12;                      // a multiple of 12: exact
        h[n] = c4 * r[pc] * pow(2.0, (double)k);
    }
    return h;
}

// PathTuner._freq: a key outside the table by pure octaves from the nearest
// tuned one of its pitch class, else at the reference (or A, else 440) in
// equal temperament
static double path_freq(const Table &t, int midi, double A, const Ref &ref)
{
    auto it = t.find(midi);
    if (it != t.end())
        return it->second;
    for (int k = 1; k < 10; k++) {
        auto lo = t.find(midi - 12 * k);
        if (lo != t.end())
            return lo->second * pow(2.0, (double)k);
        auto hi = t.find(midi + 12 * k);
        if (hi != t.end())
            return hi->second / pow(2.0, (double)k);
    }
    if (ref.on)
        return ref.hz * pow(2.0, (midi - ref.note) / 12.0);
    double base = std::isnan(A) || A == 0.0 ? 440.0 : A;
    return base * pow(2.0, (midi - 69) / 12.0);
}

// ragas.table: the error, or 0
static int raga_table(const std::string &spec, double *out, int *have, double sa_hz = 0.0, int *sa_out = nullptr,
                      double *sw = nullptr, int *nsw = nullptr)
{
    // parse: raga:<system>[/<raga>]@<key>[:<Sa Hz>]
    std::string s = spec;
    if (s.compare(0, 5, "raga:") == 0)
        s = s.substr(5);
    size_t at = s.find('@');
    if (at == std::string::npos)
        return -5;
    std::string body = s.substr(0, at), a = s.substr(at + 1);
    double hz = 0.0;
    bool has_hz = false;
    size_t colon = a.find(':');
    if (colon != std::string::npos) {
        if (!pyfloat(a.substr(colon + 1), &hz))
            return -3;
        has_hz = true;
        a = a.substr(0, colon);
    }
    size_t sl = body.find('/');
    std::string system = body.substr(0, sl), raga = sl == std::string::npos ? "" : body.substr(sl + 1);
    const RagaSys *sys = nullptr;
    for (const RagaSys &r : RAGA_SYSTEMS)
        if (system == r.name)
            sys = &r;
    if (!sys)
        return -5;
    const Raga *rg = nullptr;           // (ragas.swaras: the named raga's, else the system's own)
    for (const Raga &r : RAGAS)
        if (raga.empty() ? system == r.name : raga == r.name)
            rg = &r;
    if (!raga.empty() && !rg)
        return -5;
    int key = key_of(a);
    if (key < 0)
        return -2;
    int sa = 60 + key;
    // (ragas.table: hz or sa_hz or 12-TET's)
    double f_sa = (has_hz && hz != 0.0) ? hz : sa_hz != 0.0 ? sa_hz : 440.0 * pow(2.0, (sa - 69) / 12.0);
    if (sa_out)
        *sa_out = sa;
    if (sw) {
        *nsw = rg ? rg->n : 12;
        for (int i = 0; i < *nsw; i++)
            sw[i] = sys->cents[rg ? rg->idx[i] : i];
    }
    for (int n = 0; n < 128; n++) {
        int d = n - sa;
        int octv = (int)floor(d / 12.0), deg = d - 12 * octv;
        out[n] = f_sa * pow(2.0, octv + sys->cents[deg] / 1200.0);
        have[n] = 1;
    }
    return 0;
}

}  // namespace tuner
}  // namespace nv

extern "C" {

// blockrender.tuning_table(name) into out[128] (have[n] 0 where the tuner has
// no frequency), at the reference (note, Hz) when ref_note >= 0
// (tunelib.set_reference). 0, or: -1 no such tuner, -2 no such key, -3 a
// bad pitch, -4 @KEY or :A4 on a tuner without a table to move, -5 a bad
// raga spec
int nv_tuning_table(const char *name, int ref_note, double ref_hz, double *out, int *have)
{
    using namespace nv::tuner;
    for (int n = 0; n < 128; n++) {
        out[n] = 0.0;
        have[n] = 0;
    }
    std::string key = name;
    for (char &c : key)
        c = (char)tolower((unsigned char)c);
    if (key.compare(0, 5, "raga:") == 0)
        return raga_table(key, out, have);
    Ref ref{ref_note >= 0, ref_note, ref_hz};
    // name~Hz: A4 given, as the reference (69, Hz) would set it (a part's own
    // tuning at the rig's A: blockrender.tuning_table)
    size_t tilde = key.find('~');
    if (tilde != std::string::npos) {
        double a4;
        if (key.compare(0, 5, "raga:") == 0 || !pyfloat(key.substr(tilde + 1), &a4))
            return -3;
        ref = Ref{true, 69, a4};
        key = key.substr(0, tilde);
    }
    double pitch = NAN;
    bool has_pitch = false;
    size_t colon = key.find(':');
    if (colon != std::string::npos) {
        if (!pyfloat(key.substr(colon + 1), &pitch))
            return -3;
        has_pitch = true;
        key = key.substr(0, colon);
    }
    int tonic = 0;
    bool has_tonic = false;
    size_t at = key.find('@');
    if (at != std::string::npos) {
        tonic = key_of(key.substr(at + 1));
        if (tonic < 0)
            return -2;
        has_tonic = true;
        key = key.substr(0, at);
    }
    for (const Twelve &t : TWELVE)
        if (key == t.name) {
            if (has_pitch || has_tonic)
                return -4;
            double C = ref.on ? ref.hz / twelve_ratio(t, ref.note - 60) : (double)t.A / twelve_ratio(t, 9);
            for (int n = 0; n < 128; n++) {
                out[n] = C * twelve_ratio(t, n - 60);
                have[n] = 1;
            }
            return 0;
        }
    if (key == "dynamic") {
        if (has_pitch || has_tonic)
            return -4;
        for (int n = 0; n < 128; n++)               // (its search ignores the reference: so here)
            if (!std::isnan(DYNAMIC[n])) {
                out[n] = DYNAMIC[n];
                have[n] = 1;
            }
        return 0;
    }
    // chains/<bridge> (tunelib.ChainsTuner): hybridmean's chains, any bridge, at 440
    static const PathT CHAINS = {"chains", "", 440.0, 2};
    double Xc = NAN;
    if (key.compare(0, 7, "chains/") == 0) {
        // chains/<bridge>[/<octaves>[/<route>]]: pure (below: the octaves route the helm bridge), or a
        // piano's octaves -- built from @KEY, not moved -- or its middle octave repeated by 2:1
        std::string sp = key.substr(7), oc = "pure", rt = "fifth";
        if (const size_t sl = sp.find('/'); sl != std::string::npos) {
            oc = sp.substr(sl + 1);
            sp = sp.substr(0, sl);
            if (const size_t s2 = oc.find('/'); s2 != std::string::npos) {
                rt = oc.substr(s2 + 1);
                oc = oc.substr(0, s2);
            }
        }
        const int route = rt == "fifth" ? 0 : rt == "fourth" ? 1 : rt == "octaves" ? 2 : -1;
        ChainLaw law;
        if (oc == "own")                                // (unresolved: pure octaves)
            oc = "pure";
        const bool own = oc.size() > 2 && oc[0] == 'b' && oc.find('=') != std::string::npos;
        if (!chain_bridge(sp, &Xc) || (oc != "pure" && oc != "piano" && oc != "middle" && !own) || route < 0
            || (own && !chain_law(oc, &law)))
            return -1;
        if (oc == "pure" && route == 2)
            chain_bridge("helm", &Xc);
        if (oc != "pure") {
            const double ratio = sp == "mean" ? pow(80.0 * 81.0, 0.5) / 64.0 : pow(2.0, Xc / 1200.0);
            Table t = chain_gen(route, has_tonic ? tonic : 0, ratio, sp == "pure", law);
            const double A = has_pitch ? pitch : 440.0;
            const int rn = ref.on ? ref.note : 69;
            const double rh = ref.on ? ref.hz : A;
            auto it = t.find(rn);
            if (it != t.end() && it->second != 0.0) {
                const double k = rh / it->second;
                for (auto &kv : t)
                    kv.second = kv.second * k;
            }
            if (oc == "middle") {                       // (HybridHarmonicTuner's: C4's octave, by pure 2:1)
                bool all = true;
                for (int i = 0; i < 12; i++)
                    all = all && t.count(60 + i);
                if (all) {
                    double r[12];
                    for (int i = 0; i < 12; i++)
                        r[i] = t[60 + i] / t[60];
                    const double c4 = t[60];
                    Table h;
                    for (int n = 0; n < 128; n++) {
                        const int dd = n - 60, pc = ((dd % 12) + 12) % 12, k = (dd - pc) / 12;
                        h[n] = c4 * r[pc] * pow(2.0, (double)k);
                    }
                    t.swap(h);
                }
            }
            for (int n = 0; n < 128; n++) {
                out[n] = path_freq(t, n, A, ref);
                have[n] = 1;
            }
            return 0;
        }
    }
    const PathT *found = std::isnan(Xc) ? nullptr : &CHAINS;
    for (const PathT &p : PATH)
        if (!found && key == p.name)
            found = &p;
    if (found) {
        const PathT &p = *found;
        double A = has_pitch ? pitch : p.A;     // at_pitch: the class's A
        Table t = path_table(p, A, ref, Xc);
        if (has_tonic && tonic != 0) {
            // in_key: every key moved up, A4 kept where the base put it
            Table moved;
            for (auto &kv : t)
                moved[kv.first + tonic] = kv.second;
            if (t.count(69) && moved.count(69)) {
                double s = t[69] / moved[69];
                for (auto &kv : moved)
                    kv.second = kv.second * s;
            }
            t.swap(moved);
        }
        for (int n = 0; n < 128; n++) {
            out[n] = path_freq(t, n, A, ref);
            have[n] = 1;
        }
        return 0;
    }
    return -1;
}

// ragas.table(spec, sa_hz) into out[128], Sa's note (sa_note: the octave
// from middle C up) and the swaras' cents (ragas.swaras, sw[12], *nsw of
// them): the secondary tuning's and the meend's. sa_hz 0: none. 0, or < 0 as
// nv_tuning_table's raga specs.
// THE EASTERN TUNING'S CHOICES (livetui.pick_eastern): system i's name
// (ragas.SYSTEMS, NULL past the last), and raga i's -- its swaras' count and
// their indices into its system's twelve (ragas.RAGAS)
extern "C" const char *nv_raga_system_name(int i)
{
    return i >= 0 && i < (int)(sizeof nv::tuner::RAGA_SYSTEMS / sizeof nv::tuner::RAGA_SYSTEMS[0]) ? nv::tuner::RAGA_SYSTEMS[i].name : nullptr;
}

extern "C" const char *nv_raga_name(int i, int *n, const int **idx)
{
    if (i < 0 || i >= (int)(sizeof nv::tuner::RAGAS / sizeof nv::tuner::RAGAS[0]))
        return nullptr;
    if (n)
        *n = nv::tuner::RAGAS[i].n;
    if (idx)
        *idx = nv::tuner::RAGAS[i].idx;
    return nv::tuner::RAGAS[i].name;
}

int nv_raga_info(const char *spec, double sa_hz, double *out, int *have, int *sa_note, double *sw, int *nsw)
{
    std::string key = spec;
    for (char &c : key)
        c = (char)tolower((unsigned char)c);
    for (int n = 0; n < 128; n++) {
        out[n] = 0.0;
        have[n] = 0;
    }
    if (key.compare(0, 5, "raga:") != 0)
        return -5;
    return nv::tuner::raga_table(key, out, have, sa_hz, sa_note, sw, nsw);
}

}  // extern "C"
