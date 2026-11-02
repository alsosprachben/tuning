// live.cpp -- the native engine's LIVE side. First piece: a key's TEMPLATE.
//
// live.py makes each key's note once, at each velocity it is played at, and
// stamps it into the slab at every press (Slab.stamp_cols); a template is
// blockrender.prepare of a one-note file (live.Voice._raw_template): tempo
// one beat a second, the program, CC7 and CC11 at 127, the key down at 0 and
// up at 1 s, the track ending a second later -- with fixed touch on and the
// register off (the slab has its own: LiveChannel). nv_template builds that
// file's bytes here and runs them through the engine (midi.cpp, channel.cpp,
// prepare.cpp): the template's table, bit for bit the Python's.
//
// Its derived fields (live's masks, hrel, dur, fa_at...) are arithmetic on
// these columns: the slab's port takes them.

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <map>
#include <tuple>
#include <type_traits>
#include <vector>

#include "pycompat.h"
#include "live.h"

extern "C" {
void *nv_midi_read(const uint8_t *buf, long long len, int *err);
void nv_midi_free(void *p);
double nv_midi_total(void *p);
void nv_midi_song(void *p, void *song, const double *trim);
void *nv_song_new(void);
void nv_song_free(void *s);
void nv_song_tuning(void *s, long long ch, double t, const double *freq);
void nv_song_finish(void *s, double total);
void nv_song_kits(void *s, const double *f0, const double *seat);
void nv_song_chokes(void *s, const unsigned long long *choke);
void nv_song_strokes(void *s, const int *kind, const double *par);
void nv_log_n(long n, const double *x, double *out);
long long nv_prepare(void *song, const NoteClass *const *K, const NoteIn *tmpl, const double *br, int nbr,
                     PyRandom *rs, double **rowsp, double *qacc, double *azimuth, const int *kind, double scale,
                     double full_db_s, double residual, double beta, long long blk, double total, double ring_floor,
                     double ring_max, double *out, double knee_db, double ln10_20, double xdec_nepers, double SR,
                     void **dm, int with_register);
}

namespace nv {
namespace live {

static void vlq(std::vector<uint8_t> &b, uint32_t v)
{
    uint8_t t[5];
    int n = 0;
    t[n++] = v & 0x7F;
    while (v >>= 7)
        t[n++] = 0x80 | (v & 0x7F);
    while (n)
        b.push_back(t[--n]);
}

// _raw_template's file, as mido saves it (type 1, 480 ticks a beat, one
// track): end, the track's last delta (a drum's 18 beats: its 8 s ring)
static std::vector<uint8_t> one_note(int program, int note, int vel, int ch, int fast, uint32_t end = 480)
{
    std::vector<uint8_t> tr;
    auto ev = [&](uint32_t dt, std::initializer_list<uint8_t> bytes) {
        vlq(tr, dt);
        tr.insert(tr.end(), bytes);
    };
    ev(0, {0xFF, 0x51, 0x03, 0x0F, 0x42, 0x40});                     // set_tempo 1000000
    ev(0, {(uint8_t)(0xC0 | ch), (uint8_t)program});
    ev(0, {(uint8_t)(0xB0 | ch), 7, 127});
    ev(0, {(uint8_t)(0xB0 | ch), 11, 127});
    if (fast >= 0)
        ev(0, {(uint8_t)(0xB0 | ch), 1, (uint8_t)fast});            // a wheel's step (the honky-tonk's detune)
    ev(0, {(uint8_t)(0x90 | ch), (uint8_t)note, (uint8_t)vel});
    ev(480, {(uint8_t)(0x80 | ch), (uint8_t)note, 0});
    ev(end, {0xFF, 0x2F, 0x00});
    std::vector<uint8_t> f = {'M', 'T', 'h', 'd', 0, 0, 0, 6, 0, 1, 0, 1, 0x01, 0xE0, 'M', 'T', 'r', 'k'};
    uint32_t n = (uint32_t)tr.size();
    f.push_back(n >> 24); f.push_back(n >> 16); f.push_back(n >> 8); f.push_back(n);
    f.insert(f.end(), tr.begin(), tr.end());
    return f;
}

// THE DRUM SETS, as a drum part's templates read them (native.kits): each
// drum program's key's pitch, seat, exclusive class (two words) and
// gesture (a kind, NV_SPAR numbers)
struct Kits {
    std::vector<double> f0, seat, spar;
    std::vector<unsigned long long> choke;
    std::vector<int> skind;
};

}  // namespace live
}  // namespace nv

extern "C" {

// A key's template: program, key and velocity on channel 0 -- or, kit
// given, a drum set's on GM's percussion channel (its key's pitch, seat,
// exclusive class and strokes from kit's tables: native.kits'), the tuning freq[128],
// trim[256] (a GM file's: patch_map.program_trim, melodic then drum), fast
// a wheel's step sent as CC1 before the note (-1 none: _raw_template's), the
// engine's constants in tmpl (its fixed_touch set, as live builds templates)
// and the rest as nv_prepare's. The rows in *rowsp (nv_buf_free), out[] as
// nv_prepare's. Returns the rows, or < 0 (the file refused, a note not the
// engine's).
static long long template_rows(const NoteClass *const *K, const NoteIn *tmpl, const double *freq,
                               const double *trim, int program, int note, int vel, int fast, double **rowsp,
                               const int *kind, double scale, double full_db_s, double residual, double beta,
                               long long blk, double ring_floor, double ring_max, double *out, double knee_db,
                               double ln10_20, double xdec_nepers, double SR, void **dm, const nv::live::Kits *kit,
                               std::vector<long long> *srows);

long long nv_template(const NoteClass *const *K, const NoteIn *tmpl, const double *freq, const double *trim,
                      int program, int note, int vel, int fast, double **rowsp, const int *kind, double scale,
                      double full_db_s, double residual, double beta, long long blk, double ring_floor,
                      double ring_max, double *out, double knee_db, double ln10_20, double xdec_nepers, double SR,
                      void **dm, const nv::live::Kits *kit = nullptr)
{
    return template_rows(K, tmpl, freq, trim, program, note, vel, fast, rowsp, kind, scale, full_db_s, residual,
                         beta, blk, ring_floor, ring_max, out, knee_db, ln10_20, xdec_nepers, SR, dm, kit, nullptr);
}

}  // extern "C"

// ...and its strokes' rows (srows: [first, end) pairs, the song's stroke_rows)
static long long template_rows(const NoteClass *const *K, const NoteIn *tmpl, const double *freq,
                               const double *trim, int program, int note, int vel, int fast, double **rowsp,
                               const int *kind, double scale, double full_db_s, double residual, double beta,
                               long long blk, double ring_floor, double ring_max, double *out, double knee_db,
                               double ln10_20, double xdec_nepers, double SR, void **dm, const nv::live::Kits *kit,
                               std::vector<long long> *srows)
{
    std::vector<uint8_t> f = kit ? nv::live::one_note(program, note, vel, 9, fast, 480 * 18)
                                 : nv::live::one_note(program, note, vel, 0, fast);
    int err = 0;
    void *m = nv_midi_read(f.data(), (long long)f.size(), &err);
    if (!m)
        return -1000000001LL;
    void *song = nv_song_new();
    nv_song_tuning(song, -1, 0.0, freq);
    if (kit) {
        nv_song_kits(song, kit->f0.data(), kit->seat.data());
        nv_song_chokes(song, kit->choke.data());
    }
    nv_midi_song(m, song, trim);
    if (kit)
        nv_song_strokes(song, kit->skind.data(), kit->spar.data());
    double total = nv_midi_total(m);
    nv_song_finish(song, total);
    PyRandom rs;
    pyr_seed(&rs, 0);                       // _prepare's random.seed(0)
    double qacc[18] = {0}, az = 0.0;
    long long P = nv_prepare(song, K, tmpl, nullptr, 0, &rs, rowsp, qacc, &az, kind, scale, full_db_s, residual,
                             beta, blk, total, ring_floor, ring_max, out, knee_db, ln10_20, xdec_nepers, SR, dm, 0);
    if (srows && P >= 0) {
        int n = nv_song_n_stroke_rows(song, nullptr, 0);
        srows->resize(2 * n);
        nv_song_n_stroke_rows(song, srows->data(), n);
    }
    nv_song_free(song);
    nv_midi_free(m);
    return P;
}

// ---------------------------------------------------------------------------
// THE TEMPLATE CACHE (live.Patch): a part's keys, each at every velocity
// bucket's centre (Patch.bucket_vel) and every wheel step, built once off the
// audio thread (Patch.warm) and looked up at a press (Patch.get). A template
// is live's: its table's columns in prepare's final types, grouped as live's
// slab holds them, and what _raw_template derives for a piano -- hrel (each
// partial's frequency over the lowest), dur (its first row's length), fa_at
// (the rows at the commonest fade), the velocity it was built at.

namespace nv {
namespace live {

static const char *F8[] = {"om", "p0", "p0R", "fmw", "fmp", "fmpR"};
static const char *F4[] = {"aL", "aR", "nf", "fa", "re", "ch", "logr", "logrA", "aft", "sus", "cv", "cc", "crl",
                           "sj", "csc", "cbw", "tbav", "tau", "tcut", "vd", "vr", "vp", "delL", "delR", "az", "rdl",
                           "nfr"};
static const char *F4N[] = {"gb", "gt", "gc", "vdl"};
static const char *I4[] = {"gr", "cr", "br", "pl", "fx", "mk"};
static const char *EMIT[NCOLS] = {
    "om", "p0", "p0R", "aL", "aR", "aM", "mch", "px", "pz", "az", "dr", "nf", "non", "noff", "fa", "re", "ch",
    "logr", "logrA", "aft", "sus", "cv", "cc", "crl", "sj", "csc", "cbw", "tbav", "tau", "tcut", "gb", "gt",
    "gc", "vd", "vr", "vp", "vdl", "delL", "delR", "gr", "cr", "br", "pl", "fx", "mk", "rdl", "fmw", "nfr",
    "fmp", "fmpR"};

static int emit_col(const char *n)
{
    for (int c = 0; c < NCOLS; c++)
        if (!strcmp(EMIT[c], n))
            return c;
    return -1;
}


struct Cache {
    std::vector<const NoteClass *> K;
    NoteIn t;
    double freq[128], trim[256];
    int kind[NCOLS], fin[NCOLS];
    double scale, full, residual, beta, ring_floor, ring_max, knee, ln10_20, xdec, SR;
    long long blk;
    std::map<std::tuple<int, int, int>, Template> tm;
    bool drums = false;                 // a drum part: the program is its set (kit's tables)
    Kits kit;
    double oneshot_floor_db = 100.0;    // live.ONESHOT_FLOOR_DB

    // prepare's final type for an EMIT column's value (FINAL_DTYPES)
    double fin_of(int c, double x) const
    {
        switch (fin[c]) {
        case 1: return (double)(float)x;
        case 2: return (double)(long long)x;
        case 3: return (double)(int32_t)x;
        }
        return x;
    }

    bool build(int program, int note, int vel, int fast, Template &T)
    {
        double *rows = nullptr, out[48] = {0};
        void *dm[6] = {nullptr};
        std::vector<long long> srows;
        long long P = template_rows(K.data(), &t, freq, trim, program, note, vel, fast, &rows, kind, scale, full,
                                    residual, beta, blk, ring_floor, ring_max, out, knee, ln10_20, xdec, SR, dm,
                                    drums ? &kit : nullptr, &srows);
        if (P < 0) {
            free(rows);
            return false;
        }
        T.P = (long)P;
        T.vel = vel;
        auto take = [&](const char *name, auto &vec) {
            int c = emit_col(name);
            vec.resize(P);
            for (long long r = 0; r < P; r++)
                vec[r] = (typename std::remove_reference<decltype(vec)>::type::value_type)fin_of(c, rows[NCOLS * r + c]);
        };
        for (int q = 0; q < 6; q++)
            take(F8[q], T.f8[q]);
        for (int q = 0; q < 27; q++)
            take(F4[q], T.f4[q]);
        for (int q = 0; q < 4; q++)
            take(F4N[q], T.f4n[q]);
        take("non", T.i8[0]);
        take("noff", T.i8[1]);
        for (int q = 0; q < 6; q++)
            take(I4[q], T.i4[q]);
        free(rows);
        for (int q = 0; q < 6; q++)
            free(dm[q]);
        // hrel: nf (float64 of the float32) over max(its least, 1e-9), as float32
        const std::vector<float> &nf = T.f4[2];
        T.hrel.resize(P);
        if (P) {
            double mn = (double)nf[0];
            for (long long r = 1; r < P; r++)
                if ((double)nf[r] < mn)
                    mn = (double)nf[r];
            double d = mn > 1e-9 ? mn : 1e-9;
            for (long long r = 0; r < P; r++)
                T.hrel[r] = (float)((double)nf[r] / d);
        }
        T.dur = P ? T.i8[1][0] - T.i8[0][0] : 0;
        // fa_at: the rows whose fade is the commonest (np.unique: the least of a tie)
        const std::vector<float> &fa = T.f4[3];
        T.fa_at.assign(P, 0);
        if (P) {
            std::map<float, long> cnt;
            for (float v : fa)
                cnt[v]++;
            float mode = cnt.begin()->first;
            long best = -1;
            for (auto &kv : cnt)
                if (kv.second > best) {
                    best = kv.second;
                    mode = kv.first;
                }
            for (long long r = 0; r < P; r++)
                T.fa_at[r] = fa[r] == mode;
        }
        // A STROKED KEY (a drum's gesture): each stroke's rows where it falls
        // in the note (sof: its onset less its room delay, over the least of
        // the strokes'; numpy's int64 - float32, truncated) -- a layer's rows,
        // struck with the key, at the press (0)
        int q = 128 * program + note;
        const NoteClass *nc = (q >= 0 && q < NV_K_DRUMS) ? K[(drums ? NV_K_DRUMS : 0) + q] : nullptr;
        if (P && !srows.empty()) {
            const std::vector<float> &rdl = T.f4[25];
            std::vector<char> st(P, 0);
            for (size_t k = 0; k < srows.size(); k += 2)
                for (long long r = srows[k]; r < std::min(srows[k + 1], (long long)P); r++)
                    st[r] = 1;
            double mn = 0.0;
            bool any = false;
            for (long long r = 0; r < P; r++) {
                if (!st[r])
                    continue;
                double b = (double)T.i8[0][r] - (double)rdl[r];
                if (!any || b < mn)
                    mn = b;
                any = true;
            }
            if (any) {
                T.sof.assign(P, 0);
                for (long long r = 0; r < P; r++)
                    if (st[r])
                        T.sof[r] = (long long)((double)T.i8[0][r] - (double)rdl[r] - mn);
            }
        }
        // A ONE-SHOT: each row its length offline (rof) -- but not past where
        // it falls silent, ONESHOT_FLOOR_DB under the loudest row, where it
        // only decays; its length the longest, counted from the press
        // A TAPE PLAYED BACKWARDS STOPS AT ITS ARRIVAL (live's rof for
        // played_backwards): each row grows to its own end, a key-up before
        // it still cutting it there
        if (P && nc && nc->played_backwards) {
            T.rof.resize(P);
            for (long long r = 0; r < P; r++)
                T.rof[r] = T.i8[1][r] - T.i8[0][r];
        }
        T.oneshot = P && nc && nc->one_shot;
        if (T.oneshot) {
            T.rof.resize(P);
            for (long long r = 0; r < P; r++)
                T.rof[r] = T.i8[1][r] - T.i8[0][r];
            const std::vector<float> &aL = T.f4[0], &aR = T.f4[1], &fa = T.f4[3], &lrf = T.f4[6], &sus = T.f4[9];
            const std::vector<int32_t> &gr = T.i4[0];
            std::vector<double> a(P), lr(P);
            double amax = 0.0;
            bool any_quiet = false;
            for (long long r = 0; r < P; r++) {
                float x = fabsf(aL[r]), y = fabsf(aR[r]);
                a[r] = (double)(y > x ? y : x);               // np.maximum of the float32s
                lr[r] = (double)lrf[r];
                if (r == 0 || a[r] > amax)
                    amax = a[r];
                if (lr[r] > 0 && sus[r] <= 0 && gr[r] < 0)
                    any_quiet = true;
            }
            if (any_quiet && amax > 0) {
                double fl = amax * pow(10.0, -oneshot_floor_db / 20.0);
                std::vector<double> x(P), lg(P);
                for (long long r = 0; r < P; r++)
                    x[r] = (a[r] > fl ? a[r] : fl) / fl;
                nv_log_n((long)P, x.data(), lg.data());
                for (long long r = 0; r < P; r++) {
                    if (!(lr[r] > 0 && sus[r] <= 0 && gr[r] < 0))
                        continue;
                    double ts = lg[r] / (lr[r] > 0 ? lr[r] : 1.0);
                    long long end = (long long)((double)fa[r] + ts * SR + 0.01 * SR);
                    if (end < T.rof[r])
                        T.rof[r] = end;
                }
            }
            long long d = 0;
            for (long long r = 0; r < P; r++) {
                long long v = T.rof[r] + (T.sof.empty() ? 0 : T.sof[r]);
                if (r == 0 || v > d)
                    d = v;
            }
            T.dur = d;
        }
        // A HELD TEXTURE IS A HELD NOTE (live's min_hold): its rows run until
        // the key is up, but those that decay on their own; its gate the least
        if (T.oneshot && nc->held_texture && nc->gate_time > 0.0) {
            for (long long r = 0; r < P; r++)
                if (!((double)T.f4[6][r] > 0 && T.f4[9][r] <= 0 && T.i4[0][r] < 0))
                    T.rof[r] = -1;
            T.oneshot = false;
            T.min_hold = (long long)nearbyint(nc->gate_time * SR);
        }
        return true;
    }
};

}  // namespace live
}  // namespace nv

extern "C" {

// A template cache: the classes (K[128 * program + key], the drum sets' after), the engine's
// constants (tmpl: its fixed_touch set), the tuning, the trims, the columns'
// table and final types, and the rest as nv_template's
void *nv_tcache_new(const NoteClass *const *K, const NoteIn *tmpl, const double *freq, const double *trim,
                    const int *kind, const int *fin, double scale, double full_db_s, double residual, double beta,
                    long long blk, double ring_floor, double ring_max, double knee_db, double ln10_20,
                    double xdec_nepers, double SR)
{
    nv::live::Cache *C = new nv::live::Cache();
    C->K.assign(K, K + 2 * NV_K_DRUMS);
    C->t = *tmpl;
    memcpy(C->freq, freq, sizeof C->freq);
    memcpy(C->trim, trim, sizeof C->trim);
    memcpy(C->kind, kind, sizeof C->kind);
    memcpy(C->fin, fin, sizeof C->fin);
    C->scale = scale; C->full = full_db_s; C->residual = residual; C->beta = beta; C->blk = blk;
    C->ring_floor = ring_floor; C->ring_max = ring_max; C->knee = knee_db; C->ln10_20 = ln10_20;
    C->xdec = xdec_nepers; C->SR = SR;
    return C;
}

void nv_tcache_free(void *h) { delete (nv::live::Cache *)h; }

// A DRUM PART'S CACHE: its program the drum set, its keys built on GM's
// percussion channel from the sets' tables (native.kits: f0, seat, choke,
// skind, spar), live's ONESHOT_FLOOR_DB
void nv_tcache_kits(void *h, const double *f0, const double *seat, const unsigned long long *choke,
                    const int *skind, const double *spar, double oneshot_floor_db)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    C->drums = true;
    C->kit.f0.assign(f0, f0 + 16384);
    C->kit.seat.assign(seat, seat + 16384);
    C->kit.choke.assign(choke, choke + 2 * 16384);
    C->kit.skind.assign(skind, skind + 16384);
    C->kit.spar.assign(spar, spar + NV_SPAR * 16384);
    C->oneshot_floor_db = oneshot_floor_db;
}

// Patch.warm: keys lo..hi, nb buckets (each at bucket_vel), the wheel steps
// (nsp of them; -1 for none); the templates built. Returns how many.
long nv_tcache_warm(void *h, int program, int lo, int hi, int nb, const int *speeds, int nsp)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    long n = 0;
    for (int note = lo; note <= hi; note++)
        for (int b = 0; b < nb; b++)
            for (int q = 0; q < nsp; q++) {
                auto k = std::make_tuple(note, b, speeds[q]);
                if (C->tm.count(k))
                    continue;
                int vel = (int)std::min(127.0, (b + 0.5) * 128.0 / nb);    // Patch.bucket_vel
                nv::live::Template T;
                if (C->build(program, note, vel, speeds[q], T)) {
                    C->tm[k] = std::move(T);
                    n++;
                }
            }
    return n;
}

// Patch.get's template, or NULL: its P, dur, vel, a one-shot, its rows'
// own ends (rof) and its strokes' offsets (sof) there, through out[6]
void *nv_tcache_get(void *h, int note, int bucket, int speed, long long *out)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    auto it = C->tm.find(std::make_tuple(note, bucket, speed));
    if (it == C->tm.end())
        return nullptr;
    out[0] = it->second.P;
    out[1] = it->second.dur;
    out[2] = it->second.vel;
    out[3] = it->second.oneshot;
    out[4] = !it->second.rof.empty();
    out[5] = !it->second.sof.empty();
    return &it->second;
}

// tonelib.slur_fade for the part's key: (fade, chiff) s of its legato attack
// alone at the tuning's pitch, and the voice's attack_fraction_max; 0 where
// it has none (no legato_attack_s, no class, no pitch)
int nv_tcache_slur_fade(void *h, int program, int note, double *out)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (note < 0 || note > 127 || program < 0 || program > 127)
        return 0;
    const NoteClass *k = C->K[(C->drums ? NV_K_DRUMS : 0) + 128 * program + note];
    double f0 = C->freq[note];
    if (!k || !k->legato_set || f0 <= 0.0)
        return 0;
    double s = k->legato_attack_s;                          // speech_time
    if (k->speech_cycles > 0.0 && f0 > 0.0)
        s = s + k->speech_cycles / f0;
    double w = s;                                           // chiff_time
    if (k->chiff_width_set || k->chiff_width_cycles > 0.0) {
        w = k->chiff_width_set ? k->chiff_width : s;
        if (k->chiff_width_cycles > 0.0 && f0 > 0.0) {
            double c = k->chiff_width_cycles / f0;
            w = c < w ? c : w;
        }
    }
    out[0] = s;
    out[1] = w;
    out[2] = k->attack_fraction_max;
    return 1;
}

// a template's column (live's group: 0 F8, 1 F4, 2 F4_NOTE, 3 I8, 4 I4; 5 hrel; 6 fa_at as int8; 7 rof, 8 sof)
const void *nv_tmpl_col(void *t, int group, int index)
{
    nv::live::Template *T = (nv::live::Template *)t;
    switch (group) {
    case 0: return T->f8[index].data();
    case 1: return T->f4[index].data();
    case 2: return T->f4n[index].data();
    case 3: return T->i8[index].data();
    case 4: return T->i4[index].data();
    case 5: return T->hrel.data();
    case 6: return T->fa_at.data();
    case 7: return T->rof.data();
    case 8: return T->sof.data();
    }
    return nullptr;
}

}  // extern "C"

extern "C" const nv::live::Template *nv_tcache_lookup(void *h, int note, int bucket, int speed)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    auto it = C->tm.find(std::make_tuple(note, bucket, speed));
    return it == C->tm.end() ? nullptr : &it->second;
}
