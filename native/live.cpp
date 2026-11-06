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
static std::vector<uint8_t> one_note(int program, int note, int vel, int ch, int fast, uint32_t end = 480,
                                     const OrganSpec *og = nullptr)
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
// the tuner's raga, as blockrender's prepare finds it (T.raga_sa_note: -1 none;
// its swaras): the cache's whose template this thread is building
static thread_local int g_raga_sa = -1, g_raga_nsw = 0;
static thread_local double g_raga_sw[12];

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
    const NoteClass *kc = (!kit && program >= 0 && program < 128) ? K[128 * program + note] : nullptr;
    const OrganSpec *og = kc ? kc->organ : nullptr;
    // (a drone-wheel program's: built with its drones CORKED -- live sounds
    // them as its own held voices, live._raw_template's fast = 0)
    const NoteClass *pc_ = (!kit && program >= 0 && program < 128) ? K[128 * program + 60] : nullptr;
    if (pc_ && pc_->drone_wheel && fast < 0)
        fast = 0;
    std::vector<uint8_t> f = kit ? nv::live::one_note(program, note, vel, 9, fast, 480 * 18)
                                 : nv::live::one_note(program, note, vel, 0, fast, 480, og);
    int err = 0;
    void *m = nv_midi_read(f.data(), (long long)f.size(), &err);
    if (!m)
        return -1000000001LL;
    void *song = nv_song_new();
    nv_song_tuning(song, -1, 0.0, freq);
    if (g_raga_sa >= 0)
        nv_song_eastern(song, nullptr, 1, g_raga_sa, g_raga_sw, g_raga_nsw);
    if (kit) {
        nv_song_kits(song, kit->f0.data(), kit->seat.data());
        nv_song_chokes(song, kit->choke.data());
    }
    nv_midi_song(m, song, trim);
    if (og) {                               // the organ on its channel, its stops all drawn
        std::vector<const OrganSpec *> po(128, nullptr);
        po[program] = og;
        nv_song_organ(song, 0, og, po.data());
        nv_song_organ_wind_rows(song, 0);   // (its rows' wind rows, as the one-note file has them)
    }
    if (kit)
        nv_song_strokes(song, kit->skind.data(), kit->spar.data());
    double total = nv_midi_total(m);
    nv_song_finish(song, total);
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
    if (P >= 0)                                 // the speaker cabinet (_prep_cabinet), before any rotor
        nv_cabinet_pass(song, *rowsp, P);
    // A ROTARY VOICE'S CABINET (_raw_template: leslie.expand with SIDEBANDS
    // off): the cabinet's colour, the crossover's copies (leslie_flip), each
    // row's Doppler at the rotor's speed from the file's CC1 (fast), else the
    // voice's own -- the swing itself is the slab's
    if (les && P >= 0 && nv_song_leslie(song, -1, nullptr) > 0) {
        long long c;
        int kind_ = nv_song_leslie(song, 0, &c);
        int nc = nv_song_ccs(song, c, 1, nullptr, nullptr, 0);
        std::vector<double> ct(nc), req;
        std::vector<int> cv(nc);
        nv_song_ccs(song, c, 1, ct.data(), cv.data(), nc);
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

// tremolo.expand: every row of a modulated channel (in mask, when given: a
// Tremolo stop's notes) its sideband pair, appended in order -- the upper
// then the lower, at the rate either side of the row's, each half the depth
// (a pan's right ear the opposite sign, its mono sum none); a section's
// players each their own rate and phase (scatter). The rows NCOLS each,
// *P of them, realloc'd; a damper's dk/dg (dm[0], dm[1]) copied with them.
// The channels nch of chans, each's (rate, depth, stereo, scatter) in cfg;
// mask nmask long (NULL: every row). Returns the sidebands made.
extern "C" long long nv_chorus_expand(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                                      const double *sends, const int *ncents, const double *cents,
                                      const int *kinds, double sr)
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
    for (int q = 0; q < nch; q++) {
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
        // ...and the dry share comes down by what the wet took
        if (made && dry != 1.0)
            for (long long i : sel)
                for (int c : {cAL, cAR, cAM})
                    rows[(size_t)NCOLS * i + c] = rows[(size_t)NCOLS * i + c] * dry;
    }
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

extern "C" long long nv_tremolo_expand(double **rowsp, long long *Pp, void **dm, int nch, const long long *chans,
                                       const double *cfg, const char *mask, long long nmask, double sr)
{
    if (nch <= 0)
        return 0;
    const int cOM = emit_col("om"), cP0 = emit_col("p0"), cP0R = emit_col("p0R"), cAL = emit_col("aL"),
              cAR = emit_col("aR"), cAM = emit_col("aM"), cMCH = emit_col("mch"), cPL = emit_col("pl");
    const long long n = *Pp;
    std::vector<double> extra;
    std::vector<long long> src;
    for (long long i = 0; i < n; i++) {
        if (mask && (i >= nmask || !mask[i]))
            continue;
        const double *row = *rowsp + (size_t)NCOLS * i;
        int q = 0;
        while (q < nch && chans[q] != (long long)(int)row[cMCH])
            q++;
        if (q == nch)
            continue;
        const double *c = cfg + 4 * q;
        double rate = c[0], depth = c[1], scatter = c[3];
        bool stereo = c[2] != 0.0;
        if (depth <= 0.0 || rate <= 0.0)
            continue;
        double ph = 0.0;
        if (scatter > 0.0) {
            PyRandom r;
            pyr_seed(&r, 0x7E30 + chans[q] * 977 + (long long)row[cPL]);
            rate = rate * (1.0 + scatter * pyr_uniform(&r, -1.0, 1.0));
            ph = pyr_uniform(&r, 0.0, 2.0 * M_PI);
        }
        double dw = 2.0 * M_PI * rate / sr, half = 0.5 * depth;
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
    bool drums = false;                 // a drum part: the program is its set (kit's tables)
    Kits kit;
    std::vector<double> les;            // the Leslie's constants (leslie.cpp's L_*), empty: none
    int raga_sa = -1, raga_nsw = 0;     // its tuner's raga (a raga tuner's: Sa's note, -1 none; the swaras)
    int gm2 = 0;                        // its tuner is gm2's: the store's tables over it (_mts_ratio)
    double raga_sw[12];
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
        std::vector<long long> srows, prows, flips;
        std::vector<double> jrows;
        std::vector<long long> rrows, grows;
        double mft[30];
        g_raga_sa = raga_sa;                // (the template's prepare: T.raga_sa_note, T.raga_spec)
        g_raga_nsw = raga_nsw;
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
        int q = 128 * program + note;
        const NoteClass *nc = (q >= 0 && q < NV_K_DRUMS) ? K[(drums ? NV_K_DRUMS : 0) + q] : nullptr;
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
                    for (int c = 0; c < 27; c++)
                        cut(D.f4[c], T.f4[c]);
                    for (int c = 0; c < 4; c++)
                        cut(D.f4n[c], T.f4n[c]);
                    for (int c = 0; c < 2; c++)
                        cut(D.i8[c], T.i8[c]);
                    for (int c = 0; c < 6; c++)
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
                for (int c = 0; c < 27; c++)
                    T.f4[c].swap(K2.f4[c]);
                for (int c = 0; c < 4; c++)
                    T.f4n[c].swap(K2.f4n[c]);
                for (int c = 0; c < 2; c++)
                    T.i8[c].swap(K2.i8[c]);
                for (int c = 0; c < 6; c++)
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
                for (int c = 0; c < 27; c++)
                    cut(R.f4[c], T.f4[c]);
                for (int c = 0; c < 4; c++)
                    cut(R.f4n[c], T.f4n[c]);
                for (int c = 0; c < 2; c++)
                    cut(R.i8[c], T.i8[c]);
                for (int c = 0; c < 6; c++)
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
                for (int c = 0; c < 27; c++)
                    cut(J.f4[c], T.f4[c]);
                for (int c = 0; c < 4; c++)
                    cut(J.f4n[c], T.f4n[c]);
                for (int c = 0; c < 2; c++)
                    cut(J.i8[c], T.i8[c]);
                for (int c = 0; c < 6; c++)
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
                for (int c = 0; c < 27; c++)
                    split(Rl.f4[c], T.f4[c]);
                for (int c = 0; c < 4; c++)
                    split(Rl.f4n[c], T.f4n[c]);
                for (int c = 0; c < 2; c++)
                    split(Rl.i8[c], T.i8[c]);
                for (int c = 0; c < 6; c++)
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

// the Leslie's constants for a rotary voice's templates (the export's LESL)
void nv_tcache_leslie(void *h, const double *L, int n) { ((nv::live::Cache *)h)->les.assign(L, L + n); }

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
// the class a melodic program's key plays (NULL: none)
const NoteClass *nv_tcache_note_class(void *h, int program, int note)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (note < 0 || note > 127 || program < 0 || program > 127)
        return nullptr;
    return C->K[(C->drums ? NV_K_DRUMS : 0) + 128 * program + note];
}

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
    const NoteClass *k = C->K[128 * program + 60];
    return k ? k->organ : nullptr;
}

// the cache's templates, each in turn (i < n): its count with i < 0
const nv::live::Template *nv_tcache_at(void *h, long i, long *n)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
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
    return C && program >= 0 && program < 128 ? C->trim[program] : 1.0;
}

// the class a key of a program plays (none on a drum set's cache)
const NoteClass *nv_tcache_class_key(void *h, int program, int key)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (!C || C->drums || program < 0 || program > 127 || key < 0 || key > 127)
        return nullptr;
    return C->K[128 * program + key];
}

const NoteClass *nv_tcache_class(void *h, int program)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (!C || C->drums || program < 0 || program > 127)
        return nullptr;
    return C->K[128 * program + 60];
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
// where it does not glide
int nv_tcache_glide(void *h, int program, int src, int tgt, int cc5, double *out)
{
    nv::live::Cache *C = (nv::live::Cache *)h;
    if (tgt < 0 || tgt > 127 || program < 0 || program > 127)
        return 0;
    const NoteClass *k = C->K[(C->drums ? NV_K_DRUMS : 0) + 128 * program + tgt];
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
    auto it = C->tm.find(std::make_tuple(note, bucket, speed));
    return it == C->tm.end() ? nullptr : &it->second;
}
