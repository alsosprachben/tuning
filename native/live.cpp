#include <functional>
#include <climits>
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
#include <array>
#include <atomic>
#include <memory>
#include <mutex>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <tuple>
#include <type_traits>
#include <vector>

#include "pycompat.h"
#include "live.h"

namespace nv {
namespace live {
static int emit_col(const char *n);     // (a row's column by name; below)
}
}

extern "C" {
void *nv_midi_read(const uint8_t *buf, long long len, int *err);
void *nv_midi_read_plain(const uint8_t *buf, long long len, int *err);  // (the file modes left out: midi.cpp)
void nv_midi_free(void *p);
double nv_midi_total(void *p);
void nv_midi_song(void *p, void *song, const double *trim);
void *nv_song_new(void);
void nv_song_live_template(void *s, int no_cut, int no_part_drones);
void nv_song_roll_first(void *s);
void nv_song_free(void *s);
void nv_song_tuning(void *s, long long ch, double t, const double *freq);
void nv_song_finish(void *s, double total);
int nv_song_n_notes(void *s);
int nv_midi_user_drum(void *p, int set, int key, int *iv);
void nv_song_user_drum(void *s, int i, int uq, int umask, const int *uv);
int nv_song_kidx(void *s, int i);
void nv_song_get_note(void *s, int i, long long *ch, int *iv, double *dv);
void nv_song_table(void *s, long long ch, double t, double *out);
void nv_song_siren(void *s, long long ch, int note, double on, double row, double end);
void nv_song_siren_up(void *s, long long ch, int note, double on, double row);
int nv_song_cc_get(void *s, long long ch, int cc, int cap, double *t, int *v);
int nv_song_press_get(void *s, long long ch, int key, int cap, double *t, int *v);
void nv_song_kits(void *s, const double *f0, const double *seat);
int nv_midi_n_dedit(void *p);
void nv_midi_dedit(void *p, int i, int *iv, double *t);
void nv_song_dedit(void *s, int n, const int *iv, const double *t);
void nv_song_chokes(void *s, const unsigned long long *choke);
void nv_song_strokes(void *s, const int *kind, const double *par);
void nv_song_chokes_n(void *s, const unsigned long long *choke, int n);
void nv_song_kits_n(void *s, const double *f0, const double *seat, int n);
void nv_song_strokes_k(void *s, const NoteClass *const *K, const int *kind, const double *par);
void nv_song_vars(void *s, int nent, const int *nls, const int *ls, const double *trim, const int *gs, const int *gm2);
void nv_song_cab_resolve(void *s, int (*cb)(void *, int, int, int *), void *ctx);
void nv_song_class_remap(void *s, int (*cb)(void *, int), void *ctx);
void nv_song_slot_organs(void *s, int n, const OrganSpec *const *so);
void nv_song_slot_orgs(void *s, int n, const int *off, const OrganSpec *const *og);
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
// A DRUM KEY's OWN PITCH AND PAN as a template axis (live's _drum_axis,
// ('dr', pitch, pan)): DV_BASE + 256 x (pitch + 64, 128 none) + (pan, 128 none)
static const int DV_BASE = 1 << 20;
static inline int drum_axis(int pitch, int pan)     // (INT_MIN: unset)
{
    return DV_BASE + 256 * (pitch == INT_MIN ? 128 : std::max(0, std::min(127, pitch + 64)))
           + (pan == INT_MIN ? 128 : std::max(0, std::min(127, pan)));
}

// ...AND A USER DRUM SET's KEY (live's ('dr', pitch, pan, its settings)): its
// PLAY NOTE, pan, source set and key (-1 unset) with the drum NRPN's pitch and
// pan, hashed into DV2_BASE's range -- the spec itself handed to the build
// (g_ud: the builder's, one build at a time)
static const int DV2_BASE = 1 << 28;
static inline int drum_axis_ud(int pitch, int pan, const int *ud, int uset)
{
    unsigned h = 2166136261u;
    auto mix = [&](int v) {
        for (int b = 0; b < 4; b++) {
            h ^= (unsigned)((v >> (8 * b)) & 0xFF);
            h *= 16777619u;
        }
    };
    mix(pitch);
    mix(pan);
    for (int i = 0; i < 4; i++)
        mix(ud[i]);
    mix(uset);
    return DV2_BASE + (int)(h & 0xFFFFFF);
}
static thread_local int g_ud_pitch = INT_MIN, g_ud_pan = INT_MIN, g_ud_set = 0;
static thread_local int g_ud[4] = {-1, -1, -1, -1};     // (note, pan, src_set, src_note)

static std::vector<uint8_t> one_note(int program, int note, int vel, int ch, int fast, uint32_t end = 480,
                                     const OrganSpec *og = nullptr, int bank = 0, int fast_cc = NV_CC_LESLIE,
                                     bool cork = false)
{
    // (an edited drum key's: GS's drum NRPNs on the key before it, the file's
    // own -- live._raw_template's)
    int dpitch = -1, dpan = -1;
    bool uds = false;
    if (fast >= DV2_BASE) {                 // (a user set key's: the spec the build was handed)
        dpitch = g_ud_pitch == INT_MIN ? 128 : std::max(0, std::min(127, g_ud_pitch + 64));
        dpan = g_ud_pan == INT_MIN ? 128 : std::max(0, std::min(127, g_ud_pan));
        uds = true;
        fast = -1;
    } else if (fast >= DV_BASE) {
        dpitch = (fast - DV_BASE) / 256;
        dpan = (fast - DV_BASE) % 256;
        fast = -1;
    }
    std::vector<uint8_t> tr;
    auto ev = [&](uint32_t dt, std::initializer_list<uint8_t> bytes) {
        vlq(tr, dt);
        tr.insert(tr.end(), bytes);
    };
    ev(0, {0xFF, 0x51, 0x03, 0x0F, 0x42, 0x40});                     // set_tempo 1000000
    if (bank) {
        // THE BANK FIRST, as a file selects a variation (Patch._raw_template):
        // CC0 = bank, and a map's own tone under CC32 = map (bank_select)
        ev(0, {(uint8_t)(0xB0 | ch), 0, (uint8_t)(bank & 0x7F)});
        if ((bank & 4095) >> 7)
            ev(0, {(uint8_t)(0xB0 | ch), 32, (uint8_t)((bank & 4095) >> 7)});
    }
    ev(0, {(uint8_t)(0xC0 | ch), (uint8_t)program});
    if ((bank >> 12) & 15)                  // (its cabinet, patch_map.cab_key's: CC83, after the program change
        ev(0, {(uint8_t)(0xB0 | ch), 83, (uint8_t)((bank >> 12) & 15)});        //  that puts it back)
    if ((bank >> 16) & 7)                   // (its pickup, patch_map.pk_key's: CC85, the same)
        ev(0, {(uint8_t)(0xB0 | ch), 85, (uint8_t)((bank >> 16) & 7)});
    ev(0, {(uint8_t)(0xB0 | ch), 7, 127});
    ev(0, {(uint8_t)(0xB0 | ch), 11, 127});
    if (og) {
        // AN ORGAN WITH EVERY STOP DRAWN (live._raw_template): every rank in
        // the template, speaking at the onset; the live registration is
        // which ranks a press stamps. Through the voice's own stop word.
        long long w = 0;
        if (og->wccs[0] == 11)
            w = (1LL << (7 * og->n_wccs)) - 1;
        else
            for (int i = 0; i < og->n_rank; i++)
                if (og->rank[i].n_ratio)
                    w |= 1LL << i;
        for (int i = 0; i < og->n_wccs; i++)
            ev(0, {(uint8_t)(0xB0 | ch), (uint8_t)og->wccs[i], (uint8_t)((w >> (7 * i)) & 0x7F)});
    }
    if (cork)
        ev(0, {(uint8_t)(0xB0 | ch), NV_CC_DRONES, 0});             // the drones corked (live._raw_template)
    if (fast >= 0)          // the template axis's step: the honky-tonk's detune (CC13), else the rotor's (CC80)
        ev(0, {(uint8_t)(0xB0 | ch), (uint8_t)fast_cc, (uint8_t)fast});
    if (uds) {                              // GS's user drum DT1s on the key (blockrender's uset)
        static const int CODE[4] = {0x01, 0x04, 0x0B, 0x0C};
        for (int i = 0; i < 4; i++) {
            if (g_ud[i] < 0)
                continue;
            const uint8_t a[4] = {0x21, (uint8_t)((g_ud_set << 4) | CODE[i]), (uint8_t)note, (uint8_t)g_ud[i]};
            const uint8_t cs = (uint8_t)((128 - (a[0] + a[1] + a[2] + a[3]) % 128) % 128);
            ev(0, {0xF0, 10, 0x41, 0x10, 0x42, 0x12, a[0], a[1], a[2], a[3], cs, 0xF7});
        }
    }
    if (dpitch >= 0 && dpitch < 128) {
        ev(0, {(uint8_t)(0xB0 | ch), 99, 0x18});
        ev(0, {(uint8_t)(0xB0 | ch), 98, (uint8_t)note});
        ev(0, {(uint8_t)(0xB0 | ch), 6, (uint8_t)dpitch});
    }
    if (dpan >= 0 && dpan < 128) {
        ev(0, {(uint8_t)(0xB0 | ch), 99, 0x1C});
        ev(0, {(uint8_t)(0xB0 | ch), 98, (uint8_t)note});
        ev(0, {(uint8_t)(0xB0 | ch), 6, (uint8_t)dpan});
    }
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
// ...SHARED, not copied: views of the export's tables (the host's, read once
// and never moved), which outlive every cache -- each drum patch held its own
// copy of every set's, 19 MB a patch (A5: a 28-part file held hundreds of MB)
template <class T> struct View {
    const T *p = nullptr;
    size_t n = 0;
    const T *data() const { return p; }
    size_t size() const { return n; }
    bool empty() const { return n == 0; }
    const T &operator[](size_t i) const { return p[i]; }
    void assign(const T *a, const T *b) { p = a; n = (size_t)(b - a); }
};
struct Kits {
    View<double> f0, seat, spar;
    View<unsigned long long> choke;
    View<int> skind;
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
// the tuner's raga, as blockrender's prepare finds it (T.raga_sa_note: -1 none;
// its swaras): the cache's whose template this thread is building
static thread_local int g_raga_sa = -1, g_raga_nsw = 0;
// BANK SELECT (the export's VARS, nv_live_vars): each entry's layers (slot,
// semitones, lowest and highest velocity) and its trim (a file not GS's:
// live's templates), GS's [map][program][msb] and GM 2's tables, each slot's
// organ; and the variation the template being built is of (Cache::build)
static std::vector<int> g_var_nls, g_var_off, g_var_ls, g_var_gs, g_var_gm2;
static std::vector<double> g_var_trim;
static std::vector<const OrganSpec *> g_slot_organ;
static std::vector<int> g_slot_off;                 // ...and every organ its tone brings (nv_song_slot_orgs')
static std::vector<const OrganSpec *> g_slot_og;
static thread_local int g_tmpl_var = 0;
// THE SPECTRA-TONE's numbers (native.spectra_constants; nv_tcache_spectra) for
// the templates built on this thread, and each built row's place in its cone
// table (NAN: on no rotor) -- live's template cut: CONE_COLS from leslie's
static thread_local const std::vector<double> *g_tmpl_spec = nullptr;
static thread_local std::vector<float> g_tmpl_cone;
static thread_local const std::map<int, int> *g_tmpl_cabk = nullptr;     // (the template's cabinet voices: Cache::cabk)
static long long g_k_n = 0;             // K's length a cache copies (0: the programs' and drum sets' only)
// THE MAPS' OWN DRUM SETS (the export's MKIT: a drum program 128 + j): their
// keys' region of K and how many (nv_tcache_mapk); the sets' tables are
// then 128 x (128 + n) keys long
static int g_mapk_base = 0, g_mapk_n = 0;
static std::vector<int> g_mapk_ids;  // (their ids, 128 x map + program: a template selects one by them)

// THE CABINET CHOICES' SPEAKERS (the export's VARS, last: native.cab_terms --
// nv_cab_terms): each patch_map.CAB_CHOICES index's 36 doubles -- [0] a Leslie,
// [1] cab_set, [2] n_cab_fm, [3] n_cab_afm, [4] cab_floor, [5..16] cab_fm,
// [17..28] cab_afm, [29] corner, [30] order, [31] cut, [32] bell, [33] ref
static std::vector<double> g_cab_terms;
static std::mutex g_cab_mu;
static std::map<std::pair<const NoteClass *, int>, std::unique_ptr<NoteClass>> g_cab_made;

// the entry variation key v selects for program p (the reader's bsel, Song::bank's): 0 the capital
static int var_entry(int p, int v)
{
    v &= 4095;                              // (a cabinet choice over bit 12: the variation's own entry -- Cache::cab_prep makes its voice)
    if (!v || g_var_gs.empty() || p < 0 || p > 127)
        return 0;
    int msb = v & 0x7F, mp = v >> 7;
    if (!msb)
        return 0;
    int bs = 1 + 128 * (mp >= 1 && mp <= 4 ? mp : 0) + msb;
    return g_var_gs[((size_t)((bs - 1) / 128) * 128 + p) * 128 + (bs - 1) % 128];
}

// ...and the K index its key plays (its first layer's slot, at its semitones), -1 none
static int var_kidx(int en, int key)
{
    if (en <= 0 || en >= (int)g_var_nls.size() || g_var_nls[en] < 1)
        return -1;
    const int *l = &g_var_ls[4 * (size_t)g_var_off[en]];
    int k = key + l[1];
    return k >= 0 && k <= 127 ? NV_K_VAR + 128 * l[0] + k : -1;
}
static thread_local double g_raga_sw[12];
// A MELODIC NOTE THAT BORROWS A KIT KEY'S STROKES (sfx_strokes_of: the Morse
// keyboard's characters): the drum sets' tables its template's song reads, as
// a file's song has them (nvrender's) -- set by a melodic cache that has them
static thread_local const nv::live::Kits *g_tmpl_stk = nullptr;

static long long template_rows(const NoteClass *const *K, const NoteIn *tmpl, const double *freq,
                               const double *trim, int program, int note, int vel, int fast, double **rowsp,
                               const int *kind, double scale, double full_db_s, double residual, double beta,
                               long long blk, double ring_floor, double ring_max, double *out, double knee_db,
                               double ln10_20, double xdec_nepers, double SR, void **dm, const nv::live::Kits *kit,
                               std::vector<long long> *srows, std::vector<long long> *prows = nullptr,
                               const double *les = nullptr, std::vector<long long> *flips = nullptr,
                               std::vector<double> *jrows = nullptr, std::vector<long long> *rrows = nullptr,
                               double *mft = nullptr, std::vector<long long> *grows = nullptr);
long long nv_tremolo_expand(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                            const double *cfg, const char *mask, long long nmask, double sr);
long long nv_leslie_expand(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                           const int *nreq, const double *req, double sr, const double *L, void **lobe,
                           long long **flips, long long *nflips);
void nv_leslie_params(long n, const double *nf, const char *flip, const double *L, char *horn, float *fl, float *sh,
                      double *nrm);

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

struct NvSirRow {                       // (nv_song_sirens: a rotor's row -- nvrender.cpp's twin)
    long long ch;
    std::vector<float> r, l;
    std::vector<double> c;
};

// THE FIRE SIRENS' ROTORS (_prep_siren, siren.py): each (channel, key)'s
// notes in their order, its rotor carried key to key -- wound up by its
// motor while held (to its gate where a held texture has one), coasting
// after and between presses -- a row each, after the others: its speed a
// block (the mean ratio), its phase summed from it, its level at each
// edge; the note sounding to the rotor's floor or the next press
// -- in the library, so live's templates make them as a file's render does:
// sbase the first siren row's index, the rows into *sirp
void nv_song_sirens(void *song, const NoteClass *const *K, int nK, double total, double SR, long long BLK, int sbase,
                    std::vector<NvSirRow> *sirp)
{
    typedef NvSirRow SirRow;
    std::vector<NvSirRow> &sir = *sirp;
    auto pmx = [](double a, double b) { return b > a ? b : a; };    // (Python's max and min)
    auto pmn = [](double a, double b) { return b < a ? b : a; };
    // siren.FIRE, siren.HELMHOLTZ (its air_tau; U_LOW its tone's fade-in)
    double A = 0.723, Bc = 0.0908, W = (A + Bc) / A, TAU = 0.0;
    const double UK = 0.452, NE = 3.8, FLOOR = pow(10.0, -60.0 / 20.0), ULOW = 0.12;
    auto model = [&](int kind) {
        A = kind == 2 ? 1.50 : 0.723;
        Bc = kind == 2 ? 0.17 : 0.0908;
        TAU = kind == 2 ? 0.04 : 0.0;
        W = (A + Bc) / A;
    };
    auto air_step = [&](double air, double p, double dt) {
        return TAU <= 0.0 ? p : p + (air - p) * exp(-dt / TAU);
    };
    auto blown = [&](double u, double air) {
        return sqrt(pmx(air, 0.0)) * (u * u / (u * u + ULOW * ULOW));
    };
    // (_stepv: the last event at or before tt, d before any)
    auto stepv = [](const std::vector<std::pair<double, int>> &ev, double tt) {
        double x = 0.0;
        for (const auto &e : ev) {
            if (e.first <= tt + 1e-9)
                x = e.second;
            else
                break;
        }
        return x;
    };
    auto press = [&](long long c, int key) {
        std::vector<std::pair<double, int>> ev;
        int n = nv_song_press_get(song, c, key, 0, nullptr, nullptr);
        std::vector<double> t(n);
        std::vector<int> v(n);
        nv_song_press_get(song, c, key, n, t.data(), v.data());
        for (int q = 0; q < n; q++)
            ev.push_back(std::make_pair(t[q], v[q]));
        return ev;
    };
    auto cc_ev = [&](long long c, int cc) {     // (sorted((t, v) for the channel's cc): Python's tuples)
        std::vector<std::pair<double, int>> ev;
        int n = nv_song_cc_get(song, c, cc, 0, nullptr, nullptr);
        std::vector<double> t(n);
        std::vector<int> v(n);
        nv_song_cc_get(song, c, cc, n, t.data(), v.data());
        for (int q = 0; q < n; q++)
            ev.push_back(std::make_pair(t[q], v[q]));
        std::sort(ev.begin(), ev.end());
        return ev;
    };
    auto step = [&](double u, double p, double dt) {
        double k = A * p + Bc;
        if (k <= 0.0)
            return u;
        double target = A * p * W * sqrt(pmx(p, 0.0)) / k;
        return target + (u - target) * exp(-k * dt);
    };
    auto mean_over = [&](double u, double p, double dt) {
        double k = A * p + Bc;
        if (k <= 0.0 || dt <= 0.0)
            return u;
        double target = A * p * W * sqrt(pmx(p, 0.0)) / k;
        return target + (u - target) * (1.0 - exp(-k * dt)) / (k * dt);
    };
    auto level = [&](double u) {
        if (u <= 0.0)
            return 0.0;
        double x = pow(u / UK, NE), x1 = pow(1.0 / UK, NE);
        return sqrt((x / (1.0 + x)) / (x1 / (1.0 + x1)));
    };
    auto floordiv = [](double a, double b) {    // Python's float a // b
        double mod = fmod(a, b), div = (a - mod) / b;
        if (mod != 0.0 && ((b < 0.0) != (mod < 0.0)))
            div -= 1.0;
        double f = floor(div);
        if (div - f > 0.5)
            f += 1.0;
        return f;
    };
    const long nblk_ = (long)(((long long)(total * SR) + (long long)SR) / (long long)BLK + 2);
    const double bdt = BLK / SR;
    // (keyed (channel, key, kind) as _sir_keys is: kind 1 the fire siren's, 2 the Helmholtz's)
    typedef std::tuple<long long, int, int> SirKey;
    std::vector<SirKey> order;
    std::map<SirKey, std::vector<std::tuple<double, double, int>>> byk;
    for (int i = 0, n = nv_song_n_notes(song); i < n; i++) {
        long long c;
        int iv[4];
        double dv[2];
        nv_song_get_note(song, i, &c, iv, dv);
        int q = nv_song_kidx(song, i);
        const NoteClass *k = (q >= 0 && q < nK) ? K[q] : nullptr;
        if (!k || !k->siren)
            continue;
        auto key = std::make_tuple(c, iv[0], k->siren);
        if (!byk.count(key))
            order.push_back(key);
        byk[key].push_back(std::make_tuple(dv[0], dv[1], i));
    }
    for (const auto &key : order) {
        auto &ns = byk[key];
        const long long kc = std::get<0>(key);
        const int kind = std::get<2>(key);
        model(kind);
        auto vel_of = [&](int i) {
            long long c;
            int iv[4];
            double dv[2];
            nv_song_get_note(song, i, &c, iv, dv);
            return iv[1];
        };
        std::stable_sort(ns.begin(), ns.end(), [&](const std::tuple<double, double, int> &a,
                                                   const std::tuple<double, double, int> &b) {
            if (std::get<0>(a) != std::get<0>(b))
                return std::get<0>(a) < std::get<0>(b);
            if (std::get<1>(a) != std::get<1>(b))
                return std::get<1>(a) < std::get<1>(b);
            return vel_of(std::get<2>(a)) < vel_of(std::get<2>(b));   // (then the velocity: the tuples')
        });
        // the air's sources (the Helmholtz siren's): the channel's
        // aftertouch, the key's, CC2 -- and the crank, CC20 (tonelib.WHEEL_CC)
        std::vector<std::pair<double, int>> at, pt, c2, c1;
        if (kind == 2) {
            at = press(kc, -1);
            pt = press(kc, std::get<1>(key));
            c2 = cc_ev(kc, 2);
            c1 = cc_ev(kc, NV_CC_CRANK);
        }
        double u = 0.0, air = 0.0, tprev = NAN;
        for (size_t j = 0; j < ns.size(); j++) {
            double on = std::get<0>(ns[j]), of = std::get<1>(ns[j]);
            const NoteClass *k = K[nv_song_kidx(song, std::get<2>(ns[j]))];
            const double pv = vel_of(std::get<2>(ns[j])) / 127.0;
            if (!std::isnan(tprev) && on > tprev) {
                u *= exp(-Bc * (on - tprev));           // (Rotor.coast)
                air = air_step(air, 0.0, on - tprev);
            }
            double drive_end = of;
            if (k->held_texture && k->gate_time > 0.0)
                drive_end = pmx(of, on + k->gate_time);
            double cap = j + 1 < ns.size() ? std::get<0>(ns[j + 1]) : INFINITY;
            long b0 = (long)floordiv(on * SR, (double)BLK);
            std::vector<double> r, lv;
            long kb = b0;
            double end;
            for (;;) {
                double tb = kb * bdt;
                if (tb >= cap || kb >= nblk_) {
                    end = pmn(cap, nblk_ * bdt);
                    break;
                }
                double tm = tb + 0.5 * bdt;
                double p = 0.0;
                if (tm < drive_end)
                    p = kind == 1 ? 1.0 : pmx(pmx(pmx(pv, stepv(at, tm) / 127.0), stepv(pt, tm) / 127.0),
                                              stepv(c2, tm) / 127.0);
                double l0 = kind == 1 ? level(u) : blown(u, air);
                double rr = mean_over(u, p, bdt);
                u = step(u, p, bdt);
                air = air_step(air, p, bdt);
                double l1 = kind == 1 ? level(u) : blown(u, air);
                r.push_back(rr);
                lv.push_back(l0);
                kb++;
                if (tb >= drive_end) {
                    if (kind == 1 ? l1 <= FLOOR : air <= 1e-3 * pmx(pv, 1e-3)) {
                        end = kb * bdt;
                        break;
                    }
                }
            }
            lv.push_back(kind == 1 ? level(u) : blown(u, air));
            if (kind == 2)                  // (the velocity's gain is the onset's level)
                for (double &x : lv)
                    x = x / sqrt(pmx(pv, 1e-3));
            tprev = pmn(end, cap);
            SirRow row;
            row.ch = kc;
            row.r.assign(nblk_, 1.0f);
            long nn = std::min((long)r.size(), nblk_ - b0);
            for (long q = 0; q < nn; q++)
                row.r[b0 + q] = (float)r[q];
            if (nn > 0)
                for (long q = b0 + nn; q < nblk_; q++)
                    row.r[q] = (float)r[nn - 1];
            row.l.assign(nblk_ + 1, 1.0f);
            long nl = std::min((long)lv.size(), std::max(nn, 0L) + 1);
            for (long q = 0; q < nl && b0 + q < nblk_ + 1; q++)
                row.l[b0 + q] = (float)lv[q];
            for (long q = b0 + nl; q < nblk_ + 1; q++)
                row.l[q] = (float)lv[nl - 1];
            row.c.assign(nblk_, 0.0);
            double acc = 0.0;               // (the phase: cumsum of (ratio - 1) x BLK, from 0)
            for (long q = 0; q + 1 < nblk_; q++) {
                acc = acc + ((double)row.r[q] - 1.0) * BLK;
                row.c[q + 1] = acc;
            }
            nv_song_siren(song, kc, std::get<1>(key), on, (double)(sbase + (int)sir.size()), tprev);
            const bool upper = k->organ && k->organ->siren_up;
            SirRow up;
            if (upper) {
                // THE CRANK (siren.crank_samples): the upper chest's angle as
                // samples of phase at each block's start, from the wheel --
                // its ratio the lower's moved while the wheel moves, its
                // phase the lower's plus the angle, exactly
                double tab[128];
                nv_song_table(song, kc, on, tab);
                const double frev = tab[std::get<1>(key)] / 12.0;
                std::vector<double> dl(nblk_ + 1, 0.0);
                for (long q = b0; q < std::min(b0 + nn + 1, nblk_ + 1); q++) {
                    int c1v = (int)stepv(c1, q * bdt);
                    double th = (M_PI / 12.0) * (double)std::max(0, std::min(127, c1v)) / 127.0;
                    dl[q] = th * SR / (2.0 * M_PI * frev);
                }
                up.ch = kc;
                up.r.resize(nblk_);
                up.c.resize(nblk_);
                for (long q = 0; q < nblk_; q++) {
                    up.r[q] = (float)((double)row.r[q] + (dl[q + 1] - dl[q]) / BLK);
                    up.c[q] = row.c[q] + dl[q];
                }
                up.l = row.l;
            }
            sir.push_back(std::move(row));
            if (upper) {
                nv_song_siren_up(song, kc, std::get<1>(key), on, (double)(sbase + (int)sir.size()));
                sir.push_back(std::move(up));
            }
        }
    }
}

// ...and its strokes' rows (srows: [first, end) pairs, the song's stroke_rows)
static long long template_rows(const NoteClass *const *K, const NoteIn *tmpl, const double *freq,
                               const double *trim, int program, int note, int vel, int fast, double **rowsp,
                               const int *kind, double scale, double full_db_s, double residual, double beta,
                               long long blk, double ring_floor, double ring_max, double *out, double knee_db,
                               double ln10_20, double xdec_nepers, double SR, void **dm, const nv::live::Kits *kit,
                               std::vector<long long> *srows, std::vector<long long> *prows, const double *les,
                               std::vector<long long> *flips, std::vector<double> *jrows,
                               std::vector<long long> *rrows, double *mft, std::vector<long long> *grows)
{
    // (a variation's: its first layer's slot -- var_entry, var_kidx)
    const int ven = kit ? 0 : var_entry(program, g_tmpl_var);
    auto kat = [&](int key) -> const NoteClass * {
        if (kit || program < 0 || program > 127)
            return nullptr;
        if (ven) {
            int q = var_kidx(ven, key);
            return q >= 0 ? K[q] : nullptr;
        }
        return K[128 * program + key];
    };
    const NoteClass *kc = kat(note);
    const OrganSpec *og = kc ? kc->organ : nullptr;
    // (a drone-wheel program's: built with its drones CORKED, CC18 = 0 --
    // live sounds them as its own held voices, live._raw_template's)
    const NoteClass *pc_ = kat(60);
    const bool cork = pc_ && pc_->drone_wheel;
    const int fast_cc = pc_ && pc_->detune_wheel ? NV_CC_DETUNE : NV_CC_LESLIE;
    // (a map's own set, 128 + j: as a file selects it -- CC32 = its map, then
    // its program -- and the reader's kit_in_map plays it; live._raw_template's)
    const int mid = kit && program >= 128 && program - 128 < (int)g_mapk_ids.size() ? g_mapk_ids[program - 128] : -1;
    std::vector<uint8_t> f = mid >= 0 ? nv::live::one_note(mid & 127, note, vel, 9, fast, 480 * 18, nullptr, 128 * (mid >> 7))
                           : kit ? nv::live::one_note(program, note, vel, 9, fast, 480 * 18)
                                 : nv::live::one_note(program, note, vel, 0, fast, 480, og, (ven || (g_tmpl_var >> 12)) ? g_tmpl_var : 0, fast_cc, cork);
    int err = 0;
    void *m = nv_midi_read_plain(f.data(), (long long)f.size(), &err);
    if (!m)
        return -1000000001LL;
    void *song = nv_song_new();
    if (pc_ && (pc_->cut_semi || pc_->n_dchoice))   // (live's markers: the cut and the pungi's drone live's own)
        nv_song_live_template(song, pc_->cut_semi != 0, pc_->n_dchoice != 0);
    nv_song_tuning(song, -1, 0.0, freq);
    if (g_raga_sa >= 0)
        nv_song_eastern(song, nullptr, 1, g_raga_sa, g_raga_sw, g_raga_nsw);
    // (a melodic note's borrowed strokes: the sets' tables, as a file's song has them)
    const nv::live::Kits *stk = !kit && g_tmpl_stk && pc_ && pc_->sfx_prog >= 0 ? g_tmpl_stk : nullptr;
    if (kit || stk) {
        const nv::live::Kits *kt = kit ? kit : stk;
        // (A HELD ROLL's template: its first hit alone -- live._raw_template's
        // ROLL_FIRST; the rest struck as the key is held)
        const int rq = kit ? 128 * program + note
                           : kc && kc->sfx_prog >= 0 ? 128 * kc->sfx_prog + (kc->sfx_key >= 0 ? kc->sfx_key : note) : -1;
        if (rq >= 0 && rq < (int)kt->skind.size() && (kt->skind[rq] == 4 || kt->skind[rq] == 7))
            nv_song_roll_first(song);
        // (every set's keys: the 128's and the maps' own after them, nvrender's)
        nv_song_kits_n(song, kt->f0.data(), kt->seat.data(), (int)kt->f0.size());
        nv_song_chokes_n(song, kt->choke.data(), (int)kt->f0.size());
    }
    if (ven) {                              // (bank select's tables, before the note takes its variation)
        nv_song_vars(song, (int)g_var_nls.size(), g_var_nls.data(), g_var_ls.data(), g_var_trim.data(),
                     g_var_gs.data(), g_var_gm2.data());

        nv_song_slot_organs(song, (int)g_slot_organ.size(), g_slot_organ.data());
        nv_song_slot_orgs(song, (int)g_slot_organ.size(), g_slot_off.data(), g_slot_og.data());
    }
    nv_midi_song(m, song, trim);
    if (g_tmpl_cabk && (g_tmpl_var >> 20))  // (its knobs' voices: every note to its class's copy)
        nv_song_class_remap(song, [](void *ctx, int q) {
            const auto &mp = *(const std::map<int, int> *)ctx;
            auto it = mp.find(q);
            return it == mp.end() ? q : it->second;
        }, (void *)g_tmpl_cabk);
    else if (g_tmpl_cabk)                   // (its cabinet's voices: the note to its class's, Cache::cab_prep's)
        nv_song_cab_resolve(song, [](void *ctx, int q, int, int *) {
            const auto &mp = *(const std::map<int, int> *)ctx;
            auto it = mp.find(q);
            return it == mp.end() ? q : it->second;
        }, (void *)g_tmpl_cabk);
    if (kit) {
        // AN EDITED DRUM KEY's: the one-note file's drum NRPNs, the song's
        // (nvrender's dedit pass) -- its pitch and pan as the file's note has them
        int nd = nv_midi_n_dedit(m);
        if (nd) {
            std::vector<int> div(4 * (size_t)nd);
            std::vector<double> dt(nd);
            for (int i = 0; i < nd; i++)
                nv_midi_dedit(m, i, div.data() + 4 * i, dt.data() + i);
            nv_song_dedit(song, nd, div.data(), dt.data());
        }
    }
    // THE ORGANS ON ITS CHANNEL, its stops all drawn: the key's class's -- or
    // a variation's every organ, a family each (nvrender's ent_organs: the
    // Technorg Hit's drawbar layer is another family than its hit's)
    std::vector<const OrganSpec *> ogs;
    if (ven && g_var_nls[ven] >= 1) {
        const int sl = g_var_ls[4 * (size_t)g_var_off[ven]];
        if (sl >= 0 && sl + 1 < (int)g_slot_off.size())
            ogs.assign(g_slot_og.begin() + g_slot_off[sl], g_slot_og.begin() + g_slot_off[sl + 1]);
    }
    if (ogs.empty() && og)
        ogs.push_back(og);
    if (!ogs.empty()) {
        std::vector<const OrganSpec *> po(128, nullptr);
        po[program] = og;
        std::vector<int> fams;
        for (const OrganSpec *o : ogs) {
            if (std::find(fams.begin(), fams.end(), o->family) != fams.end())
                continue;
            fams.push_back(o->family);
            nv_song_organ(song, 0, o, po.data());
        }
        nv_song_organ_wind_rows(song, 0);   // (its rows' wind rows, as the one-note file has them)
    }
    if (kit)
        nv_song_strokes(song, kit->skind.data(), kit->spar.data());
    if (kit && (program == 64 || program == 65)) {
        // A USER DRUM SET's KEY (nvrender's pass): another set's key -- its
        // class, pitch and seat -- with its own play note, level, pan and Rx
        for (int i = 0, nn = nv_song_n_notes(song); i < nn; i++) {
            long long c_;
            int iv_[4];
            double dv_[2];
            nv_song_get_note(song, i, &c_, iv_, dv_);
            int u[13] = {0};
            int mm = iv_[3] && (iv_[2] == 64 || iv_[2] == 65) ? nv_midi_user_drum(m, iv_[2] - 64, iv_[0], u) : 0;
            if (!((mm >> 12) & 1))
                continue;
            const int sset = (mm >> 11) & 1 ? u[11] : 0, snote = u[12];
            int uv[9] = {0}, um = 0;
            if ((mm >> 1) & 1)
                uv[0] = u[1] - snote, um |= 1;
            if ((mm >> 2) & 1)
                uv[1] = u[2], um |= 2;
            if ((mm >> 4) & 1)
                uv[2] = u[4], um |= 4;
            if ((mm >> 8) & 1)
                uv[6] = u[8], um |= 64;
            nv_song_user_drum(song, i, 128 * sset + snote, um, uv);
        }
    }
    else if (stk)                           // (its class's kit key: nvrender's nv_song_strokes_k)
        nv_song_strokes_k(song, K, stk->skind.data(), stk->spar.data());
    double total = nv_midi_total(m);
    nv_song_finish(song, total);
    {                                       // a siren's rotor: its note's row and its end (_prep_siren)
        std::vector<NvSirRow> sir;
        nv_song_sirens(song, K, INT_MAX, total, SR, blk, 0, &sir);
    }
    PyRandom rs;
    pyr_seed(&rs, 0);                       // _prepare's random.seed(0)
    double qacc[18] = {0}, az = 0.0;
    nv_set_moog_neutral(1);                 // (a Moog's live template: knob-neutral, blockrender's MOOG_NEUTRAL)
    long long P = nv_prepare(song, K, tmpl, nullptr, 0, &rs, rowsp, qacc, &az, kind, scale, full_db_s, residual,
                             beta, blk, total, ring_floor, ring_max, out, knee_db, ln10_20, xdec_nepers, SR, dm, 0);
    nv_set_moog_neutral(0);
    if (mft) {                              // its Moog note's filter row (t["FT"]), NAN where none
        if (P < 0 || !nv_song_moog_ft(song, 0, mft))
            for (int q = 0; q < 30; q++)
                mft[q] = NAN;
    }
    if (srows && P >= 0) {
        int n = nv_song_n_stroke_rows(song, nullptr, 0);
        srows->resize(2 * n);
        nv_song_n_stroke_rows(song, srows->data(), n);
    }
    if (grows && P >= 0) {                      // ...and its grains' (_GRAIN_ROWS)
        int ng = nv_song_n_grain_rows(song, nullptr, 0);
        grows->resize(2 * ng);
        nv_song_n_grain_rows(song, grows->data(), ng);
    }
    if (rrows && P >= 0) {                      // ...and its key-up's rows (rel_rows)
        int nr = nv_song_n_rel_rows(song, nullptr, 0);
        rrows->resize(2 * nr);
        nv_song_n_rel_rows(song, rrows->data(), nr);
    }
    if (jrows && P >= 0) {                      // ...and its jacks' clicks (rel_jacks)
        int nj = nv_song_n_rel_jacks(song, nullptr, 0);
        jrows->resize(4 * nj);
        nv_song_n_rel_jacks(song, jrows->data(), nj);
    }
    if (prows && P >= 0) {                      // ...and its pushes' (push_rows)
        int np = nv_song_n_push_rows(song, nullptr, 0);
        prows->resize(2 * np);
        nv_song_n_push_rows(song, prows->data(), np);
    }
    if (P >= 0) {
        // AN ORDINARY VOICE'S TREMOLO (_prep_tremolo's, _note_tremolo): the
        // one-note file has no CC1, so an intrinsic one's (GM 44's stroke)
        int nv_ = nv_song_trems(song, nullptr, nullptr, 0);
        if (nv_ > 0) {
            std::vector<long long> vch(nv_);
            std::vector<double> vcfg(4 * nv_);
            nv_song_trems(song, vch.data(), vcfg.data(), nv_);
            nv_tremolo_expand(rowsp, &P, dm, nv_, vch.data(), vcfg.data(), nullptr, 0, SR);
        }
    }
    // THE VOICE's OWN CHORUS (_prep_chorus: the one-note file sends no CC93,
    // so a pedal's -- chorus_send, GS's Chorus Gt -- or a detuned pair's, GS's
    // Detuned EP and Organs), after the tremolos and before the cabinet, as
    // nvrender's: on the note's mix channel. (Live had them; native's
    // templates did not -- Detuned EP 1 played as the plain Rhodes.)
    if (P > 0 && !kit && kc && (kc->cho_send || kc->pair_set)) {
        long long mc = (long long)(*rowsp)[nv::live::emit_col("mch")];
        double send = kc->cho_send ? kc->cho_send : 1.0;
        int nc = kc->cho_send ? kc->n_cho : 2, ck = kc->cho_send ? 0 : 1;
        double cents[8], gsp[40] = {0};
        for (int q = 0; q < 8; q++)
            cents[q] = kc->cho_send ? (q < kc->n_cho ? kc->cho_cents[q] : 0.0)
                                    : q == 0 ? kc->pair_lo : q == 1 ? kc->pair_hi : 0.0;
        nv_chorus_expand(rowsp, &P, dm, 1, &mc, &send, &nc, cents, &ck, gsp, SR);
    }
    if (P >= 0)                                 // the speaker cabinet (_prep_cabinet), before any rotor
        nv_cabinet_pass(song, *rowsp, P);
    // A ROTARY VOICE'S CABINET (_raw_template: leslie.expand with SIDEBANDS
    // off): the cabinet's colour, the crossover's copies (leslie_flip), each
    // row's Doppler at the rotor's speed from the file's CC1 (fast), else the
    // voice's own -- the swing itself is the slab's
    g_tmpl_cone.clear();
    long long c_st = 0;
    if (les && P >= 0 && nv_song_leslie(song, -1, nullptr) > 0 && nv_song_leslie(song, 0, &c_st) >= 8) {
        // A SPECTRA-TONE (leslie.expand's branch: the rows' levels their own,
        // no copies): each sounding row of its channel's place in the cone
        // table -- spectratone.bin_coord, from the row's own nf (live's
        // template: lfl from p's, lsh -1, lsr 0)
        long long c;
        int kind_ = nv_song_leslie(song, 0, &c);
        const std::vector<double> *sp = g_tmpl_spec;
        if (sp && sp->size() >= 11) {
            const double f0 = (*sp)[2], bpo = (*sp)[3], nb = (*sp)[0], mode = (double)((kind_ - 8) / 2);
            const int cMCH = nv::live::emit_col("mch"), cNF = nv::live::emit_col("nf");
            g_tmpl_cone.assign((size_t)P, NAN);
            for (long long i = 0; i < P; i++) {
                const double *r = *rowsp + (size_t)NCOLS * i;
                if ((long long)r[cMCH] != c || r[cNF] <= 0.0)
                    continue;
                const double f = r[cNF];
                double u = log2((f > f0 ? f : f0) / f0) * bpo;
                if (u > nb - 1.001)
                    u = nb - 1.001;
                g_tmpl_cone[(size_t)i] = (float)(mode * nb + u);
            }
        }
    } else if (les && P >= 0 && nv_song_leslie(song, -1, nullptr) > 0) {
        long long c;
        int kind_ = nv_song_leslie(song, 0, &c);
        int nc = nv_song_ccs(song, c, NV_CC_LESLIE, nullptr, nullptr, 0);
        std::vector<double> ct(nc), req;
        std::vector<int> cv(nc);
        nv_song_ccs(song, c, NV_CC_LESLIE, ct.data(), cv.data(), nc);
        if (nc == 0 || ct[0] > 0.0) {
            req.push_back(0.0);
            req.push_back(kind_ == 2 ? les[4] : les[3]);
        }
        for (int q = 0; q < nc; q++) {
            req.push_back(ct[q]);
            req.push_back(cv[q] < 42 ? 0.0 : cv[q] < 85 ? les[3] : les[4]);     // leslie.zone
        }
        int nq = (int)req.size() / 2;
        long long *fl = nullptr, nfl = 0;
        nv_leslie_expand(rowsp, &P, dm, 1, &c, &nq, req.data(), SR, les, nullptr, &fl, &nfl);
        if (flips)
            flips->assign(fl, fl + nfl);
        free(fl);
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
                           "nfr", "lfl", "lsh"};        // (the last two the Spectra-Tone's: not emitted, set by build)
static const char *F4N[] = {"gb", "gt", "gc", "vdl"};
static const char *I4[] = {"gr", "cr", "br", "pl", "fx", "mk", "lsr"};
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

// tremolo.expand: every row of a modulated channel (in mask, when given: a
// Tremolo stop's notes) its sideband pair, appended in order -- the upper
// then the lower, at the rate either side of the row's, each half the depth
// (a pan's right ear the opposite sign, its mono sum none); a section's
// players each their own rate and phase (scatter). The rows NCOLS each,
// *P of them, realloc'd; a damper's dk/dg (dm[0], dm[1]) copied with them.
// The channels nch of chans, each's (rate, depth, stereo, scatter) in cfg;
// mask nmask long (NULL: every row). Returns the sidebands made.
// blockrender.gsd_place's memo, the render's: (output, whole Hz) -> that
// whole Hz's (gL, gR, dL, dR) -- whoever asks first -- shared by the GS delay's repeats and
// the chorus device's copies, in the order they ask (the delay's first)
static std::map<std::pair<double, long long>, std::array<double, 4>> g_gsd_place;
// (its keys as Python's: an output 10 + its index ('l', 'r', 'c'), a pan the
// pan itself (-1..1: a pitch shifter's, a Hexa Chorus's voice), an angle 1000
// + its degrees -- one memo, so a pan two effects share is one entry)

extern "C" void nv_gsd_place_reset(void) { g_gsd_place.clear(); }

// output side (0 l, 1 r, 2 c) at frequency f: pl the head's beta, then each
// output's (left incidence, right incidence, left delay, right delay)
extern "C" void nv_gsd_place4(int key, double f, double beta, const double *P, double *out);
extern "C" void nv_gsd_place4k(double key, double f, double beta, const double *P, double *out);
extern "C" void nv_gsd_place(int side, double f, const double *pl, double *out)
{
    nv_gsd_place4k(10.0 + side, f, pl[0], pl + 1 + 4 * side, out);
}

// ...an output or a pan given by its incidences and delays (P: li, ri, dL,
// dR), under its own key in the same memo (a pan's: 100 + its value)
extern "C" void nv_gsd_place4(int side, double f, double beta, const double *P, double *out)
{
    nv_gsd_place4k(side >= 100 ? (side - 100 - 64) / 63.0 : 10.0 + side, f, beta, P, out);
}

extern "C" void nv_gsd_place4k(double side, double f, double beta, const double *P, double *out)
{
    auto key = std::make_pair(side, (long long)f);
    auto it = g_gsd_place.find(key);
    if (it == g_gsd_place.end()) {
        auto hg = [&](double inc) {     // (SynthProperties.hrtf_gain)
            const double alpha_min = 0.1, theta_min = 150.0 * M_PI / 180.0;
            double alpha = 1.0 + alpha_min / 2.0 + (1.0 - alpha_min / 2.0) * cos(inc * M_PI / theta_min);
            double omega = 2.0 * M_PI * (double)key.second;
            return sqrt(pow(alpha * omega, 2.0) + pow(beta, 2.0)) / sqrt(pow(omega, 2.0) + pow(beta, 2.0));
        };
        it = g_gsd_place.emplace(key, std::array<double, 4>{hg(P[0]), hg(P[1]), P[2], P[3]}).first;
    }
    for (int q = 0; q < 4; q++)
        out[q] = it->second[q];
}

// AN INSERTION EFFECT's MIX FOLLOWING THE FILE (gsefx.mix_share, chorus.expand's
// fourth): channel q's share at each row's onset, the last time (s) at or
// before it -- given before nv_chorus_expand (a device of kind 2), used by it
static std::map<int, std::pair<std::vector<double>, std::vector<double>>> g_cho_steps;
static std::map<int, bool> g_cho_samples;  // (a channel's steps in samples, step_at's; else seconds)
// ...and its VOICES where the device's are not GS_TAPS' two (gsefx._chorus's
// taps): each (key, li, ri, dL, dR, LFO phase, extra delay s, depth factor),
// placed by its own incidences under its key in gsd_place's memo
static std::map<int, std::vector<double>> g_cho_taps;
extern "C" void nv_chorus_taps(int q, int n, const double *taps)
{
    g_cho_taps[q] = std::vector<double>(taps, taps + 8 * n);
}
extern "C" void nv_chorus_share_steps(int q, int n, const double *ts, const double *vals)
{
    g_cho_steps[q] = std::make_pair(std::vector<double>(ts, ts + n), std::vector<double>(vals, vals + n));
    g_cho_samples[q] = false;
}

// ...a CC93 that moves (_note_chorus_send's step table, step_at): its changes in samples
extern "C" void nv_chorus_share_steps_n(int q, int n, const double *ts, const double *vals)
{
    g_cho_steps[q] = std::make_pair(std::vector<double>(ts, ts + n), std::vector<double>(vals, vals + n));
    g_cho_samples[q] = true;
}

extern "C" long long nv_chorus_expand(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                                      const double *sends, const int *ncents, const double *cents,
                                      const int *kinds, const double *gsp, double sr)
{
    // chorus.py's SWEEP_HZ, DELAY_S, SWEEP_DEPTH, FLOOR
    static const double SWEEP_HZ[4] = {0.21, 0.29, 0.17, 0.34}, DELAY_S[4] = {0.007, 0.011, 0.013, 0.017};
    const double SWEEP_DEPTH = 0.0016, FLOOR = 0.02;
    const int cOM = emit_col("om"), cP0 = emit_col("p0"), cP0R = emit_col("p0R"), cAL = emit_col("aL"),
              cAR = emit_col("aR"), cAM = emit_col("aM"), cMCH = emit_col("mch"), cNF = emit_col("nf"),
              cVD = emit_col("vd"), cVR = emit_col("vr"), cVP = emit_col("vp");
    const long long n = *Pp;
    double *rows = *rowsp;
    // the columns as they were (np.array of A's): the copies are made from them
    std::vector<double> om(n), nf(n), p0(n), p0R(n), aL(n), aR(n), aM(n);
    for (long long i = 0; i < n; i++) {
        const double *r = rows + (size_t)NCOLS * i;
        om[i] = r[cOM]; nf[i] = r[cNF]; p0[i] = r[cP0]; p0R[i] = r[cP0R];
        aL[i] = r[cAL]; aR[i] = r[cAR]; aM[i] = r[cAM];
    }
    std::vector<double> extra;
    std::vector<long long> src;
    long long made = 0;
    const int cNON = emit_col("non"), cNOFF = emit_col("noff"), cNFR = emit_col("nfr"), cDL = emit_col("delL"),
              cDR = emit_col("delR"), cFMW = emit_col("fmw"), cFMP = emit_col("fmp"), cFMPR = emit_col("fmpR"),
              cVDL = emit_col("vdl");
    for (int q = 0; q < nch; q++) {
        if (kinds && kinds[q] == 2) {
            // A CHORUS DEVICE (chorus.gs_copies: a tone's insertion effect's
            // chorus): each output's copies of the channel's rows, a pass a
            // round of its feedback, placed at the output, the LFO free
            const double *G = gsp + 40 * q;
            const double tau = G[0], rate = G[1], vd = G[2], fb = G[3], lpf = G[4];
            auto tov = g_cho_taps.find(q);
            const double *TV = tov != g_cho_taps.end() ? tov->second.data() : nullptr;
            const int ntap = TV ? (int)(tov->second.size() / 8) : (int)G[6];
            std::vector<long long> sel;
            for (long long i = 0; i < n; i++)
                if ((long long)rows[(size_t)NCOLS * i + cMCH] == chans[q])
                    sel.push_back(i);
            // the share: the device's, or each row's (its onset's step)
            auto stp = g_cho_steps.find(q);
            std::vector<double> share(sel.size(), G[5]);
            if (stp != g_cho_steps.end()) {
                const std::vector<double> &ts = stp->second.first, &vs = stp->second.second;
                const bool samp = g_cho_samples[q];
                for (size_t j = 0; j < sel.size(); j++) {
                    double x = samp ? rows[(size_t)NCOLS * sel[j] + cNON] : rows[(size_t)NCOLS * sel[j] + cNON] / sr;
                    long i = (long)(std::upper_bound(ts.begin(), ts.end(), x) - ts.begin()) - 1;
                    share[j] = vs[i < 0 ? 0 : i >= (long)vs.size() ? (long)vs.size() - 1 : i];     // (before the first: the first)
                }
            }
            bool any = false;
            for (double x : share)
                any = any || x > 0.0;
            if (sel.empty() || !any)
                continue;
            const double fb2 = pow(fb, 2.0);
            const double passes = fb2 < 1.0 ? (1.0 - pow(fb2, 16.0)) / (1.0 - fb2) : 16.0;
            std::vector<double> wet(sel.size());
            for (size_t j = 0; j < sel.size(); j++)
                wet[j] = sqrt(share[j] / (double)ntap / passes);
            std::vector<double> non(sel.size()), noff(sel.size()), ph0(sel.size()), ph0R(sel.size()), fmp(sel.size()),
                fmpR(sel.size()), fmw(sel.size()), f(sel.size());
            for (size_t j = 0; j < sel.size(); j++) {
                const double *r = rows + (size_t)NCOLS * sel[j];
                long long i = sel[j];
                non[j] = r[cNON];
                noff[j] = r[cNOFF];
                ph0[j] = p0[i] + om[i] * (r[cNON] + r[cDL]);
                ph0R[j] = p0R[i] + om[i] * (r[cNON] + r[cDR]);
                fmp[j] = r[cFMP]; fmpR[j] = r[cFMPR]; fmw[j] = r[cFMW];
                f[j] = om[i] * sr / (2.0 * M_PI);
            }
            long long made_q = 0;
            for (int ti = 0; ti < ntap; ti++) {
                const double *tv = TV ? TV + 8 * ti : nullptr;
                const int side = tv ? 0 : (int)G[20 + 4 * ti];
                const double phase = tv ? tv[5] : G[21 + 4 * ti], ext = tv ? tv[6] : G[22 + 4 * ti],
                             dfac = tv ? tv[7] : G[23 + 4 * ti];
                std::vector<std::array<double, 4>> pl(sel.size());
                for (size_t j = 0; j < sel.size(); j++)
                    if (tv)                     // (a voice of its own: its pan or angle)
                        nv_gsd_place4k(tv[0], f[j], G[7], tv + 1, pl[j].data());
                    else
                        nv_gsd_place(side, f[j], G + 7, pl[j].data());     // (the render's memo: gsd_place)
                for (int k = 1; k <= 16; k++) {
                    const double fk = pow(fb, (double)(k - 1));
                    bool loud = false;          // (np.all(|g| < FLOOR / 2): the pass makes nothing)
                    for (size_t j = 0; j < sel.size(); j++)
                        loud = loud || !(fabs(wet[j] * fk) < FLOOR * 0.5);
                    if (!loud || (k > 1 && fb == 0.0))
                        break;
                    double d = (k * tau + ext) * sr;
                    for (size_t j = 0; j < sel.size(); j++) {
                        const double g = wet[j] * fk;
                        if (!(fabs(g) > 1e-12))
                            continue;           // (a row whose mix is 0 there makes no copy)
                        long long i = sel[j];
                        size_t o = extra.size();
                        extra.insert(extra.end(), rows + (size_t)NCOLS * i, rows + (size_t)NCOLS * (i + 1));
                        double *e = extra.data() + o;
                        double nn = non[j] + d;
                        e[cNON] = nn;
                        e[cNOFF] = noff[j] + d;
                        e[cNFR] = nn - floor(nn);
                        e[cDL] = pl[j][2];
                        e[cDR] = pl[j][3];
                        e[cP0] = -om[i] * (nn + pl[j][2]) + ph0[j];
                        e[cP0R] = -om[i] * (nn + pl[j][3]) + ph0R[j];
                        e[cFMP] = fmp[j] - fmw[j] * d;
                        e[cFMPR] = fmpR[j] - fmw[j] * d;
                        double lp = 1.0;
                        if (lpf != 0.0) {
                            double x = f[j] / lpf;
                            lp = 1.0 / sqrt(1.0 + x * x);
                        }
                        double m = fabs(aM[i]) * g * lp;
                        e[cAL] = m * pl[j][0];
                        e[cAR] = m * pl[j][1];
                        e[cAM] = aM[i] * g * lp;
                        double vk = k * vd * dfac;
                        e[cVD] = vk < 0.5 ? vk : 0.5;                   // (min(0.5, ...))
                        e[cVR] = rate;
                        double vp = 2.0 * M_PI * rate * nn / sr + phase, tw = 2.0 * M_PI;
                        double md = fmod(vp, tw);                        // (numpy's %: the divisor's sign)
                        if (md != 0.0) {
                            if ((tw < 0.0) != (md < 0.0))
                                md += tw;
                        } else {
                            md = copysign(0.0, tw);
                        }
                        e[cVP] = md;
                        e[cVDL] = 0.0;
                        src.push_back(i);
                        made++;
                        made_q++;
                    }
                }
            }
            // ...and the dry share comes down by what the copies took
            if (made_q)
                for (size_t j = 0; j < sel.size(); j++) {
                    double dry = sqrt(1.0 - share[j]);
                    if (dry != 1.0)
                        for (int c : {cAL, cAR, cAM})
                            rows[(size_t)NCOLS * sel[j] + c] = rows[(size_t)NCOLS * sel[j] + c] * dry;
                }
            continue;
        }
        double send = sends[q];
        int nc = ncents[q];
        if (send <= FLOOR || nc <= 0)
            continue;
        std::vector<long long> sel;
        for (long long i = 0; i < n; i++)
            if ((long long)rows[(size_t)NCOLS * i + cMCH] == chans[q])
                sel.push_back(i);
        if (sel.empty())
            continue;
        if (kinds && kinds[q] == 1) {
            // A DETUNED PAIR (chorus._pair): the rows moved down and left, a
            // copy up and right, each at half power (pair_side), the copy
            // delayed by the line's first delay
            double lo = pow(2.0, cents[8 * q] / 1200.0), hi = pow(2.0, cents[8 * q + 1] / 1200.0);
            const double PAIR_PAN = 0.5;
            double gl0 = pow(0.5 * (1.0 - PAIR_PAN * -1), 0.5), gr0 = pow(0.5 * (1.0 + PAIR_PAN * -1), 0.5);
            double gl1 = pow(0.5 * (1.0 - PAIR_PAN * 1), 0.5), gr1 = pow(0.5 * (1.0 + PAIR_PAN * 1), 0.5);
            double half = pow(0.5, 0.5), delay = DELAY_S[0];
            for (long long i : sel) {
                double *r = rows + (size_t)NCOLS * i;
                if (nf[i] * hi < sr * 0.5) {
                    size_t o = extra.size();
                    extra.insert(extra.end(), r, r + NCOLS);
                    double *e = extra.data() + o;
                    e[cOM] = om[i] * hi;
                    e[cNF] = nf[i] * hi;
                    e[cP0] = p0[i] * hi - om[i] * hi * delay * sr;
                    e[cP0R] = p0R[i] * hi - om[i] * hi * delay * sr;
                    e[cAL] = aL[i] * gl1;
                    e[cAR] = aR[i] * gr1;
                    e[cAM] = aM[i] * half;
                    src.push_back(i);
                    made++;
                }
                r[cOM] = om[i] * lo;
                r[cNF] = nf[i] * lo;
                r[cP0] = p0[i] * lo;
                r[cP0R] = p0R[i] * lo;
                r[cAL] = aL[i] * gl0;
                r[cAR] = aR[i] * gr0;
                r[cAM] = aM[i] * half;
            }
            continue;
        }
        double wet = pow(send / (double)nc, 0.5), dry = pow(1.0 - send, 0.5), gain = wet;
        for (int ci = 0; ci < nc; ci++) {
            double ratio = pow(2.0, cents[8 * q + ci] / 1200.0);
            double rate = SWEEP_HZ[ci % 4], delay = DELAY_S[ci % 4];
            for (long long i : sel) {
                if (!(nf[i] * ratio < sr * 0.5))
                    continue;
                size_t o = extra.size();
                extra.insert(extra.end(), rows + (size_t)NCOLS * i, rows + (size_t)NCOLS * (i + 1));
                double *e = extra.data() + o;
                e[cOM] = om[i] * ratio;
                e[cNF] = nf[i] * ratio;
                e[cP0] = p0[i] * ratio - om[i] * ratio * delay * sr;
                e[cP0R] = p0R[i] * ratio - om[i] * ratio * delay * sr;
                e[cAL] = aL[i] * gain;
                e[cAR] = aR[i] * gain;
                e[cAM] = aM[i] * gain;
                e[cVD] = SWEEP_DEPTH;
                e[cVR] = rate;
                e[cVP] = 2.0 * M_PI * ((double)ci / (double)nc);
                src.push_back(i);
                made++;
            }
        }
        // ...and the dry share comes down by what the wet took -- the
        // channel's, whatever copies were made (chorus.expand's)
        if (dry != 1.0)
            for (long long i : sel)
                for (int c : {cAL, cAR, cAM})
                    rows[(size_t)NCOLS * i + c] = rows[(size_t)NCOLS * i + c] * dry;
    }
    g_cho_steps.clear();
    g_cho_samples.clear();
    g_cho_taps.clear();
    long long m = (long long)src.size();
    if (!m)
        return 0;
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
    *Pp = n + m;
    return m;
}

// ONE ROW through channel q's chorus (nv_chorus_expand's, a stream's): a
// plain chorus's copies (kind 0: each voice ci at its cents, its sweep) or a
// detuned pair's (kind 1: the row moved down and left, its copy up and
// right), from the row as it was; its dry share taken off it. The copies
// into cp (NCOLS each, at most 8), their voice in ci; how many returned
// (-1: a chorus device, a stream's to refuse)
extern "C" int nv_chorus_row(double *r, int kind, double send, int nc, const double *cents, double sr, double *cp,
                             int *ci_out)
{
    static const double SWEEP_HZ[4] = {0.21, 0.29, 0.17, 0.34}, DELAY_S[4] = {0.007, 0.011, 0.013, 0.017};
    const double SWEEP_DEPTH = 0.0016, FLOOR = 0.02;
    const int cOM = emit_col("om"), cP0 = emit_col("p0"), cP0R = emit_col("p0R"), cAL = emit_col("aL"),
              cAR = emit_col("aR"), cAM = emit_col("aM"), cNF = emit_col("nf"), cVD = emit_col("vd"),
              cVR = emit_col("vr"), cVP = emit_col("vp");
    if (kind == 2)
        return -1;
    if (send <= FLOOR || nc <= 0)
        return 0;
    const double om = r[cOM], nf = r[cNF], p0 = r[cP0], p0R = r[cP0R], aL = r[cAL], aR = r[cAR], aM = r[cAM];
    int made = 0;
    if (kind == 1) {
        double lo = pow(2.0, cents[0] / 1200.0), hi = pow(2.0, cents[1] / 1200.0);
        const double PAIR_PAN = 0.5;
        double gl0 = pow(0.5 * (1.0 - PAIR_PAN * -1), 0.5), gr0 = pow(0.5 * (1.0 + PAIR_PAN * -1), 0.5);
        double gl1 = pow(0.5 * (1.0 - PAIR_PAN * 1), 0.5), gr1 = pow(0.5 * (1.0 + PAIR_PAN * 1), 0.5);
        double half = pow(0.5, 0.5), delay = DELAY_S[0];
        if (nf * hi < sr * 0.5) {
            double *e = cp;
            memcpy(e, r, sizeof(double) * NCOLS);
            e[cOM] = om * hi;
            e[cNF] = nf * hi;
            e[cP0] = p0 * hi - om * hi * delay * sr;
            e[cP0R] = p0R * hi - om * hi * delay * sr;
            e[cAL] = aL * gl1;
            e[cAR] = aR * gr1;
            e[cAM] = aM * half;
            ci_out[0] = 0;
            made = 1;
        }
        r[cOM] = om * lo;
        r[cNF] = nf * lo;
        r[cP0] = p0 * lo;
        r[cP0R] = p0R * lo;
        r[cAL] = aL * gl0;
        r[cAR] = aR * gr0;
        r[cAM] = aM * half;
        return made;
    }
    double wet = pow(send / (double)nc, 0.5), dry = pow(1.0 - send, 0.5), gain = wet;
    for (int ci = 0; ci < nc; ci++) {
        double ratio = pow(2.0, cents[ci] / 1200.0);
        double rate = SWEEP_HZ[ci % 4], delay = DELAY_S[ci % 4];
        if (!(nf * ratio < sr * 0.5))
            continue;
        double *e = cp + (size_t)NCOLS * made;
        memcpy(e, r, sizeof(double) * NCOLS);
        e[cOM] = om * ratio;
        e[cNF] = nf * ratio;
        e[cP0] = p0 * ratio - om * ratio * delay * sr;
        e[cP0R] = p0R * ratio - om * ratio * delay * sr;
        e[cAL] = aL * gain;
        e[cAR] = aR * gain;
        e[cAM] = aM * gain;
        e[cVD] = SWEEP_DEPTH;
        e[cVR] = rate;
        e[cVP] = 2.0 * M_PI * ((double)ci / (double)nc);
        ci_out[made] = ci;
        made++;
    }
    if (dry != 1.0)
        for (int c : {cAL, cAR, cAM})
            r[c] = r[c] * dry;
    return made;
}

// ONE ROW through a CHORUS DEVICE (nv_chorus_expand's kind 2, a stream's): G
// its record (40), TV its own voices (8 each, ntv of them; NULL: G's taps),
// share the row's at its onset, kmax the passes its channel makes (its
// loudest row's); the copies into cp (NCOLS each, cap of them), each's tap *
// 17 + pass in ix; returned. Where any copy is made (kmax > 0), the row's dry
// share comes off it, as the whole pass takes it off every row of the channel.
extern "C" int nv_chorus_dev_row(double *r, const double *G, const double *TV, int ntv, double share, int kmax,
                                 double sr, double *cp, int *ix, int cap)
{
    const int cOM = emit_col("om"), cP0 = emit_col("p0"), cP0R = emit_col("p0R"), cAL = emit_col("aL"),
              cAR = emit_col("aR"), cAM = emit_col("aM"), cVD = emit_col("vd"), cVR = emit_col("vr"),
              cVP = emit_col("vp"), cNON = emit_col("non"), cNOFF = emit_col("noff"), cNFR = emit_col("nfr"),
              cDL = emit_col("delL"), cDR = emit_col("delR"), cFMW = emit_col("fmw"), cFMP = emit_col("fmp"),
              cFMPR = emit_col("fmpR"), cVDL = emit_col("vdl");
    if (kmax <= 0)
        return 0;
    const double tau = G[0], rate = G[1], vd = G[2], fb = G[3], lpf = G[4];
    const int ntap = TV ? ntv : (int)G[6];
    const double fb2 = pow(fb, 2.0);
    const double passes = fb2 < 1.0 ? (1.0 - pow(fb2, 16.0)) / (1.0 - fb2) : 16.0;
    const double wet = sqrt(share / (double)ntap / passes);
    const double om = r[cOM], p0 = r[cP0], p0R = r[cP0R], aM = r[cAM];
    const double non = r[cNON], noff = r[cNOFF];
    const double ph0 = p0 + om * (r[cNON] + r[cDL]), ph0R = p0R + om * (r[cNON] + r[cDR]);
    const double fmp = r[cFMP], fmpR = r[cFMPR], fmw = r[cFMW];
    const double f = om * sr / (2.0 * M_PI);
    int made = 0;
    for (int ti = 0; ti < ntap; ti++) {
        const double *tv = TV ? TV + 8 * ti : nullptr;
        const int side = tv ? 0 : (int)G[20 + 4 * ti];
        const double phase = tv ? tv[5] : G[21 + 4 * ti], ext = tv ? tv[6] : G[22 + 4 * ti],
                     dfac = tv ? tv[7] : G[23 + 4 * ti];
        double pl[4];
        if (tv)
            nv_gsd_place4k(tv[0], f, G[7], tv + 1, pl);
        else
            nv_gsd_place(side, f, G + 7, pl);
        for (int k = 1; k <= kmax; k++) {
            const double fk = pow(fb, (double)(k - 1));
            const double d = (k * tau + ext) * sr;
            const double g = wet * fk;
            if (!(fabs(g) > 1e-12))
                continue;
            if (made >= cap)
                return -1;
            double *e = cp + (size_t)NCOLS * made;
            memcpy(e, r, sizeof(double) * NCOLS);
            double nn = non + d;
            e[cNON] = nn;
            e[cNOFF] = noff + d;
            e[cNFR] = nn - floor(nn);
            e[cDL] = pl[2];
            e[cDR] = pl[3];
            e[cP0] = -om * (nn + pl[2]) + ph0;
            e[cP0R] = -om * (nn + pl[3]) + ph0R;
            e[cFMP] = fmp - fmw * d;
            e[cFMPR] = fmpR - fmw * d;
            double lp = 1.0;
            if (lpf != 0.0) {
                double x = f / lpf;
                lp = 1.0 / sqrt(1.0 + x * x);
            }
            double m = fabs(aM) * g * lp;
            e[cAL] = m * pl[0];
            e[cAR] = m * pl[1];
            e[cAM] = aM * g * lp;
            double vk = k * vd * dfac;
            e[cVD] = vk < 0.5 ? vk : 0.5;
            e[cVR] = rate;
            double vp = 2.0 * M_PI * rate * nn / sr + phase, tw = 2.0 * M_PI;
            double md = fmod(vp, tw);
            if (md != 0.0) {
                if ((tw < 0.0) != (md < 0.0))
                    md += tw;
            } else {
                md = copysign(0.0, tw);
            }
            e[cVP] = md;
            e[cVDL] = 0.0;
            ix[made] = ti * 17 + k;
            made++;
        }
    }
    double dry = sqrt(1.0 - share);
    if (dry != 1.0)
        for (int c : {cAL, cAR, cAM})
            r[c] = r[c] * dry;
    return made;
}

// A CONTROLLER MATRIX's TREMOLO (blockrender: _CMX_TREM): a channel's map of
// the rows its sidebands ride instead of their parent's -- given before
// nv_tremolo_expand, used by it
static std::map<long long, std::map<long long, long long>> g_trem_brmap;
extern "C" void nv_tremolo_brmap(long long ch, int n, const long long *from, const long long *to)
{
    auto &m = g_trem_brmap[ch];
    for (int q = 0; q < n; q++)
        m[from[q]] = to[q];
}

// ...and an insertion effect's (gsefx: Tremolo, Auto Pan) a WAVEFORM: its
// harmonics (harmonic, coefficient, phase), each its own sideband pair --
// given before nv_tremolo_expand, used by it
static std::map<long long, std::vector<double>> g_trem_wave;
extern "C" void nv_tremolo_wave(long long ch, int n, const double *khp)
{
    g_trem_wave[ch] = std::vector<double>(khp, khp + 3 * n);
}

// ...and EACH ROW's OWN SETTING in its channel's place (tremolo.expand's
// cfgs: a harmonium note's Tremolo stop, read at its note-on), 4 a row
// (rate NaN: none), given before nv_tremolo_expand, used by it
static std::vector<double> g_trem_rcfg;
extern "C" void nv_tremolo_row_cfg(long long n, const double *cfg4) { g_trem_rcfg.assign(cfg4, cfg4 + 4 * n); }

// ONE ROW's SIDEBANDS (nv_tremolo_expand's, a stream's): c its setting (rate,
// depth, stereo, scatter), ch its channel (the scatter's seed), H its waveform's
// harmonics (nh of them; NULL: the plain pair) -- into out (NCOLS each, at most
// 2 nh or 2), in the whole pass's order; returned
extern "C" int nv_tremolo_row(const double *row, const double *c, long long ch, const double *H, int nh, double sr,
                              double *out)
{
    const int cOM = emit_col("om"), cP0 = emit_col("p0"), cP0R = emit_col("p0R"), cAL = emit_col("aL"),
              cAR = emit_col("aR"), cAM = emit_col("aM"), cPL = emit_col("pl");
    double rate = c[0], depth = c[1], scatter = c[3];
    const bool stereo = c[2] != 0.0;
    if (depth <= 0.0 || rate <= 0.0)
        return 0;
    double ph = 0.0;
    if (scatter > 0.0) {
        PyRandom r;
        pyr_seed(&r, 0x7E30 + ch * 977 + (long long)row[cPL]);
        rate = rate * (1.0 + scatter * pyr_uniform(&r, -1.0, 1.0));
        ph = pyr_uniform(&r, 0.0, 2.0 * M_PI);
    }
    const double dw = 2.0 * M_PI * rate / sr, half = 0.5 * depth;
    int m = 0;
    if (H) {
        for (int hk = 0; hk < nh; hk++) {
            const double k = H[3 * hk], ck = H[3 * hk + 1], pk = H[3 * hk + 2];
            const double hh = 0.5 * depth * ck;
            for (double sign : {1.0, -1.0}) {
                double *e = out + (size_t)NCOLS * m++;
                memcpy(e, row, sizeof(double) * NCOLS);
                e[cOM] = row[cOM] + sign * k * dw;
                e[cP0] = row[cP0] + sign * (k * ph + pk);
                e[cP0R] = row[cP0R] + sign * (k * ph + pk);
                e[cAL] = row[cAL] * hh;
                e[cAR] = row[cAR] * (stereo ? -hh : hh);
                e[cAM] = stereo ? 0.0 : row[cAM] * hh;
            }
        }
        return m;
    }
    for (double sign : {1.0, -1.0}) {
        double *e = out + (size_t)NCOLS * m++;
        memcpy(e, row, sizeof(double) * NCOLS);
        e[cOM] = row[cOM] + sign * dw;
        if (ph != 0.0) {
            e[cP0] = row[cP0] + sign * ph;
            e[cP0R] = row[cP0R] + sign * ph;
        }
        e[cAL] = row[cAL] * half;
        e[cAR] = row[cAR] * (stereo ? -half : half);
        e[cAM] = stereo ? 0.0 : row[cAM] * half;
    }
    return m;
}

extern "C" long long nv_tremolo_expand(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                                       const double *cfg, const char *mask, long long nmask, double sr)
{
    if (nch <= 0)
        return 0;
    const int cOM = emit_col("om"), cP0 = emit_col("p0"), cP0R = emit_col("p0R"), cAL = emit_col("aL"),
              cAR = emit_col("aR"), cAM = emit_col("aM"), cMCH = emit_col("mch"), cPL = emit_col("pl"),
              cBR = emit_col("br");
    const long long n = *Pp;
    std::vector<double> extra;
    std::vector<long long> src;
    std::map<long long, std::map<long long, long long>> brmap;
    brmap.swap(g_trem_brmap);
    std::map<long long, std::vector<double>> wave;
    wave.swap(g_trem_wave);
    std::vector<double> rcfg;
    rcfg.swap(g_trem_rcfg);
    std::vector<long long> chq(chans, chans + nch);
    for (long long i = 0; i < n; i++) {
        if (mask && (i >= nmask || !mask[i]))
            continue;
        const double *row = *rowsp + (size_t)NCOLS * i;
        int q = 0;
        const double *c;
        if (!rcfg.empty()) {                // (the row's own: its channel needs no entry)
            if (4 * i + 3 >= (long long)rcfg.size() || std::isnan(rcfg[4 * i]))
                continue;
            c = rcfg.data() + 4 * i;
            chq.push_back((long long)(int)row[cMCH]);
            q = (int)chq.size() - 1;
        } else {
            while (q < nch && chans[q] != (long long)(int)row[cMCH])
                q++;
            if (q == nch)
                continue;
            c = cfg + 4 * q;
        }
        const long long *chans_ = chq.data();
        (void)chans_;
        double rate = c[0], depth = c[1], scatter = c[3];
        bool stereo = c[2] != 0.0;
        if (depth <= 0.0 || rate <= 0.0)
            continue;
        double ph = 0.0;
        if (scatter > 0.0) {
            PyRandom r;
            pyr_seed(&r, 0x7E30 + chq[q] * 977 + (long long)row[cPL]);
            rate = rate * (1.0 + scatter * pyr_uniform(&r, -1.0, 1.0));
            ph = pyr_uniform(&r, 0.0, 2.0 * M_PI);
        }
        double dw = 2.0 * M_PI * rate / sr, half = 0.5 * depth;
        auto wv = wave.find(chq[q]);
        if (wv != wave.end()) {
            // A WAVEFORM'S HARMONICS, each its own sideband pair: k times the
            // rate, its coefficient's share of the depth, its phase (+ for the
            // upper, - for the lower, as the scatter's)
            const std::vector<double> &H = wv->second;
            for (size_t hk = 0; hk < H.size() / 3; hk++) {
                const double k = H[3 * hk], ck = H[3 * hk + 1], pk = H[3 * hk + 2];
                const double hh = 0.5 * depth * ck;
                for (double sign : {1.0, -1.0}) {
                    size_t o = extra.size();
                    extra.insert(extra.end(), row, row + NCOLS);
                    double *e = extra.data() + o;
                    e[cOM] = row[cOM] + sign * k * dw;
                    e[cP0] = row[cP0] + sign * (k * ph + pk);
                    e[cP0R] = row[cP0R] + sign * (k * ph + pk);
                    e[cAL] = row[cAL] * hh;
                    e[cAR] = row[cAR] * (stereo ? -hh : hh);
                    e[cAM] = stereo ? 0.0 : row[cAM] * hh;
                    auto bm = brmap.find(chq[q]);
                    if (bm != brmap.end()) {
                        auto it = bm->second.find((long long)row[cBR]);
                        if (it != bm->second.end())
                            e[cBR] = (double)it->second;
                    }
                    src.push_back(i);
                }
            }
            continue;
        }
        for (double sign : {1.0, -1.0}) {
            size_t o = extra.size();
            extra.insert(extra.end(), row, row + NCOLS);
            double *e = extra.data() + o;
            e[cOM] = row[cOM] + sign * dw;
            if (ph != 0.0) {
                e[cP0] = row[cP0] + sign * ph;
                e[cP0R] = row[cP0R] + sign * ph;
            }
            e[cAL] = row[cAL] * half;
            e[cAR] = row[cAR] * (stereo ? -half : half);
            e[cAM] = stereo ? 0.0 : row[cAM] * half;
            auto bm = brmap.find(chq[q]);
            if (bm != brmap.end()) {
                auto it = bm->second.find((long long)row[cBR]);
                if (it != bm->second.end())
                    e[cBR] = (double)it->second;
            }
            src.push_back(i);
        }
    }
    long long m = (long long)src.size();
    if (!m)
        return 0;
    double *rows = (double *)realloc(*rowsp, sizeof(double) * NCOLS * (size_t)(n + m));
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
    *Pp = n + m;
    return m;
}


struct Cache {
    std::vector<const NoteClass *> K;
    NoteIn t;
    double freq[128], trim[256];
    int kind[NCOLS], fin[NCOLS];
    double scale, full, residual, beta, ring_floor, ring_max, knee, ln10_20, xdec, SR;
    long long blk;
    std::map<std::tuple<int, int, int>, Template> tm;
    // AN EDITED DRUM KEY's TEMPLATES (drum_axis), built while playing (the
    // builder's, nv_tcache_build_var): each kept where it was made (vstore),
    // found through a map the audio thread reads by an atomic pointer, a
    // new copy published per build and the old kept till the cache goes
    typedef std::map<std::tuple<int, int, int>, const Template *> VMap;
    std::vector<std::unique_ptr<Template>> vstore;
    std::atomic<const VMap *> vmap{nullptr};
    std::vector<std::unique_ptr<VMap>> vgrave;
    long nseq = 0;                      // (the templates built so far: each one's seq)
    // TEMPLATES ADDED WHILE IT PLAYS (on demand: a note that found none, then
    // its octave): the audio thread finds every template through `slot`, an
    // atomic pointer per (key, bucket, speed) set once the template is
    // whole, and never reads tm; tm is written under tmu (a std::map's
    // nodes stay put, so a slot's pointer holds). The shape is the first
    // warm's (its buckets and wheel steps); a second of another shape turns
    // the slots off (s_nb < 0: tm read as before, nothing added)
    std::mutex tmu;
    int s_nb = 0, s_nsp = 0, s_sp[8] = {0};
    std::unique_ptr<std::atomic<const Template *>[]> slot;
    // (the slot of (note, bucket, speed): -1 none)
    long slot_of(int note, int bucket, int speed) const
    {
        if (s_nb <= 0 || note < 0 || note > 127 || bucket < 0 || bucket >= s_nb)
            return -1;
        for (int q = 0; q < s_nsp; q++)
            if (s_sp[q] == speed)
                return ((long)note * s_nb + bucket) * s_nsp + q;
        return -1;
    }
    // (a warm's shape: the slots made at the first, every template there so far in them)
    void shape(int nb, const int *speeds, int nsp)
    {
        if (s_nb < 0)
            return;
        if (s_nb > 0) {
            bool same = nb == s_nb && nsp == s_nsp;
            for (int q = 0; same && q < nsp; q++)
                same = speeds[q] == s_sp[q];
            if (!same)
                s_nb = -1;
            return;
        }
        if (nb <= 0 || nsp <= 0 || nsp > 8) {
            s_nb = -1;
            return;
        }
        s_nb = nb;
        s_nsp = nsp;
        for (int q = 0; q < nsp; q++)
            s_sp[q] = speeds[q];
        const long n = 128L * nb * nsp;
        slot.reset(new std::atomic<const Template *>[n]);
        for (long i = 0; i < n; i++)
            slot[i].store(nullptr, std::memory_order_relaxed);
        for (auto &kv : tm) {
            long ix = slot_of(std::get<0>(kv.first), std::get<1>(kv.first), std::get<2>(kv.first));
            if (ix >= 0)
                slot[ix].store(&kv.second, std::memory_order_release);
        }
    }
    // (a template kept: into tm, then its slot)
    const Template *keep(const std::tuple<int, int, int> &k, Template &&T)
    {
        Template *p;
        {
            std::lock_guard<std::mutex> lk(tmu);
            p = &(tm[k] = std::move(T));
        }
        long ix = slot_of(std::get<0>(k), std::get<1>(k), std::get<2>(k));
        if (ix >= 0)
            slot[ix].store(p, std::memory_order_release);
        return p;
    }
    bool drums = false;                 // a drum part: the program is its set (kit's tables)
    int var = 0;                        // its variation key (live.Patch.variation: map x 128 + bank), 0 none

    // the class a key plays: the variation's (its first layer's slot), else the program's
    const NoteClass *cls(int program, int key) const
    {
        if (drums && program >= 128 && program < 128 + g_mapk_n && key >= 0 && key <= 127)
            return K[g_mapk_base + 128 * (program - 128) + key];    // (a map's own set)
        if (program < 0 || program > 127 || key < 0 || key > 127)
            return nullptr;
        if (!drums && (var >> 12) && cab_prog == program && cabq[key] >= 0)
            return K[cabq[key]];            // (its cabinet's voice: cab_prep's)
        int en = drums ? 0 : var_entry(program, var);
        if (en) {
            int q = var_kidx(en, key);
            return q >= 0 && q < (int)K.size() ? K[q] : nullptr;
        }
        return K[(drums ? NV_K_DRUMS : 0) + 128 * program + key];
    }
    // THE CABINET's VOICES (a variation key's choice over bit 12): each key's
    // class through it (nv_cab_variant), put in K past its end -- room kept
    // for them when the cache was made, so K never moves under a reader --
    // and cabq the index a key's note takes (its template's, its class's).
    // Made before the program's first template, once
    int cab_prog = -1;
    int cabq[128];
    std::map<int, int> cabk;                // (an index in K -> its cabinet's: the template song's notes)
    void cab_prep(int program)
    {
        if (drums || !(var >> 12) || cab_prog == program || program < 0 || program > 127)
            return;
        const int c = (var >> 12) & 255, en = var_entry(program, var);
        for (int key = 0; key < 128; key++) {
            const int q = en ? var_kidx(en, key) : 128 * program + key;
            cabq[key] = -1;
            if (q < 0 || q >= (int)K.size() || !K[q])
                continue;
            auto it = cabk.find(q);
            if (it == cabk.end()) {
                const NoteClass *d = nv_voice_variant(nv_variant(K[q], c), var >> 20);    // (its pickup's, its cabinet's, then its knobs')
                if (d == K[q] || K.size() >= K.capacity())
                    continue;
                K.push_back(d);
                it = cabk.emplace(q, (int)K.size() - 1).first;
            }
            cabq[key] = it->second;
        }
        cab_prog = program;
    }
    Kits kit;
    std::vector<double> les;            // the Leslie's constants (leslie.cpp's L_*), empty: none
    std::vector<double> spec;           // the Spectra-Tone's (native.spectra_constants), empty: none
    int raga_sa = -1, raga_nsw = 0;     // its tuner's raga (a raga tuner's: Sa's note, -1 none; the swaras)
    int gm2 = 0;                        // its tuner is gm2's: the store's tables over it (_mts_ratio)
    double raga_sw[12];
    double oneshot_floor_db = 100.0;    // live.ONESHOT_FLOOR_DB
    long roll_hit_rows = 4096;          // live.ROLL_HIT_ROWS

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
        std::vector<long long> srows, prows, flips;
        std::vector<double> jrows;
        std::vector<long long> rrows, grows;
        double mft[30];
        g_raga_sa = raga_sa;                // (the template's prepare: T.raga_sa_note, T.raga_spec)
        g_raga_nsw = raga_nsw;
        g_tmpl_var = drums ? 0 : var;       // (its variation's bank, before its program change)
        g_tmpl_spec = spec.empty() ? nullptr : &spec;   // (a Spectra-Tone's cone rows: template_rows)
        cab_prep(program);                  // (...through its cabinet: its voices in K, cabk)
        g_tmpl_cabk = cabk.empty() ? nullptr : &cabk;
        g_tmpl_stk = !drums && !kit.f0.empty() ? &kit : nullptr;   // (a melodic cache's borrowed strokes)
        for (int i = 0; i < raga_nsw; i++)
            g_raga_sw[i] = raga_sw[i];
        long long P = template_rows(K.data(), &t, freq, trim, program, note, vel, fast, &rows, kind, scale, full,
                                    residual, beta, blk, ring_floor, ring_max, out, knee, ln10_20, xdec, SR, dm,
                                    drums ? &kit : nullptr, &srows, &prows, les.empty() ? nullptr : les.data(),
                                    &flips, &jrows, &rrows, mft, &grows);
        if (P < 0) {
            free(rows);
            return false;
        }
        T.P = (long)P;
        T.vel = vel;
        for (int q = 0; q < 27; q++)
            T.room_q[q] = out[4 + q];
        T.seq = nseq++;
        if (!std::isnan(mft[10])) {         // a Moog note: its row's key and valve (t["FT"])
            T.moog = true;
            T.ft_f0 = (double)(float)mft[10];  // (prepare's FT table is float32)
            T.ft_pre = mft[11] > 0.5;
        }
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
        // THE SPECTRA-TONE's columns (CONE_COLS): a cone row's rotor 0, its
        // place in the table, lsh -1; every other row on no rotor
        T.f4[27].assign((size_t)P, 1.0f);
        T.f4[28].assign((size_t)P, 0.0f);
        T.i4[6].assign((size_t)P, -1);
        if ((long long)g_tmpl_cone.size() == P)
            for (long long r = 0; r < P; r++)
                if (!std::isnan(g_tmpl_cone[(size_t)r])) {
                    T.i4[6][r] = 0;
                    T.f4[27][r] = g_tmpl_cone[(size_t)r];
                    T.f4[28][r] = -1.0f;
                }
        {                                   // the other strings' rows (t["ring"]: _RING, dr 0.9 direct, 0.1 an image)
            int cdr = emit_col("dr");
            bool any = false;
            std::vector<char> rg(P, 0);
            for (long long r = 0; r < P; r++) {
                double d = rows[NCOLS * r + cdr];
                rg[r] = d == 0.9 || d == 0.1;
                any = any || rg[r];
            }
            if (any)
                T.ring.swap(rg);
        }
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
        // ITS GRAINS (t["grain"], t["gof"]): each lands where it falls in the
        // note, its onset less the first direct row's (rdl 0, not a grain);
        // placed at the press, a rain key's drops all fell in its first instant
        std::vector<char> gmask;
        if (P && !grows.empty()) {
            gmask.assign(P, 0);
            bool anyg = false;
            for (size_t k = 0; k + 1 < grows.size(); k += 2)
                for (long long r = grows[k]; r < std::min(grows[k + 1], (long long)P); r++)
                    gmask[r] = anyg = 1;
            if (anyg) {
                const std::vector<float> &rdl = T.f4[25];
                long long t0 = 0;
                bool have = false;
                for (long long r = 0; r < P; r++)
                    if (rdl[r] == 0.0f && !gmask[r] && (!have || T.i8[0][r] < t0)) {
                        t0 = T.i8[0][r];
                        have = true;
                    }
                if (!have)
                    for (long long r = 0; r < P; r++)
                        if (r == 0 || T.i8[0][r] < t0)
                            t0 = T.i8[0][r];
                T.gof.assign(P, 0);
                for (long long r = 0; r < P; r++)
                    if (gmask[r])
                        T.gof[r] = T.i8[0][r] - t0;
            } else {
                gmask.clear();
            }
        }
        // A STROKED KEY (a drum's gesture): each stroke's rows where it falls
        // in the note (sof: its onset less its room delay, over the least of
        // the strokes'; numpy's int64 - float32, truncated) -- a layer's rows,
        // struck with the key, at the press (0)
        // the sympathetic strings' rows (t["sym"]: sym_rows, the notes' end to theirs)
        if (P && out[42] > out[3]) {
            T.sym.assign(P, 0);
            for (long long r = (long long)out[3]; r < std::min((long long)out[42], (long long)P); r++)
                T.sym[r] = 1;
        }
        // the bellows' push rows (t["push"])
        if (P && !prows.empty()) {
            T.push.assign(P, 0);
            for (size_t k = 0; k < prows.size(); k += 2)
                for (long long r = prows[k]; r < std::min(prows[k + 1], (long long)P); r++)
                    T.push[r] = 1;
        }
        const NoteClass *nc = cls(program, note);   // (its variation's, where it is one)
        T.scatter_ms = nc ? nc->scatter_ms : 0.0;             // (t["scatter_ms"])
        // the Leslie's crossover copies (t["lflip"])
        T.lflip.assign(P, 0);
        for (long long r : flips)
            if (r < P)
                T.lflip[r] = 1;
        // ...and its rows' lobes, a rotary voice's (live's leslie_params, done once here)
        if (P && nc && nc->leslie && !les.empty()) {
            std::vector<double> nf((size_t)P);
            for (long long r = 0; r < P; r++)
                nf[r] = (double)T.f4[2][r];
            T.lhorn.resize(P); T.lfl.resize(P); T.lsh.resize(P); T.lnrm.resize(P);
            nv_leslie_params((long)P, nf.data(), T.lflip.data(), les.data(), T.lhorn.data(), T.lfl.data(),
                             T.lsh.data(), T.lnrm.data());
        }
        // A HAMMOND'S CONTACTS (t["cof"]): each row's onset less its room
        // delay over the least (numpy: int64 - float32, as float64, truncated)
        if (P && nc && nc->organ && nc->organ->contact_on) {
            const std::vector<float> &rdl = T.f4[25];
            double mn = 0.0;
            for (long long r = 0; r < P; r++) {
                double b = (double)T.i8[0][r] - (double)rdl[r];
                if (r == 0 || b < mn)
                    mn = b;
            }
            T.cof.resize(P);
            for (long long r = 0; r < P; r++)
                T.cof[r] = (long long)(((double)T.i8[0][r] - (double)rdl[r]) - mn);
        }
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
        // ...AND THE QUILL'S CATCH ENDS AT THE SLIP (live's rof for
        // pre_pluck_s): a catch row keeps its length from its onset (a few
        // ms, under 20), every other row the key's (-1)
        if (P && nc && nc->pre_pluck) {
            T.rof.resize(P);
            const long long lim = (long long)(0.02 * SR);
            for (long long r = 0; r < P; r++) {
                long long len = T.i8[1][r] - T.i8[0][r];
                T.rof[r] = len <= lim ? len : -1;
            }
        }
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
        // ITS OWN DISTANCE (t["send"]: reverb_distance, the gunshot's)
        T.send = (nc && nc->rd_set) ? nc->reverb_dist : NAN;
        // A HELD TEXTURE IS A HELD NOTE (live's min_hold): its rows run until
        // the key is up, but those that decay on their own; its gate the least
        if (T.oneshot && nc->held_texture && nc->gate_time > 0.0) {
            for (long long r = 0; r < P; r++)
                if (!((double)T.f4[6][r] > 0 && T.f4[9][r] <= 0 && T.i4[0][r] < 0))
                    T.rof[r] = -1;
            T.oneshot = false;
            T.min_hold = (long long)nearbyint(nc->gate_time * SR);
            // ...AND ITS GRAINS GO ON (t["gpool"]): the template's own drops,
            // one one-shot a drop (its rows sharing an onset), struck by the
            // part while the key is down at the class's own rate; the held
            // stamp is the rest
            double rate_g = 0.0;
            for (int g = 0; g < nc->n_grain; g++)
                if (nc->grain[g][2] > 0.0)
                    rate_g += nc->grain[g][2];
            if (!gmask.empty() && rate_g > 0.0) {
                std::vector<long long> ons;
                for (long long r = 0; r < P; r++)
                    if (gmask[r])
                        ons.push_back(T.i8[0][r]);
                std::sort(ons.begin(), ons.end());
                ons.erase(std::unique(ons.begin(), ons.end()), ons.end());
                auto slice = [&](Template &D, const std::vector<long> &idx) {
                    auto cut = [&](auto &dst, const auto &src) {
                        dst.resize(idx.size());
                        for (size_t q = 0; q < idx.size(); q++)
                            dst[q] = src[idx[q]];
                    };
                    D.P = (long)idx.size();
                    for (int c = 0; c < 6; c++)
                        cut(D.f8[c], T.f8[c]);
                    for (int c = 0; c < NV_LF4; c++)
                        cut(D.f4[c], T.f4[c]);
                    for (int c = 0; c < 4; c++)
                        cut(D.f4n[c], T.f4n[c]);
                    for (int c = 0; c < 2; c++)
                        cut(D.i8[c], T.i8[c]);
                    for (int c = 0; c < NV_LI4; c++)
                        cut(D.i4[c], T.i4[c]);
                    cut(D.hrel, T.hrel);
                    if (!T.sof.empty())
                        cut(D.sof, T.sof);
                    if (!T.rof.empty())
                        cut(D.rof, T.rof);
                    if (!T.fa_at.empty())
                        cut(D.fa_at, T.fa_at);
                    if (!T.cof.empty())
                        cut(D.cof, T.cof);
                    if (!T.lflip.empty())
                        cut(D.lflip, T.lflip);
                    if (!T.push.empty())
                        cut(D.push, T.push);
                    if (!T.sym.empty())
                        cut(D.sym, T.sym);
                    if (!T.ring.empty())
                        cut(D.ring, T.ring);
                };
                for (long long on : ons) {
                    std::vector<long> idx;
                    for (long long r = 0; r < P; r++)
                        if (gmask[r] && T.i8[0][r] == on)
                            idx.push_back((long)r);
                    Template D;
                    slice(D, idx);
                    D.oneshot = true;
                    D.send = T.send;            // (a drop's, as the dict's scalars are)
                    D.cof.clear();
                    D.scatter_ms = 0.0;
                    D.vel = T.vel;
                    long long mx = 0;
                    for (long q = 0; q < D.P; q++)
                        mx = q == 0 ? D.rof[q] : std::max(mx, D.rof[q]);
                    D.dur = mx;
                    T.gpool.push_back(std::move(D));
                }
                std::vector<long> keep;
                for (long long r = 0; r < P; r++)
                    if (!gmask[r])
                        keep.push_back((long)r);
                Template K2;
                slice(K2, keep);
                for (int c = 0; c < 6; c++)
                    T.f8[c].swap(K2.f8[c]);
                for (int c = 0; c < NV_LF4; c++)
                    T.f4[c].swap(K2.f4[c]);
                for (int c = 0; c < 4; c++)
                    T.f4n[c].swap(K2.f4n[c]);
                for (int c = 0; c < 2; c++)
                    T.i8[c].swap(K2.i8[c]);
                for (int c = 0; c < NV_LI4; c++)
                    T.i4[c].swap(K2.i4[c]);
                T.hrel = K2.hrel;
                T.sof = K2.sof; T.rof = K2.rof; T.fa_at = K2.fa_at; T.cof = K2.cof; T.lflip = K2.lflip;
                T.push = K2.push; T.sym = K2.sym; T.ring = K2.ring;
                T.P = K2.P;
                P = T.P;
                T.gof.clear();
                gmask.clear();
            }
            T.grate = rate_g;
        }
        // A HELD ROLL IS STRUCK AS IT GOES (t["roll"]: percussion_map.RollSteps):
        // one hit kept -- the template's first, at its strongest roll_hit_rows
        // rows by their energy -- struck at each of the gesture's steps while
        // the key is held (Part's roll_tick); the held stamp is nothing. Its
        // gesture the kit key's (a drum set's own, or a melodic SFX's: its
        // cache's borrowed tables), kind 4 or 7 of the export's
        if (P && !T.sof.empty() && !kit.skind.empty()) {
            int q = -1, rk = note;
            if (drums)
                q = 128 * program + note;
            else if (nc && nc->sfx_prog >= 0) {
                rk = nc->sfx_key >= 0 ? nc->sfx_key : note;
                q = 128 * nc->sfx_prog + rk;
            }
            const int rkind = q >= 0 && q < (int)kit.skind.size() ? kit.skind[q] : 0;
            if (rkind == 4 || rkind == 7) {
                const double *rp = kit.spar.data() + (size_t)NV_SPAR * q;
                std::vector<long> h;
                for (long long r = 0; r < P; r++)
                    if (T.sof[r] == 0)
                        h.push_back((long)r);
                if ((long)h.size() > roll_hit_rows) {
                    std::vector<double> e(P, 0.0);
                    for (long r : h) {
                        double a = std::max(std::fabs((double)T.f4[0][r]), std::fabs((double)T.f4[1][r]));
                        e[r] = a * a / (2.0 * std::max((double)T.f4[6][r], 1e-3));
                    }
                    std::stable_sort(h.begin(), h.end(), [&](long x, long y) { return e[x] > e[y]; });
                    h.resize(roll_hit_rows);
                    std::sort(h.begin(), h.end());
                }
                Template D;
                auto cut = [&](auto &dst, const auto &src) {
                    dst.resize(h.size());
                    for (size_t j = 0; j < h.size(); j++)
                        dst[j] = src[h[j]];
                };
                D.P = (long)h.size();
                for (int c = 0; c < 6; c++)
                    cut(D.f8[c], T.f8[c]);
                for (int c = 0; c < NV_LF4; c++)
                    cut(D.f4[c], T.f4[c]);
                for (int c = 0; c < 4; c++)
                    cut(D.f4n[c], T.f4n[c]);
                for (int c = 0; c < 2; c++)
                    cut(D.i8[c], T.i8[c]);
                for (int c = 0; c < NV_LI4; c++)
                    cut(D.i4[c], T.i4[c]);
                cut(D.hrel, T.hrel);
                if (!T.rof.empty())
                    cut(D.rof, T.rof);
                if (!T.lflip.empty())
                    cut(D.lflip, T.lflip);
                if (!T.push.empty())
                    cut(D.push, T.push);
                if (!T.sym.empty())
                    cut(D.sym, T.sym);
                if (!T.ring.empty())
                    cut(D.ring, T.ring);
                D.oneshot = true;
                D.send = T.send;
                D.scatter_ms = 0.0;
                D.vel = T.vel;
                std::copy(T.room_q, T.room_q + 27, D.room_q);
                D.seq = T.seq;
                long long mx = 0;
                if (!D.rof.empty())
                    for (long j = 0; j < D.P; j++)
                        mx = j == 0 ? D.rof[j] : std::max(mx, D.rof[j]);
                else
                    for (long j = 0; j < D.P; j++)
                        mx = j == 0 ? D.i8[1][j] - D.i8[0][j] : std::max(mx, D.i8[1][j] - D.i8[0][j]);
                D.dur = mx;
                // ...its level in the template: the gesture's first hit, the
                // note struck at 0 s (rasp_strokes': its seed note x 7919)
                PyRandom r0;
                pyr_seed(&r0, (long long)rk * 7919LL);
                double db0;
                if (rkind == 4) {
                    pyr_uniform(&r0, -0.15, 0.15);
                    db0 = rp[9] - rp[3] * 0.0 + pyr_uniform(&r0, -rp[6], rp[6]);
                } else
                    db0 = rp[2] + (rp[3] - rp[2]) * std::min(1.0, 0.0 / rp[1]) + pyr_uniform(&r0, -rp[4], rp[4]);
                T.roll_lv0 = pow(10.0, db0 / 40.0);
                T.roll_kind = rkind;
                T.roll_par.assign(rp, rp + (rkind == 4 ? 11 : 10));
                T.roll_key = rk;
                T.roll_hit.clear();
                T.roll_hit.push_back(std::move(D));
                for (int c = 0; c < 6; c++)
                    T.f8[c].clear();
                for (int c = 0; c < NV_LF4; c++)
                    T.f4[c].clear();
                for (int c = 0; c < 4; c++)
                    T.f4n[c].clear();
                for (int c = 0; c < 2; c++)
                    T.i8[c].clear();
                for (int c = 0; c < NV_LI4; c++)
                    T.i4[c].clear();
                T.hrel.clear();
                T.sof.clear(); T.rof.clear(); T.fa_at.clear(); T.cof.clear(); T.lflip.clear();
                T.push.clear(); T.sym.clear(); T.ring.clear();
                T.P = 0;
                P = 0;
            }
        }
        // AN ORGAN, SLICED BY RANK (_raw_template's t["ranks"]): each rank's
        // rows, their columns and their share of hrel
        if (nc && nc->organ && P) {
            T.ranks.assign(nc->organ->n_rank, Template());
            for (int ri = 0; ri < nc->organ->n_rank; ri++) {
                std::vector<long> idx;
                for (long long r = 0; r < P; r++)
                    if (T.i4[0][r] == ri)
                        idx.push_back((long)r);
                Template &R = T.ranks[ri];
                R.P = (long)idx.size();
                if (!R.P)
                    continue;
                auto cut = [&](auto &dst, const auto &src) {
                    dst.resize(idx.size());
                    for (size_t q = 0; q < idx.size(); q++)
                        dst[q] = src[idx[q]];
                };
                for (int c = 0; c < 6; c++)
                    cut(R.f8[c], T.f8[c]);
                for (int c = 0; c < NV_LF4; c++)
                    cut(R.f4[c], T.f4[c]);
                for (int c = 0; c < 4; c++)
                    cut(R.f4n[c], T.f4n[c]);
                for (int c = 0; c < 2; c++)
                    cut(R.i8[c], T.i8[c]);
                for (int c = 0; c < NV_LI4; c++)
                    cut(R.i4[c], T.i4[c]);
                cut(R.hrel, T.hrel);
                if (!T.sof.empty())
                    cut(R.sof, T.sof);
                if (!T.rof.empty())
                    cut(R.rof, T.rof);
                if (!T.cof.empty())
                    cut(R.cof, T.cof);
                cut(R.lflip, T.lflip);
                if (!T.lhorn.empty()) {
                    cut(R.lhorn, T.lhorn);
                    cut(R.lfl, T.lfl);
                    cut(R.lsh, T.lsh);
                    cut(R.lnrm, T.lnrm);
                }
            }
            // ...AND ONE CLICK A JACK (t["rel_rank"]): each stop's key-up
            // rows (no rank: gr -1), their jack's offset, their length
            for (size_t q = 0; q + 3 < jrows.size(); q += 4) {
                long long a = (long long)jrows[q], b = std::min((long long)jrows[q + 1], (long long)P);
                if (a >= P || b <= a)
                    continue;
                Template J;
                J.P = (long)(b - a);
                auto cut = [&](auto &dst, const auto &src) { dst.assign(src.begin() + a, src.begin() + b); };
                for (int c = 0; c < 6; c++)
                    cut(J.f8[c], T.f8[c]);
                for (int c = 0; c < NV_LF4; c++)
                    cut(J.f4[c], T.f4[c]);
                for (int c = 0; c < 4; c++)
                    cut(J.f4n[c], T.f4n[c]);
                for (int c = 0; c < 2; c++)
                    cut(J.i8[c], T.i8[c]);
                for (int c = 0; c < NV_LI4; c++)
                    cut(J.i4[c], T.i4[c]);
                cut(J.hrel, T.hrel);
                long long co = (long long)nearbyint(jrows[q + 3] * SR);
                J.cof.assign(J.P, co);
                long long mx = 0;
                for (long r = 0; r < J.P; r++)
                    mx = r == 0 ? J.i8[1][r] - J.i8[0][r] : std::max(mx, J.i8[1][r] - J.i8[0][r]);
                J.dur = mx + co;
                T.jacks.push_back(J);
                T.jack_rank.push_back((int)jrows[q + 2]);
            }
        }
        // THE KEY-UP's ROWS (live's t["rel"]: a voice with no ranks): out of
        // the note -- every row it has, column or not -- into a one-shot of
        // their own, its length from its first onset to its last end
        if (!(nc && nc->organ) && T.P) {
            long long TP = T.P;
            std::vector<char> msk(TP, 0);
            bool any = false;
            for (size_t q = 0; q + 1 < rrows.size(); q += 2) {
                long long a = rrows[q], b = std::min(rrows[q + 1], TP);
                if (a >= TP)
                    continue;
                for (long long r = a; r < b; r++) {
                    msk[r] = 1;
                    any = true;
                }
            }
            if (any) {
                std::vector<long> in, keep;
                for (long long r = 0; r < TP; r++)
                    (msk[r] ? in : keep).push_back((long)r);
                Template Rl;
                auto split = [&](auto &dst, auto &src) {
                    if ((long long)src.size() != TP)
                        return;
                    dst.resize(in.size());
                    for (size_t q = 0; q < in.size(); q++)
                        dst[q] = src[in[q]];
                    std::remove_reference_t<decltype(src)> rest(keep.size());
                    for (size_t q = 0; q < keep.size(); q++)
                        rest[q] = src[keep[q]];
                    src.swap(rest);
                };
                for (int c = 0; c < 6; c++)
                    split(Rl.f8[c], T.f8[c]);
                for (int c = 0; c < NV_LF4; c++)
                    split(Rl.f4[c], T.f4[c]);
                for (int c = 0; c < 4; c++)
                    split(Rl.f4n[c], T.f4n[c]);
                for (int c = 0; c < 2; c++)
                    split(Rl.i8[c], T.i8[c]);
                for (int c = 0; c < NV_LI4; c++)
                    split(Rl.i4[c], T.i4[c]);
                split(Rl.hrel, T.hrel);
                split(Rl.fa_at, T.fa_at);
                split(Rl.rof, T.rof);
                split(Rl.sof, T.sof);
                split(Rl.cof, T.cof);
                split(Rl.lflip, T.lflip);
                split(Rl.lhorn, T.lhorn);
                split(Rl.lfl, T.lfl);
                split(Rl.lsh, T.lsh);
                split(Rl.lnrm, T.lnrm);
                split(Rl.push, T.push);
                Rl.P = (long)in.size();
                long long mxo = Rl.i8[1][0], mno = Rl.i8[0][0];
                for (long r = 0; r < Rl.P; r++) {
                    mxo = std::max(mxo, Rl.i8[1][r]);
                    mno = std::min(mno, Rl.i8[0][r]);
                }
                Rl.dur = mxo - mno;
                Rl.oneshot = true;
                T.P = (long)keep.size();
                T.rel.push_back(Rl);
            }
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
// the cache's tuner is a raga's: its Sa's note (-1 none) and swaras' cents (the
// templates' strings, the meend's); and read back (sa, sw[12], *nsw)
void nv_tcache_set_raga(void *h, int sa, const double *sw, int nsw)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    C->raga_sa = sa;
    C->raga_nsw = nsw > 0 && nsw <= 12 ? nsw : 0;
    for (int i = 0; i < C->raga_nsw; i++)
        C->raga_sw[i] = sw[i];
}

void nv_tcache_set_gm2(void *h, int on) { ((nv::live::Cache *)h)->gm2 = on; }
int nv_tcache_gm2(void *h) { return ((const nv::live::Cache *)h)->gm2; }

int nv_tcache_get_raga(void *h, double *sw, int *nsw)
{
    const nv::live::Cache *C = (const nv::live::Cache *)h;
    *nsw = C->raga_nsw;
    for (int i = 0; i < C->raga_nsw; i++)
        sw[i] = C->raga_sw[i];
    return C->raga_sa;
}

void *nv_tcache_new(const NoteClass *const *K, const NoteIn *tmpl, const double *freq, const double *trim,
                    const int *kind, const int *fin, double scale, double full_db_s, double residual, double beta,
                    long long blk, double ring_floor, double ring_max, double knee_db, double ln10_20,
                    double xdec_nepers, double SR)
{
    nv::live::Cache *C = new nv::live::Cache();
    C->K.reserve((g_k_n > 2 * NV_K_DRUMS ? g_k_n : 2 * NV_K_DRUMS) + 256);    // (room for its cabinet's voices: cab_prep)
    C->K.assign(K, K + (g_k_n > 2 * NV_K_DRUMS ? g_k_n : 2 * NV_K_DRUMS));
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

// (NV_CACHE_POISON=1, the checks': a cache let go is poisoned and kept, not
// freed -- its numbers NaN, its indices wild, its classes gone -- so a part
// that still reached it would sound NaN or fall over, not read freed memory)
static void tmpl_poison(nv::live::Template &T)
{
    for (auto &v : T.f8) std::fill(v.begin(), v.end(), NAN);
    for (auto &v : T.f4) std::fill(v.begin(), v.end(), NAN);
    for (auto &v : T.f4n) std::fill(v.begin(), v.end(), NAN);
    for (auto &v : T.i8) std::fill(v.begin(), v.end(), 1LL << 40);
    for (auto &v : T.i4) std::fill(v.begin(), v.end(), 0x3fffffff);
    std::fill(T.hrel.begin(), T.hrel.end(), NAN);
    for (auto *vs : {&T.ranks, &T.jacks, &T.rel, &T.gpool, &T.roll_hit})
        for (auto &s : *vs)
            tmpl_poison(s);
}

void nv_tcache_free(void *h)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (C && getenv("NV_CACHE_POISON")) {
        for (auto &kv : C->tm)
            tmpl_poison(kv.second);
        for (auto &u : C->vstore)
            tmpl_poison(*u);
        std::fill(C->K.begin(), C->K.end(), nullptr);
        for (double &f : C->freq)
            f = NAN;
        return;
    }
    delete C;
}

// A CACHE's SIZE (the host's patch cache: live's LRU counts partials; here
// the bytes its templates hold), and EVERY TEMPLATE IN IT a part can keep a
// pointer to (its own, a drum key's edits, their organ ranks: a retired
// cache's, nv_part_cache_retire) -- into out (cap), how many there are
static size_t tmpl_bytes(const nv::live::Template &T)
{
    size_t b = sizeof T;
    for (const auto &v : T.f8) b += v.capacity() * sizeof(double);
    for (const auto &v : T.f4) b += v.capacity() * sizeof(float);
    for (const auto &v : T.f4n) b += v.capacity() * sizeof(float);
    for (const auto &v : T.i8) b += v.capacity() * sizeof(long long);
    for (const auto &v : T.i4) b += v.capacity() * sizeof(int32_t);
    b += T.hrel.capacity() * sizeof(float) + T.fa_at.capacity();
    b += (T.rof.capacity() + T.sof.capacity() + T.cof.capacity() + T.gof.capacity()) * sizeof(long long);
    for (const auto *vs : {&T.ranks, &T.jacks, &T.rel, &T.gpool, &T.roll_hit})
        for (const auto &s : *vs)
            b += tmpl_bytes(s);
    return b;
}

// (a cache's shape, for the memory report: its templates and their rows, ranks' and stores' included)
void nv_tcache_shape(void *h, long *ntmpl, long long *rows)
{
    const nv::live::Cache *C = (const nv::live::Cache *)h;
    long n = 0;
    long long r = 0;
    std::function<void(const nv::live::Template &)> add = [&](const nv::live::Template &T) {
        n++;
        r += T.P;
        for (const auto *vs : {&T.ranks, &T.jacks, &T.rel, &T.gpool, &T.roll_hit})
            for (const auto &s : *vs)
                add(s);
    };
    std::lock_guard<std::mutex> lk(const_cast<nv::live::Cache *>(C)->tmu);
    for (const auto &kv : C->tm)
        add(kv.second);
    for (const auto &u : C->vstore)
        add(*u);
    *ntmpl = n;
    *rows = r;
}

long long nv_tcache_bytes(void *h)
{
    const nv::live::Cache *C = (const nv::live::Cache *)h;
    size_t b = sizeof *C;
    std::lock_guard<std::mutex> lk(const_cast<nv::live::Cache *>(C)->tmu);
    for (const auto &kv : C->tm)
        b += tmpl_bytes(kv.second);
    for (const auto &u : C->vstore)
        b += tmpl_bytes(*u);
    return (long long)b;
}

long nv_tcache_templates(void *h, const void **out, long cap)
{
    const nv::live::Cache *C = (const nv::live::Cache *)h;
    long n = 0;
    auto put = [&](const nv::live::Template &T) {
        if (n < cap)
            out[n] = &T;
        n++;
        for (const auto &R : T.ranks) {
            if (n < cap)
                out[n] = &R;
            n++;
        }
    };
    std::lock_guard<std::mutex> lk(const_cast<nv::live::Cache *>(C)->tmu);
    for (const auto &kv : C->tm)
        put(kv.second);
    for (const auto &u : C->vstore)
        put(*u);
    return n;
}

// the Leslie's constants for a rotary voice's templates (the export's LESL)
void nv_tcache_leslie(void *h, const double *L, int n) { ((nv::live::Cache *)h)->les.assign(L, L + n); }
// ...and the Spectra-Tone's numbers (native.spectra_constants: its templates' cone rows)
void nv_tcache_spectra(void *h, const double *sp, int n) { ((nv::live::Cache *)h)->spec.assign(sp, sp + n); }

// A DRUM PART'S CACHE: its program the drum set, its keys built on GM's
// percussion channel from the sets' tables (native.kits: f0, seat, choke,
// skind, spar), live's ONESHOT_FLOOR_DB
// (the tables are the caller's, outliving the cache: the export's)
void nv_tcache_kits(void *h, const double *f0, const double *seat, const unsigned long long *choke,
                    const int *skind, const double *spar, double oneshot_floor_db)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    C->drums = true;
    const size_t nk = 128 * (size_t)(128 + g_mapk_n);    // (the maps' own sets after the 128)
    C->kit.f0.assign(f0, f0 + nk);
    C->kit.seat.assign(seat, seat + nk);
    C->kit.choke.assign(choke, choke + 2 * nk);
    C->kit.skind.assign(skind, skind + nk);
    C->kit.spar.assign(spar, spar + NV_SPAR * nk);
    C->oneshot_floor_db = oneshot_floor_db;
}

// A MELODIC CACHE's DRUM SETS' TABLES, for a note that borrows a kit key's
// strokes (sfx_strokes_of): nv_tcache_kits's, the cache staying melodic
void nv_tcache_stroke_kits(void *h, const double *f0, const double *seat, const unsigned long long *choke,
                           const int *skind, const double *spar)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    const size_t nk = 128 * (size_t)(128 + g_mapk_n);
    C->kit.f0.assign(f0, f0 + nk);
    C->kit.seat.assign(seat, seat + nk);
    C->kit.choke.assign(choke, choke + 2 * nk);
    C->kit.skind.assign(skind, skind + nk);
    C->kit.spar.assign(spar, spar + NV_SPAR * nk);
}

// THE MAPS' OWN DRUM SETS: their keys' region of K (base), how many (n) --
// set before any drum set's cache, as the sets' tables are as long
void nv_tcache_mapk(int base, int n, const int *ids)
{
    g_mapk_base = base;
    g_mapk_n = n;
    g_mapk_ids.assign(ids, ids + n);
}

// Patch.warm: keys lo..hi, nb buckets (each at bucket_vel), the wheel steps
// (nsp of them; -1 for none); the templates built. Returns how many.
// ...counting each (key, bucket, speed) into *done as it goes (NULL: not
// counted) -- (hi - lo + 1) x nb x nsp in all: a builder's progress, read
// by another thread
long nv_tcache_warm_p(void *h, int program, int lo, int hi, int nb, const int *speeds, int nsp, long *done)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    long n = 0;
    C->shape(nb, speeds, nsp);
    for (int note = lo; note <= hi; note++)
        for (int b = 0; b < nb; b++)
            for (int q = 0; q < nsp; q++) {
                if (done)
                    __atomic_fetch_add(done, 1L, __ATOMIC_RELAXED);
                auto k = std::make_tuple(note, b, speeds[q]);
                if (C->tm.count(k))
                    continue;
                int vel = (int)std::min(127.0, (b + 0.5) * 128.0 / nb);    // Patch.bucket_vel
                nv::live::Template T;
                if (C->build(program, note, vel, speeds[q], T)) {
                    C->keep(k, std::move(T));
                    n++;
                }
            }
    return n;
}

// ...ON A BUDGET, and only the octaves asked for (A5): oct a mask of the
// octaves (note / 12) to build, 0 every one -- a file's (its notes'
// octaves: the rest never asked); limit > 0 the bytes its templates may
// take (*bytes, as it goes): past it, -1 at once, the cache as it stands
// for the caller to free (a program refused, not half there). The same
// templates in the same order as nv_tcache_warm_p's, those built.
long nv_tcache_warm_b(void *h, int program, int lo, int hi, int nb, const int *speeds, int nsp, long *done,
                      unsigned oct, long long limit, long long *bytes)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    long n = 0;
    long long b = 0;
    C->shape(nb, speeds, nsp);
    for (int note = lo; note <= hi; note++) {
        const bool want = !oct || (oct >> (note / 12) & 1u);
        for (int bk = 0; bk < nb; bk++)
            for (int q = 0; q < nsp; q++) {
                if (done)
                    __atomic_fetch_add(done, 1L, __ATOMIC_RELAXED);
                if (!want)
                    continue;
                auto k = std::make_tuple(note, bk, speeds[q]);
                if (C->tm.count(k))
                    continue;
                int vel = (int)std::min(127.0, (bk + 0.5) * 128.0 / nb);    // Patch.bucket_vel
                nv::live::Template T;
                if (C->build(program, note, vel, speeds[q], T)) {
                    const long long tb = (long long)tmpl_bytes(T);
                    if (limit > 0 && b + tb > limit) {      // (refused before it is kept: never past the limit)
                        if (bytes)
                            *bytes = b + tb;
                        return -1;
                    }
                    b += tb;
                    C->keep(k, std::move(T));
                    n++;
                }
            }
    }
    if (bytes)
        *bytes = b;
    return n;
}

// ONE TEMPLATE (a patch's size sampled before it is built, A5): note's at bucket
// bk and speeds[q], in the shape (nb, speeds) the warm will use, built and kept
// (the warm passes it by); its bytes, 0 none (none built, or one there already)
long long nv_tcache_sample(void *h, int program, int note, int bk, int q, int nb, const int *speeds, int nsp)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    C->shape(nb, speeds, nsp);
    auto k = std::make_tuple(note, bk, speeds[q]);
    if (C->tm.count(k))
        return 0;
    int vel = (int)std::min(127.0, (bk + 0.5) * 128.0 / nb);    // Patch.bucket_vel
    nv::live::Template T;
    if (!C->build(program, note, vel, speeds[q], T))
        return 0;
    const long long tb = (long long)tmpl_bytes(T);
    C->keep(k, std::move(T));
    return tb;
}

long nv_tcache_warm(void *h, int program, int lo, int hi, int nb, const int *speeds, int nsp)
{
    return nv_tcache_warm_p(h, program, lo, hi, nb, speeds, nsp, nullptr);
}

// live._room_band_q's part of a cache: every template's room_q (27 each:
// band, Q, energy), in the order they were built, into out (cap
// templates); how many there are
long nv_tcache_room_q(void *h, double *out, long cap)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    std::vector<const nv::live::Template *> ts;
    for (const auto &kv : C->tm)
        ts.push_back(&kv.second);
    std::sort(ts.begin(), ts.end(), [](const nv::live::Template *a, const nv::live::Template *b) { return a->seq < b->seq; });
    for (long i = 0; i < (long)ts.size() && i < cap; i++)
        memcpy(out + 27 * i, ts[i]->room_q, sizeof(double) * 27);
    return (long)ts.size();
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
// the class a melodic program's key plays (NULL: none)
const NoteClass *nv_tcache_note_class(void *h, int program, int note)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (note < 0 || note > 127 || program < 0 || program > 127)
        return nullptr;
    return C->cls(program, note);
}

int nv_tcache_slur_fade(void *h, int program, int note, double *out)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (note < 0 || note > 127 || program < 0 || program > 127)
        return 0;
    const NoteClass *k = C->cls(program, note);
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

// a template's section scatter, ms (t["scatter_ms"])
double nv_tmpl_scatter(void *t) { return ((nv::live::Template *)t)->scatter_ms; }

// the tuning's pitch of a key (live's patch.freqs())
double nv_tcache_freq(void *h, int note)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    return (note >= 0 && note < 128) ? C->freq[note] : 0.0;
}

// a program's registered organ (its classes' table: live's part.organ), NULL none
const OrganSpec *nv_tcache_organ(void *h, int program)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (!C || C->drums || program < 0 || program > 127)
        return nullptr;
    const NoteClass *k = C->cls(program, 60);
    return k ? k->organ : nullptr;
}

// the cache's templates, each in turn (i < n): its count with i < 0
const nv::live::Template *nv_tcache_at(void *h, long i, long *n)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    std::lock_guard<std::mutex> lk(C->tmu);
    if (n)
        *n = (long)C->tm.size();
    if (i < 0 || i >= (long)C->tm.size())
        return nullptr;
    auto it = C->tm.begin();
    std::advance(it, i);
    return &it->second;
}

// a program's class (its key 60's), NULL none
// a melodic program's trim (patch_map.program_trim, the templates')
double nv_tcache_trim(void *h, int program)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (!C || program < 0 || program > 127)
        return 1.0;
    int en = C->drums ? 0 : var_entry(program, C->var);    // (a variation's own: VARIATION_TRIM_DB)
    return en ? g_var_trim[en] : C->trim[program];
}

// the class a key of a program plays (none on a drum set's cache)
const NoteClass *nv_tcache_class_key(void *h, int program, int key)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (!C || C->drums || program < 0 || program > 127 || key < 0 || key > 127)
        return nullptr;
    return C->cls(program, key);
}

// ...a drum set's key's too (live.Patch._voice_class: percussion_for_note's class)
const NoteClass *nv_tcache_key_class(void *h, int program, int key)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    return C ? C->cls(program, key) : nullptr;
}

const NoteClass *nv_tcache_class(void *h, int program)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (!C || C->drums || program < 0 || program > 127)
        return nullptr;
    return C->cls(program, 60);
}

// A CACHE's VARIATION (live.Patch.variation), before its templates are warmed
void nv_tcache_set_var(void *h, int v) { ((nv::live::Cache *)h)->var = v; }

// THE CABINET CHOICES' SPEAKERS (VARS' last: native.cab_terms), 36 doubles a choice
void nv_cab_terms(int n, const double *terms)
{
    std::lock_guard<std::mutex> lk(g_cab_mu);
    g_cab_terms.assign(terms, terms + 36 * (size_t)std::max(0, n));
}

// A VOICE THROUGH CABINET CHOICE c (patch_map.cabinet_class): its own class
// copied, its speaker, its Leslie and -- a Leslie coming or going -- its
// level (cab_mk) changed, all else (its tables) shared; made once and kept.
// The voice itself where it does not offer c (cab_mask) or there is no table
const NoteClass *nv_cab_variant(const NoteClass *k, int c)
{
    if (!k || c <= 0 || c >= 31 || !((k->cab_mask >> c) & 1))
        return k;
    std::lock_guard<std::mutex> lk(g_cab_mu);
    if ((size_t)(36 * (c + 1)) > g_cab_terms.size())
        return k;
    auto &slot = g_cab_made[std::make_pair(k, c)];
    if (slot)
        return slot.get();
    const double *T = g_cab_terms.data() + 36 * (size_t)c;
    std::unique_ptr<NoteClass> d(new NoteClass(*k));
    d->leslie = T[0] != 0.0 ? (k->leslie ? k->leslie : k->cab_lfast) : 0;
    d->spectra = (int)T[34];                // (a Spectra-Tone: patch_map.SPECTRA_CHOICES)
    d->cab_set = (int)T[1];
    d->n_cab_fm = (int)T[2];
    d->n_cab_afm = (int)T[3];
    d->cab_floor = T[4];
    for (int i = 0; i < 4; i++)
        for (int j = 0; j < 3; j++) {
            d->cab_fm[i][j] = T[5 + 3 * i + j];
            d->cab_afm[i][j] = T[17 + 3 * i + j];
        }
    d->cab_corner = T[29];
    d->cab_order = T[30];
    d->cab_cut = T[31];
    d->cab_bell = T[32];
    d->cab_ref = T[33];
    const bool les0 = k->leslie != 0, les1 = d->leslie != 0;
    if (les0 != les1 && k->cab_mk != 0.0)   // (as Python's: initial_gain x 10 ** (+-mk / 20))
    {
        const double f = pow(10.0, (les1 ? k->cab_mk : -k->cab_mk) / 20.0);
        d->init.initial_gain = k->init.initial_gain * f;
        d->tmpl.gain = k->tmpl.gain * f;    // (its template's: initial_gain's product, the same factor)
    }
    slot = std::move(d);
    return slot.get();
}

// A VOICE THROUGH PICKUP CHOICE p (patch_map.pickup_class): its own class
// copied, its coils -- where they sit, how they are wired, their winding
// and load -- or a Clavinet's rocker setting changed, all else shared; the
// note's fret moves them as it moves its own (nv_voice_init). Made once and
// kept; the voice itself where it does not offer p (pk_mask) or there is no
// table. Its terms (native.cab_terms, block pk_base + p): [0] the coils, [1..4]
// their places, [5..8] their weights, [9] the turns, [10] the load's
// resonance, [11] its Q (<= 0 the voice's), [12] a Clavinet's setting (-1 none)
static std::map<std::pair<const NoteClass *, int>, std::unique_ptr<NoteClass>> g_pk_made;
const NoteClass *nv_pk_variant(const NoteClass *k, int p)
{
    if (!k || p <= 0 || p >= 8 || !((k->pk_mask >> p) & 1) || k->pk_base <= 0)
        return k;
    std::lock_guard<std::mutex> lk(g_cab_mu);
    const size_t b = 36 * (size_t)(k->pk_base + p);
    if (b + 36 > g_cab_terms.size())
        return k;
    auto &slot = g_pk_made[std::make_pair(k, p)];
    if (slot)
        return slot.get();
    const double *T = g_cab_terms.data() + b;
    std::unique_ptr<NoteClass> d(new NoteClass(*k));
    VoiceSnap &s = d->tmpl;
    // (the template's own fret: its coils' places over its class's -- nv_voice_init's again per note)
    const double sc = k->tmpl.pk_q0[0] > 0.0 ? k->tmpl.pk_q[0] / k->tmpl.pk_q0[0] : 1.0;
    if (T[12] >= 0.0) {
        s.cl_sel = (int)T[12];
        s.n_pk = s.cl_sel <= 1 ? 1 : 2;
        for (int i = 0; i < 4; i++)
            s.pk_sign[i] = i < s.n_pk ? (i == 1 && s.cl_sel == 3 ? -1.0 : 1.0) : 0.0;
    } else {
        const int n = std::max(1, std::min(4, (int)T[0]));
        s.n_pk = n;
        for (int i = 0; i < 4; i++) {
            s.pk_q0[i] = i < n ? T[1 + i] : 0.0;
            s.pk_sign[i] = i < n ? T[5 + i] : 0.0;
            s.pk_q[i] = i < n ? std::min(T[1 + i] * sc, 0.5) : 0.0;
        }
        s.pk_turns = k->tmpl.pk_turns / k->pk_t0 * T[9];
        s.pk_res_hz = T[10];
        if (T[11] > 0.0)
            s.pk_qf = T[11];
    }
    slot = std::move(d);
    return slot.get();
}

const NoteClass *nv_variant(const NoteClass *k, int code)
{
    return nv_cab_variant(nv_pk_variant(k, (code >> 4) & 7), code & 15);
}

int nv_voicing_knobs(const NoteClass *k, double *v0)
{
    if (!k)
        return 0;
    const VoiceSnap &s = k->tmpl;
    if (s.kind == 4 && s.elec && !s.clav) {
        // (an electric guitar or bass: where the pick strikes, the strings' loss)
        // (no PICK on a slap's or pop's fret contact, no STRINGS on a
        // feedback loop: piano_knobs.knobs_of's reasons)
        int m = 0;
        if (!s.fc_tab) {
            m |= 1 << NV_VK_PICK;
            v0[NV_VK_PICK] = s.eg_sp;
        }
        const double x = s.sp_decay ? s.sp_wind : s.harmonic_decay_db;
        if (x > 0.0 && !s.fb_set) {
            m |= 1 << NV_VK_STRINGS;
            v0[NV_VK_STRINGS] = x;
        }
        if (s.pk_res_hz != 0.0 && s.tone_r0 != 0.0) {
            m |= 1 << NV_VK_TONE;
            v0[NV_VK_TONE] = s.tone_turn;
        }
        return m;
    }
    if (s.kind == 5 && (s.ep_kind == 1 || s.ep_kind == 2)) {
        // (an electric piano: its pickup's voicing and the hammer's swing)
        int m = 0;
        if (s.ep_kind == 1) {
            m |= 1 << NV_VK_TINE | 1 << NV_VK_GAP;
            v0[NV_VK_TINE] = s.ep_p[0];
            v0[NV_VK_GAP] = s.ep_p[1];
            if (s.n_tb > 0 && s.tb_g[0] > 0.0) {
                m |= 1 << NV_VK_TONEBAR;
                v0[NV_VK_TONEBAR] = s.tb_g[0];
            }
        } else {
            m |= 1 << NV_VK_REED;
            v0[NV_VK_REED] = s.ep_p[0];
        }
        if (s.ep_defl > 0.0) {
            m |= 1 << NV_VK_SWING;
            v0[NV_VK_SWING] = s.ep_defl;
        }
        return m;
    }
    if (s.kind != 0 || !s.hammer_model)
        return 0;
    int m = 1 << NV_VK_HAMMER;
    v0[NV_VK_HAMMER] = s.hm_logk;
    if (s.hm_core_mm > 0.0 || s.hm_core_edge_mm > 0.0) {
        m |= 1 << NV_VK_WEAR;
        v0[NV_VK_WEAR] = s.hm_core_mm;
    }
    m |= 1 << NV_VK_STRIKE;
    v0[NV_VK_STRIKE] = s.sp_curve_set ? 1.0 / s.sp_curve[0] : s.strike_point;
    if (k->detune_hi > 0.0) {
        m |= 1 << NV_VK_UNISON;
        v0[NV_VK_UNISON] = k->detune_hi;
    }
    if (s.board_kind == 0 && s.lid_db != 0.0) {
        m |= 1 << NV_VK_LID;
        v0[NV_VK_LID] = s.lid_db;
    }
    if (s.board_kind == 0 || s.board_kind == 1) {
        m |= 1 << NV_VK_BOARD;
        v0[NV_VK_BOARD] = s.board_high_hz;
    }
    if (s.board_kind == 2) {
        m |= 1 << NV_VK_PICKUP;
        v0[NV_VK_PICKUP] = s.bridge_corner_hz;
    }
    return m;
}

// (piano_knobs.piano_class, in place: what each knob moves -- the class's
// own fields, and its template's where a note's setup reads them from there)
void nv_voicing_apply(NoteClass *d, const double *t, int mask)
{
    double v0[NV_VK_N];
    mask &= nv_voicing_knobs(d, v0);
    VoiceSnap &s = d->tmpl;
    if (mask >> NV_VK_HAMMER & 1)
        s.hm_logk += t[NV_VK_HAMMER];
    if (mask >> NV_VK_WEAR & 1) {
        s.hm_core_mm *= t[NV_VK_WEAR];
        s.hm_core_edge_mm *= t[NV_VK_WEAR];
    }
    if (mask >> NV_VK_STRIKE & 1) {
        if (s.sp_curve_set) {
            for (int i = 0; i < 3; i++)
                s.sp_curve[i] /= t[NV_VK_STRIKE];
            // (the prototype's own point, as its constructor set it from the curve: nv_voice_init's)
            const double f = s.frequency_x * pow(2.0, s.octave_position);
            const int midi = (int)rint(69.0 + 12.0 * log(f / 440.0) / log(2.0));
            const double oo = (midi - 69) / 12.0, sp = 1.0 / (s.sp_curve[0] + s.sp_curve[1] * oo + s.sp_curve[2] * oo * oo);
            s.strike_point = 0.5 < sp ? 0.5 : (0.02 > sp ? 0.02 : sp);
        } else
            s.strike_point *= t[NV_VK_STRIKE];
    }
    if (mask >> NV_VK_UNISON & 1) {
        d->detune_lo *= t[NV_VK_UNISON];
        d->detune_hi *= t[NV_VK_UNISON];
        d->init.detune_lo *= t[NV_VK_UNISON];
        d->init.detune_hi *= t[NV_VK_UNISON];
    }
    if (mask >> NV_VK_LID & 1)
        s.lid_db += t[NV_VK_LID];
    if (mask >> NV_VK_BOARD & 1)
        s.board_high_hz *= t[NV_VK_BOARD];
    if (mask >> NV_VK_PICKUP & 1)
        s.bridge_corner_hz *= t[NV_VK_PICKUP];
    if (s.kind == 4 && s.elec) {
        // (an electric guitar's: the pick at the open string, the template
        // note's as its fret has it; the loss its decay law reads)
        if (mask >> NV_VK_PICK & 1) {
            s.eg_sp *= t[NV_VK_PICK];
            s.pk_sp *= t[NV_VK_PICK];
            s.strike_point *= t[NV_VK_PICK];
        }
        if (mask >> NV_VK_STRINGS & 1) {
            if (s.sp_decay)
                s.sp_wind *= t[NV_VK_STRINGS];
            else
                s.harmonic_decay_db *= t[NV_VK_STRINGS];
        }
        if (mask >> NV_VK_TONE & 1)
            s.tone_turn *= t[NV_VK_TONE];
        return;
    }
    if (s.kind == 5) {
        // (an electric piano's: its pickup's parameters and the swing; each
        // note's layers nv_voice_init's from them)
        if (mask >> NV_VK_TINE & 1)
            s.ep_p[0] += t[NV_VK_TINE];
        if (mask >> NV_VK_REED & 1)
            s.ep_p[0] += t[NV_VK_REED];
        if (mask >> NV_VK_GAP & 1)
            s.ep_p[1] *= t[NV_VK_GAP];
        if (mask >> NV_VK_SWING & 1)
            s.ep_defl *= t[NV_VK_SWING];
        if (mask >> NV_VK_TONEBAR & 1)
            for (int i = 0; i < s.n_tb; i++)
                s.tb_g[i] *= t[NV_VK_TONEBAR];
        return;
    }
    if (mask)
        nv_hammer_note(&s);                 // (its prototype's hammer shares: the export's, of the moved class)
}

size_t nv_noteclass_size(void) { return sizeof(NoteClass); }

// THE SETTINGS NAMED: each distinct (transform, mask) its id, for as long as
// the process runs (a variation key holds 11 bits of it)
// -- and the part's own tuning with them (Ben, 2026-11-27: a part's tuning;
// the id rides the patch key as the knobs do, and a program change clears
// both): a tuner name's id, tid
static std::mutex g_vc_mu;
struct VcSet {
    std::array<double, NV_VK_N> t;
    int mask, tid;
};
static std::vector<VcSet> g_vc_set(1);      // ([0] none)
static std::vector<std::string> g_tn_set(1);    // (tuner names by id: [0] "")
int nv_tuner_id(const char *name)
{
    if (!name || !*name)
        return 0;
    std::lock_guard<std::mutex> lk(g_vc_mu);
    for (size_t i = 1; i < g_tn_set.size(); i++)
        if (g_tn_set[i] == name)
            return (int)i;
    g_tn_set.emplace_back(name);
    return (int)g_tn_set.size() - 1;
}
const char *nv_tuner_name(int tid)
{
    std::lock_guard<std::mutex> lk(g_vc_mu);
    return tid > 0 && (size_t)tid < g_tn_set.size() ? g_tn_set[(size_t)tid].c_str() : "";
}
int nv_voicing_id_t(const double *t, int mask, int tid)
{
    mask &= (1 << NV_VK_N) - 1;
    if (!mask && tid <= 0)
        return 0;
    std::array<double, NV_VK_N> a{};
    for (int i = 0; i < NV_VK_N; i++)
        a[i] = (mask >> i & 1) ? t[i] : 0.0;
    tid = std::max(0, tid);
    std::lock_guard<std::mutex> lk(g_vc_mu);
    for (size_t i = 1; i < g_vc_set.size(); i++)
        if (g_vc_set[i].mask == mask && g_vc_set[i].tid == tid && g_vc_set[i].t == a)
            return (int)i;
    if (g_vc_set.size() >= 2048)
        return -1;                          // (full: the caller keeps what it had)
    g_vc_set.push_back(VcSet{a, mask, tid});
    return (int)g_vc_set.size() - 1;
}
int nv_voicing_id(const double *t, int mask) { return nv_voicing_id_t(t, mask, 0); }
int nv_voicing_tid(int vid)
{
    std::lock_guard<std::mutex> lk(g_vc_mu);
    return vid > 0 && (size_t)vid < g_vc_set.size() ? g_vc_set[(size_t)vid].tid : 0;
}

// A VOICE THROUGH SETTING vid: its class copied and moved, kept -- made
// again when the class it came from has changed since (a room's fields
// written into every class: the copy's would be the old room's); a copy
// replaced is kept too (a cache built from it may still hold it)
struct VoicedClass {
    std::unique_ptr<NoteClass> base, made;
};
static std::map<std::pair<const NoteClass *, int>, VoicedClass> g_vc_made;
static std::vector<std::unique_ptr<NoteClass>> g_vc_old;
const NoteClass *nv_voice_variant(const NoteClass *k, int vid)
{
    if (!k || vid <= 0)
        return k;
    std::lock_guard<std::mutex> lk(g_vc_mu);
    if ((size_t)vid >= g_vc_set.size() || !g_vc_set[(size_t)vid].mask)
        return k;                           // (a tuning alone moves no class: its cache's table)
    VoicedClass &e = g_vc_made[std::make_pair(k, vid)];
    if (e.made && memcmp(e.base.get(), k, sizeof(NoteClass)) == 0)
        return e.made.get();
    if (e.made)
        g_vc_old.push_back(std::move(e.made));
    e.base.reset(new NoteClass(*k));
    e.made.reset(new NoteClass(*k));
    nv_voicing_apply(e.made.get(), g_vc_set[(size_t)vid].t.data(), g_vc_set[(size_t)vid].mask);
    return e.made.get();
}
int nv_tcache_var(void *h) { return ((nv::live::Cache *)h)->var; }

// BANK SELECT's tables for live's templates (the export's VARS: as nv_song_vars
// takes them, each entry's trim live's -- a file that is not GS's), each slot's
// organ, and K's length with the variations' region (the drones' before it)
void nv_live_vars(int nent, const int *nls, const int *ls, const double *trim, const int *gs, const int *gm2,
                  int nslot, const OrganSpec *const *so, const int *soff, const OrganSpec *const *sog,
                  long long kn)
{
    g_var_nls.assign(nls, nls + nent);
    g_var_off.assign(nent, 0);
    int t = 0;
    for (int e = 0; e < nent; e++) {
        g_var_off[e] = t;
        t += nls[e];
    }
    g_var_ls.assign(ls, ls + 4 * (size_t)t);
    g_var_trim.assign(trim, trim + nent);
    g_var_gs.assign(gs, gs + 5 * 128 * 128);
    g_var_gm2.assign(gm2, gm2 + 128 * 128);
    g_slot_organ.assign(so, so + nslot);
    g_slot_off.assign(soff, soff + nslot + 1);
    g_slot_og.assign(sog, sog + soff[nslot]);
    g_k_n = kn;
}

// an organ template's rank ri (t["ranks"]), its P through *n; NULL where it has none
void *nv_tmpl_rank(void *t, int ri, long long *n)
{
    nv::live::Template *T = (nv::live::Template *)t;
    if (ri < 0 || ri >= (int)T->ranks.size() || !T->ranks[ri].P)
        return nullptr;
    *n = T->ranks[ri].P;
    return &T->ranks[ri];
}

// live._glide's coefficients for a press on key tgt from key src: (g, tau,
// cutoff) at CC5 cc5 -- the class's mechanism, where it reaches -- or 0
// where it does not glide. moog_tau > 0: a Moog's GLIDE knob's lag (in
// cents) in place of CC5's time, as the kernel's (moog.glide_kernel_tau)
int nv_tcache_glide(void *h, int program, int src, int tgt, int cc5, double *out, double moog_tau)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (tgt < 0 || tgt > 127 || program < 0 || program > 127)
        return 0;
    const NoteClass *k = C->cls(program, tgt);     // (its variation's, where it is one)
    if (!k || !k->glide_mech)
        return 0;
    if (src < 0 || src > 127 || C->freq[src] <= 0.0 || C->freq[tgt] <= 0.0)
        return 0;
    if (!isnan(k->glide_reach) && std::abs(tgt - src) > k->glide_reach + 1e-9)
        return 0;
    double ft = C->freq[tgt], fs = C->freq[src];
    double v = std::min(127.0, std::max(0.0, (double)cc5)) / 127.0;
    double t1 = k->porta_fast * pow(k->porta_slow / k->porta_fast, v);
    double tau = k->glide_mech == 2 ? std::max(1e-4, t1) : std::max(1e-4, t1 * fabs(1.0 / fs - 1.0 / ft) / k->porta_d_semi);
    if (moog_tau > 0.0)
        tau = moog_tau * log(2.0) / log(1.0 + sqrt(ft / fs));
    out[0] = ft / fs - 1.0;
    out[1] = tau;
    out[2] = tau * k->porta_settle;
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
    case 9: return T->push.empty() ? nullptr : T->push.data();
    }
    return nullptr;
}

}  // extern "C"

extern "C" const nv::live::Template *nv_tcache_lookup(void *h, int note, int bucket, int speed)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (speed >= nv::live::DV_BASE) {           // (an edited drum key's: the variants' map)
        const nv::live::Cache::VMap *vm = C->vmap.load(std::memory_order_acquire);
        if (!vm)
            return nullptr;
        auto vt = vm->find(std::make_tuple(note, bucket, speed));
        return vt == vm->end() ? nullptr : vt->second;
    }
    if (C->s_nb > 0) {                          // (the slots: what a builder adds, safely)
        long ix = C->slot_of(note, bucket, speed);
        return ix < 0 ? nullptr : C->slot[ix].load(std::memory_order_acquire);
    }
    auto it = C->tm.find(std::make_tuple(note, bucket, speed));
    return it == C->tm.end() ? nullptr : &it->second;
}

// A TEMPLATE ADDED WHILE THE CACHE PLAYS (A5's on demand: the note that
// found none, then its octave), built at its bucket's velocity: 1 built, 0
// there already, -1 not (no slots, or none to build); *bytes its size
extern "C" int nv_tcache_add(void *h, int program, int note, int bucket, int speed, long long *bytes)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (bytes)
        *bytes = 0;
    const long ix = C->slot_of(note, bucket, speed);
    if (ix < 0)
        return -1;
    if (C->slot[ix].load(std::memory_order_acquire))
        return 0;
    int vel = (int)std::min(127.0, (bucket + 0.5) * 128.0 / C->s_nb);     // Patch.bucket_vel
    nv::live::Template T;
    if (!C->build(program, note, vel, speed, T))
        return -1;
    if (bytes)
        *bytes = (long long)tmpl_bytes(T);
    C->keep(std::make_tuple(note, bucket, speed), std::move(T));
    return 1;
}

// (a template there: 1, else 0)
extern "C" int nv_tcache_has(void *h, int note, int bucket, int speed)
{
    return nv_tcache_lookup(h, note, bucket, speed) != nullptr;
}

// ...its shape (buckets, wheel steps into sp[8]): 0 none (no slots)
extern "C" int nv_tcache_slots(void *h, int *nb, int *sp)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (C->s_nb <= 0)
        return 0;
    *nb = C->s_nb;
    for (int q = 0; q < C->s_nsp; q++)
        sp[q] = C->s_sp[q];
    return C->s_nsp;
}

// an edited drum key's axis (live._drum_axis): pitch, pan (INT_MIN unset)
extern "C" int nv_drum_axis(int pitch, int pan) { return nv::live::drum_axis(pitch, pan); }

// ...a user set key's (ud: its PLAY NOTE, pan, source set, source key; -1 unset)
extern "C" int nv_drum_axis_ud(int pitch, int pan, const int *ud, int uset)
{
    return nv::live::drum_axis_ud(pitch, pan, ud, uset);
}

extern "C" int nv_tcache_build_var(void *h, int program, int note, int bucket, int nb, int axis);

// A USER SET KEY's TEMPLATE, built with its spec (nv_tcache_build_var's)
extern "C" int nv_tcache_build_var_ud(void *h, int program, int note, int bucket, int nb, int axis, int pitch,
                                      int pan, const int *ud)
{
    nv::live::g_ud_pitch = pitch;
    nv::live::g_ud_pan = pan;
    nv::live::g_ud_set = program - 64;
    for (int i = 0; i < 4; i++)
        nv::live::g_ud[i] = ud[i];
    return nv_tcache_build_var(h, program, note, bucket, nb, axis);
}

// AN EDITED DRUM KEY's TEMPLATE, built (one writer: the builder, or in step)
// and published: 1 built, 0 there already, -1 not built
extern "C" int nv_tcache_build_var(void *h, int program, int note, int bucket, int nb, int axis)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    auto k = std::make_tuple(note, bucket, axis);
    const nv::live::Cache::VMap *vm = C->vmap.load(std::memory_order_acquire);
    if (vm && vm->count(k))
        return 0;
    int vel = (int)std::min(127.0, (bucket + 0.5) * 128.0 / nb);    // Patch.bucket_vel
    std::unique_ptr<nv::live::Template> T(new nv::live::Template);
    if (!C->build(program, note, vel, axis, *T))
        return -1;
    std::unique_ptr<nv::live::Cache::VMap> nm(vm ? new nv::live::Cache::VMap(*vm) : new nv::live::Cache::VMap);
    (*nm)[k] = T.get();
    C->vstore.push_back(std::move(T));
    C->vmap.store(nm.get(), std::memory_order_release);
    C->vgrave.push_back(std::move(nm));
    return 1;
}
