// tuner.cpp -- the tuners: blockrender.tuning_table(name) with no Python.
//
// A tuner here is a 128-key table, which is all the renderers ever ask of
// one: midilib.set_tuner's name -- a registry name, then optionally @KEY and
// :A4 (`hybrid@D:466`), or Indian intonation, raga:<system>[/<raga>]@<Sa>
// [:<Sa Hz>] -- and every key's frequency as tunelib's class gives it, at
// tunelib.set_reference's pitch when one is in force. What each class starts
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
//   `dynamic`               its search's table, as it comes (the search reads
//                           no reference, so neither does this)
//   ragas                   (ragas.table) Sa at its key in the octave from
//                           middle C, each key Sa times its swara's cents
//
// Bit for bit blockrender.tuning_table's (examples/tuner_check.py): libm's
// pow, log and sqrt where Python calls them, its order of operations.

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

// PathTuner._build_table at A (NAN: none)
static Table path_table(const PathT &p, double A, const Ref &ref)
{
    Table t;
    if (p.kind == 2) {
        // HybridMeanTuner: two chains of pure fifths, bridged D-F# by the mean third
        double P = 1200.0 * (log(1.5) / log(2.0));
        double X = 1200.0 * (log(sqrt(1.25 * 81.0 / 64.0)) / log(2.0));
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
static int raga_table(const std::string &spec, double *out, int *have)
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
    if (!raga.empty()) {
        bool ok = false;
        for (const char *r : RAGAS)
            ok = ok || raga == r;
        if (!ok)
            return -5;
    }
    int key = key_of(a);
    if (key < 0)
        return -2;
    int sa = 60 + key;
    double f_sa = (has_hz && hz != 0.0) ? hz : 440.0 * pow(2.0, (sa - 69) / 12.0);
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
    for (const PathT &p : PATH)
        if (key == p.name) {
            double A = has_pitch ? pitch : p.A;     // at_pitch: the class's A
            Table t = path_table(p, A, ref);
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

}  // extern "C"
